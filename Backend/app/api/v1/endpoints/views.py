from datetime import datetime
import os
from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from pathlib import Path
from sqlalchemy.orm import Session
from app.core.database import get_db

from app.models.tiendanube import TarjetaQR, Usuario

router = APIRouter()

# --- LÓGICA DE RUTAS SEGURA ---
# Path(__file__) es este archivo (views.py)
# .parent sube niveles: endpoints -> v1 -> api -> app -> Backend (Raíz)
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent

@router.get("/promo", include_in_schema=False)
async def pagina_promo(
    c: str = Query(None), # Capturamos el código de la URL (?c=TRIDY-123)
    db: Session = Depends(get_db)
):
    # 1. Si no viene código, mostramos la página normal (con el error de "Falta código")
    if not c:
        ruta = BASE_DIR / "promo.html"
        with open(ruta, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())

    # 2. Buscamos la tarjeta en la DB
    tarjeta = db.query(TarjetaQR).filter(TarjetaQR.codigo == c).first()

    # 3. LA MAGIA: Si ya está ligada, lo mandamos a la tienda principal
    if tarjeta and tarjeta.estado == "ligado":
        # Puedes mandarlo al home o a una página específica de "Gracias"
        return RedirectResponse(url="https://tridyland.com/?utm_source=qr_reclamado")

    # 4. Si la tarjeta es nueva o activada, le mostramos su landing de registro
    ruta = BASE_DIR / "promo.html"
    if not ruta.exists():
        return HTMLResponse(content="<h1>Error: No veo promo.html</h1>", status_code=404)
        
    with open(ruta, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@router.get("/admin/escaner", response_class=HTMLResponse, include_in_schema=False)
async def pagina_escaner():
    ruta = BASE_DIR / "escaner.html"
    
    if not ruta.exists():
        return HTMLResponse(content=f"<h1>Error: No veo escaner.html en {ruta}</h1>", status_code=404)
        
    with open(ruta, "r", encoding="utf-8") as f:
        return f.read()

@router.get("/login-magico", include_in_schema=False)
async def login_magico(
    token: str = Query(...), 
    db: Session = Depends(get_db)
):
    # 1. Buscar al usuario por el token
    usuario = db.query(Usuario).filter(Usuario.magic_token == token).first()

    # 2. Validar si existe y si no ha expirado
    if not usuario:
        # Si el token no sirve, lo mandamos al registro normal
        return RedirectResponse(url="https://tridyland.com/account/login")
    
    if usuario.token_expires_at and usuario.token_expires_at < datetime.utcnow():
        return RedirectResponse(url="https://tridyland.com/account/login?error=token_expirado")

    # 3. ¡EXITO! Lo mandamos a la tienda con su token en la URL
    # Agregamos el token como parámetro para que nuestro JavaScript en Tiendanube lo guarde
    response = RedirectResponse(url=f"https://tridyland.com/?auth_token={token}")
    return response