"""Remote GitHub mutation verification for read-only Cursor Cloud Agent runs.

Cursor's terminal ``git.branches`` field is execution metadata, not proof that a
remote branch was pushed.  The authoritative check is GitHub remote state.
"""
from __future__ import annotations

import os
import re
from typing import Any, Mapping, Sequence

import requests


def _github_token() -> str:
    return str(
        os.getenv("TERRABOT_GITHUB_TOKEN")
        or os.getenv("GITHUB_TOKEN")
        or os.getenv("GH_TOKEN")
        or ""
    ).strip()


def _repo_identity(repo_url: str) -> tuple[str, str]:
    value = str(repo_url or "").strip().rstrip("/")
    match = re.search(r"github\.com[/:]([^/]+)/([^/]+?)(?:\.git)?$", value, re.IGNORECASE)
    if not match:
        return "", ""
    return match.group(1), match.group(2)


def snapshot_remote_branches(
    repos: Sequence[Mapping[str, Any]],
    *,
    http_client: Any = requests,
) -> dict[str, dict[str, str]]:
    """Return ``repo_url -> {branch: sha}`` for the current GitHub remote heads.

    An empty result means remote verification is unavailable (normally because
    no GitHub token is configured).  Callers should log that state but must not
    reinterpret Cursor-local branch metadata as a remote push.
    """
    token = _github_token()
    if not token:
        return {}
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "terrabot-cursor-readonly/1.0",
    }
    result: dict[str, dict[str, str]] = {}
    for repo in repos or []:
        repo_url = str(repo.get("url") or "").strip().rstrip("/")
        owner, name = _repo_identity(repo_url)
        if not owner or not name:
            continue
        branches: dict[str, str] = {}
        for page in range(1, 11):
            response = http_client.get(
                f"https://api.github.com/repos/{owner}/{name}/branches",
                headers=headers,
                params={"per_page": 100, "page": page},
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json() or []
            if not isinstance(payload, list):
                break
            for item in payload:
                if not isinstance(item, Mapping):
                    continue
                branch = str(item.get("name") or "").strip()
                commit = item.get("commit") if isinstance(item.get("commit"), Mapping) else {}
                sha = str(commit.get("sha") or "").strip()
                if branch:
                    branches[branch] = sha
            if len(payload) < 100:
                break
        result[repo_url] = branches
    return result


def cursor_reported_remote_mutations(
    terminal: Mapping[str, Any],
    before: Mapping[str, Mapping[str, str]],
    after: Mapping[str, Mapping[str, str]],
) -> list[dict[str, str]]:
    """Return verified remote mutations among branches reported by Cursor."""
    git = terminal.get("git") if isinstance(terminal.get("git"), Mapping) else {}
    reported = git.get("branches") if isinstance(git, Mapping) else []
    if not isinstance(reported, list) or not before or not after:
        return []

    mutations: list[dict[str, str]] = []
    for item in reported:
        if not isinstance(item, Mapping):
            continue
        branch = str(item.get("branch") or "").strip()
        raw_repo = str(item.get("repoUrl") or item.get("repo") or "").strip()
        if not branch:
            continue
        owner, name = _repo_identity(raw_repo)
        candidates = []
        if owner and name:
            candidates.extend([
                f"https://github.com/{owner}/{name}",
                f"http://github.com/{owner}/{name}",
            ])
        candidates.extend([key for key in after if key.endswith(f"/{name}") and name] if name else [])
        repo_key = next((key for key in candidates if key in after), "")
        if not repo_key and len(after) == 1:
            repo_key = next(iter(after))
        if not repo_key:
            continue
        before_sha = str((before.get(repo_key) or {}).get(branch) or "")
        after_sha = str((after.get(repo_key) or {}).get(branch) or "")
        if after_sha and after_sha != before_sha:
            mutations.append({
                "repository": repo_key,
                "branch": branch,
                "before_sha": before_sha,
                "after_sha": after_sha,
            })
    return mutations
