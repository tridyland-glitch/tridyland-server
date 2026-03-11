from app.core.security import get_api_key
from app.models.product import Product
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from app.core.database import get_db
from app.models.inventory import InventoryMovement, MovementType, StageLocation
from app.schemas.inventory import MovementCreate, MovementResponse, SmartInventoryRequest

router = APIRouter()

@router.post("/", dependencies=[Depends(get_api_key)], response_model=MovementResponse)
def create_movement(movement: MovementCreate, db: Session = Depends(get_db)):
    # Logica simple: Insertar el movimiento
    # Aqui podriamos agregar logica extra como validar stock negativo

    if movement.type in [MovementType.VENTA, MovementType.MERMA_INTERNA, MovementType.REGALO_MARKETING]:
        # Si viene positivo (ej: 5), lo volvemos negativo (ej: -5)
        if movement.quantity > 0:
            movement.quantity = movement.quantity * -1
    
    db_obj = InventoryMovement(**movement.model_dump())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

@router.get("/stock/{product_id}", dependencies=[Depends(get_api_key)])
def get_current_stock(product_id: int, db: Session = Depends(get_db)):
    # Ejemplo de consulta de stock calculado
    # En produccion usar Views o queries mas complejos
    movements = db.query(InventoryMovement).filter(InventoryMovement.product_id == product_id).all()
    total = sum(m.quantity for m in movements)
    return {"product_id": product_id, "current_stock": total}

@router.post("/physical-count", dependencies=[Depends(get_api_key)])
def set_physical_stock(
    product_id: int = Body(...), 
    actual_quantity: int = Body(...), 
    db: Session = Depends(get_db)
):
    """
    Tú dices: 'Tengo 5 reales'.
    El sistema: Calcula que tenía 2 en DB, así que crea un ajuste de +3.
    """
    # 1. Calcular stock actual en DB
    current_movements = db.query(InventoryMovement).filter(InventoryMovement.product_id == product_id).all()
    current_db_stock = sum(m.quantity for m in current_movements)
    
    # 2. Calcular la diferencia necesaria
    diff = actual_quantity - current_db_stock
    
    if diff == 0:
        return {"message": "El stock ya estaba correcto. No se hicieron cambios.", "stock": actual_quantity}

    # 3. Crear el movimiento de ajuste (Positivo o Negativo)
    adjustment = InventoryMovement(
        product_id=product_id,
        type=MovementType.AJUSTE_INVENTARIO,
        stage=StageLocation.TIENDA,
        quantity=diff,
        monetary_value=0, # El ajuste no impacta caja, solo inventario
        notes="Conteo Físico Real"
    )
    
    db.add(adjustment)
    db.commit()
    
    return {
        "status": "updated",
        "previous_stock": current_db_stock,
        "adjustment": diff,
        "new_stock": actual_quantity
    }

@router.post("/smart-update", dependencies=[Depends(get_api_key)])
def smart_inventory_update(
    req: SmartInventoryRequest, 
    db: Session = Depends(get_db)
):
    """
    Endpoint para el Asistente n8n.
    1. Busca productos similares.
    2. Si hay 1 exacto -> Actualiza stock.
    3. Si hay varios -> Retorna lista para que el Bot pregunte.
    4. Si no hay ninguno (y force_create=False) -> Pide confirmar creación.
    """
    
    # 1. Búsqueda Fuzzy simple (SQL ILIKE)
    # Mejoramos la búsqueda rompiendo el texto en palabras clave
    keywords = req.query_text.split()
    query = db.query(Product)
    for word in keywords:
        query = query.filter(Product.name.ilike(f"%{word}%"))
    
    matches = query.all()

    # CASO A: Ambigüedad (Encontró varios)
    if len(matches) > 1:
        return {
            "status": "ambiguous",
            "message": f"Encontré {len(matches)} productos similares.",
            "options": [
                {"id": p.id, "name": f"{p.name} ({p.size or '-'})"} 
                for p in matches
            ]
        }

    # CASO B: No existe (Crear nuevo)
    if len(matches) == 0:
        if not req.force_create:
            return {
                "status": "not_found", 
                "message": "No encontré ese producto. ¿Quieres crearlo?",
                "requires_action": "CREATE_NEW"
            }
        else:
            # Crear producto nuevo al vuelo
            new_prod = Product(
                name=req.query_text, # Usamos el texto de búsqueda como nombre provisional
                base_price=req.new_price,
                category=req.new_category,
                image_url=req.image_url
            )
            db.add(new_prod)
            db.commit()
            db.refresh(new_prod)
            matches = [new_prod] # Ahora ya existe

    # CASO C: Coincidencia Única (Actualizar Stock)
    product = matches[0]
    
    # Lógica de "Conteo Físico" (Setear stock, no sumar)
    # Reusamos la lógica de tu endpoint anterior
    current_stock = db.query(func.sum(InventoryMovement.quantity)).filter(
        InventoryMovement.product_id == product.id
    ).scalar() or 0
    
    diff = req.quantity - current_stock
    
    if diff != 0:
        adj = InventoryMovement(
            product_id=product.id,
            type=MovementType.AJUSTE_INVENTARIO,
            stage=StageLocation.TIENDA,
            quantity=diff,
            notes="Ajuste vía Asistente Voz/Foto"
        )
        db.add(adj)
        db.commit()

    return {
        "status": "success",
        "product_name": product.name,
        "new_stock": req.quantity,
        "image_saved": bool(product.image_url)
    }