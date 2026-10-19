"""Dashboard, cash flow, credit score and loan center."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import services
from app.ai import templates
from app.db import get_db
from app import plans
from app.deps import get_business, needs, owned, require_owner
from app.engines.loan import DISCLAIMER, emi
from app.models import Business, CreditScore, Loan, Notification, Repayment, Transaction
from app.schemas import LoanIn, PayIn, WhatIfIn

router = APIRouter(tags=["finance"], dependencies=[Depends(require_owner)])
CREDIT = [Depends(needs("credit"))]


def _add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    day = min(d.day, [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30,
                      31, 31, 30, 31, 30, 31][m - 1])
    return date(y, m, day)


@router.get("/dashboard/summary")
def dashboard(business: Business = Depends(get_business), db: Session = Depends(get_db)):
    today = services.today()
    data = services.load(db, business)
    fc = services.cash_forecast(db, business, 30)
    ranked = services.recovery_priority(db, business)
    credit = services.credit_score(db, business)
    services.refresh_notifications(db, business, fc, ranked)

    month_start = today.replace(day=1)
    inc = sum(t.amount for t in data.transactions if t.type == "income" and t.date >= month_start)
    exp = sum(t.amount for t in data.transactions if t.type == "expense" and t.date >= month_start)
    unread = db.scalars(select(Notification).where(Notification.business_id == business.id,
                                                   Notification.is_read.is_(False))
                        .order_by(Notification.created_at.desc()).limit(5)).all()
    return {
        "business": {"name": business.name, "currency": business.currency},
        "as_of": today.isoformat(),
        "balance": fc["start_balance"],
        "threshold": fc["threshold"],
        "month_to_date": {"income": round(inc), "expense": round(exp), "net": round(inc - exp)},
        "receivables": {"outstanding": sum(r["outstanding"] for r in ranked),
                        "overdue": sum(r["overdue_amount"] for r in ranked),
                        "customers_overdue": sum(1 for r in ranked if r["overdue_amount"] > 0)},
        "cash_alert": fc["first_shortage"],
        "forecast_preview": [{"date": r["date"], "balance": r["balance"], "status": r["status"]}
                             for r in fc["series"][:14]],
        "credit_score": {"score": credit["score"], "band": credit["band"]},
        "top_collections": [{k: r[k] for k in ("customer_id", "customer_name", "overdue_amount",
                                                 "max_days_overdue")} for r in ranked[:3]],
        "summary": templates.daily_summary(fc, ranked, credit, business.currency),
        "notifications": [{"id": n.id, "type": n.type, "message": n.message} for n in unread],
    }


@router.get("/cashflow/forecast")
def cash_forecast(days: int = Query(30, ge=7, le=90), business: Business = Depends(get_business),
                  db: Session = Depends(get_db)):
    if days > plans.FREE_FORECAST_DAYS and not plans.can_use(business, "forecast_long"):
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED,
                            f"Upgrade to Pro to use this: {plans.PRO_FEATURES['forecast_long']}")
    return services.cash_forecast(db, business, days)


@router.get("/cashflow/calendar")
def cash_calendar(days: int = Query(30, ge=7, le=90), business: Business = Depends(get_business),
                  db: Session = Depends(get_db)):
    if days > plans.FREE_FORECAST_DAYS and not plans.can_use(business, "forecast_long"):
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED,
                            f"Upgrade to Pro to use this: {plans.PRO_FEATURES['forecast_long']}")
    fc = services.cash_forecast(db, business, days)
    data = services.load(db, business)
    by_day: dict[str, dict] = {}
    for e in fc["expected_inflows"]:
        day = by_day.setdefault(e["date"], {"date": e["date"], "inflows": [], "outflows": []})
        day["inflows"].append({"what": f"Invoice #{e['invoice_id']} from {data.customers.get(e['customer_id'])}",
                               "amount": e["amount"], "probability": e["probability"]})
    for e in fc["expected_outflows"]:
        day = by_day.setdefault(e["date"], {"date": e["date"], "inflows": [], "outflows": []})
        what = f"Bill to {e['supplier']}" if e["kind"] == "bill" else "Loan installment"
        day["outflows"].append({"what": what, "amount": e["amount"], "overdue": e["overdue"]})
    status = {r["date"]: r for r in fc["series"]}
    for d, day in by_day.items():
        day["projected_balance"] = status[d]["balance"]
        day["status"] = status[d]["status"]
    return {"days": [by_day[k] for k in sorted(by_day)], "currency": business.currency}


@router.get("/credit-score", dependencies=CREDIT)
def credit_score(business: Business = Depends(get_business), db: Session = Depends(get_db)):
    return services.credit_score(db, business)


@router.get("/credit-score/history", dependencies=CREDIT)
def credit_history(business: Business = Depends(get_business), db: Session = Depends(get_db)):
    rows = db.scalars(select(CreditScore).where(CreditScore.business_id == business.id)
                      .order_by(CreditScore.calculated_at)).all()
    return [{"date": r.calculated_at.date().isoformat(), "score": r.score, "band": r.band} for r in rows]


@router.get("/loan/readiness", dependencies=CREDIT)
def loan_readiness(business: Business = Depends(get_business), db: Session = Depends(get_db)):
    r = services.loan_recommendation(db, business)
    return {k: r[k] for k in ("ready", "score", "band", "safe_monthly_installment", "max_recommended_amount",
                              "capacity", "checklist", "disclaimer")}


@router.get("/loan/recommendations", dependencies=CREDIT)
def loan_recommendations(business: Business = Depends(get_business), db: Session = Depends(get_db)):
    r = services.loan_recommendation(db, business)
    return {"options": r["options"], "catalog": r["catalog"], "score": r["score"],
            "safe_monthly_installment": r["safe_monthly_installment"],
            "max_recommended_amount": r["max_recommended_amount"], "disclaimer": r["disclaimer"]}


@router.post("/loan/what-if", dependencies=CREDIT)
def what_if(body: WhatIfIn, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    return services.what_if(db, business, **body.model_dump())


def _loan_row(loan: Loan, reps: list[Repayment], today) -> dict:
    unpaid = [r for r in reps if not r.paid_date]
    return {
        "id": loan.id, "lender": loan.lender, "principal": loan.principal, "rate": loan.rate,
        "tenure_months": loan.tenure_months, "start_date": loan.start_date, "emi": round(loan.emi),
        "status": loan.status, "paid_installments": len(reps) - len(unpaid),
        "remaining_to_pay": round(sum(r.amount for r in unpaid)),
        "overdue_installments": sum(1 for r in unpaid if r.due_date < today),
        "next_due": next(({"id": r.id, "due_date": r.due_date, "amount": round(r.amount)} for r in unpaid), None),
    }


@router.get("/loans", dependencies=CREDIT)
def list_loans(business: Business = Depends(get_business), db: Session = Depends(get_db)):
    today = services.today()
    out = []
    for loan in db.scalars(select(Loan).where(Loan.business_id == business.id).order_by(Loan.start_date.desc())):
        reps = db.scalars(select(Repayment).where(Repayment.loan_id == loan.id).order_by(Repayment.due_date)).all()
        out.append(_loan_row(loan, reps, today))
    return out


@router.get("/loans/{loan_id}", dependencies=CREDIT)
def loan_schedule(loan_id: int, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    """One loan with every installment: due date, amount, and whether it is paid or late."""
    loan = owned(db, Loan, loan_id, business)
    today = services.today()
    reps = db.scalars(select(Repayment).where(Repayment.loan_id == loan.id).order_by(Repayment.due_date)).all()
    return {**_loan_row(loan, reps, today),
            "schedule": [{"id": r.id, "number": i + 1, "due_date": r.due_date, "amount": round(r.amount),
                          "paid_date": r.paid_date, "overdue": r.paid_date is None and r.due_date < today}
                         for i, r in enumerate(reps)]}


@router.post("/loans", status_code=201, dependencies=CREDIT)
def add_loan(body: LoanIn, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    """Record an existing loan so its installments count in the forecast and credit score.

    `installments_paid` of them are marked paid on their due dates without adding expenses: those payments
    happened before and are already in the owner's records, so they must not be counted twice.
    """
    monthly = emi(body.principal, body.rate, body.tenure_months)
    loan = Loan(business_id=business.id, emi=monthly, **body.model_dump(exclude={"installments_paid"}))
    db.add(loan)
    db.flush()
    for k in range(1, body.tenure_months + 1):
        due = _add_months(body.start_date, k)
        db.add(Repayment(business_id=business.id, loan_id=loan.id, due_date=due, amount=monthly,
                         paid_date=due if k <= body.installments_paid else None))
    if body.installments_paid >= body.tenure_months:
        loan.status = "closed"
    db.commit()
    return {"id": loan.id, "emi": round(monthly), "disclaimer": DISCLAIMER}


@router.delete("/loans/{loan_id}", status_code=204, dependencies=CREDIT)
def delete_loan(loan_id: int, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    """Remove a loan that was entered by mistake. Expenses already recorded for its paid installments stay."""
    loan = owned(db, Loan, loan_id, business)
    db.execute(delete(Repayment).where(Repayment.loan_id == loan.id))
    db.delete(loan)
    db.commit()


@router.patch("/repayments/{repayment_id}/paid", dependencies=CREDIT)
def pay_installment(repayment_id: int, body: PayIn | None = None, business: Business = Depends(get_business),
                    db: Session = Depends(get_db)):
    r = owned(db, Repayment, repayment_id, business)
    if r.paid_date:
        return {"id": r.id, "paid_date": r.paid_date}
    r.paid_date = body.paid_date if body and body.paid_date else services.today()
    db.add(Transaction(business_id=business.id, date=r.paid_date, amount=r.amount, type="expense",
                       category="Loan repayment", description=f"Installment for loan #{r.loan_id}",
                       source="system"))
    loan = db.get(Loan, r.loan_id)
    if all(x.paid_date for x in db.scalars(select(Repayment).where(Repayment.loan_id == loan.id))):
        loan.status = "closed"
    db.commit()
    return {"id": r.id, "paid_date": r.paid_date}


@router.get("/cashflow/upcoming")
def upcoming(business: Business = Depends(get_business), db: Session = Depends(get_db)):
    """Next 7 days of known money in and out, for the dashboard."""
    fc = services.cash_forecast(db, business, 7)
    end = (services.today() + timedelta(days=7)).isoformat()
    return {"inflows": [e for e in fc["expected_inflows"] if e["date"] <= end],
            "outflows": [e for e in fc["expected_outflows"] if e["date"] <= end]}
