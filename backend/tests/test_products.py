"""Product performance: metrics, classes, cash-limited scale-up, and the product/stock API."""

from datetime import date, timedelta

from app.engines import products as pe
from app.engines.data import BusinessData, Inv, ProductRow, SaleRow

TODAY = date(2026, 10, 17)
OLD = TODAY - timedelta(days=400)


def biz() -> BusinessData:
    return BusinessData(business_id=1, started_at=OLD, opening_balance=0, cash_threshold=0)


def product(d, pid, cost, price, stock, daily_units, days=90, last_sale_days_ago=0, created=OLD, credit_inv=None):
    """A product that sold `daily_units` a day for `days` days, ending `last_sale_days_ago` days ago."""
    d.products.append(ProductRow(pid, f"P{pid}", cost, price, stock, created, True))
    if daily_units:
        for k in range(days):
            day = TODAY - timedelta(days=last_sale_days_ago + k)
            pay, inv = ("credit", credit_inv) if credit_inv and k % 2 else ("cash", None)
            d.sales.append(SaleRow(pid, day, daily_units, price, cost, pay, inv))


def mixed_shop() -> BusinessData:
    d = biz()
    # Turnover: 7 days of stock ~52/yr (fast), 18 days ~20/yr (medium), 300 days ~1.2/yr (slow).
    product(d, 1, 70, 100, stock=70, daily_units=10)     # fast, 30% margin   -> star
    product(d, 2, 95, 100, stock=70, daily_units=10)     # fast, 5% margin    -> cash cow
    product(d, 3, 70, 100, stock=90, daily_units=5)      # medium, 30% margin -> cash cow
    product(d, 4, 95, 100, stock=90, daily_units=5)      # medium, 5% margin  -> slow
    product(d, 5, 70, 100, stock=600, daily_units=2)     # slow               -> slow
    product(d, 9, 70, 100, stock=70, daily_units=10)     # more fast sellers, so the median is "fast"
    product(d, 10, 95, 100, stock=70, daily_units=10)
    product(d, 6, 70, 100, stock=40, daily_units=2, last_sale_days_ago=70)    # stale with stock -> dead
    product(d, 7, 70, 100, stock=30, daily_units=0, created=TODAY - timedelta(days=5))  # new
    product(d, 8, 70, 100, stock=0, daily_units=0)       # nothing           -> inactive
    return d


def classes(result) -> dict[int, str]:
    return {r["product_id"]: r["product_class"] for r in result["products"]}


def test_classification_covers_every_class():
    r = pe.score_products(mixed_shop(), TODAY, cash_budget=0)
    assert classes(r) == {1: "star", 2: "cash_cow", 3: "cash_cow", 4: "slow", 5: "slow", 6: "dead",
                          7: "new", 8: "inactive", 9: "star", 10: "cash_cow"}
    assert sum(r["counts"].values()) == 10


def test_metrics_edge_cases():
    rows = {r["product_id"]: r for r in pe.metrics(mixed_shop(), TODAY)}
    assert rows[7]["days_of_stock"] is None and rows[7]["growth_pct"] is None   # new, no sales
    assert rows[8]["turnover"] is None                                          # no stock, no sales
    assert rows[1]["growth_pct"] == 0.0 and rows[1]["margin_pct"] == 30.0
    assert rows[1]["days_of_stock"] == 7.0
    assert rows[6]["days_since_last_sale"] == 70


def test_no_scale_up_without_cash():
    r = pe.score_products(mixed_shop(), TODAY, cash_budget=0)
    star = next(p for p in r["products"] if p["product_id"] == 1)
    assert star["recommended_qty_change"] == 0 and star["cash_impact"] == 0
    assert "once cash recovers" in star["action"] and star["scale_up_cash_needed"] > 0
    assert r["scale_up_spent"] == 0


def test_scale_up_is_capped_by_budget():
    full = pe.score_products(mixed_shop(), TODAY, cash_budget=1_000_000)
    star = next(p for p in full["products"] if p["product_id"] == 1)
    want_units = 14 * 10 - 70  # 14 days of demand minus stock on hand
    assert star["recommended_qty_change"] == want_units and star["cash_impact"] == -want_units * 70
    half = pe.score_products(mixed_shop(), TODAY, cash_budget=2_000)
    star = next(p for p in half["products"] if p["product_id"] == 1)
    assert 0 < -star["cash_impact"] <= 2_000 and "partly" in star["action"]
    assert half["scale_up_spent"] <= 2_000


def test_budget_split_by_profit_between_stars():
    d = biz()
    product(d, 1, 70, 100, stock=0, daily_units=20)   # earns twice as much...
    product(d, 2, 70, 100, stock=0, daily_units=10)   # ...as this one
    product(d, 3, 95, 100, stock=0, daily_units=15)   # low margin, keeps the median margin below 30%
    r = pe.score_products(d, TODAY, cash_budget=9_000)
    spend = {p["product_id"]: -p["cash_impact"] for p in r["products"] if p["product_class"] == "star"}
    assert set(spend) == {1, 2} and spend[1] > spend[2]


def test_clearing_slow_and_dead_frees_cash():
    r = pe.score_products(mixed_shop(), TODAY, cash_budget=0)
    rows = {p["product_id"]: p for p in r["products"]}
    slow = rows[5]  # 600 on hand, 2 a day: keep 60, clear 540 at 10% off
    assert slow["recommended_qty_change"] == -540 and slow["cash_impact"] == round(540 * 100 * 0.9)
    dead = rows[6]  # all 40 at 30% off
    assert dead["recommended_qty_change"] == -40 and dead["cash_impact"] == round(40 * 100 * 0.7)
    assert r["cash_freed_if_cleared"] >= slow["cash_impact"] + dead["cash_impact"]
    assert r["cash_tied_in_slow_and_dead"] == 90 * 95 + 600 * 70 + 40 * 70  # products 4, 5 and 6 at cost


def test_cash_conversion_counts_credit_delay():
    d = biz()
    d.invoices.append(Inv(50, 1, 1_000, TODAY - timedelta(days=100), TODAY - timedelta(days=85),
                          TODAY - timedelta(days=80), 1_000))
    product(d, 1, 70, 100, stock=70, daily_units=10, credit_inv=50)  # half the days on credit
    row = pe.metrics(d, TODAY)[0]
    assert row["credit_collection_days"] == 20.0 and row["cash_share_pct"] == 50
    assert row["cash_conversion_days"] == 10.0
    cash_only = biz()
    product(cash_only, 1, 70, 100, stock=70, daily_units=10)
    assert pe.metrics(cash_only, TODAY)[0]["cash_conversion_days"] == 0.0


def test_empty_business():
    r = pe.score_products(biz(), TODAY, cash_budget=10_000)
    assert r["products"] == [] and r["scale_up_spent"] == 0


def test_product_api(client, demo_headers):
    from app.db import SessionLocal
    from app.models import ProductScore
    perf = client.get("/products/performance", headers=demo_headers).json()
    assert len(perf["products"]) == 13 and perf["counts"]["dead"] == 2 and perf["counts"]["new"] == 1
    assert perf["counts"]["star"] >= 1
    db = SessionLocal()
    try:
        assert db.query(ProductScore).count() == 13
    finally:
        db.close()
    if perf["shortage_gap"]:
        stars = [p for p in perf["products"] if p["product_class"] == "star"]
        assert all(p["cash_impact"] == 0 for p in stars)  # cash gap ahead: no scale-up spending


def test_sales_and_stock_api(client):
    from tests.test_api import signup
    h = signup(client, "products@example.com")
    p = client.post("/products", headers=h, json={"name": "Tea", "unit_cost": 200, "unit_price": 250,
                                                  "stock_qty": 10}).json()
    sale = client.post("/sale-items", headers=h, json={"product_id": p["id"], "date": "2026-10-16", "qty": 4})
    assert sale.status_code == 201 and sale.json()["unit_price"] == 250
    assert client.get("/products", headers=h).json()[0]["stock_qty"] == 6
    txns = client.get("/transactions?type=income", headers=h).json()["items"]
    assert txns[0]["amount"] == 1_000 and txns[0]["category"] == "Sales"
    assert client.post("/sale-items", headers=h, json={"product_id": p["id"], "date": "2026-10-16",
                                                       "qty": 7}).status_code == 409
    assert client.post("/sale-items", headers=h, json={"product_id": p["id"], "date": "2026-10-16", "qty": 1,
                                                       "payment_type": "credit"}).status_code == 422
    buy = client.post("/stock-movements", headers=h, json={"product_id": p["id"], "date": "2026-10-16",
                                                           "qty": 20, "unit_cost": 210}).json()
    assert buy["stock_qty"] == 26 and buy["unit_cost"] == 210
    exp = client.get("/transactions?type=expense", headers=h).json()["items"]
    assert exp[0]["amount"] == 4_200 and exp[0]["category"] == "Inventory"
    assert client.post("/stock-movements", headers=h, json={"product_id": p["id"], "date": "2026-10-16",
                                                            "qty": 5, "reason": "write_off"}).status_code == 422
    assert client.post("/stock-movements", headers=h, json={"product_id": p["id"], "date": "2026-10-16",
                                                            "qty": -100, "reason": "adjustment"}).status_code == 409


def test_product_api_isolation(client, demo_headers):
    from tests.test_api import signup
    h = signup(client, "products-other@example.com")
    demo_product = client.get("/products", headers=demo_headers).json()[0]["id"]
    assert client.post("/sale-items", headers=h, json={"product_id": demo_product, "date": "2026-10-16",
                                                       "qty": 1}).status_code == 404
    assert client.put(f"/products/{demo_product}", headers=h, json={"name": "x"}).status_code == 404
    assert client.get("/products/performance", headers=h).json()["products"] == []
