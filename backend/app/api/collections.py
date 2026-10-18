"""Receivable prioritization: ranked collections, bilingual reminders, credit limits."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import services
from app.ai import templates
from app.ai.text import polish_reminder
from app.db import get_db
from app.deps import ai_limiter, audit, get_business, needs, owned, require_owner
from app.models import Business, CollectionScore, Customer, Invoice, Reminder
from app.schemas import ReminderOut

router = APIRouter(tags=["collections"], dependencies=[Depends(require_owner), Depends(needs("collections"))])

# Which message style fits each recommended action.
ACTION_TO_TEMPLATE = {"stop_credit": "final", "visit": "firm", "call": "firm", "discount": "discount",
                      "wait": "upcoming"}


@router.get("/collections/priority")
def collection_priority(business: Business = Depends(get_business), db: Session = Depends(get_db)):
    """Ranked list for today; also saved as today's snapshot in collection_scores."""
    result = services.collection_scores(db, business, persist=True)
    customers = result["customers"]
    return {
        "as_of": services.today().isoformat(),
        "currency": business.currency,
        "model": result["model"],
        "shortage_gap": result["shortage_gap"],
        "total_outstanding": sum(c["outstanding"] for c in customers),
        "total_overdue": sum(c["overdue_amount"] for c in customers),
        "expected_in_7_days": round(sum(c["outstanding"] * c["p_pay_7d"] for c in customers)),
        "customers": customers,
    }


@router.get("/collections/{customer_id}/history")
def score_history(customer_id: int, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    owned(db, Customer, customer_id, business)
    rows = db.scalars(select(CollectionScore).where(CollectionScore.customer_id == customer_id)
                      .order_by(CollectionScore.as_of)).all()
    return [{"as_of": r.as_of, "score": r.score, "p_pay_7d": r.p_pay_7d, "aging_bucket": r.aging_bucket,
             "action": r.recommended_action, "credit_limit": r.credit_limit} for r in rows]


@router.post("/collections/{customer_id}/reminder", response_model=ReminderOut, status_code=201,
             dependencies=[Depends(ai_limiter)])
def collection_reminder(customer_id: int, polish: bool = True,
                        business: Business = Depends(get_business), db: Session = Depends(get_db)):
    """Draft (never send) a reminder for everything this customer owes, in the style its action calls for."""
    customer = owned(db, Customer, customer_id, business)
    scored = {c["customer_id"]: c for c in services.collection_scores(db, business)["customers"]}
    c = scored.get(customer.id)
    if c is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This customer owes nothing")
    oldest = c["invoices"][0]
    style = ACTION_TO_TEMPLATE.get(c["action"]) or c["tone"]
    text = templates.reminder(
        style, customer=customer.name, business=business.name, amount=c["outstanding"],
        currency=business.currency, due_date=oldest["due_date"], days=c["max_days_overdue"],
        discount_deadline=(services.today() + timedelta(days=3)).isoformat())
    generated_by = "template"
    if polish:
        text, generated_by = polish_reminder(text, style, customer.name, business.name, business.ai_mode)
    r = Reminder(business_id=business.id, invoice_id=oldest["invoice_id"], message=text, tone=style,
                 generated_by=generated_by)
    db.add(r)
    db.commit()
    return r


class CreditLimitIn(BaseModel):
    amount: float | None = Field(default=None, ge=0, le=1e10)  # omit to apply the suggestion


@router.post("/customers/{customer_id}/credit-limit")
def set_credit_limit(customer_id: int, body: CreditLimitIn, business: Business = Depends(get_business),
                     db: Session = Depends(get_db)):
    customer = owned(db, Customer, customer_id, business)
    amount = body.amount
    if amount is None:
        scored = {c["customer_id"]: c for c in services.collection_scores(db, business)["customers"]}
        if customer.id not in scored:
            raise HTTPException(status.HTTP_409_CONFLICT, "No suggestion: this customer owes nothing today")
        amount = scored[customer.id]["credit_limit"]
    customer.credit_limit = amount
    db.commit()
    audit(db, "credit_limit_set", business.owner.email, business_id=business.id,
          target=f"customer:{customer.id}={amount}")
    return {"customer_id": customer.id, "credit_limit": amount}
