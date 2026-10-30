"""Shared Temporal client (pydantic payloads)."""

import asyncio

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter

from app.config import get_settings

_client: Client | None = None
_lock = asyncio.Lock()


async def connect_temporal() -> Client:
    settings = get_settings()
    return await Client.connect(
        settings.TEMPORAL_ADDRESS,
        namespace=settings.TEMPORAL_NAMESPACE,
        data_converter=pydantic_data_converter,
    )


async def get_temporal_client() -> Client:
    """Lazily connected client, reused for the life of the process."""
    global _client
    if _client is None:
        async with _lock:
            if _client is None:
                _client = await connect_temporal()
    return _client
