from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.security import EncryptedString


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(EncryptedString(512), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    businesses: Mapped[list["Business"]] = relationship(back_populates="owner")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    type: Mapped[str] = mapped_column(String(80), default="retail")
    started_at: Mapped[date] = mapped_column(Date)
    opening_balance: Mapped[float] = mapped_column(Float, default=0.0)
    cash_threshold: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(8), default="BDT")
    reminder_tone: Mapped[str] = mapped_column(String(20), default="auto")  # auto | friendly | firm | final
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    owner: Mapped[User] = relationship(back_populates="businesses")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[float] = mapped_column(Float)
    type: Mapped[str] = mapped_column(String(10))  # income | expense
    category: Mapped[str] = mapped_column(String(60))
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(10), default="manual")  # manual | csv | scan | system
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(EncryptedString(512), nullable=True)
    email: Mapped[str | None] = mapped_column(EncryptedString(512), nullable=True)
    risk_level: Mapped[str] = mapped_column(String(10), default="low")  # low | medium | high
    credit_limit: Mapped[float | None] = mapped_column(Float, nullable=True)  # suggested by collection scoring
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    issue_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    paid_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # date it was fully paid
    amount_paid: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    status: Mapped[str] = mapped_column(String(10), default="unpaid")  # unpaid | partial | paid
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    customer: Mapped[Customer] = relationship()

    @property
    def outstanding(self) -> float:
        return 0.0 if self.status == "paid" else max(0.0, self.amount - (self.amount_paid or 0.0))


class InvoicePayment(Base):
    """One payment against an invoice; several rows mean the customer paid in parts."""

    __tablename__ = "invoice_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date)
    amount: Mapped[float] = mapped_column(Float)


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    message: Mapped[str] = mapped_column(Text)
    tone: Mapped[str] = mapped_column(String(20))
    channel: Mapped[str] = mapped_column(String(20), default="sms")
    status: Mapped[str] = mapped_column(String(10), default="draft")  # draft | sent
    generated_by: Mapped[str] = mapped_column(String(20), default="template")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(EncryptedString(512), nullable=True)
    # Payment terms, used by the supplier negotiation assistant.
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30, server_default="30")
    early_pay_discount_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    early_pay_within_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    late_fee_pct_month: Mapped[float | None] = mapped_column(Float, nullable=True)


class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    paid_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # date it was fully paid
    amount_paid: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    status: Mapped[str] = mapped_column(String(10), default="unpaid")  # unpaid | partial | paid
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    supplier: Mapped[Supplier] = relationship()

    @property
    def outstanding(self) -> float:
        return 0.0 if self.status == "paid" else max(0.0, self.amount - (self.amount_paid or 0.0))


class Loan(Base):
    __tablename__ = "loans"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    lender: Mapped[str] = mapped_column(String(160))
    principal: Mapped[float] = mapped_column(Float)
    rate: Mapped[float] = mapped_column(Float)  # annual interest, percent
    tenure_months: Mapped[int] = mapped_column(Integer)
    start_date: Mapped[date] = mapped_column(Date)
    emi: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(10), default="active")  # active | closed


class Repayment(Base):
    __tablename__ = "repayments"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey("loans.id", ondelete="CASCADE"), index=True)
    due_date: Mapped[date] = mapped_column(Date)
    paid_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[float] = mapped_column(Float)


class CreditScore(Base):
    __tablename__ = "credit_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    score: Mapped[int] = mapped_column(Integer)
    band: Mapped[str] = mapped_column(String(30))
    factors: Mapped[dict] = mapped_column(JSON)
    calculated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class LoanProduct(Base):
    __tablename__ = "loan_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    lender: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(40))  # working_capital | sme_term | microfinance
    min_amount: Mapped[float] = mapped_column(Float)
    max_amount: Mapped[float] = mapped_column(Float)
    rate: Mapped[float] = mapped_column(Float)  # annual percent
    tenure_months: Mapped[int] = mapped_column(Integer)
    min_score: Mapped[int] = mapped_column(Integer)


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    target_amount: Mapped[float] = mapped_column(Float)
    current_amount: Mapped[float] = mapped_column(Float, default=0.0)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(String(500))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(12))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class LenderAccess(Base):
    __tablename__ = "lender_access"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    lender_name: Mapped[str] = mapped_column(String(160))
    scope: Mapped[list] = mapped_column(JSON)  # e.g. ["credit_score", "pnl"]
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RecurringExpense(Base):
    """Fixed monthly payables (salary, rent, utilities) placed on their exact day in the forecast."""

    __tablename__ = "recurring_expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(60))  # matches Transaction.category when paid
    amount: Mapped[float] = mapped_column(Float)
    day_of_month: Mapped[int] = mapped_column(Integer)  # 1-28
    active: Mapped[bool] = mapped_column(Boolean, default=True)


# Product performance

class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    sku: Mapped[str | None] = mapped_column(String(60), nullable=True)
    unit_cost: Mapped[float] = mapped_column(Float)   # current purchase/production cost
    unit_price: Mapped[float] = mapped_column(Float)  # current selling price
    stock_qty: Mapped[float] = mapped_column(Float, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SaleItem(Base):
    """One product line sold. Cash lines roll up into the day's Sales transaction;
    credit lines belong to an invoice."""

    __tablename__ = "sale_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    qty: Mapped[float] = mapped_column(Float)
    unit_price: Mapped[float] = mapped_column(Float)
    unit_cost: Mapped[float] = mapped_column(Float)  # cost at the time of sale, for margin
    payment_type: Mapped[str] = mapped_column(String(10))  # cash | credit
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id", ondelete="SET NULL"),
                                                   nullable=True, index=True)


class StockMovement(Base):
    """Stock in (purchase/production, qty > 0) or out (sale, write-off, qty < 0)."""

    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    qty: Mapped[float] = mapped_column(Float)
    unit_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str] = mapped_column(String(20))  # purchase | sale | adjustment | write_off


# Cash advisor snapshots and actions

class CollectionScore(Base):
    __tablename__ = "collection_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    as_of: Mapped[date] = mapped_column(Date, index=True)
    score: Mapped[float] = mapped_column(Float)  # 0-100
    p_pay_7d: Mapped[float] = mapped_column(Float)
    aging_bucket: Mapped[str] = mapped_column(String(10))  # 0-30 | 31-60 | 61-90 | 90+
    recommended_action: Mapped[str] = mapped_column(String(30))
    credit_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    features: Mapped[dict] = mapped_column(JSON)


class ProductScore(Base):
    __tablename__ = "product_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    as_of: Mapped[date] = mapped_column(Date, index=True)
    product_class: Mapped[str] = mapped_column(String(12))  # star | cash_cow | slow | dead | new
    revenue_30d: Mapped[float] = mapped_column(Float)
    revenue_90d: Mapped[float] = mapped_column(Float)
    growth_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    margin_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    days_of_stock: Mapped[float | None] = mapped_column(Float, nullable=True)
    turnover: Mapped[float | None] = mapped_column(Float, nullable=True)
    cash_conversion_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    recommended_qty_change: Mapped[float] = mapped_column(Float, default=0.0)
    features: Mapped[dict] = mapped_column(JSON)


class Recommendation(Base):
    """One step of the daily action plan."""

    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    plan_date: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(30))  # collect | clear_stock | delay_payable | cut_expense | scale_up | financing
    title: Mapped[str] = mapped_column(String(255))
    target_ref: Mapped[str | None] = mapped_column(String(60), nullable=True)  # e.g. "customer:12"
    cash_impact: Mapped[float] = mapped_column(Float)  # + frees/brings cash, - uses cash
    days_to_impact: Mapped[int] = mapped_column(Integer)
    risk: Mapped[str] = mapped_column(String(10))  # low | medium | high
    reasoning: Mapped[str] = mapped_column(Text)
    rank: Mapped[int] = mapped_column(Integer)
    optional: Mapped[bool] = mapped_column(Boolean, default=False)  # not needed to close the gap
    status: Mapped[str] = mapped_column(String(10), default="open")  # open | done | dismissed
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class ActionLog(Base):
    __tablename__ = "action_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    recommendation_id: Mapped[int] = mapped_column(ForeignKey("recommendations.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(12))  # done | dismissed | reopened
    actual_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# Supplier negotiation assistant

class PaymentPlan(Base):
    """A proposed new payment schedule for one supplier bill.

    draft -> approved (owner approves proposing it) -> accepted / rejected (supplier's answer,
    recorded by the owner). Only an accepted plan changes the cash forecast. Nothing here
    pays a supplier or sends a message by itself.
    """

    __tablename__ = "payment_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("bills.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # extension | partial | custom
    status: Mapped[str] = mapped_column(String(12), default="draft")  # draft|approved|accepted|rejected|cancelled|completed
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    supplier_response_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    estimated_fee: Mapped[float] = mapped_column(Float, default=0.0)  # late fee or lost discount, estimate
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    bill: Mapped[Bill] = relationship()
    installments: Mapped[list["PaymentPlanInstallment"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", order_by="PaymentPlanInstallment.due_date")


class PaymentPlanInstallment(Base):
    __tablename__ = "payment_plan_installments"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("payment_plans.id", ondelete="CASCADE"), index=True)
    due_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(10), default="scheduled")  # scheduled | paid
    paid_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    plan: Mapped[PaymentPlan] = relationship(back_populates="installments")


class NegotiationDraft(Base):
    """An editable message to a supplier. The app never sends it; the owner copies it and may mark it sent."""

    __tablename__ = "negotiation_drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("bills.id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("payment_plans.id", ondelete="SET NULL"), nullable=True)
    lang: Mapped[str] = mapped_column(String(2))  # en | bn
    message: Mapped[str] = mapped_column(Text)
    generated_by: Mapped[str] = mapped_column(String(30), default="template")
    status: Mapped[str] = mapped_column(String(12), default="draft")  # draft | marked_sent
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class FinancingOffer(Base):
    """Catalogue of financing products used for comparisons. Seeded rows are DEMO offers, not real ones."""

    __tablename__ = "financing_offers"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(160))
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(30))  # invoice_financing | short_term_loan | overdraft
    advance_rate_pct: Mapped[float | None] = mapped_column(Float, nullable=True)  # invoice financing: share advanced
    fee_pct: Mapped[float] = mapped_column(Float, default=0.0)            # one-off fee on principal (or invoice face)
    monthly_rate_pct: Mapped[float] = mapped_column(Float, default=0.0)   # interest per 30 days
    min_amount: Mapped[float] = mapped_column(Float, default=0.0)
    max_amount: Mapped[float] = mapped_column(Float)
    max_days: Mapped[int] = mapped_column(Integer)
    lead_days: Mapped[int] = mapped_column(Integer, default=3)  # days until funds could arrive
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)


class PayablesRecommendation(Base):
    """History of supplier-negotiation recommendations, one row per run."""

    __tablename__ = "payables_recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    shortfall: Mapped[float] = mapped_column(Float)
    shortfall_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    headline: Mapped[str] = mapped_column(String(500))
    total_cost: Mapped[float] = mapped_column(Float, default=0.0)
    payload: Mapped[dict] = mapped_column(JSON)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor: Mapped[str] = mapped_column(String(160))
    action: Mapped[str] = mapped_column(String(60))
    target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
