"""Lender introductions: the owner asks to be introduced to a lender for a loan product, with consent.

This records the request and what the owner agreed to share, so partner lenders can be counted per lead.
It does not contact the lender and it is not a loan application: the lender decides on its own, and the
owner records the outcome here.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import services
from app.db import get_db
from app.deps import audit, get_business, needs, owned, require_owner
from app.models import Business, LenderReferral, LoanProduct, User, utcnow

router = APIRouter(prefix="/referrals", tags=["referrals"], dependencies=[Depends(require_owner), Depends(needs("referrals"))])

OPEN = ("submitted", "contacted")
NEXT = {"submitted": {"contacted", "declined", "withdrawn"}, "contacted": {"funded", "declined", "withdrawn"}}
NOTE = "An introduction request only. The lender decides; this is not a loan application or an approval."


class ReferralIn(BaseModel):
    loan_product_id: int
    amount: float = Field(gt=0, le=1e10)
    share: list[Literal["credit_score", "pnl", "cash_forecast"]] = Field(min_length=1, max_length=3)
    note: str | None = Field(default=None, max_length=500)
    confirm: Literal[True]  # the owner's explicit consent to share


class StatusIn(BaseModel):
    status: Literal["contacted", "funded", "declined", "withdrawn"]
    note: str | None = Field(default=None, max_length=500)


def _out(r: LenderReferral) -> dict:
    return {"id": r.id, "lender_name": r.lender_name, "product_name": r.product_name,
            "requested_amount": r.requested_amount, "score_snapshot": r.score_snapshot, "band_snapshot": r.band_snapshot,
            "shared_fields": r.shared_fields, "status": r.status, "note": r.note, "consent_at": r.consent_at,
            "updated_at": r.updated_at}


@router.get("")
def list_referrals(business: Business = Depends(get_business), db: Session = Depends(get_db)):
    rows = db.scalars(select(LenderReferral).where(LenderReferral.business_id == business.id)
                      .order_by(LenderReferral.id.desc())).all()
    by_status: dict[str, int] = {}
    for r in rows:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    return {"items": [_out(r) for r in rows], "summary": {"total": len(rows), "by_status": by_status},
            "disclaimer": NOTE}


@router.post("", status_code=201)
def create_referral(body: ReferralIn, business: Business = Depends(get_business), owner: User = Depends(require_owner),
                    db: Session = Depends(get_db)):
    product = db.get(LoanProduct, body.loan_product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Loan product not found")
    if not product.min_amount <= body.amount <= product.max_amount:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"This product lends between {product.min_amount:,.0f} and {product.max_amount:,.0f}")
    credit = services.credit_score(db, business, store=False)
    if credit["score"] < product.min_score:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Your credit score ({credit['score']}) is below this product's minimum ({product.min_score})")
    existing = db.scalar(select(LenderReferral).where(
        LenderReferral.business_id == business.id, LenderReferral.loan_product_id == product.id,
        LenderReferral.status.in_(OPEN)))
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "You already have an open request for this product")
    r = LenderReferral(business_id=business.id, loan_product_id=product.id, lender_name=product.lender,
                       product_name=product.name, requested_amount=body.amount, score_snapshot=credit["score"],
                       band_snapshot=credit["band"], shared_fields=sorted(set(body.share)), note=body.note)
    db.add(r)
    db.commit()
    audit(db, "referral_requested", owner.email, business_id=business.id, user_id=owner.id,
          target=f"{product.lender}:{product.name}:{','.join(r.shared_fields)}")
    return {**_out(r), "disclaimer": NOTE}


@router.post("/{referral_id}/status")
def update_status(referral_id: int, body: StatusIn, business: Business = Depends(get_business),
                  owner: User = Depends(require_owner), db: Session = Depends(get_db)):
    """Record what happened: the lender got in touch, funded, declined, or you withdrew."""
    r = owned(db, LenderReferral, referral_id, business)
    if body.status not in NEXT.get(r.status, set()):
        raise HTTPException(status.HTTP_409_CONFLICT, f"A {r.status} request can't be marked {body.status}")
    r.status, r.updated_at = body.status, utcnow()
    if body.note:
        r.note = body.note
    db.commit()
    audit(db, f"referral_{body.status}", owner.email, business_id=business.id, user_id=owner.id, target=f"referral:{r.id}")
    return _out(r)
