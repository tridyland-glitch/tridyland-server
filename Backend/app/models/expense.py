import enum
from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class ExpenseCategory(str, enum.Enum):
    MATERIA_PRIMA = "MATERIA_PRIMA"   # Filamento, Resina
    COMPONENTES = "COMPONENTES"       # Imanes, Argollas
    REFACCIONES = "REFACCIONES"       # Hotends, Nozzles
    MAQUINARIA = "MAQUINARIA"         # Impresoras nuevas
    HERRAMIENTAS = "HERRAMIENTAS"     # Pinzas, Espátulas
    EVENTOS = "EVENTOS"               # Cuota del stand
    SERVICIOS = "SERVICIOS"           # Luz, Internet
    LOGISTICA = "LOGISTICA"           # Gasolina, Uber, Envíos
    MARKETING = "MARKETING"           # Ads, Tarjetas
    OTROS = "OTROS"

class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    description = Column(String, nullable=False) # "3 Rollos Polyterra"
    amount = Column(Float, nullable=False)       # $850.00
    category = Column(Enum(ExpenseCategory), nullable=False)
    
    date = Column(DateTime(timezone=True), server_default=func.now())
    supplier = Column(String, nullable=True)     # "Amazon", "3DMarket"
    receipt_url = Column(String, nullable=True)  # Foto del ticket
    notes = Column(Text, nullable=True)

    # RELACIONES
    # 1. Vinculación opcional a un evento (Ej: Pagué la cuota del evento X)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=True)
    event = relationship("Event", back_populates="expenses")