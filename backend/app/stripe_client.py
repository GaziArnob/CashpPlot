"""Stripe over plain HTTPS: Checkout for the Pro subscription, the billing portal, and webhook verification.

Use test keys (sk_test_...) until the business is verified with Stripe. No card data ever reaches this server:
the customer pays on Stripe's own page.
"""

import hashlib
import hmac
import json
import time

import httpx

from app.config import get_settings

API = "https://api.stripe.com/v1"
TIMEOUT = 20.0
TOLERANCE_SECONDS = 300


class StripeError(Exception):
    """Stripe refused or could not be reached. The message is safe to show the owner."""


def configured() -> bool:
    s = get_settings()
    return bool(s.stripe_secret_key and s.stripe_price_id)


def _call(method: str, path: str, data: dict | None = None) -> dict:
    s = get_settings()
    try:
        r = httpx.request(method, API + path, data=data, auth=(s.stripe_secret_key, ""), timeout=TIMEOUT)
    except httpx.HTTPError:
        raise StripeError("Could not reach Stripe")
    if r.status_code >= 300:
        try:
            msg = r.json().get("error", {}).get("message") or "request failed"
        except ValueError:
            msg = "request failed"
        raise StripeError(f"Stripe said: {msg}")
    return r.json()


def create_checkout(business_id: int, email: str, customer_id: str | None) -> str:
    s = get_settings()
    data = {
        "mode": "subscription",
        "line_items[0][price]": s.stripe_price_id,
        "line_items[0][quantity]": "1",
        "success_url": f"{s.app_url}/settings?billing=success#plan",
        "cancel_url": f"{s.app_url}/settings?billing=cancelled#plan",
        "client_reference_id": str(business_id),
        "subscription_data[metadata][business_id]": str(business_id),
    }
    if customer_id:
        data["customer"] = customer_id
    else:
        data["customer_email"] = email
    return _call("POST", "/checkout/sessions", data)["url"]


def create_portal(customer_id: str) -> str:
    return _call("POST", "/billing_portal/sessions", {"customer": customer_id,
                                                      "return_url": f"{get_settings().app_url}/settings#plan"})["url"]


def cancel_subscription(subscription_id: str) -> None:
    try:
        _call("DELETE", f"/subscriptions/{subscription_id}")
    except StripeError as e:
        if "No such subscription" in str(e):
            return  # already gone
        raise


def verify_webhook(payload: bytes, header: str | None, now: float | None = None) -> dict | None:
    """The event if Stripe's signature is valid and recent, else None. Never trust an unsigned event."""
    secret = get_settings().stripe_webhook_secret
    if not secret or not header:
        return None
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    stamp = parts.get("t")
    if not stamp or not stamp.isdigit() or abs((now if now is not None else time.time()) - int(stamp)) > TOLERANCE_SECONDS:
        return None
    expected = hmac.new(secret.encode(), f"{stamp}.".encode() + payload, hashlib.sha256).hexdigest()
    signatures = [v for k, v in (p.split("=", 1) for p in header.split(",") if "=" in p) if k == "v1"]
    if not any(hmac.compare_digest(expected, sig) for sig in signatures):
        return None
    try:
        return json.loads(payload)
    except ValueError:
        return None
