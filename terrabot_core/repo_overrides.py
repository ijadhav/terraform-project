from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def _parse_simple_yaml(text: str) -> Dict[str, Any]:
    """Small dependency-free parser for flat .terrabot/repo.yaml overrides.

    Supported shapes are intentionally limited to simple key/value pairs and
    comma separated lists, which is enough for repo-level hints. Full YAML is
    not required for the local scanner.
    """
    data: Dict[str, Any] = {}
    for raw_line in (text or "").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if not key:
            continue
        if value.startswith("[") and value.endswith("]"):
            items = [item.strip().strip("'\"") for item in value[1:-1].split(",")]
            data[key] = [item for item in items if item]
        elif "," in value:
            data[key] = [item.strip() for item in value.split(",") if item.strip()]
        elif value.lower() in {"true", "false"}:
            data[key] = value.lower() == "true"
        else:
            data[key] = value
    return data


def load_repo_overrides(workspace: Path) -> Dict[str, Any]:
    folder = workspace / ".terrabot"
    for filename in ("repo.json", "repo.yaml", "repo.yml"):
        path = folder / filename
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if filename.endswith(".json"):
            try:
                value = json.loads(text)
                return value if isinstance(value, dict) else {}
            except json.JSONDecodeError:
                return {}
        return _parse_simple_yaml(text)
    return {}
