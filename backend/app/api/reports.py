"""Reports, insights, goals and notifications."""

import io

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import services
from app.db import get_db
from app.deps import audit, get_business, needs, owned, require_owner
from app.models import Business, Goal
from app.schemas import GoalIn, GoalOut

router = APIRouter(tags=["reports"], dependencies=[Depends(require_owner), Depends(needs("reports"))])


def _month(month: str | None) -> tuple[int, int]:
    if not month:
        t = services.today()
        return t.year, t.month
    try:
        y, m = (int(x) for x in month.split("-"))
        if not 1 <= m <= 12:
            raise ValueError
        return y, m
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "month must look like 2026-10")


@router.get("/reports/pnl")
def pnl(month: str | None = Query(None, max_length=7), business: Business = Depends(get_business),
        db: Session = Depends(get_db)):
    y, m = _month(month)
    return services.pnl(db, business, y, m)


@router.get("/reports/insights")
def insights(business: Business = Depends(get_business), db: Session = Depends(get_db)):
    return services.spending_insights(db, business)


@router.get("/reports/export")
def export_pdf(month: str | None = Query(None, max_length=7), business: Business = Depends(get_business),
               db: Session = Depends(get_db)):
    y, m = _month(month)
    report = services.pnl(db, business, y, m)
    credit = services.credit_score(db, business, store=False)
    cur = business.currency

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    x, yy = 20 * mm, height - 25 * mm

    def line(text, size=10, bold=False, gap=6):
        nonlocal yy
        if yy < 25 * mm:
            c.showPage()
            yy = height - 25 * mm
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(x, yy, text)
        yy -= gap * mm

    line(f"{business.name}: Profit & Loss, {report['month']}", 16, True, 10)
    line(f"Total income: {report['total_income']:,} {cur}", 11, True)
    for k, v in report["income"].items():
        line(f"    {k}: {v:,} {cur}")
    yy -= 3 * mm
    line(f"Total expense: {report['total_expense']:,} {cur}", 11, True)
    for k, v in report["expense"].items():
        line(f"    {k}: {v:,} {cur}")
    yy -= 3 * mm
    margin = f" ({report['margin_pct']}% margin)" if report["margin_pct"] is not None else ""
    line(f"Net profit: {report['net_profit']:,} {cur}{margin}", 12, True, 10)
    line(f"Credit score: {credit['score']} ({credit['band']})", 11, True)
    for r in credit["reasons_positive"] + credit["reasons_negative"]:
        line(f"    {r}", 9)
    c.showPage()
    c.save()
    buf.seek(0)
    audit(db, "report_export", business.owner.email, business_id=business.id, target=report["month"])
    filename = f"pnl-{report['month']}.pdf"
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/goals", response_model=list[GoalOut])
def list_goals(business: Business = Depends(get_business), db: Session = Depends(get_db)):
    return db.scalars(select(Goal).where(Goal.business_id == business.id)).all()


@router.post("/goals", response_model=GoalOut, status_code=201)
def create_goal(body: GoalIn, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    g = Goal(business_id=business.id, **body.model_dump())
    db.add(g)
    db.commit()
    return g


@router.put("/goals/{goal_id}", response_model=GoalOut)
def update_goal(goal_id: int, body: GoalIn, business: Business = Depends(get_business),
                db: Session = Depends(get_db)):
    g = owned(db, Goal, goal_id, business)
    for k, v in body.model_dump().items():
        setattr(g, k, v)
    db.commit()
    return g


@router.delete("/goals/{goal_id}", status_code=204)
def delete_goal(goal_id: int, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    db.delete(owned(db, Goal, goal_id, business))
    db.commit()
