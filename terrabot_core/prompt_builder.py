from __future__ import annotations

from typing import Any, Dict, List

from terrabot_core.models import EvidenceItem, PolicyResult, RepoProfile, WorkflowProfile, to_jsonable


def _trim_profile(profile: RepoProfile) -> Dict[str, Any]:
    return {
        "root": profile.root,
        "repo_name": profile.repo_name,
        "languages": profile.languages,
        "iac_tools": profile.iac_tools,
        "clouds": profile.clouds,
        "providers": profile.providers,
        "terraform_roots": [to_jsonable(root) for root in profile.terraform_roots[:30]],
        "tfvars_files": profile.tfvars_files[:80],
        "environments": profile.environments,
        "pipeline_systems": profile.pipeline_systems,
        "pipeline_files": profile.pipeline_files[:40],
        "validation_commands": profile.validation_commands,
        "policy_files": profile.policy_files,
        "repo_conventions": profile.repo_conventions,
        "module_examples": [
            {
                "path": module.path,
                "name": module.name,
                "source": module.source,
                "start_line": module.start_line,
                "end_line": module.end_line,
            }
            for module in profile.modules[:40]
        ],
    }


def _trim_evidence(evidence: List[EvidenceItem]) -> List[Dict[str, Any]]:
    items = []
    for item in evidence:
        items.append(
            {
                "path": item.path,
                "reason": item.reason,
                "kind": item.kind,
                "score": item.score,
                "start_line": item.start_line,
                "end_line": item.end_line,
                "snippet": (item.snippet or "")[:3000],
            }
        )
    return items


def build_context_pack(
    prompt: str,
    profile: RepoProfile,
    workflow: WorkflowProfile,
    evidence: List[EvidenceItem],
    policy: PolicyResult,
) -> Dict[str, Any]:
    return {
        "user_request": prompt,
        "repo_profile": _trim_profile(profile),
        "workflow_profile": to_jsonable(workflow),
        "policy": to_jsonable(policy),
        "evidence": _trim_evidence(evidence),
        "generation_contract": {
            "output_format": "json",
            "required_top_level_keys": ["summary", "source_paths_used", "files", "questions", "validation_commands"],
            "file_contract": {
                "path": "repo-relative path",
                "operation": "add | modify | delete",
                "content": "full final file content for add/modify; omit for delete",
                "source_paths_used": "subset of retrieved evidence paths that support this file",
            },
            "hard_rules": [
                "Only change files required by the request.",
                "Do not invent missing IDs, secrets, subnet IDs, object IDs, subscription IDs, or connection strings.",
                "If required values are missing or ambiguous, return questions instead of files.",
                "Use source_paths_used for every generated file.",
                "Follow company policy even when repo examples are weaker.",
            ],
        },
    }
