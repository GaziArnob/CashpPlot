"""Supplier negotiation messages.

The result is always an editable DRAFT. This module never sends anything: the owner reviews,
edits, copies it and sends it themselves.

A message is built from a template first (reviewed wording, exact figures). A free LLM may then
rephrase it more naturally. Before it sees the text, the supplier's and the business's names are
replaced by placeholders, and the real names are put back afterwards. The rewrite is kept only if
the placeholders survive and every figure matches the template's; otherwise the template is used.
"""

import logging
from datetime import date

from app.ai import providers
from app.ai.templates import money
from app.ai.tools import numbers_in, ungrounded_numbers

log = logging.getLogger(__name__)

SUPPLIER_TOKEN, BUSINESS_TOKEN = "[SUPPLIER]", "[BUSINESS]"


def _date(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%b %d, %Y").replace(" 0", " ")


def _history(rate: float | None) -> str:
    if rate is None or rate < 0.7:
        return ""
    return f" We have paid your bills on time {round(rate * 100)}% of the time and value our relationship."


def template(kind: str, *, supplier: str, business: str, currency: str, amount: float, due_date: str,
             installments: list[dict], on_time_rate: float | None) -> str:
    """The reviewed message text. kind: extension | partial | custom."""
    amt, due = money(amount, currency), _date(due_date)
    last = _date(max(i["due_date"] for i in installments))
    lines = [f"{k}. {_date(i['due_date'])}: {money(i['amount'], currency)}" for k, i in enumerate(installments, 1)]
    if kind == "extension":
        body = (f"Our bill of {amt} is due on {due}. Because of a temporary squeeze on our cash flow, could we please "
                f"pay the full amount on {last} instead?")
    else:
        body = (f"We would like to settle our {amt} bill (due {due}) in instalments:\n" + "\n".join(lines)
                + "\nThis lets us keep our cash flow steady and pay the whole amount with certainty.")
    return (f"Dear {supplier},\n\nI hope you are well. {body}{_history(on_time_rate)}\n\n"
            f"Please let us know if this works for you. Thank you for your understanding.\n\nKind regards,\n{business}")


def _figures(text: str) -> set[float]:
    return {n for n in numbers_in(text) if n >= 100 and not 1900 <= n <= 2100}


def _figures_match(text: str, source: str) -> bool:
    """Every figure of 100+ in the rewrite must appear in the template, and none may be dropped."""
    return _figures(source) <= _figures(text) and not ungrounded_numbers(text, [source], strict=True)


def generate(kind: str, polish: bool = True, mode: str = "cloud", **fields) -> tuple[str, str]:
    """Returns (message, generated_by). Falls back to the template on any doubt."""
    base = template(kind, **fields)
    if not polish:
        return base, "template"
    masked = base.replace(fields["supplier"], SUPPLIER_TOKEN).replace(fields["business"], BUSINESS_TOKEN)
    prompt = ("Rewrite this message to a supplier so it sounds warm, natural and professional. "
              f"Keep every amount, date and percentage exactly as written, and keep {SUPPLIER_TOKEN} and "
              f"{BUSINESS_TOKEN} exactly as written. Keep it about the same length, do not promise anything not "
              "already in it, and keep the greeting and sign-off. Reply with the message only.\n\n" + masked)
    try:
        res = providers.chat([{"role": "user", "content": prompt}], mode=mode)
    except providers.NoLLMAvailable:
        return base, "template"
    text = (res.text or "").strip()
    if (not text or len(text) > 2 * len(masked) + 200 or SUPPLIER_TOKEN not in text or BUSINESS_TOKEN not in text
            or not _figures_match(text, masked)):
        log.warning("Negotiation rewrite rejected (figures or placeholders changed)")
        return base, "template"
    return text.replace(SUPPLIER_TOKEN, fields["supplier"]).replace(BUSINESS_TOKEN, fields["business"]), res.provider
