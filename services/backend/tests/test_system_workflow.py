import uuid

from temporalio import activity
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app.activities.events import EventInput
from app.workflows.system import SystemCheckWorkflow

written: list[EventInput] = []


@activity.defn(name="write_event")
async def fake_write_event(event: EventInput) -> int:
    written.append(event)
    return 42


async def test_system_check_writes_one_event():
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue="test",
            workflows=[SystemCheckWorkflow],
            activities=[fake_write_event],
        ):
            result = await env.client.execute_workflow(
                SystemCheckWorkflow.run, "tester", id=f"wf-{uuid.uuid4()}", task_queue="test"
            )
    assert result == 42
    assert written[-1].actor == "tester"
