"""Development workflows: act as the PM or translator in the fake Plunet (PLUNET_MODE=fake)."""

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.activities import plunet
    from app.workflows.models import DEFAULT_PLUNET_QUEUE


@workflow.defn
class DevPlunetJobStatusWorkflow:
    @workflow.run
    async def run(self, job_id: int, status: str, resource_id: int | None = None, plunet_queue: str = DEFAULT_PLUNET_QUEUE) -> None:
        await workflow.execute_activity(
            plunet.dev_plunet_job_status, args=[job_id, status, resource_id],
            task_queue=plunet_queue, start_to_close_timeout=timedelta(seconds=30),
        )


@workflow.defn
class DevPlunetConvertQuoteWorkflow:
    @workflow.run
    async def run(self, order_id: int, plunet_queue: str = DEFAULT_PLUNET_QUEUE) -> int:
        return await workflow.execute_activity(
            plunet.dev_plunet_convert_quote, order_id,
            task_queue=plunet_queue, start_to_close_timeout=timedelta(seconds=30),
        )
