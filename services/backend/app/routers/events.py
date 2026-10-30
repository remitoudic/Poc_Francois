"""Server-Sent Events stream of the events bus (backend-architecture.md §4.2)."""

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.orchestration import Event
from app.realtime.broadcaster import RESYNC, broadcaster
from app.realtime.events import scoped_events_query, serialize_event

router = APIRouter(prefix="/events", tags=["Realtime"])

REPLAY_LIMIT = 1000


def _frame(event: dict) -> str:
    return f"id: {event['id']}\nevent: {event['kind'].lower()}\ndata: {json.dumps(event)}\n\n"


async def _replay(order_id: int | None, position_id: int | None, after_id: int) -> list[dict]:
    query = (
        scoped_events_query(order_id, position_id).where(Event.id > after_id).limit(REPLAY_LIMIT)
    )
    async with AsyncSessionLocal() as session:
        return [serialize_event(e) for e in (await session.scalars(query)).all()]


@router.get("/stream")
async def stream_events(
    request: Request,
    order_id: int | None = Query(None),
    position_id: int | None = Query(None),
    last_event_id: int | None = Query(None, description="Resume after this event id"),
    last_event_id_header: str | None = Header(None, alias="Last-Event-ID"),
):
    """Live events, optionally scoped to one order or position. Resumes from Last-Event-ID."""
    heartbeat = get_settings().SSE_HEARTBEAT_SECONDS
    resume_from = last_event_id
    if last_event_id_header and last_event_id_header.isdigit():
        resume_from = int(last_event_id_header)

    async def generate() -> AsyncIterator[str]:
        # Subscribe before replaying so nothing falls between the replay and the live stream.
        subscription = broadcaster.subscribe(order_id=order_id, position_id=position_id)
        sent_up_to = resume_from or 0
        try:
            yield "retry: 3000\n: connected\n\n"
            if resume_from is not None:
                for event in await _replay(order_id, position_id, resume_from):
                    sent_up_to = event["id"]
                    yield _frame(event)
            while not subscription.overflowed:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(subscription.queue.get(), timeout=heartbeat)
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                if item is RESYNC:
                    yield "event: resync\ndata: {}\n\n"
                elif item["id"] > sent_up_to:
                    sent_up_to = item["id"]
                    yield _frame(item)
        finally:
            broadcaster.unsubscribe(subscription)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("")
async def list_events(
    order_id: int | None = Query(None),
    position_id: int | None = Query(None),
    after_id: int = Query(0),
    limit: int = Query(200, le=1000),
):
    """Paginated event history (Logs tab)."""
    query = scoped_events_query(order_id, position_id).where(Event.id > after_id).limit(limit)
    async with AsyncSessionLocal() as session:
        return [serialize_event(e) for e in (await session.scalars(query)).all()]
