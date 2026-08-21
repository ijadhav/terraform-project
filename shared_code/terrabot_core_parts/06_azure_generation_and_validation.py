from __future__ import annotations
def _top_level_hcl_assignment_spans(hcl_content: str) -> list[dict]:
    """Return top-level assignment spans, including duplicate names."""
    text = (hcl_content or "").replace("\r\n", "\n")
    spans: list[dict] = []

    for match in re.finditer(r'(?m)^[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*', text):
        if _hcl_nesting_depth_at_position(text, match.start()) != 0:
            continue

        start, end = _assignment_span_from_match(text, match)
        spans.append({
            "name": match.group(1).strip(),
            "start": start,
            "end": end,
            "text": text[start:end],
        })

    return spans


def _dedupe_hcl_object_top_level_fields(object_value: str) -> str:
    """Remove duplicate root fields inside an HCL object literal, keeping the last value."""
    text = (object_value or "").replace("\r\n", "\n").strip()
    if not (text.startswith("{") and text.endswith("}")):
        return object_value

    inner = text[1:-1]
    spans = _top_level_hcl_assignment_spans(inner)
    if not spans:
        return text

    last_by_name: dict[str, int] = {}
    for idx, span in enumerate(spans):
        last_by_name[span["name"]] = idx

    remove_ranges = [
        (span["start"], span["end"])
        for idx, span in enumerate(spans)
        if last_by_name.get(span["name"]) != idx
    ]

    if not remove_ranges:
        return text

    new_inner = inner
    for start, end in sorted(remove_ranges, reverse=True):
        if end < len(new_inner) and new_inner[end:end + 1] == "\n":
            end += 1
        new_inner = new_inner[:start] + new_inner[end:]

    return "{" + new_inner.rstrip() + "\n}"


def _hcl_single_line_collection_is_complete(value: str) -> bool:
    """Return true when a one-line HCL collection/call value closes on that line."""
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
        elif ch in "[{(":
            depth += 1
        elif ch in "]})" and depth > 0:
            depth -= 1

    return depth == 0


def _hcl_assignment_value_starts_multiline(value: str) -> bool:
    """Terraform fmt does not align arguments whose value opens a multi-line collection."""
    expr = _strip_hcl_inline_comment(value).strip() if "_strip_hcl_inline_comment" in globals() else (value or "").strip()
    if not expr or expr[0] not in "[{(":
        return False
    return not _hcl_single_line_collection_is_complete(expr)


def _format_hcl_assignment_alignment(hcl_content: str) -> str:
    """Normalize Terrabot-generated HCL snippets to Terraform fmt style.

    Terraform fmt aligns consecutive scalar assignments, but it does not align
    an assignment whose value starts a multi-line list/object/call. For example,
    fmt wants `containers = [` and `lifecycle_rules = [` while still aligning
    nearby scalar values such as `account_tier` and `account_replication`.
    """
    lines = (hcl_content or "").replace("\r\n", "\n").split("\n")
    output: list[str] = []
    group: list[tuple[str, str, str]] = []

    def flush_group() -> None:
        nonlocal group
        if not group:
            return

        max_name_len = max(len(name) for _, name, _ in group)
        for indent, name, value in group:
            output.append(f"{indent}{name}{' ' * (max_name_len - len(name) + 1)}= {value}")

        group = []

    for line in lines:
        match = re.match(r'^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$', line)
        if match:
            indent, name, value = match.group(1), match.group(2), match.group(3)
            if _hcl_assignment_value_starts_multiline(value):
                flush_group()
                output.append(f"{indent}{name} = {value}".rstrip())
                continue
            if group and group[-1][0] != indent:
                flush_group()
            group.append((indent, name, value))
            continue

        flush_group()
        output.append(line.rstrip())

    flush_group()
    return "\n".join(output).rstrip() + "\n"


def _normalize_generated_hcl_value(value: str) -> str:
    """Normalize generated HCL values before appending/replacing them."""
    normalized = (value or "").replace("\r\n", "\n").strip()
    if normalized.startswith("{") and normalized.endswith("}"):
        normalized = _dedupe_hcl_object_top_level_fields(normalized)

    return _format_hcl_assignment_alignment(normalized).rstrip()


def _normalize_generated_tfvars_content(tfvars_content: str) -> str:
    """Normalize generated tfvars snippets only.

    Do not call this on a full existing tfvars file unless it is acceptable to
    reformat the whole file. Azure consumer generation must preserve the
    backend-read tfvars content exactly, so use
    _normalize_generated_tfvars_content_preserving_existing for full files.
    """
    text = (tfvars_content or "").replace("\r\n", "\n").rstrip()
    if not text:
        return "\n"

    updated = text

    for span in reversed(_top_level_hcl_assignment_spans(updated)):
        value = _extract_hcl_assignment_value(updated, span["name"])
        if not value or not value.strip().startswith("{"):
            continue

        normalized_value = _normalize_generated_hcl_value(value)
        if normalized_value.strip() == value.strip():
            continue

        updated = _replace_top_level_tfvars_assignment(
            updated,
            span["name"],
            normalized_value,
        ).rstrip()

    updated = _format_hcl_assignment_alignment(updated)
    return updated.rstrip() + "\n"


def _normalize_generated_tfvars_content_preserving_existing(
    existing_tfvars: str,
    generated_tfvars: str,
) -> str:
    """Format only generated additions while preserving existing tfvars bytes.

    Azure existing-module consumer PRs are rejected unless the routed tfvars
    file contains the backend-read existing content plus additions. Running a
    formatter across the whole final file can change spacing inside the
    existing content, which makes the preservation check fail. This helper
    finds the existing content inside the generated file and formats only the
    generated prefix/suffix around it.
    """
    existing = (existing_tfvars or "").replace("\r\n", "\n")
    generated = (generated_tfvars or "").replace("\r\n", "\n")

    if not generated.strip():
        return "\n"

    if not existing.strip():
        return _normalize_generated_tfvars_content(generated)

    candidates = []
    for candidate in (existing, existing.rstrip(), existing.strip()):
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    for existing_segment in candidates:
        idx = generated.find(existing_segment)
        if idx == -1:
            continue

        prefix = generated[:idx]
        suffix = generated[idx + len(existing_segment):]
        formatted_prefix = _normalize_generated_tfvars_content(prefix).rstrip("\n") if prefix.strip() else prefix
        formatted_suffix = _normalize_generated_tfvars_content(suffix).rstrip("\n") if suffix.strip() else suffix

        # Preserve the exact existing segment. Only generated prefix/suffix are
        # normalized. Ensure there is a newline between the preserved content
        # and formatted generated suffix when both are present.
        parts = [formatted_prefix, existing_segment]
        result = "".join(parts)
        if formatted_suffix:
            if result and not result.endswith("\n") and not formatted_suffix.startswith("\n"):
                result += "\n"
            result += formatted_suffix

        return result.rstrip() + "\n"

    # No exact existing segment was found. Return the generated content
    # unchanged so the caller's preservation check can reject it or merge it
    # from backend context. Do not reformat it here because that would make
    # diagnostics harder and could hide deletion of existing content.
    return generated.rstrip() + "\n"

def _replace_or_insert_hcl_object_field(object_value: str, field_name: str, field_value: str) -> str:
    text = (object_value or "").replace("\r\n", "\n").rstrip()
    field_name = (field_name or "").strip()
    field_value = _normalize_generated_hcl_value(field_value)

    if not text or not field_name or not field_value:
        return text

    # Object literal path: operate inside the outer braces, because fields in
    # `{ ... }` are depth 0 only after stripping the wrapper braces.
    if text.strip().startswith("{") and text.strip().endswith("}"):
        stripped = text.strip()
        inner = stripped[1:-1]

        spans = _top_level_hcl_assignment_spans(inner)
        matching = [span for span in spans if span["name"] == field_name]

        if matching:
            keep = matching[-1]
            line = inner[keep["start"]:keep["end"]]
            indent_match = re.match(r"\s*", line)
            indent = indent_match.group(0) if indent_match else "  "

            replacement = f"{indent}{field_name} = {field_value}"
            new_inner = inner[:keep["start"]] + replacement + inner[keep["end"]:]

            for span in reversed(matching[:-1]):
                start, end = span["start"], span["end"]
                if end < len(new_inner) and new_inner[end:end + 1] == "\n":
                    end += 1
                new_inner = new_inner[:start] + new_inner[end:]

            return _normalize_generated_hcl_value("{" + new_inner.rstrip() + "\n}")

        close_idx = text.rfind("}")
        if close_idx == -1:
            return text

        updated = text[:close_idx].rstrip() + f"\n  {field_name} = {field_value}\n" + text[close_idx:]
        return _normalize_generated_hcl_value(updated)

    # Non-object fallback.
    start, end = _top_level_tfvars_assignment_span(text, field_name)
    if start >= 0 and end >= 0:
        line_start = text.rfind("\n", 0, start) + 1
        line = text[line_start:end]
        indent_match = re.match(r"\s*", line)
        indent = indent_match.group(0) if indent_match else ""

        replacement = f"{indent}{field_name} = {field_value}"
        suffix = text[end:]
        if suffix and not suffix.startswith("\n"):
            replacement += "\n"

        return _format_hcl_assignment_alignment(text[:start] + replacement + suffix).rstrip()

    return _format_hcl_assignment_alignment(text.rstrip() + f"\n{field_name} = {field_value}").rstrip()

def _object_field_override_candidates(field_name: str, object_name: str = "") -> list[str]:
    field_name = _terraform_safe_variable_name(field_name)
    object_name = _terraform_safe_variable_name(object_name)
    candidates = [field_name]

    if object_name and field_name.startswith(object_name + "_"):
        candidates.append(field_name[len(object_name) + 1:])

    # Common Azure module input names are prefixed with the resource type while
    # the object fields are named account_*. Map short user replies such as
    # storage_account_tier = "Standard" onto account_tier inside the generated
    # storage_account_zrs_custom object.
    if field_name.startswith("storage_account_"):
        rest = field_name[len("storage_account_"):]
        candidates.append(f"account_{rest}")
        candidates.append(rest)

    if field_name.startswith("key_vault_"):
        candidates.append(field_name[len("key_vault_"):])

    module_field = _module_object_field_for_input(field_name) if "_module_object_field_for_input" in globals() else ""
    if module_field:
        candidates.append(module_field)

    return _dedupe_preserving_order([candidate for candidate in candidates if candidate])


def _merge_hcl_object_field_overrides(base_value: str, object_name: str, user_assignments: dict[str, str]) -> str:
    merged = (base_value or "").strip()
    object_name = (object_name or "").strip()
    if not merged or not object_name or not isinstance(user_assignments, dict):
        return merged

    if object_name in user_assignments:
        object_override = (user_assignments.get(object_name) or "").strip()
        if object_override.startswith("{"):
            base_fields = _top_level_tfvars_assignment_field_names(merged)
            override_fields = _extract_tfvars_assignments_from_text(object_override)
            if base_fields and override_fields and (base_fields - set(override_fields.keys())):
                for field, value in override_fields.items():
                    merged = _replace_or_insert_hcl_object_field(merged, field, value)
            else:
                merged = object_override

    object_fields = _top_level_tfvars_assignment_field_names(merged)
    for field, value in user_assignments.items():
        if field == object_name:
            continue
        for candidate_field in _object_field_override_candidates(field, object_name):
            if candidate_field in object_fields:
                merged = _replace_or_insert_hcl_object_field(merged, candidate_field, value)
                object_fields.add(candidate_field)
                break

    return merged

def _tfvars_assignment_should_use_candidate(existing_tfvars: str, generated_tfvars: str, variable_name: str, candidate_value: str) -> bool:
    """Return true when a newly generated assignment is only a stub.

    Existing tfvars assignments are never replaced. This only upgrades a new
    assignment that the agent appended in the same generation pass, for example
    `containers = []`, with the backend-suggested full object copied from the
    existing tf-azure-hub tfvars pattern.
    """
    variable_name = (variable_name or "").strip()
    candidate = (candidate_value or "").strip()
    if not variable_name or not candidate:
        return False
    if _has_top_level_tfvars_assignment(existing_tfvars, variable_name):
        return False
    if not _has_top_level_tfvars_assignment(generated_tfvars, variable_name):
        return False

    current = _extract_hcl_assignment_value(generated_tfvars, variable_name).strip()
    if not current:
        return True

    normalized_current = re.sub(r"\s+", " ", current).strip()
    normalized_candidate = re.sub(r"\s+", " ", candidate).strip()
    if normalized_current == normalized_candidate:
        return False

    if normalized_current in {"{}", "[]", "null"}:
        return True

    current_fields = _top_level_tfvars_assignment_field_names(current)
    candidate_fields = _top_level_tfvars_assignment_field_names(candidate)
    if candidate_fields and (candidate_fields - current_fields):
        if len(candidate) > len(current) + 8:
            return True

    if re.search(r'(?m)^[ \t]*containers[ \t]*=[ \t]*\[[ \t]*\][ \t]*$', current) and not re.search(r'(?m)^[ \t]*containers[ \t]*=[ \t]*\[[ \t]*\][ \t]*$', candidate):
        return True

    return len(candidate) > len(current) * 2 and len(candidate) > len(current) + 40


AZURE_TFVARS_AUTOFILL_EXCLUDED_ROOTS = {
    "hub_name",
    "subscription_type",
    "subscription_id",
    "tenant_id",
    "location",
    "tags",
    "environment",
    "infra_devops",
}


def _new_module_tfvars_roots_from_context(
    routing_context: dict | None,
    consumer_content: str,
) -> set[str]:
    """Return var.* roots used by the newly generated module block only.

    The full consumer file also contains existing module blocks. Using every
    var.* root from that file can make Terrabot append source/default objects
    such as storage_account_zrs in addition to the requested sibling object
    storage_account_zrs_custom. This scopes value generation to the new
    source-matched block(s) only.
    """
    routing_context = routing_context or {}
    existing_consumer = routing_context.get("existing_consumer_file_content") or ""
    module_source_url = routing_context.get("module_source_url") or ""
    roots: set[str] = set()

    if module_source_url:
        for block in _new_matching_module_blocks(existing_consumer, consumer_content or "", module_source_url):
            roots.update(_extract_var_roots_from_text(block.get("block") or ""))

    return {
        _terraform_safe_variable_name(root)
        for root in roots
        if _terraform_safe_variable_name(root)
    }


def _request_tfvars_roots(
    routing_context: dict | None,
    consumer_content: str,
    generated_tfvars: str = "",
) -> set[str]:
    """Return tfvars roots that may be generated for this request.

    For source-matched Azure module consumption, use only the var.* roots from
    the newly generated module block. The full consumer file also contains the
    existing matched module, and using every var.* reference from the whole file
    can re-add the source object, for example storage_account_zrs, when the
    request is for storage_account_zrs_custom.

    When there is no new module block, fall back only to generated top-level
    tfvars roots. That preserves follow-up value-change workflows without
    allowing unrelated existing consumer roots to be appended.
    """
    routing_context = routing_context or {}
    request_roots = _new_module_tfvars_roots_from_context(routing_context, consumer_content)
    if request_roots:
        return request_roots

    generated_roots = {
        _terraform_safe_variable_name(root)
        for root in _extract_top_level_hcl_assignment_names(generated_tfvars or "")
        if _terraform_safe_variable_name(root)
    }
    if generated_roots:
        return generated_roots

    # A routed Azure existing-module consumer request should never fall back to
    # all roots in the full consumer file. If no new block or generated tfvars
    # root exists, there is nothing safe to append.
    if routing_context.get("module_source_url") or routing_context.get("existing_consumer_file_content"):
        return set()

    return {
        _terraform_safe_variable_name(root)
        for root in _extract_var_roots_from_text(consumer_content or "")
        if _terraform_safe_variable_name(root)
    }


def _remove_disallowed_top_level_tfvars_assignments(
    hcl_content: str,
    allowed_roots: set[str],
) -> str:
    """Remove generated top-level tfvars assignments outside allowed_roots.

    This is applied only to generated prefixes/suffixes around the preserved
    backend-read tfvars content. It prevents an existing source object copied
    from the matched module pattern from being appended as a new root value.
    """
    text = (hcl_content or "").replace("\r\n", "\n")
    if not text.strip() or not allowed_roots:
        return text

    remove_ranges: list[tuple[int, int]] = []
    for span in _top_level_hcl_assignment_spans(text):
        safe_name = _terraform_safe_variable_name(span.get("name") or "")
        if safe_name and safe_name not in allowed_roots:
            start, end = int(span["start"]), int(span["end"])
            if end < len(text) and text[end:end + 1] == "\n":
                end += 1
            remove_ranges.append((start, end))

    if not remove_ranges:
        return text

    updated = text
    for start, end in sorted(remove_ranges, reverse=True):
        updated = updated[:start] + updated[end:]

    # Drop an empty Terrabot-generated header when all generated assignments
    # under it were removed.
    if not _top_level_hcl_assignment_spans(updated):
        marker = "# Terrabot-generated Azure module values"
        if marker in updated:
            return "\n" if updated.startswith("\n") else ""

    return updated


def _sanitize_generated_tfvars_assignments_for_request(
    existing_tfvars: str,
    generated_tfvars: str,
    routing_context: dict | None,
    consumer_content: str,
) -> str:
    """Preserve existing tfvars bytes and remove unrelated generated roots."""
    allowed_roots = _request_tfvars_roots(routing_context, consumer_content, generated_tfvars)
    if not allowed_roots:
        return (generated_tfvars or "").replace("\r\n", "\n").rstrip() + "\n"

    existing = (existing_tfvars or "").replace("\r\n", "\n")
    generated = (generated_tfvars or "").replace("\r\n", "\n")

    candidates: list[str] = []
    for candidate in (existing, existing.rstrip(), existing.strip()):
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    for existing_segment in candidates:
        idx = generated.find(existing_segment)
        if idx == -1:
            continue

        prefix = generated[:idx]
        suffix = generated[idx + len(existing_segment):]
        prefix = _remove_disallowed_top_level_tfvars_assignments(prefix, allowed_roots)
        suffix = _remove_disallowed_top_level_tfvars_assignments(suffix, allowed_roots)
        return (prefix + existing_segment + suffix).rstrip() + "\n"

    # If the agent returned only a snippet, sanitize that snippet before the
    # merge helper appends safe assignments to the backend-read file.
    return _remove_disallowed_top_level_tfvars_assignments(generated, allowed_roots).rstrip() + "\n"



def _user_assignments_with_object_field_aliases(
    user_assignments: dict[str, str],
    routing_context: dict,
    source_object_root: str = "",
) -> dict[str, str]:
    """Map module-input override names to object-field names.

    Example: a user can reply with storage_account_tier = "Standard" while the
    actual tfvars object field is account_tier. The matched existing module
    expression tells us that mapping:
    storage_account_tier = var.storage_account_zrs.account_tier
    """
    result: dict[str, str] = {}
    for key, value in (user_assignments or {}).items():
        key = (key or "").strip()
        value = (value or "").strip()
        if key and value:
            result[key] = value

    routing_context = routing_context or {}
    source_object_root = source_object_root or _dominant_object_var_root(
        routing_context.get("matched_module_block") or ""
    )

    for item in routing_context.get("suggested_variable_values") or []:
        if not isinstance(item, dict):
            continue
        input_name = (item.get("input_name") or "").strip()
        expression = (item.get("matched_existing_module_expression") or "").strip()
        field_name = _module_object_field_for_input(
            input_name,
            pattern_expression=expression,
            source_object_root=source_object_root,
        )
        if input_name and field_name and input_name in user_assignments:
            result[field_name] = (user_assignments[input_name] or "").strip()

    # Small safety net for the common storage-account module naming convention.
    storage_account_aliases = {
        "storage_account_tier": "account_tier",
        "storage_account_replication": "account_replication",
        "storage_account_kind": "account_kind",
        "storage_account_access_tier": "account_access_tier",
        "storage_account_is_hns_enabled": "account_is_hns_enabled",
    }
    for input_name, field_name in storage_account_aliases.items():
        if input_name in user_assignments and field_name not in result:
            result[field_name] = (user_assignments[input_name] or "").strip()

    return {key: value for key, value in result.items() if key and value}

def _candidate_tfvars_assignments_from_suggestions(
    routing_context: dict,
    consumer_content: str,
    retrieved_value_context: list | None = None,
) -> dict[str, str]:
    request_roots = _request_tfvars_roots(routing_context, consumer_content)
    candidates: dict[str, str] = {}
    user_selected_assignments = _user_selected_tfvars_assignments(retrieved_value_context)

    # User-provided HCL wins when it names a variable root referenced by the
    # newly generated module invocation. Do not use all var.* references from
    # the full consumer file, because existing module blocks may reference
    # source/default objects that must not be added to the routed tfvars file.
    for name, value in user_selected_assignments.items():
        name = _terraform_safe_variable_name((name or "").strip())
        value = (value or "").strip()
        if (
            name
            and value
            and name in request_roots
            and name not in AZURE_TFVARS_AUTOFILL_EXCLUDED_ROOTS
        ):
            candidates[name] = _normalize_generated_hcl_value(value)

    existing_consumer = (routing_context or {}).get("existing_consumer_file_content") or ""
    module_source_url = (routing_context or {}).get("module_source_url") or ""
    matched_block = (routing_context or {}).get("matched_module_block") or ""
    source_object_root = _dominant_object_var_root(matched_block)

    if source_object_root:
        source_value = ""
        for source_content in (
            (routing_context or {}).get("existing_tfvars_file_content") or "",
            (routing_context or {}).get("common_tfvars_file_content") or "",
        ):
            source_value = _extract_hcl_assignment_value(source_content, source_object_root)
            if source_value:
                break

        if not source_value:
            for item in (routing_context or {}).get("suggested_variable_values") or []:
                if not isinstance(item, dict):
                    continue
                if (item.get("tfvars_variable_name") or "").strip() == source_object_root:
                    suggested_value = (item.get("suggested_value") or "").strip()
                    if suggested_value and not suggested_value.endswith(" ..."):
                        source_value = suggested_value
                        break

        if source_value and module_source_url:
            for block in _new_matching_module_blocks(existing_consumer, consumer_content, module_source_url):
                module_name = (block.get("header") or "").replace('module "', "").replace('"', "").strip()
                target_object_root = _tfvars_object_name_from_module_name(module_name)
                if (
                    target_object_root
                    and target_object_root in request_roots
                    and target_object_root not in AZURE_TFVARS_AUTOFILL_EXCLUDED_ROOTS
                ):
                    object_field_overrides = _user_assignments_with_object_field_aliases(
                        user_selected_assignments,
                        routing_context or {},
                        source_object_root=source_object_root,
                    )
                    object_value = _merge_hcl_object_field_overrides(
                        source_value,
                        target_object_root,
                        object_field_overrides,
                    )
                    candidates.setdefault(target_object_root, _normalize_generated_hcl_value(object_value))

    for item in (routing_context or {}).get("suggested_variable_values") or []:
        if not isinstance(item, dict) or item.get("sensitive"):
            continue
        # Do not skip undeclared roots here. variables.tf declaration generation
        # is handled later by _ensure_azure_consumer_variables_tf_declarations.
        tfvar_name = (item.get("tfvars_variable_name") or item.get("input_name") or "").strip()
        if not tfvar_name or tfvar_name in AZURE_TFVARS_AUTOFILL_EXCLUDED_ROOTS:
            continue

        expression = item.get("matched_existing_module_expression") or ""
        value = ""
        for source_content in (
            (routing_context or {}).get("existing_tfvars_file_content") or "",
            (routing_context or {}).get("common_tfvars_file_content") or "",
        ):
            value = _extract_hcl_assignment_value(source_content, tfvar_name)
            if value:
                break

        if not value:
            suggested_value = (item.get("suggested_value") or "").strip()
            if suggested_value and not suggested_value.endswith(" ..."):
                value = suggested_value

        if not value:
            continue

        if _terraform_safe_variable_name(tfvar_name) not in request_roots:
            continue

        if tfvar_name in user_selected_assignments:
            value = user_selected_assignments[tfvar_name]

        candidates.setdefault(tfvar_name, _normalize_generated_hcl_value(value))

    for name, value in (routing_context or {}).get("auto_tfvars_assignments", {}).items():
        safe_name = _terraform_safe_variable_name(name)
        if (
            safe_name
            and safe_name in request_roots
            and safe_name not in AZURE_TFVARS_AUTOFILL_EXCLUDED_ROOTS
            and value
        ):
            candidates.setdefault(safe_name, _normalize_generated_hcl_value(value))

    return candidates


def _replace_tfvars_assignment(tfvars_content: str, assignment_name: str, value: str) -> str:
    value = _normalize_generated_hcl_value(value)

    if _has_top_level_tfvars_assignment(tfvars_content, assignment_name):
        # Replace only the requested assignment value. Do not run a formatter
        # across the entire tfvars file, because Azure consumer changes must
        # preserve the backend-read existing content exactly.
        return _replace_top_level_tfvars_assignment(
            tfvars_content,
            assignment_name,
            value,
        ).replace("\r\n", "\n").rstrip() + "\n"

    return _append_tfvars_assignments_preserving_existing(tfvars_content, {assignment_name: value})


def _tfvars_assignment_exists_in_existing_file(existing_tfvars: str, assignment_name: str) -> bool:
    return _has_top_level_tfvars_assignment(existing_tfvars or "", assignment_name)


def _append_tfvars_assignments_preserving_existing(tfvars_content: str, assignments: dict[str, str]) -> str:
    if not assignments:
        return (tfvars_content or "").replace("\r\n", "\n").rstrip() + "\n"

    lines = [
        "",
        "# =======================================================",
        "# Terrabot-generated Azure module values",
        "# =======================================================",
    ]
    for name, value in assignments.items():
        value = _normalize_generated_hcl_value(value)
        if not value:
            continue
        lines.append(f"{name} = {value}")
        lines.append("")

    # Preserve existing tfvars content exactly. Only normalize the generated
    # assignment values before appending them.
    return (
        (tfvars_content or "").replace("\r\n", "\n").rstrip()
        + "\n"
        + "\n".join(lines).rstrip()
        + "\n"
    )


def _merge_generated_tfvars_with_existing_preserving_existing(
    existing_tfvars: str,
    generated_tfvars: str,
    candidate_assignments: dict[str, str],
    consumer_content: str,
    routing_context: dict | None = None,
) -> str:
    """Recover a tfvars file when the agent omitted existing content.

    The agent sometimes returns only the user's overrides or only the new HCL
    snippet. For Azure existing-module consumers, that is not allowed to reach
    GitHub. This helper starts from the backend-read existing tfvars file and
    appends only safe top-level assignments for variables referenced by the new
    consumer module. Existing assignments are never overwritten here.
    """
    base = (existing_tfvars or "").replace("\r\n", "\n").rstrip() + "\n"
    referenced_roots = _request_tfvars_roots(routing_context, consumer_content, generated_tfvars)
    safe_assignments: dict[str, str] = {}

    for name in _extract_top_level_hcl_assignment_names(generated_tfvars):
        name = (name or "").strip()
        value = (_extract_hcl_assignment_value(generated_tfvars, name) or "").strip()
        if not name or not value:
            continue
        if name in AZURE_TFVARS_AUTOFILL_EXCLUDED_ROOTS:
            continue
        if referenced_roots and name not in referenced_roots:
            continue
        if _has_top_level_tfvars_assignment(base, name):
            continue
        safe_assignments[name] = value

    for name, value in (candidate_assignments or {}).items():
        name = (name or "").strip()
        value = (value or "").strip()
        if not name or not value:
            continue
        if name in AZURE_TFVARS_AUTOFILL_EXCLUDED_ROOTS:
            continue
        if referenced_roots and name not in referenced_roots:
            continue
        if _has_top_level_tfvars_assignment(base, name):
            continue
        safe_assignments[name] = value

    if not safe_assignments:
        return base

    return _append_tfvars_assignments_preserving_existing(base, safe_assignments)


def _ensure_azure_consumer_tfvars_values_added(
    existing_tfvars: str,
    tfvars_content: str,
    routing_context: dict,
    consumer_content: str,
    retrieved_value_context: list | None = None,
) -> str:
    """Ensure the routed tfvars file receives complete suggested values.

    The generated tfvars file must preserve the existing backend-routed file.
    When the agent returns only a snippet or only user overrides, recover by
    starting from existing_tfvars and appending the new safe assignments. This
    keeps the PR from deleting existing tfvars content while still allowing the
    confirmed values/defaults to be generated.
    """
    existing = (existing_tfvars or "").replace("\r\n", "\n")
    generated = (tfvars_content or "").replace("\r\n", "\n").rstrip() + "\n"

    candidates = _candidate_tfvars_assignments_from_suggestions(
        routing_context,
        consumer_content,
        retrieved_value_context=retrieved_value_context,
    )

    generated = _sanitize_generated_tfvars_assignments_for_request(
        existing_tfvars=existing,
        generated_tfvars=generated,
        routing_context=routing_context,
        consumer_content=consumer_content,
    )

    if not _content_contains_existing_file(existing, generated):
        generated = _merge_generated_tfvars_with_existing_preserving_existing(
            existing_tfvars=existing,
            generated_tfvars=generated,
            candidate_assignments=candidates,
            consumer_content=consumer_content,
            routing_context=routing_context,
        )

    updated = _sanitize_generated_tfvars_assignments_for_request(
        existing_tfvars=existing,
        generated_tfvars=generated,
        routing_context=routing_context,
        consumer_content=consumer_content,
    )
    missing_assignments: dict[str, str] = {}
    for name, value in candidates.items():
        if not name or not value:
            continue
        if _has_top_level_tfvars_assignment(updated, name):
            if _generated_tfvars_assignment_should_be_replaced(existing, updated, name, value):
                updated = _replace_top_level_tfvars_assignment(updated, name, value)
            continue
        missing_assignments[name] = value

    if missing_assignments:
        updated = _append_tfvars_assignments_preserving_existing(updated, missing_assignments)

    return _normalize_generated_tfvars_content_preserving_existing(existing, updated)


def _recover_generated_tfvars_preserving_existing(
    existing_tfvars: str,
    generated_tfvars: str,
    routing_context: dict | None = None,
    consumer_content: str = "",
    retrieved_value_context: list | None = None,
) -> str:
    """Return tfvars content that preserves the backend-read file exactly.

    Some agent replies contain only the user's HCL overrides, or contain a
    formatted copy of the existing tfvars file. Azure consumer generation must
    not let either shape reach preview/commit. Start from the backend-read
    existing tfvars content, then append only safe generated/candidate root
    assignments for the new module.
    """
    existing = (existing_tfvars or "").replace("\r\n", "\n")
    generated = (generated_tfvars or "").replace("\r\n", "\n").rstrip() + "\n"

    generated = _sanitize_generated_tfvars_assignments_for_request(
        existing_tfvars=existing,
        generated_tfvars=generated,
        routing_context=routing_context,
        consumer_content=consumer_content,
    )

    formatted = _normalize_generated_tfvars_content_preserving_existing(
        existing,
        generated,
    )
    if _content_contains_existing_file(existing, formatted):
        return formatted

    candidates: dict[str, str] = {}
    if routing_context:
        candidates = _candidate_tfvars_assignments_from_suggestions(
            routing_context,
            consumer_content,
            retrieved_value_context=retrieved_value_context,
        )

    recovered = _merge_generated_tfvars_with_existing_preserving_existing(
        existing_tfvars=existing,
        generated_tfvars=generated,
        candidate_assignments=candidates,
        consumer_content=consumer_content,
        routing_context=routing_context,
    )
    recovered = _normalize_generated_tfvars_content_preserving_existing(
        existing,
        recovered,
    )

    return recovered.replace("\r\n", "\n").rstrip() + "\n"


def _tfvars_missing_suggested_assignments(
    tfvars_content: str,
    routing_context: dict,
    consumer_content: str,
    retrieved_value_context: list | None = None,
) -> list[str]:
    candidates = _candidate_tfvars_assignments_from_suggestions(
        routing_context,
        consumer_content,
        retrieved_value_context=retrieved_value_context,
    )
    existing_tfvars = (routing_context or {}).get("existing_tfvars_file_content") or ""
    missing = []
    for name, value in candidates.items():
        if not _has_top_level_tfvars_assignment(tfvars_content, name):
            missing.append(name)
            continue
        if _generated_tfvars_assignment_should_be_replaced(existing_tfvars, tfvars_content, name, value):
            missing.append(name)
    return missing

def enforce_real_module_inputs_stage1(agent_result: dict, retrieved_module_context: list) -> dict:
    if not isinstance(agent_result, dict):
        return agent_result

    if agent_result.get("workflow") != "azure_consumer_generation":
        return agent_result

    if normalize_repo_target(
        agent_result.get("cloud"),
        repo_target=agent_result.get("repo_target"),
        workflow=agent_result.get("workflow"),
    ) != "tf-azure-hub":
        return agent_result

    allowed_inputs = []
    required_inputs = []

    for item in retrieved_module_context or []:
        if not isinstance(item, dict):
            continue

        for name in item.get("inputs_detected") or []:
            name = str(name).strip()
            if name and name not in allowed_inputs:
                allowed_inputs.append(name)

        for name in item.get("required_inputs_detected") or []:
            name = str(name).strip()
            if name and name in allowed_inputs and name not in required_inputs:
                required_inputs.append(name)

    if not allowed_inputs:
        raise ValueError(
            "No verified module inputs found for Azure consumer generation. "
            "The backend must build retrieved_module_context from the selected module repo before generating a consumer."
        )

    module_source_url = _get_verified_azure_module_source_url(retrieved_module_context)
    if not module_source_url:
        raise ValueError("No verified Azure module source URL found for consumer generation.")

    if not re.fullmatch(
        r"git@github\.com:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\.git\?ref=[^\s\"']+",
        module_source_url,
    ):
        raise ValueError("Verified Azure module source URL is invalid or missing ?ref.")

    routing_context = _get_azure_consumer_routing_context(
        agent_result.get("retrieved_value_context") or []
    )

    # finalize_agent_result_after_parse passes only module context today. The
    # backend attaches routing context to the parsed payload before calling this
    # validator when Azure consumer source matching is active.
    if not routing_context:
        routing_context = _get_azure_consumer_routing_context(
            getattr(enforce_real_module_inputs, "_active_retrieved_value_context", [])
        )

    if routing_context:
        files = agent_result.get("files") or []
        target_consumer = normalize_agent_relative_tf_path(
            routing_context.get("target_consumer_filename") or "",
            "azure",
        )
        target_tfvars = normalize_agent_relative_tf_path(
            routing_context.get("target_tfvars_filename") or "",
            "azure",
        )
        existing_consumer = routing_context.get("existing_consumer_file_content") or ""
        existing_tfvars = routing_context.get("existing_tfvars_file_content") or ""
        is_new_consumer_routing = routing_context.get("source") == "backend_new_azure_consumer_routing"

        if not target_consumer or not target_consumer.endswith(".tf"):
            raise ValueError("Azure consumer generation did not have a backend-routed .tf target file.")
        if not target_tfvars or not target_tfvars.endswith(".tfvars"):
            raise ValueError("Azure consumer generation did not have a backend-routed .tfvars target file.")
        if not existing_consumer.strip() and not is_new_consumer_routing:
            raise ValueError(f"Backend-routed consumer file was empty or unreadable: {target_consumer}")
        if not existing_tfvars.strip():
            raise ValueError(f"Backend-routed tfvars file was empty or unreadable: {target_tfvars}")

        variables_tf_filename = "variables.tf"
        allowed_file_names = {target_consumer, target_tfvars, variables_tf_filename}
        extra_files = [
            file_data.get("filename")
            for file_data in files
            if file_data.get("filename") not in allowed_file_names
        ]
        if extra_files:
            raise ValueError(
                "Azure existing-module consumer generation may only update the backend-routed module invocation file "
                f"and backend-routed tfvars file. Unexpected file(s): {', '.join(extra_files)}"
            )

        consumer_file = _find_agent_file_by_name_or_suffix(files, target_consumer, suffix=".tf")
        tfvars_file = _find_agent_file_by_name_or_suffix(files, target_tfvars, suffix=".tfvars")

        inputs_to_emit = required_inputs or allowed_inputs

        if not consumer_file and not is_new_consumer_routing:
            raise ValueError(
                f"Azure consumer generation must return the backend-selected module invocation file: {target_consumer}"
            )

        if is_new_consumer_routing:
            module_context = _get_primary_azure_module_context(retrieved_module_context)
            module_name = _azure_consumer_module_name_from_module_context(module_context)
            if not inputs_to_emit:
                raise ValueError("No verified module inputs are available to emit for Azure consumer generation.")
            longest = max(len(name) for name in inputs_to_emit)
            module_lines = [
                f'module "{module_name}" {{',
                f'  source = "{module_source_url}"',
                "",
            ]
            for name in inputs_to_emit:
                spacing = " " * (longest - len(name) + 1)
                module_lines.append(f"  {name}{spacing}= var.{name}")
            module_lines.append("}")
            generated_module_content = "\n".join(module_lines).rstrip() + "\n"
            if consumer_file and (consumer_file.get("content") or "").strip():
                consumer_content = (consumer_file.get("content") or "").replace("\r\n", "\n").rstrip() + "\n"
            else:
                consumer_content = generated_module_content
        else:
            consumer_content = (consumer_file.get("content") or "").replace("\r\n", "\n").rstrip() + "\n"
        if tfvars_file:
            tfvars_content = (tfvars_file.get("content") or "").replace("\r\n", "\n").rstrip() + "\n"
        else:
            # Do not allow the old one-file PR path. Start from the existing
            # backend-routed tfvars content and append confirmed/suggested
            # assignments below.
            tfvars_content = existing_tfvars.replace("\r\n", "\n").rstrip() + "\n"

        if module_source_url not in consumer_content:
            raise ValueError(
                "Azure consumer generation must include the exact backend-selected module_source_url unchanged "
                f"inside {target_consumer}."
            )

        if existing_consumer.strip() and not _content_contains_existing_file(existing_consumer, consumer_content):
            consumer_content = _merge_terraform_content_preserving_existing(
                existing_consumer,
                consumer_content,
            )

        active_value_context = list(
           getattr(enforce_real_module_inputs, "_active_retrieved_value_context", []) or []
        )
        user_selected_assignments = _user_selected_tfvars_assignments(active_value_context)

        consumer_content = _repair_azure_consumer_module_invocations(
            existing_consumer=existing_consumer,
            consumer_content=consumer_content,
            routing_context=routing_context,
            module_source_url=module_source_url,
            allowed_input_names=allowed_inputs,
            user_selected_assignments=user_selected_assignments,
         )

        if module_source_url not in consumer_content:
            raise ValueError(
                "The merged Azure consumer file does not contain the verified module source. No PR was created."
           )
        
        tfvars_content = _ensure_azure_consumer_tfvars_values_added(
            existing_tfvars=existing_tfvars,
            tfvars_content=tfvars_content,
            routing_context=routing_context,
            consumer_content=consumer_content,
            retrieved_value_context=active_value_context,
        )
        tfvars_content = _recover_generated_tfvars_preserving_existing(
            existing_tfvars=existing_tfvars,
            generated_tfvars=tfvars_content,
            routing_context=routing_context,
            consumer_content=consumer_content,
            retrieved_value_context=active_value_context,
        )

        if not _content_contains_existing_file(existing_tfvars, tfvars_content):
            raise ValueError(
                f"Generated tfvars content for {target_tfvars} does not preserve the existing file contents. "
                "The backend rejects tfvars changes unless the full existing file content is included and only additions are made."
            )

        if _normalized_hcl_content_for_compare(existing_tfvars) == _normalized_hcl_content_for_compare(tfvars_content):
            raise ValueError(
                f"Generated tfvars content for {target_tfvars} is unchanged. "
                "Azure existing-module consumer generation must add variable values to the routed tfvars file so the PR contains both the module invocation and its variable values."
            )

        missing_tfvars_assignments = _tfvars_missing_suggested_assignments(
            tfvars_content=tfvars_content,
            routing_context=routing_context,
            consumer_content=consumer_content,
            retrieved_value_context=active_value_context,
        )
        if missing_tfvars_assignments:
            raise ValueError(
                f"Generated tfvars content for {target_tfvars} is missing required suggested variable assignment(s): "
                + ", ".join(missing_tfvars_assignments)
                + ". Azure existing-module consumer PRs must update the backend-routed tfvars file instead of hardcoding values in the module invocation."
            )

        original_variables_tf_content = (
            routing_context.get("variables_tf_file_content") or ""
        ).replace("\r\n", "\n")

        variables_tf_content, added_variable_declarations = _ensure_azure_consumer_variables_tf_declarations(
            agent_result=agent_result,
            routing_context=routing_context,
            tfvars_content=tfvars_content,
            active_value_context=active_value_context,
            consumer_content=consumer_content,
        )

        variables_tf_content = _repair_unclosed_variables_tf_content_for_write(
            existing_content=original_variables_tf_content,
            generated_content=variables_tf_content,
            path=variables_tf_filename,
        )

        variables_tf_changed = (
            bool(variables_tf_content.strip())
            and _normalized_hcl_content_for_compare(variables_tf_content)
            != _normalized_hcl_content_for_compare(original_variables_tf_content)
        )

        tfvars_content = _recover_generated_tfvars_preserving_existing(
            existing_tfvars=existing_tfvars,
            generated_tfvars=tfvars_content,
            routing_context=routing_context,
            consumer_content=consumer_content,
            retrieved_value_context=active_value_context,
        )

        if not _content_contains_existing_file(existing_tfvars, tfvars_content):
            raise ValueError(
                f"Generated tfvars content for {target_tfvars} does not preserve the existing file contents after formatting. "
                "The backend rejects tfvars changes unless the full existing file content is included and only additions are made."
            )

        result_files = [
            {
                "filename": target_consumer,
                "content": consumer_content,
            },
            {
                "filename": target_tfvars,
                "content": tfvars_content,
            },
        ]

        if added_variable_declarations or variables_tf_changed:
            result_files.append({
                "filename": variables_tf_filename,
                "content": variables_tf_content,
            })

        agent_result["repo_target"] = "tf-azure-hub"
        agent_result["files"] = result_files
        agent_result["routing_summary"] = {
            "consumer_file": target_consumer,
            "tfvars_file": target_tfvars,
            "variables_file": variables_tf_filename if added_variable_declarations else "",
            "variables_added": added_variable_declarations,
            "azure_environment": routing_context.get("azure_environment"),
            "matched_module_source": routing_context.get("matched_module_source"),
            "match_type": routing_context.get("match_type"),
        }
        return agent_result

    raise ValueError(
        "Azure consumer generation requires backend-routed tf-azure-hub context with target_consumer_filename "
        "and target_tfvars_filename. No single-file/source-only consumer PR was created."
    )
enforce_real_module_inputs = enforce_real_module_inputs_stage1

def finalize_agent_result_after_parse(
    agent_result: dict,
    retrieved_module_context: list,
    retrieved_value_context: list | None = None,
) -> dict:
    agent_result = enrich_agent_result_with_module_repo_target(
        agent_result,
        retrieved_module_context,
    )

    agent_result = validate_azure_module_population_core_files(agent_result)

    agent_result = enforce_verified_aws_module_sources(
        agent_result,
        retrieved_module_context,
    )

    enforce_real_module_inputs._active_retrieved_value_context = list(retrieved_value_context or [])
    try:
        agent_result = enforce_real_module_inputs(
            agent_result,
            retrieved_module_context,
        )
        agent_result = ensure_azure_consumer_variables_tf_file(
            agent_result,
            retrieved_value_context=retrieved_value_context,
        )
        agent_result = _repair_azure_consumer_variables_tf_files_in_agent_result(
            agent_result,
        )
    finally:
        enforce_real_module_inputs._active_retrieved_value_context = []

    return agent_result

def _item_attr(item, name, default=None):
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _extract_text_from_response(response) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    text_parts = []

    for item in getattr(response, "output", []) or []:
        if _item_attr(item, "type") != "message":
            continue

        for part in (_item_attr(item, "content", []) or []):
            part_type = _item_attr(part, "type")
            if part_type in ("output_text", "text"):
                text_value = _item_attr(part, "text")
                if isinstance(text_value, str):
                    text_parts.append(text_value)
                else:
                    wrapped_value = getattr(text_value, "value", None)
                    if isinstance(wrapped_value, str):
                        text_parts.append(wrapped_value)

    return "\n".join(text_parts).strip()


def _collect_mcp_approval_requests(response):
    approval_ids = []
    seen = set()

    for item in getattr(response, "output", []) or []:
        item_type = _item_attr(item, "type")
        item_id = _item_attr(item, "id")

        if item_type == "mcp_approval_request" and item_id and item_id not in seen:
            approval_ids.append(item_id)
            seen.add(item_id)

    return approval_ids


def _call_agent_base(conversation_id: Optional[str], user_content: str):
    agent_reference = find_agent_reference(AGENT_NAME)

    client = get_project_client()
    with client.get_openai_client() as openai_client:
        # First request in a new thread
        if not conversation_id:
            conversation = openai_client.conversations.create(
                items=[{"type": "message", "role": "user", "content": user_content}],
            )
            conversation_id = conversation.id
        else:
            # Follow-up request in an existing thread
            openai_client.conversations.items.create(
                conversation_id=conversation_id,
                items=[{"type": "message", "role": "user", "content": user_content}],
            )

        # Start a response run for the current conversation state
        response = openai_client.responses.create(
            conversation=conversation_id,
            extra_body={"agent_reference": agent_reference},
        )

        max_approval_rounds = 10

        for _ in range(max_approval_rounds):
            approval_ids = _collect_mcp_approval_requests(response)
            if not approval_ids:
                break

            approval_input: Any = [
                {
                    "type": "mcp_approval_response",
                    "approval_request_id": approval_id,
                    "approve": True,
                }
                for approval_id in approval_ids
            ]

            # IMPORTANT:
            # For approval continuation, use previous_response_id only.
            response = openai_client.responses.create(
                previous_response_id=response.id,
                input=approval_input,
                extra_body={"agent_reference": agent_reference},
            )

        remaining_approvals = _collect_mcp_approval_requests(response)
        if remaining_approvals:
            raise RuntimeError(
                "The agent requested tool approval but one approval step was missed. "
                "Please restart the backend and retry."
            )

        reply = _extract_text_from_response(response)
        if not reply:
            reply = "The agent completed the request but returned no text response."

        return conversation_id, reply
    
def coerce_context_list(value: Any) -> List[dict]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _context_source_is_backend_owned(source: str) -> bool:
    source = str(source or "").strip()
    if not source:
        return False
    return source.startswith(BACKEND_CONTEXT_SOURCE_PREFIXES)


def filter_backend_owned_context_list(context_list: list | None, *, context_name: str = "context") -> list[dict]:
    """Drop caller-provided RAG/KB contexts when backend-only mode is enabled.

    The backend may still append live GitHub contexts later in the flow. Those
    contexts carry backend/live_github/github/verified/deterministic source
    markers and are allowed through.
    """
    items = coerce_context_list(context_list)
    if not DISABLE_EXTERNAL_RAG_CONTEXT:
        return items

    filtered = []
    dropped = 0
    for item in items:
        source = item.get("source") or item.get("context_source") or item.get("provider") or ""
        if _context_source_is_backend_owned(source):
            filtered.append(item)
        else:
            dropped += 1

    if dropped:
        print(f"Backend-only mode dropped {dropped} non-backend {context_name} item(s).")
    return filtered


def build_backend_context_policy() -> dict:
    return {
        "source": "backend_context_policy",
        "backend_only_context": True,
        "rag_or_kb_repo_state_allowed": False,
        "instructions": [
            "Use only backend-provided live GitHub context for repo/module/value/resource state.",
            "Do not use RAG, Azure AI Search, Foundry KB snippets, or uploaded repo dumps as Terraform state.",
            "If required backend-owned context is missing, ask for clarification instead of inventing Terraform.",
        ],
    }



def is_infra_modification_or_delete_prompt(prompt: str) -> bool:
    """Return True for update/delete/fix/refactor prompts.

    This intentionally runs before module discovery/generation routing. A prompt
    such as "change hard expiry to false" must edit existing code, not create or
    append a new module block.
    """
    text = re.sub(r"\s+", " ", (prompt or "").strip().lower())
    if not text:
        return False

    modification_terms = [
        "update",
        "change",
        "set",
        "modify",
        "resize",
        "rename",
        "enable",
        "disable",
        "increase",
        "decrease",
        "remove",
        "delete",
        "decommission",
        "fix",
        "refactor",
        "replace value",
        "turn on",
        "turn off",
        "add tag",
        "remove tag",
        "change tag",
    ]

    creation_terms = [
        "create",
        "add new",
        "provision new",
        "deploy new",
        "make new",
        "build new",
    ]

    has_modification = any(term in text for term in modification_terms)
    has_creation = any(term in text for term in creation_terms)
    return has_modification and not has_creation


def _infer_generation_workflow_base(prompt: str, target_cloud: str, requested_workflow: Optional[str] = None) -> str:
    requested_workflow = (requested_workflow or "").strip()
    if requested_workflow:
        return requested_workflow

    text = (prompt or "").strip().lower()

    # Update/delete/fix/refactor prompts must be routed to a modification
    # workflow before module discovery or module creation logic runs.
    if is_infra_modification_or_delete_prompt(prompt):
        if target_cloud == "aws":
            return "aws_infra_modification"
        if target_cloud == "azure":
            return "azure_infra_modification"

    if target_cloud == "aws":
        return "aws_module_consumer"

    if target_cloud == "azure":
        if any(term in text for term in [
            "populate module repo",
            "populate the module repo",
            "generate module files",
            "create main.tf",
            "create variables.tf",
            "create outputs.tf",
            "create versions.tf",
            "create readme",
            "module repo files",
            "module files",
        ]):
            return "azure_module_repo_population"

        if any(term in text for term in [
            "create module",
            "new module",
            "new repo",
            "new repository",
            "module repository",
            "separate repo",
            "separate repository",
        ]):
            return "azure_module_repo_creation"

        return "azure_module_discovery"

    return ""

def _build_agent_input_for_infra_base(
    prompt: str,
    thread_id: str,
    selected_cloud: Optional[str] = None,
    workflow: Optional[str] = None,
    retrieved_module_context: Optional[list] = None,
    retrieved_value_context: Optional[list] = None,
) -> str:
    context_blocks = []

    thread_state = recover_thread_pr_state(thread_id)
    selected_cloud = safe_normalize_cloud(selected_cloud)
    retrieved_module_context = filter_backend_owned_context_list(
        retrieved_module_context,
        context_name="retrieved_module_context",
    )
    retrieved_value_context = filter_backend_owned_context_list(
        retrieved_value_context,
        context_name="retrieved_value_context",
    )
    if DISABLE_EXTERNAL_RAG_CONTEXT and not any(
        isinstance(item, dict) and item.get("source") == "backend_context_policy"
        for item in retrieved_value_context
    ):
        retrieved_value_context.append(build_backend_context_policy())
    azure_consumer_routing_context = _get_azure_consumer_routing_context(retrieved_value_context)
    backend_variable_declaration_context = build_backend_variable_declaration_context(
        prompt=prompt,
        cloud=selected_cloud or "",
        workflow=workflow or "",
        retrieved_module_context=retrieved_module_context,
        retrieved_value_context=retrieved_value_context,
    )
    if backend_variable_declaration_context:
        retrieved_value_context.append(backend_variable_declaration_context)

    if selected_cloud:
        clouds_to_include = [selected_cloud]
    else:
        clouds_to_include = list(thread_state.keys())

    for cloud in clouds_to_include:
        state = thread_state.get(cloud)
        if not state:
            continue

        base_branch = github_base_branch_for_cloud(cloud)
        source_branch = state["branch"] if state.get("has_open_pr") and github_branch_exists(cloud, state["branch"]) else base_branch
        context_root = state.get("environment_path") or state["folder"]
        existing_files = load_existing_tf_files_for_context(cloud,source_branch, context_root)

        context_blocks.append(
            {
                "cloud": cloud,
                "pr_url": state.get("pr_url"),
                "pr_number": state.get("pr_number"),
                "branch": state["branch"],
                "source_branch_for_context": source_branch,
                "folder": state["folder"],
                "update_mode": "modify_existing_in_same_folder",
                "existing_files": existing_files,
            }
        )

    instructions = [
        "You are generating Terraform changes for exactly one target cloud.",
        "Return valid JSON only.",
        "Return complete updated .tf and .tfvars files only.",
        "Preserve nested relative Terraform file paths exactly as returned.",
        "Do not create a new folder for follow-up changes unless explicitly requested.",
        "If existing_pr_context is present, update the existing Terraform in the same folder for the target cloud.",
        "If the previous PR was merged, continue from the Terraform currently present in the base branch.",
        "Use workflow, retrieved_module_context, and retrieved_value_context as high-priority guidance when provided.",
        "Never emit a source-only module block if required inputs are missing.",
        "If a module exists but required inputs cannot be inferred safely, ask for clarification instead of returning a partial module block.",
        "Backend-only variable declaration policy: do not use RAG/KB to infer variable values, types, defaults, or repo patterns; use only backend_variable_declaration_context and backend-owned GitHub context.",
        "For generated AWS and Azure module variables.tf/vars.tf files, every variable block must include description and type. A description-only variable block is invalid.",
        "For generated module bool variables, default to false unless the user explicitly provided a different safe value. For number variables, default to -1 unless explicitly provided. For map/list/set/object variables, use {}, [], [], or null respectively unless backend context provides a full safe default.",
        "For generated module string variables, include a default only when the user explicitly provided a non-sensitive value or backend GitHub context supplies an approved value/reference; otherwise ask for the value/reference in natural language before returning JSON.",
        "Never invent AMIs, subnet IDs, security group IDs, account IDs, ARNs, passwords, keys, tokens, connection strings, or private IDs. Use backend-approved references or ask.",
        "Every infrastructure response must contain at least one Terraform or tfvars file in the files array.",
        "For follow-up changes in an existing PR context, update the existing Terraform/tfvars files and return the full updated file contents.",
        "Do not return an empty files array.",
        "If the request is a rename or small update to an existing resource in existing_pr_context, modify the existing file and return that updated file.",
        "For infrastructure JSON, include repo_target.",
        "Valid repo_target values are: tf-devops, vena_repos, tf-azure-hub, azure-module-repo.",
      ]

    if azure_consumer_routing_context:
        instructions.extend([
            "Azure consumer routing is backend-authoritative for this request.",
            f"Generate the module invocation only in backend-selected file '{azure_consumer_routing_context.get('target_consumer_filename')}'.",
            f"Generate variable values only in existing file '{azure_consumer_routing_context.get('target_tfvars_filename')}'.",
            "For an object-backed new Azure instance, return the complete three-file write-set together: the backend-selected definition file, the existing variables.tf with the dedicated object declaration appended, and the target environment's own tfvars file with a concrete cloned object assignment.",
            "variables.tf must contain the full existing content plus only the appended declaration whose type exactly matches the nearest sibling variable; never omit this file when the new module introduces a dedicated object root.",
            "Every variables.tf declaration you return must be a complete balanced HCL variable block. For object types, `type = object({ ... })` only closes the object type expression; you must also add the final variable-block close brace. Prefer the backend-generated conflict-safe form, where the final line is `} # terrabot:close-variable <name>` followed by `# terrabot:end-variable <name>`.",
            "Never defer variables.tf to a later turn and never claim it will be added later. The invocation, declaration, and environment values must be present in the same response.",
            "Every returned file must contain the full final file content, including all existing content and the new additions.",
            "Never create a different module invocation file. If backend source matching found an existing file, use it; if backend_new_azure_consumer_routing is present, use only the backend-selected new file.",
            "Never remove, rewrite, or shorten existing Terraform blocks, comments, locals, providers, data sources, modules, or tfvars values.",
            "Do not place concrete variable values in the module invocation .tf file; put values in the backend-selected tfvars file.",
            "For source-matched Azure modules, follow the existing matched module block pattern: use its var.*, local.*, resource, lookup(), and merge() expressions instead of hardcoded literals in the new module invocation.",
            "When the user confirms suggested values, copy the relevant suggested_variable_values into the backend-selected tfvars file; the tfvars file must contain a real new value assignment for this request and must not be returned unchanged.",
            "Preserve the existing tfvars content exactly and append/merge only the new assignments needed for the new resource.",
            "All tfvars content you return must already be terraform-fmt clean. Align equals signs in object attributes exactly as terraform fmt would, and never duplicate keys inside the same object value such as account_tier or account_replication.",
            "The target tfvars file must contain a real new variable value assignment for this request; never return the tfvars file unchanged.",
            "Use suggested_variable_values, existing_consumer_file_content, existing_tfvars_file_content, common_tfvars_file_content, and variables_tf_file_content from retrieved_value_context.",
            "If the user confirmed suggested values and did not override a field, use the backend suggested/default value; never leave the generated tfvars assignment blank or as an empty stub when a suggested value exists.",
            "For object-style repo patterns, keep module inputs as references such as var.<new_object>.account_tier, and add the real object value to the routed tfvars file.",
            "Never emit a new tfvars object with only containers = [] when the matched existing tfvars/common.tfvars object contains populated container or data protection values; copy the suggested object and let the user override only requested fields.",
            "If a sensitive required value has no approved suggested/default value, ask for that value in natural language and do not return JSON.",
            "When suggesting values, prefer existing module argument expressions and existing tfvars values from retrieved_value_context.",
        ])

    aws_env_path = None
    if selected_cloud == "aws":
        for item in retrieved_value_context:
            env_path = (item or {}).get("environment_path")
            if isinstance(env_path, str) and env_path.startswith("terraform/"):
                aws_env_path = env_path
                break

    if aws_env_path:
        instructions.extend([
            f"For this AWS request, use the resolved environment folder '{aws_env_path}'.",
            "For AWS follow-up changes, update the same existing Terraform file or folder in that AWS environment when possible.",
            "Do not create a new changes/<thread>/ path for AWS follow-up updates when an existing AWS environment file already exists.",
            "Return file paths either as full terraform/... paths or as paths relative to the resolved AWS environment folder.",
            "If the existing AWS file is terraform/dev_aws/minidev/redshift.tf, return redshift.tf or the full terraform path, not changes/<thread>/redshift.tf.",
            "Do not ask for clarification just because a default AWS environment can be applied safely.",
            "If the user explicitly changed the AWS environment, keep writing changes to that exact requested environment folder.",
        ])

    if selected_cloud:
        instructions.extend([
            f"The target cloud is strictly '{selected_cloud}'.",
            f"Set cloud='{selected_cloud}' in the response.",
            f"Do not return files for any other cloud.",
        ])

        if selected_cloud == "aws":
            instructions.extend([
                "Set repo_target='tf-devops'.",
            ])
            if workflow == "aws_infra_modification":
                instructions.extend([
                    "This is an AWS modification workflow. Set workflow='aws_infra_modification'.",
                    "Use backend_existing_infra_code_match from retrieved_value_context as the source of truth for existing Terraform code.",
                    "Edit only matched existing files and return full final file contents for changed files only.",
                    "Do not create a new module or resource to represent an update/delete/fix request.",
                ])
            else:
                instructions.extend([
                    "For AWS consumer generation, use only verified local modules listed in retrieved_module_context from tf-devops/terraform/modules.",
                    "Never invent, suggest, or ask about module names that are not present in retrieved_module_context.",
                    "Every AWS module block source must exactly use a retrieved module_source value, another verified local path under tf-devops/terraform/modules, or the proposed_new_module_path when workflow is aws_module_creation.",
                ])
                if workflow != "aws_module_creation":
                    instructions.append("Do not create files under terraform/modules; this workflow consumes existing approved modules only.")

        if selected_cloud == "azure":
            instructions.extend([
                "For Azure, return Terraform file paths relative to the Azure target folder only.",
                "Do not prefix returned filenames with 'azure/'.",
                "Do not return Azure filenames under 'terraform/'.",
                "For Azure follow-up changes in the same thread, update the same files/folder already used by the existing Azure PR when present.",
                "If retrieved_module_context includes module_source_url, use that exact module source string unchanged.",
                "Do not rewrite an SSH GitHub module source into git::https format.",
                "Do not append '//' for root-module usage.",
                "For root-module usage, preserve the exact source format provided by retrieved_module_context.",
                "For Azure, use only verified module repository URLs supplied in retrieved_module_context.",
                "Do not construct or guess a GitHub module source URL.",
                "Do not invent module inputs, defaults, or example values not present in retrieved_value_context.",
                "If required values are missing, ask for clarification.",
                "If a similar module was provided rather than an exact match, describe it briefly and ask for confirmation before generating Terraform.",
                "If workflow indicates module repo creation, generate only the repo-creation or module-repo files for that stage.",
                "Do not generate tf-azure-hub consumer code until a verified module repository path exists.",
            ])

    if workflow:
        instructions.append(f"The workflow is '{workflow}'.")

        if workflow == "aws_module_consumer":
          instructions.extend([
        "For AWS tf-devops, retrieved_module_context is the source of truth for allowed modules; it was read by the backend from live tf-devops/terraform/modules.",
        "Generate Terraform only with module_source values from retrieved_module_context or verified existing module paths shown there.",
        "If the requested module is not in retrieved_module_context, do not suggest a guessed module such as ec2_instance and do not generate Terraform JSON.",
        "Use inputs_detected, required_inputs_detected, outputs_detected, and consumer_examples from the selected retrieved module only.",
        "If required values are missing, ask for those values without naming any unverified module.",
        "Prefer reusing existing consumer examples over creating new patterns.",
        "Never create new local module implementation files under terraform/modules in this workflow.",
         ])
        elif workflow == "aws_module_creation":
          instructions.extend([
        "This workflow is allowed only after backend AWS module discovery found no verified module and the user confirmed creating a new one.",
        "Create module implementation files under terraform/modules/<new_module_name>/ and a consumer file under the resolved terraform environment folder.",
        "The consumer module block must reference the new local module using the exact relative path from that environment folder to terraform/modules/<new_module_name>.",
        "Do not use remote module sources or unverified module paths.",
        "Do not guess account-specific values; use variables for missing AMIs, subnet IDs, security group IDs, ARNs, VPC IDs, and KMS keys.",
         ])
        elif workflow == "azure_consumer_generation":
            instructions.extend([
                "For Azure tf-azure-hub existing-module consumption, backend source matching determines the target module invocation file.",
                "Set repo_target='tf-azure-hub'.",
                "Use exact module_source_url from retrieved_module_context without rewriting the source or ref.",
                "Generate a single-instance module call unless the verified module inputs explicitly require map/for_each semantics.",
                "Do not use for_each or each.value unless the selected module variables and existing tf-azure-hub pattern require it.",
                "Module invocation code must be added to the backend-selected existing .tf file and must preserve all existing file content.",
                "Variable values must be added to the backend-selected existing tfvars file under vars/common.tfvars or vars/{npr,prd,sbx}/tier.tfvars, preserving all existing content.",
                "The tfvars file must be changed in the JSON response; returning it unchanged is invalid because the PR would only contain the module invocation file.",
                "Do not put concrete environment values in the module invocation .tf file.",
                "If required input values are not confirmed by the user or cannot be safely reused from suggested_variable_values, ask for values in natural language and do not return JSON.",
                "Do not create a new consumer .tf file for a source-matched existing Azure module.",
            ])
        elif workflow == "azure_module_repo_creation":
         instructions.extend([
             "You are in the Azure module REPOSITORY CREATION stage only.",
             "This stage creates a PR in terraform-github/vena_repos that defines a new GitHub repository using the existing repo module.",
             "Set workflow='azure_module_repo_creation'.",
             "Set repo_target='vena_repos'.",
             "Return exactly one file.",
             "The filename must be root-level and may use the requested repository name, for example azure_linux_vm_module.tf.",
             "The GitHub repository name may be any valid repo name supplied by the user; do not force a tf-module or tf_module prefix.",
             "The file content must use module source '../modules/repo'.",
             "Set merge_commit_title to PR_TITLE or MERGE_MESSAGE only; use PR_TITLE by default.",
             "Set merge_commit_message to PR_BODY, PR_TITLE, or BLANK only; use PR_BODY by default. BLANK is a GitHub enum value here, not a placeholder.",
             "Do not use resource \"github_repository\".",
             "Do not generate Azure infrastructure.",
             "Do not generate azurerm_* resources.",
             "Do not generate provider blocks.",
             "Do not generate variables, outputs, locals, terraform blocks, main.tf, variables.tf, outputs.tf, versions.tf, README, repo_name, folders, changes/, tf-azure-hub/, terraform/, or azure/ paths.",
              "The module implementation files are generated later in azure_module_repo_population, not now.",
          ])
            
        elif workflow == "azure_module_repo_population":
            instructions.extend([
                "Populate the verified Azure module repository with module implementation files.",
                "Set repo_target='azure-module-repo'.",
                "Include target_module_repo_full_name from retrieved_module_context.repo_full_name in the JSON response.",
                "Return file paths relative to the module repository root only.",
                "Do not prefix files with terraform/, tf-azure-hub/, vena-repos/, azure/, or changes/.",
                "Use only retrieved_module_context and retrieved_value_context grounded from the real verified module repo and real consumer examples.",
                "Always generate root-level main.tf, variables.tf, and outputs.tf.",
                "main.tf must contain real Terraform implementation code, not comments or placeholder text.",
                "variables.tf must contain real variable blocks for every configurable module input.",
                "Every variables.tf variable block must include description and type. A description-only variable block is invalid.",
                "Use backend_variable_declaration_context: bool defaults false, number defaults -1, map defaults {}, list/set defaults [], object defaults null, and string defaults only when explicitly user-provided or backend-approved.",
                "For missing string/private values such as subnet IDs, principal IDs, passwords, client secrets, key vault secret IDs, tenant IDs, subscription IDs, or private endpoints, ask for the approved value/reference before returning JSON.",
                "outputs.tf must contain real output blocks for values consumers need.",
                "Do not return comment-only files.",
                "Do not use TODO, placeholder, pending design, fill this, replace me, CHANGEME, or similar text.",
                "If the request does not contain enough design detail to create a correct module implementation, ask for clarification instead of returning JSON.",
                "Generate versions.tf when useful for provider/version constraints.",
                "Do not return README.md as the only generated file.",
                "Do not generate README.md unless the user explicitly requested documentation.",
                "If README.md is generated, it must be named README.md, never README.md.tf.",
                "If required values, variable meanings, or outputs cannot be inferred from grounded context, ask for clarification instead of inventing defaults.",
                "Do not generate tf-azure-hub consumer Terraform in this response.",
            ])
        elif workflow == "azure_module_discovery":
            instructions.extend([
                "Do not generate Terraform in this stage.",
                "This backend-only stage should normally not reach the model.",
            ])
            

    payload = {
        "request_type": "terraform_update_or_generation",
        "target_cloud": selected_cloud,
        "workflow": workflow,
        "user_request": prompt,
        "instructions": instructions,
        "retrieved_module_context": retrieved_module_context,
        "retrieved_value_context": retrieved_value_context,
        "backend_azure_consumer_routing": azure_consumer_routing_context,
        "existing_pr_context": context_blocks,
    }

    return json.dumps(payload, indent=2)

def store_pending_infra_change(
    thread_id: str,
    jira_ticket: str,
    prompt: str,
    agent_result: dict,
    ticket_link: str = "",
    ticket_title: str = "",
):
    cloud = normalize_cloud(agent_result.get("cloud"))
    repo_target = normalize_repo_target(
        cloud,
        repo_target=agent_result.get("repo_target"),
        workflow=agent_result.get("workflow"),
    )
    key = build_pending_change_key(thread_id, jira_ticket, cloud, repo_target, prompt)

    PENDING_INFRA_CHANGES[key] = {
        "thread_id": thread_id,
        "jira_ticket": (jira_ticket or "").strip().upper(),
        "ticket_link": (ticket_link or "").strip(),
        "ticket_title": (ticket_title or "").strip(),
        "prompt": prompt,
        "cloud": cloud,
        "repo_target": repo_target,
        "state_bucket": state_bucket_for_target(cloud, repo_target, agent_result.get("workflow")),
        "agent_result": agent_result,
    }
    return key

def build_user_friendly_error(message: str) -> str:
    text = (message or "").strip()
    lower = text.lower()

    if (
        "terrabot blocked the generated change before any branch write" in lower
        or "unsafe_generated_change" in lower
        or "substantially shorter than the live repository file" in lower
        or "does not preserve any existing terraform block" in lower
        or "removes too many existing" in lower
        or "repository-content placeholder" in lower
    ):
        return (
            "Terrabot could not produce a backend-valid Terraform change after internal "
            "repair attempts. No repository changes were written."
        )

    if "cloud must be either" in lower:
        return "Please specify which cloud you want to use: AWS or Azure."

    if "azure_module_repo_creation" in lower:
        return (
            "The repo-creation step must create exactly one vena_repos module definition file "
            "using module '../modules/repo'. It must not generate module implementation files, "
            "Azure resources, variables, outputs, or github_repository resources."
        )

    if "could not parse json from agent response" in lower:
        return (
            "The agent returned an invalid Terraform response. Please retry with a clearer request."
        )

    if "non-empty 'files' array" in lower:
        return (
            "The agent returned an infrastructure response without Terraform files. "
            "Please retry with a single-cloud request."
        )

    if "mcp approval requests do not have an approval" in lower:
        return (
            "The agent requested tool approval but one approval step was missed. "
            "Please restart the backend and retry the request."
        )

    if "tool approval but one approval step was missed" in lower:
        return (
            "The agent requested tool approval but one approval step was missed. "
            "Please restart the backend and retry the request."
        )

    if "generated module variable declarations require backend-approved defaults" in lower or "module variable declarations are incomplete" in lower or "variables.tf is missing safe backend-approved" in lower:
        return (
            "The generated module variables.tf is missing required type/default information. "
            "Please provide the missing safe string values or approved repo references. "
            "The backend will not invent AMIs, subnet IDs, security group IDs, account IDs, ARNs, passwords, keys, or tokens."
        )

    if "invalid content for file" in lower:
        return "A Terraform file was generated with invalid content. Please retry with a simpler request."

    if "no response returned from agent" in lower:
        return "The agent did not return a result. Please retry your request."

    if "unexpected keyword argument 'workflow'" in lower:
        return "The backend function signature was outdated. The service code must support workflow-aware infra routing."

    if "'bool' object has no attribute 'request_type'" in lower:
        return "The router returned a boolean instead of a structured decision. The backend safely normalizes router output."

    if "git" in lower and "pull request" in lower:
        return (
            "GitHub could not open or update the pull request for this branch. "
            "The service opens a fresh PR cycle automatically when the previous PR is already merged or closed."
        )

    if (
        "unverified aws module source" in lower
        or "aws module blocks must use verified local" in lower
        or "tf-devops/terraform/modules" in lower and "aws" in lower
    ):
        return f"Your request could not be completed safely: {text}"

    if "no verified module inputs found" in lower:
        return "The verified module exists, but no module inputs could be read from variables.tf. No PR was created."

    if "missing required verified module inputs" in lower:
        return f"Your request could not be completed safely: {text}"

    if "verified azure module source url" in lower:
        return "The verified Azure module source URL was missing or invalid. No PR was created."

    if any(term in lower for term in ["instance type", "instance_size", "t2.micro", "t3.micro"]):
        return "The requested instance type may be invalid or unsupported."

    if "vm size" in lower or "standard_" in lower:
        return "The requested VM size may be invalid or unavailable."

    if any(term in lower for term in ["subnet", "cidr", "address prefix"]):
        return "The subnet range looks invalid or conflicting."

    if "already exists" in lower or "duplicate" in lower:
        return "A resource with the same name already exists. Try changing the resource name or updating the existing resource."

    if "azure module discovery" in lower:
        return "The backend could not complete Azure module discovery in vena_repos. Please retry."

    return f"Your request could not be completed: {text}"

def is_valid_jira_ticket(ticket: str) -> bool:
    return bool(re.fullmatch(r"STO-\d{4,}", (ticket or "").strip().upper()))


def build_conversation_label(jira_ticket: str, conversation_id: Optional[str]) -> str:
    ticket = (jira_ticket or "").strip().upper()
    if ticket:
        return ticket
    return conversation_id or "New"

def build_pending_change_key(
    thread_id: str,
    jira_ticket: str,
    cloud: str,
    repo_target: str = "",
    prompt: str = "",
) -> str:
    del prompt
    raw = (
        f"{thread_id or 'no-thread'}::"
        f"{(jira_ticket or '').strip().upper()}::"
        f"{safe_normalize_cloud(cloud) or 'unknown'}::"
        f"{(repo_target or '').strip().lower() or 'default'}"
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _extract_owner_repo(value: Any | None, default_owner: Optional[str] = None) -> tuple[str, str]:
    value = (value or "").strip()
    if not value:
        return "", ""

    if value.startswith("https://github.com/"):
        value = value.replace("https://github.com/", "", 1).strip("/")

    if "/" in value:
        owner, repo = value.split("/", 1)
        return owner.strip(), repo.strip().strip("/")

    return (default_owner or GITHUB_OWNER or "").strip(), value.strip("/")


def _workflow_for_state_bucket(bucket_name: str) -> str:
    return {
        "aws": "aws_module_consumer",
        "azure_module": "azure_module_repo_creation",
        "azure_module_population": "azure_module_repo_population",
        "azure_consumer": "azure_consumer_generation",
    }.get(bucket_name or "", "")


def _repo_target_for_state_bucket(bucket_name: str) -> str:
    return {
        "aws": "tf-devops",
        "azure_module": "vena_repos",
        "azure_module_population": AZURE_MODULE_REPO_TARGET,
        "azure_consumer": "tf-azure-hub",
    }.get(bucket_name or "", "")


def _stage_label_for_state_bucket(bucket_name: str) -> str:
    return {
        "aws": "AWS tf-devops PR",
        "azure_module": "Azure module repo definition PR",
        "azure_module_population": "Azure module implementation PR",
        "azure_consumer": "Azure tf-azure-hub consumer PR",
    }.get(bucket_name or "", bucket_name or "PR")


def _pr_status_from_state(state: dict) -> str:
    state = state or {}
    raw_candidates = [
        state.get("status"),
        state.get("latest_pr_state"),
        state.get("state"),
        state.get("pr_state"),
    ]
    raw_values = [str(value).strip().lower() for value in raw_candidates if value]

    if state.get("merged") is True or state.get("latest_pr_merged") is True or state.get("merged_at") or "merged" in raw_values:
        return "merged"
    if state.get("closed") is True or state.get("closed_at") or "closed" in raw_values or "declined" in raw_values:
        return "closed"
    if state.get("has_open_pr") is True or "open" in raw_values:
        return "open"
    if raw_values:
        return raw_values[0]
    if state.get("pr_number") and state.get("pr_url"):
        return "unknown"
    return "pending"


def _azure_consumer_module_name_from_repo(repo_name: str) -> str:
    module_name = re.sub(r"^tf-module-azure-", "", (repo_name or "").strip())
    module_name = re.sub(r"^tf-azure-", "", module_name)
    module_name = re.sub(r"[^a-z0-9_]+", "_", module_name.replace("-", "_").lower()).strip("_")
    return module_name or "azure_module"


def _azure_consumer_state_contains_module_invocation(
    state: dict,
    target_owner: str,
    target_repo: str,
) -> bool:
    """Best-effort check that an existing tf-azure-hub PR/file already invokes the target module."""
    if not isinstance(state, dict) or not state or not target_repo:
        return False

    target_owner = (target_owner or GITHUB_OWNER or "").strip()
    target_repo = (target_repo or "").strip()
    expected_source_fragments = [
        f"git@github.com:{target_owner}/{target_repo}.git" if target_owner else "",
        f"/{target_repo}.git",
        target_repo,
    ]
    expected_source_fragments = [item for item in expected_source_fragments if item]

    owner, repo = _state_repo_owner_name("azure_consumer", state)
    owner = owner or GITHUB_OWNER
    repo = repo or GITHUB_AZURE_REPO

    candidate_paths = []
    pr_number = state.get("pr_number")
    if owner and repo and pr_number:
        try:
            for item in github_list_pull_request_files_by_repo(owner, repo, int(pr_number)):
                path = (item or {}).get("filename") or (item or {}).get("path") or ""
                patch = (item or {}).get("patch") or ""
                if path.endswith(".tf") and path not in candidate_paths:
                    candidate_paths.append(path)
                if patch and all(fragment in patch for fragment in ["module", "source"]) and any(
                    fragment in patch for fragment in expected_source_fragments
                ):
                    return True
        except Exception as file_error:
            print(f"Azure consumer PR file inspection skipped for {owner}/{repo}#{pr_number}: {file_error}")

    expected_filename = f"{_azure_consumer_module_name_from_repo(target_repo)}.tf"
    if expected_filename not in candidate_paths:
        candidate_paths.append(expected_filename)

    candidate_refs = []
    for key in ("head_branch", "branch", "base_branch"):
        value = (state.get(key) or "").strip()
        if value and value not in candidate_refs:
            candidate_refs.append(value)

    if _pr_status_from_state(state) == "merged":
        base_branch = (state.get("base_branch") or GITHUB_AZURE_BASE_BRANCH or "main").strip()
        if base_branch and base_branch not in candidate_refs:
            candidate_refs.append(base_branch)

    for path in candidate_paths:
        if not path or not path.endswith(".tf"):
            continue
        for ref in candidate_refs:
            try:
                content = github_get_file_content(
                    "azure",
                    path,
                    ref,
                    repo_target="tf-azure-hub",
                    workflow="azure_consumer_generation",
                )
            except Exception:
                content = None

            if not content:
                continue

            content_lower = content.lower()
            if (
                "module" in content_lower
                and "source" in content_lower
                and any(fragment.lower() in content_lower for fragment in expected_source_fragments)
            ):
                return True

    return False


def _consumer_state_blocks_auto_creation(
    state: Optional[dict],
    target_owner: str = "",
    target_repo: str = "",
) -> bool:
    """Return True only when a real consumer PR/file for the target module already exists."""
    if not isinstance(state, dict) or not state:
        return False

    status = _pr_status_from_state(state)

    # Closed and folder-only pending states should not permanently block the
    # automatic consumer PR after module population has merged.
    if status in {"closed", "pending"}:
        return False

    has_pr_reference = bool(state.get("pr_number") or state.get("pr_url") or state.get("head_branch"))
    if not has_pr_reference:
        return False

    if target_repo:
        return _azure_consumer_state_contains_module_invocation(
            state,
            target_owner=target_owner,
            target_repo=target_repo,
        )

    return status in {"open", "merged", "unknown"}


def _state_repo_owner_name(bucket_name: str, state: dict) -> tuple[str, str]:
    state = state or {}
    workflow = state.get("workflow") or _workflow_for_state_bucket(bucket_name)
    repo_target = state.get("repo_target") or _repo_target_for_state_bucket(bucket_name)

    if bucket_name == "azure_module_population" or repo_target == AZURE_MODULE_REPO_TARGET:
        for key in ("target_module_repo_full_name", "module_repo_full_name", "repo_full_name", "folder"):
            owner, repo = _extract_owner_repo(state.get(key), default_owner=GITHUB_OWNER)
            if owner and repo:
                return owner, repo
        return "", ""

    cloud = state.get("cloud") or ("aws" if bucket_name == "aws" else "azure")
    try:
        return _require_setting(GITHUB_OWNER, "GITHUB_OWNER"), github_repo_for_cloud(
            cloud,
            repo_target=repo_target,
            workflow=workflow,
        )
    except Exception:
        return "", ""


def _refresh_single_pr_state_from_github(bucket_name: str, state: dict) -> dict:
    state = dict(state or {})
    if not state:
        return state

    workflow = state.get("workflow") or _workflow_for_state_bucket(bucket_name)
    repo_target = state.get("repo_target") or _repo_target_for_state_bucket(bucket_name)
    state["workflow"] = workflow
    state["repo_target"] = repo_target
    state["stage"] = state.get("stage") or _stage_label_for_state_bucket(bucket_name)

    owner, repo = _state_repo_owner_name(bucket_name, state)
    if owner and repo:
        state["repo_owner"] = owner
        state["repo_name"] = repo
        state["repo_full_name"] = f"{owner}/{repo}"

    pr = None
    pr_number = state.get("pr_number")

    try:
        if owner and repo and pr_number:
            pr = github_get_pull_request_by_repo(owner, repo, int(pr_number))

        if not pr and owner and repo and state.get("branch"):
            if bucket_name == "azure_module_population" or repo_target == AZURE_MODULE_REPO_TARGET:
                base_branch = state.get("base_branch") or github_get_repo_default_branch(owner, repo) or GITHUB_AZURE_BASE_BRANCH
                pr = github_find_pr_by_branch_by_repo(owner, repo, state["branch"], base_branch, state="open")
                if not pr:
                    pr = github_find_pr_by_branch_by_repo(owner, repo, state["branch"], base_branch, state="all")
            else:
                cloud = state.get("cloud") or ("aws" if bucket_name == "aws" else "azure")
                pr = github_find_pr_by_branch(
                    cloud,
                    state["branch"],
                    state="open",
                    repo_target=repo_target,
                    workflow=workflow,
                )
                if not pr:
                    pr = github_find_pr_by_branch(
                        cloud,
                        state["branch"],
                        state="all",
                        repo_target=repo_target,
                        workflow=workflow,
                    )
    except Exception as refresh_error:
        state["status_refresh_error"] = str(refresh_error)
        state["status"] = _pr_status_from_state(state)
        return state

    if pr:
        state["pr_number"] = pr.get("number") or state.get("pr_number")
        state["pr_url"] = pr.get("html_url") or state.get("pr_url")
        state["pr_title"] = pr.get("title") or state.get("pr_title")
        state["latest_pr_state"] = pr.get("state")
        state["latest_pr_merged"] = bool(pr.get("merged_at"))
        state["merged"] = bool(pr.get("merged_at"))
        state["merged_at"] = pr.get("merged_at")
        state["closed_at"] = pr.get("closed_at")
        state["has_open_pr"] = pr.get("state") == "open"
        state["base_branch"] = pr.get("base", {}).get("ref") or state.get("base_branch")
        state["head_branch"] = pr.get("head", {}).get("ref") or state.get("head_branch") or state.get("branch")
        state["merge_commit_sha"] = pr.get("merge_commit_sha") or state.get("merge_commit_sha")
        body = pr.get("body") or ""
        if body and not state.get("original_prompt"):
            state["original_prompt"] = _extract_original_prompt_from_pr_body(body)

    state["status"] = _pr_status_from_state(state)
    return state


def _extract_original_prompt_from_pr_body(body: str) -> str:
    body = body or ""
    marker = "\n## Request\n"
    if marker in body:
        return body.split(marker, 1)[1].strip()

    marker = "## Request"
    if marker in body:
        return body.split(marker, 1)[1].strip()

    return ""



def _extract_azure_module_repo_name_from_text(text: str) -> str:
    text = text or ""

    module_repo_match = re.search(
        r'(?m)^\s*name\s*=\s*"([A-Za-z0-9][A-Za-z0-9_.-]{0,99})"',
        text,
        re.IGNORECASE,
    )
    if module_repo_match:
        repo_name = sanitize_azure_module_repo_name(module_repo_match.group(1))
        if repo_name:
            return repo_name

    target_match = re.search(
        r"\b(?:target_)?(?:module_)?repo(?:sitory)?_?name\s*(?:=|:)\s*`?([A-Za-z0-9_.-]+)`?",
        text,
        re.IGNORECASE,
    )
    if target_match:
        repo_name = sanitize_azure_module_repo_name(target_match.group(1))
        if repo_name:
            return repo_name

    title_match = re.search(
        r"\bcreate\s+([A-Za-z0-9][A-Za-z0-9_.-]{1,99})\s+module\s+repo(?:sitory)?\b",
        text,
        re.IGNORECASE,
    )
    if title_match:
        repo_name = sanitize_azure_module_repo_name(title_match.group(1))
        if repo_name and repo_name not in {"azure", "module", "repo", "repository"}:
            return repo_name

    inline_match = re.search(
        r"\b([A-Za-z0-9][A-Za-z0-9_.-]*(?:azure|module)[A-Za-z0-9_.-]*)\b",
        text,
        re.IGNORECASE,
    )
    if inline_match:
        repo_name = sanitize_azure_module_repo_name(inline_match.group(1))
        if repo_name and repo_name not in {"azure", "module", "terraform-module"}:
            return repo_name

    return ""

def infer_azure_module_repo_target_from_creation_state(state: dict) -> tuple[str, str]:
    state = state or {}

    for key in (
        "target_module_repo_full_name",
        "module_repo_full_name",
        "repo_full_name",
    ):
        owner, repo = _extract_owner_repo(state.get(key), default_owner=GITHUB_OWNER)
        if owner and repo and repo != GITHUB_VENA_REPO:
            return owner, repo

    for key in ("target_module_repo_name", "module_repo_name", "repo_name"):
        value = (state.get(key) or "").strip()
        if value and value != GITHUB_VENA_REPO:
            return _require_setting(GITHUB_OWNER, "GITHUB_OWNER"), value

    pr_number = state.get("pr_number")
    if not pr_number:
        return "", ""

    try:
        pr = github_get_pull_request(
            "azure",
            int(pr_number),
            repo_target="vena_repos",
            workflow="azure_module_repo_creation",
        )
    except Exception:
        pr = None

    if pr:
        repo_name = _extract_azure_module_repo_name_from_text(
            "\n".join([pr.get("title") or "", pr.get("body") or ""])
        )
        if repo_name:
            return _require_setting(GITHUB_OWNER, "GITHUB_OWNER"), repo_name

    try:
        files = github_list_pull_request_files(
            "azure",
            int(pr_number),
            repo_target="vena_repos",
            workflow="azure_module_repo_creation",
        )
    except Exception:
        files = []

    read_refs = []
    if state.get("status") == "merged" or state.get("latest_pr_merged") or state.get("merged_at"):
        read_refs.append(github_base_branch_for_cloud("azure", repo_target="vena_repos", workflow="azure_module_repo_creation"))
    if state.get("branch"):
        read_refs.append(state.get("branch"))
    read_refs.append(github_base_branch_for_cloud("azure", repo_target="vena_repos", workflow="azure_module_repo_creation"))

    seen_refs = []
    for ref in read_refs:
        if ref and ref not in seen_refs:
            seen_refs.append(ref)

    for item in files or []:
        path = (item or {}).get("filename") or (item or {}).get("path") or ""
        if not path.endswith(".tf"):
            continue

        for ref in seen_refs:
            try:
                content = github_get_file_content(
                    "azure",
                    path,
                    ref,
                    repo_target="vena_repos",
                    workflow="azure_module_repo_creation",
                )
            except Exception:
                content = None

            repo_name = _extract_azure_module_repo_name_from_text(content or "")
            if repo_name:
                return _require_setting(GITHUB_OWNER, "GITHUB_OWNER"), repo_name

    return "", ""


def recover_azure_module_population_state(thread_id: str, owner: str, repo: str) -> dict | None:
    if not thread_id or not owner or not repo:
        return None

    repo_metadata = github_get_repo(owner, repo)
    if not repo_metadata:
        return None

    base_branch = repo_metadata.get("default_branch") or GITHUB_AZURE_BASE_BRANCH
    prefix = f"{GITHUB_PR_SOURCE_BRANCH_AZURE}-azure-module-population-{stable_thread_key(thread_id)}"

    candidate_branches = [prefix]
    try:
        candidate_branches.extend(github_list_matching_branches_by_repo(owner, repo, prefix))
    except Exception:
        pass

    candidate_branches = _dedupe_preserving_order(candidate_branches)
    selected = None
    latest_pr = None
    open_pr = None

    for branch in candidate_branches:
        try:
            candidate_open = github_find_pr_by_branch_by_repo(owner, repo, branch, base_branch, state="open")
        except Exception:
            candidate_open = None
        if candidate_open:
            selected = branch
            open_pr = candidate_open
            latest_pr = candidate_open
            break

        try:
            candidate_latest = github_find_pr_by_branch_by_repo(owner, repo, branch, base_branch, state="all")
        except Exception:
            candidate_latest = None

        if candidate_latest:
            selected = branch
            latest_pr = candidate_latest

    if not selected:
        selected = prefix

    branch_exists = False
    try:
        branch_exists = github_branch_exists_by_repo(owner, repo, selected)
    except Exception:
        branch_exists = False

    if not branch_exists and not open_pr and not latest_pr:
        return None

    state = {
        "branch": selected,
        "pr_number": (open_pr or latest_pr or {}).get("number"),
        "pr_url": (open_pr or latest_pr or {}).get("html_url"),
        "cloud": "azure",
        "repo_target": AZURE_MODULE_REPO_TARGET,
        "state_bucket": "azure_module_population",
        "folder": f"{owner}/{repo}",
        "cycle": 1,
        "has_open_pr": bool(open_pr),
        "latest_pr_state": (latest_pr or {}).get("state"),
        "latest_pr_merged": bool((latest_pr or {}).get("merged_at")),
        "merged_at": (latest_pr or {}).get("merged_at"),
        "closed_at": (latest_pr or {}).get("closed_at"),
        "target_module_repo_owner": owner,
        "target_module_repo_name": repo,
        "target_module_repo_full_name": f"{owner}/{repo}",
        "workflow": "azure_module_repo_population",
        "base_branch": base_branch,
    }
    state["status"] = _pr_status_from_state(state)
    return state


def recover_merged_azure_module_population_state_from_repo_files(
    thread_id: str,
    owner: str,
    repo: str,
    original_prompt: str = "",
) -> dict | None:
    """Synthesize a merged population state when the module repo is already populated.

    GitHub branch cleanup can make the original population PR unrecoverable by
    head branch. If the target module repo default branch already contains the
    required validated module files, treat the population stage as complete so
    the automatic tf-azure-hub consumer PR can continue.
    """
    if not thread_id or not owner or not repo:
        return None

    repo_metadata = github_get_repo(owner, repo)
    if not repo_metadata:
        return None

    base_branch = (repo_metadata.get("default_branch") or GITHUB_AZURE_BASE_BRANCH or "main").strip()
    if not base_branch:
        return None

    try:
        invalid_or_missing = get_invalid_or_missing_azure_module_population_core_files(
            owner,
            repo,
            base_branch,
        )
    except Exception as validation_error:
        print(f"Azure module population base-branch validation skipped for {owner}/{repo}@{base_branch}: {validation_error}")
        return None

    if invalid_or_missing:
        return None

    branch_prefix = f"{GITHUB_PR_SOURCE_BRANCH_AZURE}-azure-module-population-{stable_thread_key(thread_id)}"
    state = {
        "branch": branch_prefix,
        "head_branch": branch_prefix,
        "base_branch": base_branch,
        "pr_number": None,
        "pr_url": None,
        "pr_title": "[AZURE] Populate module repository",
        "cloud": "azure",
        "repo_target": AZURE_MODULE_REPO_TARGET,
        "state_bucket": "azure_module_population",
        "folder": f"{owner}/{repo}",
        "cycle": 1,
        "has_open_pr": False,
        "latest_pr_state": "closed",
        "latest_pr_merged": True,
        "merged": True,
        "merged_at": "module_repo_default_branch_contains_required_files",
        "target_module_repo_owner": owner,
        "target_module_repo_name": repo,
        "target_module_repo_full_name": f"{owner}/{repo}",
        "workflow": "azure_module_repo_population",
        "original_prompt": original_prompt or "",
        "recovered_from_module_repo_files": True,
    }
    state["status"] = "merged"
    return state


def refresh_thread_pr_states(thread_id: str) -> dict:
    if not thread_id:
        return {}

    ensure_thread_meta(thread_id)
    recovered = dict(recover_thread_pr_state(thread_id) or {})
    meta = THREAD_PR_STATE.get(thread_id, {}).get("_meta", {"last_selected_cloud": None})

    for bucket_name in list(recovered.keys()):
        if bucket_name == "_meta" or not isinstance(recovered.get(bucket_name), dict):
            continue
        recovered[bucket_name] = _refresh_single_pr_state_from_github(bucket_name, recovered[bucket_name])

    azure_module_state = recovered.get("azure_module")
    if azure_module_state:
        owner, repo = infer_azure_module_repo_target_from_creation_state(azure_module_state)
        if owner and repo:
            azure_module_state["target_module_repo_owner"] = owner
            azure_module_state["target_module_repo_name"] = repo
            azure_module_state["target_module_repo_full_name"] = f"{owner}/{repo}"
            recovered["azure_module"] = azure_module_state

            if "azure_module_population" not in recovered:
                population_state = recover_azure_module_population_state(thread_id, owner, repo)
                if population_state:
                    recovered["azure_module_population"] = _refresh_single_pr_state_from_github(
                        "azure_module_population",
                        population_state,
                    )
                elif _pr_status_from_state(azure_module_state) == "merged":
                    population_state = recover_merged_azure_module_population_state_from_repo_files(
                        thread_id=thread_id,
                        owner=owner,
                        repo=repo,
                        original_prompt=azure_module_state.get("original_prompt") or "",
                    )
                    if population_state:
                        recovered["azure_module_population"] = population_state

    if recovered:
        THREAD_PR_STATE[thread_id] = dict(recovered)
        THREAD_PR_STATE[thread_id]["_meta"] = meta

    return {
        key: value
        for key, value in THREAD_PR_STATE.get(thread_id, {}).items()
        if key in ("aws", "azure_module", "azure_module_population", "azure_consumer") and isinstance(value, dict)
    }


def _build_azure_module_repo_context(owner: str, repo: str, original_prompt: str = "", resolved_ref: str = "") -> dict:
    repo_metadata = github_get_repo(owner, repo)
    default_branch = (repo_metadata or {}).get("default_branch") or GITHUB_AZURE_BASE_BRANCH or "main"
    resolved_ref = (resolved_ref or default_branch or "main").strip()

    return {
        "source": "backend_auto_new_azure_module_repo",
        "match_type": "new_module_created",
        "repo_name": repo,
        "repo_owner": owner,
        "repo_full_name": f"{owner}/{repo}",
        "target_module_repo_name": repo,
        "target_module_repo_full_name": f"{owner}/{repo}",
        "verified_repo_url": f"https://github.com/{owner}/{repo}",
        "verified_default_branch": default_branch,
        "resolved_ref": resolved_ref,
        "module_source_url": f"git@github.com:{owner}/{repo}.git?ref={resolved_ref}",
        "description": f"Azure module repository generated for: {original_prompt}",
        "resource_hints": re.findall(r"[a-z0-9]+", (original_prompt or "").lower())[:12],
    }


def generate_azure_module_repo_population_with_agent(
    conversation_id: str,
    original_prompt: str,
    target_owner: str,
    target_repo: str,
) -> dict:
    module_context = [
        _build_azure_module_repo_context(
            target_owner,
            target_repo,
            original_prompt=original_prompt,
        )
    ]
    value_context = [
        {
            "source": "backend_original_request_for_new_azure_module",
            "original_prompt": original_prompt,
            "target_module_repo_full_name": f"{target_owner}/{target_repo}",
        },
        {
            "source": "backend_azure_module_population_requirements",
            "required_root_files": list(AZURE_MODULE_POPULATION_REQUIRED_FILES),
            "main_tf_requirement": "must contain real Terraform resource, data, or module blocks",
            "variables_tf_requirement": "must contain variable blocks for configurable inputs",
            "outputs_tf_requirement": "must contain output blocks for useful consumer-facing values",
            "forbidden_content": list(AZURE_MODULE_POPULATION_FORBIDDEN_TEXT),
        },
    ]

    last_error = ""
    last_agent_reply = ""

    for attempt in range(1, 4):
        agent_input = build_agent_input_for_infra(
            original_prompt,
            conversation_id,
            selected_cloud="azure",
            workflow="azure_module_repo_population",
            retrieved_module_context=module_context,
            retrieved_value_context=value_context,
        )

        if last_error:
            retry_payload = {
                "task": "Retry Azure module repo population and return corrected Terraform infra JSON only.",
                "validation_error_from_backend": last_error,
                "previous_bad_agent_reply": last_agent_reply,
                "original_population_request": json.loads(agent_input),
                "required_files": list(AZURE_MODULE_POPULATION_REQUIRED_FILES),
                "absolute_rules": [
                    "Return valid JSON only. Do not include markdown or commentary.",
                    "Set cloud='azure', workflow='azure_module_repo_population', repo_target='azure-module-repo'.",
                    "Include target_module_repo_full_name for the verified target module repo.",
                    "Generate root-level main.tf, variables.tf, and outputs.tf.",
                    "main.tf must contain real Terraform resource, data, or module blocks.",
                    "variables.tf must contain real variable blocks with description and type for every variable.",
                    "For bool variables default to false; for number variables default to -1; for map/list/set/object variables use {}, [], [], or null; for string variables ask unless value is explicit or backend-approved.",
                    "Never invent private values such as subnet IDs, account IDs, tenant IDs, ARNs, passwords, keys, tokens, or secrets.",
                    "outputs.tf must contain real output blocks.",
                    "Do not return comment-only files or placeholder text.",
                    "Do not prefix paths with terraform/, tf-azure-hub/, vena_repos/, changes/, generated/, scratch/, or azure/.",
                ],
            }
            agent_input = json.dumps(retry_payload, indent=2)

        _conversation_id, agent_reply = call_agent(conversation_id, agent_input)
        last_agent_reply = agent_reply or ""

        if not last_agent_reply.strip():
            last_error = "No response returned from agent for Azure module repo population."
            continue

        try:
            agent_result = try_parse_agent_output(last_agent_reply)
            agent_result = finalize_agent_result_after_parse(agent_result, module_context)

            if agent_result.get("workflow") != "azure_module_repo_population":
                raise ValueError("Azure module repo population must return workflow='azure_module_repo_population'.")

            return agent_result
        except Exception as generation_error:
            last_error = str(generation_error)
            print(
                f"Azure module repo population attempt {attempt} failed for "
                f"{target_owner}/{target_repo}: {last_error}"
            )

    raise ValueError(
        "Foundry Terraform agent did not return a valid Azure module repo population payload after 3 attempts. "
        f"Last error: {last_error}"
    )



def get_invalid_or_missing_azure_module_population_core_files(owner: str, repo: str, ref: str) -> list[str]:
    if not owner or not repo or not ref:
        return list(AZURE_MODULE_POPULATION_REQUIRED_FILES)

    files = []
    missing = []

    for filename in AZURE_MODULE_POPULATION_REQUIRED_FILES:
        try:
            content = github_get_file_content_by_repo(owner, repo, filename, ref=ref)
        except Exception:
            content = None

        if not isinstance(content, str) or not content.strip():
            missing.append(filename)
            continue

        files.append({
            "filename": filename,
            "content": content,
        })

    if missing:
        return missing

    try:
        validate_azure_module_population_core_files({
            "mode": "infra",
            "cloud": "azure",
            "workflow": "azure_module_repo_population",
            "repo_target": AZURE_MODULE_REPO_TARGET,
            "files": files,
        })
        return []
    except Exception:
        return list(AZURE_MODULE_POPULATION_REQUIRED_FILES)


def build_grounded_azure_context_for_new_module_repo(
    target_owner: str,
    target_repo: str,
    selected_ref: str = "",
    original_prompt: str = "",
) -> dict:
    """Build module context directly from the populated module repo.

    This powers the automatic post-population tf-azure-hub consumer step. It
    reads the newly populated repo branch directly instead of depending on
    consumer-example search results.
    """
    target_owner = (target_owner or "").strip()
    target_repo = (target_repo or "").strip()
    if not target_owner or not target_repo:
        raise RuntimeError("Azure consumer generation requires a verified target module repo owner and name.")

    repo_metadata = github_get_repo(target_owner, target_repo)
    if not repo_metadata:
        raise RuntimeError(f"Verified Azure module repo was not found: {target_owner}/{target_repo}")

    default_branch = (repo_metadata.get("default_branch") or GITHUB_AZURE_BASE_BRANCH or "main").strip()
    resolved_ref = (selected_ref or default_branch or "main").strip()

    try:
        tf_paths = _list_tf_files_by_repo_ref(target_owner, target_repo, resolved_ref)
    except Exception as read_error:
        raise RuntimeError(
            f"Could not list Terraform files from verified Azure module repo "
            f"{target_owner}/{target_repo}@{resolved_ref}: {read_error}"
        )

    tf_files = []
    inputs = []
    required_inputs = []
    outputs = []

    for tf_path in tf_paths or []:
        try:
            content = github_get_file_content_by_repo(target_owner, target_repo, tf_path, ref=resolved_ref)
        except Exception:
            content = None

        if not content:
            continue

        tf_files.append({"path": tf_path, "content": content})
        inputs.extend(_extract_tf_variable_names_from_text(content))
        required_inputs.extend(_extract_required_variable_names_from_text(content))
        outputs.extend(_extract_tf_output_names_from_text(content))

    inputs = _dedupe_preserving_order(inputs)
    required_inputs = [
        name for name in _dedupe_preserving_order(required_inputs)
        if name in inputs
    ]
    outputs = _dedupe_preserving_order(outputs)

    if not tf_files:
        raise RuntimeError(
            f"No Terraform files were found in verified Azure module repo "
            f"{target_owner}/{target_repo}@{resolved_ref}."
        )

    if not inputs:
        raise RuntimeError(
            f"No module inputs were found in verified Azure module repo "
            f"{target_owner}/{target_repo}@{resolved_ref}. "
            "The module population PR must include variables.tf with real variable blocks before a tf-azure-hub consumer PR can be created."
        )

    file_paths = [item["path"] for item in tf_files]
    lower_paths = [item.lower() for item in file_paths]
    module_source_url = f"git@github.com:{target_owner}/{target_repo}.git?ref={resolved_ref}"

    return {
        "source": "backend_verified_new_azure_module_repo_files",
        "match_type": "new_module_created",
        "repo_name": target_repo,
        "repo_owner": target_owner,
        "repo_full_name": f"{target_owner}/{target_repo}",
        "target_module_repo_name": target_repo,
        "target_module_repo_full_name": f"{target_owner}/{target_repo}",
        "verified_repo_url": f"https://github.com/{target_owner}/{target_repo}",
        "verified_default_branch": default_branch,
        "resolved_ref": resolved_ref,
        "module_source_url": module_source_url,
        "description": f"Azure module repository generated for: {original_prompt}",
        "resource_hints": re.findall(r"[a-z0-9]+", (original_prompt or "").lower())[:12],
        "file_list": file_paths,
        "inputs_detected": inputs,
        "required_inputs_detected": required_inputs,
        "outputs_detected": outputs,
        "module_structure": {
            "file_count": len(tf_files),
            "root_tf_files": [item for item in file_paths if "/" not in item and item.endswith(".tf")],
            "has_main_tf": "main.tf" in lower_paths,
            "has_variables_tf": "variables.tf" in lower_paths,
            "has_outputs_tf": "outputs.tf" in lower_paths,
            "has_versions_tf": "versions.tf" in lower_paths,
            "has_readme": any(item.endswith("readme.md") for item in lower_paths),
        },
        "module_files": tf_files,
    }


def _build_azure_consumer_payload_from_verified_context(
    original_prompt: str,
    module_context: dict,
    thread_id: str = "",
) -> dict:
    module_context = module_context or {}
    routing_context = build_new_azure_consumer_file_routing_context(
        prompt=original_prompt,
        thread_id=thread_id,
        retrieved_module_context=[module_context],
        retrieved_value_context=[],
        tf_file_count=0,
        auto_confirm=True,
    )
    if not routing_context:
        raise ValueError("Could not build tf-azure-hub routing for the new Azure module consumer.")

    module_name = _azure_consumer_module_name_from_module_context(module_context)
    source_url = module_context.get("module_source_url") or ""
    inputs_to_emit = _dedupe_preserving_order(
        list(module_context.get("required_inputs_detected") or [])
        + list(module_context.get("inputs_detected") or [])
    )
    if not inputs_to_emit:
        raise ValueError("No verified module inputs are available to emit for the new Azure module consumer.")
    longest = max(len(name) for name in inputs_to_emit)
    module_lines = [
        f'module "{module_name}" {{',
        f'  source = "{source_url}"',
        "",
    ]
    for name in inputs_to_emit:
        spacing = " " * (longest - len(name) + 1)
        module_lines.append(f"  {name}{spacing}= var.{name}")
    module_lines.append("}")

    payload = {
        "mode": "infra",
        "cloud": "azure",
        "workflow": "azure_consumer_generation",
        "repo_target": "tf-azure-hub",
        "title": f"[AZURE] Use {module_context.get('repo_name') or module_context.get('target_module_repo_name') or 'Azure module'} module",
        "summary": f"Adds tf-azure-hub consumer usage for {module_context.get('repo_name') or module_context.get('target_module_repo_name') or 'Azure module'}.",
        "files": [
            {
                "filename": routing_context["target_consumer_filename"],
                "content": "\n".join(module_lines).rstrip() + "\n",
            },
            {
                "filename": routing_context["target_tfvars_filename"],
                "content": (routing_context.get("existing_tfvars_file_content") or "").rstrip() + "\n",
            },
        ],
    }

    parsed = parse_agent_output(json.dumps(payload))
    return finalize_agent_result_after_parse(parsed, [module_context], [routing_context])


def generate_azure_consumer_for_new_module(
    original_prompt: str,
    target_owner: str,
    target_repo: str,
    selected_ref: str = "",
    fallback_refs: list[str] | None = None,
    thread_id: str = "",
) -> dict:
    repo_metadata = github_get_repo(target_owner, target_repo)
    if not repo_metadata:
        raise RuntimeError(f"Verified Azure module repo was not found: {target_owner}/{target_repo}")

    default_branch = (repo_metadata.get("default_branch") or "").strip()
    ref_candidates = _dedupe_preserving_order([
        (selected_ref or "").strip(),
        *[(ref or "").strip() for ref in (fallback_refs or [])],
        default_branch,
        GITHUB_AZURE_BASE_BRANCH,
        "main",
    ])
    ref_candidates = [ref for ref in ref_candidates if ref]

    if not ref_candidates:
        ref_candidates = ["main"]

    module_context = []
    direct_read_errors = []

    for candidate_ref in ref_candidates:
        try:
            module_context = [
                build_grounded_azure_context_for_new_module_repo(
                    target_owner=target_owner,
                    target_repo=target_repo,
                    selected_ref=candidate_ref,
                    original_prompt=original_prompt,
                )
            ]
            break
        except Exception as context_error:
            direct_read_errors.append(f"{candidate_ref}: {context_error}")
            module_context = []

    if not module_context:
        selected_ref_for_fallback = ref_candidates[0]
        match = {
            "match_type": "new_module_created",
            "repo_name": target_repo,
            "repo_owner": target_owner,
            "repo_full_name": f"{target_owner}/{target_repo}",
            "repo_url": f"https://github.com/{target_owner}/{target_repo}",
            "description": f"Azure module repository generated for: {original_prompt}",
            "visibility": "private",
            "resource_hints": re.findall(r"[a-z0-9]+", (original_prompt or "").lower())[:12],
        }

        module_context, value_context = add_grounded_azure_context_for_match(
            match,
            selected_module_ref=selected_ref_for_fallback,
            retrieved_module_context=[],
            retrieved_value_context=[],
        )
        del value_context

    if not module_context:
        detail = "; ".join(direct_read_errors[:5])
        raise RuntimeError(
            f"Could not read Terraform files from verified Azure module repo "
            f"{target_owner}/{target_repo}. Tried refs: {', '.join(ref_candidates)}."
            + (f" Direct repo read errors: {detail}" if detail else "")
        )

    return _build_azure_consumer_payload_from_verified_context(
        original_prompt,
        module_context[0],
        thread_id=thread_id,
    )


def _state_original_prompt(*states: dict, fallback: str = "") -> str:
    for state in states:
        if isinstance(state, dict) and (state.get("original_prompt") or "").strip():
            return state.get("original_prompt").strip()
    return (fallback or "").strip()


def _state_first_value(key: str, *states: dict, fallback: str = "") -> str:
    for state in states:
        if isinstance(state, dict) and (state.get(key) or "").strip():
            return str(state.get(key)).strip()
    return (fallback or "").strip()


def build_azure_consumer_ref_candidates_from_population_state(
    population_state: dict,
    target_owner: str,
    target_repo: str,
) -> list[str]:
    """Return verified/refreshed refs to try for post-population consumer generation.

    The preferred consumer source should remain the module repo base/default branch.
    The merge commit SHA and population head branch are included as fallbacks so
    the automatic tf-azure-hub invocation step can still complete if GitHub's
    contents API has not exposed the merged base branch yet, or if the PR was
    merged into a nonstandard branch.
    """
    population_state = population_state or {}
    candidates = [
        population_state.get("base_branch"),
        population_state.get("merge_commit_sha"),
        population_state.get("head_branch"),
        population_state.get("branch"),
    ]

    try:
        default_branch = github_get_repo_default_branch(target_owner, target_repo)
    except Exception:
        default_branch = ""

    candidates.extend([
        default_branch,
        GITHUB_AZURE_BASE_BRANCH,
        "main",
    ])

    return _dedupe_preserving_order([
        str(candidate).strip()
        for candidate in candidates
        if str(candidate or "").strip()
    ])


def auto_advance_azure_missing_module_workflow(
    thread_id: str,
    ticket_number: str = "",
    ticket_link: str = "",
    ticket_title: str = "",
) -> list[str]:
    events = []
    if not thread_id:
        return events

    thread_states = refresh_thread_pr_states(thread_id)
    azure_module_state = thread_states.get("azure_module") or {}

    if _pr_status_from_state(azure_module_state) == "merged":
        target_owner, target_repo = infer_azure_module_repo_target_from_creation_state(azure_module_state)
        if target_owner and target_repo:
            azure_module_state["target_module_repo_owner"] = target_owner
            azure_module_state["target_module_repo_name"] = target_repo
            azure_module_state["target_module_repo_full_name"] = f"{target_owner}/{target_repo}"
            THREAD_PR_STATE.setdefault(thread_id, {})["azure_module"] = azure_module_state

            population_state = thread_states.get("azure_module_population") or recover_azure_module_population_state(
                thread_id,
                target_owner,
                target_repo,
            )

            if not population_state and github_repo_exists(target_owner, target_repo):
                population_state = recover_merged_azure_module_population_state_from_repo_files(
                    thread_id=thread_id,
                    owner=target_owner,
                    repo=target_repo,
                    original_prompt=azure_module_state.get("original_prompt") or "",
                )
                if population_state:
                    THREAD_PR_STATE.setdefault(thread_id, {})["azure_module_population"] = population_state
                    thread_states["azure_module_population"] = population_state
                    events.append(
                        "Detected required Azure module implementation files on the module repo default branch. "
                        "Continuing to tf-azure-hub consumer generation."
                    )

            if population_state:
                refreshed_population_state = _refresh_single_pr_state_from_github(
                    "azure_module_population",
                    population_state,
                )
                THREAD_PR_STATE.setdefault(thread_id, {})["azure_module_population"] = refreshed_population_state

                if _pr_status_from_state(refreshed_population_state) == "open":
                    population_branch = refreshed_population_state.get("branch") or ""
                    invalid_or_missing_files = get_invalid_or_missing_azure_module_population_core_files(
                        target_owner,
                        target_repo,
                        population_branch,
                    )

                    if invalid_or_missing_files:
                        original_prompt = _state_original_prompt(
                            azure_module_state,
                            refreshed_population_state,
                            fallback=ticket_title or "Create Azure module implementation files.",
                        )

                        agent_result = generate_azure_module_repo_population_with_agent(
                            conversation_id=thread_id,
                            original_prompt=original_prompt,
                            target_owner=target_owner,
                            target_repo=target_repo,
                        )
                        pr_result = commit_azure_module_repo_population_files(
                            agent_result=agent_result,
                            prompt=original_prompt,
                            thread_id=thread_id,
                            jira_ticket=_state_first_value("ticket_number", refreshed_population_state, azure_module_state, fallback=ticket_number),
                            ticket_link=_state_first_value("ticket_link", refreshed_population_state, azure_module_state, fallback=ticket_link),
                            ticket_title=_state_first_value("ticket_title", refreshed_population_state, azure_module_state, fallback=ticket_title),
                        )
                        events.append(
                            "Azure module implementation PR was missing or had invalid required files "
                            f"({', '.join(invalid_or_missing_files)}). "
                            f"Updated module repo PR: {pr_result.get('pr_url')}"
                        )

                thread_states = refresh_thread_pr_states(thread_id)
            else:
                if not github_repo_exists(target_owner, target_repo):
                    events.append(
                        f"Azure module repo definition PR is merged, waiting for GitHub repository {target_owner}/{target_repo} to become available."
                    )
                    return events

                original_prompt = _state_original_prompt(
                    azure_module_state,
                    fallback=ticket_title or "Create Azure module implementation files.",
                )
                agent_result = generate_azure_module_repo_population_with_agent(
                    conversation_id=thread_id,
                    original_prompt=original_prompt,
                    target_owner=target_owner,
                    target_repo=target_repo,
                )
                pr_result = commit_azure_module_repo_population_files(
                    agent_result=agent_result,
                    prompt=original_prompt,
                    thread_id=thread_id,
                    jira_ticket=_state_first_value("ticket_number", azure_module_state, fallback=ticket_number),
                    ticket_link=_state_first_value("ticket_link", azure_module_state, fallback=ticket_link),
                    ticket_title=_state_first_value("ticket_title", azure_module_state, fallback=ticket_title),
                )
                events.append(
                    "Azure module repo definition PR is merged. "
                    f"Created module implementation PR: {pr_result.get('pr_url')}"
                )
                thread_states = refresh_thread_pr_states(thread_id)

    population_state = thread_states.get("azure_module_population") or {}
    if _pr_status_from_state(population_state) == "merged":
        target_owner, target_repo = _state_repo_owner_name("azure_module_population", population_state)
        if not target_owner or not target_repo:
            target_owner, target_repo = infer_azure_module_repo_target_from_creation_state(azure_module_state)

        consumer_state = thread_states.get("azure_consumer")
        if consumer_state:
            refreshed_consumer_state = _refresh_single_pr_state_from_github(
                "azure_consumer",
                consumer_state,
            )
            THREAD_PR_STATE.setdefault(thread_id, {})["azure_consumer"] = refreshed_consumer_state
            consumer_state = refreshed_consumer_state

        if not _consumer_state_blocks_auto_creation(
            consumer_state,
            target_owner=target_owner,
            target_repo=target_repo,
        ):
            if target_owner and target_repo:
                ref_candidates = build_azure_consumer_ref_candidates_from_population_state(
                    population_state,
                    target_owner,
                    target_repo,
                )
                selected_ref = ref_candidates[0] if ref_candidates else "main"
                original_prompt = _state_original_prompt(
                    population_state,
                    azure_module_state,
                    fallback=ticket_title or "Create Azure consumer module usage.",
                )
                agent_result = generate_azure_consumer_for_new_module(
                    original_prompt=original_prompt,
                    target_owner=target_owner,
                    target_repo=target_repo,
                    selected_ref=selected_ref,
                    fallback_refs=ref_candidates[1:],
                    thread_id=thread_id,
                )
                pr_result = commit_terraform_files_to_repo(
                    agent_result=agent_result,
                    prompt=original_prompt,
                    thread_id=thread_id,
                    jira_ticket=_state_first_value("ticket_number", population_state, azure_module_state, fallback=ticket_number),
                    ticket_link=_state_first_value("ticket_link", population_state, azure_module_state, fallback=ticket_link),
                    ticket_title=_state_first_value("ticket_title", population_state, azure_module_state, fallback=ticket_title),
                )
                events.append(
                    "Azure module implementation PR is merged. "
                    f"Created tf-azure-hub consumer PR: {pr_result.get('pr_url')}"
                )
                refresh_thread_pr_states(thread_id)
            else:
                events.append(
                    "Azure module implementation PR is merged, but the target module repo could not be inferred for tf-azure-hub consumer generation."
                )

    return events


def build_thread_prs_payload(thread_id: str, auto_advance: bool = True) -> dict:
    if thread_id and auto_advance and thread_id not in THREAD_AUTO_ADVANCE_IN_PROGRESS:
        THREAD_AUTO_ADVANCE_IN_PROGRESS.add(thread_id)
        try:
            current_states = refresh_thread_pr_states(thread_id)
            azure_module_state = current_states.get("azure_module") or {}
            population_state = current_states.get("azure_module_population") or {}

            should_auto_advance = (
                _pr_status_from_state(azure_module_state) == "merged"
                or _pr_status_from_state(population_state) == "merged"
            )

            if should_auto_advance:
                auto_advance_azure_missing_module_workflow(
                    thread_id=thread_id,
                    ticket_number=_state_first_value("ticket_number", population_state, azure_module_state),
                    ticket_link=_state_first_value("ticket_link", population_state, azure_module_state),
                    ticket_title=_state_first_value("ticket_title", population_state, azure_module_state),
                )
        except Exception as auto_error:
            print(f"Azure auto-advance skipped while building thread PR payload for {thread_id}: {auto_error}")
        finally:
            THREAD_AUTO_ADVANCE_IN_PROGRESS.discard(thread_id)

    thread_state = refresh_thread_pr_states(thread_id) if thread_id else {}

    payload = {}
    for bucket_name, state in thread_state.items():
        if bucket_name not in ("aws", "azure_module", "azure_consumer", "azure_module_population"):
            continue
        if not isinstance(state, dict):
            continue

        refreshed = _refresh_single_pr_state_from_github(bucket_name, state)
        payload[bucket_name] = {
            "stage": refreshed.get("stage") or _stage_label_for_state_bucket(bucket_name),
            "status": refreshed.get("status") or _pr_status_from_state(refreshed),
            "pr_number": refreshed.get("pr_number"),
            "pr_url": refreshed.get("pr_url"),
            "pr_title": refreshed.get("pr_title"),
            "branch": refreshed.get("branch"),
            "folder": refreshed.get("folder"),
            "cloud": refreshed.get("cloud"),
            "repo_target": refreshed.get("repo_target"),
            "repo_owner": refreshed.get("repo_owner"),
            "repo_name": refreshed.get("repo_name"),
            "repo_full_name": refreshed.get("repo_full_name"),
            "latest_pr_state": refreshed.get("latest_pr_state"),
            "latest_pr_merged": bool(refreshed.get("latest_pr_merged")),
            "merged": bool(refreshed.get("merged") or refreshed.get("latest_pr_merged")),
            "merged_at": refreshed.get("merged_at"),
            "closed_at": refreshed.get("closed_at"),
            "has_open_pr": bool(refreshed.get("has_open_pr")),
            "target_module_repo_full_name": refreshed.get("target_module_repo_full_name"),
            "target_module_repo_name": refreshed.get("target_module_repo_name"),
            "status_refresh_error": refreshed.get("status_refresh_error"),
        }

    if "azure_consumer" in payload:
        payload["azure"] = payload["azure_consumer"]
    elif "azure_module_population" in payload:
        payload["azure"] = payload["azure_module_population"]
    elif "azure_module" in payload:
        payload["azure"] = payload["azure_module"]

    if "azure_module_population" in payload:
        payload["azure_population"] = payload["azure_module_population"]

    return payload


def handle_refresh_pr_status_request(
    conversation_id: str,
    conversation_label: str,
    ticket_number: str,
    ticket_link: str,
    ticket_title: str,
):
    if not conversation_id:
        return {
            "ok": False,
            "mode": "chat",
            "reply": "No active conversation was found for this JIRA ticket.",
            "ticket_link": ticket_link,
            "ticket_number": ticket_number,
            "ticket_title": ticket_title,
        }, 400

    events = []
    try:
        events.extend(auto_advance_azure_missing_module_workflow(
            thread_id=conversation_id,
            ticket_number=ticket_number,
            ticket_link=ticket_link,
            ticket_title=ticket_title,
        ))
    except Exception as automation_error:
        events.append(f"Azure PR automation paused: {automation_error}")

    return {
        "ok": True,
        "mode": "chat",
        "reply": "PR status refreshed.",
        "thread_id": conversation_id,
        "conversation_label": conversation_label,
        "jira_ticket": ticket_number,
        "ticket_number": ticket_number,
        "ticket_link": ticket_link,
        "ticket_title": ticket_title,
        "thread_prs": build_thread_prs_payload(conversation_id, auto_advance=False),
        "events": events,
    }, 200

def build_router_response_message(router_decision):
    if router_decision.workflow == "clarification_required":
        if not router_decision.cloud:
            return "Please specify which cloud to use: AWS or Azure."
        return "Please provide the target environment or enough deployment context to continue."
    return router_decision.reason


def normalize_router_decision(prompt, requested_mode, requested_cloud, recovered_state, thread_id=None):
    """Normalize only explicit backend workflow state; never classify user intent.

    Ordinary Teams messages are intentionally returned as ``chat`` here so
    they are sent to the Foundry agent first. The terminal Teams wrapper sets
    requested_mode="infra" only after Foundry classifies the current user
    message as infrastructure, or when a deterministic protocol continuation
    (branch/Jira/target selection) is already in progress.
    """
    del recovered_state, thread_id
    prompt_text = (prompt or "").strip()
    inferred_cloud = safe_normalize_cloud(requested_cloud) or infer_cloud_from_prompt(prompt_text)
    if (requested_mode or "").strip().lower() == "infra":
        return NormalizedRouterDecision(
            request_type="infra",
            cloud=inferred_cloud,
            workflow="standard",
            reason="Infrastructure mode supplied by Foundry classification or deterministic workflow continuation.",
        )
    return NormalizedRouterDecision(
        request_type="chat",
        cloud=inferred_cloud,
        workflow="standard",
        reason="Ordinary user intent is delegated to the Foundry agent.",
    )


def get_pending_infra_change_by_id(pending_change_id: str):
    return PENDING_INFRA_CHANGES.get((pending_change_id or "").strip())


def clear_pending_infra_change_by_id(pending_change_id: str):
    return PENDING_INFRA_CHANGES.pop((pending_change_id or "").strip(), None)


def _module_variable_value_key(thread_id: str, ticket_number: str = "") -> str:
    return f"{str(thread_id or '').strip()}::{str(ticket_number or '').strip().upper()}"


def store_pending_module_variable_value_selection(
    thread_id: str,
    ticket_number: str,
    original_prompt: str,
    agent_result: dict,
    variable_form: dict,
    workflow: str,
    cloud: str,
    ticket_link: str = "",
    ticket_title: str = "",
):
    key = _module_variable_value_key(thread_id, ticket_number)
    PENDING_MODULE_VARIABLE_VALUE_SELECTIONS[key] = {
        "thread_id": thread_id,
        "ticket_number": (ticket_number or "").strip().upper(),
        "original_prompt": original_prompt or "",
        "agent_result": agent_result or {},
        "variable_form": variable_form or {},
        "workflow": workflow or "",
        "cloud": cloud or "",
        "ticket_link": ticket_link or "",
        "ticket_title": ticket_title or "",
    }
    return key


def get_pending_module_variable_value_selection(thread_id: str, ticket_number: str = "") -> dict:
    return PENDING_MODULE_VARIABLE_VALUE_SELECTIONS.get(
        _module_variable_value_key(thread_id, ticket_number),
        {},
    )


def clear_pending_module_variable_value_selection(thread_id: str, ticket_number: str = ""):
    PENDING_MODULE_VARIABLE_VALUE_SELECTIONS.pop(
        _module_variable_value_key(thread_id, ticket_number),
        None,
    )


def _extract_module_variable_assignments_from_text(text: str) -> dict[str, str]:
    assignments: dict[str, str] = {}
    for match in re.finditer(r'(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$', text or ""):
        name = (match.group(1) or "").strip()
        value = (match.group(2) or "").strip().rstrip(",")
        if name and value:
            assignments[name] = value
    return assignments


def _module_variable_values_to_prompt_suffix(values: dict[str, str]) -> str:
    lines = []
    for name, value in (values or {}).items():
        name = (name or "").strip()
        value = (value or "").strip()
        if not name or not value:
            continue
        lines.append(f"{name} = {value}")
    if not lines:
        return ""
    return "\n\nBackend-approved module variable values from user:\n" + "\n".join(lines) + "\n"


def _module_variable_field_description(block: str, name: str) -> str:
    description = _variable_attr_value(block, "description")
    if description:
        return description.strip().strip('"')
    return name


def build_module_variable_value_form(agent_result: dict, issues: list[str] | None = None) -> dict:
    workflow = (agent_result.get("workflow") or "").strip()
    cloud = safe_normalize_cloud(agent_result.get("cloud") or "") or agent_result.get("cloud") or ""
    fields = []
    seen = set()

    for file_data in agent_result.get("files") or []:
        if not isinstance(file_data, dict):
            continue
        filename = (file_data.get("filename") or "").replace("\\", "/")
        content = file_data.get("content") or ""
        if workflow == "aws_module_creation" and not re.search(r'/terraform/modules/.+/(?:vars|variables)\.tf$', "/" + filename):
            continue
        if workflow == "azure_module_repo_population" and filename != "variables.tf":
            continue

        for item in _iter_variable_blocks_with_names(content):
            name = item.get("name") or ""
            if not name or name in seen:
                continue
            block = item.get("block") or ""
            type_expr = _variable_type_from_block(block) or _infer_variable_type_from_name_and_default(name, block)
            normalized_type = _normalize_type_expr(type_expr)
            default_present = _variable_attr_present(block, "default")
            description = _module_variable_field_description(block, name)
            is_sensitive = _variable_name_is_private_or_sensitive(name)

            # The backend supplies safe bool/number/map/list/set/object defaults automatically.
            # The widget is for string/private values that cannot be invented.
            if normalized_type != "string":
                continue
            if default_present and not is_sensitive:
                continue

            seen.add(name)
            fields.append({
                "name": name,
                "type": type_expr or "string",
                "description": description,
                "filename": filename,
                "sensitive": bool(is_sensitive),
                "required": True,
                "placeholder": "Enter approved value or reference",
            })

    return {
        "title": "Module variable values required",
        "description": "Provide approved values or references before Terrabot creates the PR preview.",
        "cloud": cloud,
        "workflow": workflow,
        "issues": list(issues or agent_result.get("_module_variable_issues") or []),
        "fields": fields,
    }


def _module_variable_form_response_payload(
    conversation_id: str,
    conversation_label: str,
    ticket_number: str,
    ticket_link: str,
    ticket_title: str,
    variable_form: dict,
    cloud: str,
    workflow: str,
) -> dict:
    return {
        "ok": False,
        "mode": "module_variable_values",
        "reply": "Terrabot needs approved module variable values before creating the PR preview.",
        "thread_id": conversation_id,
        "conversation_label": conversation_label,
        "jira_ticket": ticket_number,
        "ticket_number": ticket_number,
        "ticket_link": ticket_link,
        "ticket_title": ticket_title,
        "cloud": cloud,
        "workflow": workflow,
        "variable_form": variable_form,
        "missing_variables": variable_form.get("fields") or [],
        "thread_prs": build_thread_prs_payload(conversation_id),
    }


def _normalize_agent_module_variable_files_with_values(agent_result: dict, values: dict[str, str], original_prompt: str = "") -> tuple[dict, list[str]]:
    updated = dict(agent_result or {})
    user_prompt = (original_prompt or updated.get("user_prompt") or updated.get("summary") or "") + _module_variable_values_to_prompt_suffix(values)
    files, issues = normalize_generated_module_variable_files(
        updated.get("files") or [],
        updated.get("workflow") or "",
        user_prompt=user_prompt,
    )
    updated["files"] = files
    updated["user_prompt"] = user_prompt
    updated.pop("_module_variable_values_required", None)
    updated.pop("_module_variable_issues", None)
    return updated, issues


def _hcl_placeholder_for_module_variable(variable_name: str, sensitive: bool = False) -> str:
    """Return a non-real placeholder HCL string for branch-first Teams flows."""
    safe_name = re.sub(r"[^A-Za-z0-9_]+", "_", (variable_name or "value").strip()).strip("_").upper()
    if not safe_name:
        safe_name = "VALUE"
    prefix = "TERRABOT_SECRET_PLACEHOLDER" if sensitive else "TERRABOT_PLACEHOLDER"
    return json.dumps(f"{prefix}_{safe_name}")


def _module_placeholder_values_from_agent_result(agent_result: dict) -> dict[str, str]:
    """Build deterministic placeholder values for module variables that block Teams branch creation.

    Teams should create a review branch first and defer real values to code review/Jira/PR
    discussion. This function supplies visibly fake HCL string defaults only for variables
    that the backend already identified as requiring approved values.
    """
    values: dict[str, str] = {}
    form = build_module_variable_value_form(
        agent_result,
        issues=agent_result.get("_module_variable_issues") or [],
    )
    for field in form.get("fields") or []:
        if not isinstance(field, dict):
            continue
        name = str(field.get("name") or "").strip()
        if not name:
            continue
        values[name] = _hcl_placeholder_for_module_variable(
            name,
            sensitive=bool(field.get("sensitive")),
        )
    return values


def _apply_module_placeholder_values_for_teams(agent_result: dict, original_prompt: str) -> tuple[dict, list[str], dict[str, str]]:
    """Normalize module files with placeholder values so Teams can push a branch before PR."""
    placeholder_values = _module_placeholder_values_from_agent_result(agent_result)
    if not placeholder_values:
        return agent_result, list(agent_result.get("_module_variable_issues") or []), {}
    updated, issues = _normalize_agent_module_variable_files_with_values(
        agent_result,
        placeholder_values,
        original_prompt=original_prompt,
    )
    updated["terrabot_placeholder_values_used"] = True
    updated["terrabot_placeholder_variable_names"] = sorted(placeholder_values.keys())
    summary = str(updated.get("summary") or "").strip()
    note = (
        "Placeholder module variable defaults were inserted so the Teams flow can "
        "create a GitHub branch for review before opening a PR. Replace these "
        "TERRABOT_PLACEHOLDER values with approved environment values before merge."
    )
    updated["summary"] = f"{summary}\n\n{note}".strip() if summary else note
    return updated, issues, placeholder_values


def _start_module_variable_value_selection_response(
    conversation_id: str,
    conversation_label: str,
    ticket_number: str,
    ticket_link: str,
    ticket_title: str,
    effective_prompt: str,
    agent_result: dict,
    issues: list[str] | None = None,
):
    variable_form = build_module_variable_value_form(agent_result, issues=issues)
    if not variable_form.get("fields"):
        # Fallback: expose issue text as fields if parsing failed, but keep the
        # flow interactive instead of returning a terminal red error.
        variable_form["fields"] = [
            {
                "name": re.sub(r"[^A-Za-z0-9_]+", "_", str(issue or "value")).strip("_")[:64] or "value",
                "type": "string",
                "description": str(issue or "Missing approved value"),
                "required": True,
                "sensitive": True,
                "placeholder": "Enter approved value or reference",
            }
            for issue in (issues or agent_result.get("_module_variable_issues") or ["missing_value"])
        ]

    store_pending_module_variable_value_selection(
        thread_id=conversation_id,
        ticket_number=ticket_number,
        original_prompt=effective_prompt,
        agent_result=agent_result,
        variable_form=variable_form,
        workflow=agent_result.get("workflow") or "",
        cloud=agent_result.get("cloud") or "",
        ticket_link=ticket_link,
        ticket_title=ticket_title,
    )
    return _module_variable_form_response_payload(
        conversation_id,
        conversation_label,
        ticket_number,
        ticket_link,
        ticket_title,
        variable_form,
        agent_result.get("cloud") or "",
        agent_result.get("workflow") or "",
    ), 400


def handle_submit_module_variable_values(
    data: dict,
    conversation_id: str,
    conversation_label: str,
    ticket_number: str,
    ticket_link: str,
    ticket_title: str,
):
    if not conversation_id:
        return {
            "ok": False,
            "mode": "chat",
            "reply": "No active conversation was found for this JIRA ticket.",
            "ticket_link": ticket_link,
            "ticket_number": ticket_number,
            "ticket_title": ticket_title,
        }, 400

    pending = get_pending_module_variable_value_selection(conversation_id, ticket_number)
    if not pending:
        return {
            "ok": False,
            "mode": "chat",
            "reply": "No pending module variable value form was found for this thread.",
            "thread_id": conversation_id,
            "conversation_label": conversation_label,
            "jira_ticket": ticket_number,
            "ticket_number": ticket_number,
            "ticket_link": ticket_link,
            "ticket_title": ticket_title,
        }, 400

    values = data.get("variable_values") or {}
    if not isinstance(values, dict):
        values = {}
    values = {str(k).strip(): str(v).strip() for k, v in values.items() if str(k).strip() and str(v).strip()}
    values.update(_extract_module_variable_assignments_from_text(data.get("prompt") or ""))

    if not values:
        return {
            "ok": False,
            "mode": "module_variable_values",
            "reply": "Please provide values for the required module variables.",
            "thread_id": conversation_id,
            "conversation_label": conversation_label,
            "jira_ticket": ticket_number,
            "ticket_number": ticket_number,
            "ticket_link": ticket_link,
            "ticket_title": ticket_title,
            "cloud": pending.get("cloud"),
            "workflow": pending.get("workflow"),
            "variable_form": pending.get("variable_form"),
            "missing_variables": (pending.get("variable_form") or {}).get("fields") or [],
            "thread_prs": build_thread_prs_payload(conversation_id),
        }, 400

    agent_result = dict(pending.get("agent_result") or {})
    agent_result, issues = _normalize_agent_module_variable_files_with_values(
        agent_result,
        values,
        original_prompt=pending.get("original_prompt") or "",
    )
    if issues:
        variable_form = build_module_variable_value_form(agent_result, issues=issues)
        store_pending_module_variable_value_selection(
            thread_id=conversation_id,
            ticket_number=ticket_number,
            original_prompt=pending.get("original_prompt") or "",
            agent_result=agent_result,
            variable_form=variable_form,
            workflow=pending.get("workflow") or agent_result.get("workflow") or "",
            cloud=pending.get("cloud") or agent_result.get("cloud") or "",
            ticket_link=ticket_link,
            ticket_title=ticket_title,
        )
        return _module_variable_form_response_payload(
            conversation_id,
            conversation_label,
            ticket_number,
            ticket_link,
            ticket_title,
            variable_form,
            pending.get("cloud") or agent_result.get("cloud") or "",
            pending.get("workflow") or agent_result.get("workflow") or "",
        ), 400

    agent_result["repo_target"] = normalize_repo_target(
        agent_result.get("cloud") or pending.get("cloud") or "aws",
        repo_target=agent_result.get("repo_target"),
        workflow=agent_result.get("workflow") or pending.get("workflow"),
    )
    agent_result["state_bucket"] = state_bucket_for_target(
        agent_result.get("cloud") or pending.get("cloud") or "aws",
        agent_result.get("repo_target"),
        agent_result.get("workflow") or pending.get("workflow"),
    )

    original_prompt = (pending.get("original_prompt") or "").strip() + _module_variable_values_to_prompt_suffix(values)
    pending_key = store_pending_infra_change(
        conversation_id,
        ticket_number,
        original_prompt.strip(),
        agent_result,
        ticket_link=ticket_link,
        ticket_title=ticket_title,
    )
    clear_pending_module_variable_value_selection(conversation_id, ticket_number)
    clear_pending_cloud_clarification(conversation_id, ticket_number)

    return {
        "ok": True,
        "mode": "infra_preview",
        "reply": "Module variable values were applied. Terraform changes are ready. Do you want to commit these changes to the PR?",
        "thread_id": conversation_id,
        "conversation_label": conversation_label,
        "jira_ticket": ticket_number,
        "ticket_number": ticket_number,
        "ticket_link": ticket_link,
        "ticket_title": ticket_title,
        "pending_change_id": pending_key,
        "cloud": agent_result.get("cloud"),
        "workflow": agent_result.get("workflow"),
        "repo_target": agent_result.get("repo_target"),
        "state_bucket": agent_result.get("state_bucket"),
        "title": agent_result.get("title"),
        "summary": agent_result.get("summary"),
        "files": [f.get("filename") for f in agent_result.get("files") or [] if isinstance(f, dict)],
        "thread_prs": build_thread_prs_payload(conversation_id),
    }, 200


