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

_TABLE_NAME = os.getenv("TERRABOT_TEST_RUNNER_STATE_TABLE", "TerrabotAutomatedTestRuns").strip() or "TerrabotAutomatedTestRuns"
_QUEUE_NAME = os.getenv("TERRABOT_TEST_RUNNER_QUEUE_NAME", "terrabot-automated-tests").strip() or "terrabot-automated-tests"


def _connection_string() -> str:
    value = (
        os.getenv("TERRABOT_TEST_RUNNER_STORAGE_CONNECTION_STRING")
        or os.getenv("AzureWebJobsStorage")
        or ""
    ).strip()
    if not value:
        raise RuntimeError(
            "Missing TERRABOT_TEST_RUNNER_STORAGE_CONNECTION_STRING/AzureWebJobsStorage."
        )
    return value


def _parse_connection_string() -> dict[str, str]:
    result: dict[str, str] = {}
    for part in _connection_string().split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        result[key.strip()] = value.strip()
    if not result.get("AccountName") or not result.get("AccountKey"):
        raise RuntimeError(
            "The automated-test queue currently requires an Azure Storage connection "
            "string containing AccountName and AccountKey."
        )
    return result


def _table_client():
    service = TableServiceClient.from_connection_string(_connection_string())
    service.create_table_if_not_exists(_TABLE_NAME)
    return service.get_table_client(_TABLE_NAME)


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
        "run_mode": str(item.get("run_mode") or "regression"),
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



def save_context_candidate(owner_hash: str, run_id: str, candidate: dict[str, Any]) -> None:
    candidate_id = str((candidate or {}).get("candidate_id") or "").strip()
    if not candidate_id:
        raise ValueError("candidate_id is required for context-candidate state.")
    entity = {
        "PartitionKey": owner_hash,
        "RowKey": f"candidate::{run_id}::{candidate_id}",
        "entity_type": "context_candidate",
        "run_id": run_id,
        "candidate_id": candidate_id,
        "status": str((candidate or {}).get("status") or "candidate"),
        "updated_at": utc_now(),
        "payload_json": json.dumps(candidate or {}, ensure_ascii=False)[:60000],
    }
    _table_client().upsert_entity(entity=entity, mode=UpdateMode.REPLACE)


def load_context_candidates(owner_hash: str, run_id: str) -> list[dict[str, Any]]:
    rows = _table_client().query_entities(
        query_filter=f"PartitionKey eq '{owner_hash}' and entity_type eq 'context_candidate' and run_id eq '{run_id}'"
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        try:
            result.append(json.loads(str(row.get("payload_json") or "{}")))
        except Exception:
            continue
    return result


def update_context_candidate_status(owner_hash: str, run_id: str, candidate_id: str, status: str, **fields: Any) -> None:
    row_key = f"candidate::{run_id}::{candidate_id}"
    table = _table_client()
    try:
        entity = dict(table.get_entity(partition_key=owner_hash, row_key=row_key))
        payload = json.loads(str(entity.get("payload_json") or "{}"))
    except Exception:
        payload = {"candidate_id": candidate_id, "run_id": run_id}
    payload.update(fields)
    payload["status"] = status
    save_context_candidate(owner_hash, run_id, payload)


def load_coverage(repo_full_name: str) -> dict[str, dict[str, Any]]:
    partition = "coverage::" + hashlib.sha256(str(repo_full_name or "").lower().encode()).hexdigest()[:24]
    rows = _table_client().query_entities(
        query_filter=f"PartitionKey eq '{partition}' and entity_type eq 'coverage'"
    )
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        try:
            payload = json.loads(str(row.get("payload_json") or "{}"))
        except Exception:
            payload = {}
        key = str(payload.get("coverage_key") or row.get("coverage_key") or "")
        if key:
            result[key] = payload
    return result


def save_coverage(repo_full_name: str, coverage_key: str, payload: dict[str, Any]) -> None:
    partition = "coverage::" + hashlib.sha256(str(repo_full_name or "").lower().encode()).hexdigest()[:24]
    current = dict(payload or {})
    current["coverage_key"] = coverage_key
    entity = {
        "PartitionKey": partition,
        "RowKey": "coverage::" + hashlib.sha256(coverage_key.encode()).hexdigest()[:32],
        "entity_type": "coverage",
        "coverage_key": coverage_key,
        "updated_at": utc_now(),
        "payload_json": json.dumps(current, ensure_ascii=False)[:60000],
    }
    _table_client().upsert_entity(entity=entity, mode=UpdateMode.REPLACE)

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


def _queue_request(method: str, url: str, *, body: bytes = b"") -> requests.Response:
    cfg = _parse_connection_string()
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


def enqueue_run(message: dict[str, Any]) -> None:
    cfg = _parse_connection_string()
    account = cfg["AccountName"]
    endpoint = cfg.get("QueueEndpoint") or f"https://{account}.queue.core.windows.net"
    queue_url = endpoint.rstrip("/") + "/" + quote(_QUEUE_NAME, safe="-")
    create = _queue_request("PUT", queue_url + "?restype=queue")
    if create.status_code not in {201, 204, 409}:
        raise RuntimeError(
            f"Unable to create/access automated-test queue {_QUEUE_NAME}: "
            f"HTTP {create.status_code} {create.text[:400]}"
        )
    # Azure Functions queue bindings are configured with MessageEncoding=Base64.
    # Encode the JSON payload once here; the Functions host decodes it before
    # exposing QueueMessage.get_body() to the Python worker.
    raw_message = json.dumps(message, ensure_ascii=False).encode("utf-8")
    message_text = base64.b64encode(raw_message).decode("ascii")
    body = f"<QueueMessage><MessageText>{message_text}</MessageText></QueueMessage>".encode("utf-8")
    response = _queue_request("POST", queue_url + "/messages", body=body)
    if response.status_code != 201:
        raise RuntimeError(
            f"Unable to enqueue Terrabot automated test run: HTTP {response.status_code} "
            f"{response.text[:500]}"
        )
