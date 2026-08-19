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