from pydantic import BaseModel
from temporalio import activity

from app.domain.enums import EventKind, EventLevel
from app.realtime.events import record_event


class EventInput(BaseModel):
    message: str
    kind: EventKind = EventKind.LOG
    level: EventLevel = EventLevel.INFO
    order_id: int | None = None
    position_id: int | None = None
    task_id: int | None = None
    actor: str = "system"
    reason: str | None = None
    data: dict | None = None


@activity.defn
async def write_event(event: EventInput) -> int:
    """Write one event row (trigger → NOTIFY → SSE). Returns the event id."""
    return await record_event(**event.model_dump())
