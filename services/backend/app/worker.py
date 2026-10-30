"""Temporal worker entrypoint: `python -m app.worker`.

Two workers in one process:
- `fox-orchestration`: workflows and the fast async activities (database, Polylang, QA).
- `fox-plunet`: synchronous SOAP activities on a small thread pool, so Plunet is not flooded.
"""

import asyncio
import logging
import signal
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleIntervalSpec,
    ScheduleOverlapPolicy,
    SchedulePolicy,
    ScheduleSpec,
    ScheduleUpdate,
)
from temporalio.worker import Worker

from app.activities import content, plunet, projection
from app.activities.events import write_event
from app.config import get_settings
from app.temporal.client import connect_temporal
from app.workflows.dev import DevPlunetConvertQuoteWorkflow, DevPlunetJobStatusWorkflow
from app.workflows.order import OrderWorkflow
from app.workflows.position import PositionWorkflow
from app.workflows.sync import SYNC_SCHEDULE_ID, PlunetSyncWorkflow
from app.workflows.system import SystemCheckWorkflow

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("app.worker")

WORKFLOWS = [
    SystemCheckWorkflow,
    OrderWorkflow,
    PositionWorkflow,
    PlunetSyncWorkflow,
    DevPlunetJobStatusWorkflow,
    DevPlunetConvertQuoteWorkflow,
]
ORCHESTRATION_ACTIVITIES = [
    write_event,
    projection.load_order,
    projection.load_position,
    projection.record_task,
    projection.reset_tasks,
    projection.close_position,
    projection.update_order,
    projection.set_position_workflow,
    projection.collect_sync_targets,
    content.import_xliff,
    content.run_qa,
    content.deliver,
]
PLUNET_ACTIVITIES = [
    plunet.plunet_create_project,
    plunet.plunet_set_quote_status,
    plunet.plunet_adopt_order,
    plunet.plunet_create_item,
    plunet.plunet_upload_source,
    plunet.plunet_set_item_status,
    plunet.plunet_create_job,
    plunet.plunet_job_outcome,
    plunet.plunet_cancel_job,
    plunet.plunet_cancel_position,
    plunet.plunet_fetch_translation,
    plunet.plunet_poll,
    plunet.dev_plunet_job_status,
    plunet.dev_plunet_convert_quote,
]


async def ensure_sync_schedule(client: Client) -> None:
    """Create or update the 2-minute PlunetSyncWorkflow schedule (overlap SKIP)."""
    settings = get_settings()
    schedule = Schedule(
        action=ScheduleActionStartWorkflow(
            PlunetSyncWorkflow.run,
            settings.TEMPORAL_PLUNET_TASK_QUEUE,
            id="plunet-sync-run",
            task_queue=settings.TEMPORAL_TASK_QUEUE,
        ),
        spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(seconds=settings.PLUNET_SYNC_SECONDS))]),
        policy=SchedulePolicy(overlap=ScheduleOverlapPolicy.SKIP),
    )
    try:
        await client.create_schedule(SYNC_SCHEDULE_ID, schedule)
        logger.info("Created schedule %s (every %ss)", SYNC_SCHEDULE_ID, settings.PLUNET_SYNC_SECONDS)
    except ScheduleAlreadyRunningError:
        await client.get_schedule_handle(SYNC_SCHEDULE_ID).update(lambda _: ScheduleUpdate(schedule=schedule))
        logger.info("Updated schedule %s (every %ss)", SYNC_SCHEDULE_ID, settings.PLUNET_SYNC_SECONDS)


async def connect_with_retry() -> Client:
    for attempt in range(1, 31):
        try:
            return await connect_temporal()
        except Exception as exc:
            logger.warning("Temporal not reachable (attempt %d): %s", attempt, exc)
            await asyncio.sleep(2)
    raise SystemExit("Could not connect to Temporal")


async def main() -> None:
    settings = get_settings()
    client = await connect_with_retry()
    await ensure_sync_schedule(client)

    with ThreadPoolExecutor(max_workers=settings.PLUNET_MAX_CONCURRENT_CALLS) as plunet_pool:
        orchestration = Worker(
            client,
            task_queue=settings.TEMPORAL_TASK_QUEUE,
            workflows=WORKFLOWS,
            activities=ORCHESTRATION_ACTIVITIES,
        )
        plunet_worker = Worker(
            client,
            task_queue=settings.TEMPORAL_PLUNET_TASK_QUEUE,
            activities=PLUNET_ACTIVITIES,
            activity_executor=plunet_pool,
            max_concurrent_activities=settings.PLUNET_MAX_CONCURRENT_CALLS,
        )

        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)

        logger.info(
            "Worker started on %s (namespace %s, queues %s and %s, Plunet mode %s)",
            settings.TEMPORAL_ADDRESS, settings.TEMPORAL_NAMESPACE,
            settings.TEMPORAL_TASK_QUEUE, settings.TEMPORAL_PLUNET_TASK_QUEUE, settings.PLUNET_MODE,
        )
        async with orchestration, plunet_worker:
            await stop.wait()
            logger.info("Shutting down: finishing running activities")


if __name__ == "__main__":
    asyncio.run(main())
