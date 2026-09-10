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

import concurrent.futures
import hashlib
import logging
import os
import re
import secrets
import time
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from shared_code import repository_context
from shared_code.automated_tests import terrabot_test_state
from shared_code.automated_tests import terrabot_semantic_engine
from shared_code.automated_tests import terrabot_cursor_result_validator
from shared_code.automated_tests import cursor_prompt_provider
from shared_code.automated_tests import terrabot_test_analysis
from shared_code.automated_tests import terrabot_test_coverage
from shared_code.automated_tests import terrabot_context_revalidation

LOGGER = logging.getLogger("terrabot.automated_tests")
LOGGER.setLevel(logging.INFO)

TEST_COMMAND_RE = re.compile(
    r"^\s*run\s+tests(?:\s+(aws|azure|all))?(?:\s+(\d{1,2}))?\s*$",
    re.IGNORECASE,
)
TEST_MODE_COMMAND_RE = re.compile(
    r"^\s*run\s+tests\s+(regression|exploration|context-regression|mixed)"
    r"(?:\s+(aws|azure|all))?(?:\s+(same))?(?:\s+(\d{1,2}))?\s*$",
    re.IGNORECASE,
)
TEST_REPEAT_RE = re.compile(
    r"^\s*run\s+tests\s+repeat\s+([A-Za-z0-9._:-]+)\s*$",
    re.IGNORECASE,
)
TEST_SAME_SUFFIX_RE = re.compile(
    r"^\s*run\s+tests\s+(regression|exploration|context-regression|mixed)"
    r"(?:\s+(aws|azure|all))?\s+(\d{1,2})\s+same\s*$",
    re.IGNORECASE,
)
TEST_STATUS_RE = re.compile(
    r"^\s*run\s+tests\s+status(?:\s+([A-Za-z0-9._:-]+))?\s*$",
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
_DEFAULT_CASES = max(1, min(int(os.getenv("TERRABOT_TEST_RUNNER_DEFAULT_CASES", "8")), _MAX_CASES))
_SCAN_FILE_LIMIT = max(10, min(int(os.getenv("TERRABOT_TEST_RUNNER_SCAN_FILES", "45")), 150))
_TREE_PATH_LIMIT = max(200, min(int(os.getenv("TERRABOT_TEST_RUNNER_TREE_PATH_LIMIT", "12000")), 50000))
_MAX_PARALLEL_CASES = max(1, min(int(os.getenv("TERRABOT_TEST_RUNNER_MAX_PARALLEL_CASES", "2")), 4))


def _diag(event: str, level: str = "info", **fields: Any) -> None:
    parts = [f"event={event}", f"level={level}"]
    for key, value in fields.items():
        text = re.sub(r"\s+", " ", str(value if value is not None else "")).strip()
        if len(text) > 400:
            text = text[:397] + "..."
        parts.append(f"{key}={text}")
    message = "[TerrabotTest] " + " ".join(parts)
    # Emit each diagnostic exactly once. In Azure Functions the logging
    # pipeline/root logger has handlers, so use structured logging. During
    # lightweight local/unit-test execution there may be no handlers; fall
    # back to stdout so diagnostics remain visible without triggering
    # logging.lastResort + print duplicates for warning/error events.
    if LOGGER.hasHandlers():
        if level in {"warning", "error"}:
            LOGGER.warning(message)
        else:
            LOGGER.info(message)
        return
    try:
        print(message, flush=True)
    except Exception:
        pass


def is_automated_test_command(prompt: str) -> bool:
    value = str(prompt or "").strip()
    return bool(TEST_COMMAND_RE.fullmatch(value) or TEST_MODE_COMMAND_RE.fullmatch(value) or TEST_SAME_SUFFIX_RE.fullmatch(value) or TEST_REPEAT_RE.fullmatch(value) or TEST_STATUS_RE.fullmatch(value))


def _parse_command(prompt: str) -> tuple[str, int]:
    value = str(prompt or "").strip()
    suffix_match = TEST_SAME_SUFFIX_RE.fullmatch(value)
    if suffix_match:
        cloud = str(suffix_match.group(2) or "all").lower()
        count = int(suffix_match.group(3) or _DEFAULT_CASES)
        return cloud, max(1, min(count, _MAX_CASES))
    mode_match = TEST_MODE_COMMAND_RE.fullmatch(value)
    if mode_match:
        cloud = str(mode_match.group(2) or "all").lower()
        count = int(mode_match.group(4) or _DEFAULT_CASES)
        return cloud, max(1, min(count, _MAX_CASES))
    match = TEST_COMMAND_RE.fullmatch(value)
    if not match:
        raise ValueError("Unsupported automated test command.")
    cloud = str(match.group(1) or "all").lower()
    count = int(match.group(2) or _DEFAULT_CASES)
    return cloud, max(1, min(count, _MAX_CASES))


def _parse_test_mode(prompt: str) -> str:
    value = str(prompt or "").strip()
    match = TEST_MODE_COMMAND_RE.fullmatch(value) or TEST_SAME_SUFFIX_RE.fullmatch(value)
    return str(match.group(1) if match else "regression").lower()


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
    case_type: str
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
    phase1_freeform_clarification: bool = False
    phase1_cursor_clarification_used: bool = False
    phase1_cursor_clarification_attempted: bool = False
    phase1_cursor_clarification_failed: bool = False
    phase1_cursor_clarification_error: str = ""
    phase1_cursor_unavailable_fallback_used: bool = False
    expected_target_found: bool = False
    correct_flag_detected: bool = False
    phase1_control_mentioned: bool = False
    phase2_control_mentioned: bool = False
    phase1_mode: str = ""
    phase2_mode: str = ""
    phase1_file_generated: bool = False
    validation_ok: bool = False
    validation_error: str = ""
    branch_pushed: bool = False
    branch_name: str = ""
    branch_url: str = ""
    context_stored: bool = False
    context_present_before: bool = False
    production_context_created: bool = False
    fallback_context_created: bool = False
    context_gap_detected: bool = False
    context_candidate_created: bool = False
    context_candidate_verified: bool = False
    context_candidate_promoted: bool = False
    phase2_context_retrieved: bool = False
    phase2_context_attached: bool = False
    phase2_context_useful: bool = False
    phase2_ok: bool = False
    phase2_clarified: bool = False
    phase2_freeform_clarification: bool = False
    phase2_cursor_clarification_used: bool = False
    phase2_cursor_clarification_attempted: bool = False
    phase2_cursor_clarification_failed: bool = False
    phase2_cursor_clarification_error: str = ""
    phase2_cursor_unavailable_fallback_used: bool = False
    resolved_workflow: str = ""
    phase2_context_backend_defect: bool = False
    phase2_target_ok: bool = False
    phase2_file_generated: bool = False
    phase2_reused_without_clarification: bool = False
    bot_calls: int = 0
    duration_ms: int = 0
    error: str = ""
    score: int = 0
    backend_score: int = 0
    actual_file: str = ""
    actual_mode: str = ""
    failure_classification: str = ""
    cursor_validation_requested: bool = False
    cursor_validation_completed: bool = False
    cursor_output_correct: bool = False
    cursor_context_added: bool = False
    cursor_context_retrievable: bool = False
    cursor_context_reused: bool = False
    cursor_overall_ok: bool = False
    cursor_validation_reason: str = ""
    cursor_validation_error: str = ""
    cursor_agent_url: str = ""
    cursor_validation_duration_ms: int = 0
    cursor_verdict_evidence: list[str] = field(default_factory=list)
    cursor_evidence: dict[str, Any] = field(default_factory=dict, repr=False)
    # Extended classification fields (req 16)
    repo_qna_intent_failure: bool = False
    boolean_inventory_exists: bool = False
    generation_truncated: bool = False
    repair_exhausted: bool = False
    agent_self_validation_failed: bool = False
    backend_preservation_failed: bool = False
    surgical_edit_anchor_failed: bool = False
    workflow_continuity_failure: bool = False
    context_revalidation_failed: bool = False
    creation_case_invalid: bool = False
    failed_validation_branch_pushed: bool = False
    generation_shape_failed: bool = False
    creation_workflow_routing_failed: bool = False
    boolean_context_attachment_failed: bool = False
    qna_routing_failed: bool = False
    diag_branch_name: str = ""
    diag_branch_url: str = ""
    candidate_fingerprints: list[str] = field(default_factory=list)
    target_contract: dict[str, Any] = field(default_factory=dict)


@dataclass
class TestRunResult:
    __test__ = False

    run_id: str
    requested_cases: int
    cases: list[TestCaseResult] = field(default_factory=list)
    discovery_errors: list[str] = field(default_factory=list)
    repository_question_checks: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0


def _calculate_case_score(row: TestCaseResult) -> int:
    """Score based on agent self-validation + backend validation only.

    Cursor result validation is temporarily disabled. Scoring covers:
    generation, preservation validation, branch push, and context reuse.
    """
    if row.case.case_type == "resource_creation":
        assertions = [
            row.expected_target_found,
            row.correct_flag_detected,
            row.phase1_file_generated,
            row.validation_ok,
            row.branch_pushed,
        ]
    else:
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
            row.phase2_context_useful,
        ]
    return round(100 * sum(bool(value) for value in assertions) / max(len(assertions), 1))


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


def _vague_alias(alias: str) -> str:
    """Make repository-derived feature wording less identifier-like.

    The test should exercise semantic resolution rather than merely copying the
    Terraform identifier into the prompt.  Replacements are intentionally
    generic infrastructure vocabulary, not repository/resource allow-lists.
    """
    words = [word for word in re.findall(r"[a-z0-9]+", str(alias or "").lower()) if word]
    replacements = {
        "lb": ["load", "balancer"],
        "alb": ["load", "balancer"],
        "metrics": ["monitoring"],
        "metric": ["monitoring"],
        "enabled": ["active"],
        "enable": ["active"],
        "premerge": ["before", "merge"],
        "oom": ["out", "of", "memory"],
        "ecs": ["container", "service"],
        "replication": ["copying"],
        "elastic": ["scalable"],
        "pool": ["capacity"],
        "handler": ["handling"],
    }
    rewritten: list[str] = []
    changed = False
    for word in words:
        replacement = replacements.get(word)
        if replacement:
            rewritten.extend(replacement)
            changed = True
        else:
            rewritten.append(word)
    if not changed and len(rewritten) >= 3:
        # Remove one low-information middle token so the prompt is not a
        # verbatim humanization of the flag while retaining enough semantics.
        rewritten.pop(len(rewritten) // 2)
    return " ".join(rewritten).strip() or str(alias or "").strip()


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
    vague = _vague_alias(alias)
    if phase == 1:
        templates = [
            "please {action} the {vague} setup in {env}",
            "can you switch the {vague} capability {direction} for {env}",
            "for {env}, make the {vague} behavior {state}",
            "I need the {vague} integration {state} around {env}",
            "change {env} so the {vague} piece is {state}",
        ]
    else:
        templates = [
            "can we have the {vague} part {state} in {env}",
            "please switch the {vague} behavior {direction} for {env}",
            "{env} should have the {vague} capability {state}",
            "turn the {vague} setup {direction} around {env}",
            "make that {vague} integration {state} for {env}",
        ]
    template = secrets.choice(templates)
    return template.format(
        action=action,
        alias=alias,
        vague=vague,
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
    semantic_generation: bool = False,
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
        semantic = (
            terrabot_semantic_engine.generate_semantic_variants(
                cloud=spec.cloud,
                environment=str(item["environment"]),
                alias=str(item["alias"]),
                desired_value=desired,
                path=str(item["path"]),
                flag=str(item["flag"]),
                count=2,
                workspace=os.getenv("TERRABOT_TEST_CURSOR_WORKSPACE", "").strip(),
            )
            if semantic_generation
            else []
        )
        phase1 = semantic[0] if semantic else _build_prompt(str(item["alias"]), str(item["environment"]), desired, phase=1)
        phase2 = semantic[1] if len(semantic) > 1 else _build_prompt(str(item["alias"]), str(item["environment"]), desired, phase=2)
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
                case_type="boolean_context",
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


def _build_creation_prompt(alias: str, environment: str, *, phase: int, nonce: str) -> str:
    vague = _vague_alias(alias)
    env = str(environment or "repository").strip()
    name = f"tb-{nonce}"
    templates = (
        [
            "create another {vague} resource in {env} named {name} using the existing repository pattern",
            "provision a new {vague} in {env} named {name} following the existing Terraform module pattern",
            "add another {vague} instance in {env} named {name} using the repository's existing infrastructure pattern",
        ]
        if phase == 1
        else [
            "create one more {vague} resource in {env} named {name} using the same repository pattern",
            "add another {vague} instance to {env} called {name} following the existing Terraform pattern",
            "provision an additional {vague} in {env} named {name} using the established repository convention",
        ]
    )
    return secrets.choice(templates).format(vague=vague, env=env, name=name)


def _derive_creation_case_for_repository(
    core: Any,
    spec: RepositorySpec,
    *,
    run_id: str,
    index: int,
) -> TestCase | None:
    """Derive one repository-backed resource-creation case without hardcoding a resource.

    AWS uses an existing module that is not already consumed by the selected
    environment. Azure uses a live root module family together with an actual
    environment hub.tfvars. The assertions for these cases intentionally test
    generation/validation/branch transport rather than an exact Boolean flag.
    """
    commit_sha, paths = _github_recursive_tree(core, spec)
    rng = secrets.SystemRandom()
    nonce = hashlib.sha1(f"{run_id}:{spec.cloud}:creation:{index}".encode()).hexdigest()[:6]

    if spec.cloud == "aws":
        environment_paths = [
            path for path in paths
            if re.search(r"^terraform/(?:dev_aws|prod_aws|dev_services_aws)/[^/]+/main\.tf$", path)
        ]
        module_names = sorted({
            match.group(1)
            for path in paths
            for match in [re.match(r"^terraform/modules/([^/]+)/.+\.tf$", path)]
            if match
        })
        rng.shuffle(environment_paths)
        rng.shuffle(module_names)
        # Pre-filter module names: skip singletons (global/shared/state/backend/base)
        # and modules whose name suggests they gate a unique resource (req 13).
        _SINGLETON_PATTERNS = re.compile(
            r"(?:^|_)(?:global|shared|base|backend|state|bootstrap|core|common|root)(?:_|$)",
            re.IGNORECASE,
        )

        def _module_is_safe_creation_candidate(mname: str, all_paths: list[str]) -> bool:
            """True if module exists in catalog and could be re-instantiated."""
            if _SINGLETON_PATTERNS.search(mname):
                return False
            # Must have at least one .tf in its modules/ directory
            module_prefix = f"terraform/modules/{mname}/"
            return any(p.startswith(module_prefix) for p in all_paths)

        safe_modules = [m for m in module_names if _module_is_safe_creation_candidate(m, paths)]

        # Creation cases must be backed by at least one real sibling consumer.
        # This prevents synthetic prompts for modules that exist in the catalog
        # but have no proven repository consumption pattern.
        sibling_consumers: dict[str, str] = {}
        for sibling_path in environment_paths[:60]:
            try:
                sibling_content = core.github_get_file_content_by_repo(spec.owner, spec.repo, sibling_path, ref=spec.branch) or ""
            except Exception:
                continue
            for module_name in safe_modules:
                if module_name in sibling_consumers:
                    continue
                if re.search(rf"modules/{re.escape(module_name)}(?:\b|\")", sibling_content, re.IGNORECASE):
                    sibling_consumers[module_name] = sibling_path

        for env_path in environment_paths[:12]:
            environment = _infer_environment(env_path, "aws")
            if not _candidate_environment_is_valid(core, spec, env_path, environment):
                continue
            content = core.github_get_file_content_by_repo(spec.owner, spec.repo, env_path, ref=spec.branch) or ""
            if not content:
                continue
            for module_name in safe_modules[:30]:
                # Select only a reusable module with a proven sibling consumer,
                # and ensure it is not already consumed in this target environment.
                sibling_path = sibling_consumers.get(module_name, "")
                if not sibling_path or sibling_path == env_path:
                    continue
                if re.search(rf"modules/{re.escape(module_name)}(?:\b|\")", content, re.IGNORECASE):
                    continue
                alias = _humanize_flag(module_name) or module_name.replace("_", " ")
                phase1 = _build_creation_prompt(alias, environment, phase=1, nonce=nonce)
                phase2 = _build_creation_prompt(alias, environment, phase=2, nonce=nonce)
                return TestCase(
                    case_id=f"aws-create-{index:02d}-{nonce}",
                    case_type="resource_creation",
                    cloud=spec.cloud,
                    owner=spec.owner,
                    repo=spec.repo,
                    branch=spec.branch,
                    commit_sha=commit_sha,
                    path=env_path,
                    environment=environment,
                    flag="",
                    alias=alias,
                    current_value=False,
                    desired_value=True,
                    evidence_line=f"terraform/modules/{module_name}; sibling consumer: {sibling_path}",
                    phase1_prompt=phase1,
                    phase2_prompt=phase2,
                )

    if spec.cloud == "azure":
        hub_paths = [
            path for path in paths
            if re.search(r"^vars/(?:npr|sbx|prd)/[^/]+/hub\.tfvars$", path)
        ]
        root_tf_paths = [path for path in paths if "/" not in path and path.endswith(".tf")]
        rng.shuffle(hub_paths)
        rng.shuffle(root_tf_paths)
        module_families: list[str] = []
        for tf_path in root_tf_paths[:25]:
            content = core.github_get_file_content_by_repo(spec.owner, spec.repo, tf_path, ref=spec.branch) or ""
            for match in re.finditer(r'(?m)^\s*module\s+"([^"]+)"\s*\{', content):
                label = match.group(1).strip()
                if label and label not in module_families:
                    module_families.append(label)
        rng.shuffle(module_families)
        for hub_path in hub_paths[:12]:
            environment = _infer_environment(hub_path, "azure")
            if not _candidate_environment_is_valid(core, spec, hub_path, environment):
                continue
            for module_name in module_families[:30]:
                alias = _humanize_flag(module_name) or module_name.replace("_", " ").replace("-", " ")
                if len(alias.strip()) < 3:
                    continue
                return TestCase(
                    case_id=f"azure-create-{index:02d}-{nonce}",
                    case_type="resource_creation",
                    cloud=spec.cloud,
                    owner=spec.owner,
                    repo=spec.repo,
                    branch=spec.branch,
                    commit_sha=commit_sha,
                    path=hub_path,
                    environment=environment,
                    flag="",
                    alias=alias,
                    current_value=False,
                    desired_value=True,
                    evidence_line=f"root module family: {module_name}",
                    phase1_prompt=_build_creation_prompt(alias, environment, phase=1, nonce=nonce),
                    phase2_prompt=_build_creation_prompt(alias, environment, phase=2, nonce=nonce),
                )
    return None


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


def _response_file_content(result: dict, expected_path: str) -> str:
    expected = str(expected_path or "").strip().strip("/")
    for item in _coerce_result_file_items(result):
        path = str(item.get("path") or "").strip().strip("/")
        if expected and path != expected:
            continue
        value = str(item.get("content") or "")
        if value:
            return value
    return ""


def _cursor_file_evidence(case: TestCase, result: dict) -> list[dict[str, Any]]:
    """Return bounded generated-file evidence for the final Cursor review."""
    evidence: list[dict[str, Any]] = []
    try:
        configured_files = int(os.getenv("TERRABOT_TEST_CURSOR_VALIDATION_MAX_FILES_PER_PHASE", "5"))
    except (TypeError, ValueError):
        configured_files = 5
    try:
        configured_chars = int(os.getenv("TERRABOT_TEST_CURSOR_VALIDATION_FILE_EXCERPT_CHARS", "9000"))
    except (TypeError, ValueError):
        configured_chars = 9000
    max_files = max(1, min(configured_files, 12))
    max_chars = max(1000, min(configured_chars, 30000))
    for item in (result.get("files") or [])[:max_files]:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or item.get("filename") or "").strip().strip("/")
        content = ""
        for key in ("content", "final_content", "text", "terraform"):
            value = item.get(key)
            if isinstance(value, str) and value:
                content = value
                break
        if not path:
            continue
        excerpt = content
        if content and case.flag:
            lines = content.splitlines()
            index = next(
                (i for i, line in enumerate(lines) if re.search(rf"\b{re.escape(case.flag)}\b", line, re.IGNORECASE)),
                -1,
            )
            if index >= 0:
                excerpt = "\n".join(lines[max(0, index - 24) : min(len(lines), index + 25)])
        if len(excerpt) > max_chars:
            excerpt = excerpt[: max_chars // 2] + "\n...<excerpt truncated>...\n" + excerpt[-max_chars // 2 :]
        evidence.append({
            "path": path,
            "content_length": len(content),
            "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest() if content else "",
            "excerpt": excerpt,
        })
    return evidence


def _cursor_context_evidence(record: dict | None) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {}
    return {
        "id": str(record.get("id") or ""),
        "category": str(record.get("category") or ""),
        "subject": str(record.get("subject") or ""),
        "scope": str(record.get("scope") or ""),
        "statement": str(record.get("statement") or "")[:4000],
        "evidence_paths": [str(value) for value in (record.get("evidence_paths") or [])[:12]],
        "confidence": record.get("confidence"),
        "stale": bool(record.get("stale")),
    }


def _control_mentioned(case: TestCase, result: dict) -> bool:
    """Diagnostic-only signal that Terrabot named the expected Boolean control.

    This intentionally excludes generated file bodies and never contributes to
    pass/fail scoring. Boolean correctness requires the exact requested literal
    assignment in the generated expected file.
    """
    if case.case_type != "boolean_context" or not case.flag:
        return False
    parts = [
        str(result.get("summary") or ""),
        str(result.get("reply") or ""),
        str(result.get("analysis") or ""),
        str(result.get("questions") or ""),
        str(result.get("candidates") or ""),
    ]
    return case.flag.lower() in "\n".join(parts).lower()



def _coerce_result_file_items(result: dict) -> list[dict[str, str]]:
    """Return generated Terraform file records from every backend response shape.

    Teams infra_preview responses are intentionally compact and may expose
    files as path strings while the complete candidate is stored in pending
    state. The test runner should not mark target detection failed merely
    because production UI transport used a compact file list.
    """
    records: list[dict[str, str]] = []
    for container_key in ("files", "generated_files", "committed_agent_result_files"):
        for item in (result.get(container_key) or []):
            if isinstance(item, dict):
                path = str(item.get("path") or item.get("filename") or "").strip().strip("/")
                content = ""
                for key in ("content", "final_content", "text", "terraform", "file_content", "new_content"):
                    value = item.get(key)
                    if isinstance(value, str):
                        content = value
                        break
                if path:
                    records.append({"path": path, "content": content})
            elif isinstance(item, str):
                path = item.strip().strip("/")
                if path:
                    records.append({"path": path, "content": ""})
    # Some backend wrappers carry the full candidate under agent_result.
    nested = result.get("agent_result") or result.get("terraform_result") or result.get("pending_change")
    if isinstance(nested, dict) and nested is not result:
        records.extend(_coerce_result_file_items(nested))
    unique: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in records:
        path = item["path"]
        if path in seen:
            # Prefer records with content over compact path-only records.
            if item.get("content"):
                for existing in unique:
                    if existing["path"] == path and not existing.get("content"):
                        existing["content"] = item["content"]
            continue
        seen.add(path)
        unique.append(item)
    return unique


def _hydrate_result_files_from_pending(core: Any, result: dict) -> dict:
    """Best-effort: expand an infra_preview compact file list from pending state."""
    current = dict(result or {})
    if any(isinstance(item, dict) and str(item.get("content") or "") for item in current.get("files") or []):
        return current
    pending_id = str(current.get("pending_change_id") or "").strip()
    thread_id = str(current.get("thread_id") or "").strip()
    if not pending_id:
        return current
    getter = getattr(core, "get_pending_infra_change_by_id", None)
    if not callable(getter):
        return current
    candidates = []
    for args in ((thread_id, pending_id), (pending_id,), (thread_id, "", pending_id)):
        try:
            pending = getter(*args)
        except TypeError:
            continue
        except Exception:
            continue
        if isinstance(pending, dict) and pending:
            candidates.append(pending)
    for pending in candidates:
        for key in ("agent_result", "result", "payload", "change", "terraform_result"):
            value = pending.get(key)
            if isinstance(value, dict):
                files = _coerce_result_file_items(value)
                if any(item.get("content") for item in files):
                    current["files"] = [{"filename": item["path"], "content": item.get("content", "")} for item in files]
                    current["hydrated_from_pending_change"] = True
                    return current
        files = _coerce_result_file_items(pending)
        if any(item.get("content") for item in files):
            current["files"] = [{"filename": item["path"], "content": item.get("content", "")} for item in files]
            current["hydrated_from_pending_change"] = True
            return current
    return current

def _response_executable_files(result: dict) -> list[dict[str, str]]:
    """Return backend-executable Terraform files only."""
    valid: list[dict[str, str]] = []
    for item in _coerce_result_file_items(result):
        path = str(item.get("path") or "").strip().strip("/")
        content = str(item.get("content") or "")
        lower = path.lower()
        if not path or path.startswith(("/", "./", "../")):
            continue
        if not lower.endswith((".tf", ".tfvars", ".tfvars.json")):
            continue
        if any(path.startswith(prefix) for prefix in ("changes/", "scratch/", "terraform-project/", "tf-devops/", "tf-azure-hub/")):
            continue
        valid.append({"path": path, "content": content})
    return valid


def _target_detection(case: TestCase, result: dict) -> tuple[bool, bool, bool, str]:
    executable_files = _response_executable_files(result)
    paths = [item["path"] for item in executable_files]
    text = _response_text(result)
    expected_path = str(case.path or "").strip().strip("/")
    expected_target_found = expected_path in paths
    if case.case_type == "resource_creation":
        alias_tokens = {
            token for token in re.findall(r"[a-z0-9]+", case.alias.lower())
            if len(token) > 2
        }
        semantic_text = text + "\n" + "\n".join(paths).lower() + "\n" + "\n".join(item["content"].lower()[:8000] for item in executable_files)
        correct_flag_detected = bool(alias_tokens) and any(token in semantic_text for token in alias_tokens)
        expected_target_found = bool(executable_files)
    else:
        content = _response_file_content(result, expected_path)
        expected_value = "true" if case.desired_value else "false"
        assignment = re.search(
            rf"(?m)^\s*{re.escape(case.flag)}\s*=\s*{expected_value}\s*(?:#.*)?$",
            content,
            re.IGNORECASE,
        ) if content and case.flag else None
        correct_flag_detected = bool(assignment)
        contract = (
            ((result.get("test_diagnostics") or {}).get("resolved_repository_target_contract"))
            or result.get("resolved_repository_target_contract")
            or result.get("target_contract")
            or {}
        )
        if isinstance(contract, dict) and contract:
            contract_path = str(contract.get("path") or "").strip().strip("/")
            contract_flag = str(contract.get("flag") or "").strip()
            contract_new = str(contract.get("new_value") or contract.get("desired_value") or "").strip().lower()
            if contract_path == expected_path and contract_flag == case.flag and contract_new == expected_value:
                expected_target_found = True
                correct_flag_detected = True
    file_generated = bool(executable_files)
    actual_file = next((path for path in paths if path == expected_path), paths[0] if paths else "")
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


def _pick_automated_candidate_reply(case: TestCase, result: dict) -> str:
    """Return a numeric clarification reply suitable for unattended tests.

    Boolean-context cases prefer the repository-derived expected candidate.
    Resource-creation cases deliberately choose a random valid option because
    module/resource selection is itself part of the workflow being exercised.
    Clarification is therefore not a failed assertion when generation proceeds.
    """
    candidates = [item for item in (result.get("candidates") or []) if isinstance(item, dict)]
    if case.case_type != "resource_creation":
        expected = _pick_expected_candidate(case, result)
        if expected:
            # Convert an exact flag/path selection to the displayed numeric
            # index when possible so production numeric-reply handling is tested.
            for fallback_index, item in enumerate(candidates, start=1):
                item_index = str(item.get("index") or fallback_index).strip()
                if expected == item_index:
                    return item_index
                if expected in {
                    str(item.get("flag") or "").strip(),
                    str(item.get("path") or "").strip(),
                }:
                    return item_index
            return expected
    if candidates:
        chosen = secrets.choice(list(enumerate(candidates, start=1)))
        fallback_index, item = chosen
        return str(item.get("index") or fallback_index).strip() or str(fallback_index)
    # Zero structured candidates is a free-form clarification, not a numeric
    # target picker. Never synthesize option 1 because no such option exists.
    return ""


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


def _search_phase2_context(
    case: TestCase,
    *,
    required_context_id: str = "",
) -> tuple[dict, dict | None]:
    """Retrieve Phase 2 context by paraphrase, then by the learned exact ID.

    Semantic search remains the first assertion. When the record was created or
    verified in Phase 1, its exact durable ID is also available to the fresh Phase
    2 conversation. Falling back to that exact ID prevents search ranking or
    index-consistency lag from dropping a mandatory continuation record. The
    record still must map to the expected live path+flag before it is returned.
    """
    try:
        attempts = int(os.getenv("TERRABOT_TEST_PHASE2_CONTEXT_SEARCH_ATTEMPTS", "3"))
    except (TypeError, ValueError):
        attempts = 3
    attempts = max(1, min(attempts, 5))
    try:
        top_k = int(os.getenv("TERRABOT_TEST_PHASE2_CONTEXT_TOP_K", "25"))
    except (TypeError, ValueError):
        top_k = 25
    top_k = max(8, min(top_k, 25))
    last: dict = {}
    for attempt in range(1, attempts + 1):
        last = repository_context.search_repository_context(
            repo_owner=case.owner,
            repo_name=case.repo,
            query=case.phase2_prompt,
            current_commit_sha="",
            top_k=top_k,
        )
        match = _matching_context_record(case, last)
        if match is not None:
            if attempt > 1:
                _diag(
                    "phase2_context_retrieved_after_retry",
                    test_case_id=case.case_id,
                    attempt=attempt,
                    top_k=top_k,
                    context_id=str(match.get("id") or ""),
                )
            return last, match
        if attempt < attempts:
            time.sleep(min(0.5 * attempt, 1.5))

    context_id = str(required_context_id or "").strip()
    if context_id:
        try:
            record = repository_context.get_repository_context_by_id(context_id)
        except Exception as exc:
            _diag(
                "phase2_required_context_exact_id_lookup_failed",
                level="warning",
                test_case_id=case.case_id,
                context_id=context_id,
                error=exc,
            )
            record = None
        if record is not None:
            exact = {
                "id": str(getattr(record, "id", "") or ""),
                "category": str(getattr(record, "category", "") or ""),
                "subject": str(getattr(record, "subject", "") or ""),
                "scope": str(getattr(record, "scope", "") or ""),
                "statement": str(getattr(record, "statement", "") or ""),
                "evidence_paths": list(getattr(record, "evidence_paths", []) or []),
                "evidence_commit_sha": str(getattr(record, "evidence_commit_sha", "") or ""),
                "evidence_branch": str(getattr(record, "evidence_branch", "") or ""),
                "status": str(getattr(record, "status", "active") or "active"),
                "confidence": getattr(record, "confidence", 0.0),
                "stale": False,
                "required_continuation_record": True,
            }
            repo_full_name = str(getattr(record, "repo_full_name", "") or "").lower()
            if (
                repo_full_name == f"{case.owner}/{case.repo}".lower()
                and _matching_context_record(case, {"results": [exact]}) is not None
            ):
                _diag(
                    "phase2_context_retrieved_by_exact_id",
                    test_case_id=case.case_id,
                    context_id=context_id,
                    semantic_search_result_count=len(last.get("results") or []),
                )
                merged = dict(last or {})
                merged_results = [exact] + [
                    item for item in (last.get("results") or [])
                    if isinstance(item, dict) and str(item.get("id") or "") != context_id
                ]
                merged["results"] = merged_results
                return merged, exact
    return last, None


def _ensure_context_mapping(
    core: Any,
    case: TestCase,
    run_id: str,
    *,
    evidence_branch: str = "",
    evidence_commit_sha: str = "",
    subject_override: str = "",
    statement_override: str = "",
    source_suffix: str = "",
) -> bool:
    subject_value = re.sub(r"\s+", " ", str(subject_override or case.alias or "")).strip()
    try:
        if subject_override:
            existing = repository_context.search_repository_context(
                repo_owner=case.owner,
                repo_name=case.repo,
                query=f"{subject_value} {case.environment}",
                current_commit_sha=str(evidence_commit_sha or case.commit_sha),
                top_k=12,
            )
        else:
            existing = _search_context(case)
    except Exception as exc:
        _diag(
            "context_mapping_search_failed",
            level="error",
            run_id=run_id,
            test_case_id=case.case_id,
            repo=f"{case.owner}/{case.repo}",
            path=case.path,
            flag=case.flag,
            error=exc,
        )
        raise
    existing_match = _matching_context_record(case, existing)
    if existing_match and (
        not subject_override
        or subject_value.lower() in " ".join([
            str(existing_match.get("subject") or ""),
            str(existing_match.get("statement") or ""),
        ]).lower()
    ):
        _diag(
            "context_mapping_already_present",
            run_id=run_id,
            test_case_id=case.case_id,
            repo=f"{case.owner}/{case.repo}",
            path=case.path,
            flag=case.flag,
        )
        return True

    ref = str(evidence_branch or case.branch).strip()
    commit_sha = str(evidence_commit_sha or case.commit_sha).strip()
    try:
        live_content = core.github_get_file_content_by_repo(case.owner, case.repo, case.path, ref=ref) or ""
    except Exception as exc:
        _diag(
            "context_mapping_evidence_read_failed",
            level="error",
            run_id=run_id,
            test_case_id=case.case_id,
            repo=f"{case.owner}/{case.repo}",
            ref=ref,
            path=case.path,
            flag=case.flag,
            error=exc,
        )
        raise
    if not live_content:
        _diag(
            "context_mapping_evidence_missing",
            level="warning",
            run_id=run_id,
            test_case_id=case.case_id,
            repo=f"{case.owner}/{case.repo}",
            ref=ref,
            commit_sha=commit_sha,
            path=case.path,
            flag=case.flag,
        )
    evidence_line = case.evidence_line
    assignment = re.search(
        rf"(?m)^\s*{re.escape(case.flag)}\s*=\s*(?:true|false)\s*(?:#.*)?$",
        str(live_content),
        re.IGNORECASE,
    )
    if assignment:
        evidence_line = assignment.group(0).strip()
    else:
        _diag(
            "context_mapping_assignment_not_found",
            level="warning",
            run_id=run_id,
            test_case_id=case.case_id,
            repo=f"{case.owner}/{case.repo}",
            ref=ref,
            path=case.path,
            flag=case.flag,
            live_content_chars=len(live_content),
            fallback_evidence_line=evidence_line,
        )

    statement = str(statement_override or "").strip() or (
        f"In {case.repo}, {subject_value} maps to Boolean control {case.flag} "
        f"in {case.path} for environment {case.environment}."
    )
    candidate = {
        "category": "resolved_clarification",
        "subject": subject_value,
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

    try:
        action = repository_context.add_repository_context(
            repo_owner=case.owner,
            repo_name=case.repo,
            evidence_commit_sha=commit_sha,
            evidence_branch=ref,
            source_task_hash=hashlib.sha256(
                f"{run_id}:{case.case_id}:{ref}:{source_suffix}:{subject_value}".encode()
            ).hexdigest(),
            candidate=candidate,
            evidence_fetcher=evidence_fetcher,
        )
    except Exception as exc:
        _diag(
            "context_mapping_add_failed",
            level="error",
            run_id=run_id,
            test_case_id=case.case_id,
            repo=f"{case.owner}/{case.repo}",
            ref=ref,
            commit_sha=commit_sha,
            path=case.path,
            flag=case.flag,
            error=exc,
        )
        raise
    stored = bool(action.get("stored"))
    _diag(
        "context_mapping_add_result",
        level="info" if stored else "warning",
        run_id=run_id,
        test_case_id=case.case_id,
        repo=f"{case.owner}/{case.repo}",
        ref=ref,
        commit_sha=commit_sha,
        path=case.path,
        flag=case.flag,
        stored=stored,
        action=str(action.get("action") or action.get("status") or ""),
        reason=str(action.get("reason") or action.get("error") or ""),
        validation_errors=action.get("validation_errors") or action.get("errors") or [],
        context_id=str(action.get("id") or action.get("context_id") or ""),
    )
    return stored


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
        "pending_branch_choice_resolved": True,
        "branch_choice": "new",
        "force_new_branch": True,
        "reuse_branch": False,
        "existing_branch": "",
        "teams_requester": f"terrabot-test-{run_id[-6:]}-{case.case_id}",
        "test_mode": False,
        "automated_test_phase": 1,
        "allow_failed_validation_branch_push": True,
        "test_allow_failed_validation_branch_push": True,
    })
    return helper(commit_request, preview, 200)


def _invoke_backend(core: Any, request: dict, result: TestCaseResult) -> tuple[dict, int]:
    result.bot_calls += 1
    return core.handle_teams_chat_request(request)


def _automated_test_workflow(case: TestCase) -> str:
    """Do not prescribe production workflow routing from the test harness.

    The case shape is test ground truth for assertions only. Production Terrabot
    must infer its workflow from the request and live repository evidence. Phase
    2 may carry forward the workflow that production actually resolved in Phase
    1, but this helper never maps clouds/resources to workflow names.
    """
    del case
    return ""


def _phase_request(case: TestCase, prompt: str, conversation_id: str, *, phase: int) -> dict:
    request = {
        "prompt": prompt,
        "original_prompt": prompt,
        "thread_id": "",
        "teams_conversation_id": conversation_id,
        "memory_conversation_id": f"{conversation_id}::memory::{uuid.uuid4().hex}",
        "teams_requester": "terrabot-automated-test",
        "source": "teams",
        # Repository-context E2E cases are infrastructure tests by construction.
        # Bypass only the generic chat-vs-infra routing decision; Terrabot must
        # still resolve the environment, repository target, live Boolean, and
        # generate repository-aligned Terraform itself.
        "mode": "infra",
        "test_mode": True,
        "automated_test_phase": phase,
        "automated_test_case_id": case.case_id,
        "automated_test_case_type": case.case_type,
        "fresh_infra_generation": True,
        "cloud": case.cloud,
        "requested_cloud": case.cloud,
        # Test runs never reuse a user's existing Terrabot branch. Resolve the
        # branch decision up front so generation cannot stop at the production
        # branch-choice UX. Phase 1 later commits the validated preview to its
        # isolated test branch; Phase 2 remains test_mode and never commits.
        "pending_branch_choice_resolved": True,
        "branch_choice": "new",
        "force_new_branch": True,
        "reuse_branch": False,
        "existing_branch": "",
    }
    workflow = _automated_test_workflow(case)
    if workflow:
        request["workflow"] = workflow
    return request


def _validate_preview(core: Any, backend_result: dict, prompt: str, thread_id: str) -> tuple[bool, str]:
    backend_result = _hydrate_result_files_from_pending(core, backend_result)
    if str(backend_result.get("mode") or "").lower() != "infra_preview":
        return False, f"Expected infra_preview, received {backend_result.get('mode') or '<none>'}."
    if not _response_executable_files(backend_result):
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


def _cursor_error_is_unavailable(error: str) -> bool:
    text = str(error or "").lower()
    return any(token in text for token in (
        "usage_limit_exceeded", "hard limit", "rate limit", "quota",
        "cursor api key", "not configured", "timed out", "timeout",
        "http 429", "http 400", "api request failed",
    ))


def _resolve_automated_clarifications(
    core: Any,
    case: TestCase,
    row: TestCaseResult,
    result: dict,
    status: int,
    *,
    phase: int,
    conversation_id: str,
    phase_request: dict,
    run_id: str,
    max_rounds: int = 3,
) -> tuple[dict, int, bool]:
    """Resolve clarification without inventing a target-selection protocol.

    Structured pickers may be answered as target-selection replies. A free-form
    clarification (zero structured candidates) is never answered with synthetic
    option ``1``. In automated tests Cursor inspects the exact pinned repository
    and supplies the clarification answer; that answer is sent as a normal
    continuation so the production resolver bug remains visible in scoring.
    """
    clarified = False
    current = dict(result or {})
    current_status = status
    for round_no in range(1, max_rounds + 1):
        if str(current.get("mode") or "").lower() != "clarification":
            break
        clarified = True
        candidates = [item for item in (current.get("candidates") or []) if isinstance(item, dict)]
        clarification_text = str(current.get("reply") or current.get("question") or "").strip()
        _diag(
            "cursor_clarification_requested",
            run_id=run_id,
            test_case_id=case.case_id,
            phase=phase,
            round=round_no,
            candidate_count=len(candidates),
            clarification=clarification_text[:500],
        )
        original_user_prompt = case.phase1_prompt if phase == 1 else case.phase2_prompt
        prompt_author_binding = cursor_prompt_provider.get_prompt_author_target_binding(
            run_id=run_id,
            case=case,
            prompt=original_user_prompt,
        )
        cursor_clarification_enabled = os.getenv(
            "TERRABOT_TEST_CURSOR_CLARIFICATION_ENABLED", "false"
        ).strip().lower() in {"1", "true", "yes", "on"}
        if prompt_author_binding or cursor_clarification_enabled:
            cursor_resolution = cursor_prompt_provider.resolve_repository_clarification(
                owner=case.owner,
                repo=case.repo,
                commit_sha=case.commit_sha,
                original_prompt=original_user_prompt,
                clarification_text=clarification_text,
                candidates=candidates,
                # REQ 6: oracle hints are DISABLED by default.
                # The expected path/flag validates results AFTER generation but must
                # not rescue production target discovery in normal acceptance tests.
                # Enable only for explicit diagnostic runs: TERRABOT_TEST_ORACLE_HINT=true.
                expected_target_hint=(
                    {
                        "path": case.path,
                        "flag": case.flag,
                        "current_value": case.current_value,
                        "new_value": case.desired_value,
                        "environment": case.environment,
                        "alias": case.alias,
                    }
                    if case.case_type == "boolean_context"
                    and os.getenv("TERRABOT_TEST_ORACLE_HINT","false").strip().lower() in {"1","true","yes"}
                    else None
                ),
                expected_creation_hint=(
                    {
                        "target_consumer_path": case.path,
                        "environment": case.environment,
                        "alias": case.alias,
                        "module_hint": case.evidence_line,
                    }
                    if case.case_type == "resource_creation"
                    and os.getenv("TERRABOT_TEST_ORACLE_HINT","false").strip().lower() in {"1","true","yes"}
                    else None
                ),
                prompt_author_target_binding=prompt_author_binding,
                run_id=run_id,
                case_id=case.case_id,
                log_event=_diag,
            )
        else:
            cursor_resolution = {
                "attempted": False,
                "resolved": False,
                "resolution_type": "unresolved",
                "answer": "",
                "error": "",
            }
            _diag(
                "cursor_clarification_skipped",
                run_id=run_id,
                test_case_id=case.case_id,
                phase=phase,
                reason="prompt_generation_only",
            )
        cursor_attempted = bool((cursor_resolution or {}).get("attempted", True))
        cursor_resolved = bool((cursor_resolution or {}).get("resolved"))
        cursor_error = str((cursor_resolution or {}).get("error") or "").strip()
        if cursor_attempted and not cursor_resolved and not cursor_error:
            cursor_error = "Cursor did not resolve the repository clarification to one live-verifiable target."
        if phase == 1:
            row.phase1_cursor_clarification_attempted = cursor_attempted
            row.phase1_cursor_clarification_error = cursor_error
        else:
            row.phase2_cursor_clarification_attempted = cursor_attempted
            row.phase2_cursor_clarification_error = cursor_error


        resolution_type = str((cursor_resolution or {}).get("resolution_type") or "").strip().lower()
        structured_picker = bool(candidates) and bool(cursor_resolution.get("use_structured_picker"))
        selection = str(cursor_resolution.get("answer") or "").strip()

        if not cursor_resolution or resolution_type == "unresolved" or not selection:
            # Cursor clarification is optional. If Cursor is rate-limited or
            # otherwise unavailable, keep the test moving by asking Terrabot/
            # Foundry to resolve the target from the already supplied live
            # repository evidence. This does not use oracle expected_path/flag
            # hints and does not mark Cursor as successful; it prevents test
            # branch materialization from being blocked solely by Cursor quota.
            if case.case_type == "resource_creation" and candidates:
                selection = _pick_automated_candidate_reply(case, current)
                structured_picker = bool(selection)
            if not selection:
                _diag(
                    "automated_clarification_delegated_to_foundry_self_resolution",
                    level="warning",
                    run_id=run_id,
                    test_case_id=case.case_id,
                    phase=phase,
                    round=round_no,
                    candidate_count=len(candidates),
                    cursor_resolution_type=resolution_type or "<none>",
                    cursor_used=False,
                    cursor_attempted=cursor_attempted,
                    cursor_error=cursor_error[:500],
                )
                selection = (
                    "Cursor clarification is unavailable. Do not ask the user for a path, flag, "
                    "module, or environment that can be derived from live repository evidence. "
                    "Resolve the strongest repository target yourself from the supplied files, "
                    "then generate the requested minimal Terraform change."
                )
                resolution_type = "foundry_self_resolution"
                structured_picker = False
                if _cursor_error_is_unavailable(cursor_error):
                    if phase == 1:
                        row.phase1_cursor_unavailable_fallback_used = True
                    else:
                        row.phase2_cursor_unavailable_fallback_used = True

        cursor_unavailable_fallback = bool(
            resolution_type == "foundry_self_resolution" and _cursor_error_is_unavailable(cursor_error)
        )
        if phase == 1:
            row.phase1_cursor_clarification_failed = bool(cursor_attempted and not cursor_resolved and not cursor_unavailable_fallback)
            row.phase1_cursor_unavailable_fallback_used = row.phase1_cursor_unavailable_fallback_used or cursor_unavailable_fallback
        else:
            row.phase2_cursor_clarification_failed = bool(cursor_attempted and not cursor_resolved and not cursor_unavailable_fallback)
            row.phase2_cursor_unavailable_fallback_used = row.phase2_cursor_unavailable_fallback_used or cursor_unavailable_fallback

        if not structured_picker and resolution_type not in {"creation_target", "foundry_self_resolution"}:
            if phase == 1:
                row.phase1_freeform_clarification = True
            else:
                row.phase2_freeform_clarification = True

        cursor_assist_used = bool(
            cursor_resolution
            and resolution_type in {"candidate", "repository_control", "creation_target"}
            and selection
        )
        if cursor_assist_used:
            if phase == 1:
                row.phase1_cursor_clarification_used = True
            else:
                row.phase2_cursor_clarification_used = True
            selected_path = str(cursor_resolution.get("selected_path") or "").strip().strip("/")
            selected_flag = str(cursor_resolution.get("selected_flag") or "").strip()
            if (
                case.case_type == "boolean_context"
                and selected_path == case.path.strip("/")
                and selected_flag == case.flag
            ):
                _diag(
                    "cursor_clarification_target_verified_for_continuation",
                    test_case_id=case.case_id,
                    phase=phase,
                    path=selected_path,
                    flag=selected_flag,
                    note="context persistence remains branch-gated; Cursor clarification does not create learning credit before a successful branch write",
                )

        _diag(
            "automated_clarification_selected",
            test_case_id=case.case_id,
            phase=phase,
            round=round_no,
            selection=selection,
            candidate_count=len(candidates),
            structured_picker=structured_picker,
            cursor_used=cursor_assist_used,
            cursor_attempted=cursor_attempted,
            cursor_error=cursor_error[:500],
            cursor_resolution_type=resolution_type or "<none>",
            cursor_candidates_relevant=cursor_resolution.get("candidates_relevant") if cursor_resolution else "",
            cursor_selected_path=cursor_resolution.get("selected_path") if cursor_resolution else "",
            cursor_selected_flag=cursor_resolution.get("selected_flag") if cursor_resolution else "",
            process="cursor_repo_analysis->backend_continuation",
        )
        if structured_picker:
            continuation_prompt = selection
        elif cursor_assist_used and resolution_type in {"repository_control", "creation_target"}:
            # Previously the continuation re-sent the original ambiguous prompt,
            # so a correct Cursor resolution never reached Foundry and the agent
            # simply asked the same question again. Carry the resolved
            # repository instruction with the user's intent instead.
            continuation_prompt = f"{original_user_prompt}\n\nResolved repository target: {selection}"
        elif resolution_type == "foundry_self_resolution":
            continuation_prompt = f"{original_user_prompt}\n\nRepository self-resolution instruction: {selection}"
        else:
            continuation_prompt = original_user_prompt
        followup = {
            "prompt": continuation_prompt,
            "original_prompt": original_user_prompt,
            "thread_id": str(current.get("thread_id") or ""),
            "teams_conversation_id": conversation_id,
            "memory_conversation_id": phase_request["memory_conversation_id"],
            "teams_requester": phase_request["teams_requester"],
            "source": "teams",
            "mode": "infra",
            "test_mode": True,
            "automated_test_phase": phase,
            "automated_test_case_id": case.case_id,
            "automated_test_case_type": case.case_type,
            # A structured picker continues the pending selection. A free-form
            # Cursor repository-control answer replays the original semantic
            # request with a live-verifiable structured resolution attached, so
            # the final repository resolver runs instead of treating "Use X in
            # path Y" as a brand-new vague infrastructure request.
            "fresh_infra_generation": not structured_picker,
            "resume_after_repository_clarification": not structured_picker,
            # Keep the already-resolved test branch strategy across target or
            # free-form clarification continuations. A clarification must not
            # reopen the normal user branch-choice stage.
            "pending_branch_choice_resolved": True,
            "branch_choice": "new",
            "force_new_branch": True,
            "reuse_branch": False,
            "existing_branch": "",
            "cloud": case.cloud,
            "requested_cloud": case.cloud,
            "required_repository_context_ids": list(phase_request.get("required_repository_context_ids") or []),
            "repository_context_reuse_required": bool(
                phase_request.get("repository_context_reuse_required")
            ),
        }
        resolved_followup_workflow = str(
            current.get("workflow")
            or ((current.get("router") or {}).get("workflow") if isinstance(current.get("router"), dict) else "")
            or phase_request.get("workflow")
            or ""
        ).strip()
        if resolved_followup_workflow:
            followup["workflow"] = resolved_followup_workflow
        resolved_repo_target = str(current.get("repo_target") or phase_request.get("repo_target") or "").strip()
        if resolved_repo_target:
            followup["repo_target"] = resolved_repo_target
        if cursor_resolution and resolution_type in {"candidate", "repository_control"}:
            followup["cursor_repository_resolution"] = {
                "source": "cursor_read_only_repository_clarification",
                "resolution_type": resolution_type,
                "repository": f"{case.owner}/{case.repo}",
                "commit_sha": case.commit_sha,
                "path": str(cursor_resolution.get("selected_path") or "").strip().strip("/"),
                "flag": str(cursor_resolution.get("selected_flag") or "").strip(),
                "current_value": cursor_resolution.get("selected_current_value"),
                "new_value": cursor_resolution.get("selected_new_value"),
                "reason": str(cursor_resolution.get("reason") or "").strip(),
                "evidence": list(cursor_resolution.get("evidence") or [])[:4],
                "verification_provenance": str(
                    cursor_resolution.get("verification_provenance")
                    or "cursor_repository_agent"
                ),
                "cursor_api_call": bool(cursor_resolution.get("api_call", True)),
            }
            _diag(
                "cursor_clarification_handoff_prepared",
                run_id=run_id,
                test_case_id=case.case_id,
                phase=phase,
                path=followup["cursor_repository_resolution"]["path"],
                flag=followup["cursor_repository_resolution"]["flag"],
                current_value=followup["cursor_repository_resolution"]["current_value"],
                new_value=followup["cursor_repository_resolution"]["new_value"],
                process="cursor_repo_analysis->backend_live_verification->foundry_generation",
            )
        if structured_picker:
            followup["pending_target_selection_reply"] = True
            followup["pending_target_selection_thread_id"] = str(current.get("thread_id") or "")
        current, current_status = _invoke_backend(core, followup, row)
    return current, current_status, clarified


def _run_case(core: Any, case: TestCase, run_id: str, requester_id: str) -> TestCaseResult:
    started = time.monotonic()
    row = TestCaseResult(case=case)
    p1_conversation = f"terrabot-test::{requester_id}::{run_id}::{case.case_id}::p1"
    p2_conversation = f"terrabot-test::{requester_id}::{run_id}::{case.case_id}::p2"
    phase1_result: dict = {}
    phase2_result: dict = {}

    _diag(
        "case_flow_started",
        run_id=run_id,
        test_case_id=case.case_id,
        repo=f"{case.owner}/{case.repo}",
        environment=case.environment,
        expected_target=f"{case.path}::{case.flag}",
    )
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
        if case.case_type == "boolean_context":
            baseline_context = _search_context(case)
            row.context_present_before = _matching_context_record(case, baseline_context) is not None
        phase1_request = _phase_request(case, case.phase1_prompt, p1_conversation, phase=1)
        phase1_request["teams_requester"] = f"terrabot-test-{run_id[-6:]}-{case.case_id}"
        phase1_result, status = _invoke_backend(core, phase1_request, row)
        row.phase1_mode = str(phase1_result.get("mode") or "").lower()
        row.actual_mode = str(phase1_result.get("mode") or "")
        row.phase1_control_mentioned = _control_mentioned(case, phase1_result)
        _diag(
            "phase1_initial_backend_result",
            run_id=run_id,
            test_case_id=case.case_id,
            status=status,
            mode=row.phase1_mode or "<none>",
            ok=phase1_result.get("ok"),
            file_count=len(phase1_result.get("files") or []),
            candidate_count=len(phase1_result.get("candidates") or []),
            control_mentioned=row.phase1_control_mentioned,
            decision_state=phase1_result.get("decision_state") or "",
            reply=str(phase1_result.get("reply") or "")[:500],
        )
        row.phase1_ok = status < 500 and bool(phase1_result.get("ok", True))

        phase1_result, status, row.phase1_clarified = _resolve_automated_clarifications(
            core,
            case,
            row,
            phase1_result,
            status,
            phase=1,
            conversation_id=p1_conversation,
            phase_request=phase1_request,
            run_id=run_id,
        )
        phase1_result = _hydrate_result_files_from_pending(core, phase1_result)
        row.actual_mode = str(phase1_result.get("mode") or "")
        row.phase1_control_mentioned = row.phase1_control_mentioned or _control_mentioned(case, phase1_result)
        row.phase1_ok = status < 500 and bool(phase1_result.get("ok", True))
        row.resolved_workflow = str(
            phase1_result.get("workflow")
            or ((phase1_result.get("router") or {}).get("workflow") if isinstance(phase1_result.get("router"), dict) else "")
            or ""
        ).strip()
        _diag(
            "phase1_production_workflow_resolved",
            run_id=run_id,
            test_case_id=case.case_id,
            workflow=row.resolved_workflow or "<none>",
            source="production_backend_result",
        )

        (
            row.expected_target_found,
            row.correct_flag_detected,
            row.phase1_file_generated,
            row.actual_file,
        ) = _target_detection(case, phase1_result)
        row.expected_target_found = row.expected_target_found and _repo_matches(case, phase1_result)
        row.cursor_evidence["phase1"] = {
            "mode": str(phase1_result.get("mode") or ""),
            "status": status,
            "generated_files": _cursor_file_evidence(case, phase1_result),
            "backend_target_found": row.expected_target_found,
            "backend_control_detected": row.correct_flag_detected,
        }

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
            if case.case_type == "resource_creation" and str(phase1_result.get("mode") or "").lower() == "clarification":
                row.creation_workflow_routing_failed = True

        branch_result = phase1_result
        branch_status = status
        if str(phase1_result.get("mode") or "").lower() == "infra_preview":
            branch_result, branch_status = _commit_preview_to_test_branch(
                core, case, run_id, phase1_result, phase1_request
            )
            row.bot_calls += 1
            if not row.validation_ok and branch_status < 400 and bool(branch_result.get("ok", True)):
                row.failed_validation_branch_pushed = True
                row.diag_branch_name = str(branch_result.get("branch") or "").strip()
                row.diag_branch_url = str(branch_result.get("branch_url") or "").strip()

        row.branch_name = str(branch_result.get("branch") or "").strip()
        row.branch_url = str(branch_result.get("branch_url") or "").strip()
        row.branch_pushed = (
            branch_status < 400
            and bool(branch_result.get("ok", True))
            and str(branch_result.get("mode") or "").lower() == "branch_created"
            and bool(row.branch_name or row.branch_url)
        )
        # REQ 7: capture the immutable target contract from P1 for P2 continuity.
        # Pull from backend diagnostics or from the phase1_result directly.
        _p1_contract = (
            ((phase1_result.get("test_diagnostics") or {}).get("resolved_repository_target_contract"))
            or phase1_result.get("resolved_repository_target_contract")
            or {}
        )
        if isinstance(_p1_contract, dict) and _p1_contract.get("path"):
            row.target_contract = _p1_contract
            _diag(
                "phase1_target_contract_captured",
                run_id=run_id,
                test_case_id=case.case_id,
                path=_p1_contract.get("path",""),
                flag=_p1_contract.get("flag",""),
            )
        row.cursor_evidence["phase1"].update({
            "backend_validation_ok": row.validation_ok,
            "backend_validation_error": row.validation_error,
            "branch_pushed": row.branch_pushed,
            "branch_name": row.branch_name,
            "branch_url": row.branch_url,
        })
        validation_lower = str(row.validation_error or "").lower()
        if not row.phase1_file_generated and (
            "no terraform files" in validation_lower
            or "no executable terraform" in validation_lower
            or "generation_shape_failure" in validation_lower
        ):
            row.generation_shape_failed = True
        _diag(
            "phase1_branch_result",
            run_id=run_id,
            test_case_id=case.case_id,
            branch_pushed=row.branch_pushed,
            branch=row.branch_name,
            mode=branch_result.get("mode"),
        )

        if case.case_type == "resource_creation":
            # Creation is a separate workflow test. It intentionally allows
            # one or more repository/module pickers and does not require a
            # Phase 2 repository-context reuse assertion.
            row.score = _calculate_case_score(row)
            row.backend_score = row.score
            _diag(
                "resource_creation_case_completed",
                run_id=run_id,
                test_case_id=case.case_id,
                clarified=row.phase1_clarified,
                file_generated=row.phase1_file_generated,
                validation_ok=row.validation_ok,
                branch_pushed=row.branch_pushed,
                score=row.score,
            )
            return row

        # Let the normal post-commit context workflow run first. If it did not
        # create this deterministic mapping, the isolated test harness adds the
        # verified mapping itself so the same run can still exercise Phase 2.
        context_search = _search_context(case)
        row.context_stored = _matching_context_record(case, context_search) is not None
        row.production_context_created = row.context_stored and not row.context_present_before
        row.context_gap_detected = terrabot_test_analysis.is_context_gap(
            case, row, context_present_before=row.context_present_before
        )
        if not row.context_stored and row.branch_pushed and row.context_gap_detected:
            evidence_branch = row.branch_name or case.branch
            branch_sha = _branch_head_sha(core, case, row.branch_name)
            live_content = core.github_get_file_content_by_repo(
                case.owner, case.repo, case.path, ref=evidence_branch
            ) or ""
            assignment = re.search(
                rf"(?m)^\s*{re.escape(case.flag)}\s*=\s*(?:true|false)\s*(?:#.*)?$",
                str(live_content),
                re.IGNORECASE,
            )
            candidate = terrabot_test_analysis.build_boolean_context_candidate(
                case,
                run_id=run_id,
                evidence_line=assignment.group(0).strip() if assignment else case.evidence_line,
            )
            row.context_candidate_created = True
            owner_hash = terrabot_test_state.requester_hash(requester_id)
            try:
                terrabot_test_state.save_context_candidate(owner_hash, run_id, candidate)
            except Exception as exc:
                _diag("context_candidate_state_save_failed", level="warning", run_id=run_id, test_case_id=case.case_id, error=exc)

            def candidate_fetcher(owner: str, repo: str, path: str, ref_value: str) -> str | None:
                return core.github_get_file_content_by_repo(owner, repo, path, ref=ref_value)

            validation = repository_context.validate_repository_context_candidate(
                candidate,
                repo_owner=case.owner,
                repo_name=case.repo,
                evidence_ref=branch_sha or evidence_branch,
                evidence_fetcher=candidate_fetcher,
            )
            row.context_candidate_verified = bool(validation.get("valid"))
            try:
                terrabot_test_state.update_context_candidate_status(
                    owner_hash, run_id, candidate["candidate_id"],
                    "verified" if row.context_candidate_verified else "rejected",
                    validation_errors=validation.get("errors") or [],
                    verified=row.context_candidate_verified,
                )
            except Exception as exc:
                _diag("context_candidate_verification_state_failed", level="warning", run_id=run_id, test_case_id=case.case_id, error=exc)

            if row.context_candidate_verified:
                row.fallback_context_created = _ensure_context_mapping(
                    core,
                    case,
                    run_id,
                    evidence_branch=evidence_branch,
                    evidence_commit_sha=branch_sha or case.commit_sha,
                )
                row.context_candidate_promoted = row.fallback_context_created
                row.context_stored = row.context_stored or row.fallback_context_created
                try:
                    terrabot_test_state.update_context_candidate_status(
                        owner_hash, run_id, candidate["candidate_id"],
                        "promoted" if row.context_candidate_promoted else "promotion_failed",
                        promoted=row.context_candidate_promoted,
                    )
                except Exception as exc:
                    _diag("context_candidate_state_update_failed", level="warning", run_id=run_id, test_case_id=case.case_id, error=exc)

        # New learning credit is branch-gated. A deterministic test target is
        # useful assertion truth, but it must not be written to shared repository
        # context when generation/validation/branch transport failed. This keeps
        # "Context PASS" from appearing as newly learned when no validated change
        # reached the isolated test branch. Pre-existing context remains visible.
        if not row.context_stored and row.branch_pushed:
            row.fallback_context_created = _ensure_context_mapping(
                core, case, run_id,
                evidence_branch=row.branch_name or case.branch,
                evidence_commit_sha=_branch_head_sha(core, case, row.branch_name) or case.commit_sha,
            )
            row.context_candidate_promoted = row.context_candidate_promoted or row.fallback_context_created
            row.context_stored = row.context_stored or row.fallback_context_created
            if row.fallback_context_created:
                _diag(
                    "repository_derived_context_persisted_after_branch",
                    run_id=run_id,
                    test_case_id=case.case_id,
                    path=case.path,
                    flag=case.flag,
                    branch=row.branch_name,
                )
        elif not row.context_stored and not row.branch_pushed:
            _diag(
                "repository_context_learning_skipped_without_branch",
                run_id=run_id,
                test_case_id=case.case_id,
                path=case.path,
                flag=case.flag,
            )

        # Add the NATURAL-LANGUAGE request wording as a second repository-context
        # synonym only after validated branch transport. This is the additive
        # learning loop: future users do not have to use the same alias that the
        # initial deterministic repository scan derived. The mapping remains
        # live-file validated by repository_context.add_repository_context.
        if row.branch_pushed and row.context_stored and case.phase1_prompt:
            try:
                learned = _ensure_context_mapping(
                    core,
                    case,
                    run_id,
                    evidence_branch=row.branch_name or case.branch,
                    evidence_commit_sha=_branch_head_sha(core, case, row.branch_name) or case.commit_sha,
                    subject_override=case.phase1_prompt,
                    statement_override=(
                        f"In {case.repo} environment {case.environment}, a request phrased as "
                        f"'{case.phase1_prompt}' refers to Boolean control {case.flag} in {case.path}."
                    ),
                    source_suffix="phase1_natural_language_learning",
                )
                _diag(
                    "repository_context_learning_variant_persisted",
                    run_id=run_id,
                    test_case_id=case.case_id,
                    phase=1,
                    stored=learned,
                    path=case.path,
                    flag=case.flag,
                )
            except Exception as exc:
                _diag(
                    "repository_context_learning_variant_failed",
                    level="warning",
                    run_id=run_id,
                    test_case_id=case.case_id,
                    phase=1,
                    error=exc,
                )

        # Capture the actual indexed record after production learning or the
        # verified harness promotion. Cursor later checks its semantics and
        # correlates it with the independent Phase 2 search result.
        final_context_search = _search_context(case) if row.context_stored else context_search
        final_context_match = _matching_context_record(case, final_context_search)
        row.cursor_evidence["context_after_phase1"] = {
            "stored": row.context_stored,
            "present_before": row.context_present_before,
            "production_created": row.production_context_created,
            "fallback_created": row.fallback_context_created,
            "record": _cursor_context_evidence(final_context_match),
        }

        # Phase 2 retrieval is checked with the actual randomized paraphrase and
        # then exercised through a completely fresh Teams conversation.
        final_context_id = str((final_context_match or {}).get("id") or "").strip()
        phase2_search, phase2_match = _search_phase2_context(
            case,
            required_context_id=final_context_id,
        )
        row.phase2_context_retrieved = phase2_match is not None

        phase2_request = _phase_request(case, case.phase2_prompt, p2_conversation, phase=2)
        phase2_request["teams_requester"] = f"terrabot-test-phase2-{run_id[-6:]}-{case.case_id}"
        if row.resolved_workflow:
            phase2_request["workflow"] = row.resolved_workflow
            _diag(
                "phase2_workflow_continuity_applied",
                run_id=run_id,
                test_case_id=case.case_id,
                workflow=row.resolved_workflow,
                source="phase1_production_backend_result",
            )
        if phase2_match and str(phase2_match.get("id") or "").strip():
            phase2_request["required_repository_context_ids"] = [str(phase2_match.get("id"))]
            phase2_request["repository_context_reuse_required"] = True
        # REQ 7: carry the P1 immutable target contract into P2.
        # P2 must rebuild/revalidate from stored context + live GitHub without
        # clarification. Including the P1 contract lets the backend short-circuit
        # its target resolution directly to the verified contract instead of
        # re-running the full Boolean inventory / Cursor flow.
        if row.target_contract and isinstance(row.target_contract, dict):
            phase2_request["p1_resolved_target_contract"] = dict(row.target_contract)
            _diag(
                "phase2_target_contract_injected",
                run_id=run_id,
                test_case_id=case.case_id,
                path=row.target_contract.get("path",""),
                flag=row.target_contract.get("flag",""),
                workflow=row.target_contract.get("workflow",""),
            )
        phase2_result, status = _invoke_backend(core, phase2_request, row)
        row.phase2_mode = str(phase2_result.get("mode") or "").lower()
        row.phase2_control_mentioned = _control_mentioned(case, phase2_result)
        _diag(
            "phase2_initial_backend_result",
            run_id=run_id,
            test_case_id=case.case_id,
            status=status,
            mode=row.phase2_mode or "<none>",
            ok=phase2_result.get("ok"),
            file_count=len(phase2_result.get("files") or []),
            candidate_count=len(phase2_result.get("candidates") or []),
            control_mentioned=row.phase2_control_mentioned,
            decision_state=phase2_result.get("decision_state") or "",
            repository_context_attached=bool(((phase2_result.get("test_diagnostics") or {}).get("repository_context") or {}).get("attached")),
            reply=str(phase2_result.get("reply") or "")[:500],
        )
        row.phase2_ok = status < 500 and bool(phase2_result.get("ok", True))
        first_phase2_mode = row.phase2_mode
        diagnostics = ((phase2_result.get("test_diagnostics") or {}).get("repository_context") or {})
        attached_ids = {str(value) for value in (diagnostics.get("context_ids") or []) if str(value)}
        used_context_ids = {
            str(value)
            for value in (
                diagnostics.get("used_context_ids")
                or diagnostics.get("reused_context_ids")
                or []
            )
            if str(value)
        }
        expected_context_id = str((phase2_match or {}).get("id") or "").strip()
        row.phase2_context_attached = bool(
            row.phase2_context_retrieved
            and expected_context_id
            and diagnostics.get("attached")
            and expected_context_id in attached_ids
        )
        row.phase2_context_backend_defect = bool(
            row.phase2_context_retrieved and not row.phase2_context_attached
        )
        row.boolean_context_attachment_failed = bool(row.phase2_context_backend_defect)
        if row.phase2_context_backend_defect:
            _diag(
                "phase2_context_attachment_backend_defect",
                level="error",
                run_id=run_id,
                test_case_id=case.case_id,
                expected_context_id=expected_context_id,
                attached_context_ids=sorted(attached_ids),
            )
        row.phase2_reused_without_clarification = bool(
            row.phase2_context_retrieved
            and row.phase2_context_attached
            and expected_context_id in used_context_ids
            and first_phase2_mode != "clarification"
        )
        if row.phase2_context_attached and expected_context_id not in used_context_ids:
            _diag(
                "phase2_context_attached_but_not_used",
                level="error",
                run_id=run_id,
                test_case_id=case.case_id,
                expected_context_id=expected_context_id,
                attached_context_ids=sorted(attached_ids),
                used_context_ids=sorted(used_context_ids),
            )

        # Still continue a Phase 2 clarification so file-generation accuracy is
        # measured independently from context retrieval accuracy.
        phase2_result, status, row.phase2_clarified = _resolve_automated_clarifications(
            core,
            case,
            row,
            phase2_result,
            status,
            phase=2,
            conversation_id=p2_conversation,
            phase_request=phase2_request,
            run_id=run_id,
        )
        row.phase2_ok = status < 500 and bool(phase2_result.get("ok", True))
        row.phase2_control_mentioned = row.phase2_control_mentioned or _control_mentioned(case, phase2_result)

        p2_target, p2_flag, row.phase2_file_generated, _ = _target_detection(case, phase2_result)
        row.phase2_target_ok = p2_target and p2_flag and _repo_matches(case, phase2_result)
        row.phase2_context_useful = bool(
            row.phase2_context_retrieved
            and row.phase2_context_attached
            and row.phase2_target_ok
            and row.phase2_reused_without_clarification
        )
        if row.phase2_context_useful and row.branch_pushed and case.phase2_prompt:
            try:
                _ensure_context_mapping(
                    core,
                    case,
                    run_id,
                    evidence_branch=row.branch_name or case.branch,
                    evidence_commit_sha=_branch_head_sha(core, case, row.branch_name) or case.commit_sha,
                    subject_override=case.phase2_prompt,
                    statement_override=(
                        f"In {case.repo} environment {case.environment}, a request phrased as "
                        f"'{case.phase2_prompt}' refers to Boolean control {case.flag} in {case.path}."
                    ),
                    source_suffix="phase2_reused_phrase_learning",
                )
                _diag(
                    "repository_context_learning_variant_persisted",
                    run_id=run_id,
                    test_case_id=case.case_id,
                    phase=2,
                    path=case.path,
                    flag=case.flag,
                )
            except Exception as exc:
                _diag(
                    "repository_context_learning_variant_failed",
                    level="warning",
                    run_id=run_id,
                    test_case_id=case.case_id,
                    phase=2,
                    error=exc,
                )
        row.cursor_evidence["phase2"] = {
            "first_mode": first_phase2_mode,
            "final_mode": str(phase2_result.get("mode") or ""),
            "context_retrieved": row.phase2_context_retrieved,
            "retrieved_record": _cursor_context_evidence(phase2_match),
            "context_attached": row.phase2_context_attached,
            "attached_context_ids": sorted(attached_ids),
            "used_context_ids": sorted(used_context_ids),
            "expected_context_id": expected_context_id,
            "reused_without_clarification": row.phase2_reused_without_clarification,
            "target_ok": row.phase2_target_ok,
            "generated_files": _cursor_file_evidence(case, phase2_result),
        }

        row.score = _calculate_case_score(row)
        row.backend_score = row.score
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
        row.failure_classification = terrabot_test_analysis.classify_result(case, row)

    _diag(
        "test_case_completed",
        run_id=run_id,
        test_case_id=case.case_id,
        expected_target_found=row.expected_target_found,
        correct_flag_detected=row.correct_flag_detected,
        phase1_control_mentioned=row.phase1_control_mentioned,
        phase2_control_mentioned=row.phase2_control_mentioned,
        phase1_mode=row.phase1_mode,
        phase2_mode=row.phase2_mode,
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
        failure_classification=row.failure_classification,
        error=row.error[:800] if row.error else "",
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


def _fallback_repository_questions(core: Any, spec: RepositorySpec, commit_sha: str, count: int) -> list[dict[str, Any]]:
    """Generate deterministic repo-Q&A probes without Cursor."""
    try:
        _sha, paths = _github_recursive_tree(core, spec)
    except Exception:
        paths = []
    tfvars = next((p for p in paths if p.endswith("hub.tfvars")), next((p for p in paths if p.endswith(".tfvars")), ""))
    main_tf = next((p for p in paths if p.endswith("/main.tf")), next((p for p in paths if p.endswith(".tf")), ""))
    if spec.cloud == "azure" and tfvars:
        question = "Which repository file pattern controls environment-specific Azure values in this repo?"
        expected = f"Environment-specific values are represented by tfvars files such as {tfvars}."
        evidence = [tfvars]
    elif spec.cloud == "aws" and main_tf:
        question = "Where are Terraform module consumers usually wired for an AWS environment in this repo?"
        expected = f"AWS environment consumers are represented by Terraform files such as {main_tf}."
        evidence = [main_tf]
    else:
        question = f"What Terraform repository conventions are visible in {spec.repo}?"
        expected = "Answer should summarize repository-grounded Terraform placement and workflow conventions."
        evidence = paths[:3]
    return [{
        "question_id": "fallback-q1",
        "question": question,
        "expected_answer": expected,
        "evidence_paths": evidence,
        "owner": spec.owner,
        "repo": spec.repo,
        "commit_sha": commit_sha,
        "fallback_generated": True,
    }][:max(1, count)]


def _run_repository_question_checks(
    core: Any,
    specs: list[RepositorySpec],
    *,
    run_id: str,
    requester_id: str,
) -> list[dict[str, Any]]:
    """Use Cursor to author and independently validate repo/workflow questions.

    These checks exercise Terrabot's plain-language repository Q&A path without
    creating Terraform, branches, or PRs. They are supplemental and currently
    run only in exploration/mixed modes so regression mutation-case scoring
    remains backward compatible.
    """
    try:
        per_repo = int(os.getenv("TERRABOT_TEST_CURSOR_REPOSITORY_QUESTION_CASES", "1"))
    except (TypeError, ValueError):
        per_repo = 1
    per_repo = max(0, min(per_repo, 3))
    if per_repo <= 0:
        return []
    checks: list[dict[str, Any]] = []
    for spec in specs:
        try:
            commit_sha = core.github_get_base_branch_sha_by_repo(spec.owner, spec.repo, spec.branch)
        except Exception as exc:
            _diag("repository_question_commit_resolution_failed", level="warning", run_id=run_id, repo=f"{spec.owner}/{spec.repo}", error=exc)
            continue
        questions = cursor_prompt_provider.generate_repository_questions(
            owner=spec.owner,
            repo=spec.repo,
            commit_sha=str(commit_sha or ""),
            run_id=run_id,
            count=per_repo,
            log_event=_diag,
        )
        if not questions:
            questions = _fallback_repository_questions(core, spec, str(commit_sha or ""), per_repo)
            _diag(
                "repository_question_fallback_used",
                level="warning",
                run_id=run_id,
                repo=f"{spec.owner}/{spec.repo}",
                generated=len(questions),
                reason="cursor_unavailable_or_empty",
            )
        for item in questions:
            qid = f"{spec.cloud}-{item.get('question_id') or uuid.uuid4().hex[:6]}"
            conversation_id = f"terrabot-test::{requester_id}::{run_id}::{qid}::repo-question"
            request = {
                "prompt": str(item.get("question") or ""),
                "original_prompt": str(item.get("question") or ""),
                "teams_conversation_id": conversation_id,
                "memory_conversation_id": f"{conversation_id}::memory::{uuid.uuid4().hex}",
                "teams_requester": f"terrabot-test-repo-question-{run_id[-6:]}",
                "source": "teams",
                "mode": "repo_qna",
                "foundry_intent": "repo_qna",
                "skip_infra_validation": True,
                "test_mode": True,
                "automated_test_phase": 0,
                "automated_test_case_id": qid,
                "cloud": spec.cloud,
                "requested_cloud": spec.cloud,
            }
            started = time.monotonic()
            try:
                response, status = core.handle_teams_chat_request(request)
                answer = str((response or {}).get("reply") or "").strip()
                backend_mode = str((response or {}).get("mode") or "").strip().lower()
                # Repository Q&A is intentionally read-only and not part of the
                # Terraform generation/validation/branch pipeline. Cursor authors
                # the question, Terrabot answers it in the Teams conversation, and
                # this harness records the answer without independent answer
                # validation. Only an infra/branch response is flagged as routing
                # leakage; it does not block mutation-case scoring.
                infra_modes = {"infra", "infra_preview", "branch_created", "pr_created"}
                routed_to_infra = bool(status < 400 and backend_mode in infra_modes)
                backend_ok = bool(status < 400 and answer and not routed_to_infra)
                if routed_to_infra:
                    _diag(
                        "repository_question_routed_to_infra",
                        level="warning",
                        run_id=run_id,
                        question_id=qid,
                        backend_mode=backend_mode,
                        classification="REPO_QNA_INTENT_FAILURE",
                    )
            except Exception as exc:
                response, status, answer, backend_mode, backend_ok = {}, 500, "", "", False
                _diag("repository_question_backend_failed", level="warning", run_id=run_id, question_id=qid, error=exc)
            # No answer validation for repository Q&A. Store the Teams answer so
            # the result report can show what Terrabot returned; correctness is
            # not scored by Cursor or backend validators.
            validation = {
                "completed": bool(status < 400 and answer),
                "correct": bool(status < 400 and answer),
                "reason": "Repository Q&A answer recorded only; validation intentionally skipped.",
                "evidence": [],
                "error": "" if (status < 400 and answer) else "backend_answer_missing",
            }
            check = {
                "question_id": qid,
                "cloud": spec.cloud,
                "repository": f"{spec.owner}/{spec.repo}",
                "commit_sha": str(commit_sha or ""),
                "question": str(item.get("question") or ""),
                "expected_answer": str(item.get("expected_answer") or ""),
                "evidence_paths": list(item.get("evidence_paths") or []),
                "terrabot_answer": answer,
                "backend_status": status,
                "backend_mode": backend_mode,
                "backend_intent": "repo_qna" if backend_ok else ("infra_generation" if backend_mode in {"infra", "infra_preview", "branch_created", "pr_created"} else "unknown"),
                "backend_ok": backend_ok,
                "classification": "PASS" if backend_ok else ("REPO_QNA_INTENT_FAILURE" if backend_mode in {"infra", "infra_preview", "branch_created", "pr_created"} else "REPO_QNA_ANSWER_MISSING"),
                "cursor_completed": bool(validation.get("completed")),
                "cursor_correct": bool(validation.get("correct")),
                "cursor_reason": str(validation.get("reason") or ""),
                "cursor_evidence": list(validation.get("evidence") or []),
                "cursor_error": str(validation.get("error") or ""),
                "duration_ms": int((time.monotonic() - started) * 1000),
            }
            checks.append(check)
            _diag(
                "repository_question_check_completed",
                run_id=run_id,
                question_id=qid,
                repo=check["repository"],
                backend_ok=backend_ok,
                cursor_correct=check["cursor_correct"],
                duration_ms=check["duration_ms"],
            )
    return checks


def _derive_test_cases(core: Any, cloud_filter: str, count: int, run_id: str, run_mode: str = "regression") -> tuple[list[TestCase], list[str]]:
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
            creation_slots = 0 if run_mode == "context-regression" else (1 if wanted >= 2 else 0)
            boolean_wanted = max(0, wanted - creation_slots)
            pool_size = boolean_wanted * 3 if run_mode in {"exploration", "mixed"} else boolean_wanted
            derived = _derive_cases_for_repository(
                core,
                spec,
                wanted=max(boolean_wanted, pool_size),
                run_id=run_id,
                semantic_generation=run_mode in {"exploration", "mixed"},
            )
            if run_mode == "context-regression" and derived:
                context_backed: list[TestCase] = []
                for candidate_case in derived:
                    try:
                        if _matching_context_record(candidate_case, _search_context(candidate_case)) is not None:
                            context_backed.append(candidate_case)
                    except Exception as exc:
                        _diag("context_regression_selection_failed", level="warning", run_id=run_id, test_case_id=candidate_case.case_id, error=exc)
                derived = context_backed[:boolean_wanted]
            elif run_mode in {"exploration", "mixed"} and derived:
                try:
                    coverage = terrabot_test_state.load_coverage(f"{spec.owner}/{spec.repo}")
                    derived = terrabot_test_coverage.select_cases(derived, coverage, boolean_wanted)
                except Exception as exc:
                    _diag("coverage_selection_failed", level="warning", run_id=run_id, repo=f"{spec.owner}/{spec.repo}", error=exc)
                    derived = derived[:boolean_wanted]
            else:
                derived = derived[:boolean_wanted]
            if creation_slots:
                creation_case = _derive_creation_case_for_repository(
                    core,
                    spec,
                    run_id=run_id,
                    index=1,
                )
                if creation_case is not None:
                    derived.append(creation_case)
                else:
                    errors.append(f"{spec.cloud}:{spec.repo}: no safe live resource-creation case could be derived.")
            cases.extend(derived)
            if len(derived) < wanted:
                errors.append(f"{spec.cloud}:{spec.repo}: only {len(derived)}/{wanted} valid environment-scoped cases could be derived.")
        except Exception as exc:
            message = f"{spec.cloud}:{spec.owner}/{spec.repo}: {exc}"
            errors.append(message)
            _diag("repository_case_generation_failed", level="error", run_id=run_id, error=message)
    return cases[:count], errors


def _cursor_validation_case_payload(item: TestCaseResult) -> dict[str, Any]:
    case = item.case
    return {
        "case_id": case.case_id,
        "case_type": case.case_type,
        "owner": case.owner,
        "repo": case.repo,
        "cloud": case.cloud,
        "environment": case.environment,
        "commit_sha": case.commit_sha,
        "base_branch": case.branch,
        "test_branch": item.branch_name,
        "test_branch_url": item.branch_url,
        "phase1_prompt": case.phase1_prompt,
        "phase2_prompt": case.phase2_prompt if case.case_type == "boolean_context" else "",
        "expected": {
            "path": case.path,
            "flag": case.flag,
            "alias": case.alias,
            "current_value": case.current_value,
            "desired_value": case.desired_value,
            "evidence_line": case.evidence_line,
        },
        "backend_assertions": {
            "target_found": item.expected_target_found,
            "control_detected": item.correct_flag_detected,
            "phase1_control_mentioned": item.phase1_control_mentioned,
            "phase2_control_mentioned": item.phase2_control_mentioned,
            "phase1_cursor_unavailable_fallback_used": item.phase1_cursor_unavailable_fallback_used,
        "phase2_cursor_unavailable_fallback_used": item.phase2_cursor_unavailable_fallback_used,
        "target_contract": dict(item.target_contract or {}),
        "phase1_mode": item.phase1_mode,
            "phase2_mode": item.phase2_mode,
            "resolved_workflow": item.resolved_workflow,
            "phase1_cursor_clarification_attempted": item.phase1_cursor_clarification_attempted,
            "phase1_cursor_clarification_used": item.phase1_cursor_clarification_used,
            "phase1_cursor_clarification_failed": item.phase1_cursor_clarification_failed,
            "phase1_cursor_clarification_error": item.phase1_cursor_clarification_error,
            "phase2_cursor_clarification_attempted": item.phase2_cursor_clarification_attempted,
            "phase2_cursor_clarification_used": item.phase2_cursor_clarification_used,
            "phase2_cursor_clarification_failed": item.phase2_cursor_clarification_failed,
            "phase2_cursor_clarification_error": item.phase2_cursor_clarification_error,
            "phase1_file_generated": item.phase1_file_generated,
            "precommit_validation_ok": item.validation_ok,
            "branch_pushed": item.branch_pushed,
            "context_stored": item.context_stored,
            "phase2_context_retrieved": item.phase2_context_retrieved,
            "phase2_context_attached": item.phase2_context_attached,
            "phase2_context_backend_defect": item.phase2_context_backend_defect,
            "phase1_freeform_clarification": item.phase1_freeform_clarification,
            "phase2_freeform_clarification": item.phase2_freeform_clarification,
            "phase2_target_ok": item.phase2_target_ok,
            "phase2_reused_without_clarification": item.phase2_reused_without_clarification,
            "backend_score": item.score,
        },
        "evidence": item.cursor_evidence,
    }


def _apply_cursor_validation_result(
    run_id: str,
    cases: list[TestCaseResult],
    validation: dict[str, Any],
) -> None:
    requested = bool(validation.get("enabled"))
    if not requested:
        return
    completed = bool(validation.get("completed"))
    verdicts = validation.get("case_results") or {}
    shared_error = str(validation.get("error") or "").strip()
    agent_url = str(validation.get("agent_url") or "").strip()
    duration_ms = int(validation.get("duration_ms") or 0)

    for item in cases:
        item.cursor_validation_requested = True
        item.cursor_agent_url = agent_url
        item.cursor_validation_duration_ms = duration_ms
        item.backend_score = item.score
        verdict = verdicts.get(item.case.case_id) if isinstance(verdicts, dict) else None
        if completed and isinstance(verdict, dict):
            item.cursor_validation_completed = True
            item.cursor_output_correct = bool(verdict.get("output_correct"))
            if item.case.case_type == "boolean_context":
                item.cursor_context_added = bool(verdict.get("context_added"))
                item.cursor_context_retrievable = bool(verdict.get("context_retrievable"))
                item.cursor_context_reused = bool(verdict.get("context_reused"))
                applicable_ok = bool(
                    item.cursor_output_correct
                    and item.cursor_context_added
                    and item.cursor_context_retrievable
                    and item.cursor_context_reused
                )
            else:
                applicable_ok = item.cursor_output_correct
            item.cursor_overall_ok = bool(verdict.get("overall_ok")) and applicable_ok
            item.cursor_validation_reason = str(verdict.get("reason") or "").strip()
            item.cursor_verdict_evidence = [
                str(value).strip()[:500]
                for value in (verdict.get("evidence") or [])[:8]
                if str(value).strip()
            ]
        else:
            item.cursor_validation_error = shared_error or "Cursor validation did not return a verdict for this case."

        item.score = _calculate_case_score(item)
        item.failure_classification = terrabot_test_analysis.classify_result(item.case, item)
        _diag(
            "cursor_validation_applied",
            run_id=run_id,
            test_case_id=item.case.case_id,
            completed=item.cursor_validation_completed,
            output_correct=item.cursor_output_correct,
            context_added=item.cursor_context_added if item.case.case_type == "boolean_context" else "n/a",
            context_retrievable=item.cursor_context_retrievable if item.case.case_type == "boolean_context" else "n/a",
            context_reused=item.cursor_context_reused if item.case.case_type == "boolean_context" else "n/a",
            overall_ok=item.cursor_overall_ok,
            backend_score=item.backend_score,
            final_score=item.score,
            error=item.cursor_validation_error,
        )


def _escape_table(value: Any, limit: int = 56) -> str:
    text = re.sub(r"\s+", " ", str(value if value is not None else "")).strip()
    text = text.replace("|", "\\|")
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


def _status(value: bool) -> str:
    return "PASS" if value else "FAIL"


def _cursor_status(item: TestCaseResult, attribute: str) -> str:
    if not item.cursor_validation_requested:
        return "N/A"
    if not item.cursor_validation_completed:
        return "ERROR"
    return _status(bool(getattr(item, attribute, False)))


def _cursor_context_status(item: TestCaseResult) -> str:
    if item.case.case_type != "boolean_context" or not item.cursor_validation_requested:
        return "N/A"
    if not item.cursor_validation_completed:
        return "ERROR"
    return (
        f"ADD:{_status(item.cursor_context_added)} "
        f"GET:{_status(item.cursor_context_retrievable)} "
        f"USE:{_status(item.cursor_context_reused)}"
    )


def format_test_run_report(run: TestRunResult) -> str:
    completed = len(run.cases)
    passed = sum(1 for item in run.cases if item.score == 100)
    average_score = round(sum(item.score for item in run.cases) / completed, 1) if completed else 0.0
    average_backend_score = round(
        sum((item.backend_score or item.score) for item in run.cases) / completed, 1
    ) if completed else 0.0
    branches = sum(1 for item in run.cases if item.branch_pushed)
    p1_files = sum(1 for item in run.cases if item.phase1_file_generated)
    context_cases = [item for item in run.cases if item.case.case_type == "boolean_context"]
    creation_cases = [item for item in run.cases if item.case.case_type == "resource_creation"]
    contexts = sum(1 for item in context_cases if item.context_stored)
    p2_context = sum(1 for item in context_cases if item.phase2_context_retrieved)
    p2_attached = sum(1 for item in context_cases if item.phase2_context_attached)
    p2_useful = sum(1 for item in context_cases if item.phase2_context_useful)
    production_context = sum(1 for item in context_cases if item.production_context_created)
    fallback_context = sum(1 for item in context_cases if item.fallback_context_created)
    p2_files = sum(1 for item in context_cases if item.phase2_file_generated)
    avg_calls = round(sum(item.bot_calls for item in run.cases) / completed, 1) if completed else 0.0
    avg_seconds = round(sum(item.duration_ms for item in run.cases) / max(completed, 1) / 1000.0, 1)
    freeform_p1 = sum(1 for item in run.cases if item.phase1_freeform_clarification)
    freeform_p2 = sum(1 for item in context_cases if item.phase2_freeform_clarification)
    context_attach_defects = sum(1 for item in context_cases if item.phase2_context_backend_defect)
    cursor_clarifications = sum(1 for item in run.cases if item.phase1_cursor_clarification_used or item.phase2_cursor_clarification_used)
    cursor_clarification_attempts = sum(
        int(item.phase1_cursor_clarification_attempted) + int(item.phase2_cursor_clarification_attempted)
        for item in run.cases
    )
    cursor_clarification_failures = sum(
        int(item.phase1_cursor_clarification_failed) + int(item.phase2_cursor_clarification_failed)
        for item in run.cases
    )
    repository_questions = list(run.repository_question_checks or [])
    repository_questions_correct = sum(
        1 for item in repository_questions
        if item.get("backend_ok")
    )

    lines = [
        "**Terrabot automated repository-context test results**",
        f"Run ID: `{run.run_id}`",
        f"Cases: **{completed}/{run.requested_cases}** | Full passes: **{passed}** | Average accuracy: **{average_score}%**",
        f"Phase 1 files generated: **{p1_files}/{completed}** | Branches pushed: **{branches}/{completed}** | Creation cases: **{len(creation_cases)}**",
        f"Boolean-context cases: **{len(context_cases)}** | Context available: **{contexts}/{len(context_cases) or 1}** | Production learned: **{production_context}** | Harness promoted: **{fallback_context}**",
        f"Phase 2 context retrieved: **{p2_context}/{len(context_cases) or 1}** | Attached to Foundry: **{p2_attached}/{len(context_cases) or 1}** | Useful: **{p2_useful}/{len(context_cases) or 1}** | Phase 2 files: **{p2_files}/{len(context_cases) or 1}**",
        f"Unexpected free-form clarifications: **P1 {freeform_p1} / P2 {freeform_p2}** | Cursor clarification assists: **{cursor_clarifications}** (attempts **{cursor_clarification_attempts}**, failures **{cursor_clarification_failures}**) | Context-attachment backend defects: **{context_attach_defects}**",
        f"Average backend calls/case: **{avg_calls}** | Average case time: **{avg_seconds}s** | Total: **{round(run.duration_ms / 1000.0, 1)}s**",
    ]
    if repository_questions:
        # req 15: Q&A metrics separate from mutation scoring
        qna_intent_ok = sum(1 for q in repository_questions if q.get("backend_ok"))
        qna_evidence_ok = sum(1 for q in repository_questions if q.get("evidence_paths"))
        qna_plain_text_ok = sum(1 for q in repository_questions if q.get("backend_ok") and not q.get("classification","").startswith("REPO_QNA"))
        qna_intent_failures = sum(1 for q in repository_questions if q.get("classification") == "REPO_QNA_INTENT_FAILURE")
        lines.append(
            f"Cursor repository/workflow Q&A checks: **{repository_questions_correct}/{len(repository_questions)}** correct "
            f"| Intent correct: **{qna_intent_ok}/{len(repository_questions)}** "
            f"| Evidence attached: **{qna_evidence_ok}/{len(repository_questions)}** "
            f"| Intent failures (routed to infra): **{qna_intent_failures}**"
        )
    lines.extend([
        "",
        "| Test | Type | Cloud/Env | Phase 1 prompt | Expected target | P1 mode | P2 mode | Target found | P1 file | Validation | Branch URL | Branch pushed | Context | P2 retrieved | P2 attached | P2 useful | Classification | Score |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---:|",
    ])
    for item in run.cases:
        case = item.case
        target = f"{case.path} :: {case.flag}" if case.flag else f"repository creation near {case.path}"
        if case.case_type == "boolean_context":
            if item.context_present_before and item.context_stored:
                context_status = "EXISTING"
            elif item.branch_pushed and item.context_stored:
                context_status = "LEARNED"
            elif item.context_stored:
                context_status = "AVAILABLE"
            else:
                context_status = "FAIL"
        else:
            context_status = "N/A"
        p2_context_status = _status(item.phase2_context_retrieved) if case.case_type == "boolean_context" else "N/A"
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_table(case.case_id, 22),
                    _escape_table(case.case_type.replace("_", " "), 20),
                    _escape_table(f"{case.cloud}/{case.environment}", 22),
                    _escape_table(case.phase1_prompt, 38),
                    _escape_table(target, 50),
                    _escape_table(item.phase1_mode or "<none>", 20),
                    _escape_table(item.phase2_mode or "<none>", 20) if case.case_type == "boolean_context" else "N/A",
                    _status(item.expected_target_found),
                    _status(item.phase1_file_generated),
                    _status(item.validation_ok),
                    _escape_table(item.branch_url or "N/A", 50),
                    _status(item.branch_pushed),
                    context_status,
                    p2_context_status,
                    _status(item.phase2_context_attached) if case.case_type == "boolean_context" else "N/A",
                    _status(item.phase2_context_useful) if case.case_type == "boolean_context" else "N/A",
                    _escape_table(item.failure_classification or "", 36),
                    f"{item.score}%",
                ]
            )
            + " |"
        )

    if repository_questions:
        lines.extend([
            "",
            "**Repository/workflow Q&A checks** (backend-validated intent routing)",
            "| Check | Repository | Question | Terrabot answer | Intent OK | Reason |",
            "|---|---|---|---|---|---|",
        ])
        for check in repository_questions:
            lines.append(
                "| "
                + " | ".join([
                    _escape_table(check.get("question_id") or "", 22),
                    _escape_table(check.get("repository") or "", 32),
                    _escape_table(check.get("question") or "", 60),
                    _escape_table(check.get("terrabot_answer") or "", 80),
                    _status(bool(check.get("backend_ok"))),
                    _escape_table(check.get("backend_intent") or "", 40),
                ])
                + " |"
            )

    failures = [item for item in run.cases if item.score < 100]
    if failures:
        lines.extend(["", "**Failed assertions**"])
        for item in failures[:12]:
            reasons: list[str] = []
            # Surface the root backend/harness exception first so the 360-char
            # report truncation cannot hide the actual failure behind derived
            # assertions such as target/file/context failures.
            if item.error:
                reasons.append("backend/harness error: " + item.error)
            if item.phase1_cursor_clarification_failed and not item.phase1_cursor_unavailable_fallback_used:
                reasons.append(
                    "Phase 1 Cursor clarification failed: "
                    + (item.phase1_cursor_clarification_error or "unresolved")
                )
            if item.phase2_cursor_clarification_failed and not item.phase2_cursor_unavailable_fallback_used:
                reasons.append(
                    "Phase 2 Cursor clarification failed: "
                    + (item.phase2_cursor_clarification_error or "unresolved")
                )
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
            if item.case.case_type == "boolean_context" and not item.context_stored:
                reasons.append("context not added")
            if item.case.case_type == "boolean_context" and not item.phase2_context_retrieved:
                reasons.append("Phase 2 context not retrieved")
            if item.case.case_type == "boolean_context" and not item.phase2_context_attached:
                reasons.append("Phase 2 context not attached to Foundry")
            if item.case.case_type == "boolean_context" and item.phase2_context_backend_defect:
                reasons.append("backend defect: retrieved Phase 2 context was not attached")
            if item.phase1_freeform_clarification:
                reasons.append("Phase 1 unexpected free-form clarification")
            if item.phase2_freeform_clarification:
                reasons.append("Phase 2 unexpected free-form clarification")
            if item.case.case_type == "boolean_context" and not item.phase2_context_useful:
                reasons.append("Phase 2 context not useful")
            if item.case.case_type == "boolean_context" and not item.phase2_file_generated:
                reasons.append("Phase 2 file not generated")
            if item.case.case_type == "boolean_context" and not item.phase2_target_ok:
                reasons.append("Phase 2 target mismatch")
            if item.case.case_type == "boolean_context" and not item.phase2_reused_without_clarification:
                reasons.append("Phase 2 required clarification")
            if not item.error and item.validation_error and not item.validation_ok:
                reasons.append(item.validation_error)
            if item.repair_exhausted:
                reasons.append("all repair attempts exhausted")
            if item.generation_truncated:
                reasons.append("agent returned truncated/placeholder file")
            if item.surgical_edit_anchor_failed:
                reasons.append("surgical edit: old_text not unique and no line anchor")
            if item.failed_validation_branch_pushed:
                diag_ref = item.diag_branch_url or item.diag_branch_name or "?"
                reasons.append("diagnostic branch pushed (validation_ok=False): " + diag_ref)
            if item.creation_case_invalid:
                reasons.append("creation test case was invalid (singleton/gated module)")
            branch_note = ""
            if item.branch_url:
                branch_note = f" branch=[{item.branch_name or 'view'}]({item.branch_url})"
            elif item.branch_name:
                branch_note = f" branch={item.branch_name}"
            if item.diag_branch_url:
                branch_note += f" diag=[{item.diag_branch_name or 'diag'}]({item.diag_branch_url})"
            lines.append(f"- `{item.case.case_id}`:{branch_note} {_escape_table('; '.join(reasons), 360)}")

    if run.discovery_errors:
        lines.extend(["", "**Repository discovery warnings**"])
        lines.extend(f"- {_escape_table(value, 300)}" for value in run.discovery_errors)

    lines.extend([
        "",
        "Phase 1 pushes each backend-validated test change to its own Terrabot test branch; no pull request is created. Phase 2 applies only to Boolean-context cases, uses a fresh synthetic Teams conversation, and does not push another branch. After all cases finish, one read-only Cursor review independently checks generated output plus context addition, retrieval, attachment, and reuse evidence. Cursor verdicts are included in full-pass scoring when the feature is enabled.",
        f"Search Function App logs with `run_id={run.run_id}` for `[TerrabotTest]` traces.",
        "Validation: agent self-validation + backend preservation/shape/semantic checks. Cursor used for prompt generation and target clarification only.",
    ])
    return "\n".join(lines)


def _case_state_payload(item: TestCaseResult) -> dict[str, Any]:
    return {
        "test_case_id": item.case.case_id,
        "case_type": item.case.case_type,
        "cloud": item.case.cloud,
        "environment": item.case.environment,
        "repo": item.case.repo,
        "prompt": item.case.phase1_prompt,
        "phase2_prompt": item.case.phase2_prompt,
        "expected_path": item.case.path,
        "expected_flag": item.case.flag,
        "expected_target_found": item.expected_target_found,
        "correct_flag_detected": item.correct_flag_detected,
        "phase1_control_mentioned": item.phase1_control_mentioned,
        "phase2_control_mentioned": item.phase2_control_mentioned,
        "phase1_cursor_unavailable_fallback_used": item.phase1_cursor_unavailable_fallback_used,
        "phase2_cursor_unavailable_fallback_used": item.phase2_cursor_unavailable_fallback_used,
        "target_contract": dict(item.target_contract or {}),
        "phase1_mode": item.phase1_mode,
        "phase2_mode": item.phase2_mode,
        "phase1_file_generated": item.phase1_file_generated,
        "validation_ok": item.validation_ok,
        "branch_pushed": item.branch_pushed,
        "branch": item.branch_name,
        "branch_url": item.branch_url,
        "context_stored": item.context_stored,
        "context_present_before": item.context_present_before,
        "production_context_created": item.production_context_created,
        "fallback_context_created": item.fallback_context_created,
        "context_gap_detected": item.context_gap_detected,
        "context_candidate_created": item.context_candidate_created,
        "context_candidate_verified": item.context_candidate_verified,
        "context_candidate_promoted": item.context_candidate_promoted,
        "phase2_context_retrieved": item.phase2_context_retrieved,
        "phase2_context_attached": item.phase2_context_attached,
        "phase2_context_useful": item.phase2_context_useful,
        "phase2_file_generated": item.phase2_file_generated,
        "phase2_target_ok": item.phase2_target_ok,
        "phase2_reused_without_clarification": item.phase2_reused_without_clarification,
        "bot_calls": item.bot_calls,
        "duration_ms": item.duration_ms,
        "backend_score": item.backend_score,
        "score": item.score,
        "cursor_validation_requested": item.cursor_validation_requested,
        "cursor_validation_completed": item.cursor_validation_completed,
        "cursor_output_correct": item.cursor_output_correct,
        "cursor_context_added": item.cursor_context_added,
        "cursor_context_retrievable": item.cursor_context_retrievable,
        "cursor_context_reused": item.cursor_context_reused,
        "cursor_overall_ok": item.cursor_overall_ok,
        "cursor_validation_reason": item.cursor_validation_reason,
        "cursor_validation_error": item.cursor_validation_error,
        "cursor_agent_url": item.cursor_agent_url,
        "cursor_validation_duration_ms": item.cursor_validation_duration_ms,
        "cursor_verdict_evidence": list(item.cursor_verdict_evidence),
        "failure_classification": item.failure_classification,
        "error": item.error or item.validation_error or item.cursor_validation_error,
    }


def _new_run_id() -> str:
    return "ctx-" + time.strftime("%Y%m%d-%H%M%S", time.gmtime()) + "-" + uuid.uuid4().hex[:6]


def _status_report(aad_object_id: str, requested_run_id: str = "") -> tuple[dict, int]:
    owner_hash = terrabot_test_state.requester_hash(aad_object_id)
    state = (
        terrabot_test_state.load_run(owner_hash, requested_run_id)
        if requested_run_id
        else terrabot_test_state.latest_run(owner_hash)
    )
    if not state:
        return {
            "ok": False,
            "mode": "automated_test_status",
            "reply": "No automated Terrabot test run was found for this Teams identity.",
        }, 404
    run_id = str(state.get("run_id") or "")
    status = str(state.get("status") or "unknown")
    requested = int(state.get("requested_cases") or 0)
    completed = int(state.get("completed_cases") or 0)
    report = str(state.get("report") or "").strip()
    if status == "completed" and report:
        return {"ok": True, "mode": "automated_test_status", "run_id": run_id, "reply": report}, 200
    lines = [
        "**Terrabot automated test status**",
        f"Run ID: `{run_id}`",
        f"Status: **{status}**",
        f"Completed: **{completed}/{requested}**",
    ]
    if state.get("started_at"):
        lines.append(f"Started: `{state.get('started_at')}`")
    if state.get("error"):
        lines.extend(["", f"Error: `{str(state.get('error'))[:1000]}`"])
    return {"ok": status != "failed", "mode": "automated_test_status", "run_id": run_id, "reply": "\n".join(lines)}, 200


def _replay_source_run_id(prompt: str) -> str:
    repeat = TEST_REPEAT_RE.fullmatch(str(prompt or "").strip())
    return str(repeat.group(1) or "").strip() if repeat else ""


def _same_prompts_requested(prompt: str) -> bool:
    value = str(prompt or "").strip()
    suffix = TEST_SAME_SUFFIX_RE.fullmatch(value)
    if suffix:
        return True
    match = TEST_MODE_COMMAND_RE.fullmatch(value)
    return bool(match and str(match.group(3) or "").lower() == "same")


def _case_manifest(cases: list[TestCase]) -> list[dict[str, Any]]:
    return [{
        "case_id": c.case_id, "case_type": c.case_type, "cloud": c.cloud,
        "owner": c.owner, "repo": c.repo, "branch": c.branch, "commit_sha": c.commit_sha,
        "path": c.path, "environment": c.environment, "flag": c.flag, "alias": c.alias,
        "current_value": c.current_value, "desired_value": c.desired_value,
        "evidence_line": c.evidence_line, "phase1_prompt": c.phase1_prompt,
        "phase2_prompt": c.phase2_prompt,
    } for c in cases]


def _cases_from_manifest(core: Any, manifest: list[dict[str, Any]], run_id: str) -> list[TestCase]:
    rebuilt: list[TestCase] = []
    for item in manifest or []:
        if not isinstance(item, dict):
            continue
        cloud = str(item.get("cloud") or "").lower()
        repo = str(item.get("repo") or "")
        owner = str(item.get("owner") or getattr(core, "GITHUB_OWNER", "") or "")
        branch = str(item.get("branch") or (getattr(core, "GITHUB_AWS_BASE_BRANCH", "main") if cloud == "aws" else getattr(core, "GITHUB_AZURE_BASE_BRANCH", "main")) or "main")
        path = str(item.get("path") or "")
        flag = str(item.get("flag") or "")
        current_value = bool(item.get("current_value", False))
        desired_value = bool(item.get("desired_value", not current_value))
        # Replay keeps the exact prompts but refreshes the commit SHA. Boolean cases
        # also refresh the current literal so stale manifests fail explicitly rather than
        # silently changing semantic targets.
        try:
            commit_sha = str(core.github_get_base_branch_sha_by_repo(owner, repo, branch) or item.get("commit_sha") or "")
        except Exception:
            commit_sha = str(item.get("commit_sha") or "")
        if flag and path:
            try:
                live = core.github_get_file_content_by_repo(owner, repo, path, ref=branch) or ""
                m = re.search(rf"(?m)^\s*{re.escape(flag)}\s*=\s*(true|false)\s*(?:#.*)?$", live, re.IGNORECASE)
                if not m or (m.group(1).lower() == "true") != current_value:
                    raise ValueError(f"Replay target changed in live repository: {path}::{flag}")
            except Exception as exc:
                raise ValueError(f"Cannot replay {item.get('case_id')}: {exc}") from exc
        rebuilt.append(TestCase(
            case_id=str(item.get("case_id") or f"replay-{run_id[-6:]}") ,
            case_type=str(item.get("case_type") or "boolean_context"), cloud=cloud,
            owner=owner, repo=repo, branch=branch, commit_sha=commit_sha, path=path,
            environment=str(item.get("environment") or _infer_environment(path, cloud)),
            flag=flag, alias=str(item.get("alias") or (_humanize_flag(flag) if flag else "repository resource")),
            current_value=current_value, desired_value=desired_value,
            evidence_line=str(item.get("evidence_line") or ""),
            phase1_prompt=str(item.get("phase1_prompt") or ""),
            phase2_prompt=str(item.get("phase2_prompt") or ""),
        ))
    return rebuilt


def _manifest_from_saved_case_rows(core: Any, owner_hash: str, source_run_id: str) -> list[dict[str, Any]]:
    source = terrabot_test_state.load_run(owner_hash, source_run_id) or {}
    try:
        manifest = json.loads(str(source.get("case_manifest_json") or "[]"))
    except Exception:
        manifest = []
    if manifest:
        return manifest
    rows = terrabot_test_state.load_case_results(owner_hash, source_run_id)
    owner = str(getattr(core, "GITHUB_OWNER", "") or "")
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        cloud = str(row.get("cloud") or "").lower()
        repo = str(row.get("repo") or (getattr(core, "GITHUB_AWS_REPO", "") if cloud == "aws" else getattr(core, "GITHUB_AZURE_REPO", "")))
        flag = str(row.get("expected_flag") or "")
        path = str(row.get("expected_path") or "")
        current = False
        if flag and path:
            branch = str(getattr(core, "GITHUB_AWS_BASE_BRANCH", "main") if cloud == "aws" else getattr(core, "GITHUB_AZURE_BASE_BRANCH", "main"))
            live = core.github_get_file_content_by_repo(owner, repo, path, ref=branch) or ""
            m = re.search(rf"(?m)^\s*{re.escape(flag)}\s*=\s*(true|false)\s*(?:#.*)?$", live, re.IGNORECASE)
            if not m:
                continue
            current = m.group(1).lower() == "true"
        result.append({
            "case_id": row.get("test_case_id"), "case_type": row.get("case_type"), "cloud": cloud,
            "owner": owner, "repo": repo, "branch": "main", "path": path,
            "environment": row.get("environment"), "flag": flag,
            "alias": _humanize_flag(flag) if flag else "repository resource",
            "current_value": current, "desired_value": (not current) if flag else True,
            "evidence_line": "", "phase1_prompt": row.get("prompt"), "phase2_prompt": row.get("phase2_prompt"),
        })
    return result


def start_automated_test_run(core: Any, data: dict) -> tuple[dict, int]:
    """Authorize, persist and enqueue a run; never execute Foundry work inline."""
    del core
    prompt = str((data or {}).get("prompt") or "").strip()
    aad_object_id = str((data or {}).get("aad_object_id") or "").strip()
    _assert_authorized(aad_object_id)

    status_match = TEST_STATUS_RE.fullmatch(prompt)
    if status_match:
        return _status_report(aad_object_id, str(status_match.group(1) or "").strip())

    replay_source_run_id = _replay_source_run_id(prompt)
    same_requested = _same_prompts_requested(prompt)
    if replay_source_run_id:
        source = terrabot_test_state.load_run(terrabot_test_state.requester_hash(aad_object_id), replay_source_run_id)
        if not source:
            return {"ok": False, "mode": "automated_test", "reply": f"Replay source run `{replay_source_run_id}` was not found."}, 404
        cloud_filter = str(source.get("cloud_filter") or "all")
        count = int(source.get("requested_cases") or 4)
        run_mode = str(source.get("run_mode") or "mixed")
    else:
        cloud_filter, count = _parse_command(prompt)
        run_mode = _parse_test_mode(prompt)
    run_id = _new_run_id()
    owner_hash = terrabot_test_state.requester_hash(aad_object_id)
    conversation_reference = (data or {}).get("conversation_reference") or {}
    state = {
        "run_id": run_id,
        "requester_hash": owner_hash,
        "status": "queued",
        "requested_cases": count,
        "completed_cases": 0,
        "cloud_filter": cloud_filter,
        "run_mode": run_mode,
        "created_at": terrabot_test_state.utc_now(),
        "conversation_reference": conversation_reference,
        "replay_source_run_id": replay_source_run_id,
        "same_prompts_requested": same_requested,
    }
    terrabot_test_state.save_run(state)
    job = {
        "run_id": run_id,
        "prompt": prompt,
        "aad_object_id": aad_object_id,
        "requester_hash": owner_hash,
        "cloud_filter": cloud_filter,
        "run_mode": run_mode,
        "requested_cases": count,
        "conversation_reference": conversation_reference,
        "replay_source_run_id": replay_source_run_id,
        "same_prompts_requested": same_requested,
        "created_at": state["created_at"],
    }
    try:
        terrabot_test_state.enqueue_run(job)
    except Exception as exc:
        state.update({"status": "failed", "error": str(exc), "completed_at": terrabot_test_state.utc_now()})
        terrabot_test_state.save_run(state)
        raise

    _diag(
        "test_run_queued",
        run_id=run_id,
        requester_hash=owner_hash,
        cloud=cloud_filter,
        requested_cases=count,
        max_parallel_cases=_MAX_PARALLEL_CASES,
    )
    return {
        "ok": True,
        "mode": "automated_test_queued",
        "run_id": run_id,
        "reply": (
            "**Terrabot automated test run queued**\n"
            f"Run ID: `{run_id}`\n"
            f"Cases: **{count}** | Cloud scope: **{cloud_filter}** | Mode: **{run_mode}** | Parallel cases: **{_MAX_PARALLEL_CASES}**\n\n"
            "The Teams request has completed; the queue worker will run the tests in the background "
            "and post the final table back to this conversation. Use `run tests status` to check progress."
        ),
    }, 202




def _test_runner_lease_seconds() -> int:
    try:
        configured = int(os.getenv("TERRABOT_TEST_RUNNER_LEASE_SECONDS", "900"))
    except (TypeError, ValueError):
        configured = 900
    return max(120, min(configured, 21600))


def _test_runner_lease_heartbeat(owner_hash: str, run_id: str, worker_id: str, stop_event: threading.Event) -> None:
    lease_seconds = _test_runner_lease_seconds()
    interval = max(30, min(lease_seconds // 3, 180))
    renew = getattr(terrabot_test_state, "renew_run_lease", None)
    if not callable(renew):
        return
    while not stop_event.wait(interval):
        try:
            ok = bool(renew(owner_hash, run_id, worker_id=worker_id, lease_seconds=lease_seconds))
            _diag(
                "test_run_lease_heartbeat",
                level="info" if ok else "warning",
                run_id=run_id,
                worker_id=worker_id,
                renewed=ok,
            )
            if not ok:
                return
        except Exception as exc:
            _diag("test_run_lease_heartbeat_failed", level="warning", run_id=run_id, worker_id=worker_id, error=exc)

def execute_automated_test_job(core: Any, job: dict) -> str:
    """Run one queued test job with durable progress and bounded parallelism."""
    run_id = str((job or {}).get("run_id") or "").strip()
    aad_object_id = str((job or {}).get("aad_object_id") or "").strip()
    owner_hash = str((job or {}).get("requester_hash") or terrabot_test_state.requester_hash(aad_object_id)).strip()
    prompt = str((job or {}).get("prompt") or "run tests").strip()
    if not run_id:
        raise ValueError("Queued automated-test job is missing run_id.")
    _assert_authorized(aad_object_id)
    replay_source_run_id = str((job or {}).get("replay_source_run_id") or _replay_source_run_id(prompt)).strip()
    same_requested = bool((job or {}).get("same_prompts_requested") or _same_prompts_requested(prompt))
    if replay_source_run_id:
        source = terrabot_test_state.load_run(owner_hash, replay_source_run_id) or {}
        cloud_filter = str(source.get("cloud_filter") or (job or {}).get("cloud_filter") or "all")
        count = int(source.get("requested_cases") or (job or {}).get("requested_cases") or 4)
        run_mode = str(source.get("run_mode") or (job or {}).get("run_mode") or "mixed").lower()
    else:
        cloud_filter, count = _parse_command(prompt)
        run_mode = str((job or {}).get("run_mode") or _parse_test_mode(prompt)).lower()
    started = time.monotonic()
    run_state = {
        "run_id": run_id,
        "requester_hash": owner_hash,
        "status": "running",
        "requested_cases": count,
        "completed_cases": 0,
        "cloud_filter": cloud_filter,
        "run_mode": run_mode,
        "created_at": str((job or {}).get("created_at") or terrabot_test_state.utc_now()),
        "started_at": terrabot_test_state.utc_now(),
        "conversation_reference": (job or {}).get("conversation_reference") or {},
    }
    worker_id = uuid.uuid4().hex
    lease_seconds = _test_runner_lease_seconds()
    lease_acquired = False
    heartbeat_stop = threading.Event()
    heartbeat_thread: threading.Thread | None = None
    acquire_fn = getattr(terrabot_test_state, "acquire_run_lease", None)
    if callable(acquire_fn):
        lease_acquired = bool(acquire_fn(owner_hash, run_id, worker_id=worker_id, lease_seconds=lease_seconds))
    else:
        lease_acquired = True
    if not lease_acquired:
        existing = terrabot_test_state.load_run(owner_hash, run_id) or {}
        lease_snapshot_fn = getattr(terrabot_test_state, "active_run_lease", None)
        lease_snapshot = lease_snapshot_fn(owner_hash, run_id) if callable(lease_snapshot_fn) else {}
        active = bool((lease_snapshot or {}).get("active"))
        _diag(
            "test_run_worker_duplicate_suppressed",
            level="warning",
            run_id=run_id,
            worker_id=worker_id,
            existing_status=existing.get("status") or "",
            lease_owner=(lease_snapshot or {}).get("lease_owner") or existing.get("lease_owner") or "",
            lease_expires_at=(lease_snapshot or {}).get("lease_expires_at") or existing.get("lease_expires_at") or "",
            active_lease=active,
        )
        if active:
            # A healthy worker owns this run; this duplicate queue delivery can
            # finish normally and Azure may delete only this duplicate message.
            return str(existing.get("report") or "Terrabot automated test run is already running on another worker.")
        # No active lease could be proven. Raise so Azure leaves the queue
        # message retryable instead of deleting the only continuation trigger.
        raise RuntimeError(f"Terrabot automated test run {run_id} has no active lease; leaving queue message retryable.")

    claimed_state = terrabot_test_state.load_run(owner_hash, run_id) or {}
    run_state["lease_owner"] = worker_id
    run_state["lease_acquired_at"] = str(claimed_state.get("lease_acquired_at") or terrabot_test_state.utc_now())
    run_state["lease_expires_at"] = str(claimed_state.get("lease_expires_at") or "")
    terrabot_test_state.save_run(run_state)
    # Do not carry a stale lease expiry through later REPLACE saves; save_run
    # preserves the current table lease when running updates omit these fields.
    run_state.pop("lease_acquired_at", None)
    run_state.pop("lease_expires_at", None)
    heartbeat_thread = threading.Thread(
        target=_test_runner_lease_heartbeat,
        args=(owner_hash, run_id, worker_id, heartbeat_stop),
        name=f"terrabot-test-lease-{run_id[-6:]}",
        daemon=True,
    )
    heartbeat_thread.start()
    _diag(
        "test_run_worker_started",
        run_id=run_id,
        worker_id=worker_id,
        cloud=cloud_filter,
        requested_cases=count,
        lease_expires_at=run_state.get("lease_expires_at", ""),
        max_parallel_cases=_MAX_PARALLEL_CASES,
    )

    try:
        if run_mode in {"context-regression", "mixed"}:
            for spec in _repo_specs(core, cloud_filter):
                try:
                    current_sha, _ = _github_recursive_tree(core, spec)
                    stats = terrabot_context_revalidation.revalidate_repository_context(
                        core,
                        repo_owner=spec.owner,
                        repo_name=spec.repo,
                        branch=spec.branch,
                        current_commit_sha=current_sha,
                    )
                    _diag("repository_context_revalidation_completed", run_id=run_id, repo=f"{spec.owner}/{spec.repo}", **stats)
                except Exception as exc:
                    _diag("repository_context_revalidation_failed", level="warning", run_id=run_id, repo=f"{spec.owner}/{spec.repo}", error=exc)
        replay_manifest: list[dict[str, Any]] = []
        if replay_source_run_id:
            replay_manifest = _manifest_from_saved_case_rows(core, owner_hash, replay_source_run_id)
        elif same_requested:
            previous = terrabot_test_state.latest_completed_run(owner_hash, run_mode=run_mode, cloud_filter=cloud_filter, requested_cases=count)
            if previous:
                replay_source_run_id = str(previous.get("run_id") or "")
                replay_manifest = _manifest_from_saved_case_rows(core, owner_hash, replay_source_run_id)
        if replay_manifest:
            cases = _cases_from_manifest(core, replay_manifest, run_id)
            discovery_errors = []
            _diag("test_cases_replayed", run_id=run_id, replay_source_run_id=replay_source_run_id, cases=len(cases))
        else:
            cases, discovery_errors = _derive_test_cases(core, cloud_filter, count, run_id, run_mode=run_mode)
        # When enabled, Cursor now actively authors the mutation prompts from the
        # pinned repositories instead of being only a post-run validator. Target
        # metadata remains immutable; Cursor varies realistic developer language
        # across creation/provisioning, modification, enable/disable and
        # decommission/delete-style requests while preserving test intent.
        try:
            if not replay_manifest:
                cases = cursor_prompt_provider.apply_cursor_generated_prompts(
                    cases,
                    run_id=run_id,
                    log_event=_diag,
                )
            else:
                _diag("cursor_prompt_generation_skipped_for_replay", run_id=run_id, replay_source_run_id=replay_source_run_id)
        except Exception as exc:
            # Respect the provider's fail-open/fail-closed behavior. The helper
            # only raises when configured fail-open=false.
            _diag(
                "cursor_prompt_generation_job_failed",
                level="error",
                run_id=run_id,
                error=exc,
            )
            raise
        run_state["case_manifest"] = _case_manifest(cases)
        run_state["replay_source_run_id"] = replay_source_run_id
        terrabot_test_state.save_run(run_state)
        result = TestRunResult(run_id=run_id, requested_cases=count, discovery_errors=discovery_errors)
        indexed_cases = list(enumerate(cases, start=1))
        completed_by_index: dict[int, TestCaseResult] = {}
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(_MAX_PARALLEL_CASES, max(1, len(indexed_cases))),
            thread_name_prefix="terrabot-test-case",
        ) as pool:
            future_map = {
                pool.submit(_run_case, core, case, run_id, aad_object_id): index
                for index, case in indexed_cases
            }
            for future in concurrent.futures.as_completed(future_map):
                index = future_map[future]
                try:
                    case_result = future.result()
                except Exception as exc:
                    # _run_case normally absorbs case-local errors. Keep the run
                    # alive even if a worker future itself escapes unexpectedly.
                    case = indexed_cases[index - 1][1]
                    case_result = TestCaseResult(case=case, error=str(exc), duration_ms=0)
                    _diag("test_case_future_failed", level="error", run_id=run_id, test_case_id=case.case_id, error=exc)
                completed_by_index[index] = case_result
                terrabot_test_state.save_case_result(owner_hash, run_id, index, _case_state_payload(case_result))
                run_state["completed_cases"] = len(completed_by_index)
                run_state["discovery_errors"] = discovery_errors
                terrabot_test_state.save_run(run_state)
                _diag(
                    "test_run_progress_saved",
                    run_id=run_id,
                    completed_cases=len(completed_by_index),
                    requested_cases=count,
                )

        result.cases = [completed_by_index[index] for index in sorted(completed_by_index)]

        if run_mode in {"exploration", "mixed"}:
            try:
                result.repository_question_checks = _run_repository_question_checks(
                    core,
                    _repo_specs(core, cloud_filter),
                    run_id=run_id,
                    requester_id=aad_object_id,
                )
            except Exception as exc:
                _diag(
                    "repository_question_checks_failed",
                    level="warning",
                    run_id=run_id,
                    error=exc,
                )

        # Deterministic backend checks have already completed and gated every
        # branch push. Run one independent read-only Cursor review across the
        # complete run, then include its verdicts in durable state and Teams.
        # Cursor post-generation/result validation is intentionally disabled.
        # Cursor may author prompts, but generated Terraform correctness is owned
        # by Foundry self-validation plus deterministic backend validators.
        if terrabot_cursor_result_validator.cursor_result_validation_enabled():
            cursor_validation = terrabot_cursor_result_validator.validate_test_run_with_cursor(
                run_id=run_id,
                cases=[_cursor_validation_case_payload(item) for item in result.cases],
            )
            _apply_cursor_validation_result(run_id, result.cases, cursor_validation)
        else:
            _diag(
                "cursor_result_validation_skipped",
                run_id=run_id,
                reason="disabled_prompt_generation_only",
            )
        for index, case_result in enumerate(result.cases, start=1):
            terrabot_test_state.save_case_result(
                owner_hash, run_id, index, _case_state_payload(case_result)
            )
            try:
                key = terrabot_test_coverage.coverage_key(case_result.case)
                repository_key = f"{case_result.case.owner}/{case_result.case.repo}"
                existing = terrabot_test_state.load_coverage(repository_key).get(key) or {}
                test_count = int(existing.get("test_count") or 0) + 1
                failure_count = int(existing.get("failure_count") or 0) + (0 if case_result.score == 100 else 1)
                terrabot_test_state.save_coverage(
                    repository_key,
                    key,
                    {
                        "test_count": test_count,
                        "failure_count": failure_count,
                        "last_score": case_result.score,
                        "last_backend_score": case_result.backend_score,
                        "last_cursor_overall_ok": None,  # cursor result validation disabled
                        "last_run_id": run_id,
                        "last_commit_sha": case_result.case.commit_sha,
                        "last_classification": case_result.failure_classification,
                        "updated_at": terrabot_test_state.utc_now(),
                    },
                )
            except Exception as exc:
                _diag(
                    "coverage_state_save_failed",
                    level="warning",
                    run_id=run_id,
                    test_case_id=case_result.case.case_id,
                    error=exc,
                )

        result.duration_ms = int((time.monotonic() - started) * 1000)
        report = format_test_run_report(result)
        run_state.update({
            "status": "completed",
            "completed_cases": len(result.cases),
            "completed_at": terrabot_test_state.utc_now(),
            "duration_ms": result.duration_ms,
            "discovery_errors": discovery_errors,
            "repository_question_checks": list(result.repository_question_checks),
            "cursor_validation": {
                "enabled": False,
                "completed": False,
                "note": "Cursor result validation temporarily disabled; using agent self-validation + backend validation.",
            },
            "report": report,
            "lease_owner": "",
            "lease_acquired_at": "",
            "lease_expires_at": "",
        })
        terrabot_test_state.save_run(run_state)
        _diag(
            "test_run_worker_completed",
            run_id=run_id,
            requested_cases=count,
            completed_cases=len(result.cases),
            full_passes=sum(1 for item in result.cases if item.score == 100),
            duration_ms=result.duration_ms,
        )
        return report
    except Exception as exc:
        run_state.update({
            "status": "failed",
            "completed_at": terrabot_test_state.utc_now(),
            "duration_ms": int((time.monotonic() - started) * 1000),
            "error": str(exc),
            "lease_owner": "",
            "lease_acquired_at": "",
            "lease_expires_at": "",
        })
        terrabot_test_state.save_run(run_state)
        _diag("test_run_worker_failed", level="error", run_id=run_id, error=exc)
        return (
            "**Terrabot automated test run failed**\n"
            f"Run ID: `{run_id}`\n"
            f"Completed cases: **{run_state.get('completed_cases', 0)}/{count}**\n"
            f"Error: `{str(exc)[:1500]}`\n\n"
            f"Search Function App logs with `run_id={run_id}` for the complete trace."
        )
    finally:
        if lease_acquired:
            heartbeat_stop.set()
            if heartbeat_thread is not None:
                try:
                    heartbeat_thread.join(timeout=5)
                except Exception:
                    pass
            release_fn = getattr(terrabot_test_state, "release_run_lease", None)
            if callable(release_fn):
                try:
                    release_fn(owner_hash, run_id, worker_id=worker_id)
                    _diag("test_run_lease_released", run_id=run_id, worker_id=worker_id)
                except Exception as release_exc:
                    _diag("test_run_lease_release_failed", level="warning", run_id=run_id, worker_id=worker_id, error=release_exc)

def handle_teams_automated_test_request(core: Any, data: dict) -> tuple[dict, int]:
    """Queue a private test run or return durable status; never block Teams."""
    prompt = str((data or {}).get("prompt") or "").strip()
    aad_object_id = str((data or {}).get("aad_object_id") or "").strip()
    if not is_automated_test_command(prompt):
        return {"ok": False, "reply": "Unsupported automated test command."}, 400
    try:
        return start_automated_test_run(core, data)
    except PermissionError as exc:
        _diag("test_run_denied", level="warning", reason=exc)
        return {"ok": False, "reply": str(exc), "mode": "automated_test"}, 403
    except Exception as exc:
        _diag("test_run_enqueue_failed", level="error", error=exc)
        return {
            "ok": False,
            "reply": f"Terrabot could not queue the automated test run: {exc}",
            "mode": "automated_test",
        }, 500
