"""Reference data for the order form: Plunet customers and PMs, templates, the Polylang source."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_plunet, get_source, site_name
from app.config import get_settings
from app.database import get_async_session
from app.integrations.errors import IntegrationError, TechnicalError
from app.integrations.plunet import PlunetGateway
from app.integrations.polylang import PolylangConnector
from app.integrations.source import SourceBusinessError
from app.models.orchestration import Customer, Resource, WorkflowTemplate
from app.schemas.v2 import LanguageOut, Ref, SourcePostOut, TemplateOut

router = APIRouter(tags=["Reference data"])

# Plunet id lists, refreshed at most every REFERENCE_CACHE_SECONDS (SOAP calls are slow).
_cache: dict[str, tuple[float, list[int]]] = {}


async def _plunet_refs(
    key: str, model, fetch, session: AsyncSession, gateway: PlunetGateway
) -> list[Ref]:
    """Read from Plunet, upsert into the local cache table, return local ids (used everywhere else)."""
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < get_settings().REFERENCE_CACHE_SECONDS:
        plunet_ids = cached[1]
    else:
        try:
            rows = await run_in_threadpool(fetch, gateway)
        except IntegrationError as err:
            raise HTTPException(502, f"Plunet is not available: {err}") from err
        existing = {r.plunet_id: r for r in (await session.scalars(select(model))).all()}
        now = datetime.now(UTC).replace(tzinfo=None)
        for row in rows:
            local = existing.get(row.id)
            if local is None:
                session.add(model(plunet_id=row.id, name=row.name, synced_at=now))
            else:
                local.name, local.synced_at = row.name, now
        await session.commit()
        plunet_ids = [r.id for r in rows]
        _cache[key] = (time.monotonic(), plunet_ids)
    found = (await session.scalars(select(model).where(model.plunet_id.in_(plunet_ids)))).all()
    return sorted((Ref(id=r.id, name=r.name) for r in found), key=lambda r: r.name.lower())


@router.get("/plunet/customers", response_model=list[Ref])
async def list_customers(session: AsyncSession = Depends(get_async_session), gateway: PlunetGateway = Depends(get_plunet)):
    """Active Plunet customers (ids are FOX MLO ids; the Plunet id is kept in the cache table)."""
    return await _plunet_refs("customers", Customer, lambda gw: gw.list_customers(), session, gateway)


@router.get("/plunet/resources", response_model=list[Ref])
async def list_resources(session: AsyncSession = Depends(get_async_session), gateway: PlunetGateway = Depends(get_plunet)):
    """Active internal Plunet resources: the people who can be PM of an order."""
    return await _plunet_refs("project_managers", Resource, lambda gw: gw.list_project_managers(), session, gateway)


@router.get("/templates", response_model=list[TemplateOut])
async def list_templates(session: AsyncSession = Depends(get_async_session)):
    rows = (await session.scalars(select(WorkflowTemplate).order_by(WorkflowTemplate.id))).all()
    return [TemplateOut(code=t.code, name=t.name, tasks=t.tasks) for t in rows]


def _check_site(site: str | None) -> None:
    if site is not None and site != site_name():
        raise HTTPException(404, f"Unknown site {site}")


@router.get("/sources/polylang/sites", response_model=list[str])
async def list_sites():
    return [site_name()]


@router.get("/sources/polylang/languages", response_model=list[LanguageOut])
async def list_languages(site: str | None = None, source: PolylangConnector = Depends(get_source)):
    _check_site(site)
    try:
        languages = await source.list_languages()
    except TechnicalError as err:
        raise HTTPException(502, f"Polylang is not available: {err}") from err
    return [LanguageOut(slug=lang.slug, name=lang.name, locale=lang.locale) for lang in languages]


@router.get("/sources/polylang/posts", response_model=list[SourcePostOut])
async def list_posts(
    lang: str,
    site: str | None = None,
    q: str | None = Query(None, max_length=100),
    source: PolylangConnector = Depends(get_source),
):
    """Posts and pages in the source language, with their word count and existing translations."""
    _check_site(site)
    try:
        posts = await source.list_posts(lang, search=q or None)
    except SourceBusinessError as err:
        raise HTTPException(422, f"Polylang: {err}") from err
    except TechnicalError as err:
        raise HTTPException(502, f"Polylang is not available: {err}") from err
    return [
        SourcePostOut(id=p.id, title=p.title, type="page" if p.type == "page" else "post", lang=p.lang,
                      words=p.words, translations=p.translations)
        for p in posts
    ]
