"""Regression tests: the AWS/Azure infrastructure-target picker must rank a
file whose content actually matches the requested resource above generic
alphabetically-earlier environment files, and must describe file contents.

Bug: a prompt like "disable mcp waf rules in dev_aws global" resolved the
correct environment folder but the resulting picker showed only the first
six files in alphabetical order (acm.tf, acm_pca.tf, awsconfig.tf,
backend.tf, calc_snapshot.tf, cdn.tf) and never surfaced waf.tf, which was
the actual file to edit.
"""
import os

import pytest

os.environ.setdefault("PROJECT_ENDPOINT_STRING", "https://example-fake-endpoint")
os.environ.setdefault("AZURE_AGENT_NAME", "fake-agent")

terrabot_service = pytest.importorskip(
    "shared_code.terrabot_service",
    reason="terrabot_service requires the full Azure/Bot Framework dependency set",
)

PROMPT = "disable mcp waf rules in dev_aws global"

CANDIDATE_FILES = [
    {
        "path": "terraform/dev_aws/global/acm.tf",
        "content": 'resource "aws_acm_certificate" "main" {\n  domain_name = "example.com"\n}\n',
    },
    {
        "path": "terraform/dev_aws/global/acm_pca.tf",
        "content": 'resource "aws_acmpca_certificate_authority" "root" {}\n',
    },
    {
        "path": "terraform/dev_aws/global/awsconfig.tf",
        "content": 'resource "aws_config_configuration_recorder" "main" {}\n',
    },
    {
        "path": "terraform/dev_aws/global/backend.tf",
        "content": 'terraform {\n  backend "s3" {}\n}\n',
    },
    {
        "path": "terraform/dev_aws/global/waf.tf",
        "content": (
            'resource "aws_wafv2_web_acl" "mcp" {\n'
            '  name = "mcp-waf"\n'
            "}\n\n"
            'resource "aws_wafv2_web_acl_association" "mcp_api" {\n'
            "  resource_arn = aws_lb.mcp.arn\n"
            "  web_acl_arn  = aws_wafv2_web_acl.mcp.arn\n"
            "}\n"
        ),
    },
    {
        "path": "terraform/dev_aws/global/cdn.tf",
        "content": 'resource "aws_cloudfront_distribution" "main" {}\n',
    },
]


def _rank(files, prompt=PROMPT):
    return sorted(
        files,
        key=lambda item: (
            -terrabot_service._teams_semantic_candidate_score(prompt, item)[0],
            str(item.get("path") or ""),
        ),
    )


def test_waf_file_outranks_alphabetically_earlier_generic_files():
    ranked = _rank(CANDIDATE_FILES)
    assert ranked[0]["path"] == "terraform/dev_aws/global/waf.tf"


def test_waf_file_scores_above_zero_and_generic_files_do_not():
    scores = {
        item["path"]: terrabot_service._teams_semantic_candidate_score(PROMPT, item)[0]
        for item in CANDIDATE_FILES
    }
    assert scores["terraform/dev_aws/global/waf.tf"] > 0
    for path, score in scores.items():
        if path != "terraform/dev_aws/global/waf.tf":
            assert score < scores["terraform/dev_aws/global/waf.tf"]


def test_content_summary_describes_declared_resources():
    waf_item = next(item for item in CANDIDATE_FILES if item["path"].endswith("waf.tf"))
    summary = terrabot_service._teams_describe_tf_file_contents(waf_item)
    assert "aws_wafv2_web_acl" in summary
    assert "aws_wafv2_web_acl_association" in summary


def test_content_summary_empty_when_no_content_or_blocks():
    assert terrabot_service._teams_describe_tf_file_contents({"path": "x.tf"}) == ""


def test_content_summary_falls_back_to_matched_blocks_without_content():
    item = {"path": "x.tf", "matched_blocks": [{"header": "aws_wafv2_web_acl.mcp"}]}
    summary = terrabot_service._teams_describe_tf_file_contents(item)
    assert "aws_wafv2_web_acl.mcp" in summary
