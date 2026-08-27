"""Coverage keys and selection policy for adaptive Terrabot test exploration."""
from __future__ import annotations

from typing import Any


def coverage_key(case: Any) -> str:
    return "|".join([
        str(getattr(case, "cloud", "")).lower(),
        str(getattr(case, "repo", "")).lower(),
        str(getattr(case, "environment", "")).lower(),
        str(getattr(case, "case_type", "")).lower(),
        str(getattr(case, "flag", "") or getattr(case, "alias", "")).lower(),
    ])


def selection_rank(case: Any, coverage: dict[str, Any]) -> tuple[int, int, str]:
    item = coverage.get(coverage_key(case)) or {}
    tested = int(item.get("test_count") or 0)
    last_score = int(item.get("last_score") or 0)
    failures = int(item.get("failure_count") or 0)
    # Lower tuple sorts first: never-tested, then failures/low score, then least tested.
    never_tested = 0 if tested == 0 else 1
    health = last_score - min(failures * 10, 50)
    return (never_tested, health, f"{tested:06d}:{coverage_key(case)}")


def select_cases(cases: list[Any], coverage: dict[str, Any], count: int) -> list[Any]:
    ranked = sorted(cases, key=lambda case: selection_rank(case, coverage))
    return ranked[: max(0, count)]
