from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import uuid
from types import SimpleNamespace
from typing import Any, Dict, Optional

from botbuilder.core import ActivityHandler, TurnContext
from botbuilder.integration.aiohttp import (
    CloudAdapter,
    ConfigurationBotFrameworkAuthentication,
)
from botbuilder.schema import Activity, ActivityTypes, ConversationReference
from shared_code import teams_conversation_memory
from shared_code.automated_tests.terrabot_test_runner import is_automated_test_command
from shared_code.terrabot_service import (
    handle_teams_chat_request,
    handle_teams_automated_test_request,
    handle_teams_workspace_branch_request,
    load_teams_conversation_state,
    reset_teams_chat_session,
    save_teams_conversation_state,
    set_teams_conversation_context,
    set_teams_short_follow_up,
)


LOGGER = logging.getLogger("terrabot.teams")

TEAMS_THREAD_STATE: Dict[str, Dict[str, Any]] = {}

AFFIRMATIVE_RE = re.compile(
    r"^(yes|y|yeah|yep|sure|ok|okay|publish|create pr|open pr|raise pr|commit|commit it|send pr)$",
    re.I,
)
PR_REQUEST_RE = re.compile(
    r"^(?:please\s+)?(?:raise|create|open|submit|make)\s+(?:a\s+)?(?:draft\s+)?(?:pr|pull request)(?:\s+.*)?$",
    re.I,
)
BRANCH_RE = re.compile(
    r"^(?:create|make|open)\s+(?:a\s+)?(?:github\s+)?branch"
    r"(?:\s+(?:named|called))?\s+([A-Za-z0-9._/-]+)"
    r"(?:\s+(?:in|for)\s+(aws|azure))?$",
    re.I,
)
NEGATIVE_RE = re.compile(
    r"^(no|n|nope|cancel|discard|discard it|do not publish|don't publish)$",
    re.I,
)
BRANCH_REUSE_DECISION_RE = re.compile(
    r"^(?:yes|y|reuse|same|current|existing)(?:\s+branch)?$",
    re.I,
)
BRANCH_NEW_DECISION_RE = re.compile(
    r"^(?:no|n|new|fresh|different|separate)(?:\s+branch)?$",
    re.I,
)
JIRA_RE = re.compile(
    r"(https?://\S+/browse/([A-Z][A-Z0-9]+-\d+))|\b([A-Z][A-Z0-9]+-\d+)\b"
)
RESET_CHAT_RE = re.compile(
    r"^(?:please\s+)?(?:(?:/)?clear|clear\s+(?:the\s+)?(?:chat|terminal|history)|"
    r"new\s+(?:chat|request|conversation|thread)|"
    r"start\s+(?:a\s+)?new\s+(?:chat|request|conversation|thread)|"
    r"switch\s+to\s+(?:a\s+)?new\s+(?:chat|request|conversation|thread)|"
    r"reset\s+(?:the\s+)?(?:chat|conversation|thread|session))$",
    re.I,
)

def _is_freeform_user_message(text: str) -> bool:
    """True for ordinary language that is not a deterministic workflow reply.

    This helper does not classify chat vs infrastructure. That semantic decision
    belongs to Foundry. It only prevents yes/no/Jira/reset protocol messages from
    being mistaken for a new freeform turn.
    """
    value = str(text or "").strip()
    if not value:
        return False
    normalized = value.lower()
    if AFFIRMATIVE_RE.match(normalized) or NEGATIVE_RE.match(normalized):
        return False
    if RESET_CHAT_RE.match(value) or JIRA_RE.fullmatch(value):
        return False
    return True


def _is_explicit_infrastructure_prompt(text: str) -> bool:
    """Deprecated compatibility shim; semantic intent is Foundry-owned."""
    del text
    return False


def _required_setting(*names: str) -> str:
    for name in names:
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def _bot_authentication() -> ConfigurationBotFrameworkAuthentication:
    app_id = _required_setting("MicrosoftAppId", "TEAMS_BOT_APP_ID")
    app_password = _required_setting(
        "MicrosoftAppPassword",
        "TEAMS_BOT_APP_PASSWORD",
    )
    tenant_id = _required_setting(
        "MicrosoftAppTenantId",
        "TEAMS_BOT_TENANT_ID",
        "AZURE_TENANT_ID",
    )
    app_type = _required_setting("MicrosoftAppType", "TEAMS_BOT_APP_TYPE")
    if not app_type:
        app_type = "SingleTenant" if tenant_id else "MultiTenant"

    missing = []
    if not app_id:
        missing.append("MicrosoftAppId")
    if not app_password:
        missing.append("MicrosoftAppPassword")
    if app_type.lower() == "singletenant" and not tenant_id:
        missing.append("MicrosoftAppTenantId")
    if missing:
        raise RuntimeError(
            "Missing Teams bot application setting(s): " + ", ".join(missing)
        )

    LOGGER.info(
        "Creating Teams CloudAdapter: app_type=%s app_id_configured=%s "
        "password_configured=%s tenant_configured=%s",
        app_type,
        bool(app_id),
        bool(app_password),
        bool(tenant_id),
    )

    configuration = SimpleNamespace(
        APP_TYPE=app_type,
        APP_ID=app_id,
        APP_PASSWORD=app_password,
        APP_TENANTID=tenant_id,
    )
    return ConfigurationBotFrameworkAuthentication(configuration=configuration)


ADAPTER = CloudAdapter(_bot_authentication())


async def _on_turn_error(turn_context: TurnContext, error: Exception) -> None:
    LOGGER.exception("Unhandled Teams bot turn error", exc_info=error)
    try:
        await turn_context.send_activity(
            "Terrabot received your message but could not complete it. "
            "Check the Function App logs for the matching request."
        )
    except Exception:
        LOGGER.exception("Unable to send Teams error response")


ADAPTER.on_turn_error = _on_turn_error


def _strip_bot_mentions(activity: Activity) -> str:
    try:
        text = TurnContext.remove_recipient_mention(activity) or activity.text or ""
    except Exception:
        text = activity.text or ""
    text = re.sub(r"<at>.*?</at>", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def _extract_ticket(text: str) -> tuple[str, str]:
    match = JIRA_RE.search(text or "")
    if not match:
        return "", ""
    if match.group(1):
        return match.group(2) or "", match.group(1)

    ticket = match.group(3) or ""
    jira_base = os.getenv("JIRA_BASE_URL", "").strip().rstrip("/")
    return ticket, f"{jira_base}/browse/{ticket}" if jira_base else ticket


def _get_thread_id(activity: Activity) -> str:
    """Return a stable, per-user Teams conversation key.

    Teams conversation IDs are shared in group/channel threads. Including the
    sender identity prevents one user's pending workflow, Foundry thread, or
    branch decision from leaking into another user's session while remaining
    stable across devices and Function App worker restarts.
    """
    conversation_id = (
        str(getattr(getattr(activity, "conversation", None), "id", "") or "").strip()
        or str(getattr(activity, "id", "") or "").strip()
        or "teams-thread"
    )
    sender = getattr(activity, "from_property", None)
    sender_id = (
        str(getattr(sender, "aad_object_id", "") or "").strip()
        or str(getattr(sender, "id", "") or "").strip()
        or "anonymous"
    )
    sender_hash = hashlib.sha256(sender_id.encode("utf-8")).hexdigest()[:20]
    return f"{conversation_id}::user::{sender_hash}"


def _new_memory_conversation_id(thread_id: str) -> str:
    """Return a unique logical-memory id inside one stable Teams thread."""
    return f"{thread_id}::memory::{uuid.uuid4().hex}"


async def _ensure_memory_conversation(
    thread_id: str,
    state: Dict[str, Any],
    requester: str,
    *,
    reason: str = "initial_conversation",
    previous_conversation_id: str = "",
) -> str:
    memory_id = str(state.get("memory_conversation_id") or "").strip()
    if memory_id:
        return memory_id
    memory_id = _new_memory_conversation_id(thread_id)
    state["memory_conversation_id"] = memory_id
    await _persist_thread_state(thread_id, state)
    # This id is workflow/session-local only. The retired agent-memory Table
    # Store is intentionally not written; shared durable knowledge is stored
    # separately at repository scope in Azure AI Search.
    del requester, reason, previous_conversation_id
    return memory_id


async def _rotate_memory_conversation(
    thread_id: str,
    requester: str,
    *,
    reason: str,
    previous_conversation_id: str = "",
) -> str:
    fresh_state: Dict[str, Any] = {}
    memory_id = _new_memory_conversation_id(thread_id)
    fresh_state["memory_conversation_id"] = memory_id
    await _persist_thread_state(thread_id, fresh_state)
    # Rotation only separates user-specific session continuity. It does not
    # create a durable conversation-memory row.
    del requester, reason, previous_conversation_id
    return memory_id


async def _load_thread_state(thread_id: str) -> Dict[str, Any]:
    """Load durable state first, with the process cache as a fast fallback."""
    local_state = dict(TEAMS_THREAD_STATE.get(thread_id) or {})
    try:
        durable_state = await asyncio.to_thread(
            load_teams_conversation_state,
            thread_id,
        )
    except Exception:
        LOGGER.exception(
            "Unable to load durable Teams conversation state: conversation=%s",
            thread_id,
        )
        durable_state = {}

    if durable_state:
        local_state.update(durable_state)
    TEAMS_THREAD_STATE[thread_id] = local_state
    return local_state


async def _persist_thread_state(thread_id: str, state: Dict[str, Any]) -> None:
    """Persist routing state before returning a reply to Teams."""
    snapshot = dict(state or {})
    TEAMS_THREAD_STATE[thread_id] = snapshot
    try:
        stored = await asyncio.to_thread(
            save_teams_conversation_state,
            thread_id,
            snapshot,
        )
        if not stored:
            LOGGER.error(
                "Durable Teams state was not stored: conversation=%s. "
                "Multi-turn continuity may be lost if the Function worker changes.",
                thread_id,
            )
    except Exception:
        LOGGER.exception(
            "Unable to persist durable Teams conversation state: conversation=%s",
            thread_id,
        )


def _get_teams_requester(activity: Activity) -> str:
    from_property = activity.from_property
    display_name = str(getattr(from_property, "name", "") or "").strip()
    aad_object_id = str(getattr(from_property, "aad_object_id", "") or "").strip()
    fallback_id = str(getattr(from_property, "id", "") or "").strip()
    return display_name or aad_object_id or fallback_id or "teams-user"


def _clean_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    result = []
    for value in values:
        if isinstance(value, dict):
            value = value.get("path") or value.get("filename") or value.get("input") or ""
        value = str(value or "").strip()
        if value and value not in result:
            result.append(value)
    return result


def _extract_json_payload(value: str) -> Dict[str, Any]:
    """Best-effort extraction for agent JSON accidentally returned as text."""
    raw = str(value or "").strip()
    if not raw:
        return {}
    candidates = [raw]
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.IGNORECASE | re.DOTALL)
    if fenced:
        candidates.insert(0, fenced.group(1))
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        candidates.append(raw[start:end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _format_fillable(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    lines = []
    for item in values:
        if not isinstance(item, dict):
            continue
        name = str(item.get("input") or item.get("token") or "value").strip()
        hint = str(item.get("hint") or "Provide the required value.").strip()
        file_name = str(item.get("file") or "").strip()
        suffix = f" (`{file_name}`)" if file_name else ""
        lines.append(f"- `{name}`{suffix}: {hint}")
    return lines


def _format_analysis_block(analysis: str) -> list[str]:
    """Match the VS Code presentation: a visible, quoted Terrabot decision log."""
    lines = [line.strip() for line in str(analysis or "").splitlines() if line.strip()]
    if not lines:
        return []
    return ["**Terrabot's analysis**", *[f"> {line}" for line in lines]]


def _format_evidence_paths(paths: Any) -> list[str]:
    values = _clean_list(paths)[:8]
    if not values:
        return []
    return ["**Repository evidence used**", *[f"- `{value}`" for value in values]]


def _format_related_pull_requests(result: Dict[str, Any]) -> list[str]:
    """Surface already-raised (including draft) PRs related to this request.

    Populated by ``terrabot_service.handle_teams_chat_request``'s duplicate/
    related pull-request check so users are told when their request overlaps
    with in-flight work instead of only discovering it after generation.
    """
    matches = result.get("related_pull_requests")
    if not isinstance(matches, list) or not matches:
        return []
    lines = [
        "**Related pull request(s) already raised**",
        "Terrabot found existing pull request(s) on this repository that look related to this request:",
    ]
    for item in matches[:5]:
        if not isinstance(item, dict):
            continue
        number = item.get("number")
        title = str(item.get("title") or "").strip()
        author = str(item.get("author") or "").strip() or "unknown"
        branch = str(item.get("branch") or "").strip()
        state = str(item.get("state") or "").strip()
        draft = bool(item.get("draft"))
        url = str(item.get("url") or "").strip()
        status = f"{state}{' draft' if draft else ''}".strip()
        lines.append(
            f"- PR #{number} \"{title}\" by {author} (`{branch}`, {status}): {url}"
        )
    lines.append(
        "Review these before continuing — Terrabot will still proceed with this request unless you tell it to stop."
    )
    return lines


def _format_checkout_command(branch: Any) -> str:
    branch_name = str(branch or "").strip()
    if not branch_name:
        return ""
    return (
        f"git fetch origin {branch_name} && "
        f"git switch --track origin/{branch_name}"
    )


def _format_reply(result: Dict[str, Any]) -> str:
    """Render backend payloads as concise Teams messages, never raw JSON."""
    mode = str(result.get("mode") or "chat")
    reply = str(result.get("reply") or result.get("summary") or "Done.").strip()

    payload = _extract_json_payload(reply)
    if payload:
        reply = str(payload.get("reply") or payload.get("summary") or "Done.").strip()
        for key in ("analysis", "source_paths_used", "questions", "files", "user_fillable", "summary", "validation_commands"):
            if key not in result and key in payload:
                result[key] = payload[key]

    questions = _clean_list(result.get("questions"))
    files = _clean_list(result.get("files"))
    analysis = str(result.get("analysis") or "").strip()
    source_paths = result.get("source_paths_used") or []
    summary = str(result.get("summary") or "").strip()
    fillable = _format_fillable(result.get("user_fillable"))

    if result.get("suppressed_azure_module_discovery"):
        reply = summary or (
            "Terrabot could not identify one safe live-repository target after repository analysis."
        )

    if mode in {"infra_preview", "clarification"}:
        # Keep Teams clarification UX intentionally small. Repository-derived
        # decisions belong in the backend/agent workflow; the end user should
        # see only the one genuinely blocking question, if there is one.
        visible_reply = summary or reply
        related_pr_lines = _format_related_pull_requests(result)

        if mode == "clarification":
            # Target disambiguation must render the choices themselves. The old
            # renderer extracted only the first question/"Reply ..." line,
            # which produced "select option number" with no visible options.
            candidate_items = result.get("candidates") or []
            if isinstance(candidate_items, list) and candidate_items:
                flag_items = [item for item in candidate_items if isinstance(item, dict) and str(item.get("flag") or "").strip()]
                if flag_items:
                    lines = []
                    if analysis:
                        lines.extend(_format_analysis_block(analysis))
                        lines.append("")
                    requested_value = str(flag_items[0].get("requested_value") or "").strip().lower()
                    verb = "disable" if requested_value == "false" else "enable"
                    lines.extend([
                        "**Choose the Boolean parameter**",
                        f"I found multiple repository-backed Boolean parameters that can control this request. Which parameter should I {verb}?",
                        "",
                    ])
                    for fallback_index, item in enumerate(flag_items[:8], start=1):
                        index = item.get("index") or fallback_index
                        flag = str(item.get("flag") or "").strip()
                        flag_context = str(item.get("flag_context") or "").strip()
                        lines.append(f"{index}. **`{flag}`** — {flag_context or 'existing Boolean flag in the target environment main.tf'}")
                    lines.extend([
                        "",
                        f"Reply with the number or exact Boolean parameter name. Terrabot will {verb} only the selected parameter and preserve the rest of the file unchanged.",
                    ])
                    return "\n".join(lines)
                lines = []
                if analysis:
                    lines.extend(_format_analysis_block(analysis))
                    lines.append("")
                lines.extend([
                    "**Choose the infrastructure target**",
                    summary or "I found more than one similar live-repository match.",
                    "",
                ])
                # Show every discovered candidate (up to a generous display cap),
                # ordered by relevance to the prompt when the backend supplied a
                # relevance_score, so a file whose content actually matches the
                # request (e.g. waf.tf for "disable ... waf ...") is visible
                # instead of being pushed off-screen by an alphabetical top-6.
                ordered_candidates = [item for item in candidate_items if isinstance(item, dict)]
                if any("relevance_score" in item for item in ordered_candidates):
                    ordered_candidates = sorted(
                        ordered_candidates,
                        key=lambda item: (-int(item.get("relevance_score") or 0), str(item.get("path") or "")),
                    )
                display_limit = 15
                for fallback_index, item in enumerate(ordered_candidates[:display_limit], start=1):
                    index = item.get("index") or fallback_index
                    path = str(item.get("path") or "").strip()
                    blocks = [str(value).strip() for value in (item.get("matched_blocks") or []) if str(value).strip()]
                    label = blocks[0] if blocks else path.rsplit("/", 1)[-1] if path else "Terraform target"
                    content_summary = str(item.get("content_summary") or "").strip()
                    suffix = f" — {content_summary}" if content_summary else ""
                    lines.append(f"{index}. **{label}** — `{path}`{suffix}")
                remaining = len(ordered_candidates) - display_limit
                if remaining > 0:
                    lines.append(f"...and {remaining} more file(s) in this environment. Reply with a path or resource name if you don't see it above.")
                lines.extend([
                    "",
                    "Reply with the number, resource/module name, or path. Terrabot will continue the original request after your selection.",
                ])
                if related_pr_lines:
                    lines.extend(["", *related_pr_lines])
                return "\n".join(lines)

            if questions:
                lines = []
                if analysis:
                    lines.extend(_format_analysis_block(analysis))
                    lines.append("")
                lines.extend([
                    "**Terrabot question**",
                    questions[0],
                ])
                if related_pr_lines:
                    lines.extend(["", *related_pr_lines])
                return "\n".join(lines)

            # Preserve a backend-formatted multi-line choice reply instead of
            # collapsing it to a single sentence. This supports semantic
            # near-match choices even when the backend did not attach a
            # structured candidates array.
            clean = re.split(
                r"\n\s*\*\*Terrabot(?:'s)? analysis\*\*",
                visible_reply,
                maxsplit=1,
                flags=re.I,
            )[0].strip()
            numbered = [line for line in clean.splitlines() if re.match(r"^\s*\d+[.)]\s+", line)]
            if numbered:
                lines = []
                if analysis:
                    lines.extend(_format_analysis_block(analysis))
                    lines.append("")
                lines.extend(["**Choose the infrastructure target**", clean[:3000]])
                return "\n".join(lines)

            question_lines = [
                line.strip(" -\t")
                for line in clean.splitlines()
                if line.strip()
                and ("?" in line or line.strip().lower().startswith("reply "))
            ]
            if question_lines:
                return "\n".join([
                    "**Terrabot question**",
                    question_lines[0][:700],
                ])

            first_sentence = re.split(
                r"(?<=[.!?])\s+",
                re.sub(r"\s+", " ", clean).strip(),
                maxsplit=1,
            )[0]
            return "\n".join([
                "**Terrabot question**",
                first_sentence[:700]
                or "Terrabot could not complete this request.",
            ])

        # Preserve the existing infra-preview behavior. This patch only reduces
        # clarification verbosity/questions and does not change branch/PR flow.
        lines = ["**Infrastructure change prepared**", visible_reply]
        if analysis:
            lines.extend(["", *_format_analysis_block(analysis)])
        related_pr_lines = _format_related_pull_requests(result)
        if related_pr_lines:
            lines.extend(["", *related_pr_lines])
        evidence_lines = _format_evidence_paths(source_paths)
        if evidence_lines:
            lines.extend(["", *evidence_lines])
        if files:
            lines.extend(["", "**Files**", *[f"- `{item}`" for item in files]])
        if fillable:
            lines.extend(["", "**Values to fill after branch creation**", *fillable])
        lines.extend([
            "",
            "Reply `yes` to create the Terrabot branch and push the generated changes. "
            "A pull request is created only when you explicitly ask for one.",
        ])
        return "\n".join(line for line in lines if line is not None)

    if mode == "branch_choice_required":
        branch = str(result.get("branch") or "").strip()
        lines = [
            "**Choose where to apply the follow-up change**",
            reply,
        ]
        if branch:
            lines.extend(["", f"**Current branch:** `{branch}`"])
        if result.get("branch_url"):
            lines.extend(["", "**Branch link**", str(result.get("branch_url"))])
        if result.get("compare_url"):
            lines.extend(["", "**Current diff**", str(result.get("compare_url"))])
        lines.extend([
            "",
            "- Reply `yes` to use the same branch and generate against its latest remote contents.",
            "- Reply `no` to create a new `terrabot/` branch from the latest remote base branch.",
        ])
        return "\n".join(lines)

    if mode == "branch_created":
        reused = bool(result.get("branch_reused"))
        heading = "**Existing Terrabot branch updated**" if reused else "**Changes pushed to a new Terrabot branch**"
        # The branch has already been generated and pushed. Do not expose the
        # Foundry/backend planning narrative or ask for implementation approval
        # after the fact; show only the executed result.
        lines = [heading, summary or reply]
        if analysis:
            lines.extend(["", *_format_analysis_block(analysis)])
        related_pr_lines = _format_related_pull_requests(result)
        if related_pr_lines:
            lines.extend(["", *related_pr_lines])
        evidence_lines = _format_evidence_paths(source_paths)
        if evidence_lines:
            lines.extend(["", *evidence_lines])
        if files:
            lines.extend(["", "**Files changed**", *[f"- `{item}`" for item in files]])
        if fillable:
            lines.extend([
                "",
                "**Placeholder values to review**",
                *fillable,
                "",
                "The generated branch is reviewable now. Replace the listed `__FILL__...__` values before merge.",
            ])
        base_branch = str(result.get("base_branch") or "main").strip() or "main"
        branch_name = str(result.get("branch") or "").strip()
        checkout_command = _format_checkout_command(branch_name)
        lines.extend([
            "",
            "**Branch**",
            str(result.get("branch_url") or branch_name),
            "",
            f"**Compare with {base_branch}**",
            str(result.get("compare_url") or ""),
        ])
        if checkout_command:
            lines.extend([
                "",
                "**Check out this branch in your IDE**",
                f"`{checkout_command}`",
            ])
        lines.extend([
            "",
            "**Next step**",
            "- Reply `yes` to create a pull request. Terrabot will ask for a Jira ticket link before opening it.",
            "- Send another infrastructure request to continue; Terrabot will ask whether to reuse this branch when appropriate.",
        ])
        return "\n".join(lines)

    if mode == "jira_required":
        lines = [
            "**Jira ticket required before pull request creation**",
            reply or "The Terraform changes are already pushed to a Terrabot branch.",
        ]
        if result.get("branch_url"):
            lines.extend(["", f"**Branch:** {result.get('branch_url')}"])
        if result.get("compare_url"):
            base_branch = str(result.get("base_branch") or "main").strip() or "main"
            lines.append(f"**Compare with {base_branch}:** {result.get('compare_url')}")
        lines.extend([
            "",
            "Send the Jira ticket link, for example `https://<jira-host>/browse/STO-1234`. "
            "Terrabot will then create or refresh the pull request description from the current branch changes.",
        ])
        return "\n".join(lines)

    if mode == "pr_created" or result.get("pr_url"):
        lines = ["**Pull request created**", reply]
        if analysis:
            lines.extend(["", *_format_analysis_block(analysis)])
        if result.get("branch_url"):
            lines.extend(["", "**Branch**", str(result.get("branch_url"))])
        if result.get("compare_url"):
            lines.extend(["", "**Compare with base**", str(result.get("compare_url"))])
        lines.extend(["", "**Pull request**", str(result.get("pr_url") or "")])
        return "\n".join(lines)

    if questions:
        return "\n".join([reply, "", "**Needed from you**", *[f"{idx}. {item}" for idx, item in enumerate(questions, start=1)]])
    return reply


async def _send(
    turn_context: TurnContext,
    text: str,
) -> None:
    try:
        teams_conversation_memory.record_bot_message(
            _get_thread_id(turn_context.activity), text
        )
    except Exception:
        LOGGER.debug("conversation memory record skipped", exc_info=True)

    logging.warning(
        "TEAMS-DIAG-5: starting outbound send "
        "service_url=%s conversation=%s text_length=%s",
        turn_context.activity.service_url,
        getattr(turn_context.activity.conversation, "id", ""),
        len(text or ""),
    )

    try:
        response = await turn_context.send_activity(text)
    except Exception as exc:
        logging.exception(
            "TEAMS-DIAG-ERROR: outbound Teams send failed "
            "exception_type=%s exception=%s "
            "service_url=%s conversation=%s",
            type(exc).__name__,
            str(exc),
            turn_context.activity.service_url,
            getattr(turn_context.activity.conversation, "id", ""),
        )
        raise

    logging.warning(
        "TEAMS-DIAG-6: outbound activity sent activity_id=%s",
        getattr(response, "id", ""),
    )



def _remember_user_turn(state: Dict[str, Any], prompt: str) -> None:
    turns = list(state.get("recent_user_turns") or [])
    cleaned = str(prompt or "").strip()
    if cleaned:
        turns.append(cleaned)
    state["recent_user_turns"] = turns[-12:]


def _is_short_contextual_follow_up(prompt: str, state: Dict[str, Any]) -> bool:
    text = str(prompt or "").strip()
    if not text or len(text) > 80:
        return False
    if not state.get("last_infra_prompt"):
        return False
    normalized = text.lower()
    if RESET_CHAT_RE.match(text) or PR_REQUEST_RE.match(text):
        return False
    if AFFIRMATIVE_RE.match(normalized) or NEGATIVE_RE.match(normalized):
        return True
    # Environment, cloud, module choice, simple value, or terse correction.
    return bool(
        re.fullmatch(r"(?:aws|azure|[a-z0-9._/-]{1,48}|\d+)", normalized)
        or bool(state.get("pending_rule2_prompt"))  # name reply after exists-question
    )

def _teams_extract_resource_name_from_prompt(prompt: str) -> str:
    text = str(prompt or "").lower()
    for pattern in (
        r"\bwhose\s+name\s+is\s+[\"']?([a-z0-9][a-z0-9_-]{1,63})",
        r"\bname\s+is\s+[\"']?([a-z0-9][a-z0-9_-]{1,63})",
        r"\bnamed\s+[\"']?([a-z0-9][a-z0-9_-]{1,63})",
        r"\bcalled\s+[\"']?([a-z0-9][a-z0-9_-]{1,63})",
    ):
        m = re.search(pattern, text)
        if m and m.group(1) not in {"is", "a", "an", "the"}:
            return m.group(1)
    return ""

def _is_infra_target_selection_reply(prompt: str) -> bool:
    """True for compact target/flag picker replies, not new user requests."""
    text = str(prompt or "").strip().strip("`'\"")
    if not text:
        return False
    if re.fullmatch(r"#?\d+", text):
        return True
    if re.fullmatch(r"(?i)(?:create|enable|enabled|deploy|use|has|is)_[A-Za-z0-9_.-]{1,120}", text):
        return True
    if re.fullmatch(r"(?i)[A-Za-z_][A-Za-z0-9_.-]{1,120}_enabled", text):
        return True
    if re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+\.(?:tf|tfvars)", text):
        return True
    return False


def _is_rule2_name_reply(prompt: str, state: dict) -> bool:
    """True when the user is replying with a new resource name after a
    RULE-2 exists-question. The name must be a valid terraform identifier
    (alphanumeric + hyphens/underscores, no spaces) and state must hold
    a pending_rule2_prompt from the previous turn."""
    if not state.get("pending_rule2_prompt"):
        return False
    text = str(prompt or "").strip().lower()
    # Strip optional leading "use " so "use homepage-bff-2" works
    text = re.sub(r"^use\s+", "", text).strip()
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,62}", text))


def _rule2_name_from_reply(prompt: str) -> str:
    text = str(prompt or "").strip().lower()
    text = re.sub(r"^use\s+", "", text).strip()
    return text

def _contextual_prompt(prompt: str, state: Dict[str, Any]) -> str:
    # RULE-2 name reply: reconstruct a full creation prompt so all existing
    # parsing paths (cloud inference, env resolution, invocation context)
    # get the right name and environment — no cloud question possible.
    if _is_rule2_name_reply(prompt, state):
        new_name = _rule2_name_from_reply(prompt)
        prior = str(state.get("pending_rule2_prompt") or state.get("last_infra_prompt") or "").strip()
        # Replace the original resource name with the new one.
        old_name = _teams_extract_resource_name_from_prompt(prior) if prior else ""
        if old_name and old_name in prior.lower():
            new_prompt = re.sub(re.escape(old_name), new_name, prior, count=1, flags=re.IGNORECASE)
        else:
            new_prompt = prior + f" Use the name {new_name}."
        return new_prompt
    if not _is_short_contextual_follow_up(prompt, state):
        return prompt
    prior = str(state.get("last_infra_prompt") or "").strip()
    return (
        "Continue the current infrastructure request using the same repository "
        "and live GitHub context. Previous request: " + prior +
        "\nUser follow-up: " + str(prompt or "").strip()
    )


class TerrabotTeamsBot(ActivityHandler):
    async def on_message_activity(self, turn_context: TurnContext):
        activity = turn_context.activity
        thread_id = _get_thread_id(activity)
        prompt = _strip_bot_mentions(activity)

        LOGGER.info(
            "Teams message received: channel=%s conversation=%s activity=%s "
            "text_length=%s service_url=%s",
            activity.channel_id,
            thread_id,
            activity.id,
            len(prompt),
            activity.service_url,
        )

        if not prompt:
            await _send(
                turn_context,
                "Send a message or an infrastructure request, for example: "
                "create a storage account in npr.",
            )
            return

        sender = getattr(activity, "from_property", None)
        LOGGER.warning(
            "TEAMS-IDENTITY: name=%s aad_object_id=%s teams_id=%s",
            getattr(sender, "name", ""),
            getattr(sender, "aad_object_id", ""),
            getattr(sender, "id", ""),
        )
        # Automated repository-context testing is intercepted before the normal
        # Teams workflow. This path only validates/queues the run (or reads
        # durable status); the expensive test work executes in the queue worker.
        if is_automated_test_command(prompt):
            sender = getattr(activity, "from_property", None)
            aad_object_id = str(getattr(sender, "aad_object_id", "") or "").strip()
            reference = TurnContext.get_conversation_reference(activity)
            try:
                reference_payload = reference.serialize() if hasattr(reference, "serialize") else {}
            except Exception:
                reference_payload = {}
            try:
                test_result, test_status = await asyncio.to_thread(
                    handle_teams_automated_test_request,
                    {
                        "prompt": prompt,
                        "aad_object_id": aad_object_id,
                        "teams_conversation_id": thread_id,
                        "teams_requester": _get_teams_requester(activity),
                        "conversation_reference": reference_payload,
                    },
                )
            except Exception as exc:
                LOGGER.exception("Terrabot automated Teams test queueing failed", exc_info=exc)
                await _send(
                    turn_context,
                    "Terrabot could not queue the automated tests. Check the Function App logs for `[TerrabotTest]` entries.",
                )
                return

            await _send(
                turn_context,
                str(test_result.get("reply") or f"Automated test request finished with HTTP status {test_status}."),
            )
            return

        state = await _load_thread_state(thread_id)
        requester = _get_teams_requester(activity)
        memory_conversation_id = await _ensure_memory_conversation(
            thread_id, state, requester
        )
        _remember_user_turn(state, prompt)
        teams_conversation_memory.record_user_message(thread_id, prompt)
        set_teams_conversation_context(
            teams_conversation_memory.get_context_block(thread_id)
        )
        set_teams_short_follow_up(_is_short_contextual_follow_up(prompt, state))
        effective_prompt = _contextual_prompt(prompt, state)
        normalized = prompt.strip().lower()

        # Reset is an explicit command, not a yes/no workflow. Execute it
        # immediately so a later `no` can never be consumed as reset
        # cancellation instead of a branch decision.
        if RESET_CHAT_RE.match(prompt.strip()):
            workflow_thread_id = str(
                state.get("workflow_thread_id")
                or state.get("foundry_conversation_id")
                or ""
            ).strip()
            try:
                reset_result = await asyncio.to_thread(
                    reset_teams_chat_session,
                    thread_id,
                    workflow_thread_id,
                )
            except Exception:
                LOGGER.exception(
                    "Unable to reset Teams chat session: conversation=%s",
                    thread_id,
                )
                await _send(
                    turn_context,
                    "Terrabot could not clear the current chat state. "
                    "No state was intentionally changed; check the Function App logs.",
                )
                return

            previous_memory_id = memory_conversation_id
            TEAMS_THREAD_STATE.pop(thread_id, None)
            teams_conversation_memory.clear(thread_id)
            # Preserve the completed memory row. A clear starts a brand-new
            # logical conversation row instead of emptying/reusing the old one.
            memory_conversation_id = await _rotate_memory_conversation(
                thread_id,
                requester,
                reason="clear_chat",
                previous_conversation_id=previous_memory_id,
            )
            set_teams_short_follow_up(False)
            set_teams_conversation_context("")
            cleared_workflows = int(reset_result.get("workflow_states_cleared") or 0)
            await _send(
                turn_context,
                "**New Terrabot chat started**\n"
                "Terrabot's stored Teams conversation history, Foundry thread pointers, "
                "pending target/module/value selections, previews, branch decisions, "
                "Jira context, and other uncommitted request state were cleared. "
                f"Cleared workflow states: {cleared_workflows}. Your next message starts "
                "a fresh workflow. Existing GitHub branches, commits, and pull requests "
                "were not deleted.",
            )
            return

        # Compatibility cleanup for state written by older bot versions. A
        # stale reset flag must never intercept `yes` or `no` from another
        # active workflow.
        if state.pop("reset_confirmation_pending", None) is not None:
            await _persist_thread_state(thread_id, state)

        ticket_number, ticket_link = _extract_ticket(prompt)
        if ticket_link:
            state["ticket_link"] = ticket_link
            state["ticket_number"] = ticket_number

        pending_change_id = str(state.get("pending_change_id") or "").strip()
        workflow_stage = str(state.get("stage") or "").strip()
        workflow_thread_id = str(
            state.get("workflow_thread_id")
            or state.get("foundry_conversation_id")
            or ""
        ).strip()

        branch_match = BRANCH_RE.match(prompt.strip())
        if branch_match:
            from shared_code.terrabot_service import (
                GITHUB_AWS_REPO,
                GITHUB_AZURE_REPO,
                GITHUB_OWNER,
            )

            branch_name = branch_match.group(1)
            cloud = (branch_match.group(2) or "azure").lower()
            repo = GITHUB_AWS_REPO if cloud == "aws" else GITHUB_AZURE_REPO
            try:
                result = await asyncio.to_thread(
                    handle_teams_workspace_branch_request,
                    {
                        "owner": GITHUB_OWNER,
                        "repo": repo,
                        "branch": branch_name,
                        "base": "main",
                        "teams_requester": _get_teams_requester(activity),
                    },
                )
                state.update({
                    "branch": result.get("branch") or branch_name,
                    "branch_url": result.get("branch_url") or "",
                    "compare_url": result.get("compare_url") or "",
                })
                await _persist_thread_state(thread_id, state)
                await _send(
                    turn_context,
                    "\n".join([
                        str(result.get("reply") or "Branch created."),
                        "",
                        "**Branch**",
                        str(result.get("branch_url") or result.get("branch") or branch_name),
                        "",
                        "**Compare with main**",
                        str(result.get("compare_url") or ""),
                        "",
                        "**Check out this branch in your IDE**",
                        f"`{_format_checkout_command(result.get('branch') or branch_name)}`",
                    ]),
                )
            except Exception as exc:
                LOGGER.exception("GitHub branch creation failed", exc_info=exc)
                await _persist_thread_state(thread_id, state)
                await _send(turn_context, f"GitHub branch creation failed: {exc}")
            return

        # Stage-aware Teams state machine. Each reply is bound to exactly one
        # pending decision so a numeric target selection, branch yes/no, Jira
        # reply, or preview decision cannot be interpreted by another workflow.
        if workflow_stage == "awaiting_branch_reuse_decision":
            if _is_freeform_user_message(prompt):
                # A complete new instruction supersedes the older pending branch
                # request. Send it through the backend so repository/cloud scope
                # is recalculated from the current prompt. The backend preserves
                # existing branches/PRs and asks a new branch-choice question only
                # when the resolved repository actually has a reusable branch.
                await _send(turn_context, "Terrabot is processing your request...")
                request = {
                    "prompt": prompt,
                    "original_prompt": prompt,
                    "thread_id": workflow_thread_id,
                    "teams_conversation_id": thread_id,
                    "ticket_link": "",
                    "jira_ticket": "",
                    "source": "teams",
                    "supersede_pending_request": True,
                    "fresh_infra_generation": True,
                }
            else:
                if BRANCH_REUSE_DECISION_RE.match(normalized):
                    branch_choice = "reuse"
                elif BRANCH_NEW_DECISION_RE.match(normalized):
                    branch_choice = "new"
                else:
                    await _persist_thread_state(thread_id, state)
                    await _send(
                        turn_context,
                        "A branch choice is pending. Reply `yes` to reuse the current "
                        "branch, or `no` to create a new Terrabot branch from the latest "
                        "remote base branch.",
                    )
                    return

                await _send(turn_context, "Terrabot is processing your request...")
                request = {
                    "prompt": prompt,
                    "thread_id": workflow_thread_id,
                    "teams_conversation_id": thread_id,
                    "ticket_link": state.get("ticket_link", ticket_link),
                    "jira_ticket": state.get("ticket_number", ticket_number),
                    "source": "teams",
                    "mode": "infra",
                    "pending_branch_choice_reply": True,
                    "branch_choice": branch_choice,
                    # Explicitly propagate the branch decision flags so the
                    # commit function never falls back to the existing branch
                    # when the user chose "no" (new branch from base).
                    "reuse_branch": branch_choice == "reuse",
                    "force_new_branch": branch_choice == "new",
                    "existing_branch": state.get("branch", "") if branch_choice == "reuse" else "",
                }
        elif workflow_stage == "aws_module_selection":
            # AWS module-choice replies are protocol control, not new chat and
            # not generic Terraform target selection. Pin the request to AWS and
            # the existing Foundry workflow thread so the backend can consume
            # PENDING_AWS_MODULE_DISCOVERIES exactly once and invoke generation.
            await _send(turn_context, "Terrabot is processing your request...")
            request = {
                "prompt": prompt,
                "original_prompt": str(
                    state.get("pending_aws_module_selection_original_prompt")
                    or state.get("last_infra_prompt")
                    or ""
                ).strip(),
                "thread_id": str(
                    state.get("pending_aws_module_selection_thread_id")
                    or workflow_thread_id
                    or ""
                ).strip(),
                "teams_conversation_id": thread_id,
                "ticket_link": state.get("ticket_link", ticket_link),
                "jira_ticket": state.get("ticket_number", ticket_number),
                "source": "teams",
                "mode": "infra",
                "cloud": "aws",
                "requested_cloud": "aws",
                "pending_aws_module_selection_reply": True,
                "fresh_infra_generation": True,
                "pending_branch_choice_resolved": bool(
                    state.get("branch_choice_resolved_for_request")
                ),
                "branch_choice": str(state.get("resolved_branch_choice") or "").strip(),
                "reuse_branch": bool(state.get("resolved_reuse_branch")),
                "force_new_branch": bool(state.get("resolved_force_new_branch")),
                "existing_branch": str(state.get("resolved_existing_branch") or "").strip(),
            }
        elif workflow_stage == "infra_modification_target_selection":
            if _is_freeform_user_message(prompt) and not _is_infra_target_selection_reply(prompt):
                # A full instruction supersedes an abandoned target picker. The
                # backend clears only transient request state and performs fresh
                # live-GitHub discovery; branches and PRs remain untouched.
                await _send(turn_context, "Terrabot is processing your request...")
                request = {
                    "prompt": prompt,
                    "original_prompt": prompt,
                    "thread_id": workflow_thread_id,
                    "teams_conversation_id": thread_id,
                    "ticket_link": "",
                    "jira_ticket": "",
                    "source": "teams",
                    "supersede_pending_request": True,
                    "fresh_infra_generation": True,
                }
            else:
                # A target-picker reply continues the original request AFTER the
                # branch choice. Reuse the branch decision persisted by the
                # backend; never manufacture a fresh-branch choice here.
                await _send(turn_context, "Terrabot is processing your request...")
                branch_resolved = bool(state.get("branch_choice_resolved_for_request"))
                request = {
                    "prompt": prompt,
                    "original_prompt": str(
                        state.get("pending_target_selection_original_prompt")
                        or state.get("last_infra_prompt")
                        or ""
                    ).strip(),
                    "thread_id": str(
                        state.get("pending_target_selection_thread_id")
                        or workflow_thread_id
                        or ""
                    ).strip(),
                    "teams_conversation_id": thread_id,
                    "ticket_link": state.get("ticket_link", ticket_link),
                    "jira_ticket": state.get("ticket_number", ticket_number),
                    "source": "teams",
                    "mode": "infra",
                    "pending_target_selection_reply": True,
                    "pending_target_selection_thread_id": str(
                        state.get("pending_target_selection_thread_id")
                        or workflow_thread_id
                        or ""
                    ).strip(),
                    "fresh_infra_generation": True,
                    "pending_branch_choice_resolved": branch_resolved,
                    "branch_choice": str(state.get("resolved_branch_choice") or "").strip(),
                    "reuse_branch": bool(state.get("resolved_reuse_branch")) if branch_resolved else False,
                    "force_new_branch": bool(state.get("resolved_force_new_branch")) if branch_resolved else False,
                    "existing_branch": str(state.get("resolved_existing_branch") or "").strip() if branch_resolved else "",
                    "cloud": str(
                        state.get("pending_target_selection_cloud")
                        or state.get("resolved_branch_cloud")
                        or state.get("cloud")
                        or ""
                    ).strip(),
                    "requested_cloud": str(
                        state.get("pending_target_selection_cloud")
                        or state.get("resolved_branch_cloud")
                        or state.get("cloud")
                        or ""
                    ).strip(),
                }
        elif workflow_stage == "awaiting_jira":
            if ticket_link and pending_change_id:
                request = {
                    "action": "create_pr_from_branch",
                    "thread_id": workflow_thread_id,
                    "pending_change_id": pending_change_id,
                    "ticket_link": ticket_link,
                    "jira_ticket": ticket_number,
                    "ticket_title": state.get("ticket_title", ""),
                    "prompt": prompt,
                    "source": "teams",
                }
            elif pending_change_id and NEGATIVE_RE.match(normalized):
                request = {
                    "action": "discard_pending",
                    "thread_id": workflow_thread_id,
                    "pending_change_id": pending_change_id,
                    "ticket_link": state.get("ticket_link", ""),
                    "jira_ticket": state.get("ticket_number", ""),
                    "prompt": prompt,
                    "source": "teams",
                }
            elif _is_freeform_user_message(prompt):
                # A complete new infra instruction supersedes the old Jira
                # prompt. The backend clears only transient request state and
                # reconstructs repository context from live GitHub.
                await _send(turn_context, "Terrabot is processing your request...")
                request = {
                    "prompt": prompt,
                    "thread_id": workflow_thread_id,
                    "teams_conversation_id": thread_id,
                    "ticket_link": "",
                    "jira_ticket": "",
                    "source": "teams",
                }
            else:
                await _persist_thread_state(thread_id, state)
                await _send(
                    turn_context,
                    "A Jira ticket link is required before I open the pull request. "
                    "Send a link such as `https://<jira-host>/browse/STO-1234`, "
                    "or reply `no` to cancel the PR request.",
                )
                return
        elif workflow_stage == "awaiting_pr_decision" and pending_change_id:
            if ticket_link:
                request = {
                    "action": "create_pr_from_branch",
                    "thread_id": workflow_thread_id,
                    "pending_change_id": pending_change_id,
                    "ticket_link": ticket_link,
                    "jira_ticket": ticket_number,
                    "ticket_title": state.get("ticket_title", ""),
                    "prompt": prompt,
                    "source": "teams",
                }
            elif AFFIRMATIVE_RE.match(normalized) or PR_REQUEST_RE.match(prompt.strip()):
                state["stage"] = "awaiting_jira"
                await _persist_thread_state(thread_id, state)
                await _send(
                    turn_context,
                    "Send the Jira ticket link for this pull request, for example "
                    "`https://<jira-host>/browse/STO-1234`.",
                )
                return
            elif NEGATIVE_RE.match(normalized):
                request = {
                    "action": "discard_pending",
                    "thread_id": workflow_thread_id,
                    "pending_change_id": pending_change_id,
                    "ticket_link": state.get("ticket_link", ""),
                    "jira_ticket": state.get("ticket_number", ""),
                    "prompt": prompt,
                    "source": "teams",
                }
            else:
                # A new infrastructure instruction is allowed while a branch is
                # waiting for a PR decision. It remains in the same thread and
                # can add another commit to the existing Terrabot branch.
                await _send(turn_context, "Terrabot is processing your request...")
                request = {
                    "prompt": prompt,
                    "thread_id": workflow_thread_id,
                    "teams_conversation_id": thread_id,
                    "ticket_link": state.get("ticket_link", ticket_link),
                    "jira_ticket": state.get("ticket_number", ticket_number),
                    "source": "teams",
                }
        elif (
            pending_change_id
            and workflow_stage in {"awaiting_branch_commit", "awaiting_pr_confirmation", "infra_preview"}
            and AFFIRMATIVE_RE.match(normalized)
        ):
            # Legacy preview compatibility. Teams is branch-first, therefore a
            # preview approval commits to the branch instead of opening a PR.
            request = {
                "action": "commit_branch",
                "thread_id": workflow_thread_id,
                "pending_change_id": pending_change_id,
                "ticket_link": state.get("ticket_link", ""),
                "jira_ticket": state.get("ticket_number", ""),
                "prompt": prompt,
                "source": "teams",
            }
        elif (
            pending_change_id
            and workflow_stage in {"awaiting_branch_commit", "awaiting_pr_confirmation", "infra_preview"}
            and NEGATIVE_RE.match(normalized)
        ):
            request = {
                "action": "discard_pending",
                "thread_id": workflow_thread_id,
                "pending_change_id": pending_change_id,
                "ticket_link": state.get("ticket_link", ""),
                "jira_ticket": state.get("ticket_number", ""),
                "prompt": prompt,
                "source": "teams",
            }
        else:
            await _send(turn_context, "Terrabot is processing your request...")
            request = {
                "prompt": effective_prompt,
                "original_prompt": prompt,
                "thread_id": workflow_thread_id,
                "teams_conversation_id": thread_id,
                "ticket_link": state.get("ticket_link", ticket_link),
                "jira_ticket": state.get("ticket_number", ticket_number),
                "source": "teams",
            }
            # Do not classify semantic intent in the Teams transport. Ordinary
            # user language is sent to the backend/Foundry router unchanged.
            # Only deterministic protocol replies are handled locally.

        request["teams_conversation_id"] = thread_id
        request["memory_conversation_id"] = memory_conversation_id
        request["teams_requester"] = requester

        try:
            LOGGER.info(
                "Calling Teams Foundry router: action=%s foundry_thread_present=%s",
                request.get("action") or "chat",
                bool(request.get("thread_id")),
            )
            result, status_code = await asyncio.to_thread(
                handle_teams_chat_request,
                request,
            )
            LOGGER.info(
                "Teams Foundry router returned: status=%s ok=%s mode=%s "
                "foundry_thread_present=%s",
                status_code,
                result.get("ok"),
                result.get("mode"),
                bool(result.get("thread_id")),
            )
        except Exception as exc:
            LOGGER.exception("Terrabot backend failed for Teams", exc_info=exc)
            await _persist_thread_state(thread_id, state)
            await _send(
                turn_context,
                "Terrabot could not process the request because the backend failed. "
                "Check the Function App logs for details.",
            )
            return

        # The backend is the authoritative workflow-state writer. Reload its
        # durable snapshot before applying the response patch so this worker's
        # pre-request cache cannot resurrect a cleared pending flag or an older
        # stage. Only bot-local presentation history is carried forward.
        local_state_before_backend = dict(state)
        try:
            backend_state = await asyncio.to_thread(
                load_teams_conversation_state,
                thread_id,
            )
        except Exception:
            LOGGER.exception(
                "Unable to reload backend-owned Teams state: conversation=%s",
                thread_id,
            )
            backend_state = {}
        if isinstance(backend_state, dict) and backend_state:
            state = dict(backend_state)
            for local_key in ("recent_user_turns", "last_infra_prompt", "memory_conversation_id"):
                if local_state_before_backend.get(local_key) not in (None, "", []):
                    state[local_key] = local_state_before_backend[local_key]

        # Apply backend-owned durable state changes before the local stage
        # mapper runs. None is an explicit deletion directive.
        state_patch = result.get("state_patch")
        if isinstance(state_patch, dict):
            for key, value in state_patch.items():
                if value is None:
                    state.pop(str(key), None)
                else:
                    state[str(key)] = value

        # The backend returns the Foundry-created conversation id. Persist it
        # under a stable Teams conversation key before sending any response,
        # including 400 clarification responses such as module selection.
        returned_thread_id = str(result.get("thread_id") or "").strip()
        if returned_thread_id:
            state["workflow_thread_id"] = returned_thread_id
            state["foundry_conversation_id"] = returned_thread_id

        if result.get("pending_change_id"):
            state["pending_change_id"] = result["pending_change_id"]

        if result.get("decision_state"):
            state["stage"] = str(
                result.get("decision_state") or "awaiting_backend_reply"
            )

        if state.get("stage") == "aws_module_selection":
            state["pending_aws_module_selection_thread_id"] = str(
                result.get("thread_id")
                or state.get("workflow_thread_id")
                or workflow_thread_id
                or ""
            ).strip()
            state["pending_aws_module_selection_original_prompt"] = str(
                result.get("request_prompt")
                or request.get("original_prompt")
                or request.get("prompt")
                or state.get("last_infra_prompt")
                or ""
            ).strip()
            state["pending_aws_module_selection_cloud"] = "aws"

        if state.get("stage") == "infra_modification_target_selection":
            state["pending_target_selection_thread_id"] = str(
                result.get("thread_id")
                or state.get("workflow_thread_id")
                or workflow_thread_id
                or ""
            ).strip()
            state["pending_target_selection_original_prompt"] = str(
                result.get("request_prompt")
                or request.get("original_prompt")
                or state.get("last_infra_prompt")
                or ""
            ).strip()
            # Keep the provider bound to this picker even when the thread also
            # contains the other cloud's branch/PR state. Numeric replies have
            # no provider words of their own, so this field is the transport's
            # durable source of request-cloud continuity.
            state["pending_target_selection_cloud"] = str(
                result.get("cloud")
                or request.get("requested_cloud")
                or request.get("cloud")
                or state.get("resolved_branch_cloud")
                or state.get("cloud")
                or ""
            ).strip()

        mode = str(result.get("mode") or "").strip().lower()
        if mode not in {"chat", "clarification"} and request.get("prompt"):
            state["last_infra_prompt"] = str(request.get("original_prompt") or request.get("prompt") or "").strip()
        if mode == "infra_preview":
            state["stage"] = "awaiting_branch_commit"
        elif mode == "branch_created":
            state["stage"] = "awaiting_pr_decision"
            state["branch"] = result.get("branch")
            state["branch_url"] = result.get("branch_url")
            state["compare_url"] = result.get("compare_url")
            state["base_branch"] = result.get("base_branch")
        elif mode == "branch_choice_required":
            state["stage"] = "awaiting_branch_reuse_decision"
        elif mode == "jira_required":
            state["stage"] = "awaiting_jira"
        elif mode == "pr_created" or result.get("pr_url"):
            state["stage"] = "complete"
            state.pop("pending_change_id", None)
        elif request.get("action") == "discard_pending":
            state.pop("pending_change_id", None)
            state["stage"] = "idle"

        if state.get("stage") != "infra_modification_target_selection":
            state.pop("pending_target_selection_thread_id", None)
            state.pop("pending_target_selection_original_prompt", None)
            state.pop("pending_target_selection_cloud", None)

        if state.get("stage") != "aws_module_selection":
            state.pop("pending_aws_module_selection_thread_id", None)
            state.pop("pending_aws_module_selection_original_prompt", None)
            state.pop("pending_aws_module_selection_cloud", None)

        for key in (
            "ticket_link",
            "ticket_number",
            "ticket_title",
            "cloud",
            "workflow",
            "repo_target",
            "branch",
            "branch_url",
            "compare_url",
            "base_branch",
            "branch_reused",
            "created_new_branch",
            "create_pr_requested",
        ):
            if result.get(key) not in (None, ""):
                state[key] = result[key]

        # Extract pending_rule2_prompt from the RULE-2 card's invisible HTML
        # comment so the next name-reply turn knows a creation is expected.
        _rule2_match = re.search(r"<!--\s*rule2_prompt:(.*?)\s*-->",
                                  str(result.get("reply") or result.get("summary") or ""),
                                  re.DOTALL)
        if _rule2_match:
            state["pending_rule2_prompt"] = _rule2_match.group(1).strip()
            state["last_infra_prompt"] = _rule2_match.group(1).strip()

        # Persist before both success and clarification replies. This ordering
        # prevents a worker recycle between send_activity and the state write
        # from losing the user's active infrastructure selection.
        await _persist_thread_state(thread_id, state)

        if status_code >= 400 or not result.get("ok", True):
            await _send(turn_context, _format_reply(result))
            return

        await _send(turn_context, _format_reply(result))

        # A successfully raised PR closes the logical request conversation.
        # Keep its completed memory row intact, clear transient workflow state,
        # and immediately create a fresh memory row for the next user request.
        if mode == "pr_created" or result.get("pr_url"):
            completed_memory_id = str(
                state.get("memory_conversation_id") or memory_conversation_id
            ).strip()
            completed_workflow_thread = str(
                state.get("workflow_thread_id")
                or state.get("foundry_conversation_id")
                or workflow_thread_id
                or ""
            ).strip()
            try:
                await asyncio.to_thread(
                    reset_teams_chat_session,
                    thread_id,
                    completed_workflow_thread,
                )
            except Exception:
                LOGGER.exception(
                    "Unable to reset Teams workflow after PR creation: conversation=%s",
                    thread_id,
                )
            TEAMS_THREAD_STATE.pop(thread_id, None)
            teams_conversation_memory.clear(thread_id)
            await _rotate_memory_conversation(
                thread_id,
                requester,
                reason="pull_request_created",
                previous_conversation_id=completed_memory_id,
            )
            set_teams_short_follow_up(False)
            set_teams_conversation_context("")

    async def on_members_added_activity(self, members_added, turn_context: TurnContext):
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                await _send(
                    turn_context,
                    "Terrabot is ready. Send a message or mention me with an "
                    "infrastructure request.",
                )

async def send_automated_test_report(reference_payload: Dict[str, Any], text: str) -> None:
    """Post a queue-worker result back to the originating Teams conversation."""
    reference = ConversationReference().deserialize(reference_payload or {})
    app_id = _required_setting("MicrosoftAppId", "TEAMS_BOT_APP_ID")

    async def _callback(context: TurnContext) -> None:
        await context.send_activity(str(text or ""))

    # CloudAdapter proactive continuation uses the same bot identity as normal
    # Teams traffic. The queue worker calls this only after the original HTTP
    # invocation has already completed.
    await ADAPTER.continue_conversation(reference, _callback, app_id)


BOT = TerrabotTeamsBot()


async def handle_teams_bot_activity(
    body: Dict[str, Any],
    authorization_header: Optional[str],
) -> tuple[Dict[str, Any], int]:
    logging.warning("TEAMS-DIAG-1: entered handle_teams_bot_activity")

    if not isinstance(body, dict):
        logging.error("TEAMS-DIAG: body is not a dictionary")
        return {
            "ok": False,
            "reply": "Invalid Teams activity payload.",
        }, 400

    activity = Activity().deserialize(body)

    logging.warning(
        "TEAMS-DIAG-2: activity deserialized "
        "type=%s channel=%s service_url=%s conversation=%s auth_present=%s",
        activity.type,
        activity.channel_id,
        activity.service_url,
        getattr(activity.conversation, "id", ""),
        bool(authorization_header),
    )

    if not activity.type:
        return {
            "ok": False,
            "reply": "Teams activity type is missing.",
        }, 400

    if activity.type not in {
        ActivityTypes.message,
        ActivityTypes.conversation_update,
        ActivityTypes.invoke,
    }:
        logging.warning(
            "TEAMS-DIAG: ignored activity type=%s",
            activity.type,
        )
        return {}, 200

    try:
        logging.warning(
            "TEAMS-DIAG-3: calling CloudAdapter.process_activity"
        )

        invoke_response = await ADAPTER.process_activity(
            authorization_header or "",
            activity,
            BOT.on_turn,
        )

        logging.warning(
            "TEAMS-DIAG-7: CloudAdapter.process_activity completed"
        )

    except Exception as exc:
        logging.exception(
            "TEAMS-DIAG-ERROR: CloudAdapter.process_activity failed "
            "exception_type=%s exception=%s",
            type(exc).__name__,
            str(exc),
        )
        raise

    if invoke_response:
        return (
            invoke_response.body or {},
            invoke_response.status or 200,
        )

    return {}, 200