"""In-memory PlunetGateway for tests and for running FOX MLO without a Plunet portal
(`PLUNET_MODE=fake`). It enforces the same rules the real API does where FOX MLO relies on them."""

from __future__ import annotations

import itertools
import threading
from dataclasses import dataclass, field

from app.integrations.plunet.enums import ItemStatus, JobStatus, ProjectType, QuoteStatus
from app.integrations.plunet.gateway import PlunetBusinessError
from app.integrations.plunet.models import (
    CreatedProject,
    ItemDraft,
    Money,
    PlunetCustomer,
    PlunetJob,
    PlunetLanguage,
    PlunetResource,
    ProjectDraft,
)

JOB_TYPES = {"PM", "TRA", "REV"}


@dataclass
class _Item:
    draft: ItemDraft
    status: ItemStatus = ItemStatus.IN_PREPERATION
    documents: dict[str, bytes] = field(default_factory=dict)


@dataclass
class _Job:
    job: PlunetJob
    project_id: int
    price: float = 0.0


class FakePlunetGateway:
    def __init__(
        self,
        customers: list[PlunetCustomer] | None = None,
        project_managers: list[PlunetResource] | None = None,
        currency: str = "EUR",
    ):
        self.customers = customers or [
            PlunetCustomer(id=1, name="Maison Lumière SA", currency="EUR"),
            PlunetCustomer(id=2, name="Alpentech GmbH", currency="EUR"),
        ]
        self.project_managers = project_managers or [
            PlunetResource(id=11, name="Claire Dubois", email="claire@example.com"),
            PlunetResource(id=12, name="Jonas Weber", email="jonas@example.com"),
        ]
        self.currency = currency
        self.orders: dict[int, ProjectDraft] = {}
        self.quotes: dict[int, tuple[ProjectDraft, QuoteStatus, int | None]] = {}
        self.items: dict[int, _Item] = {}
        self.jobs: dict[int, _Job] = {}
        self._ids = itertools.count(1000)
        self._lock = threading.Lock()

    def _next(self) -> int:
        with self._lock:
            return next(self._ids)

    def _reject(self, op: str, msg: str) -> PlunetBusinessError:
        return PlunetBusinessError(op, -1, msg)

    # --- Reference data -------------------------------------------------------------------

    def version(self) -> str:
        return "fake"

    def list_customers(self) -> list[PlunetCustomer]:
        return list(self.customers)

    def list_project_managers(self) -> list[PlunetResource]:
        return list(self.project_managers)

    def list_languages(self) -> list[PlunetLanguage]:
        return [
            PlunetLanguage(id=327, name="English", code="en"),
            PlunetLanguage(id=326, name="French", code="fr-FR"),
            PlunetLanguage(id=323, name="German", code="de-DE"),
            PlunetLanguage(id=141, name="Italian", code="it-IT"),
            PlunetLanguage(id=292, name="Spanish (Spain)", code="es-ES"),
        ]

    # --- Orders and quotes ----------------------------------------------------------------

    def _check_draft(self, op: str, draft: ProjectDraft) -> None:
        if not any(c.id == draft.customer_id for c in self.customers):
            raise self._reject(op, f"customer {draft.customer_id} does not exist")
        if draft.project_manager_id and not any(r.id == draft.project_manager_id for r in self.project_managers):
            raise self._reject(op, f"resource {draft.project_manager_id} does not exist")

    def create_order(self, draft: ProjectDraft) -> CreatedProject:
        self._check_draft("DataOrder30.insert2", draft)
        order_id = self._next()
        self.orders[order_id] = draft
        return CreatedProject(project_type=ProjectType.ORDER, id=order_id, number=f"O-{order_id}")

    def create_quote(self, draft: ProjectDraft) -> CreatedProject:
        self._check_draft("DataQuote30.insert2", draft)
        quote_id = self._next()
        self.quotes[quote_id] = (draft, QuoteStatus.IN_PREPARATION, None)
        return CreatedProject(project_type=ProjectType.QUOTE, id=quote_id, number=f"Q-{quote_id}")

    def _quote(self, quote_id: int) -> tuple[ProjectDraft, QuoteStatus, int | None]:
        if quote_id not in self.quotes:
            raise self._reject("DataQuote30", f"quote {quote_id} does not exist")
        return self.quotes[quote_id]

    def get_quote_status(self, quote_id: int) -> QuoteStatus:
        return self._quote(quote_id)[1]

    def set_quote_status(self, quote_id: int, status: QuoteStatus) -> None:
        draft, _, order_id = self._quote(quote_id)
        self.quotes[quote_id] = (draft, status, order_id)

    def get_order_id_for_quote(self, quote_id: int) -> int | None:
        return self._quote(quote_id)[2]

    def _delete_project(self, project_id: int) -> None:
        item_ids = {i for i, item in self.items.items() if item.draft.project_id == project_id}
        self.items = {i: v for i, v in self.items.items() if i not in item_ids}
        self.jobs = {j: v for j, v in self.jobs.items() if v.job.item_id not in item_ids}

    def delete_order(self, order_id: int) -> None:
        if self.orders.pop(order_id, None) is None:
            raise self._reject("DataOrder30.delete", f"order {order_id} does not exist")
        self._delete_project(order_id)

    def delete_quote(self, quote_id: int) -> None:
        self._quote(quote_id)
        del self.quotes[quote_id]
        self._delete_project(quote_id)

    def convert_quote(self, quote_id: int) -> int:
        """Test helper: what a PM does in Plunet when turning an accepted quote into an order."""
        draft, _, _ = self._quote(quote_id)
        order_id = self.create_order(draft).id
        self.quotes[quote_id] = (draft, QuoteStatus.CHANGE_INTO_ORDER, order_id)
        return order_id

    # --- Items and documents --------------------------------------------------------------

    def _project_exists(self, project_type: ProjectType, project_id: int) -> bool:
        return project_id in (self.orders if project_type == ProjectType.ORDER else self.quotes)

    def create_item(self, draft: ItemDraft) -> int:
        if not self._project_exists(draft.project_type, draft.project_id):
            raise self._reject("DataItem30.insert2", f"project {draft.project_id} does not exist")
        if draft.project_type == ProjectType.QUOTE and self.quotes[draft.project_id][1] not in (
            QuoteStatus.NEW, QuoteStatus.IN_PREPARATION, QuoteStatus.CHECK_CLEARANCE
        ):
            raise self._reject("DataItem30.insert2", "The action is not allowed due to the object related status.")
        item_id = self._next()
        self.items[item_id] = _Item(draft)
        return item_id

    def _item(self, item_id: int) -> _Item:
        if item_id not in self.items:
            raise self._reject("DataItem30", f"item {item_id} does not exist")
        return self.items[item_id]

    def set_item_status(self, project_type: ProjectType, item_id: int, status: ItemStatus) -> None:
        self._item(item_id).status = status

    def upload_document(self, project_type: ProjectType, item_id: int, file_name: str, content: bytes) -> None:
        self._item(item_id).documents[file_name] = content

    # --- Jobs -----------------------------------------------------------------------------

    def create_job(self, project_type: ProjectType, project_id: int, item_id: int, job_type: str) -> int:
        if job_type not in JOB_TYPES:
            raise self._reject("DataJob30.insert2", f"unknown job type {job_type}")
        self._item(item_id)
        job_id = self._next()
        self.jobs[job_id] = _Job(
            PlunetJob(
                id=job_id,
                item_id=item_id,
                project_type=project_type,
                job_type=job_type,
                status=JobStatus.IN_PREPERATION.name,
            ),
            project_id,
        )
        return job_id

    def _job(self, job_id: int) -> _Job:
        if job_id not in self.jobs:
            raise self._reject("DataJob30", f"job {job_id} does not exist")
        return self.jobs[job_id]

    def get_job(self, project_type: ProjectType, job_id: int) -> PlunetJob:
        return self._job(job_id).job.model_copy()

    def list_item_jobs(self, project_type: ProjectType, item_id: int) -> list[PlunetJob]:
        return [j.job.model_copy() for j in self.jobs.values() if j.job.item_id == item_id]

    def set_job_status(self, project_type: ProjectType, job_id: int, status: JobStatus) -> None:
        self._job(job_id).job.status = JobStatus(status).name

    def assign_resource(self, project_type: ProjectType, job_id: int, resource_id: int) -> None:
        job = self._job(job_id).job
        job.resource_id = resource_id
        if job.status == JobStatus.IN_PREPERATION.name:
            job.status = JobStatus.ASSIGNED_WAITING.name

    def get_job_cost(self, project_type: ProjectType, job_id: int) -> Money:
        return Money(amount=self._job(job_id).price, currency=self.currency)

    def set_job_price(self, job_id: int, amount: float) -> None:
        """Test helper: price lines a PM enters in Plunet."""
        self._job(job_id).price = amount
