"""Revalidate stale repository-context records against current live repository evidence."""
from __future__ import annotations

import hashlib
from typing import Any

from shared_code import repository_context


def revalidate_repository_context(
    core: Any,
    *,
    repo_owner: str,
    repo_name: str,
    branch: str,
    current_commit_sha: str,
    top_k: int = 25,
) -> dict[str, int]:
    result = repository_context.search_repository_context(
        repo_owner=repo_owner,
        repo_name=repo_name,
        query="*",
        current_commit_sha=current_commit_sha,
        top_k=top_k,
        include_conflicted=True,
    )
    stats = {"checked": 0, "refreshed": 0, "invalidated": 0, "unchanged": 0}

    def fetcher(owner: str, repo: str, path: str, ref: str) -> str | None:
        return core.github_get_file_content_by_repo(owner, repo, path, ref=ref)

    for item in result.get("results") or []:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "active").strip().lower()
        if not item.get("stale") and status != "conflicted":
            continue
        stats["checked"] += 1
        evidence = [entry for entry in (item.get("evidence") or []) if isinstance(entry, dict)]
        still_valid = False
        for entry in evidence:
            path = str(entry.get("path") or "").strip()
            excerpt = str(entry.get("excerpt") or "").strip()
            if not path or not excerpt:
                continue
            content = fetcher(repo_owner, repo_name, path, current_commit_sha or branch) or ""
            if " ".join(excerpt.split()) in " ".join(str(content).split()):
                still_valid = True
                break
        if not still_valid:
            action = repository_context.invalidate_repository_context(
                context_id=str(item.get("id") or ""),
                reason="Current repository evidence no longer contains the validated excerpt.",
                current_commit_sha=current_commit_sha,
            )
            if action.get("invalidated"):
                stats["invalidated"] += 1
            continue

        candidate = {
            "category": item.get("category"),
            "subject": item.get("subject"),
            "scope": item.get("scope"),
            "statement": item.get("statement"),
            "confidence": float(item.get("confidence") or 0.9),
            "validation_summary": "Automated repository-context revalidation refreshed evidence against current HEAD.",
            "evidence": evidence,
        }
        action = repository_context.add_repository_context(
            repo_owner=repo_owner,
            repo_name=repo_name,
            evidence_commit_sha=current_commit_sha,
            evidence_branch=branch,
            source_task_hash=hashlib.sha256(
                f"context-revalidation:{repo_owner}/{repo_name}:{current_commit_sha}:{item.get('id')}".encode()
            ).hexdigest(),
            candidate=candidate,
            evidence_fetcher=fetcher,
        )
        if action.get("stored"):
            stats["refreshed"] += 1
        else:
            stats["unchanged"] += 1
    return stats
