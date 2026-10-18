"""Cash Advisor: one call for the gap card, forecast, collections, products, plan and AI advice."""

from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import services
from app.db import get_db
from app.deps import ai_limiter, get_business
from app.jobs import daily
from app.models import Business

router = APIRouter(tags=["cash advisor"])


@router.get("/cash-advisor/summary", dependencies=[Depends(ai_limiter)])
def cash_advisor_summary(lang: Literal["en", "bn"] = "en", business: Business = Depends(get_business),
                         db: Session = Depends(get_db)):
    return services.advisor_summary(db, business, lang)


@router.post("/jobs/daily/run")
def run_daily_job_now(business: Business = Depends(get_business), db: Session = Depends(get_db)):
    """Run today's job for your own business now (the scheduler runs it for everyone each morning)."""
    return daily.run_for_business(db, business)
