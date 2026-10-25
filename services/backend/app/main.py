from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db
from app.routers import etl, health, plunet, xliff

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB tables on startup
    try:
        init_db()
        print("Database initialized successfully.")
    except Exception as e:
        print(f"Database initialization warning (will retry on connection): {e}")
    yield


app = FastAPI(
    title="FOX MLO - Plunet XLIFF ETL Server",
    description="ETL transport & processing pipeline linking remote APIs, XLIFF files, Plunet BusinessManager, and destination servers.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers under /api/v1
api_v1 = FastAPI()
api_v1.include_router(health.router)
api_v1.include_router(etl.router)
api_v1.include_router(xliff.router)
api_v1.include_router(plunet.router)

app.mount("/api/v1", api_v1)


@app.get("/")
def root():
    return {
        "message": "Welcome to FOX MLO - Plunet XLIFF ETL Server",
        "docs_url": "/docs",
        "api_v1": "/api/v1",
        "status": "ONLINE",
    }
