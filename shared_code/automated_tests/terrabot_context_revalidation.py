"""Revalidate stale repository-context records against current live repository evidence."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from shared_code import repository_context

# Records created/updated within this window are skipped by revalidation. A
# commit landing anywhere in a large, actively-developed repository marks
# every previously-stored record "stale" (evidence_commit_sha != HEAD) even
# when the specific evidenced file/lines never changed. Without this grace
# period, a background revalidation sweep can invalidate a repository-context
# record within seconds of it being created (e.g. by the same request/test
# turn that just stored it), before anything downstream ever gets a chance to
# reuse it. That race was observed invalidating Phase 1 test context before
# Phase 2 could reuse it, and it degrades production accuracy the same way.
_REVALIDATION_GRACE_PERIOD_SECONDS = 900


def _seconds_since(timestamp: str) -> float | None:
    text = str(timestamp or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - parsed).total_seconds()


def _normalize_for_match(text: str) -> str:
    # Collapse whitespace and ignore quote-style/case differences that do not
    # change the underlying assignment (e.g. terraform fmt reformatting,
    # single vs double quotes) so a merely reformatted line is not treated as
    # "the excerpt is gone".
    collapsed = " ".join(str(text or "").split())
    return collapsed.replace('"', "'").casefold()


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
    stats = {"checked": 0, "refreshed": 0, "invalidated": 0, "unchanged": 0, "skipped_recent": 0, "skipped_fetch_error": 0}

    def fetcher(owner: str, repo: str, path: str, ref: str) -> str | None:
        return core.github_get_file_content_by_repo(owner, repo, path, ref=ref)

    for item in result.get("results") or []:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "active").strip().lower()
        if not item.get("stale") and status != "conflicted":
            continue
        age_seconds = _seconds_since(str(item.get("updated_at") or item.get("created_at") or ""))
        if age_seconds is not None and age_seconds < _REVALIDATION_GRACE_PERIOD_SECONDS:
            stats["skipped_recent"] += 1
            continue
        stats["checked"] += 1
        evidence = [entry for entry in (item.get("evidence") or []) if isinstance(entry, dict)]
        still_valid = False
        fetch_failed = False
        for entry in evidence:
            path = str(entry.get("path") or "").strip()
            excerpt = str(entry.get("excerpt") or "").strip()
            if not path or not excerpt:
                continue
            content = fetcher(repo_owner, repo_name, path, current_commit_sha or branch)
            if content is None:
                # A fetch failure (transient GitHub/API error, rate limit,
                # etc.) is not evidence that the excerpt is gone. Treating it
                # as "not found" was invalidating otherwise-valid records on
                # transient errors. Skip this record this cycle instead.
                fetch_failed = True
                continue
            if _normalize_for_match(excerpt) in _normalize_for_match(content):
                still_valid = True
                break
        if not still_valid and fetch_failed:
            stats["skipped_fetch_error"] += 1
            continue
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
