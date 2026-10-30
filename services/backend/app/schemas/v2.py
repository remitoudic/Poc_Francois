"""API v2 contract (backend-architecture.md §8). Mirrors services/frontend/src/api/types.ts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.enums import (
    Destination,
    EventKind,
    EventLevel,
    OrderKind,
    OrderStatus,
    Overlay,
    TaskStatus,
    TaskType,
    WorkflowStatus,
)
from app.xliff.qa import QaFinding


class Ref(BaseModel):
    id: int
    name: str


class OrderProgress(BaseModel):
    total: int
    statuses: list[WorkflowStatus]  # one per position, in position order


class Activity(BaseModel):
    message: str
    at: datetime


class OrderSummary(BaseModel):
    id: int
    kind: OrderKind
    status: OrderStatus
    number: str | None
    title: str
    customer: Ref | None
    pm: Ref | None
    deadline: datetime | None
    overdue: bool
    progress: OrderProgress
    last_activity: Activity | None


class TaskOut(BaseModel):
    id: int
    seq: int
    type: TaskType
    status: TaskStatus
    overlay: Overlay | None
    plunet_job_id: int | None
    plunet_job_status: str | None
    assignee: Ref | None
    attempts: int
    cost: float | None
    currency: str | None
    started_at: datetime | None
    finished_at: datetime | None
    duration_seconds: int | None
    error: str | None
    findings: list[QaFinding] | None


class PositionOut(BaseModel):
    id: int
    order_id: int
    no: int
    title: str
    polylang_post_id: int | None
    source_lang: str
    target_lang: str
    plunet_item_id: int | None
    file_name: str
    words: int
    segments: int
    destination: Destination
    destination_url: str | None
    status: WorkflowStatus
    note: str | None
    tasks: list[TaskOut]


class TemplateRef(BaseModel):
    code: str
    name: str


class Totals(BaseModel):
    words: int
    cost: float | None
    currency: str | None
    errors: int
    elapsed_seconds: int


class OrderDetail(OrderSummary):
    template: TemplateRef
    default_destination: Destination
    destination_url: str | None
    source_site: str | None
    source_lang: str
    plunet_order_id: int | None
    plunet_quote_id: int | None
    created_at: datetime
    positions: list[PositionOut]
    totals: Totals


class OrderBrief(BaseModel):
    id: int
    number: str | None
    title: str
    kind: OrderKind
    template: TemplateRef


class PositionDetail(BaseModel):
    order: OrderBrief
    position: PositionOut


class SegmentOut(BaseModel):
    unit_id: str
    source: str
    target: str
    findings: list[QaFinding]


class TemplateOut(BaseModel):
    code: str
    name: str
    tasks: list[TaskType]


class LanguageOut(BaseModel):
    slug: str
    name: str
    locale: str


class SourcePostOut(BaseModel):
    id: int
    title: str
    type: Literal["post", "page"]
    lang: str
    words: int
    translations: dict[str, int]


class EventOut(BaseModel):
    id: int
    created_at: datetime
    kind: EventKind
    level: EventLevel
    order_id: int | None
    position_id: int | None
    task_id: int | None
    actor: str
    message: str
    reason: str | None
    data: dict | None


# --- requests --------------------------------------------------------------------------------


class CreateOrderRequest(BaseModel):
    kind: OrderKind
    title: str = Field(max_length=255)
    customer_id: int
    pm_resource_id: int
    deadline: datetime | None = None
    source_site: str
    source_lang: str
    post_ids: list[int]
    target_langs: list[str]
    template_code: str
    destination: Destination = Destination.POLYLANG
    destination_url: str | None = None


WorkflowActionName = Literal["pause", "resume", "retry", "restart_from", "cancel"]
OrderActionName = Literal["pause", "resume", "retry_failed"]


class WorkflowActionRequest(BaseModel):
    action: WorkflowActionName
    task_seq: int | None = None
    reason: str | None = None


class OrderActionRequest(BaseModel):
    action: OrderActionName


class QuoteDecisionRequest(BaseModel):
    reason: str | None = None


# --- analytics -------------------------------------------------------------------------------


class AnalyticsRow(BaseModel):
    key: str
    label: str
    orders: int
    positions: int
    completed: int
    avg_duration_hours: float | None
    cost: float
    errors: int


class AnalyticsSummary(BaseModel):
    group_by: Literal["pm", "customer"]
    currency: str
    rows: list[AnalyticsRow]
