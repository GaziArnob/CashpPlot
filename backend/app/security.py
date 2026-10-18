"""Password hashing, JWT tokens and field-level encryption."""

import base64
import hashlib
import hmac
import os
import struct
import time
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from app.config import get_settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def create_access_token(user_id: int) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=s.access_token_minutes),
    }
    return jwt.encode(payload, s.secret_key, algorithm=ALGORITHM)


def create_refresh_token(user_id: int) -> tuple[str, str, datetime]:
    """Returns (token, jti, expires_at). The jti is stored so tokens can be rotated and revoked."""
    s = get_settings()
    now = datetime.now(timezone.utc)
    jti = uuid.uuid4().hex
    expires = now + timedelta(days=s.refresh_token_days)
    payload = {"sub": str(user_id), "type": "refresh", "jti": jti, "iat": now, "exp": expires}
    return jwt.encode(payload, s.secret_key, algorithm=ALGORITHM), jti, expires


def decode_token(token: str, expected_type: str) -> dict | None:
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != expected_type:
        return None
    return payload


def _fernet() -> Fernet:
    s = get_settings()
    key = s.field_encryption_key
    if not key:
        key = base64.urlsafe_b64encode(hashlib.sha256(s.secret_key.encode()).digest()).decode()
    return Fernet(key.encode())


class EncryptedString(TypeDecorator):
    """Stores a string encrypted at rest; transparent to the rest of the app."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None or value == "":
            return value
        return _fernet().encrypt(value.encode()).decode()

    def process_result_value(self, value, dialect):
        if value is None or value == "":
            return value
        try:
            return _fernet().decrypt(value.encode()).decode()
        except InvalidToken:
            return None


# Two-factor authentication: time-based one-time codes (RFC 6238), compatible with Google Authenticator,
# Authy, 1Password and similar apps.

TOTP_STEP = 30
TOTP_DIGITS = 6


def new_totp_secret() -> str:
    return base64.b32encode(os.urandom(20)).decode().rstrip("=")


def _hotp(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 10 ** TOTP_DIGITS
    return f"{code:0{TOTP_DIGITS}d}"


def totp_code(secret: str, at: float | None = None) -> str:
    return _hotp(secret, int((time.time() if at is None else at) // TOTP_STEP))


def verify_totp(secret: str, code: str, at: float | None = None, window: int = 1) -> bool:
    """Accepts the current code and one step either side (clock drift)."""
    code = (code or "").strip().replace(" ", "")
    if len(code) != TOTP_DIGITS or not code.isdigit():
        return False
    counter = int((time.time() if at is None else at) // TOTP_STEP)
    return any(hmac.compare_digest(_hotp(secret, counter + d), code) for d in range(-window, window + 1))


def totp_uri(secret: str, email: str, issuer: str = "CashPilot") -> str:
    from urllib.parse import quote
    return f"otpauth://totp/{quote(issuer)}:{quote(email)}?secret={secret}&issuer={quote(issuer)}"
