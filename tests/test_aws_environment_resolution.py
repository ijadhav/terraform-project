"""Regression tests for AWS environment-folder resolution.

Bug: a prompt naming the "global" environment (e.g. "disable mcp waf rules
in dev_aws global") was silently falling through to the terraform/dev_aws/
minidev default because detect_explicit_aws_environment only recognized
"global" when paired with "root" (terraform/root/global). Standalone
"global" was never matched, so resolve_aws_environment_path's fallback
picked minidev instead, and the agent then analyzed the wrong folder's
files entirely.
"""
import os

import pytest

os.environ.setdefault("PROJECT_ENDPOINT_STRING", "https://example-fake-endpoint")
os.environ.setdefault("AZURE_AGENT_NAME", "fake-agent")

terrabot_service = pytest.importorskip(
    "shared_code.terrabot_service",
    reason="terrabot_service requires the full Azure/Bot Framework dependency set",
)


def test_dev_global_environment_resolves_to_dev_aws_global():
    path, error = terrabot_service.detect_explicit_aws_environment(
        "disable mcp waf rules in dev_aws global"
    )
    assert error is None
    assert path == "terraform/dev_aws/global"


def test_prod_global_environment_resolves_to_prod_aws_global():
    path, error = terrabot_service.detect_explicit_aws_environment(
        "disable waf rules in prod global"
    )
    assert error is None
    assert path == "terraform/prod_aws/global"


def test_root_global_still_resolves_to_root_global():
    path, error = terrabot_service.detect_explicit_aws_environment(
        "update the root global terraform config"
    )
    assert error is None
    assert path == "terraform/root/global"


def test_minidev_environment_still_resolves_correctly():
    path, error = terrabot_service.detect_explicit_aws_environment(
        "create an ec2 instance in minidev"
    )
    assert error is None
    assert path == "terraform/dev_aws/minidev"


def test_resolve_aws_environment_path_uses_explicit_global_not_minidev_default():
    path, error = terrabot_service.resolve_aws_environment_path(
        "disable mcp waf rules in dev_aws global"
    )
    assert error is None
    assert path == "terraform/dev_aws/global"
    assert path != "terraform/dev_aws/minidev"
