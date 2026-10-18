from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import audit, auth_limiter, get_current_user
from app.models import Business, RefreshToken, User, utcnow
from app.schemas import BusinessOut, LoginIn, OnboardingIn, SignupIn, TokenOut, UserOut
from app.security import create_access_token, create_refresh_token, decode_token, hash_password, verify_password

router = APIRouter(tags=["auth"])

MAX_FAILED = 5
LOCK_MINUTES = 15
REFRESH_COOKIE = "refresh_token"


def _issue(db: Session, user: User, response: Response) -> TokenOut:
    s = get_settings()
    token, jti, expires = create_refresh_token(user.id)
    db.add(RefreshToken(user_id=user.id, jti=jti, expires_at=expires.replace(tzinfo=None)))
    db.commit()
    response.set_cookie(
        REFRESH_COOKIE, token, httponly=True, secure=s.cookie_secure, samesite="strict",
        max_age=s.refresh_token_days * 86400, path="/auth",
    )
    return TokenOut(access_token=create_access_token(user.id), expires_in=s.access_token_minutes * 60)


@router.post("/auth/signup", response_model=TokenOut, status_code=201, dependencies=[Depends(auth_limiter)])
def signup(body: SignupIn, response: Response, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(name=body.name, email=email, phone=body.phone, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    audit(db, "signup", email, user_id=user.id)
    return _issue(db, user, response)


@router.post("/auth/login", response_model=TokenOut, dependencies=[Depends(auth_limiter)])
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    email = body.email.lower()
    user = db.scalar(select(User).where(User.email == email))
    now = utcnow()
    if user and user.locked_until and user.locked_until > now:
        raise HTTPException(status.HTTP_423_LOCKED, "Account temporarily locked after failed logins. Try later.")
    if user is None or not verify_password(body.password, user.password_hash):
        if user:
            user.failed_logins += 1
            if user.failed_logins >= MAX_FAILED:
                user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
                user.failed_logins = 0
            db.commit()
            audit(db, "login_failed", email, user_id=user.id)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")
    user.failed_logins = 0
    user.locked_until = None
    db.commit()
    audit(db, "login", email, user_id=user.id)
    return _issue(db, user, response)


@router.post("/auth/refresh", response_model=TokenOut, dependencies=[Depends(auth_limiter)])
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    # Custom header: a cross-site form can't set it, which blocks CSRF on this cookie-auth route.
    if request.headers.get("x-requested-with") != "fetch":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing X-Requested-With: fetch header")
    token = request.cookies.get(REFRESH_COOKIE)
    payload = decode_token(token, "refresh") if token else None
    if payload is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    row = db.scalar(select(RefreshToken).where(RefreshToken.jti == payload["jti"]))
    if row is None or row.revoked or row.expires_at < utcnow():
        if row is not None:  # a reused, rotated token: revoke the whole family
            for t in db.scalars(select(RefreshToken).where(RefreshToken.user_id == row.user_id)):
                t.revoked = True
            db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token expired or revoked")
    row.revoked = True  # rotation: each refresh token works once
    db.commit()
    user = db.get(User, row.user_id)
    return _issue(db, user, response)


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(REFRESH_COOKIE)
    payload = decode_token(token, "refresh") if token else None
    if payload:
        row = db.scalar(select(RefreshToken).where(RefreshToken.jti == payload["jti"]))
        if row:
            row.revoked = True
            db.commit()
    response.delete_cookie(REFRESH_COOKIE, path="/auth")
    return Response(status_code=204)


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/onboarding", response_model=BusinessOut, status_code=201)
def onboarding(body: OnboardingIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if db.scalar(select(Business).where(Business.user_id == user.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Business already set up; edit it in Settings")
    business = Business(user_id=user.id, **body.model_dump())
    db.add(business)
    db.commit()
    audit(db, "onboarding", user.email, business_id=business.id, user_id=user.id)
    return business
