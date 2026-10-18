"""What-if simulator (Technical Documentation section 2.5): re-runs the forecast with changed inputs."""

from datetime import date

from app.engines.data import BusinessData
from app.engines.forecast import Scenario, forecast
from app.engines.loan import emi


def simulate(data: BusinessData, today: date, *, days: int = 30, sales_change_pct: float = 0.0,
             extra_monthly_expense: float = 0.0, loan_amount: float = 0.0,
             loan_rate: float = 12.0, loan_tenure_months: int = 12) -> dict:
    new_emi = emi(loan_amount, loan_rate, loan_tenure_months) if loan_amount > 0 else 0.0
    base = forecast(data, today, days)
    scenario = forecast(data, today, days, Scenario(
        sales_change_pct=sales_change_pct,
        extra_monthly_expense=extra_monthly_expense,
        loan_amount=loan_amount,
        loan_emi=new_emi,
    ))
    end_base = base["series"][-1]["balance"]
    end_scn = scenario["series"][-1]["balance"]
    return {
        "inputs": {
            "days": days, "sales_change_pct": sales_change_pct,
            "extra_monthly_expense": extra_monthly_expense, "loan_amount": loan_amount,
            "loan_rate": loan_rate, "loan_tenure_months": loan_tenure_months,
            "new_monthly_installment": round(new_emi),
        },
        "base": {"series": [{"date": r["date"], "balance": r["balance"]} for r in base["series"]],
                 "shortage_days": len(base["shortages"]), "end_balance": end_base,
                 "min_balance": base["min_balance"]},
        "scenario": {"series": [{"date": r["date"], "balance": r["balance"]} for r in scenario["series"]],
                     "shortage_days": len(scenario["shortages"]), "end_balance": end_scn,
                     "min_balance": scenario["min_balance"]},
        "end_balance_change": end_scn - end_base,
        "threshold": base["threshold"],
    }
