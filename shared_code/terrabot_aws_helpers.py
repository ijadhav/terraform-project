from __future__ import annotations
from .terrabot_cloud_helpers import AWS_NONPROD, AWS_PROD

DEFAULT_NONPROD_ENVIRONMENT = "minidev"
REPO_TARGET = "tf-devops"

def environment_path(name: str) -> str:
    key = str(name or "").strip().lower().replace("-", "_")
    return AWS_NONPROD.get(key) or AWS_PROD.get(key) or ""
