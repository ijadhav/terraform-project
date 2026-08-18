"""Durable, centralized Terrabot agent context/memory cache.

Today the Foundry agent is grounded by re-reading the live GitHub repository
head on (almost) every request. That is safe but expensive and repetitive:
the same module, environment file, or resource block is frequently re-fetched
and re-sent to the agent turn after turn, and other users working on the same
part of the repository get no benefit from work Terrabot already did.

This module adds a long-term-context layer that sits *between* the live
repository and the Foundry agent:

* Every agent turn (chat or infrastructure) can be recorded here with the
  user prompt, which files the backend searched/supplied, a summary of the
  retrieved repository context, and a summary of the code the agent
  generated (see :func:`record_agent_turn`).
* Future requests can pull a compact, bounded "memory context" block back
  out (see :func:`get_combined_memory_context`) and hand it to the agent
  alongside (never instead of) freshly verified live-repository evidence.
* Memory is tracked two ways:
    - per conversation (``conversation:<hash>``) so a single Teams thread's
      own history is available for follow-ups, and
    - centrally per cloud/repo-target (``centralized:<cloud>:<repo_target>``)
      so *any* user's prior Terrabot activity against the same live
      repository area is available to the next user who touches it — this is
      the "centralized changes by users" requirement.

Storage backends (checked in order, first available wins):
    1. Azure Table Storage — durable, shared across all Azure Functions
       workers/instances. Configured the same way as the existing Teams
       workflow-state table (``TERRABOT_STATE_STORAGE_CONNECTION_STRING`` /
       ``TERRABOT_STATE_STORAGE_ACCOUNT_URL``), so no new infrastructure is
       required in most deployments.
    2. A local JSON Lines cache file (the literal "cached file in between"
       requested for this feature). This is used automatically when Table
       Storage is not configured (for example local development or the CLI),
       and is also always available as a fast local read-through cache.

This module intentionally has no dependency on ``terrabot_service`` (or vice
versa at import time beyond a lazy call) so it stays easy to unit test and
cannot introduce an import cycle.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from azure.data.tables import TableServiceClient, UpdateMode
except ImportError:  # optional until azure-data-tables is deployed
    TableServiceClient = None
    UpdateMode = None

try:
    from azure.identity import DefaultAzureCredential
except ImportError:  # pragma: no cover - already a hard dependency in prod
    DefaultAzureCredential = None


LOGGER = logging.getLogger("terrabot.agent_memory")
LOGGER.setLevel(logging.INFO)

_TOPIC_STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "to", "in", "on", "of", "is",
    "are", "with", "using", "create", "add", "new", "please", "can",
    "you", "existing", "current", "this", "that", "terraform", "infra",
    "infrastructure", "set", "yet", "now", "should", "would", "could",
}

MEMORY_TABLE_NAME = (os.getenv("TERRABOT_AGENT_MEMORY_TABLE") or "TerrabotAgentMemory").strip()
MEMORY_TABLE_PARTITION = "agent-context-memory"

MAX_ENTRIES_PER_KEY = max(4, min(int(os.getenv("TERRABOT_AGENT_MEMORY_MAX_ENTRIES", "40")), 200))
MAX_FIELD_CHARS = max(200, min(int(os.getenv("TERRABOT_AGENT_MEMORY_MAX_FIELD_CHARS", "1500")), 8000))
MAX_CONTEXT_CHARS = max(1000, min(int(os.getenv("TERRABOT_AGENT_MEMORY_MAX_CONTEXT_CHARS", "12000")), 60000))
MEMORY_TTL_SECONDS = max(3600, int(os.getenv("TERRABOT_AGENT_MEMORY_TTL_SECONDS", str(90 * 24 * 3600))))

_DEFAULT_CACHE_FILE = Path(tempfile.gettempdir()) / "terrabot-agent-memory-cache.jsonl"
CACHE_FILE_PATH = Path(os.getenv("TERRABOT_AGENT_MEMORY_CACHE_FILE") or _DEFAULT_CACHE_FILE)

_LOCK = threading.RLock()
_TABLE_CLIENT = None
_TABLE_UNAVAILABLE = False

_MEMORY_CONTEXT_HEADER = (
    "TERRABOT AGENT MEMORY CACHE (auxiliary, long-term context): the entries "
    "below are prior Terrabot turns cached from earlier requests (this "
    "conversation and/or other users working on the same repository area), "
    "oldest first. Use them ONLY to avoid re-deriving context you already "
    "have, to keep answers consistent with prior decisions, and to resolve "
    "follow-ups. This cache is a performance and continuity aid, not a "
    "source of truth: live repository/GitHub evidence still governs any "
    "claim about current file contents, resource existence, or state, and "
    "must be re-verified before generating or committing code."
)


def _now() -> float:
    return time.time()


def _clean(value: Any, limit: int = MAX_FIELD_CHARS) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def _clean_list(values: Any, limit: int = 12, item_limit: int = 200) -> List[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    out: List[str] = []
    for value in values:
        text = _clean(value, item_limit)
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _conversation_key(conversation_id: str) -> str:
    conversation_id = str(conversation_id or "").strip()
    return f"conversation:{conversation_id}" if conversation_id else ""


def _centralized_key(cloud: str, repo_target: str) -> str:
    cloud = str(cloud or "").strip().lower()
    repo_target = str(repo_target or "").strip().lower()
    if not cloud and not repo_target:
        return ""
    return f"centralized:{cloud or 'unknown'}:{repo_target or 'unknown'}"


def _row_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Storage backend: Azure Table Storage (durable, centralized across workers)
# --------------------------------------------------------------------------

def _memory_table():
    global _TABLE_CLIENT, _TABLE_UNAVAILABLE
    if _TABLE_CLIENT is not None:
        return _TABLE_CLIENT
    if _TABLE_UNAVAILABLE or TableServiceClient is None:
        return None

    connection_string = (os.getenv("TERRABOT_STATE_STORAGE_CONNECTION_STRING") or "").strip()
    account_url = (
        os.getenv("TERRABOT_STATE_STORAGE_ACCOUNT_URL")
        or os.getenv("AzureWebJobsStorage__tableServiceUri")
        or ""
    ).strip().rstrip("/")
    account_name = (os.getenv("AzureWebJobsStorage__accountName") or "").strip()
    if not account_url and account_name:
        account_url = f"https://{account_name}.table.core.windows.net"

    try:
        if connection_string:
            service = TableServiceClient.from_connection_string(connection_string)
        elif account_url and DefaultAzureCredential is not None:
            service = TableServiceClient(endpoint=account_url, credential=DefaultAzureCredential())
        else:
            _TABLE_UNAVAILABLE = True
            return None
        _TABLE_CLIENT = service.create_table_if_not_exists(table_name=MEMORY_TABLE_NAME)
        LOGGER.info("Durable agent memory table is ready: table=%s", MEMORY_TABLE_NAME)
        return _TABLE_CLIENT
    except Exception:
        LOGGER.exception("Unable to initialize durable agent memory table; falling back to local cache file.")
        _TABLE_UNAVAILABLE = True
        return None


def _table_read_entries(key: str) -> List[dict]:
    table = _memory_table()
    if table is None:
        return []
    try:
        entity = table.get_entity(MEMORY_TABLE_PARTITION, _row_key(key))
    except Exception as exc:
        if "ResourceNotFound" not in type(exc).__name__:
            LOGGER.warning("Could not read durable agent memory key_hash=%s: %s", _row_key(key)[:12], exc)
        return []
    expires_at = float(entity.get("expires_at_epoch") or 0)
    if expires_at and _now() > expires_at:
        return []
    try:
        entries = json.loads(entity.get("entries_json") or "[]")
        return entries if isinstance(entries, list) else []
    except Exception:
        return []


def _table_write_entries(key: str, entries: List[dict]) -> bool:
    table = _memory_table()
    if table is None or UpdateMode is None:
        return False
    try:
        table.upsert_entity(
            entity={
                "PartitionKey": MEMORY_TABLE_PARTITION,
                "RowKey": _row_key(key),
                "memory_key": key,
                "entries_json": json.dumps(entries, ensure_ascii=False),
                "updated_at_epoch": _now(),
                "expires_at_epoch": _now() + MEMORY_TTL_SECONDS,
            },
            mode=UpdateMode.REPLACE,
        )
        return True
    except Exception:
        LOGGER.exception("Unable to persist durable agent memory key_hash=%s", _row_key(key)[:12])
        return False


# --------------------------------------------------------------------------
# Storage backend: local JSON Lines cache file (works everywhere, always on)
# --------------------------------------------------------------------------

def _file_read_entries(key: str) -> List[dict]:
    if not CACHE_FILE_PATH.exists():
        return []
    entries: List[dict] = []
    try:
        with CACHE_FILE_PATH.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except Exception:
                    continue
                if not isinstance(record, dict):
                    continue
                if record.get("memory_key") != key:
                    continue
                expires_at = float(record.get("expires_at_epoch") or 0)
                if expires_at and _now() > expires_at:
                    continue
                entries.append(record.get("entry") or {})
    except Exception:
        LOGGER.exception("Unable to read local agent memory cache file: %s", CACHE_FILE_PATH)
    return entries[-MAX_ENTRIES_PER_KEY:]


def _file_append_entry(key: str, entry: dict) -> None:
    try:
        CACHE_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "memory_key": key,
            "entry": entry,
            "expires_at_epoch": _now() + MEMORY_TTL_SECONDS,
        }
        with CACHE_FILE_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        LOGGER.exception("Unable to append to local agent memory cache file: %s", CACHE_FILE_PATH)


def _file_clear_key(key: str) -> None:
    """Remove every cached entry for ``key`` from the local cache file."""
    if not CACHE_FILE_PATH.exists():
        return
    try:
        kept_lines = []
        with CACHE_FILE_PATH.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    record = json.loads(stripped)
                except Exception:
                    continue
                if isinstance(record, dict) and record.get("memory_key") == key:
                    continue
                kept_lines.append(stripped)
        with CACHE_FILE_PATH.open("w", encoding="utf-8") as handle:
            for line in kept_lines:
                handle.write(line + "\n")
    except Exception:
        LOGGER.exception("Unable to clear local agent memory cache entries for key_hash=%s", _row_key(key)[:12])


def _compact_file_if_needed(key: str) -> None:
    """Best-effort trim of the local cache file once it grows large.

    This is intentionally simple (rewrite-on-threshold) since the file is a
    fast local cache, not the durable source of truth when Table Storage is
    configured.
    """
    try:
        if not CACHE_FILE_PATH.exists() or CACHE_FILE_PATH.stat().st_size < 5_000_000:
            return
        by_key: Dict[str, List[dict]] = {}
        with CACHE_FILE_PATH.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except Exception:
                    continue
                if not isinstance(record, dict):
                    continue
                mem_key = str(record.get("memory_key") or "")
                by_key.setdefault(mem_key, []).append(record)
        with CACHE_FILE_PATH.open("w", encoding="utf-8") as handle:
            for mem_key, records in by_key.items():
                for record in records[-MAX_ENTRIES_PER_KEY:]:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        LOGGER.exception("Unable to compact local agent memory cache file: %s", CACHE_FILE_PATH)


# --------------------------------------------------------------------------
# Unified read/write API
# --------------------------------------------------------------------------

def _read_entries(key: str) -> List[dict]:
    if not key:
        return []
    table_entries = _table_read_entries(key)
    if table_entries:
        return table_entries
    return _file_read_entries(key)


def _append_entry(key: str, entry: dict) -> None:
    if not key:
        return
    with _LOCK:
        entries = _read_entries(key)
        entries.append(entry)
        entries = entries[-MAX_ENTRIES_PER_KEY:]
        wrote_durable = _table_write_entries(key, entries)
        # The local file is always updated too so a single append-only cache
        # file (per the requirement) reflects every request even when Table
        # Storage is unavailable, misconfigured, or a fresh deployment.
        _file_append_entry(key, entry)
        if not wrote_durable:
            _compact_file_if_needed(key)


def extract_topic_tags(*texts: str, limit: int = 12) -> List[str]:
    """Derive short topic tags (e.g. "waf", "mcp") from prompt/response text.

    Used so a resolved concept — for example "mcp waf rules" resolving to a
    specific parameter — can be retrieved by topical relevance later, not
    only by recency. Pure/deterministic so it is easy to unit test.
    """
    tags: List[str] = []
    seen: set = set()
    for text in texts:
        for token in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", str(text or "").lower()):
            if token in _TOPIC_STOPWORDS or token in seen:
                continue
            seen.add(token)
            tags.append(token)
            if len(tags) >= limit:
                return tags
    return tags


def build_memory_entry(
    *,
    prompt: str = "",
    cloud: str = "",
    repo_target: str = "",
    workflow: str = "",
    requester: str = "",
    source: str = "",
    files_searched: Optional[List[str]] = None,
    context_retrieved_summary: str = "",
    code_generated_summary: str = "",
    response_summary: str = "",
    topic_tags: Optional[List[str]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> dict:
    """Build the structured record persisted for one agent turn."""
    resolved_tags = list(topic_tags) if topic_tags else extract_topic_tags(prompt, response_summary)
    entry = {
        "at": _now(),
        "prompt": _clean(prompt, 800),
        "cloud": str(cloud or "").strip().lower(),
        "repo_target": str(repo_target or "").strip().lower(),
        "workflow": str(workflow or "").strip(),
        "requester": _clean(requester, 120),
        "source": str(source or "").strip() or "teams",
        "files_searched": _clean_list(files_searched, limit=15, item_limit=200),
        "context_retrieved_summary": _clean(context_retrieved_summary, MAX_FIELD_CHARS),
        "code_generated_summary": _clean(code_generated_summary, MAX_FIELD_CHARS),
        "response_summary": _clean(response_summary, MAX_FIELD_CHARS),
        "topic_tags": _clean_list(resolved_tags, limit=12, item_limit=48),
    }
    if isinstance(extra, dict):
        entry["extra"] = {str(k): _clean(v, 300) for k, v in list(extra.items())[:10]}
    return entry


def record_agent_turn(
    *,
    conversation_id: str = "",
    cloud: str = "",
    repo_target: str = "",
    workflow: str = "",
    requester: str = "",
    source: str = "",
    prompt: str = "",
    files_searched: Optional[List[str]] = None,
    context_retrieved_summary: str = "",
    code_generated_summary: str = "",
    response_summary: str = "",
    topic_tags: Optional[List[str]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> dict:
    """Append one agent turn to both the conversation and centralized memory.

    Returns the stored entry. Safe to call even when no durable storage is
    configured — the local cache file always receives the entry.
    """
    entry = build_memory_entry(
        prompt=prompt,
        cloud=cloud,
        repo_target=repo_target,
        workflow=workflow,
        requester=requester,
        source=source,
        files_searched=files_searched,
        context_retrieved_summary=context_retrieved_summary,
        code_generated_summary=code_generated_summary,
        response_summary=response_summary,
        topic_tags=topic_tags,
        extra=extra,
    )

    conv_key = _conversation_key(conversation_id)
    central_key = _centralized_key(cloud, repo_target)

    if conv_key:
        try:
            _append_entry(conv_key, entry)
        except Exception:
            LOGGER.exception("agent_memory: unable to record conversation turn key_hash=%s", _row_key(conv_key)[:12])

    if central_key:
        try:
            _append_entry(central_key, entry)
        except Exception:
            LOGGER.exception("agent_memory: unable to record centralized turn key_hash=%s", _row_key(central_key)[:12])

    LOGGER.info(
        "agent_memory: recorded turn conversation=%s cloud=%s repo_target=%s topic_tags=%s "
        "prompt_chars=%s files_searched=%s cache_file=%s",
        _row_key(conv_key)[:12] if conv_key else "",
        cloud or "",
        repo_target or "",
        entry.get("topic_tags") or [],
        len(entry.get("prompt") or ""),
        len(entry.get("files_searched") or []),
        str(CACHE_FILE_PATH),
    )

    return entry


def start_conversation_memory(
    conversation_id: str,
    *,
    requester: str = "",
    source: str = "teams",
    reason: str = "new_conversation",
    previous_conversation_id: str = "",
) -> dict:
    """Create a durable row for a newly-started logical conversation.

    A Teams transport thread can host many logical Terrabot conversations.
    This marker makes each logical conversation visible as its own Azure Table
    entity immediately, even before the first Foundry turn is recorded.  Old
    conversation rows are intentionally preserved for historical retrieval.
    """
    entry = build_memory_entry(
        workflow="conversation_started",
        requester=requester,
        source=source,
        response_summary=f"New Terrabot conversation started ({reason}).",
        topic_tags=["conversation", "started", reason],
        extra={
            "event": "conversation_started",
            "reason": reason,
            "previous_conversation_id": previous_conversation_id,
        },
    )
    key = _conversation_key(conversation_id)
    if key:
        try:
            _append_entry(key, entry)
            LOGGER.info(
                "agent_memory: started logical conversation key_hash=%s reason=%s previous_present=%s",
                _row_key(key)[:12],
                reason,
                bool(previous_conversation_id),
            )
        except Exception:
            LOGGER.exception(
                "agent_memory: unable to start logical conversation key_hash=%s",
                _row_key(key)[:12],
            )
    return entry


def record_agent_response(
    conversation_id: str,
    response_summary: str,
    *,
    source: str = "teams",
    workflow: str = "rendered_response",
) -> dict:
    """Persist one delivered Terrabot response for conversation continuity.

    Unlike :func:`record_agent_turn`, this intentionally writes only to the
    per-conversation key. Rendered Teams responses can contain branch-choice,
    clarification, Jira, PR, or other transport messages that are useful to
    the same conversation later but must not pollute the cross-user
    centralized repository memory.
    """
    entry = build_memory_entry(
        workflow=workflow,
        source=source,
        response_summary=response_summary,
        topic_tags=extract_topic_tags(response_summary),
    )
    key = _conversation_key(conversation_id)
    if key:
        try:
            _append_entry(key, entry)
        except Exception:
            LOGGER.exception(
                "agent_memory: unable to record delivered response key_hash=%s",
                _row_key(key)[:12],
            )
    return entry


def _format_entries(entries: List[dict], max_chars: int) -> str:
    if not entries:
        return ""
    lines: List[str] = []
    used = 0
    for entry in reversed(entries):
        pieces = []
        prompt = entry.get("prompt")
        if prompt:
            pieces.append(f"prompt: {prompt}")
        files_searched = entry.get("files_searched") or []
        if files_searched:
            pieces.append("files_searched: " + ", ".join(files_searched[:8]))
        context_summary = entry.get("context_retrieved_summary")
        if context_summary:
            pieces.append(f"context_retrieved: {context_summary}")
        code_summary = entry.get("code_generated_summary")
        if code_summary:
            pieces.append(f"code_generated: {code_summary}")
        response_summary = entry.get("response_summary")
        if response_summary:
            pieces.append(f"response: {response_summary}")
        if not pieces:
            continue
        line = "- " + " | ".join(pieces)
        if used + len(line) + 1 > max_chars:
            break
        lines.append(line)
        used += len(line) + 1
    if not lines:
        return ""
    lines.reverse()
    return "\n".join(lines)


def _rank_entries_by_relevance(entries: List[dict], prompt: str) -> List[dict]:
    """Reorder cached entries so ones topically relevant to ``prompt`` are
    considered first, falling back to recency when nothing is relevant.

    This is what lets "what are the mcp waf rules?" retrieve an earlier
    "disable mcp waf rules" resolution even when many unrelated turns were
    cached in between, instead of only ever surfacing the most recent N
    turns regardless of topic.
    """
    if not entries:
        return []
    prompt_tags = set(extract_topic_tags(prompt))
    if not prompt_tags:
        return list(entries)

    def _score(entry: dict) -> int:
        entry_tags = set(entry.get("topic_tags") or [])
        return len(entry_tags & prompt_tags)

    scored = [(index, _score(entry), entry) for index, entry in enumerate(entries)]
    # Stable: relevance first (descending), recency (original/insertion
    # order, oldest-first) as the tiebreaker so _format_entries' "reversed()"
    # rendering still shows the most relevant-and-recent entry last/closest
    # to the live prompt.
    scored.sort(key=lambda item: (-item[1], item[0]))
    ranked = [entry for _index, score, entry in scored if score > 0]
    if not ranked:
        return list(entries)
    # Keep any non-matching entries after the relevant ones so context is
    # never silently smaller than the recency-only behavior would provide.
    relevant_ids = {id(entry) for entry in ranked}
    ranked.extend(entry for entry in entries if id(entry) not in relevant_ids)
    return ranked


def get_conversation_memory_context(
    conversation_id: str,
    max_entries: int = 8,
    max_chars: int = MAX_CONTEXT_CHARS,
    prompt: str = "",
) -> str:
    key = _conversation_key(conversation_id)
    if not key:
        return ""
    entries = _read_entries(key)
    if prompt:
        entries = _rank_entries_by_relevance(entries, prompt)
    entries = entries[-max_entries:] if not prompt else entries[:max_entries]
    block = _format_entries(entries, max_chars)
    LOGGER.info(
        "agent_memory: conversation context lookup key_hash=%s entries_found=%s relevance_ranked=%s chars=%s",
        _row_key(key)[:12], len(entries), bool(prompt), len(block),
    )
    return block


def get_centralized_memory_context(
    cloud: str,
    repo_target: str,
    max_entries: int = 6,
    max_chars: int = MAX_CONTEXT_CHARS,
    prompt: str = "",
) -> str:
    key = _centralized_key(cloud, repo_target)
    if not key:
        return ""
    entries = _read_entries(key)
    if prompt:
        entries = _rank_entries_by_relevance(entries, prompt)
    entries = entries[-max_entries:] if not prompt else entries[:max_entries]
    block = _format_entries(entries, max_chars)
    LOGGER.info(
        "agent_memory: centralized context lookup cloud=%s repo_target=%s entries_found=%s "
        "relevance_ranked=%s chars=%s",
        cloud or "", repo_target or "", len(entries), bool(prompt), len(block),
    )
    return block


def get_combined_memory_context(
    *,
    conversation_id: str = "",
    cloud: str = "",
    repo_target: str = "",
    max_chars: int = MAX_CONTEXT_CHARS,
    prompt: str = "",
) -> str:
    """Build the full memory block to attach to an agent request.

    Combines this conversation's own history with the centralized history
    for the same cloud/repo-target (other users' cached activity), bounded
    to ``max_chars`` total. Returns "" when there is nothing cached. When
    ``prompt`` is supplied, entries are ranked by topical relevance to it
    first (see :func:`_rank_entries_by_relevance`) rather than only recency,
    so a later request about the same topic (e.g. "mcp waf rules") can
    retrieve an earlier resolution even if other turns happened in between.
    """
    half = max(500, max_chars // 2)
    conversation_block = get_conversation_memory_context(conversation_id, max_chars=half, prompt=prompt)
    centralized_block = get_centralized_memory_context(
        cloud, repo_target, max_chars=max_chars - half, prompt=prompt
    )

    sections = []
    if conversation_block:
        sections.append("This conversation's prior cached turns:\n" + conversation_block)
    if centralized_block:
        sections.append(
            f"Other cached turns for cloud={cloud or 'unknown'} repo_target={repo_target or 'unknown'}:\n"
            + centralized_block
        )
    if not sections:
        return ""
    return _MEMORY_CONTEXT_HEADER + "\n\n" + "\n\n".join(sections)


def clear_conversation_memory(conversation_id: str) -> None:
    """Drop cached memory for one conversation (used by the `/clear` reset)."""
    key = _conversation_key(conversation_id)
    if not key:
        return
    with _LOCK:
        _table_write_entries(key, [])
        _file_clear_key(key)
