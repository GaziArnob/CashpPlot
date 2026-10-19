"""Runs the engines for one business. Shared by the API routes and the AI agent's tools."""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import notify, plans
from app.ai.templates import day, money
from app.engines import (collection, credit, data as engine_data, forecast, insights, loan, payables, payables_recommend, planner,
                         products, whatif)
from app.models import (ActionLog, Bill, Business, CollectionScore, CreditScore, FinancingOffer, Invoice, Loan,
                        LoanProduct, Notification, Repayment, PayablesRecommendation, ProductScore, Recommendation, Supplier, utcnow)


def today() -> date:
    return date.today()


def today_start_utc() -> datetime:
    """Local midnight today, as the naive UTC time the database stores (created_at uses UTC)."""
    return datetime.combine(today(), datetime.min.time()).astimezone(timezone.utc).replace(tzinfo=None)


def load(db: Session, business: Business) -> engine_data.BusinessData:
    return engine_data.load(db, business)


def cash_forecast(db: Session, business: Business, days: int = 30) -> dict:
    return forecast.forecast(load(db, business), today(), days)


def collection_scores(db: Session, business: Business, persist: bool = False) -> dict:
    """Ranked receivables with p(pay in 7 days), action and credit limit; optionally snapshotted."""
    d = load(db, business)
    fc = forecast.forecast(d, today(), 30)
    gap = fc["first_shortage"]["gap"] if fc["first_shortage"] else 0.0
    result = collection.score_customers(d, today(), gap)
    result["shortage_gap"] = gap
    if persist:
        db.query(CollectionScore).filter(CollectionScore.business_id == business.id,
                                         CollectionScore.as_of == today()).delete()
        for c in result["customers"]:
            db.add(CollectionScore(
                business_id=business.id, customer_id=c["customer_id"], as_of=today(), score=c["score"],
                p_pay_7d=c["p_pay_7d"], aging_bucket=c["aging_bucket"], recommended_action=c["action"],
                credit_limit=c["credit_limit"],
                features={"weights": c["features"], "history": c["history"], "relationship": c["relationship"],
                          "model": result["model"]["method"]}))
        db.commit()
    return result


def cash_budget(fc: dict) -> float:
    """Spare cash for scaling up: the lowest forecast balance above the safety threshold."""
    return max(0.0, fc["min_balance"]["balance"] - fc["threshold"])


def product_scores(db: Session, business: Business, persist: bool = False) -> dict:
    d = load(db, business)
    fc = forecast.forecast(d, today(), 30)
    result = products.score_products(d, today(), cash_budget(fc))
    result["shortage_gap"] = fc["largest_gap"]
    if persist:
        db.query(ProductScore).filter(ProductScore.business_id == business.id,
                                      ProductScore.as_of == today()).delete()
        for p in result["products"]:
            db.add(ProductScore(
                business_id=business.id, product_id=p["product_id"], as_of=today(),
                product_class=p["product_class"], revenue_30d=p["revenue_30d"], revenue_90d=p["revenue_90d"],
                growth_pct=p["growth_pct"], margin_pct=p["margin_pct"], days_of_stock=p["days_of_stock"],
                turnover=p["turnover"], cash_conversion_days=p["cash_conversion_days"],
                recommended_qty_change=p["recommended_qty_change"],
                features={k: p[k] for k in ("units_30d", "units_90d", "profit_90d", "profit_share_pct",
                                            "cash_share_pct", "credit_collection_days", "cash_impact",
                                            "action")}))
        db.commit()
    return result


def action_plan(db: Session, business: Business) -> dict:
    """Today's plan, recomputed from fresh numbers and synced to the recommendations table.

    An action keeps its id and status across recomputes (matched by kind + target), so something
    marked done stays done. Open actions that no longer apply are removed.
    """
    d = load(db, business)
    fc = forecast.forecast(d, today(), 30)
    plan = planner.build_plan(
        today(), fc,
        collections=collection.score_customers(d, today(), fc["first_shortage"]["gap"] if fc["first_shortage"] else 0)
        ["customers"],
        products=products.score_products(d, today(), cash_budget(fc)),
        insights=insights.spending_insights(d, today()),
        loan=loan.recommend(d, today(), credit.score(d, today()), loan_products(db)),
    )
    existing = {(r.kind, r.target_ref): r for r in db.scalars(select(Recommendation).where(
        Recommendation.business_id == business.id, Recommendation.plan_date == today()))}
    keep = set()
    for a in plan["actions"]:
        key = (a["kind"], a["target_ref"])
        row = existing.get(key)
        if row is None:
            row = Recommendation(business_id=business.id, plan_date=today(), kind=a["kind"],
                                 target_ref=a["target_ref"], status="open")
            db.add(row)
        row.title, row.cash_impact, row.days_to_impact = a["title"], a["cash_impact"], a["days_to_impact"]
        row.risk, row.reasoning, row.rank, row.optional = a["risk"], a["reasoning"], a["rank"], a["optional"]
        row.data = {**a["data"], "lands_after_shortage": a["lands_after_shortage"]}
        keep.add(key)
    for key, row in existing.items():
        if key not in keep:
            if row.status == "open":
                db.delete(row)
            else:
                row.rank = 1000 + row.id  # finished earlier today; listed after the live plan
    db.commit()

    rows = db.scalars(select(Recommendation).where(Recommendation.business_id == business.id,
                                                   Recommendation.plan_date == today())
                      .order_by(Recommendation.rank)).all()
    logs = db.scalars(select(ActionLog).where(ActionLog.business_id == business.id,
                                              ActionLog.recommendation_id.in_([r.id for r in rows]))).all()
    actual = {}
    for log in logs:
        if log.action == "done" and log.actual_amount is not None:
            actual[log.recommendation_id] = log.actual_amount
    actions = [{
        "id": r.id, "rank": r.rank, "kind": r.kind, "title": r.title, "target_ref": r.target_ref,
        "cash_impact": r.cash_impact, "days_to_impact": r.days_to_impact, "risk": r.risk,
        "reasoning": r.reasoning, "optional": r.optional, "status": r.status, "data": r.data,
        "actual_amount": actual.get(r.id),
    } for r in rows]
    summary = {k: v for k, v in plan.items() if k != "actions"}
    summary["done_count"] = sum(1 for a in actions if a["status"] == "done")
    summary["realized_so_far"] = round(sum(a["actual_amount"] or 0 for a in actions if a["status"] == "done"))
    return {**summary, "actions": actions}


def advisor_summary(db: Session, business: Business) -> dict:
    """Everything the Cash Advisor screen needs, plus the advice written from those numbers."""
    from app.ai import explainer
    from app.ai.tools import Aliaser

    plan = action_plan(db, business)
    d = load(db, business)
    fc = forecast.forecast(d, today(), 30)
    collections = collection.score_customers(d, today(), fc["first_shortage"]["gap"] if fc["first_shortage"] else 0)
    prods = products.score_products(d, today(), cash_budget(fc))
    alias = Aliaser()
    facts = explainer.build_facts(fc, plan, collections["customers"], prods, business.currency, alias)
    advice = explainer.explain(facts, alias, cache_key=f"{business.id}:{today().isoformat()}", mode=business.ai_mode)
    return {
        "as_of": today().isoformat(),
        "currency": business.currency,
        "advice": advice,
        "gap_card": {
            "balance": fc["start_balance"], "threshold": fc["threshold"],
            "first_shortage": fc["first_shortage"], "largest_gap": fc["largest_gap"],
            "shortage_days": len(fc["shortages"]), "min_balance": fc["min_balance"],
            "plan_expected": plan["expected_from_plan"], "gap_covered": plan["gap_covered"],
            "remaining_gap": plan["remaining_gap"],
        },
        "forecast": [{"date": r["date"], "balance": r["balance"], "low": r["low"], "high": r["high"],
                      "status": r["status"]} for r in fc["series"]],
        "collections": collections["customers"][:5],
        "collection_model": collections["model"],
        "products": {k: prods[k] for k in ("counts", "thresholds", "cash_budget", "cash_freed_if_cleared",
                                           "cash_tied_in_slow_and_dead")} | {"items": [
            {k: p[k] for k in ("product_id", "name", "product_class", "margin_pct", "turnover", "revenue_90d",
                               "cash_impact", "action")} for p in prods["products"]]},
        "plan": plan,
        "facts": facts,  # the exact JSON the explainer was allowed to use
    }


def supplier_profiles(db: Session, business: Business, d: engine_data.BusinessData) -> dict[int, dict]:
    """Terms and our payment record (share of paid bills settled on or before the due date) per supplier."""
    paid: dict[int, list[bool]] = {}
    for b in db.scalars(select(Bill).where(Bill.business_id == business.id, Bill.paid_date.is_not(None))):
        paid.setdefault(b.supplier_id, []).append(b.paid_date <= b.due_date)
    out = {}
    for s in db.scalars(select(Supplier).where(Supplier.business_id == business.id)):
        record = paid.get(s.id)
        out[s.id] = {"id": s.id, "name": s.name, "payment_terms_days": s.payment_terms_days,
                     "early_pay_discount_pct": s.early_pay_discount_pct,
                     "early_pay_within_days": s.early_pay_within_days, "late_fee_pct_month": s.late_fee_pct_month,
                     "on_time_rate": round(sum(record) / len(record), 2) if record else None,
                     "bills_paid": len(record or [])}
    return out


def financing_offers(db: Session) -> list[dict]:
    return [{"id": o.id, "provider": o.provider, "name": o.name, "kind": o.kind,
             "advance_rate_pct": o.advance_rate_pct, "fee_pct": o.fee_pct, "monthly_rate_pct": o.monthly_rate_pct,
             "min_amount": o.min_amount, "max_amount": o.max_amount, "max_days": o.max_days,
             "lead_days": o.lead_days, "is_demo": o.is_demo} for o in db.scalars(select(FinancingOffer))]


def payables_analysis(db: Session, business: Business, save: bool = False) -> dict:
    """Conflicts, per-bill payment options, financing comparison and the recommendation, in one pass."""
    d = load(db, business)
    t = today()
    cf = payables.dated_cashflow(d, t, 30)
    found = payables.conflicts(cf)
    suppliers = supplier_profiles(db, business, d)
    bills = [{"bill_id": b.id, "supplier_id": b.supplier_id, "supplier": b.supplier_name,
              "outstanding": round(b.outstanding), "amount": round(b.amount), "due_date": b.due_date.isoformat(),
              "plan_id": b.plan_id, "overdue": b.due_date < t}
             for b in d.bills if not b.paid_date and b.outstanding > 0]
    bills.sort(key=lambda b: b["due_date"])
    plans = [payables.bill_options(cf, b, suppliers.get(b["supplier_id"], {})) for b in bills
             if not b["plan_id"]]  # a bill with an accepted plan is already rescheduled
    fin: list[dict] = []
    if found:
        worst = max(found, key=lambda c: c["worst_gap"])
        need_by = date.fromisoformat(found[0]["start"])
        days_needed = (date.fromisoformat(found[-1]["end"]) - need_by).days + 14
        fin = payables.financing_options(t, worst["worst_gap"], need_by, days_needed, financing_offers(db),
                                         cf["receipts"])
    rec = payables_recommend.recommend(cf, plans, fin, suppliers, bills, t)
    result = {"as_of": t.isoformat(), "currency": business.currency, "cashflow": cf, "conflicts": found,
              "upcoming_bills": bills, "suppliers": list(suppliers.values()), "bill_options": plans,
              "financing": fin, "recommendation": rec,
              "at_risk_invoices": [r for r in cf["receipts"] if r["at_risk"]],
              "disclaimer": "Estimates from your data. Financing figures are DEMO offers, not real offers or "
                            "approvals. Nothing is paid, sent or applied for without your approval."}
    if save:
        db.add(PayablesRecommendation(business_id=business.id, shortfall=rec["shortfall"],
                                      shortfall_date=date.fromisoformat(rec["shortfall_date"]) if rec["shortfall_date"] else None,
                                      headline=rec["headline"][:500], total_cost=rec["total_cost"],
                                      payload={"recommendation": rec, "conflicts": found}))
        db.commit()
    return result


def recovery_priority(db: Session, business: Business) -> list[dict]:
    """Ranked customers (used by the dashboard, notifications and the agent)."""
    return collection_scores(db, business)["customers"]


def credit_score(db: Session, business: Business, store: bool = True) -> dict:
    result = credit.score(load(db, business), today())
    if store:
        latest = db.scalar(select(CreditScore).where(CreditScore.business_id == business.id)
                           .order_by(CreditScore.calculated_at.desc()))
        if latest is None or latest.calculated_at.date() != utcnow().date() or latest.score != result["score"]:
            db.add(CreditScore(business_id=business.id, score=result["score"], band=result["band"],
                               factors={"factors": result["factors"]}))
            db.commit()
    return result


def loan_products(db: Session) -> list[dict]:
    return [{"id": p.id, "name": p.name, "lender": p.lender, "kind": p.kind, "min_amount": p.min_amount,
             "max_amount": p.max_amount, "rate": p.rate, "tenure_months": p.tenure_months,
             "min_score": p.min_score} for p in db.scalars(select(LoanProduct))]


def loan_recommendation(db: Session, business: Business) -> dict:
    d = load(db, business)
    c = credit.score(d, today())
    return loan.recommend(d, today(), c, loan_products(db))


def what_if(db: Session, business: Business, **kwargs) -> dict:
    return whatif.simulate(load(db, business), today(), **kwargs)


def spending_insights(db: Session, business: Business) -> list[dict]:
    return insights.spending_insights(load(db, business), today())


def pnl(db: Session, business: Business, year: int, month: int) -> dict:
    return insights.pnl(load(db, business), year, month)


def refresh_notifications(db: Session, business: Business, fc: dict, ranked: list[dict]) -> None:
    """Raise the alerts that apply today. Each thing is raised once per cooldown (see notify.py), so loading the
    dashboard or running the daily job twice does not duplicate anything."""
    cur, t = business.currency, today()
    soon = t + timedelta(days=3)

    if fc["first_shortage"]:
        s = fc["first_shortage"]
        notify.create(db, business, "cash_shortage",
                      f"Cash may fall {money(s['gap'], cur)} below your safety level on {day(s['date'])}.",
                      key=f"shortage:{s['date']}", link="/cashflow", cooldown_days=3)
    for r in ranked:
        if r["max_days_overdue"] > 30:
            notify.create(db, business, "overdue",
                          f"{r['customer_name']} is {r['max_days_overdue']} days overdue on {money(r['outstanding'], cur)}.",
                          key=f"overdue:{r['customer_id']}", link="/ledger", cooldown_days=7)

    for inv in db.scalars(select(Invoice).where(Invoice.business_id == business.id, Invoice.status != "paid",
                                                Invoice.due_date >= t, Invoice.due_date <= soon)):
        notify.create(db, business, "invoice_due",
                      f"{inv.customer.name} owes {money(round(inv.outstanding), cur)}, due {day(inv.due_date.isoformat())}.",
                      key=f"invoice:{inv.id}", link="/ledger", cooldown_days=5)
    for b in db.scalars(select(Bill).where(Bill.business_id == business.id, Bill.status != "paid", Bill.due_date <= soon)):
        late = b.due_date < t
        notify.create(db, business, "bill_due",
                      f"Bill of {money(round(b.outstanding), cur)} to {b.supplier.name} "
                      f"{'was due' if late else 'is due'} {day(b.due_date.isoformat())}.",
                      key=f"bill:{b.id}", link="/payables", cooldown_days=3, severity="critical" if late else None)
    for rep in db.scalars(select(Repayment).where(Repayment.business_id == business.id, Repayment.paid_date.is_(None),
                                                  Repayment.due_date <= soon)):
        loan = db.get(Loan, rep.loan_id)
        if loan is None or loan.status != "active":
            continue
        late = rep.due_date < t
        notify.create(db, business, "loan_due",
                      f"Loan installment of {money(round(rep.amount), cur)} to {loan.lender} "
                      f"{'was due' if late else 'is due'} {day(rep.due_date.isoformat())}.",
                      key=f"loan:{rep.id}", link="/loan", cooldown_days=3, severity="critical" if late else None)

    plan = plans.describe(business)
    if plan["trial"] and plan["days_left"] is not None and plan["days_left"] <= 3:
        notify.create(db, business, "trial",
                      f"Your Pro trial ends in {plan['days_left']} day{'s' if plan['days_left'] != 1 else ''}. "
                      "Choose a plan in Settings to keep every feature.",
                      key="trial_ending", link="/settings#plan", cooldown_days=2)
    elif plan["trial_ended"]:
        notify.create(db, business, "trial", "Your Pro trial has ended, so you are on the Free plan. "
                      "Choose Pro in Settings to get everything back.", key="trial_ended", link="/settings#plan",
                      cooldown_days=30)
    db.commit()
