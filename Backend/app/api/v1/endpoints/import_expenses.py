import csv
import codecs
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from app.core.security import get_api_key
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.expense import Expense, ExpenseCategory
from app.models.filament import Filament, FilamentType
import traceback

router = APIRouter()

# --- UTILIDADES (Compartidas) ---
MESES = {
    "enero": 1, "feb": 2, "febrero": 2, "mar": 3, "marzo": 3, "abr": 4, "abril": 4, 
    "may": 5, "mayo": 5, "jun": 6, "junio": 6, "jul": 7, "julio": 7, "ago": 8, "agosto": 8, 
    "sep": 9, "septiembre": 9, "oct": 10, "octubre": 10, "nov": 11, "noviembre": 11, 
    "dic": 12, "diciembre": 12
}

def parse_spanish_date(date_str: str) -> datetime:
    """Convierte '18/julio/2024' a objeto fecha."""
    try:
        if not date_str: return datetime.now()
        parts = date_str.lower().strip().split('/')
        # A veces excel exporta con guiones
        if len(parts) == 1: parts = date_str.lower().strip().split('-')
        
        if len(parts) < 3: return datetime.now()
        
        day = int(parts[0])
        month_str = parts[1]
        year = int(parts[2])
        
        month = MESES.get(month_str, 1) # Default Enero si falla
        return datetime(year, month, day)
    except Exception:
        return datetime.now()

def clean_money(money_str: str) -> float:
    """Limpia '$3.000,00' o '10.709,00' a float."""
    if not money_str: return 0.0
    s = str(money_str).replace("$", "").strip()
    # Eliminar puntos de miles y cambiar coma por punto decimal
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0

# --- ENDPOINT 1: MAQUINARIA ---
@router.post("/machinery", dependencies=[Depends(get_api_key)])
async def import_machinery_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    CSV Esperado: Concepto, Precio, Fecha
    Ej: Ender 3 V2, 3.000,00, 18/julio/2024
    """
    csvReader = csv.DictReader(codecs.iterdecode(file.file, 'utf-8'))
    count = 0
    
    try:
        for row in csvReader:
            count += 1
            # Mapeo directo de columnas
            desc = row.get("Concepto", "Maquinaria Varia")
            price = clean_money(row.get("Precio"))
            date = parse_spanish_date(row.get("Fecha"))
            
            exp = Expense(
                description=desc,
                amount=price,
                category=ExpenseCategory.MAQUINARIA,
                date=date,
                notes="Carga Histórica Maquinaria"
            )
            db.add(exp)
        
        db.commit()
        return {"status": "success", "imported_machinery": count}
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error fila {count}: {str(e)}")

# --- ENDPOINT 2: FILAMENTOS ---
@router.post("/filaments", dependencies=[Depends(get_api_key)])
async def import_filaments_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    CSV Esperado: Marca, Material, Color, Precio, Origen, Fecha
    Crea el Gasto Y el registro de inventario de Filamento.
    """
    csvReader = csv.DictReader(codecs.iterdecode(file.file, 'utf-8'))
    count = 0
    
    try:
        for row in csvReader:
            count += 1
            
            # 1. Extraer datos
            brand = row.get("Marca", "Generico")
            mat_str = row.get("Material", "PLA").strip()
            color = row.get("Color", "Desconocido")
            price = clean_money(row.get("Precio"))
            origin = row.get("Origen", "")
            date = parse_spanish_date(row.get("Fecha"))
            
            # 2. Crear Gasto (La salida de dinero)
            desc_gasto = f"Filamento {brand} {mat_str} {color}"
            exp = Expense(
                description=desc_gasto,
                amount=price,
                category=ExpenseCategory.MATERIA_PRIMA,
                date=date,
                supplier=origin,
                notes="Carga Histórica Filamentos"
            )
            db.add(exp)
            db.flush() # ¡Importante! Genera el ID del gasto para usarlo abajo
            
            # 3. Detectar Tipo de Filamento (Mapeo simple)
            m_lower = mat_str.lower()
            f_type = FilamentType.OTHER
            if "pla" in m_lower: f_type = FilamentType.PLA
            elif "petg" in m_lower: f_type = FilamentType.PETG
            elif "tpu" in m_lower: f_type = FilamentType.TPU
            elif "abs" in m_lower: f_type = FilamentType.ABS
            elif "asa" in m_lower: f_type = FilamentType.ASA
            
            # 4. Crear Filamento (El inventario físico)
            # Asumimos que compras rollos de 1kg (1000g) nuevos
            fil = Filament(
                brand=brand,
                color=color,
                type=f_type,
                initial_weight=1000,
                current_weight=1000, # Se asume lleno al comprarlo
                price=price,
                expense_id=exp.id, # <--- Vinculación mágica
                created_at=date,   # Fecha de compra histórica
                is_active=True     # Asumimos que aun existen o existieron
            )
            db.add(fil)
            
        db.commit()
        return {"status": "success", "imported_filaments": count}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error fila {count}: {str(e)}")
    
# --- ENDPOINT 3: MATERIALES (VERSIÓN FINAL CON CSV COMPLETO) ---
@router.post("/materials", dependencies=[Depends(get_api_key)])
async def import_materials_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Carga el CSV de Materiales final.
    Columnas esperadas: Concepto, Cantidad, Precio, Origen, Fecha, Categoria
    """
    # Decodificamos el archivo
    csvReader = csv.DictReader(codecs.iterdecode(file.file, 'utf-8'))
    count = 0
    
    try:
        for row in csvReader:
            count += 1
            
            # 1. Extraer datos básicos
            raw_concept = row.get("Concepto", "Gasto General")
            qty_str = row.get("Cantidad", "")
            price = clean_money(row.get("Precio"))
            origin = row.get("Origen", "Desconocido")
            date = parse_spanish_date(row.get("Fecha"))
            
            # 2. Leer Categoría del CSV (PRIORIDAD)
            cat_val = row.get("Categoria")
            raw_category = str(cat_val).strip().upper() if cat_val is not None else ""
                        
            category_detected = ExpenseCategory.OTROS # Default
            
            # Verificamos si la categoría viene en el CSV y es válida en nuestro sistema
            if raw_category and raw_category in ExpenseCategory.__members__:
                category_detected = ExpenseCategory[raw_category]
            
            # 3. Construir descripción detallada
            # Ej: "Imanes 8*2 (Cant: 50)"
            final_desc = f"{raw_concept}"
            if qty_str and str(qty_str).strip() not in ["", "1"]:
                final_desc += f" (Cant: {qty_str})"

            # 4. Crear el Gasto
            exp = Expense(
                description=final_desc,
                amount=price,
                category=category_detected,
                date=date,
                supplier=origin,
                notes=f"Carga CSV (Cat: {category_detected.value})"
            )
            db.add(exp)
            
        db.commit()
        return {
            "status": "success", 
            "imported_materials": count,
            "message": "Gastos importados correctamente respetando la columna Categoria."
        }

    except Exception as e:
        traceback.print_exc
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error en fila {count}: {str(e)}")