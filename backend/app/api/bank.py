"""Bank connection (Plaid). Owner-only and Pro. Nothing is imported until the owner presses sync."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import banking
from app.config import get_settings
from app.db import get_db
from app.deps import audit, get_business, needs, owned, require_owner
from app.models import BankConnection, Business, Transaction, User, utcnow

router = APIRouter(prefix="/bank", tags=["bank"], dependencies=[Depends(require_owner), Depends(needs("bank"))])


class ExchangeIn(BaseModel):
    public_token: str = Field(min_length=10, max_length=200)
    institution_name: str = Field(default="Bank", max_length=160)


def _wrap(fn, *a):
    try:
        return fn(*a)
    except banking.BankError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))


@router.get("/status")
def bank_status(business: Business = Depends(get_business), db: Session = Depends(get_db)):
    rows = db.scalars(select(BankConnection).where(BankConnection.business_id == business.id)
                      .order_by(BankConnection.id)).all()
    return {"configured": banking.configured(), "environment": get_settings().plaid_env,
            "connections": [{"id": c.id, "institution": c.institution_name, "connected_at": c.created_at,
                             "last_synced_at": c.last_synced_at} for c in rows]}


@router.post("/link-token")
def link_token(business: Business = Depends(get_business)):
    if not banking.configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Bank connection is not configured")
    return {"link_token": _wrap(banking.create_link_token, business.id)}


@router.post("/exchange", status_code=201)
def exchange(body: ExchangeIn, business: Business = Depends(get_business), owner: User = Depends(require_owner),
             db: Session = Depends(get_db)):
    token, item_id = _wrap(banking.exchange_public_token, body.public_token)
    conn = BankConnection(business_id=business.id, institution_name=body.institution_name, item_id=item_id,
                          access_token=token)
    db.add(conn)
    db.commit()
    audit(db, "bank_connected", owner.email, business_id=business.id, user_id=owner.id, target=body.institution_name)
    return {"id": conn.id, "institution": conn.institution_name}


@router.post("/{conn_id}/sync")
def sync(conn_id: int, business: Business = Depends(get_business), owner: User = Depends(require_owner),
         db: Session = Depends(get_db)):
    conn = owned(db, BankConnection, conn_id, business)
    result = _wrap(banking.sync, conn.access_token, conn.sync_cursor)
    imported = skipped = 0
    for t in result["added"] + result["modified"]:
        row = banking.to_row(t, business.currency)
        if row is None:
            skipped += 1
            continue
        when = date.fromisoformat(row["date"])
        existing = db.scalar(select(Transaction).where(Transaction.business_id == business.id,
                                                       Transaction.external_id == row["external_id"]))
        if existing is not None:  # the bank changed a transaction it sent before
            existing.amount, existing.type, existing.category = row["amount"], row["type"], row["category"]
            existing.description, existing.date = row["description"], when
            continue
        db.add(Transaction(business_id=business.id, source="bank", **{**row, "date": when}))
        db.flush()
        imported += 1
    if result["removed"]:
        db.execute(delete(Transaction).where(Transaction.business_id == business.id,
                                             Transaction.external_id.in_(result["removed"])))
    conn.sync_cursor = result["cursor"]
    conn.last_synced_at = utcnow()
    db.commit()
    audit(db, "bank_synced", owner.email, business_id=business.id, user_id=owner.id, target=f"{conn.id}:{imported}")
    return {"imported": imported, "skipped": skipped, "removed": len(result["removed"])}


@router.delete("/{conn_id}", status_code=204)
def disconnect(conn_id: int, business: Business = Depends(get_business), owner: User = Depends(require_owner),
               db: Session = Depends(get_db)):
    """Stops the connection. Transactions already imported stay in CashPilot."""
    conn = owned(db, BankConnection, conn_id, business)
    name = conn.institution_name
    try:
        banking.remove_item(conn.access_token)
    except banking.BankError:
        pass  # the link is dropped here either way; the bank can also revoke it on its side
    db.delete(conn)
    db.commit()
    audit(db, "bank_disconnected", owner.email, business_id=business.id, user_id=owner.id, target=name)
