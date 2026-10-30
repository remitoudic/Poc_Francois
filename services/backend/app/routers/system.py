"""System checks for the realtime bus and Temporal."""

import uuid

from fastapi import APIRouter

from app.config import get_settings
from app.temporal.client import get_temporal_client
from app.workflows.system import SystemCheckWorkflow

router = APIRouter(prefix="/system", tags=["System"])


@router.post("/check-workflow")
async def run_system_check():
    """Start a workflow that writes one event; watch it arrive on /events/stream."""
    client = await get_temporal_client()
    workflow_id = f"system-check-{uuid.uuid4()}"
    handle = await client.start_workflow(
        SystemCheckWorkflow.run,
        "anonymous",
        id=workflow_id,
        task_queue=get_settings().TEMPORAL_TASK_QUEUE,
    )
    event_id = await handle.result()
    return {"workflow_id": workflow_id, "event_id": event_id}
