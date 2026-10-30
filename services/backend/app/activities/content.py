"""Content activities: import from the source, QA, delivery (architecture §5.3)."""

from __future__ import annotations

import httpx
from sqlalchemy import delete, select
from temporalio import activity

from app.activities.common import business_errors
from app.config import get_settings
from app.database import AsyncSessionLocal
from app.domain.enums import Destination
from app.integrations.errors import BusinessError
from app.integrations.polylang import PolylangConnector
from app.integrations.source import SourceTechnicalError
from app.models.job import XLIFFSegment
from app.models.orchestration import Position
from app.workflows.models import DeliveryResult, ImportResult, QaResult
from app.xliff import FindingLevel, check_xml, parse


def polylang() -> PolylangConnector:
    s = get_settings()
    return PolylangConnector(s.POLYLANG_BASE_URL, s.POLYLANG_USERNAME, s.POLYLANG_APP_PASSWORD, s.POLYLANG_TIMEOUT_SECONDS)


def file_name(position: Position) -> str:
    return f"p{position.polylang_post_id}.{position.target_lang}.xlf"


async def _position(session, position_id: int) -> Position:
    position = await session.get(Position, position_id)
    if position is None:
        raise BusinessError(f"Position {position_id} does not exist")
    return position


@activity.defn
@business_errors
async def import_xliff(position_id: int) -> ImportResult:
    """Fetch the .xliff for (post, target language) from Polylang, parse it, store it and its segments."""
    async with AsyncSessionLocal() as session:
        position = await _position(session, position_id)
        if position.polylang_post_id is None:
            raise BusinessError(f"Position {position_id} has no Polylang post")
        post_id, target = position.polylang_post_id, position.target_lang

    async with polylang() as source:
        xml = await source.get_xliff(post_id, target)
    doc = parse(xml)  # XliffError (business) if malformed

    async with AsyncSessionLocal() as session, session.begin():
        position = await _position(session, position_id)
        position.xliff_raw, position.xliff_processed = xml, None
        position.words, position.segments = doc.words, len(doc.units)
        await session.execute(delete(XLIFFSegment).where(XLIFFSegment.position_id == position_id))
        session.add_all(
            XLIFFSegment(
                position_id=position_id, unit_id=u.unit_id, resname=u.resname,
                source_text=u.source, target_text=u.target or None, status="new",
            )
            for u in doc.units
        )
        return ImportResult(file_name=file_name(position), words=doc.words, segments=len(doc.units))


@activity.defn
@business_errors
async def run_qa(position_id: int) -> QaResult:
    """QA on the translated file (fetched from Plunet by `plunet_fetch_translation`)."""
    async with AsyncSessionLocal() as session, session.begin():
        position = await _position(session, position_id)
        if not position.xliff_processed:
            raise BusinessError("No translated file to check")
        doc, findings = check_xml(position.xliff_processed)
        if doc is not None:
            targets = {u.unit_id: u.target for u in doc.units}
            segments = (await session.scalars(select(XLIFFSegment).where(XLIFFSegment.position_id == position_id))).all()
            for segment in segments:
                segment.target_text = targets.get(segment.unit_id)
                segment.status = "translated" if segment.target_text else "needs-translation"
    blocking = sum(f.level == FindingLevel.BLOCKING for f in findings)
    return QaResult(blocking=blocking, warnings=len(findings) - blocking, findings=findings)


@activity.defn
@business_errors
async def deliver(position_id: int) -> DeliveryResult:
    """Return trip: back to Polylang as a linked translation, POST to an endpoint, or nothing."""
    async with AsyncSessionLocal() as session:
        position = await _position(session, position_id)
        destination, url = position.destination, position.destination_url
        post_id, target, title, xml = position.polylang_post_id, position.target_lang, position.title, position.xliff_processed

    if destination == Destination.NONE:
        return DeliveryResult(message="No return trip; the file stays in FOX MLO")
    if not xml:
        raise BusinessError("No translated file to deliver")

    if destination == Destination.ENDPOINT:
        if not url:
            raise BusinessError("No endpoint URL set for this position")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(url, content=xml.encode("utf-8"), headers={"Content-Type": "application/xml"})
        except httpx.HTTPError as exc:
            raise SourceTechnicalError(f"Endpoint {url}: {exc}") from exc
        if response.status_code >= 500:
            raise SourceTechnicalError(f"Endpoint {url}: HTTP {response.status_code}")
        if response.status_code >= 400:
            raise BusinessError(f"Endpoint {url} refused the file: HTTP {response.status_code}")
        return DeliveryResult(message=f"Delivered to {url} (HTTP {response.status_code})", data={"url": url})

    doc = parse(xml)
    async with polylang() as source:
        post = await source.get_post(post_id)
        published = await source.publish_translation(post, target, title, [u.target or "" for u in doc.units])
    return DeliveryResult(
        message=f"Delivered to Polylang as post #{published.id}",
        data={"post_id": published.id, "link": published.link},
    )
