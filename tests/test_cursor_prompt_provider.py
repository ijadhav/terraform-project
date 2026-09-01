from __future__ import annotations

import json
import os
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from shared_code import terraform_primary_context
from shared_code.automated_tests import cursor_prompt_provider


@dataclass(frozen=True)
class Case:
    case_id: str
    cloud: str
    owner: str
    repo: str
    branch: str
    commit_sha: str
    path: str
    environment: str
    flag: str
    alias: str
    current_value: bool
    desired_value: bool
    evidence_line: str
    phase1_prompt: str
    phase2_prompt: str


class FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self, create_payload: dict) -> None:
        self.create_payload = create_payload
        self.calls: list[dict] = []

    def request(self, method: str, url: str, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        if method == "POST" and url.endswith("/v1/agents"):
            return FakeResponse(200, self.create_payload)
        if method == "POST" and url.endswith("/archive"):
            return FakeResponse(200, {"id": "bc-test"})
        raise AssertionError(f"Unexpected request: {method} {url}")


def make_case() -> Case:
    return Case(
        case_id="aws-01-test",
        cloud="aws",
        owner="venasolutions",
        repo="tf-devops",
        branch="main",
        commit_sha="abc123",
        path="terraform/dev_aws/dev/main.tf",
        environment="dev",
        flag="enable_cloudamqp_datadog_metrics",
        alias="cloudamqp datadog metrics",
        current_value=False,
        desired_value=True,
        evidence_line="enable_cloudamqp_datadog_metrics = false",
        phase1_prompt="backend prompt one",
        phase2_prompt="backend prompt two",
    )


class CursorPromptProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        terraform_primary_context.clear_primary_context_cache()
        self.temp = tempfile.TemporaryDirectory()
        self.context_path = Path(self.temp.name) / "context.yaml"
        self.context_path.write_text(
            "schema_version: test\nauthority: live repository wins\n",
            encoding="utf-8",
        )
        self.base_env = {
            "TERRABOT_CURSOR_PROMPT_GENERATION_ENABLED": "true",
            "TERRABOT_CURSOR_API_KEY": "test-key",
            "TERRABOT_CURSOR_MAX_PARALLEL_REPOSITORIES": "1",
            "TERRABOT_CURSOR_HTTP_RETRIES": "0",
            "TERRABOT_TERRAFORM_PRIMARY_CONTEXT_ENABLED": "true",
            "TERRABOT_TERRAFORM_PRIMARY_CONTEXT_PATH": str(self.context_path),
        }

    def tearDown(self) -> None:
        self.temp.cleanup()
        terraform_primary_context.clear_primary_context_cache()

    def test_success_replaces_only_prompts_and_pins_exact_commit(self) -> None:
        case = make_case()
        result = {
            "schema_version": "terrabot.cursor.test-prompts.v1",
            "repository_commit_sha": case.commit_sha,
            "cases": [
                {
                    "case_id": case.case_id,
                    "phase1_prompt": "turn cloudamqp datadog metrics on for dev",
                    "phase2_prompt": "enable cloudamqp metric collection in dev",
                }
            ],
        }
        session = FakeSession(
            {
                "agent": {
                    "id": "bc-test",
                    "url": "https://cursor.com/agents/bc-test",
                },
                "run": {
                    "id": "run-test",
                    "status": "FINISHED",
                    "result": json.dumps(result),
                },
            }
        )
        events: list[tuple[str, dict]] = []

        def capture(event: str, **fields) -> None:
            events.append((event, fields))

        with patch.dict(os.environ, self.base_env, clear=False):
            generated = cursor_prompt_provider.apply_cursor_generated_prompts(
                [case],
                run_id="ctx-test",
                log_event=capture,
                session=session,
            )

        self.assertEqual(len(generated), 1)
        updated = generated[0]
        self.assertEqual(updated.path, case.path)
        self.assertEqual(updated.flag, case.flag)
        self.assertEqual(updated.commit_sha, case.commit_sha)
        self.assertNotEqual(updated.phase1_prompt, case.phase1_prompt)
        self.assertNotEqual(updated.phase2_prompt, case.phase2_prompt)

        create_call = session.calls[0]
        self.assertEqual(create_call["method"], "POST")
        request_body = create_call["json"]
        self.assertEqual(
            request_body["repos"][0]["startingRef"],
            case.commit_sha,
        )
        self.assertEqual(request_body["mode"], "plan")
        self.assertFalse(request_body["autoCreatePR"])
        self.assertFalse(request_body["workOnCurrentBranch"])
        self.assertIn("Do not edit files", request_body["prompt"]["text"])
        event_names = [event for event, _ in events]
        self.assertIn("cursor_prompt_generation_completed", event_names)
        self.assertIn("cursor_agent_archived", event_names)
        self.assertTrue(any(call["url"].endswith("/archive") for call in session.calls))

    def test_reported_internal_branch_metadata_does_not_force_fallback(self) -> None:
        case = make_case()
        result = {
            "schema_version": "terrabot.cursor.test-prompts.v1",
            "repository_commit_sha": case.commit_sha,
            "cases": [
                {
                    "case_id": case.case_id,
                    "phase1_prompt": "turn cloudamqp datadog metrics on for dev",
                    "phase2_prompt": "enable cloudamqp metric collection in dev",
                }
            ],
        }
        session = FakeSession(
            {
                "agent": {"id": "bc-test"},
                "run": {
                    "id": "run-test",
                    "status": "FINISHED",
                    "result": json.dumps(result),
                    "git": {
                        "branches": [
                            {
                                "repoUrl": "github.com/venasolutions/tf-devops",
                                "branch": "cursor/unexpected-write",
                            }
                        ]
                    },
                },
            }
        )
        snapshot = {"https://github.com/venasolutions/tf-devops": {"main": case.commit_sha}}
        with patch.dict(os.environ, self.base_env, clear=False), patch.object(
            cursor_prompt_provider.cursor_readonly_guard, "snapshot_remote_branches", side_effect=[snapshot, snapshot]
        ):
            generated = cursor_prompt_provider.apply_cursor_generated_prompts(
                [case], run_id="ctx-test", session=session
            )

        self.assertNotEqual(generated, [case])
        self.assertEqual(generated[0].phase1_prompt, "turn cloudamqp datadog metrics on for dev")

    def test_invalid_commit_uses_existing_backend_prompts(self) -> None:
        case = make_case()
        result = {
            "schema_version": "terrabot.cursor.test-prompts.v1",
            "repository_commit_sha": "wrong-commit",
            "cases": [
                {
                    "case_id": case.case_id,
                    "phase1_prompt": "new one",
                    "phase2_prompt": "new two",
                }
            ],
        }
        session = FakeSession(
            {
                "agent": {"id": "bc-test"},
                "run": {
                    "id": "run-test",
                    "status": "FINISHED",
                    "result": json.dumps(result),
                },
            }
        )
        with patch.dict(os.environ, self.base_env, clear=False):
            generated = cursor_prompt_provider.apply_cursor_generated_prompts(
                [case], run_id="ctx-test", session=session
            )

        self.assertEqual(generated, [case])

    def test_disabled_provider_makes_no_http_call(self) -> None:
        case = make_case()
        session = FakeSession({})
        with patch.dict(
            os.environ,
            {"TERRABOT_CURSOR_PROMPT_GENERATION_ENABLED": "false"},
            clear=False,
        ):
            generated = cursor_prompt_provider.apply_cursor_generated_prompts(
                [case], run_id="ctx-test", session=session
            )
        self.assertEqual(generated, [case])
        self.assertEqual(session.calls, [])

    def test_fail_closed_raises_after_invalid_response(self) -> None:
        case = make_case()
        session = FakeSession(
            {
                "agent": {"id": "bc-test"},
                "run": {
                    "id": "run-test",
                    "status": "FINISHED",
                    "result": "not json",
                },
            }
        )
        env = dict(self.base_env)
        env["TERRABOT_CURSOR_FAIL_OPEN"] = "false"
        with patch.dict(os.environ, env, clear=False):
            with self.assertRaises(cursor_prompt_provider.CursorPromptError):
                cursor_prompt_provider.apply_cursor_generated_prompts(
                    [case], run_id="ctx-test", session=session
                )


if __name__ == "__main__":
    unittest.main()
