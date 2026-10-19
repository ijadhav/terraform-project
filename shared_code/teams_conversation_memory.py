"""Teams conversation memory for Terrabot.

Keeps a bounded, per-Teams-conversation transcript (user + bot turns) so the
Foundry agent can treat short messages as follow-ups the way a chatbot does.

Design rules (matching the Terrabot contract):
- AUXILIARY ONLY: the transcript is conversational context. Live GitHub
  repository evidence remains the sole authority for repository state; the
  agent must never generate code from the transcript alone. The context block
  emitted by ``get_context_block`` states this explicitly.
- CLEARED WITH THE CHAT: the ``clear``/``new chat`` reset command wipes the
  transcript together with the rest of the Teams workflow state. Entries also
  expire after ``TTL_SECONDS`` so a conversation the user abandoned (or whose
  history they cleared in the Teams UI — Teams sends no bot event for that)
  does not leak stale context into a later request.
- BOUNDED: at most ``MAX_TURNS`` turns and ``MAX_CONTEXT_CHARS`` characters
  are ever forwarded, so the agent's context budget is protected.

This module is process-local by design (same lifetime as TEAMS_THREAD_STATE
in teams_bot.py). If the Function App scales to multiple workers, back the
``_STORE`` dict with the same table/blob storage used for thread state — the
public API will not change.
"""

from __future__ import annotations

import re
import threading
import time
from typing import Dict, List

MAX_TURNS = 24            # total remembered turns (user + bot combined)
MAX_TURN_CHARS = 700      # each stored turn is truncated to this length
MAX_CONTEXT_CHARS = 6000  # cap on the emitted context block
TTL_SECONDS = 24 * 3600   # transcript lifetime without activity

_LOCK = threading.Lock()
_STORE: Dict[str, dict] = {}

_CONTEXT_HEADER = (
    "TEAMS CONVERSATION CONTEXT (auxiliary memory): the transcript below is "
    "the user's current Teams chat with Terrabot, oldest first. Use it ONLY "
    "to resolve follow-ups, pronouns, prior selections, and previously "
    "supplied values. Live GitHub repository evidence remains the sole "
    "authority for repository state — never claim a file, resource, value, "
    "or branch exists based on this transcript alone, and never generate "
    "code from it without current repository evidence."
)

_NOISE_RE = re.compile(r"^\s*(terrabot is processing your request\.*\s*)$", re.IGNORECASE)


def _now() -> float:
    return time.time()


def _clean(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(cleaned) > MAX_TURN_CHARS:
        cleaned = cleaned[: MAX_TURN_CHARS - 1].rstrip() + "…"
    return cleaned


def _entry(conversation_id: str) -> dict:
    record = _STORE.get(conversation_id)
    if record is None or (_now() - record.get("updated", 0)) > TTL_SECONDS:
        record = {"turns": [], "updated": _now()}
        _STORE[conversation_id] = record
    return record


def _record(conversation_id: str, role: str, text: str) -> None:
    cid = str(conversation_id or "").strip()
    cleaned = _clean(text)
    if not cid or not cleaned or _NOISE_RE.match(cleaned):
        return
    with _LOCK:
        record = _entry(cid)
        turns: List[dict] = record["turns"]
        # Collapse duplicate consecutive turns (retries, resent prompts).
        if turns and turns[-1]["role"] == role and turns[-1]["text"] == cleaned:
            record["updated"] = _now()
            return
        turns.append({"role": role, "text": cleaned, "at": _now()})
        record["turns"] = turns[-MAX_TURNS:]
        record["updated"] = _now()


def record_user_message(conversation_id: str, text: str) -> None:
    """Remember a user turn for this Teams conversation."""
    _record(conversation_id, "user", text)


def record_bot_message(conversation_id: str, text: str) -> None:
    """Remember a Terrabot reply for this Teams conversation."""
    _record(conversation_id, "terrabot", text)


def get_context_block(conversation_id: str) -> str:
    """Return the transcript as a bounded context block for the agent input,
    or an empty string when there is nothing (or nothing fresh) to send.

    The current in-flight user message should be recorded BEFORE calling
    this; the block excludes the final user turn so the prompt itself is
    never duplicated inside the context."""
    cid = str(conversation_id or "").strip()
    if not cid:
        return ""
    with _LOCK:
        record = _STORE.get(cid)
        if not record or (_now() - record.get("updated", 0)) > TTL_SECONDS:
            _STORE.pop(cid, None)
            return ""
        turns = list(record.get("turns") or [])
    if turns and turns[-1]["role"] == "user":
        turns = turns[:-1]
    if not turns:
        return ""
    lines: List[str] = []
    used = 0
    for turn in reversed(turns):  # newest first, then re-reverse for order
        line = f"{turn['role']}: {turn['text']}"
        if used + len(line) + 1 > MAX_CONTEXT_CHARS:
            break
        lines.append(line)
        used += len(line) + 1
    if not lines:
        return ""
    lines.reverse()
    return _CONTEXT_HEADER + "\n" + "\n".join(lines)


def clear(conversation_id: str) -> bool:
    """Forget the transcript for one Teams conversation (reset command)."""
    cid = str(conversation_id or "").strip()
    with _LOCK:
        return _STORE.pop(cid, None) is not None


def purge_expired() -> int:
    """Drop expired transcripts; safe to call opportunistically."""
    cutoff = _now() - TTL_SECONDS
    with _LOCK:
        stale = [cid for cid, record in _STORE.items() if record.get("updated", 0) < cutoff]
        for cid in stale:
            _STORE.pop(cid, None)
    return len(stale)

# Structured infrastructure continuity is serialized by the Teams durable state
# writer. These helpers deliberately perform no persistence or resource routing.
# Keeping an original prompt separate from clarified fields prevents the latest
# one-word answer from replacing the Terraform operation being prepared.
_INFRA_FIELDS = frozenset({
    "cloud", "repo_target", "workflow", "environment", "environments",
    "resolved_targets", "selected_file_paths", "boolean_assignments",
    "branch_preference", "existing_branch", "target_resource", "target_scope",
})


def merge_infrastructure_intent(
    existing: dict | None,
    original_prompt: str = "",
    *,
    clarified_fields: dict | None = None,
    clarification: str = "",
    new_request: bool = False,
) -> dict:
    """Merge only explicitly clarified attributes; never discard other targets.

    The caller must supply field names established by backend/Foundry evidence.
    A free-text answer is retained verbatim but cannot silently rewrite cloud,
    environments, Boolean assignments or target paths.
    """
    previous = {} if new_request else dict(existing or {})
    source = str(original_prompt or "").strip()
    if source and (new_request or not previous.get("original_prompt")):
        previous["original_prompt"] = source
    previous.setdefault("clarifications", [])
    clarifications = list(previous.get("clarifications") or [])
    clarification = str(clarification or "").strip()
    if clarification and clarification not in clarifications:
        clarifications.append(clarification)
    previous["clarifications"] = clarifications[-12:]
    for key, value in (clarified_fields or {}).items():
        if key not in _INFRA_FIELDS or value is None or value == "":
            continue
        if key in {"resolved_targets", "selected_file_paths", "environments"}:
            # Multi-target requests are additive unless a specific target was
            # explicitly corrected by its stable id/path.
            original = list(previous.get(key) or [])
            updates = list(value) if isinstance(value, (list, tuple)) else [value]
            for item in updates:
                if isinstance(item, dict):
                    identity = str(item.get("path") or item.get("id") or "").strip()
                    idx = next((i for i, old in enumerate(original) if isinstance(old, dict)
                                and str(old.get("path") or old.get("id") or "").strip() == identity), -1) if identity else -1
                    if idx >= 0:
                        original[idx] = {**original[idx], **item}
                    elif item not in original:
                        original.append(item)
                elif item not in original:
                    original.append(item)
            previous[key] = original
        elif key == "boolean_assignments":
            # A Boolean flag can legitimately require different values in
            # different environments. Preserve the per-target tuple, rather
            # than collapsing everything to the last flag name seen.
            if isinstance(value, dict):
                previous[key] = {**(previous.get(key) if isinstance(previous.get(key), dict) else {}), **value}
            elif isinstance(value, (list, tuple)):
                assignments = list(previous.get(key) or []) if isinstance(previous.get(key), (list, tuple)) else []
                for assignment in value:
                    if not isinstance(assignment, dict):
                        continue
                    identity = (str(assignment.get("environment_path") or assignment.get("path") or ""),
                                str(assignment.get("flag") or ""))
                    at = next((i for i, old in enumerate(assignments)
                               if isinstance(old, dict) and
                               (str(old.get("environment_path") or old.get("path") or ""),
                                str(old.get("flag") or "")) == identity), -1)
                    if at >= 0:
                        assignments[at] = {**assignments[at], **assignment}
                    else:
                        assignments.append(assignment)
                previous[key] = assignments
        else:
            previous[key] = value
    return previous


def infrastructure_prompt(intent: dict | None) -> str:
    """Keep the original infrastructure instruction and bounded corrections."""
    value = dict(intent or {})
    original = str(value.get("original_prompt") or "").strip()
    corrections = [str(item).strip() for item in (value.get("clarifications") or []) if str(item).strip()]
    if not original:
        return ""
    if not corrections:
        return original
    return (original + "\nClarifications (newer corrections override only their specific fields; "
            "preserve all other targets, paths, and Boolean assignments):\n" +
            "\n".join(f"- {item}" for item in corrections[-8:]))[-6500:]
