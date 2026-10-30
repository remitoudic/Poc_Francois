import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.integrations.plunet import get_plunet_gateway
from app.temporal.client import get_temporal_client

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/live")
def liveness():
    """Process is up (used by Docker healthchecks; no external calls)."""
    return {"status": "ONLINE"}


@router.get("")
async def health_check(request: Request, db: Session = Depends(get_db)):
    """Health check verifying PostgreSQL, the realtime listener, Temporal, Polylang and Plunet."""
    # Check Database
    db_status = "HEALTHY"
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"UNHEALTHY: {e}"

    listener = getattr(request.app.state, "events_listener", None)
    realtime_status = "HEALTHY" if listener is not None and listener.connected else "UNHEALTHY"

    temporal_status = "HEALTHY"
    try:
        client = await get_temporal_client()
        await client.service_client.check_health()
    except Exception as e:
        temporal_status = f"UNHEALTHY: {e}"

    polylang_status = "HEALTHY"
    try:
        async with httpx.AsyncClient(timeout=5.0) as http:
            res = await http.get(f"{get_settings().POLYLANG_BASE_URL}/wp-json/pll/v1/languages")
            res.raise_for_status()
    except Exception as e:
        polylang_status = f"UNHEALTHY: {e}"

    # Plunet through the gateway the workflows use (the in-memory fake with PLUNET_MODE=fake)
    settings = get_settings()
    try:
        version = await run_in_threadpool(lambda: get_plunet_gateway().version())
        plunet_status = {"success": True, "version": version, "mode": settings.PLUNET_MODE}
    except Exception as e:
        plunet_status = {"success": False, "error": str(e), "mode": settings.PLUNET_MODE}

    return {
        "status": "ONLINE",
        "app_name": "FOX MLO - Plunet XLIFF ETL Server",
        "database": db_status,
        "realtime": realtime_status,
        "temporal": temporal_status,
        "polylang": polylang_status,
        "plunet": plunet_status,
    }
