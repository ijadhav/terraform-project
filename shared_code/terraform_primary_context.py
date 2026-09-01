"""Load and attach Terrabot's repository-aligned Terraform primary context.

The context is stored as YAML but is intentionally transported as opaque text.
This keeps the Function App free of a new YAML runtime dependency and preserves
comments, ordering, and future schema changes. Live repository evidence remains
authoritative; this file supplies stable authoring conventions.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("terrabot.terraform_primary_context")
LOGGER.setLevel(logging.INFO)

_TRUE_VALUES = {"1", "true", "yes", "on"}
_DEFAULT_CONTEXT_PATH = (
    Path(__file__).resolve().parent
    / "context"
    / "terrabot_terraform_primary_context.yaml"
)
_CONTEXT_LOCK = threading.Lock()
_CONTEXT_CACHE: tuple[str, int, int, "PrimaryContext"] | None = None


@dataclass(frozen=True)
class PrimaryContext:
    """Immutable loaded primary-context document and provenance."""

    path: str
    content: str
    sha256: str
    characters: int
    format: str = "yaml"
    schema_version: str = "terrabot.terraform-primary-context.v1"
    authority: str = "repository_conventions_only_live_selected_commit_wins"

    def as_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "format": self.format,
            "sha256": self.sha256,
            "characters": self.characters,
            "authority": self.authority,
            "content": self.content,
        }


def _is_enabled() -> bool:
    value = os.getenv("TERRABOT_TERRAFORM_PRIMARY_CONTEXT_ENABLED", "true")
    return value.strip().lower() in _TRUE_VALUES


def _context_path() -> Path:
    configured = os.getenv("TERRABOT_TERRAFORM_PRIMARY_CONTEXT_PATH", "").strip()
    return Path(configured).expanduser() if configured else _DEFAULT_CONTEXT_PATH


def _max_characters() -> int:
    raw = os.getenv("TERRABOT_TERRAFORM_PRIMARY_CONTEXT_MAX_CHARS", "120000")
    try:
        return max(1000, min(int(raw), 500000))
    except (TypeError, ValueError):
        return 120000


def clear_primary_context_cache() -> None:
    """Clear the process cache. Intended for tests and controlled reloads."""

    global _CONTEXT_CACHE
    with _CONTEXT_LOCK:
        _CONTEXT_CACHE = None


def load_primary_context() -> PrimaryContext | None:
    """Load the configured context, using a stat-keyed in-process cache.

    Missing or unreadable context fails open so an existing Terrabot deployment
    does not lose generation capability. The caller logs that primary context
    was unavailable, and live repository/context-index behavior continues.
    """

    global _CONTEXT_CACHE
    if not _is_enabled():
        return None

    path = _context_path()
    try:
        stat = path.stat()
    except OSError as exc:
        LOGGER.warning(
            "[TerrabotContext] event=terraform_primary_context_unavailable "
            "path=%s error=%s",
            path,
            exc,
        )
        return None

    cache_key = (str(path.resolve()), int(stat.st_mtime_ns), int(stat.st_size))
    with _CONTEXT_LOCK:
        if _CONTEXT_CACHE and _CONTEXT_CACHE[:3] == cache_key:
            return _CONTEXT_CACHE[3]

        try:
            content = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            LOGGER.warning(
                "[TerrabotContext] event=terraform_primary_context_unavailable "
                "path=%s error=%s",
                path,
                exc,
            )
            return None

        if not content:
            LOGGER.warning(
                "[TerrabotContext] event=terraform_primary_context_empty path=%s",
                path,
            )
            return None

        maximum = _max_characters()
        if len(content) > maximum:
            LOGGER.warning(
                "[TerrabotContext] event=terraform_primary_context_too_large "
                "path=%s characters=%s max_characters=%s",
                path,
                len(content),
                maximum,
            )
            return None

        context = PrimaryContext(
            path=str(path.resolve()),
            content=content,
            sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            characters=len(content),
        )
        _CONTEXT_CACHE = (*cache_key, context)
        return context


def primary_context_payload() -> dict[str, Any] | None:
    context = load_primary_context()
    return context.as_payload() if context else None


def attach_primary_context_to_agent_input(
    agent_input: str,
    *,
    logger: logging.Logger | None = None,
) -> str:
    """Attach primary context to a JSON Foundry request without altering it otherwise.

    Non-JSON inputs are returned unchanged because blindly wrapping them could
    break legacy callers. The current Teams generation path already sends JSON.
    """

    context = load_primary_context()
    if context is None:
        return agent_input

    try:
        payload = json.loads(str(agent_input or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        (logger or LOGGER).warning(
            "[TerrabotContext] event=terraform_primary_context_not_attached "
            "reason=agent_input_not_json sha256=%s",
            context.sha256,
        )
        return agent_input

    if not isinstance(payload, dict):
        (logger or LOGGER).warning(
            "[TerrabotContext] event=terraform_primary_context_not_attached "
            "reason=agent_input_not_object sha256=%s",
            context.sha256,
        )
        return agent_input

    payload["terraform_primary_context"] = context.as_payload()
    enriched = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    (logger or LOGGER).info(
        "[TerrabotContext] event=terraform_primary_context_attached "
        "sha256=%s characters=%s enriched_input_characters=%s",
        context.sha256,
        context.characters,
        len(enriched),
    )
    return enriched
