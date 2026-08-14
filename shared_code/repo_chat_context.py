"""Live-repository grounding for ordinary (non-generation) chat questions.

The VS Code extension already lets Terrabot answer infrastructure questions
about the currently open workspace (``terrabot_core.service.ask_infrastructure``
/ ``explain_workflow``) because it has the full repository on disk. The Teams
bot previously answered plain-language questions with no repository grounding
at all (see ``shared_code.terrabot_service._teams_plain_chat_reply``), which
meant "what environments does the storage account module support?" could not
be answered accurately.

This module gives Teams (or any other transport) the same live-repository
ability: it walks the GitHub git tree for a repo/branch, scores files by
keyword overlap with the user's question, fetches the content of the best
matches, and returns a bounded context block. The retrieved file list is also
returned separately so callers can persist it (see
``shared_code.agent_memory_store``) as the "files searched/supplied" record
for this turn.
"""

from __future__ import annotations

import base64
import logging
import os
import re
from typing import Any, Dict, List, Optional

import requests

LOGGER = logging.getLogger("terrabot.repo_chat_context")

GITHUB_API = "https://api.github.com"
DEFAULT_TIMEOUT = 20
RELEVANT_EXTENSIONS = (".tf", ".tfvars", ".tf.json", ".md", ".yml", ".yaml")
MAX_TREE_ENTRIES = 4000
MAX_FILE_BYTES = 60_000

_STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "to", "in", "on", "of", "is",
    "are", "with", "using", "does", "what", "how", "why", "when", "which",
    "this", "that", "terraform", "infrastructure", "repository", "repo",
}


def _auth_headers(token: Optional[str]) -> Dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = (token or os.getenv("GITHUB_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def list_repo_tree_paths(
    owner: str,
    repo: str,
    branch: str = "main",
    token: Optional[str] = None,
) -> List[str]:
    """Return every file path in the repository at ``branch`` (best effort)."""
    owner = str(owner or "").strip()
    repo = str(repo or "").strip()
    branch = str(branch or "main").strip() or "main"
    if not owner or not repo:
        return []
    url = f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{branch}"
    try:
        response = requests.get(
            url,
            headers=_auth_headers(token),
            params={"recursive": "1"},
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        LOGGER.warning("Unable to list repo tree for %s/%s@%s: %s", owner, repo, branch, exc)
        return []

    entries = payload.get("tree") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return []
    paths = [
        str(entry.get("path") or "")
        for entry in entries
        if isinstance(entry, dict) and entry.get("type") == "blob" and entry.get("path")
    ]
    return paths[:MAX_TREE_ENTRIES]


def fetch_repo_file_content(
    owner: str,
    repo: str,
    path: str,
    ref: str = "main",
    token: Optional[str] = None,
) -> str:
    """Fetch one file's text content from the GitHub contents API."""
    owner = str(owner or "").strip()
    repo = str(repo or "").strip()
    path = str(path or "").strip().lstrip("/")
    if not owner or not repo or not path:
        return ""
    url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
    try:
        response = requests.get(
            url,
            headers=_auth_headers(token),
            params={"ref": ref or "main"},
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        LOGGER.warning("Unable to fetch repo file %s/%s:%s: %s", owner, repo, path, exc)
        return ""

    if not isinstance(payload, dict):
        return ""
    content_b64 = payload.get("content") or ""
    try:
        raw = base64.b64decode(content_b64)
    except Exception:
        return ""
    if len(raw) > MAX_FILE_BYTES:
        raw = raw[:MAX_FILE_BYTES]
    try:
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _tokenize(text: str) -> set[str]:
    tokens = {token for token in re.findall(r"[a-z0-9_-]{3,}", str(text or "").lower())}
    return {token for token in tokens if token not in _STOPWORDS}


def find_relevant_repo_files(
    prompt: str,
    file_paths: List[str],
    max_files: int = 6,
) -> List[str]:
    """Score repository paths by keyword overlap with ``prompt``.

    Pure function (no network) so it is easily unit tested. Only files with
    a Terraform/config-relevant extension and at least one keyword match are
    returned, best match first.
    """
    prompt_tokens = _tokenize(prompt)
    if not prompt_tokens:
        return []

    scored = []
    for path in file_paths:
        lowered = str(path or "").lower()
        if not lowered.endswith(RELEVANT_EXTENSIONS):
            continue
        path_tokens = _tokenize(lowered.replace("/", " ").replace(".", " "))
        overlap = prompt_tokens & path_tokens
        if not overlap:
            continue
        score = len(overlap) * 10
        if lowered.endswith(("main.tf", "variables.tf", ".tfvars")):
            score += 3
        scored.append((score, path))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [path for _, path in scored[:max_files]]


def build_live_repo_chat_context(
    prompt: str,
    owner: str,
    repo: str,
    branch: str = "main",
    token: Optional[str] = None,
    max_files: int = 6,
) -> Dict[str, Any]:
    """Build a bounded live-repository context block for a chat question.

    Returns a dict with:
        - ``paths``: the repository paths that were fetched as evidence
        - ``context_block``: formatted string ready to attach to the agent
          input, or "" when no relevant file was found.
    """
    tree_paths = list_repo_tree_paths(owner, repo, branch=branch, token=token)
    relevant_paths = find_relevant_repo_files(prompt, tree_paths, max_files=max_files)
    if not relevant_paths:
        return {"paths": [], "context_block": ""}

    sections = [
        f"LIVE REPOSITORY CONTEXT repo={owner}/{repo}@{branch}: the file "
        "excerpts below were fetched from the current repository head "
        "because they matched keywords in the user's question. Use them to "
        "answer accurately; do not guess at file contents that are not "
        "shown here.",
    ]
    fetched_paths: List[str] = []
    for path in relevant_paths:
        content = fetch_repo_file_content(owner, repo, path, ref=branch, token=token)
        if not content:
            continue
        fetched_paths.append(path)
        sections.append(f"--- {path} ---\n{content}")

    if not fetched_paths:
        return {"paths": [], "context_block": ""}

    return {"paths": fetched_paths, "context_block": "\n\n".join(sections)}
