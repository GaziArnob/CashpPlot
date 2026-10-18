import csv
import io
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import ocr
from app.db import get_db
from app.deps import get_business, owned, upload_limiter
from app.models import Business, Transaction
from app.schemas import TransactionIn, TransactionOut

router = APIRouter(prefix="/transactions", tags=["transactions"])

MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
CSV_ALIASES = {
    "date": ("date", "transaction date", "txn date"),
    "amount": ("amount", "value", "amount (bdt)"),
    "type": ("type", "direction", "dr/cr"),
    "category": ("category", "purpose"),
    "description": ("description", "details", "narration", "remarks"),
}


@router.get("")
def list_transactions(
    business: Business = Depends(get_business), db: Session = Depends(get_db),
    type: str | None = Query(None, pattern="^(income|expense)$"),
    category: str | None = Query(None, max_length=60),
    q: str | None = Query(None, max_length=100),
    date_from: date | None = None, date_to: date | None = None,
    limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
):
    stmt = select(Transaction).where(Transaction.business_id == business.id)
    if type:
        stmt = stmt.where(Transaction.type == type)
    if category:
        stmt = stmt.where(Transaction.category == category)
    if q:
        stmt = stmt.where(Transaction.description.ilike(f"%{q}%"))
    if date_from:
        stmt = stmt.where(Transaction.date >= date_from)
    if date_to:
        stmt = stmt.where(Transaction.date <= date_to)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Transaction.date.desc(), Transaction.id.desc()).limit(limit).offset(offset))
    return {"total": total, "items": [TransactionOut.model_validate(t) for t in rows]}


@router.get("/categories")
def categories(business: Business = Depends(get_business), db: Session = Depends(get_db)):
    rows = db.execute(select(Transaction.type, Transaction.category).where(
        Transaction.business_id == business.id).distinct())
    out: dict[str, list[str]] = {"income": [], "expense": []}
    for t, c in rows:
        out[t].append(c)
    return {k: sorted(v) for k, v in out.items()}


@router.post("", response_model=TransactionOut, status_code=201)
def create_transaction(body: TransactionIn, business: Business = Depends(get_business),
                       db: Session = Depends(get_db)):
    t = Transaction(business_id=business.id, **body.model_dump())
    db.add(t)
    db.commit()
    return t


@router.delete("/{txn_id}", status_code=204)
def delete_transaction(txn_id: int, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    db.delete(owned(db, Transaction, txn_id, business))
    db.commit()


def _col(header: list[str], field: str) -> int | None:
    lowered = [h.strip().lower() for h in header]
    for alias in CSV_ALIASES[field]:
        if alias in lowered:
            return lowered.index(alias)
    return None


def _parse_date(s: str) -> date:
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%d %b %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognized date {s!r}")


@router.post("/import", dependencies=[Depends(upload_limiter)])
async def import_csv(file: UploadFile = File(...), business: Business = Depends(get_business),
                     db: Session = Depends(get_db)):
    """Import a CSV (or a mobile-wallet statement exported as CSV).

    Needs date and amount columns. Type comes from a type column (income/expense, cr/dr)
    or from the amount's sign.
    """
    raw = await file.read(MAX_CSV_BYTES + 1)
    if len(raw) > MAX_CSV_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "CSV larger than 2 MB")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "CSV must be UTF-8 text")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file")
    header, body = rows[0], rows[1:]
    idx = {f: _col(header, f) for f in CSV_ALIASES}
    if idx["date"] is None or idx["amount"] is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "CSV needs 'date' and 'amount' columns")

    created, errors = 0, []
    for n, row in enumerate(body, start=2):
        if not any(c.strip() for c in row):
            continue
        try:
            d = _parse_date(row[idx["date"]])
            amount = float(row[idx["amount"]].replace(",", "").strip())
            kind = row[idx["type"]].strip().lower() if idx["type"] is not None else ""
            if kind in ("income", "credit", "cr", "in"):
                t = "income"
            elif kind in ("expense", "debit", "dr", "out"):
                t = "expense"
            else:
                t = "income" if amount >= 0 else "expense"
            amount = abs(amount)
            if amount == 0:
                raise ValueError("zero amount")
            category = (row[idx["category"]].strip() if idx["category"] is not None else "") or \
                ("Sales" if t == "income" else "Other")
            desc = row[idx["description"]].strip()[:255] if idx["description"] is not None else None
            db.add(Transaction(business_id=business.id, date=d, amount=amount, type=t,
                               category=category[:60], description=desc, source="csv"))
            created += 1
        except (ValueError, IndexError) as e:
            if len(errors) < 20:
                errors.append({"line": n, "error": str(e)})
    db.commit()
    return {"imported": created, "skipped": len(body) - created, "errors": errors}


@router.post("/scan", dependencies=[Depends(upload_limiter)])
async def scan_receipt(file: UploadFile = File(...), business: Business = Depends(get_business)):
    """Read a receipt image. Returns a suggested expense; nothing is saved until the owner confirms."""
    if file.content_type not in IMAGE_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Upload a JPEG, PNG or WebP image")
    raw = await file.read(MAX_IMAGE_BYTES + 1)
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Image larger than 5 MB")
    try:
        result = ocr.scan(raw, file.content_type)
    except ocr.OCRUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    except Exception:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not read the receipt; enter it manually")
    return {"suggestion": {"type": "expense", "date": result.get("date"), "amount": result.get("amount"),
                           "category": result.get("category") or "Other",
                           "description": result.get("vendor"), "source": "scan"},
            "engine": result.get("engine")}
