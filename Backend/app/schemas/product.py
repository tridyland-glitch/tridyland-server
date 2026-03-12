from pydantic import BaseModel, Field
from typing import Optional

class ProductBase(BaseModel):
    name: str
    size: Optional[str] = None
    category: Optional[str] = None
    franchise: Optional[str] = None
    base_price: Optional[float] = 0.0

    sku: Optional[str] = None
    tiendanube_id: Optional[str] = None
    tiendanube_url: Optional[str] = None
    ai_description_proposal: Optional[str] = None

class ProductCreate(ProductBase):
    weight_grams: Optional[float] = None
    print_time_minutes: Optional[int] = None
    avg_cost: Optional[float] = None
    image_url: Optional[str] = None
    pass

class Product(ProductBase):
    id: int
    weight_grams: Optional[float] = None
    print_time_minutes: Optional[int] = None
    avg_cost: Optional[float] = None
    image_url: Optional[str] = None
    current_stock: int = Field(default=0, description="Stock disponible en TIENDA (Vendible)")
    stock_taller: int = Field(default=0, description="Stock en proceso/reserva en TALLER")
    items_sold: int = Field(default=0, description="Total de piezas vendidas")
    total_generated: float = Field(default=0.0, description="Dinero estimado generado (Ventas * Precio)")
    
    class Config:
        orm_mode = True
    class Config:
        orm_mode = True

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    size: Optional[str] = None      # "Chico", "Grande"
    category: Optional[str] = None  # "Maceta", "Llavero"
    franchise: Optional[str] = None # "Pokemon"
    
    base_price: Optional[float] = None
    avg_cost: Optional[float] = None
    
    weight_grams: Optional[float] = None
    print_time_minutes: Optional[int] = None
    image_url: Optional[str] = None
    
    class Config:
        orm_mode = True