"""Temporal worker entrypoint: `python -m app.worker`."""

import asyncio
import logging

from temporalio.worker import Worker

from app.activities.events import write_event
from app.config import get_settings
from app.temporal.client import connect_temporal
from app.workflows.system import SystemCheckWorkflow

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("app.worker")

WORKFLOWS = [SystemCheckWorkflow]
ACTIVITIES = [write_event]


async def main() -> None:
    settings = get_settings()
    client = None
    for attempt in range(1, 31):
        try:
            client = await connect_temporal()
            break
        except Exception as exc:
            logger.warning("Temporal not reachable (attempt %d): %s", attempt, exc)
            await asyncio.sleep(2)
    if client is None:
        raise SystemExit("Could not connect to Temporal")

    worker = Worker(
        client,
        task_queue=settings.TEMPORAL_TASK_QUEUE,
        workflows=WORKFLOWS,
        activities=ACTIVITIES,
    )
    logger.info(
        "Worker started on %s (namespace %s, queue %s)",
        settings.TEMPORAL_ADDRESS,
        settings.TEMPORAL_NAMESPACE,
        settings.TEMPORAL_TASK_QUEUE,
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
