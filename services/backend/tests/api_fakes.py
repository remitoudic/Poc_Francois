"""Test harness for the v2 API: a migrated Postgres test database and a fake Temporal client."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import psycopg
import pytest
from sqlalchemy.engine import make_url
from temporalio.client import WorkflowUpdateFailedError
from temporalio.exceptions import ApplicationError, WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from tests.conftest import TEST_DATABASE_URL

V2_TABLES = "events, xliff_segments, tasks, positions, orders, customers, resources"


def _conninfo(url: str, database: str | None = None) -> str:
    u = make_url(url)
    return f"host={u.host} port={u.port or 5432} user={u.username} password={u.password} dbname={database or u.database}"


def prepare_database() -> None:
    """Create the test database if needed and migrate it to head. Skips when Postgres is down."""
    name = make_url(TEST_DATABASE_URL).database
    try:
        with psycopg.connect(_conninfo(TEST_DATABASE_URL, "postgres"), autocommit=True, connect_timeout=3) as conn:
            if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone():
                conn.execute(f'CREATE DATABASE "{name}"')
    except psycopg.OperationalError as err:
        pytest.skip(f"Postgres test database not reachable ({err.__class__.__name__}); set TEST_DATABASE_URL")
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config("alembic.ini"), "head")


def truncate() -> None:
    with psycopg.connect(_conninfo(TEST_DATABASE_URL), autocommit=True) as conn:
        conn.execute(f"TRUNCATE {V2_TABLES} RESTART IDENTITY CASCADE")


@dataclass
class FakeHandle:
    temporal: FakeTemporal
    workflow_id: str

    async def signal(self, signal, arg) -> None:
        self.temporal.check(self.workflow_id)
        self.temporal.signals.append((self.workflow_id, signal.__name__, arg))

    async def execute_update(self, update, arg) -> Any:
        self.temporal.check(self.workflow_id)
        rejection = self.temporal.reject.get((self.workflow_id, update.__name__))
        if rejection:
            raise WorkflowUpdateFailedError(ApplicationError(rejection))
        self.temporal.updates.append((self.workflow_id, update.__name__, arg))
        return None


@dataclass
class FakeTemporal:
    """Records starts, signals and updates. `missing` ids answer NOT_FOUND like a closed workflow."""

    started: list[tuple[str, str, Any]] = field(default_factory=list)
    signals: list[tuple[str, str, Any]] = field(default_factory=list)
    updates: list[tuple[str, str, Any]] = field(default_factory=list)
    reject: dict[tuple[str, str], str] = field(default_factory=dict)
    missing: set[str] = field(default_factory=set)
    running: set[str] = field(default_factory=set)
    down: bool = False

    def check(self, workflow_id: str) -> None:
        if self.down:
            raise RPCError("connection refused", RPCStatusCode.UNAVAILABLE, b"")
        if workflow_id in self.missing:
            raise RPCError("workflow execution already completed", RPCStatusCode.NOT_FOUND, b"")

    async def start_workflow(self, workflow, arg, *, id: str, task_queue: str) -> FakeHandle:
        if self.down:
            raise RPCError("connection refused", RPCStatusCode.UNAVAILABLE, b"")
        if id in self.running:
            raise WorkflowAlreadyStartedError(id, workflow.__qualname__.split(".")[0])
        self.running.add(id)
        self.missing.discard(id)
        self.started.append((id, workflow.__qualname__, arg))
        return FakeHandle(self, id)

    def get_workflow_handle(self, workflow_id: str) -> FakeHandle:
        return FakeHandle(self, workflow_id)
