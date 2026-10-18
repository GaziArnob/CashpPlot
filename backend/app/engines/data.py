"""Loads one business's data into plain objects the engines work on.

Engines never touch the database directly, which keeps them deterministic and easy to test.
"""

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (Bill, Business, Customer, Invoice, InvoicePayment, Loan, PaymentPlan, Product,
                        RecurringExpense, Repayment, SaleItem, Transaction)

# Categories that come from known events. The forecast baseline excludes them,
# because the same money is added back as a scheduled inflow or outflow.
SCHEDULED_INCOME = {"Invoice payment"}
SCHEDULED_EXPENSE = {"Bill payment", "Loan repayment"}
# Personal withdrawals by the owner. They reduce cash (so the forecast keeps them), but credit
# and loan capacity judge the business's own cash flow, before drawings.
OWNER_DRAWINGS = {"Owner drawings"}


@dataclass
class Txn:
    date: date
    amount: float
    type: str
    category: str


@dataclass
class Inv:
    id: int
    customer_id: int
    amount: float
    issue_date: date
    due_date: date
    paid_date: date | None  # set only when fully paid
    amount_paid: float = 0.0

    @property
    def outstanding(self) -> float:
        return 0.0 if self.paid_date else max(0.0, self.amount - self.amount_paid)


@dataclass
class BillRow:
    id: int
    supplier_id: int
    supplier_name: str
    amount: float
    due_date: date
    paid_date: date | None
    amount_paid: float = 0.0
    # Unpaid installments of a plan the supplier accepted: (date, amount). When present they replace
    # the single due-date payment, so the bill is never counted twice.
    schedule: list[tuple[date, float]] = field(default_factory=list)
    plan_id: int | None = None

    @property
    def outstanding(self) -> float:
        return 0.0 if self.paid_date else max(0.0, self.amount - self.amount_paid)


@dataclass
class LoanRow:
    id: int
    principal: float
    rate: float
    tenure_months: int
    start_date: date
    emi: float
    status: str


@dataclass
class RepaymentRow:
    loan_id: int
    due_date: date
    paid_date: date | None
    amount: float


@dataclass
class PaymentRow:
    invoice_id: int
    date: date
    amount: float


@dataclass
class ProductRow:
    id: int
    name: str
    unit_cost: float
    unit_price: float
    stock_qty: float
    created: date
    active: bool


@dataclass
class SaleRow:
    product_id: int
    date: date
    qty: float
    unit_price: float
    unit_cost: float
    payment_type: str  # cash | credit
    invoice_id: int | None


@dataclass
class RecurringRow:
    name: str
    category: str
    amount: float
    day_of_month: int


@dataclass
class BusinessData:
    business_id: int
    started_at: date
    opening_balance: float
    cash_threshold: float
    transactions: list[Txn] = field(default_factory=list)
    invoices: list[Inv] = field(default_factory=list)
    customers: dict[int, str] = field(default_factory=dict)
    bills: list[BillRow] = field(default_factory=list)
    loans: list[LoanRow] = field(default_factory=list)
    repayments: list[RepaymentRow] = field(default_factory=list)
    recurring: list[RecurringRow] = field(default_factory=list)  # active fixed monthly payables
    payments: list[PaymentRow] = field(default_factory=list)  # every invoice payment, incl. partial ones
    customer_since: dict[int, date] = field(default_factory=dict)
    products: list[ProductRow] = field(default_factory=list)
    sales: list[SaleRow] = field(default_factory=list)

    def balance_on(self, day: date) -> float:
        bal = self.opening_balance
        for t in self.transactions:
            if t.date <= day:
                bal += t.amount if t.type == "income" else -t.amount
        return bal


def load(db: Session, business: Business) -> BusinessData:
    bid = business.id
    data = BusinessData(
        business_id=bid,
        started_at=business.started_at,
        opening_balance=business.opening_balance,
        cash_threshold=business.cash_threshold,
    )
    for t in db.scalars(select(Transaction).where(Transaction.business_id == bid)):
        data.transactions.append(Txn(t.date, t.amount, t.type, t.category))
    for c in db.scalars(select(Customer).where(Customer.business_id == bid)):
        data.customers[c.id] = c.name
        data.customer_since[c.id] = c.created_at.date()
    for i in db.scalars(select(Invoice).where(Invoice.business_id == bid)):
        data.invoices.append(Inv(i.id, i.customer_id, i.amount, i.issue_date, i.due_date, i.paid_date,
                                 i.amount_paid or 0.0))
    for b in db.scalars(select(Bill).where(Bill.business_id == bid)):
        data.bills.append(BillRow(b.id, b.supplier_id, b.supplier.name, b.amount, b.due_date, b.paid_date,
                                  b.amount_paid or 0.0))
    accepted = {}
    for plan in db.scalars(select(PaymentPlan).where(PaymentPlan.business_id == bid,
                                                     PaymentPlan.status == "accepted")):
        accepted[plan.bill_id] = plan
    for row in data.bills:
        plan = accepted.get(row.id)
        if plan and not row.paid_date:
            row.plan_id = plan.id
            row.schedule = [(i.due_date, i.amount) for i in plan.installments if i.status != "paid"]
    for loan in db.scalars(select(Loan).where(Loan.business_id == bid)):
        data.loans.append(
            LoanRow(loan.id, loan.principal, loan.rate, loan.tenure_months, loan.start_date, loan.emi, loan.status)
        )
    for r in db.scalars(select(Repayment).where(Repayment.business_id == bid)):
        data.repayments.append(RepaymentRow(r.loan_id, r.due_date, r.paid_date, r.amount))
    for p in db.scalars(select(InvoicePayment).where(InvoicePayment.business_id == bid)):
        data.payments.append(PaymentRow(p.invoice_id, p.date, p.amount))
    for p in db.scalars(select(Product).where(Product.business_id == bid)):
        data.products.append(ProductRow(p.id, p.name, p.unit_cost, p.unit_price, p.stock_qty,
                                        p.created_at.date(), p.is_active))
    for si in db.scalars(select(SaleItem).where(SaleItem.business_id == bid)):
        data.sales.append(SaleRow(si.product_id, si.date, si.qty, si.unit_price, si.unit_cost, si.payment_type,
                                  si.invoice_id))
    for e in db.scalars(select(RecurringExpense).where(RecurringExpense.business_id == bid,
                                                       RecurringExpense.active.is_(True))):
        data.recurring.append(RecurringRow(e.name, e.category, e.amount, e.day_of_month))
    return data


def month_key(d: date) -> tuple[int, int]:
    return (d.year, d.month)


def last_full_months(today: date, n: int) -> list[tuple[int, int]]:
    """The n calendar months before the current one, oldest first."""
    y, m = today.year, today.month
    out = []
    for _ in range(n):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append((y, m))
    return list(reversed(out))


def monthly_totals(data: BusinessData, months: list[tuple[int, int]],
                   exclude: set[str] = frozenset()) -> tuple[list[float], list[float]]:
    inc = {k: 0.0 for k in months}
    exp = {k: 0.0 for k in months}
    for t in data.transactions:
        k = month_key(t.date)
        if k in inc and t.category not in exclude:
            if t.type == "income":
                inc[k] += t.amount
            else:
                exp[k] += t.amount
    return [inc[k] for k in months], [exp[k] for k in months]


def active_months(data: BusinessData, months: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Drop months before the business had any records."""
    if not data.transactions:
        return []
    first = month_key(min(t.date for t in data.transactions))
    return [k for k in months if k >= first]
