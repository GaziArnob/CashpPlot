"""Demo data: one year of a small wholesale grocery business, relative to today.

Run from the backend folder:  python -m seed.seed   (resets the database through migrations)
Demo login: demo@example.com / Demo@12345

What the data is built to show:
- A cash shortage of about 12,000 nine days ahead (a large supplier bill).
- Harbor Market 10 days overdue, Summit Wholesale 45 days overdue, Parker & Sons paying in parts,
  a brand-new customer with no history.
- Products in every class: stars, cash cows, slow movers, dead stock, and a new product with no sales.
- Every sale is recorded per product: cash lines roll up into the day's "Sales" transaction,
  credit lines belong to invoices. Stock purchases and sales move stock.
"""

import math
import random
from collections import defaultdict
from datetime import date, datetime, timedelta

from app.db import SessionLocal, reset_db
from app.engines import credit as credit_engine, data as engine_data, forecast as forecast_engine
from app.engines.loan import emi
from app.models import (Bill, Business, CreditScore, Customer, FinancingOffer, Goal, Invoice, InvoicePayment, Loan,
                        LoanProduct, Product, RecurringExpense, Repayment, SaleItem, StockMovement, Supplier,
                        Transaction, User)
from app.security import hash_password

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "Demo@12345"
TARGET_BALANCE = 65_000
THRESHOLD = 20_000
SHORTAGE_GAP = 12_000
SHORTAGE_DAY = 9

# name, sku, unit cost, unit price, mean units sold per day, profile
# profile: star | cow | slow | dead:<days since last sale> | new
PRODUCTS = [
    ("Premium Rice 5kg", "RICE-B5", 560, 760, 9.0, "star"),
    ("Sunflower Oil 1L", "OIL-M1", 185, 255, 14.0, "star"),
    ("Spice Mix Pack", "SPC-MX", 75, 125, 20.0, "star"),
    ("Sugar 1kg", "SUG-1", 118, 127, 25.0, "cow"),
    ("Red Lentils 1kg", "DAL-M1", 128, 141, 18.0, "cow"),
    ("Soybean Oil 5L", "OIL-S5", 820, 870, 6.0, "cow"),
    ("Wheat Flour 2kg", "ATT-2", 105, 117, 12.0, "cow"),
    ("Clarified Butter 500g", "GHE-5", 520, 650, 0.5, "slow"),
    ("Baby Formula 400g", "BBF-4", 760, 850, 0.4, "slow"),
    ("Premium Dates 1kg", "DAT-1", 900, 1150, 0.3, "slow"),
    ("Imported Olive Oil 1L", "OIL-O1", 1050, 1350, 0.4, "dead:80"),
    ("Glass Jar Set", "JAR-6", 420, 560, 0.3, "dead:110"),
    ("Organic Honey 500g", "HON-5", 480, 620, 0.0, "new"),
]
STOCK_DAYS = {"star": 7, "cow": 7, "slow": 60}   # restock target, in days of demand
START_STOCK_DAYS = {"star": 10, "cow": 10, "slow": 150, "dead": 400}
CREDIT_PRODUCTS = ["Sugar 1kg", "Red Lentils 1kg", "Soybean Oil 5L", "Wheat Flour 2kg", "Sunflower Oil 1L",
                   "Premium Rice 5kg"]

CUSTOMERS = [
    # name, phone, behavior, typical invoice
    ("Harbor Market", "555-0001", "slow", 15_000),
    ("Summit Wholesale", "555-0002", "bad", 22_000),
    ("Maple Mart", "555-0003", "good", 9_000),
    ("Bright Traders", "555-0004", "good", 12_000),
    ("Corner Grocery", "555-0005", "slow", 7_000),
    ("Lakeview Supermarket", "555-0006", "good", 18_000),
    ("Parker & Sons", "555-0007", "partial", 11_000),
    ("Green Valley Restaurant", "555-0008", "good", 14_000),
    ("Joy Bakery", "555-0009", "bad", 6_000),
    ("Ruby General Store", "555-0010", "good", 8_000),
]
SUPPLIERS = [
    # name, phone, payment terms (days), early-pay discount % and window (days), late fee % per month
    ("Northwind Distributors", "555-0001", 30, 2.0, 10, 1.5),
    ("Fresh Foods Ltd", "555-0002", 15, None, None, 2.0),
    ("City Packaging", "555-0003", 30, None, None, None),
    ("Pioneer Oil Mills", "555-0004", 21, 1.0, 7, 1.0),
]
# Demo financing products for comparisons. Clearly not real offers.
FINANCING_OFFERS = [
    # provider, name, kind, advance %, fee %, monthly rate %, min, max, max days, lead days
    ("Demo Factor Co.", "Invoice advance (demo)", "invoice_financing", 80.0, 1.0, 1.5, 5_000, 500_000, 90, 2),
    ("Demo Bank", "Short-term working capital (demo)", "short_term_loan", None, 1.0, 1.2, 25_000, 1_000_000, 180, 7),
    ("Demo Bank", "Business overdraft (demo)", "overdraft", None, 0.5, 1.8, 0, 200_000, 60, 1),
    ("Demo MFI", "Quick trade loan (demo)", "short_term_loan", None, 1.5, 2.0, 10_000, 300_000, 90, 3),
]
RECURRING = [
    # name, category, amount, day of month
    ("Shop rent", "Rent", 25_000, 1),
    ("Staff salaries", "Salaries", 30_000, 5),
    ("Electricity and internet", "Utilities", 4_500, 10),
    ("Owner's monthly withdrawal", "Owner drawings", 75_000, 28),
]


def add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, 28))


def noise(rng: random.Random, sd: float = 0.15) -> float:
    return math.exp(rng.gauss(0, sd))


def units(rng: random.Random, mean: float) -> int:
    """Whole units sold in a day, roughly Poisson around the mean."""
    if mean <= 0:
        return 0
    if mean < 2:
        return sum(1 for _ in range(4) if rng.random() < mean / 4)
    return max(0, round(rng.gauss(mean, math.sqrt(mean))))


class Shop:
    """Keeps stock levels while the seed walks through the year."""

    def __init__(self, db, bid: int, products: list[Product], profiles: dict[int, str], means: dict[int, float]):
        self.db, self.bid = db, bid
        self.products = products
        self.profile = profiles
        self.mean = means
        self.stock = {p.id: 0.0 for p in products}
        self.sold_today: dict[tuple, float] = defaultdict(float)

    def sell(self, p: Product, d: date, qty: float, payment: str, invoice_id: int | None = None) -> float:
        qty = min(qty, self.stock[p.id])  # can't sell what isn't on the shelf
        if qty <= 0:
            return 0.0
        self.stock[p.id] -= qty
        self.sold_today[(p.id, d)] += qty
        self.db.add(SaleItem(business_id=self.bid, product_id=p.id, date=d, qty=qty, unit_price=p.unit_price,
                             unit_cost=p.unit_cost, payment_type=payment, invoice_id=invoice_id))
        return qty * p.unit_price

    def buy(self, p: Product, d: date, qty: float) -> float:
        if qty <= 0:
            return 0.0
        self.stock[p.id] += qty
        self.db.add(StockMovement(business_id=self.bid, product_id=p.id, date=d, qty=qty,
                                  unit_cost=p.unit_cost, reason="purchase"))
        return qty * p.unit_cost

    def flush_sale_movements(self):
        for (pid, d), qty in self.sold_today.items():
            self.db.add(StockMovement(business_id=self.bid, product_id=pid, date=d, qty=-qty, reason="sale"))
        self.sold_today.clear()


def seed(today: date | None = None, rng_seed: int = 42) -> dict:
    today = today or date.today()
    rng = random.Random(rng_seed)
    start = today - timedelta(days=365)

    reset_db()
    db = SessionLocal()

    user = User(name="Alex Morgan", email=DEMO_EMAIL, phone="555-0000", password_hash=hash_password(DEMO_PASSWORD))
    db.add(user)
    db.flush()
    biz = Business(user_id=user.id, name="Evergreen Traders", type="Wholesale grocery",
                   started_at=today - timedelta(days=4 * 365 + 40), opening_balance=0,
                   cash_threshold=THRESHOLD, currency="USD", plan="pro")
    db.add(biz)
    db.flush()
    bid = biz.id

    def txn(d, amount, kind, category, desc=None, source="manual"):
        if amount > 0:
            db.add(Transaction(business_id=bid, date=d, amount=round(amount, 2), type=kind, category=category,
                               description=desc, source=source))

    # Products, with opening stock.
    products, profiles, means = [], {}, {}
    for name, sku, cost, price, mean, profile in PRODUCTS:
        created = today - timedelta(days=4) if profile == "new" else start - timedelta(days=30)
        p = Product(business_id=bid, name=name, sku=sku, unit_cost=cost, unit_price=price, stock_qty=0,
                    created_at=datetime.combine(created, datetime.min.time()))
        db.add(p)
        db.flush()
        products.append(p)
        profiles[p.id], means[p.id] = profile, mean
    by_name = {p.name: p for p in products}
    shop = Shop(db, bid, products, profiles, means)
    for p in products:
        kind = profiles[p.id].split(":")[0]
        if kind == "new":
            continue
        opening_qty = round(START_STOCK_DAYS[kind] * max(means[p.id], 0.2))
        db.add(StockMovement(business_id=bid, product_id=p.id, date=start, qty=opening_qty,
                             unit_cost=p.unit_cost, reason="adjustment"))
        shop.stock[p.id] = opening_qty

    for name, category, amount, day in RECURRING:
        db.add(RecurringExpense(business_id=bid, name=name, category=category, amount=amount, day_of_month=day))

    # Daily cash sales (per product), restocking and operating expenses.
    dow = [1.0, 0.95, 1.0, 1.05, 1.4, 1.2, 0.9]  # Mon..Sun
    d = start
    while d <= today:
        season = 1 + 0.05 * math.sin(2 * math.pi * (d.timetuple().tm_yday - 80) / 365)
        cash_total = 0.0
        for p in products:
            profile = profiles[p.id]
            if profile == "new":
                continue
            if profile.startswith("dead") and (today - d).days < int(profile.split(":")[1]):
                continue  # dead stock: no sales in the recent window
            cash_total += shop.sell(p, d, units(rng, means[p.id] * dow[d.weekday()] * season), "cash")
        txn(d, cash_total, "income", "Sales", "Cash sales")

        if True:  # top up stock every day, paid in cash (keeps cash swings realistic)
            cost = 0.0
            for p in products:
                kind = profiles[p.id]
                if kind in STOCK_DAYS:
                    target = STOCK_DAYS[kind] * means[p.id]
                    cost += shop.buy(p, d, max(0, round(target - shop.stock[p.id])))
            txn(d, cost, "expense", "Inventory", "Stock purchase (cash)")

        recent = (today - d).days < 30
        txn(d, 380 * (1.45 if recent else 1.0) * noise(rng, 0.25), "expense", "Transport", "Delivery van")
        if rng.random() < 0.3:
            txn(d, rng.uniform(300, 1_500), "expense", "Miscellaneous", "Shop supplies")
        for name, category, amount, day in RECURRING:
            if d.day == day:
                actual = amount * noise(rng, 0.1) if category == "Utilities" else amount
                txn(d, actual, "expense", category, name)
        d += timedelta(days=1)

    # Customers and credit sales. Each invoice is built from product lines.
    def credit_invoice(customer: Customer, issue: date, due: date, target: float) -> Invoice:
        inv = Invoice(business_id=bid, customer_id=customer.id, amount=0, issue_date=issue, due_date=due,
                      status="unpaid")
        db.add(inv)
        db.flush()
        picks = rng.sample(CREDIT_PRODUCTS, k=rng.randint(1, 3))
        total = 0.0
        for i, name in enumerate(picks):
            p = by_name[name]
            share = target / len(picks)
            qty = max(1, round(share / p.unit_price))
            shop.stock[p.id] += qty  # bought in for this order, so it never goes negative
            db.add(StockMovement(business_id=bid, product_id=p.id, date=issue, qty=qty,
                                 unit_cost=p.unit_cost, reason="purchase"))
            txn(issue, qty * p.unit_cost, "expense", "Inventory", f"Stock for invoice #{inv.id}")
            total += shop.sell(p, issue, qty, "credit", inv.id)
        inv.amount = round(total, 2)
        return inv

    def pay(inv: Invoice, when: date, amount: float):
        db.add(InvoicePayment(business_id=bid, invoice_id=inv.id, date=when, amount=round(amount, 2)))
        txn(when, amount, "income", "Invoice payment", f"Payment for invoice #{inv.id}", "system")
        inv.amount_paid = round((inv.amount_paid or 0) + amount, 2)
        if inv.amount_paid >= inv.amount - 0.005:
            inv.status, inv.paid_date = "paid", when
        else:
            inv.status = "partial"

    customers = {}
    for name, phone, behavior, typical in CUSTOMERS:
        c = Customer(business_id=bid, name=name, phone=phone)
        db.add(c)
        db.flush()
        customers[name] = c
        issue = start + timedelta(days=rng.randint(0, 20))
        while issue < today - timedelta(days=20):
            due = issue + timedelta(days=15)
            inv = credit_invoice(c, issue, due, typical * noise(rng, 0.25))
            delay = {"good": rng.randint(-5, 2), "slow": rng.randint(3, 20),
                     "bad": rng.randint(15, 45), "partial": rng.randint(0, 12)}[behavior]
            paid = due + timedelta(days=delay)
            if behavior == "partial":
                first = due + timedelta(days=rng.randint(-2, 4))  # half first, the rest later
                if first < today:
                    pay(inv, first, inv.amount * 0.5)
                if paid + timedelta(days=10) < today:
                    pay(inv, paid + timedelta(days=10), inv.amount - inv.amount_paid)
            elif paid < today:
                pay(inv, paid, inv.amount)
            issue += timedelta(days=rng.randint(20, 35))

    # The demo story.
    rahim = credit_invoice(customers["Harbor Market"], today - timedelta(days=25), today - timedelta(days=10), 15_000)
    rahim.note = "Festival order"
    credit_invoice(customers["Summit Wholesale"], today - timedelta(days=60), today - timedelta(days=45), 22_000)
    kabir = credit_invoice(customers["Parker & Sons"], today - timedelta(days=30), today - timedelta(days=15), 12_000)
    pay(kabir, today - timedelta(days=12), kabir.amount * 0.4)  # paid 40%, the rest still open
    for name, days_ahead, amount in [("Lakeview Supermarket", 6, 18_500), ("Maple Mart", 12, 9_200),
                                     ("Green Valley Restaurant", 18, 14_000), ("Bright Traders", 24, 12_300)]:
        issue = min(today + timedelta(days=days_ahead - 15), today - timedelta(days=rng.randint(2, 9)))  # past only
        credit_invoice(customers[name], issue, today + timedelta(days=days_ahead), amount)
    # A brand-new customer: one open invoice, no payment history at all.
    fresh = Customer(business_id=bid, name="Fresh Mart", phone="555-0011",
                     created_at=datetime.combine(today - timedelta(days=5), datetime.min.time()))
    db.add(fresh)
    db.flush()
    credit_invoice(fresh, today - timedelta(days=5), today + timedelta(days=10), 6_500)

    # Suppliers and bills (credit purchases), paid mostly on time.
    supplier_ids = {}
    for name, phone, terms, disc, disc_days, late_fee in SUPPLIERS:
        s = Supplier(business_id=bid, name=name, phone=phone, payment_terms_days=terms,
                     early_pay_discount_pct=disc, early_pay_within_days=disc_days, late_fee_pct_month=late_fee)
        db.add(s)
        db.flush()
        supplier_ids[name] = s.id
    for k in range(1, 12):
        for name, base in [("Fresh Foods Ltd", 9_000), ("City Packaging", 5_000), ("Pioneer Oil Mills", 7_000)]:
            due = add_months(start, k).replace(day=20)
            if due >= today:
                continue
            amount = round(base * noise(rng, 0.15), -2)
            paid = due + timedelta(days=rng.choice([0, 0, 0, -1, -2, 4]))
            db.add(Bill(business_id=bid, supplier_id=supplier_ids[name], amount=amount, due_date=due,
                        paid_date=paid, status="paid"))
            txn(paid, amount, "expense", "Bill payment", f"Bill from {name}", "system")
    for name, days_ahead, amount in [("City Packaging", 4, 5_200), ("Pioneer Oil Mills", 16, 7_400),
                                     ("Fresh Foods Ltd", 22, 9_800)]:
        db.add(Bill(business_id=bid, supplier_id=supplier_ids[name], amount=amount,
                    due_date=today + timedelta(days=days_ahead), status="unpaid"))

    # Loans: one closed, one active.
    def make_loan(lender, principal, rate, months, start_date, late_index=None):
        m = emi(principal, rate, months)
        loan = Loan(business_id=bid, lender=lender, principal=principal, rate=rate, tenure_months=months,
                    start_date=start_date, emi=m)
        db.add(loan)
        db.flush()
        all_paid = True
        for k in range(1, months + 1):
            due = add_months(start_date, k)
            if due < today:
                paid = due + timedelta(days=6 if k == late_index else 0)
                db.add(Repayment(business_id=bid, loan_id=loan.id, due_date=due, paid_date=paid, amount=m))
                txn(paid, m, "expense", "Loan repayment", f"Installment to {lender}", "system")
            else:
                all_paid = False
                db.add(Repayment(business_id=bid, loan_id=loan.id, due_date=due, amount=m))
        loan.status = "closed" if all_paid else "active"

    make_loan("Lotus Microfinance", 200_000, 20.0, 10, add_months(start, -1), late_index=4)
    make_loan("Summit Bank", 150_000, 13.0, 18, add_months(today, -6))

    for o in FINANCING_OFFERS:
        db.add(FinancingOffer(provider=o[0], name=o[1], kind=o[2], advance_rate_pct=o[3], fee_pct=o[4],
                              monthly_rate_pct=o[5], min_amount=o[6], max_amount=o[7], max_days=o[8],
                              lead_days=o[9], is_demo=True))
    # The loan catalog already exists: migration 0007 inserts it into any empty database.
    db.add(Goal(business_id=bid, title="Emergency cash reserve", target_amount=200_000, current_amount=65_000,
                deadline=add_months(today, 6)))
    db.add(Goal(business_id=bid, title="Second delivery van", target_amount=600_000, current_amount=120_000,
                deadline=add_months(today, 14)))

    # Stock on hand today; the new product arrives with its first delivery.
    shop.flush_sale_movements()
    honey = by_name["Organic Honey 500g"]
    shop.buy(honey, today - timedelta(days=4), 30)
    txn(today - timedelta(days=4), 30 * honey.unit_cost, "expense", "Inventory", "First stock of Organic Honey")
    for p in products:
        p.stock_qty = round(shop.stock[p.id], 2)
    db.commit()

    # Calibrate: set the opening balance so today's balance is TARGET_BALANCE.
    data = engine_data.load(db, biz)
    biz.opening_balance = round(TARGET_BALANCE - (data.balance_on(today) - data.opening_balance))
    db.commit()

    # Add the large supplier bill that creates a shortage of about SHORTAGE_GAP, around SHORTAGE_DAY days out.
    # The story needs the bill itself to cause the first shortage, so pick the latest day (SHORTAGE_DAY or
    # earlier) where cash is still comfortably above the safety level the day before; that keeps the demo
    # right whatever day of the month it is seeded on (fixed rent, salaries and drawings land on fixed dates).
    data = engine_data.load(db, biz)
    fc = forecast_engine.forecast(data, today, 30)
    series = fc["series"]
    chosen_day, big_bill = SHORTAGE_DAY, 20_000
    for day in range(SHORTAGE_DAY, 2, -1):
        before_ok = all(r["balance"] > THRESHOLD + SHORTAGE_GAP for r in series[:day - 1])
        room = series[day - 1]["balance"] - THRESHOLD + SHORTAGE_GAP
        if before_ok and room >= 10_000:
            chosen_day, big_bill = day, round(room, -2)
            break
    db.add(Bill(business_id=bid, supplier_id=supplier_ids["Northwind Distributors"], amount=big_bill,
                due_date=today + timedelta(days=chosen_day), status="unpaid", note="Festival stock order"))
    db.commit()

    # Monthly credit score history for the trend chart.
    data = engine_data.load(db, biz)
    for k in range(6, 0, -1):
        as_of = add_months(today, -k + 1).replace(day=1) - timedelta(days=1)
        c = credit_engine.score(data, as_of)
        db.add(CreditScore(business_id=bid, score=c["score"], band=c["band"], factors={"factors": c["factors"]},
                           calculated_at=datetime.combine(as_of, datetime.min.time())))
    db.commit()

    data = engine_data.load(db, biz)
    fc = forecast_engine.forecast(data, today, 30)
    summary = {
        "transactions": len(data.transactions),
        "products": len(products),
        "sale_items": db.query(SaleItem).count(),
        "customers": len(data.customers),
        "invoices": len(data.invoices),
        "partial_invoices": db.query(Invoice).filter(Invoice.status == "partial").count(),
        "bills": len(data.bills),
        "opening_balance": biz.opening_balance,
        "balance_today": round(data.balance_on(today)),
        "big_bill": big_bill,
        "first_shortage": fc["first_shortage"],
        "credit_score": credit_engine.score(data, today)["score"],
    }
    db.close()
    return summary


if __name__ == "__main__":
    result = seed()
    for k, v in result.items():
        print(f"{k}: {v}")
    print(f"\nDemo login: {DEMO_EMAIL} / {DEMO_PASSWORD}")
