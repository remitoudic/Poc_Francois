"""Workflow behaviour in Temporal's time-skipping test server, with in-memory activities."""

from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from temporalio.client import WorkflowHandle, WorkflowHistory, WorkflowUpdateFailedError
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, Worker

import tests.workflow_fakes as fakes
from app.domain.enums import (
    EventLevel,
    OrderKind,
    OrderStatus,
    TaskStatus,
    TaskType,
    WorkflowStatus,
)
from app.workflows.models import (
    ActionRequest,
    JobStatusSignal,
    OrderInput,
    PositionInput,
    QuoteConverted,
    QuoteDecision,
    RestartRequest,
    SyncChanges,
    SyncJob,
    SyncJobChange,
    SyncTargets,
)
from app.workflows.order import OrderWorkflow
from app.workflows.position import PositionWorkflow
from app.workflows.sync import PlunetSyncWorkflow
from tests.workflow_fakes import AUTO, FULL, until

QUEUE, PLUNET_QUEUE = "test", "test-plunet"
WORKFLOWS = [OrderWorkflow, PositionWorkflow, PlunetSyncWorkflow]
HISTORY_DIR = Path(__file__).parent / "fixtures" / "histories"
# FOX_WRITE_HISTORIES=1 refreshes the saved histories after an intended workflow change.
WRITE_HISTORIES = os.environ.get("FOX_WRITE_HISTORIES") == "1"

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest.fixture(autouse=True)
def fresh_world():
    fakes.world = fakes.World()
    yield


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def env():
    async with await WorkflowEnvironment.start_time_skipping(data_converter=pydantic_data_converter) as env:
        yield env


@asynccontextmanager
async def workers(env):
    with ThreadPoolExecutor(max_workers=4) as pool:
        async with (
            Worker(env.client, task_queue=QUEUE, workflows=WORKFLOWS, activities=fakes.ORCHESTRATION),
            Worker(env.client, task_queue=PLUNET_QUEUE, activities=fakes.PLUNET, activity_executor=pool),
        ):
            yield


async def start_position(env, position_id: int, **kwargs) -> WorkflowHandle:
    return await env.client.start_workflow(
        PositionWorkflow.run,
        PositionInput(position_id=position_id, plunet_queue=PLUNET_QUEUE, **kwargs),
        id=f"position-{position_id}-{uuid.uuid4().hex[:6]}",
        task_queue=QUEUE,
    )


async def task_state(handle: WorkflowHandle, seq: int):
    await until(lambda: _loaded(handle))
    return (await handle.query(PositionWorkflow.state)).tasks[seq]


async def _loaded(handle: WorkflowHandle) -> bool:
    return bool((await handle.query(PositionWorkflow.state)).tasks)


async def deliver_job(handle: WorkflowHandle, seq: int, status: str = "DELIVERED") -> int:
    """Wait until task `seq` has a Plunet job, then report a status for it, as the sync would."""
    async def has_job():
        task = await task_state(handle, seq)
        return task.plunet_job_id and task.status in (TaskStatus.WAITING, TaskStatus.RUNNING)

    await until(has_job)
    job_id = (await task_state(handle, seq)).plunet_job_id
    await handle.signal(PositionWorkflow.plunet_job_status, JobStatusSignal(job_id=job_id, status=status, resource_id=21))

    if status in ("ASSIGNED_WAITING", "IN_PROGRESS"):  # one status at a time, like two sync runs
        await until(lambda: _job_status_is(handle, seq, status))
    return job_id


async def _job_status_is(handle: WorkflowHandle, seq: int, status: str) -> bool:
    return (await task_state(handle, seq)).plunet_job_status == status


async def rejected(update, match: str) -> None:
    with pytest.raises(WorkflowUpdateFailedError) as info:
        await update
    assert match in str(info.value.cause), info.value.cause


async def run_human_tasks(handle: WorkflowHandle, seqs=(1, 2, 3)) -> None:
    for seq in seqs:
        await deliver_job(handle, seq, "ASSIGNED_WAITING")
        await deliver_job(handle, seq, "IN_PROGRESS")
        await deliver_job(handle, seq, "DELIVERED")


async def test_happy_path_through_all_six_tasks(env):
    fakes.world.add_position(1, FULL)
    async with workers(env):
        handle = await start_position(env, 1)
        await run_human_tasks(handle)
        result = await handle.result()

    assert result.status == WorkflowStatus.COMPLETED
    w = fakes.world
    assert w.count("plunet_create_job") == 3 and w.count("plunet_job_outcome") == 3
    assert w.names().index("plunet_fetch_translation") < w.names().index("run_qa") < w.names().index("deliver")
    assert ("plunet_set_item_status", (1, "DELIVERED")) in w.calls
    done = [c for c in w.changes if c.task_status == TaskStatus.DONE]
    assert [c.task_id for c in done] == [10, 11, 12, 13, 14, 15]
    assert all(c.cost == 120.0 for c in done if c.task_id in (11, 12, 13))
    assert any(c.plunet_job_status == "IN_PROGRESS" and c.position_status == WorkflowStatus.RUNNING for c in w.changes)
    assert any(c.plunet_job_status == "ASSIGNED_WAITING" and c.position_status == WorkflowStatus.WAITING for c in w.changes)
    assert w.closes[-1].status == WorkflowStatus.COMPLETED
    history = await handle.fetch_history()
    await Replayer(workflows=WORKFLOWS, data_converter=pydantic_data_converter).replay_workflow(history)
    if WRITE_HISTORIES:
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        (HISTORY_DIR / "position_happy_path.json").write_text(history.to_json())


@pytest.mark.parametrize("path", sorted(HISTORY_DIR.glob("*.json")), ids=lambda p: p.stem)
async def test_saved_histories_still_replay(path):
    """A change that breaks determinism for running workflows fails here (use workflow.patched)."""
    history = WorkflowHistory.from_json(path.stem, path.read_text())
    await Replayer(workflows=WORKFLOWS, data_converter=pydantic_data_converter).replay_workflow(history)


async def test_qa_failure_then_retry_completes(env):
    fakes.world.add_position(2, AUTO)
    fakes.world.qa_failures[2] = 1
    async with workers(env):
        handle = await start_position(env, 2)
        await until(lambda: any(c.task_status == TaskStatus.FAILED for c in fakes.world.changes))
        state = await handle.query(PositionWorkflow.state)
        assert state.status == WorkflowStatus.FAILED and state.tasks[1].status == TaskStatus.FAILED
        await handle.execute_update(PositionWorkflow.retry, ActionRequest(actor="Claire"))
        result = await handle.result()

    assert result.status == WorkflowStatus.COMPLETED
    failed = next(c for c in fakes.world.changes if c.task_status == TaskStatus.FAILED)
    assert failed.findings[0].code == "PLACEHOLDER_MISMATCH" and "u-002" in failed.error
    assert fakes.world.count("run_qa") == 2
    assert any(c.task_id == 21 and c.attempts == 2 for c in fakes.world.changes)
    assert any("Retry requested by Claire" in m for m in fakes.world.messages())


async def test_pause_during_translation_holds_next_task_until_resume(env):
    fakes.world.add_position(3, FULL)
    async with workers(env):
        handle = await start_position(env, 3)
        await run_human_tasks(handle, seqs=(1,))
        await deliver_job(handle, 2, "IN_PROGRESS")
        await handle.execute_update(PositionWorkflow.pause, ActionRequest(actor="Claire"))
        assert (await handle.query(PositionWorkflow.state)).status == WorkflowStatus.PAUSED
        await deliver_job(handle, 2, "DELIVERED")  # the translator finishes in Plunet anyway
        await until(lambda: any(c.task_id == 32 and c.task_status == TaskStatus.DONE for c in fakes.world.changes))
        assert not any(c.task_id == 33 and c.started for c in fakes.world.changes)  # REV did not start

        await handle.execute_update(PositionWorkflow.resume, ActionRequest(actor="Claire"))
        await run_human_tasks(handle, seqs=(3,))
        result = await handle.result()
    assert result.status == WorkflowStatus.COMPLETED
    assert any(c.position_status == WorkflowStatus.PAUSED for c in fakes.world.changes)


async def test_restart_from_review_resets_later_tasks_and_creates_a_new_job(env):
    fakes.world.add_position(4, FULL)
    fakes.world.qa_failures[4] = 1
    async with workers(env):
        handle = await start_position(env, 4)
        await run_human_tasks(handle)
        await until(lambda: any(c.task_status == TaskStatus.FAILED for c in fakes.world.changes))
        first_rev_job = fakes.world.task_jobs[43]
        await handle.execute_update(PositionWorkflow.restart_from, RestartRequest(seq=3, actor="Claire", reason="Reviewer missed placeholders"))
        await until(lambda: fakes.world.task_jobs.get(43, first_rev_job) != first_rev_job)
        await run_human_tasks(handle, seqs=(3,))
        result = await handle.result()

    assert result.status == WorkflowStatus.COMPLETED
    assert ("reset_tasks", (4, 3)) in fakes.world.calls
    assert fakes.world.count("run_qa") == 2


async def test_new_run_from_a_task_keeps_counting_attempts(env):
    plan = fakes.world.add_position(11, AUTO)
    for spec in plan.tasks:
        spec.attempts = 1  # as stored after the first, completed run
    async with workers(env):
        result = await env.client.execute_workflow(
            PositionWorkflow.run, PositionInput(position_id=11, start_from=1, plunet_queue=PLUNET_QUEUE),
            id=f"position-11-{uuid.uuid4().hex[:6]}", task_queue=QUEUE,
        )
    assert result.status == WorkflowStatus.COMPLETED
    assert ("reset_tasks", (11, 1)) in fakes.world.calls
    assert [c.attempts for c in fakes.world.changes if c.started] == [2, 2]  # QA and DELIVER, IMPORT not re-run
    assert any("(attempt 2)" in m for m in fakes.world.messages())


async def test_restart_while_job_open_cancels_it_in_plunet_first(env):
    fakes.world.add_position(9, FULL)
    async with workers(env):
        handle = await start_position(env, 9)
        await run_human_tasks(handle, seqs=(1,))
        tra_job = await deliver_job(handle, 2, "IN_PROGRESS")
        await handle.execute_update(PositionWorkflow.restart_from, RestartRequest(seq=1, actor="Claire"))
        assert ("plunet_cancel_job", (tra_job,)) in fakes.world.calls
        await run_human_tasks(handle)
        result = await handle.result()
    assert result.status == WorkflowStatus.COMPLETED
    assert ("reset_tasks", (9, 1)) in fakes.world.calls


async def test_cancel_requires_reason_and_cancels_plunet_jobs(env):
    fakes.world.add_position(5, FULL)
    async with workers(env):
        handle = await start_position(env, 5)
        await deliver_job(handle, 1, "ASSIGNED_WAITING")
        await rejected(handle.execute_update(PositionWorkflow.cancel, ActionRequest(actor="Claire", reason="  ")), "reason is required")
        await handle.execute_update(PositionWorkflow.cancel, ActionRequest(actor="Claire", reason="Customer withdrew"))
        result = await handle.result()

    assert result.status == WorkflowStatus.CANCELLED
    assert fakes.world.count("plunet_cancel_position") == 1
    close = fakes.world.closes[-1]
    assert close.status == WorkflowStatus.CANCELLED and close.reason == "Customer withdrew" and close.actor == "Claire"


async def test_cancel_still_closes_when_plunet_cleanup_fails(env):
    fakes.world.add_position(10, FULL)
    fakes.world.cancel_fails = True
    async with workers(env):
        handle = await start_position(env, 10)
        await deliver_job(handle, 1, "ASSIGNED_WAITING")
        await handle.execute_update(PositionWorkflow.cancel, ActionRequest(actor="Claire", reason="Customer withdrew"))
        result = await handle.result()

    assert result.status == WorkflowStatus.CANCELLED
    warning = next(c for c in fakes.world.changes if c.level == EventLevel.WARN)
    assert "Plunet cleanup failed" in warning.message and "does not exist" in warning.message
    assert "check it by hand" in fakes.world.closes[-1].message


async def test_invalid_updates_are_rejected(env):
    fakes.world.add_position(6, FULL)
    async with workers(env):
        handle = await start_position(env, 6)
        await deliver_job(handle, 1, "ASSIGNED_WAITING")
        await rejected(handle.execute_update(PositionWorkflow.resume, ActionRequest()), "Not paused")
        await rejected(handle.execute_update(PositionWorkflow.retry, ActionRequest()), "has failed")
        await rejected(handle.execute_update(PositionWorkflow.restart_from, RestartRequest(seq=4)), "current task or an earlier")
        await rejected(handle.execute_update(PositionWorkflow.restart_from, RestartRequest(seq=9)), "No task 9")
        await handle.execute_update(PositionWorkflow.cancel, ActionRequest(reason="cleanup"))
        await handle.result()


async def test_job_cancelled_in_plunet_fails_the_task_and_retry_creates_a_new_job(env):
    fakes.world.add_position(7, [TaskType.IMPORT, TaskType.TRA, TaskType.DELIVER])
    async with workers(env):
        handle = await start_position(env, 7)
        first = await deliver_job(handle, 1, "CANCELED")
        await until(lambda: any(c.task_status == TaskStatus.FAILED for c in fakes.world.changes))
        await handle.execute_update(PositionWorkflow.retry, ActionRequest(actor="Claire"))
        await until(lambda: fakes.world.task_jobs.get(71, first) != first)
        await deliver_job(handle, 1, "DELIVERED")
        result = await handle.result()
    assert result.status == WorkflowStatus.COMPLETED
    assert ("plunet_create_job", (71, True)) in fakes.world.calls


async def test_overdue_job_emits_one_warning():
    # Own environment: skipping hours of time in the shared one would also move its other workflows.
    async with await WorkflowEnvironment.start_time_skipping(data_converter=pydantic_data_converter) as env:
        now = (await env.get_current_time()).replace(tzinfo=None)
        fakes.world.add_position(8, [TaskType.IMPORT, TaskType.TRA, TaskType.DELIVER], deadline=now + timedelta(hours=2))
        async with workers(env):
            handle = await start_position(env, 8)
            await deliver_job(handle, 1, "ASSIGNED_WAITING")
            await env.sleep(timedelta(hours=3))
            await until(lambda: any(c.level == EventLevel.WARN for c in fakes.world.changes))
            await deliver_job(handle, 1, "DELIVERED")
            assert (await handle.result()).status == WorkflowStatus.COMPLETED
    warnings = [c for c in fakes.world.changes if c.level == EventLevel.WARN]
    assert len(warnings) == 1 and "overdue" in warnings[0].message


async def test_quote_waits_and_double_acceptance_starts_positions_once(env):
    fakes.world.add_order(20, OrderKind.QUOTE, [201, 202])
    fakes.world.add_position(201, AUTO, order_id=20)
    fakes.world.add_position(202, AUTO, order_id=20)
    async with workers(env):
        handle = await env.client.start_workflow(
            OrderWorkflow.run, OrderInput(order_id=20, plunet_queue=PLUNET_QUEUE), id=f"order-20-{uuid.uuid4().hex[:6]}", task_queue=QUEUE,
        )
        await until(lambda: any(c.status == OrderStatus.AWAITING_ACCEPTANCE for c in fakes.world.order_changes))
        assert fakes.world.count("plunet_create_item") == 2 and fakes.world.count("plunet_upload_source") == 2
        assert ("plunet_set_quote_status", (20, "PENDING")) in fakes.world.calls
        assert fakes.world.count("set_position_workflow") == 0  # nothing runs on a quote

        await handle.signal(OrderWorkflow.quote_accepted, QuoteDecision(actor="Claire"))
        await handle.signal(OrderWorkflow.quote_accepted, QuoteDecision(actor="plunet", in_plunet=True))
        await until(lambda: any(c.status == OrderStatus.ACCEPTED for c in fakes.world.order_changes))
        assert ("plunet_set_quote_status", (20, "ACCEPTED")) in fakes.world.calls
        await handle.signal(OrderWorkflow.quote_converted, QuoteConverted(plunet_order_id=777))
        await handle.signal(OrderWorkflow.quote_converted, QuoteConverted(plunet_order_id=778))
        result = await handle.result()

    w = fakes.world
    assert result == OrderStatus.COMPLETED
    assert w.count("plunet_set_quote_status") == 2  # PENDING, then ACCEPTED once
    assert w.calls.count(("plunet_adopt_order", (20, 777))) == 1
    assert w.count("set_position_workflow") == 2
    assert sum(c.status == WorkflowStatus.COMPLETED for c in w.closes) == 2


async def test_quote_rejected_in_plunet_runs_nothing(env):
    fakes.world.add_order(21, OrderKind.QUOTE, [211])
    fakes.world.add_position(211, AUTO, order_id=21)
    async with workers(env):
        handle = await env.client.start_workflow(
            OrderWorkflow.run, OrderInput(order_id=21, plunet_queue=PLUNET_QUEUE), id=f"order-21-{uuid.uuid4().hex[:6]}", task_queue=QUEUE,
        )
        await until(lambda: any(c.status == OrderStatus.AWAITING_ACCEPTANCE for c in fakes.world.order_changes))
        await handle.signal(OrderWorkflow.quote_rejected, QuoteDecision(actor="plunet", in_plunet=True))
        assert await handle.result() == OrderStatus.REJECTED
    assert ("plunet_set_quote_status", (21, "REJECTED")) not in fakes.world.calls  # already true in Plunet
    assert fakes.world.count("set_position_workflow") == 0


async def test_accepted_quote_withdrawn_in_fox_mlo_is_rejected_in_plunet(env):
    fakes.world.add_order(23, OrderKind.QUOTE, [231])
    fakes.world.add_position(231, AUTO, order_id=23)
    async with workers(env):
        handle = await env.client.start_workflow(
            OrderWorkflow.run, OrderInput(order_id=23, plunet_queue=PLUNET_QUEUE), id=f"order-23-{uuid.uuid4().hex[:6]}", task_queue=QUEUE,
        )
        await until(lambda: any(c.status == OrderStatus.AWAITING_ACCEPTANCE for c in fakes.world.order_changes))
        await handle.signal(OrderWorkflow.quote_accepted, QuoteDecision(actor="Claire"))
        await until(lambda: any(c.status == OrderStatus.ACCEPTED for c in fakes.world.order_changes))
        await handle.signal(OrderWorkflow.quote_rejected, QuoteDecision(actor="Claire", reason="Budget cut"))
        assert await handle.result() == OrderStatus.REJECTED
    assert ("plunet_set_quote_status", (23, "REJECTED")) in fakes.world.calls
    last = fakes.world.order_changes[-1]
    assert last.status == OrderStatus.REJECTED and last.message == "Quote withdrawn before conversion" and last.reason == "Budget cut"


async def test_rejection_stands_when_plunet_refuses_the_status(env):
    fakes.world.add_order(24, OrderKind.QUOTE, [241])
    fakes.world.add_position(241, AUTO, order_id=24)
    fakes.world.refused_quote_status = {"REJECTED"}
    async with workers(env):
        handle = await env.client.start_workflow(
            OrderWorkflow.run, OrderInput(order_id=24, plunet_queue=PLUNET_QUEUE), id=f"order-24-{uuid.uuid4().hex[:6]}", task_queue=QUEUE,
        )
        await until(lambda: any(c.status == OrderStatus.AWAITING_ACCEPTANCE for c in fakes.world.order_changes))
        await handle.signal(OrderWorkflow.quote_rejected, QuoteDecision(actor="Claire"))
        assert await handle.result() == OrderStatus.REJECTED
    warning = next(c for c in fakes.world.order_changes if c.level == EventLevel.WARN)
    assert "not set to REJECTED" in warning.message and "not allowed" in warning.message


async def test_order_runs_positions_directly(env):
    fakes.world.add_order(22, OrderKind.ORDER, [221])
    fakes.world.add_position(221, AUTO, order_id=22)
    async with workers(env):
        result = await env.client.execute_workflow(
            OrderWorkflow.run, OrderInput(order_id=22, plunet_queue=PLUNET_QUEUE), id=f"order-22-{uuid.uuid4().hex[:6]}", task_queue=QUEUE,
        )
    assert result == OrderStatus.COMPLETED
    assert fakes.world.order_changes[0].status == OrderStatus.RUNNING


async def test_sync_signals_the_position_workflow(env):
    fakes.world.add_position(30, [TaskType.IMPORT, TaskType.TRA, TaskType.DELIVER])
    async with workers(env):
        handle = await env.client.start_workflow(
            PositionWorkflow.run, PositionInput(position_id=30, plunet_queue=PLUNET_QUEUE), id="position-30", task_queue=QUEUE,
        )
        await until(lambda: 301 in fakes.world.task_jobs)
        job_id = fakes.world.task_jobs[301]
        fakes.world.sync_targets = SyncTargets(jobs=[SyncJob(position_id=30, job_id=job_id, project_type=3, known_status="IN_PREPERATION")])
        fakes.world.sync_changes = SyncChanges(jobs=[SyncJobChange(position_id=30, signal=JobStatusSignal(job_id=job_id, status="DELIVERED", resource_id=21))])
        summary = await env.client.execute_workflow(PlunetSyncWorkflow.run, PLUNET_QUEUE, id=f"sync-{uuid.uuid4().hex[:6]}", task_queue=QUEUE)
        assert summary == {"jobs": 1, "quotes": 0, "signalled": 1}
        result = await handle.result()
    assert result.status == WorkflowStatus.COMPLETED


async def test_sync_ignores_workflows_that_are_gone(env):
    fakes.world.sync_targets = SyncTargets(jobs=[SyncJob(position_id=99, job_id=1, project_type=3, known_status=None)])
    fakes.world.sync_changes = SyncChanges(jobs=[SyncJobChange(position_id=99, signal=JobStatusSignal(job_id=1, status="DELIVERED"))])
    async with workers(env):
        summary = await env.client.execute_workflow(PlunetSyncWorkflow.run, PLUNET_QUEUE, id=f"sync-{uuid.uuid4().hex[:6]}", task_queue=QUEUE)
    assert summary["signalled"] == 0

