"""Read model → API v2 shapes. The tables are written by the workflows (activities/projection.py)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.enums import (
    EventLevel,
    OrderKind,
    OrderStatus,
    Overlay,
    TaskStatus,
    TaskType,
    WorkflowStatus,
)
from app.models.orchestration import Event, Order, Position, Task
from app.schemas.v2 import (
    Activity,
    OrderBrief,
    OrderDetail,
    OrderProgress,
    OrderSummary,
    PositionDetail,
    PositionOut,
    Ref,
    TaskOut,
    TemplateRef,
    Totals,
)

LABEL = {
    TaskType.IMPORT: "Import", TaskType.PM: "PM", TaskType.TRA: "Translation",
    TaskType.REV: "Review", TaskType.QA: "QA", TaskType.DELIVER: "Delivery",
}
_FINISHED = (TaskStatus.DONE, TaskStatus.SKIPPED, TaskStatus.CANCELLED)
_CLOSED_ORDER = (OrderStatus.COMPLETED, OrderStatus.CANCELLED, OrderStatus.REJECTED)

ORDER_LOAD = (
    selectinload(Order.customer),
    selectinload(Order.pm),
    selectinload(Order.template),
    selectinload(Order.positions).selectinload(Position.tasks).selectinload(Task.assignee),
)


def utc(value: datetime | None) -> datetime | None:
    """The schema stores naive UTC; the API always sends an explicit offset."""
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


def _now() -> datetime:
    return datetime.now(UTC)


def _naive_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)  # to compare with stored naive UTC


def _ref(obj) -> Ref | None:
    return Ref(id=obj.id, name=obj.name) if obj is not None else None


def file_name(position: Position) -> str:
    return f"p{position.polylang_post_id}.{position.target_lang}.xlf"  # as content.import_xliff names it


def current_task(position: Position) -> Task | None:
    return next((t for t in position.tasks if t.status not in _FINISHED), None)


def is_overdue(order: Order) -> bool:
    return (
        order.deadline is not None and order.kind == OrderKind.ORDER
        and order.status not in _CLOSED_ORDER and utc(order.deadline) < _now()
    )


def _position_note(order: Order, position: Position, delivered: dict[int, str]) -> str | None:
    status = position.status
    if order.kind == OrderKind.QUOTE and status == WorkflowStatus.NOT_STARTED:
        return "Starts when the quote is accepted"
    if status == WorkflowStatus.PAUSED:
        return "Paused · tasks assigned to people continue in Plunet"
    if status == WorkflowStatus.CANCELLED:
        return "Cancelled"
    if status == WorkflowStatus.COMPLETED:
        deliver = next((t for t in reversed(position.tasks) if t.type == TaskType.DELIVER), None)
        return delivered.get(deliver.id) if deliver else None
    task = current_task(position)
    if task is None or status == WorkflowStatus.NOT_STARTED:
        return None
    label = LABEL[TaskType(task.type)]
    if task.status == TaskStatus.FAILED:
        return task.error
    if TaskType(task.type).is_plunet_job:
        job = f"job J-{task.plunet_job_id}" if task.plunet_job_id else "job being created"
        if task.status == TaskStatus.RUNNING:
            who = f" by {task.assignee.name}" if task.assignee else ""
            return f"{label} in progress{who} in Plunet ({job})"
        if task.assignee:
            return f"{label} assigned to {task.assignee.name} in Plunet ({job})"
        return f"{label} waiting in Plunet ({job} · {task.plunet_job_status or 'new'})"
    return f"{label} running" if task.status == TaskStatus.RUNNING else None


def _overlay(position: Position, task: Task) -> Overlay | None:
    if task.status == TaskStatus.FAILED:
        return Overlay.FAILED
    if position.status == WorkflowStatus.PAUSED and task is current_task(position):
        return Overlay.PAUSED
    return Overlay(task.overlay) if task.overlay else None


def task_out(position: Position, task: Task) -> TaskOut:
    end = task.finished_at or (_naive_now() if task.started_at else None)
    return TaskOut(
        id=task.id, seq=task.seq, type=task.type, status=task.status, overlay=_overlay(position, task),
        plunet_job_id=task.plunet_job_id, plunet_job_status=task.plunet_job_status,
        assignee=_ref(task.assignee), attempts=task.attempts,
        cost=float(task.cost) if task.cost is not None else None, currency=task.currency,
        started_at=utc(task.started_at), finished_at=utc(task.finished_at),
        duration_seconds=int((end - task.started_at).total_seconds()) if task.started_at and end else None,
        error=task.error, findings=task.findings,
    )


def position_out(order: Order, position: Position, delivered: dict[int, str]) -> PositionOut:
    return PositionOut(
        id=position.id, order_id=position.order_id, no=position.no, title=position.title,
        polylang_post_id=position.polylang_post_id, source_lang=position.source_lang,
        target_lang=position.target_lang, plunet_item_id=position.plunet_item_id,
        file_name=file_name(position), words=position.words, segments=position.segments,
        destination=position.destination, destination_url=position.destination_url,
        status=position.status, note=_position_note(order, position, delivered),
        tasks=[task_out(position, t) for t in position.tasks],
    )


async def _last_activity(session: AsyncSession, order_ids: list[int]) -> dict[int, Activity]:
    if not order_ids:
        return {}
    rows = await session.execute(
        select(Event.order_id, Event.message, Event.created_at)
        .where(Event.order_id.in_(order_ids))
        .ext(distinct_on(Event.order_id))
        .order_by(Event.order_id, Event.id.desc())
    )
    return {oid: Activity(message=msg, at=utc(at)) for oid, msg, at in rows}


async def _delivery_notes(session: AsyncSession, positions: Iterable[Position]) -> dict[int, str]:
    """Last message of each DELIVER task ("P01 · DELIVER · Delivered to Polylang as post #512")."""
    task_ids = [t.id for p in positions for t in p.tasks if t.type == TaskType.DELIVER and t.status == TaskStatus.DONE]
    if not task_ids:
        return {}
    rows = await session.execute(
        select(Event.task_id, Event.message)
        .where(Event.task_id.in_(task_ids), Event.level == EventLevel.INFO)
        .ext(distinct_on(Event.task_id))
        .order_by(Event.task_id, Event.id.desc())
    )
    return {tid: msg.split(" · ", 2)[-1] for tid, msg in rows}


def _summary_fields(order: Order, activity: Activity | None) -> dict:
    return dict(
        id=order.id, kind=order.kind, status=order.status, number=order.number, title=order.title,
        customer=_ref(order.customer), pm=_ref(order.pm), deadline=utc(order.deadline),
        overdue=is_overdue(order),
        progress=OrderProgress(total=len(order.positions), statuses=[p.status for p in order.positions]),
        last_activity=activity,
    )


async def order_summaries(session: AsyncSession, orders: list[Order]) -> list[OrderSummary]:
    activity = await _last_activity(session, [o.id for o in orders])
    return [OrderSummary(**_summary_fields(o, activity.get(o.id))) for o in orders]


def _totals(order: Order, errors: int) -> Totals:
    tasks = [t for p in order.positions for t in p.tasks]
    costed = [t for t in tasks if t.cost is not None]
    currencies = Counter(t.currency for t in costed)
    currency = currencies.most_common(1)[0][0] if currencies else None
    starts = [t.started_at for t in tasks if t.started_at]
    if starts and order.status in _CLOSED_ORDER:
        end = max((t.finished_at for t in tasks if t.finished_at), default=max(starts))
    else:
        end = _naive_now()
    return Totals(
        words=sum(p.words for p in order.positions),
        cost=round(sum(float(t.cost) for t in costed if t.currency == currency), 2) if costed else None,
        currency=currency, errors=errors,
        elapsed_seconds=int((end - min(starts)).total_seconds()) if starts else 0,
    )


async def load_order(session: AsyncSession, order_id: int) -> Order | None:
    return await session.get(Order, order_id, options=ORDER_LOAD, populate_existing=True)


async def order_detail(session: AsyncSession, order: Order) -> OrderDetail:
    activity = await _last_activity(session, [order.id])
    delivered = await _delivery_notes(session, order.positions)
    errors = await session.scalar(
        select(func.count()).select_from(Event).where(Event.order_id == order.id, Event.level == EventLevel.ERROR)
    )
    return OrderDetail(
        **_summary_fields(order, activity.get(order.id)),
        template=TemplateRef(code=order.template.code, name=order.template.name),
        default_destination=order.default_destination, destination_url=order.destination_url,
        source_site=order.source_site, source_lang=order.source_lang,
        plunet_order_id=order.plunet_order_id, plunet_quote_id=order.plunet_quote_id,
        created_at=utc(order.created_at),
        positions=[position_out(order, p, delivered) for p in order.positions],
        totals=_totals(order, errors or 0),
    )


async def position_detail(session: AsyncSession, position: Position) -> PositionDetail:
    order = await load_order(session, position.order_id)
    position = next(p for p in order.positions if p.id == position.id)
    delivered = await _delivery_notes(session, [position])
    return PositionDetail(
        order=OrderBrief(
            id=order.id, number=order.number, title=order.title, kind=order.kind,
            template=TemplateRef(code=order.template.code, name=order.template.name),
        ),
        position=position_out(order, position, delivered),
    )
