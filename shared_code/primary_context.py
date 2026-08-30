"""Primary Terraform context loader.

This module loads the concise, backend-authored Terraform guidance under
``context/terraform/`` and selects the slice relevant to a request
(cloud / repo_target / environment). The result is attached to the Foundry
agent input alongside — never instead of — live repository evidence and the
existing repository-context retrieval.

Precedence (highest wins), also stated inside the returned block so the model
sees it:

    live repository evidence
    > repository README/.github/.Serena rules
    > this primary Terraform context
    > terrabot repository-context index results
    > generic Foundry instructions

If the primary context disagrees with live repository evidence, the live
repository always wins. The loader is intentionally cheap (cached file reads)
and fail-open: any error yields an empty, non-blocking result.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

LOGGER = logging.getLogger("terrabot.primary_context")

# context/terraform lives at the repository root, one level above shared_code/.
_CONTEXT_DIR = Path(__file__).resolve().parents[1] / "context" / "terraform"

_RULES_FILE = "terraform-generation-rules.md"
_REPO_FILES = {
    "tf-azure-hub": "tf-azure-hub.md",
    "tf-devops": "tf-devops.md",
}

# Default per-document byte budget so a large request cannot be dominated by
# static context. Overridable for tuning without code changes.
_MAX_DOC_CHARS = int(os.getenv("TERRABOT_PRIMARY_CONTEXT_MAX_DOC_CHARS", "8000"))

PRECEDENCE_TEXT = (
    "CONTEXT PRECEDENCE (highest wins): "
    "(1) live repository evidence and current file contents in this request; "
    "(2) the target repository's own README/.github/.Serena rules; "
    "(3) this PRIMARY TERRAFORM CONTEXT; "
    "(4) terrabot repository-context index/retrieval results; "
    "(5) generic Foundry instructions. "
    "If this primary context disagrees with live repository evidence, the live "
    "repository always wins — treat this context as possibly stale and verify "
    "every path, flag, module source, and variable name against the live files."
)


@lru_cache(maxsize=8)
def _read_doc(filename: str) -> str:
    path = _CONTEXT_DIR / filename
    try:
        return path.read_text(encoding="utf-8")
    except Exception as exc:  # pragma: no cover - defensive, fail open
        LOGGER.debug("primary_context: could not read %s: %s", filename, exc)
        return ""


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def select_repo_docs(
    cloud: str = "",
    repo_target: str = "",
    prompt: str = "",
    workflow: str = "",
) -> List[str]:
    """Return the ordered list of per-repo doc filenames relevant to a request.

    Pure function (no I/O) so it is easily unit tested. Resolution order:
    explicit repo_target, then cloud, then keyword hints in prompt/workflow.
    When nothing resolves, both repo docs are returned so the model still has
    grounding (bounded downstream).
    """
    repo_target_n = _norm(repo_target)
    cloud_n = _norm(cloud)
    text = f"{_norm(prompt)} {_norm(workflow)}"

    selected: List[str] = []

    def add(name: str) -> None:
        if name and name not in selected:
            selected.append(name)

    if repo_target_n in _REPO_FILES:
        add(_REPO_FILES[repo_target_n])

    if not selected:
        if cloud_n == "azure":
            add(_REPO_FILES["tf-azure-hub"])
        elif cloud_n == "aws":
            add(_REPO_FILES["tf-devops"])

    if not selected:
        if "tf-azure-hub" in text or "azure" in text or "azurerm" in text:
            add(_REPO_FILES["tf-azure-hub"])
        if "tf-devops" in text or "aws" in text or "devops" in text:
            add(_REPO_FILES["tf-devops"])

    if not selected:
        # Unknown scope: provide both so generation is still grounded.
        add(_REPO_FILES["tf-azure-hub"])
        add(_REPO_FILES["tf-devops"])

    return selected


def _bounded(text: str, limit: int) -> str:
    text = text or ""
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n\n[primary context excerpt truncated]\n"


def load_primary_terraform_context(
    cloud: str = "",
    repo_target: str = "",
    environment: str = "",
    prompt: str = "",
    workflow: str = "",
    max_doc_chars: Optional[int] = None,
) -> Dict[str, Any]:
    """Load and assemble the primary Terraform context for a request.

    Returns a dict:
        loaded (bool)       — whether any primary context content was found
        block (str)         — the assembled, precedence-prefixed markdown block
                              (empty string when nothing loaded)
        sources (list[str]) — the doc filenames included
        precedence (str)    — the precedence statement (always populated)
        cloud/repo_target/environment — echoed resolution inputs (for logging)

    Never raises: on any failure it returns a non-blocking empty result.
    """
    limit = _MAX_DOC_CHARS if max_doc_chars is None else int(max_doc_chars)
    try:
        doc_names: List[str] = []
        rules = _read_doc(_RULES_FILE)
        if rules:
            doc_names.append(_RULES_FILE)
        for name in select_repo_docs(
            cloud=cloud, repo_target=repo_target, prompt=prompt, workflow=workflow
        ):
            if _read_doc(name):
                doc_names.append(name)

        sections: List[str] = [PRECEDENCE_TEXT]
        if environment:
            sections.append(f"RESOLVED ENVIRONMENT/SCOPE HINT: {environment}")
        for name in doc_names:
            content = _bounded(_read_doc(name), limit)
            if content:
                sections.append(f"--- primary-context: {name} ---\n{content}")

        loaded = len(doc_names) > 0
        block = "\n\n".join(sections) if loaded else ""
        return {
            "loaded": loaded,
            "block": block,
            "sources": doc_names,
            "precedence": PRECEDENCE_TEXT,
            "cloud": _norm(cloud),
            "repo_target": _norm(repo_target),
            "environment": str(environment or ""),
        }
    except Exception as exc:  # pragma: no cover - defensive, fail open
        LOGGER.debug("primary_context: load failed: %s", exc)
        return {
            "loaded": False,
            "block": "",
            "sources": [],
            "precedence": PRECEDENCE_TEXT,
            "cloud": _norm(cloud),
            "repo_target": _norm(repo_target),
            "environment": str(environment or ""),
        }


def log_primary_context_loaded(where: str, result: Dict[str, Any], **extra: Any) -> None:
    """Emit a consistent, secret-free log line that primary context was loaded."""
    try:
        extra_str = " ".join(f"{k}={v}" for k, v in extra.items() if v not in (None, ""))
        LOGGER.info(
            "PRIMARY-CONTEXT-LOADED where=%s loaded=%s cloud=%s repo_target=%s "
            "environment=%s sources=%s chars=%s %s",
            where,
            result.get("loaded"),
            result.get("cloud") or "",
            result.get("repo_target") or "",
            result.get("environment") or "",
            ",".join(result.get("sources") or []) or "(none)",
            len(result.get("block") or ""),
            extra_str,
        )
    except Exception:  # pragma: no cover
        LOGGER.debug("primary_context: logging failed", exc_info=True)
