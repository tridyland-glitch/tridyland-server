import base64
import os
import requests
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = os.getenv("TIENDANUBE_ACCESS_TOKEN")
USER_ID = os.getenv("TIENDANUBE_USER_ID")
API_URL = f"https://api.tiendanube.com/v1/{USER_ID}"

HEADERS = {
    "Authentication": f"bearer {ACCESS_TOKEN}",
    "User-Agent": "Tridyland Bot (hola@tridyland.com)"
}

def get_existing_categories():
    """
    Obtiene todas las categorías de la tienda y devuelve un string formateado
    para que la IA lo entienda. Ej: "123: Terror, 456: Fidgets"
    """
    try:
        url = f"{API_URL}/categories"
        response = requests.get(url, headers=HEADERS)
        
        if response.status_code == 200:
            categories = response.json()
            # Creamos una lista legible: "ID: Nombre (Nombre Padre)"
            cat_list = []
            for cat in categories:
                name = cat['name']['es']
                cat_id = cat['id']
                cat_list.append(f"{cat_id}: {name}")
            
            return "\n".join(cat_list)
        else:
            print(f"⚠️ Error obteniendo categorías: {response.text}")
            return ""
            
    except Exception as e:
        print(f"❌ Error conexión Tiendanube: {e}")
        return ""
    
def create_product_full(product_data: dict, image_paths: list) -> dict:
    """
    1. Crea el producto base en Tiendanube.
    2. Sube las imágenes a ese producto.
    Retorna los datos del producto creado.
    """
    print(f"🚀 Subiendo producto: {product_data['name']}")
    
    # 1. PREPARAR PAYLOAD DEL PRODUCTO
    payload = {
        "name": { "es": product_data["name"] },
        "description": { "es": product_data["description"] },
        "handle": { "es": product_data["handle"] },
        "seo_title": { "es": product_data.get("seo_title", "") },
        "seo_description": { "es": product_data.get("seo_description", "") },
        "tags": product_data.get("tags", ""),
        "published": False, 
        "variants": [
            {
                "price": product_data.get("price", 0),
                "stock": 0, # <--- CAMBIO: Stock en 0 (Nace agotado)
                "sku": product_data.get("sku", ""),
                
                # --- NUEVO: PESO Y DIMENSIONES ESTÁNDAR ---
                "weight": "0.050", # 50 gramos (Tiendanube usa KG)
                "width": "5",      # cm
                "height": "5",     # cm
                "depth": "5"       # cm
            }
        ],
        "categories": product_data.get("category_ids", [])
    }

    # 2. CREAR PRODUCTO (POST /products)
    try:
        response = requests.post(f"{API_URL}/products", json=payload, headers=HEADERS)
        response.raise_for_status() # Lanza error si falla
        created_product = response.json()
        product_id = created_product['id']
        print(f"✅ Producto creado con ID: {product_id}")
        
    except Exception as e:
        print(f"❌ Error creando producto base: {e}")
        try: print(response.text)
        except: pass
        return {"error": str(e)}

    # 3. SUBIR IMÁGENES (POST /products/{id}/images)
    # Recorremos tus rutas locales y las subimos una por una
    uploaded_images_count = 0
    
    for i, path in enumerate(image_paths):
        try:
            with open(path, "rb") as image_file:
                # Codificar a Base64
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                
            img_payload = {
                "filename": os.path.basename(path),
                "attachment": encoded_string,
                "position": i + 1, # 1, 2, 3...
                "alt": { "es": product_data.get("image_alt", "") } # ¡Tu Alt Text!
            }
            
            img_response = requests.post(
                f"{API_URL}/products/{product_id}/images",
                json=img_payload,
                headers=HEADERS
            )
            
            if img_response.status_code == 201:
                print(f"   📸 Imagen {i+1} subida correctamente.")
                uploaded_images_count += 1
            else:
                print(f"   ⚠️ Falló imagen {i+1}: {img_response.text}")
                
        except Exception as e:
            print(f"   ❌ Error procesando imagen {path}: {e}")

    # 4. RETORNAR RESULTADO FINAL
    return {
        "status": "success",
        "product_id": product_id,
        "admin_url": f"https://www.tiendanube.com/admin/products/{product_id}/edit",
        "preview_url": created_product.get("permalink", ""), # Link al frontend
        "images_uploaded": uploaded_images_count
    }

def get_product_by_handle(handle: str):
    """
    Busca un producto en la API usando su handle (slug).
    """
    try:
        # Tiendanube devuelve una lista incluso si solo hay un resultado
        url = f"{API_URL}/products?handle={handle}"
        response = requests.get(url, headers=HEADERS)
        products = response.json()
        
        if isinstance(products, list) and len(products) > 0:
            return products[0] 
        return None
    except Exception as e:
        print(f"❌ Error buscando producto: {e}")
        return None

def extract_handle_from_url(url: str) -> str:
    """
    Limpia la URL para obtener solo el slug del producto.
    Ej: https://tridyland.tiendanube.com/productos/cocofanto-elefante/ -> cocofanto-elefante
    """
    # Quitamos espacios y barras finales
    clean_url = url.strip().rstrip('/')
    # El handle es siempre la última parte de la ruta
    handle = clean_url.split('/')[-1]
    return handle