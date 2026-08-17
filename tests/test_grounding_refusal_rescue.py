"""Regression tests for rescuing a bare "cannot safely ground exact rule
names" refusal into an evidence-backed clarification that names the actual
rule/resource identifiers found in the selected file's live content.

Bug: after correctly resolving the environment and selecting waf.tf, the
agent still replied with a dead-end refusal ("Cannot safely disable MCP waf
rules yet because the exact MCP rule names are not grounded in the
repository evidence") instead of asking the user to pick among the named
`rule { name = "..." }` blocks actually declared in that file, even though
the file's content was already supplied to the agent.
"""
import json
import os

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


def test_looks_like_grounding_refusal_matches_real_refusal_text():
    assert terrabot_service._teams_looks_like_grounding_refusal(REFUSAL) is True


def test_looks_like_grounding_refusal_false_for_real_questions():
    assert terrabot_service._teams_looks_like_grounding_refusal(
        "Which WAF rule should be disabled: mcp-bot-control or mcp-rate-limit?"
    ) is False


def test_looks_like_grounding_refusal_false_for_normal_text():
    assert terrabot_service._teams_looks_like_grounding_refusal(
        "Added the storage account to envs/dev/main.tf."
    ) is False


def test_extract_candidate_rule_identifiers_finds_named_rule_blocks():
    identifiers = terrabot_service._teams_extract_candidate_rule_identifiers(WAF_CONTENT)
    names = {item["identifier"] for item in identifiers}
    assert "mcp-bot-control" in names
    assert "mcp-rate-limit" in names
    assert "aws_wafv2_web_acl.mcp" in names


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


def test_maybe_rescue_grounding_refusal_produces_named_choices():
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
    payload = json.loads(rescued)
    assert "mcp-bot-control" in payload["questions"][0]
    assert "mcp-rate-limit" in payload["questions"][0]
    assert "waf.tf" in payload["analysis"]


def test_maybe_rescue_grounding_refusal_falls_back_to_generic_question_without_file_content():
    """Even with no recoverable file content at all, the user must never be
    left with the bare refusal — a still-interactive generic question is
    the guaranteed worst case."""
    agent_input = json.dumps({"user_request": "disable mcp waf rules in dev_aws global"})
    rescued = terrabot_service._teams_maybe_rescue_grounding_refusal(agent_input, REFUSAL)
    assert rescued is not None
    payload = json.loads(rescued)
    assert "?" not in REFUSAL  # sanity: original refusal is not itself a question
    assert payload["questions"]
    assert "disable mcp waf rules in dev_aws global" in payload["questions"][0]


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
