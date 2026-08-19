from __future__ import annotations
import json
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

MAX_FILES = 120
MAX_FILE_BYTES = 64 * 1024


def _safe_relpath(value: str) -> str:
    cleaned = str(value or "").replace("\\", "/").lstrip("/")
    parts = [p for p in cleaned.split("/") if p and p not in {".", ".."}]
    return "/".join(parts)


def _materialize_workspace(files: List[Dict[str, Any]], workspace_name: str = "workspace") -> str:
    root = Path(tempfile.mkdtemp(prefix="terrabot-gen-")) / _safe_relpath(workspace_name or "workspace")
    root.mkdir(parents=True, exist_ok=True)
    for item in files[:MAX_FILES]:
        rel = _safe_relpath(item.get("path") or "")
        if not rel:
            continue
        content = str(item.get("content") or "")
        if len(content.encode("utf-8")) > MAX_FILE_BYTES:
            continue
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return str(root)



def _attach_shared_repository_context(
    context_pack: Dict[str, Any],
    prompt: str,
    repository: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Attach repo-scoped durable context for hosted VS Code requests.

    The extension supplies Git remote identity and current commit. If that
    metadata is unavailable (CLI/direct context_pack callers), generation
    continues unchanged rather than guessing repository identity.
    """
    repo_info = repository or {}
    owner = str(repo_info.get("owner") or "").strip()
    repo = str(repo_info.get("repo") or "").strip().removesuffix(".git")
    current_commit = str(repo_info.get("commit") or repo_info.get("commit_sha") or "").strip()
    if not owner or not repo:
        return context_pack
    try:
        from shared_code import repository_context as shared_repository_context

        result = shared_repository_context.search_repository_context(
            repo_owner=owner,
            repo_name=repo,
            query=prompt,
            current_commit_sha=current_commit,
            top_k=8,
        )
        block = shared_repository_context.format_repository_context_for_agent(result)
        enriched = dict(context_pack or {})
        if block:
            enriched["shared_repository_context"] = block
            enriched["shared_repository_context_metadata"] = {
                "repository": f"{owner}/{repo}",
                "current_commit_sha": current_commit,
                "result_count": len(result.get("results") or []),
                "stale_count": int(result.get("stale_count") or 0),
                "conflicted_count": int(result.get("conflicted_count") or 0),
            }
        enriched["repository_context_tools"] = (
            shared_repository_context.FOUNDRY_REPOSITORY_CONTEXT_TOOL_SCHEMAS
        )
        return enriched
    except Exception:
        return context_pack


def _build_agent_prompt(prompt: str, context_pack: Dict[str, Any], follow_up: bool = False) -> str:
    if follow_up:
        # Light envelope for follow-up turns in an existing Foundry
        # conversation: the full context_pack from earlier turns is already
        # in the conversation history — don't drown a one-word answer in it.
        return json.dumps({
            "task": "Follow-up in the same repo-aware Terraform session",
            "user_request": prompt,
            "requirements": [
                "This is a follow-up turn: use the workflow model, candidates, questions, and values already established earlier in this conversation.",
                "Do not re-ask questions the user already answered.",
                "The context_pack provided in earlier turns still applies; the fresh context_pack in this turn (if any) wins for file contents.",
                "Same output contract as before: JSON with summary, analysis, source_paths_used, files, user_fillable, questions, validation_commands.",
                "For a new infrastructure request, do not assume it belongs to an earlier PR. Generate workspace edits only; PR/branch decisions are handled by the VS Code client after explicit user instruction.",
                "For an existing Terraform flag/value change, search the fresh context_pack across all files for the exact root assignment and modify the file that already owns that assignment. Never route to the currently open or most recently edited file merely because it is active.",
                "Example: create_cloudamqp must be changed in the existing file that contains the root create_cloudamqp assignment (often tier.tfvars), not in hub.tfvars unless hub.tfvars actually owns that assignment.",
                "When the user explicitly names a repo-relative .tf or .tfvars file, that file is authoritative if it exists in the fresh workspace context. Do not silently redirect the request to a different file.",
                "Do not treat related flags as interchangeable. For patch management, create_patch_management controls creation; enable_pre_maintenance_event_grid and enable_post_maintenance_event_grid are separate event-grid integration flags and do not prove patch management is enabled.",
                "If the user asks to create or enable patch management and create_patch_management is false, change it to true. Do not report the request as already configured because other patch-related flags are true.",
                "VS CODE AZURE CREATION: for a request to create a new Azure resource/app instance, discover the existing file that already contains the closest matching sibling resources and place the new resource there. File placement is repository-answerable and must never be asked when a matching sibling file exists in the fresh context_pack.",
                "VS CODE AZURE CREATION: reuse the exact module source/version, wiring style, ingress/public-access pattern, networking pattern, naming pattern, and input ordering from the nearest matching sibling resource. Do not ask permission to reuse the demonstrated module or ask the user to choose public/private ingress when sibling code answers it.",
                "VS CODE AZURE CREATION: when the sibling pattern is object-backed, create a dedicated object-root variable for the new resource, append its variable declaration to the existing variables.tf that declares sibling objects, and add a concrete assignment to the target environment's hub.tfvars when that file exists. Never wire the new resource to an existing sibling's object variable.",
                "VS CODE AZURE CREATION: missing non-sensitive configuration values are not questions. Resolve them from sibling resources/defaults first; if still unknown, emit __FILL__<input_name>__ tokens and user_fillable entries and continue generation. Questions are reserved for genuinely blocking ambiguity or sensitive values with no repository-safe reference pattern.",
                "VS CODE AWS CLONE/MIRROR CREATION: when the user explicitly asks to create a NEW AWS module/resource by mirroring, cloning, copying, or basing it on an existing module (for example Redshift auditdb), treat the named existing module as a READ-ONLY TEMPLATE. Generate a NEW module implementation directory plus the target-environment consumer invocation in the SAME response, even though the template module already exists.",
                "VS CODE AWS CLONE/MIRROR CREATION: include all Terraform implementation files demonstrated by the template module (for example main.tf, vars.tf/variables.tf, outputs.tf and any additional .tf implementation files). Do not append instance-specific variables or resources into the template module directory.",
                "VS CODE AWS CLONE/MIRROR CREATION: mirror the template consumer's input set and wiring. Source values from the current repository first; when a required NON-SENSITIVE value cannot be grounded from repository code/defaults, use a syntactically valid __FILL__<input_name>__ placeholder and add matching user_fillable metadata instead of asking the user.",
                "VS CODE AWS CLONE/MIRROR CREATION: insert_into_block is ONLY for adding attributes inside a top-level block that already exists in the live file. A new module block, variable block, resource block, output block, or locals block must be returned as create/modify content, never as insert_into_block targeting a block that does not exist.",
            ],
            "context_pack": context_pack,
        }, indent=2)

    return json.dumps({
        "task": "Repo-aware Terraform infrastructure generation",
        "user_request": prompt,
        "requirements": [
            "First classify the user_request: casual chat, repository question, or infrastructure change.",
            "For casual chat and repository questions: respond with the JSON envelope where files=[] and summary contains your natural, conversational reply. Write summary as a friendly message to the user, never as a system report.",
            "For infrastructure changes: use the context_pack as the sole source of truth for repo conventions, tfvars, modules, and workflow.",
            "For existing Terraform flags and values, route by exact repository ownership: inspect every context file for the root assignment and modify the file where that assignment already exists. Open-editor recency is not evidence of ownership.",
            "For requests such as enable/disable CloudAMQP, find the existing root create_cloudamqp assignment and update that exact file. Prefer exact assignment evidence over generic environment filenames; do not choose hub.tfvars merely because it was edited in the previous turn.",
            "When the user explicitly names a repo-relative .tf or .tfvars file, treat that file as binding if it exists in context. Inspect and modify that file rather than substituting a different file based on a related convention.",
            "Do not conflate related feature flags. create_patch_management is the patch-management creation switch; enable_pre_maintenance_event_grid and enable_post_maintenance_event_grid are only event-grid integration switches.",
            "For create/enable patch management, set create_patch_management = true in the explicit file or exact assignment owner. For disable patch management, set it to false. Other true patch-related flags do not make this request a no-op.",
            "Do not attach generated workspace changes to any pull request. Return file edits only. Branch creation, commit, push, same-PR, and separate-PR decisions are handled by the VS Code client after explicit user confirmation.",
            "Return JSON only — no markdown fences, no preamble.",
            "Top-level keys: summary (str), analysis (str), source_paths_used (list), files (list), user_fillable (list), questions (list), validation_commands (list).",
            "analysis is your visible reasoning shown to the user: what you inspected, which conventions you found, which questions you answered yourself from evidence, and your decisions. 3-10 short lines with evidence paths.",
            "Before asking any question, try to answer it yourself from the context_pack (repo conventions, secret patterns, file placement). Only ask what the repository cannot answer.",
            "VS CODE NEW AZURE RESOURCE CREATION — NO REPO-ANSWERABLE QUESTIONS: find the file in the target environment/root that already contains the closest matching resource family and add the new sibling there. Never ask which file should host it when comparable resource code exists in context_pack.",
            "For Azure Container Apps/ACA specifically, search for existing ACA/container-app module/resource blocks and use their owning file (for example an aca*.tf file only when the evidence proves it). Copy the nearest sibling block's exact module source/version and wiring; never ask whether to reuse the existing ACA module.",
            "Infer ingress/public access, VNet/private networking, service-plan/workload-profile style, common environment variables, tags, location/resource-group wiring, and other structural settings from the nearest matching sibling in the same environment first, then another environment. These are Bucket-A repository decisions, not user questions.",
            "For every new Azure resource instance, give it an independent configuration root. If sibling instances are object-backed through var.<object>.*, create a NEW dedicated object-root variable for the new instance, append the declaration to the existing variables.tf that declares sibling objects, and add the new object assignment to the target environment's hub.tfvars when present (otherwise the exact environment values file demonstrated by siblings). Never point the new instance at a pre-existing sibling's object variable.",
            "For an object-backed Azure creation, return the complete write-set in one response: (1) matching resource-family definition file with the new sibling, (2) existing variables.tf with the dedicated object variable declaration, and (3) target-environment hub.tfvars/value file with the new object assignment. Do not split these across turns.",
            "For any missing non-sensitive user configuration or variable value, do NOT ask. First copy a grounded sibling/default value; if no grounded value exists, use a syntactically valid __FILL__<input_name>__ token and add user_fillable metadata. Continue generating the files. Only genuinely blocking ambiguity, unavailable required external module schema, or a sensitive value with no safe repo reference pattern may remain in questions[].",
            "VS CODE AWS NEW-MODULE CLONE/MIRROR OVERRIDE: if the user's own request says to mirror/clone/copy an existing AWS module or create a new module based on an existing implementation, the existing module is a TEMPLATE, not the consumer target. Generate BOTH (a) a new module implementation directory under the repository's demonstrated modules root and (b) the target environment consumer invocation in the SAME files[] response.",
            "For that clone/mirror workflow, copy the complete .tf file layout of the reference module from context_pack evidence, including any additional implementation .tf files beyond main/variables/outputs. Keep the reference module untouched. Do not create instance-specific variable declarations inside the reference module.",
            "For that clone/mirror workflow, mirror the reference consumer's complete input list and repository wiring. Resolve values from same-environment code, other consumers, and module defaults first. If a required NON-SENSITIVE value still cannot be sourced, emit __FILL__<input_name>__ and a matching user_fillable entry; do not block generation just to ask for ordinary values.",
            "insert_into_block may only target a top-level block that already exists in the scanned live file. When adding a brand-new module/variable/resource/output/locals block, use create for a new path or modify with the existing file plus the new block. Never use insert_into_block for a block that does not exist yet.",
            "Non-sensitive user-preference values (names, sizes, admin usernames) must not block generation: emit __FILL__<input_name>__ tokens and list each in user_fillable with file, input, and hint.",
            "Each files[] entry must include: path (str), operation (str: create|modify|delete|fill|insert_into_block), content (str for create/modify only).",
            "For adding lines inside an existing block (e.g. enabling a feature flag in an existing module block), use operation insert_into_block with block, lines, and optional anchor — never return the whole file.",
            "CloudAMQP/RabbitMQ special case: if the target environment already has create_cloudamqp = true and the user asks for another/second instance, do not add a standalone module or only variables. Return one atomic multi-file refactor across the EXISTING files that implement the pattern: the vena_datacentre variables/shim file, the actual existing CloudAMQP implementation module files, any existing outputs files that expose CloudAMQP values, and the target environment consumer main.tf as insert_into_block with cloudamqp_instances containing default plus the second entry.",
            "Do not assume modules/vena_datacentre/cloudamqp.tf exists. Discover the real CloudAMQP implementation paths from context_pack evidence/repo_profile. If modules/cloudamqp exists, use modules/cloudamqp variables/main/outputs as the source of required inputs and defaults; only mention or modify paths that exist in the scanned repo.",
            "For that CloudAMQP second-instance refactor, preserve the existing default values from the target environment; prefill plan/version for the second instance from the existing instance or modules/cloudamqp defaults; use __FILL__second_instance_key__ and __FILL__second_cloudamqp_subnet_cidr__ for only the new distinct values; include user_fillable entries.",
            "In the target environment module \"vena_datacentre\" block, cloudamqp_instances must be a small consumer object only: each entry should contain cloudamqp_plan, cloudamqp_subnet_cidr, and rabbitmq_version unless the scanned vena_datacentre variables prove more fields are required. Never put hub_name, aws_vpc_id, aws_subnet_ids, allowed_subnets, aws_source_arns, datadog_api_key, or module.vena_datacentre.* self-references in that consumer block; those belong inside the module implementation/shim.",
            "For insert_into_block lines, preserve nested indentation in the lines array. Do not send an entire main.tf as content for a consumer block addition.",
            "Never satisfy a second-instance bool-flag request with a single variables.tf change. That is incomplete and must be rejected by your own pre-return check.",
            "paths in files[] must be repo-relative, never absolute.",
            "Do not invent secrets or credentials. Add them to questions[] instead.",
        ],
        "context_pack": context_pack,
    }, indent=2)


def _parse_reply(reply: str) -> Optional[Dict[str, Any]]:
    """Extract and parse the outermost JSON object from the agent reply."""
    clean = re.sub(r'```[a-z]*\n?', '', reply).strip()
    start = clean.find('{')
    end = clean.rfind('}')
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(clean[start:end + 1])
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _existing_files_map(files: List[Dict[str, Any]]) -> Dict[str, str]:
    """path -> content for the user's scanned workspace files."""
    out: Dict[str, str] = {}
    for item in files or []:
        rel = _safe_relpath(item.get("path") or "")
        if rel:
            out[rel] = str(item.get("content") or "")
    return out


def _split_top_level_blocks(content: str) -> List[Tuple[str, str]]:
    """Split HCL content into (header_signature, block_text) pairs for every
    top-level block, tracking brace depth so nested blocks stay inside their
    parent. Non-block lines (comments between blocks, bare assignments) are
    grouped into pseudo-blocks keyed by their own text.

    header_signature examples:
      'module "vena_datacentre"', 'provider "aws"', 'locals',
      'resource "aws_mq_broker" "cloudamqp"'
    """
    lines = content.splitlines()
    blocks: List[Tuple[str, str]] = []
    idx = 0
    n = len(lines)
    while idx < n:
        line = lines[idx]
        stripped = line.strip()
        if not stripped:
            idx += 1
            continue
        # A top-level block opener: not indented, ends with "{"
        if (len(line) - len(line.lstrip())) == 0 and stripped.endswith("{"):
            header = " ".join(stripped[:-1].split()).strip()
            depth = 0
            start = idx
            while idx < n:
                depth += lines[idx].count("{") - lines[idx].count("}")
                idx += 1
                if depth == 0:
                    break
            blocks.append((header, "\n".join(lines[start:idx])))
            continue
        # Standalone top-level line (comment or assignment): pseudo-block.
        blocks.append((stripped, line))
        idx += 1
    return blocks


def _dedup_append_blocks(current: str, returned: str) -> Tuple[str, List[str], List[str]]:
    """Block-level dedup for the append-repair path.

    The agent sometimes echoes a regenerated near-copy of the whole file.
    Naively appending it doubles every block. Instead: split the returned
    content into top-level blocks, keep ONLY blocks whose header signature
    does not already exist in the current file, and append those.

    Returns (new_blocks_text, appended_headers, skipped_headers).
    """
    current_headers = {h for h, _ in _split_top_level_blocks(current)}
    appended: List[str] = []
    skipped: List[str] = []
    pieces: List[str] = []
    for header, text in _split_top_level_blocks(returned):
        if header in current_headers:
            skipped.append(header)
            continue
        # Also skip bare comment pseudo-blocks that duplicate existing lines.
        if header.startswith("#") and header in current:
            skipped.append(header)
            continue
        pieces.append(text)
        appended.append(header)
    return ("\n\n".join(pieces), appended, skipped)


def _find_block_span(lines: List[str], block_header: str) -> Tuple[int, int]:
    """Return (open_idx, close_idx) line indexes of a top-level HCL block whose
    opening line contains block_header (e.g. module "vena_datacentre").
    close_idx is the line holding the matching top-level closing brace.
    Returns (-1, -1) when not found or unbalanced."""
    header_lower = " ".join(block_header.lower().split())
    open_idx = -1
    for idx, line in enumerate(lines):
        normalized = " ".join(line.lower().split())
        if header_lower in normalized and line.rstrip().endswith("{") and (len(line) - len(line.lstrip())) == 0:
            open_idx = idx
            break
    if open_idx == -1:
        return -1, -1
    depth = 0
    for idx in range(open_idx, len(lines)):
        depth += lines[idx].count("{") - lines[idx].count("}")
        if depth == 0:
            return open_idx, idx
    return -1, -1


def _insert_lines_into_block(
    current: str,
    block_header: str,
    new_lines: List[str],
    anchor: str = "",
) -> Tuple[str, str]:
    """Upsert lines inside a named top-level block.

    New attribute keys are inserted. Existing direct attribute keys are updated
    in place, preserving the file and block structure. This is required for
    feature-flag requests such as changing create_cloudamqp = true to false;
    appending a second assignment would make the Terraform invalid.
    """
    lines = current.splitlines()

    def _key_of(line: str) -> str:
        match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", str(line or ""))
        return match.group(1) if match else ""

    # tfvars files commonly contain direct root-level assignments rather than
    # a named HCL block. The agent uses root/__root__ for this target. Treat it
    # as a safe top-level upsert: replace an existing assignment in place, or
    # insert a new assignment without reconstructing the file.
    normalized_target = " ".join((block_header or "").strip().lower().split())
    if normalized_target in {"root", "__root__", "file root", "top level", "top-level"}:
        direct_key_indexes: Dict[str, int] = {}
        depth = 0
        for idx, line in enumerate(lines):
            if depth == 0:
                key = _key_of(line)
                if key and key not in direct_key_indexes:
                    direct_key_indexes[key] = idx
            depth += line.count("{") - line.count("}")

        replacements: Dict[int, str] = {}
        to_insert: List[str] = []
        changed = False
        for raw in new_lines:
            raw_line = str(raw).rstrip()
            key = _key_of(raw_line)
            if key and key in direct_key_indexes:
                existing_idx = direct_key_indexes[key]
                existing_line = lines[existing_idx]
                indent = existing_line[: len(existing_line) - len(existing_line.lstrip())]
                replacement_line = indent + raw_line.lstrip()
                if replacement_line.rstrip() != existing_line.rstrip():
                    replacements[existing_idx] = replacement_line
                    changed = True
            else:
                to_insert.append(raw_line)

        for idx, replacement_line in replacements.items():
            lines[idx] = replacement_line

        if to_insert:
            insert_at = len(lines)
            if anchor:
                mode, _, needle = anchor.partition(":")
                needle = needle.strip().lower()
                mode = mode.strip().lower()
                if needle:
                    for idx, line in enumerate(lines):
                        if needle in line.lower():
                            insert_at = idx + 1 if mode == "after" else idx
                            break
            rendered = list(to_insert)
            if insert_at == len(lines) and lines and lines[-1].strip():
                rendered.insert(0, "")
            lines = lines[:insert_at] + rendered + lines[insert_at:]
            changed = True

        if not changed:
            return "", "all requested root assignments already have the requested values (nothing to change)."
        merged = "\n".join(lines)
        if current.endswith("\n") and not merged.endswith("\n"):
            merged += "\n"
        return merged, ""

    open_idx, close_idx = _find_block_span(lines, block_header)
    if open_idx == -1:
        return "", f"block '{block_header}' not found as a top-level block in the current file."

    def _key_of(line: str) -> str:
        match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", str(line or ""))
        return match.group(1) if match else ""

    # Find direct block attributes only. Nested object keys must not be treated
    # as duplicates of module arguments with the same name.
    direct_key_indexes: Dict[str, int] = {}
    depth = 1
    for idx in range(open_idx + 1, close_idx):
        line = lines[idx]
        if depth == 1:
            key = _key_of(line)
            if key and key not in direct_key_indexes:
                direct_key_indexes[key] = idx
        depth += line.count("{") - line.count("}")

    replacements: Dict[int, str] = {}
    to_insert: List[str] = []
    changed = False

    for raw in new_lines:
        raw_line = str(raw).rstrip()
        key = _key_of(raw_line)
        if key and key in direct_key_indexes:
            existing_idx = direct_key_indexes[key]
            existing_line = lines[existing_idx]
            indent = existing_line[: len(existing_line) - len(existing_line.lstrip())]
            replacement = indent + raw_line.lstrip()
            if replacement.rstrip() != existing_line.rstrip():
                replacements[existing_idx] = replacement
                changed = True
            continue
        to_insert.append(raw_line)

    for idx, replacement in replacements.items():
        lines[idx] = replacement

    if not to_insert:
        if not changed:
            return "", "all requested attributes already have the requested values (nothing to change)."
        merged = "\n".join(lines)
        if current.endswith("\n") and not merged.endswith("\n"):
            merged += "\n"
        return merged, ""

    # Match the block's body indentation while preserving relative indentation
    # inside multiline inserted HCL.
    indent = "  "
    for line in lines[open_idx + 1:close_idx]:
        stripped = line.lstrip()
        if stripped and not stripped.startswith("#"):
            indent = line[: len(line) - len(stripped)] or "  "
            break

    non_blank = [line for line in to_insert if line.strip()]
    min_input_indent = min(
        (len(line) - len(line.lstrip())) for line in non_blank
    ) if non_blank else 0

    rendered: List[str] = []
    for line in to_insert:
        if not line.strip():
            rendered.append("")
            continue
        rendered.append(indent + line[min_input_indent:])

    insert_at = close_idx
    if anchor:
        mode, _, needle = anchor.partition(":")
        needle = needle.strip().lower()
        mode = mode.strip().lower()
        if needle:
            for idx in range(open_idx + 1, close_idx):
                if needle in lines[idx].lower():
                    insert_at = idx + 1 if mode == "after" else idx
                    break

    if insert_at == close_idx and lines[insert_at - 1].strip() != "":
        rendered.insert(0, "")

    merged_lines = lines[:insert_at] + rendered + lines[insert_at:]
    merged = "\n".join(merged_lines)
    if current.endswith("\n") and not merged.endswith("\n"):
        merged += "\n"
    return merged, ""



def _materialize_new_top_level_block(block_header: str, new_lines: List[str]) -> str:
    """Build a complete top-level HCL block when the agent used
    insert_into_block for a block that does not exist yet.

    This is a recovery path for VS Code generation only. It prevents the
    'block not found as a top-level block' failure for brand-new module,
    variable, resource, data, output, and locals blocks. It does not infer
    repository-specific values; it only wraps the lines the agent already
    generated.
    """
    header = str(block_header or "").strip()
    if not header:
        return ""
    if header.endswith("{"):
        header = header[:-1].rstrip()

    if not re.match(
        r'^(?:module|variable|resource|data|output|locals)\b',
        header,
        re.IGNORECASE,
    ):
        return ""

    raw_lines = [str(line).rstrip() for line in (new_lines or [])]
    if not any(line.strip() for line in raw_lines):
        return ""

    non_blank = [line for line in raw_lines if line.strip()]
    min_indent = min(
        (len(line) - len(line.lstrip())) for line in non_blank
    ) if non_blank else 0

    rendered: List[str] = []
    for line in raw_lines:
        if not line.strip():
            rendered.append("")
        else:
            rendered.append("  " + line[min_indent:])

    return header + " {\n" + "\n".join(rendered).rstrip() + "\n}\n"


def _is_vscode_aws_clone_or_mirror_request(prompt: str) -> bool:
    text = re.sub(r"\s+", " ", str(prompt or "").lower())
    if not text:
        return False
    create_intent = bool(re.search(r"\b(create|add|provision|new|generate|build)\b", text))
    aws_family = bool(re.search(
        r"\b(aws|redshift|rds|ec2|s3|eks|lambda|dynamodb|cloudfront|elasticache|iam|vpc)\b",
        text,
    ))
    clone_intent = bool(re.search(
        r"\b(mirror|mirroring|clone|copy|copying|based on|same as|replicate)\b",
        text,
    ))
    module_context = bool(re.search(r"\b(module|inputs?|auditdb|consumer)\b", text))
    return create_intent and aws_family and clone_intent and module_context


def _vscode_aws_clone_write_set_errors(
    prompt: str,
    files: List[Dict[str, Any]],
) -> List[str]:
    """Require module implementation + environment consumer for an explicit
    VS Code AWS clone/mirror request.

    This prevents a partial response that edits only the reference module or
    only the consumer.
    """
    if not _is_vscode_aws_clone_or_mirror_request(prompt):
        return []

    paths = [_safe_relpath(str(item.get("path") or "")) for item in (files or [])]
    module_paths = [
        p for p in paths
        if "/modules/" in f"/{p}" and p.endswith(".tf")
    ]
    consumer_paths = [
        p for p in paths
        if p.endswith(".tf") and "/modules/" not in f"/{p}"
    ]

    errors: List[str] = []
    if not module_paths:
        errors.append(
            "VS Code AWS clone/mirror creation is incomplete: no new module implementation .tf files were generated."
        )
    if not consumer_paths:
        errors.append(
            "VS Code AWS clone/mirror creation is incomplete: no target-environment consumer .tf file was generated."
        )
    return errors


def _enforce_additive(
    agent_files: List[Dict[str, Any]],
    existing: Dict[str, str],
    prompt: str = "",
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Server-side append contract.

    - 'create' on an existing path is converted to an append-merge.
    - 'modify' whose content does not start with the existing content is
      repaired when the new content is a pure block addition (existing +
      returned appended), otherwise rejected with an error the user sees.
    - 'delete' always passes through (the agent is only allowed to emit it on
      explicit user request per instructions; the human reviews via SCM).
    """
    repaired: List[Dict[str, Any]] = []
    errors: List[str] = []

    def root_assignment_keys(lines: List[str]) -> List[str]:
        keys: List[str] = []
        for line in lines or []:
            match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", str(line or ""))
            if match and match.group(1) not in keys:
                keys.append(match.group(1))
        return keys

    def root_assignment_owners(keys: List[str]) -> Dict[str, List[str]]:
        owners: Dict[str, List[str]] = {key: [] for key in keys}
        for existing_path, existing_content in existing.items():
            depth = 0
            for line in str(existing_content or "").splitlines():
                if depth == 0:
                    match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
                    if match and match.group(1) in owners:
                        owners[match.group(1)].append(existing_path)
                depth += line.count("{") - line.count("}")
        return owners

    def environment_hints_from_prompt(value: str) -> List[str]:
        """Return environment/path hints explicitly present in the request.

        Environment names in this repository are hierarchical. For example,
        `sbx-infra` belongs to the `vars/sbx/` tier, and `npr-int` belongs to
        `vars/npr/`. Keep both the full name and its parent prefix so a request
        naming a leaf environment can still resolve a centrally owned tier.tfvars.
        """
        text = str(value or "").lower()
        tokens = re.findall(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", text)
        hints: List[str] = []
        known_roots = {"sbx", "npr", "prd", "dev", "test", "stg", "stage", "prod", "production"}
        for token in tokens:
            normalized = token.replace("_", "-")
            parts = [part for part in normalized.split("-") if part]
            if normalized in known_roots or (parts and parts[0] in known_roots):
                for candidate in (normalized, parts[0] if parts else ""):
                    if candidate and candidate not in hints:
                        hints.append(candidate)
        return hints

    def path_environment_parts(value: str) -> List[str]:
        rel = _safe_relpath(value).lower()
        parts = [part for part in rel.split("/") if part]
        env_parts: List[str] = []
        if "vars" in parts:
            idx = parts.index("vars")
            for part in parts[idx + 1:-1]:
                normalized = part.replace("_", "-")
                if normalized not in env_parts:
                    env_parts.append(normalized)
        return env_parts

    def scoped_owners(owners: List[str], proposed_path: str) -> List[str]:
        unique = list(dict.fromkeys(owners))
        if len(unique) <= 1:
            return unique

        # The model-proposed path is accepted immediately when it really owns
        # the assignment. This is exact evidence, not active-editor bias.
        if proposed_path in unique:
            return [proposed_path]

        prompt_hints = environment_hints_from_prompt(prompt)
        if prompt_hints:
            matched = [
                owner for owner in unique
                if any(
                    hint == env_part
                    or env_part.startswith(hint + "-")
                    or hint.startswith(env_part + "-")
                    for hint in prompt_hints
                    for env_part in path_environment_parts(owner)
                )
            ]
            if matched:
                return list(dict.fromkeys(matched))

        # If the request names a leaf environment but the assignment is
        # centrally owned by its tier file, use the proposed path's vars scope
        # as a secondary, deterministic hint.
        proposed_env = path_environment_parts(proposed_path)
        if proposed_env:
            matched = [
                owner for owner in unique
                if any(env in path_environment_parts(owner) for env in proposed_env)
            ]
            if matched:
                return list(dict.fromkeys(matched))

        return unique

    for f in agent_files:
        path = _safe_relpath(str(f.get("path") or ""))
        op = str(f.get("operation") or "modify").lower()
        content = str(f.get("content") or "")
        current = existing.get(path)

        if op == "insert_into_block":
            # Splice new lines INTO an existing top-level block of the live
            # file. For root-level tfvars changes, repository ownership wins
            # over the path proposed by the model: when an assignment already
            # exists in exactly one scanned file, route the edit to that file.
            # This prevents the currently open editor from becoming the target.
            block_header = str(f.get("block") or "").strip()
            new_lines = [str(x) for x in (f.get("lines") or []) if str(x).strip()]
            anchor = str(f.get("anchor") or "").strip()
            normalized_block = " ".join(block_header.lower().split())
            if normalized_block in {"root", "__root__", "file root", "top level", "top-level"}:
                keys = root_assignment_keys(new_lines)
                owners_by_key = root_assignment_owners(keys)
                scoped_by_key = {
                    key: scoped_owners(owners_by_key.get(key, []), path)
                    for key in keys
                }
                ambiguous_keys = [
                    key for key, owners in scoped_by_key.items()
                    if len(set(owners)) > 1
                ]
                if ambiguous_keys:
                    hints = environment_hints_from_prompt(prompt)
                    scope_text = f" within requested environment scope {', '.join(hints)}" if hints else ""
                    errors.append(
                        f"{path}: root assignment ownership is ambiguous for {', '.join(ambiguous_keys)}{scope_text}; "
                        "the change was not applied to an arbitrary open file."
                    )
                    continue
                owned_paths = {
                    owner
                    for key in keys
                    for owner in scoped_by_key.get(key, [])
                }
                if len(owned_paths) == 1:
                    owned_path = next(iter(owned_paths))
                    if owned_path != path:
                        errors.append(
                            f"{path}: rerouted root assignment update to repository owner {owned_path}."
                        )
                        path = owned_path
                        current = existing.get(path)
                elif len(owned_paths) > 1:
                    errors.append(
                        f"{path}: requested root assignments are owned by different files "
                        f"({', '.join(sorted(owned_paths))}); split the edit by file."
                    )
                    continue

            if current is None:
                # If the path itself is new and the agent supplied a complete
                # new top-level block shape through insert_into_block, recover
                # it as a normal create instead of failing with "block not
                # found". This is especially important for new module files.
                materialized = _materialize_new_top_level_block(block_header, new_lines)
                if materialized:
                    repaired.append({
                        "path": path,
                        "operation": "create",
                        "content": materialized,
                        "source_paths_used": f.get("source_paths_used") or [],
                    })
                    errors.append(
                        f"{path}: converted insert_into_block for a new file into a complete top-level block create."
                    )
                    continue
                errors.append(f"{path}: insert_into_block requested but the file is not in the scanned workspace.")
                continue
            if not block_header or not new_lines:
                errors.append(f"{path}: insert_into_block requires 'block' and non-empty 'lines'.")
                continue
            merged, err = _insert_lines_into_block(current, block_header, new_lines, anchor)
            if err and "not found as a top-level block" in err:
                # Recovery for a brand-new top-level block. The agent is
                # supposed to use create/modify for new blocks, but safely
                # materialize the block instead of surfacing a false failure.
                new_block = _materialize_new_top_level_block(block_header, new_lines)
                if new_block:
                    base = str(current or "").rstrip()
                    merged = (base + ("\n\n" if base else "") + new_block).rstrip() + "\n"
                    err = ""
                    errors.append(
                        f"{path}: converted insert_into_block for new top-level block '{block_header}' into a safe append."
                    )
            if err:
                errors.append(f"{path}: {err}")
                continue
            repaired.append({
                "path": path,
                "operation": "modify",
                "content": merged,
                "source_paths_used": f.get("source_paths_used") or [],
                # Mark as an explicitly safe targeted edit so the VS Code
                # client may replace the file with the server-spliced result
                # instead of falling back to appending non-prefix content.
                "in_place": True,
                "typed_insert": {"block": block_header, "lines": new_lines, "anchor": anchor},
            })
            continue

        if op == "fill":
            # Token-fill: apply replacements server-side against the LIVE
            # file content. The rest of the file is untouchable by design.
            if current is None:
                errors.append(f"{path}: fill requested but the file is not in the scanned workspace.")
                continue
            merged = current
            applied = []
            for rep in (f.get("replacements") or []):
                token = str(rep.get("token") or "")
                value = str(rep.get("value") or "")
                if not token or not token.startswith("__FILL__"):
                    continue
                if token in merged:
                    merged = merged.replace(token, value)
                    applied.append({"token": token, "value": value})
                else:
                    errors.append(f"{path}: token {token} not found in the current file (already filled or renamed).")
            if applied:
                repaired.append({
                    **f, "path": path, "operation": "modify",
                    "content": merged, "typed_replacements": applied,
                })
            continue

        if op == "delete" or current is None:
            # New path or explicit delete: pass through unchanged.
            repaired.append({**f, "path": path})
            continue

        if op == "modify" and bool(f.get("in_place")):
            # Explicit user-requested in-place edit or server-expanded typed
            # insert: relax the prefix check but still block substantial
            # shrinkage and duplicate whole-file append accidents.
            if len(content.strip()) >= int(len(current.strip()) * 0.8):
                repaired.append({**f, "path": path, "operation": "modify", "in_place": True})
            else:
                errors.append(
                    f"{path}: this file is large and the returned content was "
                    "much shorter than the real file, so applying it would have "
                    "deleted existing code — change rejected. Tell Terrabot to "
                    "'insert the new lines into the existing block instead of "
                    "regenerating the file' (it will use a safe targeted insert)."
                )
            continue

        norm_current = current.rstrip("\n")
        norm_new = content.rstrip("\n")

        if norm_new.startswith(norm_current):
            # Append contract satisfied (covers identical content too).
            repaired.append({**f, "path": path, "operation": "modify"})
            continue

        if norm_current.startswith(norm_new):
            # Returned content is a truncation of the existing file — the
            # destructive case. Reject outright.
            errors.append(
                f"{path}: generated content would remove existing code — "
                "change rejected. Ask Terrabot to 'insert the new lines into "
                "the existing file/block instead of regenerating it'."
            )
            continue

        # Neither prefix relation holds: the agent returned content that is
        # neither a valid append nor a truncation — typically a regenerated
        # near-copy of the whole file (reformatted whitespace breaks the
        # byte-prefix check). Block-level dedup repair: split the returned
        # content into top-level blocks and append ONLY blocks whose header
        # does not already exist in the current file. Duplicate blocks are
        # silently skipped so the file can never be doubled.
        if norm_new:
            new_blocks, appended_headers, skipped_headers = _dedup_append_blocks(norm_current, norm_new)
            if appended_headers:
                merged = norm_current + "\n\n" + new_blocks + "\n"
                repaired.append({**f, "path": path, "operation": "modify", "content": merged})
                note = f"{path}: appended new block(s): " + ", ".join(appended_headers[:6])
                if skipped_headers:
                    note += f" (skipped {len(skipped_headers)} duplicate block(s) the agent re-echoed)"
                errors.append(note)
            elif skipped_headers:
                errors.append(
                    f"{path}: the returned content only re-echoed {len(skipped_headers)} "
                    "block(s) that already exist — nothing new to apply. If you "
                    "wanted to CHANGE lines inside an existing block, tell "
                    "Terrabot to 'insert the new lines into the existing block' "
                    "or use a fill request for tokenized values."
                )
            else:
                errors.append(
                    f"{path}: generated content conflicts with the existing file "
                    "and could not be safely merged; change rejected."
                )
        else:
            errors.append(
                f"{path}: generated content conflicts with the existing file "
                "and could not be safely merged; change rejected."
            )

    return repaired, errors




def _explicit_iac_paths_from_prompt(prompt: str) -> List[str]:
    """Return explicit .tf/.tfvars paths or basenames named by the user."""
    found: List[str] = []
    pattern = r"(?<![A-Za-z0-9_.-])([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.(?:tf|tfvars))(?![A-Za-z0-9_.-])"
    for match in re.finditer(pattern, str(prompt or ""), re.IGNORECASE):
        value = _safe_relpath(match.group(1))
        if value and value not in found:
            found.append(value)
    return found


def _requested_boolean_flag(prompt: str) -> Tuple[str, Optional[bool]]:
    """Resolve common repository feature-flag requests deterministically."""
    text = re.sub(r"\s+", " ", str(prompt or "").strip().lower())
    if not text:
        return "", None

    flag = ""
    if re.search(r"patch\s*management", text):
        flag = "create_patch_management"
    elif re.search(r"cloud\s*amqp|cloudamqp|rabbit\s*mq|rabbitmq", text):
        if "datadog" in text and re.search(r"log|logging", text):
            flag = "cloudamqp_enable_datadog_logs"
        elif "datadog" in text and re.search(r"metric|monitoring", text):
            flag = "cloudamqp_enable_datadog_metrics"
        else:
            flag = "create_cloudamqp"
    elif re.search(r"diagnostic\s*settings?", text):
        flag = "create_diagnostic_settings"

    if not flag:
        return "", None
    if re.search(r"\b(disable|disabled|turn off|switch off|remove|stop)\b", text):
        return flag, False
    if re.search(r"\b(create|enable|enabled|turn on|switch on|add|start)\b", text):
        return flag, True
    return flag, None


def _path_matches_prompt_environment(path: str, prompt: str) -> int:
    rel = _safe_relpath(path).lower()
    text = str(prompt or "").lower().replace("_", "-")
    score = 0
    for part in [p for p in rel.replace("_", "-").split("/") if p]:
        if part and re.search(rf"(?<![a-z0-9]){re.escape(part)}(?![a-z0-9])", text):
            score += 20 + len(part)
    return score


def _resolve_explicit_existing_path(prompt: str, existing: Dict[str, str]) -> str:
    explicit = _explicit_iac_paths_from_prompt(prompt)
    if not explicit:
        return ""
    existing_paths = list(existing.keys())
    for requested in explicit:
        if requested in existing:
            return requested
        basename = requested.rsplit("/", 1)[-1].lower()
        candidates = [p for p in existing_paths if p.rsplit("/", 1)[-1].lower() == basename]
        if candidates:
            return sorted(candidates, key=lambda p: (-_path_matches_prompt_environment(p, prompt), len(p), p))[0]
    return ""


def _deterministic_requested_flag_edit(
    prompt: str,
    existing: Optional[Dict[str, str]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Apply an explicit/common boolean flag request even when the model calls it a no-op.

    Exact explicit file selection wins. Otherwise the existing root assignment
    owner is selected within the environment named in the prompt.
    """
    if not existing:
        return [], []
    flag, desired = _requested_boolean_flag(prompt)
    if not flag or desired is None:
        return [], []

    target = _resolve_explicit_existing_path(prompt, existing)
    assignment_re = re.compile(rf"^\s*{re.escape(flag)}\s*=\s*(true|false)\b", re.IGNORECASE | re.MULTILINE)
    owners = [path for path, content in existing.items() if assignment_re.search(str(content or ""))]

    if not target:
        if len(owners) == 1:
            target = owners[0]
        elif owners:
            ranked = sorted(owners, key=lambda p: (-_path_matches_prompt_environment(p, prompt), len(p), p))
            if ranked and (_path_matches_prompt_environment(ranked[0], prompt) > 0 or len(ranked) == 1):
                top_score = _path_matches_prompt_environment(ranked[0], prompt)
                tied = [p for p in ranked if _path_matches_prompt_environment(p, prompt) == top_score]
                if len(tied) == 1:
                    target = ranked[0]

    if not target or target not in existing:
        return [], []

    current = existing[target]
    match = assignment_re.search(current)
    if match and (match.group(1).lower() == ("true" if desired else "false")):
        return [], []

    merged, err = _insert_lines_into_block(
        current,
        "__root__",
        [f"{flag} = {'true' if desired else 'false'}"],
    )
    if err:
        return [], [f"{target}: {err}"]
    return [{
        "path": target,
        "operation": "modify",
        "content": merged,
        "in_place": True,
        "typed_insert": {
            "block": "__root__",
            "lines": [f"{flag} = {'true' if desired else 'false'}"],
            "anchor": "",
        },
        "source_paths_used": [target],
    }], [f"Applied deterministic repository flag routing to {target} for {flag}."]

def _is_cloudamqp_second_instance_request(prompt: str, context_pack: Optional[Dict[str, Any]] = None) -> bool:
    text = (prompt or "").lower()
    cp_text = json.dumps(context_pack or {}, default=str).lower()[:20000]
    wants_cloudamqp = any(term in text for term in ("cloudamqp", "cloud amqp", "rabbitmq", "rabbit mq"))
    wants_second = any(term in text for term in ("second", "another", "additional", "multi-instance", "multiple"))
    already_flagged = "create_cloudamqp" in cp_text or "aws_mq_broker" in cp_text
    return wants_cloudamqp and wants_second and already_flagged


def _context_existing_paths(context_pack: Optional[Dict[str, Any]]) -> List[str]:
    """Best-effort repo-relative path inventory from the context pack.

    The context pack is intentionally compact, so this collects paths from all
    places that may contain file references. It is used only to avoid hardcoded
    filenames in safety messages and completeness checks.
    """
    paths: List[str] = []

    def add(value: Any) -> None:
        rel = _safe_relpath(str(value or ""))
        if rel and "." in Path(rel).name and rel not in paths:
            paths.append(rel)

    if not isinstance(context_pack, dict):
        return paths

    for item in context_pack.get("evidence") or []:
        if isinstance(item, dict):
            add(item.get("path"))

    profile = context_pack.get("repo_profile") or {}
    if isinstance(profile, dict):
        for key in ("tfvars_files", "pipeline_files", "policy_files"):
            for value in profile.get(key) or []:
                add(value)
        for key in ("modules", "resources", "variables", "data_sources"):
            for item in profile.get(key) or []:
                if isinstance(item, dict):
                    add(item.get("path"))

    workflow = context_pack.get("workflow_profile") or {}
    if isinstance(workflow, dict):
        for key in ("target_files", "value_files"):
            for value in workflow.get(key) or []:
                add(value)
        for item in workflow.get("evidence") or []:
            if isinstance(item, dict):
                add(item.get("path"))

    return paths


def _existing_cloudamqp_surface_paths(context_pack: Optional[Dict[str, Any]]) -> Dict[str, List[str]]:
    existing = [p.lower() for p in _context_existing_paths(context_pack)]
    surfaces = {"vars": [], "implementation": [], "outputs": []}
    for path in existing:
        name = path.rsplit("/", 1)[-1]
        in_vena = "/modules/vena_datacentre/" in f"/{path}"
        in_cloudamqp = "/modules/cloudamqp/" in f"/{path}"
        if in_vena and name in {"vars.tf", "variables.tf"}:
            surfaces["vars"].append(path)
        if (in_vena or in_cloudamqp) and name == "outputs.tf":
            surfaces["outputs"].append(path)
        if in_cloudamqp and path.endswith(".tf") and name not in {"vars.tf", "variables.tf", "outputs.tf"}:
            surfaces["implementation"].append(path)
        elif in_vena and "cloudamqp" in name and path.endswith(".tf") and name != "outputs.tf":
            surfaces["implementation"].append(path)
    return surfaces


def _cloudamqp_second_instance_completeness_errors(
    files: List[Dict[str, Any]],
    context_pack: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Reject partial CloudAMQP second-instance refactors without inventing paths.

    Older logic hardcoded modules/vena_datacentre/cloudamqp.tf. Some repos keep
    the real implementation in modules/cloudamqp instead, with vena_datacentre
    only acting as the feature-flag wrapper. This check therefore derives the
    expected surfaces from existing context paths and only names files that are
    actually present in the scanned repo.
    """
    if not files:
        return []
    paths = [_safe_relpath(str(f.get("path") or "")) for f in files]
    lower_paths = [p.lower() for p in paths]
    surfaces = _existing_cloudamqp_surface_paths(context_pack)

    def has_generated(candidates: List[str]) -> bool:
        return bool(candidates) and any(p in set(candidates) for p in lower_paths)

    vars_ok = has_generated(surfaces["vars"]) or any(
        p.endswith(("vars.tf", "variables.tf")) and "vena_datacentre" in p for p in lower_paths
    )
    impl_ok = has_generated(surfaces["implementation"]) or (
        not surfaces["implementation"]
        and any(("/modules/cloudamqp/" in f"/{p}" or "vena_datacentre" in p) and "cloudamqp" in p and p.endswith(".tf") for p in lower_paths)
    )
    outputs_required = bool(surfaces["outputs"])
    outputs_ok = (not outputs_required) or has_generated(surfaces["outputs"])
    consumer_ok = any(
        str(f.get("operation") or "").lower() == "insert_into_block"
        and "cloudamqp_instances" in "\n".join(str(x) for x in (f.get("lines") or [])).lower()
        for f in files
    ) or any(
        p.endswith("main.tf") and "cloudamqp_instances" in str(f.get("content") or "").lower()
        for f, p in zip(files, lower_paths)
    )

    missing: List[str] = []
    if not vars_ok:
        candidates = surfaces["vars"] or ["existing vena_datacentre vars.tf/variables.tf"]
        missing.append("module variables/shim surface (" + ", ".join(candidates[:3]) + ")")
    if not impl_ok:
        candidates = surfaces["implementation"] or ["existing modules/cloudamqp/*.tf implementation file"]
        missing.append("actual CloudAMQP implementation surface (" + ", ".join(candidates[:5]) + ")")
    if not outputs_ok:
        missing.append("existing CloudAMQP outputs surface (" + ", ".join(surfaces["outputs"][:5]) + ")")
    if not consumer_ok:
        missing.append("target environment main.tf insert_into_block with cloudamqp_instances")
    invalid_consumer_refs: List[str] = []
    for f, p in zip(files, lower_paths):
        body = "\n".join(str(x) for x in (f.get("lines") or [])) + "\n" + str(f.get("content") or "")
        if p.endswith("main.tf") and "cloudamqp_instances" in body.lower() and "module.vena_datacentre." in body:
            invalid_consumer_refs.append(str(f.get("path") or "main.tf"))

    errors: List[str] = []
    if missing:
        errors.append(
            "CloudAMQP second-instance generation was incomplete. Missing: "
            + "; ".join(missing)
            + ". Re-run the request; Terrabot must refactor only existing scanned files. Do not ask for or generate hardcoded paths such as modules/vena_datacentre/cloudamqp.tf unless that path exists in the repo."
        )
    if invalid_consumer_refs:
        errors.append(
            "CloudAMQP consumer generation is invalid in "
            + ", ".join(invalid_consumer_refs)
            + ": a module block cannot pass module.vena_datacentre.* outputs back into the same module input. The target environment main.tf must pass only external/user values such as the default plan, subnet CIDR, and RabbitMQ version; the vena_datacentre module must compute VPC/subnet/provider details internally."
        )
    return errors

def handle_generate_request(data: Dict[str, Any], headers=None) -> tuple:
    del headers
    prompt: str = (data.get("prompt") or data.get("message") or "").strip()
    thread_id: str = str(data.get("thread_id") or "").strip()
    context_pack: Optional[Dict[str, Any]] = data.get("context_pack")
    repository: Optional[Dict[str, Any]] = data.get("repository") if isinstance(data.get("repository"), dict) else None

    if context_pack and isinstance(context_pack, dict):
        if not prompt:
            prompt = (
                context_pack.get("prompt")
                or (context_pack.get("workflow_profile") or {}).get("workflow_type")
                or "infrastructure change"
            )
        return _call_foundry_and_return(prompt, context_pack, thread_id=thread_id, repository=repository)

    files = data.get("files") or []
    if not isinstance(files, list):
        return {"ok": False, "reply": "files must be a list."}, 400
    if not prompt:
        return {"ok": False, "reply": "prompt is required."}, 400

    existing_map = _existing_files_map(files)
    workspace = _materialize_workspace(files, data.get("workspace_name") or "workspace")

    from terrabot_core.service import ask_infrastructure
    try:
        plan = ask_infrastructure(workspace, prompt, thread_id=thread_id)
    except TypeError:
        # Older service.py without the thread_id parameter — stay compatible.
        plan = ask_infrastructure(workspace, prompt)

    if plan.get("status") == "patch_ready":
        # The recursive-generator path returns finished files. Run the same
        # additive guard as the direct path so this route can never overwrite
        # existing code either, and hoist the passthrough fields (analysis,
        # user_fillable, inner-conversation thread_id) so the extension keeps
        # its full feature set regardless of which path served the request.
        plan_files = plan.get("files") or []
        plan_context_pack = plan.get("context_pack") or {}
        additive_notes: List[str] = []
        completeness_errors: List[str] = []
        if _is_cloudamqp_second_instance_request(prompt, plan_context_pack if isinstance(plan_context_pack, dict) else None):
            completeness_errors = _cloudamqp_second_instance_completeness_errors(plan_files, plan_context_pack if isinstance(plan_context_pack, dict) else None)
            if completeness_errors:
                plan_files = []
        if existing_map and plan_files:
            plan_files, additive_notes = _enforce_additive(plan_files, existing_map, prompt)
        summary = str(plan.get("summary") or "")
        if additive_notes:
            summary = summary + " [Additive-guard: " + " | ".join(additive_notes) + "]"
        return {
            "ok": True,
            "thread_id": str(plan.get("thread_id") or thread_id or ""),
            "result": plan,
            "summary": summary,
            "analysis": str(plan.get("analysis") or ""),
            "user_fillable": plan.get("user_fillable") or [],
            "diff": plan.get("diff") or "",
            "files": plan_files,
            "questions": (plan.get("questions") or []) + completeness_errors,
            "validation_commands": plan.get("validation_commands") or [],
            "reply": summary,
        }, 200

    cp = plan.get("context_pack") or {}
    return _call_foundry_and_return(prompt, cp, base_plan=plan, thread_id=thread_id, existing_files=existing_map, repository=repository)


_SENSITIVE_FINDING_RE = re.compile(
    r"sensitive|secret|password|credential|private key|token|connection string",
    re.IGNORECASE,
)


def _demote_input_policy_blocks(
    context_pack: Dict[str, Any],
    existing_files: Optional[Dict[str, str]],
) -> Dict[str, Any]:
    """Policy findings about PRE-EXISTING workspace files must not block
    generation of unrelated code. Sensitive values already committed in the
    repo are the repo's problem to remediate — Terrabot's policy gate exists
    to stop Terrabot from GENERATING new sensitive values.

    Demote any blocking_issue that (a) reads like a sensitive-content finding
    and (b) references a path that exists in the user's scanned workspace,
    into warnings (prefixed so the agent can still surface it as advice).
    All other blocking issues (true policy violations about the requested
    change) remain blocking. Fail-open: any error leaves policy untouched.
    """
    try:
        policy = context_pack.get("policy")
        if not isinstance(policy, dict):
            return context_pack
        blocking = list(policy.get("blocking_issues") or [])
        if not blocking:
            return context_pack
        known_paths = set((existing_files or {}).keys())

        kept: list = []
        demoted: list = []
        for issue in blocking:
            text = str(issue)
            is_sensitive_finding = bool(_SENSITIVE_FINDING_RE.search(text))
            references_input = any(p in text for p in known_paths) if known_paths else False
            if is_sensitive_finding and (references_input or "retrieved" in text.lower() or "evidence" in text.lower() or "scan" in text.lower()):
                demoted.append(
                    "PRE-EXISTING repo content (informational, not blocking): " + text
                )
            else:
                kept.append(issue)

        if demoted:
            policy = dict(policy)
            policy["blocking_issues"] = kept
            policy["warnings"] = list(policy.get("warnings") or []) + demoted
            policy["allowed"] = bool(policy.get("allowed", True)) or not kept
            if not kept:
                policy["allowed"] = True
            context_pack = dict(context_pack)
            context_pack["policy"] = policy
    except Exception:
        pass
    return context_pack



def _repair_vscode_aws_clone_or_mirror_generation(
    prompt: str,
    context_pack: Dict[str, Any],
    thread_id: str,
    previous_reply: str,
    errors: List[str],
) -> Tuple[str, Optional[Dict[str, Any]], str]:
    """One bounded Foundry retry for an incomplete VS Code AWS clone/mirror
    response. The retry is internal and uses the same live context pack; the
    user is not asked to resolve a mechanical module+consumer omission.
    """
    from shared_code.terrabot_service import call_agent

    repair_input = json.dumps({
        "task": "VS CODE AWS CLONE/MIRROR COMPLETENESS REPAIR",
        "user_request": prompt,
        "backend_validation_errors": errors,
        "previous_agent_reply": previous_reply,
        "requirements": [
            "This is not a new user request. Correct the previous generation using the same live context_pack.",
            "Return JSON only with the normal VS Code keys: summary, analysis, source_paths_used, files, user_fillable, questions, validation_commands.",
            "The user explicitly requested a NEW AWS module/resource by mirroring/cloning/copying an existing module. The reference module is read-only.",
            "Return the COMPLETE write-set in one response: all new module implementation .tf files demonstrated by the reference module AND the target-environment consumer .tf change.",
            "Do not modify the reference module directory for the new instance.",
            "Mirror the reference consumer's complete input set and repository wiring.",
            "For required non-sensitive values not grounded in repository code/defaults, use __FILL__<input_name>__ and matching user_fillable metadata. Do not ask for ordinary values.",
            "Do not use insert_into_block for a top-level block that does not already exist. New blocks must be complete create/modify content.",
            "questions must be empty unless there is a genuinely sensitive/structural blocker unrelated to the mechanical completeness errors above."
        ],
        "context_pack": context_pack,
    }, indent=2)

    try:
        repaired_thread_id, repaired_reply = call_agent(thread_id, repair_input)
    except Exception:
        return thread_id, None, ""

    return repaired_thread_id, _parse_reply(repaired_reply), repaired_reply


def _call_foundry_and_return(
    prompt: str,
    context_pack: Dict[str, Any],
    base_plan: Optional[Dict[str, Any]] = None,
    thread_id: str = "",
    existing_files: Optional[Dict[str, str]] = None,
    repository: Optional[Dict[str, Any]] = None,
) -> tuple:
    from shared_code.terrabot_service import call_agent

    context_pack = _demote_input_policy_blocks(context_pack, existing_files)
    context_pack = _attach_shared_repository_context(context_pack, prompt, repository)

    # A non-empty thread_id means this is a follow-up turn in an existing
    # Foundry conversation — use the light envelope so the user's answer
    # isn't buried under a repeated full context_pack.
    agent_input = _build_agent_prompt(prompt, context_pack, follow_up=bool(thread_id))

    try:
        thread_id, reply = call_agent(thread_id, agent_input)
    except Exception as exc:
        return {"ok": False, "reply": "Azure AI Foundry call failed.", "error": str(exc)}, 500

    parsed = _parse_reply(reply)

    if not parsed:
        # Agent replied in natural language (chat / Q&A path) — pass it through.
        return {
            "ok": True,
            "thread_id": thread_id,
            "summary": reply.strip(),
            "analysis": "",
            "files": [],
            "user_fillable": [],
            "questions": [],
            "validation_commands": [],
            "diff": "",
            "reply": reply.strip(),
        }, 200

    # Hoist questions/validation_commands if agent nested them inside file entries
    files_raw = parsed.get("files") or []
    clean_files = []
    questions = list(parsed.get("questions") or [])
    commands = list(parsed.get("validation_commands") or [])
    for f in files_raw:
        if not isinstance(f, dict):
            continue
        questions += [q for q in (f.pop("questions", None) or []) if q not in questions]
        commands += [c for c in (f.pop("validation_commands", None) or []) if c not in commands]
        clean_files.append(f)

    # Deterministic flag routing protects explicit-file and exact-owner requests
    # from model no-op mistakes (for example treating event-grid flags as the
    # patch-management creation switch).
    deterministic_notes: List[str] = []
    deterministic_files, deterministic_notes = _deterministic_requested_flag_edit(prompt, existing_files)
    if deterministic_files:
        clean_files = deterministic_files
        parsed["summary"] = str(parsed.get("summary") or "").strip() or "Applied the requested Terraform feature-flag change."
        parsed["analysis"] = (str(parsed.get("analysis") or "").rstrip() + "\n" + "\n".join(deterministic_notes)).strip()

    # Reject known-incomplete partial refactors before applying anything.
    completeness_errors: List[str] = []

    # VS Code explicit AWS clone/mirror requests are a complete write-set:
    # new module implementation files + target environment consumer file.
    # If the first model response is partial, repair it internally once rather
    # than exposing the mechanical omission to the user.
    clone_errors = _vscode_aws_clone_write_set_errors(prompt, clean_files)
    if clone_errors:
        repaired_thread_id, repaired_parsed, repaired_reply = _repair_vscode_aws_clone_or_mirror_generation(
            prompt=prompt,
            context_pack=context_pack,
            thread_id=thread_id,
            previous_reply=reply,
            errors=clone_errors,
        )
        if repaired_parsed:
            thread_id = repaired_thread_id
            parsed = repaired_parsed
            questions = list(parsed.get("questions") or [])
            commands = list(parsed.get("validation_commands") or [])
            clean_files = []
            for item in (parsed.get("files") or []):
                if not isinstance(item, dict):
                    continue
                questions += [q for q in (item.pop("questions", None) or []) if q not in questions]
                commands += [c for c in (item.pop("validation_commands", None) or []) if c not in commands]
                clean_files.append(item)
            clone_errors = _vscode_aws_clone_write_set_errors(prompt, clean_files)

        if clone_errors:
            clean_files = []
            # Keep one specific diagnostic only after the bounded internal
            # repair failed; do not surface the old block-not-found errors.
            questions = [
                "Terrabot could not complete both the new AWS module implementation and its target-environment consumer in the same generation."
            ]
            completeness_errors.extend(clone_errors)
    if _is_cloudamqp_second_instance_request(prompt, context_pack):
        completeness_errors = _cloudamqp_second_instance_completeness_errors(clean_files, context_pack)
        if completeness_errors:
            clean_files = []
            questions.extend(completeness_errors)

    # Server-side append contract enforcement (belt over the instructions).
    additive_notes: List[str] = []
    if existing_files and clean_files:
        clean_files, additive_notes = _enforce_additive(clean_files, existing_files, prompt)

    summary = str(parsed.get("summary") or "Generated infrastructure patch.")
    if additive_notes:
        summary = summary + " [Additive-guard: " + " | ".join(additive_notes) + "]"
    analysis = str(parsed.get("analysis") or "")
    user_fillable = [
        f for f in (parsed.get("user_fillable") or [])
        if isinstance(f, dict) and f.get("token") and f.get("input")
    ]
    return {
        "ok": True,
        "thread_id": thread_id,
        "summary": summary,
        "analysis": analysis,
        "files": clean_files,
        "user_fillable": user_fillable,
        "questions": questions,
        "validation_commands": commands,
        "diff": (base_plan.get("diff") or "") if base_plan else "",
        "reply": summary,
    }, 200
