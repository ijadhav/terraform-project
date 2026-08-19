from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from terrabot_core.models import TerraformBlock, unique_preserve_order

_BLOCK_START = re.compile(
    r'(?m)^\s*(resource|module|variable|data|provider|terraform|output|locals)'
    r'(?:\s+"([^"]+)")?(?:\s+"([^"]+)")?\s*\{'
)

_REQUIRED_PROVIDER_KEY = re.compile(r'(?m)^\s*([A-Za-z0-9_-]+)\s*=\s*\{')
_SOURCE_RE = re.compile(r'(?m)^\s*source\s*=\s*"([^"]+)"')

_PROVIDER_TO_CLOUD = {
    "azurerm": "azure",
    "azuread": "azure",
    "azapi": "azure",
    "aws": "aws",
    "google": "gcp",
    "google-beta": "gcp",
}


def _line_number_at(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _find_matching_brace(text: str, open_brace_index: int) -> int:
    depth = 0
    in_string = False
    escaped = False
    i = open_brace_index
    while i < len(text):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return len(text) - 1


def parse_terraform_blocks(content: str, relative_path: str) -> List[TerraformBlock]:
    blocks: List[TerraformBlock] = []
    if not content:
        return blocks

    for match in _BLOCK_START.finditer(content):
        block_type = match.group(1)
        labels = [label for label in match.groups()[1:] if label]
        open_brace = content.find("{", match.end() - 1)
        if open_brace < 0:
            continue
        close_brace = _find_matching_brace(content, open_brace)
        snippet = content[match.start(): close_brace + 1].strip()
        start_line = _line_number_at(content, match.start())
        end_line = _line_number_at(content, close_brace)

        name: Optional[str] = None
        provider: Optional[str] = None
        source: Optional[str] = None

        if block_type == "module" and labels:
            name = labels[0]
            source_match = _SOURCE_RE.search(snippet)
            if source_match:
                source = source_match.group(1)
        elif block_type in {"resource", "data"} and labels:
            provider = labels[0].split("_")[0]
            name = labels[-1]
        elif block_type in {"variable", "output", "provider"} and labels:
            name = labels[0]
            if block_type == "provider":
                provider = labels[0]

        blocks.append(
            TerraformBlock(
                path=relative_path,
                block_type=block_type,
                labels=labels,
                name=name,
                source=source,
                provider=provider,
                start_line=start_line,
                end_line=end_line,
                snippet=snippet[:4000],
            )
        )
    return blocks


def parse_required_providers(content: str) -> List[str]:
    providers: List[str] = []
    for terraform_match in re.finditer(r'(?s)terraform\s*\{(.*?)\n\}', content or ""):
        body = terraform_match.group(1)
        req_match = re.search(r'(?s)required_providers\s*\{(.*?)\n\s*\}', body)
        if not req_match:
            continue
        providers.extend(_REQUIRED_PROVIDER_KEY.findall(req_match.group(1)))
    return unique_preserve_order(providers)


def providers_to_clouds(providers: Iterable[str]) -> List[str]:
    clouds = []
    for provider in providers:
        key = (provider or "").strip().lower()
        if key in _PROVIDER_TO_CLOUD:
            clouds.append(_PROVIDER_TO_CLOUD[key])
    return unique_preserve_order(clouds)


def infer_resource_type_from_text(path: str, content: str) -> Optional[str]:
    rp = (path or "").lower()
    text = (content or "").lower()
    resource_map: Dict[str, List[str]] = {
        "storage_account": ["azurerm_storage_account", "storage account", "tf-azure-storage-account", "storage_accounts"],
        "key_vault": ["azurerm_key_vault", "key vault", "tf-azure-key-vault"],
        "resource_group": ["azurerm_resource_group", "resource group"],
        "vnet": ["azurerm_virtual_network", "virtual network", "vnet"],
        "subnet": ["azurerm_subnet", "subnet"],
        "private_endpoint": ["azurerm_private_endpoint", "private endpoint"],
        "app_service": ["azurerm_linux_web_app", "azurerm_windows_web_app", "app service"],
        "function_app": ["azurerm_linux_function_app", "azurerm_windows_function_app", "function app"],
        "aks": ["azurerm_kubernetes_cluster", "aks"],
        "mysql": ["azurerm_mysql", "mysql flexible"],
        "s3": ["aws_s3_bucket", "s3 bucket", "/s3.tf", "s3.tf"],
        "ec2": ["aws_instance", "ec2"],
        "iam": ["aws_iam", "iam"],
        "rds": ["aws_db_instance", "rds"],
        "vpc": ["aws_vpc", "vpc"],
        "security_group": ["aws_security_group", "security group"],
        "lambda": ["aws_lambda", "lambda"],
    }
    for resource_type, hints in resource_map.items():
        if any(hint in rp or hint in text for hint in hints):
            return resource_type
    return None


def block_resource_type(block: TerraformBlock) -> Optional[str]:
    label = "_".join(block.labels or []).lower()
    source = (block.source or "").lower()
    name = (block.name or "").lower()
    return infer_resource_type_from_text(block.path, "\n".join([label, source, name, block.snippet or ""]))
