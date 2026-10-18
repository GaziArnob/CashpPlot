"""Daily job: refresh scores and the action plan, and alert the owner when a cash crunch is coming.

Run it by hand:   python -m app.jobs.daily
The app also runs it every morning (see scheduler.py). Running it twice on the same day is safe:
snapshots are replaced and the alert is sent only once per day.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import alerts, services
from app.ai.templates import day, money
from app.db import SessionLocal
from app.models import Business, Notification

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
        since = services.today_start_utc()
        already = db.scalar(select(Notification).where(
            Notification.business_id == business.id, Notification.type == "cash_crunch",
            Notification.created_at >= since))
        if already is None:
            db.add(Notification(business_id=business.id, type="cash_crunch", message=message))
            db.commit()
            alerts.send(db, business, "Cash crunch predicted", message)
            alert_sent = True

    return {
        "business_id": business.id,
        "date": services.today().isoformat(),
        "customers_scored": len(collections["customers"]),
        "products_scored": len(prods["products"]),
        "plan_actions": len(plan["actions"]),
        "cash_crunch": fc["first_shortage"],
        "alert_sent": alert_sent,
        "alert_message": message,
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
