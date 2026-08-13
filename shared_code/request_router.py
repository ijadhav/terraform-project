import re
from typing import Optional, Dict, Any
from shared_code.intent_classifier import classify_intent
from shared_code.router_types import RouterDecision


AWS_HINTS = {
    "aws", "amazon", "amazon web services",
    "ec2", "s3", "iam", "rds", "vpc", "security group",
    "route table", "internet gateway", "lambda", "alb", "elb", "asg", "cloudfront",
    "redshift", "eks", "ecs", "target group", "listener"
}

AZURE_HINTS = {
    "azure", "microsoft azure", "azurerm",
    "resource group", "vnet", "nsg", "aks", "vm",
    "storage account", "app service", "key vault",
    "virtual network", "network security group", "private endpoint"
}

EXPLICIT_NEW_MODULE_HINTS = {
    "create module", "new module", "new repo", "new repository",
    "reusable module", "module repo"
}

AZURE_APPROVED_PATTERN_HINTS = {
    "resource group",
    "storage account",
    "key vault",
    "rbac",
    "vnet",
    "subnet",
    "vmss",
    "private endpoint",
    "aks",
    "mysql",
    "data factory"
}

REQUIRED_ENV_HINTS = {
    "dev", "prd", "prod", "sbx", "npr", "environment", "env"
}

GENERIC_RESOURCE_HINTS = {
    "server", "database", "app", "application", "instance", "storage"
}

FOLLOWUP_CHANGE_HINTS = {
    "change", "update", "modify", "rename", "set", "use", "switch","install", "add", "remove", "delete", "create", "provision", "deprovision",
    "increase", "decrease", "move", "attach", "detach", "enable", "disable",
    "name", "in prod", "in dev", "in sbx", "in npr", "for prod", "for dev","deploy", "deployment", "environment variable", "tag", "label", "port", "size", "sku",
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _contains_any(text: str, phrases: set[str]) -> bool:
    return any(p in text for p in phrases)


def _looks_like_followup_change(prompt: str) -> bool:
    text = _normalize(prompt)

    if any(p in text for p in FOLLOWUP_CHANGE_HINTS):
        return True

    if '"' in prompt or "'" in prompt:
        return True

    if re.search(r"\b(name|identifier|cluster|bucket|instance|engine|port|size|sku)\b", text):
        return True

    return False


def detect_cloud_from_prompt(prompt: str) -> Optional[str]:
    text = _normalize(prompt)

    # explicit cloud mention wins
    if "azure" in text or "azurerm" in text:
        return "azure"
    if "aws" in text or "amazon web services" in text:
        return "aws"

    # semantic-style lightweight inference for generic infra prompts
    azure_like = [
        "linux vm", "windows vm", "virtual machine", "vm", "resource group",
        "vnet", "subnet", "nsg", "storage", "identity", "app service",
        "private endpoint", "key vault"
    ]
    aws_like = [
        "ec2", "s3", "iam", "rds", "vpc", "security group",
        "target group", "listener", "alb", "lambda", "eks", "redshift"
    ]

    azure_hits = sum(1 for t in azure_like if t in text)
    aws_hits = sum(1 for t in aws_like if t in text)

    if azure_hits > aws_hits and azure_hits > 0:
        return "azure"
    if aws_hits > azure_hits and aws_hits > 0:
        return "aws"

    # safe default for generic VM-style infra
    if any(x in text for x in ["linux vm", "windows vm", "virtual machine", "create vm", "vm size"]):
        return "azure"

    return None


def infer_cloud_from_thread_state(prompt: str, recovered_state: Dict[str, Any]) -> Optional[str]:
    active_clouds = [c for c in ("aws", "azure") if c in (recovered_state or {})]

    if len(active_clouds) == 1:
        return active_clouds[0]

    prompt_cloud = detect_cloud_from_prompt(prompt)
    if prompt_cloud:
        return prompt_cloud

    text = _normalize(prompt)

    aws_followup_terms = {
        "s3", "bucket", "ec2", "iam", "rds", "vpc", "lambda", "eks",
        "alb", "listener", "target group", "versioning", "kms", "route53"
    }
    azure_followup_terms = {
        "resource group", "storage account", "key vault", "vnet", "nsg",
        "aks", "private endpoint", "vm", "virtual machine", "linux vm",
        "windows vm", "subnet", "public ip", "managed identity"
    }

    if len(active_clouds) == 2:
        aws_hits = sum(1 for t in aws_followup_terms if t in text)
        azure_hits = sum(1 for t in azure_followup_terms if t in text)

        if aws_hits > azure_hits and aws_hits > 0:
            return "aws"
        if azure_hits > aws_hits and azure_hits > 0:
            return "azure"

    return None

def has_required_context(prompt: str, cloud: Optional[str], has_existing_context: bool) -> bool:
    text = _normalize(prompt)

    if has_existing_context:
        return True

    if cloud is None:
        return False

    if cloud == "aws" and any(
        x in text for x in {
            "ec2", "s3", "iam", "vpc", "rds", "lambda", "redshift", "eks"
        }
    ):
        return True

    if cloud == "azure" and any(
        x in text for x in {
            "resource group", "storage account", "key vault",
            "vnet", "aks", "vmss", "app service", "private endpoint",
            "linux vm", "windows vm", "virtual machine", "vm"
        }
    ):
        return True

    if _contains_any(text, REQUIRED_ENV_HINTS):
        return True

    # allow generic Azure-style infra to proceed instead of forcing clarification
    if any(x in text for x in {"server", "database", "app", "application", "instance", "storage"}):
        return cloud == "azure"

    return True


def azure_request_requires_new_module_repo(prompt: str) -> bool:
    text = _normalize(prompt)
    return _contains_any(text, EXPLICIT_NEW_MODULE_HINTS)


def azure_has_known_pattern(prompt: str) -> bool:
    text = _normalize(prompt)
    return _contains_any(text, AZURE_APPROVED_PATTERN_HINTS)


def route_request(
    prompt: str,
    requested_mode: Optional[str] = None,
    requested_cloud: Optional[str] = None,
    recovered_state: Optional[Dict[str, Any]] = None,
    has_existing_pr_context: bool = False,
    repo_profile: Optional[Any] = None,
    workflow_profile: Optional[Any] = None,
) -> RouterDecision:
    recovered_state = recovered_state or {}
    requested_mode = (requested_mode or "").strip().lower()
    requested_cloud = (requested_cloud or "").strip().lower() or None

    if requested_mode == "chat":
        return RouterDecision(
            request_type="chat",
            cloud=None,
            workflow=None,
            reason="request explicitly forced to chat",
            debug={}
        )

    if requested_mode == "infra":
        forced_intent = "infra"
        intent_debug = {"forced_mode": "infra"}
    else:
        forced_intent, intent_debug = classify_intent(
            prompt,
            has_thread_pr_state=bool(recovered_state)
        )

    # Important: if this is an existing infra thread and the prompt looks like a follow-up change,
    # keep it in infra mode even if classifier is uncertain.
    if forced_intent != "infra" and bool(recovered_state) and _looks_like_followup_change(prompt):
        forced_intent = "infra"
        intent_debug = dict(intent_debug or {})
        intent_debug["followup_override"] = True

    if forced_intent != "infra":
        return RouterDecision(
            request_type="chat",
            cloud=None,
            workflow=None,
            reason="not classified as infrastructure request",
            debug=intent_debug
        )

    repo_cloud = None
    if repo_profile is not None:
        repo_clouds = getattr(repo_profile, "clouds", None) or []
        if len(repo_clouds) == 1:
            repo_cloud = repo_clouds[0]

    workflow_cloud = getattr(workflow_profile, "cloud", None) if workflow_profile is not None else None

    cloud = (
        requested_cloud
        or workflow_cloud
        or detect_cloud_from_prompt(prompt)
        or infer_cloud_from_thread_state(prompt, recovered_state)
        or repo_cloud
    )

    if not cloud:
        return RouterDecision(
            request_type="infra",
            cloud=None,
            workflow="clarification_required",
            reason="cloud is unclear",
            debug=intent_debug
        )

    if not has_required_context(prompt, cloud, has_existing_pr_context or bool(recovered_state)):
        return RouterDecision(
            request_type="infra",
            cloud=cloud,
            workflow="clarification_required",
            reason="missing required deployment context",
            debug=intent_debug
        )

    if workflow_profile is not None and getattr(workflow_profile, "workflow_type", None):
        return RouterDecision(
            request_type="infra",
            cloud=cloud,
            workflow=getattr(workflow_profile, "workflow_type"),
            reason="repo-aware workflow profile supplied by terrabot_core",
            debug=dict(intent_debug or {}, repo_aware=True)
        )

    if cloud == "aws":
        return RouterDecision(
            request_type="infra",
            cloud="aws",
            workflow="aws_module_consumer",
            reason="aws request should follow inferred Terraform strategy",
            debug=intent_debug
        )

    if cloud == "azure":
        if azure_request_requires_new_module_repo(prompt):
            return RouterDecision(
                request_type="infra",
                cloud="azure",
                workflow="azure_module_repo_creation",
                reason="user explicitly asked for a new azure module or repo",
                debug=intent_debug
            )

        if has_existing_pr_context or bool(recovered_state) or azure_has_known_pattern(prompt):
            return RouterDecision(
                request_type="infra",
                cloud="azure",
                workflow="azure_consumer_generation",
                reason="azure request matches existing tf-azure-hub style flow",
                debug=intent_debug
            )

        return RouterDecision(
            request_type="infra",
            cloud="azure",
            workflow="azure_module_repo_creation",
            reason="azure request does not match known approved consumer pattern",
            debug=intent_debug
        )

    return RouterDecision(
        request_type="infra",
        cloud=None,
        workflow="clarification_required",
        reason="unable to classify safely",
        debug=intent_debug
    )