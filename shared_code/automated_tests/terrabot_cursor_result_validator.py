"""Independent Cursor review for completed Terrabot automated test runs.

Terrabot's deterministic validators remain the pre-push authority.  This module
adds one read-only Cursor Cloud Agent review after every backend case has
finished.  Cursor receives the exact repository commits, isolated test-branch
names, generated-file excerpts, and repository-context search evidence.  It
returns a per-case JSON verdict that is included in the Teams result table.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Mapping, Sequence

import requests

LOGGER = logging.getLogger("terrabot.automated_tests.cursor_validation")
LOGGER.setLevel(logging.INFO)

_SCHEMA_VERSION = "terrabot.cursor.validation.v1"
_TERMINAL_STATUSES = {"FINISHED", "ERROR", "CANCELLED", "EXPIRED"}
_TRUE_VALUES = {"1", "true", "yes", "on"}


def _diag(event: str, level: str = "info", **fields: Any) -> None:
    parts = [f"event={event}", f"level={level}"]
    for key, value in fields.items():
        text = re.sub(r"\s+", " ", str(value if value is not None else "")).strip()
        if len(text) > 400:
            text = text[:397] + "..."
        parts.append(f"{key}={text}")
    message = "[TerrabotCursorValidation] " + " ".join(parts)
    if level in {"warning", "error"}:
        LOGGER.warning(message)
    else:
        LOGGER.info(message)
    try:
        print(message, flush=True)
    except Exception:
        pass


def cursor_result_validation_enabled() -> bool:
    return os.getenv(
        "TERRABOT_TEST_CURSOR_RESULT_VALIDATION_ENABLED",
        os.getenv("TERRABOT_TEST_CURSOR_VALIDATION_ENABLED", "false"),
    ).strip().lower() in _TRUE_VALUES


def _api_key() -> str:
    return str(
        os.getenv("TERRABOT_CURSOR_API_KEY")
        or os.getenv("CURSOR_API_KEY")
        or ""
    ).strip()


def _api_base_url() -> str:
    return str(
        os.getenv("TERRABOT_CURSOR_API_BASE_URL")
        or "https://api.cursor.com"
    ).strip().rstrip("/")


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = str(os.getenv(name) or default).strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = str(os.getenv(name) or default).strip()
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _extract_json(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL | re.IGNORECASE)
    candidate = fenced.group(1) if fenced else ""
    if not candidate:
        first = raw.find("{")
        last = raw.rfind("}")
        candidate = raw[first : last + 1] if first >= 0 and last > first else ""
    if not candidate:
        return {}
    try:
        value = json.loads(candidate)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def _as_bool(value: Any, *, field: str, allow_none: bool = False) -> bool | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool):
        return value
    raise ValueError(f"Cursor validation field {field!r} must be Boolean{', null' if allow_none else ''}.")


def _normalise_case_results(
    payload: Mapping[str, Any],
    *,
    run_id: str,
    expected_case_ids: Sequence[str],
    case_types: Mapping[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    if str(payload.get("schema_version") or "").strip() != _SCHEMA_VERSION:
        raise ValueError(f"Cursor validation returned an unsupported schema_version; expected {_SCHEMA_VERSION}.")
    returned_run_id = str(payload.get("run_id") or "").strip()
    if returned_run_id and returned_run_id != run_id:
        raise ValueError(f"Cursor validation run_id mismatch: expected {run_id}, received {returned_run_id}.")

    expected = {str(value) for value in expected_case_ids}
    result: dict[str, dict[str, Any]] = {}
    for raw in payload.get("cases") or []:
        if not isinstance(raw, Mapping):
            raise ValueError("Cursor validation cases must be JSON objects.")
        case_id = str(raw.get("case_id") or "").strip()
        if not case_id or case_id not in expected:
            raise ValueError(f"Cursor validation returned an unknown or empty case_id: {case_id or '<empty>'}.")
        if case_id in result:
            raise ValueError(f"Cursor validation returned duplicate case_id {case_id}.")

        case_type = str((case_types or {}).get(case_id) or "boolean_context").strip().lower()
        if case_type not in {"boolean_context", "resource_creation"}:
            raise ValueError(f"Unsupported Terrabot case type for Cursor validation: {case_type or '<empty>'}.")

        output_correct = _as_bool(raw.get("output_correct"), field="output_correct")
        context_added = _as_bool(raw.get("context_added"), field="context_added", allow_none=True)
        context_retrievable = _as_bool(
            raw.get("context_retrievable"), field="context_retrievable", allow_none=True
        )
        context_reused = _as_bool(raw.get("context_reused"), field="context_reused", allow_none=True)
        overall_ok = _as_bool(raw.get("overall_ok"), field="overall_ok")

        if case_type == "resource_creation":
            if any(value is not None for value in (context_added, context_retrievable, context_reused)):
                raise ValueError(
                    f"Cursor validation case {case_id} must return null for context fields on resource_creation."
                )
            applicable_ok = bool(output_correct)
        else:
            if any(value is None for value in (context_added, context_retrievable, context_reused)):
                raise ValueError(
                    f"Cursor validation case {case_id} must return Boolean context fields on boolean_context."
                )
            applicable_ok = bool(
                output_correct and context_added and context_retrievable and context_reused
            )

        # Cursor may reject a case for an additional repository-level reason even
        # when all explicit assertions are true. It may never mark overall_ok true
        # while one of the required assertions is false.
        if overall_ok and not applicable_ok:
            raise ValueError(
                f"Cursor validation case {case_id} returned overall_ok=true with a failed applicable assertion."
            )

        result[case_id] = {
            "case_id": case_id,
            "output_correct": output_correct,
            "context_added": context_added,
            "context_retrievable": context_retrievable,
            "context_reused": context_reused,
            "overall_ok": overall_ok,
            "reason": re.sub(r"\s+", " ", str(raw.get("reason") or "")).strip()[:1200],
            "evidence": [
                re.sub(r"\s+", " ", str(item or "")).strip()[:500]
                for item in (raw.get("evidence") or [])[:8]
                if str(item or "").strip()
            ],
        }
    missing = sorted(expected - set(result))
    if missing:
        raise ValueError("Cursor validation omitted case(s): " + ", ".join(missing))
    return result


def _build_prompt(run_id: str, cases: Sequence[Mapping[str, Any]]) -> str:
    evidence = json.loads(json.dumps(list(cases), ensure_ascii=False, default=str))
    max_chars = _bounded_int(
        "TERRABOT_TEST_CURSOR_VALIDATION_MAX_PROMPT_CHARS", 180000, 20000, 500000
    )
    evidence_json = json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))
    original_chars = len(evidence_json)
    if original_chars > max_chars:
        # Preserve paths and hashes while bounding source excerpts. A complete
        # run should not lose Cursor validation only because one generated file
        # is large.
        for case in evidence:
            phases = (case.get("evidence") or {}) if isinstance(case, dict) else {}
            for phase in ("phase1", "phase2"):
                phase_data = phases.get(phase) or {}
                for file_item in phase_data.get("generated_files") or []:
                    if isinstance(file_item, dict):
                        file_item["excerpt"] = str(file_item.get("excerpt") or "")[:2000]
        evidence_json = json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))
    if len(evidence_json) > max_chars:
        for case in evidence:
            phases = (case.get("evidence") or {}) if isinstance(case, dict) else {}
            for phase in ("phase1", "phase2"):
                phase_data = phases.get(phase) or {}
                for file_item in phase_data.get("generated_files") or []:
                    if isinstance(file_item, dict):
                        file_item["excerpt"] = ""
        evidence_json = json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))
    if len(evidence_json) > max_chars:
        raise ValueError(
            f"Cursor validation evidence is too large ({len(evidence_json)} chars; limit {max_chars})."
        )
    if original_chars > len(evidence_json):
        _diag(
            "cursor_validation_evidence_compacted",
            run_id=run_id,
            original_chars=original_chars,
            final_chars=len(evidence_json),
            limit=max_chars,
        )
    return f"""You are the independent read-only verifier for a completed Terrabot Terraform test run.

STRICT SAFETY RULES:
- Do not edit files.
- Do not commit, push, create a branch, or create a pull request.
- You may read the checked-out repositories and fetch the explicitly listed Terrabot test branches only for inspection.
- Treat the supplied expected target and live repository as ground truth. Do not invent a different target.

For each case verify:
1. output_correct: all applicable generated output is correct. For Boolean-context cases, independently check both the Phase 1 isolated test-branch diff and the Phase 2 generated files. The exact expected flag must have the expected value in the correct repository/environment/path and unrelated content must not be changed. For resource-creation cases, check the Phase 1 generated files and branch against nearby repository patterns.
2. context_added: for Boolean-context cases, the Phase 1 repository-index record exists and semantically maps the alias/environment to the exact path and flag with repository evidence. Use null for resource-creation cases.
3. context_retrievable: for Boolean-context cases, the Phase 2 live search returned that same or an equivalent exact mapping. Use null for resource-creation cases.
4. context_reused: for Boolean-context cases, the retrieved context was attached to Foundry and Phase 2 resolved the correct target without another clarification. Use null for resource-creation cases.
5. overall_ok: true only when every applicable Cursor assertion above passes.

The backend evidence below was collected from the live GitHub repositories, the actual generated responses, the isolated test branches, and the live repository-context index. Independently inspect the repository and branch where available, then validate the evidence correlation.

Return JSON only, with no markdown and exactly this contract:
{{"schema_version":"{_SCHEMA_VERSION}","run_id":"{run_id}","cases":[{{"case_id":"...","output_correct":true,"context_added":true,"context_retrievable":true,"context_reused":true,"overall_ok":true,"reason":"short explanation","evidence":["short evidence"]}}]}}

For resource-creation cases, context_added, context_retrievable, and context_reused must be null.

RUN EVIDENCE:
{evidence_json}
"""


def validate_test_run_with_cursor(
    *,
    run_id: str,
    cases: Sequence[Mapping[str, Any]],
    http_client: Any = requests,
) -> dict[str, Any]:
    """Run one Cursor Cloud Agent review for all completed test cases.

    The function is fail-contained: callers receive a structured error and can
    still publish the deterministic backend report. No exception from Cursor is
    allowed to discard the completed Terrabot test run.
    """
    enabled = cursor_result_validation_enabled()
    base = {
        "enabled": enabled,
        "completed": False,
        "run_id": run_id,
        "agent_id": "",
        "agent_url": "",
        "duration_ms": 0,
        "case_results": {},
        "error": "",
    }
    if not enabled:
        _diag("cursor_validation_skipped", run_id=run_id, reason="disabled")
        return base
    if not cases:
        _diag("cursor_validation_skipped", run_id=run_id, reason="no_cases")
        return {**base, "completed": True}

    key = _api_key()
    if not key:
        error = "TERRABOT_CURSOR_API_KEY or CURSOR_API_KEY is not configured."
        _diag("cursor_validation_configuration_missing", level="error", run_id=run_id, error=error)
        return {**base, "error": error}

    started = time.monotonic()
    api_base = _api_base_url()
    request_timeout = _bounded_int(
        "TERRABOT_TEST_CURSOR_VALIDATION_REQUEST_TIMEOUT_SECONDS", 45, 10, 180
    )
    total_timeout = _bounded_int(
        "TERRABOT_TEST_CURSOR_VALIDATION_TIMEOUT_SECONDS", 600, 60, 1800
    )
    poll_seconds = _bounded_float(
        "TERRABOT_TEST_CURSOR_VALIDATION_POLL_SECONDS", 5.0, 1.0, 30.0
    )
    expected_case_ids = [str(item.get("case_id") or "").strip() for item in cases]
    if any(not value for value in expected_case_ids) or len(set(expected_case_ids)) != len(expected_case_ids):
        error = "Cursor validation requires unique non-empty Terrabot case IDs."
        _diag("cursor_validation_invalid_case_set", level="error", run_id=run_id, error=error)
        return {**base, "error": error}
    case_types = {
        str(item.get("case_id") or "").strip(): str(item.get("case_type") or "boolean_context").strip().lower()
        for item in cases
    }
    repos: list[dict[str, str]] = []
    seen_repos: set[tuple[str, str]] = set()
    for item in cases:
        owner = str(item.get("owner") or "").strip()
        repo = str(item.get("repo") or "").strip()
        commit_sha = str(item.get("commit_sha") or item.get("base_ref") or "").strip()
        if not owner or not repo or not commit_sha:
            continue
        key_tuple = (f"{owner}/{repo}".lower(), commit_sha)
        if key_tuple in seen_repos:
            continue
        seen_repos.add(key_tuple)
        repos.append({
            "url": f"https://github.com/{owner}/{repo}",
            "startingRef": commit_sha,
        })

    try:
        if not repos:
            raise ValueError("Cursor validation requires at least one repository pinned to an exact commit SHA.")
        prompt = _build_prompt(run_id, cases)
        create_payload: dict[str, Any] = {
            "prompt": {"text": prompt},
            "repos": repos,
            "mode": "plan",
            "workOnCurrentBranch": False,
            "autoCreatePR": False,
        }
        model = str(os.getenv("TERRABOT_TEST_CURSOR_VALIDATION_MODEL") or "").strip()
        if model:
            create_payload["model"] = {"id": model}
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "terrabot-cursor-validation/1.0",
        }
        _diag(
            "cursor_validation_started",
            run_id=run_id,
            cases=len(cases),
            repositories=len(repos),
            test_branches=sum(1 for item in cases if str(item.get("test_branch") or "").strip()),
            prompt_chars=len(prompt),
            api_base=api_base,
        )
        create_response = http_client.post(
            f"{api_base}/v1/agents",
            headers=headers,
            json=create_payload,
            timeout=request_timeout,
        )
        create_response.raise_for_status()
        created = create_response.json() or {}
        agent = created.get("agent") or {}
        run = created.get("run") or {}
        agent_id = str(agent.get("id") or "").strip()
        run_cursor_id = str(run.get("id") or agent.get("latestRunId") or "").strip()
        agent_url = str(agent.get("url") or "").strip()
        if not agent_id or not run_cursor_id:
            raise ValueError("Cursor create-agent response did not include agent.id and run.id.")
        base.update({"agent_id": agent_id, "agent_url": agent_url})
        _diag(
            "cursor_validation_agent_created",
            run_id=run_id,
            agent_id=agent_id,
            cursor_run_id=run_cursor_id,
            agent_url=agent_url,
        )

        previous_status = ""
        terminal: dict[str, Any] = {}
        deadline = time.monotonic() + total_timeout
        while time.monotonic() < deadline:
            response = http_client.get(
                f"{api_base}/v1/agents/{agent_id}/runs/{run_cursor_id}",
                headers=headers,
                timeout=request_timeout,
            )
            response.raise_for_status()
            terminal = response.json() or {}
            status = str(terminal.get("status") or "").strip().upper()
            if status != previous_status:
                _diag(
                    "cursor_validation_run_status",
                    run_id=run_id,
                    agent_id=agent_id,
                    cursor_run_id=run_cursor_id,
                    status=status,
                )
                previous_status = status
            if status in _TERMINAL_STATUSES:
                break
            time.sleep(poll_seconds)
        else:
            raise TimeoutError(f"Cursor validation exceeded {total_timeout} seconds.")

        status = str(terminal.get("status") or "").strip().upper()
        if status != "FINISHED":
            detail = str(terminal.get("result") or terminal.get("error") or "").strip()
            raise RuntimeError(f"Cursor validation ended with status {status or '<empty>'}: {detail[:800]}")

        branches = ((terminal.get("git") or {}).get("branches") or [])
        if branches:
            branch_names = ", ".join(
                str(item.get("branch") or item.get("repoUrl") or "")
                for item in branches
                if isinstance(item, Mapping)
            )
            raise RuntimeError(
                "Cursor read-only validation reported a pushed branch; verdict rejected: "
                + (branch_names or "unknown branch")
            )

        assistant_result = str(terminal.get("result") or "")
        parsed = _extract_json(assistant_result)
        case_results = _normalise_case_results(
            parsed,
            run_id=run_id,
            expected_case_ids=expected_case_ids,
            case_types=case_types,
        )
        duration_ms = int(terminal.get("durationMs") or ((time.monotonic() - started) * 1000))
        for case_id, verdict in case_results.items():
            _diag(
                "cursor_validation_case_verdict",
                run_id=run_id,
                test_case_id=case_id,
                output_correct=verdict.get("output_correct"),
                context_added=verdict.get("context_added"),
                context_retrievable=verdict.get("context_retrievable"),
                context_reused=verdict.get("context_reused"),
                overall_ok=verdict.get("overall_ok"),
                reason=verdict.get("reason"),
            )
        _diag(
            "cursor_validation_completed",
            run_id=run_id,
            agent_id=agent_id,
            cases=len(case_results),
            passed=sum(1 for item in case_results.values() if item.get("overall_ok")),
            duration_ms=duration_ms,
        )
        return {
            **base,
            "completed": True,
            "duration_ms": duration_ms,
            "case_results": case_results,
        }
    except Exception as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        error = re.sub(r"\s+", " ", str(exc)).strip()[:1600]
        event = "cursor_validation_read_only_violation" if "pushed branch" in error.lower() else "cursor_validation_failed"
        _diag(event, level="error", run_id=run_id, agent_id=base.get("agent_id"), error=error)
        return {**base, "duration_ms": duration_ms, "error": error}


__all__ = ["cursor_result_validation_enabled", "validate_test_run_with_cursor"]
