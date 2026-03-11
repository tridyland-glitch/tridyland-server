from fastapi import APIRouter
from app.api.v1.endpoints import (
    products,
    inventory,
    import_data,
    reports,
    import_expenses,
    analytics,
    tiendanube
)

api_router = APIRouter()
api_router.include_router(products.router, prefix="/products", tags=["products"])
api_router.include_router(inventory.router, prefix="/movements", tags=["inventory"])
api_router.include_router(import_data.router, prefix="/import", tags=["import"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(import_expenses.router, prefix="/import_expenses", tags=["import_expenses"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(tiendanube.router, prefix="/tiendanube", tags=["tiendanube"])