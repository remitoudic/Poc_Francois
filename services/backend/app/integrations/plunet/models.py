"""Typed results returned by the Plunet gateway. Pydantic, so they cross Temporal boundaries."""

from datetime import datetime

from pydantic import BaseModel

from app.integrations.plunet.enums import ProjectType


class PlunetCustomer(BaseModel):
    id: int
    name: str
    currency: str | None = None


class PlunetResource(BaseModel):
    id: int
    name: str
    email: str | None = None


class PlunetLanguage(BaseModel):
    id: int
    name: str  # what the Plunet API expects in language parameters, e.g. "French"
    code: str  # Plunet folderName, e.g. "fr-FR"


class ProjectDraft(BaseModel):
    """Input for an order (Auftrag) or a quote (Angebot)."""

    project_name: str
    customer_id: int
    project_manager_id: int | None = None
    deadline: datetime | None = None
    subject: str | None = None
    reference: str | None = None  # FOX MLO order id, for traceability in Plunet
    memo: str | None = None


class CreatedProject(BaseModel):
    project_type: ProjectType
    id: int
    number: str  # display number, e.g. "O-2026-0414"


class ItemDraft(BaseModel):
    """One Plunet item per FOX MLO position: 1 post × 1 target language."""

    project_type: ProjectType
    project_id: int
    description: str
    source_lang: str
    target_lang: str
    deadline: datetime | None = None
    reference: str | None = None


class PlunetJob(BaseModel):
    id: int
    item_id: int | None
    project_type: ProjectType
    job_type: str  # short name, e.g. "TRA"
    status: str  # raw Plunet JobStatus name; the UI state is derived from it
    resource_id: int | None = None
    start_date: datetime | None = None
    due_date: datetime | None = None


class Money(BaseModel):
    amount: float
    currency: str | None
