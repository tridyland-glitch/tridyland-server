import os
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader
from app.core.config import settings

# --- CONFIGURACIÓN DE SEGURIDAD ---
API_KEY_NAME = "X-API-KEY"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# Leemos la contraseña maestra desde las variables de entorno
API_SECRET_KEY = settings.API_SECRET_KEY

async def get_api_key(api_key_header: str = Security(api_key_header)):
    """
    Valida que la API Key recibida coincida con la del servidor.
    """
    if api_key_header == API_SECRET_KEY:
        return api_key_header
    
    # Si la llave no coincide o no existe, lanzamos error 403
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Acceso Denegado: Te falta la API Key, crack."
    )