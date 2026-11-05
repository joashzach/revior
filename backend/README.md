# The Stranded Network — Backend

FastAPI · PostgreSQL 16 · SQLAlchemy 2 (async) · Alembic. Spec: `../stranded-network-backend-PRD.md`.

## Run with Docker
```
docker compose up -d --build        # db on :5433, api on :8000 (override: API_HOST_PORT / DB_HOST_PORT in .env)
curl localhost:8000/api/v1/health
```
## Run locally
```
cp .env.example .env
docker compose up -d db
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"   # Linux/macOS: .venv/bin/pip
.venv/Scripts/alembic upgrade head
.venv/Scripts/uvicorn app.main:app --workers 1
.venv/Scripts/python -m pytest
```
Always run **exactly one** uvicorn worker (in-process WS hub and background loops).
