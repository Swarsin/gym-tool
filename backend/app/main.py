from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.api.v1.endpoints import analysis
from app.database import engine, Base

app = FastAPI(title="Biomechanics Analyzer API")


async def _database_healthcheck() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False

import os

# Configure CORS for React frontend & Vercel deployment
frontend_env = os.getenv("FRONTEND_URL", "").strip("\"' \t\r\n/ ")
custom_origins = [o.strip() for o in frontend_env.split(",") if o.strip()]
default_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
allowed_origins = list(set(custom_origins + default_origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"^https://.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup event to create tables automatically for dev
@app.on_event("startup")
async def startup():
    try:
        async with engine.begin() as conn:
            # Create all tables
            await conn.run_sync(Base.metadata.create_all)
        print("Database tables initialized successfully.")
    except Exception as db_err:
        print(f"Warning: Database startup check non-fatal warning: {db_err}")

import os
from fastapi.staticfiles import StaticFiles

# Ensure static directories exist with absolute path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(os.path.join(STATIC_DIR, "overlays"), exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Include routers
from app.api.v1.endpoints import analytics
app.include_router(analysis.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1/analytics")
app.include_router(analytics.router, prefix="/api/v1") # Supports /api/v1/trends directly too

@app.get("/")
def root():
    return {"status": "ok", "message": "Biomechanics API is running"}


@app.get("/health")
async def healthcheck():
    db_ok = await _database_healthcheck()
    return {
        "status": "ok" if db_ok else "degraded",
        "database": "ok" if db_ok else "unavailable",
        "service": "Biomechanics Analyzer API",
        "version": "1.0.0",
    }


@app.get("/ready")
async def readinesscheck():
    db_ok = await _database_healthcheck()
    if not db_ok:
        return {"status": "not_ready", "database": "unavailable"}
    return {"status": "ready", "database": "ok"}


@app.get("/status")
async def statuscheck():
    db_ok = await _database_healthcheck()
    return {
        "status": "healthy" if db_ok else "degraded",
        "database": db_ok,
        "api": True,
    }


@app.get("/api/v1/health")
async def api_healthcheck():
    db_ok = await _database_healthcheck()
    return {
        "status": "ok" if db_ok else "degraded",
        "database": "ok" if db_ok else "unavailable",
        "service": "Biomechanics Analyzer API",
        "version": "1.0.0",
    }


@app.get("/api/v1/status")
async def api_statuscheck():
    db_ok = await _database_healthcheck()
    return {
        "status": "healthy" if db_ok else "degraded",
        "database": db_ok,
        "api": True,
    }
