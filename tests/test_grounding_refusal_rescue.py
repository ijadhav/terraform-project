"""Regression tests for rescuing a bare "cannot safely ground exact rule
names" (or "please provide the exact ... names") refusal into a
clarification that presents real, choosable options with short
descriptions from the selected file's live content — instead of asking the
user to recall or type an exact identifier from memory — and for resolving
the user's numbered reply back into a fully-specified instruction.

Bug 1: after correctly resolving the environment and selecting waf.tf, the
agent replied with a dead-end refusal ("Cannot safely disable MCP waf rules
yet because the exact MCP rule names are not grounded in the repository
evidence") instead of asking the user to pick among the named
`rule { name = "..." }` blocks actually declared in that file.

Bug 2 (this round): even after fixing bug 1, the agent asked the user to
"provide the exact waf_blocked_rules entries" — a dead end of a different
shape, since "rules" here are entries in a plain list-of-strings variable,
not nested blocks or Boolean flags, and the user should never have to type
an exact name; they should be shown the actual entries and pick one.
"""
import json
import os
import re

import pytest

os.environ.setdefault("PROJECT_ENDPOINT_STRING", "https://example-fake-endpoint")
os.environ.setdefault("AZURE_AGENT_NAME", "fake-agent")

terrabot_service = pytest.importorskip(
    "shared_code.terrabot_service",
    reason="terrabot_service requires the full Azure/Bot Framework dependency set",
)

WAF_CONTENT = """
resource "aws_wafv2_web_acl" "mcp" {
  name  = "mcp-waf"
  scope = "REGIONAL"

  rule {
    name     = "mcp-bot-control"
    priority = 1
    action {
      block {}
    }
  }

  rule {
    name     = "mcp-rate-limit"
    priority = 2
    action {
      block {}
    }
  }
}
"""

REFUSAL = (
    "Cannot safely disable MCP waf rules yet because the exact MCP rule "
    "names are not grounded in the repository evidence."
)

INFORMATION_SEEKING_REFUSAL = (
    "I can help, but I need exact MCP-related rule names to disable. The repo shows a long "
    "waf_blocked_rules list in terraform/dev_aws/global/waf.tf, but it doesn't label which "
    "entries are specifically MCP-related. Please provide the exact waf_blocked_rules entries "
    "that constitute the MCP set as they appear in terraform/dev_aws/global/waf.tf, so I can "
    "surgically disable only those rules without touching the rest."
)

LIST_LITERAL_CONTENT = """
waf_blocked_rules = [
  "AWSManagedRulesBotControlRuleSet",
  "AWSManagedRulesMcpBotControl",
  "AWSManagedRulesCommonRuleSet",
  "AWSManagedRulesSQLiRuleSet",
]
"""


def test_looks_like_grounding_refusal_matches_real_refusal_text():
    assert terrabot_service._teams_looks_like_grounding_refusal(REFUSAL) is True


def test_looks_like_grounding_refusal_matches_information_seeking_refusal():
    """The second reported failure shape: asking the user to type/recall an
    exact list of entries instead of presenting them as choosable options."""
    assert terrabot_service._teams_looks_like_grounding_refusal(INFORMATION_SEEKING_REFUSAL) is True


def test_looks_like_grounding_refusal_false_for_real_questions():
    assert terrabot_service._teams_looks_like_grounding_refusal(
        "Which WAF rule should be disabled: mcp-bot-control or mcp-rate-limit?"
    ) is False


def test_looks_like_grounding_refusal_false_for_normal_text():
    assert terrabot_service._teams_looks_like_grounding_refusal(
        "Added the storage account to envs/dev/main.tf."
    ) is False


def test_looks_like_grounding_refusal_false_for_reply_with_real_numbered_options():
    """A reply that already presents a good numbered picker must never be
    rewritten, even if it also contains refusal-sounding words."""
    good_reply = (
        "I need to know which rule to disable. Here are the options:\n"
        "1. AWSManagedRulesBotControlRuleSet\n"
        "2. AWSManagedRulesMcpBotControl\n"
        "Reply with the number."
    )
    assert terrabot_service._teams_looks_like_grounding_refusal(good_reply) is False


def test_extract_candidate_rule_identifiers_finds_named_rule_blocks():
    identifiers = terrabot_service._teams_extract_candidate_rule_identifiers(WAF_CONTENT)
    names = {item["identifier"] for item in identifiers}
    assert "mcp-bot-control" in names
    assert "mcp-rate-limit" in names
    assert "aws_wafv2_web_acl.mcp" in names


def test_extract_candidate_rule_identifiers_finds_list_literal_entries():
    """Bug 2 fix: waf_blocked_rules is a plain list of strings, not a nested
    block or a Boolean flag — each entry must be its own selectable option,
    and one whose name overlaps the prompt ("mcp") must be prioritized."""
    identifiers = terrabot_service._teams_extract_candidate_rule_identifiers(
        LIST_LITERAL_CONTENT, prompt="disable mcp waf rules"
    )
    entries = [item["identifier"] for item in identifiers if item["kind"] == "list_entry"]
    assert "AWSManagedRulesMcpBotControl" in entries
    assert entries.index("AWSManagedRulesMcpBotControl") < entries.index("AWSManagedRulesCommonRuleSet")
    mcp_item = next(item for item in identifiers if item["identifier"] == "AWSManagedRulesMcpBotControl")
    assert mcp_item["list_variable"] == "waf_blocked_rules"
    assert "waf_blocked_rules" in mcp_item["description"]


def test_extract_selected_file_contents_finds_selected_context():
    payload = {
        "retrieved_value_context": [
            {
                "selection_state": "selected",
                "path": "terraform/dev_aws/global/waf.tf",
                "content": WAF_CONTENT,
            },
            {
                "selection_state": "candidate_selection_required",
                "path": "terraform/dev_aws/global/acm.tf",
                "content": "resource \"aws_acm_certificate\" \"main\" {}",
            },
        ]
    }
    found = terrabot_service._teams_extract_selected_file_contents(payload)
    assert len(found) == 1
    assert found[0][0] == "terraform/dev_aws/global/waf.tf"
    assert "mcp-bot-control" in found[0][1]


def test_maybe_rescue_grounding_refusal_produces_numbered_choosable_options():
    agent_input = json.dumps({
        "user_request": "disable mcp waf rules in dev_aws global",
        "retrieved_value_context": [
            {
                "selection_state": "selected",
                "path": "terraform/dev_aws/global/waf.tf",
                "content": WAF_CONTENT,
            }
        ],
    })

    rescued = terrabot_service._teams_maybe_rescue_grounding_refusal(agent_input, REFUSAL)
    assert rescued is not None
    reply_json, resolution_context = rescued
    payload = json.loads(reply_json)
    question = payload["questions"][0]
    assert re.search(r"\d+\.\s+`mcp-bot-control`", question)
    assert re.search(r"\d+\.\s+`mcp-rate-limit`", question)
    assert "Reply with the number" in question
    assert "waf.tf" in payload["analysis"]
    assert resolution_context is not None
    assert resolution_context["file"] == "terraform/dev_aws/global/waf.tf"
    assert len(resolution_context["options"]) >= 2


def test_maybe_rescue_grounding_refusal_handles_list_literal_entries_from_information_seeking_refusal():
    """End-to-end reproduction of the second reported failure: a
    waf_blocked_rules list recovered only via the unmarked-candidate
    fallback must produce a numbered picker of the actual entries."""
    agent_input = json.dumps({
        "user_request": "disable mcp waf rules in dev_aws global",
        "candidates": [
            {"path": "terraform/dev_aws/global/waf.tf", "content": LIST_LITERAL_CONTENT},
        ],
    })

    rescued = terrabot_service._teams_maybe_rescue_grounding_refusal(agent_input, INFORMATION_SEEKING_REFUSAL)
    assert rescued is not None
    reply_json, resolution_context = rescued
    payload = json.loads(reply_json)
    question = payload["questions"][0]
    assert "AWSManagedRulesMcpBotControl" in question
    assert "Reply with the number" in question
    assert resolution_context["options"][0]["identifier"] == "AWSManagedRulesMcpBotControl"


def test_maybe_rescue_grounding_refusal_falls_back_to_generic_question_without_file_content():
    """Even with no recoverable file content at all, the user must never be
    left with the bare refusal — a still-interactive generic question is
    the guaranteed worst case."""
    agent_input = json.dumps({"user_request": "disable mcp waf rules in dev_aws global"})
    rescued = terrabot_service._teams_maybe_rescue_grounding_refusal(agent_input, REFUSAL)
    assert rescued is not None
    reply_json, resolution_context = rescued
    payload = json.loads(reply_json)
    assert "?" not in REFUSAL  # sanity: original refusal is not itself a question
    assert payload["questions"]
    assert "disable mcp waf rules in dev_aws global" in payload["questions"][0]
    assert resolution_context is None


BOOLEAN_PARAMETER_CONTENT = """
variable "mcp_waf_bot_control_enabled" {
  default = true
}

mcp_waf_bot_control_enabled = true
mcp_rate_limit_enabled      = true
some_unrelated_flag         = false
"""


def test_extract_candidate_rule_identifiers_prioritizes_prompt_relevant_boolean_parameters():
    """"Rules" are usually Boolean parameters in this repository convention
    (per explicit product guidance), and the one whose name overlaps the
    user's wording (waf/mcp) must be prioritized over an unrelated flag."""
    identifiers = terrabot_service._teams_extract_candidate_rule_identifiers(
        BOOLEAN_PARAMETER_CONTENT, prompt="disable mcp waf rules"
    )
    names_in_order = [item["identifier"] for item in identifiers if item["kind"] == "parameter"]
    assert "mcp_waf_bot_control_enabled" in names_in_order
    assert names_in_order.index("mcp_waf_bot_control_enabled") < names_in_order.index("some_unrelated_flag")


def test_extract_candidate_rule_identifiers_boolean_parameters_include_current_value():
    identifiers = terrabot_service._teams_extract_candidate_rule_identifiers(
        BOOLEAN_PARAMETER_CONTENT, prompt="disable mcp waf rules"
    )
    mcp_item = next(item for item in identifiers if item["identifier"] == "mcp_waf_bot_control_enabled")
    assert mcp_item["current_value"] == "true"


def test_extract_any_file_contents_recovers_unmarked_candidate_files():
    """Regression: the picker's candidate list did not always mark an entry
    "selected"; the broader fallback extractor must still recover its
    content so a rescue is possible."""
    payload = {
        "candidates": [
            {"path": "terraform/dev_aws/global/waf.tf", "content": BOOLEAN_PARAMETER_CONTENT},
        ]
    }
    found = terrabot_service._teams_extract_any_file_contents(payload)
    assert found
    assert found[0][0] == "terraform/dev_aws/global/waf.tf"


def test_maybe_rescue_grounding_refusal_returns_none_for_non_refusal_reply():
    agent_input = json.dumps({
        "retrieved_value_context": [
            {"selection_state": "selected", "path": "waf.tf", "content": WAF_CONTENT}
        ]
    })
    assert terrabot_service._teams_maybe_rescue_grounding_refusal(
        agent_input, "Disabled the mcp-bot-control rule in waf.tf."
    ) is None


# --------------------------------------------------------------------------
# Resolving the user's reply to a rescued picker into a fully-specified
# instruction, so the next generation attempt targets an exact,
# already-confirmed identifier instead of ambiguous free text.
# --------------------------------------------------------------------------

PENDING_LIST_ENTRY_SELECTION = {
    "file": "terraform/dev_aws/global/waf.tf",
    "original_prompt": "disable mcp waf rules in dev_aws global",
    "options": [
        {
            "identifier": "AWSManagedRulesBotControlRuleSet",
            "kind": "list_entry",
            "list_variable": "waf_blocked_rules",
            "description": "entry in the `waf_blocked_rules` list",
        },
        {
            "identifier": "AWSManagedRulesMcpBotControl",
            "kind": "list_entry",
            "list_variable": "waf_blocked_rules",
            "description": "entry in the `waf_blocked_rules` list",
        },
    ],
}

PENDING_PARAMETER_SELECTION = {
    "file": "terraform/dev_aws/global/waf.tf",
    "original_prompt": "disable mcp waf rules in dev_aws global",
    "options": [
        {"identifier": "mcp_waf_bot_control_enabled", "kind": "parameter", "current_value": "true"},
        {"identifier": "mcp_rate_limit_enabled", "kind": "parameter", "current_value": "true"},
    ],
}


def test_resolve_pending_rescue_selection_by_number():
    instruction = terrabot_service._teams_resolve_pending_rescue_selection("2", PENDING_LIST_ENTRY_SELECTION)
    assert instruction is not None
    assert "AWSManagedRulesMcpBotControl" in instruction
    assert "waf_blocked_rules" in instruction
    assert "waf.tf" in instruction


def test_resolve_pending_rescue_selection_by_exact_name():
    instruction = terrabot_service._teams_resolve_pending_rescue_selection(
        "AWSManagedRulesMcpBotControl", PENDING_LIST_ENTRY_SELECTION
    )
    assert instruction is not None
    assert "AWSManagedRulesMcpBotControl" in instruction


def test_resolve_pending_rescue_selection_for_boolean_parameter_mentions_false():
    instruction = terrabot_service._teams_resolve_pending_rescue_selection("1", PENDING_PARAMETER_SELECTION)
    assert instruction is not None
    assert "mcp_waf_bot_control_enabled" in instruction
    assert "false" in instruction


def test_resolve_pending_rescue_selection_returns_none_for_unrelated_reply():
    instruction = terrabot_service._teams_resolve_pending_rescue_selection(
        "create a new s3 bucket instead", PENDING_LIST_ENTRY_SELECTION
    )
    assert instruction is None


def test_resolve_pending_rescue_selection_returns_none_for_out_of_range_number():
    instruction = terrabot_service._teams_resolve_pending_rescue_selection("99", PENDING_LIST_ENTRY_SELECTION)
    assert instruction is None


# --------------------------------------------------------------------------
# End-to-end: handle_teams_chat_request rewrites a numbered reply into a
# fully-specified instruction BEFORE any routing/state-machine logic sees
# it, using the durable pending_rescue_selection persisted by call_agent.
# --------------------------------------------------------------------------

def test_handle_teams_chat_request_rewrites_reply_using_pending_rescue_selection(monkeypatch):
    saved_patches = []

    monkeypatch.setattr(
        terrabot_service,
        "load_teams_conversation_state",
        lambda conversation_id: {"pending_rescue_selection": PENDING_LIST_ENTRY_SELECTION},
    )

    def fake_save_ui_state(conversation_id, patch):
        saved_patches.append(patch)
        return {}

    monkeypatch.setattr(terrabot_service, "_teams_save_ui_state", fake_save_ui_state)

    captured_request = {}

    def fake_previous_handle_chat(request_data):
        captured_request.update(request_data)
        return {"mode": "infra_preview", "cloud": "aws"}, 200

    monkeypatch.setattr(
        terrabot_service, "_TEAMS_PR_DUPLICATE_CHECK_PREVIOUS_HANDLE_CHAT", fake_previous_handle_chat
    )
    monkeypatch.setattr(
        terrabot_service, "_teams_attach_related_pull_requests", lambda result, prompt, cloud: result
    )

    result, status_code = terrabot_service.handle_teams_chat_request({
        "prompt": "2",
        "teams_conversation_id": "convo-rescue-1",
    })

    assert status_code == 200
    assert "AWSManagedRulesMcpBotControl" in captured_request["prompt"]
    assert captured_request["fresh_infra_generation"] is True
    # The pending selection must be cleared after being consumed.
    assert any(patch.get("pending_rescue_selection") is None for patch in saved_patches)


def test_handle_teams_chat_request_leaves_unrelated_reply_untouched_when_no_option_matches(monkeypatch):
    monkeypatch.setattr(
        terrabot_service,
        "load_teams_conversation_state",
        lambda conversation_id: {"pending_rescue_selection": PENDING_LIST_ENTRY_SELECTION},
    )
    monkeypatch.setattr(terrabot_service, "_teams_save_ui_state", lambda conversation_id, patch: {})

    captured_request = {}

    def fake_previous_handle_chat(request_data):
        captured_request.update(request_data)
        return {"mode": "chat"}, 200

    monkeypatch.setattr(
        terrabot_service, "_TEAMS_PR_DUPLICATE_CHECK_PREVIOUS_HANDLE_CHAT", fake_previous_handle_chat
    )

    original_prompt = "what environments does this repo support?"
    terrabot_service.handle_teams_chat_request({
        "prompt": original_prompt,
        "teams_conversation_id": "convo-rescue-2",
    })

    assert captured_request["prompt"] == original_prompt
    assert "fresh_infra_generation" not in captured_request
