from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from terrabot_core.models import EvidenceItem, RepoProfile, TerraformBlock, WorkflowProfile, unique_preserve_order
from terrabot_core.terraform_parser import block_resource_type

_CLOUD_HINTS = {
    "azure": [
        "azure",
        "azurerm",
        "storage account",
        "resource group",
        "key vault",
        "vnet",
        "subnet",
        "private endpoint",
        "function app",
        "app service",
        "aks",
    ],
    "aws": [
        "aws",
        "amazon web services",
        "s3",
        "ec2",
        "iam",
        "rds",
        "vpc",
        "security group",
        "lambda",
        "eks",
    ],
}

_RESOURCE_HINTS: Dict[str, List[str]] = {
    "storage_account": ["storage account", "storage", "blob", "container", "azurerm_storage_account"],
    "key_vault": ["key vault", "vault", "secret", "azurerm_key_vault"],
    "resource_group": ["resource group", "rg", "azurerm_resource_group"],
    "vnet": ["vnet", "virtual network", "azurerm_virtual_network"],
    "subnet": ["subnet", "azurerm_subnet"],
    "private_endpoint": ["private endpoint", "private link", "azurerm_private_endpoint"],
    "app_service": ["app service", "web app", "linux web app", "windows web app"],
    "function_app": ["function app", "azure function", "functions app"],
    "aks": ["aks", "kubernetes cluster"],
    "mysql": ["mysql", "flexible server"],
    "s3": ["s3", "bucket", "aws_s3_bucket"],
    "ec2": ["ec2", "instance", "aws_instance"],
    "iam": ["iam", "role", "policy"],
    "rds": ["rds", "database", "db instance"],
    "cloudamqp": ["cloudamqp", "cloud amqp", "rabbitmq", "rabbit mq", "aws_mq_broker"],
    "vpc": ["vpc", "aws_vpc"],
    "security_group": ["security group", "sg", "aws_security_group"],
    "lambda": ["lambda", "function", "aws_lambda"],
}

_ACTION_NEW_HINTS = {"add", "create", "provision", "new", "deploy"}
_ACTION_MODIFY_HINTS = {"change", "update", "modify", "rename", "enable", "disable", "increase", "decrease", "remove", "delete"}
_NEW_MODULE_HINTS = {"new module", "create module", "reusable module", "module repo", "new repo", "new repository"}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def detect_cloud_from_prompt(prompt: str) -> Optional[str]:
    text = _normalize(prompt)
    scores = {cloud: sum(1 for hint in hints if hint in text) for cloud, hints in _CLOUD_HINTS.items()}
    if scores["azure"] > scores["aws"] and scores["azure"] > 0:
        return "azure"
    if scores["aws"] > scores["azure"] and scores["aws"] > 0:
        return "aws"
    return None


def detect_resource_type(prompt: str) -> Optional[str]:
    text = _normalize(prompt)
    scored: List[Tuple[int, str]] = []
    for resource_type, hints in _RESOURCE_HINTS.items():
        score = sum(1 for hint in hints if hint in text)
        if score:
            scored.append((score, resource_type))
    if not scored:
        return None
    return sorted(scored, reverse=True)[0][1]


def detect_target_environment(prompt: str, profile: RepoProfile) -> Optional[str]:
    text = _normalize(prompt)

    # Prefer exact repo scopes such as npr-int or prd-us5 over broad aliases like npr/prd.
    for env in sorted(profile.environments, key=len, reverse=True):
        if re.search(rf"(?<![a-z0-9]){re.escape(env.lower())}(?![a-z0-9])", text):
            return env

    env_aliases = {
        "production": "prd",
        "prod": "prd",
        "prd": "prd",
        "nonproduction": "npr",
        "non-prod": "npr",
        "non prod": "npr",
        "npr": "npr",
        "sandbox": "sbx",
        "sbx": "sbx",
        "staging": "stg",
        "stage": "stg",
        "stg": "stg",
        "development": "dev",
        "dev": "dev",
        "qa": "qa",
        "uat": "uat",
    }
    for alias, canonical in env_aliases.items():
        if re.search(rf"\b{re.escape(alias)}\b", text):
            return canonical
    return None


def _is_infra_prompt(prompt: str) -> bool:
    text = _normalize(prompt)
    infra_terms = {
        "terraform",
        "infra",
        "infrastructure",
        "provision",
        "deploy",
        "add",
        "create",
        "resource",
        "module",
        "storage",
        "bucket",
        "vnet",
        "subnet",
        "key vault",
        "ec2",
        "s3",
        "rds",
        "iam",
        "pipeline",
        "workflow",
        "tfvars",
    }
    return any(term in text for term in infra_terms)


def _find_matching_blocks(profile: RepoProfile, resource_type: Optional[str]) -> List[TerraformBlock]:
    if not resource_type:
        return []
    matches: List[TerraformBlock] = []
    for block in profile.modules + profile.resources:
        if block_resource_type(block) == resource_type:
            matches.append(block)
    return matches


def _tfvars_for_environment(profile: RepoProfile, environment: Optional[str]) -> List[str]:
    if not environment:
        return []
    env = environment.lower()
    matches = []
    for path in profile.tfvars_files:
        lower = path.lower()
        if f"/{env}/" in lower or lower.startswith(f"vars/{env}/") or lower.endswith(f"/{env}.tfvars") or f"_{env}" in lower:
            matches.append(path)
    return unique_preserve_order(matches)


def _pipeline_files_for_environment(profile: RepoProfile, environment: Optional[str]) -> List[str]:
    if not environment:
        return profile.pipeline_files[:3]
    env = environment.lower()
    matches = []
    for pipeline in profile.pipelines:
        lower = pipeline.path.lower()
        if env in lower or env in [e.lower() for e in pipeline.environments] or any(f"/{env}/" in vf.lower() for vf in pipeline.var_files):
            matches.append(pipeline.path)
    return unique_preserve_order(matches)


def _find_ambiguous_env_value_files(value_files: List[str], environment: Optional[str]) -> List[str]:
    if not environment or environment not in {"npr", "prd", "prod", "sbx", "dev", "qa", "uat", "stg"}:
        return []
    subscription_like = []
    for path in value_files:
        parts = path.split("/")
        for part in parts:
            if re.match(rf"^{re.escape(environment)}[-_].+", part, re.IGNORECASE):
                subscription_like.append(part)
    return unique_preserve_order(subscription_like)


def _build_evidence(profile: RepoProfile, matches: List[TerraformBlock], value_files: List[str], pipeline_files: List[str]) -> List[EvidenceItem]:
    evidence: List[EvidenceItem] = []
    for provider in profile.providers[:8]:
        evidence.append(EvidenceItem(path="<repo-profile>", reason=f"provider detected: {provider}", kind="provider", score=1.0))
    for block in matches[:5]:
        evidence.append(
            EvidenceItem(
                path=block.path,
                reason=f"similar Terraform {block.block_type} block: {block.name or '/'.join(block.labels)}",
                kind=block.block_type,
                start_line=block.start_line,
                end_line=block.end_line,
                snippet=block.snippet[:1200],
                score=8.0,
            )
        )
    for path in value_files[:6]:
        evidence.append(EvidenceItem(path=path, reason="environment-specific tfvars file", kind="tfvars", score=5.0))
    for path in pipeline_files[:4]:
        evidence.append(EvidenceItem(path=path, reason="pipeline references target Terraform workflow or var-files", kind="pipeline", score=4.0))
    return evidence


def infer_workflow(prompt: str, profile: RepoProfile, requested_cloud: Optional[str] = None) -> WorkflowProfile:
    text = _normalize(prompt)
    prompt_cloud = detect_cloud_from_prompt(prompt)
    cloud = requested_cloud or prompt_cloud or (profile.clouds[0] if len(profile.clouds) == 1 else None)
    resource_type = detect_resource_type(prompt)
    environment = detect_target_environment(prompt, profile)
    questions: List[str] = []

    if not _is_infra_prompt(prompt):
        return WorkflowProfile(
            workflow_type="chat_or_unknown",
            confidence=0.2,
            cloud=cloud,
            resource_type=resource_type,
            target_environment=environment,
            needs_clarification=True,
            clarification_reason="request does not look like an infrastructure change",
            questions=["Please describe the infrastructure resource or Terraform change you want Terrabot to make."],
            validation_commands=profile.validation_commands,
        )

    if not cloud:
        questions.append("Which cloud should this change target: Azure, AWS, or another provider detected in this repo?")
    if not resource_type:
        questions.append("Which infrastructure resource type should be changed or created?")
    if not environment and profile.environments:
        questions.append(f"Which environment should this target? Detected environments: {', '.join(profile.environments)}.")

    if "terraform" not in profile.iac_tools:
        return WorkflowProfile(
            workflow_type="unknown_infra_workflow",
            confidence=0.15,
            cloud=cloud,
            resource_type=resource_type,
            target_environment=environment,
            validation_commands=profile.validation_commands,
            needs_clarification=True,
            clarification_reason="no Terraform files were detected in the workspace",
            questions=questions or ["No Terraform files were detected. Which IaC tool should Terrabot use?"],
        )

    matches = _find_matching_blocks(profile, resource_type)
    value_files = _tfvars_for_environment(profile, environment)
    pipeline_files = _pipeline_files_for_environment(profile, environment)
    target_files = unique_preserve_order([block.path for block in matches[:4]] + ["variables.tf" if any(v.path == "variables.tf" for v in profile.variables) else ""] + value_files[:4] + pipeline_files[:2])

    ambiguous_values = _find_ambiguous_env_value_files(value_files, environment)
    if len(ambiguous_values) > 1:
        questions.append(
            f"Which {environment.upper()} subscription/scope should receive the change: {', '.join(ambiguous_values)}?"
        )

    if any(hint in text for hint in _NEW_MODULE_HINTS):
        workflow_type = "terraform_new_module"
        confidence = 0.72 if cloud and resource_type else 0.48
    elif matches:
        workflow_type = "terraform_existing_module_consumer"
        confidence = 0.86 if cloud and resource_type and environment else 0.68
    elif any(word in text for word in _ACTION_MODIFY_HINTS):
        workflow_type = "terraform_modify_existing_resource"
        confidence = 0.62 if resource_type else 0.42
    elif any(word in text for word in _ACTION_NEW_HINTS):
        workflow_type = "terraform_new_resource_same_root"
        confidence = 0.58 if cloud and resource_type else 0.38
    else:
        workflow_type = "unknown_infra_workflow"
        confidence = 0.3

    evidence = _build_evidence(profile, matches, value_files, pipeline_files)
    needs_clarification = bool(questions) or confidence < 0.5
    clarification_reason = "; ".join(questions) if questions else ("low confidence workflow inference" if confidence < 0.5 else None)

    return WorkflowProfile(
        workflow_type=workflow_type,
        confidence=confidence,
        cloud=cloud,
        resource_type=resource_type,
        target_environment=environment,
        target_files=target_files,
        value_files=value_files,
        validation_commands=profile.validation_commands,
        apply_strategy="generate_patch_review_validate_then_apply",
        evidence=evidence,
        needs_clarification=needs_clarification,
        clarification_reason=clarification_reason,
        questions=questions,
    )
