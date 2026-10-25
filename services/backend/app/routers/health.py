from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.plunet_service import PlunetService

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("")
def health_check(db: Session = Depends(get_db)):
    """Health check verifying FastAPI, PostgreSQL database, and Plunet API status."""
    # Check Database
    db_status = "HEALTHY"
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"UNHEALTHY: {e}"

    # Check Plunet API Version
    plunet_svc = PlunetService()
    plunet_status = plunet_svc.get_server_version()

    return {
        "status": "ONLINE",
        "app_name": "FOX MLO - Plunet XLIFF ETL Server",
        "database": db_status,
        "plunet": plunet_status,
    }
