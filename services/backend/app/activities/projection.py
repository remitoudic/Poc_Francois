"""Read-model activities (architecture §5.5). Workflows never touch the database directly.

Each activity runs in one transaction and writes its event in that transaction, so the
NOTIFY → SSE announcement and the row change are published together.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from temporalio import activity

from app.activities.common import business_errors
from app.database import AsyncSessionLocal
from app.domain.enums import (
    EventKind,
    EventLevel,
    OrderKind,
    OrderStatus,
    TaskStatus,
    WorkflowStatus,
)
from app.integrations.errors import BusinessError
from app.integrations.plunet.enums import ProjectType
from app.models.orchestration import Order, Position, Resource, Task
from app.realtime.events import add_event
from app.workflows.models import (
    OrderChange,
    OrderPlan,
    PositionClose,
    PositionPlan,
    SyncJob,
    SyncQuote,
    SyncTargets,
    TaskChange,
    TaskSpec,
)


def _now() -> datetime:
    return datetime.utcnow()  # the schema stores naive UTC


def order_status_from(kind: str, current: str, positions: list[str]) -> str:
    """Order status derived from its positions (quotes keep theirs until converted)."""
    if kind == OrderKind.QUOTE or not positions:
        return current
    if all(s == WorkflowStatus.CANCELLED for s in positions):
        return OrderStatus.CANCELLED
    if all(s in (WorkflowStatus.COMPLETED, WorkflowStatus.CANCELLED) for s in positions):
        return OrderStatus.COMPLETED
    if any(s in (WorkflowStatus.FAILED, WorkflowStatus.PAUSED) for s in positions):
        return OrderStatus.NEEDS_ATTENTION
    return OrderStatus.RUNNING


async def _refresh_order_status(session, order_id: int) -> None:
    order = await session.get(Order, order_id)
    statuses = (await session.scalars(select(Position.status).where(Position.order_id == order_id))).all()
    new = order_status_from(order.kind, order.status, list(statuses))
    if new != order.status:
        order.status = new


async def _resource_id(session, plunet_id: int, name: str | None) -> int:
    """Local id of a Plunet resource, cached on first sight."""
    resource = await session.scalar(select(Resource).where(Resource.plunet_id == plunet_id))
    if resource is None:
        resource = Resource(plunet_id=plunet_id, name=name or f"Plunet resource {plunet_id}")
        session.add(resource)
        await session.flush()
    elif name and resource.name != name:
        resource.name = name
    return resource.id


@activity.defn
@business_errors
async def load_order(order_id: int) -> OrderPlan:
    async with AsyncSessionLocal() as session:
        order = await session.get(Order, order_id, options=[selectinload(Order.positions)])
        if order is None:
            raise BusinessError(f"Order {order_id} does not exist")
        return OrderPlan(
            order_id=order.id,
            kind=order.kind,
            title=order.title,
            plunet_order_id=order.plunet_order_id,
            plunet_quote_id=order.plunet_quote_id,
            position_ids=[p.id for p in order.positions],
        )


@activity.defn
@business_errors
async def load_position(position_id: int) -> PositionPlan:
    async with AsyncSessionLocal() as session:
        position = await session.get(
            Position, position_id, options=[selectinload(Position.tasks), selectinload(Position.order)]
        )
        if position is None:
            raise BusinessError(f"Position {position_id} does not exist")
        return PositionPlan(
            position_id=position.id,
            order_id=position.order_id,
            no=position.no,
            title=position.title,
            post_id=position.polylang_post_id,
            source_lang=position.source_lang,
            target_lang=position.target_lang,
            destination=position.destination,
            deadline=position.order.deadline,
            tasks=[TaskSpec(task_id=t.id, seq=t.seq, type=t.type) for t in position.tasks],
        )


@activity.defn
async def record_task(change: TaskChange) -> None:
    async with AsyncSessionLocal() as session, session.begin():
        position = await session.get(Position, change.position_id)
        task = await session.get(Task, change.task_id) if change.task_id else None
        if task is not None:
            if change.task_status is not None:
                task.status = change.task_status
            if change.attempts is not None:
                task.attempts = change.attempts
            if change.started:
                task.started_at, task.finished_at, task.error, task.findings = _now(), None, None, None
            if change.finished:
                task.finished_at = _now()
            if change.error is not None:
                task.error = change.error
            if change.findings is not None:
                task.findings = [f.model_dump(mode="json") for f in change.findings]
            if change.plunet_job_id is not None:
                task.plunet_job_id = change.plunet_job_id
            if change.plunet_job_status is not None:
                task.plunet_job_status = change.plunet_job_status
            if change.assignee_plunet_id is not None:
                task.assignee_resource_id = await _resource_id(session, change.assignee_plunet_id, change.assignee_name)
            if change.cost is not None:
                task.cost, task.currency = change.cost, change.currency
        if change.position_status is not None and position.status != change.position_status:
            position.status = change.position_status
            await session.flush()
            await _refresh_order_status(session, position.order_id)
        if change.message:
            await add_event(
                session,
                message=change.message,
                kind=change.kind,
                level=change.level,
                order_id=position.order_id,
                position_id=position.id,
                task_id=task.id if task else None,
                actor=change.actor,
                reason=change.reason,
                data=change.data,
            )


@activity.defn
async def reset_tasks(position_id: int, from_seq: int) -> None:
    """Restart: tasks from `from_seq` on go back to PENDING (attempt counts are kept)."""
    async with AsyncSessionLocal() as session, session.begin():
        await session.execute(
            update(Task)
            .where(Task.position_id == position_id, Task.seq >= from_seq)
            .values(
                status=TaskStatus.PENDING, overlay=None, plunet_job_id=None, plunet_job_status=None,
                assignee_resource_id=None, cost=None, currency=None, findings=None, error=None,
                started_at=None, finished_at=None,
            )
        )


@activity.defn
async def close_position(close: PositionClose) -> None:
    """Final state. On CANCELLED every unfinished task becomes CANCELLED too."""
    async with AsyncSessionLocal() as session, session.begin():
        position = await session.get(Position, close.position_id)
        if close.status == WorkflowStatus.CANCELLED:
            await session.execute(
                update(Task)
                .where(Task.position_id == position.id, Task.status.not_in([TaskStatus.DONE, TaskStatus.SKIPPED]))
                .values(status=TaskStatus.CANCELLED, finished_at=_now())
            )
        position.status = close.status
        await session.flush()
        await _refresh_order_status(session, position.order_id)
        await add_event(
            session,
            message=close.message,
            kind=EventKind.STATE,
            level=EventLevel.INFO,
            order_id=position.order_id,
            position_id=position.id,
            actor=close.actor,
            reason=close.reason,
        )


@activity.defn
async def update_order(change: OrderChange) -> None:
    async with AsyncSessionLocal() as session, session.begin():
        order = await session.get(Order, change.order_id)
        if change.status is not None:
            order.status = change.status
        else:
            await _refresh_order_status(session, order.id)
        if change.message:
            await add_event(
                session,
                message=change.message,
                kind=change.kind,
                level=change.level,
                order_id=order.id,
                actor=change.actor,
                reason=change.reason,
            )


@activity.defn
async def set_position_workflow(position_id: int, workflow_id: str) -> None:
    async with AsyncSessionLocal() as session, session.begin():
        await session.execute(update(Position).where(Position.id == position_id).values(temporal_workflow_id=workflow_id))


@activity.defn
async def collect_sync_targets() -> SyncTargets:
    """Open Plunet jobs and quotes awaiting the customer: what the 2-minute sync must poll."""
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(Task.position_id, Task.plunet_job_id, Task.plunet_job_status, Order.plunet_order_id)
            .join(Position, Position.id == Task.position_id)
            .join(Order, Order.id == Position.order_id)
            .where(
                Task.plunet_job_id.is_not(None),
                Task.status.in_([TaskStatus.PENDING, TaskStatus.WAITING, TaskStatus.RUNNING]),
                Position.status.not_in([WorkflowStatus.CANCELLED, WorkflowStatus.COMPLETED]),
            )
        )
        jobs = [
            SyncJob(position_id=pid, job_id=job_id, project_type=ProjectType.ORDER, known_status=status)
            for pid, job_id, status, _ in rows
        ]
        quotes = await session.execute(
            select(Order.id, Order.plunet_quote_id).where(
                Order.kind == OrderKind.QUOTE,
                Order.status == OrderStatus.AWAITING_ACCEPTANCE,
                Order.plunet_quote_id.is_not(None),
            )
        )
        return SyncTargets(jobs=jobs, quotes=[SyncQuote(order_id=o, quote_id=q) for o, q in quotes])
