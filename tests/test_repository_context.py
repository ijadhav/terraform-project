from __future__ import annotations

from shared_code import repository_context as rc


FILES = {
    "main.tf": '''module "network" {\n  source = "../../modules/network"\n  enable_private_endpoints = true\n}\n''',
    "README.md": "All Terraform changes must pass terraform fmt and terraform validate.\n",
}


def evidence_fetcher(owner: str, repo: str, path: str, ref: str):
    del owner, repo, ref
    return FILES.get(path)


def candidate(statement: str = "The network module enables private endpoints through a Boolean input."):
    return {
        "category": "implementation_decision",
        "subject": "network private endpoints",
        "scope": "module/network",
        "statement": statement,
        "confidence": 0.95,
        "evidence": [
            {
                "path": "main.tf",
                "excerpt": 'module "network" {\n  source = "../../modules/network"\n  enable_private_endpoints = true\n}',
                "reason": "Consumer wiring shows the feature flag.",
            }
        ],
        "validation_summary": "Stable consumer wiring convention.",
    }


def install_in_memory_store(monkeypatch):
    store = {}

    def upload(record):
        store[record.id] = record

    def query(repo_full_name, identity_key):
        return [
            item
            for item in store.values()
            if item.repo_full_name == repo_full_name and item.identity_key == identity_key
        ]

    def get_by_id(context_id):
        return store.get(context_id)

    def merge(context_id, **fields):
        record = store[context_id]
        for key, value in fields.items():
            if key == "updated_at" and hasattr(value, "isoformat"):
                value = value.isoformat()
            setattr(record, key, value)

    monkeypatch.setattr(rc, "_upload_record", upload)
    monkeypatch.setattr(rc, "_query_identity_records", query)
    monkeypatch.setattr(rc, "get_repository_context_by_id", get_by_id)
    monkeypatch.setattr(rc, "_merge_status_fields", merge)
    return store


def test_candidate_must_match_repository_evidence():
    bad = candidate()
    bad["evidence"][0]["excerpt"] = "this text is not in the repository"
    result = rc.validate_repository_context_candidate(
        bad,
        repo_owner="org",
        repo_name="repo",
        evidence_ref="abc123",
        evidence_fetcher=evidence_fetcher,
    )
    assert result["valid"] is False
    assert any("none of the supplied evidence" in item for item in result["errors"])


def test_add_detects_duplicate_and_refreshes_evidence(monkeypatch):
    store = install_in_memory_store(monkeypatch)
    first = rc.add_repository_context(
        repo_owner="org",
        repo_name="repo",
        evidence_commit_sha="commit-1",
        evidence_branch="main",
        source_task_hash="task-1",
        candidate=candidate(),
        evidence_fetcher=evidence_fetcher,
    )
    second = rc.add_repository_context(
        repo_owner="org",
        repo_name="repo",
        evidence_commit_sha="commit-2",
        evidence_branch="main",
        source_task_hash="task-2",
        candidate=candidate(),
        evidence_fetcher=evidence_fetcher,
    )

    assert first["action"] == "created"
    assert second["action"] == "duplicate_refreshed"
    assert first["record"]["id"] == second["record"]["id"]
    assert len(store) == 1
    assert next(iter(store.values())).evidence_commit_sha == "commit-2"


def test_conflicting_context_preserves_both_versions(monkeypatch):
    store = install_in_memory_store(monkeypatch)
    first = rc.add_repository_context(
        repo_owner="org",
        repo_name="repo",
        evidence_commit_sha="commit-1",
        evidence_branch="main",
        source_task_hash="task-1",
        candidate=candidate(),
        evidence_fetcher=evidence_fetcher,
    )
    conflicting = candidate("The network module does not use the private endpoint Boolean input.")
    second = rc.add_repository_context(
        repo_owner="org",
        repo_name="repo",
        evidence_commit_sha="commit-2",
        evidence_branch="main",
        source_task_hash="task-2",
        candidate=conflicting,
        evidence_fetcher=evidence_fetcher,
    )

    assert second["action"] == "conflict_recorded"
    assert len(store) == 2
    first_record = store[first["record"]["id"]]
    second_record = store[second["record"]["id"]]
    assert first_record.status == "conflicted"
    assert second_record.status == "conflicted"
    assert second_record.id in first_record.conflict_with_ids
    assert first_record.id in second_record.conflict_with_ids


def test_update_versions_record_without_overwrite(monkeypatch):
    store = install_in_memory_store(monkeypatch)
    first = rc.add_repository_context(
        repo_owner="org",
        repo_name="repo",
        evidence_commit_sha="commit-1",
        evidence_branch="main",
        source_task_hash="task-1",
        candidate=candidate(),
        evidence_fetcher=evidence_fetcher,
    )
    updated_candidate = candidate("The network module enables private endpoints with enable_private_endpoints = true.")
    updated = rc.update_repository_context(
        context_id=first["record"]["id"],
        repo_owner="org",
        repo_name="repo",
        evidence_commit_sha="commit-2",
        evidence_branch="main",
        source_task_hash="task-2",
        candidate=updated_candidate,
        evidence_fetcher=evidence_fetcher,
    )

    assert updated["updated"] is True
    assert len(store) == 2
    assert store[first["record"]["id"]].status == "superseded"
    assert store[updated["record"]["id"]].supersedes_id == first["record"]["id"]


def test_invalidate_preserves_history(monkeypatch):
    store = install_in_memory_store(monkeypatch)
    created = rc.add_repository_context(
        repo_owner="org",
        repo_name="repo",
        evidence_commit_sha="commit-1",
        evidence_branch="main",
        source_task_hash="task-1",
        candidate=candidate(),
        evidence_fetcher=evidence_fetcher,
    )
    context_id = created["record"]["id"]
    result = rc.invalidate_repository_context(
        context_id=context_id,
        reason="Repository code removed this convention.",
        current_commit_sha="commit-3",
    )
    assert result["invalidated"] is True
    assert context_id in store
    assert store[context_id].status == "invalidated"


def test_agent_context_marks_stale_and_conflicted():
    record = rc.RepositoryContextRecord(
        id="rcx_1",
        repo_owner="org",
        repo_name="repo",
        repo_full_name="org/repo",
        identity_key="idkey",
        statement_key="stmtkey",
        category="coding_convention",
        subject="formatting",
        scope="repository",
        statement="Terraform files must pass terraform fmt.",
        evidence_paths=["README.md"],
        evidence_json="[]",
        evidence_commit_sha="old",
        evidence_branch="main",
        evidence_hash="ev",
        status="conflicted",
        confidence=0.9,
        validation_status="validated",
        validation_summary="README evidence.",
        source_task_hash="task",
        created_at="2026-08-18T00:00:00+00:00",
        updated_at="2026-08-18T00:00:00+00:00",
        conflict_with_ids=["rcx_2"],
    )
    block = rc.format_repository_context_for_agent(
        {"results": [record.to_public_dict(current_commit_sha="new")]}
    )
    assert "STALE" in block
    assert "CONFLICTED" in block
    assert "README.md" in block


def test_tool_schema_exposes_required_capabilities():
    names = {item["name"] for item in rc.repository_context_tool_schemas()}
    assert names == {
        "search_repository_context",
        "add_repository_context",
        "update_repository_context",
        "invalidate_repository_context",
    }
