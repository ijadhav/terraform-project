"""Terrabot stateful core loader.

The former monolithic core is physically decomposed into ordered domain parts in
``terrabot_core_parts/``. Each part executes in this module's namespace so all
legacy public/private imports, shared globals, ContextVars, pending state, staged
overrides, Teams conversation memory, and repair behavior remain compatible.

The ordered shared-namespace loader is deliberate: the current Terrabot workflow
contains late-bound stage aliases and shared mutable state. Ordinary imports would
change function ``__globals__`` ownership and risk behavior changes during this
refactor.
"""
from __future__ import annotations

from pathlib import Path

_CORE_PARTS = (
    "01_bootstrap_state.py",
    "02_github_workspace.py",
    "03_aws_workflow.py",
    "04_teams_environment_evidence.py",
    "05_azure_consumer_and_module.py",
    "06_azure_generation_and_validation.py",
    "07_teams_generation_flow.py",
    "08_teams_branch_and_state_flow.py",
    "09_repair_pipeline.py",
    "10_teams_router_runtime.py",
    "11_teams_request_state_machine.py",
    "12_repository_context.py",
    "13_validation_and_live_file_repair.py",
    "14_environment_resolution_overrides.py",
    "15_extended_repository_scope.py",
)


def _load_core_part(filename: str) -> None:
    path = Path(__file__).resolve().with_name("terrabot_core_parts") / filename
    source = path.read_text(encoding="utf-8")
    exec(compile(source, str(path), "exec"), globals(), globals())


for _core_part in _CORE_PARTS:
    _load_core_part(_core_part)

del _core_part
