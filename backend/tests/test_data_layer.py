"""Step 1 of the cash advisor: migrations, partial payments, recurring payables, seed coverage."""

from datetime import date, timedelta

from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from app import db as app_db
from app.engines import forecast
from app.engines.data import BusinessData, Inv, RecurringRow, Txn

TODAY = date(2026, 10, 17)


def _cfg(url: str):
    cfg = app_db._alembic_config()
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_migrations_build_an_empty_database(tmp_path):
    url = f"sqlite:///{tmp_path / 'fresh.db'}"
    command.upgrade(_cfg(url), "head")
    tables = set(inspect(create_engine(url)).get_table_names())
    assert {"products", "sale_items", "stock_movements", "invoice_payments", "recurring_expenses",
            "collection_scores", "product_scores", "recommendations", "action_logs"} <= tables
    cols = {c["name"] for c in inspect(create_engine(url)).get_columns("invoices")}
    assert "amount_paid" in cols


def test_migration_upgrades_a_pre_migration_database(tmp_path):
    """A database made before migrations (baseline tables, no alembic_version) keeps its rows."""
    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    command.upgrade(_cfg(url), "0001")
    eng = create_engine(url)
    with eng.begin() as c:
        c.execute(text("DROP TABLE alembic_version"))
        c.execute(text("INSERT INTO users (id, name, email, password_hash, failed_logins, created_at) "
                       "VALUES (1, 'Old', 'old@example.com', 'x', 0, '2026-01-01')"))
    command.stamp(_cfg(url), app_db.BASELINE_REVISION)
    command.upgrade(_cfg(url), "head")
    with eng.connect() as c:
        assert c.execute(text("select email from users")).scalar() == "old@example.com"
        head = ScriptDirectory.from_config(_cfg(url)).get_current_head()
        assert c.execute(text("select version_num from alembic_version")).scalar() == head


def _business(days=120) -> BusinessData:
    d = BusinessData(business_id=1, started_at=TODAY - timedelta(days=900), opening_balance=100_000,
                     cash_threshold=20_000)
    for i in range(days, 0, -1):
        day = TODAY - timedelta(days=i)
        d.transactions.append(Txn(day, 10_000, "income", "Sales"))
        d.transactions.append(Txn(day, 9_000, "expense", "Inventory"))
        if day.day == 1:
            d.transactions.append(Txn(day, 25_000, "expense", "Rent"))
    return d


def test_partial_invoice_counts_only_what_is_left():
    inv = Inv(1, 1, 10_000, TODAY - timedelta(days=20), TODAY + timedelta(days=5), None, amount_paid=4_000)
    assert inv.outstanding == 6_000
    d = _business()
    d.invoices.append(inv)
    fc = forecast.forecast(d, TODAY, 10)
    assert fc["expected_inflows"][0]["amount"] == 6_000


def test_recurring_expense_lands_on_its_day_and_leaves_the_baseline():
    d = _business()
    d.recurring.append(RecurringRow("Shop rent", "Rent", 25_000, 1))
    fc = forecast.forecast(d, TODAY, 30)
    rent_day = [r for r in fc["series"] if r["date"].endswith("-01")][0]
    assert rent_day["expected_outflow"] == 25_000
    # Baseline expense stays near the daily 9,000, not inflated by the monthly rent.
    assert all(r["expense"] < 10_500 for r in fc["series"])


def test_new_credit_collections_start_after_the_usual_lag():
    d = _business()
    for k in range(9):  # invoices paid 20 days after issue, 3,000 each (all paid before today)
        issue = TODAY - timedelta(days=80 - 7 * k)
        d.invoices.append(Inv(100 + k, 1, 3_000, issue, issue + timedelta(days=15), issue + timedelta(days=20)))
        d.transactions.append(Txn(issue + timedelta(days=20), 3_000, "income", "Invoice payment"))
    per_day, lag = forecast.new_credit_collections(d, TODAY)
    assert lag == 20 and round(per_day) == round(27_000 / 90)
    fc = forecast.forecast(d, TODAY, 30)
    assert fc["series"][2]["income"] < fc["series"][-1]["income"]


def test_outlier_capping():
    values = [100.0] * 30 + [5_000.0]
    assert max(forecast._cap_outliers(values)) < 5_000


def test_partial_payment_endpoint(client):
    from tests.test_api import signup
    h = signup(client, "partial@example.com")
    cust = client.post("/customers", headers=h, json={"name": "Part Payer"}).json()
    inv = client.post("/invoices", headers=h, json={"customer_id": cust["id"], "amount": 10_000,
                                                    "issue_date": "2026-10-01", "due_date": "2026-10-15"}).json()
    r = client.post(f"/invoices/{inv['id']}/payments", headers=h, json={"amount": 4_000}).json()
    assert r["status"] == "partial" and r["amount_paid"] == 4_000
    assert client.post(f"/invoices/{inv['id']}/payments", headers=h, json={"amount": 7_000}).status_code == 422
    open_rows = client.get("/invoices?status=open", headers=h).json()
    assert open_rows[0]["outstanding"] == 6_000
    done = client.patch(f"/invoices/{inv['id']}/paid", headers=h).json()
    assert done["status"] == "paid" and done["amount_paid"] == 10_000


def test_seed_covers_the_edge_cases(seeded):
    from sqlalchemy import func

    from app.db import SessionLocal
    from app.models import Customer, Invoice, InvoicePayment, Product, RecurringExpense, SaleItem
    db = SessionLocal()
    try:
        fresh = db.query(Customer).filter(Customer.name == "Fresh Mart").one()
        assert db.query(Invoice).filter(Invoice.customer_id == fresh.id, Invoice.status == "paid").count() == 0
        honey = db.query(Product).filter(Product.name == "Organic Honey 500g").one()
        assert db.query(SaleItem).filter(SaleItem.product_id == honey.id).count() == 0 and honey.stock_qty > 0
        cutoff = date.today() - timedelta(days=60)
        for name in ("Imported Olive Oil 1L", "Glass Jar Set"):
            p = db.query(Product).filter(Product.name == name).one()
            last = db.query(func.max(SaleItem.date)).filter(SaleItem.product_id == p.id).scalar()
            assert last < cutoff and p.stock_qty > 0
        assert db.query(Invoice).filter(Invoice.status == "partial").count() >= 1
        assert db.query(InvoicePayment.invoice_id).group_by(InvoicePayment.invoice_id) \
            .having(func.count() > 1).count() > 0
        assert db.query(RecurringExpense).count() == 4
        assert db.query(SaleItem).filter(SaleItem.date > date.today()).count() == 0
        assert seeded["first_shortage"] and abs(seeded["first_shortage"]["gap"] - 12_000) < 500
    finally:
        db.close()
