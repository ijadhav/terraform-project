"""Failure classification and context-gap analysis for Terrabot E2E tests."""
from __future__ import annotations

import hashlib
from typing import Any


# ---------------------------------------------------------------------------
# Extended failure taxonomy (req 16)
# ---------------------------------------------------------------------------
FAILURE_CLASSES = {
    # Legacy classes (preserved for backwards compat)
    "PASS",
    "BACKEND_OR_HARNESS_FAILURE",
    "CONTROL_RESOLUTION_FAILURE",
    "GENERATION_FAILURE",
    "VALIDATION_FAILURE",
    "BRANCH_FAILURE",
    "CONTEXT_STORAGE_FAILURE",
    "CONTEXT_RETRIEVAL_FAILURE",
    "CONTEXT_ATTACHMENT_FAILURE",
    "CONTEXT_ATTACHMENT_BACKEND_DEFECT",
    "UNNECESSARY_CLARIFICATION",
    "CONTEXT_REUSE_FAILURE",
    "CREATION_WORKFLOW_FAILURE",
    "CURSOR_VALIDATION_UNAVAILABLE",
    "CURSOR_OUTPUT_VALIDATION_FAILURE",
    "CURSOR_CONTEXT_STORAGE_VALIDATION_FAILURE",
    "CURSOR_CONTEXT_RETRIEVAL_VALIDATION_FAILURE",
    "CURSOR_CONTEXT_REUSE_VALIDATION_FAILURE",
    "CURSOR_VALIDATION_FAILURE",
    # New specific classes (req 16)
    "REPO_QNA_INTENT_FAILURE",          # Q&A routed to infra generation, or infra routed to Q&A
    "BOOLEAN_SEMANTIC_RESOLUTION_FAILURE",  # Boolean inventory exists but Foundry chose wrong/no flag
    "WORKFLOW_CONTINUITY_FAILURE",      # Target contract was downgraded between P1 and P2
    "GENERATION_TRUNCATION_FAILURE",    # Agent returned shortened/placeholder file
    "AGENT_SELF_VALIDATION_FAILURE",    # Self-validator fired with specific structural reason
    "BACKEND_PRESERVATION_FAILURE",     # Preservation validator rejected full file rewrite
    "SURGICAL_EDIT_ANCHOR_FAILURE",     # old_text not unique and no line anchor available
    "REPAIR_EXHAUSTED",                 # All repair attempts used up without acceptable output
    "CREATION_CASE_INVALID",            # Test case derived against singleton/already-consumed module
    "CONTEXT_REVALIDATION_FAILURE",     # Context record failed live revalidation
    "FAILED_VALIDATION_BRANCH_PUSHED",  # Diagnostic branch pushed after all repairs failed
    "TARGET_RESOLUTION_FAILURE",        # Kept: generic target resolution failed
    "GENERATION_SHAPE_FAILURE",          # Agent/backend produced no executable Terraform files or malformed files[]
    "CREATION_WORKFLOW_ROUTING_FAILURE", # Creation prompt stopped in clarification or wrong workflow before preview
    "BOOLEAN_CONTEXT_ATTACHMENT_FAILURE",# Phase 2 context was retrieved but not attached/reused for generation
    "QNA_ROUTING_FAILURE",               # Repo Q&A leaked into infra generation or failed as a conversation answer
}


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


def classify_result(case: Any, result: Any) -> str:  # noqa: C901 – intentionally ordered
    # Repo Q&A intent gate (req 1, 15)
    if getattr(result, "repo_qna_intent_failure", False) or getattr(result, "qna_routing_failed", False):
        return "QNA_ROUTING_FAILURE"

    if getattr(result, "error", ""):
        return "BACKEND_OR_HARNESS_FAILURE"

    if getattr(result, "creation_case_invalid", False):
        return "CREATION_CASE_INVALID"

    if getattr(result, "creation_workflow_routing_failed", False):
        return "CREATION_WORKFLOW_ROUTING_FAILURE"

    if getattr(result, "generation_shape_failed", False):
        return "GENERATION_SHAPE_FAILURE"

    if getattr(result, "boolean_context_attachment_failed", False):
        return "BOOLEAN_CONTEXT_ATTACHMENT_FAILURE"

    if not getattr(result, "expected_target_found", False):
        # Refine generic TARGET_RESOLUTION_FAILURE where we can
        if getattr(result, "boolean_inventory_exists", False):
            # Inventory was built but Foundry chose wrong flag
            return "BOOLEAN_SEMANTIC_RESOLUTION_FAILURE"
        return "TARGET_RESOLUTION_FAILURE"

    if not getattr(result, "correct_flag_detected", False):
        if getattr(result, "boolean_inventory_exists", False):
            return "BOOLEAN_SEMANTIC_RESOLUTION_FAILURE"
        return "CONTROL_RESOLUTION_FAILURE"

    if not getattr(result, "phase1_file_generated", False):
        if getattr(result, "generation_truncated", False):
            return "GENERATION_TRUNCATION_FAILURE"
        return "GENERATION_FAILURE"

    if not getattr(result, "validation_ok", False):
        # Refine the generic VALIDATION_FAILURE
        if getattr(result, "repair_exhausted", False):
            return "REPAIR_EXHAUSTED"
        if getattr(result, "agent_self_validation_failed", False):
            return "AGENT_SELF_VALIDATION_FAILURE"
        if getattr(result, "backend_preservation_failed", False):
            return "BACKEND_PRESERVATION_FAILURE"
        if getattr(result, "surgical_edit_anchor_failed", False):
            return "SURGICAL_EDIT_ANCHOR_FAILURE"
        return "VALIDATION_FAILURE"

    if getattr(result, "failed_validation_branch_pushed", False):
        return "FAILED_VALIDATION_BRANCH_PUSHED"

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
        if getattr(result, "context_revalidation_failed", False):
            return "CONTEXT_REVALIDATION_FAILURE"
        return "CONTEXT_RETRIEVAL_FAILURE"
    if not getattr(result, "phase2_context_attached", False):
        if getattr(result, "phase2_context_retrieved", False):
            return "CONTEXT_ATTACHMENT_BACKEND_DEFECT"
        return "CONTEXT_ATTACHMENT_FAILURE"
    if getattr(result, "workflow_continuity_failure", False):
        return "WORKFLOW_CONTINUITY_FAILURE"
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


# Repo Q&A result builder (req 1, 15)
def build_repo_qna_check(
    *,
    case_id: str,
    question: str,
    backend_intent: str,
    backend_answer: str,
    evidence_paths: list[str],
    cursor_correct: bool | None,
    cursor_reason: str,
    failure_reason: str = "",
) -> dict[str, Any]:
    """Build a standardised Q&A check record for the test run report."""
    backend_ok = str(backend_intent or "").strip().lower() == "repo_qna"
    return {
        "case_id": case_id,
        "question": question,
        "backend_intent": backend_intent,
        "backend_ok": backend_ok,
        "backend_answer": backend_answer,
        "evidence_paths": list(evidence_paths or []),
        "cursor_completed": cursor_correct is not None,
        "cursor_correct": bool(cursor_correct),
        "cursor_reason": cursor_reason,
        "failure_reason": failure_reason,
        "classification": "PASS" if backend_ok and cursor_correct else "QNA_ROUTING_FAILURE",
    }
