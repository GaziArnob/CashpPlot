"""Template text used when no LLM is available, and as the safe base for LLM drafts."""

from datetime import date

# Reminder messages: SMS/WhatsApp length, polite but firm. {amount} is already formatted.
REMINDER_TEMPLATES = {
    "en": {
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
    },
    "bn": {
        "upcoming": (
            "প্রিয় {customer}, {business} থেকে মনে করিয়ে দিচ্ছি: আপনার {amount} পরিশোধের তারিখ "
            "{due_date}। ধন্যবাদ।"
        ),
        "friendly": (
            "প্রিয় {customer}, {business} থেকে একটি বিনীত অনুরোধ। আপনার {amount} পরিশোধের তারিখ ছিল "
            "{due_date}। সুবিধামতো সময়ে পরিশোধ করলে কৃতজ্ঞ থাকব। ধন্যবাদ।"
        ),
        "firm": (
            "প্রিয় {customer}, {business}-এর কাছে আপনার {amount} {days} দিন ধরে বকেয়া "
            "(পরিশোধের তারিখ ছিল {due_date})। অনুগ্রহ করে আগামী ৩ দিনের মধ্যে পরিশোধ করুন। ধন্যবাদ।"
        ),
        "final": (
            "শেষ অনুস্মারক: {customer}, {business}-এর কাছে আপনার {amount} {days} দিন ধরে বকেয়া "
            "(তারিখ ছিল {due_date})। অনুগ্রহ করে আজই পরিশোধ করুন, অথবা কিস্তিতে পরিশোধের ব্যবস্থা করতে "
            "আজই আমাদের সাথে যোগাযোগ করুন।"
        ),
        "discount": (
            "প্রিয় {customer}, {business} থেকে একটি বিশেষ সুবিধা: আপনার {amount} বকেয়া {deadline}-এর মধ্যে "
            "পরিশোধ করলে {pct}% ছাড় পাবেন, অর্থাৎ মাত্র {discounted} দিলেই হবে। ধন্যবাদ।"
        ),
    },
}

BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
BN_MONTHS = ["জানুয়ারি", "ফেব্রুয়ারি", "মার্চ", "এপ্রিল", "মে", "জুন", "জুলাই", "আগস্ট", "সেপ্টেম্বর",
             "অক্টোবর", "নভেম্বর", "ডিসেম্বর"]


def bn_number(n: float) -> str:
    return f"{round(n):,}".translate(BN_DIGITS)


def _fmt_amount(n: float, currency: str, lang: str) -> str:
    return f"{bn_number(n)} টাকা" if lang == "bn" else money(n, currency)


def _fmt_date(iso: str, lang: str) -> str:
    d = date.fromisoformat(iso)
    if lang == "bn":
        return f"{str(d.day).translate(BN_DIGITS)} {BN_MONTHS[d.month - 1]} {str(d.year).translate(BN_DIGITS)}"
    return d.strftime("%b %d, %Y").replace(" 0", " ")


def reminder(tone: str, *, customer: str, business: str, amount: float, currency: str,
             due_date: str, days: int, lang: str = "en", discount_pct: int = 2,
             discount_deadline: str | None = None) -> str:
    """A ready-to-send reminder. tone: upcoming | friendly | firm | final | discount; lang: en | bn."""
    lang = lang if lang in REMINDER_TEMPLATES else "en"
    templates = REMINDER_TEMPLATES[lang]
    text = templates.get(tone, templates["friendly"])
    return text.format(
        customer=customer, business=business, amount=_fmt_amount(amount, currency, lang),
        due_date=_fmt_date(due_date, lang),
        days=str(days).translate(BN_DIGITS) if lang == "bn" else days,
        pct=str(discount_pct).translate(BN_DIGITS) if lang == "bn" else discount_pct,
        discounted=_fmt_amount(amount * (1 - discount_pct / 100), currency, lang),
        deadline=_fmt_date(discount_deadline or due_date, lang),
    )


def money(n: float, currency: str) -> str:
    return f"{currency} {round(n):,}"


def day(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%a, %b %d").replace(" 0", " ")


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
