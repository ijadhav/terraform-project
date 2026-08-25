"""Azure Functions Blueprint for queued Terrabot automated test execution.

Register ``blueprint`` once from the project's existing ``function_app.py``.
Keeping the trigger here prevents long-running test logic from leaking into the
main Function App module.
"""
from __future__ import annotations

import logging
import os

import azure.functions as func

LOGGER = logging.getLogger("terrabot.automated_tests.queue_function")

blueprint = func.Blueprint()
_QUEUE_NAME = os.getenv("TERRABOT_TEST_RUNNER_QUEUE_NAME", "terrabot-automated-tests").strip() or "terrabot-automated-tests"
_QUEUE_CONNECTION_SETTING = (
    os.getenv("TERRABOT_TEST_RUNNER_STORAGE_CONNECTION_SETTING", "AzureWebJobsStorage").strip()
    or "AzureWebJobsStorage"
)


@blueprint.function_name(name="terrabot_automated_test_worker")
@blueprint.queue_trigger(
    arg_name="message",
    queue_name=_QUEUE_NAME,
    connection=_QUEUE_CONNECTION_SETTING,
)
def terrabot_automated_test_worker(message: func.QueueMessage) -> None:
    """Execute one long-running test run outside the Teams HTTP invocation."""
    from shared_code.terrabot_service import process_automated_test_queue_message

    LOGGER.info(
        "[TerrabotTest] event=queue_trigger_received message_id=%s dequeue_count=%s",
        getattr(message, "id", ""),
        getattr(message, "dequeue_count", ""),
    )
    process_automated_test_queue_message(message)
