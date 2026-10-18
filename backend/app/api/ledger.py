"""Ledger: receivables (invoices, recovery, reminders) and payables (suppliers, bills)."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import services
from app.ai import templates
from app.ai.text import polish_reminder
from app.db import get_db
from app.deps import ai_limiter, audit, get_business, get_current_user, needs, owned
from app.engines.recovery import tone_for
from app.models import (Bill, Business, Customer, Invoice, InvoicePayment, Reminder, Supplier, Transaction, User,
                        utcnow)
from app.schemas import (BillIn, BillOut, InvoiceIn, InvoiceOut, InvoicePaymentIn, PayIn, ReminderOut, ReminderSendIn,
                         SupplierIn, SupplierOut)

router = APIRouter(tags=["ledger"])

OPEN_STATUSES = ("unpaid", "partial")


# Invoices (receivables)
@router.get("/invoices")
def list_invoices(business: Business = Depends(get_business), db: Session = Depends(get_db),
                  status_: str | None = Query(None, alias="status", pattern="^(paid|unpaid|partial|open|overdue)$"),
                  customer_id: int | None = None):
    stmt = select(Invoice).where(Invoice.business_id == business.id)
    today = services.today()
    if status_ == "overdue":
        stmt = stmt.where(Invoice.status.in_(OPEN_STATUSES), Invoice.due_date < today)
    elif status_ == "open":  # anything still owed, fully or in part
        stmt = stmt.where(Invoice.status.in_(OPEN_STATUSES))
    elif status_:
        stmt = stmt.where(Invoice.status == status_)
    if customer_id:
        stmt = stmt.where(Invoice.customer_id == customer_id)
    out = []
    for inv in db.scalars(stmt.order_by(Invoice.due_date.desc())):
        row = InvoiceOut.model_validate(inv).model_dump()
        row["customer_name"] = inv.customer.name
        row["outstanding"] = round(inv.outstanding)
        row["days_overdue"] = max(0, (today - inv.due_date).days) if inv.status != "paid" else 0
        out.append(row)
    return out


@router.post("/invoices", response_model=InvoiceOut, status_code=201)
def create_invoice(body: InvoiceIn, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    owned(db, Customer, body.customer_id, business)
    if body.due_date < body.issue_date:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Due date is before issue date")
    inv = Invoice(business_id=business.id, **body.model_dump())
    db.add(inv)
    db.commit()
    return inv


@router.patch("/invoices/{invoice_id}/paid", response_model=InvoiceOut)
def mark_invoice_paid(invoice_id: int, body: PayIn | None = None, business: Business = Depends(get_business),
                      db: Session = Depends(get_db)):
    inv = owned(db, Invoice, invoice_id, business)
    if inv.status == "paid":
        raise HTTPException(status.HTTP_409_CONFLICT, "Invoice already paid")
    _record_payment(db, business, inv, inv.outstanding, body.paid_date if body and body.paid_date else None)
    db.commit()
    return inv


def _record_payment(db: Session, business: Business, inv: Invoice, amount: float, when=None) -> None:
    """Apply a (possibly partial) payment: payment row, cash-in transaction, invoice status."""
    when = when or services.today()
    db.add(InvoicePayment(business_id=business.id, invoice_id=inv.id, date=when, amount=amount))
    db.add(Transaction(business_id=business.id, date=when, amount=amount, type="income",
                       category="Invoice payment", description=f"Invoice #{inv.id} from {inv.customer.name}",
                       source="system"))
    inv.amount_paid = (inv.amount_paid or 0.0) + amount
    if inv.amount_paid >= inv.amount - 0.005:
        inv.status, inv.paid_date = "paid", when
    else:
        inv.status = "partial"


@router.post("/invoices/{invoice_id}/payments", response_model=InvoiceOut, status_code=201)
def add_invoice_payment(invoice_id: int, body: InvoicePaymentIn, business: Business = Depends(get_business),
                        db: Session = Depends(get_db)):
    """Record a full or partial payment from the customer."""
    inv = owned(db, Invoice, invoice_id, business)
    if inv.status == "paid":
        raise HTTPException(status.HTTP_409_CONFLICT, "Invoice already paid")
    if body.amount > inv.outstanding + 0.005:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Payment is more than the {round(inv.outstanding):,} still owed")
    _record_payment(db, business, inv, body.amount, body.paid_date)
    db.commit()
    return inv


@router.get("/recovery/priority", dependencies=[Depends(needs("collections"))])
def recovery_priority(business: Business = Depends(get_business), db: Session = Depends(get_db)):
    ranked = services.recovery_priority(db, business)
    return {"currency": business.currency, "total_outstanding": sum(r["outstanding"] for r in ranked),
            "total_overdue": sum(r["overdue_amount"] for r in ranked), "customers": ranked}


@router.post("/recovery/reminder/{invoice_id}", response_model=ReminderOut, status_code=201,
             dependencies=[Depends(ai_limiter), Depends(needs("collections"))])
def draft_reminder(invoice_id: int, polish: bool = True,
                   business: Business = Depends(get_business), db: Session = Depends(get_db)):
    """Draft a reminder for one invoice. It is saved as a draft and never sent automatically."""
    inv = owned(db, Invoice, invoice_id, business)
    if inv.status == "paid":
        raise HTTPException(status.HTTP_409_CONFLICT, "Invoice already paid")
    days = max(0, (services.today() - inv.due_date).days)
    tone = tone_for(days) if business.reminder_tone == "auto" else business.reminder_tone
    text = templates.reminder(tone, customer=inv.customer.name, business=business.name,
                              amount=round(inv.outstanding), currency=business.currency,
                              due_date=inv.due_date.isoformat(), days=days)
    generated_by = "template"
    if polish:
        text, generated_by = polish_reminder(text, tone, inv.customer.name, business.name, business.ai_mode)
    r = Reminder(business_id=business.id, invoice_id=inv.id, message=text, tone=tone, generated_by=generated_by)
    db.add(r)
    db.commit()
    return r


@router.get("/reminders", response_model=list[ReminderOut])
def list_reminders(business: Business = Depends(get_business), db: Session = Depends(get_db)):
    return db.scalars(select(Reminder).where(Reminder.business_id == business.id)
                      .order_by(Reminder.created_at.desc()).limit(100)).all()


@router.post("/reminders/{reminder_id}/send", response_model=ReminderOut)
def send_reminder(reminder_id: int, body: ReminderSendIn, business: Business = Depends(get_business),
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The owner's explicit confirmation. Delivery is mocked; plug in an SMS/WhatsApp gateway here."""
    r = owned(db, Reminder, reminder_id, business)
    if body.message:
        r.message = body.message
    r.channel = body.channel
    r.status = "sent"
    r.sent_at = utcnow()
    db.commit()
    audit(db, "reminder_sent", user.email, business_id=business.id, user_id=user.id, target=f"reminder:{r.id}")
    return r


# Suppliers and bills (payables)
@router.get("/suppliers", response_model=list[SupplierOut])
def list_suppliers(business: Business = Depends(get_business), db: Session = Depends(get_db)):
    return db.scalars(select(Supplier).where(Supplier.business_id == business.id).order_by(Supplier.name)).all()


@router.post("/suppliers", response_model=SupplierOut, status_code=201)
def create_supplier(body: SupplierIn, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    s = Supplier(business_id=business.id, **body.model_dump())
    db.add(s)
    db.commit()
    return s


@router.get("/bills")
def list_bills(business: Business = Depends(get_business), db: Session = Depends(get_db),
               status_: str | None = Query(None, alias="status", pattern="^(paid|unpaid)$")):
    stmt = select(Bill).where(Bill.business_id == business.id)
    if status_:
        stmt = stmt.where(Bill.status == status_)
    out = []
    for b in db.scalars(stmt.order_by(Bill.due_date)):
        row = BillOut.model_validate(b).model_dump()
        row["supplier_name"] = b.supplier.name
        out.append(row)
    return out


@router.post("/bills", response_model=BillOut, status_code=201)
def create_bill(body: BillIn, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    owned(db, Supplier, body.supplier_id, business)
    b = Bill(business_id=business.id, **body.model_dump())
    db.add(b)
    db.commit()
    return b


@router.patch("/bills/{bill_id}/paid", response_model=BillOut)
def mark_bill_paid(bill_id: int, body: PayIn | None = None, business: Business = Depends(get_business),
                   db: Session = Depends(get_db)):
    b = owned(db, Bill, bill_id, business)
    if b.status == "paid":
        raise HTTPException(status.HTTP_409_CONFLICT, "Bill already paid")
    remaining = b.outstanding  # a bill partly paid through a plan only needs the rest
    b.status = "paid"
    b.paid_date = body.paid_date if body and body.paid_date else services.today()
    b.amount_paid = b.amount
    db.add(Transaction(business_id=business.id, date=b.paid_date, amount=remaining, type="expense",
                       category="Bill payment", description=f"Bill #{b.id} to {b.supplier.name}", source="system"))
    db.commit()
    return b
