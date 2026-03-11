from fastapi import APIRouter, Depends
from app.core.security import get_api_key
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional
from app.core.database import get_db
from app.models.product import Product
from app.models.inventory import InventoryMovement, MovementType, StageLocation

router = APIRouter()

# --- SCHEMAS PARA REPORTES ---
from pydantic import BaseModel

class StockReportItem(BaseModel):
    product_name: str
    size: Optional[str] = None # Permite nulos explícitamente
    category: Optional[str] = None
    current_stock: int
    potential_revenue: float

class TopSellerItem(BaseModel):
    product_name: str
    size: Optional[str] = None # Permite nulos explícitamente
    units_sold: int
    total_revenue: float

class MonthlySalesItem(BaseModel):
    month: str
    total_sales: int
    total_revenue: float

# --- ENDPOINTS ---

@router.get("/current-stock", dependencies=[Depends(get_api_key)], response_model=List[StockReportItem])
def get_store_valuation(db: Session = Depends(get_db)):
    """
    Reporte TIENDA: ¿Qué tengo listo para vender y cuánto vale?
    Filtra solo movimientos en ubicación 'TIENDA'.
    """
    results = db.query(
        Product.name,
        Product.size,
        Product.category,
        Product.base_price,
        func.sum(InventoryMovement.quantity).label("stock")
    ).join(
        InventoryMovement, Product.id == InventoryMovement.product_id
    ).filter(
        # 👇 EL FILTRO CLAVE: Solo Tienda
        InventoryMovement.stage == StageLocation.TIENDA
    ).group_by(
        Product.id, Product.name, Product.size, Product.category, Product.base_price
    ).having(
        func.sum(InventoryMovement.quantity) > 0
    ).all()

    report = []
    for r in results:
        stock = r.stock
        price = r.base_price or 0
        report.append({
            "product_name": r.name,
            "size": r.size,
            "category": r.category,
            "current_stock": stock,
            "potential_revenue": stock * price
        })
    
    # Ordenar por el que más lana te puede dar
    return sorted(report, key=lambda x: x['potential_revenue'], reverse=True)

@router.get("/workshop-stock", dependencies=[Depends(get_api_key)], response_model=List[StockReportItem])
def get_workshop_valuation(db: Session = Depends(get_db)):
    """
    Reporte TALLER: ¿Qué tengo en producción o bodega?
    Filtra solo movimientos en ubicación 'TALLER'.
    """
    results = db.query(
        Product.name,
        Product.size,
        Product.category,
        Product.base_price,
        func.sum(InventoryMovement.quantity).label("stock")
    ).join(
        InventoryMovement, Product.id == InventoryMovement.product_id
    ).filter(
        # 👇 EL FILTRO CLAVE: Solo Taller
        InventoryMovement.stage == StageLocation.TALLER
    ).group_by(
        Product.id, Product.name, Product.size, Product.category, Product.base_price
    ).having(
        func.sum(InventoryMovement.quantity) > 0
    ).all()

    report = []
    for r in results:
        stock = r.stock
        # Opcional: Podrías usar avg_cost en vez de base_price 
        # para saber el "Costo invertido" en lugar del "Precio venta"
        price = r.base_price or 0 
        
        report.append({
            "product_name": r.name,
            "size": r.size,
            "category": r.category,
            "current_stock": stock,
            "potential_revenue": stock * price
        })
    
    return sorted(report, key=lambda x: x['current_stock'], reverse=True)

@router.get("/top-sellers", dependencies=[Depends(get_api_key)], response_model=List[TopSellerItem])
def get_top_sellers(limit: int = 10, db: Session = Depends(get_db)):
    """
    Reporte 2: Tus Vacas Lecheras.
    CORREGIDO: Ahora incluye el .join() explícito.
    """
    results = db.query(
        Product.name,
        Product.size,
        func.sum(func.abs(InventoryMovement.quantity)).label("units"),
        func.sum(InventoryMovement.monetary_value).label("revenue")
    ).join(InventoryMovement, Product.id == InventoryMovement.product_id).filter( # <--- AQUÍ FALTABA EL JOIN
        InventoryMovement.type == MovementType.VENTA
    ).group_by(
        Product.id, Product.name, Product.size
    ).order_by(desc("revenue")).limit(limit).all()

    return [
        {
            "product_name": r.name,
            "size": r.size,
            "units_sold": int(r.units) if r.units else 0,
            "total_revenue": float(r.revenue) if r.revenue else 0.0
        }
        for r in results
    ]


@router.get("/monthly-sales", dependencies=[Depends(get_api_key)], response_model=List[MonthlySalesItem])
def get_monthly_sales(year: int = 2024, db: Session = Depends(get_db)):
    """
    Reporte 3: Crecimiento Mensual.
    """
    results = db.query(
        func.to_char(InventoryMovement.effective_date, 'YYYY-MM').label("month"),
        func.sum(func.abs(InventoryMovement.quantity)).label("units"),
        func.sum(InventoryMovement.monetary_value).label("revenue")
    ).filter(
        InventoryMovement.type == MovementType.VENTA,
        func.extract('year', InventoryMovement.effective_date) == year
    ).group_by("month").order_by("month").all()

    return [
        {
            "month": r.month, 
            "total_sales": int(r.units) if r.units else 0,
            "total_revenue": float(r.revenue) if r.revenue else 0.0
        }
        for r in results
    ]

@router.get("/kpis", dependencies=[Depends(get_api_key)])
def get_general_kpis(db: Session = Depends(get_db)):
    """
    KPIs Avanzados: Solo cuenta stock listo para venta (TIENDA).
    Ignora lo que está en TALLER.
    """
    # 1. KPIs Históricos (Ventas totales de por vida)
    # Aquí NO filtramos por tienda porque una venta es una venta, haya salido de donde haya salido.
    total_revenue = db.query(func.sum(InventoryMovement.monetary_value)).filter(InventoryMovement.type == MovementType.VENTA).scalar() or 0
    total_units_sold = db.query(func.sum(func.abs(InventoryMovement.quantity))).filter(InventoryMovement.type == MovementType.VENTA).scalar() or 0
    
    # 2. Stock Actual (SOLO TIENDA) 🏪
    # Aquí sí filtramos. Solo contamos lo que físicamente está en la TIENDA.
    total_stock_items = db.query(func.sum(InventoryMovement.quantity)).filter(
        InventoryMovement.stage == StageLocation.TIENDA  # <--- EL FILTRO CLAVE
    ).scalar() or 0
    
    # 3. Ticket Promedio
    total_sales_count = db.query(func.count(InventoryMovement.id)).filter(InventoryMovement.type == MovementType.VENTA).scalar() or 1
    avg_ticket = total_revenue / total_sales_count if total_sales_count > 0 else 0

    # 4. Valor Potencial del Inventario (SOLO TIENDA) 💎
    # Calculamos el stock por producto, pero SOLO sumando movimientos de TIENDA.
    stock_per_product = (
        db.query(
            InventoryMovement.product_id,
            func.sum(InventoryMovement.quantity).label("current_stock")
        )
        .filter(InventoryMovement.stage == StageLocation.TIENDA) # <--- FILTRO PARA IGNORAR TALLER
        .group_by(InventoryMovement.product_id)
        .subquery()
    )

    # Multiplicamos ese stock "limpio" por el precio base
    potential_stock_value = (
        db.query(func.sum(stock_per_product.c.current_stock * Product.base_price))
        .select_from(stock_per_product)
        .join(Product, Product.id == stock_per_product.c.product_id)
        .filter(stock_per_product.c.current_stock > 0)
        .scalar() or 0
    )

    # 5. Top Sellers (Histórico)
    top_products_query = (
        db.query(
            Product.name,
            func.sum(func.abs(InventoryMovement.quantity)).label("total_sold")
        )
        .join(InventoryMovement, InventoryMovement.product_id == Product.id)
        .filter(InventoryMovement.type == MovementType.VENTA)
        .group_by(Product.name)
        .order_by(desc("total_sold"))
        .limit(3)
        .all()
    )
    top_products = [{"name": p.name, "units": p.total_sold} for p in top_products_query]

    # 6. Desglose por Categoría (Histórico de ventas)
    category_revenue = (
        db.query(
            Product.category,
            func.sum(InventoryMovement.monetary_value).label("revenue")
        )
        .join(InventoryMovement, InventoryMovement.product_id == Product.id)
        .filter(InventoryMovement.type == MovementType.VENTA)
        .group_by(Product.category)
        .all()
    )
    category_stats = {(c.category or "Sin Categoría"): c.revenue for c in category_revenue}

    return {
        "summary": {
            "lifetime_revenue": total_revenue,
            "lifetime_units_sold": total_units_sold,
            "avg_ticket": round(avg_ticket, 2),
            "current_stock_count_store": total_stock_items, # Le cambié el nombre para que sea claro
            "potential_inventory_value_store": round(potential_stock_value, 2) # Valor real vendible
        },
        "top_sellers": top_products,
        "revenue_by_category": category_stats
    }