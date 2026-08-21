from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared_code.terrabot_core_typing import (
        AZURE_TFVARS_AUTOFILL_EXCLUDED_ROOTS,
        PENDING_AZURE_CONSUMER_VALUE_SELECTIONS,
        PENDING_AZURE_NEW_CONSUMER_FILE_CONFIRMATIONS,
        _azure_consumer_module_name_from_repo,
        _dedupe_preserving_order,
        _extract_top_level_tf_blocks,
        _repair_unclosed_variables_tf_content_for_write,
        cloud_root_dir,
        extract_first_balanced_json_object,
        find_tf_azure_hub_module_invocation_file_by_source,
        github_branch_exists,
        github_branch_seed_for_cloud,
        github_get_file_content,
        github_list_tf_files_recursive,
        hashlib,
        json,
        normalize_agent_relative_tf_path,
        normalize_cloud,
        normalize_repo_target,
        normalize_yes_no_reply,
        re,
        recover_thread_pr_state,
        safe_normalize_cloud,
    )

AZURE_DEFAULT_TFVARS_BY_ENV = {
    "npr": "vars/npr/tier.tfvars",
    "prd": "vars/prd/tier.tfvars",
    "sbx": "vars/sbx/tier.tfvars",
    "common": "vars/common.tfvars",
}


def _get_primary_azure_module_context(retrieved_module_context: list) -> dict:
    for item in retrieved_module_context or []:
        if not isinstance(item, dict):
            continue
        if (item.get("module_source_url") or "").strip():
            return item
    return {}


def _get_azure_consumer_routing_context(retrieved_value_context: list) -> dict:
    for item in retrieved_value_context or []:
        if not isinstance(item, dict):
            continue
        if item.get("source") in {
            "backend_tf_azure_hub_source_match",
            "backend_new_azure_consumer_routing",
        }:
            return item
    return {}


def _azure_consumer_value_selection_confirmed(retrieved_value_context: list) -> bool:
    for item in retrieved_value_context or []:
        if isinstance(item, dict) and item.get("source") == "backend_azure_consumer_value_selection" and item.get("confirmed"):
            return True
    return False


def _with_azure_consumer_value_selection_confirmation(retrieved_value_context: list, user_reply: str) -> list[dict]:
    result = list(retrieved_value_context or [])
    result.append({
        "source": "backend_azure_consumer_value_selection",
        "confirmed": True,
        "user_reply": user_reply or "use suggested values",
    })
    return result


def store_pending_azure_consumer_value_selection(
    thread_id: str,
    ticket_number: str,
    original_prompt: str,
    retrieved_module_context: list,
    retrieved_value_context: list,
    ticket_link: str = "",
    ticket_title: str = "",
):
    key = hashlib.sha1(
        f"{thread_id or 'no-thread'}::{ticket_number or ''}::azure-consumer-values::{original_prompt}".encode("utf-8")
    ).hexdigest()

    PENDING_AZURE_CONSUMER_VALUE_SELECTIONS[key] = {
        "thread_id": thread_id,
        "ticket_number": (ticket_number or "").strip().upper(),
        "original_prompt": original_prompt,
        "retrieved_module_context": list(retrieved_module_context or []),
        "retrieved_value_context": list(retrieved_value_context or []),
        "ticket_link": ticket_link or "",
        "ticket_title": ticket_title or "",
    }
    return key


def get_pending_azure_consumer_value_selection(thread_id: str, ticket_number: str):
    thread_id = str(thread_id or "")
    ticket_number = (ticket_number or "").strip().upper()

    for _, item in PENDING_AZURE_CONSUMER_VALUE_SELECTIONS.items():
        if str(item.get("thread_id") or "") == thread_id and (item.get("ticket_number") or "") == ticket_number:
            return item
    return None


def clear_pending_azure_consumer_value_selection(thread_id: str, ticket_number: str):
    thread_id = str(thread_id or "")
    ticket_number = (ticket_number or "").strip().upper()

    keys_to_delete = []
    for key, item in PENDING_AZURE_CONSUMER_VALUE_SELECTIONS.items():
        if str(item.get("thread_id") or "") == thread_id and (item.get("ticket_number") or "") == ticket_number:
            keys_to_delete.append(key)

    for key in keys_to_delete:
        PENDING_AZURE_CONSUMER_VALUE_SELECTIONS.pop(key, None)


def store_pending_azure_new_consumer_file_confirmation(
    thread_id: str,
    ticket_number: str,
    original_prompt: str,
    retrieved_module_context: list,
    retrieved_value_context: list,
    routing_context: dict,
    ticket_link: str = "",
    ticket_title: str = "",
):
    key = hashlib.sha1(
        f"{thread_id or 'no-thread'}::{ticket_number or ''}::azure-new-consumer-file::{original_prompt}".encode("utf-8")
    ).hexdigest()
    PENDING_AZURE_NEW_CONSUMER_FILE_CONFIRMATIONS[key] = {
        "thread_id": thread_id,
        "ticket_number": (ticket_number or "").strip().upper(),
        "original_prompt": original_prompt,
        "retrieved_module_context": list(retrieved_module_context or []),
        "retrieved_value_context": list(retrieved_value_context or []),
        "routing_context": dict(routing_context or {}),
        "ticket_link": ticket_link or "",
        "ticket_title": ticket_title or "",
    }
    return key


def get_pending_azure_new_consumer_file_confirmation(thread_id: str, ticket_number: str):
    thread_id = str(thread_id or "")
    ticket_number = (ticket_number or "").strip().upper()
    for _, item in PENDING_AZURE_NEW_CONSUMER_FILE_CONFIRMATIONS.items():
        if str(item.get("thread_id") or "") == thread_id and (item.get("ticket_number") or "") == ticket_number:
            return item
    return None


def clear_pending_azure_new_consumer_file_confirmation(thread_id: str, ticket_number: str):
    thread_id = str(thread_id or "")
    ticket_number = (ticket_number or "").strip().upper()
    keys_to_delete = []
    for key, item in PENDING_AZURE_NEW_CONSUMER_FILE_CONFIRMATIONS.items():
        if str(item.get("thread_id") or "") == thread_id and (item.get("ticket_number") or "") == ticket_number:
            keys_to_delete.append(key)
    for key in keys_to_delete:
        PENDING_AZURE_NEW_CONSUMER_FILE_CONFIRMATIONS.pop(key, None)


def _confirm_new_azure_consumer_file_routing_context(routing_context: dict) -> dict:
    confirmed = dict(routing_context or {})
    confirmed["source"] = "backend_new_azure_consumer_routing"
    confirmed["new_consumer_file_confirmed"] = True
    confirmed.pop("requires_new_consumer_file_confirmation", None)
    confirmed.pop("confirmation_source", None)
    return confirmed


def _cancel_new_azure_consumer_file_reply() -> str:
    return "Okay, I did not generate a new tf-azure-hub consumer file."


def build_azure_new_consumer_file_confirmation_reply(routing_context: dict) -> str:
    routing_context = routing_context or {}
    target_consumer = routing_context.get("target_consumer_filename") or ""
    target_tfvars = routing_context.get("target_tfvars_filename") or ""
    module_source = routing_context.get("module_source_url") or ""
    scanned_count = routing_context.get("scanned_tf_file_count") or 0
    lines = [
        "I searched every Terraform consumer file in tf-azure-hub for the selected module source and did not find an existing invocation.",
        "",
        f"Verified module source: `{module_source}`",
        f"tf-azure-hub .tf files scanned: {scanned_count}",
        "",
        "Do you want Terrabot to create a new tf-azure-hub consumer file for this module?",
        "",
        f"Proposed new consumer file: `{target_consumer}`",
        f"Variable values file: `{target_tfvars}`",
        "",
        "Reply `yes` to create the new consumer file, or `no` to cancel.",
    ]
    return "\n".join(lines)


def _azure_consumer_module_name_from_module_context(module_context: dict) -> str:
    module_context = module_context or {}
    repo_name = (
        module_context.get("repo_name")
        or module_context.get("target_module_repo_name")
        or "azure-module"
    )
    return _azure_consumer_module_name_from_repo(repo_name)


def _tf_azure_hub_file_exists(path: str, ref: str) -> bool:
    if not path or not path.endswith(".tf"):
        return False
    return github_get_file_content(
        "azure",
        path,
        ref,
        repo_target="tf-azure-hub",
        workflow="azure_consumer_generation",
    ) is not None


def _tf_azure_hub_tfvars_file_exists(path: str, ref: str) -> bool:
    if not path or not path.startswith("vars/") or not path.endswith(".tfvars"):
        return False
    return github_get_file_content(
        "azure",
        path,
        ref,
        repo_target="tf-azure-hub",
        workflow="azure_consumer_generation",
    ) is not None


def _first_existing_tf_azure_hub_tfvars_path(candidates: list[str], ref: str) -> str:
    for candidate in candidates or []:
        candidate = (candidate or "").strip().strip("/")
        if candidate and _tf_azure_hub_tfvars_file_exists(candidate, ref):
            return candidate
    return ""


def _explicit_tfvars_path_from_prompt(prompt: str) -> str:
    text = (prompt or "").strip().replace("\\", "/")
    match = re.search(r"(?<![A-Za-z0-9_./-])(vars/(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.tfvars)(?![A-Za-z0-9_./-])", text)
    return match.group(1).strip("`'\" ") if match else ""


def _azure_tfvars_file_kind_from_prompt(prompt: str) -> str:
    text = normalize_yes_no_reply(prompt)
    if re.search(r"(?<![a-z0-9])(dr|disaster recovery|failover|secondary)(?![a-z0-9])", text):
        return "dr"
    return "hub"


def _azure_exact_environment_tfvars_candidates(prompt: str) -> tuple[list[str], str]:
    text = normalize_yes_no_reply(prompt)
    kind = _azure_tfvars_file_kind_from_prompt(prompt)

    exact_env_roots = {
        "npr-int": "vars/npr/npr-int",
        "npr-stg": "vars/npr/npr-stg",
        "sbx-infra": "vars/sbx/sbx-infra",
        "prd-eu3": "vars/prd/prd-eu3",
        "prd-ca4": "vars/prd/prd-ca4",
        "prd-us5": "vars/prd/prd-us5",
        "prd-us6": "vars/prd/prd-us6",
    }

    for env_name, root in exact_env_roots.items():
        if re.search(rf"(?<![a-z0-9]){re.escape(env_name)}(?![a-z0-9])", text):
            # Exact hub environment folders use hub.tfvars by default, and dr.tfvars
            # only when the prompt explicitly asks for DR/failover/secondary.
            preferred = f"{root}/{kind}.tfvars"
            fallback = f"{root}/hub.tfvars" if kind == "dr" else f"{root}/dr.tfvars"
            return [preferred, fallback], env_name

    return [], ""


def _available_tf_azure_hub_consumer_filename(base_name: str, ref: str) -> str:
    base_name = re.sub(r"[^a-z0-9_]+", "_", (base_name or "azure_module").replace("-", "_").lower()).strip("_")
    if not base_name:
        base_name = "azure_module"
    candidates = [f"{base_name}.tf"]
    candidates.extend(f"{base_name}_{idx}.tf" for idx in range(2, 100))
    for candidate in candidates:
        if not _tf_azure_hub_file_exists(candidate, ref):
            return candidate
    raise ValueError(f"Could not find an available tf-azure-hub consumer filename for base name: {base_name}")


def _auto_tfvars_value_for_azure_input(input_name: str) -> str:
    name = (input_name or "").strip().lower()
    if not name:
        return "null"
    if _is_sensitive_variable_name(name):
        return "null"
    if name.startswith(("enable_", "create_", "has_", "is_", "use_")) or name.endswith(("_enabled", "_disabled", "_only")):
        return "false"
    if name.endswith(("_ids", "_names", "_list")):
        return "[]"
    if name.endswith(("_map", "_tags", "_settings")) or name in {"tags", "settings", "app_settings", "connection_strings"}:
        return "{}"
    if name.endswith(("_count", "_quota", "_size", "_number")):
        return "0"
    return '""'


def _auto_tfvars_assignments_for_new_consumer(module_context: dict) -> dict[str, str]:
    module_context = module_context or {}
    inputs = _dedupe_preserving_order(
        list(module_context.get("required_inputs_detected") or [])
        + list(module_context.get("inputs_detected") or [])
    )
    assignments = {}
    for input_name in inputs:
        safe_name = _terraform_safe_variable_name(input_name)
        if not safe_name or safe_name in AZURE_TFVARS_AUTOFILL_EXCLUDED_ROOTS:
            continue
        assignments[safe_name] = _auto_tfvars_value_for_azure_input(safe_name)
    return assignments


def build_new_azure_consumer_file_routing_context(
    prompt: str,
    thread_id: str,
    retrieved_module_context: list,
    retrieved_value_context: list,
    tf_file_count: int = 0,
    auto_confirm: bool = False,
) -> dict:
    module_context = _get_primary_azure_module_context(retrieved_module_context)
    module_source_url = (module_context.get("module_source_url") or "").strip()
    if not module_source_url:
        return {}
    context_ref = _get_azure_consumer_context_ref(thread_id)
    module_name = _azure_consumer_module_name_from_module_context(module_context)
    target_consumer_filename = _available_tf_azure_hub_consumer_filename(module_name, context_ref)
    target_tfvars_filename, azure_environment = resolve_azure_consumer_tfvars_path(
        prompt,
        retrieved_value_context,
        context_ref=context_ref,
    )
    existing_tfvars_content = github_get_file_content(
        "azure",
        target_tfvars_filename,
        context_ref,
        repo_target="tf-azure-hub",
        workflow="azure_consumer_generation",
    )
    if existing_tfvars_content is None:
        raise ValueError(
            f"The resolved tfvars file does not exist in tf-azure-hub: {target_tfvars_filename}. "
            "Azure consumer variable values must be added to an existing vars file."
        )
    common_tfvars_content = ""
    if target_tfvars_filename != "vars/common.tfvars":
        common_tfvars_content = github_get_file_content(
            "azure",
            "vars/common.tfvars",
            context_ref,
            repo_target="tf-azure-hub",
            workflow="azure_consumer_generation",
        ) or ""
    variables_tf_content = github_get_file_content(
        "azure",
        "variables.tf",
        context_ref,
        repo_target="tf-azure-hub",
        workflow="azure_consumer_generation",
    ) or ""
    source = "backend_new_azure_consumer_routing" if auto_confirm else "backend_new_azure_consumer_file_confirmation_required"
    routing_context = {
        "source": source,
        "repo_target": "tf-azure-hub",
        "context_ref": context_ref,
        "module_source_url": module_source_url,
        "module_repo_full_name": module_context.get("repo_full_name") or module_context.get("target_module_repo_full_name") or "",
        "target_consumer_filename": target_consumer_filename,
        "target_tfvars_filename": target_tfvars_filename,
        "azure_environment": azure_environment,
        "matched_module_name": "",
        "matched_module_source": "",
        "matched_module_block": "",
        "matched_invocation_count": 0,
        "match_type": "new_consumer_file",
        "match_score": 0,
        "existing_consumer_file_content": "",
        "existing_tfvars_file_content": existing_tfvars_content,
        "common_tfvars_file_content": common_tfvars_content,
        "variables_tf_file_content": variables_tf_content,
        "new_consumer_file": True,
        "new_consumer_file_confirmed": bool(auto_confirm),
        "requires_new_consumer_file_confirmation": not bool(auto_confirm),
        "scanned_tf_file_count": int(tf_file_count or 0),
        "auto_tfvars_assignments": _auto_tfvars_assignments_for_new_consumer(module_context),
    }
    routing_context["suggested_variable_values"] = build_azure_variable_value_suggestions(
        module_context=module_context,
        routing_context=routing_context,
        target_tfvars_content=existing_tfvars_content,
        common_tfvars_content=common_tfvars_content,
        variables_tf_content=variables_tf_content,
    )
    return routing_context


def resolve_azure_consumer_tfvars_path(
    prompt: str,
    retrieved_value_context: list | None = None,
    context_ref: str = "",
) -> tuple[str, str]:
    """Resolve the tf-azure-hub tfvars file that must receive consumer values.

    Module implementation variable declarations belong in the Azure module
    repository root variables.tf. Consumer/environment values belong in
    tf-azure-hub .tfvars files. The backend must prefer an explicit
    backend-routed path, then an explicit user path, then exact hub environment
    folders such as vars/npr/npr-int/hub.tfvars before falling back to tier files.
    """
    retrieved_value_context = retrieved_value_context or []
    for item in retrieved_value_context:
        if not isinstance(item, dict):
            continue
        explicit_path = (item.get("target_tfvars_filename") or item.get("tfvars_path") or "").strip()
        if explicit_path.startswith("vars/") and explicit_path.endswith(".tfvars"):
            return explicit_path, item.get("azure_environment") or explicit_path.split("/")[1]

    ref = (context_ref or "").strip() or github_branch_seed_for_cloud(
        "azure",
        repo_target="tf-azure-hub",
        workflow="azure_consumer_generation",
    )

    text = normalize_yes_no_reply(prompt)

    explicit_prompt_path = _explicit_tfvars_path_from_prompt(prompt)
    if explicit_prompt_path:
        if not _tf_azure_hub_tfvars_file_exists(explicit_prompt_path, ref):
            raise ValueError(
                f"The requested tf-azure-hub tfvars file does not exist: {explicit_prompt_path}"
            )
        parts = explicit_prompt_path.split("/")
        env_name = parts[2] if len(parts) >= 4 else (parts[1] if len(parts) >= 2 else "")
        return explicit_prompt_path, env_name

    if re.search(r"(?<![a-z0-9])(common\.tfvars|common tfvars|common vars|global vars)(?![a-z0-9])", text):
        return AZURE_DEFAULT_TFVARS_BY_ENV["common"], "common"

    exact_candidates, exact_env = _azure_exact_environment_tfvars_candidates(prompt)
    if exact_candidates:
        matched_path = _first_existing_tf_azure_hub_tfvars_path(exact_candidates, ref)
        if matched_path:
            return matched_path, exact_env
        raise ValueError(
            "The requested Azure environment was recognized, but no matching tfvars file exists in tf-azure-hub: "
            + ", ".join(exact_candidates)
        )

    # Check non-prod before prod because non-prod contains the token prod.
    if re.search(r"(?<![a-z0-9])(sandbox|sbx)(?![a-z0-9])", text):
        return AZURE_DEFAULT_TFVARS_BY_ENV["sbx"], "sbx"

    if re.search(r"(?<![a-z0-9])(non-production|non production|non-prod|non prod|nonprod|npr|staging)(?![a-z0-9])", text):
        return AZURE_DEFAULT_TFVARS_BY_ENV["npr"], "npr"

    if re.search(r"(?<![a-z0-9])(production|prod|prd)(?![a-z0-9])", text):
        return AZURE_DEFAULT_TFVARS_BY_ENV["prd"], "prd"

    return AZURE_DEFAULT_TFVARS_BY_ENV["npr"], "npr"


def _get_azure_consumer_context_ref(thread_id: str) -> str:
    try:
        state = recover_thread_pr_state(thread_id).get("azure_consumer") if thread_id else None
    except Exception:
        state = None

    if state:
        branch = (state.get("branch") or "").strip()
        if branch:
            try:
                if github_branch_exists(
                    "azure",
                    branch,
                    repo_target="tf-azure-hub",
                    workflow="azure_consumer_generation",
                ):
                    return branch
            except Exception:
                pass

    return github_branch_seed_for_cloud("azure", repo_target="tf-azure-hub", workflow="azure_consumer_generation")


def _extract_hcl_assignment_value(hcl_content: str, assignment_name: str) -> str:
    text = (hcl_content or "").replace("\r\n", "\n")
    assignment_name = (assignment_name or "").strip()
    if not text or not assignment_name:
        return ""

    pattern = rf'(?m)^[ \t]*{re.escape(assignment_name)}[ \t]*=[ \t]*'
    matches = list(re.finditer(pattern, text))
    if not matches:
        return ""

    # Prefer the shallowest matching assignment. In a tfvars file that means a
    # root assignment; in a module block it means a direct module argument. This
    # avoids accidentally returning nested object fields when both a root and a
    # nested field share the same name.
    match = min(
        matches,
        key=lambda item: _hcl_nesting_depth_at_position(text, item.start())
        if "_hcl_nesting_depth_at_position" in globals() else 0,
    )

    value_start = match.end()
    line_end = text.find("\n", value_start)
    if line_end == -1:
        line_end = len(text)

    first_value = text[value_start:line_end].rstrip()
    stripped = first_value.strip()
    if not stripped:
        return ""

    # A short user reply may contain comma-separated assignments on one line:
    #   storage_account_tier = "Standard", storage_account_replication = "ZRS"
    # Return only the first value for the requested name.
    if stripped[0] not in "[{(":
        value_chars = []
        in_string = False
        escape_next = False
        for ch in stripped:
            if in_string:
                value_chars.append(ch)
                if escape_next:
                    escape_next = False
                elif ch == "\\":
                    escape_next = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
                value_chars.append(ch)
                continue
            if ch == ",":
                break
            value_chars.append(ch)
        return "".join(value_chars).strip()

    open_ch = stripped[0]
    close_ch = {"[": "]", "{": "}", "(": ")"}[open_ch]
    depth = 0
    in_string = False
    escape_next = False

    for idx in range(value_start, len(text)):
        ch = text[idx]
        if in_string:
            if escape_next:
                escape_next = False
            elif ch == "\\":
                escape_next = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[value_start:idx + 1].strip()

    return text[value_start:].strip()


def _extract_root_variable_names(tf_content: str) -> list[str]:
    """Return only complete, balanced root variable declaration names.

    Regex-only detection is unsafe here because an incomplete block like:

      variable "storage_account_zrs_custom" {
        type = object({ ... })
      # missing final }

    would be treated as declared even though Terraform cannot parse it. That
    caused the backend to skip generating/repairing variables.tf.
    """
    names: list[str] = []

    for block in _extract_top_level_tf_blocks(tf_content or ""):
        header = (block.get("header") or "").strip()
        match = re.fullmatch(r'variable\s+"([^"]+)"', header)
        if not match:
            continue

        name = match.group(1).strip()
        if name and name not in names:
            names.append(name)

    return names


def _hcl_nesting_depth_at_position(text: str, position: int) -> int:
    """Return HCL collection nesting depth before position.

    This is intentionally lightweight but string-aware. It is used to tell
    top-level tfvars assignments apart from object fields such as
    account_tier, containers, filters, and actions.
    """
    depth = 0
    in_string = False
    escape_next = False

    for ch in (text or "")[:max(0, position)]:
        if in_string:
            if escape_next:
                escape_next = False
            elif ch == "\\":
                escape_next = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch in "[{(":
            depth += 1
        elif ch in "]})" and depth > 0:
            depth -= 1

    return depth


def _extract_top_level_hcl_assignment_names(hcl_content: str) -> list[str]:
    text = (hcl_content or "").replace("\r\n", "\n")
    names = []

    for match in re.finditer(r'(?m)^[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]*=', text):
        if _hcl_nesting_depth_at_position(text, match.start()) != 0:
            continue
        name = match.group(1).strip()
        if name and name not in names:
            names.append(name)

    return names


def _extract_balanced_block_from_hcl_match(hcl_content: str, match: re.Match) -> str:
    text = (hcl_content or "").replace("\r\n", "\n")
    brace_start = text.find("{", match.end() - 1)
    if brace_start == -1:
        return ""

    depth = 0
    in_string = False
    escape_next = False

    for idx in range(brace_start, len(text)):
        ch = text[idx]
        if in_string:
            if escape_next:
                escape_next = False
            elif ch == "\\":
                escape_next = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[match.start():idx + 1].strip()

    return ""


def _extract_tf_variable_block(tf_content: str, variable_name: str) -> str:
    variable_name = (variable_name or "").strip()
    if not variable_name:
        return ""

    pattern = rf'(?m)^\s*variable\s+"{re.escape(variable_name)}"\s*\{{'
    match = re.search(pattern, tf_content or "")
    if not match:
        return ""

    return _extract_balanced_block_from_hcl_match(tf_content, match)


def _variable_type_field_names(variable_block: str) -> set[str]:
    return {
        match.group(1)
        for match in re.finditer(
            r'(?m)^[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*(?:optional\()?[^\n]+',
            variable_block or "",
        )
        if match.group(1) not in {"type", "description", "default", "nullable", "sensitive", "validation", "condition", "error_message"}
    }


def _best_variables_tf_template_name(
    new_variable_name: str,
    tfvars_value: str,
    variables_tf_content: str,
    routing_context: dict | None = None,
) -> str:
    new_name = _terraform_safe_variable_name(new_variable_name)
    declared_names = _extract_root_variable_names(variables_tf_content)
    if not new_name or not declared_names:
        return ""

    candidates: list[str] = []
    routing_context = routing_context or {}
    source_root = _dominant_object_var_root(routing_context.get("matched_module_block") or "")
    if source_root in declared_names:
        candidates.append(source_root)

    suffixes = (
        "_custom",
        "_new",
        "_copy",
        "_test",
        "_dev",
        "_npr",
        "_prd",
        "_sbx",
        "_stg",
        "_stage",
        "_prod",
        "_production",
    )
    for suffix in suffixes:
        if new_name.endswith(suffix):
            candidates.append(new_name[:-len(suffix)])

    candidates.append(re.sub(r"_\d+$", "", new_name))

    for declared_name in sorted(declared_names, key=len, reverse=True):
        if new_name.startswith(declared_name + "_"):
            candidates.append(declared_name)

    for candidate in candidates:
        if candidate in declared_names:
            return candidate

    value_fields = set(_top_level_tfvars_assignment_field_names(tfvars_value))
    if value_fields:
        scored = []
        for declared_name in declared_names:
            block = _extract_tf_variable_block(variables_tf_content, declared_name)
            type_fields = _variable_type_field_names(block)
            overlap = len(value_fields & type_fields)
            if overlap:
                scored.append((-overlap, -len(declared_name), declared_name))
        if scored:
            return sorted(scored)[0][2]

    return ""


def _infer_variable_type_from_tfvars_value(tfvars_value: str) -> str:
    value = (tfvars_value or "").strip()
    if not value:
        return "any"
    if value.startswith('"') and value.endswith('"'):
        return "string"
    if value.lower() in {"true", "false"}:
        return "bool"
    if re.fullmatch(r"-?\d+(?:\.\d+)?", value):
        return "number"
    if value.startswith("["):
        return "list(any)"
    if value.startswith("{"):
        return "any"
    return "any"


def _build_variables_tf_declaration(
    new_variable_name: str,
    tfvars_value: str,
    variables_tf_content: str,
    routing_context: dict | None = None,
) -> str:
    new_variable_name = _terraform_safe_variable_name(new_variable_name)
    if not new_variable_name:
        return ""

    template_name = _best_variables_tf_template_name(
        new_variable_name,
        tfvars_value,
        variables_tf_content,
        routing_context=routing_context,
    )
    if template_name:
        template_block = _extract_tf_variable_block(variables_tf_content, template_name)
        if template_block:
            declaration = re.sub(
                rf'variable\s+"{re.escape(template_name)}"',
                f'variable "{new_variable_name}"',
                template_block,
                count=1,
            ).rstrip() + "\n"
            return _finalize_variables_tf_declaration(
                declaration,
                variable_name=new_variable_name,
            )

    inferred_type = _infer_variable_type_from_tfvars_value(tfvars_value)
    declaration = (
        f'variable "{new_variable_name}" {{\n'
        f'  description = "Values for {new_variable_name}."\n'
        f'  type        = {inferred_type}\n'
        f'}}\n'
    )
    return _finalize_variables_tf_declaration(
        declaration,
        variable_name=new_variable_name,
    )

def _hcl_curly_balance(value: str) -> int:
    """Return top-level curly brace balance while ignoring quoted strings."""
    depth = 0
    in_string = False
    escape_next = False
    for ch in value or "":
        if in_string:
            if escape_next:
                escape_next = False
            elif ch == "\\":
                escape_next = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
    return depth


def _variable_name_from_declaration(declaration: str) -> str:
    match = re.search(
        r'(?m)^\s*variable\s+"([^"\n]+)"\s*\{',
        declaration or "",
        re.IGNORECASE,
    )
    return match.group(1).strip() if match else ""


def _add_terrabot_variable_close_marker(declaration: str, variable_name: str) -> str:
    """Make the generated closing brace line unique for conflict resolution.

    A plain final `}` at EOF can become conflict context. Adding an inline HCL
    comment to the variable-block closing brace makes the close brace part of
    the generated side, so editor/GitHub "accept both changes" flows are much
    less likely to drop it.
    """
    variable_name = _terraform_safe_variable_name(variable_name)
    declaration = (declaration or "").replace("\r\n", "\n").rstrip()
    if not declaration or not variable_name:
        return declaration + "\n" if declaration else ""

    marker = f"# terrabot:close-variable {variable_name}"
    if marker in declaration:
        return declaration.rstrip() + "\n"

    lines = declaration.splitlines()
    for idx in range(len(lines) - 1, -1, -1):
        line = lines[idx]
        if not line.strip():
            continue
        if line.strip() == "}":
            indent_match = re.match(r"^\s*", line)
            indent = indent_match.group(0) if indent_match else ""
            lines[idx] = f"{indent}}} {marker}"
            return "\n".join(lines).rstrip() + "\n"
        break

    return declaration.rstrip() + "\n"


def _wrap_terrabot_variable_declaration(declaration: str, variable_name: str) -> str:
    variable_name = _terraform_safe_variable_name(variable_name)
    declaration = (declaration or "").replace("\r\n", "\n").strip()
    if not declaration or not variable_name:
        return declaration + "\n" if declaration else ""

    begin = f"# terrabot:begin-variable {variable_name}"
    end = f"# terrabot:end-variable {variable_name}"
    if begin in declaration and end in declaration:
        return declaration.rstrip() + "\n"

    return f"{begin}\n{declaration.rstrip()}\n{end}\n"


def _finalize_variables_tf_declaration(
    declaration: str,
    variable_name: str | None = None,
) -> str:
    """Return one complete, balanced Terraform variable block.

    This is applied to backend-generated declarations before appending them to
    tf-azure-hub/variables.tf. The common failure mode is a copied object type
    that ends at `  })` but omits the final `}` for the variable block. We add
    only missing trailing braces, then re-extract the variable block so a
    partial declaration cannot be committed.
    """
    declaration = (declaration or "").replace("\r\n", "\n").strip()
    variable_name = _terraform_safe_variable_name(
        variable_name or _variable_name_from_declaration(declaration)
    )

    if not declaration:
        return ""
    if not variable_name:
        raise ValueError(
            "Generated variables.tf declaration is missing a variable name; refusing to write malformed Terraform."
        )

    match = re.search(
        rf'(?m)^\s*variable\s+"{re.escape(variable_name)}"\s*\{{',
        declaration,
        re.IGNORECASE,
    )
    if match:
        declaration = declaration[match.start():].rstrip()

    balance = _hcl_curly_balance(declaration)
    if balance < 0:
        raise ValueError(
            f'Generated variables.tf declaration for {variable_name} has extra closing brace(s); refusing to write malformed Terraform.'
        )
    if balance > 0:
        declaration = declaration.rstrip() + "\n" + "\n".join("}" for _ in range(balance))

    if _hcl_curly_balance(declaration) != 0:
        raise ValueError(
            f'Generated variables.tf declaration for {variable_name} is not brace-balanced after finalization.'
        )

    block = _extract_tf_variable_block(declaration, variable_name)
    if not block:
        raise ValueError(
            f'Generated variables.tf declaration for {variable_name} is not a complete Terraform variable block.'
        )

    if _hcl_curly_balance(block) != 0:
        raise ValueError(
            f'Generated variables.tf declaration for {variable_name} is still unbalanced after finalization.'
        )

    return _add_terrabot_variable_close_marker(block, variable_name)


def _append_variables_tf_declaration(variables_tf_content: str, declaration: str) -> str:
    existing = (variables_tf_content or "").replace("\r\n", "\n").rstrip()
    variable_name = _terraform_safe_variable_name(_variable_name_from_declaration(declaration))
    declaration = _finalize_variables_tf_declaration(
        declaration,
        variable_name=variable_name,
    )
    if not declaration:
        return existing + "\n" if existing else ""

    # If a conflict resolution already left this variable header in the file,
    # repair that existing block instead of appending another copy. This handles
    # the common post-merge state: `variable "x" { ...  })` with the final
    # variable close brace dropped by "accept both changes".
    if variable_name and variable_name in set(_extract_root_variable_names(existing)):
        return _repair_unclosed_variables_tf_content_for_write(
            existing_content=None,
            generated_content=existing,
            path="variables.tf",
        )

    declaration = _wrap_terrabot_variable_declaration(declaration, variable_name)

    if declaration.strip() in existing:
        combined = existing + "\n"
    elif not existing:
        combined = declaration
    else:
        combined = existing + "\n\n" + declaration

    return _repair_unclosed_variables_tf_content_for_write(
        existing_content=None,
        generated_content=combined,
        path="variables.tf",
    )

def _ensure_azure_consumer_variables_tf_declarations(
    agent_result: dict,
    routing_context: dict,
    tfvars_content: str,
    active_value_context: list | None = None,
    consumer_content: str = "",
) -> tuple[str, list[str]]:
    """Return variables.tf content plus declarations for new tfvars roots.

    Existing-module Azure consumer generation writes values to a routed tfvars
    file. Any new top-level root added there must also exist as a root variable
    declaration in tf-azure-hub/variables.tf. This backend patch derives that
    declaration from the exact variables.tf content read during source matching,
    preserving the existing file and appending only missing declarations.
    """
    routing_context = routing_context or {}
    active_value_context = active_value_context or []
    existing_tfvars = routing_context.get("existing_tfvars_file_content") or ""
    variables_tf_content = routing_context.get("variables_tf_file_content") or ""

    if not variables_tf_content:
        for item in active_value_context:
            if isinstance(item, dict) and item.get("source") == "backend_tf_azure_hub_source_match":
                variables_tf_content = item.get("variables_tf_file_content") or ""
                if variables_tf_content:
                    break

    if not variables_tf_content:
        context_ref = routing_context.get("context_ref") or github_branch_seed_for_cloud(
            "azure",
            repo_target="tf-azure-hub",
            workflow="azure_consumer_generation",
        )
        try:
            variables_tf_content = github_get_file_content(
                "azure",
                "variables.tf",
                context_ref,
                repo_target="tf-azure-hub",
                workflow="azure_consumer_generation",
            ) or ""
        except Exception:
            variables_tf_content = ""

    original_variables_tf_content = variables_tf_content.replace("\r\n", "\n")

    if variables_tf_content.strip():
        variables_tf_content = _repair_unclosed_variables_tf_content_for_write(
        existing_content=None,
        generated_content=variables_tf_content,
        path="variables.tf",
        )

    generated_roots = _extract_top_level_hcl_assignment_names(tfvars_content)
    generated_root_set = set(generated_roots)
    existing_roots = set(_extract_top_level_hcl_assignment_names(existing_tfvars))

    # Only declarations for roots that are part of this request should be
    # appended. A root qualifies when it is newly added/changed in the routed
    # tfvars file, when the new module block references it, or when it comes
    # from backend suggested_variable_values. Do not skip a root only because it
    # already existed in tfvars; if variables.tf lacks the declaration, the PR
    # must still add the declaration or Terraform validate can fail.
    candidate_roots: list[str] = []
    for root_name in generated_roots:
        generated_value = _normalized_hcl_content_for_compare(
            _extract_hcl_assignment_value(tfvars_content, root_name)
        )
        existing_value = _normalized_hcl_content_for_compare(
            _extract_hcl_assignment_value(existing_tfvars, root_name)
        )
        if root_name not in existing_roots or generated_value != existing_value:
            candidate_roots.append(root_name)

    module_source_url = (routing_context or {}).get("module_source_url") or ""
    existing_consumer = (routing_context or {}).get("existing_consumer_file_content") or ""
    for block in _new_matching_module_blocks(existing_consumer, consumer_content or "", module_source_url):
        for referenced_root in _extract_var_roots_from_text(block.get("block") or ""):
            if referenced_root in generated_root_set and referenced_root not in candidate_roots:
                candidate_roots.append(referenced_root)

    for item in (routing_context or {}).get("suggested_variable_values") or []:
        if not isinstance(item, dict):
            continue
        suggested_root = (item.get("tfvars_variable_name") or item.get("input_name") or "").strip()
        if suggested_root in generated_root_set and suggested_root not in candidate_roots:
            candidate_roots.append(suggested_root)

    declared_roots = set(_extract_root_variable_names(variables_tf_content))
    added: list[str] = []
    updated_variables_tf = variables_tf_content.replace("\r\n", "\n").rstrip() + "\n" if variables_tf_content else ""

    for root_name in candidate_roots:
        safe_name = _terraform_safe_variable_name(root_name)
        if not safe_name:
            continue
        if safe_name in declared_roots:
            continue

        tfvars_value = _extract_hcl_assignment_value(tfvars_content, root_name)
        if not tfvars_value:
            # Do not declare variables for roots that are only referenced in the
            # module block but do not have a value in the routed tfvars file.
            # Missing values are rejected by the tfvars validation above.
            continue
        declaration = _build_variables_tf_declaration(
            safe_name,
            tfvars_value,
            updated_variables_tf,
            routing_context=routing_context,
        )
        if not declaration:
            continue

        updated_variables_tf = _append_variables_tf_declaration(updated_variables_tf, declaration)
        declared_roots.add(safe_name)
        added.append(safe_name)

    return updated_variables_tf.replace("\r\n", "\n").rstrip() + "\n", added




def _context_azure_file_content(
    path: str,
    routing_context: dict | None = None,
    active_value_context: list | None = None,
) -> str:
    """Return backend-provided tf-azure-hub file content for a repo-relative path."""
    normalized = normalize_agent_relative_tf_path(path or "", "azure")
    routing_context = routing_context or {}

    if normalized == "variables.tf":
        value = routing_context.get("variables_tf_file_content") or ""
        if value:
            return value

    target_tfvars = routing_context.get("target_tfvars_filename") or ""
    if target_tfvars and normalized == normalize_agent_relative_tf_path(target_tfvars, "azure"):
        value = routing_context.get("existing_tfvars_file_content") or ""
        if value:
            return value

    if normalized == "vars/common.tfvars":
        value = routing_context.get("common_tfvars_file_content") or ""
        if value:
            return value

    for item in active_value_context or []:
        if not isinstance(item, dict):
            continue

        if item.get("source") == "backend_tf_azure_hub_source_match":
            if normalized == "variables.tf":
                value = item.get("variables_tf_file_content") or ""
                if value:
                    return value

            target_tfvars = item.get("target_tfvars_filename") or ""
            if target_tfvars and normalized == normalize_agent_relative_tf_path(target_tfvars, "azure"):
                value = item.get("existing_tfvars_file_content") or ""
                if value:
                    return value

            if normalized == "vars/common.tfvars":
                value = item.get("common_tfvars_file_content") or ""
                if value:
                    return value

        item_path = item.get("path") or item.get("filename") or ""
        if item_path and normalized == normalize_agent_relative_tf_path(item_path, "azure"):
            value = item.get("content") or ""
            if value:
                return value

    return ""


def _read_tf_azure_hub_file_for_backend(
    path: str,
    routing_context: dict | None = None,
    active_value_context: list | None = None,
) -> str:
    """Read tf-azure-hub file content from routed context first, then GitHub."""
    normalized = normalize_agent_relative_tf_path(path or "", "azure")
    context_value = _context_azure_file_content(
        normalized,
        routing_context=routing_context,
        active_value_context=active_value_context,
    )
    if context_value:
        return context_value

    context_ref = (routing_context or {}).get("context_ref") or github_branch_seed_for_cloud(
        "azure",
        repo_target="tf-azure-hub",
        workflow="azure_consumer_generation",
    )
    try:
        return github_get_file_content(
            "azure",
            normalized,
            context_ref,
            repo_target="tf-azure-hub",
            workflow="azure_consumer_generation",
        ) or ""
    except Exception:
        return ""


def _replace_or_append_file_entry(files: list[dict], filename: str, content: str) -> None:
    filename = normalize_agent_relative_tf_path(filename or "", "azure")
    normalized_content = (content or "").replace("\r\n", "\n").rstrip() + "\n"
    if filename == "variables.tf" or filename.endswith("/variables.tf"):
        normalized_content = _repair_unclosed_variables_tf_content_for_write(
            existing_content=None,
            generated_content=normalized_content,
            path=filename,
        )

    for file_data in files:
        if normalize_agent_relative_tf_path((file_data or {}).get("filename") or "", "azure") == filename:
            file_data["filename"] = filename
            file_data["content"] = normalized_content
            return
    files.append({
        "filename": filename,
        "content": normalized_content,
    })


def _repair_azure_consumer_variables_tf_files_in_agent_result_stage1(agent_result: dict) -> dict:
    """Normalize any generated Azure consumer variables.tf before preview/commit.

    This catches the case where variables.tf is already present in files[] and
    contains the existing file plus an appended but unclosed variable block.
    The write path also performs the same check, but doing it here keeps the
    stored pending preview and committed PR content identical.
    """
    if not isinstance(agent_result, dict):
        return agent_result
    if safe_normalize_cloud(agent_result.get("cloud")) != "azure":
        return agent_result
    if (agent_result.get("workflow") or "").strip() != "azure_consumer_generation":
        return agent_result
    if normalize_repo_target("azure", agent_result.get("repo_target"), agent_result.get("workflow")) != "tf-azure-hub":
        return agent_result

    for file_data in agent_result.get("files") or []:
        if not isinstance(file_data, dict):
            continue
        filename = normalize_agent_relative_tf_path(file_data.get("filename") or "", "azure")
        if filename != "variables.tf" and not filename.endswith("/variables.tf"):
            continue
        file_data["content"] = _repair_unclosed_variables_tf_content_for_write(
            existing_content=None,
            generated_content=file_data.get("content") or "",
            path=filename,
        )
    return agent_result
_repair_azure_consumer_variables_tf_files_in_agent_result = _repair_azure_consumer_variables_tf_files_in_agent_result_stage1

def _new_tfvars_assignment_roots(
    existing_tfvars: str,
    generated_tfvars: str,
    consumer_content: str = "",
) -> list[str]:
    """Return top-level tfvars roots that were added by the generated payload."""
    existing_roots = set(_extract_top_level_hcl_assignment_names(existing_tfvars))
    generated_roots = _extract_top_level_hcl_assignment_names(generated_tfvars)
    referenced_roots = {
        _terraform_safe_variable_name(root)
        for root in re.findall(r"\bvar\.([A-Za-z_][A-Za-z0-9_]*)\b", consumer_content or "")
    }

    roots = []
    for root in generated_roots:
        safe_root = _terraform_safe_variable_name(root)
        if not safe_root:
            continue
        if root in existing_roots or safe_root in existing_roots:
            continue
        if referenced_roots and safe_root not in referenced_roots:
            continue
        if safe_root not in roots:
            roots.append(safe_root)
    return roots


def ensure_azure_consumer_variables_tf_file_stage1(
    agent_result: dict,
    retrieved_value_context: list | None = None,
) -> dict:
    """Guarantee variables.tf is added when Azure consumer tfvars adds roots.

    The agent may correctly return only the backend-routed .tf file and .tfvars
    file. The backend must still include tf-azure-hub/variables.tf whenever the
    tfvars update introduces a new top-level variable root. Existing variables.tf
    content is preserved exactly and missing declarations are appended only.
    """
    if not isinstance(agent_result, dict):
        return agent_result
    if safe_normalize_cloud(agent_result.get("cloud")) != "azure":
        return agent_result
    if (agent_result.get("workflow") or "").strip() != "azure_consumer_generation":
        return agent_result
    if normalize_repo_target("azure", agent_result.get("repo_target"), agent_result.get("workflow")) != "tf-azure-hub":
        return agent_result

    files = agent_result.get("files") or []
    if not isinstance(files, list) or not files:
        return agent_result

    active_value_context = list(retrieved_value_context or [])
    routing_context = _get_azure_consumer_routing_context(
        agent_result.get("retrieved_value_context") or active_value_context
    )

    consumer_contents = []
    for file_data in files:
        if not isinstance(file_data, dict):
            continue
        filename = normalize_agent_relative_tf_path(file_data.get("filename") or "", "azure")
        if filename.endswith(".tf") and filename != "variables.tf":
            consumer_contents.append(file_data.get("content") or "")
    combined_consumer_content = "\n".join(consumer_contents)

    variables_entry = _find_agent_file_by_name_or_suffix(files, "variables.tf", suffix="")
    existing_variables_tf_content = _read_tf_azure_hub_file_for_backend(
        "variables.tf",
        routing_context=routing_context,
        active_value_context=active_value_context,
    )

    if variables_entry:
        generated_variables_tf_content = (variables_entry.get("content") or "").replace("\r\n", "\n")
        if (
            existing_variables_tf_content
            and existing_variables_tf_content.strip() in generated_variables_tf_content.strip()
        ):
            variables_tf_content = _repair_unclosed_variables_tf_content_for_write(
                existing_variables_tf_content,
                generated_variables_tf_content,
                "variables.tf",
            )
        else:
            # Do not use a partial agent-generated variables.tf as the merge
            # base. It would either delete existing declarations or write an
            # incomplete appended block. Start from the backend-read file and
            # let the backend append the missing declaration below.
            variables_tf_content = existing_variables_tf_content or generated_variables_tf_content
    else:
        variables_tf_content = existing_variables_tf_content

    if not variables_tf_content.strip():
        return agent_result
    variables_tf_content = _repair_unclosed_variables_tf_content_for_write(
        existing_content=existing_variables_tf_content,
        generated_content=variables_tf_content,
        path="variables.tf",
    )

    updated_variables_tf = variables_tf_content.replace("\r\n", "\n").rstrip() + "\n"
    declared_roots = set(_extract_root_variable_names(updated_variables_tf))
    added: list[str] = []

    for file_data in list(files):
        if not isinstance(file_data, dict):
            continue
        filename = normalize_agent_relative_tf_path(file_data.get("filename") or "", "azure")
        if not filename.endswith(".tfvars"):
            continue

        generated_tfvars = (file_data.get("content") or "").replace("\r\n", "\n")
        existing_tfvars = _read_tf_azure_hub_file_for_backend(
            filename,
            routing_context=routing_context,
            active_value_context=active_value_context,
        )
        if not existing_tfvars and routing_context and filename == normalize_agent_relative_tf_path(routing_context.get("target_tfvars_filename") or "", "azure"):
            existing_tfvars = routing_context.get("existing_tfvars_file_content") or ""

        for root_name in _new_tfvars_assignment_roots(
            existing_tfvars=existing_tfvars,
            generated_tfvars=generated_tfvars,
            consumer_content=combined_consumer_content,
        ):
            if root_name in declared_roots:
                continue
            value = _extract_hcl_assignment_value(generated_tfvars, root_name)
            declaration = _build_variables_tf_declaration(
                root_name,
                value,
                updated_variables_tf,
                routing_context=routing_context,
            )
            if not declaration:
                continue
            updated_variables_tf = _append_variables_tf_declaration(updated_variables_tf, declaration)
            declared_roots.add(root_name)
            added.append(root_name)

    if not added:
        if variables_entry:
            repaired_variables_tf = _repair_unclosed_variables_tf_content_for_write(
                existing_variables_tf_content,
                variables_tf_content,
                "variables.tf",
            )
            if (
                existing_variables_tf_content
                and existing_variables_tf_content.strip() not in repaired_variables_tf.strip()
            ):
                # Drop unsafe partial variables.tf returned by the agent. The
                # backend will not commit a file that does not preserve existing
                # tf-azure-hub variables.tf content.
                agent_result["files"] = [
                    file_data
                    for file_data in files
                    if normalize_agent_relative_tf_path((file_data or {}).get("filename") or "", "azure") != "variables.tf"
                ]
                return agent_result
            variables_entry["content"] = repaired_variables_tf
            agent_result["files"] = files
        return agent_result

    updated_variables_tf = _repair_unclosed_variables_tf_content_for_write(
        existing_variables_tf_content,
        updated_variables_tf,
        "variables.tf",
    )

    _replace_or_append_file_entry(files, "variables.tf", updated_variables_tf)
    agent_result["files"] = files

    existing_added = list(agent_result.get("azure_consumer_variable_declarations_added") or [])
    for name in added:
        if name not in existing_added:
            existing_added.append(name)
    agent_result["azure_consumer_variable_declarations_added"] = existing_added

    routing_summary = agent_result.get("routing_summary") or {}
    routing_summary["variables_file"] = "variables.tf"
    summary_added = list(routing_summary.get("variables_added") or [])
    for name in added:
        if name not in summary_added:
            summary_added.append(name)
    routing_summary["variables_added"] = summary_added
    agent_result["routing_summary"] = routing_summary
    return agent_result
ensure_azure_consumer_variables_tf_file = ensure_azure_consumer_variables_tf_file_stage1

def _is_sensitive_variable_name(name: str) -> bool:
    lowered = (name or "").lower()
    sensitive_markers = (
        "password",
        "passwd",
        "secret",
        "token",
        "client_secret",
        "access_key",
        "private_key",
        "ssh_private",
        "certificate",
        "connection_string",
    )
    return any(marker in lowered for marker in sensitive_markers)


def _truncate_suggestion_value(value: str, limit: int = 600) -> str:
    value = (value or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + " ..."


def build_azure_variable_value_suggestions(
    module_context: dict,
    routing_context: dict,
    target_tfvars_content: str,
    common_tfvars_content: str = "",
    variables_tf_content: str = "",
) -> list[dict]:
    inputs = _dedupe_preserving_order(
        list(module_context.get("required_inputs_detected") or [])
        + list(module_context.get("inputs_detected") or [])
    )
    matched_module_block = routing_context.get("matched_module_block") or ""
    declared_root_variables = set(_extract_root_variable_names(variables_tf_content))

    suggestions = []
    for input_name in inputs:
        input_name = str(input_name or "").strip()
        if not input_name:
            continue

        module_expression = _extract_hcl_assignment_value(matched_module_block, input_name)
        tfvars_variable_name = input_name
        expression_var_match = re.match(r"^var\.([A-Za-z_][A-Za-z0-9_]*)(?:\b|\.|\[)", module_expression or "")
        if expression_var_match:
            tfvars_variable_name = expression_var_match.group(1)

        suggested_value = ""
        suggestion_source = ""
        if not _is_sensitive_variable_name(tfvars_variable_name) and not _is_sensitive_variable_name(input_name):
            suggested_value = _extract_hcl_assignment_value(target_tfvars_content, tfvars_variable_name)
            if suggested_value:
                suggestion_source = routing_context.get("target_tfvars_filename") or "target tfvars"

            if not suggested_value:
                suggested_value = _extract_hcl_assignment_value(common_tfvars_content, tfvars_variable_name)
                if suggested_value:
                    suggestion_source = "vars/common.tfvars"

            if not suggested_value and tfvars_variable_name != input_name:
                suggested_value = _extract_hcl_assignment_value(target_tfvars_content, input_name)
                if suggested_value:
                    suggestion_source = routing_context.get("target_tfvars_filename") or "target tfvars"

            if not suggested_value and tfvars_variable_name != input_name:
                suggested_value = _extract_hcl_assignment_value(common_tfvars_content, input_name)
                if suggested_value:
                    suggestion_source = "vars/common.tfvars"

        suggestions.append({
            "input_name": input_name,
            "required": input_name in set(module_context.get("required_inputs_detected") or []),
            "matched_existing_module_expression": module_expression,
            "tfvars_variable_name": tfvars_variable_name,
            "root_variable_declared": tfvars_variable_name in declared_root_variables,
            "suggested_value": _truncate_suggestion_value(suggested_value),
            "suggestion_source": suggestion_source,
            "sensitive": _is_sensitive_variable_name(tfvars_variable_name) or _is_sensitive_variable_name(input_name),
        })

    return suggestions


def build_azure_consumer_source_routing_context(
    prompt: str,
    thread_id: str,
    retrieved_module_context: list,
    retrieved_value_context: list,
) -> dict:
    module_context = _get_primary_azure_module_context(retrieved_module_context)
    module_source_url = (module_context.get("module_source_url") or "").strip()
    if not module_source_url:
        return {}

    context_ref = _get_azure_consumer_context_ref(thread_id)
    root_path = cloud_root_dir("azure", repo_target="tf-azure-hub", workflow="azure_consumer_generation") or "."

    tf_paths = github_list_tf_files_recursive(
        cloud="azure",
        root_path=root_path,
        branch=context_ref,
        repo_target="tf-azure-hub",
        workflow="azure_consumer_generation",
    )

    tf_files = []
    for tf_path in tf_paths:
        # Source matching is only for Terraform implementation files, not tfvars.
        if not tf_path.endswith(".tf"):
            continue
        content = github_get_file_content(
            "azure",
            tf_path,
            context_ref,
            repo_target="tf-azure-hub",
            workflow="azure_consumer_generation",
        )
        if content:
            tf_files.append({"path": tf_path, "content": content})

    match = find_tf_azure_hub_module_invocation_file_by_source(
        module_source_url=module_source_url,
        tf_files=tf_files,
        user_prompt=prompt,
    )

    if not match:
        auto_confirm_new_file = _is_new_azure_module_consumer_context(retrieved_module_context)
        return build_new_azure_consumer_file_routing_context(
            prompt=prompt,
            thread_id=thread_id,
            retrieved_module_context=retrieved_module_context,
            retrieved_value_context=retrieved_value_context,
            tf_file_count=len(tf_files),
            auto_confirm=auto_confirm_new_file,
        )

    target_consumer_filename = match.get("path") or match.get("filename") or ""
    existing_consumer_content = github_get_file_content(
        "azure",
        target_consumer_filename,
        context_ref,
        repo_target="tf-azure-hub",
        workflow="azure_consumer_generation",
    )
    if existing_consumer_content is None:
        raise ValueError(f"Could not read existing tf-azure-hub consumer file: {target_consumer_filename}")

    target_tfvars_filename, azure_environment = resolve_azure_consumer_tfvars_path(
        prompt,
        retrieved_value_context,
        context_ref=context_ref,
    )
    existing_tfvars_content = github_get_file_content(
        "azure",
        target_tfvars_filename,
        context_ref,
        repo_target="tf-azure-hub",
        workflow="azure_consumer_generation",
    )
    if existing_tfvars_content is None:
        raise ValueError(
            f"The resolved tfvars file does not exist in tf-azure-hub: {target_tfvars_filename}. "
            "Azure consumer variable values must be added to an existing vars file."
        )

    common_tfvars_content = ""
    if target_tfvars_filename != "vars/common.tfvars":
        common_tfvars_content = github_get_file_content(
            "azure",
            "vars/common.tfvars",
            context_ref,
            repo_target="tf-azure-hub",
            workflow="azure_consumer_generation",
        ) or ""

    variables_tf_content = github_get_file_content(
        "azure",
        "variables.tf",
        context_ref,
        repo_target="tf-azure-hub",
        workflow="azure_consumer_generation",
    ) or ""

    routing_context = {
        "source": "backend_tf_azure_hub_source_match",
        "repo_target": "tf-azure-hub",
        "context_ref": context_ref,
        "module_source_url": module_source_url,
        "module_repo_full_name": module_context.get("repo_full_name") or module_context.get("target_module_repo_full_name") or "",
        "target_consumer_filename": target_consumer_filename,
        "target_tfvars_filename": target_tfvars_filename,
        "azure_environment": azure_environment,
        "matched_module_name": match.get("matched_module_name") or "",
        "matched_module_source": match.get("matched_module_source") or "",
        "matched_module_block": match.get("matched_module_block") or "",
        "matched_invocation_count": match.get("matched_invocation_count") or 0,
        "match_type": match.get("match_type") or "",
        "match_score": match.get("score") or 0,
        "existing_consumer_file_content": existing_consumer_content,
        "existing_tfvars_file_content": existing_tfvars_content,
        "common_tfvars_file_content": common_tfvars_content,
        "variables_tf_file_content": variables_tf_content,
    }
    routing_context["suggested_variable_values"] = build_azure_variable_value_suggestions(
        module_context=module_context,
        routing_context=routing_context,
        target_tfvars_content=existing_tfvars_content,
        common_tfvars_content=common_tfvars_content,
        variables_tf_content=variables_tf_content,
    )

    return routing_context


def augment_azure_consumer_generation_context(
    prompt: str,
    thread_id: str,
    retrieved_module_context: list,
    retrieved_value_context: list,
) -> tuple[list[dict], list[dict], dict]:
    retrieved_module_context = list(retrieved_module_context or [])
    retrieved_value_context = list(retrieved_value_context or [])

    existing_routing_context = _get_azure_consumer_routing_context(retrieved_value_context)
    if existing_routing_context:
        return retrieved_module_context, retrieved_value_context, existing_routing_context

    routing_context = build_azure_consumer_source_routing_context(
        prompt=prompt,
        thread_id=thread_id,
        retrieved_module_context=retrieved_module_context,
        retrieved_value_context=retrieved_value_context,
    )

    if routing_context:
        retrieved_value_context.append(routing_context)

    return retrieved_module_context, retrieved_value_context, routing_context


def build_azure_consumer_value_selection_form(routing_context: dict, module_context: dict) -> dict:
    routing_context = routing_context or {}
    module_context = module_context or {}
    fields = []

    for item in routing_context.get("suggested_variable_values") or []:
        if not isinstance(item, dict):
            continue
        value = item.get("suggested_value") or ""
        fields.append({
            "name": item.get("tfvars_variable_name") or item.get("input_name") or "",
            "label": item.get("input_name") or item.get("tfvars_variable_name") or "",
            "tfvars_variable_name": item.get("tfvars_variable_name") or item.get("input_name") or "",
            "module_input_name": item.get("input_name") or "",
            "required": bool(item.get("required")),
            "sensitive": bool(item.get("sensitive")),
            "default_value": value,
            "default_source": item.get("suggestion_source") or "existing module pattern",
            "module_expression": item.get("matched_existing_module_expression") or "",
            "blank_uses_default": True,
        })

    return {
        "type": "azure_consumer_value_selection",
        "title": "Confirm Azure module variable values",
        "consumer_file": routing_context.get("target_consumer_filename") or "",
        "tfvars_file": routing_context.get("target_tfvars_filename") or "",
        "azure_environment": routing_context.get("azure_environment") or "",
        "module_source_url": routing_context.get("module_source_url") or "",
        "submit_label": "Use selected values",
        "default_action": "use_suggested_values",
        "blank_fields_use_defaults": True,
        "fields": fields,
    }


def build_azure_consumer_variable_values_reply(routing_context: dict, module_context: dict) -> str:
    routing_context = routing_context or {}
    module_context = module_context or {}
    suggestions = routing_context.get("suggested_variable_values") or []

    required_names = [item.get("input_name") for item in suggestions if item.get("required")]
    optional_names = [item.get("input_name") for item in suggestions if not item.get("required")]

    if routing_context.get("source") == "backend_new_azure_consumer_routing":
        first_line = (
            f"I am generating a new Azure module invocation file `{routing_context.get('target_consumer_filename')}` "
            "in tf-azure-hub because no existing consumer file uses the selected module source."
        )
    else:
        first_line = (
            f"I am generating the Azure module invocation in `{routing_context.get('target_consumer_filename')}` "
            "because that existing file already uses the selected module source."
        )

    lines = [
        first_line,
        f"I will add variable values in `{routing_context.get('target_tfvars_filename')}` and preserve the existing contents of both files.",
        "",
        "Please confirm the values Terrabot should use for the new module invocation.",
    ]

    if required_names:
        lines.append(f"Required module inputs: {', '.join(required_names[:30])}")
    if optional_names:
        lines.append(f"Optional detected inputs: {', '.join(optional_names[:20])}")

    shown = 0
    suggestion_lines = []
    for item in suggestions:
        value = item.get("suggested_value") or ""
        expression = item.get("matched_existing_module_expression") or ""
        source = item.get("suggestion_source") or ""
        name = item.get("input_name") or ""
        tfvar_name = item.get("tfvars_variable_name") or name

        if item.get("sensitive"):
            suggestion_lines.append(f"- `{name}`: sensitive value; please provide or reference an approved secret source.")
            shown += 1
        elif value:
            compact_value = re.sub(r"\s+", " ", value).strip()
            if len(compact_value) > 160:
                compact_value = compact_value[:157].rstrip() + "..."
            suggestion_lines.append(f"- `{name}` / `{tfvar_name}`: `{compact_value}` from {source}")
            shown += 1
        elif expression:
            compact_expression = re.sub(r"\s+", " ", expression).strip()
            if len(compact_expression) > 160:
                compact_expression = compact_expression[:157].rstrip() + "..."
            suggestion_lines.append(f"- `{name}`: existing module pattern uses `{compact_expression}`")
            shown += 1

        if shown >= 15:
            break

    if suggestion_lines:
        lines.append("")
        lines.append("Suggested values/patterns from existing tf-azure-hub code:")
        lines.extend(suggestion_lines)

    table_rows = []
    for item in suggestions[:12]:
        if not isinstance(item, dict):
            continue
        default_value = re.sub(r"\s+", " ", (item.get("suggested_value") or item.get("matched_existing_module_expression") or "")).strip()
        if len(default_value) > 80:
            default_value = default_value[:77].rstrip() + "..."
        table_rows.append(
            f"| `{item.get('input_name') or ''}` | `{item.get('tfvars_variable_name') or item.get('input_name') or ''}` | `{default_value or 'use existing pattern/default'}` |"
        )

    if table_rows:
        lines.append("")
        lines.append("Value selection form data:")
        lines.append("| Module input | tfvars variable | Default when left blank |")
        lines.append("|---|---|---|")
        lines.extend(table_rows)

    lines.append("")
    lines.append("Reply `use suggested values` to proceed. You can also paste HCL assignments for only the values you want to override; any omitted or blank value will use the suggested default. No PR preview will be generated until you confirm the values.")
    return "\n".join(lines)


def _content_contains_existing_file(existing_content: str, generated_content: str) -> bool:
    existing = (existing_content or "").replace("\r\n", "\n").strip()
    generated = (generated_content or "").replace("\r\n", "\n").strip()
    return bool(existing and existing in generated)


def _normalized_hcl_content_for_compare(content: str) -> str:
    return (content or "").replace("\r\n", "\n").strip()


def _is_new_azure_module_consumer_context(retrieved_module_context: list) -> bool:
    for item in retrieved_module_context or []:
        if not isinstance(item, dict):
            continue
        if (item.get("match_type") or "").strip() == "new_module_created":
            return True
        if (item.get("source") or "").strip() == "backend_verified_new_azure_module_repo_files":
            return True
    return False


def validate_azure_consumer_two_file_payload_for_commit_stage1(agent_result: dict) -> None:
    if not isinstance(agent_result, dict):
        return
    if normalize_cloud(agent_result.get("cloud")) != "azure":
        return
    if (agent_result.get("workflow") or "").strip() != "azure_consumer_generation":
        return

    routing_summary = agent_result.get("routing_summary") or {}
    if not routing_summary:
        return

    target_consumer = normalize_agent_relative_tf_path(routing_summary.get("consumer_file") or "", "azure")
    target_tfvars = normalize_agent_relative_tf_path(routing_summary.get("tfvars_file") or "", "azure")
    files = agent_result.get("files") or []
    filenames = {
        normalize_agent_relative_tf_path((file_data or {}).get("filename") or "", "azure")
        for file_data in files
    }

    missing = [path for path in (target_consumer, target_tfvars) if path and path not in filenames]
    if missing:
        raise ValueError(
            "Azure existing-module consumer PRs must include both backend-routed files. "
            f"Missing file(s): {', '.join(missing)}"
        )

    if not any(name.endswith(".tfvars") for name in filenames):
        raise ValueError(
            "Azure existing-module consumer PRs must include the backend-selected tfvars file with variable values."
        )

    # Final pre-commit guard: variables.tf may be generated by the backend
    # from a copied object variable block. A missing final variable-block brace
    # must be corrected before GitHub writes, otherwise terraform fmt/validate
    # fails with "Unclosed configuration block".
    for file_data in files:
        if not isinstance(file_data, dict):
            continue
        filename = normalize_agent_relative_tf_path((file_data.get("filename") or ""), "azure")
        if filename != "variables.tf" and not filename.endswith("/variables.tf"):
            continue
        file_data["content"] = _repair_unclosed_variables_tf_content_for_write(
            None,
            file_data.get("content") or "",
            filename,
        )
validate_azure_consumer_two_file_payload_for_commit = validate_azure_consumer_two_file_payload_for_commit_stage1


def _find_agent_file_by_name_or_suffix(files: list[dict], target_filename: str, suffix: str = "") -> dict:
    target_filename = (target_filename or "").strip()
    for file_data in files or []:
        if (file_data.get("filename") or "") == target_filename:
            return file_data
    if suffix:
        for file_data in files or []:
            if (file_data.get("filename") or "").endswith(suffix):
                return file_data
    return {}



def _strip_hcl_inline_comment(value: str) -> str:
    text = (value or "").strip()
    in_string = False
    escape_next = False
    for idx, ch in enumerate(text):
        if in_string:
            if escape_next:
                escape_next = False
            elif ch == "\\":
                escape_next = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "#":
            return text[:idx].rstrip()
        if ch == "/" and idx + 1 < len(text) and text[idx + 1] == "/":
            return text[:idx].rstrip()
    return text


def _hcl_expression_is_literal(value: str) -> bool:
    expr = _strip_hcl_inline_comment(value).strip()
    if not expr:
        return False
    lowered = expr.lower()
    if lowered in {"true", "false", "null"}:
        return True
    if re.fullmatch(r"-?\d+(?:\.\d+)?", expr):
        return True
    return expr[0] in {'"', "'", "[", "{"}


def _hcl_expression_is_repo_pattern(value: str) -> bool:
    expr = _strip_hcl_inline_comment(value).strip()
    lowered = expr.lower()
    dynamic_prefixes = (
        "var.",
        "local.",
        "data.",
        "module.",
        "azurerm_",
        "lookup(",
        "merge(",
        "try(",
        "coalesce(",
        "format(",
        "concat(",
        "toset(",
        "tolist(",
        "tomap(",
        "flatten(",
    )
    return bool(lowered.startswith(dynamic_prefixes) or "var." in lowered or "local." in lowered)


def _parse_module_assignment_lines(module_block: str) -> dict[str, dict[str, str]]:
    assignments: dict[str, dict[str, str]] = {}
    for line in (module_block or "").splitlines():
        match = re.match(r'^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$', line)
        if not match:
            continue
        key = match.group(2)
        value = match.group(3).strip()
        assignments[key] = {
            "line": line.rstrip(),
            "value": value,
        }
    return assignments


def _replace_module_assignment_line(module_block: str, key: str, new_line: str) -> str:
    pattern = rf'(?m)^\s*{re.escape(key)}\s*=.*$'
    if re.search(pattern, module_block):
        return re.sub(pattern, new_line.rstrip(), module_block, count=1)
    return module_block


def _ensure_module_source_line(module_block: str, module_source_url: str) -> str:
    source_line = f'  source = "{module_source_url}"'
    if re.search(r'(?m)^\s*source\s*=', module_block):
        return re.sub(r'(?m)^\s*source\s*=.*$', source_line, module_block, count=1)

    lines = module_block.splitlines()
    if len(lines) <= 1:
        return module_block
    return "\n".join([lines[0], source_line, *lines[1:]])


def _module_name_from_module_block(module_block: str) -> str:
    match = re.search(r'module\s+"([^"]+)"\s*\{', module_block or "", re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _terraform_safe_variable_name(value: str) -> str:
    name = (value or "").strip().replace("-", "_").lower()
    name = re.sub(r"[^a-z0-9_]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    if not name:
        return ""
    if not re.match(r"^[a-z_]", name):
        name = f"var_{name}"
    return name


def _tfvars_object_name_from_module_name(module_name: str) -> str:
    name = _terraform_safe_variable_name(module_name)
    for prefix in ("azurerm_", "azure_", "tf_azure_", "module_"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    return _terraform_safe_variable_name(name)


def _tfvars_object_name_from_module_block(module_block: str) -> str:
    return _tfvars_object_name_from_module_name(_module_name_from_module_block(module_block))


def _module_assignment_order(module_block: str) -> list[str]:
    ordered = []
    for line in (module_block or "").splitlines():
        match = re.match(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=', line)
        if not match:
            continue
        key = match.group(1)
        if key not in ordered:
            ordered.append(key)
    return ordered


def _module_assignment_indent(module_block: str, fallback: str = "  ") -> str:
    for line in (module_block or "").splitlines():
        match = re.match(r'^(\s+)[A-Za-z_][A-Za-z0-9_]*\s*=', line)
        if match:
            return match.group(1)
    return fallback


def _module_block_replace_assignment_lines(module_block: str, replacements: dict[str, str]) -> str:
    if not replacements:
        return module_block

    output = []
    for line in (module_block or "").splitlines():
        match = re.match(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=', line)
        if match and match.group(1) in replacements:
            output.append(replacements[match.group(1)].rstrip())
        else:
            output.append(line.rstrip())
    return "\n".join(output)


def _insert_module_assignment_lines_before_close(module_block: str, new_lines: list[str]) -> str:
    if not new_lines:
        return (module_block or "").rstrip()

    lines = (module_block or "").rstrip().splitlines()
    if not lines:
        return "\n".join(new_lines).rstrip()

    close_idx = -1
    for idx in range(len(lines) - 1, -1, -1):
        if lines[idx].strip() == "}":
            close_idx = idx
            break

    normalized_new_lines = [line.rstrip() for line in new_lines if (line or "").strip()]
    if close_idx == -1:
        return "\n".join(lines + normalized_new_lines).rstrip()

    before = lines[:close_idx]
    after = lines[close_idx:]
    if before and before[-1].strip():
        before.append("")
    return "\n".join(before + normalized_new_lines + after).rstrip()


def _module_object_field_from_pattern_expression(pattern_expression: str, object_root: str) -> str:
    object_root = (object_root or "").strip()
    if not object_root:
        return ""
    expression = (pattern_expression or "").strip()

    match = re.search(
        rf'\bvar\.{re.escape(object_root)}\.([A-Za-z_][A-Za-z0-9_]*)\b',
        expression,
    )
    if match:
        return match.group(1)

    match = re.search(
        rf'lookup\(\s*var\.{re.escape(object_root)}\s*,\s*"([A-Za-z_][A-Za-z0-9_]*)"',
        expression,
    )
    if match:
        return match.group(1)

    return ""


def _module_object_field_for_input(input_name: str, pattern_expression: str = "", source_object_root: str = "") -> str:
    pattern_field = _module_object_field_from_pattern_expression(pattern_expression, source_object_root)
    if pattern_field:
        return pattern_field

    name = _terraform_safe_variable_name(input_name)
    generic_prefixes = (
        "storage_account_",
        "key_vault_",
        "mysql_",
        "postgres_",
        "mssql_",
        "redis_",
        "function_app_",
        "app_service_",
    )
    for prefix in generic_prefixes:
        if name.startswith(prefix) and len(name) > len(prefix):
            return name[len(prefix):]
    return name

def _dominant_object_var_root(module_block: str) -> str:
    counts: dict[str, int] = {}
    for root in re.findall(r"\bvar\.([A-Za-z_][A-Za-z0-9_]*)\s*\.", module_block or ""):
        counts[root] = counts.get(root, 0) + 1
    for root in re.findall(r"\blookup\(\s*var\.([A-Za-z_][A-Za-z0-9_]*)\s*,", module_block or ""):
        counts[root] = counts.get(root, 0) + 1
    if not counts:
        return ""
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _rewrite_var_root_reference(value: str, old_root: str, new_root: str) -> str:
    old_root = (old_root or "").strip()
    new_root = (new_root or "").strip()
    if not old_root or not new_root or old_root == new_root:
        return value
    return re.sub(
        rf"\bvar\.{re.escape(old_root)}(?=\.|\[|\s*,|\))",
        f"var.{new_root}",
        value or "",
    )

def _extract_top_level_module_assignments(module_block: str) -> list[dict]:
    """Extract top-level module arguments while preserving multi-line HCL values.

    This correctly handles nested object/list values such as:

      app_settings = {
        settings = {
          site_config = {}
        }
      }

    The older line-based parser could copy nested assignment lines without their
    closing braces, which produced malformed Terraform.
    """
    text = (module_block or "").replace("\r\n", "\n").rstrip()
    if not text:
        return []

    lines = text.splitlines()
    header_idx = -1

    for idx, line in enumerate(lines):
        if re.match(r'^\s*module\s+"[^"]+"\s*\{\s*$', line):
            header_idx = idx
            break

    if header_idx < 0:
        return []

    assignments: list[dict] = []
    depth = 1
    i = header_idx + 1

    while i < len(lines):
        line = lines[i].rstrip()

        if depth == 1 and line.strip() == "}":
            break

        match = re.match(r'^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*=', line)

        if depth == 1 and match:
            key = match.group(2)
            indent = match.group(1)
            collected = []
            local_depth = depth

            while i < len(lines):
                current_line = lines[i].rstrip()

                if collected and local_depth == 1:
                    if current_line.strip() == "}" or re.match(
                        r'^\s*[A-Za-z_][A-Za-z0-9_]*\s*=',
                        current_line,
                    ):
                        break

                collected.append(current_line)
                local_depth += _hcl_curly_balance(current_line)
                i += 1

            assignment_text = "\n".join(collected).rstrip()
            value = assignment_text.split("=", 1)[1].strip() if "=" in assignment_text else ""

            assignments.append({
                "key": key,
                "indent": indent,
                "text": assignment_text,
                "value": value,
            })

            depth = local_depth
            continue

        depth += _hcl_curly_balance(line)
        i += 1

    return assignments


def _module_header_line_from_block(module_block: str, fallback_name: str = "azure_module") -> str:
    match = re.search(
        r'(?m)^\s*module\s+"([^"]+)"\s*\{\s*$',
        module_block or "",
        re.IGNORECASE,
    )
    if match:
        return match.group(0).rstrip()

    safe_name = _terraform_safe_variable_name(fallback_name) or "azure_module"
    return f'module "{safe_name}" {{'

def _hcl_collection_balance(value: str) -> int:
    """Return bracket/brace/paren balance while ignoring quoted strings.

    This is intentionally lightweight and is only used to decide whether a
    generated assignment is single-line. A line such as
    `identity_ids = [azurerm_identity.example.id]` has a zero balance and can
    be aligned, while `app_settings = {` or `containers = [` has a positive
    balance and must be left untouched.
    """
    pairs = {"{": "}", "[": "]", "(": ")"}
    closing = set(pairs.values())
    stack: list[str] = []
    in_string = False
    escape_next = False

    for ch in value or "":
        if in_string:
            if escape_next:
                escape_next = False
            elif ch == "\\":
                escape_next = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch in pairs:
            stack.append(pairs[ch])
        elif ch in closing:
            if stack and stack[-1] == ch:
                stack.pop()
            else:
                return -1

    return len(stack)


def _is_single_line_top_level_hcl_assignment(line: str, current_depth: int) -> bool:
    """True only for direct single-line module attributes.

    Multiline assignments like `app_settings = {` are deliberately excluded so
    nested object/list bodies are preserved exactly.
    """
    if current_depth != 1:
        return False

    stripped = (line or "").strip()
    if not stripped or stripped.startswith(("#", "//")):
        return False
    if stripped == "}":
        return False

    match = re.match(r'^\s*[A-Za-z_][A-Za-z0-9_]*\s*=\s*.+$', line or "")
    if not match:
        return False

    # Do not align lines that begin a multiline object/list/tuple or otherwise
    # have unclosed delimiters. This keeps blocks like app_settings = { intact.
    return _hcl_collection_balance(line) == 0


def _align_single_line_assignments_in_generated_hcl_block(block: str) -> str:
    """Align direct single-line attributes in one generated Terraform block.

    This mimics the part of `terraform fmt` that caused the pipeline failure,
    but it is scoped to the backend-generated block only. Existing file content
    and multiline assignments remain unchanged.
    """
    lines = (block or "").replace("\r\n", "\n").rstrip().splitlines()
    if not lines:
        return ""

    output: list[str] = []
    run: list[str] = []
    depth = 0

    def flush_run() -> None:
        nonlocal run
        if not run:
            return

        parsed = []
        max_key_len = 0
        for run_line in run:
            match = re.match(r'^(\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*)=(\s*)(.*)$', run_line)
            if not match:
                output.append(run_line.rstrip())
                continue
            indent, key, _pre_eq, _post_eq, value = match.groups()
            max_key_len = max(max_key_len, len(key))
            parsed.append((indent, key, value.rstrip()))

        if len(parsed) != len(run):
            # Defensive fallback: preserve the original run if any line was not
            # assignment-shaped after all.
            output.extend(line.rstrip() for line in run)
        else:
            for indent, key, value in parsed:
                spaces = " " * (max_key_len - len(key) + 1)
                output.append(f"{indent}{key}{spaces}= {value}".rstrip())

        run = []

    for line in lines:
        current_depth = depth

        if _is_single_line_top_level_hcl_assignment(line, current_depth):
            run.append(line.rstrip())
        else:
            flush_run()
            output.append(line.rstrip())

        depth += _hcl_curly_balance(line)

    flush_run()
    return "\n".join(output).rstrip()


def _format_generated_module_block_for_terraform_fmt(module_block: str) -> str:
    """Format only a generated module block enough to satisfy terraform fmt.

    The backend still preserves the surrounding existing .tf file byte-for-byte;
    this helper is called only on the newly generated/repaired module block
    before it is appended or used to replace an invalid generated tail.
    """
    formatted = _align_single_line_assignments_in_generated_hcl_block(module_block)
    return formatted.rstrip()



def _assignment_uses_object_root(assignment_value: str, object_root: str) -> bool:
    object_root = (object_root or "").strip()
    value = (assignment_value or "").strip()

    if not object_root or not value:
        return False

    if _module_object_field_from_pattern_expression(value, object_root):
        return True

    return bool(
        re.search(
            rf'\bvar\.{re.escape(object_root)}(?=\.|\[|\s*,|\))',
            value,
        )
    )


def _normalized_user_selected_assignment_names(user_selected_assignments: dict | None) -> set[str]:
    result = set()
    for key in (user_selected_assignments or {}).keys():
        safe_key = _terraform_safe_variable_name(key)
        if safe_key:
            result.add(safe_key)
    return result

def _rewrite_azure_module_block_with_existing_pattern(
    new_block: str,
    matched_existing_block: str,
    module_source_url: str,
    allowed_input_names: list[str] | set[str] | None = None,
    user_selected_assignments: dict | None = None,
) -> str:
    """Rewrite a new source-matched Azure module block to repo style.

    The backend-selected existing module invocation is the formatting and value
    routing template. This version preserves complete multi-line top-level
    assignments from the matched block, including nested object/list values.

    It also routes explicitly user-provided scalar inputs, such as:

      function_app_name = "Test123"

    into:

      function_app_name = var.function_app_name

    so the routed tfvars file can receive the value and the PR is not rejected
    as unchanged.
    """
    block = (new_block or "").replace("\r\n", "\n").rstrip()
    pattern_block = (matched_existing_block or "").replace("\r\n", "\n").rstrip()

    if not block or not pattern_block:
        return _ensure_module_source_line(new_block, module_source_url).rstrip()

    allowed = set(allowed_input_names or [])
    user_selected_names = _normalized_user_selected_assignment_names(user_selected_assignments)

    pattern_assignments = _extract_top_level_module_assignments(pattern_block)
    current_assignments = {
        item["key"]: item
        for item in _extract_top_level_module_assignments(block)
        if item.get("key")
    }

    pattern_object_root = _dominant_object_var_root(pattern_block)
    target_object_root = _tfvars_object_name_from_module_block(block) or pattern_object_root
    indent = _module_assignment_indent(pattern_block) or _module_assignment_indent(block)

    header = _module_header_line_from_block(
        block,
        fallback_name=_module_name_from_module_block(block) or "azure_module",
    )

    source_line = f'{indent}source = "{module_source_url}"'

    body_lines = [header, source_line, ""]
    included_keys = {"source"}

    for assignment in pattern_assignments:
        key = assignment.get("key") or ""
        if not key or key == "source":
            continue

        if allowed and key not in allowed:
            continue

        assignment_text = assignment.get("text") or ""
        assignment_value = assignment.get("value") or ""
        safe_key = _terraform_safe_variable_name(key)

        uses_object_root = _assignment_uses_object_root(
            assignment_value,
            pattern_object_root,
        )

        # If the user explicitly supplied a scalar module input value, route the
        # module argument through a root variable so the tfvars update is real.
        #
        # Do not do this for object-backed patterns such as:
        # storage_account_tier = var.storage_account_zrs.account_tier
        # Those must remain object-backed and only have the object root renamed.
        if safe_key in user_selected_names and not uses_object_root:
            assignment_text = f"{indent}{key} = var.{safe_key}"
        elif pattern_object_root and target_object_root and pattern_object_root != target_object_root:
            assignment_text = _rewrite_var_root_reference(
                assignment_text,
                pattern_object_root,
                target_object_root,
            )

        body_lines.append(assignment_text.rstrip())
        included_keys.add(key)

    extra_lines = []

    for key, current_data in current_assignments.items():
        if key in included_keys or key == "source":
            continue

        if allowed and key not in allowed:
            continue

        safe_key = _terraform_safe_variable_name(key)
        current_value = current_data.get("value") or ""

        if safe_key in user_selected_names:
            extra_lines.append(f"{indent}{key} = var.{safe_key}")
            included_keys.add(key)
            continue

        if _hcl_expression_is_literal(current_value) and target_object_root:
            field_name = _module_object_field_for_input(
                key,
                source_object_root=pattern_object_root,
            )
            if field_name:
                extra_lines.append(f"{indent}{key} = var.{target_object_root}.{field_name}")
                included_keys.add(key)
                continue

        extra_text = current_data.get("text") or f"{indent}{key} = {current_value}"
        extra_lines.append(extra_text.rstrip())
        included_keys.add(key)

    if extra_lines:
        if body_lines and body_lines[-1].strip():
            body_lines.append("")
        body_lines.extend(extra_lines)

    while body_lines and not body_lines[-1].strip():
        body_lines.pop()

    body_lines.append("}")

    result = "\n".join(body_lines).rstrip()
    result = _ensure_module_source_line(result, module_source_url).rstrip()
    result = _format_generated_module_block_for_terraform_fmt(result)

    _assert_balanced_terraform_content(
        result,
        "Azure consumer module block",
        "module pattern rewrite",
    )

    return result


def _new_matching_module_blocks(existing_consumer: str, consumer_content: str, module_source_url: str) -> list[dict]:
    existing = (existing_consumer or "").replace("\r\n", "\n")
    results = []
    for block in _extract_top_level_tf_blocks((consumer_content or "").replace("\r\n", "\n")):
        header = block.get("header") or ""
        block_text = block.get("block") or ""
        if not re.match(r'^module\s+"[^"]+"$', header):
            continue
        if module_source_url not in block_text:
            continue
        if block_text.strip() and block_text.strip() in existing:
            continue
        results.append(block)
    return results

def _find_unbalanced_source_matched_module_tail(
    consumer_content: str,
    module_source_url: str,
) -> tuple[int, int, str]:
    """Return the malformed trailing module block that contains module_source_url.

    _extract_top_level_tf_blocks intentionally ignores incomplete blocks. That
    is normally good, but for Azure source-matched generation it means a bad
    appended module like:

      module "function_app_custom" {
        source = "..."
        app_settings = {
          ...

    can bypass the source-pattern rewrite and reach terraform fmt. This helper
    finds that exact unbalanced appended tail so the backend can rewrite it from
    the known-good matched module block before preview/commit.
    """
    text = (consumer_content or "").replace("\r\n", "\n")
    source = (module_source_url or "").strip()
    if not text or not source or source not in text:
        return (-1, -1, "")

    source_idx = text.rfind(source)
    module_starts = list(re.finditer(r'(?m)^\s*module\s+"[^"]+"\s*\{', text))
    candidate_start = -1

    for match in module_starts:
        if match.start() <= source_idx:
            candidate_start = match.start()
        else:
            break

    if candidate_start < 0:
        return (-1, -1, "")

    tail = text[candidate_start:].rstrip()
    if not tail:
        return (-1, -1, "")

    # If the tail is already balanced, normal block extraction/rewrite handles it.
    if _hcl_curly_balance(tail) <= 0:
        return (-1, -1, "")

    return (candidate_start, len(text), tail)


def _assert_balanced_terraform_content(
    content: str,
    filename: str,
    context: str,
) -> None:
    """Fail fast before a malformed Terraform file is previewed or committed."""
    balance = _hcl_curly_balance((content or "").replace("\r\n", "\n"))
    if balance > 0:
        raise ValueError(
            f"Generated Terraform for {filename} is missing {balance} closing brace(s) "
            f"after {context}. No PR preview was created."
        )
    if balance < 0:
        raise ValueError(
            f"Generated Terraform for {filename} has extra closing brace(s) "
            f"after {context}. No PR preview was created."
        )

def _repair_azure_consumer_module_invocations(
    existing_consumer: str,
    consumer_content: str,
    routing_context: dict,
    module_source_url: str,
    allowed_input_names: list[str] | set[str] | None = None,
    user_selected_assignments: dict | None = None,
) -> str:
    matched_existing_block = (routing_context or {}).get("matched_module_block") or ""
    if not matched_existing_block:
        return consumer_content

    updated = (consumer_content or "").replace("\r\n", "\n").rstrip() + "\n"

    for block in _new_matching_module_blocks(existing_consumer, updated, module_source_url):
        old_block = (block.get("block") or "").rstrip()
        if not old_block:
            continue

        new_block = _rewrite_azure_module_block_with_existing_pattern(
            new_block=old_block,
            matched_existing_block=matched_existing_block,
            module_source_url=module_source_url,
            allowed_input_names=allowed_input_names,
            user_selected_assignments=user_selected_assignments,
        )

        if new_block and new_block != old_block:
            updated = updated.replace(old_block, new_block, 1)

    # Important: malformed generated module blocks are not returned by
    # _extract_top_level_tf_blocks, so the normal rewrite above cannot see them.
    # Rewrite the trailing unbalanced source-matched block from the known-good
    # existing source-matched module pattern.
    tail_start, tail_end, tail_block = _find_unbalanced_source_matched_module_tail(
        updated,
        module_source_url,
    )

    if tail_start >= 0 and tail_block:
        repaired_block = _rewrite_azure_module_block_with_existing_pattern(
            new_block=tail_block,
            matched_existing_block=matched_existing_block,
            module_source_url=module_source_url,
            allowed_input_names=allowed_input_names,
            user_selected_assignments=user_selected_assignments,
        ).rstrip()

        if not repaired_block or _hcl_curly_balance(repaired_block) != 0:
            raise ValueError(
                "Generated Azure consumer module block is malformed and could not be repaired "
                "from the source-matched existing module pattern. No PR preview was created."
            )

        updated = (
            updated[:tail_start].rstrip()
            + "\n\n"
            + repaired_block
            + "\n"
            + updated[tail_end:].lstrip()
        )

    _assert_balanced_terraform_content(
        updated,
        "Azure consumer module invocation file",
        "source-matched module rewrite",
    )

    return updated.rstrip() + "\n"


def _extract_var_roots_from_text(hcl_text: str) -> set[str]:
    return {
        match.group(1)
        for match in re.finditer(r'\bvar\.([A-Za-z_][A-Za-z0-9_]*)\b', hcl_text or "")
    }


def _split_top_level_hcl_fragments(text: str, separators: set[str] | None = None) -> list[str]:
    separators = separators or {",", "\n"}
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    in_string = False
    escape_next = False

    for ch in text or "":
        if in_string:
            current.append(ch)
            if escape_next:
                escape_next = False
            elif ch == "\\":
                escape_next = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            current.append(ch)
            continue
        if ch in "[{(":
            depth += 1
            current.append(ch)
            continue
        if ch in "]})":
            if depth > 0:
                depth -= 1
            current.append(ch)
            continue
        if ch in separators and depth == 0:
            fragment = "".join(current).strip()
            if fragment:
                parts.append(fragment)
            current = []
            continue
        current.append(ch)

    fragment = "".join(current).strip()
    if fragment:
        parts.append(fragment)
    return parts



def _split_top_level_hcl_commas(text: str) -> list[str]:
    """Split a short HCL assignment line on commas outside strings/collections."""
    parts = []
    start = 0
    depth = 0
    in_string = False
    escape_next = False
    value = text or ""

    for idx, ch in enumerate(value):
        if in_string:
            if escape_next:
                escape_next = False
            elif ch == "\\":
                escape_next = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch in "[{(":
            depth += 1
        elif ch in "]})" and depth > 0:
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(value[start:idx].strip())
            start = idx + 1

    parts.append(value[start:].strip())
    return [part for part in parts if part]


def _normalize_inline_hcl_assignments(content: str) -> str:
    """Normalize one-line comma-separated HCL assignments into one per line.

    Users often reply with values such as:
    storage_account_tier = "Standard", storage_account_replication = "ZRS"

    Terraform tfvars files do not use commas between top-level assignments, so
    normalize only when every comma-separated segment is assignment-shaped.
    Existing multi-line object/list values are preserved.
    """
    output_lines = []
    for line in (content or "").replace("\r\n", "\n").splitlines():
        parts = _split_top_level_hcl_commas(line)
        if len(parts) > 1 and all(
            re.match(r'^\s*[A-Za-z_][A-Za-z0-9_]*\s*=', part)
            for part in parts
        ):
            output_lines.extend(parts)
        else:
            output_lines.append(line)
    return "\n".join(output_lines)


def _extract_tfvars_assignments_from_text(content: str) -> dict[str, str]:
    """Extract assignment values from HCL/tfvars text without reading nested fields.

    This parser is used for user overrides and generated tfvars snippets. It
    must not treat nested object fields, lifecycle rules, filters, or actions as
    root tfvars assignments. For object literal overrides, the outer braces are
    intentionally stripped so object fields can be merged into the generated
    object value.
    """
    text = (content or "").replace("\r\n", "\n").strip()
    if not text:
        return {}

    # Accept a bare object literal passed as an override for an object variable.
    if text.startswith("{") and text.endswith("}"):
        text = text[1:-1].strip()

    text = _normalize_inline_hcl_assignments(text)

    assignments: dict[str, str] = {}
    for name in _extract_top_level_hcl_assignment_names(text):
        if not name or name in assignments:
            continue
        start, end = _top_level_tfvars_assignment_span(text, name)
        if start < 0 or end < 0:
            continue
        assignment = text[start:end]
        if "=" not in assignment:
            continue
        value = assignment.split("=", 1)[1].strip()
        if value:
            assignments[name] = value
    return assignments

def _python_value_to_hcl(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[", "(")) or stripped.lower() in {"true", "false", "null"}:
            return stripped
        if re.fullmatch(r"-?\d+(?:\.\d+)?", stripped):
            return stripped
        return json.dumps(value)
    return json.dumps(value, indent=2)


def _extract_tfvars_assignments_from_json_text(content: str) -> dict[str, str]:
    text = (content or "").strip()
    if not text:
        return {}

    try:
        data = json.loads(text)
    except Exception:
        try:
            data = json.loads(extract_first_balanced_json_object(text))
        except Exception:
            return {}

    if not isinstance(data, dict):
        return {}

    values = data.get("values") or data.get("tfvars") or data.get("assignments") or data
    if not isinstance(values, dict):
        return {}

    result: dict[str, str] = {}
    for key, value in values.items():
        name = str(key or "").strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            continue
        result[name] = _python_value_to_hcl(value).strip()
    return result


def _find_hcl_assignment_span(hcl_content: str, assignment_name: str) -> tuple[int, int]:
    text = (hcl_content or "").replace("\r\n", "\n")
    assignment_name = (assignment_name or "").strip()
    if not text or not assignment_name:
        return (-1, -1)

    pattern = rf'(?m)^[ \t]*{re.escape(assignment_name)}[ \t]*=[ \t]*'
    match = re.search(pattern, text)
    if not match:
        return (-1, -1)

    value_start = match.end()
    first_non_space = value_start
    while first_non_space < len(text) and text[first_non_space] in " \t":
        first_non_space += 1

    if first_non_space >= len(text):
        return (match.start(), value_start)

    first_char = text[first_non_space]
    if first_char not in "[{(":
        line_end = text.find("\n", value_start)
        if line_end == -1:
            line_end = len(text)
        else:
            line_end += 1
        return (match.start(), line_end)

    close_char = {"[": "]", "{": "}", "(": ")"}[first_char]
    depth = 0
    in_string = False
    escape_next = False
    for idx in range(first_non_space, len(text)):
        ch = text[idx]
        if in_string:
            if escape_next:
                escape_next = False
            elif ch == "\\":
                escape_next = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == first_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                end = idx + 1
                if end < len(text) and text[end] == "\n":
                    end += 1
                return (match.start(), end)

    return (match.start(), len(text))


def _replace_top_level_tfvars_assignment_base(tfvars_content: str, variable_name: str, value: str) -> str:
    text = (tfvars_content or "").replace("\r\n", "\n")
    start, end = _find_hcl_assignment_span(text, variable_name)
    if start < 0 or end < 0:
        return text

    replacement = f"{variable_name} = {(value or '').strip()}\n"
    return text[:start] + replacement + text[end:]


def _generated_tfvars_assignment_should_be_replaced(
    existing_tfvars: str,
    generated_tfvars: str,
    variable_name: str,
    candidate_value: str,
) -> bool:
    if not variable_name or not candidate_value:
        return False
    if _has_top_level_tfvars_assignment(existing_tfvars, variable_name):
        return False
    if not _has_top_level_tfvars_assignment(generated_tfvars, variable_name):
        return False

    generated_value = _extract_hcl_assignment_value(generated_tfvars, variable_name).strip()
    candidate = (candidate_value or "").strip()
    if not generated_value:
        return True
    if generated_value in {"{}", "[]"}:
        return True
    if "= []" in generated_value and "= []" not in candidate:
        return True
    if generated_value.startswith("{") and candidate.startswith("{"):
        generated_keys = set(re.findall(r'(?m)^[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]*=', generated_value))
        candidate_keys = set(re.findall(r'(?m)^[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]*=', candidate))
        if candidate_keys and not candidate_keys.issubset(generated_keys):
            return True
        if len(candidate) > max(len(generated_value) * 2, len(generated_value) + 80):
            return True
    return False

def _user_selected_tfvars_assignments(retrieved_value_context: list | None = None) -> dict[str, str]:
    reply = ""
    for item in retrieved_value_context or []:
        if not isinstance(item, dict):
            continue
        if item.get("source") == "backend_azure_consumer_value_selection" and item.get("confirmed"):
            reply = (item.get("user_reply") or "").strip()
            break

    if not reply:
        return {}

    normalized = normalize_yes_no_reply(reply)
    if normalized in {"use suggested values", "use suggestions", "use suggested", "suggested", "yes", "y", "proceed", "continue"}:
        return {}

    fenced = re.search(r"```(?:json|hcl|terraform|tfvars)?\s*(.*?)```", reply, re.DOTALL | re.IGNORECASE)
    if fenced:
        reply = fenced.group(1)

    json_assignments = _extract_tfvars_assignments_from_json_text(reply)
    if json_assignments:
        return json_assignments

    return _extract_tfvars_assignments_from_text(reply)



def _has_top_level_tfvars_assignment(tfvars_content: str, variable_name: str) -> bool:
    variable_name = (variable_name or "").strip()
    if not variable_name:
        return False
    return variable_name in set(_extract_top_level_hcl_assignment_names(tfvars_content or ""))


def _top_level_tfvars_assignment_span(tfvars_content: str, variable_name: str) -> tuple[int, int]:
    text = (tfvars_content or "").replace("\r\n", "\n")
    variable_name = (variable_name or "").strip()
    if not text or not variable_name:
        return -1, -1

    match = None
    for candidate in re.finditer(r'(?m)^[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*', text):
        if candidate.group(1) != variable_name:
            continue
        if _hcl_nesting_depth_at_position(text, candidate.start()) != 0:
            continue
        match = candidate
        break

    if not match:
        return -1, -1

    start = match.start()
    value_start = match.end()
    idx = value_start
    while idx < len(text) and text[idx] in " \t":
        idx += 1

    if idx >= len(text):
        return start, len(text)

    if text[idx] not in "[{(":
        line_end = text.find("\n", idx)
        if line_end == -1:
            line_end = len(text)
        return start, line_end

    open_ch = text[idx]
    close_ch = {"[": "]", "{": "}", "(": ")"}[open_ch]
    depth = 0
    in_string = False
    escape_next = False

    for pos in range(idx, len(text)):
        ch = text[pos]
        if in_string:
            if escape_next:
                escape_next = False
            elif ch == "\\":
                escape_next = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return start, pos + 1

    return start, len(text)

def _replace_top_level_tfvars_assignment(tfvars_content: str, variable_name: str, value: str) -> str:
    text = (tfvars_content or "").replace("\r\n", "\n")
    start, end = _top_level_tfvars_assignment_span(text, variable_name)
    if start < 0 or end < 0:
        return text

    replacement = f"{variable_name} = {(value or '').strip()}".rstrip()
    prefix = text[:start]
    suffix = text[end:]
    if suffix and not suffix.startswith("\n"):
        replacement += "\n"
    elif not suffix:
        replacement += "\n"
    return prefix + replacement + suffix



def _top_level_tfvars_assignment_field_names(value: str) -> set[str]:
    body = (value or "").replace("\r\n", "\n").strip()
    if body.startswith("{") and body.endswith("}"):
        body = body[1:-1]
    return set(_extract_top_level_hcl_assignment_names(body))

def _assignment_span_from_match(text: str, match: re.Match) -> tuple[int, int]:
    """Return the full HCL assignment span for a regex match ending after '='."""
    value_start = match.end()
    idx = value_start
    while idx < len(text) and text[idx] in " \t":
        idx += 1

    if idx >= len(text):
        return match.start(), len(text)

    if text[idx] not in "[{(":
        line_end = text.find("\n", idx)
        if line_end == -1:
            return match.start(), len(text)
        return match.start(), line_end

    open_ch = text[idx]
    close_ch = {"[": "]", "{": "}", "(": ")"}[open_ch]
    depth = 0
    in_string = False
    escape_next = False

    for pos in range(idx, len(text)):
        ch = text[pos]
        if in_string:
            if escape_next:
                escape_next = False
            elif ch == "\\":
                escape_next = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return match.start(), pos + 1

    return match.start(), len(text)


