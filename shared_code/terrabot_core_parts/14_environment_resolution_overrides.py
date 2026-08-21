from __future__ import annotations
def _terrabot_env_text(prompt: str) -> str:
    return re.sub(r"\s+", " ", str(prompt or "").strip().lower().replace("_", "-"))


def _terrabot_env_name_pattern(name: str) -> str:
    variants = {
        str(name or "").lower(),
        str(name or "").lower().replace("_", "-"),
        str(name or "").lower().replace("_", " "),
    }
    return "(?:" + "|".join(re.escape(item) for item in sorted(variants, key=len, reverse=True) if item) + ")"


def _terrabot_prompt_has_name(text: str, name: str) -> bool:
    pattern = _terrabot_env_name_pattern(name)
    return bool(pattern and re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", text))


def _terrabot_explicit_provider_from_prompt(prompt: str) -> str:
    text = _terrabot_env_text(prompt)
    has_aws = bool(re.search(r"(?<![a-z0-9])(?:aws|amazon web services|tf-devops|tf devops)(?![a-z0-9])", text))
    has_azure = bool(re.search(r"(?<![a-z0-9])(?:azure|azurerm|tf-azure-hub|tf azure hub)(?![a-z0-9])", text))
    if has_aws and not has_azure:
        return "aws"
    if has_azure and not has_aws:
        return "azure"
    return ""


def _terrabot_environment_matches(prompt: str) -> list[dict]:
    """Return every explicit environment named by the user, without collapsing tiers."""
    text = _terrabot_env_text(prompt)
    matches: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    def add(cloud: str, tier: str, canonical: str, path: str, alias: str = "") -> None:
        key = (cloud, tier, canonical)
        if key in seen:
            return
        seen.add(key)
        matches.append({
            "cloud": cloud,
            "tier": tier,
            "environment": canonical,
            "path": path,
            "alias": alias or canonical,
            "repo_target": TERRABOT_ENVIRONMENT_CATALOG[cloud]["repo_target"],
        })

    # Azure aliases are unambiguous and intentionally checked before canonical
    # names so a short production alias such as `ca4` resolves to `prd-ca4`.
    for alias, canonical in TERRABOT_AZURE_ENVIRONMENT_ALIASES.items():
        if not _terrabot_prompt_has_name(text, alias):
            continue
        for tier in ("nonprod", "prod"):
            path = TERRABOT_ENVIRONMENT_CATALOG["azure"][tier].get(canonical)
            if path:
                add("azure", tier, canonical, path, alias=alias)

    for cloud in ("aws", "azure"):
        for tier in ("nonprod", "prod"):
            for canonical, path in TERRABOT_ENVIRONMENT_CATALOG[cloud][tier].items():
                if _terrabot_prompt_has_name(text, canonical):
                    add(cloud, tier, canonical, path)

    # `dev environment` is a tf-devops environment, not a generic synonym for
    # Azure non-production.  The exact token rule above already resolves it;
    # this explicit guard documents the routing contract and protects against
    # model-side interpretation drift.
    if re.search(r"(?<![a-z0-9])dev(?:\s+environment|\s+env)?(?![a-z0-9])", text):
        add("aws", "nonprod", "dev", TERRABOT_ENVIRONMENT_CATALOG["aws"]["nonprod"]["dev"], alias="dev")

    return matches


def _terrabot_group_request(prompt: str) -> tuple[str, str]:
    text = _terrabot_env_text(prompt)
    all_requested = bool(re.search(r"\b(?:all|every)\b", text))
    if not all_requested:
        return "", ""
    if re.search(r"\b(?:non-prod|non prod|nonprod|non-production|non production)\b", text):
        return "nonprod", "all"
    if re.search(r"\b(?:prod|production)\b", text):
        return "prod", "all"
    return "", ""


def resolve_teams_environment_targets(prompt: str, cloud_hint: str = "") -> dict:
    """Resolve repository + target environment set before Terraform discovery.

    Exact environment identity wins over model/router cloud hints.  An explicit
    provider written by the user wins only when it does not conflict with an
    explicit environment; conflicts are returned as a clarification instead of
    silently reading the wrong repository.
    """
    matches = _terrabot_environment_matches(prompt)
    explicit_provider = _terrabot_explicit_provider_from_prompt(prompt)
    hinted_cloud = safe_normalize_cloud(cloud_hint) or ""
    environment_clouds = sorted({item["cloud"] for item in matches})

    if len(environment_clouds) > 1:
        return {
            "cloud": "",
            "repo_target": "",
            "targets": matches,
            "error": "The request names environments from both AWS/tf-devops and Azure/tf-azure-hub. Specify which environment set to change.",
            "basis": "conflicting explicit environment names",
        }

    environment_cloud = environment_clouds[0] if environment_clouds else ""
    if explicit_provider and environment_cloud and explicit_provider != environment_cloud:
        return {
            "cloud": "",
            "repo_target": "",
            "targets": matches,
            "error": (
                f"The prompt explicitly names {explicit_provider.upper()} but the environment name maps to "
                f"{environment_cloud.upper()}. Correct either the cloud or environment before Terrabot changes files."
            ),
            "basis": "provider/environment conflict",
        }

    # Environment identity is stronger than a classifier/router hint. This is
    # the key fix for `disable homepage bff in dev environment`: `dev` selects
    # AWS/tf-devops even if a prior/model classification guessed Azure.
    cloud = environment_cloud or explicit_provider or hinted_cloud
    if not cloud:
        return {
            "cloud": "",
            "repo_target": "",
            "targets": [],
            "error": "",
            "basis": "cloud remains unresolved",
        }

    group_tier, group_kind = _terrabot_group_request(prompt)
    targets = [item for item in matches if item["cloud"] == cloud]
    if group_kind == "all":
        explicit_wrong_tier = [item for item in targets if item["tier"] != group_tier]
        if explicit_wrong_tier:
            return {
                "cloud": cloud,
                "repo_target": TERRABOT_ENVIRONMENT_CATALOG[cloud]["repo_target"],
                "targets": targets,
                "error": "The request mixes an all-environments tier request with an explicit environment from another tier.",
                "basis": "conflicting environment tier selection",
            }
        targets = [
            {
                "cloud": cloud,
                "tier": group_tier,
                "environment": name,
                "path": path,
                "alias": name,
                "repo_target": TERRABOT_ENVIRONMENT_CATALOG[cloud]["repo_target"],
            }
            for name, path in TERRABOT_ENVIRONMENT_CATALOG[cloud][group_tier].items()
        ]

    defaulted = False
    if not targets and not group_kind:
        # Defaults apply only after cloud is known.  They never pick a cloud.
        default_name = TERRABOT_ENVIRONMENT_CATALOG[cloud]["default_nonprod"]
        default_path = TERRABOT_ENVIRONMENT_CATALOG[cloud]["nonprod"][default_name]
        targets = [{
            "cloud": cloud,
            "tier": "nonprod",
            "environment": default_name,
            "path": default_path,
            "alias": "backend default",
            "repo_target": TERRABOT_ENVIRONMENT_CATALOG[cloud]["repo_target"],
        }]
        defaulted = True

    # `global` and `observe` intentionally exist in both AWS tiers. Require the
    # tier when the prompt does not already disambiguate it.
    if cloud == "aws" and matches:
        by_name: dict[str, set[str]] = {}
        for item in matches:
            by_name.setdefault(item["environment"], set()).add(item["tier"])
        ambiguous = [name for name, tiers in by_name.items() if len(tiers) > 1]
        if ambiguous:
            text = _terrabot_env_text(prompt)
            wants_prod = bool(re.search(r"\b(?:prod|production)\b", text))
            wants_nonprod = bool(re.search(r"\b(?:non-prod|non prod|nonprod|non-production|non production|dev-aws|dev aws)\b", text))
            if wants_prod != wants_nonprod:
                requested_tier = "prod" if wants_prod else "nonprod"
                targets = [item for item in targets if item["tier"] == requested_tier]
            else:
                return {
                    "cloud": cloud,
                    "repo_target": "tf-devops",
                    "targets": targets,
                    "error": f"AWS environment {', '.join(ambiguous)} exists in both non-prod and prod. Specify the tier.",
                    "basis": "ambiguous AWS tier",
                }

    # Stable de-duplication by concrete repository path.
    unique_targets: list[dict] = []
    seen_paths: set[str] = set()
    for target in targets:
        path = str(target.get("path") or "")
        if path and path not in seen_paths:
            seen_paths.add(path)
            unique_targets.append(target)

    return {
        "cloud": cloud,
        "repo_target": TERRABOT_ENVIRONMENT_CATALOG[cloud]["repo_target"],
        "targets": unique_targets,
        "target_environments": [item["environment"] for item in unique_targets],
        "target_paths": [item["path"] for item in unique_targets],
        "defaulted": defaulted,
        "group": group_tier if group_kind else "",
        "error": "",
        "basis": (
            "explicit environment-to-repository mapping"
            if environment_cloud else
            "explicit provider with backend default environment"
            if explicit_provider and defaulted else
            "resolved cloud with backend default environment"
        ),
    }


# Preserve the prior implementations for compatibility/fallback behavior.
_ENV_RESOLUTION_PREVIOUS_INFER_CLOUD_FROM_PROMPT = infer_cloud_from_prompt
_ENV_RESOLUTION_PREVIOUS_RESOLVE_AWS_ENVIRONMENT_PATH = resolve_aws_environment_path
_ENV_RESOLUTION_PREVIOUS_TEAMS_REQUESTED_AWS_PATHS = _teams_requested_aws_environment_paths
_ENV_RESOLUTION_PREVIOUS_AZURE_EXACT_CANDIDATES = _azure_exact_environment_tfvars_candidates
_ENV_RESOLUTION_PREVIOUS_AZURE_TFVARS_RESOLVER = resolve_azure_consumer_tfvars_path
_ENV_RESOLUTION_PREVIOUS_NORMALIZE_ROUTER_DECISION = normalize_router_decision
_ENV_RESOLUTION_PREVIOUS_BUILD_AGENT_INPUT = build_agent_input_for_infra
_ENV_RESOLUTION_PREVIOUS_SAFE_REQUEST_CLOUD = _teams_safe_request_cloud


def infer_cloud_from_environment(prompt: str):
    matches = _terrabot_environment_matches(prompt)
    clouds = {item["cloud"] for item in matches}
    return next(iter(clouds)) if len(clouds) == 1 else None


def infer_cloud_from_prompt(prompt: str):
    resolution = resolve_teams_environment_targets(prompt)
    if resolution.get("cloud"):
        return resolution["cloud"]
    explicit = _terrabot_explicit_provider_from_prompt(prompt)
    if explicit:
        return explicit
    # Retain existing service/resource marker behavior only when no environment
    # or explicit provider resolved the repository.
    return _ENV_RESOLUTION_PREVIOUS_INFER_CLOUD_FROM_PROMPT(prompt)


def _teams_safe_request_cloud(prompt: str) -> str:
    resolution = resolve_teams_environment_targets(prompt)
    if resolution.get("cloud"):
        return str(resolution["cloud"])
    return _ENV_RESOLUTION_PREVIOUS_SAFE_REQUEST_CLOUD(prompt)


def normalize_router_decision(prompt, requested_mode, requested_cloud, recovered_state, thread_id=None):
    decision = _ENV_RESOLUTION_PREVIOUS_NORMALIZE_ROUTER_DECISION(
        prompt,
        requested_mode,
        requested_cloud,
        recovered_state,
        thread_id=thread_id,
    )
    resolution = resolve_teams_environment_targets(prompt, cloud_hint=requested_cloud or "")
    if resolution.get("error"):
        if (requested_mode or "").strip().lower() == "infra":
            return NormalizedRouterDecision(
                request_type="infra",
                cloud=None,
                workflow="clarification_required",
                reason=str(resolution["error"]),
            )
        return decision
    if resolution.get("cloud"):
        decision.cloud = str(resolution["cloud"])
        decision.reason = (
            f"Environment routing selected {resolution.get('repo_target')} from {resolution.get('basis')}. "
            f"Targets: {', '.join(resolution.get('target_environments') or [])}."
        )
    return decision


def _teams_requested_aws_environment_paths(prompt: str, branch: str = "") -> list[str]:
    resolution = resolve_teams_environment_targets(prompt, cloud_hint="aws")
    if resolution.get("cloud") == "aws" and not resolution.get("error"):
        paths = [str(item.get("path") or "").strip("/") for item in resolution.get("targets") or []]
        if paths:
            return list(dict.fromkeys(paths))
    return _ENV_RESOLUTION_PREVIOUS_TEAMS_REQUESTED_AWS_PATHS(prompt, branch=branch)


def resolve_aws_environment_path(
    prompt: str,
    retrieved_value_context: list | None = None,
    current_environment_path: str | None = None,
):
    resolution = resolve_teams_environment_targets(prompt, cloud_hint="aws")
    if resolution.get("error"):
        return None, str(resolution["error"])
    if resolution.get("cloud") == "aws" and resolution.get("targets"):
        # Singular legacy callers keep one state folder, while plural evidence
        # and generated absolute terraform/... paths cover every target. Never
        # replace an explicit environment with stale thread state.
        return str(resolution["targets"][0]["path"]), None
    return _ENV_RESOLUTION_PREVIOUS_RESOLVE_AWS_ENVIRONMENT_PATH(
        prompt,
        retrieved_value_context=retrieved_value_context,
        current_environment_path=current_environment_path,
    )


def _azure_exact_environment_tfvars_candidates(prompt: str) -> tuple[list[str], str]:
    resolution = resolve_teams_environment_targets(prompt, cloud_hint="azure")
    if resolution.get("error") or resolution.get("cloud") != "azure":
        return _ENV_RESOLUTION_PREVIOUS_AZURE_EXACT_CANDIDATES(prompt)
    targets = resolution.get("targets") or []
    if len(targets) != 1:
        return [], ""
    target = targets[0]
    root = str(target.get("path") or "").strip("/")
    env_name = str(target.get("environment") or "")
    if not root:
        return [], ""
    kind = _azure_tfvars_file_kind_from_prompt(prompt)
    preferred = f"{root}/{kind}.tfvars"
    fallback = f"{root}/hub.tfvars" if kind == "dr" else f"{root}/dr.tfvars"
    return [preferred, fallback], env_name


def resolve_azure_consumer_tfvars_path(
    prompt: str,
    retrieved_value_context: list | None = None,
    context_ref: str = "",
) -> tuple[str, str]:
    # Preserve an explicit backend-routed/user path first.
    for item in retrieved_value_context or []:
        if not isinstance(item, dict):
            continue
        explicit_path = str(item.get("target_tfvars_filename") or item.get("tfvars_path") or "").strip()
        if explicit_path.startswith("vars/") and explicit_path.endswith(".tfvars"):
            return explicit_path, str(item.get("azure_environment") or explicit_path.split("/")[1])
    explicit_prompt_path = _explicit_tfvars_path_from_prompt(prompt)
    if explicit_prompt_path:
        return _ENV_RESOLUTION_PREVIOUS_AZURE_TFVARS_RESOLVER(
            prompt,
            retrieved_value_context=retrieved_value_context,
            context_ref=context_ref,
        )

    resolution = resolve_teams_environment_targets(prompt, cloud_hint="azure")
    if resolution.get("error"):
        raise ValueError(str(resolution["error"]))
    targets = resolution.get("targets") or []
    if len(targets) == 1:
        root = str(targets[0].get("path") or "").strip("/")
        env_name = str(targets[0].get("environment") or "")
        ref = (context_ref or "").strip() or github_branch_seed_for_cloud(
            "azure", repo_target="tf-azure-hub", workflow="azure_consumer_generation"
        )
        kind = _azure_tfvars_file_kind_from_prompt(prompt)
        candidates = [f"{root}/{kind}.tfvars"]
        if kind == "dr":
            candidates.append(f"{root}/hub.tfvars")
        matched = _first_existing_tf_azure_hub_tfvars_path(candidates, ref)
        if matched:
            return matched, env_name
        raise ValueError(
            f"Azure environment {env_name} resolved to tf-azure-hub/{root}, but no expected {kind}.tfvars file exists on the live repository ref."
        )
    if len(targets) > 1:
        raise ValueError(
            "This operation targets multiple Azure environments. Generate one environment-specific tfvars edit per resolved target instead of collapsing them into a single tfvars path."
        )
    return _ENV_RESOLUTION_PREVIOUS_AZURE_TFVARS_RESOLVER(
        prompt,
        retrieved_value_context=retrieved_value_context,
        context_ref=context_ref,
    )


def build_agent_input_for_infra(
    prompt: str,
    thread_id: str,
    selected_cloud: Optional[str] = None,
    workflow: Optional[str] = None,
    retrieved_module_context: Optional[list] = None,
    retrieved_value_context: Optional[list] = None,
) -> str:
    resolution = resolve_teams_environment_targets(prompt, cloud_hint=selected_cloud or "")
    effective_cloud = resolution.get("cloud") or selected_cloud
    raw = _ENV_RESOLUTION_PREVIOUS_BUILD_AGENT_INPUT(
        prompt,
        thread_id,
        selected_cloud=effective_cloud,
        workflow=workflow,
        retrieved_module_context=retrieved_module_context,
        retrieved_value_context=retrieved_value_context,
    )
    try:
        payload = json.loads(raw)
    except Exception:
        return raw

    payload["backend_environment_resolution"] = resolution
    payload["instructions"] = list(payload.get("instructions") or []) + [
        "BACKEND ENVIRONMENT RESOLUTION IS AUTHORITATIVE (HARD): use backend_environment_resolution before repository/module/flag discovery. Never switch repositories because a resource name sounds like another cloud.",
        "When target environment `dev` is resolved, use AWS repository tf-devops and terraform/dev_aws/dev. Do not use tf-azure-hub for that turn unless the user explicitly corrects the cloud/environment conflict.",
        "Azure non-prod targets are npr-int, npr-stg, and sbx-infra; `sandbox` maps to sbx-infra. Azure prod aliases ca4/eu3/us5/us6 map to prd-ca4/prd-eu3/prd-us5/prd-us6.",
        "AWS non-prod targets are under terraform/dev_aws; AWS prod targets are under terraform/prod_aws (plus terraform/root/global where explicitly named).",
        "If the user names multiple environments, files[] must contain the complete valid change for every backend_environment_resolution.targets entry. Never collapse the set to the first target.",
        "If the user says all/every prod or all/every non-prod for the resolved cloud, apply the request to every target in backend_environment_resolution.targets.",
        "If no environment was named after cloud resolution, use the backend default target: AWS minidev; Azure sbx-infra. Do not ask the user to confirm these defaults.",
        "Do not ask which repository or environment to use when backend_environment_resolution has one or more targets and no error. Ask only when backend_environment_resolution.error is non-empty or repository evidence reveals a genuine target ambiguity inside those environments.",
    ]
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

# Keep legacy token consumers synchronized with the unified catalog. These sets
# are hints only; target paths still come from resolve_teams_environment_targets.
TEAMS_AWS_ENVIRONMENT_HINTS.update(
    name
    for tier in ("nonprod", "prod")
    for name in TERRABOT_ENVIRONMENT_CATALOG["aws"][tier]
)
TEAMS_AZURE_ENVIRONMENT_HINTS.update(
    name
    for tier in ("nonprod", "prod")
    for name in TERRABOT_ENVIRONMENT_CATALOG["azure"][tier]
)
TEAMS_AZURE_ENVIRONMENT_HINTS.update(TERRABOT_AZURE_ENVIRONMENT_ALIASES)
