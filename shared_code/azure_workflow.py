"""Azure backend workflow helpers for Terrabot.

This module intentionally contains Azure-only backend workflow state, GitHub
discovery, branch/ref selection, tf-azure-hub source matching, tfvars routing,
and Azure module repository automation helpers. It must not perform generic
cloud intent recognition. Intent-Terraform remains the authority for user
intent and Terraform JSON generation; terrabot_service.py dispatches here only
when the active backend state or Intent-Terraform result is Azure.
"""

import hashlib
import re

PENDING_AZURE_MODULE_DISCOVERIES = {}

AFFIRMATIVE_REPLIES = {"yes", "y", "use it", "reference it", "go ahead", "proceed", "continue"}
NEGATIVE_REPLIES = {"no", "n", "dont use it", "don't use it", "skip it", "not now", "cancel"}


def normalize_yes_no_reply(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).lower()


def _normalize_free_text(value: str) -> str:
    return normalize_yes_no_reply(value)


def _tokenize_for_match(value: str) -> list[str]:
    text = _normalize_free_text(value).replace("_", " ").replace("-", " ")

    replacements = {
        "linux virtual machine": "linux vm",
        "windows virtual machine": "windows vm",
        "virtual machine": "vm",
        "linux mv": "linux vm",
        "azure linux mv": "linux vm",
        "vmss": "scale set",
        "virtual machine scale set": "scale set",
        "virtual machine scale sets": "scale set",
        "scale sets": "scale set",
        "azure functions app": "function app",
        "azure function app": "function app",
        "linux function app": "function app",
        "windows function app": "function app",
        "function apps": "function app",
        "functions apps": "function app",
        "functions app": "function app",
        "functionapp": "function app",
        "functionapps": "function app",
        "function-app": "function app",
        "functions-app": "function app",
        "app services": "app service",
        "application gateway": "app gateway",
        "keyvault": "key vault",
        "postgresql": "postgres",
        "mssql": "sql",
        "sql server": "sql",
        "database": "db",
        "databases": "db",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    raw_tokens = re.findall(r"[a-z0-9]+", text)

    aliases = {
        "virtual": "vm",
        "machine": "vm",
        "mv": "vm",
        "vm": "vm",
        "linux": "linux",
        "windows": "windows",
        "scale": "scale",
        "sets": "set",
        "set": "set",
        "storage": "storage",
        "accounts": "account",
        "account": "account",
        "key": "key",
        "vault": "vault",
        "redis": "redis",
        "postgres": "postgres",
        "sql": "sql",
        "mysql": "mysql",
        "database": "db",
        "databases": "db",
        "db": "db",
        "network": "network",
        "networks": "network",
        "interface": "interface",
        "interfaces": "interface",
        "nic": "nic",
        "function": "function",
        "functions": "function",
        "func": "function",
        "fn": "function",
        "app": "app",
        "apps": "app",
        "application": "app",
        "applications": "app",
        "service": "service",
        "services": "service",
        "plan": "plan",
        "plans": "plan",
        "gateway": "gateway",
        "gateways": "gateway",
        "container": "container",
        "containers": "container",
        "registry": "registry",
        "registries": "registry",
        "private": "private",
        "endpoint": "endpoint",
        "endpoints": "endpoint",
        "dns": "dns",
        "zone": "zone",
        "zones": "zone",
    }

    stop_words = {
        "azure", "azurerm", "terraform", "tf", "module", "modules",
        "repo", "repository", "resource", "resources", "github",
        "create", "creating", "created", "new", "add", "adding",
        "update", "updating", "for", "with", "and", "or",
        "the", "a", "an", "to", "of", "in", "on", "using", "use",
        "need", "please", "from", "into", "this", "that", "it",
        "existing", "found", "do", "you", "want", "approved",
    }

    tokens = []
    for token in raw_tokens:
        token = aliases.get(token, token)
        if token in stop_words or len(token) <= 1:
            continue
        tokens.append(token)

    return _unique_preserve_order(tokens)


def _is_valid_github_repo_name(repo_name: str) -> bool:
    repo_name = (repo_name or "").strip()
    if not repo_name or repo_name in {".", ".."}:
        return False
    if repo_name.endswith(".git"):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_.-]+", repo_name))


def _looks_like_azure_module_repo_definition(
    filename: str,
    repo_name: str,
    description: str,
    tf_content: str,
    terraform_block: str = "",
) -> bool:
    filename_lower = (filename or "").lower()
    repo_name_lower = (repo_name or "").lower()
    description_lower = (description or "").lower()
    content_lower = (tf_content or "").lower()
    block_lower = (terraform_block or "").lower()

    if not _is_valid_github_repo_name(repo_name):
        return False

    is_repo_definition = (
        "../modules/repo" in content_lower
        or 'resource "github_repository"' in content_lower
        or "../modules/repo" in block_lower
        or 'resource "github_repository"' in block_lower
    )
    if not is_repo_definition:
        return False

    # Any valid vena_repos repository definition can be considered for Azure
    # module discovery. Matching/scoring below still decides whether it is
    # relevant to the user's Azure request, so custom repo names such as
    # "linux-vm" or "shared-network" are not excluded only because they do
    # not start with tf/tf_module.
    return True


AZURE_RESOURCE_CONTEXT_STOP_TOKENS = {
    "dev", "development", "test", "testing", "qa", "stage", "staging",
    "prod", "production", "prd", "nonprod", "non", "npr", "sbx",
    "sandbox", "common", "global", "shared", "tier", "env", "environment",
    "subscription", "tenant", "region", "regional", "east", "west",
    "north", "south", "central", "primary", "secondary", "dr",
    "name", "named", "called", "build", "built", "provision",
    "provisioning", "deploy", "deployment", "instance", "instances",
    "runtime", "runtime_stack", "python", "node", "nodejs", "dotnet",
    "java", "powershell", "sku", "size", "small", "medium", "large",
    "standard", "basic", "premium", "free", "consumption",
}

AZURE_REPO_NAME_QUALIFIER_TOKENS = {
    "azure", "azurerm", "tf", "terraform", "module", "modules",
    "repo", "repository", "github", "private", "public", "internal",
}

AZURE_GENERIC_RESOURCE_TOKENS = {"app", "service", "resource", "instance"}

AZURE_GENERIC_MODULE_REPO_NAMES = {
    "module",
    "modules",
    "repo",
    "repos",
    "repository",
    "repositories",
    "terraform-module",
    "terraform-modules",
    "tf-module",
    "tf-modules",
    "azure-module",
    "azure-modules",
    "tf-module-azure",
    "tf-modules-azure",
}


def _is_generic_azure_module_repo_name(repo_name: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "-", (repo_name or "").strip().lower()).strip("-")
    if not normalized:
        return True
    if normalized in AZURE_GENERIC_MODULE_REPO_NAMES:
        return True

    tokens = set(_azure_repo_name_match_tokens(normalized))
    return bool(tokens and tokens.issubset(AZURE_GENERIC_RESOURCE_TOKENS))


def _azure_requested_resource_tokens(prompt: str) -> list[str]:
    """Return resource-intent tokens from the user prompt.

    These tokens are used only for Azure module repo-name matching. Runtime
    context such as environment names, regions, and action verbs is ignored so
    a request like "create an Azure function app in npr" matches repo names for
    "function app" instead of unrelated repositories whose Terraform definition
    happens to mention "app" or "npr" in comments, CODEOWNERS, or status checks.
    """
    raw_tokens = []
    for token in _tokenize_for_match(prompt or ""):
        if token in AZURE_RESOURCE_CONTEXT_STOP_TOKENS:
            continue
        if token in AZURE_REPO_NAME_QUALIFIER_TOKENS:
            continue
        raw_tokens.append(token)

    token_set = set(raw_tokens)

    # Prefer known Azure resource phrases. This keeps "Linux Function App" on
    # the Function App repository instead of requiring "linux" in the repo name,
    # while still preserving OS-specific matching for Linux/Windows VMs.
    known_resource_phrases = [
        (["linux", "vm"], ["linux", "vm"]),
        (["windows", "vm"], ["windows", "vm"]),
        (["scale", "set"], ["scale", "set"]),
        (["function", "app"], ["function", "app"]),
        (["storage", "account"], ["storage", "account"]),
        (["key", "vault"], ["key", "vault"]),
        (["app", "service", "plan"], ["app", "service", "plan"]),
        (["app", "service"], ["app", "service"]),
        (["container", "app"], ["container", "app"]),
        (["container", "registry"], ["container", "registry"]),
        (["private", "endpoint"], ["private", "endpoint"]),
        (["app", "gateway"], ["app", "gateway"]),
        (["network", "interface"], ["network", "interface"]),
        (["dns", "zone"], ["dns", "zone"]),
    ]

    for required, canonical in known_resource_phrases:
        if set(required).issubset(token_set):
            return canonical

    return _unique_preserve_order(raw_tokens)


def _azure_repo_name_match_tokens(repo_name: str) -> list[str]:
    tokens = []
    for token in _tokenize_for_match(repo_name or ""):
        if token in AZURE_REPO_NAME_QUALIFIER_TOKENS:
            continue
        tokens.append(token)
    return _unique_preserve_order(tokens)


def _azure_repo_name_match_text(repo_name: str) -> str:
    tokens = _azure_repo_name_match_tokens(repo_name)
    return "-".join(tokens)


def _azure_token_present_in_repo_name(token: str, repo_tokens: set[str], repo_match_text: str) -> bool:
    token = (token or "").strip()
    if not token:
        return False
    if token in repo_tokens:
        return True
    # Last-resort boundary check for compact names that normalize to one token.
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", repo_match_text))


def score_azure_module_candidate(prompt: str, candidate: dict) -> tuple[int, str]:
    requested_tokens = _azure_requested_resource_tokens(prompt)
    if not requested_tokens:
        return 0, "none"

    repo_name = (candidate.get("repo_name") or "").strip()
    if _is_generic_azure_module_repo_name(repo_name):
        return 0, "none"

    repo_tokens_list = _azure_repo_name_match_tokens(repo_name)
    repo_tokens = set(repo_tokens_list)
    repo_match_text = _azure_repo_name_match_text(repo_name)

    if not repo_tokens:
        return 0, "none"

    matched_tokens = [
        token for token in requested_tokens
        if _azure_token_present_in_repo_name(token, repo_tokens, repo_match_text)
    ]

    if not matched_tokens:
        return 0, "none"

    # The match is intentionally repo-name-only. Do not score description,
    # Terraform file content, CODEOWNERS, branch checks, topics, or tf_path;
    # those caused unrelated app repos to appear for Function App requests.
    missing_tokens = [token for token in requested_tokens if token not in matched_tokens]

    if not missing_tokens:
        requested_phrase = "-".join(requested_tokens)
        phrase_bonus = 40 if requested_phrase and requested_phrase in repo_match_text else 0
        coverage_bonus = len(matched_tokens) * 25
        # Prefer a tighter repo-name match, but do not require tf/tf-module prefixes.
        extra_repo_tokens = max(0, len(repo_tokens_list) - len(requested_tokens))
        return 200 + coverage_bonus + phrase_bonus - extra_repo_tokens, "exact_match"

    # Single-token resource requests such as "redis" or "vnet" can still match
    # by repo name, because there is no second token to require. Multi-token
    # resource names must match every resource token in the repo name; otherwise
    # generic repos such as app services or serverless functions become false
    # positives for Function App requests.
    if len(requested_tokens) == 1 and matched_tokens:
        return 100 + len(matched_tokens), "exact_match"

    return 0, "none"


def discover_live_azure_module_candidates(
    user_prompt: str,
    github_owner: str,
    github_vena_dir: str,
    github_base_branch_for_cloud,
    github_list_tf_files_recursive,
    github_get_file_content,
    github_get_repo_metadata,
) -> dict:
    branch = github_base_branch_for_cloud(
        "azure",
        repo_target="vena_repos",
        workflow="azure_module_repo_creation",
    )

    discovery_root = github_vena_dir or "vena_repos"

    tf_paths = github_list_tf_files_recursive(
        cloud="azure",
        root_path=discovery_root,
        branch=branch,
        repo_target="vena_repos",
        workflow="azure_module_repo_creation",
    )

    print("Azure module discovery branch:", branch)
    print("Azure module discovery root:", discovery_root)
    print("Azure module discovery tf_paths sample:", tf_paths[:20])

    parsed_candidates = []

    for tf_path in tf_paths:
        tf_content = github_get_file_content(
            cloud="azure",
            path=tf_path,
            branch=branch,
            repo_target="vena_repos",
            workflow="azure_module_repo_creation",
        )

        if not tf_content:
            continue

        parsed = parse_vena_repo_creation_tf(
            tf_path,
            tf_content,
            github_owner=github_owner,
        )

        # Fallback: detect Vena module repo definitions even if parser misses formatting.
        if not parsed:
            lower = tf_content.lower()

            if (
                'module "' in lower
                and "../modules/repo" in lower
                and re.search(r'(?m)^\s*name\s*=\s*"[A-Za-z0-9_.-]+"', tf_content, re.IGNORECASE)
            ):
                repo_name_match = re.search(
                    r'(?m)^\s*name\s*=\s*"([^"]+)"',
                    tf_content,
                    re.IGNORECASE,
                )
                repo_name = repo_name_match.group(1).strip() if repo_name_match else ""

                description_match = re.search(
                    r'(?m)^\s*description\s*=\s*"([^"]+)"',
                    tf_content,
                    re.IGNORECASE,
                )
                description = (
                    description_match.group(1).strip()
                    if description_match
                    else f"Azure module repository for {repo_name}"
                )

                contains_azure = (
                    "azure" in tf_path.lower()
                    or "azure" in repo_name.lower()
                    or "azure" in description.lower()
                    or "azure" in tf_content.lower()
                )
                is_module_repo = _looks_like_azure_module_repo_definition(
                    tf_path.split("/")[-1],
                    repo_name,
                    description,
                    tf_content,
                    terraform_block=tf_content,
                )

                if repo_name and is_module_repo:
                    parsed = {
                        "tf_file": tf_path.split("/")[-1],
                        "tf_path": tf_path,
                        "filename": tf_path.split("/")[-1],
                        "terraform_resource_block": tf_content,
                        "repo_name": repo_name,
                        "repo_owner": github_owner,
                        "repo_full_name": f"{github_owner}/{repo_name}",
                        "repo_url": f"https://github.com/{github_owner}/{repo_name}",
                        "visibility": "private",
                        "description": description,
                        "contains_azure": contains_azure,
                        "resource_hints": _tokenize_for_match(
                            " ".join([repo_name, description, tf_path])
                        ),
                        "match_tokens": _tokenize_for_match(tf_content),
                        "is_module_repo": is_module_repo,
                    }

        if not parsed:
            continue

        if not parsed.get("is_module_repo"):
            continue
        if _is_generic_azure_module_repo_name(parsed.get("repo_name") or ""):
            continue

        score, match_type = score_azure_module_candidate(user_prompt, parsed)

        # Keep matching repo-name-only. Approved module repos may omit an
        # "azure", "tf", or "tf-module" prefix; the resource tokens from the
        # user's request still must be present in the repository name.
        if not parsed.get("contains_azure") and score <= 0:
            continue

        if score <= 0:
            repo_name_lower = (parsed.get("repo_name") or "").lower().replace("_", "-")
            prompt_tokens = set(_azure_requested_resource_tokens(user_prompt))

            fallback_match = (
                {"function", "app"}.issubset(prompt_tokens)
                and (
                    "function-app" in repo_name_lower
                    or "functions-app" in repo_name_lower
                    or ("function" in repo_name_lower and "app" in repo_name_lower)
                )
            ) or (
                {"linux", "vm"}.issubset(prompt_tokens)
                and (
                    "linux-vm" in repo_name_lower
                    or ("linux" in repo_name_lower and "vm" in repo_name_lower)
                )
            ) or (
                {"windows", "vm"}.issubset(prompt_tokens)
                and (
                    "windows-vm" in repo_name_lower
                    or ("windows" in repo_name_lower and "vm" in repo_name_lower)
                )
            ) or (
                {"scale", "set"}.issubset(prompt_tokens)
                and (
                    "scale-set" in repo_name_lower
                    or "vmss" in repo_name_lower
                    or "vm-scale" in repo_name_lower
                )
            )

            if not fallback_match:
                continue

            score = 50
            match_type = "similar_match"

        repo_metadata = github_get_repo_metadata(parsed["repo_owner"], parsed["repo_name"])
        if not repo_metadata:
            print(
                "Azure module discovery skipped missing repo:",
                parsed.get("repo_full_name"),
            )
            continue

        parsed["verified_repo_exists"] = True
        parsed["verified_default_branch"] = repo_metadata.get("default_branch") or "main"
        parsed["score"] = score
        parsed["match_type"] = match_type
        parsed_candidates.append(parsed)

    parsed_candidates.sort(
        key=lambda item: (
            0 if item.get("match_type") == "exact_match" else 1,
            -int(item.get("score") or 0),
            item.get("repo_name") or "",
        )
    )

    if parsed_candidates:
        top_match_type = parsed_candidates[0]["match_type"]
        top_matches = parsed_candidates[:5]

        return {
            "status": top_match_type,
            "decision_state": "azure_module_reference_confirmation",
            "requested_resource_hint": " ".join(_azure_requested_resource_tokens(user_prompt)[:6]),
            "searched_root": discovery_root,
            "matches": [
                {
                    "tf_file": item["tf_file"],
                    "tf_path": item["tf_path"],
                    "filename": item["filename"],
                    "terraform_resource_block": item["terraform_resource_block"],
                    "repo_name": item["repo_name"],
                    "repo_owner": item["repo_owner"],
                    "repo_full_name": item["repo_full_name"],
                    "repo_url": item["repo_url"],
                    "visibility": item["visibility"],
                    "description": item["description"],
                    "contains_azure": item["contains_azure"],
                    "resource_hints": item["resource_hints"],
                    "is_module_repo": item["is_module_repo"],
                    "verified_repo_exists": item["verified_repo_exists"],
                    "verified_default_branch": item["verified_default_branch"],
                    "match_type": item["match_type"],
                    "score": item["score"],
                    "retrieved_module_context_seed": build_azure_module_context_seed(item),
                }
                for item in top_matches
            ],
        }

    return {
        "status": "not_found",
        "decision_state": "azure_module_repo_creation_confirmation",
        "requested_resource_hint": " ".join(_azure_requested_resource_tokens(user_prompt)[:6]),
        "searched_root": discovery_root,
        "matches": [],
    }

def _unique_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def store_pending_azure_module_discovery(
    thread_id: str,
    ticket_number: str,
    original_prompt: str,
    discovery: dict,
    ticket_link: str = "",
    ticket_title: str = "",
):
    key = hashlib.sha1(
        f"{thread_id or 'no-thread'}::{ticket_number or ''}::azure-module-discovery::{original_prompt}".encode("utf-8")
    ).hexdigest()

    PENDING_AZURE_MODULE_DISCOVERIES[key] = {
        "thread_id": thread_id,
        "ticket_number": (ticket_number or "").strip().upper(),
        "original_prompt": original_prompt,
        "ticket_link": ticket_link or "",
        "ticket_title": ticket_title or "",
        "discovery": discovery or {},
    }
    return key


def get_pending_azure_module_discovery(thread_id: str, ticket_number: str):
    thread_id = str(thread_id or "")
    ticket_number = (ticket_number or "").strip().upper()

    for _, item in PENDING_AZURE_MODULE_DISCOVERIES.items():
        if str(item.get("thread_id") or "") == thread_id and (item.get("ticket_number") or "") == ticket_number:
            return item
    return None


def clear_pending_azure_module_discovery(thread_id: str, ticket_number: str):
    thread_id = str(thread_id or "")
    ticket_number = (ticket_number or "").strip().upper()

    keys_to_delete = []
    for key, item in PENDING_AZURE_MODULE_DISCOVERIES.items():
        if str(item.get("thread_id") or "") == thread_id and (item.get("ticket_number") or "") == ticket_number:
            keys_to_delete.append(key)

    for key in keys_to_delete:
        PENDING_AZURE_MODULE_DISCOVERIES.pop(key, None)


def _extract_resource_block(tf_content: str, resource_type: str = "github_repository") -> str:
    pattern = rf'resource\s+"{re.escape(resource_type)}"\s+"[^"]+"\s*\{{'
    match = re.search(pattern, tf_content or "", re.IGNORECASE)
    if not match:
        return ""

    start = match.start()
    brace_start = (tf_content or "").find("{", match.end() - 1)
    if brace_start == -1:
        return ""

    depth = 0
    in_string = False
    escape = False
    for idx in range(brace_start, len(tf_content)):
        ch = tf_content[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return tf_content[start:idx + 1]
    return ""


def _extract_assignment(block: str, key: str) -> str:
    match = re.search(rf'^\s*{re.escape(key)}\s*=\s*"([^"]+)"', block or "", re.MULTILINE)
    return match.group(1).strip() if match else ""


def _extract_resource_hints(filename: str, repo_name: str, description: str, tf_content: str) -> list[str]:
    token_source = " ".join([filename or "", repo_name or "", description or "", tf_content or ""])
    tokens = _unique_preserve_order(_tokenize_for_match(token_source))
    preferred = []
    for token in tokens:
        if token in {"tf", "module", "github", "repository", "repo", "private", "public", "internal"}:
            continue
        preferred.append(token)
    return preferred[:12]


def _extract_module_block(tf_content: str) -> tuple[str, str]:
    match = re.search(r'module\s+"([^"]+)"\s*\{', tf_content or "", re.IGNORECASE)
    if not match:
        return "", ""

    start = match.start()
    brace_start = (tf_content or "").find("{", match.end() - 1)
    if brace_start == -1:
        return match.group(1), ""

    depth = 0
    in_string = False
    escape = False
    for idx in range(brace_start, len(tf_content)):
        ch = tf_content[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return match.group(1), tf_content[start:idx + 1]

    return match.group(1), ""


def parse_vena_repo_creation_tf(tf_path: str, tf_content: str, github_owner: str) -> dict | None:
    tf_path = (tf_path or "").strip().replace("\\", "/")
    tf_content = tf_content or ""
    filename = tf_path.rsplit("/", 1)[-1]

    if not filename.endswith(".tf"):
        return None

    repo_block = _extract_resource_block(tf_content, "github_repository")
    module_name, module_block = _extract_module_block(tf_content)

    if repo_block:
        repo_name = _extract_assignment(repo_block, "name")
        description = _extract_assignment(repo_block, "description")
        visibility = _extract_assignment(repo_block, "visibility") or "private"
        terraform_block = repo_block
    elif module_block and re.search(r'^\s*source\s*=\s*"\.\./modules/repo"', module_block, re.MULTILINE):
        repo_name = _extract_assignment(module_block, "name")
        description = _extract_assignment(module_block, "description")
        visibility = "private"
        terraform_block = module_block
    else:
        return None

    if not repo_name:
        if module_name.startswith("tf_module_"):
            repo_name = module_name.replace("_", "-").replace("tf-module-", "tf-module-")
        else:
            repo_name = filename[:-3].replace("_", "-")

    contains_azure = (
        "azure" in filename.lower()
        or "azure" in repo_name.lower()
        or "azure" in description.lower()
        or "azure" in tf_content.lower()
    )
    resource_hints = _extract_resource_hints(filename, repo_name, description, tf_content)
    is_module_repo = _looks_like_azure_module_repo_definition(
        filename,
        repo_name,
        description,
        tf_content,
        terraform_block=terraform_block,
    )

    return {
        "tf_file": filename,
        "tf_path": tf_path,
        "filename": filename,
        "terraform_resource_block": terraform_block,
        "repo_name": repo_name,
        "repo_owner": github_owner,
        "repo_full_name": f"{github_owner}/{repo_name}",
        "repo_url": f"https://github.com/{github_owner}/{repo_name}",
        "visibility": visibility,
        "description": description or f"Azure module repository for {repo_name.replace('-', ' ')}",
        "contains_azure": contains_azure,
        "resource_hints": resource_hints,
        "match_tokens": _unique_preserve_order(_tokenize_for_match(" ".join([tf_path, repo_name, description, tf_content]))),
        "is_module_repo": is_module_repo,
    }




def build_azure_module_context_seed(match: dict) -> dict:
    return {
        "source": "backend_live_vena_repo_discovery",
        "match_type": match.get("match_type"),
        "repo_name": match.get("repo_name"),
        "repo_owner": match.get("repo_owner"),
        "repo_full_name": match.get("repo_full_name"),
        "repo_url": match.get("repo_url"),
        "tf_repo_creation_path": match.get("tf_path"),
        "tf_repo_creation_file": match.get("tf_file"),
        "description": match.get("description"),
        "visibility": match.get("visibility"),
        "resource_hints": list(match.get("resource_hints") or []),
        "verified_repo_exists": bool(match.get("verified_repo_exists")),
        "verified_default_branch": match.get("verified_default_branch"),
    }


def _humanize_resource_hints(hints: list[str]) -> str:
    hints = [h for h in (hints or []) if h]
    if not hints:
        return "Azure module"

    preferred = []
    for hint in hints:
        if hint in {"azure", "tf", "github"}:
            continue
        preferred.append(hint)

    if not preferred:
        return "Azure module"

    pretty = " ".join(preferred[:3]).strip()
    return f"Azure {pretty} module"


def build_azure_module_discovery_reply(discovery: dict) -> str:
    status = discovery.get("status")
    matches = discovery.get("matches") or []

    if status in {"exact_match", "similar_match"} and matches:
        lines = ["I found existing Azure module option(s):"]

        for idx, match in enumerate(matches[:5], start=1):
            repo_full_name = match.get("repo_full_name") or ""
            description = match.get("description") or "No description found."
            repo_name = match.get("repo_name") or ""

            lines.append(f"{idx}. {repo_full_name}")
            lines.append(f"   Description: {description}")
            if repo_full_name and repo_name:
                lines.append("   Branch/ref: will be selected after you choose the module.")

        lines.append("")
        lines.append("Do you want to use one of these existing modules?")

        return "\n".join(lines)

    return (
        "I could not find an approved Azure module repo in vena_repos for this request.\n\n"
        "Do you want me to create a new Azure module repo first? "
        "You can reply yes, or include the exact repo name you want, for example: "
        "create repo azure-linux-vm-module. The repo name does not need to start with tf-module or tf_module.\n\n"
        "Reply no to cancel."
    )





def build_azure_module_branch_selection_reply(discovery: dict) -> str:
    discovery = discovery or {}
    match = discovery.get("selected_match") or ((discovery.get("matches") or [{}])[0])
    branch_options = discovery.get("branch_options") or []
    repo_full_name = match.get("repo_full_name") or "the selected Azure module repo"

    if len(branch_options) > 1:
        heading = f"I found multiple branches for {repo_full_name}."
    elif len(branch_options) == 1:
        heading = f"I found one branch for {repo_full_name}."
    else:
        heading = f"I could not read branch options for {repo_full_name}."

    lines = [
        heading,
        "Please choose which branch Terrabot should use for the module source:",
    ]

    if not branch_options:
        lines.append("No readable branches were found from GitHub branch listing.")
        lines.append("Reply with the exact branch name only if you have confirmed it exists in GitHub.")
        return "\n".join(lines)

    for idx, option in enumerate(branch_options[:25], start=1):
        branch = option.get("branch") or ""
        details = []

        if option.get("recommended"):
            details.append("recommended")
        if option.get("is_default"):
            details.append("default")
        if option.get("has_variables_tf"):
            details.append("variables.tf found")

        input_count = len(option.get("inputs_detected") or [])
        required_count = len(option.get("required_inputs_detected") or [])

        if input_count:
            details.append(f"{input_count} input(s)")
        else:
            details.append("no inputs detected")

        if required_count:
            details.append(f"{required_count} required")

        suffix = f" ({', '.join(details)})" if details else ""
        lines.append(f"{idx}. {branch}{suffix}")

        preview_inputs = list(option.get("inputs_detected") or [])[:8]
        if preview_inputs:
            lines.append(f"   Inputs: {', '.join(preview_inputs)}")

    if len(branch_options) > 25:
        lines.append(
            f"...and {len(branch_options) - 25} more branch(es). "
            "Reply with the exact branch name if it is not shown."
        )

    lines.append("")
    lines.append("Reply with the branch number or exact branch name.")
    return "\n".join(lines)


def _extract_numbered_choice(reply: str, max_index: int) -> int:
    """Return a 1-based option number from compact UI replies.

    Supports replies such as "1", "yes 1", "use 2", "module 3", and
    "branch #2". It intentionally avoids mining arbitrary digits from branch
    names such as feature/v2.
    """
    if max_index <= 0:
        return 0

    normalized = normalize_yes_no_reply(reply).strip("`'\"")
    normalized = re.sub(r"[,;:]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return 0

    numeric_patterns = [
        r"^#?(\d+)$",
        r"^(?:yes|y|use|select|choose|pick|option|repo|repository|module|branch|number)\s+#?(\d+)$",
        r"^(?:yes|y)\s+(?:use|select|choose|pick)?\s*(?:option|repo|repository|module|branch|number)?\s*#?(\d+)$",
        r"^(?:use|select|choose|pick)\s+(?:option|repo|repository|module|branch|number)?\s*#?(\d+)$",
    ]

    for pattern in numeric_patterns:
        match = re.fullmatch(pattern, normalized, re.IGNORECASE)
        if not match:
            continue
        index = int(match.group(1))
        if 1 <= index <= max_index:
            return index

    return 0


def select_azure_module_match_from_reply(reply: str, matches: list[dict]) -> dict:
    """Pick a discovered Azure module repo from the user's confirmation reply."""
    options = [match for match in (matches or []) if isinstance(match, dict)]
    if not options:
        return {}

    raw = (reply or "").strip()
    if not raw:
        return {}

    cleaned = raw.strip().strip("`'\"")
    normalized = normalize_yes_no_reply(cleaned).strip("`'\"")

    numeric_index = _extract_numbered_choice(cleaned, len(options))
    if numeric_index:
        return options[numeric_index - 1]

    for option in options:
        repo_full_name = normalize_yes_no_reply(option.get("repo_full_name") or "")
        repo_name = normalize_yes_no_reply(option.get("repo_name") or "")
        if normalized and normalized in {repo_full_name, repo_name}:
            return option

    normalized_text = f" {normalized} "
    for option in options:
        for value in (option.get("repo_full_name"), option.get("repo_name")):
            value_normalized = normalize_yes_no_reply(value or "")
            if not value_normalized:
                continue
            pattern = rf"(?<![A-Za-z0-9_.-]){re.escape(value_normalized)}(?![A-Za-z0-9_.-])"
            if re.search(pattern, normalized_text):
                return option

    if normalized in AFFIRMATIVE_REPLIES:
        return options[0]

    return {}


def get_first_azure_module_match(discovery: dict) -> dict:
    discovery = discovery or {}
    selected_match = discovery.get("selected_match")
    if isinstance(selected_match, dict) and selected_match:
        return selected_match
    matches = discovery.get("matches") or []
    if matches and isinstance(matches[0], dict):
        return matches[0]
    return {}


def select_azure_module_branch_from_reply(reply: str, branch_options: list[dict]) -> str:
    raw = (reply or "").strip()
    if not raw:
        return ""

    options = [option for option in (branch_options or []) if isinstance(option, dict) and option.get("branch")]
    cleaned = raw.strip().strip("`'\"")
    normalized = normalize_yes_no_reply(cleaned).strip("`'\"")

    # Prefer exact branch names before numeric parsing so a real branch like
    # feature/v2 is not mistaken for option 2.
    for option in options:
        branch = str(option.get("branch") or "").strip()
        if normalized == normalize_yes_no_reply(branch):
            return branch

    numeric_index = _extract_numbered_choice(cleaned, len(options))
    if numeric_index:
        return str(options[numeric_index - 1].get("branch") or "").strip()

    normalized_text = f" {normalized} "
    for option in options:
        branch = str(option.get("branch") or "").strip()
        branch_normalized = normalize_yes_no_reply(branch)
        if not branch_normalized:
            continue
        pattern = rf"(?<![A-Za-z0-9_./-]){re.escape(branch_normalized)}(?![A-Za-z0-9_./-])"
        if re.search(pattern, normalized_text):
            return branch

    return ""


def _list_repo_files_recursively(owner: str, repo: str, ref: str, github_get_contents, path: str = "") -> list[dict]:
    results = []
    items = github_get_contents(owner, repo, path=path, ref=ref)
    if isinstance(items, dict):
        items = [items]

    for item in items or []:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        item_path = item.get("path") or ""
        if item_type == "dir":
            results.extend(_list_repo_files_recursively(owner, repo, ref, github_get_contents, path=item_path))
        elif item_type == "file":
            results.append(item)
    return results


def _extract_module_input_names(tf_content: str) -> list[str]:
    return _unique_preserve_order(re.findall(r'variable\s+"([^"]+)"', tf_content or "", re.IGNORECASE))


def _extract_module_output_names(tf_content: str) -> list[str]:
    return _unique_preserve_order(re.findall(r'output\s+"([^"]+)"', tf_content or "", re.IGNORECASE))

def _extract_required_variable_names(tf_content: str) -> list[str]:
    text = tf_content or ""
    required = []

    for match in re.finditer(r'variable\s+"([^"]+)"\s*\{', text, re.IGNORECASE):
        var_name = match.group(1)
        brace_start = text.find("{", match.end() - 1)
        if brace_start == -1:
            continue

        depth = 0
        in_string = False
        escape = False
        block = ""

        for idx in range(brace_start, len(text)):
            ch = text[idx]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
            else:
                if ch == '"':
                    in_string = True
                elif ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        block = text[match.start():idx + 1]
                        break

        if not block:
            continue

        has_default = re.search(r'^\s*default\s*=', block, re.MULTILINE | re.IGNORECASE) is not None
        if not has_default:
            required.append(var_name)

    return _unique_preserve_order(required)


def _infer_module_structure(module_files: list[dict]) -> dict:
    paths = [str(item.get("path") or "") for item in (module_files or [])]
    lower_paths = [p.lower() for p in paths]

    def has_file(name: str) -> bool:
        return any(p.endswith(name.lower()) for p in lower_paths)

    tf_root_files = [p for p in paths if "/" not in p and p.endswith(".tf")]

    return {
        "file_count": len(paths),
        "root_tf_files": tf_root_files,
        "has_main_tf": has_file("main.tf"),
        "has_variables_tf": has_file("variables.tf"),
        "has_outputs_tf": has_file("outputs.tf"),
        "has_versions_tf": has_file("versions.tf"),
        "has_readme": any(p.endswith("readme.md") or p.endswith("readme") for p in lower_paths),
    }


def _approved_consumer_repo_queries(owner: str, repo_names: list[str], repo_name: str, repo_full_name: str) -> list[tuple[str, str]]:
    queries = []
    for consumer_repo in repo_names or []:
        queries.extend([
            (consumer_repo, f'repo:{owner}/{consumer_repo} "{repo_name}"'),
            (consumer_repo, f'repo:{owner}/{consumer_repo} "{repo_full_name}"'),
            (consumer_repo, f'repo:{owner}/{consumer_repo} "git@github.com:{repo_full_name}.git"'),
        ])
    return queries


def _extract_module_blocks(tf_content: str) -> list[dict]:
    text = tf_content or ""
    results = []
    for match in re.finditer(r'module\s+"([^"]+)"\s*\{', text, re.IGNORECASE):
        name = match.group(1)
        brace_start = text.find("{", match.end() - 1)
        if brace_start == -1:
            continue
        depth = 0
        in_string = False
        escape = False
        block = ""
        for idx in range(brace_start, len(text)):
            ch = text[idx]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
            else:
                if ch == '"':
                    in_string = True
                elif ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        block = text[match.start():idx + 1]
                        break
        if not block:
            continue
        source_match = re.search(r'^\s*source\s*=\s*"([^"]+)"', block, re.MULTILINE)
        results.append({
            "module_name": name,
            "source": source_match.group(1).strip() if source_match else "",
            "block": block,
        })
    return results


def _source_matches_repo(source: str, repo_name: str, repo_full_name: str) -> bool:
    source = (source or "").lower()
    return bool(source and (repo_name.lower() in source or repo_full_name.lower() in source))



def _normalize_azure_source_repo(value: str) -> tuple[str, str]:
    """Return (owner, repo) from a GitHub Terraform module source.

    The source may be an SSH URL, an HTTPS URL, include a git:: prefix,
    include a root/submodule path using //, or include ?ref=. Ref and
    subdirectory are intentionally ignored for source-file routing because
    tf-azure-hub groups module invocations by module repository/resource type,
    while the selected branch/ref can differ from the existing invocation.
    """
    source = (value or "").strip().strip('"\'')
    if not source:
        return "", ""

    source = re.sub(r"^git::", "", source, flags=re.IGNORECASE)
    source = source.split("?", 1)[0].split("#", 1)[0]

    # Remove Terraform subdirectory suffix after the repository name.
    if ".git//" in source:
        source = source.split(".git//", 1)[0] + ".git"

    patterns = [
        r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$",
        r"ssh://git@github\.com/([^/]+)/([^/]+?)(?:\.git)?$",
        r"git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$",
    ]

    for pattern in patterns:
        match = re.search(pattern, source, re.IGNORECASE)
        if match:
            owner = match.group(1).strip().lower()
            repo = re.sub(r"\.git$", "", match.group(2).strip(), flags=re.IGNORECASE).lower()
            return owner, repo

    return "", ""


def azure_module_sources_match(candidate_source: str, target_source: str) -> bool:
    candidate_owner, candidate_repo = _normalize_azure_source_repo(candidate_source)
    target_owner, target_repo = _normalize_azure_source_repo(target_source)
    return bool(candidate_owner and candidate_repo and candidate_owner == target_owner and candidate_repo == target_repo)


def _module_source_match_type(candidate_source: str, target_source: str) -> str:
    candidate = (candidate_source or "").strip()
    target = (target_source or "").strip()
    if candidate and target and candidate == target:
        return "exact_source"
    if azure_module_sources_match(candidate, target):
        return "same_repo_source"
    return "none"


def _prompt_tokens_for_routing(prompt: str) -> set[str]:
    return set(_tokenize_for_match(prompt or ""))


def _routing_text_tokens(*values: str) -> set[str]:
    return set(_tokenize_for_match(" ".join(v or "" for v in values)))


def find_tf_azure_hub_module_invocation_file_by_source(
    module_source_url: str,
    tf_files: list[dict],
    user_prompt: str = "",
) -> dict:
    """Find the existing tf-azure-hub file that already invokes a module source.

    This helper is intentionally source-driven. It scans existing Terraform
    module blocks, matches by exact source first and by GitHub owner/repo next,
    then selects the most relevant existing file by prompt/file/module-token
    overlap and count of matching invocations. It never returns a synthetic
    filename.
    """
    module_source_url = (module_source_url or "").strip()
    if not module_source_url:
        return {}

    target_owner, target_repo = _normalize_azure_source_repo(module_source_url)
    if not target_owner or not target_repo:
        return {}

    prompt_tokens = _prompt_tokens_for_routing(user_prompt)
    candidates = []

    for item in tf_files or []:
        if not isinstance(item, dict):
            continue

        path = (item.get("path") or item.get("filename") or "").strip().replace("\\", "/")
        content = item.get("content") or ""
        if not path.endswith(".tf") or not content:
            continue

        module_blocks = []
        for module_block in _extract_module_blocks(content):
            source = module_block.get("source") or ""
            match_type = _module_source_match_type(source, module_source_url)
            if match_type == "none":
                continue
            module_blocks.append({
                "module_name": module_block.get("module_name") or "",
                "module_source": source,
                "module_block": module_block.get("block") or "",
                "match_type": match_type,
            })

        if not module_blocks:
            continue

        exact_count = sum(1 for block in module_blocks if block.get("match_type") == "exact_source")
        file_tokens = _routing_text_tokens(path, path.rsplit("/", 1)[-1].replace(".tf", ""))
        module_tokens = _routing_text_tokens(
            " ".join(block.get("module_name") or "" for block in module_blocks),
            " ".join(block.get("module_block") or "" for block in module_blocks),
        )
        token_overlap = len(prompt_tokens & (file_tokens | module_tokens))

        score = 0
        score += 1000 if exact_count else 700
        score += len(module_blocks) * 25
        score += exact_count * 50
        score += token_overlap * 30

        # Prefer root/resource grouping files over nested monitoring modules for
        # general tf-azure-hub consumer additions, unless the prompt matches the
        # nested path strongly enough through token_overlap.
        if "/" not in path:
            score += 10

        candidates.append({
            "path": path,
            "filename": path,
            "score": score,
            "match_type": "exact_source" if exact_count else "same_repo_source",
            "target_repo_owner": target_owner,
            "target_repo_name": target_repo,
            "matched_invocation_count": len(module_blocks),
            "matched_module_name": module_blocks[0].get("module_name") or "",
            "matched_module_source": module_blocks[0].get("module_source") or "",
            "matched_module_block": module_blocks[0].get("module_block") or "",
            "matched_module_blocks": module_blocks[:5],
        })

    if not candidates:
        return {}

    candidates.sort(
        key=lambda item: (
            -int(item.get("score") or 0),
            0 if item.get("match_type") == "exact_source" else 1,
            item.get("path") or "",
        )
    )
    return candidates[0]

def _extract_ref_from_module_source(source: str) -> str:
    source = (source or "").strip()
    if not source:
        return ""

    match = re.search(r"[?&]ref=([^&\"']+)", source, re.IGNORECASE)
    if not match:
        return ""

    return match.group(1).strip()


def build_verified_root_module_source(owner: str, repo: str, ref: str) -> str:
    owner = (owner or "").strip()
    repo = (repo or "").strip()
    ref = (ref or "").strip()

    if not owner or not repo or not ref:
        return ""

    return f"git@github.com:{owner}/{repo}.git?ref={ref}"

def resolve_verified_module_repo_url(
    match: dict,
    github_get_repo_default_branch,
    github_verify_repo_exists,
    preferred_ref: str = "",
) -> dict:
    repo_owner = match.get("repo_owner")
    repo_name = match.get("repo_name")
    repo_full_name = match.get("repo_full_name") or f"{repo_owner}/{repo_name}"
    repo_exists = github_verify_repo_exists(repo_full_name)
    default_branch = github_get_repo_default_branch(repo_owner, repo_name) if repo_exists else None
    repo_url = f"https://github.com/{repo_owner}/{repo_name}"

    chosen_ref = (preferred_ref or "").strip() or (default_branch or "").strip()

    return {
        "repo_owner": repo_owner,
        "repo_name": repo_name,
        "repo_full_name": repo_full_name,
        "repo_exists": repo_exists,
        "default_branch": default_branch,
        "chosen_ref": chosen_ref,
        "repo_url": repo_url,
        "module_source_url": (
            build_verified_root_module_source(repo_owner, repo_name, chosen_ref)
            if repo_exists and chosen_ref
            else ""
        ),
    }

def build_grounded_azure_contexts(
    match: dict,
    github_get_repo_default_branch,
    github_get_contents,
    github_get_file_content_by_repo,
    github_search_code,
    github_verify_repo_exists,
    approved_consumer_repos: list[str],
    approved_repo_default_branches: dict[str, str] | None = None,
    get_best_module_branch_with_inputs=None,
    selected_module_ref: str = "",
) -> tuple[list[dict], list[dict]]:
    repo_owner = match.get("repo_owner")
    repo_name = match.get("repo_name")
    repo_full_name = match.get("repo_full_name") or f"{repo_owner}/{repo_name}"

    if not github_verify_repo_exists(repo_full_name):
        return [], []

    approved_repo_default_branches = approved_repo_default_branches or {}
    default_branch = github_get_repo_default_branch(repo_owner, repo_name)

    search_results = []
    seen_repo_paths = set()

    for consumer_repo, query in _approved_consumer_repo_queries(
        repo_owner,
        approved_consumer_repos,
        repo_name,
        repo_full_name,
    ):
        try:
            results = github_search_code(query, per_page=10)
        except Exception:
            results = []

        for item in results or []:
            if not isinstance(item, dict):
                continue

            path = item.get("path") or ""
            repo_info = item.get("repository") or {}
            full_name = repo_info.get("full_name") or ""

            if full_name.lower() != f"{repo_owner}/{consumer_repo}".lower():
                continue

            dedupe_key = f"{consumer_repo}:{path}"
            if dedupe_key in seen_repo_paths:
                continue

            seen_repo_paths.add(dedupe_key)
            search_results.append((consumer_repo, item))

    consumer_examples = []
    preferred_ref = ""

    for consumer_repo, item in search_results[:20]:
        path = item.get("path") or ""
        consumer_ref = (
            approved_repo_default_branches.get(consumer_repo)
            or "main"
        )

        content = github_get_file_content_by_repo(
            repo_owner,
            consumer_repo,
            path,
            ref=consumer_ref,
        )
        if not content:
            continue

        for module_block in _extract_module_blocks(content):
            if not _source_matches_repo(module_block.get("source"), repo_name, repo_full_name):
                continue

            module_source = module_block.get("source") or ""
            detected_ref = _extract_ref_from_module_source(module_source)
            if detected_ref and not preferred_ref:
                preferred_ref = detected_ref

            consumer_examples.append({
                "source": "backend_real_consumer_example",
                "repo_full_name": f"{repo_owner}/{consumer_repo}",
                "repo_name": consumer_repo,
                "path": path,
                "ref": consumer_ref,
                "module_name": module_block.get("module_name"),
                "module_source": module_source,
                "module_block": module_block.get("block"),
            })

    selected_module_ref = (selected_module_ref or "").strip()

    verification = resolve_verified_module_repo_url(
        match,
        github_get_repo_default_branch=github_get_repo_default_branch,
        github_verify_repo_exists=github_verify_repo_exists,
        preferred_ref=selected_module_ref or preferred_ref,
    )

    if not verification.get("repo_exists"):
        return [], []

    owner = verification["repo_owner"]
    repo = verification["repo_name"]
    resolved_ref = verification["chosen_ref"] or verification["default_branch"]
    module_source_url = verification["module_source_url"]
    branch_inputs = []
    branch_required_inputs = []

    if selected_module_ref:
        # Explicit user selection always wins. The selected ref is then used
        # verbatim for module source and Terraform variable retrieval.
        resolved_ref = selected_module_ref
    elif callable(get_best_module_branch_with_inputs):
        try:
            best_branch, branch_inputs, branch_required_inputs = get_best_module_branch_with_inputs(owner, repo)
        except Exception:
            best_branch, branch_inputs, branch_required_inputs = None, [], []

        if best_branch:
            resolved_ref = best_branch

    module_source_url = build_verified_root_module_source(owner, repo, resolved_ref)

    repo_files = _list_repo_files_recursively(owner, repo, resolved_ref, github_get_contents)
    tf_files = []
    file_summaries = []
    aggregated_inputs = []
    aggregated_required_inputs = []
    aggregated_outputs = []

    for item in repo_files:
        path = item.get("path") or ""
        if not path.endswith(".tf"):
            continue

        content = github_get_file_content_by_repo(owner, repo, path, ref=resolved_ref)
        if not content:
            continue

        tf_files.append({"path": path, "content": content})
        file_summaries.append(path)
        aggregated_inputs.extend(_extract_module_input_names(content))
        aggregated_required_inputs.extend(_extract_required_variable_names(content))
        aggregated_outputs.extend(_extract_module_output_names(content))

    aggregated_inputs = _unique_preserve_order(list(branch_inputs or []) + aggregated_inputs)
    aggregated_required_inputs = _unique_preserve_order(
        [name for name in list(branch_required_inputs or []) + aggregated_required_inputs if name in aggregated_inputs]
    )
    aggregated_outputs = _unique_preserve_order(aggregated_outputs)
    module_structure = _infer_module_structure(tf_files)

    retrieved_module_context = [{
        "source": "backend_verified_github_module_repo",
        "match_type": match.get("match_type"),
        "repo_name": repo,
        "repo_owner": owner,
        "repo_full_name": verification["repo_full_name"],
        "target_module_repo_name": repo,
        "target_module_repo_full_name": verification["repo_full_name"],
        "verified_repo_url": verification["repo_url"],
        "verified_default_branch": verification["default_branch"],
        "resolved_ref": resolved_ref,
        "module_source_url": module_source_url,
        "tf_repo_creation_path": match.get("tf_path"),
        "tf_repo_creation_file": match.get("tf_file"),
        "description": match.get("description"),
        "visibility": match.get("visibility"),
        "resource_hints": list(match.get("resource_hints") or []),
        "file_list": file_summaries,
        "inputs_detected": aggregated_inputs,
        "required_inputs_detected": aggregated_required_inputs,
        "outputs_detected": aggregated_outputs,
        "module_structure": module_structure,
        "module_files": tf_files,
    }]

    retrieved_value_context = []
    for tf_file in tf_files:
        retrieved_value_context.append({
            "source": "backend_verified_module_repo_file",
            "repo_full_name": verification["repo_full_name"],
            "verified_repo_url": verification["repo_url"],
            "module_source_url": module_source_url,
            "verified_default_branch": verification["default_branch"],
            "resolved_ref": resolved_ref,
            "path": tf_file["path"],
            "content": tf_file["content"],
        })

    retrieved_value_context.extend(consumer_examples)

    return retrieved_module_context, retrieved_value_context

# ---------------------------------------------------------------------------
# Azure workflow routing helpers
# ---------------------------------------------------------------------------


def is_explicit_azure_consumer_value_reply(value: str) -> bool:
    """True only for explicit Azure tfvars/value replies, not bare yes/no.

    This prevents an unrelated AWS confirmation reply such as "yes" from being
    interpreted as Azure consumer values when no active Azure value-selection
    context exists.
    """
    text = (value or "").strip()
    if not text:
        return False

    normalized = normalize_yes_no_reply(text)
    if normalized in AFFIRMATIVE_REPLIES or normalized in NEGATIVE_REPLIES:
        return False

    if re.search(r"(?m)^\s*[A-Za-z_][A-Za-z0-9_]*\s*=", text):
        return True

    if text.startswith("{") and text.endswith("}"):
        return True

    if "```" in text and re.search(r"(?m)^\s*[A-Za-z_][A-Za-z0-9_]*\s*=", text):
        return True

    return False


def has_active_azure_pending_workflow(
    pending_azure_discovery=None,
    pending_azure_consumer_values=None,
    pending_azure_new_consumer_file=None,
) -> bool:
    return bool(
        pending_azure_discovery
        or pending_azure_consumer_values
        or pending_azure_new_consumer_file
    )


def should_handle_cloud_only_clarification(cloud_only_reply: bool, has_any_pending_workflow: bool) -> bool:
    """Cloud clarification should not hijack an active AWS/Azure workflow reply."""
    return bool(cloud_only_reply and not has_any_pending_workflow)


def should_block_missing_azure_value_context(prompt: str, has_pending_azure_consumer_values: bool) -> bool:
    """Block HCL value replies only when no pending value-selection context exists."""
    return bool(
        is_explicit_azure_consumer_value_reply(prompt)
        and not has_pending_azure_consumer_values
    )
