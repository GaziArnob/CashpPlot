"""Daily action plan and its checklist (done / dismissed / reopened), with an audit trail."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import services
from app.db import get_db
from app.deps import get_business, get_current_user, needs, owned, require_owner
from app.models import ActionLog, Business, Recommendation, User

router = APIRouter(tags=["actions"], dependencies=[Depends(require_owner), Depends(needs("advisor"))])


class ActionDoneIn(BaseModel):
    actual_amount: float | None = Field(default=None, ge=-1e10, le=1e10)  # what it really brought in
    note: str | None = Field(default=None, max_length=500)


class ActionNoteIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)


@router.get("/action-plan")
def get_action_plan(business: Business = Depends(get_business), db: Session = Depends(get_db)):
    """Today's prioritized plan: cash impact, time to impact, risk and reasoning for each step."""
    return {"currency": business.currency, **services.action_plan(db, business)}


def _set_status(db: Session, business: Business, user: User, action_id: int, new_status: str, log_action: str,
                note: str | None = None, actual: float | None = None) -> dict:
    rec = owned(db, Recommendation, action_id, business)
    if rec.status == new_status:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Action is already {new_status}")
    rec.status = new_status
    db.add(ActionLog(business_id=business.id, recommendation_id=rec.id, action=log_action,
                     actual_amount=actual, note=note, user_id=user.id))
    db.commit()
    return {"id": rec.id, "status": rec.status}


@router.post("/actions/{action_id}/mark-done")
def mark_done(action_id: int, body: ActionDoneIn | None = None, business: Business = Depends(get_business),
              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    body = body or ActionDoneIn()
    return _set_status(db, business, user, action_id, "done", "done", body.note, body.actual_amount)


@router.post("/actions/{action_id}/dismiss")
def dismiss(action_id: int, body: ActionNoteIn | None = None, business: Business = Depends(get_business),
            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _set_status(db, business, user, action_id, "dismissed", "dismissed", body.note if body else None)


@router.post("/actions/{action_id}/reopen")
def reopen(action_id: int, business: Business = Depends(get_business), user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    return _set_status(db, business, user, action_id, "open", "reopened")


@router.get("/actions/{action_id}/log")
def action_log(action_id: int, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    owned(db, Recommendation, action_id, business)
    rows = db.scalars(select(ActionLog).where(ActionLog.recommendation_id == action_id)
                      .order_by(ActionLog.created_at)).all()
    return [{"action": r.action, "actual_amount": r.actual_amount, "note": r.note, "at": r.created_at} for r in rows]
