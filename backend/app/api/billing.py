"""Plans. In this build switching plans takes no payment (BILLING_MODE=demo); see app/plans.py."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import plans, stripe_client
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
    mode = get_settings().billing_mode
    note = {"demo": "Demo billing: switching plans takes no payment.",
            "stripe": None if stripe_client.configured() else "Payments are not set up yet."}.get(mode)
    return {**plans.describe(business), "billing_mode": mode, "payments_connected": mode != "demo",
            "can_checkout": mode == "stripe" and stripe_client.configured(),
            "has_subscription": bool(business.stripe_customer_id), "note": note}


def _stripe(fn, *a):
    try:
        return fn(*a)
    except stripe_client.StripeError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))


@router.post("/checkout")
def checkout(business: Business = Depends(get_business), owner: User = Depends(require_owner)):
    """Start paying for Pro. The owner is sent to Stripe's page; the webhook upgrades the plan once it is paid."""
    if get_settings().billing_mode != "stripe" or not stripe_client.configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Payments are not set up yet")
    if business.plan == "pro" and business.stripe_subscription_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "You already have a Pro subscription")
    return {"url": _stripe(stripe_client.create_checkout, business.id, owner.email, business.stripe_customer_id)}


@router.post("/portal")
def portal(business: Business = Depends(get_business)):
    """Stripe's page to change the card, see invoices or cancel."""
    if not business.stripe_customer_id or not stripe_client.configured():
        raise HTTPException(status.HTTP_409_CONFLICT, "There is no subscription to manage")
    return {"url": _stripe(stripe_client.create_portal, business.stripe_customer_id)}


@router.post("/plan")
def change_plan(body: PlanIn, business: Business = Depends(get_business), owner: User = Depends(require_owner),
                db: Session = Depends(get_db)):
    mode = get_settings().billing_mode
    if mode == "stripe":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Use checkout to upgrade, or the billing portal to cancel; the plan then updates by itself")
    if mode != "demo":
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Payments are not connected yet")
    business.plan = body.plan
    business.plan_expires_at = None  # a chosen plan has no trial end
    db.commit()
    audit(db, "plan_changed", owner.email, business_id=business.id, user_id=owner.id, target=body.plan)
    return {**plans.describe(business), "billing_mode": "demo"}
