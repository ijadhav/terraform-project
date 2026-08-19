from shared_code.pr_context import (
    match_pull_requests_for_prompt,
    build_pr_context_block,
)


SAMPLE_PULL_REQUESTS = [
    {
        "number": 101,
        "title": "Add checkout storage account in prd",
        "user": {"login": "alice"},
        "head": {"ref": "terrabot/checkout-storage-prd"},
        "base": {"ref": "main"},
        "state": "open",
        "draft": False,
        "html_url": "https://github.com/org/repo/pull/101",
        "updated_at": "2026-08-01T00:00:00Z",
        "body": "Adds a storage account for the checkout service in the prd environment.",
    },
    {
        "number": 102,
        "title": "Bump provider versions",
        "user": {"login": "bob"},
        "head": {"ref": "chore/bump-providers"},
        "base": {"ref": "main"},
        "state": "open",
        "draft": True,
        "html_url": "https://github.com/org/repo/pull/102",
        "updated_at": "2026-07-30T00:00:00Z",
        "body": "Routine dependency bump.",
    },
]


def test_match_pull_requests_ranks_relevant_pr_first():
    matches = match_pull_requests_for_prompt(
        "has anyone already added a storage account for checkout in prd?",
        SAMPLE_PULL_REQUESTS,
    )
    assert matches
    assert matches[0]["number"] == 101


def test_match_pull_requests_returns_empty_when_no_overlap():
    matches = match_pull_requests_for_prompt("what is the capital of France?", SAMPLE_PULL_REQUESTS)
    assert matches == []


def test_build_pr_context_block_formats_matches(monkeypatch):
    from shared_code import pr_context

    monkeypatch.setattr(pr_context, "list_open_pull_requests", lambda *a, **k: SAMPLE_PULL_REQUESTS)

    result = build_pr_context_block(
        "add a storage account for checkout in prd",
        owner="org",
        repo="repo",
        cloud="azure",
    )
    assert result["matches"]
    assert result["matches"][0]["number"] == 101
    assert "PR #101" in result["context_block"]
    assert "cloud=azure" in result["context_block"]


def test_build_pr_context_block_empty_when_no_matches(monkeypatch):
    from shared_code import pr_context

    monkeypatch.setattr(pr_context, "list_open_pull_requests", lambda *a, **k: SAMPLE_PULL_REQUESTS)

    result = build_pr_context_block("unrelated question about lunch", owner="org", repo="repo")
    assert result["matches"] == []
    assert result["context_block"] == ""
