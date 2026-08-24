from __future__ import annotations

import threading
from time import time
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from shared_code.terrabot_core_typing import (
        AFFIRMATIVE_REPLIES,
        AGENT_NAME,
        AZDO_API_VERSION,
        AZDO_ORG,
        AZDO_PAT,
        AZDO_PIPELINE_BRANCH,
        AZDO_PIPELINE_ID,
        AZDO_PROJECT,
        GITHUB_API,
        GITHUB_AWS_REPO,
        GITHUB_AZURE_APPROVED_CONSUMER_REPOS,
        GITHUB_AZURE_BASE_BRANCH,
        GITHUB_AZURE_REPO,
        GITHUB_OWNER,
        GITHUB_PR_COMMENT_MARKER,
        GITHUB_TOKEN,
        GITHUB_VENA_REPO,
        LOGGER,
        NEGATIVE_REPLIES,
        THREAD_PR_STATE,
        _ACTIVE_GITHUB_TOKEN,
        _extract_required_variable_names_from_text,
        _extract_tf_variable_block,
        _extract_tf_variable_names_from_text,
        _extract_top_level_hcl_assignment_names,
        _modular_pr_body_follows_template,
        _modular_pr_template_headings,
        _require_setting,
        _teams_generated_preserves_existing_lines,
        _terraform_safe_variable_name,
        _validate_hcl_content_complete,
        base64,
        build_branch_name,
        build_branch_prefix,
        build_grounded_azure_contexts,
        build_stable_folder,
        escape,
        extract_json_from_text,
        find_agent_reference,
        get_approved_azure_consumer_repos,
        get_project_client,
        github_base_branch_for_cloud,
        github_repo_for_cloud,
        json,
        normalize_cloud,
        normalize_repo_target,
        normalize_yes_no_reply,
        os,
        parse_branch_cycle,
        re,
        requests,
        state_bucket_for_target,
    )
    
def _require_github_token() -> str:
    token = (GITHUB_TOKEN or os.getenv("TERRABOT_GITHUB_TOKEN") or os.getenv("GH_TOKEN") or "").strip()
    if not token:
        raise RuntimeError(
            "GitHub authentication is not configured in the Function App. "
            "Set GITHUB_TOKEN as an Azure Key Vault-backed application setting."
        )
    return token


def _validate_workspace_repo(owner: str, repo: str) -> tuple[str, str]:
    owner = (owner or "").strip()
    repo = (repo or "").strip().removesuffix(".git")
    if not owner or not repo or not re.fullmatch(r"[A-Za-z0-9_.-]+", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]+", repo):
        raise ValueError("A valid GitHub owner and repository are required.")

    configured_owner = (GITHUB_OWNER or "").strip()
    allowed_repos = {
        value.strip()
        for value in (GITHUB_AWS_REPO, GITHUB_AZURE_REPO, GITHUB_VENA_REPO)
        if value and value.strip()
    }
    allowed_repos.update(
        value.strip()
        for value in (GITHUB_AZURE_APPROVED_CONSUMER_REPOS or "").split(",")
        if value.strip()
    )
    if configured_owner and owner.lower() != configured_owner.lower():
        raise PermissionError(f"Repository owner '{owner}' is not allowed.")
    if allowed_repos and repo not in allowed_repos:
        raise PermissionError(f"Repository '{repo}' is not configured for Terrabot.")
    return owner, repo


def _github_request_error(response: requests.Response, operation: str) -> RuntimeError:
    try:
        payload = response.json()
        message = payload.get("message") or response.text
        documentation_url = payload.get("documentation_url") or ""
    except Exception:
        message = response.text or response.reason
        documentation_url = ""
    suffix = f" Documentation: {documentation_url}" if documentation_url else ""
    return RuntimeError(f"{operation} failed: GitHub returned HTTP {response.status_code}: {message}.{suffix}")


def handle_workspace_branch_request(data: dict) -> dict:
    _require_github_token()
    owner, repo = _validate_workspace_repo(str(data.get("owner") or ""), str(data.get("repo") or ""))
    base = str(data.get("base") or "main").strip()
    branch = str(data.get("branch") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", base) or not re.fullmatch(r"[A-Za-z0-9._/-]+", branch):
        raise ValueError("Branch names may contain only letters, numbers, '.', '_', '/', and '-'.")
    if branch in {base, "main", "master"}:
        raise ValueError("The new branch must be different from the base branch.")

    headers = github_headers()
    base_response = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/ref/heads/{base}",
        headers=headers, timeout=30,
    )
    if not base_response.ok:
        raise _github_request_error(base_response, "Reading the base branch")
    base_sha = base_response.json()["object"]["sha"]

    create_response = requests.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/refs",
        headers=headers, json={"ref": f"refs/heads/{branch}", "sha": base_sha}, timeout=30,
    )
    if create_response.status_code not in {201, 422}:
        raise _github_request_error(create_response, "Creating the GitHub branch")
    if create_response.status_code == 422:
        exists_response = requests.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/git/ref/heads/{branch}",
            headers=headers, timeout=30,
        )
        if not exists_response.ok:
            raise _github_request_error(create_response, "Creating the GitHub branch")

    return {
        "ok": True,
        "branch": branch,
        "base": base,
        "branch_url": f"https://github.com/{owner}/{repo}/tree/{branch}",
        "compare_url": f"https://github.com/{owner}/{repo}/compare/{base}...{branch}",
        "reply": f"GitHub branch '{branch}' is ready.",
    }


def _github_pull_request_template(owner: str, repo: str, base: str, headers: dict) -> str:
    candidates = (
        ".github/PULL_REQUEST_TEMPLATE.md",
        ".github/pull_request_template.md",
        "PULL_REQUEST_TEMPLATE.md",
        "pull_request_template.md",
        "docs/PULL_REQUEST_TEMPLATE.md",
        "docs/pull_request_template.md",
    )
    for template_path in candidates:
        response = requests.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/contents/{template_path}",
            headers=headers,
            params={"ref": base},
            timeout=30,
        )
        if response.status_code == 404:
            continue
        if not response.ok:
            raise _github_request_error(response, "Reading the pull request template")
        payload = response.json() or {}
        encoded = str(payload.get("content") or "").replace("\n", "")
        if encoded:
            try:
                return base64.b64decode(encoded).decode("utf-8").strip()
            except (ValueError, UnicodeDecodeError) as exc:
                raise RuntimeError(f"Reading the pull request template failed: {exc}") from exc
    return ""


def _github_workspace_compare(owner: str, repo: str, base: str, head: str, headers: dict) -> dict:
    response = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/compare/{base}...{head}",
        headers=headers,
        timeout=30,
    )
    if not response.ok:
        raise _github_request_error(response, "Reading the pull request branch diff")

    payload = response.json() or {}
    files = []
    for item in payload.get("files") or []:
        if not isinstance(item, dict):
            continue
        files.append({
            "filename": item.get("filename") or "",
            "status": item.get("status") or "modified",
            "additions": int(item.get("additions") or 0),
            "deletions": int(item.get("deletions") or 0),
            "changes": int(item.get("changes") or 0),
            "patch": str(item.get("patch") or "")[:12000],
        })

    commits = []
    for item in payload.get("commits") or []:
        commit = (item or {}).get("commit") or {}
        message = str(commit.get("message") or "").strip()
        if message:
            commits.append(message.splitlines()[0][:240])

    return {
        "status": payload.get("status") or "",
        "ahead_by": int(payload.get("ahead_by") or 0),
        "behind_by": int(payload.get("behind_by") or 0),
        "total_commits": int(payload.get("total_commits") or len(commits)),
        "commits": commits[:50],
        "files": files,
    }


def _workspace_pr_changed_file_lines(compare: dict) -> list[str]:
    return [
        f"- `{item.get('filename')}` ({item.get('status')}, +{item.get('additions', 0)}/-{item.get('deletions', 0)})"
        for item in (compare.get("files") or [])
        if item.get("filename")
    ]


def _workspace_pr_template_headings(template: str) -> list[str]:
    return _modular_pr_template_headings(template)


def _workspace_pr_body_follows_template(template: str, body: str) -> bool:
    return _modular_pr_body_follows_template(template, body)

def _workspace_pr_section_content(heading: str, compare: dict, prompt: str) -> str:
    heading_text = re.sub(r"^#{1,6}\s+", "", heading or "").strip().lower()
    files = compare.get("files") or []
    changed_lines = _workspace_pr_changed_file_lines(compare)
    details = "\n".join(changed_lines) if changed_lines else "- No changed-file metadata was returned by GitHub."
    request = prompt or "Requested repository changes."

    if any(token in heading_text for token in ("description", "summary", "overview")):
        return (
            f"This pull request applies the requested change from the current branch. "
            f"It updates {len(files)} repository file(s) compared with the base branch."
        )
    if any(token in heading_text for token in ("change", "modified", "files")):
        return details
    if any(token in heading_text for token in ("why", "reason", "required", "motivation")):
        return request
    if any(token in heading_text for token in ("test", "validation", "verify")):
        return "- Run the repository validation and CI checks applicable to the changed files."
    if any(token in heading_text for token in ("deploy", "rollout", "release")):
        return "- Merge through the repository's normal review and deployment workflow."
    if any(token in heading_text for token in ("risk", "impact")):
        return "Review the current branch diff and repository CI results before merge."
    if any(token in heading_text for token in ("ticket", "issue", "reference")):
        return "Not applicable."
    if any(token in heading_text for token in ("checklist", "check list")):
        return "- [ ] Repository validation and CI checks have completed successfully."
    return "Not applicable."


def _workspace_pr_fill_template_fallback(template: str, compare: dict, prompt: str) -> str:
    """Fill the repository template without returning a blank template.

    This is used only when the Foundry metadata call and its repair call fail.
    Headings and checklist labels remain in repository order, while empty or
    instructional section bodies are replaced with grounded compare metadata.
    """
    template = (template or "").strip()
    headings = _workspace_pr_template_headings(template)
    if not template or not headings:
        changed_lines = _workspace_pr_changed_file_lines(compare)
        files = compare.get("files") or []
        description = (
            f"This pull request contains {len(files)} changed file(s) from the current branch compared with the base branch."
            if files else
            "This pull request contains the changes currently present on the source branch."
        )
        details = "\n".join(changed_lines) if changed_lines else "- No changed-file metadata was returned by GitHub."
        return (
            f"## Description\n\n{description}\n\n"
            f"## Changes\n\n{details}\n\n"
            f"## Why was this required?\n\n{prompt or 'Requested repository changes.'}\n\n"
            "## How to test?\n\n- Run the repository validation and CI checks applicable to the changed files.\n\n"
            "## Deployment plan\n\n- Merge through the repository's normal review and deployment workflow."
        )

    matches = list(re.finditer(r"(?m)^#{1,6}\s+.+$", template))
    output: list[str] = []
    preamble = template[:matches[0].start()].strip()
    if preamble:
        output.append(preamble)

    for index, match in enumerate(matches):
        heading = match.group(0).strip()
        section_end = matches[index + 1].start() if index + 1 < len(matches) else len(template)
        original_body = template[match.end():section_end].strip()
        preserved_checklist = [
            line.rstrip()
            for line in original_body.splitlines()
            if re.match(r"^\s*[-*]\s+\[[ xX]\]\s+", line)
        ]
        output.append(heading)
        output.append("")
        output.append(_workspace_pr_section_content(heading, compare, prompt))
        if preserved_checklist:
            output.append("")
            output.extend(preserved_checklist)
        output.append("")

    return "\n".join(output).strip()


def _workspace_pr_fallback_body(template: str, compare: dict, prompt: str) -> str:
    return _workspace_pr_fill_template_fallback(template, compare, prompt)


def _generate_workspace_pr_metadata(
    data: dict,
    owner: Optional[str],
    repo: Optional[str],
    base: str,
    head: str,
    headers: dict | None = None,
    compare_override: dict | None = None,
) -> tuple[str, str, dict]:
    owner = _require_setting(owner, "GITHUB_OWNER")
    repo = _require_setting(repo, "GitHub repository")
    template = str(data.get("template") or "").strip()
    if not template and headers:
        template = _github_pull_request_template(owner, repo, base, headers)

    compare = compare_override if compare_override is not None else _github_workspace_compare(owner, repo, base, head, headers or {})
    prompt = str(data.get("prompt") or "").strip()
    changed_files = [item.get("filename") for item in compare.get("files") or [] if item.get("filename")]

    metadata_request = {
        "task": "Generate pull request metadata from the exact current GitHub branch diff and fill the repository pull request template.",
        "repository": f"{owner}/{repo}",
        "base_branch": base,
        "head_branch": head,
        "user_request": prompt,
        "pull_request_template": template,
        "current_branch_compare": compare,
        "required_output": {
            "title": "A specific concise PR title describing only this compare diff.",
            "body": "The completed repository pull request template, with every template heading retained in its original order and each section filled from the current compare diff.",
        },
        "rules": [
            "Return valid JSON only with exactly the keys title and body.",
            "Use only current_branch_compare as evidence for the changes in this PR.",
            "Do not use prior conversation memory, earlier branches, repository-wide context, old PRs, or unrelated files.",
            "Do not claim a file, resource, pipeline, module, environment, deletion, or addition unless it is present in current_branch_compare.files or its patch.",
            "When pull_request_template is non-empty, copy its markdown structure into body and retain every heading, checklist label, and section in the same order.",
            "Fill each template section with concrete text grounded in current_branch_compare and user_request.",
            "Do not return a free-form PR description when a template is provided.",
            "Do not return the template blank and do not leave instructional placeholders or HTML instructions as the only section content.",
            "If a template section cannot be determined from the diff, write Not applicable or a restrained validation statement instead of inventing details.",
            "The title must not be the generic phrase Terrabot infrastructure changes.",
        ],
    }

    try:
        agent_text = call_named_agent(json.dumps(metadata_request, indent=2), AGENT_NAME)
        parsed = extract_json_from_text(agent_text)
        title = str(parsed.get("title") or "").strip()
        body = str(parsed.get("body") or "").strip()
        if not title or not body:
            raise ValueError("PR metadata agent returned an empty title or body.")
        if title.lower() == "terrabot infrastructure changes":
            raise ValueError("PR metadata agent returned the generic fallback title.")

        if template and not _workspace_pr_body_follows_template(template, body):
            repair_request = {
                "task": "Repair the pull request body so it follows the repository template exactly.",
                "repository": f"{owner}/{repo}",
                "base_branch": base,
                "head_branch": head,
                "user_request": prompt,
                "pull_request_template": template,
                "current_branch_compare": compare,
                "candidate_title": title,
                "candidate_body": body,
                "required_output": {"title": title, "body": "Completed template body"},
                "rules": [
                    "Return valid JSON only with exactly title and body.",
                    "Retain every markdown heading from pull_request_template verbatim and in the same order.",
                    "Retain template checklist labels and fill all sections using only current_branch_compare and user_request.",
                    "Do not return a free-form summary and do not leave the template blank.",
                ],
            }
            repaired_text = call_named_agent(json.dumps(repair_request, indent=2), AGENT_NAME)
            repaired = extract_json_from_text(repaired_text)
            repaired_title = str(repaired.get("title") or title).strip()
            repaired_body = str(repaired.get("body") or "").strip()
            if not repaired_body or not _workspace_pr_body_follows_template(template, repaired_body):
                raise ValueError("PR metadata agent did not preserve the repository pull request template after repair.")
            title, body = repaired_title, repaired_body

        return title[:240], body, compare
    except Exception as exc:
        print(f"Workspace PR metadata generation fallback used: {exc}")
        fallback_title = str(data.get("title") or "").strip()
        if not fallback_title or fallback_title.lower() == "terrabot infrastructure changes":
            if changed_files:
                fallback_title = f"Update {changed_files[0]}" if len(changed_files) == 1 else f"Update {len(changed_files)} repository files"
            else:
                fallback_title = "Update repository changes"
        return fallback_title[:240], _workspace_pr_fallback_body(template, compare, prompt), compare





def _workspace_compare_from_client(data: dict) -> dict:
    changed_files_text = str(data.get("changed_files") or "")
    diff_text = str(data.get("diff") or "")
    files = []
    for line in changed_files_text.splitlines():
        parts = line.strip().split("\t")
        if len(parts) < 2:
            continue
        status_code = parts[0].strip().upper()
        filename = parts[-1].strip()
        if not filename:
            continue
        status = {"A": "added", "D": "removed", "M": "modified", "R": "renamed"}.get(status_code[:1], "modified")
        files.append({
            "filename": filename,
            "status": status,
            "additions": 0,
            "deletions": 0,
            "changes": 0,
            "patch": diff_text[:12000],
        })
    return {
        "status": "ahead",
        "ahead_by": 0,
        "behind_by": 0,
        "total_commits": 0,
        "commits": [],
        "files": files,
        "diff_stat": str(data.get("diff_stat") or ""),
    }


def handle_workspace_pr_metadata_request(data: dict) -> dict:
    owner, repo = _validate_workspace_repo(str(data.get("owner") or ""), str(data.get("repo") or ""))
    head = str(data.get("head") or "").strip()
    base = str(data.get("base") or "main").strip()
    if not head:
        raise ValueError("The PR source branch is required.")

    title, body, compare = _generate_workspace_pr_metadata(
        data=data,
        owner=owner,
        repo=repo,
        base=base,
        head=head,
        compare_override=_workspace_compare_from_client(data),
    )
    return {
        "ok": True,
        "title": title,
        "body": body,
        "changed_files": [item.get("filename") for item in compare.get("files") or []],
    }

def _github_convert_pull_request_to_draft(owner: str, repo: str, pr: dict, headers: dict) -> dict:
    if pr.get("draft"):
        return pr

    node_id = str(pr.get("node_id") or "").strip()
    if not node_id:
        raise RuntimeError("GitHub did not return a pull request node_id required to convert the PR to draft.")

    query = """
mutation ConvertPullRequestToDraft($pullRequestId: ID!) {
  convertPullRequestToDraft(input: {pullRequestId: $pullRequestId}) {
    pullRequest {
      number
      url
      isDraft
    }
  }
}
"""
    response = requests.post(
        f"{GITHUB_API}/graphql",
        headers=headers,
        json={"query": query, "variables": {"pullRequestId": node_id}},
        timeout=30,
    )
    if not response.ok:
        raise _github_request_error(response, "Converting the pull request to draft")

    payload = response.json() or {}
    if payload.get("errors"):
        message = "; ".join(str(item.get("message") or item) for item in payload.get("errors") or [])
        raise RuntimeError(f"Converting the pull request to draft failed: {message}")

    refreshed = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr.get('number')}",
        headers=headers,
        timeout=30,
    )
    if not refreshed.ok:
        raise _github_request_error(refreshed, "Refreshing the draft pull request")
    return refreshed.json() or pr
def handle_workspace_pr_request(data: dict) -> dict:
    _require_github_token()
    owner, repo = _validate_workspace_repo(str(data.get("owner") or ""), str(data.get("repo") or ""))
    head = str(data.get("head") or "").strip()
    base = str(data.get("base") or "main").strip()
    if not head:
        raise ValueError("The PR source branch is required.")

    headers = github_headers()
    compare_url = f"https://github.com/{owner}/{repo}/compare/{base}...{head}"
    title, body, compare = _generate_workspace_pr_metadata(
        data=data,
        owner=owner,
        repo=repo,
        base=base,
        head=head,
        headers=headers,
    )

    existing_response = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls",
        headers=headers,
        params={"state": "open", "head": f"{owner}:{head}", "base": base},
        timeout=30,
    )
    if not existing_response.ok:
        raise _github_request_error(existing_response, "Checking for an existing pull request")
    existing = existing_response.json() or []
    if existing:
        pr = existing[0]
        update_response = requests.patch(
            f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr.get('number')}",
            headers=headers,
            json={"title": title, "body": body},
            timeout=30,
        )
        if not update_response.ok:
            raise _github_request_error(update_response, "Updating the existing pull request metadata")
        pr = update_response.json() or pr
        pr = _github_convert_pull_request_to_draft(owner, repo, pr, headers)
        return {
            "ok": True,
            "existing": True,
            "updated": True,
            "pr_number": pr.get("number"),
            "pr_url": pr.get("html_url"),
            "pr_title": title,
            "compare_url": compare_url,
            "changed_files": [item.get("filename") for item in compare.get("files") or []],
            "draft": bool(pr.get("draft")),
            "reply": "The existing draft pull request title and description were refreshed from the current branch diff.",
        }

    response = requests.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls",
        headers=headers,
        json={"title": title, "head": head, "base": base, "body": body, "draft": True},
        timeout=30,
    )
    if not response.ok:
        raise _github_request_error(response, "Creating the pull request")
    pr = response.json()
    return {
        "ok": True,
        "existing": False,
        "pr_number": pr.get("number"),
        "pr_url": pr.get("html_url"),
        "pr_title": title,
        "compare_url": compare_url,
        "changed_files": [item.get("filename") for item in compare.get("files") or []],
        "draft": bool(pr.get("draft")),
        "reply": "GitHub draft pull request created successfully from the current branch diff.",
    }

def github_headers():
    token = (_ACTIVE_GITHUB_TOKEN.get() or "").strip() or _require_github_token()
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _unique_non_empty(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values or []:
        item = str(value or "").strip().replace("refs/heads/", "")
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def github_resolve_base_branch_for_cloud(
    cloud: Any | None,
    branch_name: Optional[str] = None,
    repo_target: Optional[str] = None,
    workflow: Optional[str] = None,
) -> str:
    """Return a real base branch for the target repo.

    Some repositories still use a default branch other than `main`. Teams must
    not fail branch creation only because GITHUB_AWS_BASE_BRANCH defaults to
    main; resolve the live repository default branch and use it as a fallback.
    """
    repo = github_repo_for_cloud(cloud, repo_target=repo_target, workflow=workflow)
    configured_branch = (
        branch_name
        or github_base_branch_for_cloud(cloud, repo_target=repo_target, workflow=workflow)
        or ""
    ).strip().replace("refs/heads/", "")

    repo_response = requests.get(
        f"{GITHUB_API}/repos/{GITHUB_OWNER}/{repo}",
        headers=github_headers(),
        timeout=30,
    )
    if repo_response.status_code == 404:
        raise RuntimeError(
            f"GitHub repository was not found or the token cannot access it. "
            f"Check GITHUB_OWNER='{GITHUB_OWNER}', repo='{repo}', and that the "
            "GitHub App installation includes this repository with Contents read/write permission."
        )
    repo_response.raise_for_status()
    repo_payload = repo_response.json() or {}
    default_branch = str(repo_payload.get("default_branch") or "").strip()

    branch_candidates = _unique_non_empty([
        configured_branch,
        default_branch,
        "main",
        "master",
    ])

    checked = []
    for candidate in branch_candidates:
        checked.append(candidate)
        ref_response = requests.get(
            f"{GITHUB_API}/repos/{GITHUB_OWNER}/{repo}/git/ref/heads/{candidate}",
            headers=github_headers(),
            timeout=30,
        )
        if ref_response.ok:
            if configured_branch and candidate != configured_branch:
                LOGGER.warning(
                    "Configured base branch %s was not found for %s/%s; using live base branch %s.",
                    configured_branch,
                    GITHUB_OWNER,
                    repo,
                    candidate,
                )
            return candidate
        if ref_response.status_code != 404:
            raise _github_request_error(ref_response, "Reading the GitHub base branch")

    raise RuntimeError(
        f"No usable GitHub base branch was found for {GITHUB_OWNER}/{repo}. "
        f"Checked: {', '.join(checked)}. Repo default_branch='{default_branch or 'unknown'}'."
    )


def github_get_base_branch_sha(cloud: Any | None, branch_name: Optional[str] = None, repo_target: Optional[str] = None, workflow: Optional[str] = None):
    repo = github_repo_for_cloud(cloud, repo_target=repo_target, workflow=workflow)
    base_branch = github_resolve_base_branch_for_cloud(
        cloud,
        branch_name=branch_name,
        repo_target=repo_target,
        workflow=workflow,
    )

    url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{repo}/git/ref/heads/{base_branch}"
    response = requests.get(url, headers=github_headers(), timeout=30)
    response.raise_for_status()
    return response.json()["object"]["sha"]


def github_create_branch(cloud: Any | None, branch_name: str, base_sha: str, repo_target: Optional[str] = None, workflow: Optional[str] = None):
    repo = github_repo_for_cloud(cloud, repo_target=repo_target, workflow=workflow)
    url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{repo}/git/refs"
    payload = {"ref": f"refs/heads/{branch_name}", "sha": base_sha}
    response = requests.post(url, headers=github_headers(), json=payload, timeout=30)

    if response.status_code not in (201, 422):
        response.raise_for_status()


def github_get_file_sha(cloud: Any | None, path: str, branch: str, repo_target: Optional[str] = None, workflow: Optional[str] = None):
    repo = github_repo_for_cloud(cloud, repo_target=repo_target, workflow=workflow)

    url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{repo}/contents/{path}"
    response = requests.get(url, headers=github_headers(), params={"ref": branch}, timeout=30)

    if response.status_code == 404:
        return None

    response.raise_for_status()
    return response.json().get("sha")


def github_put_file(cloud: Any | None, path: str, content: str, branch: str, commit_message: str, repo_target: Optional[str] = None, workflow: Optional[str] = None):
    repo = github_repo_for_cloud(cloud, repo_target=repo_target, workflow=workflow)
    url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{repo}/contents/{path}"
    encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")

    payload = {
        "message": commit_message,
        "content": encoded_content,
        "branch": branch,
    }

    sha = github_get_file_sha(
        cloud,
        path,
        branch,
        repo_target=repo_target,
        workflow=workflow,
    )
    if sha:
        payload["sha"] = sha

    response = requests.put(url, headers=github_headers(), json=payload, timeout=30)
    response.raise_for_status()
    _github_invalidate_request_snapshot(GITHUB_OWNER, repo, branch)
    return response.json()


def _extract_top_level_tf_blocks(tf_content: str) -> list[dict]:
    text = tf_content or ""
    starts = list(re.finditer(
        r'(?m)^\s*(module|resource|data|locals|variable|output)\s+(?:"[^"]+"\s*){0,2}\{',
        text,
    ))

    blocks = []

    for match in starts:
        brace_start = text.find("{", match.end() - 1)
        if brace_start == -1:
            continue

        depth = 0
        in_string = False
        escape = False
        end_idx = -1

        for idx in range(brace_start, len(text)):
            ch = text[idx]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end_idx = idx + 1
                    break

        if end_idx == -1:
            continue

        block = text[match.start():end_idx].strip()
        header = text[match.start():text.find("{", match.end() - 1)].strip()
        blocks.append({
            "header": re.sub(r"\s+", " ", header),
            "block": block,
        })

    return blocks


def _merge_terraform_content_preserving_existing(existing_content: str, new_content: str) -> str:
    existing = (existing_content or "").replace("\r\n", "\n").rstrip()
    new = (new_content or "").replace("\r\n", "\n").rstrip()

    if not existing:
        return new + "\n"

    if not new:
        return existing + "\n"

    if existing.strip() == new.strip():
        return existing + "\n"

    # If the agent returned the full existing file plus additions, accept it.
    if existing.strip() in new.strip():
        return new + "\n"

    existing_headers = {
        block["header"]
        for block in _extract_top_level_tf_blocks(existing)
    }

    additions = []
    for block in _extract_top_level_tf_blocks(new):
        if block["header"] not in existing_headers:
            additions.append(block["block"])

    if not additions:
        # Do not replace an existing file with a smaller or unrelated generated file.
        return existing + "\n"

    return existing + "\n\n" + "\n\n".join(additions).rstrip() + "\n"


def _is_azure_consumer_variables_tf_path(
    cloud: str,
    path: str,
    repo_target: Optional[str] = None,
    workflow: Optional[str] = None,
) -> bool:
    normalized_path = (path or "").replace("\\", "/").strip("/")
    if normalized_path != "variables.tf" and not normalized_path.endswith("/variables.tf"):
        return False
    try:
        return (
            normalize_cloud(cloud) == "azure"
            and normalize_repo_target("azure", repo_target=repo_target, workflow=workflow) == "tf-azure-hub"
        )
    except Exception:
        return False


def _hcl_curly_brace_balance_for_write(hcl_content: str) -> int:
    """Return unmatched HCL curly-brace depth, ignoring quoted strings.

    This is used as a final write-time safety check for generated variables.tf
    content. It intentionally does not rewrite existing file contents; it only
    detects whether the generated final content is missing trailing closing
    braces before it is sent to GitHub.
    """
    depth = 0
    in_string = False
    escape_next = False

    for ch in hcl_content or "":
        if in_string:
            if escape_next:
                escape_next = False
            elif ch == "\\":
                escape_next = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1

    return depth


def _has_git_conflict_markers(content: str) -> bool:
    return bool(re.search(r'(?m)^(<<<<<<<|=======|>>>>>>>)', content or ""))


def _top_level_tf_block_matches(hcl_content: str) -> list[re.Match]:
    return list(re.finditer(
        r'(?m)^\s*(terraform|provider|module|resource|data|locals|variable|output)\b(?:\s+"[^"]+"){0,2}\s*\{',
        hcl_content or "",
    ))

def _top_level_tf_headers_for_modification(hcl_content: str) -> set[str]:
    headers = set()

    for match in _top_level_tf_block_matches(hcl_content or ""):
        header = match.group(0).rsplit("{", 1)[0].strip()
        header = re.sub(r"\s+", " ", header)
        if header:
            headers.add(header)

    return headers


def _find_balanced_curly_end(hcl_content: str, brace_start: int) -> int:
    """Return index just after the matching close brace line, or -1."""
    text = hcl_content or ""
    if brace_start < 0 or brace_start >= len(text) or text[brace_start] != "{":
        return -1

    depth = 0
    in_string = False
    escape_next = False

    for idx in range(brace_start, len(text)):
        ch = text[idx]
        if in_string:
            if escape_next:
                escape_next = False
            elif ch == "\\":
                escape_next = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                line_end = text.find("\n", idx + 1)
                return len(text) if line_end == -1 else line_end

    return -1


def _repair_unclosed_variable_blocks_in_variables_tf(content: str) -> str:
    """Close incomplete variable blocks before the next top-level block or EOF.

    This is the backend recovery path for the exact merge-conflict failure where
    an editor's "accept both changes" keeps the generated object type body but
    drops the final variable-block close brace. EOF-only repair is insufficient
    once another top-level block follows, so each variable block is repaired at
    its own boundary.
    """
    text = (content or "").replace("\r\n", "\n")
    if not text.strip():
        return text

    matches = _top_level_tf_block_matches(text)
    if not matches:
        return text

    output: list[str] = []
    cursor = 0
    changed = False

    for idx, match in enumerate(matches):
        if match.group(1) != "variable":
            continue

        brace_start = text.find("{", match.end() - 1)
        next_start = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        balanced_end = _find_balanced_curly_end(text, brace_start)

        if brace_start == -1 or (balanced_end != -1 and balanced_end <= next_start):
            continue

        segment = text[match.start():next_start]
        missing = _hcl_curly_brace_balance_for_write(segment)
        if missing < 0:
            raise ValueError(
                "Generated variables.tf has extra closing brace(s) inside a variable block; refusing to write malformed Terraform."
            )
        if missing == 0:
            continue

        output.append(text[cursor:next_start].rstrip())
        output.append("\n" + "\n".join("}" for _ in range(missing)))
        cursor = next_start
        changed = True

    if not changed:
        return text

    output.append(text[cursor:])
    return "".join(output)


def _terrabot_marker_line_re(variable_name: str = "") -> re.Pattern:
    name_part = re.escape(_terraform_safe_variable_name(variable_name)) if variable_name else r"[A-Za-z_][A-Za-z0-9_]*"
    return re.compile(rf'^\s*#\s*terrabot:(?:begin|end|close)-variable\s+{name_part}\s*$')


def _variable_block_spans_for_dedupe(tf_content: str) -> list[dict]:
    text = tf_content or ""
    matches = _top_level_tf_block_matches(text)
    spans: list[dict] = []

    for idx, match in enumerate(matches):
        if match.group(1) != "variable":
            continue

        name_match = re.match(r'\s*variable\s+"([^"\n]+)"\s*\{', text[match.start():match.end()], re.IGNORECASE)
        if not name_match:
            continue
        variable_name = _terraform_safe_variable_name(name_match.group(1))
        if not variable_name:
            continue

        brace_start = text.find("{", match.end() - 1)
        next_start = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        block_end = _find_balanced_curly_end(text, brace_start)
        if block_end == -1 or block_end > next_start:
            continue

        span_start = match.start()
        prev_line_start = text.rfind("\n", 0, span_start - 1) + 1 if span_start > 0 else 0
        prev_line = text[prev_line_start:span_start].strip()
        if _terrabot_marker_line_re(variable_name).match(prev_line):
            span_start = prev_line_start

        span_end = block_end
        while span_end < len(text):
            newline_offset = 1 if text.startswith("\n", span_end) else 0
            line_start = span_end + newline_offset
            line_end = text.find("\n", line_start)
            if line_end == -1:
                line_end = len(text)
                next_pos = line_end
            else:
                next_pos = line_end + 1
            line = text[line_start:line_end]
            if not line.strip() or _terrabot_marker_line_re(variable_name).match(line):
                span_end = next_pos
                continue
            break

        block_text = text[span_start:span_end]
        normalized = re.sub(r'(?m)^\s*#\s*terrabot:(?:begin|end|close)-variable\s+[^\n]+\n?', '', block_text)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        spans.append({
            "name": variable_name,
            "start": span_start,
            "end": span_end,
            "text": block_text,
            "normalized": normalized,
            "terrabot_marked": "terrabot:" in block_text,
        })

    return spans


def _dedupe_duplicate_variable_blocks_in_variables_tf(content: str) -> str:
    """Remove duplicate generated variable blocks left by accept-both merges.

    Terraform fails on duplicate variable declarations. We only remove a later
    duplicate when it is Terrabot-marked or byte-normalized equal to the first
    declaration. Different hand-written duplicate declarations are rejected.
    """
    text = (content or "").replace("\r\n", "\n")
    spans = _variable_block_spans_for_dedupe(text)
    if not spans:
        return text

    seen: dict[str, dict] = {}
    remove_ranges: list[tuple[int, int]] = []

    for span in spans:
        name = span["name"]
        if name not in seen:
            seen[name] = span
            continue

        first = seen[name]
        if span["terrabot_marked"] or first["terrabot_marked"] or span["normalized"] == first["normalized"]:
            remove_ranges.append((span["start"], span["end"]))
            continue

        raise ValueError(
            f'Generated variables.tf contains multiple different variable "{name}" declarations; resolve the duplicate before committing.'
        )

    if not remove_ranges:
        return text

    for start, end in sorted(remove_ranges, reverse=True):
        text = text[:start].rstrip() + "\n\n" + text[end:].lstrip("\n")

    return text.rstrip() + "\n"


def _repair_unclosed_variables_tf_content_for_write(
    existing_content: str | None,
    generated_content: str,
    path: str,
) -> str:
    """Return balanced variables.tf content or reject malformed Terraform.

    This fixes the conflict-resolution case where "accept both changes" keeps
    the generated object-type body but drops the final variable-block close
    brace. It also removes duplicate Terrabot-generated variable blocks that can
    be left by accepting both sides of an EOF append conflict.
    """
    del existing_content

    normalized_path = (path or "").replace("\\", "/").strip("/")
    if normalized_path != "variables.tf" and not normalized_path.endswith("/variables.tf"):
        return (generated_content or "").replace("\r\n", "\n").rstrip() + "\n"

    generated = (generated_content or "").replace("\r\n", "\n").rstrip()

    if not generated.strip():
        return "\n"

    if _has_git_conflict_markers(generated):
        raise ValueError(
            f"Generated {path} still contains Git conflict markers; resolve the conflict before committing."
        )

    generated = _repair_unclosed_variable_blocks_in_variables_tf(generated)

    balance = _hcl_curly_brace_balance_for_write(generated)

    if balance < 0:
        raise ValueError(
            f"Generated {path} has extra closing brace(s); refusing to write malformed Terraform."
        )

    if balance > 0:
        generated = generated.rstrip() + "\n" + "\n".join("}" for _ in range(balance))

    generated = _dedupe_duplicate_variable_blocks_in_variables_tf(generated)

    if _hcl_curly_brace_balance_for_write(generated) != 0:
        raise ValueError(
            f"Generated {path} is still unbalanced after variables.tf finalization; refusing to write malformed Terraform."
        )

    for match in re.finditer(
        r'(?m)^\s*variable\s+"([^"\n]+)"\s*\{',
        generated,
        re.IGNORECASE,
    ):
        variable_name = match.group(1).strip()
        if not variable_name:
            continue

        block = _extract_tf_variable_block(generated, variable_name)
        if not block:
            raise ValueError(
                f'Generated {path} contains an incomplete variable "{variable_name}" block; refusing to write malformed Terraform.'
            )

        if _hcl_curly_brace_balance_for_write(block) != 0:
            raise ValueError(
                f'Generated {path} contains an unbalanced variable "{variable_name}" block; refusing to write malformed Terraform.'
            )

    return generated.rstrip() + "\n"

def _validate_full_file_modification_preserves_existing(
    existing_content: str,
    generated_content: str,
    path: str,
) -> None:
    existing = (existing_content or "").replace("\r\n", "\n").strip()
    generated = (generated_content or "").replace("\r\n", "\n").strip()

    if not generated:
        raise ValueError(
            f"Generated modification for {path} is empty. "
            "Refusing to remove the whole file by accident."
        )

    if path.endswith(".tf"):
        existing_headers = _top_level_tf_headers_for_modification(existing)
        generated_headers = _top_level_tf_headers_for_modification(generated)

        if existing_headers:
            preserved = existing_headers & generated_headers
            removed = existing_headers - generated_headers
            added = generated_headers - existing_headers

            # This catches the exact bad case where the agent replaces:
            # module "password_policy" { ... }
            # with terraform/provider/resource scaffolding.
            if not preserved:
                raise ValueError(
                    f"Generated modification for {path} does not preserve any existing Terraform block. "
                    "Modification workflows must edit matched existing code, not replace the file with unrelated Terraform."
                )

            # A "modification" workflow tag does not always mean "edit only,
            # never add": legitimate creation-via-append requests (e.g.
            # "create a second GRS storage account under a new module
            # instance name", "add a second instance", or any
            # already-exists -> create-under-a-new-name follow-up) also get
            # written through this path because the target file already
            # exists on disk. Blanket-rejecting any added top-level block
            # broke that entire class of legitimate creation request.
            #
            # A new block is safe to accept as long as the write is provably
            # additive: nothing existing was removed, and every line of the
            # existing file still appears, unchanged and in order, inside the
            # generated content. That is exactly the shape of a legitimate
            # "append a new sibling resource/module" change. Only reject when
            # the addition looks like a destructive rewrite (existing blocks
            # were also removed, or existing content was not preserved
            # verbatim) — that is the real hallucinated-replacement failure
            # this check exists to catch.
            if added:
                if removed or not _teams_generated_preserves_existing_lines(existing, generated):
                    raise ValueError(
                        f"Generated modification for {path} introduces new top-level Terraform blocks "
                        f"({', '.join(sorted(added))}) without cleanly preserving the existing file. "
                        "A safe change must keep every existing line untouched and only append new "
                        "block(s); regenerate so the existing content is preserved exactly."
                    )

            # Allow targeted delete/update, but reject broad replacement.
            if len(removed) > max(3, len(existing_headers) // 2):
                raise ValueError(
                    f"Generated modification for {path} removes too many existing Terraform blocks. "
                    "The backend only allows targeted update/delete/fix edits."
                )

    if path.endswith(".tfvars"):
        try:
            existing_names = set(_extract_top_level_hcl_assignment_names(existing))
            generated_names = set(_extract_top_level_hcl_assignment_names(generated))
        except Exception:
            existing_names = set()
            generated_names = set()

        if existing_names:
            removed = existing_names - generated_names

            if len(removed) > max(3, len(existing_names) // 2):
                raise ValueError(
                    f"Generated modification for {path} removes too many existing tfvars assignments. "
                    "The backend only allows targeted variable value edits."
                )

def github_put_file_if_changed_stage1(
    cloud: str,
    path: str,
    content: str,
    branch: str,
    commit_message: str,
    repo_target: Optional[str] = None,
    workflow: Optional[str] = None,
):
    """Write Foundry-generated content exactly; never synthesize Terraform.

    The backend may compare, validate, and transport the agent's final file,
    but it must not merge blocks, repair braces, normalize tfvars, toggle
    Boolean values, or otherwise create/modify Terraform on the agent's behalf.
    """
    existing_content = github_get_file_content(
        cloud,
        path,
        branch,
        repo_target=repo_target,
        workflow=workflow,
    )
    final_content = str(content or "")

    normalized_existing = (existing_content or "").replace("\r\n", "\n").strip()
    normalized_new = final_content.replace("\r\n", "\n").strip()
    if existing_content is not None and normalized_existing == normalized_new:
        return {"changed": False, "path": path, "result": None}

    # Validation is allowed; mutation is not. Foundry must correct invalid HCL.
    if path.endswith((".tf", ".tfvars")):
        _validate_hcl_content_complete(path, final_content)
        if _has_git_conflict_markers(final_content):
            raise ValueError(f"Generated {path} contains Git conflict markers.")

    result = github_put_file(
        cloud=cloud,
        path=path,
        content=final_content,
        branch=branch,
        commit_message=commit_message,
        repo_target=repo_target,
        workflow=workflow,
    )
    return {"changed": True, "path": path, "result": result}
github_put_file_if_changed = github_put_file_if_changed_stage1

def github_create_pull_request(cloud: Any | None, branch_name: str, title: str, body: str, repo_target: Optional[str] = None, workflow: Optional[str] = None):
    repo = github_repo_for_cloud(cloud, repo_target=repo_target, workflow=workflow)
    base_branch = github_resolve_base_branch_for_cloud(cloud, repo_target=repo_target, workflow=workflow)
    url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{repo}/pulls"
    payload = {
        "title": title,
        "head": branch_name,
        "base": base_branch,
        "body": body,
    }
    response = requests.post(url, headers=github_headers(), json=payload, timeout=30)

    if response.status_code == 422:
        existing = github_find_pr_by_branch(
            cloud,
            branch_name,
            state="open",
            repo_target=repo_target,
            workflow=workflow,
        )
        if existing:
            return existing
        raise RuntimeError(
            "GitHub could not create a pull request for this branch. "
            "This usually happens when the branch already has a closed or merged PR, or when there are no new commits to open a PR."
        )

    response.raise_for_status()
    return response.json()



def github_find_pr_by_branch(cloud: Any | None, branch_name: str, state: str = "open", repo_target: Optional[str] = None, workflow: Optional[str] = None):
    repo = github_repo_for_cloud(cloud, repo_target=repo_target, workflow=workflow)
    base_branch = github_base_branch_for_cloud(cloud, repo_target=repo_target, workflow=workflow)

    url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{repo}/pulls"
    response = requests.get(
        url,
        headers=github_headers(),
        params={
            "state": state,
            "head": f"{GITHUB_OWNER}:{branch_name}",
            "base": base_branch,
        },
        timeout=30,
    )
    response.raise_for_status()
    prs = response.json()
    return prs[0] if prs else None


def github_branch_exists(cloud: Any | None, branch_name: str, repo_target: Optional[str] = None, workflow: Optional[str] = None) -> bool:
    repo = github_repo_for_cloud(cloud, repo_target=repo_target, workflow=workflow)

    url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{repo}/git/ref/heads/{branch_name}"
    response = requests.get(url, headers=github_headers(), timeout=30)

    if response.status_code == 404:
        return False

    response.raise_for_status()
    return True

def github_list_matching_branches(cloud: Any | None, prefix: str, repo_target: Optional[str] = None, workflow: Optional[str] = None):
    repo = github_repo_for_cloud(cloud, repo_target=repo_target, workflow=workflow)

    url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{repo}/git/matching-refs/heads/{prefix}"
    response = requests.get(url, headers=github_headers(), timeout=30)

    if response.status_code == 404:
        return []

    response.raise_for_status()
    refs = response.json() or []
    branches = []
    for item in refs:
        ref = item.get("ref", "")
        if ref.startswith("refs/heads/"):
            branches.append(ref.replace("refs/heads/", "", 1))
    return branches

def github_folder_exists(cloud: Any | None, path: str, branch: str, repo_target: Optional[str] = None, workflow: Optional[str] = None) -> bool:
    repo = github_repo_for_cloud(cloud, repo_target=repo_target, workflow=workflow)

    url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{repo}/contents/{path}"
    response = requests.get(url, headers=github_headers(), params={"ref": branch}, timeout=30)

    if response.status_code == 404:
        return False

    response.raise_for_status()
    return True


# Cross-request cache for relatively stable repository STRUCTURE only.
# File contents intentionally remain request-local so generation/validation always
# uses live repository bytes. Entries are keyed by owner/repo/ref/path and are
# invalidated whenever Terrabot writes to that repository/ref.
_GITHUB_STRUCTURE_CACHE: dict[tuple, tuple[float, Any]] = {}
_GITHUB_STRUCTURE_CACHE_LOCK = threading.RLock()
_GITHUB_REPO_TREE_TTL_SECONDS = max(30, int(os.getenv("TERRABOT_REPO_TREE_CACHE_TTL_SECONDS", "180")))
_GITHUB_DIRECTORY_STRUCTURE_TTL_SECONDS = max(30, int(os.getenv("TERRABOT_DIRECTORY_STRUCTURE_CACHE_TTL_SECONDS", "600")))
_GITHUB_MODULE_STRUCTURE_TTL_SECONDS = max(30, int(os.getenv("TERRABOT_MODULE_STRUCTURE_CACHE_TTL_SECONDS", "600")))
_GITHUB_REPO_METADATA_TTL_SECONDS = max(30, int(os.getenv("TERRABOT_REPO_METADATA_CACHE_TTL_SECONDS", "300")))
_GITHUB_STRUCTURE_CACHE_MAX_ENTRIES = max(128, int(os.getenv("TERRABOT_STRUCTURE_CACHE_MAX_ENTRIES", "4096")))


def _github_structure_cache_ttl(path: str = "", kind: str = "directory") -> int:
    normalized = str(path or "").strip("/")
    segments = {segment.lower() for segment in normalized.split("/") if segment}
    if kind == "repo":
        return _GITHUB_REPO_METADATA_TTL_SECONDS
    if "module" in segments or "modules" in segments:
        return _GITHUB_MODULE_STRUCTURE_TTL_SECONDS
    if normalized in {"", "."}:
        return _GITHUB_REPO_TREE_TTL_SECONDS
    return _GITHUB_DIRECTORY_STRUCTURE_TTL_SECONDS


def _github_structure_cache_get(key: tuple, ttl_seconds: int):
    now = time.monotonic()
    with _GITHUB_STRUCTURE_CACHE_LOCK:
        entry = _GITHUB_STRUCTURE_CACHE.get(key)
        if not entry:
            return None
        stored_at, value = entry
        if now - stored_at > ttl_seconds:
            _GITHUB_STRUCTURE_CACHE.pop(key, None)
            return None
        return value


def _github_structure_cache_put(key: tuple, value: Any) -> None:
    with _GITHUB_STRUCTURE_CACHE_LOCK:
        _GITHUB_STRUCTURE_CACHE[key] = (time.monotonic(), value)
        overflow = len(_GITHUB_STRUCTURE_CACHE) - _GITHUB_STRUCTURE_CACHE_MAX_ENTRIES
        if overflow > 0:
            oldest = sorted(
                _GITHUB_STRUCTURE_CACHE.items(),
                key=lambda item: item[1][0],
            )[:overflow]
            for stale_key, _entry in oldest:
                _GITHUB_STRUCTURE_CACHE.pop(stale_key, None)


def _github_invalidate_structure_cache(owner: str, repo: str, ref: str = "") -> None:
    prefix = (str(owner or ""), str(repo or ""))
    normalized_ref = str(ref or "")
    with _GITHUB_STRUCTURE_CACHE_LOCK:
        for key in list(_GITHUB_STRUCTURE_CACHE):
            if len(key) < 2 or key[:2] != prefix:
                continue
            # Structure keys use owner/repo/ref/...; repo-metadata keys have no ref.
            if normalized_ref and len(key) >= 3 and key[2] not in {normalized_ref, "repo"}:
                continue
            _GITHUB_STRUCTURE_CACHE.pop(key, None)


def _github_request_snapshot() -> Optional[dict]:
    """Return the current Teams request-local GitHub snapshot, if any."""
    flow_var = globals().get("_ACTIVE_TEAMS_FLOW_CONTEXT")
    if flow_var is None:
        return None
    try:
        active = flow_var.get() or {}
    except Exception:
        return None
    if not active.get("active"):
        return None
    snapshot = active.setdefault("repository_snapshot", {})
    snapshot.setdefault("files", {})
    snapshot.setdefault("directories", {})
    snapshot.setdefault("repos", {})
    snapshot.setdefault("branch_shas", {})
    snapshot.setdefault("tf_trees", {})
    return snapshot


def _github_snapshot_key(owner: str, repo: str, ref: str, path: str = "") -> tuple[str, str, str, str]:
    return (str(owner or ""), str(repo or ""), str(ref or ""), str(path or "").strip("/"))


def _github_invalidate_request_snapshot(owner: str, repo: str, ref: str = "") -> None:
    _github_invalidate_structure_cache(owner, repo, ref)
    snapshot = _github_request_snapshot()
    if not snapshot:
        return
    prefix = (str(owner or ""), str(repo or ""))
    normalized_ref = str(ref or "")
    for bucket in ("files", "directories", "tf_trees"):
        for key in list(snapshot.get(bucket, {})):
            if key[:2] == prefix and (not normalized_ref or key[2] == normalized_ref):
                snapshot[bucket].pop(key, None)
    for key in list(snapshot.get("branch_shas", {})):
        if key[:2] == prefix and (not normalized_ref or key[2] == normalized_ref):
            snapshot["branch_shas"].pop(key, None)


def github_get_directory_listing(cloud: Any | None, path: str, branch: str, repo_target: Optional[str] = None, workflow: Optional[str] = None):
    repo = github_repo_for_cloud(cloud, repo_target=repo_target, workflow=workflow)
    normalized_path = (path or "").strip("/")
    snapshot = _github_request_snapshot()
    cache_key = _github_snapshot_key(GITHUB_OWNER, repo, branch, normalized_path)
    if snapshot is not None and cache_key in snapshot["directories"]:
        return snapshot["directories"][cache_key]
    structure_key = (str(GITHUB_OWNER or ""), str(repo or ""), str(branch or ""), "directory", normalized_path)
    cached_structure = _github_structure_cache_get(
        structure_key, _github_structure_cache_ttl(normalized_path, kind="directory")
    )
    if cached_structure is not None:
        if snapshot is not None:
            snapshot["directories"][cache_key] = cached_structure
        return cached_structure

    if normalized_path in {"", "."}:
        url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{repo}/contents"
    else:
        url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{repo}/contents/{normalized_path}"
    response = requests.get(url, headers=github_headers(), params={"ref": branch}, timeout=30)

    if response.status_code == 404:
        return []

    response.raise_for_status()
    data = response.json()
    result = data if isinstance(data, list) else [data]
    if snapshot is not None:
        snapshot["directories"][cache_key] = result
    _github_structure_cache_put(structure_key, result)
    return result


def github_get_file_content(cloud: Any | None, path: str, branch: str, repo_target: Optional[str] = None, workflow: Optional[str] = None):
    repo = github_repo_for_cloud(cloud, repo_target=repo_target, workflow=workflow)
    snapshot = _github_request_snapshot()
    cache_key = _github_snapshot_key(GITHUB_OWNER, repo, branch, path)
    if snapshot is not None and cache_key in snapshot["files"]:
        return snapshot["files"][cache_key]
    url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{repo}/contents/{path}"
    response = requests.get(url, headers=github_headers(), params={"ref": branch}, timeout=30)

    if response.status_code == 404:
        return None

    response.raise_for_status()
    data = response.json()

    encoded = data.get("content")
    if not encoded:
        return None

    content = base64.b64decode(encoded).decode("utf-8")
    if snapshot is not None:
        snapshot["files"][cache_key] = content
    return content

def _github_get_repo_metadata_base(owner: str, repo: str):
    url = f"{GITHUB_API}/repos/{owner}/{repo}"
    response = requests.get(url, headers=github_headers(), timeout=30)

    if response.status_code == 404:
        return None

    response.raise_for_status()
    return response.json()

def github_get_repo(owner: str, repo: str) -> Optional[dict]:
    snapshot = _github_request_snapshot()
    cache_key = (str(owner or ""), str(repo or ""))
    if snapshot is not None and cache_key in snapshot["repos"]:
        return snapshot["repos"][cache_key]
    structure_key = (str(owner or ""), str(repo or ""), "repo", "metadata")
    cached_repo = _github_structure_cache_get(
        structure_key, _github_structure_cache_ttl(kind="repo")
    )
    if cached_repo is not None:
        if snapshot is not None:
            snapshot["repos"][cache_key] = cached_repo
        return cached_repo
    url = f"{GITHUB_API}/repos/{owner}/{repo}"
    response = requests.get(url, headers=github_headers(), timeout=30)

    if response.status_code == 404:
        return None

    response.raise_for_status()
    result = response.json()
    if snapshot is not None:
        snapshot["repos"][cache_key] = result
    _github_structure_cache_put(structure_key, result)
    return result


def github_get_repo_default_branch(owner: str, repo: str) -> Optional[str]:
    repo_data = github_get_repo(owner, repo)
    if not repo_data:
        return None
    return repo_data.get("default_branch")


def github_get_contents(owner: str, repo: str, path: str = "", ref: Optional[str] = None):
    normalized_path = (path or "").strip("/")
    # Only directory-list responses are stored in this cross-request cache.
    # File payloads (which contain repository content) remain uncached globally.
    structure_key = (str(owner or ""), str(repo or ""), str(ref or ""), "directory", normalized_path)
    cached_structure = _github_structure_cache_get(
        structure_key, _github_structure_cache_ttl(normalized_path, kind="directory")
    )
    if cached_structure is not None:
        return cached_structure
    if normalized_path:
        url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{normalized_path}"
    else:
        url = f"{GITHUB_API}/repos/{owner}/{repo}/contents"

    params = {}
    if ref:
        params["ref"] = ref

    response = requests.get(url, headers=github_headers(), params=params or None, timeout=30)
    if response.status_code == 404:
        return [] if not normalized_path else None

    response.raise_for_status()
    result = response.json()
    if isinstance(result, list):
        _github_structure_cache_put(structure_key, result)
    return result


def github_get_file_content_by_repo(owner: str, repo: str, path: str, ref: Optional[str] = None) -> Optional[str]:
    snapshot = _github_request_snapshot()
    cache_key = _github_snapshot_key(owner, repo, ref or "", path)
    if snapshot is not None and cache_key in snapshot["files"]:
        return snapshot["files"][cache_key]
    data: Any = github_get_contents(owner, repo, path=path, ref=ref)
    if not isinstance(data, dict):
        return None

    encoded = data.get("content")
    if not encoded:
        return None

    content = base64.b64decode(encoded).decode("utf-8")
    if snapshot is not None:
        snapshot["files"][cache_key] = content
    return content

def github_get_base_branch_sha_by_repo(owner: str, repo: str, branch_name: str):
    snapshot = _github_request_snapshot()
    cache_key = (str(owner or ""), str(repo or ""), str(branch_name or ""))
    if snapshot is not None and cache_key in snapshot["branch_shas"]:
        return snapshot["branch_shas"][cache_key]
    url = f"{GITHUB_API}/repos/{owner}/{repo}/git/ref/heads/{branch_name}"
    response = requests.get(url, headers=github_headers(), timeout=30)

    if response.status_code == 404:
        raise RuntimeError(
            f"GitHub repo or branch not found. owner='{owner}', repo='{repo}', branch='{branch_name}'."
        )

    response.raise_for_status()
    sha = response.json()["object"]["sha"]
    if snapshot is not None:
        snapshot["branch_shas"][cache_key] = sha
    return sha


def github_branch_exists_by_repo(owner: str, repo: str, branch_name: str) -> bool:
    url = f"{GITHUB_API}/repos/{owner}/{repo}/git/ref/heads/{branch_name}"
    response = requests.get(url, headers=github_headers(), timeout=30)

    if response.status_code == 404:
        return False

    response.raise_for_status()
    return True


def github_create_branch_by_repo(owner: str, repo: str, branch_name: str, base_sha: str):
    url = f"{GITHUB_API}/repos/{owner}/{repo}/git/refs"
    payload = {"ref": f"refs/heads/{branch_name}", "sha": base_sha}
    response = requests.post(url, headers=github_headers(), json=payload, timeout=30)

    if response.status_code not in (201, 422):
        response.raise_for_status()


def github_get_file_sha_by_repo(owner: str, repo: str, path: str, branch: str):
    url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
    response = requests.get(url, headers=github_headers(), params={"ref": branch}, timeout=30)

    if response.status_code == 404:
        return None

    response.raise_for_status()
    return response.json().get("sha")


def github_put_file_by_repo(owner: str, repo: str, path: str, content: str, branch: str, commit_message: str):
    url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
    encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")

    payload = {
        "message": commit_message,
        "content": encoded_content,
        "branch": branch,
    }

    sha = github_get_file_sha_by_repo(owner, repo, path, branch)
    if sha:
        payload["sha"] = sha

    response = requests.put(url, headers=github_headers(), json=payload, timeout=30)
    response.raise_for_status()
    _github_invalidate_request_snapshot(owner, repo, branch)
    return response.json()


def github_get_file_content_by_repo_branch(owner: str, repo: str, path: str, branch: str):
    return github_get_file_content_by_repo(owner, repo, path, ref=branch)


def github_put_file_if_changed_by_repo(owner: str, repo: str, path: str, content: str, branch: str,  commit_message: str):
    existing_content = github_get_file_content_by_repo_branch(owner, repo, path, branch )

    normalized_existing = (existing_content or "").replace("\r\n", "\n").strip()
    normalized_new = (content or "").replace("\r\n", "\n").strip()
    
    if existing_content is not None and normalized_existing == normalized_new:
      return {
        "changed": False,
        "path": path,
        "result": None,
    }

    result = github_put_file_by_repo(
        owner=owner,
        repo=repo,
        path=path,
        content=content,
        branch=branch,
        commit_message=commit_message,
    )

    return {
        "changed": True,
        "path": path,
        "result": result,
    }


def github_find_pr_by_branch_by_repo(owner: str, repo: str, branch_name: str, base_branch: str, state: str = "open"):
    url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls"
    response = requests.get(
        url,
        headers=github_headers(),
        params={
            "state": state,
            "head": f"{owner}:{branch_name}",
            "base": base_branch,
        },
        timeout=30,
    )
    response.raise_for_status()
    prs = response.json()
    return prs[0] if prs else None


def github_create_pull_request_by_repo(owner: str, repo: str, branch_name: str, base_branch: str, title: str, body: str):
    url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls"
    payload = {
        "title": title,
        "head": branch_name,
        "base": base_branch,
        "body": body,
    }

    response = requests.post(url, headers=github_headers(), json=payload, timeout=30)

    if response.status_code == 422:
        existing = github_find_pr_by_branch_by_repo(
            owner=owner,
            repo=repo,
            branch_name=branch_name,
            base_branch=base_branch,
            state="open",
        )
        if existing:
            return existing

    response.raise_for_status()
    return response.json()



def github_get_pull_request_by_repo(owner: Optional[str], repo: Optional[str], pr_number: int):
    if not owner or not repo or not pr_number:
        return None

    url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{int(pr_number)}"
    response = requests.get(url, headers=github_headers(), timeout=30)

    if response.status_code == 404:
        return None

    response.raise_for_status()
    return response.json()


def github_list_pull_request_files_by_repo(owner: Optional[str], repo: Optional[str], pr_number: int) -> list[dict]:
    if not owner or not repo or not pr_number:
        return []

    files = []
    page = 1

    while True:
        url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{int(pr_number)}/files"
        response = requests.get(
            url,
            headers=github_headers(),
            params={"per_page": 100, "page": page},
            timeout=30,
        )

        if response.status_code == 404:
            return []

        response.raise_for_status()
        batch = response.json() or []
        files.extend([item for item in batch if isinstance(item, dict)])

        if len(batch) < 100:
            break
        page += 1

    return files


def github_list_matching_branches_by_repo(owner: str, repo: str, prefix: str) -> list[str]:
    if not owner or not repo or not prefix:
        return []

    url = f"{GITHUB_API}/repos/{owner}/{repo}/git/matching-refs/heads/{prefix}"
    response = requests.get(url, headers=github_headers(), timeout=30)

    if response.status_code == 404:
        return []

    response.raise_for_status()
    refs = response.json() or []
    branches = []
    for item in refs:
        ref = item.get("ref", "") if isinstance(item, dict) else ""
        if ref.startswith("refs/heads/"):
            branches.append(ref.replace("refs/heads/", "", 1))
    return branches


def github_get_pull_request(cloud: Any | None, pr_number: int, repo_target: Optional[str] = None, workflow: Optional[str] = None):
    repo = github_repo_for_cloud(cloud, repo_target=repo_target, workflow=workflow)
    return github_get_pull_request_by_repo(GITHUB_OWNER, repo, pr_number)


def github_list_pull_request_files(cloud: Any | None, pr_number: int, repo_target: Optional[str] = None, workflow: Optional[str] = None) -> list[dict]:
    repo = github_repo_for_cloud(cloud, repo_target=repo_target, workflow=workflow)
    return github_list_pull_request_files_by_repo(GITHUB_OWNER, repo, pr_number)


def github_search_code(query: str, per_page: int = 20) -> list:
    url = f"{GITHUB_API}/search/code"
    response = requests.get(
        url,
        headers=github_headers(),
        params={"q": query, "per_page": max(1, min(int(per_page or 20), 100))},
        timeout=30,
    )

    if response.status_code == 404:
        return []

    response.raise_for_status()
    data = response.json() or {}
    return data.get("items") or []


def _unique_branch_names(branches: list[str]) -> list[str]:
    seen = set()
    result = []
    for branch in branches or []:
        name = (branch or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(name)
    return result


def _github_list_repo_branches_from_refs(owner: str, repo: str) -> list[str]:
    """Fallback branch listing through Git refs.

    /branches is the primary API. /git/matching-refs/heads is a second
    backend-only read from GitHub and still returns only real branch refs.
    """
    url = f"{GITHUB_API}/repos/{owner}/{repo}/git/matching-refs/heads"
    response = requests.get(url, headers=github_headers(), timeout=30)

    if response.status_code == 404:
        return []

    response.raise_for_status()
    refs = response.json() or []
    branches = []
    for item in refs:
        if not isinstance(item, dict):
            continue
        ref = item.get("ref") or ""
        if ref.startswith("refs/heads/"):
            branches.append(ref.replace("refs/heads/", "", 1))
    return branches


def github_list_repo_branches(owner: str, repo: str) -> list[str]:
    branches = []
    page = 1

    while True:
        url = f"{GITHUB_API}/repos/{owner}/{repo}/branches"
        response = requests.get(
            url,
            headers=github_headers(),
            params={"per_page": 100, "page": page},
            timeout=30,
        )

        if response.status_code == 404:
            return []

        response.raise_for_status()
        batch = response.json() or []
        if not batch:
            break

        for item in batch:
            name = item.get("name") if isinstance(item, dict) else None
            if name:
                branches.append(name)

        if len(batch) < 100:
            break
        page += 1

    try:
        branches.extend(_github_list_repo_branches_from_refs(owner, repo))
    except Exception as ref_error:
        print(f"Azure module branch refs fallback skipped {owner}/{repo}: {ref_error}")

    return _unique_branch_names(branches)


def _list_tf_files_by_repo_ref(owner: str, repo: str, ref: str) -> list[str]:
    results = []

    def walk(path: str = ""):
        items = github_get_contents(owner, repo, path=path, ref=ref)
        if isinstance(items, dict):
            items = [items]

        for item in items or []:
            if not isinstance(item, dict):
                continue

            item_type = item.get("type")
            item_path = item.get("path") or ""

            if item_type == "dir":
                walk(item_path)
            elif item_type == "file" and item_path.endswith(".tf"):
                results.append(item_path)

    walk("")
    return results


def get_best_module_branch_with_inputs(repo_owner: str, repo_name: str):
    """
    Try the default/main branch first, then other branches, and return the branch
    with the strongest verified Terraform variable coverage.
    """
    repo_owner = (repo_owner or "").strip()
    repo_name = (repo_name or "").strip()
    if not repo_owner or not repo_name:
        return []

    repo_metadata = github_get_repo(repo_owner, repo_name)
    default_branch = (repo_metadata or {}).get("default_branch") or "main"
    branches = github_list_repo_branches(repo_owner, repo_name)

    ordered_branches = []
    for candidate in [default_branch, "main"] + branches:
        if candidate and candidate not in ordered_branches:
            ordered_branches.append(candidate)

    best_branch = None
    best_inputs = []
    best_required = []
    best_score = -1

    for branch in ordered_branches:
        try:
            tf_files = _list_tf_files_by_repo_ref(repo_owner, repo_name, branch)
        except Exception:
            continue

        inputs = []
        required = []

        for tf_path in tf_files:
            try:
                content = github_get_file_content_by_repo(repo_owner, repo_name, tf_path, ref=branch)
            except Exception:
                content = None

            if not content:
                continue

            inputs.extend(_extract_tf_variable_names_from_text(content))
            required.extend(_extract_required_variable_names_from_text(content))
            for match in re.finditer(r'variable\s+"([^"]+)"\s*\{', content, re.IGNORECASE):
                variable_name = match.group(1)
                brace_start = content.find("{", match.end() - 1)
                if brace_start == -1:
                    continue

                depth = 0
                in_string = False
                escape_next = False
                block = ""

                for idx in range(brace_start, len(content)):
                    ch = content[idx]
                    if in_string:
                        if escape_next:
                            escape_next = False
                        elif ch == "\\":
                            escape_next = True
                        elif ch == '"':
                            in_string = False
                        continue

                    if ch == '"':
                        in_string = True
                    elif ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            block = content[match.start():idx + 1]
                            break

                if block and not re.search(r'^\s*default\s*=', block, re.MULTILINE | re.IGNORECASE):
                    required.append(variable_name)

        inputs = list(dict.fromkeys(inputs))
        required = [name for name in list(dict.fromkeys(required)) if name in inputs]

        score = len(inputs) * 10 + len(required)
        if branch == default_branch:
            score += 2
        elif branch == "main":
            score += 1

        if score > best_score:
            best_score = score
            best_branch = branch
            best_inputs = inputs
            best_required = required


    return best_branch, best_inputs, best_required


def get_module_branch_options_with_inputs(repo_owner: Optional[str], repo_name: Optional[str]) -> list[dict]:
    """Return real GitHub branches for a module repo with input summaries.

    Branch names are taken only from GitHub APIs. No model output is used for
    branch discovery. A branch is included even if Terraform inspection fails,
    so the user can still see the real branch list.
    """
    repo_owner = (repo_owner or "").strip()
    repo_name = (repo_name or "").strip()
    if not repo_owner or not repo_name:
        return []

    repo_metadata = github_get_repo(repo_owner, repo_name)
    default_branch = (repo_metadata or {}).get("default_branch") or "main"
    branches = github_list_repo_branches(repo_owner, repo_name)

    ordered_branches = []
    for candidate in [default_branch, "main"] + list(branches or []):
        candidate = (candidate or "").strip()
        if candidate and candidate not in ordered_branches:
            ordered_branches.append(candidate)

    options = []

    for branch in ordered_branches:
        inspection_error = ""
        try:
            tf_files = _list_tf_files_by_repo_ref(repo_owner, repo_name, branch)
        except Exception as branch_error:
            inspection_error = str(branch_error)
            print(f"Azure module branch inspection could not read {repo_owner}/{repo_name}@{branch}: {branch_error}")
            tf_files = []

        inputs = []
        required = []
        outputs = []
        variables_tf_paths = []

        for tf_path in tf_files:
            lower_path = (tf_path or "").lower()
            if lower_path.endswith("variables.tf"):
                variables_tf_paths.append(tf_path)

            try:
                content = github_get_file_content_by_repo(repo_owner, repo_name, tf_path, ref=branch)
            except Exception:
                content = None

            if not content:
                continue

            inputs.extend(_extract_tf_variable_names_from_text(content))
            required.extend(_extract_required_variable_names_from_text(content))
            outputs.extend(re.findall(r'output\s+"([^"]+)"', content, re.IGNORECASE))

            for match in re.finditer(r'variable\s+"([^"]+)"\s*\{', content, re.IGNORECASE):
                variable_name = match.group(1)
                brace_start = content.find("{", match.end() - 1)
                if brace_start == -1:
                    continue

                depth = 0
                in_string = False
                escape_next = False
                block = ""

                for idx in range(brace_start, len(content)):
                    ch = content[idx]
                    if in_string:
                        if escape_next:
                            escape_next = False
                        elif ch == "\\":
                            escape_next = True
                        elif ch == '"':
                            in_string = False
                        continue

                    if ch == '"':
                        in_string = True
                    elif ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            block = content[match.start():idx + 1]
                            break

                if block and not re.search(r'^\s*default\s*=', block, re.MULTILINE | re.IGNORECASE):
                    required.append(variable_name)

        inputs = list(dict.fromkeys(inputs))
        required = [name for name in list(dict.fromkeys(required)) if name in inputs]
        outputs = list(dict.fromkeys(outputs))
        variables_tf_paths = list(dict.fromkeys(variables_tf_paths))

        score = len(inputs) * 10 + len(required)
        if variables_tf_paths:
            score += 5
        if branch == default_branch:
            score += 2
        elif branch == "main":
            score += 1

        options.append({
            "branch": branch,
            "is_default": branch == default_branch,
            "is_main": branch == "main",
            "tf_files": list(tf_files or []),
            "variables_tf_paths": variables_tf_paths,
            "has_variables_tf": bool(variables_tf_paths),
            "inputs_detected": inputs,
            "required_inputs_detected": required,
            "outputs_detected": outputs,
            "score": score,
            "inspection_error": inspection_error,
        })

    options.sort(
        key=lambda item: (
            0 if item.get("inputs_detected") else 1,
            0 if item.get("has_variables_tf") else 1,
            -int(item.get("score") or 0),
            0 if item.get("is_default") else 1,
            item.get("branch") or "",
        )
    )

    if options:
        options[0]["recommended"] = True

    return options


def should_require_azure_module_branch_selection(branch_options: list[dict]) -> bool:
    """Always require an explicit user-selected module branch/ref.

    This prevents silently falling back to main/default or a guessed "best"
    branch when variables.tf lives on another real GitHub branch.
    """
    return True


def build_azure_module_branch_discovery(discovery: dict, match: dict) -> dict:
    match = match or {}
    if match.get("repo_owner") and match.get("repo_name"):
        branch_options = get_module_branch_options_with_inputs(
            match.get("repo_owner"),
            match.get("repo_name"),
        )
    else:
        branch_options = []

    branch_discovery = dict(discovery or {})
    branch_discovery["decision_state"] = "azure_module_branch_selection"
    branch_discovery["selected_match"] = match
    branch_discovery["branch_options"] = branch_options
    branch_discovery["branch_selection_required"] = should_require_azure_module_branch_selection(branch_options)
    return branch_discovery


def _manual_branch_candidates_from_reply(reply: str) -> list[str]:
    raw = (reply or "").strip().strip("`'\"")
    if not raw:
        return []

    candidates = [raw]
    prefix_match = re.match(
        r"^(?:use|select|choose|pick|branch|ref)\s+(.+)$",
        raw,
        re.IGNORECASE,
    )
    if prefix_match:
        candidates.append(prefix_match.group(1).strip().strip("`'\""))

    result = []
    for candidate in candidates:
        candidate = (candidate or "").strip().strip("`'\"")
        lower = normalize_yes_no_reply(candidate)

        if not candidate or lower in AFFIRMATIVE_REPLIES or lower in NEGATIVE_REPLIES:
            continue
        if re.fullmatch(r"#?\d+", candidate):
            continue
        if re.search(r"\s", candidate):
            continue
        if not re.fullmatch(r"[A-Za-z0-9._/-]+", candidate):
            continue
        if candidate not in result:
            result.append(candidate)

    return result


def resolve_manual_azure_module_branch_from_reply(reply: str, match: dict) -> str:
    match = match or {}
    owner = (match.get("repo_owner") or GITHUB_OWNER or "").strip()
    repo = (match.get("repo_name") or "").strip()
    if not owner or not repo:
        return ""

    for candidate in _manual_branch_candidates_from_reply(reply):
        try:
            if github_branch_exists_by_repo(owner, repo, candidate):
                return candidate
        except Exception as branch_error:
            print(f"Manual Azure module branch check failed {owner}/{repo}@{candidate}: {branch_error}")

    return ""


def azure_context_has_verified_inputs_for_branch(
    retrieved_module_context: list,
    repo_full_name: str,
    selected_module_ref: str,
) -> bool:
    repo_full_name = (repo_full_name or "").strip().lower()
    selected_module_ref = (selected_module_ref or "").strip()

    for item in retrieved_module_context or []:
        if not isinstance(item, dict):
            continue
        if repo_full_name and (item.get("repo_full_name") or "").strip().lower() != repo_full_name:
            continue
        if selected_module_ref and (item.get("resolved_ref") or "").strip() != selected_module_ref:
            continue
        if item.get("inputs_detected"):
            return True

    return False


def add_grounded_azure_context_for_match(
    match: dict,
    selected_module_ref: str,
    retrieved_module_context: list,
    retrieved_value_context: list,
) -> tuple[list[dict], list[dict]]:
    approved_consumer_repos = get_approved_azure_consumer_repos()
    approved_repo_default_branches = {
        repo_name: GITHUB_AZURE_BASE_BRANCH
        for repo_name in approved_consumer_repos
    }

    grounded_module_context, grounded_value_context = build_grounded_azure_contexts(
        match,
        github_get_repo_default_branch=github_get_repo_default_branch,
        github_get_contents=github_get_contents,
        github_get_file_content_by_repo=github_get_file_content_by_repo,
        github_search_code=github_search_code,
        github_verify_repo_exists=github_verify_repo_exists,
        approved_consumer_repos=approved_consumer_repos,
        approved_repo_default_branches=approved_repo_default_branches,
        # Do not auto-select a best branch here. The selected ref must come
        # from the explicit branch-selection prompt and is used verbatim for
        # module source and variables.tf retrieval.
        get_best_module_branch_with_inputs=None,
        selected_module_ref=selected_module_ref,
    )

    if grounded_module_context:
        existing_keys = {
            item.get("repo_full_name")
            for item in retrieved_module_context
            if isinstance(item, dict)
        }
        for item in grounded_module_context:
            if item.get("repo_full_name") not in existing_keys:
                retrieved_module_context = list(retrieved_module_context or [])
                retrieved_module_context.append(item)
                existing_keys.add(item.get("repo_full_name"))

    if grounded_value_context:
        retrieved_value_context = list(retrieved_value_context or [])
        retrieved_value_context.extend(grounded_value_context)

    return retrieved_module_context, retrieved_value_context


def github_verify_repo_exists(full_name: str) -> bool:
    owner_repo = (full_name or "").strip().split("/", 1)
    if len(owner_repo) != 2:
        return False
    owner, repo = owner_repo
    return github_get_repo(owner, repo) is not None


def github_get_repo_metadata(owner: str, repo: str) -> Optional[dict]:
    return github_get_repo(owner, repo)


def github_repo_exists(owner: str, repo: str) -> bool:
    return github_verify_repo_exists(f"{owner}/{repo}")


def github_list_tf_files_recursive(
    cloud: str,
    root_path: str,
    branch: str,
    repo_target: Optional[str] = None,
    workflow: Optional[str] = None,
):
    repo = github_repo_for_cloud(cloud, repo_target=repo_target, workflow=workflow)
    snapshot = _github_request_snapshot()
    tree_key = _github_snapshot_key(GITHUB_OWNER, repo, branch, root_path or ".")
    if snapshot is not None and tree_key in snapshot["tf_trees"]:
        return list(snapshot["tf_trees"][tree_key])
    normalized_root = str(root_path or ".").strip("/") or "."
    structure_key = (str(GITHUB_OWNER or ""), str(repo or ""), str(branch or ""), "tf_tree", normalized_root)
    cached_tree = _github_structure_cache_get(
        structure_key, _github_structure_cache_ttl(normalized_root, kind="tree")
    )
    if cached_tree is not None:
        if snapshot is not None:
            snapshot["tf_trees"][tree_key] = list(cached_tree)
        return list(cached_tree)

    results = []

    def walk(current_path: str):
        items = github_get_directory_listing(
            cloud,
            current_path,
            branch,
            repo_target=repo_target,
            workflow=workflow,
        )
        for item in items:
            item_type = item.get("type")
            item_path = item.get("path", "")
            if item_type == "dir":
                walk(item_path)
                continue
            if item_type == "file" and item_path.endswith(".tf"):
                results.append(item_path)

    walk(root_path or ".")
    if snapshot is not None:
        snapshot["tf_trees"][tree_key] = list(results)
    _github_structure_cache_put(structure_key, list(results))
    return results

def auth_headers_ok(headers) -> bool:
    return True

def github_headers_for_repo():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def github_list_issue_comments(owner: str, repo: str, issue_number: int):
    url = f"{GITHUB_API}/repos/{owner}/{repo}/issues/{issue_number}/comments"
    response = requests.get(url, headers=github_headers_for_repo(), timeout=30)
    response.raise_for_status()
    return response.json()


def github_create_issue_comment(owner: str, repo: str, issue_number: int, body: str):
    url = f"{GITHUB_API}/repos/{owner}/{repo}/issues/{issue_number}/comments"
    response = requests.post(
        url,
        headers=github_headers_for_repo(),
        json={"body": body},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def github_update_issue_comment(owner: str, repo: str, comment_id: int, body: str):
    url = f"{GITHUB_API}/repos/{owner}/{repo}/issues/comments/{comment_id}"
    response = requests.patch(
        url,
        headers=github_headers_for_repo(),
        json={"body": body},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def github_upsert_pr_summary_comment(owner: str, repo: str, pr_number: int, body: str):
    comments = github_list_issue_comments(owner, repo, pr_number)

    existing = None
    for comment in comments:
        if GITHUB_PR_COMMENT_MARKER in (comment.get("body") or ""):
            existing = comment
            break

    final_body = f"{GITHUB_PR_COMMENT_MARKER}\n{body}"

    if existing:
        return github_update_issue_comment(owner, repo, existing["id"], final_body)

    return github_create_issue_comment(owner, repo, pr_number, final_body)

def azure_devops_headers():
    pat = (AZDO_PAT or "").strip()
    if not pat:
        raise RuntimeError("Missing AZDO_PAT environment variable.")

    token = base64.b64encode(f":{pat}".encode("utf-8")).decode("ascii")
    return {
        "Authorization": f"Basic {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

def trigger_test_branch_pipeline_for_pr(
    repo_owner: Optional[str],
    repo_name: Optional[str],
    pr_number: int,
    source_branch: str,
    target_branch: str,
):
    repo_owner = (repo_owner or "").strip()
    repo_name = (repo_name or "").strip()
    if not repo_owner or not repo_name:
        raise RuntimeError("PR repository owner and name are required for the Azure DevOps pipeline.")

    missing = []
    if not AZDO_ORG:
        missing.append("AZDO_ORG")
    if not AZDO_PROJECT:
        missing.append("AZDO_PROJECT")
    if not AZDO_PIPELINE_ID:
        missing.append("AZDO_PIPELINE_ID")
    if not AZDO_PAT:
        missing.append("AZDO_PAT")

    if missing:
        raise RuntimeError(
            "Missing Azure DevOps pipeline settings: " + ", ".join(missing)
        )

    pipeline_branch = (AZDO_PIPELINE_BRANCH or "terrabot-test").replace("refs/heads/", "").strip()
    source_branch = (source_branch or "").replace("refs/heads/", "").strip()
    target_branch = (target_branch or "").replace("refs/heads/", "").strip()

    if not source_branch:
        raise RuntimeError("PR source branch was empty.")
    if not target_branch:
        raise RuntimeError("PR target branch was empty.")

    url = (
        f"https://dev.azure.com/{AZDO_ORG}/{AZDO_PROJECT}"
        f"/_apis/build/builds?api-version={AZDO_API_VERSION}"
    )

    payload = {
        "definition": {
            "id": int(AZDO_PIPELINE_ID or 0)
        },
        "sourceBranch": f"refs/heads/{pipeline_branch}",
        "variables": {
            "PR_REPO_OWNER": {"value": repo_owner},
            "PR_REPO_NAME": {"value": repo_name},
            "PR_NUMBER": {"value": str(pr_number)},
            "PR_SOURCE_BRANCH": {"value": source_branch},
            "PR_TARGET_BRANCH": {"value": target_branch},
            "PR_IS_BACKEND_TRIGGERED": {"value": "true"},
            "PIPELINE_CODE_BRANCH": {"value": pipeline_branch},
        }
    }

    response = requests.post(
        url,
        headers=azure_devops_headers(),
        json=payload,
        timeout=30,
    )

    print("AZDO status:", response.status_code)
    print("AZDO content-type:", response.headers.get("Content-Type"))
    print("AZDO body:", response.text[:4000])
    print("AZDO pipeline code branch:", pipeline_branch)
    print("AZDO PR source branch:", source_branch)
    print("AZDO PR target branch:", target_branch)

    if "text/html" in (response.headers.get("Content-Type") or "").lower():
        raise RuntimeError(
            f"Azure DevOps returned HTML instead of JSON. "
            f"Authentication is still failing. status={response.status_code}"
        )

    response.raise_for_status()
    return response.json()


def call_named_agent(conversation_input: str, agent_name: Optional[str]):
    if not agent_name:
        raise RuntimeError("Missing PLAN_RISK_AGENT_NAME in environment variables.")

    agent_reference = find_agent_reference(agent_name)

    client = get_project_client()
    with client.get_openai_client() as openai_client:
        conversation = openai_client.conversations.create(
            items=[{"type": "message", "role": "user", "content": conversation_input}],
        )

        response = openai_client.responses.create(
            conversation=conversation.id,
            extra_body={"agent_reference": agent_reference},
        )

        return getattr(response, "output_text", None) or ""


def extract_json_safely(text: str) -> dict:
    try:
        return extract_json_from_text(text)
    except Exception:
        return {}


def _insert_breaks_for_resource(text: str) -> str:
    if not text:
        return ""
    text = escape(str(text))
    text = text.replace(".", ".<wbr>")
    text = text.replace("/", "/<wbr>")
    text = text.replace("_", "_<wbr>")
    text = text.replace("[", "[<wbr>")
    text = text.replace("]", "]<wbr>")
    text = text.replace("(", "(<wbr>")
    text = text.replace(")", ")<wbr>")
    return text


def _compact_text(value: str, limit: int = 48) -> str:
    if value is None:
        return ""
    value = " ".join(str(value).split())
    if len(value) <= limit:
        return escape(value)
    return escape(value[: limit - 1].rstrip()) + "…"


def _parse_markdown_table(table_md: str) -> list[dict]:
    lines = [line.strip() for line in (table_md or "").splitlines() if line.strip()]
    table_lines = [line for line in lines if line.startswith("|") and line.endswith("|")]

    if len(table_lines) < 2:
        return []

    headers = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
    rows: list[dict] = []

    for line in table_lines[2:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < len(headers):
            cells += [""] * (len(headers) - len(cells))
        elif len(cells) > len(headers):
            cells = cells[: len(headers)]
        rows.append(dict(zip(headers, cells)))

    return rows


def _render_compact_html_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "<p><em>No data.</em></p>"

    thead = "".join(f"<th>{escape(h)}</th>" for h in headers)
    tbody = []
    for row in rows:
        cols = "".join(f"<td>{cell}</td>" for cell in row)
        tbody.append(f"<tr>{cols}</tr>")

    return (
        "<table>"
        f"<thead><tr>{thead}</tr></thead>"
        f"<tbody>{''.join(tbody)}</tbody>"
        "</table>"
    )


def render_compact_summary_table(summary_markdown: str) -> str:
    parsed = _parse_markdown_table(summary_markdown)
    rows: list[list[str]] = []

    for row in parsed:
        marker = _compact_text(row.get("Marker", ""), 4)
        action = _compact_text(row.get("Action", ""), 12)
        count = _compact_text(row.get("Count", ""), 8)
        resources = row.get("Resources", "") or row.get("Resource", "")

        resource_cells = []
        for part in [r.strip() for r in resources.split(",") if r.strip()]:
            resource_cells.append(_insert_breaks_for_resource(part))

        if not resource_cells:
            resources_html = ""
        elif len(resource_cells) == 1:
            resources_html = resource_cells[0]
        else:
            resources_html = "<br>".join(resource_cells[:6])
            if len(resource_cells) > 6:
                resources_html += "<br>…"

        rows.append([marker, action, count, resources_html])

    return _render_compact_html_table(
        ["", "Act", "Cnt", "Resources"],
        rows,
    )



def render_compact_created_table(created_markdown: str) -> str:
    parsed = _parse_markdown_table(created_markdown)
    rows: list[list[str]] = []

    for row in parsed:
        marker = _compact_text(row.get("Marker", ""), 4)
        resource_name = _insert_breaks_for_resource(row.get("Resource Name", "") or row.get("Resource", ""))
        resource_type = _compact_text(row.get("Type", ""), 24)
        rows.append([marker, resource_name, resource_type])

    return _render_compact_html_table(
        ["", "Resource", "Type"],
        rows,
    )


def render_compact_risk_table(risk_markdown: str) -> str:
    parsed = _parse_markdown_table(risk_markdown)
    rows: list[list[str]] = []

    for row in parsed:
        marker = _compact_text(row.get("Marker", ""), 4)
        resource = _insert_breaks_for_resource(row.get("Resource", "") or row.get("Finding", ""))
        resource_type = _compact_text(row.get("Type", ""), 20)
        action = _compact_text(row.get("Action", ""), 12)
        severity = _compact_text(row.get("Severity", ""), 10)
        risk = _compact_text(row.get("Risk", "") or row.get("Impact", ""), 56)
        rows.append([marker, resource, resource_type, action, severity, risk])

    return _render_compact_html_table(
        ["", "Resource", "Type", "Act", "Sev", "Risk"],
        rows,
    )


def build_plan_risk_agent_input(tfplan: dict, payload: dict) -> dict:
    return {
        "task": "Analyze Terraform plan risk for a pull request.",
        "required_output_format": {
            "headline": "short overall result",
            "summary_markdown": (
                "markdown table with columns Marker | Action | Count | Resources"
            ),
            "created_markdown": (
                "markdown table with columns Marker | Resource Name | Type"
            ),
            "risk_markdown": (
                "markdown table with columns Marker | Resource | Type | Action | Severity | Risk"
            ),
            "overall_risk": "low|medium|high|critical",
        },
        "rules": [
            "Return valid JSON only.",
            "Do not wrap JSON in markdown.",
            "Use these markers consistently: red = 🔴, yellow = 🟡, green = 🟢.",
            "summary_markdown must be a markdown table.",
            "created_markdown must be a markdown table.",
            "risk_markdown must be a markdown table.",
            "Base analysis only on the tfplan payload provided.",
            "Never invent resources or actions not present in the plan.",
            "Keep every table cell concise.",
            "Resource and Finding columns must contain only the exact Terraform resource address or short exact name.",
            "Action must be one of Create, Update, Delete, Replace, No-op when applicable.",
            "Count must be numeric.",
            "Severity must be one of Low, Medium, High, Critical.",
            "Risk must be a short phrase, not a paragraph.",
            "Do not exceed 8 words in any non-resource table cell unless absolutely necessary.",
            "Summary should list grouped resources per action, not long prose.",
            "Created table should list only created resources.",
            "Risk table should include only meaningful risks or high-signal no-op context if needed.",
            "Set overall_risk to the highest real risk present.",
        ],
        "metadata": {
            "repo_owner": payload.get("repo_owner", ""),
            "repo_name": payload.get("repo_name", ""),
            "pr_number": payload.get("pr_number", ""),
            "branch_name": payload.get("branch_name", ""),
            "commit_sha": payload.get("commit_sha", ""),
            "build_id": payload.get("build_id", ""),
            "build_number": payload.get("build_number", ""),
            "module_directory": payload.get("module_directory", ""),
            "folder": payload.get("folder", ""),
        },
        "tfplan": tfplan,
    }


def build_pr_comment_from_agent_result(agent_result: dict, payload: dict) -> str:
    headline = (agent_result.get("headline") or "Terraform plan risk analysis").strip()
    overall_risk = (agent_result.get("overall_risk") or "unknown").strip()

    summary_markdown = (
        agent_result.get("summary_markdown")
        or "| Marker | Action | Count | Resources |\n|---|---|---:|---|\n| 🟡 | Review | 0 | No summary returned |\n"
    ).strip()

    created_markdown = (
        agent_result.get("created_markdown")
        or "| Marker | Resource Name | Type |\n|---|---|---|\n| 🟢 | None | N/A |\n"
    ).strip()

    risk_markdown = (
        agent_result.get("risk_markdown")
        or "| Marker | Resource | Type | Action | Severity | Risk |\n|---|---|---|---|---|---|\n| 🟡 | None | N/A | Review | Medium | No risk table returned |\n"
    ).strip()

    module_directory = payload.get("module_directory", "")
    folder = payload.get("folder", "")
    build_id = payload.get("build_id", "")
    repo_owner = payload.get("repo_owner", "")
    repo_name = payload.get("repo_name", "")
    pr_number = payload.get("pr_number", "")

    summary_html = render_compact_summary_table(summary_markdown)
    created_html = render_compact_created_table(created_markdown)
    risk_html = render_compact_risk_table(risk_markdown)

    return f"""<!-- terrabot-plan-risk-comment -->
## Terrabot Plan-Risk Analysis

**Result:** {escape(headline)}  
**Overall risk:** `{escape(overall_risk)}`  
**Module:** `{escape(module_directory)}`  
**Folder:** `{escape(folder)}`  
**Build ID:** `{escape(str(build_id))}`  
**PR:** `{escape(str(repo_owner))}/{escape(str(repo_name))}#{escape(str(pr_number))}`

<details open>
<summary><strong>Plan Summary</strong></summary>

{summary_html}
</details>

<details open>
<summary><strong>Resources Created</strong></summary>

{created_html}
</details>

<details open>
<summary><strong>Risk Assessment</strong></summary>

{risk_html}
</details>
"""

def load_existing_tf_files_for_context(cloud: str, branch_name: str, folder: str):
    existing = []
    folder_prefix = folder.rstrip("/") + "/"

    def walk(current_path: str):
        for item in github_get_directory_listing(cloud, current_path, branch_name):
            item_type = item.get("type")
            item_path = item.get("path", "")

            if item_type == "dir":
                walk(item_path)
                continue

            if item_type != "file" or not item_path.endswith(".tf"):
                continue

            content = github_get_file_content(cloud, item_path, branch_name)
            if content is None:
                continue

            if item_path.startswith(folder_prefix):
                relative_name = item_path[len(folder_prefix):]
            else:
                relative_name = item_path.split("/")[-1]

            existing.append({
                "filename": relative_name,
                "content": content,
            })

    walk(folder)
    return existing

def ensure_thread_meta(thread_id: str):
    if thread_id not in THREAD_PR_STATE:
        THREAD_PR_STATE[thread_id] = {}

    if "_meta" not in THREAD_PR_STATE[thread_id]:
        THREAD_PR_STATE[thread_id]["_meta"] = {
            "last_selected_cloud": None
        }

    return THREAD_PR_STATE[thread_id]["_meta"]


def set_last_selected_cloud(thread_id: str, cloud: str):
    if not thread_id:
        return
    meta = ensure_thread_meta(thread_id)
    meta["last_selected_cloud"] = cloud



def get_thread_cloud_states(thread_id: str):
    if not thread_id or thread_id not in THREAD_PR_STATE:
        return {}
    return {
        k: v for k, v in THREAD_PR_STATE[thread_id].items()
        if k in ("aws", "azure_module", "azure_consumer", "azure_module_population") and isinstance(v, dict)
    }


def infer_aws_environment_path_from_branch(cloud: str, branch_name: str) -> str | None:
    candidate_roots = [
        "terraform/dev_aws",
        "terraform/prod_aws",
    ]

    best_match = None
    best_depth = -1

    def walk(current_path: str):
        nonlocal best_match, best_depth

        for item in github_get_directory_listing(cloud, current_path, branch_name):
            item_type = item.get("type")
            item_path = item.get("path", "")

            if item_type == "dir":
                walk(item_path)
                continue

            if item_type != "file" or not item_path.endswith(".tf"):
                continue

            if item_path.startswith("terraform/dev_aws/") or item_path.startswith("terraform/prod_aws/"):
                folder = item_path.rsplit("/", 1)[0]
                depth = folder.count("/")
                if depth > best_depth:
                    best_match = folder
                    best_depth = depth

    for root in candidate_roots:
        walk(root)

    return best_match


def recover_cloud_state(thread_id: str, cloud: str, repo_target: Optional[str] = None, workflow: Optional[str] = None):
    cloud = normalize_cloud(cloud)
    repo_target = normalize_repo_target(cloud, repo_target, workflow)
    bucket = state_bucket_for_target(cloud, repo_target, workflow)

    folder = build_stable_folder(thread_id, cloud, repo_target=repo_target, workflow=workflow)
    prefix = build_branch_prefix(thread_id, cloud, repo_target=repo_target, workflow=workflow)
    matching_branches = github_list_matching_branches(cloud, prefix, repo_target=repo_target)

    latest_cycle = 0
    open_pr = None
    latest_pr = None
    selected_branch = None

    for candidate_branch in matching_branches:
        cycle = parse_branch_cycle(candidate_branch, prefix)
        if cycle <= 0:
            continue

        if cycle > latest_cycle:
            latest_cycle = cycle
            selected_branch = candidate_branch

        candidate_open_pr = github_find_pr_by_branch(cloud, candidate_branch, state="open", repo_target=repo_target)
        if candidate_open_pr:
            open_pr = candidate_open_pr
            selected_branch = candidate_branch
            latest_cycle = max(latest_cycle, cycle)
            latest_pr = candidate_open_pr
            break

        candidate_latest_pr = github_find_pr_by_branch(cloud, candidate_branch, state="all", repo_target=repo_target)
        if candidate_latest_pr and (
            latest_pr is None or cycle >= parse_branch_cycle(selected_branch or "", prefix)
        ):
            latest_pr = candidate_latest_pr

    if not selected_branch:
        selected_branch = build_branch_name(thread_id, cloud, 1, repo_target=repo_target, workflow=workflow)
        latest_cycle = 1

    branch_exists = github_branch_exists(cloud, selected_branch, repo_target=repo_target)
    folder_on_base_exists = github_folder_exists(
        cloud,
        folder,
        github_base_branch_for_cloud(cloud, repo_target=repo_target, workflow=workflow),
        repo_target=repo_target,
    )

    if not branch_exists and not open_pr and not latest_pr and not folder_on_base_exists:
        return None

    state = {
        "branch": selected_branch,
        "pr_number": open_pr.get("number") if open_pr else None,
        "pr_url": open_pr.get("html_url") if open_pr else None,
        "cloud": cloud,
        "repo_target": repo_target,
        "state_bucket": bucket,
        "folder": folder,
        "cycle": latest_cycle,
        "has_open_pr": bool(open_pr),
        "latest_pr_state": latest_pr.get("state") if latest_pr else None,
        "latest_pr_merged": bool(latest_pr.get("merged_at")) if latest_pr else False,
    }

    if cloud == "aws" and branch_exists:
        inferred_env_path = infer_aws_environment_path_from_branch(cloud, selected_branch)
        if inferred_env_path:
            state["environment_path"] = inferred_env_path

    return state

def recover_thread_pr_state(thread_id: str) -> dict:
    if not thread_id:
        return {}

    ensure_thread_meta(thread_id)

    existing_thread_state = get_thread_cloud_states(thread_id)
    if existing_thread_state:
        return existing_thread_state

    recovered = {}

    aws_state = recover_cloud_state(thread_id, "aws", repo_target="tf-devops")
    if aws_state:
        recovered["aws"] = aws_state

    azure_module_state = recover_cloud_state(thread_id, "azure", repo_target="vena_repos", workflow="azure_module_repo_creation")
    if azure_module_state:
        recovered["azure_module"] = azure_module_state

    azure_consumer_state = recover_cloud_state(thread_id, "azure", repo_target="tf-azure-hub", workflow="azure_consumer_generation")
    if azure_consumer_state:
        recovered["azure_consumer"] = azure_consumer_state

    if recovered:
        existing_meta = THREAD_PR_STATE.get(thread_id, {}).get("_meta", {"last_selected_cloud": None})
        THREAD_PR_STATE[thread_id] = dict(recovered)
        THREAD_PR_STATE[thread_id]["_meta"] = existing_meta

    return recovered


def is_infra_request(prompt: str, thread_id: Optional[str] = None) -> bool:
    """Deprecated compatibility shim.

    Teams intent is classified exclusively by the Azure AI Foundry agent.
    This function is intentionally non-semantic and must not be used as a
    routing gate. It remains temporarily import-safe for older callers while
    they are upgraded.
    """
    del prompt, thread_id
    return False




