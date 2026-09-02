from __future__ import annotations
from typing import TYPE_CHECKING , Any , Optional

if TYPE_CHECKING:
    from shared_code.terrabot_core_typing import (
        AFFIRMATIVE_REPLIES,
        AWS_MODULES_ROOT,
        GITHUB_API,
        GITHUB_OWNER,
        INFRA_MODIFICATION_WORKFLOWS,
        LOGGER,
        NEGATIVE_REPLIES,
        THREAD_PR_STATE,
        _ACTIVE_TEAMS_FLOW_CONTEXT,
        _ACTIVE_TEAMS_REQUESTER_DISPLAY,
        _ORIGINAL_ADD_BACKEND_EXISTING_AWS_INFRA_CONTEXT,
        _ORIGINAL_BUILD_AGENT_INPUT_FOR_INFRA,
        _ORIGINAL_BUILD_BACKEND_EXISTING_INFRA_MODIFICATION_CONTEXT,
        _ORIGINAL_BUILD_VERIFIED_AWS_MODULE_CONTEXT,
        _ORIGINAL_HANDLE_TEAMS_CHAT_REQUEST,
        _ORIGINAL_REPAIR_AND_PARSE_AGENT_OUTPUT,
        _ORIGINAL_TRY_PARSE_AGENT_OUTPUT,
        _assignment_span_from_match,
        _aws_module_catalog_branch,
        _azure_exact_environment_tfvars_candidates,
        _azure_tfvars_file_kind_from_prompt,
        _build_selected_infra_modification_context_base,
        _commit_terraform_files_to_branch_for_teams_base,
        _dominant_object_var_root,
        _explicit_iac_paths_from_prompt,
        _explicit_tfvars_path_from_prompt,
        _extract_hcl_assignment_value,
        _extract_tf_variable_block,
        _extract_tfvars_assignments_from_text,
        _extract_top_level_hcl_assignment_names,
        _extract_top_level_module_assignments,
        _find_balanced_curly_end,
        _generate_workspace_pr_metadata,
        _get_backend_existing_infra_context,
        _get_confirmed_aws_module_selection,
        _github_pull_request_template,
        _github_request_error,
        _has_top_level_tfvars_assignment,
        _hcl_nesting_depth_at_position,
        _infer_variable_type_from_name_and_default,
        _infra_modification_search_terms,
        _iter_variable_blocks_with_names,
        _matched_blocks_for_prompt,
        _module_object_field_from_pattern_expression,
        _normalize_type_expr,
        _normalized_hcl_content_for_compare,
        _require_setting,
        _rewrite_var_root_reference,
        _score_infra_candidate,
        _teams_auto_accept_aws_module_creation,
        _teams_auto_commit_preview,
        _teams_collect_backend_env_context,
        _teams_commit_side_flag_guarantee,
        _teams_extract_ticket_link_from_prompt,
        _teams_locate_environment_value_files,
        _teams_requested_resource_name,
        _teams_workflow_thread_id,
        _terraform_safe_variable_name,
        _tf_azure_hub_tfvars_file_exists,
        _tfvars_object_name_from_module_name,
        _top_level_hcl_assignment_spans,
        _top_level_tf_block_matches,
        _top_level_tfvars_assignment_field_names,
        _user_assignments_with_object_field_aliases,
        _user_selected_tfvars_assignments,
        _variable_attr_present,
        _variable_attr_value,
        _variable_name_is_private_or_sensitive,
        _variable_type_from_block,
        base64,
        call_agent,
        cloud_root_dir,
        discover_live_aws_module_candidates,
        extract_json_from_text,
        generate_short_ticket_title,
        get_or_create_thread_pr_state,
        github_branch_exists,
        github_create_branch,
        github_create_pull_request,
        github_find_pr_by_branch,
        github_get_base_branch_sha,
        github_get_directory_listing,
        github_get_file_content,
        github_headers,
        github_put_file_if_changed,
        github_repo_for_cloud,
        github_resolve_base_branch_for_cloud,
        github_search_code,
        hashlib,
        infer_cloud_from_prompt,
        infer_new_aws_module_path,
        is_valid_jira_ticket_link,
        json,
        load_teams_conversation_state,
        logging,
        normalize_agent_relative_tf_path,
        normalize_cloud,
        normalize_repo_target,
        normalize_yes_no_reply,
        parse_agent_output,
        re,
        recover_thread_pr_state,
        requests,
        resolve_aws_environment_path,
        safe_join_under_folder,
        safe_normalize_cloud,
        save_teams_conversation_state,
        set_last_selected_cloud,
        stable_thread_key,
        state_bucket_for_target,
        store_pending_infra_change,
        trigger_test_branch_pipeline_for_pr,
        validate_azure_consumer_two_file_payload_for_commit,
    )

def _teams_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _teams_prompt_requests_pr(prompt: str) -> bool:
    text = re.sub(r"\s+", " ", (prompt or "").strip().lower())
    return bool(
        re.search(r"\b(?:raise|create|open|submit|make)\b.*\b(?:pr|pull request)\b", text)
        or re.search(r"\b(?:pr|pull request)\b.*\b(?:raise|create|open|submit|now)\b", text)
    )


def _teams_prompt_requests_same_branch(prompt: str) -> bool:
    text = re.sub(r"\s+", " ", (prompt or "").strip().lower())
    return bool(
        re.search(r"\b(?:same|current|existing|this)\s+(?:github\s+)?branch\b", text)
        or re.search(r"\b(?:keep|reuse|continue on|use)\b.*\b(?:same|current|existing)\s+branch\b", text)
    )


def _teams_prompt_requests_new_branch(prompt: str) -> bool:
    text = re.sub(r"\s+", " ", (prompt or "").strip().lower())
    return bool(
        re.search(r"\b(?:new|fresh|separate|seperate|different|another)\s+(?:github\s+)?branch\b", text)
        or re.search(r"\b(?:create|start|use)\b.*\b(?:new|fresh|separate|different)\s+branch\b", text)
    )


def _teams_branch_choice_from_reply(prompt: str) -> str:
    text = normalize_yes_no_reply(prompt)
    if _teams_prompt_requests_same_branch(prompt):
        return "reuse"
    if _teams_prompt_requests_new_branch(prompt):
        return "new"
    if text in AFFIRMATIVE_REPLIES or re.fullmatch(r"(?:yes|y|reuse|same|current|existing)", text or ""):
        return "reuse"
    if text in NEGATIVE_REPLIES or re.fullmatch(r"(?:no|n|new|fresh|separate|different)", text or ""):
        return "new"
    return ""


def _teams_apply_state_patch(state: dict, patch: dict) -> dict:
    updated = dict(state or {})
    for key, value in dict(patch or {}).items():
        if value is None:
            updated.pop(key, None)
        else:
            updated[key] = value
    return updated


def _teams_save_ui_state(teams_conversation_id: str, patch: dict) -> dict:
    conversation_key = str(teams_conversation_id or "").strip()
    if not conversation_key:
        return {}
    state = load_teams_conversation_state(conversation_key) or {}
    state = _teams_apply_state_patch(state, patch)
    save_teams_conversation_state(conversation_key, state)
    return state


def _teams_current_context_branch(
    cloud: str,
    repo_target: Optional[str] = None,
    workflow: Optional[str] = None,
) -> str:
    context = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    if not context.get("active") or not _teams_truthy(context.get("reuse_branch")):
        return ""

    branch = str(context.get("existing_branch") or "").strip()
    if not branch:
        return ""

    try:
        if github_branch_exists(
            cloud,
            branch,
            repo_target=repo_target,
            workflow=workflow,
        ):
            return branch
    except Exception as exc:
        LOGGER.warning("Unable to verify Teams context branch %s: %s", branch, exc)
    return ""


def _teams_remote_context_branch(
    cloud: str,
    repo_target: Optional[str] = None,
    workflow: Optional[str] = None,
) -> str:
    branch = _teams_current_context_branch(cloud, repo_target, workflow)
    if branch:
        return branch
    return github_resolve_base_branch_for_cloud(
        cloud,
        repo_target=repo_target,
        workflow=workflow,
    )


def _teams_variable_specs_from_module_context(context: dict) -> list[dict]:
    specs: list[dict] = []
    seen: set[str] = set()
    branch = str(context.get("resolved_ref") or _aws_module_catalog_branch()).strip()

    for tf_path in context.get("tf_files") or []:
        try:
            content = github_get_file_content(
                "aws",
                tf_path,
                branch,
                repo_target="tf-devops",
                workflow="aws_module_consumer",
            ) or ""
        except Exception as exc:
            LOGGER.warning("Could not read AWS module variable context %s: %s", tf_path, exc)
            continue

        for item in _iter_variable_blocks_with_names(content):
            name = str(item.get("name") or "").strip()
            if not name or name in seen:
                continue
            block = str(item.get("block") or "")
            type_expr = _variable_type_from_block(block) or _infer_variable_type_from_name_and_default(name, block)
            default_expr = _variable_attr_value(block, "default") if _variable_attr_present(block, "default") else ""
            description_expr = _variable_attr_value(block, "description") if _variable_attr_present(block, "description") else ""
            sensitive_expr = _variable_attr_value(block, "sensitive") if _variable_attr_present(block, "sensitive") else ""
            specs.append({
                "name": name,
                "type": type_expr or "string",
                "default": default_expr,
                "required": not bool(default_expr),
                "description": description_expr,
                "sensitive": sensitive_expr.strip().lower() == "true" or _variable_name_is_private_or_sensitive(name),
                "source_path": tf_path,
            })
            seen.add(name)

    required = set(context.get("required_inputs_detected") or [])
    all_inputs = list(context.get("inputs_detected") or [])
    for name in all_inputs:
        name = str(name or "").strip()
        if not name or name in seen:
            continue
        specs.append({
            "name": name,
            "type": "string",
            "default": "",
            "required": name in required,
            "description": "",
            "sensitive": _variable_name_is_private_or_sensitive(name),
            "source_path": "",
        })
        seen.add(name)
    return specs


def _build_verified_aws_module_context_teams(
    module_rel_path: str,
    branch: Optional[str] = None,
    environment_path: str = "",
    include_examples: bool = True,
) -> dict:
    """Preserve existing discovery and enrich it with typed variable metadata."""
    context = _ORIGINAL_BUILD_VERIFIED_AWS_MODULE_CONTEXT(
        module_rel_path,
        branch=branch,
        environment_path=environment_path,
        include_examples=include_examples,
    )
    if context and not context.get("input_specs"):
        context = dict(context)
        context["input_specs"] = _teams_variable_specs_from_module_context(context)
    return context


def build_verified_aws_module_context(
    module_rel_path: str,
    branch: Optional[str] = None,
    environment_path: str = "",
    include_examples: bool = True,
) -> dict:
    """Public AWS module-context entry point used by discovery and recovery.

    A previous Teams-only override captured the base implementation but never
    restored this public symbol. Runtime callers therefore raised NameError
    while inspecting every candidate module. Keep non-Teams behavior byte-for-
    byte compatible with the original function and add typed Teams metadata only
    while a Teams flow is active.
    """
    active = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    if active.get("active"):
        return _build_verified_aws_module_context_teams(
            module_rel_path,
            branch=branch,
            environment_path=environment_path,
            include_examples=include_examples,
        )
    return _ORIGINAL_BUILD_VERIFIED_AWS_MODULE_CONTEXT(
        module_rel_path,
        branch=branch,
        environment_path=environment_path,
        include_examples=include_examples,
    )


def _add_backend_existing_aws_infra_context_teams(
    prompt: str,
    environment_path: str,
    branch: str,
    retrieved_value_context: list | None = None,
) -> list:
    """For Teams same-branch follow-ups, read the latest remote feature branch."""
    active_branch = _teams_current_context_branch(
        "aws",
        repo_target="tf-devops",
        workflow="aws_infra_modification",
    )
    return _ORIGINAL_ADD_BACKEND_EXISTING_AWS_INFRA_CONTEXT(
        prompt,
        environment_path,
        active_branch or branch,
        retrieved_value_context=retrieved_value_context,
    )


def add_backend_existing_aws_infra_context(
    prompt: str,
    environment_path: str,
    branch: str,
    retrieved_value_context: list | None = None,
) -> list:
    """Public compatibility wrapper for AWS live-infrastructure context.

    The AWS request router still calls this public name. Keep the Teams-aware
    branch selection implemented by the internal wrapper so same-branch
    follow-ups read the latest remote feature branch, while new/base-branch
    requests continue to use the branch supplied by the caller.
    """
    return _add_backend_existing_aws_infra_context_teams(
        prompt=prompt,
        environment_path=environment_path,
        branch=branch,
        retrieved_value_context=retrieved_value_context,
    )


def _build_backend_existing_infra_modification_context_teams_v1(
    prompt: str,
    thread_id: str,
    cloud: str,
    workflow: str,
    retrieved_value_context: list | None = None,
) -> dict:
    """Use the live Teams feature branch as modification evidence when selected."""
    context = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    if not context.get("active") or not _teams_truthy(context.get("reuse_branch")):
        return _ORIGINAL_BUILD_BACKEND_EXISTING_INFRA_MODIFICATION_CONTEXT(
            prompt,
            thread_id,
            cloud,
            workflow,
            retrieved_value_context=retrieved_value_context,
        )

    cloud = normalize_cloud(cloud)
    repo_target = normalize_repo_target(cloud, workflow=workflow)
    branch = _teams_remote_context_branch(cloud, repo_target, workflow)
    repo_full_name = f"{GITHUB_OWNER}/{github_repo_for_cloud(cloud, repo_target=repo_target, workflow=workflow)}"
    terms = _infra_modification_search_terms(prompt)
    seen_paths: set[str] = set()
    matched_files: list[dict] = []

    def add_path(path: str, reason: str) -> None:
        normalized_path = (path or "").strip().strip("/")
        if not normalized_path or normalized_path in seen_paths:
            return
        if not normalized_path.endswith((".tf", ".tfvars")):
            return
        try:
            content = github_get_file_content(
                cloud,
                normalized_path,
                branch,
                repo_target=repo_target,
                workflow=workflow,
            )
        except Exception:
            content = None
        if not content:
            return
        score = _score_infra_candidate(normalized_path, content, terms, prompt)
        if score <= 0 and terms:
            return
        seen_paths.add(normalized_path)
        matched_files.append({
            "path": normalized_path,
            "filename": normalized_path.rsplit("/", 1)[-1],
            "content": content,
            "matched_blocks": _matched_blocks_for_prompt(content, terms),
            "reason": f"{reason}; live branch {branch}",
            "score": score,
        })

    for path in _explicit_iac_paths_from_prompt(prompt):
        add_path(path, "exact path mentioned by user")

    # Scan the selected branch directly before default-branch code search.
    # This is what makes follow-up edits aware of Terrabot-generated files and
    # user commits that exist only on the current feature branch.
    context_root = _teams_context_root(cloud, workflow, repo_target, prompt, thread_id)
    try:
        branch_files = _teams_load_existing_iac_files_for_context(
            cloud,
            branch,
            context_root,
            repo_target,
            workflow,
        )
    except Exception as exc:
        LOGGER.warning("Unable to scan live Teams branch %s/%s: %s", branch, context_root, exc)
        branch_files = []
    branch_files.extend(
        _teams_previous_branch_files(
            thread_id,
            cloud,
            branch,
            repo_target,
            workflow,
        )
    )
    for item in branch_files:
        path = str(item.get("path") or item.get("filename") or "").strip()
        if not path or path in seen_paths:
            continue
        content = str(item.get("content") or "")
        score = _score_infra_candidate(path, content, terms, prompt)
        if score <= 0 and terms:
            continue
        seen_paths.add(path)
        matched_files.append({
            "path": path,
            "filename": path.rsplit("/", 1)[-1],
            "content": content,
            "matched_blocks": _matched_blocks_for_prompt(content, terms),
            "reason": str(item.get("reason") or f"direct live branch scan: {branch}"),
            "score": score,
        })

    queries: list[str] = []
    for term in terms[:8]:
        queries.append(f'repo:{repo_full_name} "{term}" extension:tf')
        queries.append(f'repo:{repo_full_name} "{term}" extension:tfvars')
    if not queries:
        queries.append(f"repo:{repo_full_name} extension:tf")

    for query in list(dict.fromkeys(queries))[:18]:
        try:
            items = github_search_code(query, per_page=25)
        except Exception as exc:
            LOGGER.warning("Existing infra GitHub search failed for %r: %s", query, exc)
            items = []
        for item in items or []:
            full_name = ((item or {}).get("repository") or {}).get("full_name") or ""
            if full_name and full_name.lower() != repo_full_name.lower():
                continue
            add_path((item or {}).get("path") or "", f"GitHub code search: {query}")

    matched_files.sort(key=lambda item: (-int(item.get("score") or 0), item.get("path") or ""))
    for item in matched_files:
        item.pop("score", None)

    return {
        "source": "backend_existing_infra_code_match",
        "selection_state": "candidate_selection_required",
        "cloud": cloud,
        "repo_target": repo_target,
        "workflow": workflow,
        "repo_full_name": repo_full_name,
        "context_ref": branch,
        "search_terms": terms,
        "matched_files": matched_files[:12],
        "matched_file_paths": [item.get("path") for item in matched_files[:12] if item.get("path")],
        "instructions": [
            "User must select exactly one existing Terraform target before generation.",
            "Use the latest live Teams feature branch as the source of truth.",
            "Do not call the agent with all candidate files for modification generation.",
        ],
    }




def _teams_context_file_identity(item: dict) -> str:
    """Return the canonical repo-relative identity for a context file."""
    return str((item or {}).get("path") or (item or {}).get("filename") or "").strip().strip("/")


def _teams_feature_flag_intent(prompt: str) -> str:
    """Return enable/disable only for explicit feature-state requests."""
    text = re.sub(r"\s+", " ", str(prompt or "").strip().lower())
    if re.search(r"\b(?:disable|turn off|switch off|deactivate|decommission|remove)\b", text):
        return "disable"
    if re.search(r"\b(?:enable|turn on|switch on|activate)\b", text):
        return "enable"
    return ""



def _teams_auto_select_feature_flag_context_stage1(existing_infra_context: dict, prompt: str) -> dict:
    """Select one unambiguous live Boolean feature flag for enable/disable.

    This is repository validation/targeting only: it never generates or mutates
    Terraform. The selected literal assignment is later enforced byte-for-byte
    by _validate_selected_boolean_is_only_file_change. For environment value
    files, normal hub requests prefer hub.tfvars; dr.tfvars is eligible only
    when the user explicitly requested DR/failover/secondary.
    """
    intent = _teams_feature_flag_intent(prompt)
    if intent not in {"enable", "disable"}:
        return {}
    context = dict(existing_infra_context or {})
    if not context:
        return {}

    text = str(prompt or "").lower().replace("_", "-")
    stop = {
        "enable", "disable", "turn", "switch", "on", "off", "remove",
        "decommission", "activate", "deactivate", "in", "for", "the",
        "a", "an", "application", "applications", "resource", "feature",
    }
    prompt_tokens = {
        token for token in re.findall(r"[a-z0-9]+", text)
        if len(token) > 2 and token not in stop
    }
    # Repository vocabulary commonly abbreviates application as app. Keep the
    # alias generic rather than hardcoding any product/resource name.
    if re.search(r"\bapplications?\b|\bapps?\b", text):
        prompt_tokens.add("app")

    target_current = "true" if intent == "disable" else "false"
    target_new = "false" if intent == "disable" else "true"
    candidates = []
    evidence = list(context.get("matched_files") or []) + list(context.get("environment_files") or [])
    seen = set()
    for item in evidence:
        if not isinstance(item, dict):
            continue
        path = _teams_context_file_identity(item)
        content = str(item.get("content") or "")
        if not path or not content or path in seen:
            continue
        seen.add(path)
        for line_no, line in enumerate(content.splitlines(), start=1):
            match = re.match(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(true|false)\s*(?:#.*)?$', line, re.IGNORECASE)
            if not match:
                continue
            flag = match.group(1)
            current = match.group(2).lower()
            if current != target_current:
                continue
            flag_tokens = {t for t in re.findall(r"[a-z0-9]+", flag.lower()) if len(t) > 1}
            overlap = prompt_tokens & flag_tokens
            if not overlap:
                continue
            # Require at least one resource-specific token beyond generic app
            # when possible. This makes "homepage application" resolve to the
            # homepage app flag while unrelated aca_app_* flags remain below it.
            specific_overlap = overlap - {"app", "enabled", "enable", "create", "deploy"}
            score = (len(specific_overlap) * 10) + len(overlap)
            if flag.lower().endswith("_enabled"):
                score += 2

            basename = path.rsplit("/", 1)[-1].lower()
            dr_requested = bool(re.search(
                r"(?<![a-z0-9])(?:dr|disaster recovery|failover|secondary)(?![a-z0-9])",
                text,
            ))
            if basename == "hub.tfvars":
                score += 8 if not dr_requested else -4
            elif basename == "dr.tfvars":
                score += 8 if dr_requested else -8
            elif basename == "tier.tfvars":
                score += 4
            elif basename == "common.tfvars":
                score += 2

            candidates.append({
                "score": score,
                "path": path,
                "item": item,
                "flag": flag,
                "current_value": current,
                "new_value": target_new,
                "line": line_no,
                "context": line.strip(),
            })

    if not candidates:
        return {}
    candidates.sort(key=lambda c: (-c["score"], c["path"], c["flag"]))
    best = candidates[0]
    # Never auto-select a tie: leave the normal evidence-backed clarification
    # path in place when two distinct Boolean controls are equally plausible.
    if len(candidates) > 1 and candidates[1]["score"] == best["score"]:
        return {}
    if best["score"] < 10:
        return {}

    selected_item = dict(best["item"] or {})
    selected_item["feature_flag_match"] = {
        "flag": best["flag"],
        "current_value": best["current_value"],
        "new_value": best["new_value"],
        "context": best["context"],
        "line": best["line"],
    }
    context["matched_files"] = [selected_item]
    context["matched_file_paths"] = [best["path"]]
    context["selected_path"] = best["path"]
    context["selection_state"] = "selected"
    context["feature_flag_selection"] = True
    context["agent_resolves_target"] = False
    context["instructions"] = list(context.get("instructions") or []) + [
        f"Backend live-evidence target: `{best['flag']} = {best['current_value']}` in `{best['path']}` line {best['line']}; requested transition is {best['current_value']} -> {best['new_value']}.",
        "Return the COMPLETE final file and change only the literal Boolean value on that assignment. Do not add, remove, rename, reorder, or reformat any other line.",
    ]
    return context
_teams_auto_select_feature_flag_context = _teams_auto_select_feature_flag_context_stage1

def _teams_repo_target_for_expected(cloud: str, workflow: str) -> str:
    return normalize_repo_target(cloud, workflow=workflow)


def _teams_branch_slug(value: str) -> str:
    value = re.sub(r"\[[A-Za-z]+\]", " ", str(value or ""))
    value = value.lower().replace("_", "-")
    value = re.sub(r"[^a-z0-9./-]+", "-", value)
    value = re.sub(r"-+", "-", value)
    value = re.sub(r"/+", "/", value).strip("-./")
    return value[:100]


def _teams_suggested_branch_name(agent_result: dict, prompt: str, thread_id: str) -> str:
    proposed = _teams_branch_slug(agent_result.get("branch_name") or "")
    if proposed.startswith("terrabot/"):
        proposed = proposed[len("terrabot/"):]
    elif proposed.startswith("terrabot-"):
        proposed = proposed[len("terrabot-"):]
    if not proposed:
        proposed = _teams_branch_slug(agent_result.get("title") or prompt) or "infrastructure-change"
    suffix = stable_thread_key(thread_id)[:8]
    return f"terrabot/{proposed[:72]}-{suffix}".rstrip("-/")


def _teams_unique_branch_name(
    cloud: Any | None,
    candidate: str,
    repo_target: Optional[str],
    workflow: Optional[str],
    start_cycle: int = 1,
) -> tuple[str, int]:
    cycle = max(1, int(start_cycle or 1))
    branch = candidate if cycle == 1 else f"{candidate}-v{cycle}"
    while github_branch_exists(cloud, branch, repo_target=repo_target, workflow=workflow):
        cycle += 1
        branch = f"{candidate}-v{cycle}"
    return branch, cycle


def _teams_load_existing_iac_files_for_context(
    cloud: str,
    branch_name: str,
    folder: str,
    repo_target: str,
    workflow: str,
    max_files: int = 120,
    max_bytes: int = 64 * 1024,
) -> list[dict]:
    """Read current remote branch IaC files with the same context budget as VS Code.

    Unlike GitHub code search, this follows the requested branch. It therefore
    includes files generated by Terrabot or edited by the user on an existing
    feature branch even when those files do not exist on the default branch.
    """
    existing: list[dict] = []
    root = (folder or ".").strip().strip("/") or "."
    root_prefix = "" if root == "." else root.rstrip("/") + "/"
    allowed_suffixes = (".tf", ".tfvars", ".hcl")
    visited: set[str] = set()

    def walk(current_path: str) -> None:
        if len(existing) >= max_files:
            return
        normalized = (current_path or ".").strip().strip("/") or "."
        if normalized in visited:
            return
        visited.add(normalized)
        for item in github_get_directory_listing(
            cloud,
            normalized,
            branch_name,
            repo_target=repo_target,
            workflow=workflow,
        ):
            if len(existing) >= max_files:
                return
            item_type = str((item or {}).get("type") or "")
            item_path = str((item or {}).get("path") or "").strip()
            if not item_path:
                continue
            if item_type == "dir":
                walk(item_path)
                continue
            if item_type != "file" or not item_path.endswith(allowed_suffixes):
                continue
            size = int((item or {}).get("size") or 0)
            if size and size > max_bytes:
                continue
            content = github_get_file_content(
                cloud,
                item_path,
                branch_name,
                repo_target=repo_target,
                workflow=workflow,
            )
            if content is None or len(content.encode("utf-8")) > max_bytes:
                continue
            relative_name = item_path[len(root_prefix):] if root_prefix and item_path.startswith(root_prefix) else item_path
            existing.append({
                "filename": relative_name,
                "path": item_path,
                "content": content,
                "source_ref": branch_name,
            })

    walk(root)
    return existing


def _teams_previous_branch_files(
    thread_id: str,
    cloud: str,
    branch_name: str,
    repo_target: str,
    workflow: str,
    max_files: int = 80,
    max_bytes: int = 64 * 1024,
) -> list[dict]:
    """Read every path already committed by this Teams workflow from the live branch."""
    if not thread_id or not branch_name:
        return []
    states = recover_thread_pr_state(thread_id) or {}
    bucket = state_bucket_for_target(cloud, repo_target, workflow)
    state = states.get(bucket) or {}
    result: list[dict] = []
    seen: set[str] = set()
    for value in state.get("files") or []:
        path = str(value or "").strip().strip("/")
        if not path or path in seen or not path.endswith((".tf", ".tfvars", ".hcl")):
            continue
        seen.add(path)
        try:
            content = github_get_file_content(
                cloud,
                path,
                branch_name,
                repo_target=repo_target,
                workflow=workflow,
            )
        except Exception as exc:
            LOGGER.warning("Unable to read prior Teams branch file %s@%s: %s", path, branch_name, exc)
            continue
        if content is None or len(content.encode("utf-8")) > max_bytes:
            continue
        result.append({
            "filename": path,
            "path": path,
            "content": content,
            "source_ref": branch_name,
            "reason": "previous Terrabot/user branch file",
        })
        if len(result) >= max_files:
            break
    return result


def _teams_context_root(
    cloud: str,
    workflow: str,
    repo_target: str,
    prompt: str,
    thread_id: str,
) -> str:
    states = recover_thread_pr_state(thread_id) if thread_id else {}
    bucket = state_bucket_for_target(cloud, repo_target, workflow)
    state = states.get(bucket) or {}
    if cloud == "aws":
        current_path = state.get("environment_path") or ""
        environment_path, _ = resolve_aws_environment_path(
            prompt,
            retrieved_value_context=[],
            current_environment_path=current_path or None,
        )
        return environment_path or current_path or "terraform/dev_aws/minidev"
    return state.get("folder") or cloud_root_dir(cloud, repo_target, workflow) or "."


def _build_agent_input_for_infra_teams_v1(
    prompt: str,
    thread_id: str,
    selected_cloud: Optional[str] = None,
    workflow: Optional[str] = None,
    retrieved_module_context: Optional[list] = None,
    retrieved_value_context: Optional[list] = None,
) -> str:
    """Append a Teams-only remote-repository envelope without changing VS Code."""
    original = _ORIGINAL_BUILD_AGENT_INPUT_FOR_INFRA(
        prompt,
        thread_id,
        selected_cloud=selected_cloud,
        workflow=workflow,
        retrieved_module_context=retrieved_module_context,
        retrieved_value_context=retrieved_value_context,
    )
    context = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    if not context.get("active"):
        return original

    try:
        payload = json.loads(original)
    except Exception:
        return original

    expected_cloud = safe_normalize_cloud(selected_cloud) or safe_normalize_cloud(context.get("expected_cloud"))
    expected_workflow = str(workflow or context.get("expected_workflow") or "").strip()
    if not expected_workflow and expected_cloud == "aws":
        expected_workflow = "aws_module_consumer"
    if not expected_workflow and expected_cloud == "azure":
        expected_workflow = "azure_consumer_generation"
    expected_repo_target = (
        _teams_repo_target_for_expected(expected_cloud, expected_workflow)
        if expected_cloud else ""
    )

    # Mutate the active context so parsing/repair and branch creation see the
    # exact backend-owned context used for this generation turn.
    context.update({
        "expected_cloud": expected_cloud or "",
        "expected_workflow": expected_workflow,
        "expected_repo_target": expected_repo_target,
        "retrieved_module_context": list(retrieved_module_context or []),
        "retrieved_value_context": list(retrieved_value_context or []),
        "effective_prompt": prompt,
        "thread_id": thread_id,
    })

    context_branch = ""
    context_root = ""
    if expected_cloud:
        context_branch = _teams_remote_context_branch(
            expected_cloud,
            expected_repo_target,
            expected_workflow,
        )
        context_root = _teams_context_root(
            expected_cloud,
            expected_workflow,
            expected_repo_target,
            prompt,
            thread_id,
        )
        try:
            existing_files = _teams_load_existing_iac_files_for_context(
                expected_cloud,
                context_branch,
                context_root,
                expected_repo_target,
                expected_workflow,
            )
            prior_files = _teams_previous_branch_files(
                thread_id,
                expected_cloud,
                context_branch,
                expected_repo_target,
                expected_workflow,
            )
            seen_context_paths = {
                str(item.get("path") or item.get("filename") or "")
                for item in existing_files
                if isinstance(item, dict)
            }
            for item in prior_files:
                item_path = str(item.get("path") or item.get("filename") or "")
                if item_path and item_path not in seen_context_paths:
                    existing_files.append(item)
                    seen_context_paths.add(item_path)
        except Exception as exc:
            LOGGER.warning(
                "Unable to load Teams live GitHub context %s@%s: %s",
                context_root,
                context_branch,
                exc,
            )
            existing_files = []

        remote_context = {
            "cloud": expected_cloud,
            "repo_target": expected_repo_target,
            "branch": context_branch,
            "source_branch_for_context": context_branch,
            "base_branch": github_resolve_base_branch_for_cloud(
                expected_cloud,
                repo_target=expected_repo_target,
                workflow=expected_workflow,
            ),
            "folder": context_root,
            "update_mode": (
                "modify_existing_in_same_branch"
                if _teams_truthy(context.get("reuse_branch"))
                else "generate_from_latest_remote_base"
            ),
            "existing_files": existing_files,
            "source": "live_github_teams_remote_workspace",
        }
        payload["existing_pr_context"] = [remote_context]
        context["context_branch"] = context_branch
        context["context_root"] = context_root

    payload["channel"] = "teams"
    payload["source"] = "teams"
    payload["teams_remote_repository_mode"] = True
    payload["teams_branch_context"] = {
        "reuse_existing_branch": _teams_truthy(context.get("reuse_branch")),
        "force_new_branch_from_latest_base": _teams_truthy(context.get("force_new_branch")),
        "existing_branch": str(context.get("existing_branch") or ""),
        "context_branch": context_branch,
        "context_root": context_root,
    }
    payload["required_output"] = {
        "mode": "infra",
        "cloud": expected_cloud or "aws | azure",
        "workflow": expected_workflow,
        "repo_target": expected_repo_target,
        "title": "short infrastructure change title",
        "branch_name": "terrabot/<short-change-slug>",
        "summary": "human-readable summary",
        "analysis": "brief repository-grounded decision log",
        "source_paths_used": ["real paths from live GitHub context"],
        "files": [{"filename": "repo-relative/path.tf", "content": "FULL final content"}],
        "user_fillable": [{"token": "__FILL__name__", "input": "name", "file": "path.tf", "hint": "expected value and example"}],
        "questions": [],
        "validation_commands": ["terraform fmt -check -recursive", "terraform validate"],
    }

    instructions = [
        instruction
        for instruction in list(payload.get("instructions") or [])
        if not any(
            marker in str(instruction)
            for marker in (
                "For bool variables, use default = false",
                "For number variables, use default = -1",
                "For map variables, use default = {}; for list/set variables",
                "For string variables, include default only when the value was explicitly provided",
                "otherwise ask for the string value/reference before returning JSON",
            )
        )
    ]
    instructions.extend([
        "TEAMS CHANNEL OVERRIDE: apply every repository inference, safety, modification, feature-flag, default-value ladder, and __FILL__ rule from the VS Code Terrabot instructions.",
        "The only platform difference is repository context: use backend-provided live GitHub files from the selected remote branch instead of a local VS Code workspace.",
        "Return the Teams backend JSON shape in required_output. Include mode, cloud, workflow, repo_target, title, branch_name, summary, analysis, files, user_fillable, questions, and validation_commands.",
        "For a confirmed AWS module selection, use exactly the selected module_source and module inputs from retrieved_module_context. Do not restart module discovery and do not return an empty files array.",
        "AWS TF-DEVOPS CONSUMER TARGET (HARD): read the complete backend-supplied target-environment Terraform files before generating. If <environment>/main.tf exists and existing module consumers are consolidated there, main.tf is the authoritative consumer target. Return the FULL existing main.tf plus exactly one new sibling module block matching its consumer style. Never ask how to encode the resource and never choose variables.tf or backend.tf as a substitute consumer target.",
        "If main.tf is absent, infer the target from the existing environment file that actually contains sibling module invocations. Repository placement is a backend/evidence decision, not a user question.",
        "Infer explicit non-sensitive values from the user prompt and apply them directly.",
        "For missing non-sensitive preferences, follow the VS Code default-value inference ladder. If no grounded value exists, generate a syntactically valid __FILL__<input_name>__ placeholder and add a matching user_fillable entry instead of blocking generation.",
        "Use existing live GitHub consumers and module defaults as examples before creating any placeholder.",
        "A follow-up modification must edit the latest file content from teams_branch_context.context_branch. Do not regenerate unrelated Terraform and do not drop user-authored branch changes.",
        "When reuse_existing_branch is true, generate against that branch. When force_new_branch_from_latest_base is true, generate against the latest remote base branch and do not inherit prior branch-only changes.",
        "Always propose branch_name beginning with terrabot/. The backend validates and uniquifies it before creating the GitHub branch.",
        "Do not return files=[] merely because user-preference values are missing. files=[] is allowed only for a truly structural, sensitive-reference, ambiguous-target, or policy blocker.",
        "Before asking any repository-structure question, scan the selected live GitHub repository scope for existing consumers, module sources, variable declarations, tfvars, sibling environment examples, and naming conventions. Ask only for a genuinely external value that cannot exist in repository evidence.",
        "Interpret natural-language resource phrases semantically. Product names and descriptive wording such as 'ACA app whose name is homepage-bff' identify the requested resource type and instance name; do not search for the literal phrase as a module name.",
        "For creation requests, derive the target file and block shape from the closest existing resource of the same type in the target environment or sibling environments. Reuse its module source, inputs, file placement, and formatting, changing only values required by the request.",
        "Do not emit conversational fallback text such as 'I need more context', 'which file', 'which module', or 'what environment' until live GitHub discovery has completed and the missing item is proven external to the repository.",
        "AZURE OBJECT-BACKED CREATION AUTHORIZATION (HARD): when live tf-azure-hub evidence demonstrates the module-block + dedicated object variable + environment tfvars pattern, editing variables.tf is explicitly authorized and required. Never ask the user to relax a variables.tf restriction or confirm permission to add a dedicated object-root variable.",
        "For such a creation, return the complete three-file set in the same response: (1) the existing resource-family definition file with only the new sibling invocation appended and wired to a new dedicated var.<root>.*, (2) the existing variables.tf with a new variable <root> declaration cloned from the nearest sibling type shape, and (3) the resolved target environment values file with a new <root> object assignment cloned from the nearest sibling concrete values. Never defer any of these files to another turn.",
        "If the requested resource name is new and the repository provides a clear nearest sibling, make all three decisions yourself. Do not return questions asking whether to use object-backed vs non-object-backed structure, whether variables.tf may be edited, which sibling to clone, or which target environment tfvars file to use.",
    ])
    selected_generation_context = next((
        item for item in retrieved_value_context or []
        if isinstance(item, dict)
        and item.get("source") == "backend_aws_selected_module_generation_context"
    ), {})
    if expected_cloud == "aws" and expected_workflow == "aws_module_consumer" and selected_generation_context:
        selected_target = str(selected_generation_context.get("target_file") or "").strip()
        selected_module = _get_confirmed_aws_module_selection(retrieved_value_context or [])
        selected_source = str(selected_module.get("module_source") or selected_generation_context.get("module_source") or "").strip()
        instructions.extend([
            "AWS MODULE OPTION HAS BEEN SELECTED (HARD): this is the generation turn, not another discovery/clarification turn.",
            "Read every .tf file supplied in the selected retrieved_module_context.module_files/all_tf_file_contents before generating the consumer.",
            f"Return exactly one changed file: {selected_target}.",
            f"Preserve the complete existing {selected_target} content byte-for-byte as the prefix and append exactly one new sibling module invocation.",
            f"The appended module block must use the exact selected source {selected_source}.",
            "Do not return another module picker, target picker, branch picker, repository-placement question, or files=[].",
        ])
    payload["instructions"] = instructions
    return json.dumps(payload, indent=2)


def _teams_coerce_agent_payload_stage1(agent_text: str, context: dict) -> tuple[dict, dict]:
    payload = extract_json_from_text(agent_text)
    if not isinstance(payload, dict):
        raise ValueError("Teams agent response was not a JSON object.")

    expected_cloud = safe_normalize_cloud(payload.get("cloud")) or safe_normalize_cloud(context.get("expected_cloud"))
    if not expected_cloud:
        raise ValueError("Teams generation could not resolve cloud='aws' or cloud='azure'.")
    expected_workflow = str(payload.get("workflow") or context.get("expected_workflow") or "").strip()
    expected_repo_target = str(payload.get("repo_target") or context.get("expected_repo_target") or "").strip()
    if not expected_repo_target:
        expected_repo_target = normalize_repo_target(expected_cloud, workflow=expected_workflow)

    payload["mode"] = "infra"
    payload["cloud"] = expected_cloud
    payload["workflow"] = expected_workflow
    payload["repo_target"] = expected_repo_target
    payload.setdefault("title", generate_short_ticket_title(context.get("effective_prompt") or payload.get("summary") or "Terrabot infrastructure change"))
    payload.setdefault("summary", "Terraform infrastructure changes generated from live GitHub repository context.")
    payload.setdefault("branch_name", _teams_suggested_branch_name(payload, context.get("effective_prompt") or "", context.get("thread_id") or "teams"))

    normalized_files: list[dict] = []
    for item in payload.get("files") or []:
        if not isinstance(item, dict):
            continue
        filename = str(item.get("filename") or item.get("path") or "").strip()
        content = item.get("content")
        operation = str(item.get("operation") or "").strip().lower()
        if not filename or not isinstance(content, str) or not content.strip():
            # Teams remote branch writes require complete materialized files.
            # A repair turn converts VS Code fill/insert operations into full
            # branch-aware file content before commit.
            if operation in {"fill", "insert_into_block"}:
                continue
            continue
        normalized_files.append({"filename": filename, "content": content})
    payload["files"] = normalized_files

    # A user-confirmed AWS module selection has one deterministic write target:
    # the target environment main.tf captured live at selection time. Validate
    # the Foundry result here so a bad response is routed through the existing
    # internal repair/fallback path instead of reopening selection or committing
    # unrelated files.
    selected_generation = next((
        item for item in context.get("retrieved_value_context") or []
        if isinstance(item, dict)
        and item.get("source") == "backend_aws_selected_module_generation_context"
    ), {})
    if (
        expected_cloud == "aws"
        and expected_workflow == "aws_module_consumer"
        and selected_generation
        and normalized_files
    ):
        target_file = str(selected_generation.get("target_file") or selected_generation.get("path") or "").strip()
        existing_content = str(selected_generation.get("content") or "")
        selected_source = str(selected_generation.get("module_source") or "").strip()
        paths = [str(item.get("filename") or "").strip() for item in normalized_files]
        if len(normalized_files) != 1 or paths != [target_file]:
            raise ValueError(
                "AWS_SELECTED_MODULE_TARGET_MISMATCH: selected-module generation must return exactly "
                f"the target consumer file {target_file}; got {paths}."
            )
        generated_content = str(normalized_files[0].get("content") or "")
        existing_prefix = existing_content.rstrip("\n")
        if existing_prefix and not generated_content.startswith(existing_prefix):
            raise ValueError(
                "AWS_SELECTED_MODULE_NOT_APPEND_ONLY: generated main.tf did not preserve the complete "
                "live target file as an unchanged prefix."
            )
        delta = generated_content[len(existing_prefix):] if existing_prefix else generated_content
        if selected_source and selected_source not in delta:
            raise ValueError(
                "AWS_SELECTED_MODULE_SOURCE_MISSING: generated consumer delta does not invoke the exact "
                f"selected module source {selected_source}."
            )
        if not re.search(r'(?m)^\s*module\s+"[^"]+"\s*\{', delta):
            raise ValueError(
                "AWS_SELECTED_MODULE_CONSUMER_MISSING: generated append-only delta contains no Terraform module block."
            )

    if not normalized_files:
        questions = payload.get("questions") or []
        detail = "; ".join(str(item) for item in questions[:6]) if isinstance(questions, list) else ""
        raise ValueError(
            "Teams agent returned no Terraform files after module/environment selection. "
            + (f"Agent questions: {detail}" if detail else "A repair generation is required.")
        )
    return payload, dict(payload)
_teams_coerce_agent_payload = _teams_coerce_agent_payload_stage1


def try_parse_agent_output(agent_text: str):
    context = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    if not context.get("active"):
        return _ORIGINAL_TRY_PARSE_AGENT_OUTPUT(agent_text)

    payload, metadata = _teams_coerce_agent_payload(agent_text, context)
    parsed = parse_agent_output(json.dumps(payload))
    for key in (
        "analysis",
        "source_paths_used",
        "user_fillable",
        "questions",
        "validation_commands",
        "branch_name",
    ):
        if metadata.get(key) not in (None, ""):
            parsed[key] = metadata.get(key)
    return parsed


def _teams_module_example_assignments(module_context: dict) -> dict[str, str]:
    values: dict[str, str] = {}
    for example in module_context.get("consumer_examples") or []:
        for block in (example or {}).get("module_blocks") or []:
            for name, expression in re.findall(
                r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^\n#]+?)\s*$",
                block or "",
            ):
                if name != "source" and name not in values:
                    values[name] = expression.strip()
    return values


def _teams_placeholder_expression(name: str, type_expr: str) -> tuple[str, str]:
    token = f"__FILL__{name}__"
    normalized = _normalize_type_expr(type_expr)
    if normalized == "bool":
        return f'try(tobool("{token}"), false)', token
    if normalized == "number":
        return f'try(tonumber("{token}"), -1)', token
    if normalized.startswith("list(") or normalized.startswith("set(") or normalized in {"list", "set"}:
        return f'try(tolist(jsondecode("{token}")), [])', token
    if normalized.startswith("map(") or normalized == "map":
        return f'try(tomap(jsondecode("{token}")), {{}})', token
    if normalized.startswith("object("):
        return f'try(jsondecode("{token}"), null)', token
    return json.dumps(token), token


def _teams_select_aws_environment_consumer_file_stage1(
    environment_path: str,
    branch: str,
) -> tuple[str, str]:
    """Select the live tf-devops environment consumer file deterministically.

    Prefer an existing main.tf because tf-devops commonly consolidates module
    invocations there.  If main.tf is absent, select the .tf file with the
    strongest existing module-consumer evidence; infrastructure plumbing files
    such as backend.tf/versions.tf/providers.tf are never chosen as creation
    targets merely because they exist.
    """
    env = str(environment_path or "").strip().strip("/")
    if not env:
        raise ValueError("AWS environment path is required for consumer generation.")

    try:
        items = github_get_directory_listing(
            "aws",
            env,
            branch,
            repo_target="tf-devops",
            workflow="aws_module_consumer",
        ) or []
    except Exception as exc:
        raise ValueError(f"Could not read live tf-devops environment {env}@{branch}: {exc}") from exc

    candidates: list[tuple[int, str, str]] = []
    excluded = {"backend.tf", "versions.tf", "providers.tf", "provider.tf", "outputs.tf", "variables.tf", "vars.tf"}
    for item in items:
        if not isinstance(item, dict) or item.get("type") != "file":
            continue
        path = str(item.get("path") or "").strip()
        name = path.rsplit("/", 1)[-1].lower()
        if not path.endswith(".tf"):
            continue
        try:
            content = github_get_file_content(
                "aws",
                path,
                branch,
                repo_target="tf-devops",
                workflow="aws_module_consumer",
            ) or ""
        except Exception:
            content = ""
        if not content:
            continue
        module_count = len(re.findall(r'(?m)^\s*module\s+"[^"]+"\s*\{', content))
        if name == "main.tf":
            score = 10000 + module_count
        elif name in excluded:
            score = -1000 + module_count
        else:
            score = (module_count * 100) + 10
        candidates.append((score, path, content))

    usable = [item for item in candidates if item[0] >= 0]
    if not usable:
        raise ValueError(
            f"No existing AWS consumer .tf file was found in {env}. "
            "The backend cannot safely choose backend.tf/variables.tf as a resource consumer target."
        )
    usable.sort(key=lambda item: (-item[0], item[1]))
    _score, path, content = usable[0]
    return path, content
_teams_select_aws_environment_consumer_file = _teams_select_aws_environment_consumer_file_stage1


def _teams_build_deterministic_aws_consumer_payload(context: dict) -> dict:
    """Disabled: Terraform semantic generation belongs exclusively to Foundry."""
    raise RuntimeError("Backend Terraform synthesis/materialization is disabled; retry through Foundry with live repository evidence.")


def repair_and_parse_agent_output(
    conversation_id: str,
    original_agent_input: str,
    bad_agent_reply: str,
    parse_error: Exception,
):
    context = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    if not context.get("active"):
        return _ORIGINAL_REPAIR_AND_PARSE_AGENT_OUTPUT(
            conversation_id,
            original_agent_input,
            bad_agent_reply,
            parse_error,
        )

    repair_payload = {
        "task": "Repair the current Teams Terraform generation and return executable files now.",
        "channel": "teams",
        "original_user_request": context.get("effective_prompt") or "",
        "expected_cloud": context.get("expected_cloud") or "",
        "expected_workflow": context.get("expected_workflow") or "",
        "expected_repo_target": context.get("expected_repo_target") or "",
        "backend_validation_error": str(parse_error),
        "previous_agent_reply": bad_agent_reply,
        "retrieved_module_context": context.get("retrieved_module_context") or [],
        "retrieved_value_context": context.get("retrieved_value_context") or [],
        "live_branch_context": {
            "branch": context.get("context_branch") or "",
            "folder": context.get("context_root") or "",
            "reuse_branch": _teams_truthy(context.get("reuse_branch")),
            "force_new_branch": _teams_truthy(context.get("force_new_branch")),
        },
        "required_output": {
            "mode": "infra",
            "cloud": context.get("expected_cloud") or "aws | azure",
            "workflow": context.get("expected_workflow") or "",
            "repo_target": context.get("expected_repo_target") or "",
            "title": "short title",
            "branch_name": "terrabot/<short-change-slug>",
            "summary": "short summary",
            "analysis": "3-10 grounded lines",
            "source_paths_used": [],
            "files": [{"filename": "repo-relative/path.tf", "content": "FULL final file"}],
            "user_fillable": [],
            "questions": [],
            "validation_commands": [],
        },
        "absolute_rules": [
            "Return one valid JSON object only.",
            "Do not return files=[] for missing non-sensitive preference values.",
            "Use the confirmed module/environment/target already present in backend context; do not restart discovery.",
            "Use explicit prompt values, then live GitHub examples/defaults, then __FILL__<input_name>__ placeholders with matching user_fillable entries.",
            "For modification requests, use the latest full file content from the live branch and alter only the requested code.",
            "For AWS module selection, use exactly the selected local module_source and required inputs.",
            "Every file must contain complete materialized content suitable for a GitHub commit.",
            "branch_name must begin with terrabot/.",
        ],
    }

    max_internal_repairs = 3
    working_payload = dict(repair_payload)
    last_repair_error: Exception | None = None

    _teams_diag_log(
        "generation_parse_repair_start",
        thread=conversation_id,
        internal_repairs=max_internal_repairs,
        original_error=str(parse_error)[:300],
    )

    for internal_attempt in range(1, max_internal_repairs + 1):
        _teams_diag_log(
            "generation_parse_repair_agent_call_start",
            thread=conversation_id,
            attempt=f"{internal_attempt}/{max_internal_repairs}",
        )
        _conversation_id, repaired_reply = call_agent(
            conversation_id,
            json.dumps(working_payload, indent=2),
        )
        _teams_diag_log(
            "generation_parse_repair_agent_call_complete",
            thread=conversation_id,
            attempt=f"{internal_attempt}/{max_internal_repairs}",
            reply_chars=len(str(repaired_reply or "")),
        )
        try:
            parsed = try_parse_agent_output(repaired_reply)
            _teams_diag_log(
                "generation_parse_repair_success",
                thread=conversation_id,
                attempt=f"{internal_attempt}/{max_internal_repairs}",
                files=len(parsed.get("files") or []),
            )
            return parsed, repaired_reply
        except Exception as repair_error:
            last_repair_error = repair_error
            _teams_diag_log(
                "generation_parse_repair_failed",
                level="warning",
                thread=conversation_id,
                attempt=f"{internal_attempt}/{max_internal_repairs}",
                error=str(repair_error)[:300],
            )
            if internal_attempt >= max_internal_repairs:
                break
            working_payload = dict(working_payload)
            working_payload["prior_repair_feedback"] = str(repair_error)
            working_payload["repair_attempt"] = internal_attempt + 1
            working_payload["repair_response_violation"] = (
                "The previous internal repair response was still not valid executable "
                "Terraform JSON. Correct that response now. Return one strict JSON object "
                "with non-empty complete files[] and no blocking questions."
            )

    # No deterministic Terraform fallback is permitted. Exhaust all three
    # private Foundry repair opportunities before this error can reach Teams.
    raise ValueError(
        "Teams Foundry generation did not return valid Terraform files after "
        f"{max_internal_repairs} internal repair attempts. "
        f"Original error: {parse_error}. Last repair error: {last_repair_error}"
    )


def _commit_terraform_files_to_branch_for_teams_v1(
    agent_result: dict,
    prompt: str,
    thread_id: str,
) -> dict:
    """Commit to the explicitly selected Teams branch strategy.

    - reuse_branch=True writes against the latest remote content of the active
      Terrabot branch, including user-pushed edits.
    - force_new_branch=True creates a clean branch from the latest remote base.
    - new branch names always begin with ``terrabot/``.
    """
    context = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    cloud = normalize_cloud(agent_result["cloud"])
    workflow = agent_result.get("workflow")
    repo_target = normalize_repo_target(
        cloud,
        repo_target=agent_result.get("repo_target"),
        workflow=workflow,
    )
    if workflow == "azure_module_repo_population":
        raise ValueError("Teams branch-first flow currently targets tf-devops and tf-azure-hub repositories.")

    validate_azure_consumer_two_file_payload_for_commit(agent_result)
    state = get_or_create_thread_pr_state(
        thread_id,
        cloud,
        repo_target=repo_target,
        workflow=workflow,
        prompt=prompt,
    )
    folder = state["folder"]
    base_branch = github_resolve_base_branch_for_cloud(
        cloud,
        repo_target=repo_target,
        workflow=workflow,
    )

    reuse_branch = _teams_truthy(context.get("reuse_branch"))
    force_new_branch = _teams_truthy(context.get("force_new_branch"))
    requested_existing_branch = str(context.get("existing_branch") or state.get("branch") or "").strip()
    branch_name = ""
    branch_reused = False
    created_new_branch = False

    if reuse_branch and requested_existing_branch and github_branch_exists(
        cloud,
        requested_existing_branch,
        repo_target=repo_target,
        workflow=workflow,
    ):
        branch_name = requested_existing_branch
        branch_reused = True
    else:
        base_candidate = _teams_suggested_branch_name(agent_result, prompt, thread_id)
        start_cycle = int(state.get("cycle") or 0) + 1 if state.get("branch") else 1
        branch_name, cycle = _teams_unique_branch_name(
            cloud,
            base_candidate,
            repo_target,
            workflow,
            start_cycle=start_cycle if (force_new_branch or state.get("branch")) else 1,
        )
        base_sha = github_get_base_branch_sha(
            cloud,
            base_branch,
            repo_target=repo_target,
            workflow=workflow,
        )
        github_create_branch(
            cloud,
            branch_name,
            base_sha,
            repo_target=repo_target,
            workflow=workflow,
        )
        state["cycle"] = cycle
        state.pop("pr_number", None)
        state.pop("pr_url", None)
        state["has_open_pr"] = False
        created_new_branch = True

    state["branch"] = branch_name

    if cloud == "aws":
        current_environment_path = state.get("environment_path") if reuse_branch else None
        aws_env_path, aws_env_error = resolve_aws_environment_path(
            prompt=prompt,
            retrieved_value_context=context.get("retrieved_value_context") or [],
            current_environment_path=current_environment_path,
        )
        if aws_env_error:
            raise ValueError(aws_env_error)
        if aws_env_path:
            state["environment_path"] = aws_env_path

    committed_files: list[str] = []
    for file_data in agent_result.get("files") or []:
        relative_path = normalize_agent_relative_tf_path(file_data["filename"], cloud)
        if relative_path.startswith("terraform/"):
            repo_path = relative_path
        elif cloud == "aws" and state.get("environment_path"):
            repo_path = safe_join_under_folder(state["environment_path"], relative_path)
        else:
            repo_path = safe_join_under_folder(folder, relative_path)

        write_result = github_put_file_if_changed(
            cloud=cloud,
            path=repo_path,
            content=file_data["content"],
            branch=branch_name,
            commit_message=f"[{cloud.upper()}] Terrabot update {repo_path}",
            repo_target=repo_target,
            workflow=workflow,
        )
        if write_result["changed"]:
            committed_files.append(repo_path)
        if cloud == "aws" and repo_path.startswith("terraform/") and not repo_path.startswith(f"{AWS_MODULES_ROOT}/"):
            state["environment_path"] = repo_path.rsplit("/", 1)[0]

    repo = github_repo_for_cloud(cloud, repo_target=repo_target, workflow=workflow)
    branch_url = f"https://github.com/{GITHUB_OWNER}/{repo}/tree/{branch_name}"
    compare_url = f"https://github.com/{GITHUB_OWNER}/{repo}/compare/{base_branch}...{branch_name}"
    branch_history = list(state.get("branch_history") or [])
    if branch_name not in branch_history:
        branch_history.append(branch_name)

    state.update({
        "workflow": workflow,
        "repo_target": repo_target,
        "base_branch": base_branch,
        "original_prompt": prompt,
        "title": agent_result.get("title") or f"[{cloud.upper()}] Terraform changes",
        "summary": agent_result.get("summary") or "Terraform infrastructure changes",
        "analysis": agent_result.get("analysis") or "",
        "files": list(dict.fromkeys(list(state.get("files") or []) + committed_files)) if branch_reused else committed_files,
        "branch_url": branch_url,
        "compare_url": compare_url,
        "branch_history": branch_history[-20:],
        "has_open_pr": bool(state.get("has_open_pr")) if branch_reused else False,
    })
    set_last_selected_cloud(thread_id, cloud)
    return {
        "cloud": cloud,
        "repo": repo,
        "repo_target": repo_target,
        "workflow": workflow,
        "folder": state.get("environment_path") if cloud == "aws" and state.get("environment_path") else folder,
        "branch": branch_name,
        "base_branch": base_branch,
        "branch_url": branch_url,
        "compare_url": compare_url,
        "files": committed_files,
        "title": state["title"],
        "summary": state["summary"],
        "analysis": state.get("analysis") or "",
        "user_fillable": agent_result.get("user_fillable") or [],
        "state": state,
        "branch_reused": branch_reused,
        "created_new_branch": created_new_branch,
        "message": (
            "Terraform changes were committed to the existing Terrabot GitHub branch."
            if branch_reused else
            "Terraform changes were committed to a new Terrabot GitHub branch."
        ),
    }



def _github_pull_request_template_for_teams(
    owner: Optional[str],
    repo: Optional[str],
    base: str,
    headers: dict,
) -> str:
    """Read the repository PR template using the same locations as VS Code.

    The existing fixed-path backend lookup is retained. Teams additionally
    supports the standard `.github/PULL_REQUEST_TEMPLATE/*.md` directory used
    by the VS Code extension, selecting the first markdown template in stable
    filename order.
    """
    owner = _require_setting(owner, "GITHUB_OWNER")
    repo = _require_setting(repo, "GitHub repository")
    template = _github_pull_request_template(owner, repo, base, headers)
    if template:
        return template

    folder_response = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/contents/.github/PULL_REQUEST_TEMPLATE",
        headers=headers,
        params={"ref": base},
        timeout=30,
    )
    if folder_response.status_code == 404:
        return ""
    if not folder_response.ok:
        raise _github_request_error(
            folder_response,
            "Reading the pull request template directory",
        )

    entries = folder_response.json() or []
    if not isinstance(entries, list):
        return ""

    markdown_templates = sorted(
        (
            item
            for item in entries
            if isinstance(item, dict)
            and item.get("type") == "file"
            and str(item.get("name") or "").lower().endswith(".md")
        ),
        key=lambda item: str(item.get("name") or "").lower(),
    )

    for item in markdown_templates:
        item_url = str(item.get("url") or "").strip()
        item_path = str(item.get("path") or "").strip()
        if not item_url and item_path:
            item_url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{item_path}"
        if not item_url:
            continue

        response = requests.get(
            item_url,
            headers=headers,
            params={"ref": base},
            timeout=30,
        )
        if response.status_code == 404:
            continue
        if not response.ok:
            raise _github_request_error(response, "Reading the pull request template")

        payload = response.json() or {}
        encoded = str(payload.get("content") or "").replace("\n", "")
        if not encoded:
            continue
        try:
            content = base64.b64decode(encoded).decode("utf-8").strip()
        except (ValueError, UnicodeDecodeError) as exc:
            raise RuntimeError(
                f"Reading the pull request template failed: {exc}"
            ) from exc
        if content:
            return content

    return ""


def _teams_pr_body_with_jira_and_attribution(
    body: str,
    ticket_link: str = "",
    ticket_number: str = "",
    teams_requester: str = "",
) -> str:
    """Insert Teams-required Jira and attribution without discarding template structure."""
    body = str(body or "").strip()
    jira_reference = str(ticket_link or ticket_number or "").strip()

    if not body:
        body = "## Description\n\nTerrabot infrastructure changes."

    if jira_reference and jira_reference not in body:
        headings = list(re.finditer(r"(?m)^#{1,6}\s+.+$", body))
        target_index = None
        for index, match in enumerate(headings):
            heading_text = re.sub(
                r"^#{1,6}\s+",
                "",
                match.group(0),
            ).strip().lower()
            if any(
                token in heading_text
                for token in ("jira", "ticket", "issue", "reference")
            ):
                target_index = index
                break

        if target_index is None:
            body = f"{body}\n\n## Jira Ticket\n\n{jira_reference}"
        else:
            heading = headings[target_index]
            section_end = (
                headings[target_index + 1].start()
                if target_index + 1 < len(headings)
                else len(body)
            )
            existing_section = body[heading.end():section_end].strip()
            existing_section = re.sub(
                r"<!--.*?-->",
                "",
                existing_section,
                flags=re.DOTALL,
            ).strip()
            if existing_section.lower() in {
                "not applicable",
                "not applicable.",
                "n/a",
                "none",
            }:
                existing_section = ""

            replacement = jira_reference
            if existing_section:
                replacement = f"{jira_reference}\n\n{existing_section}"

            body = (
                body[:heading.end()].rstrip()
                + "\n\n"
                + replacement
                + "\n\n"
                + body[section_end:].lstrip()
            ).strip()

    requester = str(teams_requester or "").strip()
    if requester:
        requester_section = f"## PR raised by\n\n{requester}"

        # Remove an older requester section before reinserting it so refreshing
        # an existing PR updates the Teams username instead of duplicating it.
        requester_heading = re.search(r"(?mi)^#{1,6}\s+PR raised by\s*$", body)
        if requester_heading:
            following_heading = re.search(
                r"(?m)^#{1,6}\s+.+$",
                body[requester_heading.end():],
            )
            requester_end = (
                requester_heading.end() + following_heading.start()
                if following_heading
                else len(body)
            )
            body = (body[:requester_heading.start()].rstrip() + "\n\n" + body[requester_end:].lstrip()).strip()

        # Place the attribution immediately after the Jira/ticket section when
        # the repository template contains one. Otherwise append it after the
        # Jira section that Terrabot added above.
        headings = list(re.finditer(r"(?m)^#{1,6}\s+.+$", body))
        jira_heading_index = None
        for index, heading in enumerate(headings):
            heading_text = re.sub(r"^#{1,6}\s+", "", heading.group(0)).strip().lower()
            if any(token in heading_text for token in ("jira", "ticket", "issue", "reference")):
                jira_heading_index = index
                break

        if jira_heading_index is None:
            body = f"{body}\n\n{requester_section}"
        else:
            insert_at = (
                headings[jira_heading_index + 1].start()
                if jira_heading_index + 1 < len(headings)
                else len(body)
            )
            body = (
                body[:insert_at].rstrip()
                + "\n\n"
                + requester_section
                + "\n\n"
                + body[insert_at:].lstrip()
            ).strip()

    attribution = "PR raised using Terrabot AI."
    if attribution not in body:
        body = f"{body}\n\n{attribution}"

    return body.strip()


def create_teams_pull_request_from_branch(
    agent_result: dict,
    prompt: str,
    thread_id: str,
    jira_ticket: str,
    ticket_link: str,
    ticket_title: str = "",
) -> dict:
    """Create or refresh a Teams PR from the repository template and branch diff."""
    if ticket_link and not is_valid_jira_ticket_link(ticket_link):
        raise ValueError("The supplied Jira ticket link is invalid.")
    cloud = normalize_cloud(agent_result["cloud"])
    workflow = agent_result.get("workflow")
    repo_target = normalize_repo_target(cloud, str(agent_result.get("repo_target") or ""), workflow)
    bucket = state_bucket_for_target(cloud, repo_target, workflow)
    state = (THREAD_PR_STATE.get(thread_id) or {}).get(bucket) or {}
    branch_name = str(state.get("branch") or "").strip()
    if not branch_name:
        raise RuntimeError("No Terrabot branch is available for this Teams conversation.")

    repo = github_repo_for_cloud(
        cloud,
        repo_target=repo_target,
        workflow=workflow,
    )
    base_branch = str(
        state.get("base_branch")
        or github_resolve_base_branch_for_cloud(
            cloud,
            repo_target=repo_target,
            workflow=workflow,
        )
    ).strip()
    headers = github_headers()
    fallback_title = (
        agent_result.get("title")
        or state.get("title")
        or f"[{cloud.upper()}] Terraform changes"
    )
    original_request = str(
        state.get("original_prompt")
        or prompt
        or "Terraform infrastructure changes"
    ).strip()

    template = _github_pull_request_template_for_teams(
        GITHUB_OWNER,
        repo,
        base_branch,
        headers,
    )
    title, body, _compare = _generate_workspace_pr_metadata(
        data={
            "template": template,
            "prompt": original_request,
            "title": fallback_title,
        },
        owner=GITHUB_OWNER,
        repo=repo,
        base=base_branch,
        head=branch_name,
        headers=headers,
    )
    body = _teams_pr_body_with_jira_and_attribution(
        body,
        ticket_link=ticket_link,
        ticket_number=jira_ticket,
        teams_requester=(
            state.get("teams_requester")
            or _ACTIVE_TEAMS_REQUESTER_DISPLAY.get()
        ),
    )

    existing = github_find_pr_by_branch(
        cloud,
        branch_name,
        state="open",
        repo_target=repo_target,
        workflow=workflow,
    )
    if existing:
        response = requests.patch(
            f"{GITHUB_API}/repos/{GITHUB_OWNER}/{repo}/pulls/{existing.get('number')}",
            headers=headers,
            json={"title": title, "body": body},
            timeout=30,
        )
        if not response.ok:
            raise _github_request_error(response, "Refreshing the existing Teams pull request description")
        pr = response.json() or existing
        message = "Existing pull request updated successfully."
    else:
        pr = github_create_pull_request(
            cloud=cloud,
            branch_name=branch_name,
            title=title,
            body=body,
            repo_target=repo_target,
            workflow=workflow,
        )
        message = "Pull request created successfully."

    state.update({
        "pr_number": pr.get("number"),
        "pr_url": pr.get("html_url"),
        "has_open_pr": True,
        "ticket_number": jira_ticket,
        "ticket_link": ticket_link,
        "ticket_title": ticket_title,
        "title": title,
        "pr_body": body,
    })
    try:
        trigger_test_branch_pipeline_for_pr(
            repo_owner=GITHUB_OWNER,
            repo_name=repo,
            pr_number=int(pr.get("number")),
            source_branch=branch_name,
            target_branch=base_branch,
        )
    except Exception as trigger_error:
        LOGGER.warning("Failed to trigger Azure pipeline for PR %s: %s", pr.get("number"), trigger_error)

    return {
        "cloud": cloud,
        "branch": branch_name,
        "branch_url": state.get("branch_url"),
        "compare_url": state.get("compare_url"),
        "pr_number": pr.get("number"),
        "pr_url": pr.get("html_url"),
        "message": message,
    }


def _teams_branch_choice_required_result(
    data: dict,
    state: dict,
    prompt: str,
    teams_conversation_id: str,
    conversation_id: str,
) -> tuple[dict, int]:
    branch = str(state.get("branch") or "").strip()
    patch = {
        "stage": "awaiting_branch_reuse_decision",
        "pending_follow_up_prompt": prompt,
        "pending_follow_up_ticket_link": data.get("ticket_link") or state.get("ticket_link") or "",
        "pending_follow_up_ticket_number": data.get("jira_ticket") or state.get("ticket_number") or "",
        "pending_follow_up_ticket_title": data.get("ticket_title") or state.get("ticket_title") or "",
    }
    _teams_save_ui_state(teams_conversation_id, patch)
    return {
        "ok": False,
        "mode": "branch_choice_required",
        "decision_state": "awaiting_branch_reuse_decision",
        "reply": (
            f"This Teams conversation already has Terrabot branch `{branch}`. "
            "Should I apply this follow-up change to the same branch? "
            "Reply `yes` to reuse it, or `no` to create a new `terrabot/` branch from the latest remote main branch."
        ),
        "thread_id": conversation_id,
        "branch": branch,
        "branch_url": state.get("branch_url") or "",
        "compare_url": state.get("compare_url") or "",
        "state_patch": patch,
    }, 400


def _handle_teams_chat_request_safe(data: dict):
    """Teams wrapper with durable branch-choice and GitHub-remote continuity."""
    request_data = dict(data or {})
    prompt = str(request_data.get("prompt") or request_data.get("message") or "").strip()
    action = str(request_data.get("action") or "").strip().lower()
    teams_conversation_id = str(
        request_data.get("teams_conversation_id")
        or request_data.get("conversation_id")
        or ""
    ).strip()
    state = load_teams_conversation_state(teams_conversation_id) if teams_conversation_id else {}
    memory_conversation_id = str(
        request_data.get("memory_conversation_id")
        or teams_conversation_id
    ).strip()
    conversation_id = str(
        request_data.get("thread_id")
        or state.get("workflow_thread_id")
        or state.get("foundry_conversation_id")
        or ""
    ).strip()
    stage = str(state.get("stage") or "").strip()
    branch = str(state.get("branch") or "").strip()

    reuse_branch = _teams_truthy(request_data.get("reuse_branch"))
    force_new_branch = _teams_truthy(request_data.get("force_new_branch"))
    state_patch: dict = {}

    if not action and stage == "awaiting_branch_reuse_decision":
        pending_prompt = str(state.get("pending_follow_up_prompt") or "").strip()
        choice = _teams_branch_choice_from_reply(prompt)
        if not pending_prompt:
            state_patch = {"stage": "awaiting_pr_decision", "pending_follow_up_prompt": None}
            _teams_save_ui_state(teams_conversation_id, state_patch)
        elif not choice:
            return {
                "ok": False,
                "mode": "branch_choice_required",
                "decision_state": "awaiting_branch_reuse_decision",
                "reply": (
                    f"Reply `yes` to apply the pending follow-up to `{branch}`, "
                    "or `no` to create a new `terrabot/` branch from the latest remote main branch."
                ),
                "thread_id": conversation_id,
                "branch": branch,
                "state_patch": {},
            }, 400
        else:
            request_data["prompt"] = pending_prompt
            prompt = pending_prompt
            reuse_branch = choice == "reuse"
            force_new_branch = choice == "new"
            request_data["reuse_branch"] = reuse_branch
            request_data["force_new_branch"] = force_new_branch
            request_data["existing_branch"] = branch
            for source_key, target_key in (
                ("pending_follow_up_ticket_link", "ticket_link"),
                ("pending_follow_up_ticket_number", "jira_ticket"),
                ("pending_follow_up_ticket_title", "ticket_title"),
            ):
                if state.get(source_key) and not request_data.get(target_key):
                    request_data[target_key] = state.get(source_key)
            state_patch = {
                "stage": "processing_follow_up",
                "pending_follow_up_prompt": None,
                "pending_follow_up_ticket_link": None,
                "pending_follow_up_ticket_number": None,
                "pending_follow_up_ticket_title": None,
            }
            state = _teams_save_ui_state(teams_conversation_id, state_patch)

    branch = str(state.get("branch") or request_data.get("existing_branch") or branch).strip()
    stage = str(state.get("stage") or stage).strip()

    # When a branch already exists, a new infrastructure instruction must not
    # silently choose between mutating that branch and starting from main.
    if (
        not action
        and branch
        and stage in {"awaiting_pr_decision", "complete", "idle"}
        and not _teams_prompt_requests_pr(prompt)
        and str(request_data.get("mode") or "").strip().lower() == "infra"
        and normalize_yes_no_reply(prompt) not in AFFIRMATIVE_REPLIES | NEGATIVE_REPLIES
        and not reuse_branch
        and not force_new_branch
        and not _teams_truthy(request_data.get("pending_branch_choice_resolved"))
    ):
        if _teams_prompt_requests_same_branch(prompt):
            reuse_branch = True
            request_data["reuse_branch"] = True
            request_data["existing_branch"] = branch
        elif _teams_prompt_requests_new_branch(prompt):
            force_new_branch = True
            request_data["force_new_branch"] = True
            request_data["existing_branch"] = branch
        else:
            return _teams_branch_choice_required_result(
                request_data,
                state,
                prompt,
                teams_conversation_id,
                conversation_id,
            )

    create_pr_requested = _teams_truthy(request_data.get("create_pr_requested")) or _teams_prompt_requests_pr(prompt)
    flow_context = {
        "active": True,
        "teams_conversation_id": teams_conversation_id,
        "memory_conversation_id": memory_conversation_id,
        "thread_id": conversation_id,
        "effective_prompt": prompt,
        "reuse_branch": reuse_branch,
        "force_new_branch": force_new_branch,
        "existing_branch": branch,
        "create_pr_requested": create_pr_requested,
        "fresh_infra_generation": _teams_truthy(request_data.get("fresh_infra_generation")),
        # Repository routing fields are also used to retrieve shared durable
        # repository context from Azure AI Search before the Foundry call.
        "cloud": str(
            request_data.get("cloud") or request_data.get("requested_cloud") or state.get("cloud") or ""
        ).strip().lower(),
        "repo_target": str(state.get("repo_target") or request_data.get("repo_target") or "").strip().lower(),
        "repo_name": str(request_data.get("repo_name") or state.get("repo") or "").strip(),
        "requester": str(request_data.get("teams_requester") or "").strip(),
        # Test-only observability. These fields do not alter routing/generation;
        # they let the isolated E2E harness prove that retrieved context was
        # actually attached before the Foundry call.
        "test_mode": _teams_truthy(request_data.get("test_mode")),
        "automated_test_case_id": str(request_data.get("automated_test_case_id") or "").strip(),
        "required_repository_context_ids": [
            str(value).strip()
            for value in (request_data.get("required_repository_context_ids") or [])
            if str(value).strip()
        ],
        # Automated tests may ask a read-only Cursor agent to resolve a genuine
        # repository clarification. This is only a hint until part 13 proves
        # the exact path/flag/value against the live repository evidence.
        "cursor_repository_resolution": (
            dict(request_data.get("cursor_repository_resolution") or {})
            if _teams_truthy(request_data.get("test_mode"))
            and isinstance(request_data.get("cursor_repository_resolution"), dict)
            else {}
        ),
    }
    context_token = _ACTIVE_TEAMS_FLOW_CONTEXT.set(flow_context)
    try:
        prefetch = globals().get("_start_repository_context_prefetch")
        if callable(prefetch):
            try:
                prefetch(flow_context)
            except Exception as exc:
                LOGGER.warning("[TerrabotDiag] event=repository_context_prefetch_start_failed error=%s", exc)
        result, status_code = _ORIGINAL_HANDLE_TEAMS_CHAT_REQUEST(request_data)
        if flow_context.get("test_mode") and isinstance(result, dict):
            diagnostics = flow_context.get("repository_context_test_diagnostics")
            if isinstance(diagnostics, dict):
                result = dict(result)
                result["test_diagnostics"] = {"repository_context": dict(diagnostics)}

        # AWS create/add/provision requests are execute-now after branch choice.
        # Foundry is not allowed to turn repository placement/module existence
        # into another user approval step. If it nevertheless returns a module/
        # path clarification, resolve the environment and module catalog in the
        # backend. A verified miss enters the existing missing-module generator
        # and auto-commit path immediately, so Teams receives only the pushed
        # branch result.
        aws_prompt = str(
            request_data.get("original_prompt")
            or flow_context.get("effective_prompt")
            or request_data.get("prompt")
            or ""
        ).strip()
        aws_create_request = bool(
            re.search(r"\b(create|add|provision|deploy|build|make)\b", aws_prompt, re.IGNORECASE)
            and safe_normalize_cloud(infer_cloud_from_prompt(aws_prompt)) == "aws"
        )
        result_text = " ".join(
            str((result or {}).get(key) or "")
            for key in ("reply", "summary", "questions")
        ).lower()
        aws_repo_question = bool(
            isinstance(result, dict)
            and str(result.get("mode") or "").lower() == "clarification"
            and (
                "which module" in result_text
                or "module should i use" in result_text
                or "module should be used" in result_text
                or "brand-new" in result_text
                or "brand new" in result_text
                or "terraform/modules" in result_text
                or "consumer block" in result_text
                or "target file" in result_text
                or "file path" in result_text
                or "repository path" in result_text
                or "candidates" in result_text
            )
        )
        if aws_create_request and aws_repo_question:
            environment_path, environment_error = resolve_aws_environment_path(
                aws_prompt,
                retrieved_value_context=flow_context.get("retrieved_value_context") or [],
                current_environment_path=flow_context.get("environment_path") or None,
            )
            if not environment_error and environment_path:
                try:
                    live_discovery = discover_live_aws_module_candidates(
                        aws_prompt,
                        environment_path=environment_path,
                        branch=flow_context.get("context_branch") or None,
                    )
                except Exception as discovery_error:
                    LOGGER.exception(
                        "Teams AWS execute-now recovery discovery failed",
                        exc_info=discovery_error,
                    )
                    live_discovery = {}

                if str(live_discovery.get("status") or "").strip().lower() == "not_found":
                    proposed_module_path = infer_new_aws_module_path(aws_prompt, live_discovery)
                    recovery_preview = {
                        "ok": False,
                        "mode": "clarification",
                        "reply": "Verified AWS module absence; continuing automatic module creation.",
                        "thread_id": (result or {}).get("thread_id") or conversation_id or request_data.get("thread_id") or "",
                        "request_prompt": aws_prompt,
                        "ticket_number": (result or {}).get("ticket_number") or request_data.get("jira_ticket") or "",
                        "jira_ticket": (result or {}).get("jira_ticket") or request_data.get("jira_ticket") or "",
                        "ticket_link": (result or {}).get("ticket_link") or request_data.get("ticket_link") or "",
                        "ticket_title": (result or {}).get("ticket_title") or request_data.get("ticket_title") or "",
                        "decision_state": "aws_module_creation_confirmation",
                        "router": {
                            "request_type": "infra",
                            "cloud": "aws",
                            "workflow": "aws_module_creation_confirmation",
                            "reason": "Backend verified no matching AWS module; Teams auto-creation required.",
                        },
                        "aws_module_discovery": live_discovery,
                        "environment_path": environment_path,
                        "proposed_module_path": proposed_module_path,
                    }
                    result, status_code = _teams_auto_accept_aws_module_creation(
                        request_data,
                        recovery_preview,
                        400,
                    )

        # Hard recovery for the exact module-selection failure where Foundry
        # acknowledged an infrastructure request but returned no files. The
        # selected AWS module and environment are already backend-verified, so
        # materialize a consumer with grounded values/__FILL__ tokens and push
        # it instead of asking the user to restart the request.
        confirmed_aws = _get_confirmed_aws_module_selection(
            flow_context.get("retrieved_value_context") or []
        )
        no_file_failure = (
            isinstance(result, dict)
            and status_code >= 400
            and str(result.get("mode") or "").lower() == "clarification"
            and (
                "without terraform files" in str(result.get("reply") or "").lower()
                or "no terraform files" in str(result.get("reply") or "").lower()
                or "single-cloud request" in str(result.get("reply") or "").lower()
                or "could not find any files for the environment" in str(result.get("reply") or "").lower()
                or "resolved the aws environment" in str(result.get("reply") or "").lower()
            )
        )
        if no_file_failure and safe_normalize_cloud(flow_context.get("expected_cloud")) == "aws" and confirmed_aws:
            fallback = None  # Terraform recovery must be performed by Foundry, never synthesized by backend.
            fallback_thread_id = str(
                result.get("thread_id")
                or flow_context.get("thread_id")
                or conversation_id
                or _teams_workflow_thread_id(request_data)
            ).strip()
            ticket_number = str(request_data.get("jira_ticket") or state.get("ticket_number") or "").strip()
            ticket_link = str(request_data.get("ticket_link") or state.get("ticket_link") or "").strip()
            ticket_title = str(request_data.get("ticket_title") or state.get("ticket_title") or "").strip()
            if fallback is None:
                return result, status_code
            pending_key = store_pending_infra_change(
                fallback_thread_id,
                ticket_number,
                prompt,
                fallback,
                ticket_link=ticket_link,
                ticket_title=ticket_title,
            )
            preview = {
                "ok": True,
                "mode": "infra_preview",
                "reply": "The selected verified AWS module was materialized and is ready for branch creation.",
                "thread_id": fallback_thread_id,
                "pending_change_id": pending_key,
                "cloud": "aws",
                "workflow": fallback.get("workflow"),
                "repo_target": fallback.get("repo_target"),
                "title": fallback.get("title"),
                "summary": fallback.get("summary"),
                "analysis": fallback.get("analysis"),
                "files": [item.get("filename") for item in fallback.get("files") or []],
                "user_fillable": fallback.get("user_fillable") or [],
            }
            recovery_request = dict(request_data)
            recovery_request["thread_id"] = fallback_thread_id
            result, status_code = _teams_auto_commit_preview(recovery_request, preview, 200)

        if state_patch:
            result = dict(result or {})
            # Preserve None values as explicit deletion directives for the
            # Teams adapter's process-local cache. Applying the patch here
            # would discard those keys and allow stale follow-up state to be
            # written back over the durable state.
            combined_state_patch = dict(result.get("state_patch") or {})
            combined_state_patch.update(state_patch)
            result["state_patch"] = combined_state_patch

        # Combined infrastructure + PR requests commit the branch first. If a
        # Jira link was supplied, create/refresh the PR immediately; otherwise
        # retain the branch and ask only for the Jira link.
        if (
            create_pr_requested
            and status_code < 400
            and isinstance(result, dict)
            and result.get("mode") == "branch_created"
            and result.get("pending_change_id")
        ):
            ticket_link = str(
                request_data.get("ticket_link")
                or _teams_extract_ticket_link_from_prompt(prompt)
                or state.get("ticket_link")
                or ""
            ).strip()
            if ticket_link and is_valid_jira_ticket_link(ticket_link):
                pr_request = dict(request_data)
                pr_request.update({
                    "action": "create_pr_from_branch",
                    "thread_id": result.get("thread_id") or conversation_id,
                    "pending_change_id": result.get("pending_change_id"),
                    "ticket_link": ticket_link,
                    "prompt": prompt,
                    "reuse_branch": True,
                    "existing_branch": result.get("branch") or branch,
                })
                return _ORIGINAL_HANDLE_TEAMS_CHAT_REQUEST(pr_request)

            jira_patch = {
                "stage": "awaiting_jira",
                "pending_change_id": result.get("pending_change_id"),
                "branch": result.get("branch"),
                "branch_url": result.get("branch_url"),
                "compare_url": result.get("compare_url"),
                "create_pr_requested": True,
            }
            _teams_save_ui_state(teams_conversation_id, jira_patch)
            jira_result = dict(result)
            jira_result.update({
                "mode": "jira_required",
                "decision_state": "awaiting_jira",
                "reply": (
                    "The Terraform changes are already pushed to the Terrabot branch. "
                    "Send the Jira ticket link and I will create the pull request with the generated description."
                ),
                "state_patch": jira_patch,
            })
            return jira_result, 200

        return result, status_code
    finally:
        _ACTIVE_TEAMS_FLOW_CONTEXT.reset(context_token)

# ============================================================================
# Teams repository-scope, surgical-modification, and cross-repository safety
# addendum. This is intentionally appended so existing VS Code/backend entry
# points and all earlier Terrabot workflows remain intact.
# ============================================================================

_TEAMS_SAFE_PREVIOUS_BUILD_MODIFICATION_CONTEXT = _build_backend_existing_infra_modification_context_teams_v1
_TEAMS_SAFE_PREVIOUS_BUILD_SELECTED_MODIFICATION_CONTEXT = _build_selected_infra_modification_context_base
_TEAMS_SAFE_PREVIOUS_BUILD_AGENT_INPUT = _build_agent_input_for_infra_teams_v1
_TEAMS_SAFE_PREVIOUS_COMMIT_TO_BRANCH = _commit_terraform_files_to_branch_for_teams_base
_TEAMS_SAFE_PREVIOUS_HANDLE_CHAT = _handle_teams_chat_request_safe
_TEAMS_SAFE_AZURE_SCOPE_CACHE: dict[str, list[str]] = {}


def _teams_safe_normalized_phrase(value: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()),
    ).strip()


def _teams_safe_request_cloud(prompt: str) -> str:
    """Resolve an explicit Teams repository switch without using old thread state."""
    normalized_prompt = re.sub(
        r"\baca\s+(?:app|application|service)s?\b",
        "azure container app",
        str(prompt or ""),
        flags=re.IGNORECASE,
    )
    inferred = safe_normalize_cloud(infer_cloud_from_prompt(normalized_prompt))
    if inferred:
        return inferred
    text = _teams_safe_normalized_phrase(prompt)
    if any(marker in text for marker in ("tf azure hub", "azure hub", "azurerm", "hub tfvars")):
        return "azure"
    if any(marker in text for marker in ("tf devops", "dev aws", "prod aws", "amazon web services")):
        return "aws"
    return ""


def _teams_safe_list_azure_scope_directories(branch: str) -> list[str]:
    """List live tf-azure-hub directories beneath vars/ for prompt scoping."""
    cache_key = str(branch or "main").strip() or "main"
    cached = _TEAMS_SAFE_AZURE_SCOPE_CACHE.get(cache_key)
    if cached is not None:
        return list(cached)

    directories: list[str] = []
    visited: set[str] = set()

    def walk(path: str, depth: int) -> None:
        normalized = str(path or "vars").strip().strip("/") or "vars"
        if normalized in visited or depth > 4 or len(directories) >= 400:
            return
        visited.add(normalized)
        try:
            entries = github_get_directory_listing(
                "azure",
                normalized,
                cache_key,
                repo_target="tf-azure-hub",
                workflow="azure_infra_modification",
            )
        except Exception as exc:
            LOGGER.warning("Unable to enumerate Azure modification scope %s@%s: %s", normalized, cache_key, exc)
            return

        for item in entries or []:
            if str((item or {}).get("type") or "") != "dir":
                continue
            item_path = str((item or {}).get("path") or "").strip().strip("/")
            if not item_path or not item_path.startswith("vars/"):
                continue
            if item_path not in directories:
                directories.append(item_path)
            walk(item_path, depth + 1)

    walk("vars", 0)
    _TEAMS_SAFE_AZURE_SCOPE_CACHE[cache_key] = list(directories)
    return directories


def _teams_safe_azure_scope_from_prompt(prompt: str, branch: str) -> tuple[str, str]:
    """Infer a concrete tf-azure-hub folder from the user's own prompt.

    Explicit paths win. Exact environment routing already present in the
    service is next. Otherwise the live `vars/` directory tree is matched so
    this works for hubs not hardcoded in Python.
    """
    explicit_tfvars = _explicit_tfvars_path_from_prompt(prompt)
    if explicit_tfvars:
        return explicit_tfvars.rsplit("/", 1)[0], f"explicit tfvars path `{explicit_tfvars}`"

    for explicit_path in _explicit_iac_paths_from_prompt(prompt):
        if explicit_path.startswith("vars/"):
            return explicit_path.rsplit("/", 1)[0], f"explicit Terraform path `{explicit_path}`"

    exact_candidates, exact_environment = _azure_exact_environment_tfvars_candidates(prompt)
    for candidate in exact_candidates or []:
        if _tf_azure_hub_tfvars_file_exists(candidate, branch):
            return candidate.rsplit("/", 1)[0], f"environment `{exact_environment}` named in the prompt"

    prompt_phrase = _teams_safe_normalized_phrase(prompt)
    prompt_tokens = set(prompt_phrase.split())
    ranked: list[tuple[int, int, str]] = []

    for directory in _teams_safe_list_azure_scope_directories(branch):
        relative = directory[len("vars/"):] if directory.startswith("vars/") else directory
        path_phrase = _teams_safe_normalized_phrase(relative)
        base_phrase = _teams_safe_normalized_phrase(directory.rsplit("/", 1)[-1])
        base_tokens = [token for token in base_phrase.split() if token]
        if not base_tokens:
            continue

        score = 0
        if base_phrase and re.search(rf"(?<![a-z0-9]){re.escape(base_phrase)}(?![a-z0-9])", prompt_phrase):
            score += 700 + (80 * len(base_tokens))
        if path_phrase and path_phrase in prompt_phrase:
            score += 900
        matched = sum(1 for token in base_tokens if token in prompt_tokens)
        if matched:
            score += matched * 90
        if matched == len(base_tokens):
            score += 300
        tier_tokens = [token for token in relative.split("/")[:-1] if token]
        score += sum(35 for token in tier_tokens if _teams_safe_normalized_phrase(token) in prompt_tokens)
        if score:
            ranked.append((score, directory.count("/"), directory))

    if not ranked:
        return "", ""

    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
    best_score, _depth, best_path = ranked[0]
    # Require meaningful evidence. A single generic token such as "vars" is
    # not sufficient to hide the rest of the repository from the user.
    if best_score < 300:
        return "", ""
    return best_path, f"live GitHub folder name matched the prompt (`{best_path}`)"


def _teams_safe_identifier_score(identifier: str, prompt: str) -> int:
    name = str(identifier or "").strip().lower()
    if not name:
        return 0
    prompt_phrase = _teams_safe_normalized_phrase(prompt)
    prompt_tokens = set(prompt_phrase.split())
    name_phrase = _teams_safe_normalized_phrase(name)
    parts = [part for part in re.split(r"[_\-]+", name) if part]
    prefix_words = {"create", "enable", "enabled", "disable", "disabled", "is", "has", "use", "allow", "set"}
    core = [part for part in parts if part not in prefix_words]
    core_phrase = " ".join(core)

    score = 0
    if name_phrase and name_phrase in prompt_phrase:
        score += 700
    if core_phrase and core_phrase in prompt_phrase:
        score += 500
    matched_core = sum(1 for part in core if part in prompt_tokens)
    score += matched_core * 70
    if core and matched_core == len(core):
        score += 220

    action_toggle = bool(re.search(r"\b(?:enable|disable|turn on|turn off)\b", prompt_phrase))
    toggle_identifier = (
        name.startswith(("create_", "enable_", "disable_"))
        or name.endswith(("_enabled", "_disabled"))
    )
    if action_toggle and toggle_identifier and (matched_core or (core_phrase and core_phrase in prompt_phrase)):
        score += 220
    return score


def _teams_safe_extended_modification_terms(prompt: str) -> list[str]:
    terms = list(_infra_modification_search_terms(prompt) or [])
    words = [
        token
        for token in re.findall(r"[a-z0-9]+", _teams_safe_normalized_phrase(prompt))
        if token not in {
            "add", "change", "create", "delete", "disable", "enable", "fix", "in", "modify",
            "remove", "set", "the", "to", "update", "aws", "azure", "terraform", "infra",
        }
    ]
    for size in (4, 3, 2):
        for index in range(0, max(0, len(words) - size + 1)):
            term = "_".join(words[index:index + size])
            if term and term not in terms:
                terms.append(term)
    return terms[:24]


def _teams_safe_selection_analysis(context: dict, prompt: str = "") -> str:
    scope_root = str(context.get("scope_root") or "").strip()
    scope_reason = str(context.get("scope_reason") or "").strip()
    paths = [str(item.get("path") or "") for item in context.get("matched_files") or [] if isinstance(item, dict)]
    lines = [
        f"Repository: {context.get('repo_full_name') or ''} on `{context.get('context_ref') or 'main'}`.",
    ]
    if scope_root:
        lines.append(f"Prompt scope: restricted repository analysis to `{scope_root}` because {scope_reason}.")
    lines.append(
        f"Target discovery: found {len(paths)} matching Terraform file(s) after applying the prompt scope and resource terms."
    )
    if paths:
        lines.append("Candidate evidence: " + ", ".join(f"`{path}`" for path in paths[:6]) + ".")
    lines.append("Safety: only the selected path may be modified; unrelated repository files are excluded from generation.")
    return "\n".join(lines)


def _build_backend_existing_infra_modification_context_teams_v2(
    prompt: str,
    thread_id: str,
    cloud: str,
    workflow: str,
    retrieved_value_context: list | None = None,
) -> dict:
    """Teams-only live GitHub target discovery with Azure hub-folder scoping."""
    active = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    normalized_cloud = safe_normalize_cloud(cloud)
    if not active.get("active") or normalized_cloud != "azure":
        return _TEAMS_SAFE_PREVIOUS_BUILD_MODIFICATION_CONTEXT(
            prompt,
            thread_id,
            cloud,
            workflow,
            retrieved_value_context=retrieved_value_context,
        )

    repo_target = normalize_repo_target("azure", workflow=workflow)
    branch = _teams_remote_context_branch("azure", repo_target, workflow)
    repo_full_name = f"{GITHUB_OWNER}/{github_repo_for_cloud('azure', repo_target=repo_target, workflow=workflow)}"
    scope_root, scope_reason = _teams_safe_azure_scope_from_prompt(prompt, branch)
    terms = _teams_safe_extended_modification_terms(prompt)
    seen_paths: set[str] = set()
    matched_files: list[dict] = []

    active["target_scope_root"] = scope_root
    active["target_scope_reason"] = scope_reason

    scope_parent = scope_root.rsplit("/", 1)[0] if scope_root and "/" in scope_root else ""

    def path_is_in_scope(path: str) -> bool:
        if not scope_root:
            return True
        normalized = str(path or "").strip().strip("/")
        if normalized.startswith(scope_root.rstrip("/") + "/"):
            return True
        # Azure environments can inherit feature switches from a direct parent
        # tier file (for example vars/sbx/tier.tfvars for vars/sbx/sbx-infra).
        # Include direct files in that parent, but never recurse into sibling
        # environment folders. This keeps the request environment-scoped while
        # allowing the backend to find the assignment owner automatically.
        return bool(scope_parent and "/" not in normalized[len(scope_parent.rstrip("/") + "/"):]
                    and normalized.startswith(scope_parent.rstrip("/") + "/"))

    def add_path(path: str, reason: str) -> None:
        normalized_path = str(path or "").strip().strip("/")
        if not normalized_path or normalized_path in seen_paths or not path_is_in_scope(normalized_path):
            return
        if not normalized_path.endswith((".tf", ".tfvars")):
            return
        try:
            content = github_get_file_content(
                "azure",
                normalized_path,
                branch,
                repo_target=repo_target,
                workflow=workflow,
            )
        except Exception:
            content = None
        if not content:
            return

        score = _score_infra_candidate(normalized_path, content, terms, prompt)
        for assignment_name in _extract_top_level_hcl_assignment_names(content):
            score += _teams_safe_identifier_score(assignment_name, prompt)
        preferred_kind = _azure_tfvars_file_kind_from_prompt(prompt)
        if scope_root and normalized_path == f"{scope_root}/{preferred_kind}.tfvars":
            score += 500
        if score <= 0 and terms:
            return

        seen_paths.add(normalized_path)
        matched_files.append({
            "path": normalized_path,
            "filename": normalized_path.rsplit("/", 1)[-1],
            "content": content,
            "matched_blocks": _matched_blocks_for_prompt(content, terms),
            "reason": reason,
            "score": score,
        })

    for explicit_path in _explicit_iac_paths_from_prompt(prompt):
        add_path(explicit_path, "exact path mentioned by the user")

    context_root = scope_root or _teams_context_root("azure", workflow, repo_target, prompt, thread_id)
    try:
        branch_files = _teams_load_existing_iac_files_for_context(
            "azure",
            branch,
            context_root,
            repo_target,
            workflow,
        )
        if scope_parent:
            # Search direct parent tier files as assignment owners. The scope
            # filter below excludes sibling environment subdirectories.
            branch_files.extend(
                _teams_load_existing_iac_files_for_context(
                    "azure",
                    branch,
                    scope_parent,
                    repo_target,
                    workflow,
                )
            )
    except Exception as exc:
        LOGGER.warning("Unable to scan scoped Azure context %s@%s: %s", context_root, branch, exc)
        branch_files = []

    branch_files.extend(
        item for item in _teams_previous_branch_files(thread_id, "azure", branch, repo_target, workflow)
        if path_is_in_scope(str((item or {}).get("path") or (item or {}).get("filename") or ""))
    )
    for item in branch_files:
        add_path(
            str((item or {}).get("path") or (item or {}).get("filename") or ""),
            str((item or {}).get("reason") or f"direct live GitHub scan of `{context_root}` on `{branch}`"),
        )

    query_prefix = f"repo:{repo_full_name}"
    if scope_root:
        query_prefix += f" path:{scope_root}"
    queries: list[str] = []
    for term in terms[:10]:
        queries.append(f'{query_prefix} "{term}" extension:tf')
        queries.append(f'{query_prefix} "{term}" extension:tfvars')

    for query in list(dict.fromkeys(queries))[:20]:
        try:
            items = github_search_code(query, per_page=25)
        except Exception as exc:
            LOGGER.warning("Scoped Azure GitHub search failed for %r: %s", query, exc)
            items = []
        for item in items or []:
            full_name = ((item or {}).get("repository") or {}).get("full_name") or ""
            if full_name and full_name.lower() != repo_full_name.lower():
                continue
            add_path(str((item or {}).get("path") or ""), f"GitHub code search: {query}")

    matched_files.sort(key=lambda item: (-int(item.get("score") or 0), item.get("path") or ""))
    for item in matched_files:
        item.pop("score", None)
    matched_files = matched_files[:12]

    selection_state = "selected" if scope_root and len(matched_files) == 1 else "candidate_selection_required"
    selected_path = matched_files[0].get("path") if selection_state == "selected" else ""
    result = {
        "source": "backend_existing_infra_code_match",
        "selection_state": selection_state,
        "cloud": "azure",
        "repo_target": repo_target,
        "workflow": workflow,
        "repo_full_name": repo_full_name,
        "context_ref": branch,
        "scope_root": scope_root,
        "scope_reason": scope_reason,
        "search_terms": terms,
        "selected_path": selected_path,
        "matched_files": matched_files,
        "matched_file_paths": [item.get("path") for item in matched_files if item.get("path")],
        "instructions": [
            "Only files inside the prompt-resolved Azure hub folder are valid modification targets when a folder was resolved.",
            "Use live GitHub content as the source of truth.",
            "Modify only the selected file and preserve every unrelated assignment, block, comment, and line.",
        ],
    }
    result["analysis"] = _teams_safe_selection_analysis(result, prompt)
    return result


def build_selected_infra_modification_context(pending_selection: dict, selected_index: int) -> dict:
    selected = _TEAMS_SAFE_PREVIOUS_BUILD_SELECTED_MODIFICATION_CONTEXT(pending_selection, selected_index)
    base = pending_selection.get("existing_infra_context") or {}
    selected["scope_root"] = base.get("scope_root") or ""
    selected["scope_reason"] = base.get("scope_reason") or ""
    selected["analysis"] = base.get("analysis") or _teams_safe_selection_analysis(
        base, pending_selection.get("original_prompt") or ""
    )
    # Discovery metadata only: the backend found this candidate via existing-
    # invocation discovery. The AGENT decides creation-vs-modification per its
    # own instructions; this flag merely lets the safety materializer accept
    # append-shaped output and new files for the discovered target.
    if base.get("invocation_generation"):
        selected["invocation_generation"] = True
        selected["operation"] = "existing_invocation_creation"
    return selected


def _teams_safe_hcl_compare(value: str) -> str:
    try:
        return _normalized_hcl_content_for_compare(value or "")
    except Exception:
        return re.sub(r"\s+", " ", str(value or "")).strip()


def _teams_safe_toggle_identifier(name: str) -> bool:
    lowered = str(name or "").strip().lower()
    return (
        lowered.startswith(("create_", "enable_", "disable_"))
        or lowered.endswith(("_enabled", "_disabled"))
    )


def _teams_safe_selected_identifiers(names: list[str], prompt: str) -> list[str]:
    unique = list(dict.fromkeys(str(name or "").strip() for name in names if str(name or "").strip()))
    if not unique:
        return []
    scored = [(name, _teams_safe_identifier_score(name, prompt)) for name in unique]
    toggle_request = bool(re.search(r"\b(?:enable|disable|turn on|turn off)\b", _teams_safe_normalized_phrase(prompt)))
    if toggle_request:
        toggle_scored = [(name, score) for name, score in scored if _teams_safe_toggle_identifier(name) and score > 0]
        if toggle_scored:
            scored = toggle_scored

    # A single changed identifier is already unambiguous.  Do not apply the
    # multi-candidate confidence threshold to it.  The old code did exactly
    # that, so a prompt such as "create an ACA app ..." produced a weak but
    # real match for the sole locals assignment `aca_apps` ("aca" matches,
    # singular "app" vs plural "apps" does not).  Its score was below 180,
    # selected_common became empty, and the backend rejected the otherwise
    # correct map-entry addition as "could not derive a prompt-specific
    # assignment change" on every self-correction attempt.
    #
    # Safety is unchanged: this shortcut is used only when there is exactly
    # one candidate identifier to choose from.  Multiple changed assignments
    # still require the existing relevance threshold so unrelated settings
    # cannot be applied broadly.
    if len(scored) == 1:
        return [scored[0][0]]

    positive = [(name, score) for name, score in scored if score > 0]
    if not positive:
        return []
    maximum = max(score for _name, score in positive)
    threshold = max(180, maximum - 50)
    return [name for name, score in positive if score >= threshold]


def _teams_safe_assignment_value(content: str, name: str) -> str:
    try:
        return str(_extract_hcl_assignment_value(content, name) or "").strip()
    except Exception:
        for span in _top_level_hcl_assignment_spans(content):
            if span.get("name") != name:
                continue
            text = str(span.get("text") or "")
            match = re.match(rf"(?s)^[ \t]*{re.escape(name)}[ \t]*=[ \t]*(.*)$", text)
            return str(match.group(1) if match else "").strip()
    return ""


def _teams_safe_replace_assignment_preserving_layout(content: str, name: str, new_value: str) -> str:
    text = str(content or "").replace("\r\n", "\n")
    spans = [item for item in _top_level_hcl_assignment_spans(text) if item.get("name") == name]
    if not spans:
        return text
    span = spans[0]
    current = str(span.get("text") or "")
    prefix_match = re.match(rf"(?s)^([ \t]*{re.escape(name)}[ \t]*=[ \t]*)(.*)$", current)
    prefix = prefix_match.group(1) if prefix_match else f"{name} = "
    replacement = prefix + str(new_value or "").strip()
    return text[:int(span["start"])] + replacement + text[int(span["end"]):]


def _teams_safe_remove_assignment(content: str, name: str) -> str:
    text = str(content or "").replace("\r\n", "\n")
    spans = [item for item in _top_level_hcl_assignment_spans(text) if item.get("name") == name]
    if not spans:
        return text
    span = spans[0]
    start, end = int(span["start"]), int(span["end"])
    if end < len(text) and text[end:end + 1] == "\n":
        end += 1
    return text[:start] + text[end:]


_TEAMS_LINE_KEY_RE = re.compile(r'^[ \t]*("?[\w][\w.-]*"?)[ \t]*=')

_TEAMS_MAP_ENTRY_KEY_RE = re.compile(r'^[ \t]*("?[\w][\w.-]*"?)[ \t]*=[ \t]*')


def _teams_norm_line(line: str) -> str:
    return re.sub(r"\s+", " ", str(line or "")).strip()


def _teams_line_counts(content: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for line in str(content or "").splitlines():
        key = _teams_norm_line(line)
        if key:
            counts[key] = counts.get(key, 0) + 1
    return counts


def _teams_unauthorized_removals(existing: str, final: str, prompt: str, path: str) -> str | None:
    """Return an error message when `final` would erase existing content the
    user did not ask to delete; None when the change is preservation-safe.

    Allowed removals:
    - explicit delete/remove/decommission/destroy wording in the prompt
      (the surgical delete paths already scope WHAT gets removed);
    - paired same-key value updates: every removed `key = old` line has a
      `key = new` line in the final content (flag toggles, size changes,
      count→for_each in-place refactors).
    Everything else — dropped entries, renamed keys, truncated blocks — is
    rejected so existing files can never be overwritten.
    """
    existing_counts = _teams_line_counts(existing)
    final_counts = _teams_line_counts(final)
    removed: list[str] = []
    for line, count in existing_counts.items():
        missing = count - final_counts.get(line, 0)
        removed.extend([line] * max(0, missing))
    if not removed:
        return None

    phrase = _teams_safe_normalized_phrase(prompt)
    if re.search(r"\b(?:delete|remove|decommission|destroy|drop|unset)\b", phrase):
        return None

    added_keys: set[str] = set()
    for line, count in final_counts.items():
        if count > existing_counts.get(line, 0):
            match = _TEAMS_LINE_KEY_RE.match(line)
            if match:
                added_keys.add(match.group(1).strip('"'))
    unpaired = []
    for line in removed:
        match = _TEAMS_LINE_KEY_RE.match(line)
        key = match.group(1).strip('"') if match else None
        if key is None or key not in added_keys:
            unpaired.append(line)
    if not unpaired:
        return None

    preview = "; ".join(unpaired[:3])
    return (
        f"Safe materialization for {path} was rejected: the change would remove "
        f"{len(unpaired)} existing line(s) the request did not ask to delete "
        f"(e.g. {preview}). Existing repository content must always be preserved; "
        "only explicit delete/decommission requests may remove code."
    )


def _teams_map_entry_spans(body: str) -> list[dict]:
    """First-level `key = ...` entries of a map/object body, including
    multiline {...}/[...] values, via brace and bracket counting."""
    entries: list[dict] = []
    lines = str(body or "").split("\n")
    index = 0
    offset = 0
    while index < len(lines):
        line = lines[index]
        match = _TEAMS_MAP_ENTRY_KEY_RE.match(line)
        if not match:
            offset += len(line) + 1
            index += 1
            continue
        start = offset
        depth = line.count("{") + line.count("[") - line.count("}") - line.count("]")
        end_index = index
        while depth > 0 and end_index + 1 < len(lines):
            end_index += 1
            nxt = lines[end_index]
            depth += nxt.count("{") + nxt.count("[") - nxt.count("}") - nxt.count("]")
        text = "\n".join(lines[index:end_index + 1])
        entries.append({
            "key": match.group(1).strip('"'),
            "start": start,
            "end": start + len(text),
            "text": text,
        })
        offset = start + len(text) + 1
        index = end_index + 1
    return entries


def _teams_is_multiline_map_value(value: str) -> bool:
    text = str(value or "").strip()
    return text.startswith("{") and text.endswith("}") and "\n" in text


def _teams_safe_prompt_resource_name(prompt: str) -> str:
    """Extract an explicitly requested resource name for Teams-safe delta targeting.

    Kept local to the Teams materializer so map/object creation does not depend
    on Foundry choosing a particular Terraform assignment name.
    """
    text = str(prompt or "").lower()
    for pattern in (
        r"\bwhose\s+name\s+is\s+[\"']?([a-z0-9][a-z0-9_-]{1,63})",
        r"\bname\s+is\s+[\"']?([a-z0-9][a-z0-9_-]{1,63})",
        r"\bnamed\s+[\"']?([a-z0-9][a-z0-9_-]{1,63})",
        r"\bcalled\s+[\"']?([a-z0-9][a-z0-9_-]{1,63})",
    ):
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""


def _teams_normalize_requested_identity(value: str) -> str:
    return re.sub(r"[-_.]+", "_", str(value or "").strip().lower()).strip("_")


def _teams_retarget_generated_map_entry(entry: dict, requested_name: str) -> dict:
    """Retarget one generated-only sibling entry to the explicit user name.

    This is intentionally limited to generated-only content. Existing live
    repository text is never rewritten. It closes the stale-sibling failure
    where Foundry cloned a valid ACA entry but left the prior sibling identity
    (for example cube-audit-cleanup-2) instead of the requested homepage-bff-2.
    """
    result = dict(entry or {})
    requested = str(requested_name or "").strip().lower()
    old_key = str(result.get("key") or "").strip()
    text = str(result.get("text") or "")
    if not requested or not old_key or not text:
        return result

    old_norm = _teams_normalize_requested_identity(old_key)
    requested_norm = _teams_normalize_requested_identity(requested)

    # Replace the map key itself first, preserving whether it was quoted.
    first_line, sep, remainder = text.partition("\n")
    key_match = re.match(r'^(\s*)("?)([^"=\s]+)("?)(\s*=.*)$', first_line)
    if key_match:
        quote = key_match.group(2) if key_match.group(2) == key_match.group(4) else ""
        first_line = (
            key_match.group(1) + quote + requested + quote + key_match.group(5)
        )
        text = first_line + (sep + remainder if sep else "")

    # Then retarget identity-bearing literals/identifiers inside the generated
    # sibling. Hyphenated resource names and underscore Terraform identifiers
    # are both common in ACA maps/flags.
    if old_key.lower() != requested:
        text = re.sub(re.escape(old_key), requested, text, flags=re.IGNORECASE)
    if old_norm and requested_norm and old_norm != requested_norm:
        # The instance token commonly sits inside a longer Terraform identifier
        # such as aca_app_<instance>_enabled, so identifier-boundary matching
        # would miss it. This text is generated-only and the replacement is
        # restricted to the exact normalized old instance token.
        text = re.sub(re.escape(old_norm), requested_norm, text, flags=re.IGNORECASE)

    result["key"] = requested
    result["text"] = text
    return result


def _teams_safe_map_entry_relevance(entry: dict, prompt: str) -> int:
    """Score a generated-only map entry against the current Teams request."""
    key = str((entry or {}).get("key") or "").strip()
    text = str((entry or {}).get("text") or "")
    score = _teams_safe_identifier_score(key, prompt)

    requested_name = _teams_safe_prompt_resource_name(prompt)
    if requested_name:
        normalized_requested = re.sub(r"[-_.]+", "_", requested_name.lower()).strip("_")
        normalized_key = re.sub(r"[-_.]+", "_", key.lower()).strip("_")
        if normalized_key == normalized_requested:
            score += 1000
        elif normalized_requested and normalized_requested in normalized_key:
            score += 500
        if requested_name.lower() in text.lower():
            score += 500

    for term in _teams_safe_extended_modification_terms(prompt):
        term_text = str(term or "").strip().lower()
        if term_text and term_text in text.lower():
            score += 40
    return score


def _teams_safe_creation_map_assignment(
    changed_names: list[str],
    existing_by_name: dict,
    generated_by_name: dict,
    existing_content: str,
    generated_content: str,
    prompt: str,
) -> str:
    """Select the assignment that actually contains the requested new map entry.

    This is the deterministic Teams fallback for map-driven resource families
    such as ACA apps. It targets the semantic delta (a generated-only sibling
    entry), rather than requiring the container assignment name itself to score
    above a generic keyword threshold.
    """
    phrase = _teams_safe_normalized_phrase(prompt)
    if not re.search(r"\b(?:create|add|provision|deploy)\b", phrase):
        return ""

    candidates: list[tuple[str, int, int]] = []
    for name in changed_names:
        if name not in existing_by_name or name not in generated_by_name:
            continue
        existing_value = _teams_safe_assignment_value(existing_content, name)
        generated_value = _teams_safe_assignment_value(generated_content, name)
        if not (_teams_is_multiline_map_value(existing_value) and _teams_is_multiline_map_value(generated_value)):
            continue

        e_open, e_close = existing_value.find("{"), existing_value.rfind("}")
        g_open, g_close = generated_value.find("{"), generated_value.rfind("}")
        if min(e_open, e_close, g_open, g_close) < 0:
            continue
        existing_entries = _teams_map_entry_spans(existing_value[e_open + 1:e_close])
        generated_entries = _teams_map_entry_spans(generated_value[g_open + 1:g_close])
        existing_keys = {entry["key"] for entry in existing_entries}
        new_entries = [entry for entry in generated_entries if entry["key"] not in existing_keys]
        if not new_entries:
            continue

        entry_score = max((_teams_safe_map_entry_relevance(entry, prompt) for entry in new_entries), default=0)
        container_score = _teams_safe_identifier_score(name, prompt)
        candidates.append((name, max(entry_score, container_score), len(new_entries)))

    if not candidates:
        return ""

    # An explicit resource-name hit is definitive even when the container is
    # generically named (for example `aca_apps`).
    strong = [item for item in candidates if item[1] >= 500]
    if len(strong) == 1:
        return strong[0][0]

    positive = [item for item in candidates if item[1] > 0]
    if len(positive) == 1:
        return positive[0][0]

    # If exactly one changed map contains any generated-only entry, it is an
    # unambiguous additive delta in the already-selected Teams target file.
    if len(candidates) == 1:
        return candidates[0][0]
    return ""


def _teams_safe_merge_map_value(existing_value: str, generated_value: str, prompt: str, path: str) -> str:
    """Additively merge a generated map/object value into the existing one.
    Existing entries are always kept verbatim (never replaced wholesale,
    never renamed, never dropped). Generated-only entries are appended
    inside the map — the Teams equivalent of insert_into_block. Single-line
    entries present in both are updated in place only when the prompt
    expresses update intent for that key."""
    existing_text = str(existing_value or "")
    generated_text = str(generated_value or "")
    open_idx = existing_text.find("{")
    close_idx = existing_text.rfind("}")
    g_open = generated_text.find("{")
    g_close = generated_text.rfind("}")
    if min(open_idx, close_idx, g_open, g_close) < 0:
        return existing_text

    existing_body = existing_text[open_idx + 1:close_idx]
    generated_body = generated_text[g_open + 1:g_close]
    existing_entries = _teams_map_entry_spans(existing_body)
    generated_entries = _teams_map_entry_spans(generated_body)
    existing_keys = {entry["key"] for entry in existing_entries}

    body = existing_body
    phrase = _teams_safe_normalized_phrase(prompt)
    update_intent = bool(re.search(r"\b(?:set|update|change|modify|resize|scale)\b", phrase))
    if update_intent:
        generated_by_key = {entry["key"]: entry for entry in generated_entries}
        for entry in sorted(existing_entries, key=lambda item: int(item["start"]), reverse=True):
            gen = generated_by_key.get(entry["key"])
            if (
                gen is not None
                and "\n" not in entry["text"]
                and "\n" not in gen["text"]
                and _teams_safe_hcl_compare(entry["text"]) != _teams_safe_hcl_compare(gen["text"])
                and _teams_safe_identifier_score(entry["key"], prompt) > 0
            ):
                body = body[: int(entry["start"])] + gen["text"] + body[int(entry["end"]):]

    new_entries = [entry for entry in generated_entries if entry["key"] not in existing_keys]
    selected_entries = list(new_entries)
    if len(new_entries) > 1:
        requested_name = _teams_safe_prompt_resource_name(prompt)
        exact = []
        if requested_name:
            target = re.sub(r"[-_.]+", "_", requested_name.lower()).strip("_")
            exact = [
                entry for entry in new_entries
                if re.sub(r"[-_.]+", "_", str(entry.get("key") or "").lower()).strip("_") == target
                or requested_name.lower() in str(entry.get("text") or "").lower()
            ]
        if exact:
            selected_entries = exact
        else:
            scored_entries = [
                (entry, _teams_safe_map_entry_relevance(entry, prompt))
                for entry in new_entries
            ]
            positive = [(entry, score) for entry, score in scored_entries if score > 0]
            if positive:
                maximum = max(score for _entry, score in positive)
                selected_entries = [entry for entry, score in positive if score >= max(120, maximum - 40)]
            else:
                # Multiple unrelated generated-only entries with no request
                # relevance are unsafe to append.
                selected_entries = []

    additions = [entry["text"] for entry in selected_entries]
    if additions:
        body = body.rstrip("\n") + "\n\n" + "\n\n".join(item.rstrip("\n") for item in additions) + "\n"

    return existing_text[: open_idx + 1] + body + existing_text[close_idx:]


def _teams_safe_patch_hcl_assignments(
    existing_content: str,
    generated_content: str,
    prompt: str,
    path: str,
) -> tuple[str, dict]:
    """Apply only prompt-relevant HCL assignments to the live existing text."""
    existing = str(existing_content or "").replace("\r\n", "\n")
    generated = str(generated_content or "").replace("\r\n", "\n")
    existing_spans = _top_level_hcl_assignment_spans(existing)
    generated_spans = _top_level_hcl_assignment_spans(generated)
    existing_by_name = {item["name"]: item for item in existing_spans}
    generated_by_name = {item["name"]: item for item in generated_spans}

    changed_common = [
        name for name in existing_by_name.keys() & generated_by_name.keys()
        if _teams_safe_hcl_compare(existing_by_name[name]["text"]) != _teams_safe_hcl_compare(generated_by_name[name]["text"])
    ]
    selected_common = _teams_safe_selected_identifiers(changed_common, prompt)

    # Creation requests against map-driven resource files need to target the
    # assignment that contains the requested NEW sibling entry. The container
    # name can be generic/plural (`aca_apps`) and score weakly against a prompt
    # that names one app. Select from the semantic map delta before applying
    # any generated changes, and narrow to that assignment so unrelated model
    # rewrites cannot hitchhike into the commit.
    creation_map_name = _teams_safe_creation_map_assignment(
        changed_common,
        existing_by_name,
        generated_by_name,
        existing,
        generated,
        prompt,
    )
    if creation_map_name:
        selected_common = [creation_map_name]

    prompt_phrase = _teams_safe_normalized_phrase(prompt)
    explicit_delete = bool(re.search(r"\b(?:delete|remove|unset)\b", prompt_phrase))
    explicit_add_or_set = bool(re.search(r"\b(?:add|create|enable|disable|set|update|change|modify)\b", prompt_phrase))

    generated_only = list(generated_by_name.keys() - existing_by_name.keys())
    selected_new = [
        name for name in _teams_safe_selected_identifiers(generated_only, prompt)
        if explicit_add_or_set and _teams_safe_identifier_score(name, prompt) >= 300
    ]

    missing_from_generated = list(existing_by_name.keys() - generated_by_name.keys())
    selected_delete = (
        [name for name in _teams_safe_selected_identifiers(missing_from_generated, prompt) if _teams_safe_identifier_score(name, prompt) >= 300]
        if explicit_delete else []
    )

    # Deterministic recovery for simple boolean toggle requests. This covers
    # cases where the model proposed unrelated schedule settings but omitted
    # the one existing flag that the user explicitly asked to enable/disable.
    fallback_toggle = ""
    fallback_value = ""
    if not selected_common and not selected_new and not selected_delete:
        desired = ""
        if re.search(r"\b(?:disable|turn off)\b", prompt_phrase):
            desired = "false"
        elif re.search(r"\b(?:enable|turn on)\b", prompt_phrase):
            desired = "true"
        if desired:
            toggle_candidates = [
                name for name in existing_by_name
                if _teams_safe_toggle_identifier(name) and _teams_safe_identifier_score(name, prompt) > 0
            ]
            selected_toggle = _teams_safe_selected_identifiers(toggle_candidates, prompt)
            if len(selected_toggle) == 1:
                fallback_toggle = selected_toggle[0]
                fallback_value = desired

    final = existing
    applied: list[str] = []
    ignored_generated = [name for name in generated_only if name not in selected_new]

    for name in selected_common:
        value = _teams_safe_assignment_value(generated, name)
        if not value:
            continue
        existing_value = _teams_safe_assignment_value(existing, name)
        if _teams_is_multiline_map_value(existing_value) and _teams_is_multiline_map_value(value):
            # A map/object value is a container of sibling entries — replacing
            # it wholesale can silently rename or drop entries (the aca_apps
            # locals overwrite). Merge additively instead: keep every existing
            # entry, append new ones, update single lines only on explicit
            # update intent.
            value = _teams_safe_merge_map_value(existing_value, value, prompt, path)
            if _teams_safe_hcl_compare(value) == _teams_safe_hcl_compare(existing_value):
                continue
        final = _teams_safe_replace_assignment_preserving_layout(final, name, value)
        applied.append(name)

    if fallback_toggle:
        final = _teams_safe_replace_assignment_preserving_layout(final, fallback_toggle, fallback_value)
        applied.append(fallback_toggle)

    for name in selected_delete:
        final = _teams_safe_remove_assignment(final, name)
        applied.append(f"delete:{name}")

    if selected_new:
        additions = []
        for name in selected_new:
            span = generated_by_name.get(name) or {}
            assignment_text = str(span.get("text") or "").strip()
            if assignment_text:
                additions.append(assignment_text)
                applied.append(f"add:{name}")
        if additions:
            final = final.rstrip() + "\n\n" + "\n\n".join(additions) + "\n"

    final = final.rstrip() + "\n"
    if _teams_safe_hcl_compare(final) == _teams_safe_hcl_compare(existing):
        raise ValueError(
            f"Terrabot could not derive a prompt-specific assignment change for {path}. "
            "No unrelated generated settings were applied."
        )

    remaining_names = set(_extract_top_level_hcl_assignment_names(final))
    required_preserved = set(existing_by_name) - {name.split(":", 1)[-1] for name in applied if name.startswith("delete:")}
    missing_preserved = sorted(required_preserved - remaining_names)
    if missing_preserved:
        raise ValueError(
            f"Safe Teams modification for {path} would remove existing assignment(s): {', '.join(missing_preserved)}."
        )

    return final, {
        "path": path,
        "kind": "hcl_assignments",
        "applied": applied,
        "ignored_generated": ignored_generated,
        "preserved_count": max(0, len(existing_by_name) - len([item for item in applied if not item.startswith("add:")])),
    }


def _teams_safe_top_level_block_spans(content: str) -> list[dict]:
    text = str(content or "").replace("\r\n", "\n")
    spans: list[dict] = []
    occurrences: dict[str, int] = {}
    for match in _top_level_tf_block_matches(text):
        if _hcl_nesting_depth_at_position(text, match.start()) != 0:
            continue
        brace_start = text.find("{", match.end() - 1)
        end = _find_balanced_curly_end(text, brace_start)
        if brace_start < 0 or end < 0:
            continue
        header = re.sub(r"\s+", " ", text[match.start():brace_start].strip())
        occurrences[header] = occurrences.get(header, 0) + 1
        key = f"{header}#{occurrences[header]}"
        spans.append({
            "key": key,
            "header": header,
            "start": match.start(),
            "end": end,
            "text": text[match.start():end],
        })
    return spans


def _teams_safe_block_relevance(block: dict, prompt: str) -> int:
    header = str((block or {}).get("header") or "")
    text = str((block or {}).get("text") or "")
    score = 0
    for term in _teams_safe_extended_modification_terms(prompt):
        normalized = str(term or "").lower()
        if normalized and normalized in f"{header}\n{text}".lower():
            score += 60
    quoted = re.findall(r'"([^"\n]+)"', header)
    score += sum(_teams_safe_identifier_score(item, prompt) for item in quoted)
    return score


def _teams_safe_merge_single_block(existing_block: str, generated_block: str, prompt: str, path: str) -> tuple[str, dict]:
    existing_open = existing_block.find("{")
    generated_open = generated_block.find("{")
    existing_close = existing_block.rfind("}")
    generated_close = generated_block.rfind("}")
    if min(existing_open, generated_open, existing_close, generated_close) < 0:
        raise ValueError(f"Terrabot could not parse the selected Terraform block in {path}.")

    existing_body = existing_block[existing_open + 1:existing_close]
    generated_body = generated_block[generated_open + 1:generated_close]
    try:
        merged_body, info = _teams_safe_patch_hcl_assignments(
            existing_body,
            generated_body,
            prompt,
            path,
        )
        closing_match = re.match(r"^[ \t]*", existing_block)
        closing_indent = closing_match.group(0) if closing_match else ""
        return (
            existing_block[:existing_open + 1]
            + merged_body.rstrip("\n")
            + f"\n{closing_indent}}}"
        ), info
    except ValueError:
        # Nested blocks are handled recursively. This allows targeted changes
        # inside lifecycle/dynamic/settings blocks without replacing the outer
        # resource or module and without losing sibling attributes.
        nested_existing = _teams_safe_top_level_block_spans(existing_body)
        nested_generated = _teams_safe_top_level_block_spans(generated_body)
        existing_map = {item["key"]: item for item in nested_existing}
        generated_map = {item["key"]: item for item in nested_generated}
        changed = [
            key for key in existing_map.keys() & generated_map.keys()
            if _teams_safe_hcl_compare(existing_map[key]["text"]) != _teams_safe_hcl_compare(generated_map[key]["text"])
        ]
        selected = sorted(
            changed,
            key=lambda key: _teams_safe_block_relevance(generated_map[key], prompt),
            reverse=True,
        )
        if not selected or _teams_safe_block_relevance(generated_map[selected[0]], prompt) <= 0:
            raise ValueError(f"Terrabot could not isolate a safe nested Terraform change in {path}.")
        selected = [selected[0]]
        body = existing_body
        applied = []
        for key in sorted(selected, key=lambda item: int(existing_map[item]["start"]), reverse=True):
            old = existing_map[key]
            new_block, nested_info = _teams_safe_merge_single_block(old["text"], generated_map[key]["text"], prompt, path)
            body = body[:int(old["start"])] + new_block + body[int(old["end"]):]
            applied.extend(nested_info.get("applied") or [old.get("header")])
        closing_match = re.match(r"^[ \t]*", existing_block)
        closing_indent = closing_match.group(0) if closing_match else ""
        return existing_block[:existing_open + 1] + body.rstrip("\n") + f"\n{closing_indent}}}", {
            "path": path,
            "kind": "nested_blocks",
            "applied": applied,
            "ignored_generated": [],
            "preserved_count": len(nested_existing) - len(selected),
        }



def _teams_all_hcl_assignment_spans(hcl_content: str) -> list[dict]:
    """Return assignment spans at any HCL nesting depth.

    Teams creation materialization normally works block-by-block, but some
    repositories keep resource collections inside ``locals`` or another
    nested object. In those files the resource-family assignment is not a
    file-level assignment, so the top-level assignment selector cannot see
    the generated sibling entry. This scanner is deliberately used only by
    the additive creation fallback below; modification/delete paths retain
    their stricter existing selectors.
    """
    text = str(hcl_content or "").replace("\r\n", "\n")
    spans: list[dict] = []
    occurrences: dict[str, int] = {}
    for match in re.finditer(
        r'(?m)^[ \t]*([A-Za-z_][A-Za-z0-9_-]*)[ \t]*=[ \t]*',
        text,
    ):
        try:
            start, end = _assignment_span_from_match(text, match)
        except Exception:
            continue
        name = str(match.group(1) or "").strip()
        if not name or end <= start:
            continue
        assignment_text = text[start:end]
        value_match = re.match(
            rf'(?s)^[ \t]*{re.escape(name)}[ \t]*=[ \t]*(.*)$',
            assignment_text,
        )
        value = str(value_match.group(1) if value_match else "").strip()
        occurrences[name] = occurrences.get(name, 0) + 1
        spans.append({
            "name": name,
            "occurrence": occurrences[name],
            "start": start,
            "end": end,
            "text": assignment_text,
            "value": value,
            "depth": _hcl_nesting_depth_at_position(text, start),
        })
    return spans


def _teams_safe_materialize_nested_creation_map_entry(
    existing_content: str,
    generated_content: str,
    prompt: str,
    path: str,
) -> tuple[str, dict] | None:
    """Disabled: Terraform semantic generation belongs exclusively to Foundry."""
    raise RuntimeError("Backend Terraform synthesis/materialization is disabled; retry through Foundry with live repository evidence.")


def _teams_safe_patch_tf_file(existing_content: str, generated_content: str, prompt: str, path: str) -> tuple[str, dict]:
    existing = str(existing_content or "").replace("\r\n", "\n")
    generated = str(generated_content or "").replace("\r\n", "\n")

    nested_creation = _teams_safe_materialize_nested_creation_map_entry(
        existing, generated, prompt, path
    )
    if nested_creation is not None:
        return nested_creation
    existing_blocks = _teams_safe_top_level_block_spans(existing)
    generated_blocks = _teams_safe_top_level_block_spans(generated)
    existing_map = {item["key"]: item for item in existing_blocks}
    generated_map = {item["key"]: item for item in generated_blocks}

    changed = [
        key for key in existing_map.keys() & generated_map.keys()
        if _teams_safe_hcl_compare(existing_map[key]["text"]) != _teams_safe_hcl_compare(generated_map[key]["text"])
    ]
    new_keys = [key for key in generated_map if key not in existing_map]
    if new_keys and not changed:
        # Append-shaped output: the agent returned the full file with every
        # existing block unchanged plus new sibling block(s). Honor the
        # agent's classification — preserve the existing file verbatim and
        # append only the new blocks. Truncation is impossible by
        # construction.
        appended = "\n\n".join(
            generated_map[key]["text"].strip("\n")
            for key in sorted(new_keys, key=lambda item: int(generated_map[item]["start"]))
        )
        final = existing.rstrip("\n") + "\n\n" + appended + "\n"
        return final, {
            "path": path,
            "kind": "agent_append",
            "applied": [str(generated_map[key].get("header") or key) for key in new_keys],
            "ignored_generated": [],
            "preserved_count": len(existing_blocks),
        }
    if not changed:
        # Some .tf files contain only root assignments. Use the same surgical
        # assignment path rather than replacing the file.
        return _teams_safe_patch_hcl_assignments(existing, generated, prompt, path)

    scored = [(key, _teams_safe_block_relevance(generated_map[key], prompt)) for key in changed]
    positive = [(key, score) for key, score in scored if score > 0]
    if positive:
        maximum = max(score for _key, score in positive)
        selected = [key for key, score in positive if score >= max(120, maximum - 40)]
    else:
        selected = changed if len(changed) == 1 else []
    if not selected:
        raise ValueError(
            f"Terrabot found multiple changed blocks in {path} but could not prove which one was requested. "
            "No broad file replacement was applied."
        )

    final = existing
    applied: list[str] = []
    patch_info: list[dict] = []
    for key in sorted(selected, key=lambda item: int(existing_map[item]["start"]), reverse=True):
        old = existing_map[key]
        merged_block, info = _teams_safe_merge_single_block(old["text"], generated_map[key]["text"], prompt, path)
        final = final[:int(old["start"])] + merged_block + final[int(old["end"]):]
        applied.append(str(old.get("header") or key))
        patch_info.append(info)

    final = final.rstrip() + "\n"
    final_headers = {item["key"] for item in _teams_safe_top_level_block_spans(final)}
    missing_headers = sorted(set(existing_map) - final_headers)
    if missing_headers:
        raise ValueError(
            f"Safe Teams modification for {path} would remove existing Terraform block(s): {', '.join(missing_headers)}."
        )
    if _teams_safe_hcl_compare(final) == _teams_safe_hcl_compare(existing):
        raise ValueError(f"Terrabot did not produce a real prompt-specific change for {path}.")

    return final, {
        "path": path,
        "kind": "terraform_blocks",
        "applied": applied,
        "ignored_generated": [item.get("header") for key, item in generated_map.items() if key not in existing_map],
        "preserved_count": max(0, len(existing_blocks) - len(selected)),
        "details": patch_info,
    }

_TEAMS_ROOT_ASSIGNMENT_RE = re.compile(r"(?m)^\s*([A-Za-z_][A-Za-z0-9_-]*)\s*=")


def _teams_safe_append_new_invocation(
    existing_content: str,
    generated_content: str,
    prompt: str,
    path: str,
) -> tuple[str, dict]:
    """Materialize a creation-by-append: preserve the existing file
    byte-for-byte and append only the genuinely new, prompt-relevant
    top-level block(s) from the generated content.

    Used for existing-invocation creation requests (e.g. adding a new ACA
    app block to aca_apps.tf). The existing file can never be truncated or
    reordered because it is copied verbatim.
    """
    existing = str(existing_content or "").replace("\r\n", "\n")
    generated = str(generated_content or "").replace("\r\n", "\n")

    if path.endswith(".tfvars"):
        # tfvars materialization: append new assignments, update changed
        # values in place, and treat already-applied state as a NO-OP —
        # never a failure. (Multi-turn flows can legitimately re-request a
        # flag that an earlier branch already set.)
        def _line_key(line: str) -> str | None:
            match = _TEAMS_ROOT_ASSIGNMENT_RE.match(line)
            return match.group(1) if match else None

        def _norm(line: str) -> str:
            return re.sub(r"\s+", " ", line).strip()

        existing_by_key: dict[str, str] = {}
        for line in existing.splitlines():
            key = _line_key(line)
            if key and key not in existing_by_key:
                existing_by_key[key] = line
        existing_keys = set(existing_by_key)

        new_lines: list[str] = []
        changed: list[tuple[str, str]] = []  # (key, generated line)
        for line in generated.splitlines():
            key = _line_key(line)
            if not key:
                continue
            if key not in existing_keys:
                if line.rstrip() not in new_lines:
                    new_lines.append(line.rstrip())
            elif _norm(existing_by_key[key]) != _norm(line):
                changed.append((key, line))

        final = existing
        applied: list[str] = []
        for key, gen_line in changed:
            value = gen_line.split("=", 1)[1].strip() if "=" in gen_line else ""
            if not value:
                continue
            final, count = re.subn(
                rf"(?m)^([ \t]*){re.escape(key)}[ \t]*=.*$",
                lambda m: f"{m.group(1)}{key} = {value}",
                final,
                count=1,
            )
            if count:
                applied.append(f"{key} = {value}")
        if new_lines:
            final = final.rstrip("\n") + "\n\n" + "\n".join(new_lines) + "\n"
            applied.extend(new_lines[:6])

        if not applied:
            # Every requested assignment already holds on this ref.
            return existing, {
                "path": path,
                "kind": "noop_already_applied",
                "applied": [],
                "ignored_generated": [],
                "preserved_count": len(existing_keys),
                "note": "requested tfvars state already present; nothing to change",
            }
        return final, {
            "path": path,
            "kind": "invocation_append_tfvars",
            "applied": applied[:8],
            "ignored_generated": [],
            "preserved_count": len(existing_keys),
        }

    existing_spans = _teams_safe_top_level_block_spans(existing)
    generated_spans = _teams_safe_top_level_block_spans(generated)
    existing_keys = {span["key"] for span in existing_spans}
    new_blocks = [span for span in generated_spans if span["key"] not in existing_keys]

    if not new_blocks:
        # The agent may have expressed the creation as a change to an
        # existing block (e.g. a for_each map entry). Fall back to the
        # surgical patcher rather than failing.
        return _teams_safe_patch_tf_file(existing, generated, prompt, path)

    relevant = [span for span in new_blocks if _teams_safe_block_relevance(span, prompt) > 0]
    if not relevant:
        # A single unambiguous new block is acceptable even without a
        # keyword hit (e.g. the prompt names the app but the block header
        # uses a normalized label).
        relevant = new_blocks if len(new_blocks) == 1 else []
    if not relevant:
        headers = ", ".join(str(span.get("header") or span.get("key")) for span in new_blocks[:5])
        raise ValueError(
            f"Invocation creation for {path} produced {len(new_blocks)} new "
            f"blocks ({headers}) but none could be matched to the request. "
            "Nothing was appended."
        )

    appended = "\n\n".join(span["text"].strip("\n") for span in relevant)
    final = existing.rstrip("\n") + "\n\n" + appended + "\n"
    return final, {
        "path": path,
        "kind": "invocation_append",
        "applied": [str(span.get("header") or span.get("key")) for span in relevant],
        "ignored_generated": [
            str(span.get("header") or span.get("key"))
            for span in new_blocks
            if span not in relevant
        ],
        "preserved_count": len(existing_spans),
    }

def _teams_generated_preserves_existing_lines(existing: str, generated: str) -> bool:
    """True when every non-empty line of the existing file appears, in order,
    in the generated content (whitespace-normalized). This proves the
    generated full file is purely additive: nothing existing was dropped,
    changed, or reordered — so committing it verbatim cannot destroy code."""
    def _norm(line: str) -> str:
        return re.sub(r"\s+", " ", str(line or "")).strip()

    generated_lines = [_norm(line) for line in str(generated or "").splitlines()]
    cursor = 0
    for raw in str(existing or "").splitlines():
        line = _norm(raw)
        if not line:
            continue
        while cursor < len(generated_lines) and generated_lines[cursor] != line:
            cursor += 1
        if cursor >= len(generated_lines):
            return False
        cursor += 1
    return True


def _teams_safe_materialize_modification(
    existing: str,
    generated: str,
    prompt: str,
    path: str,
    invocation_creation: bool = False,
) -> tuple[str, dict]:
    """Disabled: Terraform semantic generation belongs exclusively to Foundry."""
    raise RuntimeError("Backend Terraform synthesis/materialization is disabled; retry through Foundry with live repository evidence.")


def _teams_safe_materialize_modification_strict(
    existing: str,
    generated: str,
    prompt: str,
    path: str,
    invocation_creation: bool = False,
) -> tuple[str, dict]:
    """Disabled: Terraform semantic generation belongs exclusively to Foundry."""
    raise RuntimeError("Backend Terraform synthesis/materialization is disabled; retry through Foundry with live repository evidence.")


def _teams_safe_backend_analysis(
    agent_result: dict,
    prompt: str,
    cloud: str,
    repo_target: str,
    workflow: str,
    source_branch: str,
    patch_details: list[dict],
) -> tuple[str, list[str]]:
    context = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    repo = github_repo_for_cloud(cloud, repo_target=repo_target, workflow=workflow)
    selected_context = _get_backend_existing_infra_context(context.get("retrieved_value_context") or [])
    scope_root = str(selected_context.get("scope_root") or context.get("target_scope_root") or "").strip()
    scope_reason = str(selected_context.get("scope_reason") or context.get("target_scope_reason") or "").strip()

    source_paths: list[str] = []
    for value in agent_result.get("source_paths_used") or []:
        path = str(value or "").strip()
        if path and path not in source_paths:
            source_paths.append(path)
    for item in selected_context.get("matched_files") or []:
        path = str((item or {}).get("path") or "").strip()
        if path and path not in source_paths:
            source_paths.append(path)
    for detail in patch_details:
        path = str(detail.get("path") or "").strip()
        if path and path not in source_paths:
            source_paths.append(path)

    lines = [
        f"Repository: `{GITHUB_OWNER}/{repo}`; live GitHub source branch: `{source_branch}`.",
        f"Workflow: `{workflow or 'terraform change'}`; intent was inferred from the user prompt as a {cloud.upper()} infrastructure change.",
    ]
    if scope_root:
        lines.append(f"Target scope: `{scope_root}` ({scope_reason or 'resolved from the prompt'}).")
    if selected_context.get("selected_path"):
        lines.append(f"Target file: `{selected_context.get('selected_path')}` selected from live repository evidence.")
    for detail in patch_details[:3]:
        applied = [str(item) for item in detail.get("applied") or []]
        preserved = int(detail.get("preserved_count") or 0)
        lines.append(
            f"Applied change: `{detail.get('path')}` — {', '.join(applied) if applied else 'requested edit'}; "
            f"preserved {preserved} unrelated existing assignment/block(s)."
        )
        ignored = [str(item) for item in detail.get("ignored_generated") or [] if str(item)]
        if ignored:
            lines.append(
                "Safety filter: ignored unrelated generated additions/replacements: "
                + ", ".join(f"`{item}`" for item in ignored[:6])
                + "."
            )
    if source_paths:
        lines.append("Evidence: " + ", ".join(f"`{path}`" for path in source_paths[:6]) + ".")

    original_analysis = str(agent_result.get("analysis") or "").strip()
    for line in original_analysis.splitlines():
        cleaned = line.strip()
        if cleaned and cleaned not in lines and len(lines) < 10:
            lines.append(cleaned)
    return "\n".join(lines[:10]), source_paths


def _validate_new_module_variable_roots_are_provisioned(
    files: list, existing_content_by_path: dict
) -> None:
    """Catch the complementary real failure to the one above: a newly-added
    module block correctly wired to its OWN new, dedicated object variable
    (e.g. `var.storage_account_storageaccount1.*`, not an existing sibling's)
    — but that variable is never actually declared in variables.tf, never
    actually assigned a value in any tfvars file, and the response's
    analysis merely SAYS those files were (or will be) written without
    files[] actually containing them.

    This produces a branch that "looks" complete (one file changed, valid
    HCL, passes every structural check) but references an undeclared,
    unassigned variable — terraform validate would fail immediately. Raise
    ValueError so this routes through the self-correction loop and the
    complete write-set (definition + declaration + values) gets pushed
    together, in one response, instead of piecemeal across turns.
    """
    new_object_roots: set = set()
    root_to_context: dict = {}
    for f in files or []:
        if not isinstance(f, dict):
            continue
        path = f.get("path") or f.get("filename") or ""
        content = f.get("content") or ""
        if not path or not content or f.get("operation") not in ("modify", "create"):
            continue
        existing = existing_content_by_path.get(path, "") or ""
        for label in _teams_find_new_module_labels(existing, content):
            block = _teams_extract_module_block(content, label)
            if not block:
                continue
            referenced_roots = set(re.findall(r"var\.([A-Za-z0-9_]+)\.", block))
            label_tokens = [t for t in re.split(r"[_]+", label) if len(t) > 2]
            for root in referenced_roots:
                if root in existing:
                    continue  # not a newly-introduced root; pre-existing already
                if any(tok in root for tok in label_tokens):
                    new_object_roots.add(root)
                    root_to_context[root] = (label, path)

    if not new_object_roots:
        return

    all_touched_content = "\n".join(
        (f.get("content") or "")
        for f in (files or [])
        if isinstance(f, dict) and f.get("content")
    )
    all_existing_content = "\n".join(existing_content_by_path.values())

    for root in new_object_roots:
        declared = bool(
            re.search(rf'variable\s+"{re.escape(root)}"\s*\{{', all_touched_content)
            or re.search(rf'variable\s+"{re.escape(root)}"\s*\{{', all_existing_content)
        )
        assigned = bool(
            re.search(rf'^\s*{re.escape(root)}\s*=', all_touched_content, re.MULTILINE)
            or re.search(rf'^\s*{re.escape(root)}\s*=', all_existing_content, re.MULTILINE)
        )
        if declared and assigned:
            continue
        label, path = root_to_context[root]
        missing = []
        if not declared:
            missing.append("a `variable \"" + root + "\"` declaration in variables.tf")
        if not assigned:
            missing.append("a concrete `" + root + " = { ... }` value assignment in the environment's tfvars/values file")
        raise ValueError(
            f"New module block '{label}' in {path} references var.{root}.* — its own "
            "new, dedicated object variable — but this response is missing "
            + " and ".join(missing) + ". A module block referencing an undeclared or "
            "unassigned variable fails terraform validate immediately even though the "
            "HCL itself is well-formed. The complete write-set (the module block, its "
            "variables.tf declaration, and its tfvars value assignment) must be pushed "
            "together in this same response — never split across turns, and never "
            "described as done in analysis/summary unless it is actually present in "
            "files[]."
        )


def _teams_find_new_module_labels(existing: str, generated: str) -> list:
    """Module labels present in `generated` that are not present in `existing`
    — i.e. newly-appended module blocks for this response."""
    existing_labels = set(re.findall(r'module\s+"([A-Za-z0-9_]+)"\s*\{', existing or ""))
    generated_labels = re.findall(r'module\s+"([A-Za-z0-9_]+)"\s*\{', generated or "")
    seen = set()
    out = []
    for label in generated_labels:
        if label not in existing_labels and label not in seen:
            seen.add(label)
            out.append(label)
    return out


def _teams_extract_module_block(content: str, label: str) -> str:
    """Return the full text of `module "<label>" { ... }` (braces balanced)."""
    marker = f'module "{label}" {{' if f'module "{label}" {{' in content else None
    if marker is None:
        # Tolerate a space-insensitive variant, e.g. no space before the brace.
        m = re.search(rf'module\s+"{re.escape(label)}"\s*\{{', content)
        if not m:
            return ""
        start = m.start()
        brace_start = m.end() - 1
    else:
        start = content.find(marker)
        brace_start = start + len(marker) - 1
    depth = 0
    for j in range(brace_start, len(content)):
        if content[j] == "{":
            depth += 1
        elif content[j] == "}":
            depth -= 1
            if depth == 0:
                return content[start:j + 1]
    return content[start:]


def _derive_expected_variable_name(label: str, existing: str) -> Optional[str]:
    """Learn the module-label -> dedicated-object-variable naming rule this
    repo demonstrates (e.g. `module "azurerm_storage_account_zrs"` reads
    `var.storage_account_zrs.*` => strip the "azurerm_" prefix), then apply
    that exact rule to `label` to get the variable name a NEW instance of
    this resource family should use. Returns None if no sibling block in
    `existing` demonstrates a usable rule."""
    for m in re.finditer(r'module\s+"([A-Za-z0-9_]+)"\s*\{', existing or ""):
        sib_label = m.group(1)
        if sib_label == label:
            continue
        sib_block = _teams_extract_module_block(existing, sib_label)
        if not sib_block:
            continue
        for root in re.findall(r"var\.([A-Za-z0-9_]+)\.", sib_block):
            if root and sib_label.endswith(root) and sib_label != root:
                prefix = sib_label[: len(sib_label) - len(root)]
                if prefix and label.startswith(prefix):
                    return label[len(prefix):]
    return None


def _validate_azure_object_backed_new_module_wiring(files: list, existing_content_by_path: dict) -> None:
    """Catch the specific real failure: a brand-new module block (a genuinely
    new resource instance, e.g. `module "azurerm_storage_account_x"`) whose
    every input is wired to an EXISTING sibling's object variable
    (var.storage_account_grs.* etc.) instead of a new, dedicated object
    variable for this instance.

    That shape compiles and passes every other guardrail (it preserves all
    existing content, adds no unrelated blocks, is valid HCL) but is
    semantically wrong: the "new" resource would silently share every
    setting with, and offer no independent configuration from, an unrelated
    existing resource, and nothing was actually added to the values file for
    it. Raise ValueError so the self-correction loop sends this back to the
    agent with the exact fix instead of committing it.

    Detection is exact, not fuzzy: it learns the label->variable naming rule
    from an existing sibling module block (e.g. strip "azurerm_") and checks
    whether the new block references that EXACT derived name. A prior
    substring/token-overlap heuristic here could false-negative when the new
    and old names share generic words (e.g. both containing "storage" and
    "account") — this exact-prefix derivation does not have that failure
    mode.
    """
    for f in files or []:
        if not isinstance(f, dict):
            continue
        path = f.get("path") or f.get("filename") or ""
        content = f.get("content") or ""
        if not path or not content or f.get("operation") not in ("modify", "create"):
            continue
        existing = existing_content_by_path.get(path, "") or ""
        for label in _teams_find_new_module_labels(existing, content):
            block = _teams_extract_module_block(content, label)
            if not block:
                continue
            referenced_roots = set(re.findall(r"var\.([A-Za-z0-9_]+)\.", block))
            if not referenced_roots:
                continue

            expected = _derive_expected_variable_name(label, existing)
            if expected and expected in referenced_roots:
                continue  # correctly wired to its own dedicated variable

            # Fallback heuristic only when no sibling rule could be derived
            # (rare — e.g. this is the very first module block of its kind).
            if expected is None:
                label_tokens = [t for t in re.split(r"[_]+", label) if len(t) > 2]
                has_dedicated_root = any(
                    any(tok in root for tok in label_tokens) and root not in existing
                    for root in referenced_roots
                )
                if has_dedicated_root:
                    continue

            for root in referenced_roots:
                # The root is an existing variable AND it already backs some
                # OTHER, differently-labeled module block in the pre-existing
                # file content — the smoking gun for "reused someone else's
                # object instead of creating a new one".
                if re.search(rf"var\.{re.escape(root)}\b", existing) and re.search(
                    rf'module\s+"(?!{re.escape(label)}")[A-Za-z0-9_]+"\s*\{{[^{{}}]*var\.{re.escape(root)}\b',
                    existing,
                    re.DOTALL,
                ):
                    expected_note = (
                        f" (expected var.{expected}.* based on this repo's own "
                        f"label-to-variable naming rule)" if expected else ""
                    )
                    raise ValueError(
                        f"New module block '{label}' in {path} is wired entirely to "
                        f"var.{root}.* — an existing sibling module's object variable — "
                        f"instead of a new, dedicated object variable for this instance"
                        f"{expected_note}. This makes the new resource silently share "
                        "every setting with, and have no independent configuration "
                        "from, an unrelated existing resource, and nothing was added to "
                        "the values file for it. Fix: create a new object variable in "
                        "variables.tf matching this module's own name (copy the type "
                        f"shape from var.{root} exactly), add a new object assignment "
                        f"for it to the environment's values/tfvars file (clone concrete "
                        f"values from var.{root}'s existing assignment, not a reference "
                        "to it), and wire every input in this module block to that new "
                        f"variable instead of var.{root}."
                    )



def _strip_hcl_strings_and_comments(content: str) -> str:
    """Blank out string-literal and comment contents so bracket-balance
    checking never gets confused by a '{' or '#' that only appears inside a
    string or a comment. Length-preserving (replaces with spaces) so nothing
    else about the content shifts."""
    out = []
    i = 0
    n = len(content)
    in_string = False
    while i < n:
        c = content[i]
        if in_string:
            if c == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            out.append(" " if c != "\n" else "\n")
            if c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
            out.append(" ")
            i += 1
            continue
        if c == "#" or (c == "/" and i + 1 < n and content[i + 1] == "/"):
            while i < n and content[i] != "\n":
                out.append(" ")
                i += 1
            continue
        if c == "/" and i + 1 < n and content[i + 1] == "*":
            out.append("  ")
            i += 2
            while i + 1 < n and not (content[i] == "*" and content[i + 1] == "/"):
                out.append(" " if content[i] != "\n" else "\n")
                i += 1
            if i + 1 < n:
                out.append("  ")
                i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _validate_hcl_content_complete(path: str, content: str) -> None:
    """Reject generated .tf/.tfvars content whose brackets don't balance —
    the concrete, mechanical signature of truncated-mid-generation output
    (e.g. a response that cuts off after `storage_account_x = {` with no
    closing brace). This is checked before commit so incomplete Terraform
    can never reach the branch; it routes into the self-correction loop
    instead."""
    if not path or not content:
        return
    if not (path.endswith(".tf") or path.endswith(".tfvars")):
        return
    stripped = _strip_hcl_strings_and_comments(content)
    pairs = {"{": "}", "[": "]", "(": ")"}
    closers = {v: k for k, v in pairs.items()}
    stack = []
    for ch in stripped:
        if ch in pairs:
            stack.append(ch)
        elif ch in closers:
            if not stack or stack[-1] != closers[ch]:
                raise ValueError(
                    f"Generated content for {path} is not complete, valid Terraform: "
                    f"found an unexpected closing '{ch}' with no matching open bracket. "
                    "This must not be pushed — regenerate the FULL, complete file."
                )
            stack.pop()
    if stack:
        raise ValueError(
            f"Generated content for {path} is incomplete: {len(stack)} open bracket(s) "
            f"({''.join(stack)}) were never closed before the end of the file. This is "
            "the signature of output truncated mid-generation. This must not be pushed — "
            "regenerate the FULL, complete file content, including every closing brace, "
            "for every block you started."
        )


def _teams_find_missing_existing_lines(existing: str, generated: str, limit: int = 5) -> list:
    """Best-effort list of existing lines that do NOT appear, unchanged and
    in order, inside `generated` — used to build a specific error message
    for _validate_teams_modify_no_unrequested_changes."""
    def _norm(line: str) -> str:
        return re.sub(r"\s+", " ", str(line or "")).strip()

    generated_lines = [_norm(line) for line in str(generated or "").splitlines()]
    missing: list = []
    cursor = 0
    for raw in str(existing or "").splitlines():
        line = _norm(raw)
        if not line:
            continue
        start_cursor = cursor
        while cursor < len(generated_lines) and generated_lines[cursor] != line:
            cursor += 1
        if cursor >= len(generated_lines):
            missing.append(raw.strip())
            cursor = start_cursor
            if len(missing) >= limit:
                break
            continue
        cursor += 1
    return missing


def _validate_teams_modify_no_unrequested_changes(files: list, existing_content_by_path: dict) -> None:
    """Universal (all clouds) guard: for every "modify" file that is NOT an
    explicit in_place edit, every existing line must still appear, unchanged
    and in order, in the generated content. Catches the real failure where a
    full-file regeneration silently altered unrelated existing values
    (changed prefixes, retention days, SKU names, zone numbers, etc.) that
    the user never asked to touch — valid HCL, wrong content. Routes into
    the self-correction loop instead of reaching the user or the branch."""
    for f in files or []:
        if not isinstance(f, dict):
            continue
        path = f.get("path") or f.get("filename") or ""
        content = f.get("content") or ""
        if not path or not content or f.get("operation") != "modify" or f.get("in_place"):
            continue
        existing = existing_content_by_path.get(path, "")
        if not existing:
            continue
        if not _teams_generated_preserves_existing_lines(existing, content):
            missing = _teams_find_missing_existing_lines(existing, content, limit=5)
            sample = "; ".join(m[:80] for m in missing[:3]) or "unspecified existing lines"
            raise ValueError(
                f"Generated modification for {path} altered, removed, or reordered "
                f"existing content the user did not ask to change (e.g.: {sample}). "
                "A pure addition must keep every existing line byte-for-byte untouched; "
                "regenerate so every unrelated existing line is preserved exactly and "
                "only the specifically requested addition/change is applied."
            )



def _teams_normalized_repo_path(path: str) -> str:
    return str(path or "").replace("\\", "/").strip().strip("/")


def _teams_module_source_literal(module_block: str) -> str:
    match = re.search(
        r'(?m)^\s*source\s*=\s*"([^"]+)"\s*$',
        module_block or "",
    )
    return match.group(1).strip() if match else ""


def _teams_object_backed_sibling_for_new_module(
    existing_content: str,
    new_module_block: str,
    new_module_label: str,
) -> tuple[str, str, str]:
    """Return (sibling_block, sibling_object_root, module_source).

    The selected resource-family file is authoritative. Prefer the closest
    preceding object-backed sibling that uses the same module source; this is
    the repository's nearest concrete convention and avoids mixing ZRS/GRS or
    another sibling family by guesswork.
    """
    existing = str(existing_content or "").replace("\r\n", "\n")
    new_source = _teams_module_source_literal(new_module_block)
    expected_root = (
        _derive_expected_variable_name(new_module_label, existing)
        or _tfvars_object_name_from_module_name(new_module_label)
    )
    expected_tokens = [token for token in expected_root.split("_") if token]

    candidates: list[tuple[int, int, str, str, str]] = []
    for match in re.finditer(r'module\s+"([A-Za-z0-9_]+)"\s*\{', existing):
        label = match.group(1)
        block = _teams_extract_module_block(existing, label)
        object_root = _dominant_object_var_root(block)
        if not block or not object_root:
            continue
        source = _teams_module_source_literal(block)
        score = 0
        if new_source and source == new_source:
            score += 100_000
        sibling_tokens = [token for token in object_root.split("_") if token]
        score += 100 * len(set(expected_tokens) & set(sibling_tokens))
        common_prefix = 0
        for left, right in zip(expected_tokens, sibling_tokens):
            if left != right:
                break
            common_prefix += 1
        score += common_prefix * 1_000
        # For equally valid siblings, the last block is the physically nearest
        # template to a newly appended invocation.
        candidates.append((score, match.start(), block, object_root, source))

    if not candidates:
        return "", "", ""
    _score, _position, block, object_root, source = max(
        candidates,
        key=lambda item: (item[0], item[1]),
    )
    return block, object_root, source or new_source


def _teams_clone_object_backed_module_invocation(
    sibling_module_block: str,
    target_module_label: str,
    source_object_root: str,
    target_object_root: str,
) -> str:
    """Clone the nearest sibling invocation byte-for-byte in repo style.

    Only the module label and the dedicated object root change. This preserves
    comments, blank-line grouping, constant inputs, source pinning, ordering,
    and alignment exactly as the live repository demonstrates them.
    """
    block = str(sibling_module_block or "").replace("\r\n", "\n").rstrip()
    if not block:
        return ""
    block = re.sub(
        r'(?m)^(\s*module\s+")[^"]+("\s*\{)',
        lambda match: f'{match.group(1)}{target_module_label}{match.group(2)}',
        block,
        count=1,
    )
    block = _rewrite_var_root_reference(
        block,
        source_object_root,
        target_object_root,
    )
    return block.rstrip()

def _teams_clone_variable_declaration(
    source_declaration: str,
    source_name: str,
    target_name: str,
) -> str:
    source_name = _terraform_safe_variable_name(source_name)
    target_name = _terraform_safe_variable_name(target_name)
    declaration = str(source_declaration or "").replace("\r\n", "\n").strip()
    if not declaration or not source_name or not target_name:
        return ""
    declaration = re.sub(
        rf'(?m)^(\s*variable\s+"){re.escape(source_name)}("\s*\{{)',
        rf'\1{target_name}\2',
        declaration,
        count=1,
    )
    declaration = re.sub(
        rf'\bvar\.{re.escape(source_name)}\b',
        f"var.{target_name}",
        declaration,
    )
    if not _extract_tf_variable_block(declaration, target_name):
        raise ValueError(
            f'Could not clone a complete variable "{target_name}" declaration '
            f'from variable "{source_name}".'
        )
    return declaration.rstrip()


def _teams_append_repo_style_block(existing_content: str, block: str) -> str:
    existing = str(existing_content or "").replace("\r\n", "\n").rstrip("\n")
    addition = str(block or "").replace("\r\n", "\n").strip("\n")
    if not addition:
        return existing + "\n" if existing else ""
    if addition in existing:
        return existing + "\n"
    if not existing:
        return addition + "\n"
    return existing + "\n\n" + addition + "\n"


def _teams_append_repo_style_tfvars_assignment(
    existing_content: str,
    assignment_name: str,
    assignment_value: str,
) -> str:
    existing = str(existing_content or "").replace("\r\n", "\n")
    name = _terraform_safe_variable_name(assignment_name)
    value = str(assignment_value or "").strip()
    if not name or not value:
        return existing.rstrip("\n") + "\n"
    if _has_top_level_tfvars_assignment(existing, name):
        return existing.rstrip("\n") + "\n"
    return _teams_append_repo_style_block(existing, f"{name} = {value}")


def _teams_upsert_materialized_file(
    files: list[dict],
    path: str,
    content: str,
    operation: str = "modify",
) -> None:
    normalized = _teams_normalized_repo_path(path)
    final_content = str(content or "").replace("\r\n", "\n").rstrip("\n") + "\n"
    for file_data in files:
        if not isinstance(file_data, dict):
            continue
        current = _teams_normalized_repo_path(
            file_data.get("path") or file_data.get("filename") or ""
        )
        if current != normalized:
            continue
        file_data["filename"] = normalized
        file_data.pop("path", None)
        file_data["content"] = final_content
        file_data["operation"] = operation
        file_data["in_place"] = False
        return
    files.append({
        "filename": normalized,
        "content": final_content,
        "operation": operation,
        "in_place": False,
    })


def _teams_live_content_for_materialization(
    cloud: str,
    path: str,
    source_branch: str,
    repo_target: str,
    workflow: str,
) -> str:
    try:
        return github_get_file_content(
            cloud,
            path,
            source_branch,
            repo_target=repo_target,
            workflow=workflow,
        ) or ""
    except Exception:
        return ""


def _teams_azure_creation_evidence_paths(
    prompt: str,
    context: dict,
    source_branch: str,
    repo_target: str,
    workflow: str,
) -> tuple[list[str], list[str]]:
    merged = _teams_collect_backend_env_context(
        context.get("retrieved_value_context") or []
    )
    environment_entries = list(merged.get("environment_files") or [])
    companion_paths = list(merged.get("companion_write_paths") or [])

    # Refresh the exact target environment from the same branch used for the
    # commit. Cached evidence is bounded and can omit the end of a large file.
    try:
        located_entries, located_paths, _debug = _teams_locate_environment_value_files(
            prompt,
            "azure",
            repo_target,
            workflow,
            source_branch,
        )
    except Exception:
        located_entries, located_paths = [], []
    environment_entries.extend(
        entry for entry in located_entries if isinstance(entry, dict)
    )
    companion_paths.extend(located_paths or [])

    value_paths: list[str] = []
    variable_paths: list[str] = []
    for entry in environment_entries:
        path = _teams_normalized_repo_path((entry or {}).get("path") or "")
        if path.endswith((".tfvars", ".tfvars.json")) and path not in value_paths:
            value_paths.append(path)
        if path.endswith("variables.tf") and path not in variable_paths:
            variable_paths.append(path)
    for raw_path in companion_paths:
        path = _teams_normalized_repo_path(raw_path)
        if path.endswith((".tfvars", ".tfvars.json")) and path not in value_paths:
            value_paths.append(path)
        if path.endswith("variables.tf") and path not in variable_paths:
            variable_paths.append(path)
    return value_paths, variable_paths


def _teams_pick_object_values_file(
    candidate_paths: list[str],
    source_object_root: str,
    source_branch: str,
    repo_target: str,
    workflow: str,
) -> tuple[str, str, str]:
    basename_priority = {
        "hub.tfvars": 3_000,
        "tier.tfvars": 2_000,
        "common.tfvars": 1_000,
    }
    ranked: list[tuple[int, int, str, str, str]] = []
    for index, path in enumerate(candidate_paths):
        content = _teams_live_content_for_materialization(
            "azure", path, source_branch, repo_target, workflow
        )
        if not content:
            continue
        source_value = _extract_hcl_assignment_value(content, source_object_root)
        if not source_value:
            continue
        basename = path.rsplit("/", 1)[-1].lower()
        score = 100_000 + basename_priority.get(basename, 0)
        ranked.append((score, -index, path, content, source_value))
    if not ranked:
        return "", "", ""
    _score, _order, path, content, source_value = max(ranked)
    return path, content, source_value


def _teams_pick_object_variables_file(
    selected_definition_path: str,
    candidate_paths: list[str],
    source_object_root: str,
    source_branch: str,
    repo_target: str,
    workflow: str,
) -> tuple[str, str, str]:
    selected_dir = (
        selected_definition_path.rsplit("/", 1)[0]
        if "/" in selected_definition_path
        else ""
    )
    preferred = (
        f"{selected_dir}/variables.tf" if selected_dir else "variables.tf"
    )
    paths: list[str] = []
    for path in [preferred, *candidate_paths, "variables.tf"]:
        normalized = _teams_normalized_repo_path(path)
        if normalized and normalized not in paths:
            paths.append(normalized)

    ranked: list[tuple[int, int, str, str, str]] = []
    for index, path in enumerate(paths):
        content = _teams_live_content_for_materialization(
            "azure", path, source_branch, repo_target, workflow
        )
        if not content:
            continue
        declaration = _extract_tf_variable_block(content, source_object_root)
        if not declaration:
            continue
        score = 100_000
        if path == preferred:
            score += 10_000
        ranked.append((score, -index, path, content, declaration))
    if not ranked:
        return "", "", ""
    _score, _order, path, content, declaration = max(ranked)
    return path, content, declaration


def _teams_prompt_object_overrides(
    prompt: str,
    sibling_module_block: str,
    source_object_root: str,
    retrieved_value_context: list | None = None,
) -> dict[str, str]:
    prompt_text = str(prompt or "")
    explicit = dict(_user_selected_tfvars_assignments(retrieved_value_context))
    explicit.update(_extract_tfvars_assignments_from_text(prompt_text))

    # The generic parser expects assignment-oriented input. Creation prompts
    # often embed overrides in prose on the same line, for example
    # "create ... account_replication = \"GRS\"". Capture those scalar
    # assignments without interpreting arbitrary prose as values.
    scalar_re = re.compile(
        r'\b([A-Za-z_][A-Za-z0-9_]*)\s*(?:=|:)\s*'
        r'("(?:\\.|[^"\\])*"|true|false|null|-?\d+(?:\.\d+)?)',
        re.IGNORECASE,
    )
    for match in scalar_re.finditer(prompt_text):
        explicit.setdefault(match.group(1), match.group(2))

    overrides = _user_assignments_with_object_field_aliases(
        explicit,
        {"matched_module_block": sibling_module_block},
        source_object_root=source_object_root,
    )

    # Apply an explicitly named resource to the sibling's object-backed name
    # field when that mapping is demonstrated by the module invocation. Shared
    # names such as var.hub_name are intentionally excluded because they do not
    # come from the sibling object root.
    requested_name = _teams_requested_resource_name(prompt_text)
    if requested_name:
        for assignment in _extract_top_level_module_assignments(sibling_module_block):
            key = str(assignment.get("key") or "")
            value = str(assignment.get("value") or "")
            field = _module_object_field_from_pattern_expression(
                value,
                source_object_root,
            )
            if not field:
                continue
            if key == "name" or key.endswith("_name") or field == "name" or field.endswith("_name"):
                overrides.setdefault(field, json.dumps(requested_name))

    return overrides



def _teams_common_module_label_prefix(labels: list[str]) -> str:
    """Return the stable underscore-delimited prefix shared by sibling labels."""
    clean = [
        _terraform_safe_variable_name(label)
        for label in (labels or [])
        if _terraform_safe_variable_name(label)
    ]
    if not clean:
        return ""
    token_lists = [value.split("_") for value in clean]
    common: list[str] = []
    for parts in zip(*token_lists):
        if len(set(parts)) != 1:
            break
        common.append(parts[0])
    if not common:
        return ""
    return "_".join(common) + "_"


def _teams_synthesize_azure_object_backed_creation_draft(
    prompt: str,
    retrieved_value_context: list | None,
    workflow: str,
) -> dict | None:
    """Disabled: Terraform semantic generation belongs exclusively to Foundry."""
    raise RuntimeError("Backend Terraform synthesis/materialization is disabled; retry through Foundry with live repository evidence.")

def _teams_materialize_azure_object_backed_creation_stage1(
    transformed: dict,
    safe_files: list[dict],
    patch_details: list[dict],
    prompt: str,
    context: dict,
    source_branch: str,
    repo_target: str,
    workflow: str,
) -> list[dict]:
    """Disabled: Terraform semantic generation belongs exclusively to Foundry."""
    raise RuntimeError("Backend Terraform synthesis/materialization is disabled; retry through Foundry with live repository evidence.")
_teams_materialize_azure_object_backed_creation = _teams_materialize_azure_object_backed_creation_stage1


def _validate_azure_object_backed_three_file_write_set(
    files: list,
    existing_content_by_path: dict,
) -> None:
    """Require the complete object-backed Azure creation write-set.

    For every new module whose nearest sibling is backed by an object
    variable, verify that the new block mirrors that sibling's argument order,
    uses a dedicated object root, has no placeholders, and that the same
    response carries both the matching variables.tf declaration and a
    concrete tfvars assignment with the sibling's field shape.
    """
    touched = [item for item in (files or []) if isinstance(item, dict)]
    touched_blob = "\n".join(str(item.get("content") or "") for item in touched)

    for file_data in touched:
        path = _teams_normalized_repo_path(
            file_data.get("path") or file_data.get("filename") or ""
        )
        content = str(file_data.get("content") or "")
        if not path.endswith(".tf") or path.endswith("variables.tf"):
            continue
        existing = str(existing_content_by_path.get(path) or "")
        for label in _teams_find_new_module_labels(existing, content):
            block = _teams_extract_module_block(content, label)
            sibling, source_root, source = _teams_object_backed_sibling_for_new_module(
                existing,
                block,
                label,
            )
            if not sibling or not source_root:
                continue
            target_root = (
                _derive_expected_variable_name(label, existing)
                or _tfvars_object_name_from_module_name(label)
            )
            if not target_root:
                continue
            if "__FILL__" in block:
                raise ValueError(
                    f"New object-backed module '{label}' in {path} contains "
                    "__FILL__ placeholders in the definition file."
                )
            if _teams_module_source_literal(block) != source:
                raise ValueError(
                    f"New object-backed module '{label}' in {path} does not "
                    "use the nearest sibling's exact module source."
                )
            expected_block = _teams_clone_object_backed_module_invocation(
                sibling_module_block=sibling,
                target_module_label=label,
                source_object_root=source_root,
                target_object_root=target_root,
            )
            if block.strip() != expected_block.strip():
                raise ValueError(
                    f"New object-backed module '{label}' in {path} does not "
                    "match the nearest sibling's exact repository structure, "
                    "comments, grouping, ordering, or formatting."
                )
            referenced_roots = set(re.findall(r"var\.([A-Za-z0-9_]+)\.", block))
            if target_root not in referenced_roots:
                raise ValueError(
                    f"New object-backed module '{label}' in {path} must use "
                    f"its dedicated var.{target_root}.* object."
                )
            if not re.search(
                rf'variable\s+"{re.escape(target_root)}"\s*\{{',
                touched_blob,
            ):
                raise ValueError(
                    f"New object-backed module '{label}' is missing the "
                    f'variable "{target_root}" declaration in the same write-set.'
                )

            target_assignment = ""
            target_assignment_path = ""
            for candidate in touched:
                candidate_path = _teams_normalized_repo_path(
                    candidate.get("path") or candidate.get("filename") or ""
                )
                if not candidate_path.endswith((".tfvars", ".tfvars.json")):
                    continue
                candidate_value = _extract_hcl_assignment_value(
                    str(candidate.get("content") or ""),
                    target_root,
                )
                if candidate_value:
                    target_assignment = candidate_value
                    target_assignment_path = candidate_path
                    break
            if not target_assignment:
                raise ValueError(
                    f"New object-backed module '{label}' is missing the concrete "
                    f"{target_root} assignment in the target environment's "
                    "tfvars file in the same write-set."
                )
            if "__FILL__" in target_assignment or re.search(
                r"\bvar\.", target_assignment
            ):
                raise ValueError(
                    f"The {target_root} assignment in {target_assignment_path} "
                    "must contain concrete cloned values, not placeholders or "
                    "references to another object."
                )

            source_assignment = ""
            for candidate in touched:
                candidate_path = _teams_normalized_repo_path(
                    candidate.get("path") or candidate.get("filename") or ""
                )
                if not candidate_path.endswith((".tfvars", ".tfvars.json")):
                    continue
                source_assignment = _extract_hcl_assignment_value(
                    str(existing_content_by_path.get(candidate_path) or ""),
                    source_root,
                )
                if source_assignment:
                    break
            if source_assignment:
                source_fields = _top_level_tfvars_assignment_field_names(
                    source_assignment
                )
                target_fields = _top_level_tfvars_assignment_field_names(
                    target_assignment
                )
                if source_fields != target_fields:
                    raise ValueError(
                        f"The concrete {target_root} object does not match the "
                        f"nearest sibling {source_root} field shape."
                    )

def commit_terraform_files_to_branch_for_teams_stage1(agent_result: dict, prompt: str, thread_id: str) -> dict:
    """Apply Teams modifications surgically, then use the existing branch writer."""
    context = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    _teams_diag_log(
        "agent_result_received",
        thread=thread_id,
        cloud=agent_result.get("cloud"),
        workflow=agent_result.get("workflow"),
        files=[
            f"{(f or {}).get('path') or (f or {}).get('filename')}:{(f or {}).get('operation')}"
            for f in (agent_result.get("files") or [])
            if isinstance(f, dict)
        ],
    )
    _selected_infra_context = _get_backend_existing_infra_context(
        context.get("retrieved_value_context") or []
    )
    # Discovery metadata only — never derived from prompt wording. The
    # agent's returned file shape (Block 4c) decides append vs edit; this
    # flag additionally permits new-file creation for backend-discovered
    # invocation targets.
    # IMPORTANT: also check the prompt is not a disable/modification so
    # stale invocation_creation state from a prior creation turn does not
    # trigger the flag-enable guarantee on a subsequent disable/update request.
    _is_disable_or_modify = bool(re.search(
        r"\b(?:disable|turn\s+off|switch\s+off|deactivate|remove|update|modify|change|resize|scale)\b",
        str(prompt or "").lower(),
    ))
    invocation_creation = bool(
        not _is_disable_or_modify
        and (
            _selected_infra_context.get("invocation_generation")
            or _selected_infra_context.get("operation") == "existing_invocation_creation"
        )
    )
    cloud = normalize_cloud(agent_result["cloud"])
    workflow = str(agent_result.get("workflow") or "").strip()
    repo_target = normalize_repo_target(cloud, str(agent_result.get("repo_target") or ""), workflow)
    transformed = dict(agent_result)
    transformed["files"] = [dict(item) for item in agent_result.get("files") or [] if isinstance(item, dict)]
    patch_details: list[dict] = []

    base_branch = github_resolve_base_branch_for_cloud(cloud, repo_target=repo_target, workflow=workflow)
    source_branch = base_branch
    reuse_branch = _teams_truthy(context.get("reuse_branch"))
    existing_branch = str(context.get("existing_branch") or "").strip()
    if reuse_branch and existing_branch and github_branch_exists(
        cloud,
        existing_branch,
        repo_target=repo_target,
        workflow=workflow,
    ):
        source_branch = existing_branch

    if workflow in INFRA_MODIFICATION_WORKFLOWS:
        state = get_or_create_thread_pr_state(
            thread_id,
            cloud,
            repo_target=repo_target,
            workflow=workflow,
            prompt=prompt,
        )
        folder = state.get("folder") or cloud_root_dir(cloud, repo_target, workflow)
        if cloud == "aws":
            current_path = state.get("environment_path") if reuse_branch else None
            environment_path, environment_error = resolve_aws_environment_path(
                prompt,
                retrieved_value_context=context.get("retrieved_value_context") or [],
                current_environment_path=current_path,
            )
            if environment_error:
                raise ValueError(environment_error)
            if environment_path:
                state["environment_path"] = environment_path

        safe_files: list[dict] = []
        for file_data in transformed.get("files") or []:
            relative_path = normalize_agent_relative_tf_path(file_data.get("filename") or "", cloud)
            if relative_path.startswith("terraform/"):
                repo_path = relative_path
            elif cloud == "aws" and state.get("environment_path"):
                repo_path = safe_join_under_folder(state["environment_path"], relative_path)
            else:
                repo_path = safe_join_under_folder(folder, relative_path)

            existing_content = github_get_file_content(
                cloud,
                repo_path,
                source_branch,
                repo_target=repo_target,
                workflow=workflow,
            )
            if existing_content is None:
                if invocation_creation:
                    # AWS module-does-not-exist path: a creation request may
                    # legitimately introduce a new module file under
                    # terraform/modules/ or a new consumer file when the
                    # environment uses per-resource files. Creation requests
                    # never replace anything, so a new path is safe.
                    safe_files.append({
                        "filename": repo_path,
                        "content": str(file_data.get("content") or ""),
                        "operation": "create",
                        "in_place": False,
                    })
                    patch_details.append({
                        "path": repo_path,
                        "kind": "invocation_new_file",
                        "applied": ["new file (creation request)"],
                        "ignored_generated": [],
                        "preserved_count": 0,
                    })
                    continue
                raise ValueError(
                    f"The selected modification target does not exist on `{source_branch}`: {repo_path}. "
                    "Terrabot will not create a replacement file for an update request."
                )
            safe_content, detail = _teams_safe_materialize_modification(
                existing_content,
                str(file_data.get("content") or ""),
                prompt,
                repo_path,
                invocation_creation=invocation_creation,
            )
            if (
                detail.get("kind") == "noop_already_applied"
                or _teams_safe_hcl_compare(safe_content) == _teams_safe_hcl_compare(existing_content or "")
            ):
                # Desired state already present on this branch — commit
                # nothing for this file instead of failing or pushing an
                # empty diff.
                detail.setdefault("kind", "noop_already_applied")
                patch_details.append(detail)
                logging.info("Teams commit: %s already up to date, skipped", repo_path)
                continue
            safe_files.append({
                "filename": repo_path,
                "content": safe_content,
                "operation": "modify",
                # True modifications intentionally change selected existing
                # lines; invocation creation is additive and must preserve all
                # existing lines byte-for-byte.
                "in_place": not invocation_creation,
            })
            patch_details.append(detail)
        if invocation_creation:
            # RULE 1 enforcement at the ONLY ref-correct point: the flag is
            # verified and, if missing, enabled against source_branch itself
            # — the same ref every other file in this commit uses.
            _teams_commit_side_flag_guarantee(
                safe_files,
                patch_details,
                prompt,
                context,
                cloud,
                repo_target,
                workflow,
                source_branch,
            )
            if cloud == "azure":
                _teams_materialize_azure_object_backed_creation(
                    transformed,
                    safe_files,
                    patch_details,
                    prompt,
                    context,
                    source_branch,
                    repo_target,
                    workflow,
                )
        if not safe_files:
            already = ", ".join(
                f"`{item.get('path')}`" for item in patch_details
                if item.get("kind") == "noop_already_applied" and item.get("path")
            ) or "the requested files"
            raise ValueError(
                f"No changes were needed: {already} already contain the requested "
                f"state on `{source_branch}`. Nothing was pushed — the branch's "
                "current diff link shows the existing change. To create another "
                "instance, use a different name."
            )
        transformed["files"] = safe_files

    analysis, source_paths = _teams_safe_backend_analysis(
        transformed,
        prompt,
        cloud,
        repo_target,
        workflow,
        source_branch,
        patch_details,
    )
    transformed["analysis"] = analysis
    transformed["source_paths_used"] = source_paths

    # Universal (every cloud) pre-commit safety net: fetch live existing
    # content for every touched file, then verify (a) the generated content
    # is complete valid HCL — not truncated mid-generation — and (b) every
    # existing line the user did not ask to change is still present exactly
    # as it was. Both raise ValueError on failure, which the caller
    # (commit_terraform_files_to_branch_for_teams_with_self_correction) turns
    # into a private retry with the Foundry agent instead of ever reaching
    # the user or the branch.
    _existing_by_path: dict = {}
    for _f in transformed.get("files") or []:
        if not isinstance(_f, dict):
            continue
        _path = _f.get("path") or _f.get("filename") or ""
        _content = _f.get("content") or ""
        if not _path:
            continue
        try:
            _validate_hcl_content_complete(_path, _content)
            _teams_diag_log("check_completeness_pass", thread=thread_id, path=_path)
        except ValueError as _completeness_error:
            _teams_diag_log(
                "check_completeness_fail",
                level="warning",
                thread=thread_id,
                path=_path,
                error=str(_completeness_error)[:200],
            )
            raise
        if _f.get("operation") not in ("modify", "create"):
            continue
        try:
            _existing_by_path[_path] = github_get_file_content(
                cloud, _path, source_branch, repo_target=repo_target, workflow=workflow
            ) or ""
        except Exception:
            _existing_by_path[_path] = ""

    try:
        _validate_teams_modify_no_unrequested_changes(
            transformed.get("files") or [], _existing_by_path
        )
        _teams_diag_log("check_no_unrequested_changes_pass", thread=thread_id)
    except ValueError as _preservation_error:
        _teams_diag_log(
            "check_no_unrequested_changes_fail",
            level="warning",
            thread=thread_id,
            error=str(_preservation_error)[:200],
        )
        raise

    if cloud == "azure":
        try:
            _validate_azure_object_backed_new_module_wiring(
                transformed.get("files") or [], _existing_by_path
            )
            _validate_azure_object_backed_three_file_write_set(
                transformed.get("files") or [], _existing_by_path
            )
            _teams_diag_log("check_object_wiring_pass", thread=thread_id)
            _teams_diag_log("check_object_write_set_pass", thread=thread_id)
        except ValueError as _wiring_error:
            _teams_diag_log(
                "check_object_wiring_fail",
                level="warning",
                thread=thread_id,
                error=str(_wiring_error)[:200],
            )
            raise

    try:
        _validate_new_module_variable_roots_are_provisioned(
            transformed.get("files") or [], _existing_by_path
        )
        _teams_diag_log("check_variable_provisioned_pass", thread=thread_id)
    except ValueError as _provisioning_error:
        _teams_diag_log(
            "check_variable_provisioned_fail",
            level="warning",
            thread=thread_id,
            error=str(_provisioning_error)[:200],
        )
        raise

    result = _TEAMS_SAFE_PREVIOUS_COMMIT_TO_BRANCH(transformed, prompt, thread_id)
    result["analysis"] = analysis
    result["source_paths_used"] = source_paths
    result["safe_patch_details"] = patch_details
    result["context_branch"] = source_branch
    return result
commit_terraform_files_to_branch_for_teams = commit_terraform_files_to_branch_for_teams_stage1


MAX_TEAMS_SELF_CORRECTION_ATTEMPTS = 5


def _teams_diag_log(event: str, level: str = "info", **fields) -> None:
    """Single-line, greppable diagnostic log for the Teams generation and
    self-correction pipeline. Format:
        [TerrabotDiag] level=<level> event=<event> key=value key=value ...

    IMPORTANT: this always logs at WARNING severity (regardless of the
    `level` argument, which is kept only as a readability tag in the message
    itself). A prior version used LOGGER.info() for most calls, and because
    this logger's effective level was never explicitly raised, those calls
    were silently dropped under the common default (root logger at WARNING)
    — which is exactly why none of these diagnostics were showing up in the
    Function App log stream even though the code was deployed and running.
    WARNING-level output survives that default, so these are now guaranteed
    visible without depending on host.json / Application Insights logLevel
    configuration. A duplicate stdout print is emitted too, since the Azure
    Functions Python worker generally forwards stdout to the log stream
    independently of the logging module's level filtering — a second,
    independent channel in case anything still filters LOGGER itself."""
    parts = " ".join(f"{k}={v}" for k, v in fields.items() if v is not None)
    line = f"[TerrabotDiag] level={level} event={event} {parts}"
    LOGGER.warning(line)
    try:
        print(line, flush=True)
    except Exception:
        pass


def _teams_find_truncated_file_error(error_text: str):
    """Parse a completeness-validation error message. Returns
    (path, open_bracket_count, open_brackets) if it matches the truncation
    signature from _validate_hcl_content_complete, else None. Lets the
    self-correction loop choose a targeted tail-completion repair instead of
    blindly re-requesting the whole file again."""
    m = re.search(
        r"Generated content for (\S+) is incomplete: (\d+) open bracket\(s\) \(([^)]*)\)",
        error_text or "",
    )
    if not m:
        return None
    return m.group(1), int(m.group(2)), m.group(3)


def _teams_attempt_tail_completion_repair(
    files: list, path: str, thread_id: str, prompt: str,
    current_result: Optional[dict] = None,
) -> bool:
    """Targeted fix for a truncated file.

    Asking the agent to regenerate the ENTIRE file again after a truncation
    tends to hit the exact same output-length ceiling every time — which is
    why the same "N open brackets" error can recur identically across every
    self-correction attempt instead of ever being fixed. Instead: send only
    the tail of what was already generated, ask for ONLY the remaining
    content needed to finish the file, and splice the two together
    server-side. The required completion is far smaller, so this is far more
    likely to actually converge than another full-file regeneration.

    Mutates `files` in place on success and returns True. Returns False if
    the tail-completion call fails, is empty, or still doesn't balance, so
    the caller falls back to a normal full-file self-correction attempt.
    """
    target = None
    for f in files or []:
        if isinstance(f, dict) and (f.get("path") or f.get("filename")) == path:
            target = f
            break
    if target is None:
        _teams_diag_log("tail_repair_skipped_no_target_file", path=path)
        return False
    truncated = target.get("content") or ""
    if not truncated:
        _teams_diag_log("tail_repair_skipped_empty_content", path=path)
        return False

    # REAL FAILURE FIXED HERE: this payload previously carried NO repository
    # grounding at all (no retrieved_value_context, no cloud/workflow/repo
    # target). Terrabot's own core instructions forbid generating anything
    # without grounded evidence — so an agent correctly following those
    # instructions had nothing to work with and returned empty files[] on
    # every single attempt (surfacing as "Teams agent returned no Terraform
    # files..." from the generic response coercer). Carry the same grounding
    # fields the full self-correction repair already includes.
    context = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    current_result = current_result or {}
    tail_lines = truncated.splitlines()[-40:]
    tail_preview = "\n".join(tail_lines)
    repair_payload = {
        "task": (
            "TAIL-COMPLETION REPAIR: your previous output for this file was cut "
            "off before it finished. Do NOT resend the whole file. Below is the "
            "exact tail of what you already generated — continue writing from "
            "immediately after it and output ONLY the remaining content needed "
            "to finish this file completely and validly (close every open "
            "block). Keep it as short as correctly finishing the file requires "
            "and nothing more."
        ),
        "channel": "teams",
        "path": path,
        "already_generated_tail": tail_preview,
        "instructions": [
            "Return the strict JSON envelope shape, with exactly one entry in files[].",
            "That file's 'content' must be ONLY the missing continuation text — "
            "not the tail shown above, and not the rest of the file from the top.",
            "Do not add commentary, do not restart the object, do not add "
            "unrelated new content — finish exactly what was left open, in the "
            "same style/formatting as the tail shown.",
            "Use the retrieved_value_context evidence below (the same live "
            "repository evidence from the original request) to determine the "
            "correct concrete values for whatever field was left incomplete — "
            "do not refuse or return no files for lack of context; the "
            "evidence needed is included in this payload.",
        ],
        "original_user_request": prompt,
        "expected_cloud": current_result.get("cloud"),
        "expected_workflow": current_result.get("workflow"),
        "expected_repo_target": current_result.get("repo_target"),
        "retrieved_value_context": context.get("retrieved_value_context") or [],
    }
    _teams_diag_log(
        "tail_repair_call_start", thread=thread_id, path=path, tail_lines=len(tail_lines)
    )
    continuation = ""
    try:
        _conversation_id, reply = call_agent(thread_id, json.dumps(repair_payload, indent=2))
    except Exception as exc:
        _teams_diag_log("tail_repair_call_failed", level="warning", thread=thread_id, path=path, error=str(exc)[:200])
        return False

    # Prefer the normal strict parse, but don't let a schema mismatch alone
    # sink an otherwise-usable continuation — fall back to a lenient direct
    # extraction of any non-empty file content in the raw JSON reply.
    try:
        parsed = try_parse_agent_output(reply)
        for pf in (parsed.get("files") or []):
            if isinstance(pf, dict):
                continuation = pf.get("content") or ""
                if continuation:
                    break
    except Exception as strict_parse_error:
        _teams_diag_log(
            "tail_repair_strict_parse_failed_trying_lenient",
            level="warning",
            thread=thread_id,
            path=path,
            error=str(strict_parse_error)[:200],
        )
        try:
            raw = extract_json_from_text(reply)
            if isinstance(raw, dict):
                for pf in (raw.get("files") or []):
                    if isinstance(pf, dict):
                        continuation = str(pf.get("content") or "")
                        if continuation.strip():
                            break
        except Exception as lenient_parse_error:
            _teams_diag_log(
                "tail_repair_lenient_parse_failed",
                level="warning",
                thread=thread_id,
                path=path,
                error=str(lenient_parse_error)[:200],
            )
            return False

    if not continuation.strip():
        _teams_diag_log("tail_repair_call_returned_empty", level="warning", thread=thread_id, path=path)
        return False

    spliced = truncated.rstrip("\n") + "\n" + continuation.lstrip("\n")
    try:
        _validate_hcl_content_complete(path, spliced)
    except ValueError as still_bad:
        _teams_diag_log(
            "tail_repair_still_incomplete", level="warning", path=path, error=str(still_bad)[:200]
        )
        return False

    target["content"] = spliced
    _teams_diag_log("tail_repair_success", path=path, added_chars=len(continuation))
    return True



def _teams_repair_file_map(files: list[dict] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in files or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("filename") or item.get("path") or "").strip().strip("/")
        if path:
            result[path] = str(item.get("content") or "")
    return result


def _teams_collect_live_repair_files(
    current_result: dict,
    flow_context: dict | None,
    retrieved_value_context: list | None,
) -> list[dict]:
    """Read the exact live counterpart for every rejected generated file.

    Repair turns must be self-contained. They receive the rejected generated
    code and the exact live repository code side-by-side so Foundry never has
    to infer unchanged content from conversation memory or compacted context.
    """
    flow_context = dict(flow_context or {})
    value_context = list(retrieved_value_context or [])
    selected = _get_backend_existing_infra_context(value_context)
    evidence: dict[str, str] = {}

    if isinstance(selected, dict):
        for item in list(selected.get("matched_files") or []) + list(selected.get("environment_files") or []):
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or item.get("filename") or "").strip().strip("/")
            content = str(item.get("content") or "")
            if path and content:
                evidence[path] = content

    cloud = safe_normalize_cloud(current_result.get("cloud") or flow_context.get("cloud"))
    workflow = str(current_result.get("workflow") or flow_context.get("workflow") or "").strip()
    repo_target = current_result.get("repo_target") or flow_context.get("repo_target")
    if cloud:
        repo_target = normalize_repo_target(cloud, repo_target=repo_target, workflow=workflow)

    ref = ""
    if isinstance(selected, dict):
        ref = str(selected.get("context_ref") or "").strip()
    if not ref:
        ref = str(flow_context.get("context_branch") or flow_context.get("source_branch") or "").strip()
    if cloud and not ref:
        try:
            ref = _teams_remote_context_branch(cloud, repo_target, workflow)
        except Exception:
            ref = ""

    generated = _teams_repair_file_map(current_result.get("files") or [])
    live_files: list[dict] = []
    for path, rejected_content in generated.items():
        live_content = evidence.get(path, "")
        if not live_content and cloud and ref:
            try:
                live_content = github_get_file_content(
                    cloud,
                    path,
                    ref,
                    repo_target=repo_target,
                    workflow=workflow,
                ) or ""
            except Exception as exc:
                _teams_diag_log(
                    "repair_live_file_read_failed",
                    level="warning",
                    path=path,
                    ref=ref,
                    error=str(exc)[:240],
                )
        live_files.append({
            "path": path,
            "repository_ref": ref,
            "existing_live_content": live_content,
            "rejected_generated_content": rejected_content,
            "existing_nonblank_line_count": len([line for line in live_content.splitlines() if line.strip()]),
            "rejected_nonblank_line_count": len([line for line in rejected_content.splitlines() if line.strip()]),
            "existing_sha256": hashlib.sha256(live_content.encode("utf-8")).hexdigest(),
            "rejected_sha256": hashlib.sha256(rejected_content.encode("utf-8")).hexdigest(),
            "must_return_complete_final_file": bool(live_content),
        })
    return live_files


