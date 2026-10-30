"""Plunet BusinessManager gateway (architecture §6).

`PlunetGateway` is the interface activities depend on. `SoapPlunetGateway` implements it over the
SOAP API (zeep); `FakePlunetGateway` (fake.py) is an in-memory stand-in for tests and local runs.

Every SOAP call is made with keyword arguments named exactly as in the WSDL. The tests replay
each call against the recorded WSDLs in tests/fixtures/plunet_wsdl, so a wrong name or type fails
there instead of on the live portal.
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from app.integrations.errors import BusinessError, TechnicalError
from app.integrations.plunet.enums import (
    CurrencyType,
    CustomerStatus,
    ItemStatus,
    JobStatus,
    ProjectType,
    QuoteStatus,
    ResourceStatus,
    WorkingStatus,
    item_source_folder,
)
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

logger = logging.getLogger(__name__)


class PlunetError(Exception):
    """Mixin marking errors that come from Plunet."""


class PlunetTechnicalError(PlunetError, TechnicalError):
    """Network failure, timeout or SOAP fault. Retried by Temporal."""


class PlunetBusinessError(PlunetError, BusinessError):
    """Plunet answered with a non-zero statusCode: it refused the request."""

    def __init__(self, operation: str, status_code: int | None, message: str):
        super().__init__(f"Plunet {operation} failed ({status_code}): {message}")
        self.operation = operation
        self.status_code = status_code
        self.status_message = message


class PlunetAuthError(PlunetBusinessError):
    """Login refused: wrong credentials or the API user lacks rights."""


# Plunet reports an expired or unknown session in statusMessage; the wording varies by version.
_SESSION_ERROR = re.compile(r"uuid|session|not logged|login", re.I)


class PlunetGateway(Protocol):
    def version(self) -> str: ...
    def list_customers(self) -> list[PlunetCustomer]: ...
    def list_project_managers(self) -> list[PlunetResource]: ...
    def list_languages(self) -> list[PlunetLanguage]: ...
    def create_order(self, draft: ProjectDraft) -> CreatedProject: ...
    def create_quote(self, draft: ProjectDraft) -> CreatedProject: ...
    def get_quote_status(self, quote_id: int) -> QuoteStatus: ...
    def set_quote_status(self, quote_id: int, status: QuoteStatus) -> None: ...
    def get_order_id_for_quote(self, quote_id: int) -> int | None: ...
    def delete_order(self, order_id: int) -> None: ...
    def delete_quote(self, quote_id: int) -> None: ...
    def create_item(self, draft: ItemDraft) -> int: ...
    def set_item_status(self, project_type: ProjectType, item_id: int, status: ItemStatus) -> None: ...
    def upload_document(self, project_type: ProjectType, item_id: int, file_name: str, content: bytes) -> None: ...
    def create_job(self, project_type: ProjectType, project_id: int, item_id: int, job_type: str) -> int: ...
    def get_job(self, project_type: ProjectType, job_id: int) -> PlunetJob: ...
    def list_item_jobs(self, project_type: ProjectType, item_id: int) -> list[PlunetJob]: ...
    def set_job_status(self, project_type: ProjectType, job_id: int, status: JobStatus) -> None: ...
    def assign_resource(self, project_type: ProjectType, job_id: int, resource_id: int) -> None: ...
    def get_job_cost(self, project_type: ProjectType, job_id: int) -> Money: ...


ServiceFactory = Callable[[str], Any]
"""Returns the zeep service proxy for a Plunet endpoint name, e.g. "DataJob30"."""


def zeep_service_factory(base_url: str, timeout: float = 30.0) -> ServiceFactory:
    """Lazily build and cache one zeep client per Plunet endpoint."""
    from zeep import Client, Settings
    from zeep.transports import Transport

    base = base_url.rstrip("/") + "/"
    clients: dict[str, Any] = {}
    lock = threading.Lock()

    def factory(name: str) -> Any:
        with lock:
            if name not in clients:
                try:
                    clients[name] = Client(
                        f"{base}{name}?wsdl",
                        transport=Transport(timeout=timeout, operation_timeout=timeout),
                        settings=Settings(strict=False),
                    )
                except Exception as exc:
                    raise PlunetTechnicalError(f"Cannot load Plunet WSDL {name}: {exc}") from exc
            return clients[name].service

    return factory


def resolve_language(code: str, languages: list[PlunetLanguage]) -> PlunetLanguage | None:
    """Plunet language for a locale or language code ("fr", "fr_FR", "de-at").

    Exact locale first; otherwise the generic language of the same base ("de-at" -> "German"
    when Plunet has no German (Austria)), preferring names without a region in parentheses.
    """
    wanted = code.replace("_", "-").lower()
    by_code = {lang.code.lower(): lang for lang in languages}
    if wanted in by_code:
        return by_code[wanted]
    base = wanted.split("-")[0]
    candidates = [lang for lang in languages if lang.code.lower().split("-")[0] == base]
    candidates.sort(key=lambda lang: ("(" in lang.name, lang.code.lower() != base, lang.name))
    return candidates[0] if candidates else None


def _int_or_none(value: Any) -> int | None:
    return int(value) if value not in (None, 0, -1) else None


class SoapPlunetGateway:
    """PlunetGateway over SOAP. Thread-safe; one session shared and renewed on expiry."""

    def __init__(self, services: ServiceFactory, username: str, password: str):
        self._services = services
        self._username = username
        self._password = password
        self._uuid: str | None = None
        self._login_lock = threading.Lock()
        self._languages: list[PlunetLanguage] | None = None

    # --- Session --------------------------------------------------------------------------

    def _login(self) -> str:
        with self._login_lock:
            if self._uuid:
                return self._uuid
            if not self._username or not self._password:
                raise PlunetAuthError("login", None, "PLUNET_USERNAME and PLUNET_PASSWORD are not set")
            token = self._raw("PlunetAPI", "login", arg0=self._username, arg1=self._password)
            if not token or token == "refused":
                raise PlunetAuthError("login", None, f"login refused for user '{self._username}'")
            self._uuid = str(token)
            return self._uuid

    def _invalidate(self, uuid: str) -> None:
        with self._login_lock:
            if self._uuid == uuid:
                self._uuid = None

    def close(self) -> None:
        """Log out. Safe to call more than once."""
        uuid, self._uuid = self._uuid, None
        if uuid:
            try:
                self._raw("PlunetAPI", "logout", arg0=uuid)
            except Exception:  # best effort
                logger.debug("Plunet logout failed", exc_info=True)

    # --- Calls ----------------------------------------------------------------------------

    def _raw(self, service: str, operation: str, **kwargs: Any) -> Any:
        """One SOAP call; maps transport problems to PlunetTechnicalError."""
        try:
            return getattr(self._services(service), operation)(**kwargs)
        except PlunetError:
            raise
        except Exception as exc:  # zeep Fault, TransportError, requests errors, timeouts
            raise PlunetTechnicalError(f"Plunet {service}.{operation}: {exc}") from exc

    def _call(self, service: str, operation: str, **kwargs: Any) -> Any:
        """Authenticated call returning `data`. Logs in again once if the session expired."""
        for attempt in (1, 2):
            uuid = self._login()
            result = self._raw(service, operation, UUID=uuid, **kwargs)
            status = getattr(result, "statusCode", 0)
            if status == 0:
                return getattr(result, "data", None)
            message = str(getattr(result, "statusMessage", "") or "")
            if attempt == 1 and _SESSION_ERROR.search(message):
                logger.info("Plunet session expired; logging in again")
                self._invalidate(uuid)
                continue
            raise PlunetBusinessError(f"{service}.{operation}", status, message)
        raise AssertionError("unreachable")

    # --- Reference data -------------------------------------------------------------------

    def version(self) -> str:
        result = self._raw("PlunetAPI", "getPlunetVersion")
        return str(getattr(result, "data", result))

    def list_customers(self) -> list[PlunetCustomer]:
        rows = self._call("DataCustomer30", "getAllCustomerObjects", Status=CustomerStatus.ACTIVE) or []
        return sorted(
            (
                PlunetCustomer(
                    id=c.customerID,
                    name=c.fullName or " ".join(filter(None, [c.name1, c.name2])) or f"#{c.customerID}",
                    currency=c.currency or None,
                )
                for c in rows
            ),
            key=lambda c: c.name.lower(),
        )

    def list_project_managers(self) -> list[PlunetResource]:
        """Active internal resources: the people who can be PM of an order."""
        rows = self._call(
            "DataResource30",
            "getAllResourceObjects",
            WorkingStatus=WorkingStatus.INTERNAL,
            Status=ResourceStatus.ACTIVE,
        ) or []
        return sorted(
            (
                PlunetResource(
                    id=r.resourceID,
                    name=r.fullName or " ".join(filter(None, [r.name2, r.name1])) or f"#{r.resourceID}",
                    email=r.email or None,
                )
                for r in rows
            ),
            key=lambda r: r.name.lower(),
        )

    def list_languages(self) -> list[PlunetLanguage]:
        """Active languages configured in Plunet (cached for the life of the gateway)."""
        if self._languages is None:
            rows = self._call("DataAdmin30", "getAvailableLanguages", languageCode="EN") or []
            self._languages = [
                PlunetLanguage(id=r.id, name=r.name, code=r.folderName)
                for r in rows
                if r.active and r.name and r.folderName
            ]
        return self._languages

    def _language_name(self, code: str) -> str:
        language = resolve_language(code, self.list_languages())
        if language is None:
            raise PlunetBusinessError("language", None, f"no Plunet language matches '{code}'")
        return language.name

    # --- Orders and quotes ----------------------------------------------------------------

    def create_order(self, draft: ProjectDraft) -> CreatedProject:
        order_in = {
            "orderID": 0,
            "customerID": draft.customer_id,
            "customerContactID": 0,
            "projectManagerID": draft.project_manager_id or 0,
            "projectName": draft.project_name,
            "subject": draft.subject or draft.project_name,
            "referenceNumber": draft.reference,
            "projectManagerMemo": draft.memo,
            "orderDate": datetime.now(UTC),
            "deliveryDeadline": draft.deadline,
            "rate": 1.0,
        }
        order_id = int(self._call("DataOrder30", "insert2", OrderIN=order_in))
        number = self._call("DataOrder30", "getOrderNo_for_View", orderID=order_id)
        return CreatedProject(project_type=ProjectType.ORDER, id=order_id, number=str(number or order_id))

    def create_quote(self, draft: ProjectDraft) -> CreatedProject:
        """Create the quote IN_PREPARATION and set its PM.

        Plunet accepts a PM and new items only while a quote is NEW / IN_PREPARATION, so the
        caller adds the items and documents first, then releases the quote with
        `set_quote_status(quote_id, QuoteStatus.PENDING)` (awaiting the customer).
        If setting the PM fails, the quote is deleted so no half-made quote stays in Plunet.
        """
        quote_in = {
            "quoteID": 0,
            "customerID": draft.customer_id,
            "projectName": draft.project_name,
            "subject": draft.subject or draft.project_name,
            "referenceNumber": draft.reference,
            "projectManagerMemo": draft.memo,
            "creationDate": datetime.now(UTC),
            "status": QuoteStatus.IN_PREPARATION,
        }
        quote_id = int(self._call("DataQuote30", "insert2", QuoteIN=quote_in))
        try:
            if draft.project_manager_id:  # QuoteIN has no PM field
                self._call("DataQuote30", "setProjectmanagerID", resourceID=draft.project_manager_id, quoteID=quote_id)
            number = self._call("DataQuote30", "getQuoteNo_for_View", quoteID=quote_id)
        except Exception:
            try:
                self.delete_quote(quote_id)
            except Exception:
                logger.exception("Could not delete half-created Plunet quote %s", quote_id)
            raise
        return CreatedProject(project_type=ProjectType.QUOTE, id=quote_id, number=str(number or quote_id))

    def get_quote_status(self, quote_id: int) -> QuoteStatus:
        return QuoteStatus(int(self._call("DataQuote30", "getStatus", quoteID=quote_id)))

    def set_quote_status(self, quote_id: int, status: QuoteStatus) -> None:
        self._call("DataQuote30", "setStatus", Status=status, quoteID=quote_id)

    def get_order_id_for_quote(self, quote_id: int) -> int | None:
        """Order created from this quote, or None while it has not been converted.

        The SOAP API has no call that converts a quote into an order; conversion happens in
        Plunet. FOX MLO detects it through the quote's `orderID` list (phase 4 polls it after
        acceptance). `getOrderIDFirstItem` is not used: it fails with -100 on unconverted quotes.
        """
        quote = self._call("DataQuote30", "getQuoteObject", quoteID=quote_id)
        order_ids = [i for i in (getattr(quote, "orderID", None) or []) if _int_or_none(i)]
        return int(order_ids[0]) if order_ids else None

    def delete_order(self, order_id: int) -> None:
        """Remove an order with its items and jobs (rollback of a creation that failed halfway)."""
        self._call("DataOrder30", "delete", orderID=order_id)

    def delete_quote(self, quote_id: int) -> None:
        self._call("DataQuote30", "delete", quoteID=quote_id)

    # --- Items and documents --------------------------------------------------------------

    def create_item(self, draft: ItemDraft) -> int:
        # Resolve first, so an unknown language fails before anything is written to Plunet.
        source_lang = self._language_name(draft.source_lang)
        target_lang = self._language_name(draft.target_lang)
        item_in = {
            "itemID": 0,
            "projectID": draft.project_id,
            "projectType": draft.project_type,
            "briefDescription": draft.description,
            "reference": draft.reference,
            "deliveryDeadline": draft.deadline,
            "status": ItemStatus.IN_PREPERATION,
            "taxType": 0,
            "totalPrice": 0.0,
        }
        item_id = int(self._call("DataItem30", "insert2", ItemIN=item_in))
        self._call(
            "DataItem30",
            "addLanguageCombination",
            sourceLanguage=source_lang,
            targetLanguage=target_lang,
            projectType=draft.project_type,
            projectID=draft.project_id,
            itemID=item_id,
        )
        return item_id

    def set_item_status(self, project_type: ProjectType, item_id: int, status: ItemStatus) -> None:
        self._call("DataItem30", "setStatus", status=status, projectType=project_type, itemID=item_id)

    def upload_document(self, project_type: ProjectType, item_id: int, file_name: str, content: bytes) -> None:
        """Attach a file to the item's source folder (where Plunet jobs pick it up)."""
        self._call(
            "DataDocument30",
            "upload_Document",
            MainID=item_id,
            FolderType=item_source_folder(project_type),
            FileByteStream=content,
            FilePathName=f"\\{file_name}",
            FileSize=len(content),
        )

    # --- Jobs -----------------------------------------------------------------------------

    def create_job(self, project_type: ProjectType, project_id: int, item_id: int, job_type: str) -> int:
        return int(
            self._call(
                "DataJob30",
                "insert2",
                projectID=project_id,
                projectType=project_type,
                jobTypeAbbrevation=job_type,  # Plunet's spelling
                itemID=item_id,
            )
        )

    @staticmethod
    def _job(raw: Any, project_type: ProjectType) -> PlunetJob:
        return PlunetJob(
            id=raw.jobID,
            item_id=_int_or_none(raw.itemID),
            project_type=project_type,
            job_type=raw.jobTypeShort or raw.jobTypeFull or "",
            status=JobStatus(int(raw.status)).name,
            resource_id=_int_or_none(raw.resourceID),
            start_date=raw.startDate,
            due_date=raw.dueDate,
        )

    def get_job(self, project_type: ProjectType, job_id: int) -> PlunetJob:
        raw = self._call("DataJob30", "getJob_ForView", jobID=job_id, projectType=project_type)
        return self._job(raw, project_type)

    def list_item_jobs(self, project_type: ProjectType, item_id: int) -> list[PlunetJob]:
        rows = self._call("DataJob30", "getJobListOfItem_ForView", itemID=item_id, projectType=project_type)
        return [self._job(r, project_type) for r in rows or []]

    def set_job_status(self, project_type: ProjectType, job_id: int, status: JobStatus) -> None:
        self._call("DataJob30", "setJobStatus", projectType=project_type, jobID=job_id, status=status)

    def assign_resource(self, project_type: ProjectType, job_id: int, resource_id: int) -> None:
        self._call("DataJob30", "setResourceID", projectType=project_type, resourceID=resource_id, jobID=job_id)

    def get_job_cost(self, project_type: ProjectType, job_id: int) -> Money:
        """Sum of the job's price lines, in the project currency (architecture §6.3)."""
        lines = self._call(
            "DataJob30",
            "getPriceLine_ListByCurrencyType",
            jobID=job_id,
            projectType=project_type,
            currencyType=CurrencyType.PROJECT,
        ) or []
        currency = self._call("DataJob30", "getCurrency", jobID=job_id, projectType=project_type)
        return Money(amount=round(sum(float(line.amount or 0) for line in lines), 2), currency=currency or None)
