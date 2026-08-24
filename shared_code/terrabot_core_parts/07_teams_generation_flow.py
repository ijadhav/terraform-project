from __future__ import annotations
from typing import TYPE_CHECKING , Any , Optional 

if TYPE_CHECKING:
    from shared_code.terrabot_core_typing import (
        AFFIRMATIVE_REPLIES,
        AWS_MODULES_ROOT,
        AZDO_API_VERSION,
        AZDO_AWS_DRIFT_PIPELINE_BRANCH,
        AZDO_AWS_DRIFT_PIPELINE_ID,
        AZDO_AZURE_DRIFT_PIPELINE_BRANCH,
        AZDO_AZURE_DRIFT_PIPELINE_ID,
        AZDO_ORG,
        AZDO_PAT,
        AZDO_PIPELINE_BRANCH,
        AZDO_PIPELINE_ID,
        AZDO_PROJECT,
        ContextVar,
        DRIFT_AGENT_NAME,
        DRIFT_GITHUB_LOOKBACK_COMMITS,
        GITHUB_API,
        GITHUB_AWS_BASE_BRANCH,
        GITHUB_AWS_REPO,
        GITHUB_AZURE_BASE_BRANCH,
        GITHUB_AZURE_REPO,
        GITHUB_OWNER,
        GITHUB_TOKEN,
        GITHUB_VENA_DIR,
        INFRA_MODIFICATION_WORKFLOWS,
        LOGGER,
        MAX_TEAMS_SELF_CORRECTION_ATTEMPTS,
        ModuleVariableValuesRequired,
        NEGATIVE_REPLIES,
        NormalizedRouterDecision,
        PLAN_RISK_AGENT_NAME,
        TERRABOT_BACKEND_API_KEY,
        TERRABOT_BACKEND_BASE_URL,
        TERRABOT_DRIFT_STORE_PATH,
        _ACTIVE_GITHUB_TOKEN,
        _ACTIVE_TEAMS_REQUESTER_DISPLAY,
        _add_backend_existing_aws_infra_context_base,
        _apply_module_placeholder_values_for_teams,
        _aws_module_catalog_branch,
        _aws_module_selection_requests_new_module,
        _aws_selected_module_context_with_contents,
        _aws_selected_module_value_context,
        _aws_unique_custom_module_path,
        _azure_consumer_value_selection_confirmed,
        _backend_existing_infra_context_is_selected,
        _build_agent_input_for_infra_base,
        _build_backend_existing_infra_modification_context_base,
        _build_verified_aws_module_context_base,
        _cancel_new_azure_consumer_file_reply,
        _commit_terraform_files_to_branch_for_teams_base,
        _confirm_new_azure_consumer_file_routing_context,
        _create_teams_pull_request_from_branch_base,
        _get_backend_existing_infra_context,
        _get_confirmed_aws_module_selection,
        _get_primary_azure_module_context,
        _remove_backend_existing_infra_contexts,
        _repair_and_parse_agent_output_base,
        _start_module_variable_value_selection_response,
        _teams_apply_agent_identity,
        _teams_auto_accept_aws_module_creation,
        _teams_auto_select_feature_flag_context,
        _teams_azure_object_backed_no_question_corrective,
        _teams_backend_rule2_reply,
        _teams_build_backend_repair_payload,
        _teams_call_agent_for_backend_repair,
        _teams_collect_backend_env_context,
        _teams_describe_tf_file_contents,
        _teams_diag_log,
        _teams_ensure_flag_enable_in_env_values,
        _teams_flagless_creation_corrective,
        _teams_generate_aws_new_module_with_context,
        _teams_intercept_agent_questions,
        _teams_is_existing_invocation_creation,
        _teams_is_path_request_question,
        _teams_locate_environment_value_files,
        _teams_materialize_repair_edits_response,
        _teams_path_question_corrective,
        _teams_remote_context_branch,
        _teams_repair_candidate_is_identical,
        _teams_requested_resource_name,
        _teams_semantic_candidate_score,
        _teams_supplied_files_diagnostic,
        _teams_validate_repair_candidate_against_payload,
        _try_parse_agent_output_base,
        _with_azure_consumer_value_selection_confirmation,
        add_backend_existing_aws_infra_context,
        add_grounded_aws_module_context,
        add_grounded_azure_context_for_match,
        agent_reply_looks_like_infra_json,
        augment_azure_consumer_generation_context,
        aws_prompt_can_update_existing_without_module_match,
        azure_context_has_verified_inputs_for_branch,
        azure_devops_headers,
        build_agent_input_for_infra,
        build_aws_existing_module_selection_reply,
        build_aws_module_creation_confirmation_reply,
        build_azure_consumer_value_selection_form,
        build_azure_consumer_variable_values_reply,
        build_azure_module_branch_discovery,
        build_azure_module_branch_selection_reply,
        build_azure_module_creation_prompt_with_repo_name,
        build_azure_module_discovery_reply,
        build_azure_new_consumer_file_confirmation_reply,
        build_backend_existing_infra_modification_context,
        build_enhanced_conversation_label,
        build_infra_modification_selection_reply,
        build_plan_risk_agent_input,
        build_pr_comment_from_agent_result,
        build_router_response_message,
        build_selected_infra_modification_context,
        build_thread_prs_payload,
        build_user_friendly_error,
        call_agent,
        call_named_agent,
        classify_aws_pending_module_reply,
        clear_pending_aws_module_discovery,
        clear_pending_azure_consumer_value_selection,
        clear_pending_azure_module_discovery,
        clear_pending_azure_new_consumer_file_confirmation,
        clear_pending_cloud_clarification,
        clear_pending_infra_change_by_id,
        clear_pending_infra_modification_selection,
        clear_pending_module_variable_value_selection,
        coerce_context_list,
        commit_terraform_files_to_branch_for_teams_with_self_correction,
        commit_terraform_files_to_repo,
        create_teams_pull_request_from_branch,
        datetime,
        discover_live_azure_module_candidates,
        enforce_modification_uses_backend_matched_files,
        ensure_thread_meta,
        extract_azure_module_repo_name_from_confirmation_reply,
        extract_first_balanced_json_object,
        extract_json_from_text,
        extract_json_safely,
        extract_requested_azure_module_repo_name,
        filter_backend_owned_context_list,
        finalize_agent_result_after_parse,
        find_agent_reference,
        generate_aws_module_creation_with_agent,
        generate_azure_module_repo_creation_with_agent,
        generate_short_ticket_title,
        get_first_azure_module_match,
        get_github_app_installation_token,
        get_pending_aws_module_discovery,
        get_pending_azure_consumer_value_selection,
        get_pending_azure_module_discovery,
        get_pending_azure_new_consumer_file_confirmation,
        get_pending_cloud_clarification,
        get_pending_infra_change_by_id,
        get_pending_infra_modification_selection,
        get_project_client,
        github_base_branch_for_cloud,
        github_get_file_content,
        github_get_repo_metadata,
        github_headers_for_repo,
        github_list_tf_files_recursive,
        github_token_context,
        github_upsert_pr_summary_comment,
        github_verified_aws_module_exists,
        handle_refresh_pr_status_request,
        handle_submit_module_variable_values,
        handle_workspace_branch_request,
        importlib,
        infer_cloud_from_prompt,
        infer_generation_workflow,
        infer_new_aws_module_path,
        is_valid_jira_ticket_link,
        is_valid_ticket_or_link,
        json,
        load_teams_conversation_state,
        logging,
        looks_like_infra_payload,
        normalize_cloud,
        normalize_repo_target,
        normalize_router_decision,
        normalize_ticket_input,
        normalize_yes_no_reply,
        os,
        parse_agent_output,
        persist_teams_workflow_state,
        re,
        recover_thread_pr_state,
        repair_and_parse_agent_output,
        requests,
        resolve_aws_environment_path,
        resolve_manual_azure_module_branch_from_reply,
        restore_teams_workflow_state,
        safe_normalize_cloud,
        save_teams_conversation_state,
        select_aws_module_match_from_reply,
        select_azure_module_branch_from_reply,
        select_azure_module_match_from_reply,
        select_infra_modification_candidate_from_reply,
        set_last_selected_cloud,
        should_block_missing_azure_value_context,
        should_handle_cloud_only_clarification,
        stable_thread_key,
        state_bucket_for_target,
        store_pending_aws_module_discovery,
        store_pending_azure_consumer_value_selection,
        store_pending_azure_module_discovery,
        store_pending_azure_new_consumer_file_confirmation,
        store_pending_cloud_clarification,
        store_pending_infra_change,
        store_pending_infra_modification_selection,
        teams_requester_context,
        teams_workflow_has_pending_state,
        timezone,
        try_parse_agent_output,
        uuid,
    )

def _teams_extract_chat_text(agent_reply: str) -> str:
    """Return user-facing text when Foundry wraps chat in a JSON envelope."""
    raw = str(agent_reply or "").strip()
    if not raw:
        return "No response returned from agent."
    try:
        payload = extract_json_from_text(raw)
    except Exception:
        return raw
    if not isinstance(payload, dict):
        return raw
    return str(payload.get("reply") or payload.get("summary") or raw).strip()


def _teams_auto_commit_preview(data: dict, preview: dict, status_code: int):
    """Commit a successful Teams preview through the centrally installed GitHub App.

    Some outer Teams recovery/branch-choice wrappers run after the original
    ``github_token_context`` has exited.  Those wrappers can synthesize a new
    infra preview and call this helper with the original Teams request, which
    intentionally does not persist an installation token.  Re-acquire the
    short-lived GitHub App installation token here so every Teams auto-commit
    path has the same authentication guarantees as ``_handle_teams_chat_request_base``.
    """
    if status_code >= 400 or not preview.get("ok", True):
        return preview, status_code
    if preview.get("mode") != "infra_preview" or not preview.get("pending_change_id"):
        return preview, status_code

    commit_request = dict(data or {})
    commit_request.update({
        "action": "commit_branch",
        "source": "teams",
        "thread_id": preview.get("thread_id") or data.get("thread_id") or "",
        "pending_change_id": preview.get("pending_change_id") or "",
        "prompt": data.get("prompt") or "",
    })

    token = str(
        commit_request.get("github_token")
        or _ACTIVE_GITHUB_TOKEN.get()
        or ""
    ).strip()
    if not token:
        try:
            token = get_github_app_installation_token()
        except Exception as exc:
            LOGGER.exception(
                "GitHub App authentication failed during Teams auto-commit",
                exc_info=exc,
            )
            return {
                "ok": False,
                "mode": "github_app_error",
                "reply": f"Terrabot could not authenticate its GitHub App installation: {exc}",
                "thread_id": commit_request.get("thread_id") or "",
                "source": "teams",
            }, 503

    commit_request["github_token"] = token
    requester = str(
        commit_request.get("teams_requester")
        or commit_request.get("teams_requester_id")
        or _ACTIVE_TEAMS_REQUESTER_DISPLAY.get()
        or "Terrabot"
    ).strip()

    with github_token_context(token), teams_requester_context(requester):
        committed, committed_status = handle_chat_request(commit_request)
    if committed_status < 400 and committed.get("ok", True):
        cloud = str(preview.get("cloud") or committed.get("cloud") or "").strip().lower()
        repo_name = GITHUB_AWS_REPO if cloud == "aws" else GITHUB_AZURE_REPO
        base_branch = committed.get("base_branch") or (GITHUB_AWS_BASE_BRANCH if cloud == "aws" else GITHUB_AZURE_BASE_BRANCH)
        files = [str(item) for item in (preview.get("files") or []) if item]
        generated_analysis = "\n".join([
            f"Repository: {GITHUB_OWNER}/{repo_name}",
            f"Base branch: {base_branch} (latest remote branch ref)",
            f"Workflow: {preview.get('workflow') or 'Terraform infrastructure change'}",
            "Repository analysis: live GitHub files and existing Terraform conventions were used.",
            f"Generated files: {', '.join(files) if files else 'No file list returned'}",
        ])
        committed.setdefault("analysis", preview.get("analysis") or generated_analysis)
        committed.setdefault("summary", preview.get("summary") or "")
        committed.setdefault("workflow", preview.get("workflow") or "")
        committed.setdefault("repo_target", preview.get("repo_target") or "")
        committed.setdefault("title", preview.get("title") or "")
    return committed, committed_status


def _teams_workflow_thread_id(data: dict, fallback: str = "") -> str:
    """Return a stable backend workflow id for Teams-only state.

    This id is deliberately separate from the Azure AI Foundry conversation id.
    Teams infrastructure flows need a stable key for pending changes and GitHub
    branch names even when no Foundry conversation has been created yet.
    """
    teams_conversation_id = (
        (data or {}).get("teams_conversation_id")
        or (data or {}).get("conversation_id")
        or fallback
        or "teams-thread"
    )
    return f"teams-{stable_thread_key(str(teams_conversation_id))}"


def _teams_auto_accept_aws_module_creation_base(data: dict, preview: dict, status_code: int):
    """For Teams, do not stop at the AWS new-module confirmation screen.

    The Teams contract is branch-first: after a user sends an infrastructure
    request, Terrabot should analyze live GitHub, generate the change, and push
    it to a Terrabot branch. PR creation remains gated separately by explicit
    user approval and Jira collection.
    """
    if status_code < 400:
        return preview, status_code
    if not isinstance(preview, dict):
        return preview, status_code
    if (preview.get("decision_state") or "") != "aws_module_creation_confirmation":
        return preview, status_code

    workflow_thread_id = _teams_workflow_thread_id(
        data,
        fallback=(preview.get("thread_id") or data.get("thread_id") or ""),
    )
    original_prompt = (data.get("prompt") or "").strip()
    discovery = preview.get("aws_module_discovery") or {}
    proposed_module_path = (
        preview.get("proposed_module_path")
        or infer_new_aws_module_path(original_prompt, discovery)
    )
    environment_path = (
        preview.get("environment_path")
        or "terraform/dev_aws/minidev"
    )

    try:
        agent_result = generate_aws_module_creation_with_agent(
            conversation_id="",
            original_prompt=original_prompt,
            proposed_module_path=proposed_module_path,
            environment_path=environment_path,
            discovery=discovery,
        )
    except Exception as exc:
        LOGGER.exception("Teams AWS module auto-generation failed", exc_info=exc)
        failed = dict(preview)
        failed.update({
            "ok": False,
            "mode": "clarification",
            "reply": (
                "Terrabot confirmed that no verified AWS module exists, but automatic "
                f"new-module generation failed: {exc}"
            ),
            "thread_id": workflow_thread_id,
        })
        return failed, 500

    ticket_number = preview.get("ticket_number") or preview.get("jira_ticket") or ""
    ticket_link = preview.get("ticket_link") or data.get("ticket_link") or ""
    ticket_title = preview.get("ticket_title") or data.get("ticket_title") or ""
    conversation_label = (
        preview.get("conversation_label")
        or build_enhanced_conversation_label(ticket_number, ticket_title, workflow_thread_id)
    )

    placeholder_variable_names = []
    if agent_result.get("_module_variable_values_required"):
        agent_result, placeholder_issues, placeholder_values = _apply_module_placeholder_values_for_teams(
            agent_result,
            original_prompt,
        )
        if placeholder_issues:
            LOGGER.warning(
                "Teams AWS module placeholder normalization still has issues: %s",
                placeholder_issues,
            )
        if not placeholder_values:
            return _start_module_variable_value_selection_response(
                conversation_id=workflow_thread_id,
                conversation_label=conversation_label,
                ticket_number=ticket_number,
                ticket_link=ticket_link,
                ticket_title=ticket_title,
                effective_prompt=original_prompt,
                agent_result=agent_result,
                issues=agent_result.get("_module_variable_issues") or placeholder_issues or [],
            )
        placeholder_variable_names = sorted(placeholder_values.keys())

    pending_key = store_pending_infra_change(
        workflow_thread_id,
        ticket_number,
        original_prompt,
        agent_result,
        ticket_link=ticket_link,
        ticket_title=ticket_title,
    )

    auto_preview = {
        "ok": True,
        "mode": "infra_preview",
        "reply": "AWS module creation is ready. Terrabot will push it to a GitHub branch.",
        "thread_id": workflow_thread_id,
        "conversation_label": conversation_label,
        "jira_ticket": ticket_number,
        "ticket_number": ticket_number,
        "ticket_link": ticket_link,
        "ticket_title": ticket_title,
        "pending_change_id": pending_key,
        "cloud": "aws",
        "workflow": "aws_module_creation",
        "title": agent_result["title"],
        "summary": agent_result["summary"],
        "files": [f["filename"] for f in agent_result.get("files") or []],
        "repo_target": agent_result["repo_target"],
        "state_bucket": agent_result["state_bucket"],
        "analysis": (
            "Terrabot scanned the live tf-devops module catalog, found no verified "
            "matching local module, generated a new module plus minidev consumer "
            "reference, and will commit those files to a Teams branch."
            + (
                " Placeholder defaults were inserted for: "
                + ", ".join(placeholder_variable_names)
                + ". Replace TERRABOT_PLACEHOLDER values with approved values before merge."
                if placeholder_variable_names else ""
            )
        ),
        "thread_prs": build_thread_prs_payload(workflow_thread_id),
    }

    commit_data = dict(data or {})
    commit_data["thread_id"] = workflow_thread_id
    committed, committed_status = _teams_auto_commit_preview(commit_data, auto_preview, 200)
    if isinstance(committed, dict):
        committed.setdefault("analysis", auto_preview.get("analysis") or "")
        committed.setdefault("source_paths_used", auto_preview.get("source_paths_used") or [])
        committed.setdefault("user_fillable", auto_preview.get("user_fillable") or [])
        committed.setdefault("validation_commands", auto_preview.get("validation_commands") or [])
        committed.setdefault("branch_name", auto_preview.get("branch_name") or "")
    return committed, committed_status


def handle_teams_workspace_branch_request(data: dict) -> dict:
    """Create an explicit Teams branch through the installed GitHub App."""
    requester = (data.get("teams_requester") or "terrabot").strip()
    token = get_github_app_installation_token()
    with github_token_context(token), teams_requester_context(requester):
        return handle_workspace_branch_request(data)


def _teams_stage_from_result(result: dict, current_stage: str = "") -> str:
    decision_state = str((result or {}).get("decision_state") or "").strip()
    if decision_state:
        return decision_state

    mode = str((result or {}).get("mode") or "").strip().lower()
    if mode == "branch_created":
        return "awaiting_pr_decision"
    if mode == "jira_required":
        return "awaiting_jira"
    if mode == "pr_created" or (result or {}).get("pr_url"):
        return "complete"
    if mode == "infra_preview":
        return "awaiting_branch_commit"
    return current_stage or "idle"


def _finalize_teams_service_response(
    request_data: dict,
    result: dict,
    status_code: int,
    fallback_thread_id: str = "",
    existing_ui_state: dict | None = None,
):
    """Persist both router/UI state and backend pending state for every turn."""
    result = dict(result or {})
    workflow_thread_id = str(
        result.get("thread_id")
        or fallback_thread_id
        or ""
    ).strip()
    teams_conversation_id = str(
        (request_data or {}).get("teams_conversation_id")
        or (request_data or {}).get("conversation_id")
        or ""
    ).strip()

    if workflow_thread_id:
        result.setdefault("thread_id", workflow_thread_id)
        persist_teams_workflow_state(workflow_thread_id)

    if teams_conversation_id:
        state = dict(existing_ui_state or load_teams_conversation_state(teams_conversation_id) or {})
        if workflow_thread_id:
            # `workflow_thread_id` is the backend/Foundry conversation key. Keep
            # the legacy name so older deployed Teams bot code can also recover.
            state["workflow_thread_id"] = workflow_thread_id
            state["foundry_conversation_id"] = workflow_thread_id

        pending_change_id = str(result.get("pending_change_id") or "").strip()
        if pending_change_id:
            state["pending_change_id"] = pending_change_id

        state["stage"] = _teams_stage_from_result(
            result,
            str(state.get("stage") or ""),
        )

        for key in (
            "ticket_link",
            "ticket_number",
            "ticket_title",
            "branch",
            "branch_url",
            "compare_url",
            "base_branch",
            "cloud",
            "workflow",
            "repo_target",
        ):
            value = result.get(key)
            if value not in (None, ""):
                state[key] = value

        if state.get("stage") == "complete" or (request_data or {}).get("action") == "discard_pending":
            state.pop("pending_change_id", None)

        save_teams_conversation_state(teams_conversation_id, state)

    return result, status_code


def _teams_extract_ticket_link_from_prompt(prompt: str) -> str:
    match = re.search(
        r"https?://[^\s<>]+/browse/[A-Z][A-Z0-9]+-\d+",
        prompt or "",
        re.IGNORECASE,
    )
    return (match.group(0).rstrip(".,);]") if match else "")

def _teams_backend_flag_enable_envelope(
    prompt: str,
    retrieved_value_context: list | None,
    cloud: str,
    workflow: str,
) -> str | None:
    """Deterministic RULE-1 flag enable, built by the BACKEND from live
    GitHub when the agent stalls asking for a values-file path.

    Preconditions (all verified from evidence, no guessing):
    - the prompt names the resource explicitly;
    - the selected definition file wires it via var.<...>_enabled (the exact
      flag name is read from that wiring, never constructed);
    - an environment values file holding the sibling *_enabled assignments
      exists in the evidence.
    Returns a strict JSON envelope string (fed through the normal pipeline)
    or None when any precondition fails."""
    ctx = _get_backend_existing_infra_context(retrieved_value_context or [])
    if not isinstance(ctx, dict):
        ctx = {}
    merged = _teams_collect_backend_env_context(retrieved_value_context)
    name = _teams_requested_resource_name(prompt)
    if not name:
        return None
    name_us = name.replace("-", "_")

    definition_content = ""
    for item in retrieved_value_context or []:
        if not isinstance(item, dict) or item.get("source") != "backend_existing_infra_code_match":
            continue
        for matched in item.get("matched_files") or []:
            if isinstance(matched, dict):
                definition_content += "\n" + str(matched.get("content") or "")
    wiring = re.search(
        rf"var\.((?:[a-z0-9]+_)*{re.escape(name_us)}(?:_[a-z0-9]+)*_enabled)\b",
        definition_content,
    )
    if not wiring:
        return None
    flag_name = wiring.group(1)

    sibling_re = re.compile(r"(?m)^([ \t]*)([a-z0-9_]+_enabled)[ \t]*=[ \t]*(true|false)[ \t]*$")
    branch_hint = str(merged.get("context_ref") or ctx.get("context_ref") or "").strip() or github_base_branch_for_cloud(
        merged.get("cloud") or ctx.get("cloud") or cloud,
        repo_target=merged.get("repo_target") or ctx.get("repo_target"),
        workflow=merged.get("workflow") or ctx.get("workflow") or workflow,
    )
    env_entries = list(merged.get("environment_files") or []) or list(ctx.get("environment_files") or [])
    if not any(
        str((entry or {}).get("path") or "").endswith((".tfvars", ".tfvars.json"))
        for entry in env_entries
    ):
        try:
            located_entries, _located_paths, located_debug = _teams_locate_environment_value_files(
                prompt,
                merged.get("cloud") or ctx.get("cloud") or cloud,
                merged.get("repo_target") or ctx.get("repo_target"),
                merged.get("workflow") or ctx.get("workflow") or workflow,
                branch_hint,
            )
            env_entries.extend(entry for entry in located_entries if isinstance(entry, dict))
            logging.info("Teams flag envelope: live locator resolver=%s", located_debug)
        except Exception:
            logging.exception("Teams flag envelope: live locator failed")
    best_path, best_hits = "", 0
    for entry in env_entries:
        entry_path = str((entry or {}).get("path") or "")
        if not entry_path.endswith((".tfvars", ".tfvars.json")):
            continue
        hits = len(list(sibling_re.finditer(str(entry.get("content") or ""))))
        if hits > best_hits:
            best_path, best_hits = entry_path, hits
    if not best_path:
        return None

    branch = str(ctx.get("context_ref") or "").strip() or github_base_branch_for_cloud(
        ctx.get("cloud") or cloud,
        repo_target=ctx.get("repo_target"),
        workflow=ctx.get("workflow") or workflow,
    )
    try:
        live = github_get_file_content(
            ctx.get("cloud") or cloud,
            best_path,
            branch,
            repo_target=ctx.get("repo_target"),
            workflow=ctx.get("workflow") or workflow,
        ) or ""
    except Exception:
        return None
    live = str(live).replace("\r\n", "\n")

    flag_line_re = re.compile(
        rf"(?m)^([ \t]*){re.escape(flag_name)}[ \t]*=[ \t]*(true|false)[ \t]*$"
    )
    existing_line = flag_line_re.search(live)
    if existing_line:
        if existing_line.group(2) == "true":
            return None  # already enabled — RULE 2 handles this branch
        final = (
            live[: existing_line.start()]
            + f"{existing_line.group(1)}{flag_name} = true"
            + live[existing_line.end():]
        )
        change_note = f"changed `{flag_name}` from false to true"
    else:
        siblings = list(sibling_re.finditer(live))
        if siblings:
            last = siblings[-1]
            final = (
                live[: last.end()]
                + f"\n{last.group(1)}{flag_name} = true"
                + live[last.end():]
            )
        else:
            final = live.rstrip("\n") + f"\n{flag_name} = true\n"
        change_note = f"added `{flag_name} = true` beside the sibling flags"

    selected_path = str(ctx.get("selected_path") or "the definition file")
    envelope = {
        "summary": (
            f"Enable {name}: the app definition already exists in "
            f"{selected_path}; per the repo pattern the creation step is the "
            f"environment flag — {change_note} in {best_path}."
        ),
        "analysis": (
            f"Definition file: {selected_path} wires the app via var.{flag_name}. "
            f"Flag file: {best_path} (holds the sibling *_enabled assignments; read from live GitHub). "
            "Change: one-line flag enable, backend-deterministic; every other line preserved byte-for-byte."
        ),
        "source_paths_used": [path for path in (selected_path, best_path) if path],
        "files": [{
            "path": best_path,
            "operation": "modify",
            "in_place": True,
            "content": final,
            "source_paths_used": [best_path],
        }],
        "user_fillable": [],
        "questions": [],
        "validation_commands": ["terraform fmt -check -recursive", "terraform validate"],
    }
    try:
        return json.dumps(envelope, ensure_ascii=False)
    except Exception:
        return None

_TEAMS_FLAG_VALUES_BASENAME_PRIORITY = ("hub.tfvars", "tier.tfvars", "common.tfvars")

_TEAMS_SIBLING_FLAG_LINE_RE = re.compile(
    r"(?m)^([ \t]*)[a-z0-9_]+_enabled[ \t]*=[ \t]*(?:true|false)[ \t]*$"
)


def _handle_teams_chat_request_base(data: dict):  # pyright: ignore[reportGeneralTypeIssues]
    """Run Teams through the centrally installed GitHub App.

    Teams conversation routing and backend pending state are restored from
    Azure Table Storage before each turn. This prevents a numeric/module choice,
    yes/no reply, or Jira follow-up from being misclassified as a new chat when
    Azure Functions changes workers or restarts.

    Natural-language chat still goes to Foundry. Infrastructure and follow-up
    actions use a short-lived GitHub App installation token. VS Code behavior is
    unchanged because only requests with source='teams' use this wrapper.
    """
    data = dict(data or {})
    prompt = (data.get("prompt") or data.get("message") or "").strip()
    action = (data.get("action") or "").strip().lower()
    requester = (
        data.get("teams_requester")
        or data.get("teams_requester_id")
        or "terrabot"
    ).strip()
    teams_conversation_id = str(
        data.get("teams_conversation_id")
        or data.get("conversation_id")
        or ""
    ).strip()

    if not prompt and not action:
        return {"ok": False, "mode": "chat", "reply": "Please enter a prompt."}, 400

    durable_ui_state = (
        load_teams_conversation_state(teams_conversation_id)
        if teams_conversation_id
        else {}
    )
    conversation_id = str(
        data.get("thread_id")
        or durable_ui_state.get("workflow_thread_id")
        or durable_ui_state.get("foundry_conversation_id")
        or ""
    ).strip()

    if conversation_id:
        restore_teams_workflow_state(conversation_id)

    # Recover fields that may have been lost with an in-memory Teams worker.
    if not data.get("pending_change_id") and durable_ui_state.get("pending_change_id"):
        data["pending_change_id"] = durable_ui_state.get("pending_change_id")
    if not data.get("ticket_link") and durable_ui_state.get("ticket_link"):
        data["ticket_link"] = durable_ui_state.get("ticket_link")
    if not data.get("jira_ticket") and durable_ui_state.get("ticket_number"):
        data["jira_ticket"] = durable_ui_state.get("ticket_number")
    if not data.get("ticket_title") and durable_ui_state.get("ticket_title"):
        data["ticket_title"] = durable_ui_state.get("ticket_title")

    requested_mode = (data.get("mode") or "").strip().lower()
    durable_stage = str(durable_ui_state.get("stage") or "").strip()
    pending_workflow = teams_workflow_has_pending_state(conversation_id)
    if not requested_mode and (pending_workflow or durable_stage not in {"", "idle", "complete"}):
        requested_mode = "infra"

    normalized_prompt = normalize_yes_no_reply(prompt)
    affirmative_pr_reply = bool(
        normalized_prompt in AFFIRMATIVE_REPLIES
        or re.match(r"^(?:yes|y|raise|create|open)\b.*\b(?:pr|pull request)\b", normalized_prompt)
    )
    negative_pr_reply = bool(
        normalized_prompt in NEGATIVE_REPLIES
        or re.match(r"^(?:no|n|cancel|skip|not now)\b", normalized_prompt)
    )
    supplied_ticket_link = _teams_extract_ticket_link_from_prompt(prompt)
    persisted_ticket_link = str(data.get("ticket_link") or "").strip()
    pending_change_id = str(data.get("pending_change_id") or "").strip()

    # Defensive stage routing: this also works if an older Teams bot build did
    # not translate the visible yes/Jira reply into an explicit backend action.
    if not action and durable_stage == "awaiting_pr_decision" and pending_change_id:
        if supplied_ticket_link:
            action = "create_pr_from_branch"
            data["ticket_link"] = supplied_ticket_link
        elif persisted_ticket_link and is_valid_jira_ticket_link(persisted_ticket_link) and affirmative_pr_reply:
            action = "create_pr_from_branch"
        elif affirmative_pr_reply:
            jira_result = {
                "ok": True,
                "mode": "jira_required",
                "reply": (
                    "Send the Jira ticket link for this pull request, for example "
                    "https://<jira-host>/browse/STO-1234."
                ),
                "thread_id": conversation_id,
                "pending_change_id": pending_change_id,
            }
            return _finalize_teams_service_response(
                data,
                jira_result,
                200,
                fallback_thread_id=conversation_id,
                existing_ui_state=durable_ui_state,
            )
        elif negative_pr_reply:
            action = "discard_pending"

    if not action and durable_stage == "awaiting_jira" and pending_change_id:
        if supplied_ticket_link:
            action = "create_pr_from_branch"
            data["ticket_link"] = supplied_ticket_link
        elif negative_pr_reply:
            action = "discard_pending"
        else:
            jira_result = {
                "ok": True,
                "mode": "jira_required",
                "reply": (
                    "A Jira ticket link is still required before I open the pull request. "
                    "Send a link such as https://<jira-host>/browse/STO-1234, or reply no to cancel."
                ),
                "thread_id": conversation_id,
                "pending_change_id": pending_change_id,
            }
            return _finalize_teams_service_response(
                data,
                jira_result,
                200,
                fallback_thread_id=conversation_id,
                existing_ui_state=durable_ui_state,
            )

    if action:
        data["action"] = action

    infrastructure_request = (
        bool(action)
        or requested_mode == "infra"
        or pending_workflow
    )

    if not infrastructure_request:
        conversation_id, foundry_reply = call_agent(conversation_id, prompt)
        result = {
            "ok": True,
            "mode": "chat",
            "reply": _teams_extract_chat_text(foundry_reply),
            "thread_id": conversation_id,
            "source": "teams",
        }
        return _finalize_teams_service_response(
            data,
            result,
            200,
            fallback_thread_id=conversation_id,
            existing_ui_state=durable_ui_state,
        )

    try:
        installation_token = get_github_app_installation_token()
    except Exception as exc:
        LOGGER.exception("GitHub App authentication failed for Teams", exc_info=exc)
        result = {
            "ok": False,
            "mode": "github_app_error",
            "reply": f"Terrabot could not authenticate its GitHub App installation: {exc}",
            "thread_id": conversation_id,
            "source": "teams",
        }
        return _finalize_teams_service_response(
            data,
            result,
            503,
            fallback_thread_id=conversation_id,
            existing_ui_state=durable_ui_state,
        )

    infrastructure_data = dict(data)
    infrastructure_data.update({
        "prompt": prompt,
        "thread_id": conversation_id,
        "mode": "infra",
        "source": "teams",
        "github_token": installation_token,
        "teams_conversation_id": teams_conversation_id,
        "memory_conversation_id": str(data.get("memory_conversation_id") or teams_conversation_id).strip(),
    })

    with github_token_context(installation_token), teams_requester_context(requester):
        if action:
            result, status_code = handle_chat_request(infrastructure_data)
        else:
            result, status_code = handle_chat_request(infrastructure_data)
            result, status_code = _teams_auto_accept_aws_module_creation(
                infrastructure_data,
                result,
                status_code,
            )
            result, status_code = _teams_auto_commit_preview(
                infrastructure_data,
                result,
                status_code,
            )

    return _finalize_teams_service_response(
        infrastructure_data,
        result,
        status_code,
        fallback_thread_id=conversation_id,
        existing_ui_state=durable_ui_state,
    )

def handle_chat_request(data: dict):
    data = data or {}

    prompt = (data.get("prompt") or "").strip()
    conversation_id = data.get("thread_id")
    requested_mode = (data.get("mode") or "").strip().lower()
    # A Teams continuation may carry the already-resolved cloud under
    # requested_cloud even when the literal control reply (for example "2")
    # contains no provider semantics. Treat both fields as equivalent inputs
    # here so the legacy multicloud handler cannot lose the active request
    # cloud and fall into the "both AWS and Azure PRs" ambiguity branch.
    requested_cloud = data.get("cloud") or data.get("requested_cloud")
    action = (data.get("action") or "").strip().lower()
    pending_change_id = (data.get("pending_change_id") or "").strip()

    requested_workflow = (data.get("workflow") or "").strip()
    retrieved_module_context = filter_backend_owned_context_list(
        data.get("retrieved_module_context"),
        context_name="retrieved_module_context",
    )
    retrieved_value_context = filter_backend_owned_context_list(
        data.get("retrieved_value_context"),
        context_name="retrieved_value_context",
    )

    raw_ticket_value = (
        data.get("ticket_link")
        or data.get("jira_ticket")
        or ""
    ).strip()

    ticket_number, inferred_ticket_link = normalize_ticket_input(raw_ticket_value)
    ticket_link = (data.get("ticket_link") or "").strip() or inferred_ticket_link
    ticket_title = (data.get("ticket_title") or "").strip()

    if not ticket_title and prompt:
        ticket_title = generate_short_ticket_title(prompt)

    conversation_label = build_enhanced_conversation_label(
        ticket_number=ticket_number,
        ticket_title=ticket_title,
        conversation_id=conversation_id,
    )

    if action not in {"commit_pending", "commit_branch", "create_pr_from_branch", "discard_pending", "refresh_pr_status", "submit_module_variable_values"} and not prompt:
        return {"ok": False, "reply": "Please enter a prompt."}, 400

    require_jira_ticket = os.getenv("TERRABOT_REQUIRE_JIRA", "true").strip().lower() not in {"0", "false", "no"}
    request_source = (data.get("source") or "").strip().lower()
    jira_required_for_request = require_jira_ticket and request_source != "teams"

    if jira_required_for_request and not is_valid_ticket_or_link(raw_ticket_value):
        return {
            "ok": False,
            "mode": "chat",
            "reply": "A valid JIRA ticket link is required before you can continue.",
            "ticket_link": ticket_link,
            "ticket_number": ticket_number,
            "ticket_title": ticket_title,
        }, 400

    try:
        if action == "refresh_pr_status":
            return handle_refresh_pr_status_request(
                conversation_id=conversation_id,
                conversation_label=conversation_label,
                ticket_number=ticket_number,
                ticket_link=ticket_link,
                ticket_title=ticket_title,
            )

        if action == "submit_module_variable_values":
            return handle_submit_module_variable_values(
                data=data,
                conversation_id=conversation_id,
                conversation_label=conversation_label,
                ticket_number=ticket_number,
                ticket_link=ticket_link,
                ticket_title=ticket_title,
            )

        if action == "commit_branch":
            pending = get_pending_infra_change_by_id(pending_change_id)
            if not pending:
                return {"ok": False, "mode": "chat", "reply": "There are no pending infrastructure changes to commit."}, 400
            token = (data.get("github_token") or _ACTIVE_GITHUB_TOKEN.get() or "").strip()
            if not token:
                return {"ok": False, "mode": "github_auth_required", "reply": "Connect GitHub before Terrabot creates the branch."}, 401
            with github_token_context(token):
                branch_result = commit_terraform_files_to_branch_for_teams_with_self_correction(
                    pending["agent_result"], pending["prompt"], conversation_id
                )
            # The self-correction loop may have replaced the originally-generated
            # files/analysis with a corrected version — keep pending["agent_result"]
            # in sync so any later fill/insert follow-up edits the version that
            # was actually committed, not the rejected draft.
            if branch_result.get("self_corrected"):
                pending["agent_result"] = {
                    **pending["agent_result"],
                    "files": branch_result.get("committed_agent_result_files", pending["agent_result"].get("files")),
                    "analysis": branch_result.get("analysis", pending["agent_result"].get("analysis")),
                }
            pending["branch_result"] = branch_result
            pending["stage"] = "awaiting_pr_decision"
            return {
                "ok": True,
                "mode": "branch_created",
                "reply": branch_result["message"],
                "thread_id": conversation_id,
                "pending_change_id": pending_change_id,
                "branch": branch_result["branch"],
                "branch_url": branch_result["branch_url"],
                "compare_url": branch_result["compare_url"],
                "base_branch": branch_result.get("base_branch"),
                "files": branch_result["files"],
                "cloud": branch_result["cloud"],
                "workflow": pending.get("agent_result", {}).get("workflow"),
                "repo_target": pending.get("agent_result", {}).get("repo_target"),
                "summary": pending.get("agent_result", {}).get("summary") or branch_result.get("summary"),
                "analysis": pending.get("agent_result", {}).get("analysis") or branch_result.get("analysis") or "Repository analysis used live GitHub reads and existing Terraform conventions before writing the branch.",
                "user_fillable": pending.get("agent_result", {}).get("user_fillable") or branch_result.get("user_fillable") or [],
                "branch_reused": bool(branch_result.get("branch_reused")),
                "created_new_branch": bool(branch_result.get("created_new_branch")),
            }, 200

        if action == "create_pr_from_branch":
            pending = get_pending_infra_change_by_id(pending_change_id)
            if not pending:
                return {"ok": False, "mode": "chat", "reply": "No Terrabot branch is waiting for a pull request."}, 400
            if ticket_link and not is_valid_jira_ticket_link(ticket_link):
                return {
                    "ok": False,
                    "mode": "jira_required",
                    "reply": "The supplied Jira ticket link is invalid. Send a valid link or create the PR without one.",
                    "pending_change_id": pending_change_id,
                }, 400
            token = (data.get("github_token") or _ACTIVE_GITHUB_TOKEN.get() or "").strip()
            if not token:
                return {"ok": False, "mode": "github_auth_required", "reply": "Reconnect GitHub before Terrabot raises the pull request."}, 401
            with github_token_context(token):
                pr_result = create_teams_pull_request_from_branch(
                    pending["agent_result"],
                    pending["prompt"],
                    conversation_id,
                    jira_ticket=ticket_number,
                    ticket_link=ticket_link,
                    ticket_title=ticket_title,
                )
            clear_pending_infra_change_by_id(pending_change_id)
            return {
                "ok": True,
                "mode": "pr_created",
                "reply": pr_result["message"],
                "thread_id": conversation_id,
                "branch": pr_result["branch"],
                "branch_url": pr_result.get("branch_url"),
                "compare_url": pr_result.get("compare_url"),
                "pr_number": pr_result["pr_number"],
                "pr_url": pr_result["pr_url"],
                "jira_ticket": ticket_number,
                "ticket_link": ticket_link,
                "summary": pending.get("agent_result", {}).get("summary") or "Terraform pull request created.",
                "analysis": pending.get("agent_result", {}).get("analysis") or "The pull request was created from the current Terrabot branch diff.",
            }, 200

        if action == "commit_pending":
            if not conversation_id:
                return {
                    "ok": False,
                    "mode": "chat",
                    "reply": "No active conversation was found for this JIRA ticket.",
                    "ticket_link": ticket_link,
                    "ticket_number": ticket_number,
                    "ticket_title": ticket_title,
                }, 400

            pending = get_pending_infra_change_by_id(pending_change_id)
            if not pending:
                return {
                    "ok": False,
                    "mode": "chat",
                    "reply": "There are no pending infrastructure changes to commit.",
                    "thread_id": conversation_id,
                    "conversation_label": conversation_label,
                    "jira_ticket": ticket_number,
                    "ticket_number": ticket_number,
                    "ticket_link": ticket_link,
                    "ticket_title": ticket_title,
                }, 400

            pending_thread_id = pending.get("thread_id")
            if pending_thread_id and str(pending_thread_id) != str(conversation_id):
                return {
                    "ok": False,
                    "mode": "chat",
                    "reply": "The pending infrastructure preview belongs to a different thread. Please switch back to that thread and try again.",
                    "thread_id": conversation_id,
                    "conversation_label": conversation_label,
                    "jira_ticket": ticket_number,
                    "ticket_number": ticket_number,
                    "ticket_link": ticket_link,
                    "ticket_title": ticket_title,
                }, 400

            pending_cloud = normalize_cloud(
                pending.get("cloud") or pending.get("agent_result", {}).get("cloud")
            )

            pr_result = commit_terraform_files_to_repo(
                pending["agent_result"],
                pending["prompt"],
                conversation_id,
                jira_ticket=ticket_number,
                ticket_link=ticket_link,
                ticket_title=ticket_title,
            )

            clear_pending_infra_change_by_id(pending_change_id)
            clear_pending_cloud_clarification(conversation_id, ticket_number)
            clear_pending_azure_module_discovery(conversation_id, ticket_number)
            clear_pending_azure_consumer_value_selection(conversation_id, ticket_number)
            clear_pending_azure_new_consumer_file_confirmation(conversation_id, ticket_number)
            clear_pending_module_variable_value_selection(conversation_id, ticket_number)
            clear_pending_aws_module_discovery(conversation_id, ticket_number)
            clear_pending_infra_modification_selection(conversation_id, ticket_number)

            return {
                "ok": True,
                "mode": "infra",
                "reply": pr_result["message"],
                "action": pr_result["action"],
                "thread_id": conversation_id,
                "conversation_label": conversation_label,
                "pr_url": pr_result["pr_url"],
                "pr_number": pr_result["pr_number"],
                "cloud": pending_cloud,
                "branch": pr_result["branch"],
                "folder": pr_result["folder"],
                "jira_ticket": ticket_number,
                "ticket_number": ticket_number,
                "ticket_link": ticket_link,
                "ticket_title": ticket_title,
                "thread_prs": build_thread_prs_payload(conversation_id),
                "target_module_repo_full_name": pr_result.get("target_module_repo_full_name"),
                "target_module_repo_name": pr_result.get("target_module_repo_name"),
            }, 200

        if action == "discard_pending":
            if not conversation_id:
                return {
                    "ok": False,
                    "mode": "chat",
                    "reply": "No active conversation was found for this JIRA ticket.",
                    "ticket_link": ticket_link,
                    "ticket_number": ticket_number,
                    "ticket_title": ticket_title,
                }, 400

            pending = get_pending_infra_change_by_id(pending_change_id)
            if pending and pending.get("thread_id") and str(pending.get("thread_id")) != str(conversation_id):
                return {
                    "ok": False,
                    "mode": "chat",
                    "reply": "That pending infrastructure preview belongs to a different thread.",
                    "thread_id": conversation_id,
                    "conversation_label": conversation_label,
                    "jira_ticket": ticket_number,
                    "ticket_number": ticket_number,
                    "ticket_link": ticket_link,
                    "ticket_title": ticket_title,
                }, 400

            clear_pending_infra_change_by_id(pending_change_id)
            clear_pending_cloud_clarification(conversation_id, ticket_number)
            clear_pending_azure_module_discovery(conversation_id, ticket_number)
            clear_pending_azure_consumer_value_selection(conversation_id, ticket_number)
            clear_pending_azure_new_consumer_file_confirmation(conversation_id, ticket_number)
            clear_pending_module_variable_value_selection(conversation_id, ticket_number)
            clear_pending_aws_module_discovery(conversation_id, ticket_number)
            clear_pending_infra_modification_selection(conversation_id, ticket_number)

            return {
                "ok": True,
                "mode": "chat",
                "reply": "Okay, I did not commit those infrastructure changes.",
                "thread_id": conversation_id,
                "conversation_label": conversation_label,
                "jira_ticket": ticket_number,
                "ticket_number": ticket_number,
                "ticket_link": ticket_link,
                "ticket_title": ticket_title,
                "thread_prs": build_thread_prs_payload(conversation_id),
            }, 200

        recovered_state = recover_thread_pr_state(conversation_id) if conversation_id else {}
        active_clouds = [c for c in ("aws", "azure_module", "azure_module_population", "azure_consumer") if c in recovered_state]
        # Buckets are workflow/repository states, not distinct clouds. A thread
        # can legitimately have several Azure buckets at once. Collapse them
        # to provider identity before deciding whether the current request is
        # actually multicloud.
        active_cloud_providers = {
            "aws" if bucket == "aws" else "azure"
            for bucket in active_clouds
        }

        prompt_lower = normalize_yes_no_reply(prompt)
        cloud_only_reply = prompt_lower in {"aws", "azure"}
        simple_affirmative_reply = prompt_lower in AFFIRMATIVE_REPLIES
        simple_negative_reply = prompt_lower in NEGATIVE_REPLIES

        pending_clarification = None
        effective_prompt = prompt

        pending_azure_discovery = (
            get_pending_azure_module_discovery(conversation_id, ticket_number)
            if conversation_id else None
        )
        pending_azure_discovery_state = (
            ((pending_azure_discovery or {}).get("discovery") or {}).get("decision_state")
            if pending_azure_discovery else ""
        )
        pending_azure_branch_selection = pending_azure_discovery_state == "azure_module_branch_selection"
        pending_azure_reference_confirmation = bool(pending_azure_discovery and not pending_azure_branch_selection)
        pending_azure_selected_match_from_reply = {}
        pending_azure_requested_repo_name = ""
        pending_azure_module_affirmative_reply = False
        pending_azure_module_negative_reply = False

        pending_azure_consumer_values = (
            get_pending_azure_consumer_value_selection(conversation_id, ticket_number)
            if conversation_id else None
        )
        pending_azure_new_consumer_file = (
            get_pending_azure_new_consumer_file_confirmation(conversation_id, ticket_number)
            if conversation_id else None
        )
        pending_azure_new_consumer_file_reply = bool(pending_azure_new_consumer_file)
        pending_azure_consumer_values_reply = bool(pending_azure_consumer_values)
        pending_azure_consumer_values_negative_reply = bool(
            pending_azure_consumer_values
            and (
                simple_negative_reply
                or re.match(r"^(?:no|n|dont|don't|skip|cancel)\b", prompt_lower)
            )
        )

        pending_aws_discovery = (
            get_pending_aws_module_discovery(conversation_id, ticket_number)
            if conversation_id else None
        )
        pending_aws_discovery_payload = (
            ((pending_aws_discovery or {}).get("discovery") or {})
            if pending_aws_discovery else {}
        )
        pending_aws_discovery_state = pending_aws_discovery_payload.get("decision_state") or ""
        pending_aws_module_affirmative_reply = False
        pending_aws_module_negative_reply = False
        pending_aws_selected_match_from_reply = {}
        pending_aws_create_own_module_reply = False

        aws_pending_decision = classify_aws_pending_module_reply(prompt, pending_aws_discovery)
        prefer_aws_pending_reply = aws_pending_decision.force_flow
        if aws_pending_decision.pending:
            pending_aws_module_negative_reply = bool(aws_pending_decision.negative)
            pending_aws_module_affirmative_reply = bool(aws_pending_decision.affirmative)

        if pending_aws_discovery_state == "aws_module_selection":
            pending_matches = pending_aws_discovery_payload.get("matches") or []
            pending_aws_selected_match_from_reply = select_aws_module_match_from_reply(prompt, pending_matches)
            pending_aws_create_own_module_reply = _aws_module_selection_requests_new_module(prompt, pending_matches)
            pending_aws_module_negative_reply = bool(
                simple_negative_reply
                or re.match(r"^(?:no|n|dont|don't|skip|cancel)\b", prompt_lower)
            )
            pending_aws_module_affirmative_reply = bool(
                pending_aws_selected_match_from_reply
                or pending_aws_create_own_module_reply
                or simple_affirmative_reply
                or re.match(r"^(?:yes|y|use|select|choose|pick)\b", prompt_lower)
            )
            prefer_aws_pending_reply = bool(pending_aws_module_negative_reply or pending_aws_module_affirmative_reply)

        has_any_pending_workflow = bool(
            pending_azure_discovery
            or pending_azure_consumer_values
            or pending_azure_new_consumer_file
            or pending_aws_discovery
        )

        # AWS module confirmation owns yes/no replies when it is active. Clear
        # stale Azure value/new-consumer state so a simple "yes" cannot be
        # misread as an Azure consumer value-selection reply.
        if pending_aws_discovery and (pending_aws_module_affirmative_reply or pending_aws_module_negative_reply):
            if pending_azure_consumer_values_reply:
                clear_pending_azure_consumer_value_selection(conversation_id, ticket_number)
                pending_azure_consumer_values = None
                pending_azure_consumer_values_reply = False
                pending_azure_consumer_values_negative_reply = False
            if pending_azure_new_consumer_file_reply:
                clear_pending_azure_new_consumer_file_confirmation(conversation_id, ticket_number)
                pending_azure_new_consumer_file = None
                pending_azure_new_consumer_file_reply = False

        if (
            should_block_missing_azure_value_context(prompt, pending_azure_consumer_values_reply)
            and not prefer_aws_pending_reply
            and not pending_azure_new_consumer_file_reply
            and not pending_azure_discovery
        ):
            return {
                "ok": False,
                "mode": "clarification",
                "reply": (
                    "I received Azure module variable values, but there is no active Azure consumer value-selection context for this ticket. "
                    "Please restart the Azure module selection flow or reply in the same thread after Terrabot asks for variable values."
                ),
                "thread_id": conversation_id,
                "conversation_label": conversation_label,
                "jira_ticket": ticket_number,
                "ticket_number": ticket_number,
                "ticket_link": ticket_link,
                "ticket_title": ticket_title,
                "decision_state": "azure_consumer_value_selection_missing",
                "thread_prs": build_thread_prs_payload(conversation_id) if conversation_id else {},
            }, 400

        if pending_azure_reference_confirmation and not prefer_aws_pending_reply:
            pending_discovery_payload = (pending_azure_discovery or {}).get("discovery") or {}
            pending_status = pending_discovery_payload.get("status")
            pending_matches = pending_discovery_payload.get("matches") or []

            pending_azure_module_negative_reply = bool(
                simple_negative_reply
                or re.match(r"^(?:no|n|dont|don't|skip|cancel)\b", prompt_lower)
            )

            if pending_status in {"exact_match", "similar_match"} or pending_matches:
                pending_azure_selected_match_from_reply = select_azure_module_match_from_reply(
                    prompt,
                    pending_matches,
                )
                pending_azure_module_affirmative_reply = bool(
                    simple_affirmative_reply
                    or pending_azure_selected_match_from_reply
                    or re.match(r"^(?:yes|y|use|select|choose|pick)\b", prompt_lower)
                )
            elif pending_status == "not_found":
                pending_azure_requested_repo_name = extract_azure_module_repo_name_from_confirmation_reply(prompt)
                pending_azure_module_affirmative_reply = bool(
                    simple_affirmative_reply
                    or pending_azure_requested_repo_name
                    or re.match(r"^(?:yes|y|create|make|build|proceed|go ahead|continue)\b", prompt_lower)
                )

        if should_handle_cloud_only_clarification(cloud_only_reply, has_any_pending_workflow) and conversation_id:
            pending_clarification = get_pending_cloud_clarification(conversation_id, ticket_number)
            if pending_clarification:
                requested_cloud = prompt_lower
                requested_mode = "infra"
                effective_prompt = pending_clarification.get("original_prompt") or prompt

                if not ticket_link:
                    ticket_link = pending_clarification.get("ticket_link") or ticket_link
                if not ticket_title:
                    ticket_title = pending_clarification.get("ticket_title") or ticket_title

                conversation_label = build_enhanced_conversation_label(
                    ticket_number=ticket_number,
                    ticket_title=ticket_title,
                    conversation_id=conversation_id,
                )

        if pending_azure_new_consumer_file_reply and not pending_azure_consumer_values_reply and not prefer_aws_pending_reply:
            pending_routing_context = (pending_azure_new_consumer_file or {}).get("routing_context") or {}
            if simple_negative_reply:
                clear_pending_azure_new_consumer_file_confirmation(conversation_id, ticket_number)
                return {
                    "ok": True,
                    "mode": "chat",
                    "reply": _cancel_new_azure_consumer_file_reply(),
                    "thread_id": conversation_id,
                    "conversation_label": conversation_label,
                    "jira_ticket": ticket_number,
                    "ticket_number": ticket_number,
                    "ticket_link": ticket_link,
                    "ticket_title": ticket_title,
                    "thread_prs": build_thread_prs_payload(conversation_id),
                }, 200
            if not simple_affirmative_reply:
                return {
                    "ok": False,
                    "mode": "clarification",
                    "reply": build_azure_new_consumer_file_confirmation_reply(pending_routing_context),
                    "thread_id": conversation_id,
                    "conversation_label": conversation_label,
                    "jira_ticket": ticket_number,
                    "ticket_number": ticket_number,
                    "ticket_link": ticket_link,
                    "ticket_title": ticket_title,
                    "decision_state": "azure_new_consumer_file_confirmation",
                }, 400

            requested_mode = "infra"
            requested_cloud = "azure"
            requested_workflow = "azure_consumer_generation"
            effective_prompt = pending_azure_new_consumer_file.get("original_prompt") or prompt
            retrieved_module_context = coerce_context_list(pending_azure_new_consumer_file.get("retrieved_module_context"))
            retrieved_value_context = coerce_context_list(pending_azure_new_consumer_file.get("retrieved_value_context"))
            retrieved_value_context.append(_confirm_new_azure_consumer_file_routing_context(pending_routing_context))
            clear_pending_azure_new_consumer_file_confirmation(conversation_id, ticket_number)

            if not ticket_link:
                ticket_link = pending_azure_new_consumer_file.get("ticket_link") or ticket_link
            if not ticket_title:
                ticket_title = pending_azure_new_consumer_file.get("ticket_title") or ticket_title

            conversation_label = build_enhanced_conversation_label(
                ticket_number=ticket_number,
                ticket_title=ticket_title,
                conversation_id=conversation_id,
            )

        if pending_azure_consumer_values_reply:
            if pending_azure_consumer_values_negative_reply:
                clear_pending_azure_consumer_value_selection(conversation_id, ticket_number)
                return {
                    "ok": True,
                    "mode": "chat",
                    "reply": "Okay, I did not generate the Azure consumer PR preview.",
                    "thread_id": conversation_id,
                    "conversation_label": conversation_label,
                    "jira_ticket": ticket_number,
                    "ticket_number": ticket_number,
                    "ticket_link": ticket_link,
                    "ticket_title": ticket_title,
                    "thread_prs": build_thread_prs_payload(conversation_id),
                }, 200

            requested_mode = "infra"
            requested_cloud = "azure"
            requested_workflow = "azure_consumer_generation"
            effective_prompt = (
                (pending_azure_consumer_values.get("original_prompt") or "").strip()
                + "\n\nUser variable value selection reply:\n"
                + prompt.strip()
            ).strip()
            retrieved_module_context = coerce_context_list(pending_azure_consumer_values.get("retrieved_module_context"))
            retrieved_value_context = _with_azure_consumer_value_selection_confirmation(
                coerce_context_list(pending_azure_consumer_values.get("retrieved_value_context")),
                prompt,
            )

            if not ticket_link:
                ticket_link = pending_azure_consumer_values.get("ticket_link") or ticket_link
            if not ticket_title:
                ticket_title = pending_azure_consumer_values.get("ticket_title") or ticket_title

            conversation_label = build_enhanced_conversation_label(
                ticket_number=ticket_number,
                ticket_title=ticket_title,
                conversation_id=conversation_id,
            )

        if pending_azure_discovery and not prefer_aws_pending_reply and not pending_azure_consumer_values_reply and (pending_azure_branch_selection or pending_azure_module_affirmative_reply or pending_azure_module_negative_reply):
            requested_mode = "infra"
            requested_cloud = "azure"
            effective_prompt = pending_azure_discovery.get("original_prompt") or prompt

            if not ticket_link:
                ticket_link = pending_azure_discovery.get("ticket_link") or ticket_link
            if not ticket_title:
                ticket_title = pending_azure_discovery.get("ticket_title") or ticket_title

            conversation_label = build_enhanced_conversation_label(
                ticket_number=ticket_number,
                ticket_title=ticket_title,
                conversation_id=conversation_id,
            )

        if pending_aws_discovery and (pending_aws_module_affirmative_reply or pending_aws_module_negative_reply):
            requested_mode = "infra"
            requested_cloud = "aws"
            effective_prompt = pending_aws_discovery.get("original_prompt") or prompt

            if not ticket_link:
                ticket_link = pending_aws_discovery.get("ticket_link") or ticket_link
            if not ticket_title:
                ticket_title = pending_aws_discovery.get("ticket_title") or ticket_title

            conversation_label = build_enhanced_conversation_label(
                ticket_number=ticket_number,
                ticket_title=ticket_title,
                conversation_id=conversation_id,
            )

        pending_infra_mod_selection = (
            get_pending_infra_modification_selection(conversation_id, ticket_number)
            if conversation_id else {}
        )
        force_pending_infra_modification_selection_flow = False
        # AWS module selection is a more specific pending protocol than the
        # generic infrastructure target picker. A numeric module option can
        # otherwise be consumed by a stale PENDING_INFRA_MODIFICATION_SELECTIONS
        # entry first, which re-renders another picker forever and prevents the
        # selected-module Foundry generation call from ever being reached.
        if pending_infra_mod_selection and prefer_aws_pending_reply:
            clear_pending_infra_modification_selection(conversation_id, ticket_number)
            pending_infra_mod_selection = {}
        if pending_infra_mod_selection:
            selected_index = select_infra_modification_candidate_from_reply(prompt, pending_infra_mod_selection)
            if selected_index is None:
                # Creation requests must not force the user to choose repository
                # structure that Terrabot can resolve from live GitHub evidence.
                # In particular, an Azure object-backed creation such as
                # "create storageaccount1 in sbx-infra" must automatically use
                # the best resource-family file (for example storage_accounts.tf),
                # then materialize the dedicated variables.tf + environment
                # hub.tfvars additions. A user reply such as "add a dedicated
                # object-root variable" is therefore treated as continuation,
                # not as an invalid target-picker reply.
                pending_original_prompt = str(
                    pending_infra_mod_selection.get("original_prompt") or ""
                ).strip()
                pending_candidates = (
                    (pending_infra_mod_selection.get("existing_infra_context") or {})
                    .get("matched_files") or []
                )
                if (
                    pending_candidates
                    and _teams_is_existing_invocation_creation(pending_original_prompt)
                ):
                    selected_index = 0
                else:
                    pending_existing_context = pending_infra_mod_selection.get("existing_infra_context") or {}
                    if pending_existing_context.get("feature_flag_selection"):
                        selection_prefix = "Please select one of the listed feature flags by option number or exact flag name.\n\n"
                    else:
                        selection_prefix = "Please select one of the listed Terraform targets by option number or exact path.\n\n"
                    return {
                        "ok": False,
                        "mode": "clarification",
                        "reply": (
                            selection_prefix
                            + build_infra_modification_selection_reply(
                                pending_existing_context
                            )
                        ),
                        "thread_id": conversation_id,
                        "conversation_label": conversation_label,
                        "jira_ticket": ticket_number,
                        "ticket_number": ticket_number,
                        "ticket_link": ticket_link,
                        "ticket_title": ticket_title,
                        "decision_state": "infra_modification_target_selection",
                    }, 400

            selected_context = build_selected_infra_modification_context(
                pending_infra_mod_selection,
                selected_index,
            )
            effective_prompt = pending_infra_mod_selection.get("original_prompt") or effective_prompt
            requested_mode = "infra"
            requested_cloud = pending_infra_mod_selection.get("cloud") or requested_cloud
            requested_workflow = pending_infra_mod_selection.get("workflow") or requested_workflow
            retrieved_module_context = filter_backend_owned_context_list(
                pending_infra_mod_selection.get("retrieved_module_context") or [],
                context_name="retrieved_module_context",
            )
            retrieved_value_context = _remove_backend_existing_infra_contexts(
                filter_backend_owned_context_list(
                    pending_infra_mod_selection.get("retrieved_value_context") or [],
                    context_name="retrieved_value_context",
                )
            )
            retrieved_value_context.append(selected_context)
            if not ticket_link:
                ticket_link = pending_infra_mod_selection.get("ticket_link") or ticket_link
            if not ticket_title:
                ticket_title = pending_infra_mod_selection.get("ticket_title") or ticket_title
            conversation_label = build_enhanced_conversation_label(
                ticket_number=ticket_number,
                ticket_title=ticket_title,
                conversation_id=conversation_id,
            )
            clear_pending_infra_modification_selection(conversation_id, ticket_number)
            force_pending_infra_modification_selection_flow = True

        force_pending_azure_new_consumer_file_flow = bool(
            pending_azure_new_consumer_file_reply
            and not prefer_aws_pending_reply
            and not pending_azure_consumer_values_reply
            and simple_affirmative_reply
        )

        force_pending_azure_consumer_values_flow = bool(
            pending_azure_consumer_values_reply
            and not prefer_aws_pending_reply
            and not pending_azure_consumer_values_negative_reply
        )

        force_pending_azure_module_flow = bool(
            pending_azure_discovery
            and not prefer_aws_pending_reply
            and not force_pending_azure_consumer_values_flow
            and (
                pending_azure_branch_selection
                or pending_azure_module_affirmative_reply
                or pending_azure_module_negative_reply
            )
        )

        force_pending_aws_module_flow = bool(
            pending_aws_discovery
            and (
                pending_aws_module_affirmative_reply
                or pending_aws_module_negative_reply
            )
        )

        if force_pending_infra_modification_selection_flow:
            router_decision = NormalizedRouterDecision(
                request_type="infra",
                cloud=requested_cloud,
                workflow=requested_workflow,
                reason="Pending infrastructure modification target selection confirmed by user.",
            )
        elif force_pending_aws_module_flow:
            router_decision = NormalizedRouterDecision(
                request_type="infra",
                cloud="aws",
                workflow=pending_aws_discovery_state or "aws_module_creation_confirmation",
                reason="Pending AWS module selection/confirmation handled by backend.",
            )
        elif force_pending_azure_new_consumer_file_flow:
            router_decision = NormalizedRouterDecision(
                request_type="infra",
                cloud="azure",
                workflow="azure_consumer_generation",
                reason="Pending Azure new consumer file confirmation accepted by user.",
            )
        elif force_pending_azure_consumer_values_flow:
            router_decision = NormalizedRouterDecision(
                request_type="infra",
                cloud="azure",
                workflow="azure_consumer_generation",
                reason="Pending Azure consumer variable value selection confirmed by user.",
            )
        elif force_pending_azure_module_flow:
            # Keep Azure module discovery and branch selection backend-only.
            # Branch names and variables are read from GitHub APIs only.
            router_decision = NormalizedRouterDecision(
                request_type="infra",
                cloud="azure",
                workflow=pending_azure_discovery_state or "azure_module_discovery",
                reason="Pending Azure module discovery/branch selection handled by backend.",
            )
        else:
            router_decision = normalize_router_decision(
                prompt=effective_prompt,
                requested_mode=requested_mode,
                requested_cloud=requested_cloud,
                recovered_state=recovered_state,
                thread_id=conversation_id,
            )

        if router_decision.request_type == "chat":
            conversation_id, reply = call_agent(conversation_id, prompt)

            if not reply.strip():
                reply = "No response returned from agent."

            conversation_label = build_enhanced_conversation_label(
                ticket_number=ticket_number,
                ticket_title=ticket_title,
                conversation_id=conversation_id,
            )

            try:
                if agent_reply_looks_like_infra_json(reply) or looks_like_infra_payload(reply):
                    agent_result = try_parse_agent_output(reply)

                    agent_result = finalize_agent_result_after_parse(
                         agent_result,
                         retrieved_module_context,
                         retrieved_value_context,
                    )

                    pending_key = store_pending_infra_change(
                        conversation_id,
                        ticket_number,
                        repo_creation_prompt,
                        agent_result,
                        ticket_link=ticket_link,
                        ticket_title=ticket_title,
                    )

                    clear_pending_cloud_clarification(conversation_id, ticket_number)
                    clear_pending_azure_module_discovery(conversation_id, ticket_number)
                    clear_pending_azure_consumer_value_selection(conversation_id, ticket_number)
                    clear_pending_aws_module_discovery(conversation_id, ticket_number)

                    return {
                        "ok": True,
                        "mode": "infra_preview",
                        "reply": "Terraform changes are ready. Do you want to commit these changes to the PR?",
                        "thread_id": conversation_id,
                        "conversation_label": conversation_label,
                        "jira_ticket": ticket_number,
                        "ticket_number": ticket_number,
                        "ticket_link": ticket_link,
                        "ticket_title": ticket_title,
                        "pending_change_id": pending_key,
                        "cloud": agent_result["cloud"],
                        "repo_target": agent_result["repo_target"],
                        "state_bucket": agent_result["state_bucket"],
                        "target_module_repo_full_name": agent_result.get("target_module_repo_full_name"),
                        "target_module_repo_name": agent_result.get("target_module_repo_name"),
                        "title": agent_result["title"],
                        "summary": agent_result["summary"],
                        "files": [f["filename"] for f in agent_result["files"]],
                        "thread_prs": build_thread_prs_payload(conversation_id),
                        "router": {
                            "request_type": "infra",
                            "cloud": agent_result["cloud"],
                            "workflow": "converted_from_chat_reply",
                            "reason": "agent returned terraform payload after clarification/cloud selection",
                        },
                    }, 200
            except Exception as infra_parse_error:
                return {
                    "ok": False,
                    "mode": "clarification",
                    "reply": build_user_friendly_error(str(infra_parse_error)),
                    "thread_id": conversation_id,
                    "conversation_label": conversation_label,
                    "jira_ticket": ticket_number,
                    "ticket_number": ticket_number,
                    "ticket_link": ticket_link,
                    "ticket_title": ticket_title,
                }, 400

            return {
                "ok": True,
                "mode": "chat",
                "reply": reply,
                "thread_id": conversation_id,
                "conversation_label": conversation_label,
                "jira_ticket": ticket_number,
                "ticket_number": ticket_number,
                "ticket_link": ticket_link,
                "ticket_title": ticket_title,
                "thread_prs": build_thread_prs_payload(conversation_id) if conversation_id else {},
                "router": {
                    "request_type": router_decision.request_type,
                    "cloud": router_decision.cloud,
                    "workflow": router_decision.workflow,
                    "reason": router_decision.reason,
                },
            }, 200

        if router_decision.workflow == "clarification_required":
            clarification_reply = build_router_response_message(router_decision)

            if conversation_id:
                store_pending_cloud_clarification(
                    thread_id=conversation_id,
                    ticket_number=ticket_number,
                    original_prompt=effective_prompt,
                    requested_mode=requested_mode,
                    requested_cloud=requested_cloud or "",
                    ticket_link=ticket_link,
                    ticket_title=ticket_title,
                )

            return {
                "ok": False,
                "mode": "clarification",
                "reply": clarification_reply,
                "thread_id": conversation_id,
                "conversation_label": conversation_label,
                "jira_ticket": ticket_number,
                "ticket_number": ticket_number,
                "ticket_link": ticket_link,
                "ticket_title": ticket_title,
                "router": {
                    "request_type": router_decision.request_type,
                    "cloud": router_decision.cloud,
                    "workflow": router_decision.workflow,
                    "reason": router_decision.reason,
                },
            }, 400

        target_cloud = safe_normalize_cloud(requested_cloud) or router_decision.cloud

        # Teams continuation/control replies (for example target option "2")
        # carry request identity out-of-band. If an older wrapper failed to
        # propagate cloud, recover it from the restored original request and
        # the thread's last selected provider before considering multicloud
        # ambiguity. Parallel AWS/Azure PRs are normal and must never override
        # the cloud already bound to the active request.
        if request_source == "teams" and not target_cloud:
            for cloud_source in (
                data.get("requested_cloud"),
                data.get("cloud"),
                infer_cloud_from_prompt(str(data.get("original_prompt") or "")),
                infer_cloud_from_prompt(effective_prompt),
                (ensure_thread_meta(conversation_id).get("last_selected_cloud") if conversation_id else ""),
            ):
                target_cloud = safe_normalize_cloud(cloud_source)
                if target_cloud:
                    break

        if target_cloud and conversation_id:
            set_last_selected_cloud(conversation_id, target_cloud)

        # The legacy "both AWS and Azure PRs" guard is intentionally disabled
        # for Teams. Foundry/router clarification already handles genuinely
        # cloud-ambiguous *new* requests, while active Teams workflows bind a
        # cloud before branch/target selection. Using historical PR state as a
        # routing veto here caused valid numeric target selections to fail.
        if request_source != "teams" and len(active_cloud_providers) == 2 and not target_cloud:
            return {
                "ok": False,
                "mode": "clarification",
                "reply": (
                    "This thread has both AWS and Azure PRs. "
                    "Please specify which cloud to update, for example: "
                    "'update AWS instance name' or 'update Azure VM name'."
                ),
                "thread_id": conversation_id,
                "conversation_label": conversation_label,
                "jira_ticket": ticket_number,
                "ticket_number": ticket_number,
                "ticket_link": ticket_link,
                "ticket_title": ticket_title,
            }, 400

        effective_workflow = infer_generation_workflow(
            effective_prompt,
            target_cloud,
            requested_workflow=requested_workflow,
        ) or router_decision.workflow

        if router_decision.request_type == "infra":
            if not conversation_id:
                conversation_id, _ = call_agent(None, "Initialize infrastructure conversation context.")

            if target_cloud:
                set_last_selected_cloud(conversation_id, target_cloud)

            if target_cloud == "azure":
                if pending_azure_discovery and not pending_azure_consumer_values_reply and pending_azure_module_negative_reply:
                     discovery = pending_azure_discovery.get("discovery") or {}
                     clear_pending_azure_module_discovery(conversation_id, ticket_number)
                     clear_pending_azure_consumer_value_selection(conversation_id, ticket_number)

                     if discovery.get("status") == "not_found":
                        clear_pending_cloud_clarification(conversation_id, ticket_number)
                        return {
                            "ok": True,
                            "mode": "chat",
                            "reply": "Okay, I did not create a new Azure module repo or PR preview.",
                            "thread_id": conversation_id,
                            "conversation_label": conversation_label,
                            "jira_ticket": ticket_number,
                            "ticket_number": ticket_number,
                            "ticket_link": ticket_link,
                            "ticket_title": ticket_title,
                            "thread_prs": build_thread_prs_payload(conversation_id),
                        }, 200

                     requested_repo_name = extract_azure_module_repo_name_from_confirmation_reply(prompt)
                     repo_creation_prompt = build_azure_module_creation_prompt_with_repo_name(
                             effective_prompt,
                             requested_repo_name or prompt,
                     )

                     agent_result = generate_azure_module_repo_creation_with_agent(
                              conversation_id=conversation_id,
                             original_prompt=repo_creation_prompt,
                             requested_repo_name=requested_repo_name,
                     )

                     pending_key = store_pending_infra_change(
                        conversation_id,
                        ticket_number,
                        repo_creation_prompt,
                        agent_result,
                        ticket_link=ticket_link,
                        ticket_title=ticket_title,
                     )

                     clear_pending_cloud_clarification(conversation_id, ticket_number)

                     return {
                        "ok": True,
                        "mode": "infra_preview",
                        "reply": "You chose not to use the existing Azure module. Module repo creation is ready. Do you want to commit this vena_repos PR?",
                        "thread_id": conversation_id,
                        "conversation_label": conversation_label,
                        "jira_ticket": ticket_number,
                        "ticket_number": ticket_number,
                        "ticket_link": ticket_link,
                        "ticket_title": ticket_title,
                        "pending_change_id": pending_key,
                        "cloud": "azure",
                        "workflow": "azure_module_repo_creation",
                        "title": agent_result["title"],
                        "summary": agent_result["summary"],
                        "files": [f["filename"] for f in agent_result["files"]],
                        "repo_target": agent_result["repo_target"],
                        "state_bucket": agent_result["state_bucket"],
                        "target_module_repo_full_name": agent_result.get("target_module_repo_full_name"),
                        "target_module_repo_name": agent_result.get("target_module_repo_name"),
                        "thread_prs": build_thread_prs_payload(conversation_id),
                     }, 200
                if pending_azure_discovery and not pending_azure_consumer_values_reply and pending_azure_branch_selection:
                    discovery = pending_azure_discovery.get("discovery") or {}
                    selected_match = get_first_azure_module_match(discovery)
                    branch_options = discovery.get("branch_options") or []
                    selected_branch = select_azure_module_branch_from_reply(
                        prompt,
                        branch_options,
                    )

                    selected_from_list = any(
                        isinstance(option, dict)
                        and str(option.get("branch") or "").strip() == selected_branch
                        for option in branch_options
                    )

                    if selected_branch and not selected_from_list:
                        selected_branch = resolve_manual_azure_module_branch_from_reply(
                            selected_branch,
                            selected_match,
                        )

                    if not selected_branch:
                        selected_branch = resolve_manual_azure_module_branch_from_reply(
                            prompt,
                            selected_match,
                        )

                    if not selected_branch:
                        return {
                            "ok": False,
                            "mode": "clarification",
                            "reply": build_azure_module_branch_selection_reply(discovery),
                            "thread_id": conversation_id,
                            "conversation_label": conversation_label,
                            "jira_ticket": ticket_number,
                            "ticket_number": ticket_number,
                            "ticket_link": ticket_link,
                            "ticket_title": ticket_title,
                            "router": {
                                "request_type": "infra",
                                "cloud": "azure",
                                "workflow": "azure_module_branch_selection",
                                "reason": "A valid Azure module branch selection is required.",
                            },
                            "decision_state": "azure_module_branch_selection",
                            "azure_module_discovery": discovery,
                        }, 400

                    candidate_module_context, candidate_value_context = add_grounded_azure_context_for_match(
                        selected_match,
                        selected_module_ref=selected_branch,
                        retrieved_module_context=retrieved_module_context,
                        retrieved_value_context=retrieved_value_context,
                    )

                    selected_repo_full_name = selected_match.get("repo_full_name") or ""
                    if not azure_context_has_verified_inputs_for_branch(
                        candidate_module_context,
                        selected_repo_full_name,
                        selected_branch,
                    ):
                        return {
                            "ok": False,
                            "mode": "clarification",
                            "reply": (
                                f"I checked branch '{selected_branch}' for {selected_repo_full_name}, "
                                "but no Terraform module inputs were found there. "
                                "Please choose a different branch that contains variables.tf/module inputs.\n\n"
                                + build_azure_module_branch_selection_reply(discovery)
                            ),
                            "thread_id": conversation_id,
                            "conversation_label": conversation_label,
                            "jira_ticket": ticket_number,
                            "ticket_number": ticket_number,
                            "ticket_link": ticket_link,
                            "ticket_title": ticket_title,
                            "router": {
                                "request_type": "infra",
                                "cloud": "azure",
                                "workflow": "azure_module_branch_selection",
                                "reason": "Selected branch had no verified module inputs.",
                            },
                            "decision_state": "azure_module_branch_selection",
                            "azure_module_discovery": discovery,
                        }, 400

                    clear_pending_azure_module_discovery(conversation_id, ticket_number)
                    clear_pending_azure_consumer_value_selection(conversation_id, ticket_number)
                    retrieved_module_context = candidate_module_context
                    retrieved_value_context = candidate_value_context
                    effective_workflow = "azure_consumer_generation"

                    retrieved_module_context, retrieved_value_context, routing_context = augment_azure_consumer_generation_context(
                        prompt=effective_prompt,
                        thread_id=conversation_id,
                        retrieved_module_context=retrieved_module_context,
                        retrieved_value_context=retrieved_value_context,
                    )

                    if routing_context and routing_context.get("source") == "backend_new_azure_consumer_file_confirmation_required":
                        store_pending_azure_new_consumer_file_confirmation(
                            thread_id=conversation_id,
                            ticket_number=ticket_number,
                            original_prompt=effective_prompt,
                            retrieved_module_context=retrieved_module_context,
                            retrieved_value_context=[
                                item for item in list(retrieved_value_context or [])
                                if not (isinstance(item, dict) and item.get("source") == "backend_new_azure_consumer_file_confirmation_required")
                            ],
                            routing_context=routing_context,
                            ticket_link=ticket_link,
                            ticket_title=ticket_title,
                        )
                        return {
                            "ok": False,
                            "mode": "clarification",
                            "reply": build_azure_new_consumer_file_confirmation_reply(routing_context),
                            "thread_id": conversation_id,
                            "conversation_label": conversation_label,
                            "jira_ticket": ticket_number,
                            "ticket_number": ticket_number,
                            "ticket_link": ticket_link,
                            "ticket_title": ticket_title,
                            "router": {
                                "request_type": "infra",
                                "cloud": "azure",
                                "workflow": "azure_new_consumer_file_confirmation",
                                "reason": "No tf-azure-hub file uses the selected module source; user must confirm new consumer file creation.",
                            },
                            "decision_state": "azure_new_consumer_file_confirmation",
                            "target_consumer_file": routing_context.get("target_consumer_filename"),
                            "target_tfvars_file": routing_context.get("target_tfvars_filename"),
                            "module_source_url": routing_context.get("module_source_url"),
                        }, 400

                    if routing_context and not _azure_consumer_value_selection_confirmed(retrieved_value_context):
                        store_pending_azure_consumer_value_selection(
                            thread_id=conversation_id,
                            ticket_number=ticket_number,
                            original_prompt=effective_prompt,
                            retrieved_module_context=retrieved_module_context,
                            retrieved_value_context=retrieved_value_context,
                            ticket_link=ticket_link,
                            ticket_title=ticket_title,
                        )

                        return {
                            "ok": False,
                            "mode": "clarification",
                            "reply": build_azure_consumer_variable_values_reply(
                                routing_context,
                                _get_primary_azure_module_context(retrieved_module_context),
                            ),
                            "thread_id": conversation_id,
                            "conversation_label": conversation_label,
                            "jira_ticket": ticket_number,
                            "ticket_number": ticket_number,
                            "ticket_link": ticket_link,
                            "ticket_title": ticket_title,
                            "router": {
                                "request_type": "infra",
                                "cloud": "azure",
                                "workflow": "azure_consumer_value_selection",
                                "reason": "Azure consumer module file and tfvars file were routed; values must be confirmed before generation.",
                            },
                            "decision_state": "azure_consumer_value_selection",
                            "target_consumer_file": routing_context.get("target_consumer_filename"),
                            "target_tfvars_file": routing_context.get("target_tfvars_filename"),
                            "value_selection_form": build_azure_consumer_value_selection_form(
                                routing_context,
                                _get_primary_azure_module_context(retrieved_module_context),
                            ),
                        }, 400

                if pending_azure_discovery and not pending_azure_consumer_values_reply and pending_azure_module_affirmative_reply and not pending_azure_branch_selection:
                    discovery = pending_azure_discovery.get("discovery") or {}

                    if discovery.get("status") in {"exact_match", "similar_match"} or (discovery.get("matches") or []):
                        first_match = pending_azure_selected_match_from_reply or get_first_azure_module_match(discovery)
                        branch_discovery = build_azure_module_branch_discovery(discovery, first_match)

                        store_pending_azure_module_discovery(
                            thread_id=conversation_id,
                            ticket_number=ticket_number,
                            original_prompt=effective_prompt,
                            discovery=branch_discovery,
                            ticket_link=ticket_link,
                            ticket_title=ticket_title,
                        )

                        return {
                            "ok": False,
                            "mode": "clarification",
                            "reply": build_azure_module_branch_selection_reply(branch_discovery),
                            "thread_id": conversation_id,
                            "conversation_label": conversation_label,
                            "jira_ticket": ticket_number,
                            "ticket_number": ticket_number,
                            "ticket_link": ticket_link,
                            "ticket_title": ticket_title,
                            "router": {
                                "request_type": "infra",
                                "cloud": "azure",
                                "workflow": "azure_module_branch_selection",
                                "reason": "Azure module repo branch selection is required.",
                            },
                            "decision_state": "azure_module_branch_selection",
                            "azure_module_discovery": branch_discovery,
                        }, 400

                    elif discovery.get("status") == "not_found":
                      requested_repo_name = pending_azure_requested_repo_name or extract_azure_module_repo_name_from_confirmation_reply(prompt)
                      repo_creation_prompt = build_azure_module_creation_prompt_with_repo_name(
                         effective_prompt,
                         requested_repo_name or prompt,
                      )

                      agent_result = generate_azure_module_repo_creation_with_agent(
                         conversation_id=conversation_id,
                         original_prompt=repo_creation_prompt,
                         requested_repo_name=requested_repo_name,
                      )
 
                      pending_key = store_pending_infra_change(
                      conversation_id,
                      ticket_number,
                      repo_creation_prompt,
                      agent_result,
                      ticket_link=ticket_link,
                      ticket_title=ticket_title,
                      )

                      clear_pending_cloud_clarification(conversation_id, ticket_number)
                      clear_pending_azure_module_discovery(conversation_id, ticket_number)
                      clear_pending_azure_consumer_value_selection(conversation_id, ticket_number)

                      return {
                         "ok": True,
                          "mode": "infra_preview",
                         "reply": "Module repo creation is ready. Do you want to commit this vena_repos PR?",
                         "thread_id": conversation_id,
                          "conversation_label": conversation_label,
                         "jira_ticket": ticket_number,
                         "ticket_number": ticket_number,
                         "ticket_link": ticket_link,
                         "ticket_title": ticket_title,
                         "pending_change_id": pending_key,
                         "cloud": "azure",
                         "workflow": "azure_module_repo_creation",
                         "title": agent_result["title"],
                         "summary": agent_result["summary"],
                         "files": [f["filename"] for f in agent_result["files"]],
                         "repo_target": agent_result["repo_target"],
                         "state_bucket": agent_result["state_bucket"],
                         "target_module_repo_full_name": agent_result.get("target_module_repo_full_name"),
                          "target_module_repo_name": agent_result.get("target_module_repo_name"),
                         "thread_prs": build_thread_prs_payload(conversation_id),
                      }, 200

                if (
                    effective_workflow == "azure_module_repo_creation"
                    and not pending_azure_discovery
                ):
                    requested_repo_name = extract_requested_azure_module_repo_name(effective_prompt)
                    repo_creation_prompt = build_azure_module_creation_prompt_with_repo_name(
                        effective_prompt,
                        requested_repo_name,
                    )
                    agent_result = generate_azure_module_repo_creation_with_agent(
                        conversation_id=conversation_id,
                        original_prompt=repo_creation_prompt,
                        requested_repo_name=requested_repo_name,
                    )

                    pending_key = store_pending_infra_change(
                        conversation_id,
                        ticket_number,
                        repo_creation_prompt,
                        agent_result,
                        ticket_link=ticket_link,
                        ticket_title=ticket_title,
                    )

                    clear_pending_cloud_clarification(conversation_id, ticket_number)
                    clear_pending_azure_module_discovery(conversation_id, ticket_number)
                    clear_pending_azure_consumer_value_selection(conversation_id, ticket_number)

                    return {
                        "ok": True,
                        "mode": "infra_preview",
                        "reply": "Module repo creation is ready. Do you want to commit this vena_repos PR?",
                        "thread_id": conversation_id,
                        "conversation_label": conversation_label,
                        "jira_ticket": ticket_number,
                        "ticket_number": ticket_number,
                        "ticket_link": ticket_link,
                        "ticket_title": ticket_title,
                        "pending_change_id": pending_key,
                        "cloud": "azure",
                        "workflow": "azure_module_repo_creation",
                        "title": agent_result["title"],
                        "summary": agent_result["summary"],
                        "files": [f["filename"] for f in agent_result["files"]],
                        "repo_target": agent_result["repo_target"],
                        "state_bucket": agent_result["state_bucket"],
                        "target_module_repo_full_name": agent_result.get("target_module_repo_full_name"),
                        "target_module_repo_name": agent_result.get("target_module_repo_name"),
                        "thread_prs": build_thread_prs_payload(conversation_id),
                    }, 200

                # Azure module-repository discovery is a creation/consumer workflow only.
                # Existing-infrastructure modifications (including feature-flag enable/disable)
                # must continue to live tf-azure-hub target discovery instead of falling into
                # the vena_repos "create a new module repo" branch.
                should_run_azure_discovery = (
                    effective_workflow in {"azure_module_discovery", "azure_consumer_generation"}
                    and effective_workflow not in INFRA_MODIFICATION_WORKFLOWS
                    and not pending_azure_discovery
                    and "azure_consumer" not in recovered_state
                    and "azure_module" not in recovered_state
                    and not retrieved_module_context
                )

                if should_run_azure_discovery:
                    discovery_roots = []

                    configured_vena_dir = (GITHUB_VENA_DIR or "").strip().strip("/")
                    if configured_vena_dir:
                        discovery_roots.append(configured_vena_dir)

    # Canonical path inside terraform-github.
                    if "vena_repos" not in discovery_roots:
                        discovery_roots.append("vena_repos")

    # Fallback only, for repos where files are unexpectedly at root.
                    if "." not in discovery_roots:
                        discovery_roots.append(".")

                    discovery = {
                       "status": "not_found",
                       "decision_state": "azure_module_repo_creation_confirmation",
                       "requested_resource_hint": "",
                       "matches": [],
                     }

                    for discovery_root in discovery_roots:
                       candidate_discovery = discover_live_azure_module_candidates(
                         effective_prompt,
                         github_owner=GITHUB_OWNER,
                         github_vena_dir=discovery_root,
                         github_base_branch_for_cloud=github_base_branch_for_cloud,
                         github_list_tf_files_recursive=github_list_tf_files_recursive,
                         github_get_file_content=github_get_file_content,
                         github_get_repo_metadata=github_get_repo_metadata,
                       )

                       if candidate_discovery.get("status") != "not_found":
                          discovery = candidate_discovery
                          discovery["searched_root"] = discovery_root
                          break

                       discovery = candidate_discovery
                       discovery["searched_root"] = discovery_root

                    reply = build_azure_module_discovery_reply(discovery)

                    store_pending_azure_module_discovery(
                      thread_id=conversation_id,
                      ticket_number=ticket_number,
                      original_prompt=effective_prompt,
                      discovery=discovery,
                      ticket_link=ticket_link,
                      ticket_title=ticket_title,
                    )

                    return {
                     "ok": False,
                     "mode": "clarification",
                     "reply": reply,
                     "thread_id": conversation_id,
                     "conversation_label": conversation_label,
                     "jira_ticket": ticket_number,
                     "ticket_number": ticket_number,
                     "ticket_link": ticket_link,
                     "ticket_title": ticket_title,
                     "router": {
                       "request_type": "infra",
                       "cloud": "azure",
                       "workflow": "azure_module_discovery",
                       "reason": discovery.get("decision_state") or discovery.get("status"),
                     },
                     "decision_state": discovery.get("decision_state"),
                     "azure_module_discovery": discovery,
                    }, 400

            if target_cloud == "aws":
                if pending_aws_discovery and pending_aws_discovery_state == "aws_module_selection":
                    discovery = pending_aws_discovery.get("discovery") or {}
                    matches = discovery.get("matches") or []
                    if pending_aws_module_negative_reply:
                        clear_pending_aws_module_discovery(conversation_id, ticket_number)
                        return {
                            "ok": True,
                            "mode": "chat",
                            "reply": "Okay, I did not use an existing AWS module or create a PR preview.",
                            "thread_id": conversation_id,
                            "conversation_label": conversation_label,
                            "jira_ticket": ticket_number,
                            "ticket_number": ticket_number,
                            "ticket_link": ticket_link,
                            "ticket_title": ticket_title,
                            "thread_prs": build_thread_prs_payload(conversation_id),
                        }, 200

                    create_own_module = _aws_module_selection_requests_new_module(prompt, matches)
                    if create_own_module:
                        effective_prompt = pending_aws_discovery.get("original_prompt") or effective_prompt
                        selected_env_path = pending_aws_discovery.get("environment_path") or "terraform/dev_aws/minidev"
                        proposed_module_path = _aws_unique_custom_module_path(effective_prompt, discovery)
                        # Consume every competing picker before generation. This is
                        # a terminal selection transition, not another discovery turn.
                        clear_pending_aws_module_discovery(conversation_id, ticket_number)
                        clear_pending_infra_modification_selection(conversation_id, ticket_number)
                        agent_result = _teams_generate_aws_new_module_with_context(
                            conversation_id=conversation_id,
                            original_prompt=effective_prompt,
                            proposed_module_path=proposed_module_path,
                            environment_path=selected_env_path,
                            discovery={**discovery, "status": "not_found", "decision_state": "aws_module_creation"},
                        )
                        pending_key = store_pending_infra_change(
                            conversation_id,
                            ticket_number,
                            effective_prompt,
                            agent_result,
                            ticket_link=ticket_link,
                            ticket_title=ticket_title,
                        )
                        return {
                            "ok": True,
                            "mode": "infra_preview",
                            "reply": "A new AWS module and target-environment consumer were generated from live tf-devops evidence.",
                            "thread_id": conversation_id,
                            "conversation_label": conversation_label,
                            "jira_ticket": ticket_number,
                            "ticket_number": ticket_number,
                            "ticket_link": ticket_link,
                            "ticket_title": ticket_title,
                            "pending_change_id": pending_key,
                            "cloud": "aws",
                            "workflow": "aws_module_creation",
                            "repo_target": "tf-devops",
                            "title": agent_result.get("title") or "[AWS] Create custom AWS module and consumer",
                            "summary": agent_result.get("summary") or "Created a new reusable AWS module and consumer.",
                            "analysis": agent_result.get("analysis") or "",
                            "source_paths_used": agent_result.get("source_paths_used") or [],
                            "user_fillable": agent_result.get("user_fillable") or [],
                            "questions": [],
                            "validation_commands": agent_result.get("validation_commands") or [
                                "terraform fmt -check -recursive",
                                "terraform validate",
                            ],
                            "files": [item.get("filename") for item in agent_result.get("files") or [] if item.get("filename")],
                            "proposed_module_path": proposed_module_path,
                            "environment_path": selected_env_path,
                        }, 200

                    selected_match = pending_aws_selected_match_from_reply
                    if not selected_match and simple_affirmative_reply and matches:
                        selected_match = dict(matches[0])
                    if not selected_match:
                        return {
                            "ok": False,
                            "mode": "clarification",
                            "reply": build_aws_existing_module_selection_reply(
                                discovery,
                                pending_aws_discovery.get("environment_path") or "terraform/dev_aws/minidev",
                            ),
                            "thread_id": conversation_id,
                            "conversation_label": conversation_label,
                            "jira_ticket": ticket_number,
                            "ticket_number": ticket_number,
                            "ticket_link": ticket_link,
                            "ticket_title": ticket_title,
                            "decision_state": "aws_module_selection",
                            "aws_module_discovery": discovery,
                        }, 400

                    effective_prompt = pending_aws_discovery.get("original_prompt") or effective_prompt
                    selected_env_path = pending_aws_discovery.get("environment_path") or "terraform/dev_aws/minidev"
                    verified_selected, selected_generation_context = _aws_selected_module_context_with_contents(
                        selected_match,
                        discovery,
                        selected_env_path,
                    )
                    retrieved_module_context = [verified_selected]
                    retrieved_value_context = list(pending_aws_discovery.get("retrieved_value_context") or retrieved_value_context or [])
                    retrieved_value_context = _remove_backend_existing_infra_contexts(retrieved_value_context)
                    retrieved_value_context.append(
                        _aws_selected_module_value_context(verified_selected, discovery, selected_env_path)
                    )
                    retrieved_value_context.append(selected_generation_context)
                    # Selection is consumed before any generation call. Clearing
                    # both pending pickers makes re-entry into either candidate
                    # list impossible even if a lower wrapper retries the turn.
                    clear_pending_aws_module_discovery(conversation_id, ticket_number)
                    clear_pending_infra_modification_selection(conversation_id, ticket_number)
                    pending_aws_discovery = None
                    pending_aws_module_affirmative_reply = False
                    pending_aws_module_negative_reply = False
                    pending_aws_discovery_state = ""

                if pending_aws_discovery and pending_aws_module_negative_reply:
                    clear_pending_aws_module_discovery(conversation_id, ticket_number)

                    return {
                        "ok": True,
                        "mode": "chat",
                        "reply": "Okay, I did not create a new AWS module or PR preview.",
                        "thread_id": conversation_id,
                        "conversation_label": conversation_label,
                        "jira_ticket": ticket_number,
                        "ticket_number": ticket_number,
                        "ticket_link": ticket_link,
                        "ticket_title": ticket_title,
                        "thread_prs": build_thread_prs_payload(conversation_id),
                    }, 200

                if pending_aws_discovery and pending_aws_module_affirmative_reply:
                    proposed_module_path = (
                        pending_aws_discovery.get("proposed_module_path")
                        or infer_new_aws_module_path(effective_prompt, pending_aws_discovery_payload)
                    )
                    aws_env_path_for_creation = (
                        pending_aws_discovery.get("environment_path")
                        or "terraform/dev_aws/minidev"
                    )

                    if github_verified_aws_module_exists(proposed_module_path):
                        clear_pending_aws_module_discovery(conversation_id, ticket_number)
                        return {
                            "ok": False,
                            "mode": "clarification",
                            "reply": (
                                f"The AWS module tf-devops/{AWS_MODULES_ROOT}/{proposed_module_path} now exists. "
                                "Please retry the original request so Terrabot can consume the verified module instead of creating it."
                            ),
                            "thread_id": conversation_id,
                            "conversation_label": conversation_label,
                            "jira_ticket": ticket_number,
                            "ticket_number": ticket_number,
                            "ticket_link": ticket_link,
                            "ticket_title": ticket_title,
                        }, 400

                    agent_result = generate_aws_module_creation_with_agent(
                        conversation_id=conversation_id,
                        original_prompt=effective_prompt,
                        proposed_module_path=proposed_module_path,
                        environment_path=aws_env_path_for_creation,
                        discovery=pending_aws_discovery_payload,
                    )

                    if agent_result.get("_module_variable_values_required"):
                        return _start_module_variable_value_selection_response(
                            conversation_id=conversation_id,
                            conversation_label=conversation_label,
                            ticket_number=ticket_number,
                            ticket_link=ticket_link,
                            ticket_title=ticket_title,
                            effective_prompt=effective_prompt,
                            agent_result=agent_result,
                            issues=agent_result.get("_module_variable_issues") or [],
                        )

                    pending_key = store_pending_infra_change(
                        conversation_id,
                        ticket_number,
                        effective_prompt,
                        agent_result,
                        ticket_link=ticket_link,
                        ticket_title=ticket_title,
                    )

                    clear_pending_cloud_clarification(conversation_id, ticket_number)
                    clear_pending_azure_module_discovery(conversation_id, ticket_number)
                    clear_pending_azure_consumer_value_selection(conversation_id, ticket_number)
                    clear_pending_aws_module_discovery(conversation_id, ticket_number)

                    return {
                        "ok": True,
                        "mode": "infra_preview",
                        "reply": "AWS module creation is ready. Do you want to commit this tf-devops PR?",
                        "thread_id": conversation_id,
                        "conversation_label": conversation_label,
                        "jira_ticket": ticket_number,
                        "ticket_number": ticket_number,
                        "ticket_link": ticket_link,
                        "ticket_title": ticket_title,
                        "pending_change_id": pending_key,
                        "cloud": "aws",
                        "workflow": "aws_module_creation",
                        "title": agent_result["title"],
                        "summary": agent_result["summary"],
                        "files": [f["filename"] for f in agent_result["files"]],
                        "repo_target": agent_result["repo_target"],
                        "state_bucket": agent_result["state_bucket"],
                        "thread_prs": build_thread_prs_payload(conversation_id),
                    }, 200

                current_env_path = None
                existing_aws_state = recover_thread_pr_state(conversation_id).get("aws") if conversation_id else None
                if existing_aws_state:
                    current_env_path = existing_aws_state.get("environment_path")

                aws_env_path, aws_env_error = resolve_aws_environment_path(
                    effective_prompt,
                    retrieved_value_context=retrieved_value_context,
                    current_environment_path=current_env_path,
                )
                if aws_env_error:
                    return {
                        "ok": False,
                        "mode": "clarification",
                        "reply": aws_env_error,
                        "thread_id": conversation_id,
                        "conversation_label": conversation_label,
                        "jira_ticket": ticket_number,
                        "ticket_number": ticket_number,
                        "ticket_link": ticket_link,
                        "ticket_title": ticket_title,
                        "router": {
                            "request_type": "infra",
                            "cloud": "aws",
                            "workflow": effective_workflow,
                            "reason": "AWS environment mapping was ambiguous.",
                        },
                    }, 400

                if aws_env_path:
                    retrieved_value_context = list(retrieved_value_context or [])
                    if not any(
                        isinstance(item, dict) and item.get("environment_path") == aws_env_path
                        for item in retrieved_value_context
                    ):
                        retrieved_value_context.append(
                            {
                                "environment_path": aws_env_path,
                                "environment_type": "prod" if "/prod_aws/" in aws_env_path else "nonprod",
                                "region_name": (
                                    aws_env_path.split("/")[-1].replace("_dr", "")
                                    if "/prod_aws/" in aws_env_path and aws_env_path.split("/")[-1] not in {"global", "devops"}
                                    else ""
                                ),
                                "is_dr": aws_env_path.endswith("_dr"),
                                "source": "backend_environment_resolution",
                            }
                        )

                    if effective_workflow == "aws_infra_modification":
                        context_branch = github_base_branch_for_cloud(
                            "aws",
                            repo_target="tf-devops",
                            workflow=effective_workflow,
                        )
                        retrieved_value_context = add_backend_existing_aws_infra_context(
                            prompt=effective_prompt,
                            environment_path=aws_env_path,
                            branch=context_branch,
                            retrieved_value_context=retrieved_value_context,
                        )

                confirmed_aws_selection = _get_confirmed_aws_module_selection(retrieved_value_context)
                if confirmed_aws_selection:
                    aws_module_discovery = {
                        "status": "selected",
                        "decision_state": "aws_module_selected",
                        "selection_consumed": True,
                        "matches": [item for item in retrieved_module_context if isinstance(item, dict) and item.get("cloud") == "aws"],
                        "repo_full_name": f"{GITHUB_OWNER}/{GITHUB_AWS_REPO}",
                        "resolved_ref": _aws_module_catalog_branch(),
                    }
                else:
                    try:
                        retrieved_module_context, retrieved_value_context, aws_module_discovery = add_grounded_aws_module_context(
                            effective_prompt,
                            environment_path=aws_env_path or current_env_path or "",
                            retrieved_module_context=retrieved_module_context,
                            retrieved_value_context=retrieved_value_context,
                        )
                    except Exception as aws_discovery_error:
                        return {
                            "ok": False,
                            "mode": "clarification",
                            "reply": (
                                "The backend could not verify the AWS module catalog in "
                                f"tf-devops/{AWS_MODULES_ROOT}: {aws_discovery_error}"
                            ),
                            "thread_id": conversation_id,
                            "conversation_label": conversation_label,
                            "jira_ticket": ticket_number,
                            "ticket_number": ticket_number,
                            "ticket_link": ticket_link,
                            "ticket_title": ticket_title,
                            "router": {
                                "request_type": "infra",
                                "cloud": "aws",
                                "workflow": effective_workflow,
                                "reason": "AWS module catalog verification failed.",
                            },
                        }, 400

                allow_existing_update_without_new_module = (
                    effective_workflow == "aws_infra_modification"
                    or (bool(existing_aws_state) and aws_prompt_can_update_existing_without_module_match(effective_prompt))
                )

                if (
                    aws_module_discovery.get("status") in {"exact_match", "similar_match"}
                    and not allow_existing_update_without_new_module
                    and not _get_confirmed_aws_module_selection(retrieved_value_context)
                    and (aws_module_discovery.get("matches") or [])
                ):
                    store_pending_aws_module_discovery(
                        thread_id=conversation_id,
                        ticket_number=ticket_number,
                        original_prompt=effective_prompt,
                        discovery={**aws_module_discovery, "decision_state": "aws_module_selection"},
                        environment_path=aws_env_path or current_env_path or "terraform/dev_aws/minidev",
                        proposed_module_path="",
                        ticket_link=ticket_link,
                        ticket_title=ticket_title,
                    )
                    return {
                        "ok": False,
                        "mode": "clarification",
                        "reply": build_aws_existing_module_selection_reply(
                            aws_module_discovery,
                            environment_path=aws_env_path or current_env_path or "terraform/dev_aws/minidev",
                        ),
                        "thread_id": conversation_id,
                        "conversation_label": conversation_label,
                        "jira_ticket": ticket_number,
                        "ticket_number": ticket_number,
                        "ticket_link": ticket_link,
                        "ticket_title": ticket_title,
                        "router": {
                            "request_type": "infra",
                            "cloud": "aws",
                            "workflow": "aws_module_selection",
                            "reason": "Verified tf-devops AWS module option(s) found; user must select before generation.",
                        },
                        "decision_state": "aws_module_selection",
                        "aws_module_discovery": aws_module_discovery,
                        "environment_path": aws_env_path or current_env_path or "terraform/dev_aws/minidev",
                    }, 400

                if (
                    aws_module_discovery.get("status") == "not_found"
                    and not allow_existing_update_without_new_module
                ):
                    proposed_module_path = infer_new_aws_module_path(effective_prompt, aws_module_discovery)
                    resolved_aws_env_path = (
                        aws_env_path or current_env_path or "terraform/dev_aws/minidev"
                    )

                    # Teams-only: verified module absence is an execution decision,
                    # not a user confirmation point. Generate the repository-aligned
                    # module + environment consumer immediately from live tf-devops
                    # evidence. VS Code keeps the existing confirmation workflow.
                    active_teams_flow = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
                    if active_teams_flow.get("active"):
                        agent_result = _teams_generate_aws_new_module_with_context(
                            conversation_id=conversation_id,
                            original_prompt=effective_prompt,
                            proposed_module_path=proposed_module_path,
                            environment_path=resolved_aws_env_path,
                            discovery=aws_module_discovery,
                        )

                        pending_key = store_pending_infra_change(
                            conversation_id,
                            ticket_number,
                            effective_prompt,
                            agent_result,
                            ticket_link=ticket_link,
                            ticket_title=ticket_title,
                        )

                        clear_pending_aws_module_discovery(conversation_id, ticket_number)
                        return {
                            "ok": True,
                            "mode": "infra_preview",
                            "reply": (
                                "The missing AWS module and target-environment consumer "
                                "were generated from live tf-devops evidence."
                            ),
                            "thread_id": conversation_id,
                            "conversation_label": conversation_label,
                            "jira_ticket": ticket_number,
                            "ticket_number": ticket_number,
                            "ticket_link": ticket_link,
                            "ticket_title": ticket_title,
                            "pending_change_id": pending_key,
                            "cloud": "aws",
                            "workflow": "aws_module_creation",
                            "repo_target": "tf-devops",
                            "title": agent_result.get("title") or "[AWS] Create new AWS module and consumer",
                            "summary": agent_result.get("summary") or "Created a reusable AWS module and target-environment consumer.",
                            "analysis": agent_result.get("analysis") or "",
                            "source_paths_used": agent_result.get("source_paths_used") or [],
                            "user_fillable": agent_result.get("user_fillable") or [],
                            "questions": [],
                            "validation_commands": agent_result.get("validation_commands") or [
                                "terraform fmt -check -recursive",
                                "terraform validate",
                            ],
                            "files": [
                                item.get("filename")
                                for item in agent_result.get("files") or []
                                if item.get("filename")
                            ],
                            "state_bucket": agent_result.get("state_bucket")
                            or state_bucket_for_target(
                                "aws", "tf-devops", "aws_module_creation"
                            ),
                            "aws_module_discovery": aws_module_discovery,
                            "proposed_module_path": proposed_module_path,
                            "environment_path": resolved_aws_env_path,
                        }, 200

                    store_pending_aws_module_discovery(
                        thread_id=conversation_id,
                        ticket_number=ticket_number,
                        original_prompt=effective_prompt,
                        discovery=aws_module_discovery,
                        environment_path=resolved_aws_env_path,
                        proposed_module_path=proposed_module_path,
                        ticket_link=ticket_link,
                        ticket_title=ticket_title,
                    )

                    return {
                        "ok": False,
                        "mode": "clarification",
                        "reply": build_aws_module_creation_confirmation_reply(
                            aws_module_discovery,
                            environment_path=resolved_aws_env_path,
                            proposed_module_path=proposed_module_path,
                        ),
                        "thread_id": conversation_id,
                        "conversation_label": conversation_label,
                        "jira_ticket": ticket_number,
                        "ticket_number": ticket_number,
                        "ticket_link": ticket_link,
                        "ticket_title": ticket_title,
                        "router": {
                            "request_type": "infra",
                            "cloud": "aws",
                            "workflow": "aws_module_creation_confirmation",
                            "reason": "No verified tf-devops AWS module matched the request; asking whether to create a new module.",
                        },
                        "decision_state": "aws_module_creation_confirmation",
                        "aws_module_discovery": aws_module_discovery,
                        "proposed_module_path": proposed_module_path,
                        "environment_path": resolved_aws_env_path,
                    }, 400

            if (
                target_cloud == "azure"
                and effective_workflow == "azure_consumer_generation"
                and retrieved_module_context
            ):
                retrieved_module_context, retrieved_value_context, routing_context = augment_azure_consumer_generation_context(
                    prompt=effective_prompt,
                    thread_id=conversation_id,
                    retrieved_module_context=retrieved_module_context,
                    retrieved_value_context=retrieved_value_context,
                )

                if routing_context and routing_context.get("source") == "backend_new_azure_consumer_file_confirmation_required":
                    store_pending_azure_new_consumer_file_confirmation(
                        thread_id=conversation_id,
                        ticket_number=ticket_number,
                        original_prompt=effective_prompt,
                        retrieved_module_context=retrieved_module_context,
                        retrieved_value_context=[
                            item for item in list(retrieved_value_context or [])
                            if not (isinstance(item, dict) and item.get("source") == "backend_new_azure_consumer_file_confirmation_required")
                        ],
                        routing_context=routing_context,
                        ticket_link=ticket_link,
                        ticket_title=ticket_title,
                    )
                    return {
                        "ok": False,
                        "mode": "clarification",
                        "reply": build_azure_new_consumer_file_confirmation_reply(routing_context),
                        "thread_id": conversation_id,
                        "conversation_label": conversation_label,
                        "jira_ticket": ticket_number,
                        "ticket_number": ticket_number,
                        "ticket_link": ticket_link,
                        "ticket_title": ticket_title,
                        "router": {
                            "request_type": "infra",
                            "cloud": "azure",
                            "workflow": "azure_new_consumer_file_confirmation",
                            "reason": "No tf-azure-hub file uses the selected module source; user must confirm new consumer file creation.",
                        },
                        "decision_state": "azure_new_consumer_file_confirmation",
                        "target_consumer_file": routing_context.get("target_consumer_filename"),
                        "target_tfvars_file": routing_context.get("target_tfvars_filename"),
                        "module_source_url": routing_context.get("module_source_url"),
                    }, 400

                if routing_context and not _azure_consumer_value_selection_confirmed(retrieved_value_context):
                    store_pending_azure_consumer_value_selection(
                        thread_id=conversation_id,
                        ticket_number=ticket_number,
                        original_prompt=effective_prompt,
                        retrieved_module_context=retrieved_module_context,
                        retrieved_value_context=retrieved_value_context,
                        ticket_link=ticket_link,
                        ticket_title=ticket_title,
                    )
                    return {
                        "ok": False,
                        "mode": "clarification",
                        "reply": build_azure_consumer_variable_values_reply(
                            routing_context,
                            _get_primary_azure_module_context(retrieved_module_context),
                        ),
                        "thread_id": conversation_id,
                        "conversation_label": conversation_label,
                        "jira_ticket": ticket_number,
                        "ticket_number": ticket_number,
                        "ticket_link": ticket_link,
                        "ticket_title": ticket_title,
                        "router": {
                            "request_type": "infra",
                            "cloud": "azure",
                            "workflow": "azure_consumer_value_selection",
                            "reason": "Azure consumer module file and tfvars file were source-matched; values must be confirmed before generation.",
                        },
                        "decision_state": "azure_consumer_value_selection",
                        "target_consumer_file": routing_context.get("target_consumer_filename"),
                        "target_tfvars_file": routing_context.get("target_tfvars_filename"),
                        "value_selection_form": build_azure_consumer_value_selection_form(
                            routing_context,
                            _get_primary_azure_module_context(retrieved_module_context),
                        ),
                    }, 400

            if effective_workflow in INFRA_MODIFICATION_WORKFLOWS:
                existing_infra_context = _get_backend_existing_infra_context(retrieved_value_context)

                # FINAL TEAMS MODIFICATION REFRESH:
                # Broad backend_existing_infra_code_match context may have been populated
                # earlier in the same request by repository-wide/environment discovery.
                # Reusing that candidate set here bypasses the final target-main.tf +
                # Foundry Boolean-control resolver and causes the legacy file picker
                # (main.tf/backend.tf/outputs.tf/...) to be rendered.
                #
                # For a fresh Teams AWS modification turn, always rebuild the context
                # unless this is already a user-selected pending target. The final
                # resolver semantically classifies the complete target environment
                # main.tf and validates any returned Boolean against literal live HCL.
                # This is intentionally independent of hardcoded enable/disable words.
                _teams_modification_refresh_required = bool(
                    (_ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}).get("active")
                    and str(target_cloud or "").strip().lower() == "aws"
                    and not _backend_existing_infra_context_is_selected(existing_infra_context)
                )

                if not existing_infra_context or _teams_modification_refresh_required:
                    existing_infra_context = build_backend_existing_infra_modification_context(
                        prompt=effective_prompt,
                        thread_id=conversation_id,
                        cloud=target_cloud,
                        workflow=effective_workflow,
                        retrieved_value_context=retrieved_value_context,
                    )
                if not _backend_existing_infra_context_is_selected(existing_infra_context):
                    matched_files = existing_infra_context.get("matched_files") or []
                    auto_selected_flag_context = {}
                    if (_ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}).get("active"):
                        auto_selected_flag_context = _teams_auto_select_feature_flag_context(
                            existing_infra_context,
                            effective_prompt,
                        )
                    if auto_selected_flag_context:
                        existing_infra_context = auto_selected_flag_context
                    elif matched_files and _teams_is_existing_invocation_creation(effective_prompt):
                        # Ordinary create/add requests are repository-inference
                        # problems, not user-choice problems. Deterministically
                        # select the highest-ranked live GitHub candidate and
                        # continue generation. This guarantees object-backed
                        # Azure resources can proceed directly to the three-file
                        # materialization path without showing a target picker.
                        auto_pending = {
                            "original_prompt": effective_prompt,
                            "cloud": target_cloud,
                            "workflow": effective_workflow,
                            "existing_infra_context": existing_infra_context,
                        }
                        existing_infra_context = build_selected_infra_modification_context(
                            auto_pending, 0
                        )
                    elif not matched_files:
                        return {
                            "ok": False,
                            "mode": "clarification",
                            "reply": (
                                "I could not resolve a unique repository resource from the current request. "
                                "Please give me a more specific resource or module description; you do not need to provide a file path."
                            ),
                            "thread_id": conversation_id,
                            "conversation_label": conversation_label,
                            "jira_ticket": ticket_number,
                            "ticket_number": ticket_number,
                            "ticket_link": ticket_link,
                            "ticket_title": ticket_title,
                            "router": {
                                "request_type": "infra",
                                "cloud": target_cloud,
                                "workflow": effective_workflow,
                                "reason": "Existing infrastructure code was not found by backend GitHub search.",
                            },
                        }, 400
                    if (
                        not auto_selected_flag_context
                        and not _backend_existing_infra_context_is_selected(existing_infra_context)
                    ):
                        store_pending_infra_modification_selection(
                            thread_id=conversation_id,
                            ticket_number=ticket_number,
                            original_prompt=effective_prompt,
                            cloud=target_cloud,
                            workflow=effective_workflow,
                            retrieved_module_context=retrieved_module_context,
                            retrieved_value_context=_remove_backend_existing_infra_contexts(retrieved_value_context),
                            existing_infra_context=existing_infra_context,
                            ticket_link=ticket_link,
                            ticket_title=ticket_title,
                        )
                        # Always re-sort by fresh relevance to the CURRENT prompt
                        # before building the picker. Upstream builders may
                        # return matched_files in directory/alphabetical order
                        # (e.g. after live-environment-folder expansion); without
                        # this the picker showed the first N files alphabetically
                        # (acm.tf, backend.tf, ...) instead of the file that
                        # actually matches the requested resource (e.g. waf.tf
                        # for "disable mcp waf rules"), even when that file was
                        # present further down the unsorted list.
                        _ranked_matched_files = sorted(
                            matched_files,
                            key=lambda item: (
                                -_teams_semantic_candidate_score(effective_prompt, item)[0],
                                str(item.get("path") or ""),
                            ),
                        )
                        return {
                            "ok": False,
                            "mode": "clarification",
                            "reply": build_infra_modification_selection_reply(existing_infra_context),
                            "thread_id": conversation_id,
                            "conversation_label": conversation_label,
                            "jira_ticket": ticket_number,
                            "ticket_number": ticket_number,
                            "ticket_link": ticket_link,
                            "ticket_title": ticket_title,
                            "router": {
                                "request_type": "infra",
                                "cloud": target_cloud,
                                "workflow": effective_workflow,
                                "reason": "Backend found existing Terraform candidates; user must select exact target before generation.",
                            },
                            "decision_state": "infra_modification_target_selection",
                            "candidates": [
                                {
                                    "index": index + 1,
                                    "path": item.get("path"),
                                    "reason": item.get("reason"),
                                    "flag": ((item.get("feature_flag_match") or {}).get("flag") or ""),
                                    "flag_context": ((item.get("feature_flag_match") or {}).get("context") or ""),
                                    "current_value": ((item.get("feature_flag_match") or {}).get("current_value") or ""),
                                    "requested_value": ((item.get("feature_flag_match") or {}).get("new_value") or ""),
                                    "matched_blocks": [
                                        block.get("header")
                                        for block in (item.get("matched_blocks") or [])
                                        if isinstance(block, dict) and block.get("header")
                                    ],
                                    # A one-line, evidence-based description of what
                                    # the file actually declares, so the Teams picker
                                    # tells the user what is inside every environment
                                    # file instead of only its path.
                                    "content_summary": _teams_describe_tf_file_contents(item),
                                    "relevance_score": _teams_semantic_candidate_score(effective_prompt, item)[0],
                                }
                                for index, item in enumerate(_ranked_matched_files)
                            ],
                        }, 400
                retrieved_value_context = _remove_backend_existing_infra_contexts(retrieved_value_context)
                retrieved_value_context.append(existing_infra_context)

            agent_input = build_agent_input_for_infra(
                effective_prompt,
                conversation_id,
                selected_cloud=target_cloud,
                workflow=effective_workflow,
                retrieved_module_context=retrieved_module_context,
                retrieved_value_context=retrieved_value_context,
            )

            # Terraform generation is Foundry-owned. The backend has already
            # collected live GitHub evidence; pass that evidence to Foundry and
            # never synthesize, toggle, merge, or materialize Terraform here.
            conversation_id, agent_reply = call_agent(conversation_id, agent_input)

            if not agent_reply.strip():
                raise RuntimeError("No response returned from agent.")
            agent_reply = _teams_apply_agent_identity(
                agent_reply, target_cloud, effective_workflow
            )

            conversation_label = build_enhanced_conversation_label(
                ticket_number=ticket_number,
                ticket_title=ticket_title,
                conversation_id=conversation_id,
            )

            # Foundry can occasionally answer an explicit Teams infrastructure
            # creation as read-only repository Q&A (for example prefixing the
            # response with "INTENT: REPOSITORY QUESTION/ANSWER") even though
            # the backend already resolved the request as infra and supplied live
            # GitHub evidence. Never surface that prose to Teams. Retry the same
            # active generation conversation with a deterministic repository-
            # grounded corrective instruction so object-backed Azure creations
            # materialize the complete write-set instead of asking repo-answerable
            # questions.
            _invocation_active = any(
                isinstance(item, dict)
                and item.get("source") == "backend_existing_infra_code_match"
                and (
                    item.get("invocation_generation")
                    or item.get("operation") == "existing_invocation_creation"
                )
                for item in (retrieved_value_context or [])
            )
            _agent_reply_lower = str(agent_reply or "").lower()
            _agent_misclassified_as_repo_qa = bool(
                _invocation_active
                and (
                    "intent: repository question/answer" in _agent_reply_lower
                    or "repository question/answer (no direct terraform changes yet)" in _agent_reply_lower
                    or "no direct terraform changes yet" in _agent_reply_lower
                )
            )
            if _agent_misclassified_as_repo_qa:
                corrective = None
                if target_cloud == "azure":
                    corrective = _teams_azure_object_backed_no_question_corrective(
                        effective_prompt, retrieved_value_context
                    )
                if not corrective:
                    corrective = _teams_flagless_creation_corrective(
                        effective_prompt, retrieved_value_context
                    )
                if corrective:
                    conversation_id, agent_reply = call_agent(conversation_id, corrective)
                    if not str(agent_reply or "").strip():
                        raise RuntimeError(
                            "Foundry returned an empty response while correcting an infrastructure request misclassified as repository Q&A."
                        )
                    agent_reply = _teams_apply_agent_identity(
                        agent_reply, target_cloud, effective_workflow
                    )

            agent_clarification = _teams_intercept_agent_questions(agent_reply)
            _invocation_active = any(
                isinstance(item, dict)
                and item.get("source") == "backend_existing_infra_code_match"
                and (
                    item.get("invocation_generation")
                    or item.get("operation") == "existing_invocation_creation"
                )
                for item in (retrieved_value_context or [])
            )
            if agent_clarification is not None and _teams_is_path_request_question(agent_clarification):
                # During an invocation-creation flow, ANY agent clarification
                # is resolved backend-first — the tri-state is deterministic:
                # flag TRUE → RULE-2 card; flag FALSE/absent → the backend
                # materializes the flag change itself (never a permission
                # question); only path-question phrasing falls through to the
                # corrective-retry machinery. Non-invocation clarifications
                # pass through unchanged unless they ask for a path.
                rule2_reply = _teams_backend_rule2_reply(effective_prompt, retrieved_value_context)
                deterministic_envelope = None
                if not rule2_reply:
                    deterministic_envelope = _teams_backend_flag_enable_envelope(
                        effective_prompt,
                        retrieved_value_context,
                        cloud=target_cloud,
                        workflow=effective_workflow,
                    )
                if rule2_reply:
                    agent_clarification = rule2_reply
                elif deterministic_envelope:
                    # The backend built the exact flag change from live GitHub.
                    # Feed it through the normal parse → enforce → materialize
                    # pipeline; the user sees a generation preview, never the
                    # agent's question.
                    agent_reply = _teams_apply_agent_identity(
                        deterministic_envelope, target_cloud, effective_workflow
                    )
                    agent_clarification = None
                else:
                    # No flag anywhere in evidence. This does NOT mean the
                    # environment "uses a different mechanism" the user must
                    # name — plenty of resources (e.g. a plain storage account
                    # module block) are never flag-gated at all. Retry once
                    # with an explicit flagless-creation instruction before
                    # ever asking the user anything.
                    flagless_corrective = _teams_flagless_creation_corrective(
                        effective_prompt, retrieved_value_context
                    )
                    if flagless_corrective:
                        conversation_id, agent_reply = call_agent(conversation_id, flagless_corrective)
                        agent_reply = _teams_apply_agent_identity(
                            agent_reply, target_cloud, effective_workflow
                        )
                        agent_clarification = _teams_intercept_agent_questions(agent_reply)
                        if (
                            agent_clarification is not None
                            and target_cloud == "azure"
                            and _invocation_active
                        ):
                            object_corrective = _teams_azure_object_backed_no_question_corrective(
                                effective_prompt, retrieved_value_context
                            )
                            if object_corrective:
                                conversation_id, agent_reply = call_agent(conversation_id, object_corrective)
                                agent_reply = _teams_apply_agent_identity(
                                    agent_reply, target_cloud, effective_workflow
                                )
                                agent_clarification = _teams_intercept_agent_questions(agent_reply)
                        if agent_clarification is not None and _teams_is_path_request_question(agent_clarification):
                            corrective = _teams_path_question_corrective(retrieved_value_context)
                            if corrective:
                                conversation_id, agent_reply = call_agent(conversation_id, corrective)
                                agent_reply = _teams_apply_agent_identity(
                                    agent_reply, target_cloud, effective_workflow
                                )
                                agent_clarification = _teams_intercept_agent_questions(agent_reply)
                    elif _teams_is_path_request_question(agent_clarification):
                        corrective = _teams_path_question_corrective(retrieved_value_context)
                        if corrective:
                            conversation_id, agent_reply = call_agent(conversation_id, corrective)
                            agent_reply = _teams_apply_agent_identity(
                                agent_reply, target_cloud, effective_workflow
                            )
                            agent_clarification = _teams_intercept_agent_questions(agent_reply)
                            if agent_clarification is not None and _teams_is_path_request_question(agent_clarification):
                                agent_clarification = _teams_supplied_files_diagnostic(retrieved_value_context)
                        else:
                            agent_clarification = _teams_supplied_files_diagnostic(retrieved_value_context)
                    else:
                        agent_clarification = _teams_supplied_files_diagnostic(retrieved_value_context)
            if agent_clarification is not None:
                return {
                    "ok": False,
                    "mode": "clarification",
                    "reply": agent_clarification,
                    "thread_id": conversation_id,
                    "conversation_label": conversation_label,
                    "jira_ticket": ticket_number,
                    "ticket_number": ticket_number,
                    "ticket_link": ticket_link,
                    "ticket_title": ticket_title,
                    "router": {
                        "request_type": "infra",
                        "cloud": target_cloud,
                        "workflow": effective_workflow,
                        "reason": "Agent returned a blocking question (e.g. already-exists check) instead of files.",
                    },
                    "decision_state": "agent_clarification",
                }, 400

            try:
                try:
                    agent_result = try_parse_agent_output(agent_reply)
                except Exception as first_parse_error:
                    agent_result, agent_reply = repair_and_parse_agent_output(
                        conversation_id=conversation_id,
                        original_agent_input=agent_input,
                        bad_agent_reply=agent_reply,
                        parse_error=first_parse_error,
                    )

                try:
                    agent_result = finalize_agent_result_after_parse(
                        agent_result,
                        retrieved_module_context,
                        retrieved_value_context,
                    )
                except ModuleVariableValuesRequired as variable_error:
                    agent_result["files"] = variable_error.files
                    agent_result["_module_variable_values_required"] = True
                    agent_result["_module_variable_issues"] = variable_error.issues
                    return _start_module_variable_value_selection_response(
                        conversation_id=conversation_id,
                        conversation_label=conversation_label,
                        ticket_number=ticket_number,
                        ticket_link=ticket_link,
                        ticket_title=ticket_title,
                        effective_prompt=effective_prompt,
                        agent_result=agent_result,
                        issues=variable_error.issues,
                    )

                if effective_workflow in INFRA_MODIFICATION_WORKFLOWS:
                    agent_result["workflow"] = effective_workflow
                    agent_result["repo_target"] = normalize_repo_target(
                        agent_result["cloud"],
                        repo_target=agent_result.get("repo_target"),
                        workflow=effective_workflow,
                    )
                    agent_result["state_bucket"] = state_bucket_for_target(
                        agent_result["cloud"],
                        agent_result.get("repo_target"),
                        effective_workflow,
                    )
                    # Repository-preservation failures are backend validation failures,
                    # including UnsafeGeneratedChangeError. Keep them private and give
                    # Foundry bounded repair attempts before any pending change/branch is
                    # exposed to Teams. The backend validates only; it never repairs HCL.
                    validation_error = None
                    repair_feedback = ""
                    # One generation-validation repair round only: pass 1 validates
                    # the original candidate and may issue one consolidated repair;
                    # pass 2 validates that repaired candidate without another model call.
                    generation_validation_passes = min(
                        max(1, int(MAX_TEAMS_SELF_CORRECTION_ATTEMPTS or 1)), 2
                    )
                    for repair_attempt in range(1, generation_validation_passes + 1):
                        try:
                            agent_result = enforce_modification_uses_backend_matched_files(
                                agent_result, retrieved_value_context
                            )
                            validation_error = None
                            break
                        except ValueError as enforce_error:
                            validation_error = enforce_error
                            _teams_diag_log(
                                "generation_validation_failed",
                                level="warning",
                                thread=conversation_id,
                                attempt=f"{repair_attempt}/{generation_validation_passes}",
                                error=str(enforce_error)[:300],
                            )
                            if repair_attempt >= generation_validation_passes:
                                break

                            repair_payload = {
                                "task": (
                                    "SELF-CORRECTION LOOP: the backend rejected your generated "
                                    "Terraform before it was shown or written. Repair the exact "
                                    "validation failure and return corrected complete files now. "
                                    "Do not ask the user anything."
                                ),
                                "channel": "teams",
                                "original_user_request": effective_prompt,
                                "backend_validation_error": str(enforce_error),
                                "previous_generated_files": [
                                    {
                                        "filename": (item or {}).get("filename"),
                                        "content": (item or {}).get("content"),
                                    }
                                    for item in (agent_result.get("files") or [])
                                    if isinstance(item, dict)
                                ],
                                "expected_cloud": target_cloud,
                                "expected_workflow": effective_workflow,
                                "expected_repo_target": agent_result.get("repo_target"),
                                "retrieved_module_context": retrieved_module_context,
                                "retrieved_value_context": retrieved_value_context,
                                "correction_instructions": [
                                    "Fix the exact backend_validation_error; do not change unrelated repository content.",
                                    "For an existing file, return the COMPLETE final live file, preserving every unrelated line, comment, block, blank line, and ordering exactly.",
                                    "Do not abbreviate, truncate, summarize, or use placeholders for unchanged repository content.",
                                    "Make only the modification requested by original_user_request.",
                                    "Return strict infrastructure JSON with corrected files[] and no blocking questions.",
                                ],
                            }
                            selected_repair_context = _get_backend_existing_infra_context(
                                retrieved_value_context
                            )
                            if isinstance(selected_repair_context, dict):
                                # Give the repair turn the COMPLETE live content for every
                                # file it is trying to modify, not only selected_path. The
                                # repeated tfvars truncation failure happened because
                                # hub.tfvars was a companion/environment file while the
                                # repair payload prominently grounded only the selected
                                # definition file. Foundry then kept regenerating a short
                                # fragment instead of preserving the 393-line live file.
                                live_files_by_path = {}
                                for evidence_item in list(selected_repair_context.get("matched_files") or []) + list(selected_repair_context.get("environment_files") or []):
                                    if not isinstance(evidence_item, dict):
                                        continue
                                    evidence_path = str(
                                        evidence_item.get("path") or evidence_item.get("filename") or ""
                                    ).strip().strip("/")
                                    evidence_content = str(evidence_item.get("content") or "")
                                    if evidence_path and evidence_content:
                                        live_files_by_path[evidence_path] = evidence_content

                                # Resolve all files returned by the rejected generation. If a
                                # companion file was not retained in the bounded evidence,
                                # read it directly from the same live GitHub ref before asking
                                # Foundry to repair it. This remains evidence-only; the backend
                                # does not synthesize or merge Terraform.
                                rejected_paths = []
                                for generated_item in agent_result.get("files") or []:
                                    if not isinstance(generated_item, dict):
                                        continue
                                    generated_path = str(
                                        generated_item.get("filename") or generated_item.get("path") or ""
                                    ).strip().strip("/")
                                    if generated_path and generated_path not in rejected_paths:
                                        rejected_paths.append(generated_path)

                                repair_live_files = []
                                for repair_path in rejected_paths:
                                    live_content = live_files_by_path.get(repair_path) or ""
                                    if not live_content:
                                        try:
                                            repair_cloud = normalize_cloud(target_cloud)
                                            repair_repo_target = normalize_repo_target(
                                                repair_cloud,
                                                repo_target=agent_result.get("repo_target"),
                                                workflow=effective_workflow,
                                            )
                                            repair_ref = str(
                                                selected_repair_context.get("context_ref")
                                                or _teams_remote_context_branch(
                                                    repair_cloud,
                                                    repair_repo_target,
                                                    effective_workflow,
                                                )
                                            ).strip()
                                            live_content = github_get_file_content(
                                                repair_cloud,
                                                repair_path,
                                                repair_ref,
                                                repo_target=repair_repo_target,
                                                workflow=effective_workflow,
                                            ) or ""
                                        except Exception as live_read_error:
                                            _teams_diag_log(
                                                "generation_validation_repair_live_file_read_failed",
                                                level="warning",
                                                thread=conversation_id,
                                                path=repair_path,
                                                error=str(live_read_error)[:200],
                                            )
                                    if live_content:
                                        repair_live_files.append({
                                            "path": repair_path,
                                            "content": live_content,
                                            "must_preserve_verbatim_except_requested_change": True,
                                            "live_nonblank_line_count": len([
                                                line for line in live_content.splitlines() if line.strip()
                                            ]),
                                        })

                                if repair_live_files:
                                    repair_payload["teams_exact_live_files"] = repair_live_files
                                    repair_payload["agent_self_validation_required"] = {
                                        "preservation": (
                                            "Before returning JSON, compare each repaired existing file against teams_exact_live_files. "
                                            "Every unrelated live line/block/comment must still be present; only the requested change may differ."
                                        ),
                                        "completeness": (
                                            "Return the COMPLETE final file, never a snippet. A repaired file must not be materially shorter "
                                            "than its live_nonblank_line_count unless the user explicitly requested deletion."
                                        ),
                                        "hcl": (
                                            "Verify brackets/braces are balanced and the output contains no placeholders or omitted-content markers."
                                        ),
                                    }
                                    repair_payload["correction_instructions"].extend([
                                        "teams_exact_live_files is authoritative repository truth for this repair turn.",
                                        "For every existing file you return, start from its exact teams_exact_live_files content and make only the requested edit; do not reconstruct a shortened version from memory.",
                                        "Run the agent_self_validation_required checks yourself before emitting the JSON response. If preservation fails, correct it internally and only then return files[].",
                                    ])

                                selected_path = str(
                                    selected_repair_context.get("selected_path") or ""
                                ).strip()
                                if selected_path and selected_path in live_files_by_path:
                                    repair_payload["teams_exact_target_file"] = {
                                        "path": selected_path,
                                        "content": live_files_by_path[selected_path],
                                        "must_preserve_verbatim": True,
                                    }

                            # Rebuild the repair request as one self-contained package.
                            # This guarantees the agent receives the exact validator error,
                            # the exact rejected generated code, and the exact live GitHub
                            # counterpart for every returned existing file on every attempt.
                            repair_payload = _teams_build_backend_repair_payload(
                                current_result=agent_result,
                                original_user_request=effective_prompt,
                                backend_error=enforce_error,
                                flow_context=_ACTIVE_TEAMS_FLOW_CONTEXT.get() or {},
                                retrieved_value_context=retrieved_value_context,
                                retrieved_module_context=retrieved_module_context,
                                prior_repair_feedback=repair_feedback,
                            )

                            _teams_diag_log(
                                "sending_generation_validation_repair_to_agent",
                                thread=conversation_id,
                                attempt=f"{repair_attempt}/{generation_validation_passes}",
                            )

                            # A malformed/question-style Foundry repair response is itself
                            # an INTERNAL repair failure. Never let its JSON/parser error
                            # escape to the outer Teams response handler, because that would
                            # surface messages such as "Expecting ',' delimiter" to the user
                            # and prematurely stop the 5-attempt self-correction loop.
                            #
                            # Keep the last backend-invalid agent_result unchanged until a
                            # replacement repair response has been fully parsed/finalized.
                            # The next loop iteration will therefore re-run the same backend
                            # validation and send the rejection back to Foundry again.
                            try:
                                repaired_conversation_id, repaired_reply = _teams_call_agent_for_backend_repair(
                                    repair_payload
                                )
                                repaired_reply = _teams_apply_agent_identity(
                                    repaired_reply,
                                    target_cloud,
                                    effective_workflow,
                                )

                                # Materialize valid Foundry-selected repair_edits BEFORE looking
                                # for question fields. Some agent responses include an explanatory
                                # questions[] field even when they also returned a complete surgical
                                # repair. Rejecting the response before materialization threw away the
                                # executable repair and caused the same backend failure to loop.
                                repaired_reply = _teams_materialize_repair_edits_response(
                                    repaired_reply, repair_payload
                                )

                                repair_clarification = _teams_intercept_agent_questions(
                                    repaired_reply
                                )
                                if repair_clarification is not None:
                                    raise ValueError(
                                        "Foundry returned a blocking question without an executable "
                                        "internal backend-validation repair. Internal repair responses "
                                        "must return corrected files[] or valid repair_edits[]."
                                    )
                                repaired_result = try_parse_agent_output(repaired_reply)
                                repaired_result = finalize_agent_result_after_parse(
                                    repaired_result,
                                    retrieved_module_context,
                                    retrieved_value_context,
                                )
                                repaired_result["workflow"] = effective_workflow
                                repaired_result["repo_target"] = normalize_repo_target(
                                    repaired_result["cloud"],
                                    repo_target=repaired_result.get("repo_target"),
                                    workflow=effective_workflow,
                                )
                                repaired_result["state_bucket"] = state_bucket_for_target(
                                    repaired_result["cloud"],
                                    repaired_result.get("repo_target"),
                                    effective_workflow,
                                )
                                if _teams_repair_candidate_is_identical(agent_result, repaired_result):
                                    raise ValueError(
                                        "Foundry repair returned byte-identical file content to the backend-rejected candidate. "
                                        "The repair must actually change the failed output using existing_live_content."
                                    )
                                _teams_validate_repair_candidate_against_payload(
                                    repaired_result, repair_payload
                                )
                            except Exception as repair_response_error:
                                _teams_diag_log(
                                    "generation_validation_repair_response_invalid",
                                    level="warning",
                                    thread=conversation_id,
                                    attempt=f"{repair_attempt}/{generation_validation_passes}",
                                    error=str(repair_response_error)[:300],
                                )
                                repair_feedback = str(repair_response_error)
                                LOGGER.warning(
                                    "Foundry generation-validation repair response failed on "
                                    "attempt %s/%s (thread=%s): %s. Keeping the error private "
                                    "and continuing the internal repair loop.",
                                    repair_attempt,
                                    generation_validation_passes,
                                    conversation_id,
                                    repair_response_error,
                                )
                                continue

                            conversation_id = repaired_conversation_id
                            agent_reply = repaired_reply
                            agent_result = repaired_result
                            _teams_diag_log(
                                "generation_validation_repair_response_accepted",
                                thread=conversation_id,
                                attempt=f"{repair_attempt}/{generation_validation_passes}",
                                files_returned=len(agent_result.get("files") or []),
                            )

                    if validation_error is not None:
                        _teams_diag_log(
                            "generation_validation_repair_exhausted",
                            level="error",
                            thread=conversation_id,
                            error=str(validation_error)[:300],
                        )
                        raise ValueError(
                            "Terrabot could not produce a backend-valid Terraform change "
                            "after internal repair attempts. No repository changes were written."
                        )

                agent_result = _teams_ensure_flag_enable_in_env_values(
                    agent_result,
                    effective_prompt,
                    retrieved_value_context,
                    cloud=target_cloud,
                    workflow=effective_workflow,
                )

                target_cloud = agent_result["cloud"]
                if conversation_id:
                    set_last_selected_cloud(conversation_id, target_cloud)

            except Exception as parse_error:
                cleaned_reply = (agent_reply or "").strip()

                try:
                    extracted_json = extract_first_balanced_json_object(cleaned_reply)
                    agent_result = parse_agent_output(extracted_json)
                    try:
                        agent_result = finalize_agent_result_after_parse(
                            agent_result,
                            retrieved_module_context,
                            retrieved_value_context,
                        )
                    except ModuleVariableValuesRequired as variable_error:
                        agent_result["files"] = variable_error.files
                        agent_result["_module_variable_values_required"] = True
                        agent_result["_module_variable_issues"] = variable_error.issues
                        return _start_module_variable_value_selection_response(
                            conversation_id=conversation_id,
                            conversation_label=conversation_label,
                            ticket_number=ticket_number,
                            ticket_link=ticket_link,
                            ticket_title=ticket_title,
                            effective_prompt=effective_prompt,
                            agent_result=agent_result,
                            issues=variable_error.issues,
                        )
                    if effective_workflow in INFRA_MODIFICATION_WORKFLOWS:
                        agent_result["workflow"] = effective_workflow
                        agent_result["repo_target"] = normalize_repo_target(
                            agent_result["cloud"],
                            repo_target=agent_result.get("repo_target"),
                            workflow=effective_workflow,
                        )
                        agent_result["state_bucket"] = state_bucket_for_target(
                            agent_result["cloud"],
                            agent_result.get("repo_target"),
                            effective_workflow,
                        )
                        agent_result = enforce_modification_uses_backend_matched_files(
                            agent_result,
                            retrieved_value_context,
                        )
                    agent_result = _teams_ensure_flag_enable_in_env_values(
                        agent_result,
                        effective_prompt,
                        retrieved_value_context,
                        cloud=target_cloud,
                        workflow=effective_workflow,
                    )

                    target_cloud = agent_result["cloud"]
                    if conversation_id:
                        set_last_selected_cloud(conversation_id, target_cloud)

                except Exception:
                    recovered_agent_result = None

                    # A Teams infrastructure invocation is never allowed to fall
                    # back to chat merely because Foundry returned a prose plan or
                    # permission request instead of JSON.  The repository evidence
                    # and user intent are already resolved, so retry once with a
                    # hard execute-now instruction and continue through the normal
                    # validation/commit pipeline.  This is the exact guard for the
                    # "Please confirm ... if you approve" regression.
                    if _invocation_active:
                        try:
                            no_question_corrective = None
                            if target_cloud == "azure":
                                no_question_corrective = _teams_azure_object_backed_no_question_corrective(
                                    effective_prompt,
                                    retrieved_value_context,
                                )
                            if not no_question_corrective:
                                no_question_corrective = _teams_flagless_creation_corrective(
                                    effective_prompt,
                                    retrieved_value_context,
                                )
                            if no_question_corrective:
                                strict_execute = (
                                    no_question_corrective
                                    + " EXECUTE NOW. Do not describe a plan, do not ask for "
                                      "permission/confirmation/approval, and do not return chat prose. "
                                      "Return the strict Terraform JSON envelope with files[] populated "
                                      "and questions=[] in this response."
                                )
                                conversation_id, retry_reply = call_agent(
                                    conversation_id,
                                    strict_execute,
                                )
                                retry_reply = _teams_apply_agent_identity(
                                    retry_reply,
                                    target_cloud,
                                    effective_workflow,
                                )
                                retry_clarification = _teams_intercept_agent_questions(retry_reply)
                                if retry_clarification is None:
                                    recovered_agent_result = try_parse_agent_output(retry_reply)
                                    recovered_agent_result = finalize_agent_result_after_parse(
                                        recovered_agent_result,
                                        retrieved_module_context,
                                        retrieved_value_context,
                                    )
                                    if effective_workflow in INFRA_MODIFICATION_WORKFLOWS:
                                        recovered_agent_result["workflow"] = effective_workflow
                                        recovered_agent_result["repo_target"] = normalize_repo_target(
                                            recovered_agent_result["cloud"],
                                            repo_target=recovered_agent_result.get("repo_target"),
                                            workflow=effective_workflow,
                                        )
                                        recovered_agent_result["state_bucket"] = state_bucket_for_target(
                                            recovered_agent_result["cloud"],
                                            recovered_agent_result.get("repo_target"),
                                            effective_workflow,
                                        )
                                        recovered_agent_result = enforce_modification_uses_backend_matched_files(
                                            recovered_agent_result,
                                            retrieved_value_context,
                                        )
                                    recovered_agent_result = _teams_ensure_flag_enable_in_env_values(
                                        recovered_agent_result,
                                        effective_prompt,
                                        retrieved_value_context,
                                        cloud=target_cloud,
                                        workflow=effective_workflow,
                                    )
                                    agent_reply = retry_reply
                        except Exception as execute_retry_error:
                            LOGGER.warning(
                                "Teams execute-now retry did not materialize files: %s",
                                execute_retry_error,
                            )

                    if recovered_agent_result is not None:
                        agent_result = recovered_agent_result
                        target_cloud = agent_result["cloud"]
                        if conversation_id:
                            set_last_selected_cloud(conversation_id, target_cloud)
                    elif agent_reply_looks_like_infra_json(cleaned_reply) or looks_like_infra_payload(cleaned_reply):
                        return {
                            "ok": False,
                            "mode": "clarification",
                            "reply": build_user_friendly_error(str(parse_error)),
                            "thread_id": conversation_id,
                            "conversation_label": conversation_label,
                            "cloud": target_cloud,
                            "jira_ticket": ticket_number,
                            "ticket_number": ticket_number,
                            "ticket_link": ticket_link,
                            "ticket_title": ticket_title,
                        }, 400
                    elif _invocation_active:
                        # Never leak an agent planning/permission paragraph to
                        # Teams as successful chat.  Keep this response concise
                        # if all internal materialization attempts failed; branch
                        # state remains intact and no stale files are pushed.
                        return {
                            "ok": False,
                            "mode": "clarification",
                            "reply": (
                                "Terrabot could not materialize the repository-grounded change after an internal generation retry. "
                                "No repository files were changed."
                            ),
                            "thread_id": conversation_id,
                            "conversation_label": conversation_label,
                            "cloud": target_cloud,
                            "jira_ticket": ticket_number,
                            "ticket_number": ticket_number,
                            "ticket_link": ticket_link,
                            "ticket_title": ticket_title,
                            "diagnostic_code": "TEAMS_INVOCATION_EXECUTE_NOW_RETRY_EXHAUSTED",
                        }, 500
                    else:
                        return {
                            "ok": True,
                            "mode": "chat",
                            "reply": cleaned_reply or "No response returned from agent.",
                            "thread_id": conversation_id,
                            "conversation_label": conversation_label,
                            "jira_ticket": ticket_number,
                            "ticket_number": ticket_number,
                            "ticket_link": ticket_link,
                            "ticket_title": ticket_title,
                            "thread_prs": build_thread_prs_payload(conversation_id) if conversation_id else {},
                        }, 200

            try:
                pending_key = store_pending_infra_change(
                    conversation_id,
                    ticket_number,
                    effective_prompt,
                    agent_result,
                    ticket_link=ticket_link,
                    ticket_title=ticket_title,
                )
            except TypeError:
                pending_key = store_pending_infra_change(
                    conversation_id,
                    ticket_number,
                    effective_prompt,
                    agent_result,
                )

            clear_pending_cloud_clarification(conversation_id, ticket_number)
            clear_pending_azure_module_discovery(conversation_id, ticket_number)
            clear_pending_azure_consumer_value_selection(conversation_id, ticket_number)
            clear_pending_azure_new_consumer_file_confirmation(conversation_id, ticket_number)
            clear_pending_module_variable_value_selection(conversation_id, ticket_number)
            clear_pending_aws_module_discovery(conversation_id, ticket_number)

            preview_reply = "Terraform changes are ready. Do you want to commit these changes to the PR?"
            routing_summary = agent_result.get("routing_summary") or {}
            if agent_result.get("workflow") == "azure_consumer_generation" and routing_summary:
                variables_added = routing_summary.get("variables_added") or []
                variables_note = ""
                if variables_added:
                    variables_note = (
                        f" I also added missing root variable declaration(s) to variables.tf: "
                        f"{', '.join(variables_added)}."
                    )
                preview_reply = (
                    "Terraform changes are ready. I am generating the Azure module invocation in "
                    f"{routing_summary.get('consumer_file')} and variable values in "
                    f"{routing_summary.get('tfvars_file')}, preserving the existing contents of each updated file."
                    f"{variables_note} "
                    "Do you want to commit these changes to the PR?"
                )

            return {
                "ok": True,
                "mode": "infra_preview",
                "reply": preview_reply,
                "thread_id": conversation_id,
                "conversation_label": conversation_label,
                "jira_ticket": ticket_number,
                "ticket_number": ticket_number,
                "ticket_link": ticket_link,
                "ticket_title": ticket_title,
                "pending_change_id": pending_key,
                "cloud": agent_result["cloud"],
                "workflow": agent_result.get("workflow") or effective_workflow,
                "title": agent_result["title"],
                "summary": agent_result["summary"],
                "files": [f["filename"] for f in agent_result["files"]],
                "thread_prs": build_thread_prs_payload(conversation_id),
                "repo_target": agent_result["repo_target"],
                "state_bucket": agent_result["state_bucket"],
                "target_consumer_file": (agent_result.get("routing_summary") or {}).get("consumer_file"),
                "target_tfvars_file": (agent_result.get("routing_summary") or {}).get("tfvars_file"),
                "target_variables_file": (agent_result.get("routing_summary") or {}).get("variables_file"),
                "variables_added": (agent_result.get("routing_summary") or {}).get("variables_added") or [],
                "router": {
                    "request_type": router_decision.request_type,
                    "cloud": agent_result["cloud"],
                    "workflow": agent_result.get("workflow") or effective_workflow,
                    "reason": router_decision.reason,
                },
            }, 200

        conversation_id, reply = call_agent(conversation_id, prompt)

        if not reply.strip():
            reply = "No response returned from agent."

        conversation_label = build_enhanced_conversation_label(
            ticket_number=ticket_number,
            ticket_title=ticket_title,
            conversation_id=conversation_id,
        )

        return {
            "ok": True,
            "mode": "chat",
            "reply": reply,
            "thread_id": conversation_id,
            "conversation_label": conversation_label,
            "jira_ticket": ticket_number,
            "ticket_number": ticket_number,
            "ticket_link": ticket_link,
            "ticket_title": ticket_title,
            "thread_prs": build_thread_prs_payload(conversation_id) if conversation_id else {},
        }, 200

    except Exception as e:
        return {
            "ok": False,
            "reply": build_user_friendly_error(str(e)),
            "error": str(e),
        }, 400

print("AZDO org:", AZDO_ORG)
print("AZDO project:", AZDO_PROJECT)
print("AZDO pipeline id:", AZDO_PIPELINE_ID)
print("AZDO PAT present:", bool((AZDO_PAT or "").strip()))
print("AZDO PAT length:", len((AZDO_PAT or "").strip()))

def handle_plan_risk_request(data: dict, headers=None):
    del headers
    data = data or {}

    required = [
        "repo_owner",
        "repo_name",
        "pr_number",
        "branch_name",
        "commit_sha",
        "build_id",
        "module_directory",
        "folder",
        "tfplan",
    ]

    missing = [k for k in required if k not in data or data.get(k) in (None, "")]
    if missing:
        return {
            "ok": False,
            "reply": f"Missing required fields: {', '.join(missing)}",
            "received_keys": sorted(list(data.keys())),
        }, 400

    try:
        agent_input = build_plan_risk_agent_input(data["tfplan"], data)
        agent_reply = call_named_agent(json.dumps(agent_input, indent=2), PLAN_RISK_AGENT_NAME)

        if not agent_reply.strip():
            raise RuntimeError("No response returned from plan-risk agent.")

        parsed = extract_json_safely(agent_reply)
        if not parsed:
            parsed = {
                "headline": "Plan-risk agent returned non-JSON output",
                "summary_markdown": "| Resource | Action | Risk | Reason |\n|---|---|---|---|\n| N/A | N/A | Unknown | Agent reply could not be parsed as JSON. |",
                "risk_markdown": f"| Severity | Finding | Impact | Recommendation |\n|---|---|---|---|\n| medium | Agent output parsing failed | PR analysis may be incomplete | Review backend logs and agent instructions. |\n\nRaw reply:\n\n```text\n{agent_reply[:4000]}\n```",
                "overall_risk": "medium",
            }

        pr_comment = build_pr_comment_from_agent_result(parsed, data)

        comment_result = github_upsert_pr_summary_comment(
            owner=str(data["repo_owner"]),
            repo=str(data["repo_name"]),
            pr_number=int(data["pr_number"]),
            body=pr_comment,
        )

        return {
            "ok": True,
            "reply": "Plan-risk analysis completed and PR comment updated.",
            "headline": parsed.get("headline"),
            "overall_risk": parsed.get("overall_risk"),
            "repo_owner": data.get("repo_owner"),
            "repo_name": data.get("repo_name"),
            "pr_number": data.get("pr_number"),
            "comment_url": comment_result.get("html_url"),
        }, 200

    except Exception as e:
        return {
            "ok": False,
            "reply": build_user_friendly_error(str(e)),
            "error": str(e),
            "repo_owner": data.get("repo_owner"),
            "repo_name": data.get("repo_name"),
            "pr_number": data.get("pr_number"),
        }, 400


# ---------------------------------------------------------------------------
# Promotion drift workflow
# ---------------------------------------------------------------------------
# This workflow is intentionally separate from the existing PR plan-risk flow.
# It detects "promotion drift": Terraform-managed resources or planned actions
# present in NPR/non-prod but missing from PRD/prod, then attributes the likely
# source commit/PR in GitHub.


def drift_utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_drift_provider(provider: Any | None) -> str:
    value = (provider or "").strip().lower()
    aliases = {
        "amazon": "aws",
        "amazon-web-services": "aws",
        "az": "azure",
        "microsoft-azure": "azure",
    }
    value = aliases.get(value, value)
    if value not in {"aws", "azure"}:
        raise ValueError("provider must be either 'aws' or 'azure'.")
    return value


def drift_repo_for_provider(provider: str) -> str:
    provider = normalize_drift_provider(provider)
    repo = GITHUB_AWS_REPO if provider == "aws" else GITHUB_AZURE_REPO
    if not repo:
        raise RuntimeError(f"Missing GitHub repo setting for provider '{provider}'.")
    return repo


def drift_base_branch_for_provider(provider: str) -> str:
    provider = normalize_drift_provider(provider)
    return GITHUB_AWS_BASE_BRANCH if provider == "aws" else GITHUB_AZURE_BASE_BRANCH


def drift_pipeline_id_for_provider(provider: str) -> str:
    provider = normalize_drift_provider(provider)
    pipeline_id = AZDO_AWS_DRIFT_PIPELINE_ID if provider == "aws" else AZDO_AZURE_DRIFT_PIPELINE_ID
    if not pipeline_id:
        raise RuntimeError(
            f"Missing Azure DevOps drift pipeline id for {provider}. "
            f"Set {'AZDO_AWS_DRIFT_PIPELINE_ID' if provider == 'aws' else 'AZDO_AZURE_DRIFT_PIPELINE_ID'}."
        )
    return pipeline_id


def drift_pipeline_branch_for_provider(provider: str) -> str:
    provider = normalize_drift_provider(provider)
    branch = AZDO_AWS_DRIFT_PIPELINE_BRANCH if provider == "aws" else AZDO_AZURE_DRIFT_PIPELINE_BRANCH
    return (branch or AZDO_PIPELINE_BRANCH or "terrabot-test").replace("refs/heads/", "").strip()


def drift_public_ingest_url() -> str:
    if not TERRABOT_BACKEND_BASE_URL:
        return ""
    return f"{TERRABOT_BACKEND_BASE_URL}/api/drift-ingest"


def drift_auth_headers_ok(headers) -> bool:
    expected = (TERRABOT_BACKEND_API_KEY or "").strip()
    if not expected:
        return True

    headers = headers or {}
    try:
        provided = (
            headers.get("x-terrabot-api-key")
            or headers.get("X-Terrabot-Api-Key")
            or ""
        ).strip()
        auth_header = (headers.get("Authorization") or headers.get("authorization") or "").strip()
    except AttributeError:
        provided = ""
        auth_header = ""

    return provided == expected or auth_header == f"Bearer {expected}"


def load_drift_store() -> dict:
    path = TERRABOT_DRIFT_STORE_PATH
    try:
        if not path or not os.path.isfile(path):
            return {"runs": {}, "latest_by_provider": {}}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"runs": {}, "latest_by_provider": {}}
        data.setdefault("runs", {})
        data.setdefault("latest_by_provider", {})
        return data
    except Exception as store_error:
        print(f"Failed to read drift store {path}: {store_error}")
        return {"runs": {}, "latest_by_provider": {}}


def save_drift_store(data: dict) -> None:
    path = TERRABOT_DRIFT_STORE_PATH
    if not path:
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(temp_path, path)


def summarize_drift_for_status(run: dict) -> dict:
    provider = normalize_drift_provider(run.get("provider") or "aws")
    agent_result = run.get("agent_result") or run.get("foundry_result") or {}
    if isinstance(agent_result, str):
        try:
            agent_result = json.loads(agent_result)
        except Exception:
            agent_result = {"summary_markdown": agent_result[:4000]}

    raw_resources = agent_result.get("resources") or run.get("resources") or []
    resources: list[dict[str, Any]] = (
        [item for item in raw_resources if isinstance(item, dict)]
        if isinstance(raw_resources, list)
        else []
    )
    environments = []
    raw_summary = agent_result.get("summary") or {}
    summary: dict[str, Any] = raw_summary if isinstance(raw_summary, dict) else {}
    status = "drift" if agent_result.get("drift_detected") or resources else "clean"
    severity = (agent_result.get("severity") or summary.get("severity") or "info").lower()

    env_name = agent_result.get("environment") or run.get("scope") or "NPR vs PRD"
    raw_changes = agent_result.get("changes") or {}
    if isinstance(raw_changes, list):
        changes = {"create": 0, "delete": 0, "update": 0, "replace": 0}
        for item in raw_changes:
            action = str((item or {}).get("change_type") or (item or {}).get("action") or "").lower()
            if action in changes:
                changes[action] += 1
            elif action == "destroy":
                changes["delete"] += 1
            elif action == "recreate":
                changes["replace"] += 1
    elif isinstance(raw_changes, dict):
        changes = raw_changes
    else:
        changes = {}

    if not changes:
        changes = {
            "create": len([r for r in resources if str(r.get("classification") or r.get("action") or r.get("npr_action") or "").lower() in {"create", "missing_in_prd", "npr_only", "inventory_only"}]),
            "delete": len([r for r in resources if str(r.get("classification") or r.get("action") or r.get("npr_action") or "").lower() in {"delete", "removed_in_npr", "prd_only"}]),
            "update": len([r for r in resources if str(r.get("classification") or r.get("action") or r.get("npr_action") or "").lower() in {"update", "changed"}]),
            "replace": len([r for r in resources if str(r.get("classification") or r.get("action") or r.get("npr_action") or "").lower() in {"replace", "recreate"}]),
        }

    environments.append({
        "name": env_name,
        "stage": "NPR vs PRD promotion drift",
        "status": status,
        "severity": severity,
        "summary": agent_result.get("headline") or summary.get("headline") or "Promotion drift analysis complete",
        "changes": changes,
        "last_checked": run.get("completed_at") or run.get("updated_at") or run.get("started_at"),
        "run_url": (run.get("pipeline") or {}).get("url"),
        "artifact_url": (run.get("pipeline") or {}).get("artifact_url"),
        "resources": resources[:25] if isinstance(resources, list) else [],
        "attribution": run.get("attribution") or [],
    })

    return {
        "label": "AWS" if provider == "aws" else "Azure",
        "repo": drift_repo_for_provider(provider),
        "branch": drift_base_branch_for_provider(provider),
        "environments": environments,
    }


def queue_drift_pipeline(provider: str, requested_by: Optional[str] = None, scope: Optional[str] = None, extra_variables: Optional[dict] = None) -> dict:
    provider = normalize_drift_provider(provider)
    missing = []
    if not AZDO_ORG:
        missing.append("AZDO_ORG")
    if not AZDO_PROJECT:
        missing.append("AZDO_PROJECT")
    if not AZDO_PAT:
        missing.append("AZDO_PAT")
    if missing:
        raise RuntimeError("Missing Azure DevOps pipeline settings: " + ", ".join(missing))

    pipeline_id = drift_pipeline_id_for_provider(provider)
    pipeline_branch = drift_pipeline_branch_for_provider(provider)
    drift_run_id = f"drift-{provider}-{uuid.uuid4().hex[:12]}"

    variables: dict[str, dict[str, Any]] = {
        "DRIFT_MODE": {"value": "true"},
        "DRIFT_PROVIDER": {"value": provider},
        "DRIFT_RUN_ID": {"value": drift_run_id},
        "DRIFT_SCOPE": {"value": scope or "all"},
        "TERRABOT_BACKEND_DRIFT_INGEST_URL": {"value": drift_public_ingest_url()},
        "TERRABOT_REQUESTED_BY": {"value": requested_by or "terrabot-ui"},
    }

    if TERRABOT_BACKEND_API_KEY:
        variables["TERRABOT_BACKEND_API_KEY"] = {"value": TERRABOT_BACKEND_API_KEY, "isSecret": True}

    for key, value in (extra_variables or {}).items():
        if value is None:
            continue
        variables[str(key)] = {"value": str(value)}

    url = (
        f"https://dev.azure.com/{AZDO_ORG}/{AZDO_PROJECT}"
        f"/_apis/build/builds?api-version={AZDO_API_VERSION}"
    )

    payload = {
        "definition": {"id": int(pipeline_id)},
        "sourceBranch": f"refs/heads/{pipeline_branch}",
        "variables": variables,
    }

    response = requests.post(url, headers=azure_devops_headers(), json=payload, timeout=30)
    print("AZDO drift queue status:", response.status_code)
    print("AZDO drift queue body:", response.text[:4000])
    response.raise_for_status()
    run = response.json()

    store = load_drift_store()
    store["runs"][drift_run_id] = {
        "provider": provider,
        "run_id": drift_run_id,
        "status": "queued",
        "scope": scope or "all",
        "requested_by": requested_by or "terrabot-ui",
        "started_at": drift_utc_now_iso(),
        "pipeline": {
            "id": run.get("id"),
            "build_number": run.get("buildNumber"),
            "url": ((run.get("_links") or {}).get("web") or {}).get("href") or run.get("url"),
            "source_branch": f"refs/heads/{pipeline_branch}",
            "definition_id": pipeline_id,
        },
    }
    store["latest_by_provider"][provider] = drift_run_id
    save_drift_store(store)

    return {
        "provider": provider,
        "drift_run_id": drift_run_id,
        "pipeline_branch": pipeline_branch,
        "pipeline_id": pipeline_id,
        "run": run,
    }


def extract_response_text(response_obj) -> str:
    if response_obj is None:
        return ""
    direct = getattr(response_obj, "output_text", None)
    if direct:
        return str(direct)
    try:
        data = response_obj.model_dump()
    except Exception:
        try:
            data = json.loads(str(response_obj))
        except Exception:
            return str(response_obj)

    pieces = []
    for output in data.get("output", []) or []:
        if output.get("type") in {"output_text", "text"}:
            text = output.get("text")
            if isinstance(text, dict):
                text = text.get("value") or text.get("text")
            if text:
                pieces.append(str(text))
        if output.get("type") in {"message", "output_message"}:
            for item in output.get("content", []) or []:
                text = item.get("text") or item.get("value")
                if isinstance(text, dict):
                    text = text.get("value") or text.get("text")
                if text:
                    pieces.append(str(text))
    return "\n".join(pieces).strip()


def call_drift_agent(message: str, previous_response_id: Optional[str] = None) -> dict:
    if not DRIFT_AGENT_NAME:
        raise RuntimeError("Missing DRIFT_AGENT_NAME / foundry_agent_name environment variable.")

    agent_reference = find_agent_reference(DRIFT_AGENT_NAME)
    client = get_project_client()
    with client.get_openai_client() as openai_client:
        kwargs = {
            "input": message,
            "extra_body": {"agent_reference": agent_reference},
        }
        if previous_response_id:
            kwargs["previous_response_id"] = previous_response_id
        response = openai_client.responses.create(**kwargs)

    return {
        "response_id": getattr(response, "id", None),
        "reply": extract_response_text(response),
    }


def extract_json_from_agent_text(text: str) -> dict:
    parsed = extract_json_safely(text) if "extract_json_safely" in globals() else None
    if parsed:
        return parsed
    cleaned = (text or "").strip()
    if not cleaned:
        return {}
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    try:
        candidate = extract_first_balanced_json_object(cleaned)
        return json.loads(candidate)
    except Exception:
        return {"summary_markdown": cleaned[:6000]}


def normalize_drift_resource(resource: dict) -> dict:
    resource = resource or {}
    address = str(resource.get("address") or resource.get("terraform_address") or resource.get("resource") or "").strip()
    resource_type = str(resource.get("type") or resource.get("resource_type") or "").strip()
    resource_name = str(resource.get("name") or resource.get("resource_name") or "").strip()

    if address and (not resource_type or not resource_name):
        match = re.search(r"(?:^|\.)([a-zA-Z0-9_]+_[a-zA-Z0-9_]+)\.([A-Za-z0-9_-]+)(?:\[|$)", address)
        if match:
            resource_type = resource_type or match.group(1)
            resource_name = resource_name or match.group(2)

    return {
        **resource,
        "address": address,
        "type": resource_type,
        "name": resource_name,
        "source_file": resource.get("source_file") or resource.get("file") or resource.get("path") or resource.get("tf_file") or "",
    }


def github_search_resource_files(owner: str, repo: str, branch: str, resource: dict, max_results: int = 5) -> list:
    resource = normalize_drift_resource(resource)
    candidates = []
    source_file = resource.get("source_file") or ""
    if source_file:
        candidates.append({"path": source_file, "reason": "resource payload source_file"})

    queries = []
    if resource.get("type") and resource.get("name"):
        queries.append(f'repo:{owner}/{repo} resource "{resource["type"]}" "{resource["name"]}" extension:tf')
        queries.append(f'repo:{owner}/{repo} "{resource["type"]}.{resource["name"]}" extension:tf')
    if resource.get("address"):
        short_address = resource["address"].split("[")[0]
        queries.append(f'repo:{owner}/{repo} "{short_address}" extension:tf')

    seen = {source_file} if source_file else set()
    for query in queries:
        try:
            response = requests.get(
                f"{GITHUB_API}/search/code",
                headers=github_headers_for_repo(),
                params={"q": query, "per_page": max_results},
                timeout=30,
            )
            if response.status_code >= 400:
                print(f"GitHub code search failed {response.status_code}: {response.text[:500]}")
                continue
            for item in response.json().get("items", []) or []:
                path = item.get("path")
                if path and path not in seen:
                    seen.add(path)
                    candidates.append({
                        "path": path,
                        "html_url": item.get("html_url"),
                        "reason": "github code search",
                    })
        except Exception as search_error:
            print(f"GitHub resource search failed for {owner}/{repo}: {search_error}")

    return candidates[:max_results]


def github_list_commits_for_resource_path(owner: str, repo: str, path: str, branch: str, per_page: Optional[int] = None) -> list:
    if not path:
        return []
    per_page = per_page or DRIFT_GITHUB_LOOKBACK_COMMITS
    response = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/commits",
        headers=github_headers_for_repo(),
        params={"path": path, "sha": branch or None, "per_page": per_page},
        timeout=30,
    )
    if response.status_code >= 400:
        print(f"GitHub commits lookup failed {response.status_code}: {response.text[:500]}")
        return []
    return response.json() or []


def github_pull_requests_for_commit(owner: str, repo: str, sha: str) -> list:
    if not sha:
        return []
    headers = github_headers_for_repo()
    headers["Accept"] = "application/vnd.github+json"
    response = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/commits/{sha}/pulls",
        headers=headers,
        params={"per_page": 10},
        timeout=30,
    )
    if response.status_code >= 400:
        print(f"GitHub commit PR lookup failed {response.status_code}: {response.text[:500]}")
        return []
    return response.json() or []


def build_resource_attribution(provider: str, resources: list, branch: Optional[str] = None) -> list:
    provider = normalize_drift_provider(provider)
    owner = GITHUB_OWNER
    repo = drift_repo_for_provider(provider)
    branch = (branch or drift_base_branch_for_provider(provider) or "main").replace("refs/heads/", "")

    if not owner or not repo or not GITHUB_TOKEN:
        return [{
            "ok": False,
            "reason": "Missing GITHUB_OWNER, provider repo, or GITHUB_TOKEN; attribution skipped.",
        }]

    attributions = []
    for raw_resource in (resources or [])[:50]:
        resource = normalize_drift_resource(raw_resource)
        files = github_search_resource_files(owner, repo, branch, resource)
        file_attributions = []
        for file_info in files[:5]:
            path = file_info.get("path")
            commits = github_list_commits_for_resource_path(owner, repo, path, branch=branch)
            commit_results = []
            for commit in commits[:5]:
                sha = commit.get("sha")
                commit_info = commit.get("commit") or {}
                author_info = commit.get("author") or {}
                committer_info = commit.get("committer") or {}
                prs = github_pull_requests_for_commit(owner, repo, sha)
                commit_results.append({
                    "sha": sha,
                    "short_sha": sha[:7] if sha else "",
                    "message": (commit_info.get("message") or "").split("\n", 1)[0],
                    "html_url": commit.get("html_url"),
                    "author_login": author_info.get("login") or committer_info.get("login"),
                    "author_html_url": author_info.get("html_url") or committer_info.get("html_url"),
                    "commit_author_name": ((commit_info.get("author") or {}).get("name")),
                    "commit_author_email": ((commit_info.get("author") or {}).get("email")),
                    "date": ((commit_info.get("author") or {}).get("date")),
                    "pull_requests": [
                        {
                            "number": pr.get("number"),
                            "title": pr.get("title"),
                            "state": pr.get("state"),
                            "html_url": pr.get("html_url"),
                            "user_login": (pr.get("user") or {}).get("login"),
                            "user_html_url": (pr.get("user") or {}).get("html_url"),
                            "merged_at": pr.get("merged_at"),
                        }
                        for pr in prs[:5]
                    ],
                })
            file_attributions.append({**file_info, "commits": commit_results})

        attributions.append({
            "resource": resource,
            "files": file_attributions,
            "best_commit": (file_attributions[0].get("commits") or [None])[0] if file_attributions else None,
            "best_pull_request": (((file_attributions[0].get("commits") or [{}])[0]).get("pull_requests") or [None])[0] if file_attributions else None,
        })
    return attributions


def build_drift_chat_context(provider: Optional[str] = None) -> dict:
    store = load_drift_store()
    if provider:
        provider = normalize_drift_provider(provider)
        run_id = store.get("latest_by_provider", {}).get(provider)
        return store.get("runs", {}).get(run_id, {}) if run_id else {}
    latest = {}
    for provider_key, run_id in store.get("latest_by_provider", {}).items():
        latest[provider_key] = store.get("runs", {}).get(run_id, {})
    return latest


def handle_drift_trigger_request(data: dict, headers=None):
    del headers
    data = data or {}
    try:
        provider = normalize_drift_provider(data.get("provider"))
        requested_by = data.get("requested_by") or data.get("user") or "terrabot-ui"
        scope = data.get("scope") or "all"
        extra_variables = data.get("variables") if isinstance(data.get("variables"), dict) else {}
        result = queue_drift_pipeline(
            provider=provider,
            requested_by=requested_by,
            scope=scope,
            extra_variables=extra_variables,
        )
        return {
            "ok": True,
            "reply": f"{provider.upper()} promotion drift pipeline queued.",
            "provider": provider,
            "drift_run_id": result["drift_run_id"],
            "pipeline_id": result["pipeline_id"],
            "pipeline_branch": result["pipeline_branch"],
            "run": result.get("run"),
        }, 200
    except Exception as e:
        return {
            "ok": False,
            "reply": build_user_friendly_error(str(e)) if "build_user_friendly_error" in globals() else str(e),
            "error": str(e),
        }, 400


def handle_drift_ingest_request(data: dict, headers=None):
    if not drift_auth_headers_ok(headers):
        return {"ok": False, "reply": "Unauthorized drift ingest request."}, 401

    data = data or {}
    try:
        provider = normalize_drift_provider(data.get("provider") or data.get("drift_provider"))
        run_id = data.get("drift_run_id") or data.get("run_id") or f"drift-{provider}-{uuid.uuid4().hex[:12]}"
        agent_result = data.get("agent_result") or data.get("foundry_result") or {}
        if isinstance(agent_result, str):
            agent_result = extract_json_from_agent_text(agent_result)

        resources = data.get("resources") or agent_result.get("resources") or agent_result.get("drift_resources") or []
        if not isinstance(resources, list):
            resources = []

        branch = data.get("github_branch") or data.get("branch") or drift_base_branch_for_provider(provider)
        attribution = build_resource_attribution(provider, resources, branch=branch) if resources else []

        now = drift_utc_now_iso()
        store = load_drift_store()
        existing = store.get("runs", {}).get(run_id, {})
        run_payload = {
            **existing,
            **data,
            "provider": provider,
            "run_id": run_id,
            "status": "completed",
            "updated_at": now,
            "completed_at": now,
            "agent_result": agent_result,
            "resources": resources,
            "attribution": attribution,
        }
        store.setdefault("runs", {})[run_id] = run_payload
        store.setdefault("latest_by_provider", {})[provider] = run_id
        save_drift_store(store)

        return {
            "ok": True,
            "reply": "Promotion drift result ingested.",
            "provider": provider,
            "drift_run_id": run_id,
            "resource_count": len(resources),
            "attribution_count": len(attribution),
        }, 200
    except Exception as e:
        return {
            "ok": False,
            "reply": build_user_friendly_error(str(e)) if "build_user_friendly_error" in globals() else str(e),
            "error": str(e),
        }, 400


def handle_drift_status_request(data: Optional[dict] = None, headers=None):
    del headers
    data = data or {}
    try:
        store = load_drift_store()
        latest_by_provider = store.get("latest_by_provider", {})
        runs = store.get("runs", {})
        providers = {}
        has_live_data = False
        alerts = []

        for provider in ("aws", "azure"):
            run_id = latest_by_provider.get(provider)
            if run_id and run_id in runs:
                has_live_data = True
                run = runs[run_id]
                providers[provider] = summarize_drift_for_status(run)
                for env in providers[provider].get("environments", []):
                    if env.get("status") == "drift" and env.get("severity") in {"high", "critical"}:
                        alerts.append({
                            "id": f"{provider}-{run_id}",
                            "provider": provider.upper(),
                            "environment": env.get("name"),
                            "severity": env.get("severity"),
                            "message": env.get("summary"),
                        })

        return {
            "ok": True,
            "has_live_data": has_live_data,
            "drift": {
                "generatedAt": drift_utc_now_iso(),
                "providers": providers,
                "alerts": alerts,
                "runs": {k: {"provider": v.get("provider"), "status": v.get("status"), "updated_at": v.get("updated_at")} for k, v in runs.items()},
            },
        }, 200
    except Exception as e:
        return {
            "ok": False,
            "reply": build_user_friendly_error(str(e)) if "build_user_friendly_error" in globals() else str(e),
            "error": str(e),
        }, 400


def handle_drift_agent_chat_request(data: dict, headers=None):
    del headers
    data = data or {}
    try:
        provider = normalize_drift_provider(data.get("provider") or "aws")
        message = (data.get("message") or data.get("prompt") or "").strip()
        previous_response_id = data.get("previous_response_id")
        if not message:
            return {"ok": False, "reply": "message is required."}, 400

        context = build_drift_chat_context(provider)
        agent_input = (
            "You are the Terrabot promotion drift assistant. Answer the user's question using only the latest "
            "stored drift run context below. If the answer is not available in context, say what is missing and "
            "which drift pipeline should be re-run.\n\n"
            f"provider={provider}\n"
            f"latest_drift_context_json={json.dumps(context, default=str)[:120000]}\n\n"
            f"user_question={message}"
        )
        result = call_drift_agent(agent_input, previous_response_id=previous_response_id)
        return {
            "ok": True,
            "mode": "foundry",
            "provider": provider,
            "reply": result.get("reply") or "No response returned from the Drift Agent.",
            "response_id": result.get("response_id"),
            "previous_response_id": result.get("response_id"),
        }, 200
    except Exception as e:
        return {
            "ok": False,
            "mode": "error",
            "reply": build_user_friendly_error(str(e)) if "build_user_friendly_error" in globals() else str(e),
            "error": str(e),
        }, 400


def handle_drift_attribution_request(data: dict, headers=None):
    del headers
    data = data or {}
    try:
        provider = normalize_drift_provider(data.get("provider") or "aws")
        resources = data.get("resources") or []
        if not isinstance(resources, list):
            return {"ok": False, "reply": "resources must be a list."}, 400
        attribution = build_resource_attribution(
            provider,
            resources,
            branch=data.get("branch") or drift_base_branch_for_provider(provider),
        )
        return {
            "ok": True,
            "provider": provider,
            "attribution": attribution,
        }, 200
    except Exception as e:
        return {
            "ok": False,
            "reply": build_user_friendly_error(str(e)) if "build_user_friendly_error" in globals() else str(e),
            "error": str(e),
        }, 400

# Drift Jira ticket route wrapper. Keeps existing terrabot_service drift behavior intact
# while allowing function_app.py to route /drift-jira-ticket through this service.
def handle_drift_jira_ticket_request(data: dict, headers=None):
    try:
        try:
            from shared_code.commit_drift_service import handle_commit_drift_create_jira_request
        except Exception:
            drift_module = importlib.import_module("commit_drift_service")
            handle_commit_drift_create_jira_request = getattr(
                drift_module,
                "handle_commit_drift_create_jira_request",
            )
        return handle_commit_drift_create_jira_request(data or {}, headers)
    except Exception as e:
        return {
            "ok": False,
            "reply": "Failed to create Jira drift ticket.",
            "error": str(e),
        }, 500


def handle_drift_create_jira_request(data: dict, headers=None):
    return handle_drift_jira_ticket_request(data, headers)


def handle_commit_drift_create_jira_request(data: dict, headers=None):
    return handle_drift_jira_ticket_request(data, headers)



# Repo-aware local core adapters. These are intentionally lazy imports so the
# existing Azure Function/GitHub flows keep loading even when the local CLI-only
# dependencies are not being used.
def handle_repo_scan_request(data: dict, headers=None):
    del headers
    data = data or {}
    workspace = (data.get("workspace") or data.get("repo_path") or ".").strip()
    prompt = (data.get("prompt") or "").strip()
    try:
        from terrabot_core.service import scan_workspace
        return {"ok": True, "result": scan_workspace(workspace, prompt)}, 200
    except Exception as e:
        return {"ok": False, "reply": "Repo-aware scan failed.", "error": str(e)}, 400


def handle_repo_explain_workflow_request(data: dict, headers=None):
    del headers
    data = data or {}
    workspace = (data.get("workspace") or data.get("repo_path") or ".").strip()
    prompt = (data.get("prompt") or "Explain this repository workflow").strip()
    try:
        from terrabot_core.service import explain_workflow
        return {"ok": True, "result": explain_workflow(workspace, prompt)}, 200
    except Exception as e:
        return {"ok": False, "reply": "Repo-aware workflow explanation failed.", "error": str(e)}, 400


def handle_repo_ask_request(data: dict, headers=None):
    del headers
    data = data or {}
    workspace = (data.get("workspace") or data.get("repo_path") or ".").strip()
    prompt = (data.get("prompt") or data.get("message") or "").strip()
    if not prompt:
        return {"ok": False, "reply": "prompt is required."}, 400
    try:
        from terrabot_core.service import ask_infrastructure
        return {"ok": True, "result": ask_infrastructure(workspace, prompt)}, 200
    except Exception as e:
        return {"ok": False, "reply": "Repo-aware infrastructure planning failed.", "error": str(e)}, 400


# =============================================================================
# Teams GitHub-remote generation, branch continuity, and resilient output repair
# =============================================================================
# This block intentionally overrides only Teams-facing behavior. The VS Code
# extension continues to use the existing /api/generate path, workspace context,
# GitHub session, and Foundry output contract unchanged.

_ACTIVE_TEAMS_FLOW_CONTEXT: ContextVar[dict] = ContextVar(
    "terrabot_active_teams_flow_context",
    default={},
)

# Capture the already-defined base implementations. The public wrapper names are
# declared later in this module, so referencing them here raises NameError during
# module import and prevents Teams from loading.
_ORIGINAL_BUILD_VERIFIED_AWS_MODULE_CONTEXT = _build_verified_aws_module_context_base
_ORIGINAL_BUILD_AGENT_INPUT_FOR_INFRA = _build_agent_input_for_infra_base
_ORIGINAL_TRY_PARSE_AGENT_OUTPUT = _try_parse_agent_output_base
_ORIGINAL_REPAIR_AND_PARSE_AGENT_OUTPUT = _repair_and_parse_agent_output_base
_ORIGINAL_ADD_BACKEND_EXISTING_AWS_INFRA_CONTEXT = _add_backend_existing_aws_infra_context_base
_ORIGINAL_BUILD_BACKEND_EXISTING_INFRA_MODIFICATION_CONTEXT = _build_backend_existing_infra_modification_context_base
_ORIGINAL_COMMIT_TERRAFORM_FILES_TO_BRANCH_FOR_TEAMS = _commit_terraform_files_to_branch_for_teams_base
_ORIGINAL_CREATE_TEAMS_PULL_REQUEST_FROM_BRANCH = _create_teams_pull_request_from_branch_base
_ORIGINAL_HANDLE_TEAMS_CHAT_REQUEST = _handle_teams_chat_request_base


