"""Stripe webhook: the only way a payment changes a plan. It has no login; the signature is the proof."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import stripe_client
from app.db import bypass_rls, get_db
from app.deps import audit
from app.models import Business

router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    event = stripe_client.verify_webhook(await request.body(), request.headers.get("stripe-signature"))
    if event is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid signature")
    bypass_rls(db)  # no signed-in business here; the verified event names the business
    obj = event.get("data", {}).get("object", {})
    kind = event.get("type")
    if kind == "checkout.session.completed" and obj.get("mode") == "subscription":
        ref = obj.get("client_reference_id")
        business = db.get(Business, int(ref)) if ref and ref.isdigit() else None
        if business is not None and obj.get("payment_status") in ("paid", "no_payment_required"):
            business.plan, business.plan_expires_at = "pro", None
            business.stripe_customer_id, business.stripe_subscription_id = obj.get("customer"), obj.get("subscription")
            db.commit()
            audit(db, "plan_changed", "stripe", business_id=business.id, target="pro")
    elif kind in ("customer.subscription.deleted", "customer.subscription.updated"):
        business = db.scalar(select(Business).where(Business.stripe_subscription_id == obj.get("id")))
        ended = kind == "customer.subscription.deleted" or obj.get("status") in ("canceled", "unpaid", "incomplete_expired")
        if business is not None and ended:
            business.plan, business.plan_expires_at, business.stripe_subscription_id = "free", None, None
            db.commit()
            audit(db, "plan_changed", "stripe", business_id=business.id, target="free")
    return {"received": True}
