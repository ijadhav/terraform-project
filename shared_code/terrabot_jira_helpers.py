from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse


def extract_ticket_number(value: str) -> str:
    if not value:
        return ""
    text = str(value).strip()
    for pattern in (
        r"/browse/([A-Z][A-Z0-9]+-\d+)",
        r"[?&]selectedIssue=([A-Z][A-Z0-9]+-\d+)",
        r"[?&]ticket=([A-Z][A-Z0-9]+-\d+)",
        r"\b([A-Z][A-Z0-9]+-\d+)\b",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return ""


def configured_jira_origin(jira_base_url: str) -> tuple[str, str]:
    base = str(jira_base_url or "").strip()
    if not base:
        return "", ""
    parsed = urlparse(base if re.match(r"^https?://", base, re.IGNORECASE) else f"https://{base}")
    return (parsed.scheme or "").lower(), (parsed.netloc or "").lower()


def extract_ticket_number_from_jira_link(ticket_link: str, jira_base_url: str = "") -> str:
    raw = str(ticket_link or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        return ""
    configured_scheme, configured_netloc = configured_jira_origin(jira_base_url)
    if configured_scheme and parsed.scheme.lower() != configured_scheme:
        return ""
    if configured_netloc and parsed.netloc.lower() != configured_netloc:
        return ""
    path_segments = [unquote(segment).strip() for segment in (parsed.path or "").split("/") if segment.strip()]
    for marker in {"browse", "issues"}:
        for index, segment in enumerate(path_segments):
            if segment.lower() == marker and index + 1 < len(path_segments):
                return path_segments[index + 1].upper()
    query = parse_qs(parsed.query or "")
    for param_name in ("selectedIssue", "ticket", "issue", "issueKey"):
        for value in query.get(param_name) or []:
            ticket_number = extract_ticket_number(value)
            if ticket_number:
                return ticket_number
    return ""
