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
import threading
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
_REPO_QUESTION_SCHEMA_VERSION = "terrabot.cursor.repository-questions.v1"
_REPO_ANSWER_SCHEMA_VERSION = "terrabot.cursor.repository-answer-validation.v1"

# One Cursor prompt-author run already inspected a pinned repository and bound
# each generated natural-language prompt to the immutable repository-derived
# test target. Keep that provenance in-process so a later Terrabot clarification
# can be answered without launching another expensive repository agent. The
# backend still performs the authoritative current-live-file verification before
# accepting the path/flag/value transition.
_PROMPT_AUTHOR_BINDINGS: dict[tuple[str, str], dict[str, Any]] = {}
_PROMPT_AUTHOR_BINDINGS_LOCK = threading.RLock()
_PROMPT_AUTHOR_BINDINGS_LIMIT = 2048


class CursorPromptError(RuntimeError):
    """Raised when Cursor cannot return a valid prompt set."""


def _enabled() -> bool:
    # Automated testing is now intentionally Cursor-additive by default. If no
    # Cursor key is configured the provider still fails open through the
    # existing fallback path, so normal backend-derived tests remain usable.
    value = os.getenv("TERRABOT_CURSOR_PROMPT_GENERATION_ENABLED", "true")
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


def _remember_prompt_author_target_binding(
    case: Any,
    *,
    run_id: str,
    phase1_prompt: str,
    phase2_prompt: str,
    cursor_agent_id: str,
    cursor_run_id: str,
) -> None:
    """Cache the exact target for prompts authored by one pinned Cursor run.

    This record is test orchestration provenance, not repository authority. It is
    accepted downstream only after Terrabot re-reads the exact current live file
    and verifies that the literal assignment/value still exists exactly once.
    """
    case_id = str(_case_value(case, "case_id") or "").strip()
    run_key = str(run_id or "").strip()
    path_value = str(_case_value(case, "path") or "").strip().strip("/")
    flag = str(_case_value(case, "flag") or "").strip()
    current_value = _case_value(case, "current_value")
    desired_value = _case_value(case, "desired_value")
    if (
        not run_key
        or not case_id
        or not path_value
        or not flag
        or not isinstance(current_value, bool)
        or not isinstance(desired_value, bool)
        or current_value == desired_value
    ):
        return

    binding = {
        "run_id": run_key,
        "case_id": case_id,
        "repository": f"{_case_value(case, 'owner')}/{_case_value(case, 'repo')}",
        "commit_sha": str(_case_value(case, "commit_sha") or "").strip(),
        "path": path_value,
        "flag": flag,
        "current_value": current_value,
        "new_value": desired_value,
        "environment": str(_case_value(case, "environment") or "").strip(),
        "alias": str(_case_value(case, "alias") or "").strip(),
        "phase1_prompt": re.sub(r"\s+", " ", str(phase1_prompt or "")).strip(),
        "phase2_prompt": re.sub(r"\s+", " ", str(phase2_prompt or "")).strip(),
        "evidence": [str(_case_value(case, "evidence_line") or "").strip()],
        "cursor_agent_id": str(cursor_agent_id or "").strip(),
        "cursor_run_id": str(cursor_run_id or "").strip(),
        "provenance": "cursor_prompt_author_target_binding",
    }
    with _PROMPT_AUTHOR_BINDINGS_LOCK:
        _PROMPT_AUTHOR_BINDINGS[(run_key, case_id)] = binding
        while len(_PROMPT_AUTHOR_BINDINGS) > _PROMPT_AUTHOR_BINDINGS_LIMIT:
            _PROMPT_AUTHOR_BINDINGS.pop(next(iter(_PROMPT_AUTHOR_BINDINGS)), None)


def get_prompt_author_target_binding(
    *,
    run_id: str,
    case: Any,
    prompt: str = "",
) -> dict[str, Any]:
    """Return Cursor's cached prompt-to-target binding for one test turn.

    The requested prompt must be one of the two prompts produced by that exact
    Cursor run. Returning an empty dict preserves the existing repository-agent
    clarification fallback when prompt generation failed open or used a legacy
    provider response.
    """
    key = (str(run_id or "").strip(), str(_case_value(case, "case_id") or "").strip())
    with _PROMPT_AUTHOR_BINDINGS_LOCK:
        binding = dict(_PROMPT_AUTHOR_BINDINGS.get(key) or {})
    if not binding:
        return {}
    normalized_prompt = re.sub(r"\s+", " ", str(prompt or "")).strip().casefold()
    authored = {
        str(binding.get("phase1_prompt") or "").casefold(),
        str(binding.get("phase2_prompt") or "").casefold(),
    }
    if normalized_prompt and normalized_prompt not in authored:
        return {}
    if (
        str(binding.get("repository") or "").lower()
        != f"{_case_value(case, 'owner')}/{_case_value(case, 'repo')}".lower()
        or str(binding.get("commit_sha") or "") != str(_case_value(case, "commit_sha") or "")
        or str(binding.get("path") or "").strip("/") != str(_case_value(case, "path") or "").strip("/")
        or str(binding.get("flag") or "") != str(_case_value(case, "flag") or "")
    ):
        return {}
    return binding


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
            "7. Vary infrastructure language across cases so Terrabot is exercised like a real infra team: creation/provisioning, enablement, disablement/decommissioning/deletion wording, and targeted modification/update wording. Keep each prompt consistent with the immutable desired transition and repository semantics; do not ask for destructive deletion when the immutable test is only a reversible Boolean toggle unless repository evidence shows that users naturally describe that toggle as decommissioning/removal.",
            "8. Prefer developer-style descriptions of the resource behavior over Terraform identifier wording. Use repository vocabulary and nearby module/resource semantics, not a direct humanization of the flag name.",
            "9. Return JSON only. Do not wrap it in Markdown and do not add commentary.",
            "",
            *_json_contract_lines(_SCHEMA_VERSION),
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


# Cursor Cloud Agents (especially in "plan" mode on large repositories) often
# wrap their final answer in prose, summaries, or partial markdown, which made
# the old "first { .. last }" extraction fail ~5/6 of the time. Every Terrabot
# instruction now asks Cursor to print the JSON between these unique sentinel
# markers, and the parser prefers marker extraction, then fenced blocks, then
# a balanced-brace scan that picks the JSON object containing schema_version.
_JSON_BEGIN_MARKER = "BEGIN_TERRABOT_JSON"
_JSON_END_MARKER = "END_TERRABOT_JSON"


def _json_contract_lines(schema_version: str) -> list[str]:
    """Shared final-response contract appended to every Cursor instruction."""
    return [
        "FINAL RESPONSE CONTRACT (MANDATORY):",
        f"1. Print the line {_JSON_BEGIN_MARKER} on its own line.",
        "2. On the next line print exactly one raw JSON object (no markdown fences, no comments).",
        f"3. Print the line {_JSON_END_MARKER} on its own line.",
        f"4. schema_version inside the JSON must be exactly {schema_version}.",
        "5. Any analysis or notes must appear BEFORE the begin marker, never between or after the markers.",
        "6. Never finish without the two marker lines and the JSON object between them.",
    ]


def _scan_balanced_json_objects(text: str) -> list[dict[str, Any]]:
    """Return every parseable top-level JSON object found in free text."""
    objects: list[dict[str, Any]] = []
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    candidate = text[start : index + 1]
                    try:
                        value = json.loads(candidate)
                    except json.JSONDecodeError:
                        value = None
                    if isinstance(value, dict):
                        objects.append(value)
                    start = -1
    return objects


def _parse_result_text(result_text: str) -> dict[str, Any]:
    text = str(result_text or "").strip()

    # 1) Sentinel markers — the strongest signal, immune to surrounding prose.
    if _JSON_BEGIN_MARKER in text and _JSON_END_MARKER in text:
        begin = text.find(_JSON_BEGIN_MARKER) + len(_JSON_BEGIN_MARKER)
        end = text.find(_JSON_END_MARKER, begin)
        if end > begin:
            marked = text[begin:end].strip()
            if marked.startswith("```"):
                marked = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", marked)
                marked = re.sub(r"\s*```$", "", marked).strip()
            try:
                data = json.loads(marked)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                pass  # fall through to the other strategies

    # 2) A fenced ```json block anywhere in the text.
    for fence in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL):
        try:
            data = json.loads(fence.group(1))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue

    # 3) The whole text (optionally after stripping one outer fence).
    stripped = text
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        data = json.loads(stripped)
        if isinstance(data, dict):
            return data
        raise CursorPromptError("Cursor result must be a JSON object.")
    except json.JSONDecodeError:
        pass

    # 4) Balanced-brace scan across the prose: prefer an object that carries
    # schema_version (the Terrabot payload) over incidental JSON snippets that
    # Cursor may quote while explaining its analysis.
    candidates = _scan_balanced_json_objects(stripped)
    schema_candidates = [item for item in candidates if "schema_version" in item]
    if schema_candidates:
        return schema_candidates[-1]
    if candidates:
        return candidates[-1]

    # Surface what Cursor actually returned. Previously this raised with no
    # visibility into the raw text, so a Cursor agent that answered in prose
    # (common in "plan" mode on large repositories) was indistinguishable from
    # a genuine API/timeout failure in the logs.
    preview = re.sub(r"\s+", " ", text)[:800]
    LOGGER.warning(
        "[TerrabotCursor] event=cursor_result_not_json level=warning "
        "result_preview=%s",
        preview,
    )
    raise CursorPromptError(
        "Cursor result did not contain a JSON object. "
        f"result_preview={preview!r}"
    )


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
            generated_case = replace(case, phase1_prompt=phase1, phase2_prompt=phase2)
            generated.append(generated_case)
            _remember_prompt_author_target_binding(
                generated_case,
                run_id=run_id,
                phase1_prompt=phase1,
                phase2_prompt=phase2,
                cursor_agent_id=agent_id,
                cursor_run_id=cursor_run_id,
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


def _repair_clarification_protocol(
    *,
    session: Any,
    base_url: str,
    headers: dict[str, str],
    request_timeout: float,
    poll_interval: float,
    invalid_result: str,
    validation_error: str,
    run_id: str,
    case_id: str,
    log_event: Callable[..., None] | None,
) -> dict[str, Any]:
    """Reformat a completed Cursor clarification without re-reading a repo.

    Cursor's v1 API supports no-repository agents.  This repair is deliberately
    protocol-only: it may preserve a semantic choice already present in the
    first result, but it must not derive a new path/flag or turn unresolved into
    resolved.  Avoiding a second repository checkout keeps clarification repair
    bounded and prevents the long protocol-repair stalls seen in E2E runs.
    """
    try:
        run_timeout = _float_setting(
            "TERRABOT_CURSOR_CLARIFICATION_PROTOCOL_REPAIR_TIMEOUT_SECONDS",
            45.0,
            15.0,
            120.0,
        )
        prior = str(invalid_result or "")[:12000]
        instruction = "\n".join([
            "Repair ONLY the response format of a completed Terrabot Cursor clarification.",
            "Do not inspect a repository, edit files, commit, push, create branches, or open PRs.",
            "Do not change the semantic meaning of the prior result and do not invent a path, flag, value, or evidence.",
            f"The previous response failed validation with: {validation_error}",
            f"schema_version must be exactly {_CLARIFICATION_SCHEMA_VERSION}.",
            "Required keys: schema_version, answer, resolution_type, candidates_relevant, selected_index, selected_path, selected_flag, selected_current_value, selected_new_value, reason, evidence.",
            "If the prior result did not actually identify a unique repository control, preserve that meaning by returning resolution_type=unresolved, selected_index=null, selected_path=\"\", selected_flag=\"\", selected_current_value=null, selected_new_value=null, answer=\"\", evidence=[].",
            "Prior Cursor result:",
            prior,
            *_json_contract_lines(_CLARIFICATION_SCHEMA_VERSION),
        ])
        payload = {
            "name": f"Terrabot clarification protocol repair {run_id} {case_id}"[:100],
            "mode": "plan",
            "prompt": {"text": instruction},
            "workOnCurrentBranch": False,
            "autoCreatePR": False,
            "skipReviewerRequest": True,
        }
        _emit(
            "cursor_clarification_protocol_repair_started",
            log_event=log_event,
            run_id=run_id,
            test_case_id=case_id,
            prompt_chars=len(instruction),
            validation_error=validation_error,
        )
        created = _http_json(
            session,
            "POST",
            f"{base_url}/v1/agents",
            headers=headers,
            timeout=request_timeout,
            payload=payload,
        )
        agent_id, cursor_run_id, initial_run = _extract_agent_and_run(created)
        try:
            cursor_run_id = _resolve_run_id(
                session,
                agent_id,
                cursor_run_id,
                base_url=base_url,
                headers=headers,
                timeout=request_timeout,
            )
            repaired_text, _terminal = _wait_for_result(
                session,
                agent_id,
                cursor_run_id,
                initial_run,
                base_url=base_url,
                headers=headers,
                request_timeout=request_timeout,
                run_timeout=run_timeout,
                poll_interval=poll_interval,
                run_label=f"{run_id}:{case_id}:clarification-repair",
                log_event=log_event,
            )
            parsed = _parse_result_text(repaired_text)
            if str(parsed.get("schema_version") or "").strip() != _CLARIFICATION_SCHEMA_VERSION:
                raise CursorPromptError(
                    f"Cursor clarification repair schema_version must be {_CLARIFICATION_SCHEMA_VERSION}."
                )
            _emit(
                "cursor_clarification_protocol_repair_completed",
                log_event=log_event,
                run_id=run_id,
                test_case_id=case_id,
                cursor_agent_id=agent_id,
                cursor_run_id=cursor_run_id,
            )
            return parsed
        finally:
            _archive_agent_best_effort(
                session,
                agent_id,
                base_url=base_url,
                headers=headers,
                timeout=request_timeout,
                run_label=f"{run_id}:{case_id}:clarification-repair",
                log_event=log_event,
            )
    except Exception as exc:
        _emit(
            "cursor_clarification_protocol_repair_failed",
            level="warning",
            log_event=log_event,
            run_id=run_id,
            test_case_id=case_id,
            error=exc,
        )
        return {}


def resolve_repository_clarification(
    *,
    owner: str,
    repo: str,
    commit_sha: str,
    original_prompt: str,
    clarification_text: str,
    candidates: Sequence[dict[str, Any]] | None = None,
    expected_target_hint: dict[str, Any] | None = None,
    prompt_author_target_binding: dict[str, Any] | None = None,
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
    binding = (
        dict(prompt_author_target_binding or {})
        if isinstance(prompt_author_target_binding, dict)
        else {}
    )
    if binding:
        selected_path = str(binding.get("path") or "").strip().strip("/")
        selected_flag = str(binding.get("flag") or "").strip()
        selected_current_value = binding.get("current_value")
        selected_new_value = binding.get("new_value")
        binding_repository = str(binding.get("repository") or "").strip().lower()
        binding_commit = str(binding.get("commit_sha") or "").strip()
        prompt_value = re.sub(r"\s+", " ", str(original_prompt or "")).strip().casefold()
        authored_prompts = {
            str(binding.get("phase1_prompt") or "").casefold(),
            str(binding.get("phase2_prompt") or "").casefold(),
        }
        binding_valid = bool(
            selected_path
            and selected_flag
            and isinstance(selected_current_value, bool)
            and isinstance(selected_new_value, bool)
            and selected_current_value != selected_new_value
            and binding_repository == f"{owner}/{repo}".lower()
            and binding_commit == str(commit_sha or "").strip()
            and (not prompt_value or prompt_value in authored_prompts)
        )
        if binding_valid:
            candidate_payload = [dict(item) for item in (candidates or []) if isinstance(item, dict)]
            selected_index = None
            for index, candidate in enumerate(candidate_payload, start=1):
                candidate_path = str(candidate.get("path") or "").strip().strip("/")
                candidate_flag = str(candidate.get("flag") or "").strip()
                feature_match = candidate.get("feature_flag_match")
                if isinstance(feature_match, dict):
                    candidate_flag = candidate_flag or str(feature_match.get("flag") or "").strip()
                if candidate_path == selected_path and candidate_flag == selected_flag:
                    selected_index = index
                    break
            resolution_type = "candidate" if selected_index is not None else "repository_control"
            answer = str(selected_index) if selected_index is not None else f"Use {selected_flag} in {selected_path}."
            evidence = [
                re.sub(r"\s+", " ", str(value or "")).strip()[:500]
                for value in (binding.get("evidence") or [])[:4]
                if str(value or "").strip()
            ]
            _emit(
                "cursor_clarification_prompt_author_binding_used",
                log_event=log_event,
                run_id=run_id,
                test_case_id=case_id,
                repo=f"{owner}/{repo}",
                selected_path=selected_path,
                selected_flag=selected_flag,
                resolution_type=resolution_type,
                note="backend current-live-file verification remains mandatory",
            )
            return {
                "attempted": True,
                "resolved": True,
                "error": "",
                "answer": answer,
                "resolution_type": resolution_type,
                "candidates_relevant": selected_index is not None,
                "use_structured_picker": selected_index is not None,
                "selected_index": selected_index,
                "selected_path": selected_path,
                "selected_flag": selected_flag,
                "selected_current_value": selected_current_value,
                "selected_new_value": selected_new_value,
                "reason": (
                    "Cursor authored this exact test prompt for the pinned repository target; "
                    "Terrabot must independently verify the current live assignment before generation."
                ),
                "evidence": evidence,
                "agent_id": str(binding.get("cursor_agent_id") or ""),
                "run_id": str(binding.get("cursor_run_id") or ""),
                "api_call": False,
                "verification_provenance": "cursor_prompt_author_target_binding",
            }
        _emit(
            "cursor_clarification_prompt_author_binding_rejected",
            level="warning",
            log_event=log_event,
            run_id=run_id,
            test_case_id=case_id,
            repo=f"{owner}/{repo}",
            reason="binding identity or Boolean transition did not match the current test turn",
        )

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
        return {
            "attempted": True,
            "resolved": False,
            "resolution_type": "unresolved",
            "answer": "",
            "error": "TERRABOT_CURSOR_API_KEY/CURSOR_API_KEY is not configured",
        }
    session = session or requests.Session()
    base_url = _base_url()
    request_timeout = _float_setting("TERRABOT_CURSOR_REQUEST_TIMEOUT_SECONDS", 30.0, 5.0, 120.0)
    run_timeout = _float_setting(
        "TERRABOT_CURSOR_CLARIFICATION_RUN_TIMEOUT_SECONDS",
        _float_setting("TERRABOT_CURSOR_RUN_TIMEOUT_SECONDS", 180.0, 15.0, 1800.0),
        15.0,
        600.0,
    )
    poll_interval = _float_setting("TERRABOT_CURSOR_POLL_INTERVAL_SECONDS", 2.0, 0.2, 30.0)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    candidate_payload = [dict(item) for item in (candidates or []) if isinstance(item, dict)]
    oracle_hint = dict(expected_target_hint or {}) if isinstance(expected_target_hint, dict) else {}
    instruction = "\n".join([
        "You are resolving one Terrabot infrastructure clarification using only the pinned repository.",
        "This is a read-only repository-analysis task. Do not edit, commit, push, create branches, or open PRs.",
        f"Repository: https://github.com/{owner}/{repo}",
        f"Exact commit: {commit_sha}",
        f"Original user request: {original_prompt}",
        f"Terrabot clarification: {clarification_text}",
        "Terrabot structured candidates:",
        json.dumps(candidate_payload, ensure_ascii=False, indent=2),
        "Automated-test oracle hint (test-only; NOT backend authority):",
        json.dumps(oracle_hint, ensure_ascii=False, indent=2),
        "When an automated-test oracle hint is supplied, treat it only as the target that the test author intended when creating this prompt. Independently verify its exact path/flag/current value against the pinned repository before returning it. If live repository evidence disproves it, reject the hint and resolve from repository evidence instead. Never blindly echo the hint.",
        "FAST TEST-ORACLE MODE: when the oracle hint contains a path+flag, inspect that exact file first and verify the literal assignment immediately. Do not perform a broad repository scan unless the hinted live file disproves the test oracle. This clarification should normally finish after one targeted repository read.",
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
        json.dumps({
            "schema_version": _CLARIFICATION_SCHEMA_VERSION,
            "answer": "1 or Use <flag> in <path>.",
            "resolution_type": "candidate | repository_control | unresolved",
            "candidates_relevant": True,
            "selected_index": 1,
            "selected_path": "repo/relative/path.tf",
            "selected_flag": "enable_example",
            "selected_current_value": True,
            "selected_new_value": False,
            "reason": "short reason",
            "evidence": ["path: proof"],
        }, ensure_ascii=False),
        *_json_contract_lines(_CLARIFICATION_SCHEMA_VERSION),
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
        max_attempts = _int_setting("TERRABOT_CURSOR_CLARIFICATION_MAX_ATTEMPTS", 2, 1, 3)
        parsed: dict[str, Any] = {}
        last_error: CursorPromptError | None = None
        agent_id = ""
        cursor_run_id = ""
        for attempt in range(1, max_attempts + 1):
            attempt_instruction = instruction
            if attempt > 1 and last_error is not None:
                attempt_instruction = "\n".join([
                    instruction,
                    "",
                    "RETRY NOTICE: your previous response for this exact task failed "
                    f"format validation with: {str(last_error)[:600]}",
                    "You may reuse your previous repository analysis; the ONLY change "
                    "required is emitting the response in the mandated marker+JSON format.",
                ])
            create_payload["prompt"] = {"text": attempt_instruction}
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
            try:
                parsed = _parse_result_text(result_text)
                schema_version = str(parsed.get("schema_version") or "").strip()
                if schema_version != _CLARIFICATION_SCHEMA_VERSION:
                    raise CursorPromptError(
                        f"Cursor clarification schema_version must be {_CLARIFICATION_SCHEMA_VERSION}."
                    )
                last_error = None
                break
            except CursorPromptError as protocol_error:
                # First try the cheap no-repository protocol repair on this
                # attempt's raw text before burning a full repository re-read.
                repaired = _repair_clarification_protocol(
                    session=session,
                    base_url=base_url,
                    headers=headers,
                    request_timeout=request_timeout,
                    poll_interval=poll_interval,
                    invalid_result=result_text,
                    validation_error=str(protocol_error),
                    run_id=run_id,
                    case_id=case_id,
                    log_event=log_event,
                )
                if repaired:
                    parsed = repaired
                    last_error = None
                    break
                last_error = protocol_error
                _emit(
                    "cursor_clarification_format_retry",
                    level="warning",
                    log_event=log_event,
                    run_id=run_id,
                    test_case_id=case_id,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    error=protocol_error,
                )
        if last_error is not None or not parsed:
            raise last_error or CursorPromptError(
                "Cursor clarification produced no parseable result."
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
            "attempted": True,
            "resolved": resolution_type in {"candidate", "repository_control"},
            "error": "",
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
        return {
            "attempted": True,
            "resolved": False,
            "resolution_type": "unresolved",
            "answer": "",
            "error": re.sub(r"\s+", " ", str(exc)).strip()[:1600],
        }


def generate_repository_questions(
    *,
    owner: str,
    repo: str,
    commit_sha: str,
    run_id: str,
    count: int = 1,
    session: Any | None = None,
    log_event: Callable[..., None] | None = None,
) -> list[dict[str, Any]]:
    """Ask Cursor to design repository/workflow questions from live code.

    This is deliberately separate from infrastructure mutation cases. Cursor
    inspects the pinned repository and creates questions that a developer could
    naturally ask the infra team about repository behavior, placement, modules,
    environments, validation, or workflow conventions. Terrabot's answer is
    later independently checked by Cursor against the same pinned repository.
    """
    count = max(1, min(int(count or 1), 4))
    api_key = _api_key()
    if not api_key:
        _emit(
            "cursor_repository_question_generation_skipped",
            level="warning",
            log_event=log_event,
            run_id=run_id,
            repo=f"{owner}/{repo}",
            reason="TERRABOT_CURSOR_API_KEY/CURSOR_API_KEY is not configured",
        )
        return []
    http = session or requests.Session()
    base_url = _base_url()
    request_timeout = _float_setting("TERRABOT_CURSOR_REQUEST_TIMEOUT_SECONDS", 30.0, 5.0, 120.0)
    run_timeout = _float_setting("TERRABOT_CURSOR_REPOSITORY_QUESTION_TIMEOUT_SECONDS", 180.0, 30.0, 600.0)
    poll_interval = _float_setting("TERRABOT_CURSOR_POLL_INTERVAL_SECONDS", 2.0, 0.2, 30.0)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    instruction = "\n".join([
        "Design realistic read-only Terrabot repository/workflow questions for developers.",
        f"Repository: https://github.com/{owner}/{repo}",
        f"Exact commit: {commit_sha}",
        f"Generate exactly {count} question(s).",
        "Inspect the repository before writing questions: Terraform files, environment folders, modules, README/module READMEs, pipeline files, .github guidance/templates, and .serena/.Serena when present.",
        "Questions must be answerable from the repository itself and should resemble simple developer language, not exam questions.",
        "Cover useful infrastructure-team doubts such as: where/how a capability is configured, which environment/value file controls it, what a module does, how creation/modification flows are structured, what validations/pipelines apply, or how repository conventions work.",
        "Do not ask for secrets, credentials, external production state, or facts that cannot be proven from the pinned repository.",
        "For every question provide a concise expected_answer and 1-5 exact evidence_paths that support it. Do not invent paths.",
        "Return raw JSON only.",
        json.dumps({
            "schema_version": _REPO_QUESTION_SCHEMA_VERSION,
            "repository_commit_sha": commit_sha,
            "questions": [{
                "question_id": "q1",
                "question": "plain-language developer question",
                "expected_answer": "concise repository-grounded answer",
                "evidence_paths": ["repo/relative/path.tf"],
            }],
        }, ensure_ascii=False),
        *_json_contract_lines(_REPO_QUESTION_SCHEMA_VERSION),
    ])
    repos = [{"url": f"https://github.com/{owner}/{repo}", "startingRef": commit_sha}]
    remote_before = cursor_readonly_guard.snapshot_remote_branches(repos)
    payload = {
        "name": f"Terrabot repository questions {run_id} {repo}"[:100],
        "mode": "plan",
        "prompt": {"text": instruction},
        "repos": repos,
        "workOnCurrentBranch": False,
        "autoCreatePR": False,
        "skipReviewerRequest": True,
    }
    _emit(
        "cursor_repository_question_generation_started",
        log_event=log_event,
        run_id=run_id,
        repo=f"{owner}/{repo}",
        count=count,
        prompt_chars=len(instruction),
    )
    created = _http_json(http, "POST", f"{base_url}/v1/agents", headers=headers, timeout=request_timeout, payload=payload)
    agent_id, cursor_run_id, initial_run = _extract_agent_and_run(created)
    try:
        cursor_run_id = _resolve_run_id(http, agent_id, cursor_run_id, base_url=base_url, headers=headers, timeout=request_timeout)
        result_text, terminal = _wait_for_result(
            http, agent_id, cursor_run_id, initial_run,
            base_url=base_url, headers=headers, request_timeout=request_timeout,
            run_timeout=run_timeout, poll_interval=poll_interval,
            run_label=f"{run_id}:repository-questions", log_event=log_event,
        )
        remote_after = cursor_readonly_guard.snapshot_remote_branches(repos)
        mutations = cursor_readonly_guard.cursor_reported_remote_mutations(terminal, remote_before, remote_after)
        if mutations:
            raise CursorPromptError("Cursor changed a verified remote GitHub branch while generating repository questions.")
        parsed = _parse_result_text(result_text)
        if str(parsed.get("schema_version") or "").strip() != _REPO_QUESTION_SCHEMA_VERSION:
            raise CursorPromptError(f"Cursor repository-question schema_version must be {_REPO_QUESTION_SCHEMA_VERSION}.")
        if str(parsed.get("repository_commit_sha") or "").strip() != commit_sha:
            raise CursorPromptError("Cursor repository-question commit did not match the pinned commit.")
        questions: list[dict[str, Any]] = []
        for index, item in enumerate(parsed.get("questions") or [], start=1):
            if not isinstance(item, dict):
                continue
            question = re.sub(r"\s+", " ", str(item.get("question") or "")).strip()
            expected = re.sub(r"\s+", " ", str(item.get("expected_answer") or "")).strip()
            paths = [str(value).strip().strip("/") for value in (item.get("evidence_paths") or []) if str(value).strip()]
            if question and expected and paths:
                questions.append({
                    "question_id": str(item.get("question_id") or f"q{index}"),
                    "question": question,
                    "expected_answer": expected,
                    "evidence_paths": paths[:5],
                    "owner": owner,
                    "repo": repo,
                    "commit_sha": commit_sha,
                })
            if len(questions) >= count:
                break
        _emit(
            "cursor_repository_question_generation_completed",
            log_event=log_event,
            run_id=run_id,
            repo=f"{owner}/{repo}",
            generated=len(questions),
        )
        return questions
    except Exception as exc:
        _emit(
            "cursor_repository_question_generation_failed",
            level="warning",
            log_event=log_event,
            run_id=run_id,
            repo=f"{owner}/{repo}",
            error=exc,
        )
        return []
    finally:
        _archive_agent_best_effort(
            http, agent_id, base_url=base_url, headers=headers,
            timeout=request_timeout, run_label=f"{run_id}:repository-questions",
            log_event=log_event,
        )


def validate_repository_answer(
    *,
    owner: str,
    repo: str,
    commit_sha: str,
    question: str,
    terrabot_answer: str,
    expected_answer: str,
    evidence_paths: Sequence[str],
    run_id: str,
    question_id: str,
    session: Any | None = None,
    log_event: Callable[..., None] | None = None,
) -> dict[str, Any]:
    """Independently validate a Terrabot repository-Q&A answer with Cursor."""
    api_key = _api_key()
    if not api_key:
        return {"completed": False, "correct": False, "error": "Cursor API key is not configured."}
    http = session or requests.Session()
    base_url = _base_url()
    request_timeout = _float_setting("TERRABOT_CURSOR_REQUEST_TIMEOUT_SECONDS", 30.0, 5.0, 120.0)
    run_timeout = _float_setting("TERRABOT_CURSOR_REPOSITORY_ANSWER_TIMEOUT_SECONDS", 180.0, 30.0, 600.0)
    poll_interval = _float_setting("TERRABOT_CURSOR_POLL_INTERVAL_SECONDS", 2.0, 0.2, 30.0)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    instruction = "\n".join([
        "Validate one Terrabot repository/workflow answer against the pinned repository.",
        "This is read-only. Do not edit, commit, push, branch, or open PRs.",
        f"Repository: https://github.com/{owner}/{repo}",
        f"Exact commit: {commit_sha}",
        f"Question: {question}",
        f"Terrabot answer: {terrabot_answer}",
        f"Cursor-authored expected answer: {expected_answer}",
        "Expected supporting evidence paths:",
        json.dumps(list(evidence_paths), ensure_ascii=False),
        "Inspect the repository yourself. Mark correct=true only if the Terrabot answer is materially correct and repository-grounded. It need not use identical wording to expected_answer.",
        "Return raw JSON only with schema_version, correct, reason, evidence.",
        json.dumps({"schema_version": _REPO_ANSWER_SCHEMA_VERSION, "correct": True, "reason": "short reason", "evidence": ["path: proof"]}, ensure_ascii=False),
        *_json_contract_lines(_REPO_ANSWER_SCHEMA_VERSION),
    ])
    repos = [{"url": f"https://github.com/{owner}/{repo}", "startingRef": commit_sha}]
    remote_before = cursor_readonly_guard.snapshot_remote_branches(repos)
    payload = {
        "name": f"Terrabot repository answer validation {run_id} {question_id}"[:100],
        "mode": "plan",
        "prompt": {"text": instruction},
        "repos": repos,
        "workOnCurrentBranch": False,
        "autoCreatePR": False,
        "skipReviewerRequest": True,
    }
    _emit("cursor_repository_answer_validation_started", log_event=log_event, run_id=run_id, question_id=question_id, repo=f"{owner}/{repo}")
    try:
        created = _http_json(http, "POST", f"{base_url}/v1/agents", headers=headers, timeout=request_timeout, payload=payload)
        agent_id, cursor_run_id, initial_run = _extract_agent_and_run(created)
        try:
            cursor_run_id = _resolve_run_id(http, agent_id, cursor_run_id, base_url=base_url, headers=headers, timeout=request_timeout)
            result_text, terminal = _wait_for_result(
                http, agent_id, cursor_run_id, initial_run,
                base_url=base_url, headers=headers, request_timeout=request_timeout,
                run_timeout=run_timeout, poll_interval=poll_interval,
                run_label=f"{run_id}:{question_id}:repository-answer", log_event=log_event,
            )
            remote_after = cursor_readonly_guard.snapshot_remote_branches(repos)
            mutations = cursor_readonly_guard.cursor_reported_remote_mutations(terminal, remote_before, remote_after)
            if mutations:
                raise CursorPromptError("Cursor changed a verified remote GitHub branch during repository answer validation.")
            parsed = _parse_result_text(result_text)
            if str(parsed.get("schema_version") or "").strip() != _REPO_ANSWER_SCHEMA_VERSION:
                raise CursorPromptError(f"Cursor repository-answer schema_version must be {_REPO_ANSWER_SCHEMA_VERSION}.")
            correct = parsed.get("correct")
            if not isinstance(correct, bool):
                raise CursorPromptError("Cursor repository-answer correct must be Boolean.")
            result = {
                "completed": True,
                "correct": correct,
                "reason": re.sub(r"\s+", " ", str(parsed.get("reason") or "")).strip()[:1200],
                "evidence": [re.sub(r"\s+", " ", str(value)).strip()[:500] for value in (parsed.get("evidence") or [])[:6]],
                "error": "",
            }
            _emit("cursor_repository_answer_validation_completed", log_event=log_event, run_id=run_id, question_id=question_id, correct=correct)
            return result
        finally:
            _archive_agent_best_effort(http, agent_id, base_url=base_url, headers=headers, timeout=request_timeout, run_label=f"{run_id}:{question_id}:repository-answer", log_event=log_event)
    except Exception as exc:
        _emit("cursor_repository_answer_validation_failed", level="warning", log_event=log_event, run_id=run_id, question_id=question_id, error=exc)
        return {"completed": False, "correct": False, "reason": "", "evidence": [], "error": str(exc)[:1600]}

