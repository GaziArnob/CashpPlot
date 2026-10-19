"""Delivering a reminder the owner has approved: email (Brevo), WhatsApp (Meta Cloud API) or SMS (Twilio).

Nothing here runs on its own: it is called only from the owner's explicit "send" action. A channel with no
credentials is "not configured" and nothing leaves the server; the owner then sends the text themselves.
"""

import re
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

import httpx

from app.config import get_settings

TIMEOUT = 15.0
PHONE = re.compile(r"^\+[1-9]\d{6,14}$")  # E.164, e.g. +14155550123
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class DeliveryError(Exception):
    """The provider refused or could not be reached. Nothing was delivered."""


@dataclass
class Delivery:
    delivered: bool
    provider: str
    detail: str = ""


def _brevo_ready() -> bool:
    s = get_settings()
    return bool(s.brevo_api_key and s.brevo_sender_email)


def _mailjet_ready() -> bool:
    s = get_settings()
    return bool(s.mailjet_api_key and s.mailjet_secret_key and s.mailjet_sender_email)


def _smtp_ready() -> bool:
    s = get_settings()
    return bool(s.smtp_host and s.smtp_user and s.smtp_password)


def _twilio_ready() -> bool:
    s = get_settings()
    return bool(s.twilio_account_sid and s.twilio_auth_token)


def configured_channels() -> dict[str, bool]:
    s = get_settings()
    return {
        "email": _brevo_ready() or _mailjet_ready() or _smtp_ready(),
        "whatsapp": bool(s.whatsapp_token and s.whatsapp_phone_number_id) or (_twilio_ready() and bool(s.twilio_whatsapp_from)),
        "sms": bool(s.twilio_account_sid and s.twilio_auth_token and s.twilio_from),
    }


def normalize_phone(raw: str | None) -> str | None:
    """Keep a leading +, drop spaces, dashes and brackets. Returns None unless it looks like E.164."""
    if not raw:
        return None
    cleaned = re.sub(r"[\s\-().]", "", raw.strip())
    return cleaned if PHONE.match(cleaned) else None


def _reason(resp: httpx.Response) -> str:
    """What the provider said went wrong, if it says (Twilio: message, Meta: error.message, Brevo/Mailjet: message)."""
    try:
        body = resp.json()
    except (ValueError, AttributeError):
        return ""
    if not isinstance(body, dict):
        return ""
    err = body.get("error")
    msg = body.get("message") or (err.get("message") if isinstance(err, dict) else err) or body.get("ErrorMessage")
    return " ".join(str(msg).split())[:200] if msg else ""


def _check(resp: httpx.Response, provider: str) -> None:
    if resp.status_code >= 300:
        why = _reason(resp)
        raise DeliveryError(f"{provider} rejected the message ({resp.status_code})" + (f": {why}" if why else ""))


def _email(to: str, subject: str, text: str) -> Delivery:
    s = get_settings()
    try:
        r = httpx.post("https://api.brevo.com/v3/smtp/email", timeout=TIMEOUT, headers={"api-key": s.brevo_api_key},
                       json={"sender": {"email": s.brevo_sender_email, "name": s.brevo_sender_name},
                             "to": [{"email": to}], "subject": subject, "textContent": text})
    except httpx.HTTPError:
        raise DeliveryError("Could not reach Brevo")
    _check(r, "Brevo")
    return Delivery(True, "brevo")


def _mailjet(to: str, subject: str, text: str) -> Delivery:
    s = get_settings()
    try:
        r = httpx.post("https://api.mailjet.com/v3.1/send", timeout=TIMEOUT, auth=(s.mailjet_api_key, s.mailjet_secret_key),
                       json={"Messages": [{"From": {"Email": s.mailjet_sender_email, "Name": s.brevo_sender_name or "CashPilot"},
                                           "To": [{"Email": to}], "Subject": " ".join(subject.split())[:200], "TextPart": text}]})
    except httpx.HTTPError:
        raise DeliveryError("Could not reach Mailjet")
    _check(r, "Mailjet")
    # Mailjet can answer 200 and still refuse the message; the per-message status says which.
    try:
        msg = r.json()["Messages"][0]
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        msg = None
    if isinstance(msg, dict) and msg.get("Status") not in (None, "success"):
        reason = ((msg.get("Errors") or [{}])[0] or {}).get("ErrorMessage") or "it was refused"
        raise DeliveryError(f"Mailjet did not send the message: {str(reason)[:160]}")
    sent_to = (msg or {}).get("To") or [{}]
    ref = (sent_to[0] or {}).get("MessageID") if isinstance(sent_to, list) and sent_to else None
    return Delivery(True, "mailjet", f"Mailjet message id {ref}. Check Mailjet's message history if it does not arrive." if ref else "")


def _smtp(to: str, subject: str, text: str) -> Delivery:
    """Send through any SMTP mailbox. Port 465 uses SSL from the start, anything else upgrades with STARTTLS."""
    s = get_settings()
    msg = EmailMessage()
    msg["From"] = f"{s.brevo_sender_name or 'CashPilot'} <{s.smtp_from or s.smtp_user}>"
    msg["To"] = to
    msg["Subject"] = " ".join(subject.split())[:200]       # no line breaks: they could add headers
    msg.set_content(text)
    try:
        if s.smtp_port == 465:
            server = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=TIMEOUT, context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=TIMEOUT)
        with server:
            if s.smtp_port != 465:
                server.starttls(context=ssl.create_default_context())
            server.login(s.smtp_user, s.smtp_password)
            server.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise DeliveryError("The email server refused the username or password")
    except smtplib.SMTPException:
        raise DeliveryError("The email server did not accept the message")
    except OSError:
        raise DeliveryError("Could not connect to the email server. Some hosts, including Render's free plan, block "
                            "SMTP; use an email service over HTTPS (Brevo or Mailjet) instead")
    return Delivery(True, "smtp")


def _whatsapp(to: str, text: str, params: list[str]) -> Delivery:
    """With WHATSAPP_TEMPLATE_NAME set, send that approved template (it can reach anyone). Otherwise send free
    text, which WhatsApp only delivers inside 24 hours of the customer's own message (and to test numbers)."""
    s = get_settings()
    if s.whatsapp_template_name:
        body = {"messaging_product": "whatsapp", "to": to.lstrip("+"), "type": "template",
                "template": {"name": s.whatsapp_template_name, "language": {"code": s.whatsapp_template_lang},
                             "components": [{"type": "body", "parameters": [
                                 {"type": "text", "text": _clean(p)} for p in params]}] if params else []}}
        note = "Sent with the approved template, so the wording is the template's, not your edited text."
    else:
        body = {"messaging_product": "whatsapp", "to": to.lstrip("+"), "type": "text", "text": {"body": text}}
        note = ("Free-form text only reaches people who messaged the business in the last 24 hours (or test numbers); "
                "set WHATSAPP_TEMPLATE_NAME to reach anyone.")
    try:
        r = httpx.post(f"https://graph.facebook.com/v21.0/{s.whatsapp_phone_number_id}/messages", timeout=TIMEOUT,
                       headers={"Authorization": f"Bearer {s.whatsapp_token}"}, json=body)
    except httpx.HTTPError:
        raise DeliveryError("Could not reach WhatsApp")
    _check(r, "WhatsApp")
    return Delivery(True, "whatsapp", note)


def _clean(value: str) -> str:
    """Template variables may not hold line breaks, tabs or long runs of spaces."""
    return " ".join(str(value).split())[:200]


def _twilio_whatsapp(to: str, text: str) -> Delivery:
    """WhatsApp through Twilio. In the sandbox the person must first send Twilio's join phrase to the sandbox number;
    after that, free text reaches them for 24 hours from their last message."""
    s = get_settings()
    sender = s.twilio_whatsapp_from if s.twilio_whatsapp_from.startswith("whatsapp:") else f"whatsapp:{s.twilio_whatsapp_from}"
    try:
        r = httpx.post(f"https://api.twilio.com/2010-04-01/Accounts/{s.twilio_account_sid}/Messages.json", timeout=TIMEOUT,
                       auth=(s.twilio_account_sid, s.twilio_auth_token), data={"To": f"whatsapp:{to}", "From": sender, "Body": text})
    except httpx.HTTPError:
        raise DeliveryError("Could not reach Twilio")
    _check(r, "Twilio")
    return Delivery(True, "twilio-whatsapp", "In the Twilio sandbox, only people who joined it can receive this, and free text "
                                              "works for 24 hours after their last message to the sandbox number.")


def _sms(to: str, text: str) -> Delivery:
    s = get_settings()
    try:
        r = httpx.post(f"https://api.twilio.com/2010-04-01/Accounts/{s.twilio_account_sid}/Messages.json", timeout=TIMEOUT,
                       auth=(s.twilio_account_sid, s.twilio_auth_token), data={"To": to, "From": s.twilio_from, "Body": text})
    except httpx.HTTPError:
        raise DeliveryError("Could not reach Twilio")
    _check(r, "Twilio")
    return Delivery(True, "twilio")


def send(channel: str, *, to_email: str | None, to_phone: str | None, subject: str, text: str,
         template_params: list[str] | None = None) -> Delivery:
    """Deliver through the channel's provider, or report that it is not configured.

    Raises ValueError when the customer has no usable address for the channel, DeliveryError when the provider fails.
    """
    if not configured_channels()[channel]:
        return Delivery(False, "none", f"{channel.capitalize() if channel != 'sms' else 'SMS'} is not configured")
    if channel == "email":
        if not (to_email and EMAIL.match(to_email)):
            raise ValueError("This customer has no email address on file")
        if _brevo_ready():
            return _email(to_email, subject, text)
        return _mailjet(to_email, subject, text) if _mailjet_ready() else _smtp(to_email, subject, text)
    phone = normalize_phone(to_phone)
    if phone is None:
        raise ValueError("This customer has no phone number on file in international format, e.g. +14155550123")
    if channel == "whatsapp":
        s = get_settings()
        if s.whatsapp_token and s.whatsapp_phone_number_id:
            return _whatsapp(phone, text, template_params or [])
        return _twilio_whatsapp(phone, text)
    return _sms(phone, text)
