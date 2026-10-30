"""Analytics over the read model (orders only, quotes are not work done)."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.domain.enums import EventLevel, OrderKind, WorkflowStatus
from app.models.orchestration import Customer, Event, Order, Position, Resource, Task
from app.schemas.v2 import AnalyticsRow, AnalyticsSummary

router = APIRouter(prefix="/analytics", tags=["Analytics"])

DEFAULT_CURRENCY = "EUR"


def _naive(value: datetime | None) -> datetime | None:
    return value.astimezone(UTC).replace(tzinfo=None) if value is not None and value.tzinfo else value


@router.get("/summary", response_model=AnalyticsSummary)
async def summary(
    group_by: Literal["pm", "customer"] = "pm",
    from_: datetime | None = Query(None, alias="from", description="Orders created from (inclusive)"),
    to: datetime | None = Query(None, description="Orders created before (exclusive)"),
    session: AsyncSession = Depends(get_async_session),
):
    """Per PM or customer: orders, positions, completed positions, average lead time, cost, errors.

    Lead time of a position = first task start → last task end, completed positions only.
    `cost` is in the currency most tasks are priced in; costs in other currencies are left out.
    """
    model, column = (Resource, Order.pm_resource_id) if group_by == "pm" else (Customer, Order.customer_id)
    scope = [Order.kind == OrderKind.ORDER]
    if from_:
        scope.append(Order.created_at >= _naive(from_))
    if to:
        scope.append(Order.created_at < _naive(to))

    spans = (
        select(Task.position_id, func.min(Task.started_at).label("start"), func.max(Task.finished_at).label("end"))
        .group_by(Task.position_id)
        .subquery()
    )
    positions = (await session.execute(
        select(column, model.name, Order.id, Position.status, spans.c.start, spans.c.end)
        .join(Position, Position.order_id == Order.id)
        .outerjoin(model, model.id == column)
        .outerjoin(spans, spans.c.position_id == Position.id)
        .where(*scope)
    )).all()
    costs = (await session.execute(
        select(column, Task.currency, func.sum(Task.cost), func.count())
        .join(Position, Position.order_id == Order.id).join(Task, Task.position_id == Position.id)
        .where(*scope, Task.cost.is_not(None))
        .group_by(column, Task.currency)
    )).all()
    errors = dict((await session.execute(
        select(column, func.count()).select_from(Event).join(Order, Order.id == Event.order_id)
        .where(*scope, Event.level == EventLevel.ERROR).group_by(column)
    )).all())

    priced = Counter()  # reporting currency = the one most tasks are priced in
    for _, cur, _, count in costs:
        priced[cur] += count
    currency = priced.most_common(1)[0][0] if priced else DEFAULT_CURRENCY
    cost = defaultdict(float)
    for key, cur, total, _ in costs:
        if cur == currency:
            cost[key] += float(total)

    groups: dict = {}
    for key, name, order_id, status, start, end in positions:
        g = groups.setdefault(key, {"label": name or "—", "orders": set(), "positions": 0, "completed": 0, "hours": []})
        g["orders"].add(order_id)
        g["positions"] += 1
        if status == WorkflowStatus.COMPLETED:
            g["completed"] += 1
            if start and end:
                g["hours"].append((end - start).total_seconds() / 3600)

    rows = [
        AnalyticsRow(
            key=str(key) if key is not None else "none", label=g["label"], orders=len(g["orders"]),
            positions=g["positions"], completed=g["completed"],
            avg_duration_hours=round(sum(g["hours"]) / len(g["hours"]), 1) if g["hours"] else None,
            cost=round(cost.get(key, 0.0), 2), errors=errors.get(key, 0),
        )
        for key, g in groups.items()
    ]
    rows.sort(key=lambda r: (-r.orders, r.label.lower()))
    return AnalyticsSummary(group_by=group_by, currency=currency, rows=rows)
