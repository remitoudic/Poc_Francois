"""Domain vocabulary shared by the API, the Temporal workflows and the database."""

from enum import StrEnum


class OrderKind(StrEnum):
    ORDER = "ORDER"  # Plunet Auftrag
    QUOTE = "QUOTE"  # Plunet Angebot


class OrderStatus(StrEnum):
    DRAFT = "DRAFT"
    AWAITING_ACCEPTANCE = "AWAITING_ACCEPTANCE"  # quote sent, no workflow runs
    ACCEPTED = "ACCEPTED"  # quote accepted; waits for the PM to convert it in Plunet
    REJECTED = "REJECTED"
    RUNNING = "RUNNING"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"  # at least one position failed or paused
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class WorkflowStatus(StrEnum):
    """Status of one position's workflow."""

    NOT_STARTED = "NOT_STARTED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"  # current task waits on a person in Plunet
    PAUSED = "PAUSED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class TaskType(StrEnum):
    IMPORT = "IMPORT"  # orchestrator: fetch .xliff from Polylang
    PM = "PM"  # Plunet job
    TRA = "TRA"  # Plunet job: translation
    REV = "REV"  # Plunet job: review
    QA = "QA"  # orchestrator: automatic checks
    DELIVER = "DELIVER"  # orchestrator: return trip

    @property
    def is_plunet_job(self) -> bool:
        return self in (TaskType.PM, TaskType.TRA, TaskType.REV)


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    WAITING = "WAITING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


class Overlay(StrEnum):
    """Orchestrator-only conditions shown next to the Plunet state (never written to Plunet)."""

    FAILED = "FAILED"
    PAUSED = "PAUSED"


class Destination(StrEnum):
    POLYLANG = "POLYLANG"
    ENDPOINT = "ENDPOINT"
    NONE = "NONE"


class EventKind(StrEnum):
    LOG = "LOG"
    STATE = "STATE"
    ACTION = "ACTION"


class EventLevel(StrEnum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
