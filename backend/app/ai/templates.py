"""Template text used when no LLM is available, and as the safe base for LLM drafts."""

from datetime import date

CURRENCY_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "INR": "₹", "CAD": "CA$", "AUD": "A$", "SGD": "S$"}

# Reminder messages: short-message length, polite but firm. {amount} is already formatted.
REMINDER_TEMPLATES = {
    "upcoming": (
        "Hello {customer}, a quick reminder from {business}: your payment of {amount} is due on "
        "{due_date}. Thank you!"
    ),
    "friendly": (
        "Hello {customer}, this is a friendly reminder from {business}. "
        "Your payment of {amount} was due on {due_date}. "
        "Please pay when convenient. Thank you for your business!"
    ),
    "firm": (
        "Dear {customer}, our records show {amount} owed to {business} is now {days} days overdue "
        "(due {due_date}). Please arrange payment within the next 3 days. Thank you."
    ),
    "final": (
        "Final notice: {customer}, {amount} owed to {business} is {days} days overdue "
        "(due {due_date}). Please pay immediately or contact us today to agree a payment plan."
    ),
    "discount": (
        "Hello {customer}, a special offer from {business}: pay your {amount} balance by {deadline} "
        "and get {pct}% off, so you pay only {discounted}. Thank you!"
    ),
}


def money(n: float, currency: str = "USD") -> str:
    """12,345.6 -> '$12,346' for USD (and a few other currencies), 'CHF 12,346' otherwise. Negatives read '-$5'."""
    sign = "-" if round(n) < 0 else ""
    symbol = CURRENCY_SYMBOLS.get(currency)
    body = f"{abs(round(n)):,}"
    return f"{sign}{symbol}{body}" if symbol else f"{sign}{currency} {body}"


def long_date(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%b %d, %Y").replace(" 0", " ")


def day(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%a, %b %d").replace(" 0", " ")


def reminder(tone: str, *, customer: str, business: str, amount: float, currency: str,
             due_date: str, days: int, discount_pct: int = 2, discount_deadline: str | None = None) -> str:
    """A ready-to-send reminder. tone: upcoming | friendly | firm | final | discount."""
    text = REMINDER_TEMPLATES.get(tone, REMINDER_TEMPLATES["friendly"])
    return text.format(
        customer=customer, business=business, amount=money(amount, currency), due_date=long_date(due_date),
        days=days, pct=discount_pct, discounted=money(amount * (1 - discount_pct / 100), currency),
        deadline=long_date(discount_deadline or due_date))


def daily_summary(fc: dict, ranked: list[dict], credit: dict, currency: str) -> str:
    parts = [f"Your balance is {money(fc['start_balance'], currency)}."]
    if fc["first_shortage"]:
        s = fc["first_shortage"]
        parts.append(f"Cash may fall {money(s['gap'], currency)} below your safety threshold on {day(s['date'])}.")
    else:
        parts.append(f"No cash shortage is expected in the next {fc['days']} days.")
    overdue = [r for r in ranked if r["overdue_amount"] > 0]
    if overdue:
        total = sum(r["overdue_amount"] for r in overdue)
        top = overdue[0]
        parts.append(f"{len(overdue)} customers owe {money(total, currency)} overdue; "
                     f"start with {top['customer_name']} ({money(top['overdue_amount'], currency)}).")
    parts.append(f"Your credit score is {credit['score']} ({credit['band']}).")
    return " ".join(parts)
