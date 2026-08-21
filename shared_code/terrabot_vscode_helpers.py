from __future__ import annotations

import re


def pull_request_template_headings(template: str) -> list[str]:
    return [match.group(0).strip() for match in re.finditer(r"(?m)^#{1,6}\s+.+$", template or "")]


def body_follows_template(template: str, body: str) -> bool:
    headings = pull_request_template_headings(template)
    if not headings:
        return bool(str(body or "").strip())
    cursor = 0
    for heading in headings:
        index = str(body or "").find(heading, cursor)
        if index < 0:
            return False
        cursor = index + len(heading)
    return True
