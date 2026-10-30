"""Orders and quotes (backend-architecture.md §8)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError

from app.api import views
from app.api.deps import get_actor, get_source, get_temporal, site_name, temporal_errors
from app.config import get_settings
from app.database import get_async_session
from app.domain.enums import EventKind, OrderKind, OrderStatus, TaskStatus, TaskType, WorkflowStatus
from app.integrations.errors import TechnicalError
from app.integrations.polylang import PolylangConnector
from app.integrations.source import SourceBusinessError
from app.models.orchestration import Customer, Order, Position, Resource, Task, WorkflowTemplate
from app.realtime.events import add_event
from app.schemas.v2 import (
    CreateOrderRequest,
    OrderActionRequest,
    OrderDetail,
    OrderSummary,
    QuoteDecisionRequest,
)
from app.workflows.models import ActionRequest, OrderInput, QuoteDecision
from app.workflows.order import OrderWorkflow, position_workflow_id
from app.workflows.position import PositionWorkflow
from app.workflows.sync import order_workflow_id

router = APIRouter(prefix="/orders", tags=["Orders"])

MAX_POSITIONS = 500
_OPEN_QUOTE = (OrderStatus.DRAFT, OrderStatus.AWAITING_ACCEPTANCE)
_CLOSED = (OrderStatus.COMPLETED, OrderStatus.CANCELLED, OrderStatus.REJECTED)


async def _order_or_404(session: AsyncSession, order_id: int) -> Order:
    order = await views.load_order(session, order_id)
    if order is None:
        raise HTTPException(404, f"Order {order_id} not found")
    return order


@router.get("", response_model=list[OrderSummary])
async def list_orders(
    kind: OrderKind | None = None,
    status: OrderStatus | None = None,
    pm: int | None = Query(None, description="Local resource id of the PM"),
    customer: int | None = Query(None, description="Local customer id"),
    attention: bool = Query(False, description="Failed or paused positions, or past the deadline"),
    q: str | None = Query(None, max_length=100),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_async_session),
):
    query = select(Order).options(*views.ORDER_LOAD).order_by(Order.id.desc()).limit(limit).offset(offset)
    if kind:
        query = query.where(Order.kind == kind)
    if status:
        query = query.where(Order.status == status)
    if pm:
        query = query.where(Order.pm_resource_id == pm)
    if customer:
        query = query.where(Order.customer_id == customer)
    if attention:
        overdue = and_(
            Order.kind == OrderKind.ORDER, Order.deadline < datetime.now(UTC).replace(tzinfo=None), Order.status.not_in(_CLOSED)
        )
        query = query.where(or_(Order.status == OrderStatus.NEEDS_ATTENTION, overdue))
    if q and q.strip():
        like = f"%{q.strip()}%"
        query = query.outerjoin(Customer, Customer.id == Order.customer_id).where(
            or_(Order.number.ilike(like), Order.title.ilike(like), Customer.name.ilike(like))
        )
    orders = list((await session.scalars(query)).unique().all())
    return await views.order_summaries(session, orders)


@router.get("/{order_id}", response_model=OrderDetail)
async def get_order(order_id: int, session: AsyncSession = Depends(get_async_session)):
    return await views.order_detail(session, await _order_or_404(session, order_id))


async def _source_posts(source: PolylangConnector, req: CreateOrderRequest):
    """Check the request against Polylang: posts exist in the source language, languages exist."""
    try:
        languages, posts = await asyncio.gather(
            source.list_languages(), asyncio.gather(*(source.get_post(pid) for pid in req.post_ids))
        )
    except SourceBusinessError as err:
        raise HTTPException(422, f"Polylang: {err}") from err
    except TechnicalError as err:
        raise HTTPException(502, f"Polylang is not available: {err}") from err
    known = {lang.slug for lang in languages}
    unknown = [lang for lang in [req.source_lang, *req.target_langs] if lang not in known]
    if unknown:
        raise HTTPException(422, f"Unknown language(s) on {site_name()}: {', '.join(unknown)}")
    wrong = [p.id for p in posts if p.lang != req.source_lang]
    if wrong:
        raise HTTPException(422, f"Post(s) {', '.join(map(str, wrong))} are not in {req.source_lang}")
    return posts


@router.post("", response_model=OrderDetail, status_code=201)
async def create_order(
    req: CreateOrderRequest,
    actor: str = Depends(get_actor),
    session: AsyncSession = Depends(get_async_session),
    source: PolylangConnector = Depends(get_source),
    temporal: Client = Depends(get_temporal),
):
    """Save the order or quote with its positions, then start its OrderWorkflow."""
    post_ids = list(dict.fromkeys(req.post_ids))
    target_langs = list(dict.fromkeys(req.target_langs))
    if not post_ids or not target_langs:
        raise HTTPException(422, "Select at least one post and one target language")
    if req.source_lang in target_langs:
        raise HTTPException(422, "A target language must differ from the source language")
    if len(post_ids) * len(target_langs) > MAX_POSITIONS:
        raise HTTPException(422, f"At most {MAX_POSITIONS} positions per order")
    if req.source_site != site_name():
        raise HTTPException(422, f"Unknown site {req.source_site}")
    template = await session.scalar(select(WorkflowTemplate).where(WorkflowTemplate.code == req.template_code))
    if template is None:
        raise HTTPException(422, f"Unknown template {req.template_code}")
    if await session.get(Customer, req.customer_id) is None:
        raise HTTPException(422, f"Unknown customer {req.customer_id}")
    if await session.get(Resource, req.pm_resource_id) is None:
        raise HTTPException(422, f"Unknown project manager {req.pm_resource_id}")
    posts = await _source_posts(source, req.model_copy(update={"post_ids": post_ids, "target_langs": target_langs}))

    order = Order(
        kind=req.kind, status=OrderStatus.DRAFT, title=req.title.strip() or "Untitled",
        customer_id=req.customer_id, pm_resource_id=req.pm_resource_id,
        deadline=views.utc(req.deadline).replace(tzinfo=None) if req.deadline else None,
        template_id=template.id, default_destination=req.destination, destination_url=req.destination_url,
        source_site=req.source_site, source_lang=req.source_lang,
    )
    session.add(order)
    await session.flush()
    no = 0
    for post in posts:
        for lang in target_langs:
            no += 1
            position = Position(
                order_id=order.id, no=no, title=post.title or f"Post {post.id}", polylang_post_id=post.id,
                source_lang=req.source_lang, target_lang=lang, destination=req.destination,
                destination_url=req.destination_url,
            )
            position.tasks = [Task(seq=i, type=TaskType(t), status=TaskStatus.PENDING) for i, t in enumerate(template.tasks)]
            session.add(position)
    order.temporal_workflow_id = order_workflow_id(order.id)
    noun = "Quote" if req.kind == OrderKind.QUOTE else "Order"
    await add_event(
        session, order_id=order.id, kind=EventKind.ACTION, actor=actor,
        message=f"{noun} created with {no} position(s) ({template.name}); creating it in Plunet",
    )
    await session.commit()

    await _start_order(temporal, order.id)
    return await views.order_detail(session, await _order_or_404(session, order.id))


async def _start_order(temporal: Client, order_id: int) -> None:
    settings = get_settings()
    try:
        async with temporal_errors("order"):
            await temporal.start_workflow(
                OrderWorkflow.run,
                OrderInput(order_id=order_id, plunet_queue=settings.TEMPORAL_PLUNET_TASK_QUEUE),
                id=order_workflow_id(order_id), task_queue=settings.TEMPORAL_TASK_QUEUE,
            )
    except WorkflowAlreadyStartedError:
        pass  # a retried request: the workflow id makes the start idempotent
    except HTTPException as err:
        raise HTTPException(503, f"Order {order_id} is saved but its workflow did not start: {err.detail}") from err


async def _quote_signal(order_id: int, signal, decision: QuoteDecision, session: AsyncSession, temporal: Client):
    order = await _order_or_404(session, order_id)
    if order.kind != OrderKind.QUOTE or order.status not in _OPEN_QUOTE:
        raise HTTPException(409, "Only an open quote can be accepted or rejected")
    async with temporal_errors("order"):
        await temporal.get_workflow_handle(order_workflow_id(order_id)).signal(signal, decision)
    return await views.order_detail(session, await _order_or_404(session, order_id))


@router.post("/{order_id}/accept", response_model=OrderDetail, status_code=202)
async def accept_quote(
    order_id: int,
    actor: str = Depends(get_actor),
    session: AsyncSession = Depends(get_async_session),
    temporal: Client = Depends(get_temporal),
):
    """The customer accepted: FOX MLO sets ACCEPTED in Plunet; positions start once the PM converts it."""
    return await _quote_signal(order_id, OrderWorkflow.quote_accepted, QuoteDecision(actor=actor), session, temporal)


@router.post("/{order_id}/reject", response_model=OrderDetail, status_code=202)
async def reject_quote(
    order_id: int,
    body: QuoteDecisionRequest | None = None,
    actor: str = Depends(get_actor),
    session: AsyncSession = Depends(get_async_session),
    temporal: Client = Depends(get_temporal),
):
    decision = QuoteDecision(actor=actor, reason=body.reason if body else None)
    return await _quote_signal(order_id, OrderWorkflow.quote_rejected, decision, session, temporal)


_ORDER_ACTIONS = {
    "pause": ((WorkflowStatus.RUNNING, WorkflowStatus.WAITING), PositionWorkflow.pause),
    "resume": ((WorkflowStatus.PAUSED,), PositionWorkflow.resume),
    "retry_failed": ((WorkflowStatus.FAILED,), PositionWorkflow.retry),
}


@router.post("/{order_id}/actions", response_model=OrderDetail, status_code=202)
async def order_action(
    order_id: int,
    body: OrderActionRequest,
    actor: str = Depends(get_actor),
    session: AsyncSession = Depends(get_async_session),
    temporal: Client = Depends(get_temporal),
):
    """Apply an action to every position it fits (pause running ones, resume paused, retry failed)."""
    order = await _order_or_404(session, order_id)
    statuses, update = _ORDER_ACTIONS[body.action]
    targets = [p for p in order.positions if p.status in statuses]
    if not targets:
        raise HTTPException(409, f"No position of this order can {body.action.replace('_', ' ')}")
    errors: list[str] = []
    for position in targets:
        try:
            async with temporal_errors("position"):
                await temporal.get_workflow_handle(position_workflow_id(position.id)).execute_update(
                    update, ActionRequest(actor=actor)
                )
        except HTTPException as err:
            errors.append(f"P{position.no:02d}: {err.detail}")
    if len(errors) == len(targets):
        raise HTTPException(409, "; ".join(errors))
    return await views.order_detail(session, await _order_or_404(session, order_id))
