"""Durable state and Azure Queue transport for Terrabot automated test runs."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from email.utils import format_datetime
from html import escape as xml_escape
from typing import Any
from urllib.parse import parse_qsl, quote, urlparse

import requests
from azure.data.tables import TableServiceClient, UpdateMode
from azure.identity import DefaultAzureCredential

_TABLE_NAME = os.getenv("TERRABOT_TEST_RUNNER_STATE_TABLE", "TerrabotAutomatedTestRuns").strip() or "TerrabotAutomatedTestRuns"
_QUEUE_NAME = os.getenv("TERRABOT_TEST_RUNNER_QUEUE_NAME", "terrabot-automated-tests").strip() or "terrabot-automated-tests"


def _connection_string() -> str:
    """Return a real Storage connection string when one is configured.

    Azure Functions may configure ``AzureWebJobsStorage`` with managed identity
    using the double-underscore settings instead of a secret connection string.
    In that case this function intentionally returns an empty string and the
    clients below use DefaultAzureCredential.
    """
    return (
        os.getenv("TERRABOT_TEST_RUNNER_STORAGE_CONNECTION_STRING")
        or os.getenv("AzureWebJobsStorage")
        or ""
    ).strip()


def _parse_connection_string() -> dict[str, str]:
    result: dict[str, str] = {}
    value = _connection_string()
    if not value:
        return result
    for part in value.split(";"):
        if "=" not in part:
            continue
        key, item_value = part.split("=", 1)
        result[key.strip()] = item_value.strip()
    return result


def _storage_account_name() -> str:
    """Resolve the storage account used by the automated-test queue/state.

    Supports both an explicit test-runner setting and Azure Functions'
    identity-based ``AzureWebJobsStorage__accountName`` convention.
    """
    cfg = _parse_connection_string()
    account = str(cfg.get("AccountName") or "").strip()
    if account:
        return account

    for name in (
        "TERRABOT_TEST_RUNNER_STORAGE_ACCOUNT_NAME",
        "AzureWebJobsStorage__accountName",
        "AZURE_STORAGE_ACCOUNT_NAME",
    ):
        value = str(os.getenv(name) or "").strip()
        if value:
            return value

    # Identity-based Functions configuration may provide service URIs without
    # accountName. Derive the account from those URIs when available.
    for name in (
        "AzureWebJobsStorage__queueServiceUri",
        "AzureWebJobsStorage__tableServiceUri",
        "TERRABOT_TEST_RUNNER_QUEUE_SERVICE_URI",
        "TERRABOT_TEST_RUNNER_TABLE_SERVICE_URI",
    ):
        value = str(os.getenv(name) or "").strip()
        if not value:
            continue
        host = urlparse(value).hostname or ""
        if host:
            return host.split(".", 1)[0]

    raise RuntimeError(
        "Unable to resolve the automated-test Azure Storage account. Configure "
        "TERRABOT_TEST_RUNNER_STORAGE_ACCOUNT_NAME or "
        "AzureWebJobsStorage__accountName when AzureWebJobsStorage uses managed identity."
    )


def _table_service_uri() -> str:
    explicit = (
        os.getenv("TERRABOT_TEST_RUNNER_TABLE_SERVICE_URI")
        or os.getenv("AzureWebJobsStorage__tableServiceUri")
        or ""
    ).strip()
    if explicit:
        return explicit.rstrip("/")
    return f"https://{_storage_account_name()}.table.core.windows.net"


def _queue_service_uri() -> str:
    explicit = (
        os.getenv("TERRABOT_TEST_RUNNER_QUEUE_SERVICE_URI")
        or os.getenv("AzureWebJobsStorage__queueServiceUri")
        or ""
    ).strip()
    if explicit:
        return explicit.rstrip("/")
    return f"https://{_storage_account_name()}.queue.core.windows.net"


def _credential() -> DefaultAzureCredential:
    client_id = (
        os.getenv("TERRABOT_TEST_RUNNER_MANAGED_IDENTITY_CLIENT_ID")
        or os.getenv("AzureWebJobsStorage__clientId")
        or os.getenv("AZURE_CLIENT_ID")
        or ""
    ).strip()
    if client_id:
        return DefaultAzureCredential(managed_identity_client_id=client_id)
    return DefaultAzureCredential()


def _table_client():
    connection_string = _connection_string()
    cfg = _parse_connection_string()
    if connection_string and cfg.get("AccountName") and cfg.get("AccountKey"):
        service = TableServiceClient.from_connection_string(connection_string)
    else:
        service = TableServiceClient(
            endpoint=_table_service_uri(),
            credential=_credential(),
        )
    service.create_table_if_not_exists(_TABLE_NAME)
    return service.get_table_client(_TABLE_NAME)


def _canonicalized_resource(account: str, parsed_url) -> str:
    resource = f"/{account}{parsed_url.path or '/'}"
    query_pairs = parse_qsl(parsed_url.query, keep_blank_values=True)
    if not query_pairs:
        return resource
    grouped: dict[str, list[str]] = {}
    for key, value in query_pairs:
        grouped.setdefault(key.lower(), []).append(value)
    for key in sorted(grouped):
        resource += "\n" + key + ":" + ",".join(sorted(grouped[key]))
    return resource


def _shared_key_queue_request(
    method: str,
    url: str,
    *,
    body: bytes = b"",
    cfg: dict[str, str],
) -> requests.Response:
    account = cfg["AccountName"]
    key = base64.b64decode(cfg["AccountKey"])
    parsed = urlparse(url)
    x_ms_date = format_datetime(datetime.now(timezone.utc), usegmt=True)
    x_ms_version = "2021-12-02"
    content_type = "application/xml" if body else ""
    content_length = str(len(body)) if body else ""
    canonical_headers = f"x-ms-date:{x_ms_date}\nx-ms-version:{x_ms_version}\n"
    string_to_sign = "\n".join([
        method.upper(), "", "", content_length, "", content_type, "", "", "", "", "", "",
    ]) + "\n" + canonical_headers + _canonicalized_resource(account, parsed)
    signature = base64.b64encode(
        hmac.new(key, string_to_sign.encode("utf-8"), hashlib.sha256).digest()
    ).decode("ascii")
    headers = {
        "x-ms-date": x_ms_date,
        "x-ms-version": x_ms_version,
        "Authorization": f"SharedKey {account}:{signature}",
    }
    if body:
        headers["Content-Type"] = content_type
        headers["Content-Length"] = str(len(body))
    return requests.request(method, url, headers=headers, data=body or None, timeout=30)


def _identity_queue_request(method: str, url: str, *, body: bytes = b"") -> requests.Response:
    """Call Azure Queue REST using the Function App managed identity."""
    token = _credential().get_token("https://storage.azure.com/.default").token
    headers = {
        "Authorization": f"Bearer {token}",
        "x-ms-version": "2021-12-02",
        "x-ms-date": format_datetime(datetime.now(timezone.utc), usegmt=True),
    }
    if body:
        headers["Content-Type"] = "application/xml"
        headers["Content-Length"] = str(len(body))
    return requests.request(method, url, headers=headers, data=body or None, timeout=30)


def _queue_request(method: str, url: str, *, body: bytes = b"") -> requests.Response:
    cfg = _parse_connection_string()
    if cfg.get("AccountName") and cfg.get("AccountKey"):
        return _shared_key_queue_request(method, url, body=body, cfg=cfg)
    return _identity_queue_request(method, url, body=body)


def enqueue_run(message: dict[str, Any]) -> None:
    cfg = _parse_connection_string()
    endpoint = str(cfg.get("QueueEndpoint") or "").strip() or _queue_service_uri()
    queue_url = endpoint.rstrip("/") + "/" + quote(_QUEUE_NAME, safe="-")
    create = _queue_request("PUT", queue_url + "?restype=queue")
    if create.status_code not in {201, 204, 409}:
        raise RuntimeError(
            f"Unable to create/access automated-test queue {_QUEUE_NAME}: "
            f"HTTP {create.status_code} {create.text[:400]}"
        )
    message_text = xml_escape(json.dumps(message, ensure_ascii=False))
    body = f"<QueueMessage><MessageText>{message_text}</MessageText></QueueMessage>".encode("utf-8")
    response = _queue_request("POST", queue_url + "/messages", body=body)
    if response.status_code != 201:
        raise RuntimeError(
            f"Unable to enqueue Terrabot automated test run: HTTP {response.status_code} "
            f"{response.text[:500]}"
        )

def requester_hash(aad_object_id: str) -> str:
    return hashlib.sha256(str(aad_object_id or "").strip().lower().encode("utf-8")).hexdigest()[:24]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_run(run: dict[str, Any]) -> None:
    item = dict(run or {})
    run_id = str(item.get("run_id") or "").strip()
    owner_hash = str(item.get("requester_hash") or "").strip()
    if not run_id or not owner_hash:
        raise ValueError("run_id and requester_hash are required for automated-test state.")
    entity = {
        "PartitionKey": owner_hash,
        "RowKey": f"run::{run_id}",
        "entity_type": "run",
        "run_id": run_id,
        "status": str(item.get("status") or "queued"),
        "requested_cases": int(item.get("requested_cases") or 0),
        "completed_cases": int(item.get("completed_cases") or 0),
        "cloud_filter": str(item.get("cloud_filter") or "all"),
        "created_at": str(item.get("created_at") or utc_now()),
        "updated_at": utc_now(),
        "started_at": str(item.get("started_at") or ""),
        "completed_at": str(item.get("completed_at") or ""),
        "duration_ms": int(item.get("duration_ms") or 0),
        "error": str(item.get("error") or "")[:16000],
        "report": str(item.get("report") or "")[:60000],
        "discovery_errors_json": json.dumps(item.get("discovery_errors") or [], ensure_ascii=False)[:60000],
        "conversation_reference_json": json.dumps(item.get("conversation_reference") or {}, ensure_ascii=False)[:60000],
    }
    _table_client().upsert_entity(entity=entity, mode=UpdateMode.REPLACE)


def save_case_result(owner_hash: str, run_id: str, case_index: int, payload: dict[str, Any]) -> None:
    entity = {
        "PartitionKey": owner_hash,
        "RowKey": f"case::{run_id}::{int(case_index):03d}",
        "entity_type": "case",
        "run_id": run_id,
        "case_index": int(case_index),
        "updated_at": utc_now(),
        "payload_json": json.dumps(payload or {}, ensure_ascii=False)[:60000],
    }
    _table_client().upsert_entity(entity=entity, mode=UpdateMode.REPLACE)


def load_case_results(owner_hash: str, run_id: str) -> list[dict[str, Any]]:
    table = _table_client()
    rows = table.query_entities(
        query_filter=f"PartitionKey eq '{owner_hash}' and entity_type eq 'case' and run_id eq '{run_id}'"
    )
    parsed: list[tuple[int, dict[str, Any]]] = []
    for row in rows:
        try:
            payload = json.loads(str(row.get("payload_json") or "{}"))
        except Exception:
            payload = {}
        parsed.append((int(row.get("case_index") or 0), payload))
    return [payload for _, payload in sorted(parsed, key=lambda value: value[0])]


def latest_run(owner_hash: str) -> dict[str, Any] | None:
    rows = _table_client().query_entities(
        query_filter=f"PartitionKey eq '{owner_hash}' and entity_type eq 'run'"
    )
    items = [dict(row) for row in rows]
    if not items:
        return None
    items.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    return items[0]


def load_run(owner_hash: str, run_id: str) -> dict[str, Any] | None:
    try:
        return dict(_table_client().get_entity(partition_key=owner_hash, row_key=f"run::{run_id}"))
    except Exception:
        return None
