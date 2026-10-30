"""Plunet SOAP enums used by the gateway (values from apidoc.plunet.com, BM.API.SOAP.Enum)."""

from enum import IntEnum


class ProjectType(IntEnum):
    QUOTE = 1
    ORDER = 3


class QuoteStatus(IntEnum):
    PENDING = 1
    REVISED = 2
    REJECTED = 3
    CHANGE_INTO_ORDER = 4
    CANCELED = 5
    EXPIRED = 6
    ACCEPTED = 7
    NEW = 8
    IN_PREPARATION = 9
    CHECK_CLEARANCE = 11


class ItemStatus(IntEnum):
    IN_PROGRESS = 1
    DELIVERED = 2
    APPROVED = 3
    INVOICED = 4
    CANCELED = 5
    NEW_AUTO = 6
    DELIVERABLE = 7
    IN_PREPERATION = 8  # Plunet's spelling
    PAID = 9
    WITHOUT_INVOICE = 10
    PENDING = 11
    ACCEPTED = 12
    REJECTED = 13


class JobStatus(IntEnum):
    IN_PREPERATION = 0  # Plunet's spelling
    IN_PROGRESS = 1
    DELIVERED = 2
    APPROVED = 3
    CANCELED = 4
    INVOICE_ACCEPTED = 5
    PAYED = 6  # Plunet's spelling
    ASSIGNED_WAITING = 7
    REQUESTED = 8
    INVOICE_CHECKED = 9
    INVOICE_CREATED = 10
    WITHOUT_INVOICE = 11
    TRANSFERRED_TO_ORDER = 12
    OVERDUE = 13


class FolderType(IntEnum):
    QUOTE_ITEM_SOURCE = 14
    ORDER_ITEM_SOURCE = 16
    QUOTE_JOB_OUT = 21
    ORDER_JOB_OUT = 23


class CurrencyType(IntEnum):
    PROJECT = 1
    HOME = 2


class WorkingStatus(IntEnum):
    INTERNAL = 1
    EXTERNAL = 2


class ResourceStatus(IntEnum):
    ACTIVE = 1


class CustomerStatus(IntEnum):
    ACTIVE = 1


class EventType(IntEnum):
    """Callback event types for `registerCallback_Notify`."""

    STATUS_CHANGED = 1
    NEW_ENTRY_CREATED = 2
    ENTRY_DELETED = 3
    START_DATE_CHANGED = 4
    DELIVERY_DATE_CHANGED = 5


def item_source_folder(project_type: ProjectType) -> FolderType:
    return FolderType.QUOTE_ITEM_SOURCE if project_type == ProjectType.QUOTE else FolderType.ORDER_ITEM_SOURCE
