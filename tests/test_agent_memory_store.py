import importlib
import json

import pytest


@pytest.fixture()
def memory_module(tmp_path, monkeypatch):
    """Reload agent_memory_store pointed at an isolated cache file per test."""
    monkeypatch.setenv("TERRABOT_AGENT_MEMORY_CACHE_FILE", str(tmp_path / "memory-cache.jsonl"))
    monkeypatch.delenv("TERRABOT_STATE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("TERRABOT_STATE_STORAGE_ACCOUNT_URL", raising=False)
    from shared_code import agent_memory_store

    module = importlib.reload(agent_memory_store)
    # Force the Table Storage backend off regardless of ambient environment.
    module._TABLE_CLIENT = None
    module._TABLE_UNAVAILABLE = True
    yield module


def test_record_and_read_conversation_memory(memory_module):
    memory_module.record_agent_turn(
        conversation_id="conv-1",
        cloud="azure",
        repo_target="tf-azure-hub",
        workflow="azure_consumer_generation",
        requester="alice",
        prompt="create a storage account in dev",
        files_searched=["envs/dev/main.tf", "modules/storage/main.tf"],
        context_retrieved_summary="2 repository file(s) supplied as context",
        code_generated_summary="generated/modified files: envs/dev/main.tf",
        response_summary="Added storage account block to envs/dev/main.tf.",
    )

    context = memory_module.get_conversation_memory_context("conv-1")
    assert "create a storage account in dev" in context
    assert "envs/dev/main.tf" in context


def test_centralized_memory_is_shared_across_conversations(memory_module):
    memory_module.record_agent_turn(
        conversation_id="conv-a",
        cloud="aws",
        repo_target="tf-aws-modules",
        prompt="add an s3 bucket for logging",
        response_summary="Created bucket in modules/s3/main.tf",
    )

    # A different conversation targeting the same cloud/repo should see the
    # earlier user's cached activity in the centralized memory context.
    centralized = memory_module.get_centralized_memory_context("aws", "tf-aws-modules")
    assert "s3 bucket" in centralized

    combined = memory_module.get_combined_memory_context(
        conversation_id="conv-b", cloud="aws", repo_target="tf-aws-modules"
    )
    assert "s3 bucket" in combined
    assert "Other cached turns for cloud=aws repo_target=tf-aws-modules" in combined


def test_combined_memory_context_empty_when_nothing_cached(memory_module):
    assert memory_module.get_combined_memory_context(conversation_id="conv-empty") == ""


def test_extract_topic_tags_derives_meaningful_keywords(memory_module):
    tags = memory_module.extract_topic_tags("disable mcp waf rules in dev_aws global")
    assert "waf" in tags
    assert "mcp" in tags
    assert "rules" in tags


def test_relevance_ranked_retrieval_surfaces_topically_matching_entry_over_recent_unrelated_ones(memory_module):
    """Regression: "what are the mcp waf rules?" must be able to retrieve an
    earlier "disable mcp waf rules" resolution even if unrelated requests
    happened in between, not just the most recent N entries."""
    memory_module.record_agent_turn(
        conversation_id="conv-topic",
        cloud="aws",
        repo_target="tf-devops",
        prompt="disable mcp waf rules in dev_aws global",
        response_summary="Set mcp_waf_bot_control_enabled to false in waf.tf.",
    )
    for index in range(5):
        memory_module.record_agent_turn(
            conversation_id="conv-topic",
            cloud="aws",
            repo_target="tf-devops",
            prompt=f"create an unrelated s3 bucket number {index}",
            response_summary=f"Created bucket {index}.",
        )

    # Recency-only retrieval (no prompt) would miss the waf resolution once
    # more than max_entries unrelated turns have happened.
    recency_only = memory_module.get_conversation_memory_context("conv-topic", max_entries=3)
    assert "mcp_waf_bot_control_enabled" not in recency_only

    relevance_ranked = memory_module.get_conversation_memory_context(
        "conv-topic", max_entries=3, prompt="what are the mcp waf rules?"
    )
    assert "mcp_waf_bot_control_enabled" in relevance_ranked


def test_combined_memory_context_with_prompt_ranks_by_relevance(memory_module):
    memory_module.record_agent_turn(
        conversation_id="conv-b2",
        cloud="aws",
        repo_target="tf-devops",
        prompt="disable mcp waf rules",
        response_summary="Resolved to mcp_waf_bot_control_enabled = false.",
    )
    context = memory_module.get_combined_memory_context(
        conversation_id="conv-b2", cloud="aws", repo_target="tf-devops", prompt="mcp waf rules again"
    )
    assert "mcp_waf_bot_control_enabled" in context


def test_clear_conversation_memory(memory_module):
    memory_module.record_agent_turn(conversation_id="conv-clear", prompt="hello")
    assert memory_module.get_conversation_memory_context("conv-clear")
    memory_module.clear_conversation_memory("conv-clear")
    assert memory_module.get_conversation_memory_context("conv-clear") == ""


def test_local_cache_file_is_append_only_jsonl(memory_module, tmp_path):
    memory_module.record_agent_turn(conversation_id="conv-file", prompt="one")
    memory_module.record_agent_turn(conversation_id="conv-file", prompt="two")

    cache_file = memory_module.CACHE_FILE_PATH
    assert cache_file.exists()
    lines = [json.loads(line) for line in cache_file.read_text().splitlines() if line.strip()]
    assert len(lines) >= 2
    assert all(line["memory_key"] == "conversation:conv-file" for line in lines)
