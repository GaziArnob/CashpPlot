"""Optional LLM polish for short texts, always checked against the template it starts from."""

from app.ai import providers
from app.ai.tools import numbers_in

POLISH_PROMPT = (
    "Rewrite this payment reminder in a {tone} tone, polite and under 320 characters. "
    "Keep the placeholders [CUSTOMER] and [BUSINESS] exactly as written. "
    "Do not change any amount, date or number. Reply with the message only.\n\nReminder:\n{text}"
)


def polish_reminder(template_text: str, tone: str, customer: str, business: str, mode: str = "cloud") -> tuple[str, str]:
    """Returns (message, generated_by). Falls back to the template on any doubt."""
    masked = template_text.replace(customer, "[CUSTOMER]").replace(business, "[BUSINESS]")
    final_template = template_text
    try:
        res = providers.chat([{"role": "user", "content": POLISH_PROMPT.format(tone=tone, text=masked)}], mode=mode)
    except providers.NoLLMAvailable:
        return final_template, "template"
    out = (res.text or "").strip()
    if not out or "[CUSTOMER]" not in out or len(out) > 600:
        return final_template, "template"
    if not numbers_in(out) <= numbers_in(masked):
        return final_template, "template"  # the model changed a figure
    return out.replace("[CUSTOMER]", customer).replace("[BUSINESS]", business), res.provider
