from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.realtime.broadcaster import broadcaster
from app.realtime.listener import EventListener
from app.routers import etl, events, health, plunet, system, xliff

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is managed by Alembic (`alembic upgrade head` runs before the API starts).
    listener = EventListener(broadcaster)
    listener.start()
    app.state.events_listener = listener
    api_v1.state.events_listener = listener  # routers run on the mounted sub-app
    yield
    await listener.stop()


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
api_v1.include_router(events.router)
api_v1.include_router(system.router)

app.mount("/api/v1", api_v1)


@app.get("/")
def root():
    return {
        "message": "Welcome to FOX MLO - Plunet XLIFF ETL Server",
        "docs_url": "/docs",
        "api_v1": "/api/v1",
        "status": "ONLINE",
    }
