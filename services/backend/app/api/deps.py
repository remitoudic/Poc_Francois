"""Shared dependencies of the v2 routers. Tests override them (fake Temporal, Polylang, Plunet)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Header, HTTPException
from temporalio.client import Client, WorkflowUpdateFailedError
from temporalio.service import RPCError, RPCStatusCode

from app.config import get_settings
from app.integrations.plunet import PlunetGateway, get_plunet_gateway
from app.integrations.polylang import PolylangConnector
from app.temporal.client import get_temporal_client

MAX_ACTOR = 100


def site_name() -> str:
    """The Polylang site FOX MLO reads from (one per installation for now)."""
    s = get_settings()
    return s.POLYLANG_SITE or s.POLYLANG_BASE_URL.split("://", 1)[-1].rstrip("/")


def get_actor(x_fox_actor: str | None = Header(None)) -> str:
    """Who acts. Until auth exists (phase 7) the UI may send `X-Fox-Actor`; else "anonymous"."""
    actor = (x_fox_actor or "").strip()
    return actor[:MAX_ACTOR] or "anonymous"


async def get_temporal() -> Client:
    return await get_temporal_client()


async def get_source() -> AsyncIterator[PolylangConnector]:
    s = get_settings()
    async with PolylangConnector(
        s.POLYLANG_BASE_URL, s.POLYLANG_USERNAME, s.POLYLANG_APP_PASSWORD, s.POLYLANG_TIMEOUT_SECONDS
    ) as connector:
        yield connector


def get_plunet() -> PlunetGateway:
    return get_plunet_gateway()


@asynccontextmanager
async def temporal_errors(what: str):
    """Map Temporal failures: validator rejection → 409, unknown or finished workflow → 404/409."""
    try:
        yield
    except WorkflowUpdateFailedError as err:
        cause = err.cause
        raise HTTPException(409, getattr(cause, "message", None) or str(cause or err)) from err
    except RPCError as err:
        if err.status == RPCStatusCode.NOT_FOUND:
            if "completed" in err.message.lower() or "finished" in err.message.lower():
                raise HTTPException(409, f"The {what} workflow has already finished") from err
            raise HTTPException(404, f"No running workflow for this {what}") from err
        if err.status == RPCStatusCode.FAILED_PRECONDITION:
            raise HTTPException(409, err.message) from err
        raise HTTPException(503, f"Temporal is not available: {err.message}") from err
