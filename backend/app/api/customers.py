from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import services
from app.db import get_db
from app.deps import get_business, owned
from app.engines.recovery import late_share, risk_level
from app.models import Business, Customer, Invoice
from app.schemas import CustomerIn, CustomerOut, CustomerUpdate, InvoiceOut

router = APIRouter(prefix="/customers", tags=["customers"])


def _summary(c: Customer, invoices: list[Invoice], today) -> dict:
    unpaid = [i for i in invoices if i.status != "paid"]
    max_overdue = max((max(0, (today - i.due_date).days) for i in unpaid), default=0)
    return {
        **CustomerOut.model_validate(c).model_dump(),
        "outstanding": round(sum(i.outstanding for i in unpaid)),
        "overdue": round(sum(i.outstanding for i in unpaid if i.due_date < today)),
        "max_days_overdue": max_overdue,
        "invoice_count": len(invoices),
        "credit_limit": c.credit_limit,
    }


@router.get("")
def list_customers(business: Business = Depends(get_business), db: Session = Depends(get_db)):
    today = services.today()
    invoices: dict[int, list[Invoice]] = {}
    for inv in db.scalars(select(Invoice).where(Invoice.business_id == business.id)):
        invoices.setdefault(inv.customer_id, []).append(inv)
    customers = db.scalars(select(Customer).where(Customer.business_id == business.id).order_by(Customer.name))
    rows = [_summary(c, invoices.get(c.id, []), today) for c in customers]
    rows.sort(key=lambda r: -r["outstanding"])
    return rows


@router.post("", response_model=CustomerOut, status_code=201)
def create_customer(body: CustomerIn, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    c = Customer(business_id=business.id, **body.model_dump())
    db.add(c)
    db.commit()
    return c


@router.put("/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: int, body: CustomerUpdate, business: Business = Depends(get_business),
                    db: Session = Depends(get_db)):
    """Change a customer's name, phone or email. A field left out stays as it is; null or an empty string clears
    the phone or email (the name cannot be cleared)."""
    c = owned(db, Customer, customer_id, business)
    sent = body.model_fields_set
    if "name" in sent:
        if body.name is None or not body.name.strip():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A customer needs a name")
        c.name = body.name.strip()
    if "phone" in sent:
        c.phone = (body.phone or "").strip() or None
    if "email" in sent:
        c.email = body.email or None
    db.commit()
    return c


@router.get("/{customer_id}")
def customer_profile(customer_id: int, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    c = owned(db, Customer, customer_id, business)
    today = services.today()
    invoices = list(db.scalars(select(Invoice).where(Invoice.customer_id == c.id).order_by(Invoice.due_date.desc())))
    data = services.load(db, business)
    late = late_share(data, c.id)
    summary = _summary(c, invoices, today)
    paid = [i for i in invoices if i.paid_date]
    avg_delay = (sum((i.paid_date - i.due_date).days for i in paid) / len(paid)) if paid else None
    level = risk_level(late, summary["max_days_overdue"])
    if c.risk_level != level:
        c.risk_level = level
        db.commit()
    summary["risk_level"] = level
    return {
        **summary,
        "late_payment_share": round(late, 2),
        "average_days_late": round(avg_delay, 1) if avg_delay is not None else None,
        "total_paid": round(sum(i.amount for i in paid)),
        "invoices": [InvoiceOut.model_validate(i) for i in invoices],
    }
