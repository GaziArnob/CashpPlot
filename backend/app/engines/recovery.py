"""Small payment-behavior helpers. Ranking itself lives in collection.py."""

from datetime import date

from app.engines.data import BusinessData


def tone_for(days_overdue: int) -> str:
    if days_overdue <= 7:
        return "friendly"
    if days_overdue <= 30:
        return "firm"
    return "final"


def late_share(data: BusinessData, customer_id: int) -> float:
    paid = [i for i in data.invoices if i.customer_id == customer_id and i.paid_date]
    if not paid:
        return 0.5  # unknown history counts as medium risk
    return sum(1 for i in paid if i.paid_date > i.due_date) / len(paid)


def risk_level(late: float, max_overdue: int) -> str:
    if late >= 0.5 or max_overdue > 30:
        return "high"
    if late >= 0.25 or max_overdue > 7:
        return "medium"
    return "low"
