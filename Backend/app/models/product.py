from sqlalchemy import Column, Integer, String, Float, Boolean, UniqueConstraint, Text
from sqlalchemy.orm import relationship
from app.core.database import Base

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    size = Column(String, nullable=True)     # "Chico", "Mediano", "Grande"
    category = Column(String, nullable=True) # "Figura", "Fidget", "Cosplay"
    franchise = Column(String, nullable=True)
    
    base_price = Column(Float, default=0.0)
    avg_cost = Column(Float, default=0.0)

    print_time_minutes = Column(Integer, nullable=True)
    weight_grams = Column(Float, nullable=True)
    
    is_active = Column(Boolean, default=True)

    image_url = Column(String, nullable=True)

    sku = Column(String, unique=True, index=True, nullable=True)
    tiendanube_id = Column(String, nullable=True)
    tiendanube_url = Column(String, nullable=True)
    ai_description_proposal = Column(Text, nullable=True)

    movements = relationship("InventoryMovement", back_populates="product")

    __table_args__ = (
        UniqueConstraint('name', 'size', name='uix_product_name_size'),
    )
