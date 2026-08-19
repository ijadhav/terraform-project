from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from terrabot_core.filesystem import find_git_root, iter_repo_files, normalize_path, read_text
from terrabot_core.models import PipelineProfile, RepoProfile, TerraformBlock, TerraformRoot, unique_preserve_order
from terrabot_core.pipeline_parser import parse_pipeline
from terrabot_core.repo_overrides import load_repo_overrides
from terrabot_core.terraform_parser import (
    block_resource_type,
    parse_required_providers,
    parse_terraform_blocks,
    providers_to_clouds,
)

_ENV_TOKENS = {
    "dev",
    "development",
    "qa",
    "uat",
    "test",
    "tst",
    "sbx",
    "sandbox",
    "npr",
    "nonprod",
    "nonproduction",
    "stg",
    "stage",
    "staging",
    "prd",
    "prod",
    "production",
}

_LANGUAGE_BY_EXT = {
    ".tf": "terraform",
    ".tfvars": "terraform",
    ".hcl": "hcl",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".md": "markdown",
    ".py": "python",
    ".ts": "typescript",
    ".js": "javascript",
    ".sh": "shell",
    ".ps1": "powershell",
    ".rego": "rego",
}


def _normal_env(value: str) -> str:
    text = (value or "").strip().lower()
    return {
        "production": "prd",
        "prod": "prd",
        "development": "dev",
        "sandbox": "sbx",
        "nonproduction": "npr",
        "nonprod": "npr",
        "stage": "stg",
        "staging": "stg",
    }.get(text, text)


def _detect_env_from_path(relative_path: str) -> List[str]:
    rp = normalize_path(relative_path).lower()
    parts = [p for p in re.split(r"[/_.-]+", rp) if p]
    envs: List[str] = []
    env_token_set = {_normal_env(x) for x in _ENV_TOKENS}
    compound_env_re = re.compile(r"^(?:mini)?(?:dev|qa|uat|sbx|npr|stg|prd|prod)(?:[-_][a-z0-9]+)?$", re.IGNORECASE)
    for part in parts:
        normalized = _normal_env(part)
        if normalized in env_token_set:
            envs.append(normalized)
        elif compound_env_re.match(part):
            # Keep repo-specific compound environment folder names such as
            # minidev or prd-us5. Alias resolution can still map broad words
            # like "dev" to dev, but exact prompts should retain exact envs.
            envs.append(part.lower())
    for match in re.findall(r"\b(dev|qa|uat|sbx|npr|stg|prd|prod)[-_][A-Za-z0-9_-]+", rp):
        envs.append(_normal_env(match))
    return unique_preserve_order(envs)


def _looks_like_pipeline(relative_path: str, content: str) -> bool:
    rp = relative_path.lower().replace("\\", "/")
    if rp.startswith(".github/workflows/") and rp.endswith((".yml", ".yaml")):
        return True
    if "azure-pipelines" in rp and rp.endswith((".yml", ".yaml")):
        return True
    if rp.startswith("pipelines/") and rp.endswith((".yml", ".yaml")):
        return True
    if rp.startswith("pipeline-templates/") and rp.endswith((".yml", ".yaml")):
        return True
    if rp.endswith("jenkinsfile"):
        return True
    text = (content or "").lower()
    return rp.endswith((".yml", ".yaml")) and "terraform" in text and ("stages:" in text or "jobs:" in text or "steps:" in text)


def _infer_tfvars_pattern(tfvars_files: List[str]) -> List[str]:
    patterns: List[str] = []
    for path in tfvars_files:
        parts = path.split("/")
        normalized_parts: List[str] = []
        for idx, part in enumerate(parts):
            base = part
            if idx > 0 and _normal_env(part) in {_normal_env(x) for x in _ENV_TOKENS}:
                base = "{env}"
            elif re.match(r"^(dev|qa|uat|sbx|npr|stg|prd|prod)[-_].+", part, re.IGNORECASE):
                base = "{subscription}"
            normalized_parts.append(base)
        pattern = "/".join(normalized_parts)
        patterns.append(pattern)
    return unique_preserve_order(patterns)


def _detect_validation_commands(root: Path, files: Dict[str, str], terraform_present: bool) -> List[str]:
    commands: List[str] = []
    precommit = files.get(".pre-commit-config.yaml") or files.get(".pre-commit-config.yml")
    if precommit:
        if "terraform_fmt" in precommit or "terraform_docs" in precommit or "terraform_tflint" in precommit:
            commands.append("pre-commit run --all-files")
        if "terraform_fmt" in precommit:
            commands.append("terraform fmt -check -recursive")
        if "terraform_tflint" in precommit:
            commands.append("tflint --recursive")
    if terraform_present:
        commands.append("terraform fmt -check -recursive")
        commands.append("terraform validate")
    if ".tflint.hcl" in files:
        commands.append("tflint --recursive")
    for path, content in files.items():
        lower = path.lower()
        if lower.endswith((".yml", ".yaml")) and "tf-code-check" in content.lower():
            commands.append("pipeline: terraform code checks")
    return unique_preserve_order(commands)


def _detect_policy_files(files: Dict[str, str]) -> List[str]:
    policy_files: List[str] = []
    for path in files:
        lower = path.lower()
        name = Path(path).name.lower()
        if lower.startswith(".terrabot/"):
            policy_files.append(path)
        elif name in {"codeowners", "pull_request_template.md", "copilot-instructions.md"}:
            policy_files.append(path)
        elif "policy" in lower and lower.endswith((".md", ".yaml", ".yml", ".json", ".rego")):
            policy_files.append(path)
        elif lower in {"readme.md", "terraform/readme.md"}:
            policy_files.append(path)
    return unique_preserve_order(policy_files)


def _group_terraform_roots(blocks: Iterable[TerraformBlock], tf_files: Iterable[str]) -> List[TerraformRoot]:
    by_dir: Dict[str, Dict[str, object]] = defaultdict(lambda: {"providers": [], "modules": 0, "resources": 0, "variables": 0})
    for path in tf_files:
        directory = str(Path(path).parent).replace(".", "") or "."
        if directory == "":
            directory = "."
        _ = by_dir[directory]

    for block in blocks:
        directory = str(Path(block.path).parent).replace(".", "") or "."
        if directory == "":
            directory = "."
        item = by_dir[directory]
        if block.provider:
            item["providers"].append(block.provider)
        if block.block_type == "module":
            item["modules"] = int(item["modules"]) + 1
        elif block.block_type == "resource":
            item["resources"] = int(item["resources"]) + 1
        elif block.block_type == "variable":
            item["variables"] = int(item["variables"]) + 1

    roots: List[TerraformRoot] = []
    for directory, item in sorted(by_dir.items()):
        root_type = "module_definition" if "/modules/" in f"/{directory}/" or directory.startswith("modules/") or "/terraform/modules/" in f"/{directory}/" else "root_module"
        roots.append(
            TerraformRoot(
                path=directory or ".",
                root_type=root_type,
                providers=unique_preserve_order([str(x) for x in item["providers"]]),
                module_count=int(item["modules"]),
                resource_count=int(item["resources"]),
                variable_count=int(item["variables"]),
            )
        )
    return roots


def _apply_overrides(profile: RepoProfile, overrides: Dict[str, object]) -> RepoProfile:
    if not overrides:
        return profile
    for attr in ("clouds", "iac_tools", "validation_commands", "environments", "providers"):
        if attr in overrides:
            value = overrides[attr]
            if isinstance(value, str):
                setattr(profile, attr, unique_preserve_order([value]))
            elif isinstance(value, list):
                setattr(profile, attr, unique_preserve_order([str(v) for v in value]))
    conventions = dict(profile.repo_conventions or {})
    conventions["overrides"] = overrides
    profile.repo_conventions = conventions
    return profile


def scan_repository(workspace: str, prefer_git_root: bool = False) -> RepoProfile:
    workspace_path = Path(workspace).expanduser().resolve()
    if prefer_git_root:
        workspace_path = find_git_root(workspace_path)
    if not workspace_path.exists() or not workspace_path.is_dir():
        raise FileNotFoundError(f"Workspace does not exist or is not a directory: {workspace}")

    files: Dict[str, str] = {}
    file_count = 0
    languages: List[str] = []
    tf_files: List[str] = []
    tfvars_files: List[str] = []
    providers: List[str] = []
    all_blocks: List[TerraformBlock] = []
    modules: List[TerraformBlock] = []
    resources: List[TerraformBlock] = []
    variables: List[TerraformBlock] = []
    data_sources: List[TerraformBlock] = []
    pipelines: List[PipelineProfile] = []
    environments: List[str] = []

    for path in iter_repo_files(workspace_path):
        relative = normalize_path(str(path.relative_to(workspace_path)))
        content = read_text(path)
        if content is None:
            continue
        file_count += 1
        files[relative] = content
        ext = path.suffix.lower()
        if ext in _LANGUAGE_BY_EXT:
            languages.append(_LANGUAGE_BY_EXT[ext])
        environments.extend(_detect_env_from_path(relative))

        if relative.endswith(".tf"):
            tf_files.append(relative)
            blocks = parse_terraform_blocks(content, relative)
            all_blocks.extend(blocks)
            providers.extend(parse_required_providers(content))
            for block in blocks:
                if block.provider:
                    providers.append(block.provider)
                if block.block_type == "module":
                    modules.append(block)
                elif block.block_type == "resource":
                    resources.append(block)
                elif block.block_type == "variable":
                    variables.append(block)
                elif block.block_type == "data":
                    data_sources.append(block)
        elif relative.endswith(".tfvars"):
            tfvars_files.append(relative)
        if _looks_like_pipeline(relative, content):
            pipeline = parse_pipeline(relative, content)
            pipelines.append(pipeline)
            environments.extend(pipeline.environments)

    providers = unique_preserve_order([p.lower() for p in providers])
    clouds = providers_to_clouds(providers)
    iac_tools: List[str] = []
    if tf_files or tfvars_files:
        iac_tools.append("terraform")
    if any(path.endswith((".yaml", ".yml")) and "apiVersion:" in content for path, content in files.items()):
        iac_tools.append("kubernetes")

    terraform_roots = _group_terraform_roots(all_blocks, tf_files) if tf_files else []
    pipeline_systems = unique_preserve_order([p.system for p in pipelines])
    validation_commands = _detect_validation_commands(workspace_path, files, terraform_present=bool(tf_files))
    policy_files = _detect_policy_files(files)

    var_files_from_pipelines: List[str] = []
    terraform_versions: List[str] = []
    for pipeline in pipelines:
        var_files_from_pipelines.extend(pipeline.var_files)
        if pipeline.terraform_version:
            terraform_versions.append(pipeline.terraform_version)

    environments.extend(_detect_env_from_path(path) for path in [])
    flattened_envs: List[str] = []
    for env in environments:
        if isinstance(env, list):
            flattened_envs.extend(env)
        else:
            flattened_envs.append(env)

    repo_conventions = {
        "tfvars_patterns": _infer_tfvars_pattern(tfvars_files),
        "pipeline_var_files": unique_preserve_order(var_files_from_pipelines),
        "terraform_versions": unique_preserve_order(terraform_versions),
        "module_source_hosts": unique_preserve_order([m.source for m in modules if m.source]),
        "resource_types_seen": unique_preserve_order([block_resource_type(b) for b in modules + resources if block_resource_type(b)]),
    }

    profile = RepoProfile(
        root=str(workspace_path),
        repo_name=workspace_path.name,
        languages=unique_preserve_order(languages),
        iac_tools=unique_preserve_order(iac_tools),
        clouds=clouds,
        terraform_roots=terraform_roots,
        providers=providers,
        modules=modules,
        resources=resources,
        variables=variables,
        data_sources=data_sources,
        tfvars_files=unique_preserve_order(tfvars_files),
        environments=unique_preserve_order([_normal_env(e) for e in flattened_envs]),
        pipelines=pipelines,
        pipeline_systems=pipeline_systems,
        pipeline_files=unique_preserve_order([p.path for p in pipelines]),
        validation_commands=validation_commands,
        policy_files=policy_files,
        repo_conventions=repo_conventions,
        file_count=file_count,
    )
    return _apply_overrides(profile, load_repo_overrides(workspace_path))
