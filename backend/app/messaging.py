"""Delivering a reminder the owner has approved: email (Brevo), WhatsApp (Meta Cloud API) or SMS (Twilio).

Nothing here runs on its own: it is called only from the owner's explicit "send" action. A channel with no
credentials is "not configured" and nothing leaves the server; the owner then sends the text themselves.
"""

import re
from dataclasses import dataclass

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


def configured_channels() -> dict[str, bool]:
    s = get_settings()
    return {
        "email": bool(s.brevo_api_key and s.brevo_sender_email),
        "whatsapp": bool(s.whatsapp_token and s.whatsapp_phone_number_id),
        "sms": bool(s.twilio_account_sid and s.twilio_auth_token and s.twilio_from),
    }


def normalize_phone(raw: str | None) -> str | None:
    """Keep a leading +, drop spaces, dashes and brackets. Returns None unless it looks like E.164."""
    if not raw:
        return None
    cleaned = re.sub(r"[\s\-().]", "", raw.strip())
    return cleaned if PHONE.match(cleaned) else None


def _check(resp: httpx.Response, provider: str) -> None:
    if resp.status_code >= 300:
        raise DeliveryError(f"{provider} rejected the message ({resp.status_code})")


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


def _whatsapp(to: str, text: str) -> Delivery:
    s = get_settings()
    try:
        r = httpx.post(f"https://graph.facebook.com/v21.0/{s.whatsapp_phone_number_id}/messages", timeout=TIMEOUT,
                       headers={"Authorization": f"Bearer {s.whatsapp_token}"},
                       json={"messaging_product": "whatsapp", "to": to.lstrip("+"), "type": "text",
                             "text": {"body": text}})
    except httpx.HTTPError:
        raise DeliveryError("Could not reach WhatsApp")
    _check(r, "WhatsApp")
    return Delivery(True, "whatsapp", "Free-form text only reaches people who messaged the business in the last 24 hours "
                                       "(or test numbers); otherwise an approved template is needed.")


def _sms(to: str, text: str) -> Delivery:
    s = get_settings()
    try:
        r = httpx.post(f"https://api.twilio.com/2010-04-01/Accounts/{s.twilio_account_sid}/Messages.json", timeout=TIMEOUT,
                       auth=(s.twilio_account_sid, s.twilio_auth_token), data={"To": to, "From": s.twilio_from, "Body": text})
    except httpx.HTTPError:
        raise DeliveryError("Could not reach Twilio")
    _check(r, "Twilio")
    return Delivery(True, "twilio")


def send(channel: str, *, to_email: str | None, to_phone: str | None, subject: str, text: str) -> Delivery:
    """Deliver through the channel's provider, or report that it is not configured.

    Raises ValueError when the customer has no usable address for the channel, DeliveryError when the provider fails.
    """
    if not configured_channels()[channel]:
        return Delivery(False, "none", f"{channel.capitalize() if channel != 'sms' else 'SMS'} is not configured")
    if channel == "email":
        if not (to_email and EMAIL.match(to_email)):
            raise ValueError("This customer has no email address on file")
        return _email(to_email, subject, text)
    phone = normalize_phone(to_phone)
    if phone is None:
        raise ValueError("This customer has no phone number on file in international format, e.g. +14155550123")
    return _whatsapp(phone, text) if channel == "whatsapp" else _sms(phone, text)
