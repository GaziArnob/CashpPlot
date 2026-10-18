"""Shared request dependencies: auth, tenant scoping, rate limiting, audit."""

import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import plans
from app.db import get_db
from app.models import AuditLog, Business, User
from app.security import decode_token

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    payload = decode_token(creds.credentials, "access")
    if payload is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


def get_business(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Business:
    """The caller's business. Its id comes from the token's user, never from the request.

    An owner has their own business; a staff member works inside their owner's business.
    """
    if user.role == "staff":
        business = db.get(Business, user.employer_business_id) if user.employer_business_id else None
    else:
        business = db.scalar(select(Business).where(Business.user_id == user.id).order_by(Business.id))
    if business is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Onboarding required: create your business first")
    return business


def require_owner(user: User = Depends(get_current_user)) -> User:
    """Staff can record sales, customers and invoices but nothing about credit, loans, settings or the team."""
    if user.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the business owner can do this")
    return user


def needs(feature: str):
    """Dependency: the business's plan must include `feature`, otherwise 402 with an upgrade message."""

    def check(business: Business = Depends(get_business)) -> None:
        if not plans.can_use(business, feature):
            raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED,
                                f"Upgrade to Pro to use this: {plans.PRO_FEATURES[feature]}")

    return check


def owned(db: Session, model, obj_id: int, business: Business):
    """Object-level check: fetch a record only if it belongs to the caller's business."""
    obj = db.get(model, obj_id)
    if obj is None or getattr(obj, "business_id", None) != business.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} not found")
    return obj


def audit(db: Session, action: str, actor: str, *, business_id=None, user_id=None, target=None) -> None:
    db.add(AuditLog(action=action, actor=actor, business_id=business_id, user_id=user_id, target=target))
    db.commit()


class RateLimiter:
    """In-memory sliding-window limiter. Swap for Redis when running several workers."""

    def __init__(self, limit: int, window_seconds: int, scope: str):
        self.limit = limit
        self.window = window_seconds
        self.scope = scope
        self.hits: dict[str, deque] = defaultdict(deque)

    def __call__(self, request: Request) -> None:
        key = request.client.host if request.client else "unknown"
        auth = request.headers.get("authorization", "")
        if auth:
            key += ":" + auth[-16:]
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Too many {self.scope} requests, slow down")
        q.append(now)

    def reset(self) -> None:
        self.hits.clear()


auth_limiter = RateLimiter(10, 60, "auth")
ai_limiter = RateLimiter(20, 60, "AI")
upload_limiter = RateLimiter(10, 60, "upload")
