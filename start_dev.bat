@echo off
echo [1/3] Iniciando Docker (DB + n8n + Tunnel)...
docker compose up -d

echo [2/3] Esperando a la DB y aplicando Alembic...
timeout /t 5
cd Backend
call venv\Scripts\activate
alembic upgrade head

echo [3/3] Lanzando Backend con Uvicorn...
uvicorn app.main:app --reload --port 8000

echo python -m streamlit run app_factory.p