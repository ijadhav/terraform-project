from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "apply_to_terravsgithub.py"
SPEC = importlib.util.spec_from_file_location("apply_to_terravsgithub", SCRIPT)
assert SPEC and SPEC.loader
installer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = installer
SPEC.loader.exec_module(installer)


RUNNER_FIXTURE = '''from shared_code import repository_context
from shared_code.automated_tests import terrabot_test_state


def _derive_test_cases(core, cloud_filter, count, run_id):
    cases = []
    errors = []
    return cases[:count], errors


def next_function():
    return True
'''

LOADER_FIXTURE = '''"""Terrabot stateful core loader."""
from __future__ import annotations

from pathlib import Path

_CORE_PARTS = (
    "01_bootstrap_state.py",
    "10_teams_router_runtime.py",
)
'''

ROUTER_RUNTIME_FIXTURE = '''def call_agent(conversation_id, agent_input):
    active = {}
    teams_active = True
    context_enriched_input = (
        _teams_attach_repository_context(agent_input, active) if teams_active else agent_input
    )
    if teams_active:
        try:
            pass
        except Exception:
            pass
    return context_enriched_input


def next_function():
    return True
'''

LEGACY_CORE_FIXTURE = '''import shared_code.azure_workflow as azure_workflow_state
from shared_code import repository_context as shared_repository_context
from shared_code import pr_context as agent_pr_context


def call_agent(conversation_id, agent_input):
    active = {}
    teams_active = True
    context_enriched_input = (
        _teams_attach_repository_context(agent_input, active) if teams_active else agent_input
    )
    return context_enriched_input


def next_function():
    return True
'''


class InstallerTests(unittest.TestCase):
    def make_modular_repo(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        runner = root / installer.RUNNER_RELATIVE
        loader = root / installer.CORE_LOADER_RELATIVE
        runtime = root / installer.ROUTER_RUNTIME_RELATIVE
        runner.parent.mkdir(parents=True, exist_ok=True)
        runtime.parent.mkdir(parents=True, exist_ok=True)
        runner.write_text(RUNNER_FIXTURE, encoding="utf-8")
        loader.write_text(LOADER_FIXTURE, encoding="utf-8")
        runtime.write_text(ROUTER_RUNTIME_FIXTURE, encoding="utf-8")
        return temporary, root

    def make_legacy_repo(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        runner = root / installer.RUNNER_RELATIVE
        core = root / installer.CORE_LOADER_RELATIVE
        runner.parent.mkdir(parents=True, exist_ok=True)
        runner.write_text(RUNNER_FIXTURE, encoding="utf-8")
        core.write_text(LEGACY_CORE_FIXTURE, encoding="utf-8")
        return temporary, root

    def test_modular_plan_and_apply_are_idempotent(self) -> None:
        temporary, root = self.make_modular_repo()
        self.addCleanup(temporary.cleanup)

        plan = installer.build_plan(root)
        self.assertGreaterEqual(len(plan), 8)
        installer.apply_plan(plan)

        runner = (root / installer.RUNNER_RELATIVE).read_text(encoding="utf-8")
        loader = (root / installer.CORE_LOADER_RELATIVE).read_text(encoding="utf-8")
        runtime = (root / installer.ROUTER_RUNTIME_RELATIVE).read_text(encoding="utf-8")
        self.assertIn(installer.RUNNER_IMPORT, runner)
        self.assertIn("apply_cursor_generated_prompts", runner)
        self.assertIn(installer.CORE_IMPORT, loader)
        self.assertIn("attach_primary_context_to_agent_input", runtime)
        self.assertNotIn(
            "if teams_active:\n        context_enriched_input = terraform_primary_context",
            runtime,
        )
        self.assertTrue(
            (root / "shared_code/context/terrabot_terraform_primary_context.yaml").is_file()
        )

        self.assertEqual(installer.build_plan(root), [])

    def test_legacy_monolithic_core_fallback_is_preserved(self) -> None:
        temporary, root = self.make_legacy_repo()
        self.addCleanup(temporary.cleanup)

        plan = installer.build_plan(root)
        installer.apply_plan(plan)

        core = (root / installer.CORE_LOADER_RELATIVE).read_text(encoding="utf-8")
        self.assertIn(installer.CORE_IMPORT, core)
        self.assertIn("attach_primary_context_to_agent_input", core)
        self.assertFalse((root / installer.ROUTER_RUNTIME_RELATIVE).exists())
        self.assertEqual(installer.build_plan(root), [])

    def test_missing_runner_anchor_refuses_to_modify(self) -> None:
        temporary, root = self.make_modular_repo()
        self.addCleanup(temporary.cleanup)
        runner = root / installer.RUNNER_RELATIVE
        runner.write_text("def _derive_test_cases():\n    return []\n", encoding="utf-8")

        with self.assertRaises(installer.InstallError):
            installer.build_plan(root)

    def test_missing_runtime_anchor_refuses_to_modify(self) -> None:
        temporary, root = self.make_modular_repo()
        self.addCleanup(temporary.cleanup)
        runtime = root / installer.ROUTER_RUNTIME_RELATIVE
        runtime.write_text("def call_agent():\n    return None\n", encoding="utf-8")

        with self.assertRaises(installer.InstallError):
            installer.build_plan(root)


if __name__ == "__main__":
    unittest.main()
