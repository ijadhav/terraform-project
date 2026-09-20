"""Regression tests for cloud resolution and the branch yes/no continuation.

Two user-visible failures are covered here:

1. Terrabot asked "Please specify which cloud to use: AWS or Azure." for a
   prompt that names the cloud explicitly. An environment name matched inside a
   longer hyphenated identifier (``npr-infra-devops`` contains the AWS ``devops``
   environment), which produced a provider/environment conflict, and the
   conflict reason was then replaced by the generic cloud question.
2. The branch yes/no reply carried no cloud and no request text, so answering it
   produced another clarification and the branch question was asked again.
"""
import os

import pytest

os.environ.setdefault("PROJECT_ENDPOINT_STRING", "https://example-fake-endpoint")
os.environ.setdefault("AZURE_AGENT_NAME", "fake-agent")

terrabot_service = pytest.importorskip(
    "shared_code.terrabot_service",
    reason="terrabot_service requires the full Azure/Bot Framework dependency set",
)

AZURE_STORAGE_PROMPT = (
    "I want to create a storage account in npr-infra-devops subscription in npr azure"
)


def test_environment_name_does_not_match_inside_a_longer_identifier():
    text = terrabot_service._terrabot_env_text(AZURE_STORAGE_PROMPT)
    assert not terrabot_service._terrabot_prompt_has_name(text, "devops")
    assert not terrabot_service._terrabot_prompt_has_name(text, "dev")


def test_standalone_environment_names_still_match():
    text = terrabot_service._terrabot_env_text("deploy to npr-stg and to devops")
    assert terrabot_service._terrabot_prompt_has_name(text, "npr-stg")
    assert terrabot_service._terrabot_prompt_has_name(text, "devops")


def test_explicit_azure_prompt_resolves_to_azure_without_conflict():
    resolution = terrabot_service.resolve_teams_environment_targets(AZURE_STORAGE_PROMPT)
    assert resolution["error"] == ""
    assert resolution["cloud"] == "azure"
    assert resolution["repo_target"] == "tf-azure-hub"


def test_router_does_not_ask_for_a_cloud_the_prompt_already_names():
    decision = terrabot_service.normalize_router_decision(
        prompt=AZURE_STORAGE_PROMPT,
        requested_mode="infra",
        requested_cloud=None,
        recovered_state={},
    )
    assert decision.workflow != "clarification_required"
    assert decision.cloud == "azure"
    assert "specify which cloud" not in terrabot_service.build_router_response_message(decision).lower()


def test_genuine_conflict_explains_itself_instead_of_asking_for_a_cloud():
    decision = terrabot_service.normalize_router_decision(
        prompt="create an ec2 instance in the dev environment in azure",
        requested_mode="infra",
        requested_cloud=None,
        recovered_state={},
    )
    assert decision.workflow == "clarification_required"
    message = terrabot_service.build_router_response_message(decision)
    assert "AZURE" in message and "AWS" in message
    assert message != "Please specify which cloud to use: AWS or Azure."


def test_branch_reply_restores_the_prompt_and_pins_the_resolved_cloud():
    state = {
        "stage": "awaiting_branch_reuse_decision",
        "pending_follow_up_prompt": AZURE_STORAGE_PROMPT,
        "pending_follow_up_cloud": "azure",
        "pending_follow_up_branch": "terrabot-test-azure_consumer-86de10395d32",
    }
    request, handled = terrabot_service._teams_flow_guard_prepare_branch_reply(
        {"prompt": "no", "mode": "infra", "pending_branch_choice_reply": True, "branch_choice": "new"},
        state,
        "",
        "no",
    )
    assert handled is True
    assert request["prompt"] == AZURE_STORAGE_PROMPT
    assert request["cloud"] == "azure"
    assert request["requested_cloud"] == "azure"
    assert request["force_new_branch"] is True
    assert request["state_patch"]["resolved_branch_choice_prompt"] == AZURE_STORAGE_PROMPT


def test_branch_reply_is_not_forwarded_as_a_bare_yes_no_request():
    state = {
        "stage": "awaiting_branch_reuse_decision",
        "pending_follow_up_prompt": "",
        "last_infra_prompt": "no",
    }
    request, handled = terrabot_service._teams_flow_guard_prepare_branch_reply(
        {"prompt": "no", "mode": "infra", "pending_branch_choice_reply": True, "branch_choice": "new"},
        state,
        "",
        "no",
    )
    assert handled is False
    assert request["prompt"] == "no"
