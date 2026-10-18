"""Team: the owner adds staff who can record sales, customers and invoices, and nothing else."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import audit, get_business, require_owner
from app.models import Business, RefreshToken, User
from app.security import hash_password

router = APIRouter(prefix="/team", tags=["team"], dependencies=[Depends(require_owner)])

MAX_STAFF = 10


class StaffIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class PasswordIn(BaseModel):
    password: str = Field(min_length=8, max_length=128)


def _out(u: User) -> dict:
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role, "active": u.is_active,
            "two_factor": u.totp_enabled, "created_at": u.created_at}


def _staff(db: Session, business: Business, user_id: int) -> User:
    u = db.get(User, user_id)
    if u is None or u.role != "staff" or u.employer_business_id != business.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team member not found")
    return u


def _sign_out_everywhere(db: Session, user: User) -> None:
    db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id).values(revoked=True))


@router.get("")
def list_team(business: Business = Depends(get_business), db: Session = Depends(get_db)):
    rows = db.scalars(select(User).where(User.role == "staff", User.employer_business_id == business.id)
                      .order_by(User.id)).all()
    return {"max_staff": MAX_STAFF, "members": [_out(u) for u in rows],
            "can_do": ["Record sales, expenses and stock", "Add customers, invoices and bills",
                       "Record payments received and made"],
            "cannot_do": ["See the credit score, loans or reports", "Use the Cash Advisor or AI assistant",
                          "Change settings, share data or manage the team"]}


@router.post("", status_code=201)
def add_staff(body: StaffIn, business: Business = Depends(get_business), owner: User = Depends(require_owner),
              db: Session = Depends(get_db)):
    """Create a staff login. The owner chooses the first password and passes it on in person."""
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    active = db.scalars(select(User).where(User.role == "staff", User.employer_business_id == business.id,
                                           User.is_active.is_(True))).all()
    if len(active) >= MAX_STAFF:
        raise HTTPException(status.HTTP_409_CONFLICT, f"You can have up to {MAX_STAFF} active staff")
    u = User(name=body.name, email=email, password_hash=hash_password(body.password), role="staff",
             employer_business_id=business.id)
    db.add(u)
    db.commit()
    audit(db, "staff_added", owner.email, business_id=business.id, user_id=owner.id, target=f"user:{u.id}")
    return _out(u)


@router.delete("/{user_id}")
def remove_staff(user_id: int, business: Business = Depends(get_business), owner: User = Depends(require_owner),
                 db: Session = Depends(get_db)):
    """Switch a staff login off straight away (their records stay)."""
    u = _staff(db, business, user_id)
    u.is_active = False
    _sign_out_everywhere(db, u)
    db.commit()
    audit(db, "staff_removed", owner.email, business_id=business.id, user_id=owner.id, target=f"user:{u.id}")
    return _out(u)


@router.post("/{user_id}/reactivate")
def reactivate_staff(user_id: int, business: Business = Depends(get_business), owner: User = Depends(require_owner),
                     db: Session = Depends(get_db)):
    u = _staff(db, business, user_id)
    u.is_active = True
    db.commit()
    audit(db, "staff_reactivated", owner.email, business_id=business.id, user_id=owner.id, target=f"user:{u.id}")
    return _out(u)


@router.post("/{user_id}/password")
def reset_staff_password(user_id: int, body: PasswordIn, business: Business = Depends(get_business),
                         owner: User = Depends(require_owner), db: Session = Depends(get_db)):
    u = _staff(db, business, user_id)
    u.password_hash = hash_password(body.password)
    u.failed_logins, u.locked_until = 0, None
    _sign_out_everywhere(db, u)
    db.commit()
    audit(db, "staff_password_reset", owner.email, business_id=business.id, user_id=owner.id, target=f"user:{u.id}")
    return _out(u)
