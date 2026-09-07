from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class SurgicalEdit:
    path: str
    old_text: str
    new_text: str
    # Optional 1-based live-file line anchor (from exact_edit_hints). When the
    # selected old_text is not unique in the live file — tfvars files routinely
    # contain dozens of identical "<name> = false" lines — the anchor selects
    # the intended occurrence deterministically instead of failing the repair.
    line_number: int = 0


def anchor_edit_to_unique_span(
    live_content: str,
    old_text: str,
    new_text: str,
    line_number: int = 0,
) -> tuple[str, str]:
    """Expand an ambiguous (old_text, new_text) pair into a unique span.

    Strategy: locate the intended occurrence (by 1-based line anchor when
    given, otherwise unresolvable), then prepend/append whole neighbor lines
    from the live file to BOTH old_text and new_text until the expanded
    old_text occurs exactly once. Run ctx-20260906-182925 failed a correct
    boolean repair with "expected old_text to occur exactly once ... found 23";
    this makes that class of repair deterministic instead of model-dependent.
    """
    if not live_content or not old_text:
        return old_text, new_text
    if live_content.count(old_text) == 1:
        return old_text, new_text
    if line_number <= 0:
        return old_text, new_text

    normalized = live_content.replace("\r\n", "\n")
    lines = normalized.split("\n")
    if line_number > len(lines):
        return old_text, new_text

    # The anchored occurrence must plausibly contain the target line. Compare
    # with collapsed whitespace so formatting drift (aligned '=' columns) does
    # not disqualify a correct anchor.
    anchor_line = lines[line_number - 1]
    def _collapse(text: str) -> str:
        return " ".join(str(text or "").split())
    first_old_line = _collapse((old_text.splitlines() or [""])[0])
    anchor_collapsed = _collapse(anchor_line)
    if (
        first_old_line
        and first_old_line not in anchor_collapsed
        and anchor_collapsed not in _collapse(old_text)
    ):
        return old_text, new_text

    old_line_count = max(1, len(old_text.split("\n")))
    start = line_number - 1
    end = start + old_line_count  # exclusive
    span = "\n".join(lines[start:end])
    if span != old_text:
        # Anchor points at the line but the reply's old_text does not equal the
        # live span (whitespace/formatting drift). Rebuild both sides from live
        # truth when this is a single-line Boolean flip: keep the live line
        # exactly and swap only the Boolean literal implied by new_text.
        if old_line_count == 1 and "\n" not in new_text:
            import re as _re
            new_literal_match = _re.search(r"\b(true|false)\b", new_text)
            span_literal_match = _re.search(r"\b(true|false)\b", span)
            old_stripped = old_text.strip()
            if old_stripped and old_stripped in span:
                new_line = span.replace(old_stripped, new_text.strip(), 1)
                old_text, new_text = span, new_line
            elif new_literal_match and span_literal_match:
                flag_token_match = _re.match(r'\s*"?([A-Za-z0-9_.-]+)"?\s*[:=]', old_text)
                flag_token = flag_token_match.group(1) if flag_token_match else ""
                if flag_token and flag_token not in span:
                    return old_text, new_text
                new_line = (
                    span[: span_literal_match.start()]
                    + new_literal_match.group(1)
                    + span[span_literal_match.end():]
                )
                old_text, new_text = span, new_line
            else:
                return old_text, new_text
        else:
            return old_text, new_text

    expanded_old, expanded_new = old_text, new_text
    lo, hi = start, end
    for _ in range(0, 60):
        if normalized.count(expanded_old) == 1:
            return expanded_old, expanded_new
        grew = False
        if lo > 0:
            lo -= 1
            expanded_old = lines[lo] + "\n" + expanded_old
            expanded_new = lines[lo] + "\n" + expanded_new
            grew = True
        if normalized.count(expanded_old) == 1:
            return expanded_old, expanded_new
        if hi < len(lines):
            expanded_old = expanded_old + "\n" + lines[hi]
            expanded_new = expanded_new + "\n" + lines[hi]
            hi += 1
            grew = True
        if not grew:
            break
    if normalized.count(expanded_old) == 1:
        return expanded_old, expanded_new
    return old_text, new_text


def _strip_quoted_text(value: str) -> str:
    out = []
    in_string = False
    escape = False
    for ch in value or "":
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            out.append(" ")
            continue
        if ch == '"':
            in_string = True
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def delimiter_signature(value: str) -> tuple[int, int, int]:
    """Return net {}, [], () balance, ignoring quoted strings."""
    text = _strip_quoted_text(value)
    return (
        text.count("{") - text.count("}"),
        text.count("[") - text.count("]"),
        text.count("(") - text.count(")"),
    )


def nonblank_line_count(value: str) -> int:
    return sum(1 for line in (value or "").splitlines() if line.strip())


def user_explicitly_requests_deletion(prompt: str) -> bool:
    return bool(re.search(r"\b(?:delete|remove|drop|destroy)\b", str(prompt or ""), re.IGNORECASE))


def validate_surgical_edit(
    *,
    path: str,
    live_content: str,
    old_text: str,
    new_text: str,
    original_user_request: str,
    max_old_lines: int = 120,
    max_live_fraction: float = 0.45,
) -> None:
    """Validate that a Foundry-selected replacement is genuinely surgical.

    This function does not decide what Terraform should change. It only proves
    that the edit can be applied to the exact live file without reconstructing
    or overwriting unrelated content.
    """
    if not path:
        raise ValueError("Surgical edit path is required.")
    if not live_content:
        raise ValueError(f"Cannot apply a surgical edit to {path}: live file content is empty.")
    if not old_text:
        raise ValueError(f"Surgical edit for {path} must include non-empty old_text copied from the live file.")
    if old_text == new_text:
        raise ValueError(f"Surgical edit for {path} does not change anything.")

    occurrences = live_content.count(old_text)
    if occurrences != 1:
        raise ValueError(
            f"Surgical edit for {path} expected old_text to occur exactly once in the exact live file, "
            f"but found {occurrences}. Include enough exact surrounding context to identify one location."
        )

    old_lines = nonblank_line_count(old_text)
    live_lines = max(1, nonblank_line_count(live_content))
    # A repair edit is an insert/replace operation, not a disguised whole-file
    # regeneration. Small files are allowed to replace a complete logical block;
    # large files must remain tightly scoped.
    if old_lines > max_old_lines and (old_lines / live_lines) > max_live_fraction:
        raise ValueError(
            f"Surgical edit for {path} is too broad ({old_lines}/{live_lines} nonblank live lines). "
            "Choose the smallest exact assignment/block that implements the user request instead of replacing most of the file."
        )

    old_sig = delimiter_signature(old_text)
    new_sig = delimiter_signature(new_text)
    if old_sig != new_sig:
        raise ValueError(
            f"Surgical edit for {path} changes HCL delimiter balance from {old_sig} to {new_sig}. "
            "The replacement is likely truncated or structurally incomplete; return a smaller complete replacement."
        )

    if not user_explicitly_requests_deletion(original_user_request):
        old_nonblank = nonblank_line_count(old_text)
        new_nonblank = nonblank_line_count(new_text)
        if old_nonblank >= 8 and new_nonblank < max(1, int(old_nonblank * 0.50)):
            raise ValueError(
                f"Surgical edit for {path} removes too much code ({old_nonblank} -> {new_nonblank} nonblank lines) "
                "for a request that did not explicitly ask to delete repository content."
            )


def apply_surgical_edits(
    *,
    path: str,
    live_content: str,
    edits: Iterable[SurgicalEdit],
    original_user_request: str,
) -> str:
    """Apply exact Foundry-selected edits while preserving all other bytes."""
    candidate = live_content
    for index, edit in enumerate(edits, start=1):
        old_text, new_text = anchor_edit_to_unique_span(
            candidate,
            edit.old_text,
            edit.new_text,
            line_number=int(getattr(edit, "line_number", 0) or 0),
        )
        validate_surgical_edit(
            path=path,
            live_content=candidate,
            old_text=old_text,
            new_text=new_text,
            original_user_request=original_user_request,
        )
        before, sep, after = candidate.partition(old_text)
        if not sep:
            raise ValueError(f"Surgical edit {index} for {path} no longer matches the current materialized candidate.")
        candidate = before + new_text + after

        # The complete materialized candidate must retain the live file's
        # delimiter signature after every edit. Comparing only old_text and
        # new_text signatures is insufficient when an overly broad fragment is
        # selected; the whole-file invariant guarantees a surgical replacement
        # can never turn a complete live file into a truncated Terraform file.
        live_signature = delimiter_signature(live_content)
        candidate_signature = delimiter_signature(candidate)
        if candidate_signature != live_signature:
            raise ValueError(
                f"Surgical edit {index} for {path} changed the complete file delimiter signature "
                f"from {live_signature} to {candidate_signature}. The edit would make the live file "
                "structurally incomplete; return a smaller complete old_text/new_text replacement."
            )
    return candidate
