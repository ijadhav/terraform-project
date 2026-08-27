"""Optional Cursor-powered semantic test generation for Terrabot automated tests.

The semantic engine never defines Terraform ground truth.  The caller supplies a
repository-derived target (repo/environment/path/flag/value); Cursor is allowed
only to generate alternative human wording for that already-proven target.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shlex
import subprocess
from typing import Any

LOGGER = logging.getLogger("terrabot.automated_tests.semantic")


def cursor_enabled() -> bool:
    return os.getenv("TERRABOT_TEST_CURSOR_ENABLED", "false").strip().lower() in {
        "1", "true", "yes", "on"
    }


def _extract_json(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except Exception:
        pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {}
    try:
        value = json.loads(match.group(0))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def generate_semantic_variants(
    *,
    cloud: str,
    environment: str,
    alias: str,
    desired_value: bool,
    path: str,
    flag: str,
    count: int = 3,
    workspace: str = "",
) -> list[str]:
    """Return Cursor-generated user-style paraphrases for deterministic truth.

    Failures are intentionally non-fatal: the existing deterministic prompt
    generator remains the fallback so enabling Cursor cannot break test runs.
    """
    if not cursor_enabled() or count <= 0:
        return []

    command = os.getenv("TERRABOT_TEST_CURSOR_COMMAND", "agent").strip() or "agent"
    model = os.getenv("TERRABOT_TEST_CURSOR_MODEL", "").strip()
    timeout = max(10, min(int(os.getenv("TERRABOT_TEST_CURSOR_TIMEOUT_SECONDS", "90")), 300))
    prompt = f"""You are generating semantic mutation prompts for an infrastructure test harness.
Do not edit files. Do not solve the Terraform task. Do not invent another target.
Ground truth is fixed and was deterministically derived from the live repository:
- cloud: {cloud}
- environment: {environment}
- repository path: {path}
- Terraform Boolean control: {flag}
- human concept: {alias}
- desired Boolean value: {str(bool(desired_value)).lower()}

Generate {count} short, realistic user requests that mean exactly this operation but avoid using the exact Terraform flag name.
Use varied vocabulary and sentence structure. Keep the environment name verbatim so repository routing remains testable.
Return JSON only in this exact shape: {{"prompts":["...","..."]}}.
"""
    args = shlex.split(command) + ["-p", prompt, "--mode=ask", "--output-format", "text"]
    if workspace:
        args += ["--workspace", workspace]
    if model:
        args += ["--model", model]
    try:
        completed = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        LOGGER.warning("Cursor semantic generation unavailable: %s", exc)
        return []
    if completed.returncode != 0:
        LOGGER.warning("Cursor semantic generation failed rc=%s stderr=%s", completed.returncode, completed.stderr[:500])
        return []
    payload = _extract_json(completed.stdout)
    prompts = payload.get("prompts") if isinstance(payload, dict) else []
    result: list[str] = []
    seen: set[str] = set()
    for item in prompts or []:
        text = re.sub(r"\s+", " ", str(item or "")).strip()
        key = text.lower()
        if not text or key in seen or flag.lower() in key:
            continue
        if environment and environment.lower() not in key:
            continue
        seen.add(key)
        result.append(text)
        if len(result) >= count:
            break
    return result
