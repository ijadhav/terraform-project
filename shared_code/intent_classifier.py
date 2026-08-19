import re
from typing import Dict, List, Tuple

INFRA_RESOURCE_TERMS = [
    "terraform", ".tf", "main.tf", "variables.tf", "outputs.tf", "providers.tf",
    "aws", "azure", "azurerm",
    "resource group", "storage account", "key vault", "virtual network", "vnet",
    "subnet", "nsg", "network security group", "application gateway", "app gateway",
    "private endpoint", "aks", "vm", "virtual machine",
    "ec2", "s3", "rds", "iam", "lambda", "vpc", "route table",
    "security group", "internet gateway", "load balancer", "database",
    "public ip", "ssh key", "admin username", "cidr", "port", "http", "https",
    "ingress", "egress", "listener", "target group", "instance type", "vm size"
]

INFRA_ACTION_TERMS = [
    "create", "provision", "deploy", "generate", "build",
    "add", "update", "modify", "change", "remove", "delete",
    "replace", "enable", "disable", "attach", "detach",
    "rename", "edit", "increase", "decrease", "scale",
    "open", "close", "allow", "deny", "expose", "restrict",
    "set", "configure", "move", "switch", "assign"
]

CHAT_TERMS = [
    "hello", "hi", "hey", "help", "explain", "what is", "how does",
    "why", "can you tell me", "give me steps", "summarize", "example",
    "difference between", "what's your name", "name some", "show me"
]

FOLLOWUP_INFRA_TERMS = [
    "instance", "bucket", "vm", "vnet", "subnet", "resource group",
    "storage account", "key vault", "gateway", "database", "terraform",
    "module", "provider", "tag", "sku", "cidr", "private endpoint",
    "security group", "port", "http", "https", "listener", "target group",
    "public ip", "ssh key", "admin username", "instance type", "vm size"
]


def contains_phrase(text: str, phrases: List[str]) -> List[str]:
    matched = []
    for phrase in phrases:
        if phrase in text:
            matched.append(phrase)
    return matched


def classify_intent(prompt: str, has_thread_pr_state: bool = False) -> Tuple[str, Dict]:
    text = (prompt or "").strip().lower()

    matched_resources = contains_phrase(text, INFRA_RESOURCE_TERMS)
    matched_actions = contains_phrase(text, INFRA_ACTION_TERMS)
    matched_chat = contains_phrase(text, CHAT_TERMS)

    infra_score = 0
    chat_score = 0

    if matched_resources:
        infra_score += 3
    if matched_actions:
        infra_score += 2
    if matched_resources and matched_actions:
        infra_score += 4

    if matched_chat:
        chat_score += 3

    if "?" in text:
        chat_score += 1

    if has_thread_pr_state:
        matched_followup = contains_phrase(text, FOLLOWUP_INFRA_TERMS)
        if matched_followup:
            infra_score += 3
        if matched_actions and matched_followup:
            infra_score += 4

    if not matched_resources and not matched_actions:
        chat_score += 2

    intent = "infra" if infra_score >= max(4, chat_score + 2) else "chat"





    debug = {
        "intent": intent,
        "infra_score": infra_score,
        "chat_score": chat_score,
        "matched_resources": matched_resources,
        "matched_actions": matched_actions,
        "matched_chat": matched_chat,
        "has_thread_pr_state": has_thread_pr_state,
    }

    return intent, debug

def classify_intent_only(prompt: str, has_thread_pr_state: bool = False) -> Tuple[str, Dict]:
    return classify_intent(prompt, has_thread_pr_state=has_thread_pr_state)