from datetime import date, datetime
import hashlib
import hmac
import json
import math
import random
from datetime import datetime, timedelta
import string
import time
from fastapi.responses import JSONResponse
from fastapi import APIRouter, BackgroundTasks, Body, Header, UploadFile, File, Form, HTTPException, status, Request
import os
import io
from typing import List
from PIL import Image
import qrcode
import fitz
from rembg import remove
import requests
from app.core.security import get_api_key
from app.core.email import enviar_correo_experiencia
from app.models.tiendanube import PuntosLedger,Usuario,TarjetaQR
from app.schemas.tiendanube import CanjearRequest, AcumularRequest, ReclamoRequest
from app.services.ai_service import generate_social_media_pack
from app.services.tiendanube_service import create_product_full, get_existing_categories
from app.core.config import settings

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from app.core.database import get_db

router = APIRouter()

# --- CONFIGURACIÓN ---
# Carpeta temporal donde guardaremos las fotos procesadas antes de subirlas
TEMP_UPLOAD_DIR = "temp_processed_images"
os.makedirs(TEMP_UPLOAD_DIR, exist_ok=True)
# Configuración de imagen final
TARGET_SIZE = 1080

# --- WEBHOOKS OBLIGATORIOS DE PRIVACIDAD (GDPR) ---
# Tiendanube los pide para poder guardar la configuración de la App.
# Como es una app interna, solo confirmamos de recibido.

@router.post("/tiendanube/customers/redact", status_code=200)
async def webhook_customers_redact(request: Request):
    """
    Eliminar datos personales de un cliente (GDPR).
    """
    return JSONResponse(content={"message": "Received"}, status_code=status.HTTP_200_OK)

@router.post("/tiendanube/customers/data_request", status_code=200)
async def webhook_customers_data_request(request: Request):
    """
    Solicitud de datos de un cliente.
    """
    return JSONResponse(content={"message": "Received"}, status_code=status.HTTP_200_OK)

@router.post("/tiendanube/store/redact", status_code=200)
async def webhook_store_redact(request: Request):
    """
    Eliminar datos de la tienda (si se cierra la cuenta).
    """
    return JSONResponse(content={"message": "Received"}, status_code=status.HTTP_200_OK)

# --- WEBHOOKS DE CICLO DE VIDA ---

@router.post("/tiendanube/app/uninstalled", status_code=200)
async def webhook_app_uninstalled(request: Request):
    """
    Se dispara cuando desinstalan la app.
    Aquí deberías borrar el Access Token de tu DB para limpieza,
    pero por ahora solo respondemos OK.
    """
    # data = await request.json()
    # print(f"App desinstalada de la tienda: {data.get('store_id')}")
    return JSONResponse(content={"message": "Received"}, status_code=status.HTTP_200_OK)

# --- SUBIR FOTOS -> CREA PRODUCTO ---
# --- FUNCIÓN DE PROCESAMIENTO DE IMAGEN (Versión IA Centering) ---
def smart_process_image(image_bytes: bytes) -> Image.Image:
    """
    Usa IA para detectar dónde está el objeto. Calcula el centro visual
    del objeto y realiza el recorte cuadrado más grande posible alrededor
    de ese centro, respetando el fondo original. Finalmente, redimensiona a 1080x1080.
    """
    print("   🤖 Iniciando Detección y Centrado por IA...")
    
    # Abrir la imagen original
    img_original = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    orig_w, orig_h = img_original.size

    # --- PASO 1: Usar IA para encontrar el objeto ---
    try:
        # remove() devuelve bytes de la imagen sin fondo.
        # Solo la usamos como "guía" para encontrar las coordenadas.
        subject_no_bg_bytes = remove(image_bytes)
        img_guide = Image.open(io.BytesIO(subject_no_bg_bytes))
        
        # bbox es (left, top, right, bottom) del objeto detectado
        bbox = img_guide.getbbox()
    except Exception as e:
        print(f"⚠️ Advertencia: Falló la detección IA ({e}). Usando centro matemático.")
        bbox = None

    if not bbox:
        # Si la IA falla o no encuentra nada, usamos toda la imagen como fallback
        bbox = (0, 0, orig_w, orig_h)
        print("⚠️ No se detectó objeto claro. Usando imagen completa.")

    # --- PASO 2: Calcular el centro del OBJETO detectado ---
    obj_center_x = (bbox[0] + bbox[2]) / 2
    obj_center_y = (bbox[1] + bbox[3]) / 2
    
    print(f"      🎯 Centro del objeto detectado en: ({int(obj_center_x)}, {int(obj_center_y)})")

    # --- PASO 3: Definir el tamaño del recorte cuadrado ---
    # Queremos el cuadrado más grande posible que quepa en la imagen original.
    crop_size = min(orig_w, orig_h)
    half_crop = crop_size / 2

    # --- PASO 4: Calcular coordenadas tentativas del recorte centrado en el objeto ---
    crop_left = obj_center_x - half_crop
    crop_top = obj_center_y - half_crop
    crop_right = crop_left + crop_size
    crop_bottom = crop_top + crop_size

    # --- PASO 5: Ajustar (Clamping) para no salirse de la imagen ---
    # Si el objeto está muy a la orilla, el recorte tentativo podría salirse.
    # Empujamos el cuadro de recorte hacia adentro si es necesario.
    
    # Ajuste horizontal
    if crop_left < 0:
        diff = -crop_left
        crop_left += diff # Lo empujamos a 0
        crop_right += diff # Movemos el lado derecho también para mantener el tamaño
    elif crop_right > orig_w:
        diff = crop_right - orig_w
        crop_left -= diff
        crop_right -= diff
        
    # Ajuste vertical
    if crop_top < 0:
        diff = -crop_top
        crop_top += diff
        crop_bottom += diff
    elif crop_bottom > orig_h:
        diff = crop_bottom - orig_h
        crop_top -= diff
        crop_bottom -= diff

    # Coordenadas finales del recorte (asegurando enteros)
    final_crop_box = (int(crop_left), int(crop_top), int(crop_right), int(crop_bottom))

    # --- PASO 6: Recortar la imagen ORIGINAL y redimensionar ---
    img_cropped = img_original.crop(final_crop_box)
    
    # Usamos LANCZOS para la mejor calidad al redimensionar a 1080
    img_final = img_cropped.resize((TARGET_SIZE, TARGET_SIZE), Image.Resampling.LANCZOS)
    
    return img_final

# --- FUNCIÓN AUXILIAR PARA SKU ---
def generate_sku(name_hint: str) -> str:
    """
    Genera un SKU tipo: TRIDY-DEMO-8X2
    Usa las primeras 4 letras del nombre/contexto y 3 caracteres random.
    """
    # Limpiar el nombre para usarlo de prefijo (solo letras, mayúsculas)
    clean_hint = "".join(c for c in name_hint if c.isalnum()).upper()
    prefix = clean_hint[:4] if clean_hint else "ITEM"
    
    # Generar sufijo random de 3 caracteres (Letras y Números)
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))
    
    return f"TRIDY-{prefix}-{suffix}"

# --- EL ENDPOINT ---
@router.post("/process-draft", status_code=status.HTTP_201_CREATED)
async def create_product_draft_step1(
    context: str = Form(..., description="Descripción rápida del producto"),
    category_guess: str = Form(None, description="Categoría sugerida opcional"), # <--- Agregué este que faltaba en tu snippet
    price_guess: float = Form(None, description="Precio sugerido opcional"),
    main_image: UploadFile = File(..., description="LA FOTO PRINCIPAL (Se usará para la IA y Portada)"),
    gallery_images: List[UploadFile] = File(default=[], description="El resto de las fotos (Variantes, ángulos)"),
):
    """
    PASO 1 Automatización:
    1. Procesa imágenes.
    2. Genera textos con Gemini.
    3. Sube borrador a Tiendanube.
    """
    print(f"\n🚀 INICIANDO PROCESO para: {context}")
    
    processed_images_paths = []
    batch_dir = TEMP_UPLOAD_DIR
    
    # --- 1. PROCESAR IMAGEN PRINCIPAL ---
    print(f"⭐ Procesando MAIN IMAGE: {main_image.filename}")
    try:
        content_main = await main_image.read()
        final_main = smart_process_image(content_main)
        
        save_path_main = os.path.join(batch_dir, f"00_main_{main_image.filename.rsplit('.', 1)[0]}.jpg")
        
        final_main.save(save_path_main, "JPEG", quality=95)
        processed_images_paths.append(save_path_main)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en imagen principal: {e}")
    finally:
        await main_image.close()

    # --- 2. PROCESAR GALERÍA ---
    if gallery_images:
        print(f"📸 Procesando {len(gallery_images)} imágenes de galería...")
        for i, file in enumerate(gallery_images):
            if not file.content_type.startswith("image/"):
                continue
            
            try:
                content_gallery = await file.read()
                final_gallery = smart_process_image(content_gallery)
                
                clean_name = f"{str(i+1).zfill(2)}_gallery_{file.filename.rsplit('.', 1)[0]}.jpg"
                save_path_gallery = os.path.join(batch_dir, clean_name)
                
                final_gallery.save(save_path_gallery, "JPEG", quality=92)
                processed_images_paths.append(save_path_gallery)
                
            except Exception as e:
                print(f"⚠️ Saltando imagen corrupta {file.filename}: {e}")
            finally:
                await file.close()

    # --- FASE 2: IA ---
    ai_data = {}
    upload_result = {} 

    main_image_path = processed_images_paths[0]
    
    try:
        from app.services.ai_service import generate_product_data
        
        # 1. OBTENER CATEGORÍAS REALES (Sin simulación)
        print("📡 Obteniendo categorías de Tiendanube...")
        existing_cats_str = get_existing_categories() 
        
        # Si la tienda es nueva y no tiene categorías, existing_cats_str estará vacío.
        if not existing_cats_str:
            existing_cats_str = "No hay categorías creadas. Sugiere una nueva."

        # 2. LLAMAR A GEMINI
        ai_data = generate_product_data(
            image_path=main_image_path,
            context=context,
            price=price_guess,
            category_list=existing_cats_str
        )
        
        # 3. LIMPIEZA DE CATEGORÍAS (EL FIX DEL ERROR 422)
        # La IA a veces alucina IDs. Vamos a validar.
        # Si no estamos seguros, mejor enviamos lista vacía [] y tú lo categorizas manual.
        
        # Opción segura: Si la IA sugirió IDs, verifiquemos que existan en el string que bajamos.
        # Si no, los borramos para evitar el crash.
        valid_ids = []
        if "category_ids" in ai_data and ai_data["category_ids"]:
            for cat_id in ai_data["category_ids"]:
                # Truco rápido: checar si el ID está en el texto de categorías existentes
                if str(cat_id) in existing_cats_str:
                    valid_ids.append(cat_id)
                else:
                    print(f"⚠️ Ignorando categoría inválida sugerida por IA: {cat_id}")
        
        ai_data["category_ids"] = valid_ids # Reemplazamos por la lista filtrada y segura
        
        # Generar SKU
        sku_base = ai_data.get("name", context)
        ai_data["sku"] = generate_sku(sku_base) 
        
        if price_guess:
            ai_data['price'] = price_guess
            
        print(f"✅ Datos IA generados. SKU: {ai_data['sku']}")
        
    except Exception as e:
        print(f"⚠️ Error generando IA: {e}")
        ai_data = {"error": str(e)}

    # --- FASE 3: SUBIDA A TIENDANUBE ---
    if "error" not in ai_data:
        print("🚀 Iniciando carga a Tiendanube...")
        try:
            upload_result = create_product_full(
                product_data=ai_data,
                image_paths=processed_images_paths
            )
        except Exception as e:
            print(f"❌ Error crítico subiendo a Tiendanube: {e}")
            upload_result = {"error": f"Fallo crítico en subida: {str(e)}"}
    else:
        print("⚠️ Saltando subida por error previo en IA.")

    return {
        "status": "completed",
        "ai_summary": ai_data,
        "tiendanube_result": upload_result,
        "local_images": processed_images_paths
    }

@router.post("/social-pack-by-url")
async def get_social_pack_by_url(data: dict):
    input_url = data.get("url")
    if not input_url:
        raise HTTPException(status_code=400, detail="Falta la URL")

    from app.services.tiendanube_service import get_product_by_handle, extract_handle_from_url
    
    handle = extract_handle_from_url(input_url)
    product = get_product_by_handle(handle)
    
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    # --- FIX: Validación de campos ---
    product_name = product.get('name', {}).get('es', 'Producto Tridyland')
    # Intentamos obtener la URL de varias formas para que no falle
    store_url = product.get('permalink') or product.get('url') or input_url
    description_context = product.get('description', {}).get('es', '')
    
    pack = generate_social_media_pack(product_name, description_context, store_url)
    
    return {
        "product": product_name,
        "social_pack": pack,
        "main_image": product['images'][0]['src'] if product.get('images') else None
    }

# ⚙️ DICCIONARIO DE LÍMITES DIARIOS
# Define cuántos puntos máximos se pueden ganar por día según la acción
LIMITES_DIARIOS = {
    "juego_clicker" : 50,
    "vista_producto": 10,
    "add_carrito"   : 15
}

# 🎁 CATÁLOGO DE BOTÍN PARA TIENDANUBE
# "tipo" puede ser "percentage" (descuento %), "absolute" (descuento $), o "shipping" (envío gratis)
CATALOGO_PREMIOS = {
    2: {
        "A": {"tipo": "percentage", "valor": "5.00", "descripcion": "5% OFF"},
        "B": {"tipo": "absolute", "valor": "1.00", "descripcion": "Stickers (Regalo Físico)"} # <-- 1 pesito simbólico
    },
    5: {
        "A": {"tipo": "percentage", "valor": "10.00", "descripcion": "10% OFF"},
        "B": {"tipo": "absolute", "valor": "1.00", "descripcion": "Fidget Tier C (Regalo)"} # <-- 1 pesito
    },
    10: {
        "A": {"tipo": "absolute", "valor": "100.00", "descripcion": "$100 MXN OFF"},
        "B": {"tipo": "absolute", "valor": "1.00", "descripcion": "Fidget Tier B (Regalo)"} # <-- 1 pesito
    },
    25: {
        "A": {"tipo": "shipping", "valor": "0.00", "descripcion": "Envío Gratis"}, # (Shipping sí acepta 0.00)
        "B": {"tipo": "absolute", "valor": "1.00", "descripcion": "Fidget Tier A (Regalo)"} # <-- 1 pesito
    },
    50: {
        "A": {"tipo": "percentage", "valor": "50.00", "descripcion": "50% OFF (Mitad de precio)"},
        "B": {"tipo": "absolute", "valor": "1.00", "descripcion": "Figura Tier S (Regalo)"} # <-- 1 pesito
    }
}

def generar_codigo_aleatorio(longitud=6):
    letras = string.ascii_uppercase + string.digits
    return ''.join(random.choice(letras) for i in range(longitud))

@router.post("/puntos/acumular", status_code=201)
async def acumular_puntos(
    request: Request,
    payload: AcumularRequest, 
    db: Session = Depends(get_db)
):
    # 1. Validación de HMAC (Seguridad)
    mensaje_crudo = f"{payload.usuario_id}|{payload.puntos}|{payload.accion}|{payload.timestamp}"
    hash_esperado = hmac.new(
        key=settings.API_SECRET_KEY.encode('utf-8'), 
        msg=mensaje_crudo.encode('utf-8'), 
        digestmod=hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(hash_esperado, payload.hash_seguridad):
        raise HTTPException(status_code=401, detail="Firma de seguridad inválida.")

    # 🪪 TRADUCTOR: payload.usuario_id trae el CORREO
    email_cliente = payload.usuario_id
    usuario = db.query(Usuario).filter(Usuario.email == email_cliente).first()
    
    if not usuario:
        # Si juega pero no se ha registrado, le creamos un perfil fantasma
        usuario = Usuario(email=email_cliente, nombre="Héroe Anónimo")
        db.add(usuario)
        db.commit()
        db.refresh(usuario)
        
    usuario_db_id = usuario.id # ESTE ES EL UUID REAL

    # 👉 2. REVISIÓN DEL LÍMITE DIARIO
    limite = LIMITES_DIARIOS.get(payload.accion)
    
    if limite is not None:
        hoy = date.today()
        # Usamos usuario_db_id para buscar en el Ledger
        puntos_hoy = db.query(func.sum(PuntosLedger.puntos))\
            .filter(PuntosLedger.usuario_id == usuario_db_id)\
            .filter(PuntosLedger.accion == payload.accion)\
            .filter(func.date(PuntosLedger.created_at) == hoy)\
            .scalar() or 0

        if puntos_hoy >= limite:
            # 🛡️ AUNQUE LLEGUE AL LÍMITE DE PUNTOS, GUARDAMOS LOS CLICKS AUDITADOS
            if payload.clicks_raw > 0:
                db.add(PuntosLedger(usuario_id=usuario_db_id, puntos=0, accion=payload.accion, clicks_raw=payload.clicks_raw))
                db.commit()

            return {
                "status": "limite_alcanzado", 
                "mensaje": f"Has alcanzado el límite de {limite} puntos.",
                "puntos_aceptados": 0
            }
            
        if puntos_hoy + payload.puntos > limite:
            puntos_a_sumar = limite - puntos_hoy
        else:
            puntos_a_sumar = payload.puntos
    else:
        puntos_a_sumar = payload.puntos

    # 3. Guardar en la Base de Datos usando el UUID
    nuevo_registro = PuntosLedger(
        usuario_id=usuario_db_id, # <- AQUÍ ESTABA EL ERROR
        puntos=puntos_a_sumar,
        accion=payload.accion,
        clicks_raw=payload.clicks_raw
    )
    db.add(nuevo_registro)
    db.commit()

    return {
        "status": "success", 
        "mensaje": f"Se agregaron {puntos_a_sumar} puntos",
        "puntos_aceptados": puntos_a_sumar
    }

@router.post("/puntos/reclamar")
async def reclamar_botin(req: ReclamoRequest, db: Session = Depends(get_db)):
    # 1. Validar Seguridad (HMAC)
    mensaje_crudo = f"{req.usuario_id}|{req.nivel}|{req.opcion}|{req.timestamp}"
    hash_calculado = hmac.new(
        settings.API_SECRET_KEY.encode('utf-8'), 
        mensaje_crudo.encode('utf-8'), 
        hashlib.sha256
    ).hexdigest()
    
    if req.hash_seguridad != hash_calculado:
        raise HTTPException(status_code=401, detail="Firma inválida.")

    # 2. Obtener el premio del catálogo
    premio = CATALOGO_PREMIOS.get(req.nivel, {}).get(req.opcion)
    if not premio:
        raise HTTPException(status_code=400, detail="Premio no válido.")
    
    usuario = db.query(Usuario).filter(Usuario.email == req.usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    
    # --- 🛡️ LA CAPA DE AUDITORÍA (TIME-TRAVEL PROOF OF WORK) ---
    if req.nivel in [2, 5, 10, 25, 50]:
        # 1. Definimos las reglas del juego
        xp_requerida_nivel = { 2: 50, 5: 500, 10: 1500, 25: 5000, 50: 50000 }
        hp_jefes = { 2: 50, 5: 150, 10: 500, 25: 1500, 50: 5000 }
        
        xp_meta = xp_requerida_nivel.get(req.nivel, 0)
        hp_requerido = hp_jefes.get(req.nivel, 0)
        
        # 2. Traemos todo el historial de la cuenta en orden cronológico
        historial = db.query(PuntosLedger).filter(
            PuntosLedger.usuario_id == usuario.id
        ).order_by(PuntosLedger.created_at.asc()).all()
        
        xp_acumulada = 0
        fecha_desbloqueo_boss = None
        
        # 3. Buscamos el segundo exacto en el que alcanzó la XP para este Boss
        for registro in historial:
            xp_acumulada += registro.puntos
            if xp_acumulada >= xp_meta and fecha_desbloqueo_boss is None:
                fecha_desbloqueo_boss = registro.created_at
                break # ¡Encontramos el momento en que apareció el Boss en su pantalla!
                
        if not fecha_desbloqueo_boss:
            raise HTTPException(status_code=400, detail="Aún no tienes la XP necesaria para este botín.")
            
        # 4. Sumamos SOLO los clicks que ocurrieron después de que apareció el Boss
        clicks_directos_al_boss = sum(
            reg.clicks_raw 
            for reg in historial 
            if reg.created_at >= fecha_desbloqueo_boss and reg.accion == "juego_clicker"
        )
        
        # 5. El Veredicto Final (Con un 15% de tolerancia por si falló su internet en algunos clicks)
        if clicks_directos_al_boss < (hp_requerido * 0.85):
            print(f"🚨 HACKER DETECTADO: {usuario.email} intentó matar Boss {req.nivel} con {clicks_directos_al_boss} clicks (Necesitaba ~{hp_requerido}).")
            raise HTTPException(
                status_code=403, 
                detail=f"¡El Boss sigue vivo! Has dado {clicks_directos_al_boss} golpes, ¡Sigue luchando para reclamar la recompensa!"
            )

    # 3. Verificar si ya se cobró (Ledger)
    reclamo_previo = db.query(PuntosLedger).filter(
        PuntosLedger.usuario_id == usuario.id,
        PuntosLedger.accion == f"reclamo_lvl_{req.nivel}"
    ).first()

    if reclamo_previo:
        return {"status": "error", "mensaje": "Este botín ya fue reclamado anteriormente."}

    # --- 🛡️ LÓGICA DE PROTECCIÓN TRIDYLAND ---
    
    # Límite de 3 días para usarlo
    fecha_expiracion = (datetime.utcnow() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    codigo_unico = f"TRIDY-L{req.nivel}-{generar_codigo_aleatorio()}"
    
    # Payload base para Tiendanube
    payload_cupon = {
        "code": codigo_unico,
        "type": premio["tipo"],
        "value": premio["valor"],
        "max_uses": 1,
        "expires_at": fecha_expiracion  # 🕒 Candado de tiempo
    }

    # ⚔️ PROTECCIÓN PARA EL NIVEL 50 (50% OFF)
    if req.nivel == 50:
        # Limitamos el descuento máximo a $250 MXN
        payload_cupon["max_discount_value"] = 250 
        # (Opcional) Solo para ciertos productos si los tienes identificados
        # payload_cupon["product_ids"] = [12345, 67890] 
        # (Opcional) Compra mínima de $500 para que el 50% valga la pena
        payload_cupon["min_price"] = 500

    # 🚚 PROTECCIÓN PARA ENVÍO GRATIS
    if premio["tipo"] == "shipping":
        # Tiendanube usa el valor 0 o vacío para envío gratis total
        payload_cupon["value"] = 0 

    # 4. Llamada a la API de Tiendanube
    url_tiendanube = f"https://api.tiendanube.com/v1/{settings.TIENDANUBE_STORE_ID}/coupons"
    headers_api = {
        "Authentication": f"bearer {settings.TIENDANUBE_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "TridylandApp (hola@tridyland.com)"
    }

    respuesta = requests.post(url_tiendanube, json=payload_cupon, headers=headers_api)
    
    if respuesta.status_code != 201:
        raise HTTPException(status_code=500, detail="Error al forjar el cupón en la tienda.")

    # 5. Registrar en DB
    db.add(PuntosLedger(usuario_id=usuario.id, puntos=0, accion=f"reclamo_lvl_{req.nivel}"))
    db.commit()

    return {
        "status": "success",
        "codigo_cupon": codigo_unico,
        "descripcion": premio["descripcion"],
        "expira": "3 días"
    }

@router.get("/puntos/saldo", status_code=200)
async def obtener_saldo(
    request: Request,
    usuario_id: str = Query(..., description="Email del cliente de Tiendanube"),
    timestamp: int = Query(..., description="Tiempo en formato Unix Epoch"),
    hash_seguridad: str = Query(..., description="Hash SHA256 generado en el frontend"),
    db: Session = Depends(get_db)
):
    current_time = int(time.time())
    if abs(current_time - timestamp) > 60:
        raise HTTPException(status_code=403, detail="La petición ha expirado.")

    mensaje_crudo = f"{usuario_id}|{timestamp}"
    hash_esperado = hmac.new(
        key=settings.API_SECRET_KEY.encode('utf-8'), 
        msg=mensaje_crudo.encode('utf-8'), 
        digestmod=hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(hash_esperado, hash_seguridad):
        raise HTTPException(status_code=401, detail="Firma inválida.")

    # 🪪 TRADUCTOR
    email_cliente = usuario_id
    usuario = db.query(Usuario).filter(Usuario.email == email_cliente).first()
    
    # Si no existe en BD, su saldo es 0 y no tiene historial
    if not usuario:
        return {
            "saldo_actual": 0,
            "reclamos_historicos": [],
            "es_comprador_verificado": False
        }
        
    usuario_db_id = usuario.id

    # Consultamos con el UUID
    xp_total = db.query(func.sum(PuntosLedger.puntos)).filter(PuntosLedger.usuario_id == usuario_db_id).scalar() or 0
    
    reclamos = db.query(PuntosLedger.accion).filter(
        PuntosLedger.usuario_id == usuario_db_id,
        PuntosLedger.accion.like("reclamo_lvl_%")
    ).all()
    lista_reclamos = [r[0] for r in reclamos] 
    
    # 🛡️ VERIFICADOR MULTI-CANAL (Tiendanube + Físico)
    tiene_compra = db.query(PuntosLedger).filter(
        PuntosLedger.usuario_id == usuario_db_id,
        or_(
            PuntosLedger.accion.like("compra_real_%"),       # Compras en línea
            PuntosLedger.accion.like("reclamo_qr_%")   # Compras escaneadas en físico
        )
    ).first() is not None

    return {
        "saldo_actual": xp_total,
        "reclamos_historicos": lista_reclamos,
        "es_comprador_verificado": tiene_compra
    }

@router.get("/puntos/info", status_code=200)
async def obtener_info_por_token(
    token: str = Query(..., description="El Magic Token del usuario"),
    db: Session = Depends(get_db)
):
    # 1. Buscar al usuario por su token mágico
    usuario = db.query(Usuario).filter(Usuario.magic_token == token).first()
    
    if not usuario:
        raise HTTPException(status_code=404, detail="Token mágico inválido o expirado.")

    # 2. Calcular sus stats
    xp_total = db.query(func.sum(PuntosLedger.puntos)).filter(PuntosLedger.usuario_id == usuario.id).scalar() or 0
    nivel_actual = calcular_nivel_python(xp_total)

    # 3. Mandar la info de regreso al juego
    return {
        "status": "success",
        "nombre": usuario.nombre,
        "email": usuario.email, # Súper importante para que el juego sepa quién es
        "xp": xp_total,
        "nivel": nivel_actual
    }

# ---------------------------------------------------------
# 1. EL TRABAJADOR (Esta función hace el trabajo pesado)
# ---------------------------------------------------------
def calcular_nivel_python(xp: int) -> int:
    """Curva de la Dopamina: Rápida al inicio, exponencial al final. Tope 50."""
    if xp < 50: return 1
    if xp < 500: return 2 + int((xp - 50) / 150)           # Lvls 2, 3, 4 (Saltos de 150 XP)
    if xp < 1500: return 5 + int((xp - 500) / 200)         # Lvls 5 al 9 (Saltos de 200 XP)
    if xp < 5000: return 10 + int((xp - 1500) * 15 / 3500) # Lvls 10 al 24 (Saltos de ~233 XP)
    if xp < 50000: return 25 + int((xp - 5000) / 1800)     # Lvls 25 al 49 (Saltos de 1,800 XP)
    return 50 # Nivel Máximo

def procesar_orden_tiendanube(store_id: str, order_id: str, evento: str, db: Session):
    print(f"⚙️ [Background] Procesando {evento} de la orden {order_id}...")
    
    url_orden = f"https://api.tiendanube.com/v1/{store_id}/orders/{order_id}"
    headers_api = {
        "Authentication": f"bearer {settings.TIENDANUBE_ACCESS_TOKEN}",
        "User-Agent": "TridylandApp (hola@tridyland.com)",
        "Content-Type": "application/json"
    }

    respuesta = requests.get(url_orden, headers=headers_api)
    if respuesta.status_code != 200:
        print(f"❌ Error al consultar Tiendanube: {respuesta.text}")
        return

    orden_completa = respuesta.json()
    cliente = orden_completa.get("customer", {})
    email = cliente.get("email") or orden_completa.get("contact_email")
    
    if not email:
        print("⚠️ Compra sin email, se ignora.")
        return
    
    # 🪪 TRADUCTOR
    usuario = db.query(Usuario).filter(Usuario.email == email).first()
    if not usuario:
        # Extraemos el nombre de la orden si existe, o ponemos anónimo
        nombre_cliente = cliente.get("name", "Héroe Anónimo")
        usuario = Usuario(email=email, nombre=nombre_cliente)
        db.add(usuario)
        db.commit()
        db.refresh(usuario)
        
    usuario_db_id = usuario.id

    # 1. Calculamos los puntos ANTES del if, porque tanto el pago como la cancelación los necesitan
    total_orden = float(orden_completa.get("total", 0.0))
    # Multiplicamos el monto por 10 para la conversión 1:10
    puntos_base = math.floor(total_orden * 10)

    if evento == "order/paid":
        puntos_finales = puntos_base
        accion_txt = f"compra_real_{order_id}"

        # Evitar Duplicados de Pago
        existe = db.query(PuntosLedger).filter(
            PuntosLedger.usuario_id == email,
            PuntosLedger.accion == accion_txt
        ).first()

        if existe:
            print(f"⚠️ La orden {order_id} ya dio sus puntos antes.")
            return

    elif evento == "order/cancelled":
        puntos_finales = -abs(puntos_base)
        accion_txt = f"cancelacion_orden_{order_id}" # Le agregamos el ID para evitar dobles cancelaciones

        # Evitar Duplicados de Cancelación
        existe = db.query(PuntosLedger).filter(
            PuntosLedger.usuario_id == email,
            PuntosLedger.accion == accion_txt
        ).first()

        if existe:
            print(f"⚠️ La orden {order_id} ya se había cancelado antes.")
            return
            
        print(f"🚨 ¡CANCELACIÓN! Restando {abs(puntos_finales)} pts a: {email}")

    else:
        # Si es otro evento raro de Tiendanube, lo ignoramos
        return

    # 2. GUARDADO UNIFICADO EN LA BASE DE DATOS (Sirve para pagos y cancelaciones)
    nuevo_registro = PuntosLedger(
        usuario_id=usuario_db_id,
        puntos=puntos_finales,
        accion=accion_txt
    )
    db.add(nuevo_registro)
    db.commit()
    print("✅ Ledger actualizado con éxito.")

    # 3. ACCIONES POSTERIORES (Solo si fue un pago exitoso mandamos el correo)
    if evento == "order/paid":
        # Calculamos X (Total) y N (Nivel)
        xp_total = db.query(func.sum(PuntosLedger.puntos)).filter(PuntosLedger.usuario_id == email).scalar() or 0
        nivel_actual = calcular_nivel_python(xp_total)

        # Invocamos al Cartero
        enviar_correo_experiencia(email, puntos_base, xp_total, nivel_actual)
        print(f"🎉 ¡VENTA! Sumando {puntos_base} pts a {email} por una compra de ${total_orden}")

# ---------------------------------------------------------
# 2. EL RECEPCIONISTA (Tu endpoint súper rápido)
# ---------------------------------------------------------
@router.post("/webhooks/compra")
async def webhook_compra_tiendanube(
    request: Request, 
    background_tasks: BackgroundTasks, # 👈 Le pasamos el manejador de tareas
    x_linkedstore_hmac_sha256: str = Header(None), 
    db: Session = Depends(get_db)
):
    raw_body = await request.body()
    secreto_app = settings.TIENDANUBE_CLIENT_SECRET
    
    # Validamos rápido al guardia de seguridad
    firma_calculada = hmac.new(secreto_app.encode('utf-8'), raw_body, hashlib.sha256).hexdigest()
    if x_linkedstore_hmac_sha256 != firma_calculada:
        raise HTTPException(status_code=401, detail="Firma inválida")

    try:
        data = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="JSON inválido")

    store_id = data.get("store_id")
    order_id = data.get("id")
    evento = data.get("event")

    if not store_id or not order_id or not evento:
        return {"status": "ignorado"}

    # 🚀 AQUÍ ESTÁ LA MAGIA: Le pasamos la tarea al trabajador de fondo
    background_tasks.add_task(procesar_orden_tiendanube, store_id, order_id, evento, db)

    # Y respondemos inmediatamente en menos de 100ms
    return {"status": "success", "mensaje": "Webhook recibido. Procesando en segundo plano..."}

def es_codigo_seguro(codigo):
    # 1. Lista negra de palabras u ofensas (puedes ampliarla)
    # Incluye variaciones comunes y groserías cortas
    BLOCKLIST = ["PENE", "KULO", "COLO", "PUTA", "ORTO", "NIGA", "SEXO", "BOOB",
                 "NIGGA", "JOTO", "CULO", "PUTO", "CACA", "SEX", "VAGIN"]
    
    # 2. Diccionario de "Leet Speak" para normalizar números a letras
    TRADUCCION_LEET = str.maketrans("013458", "OIELSB")
    
    # Normalizamos el código (quitamos el prefijo 'TRIDY-' y pasamos a letras)
    solo_clave = codigo.replace("TRIDY-", "").upper()
    codigo_normalizado = solo_clave.translate(TRADUCCION_LEET)
    
    # 3. Verificamos si alguna palabra prohibida está contenida en el código
    for palabra in BLOCKLIST:
        if palabra in codigo_normalizado:
            return False
            
    return True

@router.post("/generar-lote-pdf-pro", dependencies=[Depends(get_api_key)])
def generar_lote_pdf_pro(
    cantidad: int = Query(..., gt=0, le=1000),
    db: Session = Depends(get_db)
):
    ahora = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    ruta_base = f"tarjetas_generadas/{ahora}"
    os.makedirs(ruta_base, exist_ok=True)
    
    # --- 📐 CONFIGURACIÓN DE COORDENADAS (En PUNTOS PDF) ---
    # Estos valores están calculados para que el ID aparezca centrado abajo
    # Si ves que sale muy a la izquierda, sube TEXTO_ID_X. 
    QR_SIZE_PTS = 88
    QR_X_PTS = 36
    QR_Y_PTS = 31.5
    COLOR_MORADO_QR = "#b33dcf"

    # Coordenadas para el ID (Lado Morado)
    # En una tarjeta de 270 pts de ancho, 165 es un buen punto para empezar después del label
    TEXTO_ID_X = 172.0  
    TEXTO_ID_Y = 148.0  
    COLOR_VERDE_TRIDY = (168/255, 241/255, 104/255) # Verde #a8f168

    try:
        # Cargamos los archivos maestros
        doc_frente_template = fitz.open("frente_morado.pdf")
        doc_trasera_template = fitz.open("trasera_verde.pdf")
        logo_pug = Image.open("logo_pug.png").convert("RGBA")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falta un archivo (PDF, TTF o Logo): {e}")

    pdf_final_frentes = fitz.open()
    pdf_final_reversos = fitz.open()
    
    codigos_db = {row[0] for row in db.query(TarjetaQR.codigo).all()}
    codigos_del_lote = set() 
    nuevas_tarjetas = []

    while len(nuevas_tarjetas) < cantidad:
        # Usamos un alfabeto sin vocales y sin caracteres confusos
        # Quitamos A, E, I, O, U, y también 0, 1, L para evitar errores de lectura
        chars = "BCDFGHJKLMNPQRSTVWXYZ23456789"
        random_str = ''.join(random.choices(chars, k=5))
        codigo = f"TRIDY-{random_str}"
        
        # Triple validación: No en DB, no en el lote actual Y QUE SEA SEGURO
        if codigo not in codigos_db and codigo not in codigos_del_lote:
            if es_codigo_seguro(codigo):
                codigos_del_lote.add(codigo)
                nuevas_tarjetas.append(TarjetaQR(codigo=codigo, estado="nuevo"))

                # --- PARTE A: EL FRENTE (Estampar el ID) ---
                pdf_final_frentes.insert_pdf(doc_frente_template)
                pagina_frente = pdf_final_frentes[-1]
                
                # 🎯 Aquí estampamos solo la clave (el ID) junto a tu etiqueta de Canva
                pagina_frente.insert_text(
                    (TEXTO_ID_X, TEXTO_ID_Y),
                    codigo, 
                    fontsize=14,
                    fontname="bree", 
                    fontfile="BreeSerif-Regular.ttf",
                    color=COLOR_VERDE_TRIDY
                )

                # --- PARTE B: EL REVERSO (QR con Pug) ---
                qr = qrcode.QRCode(version=2, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=1)
                qr.add_data(f"https://www.tridyland.com?c={codigo}")
                qr.make(fit=True)
                img_qr = qr.make_image(fill_color=COLOR_MORADO_QR, back_color="white").convert("RGBA")
                
                q_w, q_h = img_qr.size
                l_s = int(q_w * 0.28) 
                pug = logo_pug.resize((l_s, l_s), Image.Resampling.LANCZOS)
                img_qr.paste(pug, (int((q_w-l_s)/2), int((q_h-l_s)/2)), mask=pug)
                
                img_byte_arr = io.BytesIO()
                img_qr.save(img_byte_arr, format='PNG')
                img_qr_bytes = img_byte_arr.getvalue()

                pdf_final_reversos.insert_pdf(doc_trasera_template)
                pagina_trasera = pdf_final_reversos[-1]
                
                rect_qr = fitz.Rect(QR_X_PTS, QR_Y_PTS, QR_X_PTS + QR_SIZE_PTS, QR_Y_PTS + QR_SIZE_PTS)
                pagina_trasera.insert_image(rect_qr, stream=img_qr_bytes)

    # 4. Guardar archivos maestros de producción
    pdf_final_frentes.save(os.path.join(ruta_base, "01_FRENTES_VARIABLES.pdf"))
    pdf_final_reversos.save(os.path.join(ruta_base, "02_REVERSOS_VARIABLES.pdf"))
    
    pdf_final_frentes.close()
    pdf_final_reversos.close()
    doc_frente_template.close()
    doc_trasera_template.close()

    try:
        db.add_all(nuevas_tarjetas)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error en DB: {e}")

    return {"status": "success", "directorio": ruta_base, "total": cantidad}

@router.post("/generar-lote-produccion", dependencies=[Depends(get_api_key)])
def generar_lote_produccion(
    cantidad: int = Query(..., gt=0, le=1000, description="Cantidad de tarjetas únicas"),
    db: Session = Depends(get_db)
):
    nuevas_tarjetas = []
    codigos_memoria = set()
    paginas_reversos = []
    
    # 1. Configuración de Tiempos y Carpetas
    ahora = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    ruta_base = f"tarjetas_generadas/{ahora}"
    ruta_individuales = os.path.join(ruta_base, "individuales")
    os.makedirs(ruta_individuales, exist_ok=True)
    
    # --- CONFIGURACIÓN TÉCNICA ---
    COLOR_MORADO_QR = "#b33dcf" 
    QR_SIZE, QR_X, QR_Y = 350, 85, 70
    
    try:
        # Cargamos las dos caras
        # Asegúrate de tener 'frente_morado.png' y 'trasera_verde.png' en tu carpeta /app
        img_frente = Image.open("frente_morado.png").convert("RGB")
        img_trasera_base = Image.open("trasera_verde.png").convert("RGB")
        logo_pug = Image.open("logo_pug.png").convert("RGBA")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error cargando plantillas: {e}")

    # 2. Generar el PDF del Frente (Solo una página)
    pdf_frente_path = os.path.join(ruta_base, "01_FRENTE_ESTATICO.pdf")
    img_frente.save(pdf_frente_path, "PDF", resolution=300.0)

    # 3. Bucle para generar Reversos Únicos
    codigos_db = {row[0] for row in db.query(TarjetaQR.codigo).all()}

    while len(nuevas_tarjetas) < cantidad:
        random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
        codigo = f"TRIDY-{random_str}"
        
        if codigo not in codigos_db and codigo not in codigos_memoria:
            codigos_memoria.add(codigo)
            nuevas_tarjetas.append(TarjetaQR(codigo=codigo, estado="nuevo"))

            # Crear QR Cuadrado
            qr = qrcode.QRCode(version=2, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=1)
            qr.add_data(f"https://www.tridyland.com?c={codigo}")
            qr.make(fit=True)
            
            img_qr = qr.make_image(fill_color=COLOR_MORADO_QR, back_color="white").convert("RGBA")
            img_qr = img_qr.resize((QR_SIZE, QR_SIZE), Image.Resampling.LANCZOS)
            
            # Poner el Pug
            l_size = int(QR_SIZE * 0.24)
            pug = logo_pug.resize((l_size, l_size), Image.Resampling.LANCZOS)
            img_qr.paste(pug, (int((QR_SIZE-l_size)/2), int((QR_SIZE-l_size)/2)), mask=pug)
            
            # Montar Reverso
            reverso = img_trasera_base.copy()
            reverso.paste(img_qr, (QR_X, QR_Y), mask=img_qr)
            
            # Guardar PNG y recolectar para PDF
            reverso.save(os.path.join(ruta_individuales, f"{codigo}.png"))
            paginas_reversos.append(reverso)

    # 4. Generar el PDF de Reversos (Multipágina)
    if paginas_reversos:
        pdf_reversos_path = os.path.join(ruta_base, "02_REVERSOS_VARIABLES.pdf")
        paginas_reversos[0].save(
            pdf_reversos_path, 
            save_all=True, 
            append_images=paginas_reversos[1:], 
            resolution=300.0,
            quality=95
        )

    # 5. Guardar en Base de Datos
    try:
        db.add_all(nuevas_tarjetas)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error DB: {e}")

    return {
        "status": "success",
        "carpeta": ahora,
        "archivos": ["01_FRENTE_ESTATICO.pdf", "02_REVERSOS_VARIABLES.pdf"],
        "total": cantidad
    }

@router.post("/activar-tarjeta", dependencies=[Depends(get_api_key)])
def activar_tarjeta_stand(
    background_tasks: BackgroundTasks,
    codigo: str = Body(..., embed=True),
    monto_compra: float = Body(..., embed=True),
    db: Session = Depends(get_db)
):
    # 🛡️ SEGURIDAD 1: Evitar montos negativos o en ceros (anti-hackers)
    if monto_compra <= 0:
        raise HTTPException(
            status_code=400, 
            detail="El monto debe ser mayor a 0 para generar magia."
        )

    tarjeta = db.query(TarjetaQR).filter(TarjetaQR.codigo == codigo).first()

    # 🛡️ SEGURIDAD 2: Tarjeta fantasma
    if not tarjeta:
        raise HTTPException(
            status_code=404, 
            detail=f"El código '{codigo}' no existe en la base de datos de Tridyland."
        )

    # Multiplicamos el monto por 10 para la conversión 1:10
    puntos_calculados = math.floor(monto_compra * 10)
    
    xp_vieja = 0
    xp_nueva = 0

    # ESCENARIO 1: Tarjeta Nueva
    if tarjeta.estado == "nuevo":
        xp_vieja = 0
        xp_nueva = puntos_calculados
        tarjeta.estado = "activado"
        tarjeta.puntos_asignados = puntos_calculados
        tarjeta.activated_at = datetime.utcnow()

    # ESCENARIO 2: Tarjeta ya activada pero sin dueño (compró otra vez ese día)
    elif tarjeta.estado == "activado":
        xp_vieja = tarjeta.puntos_asignados
        xp_nueva = xp_vieja + puntos_calculados
        tarjeta.puntos_asignados = xp_nueva

    # ESCENARIO 3: Cliente con cuenta ligada (¡AQUÍ ESTABA EL ERROR!)
    elif tarjeta.estado == "ligado":
        usuario = db.query(Usuario).filter(Usuario.id == tarjeta.usuario_id).first()
        
        # 🛡️ SEGURIDAD 3: Validar que el usuario no haya sido borrado
        if not usuario:
            raise HTTPException(status_code=404, detail="Usuario no encontrado. La tarjeta está corrupta.")

        # 1. Calculamos la XP REAL sumando todo su historial en el Ledger
        xp_vieja = db.query(func.sum(PuntosLedger.puntos)).filter(PuntosLedger.usuario_id == usuario.id).scalar() or 0
        xp_nueva = xp_vieja + puntos_calculados

        # 2. 🛡️ ¡VITAL! Guardamos los nuevos puntos en su historial (Ledger)
        nuevo_registro = PuntosLedger(
            usuario_id=usuario.id,
            puntos=puntos_calculados,
            accion=f"activacion_stand_{codigo}",
            tarjeta_origen_id=tarjeta.id
        )
        db.add(nuevo_registro)

        # 3. Calculamos los niveles para el correo
        nivel_viejo_correo = calcular_nivel_python(xp_vieja)
        nivel_nuevo_correo = calcular_nivel_python(xp_nueva)

        # 4. Mandamos el correo de experiencia
        background_tasks.add_task(
            enviar_correo_experiencia, 
            usuario.email, 
            puntos_calculados, 
            xp_nueva, 
            nivel_nuevo_correo
        )

    # 🚀 EL CÁLCULO UNIVERSAL DE HYPE 🚀
    nivel_viejo = calcular_nivel_python(xp_vieja)
    nivel_nuevo = calcular_nivel_python(xp_nueva)

    subio_nivel = False
    alerta_premio = ""
    mensaje_final = ""

    if nivel_nuevo > nivel_viejo:
        subio_nivel = True
        if nivel_nuevo in [2, 5, 10, 25, 50]: # ¡Agregué el 50 por si acaso llegan al boss final!
            alerta_premio = f"¡DESBLOQUEÓ PREMIO DE NIVEL {nivel_nuevo}! 🎁"
        else:
            alerta_premio = "¡Nuevo Nivel Alcanzado! 🚀"
        
        if tarjeta.estado != "ligado":
            mensaje_final = f"¡Dile que ESTA TARJETA ya es Nivel {nivel_nuevo}! Que la registre YA. " + alerta_premio
        else:
            mensaje_final = f"¡Su cuenta subió a Nivel {nivel_nuevo}! " + alerta_premio
    else:
        if tarjeta.estado != "ligado":
            mensaje_final = f"La tarjeta ahora vale {xp_nueva} XP. ¡Lista para registrar!"
        else:
            mensaje_final = f"Puntos sumados. Tiene {xp_nueva} XP en total."

    # 🛡️ SEGURIDAD 4: Manejo de errores en la Base de Datos
    try:
        db.commit()
    except Exception as e:
        db.rollback() # Deshacemos todo si la base de datos se queja
        print(f"❌ Error al activar tarjeta: {e}")
        raise HTTPException(status_code=500, detail="Error guardando en la Bóveda de Datos.")

    return {
        "status": "success",
        "mensaje": f"¡BEEP! +{puntos_calculados} XP.",
        "detalle_admin": mensaje_final,
        "subio_nivel": subio_nivel,
        "nivel_alcanzado": nivel_nuevo,
        "alerta_premio": alerta_premio
    }

@router.get("/puntos/qr-info")
async def obtener_info_qr(codigo: str, db: Session = Depends(get_db)):
    tarjeta = db.query(TarjetaQR).filter(TarjetaQR.codigo == codigo).first()
    
    if not tarjeta:
        return {"valido": False, "estado": "invalido", "puntos": 0}
    
    return {
        "valido": True,
        "estado": tarjeta.estado, # Puede ser "nuevo", "activado" o "ligado"
        "puntos": tarjeta.puntos_asignados
    }

@router.post("/puntos/reclamar-qr-directo")
async def reclamar_qr_directo(
    background_tasks: BackgroundTasks,
    usuario_id: str = Body(..., embed=True), # Es el correo de Tiendanube
    codigo: str = Body(..., embed=True),
    timestamp: int = Body(..., embed=True),
    hash_seguridad: str = Body(..., embed=True),
    db: Session = Depends(get_db)
):
    # 1. Validar Seguridad
    mensaje_crudo = f"{usuario_id}|{codigo}|{timestamp}"
    hash_esperado = hmac.new(
        key=settings.API_SECRET_KEY.encode('utf-8'), 
        msg=mensaje_crudo.encode('utf-8'), 
        digestmod=hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(hash_esperado, hash_seguridad):
        raise HTTPException(status_code=401, detail="Firma de seguridad inválida.")

    # 2. Validar Tarjeta
    tarjeta = db.query(TarjetaQR).filter(TarjetaQR.codigo == codigo).first()
    if not tarjeta or tarjeta.estado != "activado":
        raise HTTPException(status_code=400, detail="Ese código es inválido o ya fue usado.")

    # 3. Buscar o Crear Usuario localmente
    email = usuario_id
    usuario = db.query(Usuario).filter(Usuario.email == email).first()
    
    if not usuario:
        # Extraemos el nombre del correo (ej. "juan123" de "juan123@mail.com")
        nombre_base = email.split('@')[0].capitalize()
        usuario = Usuario(
            email=email, 
            nombre=nombre_base, # TN mandará su nombre real después por webhook
        )
        db.add(usuario)
        db.flush()

    # 4. Ligar puntos y quemar tarjeta
    puntos_a_sumar = tarjeta.puntos_asignados
    tarjeta.usuario_id = usuario.id
    tarjeta.estado = "ligado"
    tarjeta.claimed_at = datetime.utcnow()

    # 5. Guardar en el Ledger
    db.add(PuntosLedger(
        usuario_id=usuario.id,
        puntos=puntos_a_sumar,
        accion=f"reclamo_qr_{codigo}",
        tarjeta_origen_id=tarjeta.id
    ))
    db.commit()

    # 6. Calcular nivel y mandar correo
    xp_total = db.query(func.sum(PuntosLedger.puntos)).filter(PuntosLedger.usuario_id == usuario.id).scalar() or 0
    nivel_actual = calcular_nivel_python(xp_total)

    background_tasks.add_task(
        enviar_correo_experiencia, 
        usuario.email, 
        puntos_a_sumar, 
        xp_total, 
        nivel_actual
    )

    return {
        "status": "success", 
        "mensaje": f"¡Reclamaste {puntos_a_sumar} XP!",
        "puntos_aceptados": puntos_a_sumar
    }