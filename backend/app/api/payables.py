"""Supplier negotiation assistant: conflicts, payment plans, negotiation drafts, financing comparison.

Safety rules enforced here:
  * The app never pays a supplier, never sends a message and never applies for financing.
  * A plan goes draft -> approved (owner approves proposing it) -> accepted/rejected (the supplier's
    answer, recorded by the owner). Only an ACCEPTED plan changes the cash forecast.
  * Editing an approved plan sends it back to draft: approval always matches what was approved.
  * Marking an installment paid only RECORDS a payment the owner made themselves.
"""

from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import services
from app.ai import negotiation
from app.db import get_db
from app.deps import ai_limiter, audit, get_business, get_current_user, owned
from app.engines import payables
from app.models import (Bill, Business, NegotiationDraft, PayablesRecommendation, PaymentPlan,
                        PaymentPlanInstallment, Supplier, Transaction, User, utcnow)

router = APIRouter(tags=["payables"])

MAX_INSTALLMENTS = 12
MAX_DAYS_AHEAD = 365
CENT = 0.01


# Analysis and history
@router.get("/payables/analysis")
def analysis(business: Business = Depends(get_business), db: Session = Depends(get_db)):
    """Dated 30-day cash flow, conflicts, per-bill options, financing comparison and recommendation."""
    return services.payables_analysis(db, business)


@router.post("/payables/recommendations", status_code=201)
def run_recommendation(business: Business = Depends(get_business), db: Session = Depends(get_db)):
    """Run the analysis and keep the recommendation in history."""
    result = services.payables_analysis(db, business, save=True)
    last = db.scalar(select(PayablesRecommendation).where(PayablesRecommendation.business_id == business.id)
                     .order_by(PayablesRecommendation.id.desc()))
    return {"id": last.id, **result}


@router.get("/payables/recommendations")
def recommendation_history(limit: int = Query(20, ge=1, le=100), business: Business = Depends(get_business),
                           db: Session = Depends(get_db)):
    rows = db.scalars(select(PayablesRecommendation).where(PayablesRecommendation.business_id == business.id)
                      .order_by(PayablesRecommendation.id.desc()).limit(limit)).all()
    return [{"id": r.id, "created_at": r.created_at, "shortfall": r.shortfall, "shortfall_date": r.shortfall_date,
             "headline": r.headline, "total_cost": r.total_cost,
             "steps": [{"type": s["type"], "kind": s["kind"], "cost": s["cost"], "relief": s["relief"],
                        "name": s.get("supplier") or s.get("name")}
                       for s in r.payload["recommendation"]["steps"]]} for r in rows]


@router.get("/payables/recommendations/{rec_id}")
def recommendation_detail(rec_id: int, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    r = owned(db, PayablesRecommendation, rec_id, business)
    return {"id": r.id, "created_at": r.created_at, **r.payload}


# Financing comparison
@router.get("/financing/compare")
def financing_compare(amount: float = Query(gt=0, le=1e9), needed_by_days: int = Query(7, ge=0, le=90),
                      duration_days: int = Query(30, ge=7, le=180), business: Business = Depends(get_business),
                      db: Session = Depends(get_db)):
    """Compare DEMO financing offers for an amount you choose. Nothing is applied for."""
    d = services.load(db, business)
    today = services.today()
    receipts = payables.expected_receipts(d, today, today + timedelta(days=duration_days))
    options = payables.financing_options(today, amount, today + timedelta(days=needed_by_days), duration_days,
                                         services.financing_offers(db), receipts)
    return {"as_of": today.isoformat(), "currency": business.currency, "amount": amount, "options": options,
            "disclaimer": "DEMO offers for comparison only. These are not real offers or approvals, and the app "
                          "never applies for financing for you."}


# Payment plans
class InstallmentIn(BaseModel):
    due_date: date
    amount: float = Field(gt=0, le=1e10)


class PlanIn(BaseModel):
    bill_id: int
    kind: Literal["extension", "partial", "custom"] = "custom"
    installments: list[InstallmentIn] = Field(min_length=1, max_length=MAX_INSTALLMENTS)
    note: str | None = Field(default=None, max_length=500)
    estimated_fee: float = Field(default=0, ge=0, le=1e9)

    @model_validator(mode="after")
    def _distinct_dates(self):
        dates = [i.due_date for i in self.installments]
        if len(dates) != len(set(dates)):
            raise ValueError("Each installment needs its own date")
        return self


class PlanEdit(BaseModel):
    installments: list[InstallmentIn] = Field(min_length=1, max_length=MAX_INSTALLMENTS)
    note: str | None = Field(default=None, max_length=500)


class ConfirmIn(BaseModel):
    confirm: Literal[True]  # must be sent explicitly


class SupplierResponseIn(BaseModel):
    accepted: bool
    note: str | None = Field(default=None, max_length=500)
    confirm: Literal[True]


class InstallmentPaidIn(BaseModel):
    paid_date: date | None = None
    confirm: Literal[True]


def _check_installments(bill: Bill, items: list[InstallmentIn]) -> None:
    today = services.today()
    total = round(sum(i.amount for i in items), 2)
    if abs(total - round(bill.outstanding, 2)) > CENT:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Installments add up to {total:,.2f} but {bill.outstanding:,.2f} is still owed on this bill")
    for i in items:
        if i.due_date < today:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Installment dates can't be in the past")
        if i.due_date > today + timedelta(days=MAX_DAYS_AHEAD):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Installment dates are too far ahead")


def _plan_out(p: PaymentPlan) -> dict:
    paid = sum(i.amount for i in p.installments if i.status == "paid")
    return {
        "id": p.id, "bill_id": p.bill_id, "supplier": p.bill.supplier.name, "bill_amount": p.bill.amount,
        "bill_outstanding": round(p.bill.outstanding, 2), "kind": p.kind, "status": p.status, "note": p.note,
        "supplier_response_note": p.supplier_response_note, "estimated_fee": p.estimated_fee,
        "created_at": p.created_at, "approved_at": p.approved_at, "responded_at": p.responded_at,
        "paid_so_far": round(paid, 2), "remaining": round(sum(i.amount for i in p.installments if i.status != "paid"), 2),
        "affects_forecast": p.status == "accepted",
        "installments": [{"id": i.id, "due_date": i.due_date, "amount": i.amount, "status": i.status,
                          "paid_date": i.paid_date} for i in p.installments],
    }


def _own_plan(db: Session, plan_id: int, business: Business) -> PaymentPlan:
    return owned(db, PaymentPlan, plan_id, business)


def _set_installments(plan: PaymentPlan, business: Business, items: list[InstallmentIn]) -> None:
    plan.installments.clear()
    for i in sorted(items, key=lambda x: x.due_date):
        plan.installments.append(PaymentPlanInstallment(business_id=business.id, due_date=i.due_date,
                                                        amount=round(i.amount, 2)))


@router.get("/payment-plans")
def list_plans(status_: str | None = Query(None, alias="status"), business: Business = Depends(get_business),
               db: Session = Depends(get_db)):
    stmt = select(PaymentPlan).where(PaymentPlan.business_id == business.id)
    if status_:
        stmt = stmt.where(PaymentPlan.status == status_)
    return [_plan_out(p) for p in db.scalars(stmt.order_by(PaymentPlan.id.desc()))]


@router.post("/payment-plans", status_code=201)
def create_plan(body: PlanIn, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    """Create an editable DRAFT plan. It has no effect on anything until approved and accepted."""
    bill = owned(db, Bill, body.bill_id, business)
    if bill.status == "paid":
        raise HTTPException(status.HTTP_409_CONFLICT, "This bill is already paid")
    _check_installments(bill, body.installments)
    plan = PaymentPlan(business_id=business.id, bill_id=bill.id, kind=body.kind, note=body.note,
                       estimated_fee=body.estimated_fee, status="draft")
    db.add(plan)
    _set_installments(plan, business, body.installments)
    db.commit()
    return _plan_out(plan)


@router.get("/payment-plans/{plan_id}")
def get_plan(plan_id: int, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    return _plan_out(_own_plan(db, plan_id, business))


@router.put("/payment-plans/{plan_id}")
def edit_plan(plan_id: int, body: PlanEdit, business: Business = Depends(get_business),
              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = _own_plan(db, plan_id, business)
    if plan.status not in ("draft", "approved"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"A {plan.status} plan can't be edited")
    _check_installments(plan.bill, body.installments)
    _set_installments(plan, business, body.installments)
    plan.note = body.note if body.note is not None else plan.note
    if plan.status == "approved":  # changed after approval: the owner must approve what it now says
        plan.status, plan.approved_at, plan.approved_by = "draft", None, None
        audit(db, "payment_plan_edited_unapproved", user.email, business_id=business.id, target=f"plan:{plan.id}")
    db.commit()
    return _plan_out(plan)


@router.post("/payment-plans/{plan_id}/approve")
def approve_plan(plan_id: int, body: ConfirmIn, business: Business = Depends(get_business),
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The owner approves PROPOSING this plan to the supplier. Nothing is sent or paid."""
    plan = _own_plan(db, plan_id, business)
    if plan.status != "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Only a draft plan can be approved (this one is {plan.status})")
    _check_installments(plan.bill, [InstallmentIn(due_date=i.due_date, amount=i.amount) for i in plan.installments])
    plan.status, plan.approved_at, plan.approved_by = "approved", utcnow(), user.id
    db.commit()
    audit(db, "payment_plan_approved", user.email, business_id=business.id, user_id=user.id, target=f"plan:{plan.id}")
    return _plan_out(plan)


@router.post("/payment-plans/{plan_id}/supplier-response")
def supplier_response(plan_id: int, body: SupplierResponseIn, business: Business = Depends(get_business),
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Record the supplier's answer. Only an accepted plan changes the cash forecast."""
    plan = _own_plan(db, plan_id, business)
    if plan.status != "approved":
        raise HTTPException(status.HTTP_409_CONFLICT, "Approve the plan before recording the supplier's answer")
    if body.accepted:
        other = db.scalar(select(PaymentPlan).where(PaymentPlan.bill_id == plan.bill_id,
                                                    PaymentPlan.status == "accepted", PaymentPlan.id != plan.id))
        if other:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"Plan #{other.id} is already accepted for this bill; cancel it first")
    plan.status = "accepted" if body.accepted else "rejected"
    plan.supplier_response_note, plan.responded_at = body.note, utcnow()
    db.commit()
    audit(db, f"payment_plan_{plan.status}", user.email, business_id=business.id, user_id=user.id,
          target=f"plan:{plan.id}")
    return _plan_out(plan)


@router.post("/payment-plans/{plan_id}/cancel")
def cancel_plan(plan_id: int, business: Business = Depends(get_business), user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    plan = _own_plan(db, plan_id, business)
    if plan.status in ("cancelled", "completed", "rejected"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"This plan is already {plan.status}")
    plan.status = "cancelled"
    db.commit()
    audit(db, "payment_plan_cancelled", user.email, business_id=business.id, user_id=user.id, target=f"plan:{plan.id}")
    return _plan_out(plan)


@router.post("/payment-plans/installments/{installment_id}/paid")
def installment_paid(installment_id: int, body: InstallmentPaidIn, business: Business = Depends(get_business),
                     user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Record that YOU paid this installment. The app does not move money."""
    inst = owned(db, PaymentPlanInstallment, installment_id, business)
    plan, bill = inst.plan, inst.plan.bill
    if plan.status != "accepted":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only installments of an accepted plan can be recorded as paid")
    if inst.status == "paid":
        raise HTTPException(status.HTTP_409_CONFLICT, "This installment is already recorded as paid")
    when = body.paid_date or services.today()
    inst.status, inst.paid_date = "paid", when
    bill.amount_paid = round((bill.amount_paid or 0) + inst.amount, 2)
    db.add(Transaction(business_id=business.id, date=when, amount=inst.amount, type="expense",
                       category="Bill payment", description=f"Plan #{plan.id} installment to {bill.supplier.name}",
                       source="system"))
    if bill.amount_paid >= bill.amount - CENT:
        bill.status, bill.paid_date = "paid", when
    else:
        bill.status = "partial"
    if all(i.status == "paid" for i in plan.installments):
        plan.status = "completed"
    db.commit()
    audit(db, "payment_plan_installment_paid", user.email, business_id=business.id, user_id=user.id,
          target=f"installment:{inst.id}")
    return _plan_out(plan)


# Negotiation drafts
class DraftIn(BaseModel):
    bill_id: int
    plan_id: int | None = None
    lang: Literal["en", "bn"] = "en"
    polish: bool = True


class DraftEdit(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


def _draft_out(d: NegotiationDraft) -> dict:
    return {"id": d.id, "bill_id": d.bill_id, "plan_id": d.plan_id, "lang": d.lang, "message": d.message,
            "generated_by": d.generated_by, "status": d.status, "created_at": d.created_at,
            "updated_at": d.updated_at, "sent_by_app": False,
            "note": "A draft only. The app never sends it; copy it and send it yourself."}


@router.post("/negotiation-drafts", status_code=201, dependencies=[Depends(ai_limiter)])
def create_draft(body: DraftIn, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    bill = owned(db, Bill, body.bill_id, business)
    plan = owned(db, PaymentPlan, body.plan_id, business) if body.plan_id else None
    if plan and plan.bill_id != bill.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That plan belongs to a different bill")
    if plan:
        installments = [{"due_date": i.due_date.isoformat(), "amount": i.amount} for i in plan.installments]
        kind = "extension" if len(installments) == 1 else "partial"
    else:
        installments = [{"due_date": (bill.due_date + timedelta(days=14)).isoformat(), "amount": bill.outstanding}]
        kind = "extension"
    profile = services.supplier_profiles(db, business, services.load(db, business)).get(bill.supplier_id, {})
    message, by = negotiation.generate(
        kind, body.lang, polish=body.polish, supplier=bill.supplier.name, business=business.name,
        currency=business.currency, amount=bill.outstanding, due_date=bill.due_date.isoformat(),
        installments=installments, on_time_rate=profile.get("on_time_rate"))
    draft = NegotiationDraft(business_id=business.id, bill_id=bill.id, plan_id=plan.id if plan else None,
                             lang=body.lang, message=message, generated_by=f"{by}:{body.lang}")
    db.add(draft)
    db.commit()
    return _draft_out(draft)


@router.get("/negotiation-drafts")
def list_drafts(bill_id: int | None = None, business: Business = Depends(get_business),
                db: Session = Depends(get_db)):
    stmt = select(NegotiationDraft).where(NegotiationDraft.business_id == business.id)
    if bill_id:
        stmt = stmt.where(NegotiationDraft.bill_id == bill_id)
    return [_draft_out(d) for d in db.scalars(stmt.order_by(NegotiationDraft.id.desc()).limit(100))]


@router.put("/negotiation-drafts/{draft_id}")
def edit_draft(draft_id: int, body: DraftEdit, business: Business = Depends(get_business),
               db: Session = Depends(get_db)):
    draft = owned(db, NegotiationDraft, draft_id, business)
    draft.message, draft.updated_at = body.message, utcnow()
    db.commit()
    return _draft_out(draft)


@router.post("/negotiation-drafts/{draft_id}/mark-sent")
def mark_draft_sent(draft_id: int, body: ConfirmIn, business: Business = Depends(get_business),
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The owner says they sent this message themselves. The app does not send anything."""
    draft = owned(db, NegotiationDraft, draft_id, business)
    draft.status = "marked_sent"
    db.commit()
    audit(db, "negotiation_marked_sent", user.email, business_id=business.id, user_id=user.id,
          target=f"draft:{draft.id}")
    return _draft_out(draft)


@router.delete("/negotiation-drafts/{draft_id}", status_code=204)
def delete_draft(draft_id: int, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    db.delete(owned(db, NegotiationDraft, draft_id, business))
    db.commit()


@router.get("/suppliers/{supplier_id}/terms")
def supplier_terms(supplier_id: int, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    owned(db, Supplier, supplier_id, business)
    return services.supplier_profiles(db, business, services.load(db, business))[supplier_id]
