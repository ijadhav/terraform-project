from __future__ import annotations
from typing import TYPE_CHECKING , Any, Optional

if TYPE_CHECKING:
    from shared_code.terrabot_core_typing import (
        AGENT_NAME,
        AWS_MODULES_ROOT,
        INFRA_MODIFICATION_WORKFLOWS,
        LOGGER,
        _ACTIVE_TEAMS_FLOW_CONTEXT,
        _TEAMS_FLAG_VALUES_BASENAME_PRIORITY,
        _aws_consumer_files_from_agent_result,
        _extract_aws_module_source_refs_from_text,
        _extract_root_variable_names,
        _extract_top_level_hcl_assignment_names,
        _extract_top_level_tf_blocks,
        _find_balanced_curly_end,
        _get_azure_consumer_routing_context,
        _get_backend_existing_infra_context,
        _get_verified_azure_module_source_url,
        _has_git_conflict_markers,
        _iter_variable_blocks_with_names,
        _repository_context_branch_and_sha,
        _repository_context_completed_task_payload,
        _repository_context_evidence_excerpt,
        _repository_context_repo_identity,
        _repository_context_vague_resource_phrase,
        _sanitize_aws_module_rel_path,
        _teams_auto_select_feature_flag_context_stage1,
        _teams_candidate_friendly_label,
        _teams_diag_log,
        _teams_environment_folder_evidence,
        _teams_feature_flag_intent,
        _teams_is_existing_invocation_creation,
        _teams_remote_context_branch,
        _teams_repository_context_live_files,
        _teams_save_ui_state,
        _teams_target_environment_main_tf_evidence,
        _top_level_tf_block_matches,
        _top_level_tf_headers_for_modification,
        _validate_full_file_modification_preserves_existing,
        _validate_hcl_content_complete,
        _variable_attr_present,
        add_repository_context,
        call_named_agent,
        extract_json_from_text,
        github_get_file_content,
        github_get_file_content_by_repo,
        github_put_file,
        hashlib,
        json,
        load_teams_conversation_state,
        normalize_agent_relative_tf_path,
        normalize_cloud,
        normalize_iac_relative_path,
        normalize_repo_target,
        normalize_tf_relative_path,
        normalize_yes_no_reply,
        persist_teams_workflow_state,
        re,
        restore_teams_workflow_state,
        safe_normalize_cloud,
        shared_repository_context,
    )

def _terrabot_placeholder_content_detected(content: str) -> bool:
    text = str(content or "").lower()
    markers = (
        "<existing content preserved as in evidence>",
        "existing content preserved as in evidence",
        "<existing content preserved>",
        "existing content unchanged",
        "... existing content ...",
        "# existing content preserved",
    )
    return any(marker in text for marker in markers)


def _validate_agent_full_file_preservation_for_write_stage1(
    existing_content: str,
    generated_content: str,
    path: str,
    workflow: str | None,
) -> None:
    """Reject destructive Foundry rewrites without generating any Terraform.

    Validation may compare repository truth with Foundry's final file. It may
    not repair, merge, append, toggle, or otherwise mutate the generated HCL.
    """
    if existing_content is None:
        return
    if _terrabot_placeholder_content_detected(generated_content):
        raise UnsafeGeneratedChangeError(
            f"Generated modification for {path} contains a repository-content placeholder. "
            "Foundry must return the complete real file with unrelated content preserved."
        )

    normalized_workflow = str(workflow or "").strip()
    if normalized_workflow not in INFRA_MODIFICATION_WORKFLOWS:
        return

    # Re-enable the existing non-mutating preservation validator. This function
    # only rejects destructive replacements; it does not construct file content.
    try:
        _validate_full_file_modification_preserves_existing(
            existing_content,
            generated_content,
            path,
        )
    except ValueError as exc:
        raise UnsafeGeneratedChangeError(str(exc)) from exc

    existing = (existing_content or "").replace("\r\n", "\n")
    generated = (generated_content or "").replace("\r\n", "\n")
    if not existing.strip():
        return

    # Modification requests must not silently delete existing top-level blocks
    # unless the user explicitly requested deletion/removal.
    flow_context = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    effective_prompt = str(flow_context.get("effective_prompt") or "").lower()
    explicit_delete = bool(re.search(r"\b(?:delete|remove)\b", effective_prompt))
    if path.endswith(".tf") and not explicit_delete:
        existing_headers = _top_level_tf_headers_for_modification(existing)
        generated_headers = _top_level_tf_headers_for_modification(generated)
        missing_headers = sorted(existing_headers - generated_headers)
        if missing_headers:
            raise UnsafeGeneratedChangeError(
                f"Generated modification for {path} removed existing Terraform blocks: "
                + ", ".join(missing_headers[:12])
                + ". Foundry must preserve unrelated repository content and edit only the requested code."
            )

    # A complete-file modification should remain close in size to repository
    # truth. This catches one-line/single-block replacements while allowing
    # ordinary targeted edits and additions. It is validation only.
    existing_nonblank = [line for line in existing.splitlines() if line.strip()]
    generated_nonblank = [line for line in generated.splitlines() if line.strip()]
    if len(existing_nonblank) >= 20 and len(generated_nonblank) < max(8, int(len(existing_nonblank) * 0.70)):
        raise UnsafeGeneratedChangeError(
            f"Generated modification for {path} is substantially shorter than the live repository file "
            f"({len(generated_nonblank)} vs {len(existing_nonblank)} nonblank lines). "
            "Refusing a likely truncated overwrite; Foundry must return the complete final file."
        )
_validate_agent_full_file_preservation_for_write = _validate_agent_full_file_preservation_for_write_stage1


def github_put_file_if_changed_stage2(
    cloud: str,
    path: str,
    content: str,
    branch: str,
    commit_message: str,
    repo_target: Optional[str] = None,
    workflow: Optional[str] = None,
):
    """Validate preservation, then transport Foundry content exactly as returned."""
    existing_content = github_get_file_content(
        cloud,
        path,
        branch,
        repo_target=repo_target,
        workflow=workflow,
    )
    final_content = str(content or "")

    normalized_existing = (existing_content or "").replace("\r\n", "\n").strip()
    normalized_new = final_content.replace("\r\n", "\n").strip()
    if existing_content is not None and normalized_existing == normalized_new:
        return {"changed": False, "path": path, "result": None}

    if path.endswith((".tf", ".tfvars")):
        _validate_hcl_content_complete(path, final_content)
        if _has_git_conflict_markers(final_content):
            raise ValueError(f"Generated {path} contains Git conflict markers.")
        _validate_agent_full_file_preservation_for_write(
            existing_content,
            final_content,
            path,
            workflow,
        )

    # Transport only: no merge, repair, append, normalization, or flag toggle.
    result = github_put_file(
        cloud=cloud,
        path=path,
        content=final_content,
        branch=branch,
        commit_message=commit_message,
        repo_target=repo_target,
        workflow=workflow,
    )
    return {"changed": True, "path": path, "result": result}
github_put_file_if_changed = github_put_file_if_changed_stage2

# =============================================================================
# 2026-08-18 FOUNDRY SEMANTIC BOOLEAN CONTROL + EXACT PRESERVATION — FINAL OVERRIDE
# =============================================================================
# This layer intentionally does not infer resource vocabulary in Python. For a
# Teams AWS modification, the backend resolves the target environment and reads
# its complete main.tf, then asks Foundry whether the requested operation is
# implemented by an existing literal Boolean control. Foundry owns semantic
# interpretation; the backend only verifies that returned candidates literally
# exist in live repository content and safely transports the final full file.

_FINAL_BOOL_PREVIOUS_BUILD_EXISTING_CONTEXT = build_backend_existing_infra_modification_context
_FINAL_BOOL_PREVIOUS_SELECT_CANDIDATE = select_infra_modification_candidate_from_reply
_FINAL_BOOL_PREVIOUS_PATH_QUESTION = _teams_is_path_request_question
_FINAL_BOOL_PREVIOUS_GITHUB_PUT = github_put_file_if_changed


def _foundry_boolean_control_candidates(
    prompt: str,
    main_tf_evidence: list[dict],
) -> dict:
    """Ask Foundry to semantically identify actionable Boolean controls only.

    This is classification, not Terraform generation. Python does not decide
    that words such as enable/disable/remove imply a flag; Foundry decides
    whether the requested repository change is represented by a Boolean gate.
    """
    files = [
        {
            "path": str(item.get("path") or "").strip(),
            "content": str(item.get("content") or ""),
        }
        for item in (main_tf_evidence or [])
        if isinstance(item, dict)
        and str(item.get("path") or "").strip()
        and str(item.get("content") or "").strip()
    ]
    if not files:
        return {"applicable": False, "candidates": []}

    request = {
        "task": (
            "Classify whether the user's requested existing-infrastructure modification can be fulfilled "
            "by changing an existing literal Boolean assignment in the supplied target-environment main.tf. "
            "This is semantic repository analysis only; do not generate Terraform."
        ),
        "user_request": str(prompt or "").strip(),
        "target_environment_files": files,
        "required_output": {
            "applicable": "boolean",
            "reason": "short repository-grounded explanation",
            "candidates": [
                {
                    "path": "exact supplied main.tf path",
                    "module": "exact Terraform module label containing the Boolean",
                    "flag": "exact Boolean argument name",
                    "current_value": "true|false",
                    "new_value": "true|false",
                    "description": "short description of what this Boolean controls, inferred from the module/source/nearby arguments/comments",
                }
            ],
        },
        "rules": [
            "Return JSON only with keys applicable, reason, candidates.",
            "Decide from the semantics of the user request and repository content; do not rely on a fixed action-word vocabulary supplied by the backend.",
            "Set applicable=true only when an existing literal Boolean assignment in a semantically relevant module is a valid mechanism for the requested change.",
            "Candidates must be direct Boolean arguments of semantically relevant module blocks in the supplied main.tf files.",
            "Include only candidates whose value would actually change for this request; current_value and new_value must differ.",
            "Do not return data sources, SSM parameters, URLs, secrets, numeric/string parameters, outputs, providers, backend/version settings, or keyword-only matches.",
            "Do not invent a Boolean, module, path, alias, or value that is not present in the supplied repository content.",
            "If one Boolean clearly controls the requested resource, return only that Boolean even if unrelated parameters contain similar words.",
            "If multiple genuinely plausible Boolean controls remain, return all of those Boolean controls so the user can choose among parameters, not files.",
            "If the repository does not support this request through an existing Boolean control, set applicable=false and return candidates=[].",
        ],
    }
    try:
        raw = call_named_agent(json.dumps(request, ensure_ascii=False), AGENT_NAME)
        data = extract_json_from_text(raw)
        if not isinstance(data, dict):
            return {"applicable": False, "candidates": []}
        return data
    except Exception as exc:
        LOGGER.warning("Foundry Boolean-control classification failed; continuing normal semantic workflow: %s", exc)
        return {"applicable": False, "candidates": [], "error": str(exc)}


def _literal_module_boolean_index(main_tf_evidence: list[dict]) -> dict[tuple[str, str, str], dict]:
    """Index literal direct module Boolean assignments for validation only."""
    index: dict[tuple[str, str, str], dict] = {}
    for item in main_tf_evidence or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip().strip("/")
        content = str(item.get("content") or "")
        if not path or not content:
            continue
        for block in _extract_top_level_tf_blocks(content):
            header = str(block.get("header") or "").strip()
            module_match = re.fullmatch(r'module\s+"([^"]+)"', header)
            if not module_match:
                continue
            module_name = module_match.group(1)
            block_text = str(block.get("block") or "")
            # Direct literal Boolean assignments are intentionally narrow. The
            # semantic decision is Foundry's; this regex only proves the exact
            # returned flag/value exists in the selected live module block.
            for match in re.finditer(
                r'(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(true|false)\s*(?:#.*)?$',
                block_text,
                re.IGNORECASE,
            ):
                flag = match.group(1)
                current = match.group(2).lower()
                index[(path, module_name, flag)] = {
                    "path": path,
                    "module": module_name,
                    "flag": flag,
                    "current_value": current,
                }
    return index


def _foundry_boolean_control_retry(
    prompt: str,
    main_tf_evidence: list[dict],
    literal_index: dict[tuple[str, str, str], dict],
) -> dict:
    """Retry semantic resolution against a Boolean-only repository inventory.

    The first classifier sees the complete live main.tf so Foundry can understand
    module semantics. If it returns no usable control, this retry removes the
    unrelated Terraform surface area (data blocks, subnet lists, backend values,
    URLs, etc.) and asks Foundry to compare the user's phrase only against literal
    Boolean module arguments that really exist in the same live file. Python does
    not decide which Boolean means the user's phrase; it only supplies a validated
    structural inventory.
    """
    inventory = [
        {
            "path": item[0],
            "module": item[1],
            "flag": item[2],
            "current_value": value.get("current_value"),
        }
        for item, value in literal_index.items()
    ]
    if not inventory:
        return {"applicable": False, "candidates": [], "reason": "No literal module Boolean controls exist in target main.tf."}

    request = {
        "task": (
            "SECOND-PASS SEMANTIC BOOLEAN RESOLUTION. The complete target main.tf was already inspected, "
            "but no usable Boolean control was returned. Resolve the user's colloquial resource phrase only "
            "against the repository-proven Boolean controls listed below. Do not generate Terraform."
        ),
        "user_request": str(prompt or "").strip(),
        "literal_boolean_controls": inventory,
        "target_environment_files": [
            {"path": str(item.get("path") or ""), "content": str(item.get("content") or "")}
            for item in main_tf_evidence or []
            if isinstance(item, dict)
        ],
        "required_output": {
            "applicable": "boolean",
            "reason": "short repository-grounded semantic explanation",
            "candidates": [{
                "path": "exact path from literal_boolean_controls",
                "module": "exact module from literal_boolean_controls",
                "flag": "exact flag from literal_boolean_controls",
                "current_value": "true|false",
                "new_value": "true|false",
                "confidence": 0.0,
                "description": "what this Boolean controls in repository terms",
            }],
        },
        "rules": [
            "Return JSON only with keys applicable, reason, candidates.",
            "Choose only from literal_boolean_controls; never invent a path/module/flag.",
            "Resolve aliases and colloquial wording semantically from module labels, flag names, comments, nearby settings, and the full target main.tf.",
            "A phrase does not need to literally contain the flag name. For example, repository wording such as patch setup may semantically refer to a patch-monitoring control when the surrounding module evidence supports that relationship.",
            "Ignore unrelated Boolean controls even though they are structurally valid Booleans.",
            "Return only controls that actually implement the requested behavior and whose value must change.",
            "If exactly one control is materially strongest, return only that control.",
            "Return multiple candidates only when two or more controls are genuinely distinct interpretations of the requested resource phrase, not merely because they share words.",
            "Use confidence from 0 to 1. Prefer no candidate over a weak semantic match.",
        ],
    }
    try:
        raw = call_named_agent(json.dumps(request, ensure_ascii=False), AGENT_NAME)
        parsed = extract_json_from_text(raw)
        return parsed if isinstance(parsed, dict) else {"applicable": False, "candidates": []}
    except Exception as exc:
        LOGGER.warning("Foundry Boolean-control second pass failed: %s", exc)
        return {"applicable": False, "candidates": [], "error": str(exc)}


def _validated_foundry_boolean_candidates(
    prompt: str,
    main_tf_evidence: list[dict],
) -> tuple[bool, list[dict], str]:
    literal_index = _literal_module_boolean_index(main_tf_evidence)
    classification = _foundry_boolean_control_candidates(prompt, main_tf_evidence)

    def _validate(classification_payload: dict) -> list[dict]:
        if not bool(classification_payload.get("applicable")):
            return []
        validated_items: list[dict] = []
        seen: set[tuple[str, str, str]] = set()
        for candidate in classification_payload.get("candidates") or []:
            if not isinstance(candidate, dict):
                continue
            path = str(candidate.get("path") or "").strip().strip("/")
            module_name = str(candidate.get("module") or "").strip()
            flag = str(candidate.get("flag") or "").strip()
            current = str(candidate.get("current_value") or "").strip().lower()
            new_value = str(candidate.get("new_value") or "").strip().lower()
            key = (path, module_name, flag)
            literal = literal_index.get(key)
            if not literal:
                continue
            if current not in {"true", "false"} or new_value not in {"true", "false"}:
                continue
            if current == new_value or literal.get("current_value") != current:
                continue
            if key in seen:
                continue
            seen.add(key)
            try:
                confidence = float(candidate.get("confidence") or 0.0)
            except (TypeError, ValueError):
                confidence = 0.0
            validated_items.append({
                **literal,
                "new_value": new_value,
                "confidence": max(0.0, min(confidence, 1.0)),
                "context": str(candidate.get("description") or "").strip()
                or f'Controls the requested behavior in module "{module_name}".',
                "description": str(candidate.get("description") or "").strip()
                or f'Controls the requested behavior in module "{module_name}".',
                "classification_reason": str(classification_payload.get("reason") or "").strip(),
            })
        return validated_items

    validated = _validate(classification)
    if not validated:
        retry = _foundry_boolean_control_retry(prompt, main_tf_evidence, literal_index)
        retry_validated = _validate(retry)
        if retry_validated:
            LOGGER.warning(
                "[TerrabotDiag] event=boolean_control_second_pass_resolved candidates=%s request=%s",
                len(retry_validated),
                str(prompt or "")[:160],
            )
            classification = retry
            validated = retry_validated

    if not validated:
        return False, [], str(classification.get("reason") or "")

    # Foundry owns semantic ranking. If it returned confidence values and one
    # result is materially stronger, do not make the user choose among weaker
    # alternatives. Equal/near-equal distinct controls remain a real picker.
    ranked = sorted(validated, key=lambda item: float(item.get("confidence") or 0.0), reverse=True)
    if len(ranked) > 1:
        top = float(ranked[0].get("confidence") or 0.0)
        second = float(ranked[1].get("confidence") or 0.0)
        if top >= 0.80 and top - second >= 0.15:
            ranked = [ranked[0]]

    return True, ranked, str(classification.get("reason") or "")


def build_backend_existing_infra_modification_context_stage5(
    prompt: str,
    thread_id: str,
    cloud: str,
    workflow: str,
    retrieved_value_context: list | None = None,
) -> dict:
    """Final modification resolver with Foundry-owned Boolean semantics.

    For Teams AWS modifications, always inspect the resolved environment
    main.tf first. If Foundry proves the requested operation is controlled by
    literal Boolean argument(s), only those arguments become candidates. This
    path is intentionally independent of hardcoded enable/disable keywords.
    """
    context = _FINAL_BOOL_PREVIOUS_BUILD_EXISTING_CONTEXT(
        prompt,
        thread_id,
        cloud,
        workflow,
        retrieved_value_context=retrieved_value_context,
    )
    active = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    if not active.get("active"):
        return context
    try:
        normalized_cloud = normalize_cloud(cloud)
    except Exception:
        return context
    if normalized_cloud != "aws" or str(workflow or "").strip() not in INFRA_MODIFICATION_WORKFLOWS:
        return context

    context = dict(context or {})
    branch = str(context.get("context_ref") or "").strip()
    if not branch:
        try:
            branch = _teams_remote_context_branch(
                "aws",
                repo_target="tf-devops",
                workflow=workflow,
            )
        except Exception:
            branch = ""

    main_tf_evidence = _teams_target_environment_main_tf_evidence(
        prompt,
        "aws",
        workflow,
        branch,
    )
    if not main_tf_evidence:
        return context

    applicable, candidates, reason = _validated_foundry_boolean_candidates(
        prompt,
        main_tf_evidence,
    )
    if not applicable or not candidates:
        # Still make target main.tf the primary evidence for the agent, but do
        # not invent a Boolean workflow when Foundry says the request is not
        # controlled by a literal flag.
        context["matched_files"] = main_tf_evidence
        context["matched_file_paths"] = [item.get("path") for item in main_tf_evidence if item.get("path")]
        context["selection_state"] = "selected"
        context["selected_path"] = main_tf_evidence[0].get("path") if len(main_tf_evidence) == 1 else ""
        context["target_environment_main_tf_first"] = True
        context["agent_resolves_target"] = True
        context["boolean_control_classification"] = {
            "applicable": False,
            "reason": reason,
        }
        context["instructions"] = list(context.get("instructions") or []) + [
            "The target environment main.tf is already an authorized modification target. Never ask the user for permission to modify it or for an alternative repository path.",
            "If repository semantics are genuinely ambiguous, ask only which resource/module the user means; never ask which file/path to use when the target environment has already been resolved.",
        ]
        return context

    evidence_by_path = {
        str(item.get("path") or "").strip().strip("/"): item
        for item in main_tf_evidence
        if isinstance(item, dict)
    }
    matched: list[dict] = []
    for candidate in candidates:
        source = dict(evidence_by_path.get(candidate["path"]) or {})
        if not source:
            continue
        source["feature_flag_match"] = dict(candidate)
        source["matched_blocks"] = [{
            "header": f'module "{candidate["module"]}"',
            "block": "",
        }]
        source["reason"] = "Foundry semantic Boolean-control match validated against live target main.tf"
        matched.append(source)

    if not matched:
        return context

    context["matched_files"] = matched
    context["matched_file_paths"] = list(dict.fromkeys(item.get("path") for item in matched if item.get("path")))
    context["feature_flag_selection"] = True
    context["target_environment_main_tf_first"] = True
    context["agent_resolves_target"] = False
    context["boolean_control_classification"] = {
        "applicable": True,
        "reason": reason,
        "candidate_count": len(matched),
    }
    context["instructions"] = [
        "Foundry already semantically classified the requested operation as an existing Boolean-gated repository change; the backend verified every listed Boolean literally exists in live target main.tf.",
        "Use only feature_flag_match. Do not change or surface any other parameter merely because its name/content resembles the user's resource wording.",
        "The target main.tf is already authorized by the resolved environment. Never ask permission to modify it and never ask for an alternative path.",
        "After one Boolean is selected, change only that exact Boolean assignment to feature_flag_match.new_value and return the COMPLETE final target file.",
        "Preserve every unrelated byte/line/block/comment in the existing file. Do not reformat, reorder, truncate, summarize, or replace unrelated repository content.",
    ]
    if len(matched) == 1:
        context["selection_state"] = "selected"
        context["selected_path"] = matched[0].get("path") or ""
    else:
        context["selection_state"] = "candidate_selection_required"
        context["selected_path"] = ""
    return context
build_backend_existing_infra_modification_context = build_backend_existing_infra_modification_context_stage5


def select_infra_modification_candidate_from_reply(reply: str, pending_selection: dict) -> int | None:
    """Allow Boolean picker follow-ups by number OR exact parameter name."""
    selected = _FINAL_BOOL_PREVIOUS_SELECT_CANDIDATE(reply, pending_selection)
    if selected is not None:
        return selected
    text = str(reply or "").strip().strip("`'\"").lower()
    candidates = ((pending_selection.get("existing_infra_context") or {}).get("matched_files") or [])
    for index, candidate in enumerate(candidates):
        match = (candidate or {}).get("feature_flag_match") or {}
        flag = str(match.get("flag") or "").strip().lower()
        module_name = str(match.get("module") or "").strip().lower()
        if flag and text == flag:
            return index
        if module_name and text in {module_name, f'module {module_name}'}:
            return index
    return None


def build_infra_modification_selection_reply(existing_infra_context: dict) -> str:
    """Render Boolean ambiguity as a parameter question, never a file picker."""
    candidates = list(existing_infra_context.get("matched_files") or [])
    flag_items = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        match = item.get("feature_flag_match") or {}
        if str(match.get("flag") or "").strip():
            flag_items.append((item, match))
    if flag_items:
        lines = [
            "I found multiple repository-backed controls that match this request. Which resource/control should I change?",
            "",
        ]
        for index, (item, match) in enumerate(flag_items, start=1):
            flag = str(match.get("flag") or "").strip()
            module_name = str(match.get("module") or "").strip()
            current = str(match.get("current_value") or "").strip().lower()
            target = str(match.get("new_value") or "").strip().lower()
            description = str(match.get("context") or match.get("description") or "").strip()
            label = description or (f'Boolean control in module {module_name}' if module_name else f'Repository control {flag}')
            lines.append(f"{index}. **{label}** — current state `{current}` → requested state `{target}`")
        lines.extend([
            "",
            "Reply with the number or the resource/control name shown above. Terrabot already knows the repository file and exact Terraform identifier.",
        ])
        return "\n".join(lines)
    # Preserve every earlier non-Boolean clarification behavior.
    return _teams_candidate_selection_reply_non_boolean(existing_infra_context)


def _teams_candidate_selection_reply_non_boolean(existing_infra_context: dict) -> str:
    candidates = list(existing_infra_context.get("matched_files") or [])[:6]
    if not candidates:
        return (
            "I couldn't find a repository-backed Terraform target for that resource wording. "
            "Reply with a more specific resource/module name; you do not need to provide a file path."
        )
    lines = [
        "I found a few similar repository resources. Which resource should I modify?",
        "",
    ]
    for index, item in enumerate(candidates, start=1):
        label = _teams_candidate_friendly_label(item)
        lines.append(f"{index}. **{label}**")
    lines.extend([
        "",
        "Reply with the number or resource/component name shown above. Terrabot will use the already resolved repository path internally.",
    ])
    return "\n".join(lines)


def _teams_is_path_request_question(text: str) -> bool:
    """Treat repo-answerable permission/path/flag questions as internal.

    Generic proceed/confirmation wording is included so a direct infrastructure
    command cannot leak an unnecessary approval roundtrip. Genuine ambiguity
    cards (multiple flags/modules/resources) do not match.
    """
    value = re.sub(r"\s+", " ", str(text or "").strip().lower())
    if _FINAL_BOOL_PREVIOUS_PATH_QUESTION(value):
        return True
    forbidden = (
        "path restriction", "allow modifying", "allow modification",
        "alternative repo-approved path", "alternative repository-approved path",
        "provide an alternative", "confirm how you want to proceed given the path",
        "specify the exact file", "which file should i modify",
        "which path should i modify", "permission to modify",
        "do you want me to proceed", "would you like me to proceed",
        "should i proceed", "reply yes to proceed", "before i proceed",
        "confirm the exact target", "confirm the target", "confirm the file",
        "confirm the file path", "do you want me to disable",
        "exact terraform variable", "terraform variable name",
        "point me to the exact", "paste the snippet that defines",
        "flag name and location", "where the flag resides",
        "would you like me to disable", "should i disable",
        "do you want me to enable", "would you like me to enable",
        "should i enable", "turning off the repository flag",
        "turning on the repository flag",
    )
    return any(marker in value for marker in forbidden)


def _selected_feature_flag_match_from_active_context(path: str = "") -> dict:
    active = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    wanted_path = str(path or "").strip().strip("/")
    for ctx in active.get("retrieved_value_context") or []:
        if not isinstance(ctx, dict) or ctx.get("source") != "backend_existing_infra_code_match":
            continue
        for item in ctx.get("matched_files") or []:
            if not isinstance(item, dict):
                continue
            match = item.get("feature_flag_match") or {}
            item_path = str(item.get("path") or "").strip().strip("/")
            if match and (not wanted_path or item_path == wanted_path):
                return dict(match)
    return {}


class UnsafeGeneratedChangeError(ValueError):
    """Generated Terraform is unsafe to write and must not be auto-repaired.

    These failures indicate semantic drift, unrelated edits, or destructive
    preservation violations. Retrying the same draft through Foundry can turn
    a blocked bad diff into a different bad diff, so the branch write stops.
    """


def _validate_selected_boolean_is_only_file_change_stage1(
    existing_content: str,
    generated_content: str,
    path: str,
) -> None:
    """For a selected Boolean change, require exact preservation otherwise.

    This is a validator only. It never constructs/merges Terraform. The model's
    final file must differ from live repository truth by exactly one replacement
    line: the selected literal Boolean assignment.
    """
    match = _selected_feature_flag_match_from_active_context(path)
    if not match:
        return
    flag = str(match.get("flag") or "").strip()
    current = str(match.get("current_value") or "").strip().lower()
    target = str(match.get("new_value") or "").strip().lower()
    if not flag or current not in {"true", "false"} or target not in {"true", "false"} or current == target:
        raise UnsafeGeneratedChangeError("Selected Boolean modification context is incomplete or invalid.")

    existing_lines = (existing_content or "").replace("\r\n", "\n").splitlines()
    generated_lines = (generated_content or "").replace("\r\n", "\n").splitlines()
    if len(existing_lines) != len(generated_lines):
        raise UnsafeGeneratedChangeError(
            f"Generated Boolean modification for {path} added/removed lines. "
            "Only the selected Boolean assignment may change; all other repository content must remain exactly preserved."
        )

    assignment = re.compile(
        rf'^(\s*){re.escape(flag)}(\s*=\s*)(true|false)(\s*(?:#.*)?)$',
        re.IGNORECASE,
    )
    changed = 0
    for old_line, new_line in zip(existing_lines, generated_lines):
        if old_line == new_line:
            continue
        old_match = assignment.match(old_line)
        new_match = assignment.match(new_line)
        if not old_match or not new_match:
            raise UnsafeGeneratedChangeError(
                f"Generated Boolean modification for {path} changed unrelated repository content. "
                f"Only `{flag} = {current}` may become `{flag} = {target}`."
            )
        if old_match.group(3).lower() != current or new_match.group(3).lower() != target:
            raise UnsafeGeneratedChangeError(
                f"Generated Boolean modification for {path} changed `{flag}` with unexpected values. "
                f"Expected {current} -> {target}."
            )
        # Preserve indentation, spacing around '=', and any inline comment too.
        if old_match.group(1) != new_match.group(1) or old_match.group(2) != new_match.group(2) or old_match.group(4) != new_match.group(4):
            raise UnsafeGeneratedChangeError(
                f"Generated Boolean modification for {path} reformatted the selected line. "
                "Only the literal Boolean value may change."
            )
        changed += 1
    if changed != 1:
        raise UnsafeGeneratedChangeError(
            f"Generated Boolean modification for {path} must change exactly one `{flag}` assignment; observed {changed}."
        )
_validate_selected_boolean_is_only_file_change = _validate_selected_boolean_is_only_file_change_stage1


def github_put_file_if_changed(
    cloud: str,
    path: str,
    content: str,
    branch: str,
    commit_message: str,
    repo_target: Optional[str] = None,
    workflow: Optional[str] = None,
):
    """Add exact selected-Boolean preservation validation, then use prior writer."""
    existing_content = github_get_file_content(
        cloud,
        path,
        branch,
        repo_target=repo_target,
        workflow=workflow,
    )
    if existing_content is not None:
        _validate_selected_boolean_is_only_file_change(
            existing_content,
            str(content or ""),
            path,
        )
    return _FINAL_BOOL_PREVIOUS_GITHUB_PUT(
        cloud=cloud,
        path=path,
        content=content,
        branch=branch,
        commit_message=commit_message,
        repo_target=repo_target,
        workflow=workflow,
    )



# =============================================================================
# 2026-08-18 VALIDATED AGENT-OWNED MODIFICATION/CREATION CONTRACT — FINAL OVERRIDE
# =============================================================================
# Teams backend responsibilities are limited to repository retrieval, literal
# repository validation, preservation validation, state, and transport. Foundry
# owns semantic target selection and every Terraform/HCL edit.

_VALIDATED_PREVIOUS_BUILD_EXISTING_CONTEXT = build_backend_existing_infra_modification_context
_VALIDATED_PREVIOUS_CONTEXT_SELECTED = _backend_existing_infra_context_is_selected
_VALIDATED_PREVIOUS_ENFORCE_MOD_PATHS = enforce_modification_uses_backend_matched_files
_VALIDATED_PREVIOUS_ENFORCE_REAL_INPUTS = enforce_real_module_inputs
_VALIDATED_PREVIOUS_ENSURE_AZURE_VARIABLES = ensure_azure_consumer_variables_tf_file
_VALIDATED_PREVIOUS_REPAIR_AZURE_VARIABLES = _repair_azure_consumer_variables_tf_files_in_agent_result
_VALIDATED_PREVIOUS_AWS_MATERIALIZER = _teams_aws_materialize_repo_aligned_consumer
_VALIDATED_PREVIOUS_AZURE_OBJECT_MATERIALIZER = _teams_materialize_azure_object_backed_creation
_VALIDATED_PREVIOUS_COMMIT_FLAG_GUARANTEE = _teams_commit_side_flag_guarantee
_VALIDATED_PREVIOUS_ENSURE_FLAG_VALUES = _teams_ensure_flag_enable_in_env_values


def _teams_context_file_identity(item: dict) -> str:
    return str((item or {}).get("path") or (item or {}).get("filename") or "").strip().strip("/")


def _teams_merge_repository_evidence(primary: list[dict], extra: list[dict]) -> list[dict]:
    """Deduplicate live evidence without ranking/choosing a semantic target."""
    result: list[dict] = []
    seen: set[str] = set()
    for item in list(primary or []) + list(extra or []):
        if not isinstance(item, dict):
            continue
        path = _teams_context_file_identity(item)
        content = str(item.get("content") or "")
        if not path or not content or path in seen:
            continue
        result.append(dict(item))
        seen.add(path)
    return result


def _teams_rehydrate_repository_evidence_full_contents(
    evidence: list[dict],
    cloud: str,
    repo_target: str,
    workflow: str,
    branch: str,
) -> list[dict]:
    """Refresh Terraform evidence from live GitHub without snippet truncation.

    Environment discovery intentionally bounds snippets for general Foundry
    context. Boolean targeting cannot use those bounded snippets as its literal
    inventory, because a valid flag can appear after the per-file character
    cutoff (large hub/tier tfvars files are a common example). Re-read only the
    already-discovered Terraform paths from the same resolved branch. This is
    repository retrieval, not semantic selection or Terraform generation.
    """
    result: list[dict] = []
    for item in evidence or []:
        if not isinstance(item, dict):
            continue
        refreshed = dict(item)
        path = _teams_context_file_identity(refreshed)
        if not path or not path.endswith((".tf", ".tfvars")):
            result.append(refreshed)
            continue
        try:
            live_content = github_get_file_content(
                cloud,
                path,
                branch,
                repo_target=repo_target,
                workflow=workflow,
            )
        except Exception as exc:
            LOGGER.debug(
                "Full Teams repository evidence refresh failed path=%s branch=%s: %s",
                path,
                branch,
                exc,
            )
            live_content = None
        if live_content is not None:
            refreshed["content"] = live_content
            refreshed["full_live_content"] = True
        result.append(refreshed)
    return result


def build_backend_existing_infra_modification_context_stage6(
    prompt: str,
    thread_id: str,
    cloud: str,
    workflow: str,
    retrieved_value_context: list | None = None,
) -> dict:
    """Final Teams modification retrieval contract.

    The backend may resolve an environment and collect repository files. It must
    not make the semantic resource/module decision for non-Boolean ambiguity.
    Boolean candidates remain Foundry-classified and literal-repository-validated.
    All other environment/repository candidates become hidden evidence supplied
    to Foundry, not a user-facing file picker.
    """
    context = _VALIDATED_PREVIOUS_BUILD_EXISTING_CONTEXT(
        prompt,
        thread_id,
        cloud,
        workflow,
        retrieved_value_context=retrieved_value_context,
    )
    active = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    if not active.get("active"):
        return context
    try:
        normalized_cloud = normalize_cloud(cloud)
    except Exception:
        return context
    if str(workflow or "").strip() not in INFRA_MODIFICATION_WORKFLOWS:
        return context

    context = dict(context or {})
    matched = list(context.get("matched_files") or [])

    # Preserve the validated Boolean ambiguity protocol: multiple literal
    # Foundry-selected Boolean controls are intentionally user choices.
    if context.get("feature_flag_selection"):
        return context

    branch = str(context.get("context_ref") or "").strip()
    repo_target = normalize_repo_target(normalized_cloud, workflow=workflow)
    if not branch:
        try:
            branch = _teams_remote_context_branch(normalized_cloud, repo_target, workflow)
        except Exception:
            branch = ""

    # Read the complete environment folder when it can be resolved. These are
    # evidence files only; Foundry decides which resource/module/file implements
    # the request. No file list is surfaced to the user.
    env_entries: list[dict] = []
    env_write_paths: list[str] = []
    env_debug: dict = {}
    if branch:
        try:
            env_entries, env_write_paths, env_debug = _teams_environment_folder_evidence(
                prompt,
                normalized_cloud,
                repo_target,
                workflow,
                branch,
            )
        except Exception as exc:
            env_debug = {"error": str(exc)}

    combined = _teams_merge_repository_evidence(matched, env_entries)
    if combined:
        context["matched_files"] = combined
        context["matched_file_paths"] = [_teams_context_file_identity(item) for item in combined]
        context["selection_state"] = "selected"
        context["selected_path"] = ""
        context["agent_resolves_target"] = True
        context["environment_files"] = list(env_entries or [])
        context["environment_evidence_summary"] = env_debug
        if env_write_paths:
            existing_companions = list(context.get("companion_write_paths") or [])
            for path in env_write_paths:
                if path and path not in existing_companions:
                    existing_companions.append(path)
            context["companion_write_paths"] = existing_companions
        context["instructions"] = list(context.get("instructions") or []) + [
            "Repository file discovery is backend evidence only. Do not ask the user which Terraform file to edit.",
            "Inspect all supplied environment/repository evidence and infer the exact resource/module/file required by the user's request from repository semantics and existing patterns.",
            "If multiple genuinely distinct resource/module targets remain after semantic analysis, ask the user which RESOURCE/MODULE they mean; list only relevant semantic choices with concise repository-derived descriptions.",
            "For a Boolean-gated behavior, prefer the literal Boolean control inside the semantically matched resource/module and do not surface unrelated parameters or files.",
            "Generate complete final changed files yourself. The backend will validate but will not merge, append, toggle, repair, or synthesize Terraform.",
        ]
    return context
build_backend_existing_infra_modification_context = build_backend_existing_infra_modification_context_stage6


def _backend_existing_infra_context_is_selected(context: dict | None) -> bool:
    """Agent-resolved multi-file evidence counts as ready for Foundry generation.

    A validated multi-Boolean choice remains unresolved until the user selects
    one candidate. Everything else may be passed to Foundry as repository
    evidence without asking the user to choose a file.
    """
    if isinstance(context, dict):
        if context.get("feature_flag_selection") and context.get("selection_state") == "candidate_selection_required":
            return False
        if context.get("agent_resolves_target") and context.get("matched_files"):
            return True
    return _VALIDATED_PREVIOUS_CONTEXT_SELECTED(context)


def _teams_validate_agent_preserved_existing_file(path: str, generated: str, context: dict) -> None:
    path = str(path or "").strip().strip("/")
    if not path:
        return
    for item in list(context.get("matched_files") or []) + list(context.get("environment_files") or []):
        if not isinstance(item, dict) or _teams_context_file_identity(item) != path:
            continue
        existing = str(item.get("content") or "")
        if not existing:
            return
        _validate_agent_full_file_preservation_for_write(
            existing,
            generated,
            path,
            str(context.get("workflow") or ""),
        )
        return


def enforce_modification_uses_backend_matched_files(agent_result: dict, retrieved_value_context: list | None) -> dict:
    """Validate agent-chosen paths and aggregate independent deterministic failures.

    For agent_resolves_target contexts every supplied live evidence path is an
    allowed candidate. All returned files are checked before raising so Foundry
    receives one repair package containing every known path/preservation/companion
    failure instead of discovering them across sequential repair rounds.
    """
    context = _get_backend_existing_infra_context(retrieved_value_context)
    validation_errors: list[str] = []

    if not isinstance(context, dict) or not context.get("agent_resolves_target"):
        try:
            result = _VALIDATED_PREVIOUS_ENFORCE_MOD_PATHS(agent_result, retrieved_value_context)
        except ValueError as exc:
            validation_errors.append(str(exc))
            result = agent_result
    else:
        allowed = {
            _teams_context_file_identity(item)
            for item in list(context.get("matched_files") or []) + list(context.get("environment_files") or [])
            if isinstance(item, dict) and _teams_context_file_identity(item)
        }
        allowed |= {
            str(path or "").strip().strip("/")
            for path in context.get("companion_write_paths") or []
            if str(path or "").strip()
        }
        for file_data in agent_result.get("files") or []:
            if not isinstance(file_data, dict):
                continue
            raw = str(file_data.get("filename") or file_data.get("path") or "").strip()
            try:
                normalized = normalize_iac_relative_path(raw, allow_tfvars=True).strip("/")
            except Exception as exc:
                validation_errors.append(f"Invalid generated path `{raw}`: {exc}")
                continue
            if allowed and normalized not in allowed:
                validation_errors.append(
                    f"Generated modification path `{normalized}` is not present in the live repository evidence for this request. "
                    "Foundry must choose only repository-grounded target files supplied by the backend."
                )
                continue
            try:
                _teams_validate_agent_preserved_existing_file(
                    normalized,
                    str(file_data.get("content") or ""),
                    context,
                )
            except ValueError as exc:
                validation_errors.append(str(exc))
        result = agent_result

    # Creation companion completeness is part of the same deterministic batch.
    active = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    effective_prompt = str(active.get("effective_prompt") or agent_result.get("user_prompt") or "")
    if active.get("active") and _teams_is_existing_invocation_creation(effective_prompt):
        creation_context = _get_backend_existing_infra_context(retrieved_value_context)
        creation_context = creation_context if isinstance(creation_context, dict) else {}
        companions = {
            str(path or "").strip().strip("/")
            for path in (creation_context.get("companion_write_paths") or [])
            if str(path or "").strip()
        }
        returned = set()
        for item in result.get("files") or []:
            if not isinstance(item, dict):
                continue
            raw = str(item.get("filename") or item.get("path") or "")
            try:
                returned.add(normalize_iac_relative_path(raw, allow_tfvars=True).strip("/"))
            except Exception:
                continue
        required_tfvars = sorted(path for path in companions if path.endswith((".tfvars", ".tfvars.json")))
        if required_tfvars and not (returned & set(required_tfvars)):
            validation_errors.append(
                "Creation output is missing the repository companion tfvars values file. "
                f"Foundry must return the complete updated content for one of: {', '.join(required_tfvars)}."
            )

    if validation_errors:
        # Stable de-duplication keeps the repair prompt concise when two guards
        # report the same underlying preservation problem.
        unique_errors = list(dict.fromkeys(error for error in validation_errors if error))
        raise ValueError(
            "BACKEND_MODIFICATION_VALIDATION_FAILED_MULTIPLE: "
            + " | ".join(unique_errors)
        )
    return result


def _teams_validate_azure_consumer_agent_output(
    agent_result: dict,
    retrieved_module_context: list,
    retrieved_value_context: list | None,
) -> dict:
    """Validator-only Azure consumer contract; never builds/merges HCL."""
    routing = _get_azure_consumer_routing_context(retrieved_value_context or [])
    if not routing:
        raise ValueError("Azure consumer generation requires live backend routing evidence before generation.")
    target_consumer = normalize_agent_relative_tf_path(routing.get("target_consumer_filename") or "", "azure")
    target_tfvars = normalize_agent_relative_tf_path(routing.get("target_tfvars_filename") or "", "azure")
    files = [item for item in (agent_result.get("files") or []) if isinstance(item, dict)]
    by_name = {
        normalize_agent_relative_tf_path(str(item.get("filename") or item.get("path") or ""), "azure"): item
        for item in files
    }
    if target_consumer not in by_name:
        raise ValueError(f"Azure creation output is missing the repository consumer file `{target_consumer}`.")
    if target_tfvars not in by_name:
        raise ValueError(f"Azure creation output is missing the repository tfvars values file `{target_tfvars}`.")

    module_source = _get_verified_azure_module_source_url(retrieved_module_context)
    if module_source and module_source not in str(by_name[target_consumer].get("content") or ""):
        raise ValueError("Azure consumer output does not use the verified selected module source.")

    existing_consumer = str(routing.get("existing_consumer_file_content") or "")
    if existing_consumer:
        _validate_agent_full_file_preservation_for_write(
            existing_consumer,
            str(by_name[target_consumer].get("content") or ""),
            target_consumer,
            "azure_consumer_generation",
        )
    existing_tfvars = str(routing.get("existing_tfvars_file_content") or "")
    if existing_tfvars:
        _validate_agent_full_file_preservation_for_write(
            existing_tfvars,
            str(by_name[target_tfvars].get("content") or ""),
            target_tfvars,
            "azure_consumer_generation",
        )

    generated_tfvars = str(by_name[target_tfvars].get("content") or "")
    existing_roots = set(_extract_top_level_hcl_assignment_names(existing_tfvars))
    generated_roots = set(_extract_top_level_hcl_assignment_names(generated_tfvars))
    new_roots = sorted(generated_roots - existing_roots)
    if new_roots:
        variables_name = "variables.tf"
        existing_variables = str(routing.get("variables_tf_file_content") or "")
        declared_existing = set(_extract_root_variable_names(existing_variables))
        missing_declarations = [name for name in new_roots if name not in declared_existing]
        if missing_declarations:
            variables_file = by_name.get(variables_name)
            if not variables_file:
                raise ValueError(
                    "Azure creation added new tfvars root variable(s) but did not return `variables.tf`. "
                    f"Foundry must append declarations for: {', '.join(missing_declarations)} while preserving the complete existing file."
                )
            generated_variables = str(variables_file.get("content") or "")
            _validate_agent_full_file_preservation_for_write(
                existing_variables,
                generated_variables,
                variables_name,
                "azure_consumer_generation",
            )
            declared_generated = set(_extract_root_variable_names(generated_variables))
            still_missing = [name for name in missing_declarations if name not in declared_generated]
            if still_missing:
                raise ValueError(
                    "Azure `variables.tf` is missing declaration(s) required by the new tfvars values: "
                    + ", ".join(still_missing)
                )
    return agent_result


def enforce_real_module_inputs(agent_result: dict, retrieved_module_context: list) -> dict:
    active = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    if not active.get("active"):
        return _VALIDATED_PREVIOUS_ENFORCE_REAL_INPUTS(agent_result, retrieved_module_context)
    if not isinstance(agent_result, dict) or str(agent_result.get("workflow") or "") != "azure_consumer_generation":
        return _VALIDATED_PREVIOUS_ENFORCE_REAL_INPUTS(agent_result, retrieved_module_context)
    value_context = list(getattr(enforce_real_module_inputs, "_active_retrieved_value_context", []) or [])
    return _teams_validate_azure_consumer_agent_output(agent_result, retrieved_module_context, value_context)


def ensure_azure_consumer_variables_tf_file(agent_result: dict, retrieved_value_context: list | None = None) -> dict:
    """Teams: validate only; never append variables.tf in backend."""
    if (_ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}).get("active"):
        return agent_result
    return _VALIDATED_PREVIOUS_ENSURE_AZURE_VARIABLES(agent_result, retrieved_value_context)


def _repair_azure_consumer_variables_tf_files_in_agent_result(agent_result: dict) -> dict:
    """Teams: malformed HCL is a Foundry repair-loop error, not backend repair."""
    if (_ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}).get("active"):
        for item in agent_result.get("files") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("filename") or item.get("path") or "")
            if name.endswith((".tf", ".tfvars")):
                _validate_hcl_content_complete(name, str(item.get("content") or ""))
        return agent_result
    return _VALIDATED_PREVIOUS_REPAIR_AZURE_VARIABLES(agent_result)


def _teams_aws_materialize_repo_aligned_consumer(
    agent_result: dict,
    proposed_module_path: str,
    environment_path: str,
    context_pack: dict,
) -> dict:
    """Validator-only Teams AWS consumer step; Foundry returns the full file."""
    if not (_ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}).get("active"):
        return _VALIDATED_PREVIOUS_AWS_MATERIALIZER(agent_result, proposed_module_path, environment_path, context_pack)
    updated = dict(agent_result or {})
    module_path = _sanitize_aws_module_rel_path(proposed_module_path)
    consumer_files = _aws_consumer_files_from_agent_result(updated.get("files") or [])
    if not consumer_files:
        raise ValueError("AWS module creation must return the repository consumer file generated by Foundry.")
    found_reference = False
    for file_data in consumer_files:
        filename = normalize_tf_relative_path(file_data.get("filename") or "")
        if not filename.startswith(str(environment_path or "").strip().strip("/") + "/"):
            continue
        content = str(file_data.get("content") or "")
        for ref in _extract_aws_module_source_refs_from_text(content):
            if ref.get("module_path") == module_path:
                found_reference = True
        branch = str(((context_pack or {}).get("repo_profile") or {}).get("source_branch") or "").strip()
        if branch:
            try:
                existing = github_get_file_content(
                    "aws", filename, branch, repo_target="tf-devops", workflow="aws_module_creation"
                )
            except Exception:
                existing = None
            if existing:
                _validate_agent_full_file_preservation_for_write(existing, content, filename, "aws_module_creation")
    if not found_reference:
        raise ValueError(f"AWS creation consumer output does not reference `{AWS_MODULES_ROOT}/{module_path}`.")
    return updated


def _teams_materialize_azure_object_backed_creation(*args, **kwargs):
    """Disabled for Teams: backend must never synthesize Azure Terraform."""
    if (_ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}).get("active"):
        return None
    return _VALIDATED_PREVIOUS_AZURE_OBJECT_MATERIALIZER(*args, **kwargs)


def _teams_commit_side_flag_guarantee(*args, **kwargs):
    """Disabled for Teams: missing flags must be repaired by Foundry, not patched."""
    if (_ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}).get("active"):
        return None
    return _VALIDATED_PREVIOUS_COMMIT_FLAG_GUARANTEE(*args, **kwargs)


def _teams_ensure_flag_enable_in_env_values(
    agent_result: dict,
    prompt: str,
    retrieved_value_context: list,
    cloud: str = "",
    workflow: str = "",
) -> dict:
    """Teams backend does not create/toggle flags; it validates agent output later."""
    if (_ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}).get("active"):
        return agent_result
    return _VALIDATED_PREVIOUS_ENSURE_FLAG_VALUES(
        agent_result,
        prompt,
        retrieved_value_context,
        cloud=cloud,
        workflow=workflow,
    )

# =============================================================================
# 2026-08-19 GENERIC REPOSITORY-DRIVEN CHANGE STRATEGY — FINAL OVERRIDE
# =============================================================================
# Foundry owns every semantic infrastructure decision and every Terraform/HCL
# edit. The backend only retrieves live repository evidence, validates literal
# repository facts/preservation, and transports Foundry's complete final files.
# No resource, environment, flag, module, or repository-specific mapping is
# encoded in this override.

_GENERIC_STRATEGY_PREVIOUS_BUILD_CONTEXT = build_backend_existing_infra_modification_context
_GENERIC_STRATEGY_PREVIOUS_BOOL_VALIDATOR = _validate_selected_boolean_is_only_file_change
_GENERIC_STRATEGY_PREVIOUS_NORMALIZE_MODULE_VARIABLES = normalize_module_variables_tf_content
_GENERIC_STRATEGY_PREVIOUS_AZURE_COMMIT_VALIDATOR = validate_azure_consumer_two_file_payload_for_commit


def _repository_boolean_scope_ranges(content: str) -> list[dict]:
    """Return balanced top-level HCL block ranges for descriptive validation.

    This is structural parsing only. It does not infer what any block or Boolean
    means and it never mutates repository content.
    """
    text = str(content or "")
    ranges: list[dict] = []
    for match in _top_level_tf_block_matches(text):
        brace_start = text.find("{", match.end() - 1)
        block_end = _find_balanced_curly_end(text, brace_start)
        if brace_start < 0 or block_end < 0:
            continue
        header = text[match.start():brace_start].strip()
        ranges.append({
            "start": match.start(),
            "end": block_end,
            "header": re.sub(r"\s+", " ", header),
        })
    return ranges


def _repository_literal_boolean_inventory(repository_evidence: list[dict]) -> list[dict]:
    """Index literal Boolean assignments from any supplied Terraform evidence.

    The inventory is intentionally resource-agnostic. It includes literal
    assignments in .tf and .tfvars files and records their exact line number and
    enclosing top-level block, when one exists. Foundry decides which (if any)
    implements the user's requested behavior.
    """
    inventory: list[dict] = []
    for item in repository_evidence or []:
        if not isinstance(item, dict):
            continue
        path = _teams_context_file_identity(item)
        content = str(item.get("content") or "")
        if not path or not content or not path.endswith((".tf", ".tfvars")):
            continue

        ranges = _repository_boolean_scope_ranges(content)
        offset = 0
        for line_number, line in enumerate(content.replace("\r\n", "\n").splitlines(), start=1):
            match = re.match(
                r'^(\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*=\s*)(true|false)(\s*(?:#.*)?)$',
                line,
                re.IGNORECASE,
            )
            line_start = offset
            offset += len(line) + 1
            if not match:
                continue

            containing = [entry for entry in ranges if entry["start"] <= line_start < entry["end"]]
            scope = max(containing, key=lambda entry: entry["start"]) if containing else None
            inventory.append({
                "path": path,
                "line_number": line_number,
                "flag": match.group(2),
                "current_value": match.group(4).lower(),
                "scope": str((scope or {}).get("header") or "top-level assignment"),
                "exact_line": line,
            })
    return inventory


def _teams_shared_context_for_repository_decision(prompt: str) -> tuple[str, list[dict], dict]:
    """Retrieve durable context plus CURRENT live evidence for target selection.

    Semantic flag/module selection happens before the ordinary generation
    ``call_agent`` path, so relying only on call_agent's context injection meant
    stored resource mappings were invisible during the decision that chooses a
    Boolean/module. This helper makes the same repository context available to
    the semantic decision call and re-reads every referenced evidence path from
    the current repository branch.
    """
    active = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    cloud = str(active.get("cloud") or "").strip()
    repo_target = str(active.get("repo_target") or "").strip()
    workflow = str(active.get("workflow") or "").strip()
    owner, repo = _repository_context_repo_identity(cloud, repo_target, workflow, str(active.get("repo_name") or ""))
    if not owner or not repo:
        return "", [], {}
    preferred_branch = str(active.get("context_branch") or active.get("existing_branch") or active.get("source_branch") or "").strip()
    branch, current_sha = _repository_context_branch_and_sha(owner, repo, preferred_branch)
    try:
        search_result = shared_repository_context.search_repository_context(
            repo_owner=owner,
            repo_name=repo,
            query=str(prompt or "").strip(),
            current_commit_sha=current_sha,
            top_k=8,
        )
        required_ids = [
            str(value).strip()
            for value in (active.get("required_repository_context_ids") or [])
            if str(value).strip()
        ]
        if required_ids:
            merged = [dict(item) for item in (search_result.get("results") or []) if isinstance(item, dict)]
            present = {str(item.get("id") or "").strip() for item in merged}
            for context_id in required_ids:
                if context_id in present:
                    continue
                record = shared_repository_context.get_repository_context_by_id(context_id)
                if record is None or str(record.repo_full_name or "").lower() != f"{owner}/{repo}".lower():
                    continue
                merged.insert(0, {
                    "id": record.id, "category": record.category, "subject": record.subject,
                    "scope": record.scope, "statement": record.statement,
                    "evidence_paths": list(record.evidence_paths or []),
                    "evidence_commit_sha": record.evidence_commit_sha,
                    "evidence_branch": record.evidence_branch, "status": record.status,
                    "confidence": record.confidence,
                    "conflict_with_ids": list(record.conflict_with_ids or []), "stale": False,
                })
                present.add(context_id)
            search_result = dict(search_result or {})
            search_result["results"] = merged
        block = shared_repository_context.format_repository_context_for_agent(search_result)
        LOGGER.info(
            "[TerrabotDiag] event=repository_context_semantic_selection_complete repo=%s/%s results=%s ids=%s",
            owner, repo, len(search_result.get("results") or []),
            ",".join(str(item.get("id") or "") for item in (search_result.get("results") or []) if isinstance(item, dict))[:800],
        )
    except Exception as exc:
        LOGGER.warning(
            "[TerrabotDiag] event=repository_context_semantic_decision_search_failed repo=%s/%s error=%s",
            owner, repo, exc,
        )
        return "", [], {}
    live_files = _teams_repository_context_live_files(owner, repo, branch, search_result)
    metadata = {
        "repository": f"{owner}/{repo}",
        "branch": branch,
        "current_commit_sha": current_sha,
        "result_count": len(search_result.get("results") or []),
        "stale_count": int(search_result.get("stale_count") or 0),
        "conflicted_count": int(search_result.get("conflicted_count") or 0),
        "context_ids": [
            str(item.get("id") or "") for item in (search_result.get("results") or [])
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        ],
    }
    return block, live_files, metadata


def _foundry_repository_change_strategy(
    prompt: str,
    repository_evidence: list[dict],
) -> dict:
    """Ask Foundry whether the request uses an existing Boolean repository gate.

    This semantic classification is deliberately action- and resource-agnostic.
    It covers creation, enablement, disablement, modification, and deletion
    without a Python keyword table. Foundry may choose a Boolean only when live
    repository semantics prove that the Boolean is the repository's mechanism
    for the requested operation.
    """
    evidence = [
        {"path": _teams_context_file_identity(item), "content": str(item.get("content") or "")}
        for item in repository_evidence or []
        if isinstance(item, dict) and _teams_context_file_identity(item) and str(item.get("content") or "")
    ]
    inventory = _repository_literal_boolean_inventory(repository_evidence)
    if not evidence:
        return {"operation": "unknown", "boolean_applicable": False, "candidates": [], "inventory": inventory}

    shared_context_block, shared_context_live_files, shared_context_metadata = (
        _teams_shared_context_for_repository_decision(prompt)
    )

    request = {
        "task": (
            "Infer the repository implementation strategy for the CURRENT infrastructure request from live evidence. "
            "Decide whether an existing literal Boolean assignment is the repository-proven mechanism for this request. "
            "This is semantic analysis only; do not generate or rewrite Terraform."
        ),
        "user_request": str(prompt or "").strip(),
        "repository_evidence": evidence,
        "literal_boolean_inventory": inventory,
        "shared_repository_context": shared_context_block,
        "shared_repository_context_live_files": shared_context_live_files,
        "shared_repository_context_metadata": shared_context_metadata,
        "required_output": {
            "operation": "create|enable|disable|modify|delete|unknown",
            "boolean_applicable": "boolean",
            "reason": "short repository-grounded explanation",
            "candidates": [{
                "path": "exact path from literal_boolean_inventory",
                "line_number": 1,
                "flag": "exact flag from literal_boolean_inventory",
                "current_value": "true|false",
                "new_value": "true|false",
                "confidence": 0.0,
                "description": "what this Boolean controls in repository terms",
            }],
        },
        "rules": [
            "Return JSON only with operation, boolean_applicable, reason, candidates.",
            "Infer operation from the user's meaning; the backend does not provide an action-keyword mapping.",
            "Choose only entries that literally exist in literal_boolean_inventory; never invent a path, line, flag, module, resource, or value.",
            "Set boolean_applicable=true only when repository evidence proves that changing an existing Boolean is the minimal correct implementation of the CURRENT request.",
            "A create request may use an existing Boolean only when the resource/consumer definition already exists and the repository uses that Boolean to materialize/activate it.",
            "A delete request may use an existing Boolean only when repository evidence proves that changing the Boolean is the established decommission/removal mechanism; otherwise deletion must remain a normal code-generation request.",
            "For ordinary modifications, use a Boolean only when that Boolean directly implements the requested behavior; do not convert arbitrary setting changes into feature-flag changes.",
            "Include only candidates whose literal value must change. current_value and new_value must differ.",
            "Do not return unrelated Booleans merely because their names share words with the user request.",
            "The user may use colloquial wording, synonyms, abbreviations, or a phrase that does not literally occur in the flag name. Resolve meaning from the surrounding module/resource wiring, comments, variable names, and shared repository context rather than requiring token overlap with the identifier.",
            "When a colloquial request maps to one live repository control after reading the complete relevant file, prefer that single control even when the prompt contains none of the exact underscore-separated words from the flag.",
            "When shared_repository_context contains a prior resource/alias mapping, treat it only as a semantic hint and verify it against shared_repository_context_live_files plus repository_evidence. If the current live file still proves the mapping, use that concrete control without asking the user for a file/path/flag/module name.",
            "If a stored mapping is stale, conflicted, missing from the current live file, or contradicted by repository_evidence, ignore it and resolve from current live repository evidence instead.",
            "When one candidate is materially strongest, return only that candidate. Return multiple candidates only for genuine semantic ambiguity.",
            "Prefer boolean_applicable=false over a weak or speculative Boolean match.",
        ],
    }
    try:
        raw = call_named_agent(json.dumps(request, ensure_ascii=False), AGENT_NAME)
        parsed = extract_json_from_text(raw)
        if not isinstance(parsed, dict):
            parsed = {}
    except Exception as exc:
        LOGGER.warning("Generic repository strategy classification failed: %s", exc)
        parsed = {"operation": "unknown", "boolean_applicable": False, "reason": str(exc), "candidates": []}
    parsed["inventory"] = inventory
    return parsed


def _validated_repository_boolean_strategy_stage1(
    prompt: str,
    repository_evidence: list[dict],
) -> tuple[dict, list[dict]]:
    """Validate Foundry-selected Boolean candidates against literal live evidence."""
    strategy = _foundry_repository_change_strategy(prompt, repository_evidence)
    if not strategy.get("boolean_applicable"):
        return strategy, []

    inventory = strategy.get("inventory") or []
    literal_index = {
        (
            str(item.get("path") or "").strip().strip("/"),
            int(item.get("line_number") or 0),
            str(item.get("flag") or "").strip(),
        ): item
        for item in inventory
        if isinstance(item, dict)
    }
    validated: list[dict] = []
    seen: set[tuple[str, int, str]] = set()
    for candidate in strategy.get("candidates") or []:
        if not isinstance(candidate, dict):
            continue
        path = str(candidate.get("path") or "").strip().strip("/")
        flag = str(candidate.get("flag") or "").strip()
        try:
            line_number = int(candidate.get("line_number") or 0)
        except (TypeError, ValueError):
            line_number = 0
        key = (path, line_number, flag)
        literal = literal_index.get(key)
        if not literal or key in seen:
            continue
        current = str(candidate.get("current_value") or "").strip().lower()
        target = str(candidate.get("new_value") or "").strip().lower()
        if current not in {"true", "false"} or target not in {"true", "false"}:
            continue
        if current == target or current != literal.get("current_value"):
            continue
        try:
            confidence = max(0.0, min(float(candidate.get("confidence") or 0.0), 1.0))
        except (TypeError, ValueError):
            confidence = 0.0
        seen.add(key)
        validated.append({
            **literal,
            "new_value": target,
            "confidence": confidence,
            "context": str(candidate.get("description") or "").strip(),
            "description": str(candidate.get("description") or "").strip(),
            "classification_reason": str(strategy.get("reason") or "").strip(),
            "operation": str(strategy.get("operation") or "unknown").strip().lower(),
        })

    ranked = sorted(validated, key=lambda item: float(item.get("confidence") or 0.0), reverse=True)
    if len(ranked) > 1:
        top = float(ranked[0].get("confidence") or 0.0)
        second = float(ranked[1].get("confidence") or 0.0)
        if top >= 0.80 and top - second >= 0.15:
            ranked = [ranked[0]]
    return strategy, ranked
_validated_repository_boolean_strategy = _validated_repository_boolean_strategy_stage1


def _teams_azure_boolean_resolution_phases(
    prompt: str,
    repository_evidence: list[dict],
    scope_root: str = "",
) -> list[list[dict]]:
    """Return ordered evidence phases for Azure enable/disable resolution.

    A normal hub request must never let a sibling ``dr.tfvars`` compete with
    ``hub.tfvars``.  Foundry still owns the semantic mapping from user wording
    to a repository Boolean, but it receives the value files in repository
    precedence order: hub -> tier -> common.  For an explicit DR/failover
    request, dr.tfvars is the leaf value file instead.

    Non-tfvars Terraform evidence is included in every phase so Foundry can
    infer what a Boolean controls from module/resource wiring without asking
    the user for a flag or file name.
    """
    intent = _teams_feature_flag_intent(prompt)
    if intent not in {"enable", "disable"}:
        return [list(repository_evidence or [])]

    evidence = [item for item in (repository_evidence or []) if isinstance(item, dict)]
    non_values = [
        item for item in evidence
        if not _teams_context_file_identity(item).lower().endswith((".tfvars", ".tfvars.json"))
    ]
    value_items = [
        item for item in evidence
        if _teams_context_file_identity(item).lower().endswith((".tfvars", ".tfvars.json"))
    ]
    if not value_items:
        return [evidence]

    text = normalize_yes_no_reply(prompt)
    dr_requested = bool(re.search(
        r"(?<![a-z0-9])(dr|disaster recovery|failover|secondary)(?![a-z0-9])",
        text,
    ))
    preferred_basenames = (
        ("dr.tfvars", "tier.tfvars", "common.tfvars")
        if dr_requested
        else _TEAMS_FLAG_VALUES_BASENAME_PRIORITY
    )

    normalized_scope = str(scope_root or "").strip().strip("/")
    phases: list[list[dict]] = []
    used_paths: set[str] = set()

    for basename in preferred_basenames:
        matches: list[dict] = []
        for item in value_items:
            path = _teams_context_file_identity(item).strip().strip("/")
            if not path or path in used_paths:
                continue
            if path.rsplit("/", 1)[-1].lower() != basename:
                continue
            if normalized_scope:
                # Leaf hub/dr files belong to the exact environment folder.
                # tier/common may be inherited from a direct parent/root and
                # are therefore allowed outside the leaf scope.
                if basename in {"hub.tfvars", "dr.tfvars"} and not path.startswith(normalized_scope.rstrip("/") + "/"):
                    continue
            matches.append(item)
        if not matches:
            continue
        for item in matches:
            used_paths.add(_teams_context_file_identity(item).strip().strip("/"))
        phases.append(_teams_merge_repository_evidence(non_values, matches))

    # Never reintroduce dr.tfvars into a normal environment request. If none of
    # the preferred files were present, keep non-DR value evidence only.
    if not phases:
        allowed_values = []
        for item in value_items:
            path = _teams_context_file_identity(item).lower()
            if not dr_requested and path.endswith("/dr.tfvars"):
                continue
            allowed_values.append(item)
        phases.append(_teams_merge_repository_evidence(non_values, allowed_values))

    return [phase for phase in phases if phase] or [evidence]


def _teams_resolve_repository_boolean_strategy(
    prompt: str,
    repository_evidence: list[dict],
    scope_root: str = "",
) -> tuple[dict, list[dict], list[dict]]:
    """Run semantic Boolean resolution in repository precedence order.

    Returns ``(strategy, candidates, evidence_used)``.  The first phase that
    yields a backend-validated literal Boolean wins.  If no phase yields a
    Boolean, the final strategy result is returned so ordinary non-Boolean
    modification generation can continue unchanged.
    """
    phases = _teams_azure_boolean_resolution_phases(prompt, repository_evidence, scope_root)
    last_strategy: dict = {}
    last_phase: list[dict] = list(repository_evidence or [])
    for phase in phases:
        strategy, candidates = _validated_repository_boolean_strategy(prompt, phase)
        last_strategy = strategy
        last_phase = phase
        if candidates:
            return strategy, candidates, phase

        # Foundry semantic classification is primary. If it declines a Boolean
        # even though the preferred repository value file contains one unique,
        # high-confidence prompt/identifier match, use the existing generic
        # backend selector as a safety fallback. This selector is resource-
        # agnostic, tie-safe, and operates only on literal live-repository
        # assignments; it never invents a flag or path. The fallback prevents
        # "tell me the exact variable/file" questions for self-answerable
        # requests such as disabling a homepage application whose repo flag is
        # named aca_app_homepage_bff_enabled.
        fallback_context = {
            "matched_files": list(phase),
            "environment_files": list(phase),
            "selection_state": "candidate_selection_required",
        }
        selected = _teams_auto_select_feature_flag_context_stage1(
            fallback_context,
            prompt,
        )
        selected_files = list((selected or {}).get("matched_files") or [])
        if (selected or {}).get("feature_flag_selection") and len(selected_files) == 1:
            selected_item = selected_files[0]
            match = dict(selected_item.get("feature_flag_match") or {})
            path = _teams_context_file_identity(selected_item)
            flag = str(match.get("flag") or "").strip()
            current = str(match.get("current_value") or "").strip().lower()
            target = str(match.get("new_value") or "").strip().lower()
            try:
                line_number = int(match.get("line") or 0)
            except (TypeError, ValueError):
                line_number = 0
            if path and flag and line_number > 0 and current in {"true", "false"} and target in {"true", "false"} and current != target:
                candidate = {
                    "path": path,
                    "line_number": line_number,
                    "flag": flag,
                    "current_value": current,
                    "new_value": target,
                    "confidence": 1.0,
                    "context": str(match.get("context") or "").strip(),
                    "description": "Unique live-repository Boolean matched by prompt semantics after Foundry declined a Boolean strategy.",
                    "classification_reason": "deterministic repository Boolean fallback after semantic classifier returned no candidate",
                    "operation": _teams_feature_flag_intent(prompt),
                }
                fallback_strategy = {
                    "operation": _teams_feature_flag_intent(prompt),
                    "boolean_applicable": True,
                    "reason": (
                        "Foundry returned no Boolean candidate, but live repository evidence contained one unique "
                        "high-confidence literal Boolean matching the requested feature in the preferred values file."
                    ),
                    "fallback": "unique_literal_boolean_semantic_match",
                }
                return fallback_strategy, [candidate], phase
    return last_strategy, [], last_phase


def build_backend_existing_infra_modification_context(
    prompt: str,
    thread_id: str,
    cloud: str,
    workflow: str,
    retrieved_value_context: list | None = None,
) -> dict:
    """Generic Teams repository strategy with Foundry-owned semantics.

    The prior repository retriever remains intact. This final layer removes any
    AWS/main.tf/resource-name dependency from feature-flag selection by running
    the same semantic Boolean strategy over all live Terraform evidence already
    gathered for the resolved request.
    """
    context = _GENERIC_STRATEGY_PREVIOUS_BUILD_CONTEXT(
        prompt,
        thread_id,
        cloud,
        workflow,
        retrieved_value_context=retrieved_value_context,
    )
    active = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    if not active.get("active") or str(workflow or "").strip() not in INFRA_MODIFICATION_WORKFLOWS:
        return context

    context = dict(context or {})

    # Re-read the resolved environment evidence independently of any earlier
    # feature-flag shortcut. This prevents a prior AWS/main.tf-only classifier
    # from narrowing the evidence before the generic strategy runs. Repository
    # discovery remains structural; Foundry performs all semantic selection.
    extra_environment_evidence: list[dict] = []
    try:
        normalized_cloud = normalize_cloud(cloud)
        repo_target = normalize_repo_target(normalized_cloud, workflow=workflow)
        branch = str(context.get("context_ref") or "").strip() or _teams_remote_context_branch(
            normalized_cloud, repo_target, workflow
        )
        extra_environment_evidence, _write_paths, _debug = _teams_environment_folder_evidence(
            prompt, normalized_cloud, repo_target, workflow, branch
        )
    except Exception as exc:
        LOGGER.debug("Generic strategy environment evidence refresh skipped: %s", exc)

    evidence = _teams_merge_repository_evidence(
        list(context.get("matched_files") or []) + list(context.get("environment_files") or []),
        extra_environment_evidence,
    )
    if not evidence:
        return context

    # Critical: environment discovery stores bounded snippets (20k chars per
    # file). A Boolean near the end of a large hub.tfvars/tier.tfvars therefore
    # did not enter literal_boolean_inventory and Foundry was incorrectly told
    # there was no repository-proven control. Rehydrate the already-resolved
    # Terraform evidence from the same live branch before Boolean inventory and
    # semantic classification.
    try:
        evidence = _teams_rehydrate_repository_evidence_full_contents(
            evidence, normalized_cloud, repo_target, workflow, branch
        )
    except Exception as exc:
        LOGGER.debug("Full Teams repository evidence rehydration skipped: %s", exc)

    if normalized_cloud == "azure":
        strategy, candidates, strategy_evidence = _teams_resolve_repository_boolean_strategy(
            prompt,
            evidence,
            scope_root=str(context.get("scope_root") or ""),
        )
        # Keep the resolved evidence visible to downstream generation.  For a
        # normal hub request this deliberately excludes dr.tfvars, preventing
        # a later agent turn from switching away from the already-resolved hub.
        evidence = strategy_evidence or evidence
    else:
        strategy, candidates = _validated_repository_boolean_strategy(prompt, evidence)
    context["repository_change_strategy"] = {
        "operation": str(strategy.get("operation") or "unknown"),
        "boolean_applicable": bool(candidates),
        "reason": str(strategy.get("reason") or ""),
    }

    # A non-Boolean result remains a normal Foundry generation request. The
    # backend supplies live files but does not select or edit a resource.
    if not candidates:
        context.pop("feature_flag_selection", None)
        context["matched_files"] = evidence
        context["matched_file_paths"] = [_teams_context_file_identity(item) for item in evidence]
        context["selection_state"] = "selected"
        context["selected_path"] = ""
        context["agent_resolves_target"] = True
        context["instructions"] = list(context.get("instructions") or []) + [
            "Foundry classified this request as not safely reducible to an existing literal Boolean gate. Continue with repository-semantic generation for the requested create/modify/delete operation.",
            "Generate the minimal repository delta from live evidence. The backend validates and transports only; it never constructs, merges, repairs, appends, removes, or toggles Terraform.",
        ]
        return context

    evidence_by_path = {
        _teams_context_file_identity(item): item
        for item in evidence
        if isinstance(item, dict) and _teams_context_file_identity(item)
    }
    matched: list[dict] = []
    for candidate in candidates:
        source = dict(evidence_by_path.get(str(candidate.get("path") or "").strip().strip("/")) or {})
        if not source:
            continue
        source["feature_flag_match"] = dict(candidate)
        source["reason"] = "Foundry semantic Boolean strategy validated against exact live repository assignment"
        matched.append(source)
    if not matched:
        return context

    context["matched_files"] = matched
    context["matched_file_paths"] = list(dict.fromkeys(_teams_context_file_identity(item) for item in matched))
    context["feature_flag_selection"] = True
    context["agent_resolves_target"] = False
    context["instructions"] = [
        "Foundry semantically proved that the CURRENT request is implemented by an existing literal Boolean assignment and the backend verified the exact live path/line/value.",
        "Use only feature_flag_match. Do not infer another flag or edit any unrelated repository content.",
        "Return the COMPLETE final selected file with only feature_flag_match.current_value changed to feature_flag_match.new_value on feature_flag_match.line_number.",
        "Preserve every other line exactly. The backend performs exact-diff validation and will block unrelated changes without synthesizing a repair.",
    ]
    if len(matched) == 1:
        context["selection_state"] = "selected"
        context["selected_path"] = _teams_context_file_identity(matched[0])
    else:
        context["selection_state"] = "candidate_selection_required"
        context["selected_path"] = ""
    return context


def _validate_selected_boolean_is_only_file_change(
    existing_content: str,
    generated_content: str,
    path: str,
) -> None:
    """Require exactly the validated Boolean line to change, independent of resource type."""
    match = _selected_feature_flag_match_from_active_context(path)
    if not match:
        return _GENERIC_STRATEGY_PREVIOUS_BOOL_VALIDATOR(existing_content, generated_content, path)

    flag = str(match.get("flag") or "").strip()
    current = str(match.get("current_value") or "").strip().lower()
    target = str(match.get("new_value") or "").strip().lower()
    try:
        line_number = int(match.get("line_number") or 0)
    except (TypeError, ValueError):
        line_number = 0
    if not flag or line_number <= 0 or current not in {"true", "false"} or target not in {"true", "false"} or current == target:
        raise UnsafeGeneratedChangeError("Selected Boolean repository context is incomplete or invalid.")

    existing_lines = (existing_content or "").replace("\r\n", "\n").splitlines()
    generated_lines = (generated_content or "").replace("\r\n", "\n").splitlines()
    if len(existing_lines) != len(generated_lines):
        raise UnsafeGeneratedChangeError(
            f"Generated Boolean modification for {path} added or removed lines; only the selected literal Boolean may change."
        )
    if line_number > len(existing_lines):
        raise UnsafeGeneratedChangeError("Selected Boolean line no longer exists in the live repository file.")

    assignment = re.compile(
        rf'^(\s*){re.escape(flag)}(\s*=\s*)(true|false)(\s*(?:#.*)?)$',
        re.IGNORECASE,
    )
    changed_lines = [index for index, pair in enumerate(zip(existing_lines, generated_lines), start=1) if pair[0] != pair[1]]
    if changed_lines != [line_number]:
        raise UnsafeGeneratedChangeError(
            f"Generated Boolean modification for {path} changed unrelated repository content. "
            f"Only line {line_number} (`{flag}`) may change."
        )
    old_match = assignment.match(existing_lines[line_number - 1])
    new_match = assignment.match(generated_lines[line_number - 1])
    if not old_match or not new_match:
        raise UnsafeGeneratedChangeError("The selected Boolean assignment was structurally changed instead of only toggling its literal value.")
    if old_match.group(3).lower() != current or new_match.group(3).lower() != target:
        raise UnsafeGeneratedChangeError(
            f"Generated Boolean modification for {path} has the wrong transition; expected {current} -> {target}."
        )
    if old_match.group(1) != new_match.group(1) or old_match.group(2) != new_match.group(2) or old_match.group(4) != new_match.group(4):
        raise UnsafeGeneratedChangeError("The selected Boolean line was reformatted; only the literal true/false value may change.")


def normalize_module_variables_tf_content(
    content: str,
    filename: str,
    workflow: str,
    user_prompt: str = "",
) -> tuple[str, list[str]]:
    """Teams backend is validation/transport only; never rewrite Foundry HCL."""
    if (_ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}).get("active"):
        issues: list[str] = []
        if filename.endswith(("variables.tf", "vars.tf")):
            for item in _iter_variable_blocks_with_names(content or ""):
                block = str(item.get("block") or "")
                name = str(item.get("name") or "")
                if not _variable_attr_present(block, "description"):
                    issues.append(f'variable "{name}" is missing description')
                if not _variable_attr_present(block, "type"):
                    issues.append(f'variable "{name}" is missing type')
        return str(content or ""), issues
    return _GENERIC_STRATEGY_PREVIOUS_NORMALIZE_MODULE_VARIABLES(
        content,
        filename,
        workflow,
        user_prompt=user_prompt,
    )


def validate_azure_consumer_two_file_payload_for_commit(agent_result: dict) -> None:
    """Teams commit guard validates Foundry files but never repairs them."""
    if not (_ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}).get("active"):
        return _GENERIC_STRATEGY_PREVIOUS_AZURE_COMMIT_VALIDATOR(agent_result)
    if not isinstance(agent_result, dict):
        return
    if safe_normalize_cloud(agent_result.get("cloud")) != "azure":
        return
    if str(agent_result.get("workflow") or "").strip() != "azure_consumer_generation":
        return
    routing_summary = agent_result.get("routing_summary") or {}
    files = [item for item in (agent_result.get("files") or []) if isinstance(item, dict)]
    filenames = {
        normalize_agent_relative_tf_path(str(item.get("filename") or item.get("path") or ""), "azure")
        for item in files
    }
    required = [
        normalize_agent_relative_tf_path(str(routing_summary.get(key) or ""), "azure")
        for key in ("consumer_file", "tfvars_file")
        if str(routing_summary.get(key) or "").strip()
    ]
    missing = [name for name in required if name not in filenames]
    if missing:
        raise ValueError("Azure consumer output is missing backend-routed Foundry file(s): " + ", ".join(missing))
    for item in files:
        name = normalize_agent_relative_tf_path(str(item.get("filename") or item.get("path") or ""), "azure")
        if name.endswith((".tf", ".tfvars")):
            _validate_hcl_content_complete(name, str(item.get("content") or ""))

# =============================================================================
# 2026-08-19 THREE-MODE FOUNDRY OUTPUT ENFORCEMENT — FINAL OVERRIDE
# =============================================================================
# Foundry owns Terraform generation. The backend only retrieves repository
# truth, classifies the write policy from already-resolved workflow context,
# validates the returned full file, and transports it. It never edits HCL.

_THREE_MODE_PREVIOUS_FULL_FILE_VALIDATOR = _validate_agent_full_file_preservation_for_write


def _teams_active_repository_change_strategy() -> dict:
    """Return the already-resolved repository strategy for the active Teams turn."""
    active = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    value_context = active.get("retrieved_value_context") or []
    context = _get_backend_existing_infra_context(value_context)
    if not isinstance(context, dict):
        return {}
    strategy = context.get("repository_change_strategy") or {}
    return dict(strategy) if isinstance(strategy, dict) else {}


def _teams_validation_change_mode(path: str, workflow: str | None) -> str:
    """Choose validation mode without resource-, repo-, path-, or flag-name maps.

    Semantic resource/flag selection remains Foundry-owned. The backend uses
    only the validated Boolean evidence and the already-resolved operation.
    """
    if _selected_feature_flag_match_from_active_context(path):
        return "boolean"

    active = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    if not active.get("active"):
        return "legacy"

    strategy = _teams_active_repository_change_strategy()
    operation = str(strategy.get("operation") or "").strip().lower()
    if operation in {"create", "creation", "add", "provision", "deploy"}:
        return "create"
    if operation in {"modify", "modification", "update", "delete", "deletion", "remove"}:
        return "modify"

    effective_prompt = str(active.get("effective_prompt") or "").strip()
    if effective_prompt and _teams_is_existing_invocation_creation(effective_prompt):
        return "create"

    if str(workflow or "").strip() in INFRA_MODIFICATION_WORKFLOWS:
        return "modify"
    return "legacy"


def _validate_foundry_append_only_existing_file(
    existing_content: str,
    generated_content: str,
    path: str,
) -> None:
    """Creation in an existing file must be exact-prefix + non-empty append."""
    existing = str(existing_content or "")
    generated = str(generated_content or "")
    if not existing:
        return
    if not generated.startswith(existing):
        raise UnsafeGeneratedChangeError(
            f"Creation output for {path} changed existing repository content. "
            "For an existing target file, Foundry must copy the live file byte-for-byte "
            "and append only the newly requested Terraform after the original EOF."
        )
    appended = generated[len(existing):]
    if not appended.strip():
        raise UnsafeGeneratedChangeError(
            f"Creation output for {path} did not append any new Terraform after the live file."
        )


def _validate_foundry_targeted_existing_file_delta(
    existing_content: str,
    generated_content: str,
    path: str,
) -> None:
    """Reject broad rewrites while allowing a bounded, localized Foundry delta.

    This is deliberately semantic-neutral. It does not decide which resource
    should change. It only ensures that a modification leaves the overwhelming
    majority of the live file byte-for-byte unchanged and does not introduce
    formatting-only churn across unrelated lines.
    """
    import difflib
    import math

    existing = str(existing_content or "")
    generated = str(generated_content or "")
    if not existing:
        return
    if existing == generated:
        return

    old_lines = existing.splitlines(keepends=True)
    new_lines = generated.splitlines(keepends=True)
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    changed_existing = 0
    changed_generated = 0
    hunks = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        hunks += 1
        changed_existing += i2 - i1
        changed_generated += j2 - j1

        if tag == "replace":
            old_segment = old_lines[i1:i2]
            new_segment = new_lines[j1:j2]
            if len(old_segment) == len(new_segment) and all(
                re.sub(r"\s+", " ", old.rstrip("\r\n").strip())
                == re.sub(r"\s+", " ", new.rstrip("\r\n").strip())
                for old, new in zip(old_segment, new_segment)
            ):
                raise UnsafeGeneratedChangeError(
                    f"Modification output for {path} contains formatting-only changes. "
                    "Foundry must preserve unrelated spacing and formatting exactly."
                )

    existing_line_count = max(1, len(old_lines))
    changed_total = changed_existing + changed_generated
    # Dynamic safety budgets scale with file size; they are not tied to any
    # repository, environment, resource family, or feature-flag name.
    line_budget = max(20, int(math.ceil(existing_line_count * 0.20)))
    hunk_budget = max(3, int(math.ceil(existing_line_count / 250.0)))

    if changed_total > line_budget or hunks > hunk_budget:
        raise UnsafeGeneratedChangeError(
            f"Modification output for {path} is not a small targeted delta "
            f"({changed_total} changed line entries across {hunks} diff regions). "
            "Foundry must start from the exact live file and alter only the lines required "
            "for the requested existing resource."
        )


def _validate_agent_full_file_preservation_for_write(
    existing_content: str,
    generated_content: str,
    path: str,
    workflow: str | None,
) -> None:
    """Final Teams write policy: Boolean-only, targeted modify, or append-only create."""
    if existing_content is None:
        # A genuinely new file has no pre-existing bytes to preserve. Existing
        # path/routing/HCL validators still apply before transport.
        return _THREE_MODE_PREVIOUS_FULL_FILE_VALIDATOR(
            existing_content,
            generated_content,
            path,
            workflow,
        )

    if _terrabot_placeholder_content_detected(generated_content):
        raise UnsafeGeneratedChangeError(
            f"Generated output for {path} contains a repository-content placeholder. "
            "Foundry must return the complete final file."
        )

    mode = _teams_validation_change_mode(path, workflow)

    if mode == "boolean":
        _validate_selected_boolean_is_only_file_change(
            existing_content,
            generated_content,
            path,
        )
        return

    if mode == "create":
        _validate_foundry_append_only_existing_file(
            existing_content,
            generated_content,
            path,
        )
        return

    if mode == "modify":
        # Keep all existing structural/destructive checks, then add the stricter
        # minimal-diff boundary. Neither validator modifies generated HCL.
        _THREE_MODE_PREVIOUS_FULL_FILE_VALIDATOR(
            existing_content,
            generated_content,
            path,
            workflow,
        )
        _validate_foundry_targeted_existing_file_delta(
            existing_content,
            generated_content,
            path,
        )
        return

    return _THREE_MODE_PREVIOUS_FULL_FILE_VALIDATOR(
        existing_content,
        generated_content,
        path,
        workflow,
    )

# =============================================================================
# 2026-08-20 FINAL FOLLOW-UP + SEMANTIC FLAG RELEVANCE OVERRIDE
# =============================================================================
# Goals:
#   1. Keep a Foundry blocking clarification attached to the same infrastructure
#      request so a compact user answer ("2", a flag name, etc.) resumes generation.
#   2. Before a Boolean picker is shown, make Foundry adjudicate the already
#      repository-validated Boolean candidates and retain only genuinely relevant
#      controls. No resource/flag vocabulary is encoded in Python.
#   3. Leave the existing backend-validation self-correction / repair_edits loop
#      untouched. These overrides only affect semantic candidate selection and
#      multi-turn continuation state.

_RELEVANCE_PREVIOUS_VALIDATED_REPOSITORY_BOOLEAN_STRATEGY = _validated_repository_boolean_strategy
_RELEVANCE_PREVIOUS_PENDING_MAPPINGS = _teams_pending_state_mappings
_RELEVANCE_PREVIOUS_HANDLE_TEAMS_CHAT_REQUEST = handle_teams_chat_request

PENDING_AGENT_INFRA_CLARIFICATIONS: Dict[str, Dict[str, Any]] = {}


def _teams_pending_state_mappings() -> dict[str, dict]:
    """Include generic Foundry infrastructure clarification state in durable state."""
    mappings = dict(_RELEVANCE_PREVIOUS_PENDING_MAPPINGS())
    mappings["pending_agent_infra_clarifications"] = PENDING_AGENT_INFRA_CLARIFICATIONS
    return mappings


def _agent_infra_clarification_key(thread_id: str) -> str:
    thread = str(thread_id or "").strip()
    return hashlib.sha1(f"agent-infra-clarification::{thread}".encode("utf-8")).hexdigest()


def _store_pending_agent_infra_clarification(
    thread_id: str,
    original_prompt: str,
    cloud: str = "",
    workflow: str = "",
    repo_target: str = "",
    question: str = "",
) -> None:
    thread = str(thread_id or "").strip()
    if not thread:
        return
    PENDING_AGENT_INFRA_CLARIFICATIONS[_agent_infra_clarification_key(thread)] = {
        "thread_id": thread,
        "original_prompt": str(original_prompt or "").strip(),
        "cloud": str(cloud or "").strip(),
        "workflow": str(workflow or "").strip(),
        "repo_target": str(repo_target or "").strip(),
        "question": str(question or "").strip(),
    }
    try:
        persist_teams_workflow_state(thread)
    except Exception:
        LOGGER.debug("Could not persist pending agent infrastructure clarification", exc_info=True)


def _get_pending_agent_infra_clarification(thread_id: str) -> dict:
    thread = str(thread_id or "").strip()
    if not thread:
        return {}
    return dict(PENDING_AGENT_INFRA_CLARIFICATIONS.get(_agent_infra_clarification_key(thread)) or {})


def _clear_pending_agent_infra_clarification(thread_id: str) -> None:
    thread = str(thread_id or "").strip()
    if not thread:
        return
    PENDING_AGENT_INFRA_CLARIFICATIONS.pop(_agent_infra_clarification_key(thread), None)
    try:
        persist_teams_workflow_state(thread)
    except Exception:
        LOGGER.debug("Could not persist cleared agent infrastructure clarification", exc_info=True)


def _repository_candidate_context_window(
    repository_evidence: list[dict],
    candidate: dict,
    radius: int = 6,
) -> str:
    """Return a bounded live-code window around one validated Boolean assignment."""
    wanted_path = str(candidate.get("path") or "").strip().strip("/")
    try:
        line_number = int(candidate.get("line_number") or 0)
    except (TypeError, ValueError):
        line_number = 0
    if not wanted_path or line_number <= 0:
        return ""
    for item in repository_evidence or []:
        if not isinstance(item, dict):
            continue
        if _teams_context_file_identity(item) != wanted_path:
            continue
        lines = str(item.get("content") or "").replace("\r\n", "\n").splitlines()
        if not lines:
            return ""
        start = max(0, line_number - 1 - radius)
        end = min(len(lines), line_number + radius)
        return "\n".join(
            f"{index + 1}: {lines[index]}"
            for index in range(start, end)
        )
    return ""


def _foundry_adjudicate_repository_boolean_candidates(
    prompt: str,
    repository_evidence: list[dict],
    candidates: list[dict],
) -> list[dict]:
    """Ask Foundry to prune validated Boolean candidates to prompt-relevant controls.

    Python does not infer which flag implements the request. It only supplies the
    exact repository-validated candidates and nearby live code, then validates
    that Foundry's adjudicated selections are a subset of those candidates.
    """
    if len(candidates or []) <= 1:
        return list(candidates or [])

    candidate_payload = []
    for candidate in candidates or []:
        if not isinstance(candidate, dict):
            continue
        candidate_payload.append({
            "path": str(candidate.get("path") or "").strip().strip("/"),
            "line_number": int(candidate.get("line_number") or 0),
            "flag": str(candidate.get("flag") or "").strip(),
            "current_value": str(candidate.get("current_value") or "").strip().lower(),
            "new_value": str(candidate.get("new_value") or "").strip().lower(),
            "scope": str(candidate.get("scope") or "").strip(),
            "prior_description": str(candidate.get("description") or candidate.get("context") or "").strip(),
            "nearby_live_code": _repository_candidate_context_window(repository_evidence, candidate),
        })

    request = {
        "task": (
            "FINAL SEMANTIC BOOLEAN CANDIDATE ADJUDICATION. The backend has already "
            "proved every candidate below is a real literal Boolean assignment in the live repository. "
            "Select only the candidate(s) that actually implement the CURRENT user request. "
            "Do not generate Terraform."
        ),
        "user_request": str(prompt or "").strip(),
        "validated_candidates": candidate_payload,
        "required_output": {
            "reason": "short repository-grounded explanation",
            "selected": [{
                "path": "exact path from validated_candidates",
                "line_number": 1,
                "flag": "exact flag from validated_candidates",
                "relevance": 0.0,
                "description": "concise explanation of why this control matches the requested behavior",
            }],
        },
        "rules": [
            "Return JSON only with keys reason and selected.",
            "Select only from validated_candidates; never invent or rename a flag/path/line.",
            "Judge semantic relevance from the user request plus scope, nearby_live_code, and repository naming/context.",
            "Do not select a Boolean merely because it is in the same file or because of weak generic lexical overlap with the request.",
            "If exactly one control clearly implements the requested behavior, return exactly one selected item.",
            "Return multiple selected items only when they are genuinely distinct plausible implementations of the same requested behavior and a user choice is truly required.",
            "Omit weak, incidental, infrastructure-wide, and unrelated controls.",
            "Use relevance from 0 to 1. A selected item must be strongly supported by repository semantics, not just lexical overlap.",
            "If none is strongly supported, return selected=[].",
        ],
    }

    try:
        raw = call_named_agent(json.dumps(request, ensure_ascii=False), AGENT_NAME)
        parsed = extract_json_from_text(raw)
    except Exception as exc:
        LOGGER.warning("Boolean candidate adjudication failed; using bounded validated fallback: %s", exc)
        parsed = {}

    original_index = {
        (
            str(item.get("path") or "").strip().strip("/"),
            int(item.get("line_number") or 0),
            str(item.get("flag") or "").strip(),
        ): item
        for item in candidates or []
        if isinstance(item, dict)
    }

    adjudicated: list[dict] = []
    if isinstance(parsed, dict):
        for selected in parsed.get("selected") or []:
            if not isinstance(selected, dict):
                continue
            key = (
                str(selected.get("path") or "").strip().strip("/"),
                int(selected.get("line_number") or 0),
                str(selected.get("flag") or "").strip(),
            )
            original = original_index.get(key)
            if not original:
                continue
            try:
                relevance = max(0.0, min(float(selected.get("relevance") or 0.0), 1.0))
            except (TypeError, ValueError):
                relevance = 0.0
            if relevance < 0.60:
                continue
            item = dict(original)
            item["confidence"] = max(float(item.get("confidence") or 0.0), relevance)
            item["context"] = str(selected.get("description") or item.get("context") or "").strip()
            item["description"] = item["context"]
            adjudicated.append(item)

    if adjudicated:
        adjudicated.sort(key=lambda item: float(item.get("confidence") or 0.0), reverse=True)
        top = float(adjudicated[0].get("confidence") or 0.0)
        # Keep only candidates that remain close to the strongest semantic match.
        # This is resource-agnostic confidence pruning; no flag/resource names are encoded.
        adjudicated = [
            item for item in adjudicated
            if float(item.get("confidence") or 0.0) >= max(0.60, top - 0.18)
        ]
        return adjudicated[:5]

    # If adjudication is unavailable, never expose an unbounded inventory.
    # Preserve the strongest repository-validated candidates only; ambiguity is
    # safer than auto-selecting a weak control.
    fallback = sorted(
        [dict(item) for item in candidates or [] if isinstance(item, dict)],
        key=lambda item: float(item.get("confidence") or 0.0),
        reverse=True,
    )
    if not fallback:
        return []
    top = float(fallback[0].get("confidence") or 0.0)
    if top > 0:
        fallback = [
            item for item in fallback
            if float(item.get("confidence") or 0.0) >= max(0.50, top - 0.15)
        ]
    return fallback[:5]


def _repository_context_unique_boolean_match(
    prompt: str,
    inventory: list[dict],
    operation: str,
) -> list[dict]:
    """Resolve an exact durable context mapping against live environment Booleans.

    Repository context is only a semantic index: a record is accepted here only
    when it names both a live Boolean flag and its current live path. A unique
    match is therefore safe to auto-select and must not trigger clarification.
    """
    active = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    owner, repo = _repository_context_repo_identity(
        str(active.get("cloud") or ""),
        str(active.get("repo_target") or ""),
        str(active.get("workflow") or ""),
        str(active.get("repo_name") or ""),
    )
    if not owner or not repo or not inventory:
        return []
    try:
        branch, current_sha = _repository_context_branch_and_sha(
            owner, repo, str(active.get("context_branch") or active.get("existing_branch") or "")
        )
        search = shared_repository_context.search_repository_context(
            repo_owner=owner, repo_name=repo, query=str(prompt or "").strip(),
            current_commit_sha=current_sha, top_k=8,
        )
    except Exception as exc:
        LOGGER.warning(
            "[TerrabotDiag] event=repository_context_boolean_resolution_search_failed repo=%s/%s error=%s",
            owner, repo, exc,
        )
        return []

    wanted_value = {"create": "true", "enable": "true", "disable": "false", "delete": "false"}.get(
        str(operation or "").strip().lower(), ""
    )
    matches: list[dict] = []
    seen: set[tuple[str, int, str]] = set()
    for record in search.get("results") or []:
        if not isinstance(record, dict) or str(record.get("status") or "active").lower() == "conflicted":
            continue
        record_text = " ".join([
            str(record.get("subject") or ""),
            str(record.get("scope") or ""),
            str(record.get("statement") or ""),
            " ".join(str(value) for value in (record.get("evidence_paths") or [])),
        ]).lower()
        for item in inventory:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "").strip().strip("/")
            flag = str(item.get("flag") or "").strip()
            if not path or not flag or flag.lower() not in record_text or path.lower() not in record_text:
                continue
            current = str(item.get("current_value") or "").strip().lower()
            target = wanted_value or ("false" if current == "true" else "true")
            if target == current:
                continue
            key = (path, int(item.get("line_number") or 0), flag)
            if key in seen:
                continue
            seen.add(key)
            matches.append({
                **item,
                "new_value": target,
                "confidence": max(float(record.get("confidence") or 0.0), 0.99),
                "context": str(record.get("statement") or "").strip(),
                "description": str(record.get("statement") or "").strip(),
                "repository_context_id": str(record.get("id") or "").strip(),
                "operation": str(operation or "unknown").strip().lower(),
            })
    LOGGER.info(
        "[TerrabotDiag] event=repository_context_boolean_resolution_complete repo=%s/%s operation=%s matches=%s context_ids=%s",
        owner, repo, operation, len(matches),
        ",".join(str(item.get("repository_context_id") or "") for item in matches)[:800],
    )
    return matches


def _foundry_repository_boolean_inventory_retry(
    prompt: str,
    repository_evidence: list[dict],
    inventory: list[dict],
    operation_hint: str = "unknown",
) -> dict:
    """Second-pass semantic resolver focused only on live environment Booleans.

    This is deliberately invoked before asking the user. It gives Foundry the
    complete environment files plus a compact literal Boolean inventory so
    colloquial phrases and synonyms can resolve without file/flag questions.
    """
    if not inventory:
        return {"operation": operation_hint or "unknown", "boolean_applicable": False, "candidates": []}
    shared_context_block, shared_context_live_files, shared_context_metadata = (
        _teams_shared_context_for_repository_decision(prompt)
    )
    request = {
        "task": (
            "SECOND-PASS ENVIRONMENT BOOLEAN RESOLUTION. Before any clarification, determine whether the current "
            "create/delete/enable/disable infrastructure request is controlled by one existing Boolean in the target "
            "environment. Resolve colloquial wording semantically; do not generate Terraform."
        ),
        "user_request": str(prompt or "").strip(),
        "operation_hint": str(operation_hint or "unknown"),
        "literal_boolean_inventory": inventory,
        "target_environment_files": [
            {"path": _teams_context_file_identity(item), "content": str(item.get("content") or "")}
            for item in repository_evidence or []
            if isinstance(item, dict) and _teams_context_file_identity(item) and str(item.get("content") or "")
        ],
        "shared_repository_context": shared_context_block,
        "shared_repository_context_live_files": shared_context_live_files,
        "shared_repository_context_metadata": shared_context_metadata,
        "required_output": {
            "operation": "create|enable|disable|modify|delete|unknown",
            "boolean_applicable": "boolean",
            "reason": "short repository-grounded explanation",
            "candidates": [{
                "path": "exact inventory path", "line_number": 1, "flag": "exact inventory flag",
                "current_value": "true|false", "new_value": "true|false", "confidence": 0.0,
                "description": "what the control does in this repository",
            }],
        },
        "rules": [
            "Return JSON only.",
            "Inspect environment controls first for create/delete/enable/disable requests before considering ordinary code edits.",
            "Choose only from literal_boolean_inventory and only when the live environment files prove the control exists.",
            "Use semantic synonyms and surrounding Terraform/module context; exact token overlap with the flag is not required.",
            "If one control clearly implements the request, return exactly one candidate and do not ask for clarification.",
            "Return multiple candidates only for genuine repository ambiguity.",
            "Use shared repository context only after revalidating its mapped flag/path against current live files.",
        ],
    }
    try:
        raw = call_named_agent(json.dumps(request, ensure_ascii=False), AGENT_NAME)
        parsed = extract_json_from_text(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception as exc:
        LOGGER.warning("Second-pass environment Boolean resolution failed: %s", exc)
        return {"operation": operation_hint or "unknown", "boolean_applicable": False, "candidates": [], "error": str(exc)}


def _validated_repository_boolean_strategy(
    prompt: str,
    repository_evidence: list[dict],
) -> tuple[dict, list[dict]]:
    """Environment-first Boolean resolution with durable-context reuse.

    A unique repository-proven Boolean is auto-selected. Clarification is
    reserved for two or more semantically valid live controls.
    """
    strategy = _foundry_repository_change_strategy(prompt, repository_evidence)
    strategy = dict(strategy or {})
    inventory = strategy.get("inventory") or _repository_literal_boolean_inventory(repository_evidence)
    operation = str(strategy.get("operation") or "unknown").strip().lower()

    literal_index = {
        (str(item.get("path") or "").strip().strip("/"), int(item.get("line_number") or 0), str(item.get("flag") or "").strip()): item
        for item in inventory if isinstance(item, dict)
    }

    def _validated(parsed: dict) -> list[dict]:
        values: list[dict] = []
        seen: set[tuple[str, int, str]] = set()
        for candidate in (parsed or {}).get("candidates") or []:
            if not isinstance(candidate, dict):
                continue
            try:
                line_number = int(candidate.get("line_number") or 0)
            except (TypeError, ValueError):
                line_number = 0
            key = (
                str(candidate.get("path") or "").strip().strip("/"),
                line_number,
                str(candidate.get("flag") or "").strip(),
            )
            literal = literal_index.get(key)
            if not literal or key in seen:
                continue
            current = str(candidate.get("current_value") or "").strip().lower()
            target = str(candidate.get("new_value") or "").strip().lower()
            if current not in {"true", "false"} or target not in {"true", "false"} or current == target:
                continue
            if current != str(literal.get("current_value") or "").strip().lower():
                continue
            try:
                confidence = max(0.0, min(float(candidate.get("confidence") or 0.0), 1.0))
            except (TypeError, ValueError):
                confidence = 0.0
            seen.add(key)
            values.append({
                **literal,
                "new_value": target,
                "confidence": confidence,
                "context": str(candidate.get("description") or "").strip(),
                "description": str(candidate.get("description") or "").strip(),
                "classification_reason": str((parsed or {}).get("reason") or "").strip(),
                "operation": str((parsed or {}).get("operation") or operation or "unknown").strip().lower(),
            })
        return values

    validated = _validated(strategy) if strategy.get("boolean_applicable") else []

    # Durable context gets first chance to resolve a previously learned alias.
    context_matches = _repository_context_unique_boolean_match(prompt, inventory, operation)
    if len(context_matches) == 1:
        strategy["boolean_applicable"] = True
        strategy["requires_user_choice"] = False
        strategy["resolution_source"] = "validated_repository_context"
        strategy["validated_candidate_count"] = 1
        strategy["adjudicated_candidate_count"] = 1
        LOGGER.info(
            "[TerrabotDiag] event=repository_context_usage_observed source=boolean_resolver context_id=%s path=%s flag=%s",
            context_matches[0].get("repository_context_id") or "",
            context_matches[0].get("path") or "",
            context_matches[0].get("flag") or "",
        )
        return strategy, context_matches

    # First-time aliases still get one Boolean-only semantic retry before any
    # user question. This is especially important for Cursor-generated synonyms.
    if not validated:
        retry = _foundry_repository_boolean_inventory_retry(
            prompt, repository_evidence, inventory, operation_hint=operation
        )
        retry_operation = str(retry.get("operation") or operation or "unknown").strip().lower()
        if retry_operation != "unknown":
            operation = retry_operation
            strategy["operation"] = retry_operation
        if retry.get("boolean_applicable"):
            validated = _validated(retry)
            if validated:
                strategy["boolean_applicable"] = True
                strategy["reason"] = str(retry.get("reason") or strategy.get("reason") or "")
                strategy["resolution_source"] = "environment_boolean_retry"

    if not validated:
        strategy["validated_candidate_count"] = 0
        strategy["adjudicated_candidate_count"] = 0
        strategy["requires_user_choice"] = False
        return strategy, []

    adjudicated = _foundry_adjudicate_repository_boolean_candidates(
        prompt, repository_evidence, validated
    )
    strategy["validated_candidate_count"] = len(validated)
    strategy["adjudicated_candidate_count"] = len(adjudicated)
    strategy["requires_user_choice"] = len(adjudicated) > 1
    if len(adjudicated) == 1:
        strategy["resolution_source"] = strategy.get("resolution_source") or "unique_live_environment_boolean"
    return strategy, adjudicated

# =============================================================================
# 2026-08-20 UNIFIED CLOUD / ENVIRONMENT RESOLUTION - FINAL OVERRIDE
# =============================================================================
# Environment identity is repository identity.  Resolve it before allowing a
# model/router guess to select tf-devops vs tf-azure-hub.  The catalog below is
# deployment topology supplied by the platform owner; resource/flag mappings
# remain repository-derived and are intentionally not hardcoded here.

TERRABOT_ENVIRONMENT_CATALOG = {
    "aws": {
        "repo_target": "tf-devops",
        "default_nonprod": "minidev",
        "nonprod": {
            "dev": "terraform/dev_aws/dev",
            "minidev": "terraform/dev_aws/minidev",
            "bolt": "terraform/dev_aws/bolt",
            "bolt_dr": "terraform/dev_aws/bolt_dr",
            "bolt_sqlstaging": "terraform/dev_aws/bolt_sqlstaging",
            "dev_devops": "terraform/dev_aws/dev_devops",
            "dev_sqlstaging": "terraform/dev_aws/dev_sqlstaging",
            "global": "terraform/dev_aws/global",
            "minidev_sqlstaging": "terraform/dev_aws/minidev_sqlstaging",
            "observe": "terraform/dev_aws/observe",
        },
        "prod": {
            "ca3": "terraform/prod_aws/ca3",
            "ca3_dr": "terraform/prod_aws/ca3_dr",
            "devops": "terraform/prod_aws/devops",
            "eu1": "terraform/prod_aws/eu1",
            "eu1_dr": "terraform/prod_aws/eu1_dr",
            "eu2": "terraform/prod_aws/eu2",
            "eu2_dr": "terraform/prod_aws/eu2_dr",
            "global": "terraform/prod_aws/global",
            "observe": "terraform/prod_aws/observe",
            "sqlstaging": "terraform/prod_aws/sqlstaging",
            "sqlstaging_ca": "terraform/prod_aws/sqlstaging_ca",
            "sqlstaging_eu": "terraform/prod_aws/sqlstaging_eu",
            "sqlstaging_eu2": "terraform/prod_aws/sqlstaging_eu2",
            "sqlstaging_us4": "terraform/prod_aws/sqlstaging_us4",
            "sqlstaging_west": "terraform/prod_aws/sqlstaging_west",
            "us1": "terraform/prod_aws/us1",
            "us1_dr": "terraform/prod_aws/us1_dr",
            "us2": "terraform/prod_aws/us2",
            "us2_dr": "terraform/prod_aws/us2_dr",
            "us3": "terraform/prod_aws/us3",
            "us3_dr": "terraform/prod_aws/us3_dr",
            "us4": "terraform/prod_aws/us4",
            "us4_dr": "terraform/prod_aws/us4_dr",
            "root/global": "terraform/root/global",
        },
    },
    "azure": {
        "repo_target": "tf-azure-hub",
        "default_nonprod": "sbx-infra",
        "nonprod": {
            "npr-int": "vars/npr/npr-int",
            "npr-stg": "vars/npr/npr-stg",
            "sbx-infra": "vars/sbx/sbx-infra",
        },
        "prod": {
            "prd-ca4": "vars/prd/prd-ca4",
            "prd-eu3": "vars/prd/prd-eu3",
            "prd-us5": "vars/prd/prd-us5",
            "prd-us6": "vars/prd/prd-us6",
        },
    },
}

TERRABOT_AZURE_ENVIRONMENT_ALIASES = {
    "sandbox": "sbx-infra",
    "sbx": "sbx-infra",
    "npr-staging": "npr-stg",
    "npr-staging": "npr-stg",
    "ca4": "prd-ca4",
    "eu3": "prd-eu3",
    "us5": "prd-us5",
    "us6": "prd-us6",
}


