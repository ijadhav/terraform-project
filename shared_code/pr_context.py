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
LOGGER.setLevel(logging.INFO)

GITHUB_API = "https://api.github.com"
DEFAULT_TIMEOUT = 15
MAX_PULL_REQUESTS_FETCHED = 40

_STOPWORDS = {
    # grammar / generic request words
    "the", "a", "an", "and", "or", "for", "to", "in", "on", "of", "is",
    "are", "with", "using", "please", "can", "you", "existing", "current",
    "this", "that", "terraform", "infra", "infrastructure", "request", "change",
    "changes", "feature", "resource", "service", "setup", "config", "configuration",
    # action words are intentionally non-discriminating for PR relevance
    "create", "created", "add", "added", "new", "enable", "enabled", "disable",
    "disabled", "remove", "removed", "delete", "deleted", "update", "updated",
    "modify", "modified", "fix", "fixed", "turn", "switch", "decommission",
    # cloud/environment words must never make two otherwise unrelated PRs match
    "aws", "azure", "prod", "production", "dev", "development", "nonprod", "non",
    "environment", "environments", "env", "main", "branch", "draft", "pull", "pr",
}


def _is_environment_token(token: str) -> bool:
    token = str(token or "").lower()
    return bool(
        re.fullmatch(r"(?:us|eu|ca|ap|uk|au|sa)\d+(?:dr)?", token)
        or re.fullmatch(r"(?:mini)?dev\d*", token)
        or re.fullmatch(r"(?:prod|prd|npr|sbx|uat|stage|stg)\d*", token)
        or token in {"global", "observe", "sqlstaging", "devops"}
    )



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
        LOGGER.warning(
            "pr_context: cannot list pull requests, owner/repo missing: owner=%r repo=%r", owner, repo
        )
        return []
    url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls"
    token_configured = bool((token or os.getenv("GITHUB_TOKEN") or "").strip())
    LOGGER.info(
        "pr_context: searching for pull requests repo=%s/%s state=%s token_configured=%s",
        owner, repo, state, token_configured,
    )
    try:
        response = requests.get(
            url,
            headers=_auth_headers(token),
            params={"state": state, "per_page": min(max(per_page, 1), 100), "sort": "updated", "direction": "desc"},
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        pull_requests = payload if isinstance(payload, list) else []
        draft_count = sum(1 for pr in pull_requests if isinstance(pr, dict) and pr.get("draft"))
        LOGGER.info(
            "pr_context: fetched %s pull request(s) for %s/%s (%s draft)",
            len(pull_requests), owner, repo, draft_count,
        )
        return pull_requests
    except Exception as exc:
        LOGGER.warning(
            "pr_context: unable to list pull requests for %s/%s status=%s error=%s",
            owner, repo, getattr(getattr(exc, "response", None), "status_code", "n/a"), exc,
        )
        return []


def _tokenize(text: str) -> set[str]:
    """Return semantic PR-match tokens, splitting branch/flag compounds.

    Generic actions and environment labels are removed before scoring so a PR
    cannot be deemed related merely because both requests say "disable" or
    mention the same hub such as us1/us2.
    """
    normalized = str(text or "").lower().replace("_", " ").replace("-", " ")
    aliases = {
        "patching": "patch",
        "patches": "patch",
        "rabbitmq": "cloudamqp",
    }
    tokens: set[str] = set()
    for raw in re.findall(r"[a-z0-9]{3,}", normalized):
        token = aliases.get(raw, raw)
        if token in _STOPWORDS or _is_environment_token(token):
            continue
        tokens.add(token)
    return tokens


def _pull_request_token_sets(pull_request: dict) -> tuple[set[str], set[str], set[str]]:
    title = _tokenize(str(pull_request.get("title") or ""))
    branch = _tokenize(str((pull_request.get("head") or {}).get("ref") or ""))
    body = _tokenize(str(pull_request.get("body") or ""))
    return title, branch, body


def _score_pull_request(prompt_tokens: set[str], pull_request: dict) -> tuple[int, set[str], set[str]]:
    title_tokens, branch_tokens, body_tokens = _pull_request_token_sets(pull_request)
    strong_overlap = prompt_tokens & (title_tokens | branch_tokens)
    body_overlap = prompt_tokens & body_tokens

    # Title/branch overlap is strong evidence. Body-only overlap is accepted
    # only when at least two distinct semantic request terms agree, which
    # avoids one incidental word surfacing an unrelated PR.
    score = 0
    score += 10 * len(prompt_tokens & title_tokens)
    score += 8 * len(prompt_tokens & branch_tokens)
    score += 4 * len(body_overlap)
    return score, strong_overlap, body_overlap


def match_pull_requests_for_prompt(
    prompt: str,
    pull_requests: List[dict],
    max_matches: int = 5,
    min_score: int = 8,
) -> List[dict]:
    """Return only resource-semantically related pull requests.

    Generic action words and environment labels are ignored. A match requires
    either a meaningful token in the PR title/branch or at least two meaningful
    request tokens in the PR body. This prevents matches driven only by words
    such as enable/disable/create/us1/us2.
    """
    prompt_tokens = _tokenize(prompt)
    if not prompt_tokens:
        return []
    scored = []
    for pull_request in pull_requests:
        if not isinstance(pull_request, dict):
            continue
        score, strong_overlap, body_overlap = _score_pull_request(prompt_tokens, pull_request)
        relevant = bool(strong_overlap) or len(body_overlap) >= 2
        if relevant and score >= min_score:
            scored.append((score, len(strong_overlap), len(body_overlap), pull_request))
    scored.sort(key=lambda item: (-item[0], -item[1], -item[2]))
    matches = [item[3] for item in scored[:max_matches]]
    LOGGER.info(
        "pr_context: strictly matched %s of %s PR(s) prompt_tokens=%s best_score=%s",
        len(matches), len(pull_requests), sorted(prompt_tokens)[:10],
        scored[0][0] if scored else 0,
    )
    return matches

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
    LOGGER.info(
        "pr_context: duplicate-work check starting repo=%s/%s cloud=%s prompt_preview=%r",
        owner, repo, cloud or "", str(prompt or "")[:120],
    )
    pull_requests = list_open_pull_requests(owner, repo, token=token)
    matches = match_pull_requests_for_prompt(prompt, pull_requests, max_matches=max_matches)
    summaries = [_summarize_pull_request(pr) for pr in matches]

    if not summaries:
        LOGGER.info(
            "pr_context: no related pull request found repo=%s/%s cloud=%s (checked %s open PR(s))",
            owner, repo, cloud or "", len(pull_requests),
        )
        return {"matches": [], "context_block": ""}

    LOGGER.info(
        "pr_context: found %s related pull request(s) repo=%s/%s cloud=%s numbers=%s draft_flags=%s",
        len(summaries), owner, repo, cloud or "",
        [item["number"] for item in summaries],
        [item["draft"] for item in summaries],
    )

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
