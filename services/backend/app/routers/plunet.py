from fastapi import APIRouter

from app.services.plunet_service import PlunetService

router = APIRouter(prefix="/plunet", tags=["Plunet Integration"])


@router.get("/status")
def get_plunet_status():
    """Retrieve real-time connectivity status and version of Plunet BusinessManager."""
    svc = PlunetService()
    return svc.get_server_version()


@router.post("/test-login")
def test_plunet_login():
    """Authenticate with Plunet API user credentials and retrieve a session UUID."""
    svc = PlunetService()
    return svc.test_login()
