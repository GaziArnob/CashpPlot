"""Cash flow prediction (Technical Documentation section 2.1).

Projects the daily balance for the next 7-30 days and flags days below the cash threshold.
"""

import math
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from app.engines.data import SCHEDULED_EXPENSE, SCHEDULED_INCOME, BusinessData

HISTORY_DAYS = 180
HW_MIN_DAYS = 60
Z80 = 1.28  # 80% band


@dataclass
class Scenario:
    sales_change_pct: float = 0.0
    extra_monthly_expense: float = 0.0
    loan_amount: float = 0.0
    loan_emi: float = 0.0


def daily_baseline_series(data: BusinessData, start: date, end: date) -> tuple[list[float], list[float]]:
    """Daily income and expense from start to end inclusive, without scheduled categories.

    Recurring payables (rent, salaries...) are left out too: they are placed on their exact
    day instead, because a few large monthly payments distort a daily trend model.
    """
    skip_expense = SCHEDULED_EXPENSE | {r.category for r in data.recurring}
    n = (end - start).days + 1
    inc = [0.0] * n
    exp = [0.0] * n
    for t in data.transactions:
        if start <= t.date <= end:
            i = (t.date - start).days
            if t.type == "income" and t.category not in SCHEDULED_INCOME:
                inc[i] += t.amount
            elif t.type == "expense" and t.category not in skip_expense:
                exp[i] += t.amount
    return inc, exp


def _wma(values: list[float], window: int = 28) -> float:
    vals = values[-window:]
    if not vals:
        return 0.0
    weights = np.arange(1, len(vals) + 1, dtype=float)
    return float(np.dot(vals, weights) / weights.sum())


def _dow_factors(values: list[float], start: date) -> list[float]:
    """Average of each weekday divided by the overall average, over the last 12 weeks."""
    take = min(len(values), 84)
    vals = values[-take:]
    first = start + timedelta(days=len(values) - take)
    overall = sum(vals) / len(vals) if vals else 0.0
    if overall <= 0:
        return [1.0] * 7
    sums, counts = [0.0] * 7, [0] * 7
    for i, v in enumerate(vals):
        wd = (first + timedelta(days=i)).weekday()
        sums[wd] += v
        counts[wd] += 1
    return [(sums[d] / counts[d]) / overall if counts[d] else 1.0 for d in range(7)]


def _wma_forecast(values: list[float], start: date, horizon_dates: list[date]) -> tuple[list[float], list[float]]:
    """Returns (forecast for horizon, one-step residuals on history)."""
    dow = _dow_factors(values, start)
    level = _wma(values)
    preds = [max(0.0, level * dow[d.weekday()]) for d in horizon_dates]
    residuals = []
    for i in range(28, len(values)):
        fitted = _wma(values[:i]) * dow[(start + timedelta(days=i)).weekday()]
        residuals.append(values[i] - fitted)
    return preds, residuals


def _cap_outliers(values: list[float]) -> list[float]:
    """Clip one-off spikes (a bulk order, a yearly payment) so they don't drag the level."""
    if len(values) < 14:
        return values
    q1, q3 = np.percentile(values, [25, 75])
    cap = q3 + 3 * (q3 - q1)
    return [min(v, cap) for v in values]


def _holt_winters(values: list[float], horizon: int, season: int = 7,
                  alpha: float = 0.15, beta: float = 0.03, gamma: float = 0.2, phi: float = 0.9):
    """Additive Holt-Winters with a damped trend. Returns (forecast, one-step residuals)."""
    level = sum(values[:season]) / season
    trend = (sum(values[season:2 * season]) - sum(values[:season])) / (season * season)
    seas = [values[i] - level for i in range(season)]
    residuals = []
    for i in range(season, len(values)):
        s = seas[i % season]
        fitted = level + phi * trend + s
        residuals.append(values[i] - fitted)
        prev_level = level
        level = alpha * (values[i] - s) + (1 - alpha) * (prev_level + phi * trend)
        trend = beta * (level - prev_level) + (1 - beta) * phi * trend
        seas[i % season] = gamma * (values[i] - level) + (1 - gamma) * s
    n = len(values)
    preds = []
    damp = 0.0
    for h in range(1, horizon + 1):
        damp += phi ** h
        preds.append(max(0.0, level + damp * trend + seas[(n + h - 1) % season]))
    return preds, residuals


def collection_probability(data: BusinessData, customer_id: int) -> float:
    """Share of the customer's past invoices that were paid on or before the due date."""
    paid = [i for i in data.invoices if i.customer_id == customer_id and i.paid_date]
    if not paid:
        return 0.7
    on_time = sum(1 for i in paid if i.paid_date <= i.due_date)
    return on_time / len(paid)


def new_credit_collections(data: BusinessData, today: date) -> tuple[float, float]:
    """Cash from credit sales that haven't been invoiced yet.

    Returns (average collected per day over the last 90 days, typical days from invoice to payment).
    Open invoices are scheduled one by one, so this only adds money from invoices issued in the
    future, starting once that issue-to-payment lag has passed.
    """
    since = today - timedelta(days=90)
    collected = sum(t.amount for t in data.transactions
                    if t.type == "income" and t.category in SCHEDULED_INCOME and since <= t.date < today)
    lags = [(i.paid_date - i.issue_date).days for i in data.invoices
            if i.paid_date and i.paid_date >= today - timedelta(days=180)]
    lag = float(np.median(lags)) if lags else 30.0
    return collected / 90.0, lag


def forecast(data: BusinessData, today: date, days: int = 30, scenario: Scenario | None = None) -> dict:
    days = max(1, min(days, 90))
    scenario = scenario or Scenario()
    horizon = [today + timedelta(days=h) for h in range(1, days + 1)]
    end = horizon[-1]

    # 1. Daily baseline series from history (yesterday back, up to 180 days).
    first_txn = min((t.date for t in data.transactions), default=today)
    hist_start = max(today - timedelta(days=HISTORY_DAYS), first_txn)
    hist_end = today - timedelta(days=1)
    if hist_end >= hist_start:
        inc_hist, exp_hist = daily_baseline_series(data, hist_start, hist_end)
    else:
        inc_hist, exp_hist = [], []
    n_hist = len(inc_hist)

    # 2. Baseline forecast.
    if n_hist >= HW_MIN_DAYS:
        method = "holt_winters"
        inc_pred, inc_res = _holt_winters(_cap_outliers(inc_hist), days)
        exp_pred, exp_res = _holt_winters(_cap_outliers(exp_hist), days)
    elif n_hist >= 7:
        method = "weighted_moving_average"
        inc_pred, inc_res = _wma_forecast(inc_hist, hist_start, horizon)
        exp_pred, exp_res = _wma_forecast(exp_hist, hist_start, horizon)
    else:
        method = "average"
        avg_i = sum(inc_hist) / n_hist if n_hist else 0.0
        avg_e = sum(exp_hist) / n_hist if n_hist else 0.0
        inc_pred, exp_pred = [avg_i] * days, [avg_e] * days
        inc_res, exp_res = [], []

    k = min(len(inc_res), len(exp_res))
    net_res = [inc_res[-k + i] - exp_res[-k + i] for i in range(k)] if k else []
    if len(net_res) >= 7:
        sigma = float(np.std(net_res))
    else:
        net_hist = [a - b for a, b in zip(inc_hist, exp_hist)]
        sigma = float(np.std(net_hist)) if len(net_hist) > 1 else 0.0

    # 3. Known future events.
    inflow = {d: 0.0 for d in horizon}
    outflow = {d: 0.0 for d in horizon}
    events_in, events_out = [], []
    overdue_receivables = 0.0
    for inv in data.invoices:
        if inv.paid_date:
            continue
        owed = inv.outstanding  # what is left after any partial payments
        if inv.due_date <= today:
            overdue_receivables += owed
            continue
        if inv.due_date <= end:
            p = collection_probability(data, inv.customer_id)
            inflow[inv.due_date] += owed * p
            events_in.append({"date": inv.due_date.isoformat(), "kind": "invoice", "invoice_id": inv.id,
                              "customer_id": inv.customer_id, "amount": round(owed),
                              "expected": round(owed * p), "probability": round(p, 2)})
    for b in data.bills:
        if b.paid_date:
            continue
        # An accepted payment plan replaces the single due-date payment; otherwise pay what's left.
        payments = b.schedule or [(b.due_date, b.outstanding)]
        for due, amount in payments:
            when = max(due, horizon[0])  # anything overdue is assumed paid tomorrow
            if when <= end and amount > 0:
                outflow[when] += amount
                events_out.append({"date": when.isoformat(), "kind": "bill", "bill_id": b.id,
                                   "supplier": b.supplier_name, "amount": round(amount),
                                   "overdue": due <= today, "plan_id": b.plan_id})
    for r in data.repayments:
        if r.paid_date:
            continue
        when = max(r.due_date, horizon[0])
        if when <= end:
            outflow[when] += r.amount
            events_out.append({"date": when.isoformat(), "kind": "loan_repayment", "loan_id": r.loan_id,
                               "amount": round(r.amount), "overdue": r.due_date <= today})

    for rec in data.recurring:
        for d in horizon:
            last_day = (date(d.year + d.month // 12, d.month % 12 + 1, 1) - timedelta(days=1)).day
            if d.day == min(rec.day_of_month, last_day):
                outflow[d] += rec.amount
                events_out.append({"date": d.isoformat(), "kind": "recurring", "name": rec.name,
                                   "category": rec.category, "amount": round(rec.amount), "overdue": False})

    # What-if adjustments.
    if scenario.loan_amount:
        inflow[horizon[0]] += scenario.loan_amount
    if scenario.loan_emi:
        for m in range(1, days // 30 + 1):
            d = today + timedelta(days=30 * m)
            if d in outflow:
                outflow[d] += scenario.loan_emi

    daily_credit, credit_lag = new_credit_collections(data, today)

    # 4. Roll the balance forward.
    balance = data.balance_on(today)
    start_balance = balance
    threshold = data.cash_threshold
    rows, shortages = [], []
    for h, d in enumerate(horizon, start=1):
        # Collections from invoices issued after today ramp in around the usual payment lag.
        ramp = min(1.0, max(0.0, (h - (credit_lag - 5)) / 10.0))
        i_hat = (inc_pred[h - 1] + daily_credit * ramp) * (1 + scenario.sales_change_pct / 100.0)
        e_hat = exp_pred[h - 1] + scenario.extra_monthly_expense / 30.0
        balance += i_hat - e_hat + inflow[d] - outflow[d]
        band = Z80 * sigma * math.sqrt(h)
        low, high = balance - band, balance + band
        if balance < threshold:
            status = "shortage"
            shortages.append({"date": d.isoformat(), "balance": round(balance), "gap": round(threshold - balance)})
        elif low < threshold:
            status = "at_risk"
        else:
            status = "ok"
        rows.append({
            "date": d.isoformat(),
            "income": round(i_hat), "expense": round(e_hat),
            "expected_inflow": round(inflow[d]), "expected_outflow": round(outflow[d]),
            "balance": round(balance), "low": round(low), "high": round(high), "status": status,
        })

    min_row = min(rows, key=lambda r: r["balance"])
    first = shortages[0] if shortages else None
    drivers = []
    if first:
        fdate = date.fromisoformat(first["date"])
        drivers = [e for e in events_out if fdate - timedelta(days=7) <= date.fromisoformat(e["date"]) <= fdate]
        drivers.sort(key=lambda e: -e["amount"])

    return {
        "as_of": today.isoformat(),
        "days": days,
        "method": method,
        "history_days": n_hist,
        "start_balance": round(start_balance),
        "threshold": round(threshold),
        "series": rows,
        "shortages": shortages,
        "first_shortage": first,
        "largest_gap": max((s["gap"] for s in shortages), default=0),
        "min_balance": {"date": min_row["date"], "balance": min_row["balance"]},
        "at_risk_days": sum(1 for r in rows if r["status"] == "at_risk"),
        "overdue_receivables": round(overdue_receivables),
        "expected_inflows": events_in,
        "expected_outflows": events_out,
        "drivers": drivers,
    }
