"""AWS backend workflow helpers for Terrabot.

This module intentionally contains only AWS-specific pending-state and backend
workflow helpers. It must not perform generic cloud intent recognition or call
Azure workflow state. Intent-Terraform remains the authority for user intent and
Terraform JSON generation; terrabot_service.py dispatches here only when the
active backend state or Intent-Terraform result is AWS.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


AWS_AFFIRMATIVE_REPLIES = {
    "yes",
    "y",
    "use it",
    "reference it",
    "go ahead",
    "proceed",
    "continue",
    "create it",
    "generate it",
}

AWS_NEGATIVE_REPLIES = {
    "no",
    "n",
    "dont use it",
    "don't use it",
    "skip it",
    "not now",
    "cancel",
}


@dataclass(frozen=True)
class AwsPendingModuleDecision:
    pending: bool = False
    affirmative: bool = False
    negative: bool = False
    force_flow: bool = False
    workflow: str = "aws_module_creation_confirmation"
    reason: str = ""


def normalize_aws_reply(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).lower()


def is_aws_affirmative_reply(value: str) -> bool:
    text = normalize_aws_reply(value)
    return bool(
        text in AWS_AFFIRMATIVE_REPLIES
        or re.match(r"^(?:yes|y|create|generate|proceed|go ahead|continue)\b", text)
    )


def is_aws_negative_reply(value: str) -> bool:
    text = normalize_aws_reply(value)
    return bool(
        text in AWS_NEGATIVE_REPLIES
        or re.match(r"^(?:no|n|dont|don't|skip|cancel)\b", text)
    )


def classify_aws_pending_module_reply(prompt: str, pending_aws_discovery: dict | None) -> AwsPendingModuleDecision:
    """Classify a reply while an AWS module creation/confirmation is pending.

    A bare "yes" must be consumed by AWS when an AWS confirmation is active;
    otherwise stale Azure pending states can incorrectly treat it as an Azure
    value-selection confirmation.
    """
    if not pending_aws_discovery:
        return AwsPendingModuleDecision()

    discovery = (pending_aws_discovery or {}).get("discovery") or {}
    workflow = discovery.get("decision_state") or "aws_module_creation_confirmation"
    affirmative = is_aws_affirmative_reply(prompt)
    negative = is_aws_negative_reply(prompt)
    force_flow = affirmative or negative

    return AwsPendingModuleDecision(
        pending=True,
        affirmative=affirmative,
        negative=negative,
        force_flow=force_flow,
        workflow=workflow,
        reason="Pending AWS module creation/confirmation handled by AWS workflow helper." if force_flow else "",
    )


def should_suppress_azure_pending_for_aws(prompt: str, pending_aws_discovery: dict | None) -> bool:
    """Return True when an AWS pending confirmation should take precedence."""
    decision = classify_aws_pending_module_reply(prompt, pending_aws_discovery)
    return bool(decision.force_flow)
