"""Supplier negotiation messages in English and Bangla.

The result is always an editable DRAFT. This module never sends anything: the owner reviews,
edits, copies it and sends it themselves.

A message is built from a template first (reviewed wording, exact figures). A free LLM may then
rephrase it more naturally, but its answer is kept only if every figure matches the template's;
otherwise the template text is used.
"""

import logging
from datetime import date

from app.ai import providers
from app.ai.templates import BN_DIGITS, BN_MONTHS, bn_number
from app.ai.tools import numbers_in, ungrounded_numbers

log = logging.getLogger(__name__)
TO_ASCII = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def _money(n: float, currency: str, lang: str) -> str:
    return f"{bn_number(n)} টাকা" if lang == "bn" else f"{currency} {round(n):,}"


def _date(iso: str, lang: str) -> str:
    d = date.fromisoformat(iso)
    if lang == "bn":
        return f"{str(d.day).translate(BN_DIGITS)} {BN_MONTHS[d.month - 1]} {str(d.year).translate(BN_DIGITS)}"
    return d.strftime("%b %d, %Y").replace(" 0", " ")


def _history(rate: float | None, lang: str) -> str:
    if rate is None or rate < 0.7:
        return ""
    pct = round(rate * 100)
    if lang == "bn":
        return f" এর আগে আমরা আপনাদের {str(pct).translate(BN_DIGITS)}% বিল সময়মতো পরিশোধ করেছি এবং আমাদের সম্পর্কের মূল্য দিই।"
    return f" We have paid your bills on time {pct}% of the time and value our relationship."


def template(kind: str, lang: str, *, supplier: str, business: str, currency: str, amount: float, due_date: str,
             installments: list[dict], on_time_rate: float | None, discount_note: str | None = None) -> str:
    """The reviewed message text. kind: extension | partial | custom. lang: en | bn."""
    lang = lang if lang in ("en", "bn") else "en"
    amt, due = _money(amount, currency, lang), _date(due_date, lang)
    hist = _history(on_time_rate, lang)
    lines = [f"{k}. {_date(i['due_date'], lang)}: {_money(i['amount'], currency, lang)}"
             for k, i in enumerate(installments, start=1)]
    last = _date(max(i["due_date"] for i in installments), lang)
    if lang == "bn":
        amt_of = f"{bn_number(amount)} টাকার"  # "of 39,200 taka"
        lines = [f"{str(k).translate(BN_DIGITS)}. {_date(i['due_date'], lang)}: {_money(i['amount'], currency, lang)}"
                 for k, i in enumerate(installments, start=1)]
        if kind == "extension":
            body = (f"আমাদের {amt_of} বিলের পরিশোধের তারিখ {due}। ব্যবসার নগদ প্রবাহে সাময়িক চাপ থাকায় অনুগ্রহ করে "
                    f"পুরো টাকা {last} তারিখে পরিশোধের সুযোগ দিন।")
        else:
            body = (f"আমাদের {amt_of} বিলটি (তারিখ {due}) নিচের সময়সূচি অনুযায়ী ভাগে ভাগে পরিশোধ করতে চাই:\n"
                    + "\n".join(lines) + "\nএতে আমাদের নগদ প্রবাহ ঠিক রেখে পুরো টাকাই নিশ্চিতভাবে পরিশোধ করতে পারব।")
        return (f"প্রিয় {supplier},\n\nআশা করি ভালো আছেন। {body}{hist}\n\n"
                f"আপনাদের সুবিধা-অসুবিধা জানালে কৃতজ্ঞ থাকব। ধন্যবাদ।\n\nবিনীত,\n{business}")
    if kind == "extension":
        body = (f"Our bill of {amt} is due on {due}. Because of a temporary squeeze on our cash flow, could we please "
                f"pay the full amount on {last} instead?")
    else:
        body = (f"We would like to settle our {amt} bill (due {due}) in instalments:\n" + "\n".join(lines)
                + "\nThis lets us keep our cash flow steady and pay the whole amount with certainty.")
    return (f"Dear {supplier},\n\nI hope you are well. {body}{hist}\n\n"
            f"Please let us know if this works for you. Thank you for your understanding.\n\nKind regards,\n{business}")


def _figures_match(text: str, source: str) -> bool:
    """Every number of 100+ in the rewrite must appear in the template, and none may be dropped."""
    want = {n for n in numbers_in(source.translate(TO_ASCII)) if n >= 100 and not 1900 <= n <= 2100}
    got = {n for n in numbers_in(text.translate(TO_ASCII)) if n >= 100 and not 1900 <= n <= 2100}
    return want <= got and not ungrounded_numbers(text.translate(TO_ASCII), [source.translate(TO_ASCII)], strict=True)


def generate(kind: str, lang: str, polish: bool = True, **fields) -> tuple[str, str]:
    """Returns (message, generated_by). Falls back to the template on any doubt."""
    base = template(kind, lang, **fields)
    if not polish:
        return base, "template"
    language = "Bangla (Bengali script)" if lang == "bn" else "English"
    prompt = (f"Rewrite this message to a supplier so it sounds warm, natural and professional in {language}. "
              "Keep every amount, date, name and percentage exactly as written, keep it about the same length, "
              "do not promise anything not already in it, and keep the greeting and sign-off. "
              "Reply with the message only.\n\n" + base)
    try:
        res = providers.chat([{"role": "user", "content": prompt}])
    except providers.NoLLMAvailable:
        return base, "template"
    text = (res.text or "").strip()
    if not text or len(text) > 2 * len(base) + 200 or not _figures_match(text, base):
        log.warning("Negotiation rewrite rejected (figures changed)")
        return base, "template"
    return text, res.provider
