from __future__ import annotations
from typing import TYPE_CHECKING , Any, Optional 

if TYPE_CHECKING:
    from shared_code.terrabot_core_typing import (
        AFFIRMATIVE_REPLIES,
        AWS_MODULES_ROOT,
        GITHUB_OWNER,
        GITHUB_TOKEN,
        INFRA_MODIFICATION_WORKFLOWS,
        LOGGER,
        NEGATIVE_REPLIES,
        TEAMS_AWS_ENVIRONMENT_HINTS,
        TEAMS_AZURE_ENVIRONMENT_HINTS,
        THREAD_AUTO_ADVANCE_IN_PROGRESS,
        THREAD_METADATA,
        THREAD_PR_STATE,
        _ACTIVE_TEAMS_FLOW_CONTEXT,
        _TEAMS_AWS_ENVIRONMENT_TOKEN_RE,
        _TEAMS_FLAG_VALUES_BASENAME_PRIORITY,
        _TEAMS_MULTICLOUD_PREVIOUS_CALL_AGENT,
        _TEAMS_NEW_BRANCH_PREVIOUS_HANDLE_CHAT,
        _TEAMS_SIBLING_FLAG_LINE_RE,
        _TEAMS_WORKFLOW_STATE_PARTITION,
        _aws_created_module_paths_from_files,
        _aws_module_catalog_branch,
        _backend_existing_infra_context_is_selected,
        _build_agent_input_for_infra_safe,
        _build_backend_existing_infra_modification_context_teams_v2,
        _dedupe_preserving_order,
        _delete_chunked_teams_state,
        _extract_aws_module_source_refs_from_text,
        _extract_top_level_tf_blocks,
        _get_backend_existing_infra_context,
        _get_confirmed_aws_module_selection,
        _has_git_conflict_markers,
        _infer_generation_workflow_base,
        _matched_blocks_for_prompt,
        _remove_teams_mapping_entries_for_thread,
        _sanitize_aws_module_rel_path,
        _store_repository_context_from_resource_selection,
        _teams_all_hcl_assignment_spans,
        _teams_auto_accept_aws_module_creation,
        _teams_aws_discriminative_tokens,
        _teams_aws_extract_new_consumer_block,
        _teams_aws_match_has_resource_evidence,
        _teams_best_cloud_state,
        _teams_branch_choice_from_reply,
        _teams_chat_repo_targets,
        _teams_cloud_session,
        _teams_definition_root_evidence,
        _teams_diag_log,
        _teams_ensure_variables_tf_evidence,
        _teams_environment_folder_evidence,
        _teams_foundry_classify_request,
        _teams_is_multiline_map_value,
        _teams_locate_environment_value_files,
        _teams_map_entry_spans,
        _teams_message_is_protocol_control,
        _teams_module_source_literal,
        _teams_normalize_requested_identity,
        _teams_pending_state_mappings,
        _teams_remote_context_branch,
        _teams_resolve_pending_rescue_selection,
        _teams_safe_azure_scope_from_prompt,
        _teams_safe_extended_modification_terms,
        _teams_safe_normalized_phrase,
        _teams_safe_prompt_resource_name,
        _teams_safe_request_cloud,
        _teams_save_ui_state,
        _teams_selected_rescue_options,
        _teams_truthy,
        _validate_hcl_content_complete,
        agent_pr_context,
        build_aws_local_module_source,
        build_selected_infra_modification_context,
        clear_teams_conversation_state,
        cloud_root_dir,
        contextvars,
        detect_explicit_aws_environment,
        discover_live_aws_module_candidates,
        extract_json_from_text,
        get_pending_infra_modification_selection,
        github_base_branch_for_cloud,
        github_branch_exists,
        github_get_directory_listing,
        github_get_file_content,
        github_list_tf_files_recursive,
        github_repo_for_cloud,
        github_resolve_base_branch_for_cloud,
        infer_cloud_from_prompt,
        infer_new_aws_module_path,
        is_infra_modification_or_delete_prompt,
        is_valid_jira_ticket_link,
        json,
        load_teams_conversation_state,
        logging,
        normalize_aws_module_source_path,
        normalize_cloud,
        normalize_repo_target,
        normalize_tf_relative_path,
        normalize_yes_no_reply,
        os,
        persist_teams_workflow_state,
        re,
        recover_thread_pr_state,
        resolve_aws_environment_path,
        restore_teams_workflow_state,
        safe_normalize_cloud,
        select_infra_modification_candidate_from_reply,
        stable_thread_key,
        store_pending_infra_modification_selection,
    )

def _teams_clear_pending_generation_for_thread(thread_id: str) -> None:
    """Clear only transient generation state for a completed/abandoned request.

    Branch and pull-request history in THREAD_PR_STATE is intentionally kept.
    The durable workflow snapshot is then rewritten without stale selections,
    generated previews, or module-discovery confirmations.
    """
    thread = str(thread_id or "").strip()
    if not thread:
        return
    try:
        restore_teams_workflow_state(thread)
    except Exception:
        pass
    for mapping in _teams_pending_state_mappings().values():
        _remove_teams_mapping_entries_for_thread(mapping, thread)
    try:
        persist_teams_workflow_state(thread)
    except Exception as exc:
        LOGGER.warning(
            "Unable to persist cleared Teams pending workflow state for thread %s: %s",
            stable_thread_key(thread),
            exc,
        )


def _teams_prepare_pending_branch_choice_request(
    request_data: dict,
    state: dict,
    teams_conversation_id: str,
    prompt: str,
) -> tuple[dict, bool]:
    """Convert a yes/no branch reply back into the captured infra request.

    Returns ``(request_data, handled)``.  The state transition is completed
    here so older wrapper layers cannot reinterpret the literal word "no" as
    the generation prompt or recover stale pending module state.
    """
    stage = str(state.get("stage") or "").strip()
    if stage != "awaiting_branch_reuse_decision":
        return request_data, False

    choice = _teams_branch_choice_from_reply(prompt)
    if not choice:
        return request_data, False

    pending_prompt = str(state.get("pending_follow_up_prompt") or "").strip()
    if not pending_prompt:
        return request_data, False

    pending_cloud = safe_normalize_cloud(str(state.get("pending_follow_up_cloud") or "")) or ""
    cloud_state = _teams_best_cloud_state(state, pending_cloud) if pending_cloud else {}
    cloud_session = _teams_cloud_session(state, pending_cloud) if pending_cloud else {}
    previous_thread = str(
        cloud_state.get("thread_id")
        or cloud_session.get("thread_id")
        or state.get("workflow_thread_id")
        or state.get("foundry_conversation_id")
        or request_data.get("thread_id")
        or ""
    ).strip()

    # The pending prompt, not the literal yes/no answer, is the new generation
    # request.  Clear stale per-request state before invoking any older router.
    _teams_clear_pending_generation_for_thread(previous_thread)

    updated = dict(request_data or {})
    updated["prompt"] = pending_prompt
    updated["message"] = pending_prompt
    updated["fresh_infra_generation"] = True
    updated["pending_branch_choice_resolved"] = True
    updated["requested_cloud"] = pending_cloud

    if choice == "reuse":
        branch = str(
            state.get("pending_follow_up_branch")
            or cloud_state.get("branch")
            or cloud_session.get("branch")
            or ""
        ).strip()
        updated["reuse_branch"] = True
        updated["force_new_branch"] = False
        updated["existing_branch"] = branch
        # A distinct prompt gets a clean Foundry conversation even when the
        # target Git branch is reused.  Live branch contents carry prior code.
        updated["thread_id"] = ""
    else:
        updated["reuse_branch"] = False
        updated["force_new_branch"] = True
        updated["existing_branch"] = ""
        # Critical: do not reuse the previous Foundry thread when creating a
        # branch from latest main.  That thread may still remember old files.
        updated["thread_id"] = ""

    for source_key, target_key in (
        ("pending_follow_up_ticket_link", "ticket_link"),
        ("pending_follow_up_ticket_number", "jira_ticket"),
        ("pending_follow_up_ticket_title", "ticket_title"),
    ):
        value = state.get(source_key)
        if value and not updated.get(target_key):
            updated[target_key] = value

    # Move out of the branch-decision stage before delegating.  This prevents
    # earlier wrappers from performing a second branch-choice resolution and
    # replacing the restored prompt with stale state.
    patch = {
        "stage": "processing_new_infrastructure_request",
        "pending_follow_up_prompt": None,
        "pending_follow_up_cloud": None,
        "pending_follow_up_has_pr": None,
        "pending_follow_up_branch": None,
        "pending_follow_up_pr_url": None,
        "pending_follow_up_ticket_link": None,
        "pending_follow_up_ticket_number": None,
        "pending_follow_up_ticket_title": None,
        "workflow_thread_id": None,
        "foundry_conversation_id": None,
    }
    _teams_save_ui_state(teams_conversation_id, patch)
    updated["state_patch"] = patch
    return updated, True


def _handle_teams_chat_request_new_branch(data: dict):
    """Ensure branch choices execute the captured current request, never old files."""
    request_data = dict(data or {})
    prompt = str(request_data.get("prompt") or request_data.get("message") or "").strip()
    action = str(request_data.get("action") or "").strip().lower()
    teams_conversation_id = str(
        request_data.get("teams_conversation_id")
        or request_data.get("conversation_id")
        or ""
    ).strip()

    if not action and teams_conversation_id:
        state = load_teams_conversation_state(teams_conversation_id) or {}
        request_data, handled = _teams_prepare_pending_branch_choice_request(
            request_data,
            state,
            teams_conversation_id,
            prompt,
        )
        if handled:
            result, status_code = _TEAMS_NEW_BRANCH_PREVIOUS_HANDLE_CHAT(request_data)
            result = dict(result or {})
            # Make the resolution visible and auditable in Teams.
            resolved_prompt = str(request_data.get("prompt") or "").strip()
            branch_mode = "existing branch" if _teams_truthy(request_data.get("reuse_branch")) else "new branch from latest remote base"
            isolation_note = (
                f"Request isolation: generated only the pending request `{resolved_prompt}`. "
                f"Branch selection: {branch_mode}. Previous generated files and the prior Foundry conversation were not reused."
            )
            result["analysis"] = "\n".join(
                part for part in (
                    str(result.get("analysis") or "").strip(),
                    isolation_note,
                )
                if part
            )
            patch = dict(result.get("state_patch") or {})
            patch.update({
                "pending_follow_up_prompt": None,
                "pending_follow_up_cloud": None,
                "pending_follow_up_branch": None,
                "pending_follow_up_has_pr": None,
                "pending_follow_up_pr_url": None,
            })
            result["state_patch"] = patch
            _teams_save_ui_state(teams_conversation_id, patch)
            return result, status_code

    return _TEAMS_NEW_BRANCH_PREVIOUS_HANDLE_CHAT(request_data)

# =============================================================================
# Teams feature-state requests are agent-resolved.
# The backend supplies live repository evidence only; Foundry determines
# whether the request maps to a Boolean flag, resource attribute, list entry,
# or another repository-defined mechanism. No resource names or aliases are
# hardcoded here.

# =============================================================================
# Teams must apply the same repository-aware feature-flag rules as the VS Code
# workflow.  A disable/remove request for a bool-gated resource is an in-place
# change to the existing consumer flag, not a user clarification or a new
# module/resource generation request.

_TEAMS_FEATURE_FLAG_PREVIOUS_BUILD_INPUT = _build_agent_input_for_infra_safe
_TEAMS_FEATURE_FLAG_PREVIOUS_BUILD_MODIFICATION_CONTEXT = _build_backend_existing_infra_modification_context_teams_v2


def _build_backend_existing_infra_modification_context_stateless(
    prompt: str,
    thread_id: str,
    cloud: str,
    workflow: str,
    retrieved_value_context: list | None = None,
) -> dict:
    """Evidence-only pass-through; Foundry owns resource/flag interpretation."""
    return _TEAMS_FEATURE_FLAG_PREVIOUS_BUILD_MODIFICATION_CONTEXT(
        prompt,
        thread_id,
        cloud,
        workflow,
        retrieved_value_context=retrieved_value_context,
    )


def _build_agent_input_for_infra_stateless(
    prompt: str,
    thread_id: str,
    selected_cloud: Optional[str] = None,
    workflow: Optional[str] = None,
    retrieved_module_context: Optional[list] = None,
    retrieved_value_context: Optional[list] = None,
) -> str:
    """Tell Foundry it owns semantic targeting and Terraform generation."""
    raw = _TEAMS_FEATURE_FLAG_PREVIOUS_BUILD_INPUT(
        prompt,
        thread_id,
        selected_cloud=selected_cloud,
        workflow=workflow,
        retrieved_module_context=retrieved_module_context,
        retrieved_value_context=retrieved_value_context,
    )
    try:
        payload = json.loads(raw)
    except Exception:
        return raw
    instructions = list(payload.get("instructions") or [])
    instructions.extend([
        "FOUNDRY OWNS TERRAFORM GENERATION: the backend supplies live GitHub evidence only and does not choose flags/resources or synthesize HCL.",
        "For enable/disable requests, inspect the supplied repository code and infer the controlling repository-defined Boolean flag or equivalent mechanism from the Terraform itself. Never rely on backend aliases or hardcoded resource vocabulary.",
        "Only Boolean assignments whose CURRENT value can transition in the requested direction are candidates: disable => current true; enable => current false. Ignore unrelated non-Boolean parameters, data sources, resources, backend/provider files, and unrelated flags.",
        "If exactly one semantic flag/resource match exists, generate the full final file immediately and change only that target. If multiple genuine semantic matches remain, ask one numbered choice and describe each candidate from its enclosing Terraform block/module and nearby code.",
        "Do not ask the user to choose a file when repository semantics identify the controlling flag. Do not show files that contain no semantic match.",
        "All Terraform/HCL content must come from Foundry output. Backend validation/commit transport may reject invalid output but must never repair or generate Terraform on your behalf.",
    ])
    payload["instructions"] = instructions
    return json.dumps(payload, indent=2)

# =============================================================================
# Teams stateless live-GitHub request resolution and Azure workflow guard
# =============================================================================
# A complete Teams infrastructure instruction is self-contained. It must not
# depend on a previous Foundry conversation, a local VS Code workspace, or a
# process-local pending-selection dictionary. Live GitHub repository evidence
# is reloaded for the resolved cloud/environment on every such request.

_TEAMS_STATELESS_PREVIOUS_HANDLE_CHAT = _handle_teams_chat_request_new_branch

_TEAMS_SELF_CONTAINED_INFRA_ACTION_RE = re.compile(
    r"\b(create|add|provision|deploy|update|modify|change|set|enable|disable|"
    r"remove|delete|decommission|replace|refactor|fix|configure|increase|decrease|"
    r"attach|detach|migrate|move|rename|turn\s+on|turn\s+off|switch\s+on|switch\s+off)\b",
    re.IGNORECASE,
)

_TEAMS_STALE_DECISION_STAGES = {
    # A complete new infrastructure request must be able to supersede an old
    # PR/Jira flow. Without this, the lower durable-state router recovers the
    # old pending_change_id and returns jira_required before live repository
    # discovery can run for the new prompt.
    "awaiting_jira",
    "infra_modification_target_selection",
    "azure_module_branch_selection",
    "azure_module_repo_creation_confirmation",
    "azure_module_selection",
    "azure_consumer_value_selection",
    "azure_new_consumer_file_confirmation",
    "aws_module_selection",
    "aws_module_creation_confirmation",
    "module_variable_values",
    "awaiting_branch_commit",
    "awaiting_pr_confirmation",
    "infra_preview",
}


def _teams_is_self_contained_infra_request(prompt: str) -> bool:
    """Compatibility wrapper; semantic intent remains Foundry-owned."""
    text = str(prompt or "").strip()
    if not text:
        return False
    normalized = normalize_yes_no_reply(text)
    if normalized in AFFIRMATIVE_REPLIES or normalized in NEGATIVE_REPLIES:
        return False
    if re.fullmatch(r"\d+", normalized or "") or is_valid_jira_ticket_link(text):
        return False
    return _teams_foundry_classify_request(text) == "infra"


def _teams_reset_transient_state_for_new_request(
    teams_conversation_id: str,
    state: dict,
) -> dict:
    """Drop stale per-request decisions while preserving Git branch/PR history."""
    workflow_thread_id = str(
        state.get("workflow_thread_id")
        or state.get("foundry_conversation_id")
        or ""
    ).strip()
    if workflow_thread_id:
        _teams_clear_pending_generation_for_thread(workflow_thread_id)

    next_stage = "awaiting_pr_decision" if state.get("branch") else "idle"
    patch = {
        "stage": next_stage,
        "pending_change_id": None,
        "pending_follow_up_prompt": None,
        "pending_follow_up_cloud": None,
        "pending_follow_up_has_pr": None,
        "pending_follow_up_branch": None,
        "pending_follow_up_pr_url": None,
        "pending_follow_up_ticket_link": None,
        "pending_follow_up_ticket_number": None,
        "pending_follow_up_ticket_title": None,
        # Jira metadata belongs to the superseded request. Branch/PR history is
        # retained separately, but a new infrastructure request must not inherit
        # the previous request's ticket when the lower router reloads durable
        # Teams state.
        "ticket_link": None,
        "ticket_number": None,
        "ticket_title": None,
        "create_pr_requested": None,
        "selected_module": None,
        "selected_module_path": None,
        "selected_target_path": None,
        "decision_state": None,
    }
    if teams_conversation_id:
        _teams_save_ui_state(teams_conversation_id, patch)
    return patch


def _teams_structured_live_repo_failure(
    prompt: str,
    cloud: str,
    workflow: str,
    result: dict,
) -> tuple[dict, int]:
    """Replace module/path fallback leakage with one grounded blocking question."""
    repo_target = normalize_repo_target(cloud, workflow=workflow)
    repo = github_repo_for_cloud(cloud, repo_target=repo_target, workflow=workflow)
    original_analysis = str(result.get("analysis") or "").strip()
    analysis = "\n".join(filter(None, [
        original_analysis,
        f"Repository resolution: `{GITHUB_OWNER}/{repo}` ({repo_target}) from the current prompt.",
        "Context source: fresh live GitHub content obtained through the Teams GitHub App; prior Foundry/workspace context was not required.",
        "Target search: environment-scoped Terraform assignments, module blocks, variables, feature flags, and sibling patterns were evaluated before escalation.",
    ]))
    return {
        "ok": False,
        "mode": "clarification",
        "summary": "Terrabot could not identify one safe live-repository target after repository analysis.",
        "reply": (
            "Terrabot scanned the resolved live GitHub repository but could not materialize a single safe Terraform change. "
            "No repository path is required from you. Check the diagnostic details below and retry after the repository scan issue is resolved."
        ),
        "analysis": analysis,
        "source_paths_used": result.get("source_paths_used") or [],
        "files": [],
        "questions": [
            "Confirm only the feature or resource name if it differs from the name in your request; repository paths and flag names do not need to be supplied."
        ],
        "cloud": cloud,
        "workflow": workflow,
        "repo_target": repo_target,
        "request_prompt": prompt,
        "diagnostic_code": "TEAMS_LIVE_REPO_TARGET_UNRESOLVED",
        "suppressed_azure_module_discovery": True,
        "thread_id": result.get("thread_id") or "",
        "state_patch": result.get("state_patch") or {},
    }, 400


def _handle_teams_chat_request_stateless(data: dict):
    """Resolve every complete Teams infra prompt from prompt + live GitHub state."""
    request_data = dict(data or {})
    prompt = str(request_data.get("prompt") or request_data.get("message") or "").strip()
    action = str(request_data.get("action") or "").strip().lower()
    teams_conversation_id = str(
        request_data.get("teams_conversation_id")
        or request_data.get("conversation_id")
        or ""
    ).strip()

    # A numeric/path reply to the Terraform target picker is a continuation of
    # the same infrastructure request. It must not be reclassified as a new
    # follow-up request and sent through the branch reuse/new-branch prompt.
    # The original request began before target disambiguation, so complete it
    # on a fresh branch from the latest remote base after the target is chosen.
    workflow_thread_id = str(request_data.get("thread_id") or "").strip()
    pending_target_selection = (
        get_pending_infra_modification_selection(workflow_thread_id, "")
        if workflow_thread_id and not action
        else {}
    )
    target_selection_continuation = bool(
        pending_target_selection
        and select_infra_modification_candidate_from_reply(
            prompt,
            pending_target_selection,
        ) is not None
    )
    if target_selection_continuation:
        # Target selection happens AFTER the branch choice. Preserve the branch
        # decision captured for this request instead of silently forcing a new
        # branch. This is critical when AWS and Azure maintain parallel branch
        # histories in the same Teams conversation.
        ui_state = load_teams_conversation_state(teams_conversation_id) if teams_conversation_id else {}
        branch_resolved = _teams_truthy(ui_state.get("branch_choice_resolved_for_request"))
        request_data["pending_branch_choice_resolved"] = branch_resolved
        request_data["pending_target_selection_resolved"] = True
        if branch_resolved:
            request_data["reuse_branch"] = _teams_truthy(ui_state.get("resolved_reuse_branch"))
            request_data["force_new_branch"] = _teams_truthy(ui_state.get("resolved_force_new_branch"))
            request_data["existing_branch"] = str(ui_state.get("resolved_existing_branch") or "").strip()
            request_data["branch_choice"] = str(ui_state.get("resolved_branch_choice") or "").strip()
            request_data["cloud"] = str(
                ui_state.get("resolved_branch_cloud")
                or pending_target_selection.get("cloud")
                or request_data.get("cloud")
                or ""
            ).strip()

    self_contained = not action and str(request_data.get("mode") or "").strip().lower() == "infra" and not target_selection_continuation
    inferred_cloud = _teams_safe_request_cloud(prompt) if self_contained else ""
    inferred_workflow = (
        infer_generation_workflow(prompt, inferred_cloud)
        if self_contained and inferred_cloud
        else ""
    )

    reset_patch: dict = {}
    if self_contained and inferred_cloud and inferred_workflow:
        state = load_teams_conversation_state(teams_conversation_id) if teams_conversation_id else {}
        stage = str(state.get("stage") or "").strip()
        pending_prompt = str(state.get("pending_follow_up_prompt") or "").strip()

        # A full new request supersedes stale module/file/value questions. It
        # does not delete branches or pull requests, which remain available to
        # the normal same-branch/new-branch decision workflow.
        if stage in _TEAMS_STALE_DECISION_STAGES or (
            stage == "awaiting_branch_reuse_decision"
            and pending_prompt
            and normalize_yes_no_reply(pending_prompt) != normalize_yes_no_reply(prompt)
        ):
            reset_patch = _teams_reset_transient_state_for_new_request(
                teams_conversation_id,
                state,
            )
            request_data["state_patch"] = reset_patch
            # Keep the Foundry conversation for the same user/thread. Only
            # transient workflow decisions are cleared; conversational memory
            # must remain available for follow-up interpretation.

        request_data["mode"] = "infra"
        request_data["cloud"] = inferred_cloud
        request_data["workflow"] = inferred_workflow
        request_data["requested_cloud"] = inferred_cloud
        request_data["fresh_infra_generation"] = True
        request_data["stateless_live_github_resolution"] = True

    result, status_code = _TEAMS_STATELESS_PREVIOUS_HANDLE_CHAT(request_data)
    result = dict(result or {})
    if reset_patch:
        combined_patch = dict(reset_patch)
        combined_patch.update(dict(result.get("state_patch") or {}))
        result["state_patch"] = combined_patch

    if self_contained and inferred_cloud and inferred_workflow:
        result.setdefault("request_prompt", prompt)
        result.setdefault("cloud", inferred_cloud)
        result.setdefault("workflow", inferred_workflow)
        result.setdefault(
            "repo_target",
            normalize_repo_target(inferred_cloud, workflow=inferred_workflow),
        )
        analysis_note = (
            "Stateless request resolution: inferred the cloud/environment from the current prompt and read the target repository from live GitHub using GitHub App authentication; no prior chat or local workspace context was required."
        )
        result["analysis"] = "\n".join(filter(None, [
            str(result.get("analysis") or "").strip(),
            analysis_note,
        ]))

        visible_text = " ".join(
            str(result.get(key) or "")
            for key in ("reply", "summary")
        ).lower()
        leaked_module_fallback = (
            "approved azure module repo in vena_repos" in visible_text
            or "create a new azure module repo first" in visible_text
        )
        leaked_path_fallback = (
            "include the exact resource/module/policy name or target file path" in visible_text
            or "provide the exact file path" in visible_text
            or "provide path to" in visible_text
            or "which exact file" in visible_text
            or "which existing" in visible_text and "module" in visible_text
            or "need more context" in visible_text
            or "need a bit more detail" in visible_text
            or "quick clarifying question" in visible_text
        )
        if leaked_module_fallback or leaked_path_fallback:
            # AWS creation must never expose a repository-placement/source
            # clarification after branch choice. Re-run backend-owned live
            # module discovery; if the requested module is truly absent, enter
            # the existing Teams auto-create + auto-commit path directly.
            if inferred_cloud == "aws":
                environment_path, environment_error = resolve_aws_environment_path(
                    prompt,
                    retrieved_value_context=[],
                    current_environment_path=None,
                )
                if not environment_error and environment_path:
                    try:
                        discovery = discover_live_aws_module_candidates(
                            prompt,
                            environment_path=environment_path,
                        )
                    except Exception as discovery_error:
                        LOGGER.exception(
                            "Teams AWS fallback recovery discovery failed",
                            exc_info=discovery_error,
                        )
                        discovery = {}

                    if str(discovery.get("status") or "").strip().lower() == "not_found":
                        proposed_module_path = infer_new_aws_module_path(prompt, discovery)
                        recovery_preview = {
                            "ok": False,
                            "mode": "clarification",
                            "reply": "Verified AWS module absence; continuing automatic module creation.",
                            "thread_id": result.get("thread_id") or request_data.get("thread_id") or "",
                            "request_prompt": prompt,
                            "ticket_number": result.get("ticket_number") or request_data.get("jira_ticket") or "",
                            "jira_ticket": result.get("jira_ticket") or request_data.get("jira_ticket") or "",
                            "ticket_link": result.get("ticket_link") or request_data.get("ticket_link") or "",
                            "ticket_title": result.get("ticket_title") or request_data.get("ticket_title") or "",
                            "decision_state": "aws_module_creation_confirmation",
                            "router": {
                                "request_type": "infra",
                                "cloud": "aws",
                                "workflow": "aws_module_creation_confirmation",
                                "reason": "Backend verified no matching AWS module; Teams auto-creation required.",
                            },
                            "aws_module_discovery": discovery,
                            "environment_path": environment_path,
                            "proposed_module_path": proposed_module_path,
                            "state_patch": result.get("state_patch") or {},
                        }
                        recovered, recovered_status = _teams_auto_accept_aws_module_creation(
                            request_data,
                            recovery_preview,
                            400,
                        )
                        if isinstance(recovered, dict) and (
                            recovered_status < 400 or recovered.get("reply")
                        ):
                            return recovered, recovered_status

            return _teams_structured_live_repo_failure(
                prompt,
                inferred_cloud,
                inferred_workflow,
                result,
            )

    return result, status_code


# =============================================================================
# Teams existing-invocation-first generation
# =============================================================================
# Teams creation requests must first reuse a proven consumer/invocation pattern
# in the target repository. External module-repository discovery remains
# available only when the user explicitly asks to create/populate a module repo.

_TEAMS_INVOCATION_PREVIOUS_INFER_WORKFLOW = _infer_generation_workflow_base
_TEAMS_INVOCATION_PREVIOUS_BUILD_MODIFICATION_CONTEXT = _build_backend_existing_infra_modification_context_stateless
_TEAMS_INVOCATION_PREVIOUS_BUILD_AGENT_INPUT = _build_agent_input_for_infra_stateless

_TEAMS_INVOCATION_CREATION_RE = re.compile(
    r"\b(create|add|provision|deploy|build|make)\b", re.IGNORECASE
)
_TEAMS_EXPLICIT_MODULE_REPO_RE = re.compile(
    r"\b(create|add|populate|build)\b.{0,50}\b(module\s+repo(?:sitory)?|new\s+repo(?:sitory)?|terraform-github|vena_repos)\b",
    re.IGNORECASE,
)


def _teams_invocation_resource_aliases(prompt: str) -> list[str]:
    text = str(prompt or "").lower()
    aliases: list[str] = []
    groups = {
        "aca": [
            "aca", "azure container app", "azure container apps", "container app",
            "container apps", "azurerm_container_app", "aca_app",
        ],
        "cloudamqp": ["cloudamqp", "cloud amqp", "rabbitmq", "rabbit mq"],
        "s3": ["s3", "bucket", "aws_s3_bucket", "s3_bucket"],
        "ec2": ["ec2", "instance", "aws_instance", "ec2_instance"],
        "aks": ["aks", "azure kubernetes", "azurerm_kubernetes_cluster"],
        "storage": ["storage account", "azurerm_storage_account", "storage_account"],
        "keyvault": ["key vault", "keyvault", "azurerm_key_vault"],
        "servicebus": ["service bus", "servicebus", "azurerm_servicebus"],
        "function": ["function app", "function_app", "azurerm_linux_function_app"],
    }
    for canonical, values in groups.items():
        if any(value in text for value in values):
            aliases.extend([canonical, *values])

    # Capture a non-sensitive requested instance name, e.g. homepage-bff.
    for match in re.finditer(
        r"\b(?:named?|name\s+is|called)\s+[\"']?([a-z0-9][a-z0-9_-]{1,63})",
        text,
        re.IGNORECASE,
    ):
        aliases.append(match.group(1).lower())

    return _dedupe_preserving_order(
        [
            re.sub(r"[^a-z0-9_\-]+", " ", value.lower()).strip()
            for value in aliases
            if str(value or "").strip()
        ]
    )

_TEAMS_PATH_QUESTION_RE = re.compile(
    r"(?:provide|open|point\s+me|paste|share|attach|upload|confirm|specify|"
    r"tell\s+me|indicate|which|surface[sd]?|include[sd]?|supply|supplied|"
    r"available)"
    r"[^.\n]{0,120}(?:file|path|tfvars|values)"
    r"|exact\s+(?:path|values\s+file)"
    r"|once\s+the\s+backend\s+includes",
    re.IGNORECASE,
)


def _teams_commit_side_flag_guarantee_stage1(
    safe_files: list,
    patch_details: list,
    prompt: str,
    context: dict,
    cloud: str,
    repo_target,
    workflow,
    source_branch: str,
) -> None:
    """COMMIT-SIDE RULE-1 guarantee, evaluated against the SAME ref the
    commit writes to (source_branch). If the files being committed wire a
    new var.<name>_enabled flag and neither they nor source_branch itself
    enable it, append the values-file change here. Mutates safe_files /
    patch_details in place; logs every decision; never raises."""
    try:
        name = _teams_requested_resource_name(prompt)
        if not name:
            logging.info("Teams commit flag guarantee: skipped (no resource name)")
            return
        name_pattern = re.escape(name.replace("-", "_"))
        blob = "\n".join(
            str(item.get("content") or "") for item in safe_files if isinstance(item, dict)
        )
        wiring = re.search(
            rf"var\.((?:[a-z0-9]+_)*{name_pattern}(?:_[a-z0-9]+)*_enabled)\b", blob
        )
        flag_name = wiring.group(1) if wiring else ""

        merged = _teams_collect_backend_env_context(context.get("retrieved_value_context") or [])
        values_path = _teams_pick_flag_values_file(merged)
        if not values_path:
            try:
                entries, paths, resolver_debug = _teams_locate_environment_value_files(
                    prompt, cloud, repo_target, workflow, source_branch
                )
                merged["environment_files"].extend(
                    entry for entry in entries if isinstance(entry, dict)
                )
                merged["companion_write_paths"].extend(
                    path for path in paths if path not in merged["companion_write_paths"]
                )
                logging.info("Teams commit flag guarantee: live locator resolver=%s", resolver_debug)
            except Exception:
                logging.exception("Teams commit flag guarantee: locator failed")
            values_path = _teams_pick_flag_values_file(merged)
        if not values_path:
            logging.info("Teams commit flag guarantee: no values file resolvable for %s", flag_name)
            return

        for item in safe_files:
            if isinstance(item, dict) and str(item.get("filename") or "").strip().strip("/") == values_path:
                logging.info("Teams commit flag guarantee: %s already in commit set", values_path)
                return

        live = github_get_file_content(
            cloud, values_path, source_branch, repo_target=repo_target, workflow=workflow
        ) or ""
        live = str(live).replace("\r\n", "\n")
        if not flag_name:
            flag_name = _teams_infer_requested_enable_flag_from_values(prompt, live)
            if not flag_name:
                logging.info(
                    "Teams commit flag guarantee: skipped (no requested-name wiring and no live sibling flag family for %s)",
                    name,
                )
                return
        if re.search(rf"(?m)^[ \t]*{re.escape(flag_name)}[ \t]*=[ \t]*true\b", blob):
            logging.info("Teams commit flag guarantee: %s already enabled in committed files", flag_name)
            return
        flag_line = re.search(
            rf"(?m)^([ \t]*){re.escape(flag_name)}[ \t]*=[ \t]*(true|false)[ \t]*$", live
        )
        if flag_line and flag_line.group(2) == "true":
            logging.info(
                "Teams commit flag guarantee: %s already true on %s", flag_name, source_branch
            )
            return
        if flag_line:
            final = (
                live[: flag_line.start()]
                + f"{flag_line.group(1)}{flag_name} = true"
                + live[flag_line.end():]
            )
            note = "flipped to true"
        else:
            siblings = list(_TEAMS_SIBLING_FLAG_LINE_RE.finditer(live))
            if siblings:
                last = siblings[-1]
                final = (
                    live[: last.end()]
                    + f"\n{last.group(1)}{flag_name} = true"
                    + live[last.end():]
                )
            else:
                final = live.rstrip("\n") + f"\n{flag_name} = true\n"
            note = "added beside sibling flags"

        safe_files.append({
            "filename": values_path,
            "content": final,
            "operation": "modify",
            # Flipping an existing false assignment is an intentional
            # in-place edit; adding a missing flag remains additive.
            "in_place": bool(flag_line),
        })
        patch_details.append({
            "path": values_path,
            "kind": "flag_enable_commit_guarantee",
            "applied": [f"{flag_name} = true"],
            "ignored_generated": [],
            "note": f"commit-side RULE 1 guarantee ({note}) against {source_branch}",
        })
        logging.info(
            "Teams commit flag guarantee: %s = true in %s (%s) on %s",
            flag_name, values_path, note, source_branch,
        )
    except Exception:
        logging.exception("Teams commit flag guarantee: skipped on error")
_teams_commit_side_flag_guarantee = _teams_commit_side_flag_guarantee_stage1

def _teams_collect_backend_env_context(retrieved_value_context: list | None) -> dict:
    """Merge every backend_existing_infra_code_match item in
    retrieved_value_context into one view. Multi-turn flows accumulate
    several context items; relying on 'selected or first' loses the one
    carrying environment_files/invocation flags."""
    merged: dict = {
        "environment_files": [],
        "companion_write_paths": [],
        "invocation": False,
        "cloud": "",
        "repo_target": "",
        "workflow": "",
        "context_ref": "",
        "selected_path": "",
    }
    seen_paths: set[str] = set()
    for item in retrieved_value_context or []:
        if not isinstance(item, dict):
            continue
        if item.get("source") != "backend_existing_infra_code_match":
            continue
        if item.get("invocation_generation") or item.get("operation") == "existing_invocation_creation":
            merged["invocation"] = True
        for entry in item.get("environment_files") or []:
            if isinstance(entry, dict) and entry.get("path") and entry["path"] not in seen_paths:
                seen_paths.add(entry["path"])
                merged["environment_files"].append(entry)
        for path in item.get("companion_write_paths") or []:
            if path and path not in merged["companion_write_paths"]:
                merged["companion_write_paths"].append(path)
        for key in ("cloud", "repo_target", "workflow", "context_ref", "selected_path"):
            if not merged[key] and item.get(key):
                merged[key] = str(item.get(key))
    return merged

def _teams_pick_flag_values_file(ctx: dict) -> str:
    """Choose the environment values file that holds the feature flags.
    Priority: hub.tfvars, tier.tfvars, common.tfvars (the repo's known flag
    files, common being shared across environments), then whichever tfvars
    in evidence holds the most sibling *_enabled assignments."""
    entries = [entry for entry in (ctx.get("environment_files") or []) if isinstance(entry, dict)]
    for wanted in _TEAMS_FLAG_VALUES_BASENAME_PRIORITY:
        for entry in entries:
            path = str(entry.get("path") or "")
            if path.rsplit("/", 1)[-1].lower() != wanted:
                continue
            if _TEAMS_SIBLING_FLAG_LINE_RE.search(str(entry.get("content") or "")):
                return path
    best_path, best_hits = "", 0
    for entry in entries:
        path = str(entry.get("path") or "")
        if not path.endswith((".tfvars", ".tfvars.json")):
            continue
        hits = len(_TEAMS_SIBLING_FLAG_LINE_RE.findall(str(entry.get("content") or "")))
        if hits > best_hits:
            best_path, best_hits = path, hits
    if best_path:
        return best_path
    # Last resort: a priority-named companion path even without cached content.
    for wanted in _TEAMS_FLAG_VALUES_BASENAME_PRIORITY:
        for path in ctx.get("companion_write_paths") or []:
            if str(path).rsplit("/", 1)[-1].lower() == wanted:
                return str(path)
    return ""


def _teams_infer_requested_enable_flag_from_values(prompt: str, live_values: str) -> str:
    """Infer the requested resource's enable flag from sibling flag families.

    This is used only for create/add/provision/deploy requests when the model
    omitted or retained a stale sibling var.<name>_enabled reference. The
    requested resource name comes from the user prompt; the flag prefix comes
    only from live target-environment tfvars evidence.
    """
    phrase = _teams_safe_normalized_phrase(prompt)
    if not re.search(r"\b(?:create|add|provision|deploy)\b", phrase):
        return ""
    requested = _teams_requested_resource_name(prompt)
    if not requested:
        return ""
    requested_norm = _teams_normalize_requested_identity(requested)
    flags = [
        match.group(1)
        for match in re.finditer(
            r'(?m)^\s*([A-Za-z_][A-Za-z0-9_]*_enabled)\s*=\s*(?:true|false)\s*$',
            str(live_values or ""),
        )
    ]
    if not flags:
        return ""

    alias_prefixes: list[str] = []
    for alias in _teams_invocation_resource_aliases(prompt):
        normalized = re.sub(r"[^a-z0-9]+", "_", str(alias or "").lower()).strip("_")
        if normalized and normalized not in alias_prefixes:
            alias_prefixes.append(normalized)
    alias_prefixes.sort(key=len, reverse=True)

    for prefix in alias_prefixes:
        sibling_hits = [name for name in flags if name.startswith(prefix + "_")]
        if sibling_hits:
            return f"{prefix}_{requested_norm}_enabled"
    return ""


def _teams_ensure_flag_enable_in_env_values_stage1(
    agent_result: dict,
    prompt: str,
    retrieved_value_context: list | None,
    cloud: str,
    workflow: str,
) -> dict:
    """RULE 1 completion guarantee: when a creation wires a new
    var.<name>_enabled flag but no returned file enables it, the backend
    appends `<flag> = true` to the environment's values file itself —
    scanning hub.tfvars / tier.tfvars / common.tfvars and the sibling
    *_enabled definitions. Never asks; never blocks the run (best-effort
    with full logging)."""
    try:
        if not isinstance(agent_result, dict):
            return agent_result
        if (agent_result.get("workflow") or "").strip() not in INFRA_MODIFICATION_WORKFLOWS:
            return agent_result
        name = _teams_requested_resource_name(prompt)
        if not name:
            logging.info("Teams flag-enable completion: skipped (no resource name in prompt)")
            return agent_result
        name_pattern = re.escape(name.replace("-", "_"))

        files = [item for item in (agent_result.get("files") or []) if isinstance(item, dict)]
        returned_blob = "\n".join(str(item.get("content") or "") for item in files)
        wiring = re.search(
            rf"var\.((?:[a-z0-9]+_)*{name_pattern}(?:_[a-z0-9]+)*_enabled)\b",
            returned_blob,
        )
        flag_name = wiring.group(1) if wiring else ""

        # A matching returned var.<requested>_enabled reference is strong proof,
        # flag-gated creation — merge ALL backend contexts instead of
        # trusting whichever item 'selected or first' happens to return.
        merged = _teams_collect_backend_env_context(retrieved_value_context)
        effective_cloud = merged["cloud"] or cloud
        effective_repo_target = merged["repo_target"] or None
        effective_workflow_value = merged["workflow"] or workflow
        branch = merged["context_ref"].strip() or github_base_branch_for_cloud(
            effective_cloud,
            repo_target=effective_repo_target,
            workflow=effective_workflow_value,
        )

        values_path = _teams_pick_flag_values_file(merged)
        if not values_path:
            # Self-sufficiency: resolve the environment's value files live
            # (the v10 repo-wide locator) instead of giving up.
            try:
                located_entries, located_paths, located_debug = _teams_locate_environment_value_files(
                    prompt, effective_cloud, effective_repo_target, effective_workflow_value, branch
                )
                merged["environment_files"].extend(
                    entry for entry in located_entries if isinstance(entry, dict)
                )
                merged["companion_write_paths"].extend(
                    path for path in located_paths if path not in merged["companion_write_paths"]
                )
                logging.info("Teams flag-enable completion: live locator ran resolver=%s", located_debug)
            except Exception:
                logging.exception("Teams flag-enable completion: live locator failed")
            values_path = _teams_pick_flag_values_file(merged)
        if not values_path:
            logging.info("Teams flag-enable completion: no values file resolvable for %s", flag_name)
            return agent_result
        for item in retrieved_value_context or []:
            if isinstance(item, dict) and item.get("source") == "backend_existing_infra_code_match":
                companions = list(item.get("companion_write_paths") or [])
                if values_path not in companions:
                    companions.append(values_path)
                    item["companion_write_paths"] = companions

        live = github_get_file_content(
            effective_cloud,
            values_path,
            branch,
            repo_target=effective_repo_target,
            workflow=effective_workflow_value,
        ) or ""
        live = str(live).replace("\r\n", "\n")

        if not flag_name:
            flag_name = _teams_infer_requested_enable_flag_from_values(prompt, live)
            if not flag_name:
                logging.info(
                    "Teams flag-enable completion: skipped (no requested-name wiring and no live sibling flag family for %s)",
                    name,
                )
                return agent_result

        enabled_re = re.compile(rf"(?m)^[ \t]*{re.escape(flag_name)}[ \t]*=[ \t]*true\b")
        if any(enabled_re.search(str(item.get("content") or "")) for item in files):
            logging.info("Teams flag-enable completion: agent already enabled %s", flag_name)
            return agent_result

        if re.search(rf"(?m)^[ \t]*{re.escape(flag_name)}[ \t]*=", live):
            flipped = re.sub(
                rf"(?m)^([ \t]*){re.escape(flag_name)}[ \t]*=[ \t]*false[ \t]*$",
                rf"\g<1>{flag_name} = true",
                live,
            )
            if flipped == live:
                return agent_result  # already true in the live file
            final = flipped
            note = f"set `{flag_name} = true`"
        else:
            siblings = list(_TEAMS_SIBLING_FLAG_LINE_RE.finditer(live))
            if siblings:
                last = siblings[-1]
                final = (
                    live[: last.end()]
                    + f"\n{last.group(1)}{flag_name} = true"
                    + live[last.end():]
                )
            else:
                final = live.rstrip("\n") + f"\n{flag_name} = true\n"
            note = f"added `{flag_name} = true`"

        for item in files:
            item_path = str(item.get("filename") or item.get("path") or "").strip().strip("/")
            if item_path == values_path:
                item["content"] = final
                break
        else:
            agent_result.setdefault("files", []).append({
                "filename": values_path,
                "path": values_path,
                "content": final,
                "operation": "modify",
                "in_place": True,
                "source_paths_used": [values_path],
            })

        agent_result["summary"] = (
            str(agent_result.get("summary") or "").rstrip(". ")
            + f". Backend {note} in {values_path} to enable the new app per the environment flag pattern."
        )
        if agent_result.get("analysis") is not None:
            agent_result["analysis"] = (
                str(agent_result.get("analysis") or "").rstrip()
                + f"\nFlag file: {values_path} — backend-deterministic {note}; placed beside the sibling *_enabled flags."
            )
        source_paths = list(agent_result.get("source_paths_used") or [])
        if values_path not in source_paths:
            source_paths.append(values_path)
            agent_result["source_paths_used"] = source_paths
        logging.info(
            "Teams flag-enable completion: flag=%s file=%s (%s)",
            flag_name, values_path, note,
        )
        return agent_result
    except Exception:
        logging.exception("Teams flag-enable completion skipped")
        return agent_result
_teams_ensure_flag_enable_in_env_values = _teams_ensure_flag_enable_in_env_values_stage1
    
def _teams_is_path_request_question_stage1(text: str) -> bool:
    return bool(_TEAMS_PATH_QUESTION_RE.search(str(text or "")))
_teams_is_path_request_question = _teams_is_path_request_question_stage1


_TEAMS_NAME_STOPWORDS = {"is", "a", "an", "the", "it", "as", "be", "of", "to"}


def _teams_requested_resource_name(prompt: str) -> str:
    """Extract the explicit resource name. Longest alternatives first so
    'whose name is homepage-bff' captures 'homepage-bff', never 'is'."""
    text = str(prompt or "").lower()
    for pattern in (
        r"\bwhose\s+name\s+is\s+[\"']?([a-z0-9][a-z0-9_-]{1,63})",
        r"\bname\s+is\s+[\"']?([a-z0-9][a-z0-9_-]{1,63})",
        r"\bnamed\s+[\"']?([a-z0-9][a-z0-9_-]{1,63})",
        r"\bcalled\s+[\"']?([a-z0-9][a-z0-9_-]{1,63})",
        r"\bname\s+[\"']?([a-z0-9][a-z0-9_-]{1,63})",
    ):
        match = re.search(pattern, text)
        if match and match.group(1) not in _TEAMS_NAME_STOPWORDS:
            return match.group(1)
    return ""


def _teams_backend_rule2_reply(prompt: str, retrieved_value_context: list | None) -> str | None:
    """RULE 2 answered by the BACKEND: when the evidence proves the requested
    resource's enable flag is already true, return the modify-or-new-name
    question directly — never relay an agent request for file paths."""
    if not _teams_is_existing_invocation_creation(prompt):
        return None
    ctx = _get_backend_existing_infra_context(retrieved_value_context or [])
    name = _teams_requested_resource_name(prompt)
    if not isinstance(ctx, dict) or not name:
        return None
    name_us = name.replace("-", "_")
    # Segment-boundary match: the name must appear as complete underscore
    # segment(s) inside the flag (aca_app_homepage_bff_enabled), so
    # substrings can never match (prov**is**ioner vs 'is').
    flag_re = re.compile(
        rf"\b((?:[a-z0-9]+_)*{re.escape(name_us)}(?:_[a-z0-9]+)*_enabled)\b\s*=\s*true",
        re.IGNORECASE,
    )
    # Merge ALL backend contexts — avoid the single-ctx "selected or first"
    # trap that matched main-branch content when the target is a new branch.
    all_env_files: list[dict] = []
    all_matched: list[dict] = []
    seen_paths: set[str] = set()
    for item in retrieved_value_context or []:
        if not isinstance(item, dict) or item.get("source") != "backend_existing_infra_code_match":
            continue
        for entry in item.get("environment_files") or []:
            if isinstance(entry, dict) and entry.get("path") not in seen_paths:
                seen_paths.add(entry.get("path"))
                all_env_files.append(entry)
        for matched in item.get("matched_files") or []:
            if isinstance(matched, dict):
                all_matched.append(matched)
    sources: list[dict] = all_env_files
    for matched in all_matched:
        sources.append(matched)
    for entry in sources:
        content = str((entry or {}).get("content") or "")
        found = flag_re.search(content)
        if found:
            path = str((entry or {}).get("path") or "")
            return (
                f"**{name} already exists and is enabled** — `{found.group(1)} = true` in `{path}`.\n\n"
                f"- Reply `modify <your change>` (for example `modify cpu to 0.5`) to update the existing app's configuration.\n"
                f"- Or reply with a new app name (for example `{name}-2` or `{name}-web`) to create a new instance — "
                "Terrabot will add the new definition alongside the existing apps and enable its flag in the environment values file.\n\n"
                f"**Terrabot's analysis** Backend verified the enable flag in the live environment evidence (`{path}`); no file input is needed from you."
                f"\n\n<!-- rule2_prompt:{prompt} -->"
            )
    return None


def _teams_flagless_creation_corrective(prompt: str, retrieved_value_context: list | None) -> str | None:
    """Built when deterministic flag materialization found no boolean
    enable/disable flag anywhere in evidence for this resource family.

    Not every resource is flag-gated — plenty of repos just add a new
    sibling module/resource block to a per-resource-family file (e.g. a new
    module block in storage_accounts.tf) with no accompanying boolean flag
    at all. The old fallback treated "no flag found" as "ask the user for
    the flag name", which is wrong whenever the resource simply isn't
    flag-gated in this repo. This corrective tells the agent to fall back
    to an ordinary additive creation instead of asking anything."""
    ctx = _get_backend_existing_infra_context(retrieved_value_context or [])
    files = [
        str((entry or {}).get("path") or "")
        for entry in (ctx.get("environment_files") or [])
        if (entry or {}).get("path")
    ] if isinstance(ctx, dict) else []
    matched = [
        str((entry or {}).get("path") or "")
        for entry in (ctx.get("matched_files") or [])
        if isinstance(ctx, dict) and (entry or {}).get("path")
    ]
    all_paths = list(dict.fromkeys([*matched, *files]))
    if not all_paths:
        return None
    listed = ", ".join(all_paths[:12])
    return (
        "CORRECTION: no boolean create_*/enable_*/*_enabled flag exists anywhere "
        "in the supplied evidence for this resource. That means this resource "
        "family is NOT flag-gated in this repository — do not ask about a flag, "
        "and do not ask for a file, path, or any other context. The live evidence "
        "already contains everything needed: " + listed + ". "
        "Scan those files for the existing resource-family definition (the file "
        "that already contains sibling resources/module blocks of the same type "
        "as the one requested, e.g. other storage account modules for a storage "
        "account request) and generate the change as a normal additive creation: "
        "append one new sibling block to that definition file, copying the "
        "nearest existing block's structure, wiring, and formatting exactly "
        "(CONSUMER PATTERN CONFORMANCE). If the nearest sibling is object-backed "
        "(its inputs read var.<object_root>.*), ALWAYS materialize the exact three-file "
        "pattern in one response: definition file + existing variables.tf + target "
        "environment tfvars. Derive a NEW dedicated object root from the new module "
        "label, clone the nearest sibling variable declaration shape under that root, "
        "and clone the nearest sibling's concrete tfvars object values under that root. "
        "Do not ask which sibling/replication family to use; choose the nearest sibling "
        "in the selected resource-family file. If this repo stores concrete values in a "
        "separate tfvars/values file, also add the matching values entry there, "
        "mirroring exactly how the nearest existing sibling instance's values are "
        "declared. Return the complete existing file(s) plus only the new "
        "block/entry, per the APPEND CONTRACT. Return the strict JSON envelope "
        "with files[] populated — returning empty files[] or a question here is a "
        "contract violation; every fact needed to generate this change is already "
        "in the evidence you were given."
    )


def _teams_azure_object_backed_no_question_corrective(
    prompt: str,
    retrieved_value_context: list | None,
) -> str | None:
    """Force ordinary Azure object-backed creation to self-resolve repo choices.

    This is a Teams-only corrective used after Foundry asks non-blocking questions
    for a creation whose live evidence already contains the resource-family file,
    variables.tf, and the target environment values file. The repository pattern,
    not the user, chooses the sibling schema and concrete defaults.
    """
    ctx = _get_backend_existing_infra_context(retrieved_value_context or [])
    if not isinstance(ctx, dict):
        return None

    selected_path = str(
        ctx.get("selected_path")
        or ((ctx.get("matched_file_paths") or [""])[0])
        or ""
    ).strip()
    env_files = [
        str((entry or {}).get("path") or "").strip()
        for entry in (ctx.get("environment_files") or [])
        if isinstance(entry, dict) and str((entry or {}).get("path") or "").strip()
    ]
    variable_paths = [path for path in env_files if path.endswith("variables.tf")]
    tfvars_paths = [path for path in env_files if path.endswith(".tfvars")]
    if not selected_path:
        return None

    requested_name = _teams_requested_resource_name(prompt)
    target_hint = requested_name or "the requested new instance"
    evidence_text = ", ".join(list(dict.fromkeys([selected_path, *variable_paths, *tfvars_paths]))[:12])
    return (
        "CORRECTION: this Azure creation is fully repo-answerable. Do not ask the "
        "user to choose an object root, sibling, replication family, module pattern, "
        "Terraform file, tfvars file, or non-sensitive values. Generate now from the "
        "nearest existing sibling in the live target environment. "
        f"Target instance: {target_hint}. Evidence: {evidence_text}. "
        "For an object-backed resource family, the response MUST contain the complete "
        "three-file write-set in this same response: (1) append the new sibling module "
        "invocation to the backend-selected resource-family definition file and wire "
        "every object-backed input to a NEW dedicated var.<object_root>.* derived from "
        "the new module label; (2) append a variable declaration for that exact object "
        "root to the existing variables.tf, cloning the nearest sibling variable's "
        "type shape exactly; (3) append a concrete object assignment for that exact "
        "root to the TARGET ENVIRONMENT'S own tfvars file, cloning the nearest sibling "
        "object's concrete values and applying only explicit user overrides. Never use "
        "__FILL__ placeholders for this object-backed creation. Never reuse an existing "
        "sibling variable root. If multiple sibling variants exist, choose the nearest "
        "sibling in the selected definition file and clone its schema/values; this is a "
        "repository decision, not a user question. Return JSON with files[] populated "
        "and questions=[]; do not return prose or a clarification."
    )


def _teams_path_question_corrective(retrieved_value_context: list | None) -> str | None:
    ctx = _get_backend_existing_infra_context(retrieved_value_context or [])
    files = [
        str((entry or {}).get("path") or "")
        for entry in (ctx.get("environment_files") or [])
        if (entry or {}).get("path")
    ] if isinstance(ctx, dict) else []
    if not files:
        return None
    listed = ", ".join(files[:12])
    return (
        "CORRECTION: do not ask for any file or path. The context_pack's "
        "environment_files ALREADY contains the full live contents of: "
        + listed
        + ". Apply the MANDATORY CREATION/DISABLE PROCEDURE now using those "
        "files and return the strict JSON envelope with files[] (or the "
        "single RULE 2 modify-or-new-name question if the resource is "
        "already enabled). Asking for a path again is a contract violation."
    )


def _teams_supplied_files_diagnostic(retrieved_value_context: list | None) -> str:
    ctx = _get_backend_existing_infra_context(retrieved_value_context or [])
    files = [
        str((entry or {}).get("path") or "")
        for entry in (ctx.get("environment_files") or [])
        if (entry or {}).get("path")
    ] if isinstance(ctx, dict) else []
    if files:
        return (
            "Terrabot supplied these live environment files as evidence: "
            + ", ".join(f"`{path}`" for path in files[:12])
            + ", but could not find an existing pattern (a flag or a "
            "resource-family definition file with a comparable sibling block) "
            "to model this change on. Name the exact resource type or file this "
            "should follow and Terrabot will apply it."
        )
    # Do not convert a missing generic context wrapper into a false
    # "environment not found" user error. AWS environment placement is backend
    # deterministic; the generation/recovery path should re-read the exact
    # dev_aws/prod_aws folder instead. This diagnostic is retained only for a
    # genuine live GitHub read failure.
    env_path = ""
    for item in retrieved_value_context or []:
        if isinstance(item, dict):
            candidate = str(item.get("environment_path") or "").strip()
            if candidate.startswith(("terraform/dev_aws/", "terraform/prod_aws/")):
                env_path = candidate
                break
    if env_path:
        return (
            f"Terrabot resolved the AWS environment to `{env_path}`, but the live "
            "GitHub read returned no usable Terraform files for that exact folder. "
            "The backend will retry the exact environment scope instead of asking "
            "for a repository path."
        )
    return (
        "Terrabot could not read the resolved environment from the live repository. "
        "The backend environment resolver did not produce a usable target folder."
    )

def _teams_intercept_agent_questions(agent_reply: str) -> str | None:
    """Detect a genuinely blocking question *or* an accidental permission/plan reply.

    Teams infrastructure generation must never leak a Foundry planning paragraph
    such as "please confirm", "if you approve", or "should I proceed" to the
    end user.  Returning that prose from this helper lets the existing backend
    corrective path re-run generation against the already supplied live GitHub
    evidence.  JSON question envelopes are still supported for the one legitimate
    already-exists / ambiguity cases.
    """
    raw = str(agent_reply or "").strip()
    try:
        data = extract_json_from_text(raw)
    except Exception:
        data = None

    if isinstance(data, dict):
        if data.get("files"):
            return None
        questions = [
            str(item).strip()
            for item in (data.get("questions") or [])
            if str(item).strip()
        ]
        summary = str(data.get("summary") or "").strip()
        if not questions and not summary:
            return None
        # Teams clarifications are deliberately compact.  Do not expose the
        # agent's analysis/planning narrative to the user.
        if questions:
            return "\n".join([summary, questions[0]]).strip()
        return summary

    # Foundry occasionally ignores the JSON contract and returns a natural-
    # language plan that ends by requesting approval. Treat that as a failed
    # generation attempt, not as chat.  The caller will immediately retry with
    # the repository-grounded no-question corrective.
    lower = re.sub(r"\s+", " ", raw.lower()).strip()
    permission_markers = (
        "please confirm",
        "if you confirm",
        "if you approve",
        "if you approve,",
        "once you confirm",
        "once approved",
        "do you want me to proceed",
        "would you like me to proceed",
        "should i proceed",
        "reply yes to proceed",
        "reply `yes` to proceed",
        "before i proceed",
        "before proceeding",
        "to proceed, i need",
        "if you want me to proceed",
        "plan i intend to execute",
        "i would also",
        "i would generate",
        "i will return a single json payload",
    )
    if raw and any(marker in lower for marker in permission_markers):
        return raw
    return None

def _teams_apply_agent_identity(agent_reply: str, cloud: str, workflow: str) -> str:
    """The Foundry instruction set intentionally omits top-level cloud/
    workflow keys (transport identity is backend routing, not agent intent).
    Inject the backend-resolved identity into the agent's JSON envelope so
    the shared parser accepts it — Teams flow only; never overrides values
    the agent did supply; non-JSON (chat) replies pass through unchanged."""
    try:
        data = extract_json_from_text(agent_reply)
    except Exception:
        return agent_reply
    if not isinstance(data, dict):
        return agent_reply
    updated = False
    normalized_cloud = safe_normalize_cloud(cloud or "")
    if not str(data.get("cloud") or "").strip() and normalized_cloud:
        data["cloud"] = normalized_cloud
        updated = True
    if not str(data.get("workflow") or "").strip() and str(workflow or "").strip():
        data["workflow"] = str(workflow).strip()
        updated = True
    if not updated:
        return agent_reply
    try:
        return json.dumps(data)
    except Exception:
        return agent_reply

_TEAMS_CONVERSATION_CONTEXT: contextvars.ContextVar[str] = contextvars.ContextVar(
    "terrabot_teams_conversation_context", default=""
)


def set_teams_conversation_context(block: str) -> None:
    """Called by the Teams bot before each request with the bounded chat
    transcript (or "" to clear). Auxiliary context only — GitHub evidence
    remains authoritative; see teams_conversation_memory.get_context_block."""
    _TEAMS_CONVERSATION_CONTEXT.set(str(block or ""))   

_TEAMS_SHORT_FOLLOW_UP: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "terrabot_teams_short_follow_up", default=False
)


def set_teams_short_follow_up(value: bool) -> None:
    """Teams bot marks replies that are short contextual follow-ups (a bare
    new name, an environment word). For those, a single backend-discovered
    candidate is auto-confirmed instead of re-asking the selection card."""
    _TEAMS_SHORT_FOLLOW_UP.set(bool(value))

def _teams_is_existing_invocation_creation(prompt: str) -> bool:
    text = str(prompt or "").strip()
    if not text or not _TEAMS_INVOCATION_CREATION_RE.search(text):
        return False
    if is_infra_modification_or_delete_prompt(text):
        return False
    if _TEAMS_EXPLICIT_MODULE_REPO_RE.search(text):
        return False
    return bool(_teams_invocation_resource_aliases(text))


def infer_generation_workflow(prompt: str, target_cloud: str, requested_workflow: Optional[str] = None) -> str:
    """Route Azure creation to existing invocations; keep AWS module discovery authoritative."""
    requested = str(requested_workflow or "").strip()
    if requested:
        return requested
    cloud = safe_normalize_cloud(target_cloud)

    # AWS creation must always enter the tf-devops module-discovery workflow
    # first. Routing ordinary AWS create/add prompts to aws_infra_modification
    # sets allow_existing_update_without_new_module=True later in the request
    # pipeline, which suppresses the verified module-not-found -> new-module
    # path. That is the regression that can turn "create an EC2 instance in
    # minidev" into an edit of terraform/dev_aws/minidev/variables.tf only.
    # The base workflow already routes AWS create requests to
    # aws_module_consumer, where live terraform/modules discovery decides
    # between consumer-only generation and module + consumer generation.
    if cloud == "aws":
        return _TEAMS_INVOCATION_PREVIOUS_INFER_WORKFLOW(
            prompt, target_cloud, requested_workflow
        )

    # Preserve the existing Azure invocation-first behavior, including the ACA
    # nested/object-backed creation fixes.
    if cloud == "azure" and _teams_is_existing_invocation_creation(prompt):
        return "azure_infra_modification"

    return _TEAMS_INVOCATION_PREVIOUS_INFER_WORKFLOW(prompt, target_cloud, requested_workflow)


def _teams_invocation_scope(prompt: str, cloud: str, branch: str) -> str:
    normalized_cloud = safe_normalize_cloud(cloud)
    if normalized_cloud == "aws":
        try:
            path, _question = detect_explicit_aws_environment(prompt)
            return str(path or "").strip().strip("/")
        except Exception:
            return ""
    if normalized_cloud == "azure":
        try:
            path, _reason = _teams_safe_azure_scope_from_prompt(prompt, branch)
            return str(path or "").strip().strip("/")
        except Exception:
            return ""
    return ""


def _teams_invocation_file_score(path: str, content: str, prompt: str, scope_root: str) -> int:
    aliases = _teams_invocation_resource_aliases(prompt)
    lower_path = str(path or "").lower()
    lower_content = str(content or "").lower()
    filename = lower_path.rsplit("/", 1)[-1]
    score = 0

    if re.search(r"(?m)^\s*module\s+\"[^\"]+\"\s*\{", content or ""):
        score += 120
    for alias in aliases:
        compact = alias.replace(" ", "_").replace("-", "_")
        words = {alias, compact, compact.replace("_", "-")}
        for word in words:
            if not word:
                continue
            if word in filename:
                score += 500
            if word in lower_path:
                score += 120
            if word in lower_content:
                score += 80
    if "source" in lower_content and "module" in lower_content:
        score += 40
    if scope_root and lower_path.startswith(scope_root.lower().rstrip("/") + "/"):
        score += 100
    # Prefer established resource-family files such as aca.tf over generic files.
    if filename in {"main.tf", "variables.tf", "outputs.tf", "versions.tf", "provider.tf", "backend.tf"}:
        score -= 80
    return score


def _teams_discover_invocation_candidates(
    prompt: str,
    cloud: str,
    workflow: str,
    base_context: dict,
) -> list[dict]:
    repo_target = base_context.get("repo_target") or normalize_repo_target(cloud, workflow=workflow)
    branch = base_context.get("context_ref") or github_base_branch_for_cloud(
        cloud, repo_target=repo_target, workflow=workflow
    )
    scope_root = _teams_invocation_scope(prompt, cloud, branch)
    candidates: dict[str, dict] = {}

    for item in base_context.get("matched_files") or []:
        if isinstance(item, dict) and item.get("path") and item.get("content"):
            candidates[str(item["path"])] = dict(item)

    # Search the complete target repository because shared invocation files such
    # as aca.tf may live at the Terraform root while environment values live in
    # vars/<environment>. The chosen file must still prove the resource pattern.
    root_path = cloud_root_dir(cloud, repo_target=repo_target, workflow=workflow) or "."
    try:
        paths = github_list_tf_files_recursive(
            cloud=cloud,
            root_path=root_path,
            branch=branch,
            repo_target=repo_target,
            workflow=workflow,
        )
    except Exception:
        paths = []

    for path in paths or []:
        path = str(path or "").strip().strip("/")
        if not path.endswith(".tf"):
            continue
        try:
            content = github_get_file_content(
                cloud, path, branch, repo_target=repo_target, workflow=workflow
            )
        except Exception:
            content = None
        if not content:
            continue
        score = _teams_invocation_file_score(path, content, prompt, scope_root)
        if score <= 0:
            continue
        candidates[path] = {
            "path": path,
            "filename": path.rsplit("/", 1)[-1],
            "content": content,
            "matched_blocks": _matched_blocks_for_prompt(
                content, _teams_invocation_resource_aliases(prompt)
            ),
            "reason": "live GitHub existing invocation pattern",
            "score": score,
        }

    ranked = sorted(
        candidates.values(),
        key=lambda item: (
            -int(item.get("score") or _teams_invocation_file_score(
                item.get("path") or "", item.get("content") or "", prompt, scope_root
            )),
            item.get("path") or "",
        ),
    )
    return ranked

def _teams_invocation_workflow_analysis(
    repo_full_name: str,
    scope_root: str,
    selected_path: str,
    selected_content: str,
) -> str:
    """Backend-inferred workflow summary for the selection card — shows HOW
    the repo defines this resource family so failures are debuggable."""
    lines = [f"Repository: `{repo_full_name}`; evidence read from live GitHub."]
    if scope_root:
        lines.append(f"Environment scope: `{scope_root}` (all its .tf/.tfvars files are attached as evidence after selection).")
    filename = selected_path.rsplit("/", 1)[-1]
    content = str(selected_content or "")
    locals_match = re.search(r"locals\s*\{\s*([A-Za-z0-9_]+)\s*=\s*\{", content)
    if locals_match:
        lines.append(
            f"Inferred pattern: instances are defined inline in `{filename}` as entries of `locals.{locals_match.group(1)}`."
        )
    else:
        lines.append(f"Inferred pattern: instances are defined inline in `{filename}` alongside existing siblings.")
    flag_vars = sorted(set(re.findall(r"var\.([A-Za-z0-9_]*_enabled)", content)))[:4]
    if flag_vars:
        flags = ", ".join(f"`{name}`" for name in flag_vars)
        lines.append(
            f"Inferred flag mechanism: instances are gated by variables like {flags}, assigned in the environment's tfvars value files — the agent reads those files and sets the new flag itself."
        )
    lines.append("Safety: the selected file plus the scope's value files are the only write targets; all existing lines are preserved.")
    return "\n".join(lines)

def _teams_selected_invocation_context(
    base_context: dict,
    selected: dict,
    prompt: str,
    cloud: str,
    workflow: str,
) -> dict:
    path = str(selected.get("path") or "").strip().strip("/")
    content = str(selected.get("content") or "")
    aliases = _teams_invocation_resource_aliases(prompt)
    context = {
        # Uses the modification-context source so the selected-target checks
        # (_get_backend_existing_infra_context, enforce_modification_uses_
        # backend_matched_files) recognize it. invocation_generation=True is
        # the tag that distinguishes creation-by-append from a true
        # modification throughout the pipeline.
        "source": "backend_existing_infra_code_match",
        "operation": "existing_invocation_creation",
        # Present the discovered file as a candidate the user confirms first;
        # generation runs on the option-number reply via the standard
        # pending-selection flow.
        "selection_state": "candidate_selection_required",
        "cloud": safe_normalize_cloud(cloud),
        "repo_target": base_context.get("repo_target") or normalize_repo_target(cloud, workflow=workflow),
        "workflow": workflow,
        "repo_full_name": base_context.get("repo_full_name") or "",
        "context_ref": base_context.get("context_ref") or "",
        "scope_root": base_context.get("scope_root") or "",
        "scope_reason": base_context.get("scope_reason") or "",
        "search_terms": aliases,
        "selected_path": path,
        "matched_files": [{
            "path": path,
            "filename": path.rsplit("/", 1)[-1],
            "content": content,
            "matched_blocks": selected.get("matched_blocks") or _matched_blocks_for_prompt(content, aliases),
            "reason": "backend-selected existing invocation pattern",
            "selected_by_backend": True,
        }],
        "matched_file_paths": [path],
        "invocation_generation": True,
        "instructions": [
            "Backend selected the existing Terraform invocation file that demonstrates the requested resource pattern.",
            "Do not ask the user to confirm the repository, module source, file path, invocation style, or defaults.",
            "Add one new sibling invocation in this same file, following the nearest existing block byte-for-byte for source style, expressions, ordering, comments, and formatting.",
            "Use explicit prompt values first, then values from the nearest existing invocation, then declared defaults. Use __FILL__ tokens only for unresolved non-sensitive preferences.",
            "Do not access terraform-github, vena_repos, or another module repository for this request. The existing invocation is sufficient evidence for the consumer contract.",
            "Preserve every existing invocation and unrelated line. Return the complete final selected file for the Teams GitHub writer.",
            "AZURE OBJECT-BACKED THREE-FILE CONTRACT (HARD): when the nearest sibling invocation is backed by var.<object> fields, the definition file may contain only the repository-style module invocation wired to a NEW dedicated object root for this instance. Do not put __FILL__ tokens or environment-specific concrete values into that module block.",
            "In the SAME response, append a variable declaration for that dedicated object to the existing variables.tf by cloning the nearest sibling variable's exact type/optional/nesting shape, and append a concrete object assignment to the target environment's own hub.tfvars/tier.tfvars/common.tfvars file where that resource family's sibling values already live. Do not add a description, default, validation, nullable, or sensitive attribute unless the sibling declaration contains it.",
            "Clone the sibling object's concrete field values into the new tfvars object; never reference the sibling object, never reuse its variable root, and never split the three files across later turns.",
            "Before returning, self-check that the module root, variable declaration name, and tfvars assignment name are identical; that the new object has the sibling field shape; that all existing lines remain unchanged; and that Terraform formatting/brace balance is valid.",
            "MANDATORY CREATION/DISABLE PROCEDURE — follow these rules in this exact order, no manual intervention: RULE 1 (resource name does NOT exist): add the definition in the existing file that holds the similar resources (copy the nearest sibling's naming convention, wiring, and structure exactly). THEN check whether this resource family uses a boolean flag mechanism anywhere in the evidence (create_*/enable_*/*_enabled in the environment value files or sibling environments) — if it does, also enable it via that flag system and return the tfvars file with the new flag set true. If NO such flag exists anywhere in the evidence for this resource family, the definition-file append IS the whole change — do not invent a flag, do not ask about a flag, and do not ask for any file or path; every fact needed is already in the supplied evidence. When the repo stores concrete values separately (a tfvars/values file), still add the matching values entry there even when no flag is involved, mirroring the nearest existing sibling instance's values exactly. RULE 2 (resource with that name DOES exist — enabled): return empty files[] with ONE question offering (a) modify/update the existing resource's configuration, or (b) create the resource under another name (suggest one matching repo naming style); on 'modify' run the modification workflow, on a new name run RULE 1 with that name. If the definition exists but its flag is absent/false, the creation IS the flag change: return only the tfvars edit, no duplicate definition, no question. RULE 3 (disable request): find the existing flag inside the environment's value files and set it to false — nothing else. Never ask for a tfvars path or file contents; every environment value file is supplied in environment_files, and if none matched, say so plainly instead of asking.",
            "NEW FLAG DECLARATIONS ARE APPENDS: when RULE 1 introduces a new <name>_enabled flag, its variable declaration is APPENDED to the existing variables file that already declares the sibling *_enabled variables (that file is in the evidence and in companion_write_paths). NEVER create a new .tf file when the siblings live in existing files — new-file output for this pattern is rejected by the backend. The complete write set for a flag-gated creation is exactly: the definition file (new sibling entry), the existing variables file (new variable declaration appended), and the environment values file (flag = true).",
            "FLAG FILE DISCOVERY (MANDATORY, BOTH FILES ALWAYS): environment feature flags live in the environment folder's values files — hub.tfvars first, then tier.tfvars, then common.tfvars (shared across environments), all read from live GitHub into environment_files. A creation response that returns only the definition file is INCOMPLETE: every creation MUST return the values file too, with the new <name>_enabled = true placed beside the sibling *_enabled assignments in their exact format. Never ask where to set a flag. The backend independently verifies the flag against the actual commit branch and enables it there if the generation omitted it — but a definition-only response is still a contract violation.",
            "NEVER ASK PERMISSION for the flag step: when the definition exists and the flag is absent or false, generate the flag change immediately —\"Proceed to enable ...?\" style questions are forbidden; the only legal exists-question is the RULE-2 modify-or-new-name choice when the flag is already true.",
            "Never ask the user for a tfvars path or file contents: environment_files contains the scope's live .tf/.tfvars files and companion_write_paths lists the value files you may write.",
        ],
        "analysis": _teams_invocation_workflow_analysis(
            repo_full_name=base_context.get("repo_full_name") or "",
            scope_root=base_context.get("scope_root") or "",
            selected_path=path,
            selected_content=content,
        ),
    }
    # Auto-selected short-follow-up runs skip the redundant card, so this
    # context must carry the SAME evidence the resume path builds.
    branch_ref = str(base_context.get("context_ref") or "").strip() or github_base_branch_for_cloud(
        context["cloud"], repo_target=context["repo_target"], workflow=workflow
    )
    evidence_entries: list[dict] = []
    companion_paths: list[str] = []
    seen_paths: set[str] = set()
    for loader in (
        lambda: _teams_locate_environment_value_files(prompt, context["cloud"], context["repo_target"], workflow, branch_ref)[:2],
        lambda: _teams_environment_folder_evidence(prompt, context["cloud"], context["repo_target"], workflow, branch_ref)[:2],
        lambda: _teams_definition_root_evidence(context["cloud"], context["repo_target"], workflow, branch_ref, path),
    ):
        try:
            entries, write_paths = loader()
        except Exception:
            continue
        for entry in entries:
            if entry.get("path") and entry["path"] not in seen_paths:
                seen_paths.add(entry["path"])
                evidence_entries.append(entry)
        for write_path in write_paths:
            if write_path and write_path not in companion_paths:
                companion_paths.append(write_path)
    if evidence_entries:
        context["environment_files"] = evidence_entries
    if companion_paths:
        context["companion_write_paths"] = companion_paths
    if _TEAMS_SHORT_FOLLOW_UP.get():
        context["selection_state"] = "selected"
    return context


def build_backend_existing_infra_modification_context_stage1(
    prompt: str,
    thread_id: str,
    cloud: str,
    workflow: str,
    retrieved_value_context: list | None = None,
) -> dict:
    """Auto-select a proven invocation file for ordinary create/add requests."""
    context = _TEAMS_INVOCATION_PREVIOUS_BUILD_MODIFICATION_CONTEXT(
        prompt,
        thread_id,
        cloud,
        workflow,
        retrieved_value_context=retrieved_value_context,
    )
    active = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    if not active.get("active") or not _teams_is_existing_invocation_creation(prompt):
        return context

    candidates = _teams_discover_invocation_candidates(prompt, cloud, workflow, context)
    if not candidates:
        return context

    # The highest-scoring established resource-family file is authoritative.
    # A tie is resolved deterministically by path; users are not asked to choose
    # repository structure that the backend can inspect itself.
    return _teams_selected_invocation_context(
        context,
        candidates[0],
        prompt,
        cloud,
        workflow,
    )
build_backend_existing_infra_modification_context = build_backend_existing_infra_modification_context_stage1


def build_agent_input_for_infra(
    prompt: str,
    thread_id: str,
    selected_cloud: Optional[str] = None,
    workflow: Optional[str] = None,
    retrieved_module_context: Optional[list] = None,
    retrieved_value_context: Optional[list] = None,
) -> str:
    retrieved_value_context = _teams_ensure_variables_tf_evidence(selected_cloud, retrieved_value_context)
    raw = _TEAMS_INVOCATION_PREVIOUS_BUILD_AGENT_INPUT(
        prompt,
        thread_id,
        selected_cloud=selected_cloud,
        workflow=workflow,
        retrieved_module_context=retrieved_module_context,
        retrieved_value_context=retrieved_value_context,
    )
    active = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    if not active.get("active"):
        return raw
    conversation_block = _TEAMS_CONVERSATION_CONTEXT.get() or ""
    try:
        payload = json.loads(raw)
    except Exception:
        if conversation_block:
            return f"{raw}\n\n{conversation_block}"
        return raw

    context = _get_backend_existing_infra_context(retrieved_value_context or [])
    if isinstance(context, dict) and context.get("invocation_generation"):
        selected_path = str(context.get("selected_path") or "").strip()
        selected_content = ""
        for matched in context.get("matched_files") or []:
            if not isinstance(matched, dict):
                continue
            matched_path = str(matched.get("path") or matched.get("filename") or "").strip()
            if selected_path and matched_path == selected_path:
                selected_content = str(matched.get("content") or "")
                break
        if not selected_content and context.get("matched_files"):
            first = (context.get("matched_files") or [{}])[0]
            if isinstance(first, dict):
                selected_content = str(first.get("content") or "")

        requested_resource_name = _teams_safe_prompt_resource_name(prompt)
        nested_assignments = []
        if selected_content:
            for assignment in _teams_all_hcl_assignment_spans(selected_content):
                value = str(assignment.get("value") or "")
                if _teams_is_multiline_map_value(value):
                    nested_assignments.append({
                        "name": assignment.get("name") or "",
                        "depth": int(assignment.get("depth") or 0),
                        "existing_entry_keys": [
                            entry.get("key") or ""
                            for entry in _teams_map_entry_spans(value[value.find("{") + 1:value.rfind("}")])
                        ][:80],
                    })

        payload["teams_existing_invocation_generation"] = {
            "selected_file": selected_path,
            "resource_aliases": _teams_invocation_resource_aliases(prompt),
            "requested_resource_name": requested_resource_name,
            "repository_ref": context.get("context_ref") or "",
            "repo_target": context.get("repo_target") or "",
            "nested_map_assignments": nested_assignments,
        }
        # Give Foundry the exact full live target separately from the broader
        # evidence list.  This prevents context compaction/ranking from hiding
        # the one file that must be reproduced byte-for-byte.
        if selected_path and selected_content:
            payload["teams_exact_target_file"] = {
                "path": selected_path,
                "content": selected_content,
                "must_preserve_verbatim": True,
                "requested_resource_name": requested_resource_name,
            }
        payload["instructions"] = list(payload.get("instructions") or []) + [
            "TEAMS EXISTING-INVOCATION-FIRST (HARD): this is a module/resource invocation request, not module-repository creation or discovery.",
            "Use the backend-selected existing invocation file as the complete consumer contract. Infer the module source, required expressions, locals/vars wiring, naming, ordering, comments, and formatting from the nearest existing sibling block.",
            "Generate the new invocation in that same file. Do not create a separate invocation file when a demonstrated resource-family file already exists.",
            "Never ask the user to confirm the repository pattern, target file, module source, or whether to reuse existing defaults. Resolve these from live GitHub evidence.",
            "Do not read terraform-github, vena_repos, or another module repository. Do not return an approved-module-repository error for this workflow.",
            "For explicit values in the prompt, apply them in the target environment's values file. For object-backed resources, copy all missing values from the nearest sibling object; never place __FILL__ tokens in the module invocation.",
            "For an object-backed new Azure instance, return all three complete files together: the resource-family definition file wired to a new dedicated var.<object> root, variables.tf with the exact sibling declaration shape cloned under that root (including only attributes the sibling already has), and the target environment's own tfvars values file with a concrete cloned assignment.",
            "The new module block must not reuse an existing sibling's object root and must not contain actual environment values; preserve repository references such as var.*, local.*, resource references, lookup(), and merge() exactly as the nearest sibling demonstrates.",
            "Keep feature-flag enable/disable and existing-configuration modify/delete workflows unchanged. This invocation rule applies only to ordinary create/add/provision requests.",
            "TEAMS EXACT TARGET MATERIALIZATION (HARD): teams_exact_target_file contains the complete live selected file. Start your returned content from that exact text and change only what the current user request requires. Never reconstruct the file from memory or from excerpts.",
            "MAP-DRIVEN CREATION (HARD): when nested_map_assignments identifies a locals/object map in the selected file, add exactly ONE new sibling entry for requested_resource_name inside the existing matching map. Copy the nearest existing sibling entry's complete field structure/wiring and apply the requested name. Do not rename, rewrite, reorder, or delete any existing entry.",
            "For a request like 'create a aca app ... name is homepage-bff-2', the returned selected file MUST contain a new homepage-bff-2 entry (or the repo-normalized equivalent demonstrated by sibling keys). Returning the old file unchanged, only changing unrelated settings, or omitting the requested name is invalid.",
            "Return executable files now. Do not describe a plan and do not rely on a later self-correction turn for ordinary map-entry creation.",
        ]
    if conversation_block:
        payload["teams_conversation_context"] = conversation_block
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

# =============================================================================
# Teams terminal conversation-flow guard
# =============================================================================
# This final wrapper is intentionally last. It establishes one owner for each
# pending reply, prevents target-selection replies from entering branch-choice
# routing, makes `no` deterministically create a new branch, and performs a
# complete stored-chat reset without deleting remote GitHub artifacts.

_TEAMS_FLOW_GUARD_PREVIOUS_HANDLE_CHAT = _handle_teams_chat_request_stateless


def _teams_flow_guard_thread_ids(state: dict, explicit_thread_id: str = "") -> list[str]:
    """Return every workflow thread referenced by one Teams conversation."""
    values: list[str] = []

    def add(value: Any) -> None:
        item = str(value or "").strip()
        if item and item not in values:
            values.append(item)

    add(explicit_thread_id)
    add((state or {}).get("workflow_thread_id"))
    add((state or {}).get("foundry_conversation_id"))

    sessions = (state or {}).get("cloud_sessions") or {}
    if isinstance(sessions, dict):
        for session in sessions.values():
            if isinstance(session, dict):
                add(session.get("thread_id"))
                add(session.get("workflow_thread_id"))
                add(session.get("foundry_conversation_id"))

    for key in ("workflow_thread_ids", "thread_history", "workflow_threads"):
        collection = (state or {}).get(key) or []
        if isinstance(collection, dict):
            collection = list(collection.values())
        if isinstance(collection, (list, tuple, set)):
            for item in collection:
                if isinstance(item, dict):
                    add(item.get("thread_id"))
                else:
                    add(item)

    return values


def _teams_flow_guard_clear_thread(thread_id: str) -> None:
    """Clear all transient/backend state for a thread, never GitHub refs."""
    thread = str(thread_id or "").strip()
    if not thread:
        return

    try:
        restore_teams_workflow_state(thread)
    except Exception:
        pass

    for mapping in _teams_pending_state_mappings().values():
        _remove_teams_mapping_entries_for_thread(mapping, thread)

    # These dictionaries contain workflow metadata only. Removing them does not
    # call GitHub and therefore does not delete a branch, commit, or pull request.
    THREAD_PR_STATE.pop(thread, None)
    THREAD_METADATA.pop(thread, None)
    THREAD_AUTO_ADVANCE_IN_PROGRESS.discard(thread)
    _delete_chunked_teams_state(_TEAMS_WORKFLOW_STATE_PARTITION, thread)


def reset_teams_chat_session(
    teams_conversation_id: str,
    workflow_thread_id: str = "",
) -> dict:
    """Clear all stored Teams history/pending state and preserve GitHub artifacts."""
    conversation_id = str(teams_conversation_id or "").strip()
    explicit_thread = str(workflow_thread_id or "").strip()
    state = load_teams_conversation_state(conversation_id) if conversation_id else {}
    thread_ids = _teams_flow_guard_thread_ids(state, explicit_thread)

    for thread_id in thread_ids:
        _teams_flow_guard_clear_thread(thread_id)

    if conversation_id:
        clear_teams_conversation_state(conversation_id)

    LOGGER.info(
        "Reset complete Teams chat state: conversation_hash=%s workflow_count=%s",
        stable_thread_key(conversation_id) if conversation_id else "",
        len(thread_ids),
    )
    return {
        "ok": True,
        "conversation_state_cleared": bool(conversation_id),
        "workflow_state_cleared": bool(thread_ids),
        "workflow_states_cleared": len(thread_ids),
        "cleared_workflow_thread_ids": thread_ids,
        "github_artifacts_deleted": False,
        "github_auth_cleared": False,
    }


def _teams_flow_guard_thread_candidates_stage1(request_data: dict, state: dict) -> list[str]:
    values: list[str] = []

    def add(value: Any) -> None:
        item = str(value or "").strip()
        if item and item not in values:
            values.append(item)

    add((request_data or {}).get("thread_id"))
    add((request_data or {}).get("pending_target_selection_thread_id"))
    add((state or {}).get("pending_target_selection_thread_id"))
    add((state or {}).get("workflow_thread_id"))
    add((state or {}).get("foundry_conversation_id"))
    sessions = (state or {}).get("cloud_sessions") or {}
    if isinstance(sessions, dict):
        for session in sessions.values():
            if isinstance(session, dict):
                add(session.get("thread_id"))
    return values
_teams_flow_guard_thread_candidates = _teams_flow_guard_thread_candidates_stage1


def _teams_flow_guard_find_target_selection(
    request_data: dict,
    state: dict,
    reply: str,
) -> tuple[str, dict, int | None]:
    """Find the exact pending target picker to which this reply belongs."""
    ticket_candidates: list[str] = []
    for value in (
        (request_data or {}).get("jira_ticket"),
        (request_data or {}).get("ticket_number"),
        (state or {}).get("ticket_number"),
        "",
    ):
        ticket = str(value or "").strip().upper()
        if ticket not in ticket_candidates:
            ticket_candidates.append(ticket)

    for thread_id in _teams_flow_guard_thread_candidates(request_data, state):
        for ticket in ticket_candidates:
            try:
                pending = get_pending_infra_modification_selection(thread_id, ticket)
            except Exception:
                pending = {}
            if not pending:
                continue
            selected_index = select_infra_modification_candidate_from_reply(reply, pending)
            if selected_index is not None:
                return thread_id, pending, selected_index
    return "", {}, None


def _teams_flow_guard_clear_branch_prompt(teams_conversation_id: str, stage: str) -> dict:
    patch = {
        "stage": stage,
        "reset_confirmation_pending": None,
        "pending_follow_up_prompt": None,
        "pending_follow_up_cloud": None,
        "pending_follow_up_has_pr": None,
        "pending_follow_up_branch": None,
        "pending_follow_up_pr_url": None,
        "pending_follow_up_ticket_link": None,
        "pending_follow_up_ticket_number": None,
        "pending_follow_up_ticket_title": None,
    }
    if teams_conversation_id:
        _teams_save_ui_state(teams_conversation_id, patch)
    return patch


def _teams_flow_guard_prepare_branch_reply(
    request_data: dict,
    state: dict,
    teams_conversation_id: str,
    prompt: str,
) -> tuple[dict, bool]:
    """Bind yes/no to the captured branch prompt and restore its infra request."""
    stage = str((state or {}).get("stage") or "").strip()
    marked = _teams_truthy((request_data or {}).get("pending_branch_choice_reply"))
    if stage != "awaiting_branch_reuse_decision" and not marked:
        return request_data, False

    explicit_choice = str((request_data or {}).get("branch_choice") or "").strip().lower()
    choice = explicit_choice if explicit_choice in {"reuse", "new"} else _teams_branch_choice_from_reply(prompt)
    if not choice:
        return request_data, False

    pending_prompt = str((state or {}).get("pending_follow_up_prompt") or "").strip()
    if not pending_prompt:
        return request_data, False

    updated = dict(request_data or {})
    old_thread = str(
        (state or {}).get("workflow_thread_id")
        or (state or {}).get("foundry_conversation_id")
        or updated.get("thread_id")
        or ""
    ).strip()

    # If an earlier router incorrectly asked for a branch after a target-picker
    # reply, continue that picker on its original workflow thread. Do not clear
    # its pending selection object before the core handler consumes it.
    selection_thread, _pending, selection_index = _teams_flow_guard_find_target_selection(
        {**updated, "thread_id": old_thread},
        state,
        pending_prompt,
    )
    is_target_selection = selection_index is not None

    if not is_target_selection:
        _teams_clear_pending_generation_for_thread(old_thread)

    updated["prompt"] = pending_prompt
    updated["message"] = pending_prompt
    updated["pending_branch_choice_resolved"] = True
    updated["pending_branch_choice_reply"] = True
    updated["branch_choice"] = choice
    updated["reuse_branch"] = choice == "reuse"
    updated["force_new_branch"] = choice == "new"
    updated["existing_branch"] = (
        str((state or {}).get("pending_follow_up_branch") or (state or {}).get("branch") or "").strip()
        if choice == "reuse"
        else ""
    )
    updated["fresh_infra_generation"] = True

    if is_target_selection:
        updated["thread_id"] = selection_thread
        updated["pending_target_selection_reply"] = True
    else:
        # The new infrastructure instruction gets a fresh Foundry conversation.
        # Live GitHub branch contents remain the source of truth for reuse.
        updated["thread_id"] = ""

    for source_key, target_key in (
        ("pending_follow_up_ticket_link", "ticket_link"),
        ("pending_follow_up_ticket_number", "jira_ticket"),
        ("pending_follow_up_ticket_title", "ticket_title"),
    ):
        value = (state or {}).get(source_key)
        if value and not updated.get(target_key):
            updated[target_key] = value

    updated["state_patch"] = _teams_flow_guard_clear_branch_prompt(
        teams_conversation_id,
        "infra_modification_target_selection" if is_target_selection else "processing_new_infrastructure_request",
    )
    # Persist the branch decision across any later semantic target picker. The
    # picker is repository disambiguation only; it must never reopen branch
    # selection or lose the selected cloud.
    updated["state_patch"].update({
        "branch_choice_resolved_for_request": True,
        "resolved_branch_choice": choice,
        "resolved_reuse_branch": choice == "reuse",
        "resolved_force_new_branch": choice == "new",
        "resolved_existing_branch": updated.get("existing_branch") or "",
        "resolved_branch_cloud": str((state or {}).get("pending_follow_up_cloud") or (state or {}).get("cloud") or updated.get("cloud") or "").strip(),
    })
    if teams_conversation_id:
        _teams_save_ui_state(teams_conversation_id, updated["state_patch"])
    return updated, True


def _handle_teams_chat_request_state_machine(data: dict):
    """Terminal Teams state machine: one pending reply, one transition, no loops."""
    request_data = dict(data or {})
    prompt = str(request_data.get("prompt") or request_data.get("message") or "").strip()
    action = str(request_data.get("action") or "").strip().lower()
    teams_conversation_id = str(
        request_data.get("teams_conversation_id")
        or request_data.get("conversation_id")
        or ""
    ).strip()
    state = load_teams_conversation_state(teams_conversation_id) if teams_conversation_id else {}

    # Semantic intent belongs exclusively to Foundry. Backend code handles only
    # deterministic protocol continuations (branch yes/no, Jira, target picks,
    # PR decisions). Every ordinary user message is classified once in a fresh
    # Foundry call before repository discovery/routing.
    if (
        prompt
        and not _teams_message_is_protocol_control(request_data, state, prompt)
        and str(request_data.get("mode") or "").strip().lower() != "infra"
    ):
        foundry_intent = _teams_foundry_classify_request(prompt)
        request_data["foundry_intent"] = foundry_intent
        if foundry_intent == "infra":
            request_data["mode"] = "infra"
        elif foundry_intent in {"chat", "repo_qna"}:
            request_data.pop("mode", None)

    # State from versions that required clear-confirmation is invalid here. The
    # explicit clear command is handled synchronously by teams_bot.py.
    if state.get("reset_confirmation_pending") is not None and teams_conversation_id:
        _teams_save_ui_state(teams_conversation_id, {"reset_confirmation_pending": None})
        state.pop("reset_confirmation_pending", None)

    # Restore backend pending state before interpreting a numeric/path reply.
    # This is required after Azure Functions cold starts and also prevents the
    # lower plain-chat guard from treating option `1` as a greeting request.
    if not action:
        for candidate_thread in _teams_flow_guard_thread_candidates(request_data, state):
            try:
                restore_teams_workflow_state(candidate_thread)
            except Exception:
                LOGGER.exception(
                    "Unable to restore Teams target-selection state: thread_hash=%s",
                    stable_thread_key(candidate_thread),
                )

    target_thread = ""
    target_pending: dict = {}
    target_index: int | None = None
    if not action:
        target_thread, target_pending, target_index = _teams_flow_guard_find_target_selection(
            request_data,
            state,
            prompt,
        )

    marked_target_selection = _teams_truthy(
        request_data.get("pending_target_selection_reply")
    )
    target_selection_reply = bool(target_index is not None or marked_target_selection)

    if marked_target_selection and target_index is None:
        # A marked selection must never fall through to Foundry chat. Try the
        # durable locator once more, then fail closed with a deterministic
        # recovery message rather than returning the agent's greeting.
        locator_thread = str(
            request_data.get("pending_target_selection_thread_id")
            or state.get("pending_target_selection_thread_id")
            or request_data.get("thread_id")
            or ""
        ).strip()
        if locator_thread:
            try:
                restore_teams_workflow_state(locator_thread)
            except Exception:
                LOGGER.exception(
                    "Unable to restore marked target selection: thread_hash=%s",
                    stable_thread_key(locator_thread),
                )
            target_thread, target_pending, target_index = _teams_flow_guard_find_target_selection(
                {**request_data, "thread_id": locator_thread},
                state,
                prompt,
            )

        if target_index is None:
            patch = _teams_flow_guard_clear_branch_prompt(
                teams_conversation_id,
                "idle",
            )
            patch.update({
                "pending_target_selection_thread_id": None,
                "pending_target_selection_original_prompt": None,
            })
            return {
                "ok": False,
                "mode": "clarification",
                "reply": (
                    "The saved Terraform target selection could not be restored, so Terrabot "
                    "cleared that expired selection instead of treating your reply as chat. "
                    "Resend the infrastructure request; existing GitHub branches were kept."
                ),
                "thread_id": locator_thread,
                "state_patch": patch,
                "diagnostic_code": "TEAMS_TARGET_SELECTION_STATE_EXPIRED",
            }, 409

    if target_selection_reply:
        # Branch choice is resolved BEFORE target disambiguation. A target-picker
        # reply may select only the repository target; it must never reopen or
        # silently replace the branch decision.
        branch_already_resolved = bool(
            _teams_truthy(request_data.get("pending_branch_choice_resolved"))
            or _teams_truthy(state.get("branch_choice_resolved_for_request"))
        )
        resolved_choice = str(
            request_data.get("branch_choice")
            or state.get("resolved_branch_choice")
            or ""
        ).strip().lower()
        if branch_already_resolved:
            request_data["pending_branch_choice_resolved"] = True
            request_data["reuse_branch"] = (
                resolved_choice == "reuse"
                or _teams_truthy(state.get("resolved_reuse_branch"))
            )
            request_data["force_new_branch"] = (
                resolved_choice == "new"
                or _teams_truthy(state.get("resolved_force_new_branch"))
            )
            request_data["existing_branch"] = str(
                request_data.get("existing_branch")
                or state.get("resolved_existing_branch")
                or ""
            ).strip()
        elif not str(state.get("branch") or "").strip():
            # First request in this cloud: there was no reusable branch to ask
            # about, so the backend may create a fresh branch after generation.
            request_data["pending_branch_choice_resolved"] = True
            request_data.setdefault("reuse_branch", False)
            request_data.setdefault("force_new_branch", True)
            request_data.setdefault("existing_branch", "")
        else:
            # Compatibility for stale conversations created by older versions:
            # branch-first ordering was not recorded. Ask once, but never after
            # a recorded branch decision. New requests cannot enter this path.
            selection_thread = target_thread or str(request_data.get("thread_id") or "").strip()
            original_request = str(
                (target_pending or {}).get("original_prompt")
                or state.get("pending_target_selection_original_prompt")
                or request_data.get("original_prompt")
                or ""
            ).strip()
            existing_branch = str(state.get("branch") or "").strip()
            patch = {
                "stage": "awaiting_branch_reuse_decision",
                "pending_follow_up_prompt": prompt,
                "pending_follow_up_branch": existing_branch,
                "pending_follow_up_cloud": (target_pending or {}).get("cloud") or state.get("cloud") or "",
                "pending_follow_up_ticket_link": request_data.get("ticket_link") or state.get("ticket_link") or "",
                "pending_follow_up_ticket_number": request_data.get("jira_ticket") or state.get("ticket_number") or "",
                "pending_follow_up_ticket_title": request_data.get("ticket_title") or state.get("ticket_title") or "",
                "pending_target_selection_thread_id": selection_thread,
                "pending_target_selection_original_prompt": original_request,
            }
            _teams_save_ui_state(teams_conversation_id, patch)
            return {
                "ok": False,
                "mode": "branch_choice_required",
                "decision_state": "awaiting_branch_reuse_decision",
                "reply": (
                    f"Choose the branch before I apply the selected Terraform target. Existing branch: `{existing_branch}`."
                ),
                "thread_id": selection_thread,
                "branch": existing_branch,
                "branch_url": state.get("branch_url") or "",
                "compare_url": state.get("compare_url") or "",
                "state_patch": patch,
            }, 400

        if target_thread:
            request_data["thread_id"] = target_thread

        # Resolve the active cloud BEFORE delegating the selected target. A
        # target-picker reply such as "2" is workflow control, not a new cloud
        # classification event. Prefer the pending picker, then the branch cloud
        # captured for this request, then the request payload/current UI cloud.
        selected_request_cloud = safe_normalize_cloud(str(
            (target_pending or {}).get("cloud")
            or request_data.get("cloud")
            or request_data.get("requested_cloud")
            or state.get("resolved_branch_cloud")
            or state.get("pending_follow_up_cloud")
            or state.get("cloud")
            or ""
        )) or ""

        request_data.update({
            "mode": "infra",
            "pending_target_selection_reply": True,
            "pending_target_selection_thread_id": target_thread or request_data.get("thread_id") or "",
            "pending_target_selection_resolved": True,
            "fresh_infra_generation": True,
        })
        if selected_request_cloud:
            request_data["cloud"] = selected_request_cloud
            request_data["requested_cloud"] = selected_request_cloud
        if target_pending:
            # The pending picker owns cloud/workflow/request identity. This
            # prevents a selected AWS Redshift target from falling into the
            # generic "both AWS and Azure PRs" ambiguity branch.
            request_data["cloud"] = target_pending.get("cloud") or request_data.get("cloud") or ""
            request_data["requested_cloud"] = request_data["cloud"]
            request_data["workflow"] = target_pending.get("workflow") or request_data.get("workflow") or ""
            request_data["original_prompt"] = target_pending.get("original_prompt") or request_data.get("original_prompt") or ""
        elif state.get("resolved_branch_cloud"):
            request_data["cloud"] = state.get("resolved_branch_cloud")
            request_data["requested_cloud"] = state.get("resolved_branch_cloud")

        request_data["state_patch"] = _teams_flow_guard_clear_branch_prompt(
            teams_conversation_id,
            "infra_modification_target_selection",
        )
        request_data["state_patch"].update({
            "branch_choice_resolved_for_request": True,
            "resolved_branch_choice": resolved_choice or state.get("resolved_branch_choice") or "new",
            "resolved_reuse_branch": _teams_truthy(request_data.get("reuse_branch")),
            "resolved_force_new_branch": _teams_truthy(request_data.get("force_new_branch")),
            "resolved_existing_branch": request_data.get("existing_branch") or "",
            "resolved_branch_cloud": request_data.get("cloud") or state.get("resolved_branch_cloud") or "",
        })

    branch_reply_handled = False
    if not action and not target_selection_reply:
        request_data, branch_reply_handled = _teams_flow_guard_prepare_branch_reply(
            request_data,
            state,
            teams_conversation_id,
            prompt,
        )

    result, status_code = _TEAMS_FLOW_GUARD_PREVIOUS_HANDLE_CHAT(request_data)
    result = dict(result or {})

    # Post-selection backend validation/repair. Once the user selected a real
    # candidate, branch + cloud + target are all resolved. A response that
    # reopens branch selection, repeats the picker, asks which cloud, or returns
    # generic clarification is mechanically invalid. Re-submit the SAME
    # selected request to the generation/agent path once with explicit workflow
    # identity; do not expose the faulty output to Teams.
    if target_selection_reply:
        reply_lower = str(result.get("reply") or result.get("summary") or "").lower()
        decision_lower = str(result.get("decision_state") or "").strip().lower()
        mode_lower = str(result.get("mode") or "").strip().lower()
        faulty_clarification_markers = (
            "this thread has both aws and azure prs",
            "please specify which cloud",
            "reply with the option number",
            "select one of the listed terraform targets",
            "choose the infrastructure target",
            "provide the exact file path",
            "could not identify one safe live-repository target",
            "repository path",
        )
        faulty_after_selection = bool(
            mode_lower == "branch_choice_required"
            or decision_lower == "infra_modification_target_selection"
            or any(marker in reply_lower for marker in faulty_clarification_markers)
        )
        if faulty_after_selection and target_pending and target_index is not None:
            # The lower handler normally consumes/clears the pending object even
            # if a later router emits a faulty clarification. Restore it for the
            # repair pass so the selected candidate can be materialized again.
            try:
                store_pending_infra_modification_selection(
                    thread_id=target_thread or str(request_data.get("thread_id") or ""),
                    ticket_number=str(target_pending.get("ticket_number") or ""),
                    original_prompt=target_pending.get("original_prompt") or request_data.get("original_prompt") or "",
                    cloud=target_pending.get("cloud") or request_data.get("cloud") or "",
                    workflow=target_pending.get("workflow") or request_data.get("workflow") or "",
                    retrieved_module_context=target_pending.get("retrieved_module_context") or [],
                    retrieved_value_context=target_pending.get("retrieved_value_context") or [],
                    existing_infra_context=target_pending.get("existing_infra_context") or {},
                    ticket_link=target_pending.get("ticket_link") or request_data.get("ticket_link") or "",
                    ticket_title=target_pending.get("ticket_title") or request_data.get("ticket_title") or "",
                )
            except Exception:
                LOGGER.exception("Unable to restore target selection for repair pass")

            repair = dict(request_data)
            repair.update({
                "thread_id": target_thread or repair.get("thread_id") or "",
                "prompt": prompt,
                "mode": "infra",
                "pending_target_selection_reply": True,
                "pending_target_selection_thread_id": target_thread or repair.get("thread_id") or "",
                "pending_target_selection_resolved": True,
                "pending_branch_choice_resolved": True,
                "cloud": target_pending.get("cloud") or repair.get("cloud") or "",
                "requested_cloud": target_pending.get("cloud") or repair.get("cloud") or "",
                "workflow": target_pending.get("workflow") or repair.get("workflow") or "",
                "original_prompt": target_pending.get("original_prompt") or repair.get("original_prompt") or "",
                "post_selection_repair": True,
                "fresh_infra_generation": True,
            })
            result, status_code = _TEAMS_FLOW_GUARD_PREVIOUS_HANDLE_CHAT(repair)
            result = dict(result or {})
            request_data = repair

    # Defense in depth: an explicit infrastructure request must never escape
    # the terminal Teams state machine as a read-only repository-Q&A chat
    # response. This catches legacy/router paths outside the inner generation
    # corrective above, including branch-choice continuations restored from
    # durable state. Retry once with infrastructure mode forced while keeping
    # the exact restored prompt and branch decision.
    _terminal_repo_qa_mismatch = bool(
        str(result.get("mode") or "").lower() == "chat"
        and request_data.get("mode") == "infra"
    )
    if _terminal_repo_qa_mismatch:
        retry = dict(request_data)
        retry["mode"] = "infra"
        retry["foundry_intent"] = "infra"
        retry["fresh_infra_generation"] = True
        retry["pending_branch_choice_resolved"] = bool(
            retry.get("pending_branch_choice_resolved")
            or retry.get("pending_branch_choice_reply")
        )
        result, status_code = _TEAMS_FLOW_GUARD_PREVIOUS_HANDLE_CHAT(retry)
        result = dict(result or {})

    # One guarded retry is allowed only when a lower legacy wrapper attempted
    # to re-open branch choice before consuming an existing target selection.
    if target_selection_reply and str(result.get("mode") or "").lower() == "branch_choice_required":
        retry_thread, _retry_pending, retry_index = _teams_flow_guard_find_target_selection(
            request_data,
            load_teams_conversation_state(teams_conversation_id) if teams_conversation_id else state,
            prompt,
        )
        if retry_index is not None:
            retry = dict(request_data)
            retry["thread_id"] = retry_thread
            retry["pending_branch_choice_resolved"] = True
            # Preserve the branch decision already made before target
            # disambiguation. A repair retry may not silently convert reuse ->
            # new branch or discard the selected existing branch.
            retry["force_new_branch"] = _teams_truthy(request_data.get("force_new_branch"))
            retry["reuse_branch"] = _teams_truthy(request_data.get("reuse_branch"))
            retry["existing_branch"] = str(request_data.get("existing_branch") or "")
            retry["branch_choice"] = str(request_data.get("branch_choice") or "")
            _teams_flow_guard_clear_branch_prompt(
                teams_conversation_id,
                "infra_modification_target_selection",
            )
            result, status_code = _TEAMS_FLOW_GUARD_PREVIOUS_HANDLE_CHAT(retry)
            result = dict(result or {})

    # A target-selection reply is workflow control, never chat. Retry once if
    # a legacy lower wrapper returned a conversational response before reaching
    # the durable pending-state handler.
    if target_selection_reply and str(result.get("mode") or "").lower() == "chat":
        retry_state = load_teams_conversation_state(teams_conversation_id) if teams_conversation_id else state
        for candidate_thread in _teams_flow_guard_thread_candidates(request_data, retry_state):
            try:
                restore_teams_workflow_state(candidate_thread)
            except Exception:
                pass
        retry_thread, retry_pending, retry_index = _teams_flow_guard_find_target_selection(
            request_data,
            retry_state,
            prompt,
        )
        if retry_index is not None:
            retry = dict(request_data)
            retry.update({
                "thread_id": retry_thread,
                "mode": "infra",
                "pending_target_selection_reply": True,
                "pending_target_selection_thread_id": retry_thread,
                "pending_branch_choice_resolved": True,
                "pending_target_selection_resolved": True,
                # Keep the branch choice from the request that opened the
                # picker; this retry repairs routing only.
                "force_new_branch": _teams_truthy(request_data.get("force_new_branch")),
                "reuse_branch": _teams_truthy(request_data.get("reuse_branch")),
                "existing_branch": str(request_data.get("existing_branch") or ""),
                "branch_choice": str(request_data.get("branch_choice") or ""),
                "fresh_infra_generation": True,
                "cloud": retry_pending.get("cloud") or retry.get("cloud") or "",
                "workflow": retry_pending.get("workflow") or retry.get("workflow") or "",
                "original_prompt": retry_pending.get("original_prompt") or retry.get("original_prompt") or "",
            })
            _teams_flow_guard_clear_branch_prompt(
                teams_conversation_id,
                "infra_modification_target_selection",
            )
            result, status_code = _TEAMS_FLOW_GUARD_PREVIOUS_HANDLE_CHAT(retry)
            result = dict(result or {})

    if target_selection_reply and str(result.get("mode") or "").lower() == "chat":
        patch = _teams_flow_guard_clear_branch_prompt(teams_conversation_id, "idle")
        patch.update({
            "pending_target_selection_thread_id": None,
            "pending_target_selection_original_prompt": None,
        })
        return {
            "ok": False,
            "mode": "clarification",
            "reply": (
                "Terrabot blocked a conflicting chat response while processing the Terraform "
                "target selection. Resend the infrastructure request; existing GitHub branches "
                "were kept."
            ),
            "thread_id": str(request_data.get("thread_id") or ""),
            "state_patch": patch,
            "diagnostic_code": "TEAMS_TARGET_SELECTION_CHAT_CONFLICT_BLOCKED",
        }, 409

    # Never return the same branch question after a definitive yes/no reply.
    # Retry once after forcing the durable stage out of branch selection; this
    # absorbs stale legacy wrappers without asking the user twice.
    if branch_reply_handled and str(result.get("mode") or "").lower() == "branch_choice_required":
        retry = dict(request_data)
        retry["pending_branch_choice_resolved"] = True
        retry["reuse_branch"] = _teams_truthy(request_data.get("reuse_branch"))
        retry["force_new_branch"] = _teams_truthy(request_data.get("force_new_branch"))
        retry["existing_branch"] = str(request_data.get("existing_branch") or "")
        _teams_flow_guard_clear_branch_prompt(
            teams_conversation_id,
            "processing_new_infrastructure_request",
        )
        result, status_code = _TEAMS_FLOW_GUARD_PREVIOUS_HANDLE_CHAT(retry)
        result = dict(result or {})

    if branch_reply_handled and str(result.get("mode") or "").lower() == "branch_choice_required":
        patch = _teams_flow_guard_clear_branch_prompt(teams_conversation_id, "idle")
        return {
            "ok": False,
            "mode": "clarification",
            "reply": (
                "Terrabot cleared a conflicting branch-decision state instead of repeating the question. "
                "Resend the infrastructure request; existing GitHub branches were kept."
            ),
            "thread_id": str(result.get("thread_id") or ""),
            "state_patch": patch,
            "diagnostic_code": "TEAMS_BRANCH_DECISION_CONFLICT_CLEARED",
        }, 409

    patch = dict(result.get("state_patch") or {})
    patch["reset_confirmation_pending"] = None
    decision_state = str(result.get("decision_state") or "").strip()
    if decision_state == "infra_modification_target_selection":
        selection_thread = str(
            result.get("thread_id")
            or request_data.get("thread_id")
            or ""
        ).strip()
        patch.update({
            "stage": "infra_modification_target_selection",
            "pending_target_selection_thread_id": selection_thread,
            "pending_target_selection_original_prompt": str(
                result.get("request_prompt")
                or request_data.get("original_prompt")
                or request_data.get("prompt")
                or ""
            ).strip(),
            # Keep the already-resolved branch choice across the picker turn.
            "branch_choice_resolved_for_request": bool(
                _teams_truthy(request_data.get("pending_branch_choice_resolved"))
                or _teams_truthy(state.get("branch_choice_resolved_for_request"))
            ),
            "resolved_branch_choice": request_data.get("branch_choice") or state.get("resolved_branch_choice") or "",
            "resolved_reuse_branch": _teams_truthy(request_data.get("reuse_branch")) or _teams_truthy(state.get("resolved_reuse_branch")),
            "resolved_force_new_branch": _teams_truthy(request_data.get("force_new_branch")) or _teams_truthy(state.get("resolved_force_new_branch")),
            "resolved_existing_branch": request_data.get("existing_branch") or state.get("resolved_existing_branch") or "",
            "resolved_branch_cloud": request_data.get("cloud") or state.get("resolved_branch_cloud") or result.get("cloud") or "",
        })
    elif target_selection_reply:
        # Clear the branch/target continuation only after a successful
        # materialization. If a genuine blocker survives the internal repair
        # pass, keep the resolved branch/cloud so the next continuation cannot
        # fall back into branch selection or cross-cloud ambiguity.
        terminal_selection_success = bool(
            status_code < 400
            and result.get("ok", True)
            and str(result.get("mode") or "").strip().lower()
            not in {"clarification", "branch_choice_required"}
            and str(result.get("decision_state") or "").strip().lower()
            != "infra_modification_target_selection"
        )
        if terminal_selection_success:
            patch.update({
                "pending_target_selection_thread_id": None,
                "pending_target_selection_original_prompt": None,
                "branch_choice_resolved_for_request": None,
                "resolved_branch_choice": None,
                "resolved_reuse_branch": None,
                "resolved_force_new_branch": None,
                "resolved_existing_branch": None,
                "resolved_branch_cloud": None,
            })
        else:
            patch.update({
                "stage": "infra_modification_target_selection",
                "pending_target_selection_thread_id": target_thread or request_data.get("thread_id") or "",
                "pending_target_selection_original_prompt": (
                    (target_pending or {}).get("original_prompt")
                    or request_data.get("original_prompt")
                    or state.get("pending_target_selection_original_prompt")
                    or ""
                ),
                "branch_choice_resolved_for_request": True,
                "resolved_branch_choice": request_data.get("branch_choice") or state.get("resolved_branch_choice") or "",
                "resolved_reuse_branch": _teams_truthy(request_data.get("reuse_branch")),
                "resolved_force_new_branch": _teams_truthy(request_data.get("force_new_branch")),
                "resolved_existing_branch": request_data.get("existing_branch") or state.get("resolved_existing_branch") or "",
                "resolved_branch_cloud": request_data.get("cloud") or state.get("resolved_branch_cloud") or "",
            })

    if target_selection_reply or branch_reply_handled:
        patch.update({
            "pending_follow_up_prompt": None,
            "pending_follow_up_cloud": None,
            "pending_follow_up_has_pr": None,
            "pending_follow_up_branch": None,
            "pending_follow_up_pr_url": None,
            "pending_follow_up_ticket_link": None,
            "pending_follow_up_ticket_number": None,
            "pending_follow_up_ticket_title": None,
        })
    result["state_patch"] = patch
    if teams_conversation_id:
        _teams_save_ui_state(teams_conversation_id, patch)

    return result, status_code
handle_teams_chat_request = _handle_teams_chat_request_state_machine

# =============================================================================
# Final prompt/output relevance + Terraform validation guard
# =============================================================================
# This patch is deliberately appended as a final override so every earlier
# workflow/branch/GitHub-App patch remains intact. It adds a write-time semantic
# gate and removes backend preference for specific AWS consumer filenames.

_PROMPT_GUARD_PREVIOUS_COMMIT_TERRAFORM_FOR_TEAMS = commit_terraform_files_to_branch_for_teams
_PROMPT_GUARD_PREVIOUS_AWS_CONSUMER_SELECTOR = _teams_select_aws_environment_consumer_file

_PROMPT_GUARD_GENERIC_WORDS = {
    "a", "an", "the", "create", "add", "provision", "deploy", "make", "new",
    "update", "modify", "change", "set", "enable", "disable", "remove", "delete",
    "in", "into", "for", "on", "of", "to", "with", "using", "use", "existing",
    "aws", "azure", "terraform", "resource", "module", "instance", "environment",
    "env", "dev", "prod", "production", "nonprod", "non", "minidev", "please",
}


def _prompt_guard_resource_tokens(prompt: str) -> set[str]:
    """Extract resource-specific request tokens without service hardcoding.

    The AWS matcher already owns repository-aware token normalization, including
    plural/singular handling and weak-token filtering. Reuse it when available;
    otherwise use a conservative generic tokenizer. Environment names are not
    semantic proof that generated code implements the requested resource.
    """
    text = str(prompt or "").strip().lower()
    if not text:
        return set()
    try:
        tokens = set(_teams_aws_discriminative_tokens(text))
    except Exception:
        tokens = set()
    if tokens:
        return tokens
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text)
        if len(token) > 1
        and token not in _PROMPT_GUARD_GENERIC_WORDS
        and not _TEAMS_AWS_ENVIRONMENT_TOKEN_RE.fullmatch(token or "")
    }


def _prompt_guard_generated_blob(agent_result: dict) -> str:
    parts = [
        str(agent_result.get("title") or ""),
        str(agent_result.get("summary") or ""),
        str(agent_result.get("analysis") or ""),
    ]
    for item in agent_result.get("files") or []:
        if not isinstance(item, dict):
            continue
        parts.append(str(item.get("filename") or item.get("path") or ""))
        parts.append(str(item.get("content") or ""))
    return "\n".join(parts).lower()


def _prompt_guard_matching_verified_aws_modules(prompt: str) -> set[str]:
    """Return live module paths that are semantically supported by this prompt."""
    active = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    matches: set[str] = set()
    for item in active.get("retrieved_module_context") or []:
        if not isinstance(item, dict):
            continue
        raw_path = str(item.get("module_path") or item.get("verified_module_path") or "").strip()
        module_path = _sanitize_aws_module_rel_path(raw_path)
        if not module_path:
            continue
        keep, _reasons = _teams_aws_match_has_resource_evidence(prompt, {"module_path": module_path})
        if keep:
            matches.add(module_path)
    return matches


def _prompt_guard_validate_semantic_relevance(agent_result: dict, prompt: str) -> None:
    """Reject stale/wrong-resource output before any GitHub write.

    This specifically prevents a request such as "create an EC2 instance" from
    committing a Redshift consumer merely because Redshift appeared in nearby
    repository evidence or a prior Foundry turn.
    """
    if not isinstance(agent_result, dict):
        raise ValueError("Generated infrastructure result is not a JSON object.")
    files = [item for item in agent_result.get("files") or [] if isinstance(item, dict)]
    if not files:
        raise ValueError("Generated infrastructure result contains no Terraform files.")

    active = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    cloud = safe_normalize_cloud(agent_result.get("cloud") or active.get("expected_cloud") or "") or ""
    workflow = str(agent_result.get("workflow") or active.get("expected_workflow") or "").strip()
    blob = _prompt_guard_generated_blob(agent_result)
    request_tokens = _prompt_guard_resource_tokens(prompt)

    if cloud == "aws" and request_tokens:
        verified_matches = _prompt_guard_matching_verified_aws_modules(prompt)
        referenced_modules: set[str] = set()
        for item in files:
            for ref in _extract_aws_module_source_refs_from_text(str(item.get("content") or "")):
                module_path = _sanitize_aws_module_rel_path(str(ref.get("module_path") or ""))
                if module_path:
                    referenced_modules.add(module_path)

        if workflow == "aws_module_consumer" and verified_matches:
            if not (referenced_modules & verified_matches):
                raise ValueError(
                    "PROMPT_OUTPUT_MISMATCH: generated AWS consumer references module(s) "
                    f"{sorted(referenced_modules) or ['none']} but the current request '{prompt}' "
                    f"is supported by verified module(s) {sorted(verified_matches)}. Regenerate only for the current request."
                )
        elif workflow == "aws_module_consumer" and referenced_modules:
            wrong = [
                path for path in referenced_modules
                if not _teams_aws_match_has_resource_evidence(prompt, {"module_path": path})[0]
            ]
            if wrong and len(wrong) == len(referenced_modules):
                raise ValueError(
                    "PROMPT_OUTPUT_MISMATCH: every generated AWS module reference is unrelated to the current "
                    f"request '{prompt}': {sorted(wrong)}. Do not reuse repository evidence from another resource."
                )

        # New-module generation must name/materialize a module whose path is
        # semantically tied to the current prompt, not a stale module family.
        if workflow == "aws_module_creation":
            created_paths = _aws_created_module_paths_from_files(files)
            unrelated = [
                path for path in created_paths
                if not _teams_aws_match_has_resource_evidence(prompt, {"module_path": path})[0]
            ]
            if created_paths and len(unrelated) == len(created_paths):
                raise ValueError(
                    "PROMPT_OUTPUT_MISMATCH: generated new AWS module path(s) do not match the current "
                    f"request '{prompt}': {sorted(created_paths)}."
                )

        # Generic last-line defense: at least one resource-specific request
        # token should survive into filenames/content/summary unless a verified
        # module path already proves the semantic match.
        token_hit = any(re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", blob) for token in request_tokens)
        if not token_hit and not verified_matches:
            raise ValueError(
                "PROMPT_OUTPUT_MISMATCH: generated Terraform contains no resource-specific evidence for "
                f"the current request '{prompt}' (request tokens: {sorted(request_tokens)})."
            )


def _prompt_guard_validate_terraform_shape(agent_result: dict) -> None:
    """Run backend-local Terraform/HCL completeness checks before agent review."""
    for item in agent_result.get("files") or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("filename") or item.get("path") or "").strip()
        if not path.endswith((".tf", ".tfvars")):
            continue
        content = str(item.get("content") or "")
        if not content.strip():
            raise ValueError(f"Generated Terraform file {path} is empty.")
        _validate_hcl_content_complete(path, content)
        if _has_git_conflict_markers(content):
            raise ValueError(f"Generated Terraform file {path} contains Git conflict markers.")


def _prompt_guard_agent_self_validate_stage1(agent_result: dict, prompt: str) -> None:
    """Ask Foundry for an independent semantic + Terraform sanity verdict.

    This is intentionally a fresh validation conversation: it cannot inherit a
    previous resource request. The backend remains authoritative and runs its
    own validators after this check; this call is an additional model-level
    guard, not a replacement for deterministic validation.
    """
    active = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    if not active.get("active"):
        return
    if str(os.getenv("TERRABOT_TEAMS_AGENT_SELF_VALIDATE", "true")).strip().lower() in {"0", "false", "no"}:
        return

    compact_files = []
    max_chars = max(4000, int(os.getenv("TERRABOT_TEAMS_SELF_VALIDATE_FILE_CHARS", "16000")))
    for item in agent_result.get("files") or []:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "")
        compact_files.append({
            "path": str(item.get("filename") or item.get("path") or ""),
            "content": content if len(content) <= max_chars else content[: max_chars // 2] + "\n...<middle omitted>...\n" + content[-max_chars // 2 :],
        })

    # If repository targeting already resolved one literal Boolean control,
    # self-validation must validate that resolved target rather than re-run
    # semantic discovery over a large file containing unrelated flags.
    resolved_feature_flag = {}
    for context_item in active.get("retrieved_value_context") or []:
        if not isinstance(context_item, dict):
            continue
        for matched in context_item.get("matched_files") or []:
            if not isinstance(matched, dict):
                continue
            feature_match = matched.get("feature_flag_match") or {}
            if not isinstance(feature_match, dict) or not feature_match.get("flag"):
                continue
            resolved_feature_flag = {
                "path": str(matched.get("path") or matched.get("filename") or "").strip(),
                "flag": str(feature_match.get("flag") or "").strip(),
                "line_number": int(feature_match.get("line_number") or feature_match.get("line") or 0),
                "current_value": str(feature_match.get("current_value") or "").strip().lower(),
                "new_value": str(feature_match.get("new_value") or "").strip().lower(),
                "description": str(feature_match.get("description") or feature_match.get("context") or "").strip(),
            }
            break
        if resolved_feature_flag:
            break

    # The selected Boolean is also stored in active repository evidence by the
    # backend target resolver. Prefer that authoritative live-verified selection
    # when retrieved_value_context did not carry the feature_flag_match forward.
    # This prevents self-validation from re-solving an already-solved target.
    if not resolved_feature_flag:
        try:
            selected = _selected_feature_flag_match_from_active_context()
        except Exception:
            selected = {}
        if isinstance(selected, dict) and selected.get("flag"):
            resolved_feature_flag = {
                "path": str(selected.get("path") or selected.get("filename") or "").strip(),
                "flag": str(selected.get("flag") or "").strip(),
                "line_number": int(selected.get("line_number") or selected.get("line") or 0),
                "current_value": str(selected.get("current_value") or "").strip().lower(),
                "new_value": str(selected.get("new_value") or "").strip().lower(),
                "description": str(selected.get("description") or selected.get("context") or "").strip(),
            }

    validation_request = {
        "task": "VALIDATE GENERATED TERRAFORM AGAINST CURRENT USER REQUEST. Return JSON verdict only.",
        "user_request": prompt,
        "expected_cloud": agent_result.get("cloud") or active.get("expected_cloud") or "",
        "expected_workflow": agent_result.get("workflow") or active.get("expected_workflow") or "",
        "generated_files": compact_files,
        "resolved_repository_target": resolved_feature_flag,
        "required_verdict": {"valid": True, "errors": [], "reason": "short explanation"},
        "rules": [
            "When resolved_repository_target is non-empty, the repository target has ALREADY been semantically selected and literally verified against live repository evidence. Do not rediscover or challenge that target because other flags/resources also exist in the full file.",
            "For a resolved_repository_target, validate only that the generated file implements the stated current_value -> new_value transition for that exact path/flag and does not introduce unrelated changes. Treat that exact target as authoritative backend evidence, not as a hypothesis to reinterpret.",
            "For a Boolean-only change, compare the target assignment directly. Do not fail merely because the compact validation excerpt omits unrelated middle sections of a large file.",
            "The generated files must implement the current user_request, not a previous or neighboring resource request.",
            "Reject output when the requested resource family/name is absent or a different resource family is generated.",
            "Reject stale paths/module sources that belong to a different request unless live repository wiring makes them strictly necessary.",
            "Check Terraform/HCL syntax plausibility: balanced blocks, valid Terraform constructs, no malformed placeholder syntax, no conflict markers.",
            "Check that module/resource references in the generated change are coherent with the stated request.",
            "Return valid JSON only; do not repair or generate Terraform in this validation call.",
        ],
    }
    try:
        LOGGER.info(
            "[TerrabotFlow] step=generated_output_validation actor=foundry target=%s flag=%s files=%s",
            resolved_feature_flag.get("path") or "unresolved",
            resolved_feature_flag.get("flag") or "unresolved",
            len(compact_files),
        )
        _validation_thread, validation_text = _TEAMS_MULTICLOUD_PREVIOUS_CALL_AGENT(
            None,
            json.dumps(validation_request, separators=(",", ":")),
        )
        verdict = extract_json_from_text(validation_text)
    except Exception as exc:
        # Model-level validation is defense-in-depth. Do not block a request only
        # because the validation service call itself failed; deterministic
        # backend guards still run immediately afterward.
        LOGGER.warning("Teams agent self-validation call failed; deterministic validation remains active: %s", exc)
        return

    if not isinstance(verdict, dict):
        raise ValueError("AGENT_SELF_VALIDATION_FAILED: validator returned a non-object verdict.")
    if verdict.get("valid") is True:
        LOGGER.info("[TerrabotFlow] step=generated_output_validation actor=foundry result=pass")
        return
    errors = verdict.get("errors") or []
    if isinstance(errors, str):
        errors = [errors]
    reason = str(verdict.get("reason") or "").strip()
    detail = "; ".join(str(item) for item in errors if str(item).strip()) or reason or "generated output did not match the current request"
    raise ValueError(f"AGENT_SELF_VALIDATION_FAILED: {detail}")
_prompt_guard_agent_self_validate = _prompt_guard_agent_self_validate_stage1


def commit_terraform_files_to_branch_for_teams_stage2(agent_result: dict, prompt: str, thread_id: str) -> dict:
    """Final Teams write gate: prompt relevance -> HCL -> agent verifier -> existing commit guards."""
    _prompt_guard_validate_semantic_relevance(agent_result, prompt)
    _prompt_guard_validate_terraform_shape(agent_result)
    _prompt_guard_agent_self_validate(agent_result, prompt)
    return _PROMPT_GUARD_PREVIOUS_COMMIT_TERRAFORM_FOR_TEAMS(agent_result, prompt, thread_id)
commit_terraform_files_to_branch_for_teams = commit_terraform_files_to_branch_for_teams_stage2


def _teams_select_aws_environment_consumer_file(
    environment_path: str,
    branch: str,
) -> tuple[str, str]:
    """Discover the AWS consumer file from live repository structure only.

    No filename receives special priority. A file is eligible because its live
    content demonstrates consumer module invocations. This removes the backend
    hardcoding that forced main.tf (and the complementary filename blacklist)
    and leaves environment/path conventions to repository evidence + Foundry
    instructions.
    """
    env = str(environment_path or "").strip().strip("/")
    if not env:
        raise ValueError("AWS environment path is required for consumer generation.")
    try:
        items = github_get_directory_listing(
            "aws", env, branch, repo_target="tf-devops", workflow="aws_module_consumer"
        ) or []
    except Exception as exc:
        raise ValueError(f"Could not read live tf-devops environment {env}@{branch}: {exc}") from exc

    candidates: list[tuple[int, int, str, str]] = []
    for item in items:
        if not isinstance(item, dict) or item.get("type") != "file":
            continue
        path = str(item.get("path") or "").strip()
        if not path.endswith(".tf"):
            continue
        try:
            content = github_get_file_content(
                "aws", path, branch, repo_target="tf-devops", workflow="aws_module_consumer"
            ) or ""
        except Exception:
            continue
        if not content:
            continue
        module_count = len(re.findall(r'(?m)^\s*module\s+"[^"]+"\s*\{', content))
        resource_count = len(re.findall(r'(?m)^\s*resource\s+"[^"]+"\s+"[^"]+"\s*\{', content))
        # Consumer evidence, not filename, determines ranking. Prefer files that
        # already contain module invocations; raw-resource files remain weaker
        # evidence but are not forbidden by a hardcoded name list.
        if module_count <= 0:
            continue
        candidates.append((module_count, resource_count, path, content))

    if not candidates:
        raise ValueError(
            f"No live Terraform file in {env} demonstrates an existing module-consumer pattern. "
            "Do not guess a backend filename; let repository evidence/agent workflow select or create the repo-aligned consumer target."
        )
    candidates.sort(key=lambda row: (-row[0], row[1], row[2]))
    _modules, _resources, path, content = candidates[0]
    return path, content

# The new-module consumer materializer also follows the agent's repository-
# inferred target instead of selecting a backend-owned filename. The backend
# still owns full-file preservation by fetching that exact generated path live.
_PROMPT_GUARD_PREVIOUS_AWS_MATERIALIZER = _teams_aws_materialize_repo_aligned_consumer


def _teams_aws_materialize_repo_aligned_consumer_stage2(
    agent_result: dict,
    proposed_module_path: str,
    environment_path: str,
    context_pack: dict,
) -> dict:
    updated = dict(agent_result or {})
    files = [dict(item) for item in updated.get("files") or [] if isinstance(item, dict)]
    module_path = _sanitize_aws_module_rel_path(proposed_module_path)
    generated_consumer_path, new_block = _teams_aws_extract_new_consumer_block(files, module_path)
    if not new_block:
        raise ValueError(
            f"No consumer module block references the new module {AWS_MODULES_ROOT}/{module_path}."
        )

    env = str(environment_path or "").strip().strip("/")
    target_path = normalize_tf_relative_path(generated_consumer_path or "")
    if not target_path or not target_path.startswith(env.rstrip("/") + "/"):
        raise ValueError(
            f"Generated AWS consumer target {target_path or '<empty>'} is outside the resolved environment {env}."
        )

    context_pack = dict(context_pack or {})
    repo_profile = dict(context_pack.get("repo_profile") or {})
    branch = str(repo_profile.get("source_branch") or "").strip() or _aws_module_catalog_branch()
    try:
        live_content = github_get_file_content(
            "aws",
            target_path,
            branch,
            repo_target="tf-devops",
            workflow="aws_module_creation",
        )
    except Exception as exc:
        LOGGER.warning(
            "Could not read agent-selected AWS consumer target %s@%s: %s",
            target_path,
            branch,
            exc,
        )
        live_content = None

    expected_source = build_aws_local_module_source(module_path, target_path.rsplit("/", 1)[0])
    source_match = re.search(r'(?m)^\s*source\s*=\s*"([^"]+)"', new_block)
    if not source_match or source_match.group(1).replace("\\", "/").rstrip("/") != expected_source:
        raise ValueError(
            f'Generated consumer for {AWS_MODULES_ROOT}/{module_path} must use source = "{expected_source}".'
        )

    if live_content is not None:
        live_content = str(live_content).replace("\r\n", "\n")
        for block in _extract_top_level_tf_blocks(live_content):
            block_text = str(block.get("block") or "")
            existing_source = re.search(r'(?m)^\s*source\s*=\s*"([^"]+)"', block_text)
            if existing_source and normalize_aws_module_source_path(existing_source.group(1)) == module_path:
                raise ValueError(
                    f"The target environment already contains a consumer for {AWS_MODULES_ROOT}/{module_path}; refusing to duplicate it."
                )
        materialized = live_content.rstrip() + "\n\n" + new_block.rstrip() + "\n"
    else:
        # A genuinely new agent-selected consumer file is allowed only inside
        # the resolved environment. Repository instructions/evidence, not a
        # backend filename table, decide that placement.
        materialized = new_block.rstrip() + "\n"

    module_files = []
    for item in files:
        filename = normalize_tf_relative_path(item.get("filename") or item.get("path") or "")
        if filename.startswith(f"{AWS_MODULES_ROOT}/{module_path}/"):
            module_files.append(item)
    module_files.append({"filename": target_path, "content": materialized})
    updated["files"] = module_files
    return updated
_teams_aws_materialize_repo_aligned_consumer = _teams_aws_materialize_repo_aligned_consumer_stage2

# =============================================================================
# Teams vague-resource semantic resolution + user-friendly disambiguation
# =============================================================================
# Final override: ordinary infra prompts may use colloquial/approximate resource
# wording.  The backend expands the live environment evidence first, ranks real
# Terraform targets semantically, auto-selects a unique strong match, and only
# asks the user when multiple materially distinct live-repo matches remain.

_TEAMS_VAGUE_PREVIOUS_BUILD_MODIFICATION_CONTEXT = build_backend_existing_infra_modification_context
_TEAMS_VAGUE_GENERIC_WORDS = {
    "setup", "configuration", "config", "management", "manager", "service",
    "feature", "resource", "resources", "module", "modules", "terraform",
    "infra", "infrastructure", "setting", "settings", "system", "component",
    "aws", "azure", "please", "the", "a", "an", "for", "from", "in", "on",
    "to", "of", "and", "or", "with", "using", "use", "existing", "current",
    "enable", "disable", "create", "add", "update", "modify", "change", "set",
    "remove", "delete", "fix", "turn", "off", "on",
}


def _teams_semantic_tokens(value: str) -> list[str]:
    text = str(value or "").lower().replace("-", "_").replace("/", "_")
    raw = re.findall(r"[a-z0-9]+", text)
    result: list[str] = []
    environment_words = {
        part
        for env_name in (set(TEAMS_AWS_ENVIRONMENT_HINTS) | set(TEAMS_AZURE_ENVIRONMENT_HINTS))
        for part in re.findall(r"[a-z0-9]+", str(env_name).lower())
    }
    for token in raw:
        if len(token) < 3 or token in _TEAMS_VAGUE_GENERIC_WORDS or token in environment_words:
            continue
        # Lightweight morphological normalization; repository identifiers often
        # differ only by plural/gerund suffixes.
        normalized = token
        if len(normalized) > 5 and normalized.endswith("ing"):
            normalized = normalized[:-3]
        elif len(normalized) > 4 and normalized.endswith("ies"):
            normalized = normalized[:-3] + "y"
        elif len(normalized) > 4 and normalized.endswith("s") and not normalized.endswith("ss"):
            normalized = normalized[:-1]
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _teams_candidate_identifiers(item: dict) -> list[str]:
    values: list[str] = []
    path = str(item.get("path") or item.get("filename") or "")
    if path:
        values.extend(re.findall(r"[A-Za-z0-9_-]+", path))
    for block in item.get("matched_blocks") or []:
        if isinstance(block, dict):
            header = str(block.get("header") or "")
            if header:
                values.append(header)
    content = str(item.get("content") or "")
    # Comments often carry the human-facing feature name even when the HCL
    # identifier is abbreviated. Include short comment text in semantic matching.
    for comment in re.findall(r"(?m)^\s*(?:#|//)\s*([^\n]{3,160})", content):
        values.append(comment)
    for pattern in (
        r'(?m)^\s*(?:module|resource|data)\s+"([^"]+)"(?:\s+"([^"]+)")?',
        r'(?m)^\s*variable\s+"([^"]+)"',
        r'(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=',
    ):
        for match in re.finditer(pattern, content):
            values.extend(group for group in match.groups() if group)
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))[:120]


def _teams_describe_tf_file_contents(item: dict) -> str:
    """One-line, evidence-based description of what a .tf file declares.

    Used so the Teams infrastructure-target picker tells the user what is
    actually inside each candidate file (not just its path), and so a file
    whose declared resources match the request's wording (for example a WAF
    resource for a "disable ... waf ..." request) is identifiable at a
    glance instead of requiring the user to open every candidate.
    """
    content = str(item.get("content") or "")
    if not content:
        blocks = [
            str(block.get("header") or "").strip()
            for block in (item.get("matched_blocks") or [])
            if isinstance(block, dict) and str(block.get("header") or "").strip()
        ]
        return ("Matches: " + ", ".join(dict.fromkeys(blocks[:4]))) if blocks else ""

    declarations: list[str] = []
    for match in re.finditer(
        r'(?m)^\s*(resource|data|module)\s+"([^"]+)"(?:\s+"([^"]+)")?',
        content,
    ):
        kind, type_or_name, name = match.groups()
        label = f"{type_or_name}.{name}" if name else type_or_name
        declarations.append(f"{kind} {label}")
        if len(declarations) >= 6:
            break
    if declarations:
        return "Defines: " + ", ".join(dict.fromkeys(declarations))

    variables = re.findall(r'(?m)^\s*variable\s+"([^"]+)"', content)
    if variables:
        summary = "Declares variables: " + ", ".join(dict.fromkeys(variables))
        return summary[:220]

    return ""


def _teams_semantic_candidate_score(prompt: str, item: dict) -> tuple[int, list[str]]:
    prompt_tokens = _teams_semantic_tokens(prompt)
    if not prompt_tokens:
        return 0, []
    identifiers = _teams_candidate_identifiers(item)
    identifier_tokens: set[str] = set()
    for identifier in identifiers:
        identifier_tokens.update(_teams_semantic_tokens(identifier))

    matched: list[str] = []
    score = 0
    for token in prompt_tokens:
        if token in identifier_tokens:
            score += 220
            matched.append(token)
            continue
        # Prefix equivalence handles patch/patching, auth/authentication-like
        # repository labels without introducing resource-specific hardcoding.
        if any(
            len(token) >= 4 and len(candidate) >= 4
            and (candidate.startswith(token) or token.startswith(candidate))
            for candidate in identifier_tokens
        ):
            score += 120
            matched.append(token)

    path = str(item.get("path") or "").lower()
    if any(token in path.replace("-", "_") for token in matched):
        score += 40
    if item.get("matched_blocks"):
        score += min(60, 15 * len(item.get("matched_blocks") or []))
    return score, list(dict.fromkeys(matched))


def _teams_expand_modification_candidates_from_environment(
    context: dict,
    prompt: str,
    cloud: str,
    workflow: str,
) -> dict:
    """Add live target-environment files before deciding that nothing matches."""
    active = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    if not active.get("active"):
        return context
    try:
        normalized_cloud = normalize_cloud(cloud)
        repo_target = normalize_repo_target(normalized_cloud, workflow=workflow)
        branch = str(context.get("context_ref") or "").strip() or _teams_remote_context_branch(
            normalized_cloud, repo_target, workflow
        )
        evidence, _value_paths, _debug = _teams_environment_folder_evidence(
            prompt, normalized_cloud, repo_target, workflow, branch
        )
    except Exception as exc:
        LOGGER.warning("Vague-target environment expansion failed: %s", exc)
        return context

    existing = list(context.get("matched_files") or [])
    by_path = {
        str(item.get("path") or "").strip(): dict(item)
        for item in existing if isinstance(item, dict) and str(item.get("path") or "").strip()
    }
    prompt_terms = _teams_safe_extended_modification_terms(prompt)
    for entry in evidence or []:
        path = str((entry or {}).get("path") or "").strip()
        content = str((entry or {}).get("content") or "")
        if not path or not content or not path.endswith((".tf", ".tfvars")):
            continue
        candidate = by_path.get(path) or {
            "path": path,
            "filename": path.rsplit("/", 1)[-1],
            "content": content,
            "matched_blocks": _matched_blocks_for_prompt(content, prompt_terms),
            "reason": "live target-environment context scan",
        }
        semantic_score, semantic_terms = _teams_semantic_candidate_score(prompt, candidate)
        if semantic_score <= 0:
            continue
        candidate["semantic_score"] = semantic_score
        candidate["semantic_terms"] = semantic_terms
        by_path[path] = candidate

    context = dict(context or {})
    context["matched_files"] = list(by_path.values())
    context["matched_file_paths"] = [item.get("path") for item in context["matched_files"] if item.get("path")]
    return context


def _teams_semantic_resolve_modification_context(
    context: dict,
    prompt: str,
    cloud: str,
    workflow: str,
) -> dict:
    if _backend_existing_infra_context_is_selected(context):
        return context
    candidates = list(context.get("matched_files") or [])
    if not candidates:
        return context

    ranked: list[tuple[int, int, dict]] = []
    for index, item in enumerate(candidates):
        score, matched_terms = _teams_semantic_candidate_score(prompt, item)
        item = dict(item)
        item["semantic_score"] = score
        item["semantic_terms"] = matched_terms
        ranked.append((score, index, item))
    ranked.sort(key=lambda value: (-value[0], str(value[2].get("path") or "")))
    candidates = [item for _score, _index, item in ranked if _score > 0]
    if not candidates:
        return context

    best_score = ranked[0][0]
    second_score = ranked[1][0] if len(ranked) > 1 else 0
    best = ranked[0][2]
    # A unique discriminative semantic match is a repository decision, not a
    # user question.  Require one meaningful prompt token and a clear margin.
    unique_strong = bool(
        best_score >= 220
        and best.get("semantic_terms")
        and (len(ranked) == 1 or best_score >= second_score + 120 or best_score >= second_score * 1.7)
    )
    if unique_strong:
        selected_context = build_selected_infra_modification_context(
            {
                "original_prompt": prompt,
                "cloud": cloud,
                "workflow": workflow,
                "existing_infra_context": {**context, "matched_files": [best]},
            },
            0,
        )
        selected_context["semantic_resolution"] = {
            "decision": "auto_selected_unique_live_repo_match",
            "matched_terms": best.get("semantic_terms") or [],
            "score": best_score,
            "path": best.get("path") or "",
        }
        selected_context["analysis"] = "\n".join(filter(None, [
            str(context.get("analysis") or "").strip(),
            f"Semantic target: `{best.get('path') or ''}` matched the user's approximate wording via {', '.join(best.get('semantic_terms') or [])}.",
            "Decision: unique repository-supported match; Terrabot selected it automatically instead of asking for an implementation path/module name.",
        ]))
        return selected_context

    # Multiple meaningful matches remain: retain a short, ranked set for the
    # user-facing picker.  This is a genuine structural ambiguity.
    result = dict(context)
    result["selection_state"] = "candidate_selection_required"
    result["matched_files"] = candidates[:6]
    result["matched_file_paths"] = [item.get("path") for item in candidates[:6] if item.get("path")]
    result["semantic_resolution"] = {
        "decision": "user_choice_required_multiple_live_repo_matches",
        "prompt_terms": _teams_semantic_tokens(prompt),
    }
    return result


def build_backend_existing_infra_modification_context_stage2(
    prompt: str,
    thread_id: str,
    cloud: str,
    workflow: str,
    retrieved_value_context: list | None = None,
) -> dict:
    """Final Teams resolver: live-context expansion -> semantic selection -> picker."""
    context = _TEAMS_VAGUE_PREVIOUS_BUILD_MODIFICATION_CONTEXT(
        prompt,
        thread_id,
        cloud,
        workflow,
        retrieved_value_context=retrieved_value_context,
    )
    active = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    if not active.get("active"):
        return context
    if _backend_existing_infra_context_is_selected(context):
        return context
    context = _teams_expand_modification_candidates_from_environment(
        context, prompt, cloud, workflow
    )
    return _teams_semantic_resolve_modification_context(
        context, prompt, cloud, workflow
    )
build_backend_existing_infra_modification_context = build_backend_existing_infra_modification_context_stage2


def _teams_candidate_friendly_label(item: dict) -> str:
    blocks = [
        str(block.get("header") or "").strip()
        for block in (item.get("matched_blocks") or [])
        if isinstance(block, dict) and str(block.get("header") or "").strip()
    ]
    if blocks:
        return blocks[0]
    identifiers = _teams_candidate_identifiers(item)
    return identifiers[0] if identifiers else str(item.get("filename") or "Terraform target")


def build_infra_modification_selection_reply_stage2(existing_infra_context: dict) -> str:
    """Clean Teams clarification that always includes the actual choices."""
    candidates = list(existing_infra_context.get("matched_files") or [])[:6]
    if not candidates:
        return (
            "I couldn't find a repository-backed Terraform target for that resource wording. "
            "You can reply with a more specific resource name; you do not need to provide a file path or module name."
        )
    lines = [
        "I found a few similar infrastructure targets in the live repository. Which one should I use?",
        "",
    ]
    for index, item in enumerate(candidates, start=1):
        label = _teams_candidate_friendly_label(item)
        path = str(item.get("path") or "").strip()
        terms = ", ".join(item.get("semantic_terms") or [])
        suffix = f" — matched: {terms}" if terms else ""
        lines.append(f"{index}. **{label}** — `{path}`{suffix}")
    lines.extend([
        "",
        "Reply with the number, the module/resource name, or the path. After you choose, Terrabot will generate the change and run the existing Terraform validation/self-check flow.",
    ])
    return "\n".join(lines)
build_infra_modification_selection_reply = build_infra_modification_selection_reply_stage2

# =============================================================================
# 2026-08-13 Teams AWS selected-module materialization hardening
# =============================================================================
# This final override fixes the selected-module failure mode where Foundry was
# asked to reproduce a very large environment main.tf, the independent validator
# then judged all pre-existing resources in that file as part of the new change,
# and self-correction repeatedly failed the append-prefix check.  Repository
# truth stays in live GitHub; Foundry now supplies the selected module consumer
# block and the backend deterministically appends that block to the authoritative
# live consumer file before validation/commit.

_AWS_SELECTED_CONTEXT_PREVIOUS = _aws_selected_module_context_with_contents
_AWS_SELECTED_COERCE_PREVIOUS = _teams_coerce_agent_payload
_AWS_SELECTED_SELF_VALIDATE_PREVIOUS = _prompt_guard_agent_self_validate
_AWS_SELECTED_HANDLE_PREVIOUS = handle_teams_chat_request


def _aws_selected_module_context_with_contents(
    selected_match: dict,
    discovery: dict,
    environment_path: str,
) -> tuple[dict, dict]:
    """Enrich selected-module generation with complete live environment context.

    The base implementation already reloads every .tf file under the selected
    module and the complete target consumer.  This override additionally sends
    every Terraform/value file in the target environment plus full existing
    consumer examples for the selected module when they are readable.  This
    gives Foundry concrete values and wiring examples instead of placeholders.
    """
    verified, target_context = _AWS_SELECTED_CONTEXT_PREVIOUS(
        selected_match,
        discovery,
        environment_path,
    )
    verified = dict(verified or {})
    target_context = dict(target_context or {})

    env = str(environment_path or verified.get("environment_path") or "").strip().strip("/")
    flow_context = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    branch = ""
    if _teams_truthy(flow_context.get("reuse_branch")):
        candidate = str(flow_context.get("existing_branch") or "").strip()
        if candidate:
            try:
                if github_branch_exists(
                    "aws", candidate, repo_target="tf-devops", workflow="aws_module_consumer"
                ):
                    branch = candidate
            except Exception:
                branch = ""
    if not branch and _teams_truthy(flow_context.get("force_new_branch")):
        try:
            branch = github_resolve_base_branch_for_cloud(
                "aws", repo_target="tf-devops", workflow="aws_module_consumer"
            )
        except Exception:
            branch = ""
    if not branch:
        branch = str(target_context.get("context_ref") or discovery.get("resolved_ref") or "").strip()
    if not branch:
        branch = _teams_remote_context_branch(
            "aws", repo_target="tf-devops", workflow="aws_module_consumer"
        )

    # Re-read the selected module and target consumer on the exact branch mode
    # chosen by the user.  Discovery metadata may have been built on another ref;
    # it must never override the branch choice.
    module_root = str(verified.get("verified_module_root") or "").strip()
    if not module_root:
        module_rel = _sanitize_aws_module_rel_path(verified.get("module_path") or verified.get("verified_module_path") or "")
        module_root = f"{AWS_MODULES_ROOT}/{module_rel}" if module_rel else ""
    selected_module_files: list[dict] = []
    selected_module_paths: list[str] = []
    if module_root:
        def walk_selected_module(path: str) -> None:
            try:
                items = github_get_directory_listing(
                    "aws", path, branch, repo_target="tf-devops", workflow="aws_module_consumer"
                ) or []
            except Exception:
                return
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_path = str(item.get("path") or "").strip()
                if item.get("type") == "dir":
                    walk_selected_module(item_path)
                elif item.get("type") == "file" and item_path.endswith(".tf"):
                    try:
                        content = github_get_file_content(
                            "aws", item_path, branch, repo_target="tf-devops", workflow="aws_module_consumer"
                        )
                    except Exception:
                        content = None
                    if content is not None:
                        selected_module_paths.append(item_path)
                        selected_module_files.append({"path": item_path, "content": content})
        walk_selected_module(module_root)
    if selected_module_files:
        verified["tf_files"] = list(dict.fromkeys(selected_module_paths))
        verified["module_files"] = selected_module_files
        verified["all_tf_file_contents"] = selected_module_files
        verified["resolved_ref"] = branch

    target_path = str(target_context.get("target_file") or target_context.get("path") or "").strip()
    if target_path:
        try:
            live_target = github_get_file_content(
                "aws", target_path, branch, repo_target="tf-devops", workflow="aws_module_consumer"
            )
        except Exception:
            live_target = None
        if live_target is not None:
            target_context["content"] = live_target
            target_context["context_ref"] = branch

    environment_files: list[dict] = []
    seen_env: set[str] = set()

    def walk_environment(path: str) -> None:
        try:
            items = github_get_directory_listing(
                "aws", path, branch,
                repo_target="tf-devops", workflow="aws_module_consumer",
            ) or []
        except Exception as exc:
            LOGGER.warning("Could not enrich AWS selected-module environment context %s@%s: %s", path, branch, exc)
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            item_path = str(item.get("path") or "").strip()
            if not item_path:
                continue
            if item.get("type") == "dir":
                walk_environment(item_path)
                continue
            if item.get("type") != "file" or not item_path.endswith((".tf", ".tfvars")):
                continue
            if item_path in seen_env:
                continue
            try:
                content = github_get_file_content(
                    "aws", item_path, branch,
                    repo_target="tf-devops", workflow="aws_module_consumer",
                )
            except Exception:
                content = None
            if content is None:
                continue
            seen_env.add(item_path)
            environment_files.append({
                "path": item_path,
                "content": content,
                "source": "live_github_target_environment_file",
                "environment_path": env,
                "resolved_ref": branch,
            })

    if env:
        walk_environment(env)

    # Expand any module consumer examples already discovered by the backend to
    # their complete live file contents.  The selected module's own examples are
    # the strongest source for required values and expression style.
    example_files: list[dict] = []
    seen_examples: set[str] = set()
    for example in verified.get("consumer_examples") or []:
        if not isinstance(example, dict):
            continue
        path = str(example.get("path") or example.get("filename") or "").strip()
        if not path or path in seen_examples:
            continue
        example_ref = str(example.get("resolved_ref") or branch).strip() or branch
        try:
            content = github_get_file_content(
                "aws", path, example_ref,
                repo_target="tf-devops", workflow="aws_module_consumer",
            )
        except Exception:
            content = None
        if content is None:
            continue
        seen_examples.add(path)
        example_files.append({
            "path": path,
            "content": content,
            "source": "live_github_selected_module_consumer_example",
            "resolved_ref": example_ref,
        })

    verified["target_environment_files"] = environment_files
    verified["consumer_example_files"] = example_files
    verified.setdefault("instructions", [])
    verified["instructions"] = list(verified.get("instructions") or []) + [
        "Use target_environment_files to reuse values/references already present in the target environment before emitting any __FILL__ token.",
        "Use consumer_example_files as the strongest consumer wiring/value pattern for this selected module.",
        "Generate one new sibling module invocation only; the backend will append it to the authoritative live target file.",
    ]

    target_context["environment_files"] = environment_files
    target_context["selected_module_consumer_examples"] = example_files
    target_context["materialization_mode"] = "backend_append_selected_module_block"
    target_context["instruction"] = (
        "Return a consumer file containing the new selected-module invocation. "
        "The backend extracts that invocation and appends it to the complete live target file, preserving all existing content exactly."
    )
    return verified, target_context


def _teams_selected_module_block_from_payload(payload: dict, context: dict) -> tuple[str, str, str]:
    """Return (target_path, existing_content, selected_module_block).

    Only a top-level module block whose source exactly equals the backend-selected
    module source is accepted.  Unrelated generated resources/blocks are ignored
    rather than being allowed to contaminate the target environment file.
    """
    selected_generation = next((
        item for item in context.get("retrieved_value_context") or []
        if isinstance(item, dict)
        and item.get("source") == "backend_aws_selected_module_generation_context"
    ), {})
    if not selected_generation:
        return "", "", ""

    target_file = str(selected_generation.get("target_file") or selected_generation.get("path") or "").strip()
    existing_content = str(selected_generation.get("content") or "")
    confirmed = _get_confirmed_aws_module_selection(context.get("retrieved_value_context") or [])
    selected_source = str(
        confirmed.get("module_source")
        or selected_generation.get("module_source")
        or ""
    ).strip()
    if not target_file or not selected_source:
        raise ValueError("AWS_SELECTED_MODULE_CONTEXT_INCOMPLETE: target file or selected module source is missing.")

    matches: list[str] = []
    for item in payload.get("files") or []:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "")
        if not content.strip():
            continue
        for block_info in _extract_top_level_tf_blocks(content):
            header = str(block_info.get("header") or "")
            block = str(block_info.get("block") or "")
            if not header.startswith("module ") or not block:
                continue
            if _teams_module_source_literal(block) == selected_source:
                matches.append(block.rstrip())

    # Deduplicate byte-identical copies (an agent may echo the same block in a
    # full-file response and a secondary field during repair).
    matches = list(dict.fromkeys(matches))
    if not matches:
        raise ValueError(
            "AWS_SELECTED_MODULE_CONSUMER_MISSING: Foundry did not return a module block using the exact selected source "
            f"{selected_source}."
        )
    if len(matches) > 1:
        raise ValueError(
            "AWS_SELECTED_MODULE_MULTIPLE_CONSUMERS: Foundry returned more than one new module block for the selected source; exactly one is allowed."
        )

    new_block = matches[0]
    header_match = re.match(r'\s*module\s+"([^"]+)"', new_block)
    if header_match:
        label = header_match.group(1)
        if re.search(rf'(?m)^\s*module\s+"{re.escape(label)}"\s*\{{', existing_content):
            raise ValueError(
                f"AWS_SELECTED_MODULE_DUPLICATE_LABEL: target file already contains module \"{label}\"; generate a unique sibling label."
            )
    return target_file, existing_content, new_block


def _teams_selected_module_canonical_payload(payload: dict, context: dict) -> dict:
    target_file, existing_content, new_block = _teams_selected_module_block_from_payload(payload, context)
    if not target_file:
        return payload

    final_content = existing_content.rstrip("\n") + "\n\n" + new_block.rstrip() + "\n"
    result = dict(payload or {})
    result["mode"] = "infra"
    result["cloud"] = "aws"
    result["workflow"] = "aws_module_consumer"
    result["repo_target"] = "tf-devops"
    result["files"] = [{"filename": target_file, "content": final_content}]
    result["questions"] = []
    analysis = str(result.get("analysis") or "").strip()
    materialization_note = (
        f"Backend materialization: extracted the selected-module consumer block and appended it to live `{target_file}`; existing file content was not regenerated."
    )
    result["analysis"] = "\n".join(filter(None, [analysis, materialization_note]))
    return result


def _teams_coerce_agent_payload(agent_text: str, context: dict) -> tuple[dict, dict]:
    """Canonicalize selected-module output before the legacy full-file guard."""
    selected_generation = next((
        item for item in context.get("retrieved_value_context") or []
        if isinstance(item, dict)
        and item.get("source") == "backend_aws_selected_module_generation_context"
    ), {})
    if selected_generation:
        raw = extract_json_from_text(agent_text)
        if not isinstance(raw, dict):
            raise ValueError("Teams agent response was not a JSON object.")
        canonical = _teams_selected_module_canonical_payload(raw, context)
        return _AWS_SELECTED_COERCE_PREVIOUS(json.dumps(canonical), context)
    return _AWS_SELECTED_COERCE_PREVIOUS(agent_text, context)


def _prompt_guard_agent_self_validate(agent_result: dict, prompt: str) -> None:
    """Validate only the selected-module delta, never unrelated live main.tf code."""
    active = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    selected_generation = next((
        item for item in active.get("retrieved_value_context") or []
        if isinstance(item, dict)
        and item.get("source") == "backend_aws_selected_module_generation_context"
    ), {})
    if not selected_generation:
        return _AWS_SELECTED_SELF_VALIDATE_PREVIOUS(agent_result, prompt)
    if str(os.getenv("TERRABOT_TEAMS_AGENT_SELF_VALIDATE", "true")).strip().lower() in {"0", "false", "no"}:
        return

    target = str(selected_generation.get("target_file") or selected_generation.get("path") or "").strip()
    existing = str(selected_generation.get("content") or "")
    confirmed = _get_confirmed_aws_module_selection(active.get("retrieved_value_context") or [])
    selected_source = str(confirmed.get("module_source") or selected_generation.get("module_source") or "").strip()
    delta_files: list[dict] = []
    for item in agent_result.get("files") or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("filename") or item.get("path") or "").strip()
        content = str(item.get("content") or "")
        if path != target:
            continue
        prefix = existing.rstrip("\n")
        delta = content[len(prefix):] if prefix and content.startswith(prefix) else content
        delta_files.append({"path": path, "content": delta.strip()})

    if len(delta_files) != 1:
        raise ValueError(
            "AGENT_SELF_VALIDATION_FAILED: selected-module workflow must materialize exactly one target consumer delta."
        )

    # Deterministic checks run before the model verdict so a validator cannot
    # confuse unrelated pre-existing resources with the requested change.
    delta = delta_files[0]["content"]
    if selected_source and selected_source not in delta:
        raise ValueError(
            f"AGENT_SELF_VALIDATION_FAILED: selected module source {selected_source} is absent from the appended consumer delta."
        )
    if len(re.findall(r'(?m)^\s*module\s+"[^"]+"\s*\{', delta)) != 1:
        raise ValueError(
            "AGENT_SELF_VALIDATION_FAILED: appended consumer delta must contain exactly one module block."
        )
    _validate_hcl_content_complete(target, delta)

    validation_request = {
        "task": "VALIDATE GENERATED TERRAFORM AGAINST CURRENT USER REQUEST. Return JSON verdict only.",
        "user_request": prompt,
        "expected_cloud": "aws",
        "expected_workflow": "aws_module_consumer",
        "selected_module_source": selected_source,
        "generated_files": delta_files,
        "validation_scope": "ONLY the appended consumer delta below is new. The existing target environment file is intentionally omitted because its unrelated resources are pre-existing repository state.",
        "required_verdict": {"valid": True, "errors": [], "reason": "short explanation"},
        "rules": [
            "Judge only generated_files.content as the new change; do not require or discuss unrelated pre-existing environment resources.",
            "The delta must implement the current user_request using selected_module_source.",
            "Reject a different resource family, wrong selected module source, malformed HCL, conflict markers, or more than one new module block.",
            "Do not reject because the target environment may already contain other resource families; those are not included in this delta.",
            "Return valid JSON only; do not generate replacement Terraform.",
        ],
    }
    try:
        _validation_thread, validation_text = _TEAMS_MULTICLOUD_PREVIOUS_CALL_AGENT(
            None, json.dumps(validation_request, separators=(",", ":"))
        )
        verdict = extract_json_from_text(validation_text)
    except Exception as exc:
        LOGGER.warning("Teams selected-module self-validation call failed; deterministic validation remains active: %s", exc)
        return
    if isinstance(verdict, dict) and verdict.get("valid") is True:
        return
    if not isinstance(verdict, dict):
        LOGGER.warning(
            "Selected-module model validator returned a non-object verdict; deterministic selected-source/HCL checks passed, so commit validation continues."
        )
        return
    errors = verdict.get("errors") or []
    if isinstance(errors, str):
        errors = [errors]
    reason = str(verdict.get("reason") or "").strip()
    detail = "; ".join(str(item) for item in errors if str(item).strip()) or reason or "selected consumer delta did not match the current request"
    # For this explicit post-selection workflow the backend has already proved:
    # exact selected source, exactly one appended module block, HCL completeness,
    # current-request semantic relevance, and byte-preserving materialization.
    # Treat the independent model verdict as advisory here so a false negative
    # cannot trigger five identical full-file repair attempts.
    LOGGER.warning(
        "Selected-module model validator rejected a deterministically valid delta; continuing with backend guards instead of entering a repair loop: %s",
        detail,
    )
    _teams_diag_log(
        "selected_module_model_validation_advisory_rejection",
        level="warning",
        thread=str(active.get("thread_id") or ""),
        error=detail[:240],
    )
    return


def _teams_find_reusable_aws_branch_for_request(state: dict, request_data: dict) -> str:
    """Resolve the current AWS Terrabot branch even when UI state is stale."""
    explicit = str(state.get("branch") or request_data.get("existing_branch") or "").strip()
    state_cloud = safe_normalize_cloud(
        state.get("resolved_branch_cloud") or state.get("cloud") or request_data.get("cloud") or request_data.get("requested_cloud")
    )
    if explicit and state_cloud == "aws":
        try:
            if github_branch_exists("aws", explicit, repo_target="tf-devops", workflow="aws_module_consumer"):
                return explicit
        except Exception:
            pass

    workflow_thread = str(
        state.get("workflow_thread_id")
        or state.get("foundry_conversation_id")
        or request_data.get("thread_id")
        or ""
    ).strip()
    if not workflow_thread:
        return ""
    try:
        restore_teams_workflow_state(workflow_thread)
    except Exception:
        pass
    try:
        aws_state = (recover_thread_pr_state(workflow_thread) or {}).get("aws") or {}
    except Exception:
        aws_state = {}
    branch = str(aws_state.get("branch") or "").strip()
    if not branch:
        return ""
    try:
        if github_branch_exists("aws", branch, repo_target="tf-devops", workflow="aws_module_consumer"):
            return branch
    except Exception:
        return ""
    return ""


def _handle_teams_chat_request_with_aws_branch_preflight(data: dict):
    """Ask branch choice before AWS module discovery/selection when reusable state exists."""
    request_data = dict(data or {})
    prompt = str(request_data.get("prompt") or request_data.get("message") or "").strip()
    action = str(request_data.get("action") or "").strip().lower()
    teams_conversation_id = str(
        request_data.get("teams_conversation_id")
        or request_data.get("conversation_id")
        or ""
    ).strip()
    state = load_teams_conversation_state(teams_conversation_id) if teams_conversation_id else {}
    stage = str(state.get("stage") or "").strip()

    # This preflight is deliberately narrow: only a fresh AWS resource-creation
    # request that will enter module discovery. Protocol replies (branch/module/
    # target/Jira/PR) continue through the existing state machine untouched.
    is_fresh_aws_creation = bool(
        not action
        and prompt
        and stage not in {
            "awaiting_branch_reuse_decision",
            "aws_module_selection",
            "infra_modification_target_selection",
            "awaiting_jira",
            "awaiting_pr_decision",
        }
        and not _teams_message_is_protocol_control(request_data, state, prompt)
        and infer_cloud_from_prompt(prompt) == "aws"
        and _teams_is_existing_invocation_creation(prompt)
        and not _teams_truthy(request_data.get("pending_branch_choice_resolved"))
        and not _teams_truthy(state.get("branch_choice_resolved_for_request"))
        and not _teams_truthy(request_data.get("reuse_branch"))
        and not _teams_truthy(request_data.get("force_new_branch"))
    )
    if is_fresh_aws_creation:
        reusable_branch = _teams_find_reusable_aws_branch_for_request(state, request_data)
        if reusable_branch:
            patch = {
                "stage": "awaiting_branch_reuse_decision",
                "pending_follow_up_prompt": prompt,
                "pending_follow_up_branch": reusable_branch,
                "pending_follow_up_cloud": "aws",
                "pending_follow_up_ticket_link": request_data.get("ticket_link") or state.get("ticket_link") or "",
                "pending_follow_up_ticket_number": request_data.get("jira_ticket") or state.get("ticket_number") or "",
                "pending_follow_up_ticket_title": request_data.get("ticket_title") or state.get("ticket_title") or "",
            }
            if teams_conversation_id:
                _teams_save_ui_state(teams_conversation_id, patch)
            return {
                "ok": False,
                "mode": "branch_choice_required",
                "decision_state": "awaiting_branch_reuse_decision",
                "reply": (
                    f"Choose the AWS branch before module discovery. Existing Terrabot branch: `{reusable_branch}`. "
                    "Reply `yes` to reuse it, or `no` to create a new `terrabot/` branch from the latest remote base."
                ),
                "thread_id": str(state.get("workflow_thread_id") or state.get("foundry_conversation_id") or request_data.get("thread_id") or ""),
                "branch": reusable_branch,
                "branch_url": state.get("branch_url") or "",
                "compare_url": state.get("compare_url") or "",
                "cloud": "aws",
                "state_patch": patch,
            }, 400

    result, status_code = _AWS_SELECTED_HANDLE_PREVIOUS(request_data)
    result = dict(result or {})

    # If this turn was the user's branch yes/no and the next backend stage is
    # AWS module selection, persist the resolved branch strategy across that
    # picker.  Without this hand-off teams_bot.py sees aws_module_selection but
    # loses the earlier branch decision, so the option reply can silently fall
    # back to a new/default branch.
    if (
        str(state.get("stage") or "").strip() == "awaiting_branch_reuse_decision"
        and str(result.get("decision_state") or "").strip() == "aws_module_selection"
    ):
        choice = str(request_data.get("branch_choice") or "").strip().lower()
        if choice not in {"reuse", "new"}:
            choice = _teams_branch_choice_from_reply(prompt)
        if choice in {"reuse", "new"}:
            existing_branch = str(
                state.get("pending_follow_up_branch")
                or state.get("branch")
                or request_data.get("existing_branch")
                or ""
            ).strip()
            patch = dict(result.get("state_patch") or {})
            patch.update({
                "stage": "aws_module_selection",
                "branch_choice_resolved_for_request": True,
                "resolved_branch_choice": choice,
                "resolved_reuse_branch": choice == "reuse",
                "resolved_force_new_branch": choice == "new",
                "resolved_existing_branch": existing_branch if choice == "reuse" else "",
                "resolved_branch_cloud": "aws",
            })
            result["state_patch"] = patch
            if teams_conversation_id:
                _teams_save_ui_state(teams_conversation_id, patch)

    return result, status_code
handle_teams_chat_request = _handle_teams_chat_request_with_aws_branch_preflight


# =============================================================================
# Duplicate/related pull-request awareness for infrastructure requests
# =============================================================================
# Every infrastructure request (creation, modification, or a clarification
# reply on the way to one) is checked against already-raised pull requests on
# the resolved cloud's repository, INCLUDING drafts, so a user is told when
# their request overlaps with in-flight work instead of Terrabot silently
# generating a duplicate change. This wraps the final handle_teams_chat_request
# so no existing routing/state-machine logic above needs to change.

_TEAMS_PR_DUPLICATE_CHECK_PREVIOUS_HANDLE_CHAT = handle_teams_chat_request


def _teams_attach_related_pull_requests(result: dict, prompt: str, cloud: str) -> dict:
    """Best-effort: attach already-raised (including draft) pull requests
    that appear related to this infrastructure request. Failures never
    block the response — they are logged and skipped."""
    try:
        normalized_cloud = safe_normalize_cloud(cloud) or ""
        repo_info = _teams_chat_repo_targets(normalized_cloud)
        if not repo_info:
            LOGGER.warning(
                "TEAMS-PR-CHECK-SKIP: no repository configured for cloud=%r (raw cloud=%r); "
                "cannot check for a related/duplicate pull request.",
                normalized_cloud, cloud,
            )
            return result
        if not prompt:
            LOGGER.warning("TEAMS-PR-CHECK-SKIP: no prompt available; cannot check for a related pull request.")
            return result
        pr_result = agent_pr_context.build_pr_context_block(
            prompt,
            repo_info["owner"],
            repo_info["repo"],
            token=GITHUB_TOKEN,
            cloud=normalized_cloud,
        )
        matches = pr_result.get("matches") or []
        if not matches:
            LOGGER.info(
                "TEAMS-PR-CHECK: no related/duplicate pull request found for this request cloud=%s.",
                normalized_cloud,
            )
            return result
        result = dict(result)
        result["related_pull_requests"] = matches
        result["related_pull_requests_context"] = pr_result.get("context_block") or ""
        LOGGER.info(
            "TEAMS-PR-CHECK: found %s related pull request(s) (including drafts) for a Teams infra "
            "request: cloud=%s numbers=%s draft_flags=%s",
            len(matches),
            normalized_cloud,
            [item.get("number") for item in matches],
            [item.get("draft") for item in matches],
        )
        return result
    except Exception:
        LOGGER.exception("TEAMS-PR-CHECK-ERROR: skipping related/duplicate pull request check due to an error")
        return result


def _handle_teams_chat_request_with_related_pr_awareness(data: dict):
    """Final Teams wrapper: attach duplicate/related pull request awareness.

    Runs after every prior routing/state-machine stage so it sees the fully
    resolved cloud and prompt. Applies to every infra-generation-facing
    response: the mode/decision_state whitelist below, PLUS any response the
    router classified as an infra request (``router.request_type ==
    "infra"``) regardless of the exact mode/decision_state string, so a
    duplicate/draft pull request is always checked for whenever the request
    is infrastructure-flavored — not only for a fixed set of mode values.
    Plain chat is handled separately by ``_teams_plain_chat_reply``, which
    already attaches PR context of its own.
    """
    request_data = dict(data or {})
    prompt = str(
        request_data.get("original_prompt")
        or request_data.get("prompt")
        or request_data.get("message")
        or ""
    ).strip()

    # Resolve a reply to a previously rescued numbered picker (see
    # _teams_maybe_rescue_grounding_refusal) BEFORE any routing/state-machine
    # logic sees this message, so a bare "1" or a named option is turned into
    # a fully-specified instruction instead of ambiguous free text. This is
    # what lets the user "choose from the list" rather than having to type an
    # exact rule/parameter name from memory.
    teams_conversation_id = str(
        request_data.get("teams_conversation_id")
        or request_data.get("conversation_id")
        or ""
    ).strip()
    if teams_conversation_id and prompt and not str(request_data.get("action") or "").strip():
        try:
            existing_state = load_teams_conversation_state(teams_conversation_id) or {}
        except Exception:
            existing_state = {}
        pending_rescue = existing_state.get("pending_rescue_selection")
        if isinstance(pending_rescue, dict) and pending_rescue.get("options"):
            selected_rescue_options = _teams_selected_rescue_options(prompt, pending_rescue)
            resolved_instruction = _teams_resolve_pending_rescue_selection(prompt, pending_rescue)
            if resolved_instruction:
                try:
                    _store_repository_context_from_resource_selection(
                        prompt, pending_rescue, selected_rescue_options
                    )
                except Exception as exc:
                    LOGGER.warning(
                        "[TerrabotDiag] event=repository_context_resource_selection_capture_failed error=%s",
                        exc,
                    )
                LOGGER.info(
                    "TEAMS-RESCUE-RESOLVE-TRIGGER: rewriting reply %r into a fully-specified "
                    "instruction using the pending rescue selection for conversation=%s.",
                    prompt[:80], teams_conversation_id,
                )
                request_data["prompt"] = resolved_instruction
                # Keep the user's original infrastructure intent separately so
                # downstream state/validation never mistakes the numeric picker
                # reply for a brand-new request. The executable prompt is the
                # resolved instruction above.
                request_data["original_prompt"] = str(pending_rescue.get("original_prompt") or resolved_instruction)
                request_data["fresh_infra_generation"] = True
                request_data["mode"] = "infra"
                request_data["pending_target_selection_resolved"] = True
                request_data["pending_target_selection_reply"] = True
                pending_cloud = str(pending_rescue.get("cloud") or "").strip()
                if pending_cloud:
                    request_data["cloud"] = pending_cloud
                    request_data["requested_cloud"] = pending_cloud
                prompt = resolved_instruction
                try:
                    _teams_save_ui_state(teams_conversation_id, {"pending_rescue_selection": None})
                except Exception:
                    LOGGER.exception(
                        "TEAMS-RESCUE-ERROR: unable to clear pending rescue selection for conversation=%s",
                        teams_conversation_id,
                    )
            else:
                LOGGER.info(
                    "TEAMS-RESCUE-RESOLVE-TRIGGER: reply %r did not match any pending rescue option "
                    "for conversation=%s; treating it as an ordinary new message.",
                    prompt[:80], teams_conversation_id,
                )

    result, status_code = _TEAMS_PR_DUPLICATE_CHECK_PREVIOUS_HANDLE_CHAT(request_data)
    result = dict(result or {})

    mode = str(result.get("mode") or "").strip().lower()
    decision_state = str(result.get("decision_state") or "").strip().lower()
    router = result.get("router") or {}
    router_request_type = str(router.get("request_type") or "").strip().lower()
    router_cloud = str(router.get("cloud") or "").strip()
    cloud = str(
        result.get("cloud")
        or router_cloud
        or request_data.get("requested_cloud")
        or request_data.get("cloud")
        or ""
    ).strip()

    is_infra_flavored = (
        mode in {"infra_preview", "clarification", "branch_created"}
        or decision_state in {"infra_modification_target_selection", "aws_module_selection", "azure_module_branch_selection"}
        or router_request_type == "infra"
    )
    if prompt and cloud and is_infra_flavored:
        LOGGER.info(
            "TEAMS-PR-CHECK-TRIGGER: checking for a related/duplicate pull request mode=%s "
            "decision_state=%s router_request_type=%s cloud=%s prompt_preview=%r",
            mode, decision_state, router_request_type, cloud, prompt[:160],
        )
        result = _teams_attach_related_pull_requests(result, prompt, cloud)
    elif prompt:
        LOGGER.info(
            "TEAMS-PR-CHECK-TRIGGER: skipped (not infra-flavored or cloud unresolved) mode=%s "
            "decision_state=%s router_request_type=%s cloud=%r",
            mode, decision_state, router_request_type, cloud,
        )

    return result, status_code
handle_teams_chat_request = _handle_teams_chat_request_with_related_pr_awareness


# =============================================================================
# 2026-08-18 AGENT-OWNED TERRAFORM GENERATION — FINAL ARCHITECTURE OVERRIDE
# =============================================================================
# Backend responsibilities: live GitHub retrieval, auth, workflow/session state,
# validation, branch/commit/PR transport, and supplying evidence. Foundry owns
# ALL Terraform semantic interpretation and ALL Terraform/HCL generation.

_AGENT_OWNED_PREVIOUS_BUILD_EXISTING_CONTEXT = build_backend_existing_infra_modification_context


