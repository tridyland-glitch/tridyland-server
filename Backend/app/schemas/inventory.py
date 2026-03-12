from pydantic import BaseModel
from typing import Optional
from enum import Enum

class MovementType(str, Enum):
    PRODUCCION = "PRODUCCION"
    VENTA = "VENTA"
    GARANTIA = "GARANTIA"
    REGALO_MARKETING = "REGALO_MARKETING"
    MERMA_INTERNA = "MERMA_INTERNA"
    AJUSTE_INICIAL = "AJUSTE_INICIAL"
    AJUSTE_INVENTARIO = "AJUSTE_INVENTARIO"

class StageLocation(str, Enum):
    TALLER = "TALLER"
    TIENDA = "TIENDA"

class MovementCreate(BaseModel):
    product_id: int
    type: MovementType
    stage: StageLocation = StageLocation.TIENDA
    quantity: int
    monetary_value: Optional[float] = 0.0
    notes: Optional[str] = None

class MovementResponse(MovementCreate):
    id: int
    class Config:
        orm_mode = True

class SmartInventoryRequest(BaseModel):
    query_text: str  # Lo que dijo el usuario: "Axolote rosa"
    quantity: int
    image_url: Optional[str] = None
    force_create: bool = False # Si True, crea el producto si no existe
    # Datos para creación opcional:
    new_price: Optional[float] = 0
    new_category: Optional[str] = None
