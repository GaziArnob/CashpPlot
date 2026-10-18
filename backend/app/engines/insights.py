"""Insight engine (Technical Documentation section 2.6) and P&L reports."""

from collections import defaultdict
from datetime import date, timedelta

from app.engines.data import BusinessData

CHANGE_THRESHOLD = 0.20


def spending_insights(data: BusinessData, today: date) -> list[dict]:
    """Compare each expense category's last 30 days with its average over the 90 days before."""
    recent_start = today - timedelta(days=29)
    prior_start = recent_start - timedelta(days=90)
    recent, prior = defaultdict(float), defaultdict(float)
    for t in data.transactions:
        if t.type != "expense":
            continue
        if recent_start <= t.date <= today:
            recent[t.category] += t.amount
        elif prior_start <= t.date < recent_start:
            prior[t.category] += t.amount

    out = []
    for cat in set(recent) | set(prior):
        avg = prior[cat] / 3
        cur = recent[cat]
        if avg <= 0:
            continue
        change = (cur - avg) / avg
        if abs(change) >= CHANGE_THRESHOLD:
            direction = "up" if change > 0 else "down"
            out.append({
                "category": cat, "last_30_days": round(cur), "monthly_average": round(avg),
                "change_pct": round(change * 100), "direction": direction,
                "message": f"{cat} spending is {direction} {abs(round(change * 100))}% compared with your "
                           f"3-month average ({round(cur)} vs {round(avg)}).",
            })
    out.sort(key=lambda x: -abs(x["change_pct"]))

    total_recent = sum(recent.values())
    if total_recent > 0:
        top_cat, top_amt = max(recent.items(), key=lambda kv: kv[1])
        out.append({
            "category": top_cat, "last_30_days": round(top_amt), "monthly_average": None,
            "change_pct": None, "direction": "share",
            "message": f"{top_cat} is your largest expense: {round(100 * top_amt / total_recent)}% "
                       f"of spending in the last 30 days.",
        })
    return out


def pnl(data: BusinessData, year: int, month: int) -> dict:
    income, expense = defaultdict(float), defaultdict(float)
    for t in data.transactions:
        if t.date.year == year and t.date.month == month:
            (income if t.type == "income" else expense)[t.category] += t.amount
    total_inc, total_exp = sum(income.values()), sum(expense.values())
    return {
        "month": f"{year:04d}-{month:02d}",
        "income": {k: round(v) for k, v in sorted(income.items(), key=lambda kv: -kv[1])},
        "expense": {k: round(v) for k, v in sorted(expense.items(), key=lambda kv: -kv[1])},
        "total_income": round(total_inc),
        "total_expense": round(total_exp),
        "net_profit": round(total_inc - total_exp),
        "margin_pct": round(100 * (total_inc - total_exp) / total_inc, 1) if total_inc else None,
    }
