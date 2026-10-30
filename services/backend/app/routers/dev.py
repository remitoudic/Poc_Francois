"""Development endpoints (DEV_ENDPOINTS=true only): create orders and play the PM/translator.

Phase 5 replaces order creation with the real API. Driving jobs and quotes needs PLUNET_MODE=fake:
the fake Plunet lives in the worker process, so changes go through small dev workflows on the
Plunet queue, then the sync schedule is triggered so the change is picked up at once.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import WorkflowUpdateFailedError

from app.config import get_settings
from app.database import get_async_session
from app.domain.enums import Destination, OrderKind, OrderStatus, TaskStatus, TaskType
from app.integrations.plunet.fake import FakePlunetGateway
from app.models.orchestration import Customer, Order, Position, Resource, Task, WorkflowTemplate
from app.temporal.client import get_temporal_client
from app.workflows.dev import DevPlunetConvertQuoteWorkflow, DevPlunetJobStatusWorkflow
from app.workflows.models import ActionRequest, OrderInput, QuoteDecision, RestartRequest
from app.workflows.order import OrderWorkflow, position_workflow_id
from app.workflows.position import PositionWorkflow
from app.workflows.sync import SYNC_SCHEDULE_ID, order_workflow_id

router = APIRouter(prefix="/dev", tags=["Dev"])


class DevPosition(BaseModel):
    post_id: int
    title: str
    target_lang: str
    destination: Destination = Destination.POLYLANG


class DevOrder(BaseModel):
    kind: OrderKind = OrderKind.ORDER
    title: str = "Dev order"
    template: str = "standard"
    customer_plunet_id: int = 1  # fake Plunet: 1 Maison Lumière, 2 Alpentech
    pm_plunet_id: int = 11  # fake Plunet: 11 Claire Dubois, 12 Jonas Weber
    source_lang: str = "en"
    deadline: datetime | None = None
    positions: list[DevPosition] = Field(min_length=1)


class DevJobStatus(BaseModel):
    status: str  # Plunet JobStatus name, e.g. ASSIGNED_WAITING, IN_PROGRESS, DELIVERED
    resource_plunet_id: int | None = None  # fake translators: 21, 22


async def _cached(session: AsyncSession, model, plunet_id: int, name: str):
    row = (await session.execute(select(model).where(model.plunet_id == plunet_id))).scalar_one_or_none()
    if row is None:
        row = model(plunet_id=plunet_id, name=name)
        session.add(row)
        await session.flush()
    return row


def _fake_names() -> tuple[dict[int, str], dict[int, str]]:
    fake = FakePlunetGateway()
    return ({c.id: c.name for c in fake.customers},
            {r.id: r.name for r in fake.project_managers + fake.translators})


@router.post("/orders")
async def create_order(body: DevOrder, session: AsyncSession = Depends(get_async_session)):
    """Create an order or quote with its positions and tasks, then start its OrderWorkflow."""
    settings = get_settings()
    template = (await session.execute(select(WorkflowTemplate).where(WorkflowTemplate.code == body.template))).scalar_one_or_none()
    if template is None:
        raise HTTPException(404, f"Unknown template {body.template}")
    customers, resources = _fake_names()
    customer = await _cached(session, Customer, body.customer_plunet_id, customers.get(body.customer_plunet_id, f"Customer {body.customer_plunet_id}"))
    pm = await _cached(session, Resource, body.pm_plunet_id, resources.get(body.pm_plunet_id, f"Resource {body.pm_plunet_id}"))
    for plunet_id, name in resources.items():  # translators show by name once they deliver
        await _cached(session, Resource, plunet_id, name)

    order = Order(
        kind=body.kind, status=OrderStatus.DRAFT, title=body.title, customer_id=customer.id, pm_resource_id=pm.id,
        deadline=body.deadline.replace(tzinfo=None) if body.deadline else None, template_id=template.id,
        source_lang=body.source_lang,
    )
    session.add(order)
    await session.flush()
    for no, p in enumerate(body.positions, start=1):
        position = Position(
            order_id=order.id, no=no, title=p.title, polylang_post_id=p.post_id, source_lang=body.source_lang,
            target_lang=p.target_lang, destination=p.destination,
        )
        position.tasks = [Task(seq=i, type=TaskType(t), status=TaskStatus.PENDING) for i, t in enumerate(template.tasks)]
        session.add(position)
    order.temporal_workflow_id = order_workflow_id(order.id)
    await session.commit()

    client = await get_temporal_client()
    await client.start_workflow(
        OrderWorkflow.run, OrderInput(order_id=order.id, plunet_queue=settings.TEMPORAL_PLUNET_TASK_QUEUE),
        id=order.temporal_workflow_id, task_queue=settings.TEMPORAL_TASK_QUEUE,
    )
    return {"order_id": order.id, "workflow_id": order.temporal_workflow_id}


async def _sync_now() -> None:
    client = await get_temporal_client()
    await client.get_schedule_handle(SYNC_SCHEDULE_ID).trigger()


async def _run_dev(workflow, *args) -> object:
    settings = get_settings()
    if settings.PLUNET_MODE != "fake":
        raise HTTPException(409, "Only available with PLUNET_MODE=fake")
    client = await get_temporal_client()
    result = await client.execute_workflow(
        workflow, args=[*args, settings.TEMPORAL_PLUNET_TASK_QUEUE],
        id=f"dev-{uuid.uuid4().hex[:8]}", task_queue=settings.TEMPORAL_TASK_QUEUE,
    )
    await _sync_now()
    return result


@router.post("/plunet/jobs/{job_id}/status")
async def set_job_status(job_id: int, body: DevJobStatus):
    """Act as the translator/PM in the fake Plunet; the sync then signals the position."""
    await _run_dev(DevPlunetJobStatusWorkflow.run, job_id, body.status, body.resource_plunet_id)
    return {"job_id": job_id, "status": body.status}


@router.post("/plunet/quotes/{order_id}/convert")
async def convert_quote(order_id: int):
    """Act as the PM in the fake Plunet: convert the accepted quote into an order."""
    plunet_order_id = await _run_dev(DevPlunetConvertQuoteWorkflow.run, order_id)
    return {"order_id": order_id, "plunet_order_id": plunet_order_id}


@router.post("/plunet/sync")
async def sync_now():
    await _sync_now()
    return {"triggered": SYNC_SCHEDULE_ID}


@router.post("/orders/{order_id}/accept")
async def accept_quote(order_id: int, body: ActionRequest):
    client = await get_temporal_client()
    await client.get_workflow_handle(order_workflow_id(order_id)).signal(OrderWorkflow.quote_accepted, QuoteDecision(actor=body.actor))
    return {"order_id": order_id, "accepted": True}


@router.post("/orders/{order_id}/reject")
async def reject_quote(order_id: int, body: ActionRequest):
    client = await get_temporal_client()
    decision = QuoteDecision(actor=body.actor, reason=body.reason)
    await client.get_workflow_handle(order_workflow_id(order_id)).signal(OrderWorkflow.quote_rejected, decision)
    return {"order_id": order_id, "rejected": True}


_ACTIONS = {
    "pause": PositionWorkflow.pause,
    "resume": PositionWorkflow.resume,
    "retry": PositionWorkflow.retry,
    "cancel": PositionWorkflow.cancel,
}


@router.post("/positions/{position_id}/{action}")
async def position_action(position_id: int, action: str, body: RestartRequest | ActionRequest):
    """pause | resume | retry | cancel (reason required) | restart (body: seq)."""
    if action == "restart":
        if not isinstance(body, RestartRequest):
            raise HTTPException(422, "restart needs seq")
        update, arg = PositionWorkflow.restart_from, body
    elif action in _ACTIONS:
        update, arg = _ACTIONS[action], ActionRequest(actor=body.actor, reason=body.reason)
    else:
        raise HTTPException(404, f"Unknown action {action}")
    client = await get_temporal_client()
    try:
        state = await client.get_workflow_handle(position_workflow_id(position_id)).execute_update(update, arg)
    except WorkflowUpdateFailedError as err:
        raise HTTPException(409, str(err.cause.message if err.cause else err)) from err
    return state


@router.get("/positions/{position_id}/state")
async def position_state(position_id: int):
    client = await get_temporal_client()
    return await client.get_workflow_handle(position_workflow_id(position_id)).query(PositionWorkflow.state)
