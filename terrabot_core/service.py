from __future__ import annotations

from typing import Any, Dict, Optional

from terrabot_core.generator import generate_change_plan
from terrabot_core.models import WorkflowProfile, to_jsonable
from terrabot_core.policy_loader import evaluate_policy
from terrabot_core.retriever import retrieve_context
from terrabot_core.scanner import scan_repository
from terrabot_core.workflow_inferer import infer_workflow


def scan_workspace(workspace: str, prompt: str = "") -> Dict[str, Any]:
    profile = scan_repository(workspace)
    if prompt:
        workflow = infer_workflow(prompt, profile)
        evidence_prompt = prompt
    else:
        workflow = WorkflowProfile(
            workflow_type="repository_scan",
            confidence=1.0,
            cloud=profile.clouds[0] if len(profile.clouds) == 1 else None,
            target_files=profile.pipeline_files[:5] + profile.tfvars_files[:5],
            validation_commands=profile.validation_commands,
            apply_strategy="scan_only",
        )
        evidence_prompt = "terraform workflow pipeline tfvars variables provider"
    evidence = retrieve_context(workspace, evidence_prompt, profile, workflow, limit=10)
    return {
        "repo_profile": to_jsonable(profile),
        "workflow_profile": to_jsonable(workflow),
        "evidence": to_jsonable(evidence),
    }


def explain_workflow(workspace: str, prompt: str) -> Dict[str, Any]:
    profile = scan_repository(workspace)
    workflow = infer_workflow(prompt, profile)
    evidence = retrieve_context(workspace, prompt, profile, workflow, limit=10)
    policy = evaluate_policy(prompt, profile, workflow, evidence, workspace)
    return {
        "repo_profile": to_jsonable(profile),
        "workflow_profile": to_jsonable(workflow),
        "evidence": to_jsonable(evidence),
        "policy": to_jsonable(policy),
    }


def ask_infrastructure(workspace: str, prompt: str, thread_id: str = "") -> Dict[str, Any]:
    profile = scan_repository(workspace)
    workflow = infer_workflow(prompt, profile)
    evidence = retrieve_context(workspace, prompt, profile, workflow, limit=12)
    policy = evaluate_policy(prompt, profile, workflow, evidence, workspace)
    plan = generate_change_plan(workspace, prompt, profile, workflow, evidence, policy, thread_id=thread_id)
    result = to_jsonable(plan)
    # generator attaches non-dataclass passthrough fields (analysis,
    # user_fillable, thread_id) for the /api/generate handler; to_jsonable
    # serializes dataclass fields only, so merge them here. Fail-open.
    try:
        extras = getattr(plan, "passthrough", None)
        if isinstance(extras, dict) and isinstance(result, dict):
            for key, value in extras.items():
                result.setdefault(key, value)
    except Exception:
        pass
    return result
