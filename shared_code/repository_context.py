"""Centralized repository-level context for Terrabot.

The repository context layer stores only durable repository knowledge.  It does
not store conversation transcripts or conversation summaries.  Azure AI Search
is used for both persistence and retrieval so the context is shared by every
Terrabot user working on the same repository and uses the project's existing
search/embedding architecture.

Live repository code remains the ultimate source of truth.  Every write must be
validated against repository evidence before it is indexed.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional

from shared_code.settings_loader import load_local_settings

load_local_settings()

LOGGER = logging.getLogger("terrabot.repository_context")
LOGGER.setLevel(logging.INFO)

try:  # optional at import time so unit tests can run without Azure SDKs
    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents import SearchClient
    from azure.search.documents.indexes import SearchIndexClient
    from azure.search.documents.indexes.models import (
        HnswAlgorithmConfiguration,
        SearchField,
        SearchFieldDataType,
        SearchIndex,
        SearchableField,
        SimpleField,
        VectorSearch,
        VectorSearchProfile,
    )
    from azure.search.documents.models import VectorizedQuery
except ImportError:  # pragma: no cover - exercised only in minimal local envs
    AzureKeyCredential = None
    SearchClient = None
    SearchIndexClient = None
    SearchIndex = None
    SearchField = None
    SearchFieldDataType = None
    SearchableField = None
    SimpleField = None
    VectorSearch = None
    HnswAlgorithmConfiguration = None
    VectorSearchProfile = None
    VectorizedQuery = None


AZURE_SEARCH_ENDPOINT = (os.getenv("AZURE_SEARCH_ENDPOINT") or "").strip().rstrip("/")
AZURE_SEARCH_KEY = (os.getenv("AZURE_SEARCH_KEY") or "").strip()
REPOSITORY_CONTEXT_INDEX_NAME = (
    os.getenv("AZURE_SEARCH_REPOSITORY_CONTEXT_INDEX_NAME")
    or "terrabot-repository-context"
).strip()
EMBEDDING_DIMENSIONS = int(os.getenv("AZURE_OPENAI_EMBEDDING_DIMENSIONS", "1536"))
REPOSITORY_CONTEXT_ENABLED = (
    os.getenv("TERRABOT_REPOSITORY_CONTEXT_ENABLED", "true").strip().lower()
    not in {"0", "false", "no", "off"}
)
AUTO_CREATE_INDEX = (
    os.getenv("TERRABOT_REPOSITORY_CONTEXT_AUTO_CREATE_INDEX", "true").strip().lower()
    not in {"0", "false", "no", "off"}
)
MIN_CONFIDENCE = float(os.getenv("TERRABOT_REPOSITORY_CONTEXT_MIN_CONFIDENCE", "0.75"))
DEFAULT_TOP_K = max(1, min(int(os.getenv("TERRABOT_REPOSITORY_CONTEXT_TOP_K", "8")), 25))
MAX_CONTEXT_CHARS = max(
    1000,
    min(int(os.getenv("TERRABOT_REPOSITORY_CONTEXT_MAX_CHARS", "12000")), 50000),
)

DOC_TYPE = "repository_context"
ACTIVE_STATUSES = {"active", "conflicted"}
ALLOWED_CATEGORIES = {
    "architecture_decision",
    "implementation_decision",
    "coding_convention",
    "repository_constraint",
    "component_relationship",
    "workflow_procedure",
    "api_integration_behavior",
    "resolved_clarification",
    "repository_fact",
}

_INDEX_READY = False
_SEARCH_CLIENT = None
# Process-local synchronization prevents two concurrent requests in the same
# Function worker from both attempting index initialization. Azure Functions can
# still run multiple workers/instances, so ensure_repository_context_index also
# handles cross-instance create/update conflicts below.
_INDEX_LOCK = threading.Lock()
_INDEX_OPERATION_RETRY_DELAYS = (0.2, 0.4, 0.8, 1.5, 2.5, 4.0)


def _diag(event: str, level: str = "info", **fields: Any) -> None:
    """Emit Function-App-visible structured diagnostics.

    WARNING is intentional: Azure Functions deployments commonly filter INFO
    from application log streams.  The semantic level remains a field in the
    message while WARNING ensures the line is visible.
    """
    parts = [f"event=repository_context_{event}", f"level={level}"]
    for key, value in fields.items():
        text = str(value if value is not None else "").replace("\n", " ")
        if len(text) > 500:
            text = text[:497] + "..."
        parts.append(f"{key}={text}")
    message = "[TerrabotDiag] " + " ".join(parts)
    LOGGER.warning(message)
    try:
        print(message, flush=True)
    except Exception:
        pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value or "")


def _normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalize_repo_part(value: str) -> str:
    return str(value or "").strip().removesuffix(".git")


def _normalize_path(value: str) -> str:
    raw = str(value or "").replace("\\", "/").strip().lstrip("/")
    parts = [part for part in raw.split("/") if part and part not in {".", ".."}]
    return "/".join(parts)


def _repo_full_name(owner: str, repo: str) -> str:
    owner = _normalize_repo_part(owner)
    repo = _normalize_repo_part(repo)
    if not owner or not repo:
        raise ValueError("repo_owner and repo_name are required.")
    return f"{owner}/{repo}"


def _hash_text(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _identity_key(repo_full_name: str, category: str, subject: str, scope: str) -> str:
    raw = "::".join(
        [
            repo_full_name.lower(),
            _normalize_space(category).lower(),
            _normalize_space(subject).lower(),
            _normalize_space(scope).lower(),
        ]
    )
    return _hash_text(raw)


def _statement_key(statement: str) -> str:
    text = _normalize_space(statement).rstrip(".").lower()
    return _hash_text(text)


def _safe_odata(value: str) -> str:
    return str(value or "").replace("'", "''")


def _redact_sensitive_literals(value: str) -> str:
    text = str(value or "")
    patterns = [
        r'(?i)(password\s*=\s*)"[^"]+"',
        r'(?i)(client_secret\s*=\s*)"[^"]+"',
        r'(?i)(api[_-]?key\s*=\s*)"[^"]+"',
        r'(?i)(access[_-]?token\s*=\s*)"[^"]+"',
        r'(?i)(secret[_-]?key\s*=\s*)"[^"]+"',
        r'(?i)(connection_string\s*=\s*)"[^"]+"',
    ]
    for pattern in patterns:
        text = re.sub(pattern, r'\1"<redacted>"', text)
    return text


def _contains_conversation_summary_language(statement: str) -> bool:
    lower = _normalize_space(statement).lower()
    return any(
        marker in lower
        for marker in (
            "the user asked",
            "the user said",
            "in this conversation",
            "in this chat",
            "we discussed",
            "terrabot responded",
            "the assistant",
        )
    )


@dataclass
class RepositoryContextEvidence:
    path: str
    excerpt: str
    reason: str = ""


@dataclass
class RepositoryContextCandidate:
    category: str
    subject: str
    statement: str
    scope: str = "repository"
    confidence: float = 0.0
    evidence: List[RepositoryContextEvidence] = field(default_factory=list)
    validation_summary: str = ""


@dataclass
class RepositoryContextRecord:
    id: str
    repo_owner: str
    repo_name: str
    repo_full_name: str
    identity_key: str
    statement_key: str
    category: str
    subject: str
    scope: str
    statement: str
    evidence_paths: List[str]
    evidence_json: str
    evidence_commit_sha: str
    evidence_branch: str
    evidence_hash: str
    status: str
    confidence: float
    validation_status: str
    validation_summary: str
    source_task_hash: str
    created_at: str
    updated_at: str
    supersedes_id: str = ""
    conflict_with_ids: List[str] = field(default_factory=list)

    def to_public_dict(self, *, current_commit_sha: str = "") -> Dict[str, Any]:
        data = asdict(self)
        stale = bool(
            current_commit_sha
            and self.evidence_commit_sha
            and current_commit_sha != self.evidence_commit_sha
        )
        data["stale"] = stale
        data["current_commit_sha"] = current_commit_sha or ""
        try:
            data["evidence"] = json.loads(self.evidence_json or "[]")
        except Exception:
            data["evidence"] = []
        return data


RepositoryEvidenceFetcher = Callable[[str, str, str, str], Optional[str]]


def repository_context_tool_schemas() -> List[Dict[str, Any]]:
    """Function-tool compatible schemas documented/exposed to Foundry."""
    evidence_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "path": {"type": "string"},
            "excerpt": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["path", "excerpt"],
    }
    candidate_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "category": {"type": "string", "enum": sorted(ALLOWED_CATEGORIES)},
            "subject": {"type": "string"},
            "scope": {"type": "string"},
            "statement": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "evidence": {"type": "array", "items": evidence_schema, "minItems": 1},
            "validation_summary": {"type": "string"},
        },
        "required": ["category", "subject", "statement", "confidence", "evidence"],
    }
    return [
        {
            "type": "function",
            "name": "search_repository_context",
            "description": "Search durable shared context for one repository before repository work. Live code remains authoritative.",
            "strict": True,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "repo_owner": {"type": "string"},
                    "repo_name": {"type": "string"},
                    "query": {"type": "string"},
                    "current_commit_sha": {"type": "string"},
                    "top_k": {"type": "integer", "minimum": 1, "maximum": 25},
                },
                "required": ["repo_owner", "repo_name", "query"],
            },
        },
        {
            "type": "function",
            "name": "add_repository_context",
            "description": "Add one evidence-validated durable repository conclusion. Never use this for conversation history or task summaries.",
            "strict": True,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "repo_owner": {"type": "string"},
                    "repo_name": {"type": "string"},
                    "evidence_commit_sha": {"type": "string"},
                    "evidence_branch": {"type": "string"},
                    "source_task_hash": {"type": "string"},
                    "candidate": candidate_schema,
                },
                "required": ["repo_owner", "repo_name", "evidence_commit_sha", "candidate"],
            },
        },
        {
            "type": "function",
            "name": "update_repository_context",
            "description": "Create a new evidence-validated version of an existing context record while preserving the superseded record.",
            "strict": True,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "context_id": {"type": "string"},
                    "repo_owner": {"type": "string"},
                    "repo_name": {"type": "string"},
                    "evidence_commit_sha": {"type": "string"},
                    "evidence_branch": {"type": "string"},
                    "source_task_hash": {"type": "string"},
                    "candidate": candidate_schema,
                },
                "required": ["context_id", "repo_owner", "repo_name", "evidence_commit_sha", "candidate"],
            },
        },
        {
            "type": "function",
            "name": "invalidate_repository_context",
            "description": "Invalidate a durable context record without deleting history when repository evidence no longer supports it.",
            "strict": True,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "context_id": {"type": "string"},
                    "reason": {"type": "string"},
                    "current_commit_sha": {"type": "string"},
                },
                "required": ["context_id", "reason"],
            },
        },
    ]


FOUNDRY_REPOSITORY_CONTEXT_TOOL_SCHEMAS = repository_context_tool_schemas()


def _validate_sdk_available() -> None:
    if not REPOSITORY_CONTEXT_ENABLED:
        raise RuntimeError("Repository context is disabled by TERRABOT_REPOSITORY_CONTEXT_ENABLED.")
    if SearchClient is None or SearchIndexClient is None or AzureKeyCredential is None:
        raise RuntimeError(
            "azure-search-documents is required for centralized repository context."
        )
    missing = []
    if not AZURE_SEARCH_ENDPOINT:
        missing.append("AZURE_SEARCH_ENDPOINT")
    if not AZURE_SEARCH_KEY:
        missing.append("AZURE_SEARCH_KEY")
    if not REPOSITORY_CONTEXT_INDEX_NAME:
        missing.append("AZURE_SEARCH_REPOSITORY_CONTEXT_INDEX_NAME")
    if missing:
        raise RuntimeError("Missing repository-context setting(s): " + ", ".join(missing))


def build_repository_context_index():
    _validate_sdk_available()
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
        SimpleField(name="doc_type", type=SearchFieldDataType.String, filterable=True, retrievable=True),
        SearchableField(name="repo_owner", type=SearchFieldDataType.String, filterable=True, retrievable=True),
        SearchableField(name="repo_name", type=SearchFieldDataType.String, filterable=True, retrievable=True),
        SearchableField(name="repo_full_name", type=SearchFieldDataType.String, filterable=True, retrievable=True),
        SimpleField(name="identity_key", type=SearchFieldDataType.String, filterable=True, retrievable=True),
        SimpleField(name="statement_key", type=SearchFieldDataType.String, filterable=True, retrievable=True),
        SearchableField(name="category", type=SearchFieldDataType.String, filterable=True, retrievable=True),
        SearchableField(name="subject", type=SearchFieldDataType.String, filterable=True, retrievable=True),
        SearchableField(name="scope", type=SearchFieldDataType.String, filterable=True, retrievable=True),
        SearchableField(name="statement", type=SearchFieldDataType.String, retrievable=True),
        SearchField(
            name="evidence_paths",
            type=SearchFieldDataType.Collection(SearchFieldDataType.String),
            searchable=True,
            filterable=True,
            retrievable=True,
        ),
        SearchableField(name="evidence_json", type=SearchFieldDataType.String, retrievable=True),
        SimpleField(name="evidence_commit_sha", type=SearchFieldDataType.String, filterable=True, retrievable=True),
        SimpleField(name="evidence_branch", type=SearchFieldDataType.String, filterable=True, retrievable=True),
        SimpleField(name="evidence_hash", type=SearchFieldDataType.String, filterable=True, retrievable=True),
        SimpleField(name="status", type=SearchFieldDataType.String, filterable=True, retrievable=True),
        SimpleField(name="confidence", type=SearchFieldDataType.Double, filterable=True, sortable=True, retrievable=True),
        SimpleField(name="validation_status", type=SearchFieldDataType.String, filterable=True, retrievable=True),
        SearchableField(name="validation_summary", type=SearchFieldDataType.String, retrievable=True),
        SimpleField(name="source_task_hash", type=SearchFieldDataType.String, filterable=True, retrievable=True),
        SimpleField(name="created_at", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True, retrievable=True),
        SimpleField(name="updated_at", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True, retrievable=True),
        SimpleField(name="supersedes_id", type=SearchFieldDataType.String, filterable=True, retrievable=True),
        SearchField(
            name="conflict_with_ids",
            type=SearchFieldDataType.Collection(SearchFieldDataType.String),
            filterable=True,
            retrievable=True,
        ),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=EMBEDDING_DIMENSIONS,
            vector_search_profile_name="repository-context-vector-profile",
            hidden=True,
        ),
    ]
    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="repository-context-hnsw")],
        profiles=[
            VectorSearchProfile(
                name="repository-context-vector-profile",
                algorithm_configuration_name="repository-context-hnsw",
            )
        ],
    )
    return SearchIndex(
        name=REPOSITORY_CONTEXT_INDEX_NAME,
        fields=fields,
        vector_search=vector_search,
    )


def _search_index_exception_status(exc: Exception) -> int:
    """Best-effort HTTP status extraction without depending on Azure exception classes."""
    for attr in ("status_code", "status"):
        value = getattr(exc, attr, None)
        try:
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            pass
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0


def _search_index_exception_code(exc: Exception) -> str:
    """Return the Azure Search service error code when the SDK exposes one."""
    error = getattr(exc, "error", None)
    code = getattr(error, "code", None)
    if code:
        return str(code)
    code = getattr(exc, "error_code", None)
    return str(code or "")


def _is_repository_context_index_not_found(exc: Exception) -> bool:
    status = _search_index_exception_status(exc)
    code = _search_index_exception_code(exc).strip().lower()
    text = str(exc or "").lower()
    return (
        status == 404
        or code in {"resourcenotfound", "indexnotfound"}
        or ("index" in text and "not found" in text)
    )


def _is_repository_context_index_concurrency_conflict(exc: Exception) -> bool:
    """Recognize transient Azure AI Search control-plane conflicts.

    Azure Search rejects simultaneous index create/update operations with
    OperationNotAllowed / ResourceCreationConcurrencyConflict. These are
    transient coordination failures, not repository-context failures.
    """
    status = _search_index_exception_status(exc)
    code = _search_index_exception_code(exc).strip().lower()
    text = f"{code} {exc}".lower()
    markers = (
        "operationnotallowed",
        "resourcecreationconcurrencyconflict",
        "concurrent operation",
        "already exists",
        "resourcealreadyexists",
    )
    return status in {409, 429} or any(marker in text for marker in markers)


def _repository_context_index_exists(client: Any) -> bool:
    try:
        client.get_index(REPOSITORY_CONTEXT_INDEX_NAME)
        return True
    except Exception as exc:
        if _is_repository_context_index_not_found(exc):
            return False
        raise


def _wait_for_repository_context_index(client: Any) -> bool:
    """Wait for another Function worker/instance to finish creating the index."""
    for delay in _INDEX_OPERATION_RETRY_DELAYS:
        time.sleep(delay)
        try:
            if _repository_context_index_exists(client):
                return True
        except Exception as exc:
            if _is_repository_context_index_concurrency_conflict(exc):
                continue
            raise
    return False


def _force_create_or_update_repository_context_index(client: Any, index: Any) -> None:
    """Admin/schema-migration path with bounded retry for concurrent updates."""
    last_error: Exception | None = None
    attempts = len(_INDEX_OPERATION_RETRY_DELAYS) + 1
    for attempt in range(1, attempts + 1):
        try:
            client.create_or_update_index(index)
            return
        except Exception as exc:
            if not _is_repository_context_index_concurrency_conflict(exc):
                raise
            last_error = exc
            if attempt >= attempts:
                break
            delay = _INDEX_OPERATION_RETRY_DELAYS[attempt - 1]
            _diag(
                "index_update_concurrency_retry",
                level="warning",
                index=REPOSITORY_CONTEXT_INDEX_NAME,
                attempt=f"{attempt}/{attempts}",
                delay_seconds=delay,
                error=exc,
            )
            time.sleep(delay)
    if last_error is not None:
        raise last_error


def ensure_repository_context_index(force: bool = False) -> str:
    """Ensure the repository-context index exists without racing on cold start.

    Normal runtime initialization is read-before-create: if the index already
    exists, no schema update is issued. This is critical in a scaled Azure
    Function because _INDEX_READY is process-local and multiple workers can cold
    start concurrently.

    ``force=True`` preserves the existing explicit schema-update behavior used by
    create_search_index.py, but adds bounded retry for concurrent control-plane
    operations.
    """
    global _INDEX_READY
    _validate_sdk_available()
    if _INDEX_READY and not force:
        return REPOSITORY_CONTEXT_INDEX_NAME
    if not AUTO_CREATE_INDEX and not force:
        return REPOSITORY_CONTEXT_INDEX_NAME

    with _INDEX_LOCK:
        # Another request in this worker may have completed initialization while
        # this request waited for the lock.
        if _INDEX_READY and not force:
            return REPOSITORY_CONTEXT_INDEX_NAME

        client = SearchIndexClient(
            endpoint=AZURE_SEARCH_ENDPOINT,
            credential=AzureKeyCredential(AZURE_SEARCH_KEY),
        )

        if not force:
            # Runtime requests must never update an existing index schema. They
            # only create it when it is genuinely absent.
            try:
                index_exists = _repository_context_index_exists(client)
            except Exception as exc:
                if not _is_repository_context_index_concurrency_conflict(exc):
                    raise
                _diag(
                    "index_probe_concurrency_wait",
                    level="warning",
                    index=REPOSITORY_CONTEXT_INDEX_NAME,
                    error=exc,
                )
                if not _wait_for_repository_context_index(client):
                    raise
                index_exists = True

            if index_exists:
                _INDEX_READY = True
                _diag(
                    "index_ready",
                    index=REPOSITORY_CONTEXT_INDEX_NAME,
                    action="existing",
                )
                return REPOSITORY_CONTEXT_INDEX_NAME

            index = build_repository_context_index()
            try:
                client.create_index(index)
                action = "created"
            except Exception as exc:
                if not _is_repository_context_index_concurrency_conflict(exc):
                    raise
                _diag(
                    "index_create_concurrency_wait",
                    level="warning",
                    index=REPOSITORY_CONTEXT_INDEX_NAME,
                    error=exc,
                )
                if not _wait_for_repository_context_index(client):
                    raise
                action = "created_by_concurrent_worker"

            _INDEX_READY = True
            _diag(
                "index_ready",
                index=REPOSITORY_CONTEXT_INDEX_NAME,
                action=action,
            )
            return REPOSITORY_CONTEXT_INDEX_NAME

        # Explicit deployment/admin path: preserve schema reconciliation while
        # tolerating another concurrent index operation.
        index = build_repository_context_index()
        _force_create_or_update_repository_context_index(client, index)
        _INDEX_READY = True
        _diag(
            "index_ready",
            index=REPOSITORY_CONTEXT_INDEX_NAME,
            action="force_create_or_update",
        )
        return REPOSITORY_CONTEXT_INDEX_NAME


def get_repository_context_search_client():
    global _SEARCH_CLIENT
    _validate_sdk_available()
    if _SEARCH_CLIENT is not None:
        return _SEARCH_CLIENT
    if AUTO_CREATE_INDEX:
        ensure_repository_context_index()
    _SEARCH_CLIENT = SearchClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        index_name=REPOSITORY_CONTEXT_INDEX_NAME,
        credential=AzureKeyCredential(AZURE_SEARCH_KEY),
    )
    return _SEARCH_CLIENT


def _embedding(text: str) -> List[float]:
    # Reuse the project's existing Azure OpenAI embedding client/settings.
    from shared_code.index_loader import get_embeddings

    vectors = get_embeddings([text])
    if not vectors:
        raise RuntimeError("Azure OpenAI returned no repository-context embedding.")
    return vectors[0]


def _embedding_text(record: RepositoryContextRecord | RepositoryContextCandidate, repo_full_name: str = "") -> str:
    if isinstance(record, RepositoryContextRecord):
        repo_full_name = record.repo_full_name
        category = record.category
        subject = record.subject
        scope = record.scope
        statement = record.statement
        validation_summary = record.validation_summary
    else:
        category = record.category
        subject = record.subject
        scope = record.scope
        statement = record.statement
        validation_summary = record.validation_summary
    return "\n".join(
        [
            f"repository: {repo_full_name}",
            f"category: {category}",
            f"subject: {subject}",
            f"scope: {scope}",
            f"statement: {statement}",
            f"validation: {validation_summary}",
        ]
    ).strip()


def _record_to_search_document(record: RepositoryContextRecord) -> Dict[str, Any]:
    return {
        "id": record.id,
        "doc_type": DOC_TYPE,
        "repo_owner": record.repo_owner,
        "repo_name": record.repo_name,
        "repo_full_name": record.repo_full_name,
        "identity_key": record.identity_key,
        "statement_key": record.statement_key,
        "category": record.category,
        "subject": record.subject,
        "scope": record.scope,
        "statement": record.statement,
        "evidence_paths": record.evidence_paths,
        "evidence_json": record.evidence_json,
        "evidence_commit_sha": record.evidence_commit_sha,
        "evidence_branch": record.evidence_branch,
        "evidence_hash": record.evidence_hash,
        "status": record.status,
        "confidence": float(record.confidence),
        "validation_status": record.validation_status,
        "validation_summary": record.validation_summary,
        "source_task_hash": record.source_task_hash,
        "created_at": datetime.fromisoformat(record.created_at.replace("Z", "+00:00")),
        "updated_at": datetime.fromisoformat(record.updated_at.replace("Z", "+00:00")),
        "supersedes_id": record.supersedes_id,
        "conflict_with_ids": record.conflict_with_ids,
        "content_vector": _embedding(_embedding_text(record)),
    }


def _search_doc_to_record(doc: Dict[str, Any]) -> RepositoryContextRecord:
    return RepositoryContextRecord(
        id=str(doc.get("id") or ""),
        repo_owner=str(doc.get("repo_owner") or ""),
        repo_name=str(doc.get("repo_name") or ""),
        repo_full_name=str(doc.get("repo_full_name") or ""),
        identity_key=str(doc.get("identity_key") or ""),
        statement_key=str(doc.get("statement_key") or ""),
        category=str(doc.get("category") or ""),
        subject=str(doc.get("subject") or ""),
        scope=str(doc.get("scope") or ""),
        statement=str(doc.get("statement") or ""),
        evidence_paths=[str(v) for v in (doc.get("evidence_paths") or [])],
        evidence_json=str(doc.get("evidence_json") or "[]"),
        evidence_commit_sha=str(doc.get("evidence_commit_sha") or ""),
        evidence_branch=str(doc.get("evidence_branch") or ""),
        evidence_hash=str(doc.get("evidence_hash") or ""),
        status=str(doc.get("status") or ""),
        confidence=float(doc.get("confidence") or 0.0),
        validation_status=str(doc.get("validation_status") or ""),
        validation_summary=str(doc.get("validation_summary") or ""),
        source_task_hash=str(doc.get("source_task_hash") or ""),
        created_at=_iso(doc.get("created_at")),
        updated_at=_iso(doc.get("updated_at")),
        supersedes_id=str(doc.get("supersedes_id") or ""),
        conflict_with_ids=[str(v) for v in (doc.get("conflict_with_ids") or [])],
    )


def _coerce_candidate(value: Dict[str, Any] | RepositoryContextCandidate) -> RepositoryContextCandidate:
    if isinstance(value, RepositoryContextCandidate):
        return value
    evidence = []
    for item in value.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        path = _normalize_path(item.get("path") or "")
        excerpt = str(item.get("excerpt") or "").strip()
        if path and excerpt:
            evidence.append(
                RepositoryContextEvidence(
                    path=path,
                    excerpt=excerpt,
                    reason=_normalize_space(item.get("reason") or ""),
                )
            )
    return RepositoryContextCandidate(
        category=_normalize_space(value.get("category") or "").lower(),
        subject=_normalize_space(value.get("subject") or ""),
        scope=_normalize_space(value.get("scope") or "repository") or "repository",
        statement=_normalize_space(value.get("statement") or ""),
        confidence=float(value.get("confidence") or 0.0),
        evidence=evidence,
        validation_summary=_normalize_space(value.get("validation_summary") or ""),
    )


def validate_repository_context_candidate(
    candidate: Dict[str, Any] | RepositoryContextCandidate,
    *,
    repo_owner: str,
    repo_name: str,
    evidence_ref: str,
    evidence_fetcher: RepositoryEvidenceFetcher,
) -> Dict[str, Any]:
    """Validate a proposed durable fact against exact repository evidence."""
    parsed = _coerce_candidate(candidate)
    errors: List[str] = []
    verified: List[Dict[str, str]] = []

    if parsed.category not in ALLOWED_CATEGORIES:
        errors.append(f"unsupported category: {parsed.category or '<empty>'}")
    if len(parsed.subject) < 3:
        errors.append("subject is too short")
    if len(parsed.statement) < 12:
        errors.append("statement is too short to be durable repository knowledge")
    if _contains_conversation_summary_language(parsed.statement):
        errors.append("statement describes a conversation instead of repository knowledge")
    if parsed.confidence < MIN_CONFIDENCE:
        errors.append(
            f"confidence {parsed.confidence:.2f} is below minimum {MIN_CONFIDENCE:.2f}"
        )
    if not parsed.evidence:
        errors.append("at least one repository evidence excerpt is required")

    repo_full = _repo_full_name(repo_owner, repo_name)
    for evidence in parsed.evidence[:12]:
        path = _normalize_path(evidence.path)
        excerpt = str(evidence.excerpt or "").strip()
        if not path or not excerpt:
            continue
        try:
            content = evidence_fetcher(repo_owner, repo_name, path, evidence_ref)
        except Exception as exc:
            _diag(
                "validation_evidence_fetch_failed",
                level="warning",
                repo=repo_full,
                path=path,
                ref=evidence_ref,
                error=exc,
            )
            continue
        if content is None:
            continue
        normalized_content = _normalize_space(content)
        normalized_excerpt = _normalize_space(excerpt)
        if normalized_excerpt and normalized_excerpt in normalized_content:
            verified.append(
                {
                    "path": path,
                    "excerpt": _redact_sensitive_literals(excerpt[:800]),
                    "reason": _normalize_space(evidence.reason)[:500],
                }
            )

    if not verified:
        errors.append("none of the supplied evidence excerpts matched repository content at the evidence ref")

    valid = not errors
    _diag(
        "validation_complete",
        level="info" if valid else "warning",
        repo=repo_full,
        category=parsed.category,
        subject=parsed.subject,
        valid=valid,
        verified_evidence=len(verified),
        error_count=len(errors),
    )
    return {
        "valid": valid,
        "errors": errors,
        "candidate": parsed,
        "verified_evidence": verified,
    }


def _query_identity_records(repo_full_name: str, identity_key: str) -> List[RepositoryContextRecord]:
    client = get_repository_context_search_client()
    filter_text = (
        f"doc_type eq '{DOC_TYPE}' and "
        f"repo_full_name eq '{_safe_odata(repo_full_name)}' and "
        f"identity_key eq '{_safe_odata(identity_key)}'"
    )
    results = client.search(
        search_text="*",
        filter=filter_text,
        top=50,
        order_by=["updated_at desc"],
    )
    return [_search_doc_to_record(dict(item)) for item in results]


def get_repository_context_by_id(context_id: str) -> Optional[RepositoryContextRecord]:
    client = get_repository_context_search_client()
    try:
        doc = client.get_document(key=str(context_id or "").strip())
    except Exception:
        return None
    return _search_doc_to_record(dict(doc)) if doc else None


def _upload_record(record: RepositoryContextRecord) -> None:
    client = get_repository_context_search_client()
    result = client.merge_or_upload_documents(documents=[_record_to_search_document(record)])
    failures = [item for item in (result or []) if not getattr(item, "succeeded", False)]
    if failures:
        raise RuntimeError(f"Azure AI Search rejected repository context record {record.id}.")


def _merge_status_fields(context_id: str, **fields: Any) -> None:
    document = {"id": context_id, **fields}
    client = get_repository_context_search_client()
    result = client.merge_documents(documents=[document])
    failures = [item for item in (result or []) if not getattr(item, "succeeded", False)]
    if failures:
        raise RuntimeError(f"Azure AI Search could not update repository context {context_id}.")


def add_repository_context(
    *,
    repo_owner: str,
    repo_name: str,
    evidence_commit_sha: str,
    evidence_branch: str,
    source_task_hash: str,
    candidate: Dict[str, Any] | RepositoryContextCandidate,
    evidence_fetcher: RepositoryEvidenceFetcher,
) -> Dict[str, Any]:
    """Validate, deduplicate, and store one durable repository conclusion."""
    repo_full = _repo_full_name(repo_owner, repo_name)
    evidence_ref = str(evidence_commit_sha or evidence_branch or "").strip()
    if not evidence_ref:
        raise ValueError("evidence_commit_sha or evidence_branch is required.")

    _diag("add_started", repo=repo_full, commit=evidence_commit_sha, branch=evidence_branch)
    validation = validate_repository_context_candidate(
        candidate,
        repo_owner=repo_owner,
        repo_name=repo_name,
        evidence_ref=evidence_ref,
        evidence_fetcher=evidence_fetcher,
    )
    if not validation["valid"]:
        _diag(
            "add_rejected",
            level="warning",
            repo=repo_full,
            errors=" | ".join(validation["errors"]),
        )
        return {"ok": False, "stored": False, "errors": validation["errors"]}

    parsed: RepositoryContextCandidate = validation["candidate"]
    verified = validation["verified_evidence"]
    identity = _identity_key(repo_full, parsed.category, parsed.subject, parsed.scope)
    statement_key = _statement_key(parsed.statement)
    evidence_hash = _hash_text(
        json.dumps(
            {
                "commit": evidence_commit_sha,
                "branch": evidence_branch,
                "evidence": verified,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
    )

    existing = _query_identity_records(repo_full, identity)
    current = [record for record in existing if record.status in ACTIVE_STATUSES]
    exact = next((record for record in current if record.statement_key == statement_key), None)
    now = _utc_now().isoformat()

    if exact:
        # Same durable fact: refresh evidence/version in place instead of adding
        # another copy. This is duplicate detection + evidence update.
        exact.evidence_paths = [item["path"] for item in verified]
        exact.evidence_json = json.dumps(verified, ensure_ascii=False)
        exact.evidence_commit_sha = str(evidence_commit_sha or "")
        exact.evidence_branch = str(evidence_branch or "")
        exact.evidence_hash = evidence_hash
        exact.confidence = max(exact.confidence, parsed.confidence)
        exact.validation_status = "validated"
        exact.validation_summary = parsed.validation_summary or exact.validation_summary
        exact.source_task_hash = str(source_task_hash or exact.source_task_hash)
        exact.updated_at = now
        _upload_record(exact)
        _diag("duplicate_refreshed", repo=repo_full, context_id=exact.id, subject=parsed.subject)
        return {
            "ok": True,
            "stored": True,
            "action": "duplicate_refreshed",
            "record": exact.to_public_dict(current_commit_sha=evidence_commit_sha),
        }

    conflict_ids = [record.id for record in current if record.statement_key != statement_key]
    status = "conflicted" if conflict_ids else "active"
    context_id = "rcx_" + _hash_text(
        f"{repo_full}:{identity}:{statement_key}:{evidence_hash}:{now}"
    )[:28]
    record = RepositoryContextRecord(
        id=context_id,
        repo_owner=_normalize_repo_part(repo_owner),
        repo_name=_normalize_repo_part(repo_name),
        repo_full_name=repo_full,
        identity_key=identity,
        statement_key=statement_key,
        category=parsed.category,
        subject=parsed.subject,
        scope=parsed.scope,
        statement=_redact_sensitive_literals(parsed.statement),
        evidence_paths=[item["path"] for item in verified],
        evidence_json=json.dumps(verified, ensure_ascii=False),
        evidence_commit_sha=str(evidence_commit_sha or ""),
        evidence_branch=str(evidence_branch or ""),
        evidence_hash=evidence_hash,
        status=status,
        confidence=parsed.confidence,
        validation_status="validated",
        validation_summary=parsed.validation_summary,
        source_task_hash=str(source_task_hash or ""),
        created_at=now,
        updated_at=now,
        conflict_with_ids=conflict_ids,
    )
    _upload_record(record)

    if conflict_ids:
        for old in current:
            old_conflicts = list(dict.fromkeys(list(old.conflict_with_ids or []) + [record.id]))
            _merge_status_fields(
                old.id,
                status="conflicted",
                conflict_with_ids=old_conflicts,
                updated_at=_utc_now(),
            )
        _diag(
            "conflict_recorded",
            level="warning",
            repo=repo_full,
            context_id=record.id,
            conflict_with=",".join(conflict_ids),
            subject=record.subject,
        )
        action = "conflict_recorded"
    else:
        _diag("stored", repo=repo_full, context_id=record.id, subject=record.subject)
        action = "created"

    return {
        "ok": True,
        "stored": True,
        "action": action,
        "record": record.to_public_dict(current_commit_sha=evidence_commit_sha),
    }


def update_repository_context(
    *,
    context_id: str,
    repo_owner: str,
    repo_name: str,
    evidence_commit_sha: str,
    evidence_branch: str,
    source_task_hash: str,
    candidate: Dict[str, Any] | RepositoryContextCandidate,
    evidence_fetcher: RepositoryEvidenceFetcher,
) -> Dict[str, Any]:
    """Version an existing context item without overwriting its history."""
    old = get_repository_context_by_id(context_id)
    if old is None:
        return {"ok": False, "updated": False, "errors": ["context record not found"]}
    repo_full = _repo_full_name(repo_owner, repo_name)
    if old.repo_full_name.lower() != repo_full.lower():
        return {"ok": False, "updated": False, "errors": ["context record belongs to another repository"]}

    validation = validate_repository_context_candidate(
        candidate,
        repo_owner=repo_owner,
        repo_name=repo_name,
        evidence_ref=str(evidence_commit_sha or evidence_branch or ""),
        evidence_fetcher=evidence_fetcher,
    )
    if not validation["valid"]:
        return {"ok": False, "updated": False, "errors": validation["errors"]}

    parsed: RepositoryContextCandidate = validation["candidate"]
    verified = validation["verified_evidence"]
    now = _utc_now().isoformat()
    identity = _identity_key(repo_full, parsed.category, parsed.subject, parsed.scope)
    statement_key = _statement_key(parsed.statement)
    evidence_hash = _hash_text(
        json.dumps({"commit": evidence_commit_sha, "evidence": verified}, sort_keys=True, ensure_ascii=False)
    )
    new_id = "rcx_" + _hash_text(f"update:{old.id}:{statement_key}:{evidence_hash}:{now}")[:28]
    # Preserve explicit conflicts with other current records sharing this
    # repository/category/subject/scope identity. Updating one version must not
    # silently make a contradictory sibling disappear.
    identity_records = _query_identity_records(repo_full, identity)
    other_current = [
        record
        for record in identity_records
        if record.id != old.id and record.status in ACTIVE_STATUSES
    ]
    conflict_ids = [
        record.id for record in other_current if record.statement_key != statement_key
    ]

    new_record = RepositoryContextRecord(
        id=new_id,
        repo_owner=old.repo_owner,
        repo_name=old.repo_name,
        repo_full_name=old.repo_full_name,
        identity_key=identity,
        statement_key=statement_key,
        category=parsed.category,
        subject=parsed.subject,
        scope=parsed.scope,
        statement=_redact_sensitive_literals(parsed.statement),
        evidence_paths=[item["path"] for item in verified],
        evidence_json=json.dumps(verified, ensure_ascii=False),
        evidence_commit_sha=str(evidence_commit_sha or ""),
        evidence_branch=str(evidence_branch or ""),
        evidence_hash=evidence_hash,
        status="conflicted" if conflict_ids else "active",
        confidence=parsed.confidence,
        validation_status="validated",
        validation_summary=parsed.validation_summary,
        source_task_hash=str(source_task_hash or ""),
        created_at=now,
        updated_at=now,
        supersedes_id=old.id,
        conflict_with_ids=conflict_ids,
    )
    _upload_record(new_record)
    _merge_status_fields(old.id, status="superseded", updated_at=_utc_now())

    for sibling in other_current:
        if sibling.id not in conflict_ids:
            continue
        sibling_conflicts = list(
            dict.fromkeys(list(sibling.conflict_with_ids or []) + [new_record.id])
        )
        _merge_status_fields(
            sibling.id,
            status="conflicted",
            conflict_with_ids=sibling_conflicts,
            updated_at=_utc_now(),
        )

    _diag(
        "updated",
        repo=repo_full,
        old_context_id=old.id,
        new_context_id=new_record.id,
        status=new_record.status,
        conflict_with=",".join(conflict_ids),
    )
    return {
        "ok": True,
        "updated": True,
        "action": "version_created",
        "record": new_record.to_public_dict(current_commit_sha=evidence_commit_sha),
        "superseded_id": old.id,
    }


def invalidate_repository_context(
    *,
    context_id: str,
    reason: str,
    current_commit_sha: str = "",
) -> Dict[str, Any]:
    record = get_repository_context_by_id(context_id)
    if record is None:
        return {"ok": False, "invalidated": False, "errors": ["context record not found"]}
    reason = _normalize_space(reason)
    if not reason:
        return {"ok": False, "invalidated": False, "errors": ["reason is required"]}
    validation_summary = _normalize_space(
        f"{record.validation_summary} Invalidated: {reason}"
    ).strip()
    _merge_status_fields(
        record.id,
        status="invalidated",
        validation_status="invalidated",
        validation_summary=validation_summary,
        updated_at=_utc_now(),
    )
    _diag(
        "invalidated",
        level="warning",
        repo=record.repo_full_name,
        context_id=record.id,
        current_commit=current_commit_sha,
        reason=reason,
    )
    return {
        "ok": True,
        "invalidated": True,
        "context_id": record.id,
        "reason": reason,
        "current_commit_sha": current_commit_sha,
    }


def search_repository_context(
    *,
    repo_owner: str,
    repo_name: str,
    query: str,
    current_commit_sha: str = "",
    top_k: int = DEFAULT_TOP_K,
    include_conflicted: bool = True,
) -> Dict[str, Any]:
    """Retrieve repository-scoped durable knowledge, ranked lexically+vector."""
    repo_full = _repo_full_name(repo_owner, repo_name)
    top_k = max(1, min(int(top_k or DEFAULT_TOP_K), 25))
    _diag(
        "search_started",
        repo=repo_full,
        query_preview=_normalize_space(query)[:180],
        current_commit=current_commit_sha,
        top_k=top_k,
    )
    client = get_repository_context_search_client()
    statuses = ["active", "conflicted"] if include_conflicted else ["active"]
    status_filter = " or ".join(f"status eq '{status}'" for status in statuses)
    filter_text = (
        f"doc_type eq '{DOC_TYPE}' and "
        f"repo_full_name eq '{_safe_odata(repo_full)}' and ({status_filter})"
    )
    kwargs: Dict[str, Any] = {
        "search_text": _normalize_space(query) or "*",
        "filter": filter_text,
        "top": max(top_k * 2, top_k),
        "search_fields": ["statement", "subject", "scope", "category", "validation_summary", "evidence_paths"],
    }
    if query and VectorizedQuery is not None:
        try:
            kwargs["vector_queries"] = [
                VectorizedQuery(
                    vector=_embedding(query),
                    k_nearest_neighbors=max(10, top_k * 3),
                    fields="content_vector",
                )
            ]
        except Exception as exc:
            _diag("search_vector_fallback", level="warning", repo=repo_full, error=exc)

    results = client.search(**kwargs)
    records: List[Dict[str, Any]] = []
    for item in results:
        record = _search_doc_to_record(dict(item))
        public = record.to_public_dict(current_commit_sha=current_commit_sha)
        score = getattr(item, "@search.score", None)
        if score is None and isinstance(item, dict):
            score = item.get("@search.score")
        public["search_score"] = score
        records.append(public)
        if len(records) >= top_k:
            break

    stale_count = sum(1 for item in records if item.get("stale"))
    conflicted_count = sum(1 for item in records if item.get("status") == "conflicted")
    _diag(
        "search_completed",
        repo=repo_full,
        result_count=len(records),
        stale_count=stale_count,
        conflicted_count=conflicted_count,
    )
    return {
        "ok": True,
        "repository": repo_full,
        "current_commit_sha": current_commit_sha,
        "results": records,
        "stale_count": stale_count,
        "conflicted_count": conflicted_count,
    }


def format_repository_context_for_agent(search_result: Dict[str, Any]) -> str:
    """Render a bounded evidence-aware context block for a Foundry prompt."""
    results = list(search_result.get("results") or [])
    if not results:
        return ""
    lines = [
        "SHARED REPOSITORY CONTEXT (durable, repository-scoped; never conversation memory):",
        "Use these items as hints/decisions only. Live repository code in the current request is the ultimate source of truth.",
        "If an item is stale or conflicted, revalidate it against current repository evidence before relying on it.",
    ]
    used = sum(len(line) + 1 for line in lines)
    for item in results:
        marker = []
        if item.get("stale"):
            marker.append("STALE")
        if item.get("status") == "conflicted":
            marker.append("CONFLICTED")
        marker_text = f" [{' '.join(marker)}]" if marker else ""
        evidence_paths = ", ".join(item.get("evidence_paths") or [])
        line_parts = [
            f"- {item.get('category')} / {item.get('subject')}{marker_text}: {item.get('statement')}",
            f"  scope={item.get('scope')} evidence_commit={item.get('evidence_commit_sha') or 'unknown'}",
        ]
        if evidence_paths:
            line_parts.append(f"  evidence_paths={evidence_paths}")
        if item.get("status") == "conflicted" and item.get("conflict_with_ids"):
            line_parts.append("  conflict_with=" + ",".join(item.get("conflict_with_ids") or []))
        block = "\n".join(line_parts)
        if used + len(block) + 1 > MAX_CONTEXT_CHARS:
            break
        lines.append(block)
        used += len(block) + 1
    return "\n".join(lines)


def parse_context_extraction_response(text: str) -> List[Dict[str, Any]]:
    raw = str(text or "").strip()
    if not raw:
        return []
    parsed: Dict[str, Any] = {}
    try:
        parsed = json.loads(raw)
    except Exception:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(raw[start : end + 1])
            except Exception:
                parsed = {}
    candidates = parsed.get("candidates") if isinstance(parsed, dict) else []
    return [item for item in (candidates or []) if isinstance(item, dict)]
