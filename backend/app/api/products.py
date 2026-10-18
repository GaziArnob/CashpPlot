"""Products, item-level sales, stock movements and product performance."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import services
from app.db import get_db
from app.deps import get_business, owned
from app.models import Business, Invoice, Product, SaleItem, StockMovement, Transaction
from app.schemas import ProductIn, ProductOut, ProductUpdate, SaleItemIn, SaleItemOut, StockMovementIn

router = APIRouter(tags=["products"])


@router.get("/products", response_model=list[ProductOut])
def list_products(include_inactive: bool = False, business: Business = Depends(get_business),
                  db: Session = Depends(get_db)):
    stmt = select(Product).where(Product.business_id == business.id)
    if not include_inactive:
        stmt = stmt.where(Product.is_active.is_(True))
    return db.scalars(stmt.order_by(Product.name)).all()


@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(body: ProductIn, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    p = Product(business_id=business.id, **body.model_dump())
    db.add(p)
    db.flush()
    if body.stock_qty:
        db.add(StockMovement(business_id=business.id, product_id=p.id, date=services.today(), qty=body.stock_qty,
                             unit_cost=body.unit_cost, reason="adjustment"))
    db.commit()
    return p


@router.put("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: int, body: ProductUpdate, business: Business = Depends(get_business),
                   db: Session = Depends(get_db)):
    p = owned(db, Product, product_id, business)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(p, k, v)
    db.commit()
    return p


@router.get("/products/performance")
def product_performance(business: Business = Depends(get_business), db: Session = Depends(get_db)):
    """Metrics, class and a cash-aware stock plan per product; saved as today's snapshot."""
    result = services.product_scores(db, business, persist=True)
    return {"as_of": services.today().isoformat(), "currency": business.currency, **result}


@router.get("/sale-items", response_model=list[SaleItemOut])
def list_sale_items(product_id: int | None = None, limit: int = Query(100, ge=1, le=1000),
                    business: Business = Depends(get_business), db: Session = Depends(get_db)):
    stmt = select(SaleItem).where(SaleItem.business_id == business.id)
    if product_id:
        stmt = stmt.where(SaleItem.product_id == product_id)
    return db.scalars(stmt.order_by(SaleItem.date.desc(), SaleItem.id.desc()).limit(limit)).all()


@router.post("/sale-items", response_model=SaleItemOut, status_code=201)
def record_sale(body: SaleItemIn, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    """Record one product line sold. Cash sales also book the cash in; credit sales attach to an invoice."""
    p = owned(db, Product, body.product_id, business)
    if body.qty > p.stock_qty + 1e-9:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Only {p.stock_qty:g} in stock")
    if body.payment_type == "credit":
        if body.invoice_id is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A credit sale needs an invoice_id")
        owned(db, Invoice, body.invoice_id, business)
    price = body.unit_price if body.unit_price is not None else p.unit_price
    item = SaleItem(business_id=business.id, product_id=p.id, date=body.date, qty=body.qty, unit_price=price,
                    unit_cost=p.unit_cost, payment_type=body.payment_type,
                    invoice_id=body.invoice_id if body.payment_type == "credit" else None)
    db.add(item)
    db.add(StockMovement(business_id=business.id, product_id=p.id, date=body.date, qty=-body.qty, reason="sale"))
    p.stock_qty -= body.qty
    if body.payment_type == "cash":
        db.add(Transaction(business_id=business.id, date=body.date, amount=body.qty * price, type="income",
                           category="Sales", description=f"{body.qty:g} x {p.name}", source="manual"))
    db.commit()
    return item


@router.post("/stock-movements", status_code=201)
def record_stock_movement(body: StockMovementIn, business: Business = Depends(get_business),
                          db: Session = Depends(get_db)):
    p = owned(db, Product, body.product_id, business)
    if body.reason == "purchase" and body.qty <= 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A purchase adds stock: qty must be positive")
    if body.reason == "write_off" and body.qty >= 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A write-off removes stock: qty must be negative")
    if p.stock_qty + body.qty < -1e-9:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Stock can't go below zero (on hand {p.stock_qty:g})")
    cost = body.unit_cost if body.unit_cost is not None else p.unit_cost
    db.add(StockMovement(business_id=business.id, product_id=p.id, date=body.date, qty=body.qty,
                         unit_cost=cost, reason=body.reason))
    p.stock_qty += body.qty
    if body.reason == "purchase":
        p.unit_cost = cost  # latest purchase cost becomes the current cost
        if body.paid_in_cash:
            db.add(Transaction(business_id=business.id, date=body.date, amount=body.qty * cost, type="expense",
                               category="Inventory", description=f"Stock: {body.qty:g} x {p.name}",
                               source="manual"))
    db.commit()
    return {"product_id": p.id, "stock_qty": p.stock_qty, "unit_cost": p.unit_cost}
