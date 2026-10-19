"""The owner's notification center: the list, unread count, read/delete, and which alerts to receive."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app import messaging, notify
from app.db import get_db
from app.deps import get_business, owned, require_owner
from app.models import Business, Notification

router = APIRouter(prefix="/notifications", tags=["notifications"], dependencies=[Depends(require_owner)])


class PreferencesIn(BaseModel):
    muted: list[str] = Field(default_factory=list, max_length=20)
    email: bool = False


def _out(n: Notification) -> dict:
    return {"id": n.id, "type": n.type, "label": notify.label(n.type), "message": n.message, "severity": n.severity,
            "link": n.link, "is_read": n.is_read, "created_at": n.created_at}


@router.get("")
def list_notifications(unread_only: bool = False, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                       business: Business = Depends(get_business), db: Session = Depends(get_db)):
    stmt = select(Notification).where(Notification.business_id == business.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit).offset(offset))
    return {"total": total, "items": [_out(n) for n in rows]}


@router.get("/summary")
def summary(business: Business = Depends(get_business), db: Session = Depends(get_db)):
    """Light enough to poll: the unread count and the latest few."""
    unread = db.scalar(select(func.count()).select_from(Notification).where(
        Notification.business_id == business.id, Notification.is_read.is_(False)))
    latest = db.scalars(select(Notification).where(Notification.business_id == business.id)
                        .order_by(Notification.created_at.desc(), Notification.id.desc()).limit(6))
    return {"unread": unread, "latest": [_out(n) for n in latest]}


@router.post("/read-all")
def read_all(business: Business = Depends(get_business), db: Session = Depends(get_db)):
    result = db.execute(update(Notification).where(Notification.business_id == business.id,
                                                    Notification.is_read.is_(False)).values(is_read=True))
    db.commit()
    return {"marked": result.rowcount}


@router.get("/preferences")
def get_preferences(business: Business = Depends(get_business)):
    muted = set(business.muted_notifications or [])
    return {"types": [{"type": k, "label": v[0], "severity": v[1], "muted": k in muted} for k, v in notify.TYPES.items()],
            "email": business.notify_email, "email_available": messaging.configured_channels()["email"]}


@router.put("/preferences")
def set_preferences(body: PreferencesIn, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    business.muted_notifications = sorted({m for m in body.muted if m in notify.TYPES})
    business.notify_email = body.email
    db.commit()
    return get_preferences(business)


@router.patch("/{notification_id}/read")
def mark_read(notification_id: int, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    n = owned(db, Notification, notification_id, business)
    n.is_read = True
    db.commit()
    return _out(n)


@router.delete("/{notification_id}", status_code=204)
def dismiss(notification_id: int, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    db.delete(owned(db, Notification, notification_id, business))
    db.commit()
