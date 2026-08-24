from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared_code.terrabot_core_typing import (
        PENDING_AWS_MODULE_DISCOVERIES,
        _github_request_error,
        build_conversation_label,
        call_agent,
        is_valid_jira_ticket,
        normalize_generated_module_variable_files,
        parse_agent_output,
        try_parse_agent_output,
    )
import os
import re
import json
import base64
import hashlib
import uuid
import time as _time_module
import threading
import contextvars
import zlib
import importlib
from concurrent.futures import ThreadPoolExecutor

try:
    import jwt
except ImportError:  # optional unless GitHub App authentication is enabled
    jwt = None


import asyncio
import logging
from dataclasses import dataclass
from urllib import response
from urllib.parse import parse_qs, unquote, urlparse, urlencode

import requests
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

try:
    from azure.data.tables import TableServiceClient, UpdateMode
except ImportError:  # optional until requirements are deployed
    TableServiceClient = None
    UpdateMode = None
from shared_code.azure_workflow import (
    AFFIRMATIVE_REPLIES,
    NEGATIVE_REPLIES,
    build_azure_module_branch_selection_reply,
    build_azure_module_discovery_reply,
    build_grounded_azure_contexts,
    find_tf_azure_hub_module_invocation_file_by_source,
    clear_pending_azure_module_discovery,
    discover_live_azure_module_candidates,
    get_first_azure_module_match,
    get_pending_azure_module_discovery,
    normalize_yes_no_reply,
    select_azure_module_branch_from_reply,
    select_azure_module_match_from_reply,
    store_pending_azure_module_discovery,
    has_active_azure_pending_workflow,
    is_explicit_azure_consumer_value_reply,
    should_block_missing_azure_value_context,
    should_handle_cloud_only_clarification,
)
from shared_code.aws_workflow import (
    classify_aws_pending_module_reply,
    should_suppress_azure_pending_for_aws,
)
import shared_code.azure_workflow as azure_workflow_state
from shared_code import repository_context as shared_repository_context
from shared_code import pr_context as agent_pr_context
from shared_code import repo_chat_context
from shared_code.terrabot_repair_helpers import SurgicalEdit, apply_surgical_edits
from shared_code.terrabot_teams_helpers import repair_protocol as _modular_repair_protocol, repair_response_contract as _modular_repair_response_contract
from shared_code.terrabot_jira_helpers import extract_ticket_number as _modular_extract_ticket_number, extract_ticket_number_from_jira_link as _modular_extract_ticket_number_from_jira_link
from shared_code.terrabot_vscode_helpers import pull_request_template_headings as _modular_pr_template_headings, body_follows_template as _modular_pr_body_follows_template
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any, List, Dict, Optional
from urllib.parse import urlparse
from contextvars import ContextVar
from html import escape
load_dotenv()

LOGGER = logging.getLogger("terrabot.service")
LOGGER.setLevel(logging.INFO)

_TERRABOT_IO_EXECUTOR = ThreadPoolExecutor(
    max_workers=max(4, int(os.getenv("TERRABOT_IO_MAX_WORKERS", "12"))),
    thread_name_prefix="terrabot-io",
)

from shared_code.keyvault_loader import load_keyvault_secrets
load_keyvault_secrets()

PROJECT_ENDPOINT = os.getenv("PROJECT_ENDPOINT_STRING")
AGENT_NAME = os.getenv("AZURE_AGENT_NAME")

PLAN_RISK_AGENT_NAME = os.getenv("PLAN_RISK_AGENT_NAME")
BACKEND_PLAN_API_URL = os.getenv("BACKEND_PLAN_API_URL")
GITHUB_PR_COMMENT_MARKER = "<!-- terrabot-plan-risk-comment -->"

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_OWNER = os.getenv("GITHUB_OWNER")
GITHUB_AWS_REPO = os.getenv("GITHUB_AWS_REPO")
GITHUB_AWS_BASE_BRANCH = os.getenv("GITHUB_AWS_BASE_BRANCH", "main")
GITHUB_AWS_DIR = os.getenv("GITHUB_AWS_DIR", "terraform")

GITHUB_AZURE_REPO = os.getenv("GITHUB_AZURE_REPO")
GITHUB_AZURE_BASE_BRANCH = os.getenv("GITHUB_AZURE_BASE_BRANCH", "main")
GITHUB_AZURE_DIR = os.getenv("GITHUB_AZURE_DIR", ".")
GITHUB_AZURE_APPROVED_CONSUMER_REPOS = os.getenv("GITHUB_AZURE_APPROVED_CONSUMER_REPOS", "")

GITHUB_VENA_REPO = os.getenv("GITHUB_VENA_REPO")
GITHUB_VENA_BASE_BRANCH = os.getenv("GITHUB_VENA_BASE_BRANCH", "main")
GITHUB_VENA_DIR = os.getenv("GITHUB_VENA_DIR", "vena_repos")
JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "").strip().rstrip("/")

AZDO_ORG = os.getenv("AZDO_ORG")
AZDO_PROJECT = os.getenv("AZDO_PROJECT")
AZDO_PIPELINE_ID = os.getenv("AZDO_PIPELINE_ID")
AZDO_PAT = os.getenv("AZDO_PAT")
AZDO_PIPELINE_BRANCH = os.getenv("AZDO_PIPELINE_BRANCH", "terrabot-test")

# Promotion drift settings. These are intentionally separate from the normal
# PR plan-risk pipeline settings so drift can be enabled without changing
# existing plan/apply behavior.
DRIFT_AGENT_NAME = os.getenv("DRIFT_AGENT_NAME") or os.getenv("FOUNDRY_AGENT_NAME") or os.getenv("foundry_agent_name")
TERRABOT_BACKEND_BASE_URL = (
    os.getenv("TERRABOT_BACKEND_BASE_URL")
    or os.getenv("BACKEND_BASE_URL")
    or os.getenv("BACKEND_PLAN_API_URL")
    or ""
).rstrip("/")
TERRABOT_BACKEND_API_KEY = os.getenv("TERRABOT_BACKEND_API_KEY")
TERRABOT_DRIFT_STORE_PATH = os.getenv("TERRABOT_DRIFT_STORE_PATH", "/tmp/terrabot-drift-results.json")
AZDO_AWS_DRIFT_PIPELINE_ID = os.getenv("AZDO_AWS_DRIFT_PIPELINE_ID") or os.getenv("AZDO_PIPELINE_ID")
AZDO_AZURE_DRIFT_PIPELINE_ID = os.getenv("AZDO_AZURE_DRIFT_PIPELINE_ID")
AZDO_AWS_DRIFT_PIPELINE_BRANCH = os.getenv("AZDO_AWS_DRIFT_PIPELINE_BRANCH", AZDO_PIPELINE_BRANCH)
AZDO_AZURE_DRIFT_PIPELINE_BRANCH = os.getenv("AZDO_AZURE_DRIFT_PIPELINE_BRANCH", AZDO_PIPELINE_BRANCH)
DRIFT_GITHUB_LOOKBACK_COMMITS = int(os.getenv("DRIFT_GITHUB_LOOKBACK_COMMITS", "10"))

GITHUB_PR_SOURCE_BRANCH = os.getenv("GITHUB_PR_SOURCE_BRANCH", "terrabot-test")
GITHUB_PR_SOURCE_BRANCH_AWS = os.getenv("GITHUB_PR_SOURCE_BRANCH_AWS", GITHUB_PR_SOURCE_BRANCH)
GITHUB_PR_SOURCE_BRANCH_AZURE = os.getenv("GITHUB_PR_SOURCE_BRANCH_AZURE", GITHUB_PR_SOURCE_BRANCH)
GITHUB_PR_SOURCE_BRANCH_VENA = os.getenv("GITHUB_PR_SOURCE_BRANCH_VENA", GITHUB_PR_SOURCE_BRANCH_AZURE)

AZDO_API_VERSION = os.getenv("AZDO_API_VERSION", "7.1")
GITHUB_API = "https://api.github.com"

# Teams uses a centrally installed GitHub App. VS Code keeps its existing
# user-token workflow and is not changed by these settings.
GITHUB_APP_ID = (os.getenv("GITHUB_APP_ID") or "").strip()
GITHUB_APP_INSTALLATION_ID = (os.getenv("GITHUB_APP_INSTALLATION_ID") or "").strip()
GITHUB_APP_PRIVATE_KEY = (os.getenv("GITHUB_APP_PRIVATE_KEY") or "").strip()
GITHUB_APP_PRIVATE_KEY_PATH = (os.getenv("GITHUB_APP_PRIVATE_KEY_PATH") or "").strip()
_GITHUB_APP_TOKEN_CACHE: Dict[str, Any] = {"token": "", "expires_at": 0.0}
_GITHUB_APP_TOKEN_LOCK = threading.Lock()
AZURE_MODULE_REPO_TARGET = "azure-module-repo"

ALLOWED_GITHUB_MERGE_COMMIT_TITLES = {"PR_TITLE", "MERGE_MESSAGE"}
ALLOWED_GITHUB_MERGE_COMMIT_MESSAGES = {"PR_BODY", "PR_TITLE", "BLANK"}
DEFAULT_GITHUB_MERGE_COMMIT_TITLE = "PR_TITLE"
DEFAULT_GITHUB_MERGE_COMMIT_MESSAGE = "PR_BODY"

AZURE_NEW_MODULE_AUTOMATION_STAGES = (
    "azure_module",
    "azure_module_population",
    "azure_consumer",
)

AZURE_MODULE_STAGE_LABELS = {
    "azure_module": "terraform-github repo definition",
    "azure_module_population": "new Azure module repo implementation",
    "azure_consumer": "tf-azure-hub consumer",
    "aws": "AWS tf-devops",
}

# Workflows that modify existing Terraform code. These must write the generated
# full file after safety validation instead of using append/merge behavior,
# otherwise one-line edits inside existing blocks can be swallowed as "no change".
INFRA_MODIFICATION_WORKFLOWS = {"aws_infra_modification", "azure_infra_modification"}


credential = None
project_client = None



THREAD_PR_STATE = {}
PENDING_INFRA_CHANGES = {}
THREAD_METADATA = {}
THREAD_AUTO_ADVANCE_IN_PROGRESS = set()
PENDING_AZURE_CONSUMER_VALUE_SELECTIONS = {}
PENDING_AZURE_NEW_CONSUMER_FILE_CONFIRMATIONS = {}
PENDING_MODULE_VARIABLE_VALUE_SELECTIONS = {}
PENDING_INFRA_MODIFICATION_SELECTIONS = {}

# Teams GitHub OAuth/session state. In production, configure a durable token store
# and replace these dictionaries with encrypted Table/Cosmos persistence. Tokens
# are never sent to Foundry or returned in Teams messages.
TEAMS_GITHUB_TOKENS: Dict[str, str] = {}
TEAMS_GITHUB_OAUTH_STATE: Dict[str, Dict[str, Any]] = {}
TEAMS_GITHUB_DEVICE_STATE: Dict[str, Dict[str, Any]] = {}
_ACTIVE_GITHUB_TOKEN: ContextVar[str] = ContextVar("terrabot_active_github_token", default="")
_ACTIVE_TEAMS_REQUESTER: ContextVar[str] = ContextVar("terrabot_active_teams_requester", default="terrabot")
_ACTIVE_TEAMS_REQUESTER_DISPLAY: ContextVar[str] = ContextVar("terrabot_active_teams_requester_display", default="Terrabot")
_GITHUB_STATE_TABLE = None


def _github_state_table():
    global _GITHUB_STATE_TABLE

    if _GITHUB_STATE_TABLE is not None:
        return _GITHUB_STATE_TABLE

    if TableServiceClient is None:
        LOGGER.error(
            "azure-data-tables is not installed; "
            "durable GitHub auth state is unavailable."
        )
        return None

    table_name = (
        os.getenv("TERRABOT_GITHUB_STATE_TABLE")
        or "TerrabotGithubState"
    ).strip()

    connection_string = (
        os.getenv("TERRABOT_STATE_STORAGE_CONNECTION_STRING")
        or ""
    ).strip()

    table_service_client_cls = TableServiceClient
    if table_service_client_cls is None:
        LOGGER.error(
            "azure-data-tables is not installed; "
            "durable GitHub auth state is unavailable."
        )
        return None

    try:
        if connection_string:
            service = table_service_client_cls.from_connection_string(
                connection_string
            )
        else:
            account_url = (
                os.getenv("TERRABOT_STATE_STORAGE_ACCOUNT_URL")
                or os.getenv("AzureWebJobsStorage__tableServiceUri")
                or ""
            ).strip().rstrip("/")

            account_name = (
                os.getenv("AzureWebJobsStorage__accountName")
                or ""
            ).strip()

            if not account_url and account_name:
                account_url = (
                    f"https://{account_name}.table.core.windows.net"
                )

            if not account_url:
                raise RuntimeError(
                    "Set TERRABOT_STATE_STORAGE_ACCOUNT_URL to "
                    "https://<storage-account>.table.core.windows.net."
                )

            parsed = urlparse(account_url)

            if (
                parsed.scheme != "https"
                or not parsed.netloc
                or parsed.path not in {"", "/"}
            ):
                raise ValueError(
                    "Invalid Table Storage account URL. "
                    "Do not include the table name or another URL path."
                )

            service = table_service_client_cls(
                endpoint=account_url,
                credential=DefaultAzureCredential(),
            )

        table_client = service.create_table_if_not_exists(
            table_name=table_name
        )

        _GITHUB_STATE_TABLE = table_client

        LOGGER.info(
            "Durable Teams GitHub auth table is ready: "
            "endpoint=%s table=%s",
            service.url,
            table_name,
        )

        return _GITHUB_STATE_TABLE

    except Exception:
        LOGGER.exception(
            "Unable to initialize durable Teams GitHub auth storage."
        )
        return None


def _github_state_row_key(user_key: str) -> str:
    return hashlib.sha256((user_key or "").encode("utf-8")).hexdigest()


def teams_github_conversation_key(conversation_id: str) -> str:
    conversation_id = (conversation_id or "").strip()
    return f"conversation:{conversation_id}" if conversation_id else ""


def _load_durable_github_state(user_key: str) -> dict:
    key = (user_key or "").strip()
    if not key:
        return {}
    table = _github_state_table()
    if table is None:
        return {}
    try:
        entity = table.get_entity("teams-github", _github_state_row_key(key))
        return dict(entity)
    except Exception as exc:
        if "ResourceNotFound" not in type(exc).__name__:
            LOGGER.warning("Could not read durable Teams GitHub state: %s", exc)
        return {}


def _save_durable_github_state(user_key: str, values: dict) -> bool:
    key = (user_key or "").strip()
    if not key:
        return False
    table = _github_state_table()
    if table is None:
        LOGGER.error("Durable Teams GitHub state storage is unavailable.")
        return False
    update_mode = UpdateMode
    if update_mode is None:
        LOGGER.error("azure-data-tables UpdateMode is unavailable.")
        return False
    entity = {
        "PartitionKey": "teams-github",
        "RowKey": _github_state_row_key(key),
        "user_key": key,
        **{k: v for k, v in (values or {}).items() if v is not None},
    }
    try:
        table.upsert_entity(entity=entity, mode=update_mode.MERGE)
        stored = table.get_entity("teams-github", _github_state_row_key(key))
        return bool(stored)
    except Exception:
        LOGGER.exception("Unable to persist durable Teams GitHub auth state.")
        return False


def _delete_durable_github_state(user_key: str) -> None:
    key = (user_key or "").strip()
    table = _github_state_table()
    if not key or table is None:
        return
    try:
        table.delete_entity("teams-github", _github_state_row_key(key))
    except Exception:
        pass


# Teams conversation/workflow state must survive Azure Functions worker changes,
# cold starts, and scale-out. The same Azure Table account already used for
# GitHub auth state is reused, but the data is isolated by partition.
_TEAMS_CONVERSATION_STATE_PARTITION = "teams-conversation-state"
_TEAMS_WORKFLOW_STATE_PARTITION = "teams-workflow-state"
_TEAMS_STATE_SCHEMA_VERSION = 1
_TEAMS_STATE_CHUNK_SIZE = max(
    8_000,
    min(int(os.getenv("TERRABOT_TEAMS_STATE_CHUNK_SIZE", "28000")), 30_000),
)
_TEAMS_STATE_MAX_CHUNKS = max(
    8,
    min(int(os.getenv("TERRABOT_TEAMS_STATE_MAX_CHUNKS", "128")), 256),
)
_TEAMS_STATE_TTL_SECONDS = max(
    3_600,
    int(os.getenv("TERRABOT_TEAMS_STATE_TTL_SECONDS", str(7 * 24 * 60 * 60))),
)
_TEAMS_STATE_LOCK = threading.RLock()


def _teams_state_json_safe(value):
    """Convert workflow state to JSON-safe primitives without losing structure."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            str(key): _teams_state_json_safe(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_teams_state_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _teams_state_base_row_key(state_key: str) -> str:
    return hashlib.sha256((state_key or "").encode("utf-8")).hexdigest()


def _teams_state_chunk_row_key(
    base_row_key: str,
    generation: str,
    index: int,
) -> str:
    generation = re.sub(r"[^A-Za-z0-9-]", "", generation or "legacy")[:24] or "legacy"
    return f"{base_row_key}-{generation}-c{int(index):04d}"


def _encode_teams_state_payload(payload: dict) -> tuple[list[str], str]:
    raw = json.dumps(
        _teams_state_json_safe(payload or {}),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    encoded = base64.b64encode(zlib.compress(raw, level=9)).decode("ascii")
    chunks = [
        encoded[index:index + _TEAMS_STATE_CHUNK_SIZE]
        for index in range(0, len(encoded), _TEAMS_STATE_CHUNK_SIZE)
    ] or [""]
    if len(chunks) > _TEAMS_STATE_MAX_CHUNKS:
        raise ValueError(
            "Teams workflow state is too large for durable Table Storage "
            f"({len(chunks)} chunks; maximum {_TEAMS_STATE_MAX_CHUNKS})."
        )
    checksum = hashlib.sha256(encoded.encode("ascii")).hexdigest()
    return chunks, checksum


def _decode_teams_state_payload(encoded: str, checksum: str = "") -> dict:
    encoded = str(encoded or "")
    if checksum:
        actual = hashlib.sha256(encoded.encode("ascii")).hexdigest()
        if actual != checksum:
            raise ValueError("Durable Teams state checksum validation failed.")
    raw = zlib.decompress(base64.b64decode(encoded.encode("ascii")))
    payload = json.loads(raw.decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def _load_chunked_teams_state(partition_key: str, state_key: str) -> dict:
    key = (state_key or "").strip()
    if not key:
        return {}
    table = _github_state_table()
    if table is None:
        return {}

    base_row_key = _teams_state_base_row_key(key)
    try:
        metadata = dict(table.get_entity(partition_key, base_row_key))
    except Exception as exc:
        if "ResourceNotFound" not in type(exc).__name__:
            LOGGER.warning(
                "Could not read durable Teams state partition=%s key_hash=%s: %s",
                partition_key,
                base_row_key[:12],
                exc,
            )
        return {}

    expires_at = float(metadata.get("expires_at_epoch") or 0)
    if expires_at and _time_module.time() > expires_at:
        _delete_chunked_teams_state(partition_key, key)
        return {}

    chunk_count = int(metadata.get("chunk_count") or 0)
    if chunk_count <= 0 or chunk_count > _TEAMS_STATE_MAX_CHUNKS:
        LOGGER.error(
            "Invalid durable Teams state chunk count partition=%s key_hash=%s count=%s",
            partition_key,
            base_row_key[:12],
            chunk_count,
        )
        return {}

    generation = str(metadata.get("generation") or "legacy").strip() or "legacy"
    chunks = []
    try:
        for index in range(chunk_count):
            entity = table.get_entity(
                partition_key,
                _teams_state_chunk_row_key(base_row_key, generation, index),
            )
            chunks.append(str(entity.get("payload") or ""))
        return _decode_teams_state_payload(
            "".join(chunks),
            str(metadata.get("checksum") or ""),
        )
    except Exception:
        LOGGER.exception(
            "Unable to decode durable Teams state partition=%s key_hash=%s",
            partition_key,
            base_row_key[:12],
        )
        return {}


def _save_chunked_teams_state(partition_key: str, state_key: str, payload: dict) -> bool:
    key = (state_key or "").strip()
    if not key:
        return False
    table = _github_state_table()
    if table is None:
        LOGGER.error(
            "Durable Teams state storage is unavailable. Configure Table Storage "
            "before running Teams multi-turn workflows in production."
        )
        return False
    update_mode = UpdateMode
    if update_mode is None:
        LOGGER.error("azure-data-tables UpdateMode is unavailable.")
        return False

    try:
        chunks, checksum = _encode_teams_state_payload(payload)
    except Exception:
        LOGGER.exception("Unable to serialize durable Teams state.")
        return False

    base_row_key = _teams_state_base_row_key(key)
    now = _time_module.time()
    replace_mode = update_mode.REPLACE

    with _TEAMS_STATE_LOCK:
        old_chunk_count = 0
        old_generation = ""
        try:
            old = table.get_entity(partition_key, base_row_key)
            old_chunk_count = int(old.get("chunk_count") or 0)
            old_generation = str(old.get("generation") or "legacy").strip() or "legacy"
        except Exception:
            old_chunk_count = 0
            old_generation = ""

        generation = uuid.uuid4().hex[:16]
        try:
            for index, chunk in enumerate(chunks):
                table.upsert_entity(
                    entity={
                        "PartitionKey": partition_key,
                        "RowKey": _teams_state_chunk_row_key(base_row_key, generation, index),
                        "payload": chunk,
                    },
                    mode=replace_mode,
                )

            # Metadata is written last. Readers continue using the complete old
            # generation until this atomic entity replacement points them to
            # the complete new generation.
            table.upsert_entity(
                entity={
                    "PartitionKey": partition_key,
                    "RowKey": base_row_key,
                    "state_key": key,
                    "schema_version": _TEAMS_STATE_SCHEMA_VERSION,
                    "generation": generation,
                    "chunk_count": len(chunks),
                    "checksum": checksum,
                    "updated_at_epoch": now,
                    "expires_at_epoch": now + _TEAMS_STATE_TTL_SECONDS,
                },
                mode=replace_mode,
            )

            if old_generation:
                for index in range(min(old_chunk_count, _TEAMS_STATE_MAX_CHUNKS)):
                    try:
                        table.delete_entity(
                            partition_key,
                            _teams_state_chunk_row_key(base_row_key, old_generation, index),
                        )
                    except Exception:
                        pass
            return True
        except Exception:
            LOGGER.exception(
                "Unable to persist durable Teams state partition=%s key_hash=%s",
                partition_key,
                base_row_key[:12],
            )
            return False


def _delete_chunked_teams_state(partition_key: str, state_key: str) -> None:
    key = (state_key or "").strip()
    table = _github_state_table()
    if not key or table is None:
        return
    base_row_key = _teams_state_base_row_key(key)
    chunk_count = 0
    generation = "legacy"
    try:
        metadata = table.get_entity(partition_key, base_row_key)
        chunk_count = int(metadata.get("chunk_count") or 0)
        generation = str(metadata.get("generation") or "legacy").strip() or "legacy"
    except Exception:
        chunk_count = 0
    for index in range(min(chunk_count, _TEAMS_STATE_MAX_CHUNKS)):
        try:
            table.delete_entity(
                partition_key,
                _teams_state_chunk_row_key(base_row_key, generation, index),
            )
        except Exception:
            pass
    try:
        table.delete_entity(partition_key, base_row_key)
    except Exception:
        pass


def load_teams_conversation_state(teams_conversation_id: str) -> dict:
    """Load durable UI/router state for one Microsoft Teams conversation."""
    return _load_chunked_teams_state(
        _TEAMS_CONVERSATION_STATE_PARTITION,
        (teams_conversation_id or "").strip(),
    )


def save_teams_conversation_state(teams_conversation_id: str, state: dict) -> bool:
    """Persist non-secret Teams state used to route follow-up messages."""
    cleaned = {
        str(key): value
        for key, value in dict(state or {}).items()
        if "token" not in str(key).lower() and "secret" not in str(key).lower()
    }
    return _save_chunked_teams_state(
        _TEAMS_CONVERSATION_STATE_PARTITION,
        (teams_conversation_id or "").strip(),
        cleaned,
    )


def clear_teams_conversation_state(teams_conversation_id: str) -> None:
    _delete_chunked_teams_state(
        _TEAMS_CONVERSATION_STATE_PARTITION,
        (teams_conversation_id or "").strip(),
    )


def _reset_teams_chat_session_base(
    teams_conversation_id: str,
    workflow_thread_id: str = "",
) -> dict:
    """Clear Teams router/workflow state without deleting GitHub artifacts or auth."""
    conversation_id = (teams_conversation_id or "").strip()
    thread_id = (workflow_thread_id or "").strip()

    if thread_id:
        THREAD_PR_STATE.pop(thread_id, None)
        THREAD_METADATA.pop(thread_id, None)
        THREAD_AUTO_ADVANCE_IN_PROGRESS.discard(thread_id)
        for mapping in _teams_pending_state_mappings().values():
            _remove_teams_mapping_entries_for_thread(mapping, thread_id)
        _delete_chunked_teams_state(_TEAMS_WORKFLOW_STATE_PARTITION, thread_id)

    if conversation_id:
        clear_teams_conversation_state(conversation_id)

    LOGGER.info(
        "Reset Teams chat session: conversation_hash=%s workflow_thread_hash=%s",
        stable_thread_key(conversation_id) if conversation_id else "",
        stable_thread_key(thread_id) if thread_id else "",
    )
    return {
        "ok": True,
        "conversation_state_cleared": bool(conversation_id),
        "workflow_state_cleared": bool(thread_id),
        "github_artifacts_deleted": False,
        "github_auth_cleared": False,
    }


def _teams_pending_state_mappings_stage1() -> dict[str, dict]:
    return {
        "pending_infra_changes": PENDING_INFRA_CHANGES,
        "pending_cloud_clarifications": PENDING_CLOUD_CLARIFICATIONS,
        "pending_aws_module_discoveries": PENDING_AWS_MODULE_DISCOVERIES,
        "pending_azure_module_discoveries": azure_workflow_state.PENDING_AZURE_MODULE_DISCOVERIES,
        "pending_azure_consumer_value_selections": PENDING_AZURE_CONSUMER_VALUE_SELECTIONS,
        "pending_azure_new_consumer_file_confirmations": PENDING_AZURE_NEW_CONSUMER_FILE_CONFIRMATIONS,
        "pending_module_variable_value_selections": PENDING_MODULE_VARIABLE_VALUE_SELECTIONS,
        "pending_infra_modification_selections": PENDING_INFRA_MODIFICATION_SELECTIONS,
    }
_teams_pending_state_mappings = _teams_pending_state_mappings_stage1


def _teams_mapping_entries_for_thread(mapping: dict, thread_id: str) -> dict:
    thread = str(thread_id or "")
    return {
        str(key): value
        for key, value in mapping.items()
        if isinstance(value, dict)
        and str(value.get("thread_id") or "") == thread
    }


def _remove_teams_mapping_entries_for_thread(mapping: dict, thread_id: str) -> None:
    thread = str(thread_id or "")
    for key, value in list(mapping.items()):
        if isinstance(value, dict) and str(value.get("thread_id") or "") == thread:
            mapping.pop(key, None)


def capture_teams_workflow_state(thread_id: str) -> dict:
    """Capture every backend pending object belonging to one Teams thread."""
    thread = (thread_id or "").strip()
    if not thread:
        return {}
    return {
        "schema_version": _TEAMS_STATE_SCHEMA_VERSION,
        "thread_id": thread,
        "thread_pr_state": _teams_state_json_safe(THREAD_PR_STATE.get(thread) or {}),
        "pending": {
            name: _teams_state_json_safe(
                _teams_mapping_entries_for_thread(mapping, thread)
            )
            for name, mapping in _teams_pending_state_mappings().items()
        },
    }


def persist_teams_workflow_state(thread_id: str) -> bool:
    """Persist backend workflow/pending state after every Teams turn."""
    thread = (thread_id or "").strip()
    if not thread:
        return False
    return _save_chunked_teams_state(
        _TEAMS_WORKFLOW_STATE_PARTITION,
        thread,
        capture_teams_workflow_state(thread),
    )


def restore_teams_workflow_state(thread_id: str) -> bool:
    """Restore backend workflow state before processing a Teams follow-up."""
    thread = (thread_id or "").strip()
    if not thread:
        return False
    snapshot = _load_chunked_teams_state(_TEAMS_WORKFLOW_STATE_PARTITION, thread)
    if not snapshot:
        return False

    thread_pr_state = snapshot.get("thread_pr_state")
    if isinstance(thread_pr_state, dict):
        THREAD_PR_STATE[thread] = thread_pr_state

    pending_snapshot = snapshot.get("pending") or {}
    for name, mapping in _teams_pending_state_mappings().items():
        _remove_teams_mapping_entries_for_thread(mapping, thread)
        restored = pending_snapshot.get(name) or {}
        if isinstance(restored, dict):
            mapping.update(restored)

    LOGGER.info(
        "Restored durable Teams workflow state: thread_hash=%s pending_groups=%s",
        stable_thread_key(thread),
        sum(bool(items) for items in pending_snapshot.values() if isinstance(items, dict)),
    )
    return True


def teams_workflow_has_pending_state(thread_id: str) -> bool:
    thread = (thread_id or "").strip()
    if not thread:
        return False
    for mapping in _teams_pending_state_mappings().values():
        if _teams_mapping_entries_for_thread(mapping, thread):
            return True
    return False


def teams_github_user_key(tenant_id: str, aad_object_id: str) -> str:
    tenant = (tenant_id or "").strip()
    user = (aad_object_id or "").strip()
    if not tenant or not user:
        return ""
    return f"{tenant}:{user}"


def get_teams_github_token(user_key: str) -> str:
    key = (user_key or "").strip()
    token = (TEAMS_GITHUB_TOKENS.get(key) or "").strip()
    if token:
        return token
    durable = _load_durable_github_state(key)
    token = str(durable.get("access_token") or "").strip()
    if token:
        TEAMS_GITHUB_TOKENS[key] = token
    return token


def set_teams_github_token(user_key: str, token: str) -> None:
    key = (user_key or "").strip()
    value = (token or "").strip()
    if not key or not value:
        raise ValueError("A Teams GitHub user key and token are required.")
    TEAMS_GITHUB_TOKENS[key] = value
    _save_durable_github_state(key, {
        "access_token": value,
        "auth_status": "connected",
        "device_code": "",
        "user_code": "",
        "pending_prompt": "",
    })


def clear_teams_github_token(user_key: str) -> None:
    key = (user_key or "").strip()
    TEAMS_GITHUB_TOKENS.pop(key, None)
    TEAMS_GITHUB_DEVICE_STATE.pop(key, None)
    _delete_durable_github_state(key)

def _github_oauth_client_id() -> str:
    """Resolve the GitHub OAuth client used by VS Code/Teams integrations."""
    for name in (
        "GITHUB_OAUTH_CLIENT_ID",
        "GITHUB_CLIENT_ID",
        "TERRABOT_GITHUB_CLIENT_ID",
        "VSCODE_GITHUB_CLIENT_ID",
    ):
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def _github_oauth_client_secret() -> str:
    for name in (
        "GITHUB_OAUTH_CLIENT_SECRET",
        "GITHUB_CLIENT_SECRET",
        "TERRABOT_GITHUB_CLIENT_SECRET",
        "VSCODE_GITHUB_CLIENT_SECRET",
    ):
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def _github_oauth_callback_url() -> str:
    callback_url = (os.getenv("GITHUB_OAUTH_CALLBACK_URL") or "").strip()
    public_base = (os.getenv("TERRABOT_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    return callback_url or (f"{public_base}/api/github/teams/callback" if public_base else "")


def build_teams_github_connect_url(user_key: str, conversation_id: str = "") -> str:
    """Build browser OAuth URL when a callback-based OAuth app is configured."""
    client_id = _github_oauth_client_id()
    callback_url = _github_oauth_callback_url()
    if not client_id:
        raise RuntimeError(
            "Missing GitHub OAuth client ID. Configure one of "
            "GITHUB_OAUTH_CLIENT_ID, GITHUB_CLIENT_ID, "
            "TERRABOT_GITHUB_CLIENT_ID, or VSCODE_GITHUB_CLIENT_ID."
        )
    if not callback_url:
        raise RuntimeError("Missing GITHUB_OAUTH_CALLBACK_URL or TERRABOT_PUBLIC_BASE_URL.")

    nonce = uuid.uuid4().hex
    TEAMS_GITHUB_OAUTH_STATE[nonce] = {
        "user_key": (user_key or "").strip(),
        "conversation_id": (conversation_id or "").strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    scopes = (os.getenv("GITHUB_OAUTH_SCOPES") or "repo read:org").strip()
    return "https://github.com/login/oauth/authorize?" + urlencode({
        "client_id": client_id,
        "redirect_uri": callback_url,
        "scope": scopes,
        "state": nonce,
    })


def start_teams_github_authentication(user_key: str, conversation_id: str = "", pending_prompt: str = "") -> dict:
    """Start GitHub auth using browser OAuth or GitHub's device flow.

    Device flow mirrors the VS Code experience more closely: the user opens
    GitHub, enters a short code, and no Function App client secret or public
    callback route is required. The GitHub OAuth app must have Device Flow
    enabled.
    """
    client_id = _github_oauth_client_id()
    if not client_id:
        raise RuntimeError(
            "Missing GitHub OAuth client ID. Reuse the client ID configured for "
            "the VS Code GitHub connection by setting GITHUB_CLIENT_ID or "
            "VSCODE_GITHUB_CLIENT_ID in the Function App."
        )

    callback_url = _github_oauth_callback_url()
    client_secret = _github_oauth_client_secret()
    force_device = (os.getenv("GITHUB_OAUTH_USE_DEVICE_FLOW") or "").strip().lower() in {
        "1", "true", "yes"
    }

    if callback_url and client_secret and not force_device:
        return {
            "method": "authorization_code",
            "connect_url": build_teams_github_connect_url(user_key, conversation_id),
        }

    scopes = (os.getenv("GITHUB_OAUTH_SCOPES") or "repo read:org").strip()
    response = requests.post(
        "https://github.com/login/device/code",
        headers={"Accept": "application/json"},
        data={"client_id": client_id, "scope": scopes},
        timeout=30,
    )
    if not response.ok:
        raise _github_request_error(response, "Starting GitHub device authentication")
    payload = response.json() or {}
    device_code = str(payload.get("device_code") or "").strip()
    user_code = str(payload.get("user_code") or "").strip()
    verification_uri = str(
        payload.get("verification_uri")
        or payload.get("verification_uri_complete")
        or "https://github.com/login/device"
    ).strip()
    if not device_code or not user_code:
        raise RuntimeError("GitHub did not return a device authentication code.")

    key = (user_key or "").strip()
    device_state = {
        "device_code": device_code,
        "user_code": user_code,
        "verification_uri": verification_uri,
        "conversation_id": (conversation_id or "").strip(),
        "pending_prompt": (pending_prompt or "").strip(),
        "interval": max(5, int(payload.get("interval") or 5)),
        "expires_in": int(payload.get("expires_in") or 900),
        "created_at_epoch": datetime.now(timezone.utc).timestamp(),
        "auth_status": "pending",
    }
    if not key:
        raise RuntimeError(
            "Teams could not resolve a stable GitHub user identity from the activity. "
            "The Teams tenant ID and sender AAD object ID are required."
        )

    TEAMS_GITHUB_DEVICE_STATE[key] = device_state
    saved_user_state = _save_durable_github_state(key, device_state)

    # Mirror the pending challenge under the stable Teams conversation ID.
    # Some Teams activities expose a different sender-id shape on the follow-up
    # message. The conversation key allows `continue` to recover the exact same
    # device challenge without starting a second authentication flow.
    conversation_key = teams_github_conversation_key(conversation_id)
    saved_conversation_state = False
    if conversation_key:
        TEAMS_GITHUB_DEVICE_STATE[conversation_key] = dict(device_state)
        saved_conversation_state = _save_durable_github_state(conversation_key, device_state)

    if not saved_user_state and not saved_conversation_state:
        TEAMS_GITHUB_DEVICE_STATE.pop(key, None)
        if conversation_key:
            TEAMS_GITHUB_DEVICE_STATE.pop(conversation_key, None)
        raise RuntimeError(
            "Terrabot could not persist the GitHub device challenge. Configure a reachable "
            "Azure Table Storage account and grant the Function App Storage Table Data "
            "Contributor access before retrying."
        )

    LOGGER.info(
        "Stored Teams GitHub device challenge: user_key_hash=%s conversation_key_hash=%s durable=%s",
        _github_state_row_key(key)[:12],
        _github_state_row_key(conversation_key)[:12] if conversation_key else "",
        _github_state_table() is not None,
    )
    return {
        "method": "device_flow",
        "verification_uri": verification_uri,
        "user_code": user_code,
        "expires_in": int(payload.get("expires_in") or 900),
    }


def complete_teams_github_device_authentication(
    user_key: str,
    conversation_id: str = "",
) -> dict:
    user_key = (user_key or "").strip()
    conversation_key = teams_github_conversation_key(conversation_id)

    lookup_keys = []
    for candidate in (user_key, conversation_key):
        if candidate and candidate not in lookup_keys:
            lookup_keys.append(candidate)

    state = {}
    state_key = ""
    for candidate in lookup_keys:
        state = (
            TEAMS_GITHUB_DEVICE_STATE.get(candidate)
            or _load_durable_github_state(candidate)
            or {}
        )
        if state and state.get("device_code"):
            state_key = candidate
            TEAMS_GITHUB_DEVICE_STATE[candidate] = dict(state)
            break

    if not state:
        LOGGER.warning(
            "No Teams GitHub device challenge found: user_key_hash=%s "
            "conversation_key_hash=%s durable=%s",
            _github_state_row_key(user_key)[:12] if user_key else "",
            _github_state_row_key(conversation_key)[:12] if conversation_key else "",
            _github_state_table() is not None,
        )
        return {
            "ok": False,
            "pending": False,
            "error": (
                "No GitHub device authentication is pending. The pending device "
                "challenge was not found in durable storage."
            ),
        }

    created = float(state.get("created_at_epoch") or 0)
    expires_in = int(state.get("expires_in") or 900)
    if created and datetime.now(timezone.utc).timestamp() > created + expires_in:
        for candidate in lookup_keys:
            TEAMS_GITHUB_DEVICE_STATE.pop(candidate, None)
        return {
            "ok": False,
            "pending": False,
            "error": "The GitHub device code expired. Start the connection again.",
        }

    response = requests.post(
        "https://github.com/login/oauth/access_token",
        headers={"Accept": "application/json"},
        data={
            "client_id": _github_oauth_client_id(),
            "device_code": state.get("device_code") or "",
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        },
        timeout=30,
    )
    if not response.ok:
        raise _github_request_error(response, "Completing GitHub device authentication")

    payload = response.json() or {}
    token = str(payload.get("access_token") or "").strip()
    error = str(payload.get("error") or "").strip()

    if token:
        pending_prompt = str(state.get("pending_prompt") or "").strip()

        # Persist the token under the canonical user key and the conversation
        # fallback key. Return the token directly so the current request does
        # not depend on a second storage read.
        if user_key:
            set_teams_github_token(user_key, token)
        if conversation_key:
            TEAMS_GITHUB_TOKENS[conversation_key] = token
            _save_durable_github_state(conversation_key, {
                "access_token": token,
                "auth_status": "connected",
                "device_code": "",
                "user_code": "",
                "pending_prompt": "",
            })

        for candidate in lookup_keys:
            TEAMS_GITHUB_DEVICE_STATE.pop(candidate, None)

        LOGGER.info(
            "Completed Teams GitHub device authentication: state_key_hash=%s "
            "user_key_hash=%s conversation_key_hash=%s",
            _github_state_row_key(state_key)[:12] if state_key else "",
            _github_state_row_key(user_key)[:12] if user_key else "",
            _github_state_row_key(conversation_key)[:12] if conversation_key else "",
        )
        return {
            "ok": True,
            "pending": False,
            "scope": payload.get("scope") or "",
            "pending_prompt": pending_prompt,
            "access_token": token,
        }

    if error in {"authorization_pending", "slow_down"}:
        return {"ok": False, "pending": True, "error": error}

    for candidate in lookup_keys:
        TEAMS_GITHUB_DEVICE_STATE.pop(candidate, None)
    return {
        "ok": False,
        "pending": False,
        "error": payload.get("error_description") or error or "GitHub authentication failed.",
    }


def handle_teams_github_oauth_callback(code: str, state: str) -> dict:
    oauth_state = TEAMS_GITHUB_OAUTH_STATE.pop((state or "").strip(), None)
    if not oauth_state:
        raise ValueError("The GitHub authentication request is invalid or expired.")
    client_id = _github_oauth_client_id()
    client_secret = _github_oauth_client_secret()
    callback_url = _github_oauth_callback_url()
    if not client_id or not client_secret:
        raise RuntimeError("GitHub OAuth client settings are incomplete.")
    response = requests.post(
        "https://github.com/login/oauth/access_token",
        headers={"Accept": "application/json"},
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": (code or "").strip(),
            "redirect_uri": callback_url,
            "state": (state or "").strip(),
        },
        timeout=30,
    )
    if not response.ok:
        raise _github_request_error(response, "Exchanging the GitHub OAuth code")
    payload = response.json() or {}
    token = (payload.get("access_token") or "").strip()
    if not token:
        raise RuntimeError(payload.get("error_description") or "GitHub did not return an access token.")
    set_teams_github_token(oauth_state.get("user_key") or "", token)
    return {
        "ok": True,
        "user_key": oauth_state.get("user_key") or "",
        "conversation_id": oauth_state.get("conversation_id") or "",
        "scope": payload.get("scope") or "",
    }



def _github_app_private_key() -> str:
    value = (GITHUB_APP_PRIVATE_KEY or "").strip()
    if value:
        # Azure App Settings commonly preserve line breaks as literal \\n.
        return value.replace("\\n", "\n")
    if GITHUB_APP_PRIVATE_KEY_PATH:
        with open(GITHUB_APP_PRIVATE_KEY_PATH, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    raise RuntimeError(
        "Missing GitHub App private key. Set GITHUB_APP_PRIVATE_KEY to a Key Vault-backed PEM value "
        "or set GITHUB_APP_PRIVATE_KEY_PATH to a mounted secret file."
    )


def validate_github_app_settings() -> None:
    missing = []
    if not GITHUB_APP_ID:
        missing.append("GITHUB_APP_ID")
    if not GITHUB_APP_INSTALLATION_ID:
        missing.append("GITHUB_APP_INSTALLATION_ID")
    if not GITHUB_APP_PRIVATE_KEY and not GITHUB_APP_PRIVATE_KEY_PATH:
        missing.append("GITHUB_APP_PRIVATE_KEY or GITHUB_APP_PRIVATE_KEY_PATH")
    if missing:
        raise RuntimeError("Missing GitHub App setting(s): " + ", ".join(missing))


def _github_app_jwt() -> str:
    validate_github_app_settings()
    if jwt is None:
        raise RuntimeError(
            "PyJWT is required only when GitHub App authentication is enabled. "
            "Add PyJWT[crypto] to requirements.txt or disable the GitHub App settings."
        )
    now = int(_time_module.time())
    payload = {
        "iat": now - 60,
        "exp": now + (9 * 60),
        "iss": GITHUB_APP_ID,
    }
    encoded: Any = jwt.encode(payload, _github_app_private_key(), algorithm="RS256")
    if isinstance(encoded, bytes):
        return encoded.decode("utf-8")
    return str(encoded)


def get_github_app_installation_token(force_refresh: bool = False) -> str:
    """Return a cached, short-lived installation token for Teams GitHub calls."""
    now = _time_module.time()
    cached = str(_GITHUB_APP_TOKEN_CACHE.get("token") or "").strip()
    expires_at = float(_GITHUB_APP_TOKEN_CACHE.get("expires_at") or 0)
    if not force_refresh and cached and now < expires_at - 300:
        return cached

    with _GITHUB_APP_TOKEN_LOCK:
        now = _time_module.time()
        cached = str(_GITHUB_APP_TOKEN_CACHE.get("token") or "").strip()
        expires_at = float(_GITHUB_APP_TOKEN_CACHE.get("expires_at") or 0)
        if not force_refresh and cached and now < expires_at - 300:
            return cached

        response = requests.post(
            f"{GITHUB_API}/app/installations/{GITHUB_APP_INSTALLATION_ID}/access_tokens",
            headers={
                "Authorization": f"Bearer {_github_app_jwt()}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30,
        )
        if not response.ok:
            raise _github_request_error(response, "Creating a GitHub App installation token")

        payload = response.json() or {}
        token = str(payload.get("token") or "").strip()
        if not token:
            raise RuntimeError("GitHub did not return an installation access token.")

        expires_text = str(payload.get("expires_at") or "").strip()
        try:
            expires_epoch = datetime.fromisoformat(expires_text.replace("Z", "+00:00")).timestamp()
        except Exception:
            expires_epoch = now + 3300

        _GITHUB_APP_TOKEN_CACHE.update({"token": token, "expires_at": expires_epoch})
        return token


def validate_github_app_repository_access() -> None:
    """Fail at startup/request time if the installation lacks required repositories or write permissions."""
    token = get_github_app_installation_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    for repo in (GITHUB_AWS_REPO, GITHUB_AZURE_REPO):
        if not repo:
            continue
        response = requests.get(f"{GITHUB_API}/repos/{GITHUB_OWNER}/{repo}", headers=headers, timeout=30)
        if not response.ok:
            raise _github_request_error(response, f"Validating GitHub App access to {GITHUB_OWNER}/{repo}")
        permissions = (response.json() or {}).get("permissions") or {}
        if not (permissions.get("push") or permissions.get("maintain") or permissions.get("admin")):
            raise PermissionError(
                f"The GitHub App can read {GITHUB_OWNER}/{repo}, but cannot push branches. "
                "Grant repository Contents: Read and write."
            )


class teams_requester_context:
    def __init__(self, requester: str):
        self.display_name = str(requester or "Terrabot").strip() or "Terrabot"
        value = re.sub(r"[^A-Za-z0-9-]+", "-", self.display_name).strip("-").lower()
        self.requester = value[:40] or "terrabot"
        self._reset = None
        self._display_reset = None

    def __enter__(self):
        self._reset = _ACTIVE_TEAMS_REQUESTER.set(self.requester)
        self._display_reset = _ACTIVE_TEAMS_REQUESTER_DISPLAY.set(self.display_name)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._display_reset is not None:
            _ACTIVE_TEAMS_REQUESTER_DISPLAY.reset(self._display_reset)
        if self._reset is not None:
            _ACTIVE_TEAMS_REQUESTER.reset(self._reset)


class github_token_context:
    def __init__(self, token: str):
        self.token = (token or "").strip()
        self._reset = None

    def __enter__(self):
        self._reset = _ACTIVE_GITHUB_TOKEN.set(self.token)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._reset is not None:
            _ACTIVE_GITHUB_TOKEN.reset(self._reset)


# Backend-only retrieval mode. Terrabot does not use caller-provided RAG/KB
# snippets as authoritative Terraform state. Repo/module/value/resource context
# must be generated by backend live GitHub reads.
DISABLE_EXTERNAL_RAG_CONTEXT = os.getenv("TERRABOT_DISABLE_EXTERNAL_RAG_CONTEXT", "true").strip().lower() not in {"0", "false", "no"}
BACKEND_CONTEXT_SOURCE_PREFIXES = (
    "backend_",
    "live_github_",
    "github_",
    "verified_",
    "deterministic_",
)

@dataclass
class NormalizedRouterDecision:
    request_type: str
    cloud: Optional[str] = None
    workflow: str = "standard"
    reason: str = ""


class ModuleVariableValuesRequired(ValueError):
    """Raised when generated module variable files need user-approved values.

    This is intentionally not treated as a terminal backend error. The chat
    handler converts it into a module_variable_values response so the UI can
    collect approved values/references and then continue to PR preview.
    """

    def __init__(self, files: list[dict], issues: list[str], workflow: str = ""):
        super().__init__(
            "Generated module variable declarations require user-approved values. "
            + "; ".join(issues or [])
        )
        self.files = list(files or [])
        self.issues = list(issues or [])
        self.workflow = workflow or ""

def validate_foundry_settings() -> None:
    missing = []

    if not PROJECT_ENDPOINT:
        missing.append("PROJECT_ENDPOINT_STRING")

    if not AGENT_NAME:
        missing.append("AZURE_AGENT_NAME")

    if missing:
        raise ValueError(
            "Missing Foundry environment variables: "
            + ", ".join(missing)
        )


def _require_setting(value: Optional[str], name: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return normalized


def validate_github_settings() -> None:
    missing = []

    github_token = (
        GITHUB_TOKEN
        or os.getenv("TERRABOT_GITHUB_TOKEN")
        or os.getenv("GH_TOKEN")
        or ""
    ).strip()

    if not github_token:
        missing.append("GITHUB_TOKEN")

    if not GITHUB_OWNER:
        missing.append("GITHUB_OWNER")

    if not GITHUB_AWS_REPO:
        missing.append("GITHUB_AWS_REPO")

    if not GITHUB_AZURE_REPO:
        missing.append("GITHUB_AZURE_REPO")

    if not GITHUB_VENA_REPO:
        missing.append("GITHUB_VENA_REPO")

    if missing:
        raise ValueError(
            "Missing GitHub environment variables: "
            + ", ".join(missing)
        )

def get_project_client() -> AIProjectClient:
    global credential, project_client

    if project_client is None:
        validate_foundry_settings()
        endpoint = (PROJECT_ENDPOINT or "").strip()
        if not endpoint:
            raise ValueError("Missing Foundry environment variable: PROJECT_ENDPOINT_STRING")
        active_credential = DefaultAzureCredential()
        credential = active_credential
        project_client = AIProjectClient(
            endpoint=endpoint,
            credential=active_credential,
        )

    return project_client

def extract_ticket_number(value: str) -> str:
    return _modular_extract_ticket_number(value)

def _configured_jira_origin() -> tuple[str, str]:
    base = (JIRA_BASE_URL or "").strip()
    if not base:
        return "", ""

    parsed = urlparse(
        base if re.match(r"^https?://", base, re.IGNORECASE) else f"https://{base}"
    )
    return (parsed.scheme or "").lower(), (parsed.netloc or "").lower()


def extract_ticket_number_from_jira_link(ticket_link: str) -> str:
    return _modular_extract_ticket_number_from_jira_link(ticket_link, JIRA_BASE_URL)

def is_valid_jira_ticket_link(ticket_link: str) -> bool:
    ticket_number = extract_ticket_number_from_jira_link(ticket_link)
    return bool(ticket_number and is_valid_jira_ticket(ticket_number))


def normalize_ticket_input(ticket_value: str) -> tuple[str, str]:
    raw = (ticket_value or "").strip()
    if not raw:
        return "", ""

    if raw.lower().startswith(("http://", "https://")):
        ticket_number = extract_ticket_number_from_jira_link(raw)
        return ticket_number, raw if ticket_number else ""

    return extract_ticket_number(raw), ""


def is_valid_ticket_or_link(raw_value: str) -> bool:
    return is_valid_jira_ticket_link(raw_value)


def find_agent_reference(agent_name: Optional[str]):
    agent_name = (agent_name or "").strip()
    if not agent_name:
        raise RuntimeError("A Foundry agent name is required.")

    client = get_project_client()
    agents = list(client.agents.list())

    if not agents:
        raise RuntimeError("No agents were found in this Azure AI Foundry project.")

    matches = [a for a in agents if getattr(a, "name", None) == agent_name]

    if not matches:
        available_names = [getattr(a, "name", None) for a in agents]
        raise RuntimeError(
            f"Configured AZURE_AGENT_NAME '{agent_name}' was not found. "
            f"Available agent names: {available_names}"
        )

    agent = None
    for a in matches:
        if getattr(a, "version", None):
            agent = a
            break

    if agent is None:
        agent = matches[0]

    ref = {
        "name": getattr(agent, "name", None),
        "type": "agent_reference",
    }

    agent_version = getattr(agent, "version", None)
    if agent_version:
        ref["version"] = agent_version

    return ref


def normalize_iac_relative_path(filename: str, allow_tfvars: bool = False) -> str:
    raw = (filename or "main.tf").strip().replace("\\", "/")
    raw = raw.lstrip("/")

    parts = []
    for part in raw.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            raise ValueError("Terraform file paths must be relative and cannot contain '..'.")
        parts.append(part)

    cleaned = "/".join(parts) if parts else "main.tf"

    if allow_tfvars and cleaned.endswith(".tfvars"):
        return cleaned

    if not cleaned.endswith(".tf"):
        cleaned += ".tf"

    return cleaned


def normalize_tf_relative_path(filename: str) -> str:
    return normalize_iac_relative_path(filename, allow_tfvars=False)

def normalize_agent_relative_tf_path(filename: str, cloud: str) -> str:
    raw = (filename or "main.tf").strip().replace("\\", "/").lstrip("/")
    path = normalize_iac_relative_path(raw, allow_tfvars=(cloud == "azure"))

    if cloud == "azure":
        forbidden_prefixes = (
            "changes/",
            "temp/",
            "generated/",
            "scratch/",
            "azure/",
            "azure_module/",
            "tf-azure-hub/",
            "vena_repos/",
            "vena-repos/",
            "terraform/",
        )

        if path.startswith(forbidden_prefixes):
            raise ValueError(
                "Azure filenames must be repo-relative only. "
                "Do not prefix filenames with repo names, terraform/, changes/, or scratch paths."
            )

    if cloud == "aws":
        if path.startswith(("changes/", "temp/", "generated/", "scratch/")):
            raise ValueError("AWS filenames must not use scratch or generated paths.")

    return path


AZURE_MODULE_POPULATION_REQUIRED_FILES = ("main.tf", "variables.tf", "outputs.tf")

AZURE_MODULE_POPULATION_FORBIDDEN_TEXT = (
    "todo",
    "changeme",
    "change me",
    "replace me",
    "replace_me",
    "fill this",
    "fill_this",
    "placeholder",
    "pending design",
    "implementation pending",
    "module implementation pending",
    "not implemented",
    "example only",
    "sample only",
)


def normalize_azure_module_repo_population_path(filename: str) -> str:
    raw = (filename or "main.tf").strip().replace("\\", "/").lstrip("/")

    if not raw:
        raw = "main.tf"

    parts = []
    for part in raw.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            raise ValueError(
                "Azure module repo population file paths must be relative and cannot contain '..'."
            )
        parts.append(part)

    cleaned = "/".join(parts) if parts else "main.tf"

    forbidden_prefixes = (
        "terraform/",
        "tf-azure-hub/",
        "vena_repos/",
        "vena-repos/",
        "changes/",
        "temp/",
        "generated/",
        "scratch/",
        "azure/",
    )

    if cleaned.startswith(forbidden_prefixes):
        raise ValueError(
            "Azure module repo population files must be relative to the module repository root."
        )

    if "/" in cleaned:
        raise ValueError(
            "Azure module repo population must generate root-level module files only."
        )

    lower = cleaned.lower()

    if lower in {"readme", "readme.md", "readme.md.tf"}:
        return "README.md"

    if lower.endswith(".md"):
        raise ValueError(
            "Only README.md may be generated as a markdown file during azure_module_repo_population."
        )

    if lower in {"main.tf", "variables.tf", "outputs.tf", "versions.tf"}:
        return lower

    if not lower.endswith(".tf"):
        cleaned += ".tf"

    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.tf", cleaned):
        raise ValueError(f"Invalid Azure module repo population filename: {cleaned}")

    return cleaned


def _hcl_without_comments(content: str) -> str:
    text = (content or "").replace("\r\n", "\n")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    lines = []

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#") or stripped.startswith("//"):
            continue
        lines.append(line)

    return "\n".join(lines).strip()


def _contains_forbidden_population_text(content: str) -> bool:
    lower = (content or "").lower()
    return any(marker in lower for marker in AZURE_MODULE_POPULATION_FORBIDDEN_TEXT)


def _has_main_tf_implementation_block(content: str) -> bool:
    text = _hcl_without_comments(content)
    return bool(
        re.search(r'(?m)^\s*resource\s+"[^\"]+"\s+"[^\"]+"\s*\{', text)
        or re.search(r'(?m)^\s*data\s+"[^\"]+"\s+"[^\"]+"\s*\{', text)
        or re.search(r'(?m)^\s*module\s+"[^\"]+"\s*\{', text)
    )


def _has_variable_block(content: str) -> bool:
    return bool(re.search(r'(?m)^\s*variable\s+"[A-Za-z0-9_]+"\s*\{', _hcl_without_comments(content)))


def _has_output_block(content: str) -> bool:
    return bool(re.search(r'(?m)^\s*output\s+"[A-Za-z0-9_]+"\s*\{', _hcl_without_comments(content)))


def validate_azure_module_population_core_files(agent_result: dict) -> dict:
    if not isinstance(agent_result, dict):
        return agent_result

    if (agent_result.get("workflow") or "").strip() != "azure_module_repo_population":
        return agent_result

    files = agent_result.get("files") or []
    files_by_name = {}
    normalized_files = []
    seen = set()

    for file_data in files:
        if not isinstance(file_data, dict):
            continue

        filename = normalize_azure_module_repo_population_path(file_data.get("filename") or "")
        content = file_data.get("content", "")
        if not isinstance(content, str):
            content = str(content or "")

        if filename in seen:
            continue

        normalized_content = content.rstrip() + "\n"
        normalized_files.append({
            "filename": filename,
            "content": normalized_content,
        })
        files_by_name[filename] = normalized_content
        seen.add(filename)

    missing = [
        filename
        for filename in AZURE_MODULE_POPULATION_REQUIRED_FILES
        if filename not in files_by_name
    ]

    if missing:
        raise ValueError(
            "azure_module_repo_population must generate real root-level module files: "
            + ", ".join(AZURE_MODULE_POPULATION_REQUIRED_FILES)
            + f". Missing: {', '.join(missing)}"
        )

    for filename in AZURE_MODULE_POPULATION_REQUIRED_FILES:
        content = files_by_name.get(filename) or ""

        if not _hcl_without_comments(content):
            raise ValueError(
                f"{filename} cannot be empty or comment-only. "
                "The Azure module population stage must generate real Terraform code."
            )

        if _contains_forbidden_population_text(content):
            raise ValueError(
                f"{filename} contains placeholder or pending-design text. "
                "The Azure module population stage must generate real Terraform code or ask for clarification."
            )

    if not _has_main_tf_implementation_block(files_by_name["main.tf"]):
        raise ValueError(
            "main.tf must contain at least one real Terraform resource, data, or module block."
        )

    if not _has_variable_block(files_by_name["variables.tf"]):
        raise ValueError(
            "variables.tf must contain at least one real Terraform variable block."
        )

    if not _has_output_block(files_by_name["outputs.tf"]):
        raise ValueError(
            "outputs.tf must contain at least one real Terraform output block."
        )

    normalized_files, variable_issues = normalize_generated_module_variable_files(
        normalized_files,
        "azure_module_repo_population",
        user_prompt=agent_result.get("user_prompt") or agent_result.get("summary") or "",
    )
    if variable_issues:
        raise ModuleVariableValuesRequired(
            normalized_files,
            variable_issues,
            workflow="azure_module_repo_population",
        )

    agent_result["files"] = normalized_files
    return agent_result


def ensure_tf_extension(filename: str) -> str:
    return normalize_tf_relative_path(filename)

def safe_join_under_folder(folder: str, relative_tf_path: str) -> str:
    base = (folder or "").strip().strip("/")
    rel = normalize_iac_relative_path(
        relative_tf_path,
        allow_tfvars=str(relative_tf_path or "").strip().endswith(".tfvars"),
    )

    if rel.startswith("../") or rel == ".." or "/../" in rel:
        raise ValueError("Terraform file path escapes the target folder.")

    # Repo-root mode: valid for tf-azure-hub root and terraform-github/vena_repos root.
    if base in ("", "."):
        return rel

    combined = f"{base}/{rel}".replace("\\", "/")
    combined = re.sub(r"/+", "/", combined)

    if not combined.startswith(base + "/"):
        raise ValueError("Terraform file path escapes the target folder.")

    return combined



def normalize_cloud(cloud: Any | None) -> str:
    cloud = (cloud or "").strip().lower()
    if cloud in ["aws", "amazon", "amazon-web-services"]:
        return "aws"
    if cloud in ["azure", "microsoft-azure"]:
        return "azure"
    raise ValueError("Cloud must be either 'aws' or 'azure'.")

def normalize_repo_target(
    cloud: Any | None,
    repo_target: Any | None = None,
    workflow: Any | None = None,
) -> str:
    cloud = normalize_cloud(cloud)
    repo_target = (repo_target or "").strip().lower().replace("-", "_")
    workflow = (workflow or "").strip()

    if cloud == "aws":
        return "tf-devops"

    if repo_target == "vena_repos":
        return "vena_repos"

    if repo_target in {"tf_azure_hub", "tf-azure-hub"}:
        return "tf-azure-hub"

    if repo_target in {
        AZURE_MODULE_REPO_TARGET,
        AZURE_MODULE_REPO_TARGET.replace("-", "_"),
    }:
        return AZURE_MODULE_REPO_TARGET

    if workflow == "azure_module_repo_creation":
        return "vena_repos"

    if workflow == "azure_module_repo_population":
        return AZURE_MODULE_REPO_TARGET

    return "tf-azure-hub"

def state_bucket_for_target(cloud: Any | None, repo_target: Optional[str] = None, workflow: Optional[str] = None) -> str:
    cloud = normalize_cloud(cloud)
    repo_target = normalize_repo_target(cloud, repo_target, workflow)

    if cloud == "aws":
        return "aws"
    if repo_target == "vena_repos":
        return "azure_module"
    if repo_target == AZURE_MODULE_REPO_TARGET:
        return "azure_module_population"
    return "azure_consumer"

def github_repo_for_cloud(cloud: Any | None, repo_target: Optional[str] = None, workflow: Optional[str] = None) -> str:
    cloud = normalize_cloud(cloud)
    repo_target = normalize_repo_target(cloud, repo_target, workflow)

    if cloud == "aws":
        return _require_setting(GITHUB_AWS_REPO, "GITHUB_AWS_REPO")
    if repo_target == "vena_repos":
        return _require_setting(GITHUB_VENA_REPO, "GITHUB_VENA_REPO")
    if repo_target == AZURE_MODULE_REPO_TARGET:
        raise RuntimeError(
            "azure_module_repo_population requires a dynamic module repo target. "
            "Use commit_azure_module_repo_population_files instead of github_repo_for_cloud."
        )
    return _require_setting(GITHUB_AZURE_REPO, "GITHUB_AZURE_REPO")


def github_base_branch_for_cloud(cloud: Any | None, repo_target: Optional[str] = None, workflow: Optional[str] = None) -> str:
    cloud = normalize_cloud(cloud)
    repo_target = normalize_repo_target(cloud, repo_target, workflow)

    if cloud == "aws":
        return GITHUB_AWS_BASE_BRANCH
    if repo_target == "vena_repos":
        return GITHUB_VENA_BASE_BRANCH
    if repo_target == AZURE_MODULE_REPO_TARGET:
        return GITHUB_AZURE_BASE_BRANCH
    return GITHUB_AZURE_BASE_BRANCH


def github_pr_source_branch_for_cloud(cloud: Any | None, repo_target: Optional[str] = None, workflow: Optional[str] = None) -> str:
    cloud = normalize_cloud(cloud)
    repo_target = normalize_repo_target(cloud, repo_target, workflow)

    if cloud == "aws":
        return GITHUB_PR_SOURCE_BRANCH_AWS
    if repo_target == "vena_repos":
        return GITHUB_PR_SOURCE_BRANCH_VENA
    return GITHUB_PR_SOURCE_BRANCH_AZURE


def github_branch_seed_for_cloud(cloud: Any | None, repo_target: Optional[str] = None, workflow: Optional[str] = None) -> str:
    cloud = normalize_cloud(cloud)
    seed = (github_pr_source_branch_for_cloud(cloud, repo_target=repo_target, workflow=workflow) or "").strip()
    if seed:
        return seed
    return github_base_branch_for_cloud(cloud, repo_target=repo_target, workflow=workflow)

def safe_normalize_cloud(cloud: Any | None):
    try:
        return normalize_cloud(str(cloud or ""))
    except Exception:
        return None


# Teams environment-to-repository routing hints. Explicit cloud/provider terms
# always win. These mappings are used only when the prompt does not identify a
# cloud clearly, so environment names can select the correct live GitHub repo.
TEAMS_AWS_ENVIRONMENT_HINTS = {
    "ca3", "ca3_dr", "devops", "eu1", "eu1_dr", "eu2", "eu2_dr",
    "global", "observe", "sqlstaging", "sqlstaging_ca", "sqlstaging_eu",
    "sqlstaging_eu2", "sqlstaging_us4", "sqlstaging_west", "us1", "us1_dr",
    "us2", "us2_dr", "us3", "us3_dr", "us4", "us4_dr", "bolt", "bolt_dr",
    "bolt_sqlstaging", "dev", "dev_devops", "dev_sqlstaging", "minidev",
    "minidev_sqlstaging",
}
TEAMS_AZURE_ENVIRONMENT_HINTS = {
    "npr-int", "npr-stg", "sbx-infra", "ca4", "eu3", "us5", "us6",
    "prd-ca4", "prd-eu3", "prd-us5", "prd-us6",
}


def _prompt_environment_tokens(prompt: str) -> set[str]:
    normalized = str(prompt or "").lower().replace("_", "-")
    return {
        token.strip("-")
        for token in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", normalized)
        if token.strip("-")
    }


def infer_cloud_from_environment(prompt: str):
    """Infer cloud from a uniquely mapped environment when cloud is omitted."""
    tokens = _prompt_environment_tokens(prompt)
    aws_matches = sorted(tokens & TEAMS_AWS_ENVIRONMENT_HINTS)
    azure_matches = sorted(tokens & TEAMS_AZURE_ENVIRONMENT_HINTS)

    if aws_matches and not azure_matches:
        return "aws"
    if azure_matches and not aws_matches:
        return "azure"
    return None


def infer_cloud_from_prompt(prompt: str):
    """Infer cloud from explicit provider/resource wording, then environment."""
    text = normalize_yes_no_reply(prompt)
    if not text:
        return None

    azure_markers = [
        "azure",
        "azurerm",
        "resource group",
        "vnet",
        "virtual network",
        "azure vm",
        "azure linux vm",
        "azure windows vm",
        "azure container app",
        "azure container apps",
        "container app",
        "container apps",
        "aca app",
        " aca ",
    ]
    aws_markers = [
        "aws",
        "amazon web services",
        "ec2",
        "s3",
        "rds",
        "iam",
        "vpc",
        "eks",
        "lambda",
        "redshift",
        "dynamodb",
        "cloudfront",
        "sqs",
        "sns",
        "elasticache",
    ]

    has_azure = any(marker in text for marker in azure_markers)
    has_aws = any(marker in text for marker in aws_markers)

    if has_azure and not has_aws:
        return "azure"
    if has_aws and not has_azure:
        return "aws"
    if has_azure and has_aws:
        return None

    return infer_cloud_from_environment(prompt)

def get_approved_azure_consumer_repos() -> list[str]:
    raw = (GITHUB_AZURE_APPROVED_CONSUMER_REPOS or "").strip()
    repos = []

    if raw:
        for item in raw.split(","):
            name = (item or "").strip()
            if name:
                repos.append(name)

    if GITHUB_AZURE_REPO and GITHUB_AZURE_REPO not in repos:
        repos.insert(0, GITHUB_AZURE_REPO)

    # preserve order
    seen = set()
    result = []
    for repo in repos:
        if repo not in seen:
            seen.add(repo)
            result.append(repo)

    return result




import re





def generate_short_ticket_title(text: str) -> str:
    if not text:
        return "New Request"

    cleaned = re.sub(r"\s+", " ", text).strip()
    cleaned = re.sub(r"[^\w\s-]", "", cleaned)

    if not cleaned:
        return "New Request"

    words = cleaned.split()[:5]
    return " ".join(word.capitalize() for word in words)
PENDING_CLOUD_CLARIFICATIONS = {}


def store_pending_cloud_clarification(
    thread_id: str,
    ticket_number: str,
    original_prompt: str,
    requested_mode: str = "",
    requested_cloud: str = "",
    ticket_link: str = "",
    ticket_title: str = "",
):
    key = hashlib.sha1(
        f"{thread_id or 'no-thread'}::{ticket_number or ''}::{original_prompt}".encode("utf-8")
    ).hexdigest()

    PENDING_CLOUD_CLARIFICATIONS[key] = {
        "thread_id": thread_id,
        "ticket_number": (ticket_number or "").strip().upper(),
        "original_prompt": original_prompt,
        "requested_mode": requested_mode or "",
        "requested_cloud": requested_cloud or "",
        "ticket_link": ticket_link or "",
        "ticket_title": ticket_title or "",
    }
    return key


def get_pending_cloud_clarification(thread_id: str, ticket_number: str):
    thread_id = str(thread_id or "")
    ticket_number = (ticket_number or "").strip().upper()

    for _, item in PENDING_CLOUD_CLARIFICATIONS.items():
        if str(item.get("thread_id") or "") == thread_id and (item.get("ticket_number") or "") == ticket_number:
            return item
    return None


def clear_pending_cloud_clarification(thread_id: str, ticket_number: str):
    thread_id = str(thread_id or "")
    ticket_number = (ticket_number or "").strip().upper()

    keys_to_delete = []
    for key, item in PENDING_CLOUD_CLARIFICATIONS.items():
        if str(item.get("thread_id") or "") == thread_id and (item.get("ticket_number") or "") == ticket_number:
            keys_to_delete.append(key)

    for key in keys_to_delete:
        PENDING_CLOUD_CLARIFICATIONS.pop(key, None)

def build_thread_label(ticket_title: str, ticket_number: str) -> str:
    title = (ticket_title or "New Request").strip()
    number = (ticket_number or "UNASSIGNED").strip()
    return f"{title} - {number}"


def build_enhanced_conversation_label(ticket_number: str, ticket_title: str, conversation_id: str | None) -> str:
    title = (ticket_title or "").strip()
    ticket = (ticket_number or "").strip()

    if title and ticket:
        return f"{title} - {ticket}"

    if ticket:
        return build_conversation_label(ticket, conversation_id)

    return title or (conversation_id or "New")


def build_pr_body(
    user_prompt: str,
    ticket_link: str = "",
    ticket_number: str = "",
    ticket_title: str = "",
    cloud: Optional[str] = "",
    folder: Optional[str] = "",
    thread_id: Optional[str] = "",
    branch_cycle=None,
    files=None,
    summary: str = "",
) -> str:
    files = files or []

    ticket_header = build_thread_label(ticket_title, ticket_number)

    parts = []

    if summary:
        parts.append(summary)
        parts.append("")

    parts.append("## Ticket")
    parts.append(ticket_header)

    if ticket_link:
        parts.append("")
        parts.append("## Ticket Link")
        parts.append(ticket_link)

    parts.append("")
    parts.append("## Metadata")
    parts.append(f"- Cloud: {cloud or 'Not provided'}")
    parts.append(f"- Folder: {folder or 'Not provided'}")
    parts.append(f"- Thread ID: {thread_id or 'Not provided'}")

    if branch_cycle is not None:
        parts.append(f"- Branch Cycle: {branch_cycle}")

    if files:
        parts.append("")
        parts.append("## Files Updated")
        for file_path in files:
            parts.append(f"- {file_path}")

    parts.append("")
    parts.append("## Request")
    parts.append(user_prompt)

    parts.append("")
    parts.append("## Automation")
    parts.append("PR raised using Terrabot AI.")

    return "\n".join(parts)



def extract_first_balanced_json_object(text: str) -> str:
    text = (text or "").strip()
    if not text:
        raise ValueError("Could not parse JSON from agent response.")

    start = text.find("{")
    if start == -1:
        raise ValueError("Could not parse JSON from agent response.")

    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(text)):
        ch = text[i]

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]

    raise ValueError("Could not parse JSON from agent response.")


def extract_json_from_text(text: str) -> dict:
    text = (text or "").strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    candidate = extract_first_balanced_json_object(text)
    return json.loads(candidate)


def looks_like_infra_payload(text: str) -> bool:
    text = (text or "").strip().lower()
    infra_markers = [
        '"mode"', '"infra"', '"cloud"', '"files"', '"filename"', '"content"',
        "```json", "{", "terraform", ".tf"
    ]
    marker_hits = sum(1 for marker in infra_markers if marker in text)
    return marker_hits >= 4 and ('"files"' in text or '"content"' in text)


def extract_possible_json_object(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""

    fenced = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1].strip()

    return ""


def agent_reply_looks_like_infra_json(text: str) -> bool:
    candidate = extract_possible_json_object(text).lower()
    if not candidate:
        return False

    required_markers = ['"cloud"', '"files"', '"filename"', '"content"']
    return all(marker in candidate for marker in required_markers)

def _try_parse_agent_output_base(agent_text: str):
    candidate = extract_possible_json_object(agent_text) or (agent_text or "").strip()
    return parse_agent_output(candidate)

def _repair_and_parse_agent_output_base(
    conversation_id: str,
    original_agent_input: str,
    bad_agent_reply: str,
    parse_error: Exception,
):
    del conversation_id

    repair_prompt = {
        "task": "Return corrected Terraform infra JSON only.",
        "error": str(parse_error),
        "original_agent_input": original_agent_input,
        "bad_agent_reply": bad_agent_reply,
        "absolute_rules": [
            "Return valid JSON only.",
            "Do not include markdown.",
            "Do not explain.",
            "Use repo_target='vena_repos', never 'vena-repos'.",
            "If workflow is azure_module_repo_creation, create ONLY the terraform-github/vena_repos module repository definition.",
            "For azure_module_repo_creation, return exactly one root-level .tf file that defines the requested repository.",
            "For azure_module_repo_creation, the GitHub repo name may be any valid repo name supplied by the user; do not force a tf-module or tf_module prefix.",
            "For azure_module_repo_creation, content must use module source '../modules/repo'.",
            "For azure_module_repo_creation, merge_commit_title must be exactly one of: PR_TITLE, MERGE_MESSAGE. Use PR_TITLE by default.",
            "For azure_module_repo_creation, merge_commit_message must be exactly one of: PR_BODY, PR_TITLE, BLANK. Use PR_BODY by default. BLANK is a GitHub enum value here, not a placeholder.",
            "For azure_module_repo_creation, never use resource 'github_repository'.",
            "For azure_module_repo_creation, never create azurerm resources, variables, outputs, provider blocks, main.tf, variables.tf, outputs.tf, versions.tf, README, folders, changes/, tf-azure-hub/, terraform/, or azure/ paths.",
        ],
        "required_shape": {
            "mode": "infra",
            "cloud": "azure",
            "workflow": "azure_module_repo_creation",
            "repo_target": "vena_repos",
            "title": "[AZURE] Create Azure module repository",
            "summary": "Creates the Azure module repository definition in terraform-github/vena_repos.",
            "files": [
                {
                    "filename": "azure_linux_vm_module.tf",
                    "content": "module \"azure_linux_vm_module\" {\n  source = \"../modules/repo\"\n\n  name                   = \"azure-linux-vm-module\"\n  description            = \"Repository for Azure Linux VM Module\"\n  delete_branch_on_merge = true\n  has_issues             = true\n  default_branch         = \"main\"\n  merge_commit_title     = \"PR_TITLE\"\n  merge_commit_message   = \"PR_BODY\"\n  actions_enabled        = false\n\n  managed_files = {\n    PULL_REQUEST_TEMPLATE = {\n      repo_path  = \".github/PULL_REQUEST_TEMPLATE.md\"\n      local_file = \"devops.md\"\n    }\n    CODEOWNERS = {\n      repo_path     = \".github/CODEOWNERS\"\n      file_contents = \"* @venasolutions/${var.vena_teams.sto.slug}\"\n    }\n    PRE_COMMIT = {\n      repo_path  = \".pre-commit-config.yaml\"\n      local_file = \"terraform.yml\"\n    }\n  }\n\n  collaborators = {}\n\n  managed_branches = [\"main\"]\n}\n"
                }
            ]
        }
    }

    _new_conversation_id, repaired_reply = call_agent(
        None,
        json.dumps(repair_prompt, indent=2),
    )

    return try_parse_agent_output(repaired_reply), repaired_reply


def is_valid_github_repo_name(repo_name: str) -> bool:
    repo_name = (repo_name or "").strip()
    if not repo_name or repo_name in {".", ".."}:
        return False
    if repo_name.endswith(".git") or "/" in repo_name or "\\" in repo_name:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_.-]+", repo_name))


def sanitize_azure_module_repo_name(repo_name: str) -> str:
    """Return a safe GitHub repo name while preserving hyphen normalization."""
    value = (repo_name or "").strip().strip("`'\"<>()[]{}")
    if not value:
        return ""

    value = value.replace("https://github.com/", "").replace("git@github.com:", "")
    value = value.split("?", 1)[0].split("#", 1)[0].strip("/")

    if "/" in value:
        value = value.rsplit("/", 1)[-1]

    value = re.sub(r"\.git$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"[\s_]+", "-", value.lower())
    value = re.sub(r"[^a-z0-9.-]", "-", value)
    value = re.sub(r"-+", "-", value).strip(".-")

    if not is_valid_github_repo_name(value):
        return ""

    return value[:100]


def terraform_label_from_repo_name(repo_name: str, fallback: str = "azure_module") -> str:
    label = (repo_name or fallback or "azure_module").strip().lower()
    label = re.sub(r"[^a-z0-9_]+", "_", label.replace("-", "_").replace(".", "_"))
    label = re.sub(r"_+", "_", label).strip("_")

    if not label:
        label = fallback or "azure_module"
    if not re.match(r"^[a-z_]", label):
        label = f"repo_{label}"

    return label[:100]


def _candidate_azure_repo_name_from_text(value: str) -> str:
    candidate = (value or "").strip().strip("`'\"")
    if not candidate:
        return ""

    candidate = re.split(
        r"(?:\s+for\s+)|(?:\s+please\b)|(?:\s+and\b)|(?:\s+then\b)|[,;\n]",
        candidate,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip().strip("`'\".:)")
    candidate = re.sub(r"\s+", " ", candidate).strip()

    if re.match(r"^(?:for|first)\b", candidate, re.IGNORECASE):
        return ""

    stop_values = {
        "a", "an", "the", "first", "new", "module", "repo", "repository",
        "azure", "terraform", "please", "one", "it", "this", "that",
        "custom", "name", "new repo", "new repository", "module repo",
        "module repository", "azure module", "azure repo", "azure repository",
        "yes", "y", "no", "n", "create", "make", "build", "for",
        "named", "called", "as",
    }
    if not candidate or candidate.lower() in stop_values:
        return ""

    return sanitize_azure_module_repo_name(candidate)


def extract_requested_azure_module_repo_name(prompt: str) -> str:
    """Extract an explicit custom Azure module repo name from user text, if provided."""
    text = re.sub(r"\s+", " ", (prompt or "").strip())
    if not text:
        return ""

    patterns = [
        r"\b(?:target_)?(?:module_)?repo(?:sitory)?[_ -]?name\s*(?:is|=|:)?\s*[`'\"]?([A-Za-z0-9][A-Za-z0-9_. \-]{1,120})",
        r"\b(?:repo|repository)\s+(?:named|called)\s+[`'\"]?([A-Za-z0-9][A-Za-z0-9_. \-]{1,120})",
        r"\b(?:named|called|call\s+it|name\s+it)\s+[`'\"]?([A-Za-z0-9][A-Za-z0-9_. \-]{1,120})",
        r"\b(?:create|make|build)\s+(?:a\s+|an\s+|the\s+)?(?:new\s+)?(?:azure\s+)?(?:module\s+)?(?:repo|repository)\s+(?!for\b|first\b)(?:named\s+|called\s+|as\s+)?[`'\"]?([A-Za-z0-9][A-Za-z0-9_. \-]{1,120})",
        r"\buse\s+(?:repo|repository)\s+[`'\"]?([A-Za-z0-9][A-Za-z0-9_. \-]{1,120})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue

        candidate = _candidate_azure_repo_name_from_text(match.group(1))
        if candidate:
            return candidate

    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{1,120}", text):
        return _candidate_azure_repo_name_from_text(text)

    return ""


def build_azure_module_creation_prompt_with_repo_name(original_prompt: str, repo_name_source: str = "") -> str:
    repo_name = (
        extract_requested_azure_module_repo_name(repo_name_source)
        or extract_requested_azure_module_repo_name(original_prompt)
    )
    original_prompt = (original_prompt or "").strip()
    if not repo_name:
        return original_prompt
    if repo_name in original_prompt.lower():
        return original_prompt
    return f"{original_prompt}\n\nRequested Azure module repo name: {repo_name}"


def extract_azure_module_repo_name_from_confirmation_reply(reply: str) -> str:
    repo_name = extract_requested_azure_module_repo_name(reply)
    if repo_name:
        return repo_name

    cleaned = (reply or "").strip().strip("`'\"")
    normalized = normalize_yes_no_reply(cleaned)
    if normalized in AFFIRMATIVE_REPLIES or normalized in NEGATIVE_REPLIES:
        return ""
    if re.search(r"\s", cleaned):
        return ""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{1,99}", cleaned):
        return ""

    return sanitize_azure_module_repo_name(cleaned)


def _extract_hcl_string_assignment(tf_content: str, key: str) -> str:
    match = re.search(
        rf'^\s*{re.escape(key)}\s*=\s*"([^"]*)"',
        tf_content or "",
        re.MULTILINE,
    )
    return match.group(1).strip() if match else ""


def _validate_azure_repo_merge_commit_settings(tf_content: str) -> None:
    merge_commit_title = _extract_hcl_string_assignment(tf_content, "merge_commit_title")
    merge_commit_message = _extract_hcl_string_assignment(tf_content, "merge_commit_message")

    if merge_commit_title not in ALLOWED_GITHUB_MERGE_COMMIT_TITLES:
        allowed = ", ".join(sorted(ALLOWED_GITHUB_MERGE_COMMIT_TITLES))
        raise ValueError(
            "azure_module_repo_creation must set merge_commit_title to one of: "
            f"{allowed}."
        )

    if merge_commit_message not in ALLOWED_GITHUB_MERGE_COMMIT_MESSAGES:
        allowed = ", ".join(sorted(ALLOWED_GITHUB_MERGE_COMMIT_MESSAGES))
        raise ValueError(
            "azure_module_repo_creation must set merge_commit_message to one of: "
            f"{allowed}."
        )


def infer_azure_module_resource_slug(original_prompt: str) -> str:
    text = (original_prompt or "").strip().lower()
    explicit = re.search(r"(?:module|repo|repository)\s+(?:for\s+)?([a-z0-9][a-z0-9 _-]{1,80})", text)
    if explicit:
        text = explicit.group(1)

    replacements = {
        "virtual machine": "vm",
        "linux virtual machine": "linux vm",
        "windows virtual machine": "windows vm",
    }
    for old, new_value in replacements.items():
        text = text.replace(old, new_value)

    tokens = re.findall(r"[a-z0-9]+", text)
    stop_words = {
        "azure", "terraform", "module", "repo", "repository", "resource",
        "create", "creating", "new", "update", "for", "with", "and",
        "the", "a", "an", "to", "of", "in", "on", "using", "use",
        "need", "please", "from", "into", "this", "that", "it", "first",
        "empty", "github", "definition", "pr", "allow", "allows", "name",
        "named", "called", "as", "requested",
    }
    resource_tokens = [token for token in tokens if token not in stop_words]

    if not resource_tokens:
        resource_tokens = ["module"]

    slug = "-".join(resource_tokens[:6])
    slug = re.sub(r"[^a-z0-9-]", "-", slug).strip("-")
    slug = re.sub(r"-+", "-", slug)
    return slug or "module"


def generate_azure_module_repo_creation_with_agent(
    conversation_id: str,
    original_prompt: str,
    requested_repo_name: str = "",
) -> dict:
    """Generate Azure module-repository Terraform exclusively through Foundry.

    The backend supplies the resolved user request and repository evidence; it
    never constructs Terraform/HCL itself. Any requested repository name is
    passed to Foundry as user intent, not converted into backend-owned code.
    """
    request = {
        "task": "Generate the requested Azure module repository Terraform using the live repository evidence and Terrabot Foundry instructions.",
        "user_request": str(original_prompt or "").strip(),
        "requested_repo_name": sanitize_azure_module_repo_name(requested_repo_name)
        or extract_requested_azure_module_repo_name(original_prompt),
        "backend_role": "evidence_and_transport_only",
        "rules": [
            "Infer the repository workflow and Terraform structure from supplied live repository evidence.",
            "Generate all Terraform/HCL in Foundry; the backend must not synthesize Terraform.",
            "Return the normal Terrabot infrastructure JSON payload.",
        ],
    }
    _conversation_id, agent_reply = call_agent(
        conversation_id or None,
        json.dumps(request, ensure_ascii=False),
    )
    if not str(agent_reply or "").strip():
        raise RuntimeError("No response returned from Foundry for Azure module repository generation.")
    return try_parse_agent_output(agent_reply)

def cloud_root_dir(cloud: Any | None, repo_target: Optional[str] = None, workflow: Optional[str] = None) -> str:
    cloud = normalize_cloud(cloud)
    repo_target = normalize_repo_target(cloud, repo_target, workflow)

    if cloud == "aws":
        root = GITHUB_AWS_DIR
    elif repo_target == "vena_repos":
        root = GITHUB_VENA_DIR
    else:
        root = GITHUB_AZURE_DIR

    return (root or ".").strip().strip("/")


def stable_thread_key(thread_id: str) -> str:
    raw = (thread_id or "default-thread").strip()
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def build_stable_folder(thread_id: str, cloud: str, repo_target: Optional[str] = None, workflow: Optional[str] = None) -> str:
    cloud = normalize_cloud(cloud)
    repo_target = normalize_repo_target(cloud, repo_target, workflow)
    root = cloud_root_dir(cloud, repo_target=repo_target, workflow=workflow)

    # Azure repo-definition PRs must write directly into terraform-github/vena_repos.
    if cloud == "azure" and repo_target == "vena_repos":
        return root or "."

    # Azure consumer PRs must write directly into tf-azure-hub root or configured root.
    if cloud == "azure" and repo_target == "tf-azure-hub":
        return root or "."

    bucket = state_bucket_for_target(cloud, repo_target=repo_target, workflow=workflow)
    suffix = f"changes/{stable_thread_key(thread_id)}/{bucket}"
    return suffix if root in ("", ".") else f"{root}/{suffix}"


def build_branch_prefix(thread_id: str, cloud: str, repo_target: Optional[str] = None, workflow: Optional[str] = None) -> str:
    cloud = normalize_cloud(cloud)
    bucket = state_bucket_for_target(cloud, repo_target=repo_target, workflow=workflow)
    base_prefix = github_pr_source_branch_for_cloud(cloud, repo_target=repo_target, workflow=workflow).strip()
    thread_suffix = stable_thread_key(thread_id)
    return f"{base_prefix}-{bucket}-{thread_suffix}"


def build_branch_name(thread_id: str, cloud: str, cycle: int, repo_target: Optional[str] = None, workflow: Optional[str] = None) -> str:
    prefix = build_branch_prefix(thread_id, cloud, repo_target=repo_target, workflow=workflow)
    cycle = max(1, int(cycle or 1))
    return prefix if cycle == 1 else f"{prefix}-v{cycle}"


def parse_branch_cycle(branch_name: str, prefix: str) -> int:
    branch_name = (branch_name or "").strip()
    prefix = (prefix or "").strip()

    if branch_name == prefix:
        return 1

    match = re.fullmatch(rf"{re.escape(prefix)}-v(\d+)", branch_name)
    if match:
        return int(match.group(1))

    return 0



