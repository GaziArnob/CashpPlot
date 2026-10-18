"""Product performance: which products to push, keep, shrink or clear.

Per product (last 30/90 days): units, revenue and growth, gross margin, profit contribution,
inventory turnover and days of stock left, and cash conversion speed (cash vs credit and how long
credit takes to come back).

Classes. Speed = inventory turnover against the median of selling products: fast at 60%+ of the
median, slow below 25%, medium between (a strict median split would separate near-identical
fast sellers by noise). Margin is high at or above the median margin.
  star      fast turnover and high margin           -> stock more (as cash allows)
  cash_cow  fast and low margin, or medium speed     -> keep as is
            and high margin
  slow      slow turnover, or medium speed and       -> buy less, discount the excess
            low margin
  dead      stock on hand, no sale for 60+ days      -> liquidate
  new       added in the last 30 days                -> watch, too early to judge
  inactive  no stock and no recent sales             -> nothing to do

Scaling up is capped by the cash budget: the lowest forecast balance over the next 30 days minus
the safety threshold. With a cash gap ahead the budget is zero, and stars wait for cash to recover.
"""

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from app.engines.data import BusinessData

FAST_SHARE_OF_MEDIAN = 0.60
SLOW_SHARE_OF_MEDIAN = 0.25
DEAD_AFTER_DAYS = 60
NEW_PRODUCT_DAYS = 30
STAR_STOCK_DAYS = 14       # star target cover after scaling up
SLOW_STOCK_DAYS = 30       # slow movers: keep at most a month of stock
SLOW_DISCOUNT_PCT = 10
DEAD_DISCOUNT_PCT = 30
GROWTH_CAP = 0.30          # demand projection uses growth clipped to +-30%


@dataclass
class Window:
    units: float = 0.0
    revenue: float = 0.0
    cogs: float = 0.0
    cash_revenue: float = 0.0


def _window(sales, start: date, end: date) -> Window:
    w = Window()
    for s in sales:
        if start <= s.date <= end:
            w.units += s.qty
            w.revenue += s.qty * s.unit_price
            w.cogs += s.qty * s.unit_cost
            if s.payment_type == "cash":
                w.cash_revenue += s.qty * s.unit_price
    return w


def _collection_days(data: BusinessData, invoice_ids: set[int], today: date) -> float | None:
    """Average days from invoice to (last) payment for the credit sales of one product."""
    days = []
    for inv in data.invoices:
        if inv.id in invoice_ids:
            end = inv.paid_date or today  # still open: it has taken at least this long
            days.append((end - inv.issue_date).days)
    return float(np.mean(days)) if days else None


def metrics(data: BusinessData, today: date) -> list[dict]:
    by_product: dict[int, list] = {}
    for s in data.sales:
        by_product.setdefault(s.product_id, []).append(s)
    total_profit_90 = 0.0
    rows = []
    for p in data.products:
        sales = by_product.get(p.id, [])
        w30 = _window(sales, today - timedelta(days=29), today)
        prev30 = _window(sales, today - timedelta(days=59), today - timedelta(days=30))
        w90 = _window(sales, today - timedelta(days=89), today)
        last_sale = max((s.date for s in sales), default=None)
        daily_units = w30.units / 30 if w30.units else w90.units / 90
        inventory_value = p.stock_qty * p.unit_cost
        profit_90 = w90.revenue - w90.cogs
        total_profit_90 += max(profit_90, 0.0)
        credit_invoices = {s.invoice_id for s in sales if s.payment_type == "credit" and s.invoice_id
                           and s.date >= today - timedelta(days=180)}
        collect_days = _collection_days(data, credit_invoices, today)
        cash_share = w90.cash_revenue / w90.revenue if w90.revenue else None
        rows.append({
            "product_id": p.id,
            "name": p.name,
            "unit_cost": p.unit_cost,
            "unit_price": p.unit_price,
            "stock_qty": p.stock_qty,
            "inventory_value": round(inventory_value),
            "units_30d": round(w30.units, 1),
            "units_90d": round(w90.units, 1),
            "revenue_30d": round(w30.revenue),
            "revenue_90d": round(w90.revenue),
            "growth_pct": round(100 * (w30.revenue - prev30.revenue) / prev30.revenue, 1) if prev30.revenue else None,
            "margin_per_unit": round(p.unit_price - p.unit_cost, 2),
            "margin_pct": round(100 * (p.unit_price - p.unit_cost) / p.unit_price, 1) if p.unit_price else None,
            "profit_90d": round(profit_90),
            "daily_units": round(daily_units, 2),
            "days_of_stock": round(p.stock_qty / daily_units, 1) if daily_units else None,
            # Annualized cost of goods sold / stock value. No stock but selling = very fast.
            "turnover": round(w90.cogs * 365 / 90 / inventory_value, 1) if inventory_value else
                        (None if not w90.units else 999.0),
            "cash_share_pct": round(100 * cash_share) if cash_share is not None else None,
            "credit_collection_days": round(collect_days, 1) if collect_days is not None else None,
            # Days until a sale's money is in hand: cash now, credit after the collection delay.
            "cash_conversion_days": round((1 - cash_share) * (collect_days or 0), 1) if cash_share is not None else None,
            "last_sale": last_sale.isoformat() if last_sale else None,
            "days_since_last_sale": (today - last_sale).days if last_sale else None,
            "is_new": (today - p.created).days < NEW_PRODUCT_DAYS,
            "active": p.active,
            "_growth": (w30.revenue - prev30.revenue) / prev30.revenue if prev30.revenue else 0.0,
        })
    for r in rows:
        r["profit_share_pct"] = round(100 * max(r["profit_90d"], 0) / total_profit_90, 1) if total_profit_90 else 0.0
    return rows


def classify(rows: list[dict]) -> dict:
    """Adds 'product_class' to each row. Returns the thresholds used."""
    selling = [r for r in rows if not r["is_new"] and r["units_30d"] > 0 and r["turnover"] is not None]
    t_med = float(np.median([r["turnover"] for r in selling])) if selling else 0.0
    m_med = float(np.median([r["margin_pct"] for r in selling if r["margin_pct"] is not None])) if selling else 0.0
    for r in rows:
        stale = r["days_since_last_sale"] is None or r["days_since_last_sale"] >= DEAD_AFTER_DAYS
        if r["is_new"]:
            cls = "new"
        elif stale and r["stock_qty"] > 0:
            cls = "dead"
        elif stale or r["turnover"] is None:
            cls = "inactive"
        else:
            high_margin = (r["margin_pct"] or 0) >= m_med
            t = r["turnover"]
            speed = ("fast" if t >= FAST_SHARE_OF_MEDIAN * t_med
                     else "medium" if t >= SLOW_SHARE_OF_MEDIAN * t_med else "slow")
            r["speed"] = speed
            if speed == "fast":
                cls = "star" if high_margin else "cash_cow"
            elif speed == "medium":
                cls = "cash_cow" if high_margin else "slow"
            else:
                cls = "slow"
        r["product_class"] = cls
    return {"turnover_median": round(t_med, 1), "margin_median_pct": round(m_med, 1)}


def recommend(rows: list[dict], cash_budget: float) -> dict:
    """Quantity changes for the next 30 days, with scale-ups limited to the cash budget."""
    stars = []
    for r in rows:
        cls = r["product_class"]
        demand_30 = r["daily_units"] * 30 * (1 + max(-GROWTH_CAP, min(GROWTH_CAP, r["_growth"])))
        r["demand_30d"] = round(demand_30, 1)
        r["recommended_qty_change"] = 0.0
        r["cash_impact"] = 0.0  # + frees cash, - needs cash
        if cls == "star":
            want = max(0.0, STAR_STOCK_DAYS * demand_30 / 30 - r["stock_qty"])
            r["_want_units"] = want
            r["_want_cash"] = want * r["unit_cost"]
            stars.append(r)
        elif cls == "slow":
            excess = round(max(0.0, r["stock_qty"] - SLOW_STOCK_DAYS * demand_30 / 30))  # whole units
            r["recommended_qty_change"] = -excess
            r["discount_pct"] = SLOW_DISCOUNT_PCT if excess else 0
            r["cash_impact"] = round(excess * r["unit_price"] * (1 - SLOW_DISCOUNT_PCT / 100))
            r["action"] = (f"Buy less: pause reorders and clear {round(excess)} extra units at "
                           f"{SLOW_DISCOUNT_PCT}% off" if excess >= 1 else "Buy less: reorder only what sells")
        elif cls == "dead":
            r["recommended_qty_change"] = -round(r["stock_qty"])
            r["discount_pct"] = DEAD_DISCOUNT_PCT
            r["cash_impact"] = round(r["stock_qty"] * r["unit_price"] * (1 - DEAD_DISCOUNT_PCT / 100))
            r["action"] = (f"Liquidate: no sale in {r['days_since_last_sale'] or 'any'} days; "
                           f"sell remaining {round(r['stock_qty'])} units at {DEAD_DISCOUNT_PCT}% off")
        elif cls == "cash_cow":
            r["action"] = "Keep as is: steady seller, reorder what sells"
        elif cls == "new":
            r["action"] = "Watch: too new to judge, review after 30 days"
        else:
            r["action"] = "Nothing to do: no stock, no recent sales"

    # Share the budget between stars by their profit contribution, never more than each needs.
    budget = max(0.0, cash_budget)
    total_want = sum(r["_want_cash"] for r in stars)
    total_profit = sum(max(r["profit_90d"], 1) for r in stars)
    spent = 0.0
    for r in sorted(stars, key=lambda x: -x["profit_90d"]):
        share = budget * max(r["profit_90d"], 1) / total_profit if total_profit else 0.0
        cash = min(r["_want_cash"], share)
        units = int(cash // r["unit_cost"]) if r["unit_cost"] else 0
        r["recommended_qty_change"] = float(units)
        r["cash_impact"] = -round(units * r["unit_cost"])
        spent += units * r["unit_cost"]
        if r["_want_units"] < 1:
            r["action"] = "Keep stock up: already enough on hand"
        elif units >= r["_want_units"] - 0.5:
            r["action"] = f"Scale up: stock {units} more units (to ~{STAR_STOCK_DAYS} days of demand)"
        elif units > 0:
            r["action"] = (f"Scale up partly: stock {units} more units now (cash allows); "
                           f"{round(r['_want_units'] - units)} more once cash recovers")
        else:
            r["action"] = (f"Scale up once cash recovers: needs {round(r['_want_cash']):,} for "
                           f"{round(r['_want_units'])} more units")
        r["scale_up_cash_needed"] = round(r["_want_cash"])

    for r in rows:
        for k in [k for k in r if k.startswith("_")]:
            del r[k]
    return {
        "cash_budget": round(budget),
        "scale_up_spent": round(spent),
        "scale_up_wanted": round(total_want),
        "cash_freed_if_cleared": round(sum(r["cash_impact"] for r in rows if r["cash_impact"] > 0)),
        "cash_tied_in_slow_and_dead": round(sum(r["inventory_value"] for r in rows
                                                if r["product_class"] in ("slow", "dead"))),
    }


def score_products(data: BusinessData, today: date, cash_budget: float) -> dict:
    rows = metrics(data, today)
    thresholds = classify(rows)
    summary = recommend(rows, cash_budget)
    counts = {c: sum(1 for r in rows if r["product_class"] == c)
              for c in ("star", "cash_cow", "slow", "dead", "new", "inactive")}
    order = {"star": 0, "cash_cow": 1, "slow": 2, "dead": 3, "new": 4, "inactive": 5}
    rows.sort(key=lambda r: (order[r["product_class"]], -r["profit_90d"]))
    return {"products": rows, "thresholds": thresholds, "counts": counts, **summary}
