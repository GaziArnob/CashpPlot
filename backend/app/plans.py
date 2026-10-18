"""Subscription plans: what Free and Pro include, and trials.

Free:  dashboard, transactions, customers and invoices, bills and suppliers, a 7-day cash forecast.
Pro:   everything else (30-day forecast, Cash Advisor, collections scoring, supplier plans, products,
       credit score, loan center, reports, AI agent, lender sharing and referrals).

New businesses start on a 14-day Pro trial. In this build "upgrading" only switches the plan: no payment
is taken (BILLING_MODE=demo). Connect a payment provider before charging anyone.
"""

from datetime import datetime, timedelta

from app.models import Business, utcnow

TRIAL_DAYS = 14
FREE_FORECAST_DAYS = 7

PRO_FEATURES = {
    "forecast_long": "A cash forecast longer than 7 days",
    "advisor": "The Cash Advisor and daily action plan",
    "collections": "Collections scoring and credit limits",
    "payables": "Supplier payment plans and financing comparison",
    "products": "Product performance",
    "credit": "The credit score and loan center",
    "reports": "Reports and goals",
    "agent": "The AI assistant",
    "lender_access": "Sharing your data with lenders",
    "referrals": "Lender introductions",
}


def effective_plan(business: Business, now: datetime | None = None) -> str:
    """'pro' while a Pro plan is active (or its trial has not ended), otherwise 'free'."""
    if business.plan != "pro":
        return "free"
    expires = business.plan_expires_at
    return "pro" if expires is None or expires > (now or utcnow()) else "free"


def can_use(business: Business, feature: str) -> bool:
    return feature not in PRO_FEATURES or effective_plan(business) == "pro"


def start_trial(business: Business) -> None:
    business.plan = "pro"
    business.plan_expires_at = utcnow() + timedelta(days=TRIAL_DAYS)


def describe(business: Business) -> dict:
    now = utcnow()
    plan = effective_plan(business, now)
    expires = business.plan_expires_at
    on_trial = business.plan == "pro" and expires is not None
    return {
        "plan": business.plan, "effective_plan": plan,
        "trial": on_trial and plan == "pro", "trial_ended": on_trial and plan == "free",
        "expires_at": expires,
        "days_left": max(0, (expires - now).days + 1) if expires and plan == "pro" else None,
        "free_forecast_days": FREE_FORECAST_DAYS,
        "features": {name: {"label": label, "included": plan == "pro"} for name, label in PRO_FEATURES.items()},
    }
