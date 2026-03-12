import time

from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional

# Modelo 1: Para GANAR puntos (El que ya teníamos, bien estricto)
class AcumularRequest(BaseModel):
    usuario_id: str = Field(..., description="Email del cliente")
    puntos: int = Field(..., gt=0, le=50, description="Puntos ganados. Max 50 por request.")
    accion: Literal["click_logo", "juego_clicker", "vista_producto", "add_carrito"]
    clicks_raw: Optional[int] = 0
    timestamp: int
    hash_seguridad: str

    @field_validator('timestamp')
    def check_timestamp(cls, v):
        if abs(int(time.time()) - v) > 60:
            raise ValueError('Timestamp expirado')
        return v

# Modelo 2: Para GASTAR puntos (NUEVO)
class CanjearRequest(BaseModel):
    usuario_id: str = Field(..., description="Email del cliente")
    # gt=0 asegura que no manden "-500" intentando hackear la suma matemática
    puntos_a_gastar: int = Field(..., gt=0, description="Costo del premio en puntos.")
    accion: Literal["compra_tabla_random", "compra_tabla_suerte", "cupon_descuento"]
    timestamp: int
    hash_seguridad: str

    @field_validator('timestamp')
    def check_timestamp(cls, v):
        if abs(int(time.time()) - v) > 60:
            raise ValueError('Timestamp expirado')
        return v

class ReclamoRequest(BaseModel):
    usuario_id: str
    nivel: int
    opcion: str  # "A" o "B"
    timestamp: int
    hash_seguridad: str