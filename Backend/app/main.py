from fastapi import FastAPI
from app.api.v1.api import api_router
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.endpoints import views
from fastapi.staticfiles import StaticFiles
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# --- INICIALIZACIÓN DE LA APP ---
# Agregamos 'dependencies=[Depends(get_api_key)]' para blindar TODA la app
app = FastAPI(
    title="Tridyland Backend", 
    version="1.0.0"
)

origenes_permitidos = [
    "https://tridyland.com",
    "https://www.tridyland.com",
    "https://api.tridyland.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origenes_permitidos, # Solo acepta peticiones de tu tienda
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"], # Permite consultar y enviar puntos
    allow_headers=["*"], # Permite todos los headers (incluyendo Content-Type)
)

app.include_router(api_router, prefix="/api/v1")
app.include_router(views.router)

app.mount("/sounds", StaticFiles(directory=BASE_DIR / "sounds"), name="sounds")

@app.get("/")
def root():
    return {"message": "Bienvenido a la API de Tridyland VoiceOps (Acceso Autorizado)"}