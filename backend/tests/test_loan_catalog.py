"""The eight loan types every business sees, and how a credit score and repayment capacity decide which it can take."""

from app.engines.loan import emi, evaluate
from app.loan_catalog import LOAN_TYPES
from tests.test_api import signup

KEYS = ("name", "lender", "kind", "min_amount", "max_amount", "rate", "tenure_months", "min_score")


def product(i, **over):
    return {**dict(zip(KEYS, LOAN_TYPES[i])), "id": i + 1, **over}


def test_the_catalog_has_eight_types_and_better_scores_get_cheaper_loans():
    assert len(LOAN_TYPES) == 8 and len({t[0] for t in LOAN_TYPES}) == 8
    by_score = sorted(LOAN_TYPES, key=lambda t: t[7])
    assert len({t[7] for t in LOAN_TYPES}) == 8                 # eight different score requirements
    rates = [t[5] for t in by_score]
    assert rates == sorted(rates, reverse=True)                 # the higher the score needed, the lower the rate
    assert all(t[3] < t[4] for t in LOAN_TYPES)                 # a minimum below the maximum


def test_every_database_has_the_catalog_exactly_once(client):
    from app.db import SessionLocal
    from app.models import LoanProduct
    db = SessionLocal()
    try:
        names = sorted(p.name for p in db.query(LoanProduct).all())
    finally:
        db.close()
    assert names == sorted(t[0] for t in LOAN_TYPES)


def test_evaluate_decides_by_score_then_by_capacity():
    p = product(7)                                              # SME Term Loan, needs score 700
    low = evaluate(p, 640, 5_000)
    assert low["status"] == "score_too_low" and low["points_needed"] == 60 and "60 points to go" in low["reason"]
    tight = evaluate(p, 720, 10)
    assert tight["status"] == "capacity_too_low" and tight["monthly_needed"] == round(emi(p["min_amount"], p["rate"], p["tenure_months"]))
    ok = evaluate(p, 720, 5_000)
    assert ok["status"] == "eligible" and p["min_amount"] <= ok["recommended_amount"] <= p["max_amount"]
    assert ok["monthly_installment"] <= 5_000 + 1                # never more than the safe installment
    exact = evaluate(p, 700, 5_000)                              # the score equal to the minimum is enough
    assert exact["status"] == "eligible"


def test_a_new_business_sees_all_eight_and_none_are_open_yet(client):
    h = signup(client, "loan-new@example.com")
    r = client.get("/loan/recommendations", headers=h).json()
    assert len(r["catalog"]) == 8 and r["options"] == []
    assert all(c["status"] == "score_too_low" and c["points_needed"] > 0 for c in r["catalog"])
    assert [c["min_score"] for c in r["catalog"]] == sorted(c["min_score"] for c in r["catalog"])   # easiest first


def test_the_demo_business_is_eligible_only_where_its_score_allows(client, demo_headers):
    r = client.get("/loan/recommendations", headers=demo_headers).json()
    score = r["score"]
    assert len(r["catalog"]) == 8
    for c in r["catalog"]:
        if c["status"] == "eligible":
            assert c["min_score"] <= score and c["min_amount"] <= c["recommended_amount"] <= c["max_amount"]
        elif c["status"] == "score_too_low":
            assert c["min_score"] > score
        else:
            assert c["min_score"] <= score and c["monthly_needed"] > r["safe_monthly_installment"]
    order = {"eligible": 0, "capacity_too_low": 1, "score_too_low": 2}
    assert [order[c["status"]] for c in r["catalog"]] == sorted(order[c["status"]] for c in r["catalog"])
    assert [o["product_id"] for o in r["options"]] == [c["product_id"] for c in r["catalog"] if c["status"] == "eligible"]
