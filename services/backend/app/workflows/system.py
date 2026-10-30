from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.activities.events import EventInput, write_event


@workflow.defn
class SystemCheckWorkflow:
    """Round trip api → Temporal → worker → Postgres → NOTIFY → SSE, used by the health page."""

    @workflow.run
    async def run(self, requested_by: str) -> int:
        return await workflow.execute_activity(
            write_event,
            EventInput(
                message="System check: Temporal workflow completed",
                actor=requested_by,
                data={"workflow_id": workflow.info().workflow_id},
            ),
            start_to_close_timeout=timedelta(seconds=30),
        )
