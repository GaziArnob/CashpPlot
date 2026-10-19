"""What raises a notification. Each rule looks at one kind of thing and calls notify.create with a key for that thing,
so it is raised once per cooldown (notify.py). A rule that fails is logged and skipped; it never breaks the others
or the page that triggered the check.

Thresholds are the constants below, in one place.
"""

import calendar
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import notify, plans
from app.ai.templates import day, money
from app.engines.data import OWNER_DRAWINGS, BusinessData
from app.models import (BankConnection, Bill, Business, CreditScore, Goal, Invoice, LenderReferral, Loan,
                        PaymentPlan, PaymentPlanInstallment, Repayment, utcnow)

log = logging.getLogger(__name__)

DUE_SOON_DAYS = 3  # invoices, bills, loan and plan payments
LATE_INVOICE_LIMIT = 10  # at most this many "late invoice" alerts per check, biggest first
LOW_STOCK_DAYS = 5  # days of stock left at the recent selling rate
CREDIT_DROP_POINTS = 20
SPENDING_SPIKE = 1.4  # this month's pace vs the usual, as a ratio
SALES_DROP = 0.6  # the last 14 days vs the 14 before
REFERRAL_STALE_DAYS = 14
GOAL_SOON_DAYS = 14
BANK_STALE_DAYS = 7


@dataclass
class Context:
    today: date
    fc: dict
    ranked: list[dict]
    data: BusinessData
    product_scores: Callable[[], dict]


def _money(business: Business, n: float) -> str:
    return money(round(n), business.currency)


# ---- cash -------------------------------------------------------------------------------------------------

def cash_shortage(db, business, c: Context):
    s = c.fc["first_shortage"]
    if s:
        notify.create(db, business, "cash_shortage",
                      f"Cash may fall {_money(business, s['gap'])} below your safety level on {day(s['date'])}.",
                      key=f"shortage:{s['date']}", link="/cashflow", cooldown_days=3)


def cash_low_now(db, business, c: Context):
    balance, threshold = c.fc["start_balance"], business.cash_threshold
    if threshold > 0 and balance < threshold:
        notify.create(db, business, "cash_low",
                      f"Your cash ({_money(business, balance)}) is already below your safety level of {_money(business, threshold)}.",
                      key="cash_low", link="/cashflow", cooldown_days=2)


# ---- money owed to you ----------------------------------------------------------------------------------

def customers_far_behind(db, business, c: Context):
    for r in c.ranked:
        if r["max_days_overdue"] > 30:
            notify.create(db, business, "overdue",
                          f"{r['customer_name']} is {r['max_days_overdue']} days overdue on {_money(business, r['outstanding'])}.",
                          key=f"overdue:{r['customer_id']}", link="/ledger", cooldown_days=7)


def invoices_due_soon(db, business, c: Context):
    soon = c.today + timedelta(days=DUE_SOON_DAYS)
    for inv in db.scalars(select(Invoice).where(Invoice.business_id == business.id, Invoice.status != "paid",
                                                Invoice.due_date >= c.today, Invoice.due_date <= soon)):
        notify.create(db, business, "invoice_due",
                      f"{inv.customer.name} owes {_money(business, inv.outstanding)}, due {day(inv.due_date.isoformat())}.",
                      key=f"invoice:{inv.id}", link="/ledger", cooldown_days=5)


def invoices_late(db, business, c: Context):
    """Late by 1 to 30 days. Beyond 30 days the customer-level alert above takes over."""
    rows = db.scalars(select(Invoice).where(Invoice.business_id == business.id, Invoice.status != "paid",
                                            Invoice.due_date < c.today,
                                            Invoice.due_date >= c.today - timedelta(days=30))).all()
    rows.sort(key=lambda i: -i.outstanding)
    for inv in rows[:LATE_INVOICE_LIMIT]:
        notify.create(db, business, "invoice_late",
                      f"Invoice #{inv.id} from {inv.customer.name} is {(c.today - inv.due_date).days} days late "
                      f"({_money(business, inv.outstanding)}).",
                      key=f"invoice_late:{inv.id}", link="/ledger", cooldown_days=7)


# ---- money you owe ----------------------------------------------------------------------------------------

def bills_due_soon(db, business, c: Context):
    soon = c.today + timedelta(days=DUE_SOON_DAYS)
    for b in db.scalars(select(Bill).where(Bill.business_id == business.id, Bill.status != "paid", Bill.due_date <= soon)):
        late = b.due_date < c.today
        notify.create(db, business, "bill_due",
                      f"Bill of {_money(business, b.outstanding)} to {b.supplier.name} {'was due' if late else 'is due'} "
                      f"{day(b.due_date.isoformat())}.",
                      key=f"bill:{b.id}", link="/payables", cooldown_days=3, severity="critical" if late else None)


def supplier_plan_payments(db, business, c: Context):
    """Instalments of a plan the supplier accepted: the agreed dates must be kept."""
    soon = c.today + timedelta(days=DUE_SOON_DAYS)
    rows = db.execute(select(PaymentPlanInstallment, PaymentPlan).join(PaymentPlan, PaymentPlan.id == PaymentPlanInstallment.plan_id)
                      .where(PaymentPlanInstallment.business_id == business.id, PaymentPlanInstallment.status == "scheduled",
                             PaymentPlan.status == "accepted", PaymentPlanInstallment.due_date <= soon)).all()
    for inst, plan in rows:
        late = inst.due_date < c.today
        notify.create(db, business, "plan_due",
                      f"Agreed payment of {_money(business, inst.amount)} to {plan.bill.supplier.name} "
                      f"{'was due' if late else 'is due'} {day(inst.due_date.isoformat())}.",
                      key=f"plan:{inst.id}", link="/payables", cooldown_days=3, severity="critical" if late else None)


def loan_installments(db, business, c: Context):
    soon = c.today + timedelta(days=DUE_SOON_DAYS)
    for rep in db.scalars(select(Repayment).where(Repayment.business_id == business.id, Repayment.paid_date.is_(None),
                                                  Repayment.due_date <= soon)):
        loan = db.get(Loan, rep.loan_id)
        if loan is None or loan.status != "active":
            continue
        late = rep.due_date < c.today
        notify.create(db, business, "loan_due",
                      f"Loan installment of {_money(business, rep.amount)} to {loan.lender} "
                      f"{'was due' if late else 'is due'} {day(rep.due_date.isoformat())}.",
                      key=f"loan:{rep.id}", link="/loan", cooldown_days=3, severity="critical" if late else None)


# ---- how the business is doing ----------------------------------------------------------------------------

def low_stock(db, business, c: Context):
    if not plans.can_use(business, "products"):
        return
    for p in c.product_scores()["products"]:
        if not p["units_30d"]:
            continue  # not selling: running out is not urgent
        if p["stock_qty"] <= 0:
            msg, sev = f"{p['name']} is out of stock and was selling.", "critical"
        elif p["days_of_stock"] is not None and p["days_of_stock"] <= LOW_STOCK_DAYS:
            msg, sev = f"{p['name']} will run out in about {max(1, round(p['days_of_stock']))} days at the recent selling rate.", None
        else:
            continue
        notify.create(db, business, "low_stock", msg, key=f"stock:{p['product_id']}", link="/products",
                      cooldown_days=5, severity=sev)


def credit_score_drop(db, business, c: Context):
    if not plans.can_use(business, "credit"):
        return
    rows = db.scalars(select(CreditScore).where(CreditScore.business_id == business.id)
                      .order_by(CreditScore.calculated_at.desc(), CreditScore.id.desc()).limit(2)).all()
    if len(rows) == 2 and rows[0].score <= rows[1].score - CREDIT_DROP_POINTS:
        notify.create(db, business, "credit_drop",
                      f"Your credit score fell from {rows[1].score} to {rows[0].score}. See what changed.",
                      key=f"credit_drop:{rows[0].id}", link="/credit-score", cooldown_days=14)


def _month_totals(data: BusinessData, kind: str, today: date, months: int) -> list[float]:
    """Totals for each of the last `months` complete months, oldest first. Owner drawings are not spending."""
    out = []
    y, m = today.year, today.month
    for _ in range(months):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append(sum(t.amount for t in data.transactions
                       if t.type == kind and t.date.year == y and t.date.month == m and t.category not in OWNER_DRAWINGS))
    return list(reversed(out))


def spending_spike(db, business, c: Context):
    if c.today.day < 10:
        return  # too early in the month to judge the pace
    past = [x for x in _month_totals(c.data, "expense", c.today, 3) if x > 0]
    if len(past) < 2:
        return
    first = c.today.replace(day=1)
    spent = sum(t.amount for t in c.data.transactions if t.type == "expense" and t.date >= first
                and t.category not in OWNER_DRAWINGS)
    usual = sum(past) / len(past) * c.today.day / calendar.monthrange(c.today.year, c.today.month)[1]
    if usual > 0 and spent > SPENDING_SPIKE * usual:
        notify.create(db, business, "spending_spike",
                      f"Spending this month ({_money(business, spent)}) is running {round((spent / usual - 1) * 100)}% above your usual pace.",
                      key=f"spend:{c.today:%Y-%m}", link="/reports", cooldown_days=14)


def sales_drop(db, business, c: Context):
    if (c.today - business.started_at).days < 28:
        return
    recent_from, prior_from = c.today - timedelta(days=14), c.today - timedelta(days=28)
    recent = sum(t.amount for t in c.data.transactions if t.type == "income" and recent_from < t.date <= c.today)
    prior = sum(t.amount for t in c.data.transactions if t.type == "income" and prior_from < t.date <= recent_from)
    if prior > 0 and recent < SALES_DROP * prior:
        notify.create(db, business, "sales_drop",
                      f"Sales over the last 14 days ({_money(business, recent)}) are {round((1 - recent / prior) * 100)}% "
                      f"lower than the 14 days before ({_money(business, prior)}).",
                      key=f"sales:{c.today.isocalendar().year}-{c.today.isocalendar().week // 2}", link="/reports", cooldown_days=10)


# ---- follow-ups -------------------------------------------------------------------------------------------

def stale_referrals(db, business, c: Context):
    cutoff = utcnow() - timedelta(days=REFERRAL_STALE_DAYS)
    for r in db.scalars(select(LenderReferral).where(LenderReferral.business_id == business.id,
                                                     LenderReferral.status.in_(("submitted", "contacted")),
                                                     LenderReferral.updated_at < cutoff)):
        days = (utcnow() - r.updated_at).days
        notify.create(db, business, "referral",
                      f"Your introduction request for {r.product_name} ({r.lender_name}) has had no update for {days} days. "
                      "Record the outcome or withdraw it.",
                      key=f"referral:{r.id}", link="/loan", cooldown_days=REFERRAL_STALE_DAYS)


def goals_soon(db, business, c: Context):
    soon = c.today + timedelta(days=GOAL_SOON_DAYS)
    for g in db.scalars(select(Goal).where(Goal.business_id == business.id, Goal.deadline.is_not(None),
                                           Goal.deadline >= c.today, Goal.deadline <= soon)):
        if g.current_amount < g.target_amount:
            notify.create(db, business, "goal",
                          f"Goal “{g.title}” is due {day(g.deadline.isoformat())}: {_money(business, g.current_amount)} of "
                          f"{_money(business, g.target_amount)} saved.",
                          key=f"goal:{g.id}", link="/reports", cooldown_days=7)


def stale_bank(db, business, c: Context):
    cutoff = utcnow() - timedelta(days=BANK_STALE_DAYS)
    for b in db.scalars(select(BankConnection).where(BankConnection.business_id == business.id)):
        last: datetime = b.last_synced_at or b.created_at
        if last < cutoff:
            notify.create(db, business, "bank",
                          f"Your {b.institution_name} connection has not been synced for {(utcnow() - last).days} days. "
                          "Sync it to keep your records current.",
                          key=f"bank:{b.id}", link="/transactions", cooldown_days=BANK_STALE_DAYS)


def plan_and_trial(db, business, c: Context):
    plan = plans.describe(business)
    if plan["trial"] and plan["days_left"] is not None and plan["days_left"] <= 3:
        notify.create(db, business, "trial",
                      f"Your Pro trial ends in {plan['days_left']} day{'s' if plan['days_left'] != 1 else ''}. "
                      "Choose a plan in Settings to keep every feature.",
                      key="trial_ending", link="/settings#plan", cooldown_days=2)
    elif plan["trial_ended"]:
        notify.create(db, business, "trial", "Your Pro trial has ended, so you are on the Free plan. "
                      "Choose Pro in Settings to get everything back.", key="trial_ended", link="/settings#plan",
                      cooldown_days=30)


RULES = [cash_shortage, cash_low_now, customers_far_behind, invoices_due_soon, invoices_late, bills_due_soon,
         supplier_plan_payments, loan_installments, low_stock, credit_score_drop, spending_spike, sales_drop,
         stale_referrals, goals_soon, stale_bank, plan_and_trial]


def generate(db: Session, business: Business, c: Context) -> None:
    """Run every rule. One that fails is logged and skipped."""
    for rule in RULES:
        try:
            rule(db, business, c)
            db.commit()  # keep what this rule raised even if a later one fails
        except Exception:
            log.exception("Alert rule %s failed for business %s", rule.__name__, business.id)
            db.rollback()
