"""Failure classification and context-gap analysis for Terrabot E2E tests."""
from __future__ import annotations

import hashlib
from typing import Any


def _cursor_failure(case: Any, result: Any) -> str:
    if not getattr(result, "cursor_validation_requested", False):
        return ""
    if not getattr(result, "cursor_validation_completed", False):
        return "CURSOR_VALIDATION_UNAVAILABLE"
    if not getattr(result, "cursor_output_correct", False):
        return "CURSOR_OUTPUT_VALIDATION_FAILURE"
    if str(getattr(case, "case_type", "")) == "boolean_context":
        if not getattr(result, "cursor_context_added", False):
            return "CURSOR_CONTEXT_STORAGE_VALIDATION_FAILURE"
        if not getattr(result, "cursor_context_retrievable", False):
            return "CURSOR_CONTEXT_RETRIEVAL_VALIDATION_FAILURE"
        if not getattr(result, "cursor_context_reused", False):
            return "CURSOR_CONTEXT_REUSE_VALIDATION_FAILURE"
    if not getattr(result, "cursor_overall_ok", False):
        return "CURSOR_VALIDATION_FAILURE"
    return ""


def classify_result(case: Any, result: Any) -> str:
    if getattr(result, "error", ""):
        return "BACKEND_OR_HARNESS_FAILURE"
    if not getattr(result, "expected_target_found", False):
        return "TARGET_RESOLUTION_FAILURE"
    if not getattr(result, "correct_flag_detected", False):
        return "CONTROL_RESOLUTION_FAILURE"
    if not getattr(result, "phase1_file_generated", False):
        return "GENERATION_FAILURE"
    if not getattr(result, "validation_ok", False):
        return "VALIDATION_FAILURE"
    if not getattr(result, "branch_pushed", False):
        return "BRANCH_FAILURE"
    if str(getattr(case, "case_type", "")) == "resource_creation":
        cursor_failure = _cursor_failure(case, result)
        if cursor_failure:
            return cursor_failure
        return "PASS" if getattr(result, "score", 0) == 100 else "CREATION_WORKFLOW_FAILURE"
    if not getattr(result, "context_stored", False):
        return "CONTEXT_STORAGE_FAILURE"
    if not getattr(result, "phase2_context_retrieved", False):
        return "CONTEXT_RETRIEVAL_FAILURE"
    if not getattr(result, "phase2_context_attached", False):
        if getattr(result, "phase2_context_retrieved", False):
            return "CONTEXT_ATTACHMENT_BACKEND_DEFECT"
        return "CONTEXT_ATTACHMENT_FAILURE"
    if getattr(result, "phase2_clarified", False) and getattr(result, "phase2_target_ok", False):
        return "UNNECESSARY_CLARIFICATION"
    if not getattr(result, "phase2_target_ok", False):
        return "CONTEXT_REUSE_FAILURE"
    cursor_failure = _cursor_failure(case, result)
    if cursor_failure:
        return cursor_failure
    return "PASS"


def is_context_gap(case: Any, result: Any, *, context_present_before: bool) -> bool:
    """Return True only for repository-knowledge failures, not generic failures."""
    if str(getattr(case, "case_type", "")) != "boolean_context":
        return False
    if context_present_before:
        return False
    if not getattr(result, "expected_target_found", False) or not getattr(result, "correct_flag_detected", False):
        return False
    return bool(
        getattr(result, "phase1_clarified", False)
        or not getattr(result, "production_context_created", False)
    )


def build_boolean_context_candidate(case: Any, *, run_id: str, evidence_line: str) -> dict[str, Any]:
    statement = (
        f"In {case.repo}, {case.alias} maps to Boolean control {case.flag} "
        f"in {case.path} for environment {case.environment}."
    )
    return {
        "candidate_id": "ctxcand-" + hashlib.sha1(f"{run_id}:{case.case_id}:{case.flag}".encode()).hexdigest()[:16],
        "run_id": run_id,
        "case_id": case.case_id,
        "repository": f"{case.owner}/{case.repo}",
        "status": "candidate",
        "category": "resolved_clarification",
        "subject": case.alias,
        "scope": case.environment,
        "statement": statement,
        "confidence": 0.99,
        "evidence": [{
            "path": case.path,
            "excerpt": evidence_line,
            "reason": f"The live assignment proves the Boolean control {case.flag}.",
        }],
        "source": "automated_test_context_gap",
    }
