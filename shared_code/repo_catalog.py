from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class RepoRule:
    repo_name: str
    cloud: str
    strategy: str
    root_folder_name: str


# Legacy names are kept only as hints for the existing Azure Function paths.
# New local CLI/repo-aware flow does not require these hardcoded repos; it uses
# terrabot_core.scanner.scan_repository() against the currently opened workspace.
LEGACY_REPO_RULES = {
    "tf-devops": RepoRule(
        repo_name="tf-devops",
        cloud="aws",
        strategy="repo-inferred",
        root_folder_name="tf-devops",
    ),
    "tf-azure-hub": RepoRule(
        repo_name="tf-azure-hub",
        cloud="azure",
        strategy="repo-inferred",
        root_folder_name="tf-azure-hub",
    ),
    "vena_repos": RepoRule(
        repo_name="vena_repos",
        cloud="azure",
        strategy="repo-inferred",
        root_folder_name="vena_repos",
    ),
}

# Backwards-compatible alias for older imports/tests.
REPO_RULES = LEGACY_REPO_RULES


_ENV_ALIASES = {
    "production": "prd",
    "prod": "prd",
    "prd": "prd",
    "development": "dev",
    "dev": "dev",
    "sandbox": "sbx",
    "sbx": "sbx",
    "nonproduction": "npr",
    "nonprod": "npr",
    "npr": "npr",
    "staging": "stg",
    "stage": "stg",
    "stg": "stg",
    "qa": "qa",
    "uat": "uat",
}


def detect_repo_name_from_path(path: str) -> Optional[str]:
    p = str(path).replace("\\", "/").lower()
    for repo_name in LEGACY_REPO_RULES:
        if repo_name in p:
            return repo_name

    parts = [part for part in Path(path).parts if part not in {".", ""}]
    if not parts:
        return None
    # Generic fallback: use the nearest visible folder as a repo-ish name.
    for part in reversed(parts[:-1] if Path(path).suffix else parts):
        if part not in {"terraform", "modules", "vars", "pipelines", ".github"}:
            return part
    return None


def get_repo_rule(repo_name: str) -> RepoRule:
    if repo_name in LEGACY_REPO_RULES:
        return LEGACY_REPO_RULES[repo_name]
    return RepoRule(
        repo_name=repo_name,
        cloud="unknown",
        strategy="repo-inferred",
        root_folder_name=repo_name,
    )


def infer_doc_type(repo_name: str, relative_path: str) -> str:
    rp = relative_path.replace("\\", "/").lower()

    if rp.endswith(".tfvars"):
        return "tfvars"
    if rp.endswith((".yml", ".yaml")):
        if "pipeline" in rp or rp.startswith(".github/workflows/"):
            return "pipeline"
        return "yaml"
    if rp.endswith("readme.md") or rp.endswith(".md"):
        return "readme"
    if rp.endswith(".rego") or "policy" in rp or rp.startswith(".terrabot/"):
        return "policy"
    if rp.endswith(".tf"):
        if "/modules/" in f"/{rp}" or rp.startswith("modules/") or "/terraform/modules/" in f"/{rp}":
            return "module_definition"
        if Path(rp).name in {"variables.tf", "outputs.tf", "locals.tf", "provider.tf", "providers.tf", "versions.tf", "backend.tf"}:
            return "terraform_convention"
        return "module_usage"
    return "other"


def infer_module_name(repo_name: str, relative_path: str) -> Optional[str]:
    rp = relative_path.replace("\\", "/").strip("/")
    parts = rp.split("/")
    if "modules" in parts:
        idx = parts.index("modules")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    name = Path(rp).stem.lower()
    if name.startswith("tf_module_"):
        return name.replace("tf_module_", "", 1)
    return None


def infer_environment_name(repo_name: str, relative_path: str) -> Optional[str]:
    rp = relative_path.replace("\\", "/").lower()
    parts = [part for part in rp.split("/") if part]

    for part in parts:
        if part in _ENV_ALIASES:
            return _ENV_ALIASES[part]
        prefix = part.split("_", 1)[0].split("-", 1)[0]
        if prefix in _ENV_ALIASES:
            return _ENV_ALIASES[prefix]
    return None


def infer_flags(repo_name: str, relative_path: str) -> dict:
    doc_type = infer_doc_type(repo_name, relative_path)
    rp = relative_path.replace("\\", "/").lower()

    return {
        "is_module_definition": doc_type == "module_definition",
        "is_module_usage": doc_type == "module_usage",
        "is_value_source": doc_type == "tfvars" or "key_vault" in rp or "key-vault" in rp,
        "is_repo_template": doc_type in {"module_definition", "terraform_convention", "readme"},
    }


def should_index_file(relative_path: str) -> bool:
    rp = relative_path.replace("\\", "/").lower()

    allowed_exts = (
        ".tf",
        ".tfvars",
        ".hcl",
        ".md",
        ".yml",
        ".yaml",
        ".json",
        ".rego",
    )

    ignored_parts = {
        ".git/",
        ".terraform/",
        ".terragrunt-cache/",
        "__pycache__/",
        "node_modules/",
        ".venv/",
        "venv/",
    }

    ignored_suffixes = (
        ".tfstate",
        ".tfstate.backup",
        ".pem",
        ".key",
        ".pfx",
        ".zip",
    )

    if any(part in rp for part in ignored_parts):
        return False
    if rp.endswith(ignored_suffixes):
        return False
    if not rp.endswith(allowed_exts) and Path(rp).name not in {"codeowners", ".pre-commit-config.yaml", ".tool-versions"}:
        return False
    return True
