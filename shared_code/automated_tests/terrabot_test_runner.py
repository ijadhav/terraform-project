"""Repository-derived automated tests for the Terrabot Teams workflow.

This module is deliberately isolated from ``teams_bot.py`` and the stateful
Terrabot service core.  The public adapter accepts the already-loaded core
module and exercises the same production Teams backend entrypoint without
creating pull requests. Phase 1 intentionally pushes validated changes to isolated test branches.

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

Validated Phase 1 Terraform is committed to an isolated Terrabot test branch so branch transport and post-commit context learning are tested. Phase 2 uses a fresh synthetic conversation and does not create a second branch. The runner never creates a pull request.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
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
_DEFAULT_CASES = max(1, min(int(os.getenv("TERRABOT_TEST_RUNNER_DEFAULT_CASES", "6")), _MAX_CASES))
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
    expected_target_found: bool = False
    correct_flag_detected: bool = False
    phase1_file_generated: bool = False
    validation_ok: bool = False
    validation_error: str = ""
    branch_pushed: bool = False
    branch_name: str = ""
    branch_url: str = ""
    context_stored: bool = False
    phase2_context_retrieved: bool = False
    phase2_ok: bool = False
    phase2_clarified: bool = False
    phase2_target_ok: bool = False
    phase2_file_generated: bool = False
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


def _infer_environment(path: str, cloud: str = "") -> str:
    normalized = str(path or "").replace("\\", "/").strip("/")
    cloud = str(cloud or "").strip().lower()
    if cloud == "aws":
        match = re.search(r"(?:^|/)terraform/(?:dev_aws|prod_aws|dev_services_aws)/([^/]+)(?:/|$)", normalized)
        if match:
            return match.group(1)
    if cloud == "azure":
        match = re.search(r"(?:^|/)vars/(?:npr|sbx|prd)/([^/]+)(?:/|$)", normalized)
        if match:
            return match.group(1)
    parts = [part for part in normalized.split("/") if part]
    return parts[-2] if len(parts) >= 2 else "repository"


def _prompt_alias(alias: str, cloud: str) -> str:
    """Keep generated language cloud-safe without changing the expected flag."""
    words = [word for word in re.split(r"\s+", str(alias or "").strip().lower()) if word]
    opposite = "azure" if str(cloud or "").lower() == "aws" else "aws"
    cleaned = [word for word in words if word != opposite]
    return " ".join(cleaned).strip() or str(alias or "").strip()


def _candidate_environment_is_valid(core: Any, spec: RepositorySpec, path: str, environment: str) -> bool:
    """Use Terrabot's own authoritative environment resolver before creating a prompt."""
    resolver = getattr(core, "resolve_teams_environment_targets", None)
    if not callable(resolver):
        return True
    probe = f"change terraform setting in {environment}"
    try:
        resolution = resolver(probe, cloud_hint=spec.cloud) or {}
    except TypeError:
        resolution = resolver(probe, spec.cloud) or {}
    except Exception:
        return False
    if resolution.get("error") or str(resolution.get("cloud") or "").lower() != spec.cloud:
        return False
    targets = [item for item in (resolution.get("targets") or []) if isinstance(item, dict)]
    if not targets:
        return False
    candidate_path = str(path or "").strip("/")
    for target in targets:
        if str(target.get("environment") or "").lower() != str(environment or "").lower():
            continue
        target_path = str(target.get("path") or "").strip("/")
        if not target_path or candidate_path == target_path or candidate_path.startswith(target_path + "/"):
            return True
    return False


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
    action = "enable" if desired_value else "disable"
    if phase == 1:
        templates = [
            "please {action} {alias} in {env}",
            "can you {action} {alias} for {env}",
            "{action} {alias} on {env}",
            "for {env}, {action} {alias}",
            "I need {alias} {state} in {env}",
        ]
    else:
        templates = [
            "{action} {alias} for {env}",
            "please switch {alias} {state} in {env}",
            "can you turn {alias} {direction} on {env}",
            "for {env}, set {alias} {state}",
            "make {alias} {state} in {env}",
        ]
    template = secrets.choice(templates)
    return template.format(
        action=action,
        alias=alias,
        env=env,
        state="on" if desired_value else "off",
        direction="on" if desired_value else "off",
    )


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

    # Read a wider pool than the final sample, then randomize. This prevents
    # every invocation from repeatedly choosing the same top-ranked controls.
    candidate_goal = max(wanted * 12, wanted + 12)
    for path in ranked_paths:
        if files_read >= _SCAN_FILE_LIMIT or len(candidates) >= candidate_goal:
            break
        environment = _infer_environment(path, spec.cloud)
        if environment == "repository" or not _candidate_environment_is_valid(core, spec, path, environment):
            continue
        content = core.github_get_file_content_by_repo(spec.owner, spec.repo, path, ref=spec.branch)
        files_read += 1
        if not content:
            continue
        for candidate in _extract_boolean_candidates(path, content):
            candidate["environment"] = environment
            candidate["alias"] = _prompt_alias(str(candidate.get("alias") or ""), spec.cloud)
            if candidate["alias"]:
                candidates.append(candidate)

    # Feature priority still removes weak noise, but selection is randomized
    # within the strong candidate pool on every run.
    candidates.sort(key=lambda item: -int(item.get("priority") or 0))
    strong = candidates[: max(wanted * 8, wanted)]
    secrets.SystemRandom().shuffle(strong)

    selected: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in strong:
        key = (str(item["environment"]).lower(), str(item["alias"]).lower())
        if key in seen:
            continue
        seen.add(key)
        selected.append(item)
        if len(selected) >= wanted:
            break

    cases: list[TestCase] = []
    used_prompts: set[str] = set()
    for index, item in enumerate(selected, start=1):
        desired = not bool(item["current_value"])
        phase1 = _build_prompt(str(item["alias"]), str(item["environment"]), desired, phase=1)
        phase2 = _build_prompt(str(item["alias"]), str(item["environment"]), desired, phase=2)
        # Within one run prompts must be unique; regenerate wording if a random
        # template happened to collide.
        for _ in range(8):
            if phase1.lower() not in used_prompts and phase2.lower() not in used_prompts and phase1.lower() != phase2.lower():
                break
            phase1 = _build_prompt(str(item["alias"]), str(item["environment"]), desired, phase=1)
            phase2 = _build_prompt(str(item["alias"]), str(item["environment"]), desired, phase=2)
        used_prompts.update({phase1.lower(), phase2.lower()})
        case_id = f"{spec.cloud}-{index:02d}-{hashlib.sha1((item['path'] + item['flag'] + run_id).encode()).hexdigest()[:6]}"
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
                phase1_prompt=phase1,
                phase2_prompt=phase2,
            )
        )

    _diag(
        "repository_cases_derived",
        run_id=run_id,
        repo=f"{spec.owner}/{spec.repo}",
        cloud=spec.cloud,
        tree_paths=len(paths),
        files_read=files_read,
        boolean_candidates=len(candidates),
        selected=len(cases),
        environments=",".join(sorted({case.environment for case in cases})),
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


def _target_detection(case: TestCase, result: dict) -> tuple[bool, bool, bool, str]:
    paths = _response_file_paths(result)
    text = _response_text(result)
    expected_target_found = case.path in paths or case.path.lower() in text
    correct_flag_detected = case.flag.lower() in text
    file_generated = bool(paths)
    actual_file = next((path for path in paths if path == case.path), paths[0] if paths else "")
    return expected_target_found, correct_flag_detected, file_generated, actual_file


def _target_matches(case: TestCase, result: dict) -> tuple[bool, str]:
    target, flag, _file, actual = _target_detection(case, result)
    return bool(target and flag), actual


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


def _ensure_context_mapping(
    core: Any,
    case: TestCase,
    run_id: str,
    *,
    evidence_branch: str = "",
    evidence_commit_sha: str = "",
) -> bool:
    existing = _search_context(case)
    if _matching_context_record(case, existing):
        return True

    ref = str(evidence_branch or case.branch).strip()
    commit_sha = str(evidence_commit_sha or case.commit_sha).strip()
    live_content = core.github_get_file_content_by_repo(case.owner, case.repo, case.path, ref=ref) or ""
    evidence_line = case.evidence_line
    assignment = re.search(
        rf"(?m)^\s*{re.escape(case.flag)}\s*=\s*(?:true|false)\s*(?:#.*)?$",
        str(live_content),
        re.IGNORECASE,
    )
    if assignment:
        evidence_line = assignment.group(0).strip()

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
            "against the live GitHub file before indexing it."
        ),
        "evidence": [
            {
                "path": case.path,
                "excerpt": evidence_line,
                "reason": f"The live assignment proves the Boolean control {case.flag}.",
            }
        ],
    }

    def evidence_fetcher(owner: str, repo: str, path: str, ref_value: str) -> str | None:
        return core.github_get_file_content_by_repo(owner, repo, path, ref=ref_value)

    action = repository_context.add_repository_context(
        repo_owner=case.owner,
        repo_name=case.repo,
        evidence_commit_sha=commit_sha,
        evidence_branch=ref,
        source_task_hash=hashlib.sha256(f"{run_id}:{case.case_id}:{ref}".encode()).hexdigest(),
        candidate=candidate,
        evidence_fetcher=evidence_fetcher,
    )
    return bool(action.get("stored"))


def _branch_head_sha(core: Any, case: TestCase, branch: str) -> str:
    if not branch:
        return ""
    try:
        return str(core.github_get_base_branch_sha_by_repo(case.owner, case.repo, branch) or "").strip()
    except Exception:
        return ""


def _commit_preview_to_test_branch(
    core: Any,
    case: TestCase,
    run_id: str,
    preview: dict,
    original_request: dict,
) -> tuple[dict, int]:
    helper = getattr(core, "_teams_auto_commit_preview", None)
    if not callable(helper):
        return {"ok": False, "mode": "test_commit_unavailable", "reply": "_teams_auto_commit_preview is unavailable."}, 500
    commit_request = dict(original_request or {})
    commit_request.update({
        "force_new_branch": True,
        "reuse_branch": False,
        "existing_branch": "",
        "teams_requester": f"terrabot-test-{run_id[-6:]}-{case.case_id}",
        "test_mode": False,
        "automated_test_phase": 1,
    })
    return helper(commit_request, preview, 200)


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
        "force_new_branch": True,
        "reuse_branch": False,
        "existing_branch": "",
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
        cloud=case.cloud,
        environment=case.environment,
        phase1_prompt=case.phase1_prompt,
        phase2_prompt=case.phase2_prompt,
        expected_path=case.path,
        expected_flag=case.flag,
    )

    try:
        phase1_request = _phase_request(case, case.phase1_prompt, p1_conversation, phase=1)
        phase1_request["teams_requester"] = f"terrabot-test-{run_id[-6:]}-{case.case_id}"
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
                "teams_requester": phase1_request["teams_requester"],
                "source": "teams",
                "mode": "infra",
                "test_mode": True,
                "automated_test_phase": 1,
                "pending_target_selection_reply": True,
                "pending_target_selection_thread_id": str(phase1_result.get("thread_id") or ""),
                "fresh_infra_generation": True,
                "force_new_branch": True,
                "reuse_branch": False,
                "existing_branch": "",
                "cloud": case.cloud,
                "requested_cloud": case.cloud,
            }
            phase1_result, status = _invoke_backend(core, clarification_request, row)
            row.actual_mode = str(phase1_result.get("mode") or "")
            row.phase1_ok = status < 500 and bool(phase1_result.get("ok", True))

        (
            row.expected_target_found,
            row.correct_flag_detected,
            row.phase1_file_generated,
            row.actual_file,
        ) = _target_detection(case, phase1_result)
        row.expected_target_found = row.expected_target_found and _repo_matches(case, phase1_result)

        validation_thread = str(phase1_result.get("thread_id") or p1_conversation)
        if str(phase1_result.get("mode") or "").lower() == "infra_preview":
            row.validation_ok, row.validation_error = _validate_preview(
                core, phase1_result, case.phase1_prompt, validation_thread
            )
        elif str(phase1_result.get("mode") or "").lower() == "branch_created":
            # Branch creation is downstream of the production validation gate.
            row.validation_ok = bool(phase1_result.get("ok", True))
        else:
            row.validation_ok = False
            row.validation_error = f"Expected infra_preview before branch push, received {phase1_result.get('mode') or '<none>'}."

        branch_result = phase1_result
        branch_status = status
        if row.validation_ok and str(phase1_result.get("mode") or "").lower() == "infra_preview":
            branch_result, branch_status = _commit_preview_to_test_branch(
                core, case, run_id, phase1_result, phase1_request
            )
            row.bot_calls += 1

        row.branch_name = str(branch_result.get("branch") or "").strip()
        row.branch_url = str(branch_result.get("branch_url") or "").strip()
        row.branch_pushed = (
            branch_status < 400
            and bool(branch_result.get("ok", True))
            and str(branch_result.get("mode") or "").lower() == "branch_created"
            and bool(row.branch_name or row.branch_url)
        )
        _diag(
            "phase1_branch_result",
            run_id=run_id,
            test_case_id=case.case_id,
            branch_pushed=row.branch_pushed,
            branch=row.branch_name,
            mode=branch_result.get("mode"),
        )

        # Let the normal post-commit context workflow run first. If it did not
        # create this deterministic mapping, the isolated test harness adds the
        # verified mapping itself so the same run can still exercise Phase 2.
        context_search = _search_context(case)
        row.context_stored = _matching_context_record(case, context_search) is not None
        if not row.context_stored and row.branch_pushed and row.expected_target_found and row.correct_flag_detected:
            branch_sha = _branch_head_sha(core, case, row.branch_name)
            row.context_stored = _ensure_context_mapping(
                core,
                case,
                run_id,
                evidence_branch=row.branch_name or case.branch,
                evidence_commit_sha=branch_sha or case.commit_sha,
            )

        # Phase 2 retrieval is checked with the actual randomized paraphrase and
        # then exercised through a completely fresh Teams conversation.
        phase2_search = repository_context.search_repository_context(
            repo_owner=case.owner,
            repo_name=case.repo,
            query=case.phase2_prompt,
            current_commit_sha="",
            top_k=8,
        )
        row.phase2_context_retrieved = _matching_context_record(case, phase2_search) is not None

        phase2_request = _phase_request(case, case.phase2_prompt, p2_conversation, phase=2)
        phase2_request["teams_requester"] = f"terrabot-test-phase2-{run_id[-6:]}-{case.case_id}"
        phase2_result, status = _invoke_backend(core, phase2_request, row)
        row.phase2_ok = status < 500 and bool(phase2_result.get("ok", True))
        first_phase2_mode = str(phase2_result.get("mode") or "").lower()
        row.phase2_reused_without_clarification = row.phase2_context_retrieved and first_phase2_mode != "clarification"

        # Still continue a Phase 2 clarification so file-generation accuracy is
        # measured independently from context retrieval accuracy.
        if first_phase2_mode == "clarification":
            row.phase2_clarified = True
            selection = _pick_expected_candidate(case, phase2_result) or case.flag
            phase2_followup = {
                "prompt": selection,
                "original_prompt": case.phase2_prompt,
                "thread_id": str(phase2_result.get("thread_id") or ""),
                "teams_conversation_id": p2_conversation,
                "memory_conversation_id": phase2_request["memory_conversation_id"],
                "teams_requester": phase2_request["teams_requester"],
                "source": "teams",
                "mode": "infra",
                "test_mode": True,
                "automated_test_phase": 2,
                "pending_target_selection_reply": True,
                "pending_target_selection_thread_id": str(phase2_result.get("thread_id") or ""),
                "fresh_infra_generation": True,
                "force_new_branch": True,
                "reuse_branch": False,
                "existing_branch": "",
                "cloud": case.cloud,
                "requested_cloud": case.cloud,
            }
            phase2_result, status = _invoke_backend(core, phase2_followup, row)
            row.phase2_ok = status < 500 and bool(phase2_result.get("ok", True))

        p2_target, p2_flag, row.phase2_file_generated, _ = _target_detection(case, phase2_result)
        row.phase2_target_ok = p2_target and p2_flag and _repo_matches(case, phase2_result)

        assertions = [
            row.expected_target_found,
            row.correct_flag_detected,
            row.phase1_file_generated,
            row.validation_ok,
            row.branch_pushed,
            row.context_stored,
            row.phase2_context_retrieved,
            row.phase2_file_generated,
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
        expected_target_found=row.expected_target_found,
        correct_flag_detected=row.correct_flag_detected,
        phase1_file_generated=row.phase1_file_generated,
        validation_ok=row.validation_ok,
        branch_pushed=row.branch_pushed,
        context_stored=row.context_stored,
        phase2_context_retrieved=row.phase2_context_retrieved,
        phase2_file_generated=row.phase2_file_generated,
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

    # `run tests` defaults to six cases: exactly three AWS + three Azure.
    # Explicit larger all-cloud counts remain balanced as closely as possible.
    wanted_by_cloud: dict[str, int] = {}
    if cloud_filter == "all" and len(specs) >= 2:
        aws_count = count // 2
        azure_count = count - aws_count
        wanted_by_cloud = {"aws": aws_count, "azure": azure_count}
    else:
        wanted_by_cloud = {spec.cloud: count for spec in specs}

    cases: list[TestCase] = []
    errors: list[str] = []
    for spec in specs:
        wanted = max(0, wanted_by_cloud.get(spec.cloud, 0))
        if wanted <= 0:
            continue
        try:
            derived = _derive_cases_for_repository(core, spec, wanted=wanted, run_id=run_id)
            cases.extend(derived)
            if len(derived) < wanted:
                errors.append(f"{spec.cloud}:{spec.repo}: only {len(derived)}/{wanted} valid environment-scoped cases could be derived.")
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
    branches = sum(1 for item in run.cases if item.branch_pushed)
    contexts = sum(1 for item in run.cases if item.context_stored)
    p2_context = sum(1 for item in run.cases if item.phase2_context_retrieved)
    p2_files = sum(1 for item in run.cases if item.phase2_file_generated)
    avg_calls = round(sum(item.bot_calls for item in run.cases) / completed, 1) if completed else 0.0
    avg_seconds = round(sum(item.duration_ms for item in run.cases) / max(completed, 1) / 1000.0, 1)

    lines = [
        "**Terrabot automated repository-context test results**",
        f"Run ID: `{run.run_id}`",
        f"Cases: **{completed}/{run.requested_cases}** | Full passes: **{passed}** | Average accuracy: **{average_score}%**",
        f"Branches pushed: **{branches}/{completed}** | Context added: **{contexts}/{completed}** | Phase 2 context retrieved: **{p2_context}/{completed}** | Phase 2 files generated: **{p2_files}/{completed}**",
        f"Average backend calls/case: **{avg_calls}** | Average case time: **{avg_seconds}s** | Total: **{round(run.duration_ms / 1000.0, 1)}s**",
        "",
        "| Test | Cloud/Env | Phase 1 prompt | Expected target | Target found | Flag detected | P1 file | Validation | Branch pushed | Context added | P2 context | P2 file | Score |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---:|",
    ]
    for item in run.cases:
        case = item.case
        target = f"{case.path} :: {case.flag}"
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_table(case.case_id, 22),
                    _escape_table(f"{case.cloud}/{case.environment}", 22),
                    _escape_table(case.phase1_prompt, 38),
                    _escape_table(target, 50),
                    _status(item.expected_target_found),
                    _status(item.correct_flag_detected),
                    _status(item.phase1_file_generated),
                    _status(item.validation_ok),
                    _status(item.branch_pushed),
                    _status(item.context_stored),
                    _status(item.phase2_context_retrieved),
                    _status(item.phase2_file_generated),
                    f"{item.score}%",
                ]
            )
            + " |"
        )

    failures = [item for item in run.cases if item.score < 100]
    if failures:
        lines.extend(["", "**Failed assertions**"])
        for item in failures[:12]:
            reasons: list[str] = []
            if not item.expected_target_found:
                reasons.append("expected target not detected")
            if not item.correct_flag_detected:
                reasons.append("correct flag not detected")
            if not item.phase1_file_generated:
                reasons.append("Phase 1 file not generated")
            if not item.validation_ok:
                reasons.append("validation failed")
            if not item.branch_pushed:
                reasons.append("branch not pushed")
            if not item.context_stored:
                reasons.append("context not added")
            if not item.phase2_context_retrieved:
                reasons.append("Phase 2 context not retrieved")
            if not item.phase2_file_generated:
                reasons.append("Phase 2 file not generated")
            if not item.phase2_target_ok:
                reasons.append("Phase 2 target mismatch")
            if not item.phase2_reused_without_clarification:
                reasons.append("Phase 2 required clarification")
            if item.error:
                reasons.append(item.error)
            elif item.validation_error and not item.validation_ok:
                reasons.append(item.validation_error)
            branch_note = f" branch={item.branch_name}" if item.branch_name else ""
            lines.append(f"- `{item.case.case_id}`:{branch_note} {_escape_table('; '.join(reasons), 360)}")

    if run.discovery_errors:
        lines.extend(["", "**Repository discovery warnings**"])
        lines.extend(f"- {_escape_table(value, 300)}" for value in run.discovery_errors)

    lines.extend([
        "",
        "Phase 1 pushes each validated test change to its own Terrabot test branch; no pull request is created. Phase 2 uses a fresh synthetic Teams conversation and does not push another branch.",
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
                "expected_target_found": item.expected_target_found,
                "correct_flag_detected": item.correct_flag_detected,
                "phase1_file_generated": item.phase1_file_generated,
                "validation_ok": item.validation_ok,
                "branch_pushed": item.branch_pushed,
                "branch": item.branch_name,
                "branch_url": item.branch_url,
                "context_stored": item.context_stored,
                "phase2_context_retrieved": item.phase2_context_retrieved,
                "phase2_file_generated": item.phase2_file_generated,
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
