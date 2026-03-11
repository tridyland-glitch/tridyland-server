from fastapi import APIRouter, Depends
from app.core.security import get_api_key
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, case
from typing import List, Any
from datetime import datetime
from app.core.database import get_db
from app.models.expense import Expense, ExpenseCategory
from app.models.inventory import InventoryMovement, MovementType

router = APIRouter()

# --- SCHEMAS RAPIDOS (Para documentar la respuesta) ---
from pydantic import BaseModel

class CategoryReportItem(BaseModel):
    category: str
    total: float
    percentage: float

class SupplierReportItem(BaseModel):
    supplier: str
    total: float
    transaction_count: int

class MonthlyPnLItem(BaseModel):
    month: str      # "2024-08"
    revenue: float  # Ventas
    expenses: float # Gastos
    net_profit: float # Ganancia Neta
    profit_margin: float # Margen %

# --- ENDPOINT 1: GASTOS POR CATEGORÍA (El Pay de Queso) ---
@router.get("/expenses-by-category", dependencies=[Depends(get_api_key)], response_model=List[CategoryReportItem])
def get_expenses_by_category(db: Session = Depends(get_db)):
    """
    Desglose total de en qué se ha ido el dinero históricamente.
    Ideal para gráficas de pastel.
    """
    # 1. Calcular el gran total para sacar porcentajes
    total_spent = db.query(func.sum(Expense.amount)).scalar() or 0.0
    
    # 2. Agrupar por categoría
    results = db.query(
        Expense.category,
        func.sum(Expense.amount).label("total")
    ).group_by(Expense.category).order_by(desc("total")).all()
    
    report = []
    for cat, amount in results:
        pct = (amount / total_spent * 100) if total_spent > 0 else 0
        report.append({
            "category": cat.value, # .value para obtener el string del Enum
            "total": round(amount, 2),
            "percentage": round(pct, 1)
        })
        
    return report

# --- ENDPOINT 2: TOP PROVEEDORES (¿Quién se lleva mi dinero?) ---
@router.get("/top-suppliers", dependencies=[Depends(get_api_key)], response_model=List[SupplierReportItem])
def get_top_suppliers(limit: int = 10, db: Session = Depends(get_db)):
    """
    Ranking de proveedores donde más gastas.
    Sirve para negociar precios o ver dependencias.
    """
    # Normalizamos un poco el proveedor (Mayúsculas y quitar espacios)
    # Nota: Si tienes "Amazon" y "amazon mx", idealmente se limpiarían antes, 
    # pero aquí agrupamos directo.
    results = db.query(
        Expense.supplier,
        func.sum(Expense.amount).label("total"),
        func.count(Expense.id).label("tx_count")
    ).filter(Expense.supplier != None)\
     .group_by(Expense.supplier)\
     .order_by(desc("total"))\
     .limit(limit).all()
    
    return [
        {"supplier": row.supplier, "total": row.total, "transaction_count": row.tx_count}
        for row in results
    ]

# --- ENDPOINT 3: P&L MENSUAL (La Verdad Duele o Alegra) ---
@router.get("/monthly-pnl", dependencies=[Depends(get_api_key)], response_model=List[MonthlyPnLItem])
def get_monthly_pnl(year: int = 2024, db: Session = Depends(get_db)):
    """
    Estado de Resultados Mensual (Profit & Loss).
    Cruza VENTAS (InventoryMovement) vs GASTOS (Expense).
    """
    # A. Obtener Ventas por Mes
    sales_query = db.query(
        func.to_char(InventoryMovement.created_at, 'YYYY-MM').label('month'),
        func.sum(InventoryMovement.monetary_value).label('revenue')
    ).filter(
        InventoryMovement.type == MovementType.VENTA,
        func.extract('year', InventoryMovement.created_at) == year
    ).group_by('month').all()

    # B. Obtener Gastos por Mes
    expenses_query = db.query(
        func.to_char(Expense.date, 'YYYY-MM').label('month'),
        func.sum(Expense.amount).label('total_expense')
    ).filter(
        func.extract('year', Expense.date) == year
    ).group_by('month').all()

    # C. Convertir a Diccionarios para fusionar fácil
    sales_map = {row.month: row.revenue for row in sales_query}
    expenses_map = {row.month: row.total_expense for row in expenses_query}
    
    # D. Unificar meses (puede haber meses con gastos y sin ventas, o viceversa)
    all_months = sorted(set(list(sales_map.keys()) + list(expenses_map.keys())))
    
    report = []
    for m in all_months:
        rev = sales_map.get(m, 0.0)
        exp = expenses_map.get(m, 0.0)
        net = rev - exp
        
        # Margen = (Ganancia / Venta) * 100
        margin = (net / rev * 100) if rev > 0 else 0.0
        
        report.append({
            "month": m,
            "revenue": round(rev, 2),
            "expenses": round(exp, 2),
            "net_profit": round(net, 2),
            "profit_margin": round(margin, 1)
        })
        
    return report