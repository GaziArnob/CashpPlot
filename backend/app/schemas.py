from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# Auth
class SignupIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    phone: str | None = Field(default=None, max_length=30)


class LoginIn(BaseModel):
    # Plain string: a badly formatted email just fails as "wrong email or password".
    email: str = Field(min_length=1, max_length=255)
    password: str = Field(max_length=128)
    code: str | None = Field(default=None, max_length=12)  # two-factor code, when it is switched on


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(ORM):
    id: int
    name: str
    email: str
    role: str = "owner"
    totp_enabled: bool = False


class OnboardingIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    type: str = Field(default="retail", max_length=80)
    started_at: date
    opening_balance: float = Field(default=0, ge=-1e10, le=1e10)
    cash_threshold: float = Field(default=0, ge=0, le=1e10)
    currency: str = Field(default="USD", max_length=8)


class BusinessOut(ORM):
    id: int
    name: str
    type: str
    started_at: date
    opening_balance: float
    cash_threshold: float
    currency: str
    reminder_tone: str
    ai_mode: str = "cloud"


# Transactions
class TransactionIn(BaseModel):
    date: date
    amount: float = Field(gt=0, le=1e10)
    type: Literal["income", "expense"]
    category: str = Field(min_length=1, max_length=60)
    description: str | None = Field(default=None, max_length=255)
    source: Literal["manual", "csv", "scan"] = "manual"


class TransactionOut(ORM):
    id: int
    date: date
    amount: float
    type: str
    category: str
    description: str | None
    source: str


# Customers / suppliers
class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    phone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None


class CustomerOut(ORM):
    id: int
    name: str
    phone: str | None
    email: str | None
    risk_level: str


class SupplierIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    phone: str | None = Field(default=None, max_length=30)


class SupplierOut(ORM):
    id: int
    name: str
    phone: str | None


# Ledger
class InvoiceIn(BaseModel):
    customer_id: int
    amount: float = Field(gt=0, le=1e10)
    issue_date: date
    due_date: date
    note: str | None = Field(default=None, max_length=255)


class InvoiceOut(ORM):
    id: int
    customer_id: int
    amount: float
    amount_paid: float
    issue_date: date
    due_date: date
    paid_date: date | None
    status: str
    note: str | None


class PayIn(BaseModel):
    paid_date: date | None = None


class InvoicePaymentIn(BaseModel):
    amount: float = Field(gt=0, le=1e10)
    paid_date: date | None = None


class BillIn(BaseModel):
    supplier_id: int
    amount: float = Field(gt=0, le=1e10)
    due_date: date
    note: str | None = Field(default=None, max_length=255)


class BillOut(ORM):
    id: int
    supplier_id: int
    amount: float
    amount_paid: float
    due_date: date
    paid_date: date | None
    status: str
    note: str | None


class ReminderOut(ORM):
    id: int
    invoice_id: int
    message: str
    tone: str
    channel: str
    status: str
    generated_by: str
    delivery: str | None = None  # delivered | manual, only on the send response
    delivery_note: str | None = None


class ReminderSendIn(BaseModel):
    message: str | None = Field(default=None, max_length=1000)
    channel: Literal["whatsapp", "email"] = "whatsapp"


# Loans
class LoanIn(BaseModel):
    lender: str = Field(min_length=1, max_length=160)
    principal: float = Field(gt=0, le=1e10)
    rate: float = Field(ge=0, le=100)
    tenure_months: int = Field(ge=1, le=360)
    start_date: date
    installments_paid: int = Field(default=0, ge=0, le=360)  # already paid before today, so they are not counted as late

    @model_validator(mode="after")
    def _paid_within_tenure(self):
        if self.installments_paid > self.tenure_months:
            raise ValueError("Installments paid can't be more than the number of months")
        return self


class WhatIfIn(BaseModel):
    days: int = Field(default=30, ge=7, le=90)
    sales_change_pct: float = Field(default=0, ge=-100, le=500)
    extra_monthly_expense: float = Field(default=0, ge=0, le=1e10)
    loan_amount: float = Field(default=0, ge=0, le=1e10)
    loan_rate: float = Field(default=12, ge=0, le=100)
    loan_tenure_months: int = Field(default=12, ge=1, le=360)


# Goals / notifications / settings
class GoalIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    target_amount: float = Field(gt=0, le=1e10)
    current_amount: float = Field(default=0, ge=0, le=1e10)
    deadline: date | None = None


class GoalOut(ORM):
    id: int
    title: str
    target_amount: float
    current_amount: float
    deadline: date | None


class NotificationOut(ORM):
    id: int
    type: str
    message: str
    is_read: bool


class SettingsIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    type: str | None = Field(default=None, max_length=80)
    cash_threshold: float | None = Field(default=None, ge=0, le=1e10)
    reminder_tone: Literal["auto", "friendly", "firm", "final"] | None = None
    ai_mode: Literal["cloud", "local", "off"] | None = None
    currency: str | None = Field(default=None, max_length=8)


class LenderAccessIn(BaseModel):
    lender_name: str = Field(min_length=1, max_length=160)
    scope: list[Literal["credit_score", "pnl", "cash_forecast"]] = ["credit_score", "pnl"]
    days_valid: int = Field(default=30, ge=1, le=365)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


# Products, sales and stock
class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    sku: str | None = Field(default=None, max_length=60)
    unit_cost: float = Field(ge=0, le=1e9)
    unit_price: float = Field(ge=0, le=1e9)
    stock_qty: float = Field(default=0, ge=0, le=1e9)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    sku: str | None = Field(default=None, max_length=60)
    unit_cost: float | None = Field(default=None, ge=0, le=1e9)
    unit_price: float | None = Field(default=None, ge=0, le=1e9)
    is_active: bool | None = None


class ProductOut(ORM):
    id: int
    name: str
    sku: str | None
    unit_cost: float
    unit_price: float
    stock_qty: float
    is_active: bool


class SaleItemIn(BaseModel):
    product_id: int
    date: date
    qty: float = Field(gt=0, le=1e7)
    unit_price: float | None = Field(default=None, ge=0, le=1e9)  # defaults to the product price
    payment_type: Literal["cash", "credit"] = "cash"
    invoice_id: int | None = None


class SaleItemOut(ORM):
    id: int
    product_id: int
    date: date
    qty: float
    unit_price: float
    unit_cost: float
    payment_type: str
    invoice_id: int | None


class StockMovementIn(BaseModel):
    product_id: int
    date: date
    qty: float = Field(ge=-1e7, le=1e7)  # + stock in, - stock out
    unit_cost: float | None = Field(default=None, ge=0, le=1e9)
    reason: Literal["purchase", "adjustment", "write_off"] = "purchase"
    paid_in_cash: bool = True  # a cash purchase also records the Inventory expense
