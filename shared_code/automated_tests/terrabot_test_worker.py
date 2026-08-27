"""Queue-worker entrypoint for long-running Terrabot automated tests."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any

LOGGER = logging.getLogger("terrabot.automated_tests.worker")


def _decode_queue_payload(message: Any) -> dict:
    """Decode one Azure Queue payload.

    Production queue-trigger invocations normally expose JSON bytes because the
    Functions host already decodes MessageEncoding=Base64. A Base64 fallback is
    retained for compatibility with direct/manual bindings and older messages.
    """
    if isinstance(message, dict):
        return dict(message)
    if isinstance(message, bytes):
        raw = message.decode("utf-8", errors="replace")
    elif hasattr(message, "get_body"):
        body = message.get_body()
        raw = body.decode("utf-8", errors="replace") if isinstance(body, (bytes, bytearray)) else str(body or "")
    else:
        raw = str(message or "")

    raw = raw.strip()
    if not raw:
        raise ValueError(
            "Automated-test queue payload is empty. Do not use Code + Test Run "
            "without a queue message; start the workflow from Teams with 'run tests'."
        )

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as first_error:
        # Compatibility fallback if a manually-invoked binding or legacy host
        # hands the worker the Base64 text instead of the host-decoded body.
        try:
            decoded = base64.b64decode(raw, validate=True).decode("utf-8")
            parsed = json.loads(decoded)
        except Exception as fallback_error:
            raise ValueError(
                f"Automated-test queue payload is neither JSON nor valid Base64 JSON "
                f"(length={len(raw)})."
            ) from first_error

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
