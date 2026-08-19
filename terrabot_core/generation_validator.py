from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Tuple

from terrabot_core.models import EvidenceItem, PatchFile, PolicyResult, unique_preserve_order

_FORBIDDEN_VALUE_RE = [
    re.compile(r"(?i)(client_secret|password|private_key|sas_token|connection_string)\s*="),
    re.compile(r"(?i)AccountKey="),
]
_ID_LIKE_RE = re.compile(r"(?i)\b(subscription_id|tenant_id|object_id|client_id|subnet_id|account_id|arn)\s*=\s*['\"][^'\"]+['\"]")


def _is_safe_relative_path(path: str) -> bool:
    if not path or path.startswith("/"):
        return False
    parts = Path(path).parts
    return ".." not in parts


def validate_patch_files(files: Iterable[PatchFile], evidence: List[EvidenceItem], policy: PolicyResult) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    evidence_paths = {item.path for item in evidence}

    # Policy gating happens upstream (workflow/policy stage) and in the
    # /api/generate handler, which demotes findings about PRE-EXISTING repo
    # files to warnings. Re-applying raw blocking_issues here resurrected
    # demoted false positives, so only genuinely blocking issues that
    # survived demotion should gate — and those already blocked earlier.
    if policy and not policy.allowed:
        surviving = [
            b for b in (policy.blocking_issues or [])
            if not str(b).startswith("PRE-EXISTING")
        ]
        issues.extend(surviving)

    for file in files:
        if file.operation not in {"add", "create", "modify", "delete", "fill", "insert_into_block"}:
            issues.append(f"{file.path}: unsupported operation {file.operation}")
        if not _is_safe_relative_path(file.path):
            issues.append(f"{file.path}: path must be repo-relative and cannot traverse outside workspace")
        if file.operation in {"add", "create", "modify"} and file.content is None:
            issues.append(f"{file.path}: add/create/modify operations require full file content")
        if file.operation == "insert_into_block":
            if not getattr(file, "block", None) or not getattr(file, "lines", None):
                issues.append(f"{file.path}: insert_into_block requires block and non-empty lines")
        if file.operation == "fill" and not getattr(file, "replacements", None):
            issues.append(f"{file.path}: fill requires at least one replacement")
        if file.operation in {"add", "create", "modify"}:
            content = file.content or ""
            if any(pattern.search(content) for pattern in _FORBIDDEN_VALUE_RE):
                issues.append(f"{file.path}: generated content appears to contain a secret or connection string")
            if _ID_LIKE_RE.search(content) and not any(source in evidence_paths for source in file.source_paths_used):
                issues.append(f"{file.path}: generated content includes ID-like values without cited repo evidence")
        if not file.source_paths_used and file.operation not in {"delete", "fill", "insert_into_block"}:
            issues.append(f"{file.path}: generated file must cite source_paths_used")
        unknown_sources = [source for source in file.source_paths_used if source not in evidence_paths]
        if unknown_sources:
            issues.append(f"{file.path}: source_paths_used not present in retrieved evidence: {', '.join(unknown_sources)}")

    return (len(issues) == 0), unique_preserve_order(issues)
