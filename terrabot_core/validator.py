from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from terrabot_core.models import RepoProfile

_SAFE_PREFIXES = (
    "terraform fmt",
    "terraform validate",
    "tflint",
    "pre-commit run",
)


@dataclass
class ValidationRun:
    command: str
    return_code: int
    stdout: str = ""
    stderr: str = ""
    skipped: bool = False
    reason: str = ""


@dataclass
class ValidationReport:
    commands: List[str] = field(default_factory=list)
    runs: List[ValidationRun] = field(default_factory=list)


def get_repo_validation_commands(profile: RepoProfile) -> List[str]:
    return profile.validation_commands


def run_validation_commands(workspace: str, commands: List[str], run: bool = False, timeout_seconds: int = 120) -> ValidationReport:
    report = ValidationReport(commands=commands)
    if not run:
        report.runs = [ValidationRun(command=cmd, return_code=0, skipped=True, reason="dry run") for cmd in commands]
        return report

    cwd = Path(workspace).expanduser().resolve()
    for cmd in commands:
        if not cmd.startswith(_SAFE_PREFIXES):
            report.runs.append(ValidationRun(command=cmd, return_code=0, skipped=True, reason="not an allowlisted local command"))
            continue
        try:
            completed = subprocess.run(
                cmd,
                cwd=str(cwd),
                shell=True,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
            )
            report.runs.append(
                ValidationRun(
                    command=cmd,
                    return_code=completed.returncode,
                    stdout=completed.stdout[-4000:],
                    stderr=completed.stderr[-4000:],
                )
            )
        except Exception as exc:
            report.runs.append(ValidationRun(command=cmd, return_code=1, stderr=str(exc)))
    return report
