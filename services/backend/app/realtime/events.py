"""Write events. Every insert is announced on NOTIFY by the events_notify trigger, on commit."""

from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.domain.enums import EventKind, EventLevel
from app.models.orchestration import Event


async def add_event(
    session: AsyncSession,
    *,
    message: str,
    kind: EventKind = EventKind.LOG,
    level: EventLevel = EventLevel.INFO,
    order_id: int | None = None,
    position_id: int | None = None,
    task_id: int | None = None,
    actor: str = "system",
    reason: str | None = None,
    data: dict[str, Any] | None = None,
) -> Event:
    """Add an event to the caller's transaction (published when the caller commits)."""
    event = Event(
        kind=kind,
        level=level,
        order_id=order_id,
        position_id=position_id,
        task_id=task_id,
        actor=actor,
        message=message,
        reason=reason,
        data=data,
    )
    session.add(event)
    await session.flush()
    return event


async def record_event(**kwargs: Any) -> int:
    """Write one event in its own transaction. Returns the event id."""
    async with AsyncSessionLocal() as session, session.begin():
        event = await add_event(session, **kwargs)
        return event.id


def serialize_event(event: Event) -> dict[str, Any]:
    return {
        "id": event.id,
        "created_at": event.created_at.isoformat() + "Z",
        "kind": event.kind,
        "level": event.level,
        "order_id": event.order_id,
        "position_id": event.position_id,
        "task_id": event.task_id,
        "actor": event.actor,
        "message": event.message,
        "reason": event.reason,
        "data": event.data,
    }


def scoped_events_query(order_id: int | None, position_id: int | None):
    query = select(Event).order_by(Event.id)
    if order_id is not None:
        query = query.where(Event.order_id == order_id)
    if position_id is not None:
        query = query.where(Event.position_id == position_id)
    return query


async def page_events(session: AsyncSession, query: Select, after_id: int | None, limit: int) -> list[Event]:
    """Oldest first. With `after_id`, the events after it; else the latest `limit` events."""
    if after_id is not None:
        return list((await session.scalars(query.where(Event.id > after_id).limit(limit))).all())
    latest = (await session.scalars(query.order_by(None).order_by(Event.id.desc()).limit(limit))).all()
    return list(reversed(latest))
