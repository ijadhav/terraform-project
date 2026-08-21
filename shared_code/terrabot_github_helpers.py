from __future__ import annotations

import re


def unique_non_empty(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values or []:
        item = str(value or "").strip().replace("refs/heads/", "")
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def valid_git_branch_name(value: str) -> bool:
    value = str(value or "").strip()
    return bool(value and re.fullmatch(r"[A-Za-z0-9._/-]+", value))


def sanitize_requester_branch_slug(value: str, fallback: str = "terrabot") -> str:
    slug = re.sub(r"[^A-Za-z0-9-]+", "-", str(value or "")).strip("-").lower()
    return slug[:40] or fallback
