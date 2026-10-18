"""Plans. In this build switching plans takes no payment (BILLING_MODE=demo); see app/plans.py."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import plans
from app.config import get_settings
from app.db import get_db
from app.deps import audit, get_business, require_owner
from app.models import Business, User

router = APIRouter(prefix="/billing", tags=["billing"], dependencies=[Depends(require_owner)])


class PlanIn(BaseModel):
    plan: Literal["free", "pro"]
    confirm: Literal[True]


@router.get("/plan")
def current_plan(business: Business = Depends(get_business)):
    return {**plans.describe(business), "billing_mode": get_settings().billing_mode,
            "payments_connected": get_settings().billing_mode != "demo",
            "note": "Demo billing: switching plans takes no payment." if get_settings().billing_mode == "demo" else None}


@router.post("/plan")
def change_plan(body: PlanIn, business: Business = Depends(get_business), owner: User = Depends(require_owner),
                db: Session = Depends(get_db)):
    if get_settings().billing_mode != "demo":
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Payments are not connected yet")
    business.plan = body.plan
    business.plan_expires_at = None  # a chosen plan has no trial end
    db.commit()
    audit(db, "plan_changed", owner.email, business_id=business.id, user_id=owner.id, target=body.plan)
    return {**plans.describe(business), "billing_mode": "demo"}
