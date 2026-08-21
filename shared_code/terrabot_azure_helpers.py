from __future__ import annotations
from .terrabot_cloud_helpers import AZURE_ALIASES, AZURE_NONPROD, AZURE_PROD

DEFAULT_NONPROD_ENVIRONMENT = "sbx-infra"
REPO_TARGET = "tf-azure-hub"

def canonical_environment(name: str) -> str:
    key = str(name or "").strip().lower().replace("_", "-")
    return AZURE_ALIASES.get(key, key)

def environment_root(name: str) -> str:
    key = canonical_environment(name)
    return AZURE_NONPROD.get(key) or AZURE_PROD.get(key) or ""
