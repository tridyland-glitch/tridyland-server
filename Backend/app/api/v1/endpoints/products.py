from app.core.security import get_api_key
from app.models.inventory import InventoryMovement, MovementType, StageLocation
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductUpdate, Product as ProductSchema
from sqlalchemy import or_, func, and_, case
from unidecode import unidecode
from fastapi import BackgroundTasks

router = APIRouter()

@router.post("/", dependencies=[Depends(get_api_key)], response_model=ProductSchema)
def create_product(product: ProductCreate, db: Session = Depends(get_db)):
    # Verificar duplicados
    existing = db.query(Product).filter(
        Product.name == product.name, 
        Product.size == product.size
    ).first()
    if existing:
        return existing
        
    db_product = Product(**product.model_dump())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product

@router.get("/", dependencies=[Depends(get_api_key)], response_model=List[ProductSchema])
def read_products(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(Product).offset(skip).limit(limit).all()

# Endpoint especial para el Voice Assistant (Busqueda Fuzzy)
@router.get("/search", dependencies=[Depends(get_api_key)], response_model=List[ProductSchema])
def search_products(
    q: str = Query(..., min_length=1, description="Búsqueda detallada: Tienda vs Taller"),
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """
    Búsqueda con desglose de inventario:
    1. Stock Tienda (Vendible): Suma de movimientos donde location='TIENDA'.
    2. Stock Taller (Producción): Suma de movimientos donde location='TALLER'.
    3. Ventas y Dinero.
    """
    
    # --- A. DEFINICIÓN DE MÉTRICAS SQL ---

    # 1. STOCK TIENDA (Vendible): Suma solo lo que ocurre en TIENDA
    stock_tienda_calc = func.coalesce(
        func.sum(
            case(
                (InventoryMovement.stage == StageLocation.TIENDA, InventoryMovement.quantity),
                else_=0
            )
        ), 0
    ).label("stock_tienda")

    # 2. STOCK TALLER (En Proceso): Suma solo lo que ocurre en TALLER
    stock_taller_calc = func.coalesce(
        func.sum(
            case(
                (InventoryMovement.stage == StageLocation.TALLER, InventoryMovement.quantity),
                else_=0
            )
        ), 0
    ).label("stock_taller")

    # 3. ITEMS VENDIDOS (Histórico): Igual que antes
    sales_calc = func.coalesce(
        func.sum(
            case(
                (InventoryMovement.type == MovementType.VENTA, func.abs(InventoryMovement.quantity)),
                else_=0
            )
        ), 0
    ).label("items_sold")

    # --- B. QUERY ---
    raw_results = db.query(Product, stock_tienda_calc, stock_taller_calc, sales_calc)\
        .outerjoin(InventoryMovement, Product.id == InventoryMovement.product_id)\
        .group_by(Product.id)\
        .all()
    
    # --- C. PYTHON FILTERING (Aquí está la magia) ---
    
    query_str = q.strip()
    # Detectamos si lo que escribió el usuario es un número entero (ID)
    is_id_search = query_str.isdigit()
    target_id = int(query_str) if is_id_search else -1

    search_terms = unidecode(query_str).lower().split()
    final_results = []
    
    for product, stock_tienda, stock_taller, sold in raw_results:
        
        # 1. CRITERIO DE ID: Si es número y coincide, ¡es este!
        match_id = False
        if is_id_search and product.id == target_id:
            match_id = True

        # 2. CRITERIO DE TEXTO: La búsqueda de siempre
        match_text = False
        if not match_id: # Si ya encontramos por ID, nos ahorramos procesar texto
            searchable_text = unidecode(
                f"{product.name} {product.category} {product.franchise or ''} {product.size or ''}"
            ).lower()
            
            # Verificamos si todos los términos están en el texto
            if all(term in searchable_text for term in search_terms):
                match_text = True
        
        # SI CUMPLE CUALQUIERA DE LOS DOS
        if match_id or match_text:
            prod_data = product.__dict__
            
            # Asignamos los stocks separados
            prod_data["current_stock"] = stock_tienda
            prod_data["stock_taller"] = stock_taller
            
            prod_data["items_sold"] = sold
            prod_data["total_generated"] = sold * (product.base_price or 0)
            
            final_results.append(prod_data)
            
            if len(final_results) >= limit:
                break
    
    return final_results

@router.patch("/{product_id}", dependencies=[Depends(get_api_key)], response_model=ProductSchema)
def update_product(
    product_id: int, 
    product_in: ProductUpdate, 
    db: Session = Depends(get_db)
):
    """
    Actualiza parcialmente un producto (PATCH).
    Solo envía los campos que quieras cambiar.
    """
    # 1. Buscar
    db_product = db.query(Product).filter(Product.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    
    # 2. Detectar cambios (Soporta Pydantic v1 y v2)
    # Intenta usar model_dump (v2), si falla usa dict (v1)
    if hasattr(product_in, 'model_dump'):
        update_data = product_in.model_dump(exclude_unset=True)
    else:
        update_data = product_in.dict(exclude_unset=True)
    
    # 3. Aplicar cambios
    for field, value in update_data.items():
        setattr(db_product, field, value)
    
    # 4. Guardar
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product