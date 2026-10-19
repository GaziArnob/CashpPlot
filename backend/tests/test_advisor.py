"""AI explanation layer (grounded, template fallback) and the daily job with its alert."""

import json
from datetime import datetime

import pytest

from app.ai import explainer, providers
from app.ai.tools import Aliaser
from app.jobs import scheduler

FACTS = {
    "currency": "USD",
    "cash": {"balance_today": 65000, "safety_threshold": 20000, "lowest_balance_next_30_days": -121618,
             "lowest_balance_date": "2026-11-06"},
    "cash_gap": {"first_short_date": "2026-10-26", "short_by_on_that_date": 12003,
                 "largest_gap_next_30_days": 141618, "days_below_threshold": 22},
    "plan": {"expected_cash_from_needed_steps": 162729, "gap_covered": True, "still_missing": 0,
             "needed_steps": [{"kind": "collect", "what": "collect from 4 customers", "cash_impact": 59184,
                               "days_to_impact": 7, "risk": "low"}]},
    "top_collections": [{"customer": "Customer C2", "owes": 39995, "days_overdue": 45,
                         "chance_pays_within_7_days_pct": 92, "suggested_action": "Call today"}],
    "products": {"stars": ["Sunflower Oil 1L"], "dead_stock": ["Glass Jar Set"],
                 "cash_stuck_in_slow_and_dead_stock": 96240, "cash_freed_if_cleared": 58380,
                 "spare_cash_for_scaling_up": 0},
}


@pytest.fixture
def alias():
    a = Aliaser()
    a.customer(2, "Summit Wholesale")
    return a


@pytest.fixture(autouse=True)
def clear_cache():
    explainer._cache.clear()


def fake_llm(monkeypatch, text, provider="fake"):
    monkeypatch.setattr(providers, "chat", lambda messages, tools=None, mode="cloud": providers.LLMResult(text=text, provider=provider))


def test_template_summary_english():
    text = explainer.template_summary(FACTS)
    assert "$12,003" in text and "Oct 26" in text and "$141,618" in text and "Customer C2" in text


def test_template_summary_without_gap():
    facts = {**FACTS, "cash_gap": None, "plan": {**FACTS["plan"], "needed_steps": []}}
    assert "No cash shortage" in explainer.template_summary(facts)


def test_grounded_answer_is_used_and_names_restored(monkeypatch, alias):
    fake_llm(monkeypatch, "Cash may fall $12,003 short on Oct 26. Call Customer C2 about $39,995 first.")
    r = explainer.explain(FACTS, alias, "k")
    assert r["generated_by"] == "fake" and not r["llm_rejected"]
    assert "Summit Wholesale" in r["text"] and "Customer C2" not in r["text"]


def test_invented_number_is_rejected(monkeypatch, alias):
    fake_llm(monkeypatch, "You will be short by $55,000 next week.")  # 55,000 is not in the facts
    r = explainer.explain(FACTS, alias, "k")
    assert r["generated_by"] == "template" and r["llm_rejected"]
    assert "12,003" in r["text"] and "Summit Wholesale" in r["text"]


def test_mistyped_digit_is_rejected(monkeypatch, alias):
    fake_llm(monkeypatch, "Collect $39,955 from Customer C2.")  # real figure is 39,995
    assert explainer.explain(FACTS, alias, "k")["llm_rejected"]
    explainer._cache.clear()
    fake_llm(monkeypatch, "You may be about $12,000 short on Oct 26.")  # plain rounding is fine
    assert explainer.explain(FACTS, alias, "k")["generated_by"] == "fake"


def test_no_llm_falls_back_to_template(monkeypatch, alias):
    def unavailable(messages, tools=None, mode="cloud"):
        raise providers.NoLLMAvailable("none")
    monkeypatch.setattr(providers, "chat", unavailable)
    r = explainer.explain(FACTS, alias, "k")
    assert r["generated_by"] == "template" and not r["llm_rejected"]


def test_answers_are_cached(monkeypatch, alias):
    calls = []

    def counting(messages, tools=None, mode="cloud"):
        calls.append(1)
        return providers.LLMResult(text="Cash may fall $12,003 short.", provider="fake")
    monkeypatch.setattr(providers, "chat", counting)
    explainer.explain(FACTS, alias, "k")
    explainer.explain(FACTS, alias, "k")
    assert len(calls) == 1


def test_advisor_summary_api(client, demo_headers):
    en = client.get("/cash-advisor/summary", headers=demo_headers).json()
    assert en["advice"]["text"] and en["advice"]["generated_by"]
    assert en["gap_card"]["first_shortage"] and len(en["forecast"]) == 30
    assert en["plan"]["actions"] and en["products"]["items"] and en["collections"]
    facts = json.dumps(en["facts"])
    for c in en["collections"]:
        assert c["customer_name"] not in facts  # real names never go into the LLM input


def test_daily_job_alerts_once_a_day(client, demo_headers):
    from pathlib import Path

    from app.config import get_settings
    from app.db import SessionLocal
    from app.models import AuditLog, Notification
    first = client.post("/jobs/daily/run", headers=demo_headers).json()
    second = client.post("/jobs/daily/run", headers=demo_headers).json()
    assert first["cash_crunch"] and first["alert_sent"] and "Cash crunch ahead" in first["alert_message"]
    assert second["alert_sent"] is False and second["customers_scored"] == first["customers_scored"]
    db = SessionLocal()
    try:
        assert db.query(Notification).filter(Notification.type == "cash_shortage").count() == 1
        assert db.query(AuditLog).filter(AuditLog.action == "alert_sent").count() == 1
    finally:
        db.close()
    lines = Path(get_settings().alerts_log_path).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["subject"] == "Cash crunch predicted"


def test_daily_job_without_crunch_sends_nothing(client):
    from tests.test_api import signup
    h = signup(client, "nocrunch@example.com")
    r = client.post("/jobs/daily/run", headers=h).json()
    assert r["cash_crunch"] is None and r["alert_sent"] is False


def test_scheduler_timing():
    assert scheduler.seconds_until(7, datetime(2026, 10, 17, 6, 0)) == 3600
    assert scheduler.seconds_until(7, datetime(2026, 10, 17, 8, 0)) == 23 * 3600
