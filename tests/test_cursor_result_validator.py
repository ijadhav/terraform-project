from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from shared_code.automated_tests import terrabot_cursor_result_validator as validator


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._payload


class FakeHttpClient:
    def __init__(self, terminal_payload: dict):
        self.terminal_payload = terminal_payload
        self.post_calls: list[dict] = []
        self.get_calls: list[dict] = []

    def post(self, url: str, **kwargs):
        self.post_calls.append({"url": url, **kwargs})
        return FakeResponse({
            "agent": {
                "id": "bc-test-agent",
                "latestRunId": "run-cursor-1",
                "url": "https://cursor.com/agents/bc-test-agent",
            },
            "run": {"id": "run-cursor-1", "status": "CREATING"},
        })

    def get(self, url: str, **kwargs):
        self.get_calls.append({"url": url, **kwargs})
        return FakeResponse(self.terminal_payload)


class SequenceHttpClient:
    def __init__(self, terminal_payloads: list[dict]):
        self.terminal_payloads = list(terminal_payloads)
        self.post_calls: list[dict] = []
        self.get_calls: list[dict] = []
        self._created = 0
        self._active = -1

    def post(self, url: str, **kwargs):
        self.post_calls.append({"url": url, **kwargs})
        self._active = self._created
        self._created += 1
        suffix = self._created
        return FakeResponse({
            "agent": {
                "id": f"bc-test-agent-{suffix}",
                "latestRunId": f"run-cursor-{suffix}",
                "url": f"https://cursor.com/agents/bc-test-agent-{suffix}",
            },
            "run": {"id": f"run-cursor-{suffix}", "status": "CREATING"},
        })

    def get(self, url: str, **kwargs):
        self.get_calls.append({"url": url, **kwargs})
        return FakeResponse(self.terminal_payloads[self._active])


def boolean_case_payload() -> dict:
    return {
        "case_id": "aws-001",
        "case_type": "boolean_context",
        "owner": "venasolutions",
        "repo": "tf-devops",
        "commit_sha": "abc123",
        "phase1_prompt": "Disable patch setup on us1.",
        "phase2_prompt": "Turn patch setup off in us1.",
        "expected": {
            "path": "terraform/prod_aws/us1/main.tf",
            "flag": "enable_patch_setup",
            "desired_value": False,
        },
        "backend_assertions": {
            "precommit_validation_ok": True,
            "context_stored": True,
            "phase2_context_retrieved": True,
        },
        "evidence": {},
    }


def finished_payload(*, branches=None, cases=None, schema_version="terrabot.cursor.validation.v1") -> dict:
    result = {
        "schema_version": schema_version,
        "run_id": "ctx-test",
        "cases": cases if cases is not None else [{
            "case_id": "aws-001",
            "output_correct": True,
            "context_added": True,
            "context_retrievable": True,
            "context_reused": True,
            "overall_ok": True,
            "reason": "Generated output and repository context evidence match the live target.",
            "evidence": ["Expected file and flag are present."],
        }],
    }
    return {
        "id": "run-cursor-1",
        "agentId": "bc-test-agent",
        "status": "FINISHED",
        "durationMs": 3210,
        "result": json.dumps(result),
        "git": {"branches": branches or []},
    }


class CursorResultValidatorTests(unittest.TestCase):
    def test_disabled_returns_without_calling_cursor(self):
        client = FakeHttpClient(finished_payload())
        with patch.dict(os.environ, {"TERRABOT_TEST_CURSOR_RESULT_VALIDATION_ENABLED": "false"}, clear=False):
            result = validator.validate_test_run_with_cursor(
                run_id="ctx-test",
                cases=[boolean_case_payload()],
                http_client=client,
            )
        self.assertFalse(result["enabled"])
        self.assertFalse(result["completed"])
        self.assertEqual(client.post_calls, [])
        self.assertEqual(client.get_calls, [])

    def test_success_uses_read_only_pinned_cloud_agent_contract(self):
        client = FakeHttpClient(finished_payload())
        env = {
            "TERRABOT_TEST_CURSOR_RESULT_VALIDATION_ENABLED": "true",
            "TERRABOT_CURSOR_API_KEY": "test-key",
            "TERRABOT_CURSOR_API_BASE_URL": "https://cursor.example",
            "TERRABOT_TEST_CURSOR_VALIDATION_MODEL": "model-id",
            "TERRABOT_TEST_CURSOR_VALIDATION_POLL_SECONDS": "not-a-number",
        }
        with patch.dict(os.environ, env, clear=False):
            result = validator.validate_test_run_with_cursor(
                run_id="ctx-test",
                cases=[boolean_case_payload()],
                http_client=client,
            )

        self.assertTrue(result["enabled"])
        self.assertTrue(result["completed"])
        self.assertEqual(result["case_results"]["aws-001"]["overall_ok"], True)
        self.assertEqual(len(client.post_calls), 1)
        create = client.post_calls[0]
        self.assertEqual(create["url"], "https://cursor.example/v1/agents")
        self.assertEqual(create["json"]["mode"], "plan")
        self.assertFalse(create["json"]["workOnCurrentBranch"])
        self.assertFalse(create["json"]["autoCreatePR"])
        self.assertEqual(create["json"]["model"], {"id": "model-id"})
        self.assertEqual(create["json"]["repos"], [{
            "url": "https://github.com/venasolutions/tf-devops",
            "startingRef": "abc123",
        }])
        self.assertIn("Do not edit files", create["json"]["prompt"]["text"])
        self.assertIn("context_retrievable", create["json"]["prompt"]["text"])
        self.assertEqual(
            client.get_calls[0]["url"],
            "https://cursor.example/v1/agents/bc-test-agent/runs/run-cursor-1",
        )

    def test_allows_cursor_branch_metadata_when_remote_is_unchanged(self):
        client = FakeHttpClient(finished_payload(branches=[{
            "repoUrl": "github.com/venasolutions/tf-devops",
            "branch": "cursor/internal-plan-branch",
        }]))
        env = {
            "TERRABOT_TEST_CURSOR_RESULT_VALIDATION_ENABLED": "true",
            "TERRABOT_CURSOR_API_KEY": "test-key",
        }
        snapshot = {"https://github.com/venasolutions/tf-devops": {"main": "abc123"}}
        with patch.dict(os.environ, env, clear=False), patch.object(
            validator.cursor_readonly_guard, "snapshot_remote_branches", side_effect=[snapshot, snapshot]
        ):
            result = validator.validate_test_run_with_cursor(
                run_id="ctx-test",
                cases=[boolean_case_payload()],
                http_client=client,
            )
        self.assertTrue(result["completed"])

    def test_rejects_verified_remote_cursor_branch_mutation(self):
        client = FakeHttpClient(finished_payload(branches=[{
            "repoUrl": "github.com/venasolutions/tf-devops",
            "branch": "cursor/unexpected-write",
        }]))
        env = {
            "TERRABOT_TEST_CURSOR_RESULT_VALIDATION_ENABLED": "true",
            "TERRABOT_CURSOR_API_KEY": "test-key",
        }
        before = {"https://github.com/venasolutions/tf-devops": {"main": "abc123"}}
        after = {"https://github.com/venasolutions/tf-devops": {"main": "abc123", "cursor/unexpected-write": "def456"}}
        with patch.dict(os.environ, env, clear=False), patch.object(
            validator.cursor_readonly_guard, "snapshot_remote_branches", side_effect=[before, after]
        ):
            result = validator.validate_test_run_with_cursor(
                run_id="ctx-test",
                cases=[boolean_case_payload()],
                http_client=client,
            )
        self.assertFalse(result["completed"])
        self.assertIn("remote github branch", result["error"].lower())
        self.assertEqual(result["case_results"], {})

    def test_rejects_incomplete_or_wrong_schema_verdict(self):
        client = FakeHttpClient(finished_payload(schema_version="wrong.schema", cases=[]))
        env = {
            "TERRABOT_TEST_CURSOR_RESULT_VALIDATION_ENABLED": "true",
            "TERRABOT_CURSOR_API_KEY": "test-key",
        }
        with patch.dict(os.environ, env, clear=False):
            result = validator.validate_test_run_with_cursor(
                run_id="ctx-test",
                cases=[boolean_case_payload()],
                http_client=client,
            )
        self.assertFalse(result["completed"])
        self.assertIn("schema_version", result["error"])


    def test_protocol_repair_recovers_wrong_schema_without_weakening_parser(self):
        wrong = finished_payload(schema_version="wrong.schema")
        repaired = finished_payload()
        repaired["id"] = "run-cursor-2"
        repaired["agentId"] = "bc-test-agent-2"
        client = SequenceHttpClient([wrong, repaired])
        env = {
            "TERRABOT_TEST_CURSOR_RESULT_VALIDATION_ENABLED": "true",
            "TERRABOT_CURSOR_API_KEY": "test-key",
            "TERRABOT_TEST_CURSOR_VALIDATION_PROTOCOL_REPAIR_ENABLED": "true",
            "TERRABOT_TEST_CURSOR_VALIDATION_POLL_SECONDS": "1",
        }
        snapshot = {"https://github.com/venasolutions/tf-devops": {"main": "abc123"}}
        with patch.dict(os.environ, env, clear=False), patch.object(
            validator.cursor_readonly_guard,
            "snapshot_remote_branches",
            side_effect=[snapshot, snapshot, snapshot, snapshot],
        ):
            result = validator.validate_test_run_with_cursor(
                run_id="ctx-test",
                cases=[boolean_case_payload()],
                http_client=client,
            )
        self.assertTrue(result["completed"])
        self.assertTrue(result["case_results"]["aws-001"]["overall_ok"])
        self.assertEqual(len(client.post_calls), 2)
        repair_prompt = client.post_calls[1]["json"]["prompt"]["text"]
        self.assertIn('schema_version MUST be the exact literal "terrabot.cursor.validation.v1"', repair_prompt)
        self.assertIn("Do not change the semantic verdicts", repair_prompt)

    def test_resource_creation_requires_null_context_fields(self):
        case = boolean_case_payload()
        case["case_type"] = "resource_creation"
        verdict = finished_payload(cases=[{
            "case_id": "aws-001",
            "output_correct": True,
            "context_added": None,
            "context_retrievable": None,
            "context_reused": None,
            "overall_ok": True,
            "reason": "Generated resource output matches repository patterns.",
            "evidence": ["Expected resource files were present."],
        }])
        client = FakeHttpClient(verdict)
        env = {
            "TERRABOT_TEST_CURSOR_RESULT_VALIDATION_ENABLED": "true",
            "TERRABOT_CURSOR_API_KEY": "test-key",
        }
        with patch.dict(os.environ, env, clear=False):
            result = validator.validate_test_run_with_cursor(
                run_id="ctx-test",
                cases=[case],
                http_client=client,
            )
        self.assertTrue(result["completed"])
        self.assertIsNone(result["case_results"]["aws-001"]["context_added"])

    def test_rejects_overall_true_when_an_applicable_assertion_failed(self):
        client = FakeHttpClient(finished_payload(cases=[{
            "case_id": "aws-001",
            "output_correct": True,
            "context_added": True,
            "context_retrievable": False,
            "context_reused": True,
            "overall_ok": True,
            "reason": "Inconsistent result.",
            "evidence": [],
        }]))
        env = {
            "TERRABOT_TEST_CURSOR_RESULT_VALIDATION_ENABLED": "true",
            "TERRABOT_CURSOR_API_KEY": "test-key",
        }
        with patch.dict(os.environ, env, clear=False):
            result = validator.validate_test_run_with_cursor(
                run_id="ctx-test",
                cases=[boolean_case_payload()],
                http_client=client,
            )
        self.assertFalse(result["completed"])
        self.assertIn("overall_ok=true", result["error"])

    def test_rejects_null_context_fields_for_boolean_case(self):
        client = FakeHttpClient(finished_payload(cases=[{
            "case_id": "aws-001",
            "output_correct": True,
            "context_added": None,
            "context_retrievable": None,
            "context_reused": None,
            "overall_ok": False,
            "reason": "Missing context verdicts.",
            "evidence": [],
        }]))
        env = {
            "TERRABOT_TEST_CURSOR_RESULT_VALIDATION_ENABLED": "true",
            "TERRABOT_CURSOR_API_KEY": "test-key",
        }
        with patch.dict(os.environ, env, clear=False):
            result = validator.validate_test_run_with_cursor(
                run_id="ctx-test",
                cases=[boolean_case_payload()],
                http_client=client,
            )
        self.assertFalse(result["completed"])
        self.assertIn("Boolean context fields", result["error"])

    def test_rejects_duplicate_case_ids_before_calling_cursor(self):
        client = FakeHttpClient(finished_payload())
        env = {
            "TERRABOT_TEST_CURSOR_RESULT_VALIDATION_ENABLED": "true",
            "TERRABOT_CURSOR_API_KEY": "test-key",
        }
        with patch.dict(os.environ, env, clear=False):
            result = validator.validate_test_run_with_cursor(
                run_id="ctx-test",
                cases=[boolean_case_payload(), boolean_case_payload()],
                http_client=client,
            )
        self.assertFalse(result["completed"])
        self.assertIn("unique non-empty", result["error"])
        self.assertEqual(client.post_calls, [])

    def test_large_file_evidence_is_compacted_instead_of_skipping_validation(self):
        case = boolean_case_payload()
        case["evidence"] = {
            "phase1": {"generated_files": [{"path": case["expected"]["path"], "excerpt": "x" * 30000}]},
            "phase2": {"generated_files": [{"path": case["expected"]["path"], "excerpt": "y" * 30000}]},
        }
        client = FakeHttpClient(finished_payload())
        env = {
            "TERRABOT_TEST_CURSOR_RESULT_VALIDATION_ENABLED": "true",
            "TERRABOT_CURSOR_API_KEY": "test-key",
            "TERRABOT_TEST_CURSOR_VALIDATION_MAX_PROMPT_CHARS": "20000",
        }
        with patch.dict(os.environ, env, clear=False):
            result = validator.validate_test_run_with_cursor(
                run_id="ctx-test",
                cases=[case],
                http_client=client,
            )
        self.assertTrue(result["completed"])
        prompt = client.post_calls[0]["json"]["prompt"]["text"]
        self.assertLess(len(prompt), 30000)
        self.assertIn("content", prompt.lower())


if __name__ == "__main__":
    unittest.main()
