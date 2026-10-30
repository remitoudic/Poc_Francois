"""Positions and their workflows (backend-architecture.md §8)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError

from app.api import views
from app.api.deps import get_actor, get_temporal, temporal_errors
from app.config import get_settings
from app.database import get_async_session
from app.domain.enums import EventKind, EventLevel, OrderKind, TaskType, WorkflowStatus
from app.models.job import XLIFFSegment
from app.models.orchestration import Event, Position, Task
from app.realtime.events import add_event, page_events, scoped_events_query, serialize_event
from app.schemas.v2 import EventOut, PositionDetail, SegmentOut, WorkflowActionRequest
from app.workflows.models import ActionRequest, PositionInput, RestartRequest
from app.workflows.order import position_workflow_id
from app.workflows.position import PositionWorkflow

router = APIRouter(prefix="/positions", tags=["Positions"])

_UPDATES = {
    "pause": PositionWorkflow.pause,
    "resume": PositionWorkflow.resume,
    "retry": PositionWorkflow.retry,
    "cancel": PositionWorkflow.cancel,
    "restart_from": PositionWorkflow.restart_from,
}


async def _position_or_404(session: AsyncSession, position_id: int) -> Position:
    position = await session.get(
        Position, position_id, options=[selectinload(Position.tasks), selectinload(Position.order)],
        populate_existing=True,
    )
    if position is None:
        raise HTTPException(404, f"Position {position_id} not found")
    return position


@router.get("/{position_id}", response_model=PositionDetail)
async def get_position(position_id: int, session: AsyncSession = Depends(get_async_session)):
    return await views.position_detail(session, await _position_or_404(session, position_id))


async def _restart_finished(
    session: AsyncSession, temporal: Client, position: Position, seq: int, actor: str, reason: str | None
) -> None:
    """A completed workflow takes no updates: run a new one for the position from task `seq`."""
    settings = get_settings()
    task = position.tasks[seq]
    try:
        async with temporal_errors("position"):
            await temporal.start_workflow(
                PositionWorkflow.run,
                PositionInput(position_id=position.id, start_from=seq, plunet_queue=settings.TEMPORAL_PLUNET_TASK_QUEUE),
                id=position_workflow_id(position.id), task_queue=settings.TEMPORAL_TASK_QUEUE,
            )
    except WorkflowAlreadyStartedError as err:
        raise HTTPException(409, "The workflow is already running again") from err
    await add_event(
        session, order_id=position.order_id, position_id=position.id, task_id=task.id, kind=EventKind.ACTION,
        actor=actor, reason=reason,
        message=f"P{position.no:02d} · Restart from {TaskType(task.type).value} by {actor} (new workflow run)",
    )
    await session.commit()


@router.post("/{position_id}/actions", response_model=PositionDetail, status_code=202)
async def workflow_action(
    position_id: int,
    body: WorkflowActionRequest,
    actor: str = Depends(get_actor),
    session: AsyncSession = Depends(get_async_session),
    temporal: Client = Depends(get_temporal),
):
    """pause | resume | retry | restart_from (task_seq) | cancel (reason). 409 when the workflow refuses."""
    position = await _position_or_404(session, position_id)
    if body.action == "cancel" and not (body.reason and body.reason.strip()):
        raise HTTPException(422, "A reason is required to cancel")
    if body.action == "restart_from":
        if body.task_seq is None or not 0 <= body.task_seq < len(position.tasks):
            raise HTTPException(422, "restart_from needs the seq of one of the position's tasks")
    if position.order.kind == OrderKind.QUOTE or position.status == WorkflowStatus.NOT_STARTED:
        raise HTTPException(409, "The workflow has not started yet")

    if body.action == "restart_from" and position.status == WorkflowStatus.COMPLETED:
        await _restart_finished(session, temporal, position, body.task_seq, actor, body.reason)
    else:
        request = (
            RestartRequest(seq=body.task_seq, actor=actor, reason=body.reason)
            if body.action == "restart_from" else ActionRequest(actor=actor, reason=body.reason)
        )
        async with temporal_errors("position"):
            await temporal.get_workflow_handle(position_workflow_id(position.id)).execute_update(
                _UPDATES[body.action], request
            )
    return await views.position_detail(session, await _position_or_404(session, position_id))


@router.get("/{position_id}/events", response_model=list[EventOut])
async def position_events(
    position_id: int,
    level: EventLevel | None = None,
    kind: EventKind | None = None,
    task_id: int | None = None,
    after_id: int | None = Query(None, description="Events after this id; without it, the latest ones"),
    limit: int = Query(200, ge=1, le=1000),
    session: AsyncSession = Depends(get_async_session),
):
    await _position_or_404(session, position_id)
    query = scoped_events_query(None, position_id)
    if level:
        query = query.where(Event.level == level)
    if kind:
        query = query.where(Event.kind == kind)
    if task_id:
        query = query.where(Event.task_id == task_id)
    return [serialize_event(e) for e in await page_events(session, query, after_id, limit)]


@router.get("/{position_id}/segments", response_model=list[SegmentOut])
async def position_segments(position_id: int, session: AsyncSession = Depends(get_async_session)):
    """Source and current target per unit, with the last QA findings of each unit."""
    position = await _position_or_404(session, position_id)
    rows = (await session.scalars(
        select(XLIFFSegment).where(XLIFFSegment.position_id == position_id).order_by(XLIFFSegment.id)
    )).all()
    qa: Task | None = next((t for t in reversed(position.tasks) if t.type == TaskType.QA and t.findings), None)
    findings = qa.findings if qa else []
    return [
        SegmentOut(
            unit_id=s.unit_id, source=s.source_text, target=s.target_text or "",
            findings=[f for f in findings if f.get("unit_id") == s.unit_id],
        )
        for s in rows
    ]


@router.get("/{position_id}/xliff")
async def position_xliff(
    position_id: int,
    variant: str = Query("processed", pattern="^(raw|processed)$"),
    session: AsyncSession = Depends(get_async_session),
):
    """The .xliff as imported from Polylang (`raw`) or as translated and checked (`processed`)."""
    position = await _position_or_404(session, position_id)
    content = position.xliff_raw if variant == "raw" else position.xliff_processed
    if not content:
        raise HTTPException(404, f"No {variant} .xliff for this position yet")
    name = views.file_name(position)
    if variant == "raw":
        name = name.replace(".xlf", ".source.xlf")
    return Response(
        content, media_type="application/xliff+xml",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
