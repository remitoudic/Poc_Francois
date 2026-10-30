"""In-memory stand-ins for every activity, registered under the real activity names."""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import Callable
from datetime import datetime

from temporalio import activity
from temporalio.exceptions import ApplicationError

from app.activities.common import BUSINESS_ERROR
from app.domain.enums import Destination, OrderKind, TaskType
from app.integrations.plunet.enums import ProjectType
from app.workflows.models import (
    DeliveryResult,
    ImportResult,
    JobInfo,
    JobOutcome,
    JobRequest,
    OrderChange,
    OrderPlan,
    PositionClose,
    PositionPlan,
    ProjectRef,
    QaResult,
    SyncChanges,
    SyncTargets,
    TaskChange,
    TaskSpec,
)
from app.xliff.qa import FindingLevel, QaFinding

FULL = [TaskType.IMPORT, TaskType.PM, TaskType.TRA, TaskType.REV, TaskType.QA, TaskType.DELIVER]
AUTO = [TaskType.IMPORT, TaskType.QA, TaskType.DELIVER]


class World:
    def __init__(self) -> None:
        self.positions: dict[int, PositionPlan] = {}
        self.orders: dict[int, OrderPlan] = {}
        self.calls: list[tuple[str, tuple]] = []
        self.changes: list[TaskChange] = []
        self.order_changes: list[OrderChange] = []
        self.closes: list[PositionClose] = []
        self.qa_failures: dict[int, int] = {}  # position_id -> remaining failing runs
        self.sync_targets = SyncTargets()
        self.sync_changes = SyncChanges()
        self.job_ids = itertools.count(88200)
        self.task_jobs: dict[int, int] = {}
        self.cancel_fails = False  # plunet_cancel_position raises a BusinessError

    def add_position(self, position_id: int, types: list[TaskType] = FULL, order_id: int = 1,
                     deadline: datetime | None = None) -> PositionPlan:
        plan = PositionPlan(
            position_id=position_id, order_id=order_id, no=position_id % 100, title=f"Post {position_id}",
            post_id=400 + position_id, source_lang="en", target_lang="fr", destination=Destination.POLYLANG,
            deadline=deadline,
            tasks=[TaskSpec(task_id=position_id * 10 + i, seq=i, type=t) for i, t in enumerate(types)],
        )
        self.positions[position_id] = plan
        return plan

    def add_order(self, order_id: int, kind: OrderKind, position_ids: list[int]) -> None:
        self.orders[order_id] = OrderPlan(
            order_id=order_id, kind=kind, title="Test", plunet_order_id=None, plunet_quote_id=None,
            position_ids=position_ids,
        )

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]

    def count(self, name: str) -> int:
        return self.names().count(name)

    def messages(self) -> list[str]:
        return [c.message for c in self.changes if c.message]


world = World()


def _log(name: str, *args) -> None:
    world.calls.append((name, args))


def fake(name: str) -> Callable:
    def register(fn: Callable) -> Callable:
        return activity.defn(name=name)(fn)

    return register


# --- orchestration queue ---------------------------------------------------------------------

@fake("load_position")
async def load_position(position_id: int) -> PositionPlan:
    _log("load_position", position_id)
    return world.positions[position_id]


@fake("load_order")
async def load_order(order_id: int) -> OrderPlan:
    _log("load_order", order_id)
    return world.orders[order_id]


@fake("record_task")
async def record_task(change: TaskChange) -> None:
    world.changes.append(change)


@fake("reset_tasks")
async def reset_tasks(position_id: int, from_seq: int) -> None:
    _log("reset_tasks", position_id, from_seq)
    # Like the real projection: reset tasks lose their Plunet job, so the next run creates a new one.
    for spec in world.positions[position_id].tasks[from_seq:]:
        world.task_jobs.pop(spec.task_id, None)


@fake("close_position")
async def close_position(close: PositionClose) -> None:
    world.closes.append(close)


@fake("update_order")
async def update_order(change: OrderChange) -> None:
    world.order_changes.append(change)


@fake("set_position_workflow")
async def set_position_workflow(position_id: int, workflow_id: str) -> None:
    _log("set_position_workflow", position_id, workflow_id)


@fake("collect_sync_targets")
async def collect_sync_targets() -> SyncTargets:
    return world.sync_targets


@fake("import_xliff")
async def import_xliff(position_id: int) -> ImportResult:
    _log("import_xliff", position_id)
    return ImportResult(file_name=f"p{position_id}.fr.xlf", words=120, segments=8)


@fake("run_qa")
async def run_qa(position_id: int) -> QaResult:
    _log("run_qa", position_id)
    if world.qa_failures.get(position_id, 0) > 0:
        world.qa_failures[position_id] -= 1
        finding = QaFinding(code="PLACEHOLDER_MISMATCH", level=FindingLevel.BLOCKING, unit_id="u-002", message="Placeholders differ")
        return QaResult(blocking=1, warnings=0, findings=[finding])
    return QaResult(blocking=0, warnings=0, findings=[])


@fake("deliver")
async def deliver(position_id: int) -> DeliveryResult:
    _log("deliver", position_id)
    return DeliveryResult(message="Delivered to Polylang as post #900")


ORCHESTRATION = [
    load_position, load_order, record_task, reset_tasks, close_position, update_order,
    set_position_workflow, collect_sync_targets, import_xliff, run_qa, deliver,
]


# --- plunet queue ----------------------------------------------------------------------------

@fake("plunet_create_project")
def plunet_create_project(order_id: int) -> ProjectRef:
    _log("plunet_create_project", order_id)
    kind = world.orders[order_id].kind
    project_type = ProjectType.QUOTE if kind == OrderKind.QUOTE else ProjectType.ORDER
    return ProjectRef(project_type=project_type, id=500 + order_id, number=f"N-{order_id}")


@fake("plunet_set_quote_status")
def plunet_set_quote_status(order_id: int, status: str) -> None:
    _log("plunet_set_quote_status", order_id, status)


@fake("plunet_adopt_order")
def plunet_adopt_order(order_id: int, plunet_order_id: int) -> str:
    _log("plunet_adopt_order", order_id, plunet_order_id)
    return f"O-{plunet_order_id}"


@fake("plunet_create_item")
def plunet_create_item(position_id: int) -> int:
    _log("plunet_create_item", position_id)
    return 5000 + position_id


@fake("plunet_upload_source")
def plunet_upload_source(position_id: int, file_name: str) -> bool:
    _log("plunet_upload_source", position_id, file_name)
    return True


@fake("plunet_set_item_status")
def plunet_set_item_status(position_id: int, status: str) -> None:
    _log("plunet_set_item_status", position_id, status)


@fake("plunet_create_job")
def plunet_create_job(request: JobRequest) -> JobInfo:
    _log("plunet_create_job", request.task_id, request.force_new)
    if request.task_id in world.task_jobs and not request.force_new:
        return JobInfo(job_id=world.task_jobs[request.task_id], status="IN_PREPERATION")
    job_id = next(world.job_ids)
    world.task_jobs[request.task_id] = job_id
    return JobInfo(job_id=job_id, status="IN_PREPERATION")


@fake("plunet_job_outcome")
def plunet_job_outcome(job_id: int) -> JobOutcome:
    _log("plunet_job_outcome", job_id)
    return JobOutcome(cost=120.0, currency="EUR", resource_id=21, resource_name="A. Laurent")


@fake("plunet_cancel_job")
def plunet_cancel_job(job_id: int) -> None:
    _log("plunet_cancel_job", job_id)


@fake("plunet_cancel_position")
def plunet_cancel_position(position_id: int) -> int:
    _log("plunet_cancel_position", position_id)
    if world.cancel_fails:
        raise ApplicationError(f"item {5000 + position_id} does not exist", type=BUSINESS_ERROR, non_retryable=True)
    return 1


@fake("plunet_fetch_translation")
def plunet_fetch_translation(position_id: int) -> str:
    _log("plunet_fetch_translation", position_id)
    if world.positions[position_id].post_id == 0:
        raise ApplicationError("No translated .xliff", type=BUSINESS_ERROR, non_retryable=True)
    return f"p{position_id}.fr.xlf from job J-1 (REV)"


@fake("plunet_poll")
def plunet_poll(targets: SyncTargets) -> SyncChanges:
    _log("plunet_poll", len(targets.jobs))
    return world.sync_changes


PLUNET = [
    plunet_create_project, plunet_set_quote_status, plunet_adopt_order, plunet_create_item,
    plunet_upload_source, plunet_set_item_status, plunet_create_job, plunet_job_outcome,
    plunet_cancel_job, plunet_cancel_position, plunet_fetch_translation, plunet_poll,
]


async def until(predicate: Callable[[], object], timeout: float = 10.0) -> None:
    """Wait (real time) until `predicate()` is truthy; used to follow a running workflow."""
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        result = predicate()
        if asyncio.iscoroutine(result):
            result = await result
        if result:
            return
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not reached")
        await asyncio.sleep(0.05)
