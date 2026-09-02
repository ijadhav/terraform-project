"""Cursor-backed prompt generation for Terrabot repository-context tests.

This module changes only Phase 1 and Phase 2 natural-language prompts. Test
case targets remain backend-derived and immutable, while the existing Terrabot
workflow continues to perform generation, validation, branch writes, context
indexing, Phase 2 reuse checks, durable state, and Teams reporting.

Cursor is invoked through the Cloud Agents v1 REST API so the Function App does
not require a new SDK dependency. A custom compatible gateway can be selected
with TERRABOT_CURSOR_API_BASE_URL.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from typing import Any, Callable, Iterable, Sequence

import requests

from shared_code import terraform_primary_context
from shared_code.automated_tests import cursor_readonly_guard

LOGGER = logging.getLogger("terrabot.automated_tests.cursor")
LOGGER.setLevel(logging.INFO)

_TRUE_VALUES = {"1", "true", "yes", "on"}
_SUCCESS_STATUSES = {"FINISHED", "COMPLETED", "SUCCEEDED", "SUCCESS"}
_FAILURE_STATUSES = {"ERROR", "FAILED", "CANCELLED", "CANCELED", "EXPIRED"}
_SCHEMA_VERSION = "terrabot.cursor.test-prompts.v1"
_CLARIFICATION_SCHEMA_VERSION = "terrabot.cursor.clarification.v1"


class CursorPromptError(RuntimeError):
    """Raised when Cursor cannot return a valid prompt set."""


def _enabled() -> bool:
    value = os.getenv("TERRABOT_CURSOR_PROMPT_GENERATION_ENABLED", "false")
    return value.strip().lower() in _TRUE_VALUES


def _fail_open() -> bool:
    value = os.getenv("TERRABOT_CURSOR_FAIL_OPEN", "true")
    return value.strip().lower() in _TRUE_VALUES


def _api_key() -> str:
    return (
        os.getenv("TERRABOT_CURSOR_API_KEY", "").strip()
        or os.getenv("CURSOR_API_KEY", "").strip()
    )


def _base_url() -> str:
    value = os.getenv("TERRABOT_CURSOR_API_BASE_URL", "https://api.cursor.com")
    return value.strip().rstrip("/") or "https://api.cursor.com"


def _float_setting(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _int_setting(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _emit(
    event: str,
    *,
    level: str = "info",
    log_event: Callable[..., None] | None = None,
    **fields: Any,
) -> None:
    parts = [f"event={event}", f"level={level}"]
    for key, value in fields.items():
        text = re.sub(r"\s+", " ", str(value if value is not None else "")).strip()
        if len(text) > 3500:
            text = text[:3497] + "..."
        parts.append(f"{key}={text}")
    message = "[TerrabotCursor] " + " ".join(parts)
    if level in {"warning", "error"}:
        LOGGER.warning(message)
    else:
        LOGGER.info(message)
    if log_event:
        try:
            log_event(event, level=level, **fields)
        except Exception:
            LOGGER.debug("Unable to mirror Cursor event to Terrabot diagnostics", exc_info=True)


def _case_value(case: Any, name: str) -> Any:
    return getattr(case, name)


def _case_payload(case: Any) -> dict[str, Any]:
    return {
        "case_id": str(_case_value(case, "case_id")),
        "cloud": str(_case_value(case, "cloud")),
        "environment": str(_case_value(case, "environment")),
        "path": str(_case_value(case, "path")),
        "flag": str(_case_value(case, "flag")),
        "alias": str(_case_value(case, "alias")),
        "current_value": bool(_case_value(case, "current_value")),
        "desired_value": bool(_case_value(case, "desired_value")),
        "evidence_line": str(_case_value(case, "evidence_line")),
    }


def _group_key(case: Any) -> tuple[str, str, str, str, str]:
    return (
        str(_case_value(case, "owner")),
        str(_case_value(case, "repo")),
        str(_case_value(case, "branch")),
        str(_case_value(case, "commit_sha")),
        str(_case_value(case, "cloud")),
    )


def _build_cursor_instruction(cases: Sequence[Any], run_id: str) -> str:
    owner, repo, branch, commit_sha, cloud = _group_key(cases[0])
    context = terraform_primary_context.primary_context_payload() or {}
    context_text = str(context.get("content") or "")
    context_sha = str(context.get("sha256") or "")
    immutable_cases = [_case_payload(case) for case in cases]

    response_example = {
        "schema_version": _SCHEMA_VERSION,
        "repository_commit_sha": commit_sha,
        "cases": [
            {
                "case_id": str(_case_value(case, "case_id")),
                "phase1_prompt": "natural language infrastructure request",
                "phase2_prompt": "different natural language paraphrase",
            }
            for case in cases
        ],
    }

    return "\n".join(
        [
            "You are generating test prompts for Terrabot. This is a read-only repository-analysis task.",
            "",
            "Repository and provenance:",
            f"- repository: https://github.com/{owner}/{repo}",
            f"- requested branch: {branch}",
            f"- exact required commit: {commit_sha}",
            f"- cloud: {cloud}",
            f"- Terrabot run id: {run_id}",
            "",
            "Mandatory safety constraints:",
            "1. Inspect the checked-out repository at the exact required commit before answering.",
            "2. Read relevant complete Terraform files, README/module README files, .github instructions/templates, and .serena/.Serena if present.",
            "3. Do not edit files, run any command that writes files, create a branch, commit, push, open a pull request, or generate Terraform code.",
            "4. The candidate target metadata below is immutable. Do not change path, flag, environment, values, repository, or case IDs.",
            "5. Produce only two concise, realistic Teams-style user prompts per case. Phase 2 must be a semantic paraphrase of Phase 1.",
            "6. The prompts should describe the requested behavior naturally. Avoid exposing the expected file path or implementation details unless natural user language requires them.",
            "7. Return JSON only. Do not wrap it in Markdown and do not add commentary.",
            "",
            "Primary Terraform authoring context:",
            f"- context sha256: {context_sha or 'unavailable'}",
            "- authority: repository conventions only; live selected-commit repository evidence wins on conflict.",
            context_text or "Primary context was unavailable; rely on live repository guidance.",
            "",
            "Immutable candidate test cases:",
            json.dumps(immutable_cases, ensure_ascii=False, indent=2),
            "",
            "Required response shape:",
            json.dumps(response_example, ensure_ascii=False, indent=2),
        ]
    )


def _http_json(
    session: Any,
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    timeout: float,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    retries = _int_setting("TERRABOT_CURSOR_HTTP_RETRIES", 2, 0, 5)
    last_error = ""
    for attempt in range(retries + 1):
        try:
            response = session.request(
                method,
                url,
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            status_code = int(getattr(response, "status_code", 0) or 0)
            body_text = str(getattr(response, "text", "") or "")
            if 200 <= status_code < 300:
                data = response.json()
                if not isinstance(data, dict):
                    raise CursorPromptError(f"Cursor returned non-object JSON from {method} {url}.")
                return data
            last_error = f"HTTP {status_code}: {body_text[:800]}"
            if status_code != 429 and status_code < 500:
                break
        except (requests.RequestException, ValueError, CursorPromptError) as exc:
            last_error = str(exc)
        if attempt < retries:
            time.sleep(min(1.0 * (2**attempt), 5.0))
    raise CursorPromptError(f"Cursor API request failed for {method} {url}: {last_error}")


def _extract_agent_and_run(create_result: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    agent = create_result.get("agent") if isinstance(create_result.get("agent"), dict) else {}
    run = create_result.get("run") if isinstance(create_result.get("run"), dict) else {}
    if not run and isinstance(create_result.get("initialRun"), dict):
        run = create_result["initialRun"]

    agent_id = str(agent.get("id") or create_result.get("agentId") or "").strip()
    run_id = str(
        run.get("id")
        or create_result.get("runId")
        or agent.get("latestRunId")
        or ""
    ).strip()
    if not agent_id:
        raise CursorPromptError("Cursor create-agent response did not contain an agent id.")
    return agent_id, run_id, run


def _resolve_run_id(
    session: Any,
    agent_id: str,
    run_id: str,
    *,
    base_url: str,
    headers: dict[str, str],
    timeout: float,
) -> str:
    if run_id:
        return run_id
    agent = _http_json(
        session,
        "GET",
        f"{base_url}/v1/agents/{agent_id}",
        headers=headers,
        timeout=timeout,
    )
    resolved = str(agent.get("latestRunId") or "").strip()
    if not resolved:
        raise CursorPromptError("Cursor agent record did not contain latestRunId.")
    return resolved


def _cancel_run_best_effort(
    session: Any,
    agent_id: str,
    run_id: str,
    *,
    base_url: str,
    headers: dict[str, str],
    timeout: float,
) -> None:
    try:
        session.request(
            "POST",
            f"{base_url}/v1/agents/{agent_id}/runs/{run_id}/cancel",
            headers=headers,
            timeout=timeout,
        )
    except Exception:
        LOGGER.debug("Unable to cancel timed-out Cursor run", exc_info=True)


def _archive_agent_best_effort(
    session: Any,
    agent_id: str,
    *,
    base_url: str,
    headers: dict[str, str],
    timeout: float,
    run_label: str,
    log_event: Callable[..., None] | None,
) -> None:
    enabled = os.getenv("TERRABOT_CURSOR_ARCHIVE_AGENT_AFTER_RUN", "true")
    if enabled.strip().lower() not in _TRUE_VALUES:
        return
    try:
        response = session.request(
            "POST",
            f"{base_url}/v1/agents/{agent_id}/archive",
            headers=headers,
            timeout=timeout,
        )
        status_code = int(getattr(response, "status_code", 0) or 0)
        if 200 <= status_code < 300:
            _emit(
                "cursor_agent_archived",
                log_event=log_event,
                run_id=run_label,
                cursor_agent_id=agent_id,
            )
            return
        _emit(
            "cursor_agent_archive_failed",
            level="warning",
            log_event=log_event,
            run_id=run_label,
            cursor_agent_id=agent_id,
            status_code=status_code,
        )
    except Exception as exc:
        _emit(
            "cursor_agent_archive_failed",
            level="warning",
            log_event=log_event,
            run_id=run_label,
            cursor_agent_id=agent_id,
            error=exc,
        )


def _wait_for_result(
    session: Any,
    agent_id: str,
    run_id: str,
    initial_run: dict[str, Any],
    *,
    base_url: str,
    headers: dict[str, str],
    request_timeout: float,
    run_timeout: float,
    poll_interval: float,
    run_label: str,
    log_event: Callable[..., None] | None,
) -> tuple[str, dict[str, Any]]:
    started = time.monotonic()
    current = dict(initial_run or {})
    last_status = ""

    while True:
        status = str(current.get("status") or "").strip().upper()
        if status and status != last_status:
            _emit(
                "cursor_agent_run_status",
                log_event=log_event,
                run_id=run_label,
                cursor_agent_id=agent_id,
                cursor_run_id=run_id,
                status=status,
            )
            last_status = status

        if status in _SUCCESS_STATUSES:
            result = current.get("result")
            if not isinstance(result, str) or not result.strip():
                raise CursorPromptError("Cursor run finished without a textual result.")
            return result.strip(), dict(current)
        if status in _FAILURE_STATUSES:
            detail = current.get("error") or current.get("result") or current
            raise CursorPromptError(f"Cursor run ended with status {status}: {str(detail)[:1000]}")

        elapsed = time.monotonic() - started
        if elapsed >= run_timeout:
            _cancel_run_best_effort(
                session,
                agent_id,
                run_id,
                base_url=base_url,
                headers=headers,
                timeout=request_timeout,
            )
            raise CursorPromptError(
                f"Cursor run timed out after {int(elapsed)} seconds "
                f"(agent={agent_id}, run={run_id})."
            )

        if current:
            time.sleep(poll_interval)
        current = _http_json(
            session,
            "GET",
            f"{base_url}/v1/agents/{agent_id}/runs/{run_id}",
            headers=headers,
            timeout=request_timeout,
        )


def _parse_result_text(result_text: str) -> dict[str, Any]:
    text = str(result_text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise CursorPromptError("Cursor result did not contain a JSON object.")
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise CursorPromptError(f"Cursor result JSON was invalid: {exc}") from exc
    if not isinstance(data, dict):
        raise CursorPromptError("Cursor result must be a JSON object.")
    return data


def _validated_prompts(
    data: dict[str, Any],
    cases: Sequence[Any],
    expected_commit: str,
) -> dict[str, tuple[str, str]]:
    if str(data.get("schema_version") or "").strip() != _SCHEMA_VERSION:
        raise CursorPromptError(
            f"Cursor result schema_version must be {_SCHEMA_VERSION}."
        )
    returned_commit = str(data.get("repository_commit_sha") or "").strip()
    if returned_commit != expected_commit:
        raise CursorPromptError(
            "Cursor result repository_commit_sha did not match the exact "
            f"requested commit ({returned_commit or 'missing'} != {expected_commit})."
        )

    expected_ids = [str(_case_value(case, "case_id")) for case in cases]
    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list):
        raise CursorPromptError("Cursor result cases must be an array.")

    by_id: dict[str, tuple[str, str]] = {}
    all_prompts: set[str] = set()
    maximum = _int_setting("TERRABOT_CURSOR_MAX_PROMPT_CHARS", 1200, 100, 5000)
    for item in raw_cases:
        if not isinstance(item, dict):
            raise CursorPromptError("Every Cursor result case must be an object.")
        case_id = str(item.get("case_id") or "").strip()
        phase1 = re.sub(r"\s+", " ", str(item.get("phase1_prompt") or "")).strip()
        phase2 = re.sub(r"\s+", " ", str(item.get("phase2_prompt") or "")).strip()
        if not case_id or case_id in by_id:
            raise CursorPromptError("Cursor result contains a missing or duplicate case_id.")
        if not phase1 or not phase2:
            raise CursorPromptError(f"Cursor result case {case_id} has an empty prompt.")
        if len(phase1) > maximum or len(phase2) > maximum:
            raise CursorPromptError(
                f"Cursor result case {case_id} exceeded {maximum} prompt characters."
            )
        if phase1.casefold() == phase2.casefold():
            raise CursorPromptError(
                f"Cursor result case {case_id} did not provide a distinct Phase 2 paraphrase."
            )
        for prompt in (phase1, phase2):
            normalized = prompt.casefold()
            if normalized in all_prompts:
                raise CursorPromptError("Cursor returned duplicate prompts across test cases.")
            all_prompts.add(normalized)
        by_id[case_id] = (phase1, phase2)

    if set(by_id) != set(expected_ids):
        missing = sorted(set(expected_ids) - set(by_id))
        extra = sorted(set(by_id) - set(expected_ids))
        raise CursorPromptError(
            f"Cursor result case IDs did not match; missing={missing}, extra={extra}."
        )
    return by_id


def _generate_for_group(
    cases: Sequence[Any],
    *,
    run_id: str,
    session: Any,
    log_event: Callable[..., None] | None,
) -> list[Any]:
    owner, repo, branch, commit_sha, cloud = _group_key(cases[0])
    base_url = _base_url()
    api_key = _api_key()
    if not api_key:
        raise CursorPromptError(
            "TERRABOT_CURSOR_API_KEY or CURSOR_API_KEY is not configured."
        )

    request_timeout = _float_setting(
        "TERRABOT_CURSOR_REQUEST_TIMEOUT_SECONDS", 30.0, 5.0, 120.0
    )
    run_timeout = _float_setting(
        "TERRABOT_CURSOR_RUN_TIMEOUT_SECONDS", 300.0, 15.0, 1800.0
    )
    poll_interval = _float_setting(
        "TERRABOT_CURSOR_POLL_INTERVAL_SECONDS", 2.0, 0.2, 30.0
    )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    instruction = _build_cursor_instruction(cases, run_id)
    create_payload = {
        "name": f"Terrabot prompts {run_id} {repo}"[:100],
        "mode": "plan",
        "prompt": {"text": instruction},
        "repos": [
            {
                "url": f"https://github.com/{owner}/{repo}",
                "startingRef": commit_sha,
            }
        ],
        "workOnCurrentBranch": False,
        "autoCreatePR": False,
        "skipReviewerRequest": True,
    }

    remote_before = cursor_readonly_guard.snapshot_remote_branches(create_payload["repos"])
    _emit(
        "cursor_prompt_generation_started",
        log_event=log_event,
        run_id=run_id,
        repo=f"{owner}/{repo}",
        cloud=cloud,
        branch=branch,
        commit_sha=commit_sha,
        cases=len(cases),
        instruction_characters=len(instruction),
    )
    create_result = _http_json(
        session,
        "POST",
        f"{base_url}/v1/agents",
        headers=headers,
        timeout=request_timeout,
        payload=create_payload,
    )
    agent_id, cursor_run_id, initial_run = _extract_agent_and_run(create_result)
    try:
        cursor_run_id = _resolve_run_id(
            session,
            agent_id,
            cursor_run_id,
            base_url=base_url,
            headers=headers,
            timeout=request_timeout,
        )
        agent = create_result.get("agent") if isinstance(create_result.get("agent"), dict) else {}
        _emit(
            "cursor_agent_created",
            log_event=log_event,
            run_id=run_id,
            repo=f"{owner}/{repo}",
            cursor_agent_id=agent_id,
            cursor_run_id=cursor_run_id,
            cursor_agent_url=str(agent.get("url") or ""),
        )

        result_text, terminal_run = _wait_for_result(
            session,
            agent_id,
            cursor_run_id,
            initial_run,
            base_url=base_url,
            headers=headers,
            request_timeout=request_timeout,
            run_timeout=run_timeout,
            poll_interval=poll_interval,
            run_label=run_id,
            log_event=log_event,
        )
        git_result = terminal_run.get("git") if isinstance(terminal_run.get("git"), dict) else {}
        pushed_branches = git_result.get("branches") if isinstance(git_result, dict) else []
        remote_after = cursor_readonly_guard.snapshot_remote_branches(create_payload["repos"])
        mutations = cursor_readonly_guard.cursor_reported_remote_mutations(
            terminal_run, remote_before, remote_after
        )
        if mutations:
            _emit(
                "cursor_read_only_violation",
                level="error",
                log_event=log_event,
                run_id=run_id,
                repo=f"{owner}/{repo}",
                commit_sha=commit_sha,
                cursor_agent_id=agent_id,
                cursor_run_id=cursor_run_id,
                remote_mutations=json.dumps(mutations, ensure_ascii=False)[:1000],
            )
            raise CursorPromptError(
                "Cursor changed a verified remote GitHub branch during read-only prompt generation: "
                + json.dumps(mutations, ensure_ascii=False)[:1000]
            )
        if pushed_branches and not remote_before:
            _emit(
                "cursor_remote_verification_unavailable",
                level="warning",
                log_event=log_event,
                run_id=run_id,
                repo=f"{owner}/{repo}",
                reported_branches=len(pushed_branches),
            )
        parsed = _parse_result_text(result_text)
        prompts = _validated_prompts(parsed, cases, commit_sha)

        generated: list[Any] = []
        for case in cases:
            case_id = str(_case_value(case, "case_id"))
            phase1, phase2 = prompts[case_id]
            generated.append(
                replace(case, phase1_prompt=phase1, phase2_prompt=phase2)
            )
            _emit(
                "cursor_prompt_case_generated",
                log_event=log_event,
                run_id=run_id,
                repo=f"{owner}/{repo}",
                test_case_id=case_id,
                phase1_prompt=phase1,
                phase2_prompt=phase2,
            )

        _emit(
            "cursor_prompt_generation_completed",
            log_event=log_event,
            run_id=run_id,
            repo=f"{owner}/{repo}",
            commit_sha=commit_sha,
            cases=len(generated),
            cursor_agent_id=agent_id,
            cursor_run_id=cursor_run_id,
        )
        return generated
    finally:
        _archive_agent_best_effort(
            session,
            agent_id,
            base_url=base_url,
            headers=headers,
            timeout=request_timeout,
            run_label=run_id,
            log_event=log_event,
        )


def apply_cursor_generated_prompts(
    cases: Iterable[Any],
    *,
    run_id: str,
    log_event: Callable[..., None] | None = None,
    session: Any | None = None,
) -> list[Any]:
    """Return cases with Cursor-generated prompts, preserving all target fields.

    The default is fail-open. Any unavailable, timed-out, or invalid Cursor
    group keeps its existing backend-derived prompts so the current production
    test workflow continues unchanged.
    """

    original = list(cases)
    if not original:
        return original
    if not _enabled():
        _emit(
            "cursor_prompt_generation_skipped",
            log_event=log_event,
            run_id=run_id,
            reason="disabled",
            cases=len(original),
        )
        return original

    groups: dict[tuple[str, str, str, str, str], list[tuple[int, Any]]] = {}
    for index, case in enumerate(original):
        groups.setdefault(_group_key(case), []).append((index, case))

    output = list(original)
    http_session = session or requests
    max_workers = _int_setting(
        "TERRABOT_CURSOR_MAX_PARALLEL_REPOSITORIES", 2, 1, 4
    )

    def process(items: list[tuple[int, Any]]) -> tuple[list[tuple[int, Any]], Exception | None]:
        group_cases = [case for _, case in items]
        try:
            generated = _generate_for_group(
                group_cases,
                run_id=run_id,
                session=http_session,
                log_event=log_event,
            )
            return list(zip([index for index, _ in items], generated)), None
        except Exception as exc:
            return items, exc

    results: list[tuple[list[tuple[int, Any]], Exception | None]] = []
    if len(groups) == 1 or max_workers == 1:
        results = [process(items) for items in groups.values()]
    else:
        with ThreadPoolExecutor(max_workers=min(max_workers, len(groups))) as executor:
            futures = {executor.submit(process, items): key for key, items in groups.items()}
            for future in as_completed(futures):
                results.append(future.result())

    failures: list[Exception] = []
    for indexed_cases, error in results:
        if error is None:
            for index, generated_case in indexed_cases:
                output[index] = generated_case
            continue

        failures.append(error)
        sample = indexed_cases[0][1]
        owner, repo, _branch, commit_sha, _cloud = _group_key(sample)
        _emit(
            "cursor_prompt_generation_failed",
            level="warning" if _fail_open() else "error",
            log_event=log_event,
            run_id=run_id,
            repo=f"{owner}/{repo}",
            commit_sha=commit_sha,
            error=error,
        )
        if _fail_open():
            _emit(
                "cursor_prompt_fallback_used",
                level="warning",
                log_event=log_event,
                run_id=run_id,
                repo=f"{owner}/{repo}",
                cases=len(indexed_cases),
                reason=error,
            )
        else:
            _emit(
                "cursor_prompt_failure_propagated",
                level="error",
                log_event=log_event,
                run_id=run_id,
                repo=f"{owner}/{repo}",
                cases=len(indexed_cases),
                reason=error,
            )

    if failures and not _fail_open():
        raise CursorPromptError(
            "Cursor prompt generation failed and TERRABOT_CURSOR_FAIL_OPEN is false: "
            + "; ".join(str(error) for error in failures)
        )
    return output


def resolve_repository_clarification(
    *,
    owner: str,
    repo: str,
    commit_sha: str,
    original_prompt: str,
    clarification_text: str,
    candidates: Sequence[dict[str, Any]] | None = None,
    run_id: str = "",
    case_id: str = "",
    session: Any | None = None,
    log_event: Callable[..., None] | None = None,
) -> dict[str, Any]:
    """Ask Cursor to answer a Terrabot clarification from the pinned live repo.

    The immutable expected test target is intentionally *not* supplied. Cursor
    must inspect the repository and resolve the user's semantic request itself.
    Structured candidates, when present, are included only as choices already
    exposed by Terrabot. The result is an answer suitable for the same pending
    workflow plus optional path/flag evidence for test-side verification.
    """
    api_key = _api_key()
    if not api_key:
        _emit(
            "cursor_clarification_configuration_missing",
            level="warning",
            log_event=log_event,
            run_id=run_id,
            test_case_id=case_id,
            repo=f"{owner}/{repo}",
            reason="TERRABOT_CURSOR_API_KEY/CURSOR_API_KEY is not configured",
        )
        return {}
    session = session or requests.Session()
    base_url = _base_url()
    request_timeout = _float_setting("TERRABOT_CURSOR_REQUEST_TIMEOUT_SECONDS", 30.0, 5.0, 120.0)
    run_timeout = _float_setting("TERRABOT_CURSOR_RUN_TIMEOUT_SECONDS", 300.0, 15.0, 1800.0)
    poll_interval = _float_setting("TERRABOT_CURSOR_POLL_INTERVAL_SECONDS", 2.0, 0.2, 30.0)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    candidate_payload = [dict(item) for item in (candidates or []) if isinstance(item, dict)]
    instruction = "\n".join([
        "You are resolving one Terrabot infrastructure clarification using only the pinned repository.",
        "This is a read-only repository-analysis task. Do not edit, commit, push, create branches, or open PRs.",
        f"Repository: https://github.com/{owner}/{repo}",
        f"Exact commit: {commit_sha}",
        f"Original user request: {original_prompt}",
        f"Terrabot clarification: {clarification_text}",
        "Terrabot structured candidates:",
        json.dumps(candidate_payload, ensure_ascii=False, indent=2),
        "Inspect the complete relevant Terraform environment files and repository guidance before answering.",
        "Use an analytical repository traversal: (1) identify the behavior/resource concept in the user's words, (2) inspect every Boolean assignment in the resolved environment file(s), (3) trace plausible flags into their module/resource arguments and nearby comments, (4) reject controls for different behavior, and (5) choose a control only when one is uniquely supported.",
        "Do not require literal word overlap between the user phrase and the Terraform identifier; infer meaning from wiring and nearby repository context.",
        "Evaluate Terrabot's structured candidates for semantic relevance before choosing one.",
        "Do not choose a candidate merely because it is offered. If every supplied candidate is unrelated to the requested resource/behavior, reject the candidate list and independently identify the correct live repository control.",
        "If exactly one supplied candidate is genuinely correct, set resolution_type=candidate, candidates_relevant=true, and selected_index to its 1-based position.",
        "If the supplied candidates are all unrelated but exactly one live repository control implements the request, set resolution_type=repository_control, candidates_relevant=false, selected_index=null, and return that exact selected_path and selected_flag.",
        "If no unique repository-grounded control can be determined, set resolution_type=unresolved and selected_index=null.",
        f"Return JSON only with schema_version={_CLARIFICATION_SCHEMA_VERSION} and keys: schema_version, answer, resolution_type, candidates_relevant, selected_index, selected_path, selected_flag, selected_current_value, selected_new_value, reason, evidence.",
        "For candidate or repository_control resolutions, selected_current_value and selected_new_value must be JSON booleans, must differ, and must describe the exact live assignment before/after the requested change.",
        "For unresolved, set selected_current_value=null, selected_new_value=null, selected_path=\"\", selected_flag=\"\", and evidence=[].",
        "evidence must contain at most 4 short repository-grounded strings identifying the live file/assignment or wiring that proves the choice.",
        "The answer must be concise and directly usable as the clarification reply. Never invent a path, flag, current value, or target value.",
    ])
    repos = [{"url": f"https://github.com/{owner}/{repo}", "startingRef": commit_sha}]
    remote_before = cursor_readonly_guard.snapshot_remote_branches(repos)
    create_payload = {
        "name": f"Terrabot clarification {run_id} {case_id}"[:100],
        "mode": "plan",
        "prompt": {"text": instruction},
        "repos": repos,
        "workOnCurrentBranch": False,
        "autoCreatePR": False,
        "skipReviewerRequest": True,
    }
    try:
        _emit(
            "cursor_clarification_started",
            log_event=log_event,
            run_id=run_id,
            test_case_id=case_id,
            repo=f"{owner}/{repo}",
            candidate_count=len(candidate_payload),
            prompt_chars=len(instruction),
        )
        created = _http_json(
            session,
            "POST",
            f"{base_url}/v1/agents",
            headers=headers,
            timeout=request_timeout,
            payload=create_payload,
        )
        agent_id, cursor_run_id, initial_run = _extract_agent_and_run(created)
        cursor_run_id = _resolve_run_id(
            session, agent_id, cursor_run_id,
            base_url=base_url, headers=headers, timeout=request_timeout,
        )
        result_text, terminal = _wait_for_result(
            session, agent_id, cursor_run_id, initial_run,
            base_url=base_url,
            headers=headers,
            request_timeout=request_timeout,
            run_timeout=run_timeout,
            poll_interval=poll_interval,
            run_label=run_id or case_id or "clarification",
            log_event=log_event,
        )
        remote_after = cursor_readonly_guard.snapshot_remote_branches(repos)
        mutations = cursor_readonly_guard.cursor_reported_remote_mutations(
            terminal, remote_before, remote_after
        )
        if mutations:
            raise CursorPromptError(
                "Cursor changed a verified remote GitHub branch while resolving a clarification: "
                + json.dumps(mutations, ensure_ascii=False)[:1000]
            )
        parsed = _parse_result_text(result_text)
        schema_version = str(parsed.get("schema_version") or "").strip()
        if schema_version != _CLARIFICATION_SCHEMA_VERSION:
            raise CursorPromptError(
                f"Cursor clarification schema_version must be {_CLARIFICATION_SCHEMA_VERSION}."
            )
        answer = re.sub(r"\s+", " ", str(parsed.get("answer") or "")).strip()
        resolution_type = str(parsed.get("resolution_type") or "").strip().lower()
        if resolution_type not in {"candidate", "repository_control", "unresolved"}:
            raise CursorPromptError("Cursor clarification resolution_type is invalid.")
        candidates_relevant = parsed.get("candidates_relevant")
        if not isinstance(candidates_relevant, bool):
            raise CursorPromptError("Cursor clarification candidates_relevant must be Boolean.")
        selected_path = str(parsed.get("selected_path") or "").strip().strip("/")
        selected_flag = str(parsed.get("selected_flag") or "").strip()
        selected_current_value = parsed.get("selected_current_value")
        selected_new_value = parsed.get("selected_new_value")
        selected_index = parsed.get("selected_index")
        use_structured_picker = False
        if resolution_type == "candidate":
            if not candidate_payload or not candidates_relevant:
                raise CursorPromptError("Cursor selected candidate resolution without a relevant candidate list.")
            try:
                idx = int(selected_index)
            except (TypeError, ValueError) as exc:
                raise CursorPromptError("Cursor clarification selected_index must be an integer for candidate resolution.") from exc
            if idx < 1 or idx > len(candidate_payload):
                raise CursorPromptError("Cursor clarification selected_index is outside the Terrabot candidate list.")
            chosen = candidate_payload[idx - 1]
            chosen_path = str(chosen.get("path") or "").strip().strip("/")
            chosen_flag = str(chosen.get("flag") or "").strip()
            if selected_path and chosen_path and selected_path != chosen_path:
                raise CursorPromptError("Cursor clarification selected_path disagrees with the selected Terrabot candidate.")
            if selected_flag and chosen_flag and selected_flag != chosen_flag:
                raise CursorPromptError("Cursor clarification selected_flag disagrees with the selected Terrabot candidate.")
            selected_path = selected_path or chosen_path
            selected_flag = selected_flag or chosen_flag
            chosen_current = chosen.get("current_value")
            chosen_new = chosen.get("new_value")
            if isinstance(chosen_current, bool):
                if selected_current_value is not None and selected_current_value is not chosen_current:
                    raise CursorPromptError("Cursor clarification selected_current_value disagrees with the selected Terrabot candidate.")
                selected_current_value = chosen_current
            elif isinstance(chosen_current, str) and chosen_current.strip().lower() in {"true", "false"}:
                candidate_current = chosen_current.strip().lower() == "true"
                if selected_current_value is not None and selected_current_value is not candidate_current:
                    raise CursorPromptError("Cursor clarification selected_current_value disagrees with the selected Terrabot candidate.")
                selected_current_value = candidate_current
            if isinstance(chosen_new, bool):
                if selected_new_value is not None and selected_new_value is not chosen_new:
                    raise CursorPromptError("Cursor clarification selected_new_value disagrees with the selected Terrabot candidate.")
                selected_new_value = chosen_new
            elif isinstance(chosen_new, str) and chosen_new.strip().lower() in {"true", "false"}:
                candidate_new = chosen_new.strip().lower() == "true"
                if selected_new_value is not None and selected_new_value is not candidate_new:
                    raise CursorPromptError("Cursor clarification selected_new_value disagrees with the selected Terrabot candidate.")
                selected_new_value = candidate_new
            answer = str(chosen.get("index") or idx)
            selected_index = idx
            use_structured_picker = True
        elif resolution_type == "repository_control":
            if selected_index is not None:
                raise CursorPromptError("Cursor repository_control resolution must return selected_index=null.")
            if not selected_path or not selected_flag:
                raise CursorPromptError("Cursor repository_control resolution requires selected_path and selected_flag.")
            if candidates_relevant and candidate_payload:
                raise CursorPromptError("Cursor repository_control resolution cannot mark unrelated supplied candidates as relevant.")
            answer = answer or f"Use {selected_flag} in {selected_path}."
        else:
            selected_index = None
            selected_path = ""
            selected_flag = ""
            selected_current_value = None
            selected_new_value = None
            answer = ""

        if resolution_type != "unresolved":
            if not isinstance(selected_current_value, bool) or not isinstance(selected_new_value, bool):
                raise CursorPromptError(
                    "Cursor clarification must return Boolean selected_current_value and selected_new_value for a resolved repository control."
                )
            if selected_current_value == selected_new_value:
                raise CursorPromptError("Cursor clarification selected_current_value and selected_new_value must differ.")
        if resolution_type != "unresolved" and not answer:
            raise CursorPromptError("Cursor clarification did not return a usable answer.")
        result = {
            "answer": answer,
            "resolution_type": resolution_type,
            "candidates_relevant": candidates_relevant,
            "use_structured_picker": use_structured_picker,
            "selected_index": selected_index,
            "selected_path": selected_path,
            "selected_flag": selected_flag,
            "selected_current_value": selected_current_value,
            "selected_new_value": selected_new_value,
            "reason": re.sub(r"\s+", " ", str(parsed.get("reason") or "")).strip()[:1200],
            "evidence": [
                re.sub(r"\s+", " ", str(item or "")).strip()[:500]
                for item in (parsed.get("evidence") or [])[:4]
                if str(item or "").strip()
            ],
            "agent_id": agent_id,
            "run_id": cursor_run_id,
        }
        _emit(
            "cursor_clarification_completed",
            log_event=log_event,
            run_id=run_id,
            test_case_id=case_id,
            selected_path=selected_path,
            selected_flag=selected_flag,
            selected_current_value=selected_current_value,
            selected_new_value=selected_new_value,
            selected_index=selected_index,
            resolution_type=resolution_type,
            candidates_relevant=candidates_relevant,
            use_structured_picker=use_structured_picker,
        )
        return result
    except Exception as exc:
        _emit(
            "cursor_clarification_failed",
            level="warning",
            log_event=log_event,
            run_id=run_id,
            test_case_id=case_id,
            error=exc,
        )
        return {}
