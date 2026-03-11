import enum
from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, Text
from sqlalchemy.orm import relationship
from app.core.database import Base

class EventStatus(str, enum.Enum):
    BORRADOR = "BORRADOR"
    CONFIRMADO = "CONFIRMADO"
    COMPLETADO = "COMPLETADO"
    CANCELADO = "CANCELADO"

class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)        # "Mercado San Pedro Dic"
    location = Column(String, nullable=True)
    
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=True)
    
    # Finanzas del Evento
    estimated_fee = Column(Float, default=0.0)   # Presupuesto de la cuota
    status = Column(Enum(EventStatus), default=EventStatus.BORRADOR)
    notes = Column(Text, nullable=True)

    # RELACIONES
    # 1. Gastos asociados (Cuota, Uber, Comida)
    expenses = relationship("Expense", back_populates="event")
    
    # 2. Ventas realizadas en este evento
    movements = relationship("InventoryMovement", back_populates="event")