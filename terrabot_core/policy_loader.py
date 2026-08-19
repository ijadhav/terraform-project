from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List

from terrabot_core.filesystem import read_text
from terrabot_core.models import EvidenceItem, PolicyResult, RepoProfile, WorkflowProfile, unique_preserve_order

_DEFAULT_RULES = [
    "Use repository context for style, placement, module sources, variable shape, and tfvars layout.",
    "Use company policy for mandatory controls when repo examples are weaker than policy.",
    "Do not invent secrets, tenant IDs, subscription IDs, account IDs, ARNs, object IDs, connection strings, subnet IDs, or private endpoint IDs.",
    "Do not create public network exposure unless the user explicitly asks and policy allows it.",
    "For storage resources, default to encryption, private access, public nested items disabled, and shared access keys disabled where the module supports it.",
    "Preserve existing Terraform formatting and avoid unrelated file changes.",
    "Generated files must cite source paths used from retrieved evidence.",
]

_SECRET_PATTERNS = [
    re.compile(r"(?i)(client_secret|password|private_key|sas_token|connection_string)\s*=\s*['\"][^'\"]+['\"]"),
    re.compile(r"(?i)DefaultEndpointsProtocol=.*AccountKey="),
]


def _read_policy_files(workspace: Path, policy_files: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for relative in policy_files:
        path = workspace / relative
        text = read_text(path)
        if text:
            out[relative] = text[:5000]
    return out


def load_policy_rules(workspace: str, profile: RepoProfile) -> Dict[str, object]:
    workspace_path = Path(workspace).expanduser().resolve()
    rules = list(_DEFAULT_RULES)
    explicit_file = workspace_path / ".terrabot" / "policy.json"
    source_files: List[str] = []
    if explicit_file.exists():
        try:
            payload = json.loads(explicit_file.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                extra_rules = payload.get("rules")
                if isinstance(extra_rules, list):
                    rules.extend(str(rule) for rule in extra_rules)
                    source_files.append(".terrabot/policy.json")
        except Exception:
            pass
    policy_texts = _read_policy_files(workspace_path, profile.policy_files)
    source_files.extend(policy_texts.keys())
    return {
        "rules": unique_preserve_order(rules),
        "source_files": unique_preserve_order(source_files),
        "repo_policy_snippets": policy_texts,
    }


def evaluate_policy(prompt: str, profile: RepoProfile, workflow: WorkflowProfile, evidence: List[EvidenceItem], workspace: str) -> PolicyResult:
    pack = load_policy_rules(workspace, profile)
    rules = list(pack.get("rules") or [])
    source_files = list(pack.get("source_files") or [])
    warnings: List[str] = []
    blocking: List[str] = []
    text = (prompt or "").lower()

    if workflow.resource_type == "storage_account":
        warnings.append("Storage account changes must preserve private access, encryption, non-public containers, and existing module conventions.")
        if "public" in text and "private" not in text:
            blocking.append("The request asks for public storage exposure. Company policy requires explicit approval and safer design details before generating code.")

    if workflow.cloud == "azure" and workflow.resource_type in {"storage_account", "key_vault", "mysql", "app_service", "function_app"}:
        warnings.append("Azure PaaS resources should use private networking/private endpoints unless the request includes an approved exception.")

    for item in evidence:
        for pattern in _SECRET_PATTERNS:
            if pattern.search(item.snippet or ""):
                blocking.append(f"Retrieved evidence may contain sensitive values in {item.path}; generation is blocked until the file is excluded or redacted.")
                break

    if workflow.needs_clarification:
        warnings.append("Workflow inference has unresolved questions; Terrabot should ask those before generating a patch.")

    return PolicyResult(
        allowed=not blocking,
        blocking_issues=unique_preserve_order(blocking),
        warnings=unique_preserve_order(warnings),
        rules_applied=unique_preserve_order(rules),
        source_files=unique_preserve_order(source_files),
    )
