from __future__ import annotations

import re
from pathlib import Path
from typing import List

from terrabot_core.models import PipelineProfile, unique_preserve_order

_VAR_FILE_RE = re.compile(r'-var-file\s*=\s*"?([^"\s\\]+)"?')
_TERRAFORM_VERSION_RE = re.compile(r'terraformVersion\s*:\s*[\'\"]?([^\'\"\n]+)[\'\"]?', re.IGNORECASE)
_ENV_RE = re.compile(r'(?:adoEnvironment|environment|type|tier|subscriptionName)\s*:\s*[\'\"]?([^\'\"\n#]+)', re.IGNORECASE)
_TEMPLATE_RE = re.compile(r'template\s*:\s*([^\s]+)')


def detect_pipeline_system(relative_path: str, content: str) -> str:
    rp = relative_path.lower().replace("\\", "/")
    text = content.lower()
    if rp.startswith(".github/workflows/"):
        return "github-actions"
    if "azure-pipelines" in rp or "ado-pipeline" in text or "stages:" in text and "terraform" in text:
        return "azure-pipelines"
    if rp.endswith("jenkinsfile"):
        return "jenkins"
    if "gitlab-ci" in rp:
        return "gitlab-ci"
    return "pipeline"


def parse_pipeline(relative_path: str, content: str) -> PipelineProfile:
    system = detect_pipeline_system(relative_path, content or "")
    version_match = _TERRAFORM_VERSION_RE.search(content or "")
    var_files = unique_preserve_order(_VAR_FILE_RE.findall(content or ""))
    raw_envs = [value.strip().strip("'\"") for value in _ENV_RE.findall(content or "")]
    envs: List[str] = []
    for value in raw_envs:
        for token in re.split(r'[,\s]+', value):
            token = token.strip().lower()
            if token in {"dev", "prd", "prod", "npr", "sbx", "qa", "uat", "stg", "sandbox", "nonproduction", "production"} or re.match(r'^(dev|prd|prod|npr|sbx|qa|uat|stg)[-_]', token):
                envs.append(token)
    templates = unique_preserve_order(_TEMPLATE_RE.findall(content or ""))
    return PipelineProfile(
        path=relative_path,
        system=system,
        terraform_version=version_match.group(1).strip() if version_match else None,
        var_files=var_files,
        environments=unique_preserve_order(envs),
        validation_templates=templates,
    )
