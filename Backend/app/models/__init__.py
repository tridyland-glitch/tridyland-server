from app.core.database import Base

# El orden importa un poco, pero al importarlos todos aquí, SQLAlchemy los registra.
from .event import Event
from .product import Product
from .inventory import InventoryMovement
from .expense import Expense
from .filament import Filament