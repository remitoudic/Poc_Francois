"""Mapping between Plunet JobStatus and FOX MLO task states (architecture §6.1)."""

from app.domain.enums import TaskStatus

# BM.API.SOAP.Enum.JobStatus (spelling of IN_PREPERATION is Plunet's own).
PLUNET_JOB_STATUS = {
    0: "IN_PREPERATION",
    1: "IN_PROGRESS",
    2: "DELIVERED",
    3: "APPROVED",
    4: "CANCELED",
    5: "INVOICE_ACCEPTED",
    6: "PAYED",
    7: "ASSIGNED_WAITING",
    8: "REQUESTED",
    9: "INVOICE_CHECKED",
    10: "INVOICE_CREATED",
    11: "WITHOUT_INVOICE",
    12: "TRANSFERRED_TO_ORDER",
    13: "OVERDUE",
}

_TO_TASK_STATUS = {
    "IN_PREPERATION": TaskStatus.PENDING,
    "REQUESTED": TaskStatus.WAITING,
    "ASSIGNED_WAITING": TaskStatus.WAITING,
    "IN_PROGRESS": TaskStatus.RUNNING,
    "DELIVERED": TaskStatus.DONE,
    "APPROVED": TaskStatus.DONE,
    "INVOICE_ACCEPTED": TaskStatus.DONE,
    "PAYED": TaskStatus.DONE,
    "INVOICE_CHECKED": TaskStatus.DONE,
    "INVOICE_CREATED": TaskStatus.DONE,
    "WITHOUT_INVOICE": TaskStatus.DONE,
    "TRANSFERRED_TO_ORDER": TaskStatus.DONE,
    "CANCELED": TaskStatus.CANCELLED,
}


def plunet_status_name(value: int | str) -> str:
    """Normalise a Plunet JobStatus given as its int code or its name."""
    if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
        return PLUNET_JOB_STATUS[int(value)]
    return value


def task_status_from_plunet(value: int | str) -> TaskStatus | None:
    """FOX MLO task status for a Plunet JobStatus. OVERDUE returns None: it is a flag, not a state."""
    return _TO_TASK_STATUS.get(plunet_status_name(value))
