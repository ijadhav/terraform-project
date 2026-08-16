"""Regression tests for duplicate/related pull-request awareness on infra
requests (including drafts), wired into terrabot_service.handle_teams_chat_request.
"""
import os
from unittest.mock import patch

import pytest

os.environ.setdefault("PROJECT_ENDPOINT_STRING", "https://example-fake-endpoint")
os.environ.setdefault("AZURE_AGENT_NAME", "fake-agent")

terrabot_service = pytest.importorskip(
    "shared_code.terrabot_service",
    reason="terrabot_service requires the full Azure/Bot Framework dependency set",
)

DRAFT_PR = {
    "number": 77,
    "title": "Disable MCP WAF rules in dev_aws global",
    "user": {"login": "carol"},
    "head": {"ref": "terrabot/waf-disable-global"},
    "base": {"ref": "main"},
    "state": "open",
    "draft": True,
    "html_url": "https://github.com/acme/tf-devops/pull/77",
    "updated_at": "2026-08-15T00:00:00Z",
    "body": "Disables the MCP WAF rule set in the global environment.",
}


def test_attach_related_pull_requests_finds_draft_pr(monkeypatch):
    monkeypatch.setattr(terrabot_service, "GITHUB_OWNER", "acme")
    monkeypatch.setattr(terrabot_service, "GITHUB_AWS_REPO", "tf-devops")
    with patch(
        "shared_code.pr_context.list_open_pull_requests",
        return_value=[DRAFT_PR],
    ):
        result = terrabot_service._teams_attach_related_pull_requests(
            {"mode": "infra_preview"},
            "disable mcp waf rules in dev_aws global",
            "aws",
        )

    assert "related_pull_requests" in result
    matches = result["related_pull_requests"]
    assert matches[0]["number"] == 77
    assert matches[0]["draft"] is True
    assert "PR #77" in result["related_pull_requests_context"]


def test_attach_related_pull_requests_noop_when_no_match(monkeypatch):
    monkeypatch.setattr(terrabot_service, "GITHUB_OWNER", "acme")
    monkeypatch.setattr(terrabot_service, "GITHUB_AWS_REPO", "tf-devops")
    with patch(
        "shared_code.pr_context.list_open_pull_requests",
        return_value=[DRAFT_PR],
    ):
        result = terrabot_service._teams_attach_related_pull_requests(
            {"mode": "infra_preview"},
            "create a completely unrelated lambda function for billing exports",
            "aws",
        )

    assert "related_pull_requests" not in result


def test_handle_teams_chat_request_resolves_cloud_from_nested_router_field(monkeypatch):
    """Regression: the infra_modification_target_selection clarification
    response sets cloud only under result["router"]["cloud"], not a
    top-level result["cloud"]. Without the router.cloud fallback, the
    duplicate-PR check silently never ran for that response shape."""
    monkeypatch.setattr(terrabot_service, "GITHUB_OWNER", "acme")
    monkeypatch.setattr(terrabot_service, "GITHUB_AWS_REPO", "tf-devops")
    fake_result = {
        "mode": "clarification",
        "decision_state": "infra_modification_target_selection",
        "router": {"request_type": "infra", "cloud": "aws", "workflow": "aws_infra_modification"},
        "ok": False,
    }

    with patch.object(
        terrabot_service,
        "_TEAMS_PR_DUPLICATE_CHECK_PREVIOUS_HANDLE_CHAT",
        return_value=(fake_result, 400),
    ), patch(
        "shared_code.pr_context.list_open_pull_requests",
        return_value=[DRAFT_PR],
    ):
        result, status_code = terrabot_service.handle_teams_chat_request(
            {"prompt": "disable mcp waf rules in dev_aws global"}
        )

    assert status_code == 400
    assert result["related_pull_requests"][0]["number"] == 77


def test_handle_teams_chat_request_attaches_related_prs_for_infra_preview(monkeypatch):
    monkeypatch.setattr(terrabot_service, "GITHUB_OWNER", "acme")
    monkeypatch.setattr(terrabot_service, "GITHUB_AWS_REPO", "tf-devops")
    fake_result = {"mode": "infra_preview", "cloud": "aws", "ok": True}

    with patch.object(
        terrabot_service,
        "_TEAMS_PR_DUPLICATE_CHECK_PREVIOUS_HANDLE_CHAT",
        return_value=(fake_result, 200),
    ), patch(
        "shared_code.pr_context.list_open_pull_requests",
        return_value=[DRAFT_PR],
    ):
        result, status_code = terrabot_service.handle_teams_chat_request(
            {"prompt": "disable mcp waf rules in dev_aws global"}
        )

    assert status_code == 200
    assert result["related_pull_requests"][0]["number"] == 77
