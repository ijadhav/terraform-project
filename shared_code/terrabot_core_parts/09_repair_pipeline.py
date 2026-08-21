from __future__ import annotations
# Compatibility definitions required by the repair pipeline. These existed in
# the monolithic core but were separated into a later override section during
# the refactor. Keeping them here prevents NameError when this part is used as
# the active repair implementation. Later overrides may safely replace them.
try:
    UnsafeGeneratedChangeError
except NameError:
    class UnsafeGeneratedChangeError(ValueError):
        pass


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


def _validate_agent_full_file_preservation_for_write(
    existing_content: str,
    generated_content: str,
    path: str,
    workflow: str | None,
) -> None:
    """Reject destructive existing-file rewrites without generating Terraform."""
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

    existing_nonblank = [line for line in existing.splitlines() if line.strip()]
    generated_nonblank = [line for line in generated.splitlines() if line.strip()]
    if len(existing_nonblank) >= 20 and len(generated_nonblank) < max(8, int(len(existing_nonblank) * 0.70)):
        raise UnsafeGeneratedChangeError(
            f"Generated modification for {path} is substantially shorter than the live repository file "
            f"({len(generated_nonblank)} vs {len(existing_nonblank)} nonblank lines). "
            "Refusing a likely truncated overwrite; Foundry must return the complete final file."
        )


def _teams_build_backend_repair_payload(
    current_result: dict,
    original_user_request: str,
    backend_error: Exception | str,
    flow_context: dict | None = None,
    retrieved_value_context: list | None = None,
    retrieved_module_context: list | None = None,
    prior_repair_feedback: str = "",
) -> dict:
    """Build a self-contained, live-file-backed surgical repair request.

    Existing repository files are never regenerated during repair. Foundry
    chooses the semantic old_text/new_text edit and the backend materializes it
    against exact live GitHub content, preserving every byte outside that span.
    """
    live_files = _teams_collect_live_repair_files(
        current_result, flow_context, retrieved_value_context
    )
    existing_targets = [item for item in live_files if str((item or {}).get("existing_live_content") or "")]
    all_existing = bool(live_files) and len(existing_targets) == len(live_files)
    protocol = _modular_repair_protocol(all_existing)
    return {
        "task": "SELF-CORRECTION LOOP: surgically repair the rejected Terraform against exact live repository files.",
        "channel": "teams",
        "repair_mode": "exact_live_file_surgical_edit",
        "original_user_request": str(original_user_request or ""),
        "backend_validation_error": str(backend_error),
        "prior_repair_feedback": str(prior_repair_feedback or ""),
        "expected_cloud": current_result.get("cloud"),
        "expected_workflow": current_result.get("workflow"),
        "expected_repo_target": current_result.get("repo_target"),
        "rejected_agent_result": {
            "cloud": current_result.get("cloud"),
            "workflow": current_result.get("workflow"),
            "repo_target": current_result.get("repo_target"),
            "title": current_result.get("title"),
            "summary": current_result.get("summary"),
            "files": [
                {"filename": (f or {}).get("filename"), "content": (f or {}).get("content")}
                for f in (current_result.get("files") or []) if isinstance(f, dict)
            ],
        },
        # Kept under both names for compatibility with older Foundry instructions.
        "repair_files": live_files,
        "teams_exact_live_files": [
            {
                "path": item.get("path"),
                "content": item.get("existing_live_content"),
                "live_nonblank_line_count": item.get("existing_nonblank_line_count"),
                "sha256": item.get("existing_sha256"),
            }
            for item in live_files if isinstance(item, dict)
        ],
        "retrieved_value_context": list(retrieved_value_context or []),
        "retrieved_module_context": list(retrieved_module_context or []),
        "repair_protocol": protocol,
        "required_response_contract": _modular_repair_response_contract(all_existing),
        "repair_edit_output_shape": {
            "mode": "infra",
            "cloud": current_result.get("cloud"),
            "workflow": current_result.get("workflow"),
            "repo_target": current_result.get("repo_target"),
            "title": current_result.get("title") or "Terraform repair",
            "summary": current_result.get("summary") or "Repair backend-rejected Terraform change",
            "repair_edits": [{
                "path": "repo/relative/file.tfvars",
                "old_text": "smallest exact unique text copied from existing_live_content",
                "new_text": "complete replacement implementing only original_user_request",
            }],
        },
    }

def _teams_repair_candidate_is_identical(previous_result: dict, repaired_result: dict) -> bool:
    previous = _teams_repair_file_map(previous_result.get("files") or [])
    repaired = _teams_repair_file_map(repaired_result.get("files") or [])
    return bool(previous) and previous == repaired


def _teams_validate_repair_candidate_against_payload(repaired_result: dict, repair_payload: dict) -> None:
    """Validate a repair before replacing the last rejected candidate."""
    repaired = _teams_repair_file_map(repaired_result.get("files") or [])
    workflow = repaired_result.get("workflow") or repair_payload.get("expected_workflow")
    for item in repair_payload.get("repair_files") or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip().strip("/")
        live = str(item.get("existing_live_content") or "")
        if not path or not live or path not in repaired:
            continue
        candidate = repaired[path]
        if path.endswith((".tf", ".tfvars")):
            _validate_hcl_content_complete(path, candidate)
            _validate_agent_full_file_preservation_for_write(live, candidate, path, workflow)


def _teams_materialize_repair_edits_response(agent_reply: str, repair_payload: dict) -> str:
    """Materialize exact Foundry-selected edits onto live repository bytes.

    This is the Teams equivalent of VS Code's in-place edit behavior: existing
    files are never reconstructed. Only the exact selected span is replaced; the
    prefix and suffix come directly from the live GitHub file.
    """
    text = str(agent_reply or "").strip()
    if not text:
        return text
    try:
        payload = extract_json_from_text(text)
    except Exception:
        return text

    edits = payload.get("repair_edits")
    repair_files = [item for item in (repair_payload.get("repair_files") or []) if isinstance(item, dict)]
    all_existing = bool(repair_files) and all(str(item.get("existing_live_content") or "") for item in repair_files)
    if not isinstance(edits, list) or not edits:
        if all_existing and isinstance(payload.get("files"), list) and payload.get("files"):
            raise ValueError(
                "Foundry returned full files[] for an existing-file repair. This repair mode requires "
                "repair_edits[] against exact existing_live_content so unrelated repository bytes cannot be overwritten."
            )
        return text

    live_by_path: dict[str, dict] = {}
    for item in repair_payload.get("repair_files") or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip().strip("/")
        if path:
            live_by_path[path] = item
    if not live_by_path:
        raise ValueError("Foundry returned repair_edits, but no exact live repair files were supplied by the backend.")

    edits_by_path: dict[str, list[SurgicalEdit]] = {}
    for index, edit in enumerate(edits, start=1):
        if not isinstance(edit, dict):
            raise ValueError(f"repair_edits[{index}] must be an object.")
        path = str(edit.get("path") or edit.get("filename") or "").strip().strip("/")
        if path not in live_by_path:
            raise ValueError(f"repair_edits[{index}] path '{path}' is not one of the backend-supplied exact live files.")
        old_text = edit.get("old_text")
        new_text = edit.get("new_text")
        if not isinstance(old_text, str) or not old_text:
            raise ValueError(f"repair_edits[{index}] old_text must be non-empty exact live-file text.")
        if not isinstance(new_text, str):
            raise ValueError(f"repair_edits[{index}] new_text must be a string.")
        edits_by_path.setdefault(path, []).append(SurgicalEdit(path=path, old_text=old_text, new_text=new_text))

    materialized_files: list[dict] = []
    original_request = str(repair_payload.get("original_user_request") or "")
    for path, path_edits in edits_by_path.items():
        live_item = live_by_path[path]
        live_content = str(live_item.get("existing_live_content") or "")
        if not live_content:
            raise ValueError(f"Cannot materialize repair_edits for {path}: existing_live_content is empty.")
        expected_sha = str(live_item.get("existing_sha256") or "").strip()
        actual_sha = hashlib.sha256(live_content.encode("utf-8")).hexdigest()
        if expected_sha and expected_sha != actual_sha:
            raise ValueError(f"Cannot materialize repair_edits for {path}: live-file checksum mismatch.")

        candidate = apply_surgical_edits(
            path=path,
            live_content=live_content,
            edits=path_edits,
            original_user_request=original_request,
        )
        if candidate == live_content:
            raise ValueError(f"Materialized repair for {path} is unchanged from the live file.")
        if path.endswith((".tf", ".tfvars")):
            _validate_hcl_content_complete(path, candidate)
            _validate_agent_full_file_preservation_for_write(
                live_content, candidate, path, repair_payload.get("expected_workflow")
            )
        materialized_files.append({"filename": path, "content": candidate})

    normalized = {
        "mode": "infra",
        "cloud": payload.get("cloud") or repair_payload.get("expected_cloud"),
        "workflow": payload.get("workflow") or repair_payload.get("expected_workflow"),
        "repo_target": payload.get("repo_target") or repair_payload.get("expected_repo_target"),
        "title": payload.get("title") or (repair_payload.get("rejected_agent_result") or {}).get("title") or "Terraform repair",
        "summary": payload.get("summary") or (repair_payload.get("rejected_agent_result") or {}).get("summary") or "Repair backend-rejected Terraform change",
        "files": materialized_files,
    }
    _teams_diag_log(
        "backend_repair_edits_materialized",
        edit_count=sum(len(items) for items in edits_by_path.values()),
        files=len(materialized_files),
        paths=",".join(sorted(edits_by_path))[:500],
        strategy="exact_live_file_surgical_edit",
    )
    return json.dumps(normalized, ensure_ascii=False)

def _teams_repair_reply_has_executable_change(agent_reply: str) -> bool:
    """Return True when a repair reply contains code/edit material to validate.

    A repair response may carry incidental prose/question metadata, but it is
    useful if it also contains non-empty repair_edits[] or files[]. This check
    lets the backend immediately re-prompt Foundry only for truly non-executable
    repair replies instead of burning the outer validation retry on a question.
    """
    try:
        payload = extract_json_from_text(str(agent_reply or ""))
    except Exception:
        return False
    edits = payload.get("repair_edits")
    files = payload.get("files")
    return bool(
        (isinstance(edits, list) and any(isinstance(item, dict) for item in edits))
        or (isinstance(files, list) and any(isinstance(item, dict) for item in files))
    )


def _teams_call_agent_for_backend_repair(repair_payload: dict) -> tuple[str, str]:
    """Use isolated Foundry calls and force non-executable repairs to converge.

    The repair payload is fully self-contained. If Foundry answers the first
    isolated call with a question, prose, or malformed/non-executable JSON, make
    one immediate fresh repair-enforcement call using the same live evidence.
    Terraform semantics remain Foundry-owned; the backend only requires an
    executable files[]/repair_edits[] response before returning to validation.
    """
    raw = json.dumps(repair_payload, ensure_ascii=False, separators=(",", ":"))
    _teams_diag_log(
        "backend_repair_isolated_call",
        input_chars=len(raw),
        repair_files=len(repair_payload.get("repair_files") or []),
    )
    conversation_id, reply = _TEAMS_MULTICLOUD_PREVIOUS_CALL_AGENT(None, raw)
    if _teams_repair_reply_has_executable_change(reply):
        return conversation_id, reply

    enforcement_payload = dict(repair_payload)
    enforcement_payload["repair_response_violation"] = (
        "The immediately preceding internal repair response contained no executable "
        "files[] or repair_edits[]. Do not ask a question. Produce the repair now."
    )
    enforcement_payload["mandatory_next_output"] = {
        "json_only": True,
        "questions": [],
        "must_include_exactly_one_of": ["repair_edits", "files"],
        "preferred": "repair_edits for targeted edits to existing files",
        "instruction": (
            "Use repair_files[].existing_live_content as the immutable baseline and "
            "fix backend_validation_error with the smallest Foundry-selected change."
        ),
    }
    enforcement_raw = json.dumps(
        enforcement_payload, ensure_ascii=False, separators=(",", ":")
    )
    _teams_diag_log(
        "backend_repair_nonexecutable_retry",
        input_chars=len(enforcement_raw),
        repair_files=len(repair_payload.get("repair_files") or []),
    )
    return _TEAMS_MULTICLOUD_PREVIOUS_CALL_AGENT(None, enforcement_raw)


def commit_terraform_files_to_branch_for_teams_with_self_correction(
    agent_result: dict,
    prompt: str,
    thread_id: str,
    max_attempts: int = MAX_TEAMS_SELF_CORRECTION_ATTEMPTS,
) -> dict:
    """Commit to the Teams branch, but never hand a backend guardrail
    rejection straight to the user.

    When commit_terraform_files_to_branch_for_teams raises ValueError —
    the backend's own validation/preservation/format checks reject the
    generated content before anything is written — that exact rejection
    reason is sent back to the Foundry agent as a correction task instead
    of being surfaced as an error message. The agent regenerates, the
    backend re-validates, and this repeats (bounded) until a version
    passes and is committed, or attempts run out. The user only ever sees
    output if every attempt failed, and even then gets one clear
    diagnostic rather than a raw exception.

    Errors that are NOT backend-guardrail rejections (GitHub auth/network
    failures, RuntimeError, etc.) are not caught here and propagate
    unchanged, since retrying/self-correcting those would just repeat the
    same external failure.
    """
    current_result = agent_result
    last_error: Optional[Exception] = None
    repair_feedback = ""
    _teams_diag_log(
        "commit_pipeline_start",
        thread=thread_id,
        prompt=str(prompt or "")[:120],
        max_attempts=max_attempts,
    )

    for attempt in range(1, max_attempts + 1):
        try:
            _teams_diag_log(
                "backend_validation_start",
                thread=thread_id,
                attempt=f"{attempt}/{max_attempts}",
                files=len(current_result.get("files") or []),
            )
            result = commit_terraform_files_to_branch_for_teams(current_result, prompt, thread_id)
            if attempt > 1:
                result["self_corrected"] = True
                result["self_correction_attempts"] = attempt
                result["committed_agent_result_files"] = current_result.get("files")
            _teams_diag_log(
                "commit_pipeline_success",
                thread=thread_id,
                attempt=f"{attempt}/{max_attempts}",
                branch=result.get("branch"),
            )
            return result
        except ValueError as backend_error:
            # UnsafeGeneratedChangeError intentionally subclasses ValueError. It is a
            # backend validation rejection, not an external transport/auth failure, so
            # route it through the same private Foundry self-correction loop. The
            # backend still never repairs or generates Terraform itself; it only sends
            # the rejection plus live repository evidence back to Foundry and validates
            # the newly generated result on the next attempt.
            last_error = backend_error
            _teams_diag_log(
                "backend_validation_failed",
                level="warning",
                thread=thread_id,
                attempt=f"{attempt}/{max_attempts}",
                error=str(backend_error)[:300],
            )
            if attempt >= max_attempts:
                break
            LOGGER.warning(
                "Teams backend guardrail rejected generated Terraform on attempt %s/%s "
                "(thread=%s): %s. Routing the rejection back to the Foundry agent for "
                "self-correction instead of surfacing it to the user.",
                attempt, max_attempts, thread_id, backend_error,
            )

            # Truncation failures get a targeted, small tail-completion repair
            # FIRST — repeating a full-file regeneration request tends to hit
            # the exact same output-length ceiling every time, which is why
            # the identical "N open brackets" error could recur on every
            # attempt without ever actually getting fixed.
            truncation_match = _teams_find_truncated_file_error(str(backend_error))
            if truncation_match:
                trunc_path, open_count, open_brackets = truncation_match
                _teams_diag_log(
                    "truncation_detected_trying_tail_repair",
                    thread=thread_id,
                    attempt=f"{attempt}/{max_attempts}",
                    path=trunc_path,
                    open_brackets=f"{open_count}({open_brackets})",
                )
                tail_fixed = _teams_attempt_tail_completion_repair(
                    current_result.get("files") or [], trunc_path, thread_id, prompt,
                    current_result=current_result,
                )
                if tail_fixed:
                    _teams_diag_log(
                        "tail_repair_applied_retrying_validation",
                        thread=thread_id,
                        attempt=f"{attempt}/{max_attempts}",
                        path=trunc_path,
                    )
                    continue  # re-run backend_validation_start with the spliced content
                _teams_diag_log(
                    "tail_repair_did_not_resolve_falling_back_to_full_regeneration",
                    level="warning",
                    thread=thread_id,
                    attempt=f"{attempt}/{max_attempts}",
                    path=trunc_path,
                )

            context = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
            repair_payload = {
                "task": (
                    "SELF-CORRECTION LOOP: your previously generated Terraform change was "
                    "rejected by the backend's own validation/preservation checks before "
                    "anything was written to the branch. The user has NOT seen this error. "
                    "Fix the exact problem below and return corrected files now — do not ask "
                    "the user anything."
                ),
                "channel": "teams",
                "original_user_request": prompt,
                "previous_generated_files": [
                    {"filename": (f or {}).get("filename"), "content": (f or {}).get("content")}
                    for f in (current_result.get("files") or [])
                    if isinstance(f, dict)
                ],
                "backend_validation_error": str(backend_error),
                "correction_instructions": [
                    "backend_validation_error explains precisely why the previous attempt was rejected. Fix that exact problem — do not regenerate from scratch.",
                    "Common causes and fixes: a 'modify' file did not include the complete existing file content (re-read the live evidence and reproduce it verbatim except for the requested change); the change removed, reordered, or reformatted unrelated existing lines (put them back exactly as they were); HCL braces/quotes are unbalanced (balance them); an unrelated file was touched that the user never asked about (drop that file from the response).",
                    "If the previous attempt was truncated (cut off mid-block), the file you return this time must be the COMPLETE file with every block closed — verify this yourself before returning; a second truncated response wastes the correction attempt.",
                    "Only make the change the ORIGINAL user request actually asked for. Remove any extra/unrelated edits the previous attempt introduced.",
                    "Preserve exact existing formatting, spacing, comments, and blank-line structure from the live repository evidence already supplied.",
                    "Return the same JSON envelope shape as before (summary, analysis, source_paths_used, files, user_fillable, questions, validation_commands) with corrected content.",
                    "Do not return empty files[] and do not return questions[] in response to this correction request — always return a corrected, complete files[] payload.",
                ],
                "expected_cloud": current_result.get("cloud"),
                "expected_workflow": current_result.get("workflow"),
                "expected_repo_target": current_result.get("repo_target"),
                "retrieved_value_context": context.get("retrieved_value_context") or [],
                "retrieved_module_context": context.get("retrieved_module_context") or [],
            }
            selected_repair_context = _get_backend_existing_infra_context(
                context.get("retrieved_value_context") or []
            )
            if isinstance(selected_repair_context, dict):
                selected_repair_path = str(selected_repair_context.get("selected_path") or "").strip()
                selected_repair_content = ""
                for matched in selected_repair_context.get("matched_files") or []:
                    if not isinstance(matched, dict):
                        continue
                    matched_path = str(matched.get("path") or matched.get("filename") or "").strip()
                    if not selected_repair_path or matched_path == selected_repair_path:
                        selected_repair_content = str(matched.get("content") or "")
                        if selected_repair_content:
                            break
                if selected_repair_path and selected_repair_content:
                    repair_payload["teams_exact_target_file"] = {
                        "path": selected_repair_path,
                        "content": selected_repair_content,
                        "must_preserve_verbatim": True,
                        "requested_resource_name": _teams_safe_prompt_resource_name(prompt),
                    }
            # Canonical repair package: validator error + rejected code + exact live code.
            repair_payload = _teams_build_backend_repair_payload(
                current_result=current_result,
                original_user_request=prompt,
                backend_error=backend_error,
                flow_context=context,
                retrieved_value_context=context.get("retrieved_value_context") or [],
                retrieved_module_context=context.get("retrieved_module_context") or [],
                prior_repair_feedback=repair_feedback,
            )
            _teams_diag_log(
                "sending_full_regeneration_repair_to_agent",
                thread=thread_id,
                attempt=f"{attempt}/{max_attempts}",
            )
            try:
                _conversation_id, repaired_reply = _teams_call_agent_for_backend_repair(
                    repair_payload
                )
                repaired_reply = _teams_materialize_repair_edits_response(
                    repaired_reply, repair_payload
                )
                repaired_result = try_parse_agent_output(repaired_reply)
                if _teams_repair_candidate_is_identical(current_result, repaired_result):
                    raise ValueError(
                        "Foundry repair returned byte-identical file content to the backend-rejected candidate. "
                        "The repair must actually change the failed output using existing_live_content."
                    )
                _teams_validate_repair_candidate_against_payload(repaired_result, repair_payload)
                current_result = repaired_result
                _teams_diag_log(
                    "agent_repair_response_received",
                    thread=thread_id,
                    attempt=f"{attempt}/{max_attempts}",
                    files_returned=len(current_result.get("files") or []),
                )
            except Exception as repair_call_error:
                repair_feedback = str(repair_call_error)
                LOGGER.warning(
                    "Foundry self-correction call failed on attempt %s (thread=%s): %s",
                    attempt, thread_id, repair_call_error,
                )
                _teams_diag_log(
                    "agent_repair_call_failed",
                    level="warning",
                    thread=thread_id,
                    attempt=f"{attempt}/{max_attempts}",
                    error=str(repair_call_error)[:200],
                )
                # Keep retrying with the same current_result in case this was a
                # transient issue calling/parsing the agent, until attempts run out.
                continue

    _teams_diag_log(
        "commit_pipeline_exhausted",
        level="error",
        thread=thread_id,
        max_attempts=max_attempts,
        last_error=str(last_error)[:300],
    )
    # Keep raw validator details in backend diagnostics only. Teams should never
    # receive preservation/truncation internals such as repository line counts.
    raise ValueError(
        f"Terrabot could not produce a backend-valid Terraform change after {max_attempts} "
        "internal self-correction attempts. No repository file changes were written."
    )


def _teams_ensure_variables_tf_evidence(cloud: Optional[str], retrieved_value_context: Optional[list]) -> list:
    """Universal guarantee: whenever Azure evidence includes any tfvars-style
    values file (hub.tfvars, tier.tfvars, common.tfvars, or any *.tfvars) or
    any .tf resource-family definition file, the repo's variables.tf must
    also be present in the evidence sent to the agent — the agent cannot
    correctly decide "reuse an existing object variable vs. declare a new
    one" without seeing what is already declared there. This is exactly the
    gap that caused a real production failure: a new module block was wired
    to var.storage_account_zrs.* — an existing sibling's variable — because
    the agent was never shown variables.tf and had no way to know a
    dedicated variable should have been declared instead.

    Runs for EVERY Azure Teams request, regardless of which upstream code
    path assembled the evidence (flag-based RULE machinery or a plain
    resource-family creation/modification). Idempotent — safe to call more
    than once; does nothing if variables.tf is already present or if there
    is no .tf/.tfvars evidence to justify fetching it."""
    ctx = list(retrieved_value_context or [])
    if safe_normalize_cloud(cloud) != "azure":
        return ctx
    existing_paths = {
        str((entry or {}).get("path") or "").strip()
        for entry in ctx
        if isinstance(entry, dict) and (entry or {}).get("path")
    }
    if any(p.endswith("variables.tf") for p in existing_paths):
        return ctx  # already present somewhere in the evidence
    if not any(p.endswith(".tfvars") or p.endswith(".tf") for p in existing_paths):
        return ctx  # no infra evidence yet to justify pulling variables.tf

    flow_context = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    repo_target = (
        str(flow_context.get("expected_repo_target") or flow_context.get("repo_target") or "").strip()
        or normalize_repo_target("azure", "")
    )
    workflow = str(flow_context.get("expected_workflow") or flow_context.get("workflow") or "").strip()
    branch = str(flow_context.get("context_branch") or flow_context.get("source_branch") or "").strip()
    if not branch:
        try:
            branch = github_resolve_base_branch_for_cloud("azure", repo_target=repo_target, workflow=workflow)
        except Exception:
            branch = ""
    if not branch:
        return ctx

    # tf-azure-hub convention: variables.tf sits at repo root, next to the
    # resource-family definition files (storage_accounts.tf, aca_apps.tf,
    # etc.) — but resolve it relative to whatever .tf evidence directory we
    # actually have, shallowest first, so this also works if a repo nests
    # its definitions under a subdirectory.
    candidate_dirs = sorted(
        {p.rsplit("/", 1)[0] if "/" in p else "" for p in existing_paths if p.endswith(".tf")},
        key=len,
    ) or [""]
    for directory in candidate_dirs:
        var_path = f"{directory}/variables.tf" if directory else "variables.tf"
        try:
            content = github_get_file_content(
                "azure", var_path, branch, repo_target=repo_target, workflow=workflow
            )
        except Exception:
            content = None
        if content:
            ctx.append({
                "path": var_path,
                "content": content,
                "reason": (
                    "always-included companion evidence (backend-injected): this "
                    "repo's object-backed resource variables (e.g. "
                    "storage_account_zrs, storage_account_grs) are declared here. "
                    "Required before generating any new module/resource block: "
                    "check whether a dedicated variable for THIS instance already "
                    "exists here; if not, a new `variable \"<name>\" { type = "
                    "object({...}) }` declaration must be appended here in the "
                    "same response. Never wire a new module block to an existing "
                    "sibling's object variable without first checking this file."
                ),
            })
            break
    return ctx


