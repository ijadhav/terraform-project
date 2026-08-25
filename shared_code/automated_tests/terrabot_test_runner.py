"""Repository-derived automated tests for the Terrabot Teams workflow.

This module is deliberately isolated from ``teams_bot.py`` and the stateful
Terrabot service core.  The public adapter accepts the already-loaded core
module and exercises the same production Teams backend entrypoint without
creating branches or pull requests.

The workflow is intentionally two phase:

1. Derive a deterministic Boolean-control test case from live GitHub, submit a
   natural-language prompt through the real Teams backend, automatically answer
   a repository target clarification when one is required, run the existing
   deterministic pre-commit validators without writing to GitHub, and ensure a
   validated repository-context mapping exists.
2. Start a fresh synthetic Teams conversation and submit a paraphrase.  The
   test passes the context-reuse assertion only when the stored repository
   context can be retrieved and Terrabot resolves the target without another
   clarification.

No generated Terraform is committed by this runner.  A test never sends the
normal Teams ``yes``/commit or Jira/PR actions.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from shared_code import repository_context

LOGGER = logging.getLogger("terrabot.automated_tests")
LOGGER.setLevel(logging.INFO)

TEST_COMMAND_RE = re.compile(
    r"^\s*run\s+tests(?:\s+(aws|azure|all))?(?:\s+(\d{1,2}))?\s*$",
    re.IGNORECASE,
)

_BOOLEAN_ASSIGNMENT_RE = re.compile(
    r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(true|false)\s*(?:#.*)?$"
)

_FEATURE_NAME_RE = re.compile(
    r"^(?:create_|enable_|enabled_|deploy_|use_|has_|is_)(.+)$|^(.+?)_enabled$",
    re.IGNORECASE,
)

_MAX_CASES = max(1, min(int(os.getenv("TERRABOT_TEST_RUNNER_MAX_CASES", "10")), 20))
_DEFAULT_CASES = max(1, min(int(os.getenv("TERRABOT_TEST_RUNNER_DEFAULT_CASES", "2")), _MAX_CASES))
_SCAN_FILE_LIMIT = max(10, min(int(os.getenv("TERRABOT_TEST_RUNNER_SCAN_FILES", "45")), 150))
_TREE_PATH_LIMIT = max(200, min(int(os.getenv("TERRABOT_TEST_RUNNER_TREE_PATH_LIMIT", "12000")), 50000))


def _diag(event: str, level: str = "info", **fields: Any) -> None:
    parts = [f"event={event}", f"level={level}"]
    for key, value in fields.items():
        text = re.sub(r"\s+", " ", str(value if value is not None else "")).strip()
        if len(text) > 400:
            text = text[:397] + "..."
        parts.append(f"{key}={text}")
    message = "[TerrabotTest] " + " ".join(parts)
    if level in {"warning", "error"}:
        LOGGER.warning(message)
    else:
        LOGGER.info(message)
    try:
        print(message, flush=True)
    except Exception:
        pass


def is_automated_test_command(prompt: str) -> bool:
    return bool(TEST_COMMAND_RE.fullmatch(str(prompt or "").strip()))


def _parse_command(prompt: str) -> tuple[str, int]:
    match = TEST_COMMAND_RE.fullmatch(str(prompt or "").strip())
    if not match:
        raise ValueError("Unsupported automated test command.")
    cloud = str(match.group(1) or "all").lower()
    count = int(match.group(2) or _DEFAULT_CASES)
    return cloud, max(1, min(count, _MAX_CASES))


def _authorized_aad_ids() -> set[str]:
    raw = os.getenv("TERRABOT_TEST_RUNNER_ALLOWED_AAD_OBJECT_IDS", "")
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _assert_authorized(aad_object_id: str) -> None:
    enabled = os.getenv("TERRABOT_TEST_RUNNER_ENABLED", "false").strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        raise PermissionError(
            "Terrabot automated Teams tests are disabled. Set "
            "TERRABOT_TEST_RUNNER_ENABLED=true to enable them."
        )
    allowed = _authorized_aad_ids()
    caller = str(aad_object_id or "").strip().lower()
    if not caller or caller not in allowed:
        raise PermissionError(
            "This Teams identity is not authorized to run Terrabot automated tests."
        )


@dataclass(frozen=True)
class RepositorySpec:
    cloud: str
    owner: str
    repo: str
    branch: str


@dataclass(frozen=True)
class TestCase:
    __test__ = False

    case_id: str
    cloud: str
    owner: str
    repo: str
    branch: str
    commit_sha: str
    path: str
    environment: str
    flag: str
    alias: str
    current_value: bool
    desired_value: bool
    evidence_line: str
    phase1_prompt: str
    phase2_prompt: str


@dataclass
class TestCaseResult:
    __test__ = False

    case: TestCase
    phase1_ok: bool = False
    phase1_clarified: bool = False
    phase1_target_ok: bool = False
    validation_ok: bool = False
    validation_error: str = ""
    context_stored: bool = False
    context_hit: bool = False
    phase2_ok: bool = False
    phase2_target_ok: bool = False
    phase2_reused_without_clarification: bool = False
    bot_calls: int = 0
    duration_ms: int = 0
    error: str = ""
    score: int = 0
    actual_file: str = ""
    actual_mode: str = ""


@dataclass
class TestRunResult:
    __test__ = False

    run_id: str
    requested_cases: int
    cases: list[TestCaseResult] = field(default_factory=list)
    discovery_errors: list[str] = field(default_factory=list)
    duration_ms: int = 0


def _humanize_flag(flag: str) -> str:
    value = str(flag or "").strip().lower()
    match = _FEATURE_NAME_RE.match(value)
    if match:
        value = match.group(1) or match.group(2) or value
    value = re.sub(r"_+", " ", value).strip()
    return value


def _infer_environment(path: str) -> str:
    parts = [part for part in str(path or "").replace("\\", "/").split("/") if part]
    if len(parts) < 2:
        return "repository"
    return parts[-2]


def _path_priority(path: str) -> tuple[int, int, str]:
    normalized = str(path or "").lower()
    basename = normalized.rsplit("/", 1)[-1]
    score = 0
    if basename == "main.tf":
        score += 7
    if basename.endswith(".tfvars"):
        score += 6
    if basename in {"hub.tfvars", "terraform.tfvars"}:
        score += 3
    if "/modules/" in f"/{normalized}/" or "/module/" in f"/{normalized}/":
        score -= 8
    if "/test" in f"/{normalized}" or "/examples/" in f"/{normalized}/":
        score -= 7
    score += min(normalized.count("/"), 5)
    return (-score, len(normalized), normalized)


def _flag_priority(flag: str) -> int:
    lower = str(flag or "").lower()
    score = 0
    if lower.startswith(("create_", "enable_", "deploy_")):
        score += 6
    if lower.endswith("_enabled"):
        score += 5
    if lower.startswith(("is_", "has_", "use_")):
        score += 2
    if len(_humanize_flag(lower).split()) >= 2:
        score += 2
    return score


def _extract_boolean_candidates(path: str, content: str) -> list[dict[str, Any]]:
    """Return deterministic feature-like Boolean assignments from one file."""
    results: list[dict[str, Any]] = []
    for match in _BOOLEAN_ASSIGNMENT_RE.finditer(str(content or "")):
        flag = match.group(1)
        alias = _humanize_flag(flag)
        if not alias or alias == flag.lower() or len(alias) < 3:
            # Exact technical booleans are still valid, but the automated
            # learning test needs a semantic alias distinct from the identifier.
            continue
        line = match.group(0).strip()
        results.append(
            {
                "path": path,
                "environment": _infer_environment(path),
                "flag": flag,
                "alias": alias,
                "current_value": match.group(2).lower() == "true",
                "evidence_line": line,
                "priority": _flag_priority(flag),
            }
        )
    results.sort(key=lambda item: (-int(item["priority"]), item["flag"]))
    return results


def _github_recursive_tree(core: Any, spec: RepositorySpec) -> tuple[str, list[str]]:
    commit_sha = core.github_get_base_branch_sha_by_repo(spec.owner, spec.repo, spec.branch)
    commit_url = f"{core.GITHUB_API}/repos/{spec.owner}/{spec.repo}/git/commits/{commit_sha}"
    commit_response = core.requests.get(commit_url, headers=core.github_headers(), timeout=30)
    commit_response.raise_for_status()
    tree_sha = str(((commit_response.json() or {}).get("tree") or {}).get("sha") or "").strip()
    if not tree_sha:
        raise RuntimeError(f"GitHub did not return a tree SHA for {spec.owner}/{spec.repo}@{spec.branch}.")

    tree_url = f"{core.GITHUB_API}/repos/{spec.owner}/{spec.repo}/git/trees/{tree_sha}"
    tree_response = core.requests.get(
        tree_url,
        headers=core.github_headers(),
        params={"recursive": "1"},
        timeout=60,
    )
    tree_response.raise_for_status()
    payload = tree_response.json() or {}
    if payload.get("truncated"):
        _diag(
            "repository_tree_truncated",
            level="warning",
            repo=f"{spec.owner}/{spec.repo}",
            branch=spec.branch,
        )
    paths = [
        str(item.get("path") or "")
        for item in (payload.get("tree") or [])[:_TREE_PATH_LIMIT]
        if isinstance(item, dict)
        and item.get("type") == "blob"
        and str(item.get("path") or "").lower().endswith((".tf", ".tfvars"))
    ]
    return commit_sha, paths


def _build_prompt(alias: str, environment: str, desired_value: bool, *, phase: int) -> str:
    env = str(environment or "repository").strip()
    if desired_value:
        if phase == 1:
            return f"turn {alias} on in {env}"
        return f"enable {alias} for {env}"
    if phase == 1:
        return f"turn {alias} off in {env}"
    return f"disable {alias} for {env}"


def _derive_cases_for_repository(
    core: Any,
    spec: RepositorySpec,
    *,
    wanted: int,
    run_id: str,
) -> list[TestCase]:
    commit_sha, paths = _github_recursive_tree(core, spec)
    ranked_paths = sorted(paths, key=_path_priority)
    candidates: list[dict[str, Any]] = []
    files_read = 0

    for path in ranked_paths:
        if files_read >= _SCAN_FILE_LIMIT or len(candidates) >= max(wanted * 5, wanted + 4):
            break
        content = core.github_get_file_content_by_repo(spec.owner, spec.repo, path, ref=spec.branch)
        files_read += 1
        if not content:
            continue
        for candidate in _extract_boolean_candidates(path, content):
            candidates.append(candidate)

    # Prefer meaningful feature identifiers and diversify aliases/environments.
    candidates.sort(
        key=lambda item: (
            -int(item.get("priority") or 0),
            _path_priority(str(item.get("path") or "")),
            str(item.get("flag") or ""),
        )
    )
    selected: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in candidates:
        key = (str(item["environment"]).lower(), str(item["alias"]).lower())
        if key in seen:
            continue
        seen.add(key)
        selected.append(item)
        if len(selected) >= wanted:
            break

    cases: list[TestCase] = []
    for index, item in enumerate(selected, start=1):
        desired = not bool(item["current_value"])
        case_id = f"{spec.cloud}-{index:02d}-{hashlib.sha1((item['path'] + item['flag']).encode()).hexdigest()[:6]}"
        cases.append(
            TestCase(
                case_id=case_id,
                cloud=spec.cloud,
                owner=spec.owner,
                repo=spec.repo,
                branch=spec.branch,
                commit_sha=commit_sha,
                path=str(item["path"]),
                environment=str(item["environment"]),
                flag=str(item["flag"]),
                alias=str(item["alias"]),
                current_value=bool(item["current_value"]),
                desired_value=desired,
                evidence_line=str(item["evidence_line"]),
                phase1_prompt=_build_prompt(str(item["alias"]), str(item["environment"]), desired, phase=1),
                phase2_prompt=_build_prompt(str(item["alias"]), str(item["environment"]), desired, phase=2),
            )
        )

    _diag(
        "repository_cases_derived",
        run_id=run_id,
        repo=f"{spec.owner}/{spec.repo}",
        tree_paths=len(paths),
        files_read=files_read,
        boolean_candidates=len(candidates),
        selected=len(cases),
    )
    return cases


def _response_text(result: dict) -> str:
    parts = [
        str(result.get("summary") or ""),
        str(result.get("reply") or ""),
        str(result.get("analysis") or ""),
        str(result.get("questions") or ""),
        str(result.get("files") or ""),
        str(result.get("candidates") or ""),
    ]
    return "\n".join(parts).lower()


def _response_file_paths(result: dict) -> list[str]:
    paths: list[str] = []
    for item in result.get("files") or []:
        if isinstance(item, dict):
            path = item.get("path") or item.get("filename") or ""
        else:
            path = item
        path = str(path or "").strip()
        if path and path not in paths:
            paths.append(path)
    return paths


def _target_matches(case: TestCase, result: dict) -> tuple[bool, str]:
    paths = _response_file_paths(result)
    path_ok = case.path in paths or case.path.lower() in _response_text(result)
    flag_ok = case.flag.lower() in _response_text(result)
    actual_file = next((path for path in paths if path == case.path), paths[0] if paths else "")
    return bool(path_ok and flag_ok), actual_file


def _repo_matches(case: TestCase, result: dict) -> bool:
    repo_target = str(result.get("repo_target") or "").strip().lower()
    cloud = str(result.get("cloud") or "").strip().lower()
    if repo_target and (repo_target == case.repo.lower() or case.repo.lower() in repo_target):
        return True
    return cloud == case.cloud


def _pick_expected_candidate(case: TestCase, result: dict) -> str:
    best: tuple[int, str] = (0, "")
    for fallback_index, item in enumerate(result.get("candidates") or [], start=1):
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        flag = str(item.get("flag") or "").strip()
        text = str(item).lower()
        score = 0
        if path == case.path:
            score += 6
        if case.flag.lower() == flag.lower():
            score += 8
        elif case.flag.lower() in text:
            score += 4
        if case.alias.lower() in text:
            score += 1
        selection = str(item.get("index") or flag or path or fallback_index).strip()
        if score > best[0]:
            best = (score, selection)
    return best[1] if best[0] > 0 else ""


def _search_context(case: TestCase) -> dict:
    return repository_context.search_repository_context(
        repo_owner=case.owner,
        repo_name=case.repo,
        query=f"{case.alias} {case.flag} {case.environment}",
        current_commit_sha=case.commit_sha,
        top_k=8,
    )


def _matching_context_record(case: TestCase, search_result: dict) -> dict | None:
    for item in search_result.get("results") or []:
        if not isinstance(item, dict):
            continue
        text = " ".join(
            [
                str(item.get("subject") or ""),
                str(item.get("statement") or ""),
                " ".join(str(value) for value in (item.get("evidence_paths") or [])),
            ]
        ).lower()
        if case.flag.lower() in text and case.path.lower() in text:
            return item
    return None


def _ensure_context_mapping(core: Any, case: TestCase, run_id: str) -> bool:
    existing = _search_context(case)
    if _matching_context_record(case, existing):
        return True

    statement = (
        f"In {case.repo}, {case.alias} maps to Boolean control {case.flag} "
        f"in {case.path} for environment {case.environment}."
    )
    candidate = {
        "category": "resolved_clarification",
        "subject": case.alias,
        "scope": case.environment,
        "statement": statement,
        "confidence": 0.99,
        "validation_summary": (
            "Automated repository-derived Terrabot test verified this mapping "
            "against the current live GitHub file before indexing it."
        ),
        "evidence": [
            {
                "path": case.path,
                "excerpt": case.evidence_line,
                "reason": f"The live assignment proves the Boolean control {case.flag}.",
            }
        ],
    }

    def evidence_fetcher(owner: str, repo: str, path: str, ref: str) -> str | None:
        return core.github_get_file_content_by_repo(owner, repo, path, ref=ref)

    action = repository_context.add_repository_context(
        repo_owner=case.owner,
        repo_name=case.repo,
        evidence_commit_sha=case.commit_sha,
        evidence_branch=case.branch,
        source_task_hash=hashlib.sha256(f"{run_id}:{case.case_id}".encode()).hexdigest(),
        candidate=candidate,
        evidence_fetcher=evidence_fetcher,
    )
    return bool(action.get("stored"))


def _invoke_backend(core: Any, request: dict, result: TestCaseResult) -> tuple[dict, int]:
    result.bot_calls += 1
    return core.handle_teams_chat_request(request)


def _phase_request(case: TestCase, prompt: str, conversation_id: str, *, phase: int) -> dict:
    return {
        "prompt": prompt,
        "original_prompt": prompt,
        "thread_id": "",
        "teams_conversation_id": conversation_id,
        "memory_conversation_id": f"{conversation_id}::memory::{uuid.uuid4().hex}",
        "teams_requester": "terrabot-automated-test",
        "source": "teams",
        "test_mode": True,
        "automated_test_phase": phase,
        "fresh_infra_generation": True,
        "cloud": case.cloud,
        "requested_cloud": case.cloud,
    }


def _validate_preview(core: Any, backend_result: dict, prompt: str, thread_id: str) -> tuple[bool, str]:
    if str(backend_result.get("mode") or "").lower() != "infra_preview":
        return False, f"Expected infra_preview, received {backend_result.get('mode') or '<none>'}."
    if not backend_result.get("files"):
        return False, "No generated files were returned for dry-run validation."
    try:
        core._run_parallel_precommit_validations(backend_result, prompt, thread_id)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def _safe_reset(core: Any, conversation_id: str, result: dict) -> None:
    try:
        thread_id = str(result.get("thread_id") or "").strip()
        core.reset_teams_chat_session(conversation_id, thread_id)
    except Exception as exc:
        _diag("synthetic_session_reset_failed", level="warning", error=exc)


def _run_case(core: Any, case: TestCase, run_id: str, requester_id: str) -> TestCaseResult:
    started = time.monotonic()
    row = TestCaseResult(case=case)
    p1_conversation = f"terrabot-test::{requester_id}::{run_id}::{case.case_id}::p1"
    p2_conversation = f"terrabot-test::{requester_id}::{run_id}::{case.case_id}::p2"
    phase1_result: dict = {}
    phase2_result: dict = {}

    _diag(
        "test_case_started",
        run_id=run_id,
        test_case_id=case.case_id,
        repo=f"{case.owner}/{case.repo}",
        environment=case.environment,
        expected_path=case.path,
        expected_flag=case.flag,
    )

    try:
        phase1_request = _phase_request(case, case.phase1_prompt, p1_conversation, phase=1)
        phase1_result, status = _invoke_backend(core, phase1_request, row)
        row.actual_mode = str(phase1_result.get("mode") or "")
        row.phase1_ok = status < 500 and bool(phase1_result.get("ok", True))

        if str(phase1_result.get("mode") or "").lower() == "clarification":
            row.phase1_clarified = True
            selection = _pick_expected_candidate(case, phase1_result) or case.flag
            clarification_request = {
                "prompt": selection,
                "original_prompt": case.phase1_prompt,
                "thread_id": str(phase1_result.get("thread_id") or ""),
                "teams_conversation_id": p1_conversation,
                "memory_conversation_id": phase1_request["memory_conversation_id"],
                "teams_requester": "terrabot-automated-test",
                "source": "teams",
                "mode": "infra",
                "test_mode": True,
                "automated_test_phase": 1,
                "pending_target_selection_reply": True,
                "pending_target_selection_thread_id": str(phase1_result.get("thread_id") or ""),
                "fresh_infra_generation": True,
                "cloud": case.cloud,
                "requested_cloud": case.cloud,
            }
            phase1_result, status = _invoke_backend(core, clarification_request, row)
            row.actual_mode = str(phase1_result.get("mode") or "")
            row.phase1_ok = status < 500 and bool(phase1_result.get("ok", True))

        target_ok, actual_file = _target_matches(case, phase1_result)
        row.actual_file = actual_file
        row.phase1_target_ok = target_ok and _repo_matches(case, phase1_result)
        validation_thread = str(phase1_result.get("thread_id") or p1_conversation)
        row.validation_ok, row.validation_error = _validate_preview(
            core, phase1_result, case.phase1_prompt, validation_thread
        )

        # Only teach a mapping when the production backend selected the expected
        # live repository target and the same deterministic validators accept it.
        if row.phase1_target_ok and row.validation_ok:
            row.context_stored = _ensure_context_mapping(core, case, run_id)
        else:
            row.context_stored = False

        post_learning_search = _search_context(case)
        row.context_hit = _matching_context_record(case, post_learning_search) is not None

        # Phase 2 uses a fresh synthetic Teams conversation so thread/session
        # memory from Phase 1 cannot satisfy the request.
        phase2_request = _phase_request(case, case.phase2_prompt, p2_conversation, phase=2)
        phase2_result, status = _invoke_backend(core, phase2_request, row)
        row.phase2_ok = status < 500 and bool(phase2_result.get("ok", True))
        phase2_mode = str(phase2_result.get("mode") or "").lower()
        row.phase2_reused_without_clarification = row.context_hit and phase2_mode != "clarification"
        row.phase2_target_ok, _ = _target_matches(case, phase2_result)
        row.phase2_target_ok = row.phase2_target_ok and _repo_matches(case, phase2_result)

        assertions = [
            row.phase1_ok,
            row.phase1_target_ok,
            row.validation_ok,
            row.context_stored,
            row.context_hit,
            row.phase2_ok,
            row.phase2_target_ok,
            row.phase2_reused_without_clarification,
        ]
        row.score = round(100 * sum(bool(value) for value in assertions) / len(assertions))
    except Exception as exc:
        row.error = str(exc)
        _diag(
            "test_case_failed",
            level="error",
            run_id=run_id,
            test_case_id=case.case_id,
            error=exc,
        )
    finally:
        _safe_reset(core, p1_conversation, phase1_result)
        _safe_reset(core, p2_conversation, phase2_result)
        row.duration_ms = int((time.monotonic() - started) * 1000)

    _diag(
        "test_case_completed",
        run_id=run_id,
        test_case_id=case.case_id,
        phase1_target_ok=row.phase1_target_ok,
        validation_ok=row.validation_ok,
        context_hit=row.context_hit,
        phase2_target_ok=row.phase2_target_ok,
        context_reuse=row.phase2_reused_without_clarification,
        calls=row.bot_calls,
        duration_ms=row.duration_ms,
        score=row.score,
    )
    return row


def _repo_specs(core: Any, cloud_filter: str) -> list[RepositorySpec]:
    owner = str(getattr(core, "GITHUB_OWNER", "") or "").strip()
    specs: list[RepositorySpec] = []
    if cloud_filter in {"all", "aws"}:
        repo = str(getattr(core, "GITHUB_AWS_REPO", "") or "").strip()
        branch = str(getattr(core, "GITHUB_AWS_BASE_BRANCH", "") or "main").strip() or "main"
        if owner and repo:
            specs.append(RepositorySpec("aws", owner, repo, branch))
    if cloud_filter in {"all", "azure"}:
        repo = str(getattr(core, "GITHUB_AZURE_REPO", "") or "").strip()
        branch = str(getattr(core, "GITHUB_AZURE_BASE_BRANCH", "") or "main").strip() or "main"
        if owner and repo:
            specs.append(RepositorySpec("azure", owner, repo, branch))
    return specs


def _derive_test_cases(core: Any, cloud_filter: str, count: int, run_id: str) -> tuple[list[TestCase], list[str]]:
    specs = _repo_specs(core, cloud_filter)
    if not specs:
        return [], ["No configured GitHub repositories matched the requested cloud filter."]
    per_repo = max(1, (count + len(specs) - 1) // len(specs))
    cases: list[TestCase] = []
    errors: list[str] = []
    for spec in specs:
        try:
            cases.extend(_derive_cases_for_repository(core, spec, wanted=per_repo, run_id=run_id))
        except Exception as exc:
            message = f"{spec.cloud}:{spec.owner}/{spec.repo}: {exc}"
            errors.append(message)
            _diag("repository_case_generation_failed", level="error", run_id=run_id, error=message)
    return cases[:count], errors


def _escape_table(value: Any, limit: int = 56) -> str:
    text = re.sub(r"\s+", " ", str(value if value is not None else "")).strip()
    text = text.replace("|", "\\|")
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


def _status(value: bool) -> str:
    return "PASS" if value else "FAIL"


def format_test_run_report(run: TestRunResult) -> str:
    completed = len(run.cases)
    passed = sum(1 for item in run.cases if item.score == 100)
    average_score = round(sum(item.score for item in run.cases) / completed, 1) if completed else 0.0
    context_hits = sum(1 for item in run.cases if item.context_hit)
    context_reuse = sum(1 for item in run.cases if item.phase2_reused_without_clarification)
    validations = sum(1 for item in run.cases if item.validation_ok)
    avg_calls = round(sum(item.bot_calls for item in run.cases) / completed, 1) if completed else 0.0
    avg_seconds = round(sum(item.duration_ms for item in run.cases) / max(completed, 1) / 1000.0, 1)

    lines = [
        "**Terrabot automated repository-context test results**",
        f"Run ID: `{run.run_id}`",
        f"Cases: **{completed}/{run.requested_cases}** | Full passes: **{passed}** | Average accuracy: **{average_score}%**",
        f"Validation: **{validations}/{completed}** | Context hits: **{context_hits}/{completed}** | Fresh-session context reuse: **{context_reuse}/{completed}**",
        f"Average backend calls/case: **{avg_calls}** | Average case time: **{avg_seconds}s** | Total: **{round(run.duration_ms / 1000.0, 1)}s**",
        "",
        "| Test | Repo | Phase 1 prompt | Expected target | P1 target | Validation | Context | Phase 2 reuse | Calls | Time | Score |",
        "|---|---|---|---|---|---|---|---|---:|---:|---:|",
    ]
    for item in run.cases:
        case = item.case
        context_state = "PASS" if item.context_stored and item.context_hit else "FAIL"
        target = f"{case.path} :: {case.flag}"
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_table(case.case_id, 24),
                    _escape_table(case.repo, 20),
                    _escape_table(case.phase1_prompt, 42),
                    _escape_table(target, 52),
                    _status(item.phase1_target_ok),
                    _status(item.validation_ok),
                    context_state,
                    _status(item.phase2_reused_without_clarification and item.phase2_target_ok),
                    str(item.bot_calls),
                    f"{item.duration_ms / 1000.0:.1f}s",
                    f"{item.score}%",
                ]
            )
            + " |"
        )

    failures = [item for item in run.cases if item.score < 100]
    if failures:
        lines.extend(["", "**Failed assertions**"])
        for item in failures[:10]:
            reasons: list[str] = []
            if not item.phase1_target_ok:
                reasons.append("Phase 1 target mismatch")
            if not item.validation_ok:
                reasons.append("dry-run validation failed")
            if not item.context_stored or not item.context_hit:
                reasons.append("repository context was not verified")
            if not item.phase2_target_ok:
                reasons.append("Phase 2 target mismatch")
            if not item.phase2_reused_without_clarification:
                reasons.append("fresh Phase 2 required clarification or had no context hit")
            if item.error:
                reasons.append(item.error)
            elif item.validation_error and not item.validation_ok:
                reasons.append(item.validation_error)
            lines.append(f"- `{item.case.case_id}`: {_escape_table('; '.join(reasons), 300)}")

    if run.discovery_errors:
        lines.extend(["", "**Repository discovery warnings**"])
        lines.extend(f"- {_escape_table(value, 300)}" for value in run.discovery_errors)

    lines.extend([
        "",
        "No test generated a GitHub branch or pull request. Phase 1/2 synthetic Teams state was cleared after each case.",
        f"Search Function App logs with `run_id={run.run_id}` for the complete `[TerrabotTest]` execution trace.",
    ])
    return "\n".join(lines)


def _run_tests(core: Any, *, prompt: str, aad_object_id: str) -> TestRunResult:
    _assert_authorized(aad_object_id)
    cloud_filter, count = _parse_command(prompt)
    run_id = "ctx-" + time.strftime("%Y%m%d-%H%M%S", time.gmtime()) + "-" + uuid.uuid4().hex[:6]
    started = time.monotonic()
    _diag(
        "test_run_started",
        run_id=run_id,
        requester_hash=hashlib.sha256(aad_object_id.encode()).hexdigest()[:12],
        cloud=cloud_filter,
        requested_cases=count,
    )
    cases, discovery_errors = _derive_test_cases(core, cloud_filter, count, run_id)
    result = TestRunResult(run_id=run_id, requested_cases=count, discovery_errors=discovery_errors)
    for case in cases:
        result.cases.append(_run_case(core, case, run_id, aad_object_id))
    result.duration_ms = int((time.monotonic() - started) * 1000)
    _diag(
        "test_run_completed",
        run_id=run_id,
        requested_cases=count,
        completed_cases=len(result.cases),
        full_passes=sum(1 for item in result.cases if item.score == 100),
        duration_ms=result.duration_ms,
    )
    return result


def handle_teams_automated_test_request(core: Any, data: dict) -> tuple[dict, int]:
    """Run a private repository-derived test suite and return a Teams report."""
    prompt = str((data or {}).get("prompt") or "").strip()
    aad_object_id = str((data or {}).get("aad_object_id") or "").strip()
    if not is_automated_test_command(prompt):
        return {"ok": False, "reply": "Unsupported automated test command."}, 400
    try:
        run = _run_tests(core, prompt=prompt, aad_object_id=aad_object_id)
    except PermissionError as exc:
        _diag("test_run_denied", level="warning", reason=exc)
        return {"ok": False, "reply": str(exc), "mode": "automated_test"}, 403
    except Exception as exc:
        _diag("test_run_failed", level="error", error=exc)
        return {
            "ok": False,
            "reply": f"Terrabot automated test run failed before completion: {exc}",
            "mode": "automated_test",
        }, 500

    if not run.cases:
        reply = format_test_run_report(run)
        return {
            "ok": False,
            "mode": "automated_test",
            "run_id": run.run_id,
            "reply": reply,
            "results": [],
        }, 422

    return {
        "ok": True,
        "mode": "automated_test",
        "run_id": run.run_id,
        "reply": format_test_run_report(run),
        "results": [
            {
                "test_case_id": item.case.case_id,
                "repo": item.case.repo,
                "prompt": item.case.phase1_prompt,
                "expected_path": item.case.path,
                "expected_flag": item.case.flag,
                "phase1_target_ok": item.phase1_target_ok,
                "validation_ok": item.validation_ok,
                "context_stored": item.context_stored,
                "context_hit": item.context_hit,
                "phase2_target_ok": item.phase2_target_ok,
                "phase2_reused_without_clarification": item.phase2_reused_without_clarification,
                "bot_calls": item.bot_calls,
                "duration_ms": item.duration_ms,
                "score": item.score,
                "error": item.error or item.validation_error,
            }
            for item in run.cases
        ],
    }, 200
