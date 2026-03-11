import csv
import codecs
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from app.core.security import get_api_key
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.product import Product
from app.models.inventory import InventoryMovement, MovementType, StageLocation

router = APIRouter()

def parse_csv_date(date_str: str, dependencies=[Depends(get_api_key)]) -> datetime:
    """
    Convierte fechas formato 'dd/mm/yyyy' (Ej: 22/09/2024).
    Retorna None si falla o está vacío.
    """
    if not date_str:
        return None
    try:
        # Limpiamos espacios extra
        clean_date = date_str.strip()
        # Parseamos formato dia/mes/año completo
        return datetime.strptime(clean_date, "%d/%m/%Y")
    except ValueError:
        return None

def clean_money(money_str: str) -> float:
    """
    Limpia formatos con punto de miles y coma decimal.
    Ej: "1.100,00" -> 1100.00
    Ej: "120,00" -> 120.00
    """
    if not money_str or str(money_str).strip() == "":
        return 0.0
    
    s = str(money_str).strip()
    # 1. Eliminar puntos de miles (1.100 -> 1100)
    s = s.replace(".", "")
    # 2. Cambiar coma decimal por punto (120,00 -> 120.00)
    s = s.replace(",", ".")
    
    try:
        return float(s)
    except ValueError:
        return 0.0

def clean_text(text: str):
    if not text:
        return None
    t = str(text).strip()
    return None if t in ["-", ""] else t

@router.post("/sales-csv", dependencies=[Depends(get_api_key)])
async def import_sales_csv(
    file: UploadFile = File(...), 
    db: Session = Depends(get_db)
):
    # Decodificar archivo
    csvReader = csv.DictReader(codecs.iterdecode(file.file, 'utf-8'))
    
    products_created = 0
    movements_created = 0
    row_count = 0
    
    # --- MEMORIA DE FECHA ---
    # Iniciamos con hoy por seguridad, pero se sobrescribirá con la primera fecha del CSV
    last_valid_date = datetime.now() 

    try:
        for row in csvReader:
            row_count += 1
            
            # 1. Parsear Datos (Nombres exactos de tu nuevo CSV)
            raw_name = row.get("Nombre correcto", "").strip()
            raw_size = clean_text(row.get("Tamaño"))
            raw_category = clean_text(row.get("Categoría"))
            raw_franchise = clean_text(row.get("Temática"))
            
            # Dinero (Columna PAGADO)
            raw_price = clean_money(row.get("PAGADO", "0"))

            # --- LOGICA DE FECHAS ---
            raw_date_str = row.get("Fecha", "").strip()
            
            if raw_date_str:
                parsed = parse_csv_date(raw_date_str)
                if parsed:
                    last_valid_date = parsed
            
            # Usamos la memoria
            effective_date = last_valid_date

            if not raw_name:
                continue 

            # 2. Buscar o Crear Producto
            product = db.query(Product).filter(
                Product.name == raw_name,
                Product.size == raw_size
            ).first()

            if not product:
                product = Product(
                    name=raw_name,
                    size=raw_size,
                    category=raw_category,
                    franchise=raw_franchise,
                    base_price=raw_price if raw_price > 0 else 0
                )
                db.add(product)
                db.flush()
                products_created += 1
            else:
                # Actualizar metadatos si faltaban
                if not product.category and raw_category:
                    product.category = raw_category
                    db.add(product)
                if not product.franchise and raw_franchise:
                    product.franchise = raw_franchise
                    db.add(product)

            # 3. Crear Movimientos
            # CONDICION IMPORTANTE: Solo si PAGADO > 0
            # Si quieres registrar regalos (PAGADO=0), quita este IF
            if raw_price > 0:
                
                # Ajuste Inicial (Para tener stock que vender)
                adj = InventoryMovement(
                    product_id=product.id,
                    type=MovementType.AJUSTE_INICIAL,
                    stage=StageLocation.TIENDA,
                    quantity=1,
                    monetary_value=0,
                    effective_date=effective_date,
                    created_at=datetime.now(),
                    notes=f"Carga CSV Fila {row_count}"
                )
                db.add(adj)

                # Venta Real
                sale = InventoryMovement(
                    product_id=product.id,
                    type=MovementType.VENTA,
                    stage=StageLocation.TIENDA,
                    quantity=-1,
                    monetary_value=raw_price,
                    effective_date=effective_date,
                    created_at=datetime.now(),
                    notes="Importado CSV"
                )
                db.add(sale)
                movements_created += 2

        db.commit()
        
        return {
            "status": "success",
            "processed_rows": row_count,
            "new_products": products_created,
            "movements_created": movements_created,
            "message": "Importación completada con formato dd/mm/yyyy"
        }

    except Exception as e:
        db.rollback()
        print(f"Error en fila {row_count}: {e}")
        raise HTTPException(status_code=400, detail=f"Error en fila {row_count}: {str(e)}")