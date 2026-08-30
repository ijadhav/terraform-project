"""Live Terrabot test runner.

Extends the existing manual live-context smoke check (see
``scripts/test_live_pr_and_repo_context.py``) into an automated suite that:

  * constructs *natural, user-like* prompts from the CURRENT live Terraform in
    ``tf-devops`` and ``tf-azure-hub`` (Boolean modification, existing-resource
    modification, existing-module/new-consumer, repository-context regression);
  * verifies the selected target still exists at the repository HEAD before
    executing a case (never uses stale/hardcoded resource/flag/path cases);
  * runs each case through the REAL backend workflow (``handle_chat_request`` —
    the same entrypoint the Teams/chat routes use: discovery -> primary context
    -> repository-context retrieval -> Foundry -> validators/repairs ->
    branch/file push), never by calling the Terraform generator directly;
  * records independent per-case results; and
  * returns ONE aggregated result plus a Teams-ready summary. The Teams command
    handler in ``shared_code.teams_bot`` sends that single message with the
    requesting user's own identity (no hardcoded Teams identity).

The module is dependency-injected: every external call (tree listing, file
fetch, HEAD verification, repository-context retrieval, backend execution) has a
default that reuses the existing production helpers, and can be overridden in
tests with fakes so the discovery/aggregation logic runs fully offline.
"""
from __future__ import annotations

import logging
import os
import re
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

LOGGER = logging.getLogger("terrabot.live_test_runner")

# Discovered assignment matcher: create_x / enable_x / x_enabled = true|false.
_BOOL_ASSIGN_RE = re.compile(
    r"^\s*((?:create_|enable_)[a-z0-9_]+|[a-z0-9_]+_enabled)\s*=\s*(true|false)\b",
    re.IGNORECASE | re.MULTILINE,
)
_MODULE_BLOCK_RE = re.compile(r'^\s*module\s+"([a-z0-9_-]+)"\s*\{', re.IGNORECASE | re.MULTILINE)
_MODULE_SOURCE_RE = re.compile(r'source\s*=\s*"([^"]+)"')


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
class RunnerConfig:
    """Resolved repository coordinates for a run (from environment variables)."""

    def __init__(
        self,
        owner: str = "",
        azure_repo: str = "",
        azure_branch: str = "main",
        aws_repo: str = "",
        aws_branch: str = "main",
        token: str = "",
    ) -> None:
        self.owner = owner
        self.azure_repo = azure_repo
        self.azure_branch = azure_branch or "main"
        self.aws_repo = aws_repo
        self.aws_branch = aws_branch or "main"
        self.token = token

    @classmethod
    def from_env(cls) -> "RunnerConfig":
        return cls(
            owner=os.getenv("GITHUB_OWNER", "").strip(),
            azure_repo=os.getenv("GITHUB_AZURE_REPO", "").strip(),
            azure_branch=os.getenv("GITHUB_AZURE_BASE_BRANCH", "main").strip() or "main",
            aws_repo=os.getenv("GITHUB_AWS_REPO", "").strip(),
            aws_branch=os.getenv("GITHUB_AWS_BASE_BRANCH", "main").strip() or "main",
            token=os.getenv("GITHUB_TOKEN", "").strip(),
        )

    def targets(self) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        if self.owner and self.azure_repo:
            out.append({
                "cloud": "azure",
                "repo_target": "tf-azure-hub",
                "repo": self.azure_repo,
                "branch": self.azure_branch,
            })
        if self.owner and self.aws_repo:
            out.append({
                "cloud": "aws",
                "repo_target": "tf-devops",
                "repo": self.aws_repo,
                "branch": self.aws_branch,
            })
        return out


# --------------------------------------------------------------------------- #
# Pure parsing / discovery helpers (unit-testable, no network)
# --------------------------------------------------------------------------- #
def find_boolean_assignments(content: str) -> List[Dict[str, Any]]:
    """Return every root-level Boolean feature-flag assignment in a file."""
    results: List[Dict[str, Any]] = []
    for match in _BOOL_ASSIGN_RE.finditer(content or ""):
        results.append({
            "flag": match.group(1),
            "value": match.group(2).lower() == "true",
        })
    return results


def find_module_blocks(content: str) -> List[Dict[str, str]]:
    """Return module block names + sources discovered in a .tf file."""
    blocks: List[Dict[str, str]] = []
    for match in _MODULE_BLOCK_RE.finditer(content or ""):
        name = match.group(1)
        tail = (content or "")[match.end():match.end() + 600]
        source_match = _MODULE_SOURCE_RE.search(tail)
        blocks.append({"name": name, "source": source_match.group(1) if source_match else ""})
    return blocks


def environment_from_path(path: str) -> str:
    """Derive a human environment/scope label from a repo-relative path.

    tf-azure-hub: ``vars/<tier>/<scope>/hub.tfvars`` -> ``<scope>`` (else tier).
    tf-devops:    ``terraform/<account>/<env>/main.tf`` -> ``<env>``.
    """
    parts = [p for p in str(path or "").split("/") if p]
    if "vars" in parts:
        idx = parts.index("vars")
        tail = parts[idx + 1:-1]  # drop the filename
        if len(tail) >= 2:
            return tail[1]
        if tail:
            return tail[0]
    if "terraform" in parts:
        idx = parts.index("terraform")
        tail = parts[idx + 1:-1]
        if len(tail) >= 2:
            return tail[1]
        if tail:
            return tail[0]
    return ""


def _boolean_prompt(flag: str, current_value: bool, environment: str) -> str:
    action = "Disable" if current_value else "Enable"
    where = f" in {environment}" if environment else ""
    return f"{action} {flag}{where}"


def _module_consumer_prompt(module_name: str, environment: str) -> str:
    where = f" in {environment}" if environment else ""
    return (
        f"Add a new resource{where} that reuses the existing "
        f"{module_name} module pattern already used in this repository"
    )


# --------------------------------------------------------------------------- #
# Default external adapters (reuse existing production helpers)
# --------------------------------------------------------------------------- #
def _default_tree_fn(owner: str, repo: str, branch: str, token: str) -> List[str]:
    from shared_code import repo_chat_context
    return repo_chat_context.list_repo_tree_paths(owner, repo, branch=branch, token=token)


def _default_fetch_fn(owner: str, repo: str, path: str, branch: str, token: str) -> str:
    from shared_code import repo_chat_context
    return repo_chat_context.fetch_repo_file_content(owner, repo, path, ref=branch, token=token)


def _default_retrieval_fn(prompt: str, owner: str, repo: str, branch: str, token: str) -> Dict[str, Any]:
    from shared_code import repo_chat_context
    return repo_chat_context.build_live_repo_chat_context(prompt, owner, repo, branch=branch, token=token)


def _default_verify_fn(owner: str, repo: str, path: str, branch: str) -> bool:
    from shared_code import terrabot_service
    return terrabot_service.github_get_file_content_by_repo(owner, repo, path, ref=branch) is not None


def _default_backend_call(request: Dict[str, Any]):
    """Drive a case through the real backend workflow (not the generator)."""
    from shared_code import terrabot_service
    return terrabot_service.handle_chat_request(request)


def _default_primary_loaded(cloud: str, repo_target: str, environment: str) -> bool:
    try:
        from shared_code import primary_context
        return bool(
            primary_context.load_primary_terraform_context(
                cloud=cloud, repo_target=repo_target, environment=environment
            ).get("loaded")
        )
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Case discovery
# --------------------------------------------------------------------------- #
def discover_cases_for_target(
    target: Dict[str, str],
    tree_fn: Callable[..., List[str]],
    fetch_fn: Callable[..., str],
    token: str,
    owner: str,
) -> List[Dict[str, Any]]:
    """Build live cases for one repository from its current HEAD contents."""
    cloud = target["cloud"]
    repo = target["repo"]
    branch = target["branch"]
    repo_target = target["repo_target"]

    tree = tree_fn(owner, repo, branch, token)
    cases: List[Dict[str, Any]] = []

    # Candidate value files: tfvars for Azure, hub env main.tf for AWS.
    if cloud == "azure":
        value_files = [p for p in tree if p.endswith(".tfvars") and p.startswith("vars/")]

        # Prefer environment-scoped files so prompts read naturally: an
        # env tier.tfvars first, then a hub.tfvars, then shared common.tfvars.
        def _azure_rank(path: str) -> tuple:
            name = path.rsplit("/", 1)[-1]
            order = {"tier.tfvars": 0, "hub.tfvars": 1, "common.tfvars": 2}.get(name, 3)
            return (order, len(path))

        value_files.sort(key=_azure_rank)
    else:
        value_files = [
            p for p in tree
            if p.endswith("main.tf") and ("/dev_aws/" in f"/{p}" or "/prod_aws/" in f"/{p}")
        ]
        value_files.sort(key=lambda p: len(p))

    # --- Boolean modification + existing-resource modification cases --------- #
    for path in value_files[:8]:
        content = fetch_fn(owner, repo, path, branch, token)
        if not content:
            continue
        assignments = find_boolean_assignments(content)
        if assignments:
            picked = assignments[0]
            env = environment_from_path(path)
            cases.append({
                "type": "boolean_modification",
                "cloud": cloud,
                "repo_target": repo_target,
                "repo": repo,
                "branch": branch,
                "environment": env,
                "target_path": path,
                "flag": picked["flag"],
                "current_value": picked["value"],
                "desired_value": not picked["value"],
                "prompt": _boolean_prompt(picked["flag"], picked["value"], env),
                "mode": "infra",
            })
            break

    # --- Existing-module / new-consumer case -------------------------------- #
    tf_files = [p for p in tree if p.endswith(".tf") and "/modules/" not in f"/{p}"]
    for path in tf_files[:15]:
        content = fetch_fn(owner, repo, path, branch, token)
        if not content:
            continue
        modules = find_module_blocks(content)
        if modules:
            module = modules[0]
            env = environment_from_path(path) or _first_environment_hint(tree, cloud)
            cases.append({
                "type": "existing_module_new_consumer",
                "cloud": cloud,
                "repo_target": repo_target,
                "repo": repo,
                "branch": branch,
                "environment": env,
                "target_path": path,
                "module": module["name"],
                "module_source": module["source"],
                "prompt": _module_consumer_prompt(module["name"], env),
                "mode": "infra",
            })
            break

    # --- Repository-context regression case --------------------------------- #
    # Reuse a discovered flag so the retrieval assertion targets a file that
    # provably exists right now.
    bool_case = next((c for c in cases if c["type"] == "boolean_modification"), None)
    if bool_case:
        cases.append({
            "type": "repository_context_regression",
            "cloud": cloud,
            "repo_target": repo_target,
            "repo": repo,
            "branch": branch,
            "environment": bool_case["environment"],
            "target_path": bool_case["target_path"],
            "flag": bool_case["flag"],
            "prompt": f"Which repository file sets {bool_case['flag']}?",
            "mode": "chat",
        })

    return cases


def _first_environment_hint(tree: List[str], cloud: str) -> str:
    for path in tree:
        env = environment_from_path(path)
        if env:
            return env
    return ""


# --------------------------------------------------------------------------- #
# Case execution
# --------------------------------------------------------------------------- #
def _blank_result(case: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "case_id": case.get("case_id"),
        "type": case.get("type"),
        "cloud": case.get("cloud"),
        "repo_target": case.get("repo_target"),
        "environment": case.get("environment"),
        "target_path": case.get("target_path"),
        "flag": case.get("flag"),
        "prompt": case.get("prompt"),
        "target_found": False,
        "flag_control_detected": bool(case.get("flag") or case.get("module")),
        "primary_context_loaded": False,
        "repository_context_retrieved": False,
        "repository_context_useful": False,
        "generated_file": False,
        "validation": False,
        "branch_pushed": False,
        "attempts": 0,
        "duration_seconds": 0.0,
        "failure_reason": "",
    }


def execute_case(
    case: Dict[str, Any],
    run_id: str,
    owner: str,
    token: str,
    *,
    verify_fn: Callable[..., bool],
    retrieval_fn: Callable[..., Dict[str, Any]],
    backend_call: Callable[..., Any],
    primary_loaded_fn: Callable[..., bool],
) -> Dict[str, Any]:
    """Execute one case end-to-end and return its independent result record."""
    started = time.time()
    result = _blank_result(case)
    repo = case["repo"]
    branch = case["branch"]
    path = case["target_path"]

    result["primary_context_loaded"] = bool(
        primary_loaded_fn(case.get("cloud", ""), case.get("repo_target", ""), case.get("environment", ""))
    )

    # (1) Verify the selected target still exists at HEAD before executing.
    try:
        result["target_found"] = bool(verify_fn(owner, repo, path, branch))
    except Exception as exc:
        result["failure_reason"] = f"head_verify_error: {exc}"
    if not result["target_found"]:
        result["failure_reason"] = result["failure_reason"] or "target_missing_at_head"
        result["duration_seconds"] = round(time.time() - started, 3)
        _log_case_result(run_id, result)
        return result

    # (2) Repository-context retrieval (existing live-repo retrieval helper).
    try:
        retrieved = retrieval_fn(case["prompt"], owner, repo, branch, token) or {}
        paths = list(retrieved.get("paths") or [])
        block = str(retrieved.get("context_block") or "")
        result["repository_context_retrieved"] = bool(paths)
        flag = str(case.get("flag") or "")
        result["repository_context_useful"] = bool(
            (path in paths)
            or (flag and flag.lower() in block.lower())
        )
    except Exception as exc:
        result["failure_reason"] = f"retrieval_error: {exc}"

    # (3) Real backend execution (discovery -> primary context -> retrieval ->
    #     Foundry -> validators/repairs -> preview), then branch push. The
    #     regression case only exercises retrieval, so it stops here.
    if case.get("mode") == "infra":
        attempts = 0
        try:
            request = {
                "prompt": case["prompt"],
                "mode": "infra",
                "cloud": case["cloud"],
                "requested_cloud": case["cloud"],
                "workflow": _infra_workflow_for_cloud(case["cloud"]),
                "repo_target": case["repo_target"],
                "environment": case.get("environment", ""),
                "source": "teams",  # bypasses the interactive JIRA gate
                "run_id": run_id,
                "case_id": case["case_id"],
                "teams_conversation_id": f"{run_id}:{case['case_id']}",
            }
            attempts += 1
            backend_result, _status = _unpack(backend_call(request))
            result["generated_file"] = bool(backend_result.get("files"))
            result["validation"] = bool(
                backend_result.get("validation_commands")
                or backend_result.get("mode") == "infra_preview"
            )
            result["attempts"] = int(backend_result.get("attempts") or attempts)
            if not backend_result.get("ok", True):
                result["failure_reason"] = (
                    result["failure_reason"] or str(backend_result.get("reply") or "backend_not_ok")
                )

            # (4) Branch push through the same backend commit path.
            pending_change_id = str(backend_result.get("pending_change_id") or "").strip()
            thread_id = str(backend_result.get("thread_id") or "").strip()
            if pending_change_id:
                commit_request = {
                    "action": "commit_branch",
                    "pending_change_id": pending_change_id,
                    "thread_id": thread_id,
                    "cloud": case["cloud"],
                    "source": "teams",
                    "run_id": run_id,
                    "case_id": case["case_id"],
                    "teams_conversation_id": request["teams_conversation_id"],
                }
                attempts += 1
                commit_result, _cstatus = _unpack(backend_call(commit_request))
                result["branch_pushed"] = bool(
                    commit_result.get("branch_url")
                    or commit_result.get("pr_url")
                    or commit_result.get("branch")
                    or commit_result.get("committed")
                )
                result["attempts"] = max(result["attempts"], attempts)
                if not result["branch_pushed"] and not result["failure_reason"]:
                    result["failure_reason"] = str(commit_result.get("reply") or "branch_not_pushed")
        except Exception as exc:
            result["failure_reason"] = result["failure_reason"] or f"backend_error: {exc}"
            result["attempts"] = max(result["attempts"], attempts)

    result["duration_seconds"] = round(time.time() - started, 3)
    _log_case_result(run_id, result)
    return result


def _infra_workflow_for_cloud(cloud: str) -> str:
    return "aws_infra_modification" if cloud == "aws" else "azure_infra_modification"


def _unpack(value: Any):
    """Backend handlers return (result_dict, status); tolerate a bare dict."""
    if isinstance(value, tuple) and len(value) == 2:
        result, status = value
        return (result if isinstance(result, dict) else {}), status
    if isinstance(value, dict):
        return value, 200
    return {}, 0


def _log_case_result(run_id: str, result: Dict[str, Any]) -> None:
    """Emit one secret-free structured log line with every required field."""
    LOGGER.info(
        "TERRABOT-TEST-RESULT run_id=%s case_id=%s type=%s repo=%s environment=%s "
        "target_found=%s flag_control_detected=%s primary_context_loaded=%s "
        "repository_context_retrieved=%s repository_context_useful=%s "
        "generated_file=%s validation=%s branch_pushed=%s attempts=%s "
        "duration=%.3fs failure_reason=%s constructed_prompt=%r",
        run_id,
        result.get("case_id"),
        result.get("type"),
        result.get("repo_target"),
        result.get("environment") or "(none)",
        result.get("target_found"),
        result.get("flag_control_detected"),
        result.get("primary_context_loaded"),
        result.get("repository_context_retrieved"),
        result.get("repository_context_useful"),
        result.get("generated_file"),
        result.get("validation"),
        result.get("branch_pushed"),
        result.get("attempts"),
        float(result.get("duration_seconds") or 0.0),
        result.get("failure_reason") or "(none)",
        str(result.get("prompt") or "")[:200],
    )


# --------------------------------------------------------------------------- #
# Aggregation + reporting
# --------------------------------------------------------------------------- #
def aggregate(run_id: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(results)
    def count(field: str) -> int:
        return sum(1 for r in results if r.get(field))
    passed = sum(
        1 for r in results
        if r.get("target_found") and not r.get("failure_reason")
    )
    return {
        "run_id": run_id,
        "total_cases": total,
        "passed": passed,
        "failed": total - passed,
        "target_found": count("target_found"),
        "flag_control_detected": count("flag_control_detected"),
        "primary_context_loaded": count("primary_context_loaded"),
        "repository_context_retrieved": count("repository_context_retrieved"),
        "repository_context_useful": count("repository_context_useful"),
        "generated_file": count("generated_file"),
        "validation": count("validation"),
        "branch_pushed": count("branch_pushed"),
        "cases": results,
    }


def format_teams_summary(aggregate_result: Dict[str, Any]) -> str:
    """Render ONE aggregated Teams-ready message from the run."""
    a = aggregate_result
    lines = [
        f"**Terrabot live test run** `{a['run_id']}`",
        f"Cases: {a['total_cases']} · Passed: {a['passed']} · Failed: {a['failed']}",
        "",
        "**Aggregate signals**",
        f"- Target found: {a['target_found']}/{a['total_cases']}",
        f"- Flag/control detected: {a['flag_control_detected']}/{a['total_cases']}",
        f"- Primary context loaded: {a['primary_context_loaded']}/{a['total_cases']}",
        f"- Repository context retrieved: {a['repository_context_retrieved']}/{a['total_cases']}",
        f"- Repository context useful: {a['repository_context_useful']}/{a['total_cases']}",
        f"- Generated file: {a['generated_file']}/{a['total_cases']}",
        f"- Validation: {a['validation']}/{a['total_cases']}",
        f"- Branch pushed: {a['branch_pushed']}/{a['total_cases']}",
        "",
        "**Cases**",
    ]
    for c in a["cases"]:
        status = "PASS" if (c.get("target_found") and not c.get("failure_reason")) else "FAIL"
        detail = c.get("failure_reason") or (
            f"file={'yes' if c.get('generated_file') else 'no'} "
            f"branch={'yes' if c.get('branch_pushed') else 'no'}"
        )
        lines.append(
            f"- [{status}] {c.get('type')} ({c.get('repo_target')}/{c.get('environment') or '-'}): "
            f"\"{c.get('prompt')}\" → {detail}"
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run_suite(
    config: Optional[RunnerConfig] = None,
    *,
    run_id: str = "",
    tree_fn: Callable[..., List[str]] = _default_tree_fn,
    fetch_fn: Callable[..., str] = _default_fetch_fn,
    verify_fn: Callable[..., bool] = _default_verify_fn,
    retrieval_fn: Callable[..., Dict[str, Any]] = _default_retrieval_fn,
    backend_call: Callable[..., Any] = _default_backend_call,
    primary_loaded_fn: Callable[..., bool] = _default_primary_loaded,
) -> Dict[str, Any]:
    """Discover, verify, execute, and aggregate the live Terrabot test suite."""
    config = config or RunnerConfig.from_env()
    run_id = run_id or f"tbtest-{uuid.uuid4().hex[:10]}"

    targets = config.targets()
    LOGGER.info(
        "TERRABOT-TEST-RUN-START run_id=%s owner=%s targets=%s",
        run_id, config.owner or "(unset)", [t["repo_target"] for t in targets] or "(none)",
    )
    if not targets:
        LOGGER.warning(
            "TERRABOT-TEST-RUN-START run_id=%s: no repositories resolved from env "
            "(set GITHUB_OWNER and GITHUB_AZURE_REPO/GITHUB_AWS_REPO).", run_id,
        )

    results: List[Dict[str, Any]] = []
    case_index = 0
    for target in targets:
        try:
            cases = discover_cases_for_target(target, tree_fn, fetch_fn, config.token, config.owner)
        except Exception as exc:
            LOGGER.warning(
                "TERRABOT-TEST-DISCOVERY-ERROR run_id=%s repo=%s: %s",
                run_id, target.get("repo_target"), exc,
            )
            cases = []
        LOGGER.info(
            "TERRABOT-TEST-DISCOVERY run_id=%s repo=%s discovered=%s types=%s",
            run_id, target.get("repo_target"), len(cases), [c["type"] for c in cases],
        )
        for case in cases:
            case_index += 1
            case["case_id"] = f"c{case_index:02d}-{case['type']}"
            results.append(
                execute_case(
                    case, run_id, config.owner, config.token,
                    verify_fn=verify_fn,
                    retrieval_fn=retrieval_fn,
                    backend_call=backend_call,
                    primary_loaded_fn=primary_loaded_fn,
                )
            )

    summary = aggregate(run_id, results)
    LOGGER.info(
        "TERRABOT-TEST-RUN-END run_id=%s total=%s passed=%s failed=%s",
        run_id, summary["total_cases"], summary["passed"], summary["failed"],
    )
    summary["teams_summary"] = format_teams_summary(summary)
    return summary
