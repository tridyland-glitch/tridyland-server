import enum
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Enum, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base

class MovementType(str, enum.Enum):
    PRODUCCION = "PRODUCCION"
    VENTA = "VENTA"
    GARANTIA = "GARANTIA"
    REGALO_MARKETING = "REGALO_MARKETING"
    MERMA_INTERNA = "MERMA_INTERNA"
    AJUSTE_INICIAL = "AJUSTE_INICIAL"
    AJUSTE_INVENTARIO = "AJUSTE_INVENTARIO"

class StageLocation(str, enum.Enum):
    TALLER = "TALLER"   # WIP
    TIENDA = "TIENDA"   # Listo para venta (Stock disponible)
    EVENTO = "EVENTO"   # Se llevó a un mercadito

class InventoryMovement(Base):
    __tablename__ = "inventory_movements"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    product = relationship("Product", back_populates="movements")
    
    type = Column(Enum(MovementType), nullable=False)
    stage = Column(Enum(StageLocation), default=StageLocation.TIENDA)
    
    # Cantidad: Positivo para entradas, Negativo para salidas
    quantity = Column(Integer, nullable=False)

    effective_date = Column(DateTime, nullable=True)
    
    monetary_value = Column(Float, default=0.0)
    notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    effective_date = Column(DateTime, nullable=True) # Cuándo ocurrió realmente (para reportes históricos)

    # RELACIÓN NUEVA: ¿En qué evento se vendió?
    event_id = Column(Integer, ForeignKey("events.id"), nullable=True)
    event = relationship("Event", back_populates="movements")
