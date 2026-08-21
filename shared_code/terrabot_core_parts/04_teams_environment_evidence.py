from __future__ import annotations
def _teams_prompt_environment_tokens(prompt: str) -> list[str]:
    """Candidate environment names from the prompt, longest first so
    'sbx-infra' outranks 'sbx'. Sub-parts of hyphen/underscore tokens are
    included for tier matching (vars/sbx/tier.tfvars)."""
    text = str(prompt or "").lower()
    raw = re.findall(r"[a-z0-9][a-z0-9_-]{2,}", text)
    tokens: set[str] = set()
    for token in raw:
        if token in _TEAMS_ENV_TOKEN_STOPWORDS or token.isdigit():
            continue
        tokens.add(token)
        for part in re.split(r"[-_]", token):
            if len(part) >= 3 and part not in _TEAMS_ENV_TOKEN_STOPWORDS:
                tokens.add(part)
    return sorted(tokens, key=len, reverse=True)[:16]


def _teams_list_value_files_recursive(
    cloud: str,
    branch: str,
    repo_target: Optional[str] = None,
    workflow: Optional[str] = None,
) -> list[str]:
    """Bounded repo-wide walk collecting every *.tfvars path."""
    results: list[str] = []
    visited_dirs = 0

    def walk(current_path: str, depth: int) -> None:
        nonlocal visited_dirs
        if depth > _TEAMS_VALUE_WALK_MAX_DEPTH or visited_dirs >= _TEAMS_VALUE_WALK_MAX_DIRS:
            return
        visited_dirs += 1
        try:
            items = github_get_directory_listing(
                cloud, current_path, branch, repo_target=repo_target, workflow=workflow
            ) or []
        except Exception:
            return
        for item in items:
            if len(results) >= _TEAMS_VALUE_WALK_MAX_FILES:
                return
            item_path = str((item or {}).get("path") or "").strip("/")
            item_type = str((item or {}).get("type") or "")
            if not item_path:
                continue
            if item_type == "dir":
                name = item_path.rsplit("/", 1)[-1]
                if name.startswith(".") or name in {"node_modules"}:
                    continue
                walk(item_path, depth + 1)
            elif item_type == "file" and item_path.endswith(".tfvars"):
                results.append(item_path)

    walk("", 0)
    return results


def _teams_requested_aws_environment_paths(prompt: str, branch: str = "") -> list[str]:
    """Resolve every AWS environment explicitly requested by one Teams prompt.

    This is deliberately plural. A prompt such as ``us1 and us2`` must not be
    collapsed to the first match, and ``all prod environments`` expands from
    the live ``terraform/prod_aws`` directory instead of assuming one default
    production environment.
    """
    text = str(prompt or "").strip().lower().replace("-", "_")
    paths: list[str] = []

    all_prod = bool(re.search(r"\b(?:all|every)\s+(?:prod|production)(?:\s+(?:env|envs|environment|environments|hub|hubs))?\b", text))
    if all_prod and branch:
        try:
            items = github_get_directory_listing(
                "aws", "terraform/prod_aws", branch,
                repo_target="tf-devops", workflow="aws_infra_modification",
            ) or []
            for item in items:
                if isinstance(item, dict) and item.get("type") == "dir":
                    path = str(item.get("path") or "").strip().strip("/")
                    if path.startswith("terraform/prod_aws/") and path not in paths:
                        paths.append(path)
        except Exception:
            LOGGER.debug("Unable to enumerate all live prod AWS environments", exc_info=True)

    # Explicit environment names. Long/specific names are checked before their
    # shorter base names so ``us1_dr`` does not also produce ``us1``.
    aliases: list[tuple[str, str]] = []
    for name, path in {**AWS_DEV_ENV_FOLDERS, **AWS_PROD_ENV_FOLDERS}.items():
        aliases.append((str(name).lower(), str(path)))
    aliases.sort(key=lambda item: len(item[0]), reverse=True)
    consumed: list[tuple[int, int]] = []
    for name, path in aliases:
        forms = {name, name.replace("_", " "), name.replace("_", "-")}
        for form in forms:
            for match in re.finditer(rf"(?<![a-z0-9]){re.escape(form)}(?![a-z0-9])", text):
                span = match.span()
                if any(span[0] >= a and span[1] <= b for a, b in consumed):
                    continue
                if path not in paths:
                    paths.append(path)
                consumed.append(span)
                break
            else:
                continue
            break

    # Region aliases not equal to folder names remain supported by the legacy
    # singular resolver. Add that result when it represents another explicit
    # target, but never use its minidev/us1 fallback for plural requests.
    try:
        legacy_path, legacy_error = detect_explicit_aws_environment(prompt)
    except Exception:
        legacy_path, legacy_error = None, None
    if not legacy_error and legacy_path and legacy_path not in paths:
        paths.append(str(legacy_path).strip().strip("/"))

    return paths


def _teams_exact_aws_environment_path(prompt: str) -> str:
    """Return one deterministic tf-devops environment folder when exactly one is requested.

    AWS repository layout is fixed at the tier boundary: non-production
    environments live under terraform/dev_aws and production environments live
    under terraform/prod_aws.  This helper deliberately bypasses the generic
    repo-wide token walker so words such as ``ec2``, ``instance`` or ``dev_aws``
    can never become accidental environment matches.
    """
    explicit_paths = _teams_requested_aws_environment_paths(prompt)
    if len(explicit_paths) > 1:
        return ""
    if explicit_paths:
        normalized = explicit_paths[0]
    else:
        try:
            path, error = resolve_aws_environment_path(prompt)
        except Exception:
            return ""
        if error or not path:
            return ""
        normalized = str(path).strip().strip("/")
    allowed_prefixes = ("terraform/dev_aws/", "terraform/prod_aws/")
    if normalized == "terraform/root/global" or normalized.startswith(allowed_prefixes):
        return normalized
    return ""


def _teams_read_exact_environment_folder(
    environment_path: str,
    cloud: str,
    repo_target: str | None,
    workflow: str | None,
    branch: str,
) -> tuple[list[dict], list[str], dict]:
    """Read the exact resolved environment folder directly from live GitHub."""
    env = str(environment_path or "").strip().strip("/")
    debug = {"exact_environment_path": env, "files": 0, "value_files": []}
    if not env:
        return [], [], debug

    paths: list[str] = []

    def collect(path: str, depth: int) -> None:
        if depth > 2 or len(paths) >= _TEAMS_ENV_EVIDENCE_MAX_FILES:
            return
        try:
            items = github_get_directory_listing(
                cloud, path, branch, repo_target=repo_target, workflow=workflow
            ) or []
        except Exception as exc:
            debug["error"] = str(exc)
            return
        for item in items:
            if len(paths) >= _TEAMS_ENV_EVIDENCE_MAX_FILES:
                break
            item_path = str((item or {}).get("path") or "").strip("/")
            item_type = str((item or {}).get("type") or "")
            if not item_path:
                continue
            base = item_path.rsplit("/", 1)[-1]
            if item_type == "dir" and depth < 2 and not base.startswith("."):
                collect(item_path, depth + 1)
            elif item_type == "file" and item_path.endswith(_TEAMS_ENV_FOLDER_EXTS):
                paths.append(item_path)

    collect(env, 0)

    # main.tf is the authoritative AWS consumer file when it exists. Read it
    # first so bounded evidence can never omit the consumer target.
    def priority(path: str) -> tuple[int, str]:
        name = path.rsplit("/", 1)[-1].lower()
        order = {
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
        return order.get(name, 4), path

    entries: list[dict] = []
    value_paths: list[str] = []
    total_chars = 0
    for path in sorted(dict.fromkeys(paths), key=priority):
        if path.endswith((".tfvars", ".tfvars.json")):
            value_paths.append(path)
        if total_chars >= _TEAMS_ENV_EVIDENCE_TOTAL_CHARS:
            continue
        try:
            content = github_get_file_content(
                cloud, path, branch, repo_target=repo_target, workflow=workflow
            ) or ""
        except Exception:
            continue
        snippet = str(content)[:_TEAMS_ENV_EVIDENCE_PER_FILE_CHARS]
        entries.append({
            "path": path,
            "content": snippet,
            "reason": "exact backend-resolved AWS environment file (live GitHub)",
        })
        total_chars += len(snippet)

    debug["files"] = len(entries)
    debug["value_files"] = list(value_paths)
    return entries, value_paths, debug


def _teams_locate_environment_value_files(
    prompt: str,
    cloud: str,
    repo_target: str | None,
    workflow: str | None,
    branch: str,
) -> tuple[list[dict], list[str], dict]:
    """Resolve the environment NAMED IN THE PROMPT to its live value files,
    anywhere in the repository — the deterministic step a human performs
    ('sbx-infra' → vars/sbx/sbx-infra/*.tfvars + its parent tier files).

    Returns (evidence_entries, value_paths, debug_summary)."""
    # AWS has a deterministic tiered layout. Resolve the named environment to
    # terraform/dev_aws/<env> or terraform/prod_aws/<env> first and read that
    # folder directly; do not depend on the bounded repo-wide token walk.
    if safe_normalize_cloud(cloud) == "aws":
        exact_envs = _teams_requested_aws_environment_paths(prompt, branch=branch)
        if exact_envs:
            combined_entries: list[dict] = []
            combined_value_paths: list[str] = []
            per_environment: list[dict] = []
            for exact_env in exact_envs:
                entries, value_paths, exact_debug = _teams_read_exact_environment_folder(
                    exact_env, cloud, repo_target, workflow, branch
                )
                combined_entries.extend(
                    entry for entry in entries
                    if str((entry or {}).get("path") or "").endswith((".tfvars", ".tfvars.json"))
                )
                for path in value_paths:
                    if path not in combined_value_paths:
                        combined_value_paths.append(path)
                per_environment.append({
                    "path": exact_env,
                    "files": exact_debug.get("files", 0),
                    "value_files": list(value_paths),
                })
            return combined_entries, combined_value_paths, {
                "tokens": [path.rsplit("/", 1)[-1] for path in exact_envs],
                "walked": 0,
                "matched": combined_value_paths,
                "exact_environment_paths": exact_envs,
                "environments": per_environment,
            }

    tokens = _teams_prompt_environment_tokens(prompt)
    debug = {"tokens": tokens, "walked": 0, "matched": []}
    if not tokens:
        return [], [], debug
    all_values = _teams_list_value_files_recursive(
        cloud, branch, repo_target=repo_target, workflow=workflow
    )
    debug["walked"] = len(all_values)

    scored: list[tuple[int, str]] = []
    for path in all_values:
        lower = path.lower()
        segments = set(re.split(r"[/._]", lower))
        best = 0
        for token in tokens:
            if token in segments:
                best = max(best, len(token) * 10)   # exact segment match wins
            elif token in lower:
                best = max(best, len(token))
        if best:
            scored.append((best, path))
    scored.sort(reverse=True)
    matched = [path for _, path in scored[:8]]

    # Tier parents: value files sitting in ancestor directories of a matched
    # environment file often hold the shared enable flags.
    parents: list[str] = []
    for path in matched:
        parts = path.split("/")[:-1]
        while parts:
            prefix = "/".join(parts)
            for candidate in all_values:
                if candidate not in matched and candidate not in parents:
                    if candidate.rsplit("/", 1)[0] == prefix:
                        parents.append(candidate)
            parts = parts[:-1]
    value_paths = matched + parents[:4]
    debug["matched"] = value_paths

    evidence: list[dict] = []
    total_chars = 0
    for path in value_paths:
        if total_chars >= _TEAMS_ENV_EVIDENCE_TOTAL_CHARS:
            break
        try:
            file_content = github_get_file_content(
                cloud, path, branch, repo_target=repo_target, workflow=workflow
            ) or ""
        except Exception:
            continue
        snippet = str(file_content)[:_TEAMS_ENV_EVIDENCE_PER_FILE_CHARS]
        evidence.append({
            "path": path,
            "content": snippet,
            "reason": "environment value file resolved from the prompt's environment name (live GitHub) — enable flags for the requested environment are set here",
        })
        total_chars += len(snippet)
    return evidence, value_paths, debug

_TEAMS_ENV_FOLDER_EXTS = (".tf", ".tfvars", ".tfvars.json", ".json", ".yaml", ".yml", ".hcl")


def _teams_environment_folder_evidence(
    prompt: str,
    cloud: str,
    repo_target: str,
    workflow: str,
    branch: str,
) -> tuple[list[dict], list[str], dict]:
    """Ship the ENTIRE target environment folder as evidence — every file
    type, not just resource/tfvars files. The environment is resolved by
    matching the name in the prompt (e.g. 'sbx-infra') against directory and
    file names anywhere in the live repository tree, exactly the way a human
    finds it. Returns (evidence_entries, value_write_paths, debug)."""
    if safe_normalize_cloud(cloud) == "aws":
        exact_envs = _teams_requested_aws_environment_paths(prompt, branch=branch)
        if exact_envs:
            combined_entries: list[dict] = []
            combined_value_paths: list[str] = []
            per_environment: list[dict] = []
            for exact_env in exact_envs:
                entries, value_paths, exact_debug = _teams_read_exact_environment_folder(
                    exact_env, cloud, repo_target, workflow, branch
                )
                combined_entries.extend(entries)
                for path in value_paths:
                    if path not in combined_value_paths:
                        combined_value_paths.append(path)
                per_environment.append({
                    "path": exact_env,
                    "files": exact_debug.get("files", 0),
                    "value_files": list(value_paths),
                })
            return combined_entries, combined_value_paths, {
                "tokens": [path.rsplit("/", 1)[-1] for path in exact_envs],
                "matched_dirs": exact_envs,
                "visited": len(exact_envs),
                "files": len(combined_entries),
                "resolver": "deterministic_plural_aws_environment_paths",
                "environments": per_environment,
            }

    tokens = _teams_prompt_environment_tokens(prompt)
    debug: dict = {"tokens": tokens, "matched_dirs": [], "files": 0, "visited": 0}
    if not tokens:
        return [], [], debug

    matched_dirs: list[str] = []
    token_named_files: list[str] = []
    visited = 0

    def walk(path: str, depth: int) -> None:
        nonlocal visited
        if depth > 7 or visited > 250:
            return
        visited += 1
        try:
            items = github_get_directory_listing(
                cloud, path, branch, repo_target=repo_target, workflow=workflow
            ) or []
        except Exception:
            return
        for item in items:
            item_path = str((item or {}).get("path") or "").strip("/")
            item_type = str((item or {}).get("type") or "")
            if not item_path:
                continue
            base = item_path.rsplit("/", 1)[-1].lower()
            if item_type == "dir":
                if base.startswith(".") or base in {"node_modules"}:
                    continue
                if any(token == base or (len(token) >= 4 and token in base) for token in tokens):
                    matched_dirs.append(item_path)
                walk(item_path, depth + 1)
            elif item_type == "file" and base.endswith(_TEAMS_ENV_FOLDER_EXTS):
                stem = base
                for ext in _TEAMS_ENV_FOLDER_EXTS:
                    if stem.endswith(ext):
                        stem = stem[: -len(ext)]
                        break
                if any(token == stem or (len(token) >= 4 and token in stem) for token in tokens):
                    token_named_files.append(item_path)

    walk("", 0)
    debug["visited"] = visited
    debug["matched_dirs"] = matched_dirs[:6]

    folder_files: list[str] = []

    def collect(path: str, depth: int) -> None:
        try:
            items = github_get_directory_listing(
                cloud, path, branch, repo_target=repo_target, workflow=workflow
            ) or []
        except Exception:
            return
        for item in items:
            item_path = str((item or {}).get("path") or "").strip("/")
            item_type = str((item or {}).get("type") or "")
            if not item_path:
                continue
            base = item_path.rsplit("/", 1)[-1]
            if item_type == "dir" and depth < 2 and not base.startswith("."):
                collect(item_path, depth + 1)
            elif item_type == "file" and item_path.endswith(_TEAMS_ENV_FOLDER_EXTS):
                folder_files.append(item_path)

    for directory in matched_dirs[:4]:
        collect(directory, 0)

    ordered_paths: list[str] = []
    for path in folder_files + token_named_files:
        if path not in ordered_paths:
            ordered_paths.append(path)

    entries: list[dict] = []
    write_paths: list[str] = []
    total_chars = 0
    for path in ordered_paths[:30]:
        if path.endswith((".tfvars", ".tfvars.json")):
            write_paths.append(path)
        if total_chars >= _TEAMS_ENV_EVIDENCE_TOTAL_CHARS:
            continue
        try:
            file_content = github_get_file_content(
                cloud, path, branch, repo_target=repo_target, workflow=workflow
            ) or ""
        except Exception:
            continue
        snippet = str(file_content)[:_TEAMS_ENV_EVIDENCE_PER_FILE_CHARS]
        entries.append({
            "path": path,
            "content": snippet,
            "reason": "target environment folder file (live GitHub) — the environment's full contents; infer flags, wiring and conventions here",
        })
        total_chars += len(snippet)
    debug["files"] = len(entries)
    return entries, write_paths, debug

def _teams_definition_root_evidence(
    cloud: str,
    repo_target: str,
    workflow: str,
    branch: str,
    selected_path: str,
) -> tuple[list[dict], list[str]]:
    """Files sitting NEXT TO the selected definition file (its directory,
    non-recursive). The sibling variables file that declares the *_enabled
    flags lives here; it is evidence AND an allowed append target so the new
    flag's variable declaration is APPENDED to it — never a new file."""
    selected_norm = str(selected_path or "").strip().strip("/")
    directory = selected_norm.rsplit("/", 1)[0] if "/" in selected_norm else ""
    entries: list[dict] = []
    write_paths: list[str] = []
    try:
        items = github_get_directory_listing(
            cloud, directory, branch, repo_target=repo_target, workflow=workflow
        ) or []
    except Exception:
        return entries, write_paths
    total_chars = 0
    for item in items:
        item_path = str((item or {}).get("path") or "").strip("/")
        item_type = str((item or {}).get("type") or "")
        if item_type != "file" or not item_path.endswith(".tf") or item_path == selected_norm:
            continue
        if total_chars >= _TEAMS_ENV_EVIDENCE_TOTAL_CHARS:
            break
        try:
            file_content = github_get_file_content(
                cloud, item_path, branch, repo_target=repo_target, workflow=workflow
            ) or ""
        except Exception:
            continue
        snippet = str(file_content)[:_TEAMS_ENV_EVIDENCE_PER_FILE_CHARS]
        entries.append({
            "path": item_path,
            "content": snippet,
            "reason": "definition-root sibling file (live GitHub) — variable declarations and shared locals for the selected pattern live here",
        })
        total_chars += len(snippet)
        base_name = item_path.rsplit("/", 1)[-1].lower()
        if base_name.startswith("variables") or re.search(r'variable\s+"[a-z0-9_]*_enabled"', snippet):
            write_paths.append(item_path)
    return entries, write_paths

def _teams_environment_evidence(
    cloud: str,
    repo_target: str,
    workflow: str,
    branch: str,
    scope_root: str,
    selected_path: str,
) -> tuple[list[dict], list[str]]:
    """Read every Terraform/value file in the resolved environment scope from
    live GitHub so the agent can infer the full workflow (where instances are
    defined, where enable flags are set, how values are wired) without asking
    the user — the Teams equivalent of the VS Code workspace scan.

    Returns (environment_files, companion_value_paths): bounded structured
    evidence entries, and the scope's *.tfvars paths which become additional
    allowed write targets for flag wiring."""
    scope = str(scope_root or "").strip().strip("/")
    selected_norm = str(selected_path or "").strip().strip("/")
    if not scope and "/" in selected_norm:
        scope = selected_norm.rsplit("/", 1)[0]
    files: list[dict] = []
    value_paths: list[str] = []
    if not scope:
        return files, value_paths

    def _walk(path: str, depth: int) -> list[str]:
        try:
            items = github_get_directory_listing(
                cloud, path, branch, repo_target=repo_target, workflow=workflow
            ) or []
        except Exception:
            return []
        found: list[str] = []
        for item in items:
            item_path = str((item or {}).get("path") or "").strip("/")
            item_type = str((item or {}).get("type") or "")
            if not item_path:
                continue
            if item_type == "dir" and depth < 2:
                found.extend(_walk(item_path, depth + 1))
            elif item_path.endswith((".tf", ".tfvars")):
                found.append(item_path)
            if len(found) >= _TEAMS_ENV_EVIDENCE_MAX_FILES:
                break
        return found

    total_chars = 0
    for file_path in _walk(scope, 0)[:_TEAMS_ENV_EVIDENCE_MAX_FILES]:
        if file_path.endswith(".tfvars"):
            value_paths.append(file_path)
        if file_path == selected_norm:
            continue  # the selected file already ships in full via matched_files
        if total_chars >= _TEAMS_ENV_EVIDENCE_TOTAL_CHARS:
            continue
        try:
            file_content = github_get_file_content(
                cloud, file_path, branch, repo_target=repo_target, workflow=workflow
            ) or ""
        except Exception:
            continue
        snippet = str(file_content)[:_TEAMS_ENV_EVIDENCE_PER_FILE_CHARS]
        files.append({
            "path": file_path,
            "content": snippet,
            "reason": "environment scope file (live GitHub) — infer workflow, wiring and flag placement from these",
        })
        total_chars += len(snippet)

    # Tier fallback: hub layouts often keep the enable flags one directory
    # above the resolved scope (e.g. vars/sbx/tier.tfvars beside
    # vars/sbx/<env>/). If the scope itself yielded no value files, scan the
    # parent directory for *.tfvars so flag placement is always inferable.
    if not value_paths and "/" in scope:
        parent = scope.rsplit("/", 1)[0]
        for file_path in _walk(parent, 1):
            if not file_path.endswith(".tfvars") or file_path in value_paths:
                continue
            value_paths.append(file_path)
            if total_chars >= _TEAMS_ENV_EVIDENCE_TOTAL_CHARS:
                continue
            try:
                file_content = github_get_file_content(
                    cloud, file_path, branch, repo_target=repo_target, workflow=workflow
                ) or ""
            except Exception:
                continue
            snippet = str(file_content)[:_TEAMS_ENV_EVIDENCE_PER_FILE_CHARS]
            files.append({
                "path": file_path,
                "content": snippet,
                "reason": "parent-tier value file (live GitHub) — enable flags for this environment may be set here",
            })
            total_chars += len(snippet)
    return files, value_paths

def _build_selected_infra_modification_context_base(pending_selection: dict, selected_index: int) -> dict:
    base = pending_selection.get("existing_infra_context") or {}
    candidates = base.get("matched_files") or []
    if selected_index < 0 or selected_index >= len(candidates):
        raise ValueError("Invalid modification target selection.")
    selected = dict(candidates[selected_index])
    cloud = base.get("cloud") or pending_selection.get("cloud")
    workflow = base.get("workflow") or pending_selection.get("workflow")
    repo_target = base.get("repo_target") or normalize_repo_target(cloud, workflow=workflow)
    branch = base.get("context_ref") or github_base_branch_for_cloud(cloud, repo_target=repo_target, workflow=workflow)
    selected_path = (selected.get("path") or "").strip()
    if not selected_path:
        raise ValueError("Selected modification target did not include a path.")
    content = github_get_file_content(cloud, selected_path, branch, repo_target=repo_target, workflow=workflow)
    if not content:
        raise ValueError(f"The selected file could not be read from GitHub: {selected_path}")
    selected["content"] = content
    selected["matched_blocks"] = _matched_blocks_for_prompt(content, base.get("search_terms") or [])
    selected["selected_by_user"] = True
    context = {
        "source": "backend_existing_infra_code_match",
        "selection_state": "selected",
        "cloud": cloud,
        "repo_target": repo_target,
        "workflow": workflow,
        "repo_full_name": base.get("repo_full_name") or "",
        "context_ref": branch,
        "search_terms": base.get("search_terms") or [],
        "selected_path": selected_path,
        "matched_files": [selected],
        "matched_file_paths": [selected_path],
        "instructions": [
            "This is the user-selected existing infrastructure target.",
            "Use this selected file content as the primary source of truth for the change.",
            "environment_files contains every Terraform/value file in the resolved environment scope, read from live GitHub — the Teams equivalent of the VS Code workspace. Infer the full workflow from them (where instances are defined, where enable flags are set, how values are wired) and answer placement/wiring questions yourself. Never ask the user for file contents, paths, or flag locations.",
            "When the repository pattern gates instances with a var.<name>_enabled style flag assigned in a tfvars value file, ALSO return that tfvars file (complete final content, every existing line preserved) with the new flag assignment added, alongside the definition file. companion_write_paths lists the value files you may write.",
            "MANDATORY CREATION/DISABLE PROCEDURE — follow these rules in this exact order, no manual intervention: RULE 1 (resource name does NOT exist): add the definition in the existing file that holds the similar resources (copy the nearest sibling's naming convention, wiring, and structure exactly). THEN check whether this resource family uses a boolean flag mechanism anywhere in the evidence (create_*/enable_*/*_enabled in the environment value files or sibling environments) — if it does, also enable it via that flag system and return the tfvars file with the new flag set true. If NO such flag exists anywhere in the evidence for this resource family, the definition-file append IS the whole change — do not invent a flag, do not ask about a flag, and do not ask for any file or path; every fact needed is already in the supplied evidence. When the repo stores concrete values separately (a tfvars/values file), still add the matching values entry there even when no flag is involved, mirroring the nearest existing sibling instance's values exactly. RULE 2 (resource with that name DOES exist — enabled): return empty files[] with ONE question offering (a) modify/update the existing resource's configuration, or (b) create the resource under another name (suggest one matching repo naming style); on 'modify' run the modification workflow, on a new name run RULE 1 with that name. If the definition exists but its flag is absent/false, the creation IS the flag change: return only the tfvars edit, no duplicate definition, no question. RULE 3 (disable request): find the existing flag inside the environment's value files and set it to false — nothing else. Never ask for a tfvars path or file contents; every environment value file is supplied in environment_files, and if none matched, say so plainly instead of asking.",
            "FLAG FILE DISCOVERY (MANDATORY, BOTH FILES ALWAYS): environment feature flags live in the environment folder's values files — hub.tfvars first, then tier.tfvars, then common.tfvars (shared across environments), all read from live GitHub into environment_files. A creation response that returns only the definition file is INCOMPLETE: every creation MUST return the values file too, with the new <name>_enabled = true placed beside the sibling *_enabled assignments in their exact format. Never ask where to set a flag. The backend independently verifies the flag against the actual commit branch and enables it there if the generation omitted it — but a definition-only response is still a contract violation.","NEW FLAG DECLARATIONS ARE APPENDS: when RULE 1 introduces a new <name>_enabled flag, its variable declaration is APPENDED to the existing variables file that already declares the sibling *_enabled variables (that file is in the evidence and in companion_write_paths). NEVER create a new .tf file when the siblings live in existing files — new-file output for this pattern is rejected by the backend. The complete write set for a flag-gated creation is exactly: the definition file (new sibling entry), the existing variables file (new variable declaration appended), and the environment values file (flag = true).",
            "NEVER ASK PERMISSION for the flag step: when the definition exists and the flag is absent or false, generate the flag change immediately — \"Proceed to enable ...?\" style questions are forbidden; the only legal exists-question is the RULE-2 modify-or-new-name choice when the flag is already true.",
            "In analysis, describe the inferred workflow: the definition file and its pattern, the flag/value file and the exact assignment added or changed, which sibling entry you copied, and which ladder rungs supplied each value.",
        ],
    }
    try:
        environment_files, companion_value_paths = _teams_environment_evidence(
            cloud,
            repo_target,
            workflow,
            branch,
            base.get("scope_root") or "",
            selected_path,
        )
    except Exception as evidence_error:
        environment_files, companion_value_paths = [], []
        context["environment_evidence_error"] = str(evidence_error)
    # Repo-wide environment resolution: the definitions hub and the
    # environment's value files can live in different subtrees, so resolve
    # the environment NAMED IN THE PROMPT across the whole repository and
    # merge its value files into the evidence and write targets.
    prompt_text = str(pending_selection.get("original_prompt") or "")
    env_debug: dict = {}
    try:
        env_value_files, env_value_paths, env_debug = _teams_locate_environment_value_files(
            prompt_text, cloud, repo_target, workflow, branch
        )
    except Exception as env_error:
        env_value_files, env_value_paths = [], []
        env_debug = {"error": str(env_error)}
    known_paths = {entry.get("path") for entry in environment_files}
    for entry in env_value_files:
        if entry.get("path") not in known_paths:
            environment_files.append(entry)
            known_paths.add(entry.get("path"))
    for path in env_value_paths:
        if path not in companion_value_paths:
            companion_value_paths.append(path)

    # Whole-environment-folder evidence: every file (any type) inside the
    # directory whose name matches the environment named in the prompt.
    try:
        folder_entries, folder_write_paths, folder_debug = _teams_environment_folder_evidence(
            prompt_text, cloud, repo_target, workflow, branch
        )
    except Exception as folder_error:
        folder_entries, folder_write_paths = [], []
        folder_debug = {"error": str(folder_error)}
    env_debug["folder"] = folder_debug
    for entry in folder_entries:
        if entry.get("path") not in known_paths:
            environment_files.append(entry)
            known_paths.add(entry.get("path"))
    for path in folder_write_paths:
        if path not in companion_value_paths:
            companion_value_paths.append(path)

    # Definition-root siblings: the variables file declaring the *_enabled
    # flags sits next to the definition file and must be an append target.
    try:
        root_entries, root_write_paths = _teams_definition_root_evidence(
            cloud, repo_target, workflow, branch, selected_path
        )
    except Exception:
        root_entries, root_write_paths = [], []
    for entry in root_entries:
        if entry.get("path") not in known_paths:
            environment_files.append(entry)
            known_paths.add(entry.get("path"))
    for path in root_write_paths:
        if path not in companion_value_paths:
            companion_value_paths.append(path)

    if environment_files:
        context["environment_files"] = environment_files
    if companion_value_paths:
        context["companion_write_paths"] = companion_value_paths
    context["environment_evidence_summary"] = {
        "scope_root": base.get("scope_root") or "",
        "derived_from_selected_path": not (base.get("scope_root") or ""),
        "environment_file_count": len(environment_files),
        "value_file_paths": companion_value_paths,
        "environment_resolver": env_debug,
    }
    if not companion_value_paths:
        context["environment_value_files_missing"] = (
            "No value files matched the environment named in the prompt "
            f"(tokens searched: {', '.join(env_debug.get('tokens') or []) or 'none'}). "
            "State this plainly instead of asking the user for a path."
        )
    logging.info(
        "Teams environment evidence: scope=%s files=%s value_files=%s resolver=%s selected=%s",
        base.get("scope_root") or "(derived)",
        len(environment_files),
        companion_value_paths,
        env_debug,
        selected_path,
    )
    return context


def enforce_modification_uses_backend_matched_files_stage1(agent_result: dict, retrieved_value_context: list | None) -> dict:
    """Keep true modifications scoped to the backend-selected file set.

    Teams intentionally routes ordinary create/add requests through
    ``*_infra_modification`` when the new resource must be appended to an
    existing resource-family file.  Those requests are *creation* requests,
    not single-file modifications: Azure object-backed creation can require
    the selected definition file plus variables.tf and the target environment
    tfvars file.  The old guard treated that complete write-set as an illegal
    modification and surfaced ``Modification output can only edit...`` after
    the user had already selected a branch.

    For Teams creation, companion_write_paths are therefore first-class write
    targets.  We also canonicalize basename-only agent paths (for example
    ``variables.tf``) to the unique repo-relative allowed path supplied by the
    backend evidence.  This preserves the safety boundary without forcing the
    model to reproduce a long directory prefix exactly.
    """
    if not isinstance(agent_result, dict):
        return agent_result
    if (agent_result.get("workflow") or "").strip() not in INFRA_MODIFICATION_WORKFLOWS:
        return agent_result

    context = _get_backend_existing_infra_context(retrieved_value_context)
    if not _backend_existing_infra_context_is_selected(context):
        raise ValueError("Modification workflow requires a user-selected backend_existing_infra_code_match target before generation.")

    allowed = {
        (path or "").strip().strip("/")
        for path in (context.get("matched_file_paths") or [])
        if path
    }
    allowed |= {
        (path or "").strip().strip("/")
        for path in (context.get("companion_write_paths") or [])
        if path
    }

    active = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    effective_prompt = str(
        active.get("effective_prompt")
        or agent_result.get("user_prompt")
        or ""
    ).strip()
    teams_creation = bool(
        active.get("active")
        and _teams_is_existing_invocation_creation(effective_prompt)
    )

    # The environment evidence is repository-grounded and is useful for path
    # canonicalization, but only creation workflows may expand the write set
    # beyond the explicitly selected file + backend-declared companions.
    if teams_creation:
        for item in context.get("environment_files") or []:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "").strip().strip("/")
            if not path:
                continue
            base = path.rsplit("/", 1)[-1].lower()
            if path.endswith((".tfvars", ".tfvars.json")) or base.startswith("variables"):
                allowed.add(path)

    basename_index: dict[str, list[str]] = {}
    for path in sorted(allowed):
        basename_index.setdefault(path.rsplit("/", 1)[-1], []).append(path)

    returned: set[str] = set()
    for file_data in (agent_result.get("files") or []):
        if not isinstance(file_data, dict):
            continue
        raw_name = str(file_data.get("filename") or file_data.get("path") or "").strip()
        normalized = normalize_iac_relative_path(raw_name, allow_tfvars=True).strip("/")
        if normalized not in allowed:
            candidates = basename_index.get(normalized.rsplit("/", 1)[-1], [])
            if len(candidates) == 1:
                normalized = candidates[0]
                file_data["filename"] = normalized
                if "path" in file_data:
                    file_data["path"] = normalized
        returned.add(normalized)

    invalid = sorted(path for path in returned if path not in allowed)
    if invalid:
        kind = "creation write-set" if teams_creation else "modification"
        raise ValueError(
            f"Teams {kind} output contains a path outside the backend-grounded target set. "
            f"Invalid path(s): {', '.join(invalid)}. Allowed path(s): {', '.join(sorted(allowed))}."
        )
    return agent_result
enforce_modification_uses_backend_matched_files = enforce_modification_uses_backend_matched_files_stage1


def commit_terraform_files_to_repo(
    agent_result: dict,
    prompt: str,
    thread_id: str,
    jira_ticket: Optional[str] = None,
    ticket_link: Optional[str] = None,
    ticket_title: Optional[str] = None,
):
    if (
        normalize_cloud(agent_result.get("cloud")) == "azure"
        and (agent_result.get("workflow") or "").strip() == "azure_module_repo_population"
    ):
        return commit_azure_module_repo_population_files(
            agent_result=agent_result,
            prompt=prompt,
            thread_id=thread_id,
            jira_ticket=jira_ticket,
            ticket_link=ticket_link,
            ticket_title=ticket_title,
        )

    cloud = normalize_cloud(agent_result["cloud"])
    workflow = agent_result.get("workflow")
    repo_target = normalize_repo_target(
        cloud,
        repo_target=agent_result.get("repo_target"),
        workflow=workflow
    )

    title = agent_result["title"]
    summary = agent_result["summary"]
    files = agent_result["files"]

    validate_azure_consumer_two_file_payload_for_commit(agent_result)

    jira_ticket = (jira_ticket or "").strip().upper()
    ticket_link = (ticket_link or "").strip()
    ticket_title = (ticket_title or "").strip()

    state = get_or_create_thread_pr_state(
        thread_id,
        cloud,
        repo_target=repo_target,
        workflow=workflow,
        prompt=prompt,
    )
    folder = state["folder"]
    branch_name = state["branch"]
    created_new_pr = False

    existing_pr = github_find_pr_by_branch(cloud, branch_name, state="open", repo_target=repo_target, workflow=workflow)
    branch_exists = github_branch_exists(cloud, branch_name, repo_target=repo_target, workflow=workflow)

    if existing_pr:
        state["pr_number"] = existing_pr.get("number")
        state["pr_url"] = existing_pr.get("html_url")
        state["has_open_pr"] = True
    else:
        state["pr_number"] = None
        state["pr_url"] = None
        state["has_open_pr"] = False

        if not branch_exists:
            seed_branch = github_branch_seed_for_cloud(cloud, repo_target=repo_target, workflow=workflow)
            base_sha = github_get_base_branch_sha(cloud, seed_branch, repo_target=repo_target, workflow=workflow)
            github_create_branch(cloud, branch_name, base_sha, repo_target=repo_target, workflow=workflow)

    committed_files = []

    if cloud == "aws" and not state.get("environment_path"):
        aws_env_path, aws_env_error = resolve_aws_environment_path(
            prompt=prompt,
            retrieved_value_context=[],
            current_environment_path=None,
        )
        if aws_env_error:
            raise ValueError(aws_env_error)
        if aws_env_path:
            state["environment_path"] = aws_env_path

    for file_data in files:
        relative_tf_path = normalize_agent_relative_tf_path(file_data["filename"], cloud)

        if relative_tf_path.startswith("terraform/"):
            repo_path = relative_tf_path
        elif cloud == "aws" and state.get("environment_path"):
            repo_path = safe_join_under_folder(state["environment_path"], relative_tf_path)
        else:
            repo_path = safe_join_under_folder(folder, relative_tf_path)

        write_result = github_put_file_if_changed(
            cloud=cloud,
            path=repo_path,
            content=file_data["content"],
            branch=branch_name,
            commit_message=f"[{cloud.upper()}] Update Terraform file {repo_path}",
            repo_target=repo_target,
            workflow=workflow,
        )
        if write_result["changed"]:
            committed_files.append(repo_path)

        if cloud == "aws" and repo_path.startswith("terraform/") and not repo_path.startswith(f"{AWS_MODULES_ROOT}/"):
            state["environment_path"] = repo_path.rsplit("/", 1)[0]

    if state["pr_number"] is None:
        if not committed_files:
            raise RuntimeError(
                "No Terraform file changes were detected, so no PR was created. "
                "Please make a real infrastructure change and try again."
            )

        pr_body = build_pr_body(
            user_prompt=prompt,
            ticket_link=ticket_link,
            ticket_number=jira_ticket,
            ticket_title=ticket_title,
            cloud=cloud,
            folder=state.get("environment_path") if cloud == "aws" and state.get("environment_path") else folder,
            thread_id=thread_id,
            branch_cycle=state.get("cycle"),
            files=committed_files,
            summary=summary,
        )

        pr = github_create_pull_request(
            cloud=cloud,
            branch_name=branch_name,
            title=title,
            body=pr_body,
            repo_target=repo_target,
            workflow=workflow,
        )

        state["pr_number"] = pr.get("number")
        state["pr_url"] = pr.get("html_url")
        state["has_open_pr"] = True
        created_new_pr = True

        try:
            trigger_test_branch_pipeline_for_pr(
                repo_owner=GITHUB_OWNER,
                repo_name=github_repo_for_cloud(cloud, repo_target=repo_target, workflow=workflow),
                pr_number=int(state["pr_number"]),
                source_branch=branch_name,
                target_branch=github_base_branch_for_cloud(cloud, repo_target=repo_target, workflow=workflow),
            )
        except Exception as trigger_error:
            print(f"Failed to trigger Azure pipeline for PR {state['pr_number']}: {trigger_error}")
    elif committed_files:
        try:
            trigger_test_branch_pipeline_for_pr(
                repo_owner=GITHUB_OWNER,
                repo_name=github_repo_for_cloud(cloud, repo_target=repo_target, workflow=workflow),
                pr_number=int(state["pr_number"]),
                source_branch=branch_name,
                target_branch=github_base_branch_for_cloud(cloud, repo_target=repo_target, workflow=workflow),
            )
        except Exception as trigger_error:
            print(f"Failed to trigger Azure pipeline for PR {state['pr_number']}: {trigger_error}")

    set_last_selected_cloud(thread_id, cloud)

    if cloud == "azure" and workflow == "azure_module_repo_creation":
        state["workflow"] = workflow
        state["repo_target"] = repo_target
        state["original_prompt"] = prompt
        state["ticket_number"] = jira_ticket
        state["ticket_link"] = ticket_link
        state["ticket_title"] = ticket_title

        for key in (
            "target_module_repo_full_name",
            "target_module_repo_name",
            "module_repo_full_name",
            "module_repo_name",
            "repo_full_name",
            "repo_name",
        ):
            if agent_result.get(key):
                state[key] = agent_result.get(key)

    action = "created" if created_new_pr else ("updated" if committed_files else "noop")
    message = (
        "PR created successfully."
        if created_new_pr else
        "Existing PR updated successfully."
        if committed_files else
        "No Terraform changes were detected, so no new commit was added."
    )

    return {
        "cloud": cloud,
        "repo_target": repo_target,
        "state_bucket": state.get("state_bucket"),
        "folder": state.get("environment_path") if cloud == "aws" and state.get("environment_path") else folder,
        "branch": branch_name,
        "files": committed_files,
        "pr_url": state["pr_url"],
        "pr_number": state["pr_number"],
        "pr_title": title,
        "jira_ticket": jira_ticket,
        "ticket_link": ticket_link,
        "ticket_title": ticket_title,
        "message": message,
        "action": action,
        "state": state,
        "target_module_repo_full_name": agent_result.get("target_module_repo_full_name") or agent_result.get("module_repo_full_name") or agent_result.get("repo_full_name"),
        "target_module_repo_name": agent_result.get("target_module_repo_name") or agent_result.get("module_repo_name") or agent_result.get("repo_name"),
    }

def github_authenticated_login() -> str:
    """Return the login associated with the active OAuth token."""
    response = requests.get(f"{GITHUB_API}/user", headers=github_headers(), timeout=30)
    if not response.ok:
        raise _github_request_error(response, "Reading the authenticated GitHub user")
    login = str((response.json() or {}).get("login") or "").strip()
    if not login:
        raise RuntimeError("GitHub did not return the authenticated user login.")
    return re.sub(r"[^A-Za-z0-9-]+", "-", login).strip("-").lower()


def _commit_terraform_files_to_branch_for_teams_base(
    agent_result: dict,
    prompt: str,
    thread_id: str,
) -> dict:
    """Create/update a user-owned GitHub branch without opening a PR."""
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
        thread_id, cloud, repo_target=repo_target, workflow=workflow, prompt=prompt
    )
    folder = state["folder"]
    base_branch = github_resolve_base_branch_for_cloud(cloud, repo_target=repo_target, workflow=workflow)

    # GitHub App installation tokens represent Terrabot rather than a user.
    # Keep user attribution in the branch namespace using the Teams requester.
    requester_slug = (_ACTIVE_TEAMS_REQUESTER.get() or "terrabot").strip()
    branch_prefix = f"{requester_slug}/terrabot-{cloud}"

    # HARD FIX: this path previously ignored reuse_branch/force_new_branch
    # entirely and always reused (or recreated with the same name) the one
    # deterministic per-thread branch. That meant replying "no" to "create a
    # new branch?" was silently discarded and changes kept landing on the
    # existing branch. Honor the explicit choice the same way the v1 commit
    # path does.
    flow_context = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    reuse_branch = _teams_truthy(flow_context.get("reuse_branch"))
    force_new_branch = _teams_truthy(flow_context.get("force_new_branch"))
    requested_existing_branch = str(
        flow_context.get("existing_branch") or state.get("branch") or ""
    ).strip()

    branch_name = ""
    if (
        reuse_branch
        and not force_new_branch
        and requested_existing_branch
        and github_branch_exists(cloud, requested_existing_branch, repo_target=repo_target, workflow=workflow)
    ):
        # Explicit "yes, reuse the existing branch".
        branch_name = requested_existing_branch
        state["branch"] = branch_name
    elif force_new_branch:
        # Explicit "no" — always materialize a genuinely NEW branch from the
        # latest base branch. Never fall back to the old branch name/content.
        base_candidate = (
            (state.get("branch") or "").strip()
            or f"{branch_prefix}-{stable_thread_key(thread_id)}"
        )
        start_cycle = max(2, int(state.get("cycle") or 0) + 1)
        branch_name, cycle = _teams_unique_branch_name(
            cloud, base_candidate, repo_target, workflow, start_cycle=start_cycle,
        )
        state["cycle"] = cycle
        state["branch"] = branch_name
        state.pop("pr_number", None)
        state.pop("pr_url", None)
        state["has_open_pr"] = False
    else:
        # No explicit branch-continuity choice was supplied for this turn
        # (e.g. the very first generation on this thread) — preserve the
        # original deterministic single-branch-per-thread behavior.
        branch_name = (state.get("branch") or "").strip()
        if not branch_name or not branch_name.startswith(f"{branch_prefix}-"):
            branch_name = f"{branch_prefix}-{stable_thread_key(thread_id)}"
        state["branch"] = branch_name

    seed_branch = base_branch

    if not github_branch_exists(cloud, branch_name, repo_target=repo_target, workflow=workflow):
        base_sha = github_get_base_branch_sha(
            cloud, seed_branch, repo_target=repo_target, workflow=workflow
        )
        github_create_branch(
            cloud, branch_name, base_sha, repo_target=repo_target, workflow=workflow
        )

    if cloud == "aws" and not state.get("environment_path"):
        aws_env_path, aws_env_error = resolve_aws_environment_path(
            prompt=prompt, retrieved_value_context=[], current_environment_path=None
        )
        if aws_env_error:
            raise ValueError(aws_env_error)
        if aws_env_path:
            state["environment_path"] = aws_env_path

    committed_files = []
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
            commit_message=f"[{cloud.upper()}] Update Terraform file {repo_path}",
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
    state.update({
        "workflow": workflow,
        "repo_target": repo_target,
        "base_branch": base_branch,
        "original_prompt": prompt,
        "title": agent_result.get("title") or f"[{cloud.upper()}] Terraform changes",
        "summary": agent_result.get("summary") or "Terraform infrastructure changes",
        "files": committed_files,
        "teams_requester": _ACTIVE_TEAMS_REQUESTER_DISPLAY.get(),
        "branch_url": branch_url,
        "compare_url": compare_url,
        "has_open_pr": False,
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
        "state": state,
        "message": "Terraform changes were committed to a new GitHub branch.",
    }


def _create_teams_pull_request_from_branch_base(
    agent_result: dict,
    prompt: str,
    thread_id: str,
    jira_ticket: str,
    ticket_link: str,
    ticket_title: str = "",
) -> dict:
    """Open the PR only after branch creation and explicit Teams approval."""
    if ticket_link and not is_valid_jira_ticket_link(ticket_link):
        raise ValueError("The supplied Jira ticket link is invalid.")
    cloud = normalize_cloud(agent_result["cloud"])
    workflow = agent_result.get("workflow")
    repo_target = normalize_repo_target(cloud, str(agent_result.get("repo_target") or ""), workflow)
    bucket = state_bucket_for_target(cloud, repo_target, workflow)
    state = (THREAD_PR_STATE.get(thread_id) or {}).get(bucket) or {}
    branch_name = (state.get("branch") or "").strip()
    if not branch_name:
        raise RuntimeError("No Terrabot branch is available for this Teams conversation.")
    files = state.get("files") or []
    body = build_pr_body(
        user_prompt=prompt,
        ticket_link=ticket_link,
        ticket_number=jira_ticket,
        ticket_title=ticket_title,
        cloud=cloud,
        folder=state.get("environment_path") or state.get("folder") or "",
        thread_id=thread_id,
        branch_cycle=state.get("cycle"),
        files=files,
        summary=agent_result.get("summary") or state.get("summary") or "Terraform infrastructure changes",
    )
    pr = github_create_pull_request(
        cloud=cloud,
        branch_name=branch_name,
        title=agent_result.get("title") or state.get("title") or f"[{cloud.upper()}] Terraform changes",
        body=body,
        repo_target=repo_target,
        workflow=workflow,
    )
    state.update({
        "pr_number": pr.get("number"),
        "pr_url": pr.get("html_url"),
        "has_open_pr": True,
        "ticket_number": jira_ticket,
        "ticket_link": ticket_link,
        "ticket_title": ticket_title,
    })
    try:
        trigger_test_branch_pipeline_for_pr(
            repo_owner=GITHUB_OWNER,
            repo_name=github_repo_for_cloud(cloud, repo_target=repo_target, workflow=workflow),
            pr_number=int(pr.get("number")),
            source_branch=branch_name,
            target_branch=state.get("base_branch") or github_resolve_base_branch_for_cloud(cloud, repo_target=repo_target, workflow=workflow),
        )
    except Exception as trigger_error:
        print(f"Failed to trigger Azure pipeline for PR {pr.get('number')}: {trigger_error}")
    return {
        "cloud": cloud,
        "branch": branch_name,
        "branch_url": state.get("branch_url"),
        "compare_url": state.get("compare_url"),
        "pr_number": pr.get("number"),
        "pr_url": pr.get("html_url"),
        "message": "Pull request created successfully.",
    }


def parse_agent_output(agent_text: str) -> dict:
    data = extract_json_from_text(agent_text)

    mode = (data.get("mode") or "").strip().lower()
    if mode and mode != "infra":
        raise ValueError("Agent response mode must be 'infra' for infrastructure requests.")

    cloud = safe_normalize_cloud(data.get("cloud", ""))
    if not cloud:
        raise ValueError("Agent response must contain cloud='aws' or cloud='azure'.")

    workflow = (data.get("workflow") or "").strip()
    repo_target = normalize_repo_target(
        cloud,
        repo_target=data.get("repo_target"),
        workflow=workflow,
    )

    files = data.get("files", [])
    if not isinstance(files, list) or not files:
        raise ValueError("Agent response must contain a non-empty 'files' array.")

    cleaned_files = []

    for item in files:
        if not isinstance(item, dict):
            raise ValueError("Each file entry must be an object.")

        raw_filename = item.get("filename") or item.get("path") or "main.tf"

        if cloud == "azure" and workflow == "azure_module_repo_population":
            filename = normalize_azure_module_repo_population_path(raw_filename)
        else:
            filename = normalize_agent_relative_tf_path(raw_filename, cloud)
        content = item.get("content", "")

        if not isinstance(content, str) or not content.strip():
            raise ValueError(f"Invalid content for file: {filename}")

        cleaned_files.append({
            "filename": filename,
            # Teams branch writes must transport Foundry's complete file exactly.
            # Do not trim, normalize, merge, or otherwise rewrite generated HCL.
            "content": content if (_ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}).get("active") else content.strip() + "\n",
        })

    if cloud == "aws" and workflow == "aws_module_creation":
        try:
            cleaned_files = validate_aws_module_creation_payload(
                cleaned_files,
                user_prompt=data.get("user_prompt") or data.get("summary") or "",
            )
        except ModuleVariableValuesRequired as variable_error:
            cleaned_files = variable_error.files
            data["_module_variable_values_required"] = True
            data["_module_variable_issues"] = variable_error.issues

    if cloud == "aws" and workflow not in {"aws_module_creation", "aws_infra_modification"} and (workflow == "aws_module_consumer" or repo_target == "tf-devops"):
        for file_data in cleaned_files:
            filename = file_data["filename"]
            if filename.startswith(("terraform/modules/", "modules/")):
                raise ValueError(
                    "AWS module-consumer requests must not create or modify module implementation files under terraform/modules. "
                    "Use only verified existing modules from tf-devops/terraform/modules."
                )

    azure_module_repo_name_from_content = ""

    if cloud == "azure" and workflow == "azure_module_repo_creation":
        if repo_target != "vena_repos":
            raise ValueError("azure_module_repo_creation must use repo_target='vena_repos'.")

        if len(cleaned_files) != 1:
            raise ValueError("azure_module_repo_creation must return exactly one .tf file.")

        filename = cleaned_files[0]["filename"]

        if "/" in filename:
            raise ValueError(
                "For azure_module_repo_creation, return only one root-level .tf file that defines the requested repository."
            )

        if not re.fullmatch(r"[A-Za-z0-9_.-]+\.tf", filename):
            raise ValueError("Repo creation file must be a valid root-level .tf file.")

        forbidden_creation_names = {
            "main.tf",
            "variables.tf",
            "outputs.tf",
            "versions.tf",
            "locals.tf",
            "README.md.tf",
            "repo_name.txt.tf",
        }

        if filename in forbidden_creation_names:
            raise ValueError(
                "azure_module_repo_creation must create only the vena_repos module repository definition file."
            )

        content = cleaned_files[0]["content"]
        content_lower = content.lower()

        forbidden_patterns = [
            'resource "azurerm_',
            'provider "azurerm"',
            'variable "',
            'output "',
            "locals {",
            "terraform {",
            'resource "github_repository"',
        ]

        if any(pattern in content_lower for pattern in forbidden_patterns):
            raise ValueError(
                "azure_module_repo_creation must use module '../modules/repo' only and must not contain Azure resources, variables, outputs, providers, terraform blocks, locals, or github_repository resources."
            )

        if 'source = "../modules/repo"' not in content_lower:
            raise ValueError(
                'azure_module_repo_creation must define the repository using source = "../modules/repo".'
            )

        if not re.search(r'module\s+"[A-Za-z_][A-Za-z0-9_]*"\s*\{', content):
            raise ValueError(
                'azure_module_repo_creation must use module "<terraform_safe_name>" syntax.'
            )

        repo_name_match = re.search(
            r'^\s*name\s*=\s*"([A-Za-z0-9_.-]+)"',
            content,
            re.MULTILINE,
        )
        repo_name = repo_name_match.group(1).strip() if repo_name_match else ""
        azure_module_repo_name_from_content = sanitize_azure_module_repo_name(repo_name)

        if not azure_module_repo_name_from_content:
            raise ValueError(
                'azure_module_repo_creation must set name = "<valid-github-repo-name>".'
            )

        _validate_azure_repo_merge_commit_settings(content)

        if not data.get("target_module_repo_name"):
            data["target_module_repo_name"] = azure_module_repo_name_from_content
        if not data.get("target_module_repo_full_name"):
            data["target_module_repo_full_name"] = f"{GITHUB_OWNER}/{azure_module_repo_name_from_content}"

    if cloud == "azure" and workflow == "azure_module_repo_population":
        for file_data in cleaned_files:
            file_data["filename"] = normalize_azure_module_repo_population_path(
                file_data["filename"]
            )

    title = data.get("title") or f"Update {cloud} Terraform"
    summary = data.get("summary") or f"Terraform update for {cloud}"

    if cloud not in title.lower():
        title = f"[{cloud.upper()}] {title}"

    parsed = {
        "cloud": cloud,
        "repo_target": repo_target,
        "state_bucket": state_bucket_for_target(cloud, repo_target, workflow),
        "title": title,
        "summary": summary,
        "files": cleaned_files,
        "mode": "infra",
        "workflow": workflow,
    }

    for optional_key in [
        "target_module_repo_full_name",
        "target_module_repo_name",
        "module_repo_full_name",
        "module_repo_name",
        "repo_full_name",
        "repo_name",
    ]:
        if data.get(optional_key):
            parsed[optional_key] = data.get(optional_key)

    if cloud == "azure" and workflow == "azure_module_repo_creation" and azure_module_repo_name_from_content:
        parsed.setdefault("target_module_repo_name", azure_module_repo_name_from_content)
        parsed.setdefault("target_module_repo_full_name", f"{GITHUB_OWNER}/{azure_module_repo_name_from_content}")

    return parsed

def _get_verified_azure_module_source_url(retrieved_module_context: list) -> str:
    for item in retrieved_module_context or []:
        if not isinstance(item, dict):
            continue
        source = (item.get("module_source_url") or "").strip()
        if source:
            return source
    return ""


