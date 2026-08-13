"""Pull-request-aware context for Terrabot chat and infrastructure requests.

Feature: users frequently ask infrastructure questions ("has anyone already
added a storage account for the checkout service in prd?") or make requests
that overlap with work already in flight in an open pull request. This module
lets the backend look up already-raised pull requests on the relevant
cloud's repository, score them for relevance against the current prompt, and
build a compact context block the Foundry agent can use to ground its
answer instead of claiming ignorance or re-proposing duplicate work.

The module makes its own GitHub REST calls (rather than depending on
``shared_code.terrabot_service``) so it can be imported by that module
without creating an import cycle, and so it stays easily unit testable.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional

import requests

LOGGER = logging.getLogger("terrabot.pr_context")

GITHUB_API = "https://api.github.com"
DEFAULT_TIMEOUT = 15
MAX_PULL_REQUESTS_FETCHED = 40

_STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "to", "in", "on", "of", "is",
    "are", "with", "using", "create", "add", "new", "please", "can",
    "you", "existing", "current", "this", "that", "terraform", "infra",
    "infrastructure",
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


def list_open_pull_requests(
    owner: str,
    repo: str,
    token: Optional[str] = None,
    state: str = "open",
    per_page: int = MAX_PULL_REQUESTS_FETCHED,
) -> List[dict]:
    """Return open (or ``state``) pull requests for one GitHub repository.

    Best-effort: network/auth failures are logged and an empty list is
    returned so PR context is purely additive and never blocks a request.
    """
    owner = str(owner or "").strip()
    repo = str(repo or "").strip()
    if not owner or not repo:
        return []
    url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls"
    try:
        response = requests.get(
            url,
            headers=_auth_headers(token),
            params={"state": state, "per_page": min(max(per_page, 1), 100), "sort": "updated", "direction": "desc"},
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, list) else []
    except Exception as exc:
        LOGGER.warning("Unable to list pull requests for %s/%s: %s", owner, repo, exc)
        return []


def _tokenize(text: str) -> set[str]:
    tokens = {token for token in re.findall(r"[a-z0-9_-]{3,}", str(text or "").lower())}
    return {token for token in tokens if token not in _STOPWORDS}


def _score_pull_request(prompt_tokens: set[str], pull_request: dict) -> int:
    title = str(pull_request.get("title") or "")
    body = str(pull_request.get("body") or "")
    branch = str((pull_request.get("head") or {}).get("ref") or "")
    haystack_title = _tokenize(title)
    haystack_branch = _tokenize(branch)
    haystack_body = _tokenize(body)

    score = 0
    score += 6 * len(prompt_tokens & haystack_title)
    score += 4 * len(prompt_tokens & haystack_branch)
    score += 2 * len(prompt_tokens & haystack_body)
    return score


def match_pull_requests_for_prompt(
    prompt: str,
    pull_requests: List[dict],
    max_matches: int = 5,
    min_score: int = 1,
) -> List[dict]:
    """Rank pull requests by keyword overlap with ``prompt``.

    Returns the highest scoring pull requests (score >= ``min_score``),
    best first. Pure function — no network calls — so it is easy to unit
    test independent of GitHub access.
    """
    prompt_tokens = _tokenize(prompt)
    if not prompt_tokens:
        return []
    scored = []
    for pull_request in pull_requests:
        if not isinstance(pull_request, dict):
            continue
        score = _score_pull_request(prompt_tokens, pull_request)
        if score >= min_score:
            scored.append((score, pull_request))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in scored[:max_matches]]


def _summarize_pull_request(pull_request: dict) -> Dict[str, Any]:
    return {
        "number": pull_request.get("number"),
        "title": str(pull_request.get("title") or "").strip(),
        "author": str((pull_request.get("user") or {}).get("login") or "").strip(),
        "branch": str((pull_request.get("head") or {}).get("ref") or "").strip(),
        "base": str((pull_request.get("base") or {}).get("ref") or "").strip(),
        "state": str(pull_request.get("state") or "").strip(),
        "draft": bool(pull_request.get("draft")),
        "url": str(pull_request.get("html_url") or "").strip(),
        "updated_at": str(pull_request.get("updated_at") or "").strip(),
        "body_excerpt": re.sub(r"\s+", " ", str(pull_request.get("body") or "")).strip()[:400],
    }


def build_pr_context_block(
    prompt: str,
    owner: str,
    repo: str,
    token: Optional[str] = None,
    max_matches: int = 5,
    cloud: str = "",
) -> Dict[str, Any]:
    """Fetch open pull requests for one repo and match them to ``prompt``.

    Returns a dict with:
        - ``matches``: list of summarized matched pull requests (best first)
        - ``context_block``: a formatted string ready to attach to the agent
          input, or "" when there is nothing relevant.
    """
    pull_requests = list_open_pull_requests(owner, repo, token=token)
    matches = match_pull_requests_for_prompt(prompt, pull_requests, max_matches=max_matches)
    summaries = [_summarize_pull_request(pr) for pr in matches]

    if not summaries:
        return {"matches": [], "context_block": ""}

    lines = [
        "OPEN PULL REQUEST CONTEXT"
        + (f" (cloud={cloud})" if cloud else "")
        + f" repo={owner}/{repo}: the pull requests below are already raised "
        "by users on this repository and appear related to the current "
        "request based on keyword overlap. Use them to avoid proposing "
        "duplicate work, to answer questions about in-flight changes, and "
        "to reference existing branches/PRs when relevant. Verify current "
        "file contents against the live repository before generating code; "
        "do not assume a PR has already merged.",
    ]
    for item in summaries:
        lines.append(
            f"- PR #{item['number']} \"{item['title']}\" by {item['author'] or 'unknown'} "
            f"(branch `{item['branch']}` -> `{item['base']}`, {item['state']}"
            f"{', draft' if item['draft'] else ''}): {item['url']}"
            + (f" — {item['body_excerpt']}" if item["body_excerpt"] else "")
        )

    return {"matches": summaries, "context_block": "\n".join(lines)}


def build_multi_repo_pr_context_block(
    prompt: str,
    owner: str,
    repos_by_cloud: Dict[str, str],
    token: Optional[str] = None,
    max_matches: int = 5,
    requested_cloud: str = "",
) -> Dict[str, Any]:
    """Build PR context across one or more cloud repositories.

    ``repos_by_cloud`` maps cloud name (``"aws"``/``"azure"``/...) to the
    GitHub repository name. When ``requested_cloud`` is set, only that
    repository is queried; otherwise every configured repository is checked
    so a repository-agnostic infrastructure question can still find a
    relevant PR.
    """
    requested_cloud = str(requested_cloud or "").strip().lower()
    clouds = [requested_cloud] if requested_cloud and requested_cloud in repos_by_cloud else list(repos_by_cloud.keys())

    all_matches: List[dict] = []
    blocks: List[str] = []
    for cloud in clouds:
        repo = str(repos_by_cloud.get(cloud) or "").strip()
        if not repo:
            continue
        result = build_pr_context_block(prompt, owner, repo, token=token, max_matches=max_matches, cloud=cloud)
        if result["matches"]:
            all_matches.extend(result["matches"])
            blocks.append(result["context_block"])

    return {"matches": all_matches, "context_block": "\n\n".join(blocks)}
