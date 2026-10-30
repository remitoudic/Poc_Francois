"""Plunet activities (queue `fox-plunet`, synchronous, run on a small thread pool).

Idempotency: every creation first checks the id already stored in the database and saves the
new Plunet id in the same activity, so a retried activity never creates a second object.
Every change FOX MLO makes to a job goes to Plunet first; the workflow records the local state
only after the activity returns (architecture §6.2).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy.orm import Session, selectinload
from temporalio import activity

from app.activities.common import business_errors
from app.database import SessionLocal
from app.domain.enums import OrderKind, TaskStatus, TaskType
from app.integrations.errors import BusinessError
from app.integrations.plunet import (
    ItemStatus,
    JobStatus,
    ProjectType,
    QuoteStatus,
    get_plunet_gateway,
)
from app.integrations.plunet.models import ItemDraft, ProjectDraft
from app.models.orchestration import Order, Position, Task
from app.workflows.models import (
    PLUNET_JOB_TYPE,
    JobInfo,
    JobOutcome,
    JobRequest,
    JobStatusSignal,
    ProjectRef,
    SyncChanges,
    SyncJobChange,
    SyncQuoteChange,
    SyncTargets,
    position_tag,
)

_XLIFF_FILE = re.compile(r"\.(xlf|xliff|sdlxliff|mqxliff)$", re.I)
_OPEN_JOB = (TaskStatus.PENDING, TaskStatus.WAITING, TaskStatus.RUNNING, TaskStatus.FAILED)


def _get(session: Session, model, obj_id: int):
    obj = session.get(model, obj_id)
    if obj is None:
        raise BusinessError(f"{model.__name__} {obj_id} does not exist")
    return obj


def _project(order: Order) -> tuple[ProjectType, int]:
    if order.plunet_order_id:
        return ProjectType.ORDER, order.plunet_order_id
    if order.plunet_quote_id:
        return ProjectType.QUOTE, order.plunet_quote_id
    raise BusinessError(f"Order {order.id} is not in Plunet yet")


def _as_utc(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value


# --- Orders and quotes -----------------------------------------------------------------------


@activity.defn
@business_errors
def plunet_create_project(order_id: int) -> ProjectRef:
    """Create the order (Auftrag) or quote (Angebot) in Plunet, once."""
    gw = get_plunet_gateway()
    with SessionLocal() as session:
        order = _get(session, Order, order_id)
        if order.plunet_order_id or order.plunet_quote_id:
            project_type, project_id = _project(order)
            return ProjectRef(project_type=project_type, id=project_id, number=order.number or str(project_id))
        if order.customer is None or order.pm is None:
            raise BusinessError("A customer and a project manager are required to create the order in Plunet")
        draft = ProjectDraft(
            project_name=order.title,
            customer_id=order.customer.plunet_id,
            project_manager_id=order.pm.plunet_id,
            deadline=_as_utc(order.deadline),
            reference=f"FOX-{order.id}",
            memo=f"Created by FOX MLO (order {order.id}).",
        )
        created = gw.create_quote(draft) if order.kind == OrderKind.QUOTE else gw.create_order(draft)
        if created.project_type == ProjectType.QUOTE:
            order.plunet_quote_id = created.id
        else:
            order.plunet_order_id = created.id
        order.number = created.number
        session.commit()
        return ProjectRef(project_type=created.project_type, id=created.id, number=created.number)


@activity.defn
@business_errors
def plunet_set_quote_status(order_id: int, status: str) -> None:
    with SessionLocal() as session:
        order = _get(session, Order, order_id)
        if not order.plunet_quote_id:
            raise BusinessError(f"Order {order_id} has no Plunet quote")
        get_plunet_gateway().set_quote_status(order.plunet_quote_id, QuoteStatus[status])


@activity.defn
@business_errors
def plunet_adopt_order(order_id: int, plunet_order_id: int) -> str:
    """After the PM converted the quote in Plunet: switch the FOX MLO order to the new Plunet order
    and map each position to the order item Plunet copied from the quote item."""
    gw = get_plunet_gateway()
    with SessionLocal() as session:
        order = session.get(Order, order_id, options=[selectinload(Order.positions)])
        items = gw.list_items(ProjectType.ORDER, plunet_order_id)
        number = gw.get_order_number(plunet_order_id)
        for position in order.positions:
            tag = position_tag(position.id)
            match = next((i for i in items if i.description and tag in i.description), None)
            position.plunet_item_id = match.id if match else None  # IMPORT creates it if missing
        order.plunet_order_id, order.number, order.kind = plunet_order_id, number, OrderKind.ORDER
        session.commit()
        return number


# --- Items -----------------------------------------------------------------------------------


@activity.defn
@business_errors
def plunet_create_item(position_id: int) -> int:
    gw = get_plunet_gateway()
    with SessionLocal() as session:
        position = _get(session, Position, position_id)
        if position.plunet_item_id:
            return position.plunet_item_id
        project_type, project_id = _project(position.order)
        item_id = gw.create_item(ItemDraft(
            project_type=project_type,
            project_id=project_id,
            description=f"P{position.no:02d} · {position.title} · {position_tag(position.id)}",
            source_lang=position.source_lang,
            target_lang=position.target_lang,
            deadline=_as_utc(position.order.deadline),
        ))
        position.plunet_item_id = item_id
        session.commit()
        return item_id


@activity.defn
@business_errors
def plunet_upload_source(position_id: int, file_name: str) -> bool:
    """Attach the source .xliff to the item. Returns False when it is already there."""
    gw = get_plunet_gateway()
    with SessionLocal() as session:
        position = _get(session, Position, position_id)
        project_type, _ = _project(position.order)
        if not position.plunet_item_id or not position.xliff_raw:
            raise BusinessError("Item or source file missing; run IMPORT first")
        existing = {f.lstrip("\\/") for f in gw.list_item_files(project_type, position.plunet_item_id)}
        if file_name in existing:
            return False
        gw.upload_document(project_type, position.plunet_item_id, file_name, position.xliff_raw.encode("utf-8"))
        return True


@activity.defn
@business_errors
def plunet_set_item_status(position_id: int, status: str) -> None:
    with SessionLocal() as session:
        position = _get(session, Position, position_id)
        if position.plunet_item_id:
            project_type, _ = _project(position.order)
            get_plunet_gateway().set_item_status(project_type, position.plunet_item_id, ItemStatus[status])


# --- Jobs ------------------------------------------------------------------------------------


@activity.defn
@business_errors
def plunet_create_job(request: JobRequest) -> JobInfo:
    """Create the Plunet job for a human task (decision 7: due date = deadline, no resource)."""
    gw = get_plunet_gateway()
    with SessionLocal() as session:
        task = _get(session, Task, request.task_id)
        position = task.position
        project_type, project_id = _project(position.order)
        if task.plunet_job_id and not request.force_new:
            job = gw.get_job(project_type, task.plunet_job_id)
            return JobInfo(job_id=job.id, status=job.status)
        if not position.plunet_item_id:
            raise BusinessError("The position has no Plunet item")
        job_id = gw.create_job(
            project_type, project_id, position.plunet_item_id, PLUNET_JOB_TYPE[TaskType(task.type)],
            start_date=datetime.now(UTC), due_date=_as_utc(position.order.deadline),
        )
        task.plunet_job_id, task.plunet_job_status = job_id, JobStatus.IN_PREPERATION.name
        session.commit()
        return JobInfo(job_id=job_id, status=JobStatus.IN_PREPERATION.name)


@activity.defn
@business_errors
def plunet_job_outcome(job_id: int) -> JobOutcome:
    """Cost (Plunet job price lines) and assignee of a finished job."""
    gw = get_plunet_gateway()
    job = gw.get_job(ProjectType.ORDER, job_id)
    cost = gw.get_job_cost(ProjectType.ORDER, job_id)
    name = gw.get_resource(job.resource_id).name if job.resource_id else None
    return JobOutcome(cost=cost.amount, currency=cost.currency, resource_id=job.resource_id, resource_name=name)


@activity.defn
@business_errors
def plunet_cancel_job(job_id: int) -> None:
    get_plunet_gateway().set_job_status(ProjectType.ORDER, job_id, JobStatus.CANCELED)


@activity.defn
@business_errors
def plunet_cancel_position(position_id: int) -> int:
    """Cancel every unfinished Plunet job of the position and its item. Returns the job count."""
    gw = get_plunet_gateway()
    with SessionLocal() as session:
        position = _get(session, Position, position_id)
        if not position.order.plunet_order_id:
            return 0
        jobs = [t.plunet_job_id for t in position.tasks if t.plunet_job_id and t.status in _OPEN_JOB]
        for job_id in jobs:
            if gw.get_job(ProjectType.ORDER, job_id).status not in ("CANCELED", "DELIVERED", "APPROVED"):
                gw.set_job_status(ProjectType.ORDER, job_id, JobStatus.CANCELED)
        if position.plunet_item_id:
            gw.set_item_status(ProjectType.ORDER, position.plunet_item_id, ItemStatus.CANCELED)
        return len(jobs)


@activity.defn
@business_errors
def plunet_fetch_translation(position_id: int) -> str:
    """Download the translated .xliff from the last delivered Plunet job (REV, else TRA…)."""
    gw = get_plunet_gateway()
    with SessionLocal() as session:
        position = _get(session, Position, position_id)
        jobs = [t for t in sorted(position.tasks, key=lambda t: -t.seq) if t.plunet_job_id and t.status == TaskStatus.DONE]
        expected = f"p{position.polylang_post_id}.{position.target_lang}.xlf"
        for task in jobs:
            files = [f for f in gw.list_job_output(ProjectType.ORDER, task.plunet_job_id) if _XLIFF_FILE.search(f)]
            if not files:
                continue
            chosen = next((f for f in files if f.lstrip("\\/") == expected), files[0])
            content = gw.download_job_output(ProjectType.ORDER, task.plunet_job_id, chosen)
            position.xliff_processed = content.decode("utf-8-sig")
            session.commit()
            return f"{chosen.lstrip(chr(92) + '/')} from job J-{task.plunet_job_id} ({task.type})"
        raise BusinessError("No translated .xliff in the output folder of the Plunet jobs")


# --- Sync ------------------------------------------------------------------------------------


@activity.defn
@business_errors
def plunet_poll(targets: SyncTargets) -> SyncChanges:
    """Ask Plunet for the current state of open jobs and pending quotes; return what changed."""
    gw = get_plunet_gateway()
    changes = SyncChanges()
    for job in targets.jobs:
        current = gw.get_job(job.project_type, job.job_id)
        if current.status != job.known_status:
            changes.jobs.append(SyncJobChange(
                position_id=job.position_id,
                signal=JobStatusSignal(job_id=job.job_id, status=current.status, resource_id=current.resource_id),
            ))
    for quote in targets.quotes:
        status = gw.get_quote_status(quote.quote_id)
        order_id = gw.get_order_id_for_quote(quote.quote_id)
        if status not in (QuoteStatus.PENDING, QuoteStatus.IN_PREPARATION, QuoteStatus.NEW) or order_id:
            changes.quotes.append(SyncQuoteChange(order_id=quote.order_id, plunet_status=status.name, plunet_order_id=order_id))
    return changes


# --- Development (PLUNET_MODE=fake only) -----------------------------------------------------


@activity.defn
@business_errors
def dev_plunet_job_status(job_id: int, status: str, resource_id: int | None = None) -> None:
    """Act as the translator or PM in the fake Plunet: assign and move a job."""
    gw = get_plunet_gateway()
    if gw.version() != "fake":
        raise BusinessError("Only available with PLUNET_MODE=fake")
    if resource_id:
        gw.assign_resource(ProjectType.ORDER, job_id, resource_id)
    gw.set_job_status(ProjectType.ORDER, job_id, JobStatus[status])


@activity.defn
@business_errors
def dev_plunet_convert_quote(order_id: int) -> int:
    """Act as the PM in the fake Plunet: convert the accepted quote into an order."""
    gw = get_plunet_gateway()
    if gw.version() != "fake":
        raise BusinessError("Only available with PLUNET_MODE=fake")
    with SessionLocal() as session:
        order = _get(session, Order, order_id)
        return gw.convert_quote(order.plunet_quote_id)  # type: ignore[attr-defined]
