"""Cursor result validation — TEMPORARILY DISABLED.

Cursor is kept only for:
  1. Test prompt generation from live repository (cursor_prompt_provider.generate_repository_questions)
  2. Repository target clarification (cursor_prompt_provider.resolve_repository_clarification)

Output validation and post-run result verification are handled exclusively by:
  - Foundry agent self-validation (runs before every commit attempt)
  - Backend deterministic validators (semantic relevance, Terraform shape, preservation, HCL balance)

When a file passes both of those, it is pushed to a branch and the branch URL is returned directly.
Re-enabling this module: set TERRABOT_TEST_CURSOR_RESULT_VALIDATION_ENABLED=true.
"""
from __future__ import annotations
from typing import Any, Mapping, Sequence
import logging

LOGGER = logging.getLogger("terrabot.automated_tests.cursor_validation")


def cursor_result_validation_enabled() -> bool:
    """Always returns False — result validation is temporarily disabled."""
    return False


def validate_test_run_with_cursor(
    *,
    run_id: str,
    cases: Sequence[Mapping[str, Any]],
    http_client: Any = None,
) -> dict[str, Any]:
    """No-op stub — Cursor result validation is temporarily disabled.

    Validation is now owned by agent self-validation + backend validators.
    Branch push and branch URL return happen immediately after those pass.
    """
    LOGGER.debug(
        "[TerrabotCursorValidation] event=cursor_result_validation_skipped "
        "run_id=%s reason=temporarily_disabled_using_self_and_backend_validation",
        run_id,
    )
    return {
        "enabled": False,
        "completed": False,
        "run_id": run_id,
        "agent_id": "",
        "agent_url": "",
        "duration_ms": 0,
        "case_results": {},
        "error": "",
    }


__all__ = ["cursor_result_validation_enabled", "validate_test_run_with_cursor"]
