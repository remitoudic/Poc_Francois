"""Payloads exchanged between workflows and activities (pydantic, via the Temporal data converter).

Kept free of I/O so the workflow sandbox can import them.
"""

from datetime import datetime

from pydantic import BaseModel

from app.domain.enums import (
    Destination,
    EventKind,
    EventLevel,
    OrderKind,
    OrderStatus,
    TaskStatus,
    TaskType,
    WorkflowStatus,
)
from app.integrations.plunet.enums import ProjectType
from app.xliff.qa import QaFinding

# Plunet job type short names on the FOX instance (verified on the live portal).
PLUNET_JOB_TYPE = {TaskType.PM: "PRM", TaskType.TRA: "TRA", TaskType.REV: "REV"}


def position_tag(position_id: int) -> str:
    """Marker written into the Plunet item description; Plunet keeps it through quote conversion."""
    return f"FOX-P{position_id}"


# --- Plans (read from the database at workflow start) -------------------------------------


class TaskSpec(BaseModel):
    task_id: int
    seq: int
    type: TaskType
    attempts: int = 0  # runs so far; a restarted position keeps counting


class PositionPlan(BaseModel):
    position_id: int
    order_id: int
    no: int
    title: str
    post_id: int | None
    source_lang: str
    target_lang: str
    destination: Destination
    deadline: datetime | None
    tasks: list[TaskSpec]


class OrderPlan(BaseModel):
    order_id: int
    kind: OrderKind
    title: str
    plunet_order_id: int | None
    plunet_quote_id: int | None
    position_ids: list[int]


# --- Inputs and results ---------------------------------------------------------------------


DEFAULT_PLUNET_QUEUE = "fox-plunet"


class PositionInput(BaseModel):
    position_id: int
    start_from: int = 0  # > 0 restarts a finished position from that task (phase 5 "Restart from…")
    plunet_queue: str = DEFAULT_PLUNET_QUEUE  # workflows never read settings (sandbox)


class OrderInput(BaseModel):
    order_id: int
    plunet_queue: str = DEFAULT_PLUNET_QUEUE


class PositionResult(BaseModel):
    position_id: int
    status: WorkflowStatus


class ProjectRef(BaseModel):
    project_type: ProjectType
    id: int
    number: str


class ImportResult(BaseModel):
    file_name: str
    words: int
    segments: int


class JobRequest(BaseModel):
    task_id: int
    force_new: bool = False  # retry/restart of a human task creates a new Plunet job


class JobInfo(BaseModel):
    job_id: int
    status: str  # raw Plunet JobStatus name


class JobOutcome(BaseModel):
    cost: float | None
    currency: str | None
    resource_id: int | None
    resource_name: str | None


class QaResult(BaseModel):
    blocking: int
    warnings: int
    findings: list[QaFinding]


class DeliveryResult(BaseModel):
    message: str
    data: dict | None = None


# --- Projection (read model) ---------------------------------------------------------------


class TaskChange(BaseModel):
    """One state change, written to tasks/positions/orders and announced as an event.

    `None` leaves a field unchanged.
    """

    position_id: int
    task_id: int | None = None
    task_status: TaskStatus | None = None
    position_status: WorkflowStatus | None = None
    attempts: int | None = None
    started: bool = False  # set started_at, clear finished_at/error/findings
    finished: bool = False  # set finished_at
    error: str | None = None
    findings: list[QaFinding] | None = None
    plunet_job_id: int | None = None
    plunet_job_status: str | None = None
    assignee_plunet_id: int | None = None
    assignee_name: str | None = None
    cost: float | None = None
    currency: str | None = None
    # event
    message: str | None = None
    kind: EventKind = EventKind.STATE
    level: EventLevel = EventLevel.INFO
    actor: str = "system"
    reason: str | None = None
    data: dict | None = None


class OrderChange(BaseModel):
    order_id: int
    status: OrderStatus | None = None  # None = recompute from the positions
    message: str | None = None
    level: EventLevel = EventLevel.INFO
    kind: EventKind = EventKind.STATE
    actor: str = "system"
    reason: str | None = None


class PositionClose(BaseModel):
    position_id: int
    status: WorkflowStatus  # COMPLETED or CANCELLED
    message: str
    actor: str = "system"
    reason: str | None = None


# --- Signals and updates -------------------------------------------------------------------


class JobStatusSignal(BaseModel):
    job_id: int
    status: str  # raw Plunet JobStatus name
    resource_id: int | None = None


class QuoteDecision(BaseModel):
    actor: str = "system"
    reason: str | None = None
    in_plunet: bool = False  # True when detected by the sync (already true in Plunet)


class QuoteConverted(BaseModel):
    plunet_order_id: int


class ActionRequest(BaseModel):
    actor: str = "system"
    reason: str | None = None


class RestartRequest(ActionRequest):
    seq: int


class TaskState(BaseModel):
    seq: int
    type: TaskType
    status: TaskStatus
    attempts: int
    plunet_job_id: int | None
    plunet_job_status: str | None
    error: str | None


class PositionState(BaseModel):
    position_id: int
    status: WorkflowStatus
    cursor: int
    paused: bool
    cancel_reason: str | None
    tasks: list[TaskState]


# --- Plunet sync ---------------------------------------------------------------------------


class SyncJob(BaseModel):
    position_id: int
    job_id: int
    project_type: ProjectType
    known_status: str | None


class SyncQuote(BaseModel):
    order_id: int
    quote_id: int


class SyncTargets(BaseModel):
    jobs: list[SyncJob] = []
    quotes: list[SyncQuote] = []


class SyncJobChange(BaseModel):
    position_id: int
    signal: JobStatusSignal


class SyncQuoteChange(BaseModel):
    order_id: int
    plunet_status: str
    plunet_order_id: int | None


class SyncChanges(BaseModel):
    jobs: list[SyncJobChange] = []
    quotes: list[SyncQuoteChange] = []
