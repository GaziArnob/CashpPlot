"""Notifications: one alert per thing, switchable by the owner, and optionally emailed when urgent.

An alert has a `dedupe_key` that names the thing it is about (a customer, a bill, a loan installment). The same key
is not raised again until its cooldown has passed, so an unpaid invoice does not nag every single day. A type the
owner has muted is never created. Urgent (critical) alerts are emailed by the daily job when the owner turned that
on and email is connected; the in-app list is always the main place they show up.
"""

import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import messaging
from app.models import Business, Notification, utcnow

log = logging.getLogger(__name__)

# type -> (label shown to the owner, default severity)
TYPES = {
    "cash_shortage": ("Cash shortage warnings", "critical"),
    "overdue": ("Customers far behind on paying", "warning"),
    "invoice_due": ("Invoices coming due", "info"),
    "bill_due": ("Supplier bills coming due", "warning"),
    "loan_due": ("Loan installments coming due", "warning"),
    "trial": ("Plan and trial reminders", "info"),
}


def label(kind: str) -> str:
    return TYPES.get(kind, (kind.replace("_", " ").capitalize(), "info"))[0]


def create(db: Session, business: Business, kind: str, message: str, *, key: str, link: str | None = None,
           cooldown_days: float = 7, severity: str | None = None) -> Notification | None:
    """Add an alert unless the type is muted or the same thing was already raised within its cooldown."""
    if kind in (business.muted_notifications or []):
        return None
    since = utcnow() - timedelta(days=cooldown_days)
    if db.scalar(select(Notification.id).where(Notification.business_id == business.id,
                                                Notification.dedupe_key == key,
                                                Notification.created_at >= since).limit(1)) is not None:
        return None
    n = Notification(business_id=business.id, type=kind, message=message[:500], dedupe_key=key, link=link,
                     severity=severity or TYPES.get(kind, ("", "info"))[1])
    db.add(n)
    db.flush()
    return n


def send_pending_emails(db: Session, business: Business) -> int:
    """Email the owner's recent critical alerts once each, if they asked for it and email is connected."""
    if not business.notify_email or not messaging.configured_channels()["email"]:
        return 0
    since = utcnow() - timedelta(days=2)
    pending = db.scalars(select(Notification).where(
        Notification.business_id == business.id, Notification.severity == "critical",
        Notification.emailed_at.is_(None), Notification.created_at >= since)).all()
    sent = 0
    for n in pending:
        try:
            messaging.send("email", to_email=business.owner.email, to_phone=None,
                           subject=f"CashPilot alert: {label(n.type)}", text=n.message)
        except (messaging.DeliveryError, ValueError):
            log.warning("Could not email alert %s for business %s", n.id, business.id)
            continue
        n.emailed_at = utcnow()
        sent += 1
    if sent:
        db.commit()
    return sent
