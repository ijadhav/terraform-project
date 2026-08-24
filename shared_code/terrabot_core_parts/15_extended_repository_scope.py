"""Extended live-GitHub repository scope for Terrabot.

This layer is intentionally loaded last. It extends AWS repository routing without
changing the existing tf-devops / tf-azure-hub workflows or deleting/replacing any
legacy functions. Repository selection for the added repositories is Foundry-owned;
the backend only validates the selected target and supplies live GitHub evidence.
"""
from __future__ import annotations
import os
import contextvars
import requests
from typing import TYPE_CHECKING, Optional, Any


if TYPE_CHECKING:
    from shared_code.terrabot_core_typing import (
        AGENT_NAME,
        AWS_MODULES_ROOT,
        INFRA_MODIFICATION_WORKFLOWS,
        LOGGER,
        github_base_branch_for_cloud,
        github_repo_for_cloud,
        is_infra_modification_or_delete_prompt,
        _require_setting,
        _matched_blocks_for_prompt,
        _score_infra_candidate,
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
        github_pr_source_branch_for_cloud,
        _infra_modification_search_terms,
        _explicit_iac_paths_from_prompt,
        github_list_tf_files_recursive,
        cloud_root_dir,
        build_stable_folder,
        infer_generation_workflow,
        build_backend_existing_infra_modification_context,
        handle_teams_chat_request,
        validate_github_app_repository_access,
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
        GITHUB_API,
        GITHUB_OWNER,
        get_github_app_installation_token,
        _github_request_error,
        _TEAMS_SELF_CONTAINED_INFRA_ACTION_RE,
    )
# ---------------------------------------------------------------------------
# Additional repository configuration
# ---------------------------------------------------------------------------
GITHUB_PR_SOURCE_BRANCH_AWS = os.getenv("GITHUB_PR_SOURCE_BRANCH_AWS", "").strip()
GITHUB_TF_DNS_REPO = os.getenv("GITHUB_TF_DNS_REPO", "tf-dns").strip()
GITHUB_TF_DNS_BASE_BRANCH = os.getenv("GITHUB_TF_DNS_BASE_BRANCH", "main").strip() or "main"
GITHUB_TF_AWS_SSO_REPO = os.getenv("GITHUB_TF_AWS_SSO_REPO", "tf-aws-sso").strip()
GITHUB_TF_AWS_SSO_BASE_BRANCH = os.getenv("GITHUB_TF_AWS_SSO_BASE_BRANCH", "main").strip() or "main"
GITHUB_TF_NETWORK_RESOURCES_REPO = os.getenv(
    "GITHUB_TF_NETWORK_RESOURCES_REPO", "tf-network-resources"
).strip()
GITHUB_TF_NETWORK_RESOURCES_BASE_BRANCH = os.getenv(
    "GITHUB_TF_NETWORK_RESOURCES_BASE_BRANCH", "main"
).strip() or "main"
GITHUB_TERRAFORM_AWS_VPC_REPO = os.getenv(
    "GITHUB_TERRAFORM_AWS_VPC_REPO", "terraform-aws-vpc"
).strip()
GITHUB_TERRAFORM_AWS_VPC_BASE_BRANCH = os.getenv(
    "GITHUB_TERRAFORM_AWS_VPC_BASE_BRANCH", "master"
).strip() or "master"

_EXTENDED_AWS_REPOSITORIES = {
    "tf-dns": {
        "repo": GITHUB_TF_DNS_REPO,
        "base_branch": GITHUB_TF_DNS_BASE_BRANCH,
        "root": ".",
        "purpose": (
            "AWS Route53/private DNS infrastructure: environment private hosted zones, "
            "VPC-zone associations, shared network-services DNS records, and DNS-specific modules."
        ),
    },
    "tf-aws-sso": {
        "repo": GITHUB_TF_AWS_SSO_REPO,
        "base_branch": GITHUB_TF_AWS_SSO_BASE_BRANCH,
        "root": ".",
        "purpose": (
            "AWS IAM Identity Center / SSO configuration: permission sets, identity-store groups, "
            "managed and customer-managed policies, and AWS account assignments."
        ),
    },
    "tf-network-resources": {
        "repo": GITHUB_TF_NETWORK_RESOURCES_REPO,
        "base_branch": GITHUB_TF_NETWORK_RESOURCES_BASE_BRANCH,
        "root": "network_resources",
        "purpose": (
            "Shared AWS network-services infrastructure: VPCs, DNS VPC, Transit Gateway, TGW routes "
            "and attachments, VPN/interconnect routing, Route53 Resolver, and regional tfvars."
        ),
    },
    "terraform-aws-vpc": {
        "repo": GITHUB_TERRAFORM_AWS_VPC_REPO,
        "base_branch": GITHUB_TERRAFORM_AWS_VPC_BASE_BRANCH,
        "root": ".",
        "purpose": (
            "Reusable AWS VPC Terraform module implementation consumed by network infrastructure. "
            "Use only when the requested change is to the VPC module implementation/API itself, not "
            "for ordinary environment VPC configuration."
        ),
    },
}

_EXTENDED_REPO_TARGET = contextvars.ContextVar(
    "terrabot_extended_repo_target", default=""
)
_EXTENDED_REPO_CLASSIFICATION_CACHE: dict[str, str] = {}

_PRE_EXTENDED_NORMALIZE_REPO_TARGET = normalize_repo_target
_PRE_EXTENDED_GITHUB_REPO_FOR_CLOUD = github_repo_for_cloud
_PRE_EXTENDED_GITHUB_BASE_BRANCH_FOR_CLOUD = github_base_branch_for_cloud
_PRE_EXTENDED_GITHUB_PR_SOURCE_BRANCH_FOR_CLOUD = github_pr_source_branch_for_cloud
_PRE_EXTENDED_CLOUD_ROOT_DIR = cloud_root_dir
_PRE_EXTENDED_BUILD_STABLE_FOLDER = build_stable_folder
_PRE_EXTENDED_IS_EXISTING_INVOCATION_CREATION = _teams_is_existing_invocation_creation
_PRE_EXTENDED_INFER_GENERATION_WORKFLOW = infer_generation_workflow
_PRE_EXTENDED_BUILD_EXISTING_CONTEXT = build_backend_existing_infra_modification_context
_PRE_EXTENDED_HANDLE_TEAMS_CHAT = handle_teams_chat_request
_PRE_EXTENDED_VALIDATE_GITHUB_APP_ACCESS = validate_github_app_repository_access

INFRA_MODIFICATION_WORKFLOWS.add("aws_repository_native_change")


def _canonical_extended_repo_target(value: Any | None) -> str:
    text = str(value or "").strip().lower().replace("_", "-")
    aliases = {
        "tf-dns": "tf-dns",
        "dns": "tf-dns",
        "tf-aws-sso": "tf-aws-sso",
        "aws-sso": "tf-aws-sso",
        "tf-network-resources": "tf-network-resources",
        "network-resources": "tf-network-resources",
        "terraform-aws-vpc": "terraform-aws-vpc",
        "aws-vpc-module": "terraform-aws-vpc",
    }
    return aliases.get(text, "")


def _active_extended_repo_target() -> str:
    return _canonical_extended_repo_target(_EXTENDED_REPO_TARGET.get())


def normalize_repo_target(cloud: Any | None, repo_target: Any | None = None, workflow: Any | None = None) -> str:
    normalized_cloud = normalize_cloud(cloud)
    explicit = _canonical_extended_repo_target(repo_target)
    active = _active_extended_repo_target()
    if normalized_cloud == "aws" and explicit:
        return explicit
    if normalized_cloud == "aws" and str(workflow or "").strip() == "aws_repository_native_change" and active:
        return active
    if normalized_cloud == "aws" and active:
        return active
    return _PRE_EXTENDED_NORMALIZE_REPO_TARGET(normalized_cloud, repo_target, workflow)


def github_repo_for_cloud(cloud: Any | None, repo_target: Optional[str] = None, workflow: Optional[str] = None) -> str:
    normalized = normalize_repo_target(cloud, repo_target, workflow)
    if normalized in _EXTENDED_AWS_REPOSITORIES:
        return _require_setting(
            _EXTENDED_AWS_REPOSITORIES[normalized]["repo"],
            f"GitHub repository for {normalized}",
        )
    return _PRE_EXTENDED_GITHUB_REPO_FOR_CLOUD(cloud, repo_target, workflow)


def github_base_branch_for_cloud(cloud: Any | None, repo_target: Optional[str] = None, workflow: Optional[str] = None) -> str:
    normalized = normalize_repo_target(cloud, repo_target, workflow)
    if normalized in _EXTENDED_AWS_REPOSITORIES:
        return str(_EXTENDED_AWS_REPOSITORIES[normalized]["base_branch"])
    return _PRE_EXTENDED_GITHUB_BASE_BRANCH_FOR_CLOUD(cloud, repo_target, workflow)


def github_pr_source_branch_for_cloud(cloud: Any | None, repo_target: Optional[str] = None, workflow: Optional[str] = None) -> str:
    normalized = normalize_repo_target(cloud, repo_target, workflow)
    if normalized in _EXTENDED_AWS_REPOSITORIES:
        # Preserve the existing requester-aware branch naming behavior while
        # keeping the repository target independent from tf-devops.
        return GITHUB_PR_SOURCE_BRANCH_AWS
    return _PRE_EXTENDED_GITHUB_PR_SOURCE_BRANCH_FOR_CLOUD(cloud, repo_target, workflow)


def cloud_root_dir(cloud: Any | None, repo_target: Optional[str] = None, workflow: Optional[str] = None) -> str:
    normalized = normalize_repo_target(cloud, repo_target, workflow)
    if normalized in _EXTENDED_AWS_REPOSITORIES:
        return str(_EXTENDED_AWS_REPOSITORIES[normalized]["root"] or ".").strip().strip("/") or "."
    return _PRE_EXTENDED_CLOUD_ROOT_DIR(cloud, repo_target, workflow)


def build_stable_folder(thread_id: str, cloud: str, repo_target: Optional[str] = None, workflow: Optional[str] = None) -> str:
    normalized = normalize_repo_target(cloud, repo_target, workflow)
    if normalized in _EXTENDED_AWS_REPOSITORIES:
        # These repositories already have authoritative native layouts. Never
        # redirect generated Terraform into Terrabot scratch/change folders.
        return cloud_root_dir(cloud, normalized, workflow) or "."
    return _PRE_EXTENDED_BUILD_STABLE_FOLDER(thread_id, cloud, repo_target, workflow)


def _teams_is_existing_invocation_creation(prompt: str) -> bool:
    if _active_extended_repo_target():
        text = str(prompt or "").strip()
        if not text or is_infra_modification_or_delete_prompt(text):
            return False
        return bool(re.search(r"\b(create|add|provision|deploy|build|make)\b", text, re.IGNORECASE))
    return _PRE_EXTENDED_IS_EXISTING_INVOCATION_CREATION(prompt)


def _explicit_extended_repo_from_prompt(prompt: str) -> str:
    text = str(prompt or "").lower()
    for target, cfg in _EXTENDED_AWS_REPOSITORIES.items():
        names = {target.lower(), str(cfg.get("repo") or "").lower()}
        if any(name and re.search(rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])", text) for name in names):
            return target
    return ""


def _foundry_select_extended_repo_target(prompt: str) -> str:
    """Ask Foundry whether a request belongs to one of the added repositories.

    The classifier is deliberately conservative. Returning existing/default or a
    low-confidence result leaves the established tf-devops/tf-azure-hub routing
    untouched. The backend never uses a Python keyword list to infer repository
    semantics.
    """
    explicit = _explicit_extended_repo_from_prompt(prompt)
    if explicit:
        return explicit

    normalized_prompt = re.sub(r"\s+", " ", str(prompt or "").strip())
    if not normalized_prompt:
        return ""
    cache_key = hashlib.sha256(normalized_prompt.lower().encode("utf-8")).hexdigest()
    if cache_key in _EXTENDED_REPO_CLASSIFICATION_CACHE:
        return _EXTENDED_REPO_CLASSIFICATION_CACHE[cache_key]

    catalog = [
        {
            "repo_target": target,
            "repo": cfg["repo"],
            "purpose": cfg["purpose"],
        }
        for target, cfg in _EXTENDED_AWS_REPOSITORIES.items()
    ]
    request = {
        "task": "terrabot_repository_scope_classification",
        "user_request": normalized_prompt,
        "existing_default_routes": {
            "aws_general_environment_infrastructure": "tf-devops",
            "azure_consumer_infrastructure": "tf-azure-hub",
        },
        "additional_repository_catalog": catalog,
        "instructions": [
            "Decide whether this request clearly belongs to exactly one additional repository.",
            "Infer from infrastructure semantics, not from a hardcoded keyword mapping.",
            "Ordinary AWS environment resource create/update requests stay in tf-devops.",
            "Ordinary Azure consumer changes stay in tf-azure-hub.",
            "Choose terraform-aws-vpc only for changes to the reusable VPC module implementation/API itself; environment VPC values belong in their consumer/network repository.",
            "A request may mention Azure while still targeting tf-network-resources when it changes AWS-side TGW/VPN/routes/interconnect infrastructure.",
            "If evidence is ambiguous or the default repository should remain in use, return selected_repo_target as an empty string.",
            "Return JSON only with selected_repo_target, confidence, reason.",
        ],
    }
    selected = ""
    try:
        raw = call_named_agent(json.dumps(request, ensure_ascii=False), AGENT_NAME)
        parsed = json.loads(str(raw or "{}"))
        candidate = _canonical_extended_repo_target(parsed.get("selected_repo_target"))
        confidence = float(parsed.get("confidence") or 0.0)
        if candidate and confidence >= 0.75:
            selected = candidate
            LOGGER.info(
                "[TerrabotDiag] event=extended_repository_selected repo_target=%s confidence=%.2f reason=%s",
                candidate,
                confidence,
                str(parsed.get("reason") or "")[:240],
            )
        else:
            LOGGER.info(
                "[TerrabotDiag] event=extended_repository_default_route confidence=%.2f candidate=%s",
                confidence,
                candidate or "none",
            )
    except Exception as exc:
        LOGGER.warning("[TerrabotDiag] event=extended_repository_classification_failed error=%s", exc)
        selected = ""

    _EXTENDED_REPO_CLASSIFICATION_CACHE[cache_key] = selected
    return selected


def infer_generation_workflow(prompt: str, target_cloud: str, requested_workflow: Optional[str] = None) -> str:
    if str(requested_workflow or "").strip():
        return str(requested_workflow).strip()
    if safe_normalize_cloud(target_cloud) == "aws" and _active_extended_repo_target():
        return "aws_repository_native_change"
    return _PRE_EXTENDED_INFER_GENERATION_WORKFLOW(prompt, target_cloud, requested_workflow)


def _extended_repo_live_evidence(prompt: str, repo_target: str, branch: str) -> list[dict]:
    cfg = _EXTENDED_AWS_REPOSITORIES[repo_target]
    root = str(cfg.get("root") or ".")
    terms = _infra_modification_search_terms(prompt)
    explicit_paths = set(_explicit_iac_paths_from_prompt(prompt))
    paths = github_list_tf_files_recursive(
        "aws",
        root,
        branch,
        repo_target=repo_target,
        workflow="aws_repository_native_change",
    )
    scored: list[tuple[float, str, str]] = []
    for path in paths:
        try:
            content = github_get_file_content(
                "aws",
                path,
                branch,
                repo_target=repo_target,
                workflow="aws_repository_native_change",
            )
        except Exception:
            content = None
        if not content:
            continue
        score = float(_score_infra_candidate(path, content, terms, prompt))
        if path in explicit_paths:
            score += 1000.0
        if score > 0 or not terms:
            scored.append((score, path, content))
    scored.sort(key=lambda item: (-item[0], item[1]))

    evidence: list[dict] = []
    for score, path, content in scored[:16]:
        evidence.append({
            "path": path,
            "filename": path.rsplit("/", 1)[-1],
            "content": content,
            "score": score,
            "matched_blocks": _matched_blocks_for_prompt(content, terms),
            "reason": "live GitHub repository evidence selected by semantic request relevance",
            "repo_target": repo_target,
            "repo_full_name": f"{GITHUB_OWNER}/{cfg['repo']}",
            "ref": branch,
        })
    return evidence


def build_backend_existing_infra_modification_context(
    prompt: str,
    thread_id: str,
    cloud: str,
    workflow: str,
    retrieved_value_context: list | None = None,
) -> dict:
    repo_target = normalize_repo_target(cloud, workflow=workflow)
    if repo_target not in _EXTENDED_AWS_REPOSITORIES:
        return _PRE_EXTENDED_BUILD_EXISTING_CONTEXT(
            prompt,
            thread_id,
            cloud,
            workflow,
            retrieved_value_context=retrieved_value_context,
        )

    branch = _teams_remote_context_branch("aws", repo_target, "aws_repository_native_change")
    evidence = _extended_repo_live_evidence(prompt, repo_target, branch)
    cfg = _EXTENDED_AWS_REPOSITORIES[repo_target]
    LOGGER.info(
        "[TerrabotDiag] event=extended_repository_live_scan_complete repo=%s/%s branch=%s files=%s",
        GITHUB_OWNER,
        cfg["repo"],
        branch,
        len(evidence),
    )
    return {
        "cloud": "aws",
        "workflow": "aws_repository_native_change",
        "repo_target": repo_target,
        "repo_full_name": f"{GITHUB_OWNER}/{cfg['repo']}",
        "context_ref": branch,
        "scope_root": str(cfg.get("root") or "."),
        "matched_files": evidence,
        "matched_file_paths": [item["path"] for item in evidence],
        "environment_files": evidence,
        "retrieved_value_context": list(retrieved_value_context or []),
        "selection_state": "selected" if evidence else "not_found",
        "agent_resolves_target": True,
        "repository_change_strategy": {
            "operation": "repository_native_change",
            "boolean_applicable": False,
            "reason": "Foundry must infer the repository-native Terraform workflow from complete live evidence.",
        },
        "instructions": [
            f"The backend selected repository {GITHUB_OWNER}/{cfg['repo']} from Foundry repository-scope classification.",
            f"Repository purpose: {cfg['purpose']}",
            "Infer the exact repository workflow, target files, resource/module relationships, placement, naming, and edit style from the supplied live files. Do not impose tf-devops or tf-azure-hub layout rules on this repository.",
            "For modifications, preserve unrelated live content exactly and return complete final files. For creation, clone the nearest repository-native sibling pattern and place new code where this repository places the same class of object.",
            "Do not ask the user for a Terraform path when live repository evidence can resolve it. Ask only when multiple genuinely valid semantic targets remain after reading the repository.",
            "Return repo_target='" + repo_target + "' and workflow='aws_repository_native_change'.",
        ],
    }


def validate_github_app_repository_access() -> None:
    _PRE_EXTENDED_VALIDATE_GITHUB_APP_ACCESS()
    token = get_github_app_installation_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    for target, cfg in _EXTENDED_AWS_REPOSITORIES.items():
        repo = str(cfg.get("repo") or "").strip()
        if not repo:
            continue
        response = requests.get(
            f"{GITHUB_API}/repos/{GITHUB_OWNER}/{repo}", headers=headers, timeout=30
        )
        if not response.ok:
            raise _github_request_error(
                response, f"Validating GitHub App access to {GITHUB_OWNER}/{repo}"
            )
        permissions = (response.json() or {}).get("permissions") or {}
        if not (permissions.get("push") or permissions.get("maintain") or permissions.get("admin")):
            raise PermissionError(
                f"The GitHub App can read {GITHUB_OWNER}/{repo}, but cannot push branches. "
                "Grant repository Contents: Read and write."
            )
        LOGGER.info(
            "[TerrabotDiag] event=extended_repository_access_validated repo_target=%s repo=%s/%s",
            target,
            GITHUB_OWNER,
            repo,
        )


def handle_teams_chat_request(data: dict):
    """Select added repositories before the existing Teams state machine runs."""
    request_data = dict(data or {})
    prompt = str(request_data.get("prompt") or request_data.get("message") or "").strip()
    action = str(request_data.get("action") or "").strip()
    explicit_target = _canonical_extended_repo_target(request_data.get("repo_target"))

    # Continuations already carry their workflow/repository state. New semantic
    # classification is only performed for self-contained infrastructure text.
    selected = explicit_target
    if not selected and prompt and not action and _TEAMS_SELF_CONTAINED_INFRA_ACTION_RE.search(prompt):
        selected = _foundry_select_extended_repo_target(prompt)

    token = None
    try:
        if selected:
            token = _EXTENDED_REPO_TARGET.set(selected)
            request_data["repo_target"] = selected
            request_data["cloud"] = "aws"
            request_data["requested_cloud"] = "aws"
            request_data.setdefault("mode", "infra")
            request_data["workflow"] = "aws_repository_native_change"
            LOGGER.info(
                "[TerrabotDiag] event=extended_repository_scope_enter repo_target=%s prompt=%s",
                selected,
                prompt[:160],
            )
        result, status = _PRE_EXTENDED_HANDLE_TEAMS_CHAT(request_data)
        if selected and isinstance(result, dict):
            result.setdefault("repo_target", selected)
            result.setdefault("workflow", "aws_repository_native_change")
            result.setdefault("cloud", "aws")
        return result, status
    finally:
        if token is not None:
            _EXTENDED_REPO_TARGET.reset(token)
