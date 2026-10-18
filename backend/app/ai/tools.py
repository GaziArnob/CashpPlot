"""The agent's tools. All are read-only and bound to one business on the server side.

Results are minimized and pseudonymized before they reach a free LLM provider:
customer and supplier names become aliases like "Customer C12", and the backend
swaps the real names back into the final answer.
"""

import re
from datetime import date

from sqlalchemy.orm import Session

from app import services
from app.ai import templates
from app.models import Business

TOOL_SCHEMAS = [
    {
        "name": "get_cash_forecast",
        "description": "Projected daily cash balance and any cash shortages over the next N days.",
        "parameters": {"type": "object", "properties": {
            "days": {"type": "integer", "description": "Days ahead, 7 to 30", "minimum": 7, "maximum": 30}}},
    },
    {
        "name": "get_overdue_customers",
        "description": "Customers with unpaid invoices, ranked by who to collect from first.",
        "parameters": {"type": "object", "properties": {
            "limit": {"type": "integer", "description": "How many customers, 1 to 10"}}},
    },
    {
        "name": "get_credit_score",
        "description": "The business's explainable credit score (300-900), band and main reasons.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_loan_recommendation",
        "description": "Safe loan amount, matching financing options and readiness checklist. Not an approval.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "run_what_if",
        "description": "Re-run the 30-day cash forecast with changed sales, a new monthly expense or a new loan.",
        "parameters": {"type": "object", "properties": {
            "sales_change_pct": {"type": "number", "description": "Sales change in percent, e.g. -10"},
            "extra_monthly_expense": {"type": "number", "description": "New fixed monthly expense"},
            "loan_amount": {"type": "number", "description": "New loan amount received now"},
            "loan_tenure_months": {"type": "integer", "description": "Loan tenure in months"}}},
    },
    {
        "name": "get_spending_insights",
        "description": "Expense categories that changed a lot versus the 3-month average.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "draft_reminder",
        "description": "Draft (not send) a payment reminder for one customer, by alias such as C12.",
        "parameters": {"type": "object", "properties": {
            "customer": {"type": "string", "description": "Customer alias, e.g. C12"}},
            "required": ["customer"]},
    },
]


class Aliaser:
    def __init__(self):
        self.real: dict[str, str] = {}

    def customer(self, cid: int, name: str) -> str:
        alias = f"Customer C{cid}"
        self.real[alias] = name
        return alias

    def supplier(self, name: str) -> str:
        for alias, real in self.real.items():
            if real == name and alias.startswith("Supplier"):
                return alias
        alias = f"Supplier S{sum(1 for a in self.real if a.startswith('Supplier')) + 1}"
        self.real[alias] = name
        return alias

    def restore(self, text: str) -> str:
        """Swap aliases back to real names. Models sometimes add a no-break space or bold."""
        pattern = r"(Customer|Supplier)[\s   ]+([CS]\d+)(?!\d)"

        def swap(m: re.Match) -> str:
            return self.real.get(f"{m.group(1)} {m.group(2)}", m.group(0))

        return re.sub(pattern, swap, text)


def _clamp(v, lo, hi, default):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


class ToolBox:
    def __init__(self, db: Session, business: Business):
        self.db = db
        self.business = business  # from the authenticated session, never from the model
        self.alias = Aliaser()

    def run(self, name: str, args: dict) -> dict:
        fn = getattr(self, "_" + name, None)
        if name not in {t["name"] for t in TOOL_SCHEMAS} or fn is None:
            return {"error": f"Unknown tool {name}"}
        try:
            return fn(args or {})
        except Exception as e:  # tools must never crash the loop
            return {"error": f"{name} failed: {type(e).__name__}"}

    def _get_cash_forecast(self, args):
        days = _clamp(args.get("days"), 7, 30, 30)
        fc = services.cash_forecast(self.db, self.business, days)
        checkpoints = [r for i, r in enumerate(fc["series"], 1) if i in (7, 14, 21, 30) or i == days]
        return {
            "currency": self.business.currency,
            "days": days,
            "current_balance": fc["start_balance"],
            "threshold": fc["threshold"],
            "first_shortage": fc["first_shortage"],
            "shortage_days": len(fc["shortages"]),
            "largest_gap": fc["largest_gap"],
            "lowest_balance": fc["min_balance"],
            "at_risk_days": fc["at_risk_days"],
            "overdue_receivables_not_counted": fc["overdue_receivables"],
            "balance_checkpoints": [{"date": r["date"], "balance": r["balance"]} for r in checkpoints],
            "main_outflows_before_shortage": [
                {"date": e["date"], "amount": e["amount"],
                 "what": self.alias.supplier(e["supplier"]) if e["kind"] == "bill" else "Loan installment"}
                for e in fc["drivers"][:3]
            ],
        }

    def _get_overdue_customers(self, args):
        limit = _clamp(args.get("limit"), 1, 10, 5)
        ranked = services.recovery_priority(self.db, self.business)[:limit]
        return {"currency": self.business.currency, "customers": [{
            "customer": self.alias.customer(r["customer_id"], r["customer_name"]),
            "rank": r["rank"], "priority_score": r["score"], "outstanding": r["outstanding"],
            "overdue_amount": r["overdue_amount"], "days_overdue": r["max_days_overdue"],
            "aging_bucket": r["aging_bucket"], "probability_pays_within_7_days": r["p_pay_7d"],
            "recommended_action": r["action_label"], "suggested_credit_limit": r["credit_limit"],
            "collecting_closes_shortage": r["closes_shortage"], "risk": r["risk_level"],
        } for r in ranked]}

    def _get_credit_score(self, args):
        c = services.credit_score(self.db, self.business, store=False)
        return {"score": c["score"], "band": c["band"],
                "raised_by": c["reasons_positive"], "lowered_by": c["reasons_negative"]}

    def _get_loan_recommendation(self, args):
        r = services.loan_recommendation(self.db, self.business)
        return {
            "currency": self.business.currency, "ready": r["ready"], "score": r["score"], "band": r["band"],
            "safe_monthly_installment": r["safe_monthly_installment"],
            "max_recommended_amount": r["max_recommended_amount"],
            "top_options": [{k: o[k] for k in ("name", "lender", "rate", "tenure_months",
                                               "recommended_amount", "monthly_installment", "total_interest")}
                            for o in r["options"][:3]],
            "to_improve": [i["item"] for i in r["checklist"] if not i["done"]],
            "disclaimer": r["disclaimer"],
        }

    def _run_what_if(self, args):
        r = services.what_if(
            self.db, self.business,
            sales_change_pct=float(args.get("sales_change_pct") or 0),
            extra_monthly_expense=float(args.get("extra_monthly_expense") or 0),
            loan_amount=float(args.get("loan_amount") or 0),
            loan_tenure_months=_clamp(args.get("loan_tenure_months"), 3, 60, 12),
        )
        return {"currency": self.business.currency, "inputs": r["inputs"],
                "base": {k: r["base"][k] for k in ("end_balance", "shortage_days", "min_balance")},
                "scenario": {k: r["scenario"][k] for k in ("end_balance", "shortage_days", "min_balance")},
                "end_balance_change": r["end_balance_change"]}

    def _get_spending_insights(self, args):
        return {"currency": self.business.currency,
                "insights": [i["message"] for i in services.spending_insights(self.db, self.business)[:5]]}

    def _draft_reminder(self, args):
        m = re.search(r"(\d+)", str(args.get("customer", "")))
        if not m:
            return {"error": "Give a customer alias such as C12"}
        cid = int(m.group(1))
        ranked = {r["customer_id"]: r for r in services.recovery_priority(self.db, self.business)}
        r = ranked.get(cid)
        if r is None:
            return {"error": "That customer has no unpaid invoices"}
        inv = r["invoices"][0]
        alias = self.alias.customer(cid, r["customer_name"])
        text = templates.reminder(r["tone"], customer=alias, business=self.business.name,
                                  amount=r["outstanding"], currency=self.business.currency,
                                  due_date=inv["due_date"], days=r["max_days_overdue"])
        return {"customer": alias, "tone": r["tone"], "draft": text,
                "note": "Draft only. The owner reviews and sends it from the Ledger page."}


NUMBER = r"-?\d[\d,]*(?:\.\d+)?"


def numbers_in(obj) -> set[float]:
    found = set()
    if isinstance(obj, dict):
        for v in obj.values():
            found |= numbers_in(v)
    elif isinstance(obj, list):
        for v in obj:
            found |= numbers_in(v)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        found.add(float(obj))
    elif isinstance(obj, str):
        found |= {float(x.rstrip(",").replace(",", "")) for x in re.findall(NUMBER, obj)}
    return found


def _supported(v: float, k: float, strict: bool) -> bool:
    if abs(v - k) < 1:
        return True
    if strict:  # only an exact figure or the same figure rounded to hundreds/thousands ("about 12,000")
        return v in (round(k, -2), round(k, -3)) and v != 0
    return abs(v - k) <= 0.05 * max(k, 1)


def ungrounded_numbers(answer: str, results: list, strict: bool = False) -> list[str]:
    """Numbers of 100 or more in the answer that no tool result supports.

    Default allows 5% for the agent's conversational rounding; strict (the advice summary) accepts
    only exact figures or plain roundings of them, so a mistyped digit is caught.
    """
    known = set()
    for r in results:
        known |= numbers_in(r)
    known_abs = {abs(k) for k in known}
    bad = []
    for raw in (x.rstrip(",") for x in re.findall(NUMBER, answer)):
        try:
            v = float(raw.replace(",", ""))
        except ValueError:
            continue
        if v < 100 or 1900 <= v <= 2100:  # small numbers and years are fine
            continue
        if not any(_supported(v, k, strict) for k in known_abs):
            bad.append(raw)
    return bad


def today_str() -> str:
    return date.today().isoformat()
