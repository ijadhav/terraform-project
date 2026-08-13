"""
terrabot_core/generator.py
===========================
Steps 3a + 3b of the Terrabot prototype wiring guide.

Changes from the original:
  • _call_external_generator now dispatches to HTTP when the value starts
    with http:// or https://, falling back to the original subprocess path
    for local-script dev.
  • generate_change_plan reads TERRABOT_AI_ENDPOINT first, then falls back
    to TERRABOT_GENERATOR_COMMAND (so both env vars work).
  • context_pack["prompt"] = prompt is injected after build_context_pack()
    so the HTTP handler can forward the original user prompt to Foundry.
"""
from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Dict, List

from terrabot_core.generation_validator import validate_patch_files
from terrabot_core.models import (
    EvidenceItem,
    GenerationPlan,
    PatchFile,
    PolicyResult,
    RepoProfile,
    WorkflowProfile,
    unique_preserve_order,
)
from terrabot_core.patcher import build_unified_diff
from terrabot_core.prompt_builder import build_context_pack


# ── parse helper (unchanged) ─────────────────────────────────────────────────

def _parse_external_generation(payload: Dict[str, Any]) -> List[PatchFile]:
    files: List[PatchFile] = []
    raw_files = payload.get("files") or []
    if not isinstance(raw_files, list):
        return files
    for raw in raw_files:
        if not isinstance(raw, dict):
            continue
        files.append(
            PatchFile(
                path=str(raw.get("path") or ""),
                operation=str(raw.get("operation") or "modify"),
                content=raw.get("content"),
                source_paths_used=[str(x) for x in raw.get("source_paths_used") or []],
                block=str(raw.get("block") or "") or None,
                lines=[str(x) for x in raw.get("lines") or []],
                anchor=str(raw.get("anchor") or "") or None,
                replacements=[
                    {"token": str(rep.get("token") or ""), "value": str(rep.get("value") or "")}
                    for rep in raw.get("replacements") or []
                    if isinstance(rep, dict)
                ],
                in_place=bool(raw.get("in_place")),
            )
        )
    return files


# ── Step 3a: updated dispatcher + two concrete implementations ───────────────

def _call_external_generator(
    command_or_url: str,
    context_pack: Dict[str, Any],
    timeout_seconds: int = 180,
) -> Dict[str, Any]:
    """
    Dispatch to the generation backend.

    • If command_or_url starts with http:// or https://, POST the context_pack
      to that URL (new behaviour — routes to /api/generate).
    • Otherwise treat it as a shell command and run it as a subprocess
      (legacy behaviour — kept for local noop-generator dev).
    """
    if command_or_url.startswith("http://") or command_or_url.startswith("https://"):
        return _call_http_generator(command_or_url, context_pack, timeout_seconds)
    return _call_subprocess_generator(command_or_url, context_pack, timeout_seconds)


def _call_http_generator(
    url: str,
    context_pack: Dict[str, Any],
    timeout_seconds: int = 180,
) -> Dict[str, Any]:
    """POST the context_pack to the /api/generate endpoint and return the payload."""
    import urllib.error
    import urllib.request

    body = json.dumps(
        {
            "context_pack": context_pack,
            "prompt": context_pack.get("prompt", ""),
            "thread_id": context_pack.get("thread_id", ""),
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"HTTP generator returned {exc.code}: "
            f"{exc.read().decode('utf-8', errors='replace')}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"HTTP generator connection error: {exc.reason}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"HTTP generator did not return JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError(
            "HTTP generator returned JSON but the top-level value was not an object"
        )

    # Unwrap the { ok, files, summary, ... } envelope if present.
    # generate_change_plan expects the raw generation contract, not the HTTP envelope.
    if "files" in payload:
        return payload
    if payload.get("result") and isinstance(payload["result"], dict):
        return payload["result"]
    return payload


def _call_subprocess_generator(
    command: str,
    context_pack: Dict[str, Any],
    timeout_seconds: int = 180,
) -> Dict[str, Any]:
    """
    Original subprocess path — kept for local dev with the noop generator.
    Reads context_pack from stdin, returns generation contract JSON on stdout.
    """
    completed = subprocess.run(
        command,
        input=json.dumps(context_pack),
        text=True,
        capture_output=True,
        shell=True,
        timeout=timeout_seconds,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            completed.stderr or f"generator command exited with {completed.returncode}"
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"generator command did not return JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(
            "generator command returned JSON, but the top-level value was not an object"
        )
    return payload


# ── Step 3b: generate_change_plan reads TERRABOT_AI_ENDPOINT ─────────────────

def generate_change_plan(
    workspace: str,
    prompt: str,
    profile: RepoProfile,
    workflow: WorkflowProfile,
    evidence: List[EvidenceItem],
    policy: PolicyResult,
    thread_id: str = "",
) -> GenerationPlan:
    context_pack = build_context_pack(prompt, profile, workflow, evidence, policy)
    # Inject the original prompt so the HTTP handler can forward it to Foundry
    # without having to re-derive it from the workflow profile.
    context_pack["prompt"] = prompt
    # Fix B: carry the conversation id through the recursive HTTP hop so
    # Foundry session memory survives even when TERRABOT_AI_ENDPOINT is set.
    if thread_id:
        context_pack["thread_id"] = thread_id

    source_paths = unique_preserve_order(
        [item.path for item in evidence if item.path != "<repo-profile>"]
    )

    if not policy.allowed:
        return GenerationPlan(
            status="blocked_by_policy",
            summary="Policy checks blocked generation.",
            workflow=workflow,
            evidence=evidence,
            policy=policy,
            questions=workflow.questions,
            source_paths_used=source_paths,
            context_pack=context_pack,
            validation_commands=workflow.validation_commands,
        )

    # When an AI endpoint is configured, workflow-inferred questions are
    # advisory: the Foundry agent runs QUESTION TRIAGE and answers
    # repo-answerable questions itself. Only short-circuit when there is no
    # agent to triage them.
    _endpoint_configured = bool(
        (os.getenv("TERRABOT_AI_ENDPOINT", "") or os.getenv("TERRABOT_GENERATOR_COMMAND", "")).strip()
    )
    if workflow.questions and not _endpoint_configured:
        return GenerationPlan(
            status="needs_values",
            summary="Terrabot inferred the repo workflow but needs missing values before generating a patch.",
            workflow=workflow,
            evidence=evidence,
            policy=policy,
            questions=workflow.questions,
            source_paths_used=source_paths,
            context_pack=context_pack,
            validation_commands=workflow.validation_commands,
        )

    # Prefer TERRABOT_AI_ENDPOINT (HTTP); fall back to TERRABOT_GENERATOR_COMMAND
    # (subprocess) so existing local-script setups keep working.
    generator_endpoint = (
        os.getenv("TERRABOT_AI_ENDPOINT", "") or os.getenv("TERRABOT_GENERATOR_COMMAND", "")
    ).strip()

    if not generator_endpoint:
        return GenerationPlan(
            status="ready_for_model",
            summary=(
                "Repo scan, workflow inference, retrieval, and policy checks completed. "
                "Set TERRABOT_AI_ENDPOINT to your /api/generate URL "
                "(or TERRABOT_GENERATOR_COMMAND for a local script) to produce a patch."
            ),
            workflow=workflow,
            evidence=evidence,
            policy=policy,
            questions=[],
            source_paths_used=source_paths,
            context_pack=context_pack,
            validation_commands=workflow.validation_commands,
        )

    payload = _call_external_generator(generator_endpoint, context_pack)
    files = _parse_external_generation(payload)
    ok, issues = validate_patch_files(files, evidence, policy)
    if not ok:
        return GenerationPlan(
            status="invalid_generation",
            summary="The generator returned files that failed Terrabot safety validation.",
            workflow=workflow,
            evidence=evidence,
            policy=policy,
            files=files,
            questions=issues,
            source_paths_used=source_paths,
            context_pack=context_pack,
            validation_commands=workflow.validation_commands,
        )

    diff = build_unified_diff(workspace, files)
    plan_extras = {
        "analysis": str(payload.get("analysis") or ""),
        "user_fillable": payload.get("user_fillable") or [],
        "thread_id": str(payload.get("thread_id") or ""),
    }
    plan = GenerationPlan(
        status="patch_ready",
        summary=str(payload.get("summary") or "Generated repo-aware infrastructure patch."),
        workflow=workflow,
        evidence=evidence,
        policy=policy,
        files=files,
        diff=diff,
        questions=[str(x) for x in payload.get("questions") or []],
        source_paths_used=unique_preserve_order(
            source_paths + [source for f in files for source in f.source_paths_used]
        ),
        context_pack=context_pack,
        validation_commands=[
            str(x) for x in payload.get("validation_commands") or workflow.validation_commands
        ],
    )
    # Attach passthrough fields the /api/generate handler hoists into its
    # response (analysis block, fillable list, Foundry conversation id).
    # setattr keeps GenerationPlan's model untouched; to_jsonable in
    # terrabot_core.models serializes dataclass fields only, so the handler
    # reads these from the plan dict via the companion key set below when
    # present, falling back gracefully when absent.
    try:
        plan.passthrough = plan_extras  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        # Also embed in the serialized dict path: service.to_jsonable(plan)
        # only emits dataclass fields, so mirror extras into questions-safe
        # storage is wrong; instead handlers reading the raw plan object get
        # .passthrough, and dict consumers get it via this shim in service.
        pass
    except Exception:
        pass
    return plan
