from __future__ import annotations
def build_backend_existing_infra_modification_context_stage3(
    prompt: str,
    thread_id: str,
    cloud: str,
    workflow: str,
    retrieved_value_context: list | None = None,
) -> dict:
    """Supply live code to Foundry without backend resource/flag selection."""
    context = _AGENT_OWNED_PREVIOUS_BUILD_EXISTING_CONTEXT(
        prompt,
        thread_id,
        cloud,
        workflow,
        retrieved_value_context=retrieved_value_context,
    )
    active = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    if active.get("active") and _teams_feature_flag_intent(prompt) in {"enable", "disable"}:
        context = dict(context or {})
        # Prevent the generic backend file-picker from intercepting the turn.
        # matched_files retain complete live contents as evidence for Foundry.
        context["selection_state"] = "selected"
        context["selected_path"] = ""
        context.pop("feature_flag_match", None)
        context.pop("feature_flag_resolution", None)
        context["agent_resolves_target"] = True
        context["instructions"] = [
            "Foundry must inspect the supplied live repository files and decide how the requested feature is controlled.",
            "For enable/disable requests, consider only repository-defined Boolean assignments whose current value has the required polarity; do not treat unrelated parameters/resources/files as choices.",
            "If one semantic match exists, Foundry generates the complete final file directly. If multiple semantic matches remain, Foundry asks one numbered choice with a short description inferred from the Terraform block.",
            "No backend flag aliases, resource vocabulary, Boolean selection, or Terraform synthesis is authoritative.",
        ]
    return context
build_backend_existing_infra_modification_context = build_backend_existing_infra_modification_context_stage3



def _repository_context_evidence_fetcher(
    repo_owner: str,
    repo_name: str,
    path: str,
    ref: str,
) -> Optional[str]:
    return github_get_file_content_by_repo(
        repo_owner,
        repo_name,
        path,
        ref=ref or None,
    )


def search_repository_context(
    repo_owner: str,
    repo_name: str,
    query: str,
    current_commit_sha: str = "",
    top_k: int = 8,
) -> dict:
    """Backend/tool API: retrieve shared durable knowledge for one repository."""
    return shared_repository_context.search_repository_context(
        repo_owner=repo_owner,
        repo_name=repo_name,
        query=query,
        current_commit_sha=current_commit_sha,
        top_k=top_k,
    )


def add_repository_context(
    repo_owner: str,
    repo_name: str,
    evidence_commit_sha: str,
    candidate: dict,
    evidence_branch: str = "",
    source_task_hash: str = "",
) -> dict:
    """Backend/tool API: validate and add one durable repository conclusion."""
    return shared_repository_context.add_repository_context(
        repo_owner=repo_owner,
        repo_name=repo_name,
        evidence_commit_sha=evidence_commit_sha,
        evidence_branch=evidence_branch,
        source_task_hash=source_task_hash,
        candidate=candidate,
        evidence_fetcher=_repository_context_evidence_fetcher,
    )


def update_repository_context(
    context_id: str,
    repo_owner: str,
    repo_name: str,
    evidence_commit_sha: str,
    candidate: dict,
    evidence_branch: str = "",
    source_task_hash: str = "",
) -> dict:
    """Backend/tool API: version a context item while preserving history."""
    return shared_repository_context.update_repository_context(
        context_id=context_id,
        repo_owner=repo_owner,
        repo_name=repo_name,
        evidence_commit_sha=evidence_commit_sha,
        evidence_branch=evidence_branch,
        source_task_hash=source_task_hash,
        candidate=candidate,
        evidence_fetcher=_repository_context_evidence_fetcher,
    )


def invalidate_repository_context(
    context_id: str,
    reason: str,
    current_commit_sha: str = "",
) -> dict:
    """Backend/tool API: invalidate an item without deleting its history."""
    return shared_repository_context.invalidate_repository_context(
        context_id=context_id,
        reason=reason,
        current_commit_sha=current_commit_sha,
    )


def repository_context_tool_schemas() -> list[dict]:
    return list(shared_repository_context.FOUNDRY_REPOSITORY_CONTEXT_TOOL_SCHEMAS)


def _repository_context_completed_task_payload(
    agent_result: dict,
    prompt: str,
    branch_result: dict,
    thread_id: str,
) -> tuple[dict, str, str, str, str]:
    """Build the evidence packet used only for durable-context extraction."""
    owner = str(GITHUB_OWNER or "").strip()
    repo = str(branch_result.get("repo") or "").strip()
    branch = str(branch_result.get("branch") or "").strip()
    base_branch = str(branch_result.get("base_branch") or "").strip()
    if not owner or not repo or not branch:
        raise ValueError("Repository/branch identity is incomplete for context extraction.")

    commit_sha = str(
        github_get_base_branch_sha_by_repo(owner, repo, branch) or ""
    ).strip()
    compare = _github_workspace_compare(
        owner,
        repo,
        base_branch or "main",
        branch,
        github_headers(),
    )

    changed_paths = [
        str(item.get("filename") or "").strip()
        for item in (compare.get("files") or [])
        if isinstance(item, dict) and str(item.get("filename") or "").strip()
    ]
    relevant_code = []
    for path in list(dict.fromkeys(changed_paths + list(agent_result.get("source_paths_used") or [])))[:16]:
        try:
            content = github_get_file_content_by_repo(owner, repo, path, ref=commit_sha or branch)
        except Exception:
            content = None
        if content is None:
            continue
        relevant_code.append({
            "path": path,
            # Enough code for extraction without re-sending arbitrarily huge files.
            "content": str(content)[:24000],
            "truncated": len(str(content)) > 24000,
        })

    try:
        existing_context = search_repository_context(
            owner,
            repo,
            prompt,
            current_commit_sha=commit_sha,
            top_k=8,
        ).get("results") or []
    except Exception:
        existing_context = []

    clarification_exchange = str(_TEAMS_CONVERSATION_CONTEXT.get() or "")[:6000]
    task_hash = hashlib.sha256(
        json.dumps(
            {
                "repo": f"{owner}/{repo}",
                "commit": commit_sha,
                "prompt": prompt,
                "files": changed_paths,
            },
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()

    payload = {
        "task": "EXTRACT DURABLE REPOSITORY CONTEXT FROM COMPLETED TERRABOT TASK",
        "repository": f"{owner}/{repo}",
        "branch": branch,
        "base_branch": base_branch,
        "evidence_commit_sha": commit_sha,
        "user_request": prompt,
        "clarification_exchange": clarification_exchange,
        "relevant_code": relevant_code,
        "tool_results": {
            "generated_summary": agent_result.get("summary") or "",
            "generated_analysis": agent_result.get("analysis") or "",
            "source_paths_used": agent_result.get("source_paths_used") or [],
            "committed_files": branch_result.get("files") or [],
            "git_compare": compare,
        },
        "validation_test_results": {
            "backend_semantic_relevance": "passed",
            "backend_terraform_shape": "passed",
            "backend_agent_self_validation": "passed",
            "github_commit_transport": "passed",
            "declared_validation_commands": agent_result.get("validation_commands") or [],
            "declared_commands_execution": "not executed by the Function App during this commit path",
            "additional_results": agent_result.get("validation_results") or [],
        },
        "existing_repository_context": existing_context,
        "required_output": {
            "candidates": [
                {
                    "category": "repository_fact",
                    "subject": "stable repository concept",
                    "scope": "repository/module/component/environment/path",
                    "statement": "one durable repository-specific conclusion",
                    "confidence": 0.0,
                    "evidence": [
                        {
                            "path": "repo-relative path present in relevant_code",
                            "excerpt": "short exact excerpt copied from repository code at evidence_commit_sha",
                            "reason": "why this excerpt supports the statement",
                        }
                    ],
                    "validation_summary": "why this conclusion is durable and useful later",
                }
            ]
        },
        "rules": [
            "Return JSON only with exactly one top-level key: candidates.",
            "For category, return exactly ONE of: architecture_decision, implementation_decision, coding_convention, repository_constraint, component_relationship, workflow_procedure, api_integration_behavior, resolved_clarification, repository_fact. Never copy the full allowed-category list into category.",
            "Do not store or summarize the conversation, user identity, request history, branch workflow state, PR metadata, or temporary task status.",
            "Persist only repository-specific knowledge useful for future tasks: architecture/implementation decisions, coding conventions, repository constraints, component relationships, workflows/procedures, API/integration behavior, resolved repository clarifications, or important repository facts.",
            "Every candidate must be supported by at least one exact repository excerpt from relevant_code at evidence_commit_sha. Do not use clarification text, model output, or existing context as sole evidence.",
            "Do not repeat a conclusion already represented by existing_repository_context unless the repository evidence materially updates or conflicts with it.",
            "If evidence conflicts with existing context, emit the new supported conclusion; the backend will record an explicit conflict instead of overwriting history.",
            "Do not emit secrets, credentials, tokens, account IDs, connection strings, or private values.",
            "Prefer zero candidates over weak, ephemeral, task-specific, or speculative context.",
            "Use confidence >= 0.75 only when repository evidence clearly supports the conclusion.",
        ],
    }
    return payload, owner, repo, branch, task_hash




def _repository_context_allowed_category(candidate: dict) -> dict:
    """Normalize one malformed extraction category without losing the record.

    Some model responses copied the human-readable ``A | B | C`` schema text
    verbatim into ``category``.  That is not a valid repository-context
    category and caused otherwise useful evidence-backed records to be rejected.
    ``repository_fact`` is the conservative fallback for that schema-copy error;
    valid explicit categories are preserved unchanged.
    """
    item = dict(candidate or {})
    allowed = {
        "architecture_decision",
        "implementation_decision",
        "coding_convention",
        "repository_constraint",
        "component_relationship",
        "workflow_procedure",
        "api_integration_behavior",
        "resolved_clarification",
        "repository_fact",
    }
    category = str(item.get("category") or "").strip()
    if category in allowed:
        return item
    if "|" in category:
        item["category"] = "repository_fact"
        LOGGER.warning(
            "[TerrabotDiag] event=repository_context_category_schema_copy_normalized original=%s normalized=repository_fact",
            category,
        )
    return item


def _repository_context_vague_resource_phrase(prompt: str) -> str:
    """Extract the reusable resource phrase from a plain-language change request."""
    text = re.sub(r"\s+", " ", str(prompt or "").strip().lower())
    if not text:
        return ""
    text = re.sub(r"^(?:please\s+)?(?:can|could|would)\s+you\s+", "", text)
    text = re.sub(
        r"^(?:please\s+)?(?:enable|disable|create|add|remove|delete|turn\s+on|turn\s+off|stop|start|set|update|modify|change)\s+",
        "",
        text,
    )
    # Remove a trailing environment qualifier while preserving the resource phrase.
    env_names = sorted(
        set(TEAMS_AWS_ENVIRONMENT_HINTS) | set(TEAMS_AZURE_ENVIRONMENT_HINTS),
        key=len,
        reverse=True,
    )
    for env in env_names:
        env_re = re.escape(str(env).lower()).replace(r"\_", r"[_ -]")
        text = re.sub(rf"\s+(?:in|on|for)\s+{env_re}\s*$", "", text)
    text = re.sub(r"\s+(?:in|on|for)\s+terraform/[a-z0-9_./-]+\s*$", "", text)
    return text.strip(" .,:;!?`'\"")


def _repository_context_term_tokens(value: str) -> set[str]:
    stop = {"setup", "service", "resource", "feature", "module", "the", "a", "an"}
    return {
        token
        for token in re.findall(r"[a-z0-9]+", str(value or "").lower().replace("_", " ").replace("-", " "))
        if len(token) >= 3 and token not in stop
    }


def _repository_context_boolean_changes(compare: dict, changed_paths: set[str]) -> list[dict]:
    """Return literal Boolean assignment changes from the current changed files."""
    results: list[dict] = []
    for file_info in compare.get("files") or []:
        if not isinstance(file_info, dict):
            continue
        path = str(file_info.get("filename") or "").strip()
        if changed_paths and path not in changed_paths:
            continue
        patch = str(file_info.get("patch") or "")
        removed: dict[str, list[str]] = {}
        added: dict[str, list[str]] = {}
        for line in patch.splitlines():
            if line.startswith("---") or line.startswith("+++"):
                continue
            match = re.match(r"^[+-]\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(true|false)\b", line, re.IGNORECASE)
            if not match:
                continue
            name, value = match.group(1), match.group(2).lower()
            target = removed if line.startswith("-") else added
            target.setdefault(name, []).append(value)
        for name in sorted(set(removed) & set(added)):
            before_values = removed[name]
            after_values = added[name]
            changed_count = sum(1 for before, after in zip(before_values, after_values) if before != after)
            if changed_count <= 0:
                continue
            results.append({
                "path": path,
                "flag": name,
                "before": before_values[0],
                "after": after_values[0],
                "changed_occurrences": changed_count,
            })
    return results


def _repository_context_flag_modules(content: str, flag_name: str) -> list[dict]:
    """Resolve the module block(s) that contain one literal Boolean flag."""
    matches: list[dict] = []
    assignment_re = re.compile(
        rf"(?m)^\s*{re.escape(flag_name)}\s*=\s*(true|false)\b",
        re.IGNORECASE,
    )
    for block in _extract_top_level_tf_blocks(content or ""):
        header = str(block.get("header") or "").strip()
        module_match = re.fullmatch(r'module\s+"([^"]+)"', header)
        if not module_match:
            continue
        block_text = str(block.get("block") or "")
        assignment = assignment_re.search(block_text)
        if not assignment:
            continue
        # Full module text is exact repository evidence and proves containment.
        excerpt = block_text.strip()
        if len(excerpt) > 12000:
            # Preserve exact substrings when a very large module block is encountered.
            header_line = block_text.splitlines()[0].strip() if block_text.splitlines() else header
            flag_line = assignment.group(0).strip()
            evidence = [header_line, flag_line]
        else:
            evidence = [excerpt]
        matches.append({
            "module": module_match.group(1),
            "value": assignment.group(1).lower(),
            "evidence": evidence,
        })
    return matches


def _store_vague_request_control_relationships(
    payload: dict,
    owner: str,
    repo: str,
    branch: str,
    task_hash: str,
) -> dict:
    """Store vague user phrase -> concrete flag/module/file relationships.

    This is deterministic post-change extraction.  It uses the actual Git diff
    and committed Terraform, so a request such as ``disable patch setup on us1``
    can become durable context stating that ``patch setup`` is controlled by
    ``enable_patch_monitoring`` in the concrete patch-management module(s).
    """
    prompt = str(payload.get("user_request") or "").strip()
    phrase = _repository_context_vague_resource_phrase(prompt)
    commit_sha = str(payload.get("evidence_commit_sha") or "").strip()
    compare = ((payload.get("tool_results") or {}).get("git_compare") or {})
    changed_paths = {
        str(path or "").strip()
        for path in ((payload.get("tool_results") or {}).get("committed_files") or [])
        if str(path or "").strip()
    }
    if not phrase or not commit_sha:
        return {"ok": True, "stored": 0, "skipped": "missing_phrase_or_commit"}

    phrase_tokens = _repository_context_term_tokens(phrase)
    grouped: dict[tuple[str, str], list[dict]] = {}
    for change in _repository_context_boolean_changes(compare, changed_paths):
        path = change["path"]
        flag = change["flag"]
        try:
            content = github_get_file_content_by_repo(owner, repo, path, ref=commit_sha)
        except Exception:
            content = None
        if not content:
            continue
        modules = _repository_context_flag_modules(content, flag)
        if not modules:
            continue
        changed_occurrences = int(change.get("changed_occurrences") or 1)
        if len(modules) > changed_occurrences:
            # The compare proves fewer occurrences changed than currently exist.
            # Without hunk-to-module certainty, do not overstate which sibling
            # modules the user's vague phrase controls. Generic extraction can
            # still store narrower facts if Foundry can prove them from evidence.
            continue
        relation_tokens = _repository_context_term_tokens(flag)
        for module in modules:
            relation_tokens |= _repository_context_term_tokens(module.get("module") or "")
        # A vague relationship must still have a semantic bridge to the changed
        # repository control; this avoids storing unrelated Boolean changes from
        # an older cumulative branch diff.
        if phrase_tokens and not (phrase_tokens & relation_tokens):
            continue
        grouped.setdefault((path, flag), []).extend(modules)

    stored = 0
    rejected = 0
    for (path, flag), modules in grouped.items():
        module_names = list(dict.fromkeys(str(item.get("module") or "") for item in modules if item.get("module")))
        # If the user already named both the exact flag and module, this is not a
        # useful alias/clarification to store.
        prompt_lower = prompt.lower()
        if flag.lower() in prompt_lower and module_names and all(name.lower() in prompt_lower for name in module_names):
            continue
        evidence: list[dict] = []
        seen_excerpt: set[str] = set()
        for item in modules:
            for excerpt in item.get("evidence") or []:
                exact = str(excerpt or "").strip()
                if not exact or exact in seen_excerpt:
                    continue
                seen_excerpt.add(exact)
                evidence.append({
                    "path": path,
                    "excerpt": exact,
                    "reason": f'Live Terraform shows {flag} inside module "{item.get("module")}".',
                })
        if not evidence:
            continue
        module_text = ", ".join(f'`{name}`' for name in module_names)
        candidate = {
            "category": "resolved_clarification",
            "subject": phrase,
            "scope": path,
            "statement": (
                f'In `{path}`, the user-facing repository phrase "{phrase}" is controlled by '
                f'`{flag}` in module(s) {module_text}.'
            ),
            "confidence": 0.98,
            "evidence": evidence,
            "validation_summary": (
                "The completed code change changed this Boolean control in the enclosing live Terraform "
                "module block(s), making the vague request-to-control relationship reusable for future tasks."
            ),
        }
        try:
            result = add_repository_context(
                owner,
                repo,
                commit_sha,
                candidate,
                evidence_branch=branch,
                source_task_hash=f"{task_hash}:control:{hashlib.sha1((path + flag + phrase).encode('utf-8')).hexdigest()}",
            )
        except Exception as exc:
            result = {"stored": False, "errors": [str(exc)]}
        if result.get("stored"):
            stored += 1
        else:
            rejected += 1
            LOGGER.warning(
                "[TerrabotDiag] event=repository_context_control_relationship_rejected repo=%s/%s phrase=%s flag=%s modules=%s errors=%s",
                owner, repo, phrase, flag, module_names, result.get("errors") or [],
            )

    LOGGER.warning(
        "[TerrabotDiag] event=repository_context_control_relationship_completed repo=%s/%s phrase=%s stored=%s rejected=%s",
        owner, repo, phrase, stored, rejected,
    )
    return {"ok": True, "stored": stored, "rejected": rejected}

def _extract_and_store_repository_context_after_commit(
    agent_result: dict,
    prompt: str,
    branch_result: dict,
    thread_id: str,
) -> dict:
    """Best-effort post-task extraction. Never blocks a successful commit."""
    try:
        payload, owner, repo, branch, task_hash = _repository_context_completed_task_payload(
            agent_result,
            prompt,
            branch_result,
            thread_id,
        )
    except Exception as exc:
        LOGGER.warning(
            "[TerrabotDiag] event=repository_context_extraction_packet_failed error=%s",
            exc,
        )
        return {"ok": False, "stored": 0, "error": str(exc)}

    LOGGER.warning(
        "[TerrabotDiag] event=repository_context_extraction_started repo=%s/%s branch=%s task_hash=%s",
        owner,
        repo,
        branch,
        task_hash[:12],
    )

    # First persist any deterministic vague-request -> Boolean/module/file
    # relationship proved by the actual committed diff. Generic extraction below
    # can still add broader architecture/convention knowledge.
    relationship_result = _store_vague_request_control_relationships(
        payload, owner, repo, branch, task_hash
    )
    try:
        extraction_text = call_named_agent(
            json.dumps(payload, ensure_ascii=False),
            AGENT_NAME,
        )
        candidates = shared_repository_context.parse_context_extraction_response(extraction_text)
    except Exception as exc:
        LOGGER.warning(
            "[TerrabotDiag] event=repository_context_extraction_agent_failed repo=%s/%s error=%s",
            owner,
            repo,
            exc,
        )
        return {"ok": False, "stored": 0, "error": str(exc)}

    stored = int(relationship_result.get("stored") or 0)
    rejected = int(relationship_result.get("rejected") or 0)
    actions: list[dict] = []
    commit_sha = str(payload.get("evidence_commit_sha") or "")
    for candidate in candidates[:12]:
        candidate = _repository_context_allowed_category(candidate)
        try:
            result = add_repository_context(
                owner,
                repo,
                commit_sha,
                candidate,
                evidence_branch=branch,
                source_task_hash=task_hash,
            )
        except Exception as exc:
            result = {"ok": False, "stored": False, "errors": [str(exc)]}
        if result.get("stored"):
            stored += 1
        else:
            rejected += 1
        actions.append({
            "action": result.get("action") or "rejected",
            "context_id": ((result.get("record") or {}).get("id") or ""),
            "errors": result.get("errors") or [],
        })

    LOGGER.warning(
        "[TerrabotDiag] event=repository_context_extraction_completed repo=%s/%s candidates=%s stored=%s rejected=%s",
        owner,
        repo,
        len(candidates),
        stored,
        rejected,
    )
    return {
        "ok": True,
        "candidate_count": len(candidates),
        "stored": stored,
        "rejected": rejected,
        "actions": actions,
    }


def commit_terraform_files_to_branch_for_teams(agent_result: dict, prompt: str, thread_id: str) -> dict:
    """Validate and transport Foundry output without rewriting Terraform."""
    _prompt_guard_validate_semantic_relevance(agent_result, prompt)
    _prompt_guard_validate_terraform_shape(agent_result)
    _prompt_guard_agent_self_validate(agent_result, prompt)
    # Use the branch writer that consumes agent_result files directly. The
    # backend must not run surgical materializers, flag togglers, object
    # synthesizers, tfvars mergers, brace repair, or repository-code generators.
    branch_result = _commit_terraform_files_to_branch_for_teams_base(agent_result, prompt, thread_id)
    # Persist only durable repository conclusions after the task has passed the
    # backend validators and the final files are actually on the GitHub branch.
    context_result = _extract_and_store_repository_context_after_commit(
        agent_result, prompt, branch_result, thread_id
    )
    branch_result["repository_context_update"] = {
        "stored": int(context_result.get("stored") or 0),
        "rejected": int(context_result.get("rejected") or 0),
    }
    return branch_result

# =============================================================================
# 2026-08-18 TARGET main.tf + AGENT-OWNED FLAG RESOLUTION + PRESERVATION GUARD
# =============================================================================
# Final override. The backend retrieves authoritative repository code and
# validates preservation only. Foundry remains solely responsible for deciding
# which module/Boolean implements the user's request and for generating HCL.

_AGENT_MAIN_TF_PREVIOUS_BUILD_EXISTING_CONTEXT = build_backend_existing_infra_modification_context
_AGENT_MAIN_TF_PREVIOUS_GITHUB_PUT_IF_CHANGED = github_put_file_if_changed


def _teams_target_environment_main_tf_evidence(
    prompt: str,
    cloud: str,
    workflow: str,
    branch: str,
) -> list[dict]:
    """Return complete live target-environment main.tf files when they exist.

    This is structural repository retrieval only. It deliberately does not
    choose a module, resource, or flag. Foundry receives the complete consumer
    file and performs the semantic resolution.
    """
    try:
        normalized_cloud = normalize_cloud(cloud)
    except Exception:
        return []
    if normalized_cloud != "aws":
        return []

    repo_target = normalize_repo_target(
        normalized_cloud,
        workflow=workflow,
    )
    environment_paths = _teams_requested_aws_environment_paths(prompt, branch=branch)
    if not environment_paths:
        exact_environment = _teams_exact_aws_environment_path(prompt)
        if exact_environment:
            environment_paths = [exact_environment]

    evidence: list[dict] = []
    for environment_path in environment_paths:
        main_path = f"{str(environment_path).strip().strip('/')}/main.tf"
        try:
            content = github_get_file_content(
                "aws",
                main_path,
                branch,
                repo_target=repo_target,
                workflow=workflow,
            )
        except Exception:
            content = None
        if content is None:
            continue
        evidence.append({
            "path": main_path,
            "filename": "main.tf",
            "content": content,
            "reason": (
                "authoritative target-environment consumer main.tf from live GitHub; "
                "Foundry must resolve the requested module and any controlling Boolean here"
            ),
        })
    return evidence


def build_backend_existing_infra_modification_context_stage4(
    prompt: str,
    thread_id: str,
    cloud: str,
    workflow: str,
    retrieved_value_context: list | None = None,
) -> dict:
    """Prefer complete target main.tf evidence for Teams enable/disable turns.

    No semantic module or flag decision is made here. The backend only resolves
    the environment and reads the authoritative consumer file. This prevents
    repository-wide keyword matches such as backend.tf, outputs.tf, SSM data
    sources, or unrelated parameter files from becoming user choices.
    """
    context = _AGENT_MAIN_TF_PREVIOUS_BUILD_EXISTING_CONTEXT(
        prompt,
        thread_id,
        cloud,
        workflow,
        retrieved_value_context=retrieved_value_context,
    )
    active = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    intent = _teams_feature_flag_intent(prompt)
    if not (active.get("active") and intent in {"enable", "disable"}):
        return context

    context = dict(context or {})
    branch = str(context.get("context_ref") or "").strip()
    if not branch:
        try:
            normalized_cloud = normalize_cloud(cloud)
            repo_target = normalize_repo_target(normalized_cloud, workflow=workflow)
            branch = _teams_remote_context_branch(normalized_cloud, repo_target, workflow)
        except Exception:
            branch = ""

    main_tf_evidence = _teams_target_environment_main_tf_evidence(
        prompt,
        cloud,
        workflow,
        branch,
    )
    if main_tf_evidence:
        # Replace broad keyword candidates with the authoritative environment
        # consumer file(s). Foundry sees the full file and performs module/flag
        # resolution itself.
        context["matched_files"] = main_tf_evidence
        context["matched_file_paths"] = [item["path"] for item in main_tf_evidence]
        context["selection_state"] = "selected"
        context["selected_path"] = main_tf_evidence[0]["path"] if len(main_tf_evidence) == 1 else ""
        context["target_environment_main_tf_first"] = True
        context["agent_resolves_target"] = True
        context["instructions"] = [
            "Treat each supplied target-environment main.tf as authoritative live repository content.",
            "For enable/disable requests, first inspect module blocks in target main.tf. Resolve the user's resource wording to the relevant existing module from its module label, source, comments, arguments, and surrounding repository semantics.",
            "Within semantically relevant module blocks, prefer repository-defined Boolean controls whose current literal value matches the requested transition: disable => true, enable => false. Typical naming shapes such as enable_*, create_*, *_enabled, deploy_*, use_* are examples only, not a whitelist.",
            "Do not surface data sources, SSM parameters, backend/provider/version files, outputs, unrelated arguments, or plain keyword matches as choices when a semantically relevant Boolean control exists.",
            "If exactly one relevant module/Boolean exists, generate the change directly without asking the user.",
            "If multiple genuinely relevant modules remain, ask only which MODULE the user means. Each choice must show the module label and the relevant Boolean flag(s) found inside that module; do not ask the user to choose a file when all choices are in target main.tf.",
            "Return the COMPLETE final file content for every modified existing file. Copy every unrelated existing line/block/comment exactly and change only the requested assignment(s). Never use placeholders such as '<existing content preserved as in evidence>', ellipses standing for omitted repository code, or abbreviated file bodies.",
            "The backend will reject destructive/truncated full-file responses; it will not merge or synthesize Terraform on Foundry's behalf.",
        ]
    return context
build_backend_existing_infra_modification_context = build_backend_existing_infra_modification_context_stage4


