from __future__ import annotations

import unittest
from unittest.mock import patch

from shared_code.automated_tests import terrabot_test_runner as runner


class TerrabotTestRunnerRequestTests(unittest.TestCase):
    def _case(self) -> runner.TestCase:
        return runner.TestCase(
            case_id="aws-01-test",
            case_type="boolean_context",
            cloud="aws",
            owner="venasolutions",
            repo="tf-devops",
            branch="main",
            commit_sha="abc123",
            path="terraform/dev_aws/dev/main.tf",
            environment="dev",
            flag="enable_example",
            alias="example",
            current_value=True,
            desired_value=False,
            evidence_line="enable_example = true",
            phase1_prompt="disable example in dev",
            phase2_prompt="turn example off in dev",
        )

    def test_phase1_and_phase2_are_explicit_infra_with_new_branch_pre_resolved(self):
        case = self._case()
        for phase, prompt in ((1, case.phase1_prompt), (2, case.phase2_prompt)):
            with self.subTest(phase=phase):
                request = runner._phase_request(
                    case,
                    prompt,
                    f"conversation-{phase}",
                    phase=phase,
                )
                self.assertEqual(request["mode"], "infra")
                self.assertTrue(request["fresh_infra_generation"])
                self.assertTrue(request["pending_branch_choice_resolved"])
                self.assertEqual(request["branch_choice"], "new")
                self.assertTrue(request["force_new_branch"])
                self.assertFalse(request["reuse_branch"])
                self.assertEqual(request["existing_branch"], "")
                self.assertTrue(request["test_mode"])
                self.assertEqual(request["automated_test_phase"], phase)

    def test_phase1_commit_keeps_new_branch_resolution(self):
        case = self._case()

        class Core:
            captured = None

            @staticmethod
            def _teams_auto_commit_preview(request, preview, status):
                Core.captured = dict(request)
                return {
                    "ok": True,
                    "mode": "branch_created",
                    "branch": "terrabot/test",
                }, 200

        original = runner._phase_request(case, case.phase1_prompt, "conversation-1", phase=1)
        result, status = runner._commit_preview_to_test_branch(
            Core,
            case,
            "ctx-20260901-test",
            {"mode": "infra_preview", "files": [{"path": case.path}]},
            original,
        )

        self.assertEqual(status, 200)
        self.assertEqual(result["mode"], "branch_created")
        self.assertIsNotNone(Core.captured)
        self.assertTrue(Core.captured["pending_branch_choice_resolved"])
        self.assertEqual(Core.captured["branch_choice"], "new")
        self.assertTrue(Core.captured["force_new_branch"])
        self.assertFalse(Core.captured["reuse_branch"])
        self.assertEqual(Core.captured["existing_branch"], "")
        # Commit transport intentionally disables test_mode only after the
        # validated preview so Phase 1 can push the isolated test branch.
        self.assertFalse(Core.captured["test_mode"])
        self.assertEqual(Core.captured["automated_test_phase"], 1)


    def test_cursor_repository_clarification_is_handed_to_backend_structurally(self):
        case = self._case()
        row = runner.TestCaseResult(case=case)

        class Core:
            captured = None

            @staticmethod
            def handle_teams_chat_request(request):
                Core.captured = dict(request)
                return {"ok": True, "mode": "infra_preview", "files": []}, 200

        cursor_resolution = {
            "answer": f"Use {case.flag} in {case.path}.",
            "resolution_type": "repository_control",
            "candidates_relevant": False,
            "use_structured_picker": False,
            "selected_index": None,
            "selected_path": case.path,
            "selected_flag": case.flag,
            "selected_current_value": True,
            "selected_new_value": False,
            "reason": "Verified from the pinned live environment file.",
            "evidence": [f"{case.flag} = true"],
        }
        phase_request = runner._phase_request(case, case.phase1_prompt, "conversation-1", phase=1)
        initial = {
            "ok": True,
            "mode": "clarification",
            "reply": "Which repository control should I modify?",
            "thread_id": "thread-1",
            "candidates": [],
        }
        with patch.object(
            runner.cursor_prompt_provider,
            "resolve_repository_clarification",
            return_value=cursor_resolution,
        ), patch.object(runner, "_ensure_context_mapping", return_value=True):
            final, status, clarified = runner._resolve_automated_clarifications(
                Core,
                case,
                row,
                initial,
                200,
                phase=1,
                conversation_id="conversation-1",
                phase_request=phase_request,
                run_id="ctx-test",
                max_rounds=1,
            )

        self.assertTrue(clarified)
        self.assertEqual(status, 200)
        self.assertEqual(final["mode"], "infra_preview")
        self.assertIsNotNone(Core.captured)
        handoff = Core.captured["cursor_repository_resolution"]
        self.assertEqual(handoff["source"], "cursor_read_only_repository_clarification")
        self.assertEqual(handoff["path"], case.path)
        self.assertEqual(handoff["flag"], case.flag)
        self.assertIs(handoff["current_value"], True)
        self.assertIs(handoff["new_value"], False)
        self.assertFalse(Core.captured.get("pending_target_selection_reply", False))


if __name__ == "__main__":
    unittest.main()
