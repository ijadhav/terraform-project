"""Queue-worker entrypoint for long-running Terrabot automated tests."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

LOGGER = logging.getLogger("terrabot.automated_tests.worker")


def _decode_queue_payload(message: Any) -> dict:
    if isinstance(message, dict):
        return dict(message)
    if isinstance(message, bytes):
        raw = message.decode("utf-8", errors="replace")
    elif hasattr(message, "get_body"):
        body = message.get_body()
        raw = body.decode("utf-8", errors="replace") if isinstance(body, (bytes, bytearray)) else str(body)
    else:
        raw = str(message or "")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Automated-test queue payload must be a JSON object.")
    return parsed


def process_automated_test_queue_message(core: Any, message: Any) -> dict:
    """Execute one queued test run and proactively post the final Teams report."""
    from shared_code.automated_tests.terrabot_test_runner import execute_automated_test_job

    payload = _decode_queue_payload(message)
    report = execute_automated_test_job(core, payload)

    reference = payload.get("conversation_reference") or {}
    if reference and report:
        try:
            from shared_code.teams_bot import send_automated_test_report
            asyncio.run(send_automated_test_report(reference, report))
        except Exception:
            LOGGER.exception(
                "Unable to proactively post automated-test report to Teams: run_id=%s",
                payload.get("run_id"),
            )
    return {"ok": True, "run_id": payload.get("run_id"), "report": report}
