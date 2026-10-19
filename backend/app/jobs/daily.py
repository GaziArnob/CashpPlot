"""Daily job: refresh scores and the action plan, and alert the owner when a cash crunch is coming.

Run it by hand:   python -m app.jobs.daily
The app also runs it every morning (see scheduler.py). Running it twice on the same day is safe:
snapshots are replaced and the alert is sent only once per day.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import alerts, notify, services
from app.ai.templates import day, money
from app.db import SessionLocal
from app.models import AuditLog, Business

log = logging.getLogger(__name__)


def run_for_business(db: Session, business: Business) -> dict:
    collections = services.collection_scores(db, business, persist=True)
    prods = services.product_scores(db, business, persist=True)
    plan = services.action_plan(db, business)
    fc = services.cash_forecast(db, business, 30)

    alert_sent = False
    message = None
    if fc["first_shortage"]:
        s = fc["first_shortage"]
        cur = business.currency
        first_step = next((a["title"] for a in plan["actions"] if not a["optional"] and a["status"] == "open"), None)
        message = (f"Cash crunch ahead: cash may fall {money(s['gap'], cur)} below your safety level on {day(s['date'])}"
                   f" (largest gap in 30 days: {money(fc['largest_gap'], cur)}).")
        if first_step:
            message += f" First step: {first_step}."
        # The same key the dashboard rule uses, so the two never raise it twice for the same shortage day.
        notify.create(db, business, "cash_shortage", message, key=f"shortage:{s['date']}", link="/cashflow",
                      cooldown_days=3)
        db.commit()
        # The dashboard may already have raised the notification; the owner alert still goes out once a day.
        if db.scalar(select(AuditLog.id).where(AuditLog.business_id == business.id, AuditLog.action == "alert_sent",
                                               AuditLog.created_at >= services.today_start_utc()).limit(1)) is None:
            alerts.send(db, business, "Cash crunch predicted", message)
            alert_sent = True

    # Every other alert (overdue customers, bills, loan installments, trial) and urgent ones by email.
    services.refresh_notifications(db, business, fc, services.recovery_priority(db, business))
    emailed = notify.send_pending_emails(db, business)

    return {
        "business_id": business.id,
        "date": services.today().isoformat(),
        "customers_scored": len(collections["customers"]),
        "products_scored": len(prods["products"]),
        "plan_actions": len(plan["actions"]),
        "cash_crunch": fc["first_shortage"],
        "alert_sent": alert_sent,
        "alert_message": message,
        "emailed": emailed,
    }


def run_all() -> list[dict]:
    db = SessionLocal()
    results = []
    try:
        for business in db.scalars(select(Business)).all():
            try:
                results.append(run_for_business(db, business))
            except Exception:  # one broken business must not stop the others
                log.exception("Daily job failed for business %s", business.id)
                db.rollback()
                results.append({"business_id": business.id, "error": True})
    finally:
        db.close()
    log.info("Daily job finished for %d businesses", len(results))
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for r in run_all():
        print(r)
