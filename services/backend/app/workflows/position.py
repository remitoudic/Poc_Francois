"""PositionWorkflow: runs one position's task chain (architecture §5.2–5.4).

Controls are Workflow Updates with validators, so the UI gets an immediate yes/no:
pause, resume, retry, restart_from, cancel. Plunet job states arrive as `plunet_job_status`
signals from PlunetSyncWorkflow (every 2 minutes; no callbacks).
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.exceptions import ActivityError, ApplicationError

with workflow.unsafe.imports_passed_through():
    from app.activities import content, plunet, projection
    from app.activities.common import RETRY
    from app.domain.enums import EventKind, EventLevel, TaskStatus, TaskType, WorkflowStatus
    from app.domain.plunet_status import task_status_from_plunet
    from app.workflows.models import (
        ActionRequest,
        JobRequest,
        JobStatusSignal,
        PositionClose,
        PositionInput,
        PositionPlan,
        PositionResult,
        PositionState,
        RestartRequest,
        TaskChange,
        TaskSpec,
        TaskState,
    )

FAST = timedelta(seconds=30)
SLOW = timedelta(minutes=5)  # Polylang/Plunet calls with files
MAX_ERROR = 500


def _error_message(err: BaseException) -> str:
    cause = err.cause if isinstance(err, ActivityError) and err.cause else err
    message = cause.message if isinstance(cause, ApplicationError) else str(cause)
    return message[:MAX_ERROR]


class _Task:
    def __init__(self, spec: TaskSpec):
        self.spec = spec
        self.status = TaskStatus.PENDING
        self.attempts = 0
        self.job_id: int | None = None
        self.job_status: str | None = None
        self.error: str | None = None

    def reset(self) -> None:
        self.status, self.job_id, self.job_status, self.error = TaskStatus.PENDING, None, None, None


@workflow.defn
class PositionWorkflow:
    def __init__(self) -> None:
        self.plan: PositionPlan | None = None
        self.tasks: list[_Task] = []
        self.cursor = 0
        self.paused = False
        self.cancel_reason: str | None = None
        self.cancel_actor = "system"
        self.retry_requested = False
        self.restart_to: int | None = None
        self.finished: WorkflowStatus | None = None
        self.job_signals: dict[int, JobStatusSignal] = {}
        self.signal_version = 0
        self.plunet_queue = ""

    # --- helpers --------------------------------------------------------------------------

    @property
    def current(self) -> _Task | None:
        return self.tasks[self.cursor] if self.cursor < len(self.tasks) else None

    def _status(self) -> WorkflowStatus:
        if self.finished:
            return self.finished
        if self.paused:
            return WorkflowStatus.PAUSED
        task = self.current
        if task is None:
            return WorkflowStatus.RUNNING
        if task.status == TaskStatus.FAILED:
            return WorkflowStatus.FAILED
        if task.status == TaskStatus.WAITING:
            return WorkflowStatus.WAITING
        return WorkflowStatus.RUNNING

    async def _act(self, fn, *args, timeout: timedelta = FAST):
        return await workflow.execute_activity(
            fn, args=list(args), start_to_close_timeout=timeout, retry_policy=RETRY
        )

    async def _plunet(self, fn, *args, timeout: timedelta = SLOW):
        return await workflow.execute_activity(
            fn, args=list(args), task_queue=self.plunet_queue, start_to_close_timeout=timeout, retry_policy=RETRY
        )

    async def _record(self, task: _Task | None, **change) -> None:
        change.setdefault("position_status", self._status())
        await self._act(
            projection.record_task,
            TaskChange(position_id=self.plan.position_id, task_id=task.spec.task_id if task else None, **change),
        )

    def _label(self, task: _Task) -> str:
        return f"P{self.plan.no:02d} · {task.spec.type.value}"

    # --- run ------------------------------------------------------------------------------

    @workflow.run
    async def run(self, inp: PositionInput) -> PositionResult:
        self.plunet_queue = inp.plunet_queue
        self.plan = await self._act(projection.load_position, inp.position_id)
        self.tasks = [_Task(spec) for spec in self.plan.tasks]
        self.cursor = min(inp.start_from, len(self.tasks))
        if inp.start_from:
            await self._act(projection.reset_tasks, self.plan.position_id, inp.start_from)
        try:
            return await self._loop()
        except asyncio.CancelledError:
            # The order workflow was cancelled (parent close policy): clean up in Plunet, then stop.
            self.cancel_reason = self.cancel_reason or "Order cancelled"
            await self._cancel()
            raise

    async def _loop(self) -> PositionResult:
        while self.cursor < len(self.tasks):
            if self.paused:
                await workflow.wait_condition(lambda: not self.paused or self.cancel_reason is not None)
            if self.cancel_reason:
                return await self._cancel()
            if self.restart_to is not None:
                await self._restart()
                continue

            task = self.current
            ok = await self._run_task(task)

            if self.cancel_reason:
                return await self._cancel()
            if self.restart_to is not None:
                await self._restart()
                continue
            if ok:
                self.cursor += 1
                continue
            # Business failure: wait for a person to decide (architecture §5.2).
            await workflow.wait_condition(
                lambda: self.retry_requested or self.restart_to is not None or self.cancel_reason is not None
            )
            self.retry_requested = False

        self.finished = WorkflowStatus.COMPLETED
        await self._act(
            projection.close_position,
            PositionClose(position_id=self.plan.position_id, status=WorkflowStatus.COMPLETED,
                          message=f"P{self.plan.no:02d} · Workflow completed"),
        )
        return PositionResult(position_id=self.plan.position_id, status=WorkflowStatus.COMPLETED)

    async def _restart(self) -> None:
        seq, self.restart_to = self.restart_to, None
        await self._act(projection.reset_tasks, self.plan.position_id, seq)
        for task in self.tasks[seq:]:
            task.reset()
        self.cursor = seq
        self.retry_requested = False

    async def _cancel(self) -> PositionResult:
        # Plunet first: open jobs and the item become CANCELED, then the local state follows.
        try:
            jobs = await self._plunet(plunet.plunet_cancel_position, self.plan.position_id)
            outcome = f"{jobs} Plunet job(s) set to CANCELED"
        except ActivityError as err:
            # The cancellation stands; the PM finishes the cleanup in Plunet by hand.
            outcome = "Plunet not updated, check it by hand"
            await self._record(
                None, message=f"P{self.plan.no:02d} · Plunet cleanup failed: {_error_message(err)}",
                level=EventLevel.WARN, kind=EventKind.LOG, position_status=None,
            )
        self.finished = WorkflowStatus.CANCELLED
        for task in self.tasks:
            if task.status not in (TaskStatus.DONE, TaskStatus.SKIPPED):
                task.status = TaskStatus.CANCELLED
        await self._act(
            projection.close_position,
            PositionClose(
                position_id=self.plan.position_id, status=WorkflowStatus.CANCELLED,
                message=f"P{self.plan.no:02d} · Workflow cancelled · {outcome}",
                actor=self.cancel_actor, reason=self.cancel_reason,
            ),
        )
        return PositionResult(position_id=self.plan.position_id, status=WorkflowStatus.CANCELLED)

    # --- tasks ----------------------------------------------------------------------------

    async def _run_task(self, task: _Task) -> bool:
        task.attempts += 1
        task.error = None
        task.status = TaskStatus.WAITING if task.spec.type.is_plunet_job else TaskStatus.RUNNING
        await self._record(
            task, task_status=task.status, attempts=task.attempts, started=True,
            message=f"{self._label(task)} started" + (f" (attempt {task.attempts})" if task.attempts > 1 else ""),
        )
        try:
            if task.spec.type == TaskType.IMPORT:
                return await self._import(task)
            if task.spec.type.is_plunet_job:
                return await self._human(task)
            if task.spec.type == TaskType.QA:
                return await self._qa(task)
            if task.spec.type == TaskType.DELIVER:
                return await self._deliver(task)
            raise ApplicationError(f"Unknown task type {task.spec.type}", non_retryable=True)
        except ActivityError as err:
            await self._fail(task, _error_message(err))
            return False

    async def _done(self, task: _Task, message: str, **change) -> bool:
        task.status = TaskStatus.DONE
        await self._record(task, task_status=TaskStatus.DONE, finished=True, message=message, **change)
        return True

    async def _fail(self, task: _Task, error: str, **change) -> None:
        task.status, task.error = TaskStatus.FAILED, error
        await self._record(
            task, task_status=TaskStatus.FAILED, finished=True, error=error,
            message=f"{self._label(task)} failed: {error}", level=EventLevel.ERROR, **change,
        )

    async def _import(self, task: _Task) -> bool:
        result = await self._act(content.import_xliff, self.plan.position_id, timeout=SLOW)
        await self._plunet(plunet.plunet_create_item, self.plan.position_id)
        uploaded = await self._plunet(plunet.plunet_upload_source, self.plan.position_id, result.file_name)
        return await self._done(
            task,
            f"{self._label(task)} · Imported post #{self.plan.post_id} → {result.file_name} "
            f"({result.segments} segments, {result.words} words)"
            + ("" if uploaded else "; file already on the Plunet item"),
        )

    async def _qa(self, task: _Task) -> bool:
        source = await self._plunet(plunet.plunet_fetch_translation, self.plan.position_id)
        result = await self._act(content.run_qa, self.plan.position_id, timeout=SLOW)
        if result.blocking:
            units = sorted({f.unit_id for f in result.findings if f.level == "BLOCKING"})
            await self._fail(
                task, f"QA failed: {result.blocking} blocking finding(s) ({', '.join(units[:5])})",
                findings=result.findings,
            )
            return False
        return await self._done(
            task,
            f"{self._label(task)} passed on {source}" + (f" · {result.warnings} warning(s)" if result.warnings else ""),
            findings=result.findings,
        )

    async def _deliver(self, task: _Task) -> bool:
        result = await self._act(content.deliver, self.plan.position_id, timeout=SLOW)
        await self._plunet(plunet.plunet_set_item_status, self.plan.position_id, "DELIVERED")
        return await self._done(task, f"{self._label(task)} · {result.message}", data=result.data)

    async def _human(self, task: _Task) -> bool:
        """Create (or reuse) the Plunet job, then follow its status until it is delivered."""
        info = await self._plunet(
            plunet.plunet_create_job, JobRequest(task_id=task.spec.task_id, force_new=task.job_id is not None)
        )
        task.job_id, task.job_status = info.job_id, None
        overdue_warned = False
        status = info.status
        resource_id: int | None = None
        while True:
            if status != task.job_status:
                task.job_status = status
                mapped = task_status_from_plunet(status)
                if mapped == TaskStatus.DONE:
                    outcome = await self._plunet(plunet.plunet_job_outcome, task.job_id)
                    return await self._done(
                        task, f"{self._label(task)} done · Plunet job J-{task.job_id} → {status}",
                        plunet_job_id=task.job_id, plunet_job_status=status, cost=outcome.cost,
                        currency=outcome.currency, assignee_plunet_id=outcome.resource_id,
                        assignee_name=outcome.resource_name,
                    )
                if mapped == TaskStatus.CANCELLED:
                    await self._fail(
                        task, f"Plunet job J-{task.job_id} was cancelled in Plunet",
                        plunet_job_id=task.job_id, plunet_job_status=status,
                    )
                    return False
                task.status = TaskStatus.RUNNING if mapped == TaskStatus.RUNNING else TaskStatus.WAITING
                await self._record(
                    task, task_status=task.status, plunet_job_id=task.job_id, plunet_job_status=status,
                    assignee_plunet_id=resource_id,
                    message=f"{self._label(task)} · Plunet job J-{task.job_id} → {status}", actor="plunet",
                )

            seen = self.signal_version
            timeout = None
            if not overdue_warned and self.plan.deadline:
                remaining = (self.plan.deadline.replace(tzinfo=None) - workflow.now().replace(tzinfo=None)).total_seconds()
                timeout = timedelta(seconds=max(remaining, 1))
            try:
                await workflow.wait_condition(
                    lambda seen=seen: self.signal_version != seen or self.cancel_reason is not None or self.restart_to is not None,
                    timeout=timeout,
                )
            except TimeoutError:
                overdue_warned = True
                await self._record(
                    task, message=f"{self._label(task)} is overdue (deadline passed); Plunet job J-{task.job_id}",
                    level=EventLevel.WARN, kind=EventKind.LOG,
                )
                continue
            if self.cancel_reason is not None or self.restart_to is not None:
                return False
            signal = self.job_signals.get(task.job_id)
            if signal:
                status, resource_id = signal.status, signal.resource_id

    # --- signals, updates, query ------------------------------------------------------------

    @workflow.signal
    def plunet_job_status(self, signal: JobStatusSignal) -> None:
        previous = self.job_signals.get(signal.job_id)
        if previous is None or previous.status != signal.status or previous.resource_id != signal.resource_id:
            self.job_signals[signal.job_id] = signal
            self.signal_version += 1

    def _check_active(self) -> None:
        if self.finished or self.cancel_reason:
            raise ValueError("The workflow is finished or being cancelled")

    async def _action(self, message: str, request: ActionRequest, **change) -> None:
        await self._record(None, kind=EventKind.ACTION, message=message, actor=request.actor, reason=request.reason, **change)

    @workflow.update
    async def pause(self, request: ActionRequest) -> PositionState:
        self.paused = True
        await self._action(f"P{self.plan.no:02d} · Paused by {request.actor}", request)
        return self.state()

    @pause.validator
    def _validate_pause(self, request: ActionRequest) -> None:
        self._check_active()
        if self.paused:
            raise ValueError("Already paused")

    @workflow.update
    async def resume(self, request: ActionRequest) -> PositionState:
        self.paused = False
        await self._action(f"P{self.plan.no:02d} · Resumed by {request.actor}", request)
        return self.state()

    @resume.validator
    def _validate_resume(self, request: ActionRequest) -> None:
        self._check_active()
        if not self.paused:
            raise ValueError("Not paused")

    @workflow.update
    async def retry(self, request: ActionRequest) -> PositionState:
        task = self.current
        self.retry_requested = True
        await self._action(f"{self._label(task)} · Retry requested by {request.actor}", request)
        return self.state()

    @retry.validator
    def _validate_retry(self, request: ActionRequest) -> None:
        self._check_active()
        if self.current is None or self.current.status != TaskStatus.FAILED:
            raise ValueError("Retry is only possible when the current task has failed")

    @workflow.update
    async def restart_from(self, request: RestartRequest) -> PositionState:
        task = self.current
        # Plunet first: a job still open on a task being reset is cancelled before moving back.
        if task and task.job_id and task.status in (TaskStatus.WAITING, TaskStatus.RUNNING) and request.seq <= self.cursor:
            await self._plunet(plunet.plunet_cancel_job, task.job_id)
        self.restart_to = request.seq
        target = self.tasks[request.seq]
        await self._action(f"P{self.plan.no:02d} · Restart from {target.spec.type.value} by {request.actor}", request)
        return self.state()

    @restart_from.validator
    def _validate_restart(self, request: RestartRequest) -> None:
        self._check_active()
        if not 0 <= request.seq < len(self.tasks):
            raise ValueError(f"No task {request.seq}")
        if request.seq > self.cursor:
            raise ValueError("Can only restart from the current task or an earlier one")

    @workflow.update
    async def cancel(self, request: ActionRequest) -> PositionState:
        self.cancel_reason, self.cancel_actor = request.reason, request.actor
        await self._action(f"P{self.plan.no:02d} · Cancel requested by {request.actor}", request)
        return self.state()

    @cancel.validator
    def _validate_cancel(self, request: ActionRequest) -> None:
        self._check_active()
        if not (request.reason and request.reason.strip()):
            raise ValueError("A reason is required to cancel")

    @workflow.query
    def state(self) -> PositionState:
        return PositionState(
            position_id=self.plan.position_id if self.plan else 0,
            status=self._status(),
            cursor=self.cursor,
            paused=self.paused,
            cancel_reason=self.cancel_reason,
            tasks=[
                TaskState(seq=t.spec.seq, type=t.spec.type, status=t.status, attempts=t.attempts,
                          plunet_job_id=t.job_id, plunet_job_status=t.job_status, error=t.error)
                for t in self.tasks
            ],
        )
