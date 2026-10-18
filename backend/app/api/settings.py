"""Settings, consent-based lender access, data export and account deletion."""

import hashlib
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import services
from app.db import Base, bypass_rls, get_db
from app.deps import audit, get_business, get_current_user, needs, owned, require_owner
from app.models import (Bill, Business, ChatMessage, CreditScore, Customer, Goal, Invoice, LenderAccess, Loan,
                        Notification, RefreshToken, Reminder, Repayment, Supplier, Transaction, User, utcnow)
from app.schemas import BusinessOut, LenderAccessIn, SettingsIn

router = APIRouter(tags=["settings"])


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@router.get("/settings", response_model=BusinessOut)
def get_settings_(business: Business = Depends(get_business)):
    return business


@router.put("/settings", response_model=BusinessOut, dependencies=[Depends(require_owner)])
def update_settings(body: SettingsIn, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    changes = body.model_dump(exclude_none=True)
    for k, v in changes.items():
        setattr(business, k, v)
    db.commit()
    audit(db, "settings_changed", business.owner.email, business_id=business.id, target=",".join(changes))
    return business


@router.get("/lender-access", dependencies=[Depends(require_owner), Depends(needs("lender_access"))])
def list_lender_access(business: Business = Depends(get_business), db: Session = Depends(get_db)):
    rows = db.scalars(select(LenderAccess).where(LenderAccess.business_id == business.id)
                      .order_by(LenderAccess.granted_at.desc())).all()
    now = utcnow()
    return [{"id": r.id, "lender_name": r.lender_name, "scope": r.scope, "granted_at": r.granted_at,
             "expires_at": r.expires_at, "active": r.revoked_at is None and r.expires_at > now} for r in rows]


@router.post("/lender-access", status_code=201, dependencies=[Depends(require_owner), Depends(needs("lender_access"))])
def grant_lender_access(body: LenderAccessIn, business: Business = Depends(get_business),
                        db: Session = Depends(get_db)):
    """The owner grants a lender scoped, expiring, read-only access. The token is shown only once."""
    token = secrets.token_urlsafe(32)
    row = LenderAccess(business_id=business.id, lender_name=body.lender_name, scope=list(body.scope),
                       token_hash=_hash(token), expires_at=utcnow() + timedelta(days=body.days_valid))
    db.add(row)
    db.commit()
    audit(db, "lender_access_granted", business.owner.email, business_id=business.id,
          target=f"{body.lender_name}:{','.join(body.scope)}")
    return {"id": row.id, "token": token, "expires_at": row.expires_at, "scope": row.scope,
            "note": "Share this token with the lender. It will not be shown again."}


@router.delete("/lender-access/{access_id}", status_code=204, dependencies=[Depends(require_owner)])
def revoke_lender_access(access_id: int, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    row = owned(db, LenderAccess, access_id, business)
    row.revoked_at = utcnow()
    db.commit()
    audit(db, "lender_access_revoked", business.owner.email, business_id=business.id, target=row.lender_name)


@router.get("/lender/view")
def lender_view(x_lender_token: str = Header(..., max_length=128), db: Session = Depends(get_db)):
    """What a lender sees with a valid token: only the scopes the owner granted."""
    bypass_rls(db)  # the token, not a signed-in business, decides what is visible
    row = db.scalar(select(LenderAccess).where(LenderAccess.token_hash == _hash(x_lender_token)))
    if row is None or row.revoked_at is not None or row.expires_at <= utcnow():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access token invalid, expired or revoked")
    business = db.get(Business, row.business_id)
    out = {"business": business.name, "lender": row.lender_name, "scope": row.scope,
           "expires_at": row.expires_at}
    if "credit_score" in row.scope:
        c = services.credit_score(db, business, store=False)
        out["credit_score"] = {k: c[k] for k in ("score", "band", "factors", "reasons_positive", "reasons_negative")}
    if "pnl" in row.scope:
        t = services.today()
        out["pnl_last_month"] = services.pnl(db, business, t.year if t.month > 1 else t.year - 1,
                                             t.month - 1 if t.month > 1 else 12)
    if "cash_forecast" in row.scope:
        fc = services.cash_forecast(db, business, 30)
        out["cash_forecast"] = {k: fc[k] for k in ("start_balance", "min_balance", "first_shortage")}
    audit(db, "lender_view", row.lender_name, business_id=business.id, target=",".join(row.scope))
    return out


@router.get("/settings/export", dependencies=[Depends(require_owner)])
def export_data(business: Business = Depends(get_business), db: Session = Depends(get_db)):
    """Everything stored for this business, as JSON (the user's right to their data)."""
    def rows(model, *fields):
        return [{f: getattr(r, f) for f in fields}
                for r in db.scalars(select(model).where(model.business_id == business.id))]

    audit(db, "data_export", business.owner.email, business_id=business.id)
    return {
        "business": BusinessOut.model_validate(business).model_dump(),
        "transactions": rows(Transaction, "date", "amount", "type", "category", "description", "source"),
        "customers": rows(Customer, "id", "name", "phone", "email"),
        "invoices": rows(Invoice, "id", "customer_id", "amount", "issue_date", "due_date", "paid_date", "status"),
        "suppliers": rows(Supplier, "id", "name", "phone"),
        "bills": rows(Bill, "id", "supplier_id", "amount", "due_date", "paid_date", "status"),
        "loans": rows(Loan, "id", "lender", "principal", "rate", "tenure_months", "start_date", "status"),
        "goals": rows(Goal, "title", "target_amount", "current_amount", "deadline"),
    }


@router.delete("/settings/account", status_code=204, dependencies=[Depends(require_owner)])
def delete_account(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Deletes the owner, their staff, their business and every record that belongs to it."""
    for b in db.scalars(select(Business).where(Business.user_id == user.id)).all():
        # Children before parents, for every table that carries a business_id.
        for table in reversed(Base.metadata.sorted_tables):
            if "business_id" in table.c and table.name != "businesses":
                db.execute(table.delete().where(table.c.business_id == b.id))
        for staff in db.scalars(select(User).where(User.employer_business_id == b.id)).all():
            db.execute(delete(RefreshToken).where(RefreshToken.user_id == staff.id))
            db.delete(staff)
        db.delete(b)
    db.execute(delete(RefreshToken).where(RefreshToken.user_id == user.id))
    audit(db, "account_deleted", user.email, user_id=user.id)
    db.delete(user)
    db.commit()
    return Response(status_code=204)
