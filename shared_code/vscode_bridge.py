from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

MAX_FILES = 120
MAX_FILE_BYTES = 64 * 1024


def _safe_relpath(value: str) -> str:
    cleaned = str(value or "").replace("\\", "/").lstrip("/")
    parts = [p for p in cleaned.split("/") if p and p not in {".", ".."}]
    return "/".join(parts)


def _materialize_workspace(files: list[dict[str, Any]], workspace_name: str = "workspace") -> str:
    root = Path(tempfile.mkdtemp(prefix="terrabot-vscode-")) / _safe_relpath(workspace_name or "workspace")
    root.mkdir(parents=True, exist_ok=True)
    for item in files[:MAX_FILES]:
        rel = _safe_relpath(item.get("path") or "")
        if not rel:
            continue
        content = str(item.get("content") or "")
        if len(content.encode("utf-8")) > MAX_FILE_BYTES:
            continue
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return str(root)


def _compact_files(files: list[dict[str, Any]]) -> list[dict[str, str]]:
    compact = []
    for item in files[:MAX_FILES]:
        rel = _safe_relpath(item.get("path") or "")
        if not rel:
            continue
        content = str(item.get("content") or "")
        if len(content.encode("utf-8")) > MAX_FILE_BYTES:
            continue
        compact.append({"path": rel, "content": content})
    return compact


def _hosted_agent_prompt(prompt: str, files: list[dict[str, str]], mode: str) -> str:
    return json.dumps(
        {
            "task": "VS Code repo-aware Terrabot infrastructure request",
            "mode": mode,
            "user_request": prompt,
            "requirements": [
                "Use the supplied repository files as source of truth for conventions, workflow, variables, tfvars, and module patterns.",
                "Keep Azure AI Foundry agent behavior and return production-safe infrastructure code changes.",
                "Return JSON only with keys: summary, files, validation_commands, pr_title, pr_body.",
                "Each files[] entry must include path, operation, and content.",
                "For a new Azure resource/app instance, place it in the existing file that contains the closest matching sibling resources; do not ask the user for a target file when repository evidence answers placement.",
                "Reuse the exact module source/version, input ordering, ingress/networking pattern, naming, tags, and wiring style of the nearest matching sibling resource without asking permission.",
                "When the Azure sibling pattern is object-backed, create a dedicated object-root variable for the new instance, append its declaration to the existing variables.tf, and add its values to the target environment's hub.tfvars when present. Never reuse a sibling instance's object variable as the new resource's configuration root.",
                "Resolve missing non-sensitive values from sibling/default evidence first; otherwise use __FILL__<input_name>__ plus user_fillable metadata instead of asking questions. Only sensitive values with no safe repository reference pattern or genuine structural ambiguity may block generation.",
                "Do not invent missing backend secrets; reuse the repository's demonstrated secret-reference pattern. Questions are only for truly blocking sensitive/structural gaps."
            ],
            "repository_files": files,
        },
        indent=2,
    )


def handle_vscode_scan_request(data: dict, headers=None):
    del headers
    files = data.get("files") or []
    if not isinstance(files, list):
        return {"ok": False, "reply": "files must be a list."}, 400
    workspace = _materialize_workspace(files, data.get("workspace_name") or "workspace")
    from terrabot_core.service import scan_workspace
    return {"ok": True, "result": scan_workspace(workspace, data.get("prompt") or "")}, 200


def handle_vscode_explain_workflow_request(data: dict, headers=None):
    del headers
    prompt = (data.get("prompt") or "Explain this repository workflow").strip()
    files = data.get("files") or []
    if not isinstance(files, list):
        return {"ok": False, "reply": "files must be a list."}, 400
    workspace = _materialize_workspace(files, data.get("workspace_name") or "workspace")
    from terrabot_core.service import explain_workflow
    return {"ok": True, "result": explain_workflow(workspace, prompt)}, 200


def handle_vscode_ask_request(data: dict, headers=None):
    del headers
    prompt = (data.get("prompt") or data.get("message") or "").strip()
    files = data.get("files") or []
    if not prompt:
        return {"ok": False, "reply": "prompt is required."}, 400
    if not isinstance(files, list) or not files:
        return {"ok": False, "reply": "files are required for hosted VS Code repo-aware mode."}, 400

    workspace = _materialize_workspace(files, data.get("workspace_name") or "workspace")

    # First build deterministic repo profile/context locally in the Function App.
    from terrabot_core.service import ask_infrastructure
    plan = ask_infrastructure(workspace, prompt)

    # If a hosted generation command is configured, terrabot_core already returned a diff.
    if plan.get("status") in {"patch_ready", "needs_values", "blocked_by_policy", "invalid_generation"}:
        return {"ok": True, "result": plan, "diff": plan.get("diff") or "", "reply": plan.get("summary") or ""}, 200

    # Otherwise call the existing Azure AI Foundry agent used by Terrabot today.
    from shared_code.terrabot_service import call_agent, try_parse_agent_output
    agent_input = _hosted_agent_prompt(prompt, _compact_files(files), "generate_patch")
    conversation_id, reply = call_agent(data.get("thread_id") or "", agent_input)
    parsed = None
    try:
        parsed = try_parse_agent_output(reply)
    except Exception:
        parsed = None

    return {
        "ok": True,
        "thread_id": conversation_id,
        "reply": reply,
        "result": parsed or plan,
    }, 200
