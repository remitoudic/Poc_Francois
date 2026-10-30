"""OrderWorkflow: creates the order or quote in Plunet, waits for quote acceptance, then runs one
child PositionWorkflow per position (architecture §5.1).

Quote acceptance (decision 6): FOX MLO sets the quote to ACCEPTED in Plunet; the PM converts it
into an order in Plunet; PlunetSyncWorkflow detects the new order and signals `quote_converted`.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.workflow import ParentClosePolicy

with workflow.unsafe.imports_passed_through():
    from app.activities import content, plunet, projection
    from app.activities.common import RETRY
    from app.domain.enums import EventKind, OrderKind, OrderStatus, WorkflowStatus
    from app.integrations.plunet.enums import ProjectType
    from app.workflows.models import (
        OrderChange,
        OrderInput,
        OrderPlan,
        PositionInput,
        PositionResult,
        QuoteConverted,
        QuoteDecision,
    )
    from app.workflows.position import PositionWorkflow

FAST = timedelta(seconds=30)
SLOW = timedelta(minutes=5)


def position_workflow_id(position_id: int) -> str:
    return f"position-{position_id}"


@workflow.defn
class OrderWorkflow:
    def __init__(self) -> None:
        self.inp: OrderInput | None = None
        self.accepted: QuoteDecision | None = None
        self.rejected: QuoteDecision | None = None
        self.converted_order_id: int | None = None
        self.started_positions = False

    async def _act(self, fn, *args, timeout: timedelta = FAST):
        return await workflow.execute_activity(fn, args=list(args), start_to_close_timeout=timeout, retry_policy=RETRY)

    async def _plunet(self, fn, *args, timeout: timedelta = SLOW):
        return await workflow.execute_activity(
            fn, args=list(args), task_queue=self.inp.plunet_queue, start_to_close_timeout=timeout, retry_policy=RETRY
        )

    async def _order(self, **change) -> None:
        await self._act(projection.update_order, OrderChange(order_id=self.inp.order_id, **change))

    @workflow.run
    async def run(self, inp: OrderInput) -> OrderStatus:
        self.inp = inp
        plan: OrderPlan = await self._act(projection.load_order, inp.order_id)
        project = await self._plunet(plunet.plunet_create_project, inp.order_id)
        kind = "Plunet quote" if project.project_type == ProjectType.QUOTE else "Plunet order"

        if plan.kind == OrderKind.QUOTE and not plan.plunet_order_id:
            outcome = await self._quote(plan, f"{kind} {project.number}")
            if outcome is not None:
                return outcome
        else:
            await self._order(status=OrderStatus.RUNNING, message=f"{kind} {project.number} created")

        return await self._run_positions(plan)

    async def _quote(self, plan: OrderPlan, label: str) -> OrderStatus | None:
        """Prepare the quote (items + files so the PM can price it) and wait for the customer."""
        # Each step is idempotent, so a worker restart repeats them safely.
        for position_id in plan.position_ids:
            await self._plunet(plunet.plunet_create_item, position_id)
            result = await self._act(content.import_xliff, position_id, timeout=SLOW)
            await self._plunet(plunet.plunet_upload_source, position_id, result.file_name)
        # Plunet accepts items only while the quote is in preparation; release it afterwards.
        await self._plunet(plunet.plunet_set_quote_status, plan.order_id, "PENDING")
        await self._order(
            status=OrderStatus.AWAITING_ACCEPTANCE,
            message=f"{label} created with {len(plan.position_ids)} item(s); waiting for the customer",
        )

        await workflow.wait_condition(lambda: bool(self.accepted or self.rejected or self.converted_order_id))
        if self.rejected and not self.converted_order_id:
            if not self.rejected.in_plunet:
                await self._plunet(plunet.plunet_set_quote_status, plan.order_id, "REJECTED")
            await self._order(
                status=OrderStatus.REJECTED, message="Quote rejected" + (" in Plunet" if self.rejected.in_plunet else ""),
                actor=self.rejected.actor, reason=self.rejected.reason,
                kind=EventKind.STATE if self.rejected.in_plunet else EventKind.ACTION,
            )
            return OrderStatus.REJECTED

        if self.accepted and not self.converted_order_id:
            if not self.accepted.in_plunet:
                await self._plunet(plunet.plunet_set_quote_status, plan.order_id, "ACCEPTED")  # Plunet first
            await self._order(
                status=OrderStatus.AWAITING_ACCEPTANCE,
                message="Quote accepted" + (" in Plunet" if self.accepted.in_plunet else "")
                + "; waiting for the PM to convert it into an order in Plunet",
                actor=self.accepted.actor, kind=EventKind.STATE if self.accepted.in_plunet else EventKind.ACTION,
            )
            await workflow.wait_condition(lambda: bool(self.converted_order_id or self.rejected))
            if not self.converted_order_id:
                await self._order(status=OrderStatus.REJECTED, message="Quote cancelled in Plunet before conversion")
                return OrderStatus.REJECTED

        number = await self._plunet(plunet.plunet_adopt_order, plan.order_id, self.converted_order_id)
        await self._order(status=OrderStatus.RUNNING, message=f"Quote converted into Plunet order {number}; workflows start")
        return None

    async def _run_positions(self, plan: OrderPlan) -> OrderStatus:
        self.started_positions = True
        handles = []
        for position_id in plan.position_ids:
            wf_id = position_workflow_id(position_id)
            await self._act(projection.set_position_workflow, position_id, wf_id)
            handles.append(
                await workflow.start_child_workflow(
                    PositionWorkflow.run,
                    PositionInput(position_id=position_id, plunet_queue=self.inp.plunet_queue),
                    id=wf_id,
                    parent_close_policy=ParentClosePolicy.REQUEST_CANCEL,
                )
            )
        results = await asyncio.gather(*handles, return_exceptions=True)
        statuses = [r.status if isinstance(r, PositionResult) else WorkflowStatus.FAILED for r in results]
        done = sum(s == WorkflowStatus.COMPLETED for s in statuses)
        await self._order(message=f"All positions finished: {done}/{len(statuses)} completed")  # status recomputed
        if all(s == WorkflowStatus.CANCELLED for s in statuses):
            return OrderStatus.CANCELLED
        return OrderStatus.COMPLETED

    # --- signals (from the api or from PlunetSyncWorkflow; all idempotent) -----------------

    @workflow.signal
    def quote_accepted(self, decision: QuoteDecision) -> None:
        if self.accepted is None and self.rejected is None:
            self.accepted = decision

    @workflow.signal
    def quote_rejected(self, decision: QuoteDecision) -> None:
        if self.rejected is None and self.converted_order_id is None:
            self.rejected = decision

    @workflow.signal
    def quote_converted(self, converted: QuoteConverted) -> None:
        if self.converted_order_id is None:
            self.converted_order_id = converted.plunet_order_id
