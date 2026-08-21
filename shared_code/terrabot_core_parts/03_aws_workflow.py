from __future__ import annotations
AWS_PROD_ENV_FOLDERS = {
    "us1": "terraform/prod_aws/us1",
    "us1_dr": "terraform/prod_aws/us1_dr",
    "us2": "terraform/prod_aws/us2",
    "us2_dr": "terraform/prod_aws/us2_dr",
    "us3": "terraform/prod_aws/us3",
    "us3_dr": "terraform/prod_aws/us3_dr",
    "us4": "terraform/prod_aws/us4",
    "us4_dr": "terraform/prod_aws/us4_dr",
    "ca3": "terraform/prod_aws/ca3",
    "ca3_dr": "terraform/prod_aws/ca3_dr",
    "eu1": "terraform/prod_aws/eu1",
    "eu1_dr": "terraform/prod_aws/eu1_dr",
    "eu2": "terraform/prod_aws/eu2",
    "eu2_dr": "terraform/prod_aws/eu2_dr",
    "global": "terraform/prod_aws/global",
    "devops": "terraform/prod_aws/devops",
    "sqlstaging": "terraform/prod_aws/sqlstaging",
    "sqlstaging_ca": "terraform/prod_aws/sqlstaging_ca",
    "sqlstaging_eu": "terraform/prod_aws/sqlstaging_eu",
    "sqlstaging_eu2": "terraform/prod_aws/sqlstaging_eu2",
    "sqlstaging_us4": "terraform/prod_aws/sqlstaging_us4",
    "sqlstaging_west": "terraform/prod_aws/sqlstaging_west",
}

AWS_DEV_ENV_FOLDERS = {
    "dev": "terraform/dev_aws/dev",
    "minidev": "terraform/dev_aws/minidev",
    "bolt": "terraform/dev_aws/bolt",
    "bolt_dr": "terraform/dev_aws/bolt_dr",
    "bolt_sqlstaging": "terraform/dev_aws/bolt_sqlstaging",
    "dev_devops": "terraform/dev_aws/dev_devops",
    "dev_sqlstaging": "terraform/dev_aws/dev_sqlstaging",
    "global": "terraform/dev_aws/global",
    "minidev_sqlstaging": "terraform/dev_aws/minidev_sqlstaging",
}

AWS_EXACT_ENV_ALIASES = {
    AWS_DEV_ENV_FOLDERS["minidev"]: [
        "terraform/dev_aws/minidev",
        "minidev",
        "mini dev",
    ],
    AWS_DEV_ENV_FOLDERS["dev"]: [
        "terraform/dev_aws/dev",
        "dev",
    ],
    AWS_DEV_ENV_FOLDERS["bolt"]: [
        "terraform/dev_aws/bolt",
        "bolt",
        "perf",
        "bolt perf",
    ],
    AWS_DEV_ENV_FOLDERS["bolt_dr"]: [
        "terraform/dev_aws/bolt_dr",
        "bolt dr",
        "bolt_dr",
        "bolt disaster recovery",
        "bolt failover",
    ],
    AWS_DEV_ENV_FOLDERS["bolt_sqlstaging"]: [
        "terraform/dev_aws/bolt_sqlstaging",
        "bolt sqlstaging",
        "bolt_sqlstaging",
    ],
    AWS_DEV_ENV_FOLDERS["dev_devops"]: [
        "terraform/dev_aws/dev_devops",
        "dev devops",
        "dev_devops",
    ],
    AWS_DEV_ENV_FOLDERS["dev_sqlstaging"]: [
        "terraform/dev_aws/dev_sqlstaging",
        "dev sqlstaging",
        "dev_sqlstaging",
    ],
    AWS_DEV_ENV_FOLDERS["minidev_sqlstaging"]: [
        "terraform/dev_aws/minidev_sqlstaging",
        "minidev sqlstaging",
        "minidev_sqlstaging",
    ],

    AWS_PROD_ENV_FOLDERS["us1_dr"]: [
        "terraform/prod_aws/us1_dr",
        "us1 dr",
        "us1_dr",
        "us1 disaster recovery",
        "us1 failover",
    ],
    AWS_PROD_ENV_FOLDERS["us1"]: [
        "terraform/prod_aws/us1",
        "us1",
        "prod us1",
    ],

    AWS_PROD_ENV_FOLDERS["us2_dr"]: [
        "terraform/prod_aws/us2_dr",
        "us2 dr",
        "us2_dr",
        "us2 disaster recovery",
        "us2 failover",
    ],
    AWS_PROD_ENV_FOLDERS["us2"]: [
        "terraform/prod_aws/us2",
        "us2",
        "prod us2",
    ],

    AWS_PROD_ENV_FOLDERS["us3_dr"]: [
        "terraform/prod_aws/us3_dr",
        "us3 dr",
        "us3_dr",
        "us3 disaster recovery",
        "us3 failover",
        "us-east-2",
        "ohio",
    ],
    AWS_PROD_ENV_FOLDERS["us3"]: [
        "terraform/prod_aws/us3",
        "us3",
        "prod us3",
        "us-west-2",
        "oregon",
    ],

    AWS_PROD_ENV_FOLDERS["us4_dr"]: [
        "terraform/prod_aws/us4_dr",
        "us4 dr",
        "us4_dr",
        "us4 disaster recovery",
        "us4 failover",
    ],
    AWS_PROD_ENV_FOLDERS["us4"]: [
        "terraform/prod_aws/us4",
        "us4",
        "prod us4",
    ],

    AWS_PROD_ENV_FOLDERS["ca3_dr"]: [
        "terraform/prod_aws/ca3_dr",
        "ca3 dr",
        "ca3_dr",
        "ca dr",
        "ca region dr",
        "canada dr",
        "canadian dr",
        "ca-central-1 dr",
        "ca-west-1",
        "calgary",
    ],
    AWS_PROD_ENV_FOLDERS["ca3"]: [
        "terraform/prod_aws/ca3",
        "ca3",
        "prod ca3",
        "ca region",
        "canada",
        "canadian region",
        "ca-central-1",
        "montreal",
    ],

    AWS_PROD_ENV_FOLDERS["eu1_dr"]: [
        "terraform/prod_aws/eu1_dr",
        "eu1 dr",
        "eu1_dr",
        "eu1 disaster recovery",
        "eu1 failover",
    ],
    AWS_PROD_ENV_FOLDERS["eu1"]: [
        "terraform/prod_aws/eu1",
        "eu1",
        "prod eu1",
    ],

    AWS_PROD_ENV_FOLDERS["eu2_dr"]: [
        "terraform/prod_aws/eu2_dr",
        "eu2 dr",
        "eu2_dr",
        "eu2 disaster recovery",
        "eu2 failover",
    ],
    AWS_PROD_ENV_FOLDERS["eu2"]: [
        "terraform/prod_aws/eu2",
        "eu2",
        "prod eu2",
    ],

    AWS_PROD_ENV_FOLDERS["global"]: [
        "terraform/prod_aws/global",
        "prod global",
        "global prod",
    ],
    AWS_PROD_ENV_FOLDERS["devops"]: [
        "terraform/prod_aws/devops",
        "prod devops",
        "devops prod",
    ],
    AWS_PROD_ENV_FOLDERS["sqlstaging"]: [
        "terraform/prod_aws/sqlstaging",
        "prod sqlstaging",
        "sqlstaging prod",
    ],
}

AWS_AMBIGUOUS_ENV_ALIASES = {
    "us-east-1": [
        AWS_PROD_ENV_FOLDERS["us1"],
        AWS_PROD_ENV_FOLDERS["us2"],
        AWS_PROD_ENV_FOLDERS["us4"],
    ],
    "virginia": [
        AWS_PROD_ENV_FOLDERS["us1"],
        AWS_PROD_ENV_FOLDERS["us2"],
        AWS_PROD_ENV_FOLDERS["us4"],
    ],
    "us-west-1": [
        AWS_PROD_ENV_FOLDERS["us1_dr"],
        AWS_PROD_ENV_FOLDERS["us2_dr"],
        AWS_PROD_ENV_FOLDERS["us4_dr"],
    ],
    "california": [
        AWS_PROD_ENV_FOLDERS["us1_dr"],
        AWS_PROD_ENV_FOLDERS["us2_dr"],
        AWS_PROD_ENV_FOLDERS["us4_dr"],
    ],
    "eu-west-1": [
        AWS_PROD_ENV_FOLDERS["eu1"],
        AWS_PROD_ENV_FOLDERS["eu2"],
    ],
    "ireland": [
        AWS_PROD_ENV_FOLDERS["eu1"],
        AWS_PROD_ENV_FOLDERS["eu2"],
    ],
    "eu-west-2": [
        AWS_PROD_ENV_FOLDERS["eu1_dr"],
        AWS_PROD_ENV_FOLDERS["eu2_dr"],
    ],
    "london": [
        AWS_PROD_ENV_FOLDERS["eu1_dr"],
        AWS_PROD_ENV_FOLDERS["eu2_dr"],
    ],
    "eu region": [
        AWS_PROD_ENV_FOLDERS["eu1"],
        AWS_PROD_ENV_FOLDERS["eu2"],
    ],
    "europe": [
        AWS_PROD_ENV_FOLDERS["eu1"],
        AWS_PROD_ENV_FOLDERS["eu2"],
    ],
}


def _aws_alias_pattern(alias: str) -> str:
    return rf"(?<![a-z0-9]){re.escape(alias.lower())}(?![a-z0-9])"


def _aws_alias_in_text(text: str, alias: str) -> bool:
    return re.search(_aws_alias_pattern(alias), text) is not None


def _best_env_path_from_aliases(text: str, alias_map: dict[str, list[str]]) -> str | None:
    best_path = None
    best_start = -1
    best_len = -1

    for path, aliases in alias_map.items():
        for alias in aliases:
            for match in re.finditer(_aws_alias_pattern(alias), text):
                start = match.start()
                alias_len = len(alias)
                if start > best_start or (start == best_start and alias_len > best_len):
                    best_path = path
                    best_start = start
                    best_len = alias_len

    return best_path




def detect_explicit_aws_environment(prompt: str):
    text = (prompt or "").strip().lower()

    # root/global is a real tf-devops area and must not fall through to minidev.
    if (
        "terraform/root/global" in text
        or "root/global" in text
        or re.search(r"(?<![a-z0-9])root[ _-]+global(?![a-z0-9])", text)
        or re.search(r"(?<![a-z0-9])global[ _-]+root(?![a-z0-9])", text)
    ):
        return "terraform/root/global", None

    # non-prod first
    if "minidev sqlstaging" in text or "minidev_sqlstaging" in text:
        return AWS_DEV_ENV_FOLDERS["minidev_sqlstaging"], None
    if "bolt sqlstaging" in text or "bolt_sqlstaging" in text:
        return AWS_DEV_ENV_FOLDERS["bolt_sqlstaging"], None
    if "dev sqlstaging" in text or "dev_sqlstaging" in text:
        return AWS_DEV_ENV_FOLDERS["dev_sqlstaging"], None
    if "dev devops" in text or "dev_devops" in text:
        return AWS_DEV_ENV_FOLDERS["dev_devops"], None
    if "bolt dr" in text or "bolt_dr" in text:
        return AWS_DEV_ENV_FOLDERS["bolt_dr"], None

    # "global" is its own real environment folder (terraform/dev_aws/global or
    # terraform/prod_aws/global) and must never fall through to the minidev
    # default just because no other environment keyword matched. Without this
    # check, a prompt such as "disable mcp waf rules in dev_aws global" fell
    # all the way to resolve_aws_environment_path's minidev fallback because
    # neither "minidev", "bolt", nor a standalone "dev" token matched.
    if re.search(r"\bglobal\b", text):
        if re.search(r"\bprod(?:uction)?\b", text):
            return AWS_PROD_ENV_FOLDERS["global"], None
        return AWS_DEV_ENV_FOLDERS["global"], None

    if re.search(r"\bminidev\b", text):
        return AWS_DEV_ENV_FOLDERS["minidev"], None
    if re.search(r"\bbolt\b", text):
        return AWS_DEV_ENV_FOLDERS["bolt"], None
    if re.search(r"\bdev\b", text):
        return AWS_DEV_ENV_FOLDERS["dev"], None

    # prod special folders
    if "sqlstaging_ca" in text or "sqlstaging ca" in text:
        return AWS_PROD_ENV_FOLDERS["sqlstaging_ca"], None
    if "sqlstaging_eu2" in text or "sqlstaging eu2" in text:
        return AWS_PROD_ENV_FOLDERS["sqlstaging_eu2"], None
    if "sqlstaging_eu" in text or "sqlstaging eu" in text:
        return AWS_PROD_ENV_FOLDERS["sqlstaging_eu"], None
    if "sqlstaging_us4" in text or "sqlstaging us4" in text:
        return AWS_PROD_ENV_FOLDERS["sqlstaging_us4"], None
    if "sqlstaging_west" in text or "sqlstaging west" in text:
        return AWS_PROD_ENV_FOLDERS["sqlstaging_west"], None
    if "sqlstaging" in text:
        return AWS_PROD_ENV_FOLDERS["sqlstaging"], None
    if "prod devops" in text or "devops prod" in text:
        return AWS_PROD_ENV_FOLDERS["devops"], None

    dr_requested = any(term in text for term in [
        " dr ", "dr ", " disaster recovery", " failover", " secondary region"
    ])

    # Canada
    if any(term in text for term in ["ca3", "ca region", "canada", "ca-central-1", "montreal"]):
        return (f"terraform/prod_aws/ca3_dr" if dr_requested else "terraform/prod_aws/ca3"), None
    if any(term in text for term in ["calgary", "ca-west-1"]):
        return "terraform/prod_aws/ca3_dr", None

    # US3 mapping
    if any(term in text for term in ["us-west-2", "oregon", "us3"]):
        return (f"terraform/prod_aws/us3_dr" if dr_requested else "terraform/prod_aws/us3"), None
    if any(term in text for term in ["us-east-2", "ohio"]):
        return "terraform/prod_aws/us3_dr", None

    # EU
    if any(term in text for term in ["eu-west-1", "ireland", "eu1"]):
        return (f"terraform/prod_aws/eu1_dr" if dr_requested else "terraform/prod_aws/eu1"), None
    if any(term in text for term in ["eu-west-2", "london", "eu2"]):
        return (f"terraform/prod_aws/eu2_dr" if dr_requested else "terraform/prod_aws/eu2"), None

    # direct prod region ids
    if re.search(r"\bus1\b", text):
        return (f"terraform/prod_aws/us1_dr" if dr_requested else "terraform/prod_aws/us1"), None
    if re.search(r"\bus2\b", text):
        return (f"terraform/prod_aws/us2_dr" if dr_requested else "terraform/prod_aws/us2"), None
    if re.search(r"\bus4\b", text):
        return (f"terraform/prod_aws/us4_dr" if dr_requested else "terraform/prod_aws/us4"), None

    # ambiguous aliases
    if any(term in text for term in ["virginia", "us-east-1"]):
        return None, (
            "The AWS region maps to more than one supported prod folder. "
            "Please specify one of: terraform/prod_aws/us1, terraform/prod_aws/us2, terraform/prod_aws/us4."
        )

    if any(term in text for term in ["eu region", "europe"]):
        return None, (
            "The AWS EU region maps to more than one supported prod folder. "
            "Please specify one of: terraform/prod_aws/eu1 or terraform/prod_aws/eu2."
        )

    return None, None


def resolve_aws_environment_path(
    prompt: str,
    retrieved_value_context: list | None = None,
    current_environment_path: str | None = None,
):
    retrieved_value_context = retrieved_value_context or []
    text = (prompt or "").strip().lower()

    explicit_path, explicit_error = detect_explicit_aws_environment(prompt)
    if explicit_error:
        return None, explicit_error
    if explicit_path:
        return explicit_path, None

    if current_environment_path:
        return current_environment_path, None

    for item in retrieved_value_context:
        env_path = (item or {}).get("environment_path")
        if isinstance(env_path, str) and env_path.startswith("terraform/"):
            return env_path, None

    # IMPORTANT: check non-prod before prod
    if "non prod" in text or "non-prod" in text or "nonprod" in text:
        return "terraform/dev_aws/minidev", None

    if "prod" in text or "production" in text:
        return "terraform/prod_aws/us1", None

    return "terraform/dev_aws/minidev", None

def get_or_create_thread_pr_state(thread_id: str, cloud: str, repo_target: Optional[str] = None, workflow: Optional[str] = None, prompt: str = ""):
    del prompt

    ensure_thread_meta(thread_id)

    cloud = normalize_cloud(cloud)
    repo_target = normalize_repo_target(cloud, repo_target, workflow)
    bucket = state_bucket_for_target(cloud, repo_target, workflow)

    thread_state = THREAD_PR_STATE[thread_id]
    existing = thread_state.get(bucket) or recover_cloud_state(thread_id, cloud, repo_target=repo_target, workflow=workflow)

    if existing and existing.get("has_open_pr") and github_branch_exists(cloud, existing["branch"], repo_target=repo_target, workflow=workflow):
        thread_state[bucket] = existing
        return existing

    next_cycle = 1
    if existing and existing.get("cycle"):
        next_cycle = int(existing["cycle"])
        if existing.get("latest_pr_state") in {"closed"} or existing.get("latest_pr_merged"):
            next_cycle += 1

    new_state = {
        "branch": build_branch_name(thread_id, cloud, next_cycle, repo_target=repo_target, workflow=workflow),
        "pr_number": existing.get("pr_number") if existing and existing.get("has_open_pr") else None,
        "pr_url": existing.get("pr_url") if existing and existing.get("has_open_pr") else None,
        "cloud": cloud,
        "repo_target": repo_target,
        "state_bucket": bucket,
        "folder": build_stable_folder(thread_id, cloud, repo_target=repo_target, workflow=workflow),
        "cycle": next_cycle,
        "has_open_pr": bool(existing and existing.get("has_open_pr")),
        "latest_pr_state": existing.get("latest_pr_state") if existing else None,
        "latest_pr_merged": existing.get("latest_pr_merged") if existing else False,
    }

    if existing and existing.get("environment_path"):
        new_state["environment_path"] = existing["environment_path"]

    thread_state[bucket] = new_state
    return new_state

def validate_generated_file_path(cloud: str, filename: str) -> str:
    forbidden_prefixes = ("changes/", "temp/", "generated/", "scratch/")
    if filename.startswith(forbidden_prefixes):
        raise ValueError(f"Invalid generated path: {filename}")

    if cloud == "azure":
        # allow repo-root tf files for tf-azure-hub
        if filename.endswith(".tf") and "/" not in filename:
            return filename
        if filename.startswith("tf-azure-hub/") or filename.startswith("vena_repos/"):
            return filename
        raise ValueError(f"Azure filename must be repo-aligned: {filename}")

    if cloud == "aws":
        if filename.startswith("terraform/"):
            return filename
        raise ValueError(f"AWS filename must stay under terraform/: {filename}")

    raise ValueError(f"Unsupported cloud for generated file validation: {cloud}")

def validate_azure_output(output, rag_context):
    files = output.get("files", [])
    names = [f["filename"] for f in files]

    if any("/changes/" in n or n.startswith("changes/") for n in names):
        return False, "Synthetic changes path is not allowed"

    linux_vm_module_exists = "tf_module_azure_linux_vm" in rag_context
    if linux_vm_module_exists:
        bad = [n for n in names if "linux_vm/main.tf" in n or "azure_module" in n]
        if bad:
            return False, "Existing Azure Linux VM module found; should emit tf-azure-hub consumer usage instead of new module source files"

    return True, None


def extract_module_repo_target_from_agent_result(agent_result: dict) -> tuple[str, str]:
    candidates = [
        agent_result.get("target_module_repo_full_name"),
        agent_result.get("module_repo_full_name"),
        agent_result.get("repo_full_name"),
    ]

    for candidate in candidates:
        value = (candidate or "").strip()
        if "/" in value:
            owner, repo = value.split("/", 1)
            if owner and repo:
                return owner.strip(), repo.strip()

    repo_name = (
        agent_result.get("target_module_repo_name")
        or agent_result.get("module_repo_name")
        or agent_result.get("repo_name")
        or ""
    ).strip()

    if repo_name:
        return _require_setting(GITHUB_OWNER, "GITHUB_OWNER"), repo_name

    raise RuntimeError(
        "azure_module_repo_population requires target_module_repo_full_name "
        "or target_module_repo_name in the generated infrastructure payload."
    )


def enrich_agent_result_with_module_repo_target(agent_result: dict, retrieved_module_context: list) -> dict:
    if not isinstance(agent_result, dict):
        return agent_result

    workflow = agent_result.get("workflow")
    if workflow != "azure_module_repo_population":
        return agent_result

    if agent_result.get("target_module_repo_full_name") or agent_result.get("target_module_repo_name"):
        return agent_result

    for item in retrieved_module_context or []:
        if not isinstance(item, dict):
            continue

        repo_full_name = item.get("repo_full_name")
        repo_name = item.get("repo_name")
        repo_owner = item.get("repo_owner") or GITHUB_OWNER

        if repo_full_name:
            agent_result["target_module_repo_full_name"] = repo_full_name
            return agent_result

        if repo_name:
            agent_result["target_module_repo_full_name"] = f"{repo_owner}/{repo_name}"
            agent_result["target_module_repo_name"] = repo_name
            return agent_result

    return agent_result

def commit_azure_module_repo_population_files(
    agent_result: dict,
    prompt: str,
    thread_id: str,
    jira_ticket: Optional[str] = None,
    ticket_link: Optional[str] = None,
    ticket_title: Optional[str] = None,
):
    agent_result = validate_azure_module_population_core_files(agent_result)

    owner, repo = extract_module_repo_target_from_agent_result(agent_result)

    repo_metadata = github_get_repo(owner, repo)
    if not repo_metadata:
        raise RuntimeError(f"Verified Azure module repo was not found: {owner}/{repo}")

    base_branch = repo_metadata.get("default_branch") or GITHUB_AZURE_BASE_BRANCH
    branch_prefix = f"{GITHUB_PR_SOURCE_BRANCH_AZURE}-azure-module-population-{stable_thread_key(thread_id)}"
    branch_name = branch_prefix

    existing_pr = github_find_pr_by_branch_by_repo(
        owner=owner,
        repo=repo,
        branch_name=branch_name,
        base_branch=base_branch,
        state="open",
    )

    branch_exists = github_branch_exists_by_repo(owner, repo, branch_name)

    if not existing_pr and not branch_exists:
        base_sha = github_get_base_branch_sha_by_repo(owner, repo, base_branch)
        github_create_branch_by_repo(owner, repo, branch_name, base_sha)

    committed_files = []

    for file_data in agent_result.get("files") or []:
        relative_path = normalize_azure_module_repo_population_path(file_data["filename"])

        if relative_path.startswith(("terraform/", "tf-azure-hub/", "vena-repos/", "changes/")):
            raise ValueError(
                f"Invalid module repo population path: {relative_path}. "
                "Module repo population files must be relative to the module repo root."
            )

        write_result = github_put_file_if_changed_by_repo(
            owner=owner,
            repo=repo,
            path=relative_path,
            content=file_data["content"],
            branch=branch_name,
            commit_message=f"[AZURE] Populate module repo file {relative_path}",
        )

        if write_result["changed"]:
            committed_files.append(relative_path)

    if existing_pr:
        pr = existing_pr
        action = "updated" if committed_files else "noop"
        message = "Existing module repo PR updated successfully." if committed_files else "No Terraform changes were detected, so no new commit was added."
    else:
        if not committed_files:
            raise RuntimeError(
                "No module repo file changes were detected, so no PR was created."
            )

        pr_body = build_pr_body(
            user_prompt=prompt,
            ticket_link=ticket_link,
            ticket_number=jira_ticket,
            ticket_title=ticket_title,
            cloud="azure",
            folder=f"{owner}/{repo}",
            thread_id=thread_id,
            branch_cycle=1,
            files=committed_files,
            summary=agent_result.get("summary") or "Populate Azure module repository",
        )

        pr = github_create_pull_request_by_repo(
            owner=owner,
            repo=repo,
            branch_name=branch_name,
            base_branch=base_branch,
            title=agent_result.get("title") or "[AZURE] Populate module repository",
            body=pr_body,
        )

        action = "created"
        message = "Module repo PR created successfully."

    ensure_thread_meta(thread_id)
    THREAD_PR_STATE[thread_id]["azure_module_population"] = {
        "branch": branch_name,
        "pr_number": pr.get("number"),
        "pr_url": pr.get("html_url"),
        "cloud": "azure",
        "repo_target": AZURE_MODULE_REPO_TARGET,
        "state_bucket": "azure_module_population",
        "folder": f"{owner}/{repo}",
        "cycle": 1,
        "has_open_pr": True,
        "latest_pr_state": pr.get("state"),
        "latest_pr_merged": bool(pr.get("merged_at")),
        "target_module_repo_owner": owner,
        "target_module_repo_name": repo,
        "target_module_repo_full_name": f"{owner}/{repo}",
        "workflow": "azure_module_repo_population",
        "original_prompt": prompt,
        "ticket_number": jira_ticket,
        "ticket_link": ticket_link,
        "ticket_title": ticket_title,
        "base_branch": base_branch,
    }

    set_last_selected_cloud(thread_id, "azure")

    return {
        "cloud": "azure",
        "repo_target": AZURE_MODULE_REPO_TARGET,
        "state_bucket": "azure_module_population",
        "folder": f"{owner}/{repo}",
        "branch": branch_name,
        "files": committed_files,
        "pr_url": pr.get("html_url"),
        "pr_number": pr.get("number"),
        "pr_title": agent_result.get("title") or "[AZURE] Populate module repository",
        "jira_ticket": jira_ticket,
        "ticket_link": ticket_link,
        "ticket_title": ticket_title,
        "message": message,
        "action": action,
        "target_module_repo_owner": owner,
        "target_module_repo_name": repo,
        "target_module_repo_full_name": f"{owner}/{repo}",
    }
def _extract_tf_variable_names_from_text(tf_content: str) -> list[str]:
    if not tf_content:
        return []

    import re

    seen = set()
    result = []

    for name in re.findall(r'variable\s+"([^"]+)"', tf_content, re.IGNORECASE):
        if name not in seen:
            seen.add(name)
            result.append(name)

    return result

def _extract_required_variable_names_from_text(tf_content: str) -> list[str]:
    if not tf_content:
        return []

    import re

    required = []

    for match in re.finditer(r'variable\s+"([^"]+)"\s*\{', tf_content, re.IGNORECASE):
        var_name = match.group(1)

        # grab small block safely
        block = tf_content[match.start(): match.start() + 300]

        if "default" not in block:
            required.append(var_name)

    return list(set(required))


AWS_MODULES_ROOT = "terraform/modules"
AWS_MODULE_VARIABLE_FILENAMES = ("vars.tf", "variables.tf")


def _aws_module_variable_filename_from_path(path: str) -> str:
    name = (path or "").strip().replace("\\", "/").rsplit("/", 1)[-1].lower()
    return name if name in AWS_MODULE_VARIABLE_FILENAMES else ""


def detect_aws_module_variable_file_convention(prompt: str = "") -> dict:
    """Detect the tf-devops module variable file convention from live GitHub.

    vars.tf and variables.tf are alternatives, not two required files. The
    backend samples existing files under terraform/modules and tells the agent
    which single filename to use for newly created modules.
    """
    del prompt
    repo_full = f"{GITHUB_OWNER}/{GITHUB_AWS_REPO}"
    counts = {"vars.tf": 0, "variables.tf": 0}
    examples: list[dict] = []
    errors: list[str] = []

    for filename in AWS_MODULE_VARIABLE_FILENAMES:
        query = f'repo:{repo_full} path:{AWS_MODULES_ROOT} filename:{filename} variable'
        try:
            results = github_search_code(query, per_page=20) or []
        except Exception as exc:
            errors.append(f"{filename}: {exc}")
            results = []

        for result in results:
            path = (result.get("path") or "").strip()
            if not path.startswith(f"{AWS_MODULES_ROOT}/"):
                continue
            if _aws_module_variable_filename_from_path(path) != filename:
                continue
            counts[filename] += 1
            if len(examples) < 8:
                content = ""
                try:
                    content = github_get_file_content(
                        "aws",
                        path,
                        _aws_module_catalog_branch(),
                        repo_target="tf-devops",
                        workflow="aws_module_creation",
                    ) or ""
                except Exception as exc:
                    errors.append(f"read {path}: {exc}")
                examples.append({
                    "path": path,
                    "filename": filename,
                    "content": content[:8000],
                })

    if counts["vars.tf"] or counts["variables.tf"]:
        preferred = "vars.tf" if counts["vars.tf"] >= counts["variables.tf"] else "variables.tf"
        source = "live_github_tf_devops_module_scan"
    else:
        preferred = "vars.tf"
        source = "backend_default_when_github_scan_unavailable"

    return {
        "source": source,
        "preferred_variable_file_name": preferred,
        "allowed_variable_file_names": [preferred],
        "alternative_variable_file_names": [name for name in AWS_MODULE_VARIABLE_FILENAMES if name != preferred],
        "scanned_counts": counts,
        "examples": examples,
        "errors": errors,
        "rule": "Generate exactly one module variable declaration file using preferred_variable_file_name. Do not generate both vars.tf and variables.tf for the same module.",
    }


def _aws_variable_filename_convention_from_context(context: dict | None) -> str:
    if isinstance(context, dict):
        value = (context.get("preferred_variable_file_name") or "").strip().lower()
        if value in AWS_MODULE_VARIABLE_FILENAMES:
            return value
    return detect_aws_module_variable_file_convention().get("preferred_variable_file_name") or "vars.tf"

AWS_MODULE_DISCOVERY_CACHE = {}
AWS_MODULE_CONTEXT_CACHE = {}
AWS_MODULE_EXISTS_CACHE = {}
PENDING_AWS_MODULE_DISCOVERIES = {}

AWS_MODULE_STOP_WORDS = {
    "a", "an", "and", "approved", "aws", "create", "delete", "deploy", "for", "from", "in",
    "module", "new", "of", "please", "prod", "production", "resource", "the", "to",
    "update", "use", "using", "with", "dev", "nonprod", "non", "environment", "env",
}


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values or []:
        value = (value or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result



# -----------------------------------------------------------------------------
# Backend-owned Terraform variable declaration policy
# -----------------------------------------------------------------------------
# This policy is deterministic backend behavior. It is not sourced from RAG/KB.
# Optional examples may be read from GitHub, but repository state must always be
# supplied by backend-owned context, never by Foundry KB snippets.

PRIVATE_VALUE_VARIABLE_NAME_PATTERN = re.compile(
    r"(?:^|_)(?:ami|ami_id|subnet|subnet_id|subnet_ids|security_group|security_group_id|security_group_ids|vpc_id|account_id|subscription_id|tenant_id|client_secret|password|private_key|access_key|secret_key|token|connection_string|certificate|cert|kms|kms_key|kms_arn|key_vault_secret|storage_account_access_key)(?:$|_)",
    re.IGNORECASE,
)


def _variable_name_is_private_or_sensitive(name: str) -> bool:
    return bool(PRIVATE_VALUE_VARIABLE_NAME_PATTERN.search(name or "")) or _is_sensitive_variable_name(name or "")


def _strip_hcl_comments_for_attr_scan(value: str) -> str:
    text = (value or "").replace("\r\n", "\n")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    cleaned = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("//"):
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def _variable_attr_present(variable_block: str, attr_name: str) -> bool:
    return bool(re.search(rf'(?m)^\s*{re.escape(attr_name)}\s+=', _strip_hcl_comments_for_attr_scan(variable_block or "")))


def _variable_attr_value(variable_block: str, attr_name: str) -> str:
    text = _strip_hcl_comments_for_attr_scan(variable_block or "")
    match = re.search(rf'(?m)^\s*{re.escape(attr_name)}\s+=\s*(.+?)\s*$', text)
    return (match.group(1).strip() if match else "")


def _variable_type_from_block(variable_block: str) -> str:
    return _variable_attr_value(variable_block, "type")


def _normalize_type_expr(type_expr: str) -> str:
    return re.sub(r"\s+", "", (type_expr or "").strip().lower())


def _infer_variable_type_from_name_and_default(name: str, variable_block: str) -> str:
    name_l = (name or "").lower()
    default_value = _variable_attr_value(variable_block, "default")
    default_l = default_value.strip().lower()

    if default_l in {"true", "false"}:
        return "bool"
    if re.fullmatch(r"-?\d+(?:\.\d+)?", default_l or ""):
        return "number"
    if default_l.startswith("["):
        return "list(string)"
    if default_l.startswith("{"):
        return "map(any)"
    if default_l == "null":
        return "object({})"

    if name_l in {"create", "enabled"} or name_l.startswith(("create_", "enable_", "enabled_", "is_", "has_", "use_")) or name_l.endswith(("_enabled", "_exists")):
        return "bool"
    if name_l in {"tags", "labels"} or name_l.endswith(("_tags", "_map", "_overrides")):
        return "map(any)"
    if name_l.endswith(("_ids", "_arns", "_names", "_list", "_prefixes")):
        return "list(string)"
    if name_l.endswith(("_days", "_count", "_size", "_capacity", "_quota", "_port", "_ttl", "_seconds", "_minutes", "_hours")):
        return "number"
    return "string"


def _safe_default_for_type(type_expr: str) -> str | None:
    normalized = _normalize_type_expr(type_expr)
    if normalized == "bool":
        return "false"
    if normalized == "number":
        return "-1"
    if normalized.startswith("map(") or normalized == "map" or normalized == "anymap":
        return "{}"
    if normalized.startswith("list(") or normalized.startswith("set(") or normalized in {"list", "set"}:
        return "[]"
    if normalized.startswith("object("):
        return "null"
    return None


def _explicit_prompt_default_for_variable(prompt: str, variable_name: str, type_expr: str) -> str:
    prompt = prompt or ""
    name = re.escape(variable_name or "")
    if not name:
        return ""

    # HCL-style assignment in the user prompt, for example instance_name = "test".
    assign_match = re.search(rf'(?m)^\s*{name}\s*=\s*(.+?)\s*$', prompt)
    if assign_match:
        raw_value = assign_match.group(1).strip().rstrip(",")
        if raw_value:
            return raw_value

    # Common natural language naming pattern.
    if _normalize_type_expr(type_expr) == "string" and variable_name in {"name", "instance_name", "bucket_name", "function_app_name", "vm_name"}:
        natural_match = re.search(r'\b(?:named|called|name(?:d)?\s*=?)\s+["\']?([A-Za-z0-9_.-]+)["\']?', prompt, re.IGNORECASE)
        if natural_match:
            return json.dumps(natural_match.group(1))

    bool_match = re.search(rf'\b{re.escape(variable_name)}\b\s+(?:to\s+)?(true|false)\b', prompt, re.IGNORECASE)
    if bool_match and _normalize_type_expr(type_expr) == "bool":
        return bool_match.group(1).lower()

    return ""


def _iter_variable_blocks_with_names(tf_content: str) -> list[dict]:
    result = []
    for block in _extract_top_level_tf_blocks(tf_content or ""):
        header = (block.get("header") or "").strip()
        match = re.fullmatch(r'variable\s+"([^"\n]+)"', header)
        if not match:
            continue
        result.append({
            "name": match.group(1).strip(),
            "header": header,
            "block": block.get("block") or "",
        })
    return result


def _insert_attribute_before_variable_close(block: str, attr_line: str) -> str:
    lines = (block or "").rstrip().splitlines()
    if not lines:
        return block
    # Insert before the final root-level close brace. Variable blocks should be balanced here.
    for index in range(len(lines) - 1, -1, -1):
        if lines[index].strip() == "}":
            lines.insert(index, attr_line)
            return "\n".join(lines).rstrip() + "\n"
    return (block or "").rstrip() + "\n" + attr_line + "\n"


def _replace_variable_block(content: str, variable_name: str, new_block: str) -> str:
    original_block = _extract_tf_variable_block(content, variable_name)
    if not original_block:
        return content
    return content.replace(original_block, new_block.rstrip() + "\n", 1)


def _normalize_module_variables_tf_content_base(
    content: str,
    filename: str,
    workflow: str,
    user_prompt: str = "",
) -> tuple[str, list[str]]:
    """Normalize generated module variables.tf/vars.tf and return issues.

    Applies only to module implementation variable files, not tf-azure-hub root
    variables.tf for consumer tfvars declarations.
    """
    if not filename.endswith(("variables.tf", "vars.tf")):
        return content, []
    if workflow not in {"aws_module_creation", "azure_module_repo_population"}:
        return content, []

    updated = (content or "").replace("\r\n", "\n").rstrip() + "\n"
    issues: list[str] = []

    for item in _iter_variable_blocks_with_names(updated):
        name = item["name"]
        block = item["block"]
        new_block = block

        if not _variable_attr_present(new_block, "description"):
            issues.append(f'variable "{name}" is missing description')
            continue

        if not _variable_attr_present(new_block, "type"):
            inferred_type = _infer_variable_type_from_name_and_default(name, new_block)
            lines = new_block.rstrip().splitlines()
            # Put type immediately after description when possible.
            inserted = False
            for idx, line in enumerate(lines):
                if re.match(r"^\s*description\s+=", line):
                    lines.insert(idx + 1, f"  type        = {inferred_type}")
                    inserted = True
                    break
            if not inserted:
                new_block = _insert_attribute_before_variable_close(new_block, f"  type        = {inferred_type}")
            else:
                new_block = "\n".join(lines).rstrip() + "\n"

        type_expr = _variable_type_from_block(new_block)
        if not type_expr:
            issues.append(f'variable "{name}" is missing type')
            updated = _replace_variable_block(updated, name, new_block)
            continue

        default_present = _variable_attr_present(new_block, "default")
        default_value = _variable_attr_value(new_block, "default") if default_present else ""
        normalized_type = _normalize_type_expr(type_expr)

        if normalized_type == "string":
            explicit_default = _explicit_prompt_default_for_variable(user_prompt, name, type_expr)
            if explicit_default:
                # Explicit values collected through the backend variable-value
                # form are treated as user-approved values/references. The
                # backend still never invents AMIs, subnet IDs, security group
                # IDs, account IDs, ARNs, passwords, keys, or tokens.
                if default_present:
                    new_block = re.sub(r'(?m)^\s*default\s+=\s*.+?$', f"  default     = {explicit_default}", new_block, count=1)
                else:
                    new_block = _insert_attribute_before_variable_close(new_block, f"  default     = {explicit_default}")
            elif default_present:
                if _variable_name_is_private_or_sensitive(name) and default_value.strip() not in {'""', "null"}:
                    issues.append(f'variable "{name}" looks private/sensitive and must not have an invented concrete default')
            else:
                issues.append(f'variable "{name}" is a string without a backend-approved or user-provided default')
        else:
            safe_default = _safe_default_for_type(type_expr)
            if safe_default is not None and not default_present:
                new_block = _insert_attribute_before_variable_close(new_block, f"  default     = {safe_default}")

            # Enforce deterministic defaults for newly generated bool/number variables unless the prompt explicitly set them.
            if safe_default is not None and _variable_attr_present(new_block, "default"):
                current_default = _variable_attr_value(new_block, "default")
                explicit_default = _explicit_prompt_default_for_variable(user_prompt, name, type_expr)
                if normalized_type == "bool" and current_default not in {"false", "true"}:
                    issues.append(f'variable "{name}" has invalid bool default {current_default}')
                elif normalized_type == "bool" and current_default == "true" and explicit_default.lower() != "true":
                    # Repair to the project-safe default unless explicitly requested.
                    new_block = re.sub(r'(?m)^\s*default\s+=\s*true\s*$', "  default     = false", new_block, count=1)
                elif normalized_type == "number" and not explicit_default and current_default != "-1":
                    new_block = re.sub(r'(?m)^\s*default\s+=\s*[^\n]+$', "  default     = -1", new_block, count=1)

        updated = _replace_variable_block(updated, name, new_block)

    if not _iter_variable_blocks_with_names(updated):
        issues.append(f"{filename} must contain at least one Terraform variable block")

    return updated.rstrip() + "\n", issues


def normalize_generated_module_variable_files(
    files: list[dict],
    workflow: str,
    user_prompt: str = "",
) -> tuple[list[dict], list[str]]:
    updated_files = []
    issues: list[str] = []
    for file_data in files or []:
        item = dict(file_data)
        filename = item.get("filename") or ""
        content = item.get("content") or ""
        new_content, file_issues = normalize_module_variables_tf_content(
            content,
            filename,
            workflow,
            user_prompt=user_prompt,
        )
        if new_content != content:
            item["content"] = new_content
        issues.extend([f"{filename}: {issue}" for issue in file_issues])
        updated_files.append(item)
    return updated_files, issues


def validate_generated_module_variable_files(
    files: list[dict],
    workflow: str,
    user_prompt: str = "",
) -> list[dict]:
    updated_files, issues = normalize_generated_module_variable_files(
        files,
        workflow,
        user_prompt=user_prompt,
    )
    if issues:
        raise ValueError(
            "Generated module variable declarations require backend-approved defaults or user-provided values. "
            + "; ".join(issues)
            + ". Ask the user for the missing approved values/references before returning JSON."
        )
    return updated_files


def extract_explicit_non_sensitive_variable_defaults_from_prompt(prompt: str) -> dict:
    values = {}
    for match in re.finditer(r'(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$', prompt or ""):
        name = match.group(1)
        value = match.group(2).strip().rstrip(",")
        if name and value and not _variable_name_is_private_or_sensitive(name):
            values[name] = value
    return values


def build_backend_variable_declaration_context(
    prompt: str,
    cloud: str,
    workflow: str,
    retrieved_module_context: list | None = None,
    retrieved_value_context: list | None = None,
) -> dict:
    """Build deterministic backend-only variable declaration policy/context.

    Optional examples are read from GitHub where possible. Failure to read them
    does not fall back to RAG/KB and does not block generation; it just means the
    agent receives policy without examples.
    """
    context = {
        "source": "backend_variable_declaration_policy",
        "backend_only": True,
        "cloud": safe_normalize_cloud(cloud) or cloud,
        "workflow": workflow or "",
        "required_variable_block_attributes": ["description", "type"],
        "attribute_order": ["description", "type", "default"],
        "safe_type_defaults": {
            "bool": "false",
            "number": "-1",
            "map": "{}",
            "list": "[]",
            "set": "[]",
            "object": "null",
        },
        "string_default_rule": "Use default only when explicit non-sensitive user value or backend-approved repo value exists; otherwise ask for values before JSON.",
        "private_value_rule": "Never invent AMIs, subnet IDs, security group IDs, account IDs, ARNs, passwords, keys, tokens, or secrets. Use backend-approved references or ask.",
        "explicit_user_values": extract_explicit_non_sensitive_variable_defaults_from_prompt(prompt),
        "github_variable_examples": [],
    }

    try:
        if safe_normalize_cloud(cloud) == "aws" and workflow == "aws_module_creation":
            convention = detect_aws_module_variable_file_convention(prompt)
            context["module_variable_file_convention"] = convention
            context["module_variable_file_name"] = convention.get("preferred_variable_file_name") or "vars.tf"
            context["allowed_module_variable_file_names"] = convention.get("allowed_variable_file_names") or [context["module_variable_file_name"]]
            context["forbidden_module_variable_file_names"] = convention.get("alternative_variable_file_names") or []
            for example in convention.get("examples") or []:
                if example.get("content"):
                    context["github_variable_examples"].append({
                        "path": example.get("path"),
                        "content": example.get("content"),
                    })
        elif safe_normalize_cloud(cloud) == "azure" and workflow == "azure_module_repo_population":
            context["module_variable_file_convention"] = {
                "source": "azure_module_repo_population_contract",
                "preferred_variable_file_name": "variables.tf",
                "allowed_variable_file_names": ["variables.tf"],
                "forbidden_variable_file_names": ["vars.tf"],
                "rule": "Azure module repo population uses root-level variables.tf only. Do not generate vars.tf.",
            }
            context["module_variable_file_name"] = "variables.tf"
            context["allowed_module_variable_file_names"] = ["variables.tf"]
            context["forbidden_module_variable_file_names"] = ["vars.tf"]
            for item in retrieved_module_context or []:
                for tf_file in item.get("tf_files") or []:
                    if (tf_file.get("path") or "").endswith("variables.tf"):
                        context["github_variable_examples"].append({
                            "path": tf_file.get("path"),
                            "content": (tf_file.get("content") or "")[:8000],
                        })
    except Exception as variable_context_error:
        context["github_variable_examples_error"] = str(variable_context_error)

    return context

def _aws_module_catalog_branch(branch: Optional[str] = None) -> str:
    """Return the branch used for live tf-devops module discovery.

    Module discovery must read the current base branch, not the configured PR
    source branch. The PR source branch can legitimately lag behind main and
    then falsely report that an existing module is missing.
    """
    requested = (branch or "").strip()
    if requested:
        return requested

    return (
        github_base_branch_for_cloud(
            "aws",
            repo_target="tf-devops",
            workflow="aws_module_consumer",
        )
        or "main"
    )


def _sanitize_aws_module_rel_path(module_rel_path: str) -> str:
    module_rel_path = (module_rel_path or "").strip().replace("\\", "/").strip("/")
    if module_rel_path.startswith(f"{AWS_MODULES_ROOT}/"):
        module_rel_path = module_rel_path[len(AWS_MODULES_ROOT) + 1:]
    if module_rel_path.startswith("modules/"):
        module_rel_path = module_rel_path[len("modules/"):]
    if not module_rel_path:
        return ""
    if module_rel_path == ".." or module_rel_path.startswith("../") or "/../" in module_rel_path:
        return ""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", module_rel_path):
        return ""
    return module_rel_path


def normalize_aws_module_source_path(source: str) -> str:
    """Return module path relative to terraform/modules for a local tf-devops source."""
    source = (source or "").strip().strip('"\'').replace("\\", "/")
    if not source:
        return ""

    lowered = source.lower()
    if lowered.startswith(("git::", "http://", "https://", "ssh://")) or "github.com" in lowered:
        return ""

    source = source.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    parts = [part for part in source.split("/") if part and part != "."]
    if not parts:
        return ""

    rel_parts = []
    if "modules" in parts:
        module_idx = len(parts) - 1 - list(reversed(parts)).index("modules")
        rel_parts = parts[module_idx + 1:]
    elif source.startswith(f"{AWS_MODULES_ROOT}/"):
        rel_parts = source[len(AWS_MODULES_ROOT) + 1:].split("/")
    elif source.startswith("modules/"):
        rel_parts = source[len("modules/"):].split("/")

    rel_parts = [part for part in rel_parts if part and part not in {".", ".."}]
    return _sanitize_aws_module_rel_path("/".join(rel_parts))


def _extract_aws_module_source_refs_from_text(tf_content: str) -> list[dict]:
    refs = []
    for block in _extract_top_level_tf_blocks(tf_content or ""):
        header = block.get("header") or ""
        if not re.match(r'^module\s+"[^"]+"$', header):
            continue

        source_match = re.search(r'(?m)^\s*source\s*=\s*"([^"]+)"', block.get("block") or "")
        if not source_match:
            refs.append({
                "module_name": "",
                "source": "",
                "module_path": "",
                "error": "missing_source",
            })
            continue

        name_match = re.match(r'^module\s+"([^"]+)"$', header)
        source = source_match.group(1).strip()
        refs.append({
            "module_name": name_match.group(1) if name_match else "",
            "source": source,
            "module_path": normalize_aws_module_source_path(source),
            "error": "" if normalize_aws_module_source_path(source) else "unrecognized_source",
        })
    return refs


def _extract_tf_output_names_from_text(tf_content: str) -> list[str]:
    if not tf_content:
        return []
    return _dedupe_preserving_order(re.findall(r'output\s+"([^"]+)"', tf_content, re.IGNORECASE))


def github_list_verified_aws_module_paths(branch: Optional[str] = None) -> list[str]:
    branch = _aws_module_catalog_branch(branch)
    cache_key = (GITHUB_OWNER, GITHUB_AWS_REPO, branch)
    if cache_key in AWS_MODULE_DISCOVERY_CACHE:
        return list(AWS_MODULE_DISCOVERY_CACHE[cache_key])

    module_paths = []

    def walk(current_path: str, rel_path: str = ""):
        items = github_get_directory_listing(
            "aws",
            current_path,
            branch,
            repo_target="tf-devops",
            workflow="aws_module_consumer",
        )
        if not items:
            return

        has_tf_file = False
        child_dirs = []
        for item in items:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            item_path = item.get("path") or ""
            item_name = item.get("name") or item_path.rsplit("/", 1)[-1]
            if item_type == "file" and item_path.endswith(".tf"):
                has_tf_file = True
            elif item_type == "dir" and item_name not in {".terraform", "__pycache__"}:
                child_rel = f"{rel_path}/{item_name}".strip("/")
                child_dirs.append((item_path, child_rel))

        if has_tf_file and rel_path:
            module_paths.append(rel_path)

        for child_path, child_rel in child_dirs:
            walk(child_path, child_rel)

    walk(AWS_MODULES_ROOT, "")
    module_paths = _dedupe_preserving_order(sorted(module_paths))
    AWS_MODULE_DISCOVERY_CACHE[cache_key] = module_paths
    return list(module_paths)


def github_verified_aws_module_exists(module_rel_path: str, branch: Optional[str] = None) -> bool:
    module_rel_path = _sanitize_aws_module_rel_path(module_rel_path)
    if not module_rel_path:
        return False

    branch = _aws_module_catalog_branch(branch)
    cache_key = (GITHUB_OWNER, GITHUB_AWS_REPO, branch, module_rel_path)
    if cache_key in AWS_MODULE_EXISTS_CACHE:
        return AWS_MODULE_EXISTS_CACHE[cache_key]

    try:
        exists = module_rel_path in github_list_verified_aws_module_paths(branch)
    except Exception:
        exists = False

    if not exists:
        try:
            items = github_get_directory_listing(
                "aws",
                f"{AWS_MODULES_ROOT}/{module_rel_path}",
                branch,
                repo_target="tf-devops",
                workflow="aws_module_consumer",
            )
            exists = any(
                isinstance(item, dict)
                and item.get("type") == "file"
                and (item.get("path") or "").endswith(".tf")
                for item in items or []
            )
        except Exception:
            exists = False

    AWS_MODULE_EXISTS_CACHE[cache_key] = bool(exists)
    return bool(exists)


def build_aws_local_module_source(module_rel_path: str, environment_path: str = "") -> str:
    module_rel_path = _sanitize_aws_module_rel_path(module_rel_path)
    if not module_rel_path:
        return ""

    module_path = f"{AWS_MODULES_ROOT}/{module_rel_path}"
    env_path = (environment_path or "").strip().strip("/")
    if not env_path or env_path in {".", AWS_MODULES_ROOT}:
        return module_path

    return os.path.relpath(module_path, start=env_path).replace("\\", "/")


def _aws_module_lookup_text(value: str) -> str:
    """Normalize prompt/module text for generic AWS module catalog matching."""
    return re.sub(
        r"\s+",
        " ",
        (value or "")
        .replace("\\", "/")
        .replace("_", " ")
        .replace("-", " ")
        .replace("/", " ")
        .lower(),
    ).strip()


def _aws_module_singular_token(token: str) -> str:
    token = (token or "").strip().lower()
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


AWS_MODULE_TOKEN_ALIASES = {
    # Generic AWS service abbreviations that commonly differ from module folder
    # names. This keeps discovery backend-owned while avoiding false misses such
    # as a user asking for an "S3 storage bucket" when the verified module
    # path is named bucket, s3_bucket, aws_s3_bucket, or storage_bucket.
    "s3": ["bucket", "storage", "object", "simple", "service"],
    "bucket": ["s3", "storage"],
    "storage": ["s3", "bucket"],
}


def _aws_module_lookup_tokens(value: str, keep_stop_words: bool = False) -> list[str]:
    """Tokenize text for module matching with small service-name expansion."""
    tokens: list[str] = []
    for token in re.findall(r"[a-z0-9]+", _aws_module_lookup_text(value)):
        if not token or len(token) <= 1:
            continue
        if not keep_stop_words and token in AWS_MODULE_STOP_WORDS:
            continue
        tokens.append(token)
        singular = _aws_module_singular_token(token)
        if singular != token:
            tokens.append(singular)
        for alias in AWS_MODULE_TOKEN_ALIASES.get(token, []):
            if alias:
                tokens.append(alias)
    return _dedupe_preserving_order(tokens)


def _aws_module_catalog_phrases(module_rel_path: str) -> list[str]:
    """Build searchable phrases from a real module path in terraform/modules.

    The phrases are derived only from the live GitHub catalog path. This avoids
    maintaining service-specific hardcoded aliases such as S3/bucket mappings and
    makes discovery work for any existing module name.
    """
    module_rel_path = _sanitize_aws_module_rel_path(module_rel_path)
    if not module_rel_path:
        return []

    basename = module_rel_path.rsplit("/", 1)[-1]
    parent_parts = module_rel_path.split("/")[:-1]
    variants = {
        module_rel_path,
        module_rel_path.replace("/", "_"),
        module_rel_path.replace("/", "-"),
        module_rel_path.replace("/", " "),
        basename,
        basename.replace("_", "-"),
        basename.replace("_", " "),
        basename.replace("-", " "),
    }

    if parent_parts:
        parent = parent_parts[-1]
        variants.update({
            parent,
            f"{parent} {basename}",
            f"{parent}_{basename}",
            f"{parent}-{basename}",
        })

    return _dedupe_preserving_order([
        re.sub(r"\s+", " ", item.replace("_", " ").replace("-", " ").replace("/", " ").lower()).strip()
        for item in variants
        if item and item.strip()
    ])


def _aws_module_token_pairs(tokens: list[str]) -> set[tuple[str, str]]:
    return {
        (tokens[index], tokens[index + 1])
        for index in range(0, max(0, len(tokens) - 1))
        if tokens[index] and tokens[index + 1]
    }


def _score_aws_module_candidate(prompt: str, module_rel_path: str) -> tuple[int, list[str]]:
    """Score a module using only the prompt and the live module catalog path.

    No resource-specific hints are used. Every module under terraform/modules is
    considered and scored from exact path/name matches, normalized phrase
    matches, token overlap, and ordered token-pair overlap.
    """
    text = re.sub(r"\s+", " ", (prompt or "").strip().lower())
    module_rel_path = _sanitize_aws_module_rel_path(module_rel_path)
    if not text or not module_rel_path:
        return 0, []

    reasons: list[str] = []
    score = 0

    prompt_tokens = _aws_module_lookup_tokens(prompt)
    prompt_token_set = set(prompt_tokens)
    module_tokens = _aws_module_lookup_tokens(module_rel_path, keep_stop_words=True)
    module_token_set = set(module_tokens)
    module_name = module_rel_path.rsplit("/", 1)[-1]

    exact_names = {
        module_rel_path.lower(),
        module_rel_path.replace("/", "_").lower(),
        module_rel_path.replace("/", "-").lower(),
        module_name.lower(),
        module_name.replace("_", "-").lower(),
        module_name.replace("_", " ").lower(),
        module_name.replace("-", " ").lower(),
    }
    for exact in sorted(exact_names, key=len, reverse=True):
        if exact and re.search(rf"(?<![a-z0-9]){re.escape(exact)}(?![a-z0-9])", text):
            score += 150
            reasons.append(f"exact_catalog_name:{exact}")
            break

    for phrase in _aws_module_catalog_phrases(module_rel_path):
        if phrase and len(phrase) > 2 and re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", _aws_module_lookup_text(prompt)):
            score += 80
            reasons.append(f"catalog_phrase:{phrase}")
            break

    overlap = sorted(prompt_token_set & module_token_set)
    if overlap:
        score += len(overlap) * 25
        reasons.append("token_overlap:" + ",".join(overlap[:8]))

        prompt_coverage = len(overlap) / max(1, len(prompt_token_set))
        module_coverage = len(overlap) / max(1, len(module_token_set))
        if prompt_coverage >= 0.5:
            score += 20
            reasons.append("prompt_token_coverage")
        if module_coverage >= 0.5:
            score += 20
            reasons.append("module_token_coverage")

    pair_overlap = _aws_module_token_pairs(prompt_tokens) & _aws_module_token_pairs(module_tokens)
    if pair_overlap:
        score += len(pair_overlap) * 35
        reasons.append(
            "ordered_token_pair:" + ",".join("/".join(pair) for pair in sorted(pair_overlap)[:5])
        )

    # Prefer direct module folders over deeply nested modules when the evidence
    # score is otherwise equal, but do not discard nested modules.
    score -= min(module_rel_path.count("/"), 4)

    if score <= 0:
        return 0, []

    return score, reasons or ["generic_catalog_token_match"]

def _find_aws_module_consumer_examples(module_rel_path: str, branch: str, max_examples: int = 3) -> list[dict]:
    module_rel_path = _sanitize_aws_module_rel_path(module_rel_path)
    if not module_rel_path:
        return []

    examples = []
    seen_paths = set()

    source_needles = [
        f"modules/{module_rel_path}",
        build_aws_local_module_source(module_rel_path, "terraform/dev_aws/minidev"),
        build_aws_local_module_source(module_rel_path, "terraform/prod_aws/us1"),
    ]
    source_needles = _dedupe_preserving_order(source_needles)

    for needle in source_needles:
        if len(examples) >= max_examples:
            break
        try:
            query = f'repo:{GITHUB_OWNER}/{GITHUB_AWS_REPO} "{needle}" path:terraform'
            search_items = github_search_code(query, per_page=20)
        except Exception as search_error:
            print(f"AWS module example search failed for {module_rel_path}: {search_error}")
            search_items = []

        for item in search_items or []:
            if len(examples) >= max_examples:
                break
            item_path = (item or {}).get("path") or ""
            if not item_path.endswith(".tf"):
                continue
            if item_path.startswith(f"{AWS_MODULES_ROOT}/"):
                continue
            if item_path in seen_paths:
                continue

            try:
                content = github_get_file_content(
                    "aws",
                    item_path,
                    branch,
                    repo_target="tf-devops",
                    workflow="aws_module_consumer",
                )
            except Exception:
                content = None
            if not content:
                continue

            matched_blocks = []
            for block in _extract_top_level_tf_blocks(content):
                if not re.match(r'^module\s+"[^"]+"$', block.get("header") or ""):
                    continue
                source_match = re.search(r'(?m)^\s*source\s*=\s*"([^"]+)"', block.get("block") or "")
                if not source_match:
                    continue
                if normalize_aws_module_source_path(source_match.group(1)) == module_rel_path:
                    matched_blocks.append(block.get("block") or "")

            if not matched_blocks:
                continue

            seen_paths.add(item_path)
            examples.append({
                "path": item_path,
                "module_blocks": matched_blocks[:2],
            })

    return examples


def _build_verified_aws_module_context_base(
    module_rel_path: str,
    branch: Optional[str] = None,
    environment_path: str = "",
    include_examples: bool = True,
) -> dict:
    module_rel_path = _sanitize_aws_module_rel_path(module_rel_path)
    if not module_rel_path:
        return {}

    branch = _aws_module_catalog_branch(branch)
    cache_key = (GITHUB_OWNER, GITHUB_AWS_REPO, branch, module_rel_path, environment_path, bool(include_examples))
    if cache_key in AWS_MODULE_CONTEXT_CACHE:
        return dict(AWS_MODULE_CONTEXT_CACHE[cache_key])

    module_root = f"{AWS_MODULES_ROOT}/{module_rel_path}"
    items = github_get_directory_listing(
        "aws",
        module_root,
        branch,
        repo_target="tf-devops",
        workflow="aws_module_consumer",
    )

    tf_files = []
    inputs = []
    required_inputs = []
    outputs = []

    for item in items or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "file":
            continue
        item_path = item.get("path") or ""
        if not item_path.endswith(".tf"):
            continue

        tf_files.append(item_path)
        try:
            content = github_get_file_content(
                "aws",
                item_path,
                branch,
                repo_target="tf-devops",
                workflow="aws_module_consumer",
            )
        except Exception:
            content = None
        if not content:
            continue

        inputs.extend(_extract_tf_variable_names_from_text(content))
        required_inputs.extend(_extract_required_variable_names_from_text(content))
        outputs.extend(_extract_tf_output_names_from_text(content))

    inputs = _dedupe_preserving_order(inputs)
    required_inputs = [name for name in _dedupe_preserving_order(required_inputs) if name in inputs]
    outputs = _dedupe_preserving_order(outputs)

    context = {
        "cloud": "aws",
        "repo_target": "tf-devops",
        "repo_full_name": f"{GITHUB_OWNER}/{GITHUB_AWS_REPO}",
        "module_root": AWS_MODULES_ROOT,
        "module_path": module_rel_path,
        "verified_module_path": f"{AWS_MODULES_ROOT}/{module_rel_path}",
        "module_source": build_aws_local_module_source(module_rel_path, environment_path),
        "module_source_kind": "verified_tf_devops_local_module",
        "resolved_ref": branch,
        "tf_files": tf_files,
        "inputs_detected": inputs,
        "required_inputs_detected": required_inputs,
        "outputs_detected": outputs,
        "source": "live_github_tf_devops_terraform_modules",
    }

    if include_examples:
        context["consumer_examples"] = _find_aws_module_consumer_examples(
            module_rel_path,
            branch,
            max_examples=3,
        )

    AWS_MODULE_CONTEXT_CACHE[cache_key] = dict(context)
    return context


def _discover_live_aws_module_candidates_base(
    prompt: str,
    environment_path: str = "",
    branch: Optional[str] = None,
    max_matches: int = 6,
) -> dict:
    branch = _aws_module_catalog_branch(branch)
    catalog = github_list_verified_aws_module_paths(branch)

    scored = []
    for module_rel_path in catalog:
        score, reasons = _score_aws_module_candidate(prompt, module_rel_path)
        if score <= 0:
            continue
        scored.append({
            "module_path": module_rel_path,
            "score": score,
            "reasons": reasons,
        })

    scored.sort(key=lambda item: (-int(item.get("score") or 0), item.get("module_path") or ""))
    selected = scored[:max(1, int(max_matches or 6))]

    matches = []
    for item in selected:
        try:
            context = build_verified_aws_module_context(
                item["module_path"],
                branch=branch,
                environment_path=environment_path,
                include_examples=True,
            )
        except Exception as context_error:
            print(f"AWS module context failed for {item.get('module_path')}: {context_error}")
            context = {
                "cloud": "aws",
                "repo_target": "tf-devops",
                "module_path": item["module_path"],
                "verified_module_path": f"{AWS_MODULES_ROOT}/{item['module_path']}",
                "module_source": build_aws_local_module_source(item["module_path"], environment_path),
                "resolved_ref": branch,
                "source": "live_github_tf_devops_terraform_modules",
                "inspection_error": str(context_error),
            }
        context["match_score"] = item.get("score")
        context["match_reasons"] = item.get("reasons") or []
        matches.append(context)

    if not matches:
        return {
            "status": "not_found",
            "decision_state": "aws_module_not_found",
            "requested_resource_hint": infer_aws_requested_resource_hint(prompt),
            "repo_full_name": f"{GITHUB_OWNER}/{GITHUB_AWS_REPO}",
            "module_root": AWS_MODULES_ROOT,
            "resolved_ref": branch,
            "matches": [],
            "available_module_paths_sample": catalog[:80],
            "catalog_count": len(catalog),
        }

    best_score = int(matches[0].get("match_score") or 0)
    status = "exact_match" if best_score >= 100 else "similar_match"
    return {
        "status": status,
        "decision_state": "aws_module_verified",
        "requested_resource_hint": infer_aws_requested_resource_hint(prompt),
        "repo_full_name": f"{GITHUB_OWNER}/{GITHUB_AWS_REPO}",
        "module_root": AWS_MODULES_ROOT,
        "resolved_ref": branch,
        "matches": matches,
        "available_module_paths_sample": catalog[:80],
        "catalog_count": len(catalog),
    }


def infer_aws_requested_resource_hint(prompt: str) -> str:
    text = (prompt or "").strip().lower()
    explicit = re.search(r"(?:module|resource|for|create|add|provision)\s+(?:an?\s+)?([a-z0-9][a-z0-9 _/-]{1,80})", text)
    if explicit:
        return re.sub(r"\s+", " ", explicit.group(1)).strip()

    tokens = [
        token for token in re.findall(r"[a-z0-9]+", text)
        if token not in AWS_MODULE_STOP_WORDS
    ]
    return " ".join(tokens[:6])


def aws_prompt_can_update_existing_without_module_match(prompt: str) -> bool:
    text = re.sub(r"\s+", " ", (prompt or "").strip().lower())
    if not text:
        return False

    update_terms = {
        "change", "update", "modify", "rename", "set", "remove", "delete",
        "enable", "disable", "increase", "decrease", "tag", "untag", "attach", "detach",
    }
    create_terms = {"create", "add", "provision", "new", "deploy"}

    has_update = any(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) for term in update_terms)
    has_create = any(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) for term in create_terms)
    return bool(has_update and not has_create)


def build_aws_module_not_found_reply(discovery: dict) -> str:
    discovery = discovery or {}
    hint = discovery.get("requested_resource_hint") or "the requested AWS resource"
    sample = discovery.get("available_module_paths_sample") or []
    catalog_count = discovery.get("catalog_count") or len(sample)

    sample_text = ", ".join(sample[:20])
    if len(sample) > 20:
        sample_text += ", ..."

    return (
        f"I scanned the live tf-devops module catalog under {AWS_MODULES_ROOT} and could not find a verified AWS module for '{hint}'. "
        "No Terraform was generated, because AWS module-consumer changes must use real local modules from tf-devops/terraform/modules only. "
        "I will not suggest or generate a guessed module name such as ec2_instance."
        + (f"\n\nVerified module catalog contains {catalog_count} module paths. Examples: {sample_text}" if sample_text else "")
    )


def infer_new_aws_module_path(prompt: str, discovery: dict | None = None) -> str:
    """Build a deterministic, sanitized candidate path for a new AWS module."""
    discovery = discovery or {}
    hint = (discovery.get("requested_resource_hint") or "").strip().lower()
    text = hint or (prompt or "").strip().lower()

    # New module naming is also generic: derive the candidate from the user's
    # requested words rather than from service-specific aliases.
    tokens = re.findall(r"[a-z0-9]+", text.replace("_", " ").replace("-", " "))
    stop_words = set(AWS_MODULE_STOP_WORDS) - {"instance"}
    stop_words.update({
        "want", "me", "terrabot", "make", "build", "stand", "spin", "up", "one",
        "verified", "local", "missing", "found", "under", "path", "folder",
    })
    resource_tokens = [token for token in tokens if token not in stop_words and len(token) > 1]

    if not resource_tokens:
        resource_tokens = ["aws", "module"]

    slug = "_".join(resource_tokens[:4])
    slug = re.sub(r"[^a-z0-9_/-]", "_", slug).strip("_/")
    slug = re.sub(r"_+", "_", slug)
    slug = re.sub(r"/+", "/", slug)
    return _sanitize_aws_module_rel_path(slug) or "aws_module"


def store_pending_aws_module_discovery(
    thread_id: str,
    ticket_number: str,
    original_prompt: str,
    discovery: dict,
    environment_path: str = "",
    proposed_module_path: str = "",
    ticket_link: str = "",
    ticket_title: str = "",
):
    key = hashlib.sha1(
        f"{thread_id or 'no-thread'}::{ticket_number or ''}::aws-module-discovery::{original_prompt}".encode("utf-8")
    ).hexdigest()

    PENDING_AWS_MODULE_DISCOVERIES[key] = {
        "thread_id": thread_id,
        "ticket_number": (ticket_number or "").strip().upper(),
        "original_prompt": original_prompt,
        "ticket_link": ticket_link or "",
        "ticket_title": ticket_title or "",
        "environment_path": environment_path or "",
        "proposed_module_path": proposed_module_path or "",
        "discovery": discovery or {},
    }
    return key


def get_pending_aws_module_discovery(thread_id: str, ticket_number: str):
    thread_id = str(thread_id or "")
    ticket_number = (ticket_number or "").strip().upper()

    for _, item in PENDING_AWS_MODULE_DISCOVERIES.items():
        if str(item.get("thread_id") or "") == thread_id and (item.get("ticket_number") or "") == ticket_number:
            return item
    return None


def clear_pending_aws_module_discovery(thread_id: str, ticket_number: str):
    thread_id = str(thread_id or "")
    ticket_number = (ticket_number or "").strip().upper()

    keys_to_delete = []
    for key, item in PENDING_AWS_MODULE_DISCOVERIES.items():
        if str(item.get("thread_id") or "") == thread_id and (item.get("ticket_number") or "") == ticket_number:
            keys_to_delete.append(key)

    for key in keys_to_delete:
        PENDING_AWS_MODULE_DISCOVERIES.pop(key, None)


def build_aws_module_creation_confirmation_reply(discovery: dict, environment_path: str, proposed_module_path: str) -> str:
    discovery = discovery or {}
    hint = discovery.get("requested_resource_hint") or "the requested AWS resource"
    catalog_count = discovery.get("catalog_count") or 0
    sample = discovery.get("available_module_paths_sample") or []
    sample_text = ", ".join(sample[:12])
    if len(sample) > 12:
        sample_text += ", ..."

    proposed_module_path = _sanitize_aws_module_rel_path(proposed_module_path) or infer_new_aws_module_path(hint, discovery)
    environment_path = (environment_path or "terraform/dev_aws/minidev").strip().strip("/")
    source_path = build_aws_local_module_source(proposed_module_path, environment_path)

    lines = [
        f"I could not find a verified AWS module under tf-devops/{AWS_MODULES_ROOT} for '{hint}'.",
        "I will not generate a guessed consumer module block against a non-existent module.",
        "",
        "Do you want me to create a new AWS module and a consumer reference in the same tf-devops PR?",
        f"New module path: tf-devops/{AWS_MODULES_ROOT}/{proposed_module_path}/",
        f"Consumer folder: tf-devops/{environment_path}/",
        f"Consumer source path: source = \"{source_path}\"",
    ]

    if catalog_count:
        lines.append("")
        lines.append(f"Verified module catalog checked: {catalog_count} existing module paths.")
    if sample_text:
        lines.append(f"Examples already present: {sample_text}")

    lines.append("")
    lines.append("Reply yes to generate the new-module PR preview, or no to cancel.")
    return "\n".join(lines)




def build_aws_existing_module_selection_reply(discovery: dict, environment_path: str = "") -> str:
    discovery = discovery or {}
    matches = discovery.get("matches") or []
    hint = discovery.get("requested_resource_hint") or "the requested AWS resource"
    environment_path = (environment_path or "terraform/dev_aws/minidev").strip().strip("/")

    lines = [
        f"I found verified AWS module option(s) in tf-devops/{AWS_MODULES_ROOT} for '{hint}'.",
        "Select the exact module Terrabot should invoke. I will not create a new module while a verified module is available.",
        "",
        f"Target consumer folder: tf-devops/{environment_path}",
        "",
    ]

    for index, match in enumerate(matches, start=1):
        module_path = match.get("module_path") or match.get("verified_module_path") or ""
        if str(module_path).startswith(f"{AWS_MODULES_ROOT}/"):
            module_path = str(module_path)[len(f"{AWS_MODULES_ROOT}/"):]
        module_source = match.get("module_source") or build_aws_local_module_source(module_path, environment_path)
        required_inputs = match.get("required_inputs_detected") or []
        inputs = match.get("inputs_detected") or []
        reason = ", ".join(match.get("match_reasons") or []) or "backend live GitHub module match"

        lines.append(f"{index}. `{module_path}`")
        lines.append(f"   Source: `source = \"{module_source}\"`")
        if required_inputs:
            lines.append(f"   Required inputs: {', '.join(required_inputs[:10])}")
        elif inputs:
            lines.append(f"   Inputs detected: {', '.join(inputs[:10])}")
        lines.append(f"   Reason: {reason}")

    lines.append("")
    lines.append(f"{len(matches) + 1}. **Create a new module for this request**")
    lines.append("   Use this when none of the verified modules is the implementation you want.")
    lines.append("")
    lines.append("Reply with the option number or exact module path. Reply no to cancel.")
    return "\n".join(lines)


def select_aws_module_match_from_reply(reply: str, matches: list[dict]) -> dict:
    text = (reply or "").strip()
    if not text:
        return {}

    number_match = re.fullmatch(r"\s*(?:option|select|choose|pick)?\s*#?(\d+)\s*", text, re.IGNORECASE)
    if number_match:
        index = int(number_match.group(1)) - 1
        if 0 <= index < len(matches or []):
            return dict(matches[index])

    normalized = text.strip("`'\" ").lower()
    for match in matches or []:
        module_path = (match.get("module_path") or match.get("verified_module_path") or "").strip()
        if module_path.startswith(f"{AWS_MODULES_ROOT}/"):
            module_path = module_path[len(f"{AWS_MODULES_ROOT}/"):]
        variants = {
            module_path.lower(),
            module_path.replace("/", "_").lower(),
            module_path.replace("/", "-").lower(),
            module_path.rsplit("/", 1)[-1].lower(),
        }
        if normalized in variants:
            return dict(match)
        if module_path and module_path.lower() in normalized:
            return dict(match)

    return {}


def _aws_module_selection_requests_new_module(reply: str, matches: list[dict]) -> bool:
    """Return True only for the explicit `create my own module` selection.

    The synthetic option is always rendered immediately after the verified
    module options, so an option number cannot collide with a real module.
    Plain `no` remains cancellation and never starts module creation.
    """
    raw = str(reply or "").strip()
    if not raw:
        return False
    number_match = re.fullmatch(
        r"\s*(?:option|select|choose|pick)?\s*#?(\d+)\s*",
        raw,
        re.IGNORECASE,
    )
    if number_match and int(number_match.group(1)) == len(matches or []) + 1:
        return True
    normalized = re.sub(r"\s+", " ", raw.strip("`'\" " ).lower())
    return bool(re.search(
        r"\b(?:create|make|build|use)\b.*\b(?:my|own|new|custom)\b.*\bmodule\b|"
        r"\b(?:new|custom)\s+module\b|\bcreate\s+module\b",
        normalized,
        re.IGNORECASE,
    ))


def _aws_unique_custom_module_path(prompt: str, discovery: dict | None = None) -> str:
    """Choose a deterministic new module path that cannot overwrite a verified module."""
    base = infer_new_aws_module_path(prompt, discovery or {})
    candidates = [f"{base}_custom", f"{base}_terrabot"]
    candidates.extend(f"{base}_custom_{index}" for index in range(2, 20))
    for candidate in candidates:
        candidate = _sanitize_aws_module_rel_path(candidate)
        if candidate and not github_verified_aws_module_exists(candidate):
            return candidate
    raise ValueError(
        f"Could not allocate a new AWS module path for {base}; verified candidate paths already exist."
    )


def _aws_selected_module_context_with_contents_stage1(
    selected_match: dict,
    discovery: dict,
    environment_path: str,
) -> tuple[dict, dict]:
    """Materialize the selected module and target main.tf for Foundry.

    This is intentionally done after the user's module choice. The generation
    turn receives every .tf file from the selected module plus the complete
    live target-environment main.tf, so it can produce one append-only consumer
    delta without re-running module discovery.
    """
    module_path = str(
        selected_match.get("module_path")
        or selected_match.get("verified_module_path")
        or ""
    ).strip()
    if module_path.startswith(f"{AWS_MODULES_ROOT}/"):
        module_path = module_path[len(f"{AWS_MODULES_ROOT}/"):]
    module_path = _sanitize_aws_module_rel_path(module_path)
    if not module_path:
        raise ValueError("The selected AWS module did not contain a verified module path.")

    environment_path = str(environment_path or "terraform/dev_aws/minidev").strip().strip("/")
    branch = str(discovery.get("resolved_ref") or _aws_module_catalog_branch()).strip()
    verified = build_verified_aws_module_context(
        module_path,
        branch=branch,
        environment_path=environment_path,
        include_examples=True,
    )
    if not verified:
        raise ValueError(f"Could not reload verified AWS module context for {module_path}.")

    module_root = f"{AWS_MODULES_ROOT}/{module_path}"
    module_tf_paths: list[str] = []

    def walk_module(current_path: str) -> None:
        for item in github_get_directory_listing(
            "aws",
            current_path,
            branch,
            repo_target="tf-devops",
            workflow="aws_module_consumer",
        ) or []:
            if not isinstance(item, dict):
                continue
            item_path = str(item.get("path") or "").strip()
            if item.get("type") == "dir":
                walk_module(item_path)
            elif item.get("type") == "file" and item_path.endswith(".tf"):
                module_tf_paths.append(item_path)

    walk_module(module_root)
    module_tf_paths = list(dict.fromkeys(module_tf_paths))
    module_files = []
    for path in module_tf_paths:
        content = github_get_file_content(
            "aws",
            path,
            branch,
            repo_target="tf-devops",
            workflow="aws_module_consumer",
        )
        if content is None:
            raise ValueError(f"Selected AWS module file could not be read from GitHub: {path}")
        module_files.append({"path": path, "content": content})
    if not module_files:
        raise ValueError(f"Selected AWS module {module_path} has no readable .tf files.")

    main_path = f"{environment_path}/main.tf"
    main_content = github_get_file_content(
        "aws",
        main_path,
        branch,
        repo_target="tf-devops",
        workflow="aws_module_consumer",
    )
    if main_content is None:
        # Module catalog and environment can live on different active refs.
        env_branch = _teams_remote_context_branch(
            "aws",
            repo_target="tf-devops",
            workflow="aws_module_consumer",
        )
        main_content = github_get_file_content(
            "aws",
            main_path,
            env_branch,
            repo_target="tf-devops",
            workflow="aws_module_consumer",
        )
        if main_content is not None:
            branch = env_branch
    if main_content is None:
        raise ValueError(
            f"The selected-module workflow requires the live target consumer file {main_path}, but it was not found."
        )

    verified = dict(verified)
    verified.update({
        "selected_by_user": True,
        "selection_state": "selected",
        "tf_files": module_tf_paths,
        "module_files": module_files,
        "all_tf_file_contents": module_files,
        "environment_path": environment_path,
        "consumer_target_file": main_path,
        "instructions": [
            "This module was explicitly selected by the user; do not rediscover or re-ask for a module.",
            "Use every module_files entry as authoritative module implementation evidence.",
            f"Generate only the new consumer invocation in {main_path}.",
            "The consumer change is append-only: preserve every existing main.tf line and append one new sibling module block.",
        ],
    })
    target_context = {
        "source": "backend_aws_selected_module_generation_context",
        "cloud": "aws",
        "repo_target": "tf-devops",
        "workflow": "aws_module_consumer",
        "selection_state": "selected",
        "module_path": module_path,
        "module_source": verified.get("module_source") or build_aws_local_module_source(module_path, environment_path),
        "environment_path": environment_path,
        "target_file": main_path,
        "path": main_path,
        "content": main_content,
        "context_ref": branch,
        "instruction": (
            "Foundry must return the complete final target main.tf with the existing content preserved and exactly one new module consumer appended."
        ),
    }
    return verified, target_context
_aws_selected_module_context_with_contents = _aws_selected_module_context_with_contents_stage1


def _aws_selected_module_value_context(selected_match: dict, discovery: dict, environment_path: str) -> dict:
    module_path = (selected_match.get("module_path") or selected_match.get("verified_module_path") or "").strip()
    if module_path.startswith(f"{AWS_MODULES_ROOT}/"):
        module_path = module_path[len(f"{AWS_MODULES_ROOT}/"):]
    module_path = _sanitize_aws_module_rel_path(module_path)
    environment_path = (environment_path or "terraform/dev_aws/minidev").strip().strip("/")
    return {
        "source": "backend_aws_module_selection_confirmed",
        "cloud": "aws",
        "repo_target": "tf-devops",
        "workflow": "aws_module_consumer",
        "module_path": module_path,
        "module_source": selected_match.get("module_source") or build_aws_local_module_source(module_path, environment_path),
        "environment_path": environment_path,
        "repo_full_name": discovery.get("repo_full_name") or f"{GITHUB_OWNER}/{GITHUB_AWS_REPO}",
        "resolved_ref": discovery.get("resolved_ref") or _aws_module_catalog_branch(),
        "instructions": [
            "Use only this selected AWS module for the consumer invocation.",
            "Do not create a new AWS module while this selected verified module exists.",
        ],
    }


def _get_confirmed_aws_module_selection(retrieved_value_context: list | None) -> dict:
    for item in retrieved_value_context or []:
        if isinstance(item, dict) and item.get("source") == "backend_aws_module_selection_confirmed":
            return item
    return {}


def _aws_created_module_paths_from_files(files: list[dict]) -> set[str]:
    created = set()
    prefix = f"{AWS_MODULES_ROOT}/"
    for file_data in files or []:
        filename = normalize_tf_relative_path((file_data or {}).get("filename") or "")
        if not filename.startswith(prefix):
            continue
        rest = filename[len(prefix):]
        parts = [part for part in rest.split("/") if part]
        if len(parts) < 2:
            continue
        module_rel_path = _sanitize_aws_module_rel_path("/".join(parts[:-1]))
        if module_rel_path:
            created.add(module_rel_path)
    return created


def _aws_consumer_files_from_agent_result(agent_result_or_files) -> list[dict]:
    files = agent_result_or_files.get("files") if isinstance(agent_result_or_files, dict) else agent_result_or_files
    result = []
    for file_data in files or []:
        filename = normalize_tf_relative_path((file_data or {}).get("filename") or "")
        if filename.startswith("terraform/") and not filename.startswith(f"{AWS_MODULES_ROOT}/"):
            result.append(file_data)
    return result



def _aws_module_variable_files_from_result(files: list[dict], module_rel_path: str) -> list[dict]:
    prefix = f"{AWS_MODULES_ROOT}/{module_rel_path.strip('/')}/"
    result = []
    for file_data in files or []:
        filename = normalize_tf_relative_path((file_data or {}).get("filename") or "")
        if not filename.startswith(prefix):
            continue
        basename = _aws_module_variable_filename_from_path(filename)
        if basename:
            result.append({
                "filename": filename,
                "basename": basename,
                "file": file_data,
            })
    return result


def validate_aws_module_variable_file_convention(cleaned_files: list[dict], module_rel_path: str, user_prompt: str = "") -> None:
    convention = detect_aws_module_variable_file_convention(user_prompt)
    preferred = convention.get("preferred_variable_file_name") or "vars.tf"
    variable_files = _aws_module_variable_files_from_result(cleaned_files, module_rel_path)

    if not variable_files:
        raise ValueError(
            f"aws_module_creation must create exactly one module variable file named {preferred} under "
            f"{AWS_MODULES_ROOT}/{module_rel_path}/."
        )

    if len(variable_files) > 1:
        names = ", ".join(item["filename"] for item in variable_files)
        raise ValueError(
            "aws_module_creation must not generate both vars.tf and variables.tf for the same module. "
            f"Detected: {names}. The backend-detected tf-devops convention is {preferred}."
        )

    actual = variable_files[0]["basename"]
    if actual != preferred:
        raise ValueError(
            f"aws_module_creation generated {actual}, but backend live GitHub scan selected {preferred} "
            f"as the tf-devops module variable file convention. Generate only {AWS_MODULES_ROOT}/{module_rel_path}/{preferred}."
        )

def validate_aws_module_creation_payload(cleaned_files: list[dict], user_prompt: str = "") -> list[dict]:
    created_module_paths = _aws_created_module_paths_from_files(cleaned_files)
    if not created_module_paths:
        raise ValueError(
            f"aws_module_creation must create at least one module implementation .tf file under {AWS_MODULES_ROOT}/<module_name>/ ."
        )

    if len(created_module_paths) != 1:
        raise ValueError("aws_module_creation must create exactly one new AWS module path per request.")

    new_module_path = next(iter(created_module_paths))
    if github_verified_aws_module_exists(new_module_path):
        raise ValueError(
            f"AWS module {AWS_MODULES_ROOT}/{new_module_path} already exists. Use aws_module_consumer instead of creating it again."
        )

    validate_aws_module_variable_file_convention(
        cleaned_files,
        new_module_path,
        user_prompt=user_prompt,
    )

    consumer_files = _aws_consumer_files_from_agent_result(cleaned_files)
    if not consumer_files:
        raise ValueError(
            "aws_module_creation must also create or update one consumer .tf file under terraform/ outside terraform/modules/."
        )

    found_new_module_reference = False
    bad_sources = []
    for file_data in consumer_files:
        filename = normalize_tf_relative_path(file_data.get("filename") or "")
        consumer_folder = filename.rsplit("/", 1)[0] if "/" in filename else "terraform"
        expected_source = build_aws_local_module_source(new_module_path, consumer_folder)
        teams_full_file_mode = bool((_ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}).get("active"))
        for ref in _extract_aws_module_source_refs_from_text(file_data.get("content") or ""):
            source = ref.get("source") or ""
            module_path = ref.get("module_path") or ""
            if module_path == new_module_path:
                found_new_module_reference = True
                normalized_source = source.replace("\\", "/").rstrip("/")
                if normalized_source != expected_source:
                    bad_sources.append(
                        f"{filename}: module.{ref.get('module_name') or '<unknown>'} must use source = \"{expected_source}\", not \"{source}\""
                    )
            elif teams_full_file_mode:
                # Teams commits complete live consumer files. Existing sibling
                # module blocks are repository truth and may legitimately use
                # external or legacy sources. They are unrelated to this new
                # module request, so validate only the newly introduced module
                # source instead of rejecting the full file for old content.
                continue
            elif module_path and not github_verified_aws_module_exists(module_path):
                bad_sources.append(
                    f"{filename}: module.{ref.get('module_name') or '<unknown>'} references unverified module source \"{source}\""
                )
            elif not module_path:
                bad_sources.append(
                    f"{filename}: module.{ref.get('module_name') or '<unknown>'} has non-local or missing source \"{source}\""
                )

    if bad_sources:
        raise ValueError("Invalid AWS module creation source path. " + "; ".join(bad_sources))

    if not found_new_module_reference:
        raise ValueError(
            f"aws_module_creation must add a consumer module block that references {AWS_MODULES_ROOT}/{new_module_path}."
        )

    cleaned_files, variable_issues = normalize_generated_module_variable_files(
        cleaned_files,
        "aws_module_creation",
        user_prompt=user_prompt,
    )
    if variable_issues:
        raise ModuleVariableValuesRequired(
            cleaned_files,
            variable_issues,
            workflow="aws_module_creation",
        )

    return cleaned_files


def _build_agent_input_for_aws_module_creation_base(
    prompt: str,
    proposed_module_path: str,
    environment_path: str,
    discovery: dict | None = None,
) -> str:
    proposed_module_path = _sanitize_aws_module_rel_path(proposed_module_path) or infer_new_aws_module_path(prompt, discovery)
    environment_path = (environment_path or "terraform/dev_aws/minidev").strip().strip("/")
    module_root = f"{AWS_MODULES_ROOT}/{proposed_module_path}"
    consumer_source = build_aws_local_module_source(proposed_module_path, environment_path)
    module_name = proposed_module_path.replace("/", "_").replace("-", "_")
    consumer_filename = f"{environment_path}/{module_name}.tf"

    backend_variable_declaration_context = build_backend_variable_declaration_context(
        prompt=prompt,
        cloud="aws",
        workflow="aws_module_creation",
        retrieved_module_context=[],
        retrieved_value_context=[],
    )
    module_variable_file_name = backend_variable_declaration_context.get("module_variable_file_name") or "vars.tf"

    payload = {
        "request_type": "terraform_update_or_generation",
        "target_cloud": "aws",
        "workflow": "aws_module_creation",
        "user_request": prompt,
        "proposed_new_module_path": proposed_module_path,
        "backend_variable_declaration_context": backend_variable_declaration_context,
        "required_output_shape": {
            "mode": "infra",
            "cloud": "aws",
            "workflow": "aws_module_creation",
            "repo_target": "tf-devops",
            "title": "[AWS] Create new AWS module and consumer reference",
            "summary": "Create a new AWS module and reference it from the selected terraform environment.",
            "files": [
                {"filename": f"{module_root}/main.tf", "content": "..."},
                {"filename": f"{module_root}/{module_variable_file_name}", "content": "..."},
                {"filename": f"{module_root}/outputs.tf", "content": "..."},
                {"filename": consumer_filename, "content": "..."},
            ],
        },
        "instructions": [
            "Return valid JSON only. Do not include markdown or commentary.",
            "Set cloud='aws', workflow='aws_module_creation', and repo_target='tf-devops'.",
            f"Create the new module implementation only under {module_root}/ using .tf files.",
            f"Create or update exactly one consumer .tf file under {environment_path}/.",
            f"The consumer module block must use source = \"{consumer_source}\" exactly.",
            f"The consumer module block name should be \"{module_name}\" unless a clearer Terraform-safe name is required.",
            "Do not reference a module path that does not either already exist in tf-devops/terraform/modules or match the proposed_new_module_path.",
            "Do not use remote module sources such as GitHub URLs, registry sources, git::, http, or ssh.",
            "Do not create provider, backend, terraform cloud, or .terraform files.",
            f"Create exactly one module variable declaration file named {module_variable_file_name}; do not create both vars.tf and variables.tf.",
            "The module variable file must follow backend_variable_declaration_context exactly.",
            "Every variable block must include description and type, in that order, followed by default when present.",
            "Never emit a variable block with only description.",
            "For bool variables, use default = false unless the user explicitly provided a different non-sensitive boolean value.",
            "For number variables, use default = -1 unless the user explicitly provided a different non-sensitive numeric value.",
            "For map variables, use default = {}; for list/set variables, use default = []; for object variables, use default = null unless a full safe object default is backend-approved.",
            "For string variables, include default only when the value was explicitly provided by the user or is backend-approved from GitHub context; otherwise ask for the string value/reference before returning JSON.",
            "Never invent account-specific IDs such as AMI IDs, subnet IDs, VPC IDs, KMS keys, ARNs, account IDs, or security group IDs. Use backend-approved repo references or ask for missing values/references.",
            "Keep the implementation minimal and reviewable. The goal is to create an approved reusable module and a consumer reference, not to guess environment-specific values.",
            "Every file path must be repo-relative and under terraform/.",
        ],
        "verified_absence": {
            "module_root_checked": AWS_MODULES_ROOT,
            "status": (discovery or {}).get("status"),
            "catalog_count": (discovery or {}).get("catalog_count"),
            "requested_resource_hint": (discovery or {}).get("requested_resource_hint"),
        },
    }
    return json.dumps(payload, indent=2)


def generate_aws_module_creation_with_agent(
    conversation_id: str,
    original_prompt: str,
    proposed_module_path: str,
    environment_path: str,
    discovery: dict | None = None,
) -> dict:
    agent_input = build_agent_input_for_aws_module_creation(
        prompt=original_prompt,
        proposed_module_path=proposed_module_path,
        environment_path=environment_path,
        discovery=discovery,
    )
    _conversation_id, agent_reply = call_agent(conversation_id, agent_input)
    if not agent_reply.strip():
        raise RuntimeError("No response returned from agent for AWS module creation.")

    try:
        agent_result = try_parse_agent_output(agent_reply)
    except Exception as parse_error:
        try:
            recovered_payload = extract_json_from_text(agent_reply)
            if not isinstance(recovered_payload, dict):
                raise parse_error

            # The deployed Foundry instructions can return the VS Code-style
            # infrastructure envelope with `path` instead of `filename` and
            # without backend routing keys. In this AWS module-creation path the
            # routing is already known deterministically, so normalize that
            # envelope instead of failing with "cloud must be aws or azure".
            recovered_payload.setdefault("mode", "infra")
            recovered_payload.setdefault("cloud", "aws")
            recovered_payload.setdefault("workflow", "aws_module_creation")
            recovered_payload.setdefault("repo_target", "tf-devops")
            recovered_payload.setdefault("title", "[AWS] Create new AWS module and consumer reference")
            recovered_payload.setdefault(
                "summary",
                "Create a new AWS module and reference it from the selected terraform environment.",
            )
            normalized_files = []
            for file_data in recovered_payload.get("files") or []:
                if not isinstance(file_data, dict):
                    continue
                item = dict(file_data)
                if not item.get("filename") and item.get("path"):
                    item["filename"] = item.get("path")
                normalized_files.append(item)
            recovered_payload["files"] = normalized_files
            agent_result = parse_agent_output(json.dumps(recovered_payload))
        except Exception as recovery_error:
            raise ValueError(
                "The agent returned invalid AWS module creation JSON. "
                "No PR preview was created. "
                f"Original parse error: {parse_error}. Recovery error: {recovery_error}"
            )

    if agent_result.get("workflow") != "aws_module_creation":
        raise ValueError("AWS new module generation returned the wrong workflow.")

    try:
        agent_result["files"] = validate_aws_module_creation_payload(
            agent_result.get("files") or [],
            user_prompt=original_prompt,
        )
    except ModuleVariableValuesRequired as variable_error:
        agent_result["files"] = variable_error.files
        agent_result["cloud"] = "aws"
        agent_result["workflow"] = "aws_module_creation"
        agent_result["repo_target"] = "tf-devops"
        agent_result["state_bucket"] = state_bucket_for_target("aws", "tf-devops", "aws_module_creation")
        agent_result["user_prompt"] = original_prompt or ""
        agent_result["_module_variable_values_required"] = True
        agent_result["_module_variable_issues"] = variable_error.issues
        return agent_result

    agent_result["user_prompt"] = original_prompt or ""
    return finalize_agent_result_after_parse(agent_result, retrieved_module_context=[])


def add_grounded_aws_module_context(
    prompt: str,
    environment_path: str,
    retrieved_module_context: list,
    retrieved_value_context: list,
) -> tuple[list[dict], list[dict], dict]:
    discovery = discover_live_aws_module_candidates(
        prompt,
        environment_path=environment_path,
    )

    retrieved_module_context = list(retrieved_module_context or [])
    existing_paths = {
        (item.get("module_path") or item.get("verified_module_path") or "").strip()
        for item in retrieved_module_context
        if isinstance(item, dict) and item.get("cloud") == "aws"
    }

    for match in discovery.get("matches") or []:
        module_path = (match.get("module_path") or "").strip()
        verified_path = (match.get("verified_module_path") or "").strip()
        if module_path and module_path not in existing_paths and verified_path not in existing_paths:
            retrieved_module_context.append(match)
            existing_paths.add(module_path)
            existing_paths.add(verified_path)

    retrieved_value_context = list(retrieved_value_context or [])
    retrieved_value_context.append({
        "source": "backend_aws_module_discovery",
        "repo_target": "tf-devops",
        "repo_full_name": discovery.get("repo_full_name"),
        "module_root": discovery.get("module_root"),
        "resolved_ref": discovery.get("resolved_ref"),
        "status": discovery.get("status"),
        "matched_module_paths": [match.get("module_path") for match in discovery.get("matches") or []],
        "available_module_paths_sample": discovery.get("available_module_paths_sample") or [],
        "catalog_count": discovery.get("catalog_count") or 0,
    })

    # Teams repository placement/module reuse is backend-resolvable context, not
    # a user decision. Once semantic filtering leaves exactly one verified live
    # module, mark it selected immediately so the core generation path does not
    # emit an unnecessary "choose a module/path" clarification. Non-Teams keeps
    # the existing interactive behavior unchanged.
    active = _ACTIVE_TEAMS_FLOW_CONTEXT.get() or {}
    matches = [item for item in discovery.get("matches") or [] if isinstance(item, dict)]
    if (
        active.get("active")
        and discovery.get("status") in {"exact_match", "similar_match"}
        and len(matches) == 1
        and not _get_confirmed_aws_module_selection(retrieved_value_context)
    ):
        retrieved_value_context.append(
            _aws_selected_module_value_context(
                matches[0],
                discovery,
                environment_path,
            )
        )
        discovery = dict(discovery)
        discovery["status"] = "selected"
        discovery["decision_state"] = "aws_module_selected"
        discovery["auto_selected_for_teams"] = True

    return retrieved_module_context, retrieved_value_context, discovery


def _verified_aws_module_paths_from_context(retrieved_module_context: list) -> set[str]:
    verified = set()
    for item in retrieved_module_context or []:
        if not isinstance(item, dict) or item.get("cloud") != "aws":
            continue
        for key in ("module_path", "verified_module_path"):
            value = (item.get(key) or "").strip()
            if not value:
                continue
            normalized = _sanitize_aws_module_rel_path(value)
            if normalized:
                verified.add(normalized)
    return verified


def enforce_verified_aws_module_sources(agent_result: dict, retrieved_module_context: list) -> dict:
    if not isinstance(agent_result, dict):
        return agent_result

    if safe_normalize_cloud(agent_result.get("cloud")) != "aws":
        return agent_result

    if normalize_repo_target(
        "aws",
        repo_target=agent_result.get("repo_target"),
        workflow=agent_result.get("workflow"),
    ) != "tf-devops":
        return agent_result

    verified_paths = _verified_aws_module_paths_from_context(retrieved_module_context)
    created_module_paths = _aws_created_module_paths_from_files(agent_result.get("files") or [])
    branch = _aws_module_catalog_branch()
    unverified = []
    external_or_missing = []

    for file_data in agent_result.get("files") or []:
        for ref in _extract_aws_module_source_refs_from_text(file_data.get("content") or ""):
            source = ref.get("source") or ""
            module_path = ref.get("module_path") or ""
            module_name = ref.get("module_name") or ""
            if not source:
                external_or_missing.append(f"module.{module_name or '<unknown>'} is missing source")
                continue
            if not module_path:
                external_or_missing.append(f"module.{module_name or '<unknown>'} source '{source}' is not a local tf-devops modules source")
                continue

            if module_path in created_module_paths:
                continue

            if module_path not in verified_paths:
                if github_verified_aws_module_exists(module_path, branch=branch):
                    verified_paths.add(module_path)
                else:
                    unverified.append(f"module.{module_name or '<unknown>'} source '{source}' -> terraform/modules/{module_path}")

    if external_or_missing:
        raise ValueError(
            "AWS module blocks must use verified local tf-devops modules only. "
            + "; ".join(external_or_missing)
        )

    if unverified:
        raise ValueError(
            "Unverified AWS module source detected. The backend checked tf-devops/terraform/modules and no PR was created. "
            + "; ".join(unverified)
        )

    if (agent_result.get("workflow") or "").strip() == "aws_module_creation" and not agent_result.get("_module_variable_values_required"):
        agent_result["files"] = validate_aws_module_creation_payload(
            agent_result.get("files") or [],
            user_prompt=agent_result.get("user_prompt") or agent_result.get("summary") or "",
        )

    return agent_result


def _add_backend_existing_aws_infra_context_base(
    prompt: str,
    environment_path: str,
    branch: str,
    retrieved_value_context: list | None = None,
) -> list:
    """Attach exact existing tf-devops files for AWS update/delete/fix prompts.

    The agent needs full current file contents so it can change an existing line
    instead of generating a new snippet. This context is backend-owned and comes
    from live GitHub reads.
    """
    retrieved_value_context = list(retrieved_value_context or [])
    env_path = (environment_path or "").strip().strip("/")
    if not env_path:
        return retrieved_value_context

    try:
        existing_files = load_existing_tf_files_for_context("aws", branch, env_path)
    except Exception as exc:
        print(f"Could not load AWS existing infra context from {env_path}@{branch}: {exc}")
        existing_files = []

    matched_files = []
    for item in existing_files or []:
        filename = item.get("filename") or ""
        content = item.get("content") or ""
        if not filename or not content:
            continue
        full_path = filename if filename.startswith("terraform/") else f"{env_path}/{filename}".replace("//", "/")
        matched_files.append({
            "path": full_path,
            "filename": filename,
            "content": content,
        })

    if matched_files:
        retrieved_value_context.append({
            "source": "backend_existing_infra_code_match",
            "cloud": "aws",
            "repo_target": "tf-devops",
            "workflow": "aws_infra_modification",
            "environment_path": env_path,
            "matched_files": matched_files,
            "instruction": "Use these existing files as the only source of truth. Edit only the requested existing resource/module/value and return changed files with full final content.",
        })

    return retrieved_value_context



def _infra_mod_selection_key(thread_id: str, ticket_number: str = "") -> str:
    return f"{str(thread_id or '').strip()}::{str(ticket_number or '').strip().upper()}"


def store_pending_infra_modification_selection(
    thread_id: str,
    ticket_number: str,
    original_prompt: str,
    cloud: str,
    workflow: str,
    retrieved_module_context: list,
    retrieved_value_context: list,
    existing_infra_context: dict,
    ticket_link: str = "",
    ticket_title: str = "",
):
    key = _infra_mod_selection_key(thread_id, ticket_number)
    PENDING_INFRA_MODIFICATION_SELECTIONS[key] = {
        "thread_id": thread_id,
        "ticket_number": (ticket_number or "").strip().upper(),
        "original_prompt": original_prompt,
        "cloud": cloud,
        "workflow": workflow,
        "retrieved_module_context": list(retrieved_module_context or []),
        "retrieved_value_context": list(retrieved_value_context or []),
        "existing_infra_context": existing_infra_context or {},
        "ticket_link": ticket_link or "",
        "ticket_title": ticket_title or "",
    }
    return key


def get_pending_infra_modification_selection(thread_id: str, ticket_number: str = "") -> dict:
    return PENDING_INFRA_MODIFICATION_SELECTIONS.get(
        _infra_mod_selection_key(thread_id, ticket_number),
        {},
    )


def clear_pending_infra_modification_selection(thread_id: str, ticket_number: str = ""):
    PENDING_INFRA_MODIFICATION_SELECTIONS.pop(
        _infra_mod_selection_key(thread_id, ticket_number),
        None,
    )


def _get_backend_existing_infra_context(retrieved_value_context: list | None) -> dict:
    selected = {}
    first = {}
    for item in retrieved_value_context or []:
        if not (isinstance(item, dict) and item.get("source") == "backend_existing_infra_code_match"):
            continue
        if item.get("selection_state") == "selected":
            selected = item
            break
        if not first:
            first = item
    return selected or first


def _remove_backend_existing_infra_contexts(retrieved_value_context: list | None) -> list:
    return [
        item for item in list(retrieved_value_context or [])
        if not (isinstance(item, dict) and item.get("source") == "backend_existing_infra_code_match")
    ]


def _backend_existing_infra_context_is_selected_stage1(context: dict | None) -> bool:
    return bool(
        isinstance(context, dict)
        and context.get("source") == "backend_existing_infra_code_match"
        and context.get("selection_state") == "selected"
        and len(context.get("matched_files") or []) == 1
    )
_backend_existing_infra_context_is_selected = _backend_existing_infra_context_is_selected_stage1


def _infra_modification_search_terms(prompt: str) -> list[str]:
    text = re.sub(r"\s+", " ", (prompt or "").strip().lower())
    terms = []
    phrases = {
        "password policy": ["password_policy", "aws_password_policy"],
        "hard expiry": ["hard_expiry"],
        "public access": ["public_access", "public_access_block"],
        "instance type": ["instance_type"],
        "storage tier": ["account_tier", "storage_account_tier"],
        "function app": ["function_app"],
    }
    for phrase, values in phrases.items():
        if phrase in text:
            terms.extend(values)
    stop = {
        "aws", "azure", "terraform", "resource", "module", "policy", "change", "update", "set", "modify",
        "delete", "remove", "fix", "refactor", "enable", "disable", "increase", "decrease", "to", "the", "a",
        "an", "in", "on", "for", "of", "and", "or", "true", "false", "root", "global", "please",
    }
    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_./-]*", prompt or ""):
        token = token.strip("`'\".,:;()[]{} ").lower().replace("-", "_")
        if len(token) >= 3 and token not in stop:
            terms.append(token)
    result = []
    for term in terms:
        if term and term not in result:
            result.append(term)
    return result[:12]


def _explicit_iac_paths_from_prompt(prompt: str) -> list[str]:
    paths = []
    for match in re.finditer(r"(?<![A-Za-z0-9_./-])([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+\.(?:tf|tfvars))(?![A-Za-z0-9_./-])", prompt or ""):
        path = match.group(1).strip("`'\" ")
        if path and path not in paths:
            paths.append(path)
    return paths


def _matched_blocks_for_prompt(content: str, terms: list[str], max_blocks: int = 6) -> list[dict]:
    result = []
    lowered_terms = [str(term or "").lower() for term in terms or [] if str(term or "").strip()]
    if str(content or "").lstrip().startswith(("#", "//")) and not content:
        return result
    for block in _extract_top_level_tf_blocks(content or ""):
        header = block.get("header") or ""
        block_text = block.get("block") or ""
        haystack = f"{header}\n{block_text}".lower()
        if not lowered_terms or any(term in haystack for term in lowered_terms):
            result.append({"header": header, "block": block_text})
        if len(result) >= max_blocks:
            break
    return result


def _score_infra_candidate(path: str, content: str, terms: list[str], prompt: str) -> int:
    haystack = f"{path}\n{content}".lower()
    score = 0
    for term in terms or []:
        if term.lower() in haystack:
            score += 20
    prompt_l = (prompt or "").lower()
    if "password" in prompt_l and "password_policy" in haystack:
        score += 200
    if "hard" in prompt_l and "hard_expiry" in haystack:
        score += 150
    if ("root global" in prompt_l or "root/global" in prompt_l) and str(path).startswith("terraform/root/global/"):
        score += 200
    return score


def _build_backend_existing_infra_modification_context_base(
    prompt: str,
    thread_id: str,
    cloud: str,
    workflow: str,
    retrieved_value_context: list | None = None,
) -> dict:
    del thread_id
    cloud = normalize_cloud(cloud)
    repo_target = normalize_repo_target(cloud, workflow=workflow)
    branch = github_base_branch_for_cloud(cloud, repo_target=repo_target, workflow=workflow)
    repo_full_name = f"{GITHUB_OWNER}/{github_repo_for_cloud(cloud, repo_target=repo_target, workflow=workflow)}"
    terms = _infra_modification_search_terms(prompt)
    seen_paths = set()
    matched_files = []

    def add_path(path: str, reason: str):
        path = (path or "").strip().strip("/")
        if not path or path in seen_paths:
            return
        if not (path.endswith(".tf") or path.endswith(".tfvars")):
            return
        try:
            content = github_get_file_content(cloud, path, branch, repo_target=repo_target, workflow=workflow)
        except Exception:
            content = None
        if not content:
            return
        score = _score_infra_candidate(path, content, terms, prompt)
        if score <= 0 and terms:
            return
        seen_paths.add(path)
        matched_files.append({
            "path": path,
            "filename": path.rsplit("/", 1)[-1],
            "content": content,
            "matched_blocks": _matched_blocks_for_prompt(content, terms),
            "reason": reason,
            "score": score,
        })

    for path in _explicit_iac_paths_from_prompt(prompt):
        add_path(path, "exact path mentioned by user")

    queries = []
    for term in terms[:8]:
        queries.append(f'repo:{repo_full_name} "{term}" extension:tf')
        queries.append(f'repo:{repo_full_name} "{term}" extension:tfvars')
    if not queries:
        queries.append(f'repo:{repo_full_name} extension:tf')

    unique_queries = []
    for query in queries:
        if query not in unique_queries:
            unique_queries.append(query)

    for query in unique_queries[:18]:
        try:
            items = github_search_code(query, per_page=25)
        except Exception as exc:
            print(f"Existing infra GitHub search failed for {query!r}: {exc}")
            items = []
        for item in items or []:
            repo = ((item or {}).get("repository") or {}).get("full_name") or ""
            if repo and repo.lower() != repo_full_name.lower():
                continue
            add_path((item or {}).get("path") or "", f"github code search: {query}")

    matched_files.sort(key=lambda item: (-int(item.get("score") or 0), item.get("path") or ""))
    for item in matched_files:
        item.pop("score", None)

    return {
        "source": "backend_existing_infra_code_match",
        "selection_state": "candidate_selection_required",
        "cloud": cloud,
        "repo_target": repo_target,
        "workflow": workflow,
        "repo_full_name": repo_full_name,
        "context_ref": branch,
        "search_terms": terms,
        "matched_files": matched_files[:12],
        "matched_file_paths": [item.get("path") for item in matched_files[:12] if item.get("path")],
        "instructions": [
            "User must select exactly one existing Terraform target before generation.",
            "Do not call the agent with all candidate files for modification generation.",
        ],
    }


def _summarize_matched_blocks_for_selection(matched_file: dict, max_blocks: int = 4) -> str:
    headers = []
    for block in (matched_file.get("matched_blocks") or [])[:max_blocks]:
        if isinstance(block, dict) and (block.get("header") or "").strip():
            headers.append((block.get("header") or "").strip())
    return ", ".join(headers) if headers else "matched file"


def build_infra_modification_selection_reply_stage1(existing_infra_context: dict) -> str:
    lines = [
        "I found existing Terraform code that may match your modification request.",
        "Select the exact file/resource you want to modify. I will only change the selected path.",
        "",
        f"Cloud: {existing_infra_context.get('cloud') or ''}",
        f"Workflow: {existing_infra_context.get('workflow') or ''}",
        "",
    ]
    for index, item in enumerate(existing_infra_context.get("matched_files") or [], start=1):
        lines.append(f"{index}. `{item.get('path') or ''}`")
        lines.append(f"   Match: {_summarize_matched_blocks_for_selection(item)}")
        lines.append(f"   Reason: {item.get('reason') or 'backend GitHub match'}")
    lines.append("")
    lines.append("Reply with the option number or the exact path to modify.")
    return "\n".join(lines)
build_infra_modification_selection_reply = build_infra_modification_selection_reply_stage1


def select_infra_modification_candidate_from_reply_stage1(reply: str, pending_selection: dict) -> int | None:
    text = (reply or "").strip()
    candidates = ((pending_selection.get("existing_infra_context") or {}).get("matched_files") or [])
    if not text:
        return None
    number_match = re.fullmatch(r"\s*(?:option|select|choose|pick)?\s*#?(\d+)\s*", text, re.IGNORECASE)
    if number_match:
        index = int(number_match.group(1)) - 1
        if 0 <= index < len(candidates):
            return index
    normalized = text.strip("`'\" ").lower()
    for index, candidate in enumerate(candidates):
        path = (candidate.get("path") or "").strip()
        if path and (path.lower() == normalized or path.lower() in normalized):
            return index
    return None
select_infra_modification_candidate_from_reply = select_infra_modification_candidate_from_reply_stage1

_TEAMS_ENV_EVIDENCE_MAX_FILES = 40
_TEAMS_ENV_EVIDENCE_PER_FILE_CHARS = 20_000
_TEAMS_ENV_EVIDENCE_TOTAL_CHARS = 120_000
_TEAMS_VALUE_WALK_MAX_DIRS = 120
_TEAMS_VALUE_WALK_MAX_DEPTH = 6
_TEAMS_VALUE_WALK_MAX_FILES = 200

_TEAMS_ENV_TOKEN_STOPWORDS = {
    "create", "creating", "update", "modify", "using", "use", "existing",
    "module", "modules", "terraform", "resource", "resources", "app", "apps",
    "aca", "the", "for", "with", "name", "named", "whose", "enable",
    "disable", "new", "want", "you", "and", "values", "value", "please",
    # Cloud/resource words are not environment names. Keeping them in the
    # token set made repo-wide environment discovery match folders/files for
    # EC2/AWS/instance before it reached the real environment directory.
    "aws", "amazon", "ec2", "instance", "instances", "s3", "rds", "iam",
    "vpc", "subnet", "eks", "lambda", "cloudamqp", "rabbitmq", "bucket",
}


