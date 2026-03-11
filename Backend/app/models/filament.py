import enum
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Enum, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base

class FilamentType(str, enum.Enum):
    PLA = "PLA"
    PETG = "PETG"
    TPU = "TPU"
    ABS = "ABS"
    ASA = "ASA"
    OTHER = "OTHER"

class Filament(Base):
    __tablename__ = "filaments"

    id = Column(Integer, primary_key=True, index=True)
    brand = Column(String, index=True)    # Polyterra, Bambu Lab
    color = Column(String)                # Rojo Sandía
    type = Column(Enum(FilamentType), default=FilamentType.PLA)
    
    initial_weight = Column(Float, default=1000.0) # Gramos (casi siempre 1kg)
    current_weight = Column(Float, default=1000.0) 
    price = Column(Float, nullable=True)  # Costo del rollo

    is_active = Column(Boolean, default=True)
    opened_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # RELACIÓN NUEVA: ¿A qué gasto corresponde este rollo?
    expense_id = Column(Integer, ForeignKey("expenses.id"), nullable=True)
    expense = relationship("Expense")