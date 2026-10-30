"""PlunetSyncWorkflow: the only path for changes made in Plunet (decision 1: no callbacks).

Runs every PLUNET_SYNC_SECONDS through a Temporal Schedule (overlap SKIP). It reads open jobs and
pending quotes, asks Plunet for their state and signals the workflows that changed. Signals are
idempotent, so a change seen twice is harmless.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.exceptions import ApplicationError

with workflow.unsafe.imports_passed_through():
    from app.activities import plunet, projection
    from app.activities.common import RETRY
    from app.workflows.models import (
        DEFAULT_PLUNET_QUEUE,
        QuoteConverted,
        QuoteDecision,
        SyncChanges,
        SyncTargets,
    )
    from app.workflows.order import OrderWorkflow
    from app.workflows.position import PositionWorkflow

SYNC_SCHEDULE_ID = "plunet-sync"
REJECTED = {"REJECTED", "CANCELED", "EXPIRED"}


def order_workflow_id(order_id: int) -> str:
    return f"order-{order_id}"


@workflow.defn
class PlunetSyncWorkflow:
    @workflow.run
    async def run(self, plunet_queue: str = DEFAULT_PLUNET_QUEUE) -> dict:
        targets: SyncTargets = await workflow.execute_activity(
            projection.collect_sync_targets, start_to_close_timeout=timedelta(seconds=30), retry_policy=RETRY
        )
        if not targets.jobs and not targets.quotes:
            return {"jobs": 0, "quotes": 0, "signalled": 0}
        changes: SyncChanges = await workflow.execute_activity(
            plunet.plunet_poll, targets, task_queue=plunet_queue,
            start_to_close_timeout=timedelta(minutes=2), retry_policy=RETRY,
        )
        signalled = 0
        for change in changes.jobs:
            signalled += await self._signal(
                f"position-{change.position_id}", PositionWorkflow.plunet_job_status, change.signal
            )
        for change in changes.quotes:
            wf_id = order_workflow_id(change.order_id)
            if change.plunet_order_id:
                signalled += await self._signal(wf_id, OrderWorkflow.quote_converted, QuoteConverted(plunet_order_id=change.plunet_order_id))
            elif change.plunet_status in REJECTED:
                signalled += await self._signal(wf_id, OrderWorkflow.quote_rejected, QuoteDecision(actor="plunet", in_plunet=True))
            elif change.plunet_status == "ACCEPTED":
                signalled += await self._signal(wf_id, OrderWorkflow.quote_accepted, QuoteDecision(actor="plunet", in_plunet=True))
        return {"jobs": len(targets.jobs), "quotes": len(targets.quotes), "signalled": signalled}

    async def _signal(self, workflow_id: str, signal, arg) -> int:
        try:
            await workflow.get_external_workflow_handle(workflow_id).signal(signal, arg)
            return 1
        except ApplicationError:
            workflow.logger.warning("Workflow %s not running; change ignored", workflow_id)
            return 0
