from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

# The report/scoring unit tests do not use Azure Table Storage. Stub only the
# import surface required by terrabot_test_state so the test remains runnable
# in the repository's minimal local environment.
if "azure.data.tables" not in sys.modules:
    azure_module = sys.modules.setdefault("azure", types.ModuleType("azure"))
    data_module = sys.modules.setdefault("azure.data", types.ModuleType("azure.data"))
    tables_module = types.ModuleType("azure.data.tables")
    tables_module.TableServiceClient = object
    tables_module.UpdateMode = types.SimpleNamespace(REPLACE="replace")
    sys.modules["azure.data.tables"] = tables_module
    setattr(azure_module, "data", data_module)
    setattr(data_module, "tables", tables_module)

from shared_code.automated_tests import terrabot_test_runner as runner
from shared_code.automated_tests import terrabot_test_worker as worker


def boolean_result() -> runner.TestCaseResult:
    case = runner.TestCase(
        case_id="aws-001",
        case_type="boolean_context",
        cloud="aws",
        owner="venasolutions",
        repo="tf-devops",
        branch="main",
        commit_sha="abc123",
        path="terraform/prod_aws/us1/main.tf",
        environment="us1",
        flag="enable_patch_setup",
        alias="patch setup",
        current_value=True,
        desired_value=False,
        evidence_line="enable_patch_setup = true",
        phase1_prompt="Disable patch setup on us1.",
        phase2_prompt="Turn patch setup off in us1.",
    )
    result = runner.TestCaseResult(case=case)
    result.expected_target_found = True
    result.correct_flag_detected = True
    result.phase1_file_generated = True
    result.validation_ok = True
    result.branch_pushed = True
    result.context_stored = True
    result.phase2_context_retrieved = True
    result.phase2_context_attached = True
    result.phase2_file_generated = True
    result.phase2_target_ok = True
    result.phase2_reused_without_clarification = True
    result.phase2_context_useful = True
    result.score = runner._calculate_case_score(result, include_cursor=False)
    result.backend_score = result.score
    result.failure_classification = "PASS"
    return result


def cursor_validation(*, retrievable=True) -> dict:
    return {
        "enabled": True,
        "completed": True,
        "agent_url": "https://cursor.com/agents/bc-test-agent",
        "duration_ms": 1200,
        "error": "",
        "case_results": {
            "aws-001": {
                "case_id": "aws-001",
                "output_correct": True,
                "context_added": True,
                "context_retrievable": retrievable,
                "context_reused": True,
                "overall_ok": retrievable,
                "reason": "Independent Cursor verification completed.",
                "evidence": [],
            }
        },
    }


class CursorValidationReportingTests(unittest.TestCase):
    def test_successful_cursor_verdict_is_part_of_full_pass_and_teams_table(self):
        result = boolean_result()
        runner._apply_cursor_validation_result("ctx-test", [result], cursor_validation())

        self.assertEqual(result.backend_score, 100)
        self.assertEqual(result.score, 100)
        self.assertTrue(result.cursor_validation_completed)
        self.assertTrue(result.cursor_output_correct)
        self.assertTrue(result.cursor_context_added)
        self.assertTrue(result.cursor_context_retrievable)
        self.assertTrue(result.cursor_context_reused)
        self.assertEqual(result.failure_classification, "PASS")

        report = runner.format_test_run_report(runner.TestRunResult(
            run_id="ctx-test",
            requested_cases=1,
            cases=[result],
            duration_ms=5000,
        ))
        self.assertIn("Cursor independent review", report)
        self.assertIn("Cursor output", report)
        self.assertIn("ADD:PASS GET:PASS USE:PASS", report)
        self.assertIn("Cursor overall", report)
        self.assertIn("| PASS | PASS | PASS |", report)

    def test_cursor_context_retrieval_rejection_changes_final_result(self):
        result = boolean_result()
        runner._apply_cursor_validation_result(
            "ctx-test", [result], cursor_validation(retrievable=False)
        )

        self.assertEqual(result.backend_score, 100)
        self.assertLess(result.score, 100)
        self.assertEqual(
            result.failure_classification,
            "CURSOR_CONTEXT_RETRIEVAL_VALIDATION_FAILURE",
        )
        report = runner.format_test_run_report(runner.TestRunResult(
            run_id="ctx-test",
            requested_cases=1,
            cases=[result],
        ))
        self.assertIn("ADD:PASS GET:FAIL USE:PASS", report)
        self.assertIn("Cursor did not verify context retrieval", report)

    def test_cursor_unavailable_is_visible_and_does_not_discard_backend_result(self):
        result = boolean_result()
        runner._apply_cursor_validation_result("ctx-test", [result], {
            "enabled": True,
            "completed": False,
            "duration_ms": 300,
            "error": "Cursor API unavailable",
            "case_results": {},
        })

        self.assertEqual(result.backend_score, 100)
        self.assertLess(result.score, 100)
        self.assertEqual(result.failure_classification, "CURSOR_VALIDATION_UNAVAILABLE")
        self.assertEqual(result.cursor_validation_error, "Cursor API unavailable")
        report = runner.format_test_run_report(runner.TestRunResult(
            run_id="ctx-test",
            requested_cases=1,
            cases=[result],
        ))
        self.assertIn("| ERROR | ERROR | ERROR |", report)
        self.assertIn("Cursor validation unavailable", report)

    def test_queue_worker_posts_the_final_cursor_report_to_originating_teams_chat(self):
        sent: list[tuple[dict, str]] = []
        teams_module = types.ModuleType("shared_code.teams_bot")

        async def send_automated_test_report(reference: dict, report: str) -> None:
            sent.append((reference, report))

        teams_module.send_automated_test_report = send_automated_test_report
        payload = {
            "run_id": "ctx-test",
            "conversation_reference": {"conversation": {"id": "teams-conversation"}},
        }
        with patch.object(runner, "execute_automated_test_job", return_value="CURSOR RESULT TABLE"), patch.dict(
            sys.modules, {"shared_code.teams_bot": teams_module}
        ):
            result = worker.process_automated_test_queue_message(object(), payload)

        self.assertTrue(result["ok"])
        self.assertEqual(result["report"], "CURSOR RESULT TABLE")
        self.assertEqual(sent, [(payload["conversation_reference"], "CURSOR RESULT TABLE")])

    def test_cursor_overall_rejection_prevents_a_full_pass(self):
        result = boolean_result()
        verdict = cursor_validation()
        verdict["case_results"]["aws-001"]["overall_ok"] = False
        verdict["case_results"]["aws-001"]["reason"] = "Unrelated repository changes were detected."
        verdict["case_results"]["aws-001"]["evidence"] = ["Unexpected additional diff was present."]

        runner._apply_cursor_validation_result("ctx-test", [result], verdict)

        self.assertEqual(result.backend_score, 100)
        self.assertLess(result.score, 100)
        self.assertEqual(result.failure_classification, "CURSOR_VALIDATION_FAILURE")
        self.assertEqual(result.cursor_verdict_evidence, ["Unexpected additional diff was present."])

    def test_coverage_is_persisted_after_cursor_validation(self):
        source = Path(runner.__file__).read_text()
        validation_index = source.index(
            "cursor_validation = terrabot_cursor_result_validator.validate_test_run_with_cursor"
        )
        coverage_index = source.index("terrabot_test_state.save_coverage(", validation_index)
        self.assertGreater(coverage_index, validation_index)
        self.assertIn('"last_cursor_overall_ok"', source[coverage_index:])


if __name__ == "__main__":
    unittest.main()
