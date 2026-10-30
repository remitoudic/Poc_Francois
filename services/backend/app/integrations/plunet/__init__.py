"""Plunet BusinessManager integration."""

from functools import lru_cache

from app.config import get_settings
from app.integrations.plunet.enums import ItemStatus, JobStatus, ProjectType, QuoteStatus
from app.integrations.plunet.fake import FakePlunetGateway
from app.integrations.plunet.gateway import (
    PlunetAuthError,
    PlunetBusinessError,
    PlunetError,
    PlunetGateway,
    PlunetTechnicalError,
    SoapPlunetGateway,
    zeep_service_factory,
)

__all__ = [
    "FakePlunetGateway",
    "ItemStatus",
    "JobStatus",
    "PlunetAuthError",
    "PlunetBusinessError",
    "PlunetError",
    "PlunetGateway",
    "PlunetTechnicalError",
    "ProjectType",
    "QuoteStatus",
    "SoapPlunetGateway",
    "get_plunet_gateway",
    "zeep_service_factory",
]


@lru_cache
def get_plunet_gateway() -> PlunetGateway:
    """Process-wide gateway: SOAP against PLUNET_BASE_URL, or in-memory with PLUNET_MODE=fake."""
    settings = get_settings()
    if settings.PLUNET_MODE == "fake":
        return FakePlunetGateway()
    return SoapPlunetGateway(
        zeep_service_factory(settings.PLUNET_BASE_URL, settings.PLUNET_TIMEOUT_SECONDS),
        settings.PLUNET_USERNAME,
        settings.PLUNET_PASSWORD,
    )
