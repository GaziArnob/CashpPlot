"""Plaid: link a bank, then import its transactions into CashPilot. Start with PLAID_ENV=sandbox (fake banks).

The owner starts every connection and every sync. The access token stays on the server, encrypted.
"""

import httpx

from app.config import get_settings

TIMEOUT = 20.0


class BankError(Exception):
    """Plaid refused or could not be reached. The message is safe to show the owner."""


def configured() -> bool:
    s = get_settings()
    return bool(s.plaid_client_id and s.plaid_secret)


def _base() -> str:
    return "https://production.plaid.com" if get_settings().plaid_env == "production" else "https://sandbox.plaid.com"


def _call(path: str, payload: dict) -> dict:
    s = get_settings()
    if not configured():
        raise BankError("Bank connection is not configured")
    try:
        r = httpx.post(_base() + path, timeout=TIMEOUT,
                       json={"client_id": s.plaid_client_id, "secret": s.plaid_secret, **payload})
    except httpx.HTTPError:
        raise BankError("Could not reach the bank connection service")
    if r.status_code >= 300:
        try:
            msg = r.json().get("error_message") or "request failed"
        except ValueError:
            msg = "request failed"
        raise BankError(f"The bank connection service said: {msg}")
    return r.json()


def create_link_token(business_id: int) -> str:
    return _call("/link/token/create", {
        "client_name": "CashPilot", "language": "en", "country_codes": ["US"],
        "user": {"client_user_id": str(business_id)}, "products": ["transactions"],
    })["link_token"]


def exchange_public_token(public_token: str) -> tuple[str, str]:
    data = _call("/item/public_token/exchange", {"public_token": public_token})
    return data["access_token"], data["item_id"]


def remove_item(access_token: str) -> None:
    _call("/item/remove", {"access_token": access_token})


def sync(access_token: str, cursor: str | None) -> dict:
    """Everything new since `cursor`: {added, modified, removed, cursor}. Pages are followed to the end."""
    added, modified, removed = [], [], []
    while True:
        payload = {"access_token": access_token, "count": 500}
        if cursor:
            payload["cursor"] = cursor
        data = _call("/transactions/sync", payload)
        added += data.get("added", [])
        modified += data.get("modified", [])
        removed += [x["transaction_id"] for x in data.get("removed", [])]
        cursor = data["next_cursor"]
        if not data.get("has_more"):
            return {"added": added, "modified": modified, "removed": removed, "cursor": cursor}


def to_row(t: dict, currency: str) -> dict | None:
    """A Plaid transaction as a CashPilot row, or None to skip it (pending, other currency, zero)."""
    if t.get("pending") or (t.get("iso_currency_code") or currency).upper() != currency.upper():
        return None
    amount = float(t["amount"])
    if amount == 0:
        return None
    category = (t.get("personal_finance_category") or {}).get("primary") or "BANK"
    return {
        "external_id": t["transaction_id"][:64], "date": t["date"], "amount": abs(amount),
        "type": "expense" if amount > 0 else "income",  # Plaid: positive means money out
        "category": category.replace("_", " ").title()[:60],
        "description": (t.get("merchant_name") or t.get("name") or "")[:255] or None,
    }
