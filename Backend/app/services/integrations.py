import random
import string
import requests
from unidecode import unidecode
from sqlalchemy.orm import Session
from app.models.product import Product

# --- 1. Generador de SKU ---
def generate_smart_sku(category: str, name: str) -> str:
    """
    Genera SKUs semánticos: CAT-NAME-1234
    Ej: Figura, Goku -> FIG-GOKU-A92Z
    """
    def clean(text, length=3):
        if not text: return "GEN"
        return unidecode(text).upper().replace(" ", "")[:length]

    cat_prefix = clean(category, 3)
    name_prefix = clean(name, 4)
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    
    return f"{cat_prefix}-{name_prefix}-{suffix}"

# --- 2. Servicio de Sincronización (Simulado) ---
def sync_with_tiendanube_task(product_id: int, db: Session):
    """
    Tarea en 2do plano:
    1. Busca producto en DB.
    2. Checa si tiene ID de Tiendanube.
    3. Si no, crea producto en TN API.
    4. Si sí, actualiza producto en TN API.
    """
    # Recargamos el producto fresco de la DB
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product: return

    print(f"🔄 Syncing Product {product.sku} with Tiendanube...")

    # AQUÍ VA TU LÓGICA REAL DE TIENDANUBE API
    # Esto es pseudo-código funcional
    try:
        # payload = { "name": product.name, "sku": product.sku, "price": product.base_price ... }
        
        if not product.tiendanube_id:
            # CREATE en Tiendanube
            # response = requests.post("https://api.tiendanube.com/...", json=payload)
            # tn_data = response.json()
            
            # Simulamos respuesta exitosa
            fake_tn_id = f"TN-{random.randint(1000,9999)}"
            fake_url = f"https://mitienda.com/productos/{product.sku}"
            
            # Guardamos la vinculación
            product.tiendanube_id = fake_tn_id
            product.tiendanube_url = fake_url
            db.commit()
            print(f"✅ Created in Tiendanube: {fake_tn_id}")
        else:
            # UPDATE en Tiendanube
            # requests.put(f"https://api.tiendanube.com/.../{product.tiendanube_id}", json=payload)
            print(f"✅ Updated Tiendanube ID: {product.tiendanube_id}")

    except Exception as e:
        print(f"❌ Error syncing Tiendanube: {e}")

# --- 3. Servicio de IA (Simulado) ---
def generate_ai_description_task(product_id: int, image_url: str, db: Session):
    """
    Tarea en 2do plano:
    1. Envía foto a GPT-4o / Gemini Vision.
    2. Genera descripción vendedora.
    3. Guarda en 'ai_description_proposal'.
    """
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product: return

    print(f"🤖 Generating AI Description for {product.name} from image...")

    try:
        # LÓGICA LLM AQUÍ
        # prompt = f"Analiza esta imagen de {product.name} ({product.category}). Genera una descripción atractiva para ecommerce."
        # ai_response = call_openai_vision(image_url, prompt)
        
        # Simulamos respuesta
        draft = f"¡Descubre el increíble {product.name}! Esta pieza de categoría {product.category} destaca por sus detalles únicos. (Generado por IA basado en foto)"
        
        product.ai_description_proposal = draft
        db.commit()
        print(f"✨ AI Draft Saved for {product.id}")

    except Exception as e:
        print(f"❌ Error AI Generation: {e}")