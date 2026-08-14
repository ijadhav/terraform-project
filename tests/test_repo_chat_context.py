from shared_code.repo_chat_context import (
    find_relevant_repo_files,
    build_live_repo_chat_context,
)


SAMPLE_TREE = [
    "envs/dev/main.tf",
    "envs/prd/main.tf",
    "modules/storage/main.tf",
    "modules/storage/variables.tf",
    "README.md",
    "scripts/deploy.sh",
]


def test_find_relevant_repo_files_matches_keywords():
    matches = find_relevant_repo_files("update the storage module variables", SAMPLE_TREE)
    assert "modules/storage/variables.tf" in matches
    assert "modules/storage/main.tf" in matches
    assert "scripts/deploy.sh" not in matches


def test_find_relevant_repo_files_returns_empty_for_no_overlap():
    assert find_relevant_repo_files("what time is it", SAMPLE_TREE) == []


def test_build_live_repo_chat_context_fetches_matched_files(monkeypatch):
    from shared_code import repo_chat_context

    monkeypatch.setattr(repo_chat_context, "list_repo_tree_paths", lambda *a, **k: SAMPLE_TREE)

    def fake_fetch(owner, repo, path, ref="main", token=None):
        return f"# content of {path}"

    monkeypatch.setattr(repo_chat_context, "fetch_repo_file_content", fake_fetch)

    result = build_live_repo_chat_context(
        "what does the storage module contain?", owner="org", repo="repo"
    )
    assert result["paths"]
    assert "modules/storage/main.tf" in result["paths"]
    assert "LIVE REPOSITORY CONTEXT" in result["context_block"]
    assert "content of modules/storage/main.tf" in result["context_block"]


def test_build_live_repo_chat_context_empty_when_no_match(monkeypatch):
    from shared_code import repo_chat_context

    monkeypatch.setattr(repo_chat_context, "list_repo_tree_paths", lambda *a, **k: SAMPLE_TREE)

    result = build_live_repo_chat_context("hello there", owner="org", repo="repo")
    assert result["paths"] == []
    assert result["context_block"] == ""
