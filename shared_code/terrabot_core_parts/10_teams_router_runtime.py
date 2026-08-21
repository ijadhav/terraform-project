from __future__ import annotations
def _build_agent_input_for_infra_safe(
    prompt: str,
    thread_id: str,
    selected_cloud: Optional[str] = None,
    workflow: Optional[str] = None,
    retrieved_module_context: Optional[list] = None,
    retrieved_value_context: Optional[list] = None,
) -> str:
    """Append stricter Teams-only targeting/preservation rules at runtime."""
    retrieved_value_context = _teams_ensure_variables_tf_evidence(selected_cloud, retrieved_value_context)
    raw = _TEAMS_SAFE_PREVIOUS_BUILD_AGENT_INPUT(
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
    try:
        payload = json.loads(raw)
    except Exception:
        return raw

    selected_context = _get_backend_existing_infra_context(retrieved_value_context or [])
    scope_root = str(selected_context.get("scope_root") or active.get("target_scope_root") or "").strip()
    if scope_root:
        payload["teams_target_scope"] = {
            "root": scope_root,
            "reason": selected_context.get("scope_reason") or active.get("target_scope_reason") or "prompt-resolved live GitHub folder",
            "hard_boundary": True,
        }

    instructions = list(payload.get("instructions") or [])
    instructions.extend([
        "TEAMS TARGET SCOPE: when teams_target_scope is present, inspect and propose modification targets only inside that root. Do not list or edit matches from other hubs/environments.",
        "TEAMS VISIBLE ANALYSIS: analysis must state the live repository and branch inspected, how the target hub/environment/file was inferred from the prompt, the evidence paths used, the exact assignment/block changed, and what unrelated content was preserved.",
        "TEAMS SURGICAL MODIFICATION: for modification workflows, do not add related settings the user did not request and do not remove omitted code. Change only prompt-relevant existing assignments or blocks in the selected file.",
        "The backend rebases modification output onto the latest live file and rejects broad replacements. Return a full, terraform-fmt-compatible proposal for the selected path, but preserve every unrelated assignment, block, comment, and blank line.",
        "A switch between AWS/tf-devops and Azure/tf-azure-hub is a repository switch: use a new branch from that repository's latest remote base and rebuild repository context rather than reusing the other repository's branch.",
        "If the prompt also requests a PR, complete code generation and branch creation first, retain the PR intent through any clarification, then create/refresh the PR after Jira collection.",
        "TEAMS AGENT SELF-VALIDATION (HARD): before returning any existing file, compare the candidate against the exact live file supplied in backend context. Start from the live text, not a reconstruction. Every differing line must be directly required by the current user prompt; remove all formatting-only, comment, blank-line, ordering, naming, or unrelated changes.",
        "TEAMS COMPLETE-FILE GUARANTEE (HARD): files[] must contain the complete final file for every existing path. Never return a shortened file, excerpt, changed block, ellipsis, placeholder, or reconstructed subset. If the live file is much longer than your candidate, treat that as self-validation failure and rebuild from the live file before responding.",
        "TEAMS THREE-MODE PRESERVATION (HARD): Boolean enable/disable = only the selected Boolean literal may differ; existing-resource modification = only a small prompt-related local delta may differ; creation in an existing file = preserve the live file exactly and append/insert only the new requested repository-pattern entry with all unrelated bytes unchanged.",
    ])
    payload["instructions"] = instructions
    return json.dumps(payload, indent=2)


def _teams_safe_result_analysis(result: dict, prompt: str, requested_cloud: str = "") -> str:
    candidates = result.get("candidates") or []
    state = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    scope_root = str(state.get("target_scope_root") or "").strip()
    scope_reason = str(state.get("target_scope_reason") or "").strip()
    if not scope_root and candidates:
        candidate_dirs = {
            str(item.get("path") or "").strip().rsplit("/", 1)[0]
            for item in candidates
            if isinstance(item, dict) and "/" in str(item.get("path") or "")
        }
        if len(candidate_dirs) == 1:
            scope_root = next(iter(candidate_dirs))
            scope_reason = "all live GitHub candidates matched the same prompt-resolved folder"
    lines = []
    cloud = requested_cloud or str((result.get("router") or {}).get("cloud") or result.get("cloud") or "").strip()
    repo = GITHUB_AZURE_REPO if cloud == "azure" else GITHUB_AWS_REPO if cloud == "aws" else ""
    if repo:
        lines.append(f"Repository: `{GITHUB_OWNER}/{repo}`; candidates were read from live GitHub content.")
    if scope_root:
        lines.append(f"Prompt scope: `{scope_root}` ({scope_reason or 'matched from the user prompt'}).")
    if candidates:
        lines.append(f"Target discovery: returned {len(candidates)} candidate(s) inside the resolved scope only.")
        lines.append("Evidence: " + ", ".join(f"`{item.get('path')}`" for item in candidates[:6] if item.get("path")) + ".")
    lines.append("Safety: the selected file is the only allowed write target; unrelated files and code are preserved.")
    return "\n".join(lines)


def _handle_teams_chat_request_targeted(data: dict):
    """Final Teams wrapper: cross-repository isolation plus analysis metadata."""
    request_data = dict(data or {})
    prompt = str(request_data.get("prompt") or request_data.get("message") or "").strip()
    action = str(request_data.get("action") or "").strip().lower()
    teams_conversation_id = str(
        request_data.get("teams_conversation_id")
        or request_data.get("conversation_id")
        or ""
    ).strip()
    state = load_teams_conversation_state(teams_conversation_id) if teams_conversation_id else {}
    requested_cloud = _teams_safe_request_cloud(prompt)
    active_cloud = safe_normalize_cloud(str(state.get("cloud") or "")) or ""
    branch = str(state.get("branch") or "").strip()
    cross_repo_switch = False

    # Carry an already-detected repository switch through numeric/path/Jira
    # clarification replies until the new repository branch has been created.
    if not action and _teams_truthy(state.get("force_new_branch")) and state.get("pending_target_cloud"):
        request_data["force_new_branch"] = True
        request_data["reuse_branch"] = False
        request_data["existing_branch"] = ""

    if (
        not action
        and branch
        and requested_cloud
        and active_cloud
        and requested_cloud != active_cloud
        and str(request_data.get("mode") or "").strip().lower() == "infra"
    ):
        cross_repo_switch = True
        request_data["force_new_branch"] = True
        request_data["reuse_branch"] = False
        request_data["existing_branch"] = ""
        # A repository switch is the Teams equivalent of a VS Code workspace
        # switch. Start a fresh Foundry conversation so old-repo file memory
        # cannot leak into the new repository analysis.
        switch_patch = {
            "stage": "processing_cross_repository",
            "force_new_branch": True,
            "reuse_branch": False,
            "pending_target_cloud": requested_cloud,
            "pending_previous_cloud": active_cloud,
            "workflow_thread_id": None,
            "foundry_conversation_id": None,
        }
        _teams_save_ui_state(teams_conversation_id, switch_patch)
        request_data["thread_id"] = ""

    result, status_code = _TEAMS_SAFE_PREVIOUS_HANDLE_CHAT(request_data)
    result = dict(result or {})

    if requested_cloud and not result.get("cloud"):
        result["cloud"] = requested_cloud
    if requested_cloud == "aws" and not result.get("repo_target"):
        result["repo_target"] = "tf-devops"
    elif requested_cloud == "azure" and not result.get("repo_target"):
        result["repo_target"] = "tf-azure-hub"

    if result.get("decision_state") == "infra_modification_target_selection" and not result.get("analysis"):
        result["analysis"] = _teams_safe_result_analysis(result, prompt, requested_cloud)

    if cross_repo_switch:
        existing_patch = dict(result.get("state_patch") or {})
        existing_patch.update({
            "force_new_branch": True,
            "reuse_branch": False,
            "pending_target_cloud": requested_cloud,
            "pending_previous_cloud": active_cloud,
        })
        result["state_patch"] = existing_patch

    if result.get("mode") in {"branch_created", "pr_created"} or result.get("pr_url"):
        existing_patch = dict(result.get("state_patch") or {})
        existing_patch.update({
            "force_new_branch": None,
            "reuse_branch": None,
            "pending_target_cloud": None,
            "pending_previous_cloud": None,
        })
        result["state_patch"] = existing_patch

    return result, status_code

# =============================================================================
# Teams AWS missing-module creation parity with VS Code repository-aware mode
# =============================================================================
# This addendum is intentionally Teams-scoped. It preserves every existing
# VS Code/backend entry point and only changes live-GitHub AWS discovery and
# new-module generation while a Teams request context is active.

_TEAMS_AWS_NEW_MODULE_PREVIOUS_DISCOVER = _discover_live_aws_module_candidates_base
_TEAMS_AWS_NEW_MODULE_PREVIOUS_BUILD_INPUT = _build_agent_input_for_aws_module_creation_base
_TEAMS_AWS_NEW_MODULE_PREVIOUS_NORMALIZE_VARIABLES = _normalize_module_variables_tf_content_base
_TEAMS_AWS_NEW_MODULE_PREVIOUS_AUTO_ACCEPT = _teams_auto_accept_aws_module_creation_base

_TEAMS_AWS_WEAK_MATCH_TOKENS = {
    "app", "application", "aws", "base", "common", "component", "core",
    "default", "generic", "helper", "infra", "infrastructure", "instance",
    "main", "module", "object", "resource", "service", "shared", "simple",
    "terraform",
}
_TEAMS_AWS_ENVIRONMENT_TOKEN_RE = re.compile(
    r"^(?:dev|development|minidev|nonprod|npr|prd|prod|production|sbx|sandbox|"
    r"stage|staging|stg|test|testing|uat|us\d+|eu\d+|ca\d+|ap\d+)$",
    re.IGNORECASE,
)
_TEAMS_AWS_CONTEXT_MAX_CHARS = 96_000


def _teams_aws_discriminative_tokens(value: str) -> set[str]:
    """Return resource-specific tokens, excluding generic request/path words."""
    tokens = set(_aws_module_lookup_tokens(value, keep_stop_words=False))
    return {
        token
        for token in tokens
        if token not in _TEAMS_AWS_WEAK_MATCH_TOKENS
        and not _TEAMS_AWS_ENVIRONMENT_TOKEN_RE.fullmatch(token or "")
    }


def _teams_aws_match_has_resource_evidence(prompt: str, match: dict) -> tuple[bool, list[str]]:
    """Reject catalog matches supported only by generic words such as instance.

    This remains generic for every AWS module: a candidate is accepted when a
    discriminative token from the request occurs in the real live-catalog path,
    or when the request explicitly names the catalog path/name. No service to
    module-name table is maintained here.
    """
    module_path = _sanitize_aws_module_rel_path(
        str((match or {}).get("module_path") or (match or {}).get("verified_module_path") or "")
    )
    if not module_path:
        return False, ["missing_module_path"]

    prompt_specific = _teams_aws_discriminative_tokens(prompt)
    if not prompt_specific:
        # An underspecified request such as "create an instance" should remain
        # interactive instead of being treated as proof that no module exists.
        return True, ["request_has_no_discriminative_resource_token"]

    module_specific = _teams_aws_discriminative_tokens(module_path)
    overlap = sorted(prompt_specific & module_specific)
    if overlap:
        return True, ["resource_token_overlap:" + ",".join(overlap)]

    prompt_text = _aws_module_lookup_text(prompt)
    for phrase in _aws_module_catalog_phrases(module_path):
        phrase_specific = _teams_aws_discriminative_tokens(phrase)
        if (
            phrase_specific
            and phrase_specific & prompt_specific
            and re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", prompt_text)
        ):
            return True, [f"explicit_catalog_phrase:{phrase}"]

    return False, [
        "generic_only_match",
        "request_tokens:" + ",".join(sorted(prompt_specific)),
        "module_tokens:" + ",".join(sorted(module_specific)),
    ]


def discover_live_aws_module_candidates(
    prompt: str,
    environment_path: str = "",
    branch: Optional[str] = None,
    max_matches: int = 6,
) -> dict:
    """Discover only resource-relevant AWS modules for Teams requests.

    Non-Teams callers retain the original discovery implementation unchanged.
    Teams previously called the original top-N materializer first; generic words
    such as ``instance`` caused unrelated IAM/RDS candidates to be opened before
    the Teams semantic filter ran. Besides wasting GitHub/Foundry context, that
    path amplified the missing public ``build_verified_aws_module_context`` bug.
    Teams now scores the complete live catalog first, filters by discriminative
    resource evidence, and materializes context only for accepted candidates.
    """
    active = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    if not active.get("active"):
        return _TEAMS_AWS_NEW_MODULE_PREVIOUS_DISCOVER(
            prompt,
            environment_path=environment_path,
            branch=branch,
            max_matches=max_matches,
        )

    effective_branch = branch
    if not effective_branch:
        try:
            effective_branch = _teams_remote_context_branch(
                "aws",
                repo_target="tf-devops",
                workflow="aws_module_consumer",
            )
        except Exception:
            effective_branch = branch
    effective_branch = effective_branch or _aws_module_catalog_branch()

    catalog = github_list_verified_aws_module_paths(effective_branch)
    accepted_candidates: list[tuple[int, str, list[str], list[str]]] = []
    rejected: list[dict] = []

    for raw_path in catalog:
        module_path = _sanitize_aws_module_rel_path(raw_path)
        if not module_path:
            continue
        score, original_reasons = _score_aws_module_candidate(prompt, module_path)
        if score <= 0:
            continue
        seed = {
            "module_path": module_path,
            "verified_module_path": f"{AWS_MODULES_ROOT}/{module_path}",
            "match_score": score,
            "match_reasons": original_reasons,
        }
        keep, confidence_reasons = _teams_aws_match_has_resource_evidence(prompt, seed)
        if keep:
            accepted_candidates.append((int(score), module_path, list(original_reasons or []), confidence_reasons))
        else:
            rejected.append({
                "module_path": module_path,
                "match_score": int(score),
                "match_reasons": list(original_reasons or []),
                "rejection_reasons": confidence_reasons,
            })

    accepted_candidates.sort(key=lambda item: (-item[0], item[1]))
    selected = accepted_candidates[:max(1, int(max_matches or 6))]
    matches: list[dict] = []
    for score, module_path, original_reasons, confidence_reasons in selected:
        try:
            item = build_verified_aws_module_context(
                module_path,
                branch=effective_branch,
                environment_path=environment_path,
                include_examples=True,
            )
        except Exception as exc:
            # Preserve discovery continuity for a genuinely relevant module, but
            # never fan out into unrelated module contexts. The accepted path
            # itself remains useful evidence and deterministic recovery can retry
            # the detailed read later.
            LOGGER.warning("Could not build Teams context for relevant AWS module %s: %s", module_path, exc)
            item = {
                "cloud": "aws",
                "repo_target": "tf-devops",
                "module_path": module_path,
                "verified_module_path": f"{AWS_MODULES_ROOT}/{module_path}",
                "module_source": build_aws_local_module_source(module_path, environment_path),
                "resolved_ref": effective_branch,
                "source": "live_github_tf_devops_terraform_modules",
                "inspection_error": str(exc),
            }
        item = dict(item or {})
        item["match_score"] = score
        item["match_reasons"] = original_reasons
        item["teams_match_confidence"] = confidence_reasons
        matches.append(item)

    base = {
        "requested_resource_hint": infer_aws_requested_resource_hint(prompt),
        "repo_full_name": f"{GITHUB_OWNER}/{GITHUB_AWS_REPO}",
        "module_root": AWS_MODULES_ROOT,
        "resolved_ref": effective_branch,
        "matches": matches,
        "available_module_paths_sample": list(catalog[:80]),
        "catalog_count": len(catalog),
        "rejected_generic_matches": rejected[:80],
        "teams_semantic_filter_applied": True,
    }
    if matches:
        best_score = max(int(item.get("match_score") or 0) for item in matches)
        base.update({
            "status": "exact_match" if best_score >= 100 else "similar_match",
            "decision_state": "aws_module_verified",
        })
        return base

    base.update({
        "status": "not_found",
        "decision_state": "aws_module_not_found",
    })
    return base


def normalize_module_variables_tf_content_stage1(
    content: str,
    filename: str,
    workflow: str,
    user_prompt: str = "",
) -> tuple[str, list[str]]:
    """Keep unresolved Teams-created module inputs required.

    The historical backend normalizer adds deterministic ``false``/``-1``
    defaults to newly generated bool/number inputs. That is useful for older
    workflows, but it hides required values in the Teams branch-first flow.
    For Teams AWS module creation only, inputs that had no default in the
    agent's module definition remain required; the consumer receives a typed
    ``__FILL__`` value instead. Agent-provided or explicit-prompt defaults are
    preserved. Existing non-Teams behavior is unchanged.
    """
    original_blocks = {
        str(item.get("name") or ""): str(item.get("block") or "")
        for item in _iter_variable_blocks_with_names(content or "")
        if str(item.get("name") or "")
    }
    updated, issues = _TEAMS_AWS_NEW_MODULE_PREVIOUS_NORMALIZE_VARIABLES(
        content,
        filename,
        workflow,
        user_prompt=user_prompt,
    )
    active = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    if active.get("active") and workflow == "aws_module_creation":
        # Remove only defaults that the previous normalizer injected. A default
        # present in the original Foundry file is repository/model evidence and
        # remains intact. An explicit prompt value also remains intact.
        updated_blocks = {
            str(item.get("name") or ""): str(item.get("block") or "")
            for item in _iter_variable_blocks_with_names(updated or "")
            if str(item.get("name") or "")
        }
        for name, original_block in original_blocks.items():
            if _variable_attr_present(original_block, "default"):
                continue
            type_expr = (
                _variable_type_from_block(original_block)
                or _infer_variable_type_from_name_and_default(name, original_block)
                or "string"
            )
            if _explicit_prompt_default_for_variable(user_prompt, name, type_expr):
                continue
            normalized_block = updated_blocks.get(name) or ""
            if not normalized_block or not _variable_attr_present(normalized_block, "default"):
                continue
            required_block = re.sub(
                r"(?m)^\s*default\s*=\s*[^\n]+\n?",
                "",
                normalized_block,
                count=1,
            )
            updated = _replace_variable_block(updated, name, required_block)

        issues = [
            issue
            for issue in issues
            if "is a string without a backend-approved or user-provided default" not in str(issue)
        ]
    return (updated or "").rstrip() + "\n", issues
normalize_module_variables_tf_content = normalize_module_variables_tf_content_stage1


def _teams_aws_context_snippet(content: str, limit: int = 14_000) -> str:
    text = str(content or "").replace("\r\n", "\n")
    if len(text) <= limit:
        return text
    half = max(1, limit // 2)
    return (
        text[:half]
        + "\n\n# --- backend evidence truncated; middle omitted ---\n\n"
        + text[-half:]
    )


def _teams_aws_new_module_context_pack(
    prompt: str,
    proposed_module_path: str,
    environment_path: str,
    discovery: dict | None = None,
) -> dict:
    """Build a live-GitHub context pack mirroring VS Code workspace evidence."""
    discovery = dict(discovery or {})
    active = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    branch = str(discovery.get("resolved_ref") or "").strip()
    if not branch:
        try:
            branch = _teams_remote_context_branch(
                "aws",
                repo_target="tf-devops",
                workflow="aws_module_creation",
            )
        except Exception:
            branch = _aws_module_catalog_branch()
    branch = branch or _aws_module_catalog_branch()

    proposed_module_path = _sanitize_aws_module_rel_path(proposed_module_path)
    environment_path = str(environment_path or "terraform/dev_aws/minidev").strip().strip("/")
    module_root = f"{AWS_MODULES_ROOT}/{proposed_module_path}"
    consumer_source = build_aws_local_module_source(proposed_module_path, environment_path)
    variable_convention = detect_aws_module_variable_file_convention(prompt)
    preferred_variable_file = variable_convention.get("preferred_variable_file_name") or "vars.tf"

    evidence: list[dict] = []
    evidence_paths: set[str] = set()
    total_chars = 0

    def add_evidence(path: str, kind: str, reason: str, content: str = "") -> None:
        nonlocal total_chars
        normalized_path = str(path or "").strip().strip("/")
        if not normalized_path or normalized_path in evidence_paths:
            return
        snippet = _teams_aws_context_snippet(content, limit=14_000) if content else ""
        remaining = _TEAMS_AWS_CONTEXT_MAX_CHARS - total_chars
        if remaining <= 0:
            return
        if len(snippet) > remaining:
            snippet = _teams_aws_context_snippet(snippet, limit=remaining)
        evidence.append({
            "path": normalized_path,
            "kind": kind,
            "reason": reason,
            "snippet": snippet,
        })
        evidence_paths.add(normalized_path)
        total_chars += len(snippet)

    # Target environment files are the Teams equivalent of the active VS Code
    # workspace and determine consumer placement, wiring, names, tags and style.
    target_environment_files: list[str] = []
    try:
        env_items = github_get_directory_listing(
            "aws",
            environment_path,
            branch,
            repo_target="tf-devops",
            workflow="aws_module_creation",
        ) or []
    except Exception as exc:
        LOGGER.warning("Could not list AWS target environment %s@%s: %s", environment_path, branch, exc)
        env_items = []
    def _aws_env_evidence_priority(value: dict) -> tuple[int, str]:
        path = str((value or {}).get("path") or "").strip()
        name = path.rsplit("/", 1)[-1].lower()
        priority = {
            "main.tf": 0,
            "locals.tf": 1,
            "variables.tf": 2,
            "vars.tf": 2,
            "outputs.tf": 8,
            "backend.tf": 9,
            "versions.tf": 9,
            "providers.tf": 9,
            "provider.tf": 9,
        }
        return priority.get(name, 4), path

    # main.tf is intentionally read first.  tf-devops environments commonly
    # use it as the consolidated consumer file, and it must never be omitted
    # merely because the environment contains more than the bounded evidence
    # limit.
    for item in sorted(env_items, key=_aws_env_evidence_priority):
        if not isinstance(item, dict) or item.get("type") != "file":
            continue
        path = str(item.get("path") or "").strip()
        if not path.endswith((".tf", ".tfvars", ".hcl")):
            continue
        try:
            content = github_get_file_content(
                "aws",
                path,
                branch,
                repo_target="tf-devops",
                workflow="aws_module_creation",
            ) or ""
        except Exception:
            content = ""
        target_environment_files.append(path)
        add_evidence(
            path,
            "target_environment_file",
            "Live target-environment file used to infer consumer placement and wiring style.",
            content,
        )
        if len(target_environment_files) >= 12:
            break

    target_main_tf = f"{environment_path}/main.tf"
    target_consumer_file = (
        target_main_tf
        if target_main_tf in target_environment_files
        else ""
    )

    # Select structural module examples from the real catalog. These are
    # explicitly examples of repository layout, not claims that they implement
    # the requested resource.
    try:
        catalog = github_list_verified_aws_module_paths(branch)
    except Exception:
        catalog = list(discovery.get("available_module_paths_sample") or [])
    scored_catalog = []
    for module_path in catalog:
        score, reasons = _score_aws_module_candidate(prompt, module_path)
        scored_catalog.append((int(score or 0), str(module_path), reasons or []))
    scored_catalog.sort(key=lambda item: (-item[0], item[1]))

    structural_paths: list[str] = []
    for _score, module_path, _reasons in scored_catalog:
        if module_path and module_path not in structural_paths:
            structural_paths.append(module_path)
        if len(structural_paths) >= 4:
            break
    if not structural_paths:
        structural_paths = [str(path) for path in catalog[:4] if str(path)]

    module_examples: list[dict] = []
    for module_path in structural_paths:
        module_dir = f"{AWS_MODULES_ROOT}/{module_path}"
        try:
            module_items = github_get_directory_listing(
                "aws",
                module_dir,
                branch,
                repo_target="tf-devops",
                workflow="aws_module_creation",
            ) or []
        except Exception:
            module_items = []
        file_paths = [
            str(item.get("path") or "")
            for item in module_items
            if isinstance(item, dict)
            and item.get("type") == "file"
            and str(item.get("path") or "").endswith(".tf")
        ]
        priority = {"main.tf": 0, preferred_variable_file: 1, "vars.tf": 1, "variables.tf": 1, "outputs.tf": 2, "versions.tf": 3}
        file_paths.sort(key=lambda path: (priority.get(path.rsplit("/", 1)[-1], 10), path))
        selected_files: list[str] = []
        for path in file_paths[:5]:
            try:
                content = github_get_file_content(
                    "aws",
                    path,
                    branch,
                    repo_target="tf-devops",
                    workflow="aws_module_creation",
                ) or ""
            except Exception:
                content = ""
            selected_files.append(path)
            add_evidence(
                path,
                "module_layout_example",
                "Existing tf-devops module used only to infer module file structure, variable declarations, outputs and formatting.",
                content,
            )
        module_examples.append({
            "module_path": module_path,
            "files": selected_files,
            "purpose": "repository structure and formatting example; not a semantic match for the requested resource",
        })

    # Repository policy and documentation are included when present.
    for path, kind, reason in (
        ("README.md", "repository_documentation", "Repository-level workflow and convention documentation."),
        ("terraform/README.md", "terraform_documentation", "Terraform-specific repository instructions."),
        (".terrabot/repo.json", "repository_policy", "Terrabot repository policy."),
        (".terrabot/repo.yaml", "repository_policy", "Terrabot repository policy."),
        (".terrabot/repo.yml", "repository_policy", "Terrabot repository policy."),
        ("azure-pipelines.yml", "pipeline", "Repository validation/pipeline convention."),
    ):
        try:
            content = github_get_file_content(
                "aws",
                path,
                branch,
                repo_target="tf-devops",
                workflow="aws_module_creation",
            ) or ""
        except Exception:
            content = ""
        if content:
            add_evidence(path, kind, reason, content)

    rejected = [
        {
            "module_path": item.get("module_path") or "",
            "reason": item.get("rejection_reasons") or [],
        }
        for item in discovery.get("rejected_generic_matches") or []
        if isinstance(item, dict)
    ]

    return {
        "user_request": prompt,
        "repo_profile": {
            "repo_name": GITHUB_AWS_REPO,
            "repo_full_name": f"{GITHUB_OWNER}/{GITHUB_AWS_REPO}",
            "source_branch": branch,
            "languages": ["Terraform", "HCL"],
            "iac_tools": ["Terraform"],
            "clouds": ["aws"],
            "terraform_roots": [GITHUB_AWS_DIR or "terraform"],
            "module_root": AWS_MODULES_ROOT,
            "target_environment_path": environment_path,
            "target_environment_files": target_environment_files,
            "module_examples": module_examples,
            "preferred_module_variable_file": preferred_variable_file,
            "validation_commands": ["terraform fmt -check -recursive", "terraform validate"],
            "repo_conventions": [
                f"Reusable AWS modules live under {AWS_MODULES_ROOT}/<module_name>.",
                f"The detected module variable declaration filename is {preferred_variable_file}.",
                "Consumers use repository-relative local module source paths.",
                "Generated code must preserve repository naming, wiring, tagging and formatting patterns from evidence.",
            ],
        },
        "workflow_profile": {
            "workflow_type": "aws_module_creation",
            "confidence": "backend_verified_module_absence",
            "cloud": "aws",
            "resource_type": discovery.get("requested_resource_hint") or infer_aws_requested_resource_hint(prompt),
            "target_environment": environment_path.rsplit("/", 1)[-1],
            "target_files": [
                f"{module_root}/main.tf",
                f"{module_root}/{preferred_variable_file}",
                f"{module_root}/outputs.tf",
                *([target_consumer_file] if target_consumer_file else []),
            ],
            "value_files": target_environment_files,
            "consumer_source": consumer_source,
            "questions": [],
        },
        "policy": {
            "allowed": True,
            "blocking_issues": [],
            "warnings": [],
            "rules_applied": [
                "live GitHub repository evidence only",
                "no invented module source/path",
                "no concrete credentials or private values",
                "missing non-sensitive values use tracked __FILL__ tokens",
                "terraform fmt-compatible HCL",
            ],
            "source_files": [item["path"] for item in evidence if item.get("kind") == "repository_policy"],
        },
        "evidence": evidence,
        "generation_contract": {
            "module_path": proposed_module_path,
            "module_root": module_root,
            "module_source": consumer_source,
            "consumer_folder": environment_path,
            "consumer_file": target_consumer_file,
            "consumer_file_rule": (
                "Use the existing target-environment main.tf as the consumer file and preserve its full content."
                if target_consumer_file
                else "Resolve the existing target-environment consumer file from live evidence; never ask the user for placement."
            ),
            "auto_create_when_module_missing": True,
            "required_artifacts": [
                "complete reusable module implementation",
                f"exactly one {preferred_variable_file} module variable file",
                "outputs.tf with useful reviewable outputs",
                "at least one consumer .tf file in the resolved environment folder",
            ],
            "output_mode": "Teams full-file GitHub branch write",
            "branch_name_prefix": "terrabot/",
        },
        "verified_absence": {
            "module_catalog_branch": branch,
            "module_root_checked": AWS_MODULES_ROOT,
            "catalog_count": discovery.get("catalog_count") or len(catalog),
            "requested_resource_hint": discovery.get("requested_resource_hint") or infer_aws_requested_resource_hint(prompt),
            "rejected_generic_matches": rejected,
        },
        "teams_remote_repository_mode": True,
        "active_branch_context": {
            "branch": active.get("existing_branch") if _teams_truthy(active.get("reuse_branch")) else branch,
            "reuse_existing_branch": _teams_truthy(active.get("reuse_branch")),
            "force_new_branch_from_latest_base": _teams_truthy(active.get("force_new_branch")),
        },
    }


def build_agent_input_for_aws_module_creation(
    prompt: str,
    proposed_module_path: str,
    environment_path: str,
    discovery: dict | None = None,
) -> str:
    """Append a VS Code-equivalent live-GitHub context pack for Teams only."""
    raw = _TEAMS_AWS_NEW_MODULE_PREVIOUS_BUILD_INPUT(
        prompt,
        proposed_module_path,
        environment_path,
        discovery=discovery,
    )
    active = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    if not active.get("active"):
        return raw

    try:
        payload = json.loads(raw)
    except Exception:
        return raw

    context_pack = _teams_aws_new_module_context_pack(
        prompt,
        proposed_module_path,
        environment_path,
        discovery=discovery,
    )
    payload["channel"] = "teams"
    payload["source"] = "teams"
    payload["teams_remote_repository_mode"] = True
    payload["context_pack"] = context_pack

    required = dict(payload.get("required_output_shape") or {})
    required.update({
        "mode": "infra",
        "cloud": "aws",
        "workflow": "aws_module_creation",
        "repo_target": "tf-devops",
        "branch_name": "terrabot/<concise-change-slug>",
        "analysis": "3-10 grounded lines explaining repository workflow inference and value sources",
        "source_paths_used": ["real paths from context_pack.evidence"],
        "user_fillable": [
            {
                "token": "__FILL__<input_name>__",
                "input": "<input_name>",
                "file": "repo-relative consumer file",
                "hint": "expected type/format and repository-grounded example when available",
            }
        ],
        "questions": [],
        "validation_commands": ["terraform fmt -check -recursive", "terraform validate"],
    })
    payload["required_output_shape"] = required

    # Strip legacy stop-and-ask rules inherited from the generic builder.
    # In Teams, the original create request plus the branch decision already
    # authorizes missing-module creation. Repository placement/default choices
    # are backend/repository decisions, and unresolved non-sensitive values use
    # __FILL__ tokens instead of another user clarification.
    inherited_instructions = list(payload.get("instructions") or [])
    forbidden_legacy_ask_fragments = (
        "otherwise ask for the string value/reference before returning json",
        "use backend-approved repo references or ask for missing values/references",
        "if the request does not contain enough design detail",
        "if required values, variable meanings, or outputs cannot be inferred",
        "the user confirmed creating a new one",
    )
    instructions = [
        item
        for item in inherited_instructions
        if not any(fragment in str(item).lower() for fragment in forbidden_legacy_ask_fragments)
    ]

    # Point the model at the actual live consumer file. When minidev/main.tf
    # is the consolidated consumer, do not let the legacy required shape steer
    # generation toward a synthetic minidev/<resource>.tf file.
    # Teams AWS new-resource creation always materializes the environment
    # consumer in the target environment's existing main.tf. Foundry may still
    # emit a temporary per-resource consumer filename, but the backend rewrites
    # that consumer into main.tf before validation/commit so no extra
    # <resource>.tf consumer file is created.
    target_consumer_file = f"{str(environment_path or '').strip().strip('/')}/main.tf"
    if target_consumer_file:
        required_files = [
            dict(item) for item in (required.get("files") or []) if isinstance(item, dict)
        ]
        env_prefix = str(environment_path or "").strip().strip("/") + "/"
        for item in required_files:
            filename = str(item.get("filename") or "")
            if filename.startswith(env_prefix) and not filename.startswith(AWS_MODULES_ROOT + "/"):
                item["filename"] = target_consumer_file
        if required_files:
            required["files"] = required_files
            payload["required_output_shape"] = required

    instructions.extend([
        "TEAMS AWS NEW-MODULE MODE: context_pack is the live-GitHub equivalent of the VS Code workspace context_pack and is the sole repository source of truth.",
        "Backend discovery exhaustively scanned terraform/modules and rejected matches supported only by generic words such as instance. Create the proposed new module; do not select one of rejected_generic_matches.",
        "In this Teams aws_module_creation workflow, an empty retrieved_module_context is EXPECTED because the backend has already verified that no matching module exists. Never interpret that empty list as a reason to ask whether a module should be created.",
        "The user's original create/add/provision request already authorizes creation of the missing reusable module under terraform/modules/<resource_family> and its consumer in the resolved environment. Never ask for confirmation, intended module-source pattern, repository placement, or required defaults before generating.",
        "Infer module source depth, file layout, variable/output filename convention, wiring, tags, naming, and defaults from context_pack live repository evidence. If a non-sensitive preference remains unresolved, use the existing __FILL__ mechanism; do not turn it into a module-creation approval question.",
        "For this verified-missing-module path, questions must be empty unless live evidence proves the requested resource already exists or a genuinely sensitive value has no repository-safe reference pattern.",
        "Infer module file layout, variable filename, resource naming, tags, wiring, provider usage, outputs and formatting from context_pack evidence. Generic AWS knowledge may supply provider syntax only; never invent repository-specific names or values.",
        "Before creating the module, inspect target-environment evidence for an existing feature flag or already-enabled resource. If evidence proves the requested resource already exists or is flag-gated, do not create a duplicate; explain the exact evidence in questions. Otherwise continue module creation now.",
        "Return the complete reusable module implementation, exactly one repository-convention variable file, outputs.tf, and at least one consumer .tf file under the backend-resolved environment folder in one response.",
        "The consumer must use the exact backend-provided local relative module_source. Never use a registry, git::, SSH, HTTP or invented source.",
        "Apply explicit non-sensitive values from the prompt directly. Then use same-environment examples, other-environment examples, module/repository defaults and closest comparable repository evidence in that order.",
        "Do not stop generation because non-sensitive preferences are missing. Keep reusable module string inputs required (no invented module defaults) and place syntactically valid __FILL__<input_name>__ values in the consumer with matching user_fillable records.",
        "For private/sensitive inputs, use the repository's demonstrated safe variable/data-source/parameter reference pattern. Never put a literal credential in module or consumer code.",
        "Every generated path must be repo-relative and every source_paths_used entry must exist in context_pack.evidence.",
        "Return terraform-fmt-compatible HCL with complete file contents. Do not return partial files, TODOs, CHANGEME text, scaffold comments or files=[].",
        "analysis must state the live branch inspected, module absence decision, repository patterns copied, target consumer folder, value-inference ladder and any remaining __FILL__ tokens.",
    ])
    payload["instructions"] = instructions
    return json.dumps(payload, indent=2)


def _teams_aws_module_variable_specs_from_generated_files(files: list[dict], module_path: str) -> list[dict]:
    prefix = f"{AWS_MODULES_ROOT}/{_sanitize_aws_module_rel_path(module_path)}/"
    specs: list[dict] = []
    seen: set[str] = set()
    for file_data in files or []:
        if not isinstance(file_data, dict):
            continue
        filename = normalize_tf_relative_path(file_data.get("filename") or file_data.get("path") or "")
        if not filename.startswith(prefix) or not filename.endswith(("vars.tf", "variables.tf")):
            continue
        for item in _iter_variable_blocks_with_names(str(file_data.get("content") or "")):
            name = str(item.get("name") or "").strip()
            if not name or name in seen:
                continue
            block = str(item.get("block") or "")
            type_expr = _variable_type_from_block(block) or _infer_variable_type_from_name_and_default(name, block)
            default_expr = _variable_attr_value(block, "default") if _variable_attr_present(block, "default") else ""
            specs.append({
                "name": name,
                "type": type_expr or "string",
                "default": default_expr,
                "required": not bool(default_expr),
                "sensitive": _variable_name_is_private_or_sensitive(name),
                "description": _module_variable_field_description(block, name),
                "source_path": filename,
            })
            seen.add(name)
    return specs


def _teams_aws_insert_missing_consumer_inputs(
    agent_result: dict,
    proposed_module_path: str,
    original_prompt: str,
) -> dict:
    """Ensure every new module required input is wired in its consumer."""
    updated = dict(agent_result or {})
    files = [dict(item) for item in updated.get("files") or [] if isinstance(item, dict)]
    module_path = _sanitize_aws_module_rel_path(proposed_module_path)
    specs = _teams_aws_module_variable_specs_from_generated_files(files, module_path)
    required_specs = [item for item in specs if item.get("required")]
    if not required_specs:
        updated["files"] = files
        return updated

    fillable = [dict(item) for item in updated.get("user_fillable") or [] if isinstance(item, dict)]
    fillable_tokens = {str(item.get("token") or "") for item in fillable}
    found_consumer = False

    for file_data in files:
        filename = normalize_tf_relative_path(file_data.get("filename") or file_data.get("path") or "")
        if not filename.startswith("terraform/") or filename.startswith(f"{AWS_MODULES_ROOT}/"):
            continue
        content = str(file_data.get("content") or "").replace("\r\n", "\n")
        for block in _extract_top_level_tf_blocks(content):
            header = str(block.get("header") or "")
            if not re.match(r'^module\s+"[^\"]+"$', header):
                continue
            block_text = str(block.get("block") or "")
            source_match = re.search(r'(?m)^\s*source\s*=\s*"([^"]+)"', block_text)
            if not source_match or normalize_aws_module_source_path(source_match.group(1)) != module_path:
                continue
            found_consumer = True
            assigned = {
                name
                for name in re.findall(r'(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=', block_text)
                if name != "source"
            }
            additions: list[tuple[str, str]] = []
            for spec in required_specs:
                name = str(spec.get("name") or "").strip()
                if not name or name in assigned:
                    continue
                explicit = "" if spec.get("sensitive") else _explicit_prompt_default_for_variable(
                    original_prompt,
                    name,
                    str(spec.get("type") or "string"),
                )
                if explicit:
                    expression = explicit
                else:
                    expression, token = _teams_placeholder_expression(name, str(spec.get("type") or "string"))
                    if token not in fillable_tokens:
                        hint = f"Required {spec.get('type') or 'string'} input"
                        if spec.get("sensitive"):
                            hint += "; supply the repository-approved reference/identifier, never a literal secret"
                        else:
                            hint += "; use a value consistent with the target environment and repository examples"
                        fillable.append({
                            "token": token,
                            "input": name,
                            "file": filename,
                            "hint": hint,
                        })
                        fillable_tokens.add(token)
                additions.append((name, expression))

            if additions:
                closing = block_text.rfind("}")
                if closing < 0:
                    raise ValueError(f"Generated consumer module block is malformed in {filename}.")
                longest = max(len(name) for name, _value in additions)
                lines = [
                    f"  {name}{' ' * (longest - len(name) + 1)}= {value}"
                    for name, value in additions
                ]
                prefix = block_text[:closing].rstrip()
                suffix = block_text[closing:]
                replacement = prefix + "\n\n" + "\n".join(lines) + "\n" + suffix
                content = content.replace(block_text, replacement, 1)
                file_data["content"] = content.rstrip() + "\n"
            break

    if not found_consumer:
        raise ValueError(
            f"No consumer module block references the new module {AWS_MODULES_ROOT}/{module_path}."
        )

    updated["files"] = files
    updated["user_fillable"] = fillable
    return updated


def _teams_aws_live_consumer_content_from_context(context_pack: dict, environment_path: str) -> tuple[str, str]:
    """Return the authoritative live consumer file for Teams AWS creation.

    Prefer the resolved environment main.tf when present.  The context pack can
    intentionally carry bounded snippets, so fetch the complete file from the
    same live GitHub branch before materializing a write.
    """
    context_pack = dict(context_pack or {})
    repo_profile = dict(context_pack.get("repo_profile") or {})
    branch = str(repo_profile.get("source_branch") or "").strip() or _aws_module_catalog_branch()
    environment_path = str(environment_path or repo_profile.get("target_environment_path") or "").strip().strip("/")
    target_files = [str(path or "").strip() for path in repo_profile.get("target_environment_files") or [] if str(path or "").strip()]

    main_path = f"{environment_path}/main.tf" if environment_path else ""
    candidates = []
    if main_path and main_path in target_files:
        candidates.append(main_path)
    for path in target_files:
        if path.endswith(".tf") and path not in candidates:
            candidates.append(path)

    # Teams AWS creation has one deterministic consumer target: the target
    # environment's main.tf whenever that file exists. Repository placement is
    # not a user decision and must never fall back to backend.tf/variables.tf or
    # an agent-invented resource file merely because main.tf has no module block
    # yet. The backend owns preservation and appends the generated sibling block
    # to the complete live main.tf content.
    if main_path:
        try:
            main_content = github_get_file_content(
                "aws",
                main_path,
                branch,
                repo_target="tf-devops",
                workflow="aws_module_creation",
            )
        except Exception as exc:
            LOGGER.warning("Could not read complete Teams AWS main.tf %s@%s: %s", main_path, branch, exc)
            main_content = None
        if main_content is not None:
            return main_path, str(main_content).replace("\r\n", "\n")

    for path in candidates:
        try:
            content = github_get_file_content(
                "aws",
                path,
                branch,
                repo_target="tf-devops",
                workflow="aws_module_creation",
            ) or ""
        except Exception:
            continue
        if content and re.search(r'(?m)^\s*module\s+"[^"]+"\s*\{', content):
            return path, content.replace("\r\n", "\n")

    if main_path:
        try:
            content = github_get_file_content(
                "aws",
                main_path,
                branch,
                repo_target="tf-devops",
                workflow="aws_module_creation",
            ) or ""
        except Exception:
            content = ""
        if content:
            return main_path, content.replace("\r\n", "\n")
    return "", ""


def _teams_aws_extract_new_consumer_block(files: list[dict], module_path: str) -> tuple[str, str]:
    """Find only the newly generated consumer block for the proposed module."""
    module_path = _sanitize_aws_module_rel_path(module_path)
    for file_data in files or []:
        if not isinstance(file_data, dict):
            continue
        filename = normalize_tf_relative_path(file_data.get("filename") or file_data.get("path") or "")
        if not filename.startswith("terraform/") or filename.startswith(f"{AWS_MODULES_ROOT}/"):
            continue
        for block in _extract_top_level_tf_blocks(str(file_data.get("content") or "")):
            header = str(block.get("header") or "")
            if not re.match(r'^module\s+"[^"]+"$', header):
                continue
            block_text = str(block.get("block") or "")
            source_match = re.search(r'(?m)^\s*source\s*=\s*"([^"]+)"', block_text)
            if source_match and normalize_aws_module_source_path(source_match.group(1)) == module_path:
                return filename, block_text.strip()
    return "", ""


def _teams_aws_materialize_repo_aligned_consumer_stage1(
    agent_result: dict,
    proposed_module_path: str,
    environment_path: str,
    context_pack: dict,
) -> dict:
    """Materialize the Teams AWS consumer against the complete live repo file.

    Foundry only needs to generate the new sibling module block.  The backend
    owns preservation: it fetches the complete current consumer file and appends
    that block, so unrelated existing consumers can never be truncated or
    rejected merely because their sources are external/non-local.
    """
    updated = dict(agent_result or {})
    files = [dict(item) for item in updated.get("files") or [] if isinstance(item, dict)]
    module_path = _sanitize_aws_module_rel_path(proposed_module_path)
    generated_consumer_path, new_block = _teams_aws_extract_new_consumer_block(files, module_path)
    if not new_block:
        raise ValueError(f"No consumer module block references the new module {AWS_MODULES_ROOT}/{module_path}.")

    live_path, live_content = _teams_aws_live_consumer_content_from_context(context_pack, environment_path)
    main_target_path = f"{str(environment_path or '').strip().strip('/')}/main.tf"

    # Final backend guard: a newly-created AWS resource consumer is committed
    # only to the resolved environment main.tf. Do not keep the agent's
    # temporary per-resource consumer filename (for example ec2_instance_minidev.tf).
    # If live main.tf exists, preserve it and append the new module block. If it
    # is unexpectedly unavailable, fail instead of silently creating a separate
    # consumer file and changing repository layout.
    target_path = main_target_path
    if live_path != main_target_path:
        branch = str(((context_pack.get("repo_profile") or {}).get("source_branch")) or "").strip() or _aws_module_catalog_branch()
        try:
            fetched_main = github_get_file_content(
                "aws",
                main_target_path,
                branch,
                repo_target="tf-devops",
                workflow="aws_module_creation",
            )
        except Exception:
            fetched_main = None
        if fetched_main is not None:
            live_content = str(fetched_main).replace("\r\n", "\n")
            live_path = main_target_path

    if live_path != main_target_path:
        raise ValueError(
            f"AWS new-resource consumer target must be the existing environment main.tf: {main_target_path}."
        )

    expected_source = build_aws_local_module_source(module_path, target_path.rsplit("/", 1)[0])
    source_match = re.search(r'(?m)^\s*source\s*=\s*"([^"]+)"', new_block)
    if not source_match or source_match.group(1).replace("\\", "/").rstrip("/") != expected_source:
        raise ValueError(
            f'Generated consumer for {AWS_MODULES_ROOT}/{module_path} must use source = "{expected_source}".'
        )

    if live_content:
        # Never duplicate the proposed module if a retry already materialized it.
        for block in _extract_top_level_tf_blocks(live_content):
            block_text = str(block.get("block") or "")
            existing_source = re.search(r'(?m)^\s*source\s*=\s*"([^"]+)"', block_text)
            if existing_source and normalize_aws_module_source_path(existing_source.group(1)) == module_path:
                raise ValueError(
                    f"The target environment already contains a consumer for {AWS_MODULES_ROOT}/{module_path}; refusing to duplicate it."
                )
        materialized = live_content.rstrip() + "\n\n" + new_block.rstrip() + "\n"
    else:
        materialized = new_block.rstrip() + "\n"

    module_files = []
    for item in files:
        filename = normalize_tf_relative_path(item.get("filename") or item.get("path") or "")
        if filename.startswith(f"{AWS_MODULES_ROOT}/{module_path}/"):
            module_files.append(item)
    module_files.append({"filename": target_path, "content": materialized})
    updated["files"] = module_files
    return updated
_teams_aws_materialize_repo_aligned_consumer = _teams_aws_materialize_repo_aligned_consumer_stage1


def _teams_validate_aws_module_creation_payload(
    cleaned_files: list[dict],
    proposed_module_path: str,
    environment_path: str,
    user_prompt: str = "",
) -> list[dict]:
    """Teams-only AWS creation validator scoped to the new module and consumer.

    The generic validator scans every module block in the complete consumer
    file.  That is incorrect for Teams full-file materialization because
    unrelated pre-existing consumers may legitimately use external sources.
    Validate only the newly created module reference while preserving all other
    existing blocks untouched.
    """
    module_path = _sanitize_aws_module_rel_path(proposed_module_path)
    created_module_paths = _aws_created_module_paths_from_files(cleaned_files)
    if created_module_paths != {module_path}:
        raise ValueError(
            f"aws_module_creation must create exactly {AWS_MODULES_ROOT}/{module_path}; detected {sorted(created_module_paths)}."
        )
    if github_verified_aws_module_exists(module_path):
        raise ValueError(f"AWS module {AWS_MODULES_ROOT}/{module_path} already exists. Use aws_module_consumer instead.")

    validate_aws_module_variable_file_convention(cleaned_files, module_path, user_prompt=user_prompt)
    expected_env = str(environment_path or "").strip().strip("/") + "/"
    consumer_files = [
        item for item in _aws_consumer_files_from_agent_result(cleaned_files)
        if normalize_tf_relative_path(item.get("filename") or "").startswith(expected_env)
    ]
    if not consumer_files:
        raise ValueError(f"aws_module_creation must materialize a consumer file under {environment_path}.")

    matches = []
    for file_data in consumer_files:
        filename = normalize_tf_relative_path(file_data.get("filename") or "")
        folder = filename.rsplit("/", 1)[0]
        expected_source = build_aws_local_module_source(module_path, folder)
        for ref in _extract_aws_module_source_refs_from_text(file_data.get("content") or ""):
            if ref.get("module_path") == module_path:
                if str(ref.get("source") or "").replace("\\", "/").rstrip("/") != expected_source:
                    raise ValueError(
                        f'{filename}: new module consumer must use source = "{expected_source}", not "{ref.get("source") or ""}".'
                    )
                matches.append((filename, ref.get("module_name") or ""))
    if len(matches) != 1:
        raise ValueError(
            f"aws_module_creation must contain exactly one consumer reference to {AWS_MODULES_ROOT}/{module_path}; detected {len(matches)}."
        )

    normalized, variable_issues = normalize_generated_module_variable_files(
        cleaned_files, "aws_module_creation", user_prompt=user_prompt
    )
    if variable_issues:
        raise ModuleVariableValuesRequired(normalized, variable_issues, workflow="aws_module_creation")
    return normalized


def _teams_aws_validate_new_module_artifacts(agent_result: dict, proposed_module_path: str) -> None:
    module_path = _sanitize_aws_module_rel_path(proposed_module_path)
    prefix = f"{AWS_MODULES_ROOT}/{module_path}/"
    filenames = [
        normalize_tf_relative_path(item.get("filename") or item.get("path") or "")
        for item in agent_result.get("files") or []
        if isinstance(item, dict)
    ]
    module_files = [path for path in filenames if path.startswith(prefix) and path.endswith(".tf")]
    if not module_files:
        raise ValueError(f"No Terraform implementation files were generated under {prefix}.")
    if not any(path.rsplit("/", 1)[-1] == "outputs.tf" for path in module_files):
        raise ValueError(f"The new module must include {prefix}outputs.tf.")
    if not any(path.startswith("terraform/") and not path.startswith(f"{AWS_MODULES_ROOT}/") for path in filenames):
        raise ValueError("The new AWS module response must include a consumer .tf file outside terraform/modules.")


def _teams_parse_aws_new_module_reply(
    agent_reply: str,
    original_prompt: str,
    proposed_module_path: str,
    environment_path: str,
    foundry_conversation_id: str,
    context_pack: dict | None = None,
) -> dict:
    payload = extract_json_from_text(agent_reply)
    if not isinstance(payload, dict):
        try:
            payload = json.loads(str(agent_reply or ""))
        except Exception as exc:
            raise ValueError(f"The agent did not return a valid JSON object: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("The agent did not return a JSON object.")

    payload.setdefault("mode", "infra")
    payload.setdefault("cloud", "aws")
    payload.setdefault("workflow", "aws_module_creation")
    payload.setdefault("repo_target", "tf-devops")
    payload.setdefault("title", "[AWS] Create new AWS module and consumer reference")
    payload.setdefault("summary", "Create a reusable AWS module and consume it from the selected environment.")
    payload.setdefault("analysis", "")
    payload.setdefault("source_paths_used", [])
    payload.setdefault("user_fillable", [])
    payload.setdefault("questions", [])
    payload.setdefault("validation_commands", ["terraform fmt -check -recursive", "terraform validate"])
    payload.setdefault("branch_name", _teams_suggested_branch_name(payload, original_prompt, foundry_conversation_id or "teams"))

    normalized_files: list[dict] = []
    for item in payload.get("files") or []:
        if not isinstance(item, dict):
            continue
        filename = str(item.get("filename") or item.get("path") or "").strip()
        content = item.get("content")
        if filename and isinstance(content, str) and content.strip():
            normalized_files.append({"filename": filename, "content": content.replace("\r\n", "\n").rstrip() + "\n"})
    payload["files"] = normalized_files
    if not normalized_files:
        raise ValueError("The agent returned no materialized Terraform files for the new AWS module.")

    parsed = parse_agent_output(json.dumps(payload))
    for key in (
        "analysis",
        "source_paths_used",
        "user_fillable",
        "questions",
        "validation_commands",
        "branch_name",
    ):
        parsed[key] = payload.get(key)

    parsed["files"] = _teams_validate_aws_module_creation_payload(
        parsed.get("files") or [],
        proposed_module_path,
        environment_path,
        user_prompt=original_prompt,
    )
    parsed = _teams_aws_insert_missing_consumer_inputs(
        parsed,
        proposed_module_path,
        original_prompt,
    )
    parsed = _teams_aws_materialize_repo_aligned_consumer(
        parsed,
        proposed_module_path,
        environment_path,
        dict(context_pack or {}),
    )
    parsed["files"] = _teams_validate_aws_module_creation_payload(
        parsed.get("files") or [],
        proposed_module_path,
        environment_path,
        user_prompt=original_prompt,
    )
    _teams_aws_validate_new_module_artifacts(parsed, proposed_module_path)
    parsed["cloud"] = "aws"
    parsed["workflow"] = "aws_module_creation"
    parsed["repo_target"] = "tf-devops"
    parsed["state_bucket"] = state_bucket_for_target("aws", "tf-devops", "aws_module_creation")
    parsed["user_prompt"] = original_prompt
    parsed["_foundry_conversation_id"] = foundry_conversation_id

    analysis_lines = [line.strip() for line in str(parsed.get("analysis") or "").splitlines() if line.strip()]
    context_pack = dict(context_pack or _teams_aws_new_module_context_pack(
        original_prompt,
        proposed_module_path,
        environment_path,
        discovery={},
    ))
    backend_lines = [
        f"Repository: `{context_pack['repo_profile']['repo_full_name']}` on `{context_pack['repo_profile']['source_branch']}`.",
        f"Verified absence: no semantically matching module was found under `{AWS_MODULES_ROOT}` for `{infer_aws_requested_resource_hint(original_prompt)}`.",
        f"Module created: `{AWS_MODULES_ROOT}/{_sanitize_aws_module_rel_path(proposed_module_path)}` using live tf-devops module-layout evidence.",
        f"Consumer placement: `{environment_path}` with source `{build_aws_local_module_source(proposed_module_path, environment_path)}`.",
        f"Value strategy: explicit prompt values, repository examples/defaults, then tracked `__FILL__` tokens ({len(parsed.get('user_fillable') or [])} remaining).",
    ]
    merged_analysis = backend_lines
    for line in analysis_lines:
        if line not in merged_analysis and len(merged_analysis) < 10:
            merged_analysis.append(line)
    parsed["analysis"] = "\n".join(merged_analysis[:10])

    evidence_paths = [str(item.get("path") or "") for item in context_pack.get("evidence") or [] if item.get("path")]
    source_paths = [str(path) for path in parsed.get("source_paths_used") or [] if str(path)]
    parsed["source_paths_used"] = list(dict.fromkeys(source_paths + evidence_paths))[:20]
    return parsed


def _teams_generate_aws_new_module_with_context(
    conversation_id: str,
    original_prompt: str,
    proposed_module_path: str,
    environment_path: str,
    discovery: dict | None = None,
) -> dict:
    agent_input = build_agent_input_for_aws_module_creation(
        original_prompt,
        proposed_module_path,
        environment_path,
        discovery=discovery,
    )
    try:
        generation_envelope = json.loads(agent_input)
        context_pack = dict(generation_envelope.get("context_pack") or {})
    except Exception:
        context_pack = _teams_aws_new_module_context_pack(
            original_prompt,
            proposed_module_path,
            environment_path,
            discovery=discovery,
        )
    foundry_conversation_id, agent_reply = call_agent(conversation_id, agent_input)
    try:
        return _teams_parse_aws_new_module_reply(
            agent_reply,
            original_prompt,
            proposed_module_path,
            environment_path,
            foundry_conversation_id,
            context_pack=context_pack,
        )
    except Exception as first_error:
        repair_request = {
            "task": "Repair the Teams AWS new-module generation and return all required Terraform files now.",
            "channel": "teams",
            "user_request": original_prompt,
            "backend_validation_error": str(first_error),
            "proposed_module_path": proposed_module_path,
            "environment_path": environment_path,
            "context_pack": context_pack,
            "previous_agent_reply": agent_reply,
            "required_corrections": [
                "Return one valid JSON object only.",
                "Create the complete reusable module implementation, exactly one repository-convention variable file, outputs.tf, and the target-environment consumer file now; do not ask for permission or confirmation.",
                f"When `{environment_path}/main.tf` exists in context_pack evidence, use that exact file for the consumer and preserve its complete existing content.",
                "Use the exact local relative module source supplied by the backend.",
                "Keep unresolved module variables required and put valid __FILL__ values in the consumer with matching user_fillable entries.",
                "Use complete terraform-fmt-compatible file contents and no TODO/scaffold placeholders.",
                "Include mode=infra, cloud=aws, workflow=aws_module_creation and repo_target=tf-devops.",
            ],
        }
        foundry_conversation_id, repaired_reply = call_agent(
            foundry_conversation_id,
            json.dumps(repair_request, indent=2),
        )
        try:
            return _teams_parse_aws_new_module_reply(
                repaired_reply,
                original_prompt,
                proposed_module_path,
                environment_path,
                foundry_conversation_id,
                context_pack=context_pack,
            )
        except Exception as second_error:
            raise ValueError(
                "Teams could not produce a valid repository-aligned AWS module and consumer after one repair. "
                f"Initial validation: {first_error}. Repair validation: {second_error}"
            ) from second_error


def _teams_auto_accept_aws_module_creation(data: dict, preview: dict, status_code: int):
    """Generate and push a missing AWS module plus consumer without a dead end."""
    if status_code < 400:
        return preview, status_code
    if not isinstance(preview, dict):
        return preview, status_code
    decision_state = str(preview.get("decision_state") or "").strip()
    router_workflow = str((preview.get("router") or {}).get("workflow") or "").strip()
    if (
        decision_state != "aws_module_creation_confirmation"
        and router_workflow != "aws_module_creation_confirmation"
    ):
        return preview, status_code

    original_prompt = str(
        (data or {}).get("original_prompt")
        or (data or {}).get("prompt")
        or preview.get("request_prompt")
        or ""
    ).strip()
    discovery = dict(preview.get("aws_module_discovery") or {})
    proposed_module_path = _sanitize_aws_module_rel_path(
        preview.get("proposed_module_path")
        or infer_new_aws_module_path(original_prompt, discovery)
    )
    environment_path = str(
        preview.get("environment_path")
        or "terraform/dev_aws/minidev"
    ).strip().strip("/")

    candidate_conversation_id = str(
        preview.get("thread_id")
        or (data or {}).get("thread_id")
        or ""
    ).strip()
    if candidate_conversation_id.startswith("teams-"):
        candidate_conversation_id = ""

    try:
        agent_result = _teams_generate_aws_new_module_with_context(
            candidate_conversation_id,
            original_prompt,
            proposed_module_path,
            environment_path,
            discovery=discovery,
        )
    except Exception as exc:
        LOGGER.exception("Teams AWS missing-module generation failed", exc_info=exc)
        failed = dict(preview)
        failed.update({
            "ok": False,
            "mode": "clarification",
            "reply": (
                "Terrabot verified that no matching AWS module exists, but repository-aligned "
                f"module and consumer generation failed validation: {exc}"
            ),
            "analysis": (
                f"Repository: `{GITHUB_OWNER}/{GITHUB_AWS_REPO}`.\n"
                f"Module catalog checked: `{AWS_MODULES_ROOT}`.\n"
                f"Proposed module: `{AWS_MODULES_ROOT}/{proposed_module_path}`.\n"
                "No branch was written because the generated module did not pass the backend contract."
            ),
        })
        return failed, 500

    workflow_thread_id = str(
        agent_result.pop("_foundry_conversation_id", "")
        or candidate_conversation_id
        or _teams_workflow_thread_id(data, fallback=preview.get("thread_id") or "")
    ).strip()
    ticket_number = str(preview.get("ticket_number") or preview.get("jira_ticket") or "").strip()
    ticket_link = str(preview.get("ticket_link") or (data or {}).get("ticket_link") or "").strip()
    ticket_title = str(preview.get("ticket_title") or (data or {}).get("ticket_title") or "").strip()
    conversation_label = str(
        preview.get("conversation_label")
        or build_enhanced_conversation_label(ticket_number, ticket_title, workflow_thread_id)
    )

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
        "reply": "The missing AWS module and its consumer were generated from live tf-devops evidence and are ready for branch creation.",
        "thread_id": workflow_thread_id,
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
        "branch_name": agent_result.get("branch_name") or "",
        "summary": agent_result.get("summary") or "Created a reusable AWS module and target-environment consumer.",
        "analysis": agent_result.get("analysis") or "",
        "source_paths_used": agent_result.get("source_paths_used") or [],
        "user_fillable": agent_result.get("user_fillable") or [],
        "questions": agent_result.get("questions") or [],
        "validation_commands": agent_result.get("validation_commands") or ["terraform fmt -check -recursive", "terraform validate"],
        "files": [item.get("filename") for item in agent_result.get("files") or [] if item.get("filename")],
        "state_bucket": agent_result.get("state_bucket") or state_bucket_for_target("aws", "tf-devops", "aws_module_creation"),
        "thread_prs": build_thread_prs_payload(workflow_thread_id),
    }

    commit_data = dict(data or {})
    commit_data["thread_id"] = workflow_thread_id
    return _teams_auto_commit_preview(commit_data, auto_preview, 200)
# =============================================================================
# Teams multi-cloud branch/PR continuity and strict natural-language guard
# =============================================================================
# This final addendum is intentionally Teams-scoped. It preserves all existing
# VS Code entry points and infrastructure workflows while fixing stale request
# replay, cross-cloud branch isolation, and parallel AWS/Azure PR continuity.

_TEAMS_MULTICLOUD_PREVIOUS_HANDLE_CHAT = _handle_teams_chat_request_targeted
_TEAMS_MULTICLOUD_PREVIOUS_CALL_AGENT = _call_agent_base

def _teams_is_explicit_infra_request(prompt: str) -> bool:
    """Compatibility wrapper backed only by Foundry semantic classification."""
    return _teams_foundry_classify_request(prompt) == "infra"


def _teams_cloud_bucket_states(thread_id: str, cloud: str) -> list[dict]:
    cloud = safe_normalize_cloud(cloud) or ""
    if not thread_id or not cloud:
        return []
    try:
        restore_teams_workflow_state(thread_id)
    except Exception:
        pass
    states = []
    for bucket, value in (THREAD_PR_STATE.get(thread_id) or {}).items():
        if bucket == "_meta" or not isinstance(value, dict):
            continue
        if safe_normalize_cloud(str(value.get("cloud") or "")) == cloud:
            item = dict(value)
            item.setdefault("state_bucket", bucket)
            states.append(item)
    states.sort(
        key=lambda item: (
            0 if item.get("has_open_pr") else 1,
            -int(item.get("cycle") or 0),
            str(item.get("branch") or ""),
        )
    )
    return states


def _teams_cloud_session(state: dict, cloud: str) -> dict:
    sessions = state.get("cloud_sessions") or {}
    if not isinstance(sessions, dict):
        return {}
    value = sessions.get(cloud) or {}
    return dict(value) if isinstance(value, dict) else {}


def _teams_best_cloud_state(state: dict, cloud: str) -> dict:
    session = _teams_cloud_session(state, cloud)
    candidate_threads = []
    for value in (
        session.get("thread_id"),
        state.get("workflow_thread_id"),
        state.get("foundry_conversation_id"),
    ):
        value = str(value or "").strip()
        if value and value not in candidate_threads:
            candidate_threads.append(value)
    for thread_id in candidate_threads:
        matches = _teams_cloud_bucket_states(thread_id, cloud)
        if matches:
            selected = matches[0]
            selected["thread_id"] = thread_id
            return selected
    if session.get("branch"):
        return dict(session)

    # Durable Teams UI state predates cloud_sessions in some conversations.
    # If that top-level branch belongs to the requested cloud, treat it as the
    # reusable branch so the branch decision is asked BEFORE repository target
    # disambiguation. Without this fallback, an old-but-valid branch can be
    # invisible until after the target picker, producing the options -> branch
    # -> options loop.
    state_cloud = safe_normalize_cloud(str(state.get("cloud") or "")) or ""
    state_branch = str(state.get("branch") or "").strip()
    if state_branch and state_cloud == cloud:
        return {
            "thread_id": str(
                state.get("workflow_thread_id")
                or state.get("foundry_conversation_id")
                or ""
            ).strip(),
            "branch": state_branch,
            "branch_url": state.get("branch_url") or "",
            "compare_url": state.get("compare_url") or "",
            "pr_url": state.get("pr_url") or "",
            "pr_number": state.get("pr_number"),
            "has_open_pr": bool(state.get("pr_url") or state.get("pr_number")),
            "repo_target": state.get("repo_target") or "",
            "workflow": state.get("workflow") or "",
            "base_branch": state.get("base_branch") or "",
        }
    return {}


def _teams_git_resolution_analysis(
    cloud: str,
    branch_state: dict,
    reuse_branch: bool,
    force_new_branch: bool,
    previous_cloud: str = "",
) -> str:
    cloud_label = (cloud or "unknown").upper()
    repo = GITHUB_AWS_REPO if cloud == "aws" else GITHUB_AZURE_REPO if cloud == "azure" else ""
    lines = [
        f"Git repository resolution: `{GITHUB_OWNER}/{repo}` for {cloud_label}.",
    ]
    if previous_cloud and previous_cloud != cloud:
        lines.append(
            f"Cloud switch detected: {previous_cloud.upper()} -> {cloud_label}; the previous cloud branch/PR was preserved and not modified."
        )
    if reuse_branch:
        lines.append(
            f"Branch resolution: reuse existing {cloud_label} branch `{branch_state.get('branch') or ''}` and generate against its latest remote contents."
        )
        if branch_state.get("has_open_pr") or branch_state.get("pr_url"):
            lines.append(
                f"PR resolution: push a new commit to the branch backing the existing {cloud_label} PR and refresh that PR."
            )
    elif force_new_branch:
        lines.append(
            f"Branch resolution: create a new {cloud_label} branch from the latest remote base branch; no other cloud branch is reused."
        )
    else:
        lines.append("Branch resolution: no Git branch mutation was requested for this message.")
    return "\n".join(lines)


def _teams_foundry_classify_request(prompt: str) -> str:
    """Classify one ordinary Teams message using the configured Foundry agent.

    No Python keyword/resource/environment scoring is used. The call is fresh
    so previous Terraform turns cannot bias classification. Repository-oriented
    verbs with approximate resource wording (for example "disable patch setup
    from minidev") must remain infrastructure because the agent can resolve the
    concrete target later from live GitHub evidence.
    """
    text = str(prompt or "").strip()
    if not text:
        return "chat"
    request = {
        "task": "CLASSIFY CURRENT TEAMS USER INTENT ONLY. Return JSON only.",
        "user_request": text,
        "allowed_intents": ["chat", "repo_qna", "infra"],
        "required_output": {"intent": "chat|repo_qna|infra", "reason": "one short sentence"},
        "rules": [
            "Use the Terrabot system instructions as the authority for intent.",
            "Infrastructure means the user is asking to create, change, enable, disable, remove, fix, or otherwise mutate infrastructure/repository Terraform.",
            "Do not require exact product terminology. Approximate or colloquial resource phrases are still infrastructure when an infrastructure action is clear; repository discovery resolves the exact target later.",
            "A named environment or repository scope plus an action such as enable/disable/change is strong infrastructure intent even if the resource phrase is vague.",
            "Chat and repository Q&A must not be converted to infrastructure merely because prior thread state exists.",
            "This is classification only: do not generate Terraform, files, questions, or implementation plans.",
        ],
    }
    try:
        _thread, reply = call_agent(None, json.dumps(request, separators=(",", ":")))
        parsed = extract_json_safely(reply)
        intent = str(parsed.get("intent") or "").strip().lower()
        if intent in {"chat", "repo_qna", "infra"}:
            LOGGER.info("Foundry Teams intent: %s", intent)
            return intent
        LOGGER.warning("Foundry Teams intent response was not recognized; delegating message without backend intent forcing.")
    except Exception as exc:
        LOGGER.warning("Foundry Teams intent classification failed; delegating message without backend intent forcing: %s", exc)
    return "unknown"


def _teams_message_is_protocol_control(request_data: dict, state: dict, prompt: str) -> bool:
    """Return True only for deterministic non-semantic workflow control replies."""
    if str(request_data.get("action") or "").strip():
        return True
    if any(_teams_truthy(request_data.get(key)) for key in (
        "pending_target_selection_reply",
        "pending_branch_choice_reply",
        "pending_branch_choice_resolved",
        "pending_target_selection_resolved",
    )):
        return True
    stage = str((state or {}).get("stage") or "").strip()
    normalized = normalize_yes_no_reply(prompt)
    if stage == "awaiting_branch_reuse_decision" and normalized in AFFIRMATIVE_REPLIES | NEGATIVE_REPLIES:
        return True
    if stage in {"awaiting_pr_decision", "awaiting_pr_confirmation", "awaiting_branch_commit", "infra_preview"}:
        if normalized in AFFIRMATIVE_REPLIES | NEGATIVE_REPLIES or _teams_prompt_requests_pr(prompt):
            return True
    if stage == "awaiting_jira" and (is_valid_jira_ticket_link(prompt) or normalized in NEGATIVE_REPLIES):
        return True
    if stage == "infra_modification_target_selection":
        if re.fullmatch(r"\d+", normalized or "") or str(prompt or "").strip().endswith((".tf", ".tfvars")):
            return True
    return False


def _teams_chat_repo_targets(cloud: str) -> dict:
    """Map a resolved cloud to its GitHub owner/repo/branch for chat grounding."""
    cloud = str(cloud or "").strip().lower()
    if cloud == "aws" and GITHUB_AWS_REPO:
        return {"owner": GITHUB_OWNER, "repo": GITHUB_AWS_REPO, "branch": GITHUB_AWS_BASE_BRANCH}
    if cloud == "azure" and GITHUB_AZURE_REPO:
        return {"owner": GITHUB_OWNER, "repo": GITHUB_AZURE_REPO, "branch": GITHUB_AZURE_BASE_BRANCH}
    return {}


def _teams_build_chat_grounding_context(
    prompt: str,
    teams_conversation_id: str,
    cloud_hint: str,
    repo_target_hint: str,
) -> dict:
    """Gather live-repository, pull-request, and cached-memory context for a
    plain-language question so Teams chat can answer infrastructure
    questions the same way the VS Code extension answers questions about the
    open workspace (feature: repo-aware Q&A), grounded in already-raised
    pull requests (feature: PR-aware answers), and long-term agent memory.

    Best effort throughout: any failure yields an empty section rather than
    blocking the chat reply.
    """
    cloud = safe_normalize_cloud(cloud_hint) or safe_normalize_cloud(infer_cloud_from_prompt(prompt)) or ""
    repo_info = _teams_chat_repo_targets(cloud)

    repo_paths: List[str] = []
    repo_context_block = ""
    pr_matches: List[dict] = []
    pr_context_block = ""

    if repo_info:
        try:
            repo_result = repo_chat_context.build_live_repo_chat_context(
                prompt,
                repo_info["owner"],
                repo_info["repo"],
                branch=repo_info["branch"],
                token=GITHUB_TOKEN,
            )
            repo_paths = repo_result.get("paths") or []
            repo_context_block = repo_result.get("context_block") or ""
        except Exception:
            LOGGER.debug("Skipping live repo chat context", exc_info=True)

        try:
            pr_result = agent_pr_context.build_pr_context_block(
                prompt,
                repo_info["owner"],
                repo_info["repo"],
                token=GITHUB_TOKEN,
                cloud=cloud,
            )
            pr_matches = pr_result.get("matches") or []
            pr_context_block = pr_result.get("context_block") or ""
        except Exception:
            LOGGER.debug("Skipping pull request chat context", exc_info=True)
    else:
        # Cloud/repo could not be resolved from the question. Still check
        # both configured repositories for a relevant open pull request so a
        # cloud-agnostic infra question can find matching in-flight work.
        try:
            pr_result = agent_pr_context.build_multi_repo_pr_context_block(
                prompt,
                GITHUB_OWNER,
                {"aws": GITHUB_AWS_REPO, "azure": GITHUB_AZURE_REPO},
                token=GITHUB_TOKEN,
            )
            pr_matches = pr_result.get("matches") or []
            pr_context_block = pr_result.get("context_block") or ""
        except Exception:
            LOGGER.debug("Skipping multi-repo pull request chat context", exc_info=True)

    shared_context_blocks: list[str] = []
    context_targets = []
    if repo_info:
        context_targets.append(repo_info)
    else:
        for configured_repo, configured_branch in (
            (GITHUB_AWS_REPO, GITHUB_AWS_BASE_BRANCH),
            (GITHUB_AZURE_REPO, GITHUB_AZURE_BASE_BRANCH),
            (GITHUB_VENA_REPO, GITHUB_VENA_BASE_BRANCH),
        ):
            if configured_repo:
                context_targets.append({
                    "owner": GITHUB_OWNER,
                    "repo": configured_repo,
                    "branch": configured_branch,
                })

    for target in context_targets:
        owner = str(target.get("owner") or "").strip()
        repo = str(target.get("repo") or "").strip()
        branch = str(target.get("branch") or "").strip()
        if not owner or not repo:
            continue
        _branch, current_sha = _repository_context_branch_and_sha(owner, repo, branch)
        try:
            search_result = shared_repository_context.search_repository_context(
                repo_owner=owner,
                repo_name=repo,
                query=prompt,
                current_commit_sha=current_sha,
                top_k=5,
            )
            block = shared_repository_context.format_repository_context_for_agent(search_result)
            if block:
                shared_context_blocks.append(block)
        except Exception as exc:
            LOGGER.warning(
                "[TerrabotDiag] event=repository_context_chat_search_failed repo=%s/%s error=%s",
                owner,
                repo,
                exc,
            )

    return {
        "cloud": cloud,
        "repo_paths": repo_paths,
        "repo_context_block": repo_context_block,
        "pr_matches": pr_matches,
        "pr_context_block": pr_context_block,
        "shared_repository_context": "\n\n".join(shared_context_blocks),
    }


def _teams_plain_chat_reply(
    prompt: str,
    teams_conversation_id: str = "",
    cloud_hint: str = "",
    repo_target_hint: str = "",
    requester: str = "",
) -> tuple[dict, int]:
    """Answer non-infra natural language without entering generation code.

    Ordinary questions ("what environments does this module support?", "has
    anyone raised a PR for the checkout storage account yet?") are answered
    using live repository evidence, already-raised pull requests, and shared
    repository context — the same repository-aware ability VS Code already has for
    the open workspace — while still refusing to generate Terraform, files,
    branches, commits, or pull requests from this path.
    """
    normalized = normalize_yes_no_reply(prompt)
    greetings = {"hi", "hello", "hey", "good morning", "good afternoon", "good evening"}
    grounding: dict = {}
    if normalized in greetings:
        reply = "Hello. Send an infrastructure change when you are ready, or ask a repository/workflow question."
    else:
        grounding = _teams_build_chat_grounding_context(
            prompt, teams_conversation_id, cloud_hint, repo_target_hint
        )
        chat_input = json.dumps({
            "task": "Answer a Microsoft Teams user conversationally without generating infrastructure.",
            "user_message": prompt,
            "rules": [
                "Return plain text only.",
                "Do not return JSON, Terraform, files, branches, commits, or pull requests.",
                "Do not reuse or summarize a previous infrastructure request unless the user explicitly asks about it.",
                "If the message is unclear, ask one concise clarifying question.",
                "When repository_context, pull_request_context, or shared_repository_context is provided below, use it to answer repository questions accurately. Live repository_context is current evidence. shared_repository_context contains durable repository knowledge shared across users, but any stale/conflicted item must be revalidated against live evidence before treating it as current truth.",
            ],
            "repository_context": grounding.get("repo_context_block") or "",
            "pull_request_context": grounding.get("pr_context_block") or "",
            "shared_repository_context": grounding.get("shared_repository_context") or "",
            "repository_context_tools": shared_repository_context.FOUNDRY_REPOSITORY_CONTEXT_TOOL_SCHEMAS,
        })
        try:
            _thread, candidate = _TEAMS_MULTICLOUD_PREVIOUS_CALL_AGENT(None, chat_input)
            reply = str(candidate or "").strip()
            if not reply or agent_reply_looks_like_infra_json(reply) or looks_like_infra_payload(reply):
                reply = "I did not detect a new infrastructure change request. Please state the change explicitly when you want Terraform generated."
        except Exception:
            reply = "I did not detect a new infrastructure change request. Please state the change explicitly when you want Terraform generated."

    return {"ok": True, "mode": "chat", "reply": reply}, 200


def _teams_compact_agent_input(agent_input: str, max_chars: int = 90000) -> str:
    """Bound Teams Foundry input while preserving live-repository evidence.

    Large repositories and long-lived conversations can exceed the model context
    window. This compactor keeps routing metadata, the current request, file
    paths, and the most relevant Terraform content while removing duplicate or
    low-value bulk. It is Teams-only and does not alter VS Code requests.
    """
    raw = str(agent_input or "")
    if len(raw) <= max_chars:
        return raw
    try:
        payload = json.loads(raw)
    except Exception:
        return raw[:max_chars]

    prompt = str(
        payload.get("user_request")
        or payload.get("prompt")
        or payload.get("original_prompt")
        or ""
    ).lower()
    prompt_tokens = {
        token for token in re.findall(r"[a-z0-9_/-]{3,}", prompt)
        if token not in {"create", "update", "modify", "using", "existing", "terraform"}
    }

    def file_score(item: dict) -> tuple[int, int]:
        path = str(item.get("path") or item.get("filename") or "").lower()
        content = str(item.get("content") or "")
        score = sum(20 for token in prompt_tokens if token in path)
        score += sum(3 for token in prompt_tokens if token in content.lower()[:12000])
        if path.endswith(("main.tf", "variables.tf", "vars.tf", ".tfvars")):
            score += 8
        if any(part in path for part in ("module", "modules", "env", "environment")):
            score += 4
        return score, -len(content)

    contexts = payload.get("existing_pr_context")
    if isinstance(contexts, list):
        for context in contexts:
            if not isinstance(context, dict):
                continue
            files = [item for item in context.get("existing_files") or [] if isinstance(item, dict)]
            files.sort(key=file_score, reverse=True)
            compact_files = []
            used = 0
            for item in files:
                path = str(item.get("path") or item.get("filename") or "")
                content = str(item.get("content") or "")
                # Full content is retained for the highest-value files; lower
                # ranked files become bounded evidence excerpts.
                # The top-ranked files are typically the selected write target
                # and its module — never clip a file the agent must reproduce.
                per_file_limit = 64000 if len(compact_files) < 2 else (24000 if len(compact_files) < 4 else 8000)
                bounded = content if len(content) <= per_file_limit else content[:per_file_limit] + "\n# [Terrabot context excerpt truncated]\n"
                candidate = {"path": path, "filename": item.get("filename") or path, "content": bounded}
                estimated = len(json.dumps(candidate, ensure_ascii=False))
                if compact_files and used + estimated > max_chars * 0.62:
                    break
                compact_files.append(candidate)
                used += estimated
            context["existing_files"] = compact_files
            context["context_compacted"] = True
            context["original_file_count"] = len(files)

    # Remove repeated verbose context blobs that are already represented by
    # existing_pr_context. Keep only compact metadata and confirmed selections.
    def _is_authoritative_context(item: dict) -> bool:
        return bool(
            item.get("selection_state") == "selected"
            or item.get("source") == "backend_existing_infra_code_match"
            or item.get("invocation_generation")
        )

    for key in ("retrieved_value_context", "retrieved_module_context"):
        values = payload.get(key)
        if isinstance(values, list):
            trimmed = []
            for item in values[:20]:
                if not isinstance(item, dict):
                    continue
                copy = dict(item)
                if _is_authoritative_context(copy):
                    # The user-confirmed write target is the agent's source of
                    # truth: its full live file content must reach the agent
                    # intact and structured. Truncating it (or str()-mangling
                    # matched_files) makes the agent ask the user for file
                    # contents the backend already read from GitHub. Bound
                    # only by a generous hard ceiling per file.
                    matched = copy.get("matched_files")
                    if isinstance(matched, list):
                        bounded_matched = []
                        for entry in matched:
                            if isinstance(entry, dict):
                                entry_copy = dict(entry)
                                entry_content = str(entry_copy.get("content") or "")
                                if len(entry_content) > 160_000:
                                    entry_copy["content"] = entry_content[:160_000]
                                bounded_matched.append(entry_copy)
                            else:
                                bounded_matched.append(entry)
                        copy["matched_files"] = bounded_matched
                    own_content = copy.get("content")
                    if isinstance(own_content, str) and len(own_content) > 160_000:
                        copy["content"] = own_content[:160_000]
                    for content_key in ("tf_files", "consumer_examples"):
                        if content_key in copy:
                            copy[content_key] = str(copy[content_key])[:6000]
                else:
                    for content_key in ("content", "matched_files", "tf_files", "consumer_examples"):
                        if content_key in copy:
                            copy[content_key] = str(copy[content_key])[:6000]
                trimmed.append(copy)
            payload[key] = trimmed

    compact = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(compact) > max_chars:
        # Over budget: keep the authoritative selected target whole and drop
        # auxiliary context items instead of blind-chopping the JSON tail.
        for key in ("retrieved_value_context", "retrieved_module_context"):
            values = payload.get(key)
            if isinstance(values, list):
                authoritative = [
                    item for item in values
                    if isinstance(item, dict) and _is_authoritative_context(item)
                ]
                payload[key] = authoritative or values[:3]
        compact = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(compact) <= max_chars:
        return compact
    # Never cut JSON text mid-object. If authoritative evidence alone exceeds
    # the preferred budget, send the valid payload intact and let call_agent
    # perform its context-length retry with a smaller budget.
    return compact


def _teams_is_context_length_error(exc: Exception) -> bool:
    text = str(exc or "").lower()
    return "context_length_exceeded" in text or "context window" in text or "maximum context" in text


def _teams_extract_files_searched(payload: dict) -> List[str]:
    """Best-effort extraction of the repository paths supplied to the agent.

    Looks across the shapes used by the various Teams/VS Code agent-input
    builders so the cached memory entry's "files_searched" is populated
    regardless of which workflow built the payload.
    """
    paths: List[str] = []

    def _collect(value: Any) -> None:
        if isinstance(value, dict):
            path = value.get("path") or value.get("filename") or value.get("input")
            if isinstance(path, str) and path.strip():
                if path.strip() not in paths:
                    paths.append(path.strip())
            for nested_key in ("existing_files", "matched_files"):
                nested = value.get(nested_key)
                if isinstance(nested, list):
                    for item in nested:
                        _collect(item)
        elif isinstance(value, list):
            for item in value:
                _collect(item)

    for key in ("existing_pr_context", "retrieved_value_context", "retrieved_module_context", "repository_files"):
        _collect(payload.get(key))
    return paths[:20]


def _repository_context_repo_identity(
    cloud: str,
    repo_target: str = "",
    workflow: str = "",
    explicit_repo: str = "",
) -> tuple[str, str]:
    """Resolve the repository identity used by shared context retrieval.

    This is repository routing only; it does not infer Terraform semantics.
    """
    owner = str(GITHUB_OWNER or "").strip()
    explicit = str(explicit_repo or "").strip().removesuffix(".git")
    if explicit and owner:
        return owner, explicit

    normalized_cloud = safe_normalize_cloud(cloud or "") or ""
    target = str(repo_target or "").strip().lower().replace("_", "-")
    workflow = str(workflow or "").strip().lower()
    if normalized_cloud == "aws":
        return owner, str(GITHUB_AWS_REPO or "").strip()
    if normalized_cloud == "azure":
        if target in {"vena-repos", "vena_repos"} or workflow == "azure_module_repo_creation":
            return owner, str(GITHUB_VENA_REPO or "").strip()
        return owner, str(GITHUB_AZURE_REPO or "").strip()
    return "", ""


def _repository_context_branch_and_sha(
    owner: str,
    repo: str,
    preferred_branch: str = "",
) -> tuple[str, str]:
    if not owner or not repo:
        return "", ""
    branch = str(preferred_branch or "").strip().replace("refs/heads/", "")
    try:
        metadata = github_get_repo(owner, repo) or {}
        branch = branch or str(metadata.get("default_branch") or "").strip()
    except Exception:
        pass
    if not branch:
        branch = "main"
    try:
        sha = github_get_base_branch_sha_by_repo(owner, repo, branch)
    except Exception:
        sha = ""
    return branch, str(sha or "").strip()


def _teams_attach_repository_context(agent_input: str, active: dict) -> str:
    """Attach shared repository context before Foundry works on a task.

    This replaces the retired cross-user conversation/table-memory cache.  The
    injected block contains only durable repository conclusions from Azure AI
    Search and is explicitly subordinate to current live-GitHub evidence.
    """
    try:
        payload = json.loads(agent_input)
        if not isinstance(payload, dict):
            return agent_input
    except Exception:
        return agent_input

    prompt_for_relevance = str(
        active.get("effective_prompt")
        or payload.get("user_request")
        or payload.get("prompt")
        or payload.get("user_message")
        or ""
    ).strip()
    owner, repo = _repository_context_repo_identity(
        str(active.get("cloud") or payload.get("cloud") or payload.get("expected_cloud") or ""),
        str(active.get("repo_target") or payload.get("repo_target") or payload.get("expected_repo_target") or ""),
        str(payload.get("workflow") or payload.get("expected_workflow") or ""),
        str(active.get("repo_name") or ""),
    )
    if not owner or not repo:
        payload.setdefault(
            "repository_context_tools",
            shared_repository_context.FOUNDRY_REPOSITORY_CONTEXT_TOOL_SCHEMAS,
        )
        return json.dumps(payload, ensure_ascii=False)

    preferred_branch = str(
        active.get("context_branch")
        or active.get("existing_branch")
        or payload.get("repository_ref")
        or ""
    ).strip()
    branch, current_sha = _repository_context_branch_and_sha(owner, repo, preferred_branch)
    try:
        search_result = shared_repository_context.search_repository_context(
            repo_owner=owner,
            repo_name=repo,
            query=prompt_for_relevance,
            current_commit_sha=current_sha,
        )
        context_block = shared_repository_context.format_repository_context_for_agent(search_result)
    except Exception as exc:
        LOGGER.warning(
            "[TerrabotDiag] event=repository_context_attach_failed repo=%s/%s error=%s",
            owner,
            repo,
            exc,
        )
        context_block = ""
        search_result = {"results": []}

    if context_block:
        payload["shared_repository_context"] = context_block
        payload["shared_repository_context_metadata"] = {
            "repository": f"{owner}/{repo}",
            "branch": branch,
            "current_commit_sha": current_sha,
            "result_count": len(search_result.get("results") or []),
            "stale_count": int(search_result.get("stale_count") or 0),
            "conflicted_count": int(search_result.get("conflicted_count") or 0),
        }
    payload["repository_context_tools"] = (
        shared_repository_context.FOUNDRY_REPOSITORY_CONTEXT_TOOL_SCHEMAS
    )
    return json.dumps(payload, ensure_ascii=False)


def _repository_context_collect_live_evidence(payload: Any, max_files: int = 12) -> list[dict]:
    """Collect bounded live repository file evidence already supplied for this turn.

    This is intentionally conservative: clarification text is never evidence by
    itself. A clarification can be promoted to shared repository context only
    when at least one current repository file in the request supports it.
    """
    found: list[dict] = []
    seen: set[str] = set()

    def _collect(value: Any) -> None:
        if len(found) >= max_files:
            return
        if isinstance(value, dict):
            path = str(value.get("path") or value.get("filename") or "").strip()
            content = value.get("content")
            if path and isinstance(content, str) and content.strip() and path not in seen:
                seen.add(path)
                found.append({
                    "path": path,
                    "content": content[:16000],
                    "truncated": len(content) > 16000,
                })
            for nested in value.values():
                if isinstance(nested, (dict, list)):
                    _collect(nested)
        elif isinstance(value, list):
            for item in value:
                _collect(item)

    _collect(payload)
    return found[:max_files]


def _repository_context_should_capture_clarification(prompt: str) -> bool:
    """Return True for likely clarification/resolution turns.

    Explicit definition-style replies and short contextual follow-ups qualify.
    The subsequent evidence-validation step is what decides whether anything is
    actually persisted.
    """
    text = str(prompt or "").strip()
    if not text or not str(_TEAMS_CONVERSATION_CONTEXT.get() or "").strip():
        return False
    if _TEAMS_SHORT_FOLLOW_UP.get():
        return True
    return bool(re.search(
        r"\b(?:means|meaning|refers\s+to|is\s+the|is\s+an?|same\s+as|aka|a\.?k\.?a\.?|by\s+.+?\s+i\s+mean)\b",
        text,
        re.IGNORECASE,
    ))


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


def _extract_and_store_repository_context_from_clarification(agent_input: str, active: dict) -> dict:
    """Promote an evidence-backed clarification before any commit occurs.

    Example: a user clarifies that "observe collector" refers to the repo's
    OTel collector. Foundry may extract that alias/relationship immediately, but
    the backend stores it only when an exact current GitHub/workspace excerpt
    supports the conclusion. This is best-effort and never blocks the request.
    """
    prompt = str(active.get("effective_prompt") or "").strip()
    if not _repository_context_should_capture_clarification(prompt):
        return {"ok": True, "stored": 0, "skipped": "not_clarification"}
    try:
        payload = json.loads(agent_input)
    except Exception:
        return {"ok": True, "stored": 0, "skipped": "non_json_input"}
    if not isinstance(payload, dict):
        return {"ok": True, "stored": 0, "skipped": "non_object_input"}

    owner, repo = _repository_context_repo_identity(
        str(active.get("cloud") or payload.get("cloud") or payload.get("expected_cloud") or ""),
        str(active.get("repo_target") or payload.get("repo_target") or payload.get("expected_repo_target") or ""),
        str(payload.get("workflow") or payload.get("expected_workflow") or ""),
        str(active.get("repo_name") or ""),
    )
    if not owner or not repo:
        return {"ok": True, "stored": 0, "skipped": "repo_unresolved"}

    evidence = _repository_context_collect_live_evidence(payload)
    if not evidence:
        LOGGER.warning(
            "[TerrabotDiag] event=repository_context_clarification_skipped repo=%s/%s reason=no_live_evidence",
            owner, repo,
        )
        return {"ok": True, "stored": 0, "skipped": "no_live_evidence"}

    branch, commit_sha = _repository_context_branch_and_sha(
        owner,
        repo,
        str(active.get("context_branch") or active.get("existing_branch") or payload.get("repository_ref") or ""),
    )
    if not commit_sha:
        return {"ok": True, "stored": 0, "skipped": "commit_unresolved"}

    transcript = str(_TEAMS_CONVERSATION_CONTEXT.get() or "")[-6000:]
    try:
        existing = search_repository_context(
            owner, repo, prompt, current_commit_sha=commit_sha, top_k=6
        ).get("results") or []
    except Exception:
        existing = []

    extraction = {
        "task": "EXTRACT DURABLE REPOSITORY CONTEXT FROM RESOLVED CLARIFICATION",
        "repository": f"{owner}/{repo}",
        "branch": branch,
        "evidence_commit_sha": commit_sha,
        "current_user_reply": prompt,
        "clarification_exchange": transcript,
        "relevant_code": evidence,
        "existing_repository_context": existing,
        "required_output": {
            "candidates": [{
                "category": "resolved_clarification",
                "subject": "stable repository concept or user-facing alias",
                "scope": "repository/module/component/environment/path",
                "statement": "one durable repository-specific clarification",
                "confidence": 0.0,
                "evidence": [{
                    "path": "repo-relative path present in relevant_code",
                    "excerpt": "short exact excerpt copied from repository code",
                    "reason": "why this excerpt supports the clarification",
                }],
                "validation_summary": "why this clarification will help future repository tasks",
            }]
        },
        "rules": [
            "Return JSON only with exactly one top-level key: candidates.",
            "This is clarification extraction, not Terraform generation.",
            "Persist only a repository-specific resolved clarification that will help future users understand the same repository concept.",
            "The conversation establishes what the user meant, but it is not repository evidence. Every candidate must also be supported by an exact excerpt from relevant_code.",
            "Typical useful output is an alias or semantic mapping such as a team-facing resource phrase mapping to the concrete component/module name used by this repository.",
            "Do not emit user preferences, one-off task choices, secrets, conversation summaries, or unsupported terminology mappings.",
            "Do not repeat an existing context item unless current evidence materially updates or conflicts with it.",
            "Use confidence >= 0.80 only when both the clarification exchange and repository evidence support the mapping.",
            "Prefer zero candidates over a weak inference.",
        ],
    }

    LOGGER.warning(
        "[TerrabotDiag] event=repository_context_clarification_extraction_started repo=%s/%s branch=%s",
        owner, repo, branch,
    )
    try:
        text = call_named_agent(json.dumps(extraction, ensure_ascii=False), AGENT_NAME)
        candidates = shared_repository_context.parse_context_extraction_response(text)
    except Exception as exc:
        LOGGER.warning(
            "[TerrabotDiag] event=repository_context_clarification_extraction_failed repo=%s/%s error=%s",
            owner, repo, exc,
        )
        return {"ok": False, "stored": 0, "error": str(exc)}

    task_hash = hashlib.sha256(
        json.dumps({
            "repo": f"{owner}/{repo}",
            "commit": commit_sha,
            "reply": prompt,
            "transcript": transcript,
        }, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    stored = 0
    rejected = 0
    for candidate in candidates[:4]:
        candidate = dict(candidate or {})
        candidate["category"] = "resolved_clarification"
        try:
            result = add_repository_context(
                owner, repo, commit_sha, candidate,
                evidence_branch=branch,
                source_task_hash=task_hash,
            )
        except Exception as exc:
            result = {"stored": False, "errors": [str(exc)]}
        if result.get("stored"):
            stored += 1
        else:
            rejected += 1

    LOGGER.warning(
        "[TerrabotDiag] event=repository_context_clarification_extraction_completed repo=%s/%s candidates=%s stored=%s rejected=%s",
        owner, repo, len(candidates), stored, rejected,
    )
    return {"ok": True, "candidate_count": len(candidates), "stored": stored, "rejected": rejected}


_GROUNDING_REFUSAL_RE = re.compile(
    r"\b(cannot safely|can(?:not|['\u2019]t) safely|not grounded|cannot proceed without|"
    r"unable to safely|could not (?:be completed|safely)|cannot determine (?:the )?exact|"
    r"i need (?:the )?exact|please provide the exact|provide the exact|specify the exact|"
    r"name the exact|doesn'?t label which|does not label which)\b",
    re.IGNORECASE,
)

# A reply that already presents real numbered/lettered options is a GOOD
# clarification and must never be rewritten, even if it also happens to
# contain refusal-like wording elsewhere in the same message.
_NUMBERED_OPTIONS_RE = re.compile(r"(?m)^\s*\d+[.)]\s+\S")

# "Rule" in an enable/disable request almost always maps to a repository
# Boolean parameter/flag (e.g. `mcp_waf_bot_control_enabled = true`), not a
# Terraform-native nested block. This mirrors foundry-agent-instructions
# rule 13: understand "rule" as a parameter set to true/false first.
_BOOLEAN_ASSIGNMENT_RE = re.compile(
    r'(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(true|false)\b'
)

# WAF/ACL-style rule lists are frequently declared as a plain list-of-strings
# variable/local (e.g. `waf_blocked_rules = ["RuleA", "RuleB", ...]`) rather
# than as individual Boolean flags or nested blocks. Each string entry is a
# selectable option in its own right.
_LIST_LITERAL_RE = re.compile(r"(?ms)([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\[(.*?)\]")


def _teams_looks_like_grounding_refusal(reply: str) -> bool:
    """True when a modification-generation reply is a bare refusal/
    information-seeking dead end instead of a specific, evidence-backed,
    already-answerable-by-number clarifying question.

    Refusals such as "cannot safely disable X because the exact rule names
    are not grounded in the repository evidence", or "I need the exact
    MCP-related rule names ... please provide the exact entries", are
    usually the wrong answer: the agent already had the selected file's
    content in its context and should have asked the user to CHOOSE among
    the actual rule/resource/parameter/list-entry identifiers declared
    there, instead of asking the user to recall or type them from memory.
    A reply that already presents real numbered options (see
    ``_NUMBERED_OPTIONS_RE``) is left alone — it is already a good
    clarification and must not be rewritten.
    """
    text = str(reply or "")
    if not text:
        return False
    if _NUMBERED_OPTIONS_RE.search(text):
        return False
    return bool(_GROUNDING_REFUSAL_RE.search(text))


def _teams_extract_selected_file_contents(payload: Any, max_files: int = 3) -> list[tuple[str, str]]:
    """Recursive search for the selected/target file(s)' live content inside
    an agent-input payload, preferring entries explicitly marked selected.
    """
    found: list[tuple[str, str]] = []

    def _collect(value: Any) -> None:
        if len(found) >= max_files:
            return
        if isinstance(value, dict):
            is_selected = (
                value.get("selection_state") == "selected"
                or value.get("source") == "backend_existing_infra_code_match"
            )
            content = value.get("content")
            path = value.get("path") or value.get("filename") or value.get("selected_path")
            if is_selected and isinstance(content, str) and content.strip():
                found.append((str(path or "selected file"), content))
            matched = value.get("matched_files")
            if isinstance(matched, list):
                for entry in matched:
                    _collect(entry)
            for nested_key in (
                "existing_files",
                "existing_pr_context",
                "retrieved_value_context",
                "retrieved_module_context",
            ):
                nested = value.get(nested_key)
                if isinstance(nested, list):
                    for item in nested:
                        _collect(item)
        elif isinstance(value, list):
            for item in value:
                _collect(item)

    _collect(payload)
    return found[:max_files]


def _teams_extract_any_file_contents(payload: Any, max_files: int = 6) -> list[tuple[str, str]]:
    """Broader fallback: collect content from ANY file-like entry in the
    payload, regardless of whether it was marked "selected".

    Used when :func:`_teams_extract_selected_file_contents` finds nothing —
    for example because the upstream payload never set selection_state on
    the entry the user actually picked. Without this fallback the rescue
    could silently fail to find evidence that was, in fact, present in the
    request, leaving the user back at a bare refusal.
    """
    found: list[tuple[str, str]] = []
    seen_paths: set[str] = set()

    def _collect(value: Any) -> None:
        if len(found) >= max_files:
            return
        if isinstance(value, dict):
            content = value.get("content")
            path = str(value.get("path") or value.get("filename") or value.get("selected_path") or "").strip()
            if isinstance(content, str) and content.strip() and path and path not in seen_paths:
                seen_paths.add(path)
                found.append((path, content))
            matched = value.get("matched_files")
            if isinstance(matched, list):
                for entry in matched:
                    _collect(entry)
            for nested_key in (
                "existing_files",
                "existing_pr_context",
                "retrieved_value_context",
                "retrieved_module_context",
                "candidates",
            ):
                nested = value.get(nested_key)
                if isinstance(nested, list):
                    for item in nested:
                        _collect(item)
        elif isinstance(value, list):
            for item in value:
                _collect(item)

    _collect(payload)
    return found[:max_files]


def _teams_extract_list_literal_entries(content: str, max_lists: int = 4) -> list[tuple[str, str]]:
    """Extract ``variable_name = ["EntryA", "EntryB", ...]`` style lists.

    Returns ``(list_variable_name, entry_string)`` pairs for every quoted
    string entry found in every matching list literal, so each entry can be
    offered as its own selectable option (the common shape for a WAF/ACL
    "blocked rules" list, which is plain strings rather than nested blocks
    or individual Boolean flags).
    """
    pairs: list[tuple[str, str]] = []
    lists_seen = 0
    for match in _LIST_LITERAL_RE.finditer(content):
        var_name, body = match.groups()
        entries = re.findall(r'"([^"]+)"', body)
        if not entries:
            continue
        lists_seen += 1
        for entry in entries:
            pairs.append((var_name, entry))
        if lists_seen >= max_lists:
            break
    return pairs


def _teams_extract_candidate_rule_identifiers(content: str, prompt: str = "", max_items: int = 12) -> list[dict]:
    """Extract named rule/resource/parameter/list-entry identifiers declared
    inside one .tf file, so a clarifying question can offer concrete,
    choosable options instead of only pointing at an abstract file or
    asking the user to recall/type an exact name from memory.

    Reflects repository convention, not Terraform syntax alone: WAF/ACL
    style "rules" are commonly (a) a plain list-of-strings variable/local
    (for example ``waf_blocked_rules = ["RuleA", "RuleB"]``), (b) a Boolean
    parameter/flag (``name = true``/``false``), (c) a named nested
    ``rule { name = "..." }`` block, or — rarely — (d) a top-level
    ``resource``/``data`` block. All four shapes are collected and then
    ranked together by overlap with the request's own wording so, for
    example, a list entry or flag whose name contains "mcp" outranks an
    unrelated one found in the same file.
    """
    prompt_tokens = {token for token in re.findall(r"[a-z0-9]+", (prompt or "").lower()) if len(token) >= 3}

    def _relevance(text: str) -> int:
        text_lower = text.lower()
        text_tokens = set(re.findall(r"[a-z0-9]+", text_lower))
        exact_hits = text_tokens & prompt_tokens
        # Identifiers such as AWS managed rule set names are frequently
        # camelCase/PascalCase with no separators (e.g.
        # "AWSManagedRulesMcpBotControl"), so a whole-token match never
        # occurs even when the identifier clearly names the requested
        # concept ("mcp"). A case-insensitive substring check catches this
        # without needing full camelCase segmentation.
        substring_hits = {token for token in prompt_tokens if token not in exact_hits and token in text_lower}
        return len(exact_hits) * 2 + len(substring_hits)

    candidates: list[dict] = []
    seen: set[str] = set()

    for var_name, entry in _teams_extract_list_literal_entries(content):
        if entry in seen:
            continue
        seen.add(entry)
        candidates.append({
            "identifier": entry,
            "kind": "list_entry",
            "list_variable": var_name,
            "description": f"entry in the `{var_name}` list",
            "_score": _relevance(entry) + _relevance(var_name),
        })

    for match in re.finditer(r"(?ms)\brule\s*\{(.*?)\n\s*\}", content):
        block = match.group(1)
        name_match = re.search(r'name\s*=\s*"([^"]+)"', block)
        if name_match:
            name = name_match.group(1).strip()
            if name and name not in seen:
                seen.add(name)
                candidates.append({
                    "identifier": name,
                    "kind": "rule",
                    "description": "named rule block",
                    "_score": _relevance(name),
                })

    for match in _BOOLEAN_ASSIGNMENT_RE.finditer(content):
        name, value = match.groups()
        if name in seen:
            continue
        seen.add(name)
        candidates.append({
            "identifier": name,
            "kind": "parameter",
            "current_value": value,
            "description": f"parameter, currently `{value}`",
            "_score": _relevance(name),
        })

    for match in re.finditer(r'(?m)^\s*(resource|data)\s+"([^"]+)"\s+"([^"]+)"', content):
        kind, res_type, res_name = match.groups()
        label = f"{res_type}.{res_name}"
        if label in seen:
            continue
        seen.add(label)
        candidates.append({
            "identifier": label,
            "kind": kind,
            "description": f"{kind} block",
            "_score": _relevance(label),
        })

    # Stable sort: relevance to the prompt first, otherwise keep discovery
    # order (list entries, then rule blocks, then parameters, then
    # resources) so a large, mostly-irrelevant list still shows its first
    # few entries rather than an arbitrary re-shuffle.
    candidates_with_index = list(enumerate(candidates))
    candidates_with_index.sort(key=lambda pair: (-pair[1]["_score"], pair[0]))
    ordered = [item for _index, item in candidates_with_index]
    for item in ordered:
        item.pop("_score", None)
    return ordered[:max_items]


def _teams_build_options_question(
    options: list[dict],
    prompt: str,
    file_path: str,
    total_available: int = 0,
) -> str:
    """Render extracted identifiers as a real numbered picker with a short
    description per option, instead of asking the user to type/recall an
    exact name from memory.
    """
    lines = [
        f"I found the following option(s) in `{file_path}` for \"{prompt.strip()}\". "
        "Which one(s) should be changed?" if prompt.strip() else
        f"I found the following option(s) in `{file_path}`. Which one(s) should be changed?",
        "",
    ]
    for index, item in enumerate(options, start=1):
        description = str(item.get("description") or item.get("kind") or "").strip()
        suffix = f" — {description}" if description else ""
        lines.append(f"{index}. `{item['identifier']}`{suffix}")
    remaining = total_available - len(options)
    if remaining > 0:
        lines.append(f"...and {remaining} more option(s) not shown. Reply with the exact name if you don't see it above.")
    lines.extend(["", "Reply with the number(s) or the exact name(s)."])
    return "\n".join(lines)


def _teams_build_grounding_rescue_reply(
    files: list[tuple[str, str]],
    prompt: str = "",
    max_options: int = 15,
) -> Optional[tuple[str, dict]]:
    """Build a clarification naming concrete, choosable options found in the
    selected file(s), instead of leaving a bare refusal or asking the user
    to recall/type an exact identifier.

    Returns ``(reply_json_str, resolution_context)`` on success, where
    ``resolution_context`` is the structured record (options, file, prompt)
    the caller should persist so the user's next reply (a number or name)
    can be deterministically resolved back into a fully-specified
    instruction — see :func:`_teams_resolve_pending_rescue_selection`.
    Returns None when no useful identifiers could be extracted at all, so
    the caller can fall back to :func:`_teams_build_generic_clarification_reply`.
    """
    all_options: list[dict] = []
    primary_file = files[0][0] if files else ""
    for path, content in files:
        identifiers = _teams_extract_candidate_rule_identifiers(content, prompt=prompt, max_items=40)
        for item in identifiers:
            item = dict(item)
            item["file"] = path
            all_options.append(item)
    if not all_options:
        return None

    visible_options = all_options[:max_options]
    question = _teams_build_options_question(visible_options, prompt, primary_file, total_available=len(all_options))
    payload = {
        "summary": question,
        "reply": question,
        "analysis": (
            f"Inspected `{primary_file}` and extracted {len(all_options)} named "
            "rule/parameter/list-entry candidate(s) instead of asking the user to recall an exact name."
        ),
        "questions": [question],
        "files": [],
        "user_fillable": [],
    }
    resolution_context = {
        "options": visible_options,
        "file": primary_file,
        "original_prompt": prompt,
    }
    return json.dumps(payload, ensure_ascii=False), resolution_context


def _teams_build_generic_clarification_reply(prompt: str, files: Optional[list[tuple[str, str]]] = None) -> str:
    """Guaranteed non-refusal fallback: always ask, never dead-end.

    Used when the request was recognized as a modification but no
    identifiers could be extracted from any recovered file content. The
    user must always get an interactive question instead of a bare
    "cannot proceed" message, per the no-dead-end requirement.
    """
    files = files or []
    inspected = f" I inspected `{files[0][0]}`." if files else ""
    clean_prompt = str(prompt or "").strip()
    question = (
        (f'For "{clean_prompt}", ' if clean_prompt else "")
        + "I could not confidently identify the exact rule, resource, or parameter to change."
        + inspected
        + " Please name the specific rule/parameter (or its current true/false value) that should be changed, "
        "and I will apply it."
    )
    payload = {
        "summary": question,
        "reply": question,
        "analysis": (
            "Repository evidence was inspected but did not contain an unambiguous, "
            "uniquely named match for this request; asking the user instead of refusing."
        ),
        "questions": [question],
        "files": [],
        "user_fillable": [],
    }
    return json.dumps(payload, ensure_ascii=False)


def _teams_maybe_rescue_grounding_refusal(agent_input: str, reply: str) -> Optional[tuple[str, Optional[dict]]]:
    """Turn a bare grounding refusal into an evidence-backed, choosable
    clarification.

    Guarantees the user is never left with a bare "cannot safely"/"not
    grounded"/"please provide the exact ..." refusal for a modification
    request that reached the agent: if named identifiers can be extracted
    from recovered file content, they are presented as a numbered picker;
    otherwise a still-interactive generic clarification is returned. Only a
    reply that is not recognized as a refusal at all (or a payload that
    cannot be parsed) is left completely untouched.

    Returns ``(reply, resolution_context_or_None)``. ``resolution_context``
    is non-None only when a numbered picker was built, and should be
    persisted (see ``call_agent``) so the next user reply can be resolved
    deterministically instead of being sent to the agent as free text.
    """
    if not _teams_looks_like_grounding_refusal(reply):
        return None
    try:
        payload = json.loads(agent_input)
    except Exception:
        LOGGER.warning(
            "TEAMS-RESCUE-1: grounding refusal detected but agent_input was not valid JSON; "
            "cannot recover file evidence, leaving the original reply unchanged."
        )
        return None

    prompt = str(payload.get("user_request") or payload.get("prompt") or "").strip()
    files = _teams_extract_selected_file_contents(payload)
    extraction_mode = "selected"
    if not files:
        files = _teams_extract_any_file_contents(payload)
        extraction_mode = "any-file-fallback"

    # Never turn an explicit enable/disable request into the old broad picker
    # that enumerates every Boolean, data block, list entry, and resource found
    # in whichever recovered Terraform file happens to come first. That was the
    # regression that surfaced backend.tf encryption/SSM/subnet options for a
    # patch-monitoring request. The dedicated Boolean resolver above owns this
    # workflow. If it still cannot resolve the feature, return one concise
    # semantic clarification instead of unrelated repository choices.
    feature_intent = _teams_feature_flag_intent(prompt)
    if feature_intent in {"enable", "disable"}:
        question = (
            f'I could not map "{prompt}" to a unique repository Boolean control in the resolved environment. '
            "I will not show unrelated Terraform parameters as choices. Please clarify the feature/resource meaning in plain language."
        )
        payload_out = {
            "summary": question,
            "reply": question,
            "analysis": "The resolved environment was inspected, but no repository-proven Boolean control was uniquely selected after semantic resolution.",
            "questions": [question],
            "files": [],
            "user_fillable": [],
        }
        LOGGER.warning(
            "[TerrabotDiag] event=feature_flag_grounding_rescue_suppressed_broad_picker request=%s files=%s",
            prompt[:160],
            [path for path, _content in files],
        )
        return json.dumps(payload_out, ensure_ascii=False), None

    LOGGER.info(
        "TEAMS-RESCUE-2: grounding refusal detected, attempting rescue prompt=%r "
        "extraction_mode=%s files_recovered=%s",
        prompt[:160], extraction_mode, [path for path, _content in files],
    )

    try:
        rescued = _teams_build_grounding_rescue_reply(files, prompt=prompt) if files else None
        if rescued:
            reply_json, resolution_context = rescued
            LOGGER.info(
                "TEAMS-RESCUE-3: rescued refusal with %s named option(s) from recovered file content.",
                len(resolution_context.get("options") or []),
            )
            return reply_json, resolution_context
        LOGGER.warning(
            "TEAMS-RESCUE-4: no named identifiers could be extracted from %s recovered file(s); "
            "falling back to a generic (but still interactive) clarification instead of the bare refusal.",
            len(files),
        )
        return _teams_build_generic_clarification_reply(prompt, files), None
    except Exception:
        LOGGER.exception("TEAMS-RESCUE-ERROR: rescue construction failed; using generic clarification fallback.")
        return _teams_build_generic_clarification_reply(prompt, files), None


def _teams_selected_rescue_options(prompt: str, pending: dict) -> list[dict]:
    """Return the live-repository picker options explicitly selected by a user."""
    options = pending.get("options") or []
    text = str(prompt or "").strip()
    if not options or not text:
        return []

    selected: list[dict] = []
    number_tokens = re.findall(r"\d+", text)
    if number_tokens and re.fullmatch(r"[\d,\s&and]+", text, re.IGNORECASE):
        for token in number_tokens:
            index = int(token) - 1
            if 0 <= index < len(options):
                selected.append(dict(options[index]))
    if not selected:
        normalized = text.lower()
        for option in options:
            identifier = str(option.get("identifier") or "").lower()
            if identifier and (identifier == normalized or identifier in normalized or normalized in identifier):
                selected.append(dict(option))

    deduped = []
    seen = set()
    for item in selected:
        key = (str(item.get("file") or pending.get("file") or ""), str(item.get("identifier") or ""))
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped


def _repository_context_evidence_excerpt(content: str, identifier: str, radius: int = 2) -> str:
    """Return a small exact excerpt around an identifier from live repository text."""
    lines = str(content or "").splitlines()
    needle = str(identifier or "").strip().lower()
    if not needle:
        return ""
    for index, line in enumerate(lines):
        if needle in line.lower():
            start = max(0, index - radius)
            end = min(len(lines), index + radius + 1)
            return "\n".join(lines[start:end]).strip()
    return ""


def _store_repository_context_from_resource_selection(
    user_reply: str,
    pending: dict,
    selected: list[dict],
) -> dict:
    """Persist user-phrase -> selected live-resource mappings immediately.

    This runs when Terrabot showed repository-derived resource/flag/rule options
    and the user chose one. No Git commit is required. Foundry extracts only a
    durable ``resolved_clarification`` and the normal repository-context layer
    still validates the cited excerpt against the exact repository commit before
    storing it.
    """
    if not selected:
        return {"ok": True, "stored": 0, "skipped": "no_selection"}

    cloud = str(pending.get("cloud") or "").strip()
    repo_target = str(pending.get("repo_target") or "").strip()
    owner, repo = _repository_context_repo_identity(cloud, repo_target, "", "")
    if not owner or not repo:
        return {"ok": True, "stored": 0, "skipped": "repo_unresolved"}

    try:
        branch, commit_sha = _repository_context_branch_and_sha(owner, repo, "")
    except Exception as exc:
        return {"ok": False, "stored": 0, "error": str(exc)}
    if not commit_sha:
        return {"ok": True, "stored": 0, "skipped": "commit_unresolved"}

    relevant_code = []
    for item in selected:
        path = str(item.get("file") or pending.get("file") or "").strip()
        identifier = str(item.get("identifier") or "").strip()
        if not path or not identifier:
            continue
        try:
            content = github_get_file_content(
                cloud, path, branch, repo_target=repo_target or None, workflow="",
            )
        except Exception:
            content = None
        excerpt = _repository_context_evidence_excerpt(content or "", identifier)
        if excerpt:
            relevant_code.append({
                "path": path,
                "identifier": identifier,
                "kind": str(item.get("kind") or "resource"),
                "content": excerpt,
            })

    if not relevant_code:
        LOGGER.warning(
            "[TerrabotDiag] event=repository_context_resource_selection_skipped repo=%s/%s reason=no_live_evidence",
            owner, repo,
        )
        return {"ok": True, "stored": 0, "skipped": "no_live_evidence"}

    original_prompt = str(pending.get("original_prompt") or "").strip()
    selection_text = ", ".join(str(item.get("identifier") or "") for item in selected)
    try:
        existing = search_repository_context(
            owner, repo, original_prompt or selection_text, current_commit_sha=commit_sha, top_k=6
        ).get("results") or []
    except Exception:
        existing = []

    extraction = {
        "task": "EXTRACT DURABLE REPOSITORY CONTEXT FROM RESOLVED RESOURCE SELECTION",
        "repository": f"{owner}/{repo}",
        "branch": branch,
        "evidence_commit_sha": commit_sha,
        "original_user_request": original_prompt,
        "user_selection_reply": str(user_reply or "").strip(),
        "selected_repository_targets": selected,
        "relevant_code": relevant_code,
        "existing_repository_context": existing,
        "required_output": {
            "candidates": [{
                "category": "resolved_clarification",
                "subject": "stable user-facing repository term or resource alias",
                "scope": "repository/module/component/environment/path",
                "statement": "durable mapping from the user's phrase to the selected concrete repository target",
                "confidence": 0.0,
                "evidence": [{
                    "path": "repo-relative path present in relevant_code",
                    "excerpt": "exact excerpt copied from relevant_code.content",
                    "reason": "why the selected repository target supports this semantic mapping",
                }],
                "validation_summary": "why this mapping will prevent future ambiguity",
            }]
        },
        "rules": [
            "Return JSON only with exactly one top-level key: candidates.",
            "Emit only resolved_clarification candidates.",
            "The user's selection resolves which live repository target their original wording meant.",
            "Store the semantic mapping, not the one-off requested action. Example: store 'observe collector refers to the repository OTel collector', not 'disable it in us1'.",
            "Every candidate must cite an exact excerpt from relevant_code; the user reply alone is never repository evidence.",
            "Do not store environment-specific action state unless the terminology itself is environment-specific.",
            "Do not store user preferences, conversation summaries, secrets, branch choices, or transient task state.",
            "Prefer zero candidates if the original phrase is too generic to be useful across future tasks.",
            "Use confidence >= 0.80 only when the selection and repository evidence jointly support the mapping.",
        ],
    }

    LOGGER.warning(
        "[TerrabotDiag] event=repository_context_resource_selection_extraction_started repo=%s/%s selected=%s",
        owner, repo, selection_text,
    )
    try:
        text = call_named_agent(json.dumps(extraction, ensure_ascii=False), AGENT_NAME)
        candidates = shared_repository_context.parse_context_extraction_response(text)
    except Exception as exc:
        LOGGER.warning(
            "[TerrabotDiag] event=repository_context_resource_selection_extraction_failed repo=%s/%s error=%s",
            owner, repo, exc,
        )
        return {"ok": False, "stored": 0, "error": str(exc)}

    task_hash = hashlib.sha256(json.dumps({
        "repo": f"{owner}/{repo}",
        "commit": commit_sha,
        "request": original_prompt,
        "reply": str(user_reply or "").strip(),
        "selected": [str(item.get("identifier") or "") for item in selected],
    }, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    stored = 0
    rejected = 0
    for candidate in candidates[:4]:
        candidate = dict(candidate or {})
        candidate["category"] = "resolved_clarification"
        try:
            result = add_repository_context(
                owner, repo, commit_sha, candidate, evidence_branch=branch, source_task_hash=task_hash
            )
        except Exception as exc:
            result = {"stored": False, "errors": [str(exc)]}
        if result.get("stored"):
            stored += 1
        else:
            rejected += 1

    LOGGER.warning(
        "[TerrabotDiag] event=repository_context_resource_selection_extraction_completed repo=%s/%s candidates=%s stored=%s rejected=%s",
        owner, repo, len(candidates), stored, rejected,
    )
    return {"ok": True, "candidate_count": len(candidates), "stored": stored, "rejected": rejected}


def _teams_resolve_pending_rescue_selection(prompt: str, pending: dict) -> Optional[str]:
    """Resolve a user's picker reply into an exact repository instruction."""
    selected = _teams_selected_rescue_options(prompt, pending)
    if not selected:
        return None

    text = str(prompt or "").strip()
    file_path = str(pending.get("file") or "").strip()
    original_prompt = str(pending.get("original_prompt") or "").strip()
    identifiers = ", ".join(f'"{item.get("identifier")}"' for item in selected)
    kinds = {str(item.get("kind") or "") for item in selected}

    if kinds == {"parameter"}:
        feature_intent = _teams_feature_flag_intent(original_prompt)
        target_value = "true" if feature_intent == "enable" else "false"
        instruction = (
            f'Continue the ORIGINAL infrastructure request "{original_prompt}". The user selected '
            f'parameter(s) {identifiers} in `{file_path}`. Set only the selected parameter(s) to '
            f'`{target_value}` and preserve every other line unchanged. This is a resolved target-selection '
            "continuation, not a new chat request."
        )
    elif kinds == {"list_entry"}:
        list_vars = {str(item.get("list_variable") or "") for item in selected}
        list_var = next(iter(list_vars)) if len(list_vars) == 1 else ""
        list_note = f" from the `{list_var}` list" if list_var else ""
        instruction = (
            f'For the request "{original_prompt}": disable the rule entry/entries {identifiers}{list_note} '
            f"in `{file_path}`. Preserve every other entry in that list unchanged."
        )
    else:
        instruction = (
            f'For the request "{original_prompt}": apply the requested change to {identifiers} in '
            f"`{file_path}`. Do not change any other declaration in that file."
        )

    LOGGER.info(
        "TEAMS-RESCUE-RESOLVE: resolved user reply %r to option(s) %s -> instruction=%r",
        text[:80], [item.get("identifier") for item in selected], instruction[:200],
    )
    return instruction


def call_agent(conversation_id: Optional[str], agent_input: str):
    """Run Teams generation with bounded live-GitHub context and one safe retry.

    Every Teams call is additionally enriched with shared repository-level
    context from Azure AI Search before Foundry works. This context contains
    only evidence-validated durable repository knowledge; it is not a
    conversation log and current live GitHub evidence always wins. A bare
    "cannot safely ground exact rule/value names" refusal for a
    modification request is rescued into a clarification that names the
    actual rule/resource identifiers found in the selected file's live
    content, since the agent already had that evidence available.
    """
    active = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    teams_active = bool(active.get("active"))
    first_fresh = bool(
        teams_active
        and active.get("fresh_infra_generation")
        and not active.get("fresh_generation_consumed")
    )
    if first_fresh:
        active["fresh_generation_consumed"] = True
        conversation_id = None

    call_id = uuid.uuid4().hex[:10]
    if teams_active:
        LOGGER.info(
            "TEAMS-AGENT-CALL-1[%s]: sending prompt to Foundry agent conversation_id=%s "
            "teams_conversation=%s cloud=%s repo_target=%s effective_prompt=%r input_chars=%s",
            call_id,
            conversation_id or "(new)",
            str(active.get("teams_conversation_id") or ""),
            str(active.get("cloud") or ""),
            str(active.get("repo_target") or ""),
            str(active.get("effective_prompt") or "")[:200],
            len(agent_input or ""),
        )

    context_budget = max(90000, int(os.getenv("TERRABOT_TEAMS_AGENT_CONTEXT_MAX_CHARS", "180000")))
    context_enriched_input = (
        _teams_attach_repository_context(agent_input, active) if teams_active else agent_input
    )
    if teams_active:
        try:
            _extract_and_store_repository_context_from_clarification(context_enriched_input, active)
        except Exception as exc:
            LOGGER.warning(
                "[TerrabotDiag] event=repository_context_clarification_capture_failed error=%s",
                exc,
            )
    bounded_input = (
        _teams_compact_agent_input(context_enriched_input, context_budget)
        if teams_active
        else context_enriched_input
    )
    try:
        result_conversation_id, reply = _TEAMS_MULTICLOUD_PREVIOUS_CALL_AGENT(conversation_id, bounded_input)
    except Exception as exc:
        if not teams_active or not _teams_is_context_length_error(exc):
            if teams_active:
                LOGGER.exception("TEAMS-AGENT-CALL-ERROR[%s]: Foundry agent call failed.", call_id)
            raise
        LOGGER.warning(
            "TEAMS-AGENT-CALL-RETRY[%s]: Teams Foundry context limit reached; retrying once with a "
            "fresh conversation and tighter live-repository context.",
            call_id,
        )
        retry_input = _teams_compact_agent_input(context_enriched_input, 45000)
        result_conversation_id, reply = _TEAMS_MULTICLOUD_PREVIOUS_CALL_AGENT(None, retry_input)

    if teams_active:
        LOGGER.info(
            "TEAMS-AGENT-CALL-2[%s]: Foundry agent responded conversation_id=%s reply_chars=%s "
            "reply_preview=%r looks_like_refusal=%s",
            call_id,
            result_conversation_id or "",
            len(reply or ""),
            str(reply or "")[:200],
            _teams_looks_like_grounding_refusal(reply),
        )
        rescue_outcome = _teams_maybe_rescue_grounding_refusal(context_enriched_input, reply)
        if rescue_outcome:
            rescued_reply, resolution_context = rescue_outcome
            LOGGER.info(
                "TEAMS-AGENT-CALL-3[%s]: rescued a bare grounding refusal into an evidence-backed "
                "clarification before returning it to the user (options=%s).",
                call_id,
                len((resolution_context or {}).get("options") or []),
            )
            reply = rescued_reply
            teams_conversation_id = str(active.get("teams_conversation_id") or "").strip()
            if resolution_context and teams_conversation_id:
                try:
                    _teams_save_ui_state(
                        teams_conversation_id,
                        {
                            "pending_rescue_selection": {
                                **resolution_context,
                                "cloud": str(active.get("cloud") or ""),
                                "repo_target": str(active.get("repo_target") or ""),
                            },
                        },
                    )
                    LOGGER.info(
                        "TEAMS-RESCUE-5: persisted pending rescue selection for conversation=%s "
                        "(%s option(s)) so the next reply can be resolved deterministically.",
                        teams_conversation_id,
                        len(resolution_context.get("options") or []),
                    )
                except Exception:
                    LOGGER.exception(
                        "TEAMS-RESCUE-ERROR: unable to persist pending rescue selection for conversation=%s",
                        teams_conversation_id,
                    )
    return result_conversation_id, reply


def _handle_teams_chat_request_multicloud(data: dict):
    """Final Teams router with strict intent and independent AWS/Azure flows."""
    request_data = dict(data or {})
    prompt = str(request_data.get("prompt") or request_data.get("message") or "").strip()
    action = str(request_data.get("action") or "").strip().lower()
    teams_conversation_id = str(
        request_data.get("teams_conversation_id")
        or request_data.get("conversation_id")
        or ""
    ).strip()
    memory_conversation_id = str(
        request_data.get("memory_conversation_id")
        or teams_conversation_id
    ).strip()
    state = load_teams_conversation_state(teams_conversation_id) if teams_conversation_id else {}
    stage = str(state.get("stage") or "").strip()

    decision_stages = {
        "awaiting_branch_reuse_decision",
        "awaiting_jira",
        "awaiting_branch_commit",
        "awaiting_pr_confirmation",
        "infra_preview",
        "infra_modification_target_selection",
        "processing_target_selection",
        "processing_new_infrastructure_request",
        "azure_module_branch_selection",
        "aws_module_selection",
    }
    explicit_infra = str(request_data.get("mode") or "").strip().lower() == "infra"
    continuation_reply = any(
        _teams_truthy(request_data.get(key))
        for key in (
            "pending_target_selection_reply",
            "pending_branch_choice_reply",
            "pending_branch_choice_resolved",
            "pending_target_selection_resolved",
        )
    )

    # Critical guard: prior infra state must never turn ordinary language into
    # a Terraform request. Explicit continuation markers and processing stages
    # are owned by the workflow state machine and must never be sent to Foundry
    # as plain chat (for example, target option `1`).
    if (
        not action
        and prompt
        and not explicit_infra
        and not continuation_reply
        and stage not in decision_stages
        and not _teams_prompt_requests_pr(prompt)
    ):
        return _teams_plain_chat_reply(
            prompt,
            teams_conversation_id=memory_conversation_id,
            cloud_hint=str(state.get("cloud") or "").strip(),
            repo_target_hint=str(state.get("repo_target") or "").strip(),
            requester=str(request_data.get("teams_requester") or "").strip(),
        )

    # Protocol continuations (branch yes/no and target-picker replies) carry the
    # cloud already resolved for the pending request. Never re-infer cloud from
    # the literal control reply (for example "2" or "no"): doing so produces
    # an empty cloud and can incorrectly trigger the legacy "both AWS and Azure
    # PRs" ambiguity when parallel cloud sessions exist.
    pinned_request_cloud = safe_normalize_cloud(str(
        request_data.get("cloud")
        or request_data.get("requested_cloud")
        or ""
    )) or ""
    requested_cloud = (
        pinned_request_cloud
        or (_teams_safe_request_cloud(prompt) if explicit_infra else "")
    )
    active_cloud = safe_normalize_cloud(str(state.get("cloud") or "")) or ""
    target_cloud_state = _teams_best_cloud_state(state, requested_cloud) if requested_cloud else {}

    # Branch choice must be resolved BEFORE any Foundry generation. Durable UI
    # state can be empty after a worker restart even though the deterministic
    # Terrabot branch still exists remotely. Recover the current cloud's live
    # branch state from GitHub before deciding whether this is a first request
    # or a follow-up. Without this recovery, the request falls through to
    # Foundry immediately and the user never gets the reuse/new-branch choice.
    if explicit_infra and requested_cloud and not target_cloud_state.get("branch"):
        recovery_thread_id = str(
            request_data.get("thread_id")
            or state.get("workflow_thread_id")
            or (_teams_cloud_session(state, requested_cloud) or {}).get("thread_id")
            or ""
        ).strip()
        if recovery_thread_id:
            try:
                restore_teams_workflow_state(recovery_thread_id)
            except Exception:
                pass
            try:
                recovered_thread_state = recover_thread_pr_state(recovery_thread_id) or {}
                recovered_bucket = (
                    "aws" if requested_cloud == "aws"
                    else "azure_consumer"
                )
                recovered_cloud_state = recovered_thread_state.get(recovered_bucket) or {}
                if recovered_cloud_state.get("branch"):
                    target_cloud_state = dict(recovered_cloud_state)
                    target_cloud_state.setdefault("thread_id", recovery_thread_id)
                    request_data["thread_id"] = recovery_thread_id
                    _teams_diag_log(
                        "branch_state_recovered_before_foundry",
                        thread=recovery_thread_id,
                        cloud=requested_cloud,
                        branch=target_cloud_state.get("branch"),
                    )
            except Exception as branch_recovery_error:
                _teams_diag_log(
                    "branch_state_recovery_before_foundry_failed",
                    level="warning",
                    thread=recovery_thread_id,
                    cloud=requested_cloud,
                    error=str(branch_recovery_error)[:240],
                )

    reuse_branch = _teams_truthy(request_data.get("reuse_branch"))
    force_new_branch = _teams_truthy(request_data.get("force_new_branch"))
    branch_choice_already_resolved = _teams_truthy(
        request_data.get("pending_branch_choice_resolved")
    )
    branch_choice_reply = (
        stage == "awaiting_branch_reuse_decision"
        and not action
        and not branch_choice_already_resolved
    )

    # Resolve a pending branch/PR choice against the cloud captured when the
    # choice was asked, not whichever cloud happened to be most recent globally.
    if branch_choice_reply:
        pending_cloud = safe_normalize_cloud(str(state.get("pending_follow_up_cloud") or "")) or requested_cloud or active_cloud
        pending_choice = _teams_branch_choice_from_reply(prompt)
        if pending_choice == "reuse":
            request_data["reuse_branch"] = True
            request_data["force_new_branch"] = False
            reuse_branch = True
            force_new_branch = False
        elif pending_choice == "new":
            request_data["reuse_branch"] = False
            request_data["force_new_branch"] = True
            reuse_branch = False
            force_new_branch = True
        if pending_cloud:
            requested_cloud = pending_cloud
            target_cloud_state = _teams_best_cloud_state(state, pending_cloud)
            session = _teams_cloud_session(state, pending_cloud)
            request_data["thread_id"] = str(
                target_cloud_state.get("thread_id")
                or session.get("thread_id")
                or request_data.get("thread_id")
                or ""
            )
            request_data["existing_branch"] = str(
                target_cloud_state.get("branch") or session.get("branch") or state.get("branch") or ""
            )

    # A new request for the same cloud must ask whether to reuse that cloud's
    # branch/PR or create a new branch. Switching clouds always creates a new
    # branch in the other repository and preserves the old cloud's state.
    if (
        not action
        and explicit_infra
        and requested_cloud
        and not branch_choice_reply
        and not branch_choice_already_resolved
    ):
        if target_cloud_state.get("branch"):
            session_thread = str(target_cloud_state.get("thread_id") or "").strip()
            if session_thread:
                request_data["thread_id"] = session_thread
            request_data["existing_branch"] = target_cloud_state.get("branch")

            if not reuse_branch and not force_new_branch:
                has_pr = bool(target_cloud_state.get("has_open_pr") or target_cloud_state.get("pr_url"))
                branch = str(target_cloud_state.get("branch") or "").strip()
                patch = {
                    "stage": "awaiting_branch_reuse_decision",
                    "pending_follow_up_prompt": prompt,
                    "pending_follow_up_cloud": requested_cloud,
                    "pending_follow_up_has_pr": has_pr,
                    "pending_follow_up_branch": branch,
                    "pending_follow_up_pr_url": target_cloud_state.get("pr_url") or "",
                    "pending_follow_up_ticket_link": request_data.get("ticket_link") or state.get("ticket_link") or "",
                    "pending_follow_up_ticket_number": request_data.get("jira_ticket") or state.get("ticket_number") or "",
                    "pending_follow_up_ticket_title": request_data.get("ticket_title") or state.get("ticket_title") or "",
                }
                _teams_save_ui_state(teams_conversation_id, patch)
                if has_pr:
                    reply = (
                        f"An existing **{requested_cloud.upper()}** pull request is open on branch `{branch}`. "
                        "Reply `yes` to generate this change on that branch and push a new commit to the same PR, "
                        "or reply `no` to create a new branch for a different PR."
                    )
                else:
                    reply = (
                        f"An existing **{requested_cloud.upper()}** Terrabot branch `{branch}` is available. "
                        "Reply `yes` to generate this change on the existing branch, or reply `no` to create a new branch."
                    )
                return {
                    "ok": False,
                    "mode": "branch_choice_required",
                    "decision_state": "awaiting_branch_reuse_decision",
                    "reply": reply,
                    "thread_id": request_data.get("thread_id") or "",
                    "cloud": requested_cloud,
                    "branch": branch,
                    "branch_url": target_cloud_state.get("branch_url") or "",
                    "compare_url": target_cloud_state.get("compare_url") or "",
                    "pr_url": target_cloud_state.get("pr_url") or "",
                    "state_patch": patch,
                    "analysis": _teams_git_resolution_analysis(
                        requested_cloud, target_cloud_state, False, False, active_cloud
                    ),
                }, 400
        elif active_cloud and requested_cloud != active_cloud:
            force_new_branch = True
            request_data["force_new_branch"] = True
            request_data["reuse_branch"] = False
            request_data["existing_branch"] = ""

    # Once a request cloud has been resolved, pin it onto the payload passed to
    # every older handler. Older layers read `cloud` directly; keeping the
    # value only in this wrapper-local `requested_cloud` variable allowed a
    # numeric target reply to reach the legacy multicloud ambiguity guard with
    # target_cloud=None whenever the thread also had state for the other cloud.
    # Parallel AWS/Azure PRs are normal; the current request cloud always wins.
    if requested_cloud:
        request_data["cloud"] = requested_cloud
        request_data["requested_cloud"] = requested_cloud

    # Mark only a genuinely new infrastructure instruction for fresh Foundry
    # generation. Numeric selections, yes/no decisions, Jira links, and PR
    # actions continue the current workflow and do not reset context.
    if explicit_infra and not action and not branch_choice_reply:
        request_data["fresh_infra_generation"] = True

    result, status_code = _TEAMS_MULTICLOUD_PREVIOUS_HANDLE_CHAT(request_data)
    result = dict(result or {})

    result_cloud = safe_normalize_cloud(str(result.get("cloud") or "")) or requested_cloud
    result_thread = str(
        result.get("thread_id")
        or request_data.get("thread_id")
        or state.get("workflow_thread_id")
        or ""
    ).strip()

    # Persist independent AWS and Azure session pointers. This lets the user go
    # AWS -> Azure -> AWS and recover the correct prior AWS branch/PR.
    if result_cloud and teams_conversation_id:
        latest_state = load_teams_conversation_state(teams_conversation_id)
        sessions = dict(latest_state.get("cloud_sessions") or {})
        previous_session = dict(sessions.get(result_cloud) or {})
        for key, value in {
            "thread_id": result_thread,
            "branch": result.get("branch"),
            "branch_url": result.get("branch_url"),
            "compare_url": result.get("compare_url"),
            "pr_url": result.get("pr_url"),
            "pr_number": result.get("pr_number"),
            "repo_target": result.get("repo_target"),
            "workflow": result.get("workflow"),
            "base_branch": result.get("base_branch"),
        }.items():
            if value not in (None, ""):
                previous_session[key] = value
        if result.get("mode") == "pr_created" or result.get("pr_url"):
            previous_session["has_open_pr"] = True
        sessions[result_cloud] = previous_session
        patch = dict(result.get("state_patch") or {})
        patch.update({
            "cloud_sessions": sessions,
            "cloud": result_cloud,
            "pending_follow_up_cloud": None,
            "pending_follow_up_has_pr": None,
            "pending_follow_up_branch": None,
            "pending_follow_up_pr_url": None,
        })
        result["state_patch"] = patch
        _teams_save_ui_state(teams_conversation_id, patch)

    # If the user chose the existing branch that already backs an open PR,
    # refresh that PR immediately after the new commit. No cross-cloud PR is
    # touched because the lookup is scoped to result_cloud/repo_target/branch.
    chosen_reuse = _teams_truthy(request_data.get("reuse_branch"))
    existing_pr_state = target_cloud_state if result_cloud == requested_cloud else {}
    if (
        status_code < 400
        and result.get("mode") == "branch_created"
        and chosen_reuse
        and (existing_pr_state.get("has_open_pr") or existing_pr_state.get("pr_url"))
        and result.get("pending_change_id")
    ):
        pr_request = dict(request_data)
        pr_request.update({
            "action": "create_pr_from_branch",
            "thread_id": result.get("thread_id") or result_thread,
            "pending_change_id": result.get("pending_change_id"),
            "ticket_link": existing_pr_state.get("ticket_link") or state.get("ticket_link") or "",
            "jira_ticket": existing_pr_state.get("ticket_number") or state.get("ticket_number") or "",
            "ticket_title": existing_pr_state.get("ticket_title") or state.get("ticket_title") or "",
            "prompt": prompt,
            "reuse_branch": True,
            "existing_branch": result.get("branch") or existing_pr_state.get("branch") or "",
        })
        refreshed, refreshed_status = _TEAMS_MULTICLOUD_PREVIOUS_HANDLE_CHAT(pr_request)
        refreshed = dict(refreshed or {})
        refreshed["analysis"] = "\n".join(filter(None, [
            str(refreshed.get("analysis") or "").strip(),
            _teams_git_resolution_analysis(result_cloud, existing_pr_state, True, False, active_cloud),
        ]))
        return refreshed, refreshed_status

    if result_cloud and (result.get("mode") in {"branch_created", "pr_created"} or result.get("branch") or result.get("pr_url")):
        git_analysis = _teams_git_resolution_analysis(
            result_cloud,
            target_cloud_state or result,
            chosen_reuse or bool(result.get("branch_reused")),
            force_new_branch or bool(result.get("created_new_branch")),
            active_cloud,
        )
        result["analysis"] = "\n".join(filter(None, [
            str(result.get("analysis") or "").strip(),
            git_analysis,
        ]))

    return result, status_code

# =============================================================================
# Teams new-branch request isolation
# =============================================================================
# A branch-choice reply ("no" => new branch, "yes" => same branch) belongs to
# the new infrastructure prompt captured when the choice was shown.  Older
# workflow dictionaries and the previous Foundry conversation must not be
# allowed to replay files from an earlier request.

_TEAMS_NEW_BRANCH_PREVIOUS_HANDLE_CHAT = _handle_teams_chat_request_multicloud


