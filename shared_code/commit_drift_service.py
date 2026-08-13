"""Azure DevOps deployed-commit drift detection for Terrabot.

This module intentionally does not use GitHub directory/path history to decide
what NPR and PRD mean.  NPR/dev and PRD/prod are resolved from Azure DevOps
pipelines.  Drift is calculated by comparing:

    GitHub main branch latest SHA
    latest successful Azure DevOps NPR/dev pipeline run sourceVersion
    latest successful Azure DevOps PRD/prod pipeline run sourceVersion

GitHub is still used for two things only:
  1. reading the latest main branch commit for the repo
  2. enriching relevant SHAs with commit/PR/Jira metadata for the UI

Azure DevOps is the source of truth for what has been deployed to NPR/PRD.
"""

from __future__ import annotations

import base64
import json
import os
import re
import tempfile
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

JsonDict = Dict[str, Any]


def _safe_int_env(name: str, default: int, *aliases: str) -> int:
    """Read an integer env var without making module import fail."""
    for key in (name, *aliases):
        raw = os.getenv(key)
        if raw is None or str(raw).strip() == "":
            continue
        try:
            return int(str(raw).strip())
        except (TypeError, ValueError):
            return default
    return default


CACHE_SCHEMA_VERSION = "terrabot-ado-deployed-commit-drift-v7-npr-prd-main-single-card"
CACHE_FILE = os.getenv(
    "DRIFT_COMMIT_CACHE_FILE",
    os.path.join(tempfile.gettempdir(), f"{CACHE_SCHEMA_VERSION}.json"),
)
CACHE_TTL_SECONDS = _safe_int_env("DRIFT_COMMIT_CACHE_TTL_SECONDS", 300)
GITHUB_TIMEOUT_SECONDS = _safe_int_env("DRIFT_GITHUB_TIMEOUT_SECONDS", 15)
AZDO_TIMEOUT_SECONDS = _safe_int_env("DRIFT_AZDO_TIMEOUT_SECONDS", 20, "AZDO_TIMEOUT_SECONDS")
JIRA_TIMEOUT_SECONDS = _safe_int_env("DRIFT_JIRA_TIMEOUT_SECONDS", 10)
STATUS_AUTO_REFRESH = os.getenv("DRIFT_STATUS_AUTO_REFRESH", "false").strip().lower() in {"1", "true", "yes", "on"}
AZDO_FALLBACK_ANY_BRANCH = os.getenv("DRIFT_AZDO_FALLBACK_ANY_BRANCH", "true").strip().lower() in {"1", "true", "yes", "on"}
AZDO_API_VERSION = os.getenv("AZDO_API_VERSION", "7.1").strip() or "7.1"
DEBUG = os.getenv("DRIFT_DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"}
SHOW_INVALID_JIRA_KEYS = os.getenv("DRIFT_SHOW_INVALID_JIRA_KEYS", "false").strip().lower() in {"1", "true", "yes", "on"}
JIRA_MIN_ISSUE_NUMBER_DIGITS = _safe_int_env("JIRA_MIN_ISSUE_NUMBER_DIGITS", 2)
JIRA_EXTRACT_FROM_BRANCH_REFS = os.getenv("JIRA_EXTRACT_FROM_BRANCH_REFS", "true").strip().lower() in {"1", "true", "yes", "on"}
JIRA_EXTRACT_FROM_PR_COMMENTS = os.getenv("JIRA_EXTRACT_FROM_PR_COMMENTS", "true").strip().lower() in {"1", "true", "yes", "on"}
DEFAULT_IGNORED_JIRA_PROJECT_KEYS = "US,EU,CA,STO,AWS,AZURE,NPR,PRD,SBX,DEV,PROD"
JIRA_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")

PROVIDER_DEFAULTS: Dict[str, JsonDict] = {
    "aws": {
        "label": "AWS",
        "repo_env_names": ["GITHUB_AWS_REPO", "AWS_GITHUB_REPO"],
        "owner_env_names": ["GITHUB_AWS_OWNER", "AWS_GITHUB_OWNER", "GITHUB_OWNER"],
        "default_repo": "tf-devops",
        "main_branch_env": "AWS_MAIN_BRANCH",
        "default_main_branch": "main",
        "groups_env_names": ["AWS_ADO_PIPELINE_GROUPS", "AWS_AZDO_PIPELINE_GROUPS", "AWS_PIPELINE_FILE_PAIRS"],
        "default_groups": [
            {
                "name": "core",
                "label": "tf-devops core dev/prod",
                "npr": "yaml:azure-pipelines_dev.yml",
                "prd": "yaml:azure-pipelines_prod.yml",
            },
        ],
    },
    "azure": {
        "label": "Azure",
        "repo_env_names": ["GITHUB_AZURE_REPO", "AZURE_GITHUB_REPO"],
        "owner_env_names": ["GITHUB_AZURE_OWNER", "AZURE_GITHUB_OWNER", "GITHUB_OWNER"],
        "default_repo": "tf-azure-hub",
        "main_branch_env": "AZURE_MAIN_BRANCH",
        "default_main_branch": "main",
        "groups_env_names": ["AZURE_ADO_PIPELINE_GROUPS", "AZURE_AZDO_PIPELINE_GROUPS", "AZURE_PIPELINE_FILE_PAIRS"],
        "default_groups": [
            {
                "name": "hub",
                "label": "tf-azure-hub NPR/PRD",
                "npr": "yaml:pipelines/azure-pipelines-npr.yml",
                "prd": "yaml:pipelines/azure-pipelines-prd.yml",
            }
        ],
    },
}

_MEMORY_CACHE: Optional[JsonDict] = None
_MEMORY_CACHE_LOADED_AT = 0.0
_JIRA_CACHE: Dict[str, JsonDict] = {}
_PR_CACHE: Dict[str, JsonDict] = {}
_COMMIT_CACHE: Dict[str, JsonDict] = {}
_DEF_CACHE: Dict[str, List[JsonDict]] = {}
_BUILD_CACHE: Dict[str, Optional[JsonDict]] = {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _short_sha(sha: Optional[str]) -> str:
    return (sha or "")[:12]


def _env_first(names: Iterable[str], default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def _split_csv(value: str) -> List[str]:
    if not value:
        return []
    parts: List[str] = []
    for item in value.replace("\n", ",").split(","):
        cleaned = item.strip().strip('"').strip("'")
        if cleaned:
            parts.append(cleaned)
    return parts


def _parse_date(value: Optional[str]) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _github_url(owner: str, repo: str, sha: str) -> str:
    return f"https://github.com/{owner}/{repo}/commit/{sha}" if owner and repo and sha else ""


def _github_compare_url(owner: str, repo: str, base_sha: str, head_sha: str) -> str:
    return f"https://github.com/{owner}/{repo}/compare/{base_sha}...{head_sha}" if owner and repo and base_sha and head_sha else ""


def _safe_branch_name(value: str, default: str = "main") -> str:
    """Return the Git branch used for the source baseline.

    Older setup guides used AWS_NPR_BRANCH/AWS_PRD_BRANCH.  NPR/PRD are not Git
    branches in the ADO deployed-commit model.  If a main branch override is
    accidentally set to npr/prd/dev/prod, fall back to main instead of calling
    /branches/npr and failing with GitHub 404.
    """
    branch = (value or default or "main").strip()
    if branch.lower() in {"npr", "prd", "dev", "prod", "production", "nonprod", "non-prod"}:
        return default or "main"
    return branch


def _provider_config(provider: str) -> JsonDict:
    defaults = PROVIDER_DEFAULTS[provider]
    main_branch = _safe_branch_name(os.getenv(defaults["main_branch_env"], defaults["default_main_branch"]), defaults["default_main_branch"])
    return {
        "provider": provider,
        "label": defaults["label"],
        "owner": _env_first(defaults["owner_env_names"], os.getenv("GITHUB_OWNER", "").strip()),
        "repo": _env_first(defaults["repo_env_names"], defaults["default_repo"]),
        "branch": main_branch,
        "ado_groups": _filter_pipeline_groups(provider, _parse_pipeline_groups(provider, defaults)),
    }


def _filter_pipeline_groups(provider: str, groups: List[JsonDict]) -> List[JsonDict]:
    """Keep AWS drift checks scoped to the core NPR/PRD pair only.

    EKS and Bolt deployments are intentionally excluded from AWS drift comparison.
    """
    if provider != "aws":
        return groups

    filtered: List[JsonDict] = []
    skip_re = re.compile(r"(^|[^a-z0-9])(eks|bolt)([^a-z0-9]|$)", re.IGNORECASE)
    for group in groups:
        text = " ".join(str(group.get(key) or "") for key in ("name", "label", "npr", "prd"))
        if skip_re.search(text):
            continue
        filtered.append(group)

    return filtered


def _azdo_config() -> JsonDict:
    org = _env_first(["AZDO_ORG", "AZURE_DEVOPS_ORG", "ADO_ORG"], "")
    project = _env_first(["AZDO_PROJECT", "AZURE_DEVOPS_PROJECT", "ADO_PROJECT"], "")
    pat = _env_first(["AZDO_PAT", "AZURE_DEVOPS_PAT", "ADO_PAT"], "")
    return {"org": org, "project": project, "pat": pat}


class GitHubClient:
    def __init__(self, token: str):
        self.token = token

    def request(self, path: str, query: Optional[JsonDict] = None, accept: Optional[str] = None) -> Any:
        url = f"https://api.github.com{path}"
        if query:
            clean = {k: v for k, v in query.items() if v not in (None, "")}
            if clean:
                url += "?" + urllib.parse.urlencode(clean)
        headers = {
            "Accept": accept or "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "terrabot-ado-deployed-commit-drift",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=GITHUB_TIMEOUT_SECONDS) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(detail)
                detail = parsed.get("message") or detail
            except Exception:
                pass
            raise RuntimeError(f"GitHub API request failed with HTTP {exc.code}: {detail}. URL path: {path}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"GitHub API network error for {path}: {exc.reason}") from exc

    def branch(self, owner: str, repo: str, branch: str) -> JsonDict:
        return self.request(
            f"/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}/branches/{urllib.parse.quote(branch, safe='')}"
        )

    def commit(self, owner: str, repo: str, sha: str) -> JsonDict:
        cache_key = f"{owner}/{repo}@{sha}"
        if cache_key in _COMMIT_CACHE:
            return _COMMIT_CACHE[cache_key]
        payload = self.request(
            f"/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}/commits/{urllib.parse.quote(sha, safe='')}"
        )
        _COMMIT_CACHE[cache_key] = payload
        return payload

    def associated_prs(self, owner: str, repo: str, sha: str) -> List[JsonDict]:
        data = self.request(
            f"/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}/commits/{urllib.parse.quote(sha, safe='')}/pulls",
            accept="application/vnd.github+json",
        )
        return data if isinstance(data, list) else []

    def pull_request(self, owner: str, repo: str, number: int) -> JsonDict:
        cache_key = f"{owner}/{repo}#{int(number)}"
        if cache_key in _PR_CACHE:
            return _PR_CACHE[cache_key]
        payload = self.request(
            f"/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}/pulls/{int(number)}",
            accept="application/vnd.github+json",
        )
        _PR_CACHE[cache_key] = payload
        return payload

    def issue_comments(self, owner: str, repo: str, number: int, per_page: int = 30) -> List[JsonDict]:
        data = self.request(
            f"/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}/issues/{int(number)}/comments",
            {"per_page": per_page},
            accept="application/vnd.github+json",
        )
        return data if isinstance(data, list) else []


class AzureDevOpsClient:
    def __init__(self, org: str, project: str, pat: str):
        self.org = org
        self.project = project
        self.pat = pat
        self.base = f"https://dev.azure.com/{urllib.parse.quote(org)}/{urllib.parse.quote(project)}"

    def request(self, path: str, query: Optional[JsonDict] = None) -> Any:
        url = f"{self.base}{path}"
        clean = {"api-version": AZDO_API_VERSION}
        if query:
            clean.update({k: v for k, v in query.items() if v not in (None, "")})
        url += "?" + urllib.parse.urlencode(clean)
        auth = base64.b64encode(f":{self.pat}".encode("utf-8")).decode("ascii")
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Basic {auth}",
                "User-Agent": "terrabot-ado-deployed-commit-drift",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=AZDO_TIMEOUT_SECONDS) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(detail)
                detail = parsed.get("message") or detail
            except Exception:
                pass
            raise RuntimeError(f"Azure DevOps API request failed with HTTP {exc.code}: {detail}. URL path: {path}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Azure DevOps API network error for {path}: {exc.reason}") from exc

    def definition_by_id(self, definition_id: int) -> List[JsonDict]:
        cache_key = f"id:{definition_id}"
        if cache_key in _DEF_CACHE:
            return _DEF_CACHE[cache_key]
        payload = self.request(f"/_apis/build/definitions/{int(definition_id)}")
        result = [payload] if isinstance(payload, dict) and payload.get("id") else []
        _DEF_CACHE[cache_key] = result
        return result

    def definitions_by_name(self, name: str) -> List[JsonDict]:
        cache_key = f"name:{name}"
        if cache_key in _DEF_CACHE:
            return _DEF_CACHE[cache_key]
        payload = self.request("/_apis/build/definitions", {"name": name, "includeAllProperties": "true", "$top": 50})
        values = payload.get("value") if isinstance(payload, dict) else []
        result = values if isinstance(values, list) else []
        _DEF_CACHE[cache_key] = result
        return result

    def definitions_by_yaml(self, yaml_filename: str) -> List[JsonDict]:
        cache_key = f"yaml:{yaml_filename}"
        if cache_key in _DEF_CACHE:
            return _DEF_CACHE[cache_key]
        payload = self.request(
            "/_apis/build/definitions",
            {"yamlFilename": yaml_filename, "includeAllProperties": "true", "$top": 100},
        )
        values = payload.get("value") if isinstance(payload, dict) else []
        result = values if isinstance(values, list) else []
        if not result:
            # Some Azure DevOps orgs do not support yamlFilename filtering reliably.
            # Fetch definitions and filter common YAML fields locally.
            all_payload = self.request("/_apis/build/definitions", {"includeAllProperties": "true", "$top": 500})
            all_values = all_payload.get("value") if isinstance(all_payload, dict) else []
            expected = yaml_filename.strip().lower().lstrip("/")
            result = []
            for item in all_values if isinstance(all_values, list) else []:
                candidates = [
                    str(item.get("yamlFilename") or ""),
                    str(((item.get("process") or {}).get("yamlFilename")) or ""),
                    str(((item.get("process") or {}).get("filename")) or ""),
                    str(item.get("path") or ""),
                ]
                normalized = [candidate.strip().lower().lstrip("/") for candidate in candidates]
                if expected in normalized or any(candidate.endswith("/" + expected) for candidate in normalized):
                    result.append(item)
        _DEF_CACHE[cache_key] = result
        return result

    def latest_successful_build(self, definition_id: int, source_branch: str) -> Optional[JsonDict]:
        def query_build(branch_value: str) -> Optional[JsonDict]:
            cache_key = f"build:{definition_id}:{branch_value or 'ANY'}"
            if cache_key in _BUILD_CACHE:
                return _BUILD_CACHE[cache_key]
            query = {
                "definitions": str(int(definition_id)),
                "statusFilter": "completed",
                "resultFilter": "succeeded",
                "queryOrder": "finishTimeDescending",
                "$top": 1,
            }
            if branch_value:
                query["branchName"] = branch_value
            payload = self.request("/_apis/build/builds", query)
            values = payload.get("value") if isinstance(payload, dict) else []
            build = values[0] if isinstance(values, list) and values else None
            _BUILD_CACHE[cache_key] = build
            return build

        build = query_build(source_branch)
        if build:
            build = dict(build)
            build["_terrabot_requested_branch"] = source_branch
            build["_terrabot_branch_filter_used"] = bool(source_branch)
            build["_terrabot_branch_fallback"] = False
            return build

        if source_branch and AZDO_FALLBACK_ANY_BRANCH:
            fallback = query_build("")
            if fallback:
                fallback = dict(fallback)
                fallback["_terrabot_requested_branch"] = source_branch
                fallback["_terrabot_branch_filter_used"] = False
                fallback["_terrabot_branch_fallback"] = True
                return fallback
        return None

def _parse_spec(raw: str) -> JsonDict:
    value = str(raw or "").strip()
    if not value:
        return {"kind": "none", "value": "", "raw": value}
    if ":" in value:
        kind, rest = value.split(":", 1)
        kind = kind.strip().lower()
        rest = rest.strip()
        if kind in {"id", "definition", "definition_id"}:
            return {"kind": "id", "value": rest, "raw": value}
        if kind in {"yaml", "file", "path", "yamlfilename"}:
            return {"kind": "yaml", "value": rest, "raw": value}
        if kind in {"name", "pipeline"}:
            return {"kind": "name", "value": rest, "raw": value}
    if value.isdigit():
        return {"kind": "id", "value": value, "raw": value}
    lower = value.lower()
    if lower.endswith(".yml") or lower.endswith(".yaml") or "/" in value:
        return {"kind": "yaml", "value": value, "raw": value}
    return {"kind": "name", "value": value, "raw": value}



def _pairs_from_simple_file_vars(provider: str) -> List[JsonDict]:
    """Build ADO pipeline groups from legacy *_PIPELINE_FILES variables.

    Older Terrabot env var sets used AWS_NPR_PIPELINE_FILES/AWS_PRD_PIPELINE_FILES
    and AZURE_NPR_PIPELINE_FILES/AZURE_PRD_PIPELINE_FILES.  In the ADO deployed
    commit model those values are Azure DevOps pipeline YAML filenames, not
    Terraform context paths.  This helper turns them into yaml:<file> specs so
    existing app settings keep working.
    """
    if provider == "aws":
        npr_files = _split_csv(_env_first(["AWS_NPR_PIPELINE_FILES", "AWS_DEV_PIPELINE_FILES"], ""))
        prd_files = _split_csv(_env_first(["AWS_PRD_PIPELINE_FILES", "AWS_PROD_PIPELINE_FILES"], ""))
        default_labels = ["core"]
    else:
        npr_files = _split_csv(_env_first(["AZURE_NPR_PIPELINE_FILES", "AZURE_DEV_PIPELINE_FILES"], ""))
        prd_files = _split_csv(_env_first(["AZURE_PRD_PIPELINE_FILES", "AZURE_PROD_PIPELINE_FILES"], ""))
        default_labels = ["hub"]

    if not npr_files and not prd_files:
        return []

    groups: List[JsonDict] = []
    max_len = max(len(npr_files), len(prd_files))
    if provider == "aws":
        max_len = min(max_len, 1)
    for idx in range(max_len):
        label = default_labels[idx] if idx < len(default_labels) else f"pipeline-{idx + 1}"
        npr = npr_files[idx] if idx < len(npr_files) else ""
        prd = prd_files[idx] if idx < len(prd_files) else ""
        groups.append({
            "name": label,
            "label": label,
            "npr": f"yaml:{npr}" if npr else "",
            "prd": f"yaml:{prd}" if prd else "",
        })
    return groups

def _parse_pipeline_groups(provider: str, defaults: JsonDict) -> List[JsonDict]:
    raw = _env_first(defaults["groups_env_names"], "")
    if raw:
        groups: List[JsonDict] = []
        for entry in _split_csv(raw):
            if not entry:
                continue
            label = "pipeline"
            body = entry
            if ":" in entry and "=>" in entry:
                maybe_label, maybe_body = entry.split(":", 1)
                if maybe_label.strip() and not maybe_label.strip().lower() in {"id", "yaml", "name"}:
                    label = maybe_label.strip()
                    body = maybe_body.strip()
            if "=>" in body:
                left, right = body.split("=>", 1)
            else:
                left, right = body, ""
            groups.append({"name": label, "label": label, "npr": left.strip(), "prd": right.strip()})
        if groups:
            return groups

    # Backward-compatible fallback for simple env vars.
    if provider == "aws":
        npr_ids = _split_csv(_env_first(["AWS_ADO_DEV_DEFINITION_IDS", "AWS_ADO_NPR_DEFINITION_IDS"], ""))
        prd_ids = _split_csv(_env_first(["AWS_ADO_PROD_DEFINITION_IDS", "AWS_ADO_PRD_DEFINITION_IDS"], ""))
        if npr_ids or prd_ids:
            groups = []
            for idx in range(min(max(len(npr_ids), len(prd_ids)), 1)):
                groups.append({
                    "name": f"aws-{idx + 1}",
                    "label": f"tf-devops pipeline pair {idx + 1}",
                    "npr": f"id:{npr_ids[idx]}" if idx < len(npr_ids) else "",
                    "prd": f"id:{prd_ids[idx]}" if idx < len(prd_ids) else "",
                })
            return groups
    if provider == "azure":
        npr_ids = _split_csv(_env_first(["AZURE_ADO_NPR_DEFINITION_IDS", "AZURE_ADO_DEV_DEFINITION_IDS"], ""))
        prd_ids = _split_csv(_env_first(["AZURE_ADO_PRD_DEFINITION_IDS", "AZURE_ADO_PROD_DEFINITION_IDS"], ""))
        if npr_ids or prd_ids:
            groups = []
            for idx in range(max(len(npr_ids), len(prd_ids))):
                groups.append({
                    "name": f"azure-{idx + 1}",
                    "label": f"tf-azure-hub pipeline pair {idx + 1}",
                    "npr": f"id:{npr_ids[idx]}" if idx < len(npr_ids) else "",
                    "prd": f"id:{prd_ids[idx]}" if idx < len(prd_ids) else "",
                })
            return groups
    simple_file_groups = _pairs_from_simple_file_vars(provider)
    if simple_file_groups:
        return simple_file_groups
    return list(defaults["default_groups"])


def _ado_source_branch(branch: str, provider: str = "") -> str:
    """Return the Azure DevOps build sourceBranch filter for deployment lookup.

    The drift check is comparing the latest commit on GitHub main with the
    latest successful deployment pipeline runs.  Do not accidentally use the
    app's generic AZDO_PIPELINE_BRANCH value here; many Terrabot deployments set
    AZDO_PIPELINE_BRANCH=terrabot-test for the Terrabot app pipeline itself,
    while the infrastructure deployment pipelines run from main.

    Use one of these when you intentionally want a non-main or unfiltered lookup:
      AWS_ADO_SOURCE_BRANCH / AZURE_ADO_SOURCE_BRANCH
      DRIFT_AZDO_SOURCE_BRANCH
      ADO_DEPLOYMENT_SOURCE_BRANCH

    Set the value to any/all/* to skip branch filtering.
    """
    provider_prefix = provider.upper() if provider else ""
    names = []
    if provider_prefix:
        names.extend([
            f"{provider_prefix}_ADO_SOURCE_BRANCH",
            f"{provider_prefix}_AZDO_SOURCE_BRANCH",
            f"{provider_prefix}_ADO_DEPLOYMENT_BRANCH",
            f"{provider_prefix}_AZDO_DEPLOYMENT_BRANCH",
        ])
    names.extend([
        "DRIFT_AZDO_SOURCE_BRANCH",
        "DRIFT_ADO_SOURCE_BRANCH",
        "ADO_DEPLOYMENT_SOURCE_BRANCH",
        "AZDO_DEPLOYMENT_SOURCE_BRANCH",
    ])

    # Backward compatibility: only honor the generic AZDO_PIPELINE_BRANCH if the
    # caller explicitly opts in.  This prevents AZDO_PIPELINE_BRANCH=terrabot-test
    # from making all deployment lookups miss the successful main-branch runs.
    use_global = os.getenv("DRIFT_USE_GLOBAL_AZDO_PIPELINE_BRANCH", "false").strip().lower() in {"1", "true", "yes", "on"}
    if use_global:
        names.extend(["AZDO_SOURCE_BRANCH", "ADO_SOURCE_BRANCH", "AZDO_PIPELINE_BRANCH", "ADO_PIPELINE_BRANCH"])

    value = _env_first(names, "")
    if not value:
        value = branch or "main"
    value = value.strip()
    if value.lower() in {"", "*", "any", "all", "none", "false", "off"}:
        return ""
    if value.startswith("refs/heads/"):
        return value
    return f"refs/heads/{value}"

def _resolve_definitions(client: AzureDevOpsClient, spec: JsonDict) -> List[JsonDict]:
    kind = spec.get("kind")
    value = str(spec.get("value") or "").strip()
    if not value or kind == "none":
        return []
    if kind == "id":
        if not value.isdigit():
            raise RuntimeError(f"Invalid Azure DevOps definition id: {value}")
        return client.definition_by_id(int(value))
    if kind == "yaml":
        return client.definitions_by_yaml(value)
    if kind == "name":
        return client.definitions_by_name(value)
    return []


def _web_url_from_build(build: JsonDict) -> str:
    links = build.get("_links") or {}
    web = links.get("web") or {}
    href = web.get("href") if isinstance(web, dict) else ""
    if href:
        return href
    return build.get("url") or ""


def _definition_display(definition: Optional[JsonDict], spec: JsonDict) -> JsonDict:
    definition = definition or {}
    return {
        "id": definition.get("id"),
        "name": definition.get("name") or spec.get("raw") or spec.get("value") or "",
        "path": definition.get("path") or "",
        "url": ((definition.get("_links") or {}).get("web") or {}).get("href") or definition.get("url") or "",
        "spec": spec,
    }


def _latest_deployment_for_spec(
    client: AzureDevOpsClient,
    *,
    spec_text: str,
    provider: str,
    environment: str,
    source_branch: str,
) -> JsonDict:
    checked_at = _utc_now()
    spec = _parse_spec(spec_text)
    if spec.get("kind") == "none":
        return {
            "environment": environment,
            "status": "not_configured",
            "required": False,
            "spec": spec,
            "checked_at": checked_at,
        }

    try:
        definitions = _resolve_definitions(client, spec)
        if not definitions:
            return {
                "environment": environment,
                "status": "error",
                "required": True,
                "spec": spec,
                "summary": f"No Azure DevOps pipeline definition matched {spec.get('raw') or spec.get('value')}",
                "error": f"No Azure DevOps pipeline definition matched {spec.get('raw') or spec.get('value')}",
                "checked_at": checked_at,
            }

        candidates: List[Tuple[JsonDict, JsonDict]] = []
        errors: List[str] = []
        for definition in definitions:
            definition_id = definition.get("id")
            if not definition_id:
                continue
            try:
                build = client.latest_successful_build(int(definition_id), source_branch)
                if build:
                    candidates.append((definition, build))
            except Exception as exc:
                errors.append(str(exc))

        if not candidates:
            return {
                "environment": environment,
                "status": "error",
                "required": True,
                "spec": spec,
                "definitions": [_definition_display(item, spec) for item in definitions],
                "summary": f"No successful Azure DevOps run found for {spec.get('raw') or spec.get('value')} on {source_branch or 'any branch'}. Confirm the pipeline definition ID/YAML file and branch filter. You can set AZDO_PIPELINE_BRANCH=main, AZDO_PIPELINE_BRANCH=terrabot-test, or AZDO_PIPELINE_BRANCH=any.",
                "error": f"No successful Azure DevOps run found for {spec.get('raw') or spec.get('value')} on {source_branch or 'any branch'}. Confirm the pipeline definition ID/YAML file and branch filter. You can set AZDO_PIPELINE_BRANCH=main, AZDO_PIPELINE_BRANCH=terrabot-test, or AZDO_PIPELINE_BRANCH=any.",
                "errors": errors,
                "checked_at": checked_at,
            }

        def finish_time(pair: Tuple[JsonDict, JsonDict]) -> float:
            build = pair[1]
            return _parse_date(build.get("finishTime") or build.get("queueTime") or build.get("startTime"))

        definition, build = sorted(candidates, key=finish_time, reverse=True)[0]
        sha = build.get("sourceVersion") or ""
        requested_for = build.get("requestedFor") or build.get("requestedBy") or {}
        queue = build.get("queue") or {}
        return {
            "environment": environment,
            "status": "succeeded",
            "required": True,
            "spec": spec,
            "definition": _definition_display(definition, spec),
            "definition_id": definition.get("id"),
            "definition_name": definition.get("name") or "",
            "pipeline_name": definition.get("name") or "",
            "pipeline_id": definition.get("id"),
            "build_id": build.get("id"),
            "run_id": build.get("id"),
            "build_number": build.get("buildNumber") or build.get("build_number") or "",
            "run_number": build.get("buildNumber") or "",
            "source_branch": build.get("sourceBranch") or source_branch,
            "requested_source_branch": build.get("_terrabot_requested_branch") or source_branch,
            "branch_filter_used": bool(build.get("_terrabot_branch_filter_used")),
            "branch_fallback": bool(build.get("_terrabot_branch_fallback")),
            "branch_warning": (f"No successful run was found on {build.get('_terrabot_requested_branch')}; using latest successful run from {build.get('sourceBranch')}." if build.get("_terrabot_branch_fallback") else ""),
            "source_version": sha,
            "sha": sha,
            "short_sha": _short_sha(sha),
            "result": build.get("result"),
            "build_status": build.get("status"),
            "queue_time": build.get("queueTime") or "",
            "start_time": build.get("startTime") or "",
            "finish_time": build.get("finishTime") or "",
            "timestamp": _parse_date(build.get("finishTime") or build.get("queueTime") or build.get("startTime")),
            "url": _web_url_from_build(build),
            "web_url": _web_url_from_build(build),
            "queue": queue.get("name") if isinstance(queue, dict) else "",
            "requested_for": requested_for.get("displayName") if isinstance(requested_for, dict) else "",
            "requested_for_unique_name": requested_for.get("uniqueName") if isinstance(requested_for, dict) else "",
            "checked_at": checked_at,
        }
    except Exception as exc:
        return {
            "environment": environment,
            "status": "error",
            "required": True,
            "spec": spec,
            "summary": str(exc),
            "error": str(exc),
            "checked_at": checked_at,
        }


def _normalize_commit_payload(owner: str, repo: str, payload: JsonDict, fallback_sha: str = "") -> JsonDict:
    commit = payload.get("commit") or {}
    author = commit.get("author") or {}
    committer = commit.get("committer") or {}
    author_user = payload.get("author") or {}
    committer_user = payload.get("committer") or {}
    sha = payload.get("sha") or fallback_sha or ""
    message = commit.get("message") or ""
    date = committer.get("date") or author.get("date") or ""
    return {
        "sha": sha,
        "short_sha": _short_sha(sha),
        "message": message,
        "title": message.splitlines()[0] if message else "",
        "date": date,
        "timestamp": _parse_date(date),
        "html_url": payload.get("html_url") or _github_url(owner, repo, sha),
        "author_login": author_user.get("login") if isinstance(author_user, dict) else "",
        "author_name": author.get("name") or "",
        "author_email": author.get("email") or "",
        "committer_login": committer_user.get("login") if isinstance(committer_user, dict) else "",
        "committer_name": committer.get("name") or "",
        "committer_email": committer.get("email") or "",
        "prs": [],
        "pull_requests": [],
        "jira_keys": [],
        "jira_tickets": [],
    }


def _branch_summary(client: GitHubClient, owner: str, repo: str, branch: str) -> JsonDict:
    payload = client.branch(owner, repo, branch)
    commit_ref = payload.get("commit") or {}
    sha = commit_ref.get("sha") or ""
    commit_payload = client.commit(owner, repo, sha) if sha else {}
    commit = _normalize_commit_payload(owner, repo, commit_payload, sha)
    return {
        "branch": branch,
        "sha": sha,
        "short_sha": _short_sha(sha),
        "commit_url": commit.get("html_url") or _github_url(owner, repo, sha),
        "message": commit.get("message") or "",
        "title": commit.get("title") or "",
        "date": commit.get("date") or "",
        "commit": commit,
    }


def _jira_ignored_project_keys() -> List[str]:
    raw = os.getenv("JIRA_IGNORED_PROJECT_KEYS", DEFAULT_IGNORED_JIRA_PROJECT_KEYS)
    keys: List[str] = []
    for item in _split_csv(raw.upper()):
        cleaned = re.sub(r"[^A-Z0-9]", "", item.strip().upper())
        if cleaned and cleaned not in keys:
            keys.append(cleaned)
    return keys


def _jira_key_parts(key: str) -> Tuple[str, str]:
    match = re.fullmatch(r"([A-Z][A-Z0-9]+)-(\d+)", str(key or "").upper().strip())
    if not match:
        return "", ""
    return match.group(1), match.group(2)


def _jira_allowed_project_keys() -> List[str]:
    raw = os.getenv("JIRA_PROJECT_KEYS") or os.getenv("JIRA_ALLOWED_PROJECT_KEYS") or ""
    keys: List[str] = []
    for item in _split_csv(raw.upper()):
        text = item.strip().upper()
        match = JIRA_KEY_RE.search(text)
        if match:
            prefix, _ = _jira_key_parts(match.group(0))
            cleaned = prefix
        else:
            cleaned = re.sub(r"[^A-Z0-9]", "", text)
        if cleaned and cleaned not in keys:
            keys.append(cleaned)
    return keys


def _jira_key_allowed(key: str) -> bool:
    prefix, issue_number = _jira_key_parts(key)
    if not prefix or not issue_number:
        return False
    allowed = _jira_allowed_project_keys()
    if allowed:
        return prefix in allowed
    if prefix in _jira_ignored_project_keys():
        return False
    if len(issue_number) < max(1, JIRA_MIN_ISSUE_NUMBER_DIGITS):
        return False
    return True


def _extract_jira_keys(*values: Any) -> List[str]:
    keys: List[str] = []
    for value in values:
        if value is None:
            continue
        for key in JIRA_KEY_RE.findall(str(value).upper()):
            if _jira_key_allowed(key) and key not in keys:
                keys.append(key)
    return keys


def _jira_base_url() -> str:
    base = os.getenv("JIRA_BASE_URL", "").strip().rstrip("/")
    if not base:
        return ""
    parsed = urllib.parse.urlsplit(base)
    if not parsed.scheme or not parsed.netloc:
        return base.rstrip("/")
    path = parsed.path or ""
    lowered = path.lower()
    for marker in ("/browse/", "/browse", "/rest/api/3", "/rest/api/2", "/jira/"):
        idx = lowered.find(marker)
        if idx >= 0:
            path = path[:idx]
            break
    if path.lower() == "/jira":
        path = ""
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path.rstrip("/"), "", "")).rstrip("/")


def _jira_issue_url(key: str) -> str:
    base = _jira_base_url()
    return f"{base}/browse/{urllib.parse.quote(key, safe='')}" if base and key else ""


def _jira_configured() -> bool:
    return bool(_jira_base_url() and os.getenv("JIRA_EMAIL") and os.getenv("JIRA_API_TOKEN"))


def _parse_jira_error(exc: urllib.error.HTTPError) -> str:
    try:
        detail = exc.read().decode("utf-8", errors="replace")
        parsed = json.loads(detail) if detail else {}
        if isinstance(parsed, dict):
            messages = parsed.get("errorMessages") or []
            if messages:
                return "; ".join(str(item) for item in messages)
            errors = parsed.get("errors") or {}
            if errors:
                return "; ".join(f"{k}: {v}" for k, v in errors.items())
            if parsed.get("message"):
                return str(parsed.get("message"))
        return detail or f"HTTP Error {exc.code}: {exc.reason}"
    except Exception:
        return f"HTTP Error {exc.code}: {exc.reason}"


def _fetch_jira_issue(key: str) -> JsonDict:
    key = str(key or "").upper().strip()
    if key in _JIRA_CACHE:
        return _JIRA_CACHE[key]
    if not key or not _jira_key_allowed(key):
        ticket = {"key": key, "status": "Ignored", "available": False, "ignored": True, "display": False, "url": _jira_issue_url(key)}
        _JIRA_CACHE[key] = ticket
        return ticket
    if not _jira_configured():
        ticket = {
            "key": key,
            "status": "Jira not configured",
            "summary": "Set JIRA_BASE_URL, JIRA_EMAIL, and JIRA_API_TOKEN to read Jira status.",
            "url": _jira_issue_url(key),
            "available": False,
            "display": True,
        }
        _JIRA_CACHE[key] = ticket
        return ticket
    base = _jira_base_url()
    email = os.getenv("JIRA_EMAIL", "")
    token = os.getenv("JIRA_API_TOKEN", "")
    auth = base64.b64encode(f"{email}:{token}".encode("utf-8")).decode("ascii")
    fields = "status,summary,assignee,priority,issuetype"
    last_error = ""
    last_code = None
    for version in [os.getenv("JIRA_API_VERSION", "3").strip() or "3", "3", "2"]:
        url = f"{base}/rest/api/{version}/issue/{urllib.parse.quote(key, safe='')}?{urllib.parse.urlencode({'fields': fields})}"
        req = urllib.request.Request(url, headers={"Accept": "application/json", "Authorization": f"Basic {auth}", "User-Agent": "terrabot-ado-deployed-commit-drift"})
        try:
            with urllib.request.urlopen(req, timeout=JIRA_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
            fields_payload = payload.get("fields") or {}
            status = fields_payload.get("status") or {}
            assignee = fields_payload.get("assignee") or {}
            priority = fields_payload.get("priority") or {}
            issue_type = fields_payload.get("issuetype") or {}
            ticket = {
                "key": key,
                "status": status.get("name") or "Unknown",
                "status_category": (status.get("statusCategory") or {}).get("name") or "",
                "summary": fields_payload.get("summary") or "",
                "assignee": assignee.get("displayName") or "Unassigned",
                "priority": priority.get("name") or "",
                "issue_type": issue_type.get("name") or "",
                "url": _jira_issue_url(key),
                "available": True,
                "display": True,
                "api_version": version,
            }
            _JIRA_CACHE[key] = ticket
            return ticket
        except urllib.error.HTTPError as exc:
            last_code = exc.code
            last_error = _parse_jira_error(exc)
            if exc.code == 404:
                break
        except Exception as exc:
            last_error = str(exc)
            break
    ticket = {
        "key": key,
        "status": "Jira issue not found" if last_code == 404 else "Jira lookup failed",
        "summary": last_error or "Jira lookup failed.",
        "url": _jira_issue_url(key),
        "available": False,
        "display": last_code != 404,
        "not_found": last_code == 404,
        "http_status": last_code,
    }
    _JIRA_CACHE[key] = ticket
    return ticket


def _should_display_jira_ticket(ticket: JsonDict) -> bool:
    if SHOW_INVALID_JIRA_KEYS:
        return True
    if ticket.get("ignored") or ticket.get("not_found"):
        return False
    if ticket.get("display"):
        return True
    if ticket.get("available") is False and ticket.get("status") == "Jira lookup failed":
        return False
    return True


def _normalize_pr(pr: JsonDict) -> JsonDict:
    user = pr.get("user") or {}
    head = pr.get("head") or {}
    base = pr.get("base") or {}
    labels = []
    for label in pr.get("labels") or []:
        if isinstance(label, dict) and label.get("name"):
            labels.append(str(label.get("name")))
        elif isinstance(label, str):
            labels.append(label)
    return {
        "number": pr.get("number"),
        "title": pr.get("title") or "",
        "url": pr.get("html_url") or pr.get("url") or "",
        "state": "merged" if pr.get("merged_at") else (pr.get("state") or ""),
        "merged_at": pr.get("merged_at") or "",
        "created_at": pr.get("created_at") or "",
        "updated_at": pr.get("updated_at") or "",
        "user": user.get("login") if isinstance(user, dict) else "",
        "author": user.get("login") if isinstance(user, dict) else "",
        "head_ref": head.get("ref") if isinstance(head, dict) else "",
        "base_ref": base.get("ref") if isinstance(base, dict) else "",
        "body": pr.get("body") or "",
        "comments_text": pr.get("comments_text") or "",
        "labels": labels,
        "jira_keys": [],
        "jira_tickets": [],
    }


def _merge_pr_detail(summary: JsonDict, detail: JsonDict) -> JsonDict:
    merged = dict(summary or {})
    for key in ("title", "html_url", "state", "merged_at", "created_at", "updated_at", "body", "user", "head", "base", "labels", "comments_text"):
        if isinstance(detail, dict) and detail.get(key) is not None:
            merged[key] = detail.get(key)
    return merged


def _enrich_pr_with_jira(pr: JsonDict) -> JsonDict:
    text_values = [pr.get("title"), pr.get("body"), pr.get("comments_text"), " ".join(pr.get("labels") or [])]
    ref_values = [pr.get("head_ref"), pr.get("base_ref")]
    keys = _extract_jira_keys(*text_values)
    if JIRA_EXTRACT_FROM_BRANCH_REFS:
        for key in _extract_jira_keys(*ref_values):
            if key not in keys:
                keys.append(key)
    tickets: List[JsonDict] = []
    for key in keys:
        ticket = dict(_fetch_jira_issue(key))
        ticket.setdefault("key", key)
        ticket["source"] = "pull_request"
        if not ticket.get("ignored") and not ticket.get("not_found"):
            ticket["display"] = True
        tickets.append(ticket)
    pr["jira_keys"] = [ticket.get("key") for ticket in tickets if ticket.get("key") and _should_display_jira_ticket(ticket)]
    pr["jira_tickets"] = [ticket for ticket in tickets if _should_display_jira_ticket(ticket)]
    pr["jira_lookup_results"] = tickets
    return pr


def _add_unique_keys(keys: List[str], candidates: Iterable[str]) -> None:
    for key in candidates:
        if key and key not in keys:
            keys.append(key)


def _enrich_commit(client: GitHubClient, owner: str, repo: str, sha: str) -> JsonDict:
    if not sha:
        return {}
    try:
        payload = client.commit(owner, repo, sha)
        commit = _normalize_commit_payload(owner, repo, payload, sha)
    except Exception as exc:
        return {
            "sha": sha,
            "short_sha": _short_sha(sha),
            "html_url": _github_url(owner, repo, sha),
            "title": f"Unable to read GitHub commit metadata: {exc}",
            "message": f"Unable to read GitHub commit metadata: {exc}",
            "metadata_error": str(exc),
            "prs": [],
            "pull_requests": [],
            "jira_keys": [],
            "jira_tickets": [],
        }

    prs: List[JsonDict] = []
    try:
        for item in client.associated_prs(owner, repo, sha)[:5]:
            raw = item
            number = item.get("number")
            if number:
                try:
                    raw = _merge_pr_detail(item, client.pull_request(owner, repo, int(number)))
                except Exception as detail_exc:
                    raw = dict(item)
                    raw["detail_error"] = str(detail_exc)
                if JIRA_EXTRACT_FROM_PR_COMMENTS:
                    try:
                        comments = client.issue_comments(owner, repo, int(number), per_page=30)
                        raw["comments_text"] = "\n".join(str(comment.get("body") or "") for comment in comments[:30])
                    except Exception as comments_exc:
                        raw["comments_error"] = str(comments_exc)
            prs.append(_enrich_pr_with_jira(_normalize_pr(raw)))
    except Exception as exc:
        commit["pull_request_error"] = str(exc)

    pr_keys: List[str] = []
    for pr in prs:
        _add_unique_keys(pr_keys, pr.get("jira_keys") or [])
    commit_keys = _extract_jira_keys(commit.get("title"), commit.get("message"))
    keys: List[str] = []
    _add_unique_keys(keys, pr_keys)
    _add_unique_keys(keys, commit_keys)

    pr_ticket_map: Dict[str, JsonDict] = {}
    for pr in prs:
        for ticket in pr.get("jira_tickets") or []:
            key = ticket.get("key")
            if key and key not in pr_ticket_map:
                pr_ticket_map[key] = ticket
    lookup_results = [pr_ticket_map.get(key) or _fetch_jira_issue(key) for key in keys]
    visible_tickets = [ticket for ticket in lookup_results if _should_display_jira_ticket(ticket)]

    commit["prs"] = prs
    commit["pull_requests"] = prs
    commit["jira_candidate_keys"] = keys
    commit["jira_lookup_results"] = lookup_results
    commit["jira_lookup_failures"] = [ticket for ticket in lookup_results if not ticket.get("available")]
    commit["jira_keys"] = [ticket.get("key") for ticket in visible_tickets if ticket.get("key")]
    commit["jira_tickets"] = visible_tickets
    return commit


def _commit_for_ui(commit: Optional[JsonDict]) -> JsonDict:
    if not commit:
        return {}
    return {
        "sha": commit.get("sha"),
        "short_sha": commit.get("short_sha") or _short_sha(commit.get("sha")),
        "message": commit.get("message"),
        "title": commit.get("title"),
        "date": commit.get("date"),
        "html_url": commit.get("html_url"),
        "author_login": commit.get("author_login"),
        "author_name": commit.get("author_name"),
        "author_email": commit.get("author_email"),
        "committer_login": commit.get("committer_login"),
        "prs": commit.get("prs") or commit.get("pull_requests") or [],
        "pull_requests": commit.get("pull_requests") or commit.get("prs") or [],
        "jira_keys": commit.get("jira_keys") or [],
        "jira_tickets": commit.get("jira_tickets") or [],
        "jira_lookup_failures": commit.get("jira_lookup_failures") or [],
        "jira_lookup_results": commit.get("jira_lookup_results") or [],
        "jira_candidate_keys": commit.get("jira_candidate_keys") or [],
    }



def _clean_user_identity_value(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    raw = re.sub(r"^GitHub App[\\/]", "", raw, flags=re.IGNORECASE).strip()
    lower = raw.lower()
    if not raw or lower == "unknown":
        return ""
    if "github app" in lower:
        return ""
    if "microsoft.visualstudio.services.tfs" in lower:
        return ""
    if "ad157672-dafb-4cc1-82a8-0c9d5ddb0c63" in lower:
        return ""
    if re.fullmatch(r"00000002-0000-8888-8000-000000000000@[0-9a-f-]{36}", lower):
        return ""
    if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", lower):
        return ""
    if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}@[0-9a-f-]{36}", lower):
        return ""
    match = re.fullmatch(r"\d+\+([^@]+)@users\.noreply\.github\.com", raw, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.fullmatch(r"([^@]+)@users\.noreply\.github\.com", raw, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return raw


def _clean_user_object(*values: Any) -> Optional[JsonDict]:
    for value in values:
        if isinstance(value, dict):
            candidates = [
                value.get("email"),
                value.get("login"),
                value.get("user"),
                value.get("username"),
                value.get("name"),
                value.get("displayName"),
            ]
        else:
            candidates = [value]
        for candidate in candidates:
            clean = _clean_user_identity_value(candidate)
            if clean:
                email = clean if "@" in clean and not clean.lower().endswith("@users.noreply.github.com") else ""
                return {"login": clean, "name": clean, "email": email}
    return None

def _users_from_commits(commits: Iterable[JsonDict], deployments: Iterable[JsonDict] = ()) -> List[JsonDict]:
    users: List[JsonDict] = []
    seen = set()

    def add_user(*values: Any) -> None:
        user = _clean_user_object(*values)
        if not user:
            return
        key = user.get("email") or user.get("login") or user.get("name")
        if key and key not in seen:
            users.append(user)
            seen.add(key)

    for deployment in deployments:
        add_user(deployment.get("requested_for_unique_name"), deployment.get("requested_for"))

    for commit in commits:
        add_user(
            commit.get("author_email"),
            commit.get("author_login"),
            commit.get("author_name"),
            commit.get("committer_email"),
            commit.get("committer_login"),
            commit.get("committer_name"),
        )
        for pr in commit.get("prs") or commit.get("pull_requests") or []:
            add_user(pr.get("user"), pr.get("author"))
    return users


def _tickets_from_commits(commits: Iterable[JsonDict]) -> List[JsonDict]:
    tickets: List[JsonDict] = []
    seen = set()
    for commit in commits:
        for ticket in commit.get("jira_tickets") or []:
            key = ticket.get("key")
            if key and key not in seen and _should_display_jira_ticket(ticket):
                tickets.append(ticket)
                seen.add(key)
        for pr in commit.get("prs") or commit.get("pull_requests") or []:
            for ticket in pr.get("jira_tickets") or []:
                key = ticket.get("key")
                if key and key not in seen and _should_display_jira_ticket(ticket):
                    tickets.append(ticket)
                    seen.add(key)
    return tickets


def _prs_from_commits(commits: Iterable[JsonDict]) -> List[JsonDict]:
    prs: List[JsonDict] = []
    seen = set()
    for commit in commits:
        for pr in commit.get("prs") or commit.get("pull_requests") or []:
            key = pr.get("url") or pr.get("number")
            if key and key not in seen:
                prs.append(pr)
                seen.add(key)
    return prs


def _deployment_label(deployment: Optional[JsonDict]) -> str:
    if not deployment or deployment.get("status") == "not_configured":
        return "not configured"
    if deployment.get("status") == "error":
        return deployment.get("error") or deployment.get("summary") or "error"
    name = deployment.get("pipeline_name") or deployment.get("definition_name") or "pipeline"
    build = deployment.get("build_number") or deployment.get("run_number") or deployment.get("build_id") or "latest successful run"
    return f"{name} #{build}"


def _deployment_sha(deployment: Optional[JsonDict]) -> str:
    if not deployment or deployment.get("status") in {"not_configured", "error"}:
        return ""
    return deployment.get("sha") or deployment.get("source_version") or ""


def _deployment_for_ui(deployment: Optional[JsonDict]) -> JsonDict:
    if not deployment:
        return {}
    return {
        "environment": deployment.get("environment"),
        "status": deployment.get("status"),
        "sha": _deployment_sha(deployment),
        "short_sha": _short_sha(_deployment_sha(deployment)),
        "pipeline_name": deployment.get("pipeline_name"),
        "pipeline_id": deployment.get("pipeline_id"),
        "definition_name": deployment.get("definition_name"),
        "definition_id": deployment.get("definition_id"),
        "build_id": deployment.get("build_id"),
        "run_id": deployment.get("run_id"),
        "build_number": deployment.get("build_number"),
        "run_number": deployment.get("run_number"),
        "source_branch": deployment.get("source_branch"),
        "requested_source_branch": deployment.get("requested_source_branch"),
        "branch_filter_used": deployment.get("branch_filter_used"),
        "branch_fallback": deployment.get("branch_fallback"),
        "branch_warning": deployment.get("branch_warning"),
        "url": deployment.get("url") or deployment.get("web_url"),
        "finish_time": deployment.get("finish_time"),
        "requested_for": deployment.get("requested_for"),
        "requested_for_unique_name": deployment.get("requested_for_unique_name"),
        "error": deployment.get("error"),
        "summary": deployment.get("summary"),
        "spec": deployment.get("spec"),
    }


def _row_remediation(
    *,
    provider_label: str,
    repo: str,
    row_type: str,
    group_label: str,
    main_sha: str,
    npr_deployment: Optional[JsonDict],
    prd_deployment: Optional[JsonDict],
    responsible_commits: List[JsonDict],
) -> str:
    main_short = _short_sha(main_sha)
    npr_short = _short_sha(_deployment_sha(npr_deployment))
    prd_short = _short_sha(_deployment_sha(prd_deployment))
    commit = responsible_commits[0] if responsible_commits else {}
    sha = _short_sha(commit.get("sha")) or main_short
    prs = _prs_from_commits(responsible_commits)
    pr_text = f" PR #{prs[0].get('number')}" if prs else ""
    tickets = _tickets_from_commits(responsible_commits)
    jira_text = f" Jira {tickets[0].get('key')} is {tickets[0].get('status')}." if tickets else ""
    if row_type == "npr_main":
        return (
            f"Deploy {repo} main commit {main_short} to the NPR/dev pipeline for {group_label}. "
            f"Review commit {sha}{pr_text}, then rerun the matching successful NPR/dev pipeline. "
            f"Current NPR/dev deployed commit is {npr_short or 'unknown'}.{jira_text}"
        )
    if row_type == "prd_main":
        return (
            f"Deploy {repo} main commit {main_short} to the PRD/prod pipeline for {group_label}. "
            f"Review commit {sha}{pr_text}, then promote through the normal PRD approval/deployment flow. "
            f"Current PRD/prod deployed commit is {prd_short or 'unknown'}.{jira_text}"
        )
    if row_type == "npr_prd":
        return (
            f"Align NPR/dev and PRD/prod deployments for {group_label}. "
            f"NPR/dev is at {npr_short or 'unknown'} and PRD/prod is at {prd_short or 'unknown'}. "
            f"Promote the approved commit so both environments point to the same intended SHA.{jira_text}"
        )
    return f"Review {provider_label} deployed commit drift for {group_label}.{jira_text}"


def _make_comparison_row(
    *,
    provider: str,
    provider_label: str,
    owner: str,
    repo: str,
    branch: str,
    group_name: str,
    group_label: str,
    comparison_type: str,
    main: JsonDict,
    npr_deployment: Optional[JsonDict],
    prd_deployment: Optional[JsonDict],
    main_commit: JsonDict,
    npr_commit: JsonDict,
    prd_commit: JsonDict,
    checked_at: str,
) -> JsonDict:
    main_sha = main.get("sha") or ""
    npr_sha = _deployment_sha(npr_deployment)
    prd_sha = _deployment_sha(prd_deployment)
    status = "clean"
    severity = "info"
    summary = ""
    responsible_commits: List[JsonDict] = []
    deployments: List[JsonDict] = []
    head_sha = ""
    head_commit_url = ""
    compare_url = ""
    log_url = ""

    if comparison_type == "npr_main":
        deployments = [npr_deployment] if npr_deployment else []
        head_sha = npr_sha
        log_url = (npr_deployment or {}).get("url") or ""
        if not npr_deployment or npr_deployment.get("status") == "error":
            status = "error"
            severity = "critical"
            summary = f"Could not read latest successful NPR/dev ADO pipeline run for {group_label}: {(npr_deployment or {}).get('error') or 'not configured'}"
        elif not npr_sha:
            status = "error"
            severity = "critical"
            summary = f"Latest successful NPR/dev ADO pipeline run for {group_label} did not include sourceVersion."
        elif npr_sha == main_sha:
            status = "clean"
            summary = f"NPR/dev deployed commit matches main at {_short_sha(main_sha)} for {group_label}."
            responsible_commits = [npr_commit or main_commit]
        else:
            status = "drift"
            severity = "high"
            summary = f"NPR/dev is behind or different from main for {group_label}. Main={_short_sha(main_sha)}; NPR/dev deployed={_short_sha(npr_sha)} via {_deployment_label(npr_deployment)}."
            responsible_commits = [main_commit or npr_commit]
            compare_url = _github_compare_url(owner, repo, npr_sha, main_sha)
        head_commit_url = _github_url(owner, repo, npr_sha) if npr_sha else ""
    elif comparison_type == "prd_main":
        deployments = [prd_deployment] if prd_deployment else []
        head_sha = prd_sha
        log_url = (prd_deployment or {}).get("url") or ""
        if not prd_deployment or prd_deployment.get("status") == "error":
            status = "error"
            severity = "critical"
            summary = f"Could not read latest successful PRD/prod ADO pipeline run for {group_label}: {(prd_deployment or {}).get('error') or 'not configured'}"
        elif not prd_sha:
            status = "error"
            severity = "critical"
            summary = f"Latest successful PRD/prod ADO pipeline run for {group_label} did not include sourceVersion."
        elif prd_sha == main_sha:
            status = "clean"
            summary = f"PRD/prod deployed commit matches main at {_short_sha(main_sha)} for {group_label}."
            responsible_commits = [prd_commit or main_commit]
        else:
            status = "drift"
            severity = "critical"
            summary = f"PRD/prod is behind or different from main for {group_label}. Main={_short_sha(main_sha)}; PRD/prod deployed={_short_sha(prd_sha)} via {_deployment_label(prd_deployment)}."
            responsible_commits = [main_commit or prd_commit]
            compare_url = _github_compare_url(owner, repo, prd_sha, main_sha)
        head_commit_url = _github_url(owner, repo, prd_sha) if prd_sha else ""
    elif comparison_type == "npr_prd":
        deployments = [item for item in [npr_deployment, prd_deployment] if item]
        if not npr_deployment or npr_deployment.get("status") in {"not_configured", "error"}:
            status = "waiting" if npr_deployment and npr_deployment.get("status") == "not_configured" else "error"
            severity = "info" if status == "waiting" else "critical"
            summary = f"NPR/dev pipeline is not available for {group_label}; NPR vs PRD comparison is skipped."
        elif not prd_deployment or prd_deployment.get("status") in {"not_configured", "error"}:
            status = "waiting" if prd_deployment and prd_deployment.get("status") == "not_configured" else "error"
            severity = "info" if status == "waiting" else "critical"
            summary = f"PRD/prod pipeline is not available for {group_label}; NPR vs PRD comparison is skipped."
        elif not npr_sha or not prd_sha:
            status = "error"
            severity = "critical"
            summary = f"Cannot compare NPR/dev and PRD/prod for {group_label} because one deployed SHA is missing."
        elif npr_sha == prd_sha == main_sha:
            status = "clean"
            summary = f"NPR/dev, PRD/prod, and main all match at {_short_sha(main_sha)} for {group_label}."
            responsible_commits = [main_commit or npr_commit or prd_commit]
            head_sha = main_sha
            head_commit_url = _github_url(owner, repo, main_sha)
        else:
            status = "drift"
            severity = "critical"
            candidates = [
                ("main", main_commit, main_sha, _parse_date((main_commit or {}).get("date"))),
                ("NPR/dev", npr_commit, npr_sha, (npr_deployment or {}).get("timestamp") or 0),
                ("PRD/prod", prd_commit, prd_sha, (prd_deployment or {}).get("timestamp") or 0),
            ]
            label, commit, sha, _ = sorted([item for item in candidates if item[2]], key=lambda item: item[3] or 0, reverse=True)[0]
            responsible_commits = [commit or main_commit]
            head_sha = sha
            head_commit_url = _github_url(owner, repo, head_sha)
            compare_url = _github_compare_url(owner, repo, prd_sha or npr_sha, main_sha) or _github_compare_url(owner, repo, prd_sha, npr_sha)
            summary = f"NPR/dev, PRD/prod, and main are not aligned for {group_label}. NPR/dev={_short_sha(npr_sha) or 'unknown'}; PRD/prod={_short_sha(prd_sha) or 'unknown'}; main={_short_sha(main_sha) or 'unknown'}. Latest observed source: {label}."
    else:
        status = "error"
        severity = "critical"
        summary = f"Unsupported comparison type {comparison_type}."

    if status == "clean" and responsible_commits:
        responsible_commits = [commit for commit in responsible_commits if commit]
    if status in {"drift", "error"} and not responsible_commits and main_commit:
        responsible_commits = [main_commit]

    ui_commits = [_commit_for_ui(commit) for commit in responsible_commits if commit]
    tickets = _tickets_from_commits(responsible_commits)
    prs = _prs_from_commits(responsible_commits)
    users = _users_from_commits(responsible_commits, deployments)
    remediation = ""
    if status == "drift":
        remediation = _row_remediation(
            provider_label=provider_label,
            repo=repo,
            row_type=comparison_type,
            group_label=group_label,
            main_sha=main_sha,
            npr_deployment=npr_deployment,
            prd_deployment=prd_deployment,
            responsible_commits=responsible_commits,
        )
    elif status == "error":
        remediation = "Verify AZDO_ORG, AZDO_PROJECT, AZDO_PAT, pipeline definition IDs/YAML names, and Build read permission. Then refresh this provider again."

    return {
        "provider": provider,
        "providerLabel": provider_label,
        "repo": repo,
        "branch": branch,
        "source_branch": branch,
        "baseline_branch": branch,
        "name": {
            "npr_main": f"{provider_label} {group_label} NPR/dev deployed commit vs main",
            "prd_main": f"{provider_label} {group_label} PRD/prod deployed commit vs main",
            "npr_prd": f"{provider_label} {group_label} NPR/dev vs PRD/prod vs main",
        }.get(comparison_type, f"{provider_label} {group_label} deployed commit check"),
        "stage": "Azure DevOps deployed commit comparison",
        "source": "ado_deployed_commit",
        "driftType": "ado_deployed_commit",
        "comparison_type": comparison_type,
        "group": group_name,
        "group_label": group_label,
        "status": status,
        "severity": severity,
        "summary": summary,
        "commit_summary": summary,
        "lastChecked": checked_at,
        "checked_at": checked_at,
        "mainSha": main_sha,
        "main_sha": main_sha,
        "headSha": head_sha,
        "head_sha": head_sha,
        "nprSha": npr_sha,
        "npr_sha": npr_sha,
        "prdSha": prd_sha,
        "prd_sha": prd_sha,
        "nprCommitUrl": _github_url(owner, repo, npr_sha) if npr_sha else "",
        "npr_commit_url": _github_url(owner, repo, npr_sha) if npr_sha else "",
        "prdCommitUrl": _github_url(owner, repo, prd_sha) if prd_sha else "",
        "prd_commit_url": _github_url(owner, repo, prd_sha) if prd_sha else "",
        "mainCommitUrl": main.get("commit_url") or _github_url(owner, repo, main_sha),
        "main_commit_url": main.get("commit_url") or _github_url(owner, repo, main_sha),
        "nprPipelineUrl": (npr_deployment or {}).get("url") or (npr_deployment or {}).get("web_url") or "",
        "npr_pipeline_url": (npr_deployment or {}).get("url") or (npr_deployment or {}).get("web_url") or "",
        "prdPipelineUrl": (prd_deployment or {}).get("url") or (prd_deployment or {}).get("web_url") or "",
        "prd_pipeline_url": (prd_deployment or {}).get("url") or (prd_deployment or {}).get("web_url") or "",
        "nprFile": _deployment_label(npr_deployment) if npr_deployment else "",
        "prdFile": _deployment_label(prd_deployment) if prd_deployment else "",
        "npr_file": _deployment_label(npr_deployment) if npr_deployment else "",
        "prd_file": _deployment_label(prd_deployment) if prd_deployment else "",
        "context": "ADO latest successful run sourceVersion",
        "compareUrl": compare_url,
        "compare_url": compare_url,
        "headCommitUrl": head_commit_url or _github_url(owner, repo, head_sha or main_sha),
        "head_commit_url": head_commit_url or _github_url(owner, repo, head_sha or main_sha),
        "logUrl": log_url,
        "log_url": log_url,
        "adoRunUrl": log_url,
        "ado_run_url": log_url,
        "responsibleCommits": ui_commits,
        "responsible_commits": ui_commits,
        "responsibleUsers": users,
        "responsible_users": users,
        "pullRequests": prs,
        "pull_requests": prs,
        "jiraTickets": tickets,
        "jira_tickets": tickets,
        "jiraLookupFailures": [ticket for commit in responsible_commits for ticket in (commit.get("jira_lookup_failures") or [])],
        "jira_lookup_failures": [ticket for commit in responsible_commits for ticket in (commit.get("jira_lookup_failures") or [])],
        "remediation": remediation,
        "fix_instructions": remediation,
        "npr_deployment": _deployment_for_ui(npr_deployment),
        "prd_deployment": _deployment_for_ui(prd_deployment),
        "main": main,
    }


def _provider_status(rows: List[JsonDict]) -> str:
    statuses = [row.get("status") for row in rows]
    if any(status == "error" for status in statuses):
        return "error"
    if any(status == "drift" for status in statuses):
        return "drift"
    if rows and all(status in {"clean", "waiting"} for status in statuses) and any(status == "clean" for status in statuses):
        return "clean"
    return "waiting"


def _provider_alerts(provider_state: JsonDict) -> List[JsonDict]:
    alerts: List[JsonDict] = []
    for row in provider_state.get("environments") or []:
        if row.get("status") not in {"drift", "error"}:
            continue
        severity = row.get("severity") or ("critical" if row.get("status") == "error" else "high")
        alerts.append({
            "id": f"{provider_state.get('provider')}-{row.get('group')}-{row.get('comparison_type')}-{row.get('status')}",
            "provider": provider_state.get("label"),
            "environment": row.get("name"),
            "severity": severity,
            "title": "Deployed commit drift requires review" if row.get("status") == "drift" else "Deployed commit drift check failed",
            "message": row.get("summary") or "Review this deployed commit drift check.",
        })
    return alerts


def _waiting_provider(provider: str) -> JsonDict:
    cfg = _provider_config(provider)
    return {
        "provider": provider,
        "label": cfg["label"],
        "repo": cfg["repo"],
        "branch": cfg["branch"],
        "mode": "ado_deployed_commit_comparison",
        "status": "waiting",
        "generatedAt": None,
        "summary": {"status": "waiting", "message": "Waiting for backend refresh."},
        "environments": [],
        "ado_groups": cfg.get("ado_groups", []),
    }


def _error_provider(provider: str, message: str, cfg: Optional[JsonDict] = None) -> JsonDict:
    cfg = cfg or _provider_config(provider)
    checked_at = _utc_now()
    row = {
        "provider": provider,
        "providerLabel": cfg.get("label", provider.upper()),
        "repo": cfg.get("repo", ""),
        "branch": cfg.get("branch", "main"),
        "name": f"{cfg.get('label', provider.upper())} deployed commit drift configuration",
        "stage": "Backend configuration",
        "source": "ado_deployed_commit",
        "status": "error",
        "severity": "critical",
        "summary": message,
        "commit_summary": message,
        "lastChecked": checked_at,
        "checked_at": checked_at,
        "responsibleCommits": [],
        "responsibleUsers": [],
        "jiraTickets": [],
        "remediation": "Set the required Function App environment variables, restart the Function App, and refresh this provider again.",
        "fix_instructions": "Set the required Function App environment variables, restart the Function App, and refresh this provider again.",
    }
    state = {
        "provider": provider,
        "label": cfg.get("label", provider.upper()),
        "repo": cfg.get("repo", ""),
        "branch": cfg.get("branch", "main"),
        "mode": "ado_deployed_commit_comparison",
        "status": "error",
        "generatedAt": checked_at,
        "summary": {"status": "error", "message": message},
        "environments": [row],
        "ado_groups": cfg.get("ado_groups", []),
    }
    state["alerts"] = _provider_alerts(state)
    return state


def _refresh_provider(provider: str) -> JsonDict:
    if provider not in PROVIDER_DEFAULTS:
        return _error_provider(provider, f"Unsupported provider: {provider}")

    cfg = _provider_config(provider)
    azdo = _azdo_config()
    token = os.getenv("GITHUB_TOKEN", "").strip()
    missing: List[str] = []
    if not token:
        missing.append("GITHUB_TOKEN")
    if not cfg.get("owner"):
        missing.append("GITHUB_OWNER")
    if not cfg.get("repo"):
        missing.append("GITHUB_AWS_REPO/GITHUB_AZURE_REPO")
    for key, env_name in (("org", "AZDO_ORG"), ("project", "AZDO_PROJECT"), ("pat", "AZDO_PAT")):
        if not azdo.get(key):
            missing.append(env_name)
    if missing:
        return _error_provider(provider, f"Missing required Function App environment variable(s): {', '.join(missing)}.", cfg)

    checked_at = _utc_now()
    try:
        gh = GitHubClient(token)
        ado = AzureDevOpsClient(azdo["org"], azdo["project"], azdo["pat"])
        main = _branch_summary(gh, cfg["owner"], cfg["repo"], cfg["branch"])
        main_sha = main.get("sha") or ""
        main_commit = _enrich_commit(gh, cfg["owner"], cfg["repo"], main_sha) if main_sha else {}
        source_branch = _ado_source_branch(cfg["branch"], provider)

        rows: List[JsonDict] = []
        deployments: Dict[str, JsonDict] = {}
        unique_deployment_shas: Dict[str, JsonDict] = {}
        for group in cfg.get("ado_groups") or []:
            group_name = str(group.get("name") or group.get("label") or "pipeline")
            group_label = str(group.get("label") or group_name)
            npr_deployment = _latest_deployment_for_spec(
                ado,
                spec_text=str(group.get("npr") or ""),
                provider=provider,
                environment="npr",
                source_branch=source_branch,
            )
            prd_deployment = _latest_deployment_for_spec(
                ado,
                spec_text=str(group.get("prd") or ""),
                provider=provider,
                environment="prd",
                source_branch=source_branch,
            )
            deployments[f"{group_name}:npr"] = npr_deployment
            deployments[f"{group_name}:prd"] = prd_deployment
            for deployment in (npr_deployment, prd_deployment):
                sha = _deployment_sha(deployment)
                if sha and sha not in unique_deployment_shas:
                    unique_deployment_shas[sha] = _enrich_commit(gh, cfg["owner"], cfg["repo"], sha)

            npr_commit = unique_deployment_shas.get(_deployment_sha(npr_deployment), {})
            prd_commit = unique_deployment_shas.get(_deployment_sha(prd_deployment), {})
            if (group.get("npr") or "").strip() and (group.get("prd") or "").strip():
                rows.append(_make_comparison_row(
                    provider=provider,
                    provider_label=cfg["label"],
                    owner=cfg["owner"],
                    repo=cfg["repo"],
                    branch=cfg["branch"],
                    group_name=group_name,
                    group_label=group_label,
                    comparison_type="npr_prd",
                    main=main,
                    npr_deployment=npr_deployment,
                    prd_deployment=prd_deployment,
                    main_commit=main_commit,
                    npr_commit=npr_commit,
                    prd_commit=prd_commit,
                    checked_at=checked_at,
                ))

        status = _provider_status(rows)
        state = {
            "provider": provider,
            "label": cfg["label"],
            "repo": cfg["repo"],
            "branch": cfg["branch"],
            "mode": "ado_deployed_commit_comparison",
            "status": status,
            "generatedAt": checked_at,
            "updatedAt": checked_at,
            "main": main,
            "summary": {
                "status": status,
                "main_branch": cfg["branch"],
                "main_sha": main_sha,
                "source_branch": source_branch,
                "jira_configured": _jira_configured(),
                "azdo_org": azdo["org"],
                "azdo_project": azdo["project"],
            },
            "environments": rows,
            "ado_groups": cfg.get("ado_groups", []),
            "deployments": {key: _deployment_for_ui(value) for key, value in deployments.items()},
        }
        state["alerts"] = _provider_alerts(state)
        return state
    except Exception as exc:
        message = str(exc)
        if DEBUG:
            message = f"{message}\n{traceback.format_exc()}"
        return _error_provider(provider, message, cfg)


def _blank_state() -> JsonDict:
    now = _utc_now()
    return {
        "schemaVersion": CACHE_SCHEMA_VERSION,
        "mode": "ado_deployed_commit_comparison",
        "generatedAt": now,
        "updatedAt": now,
        "providers": {"aws": _waiting_provider("aws"), "azure": _waiting_provider("azure")},
        "alerts": [],
        "summary": {},
    }


def _recompute_summary(state: JsonDict) -> JsonDict:
    rows: List[JsonDict] = []
    alerts: List[JsonDict] = []
    for provider_state in (state.get("providers") or {}).values():
        rows.extend(provider_state.get("environments") or [])
        alerts.extend(provider_state.get("alerts") or _provider_alerts(provider_state))
    summary = {"total": 0, "drift": 0, "clean": 0, "waiting": 0, "error": 0, "critical": 0}
    for row in rows:
        status = row.get("status") or "waiting"
        summary["total"] += 1
        if status == "drift":
            summary["drift"] += 1
        elif status == "clean":
            summary["clean"] += 1
        elif status == "error":
            summary["error"] += 1
        else:
            summary["waiting"] += 1
        if row.get("severity") == "critical" or status == "error":
            summary["critical"] += 1
    state["alerts"] = alerts
    state["summary"] = summary
    state["schemaVersion"] = CACHE_SCHEMA_VERSION
    state["mode"] = "ado_deployed_commit_comparison"
    state["updatedAt"] = _utc_now()
    return summary


def _load_cache() -> Optional[JsonDict]:
    global _MEMORY_CACHE, _MEMORY_CACHE_LOADED_AT
    if _MEMORY_CACHE is not None and _MEMORY_CACHE.get("schemaVersion") == CACHE_SCHEMA_VERSION:
        return _MEMORY_CACHE
    if not os.path.isfile(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as handle:
            state = json.load(handle)
        if state.get("schemaVersion") != CACHE_SCHEMA_VERSION:
            return None
        _MEMORY_CACHE = state
        _MEMORY_CACHE_LOADED_AT = time.time()
        return state
    except Exception:
        return None


def _save_cache(state: JsonDict) -> None:
    global _MEMORY_CACHE, _MEMORY_CACHE_LOADED_AT
    state["schemaVersion"] = CACHE_SCHEMA_VERSION
    _recompute_summary(state)
    _MEMORY_CACHE = state
    _MEMORY_CACHE_LOADED_AT = time.time()
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as handle:
            json.dump(state, handle)
    except Exception:
        pass


def _cache_age_seconds(state: Optional[JsonDict]) -> Optional[int]:
    if not state:
        return None
    updated = state.get("updatedAt") or state.get("generatedAt")
    if not updated:
        return None
    timestamp = _parse_date(updated)
    if not timestamp:
        return None
    return max(0, int(time.time() - timestamp))


def _requested_provider(data: Optional[JsonDict]) -> str:
    value = str((data or {}).get("provider") or (data or {}).get("cloud") or "all").strip().lower()
    if value in {"aws", "amazon"}:
        return "aws"
    if value in {"azure", "az"}:
        return "azure"
    return "all"


def _json_safe(value: Any) -> Any:
    """Return a payload that json.dumps can serialize."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return str(value)


def _response(state: JsonDict, *, refreshed_provider: str = "", from_cache: bool = False, status_code: int = 200) -> Tuple[JsonDict, int]:
    _recompute_summary(state)
    payload = {
        "ok": True,
        "mode": state.get("mode"),
        "drift": state,
        "results": state,
        "providers": state.get("providers"),
        "summary": state.get("summary"),
        "alerts": state.get("alerts"),
        "has_live_data": any((provider.get("environments") for provider in (state.get("providers") or {}).values() if isinstance(provider, dict))),
        "refreshed_provider": refreshed_provider,
        "from_cache": from_cache,
        "cache_age_seconds": _cache_age_seconds(state),
    }
    return _json_safe(payload), status_code


def _safe_failure_response(provider: str, message: str) -> Tuple[JsonDict, int]:
    """Return a dashboard-compatible error payload instead of letting the Function route return 500."""
    state = _load_cache() or _blank_state()
    providers = ["aws", "azure"] if provider == "all" else [provider]
    for key in providers:
        if key in PROVIDER_DEFAULTS:
            state.setdefault("providers", {})[key] = _error_provider(key, message)
    state["generatedAt"] = _utc_now()
    try:
        _save_cache(state)
    except Exception:
        pass
    payload, _ = _response(state, refreshed_provider=provider, from_cache=False)
    payload["ok"] = True
    payload["backend_exception"] = message
    return payload, 200


def _safe_call(provider: str, func) -> Tuple[JsonDict, int]:
    try:
        return func()
    except Exception as exc:
        message = str(exc)
        if DEBUG:
            message = f"{message}\n{traceback.format_exc()}"
        return _safe_failure_response(provider, message)


def _handler_error_response(data: Optional[JsonDict], exc: Exception, operation: str) -> Tuple[JsonDict, int]:
    provider = _requested_provider(data if isinstance(data, dict) else {})
    message = f"{operation} failed: {exc}"
    if DEBUG:
        message = f"{message}\n{traceback.format_exc()}"
    state = _load_cache() or _blank_state()
    providers = ["aws", "azure"] if provider == "all" else [provider]
    for key in providers:
        if key in PROVIDER_DEFAULTS:
            state.setdefault("providers", {})[key] = _error_provider(key, message)
    state["generatedAt"] = _utc_now()
    _save_cache(state)
    return _response(state, refreshed_provider=provider, from_cache=False, status_code=200)


def handle_commit_drift_refresh_request(data: Optional[JsonDict], headers: Optional[Any] = None) -> Tuple[JsonDict, int]:
    provider = _requested_provider(data)

    def work() -> Tuple[JsonDict, int]:
        state = _load_cache() or _blank_state()
        providers = ["aws", "azure"] if provider == "all" else [provider]
        for key in providers:
            state.setdefault("providers", {})[key] = _refresh_provider(key)
        state["generatedAt"] = _utc_now()
        _save_cache(state)
        return _response(state, refreshed_provider=provider, from_cache=False)

    return _safe_call(provider, work)


def handle_commit_drift_status_request(data: Optional[JsonDict], headers: Optional[Any] = None) -> Tuple[JsonDict, int]:
    data = data or {}
    provider = _requested_provider(data)

    def work() -> Tuple[JsonDict, int]:
        force_refresh = str(data.get("refresh") or data.get("force") or "").strip().lower() in {"1", "true", "yes", "on"}
        state = _load_cache()
        age = _cache_age_seconds(state)
        stale = age is None or age > CACHE_TTL_SECONDS
        if force_refresh or (STATUS_AUTO_REFRESH and stale):
            return handle_commit_drift_refresh_request({"provider": provider}, headers)
        if state is None:
            state = _blank_state()
        return _response(state, refreshed_provider="", from_cache=True)

    return _safe_call(provider, work)


def handle_commit_drift_attribution_request(data: Optional[JsonDict], headers: Optional[Any] = None) -> Tuple[JsonDict, int]:
    state = _load_cache() or _blank_state()
    return {
        "ok": True,
        "reply": "Commit, ADO run, GitHub PR, user, and Jira attribution is included in the drift payload.",
        "drift": state,
        "results": state,
    }, 200



def _jira_auth_headers(extra: Optional[JsonDict] = None) -> JsonDict:
    email = os.getenv("JIRA_EMAIL", "")
    token = os.getenv("JIRA_API_TOKEN", "")
    auth = base64.b64encode(f"{email}:{token}".encode("utf-8")).decode("ascii")
    headers: JsonDict = {
        "Accept": "application/json",
        "Authorization": f"Basic {auth}",
        "User-Agent": "terrabot-ado-deployed-commit-drift",
    }
    if extra:
        headers.update(extra)
    return headers


def _jira_json_request(method: str, path: str, body: Optional[JsonDict] = None, query: Optional[JsonDict] = None, version: str = "3") -> JsonDict:
    base = _jira_base_url()
    if not base:
        raise RuntimeError("JIRA_BASE_URL is not configured.")
    api_path = path if path.startswith("/rest/") else f"/rest/api/{version}{path}"
    url = f"{base}{api_path}"
    clean_query = {k: v for k, v in (query or {}).items() if v not in (None, "")}
    if clean_query:
        url += "?" + urllib.parse.urlencode(clean_query)
    data = None
    headers = _jira_auth_headers()
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers = _jira_auth_headers({"Content-Type": "application/json"})
    req = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=JIRA_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = _parse_jira_error(exc)
        raise RuntimeError(f"Jira API {method.upper()} {api_path} failed with HTTP {exc.code}: {detail}") from exc


def _jira_project_key_from_existing_data(data: Optional[JsonDict] = None) -> str:
    data = data or {}
    tickets: List[Any] = []
    for key in ("jira_tickets", "jiraTickets"):
        tickets.extend(data.get(key) or [])
    for row in data.get("rows") or []:
        if isinstance(row, dict):
            for key in ("jira_tickets", "jiraTickets"):
                tickets.extend(row.get(key) or [])
    for ticket in tickets:
        if isinstance(ticket, dict):
            candidate = ticket.get("key") or ticket.get("id") or ""
        else:
            candidate = str(ticket or "")
        prefix, _ = _jira_key_parts(candidate)
        if prefix:
            return prefix
    return ""


def _jira_create_project_key(data: Optional[JsonDict] = None) -> str:
    raw = str(
        (data or {}).get("project_key")
        or os.getenv("JIRA_CREATE_PROJECT_KEY")
        or os.getenv("JIRA_DRIFT_PROJECT_KEY")
        or os.getenv("JIRA_PROJECT_KEY")
        or ""
    ).strip().upper()
    if raw:
        return re.sub(r"[^A-Z0-9]", "", raw)
    allowed = _jira_allowed_project_keys()
    if allowed:
        return allowed[0]
    return _jira_project_key_from_existing_data(data)


def _jira_issue_type() -> str:
    return os.getenv("JIRA_DRIFT_ISSUE_TYPE") or os.getenv("JIRA_ISSUE_TYPE") or "Task"


def _jira_adf_text(text: str, url: str = "") -> JsonDict:
    node: JsonDict = {"type": "text", "text": str(text or "")}
    if url:
        node["marks"] = [{"type": "link", "attrs": {"href": url}}]
    return node


def _jira_adf_paragraph(*parts: JsonDict) -> JsonDict:
    return {"type": "paragraph", "content": [part for part in parts if part]}


def _jira_adf_heading(text: str) -> JsonDict:
    return {
        "type": "heading",
        "attrs": {"level": 3},
        "content": [_jira_adf_text(text)],
    }


def _jira_adf_doc(lines: Iterable[str]) -> JsonDict:
    content = []
    for line in lines:
        text = str(line or "").strip()
        content.append(_jira_adf_paragraph(_jira_adf_text(text)) if text else _jira_adf_paragraph())
    return {"type": "doc", "version": 1, "content": content or [_jira_adf_paragraph()]}


def _value_from_any(data: JsonDict, *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _first_ado_url(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        lower = text.lower()
        if text and "github.com/" not in lower and ("dev.azure.com" in lower or "visualstudio.com" in lower or "/_build/" in lower or "_build/results" in lower):
            return text
    return ""


def _first_github_url(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text.lower().startswith("https://github.com/"):
            return text
    return ""


def _rows_for_jira_request(data: JsonDict) -> List[JsonDict]:
    rows = data.get("rows")
    if isinstance(rows, list) and rows:
        return [row for row in rows if isinstance(row, dict)]
    row = data.get("row")
    if isinstance(row, dict):
        return [row]
    return [data]


def _matching_cached_row(data: JsonDict) -> Optional[JsonDict]:
    state = _load_cache() or {}
    provider = _requested_provider(data)
    group = str(data.get("group") or data.get("group_label") or data.get("groupLabel") or "").strip()
    providers = state.get("providers") or {}
    search_providers = providers.items() if provider == "all" else [(provider, providers.get(provider) or {})]
    for _, provider_state in search_providers:
        for row in (provider_state or {}).get("environments") or []:
            if not isinstance(row, dict):
                continue
            candidates = [row.get("group"), row.get("group_label"), row.get("groupLabel"), row.get("name")]
            if group and any(str(item or "").strip() == group for item in candidates):
                return row
    return None


def _responsible_identities_from_data(data: JsonDict, rows: List[JsonDict]) -> List[str]:
    identities: List[str] = []
    seen = set()

    def add(value: Any) -> None:
        if isinstance(value, dict):
            candidates = [value.get("email"), value.get("login"), value.get("user"), value.get("username"), value.get("name"), value.get("displayName")]
        else:
            candidates = [value]
        for candidate in candidates:
            clean = _clean_user_identity_value(candidate)
            if clean and clean not in seen:
                identities.append(clean)
                seen.add(clean)
                return

    for user in data.get("responsible_users") or data.get("responsibleUsers") or []:
        add(user)
    for row in rows:
        for user in row.get("responsible_users") or row.get("responsibleUsers") or []:
            add(user)
        for commit in row.get("responsible_commits") or row.get("responsibleCommits") or []:
            add({
                "email": commit.get("author_email") or commit.get("authorEmail") or commit.get("committer_email") or commit.get("committerEmail"),
                "login": commit.get("author_login") or commit.get("authorLogin") or commit.get("committer_login") or commit.get("committerLogin"),
                "name": commit.get("author_name") or commit.get("authorName") or commit.get("committer_name") or commit.get("committerName"),
            })
    return identities


def _jira_description_adf(data: JsonDict, rows: List[JsonDict]) -> JsonDict:
    cached = _matching_cached_row(data) or {}
    merged = dict(cached)
    merged.update({k: v for k, v in data.items() if v not in (None, "", [])})

    npr_pipeline = _first_ado_url(
        merged.get("npr_pipeline_url"), merged.get("nprPipelineUrl"),
        ((merged.get("npr_deployment") or {}).get("url") if isinstance(merged.get("npr_deployment"), dict) else ""),
        ((merged.get("nprDeployment") or {}).get("url") if isinstance(merged.get("nprDeployment"), dict) else ""),
    )
    prd_pipeline = _first_ado_url(
        merged.get("prd_pipeline_url"), merged.get("prdPipelineUrl"),
        ((merged.get("prd_deployment") or {}).get("url") if isinstance(merged.get("prd_deployment"), dict) else ""),
        ((merged.get("prdDeployment") or {}).get("url") if isinstance(merged.get("prdDeployment"), dict) else ""),
    )

    npr_commit_url = _first_github_url(merged.get("npr_commit_url"), merged.get("nprCommitUrl"))
    prd_commit_url = _first_github_url(merged.get("prd_commit_url"), merged.get("prdCommitUrl"))
    main_commit_url = _first_github_url(
        merged.get("main_commit_url"),
        merged.get("mainCommitUrl"),
        ((merged.get("main") or {}).get("commit_url") if isinstance(merged.get("main"), dict) else ""),
    )

    npr_sha = _value_from_any(merged, "npr_sha", "nprSha") or "unknown"
    prd_sha = _value_from_any(merged, "prd_sha", "prdSha") or "unknown"
    main_sha = _value_from_any(merged, "main_sha", "mainSha") or "unknown"

    users = _responsible_identities_from_data(data, rows)

    content = [
        _jira_adf_heading("Terrabot detected Terraform deployed-commit drift."),
        _jira_adf_paragraph(
            _jira_adf_text("Status: "),
            _jira_adf_text(_value_from_any(merged, "status") or "drift"),
        ),
        _jira_adf_paragraph(
            _jira_adf_text("Severity: "),
            _jira_adf_text(_value_from_any(merged, "severity") or "unknown"),
        ),
        _jira_adf_paragraph(
            _jira_adf_text("Drift description: "),
            _jira_adf_text(_value_from_any(merged, "drift_description", "summary", "commit_summary") or "NPR, PRD, and main are not aligned."),
        ),
        _jira_adf_paragraph(
            _jira_adf_text("Fix guidance: "),
            _jira_adf_text(_value_from_any(merged, "fix_instructions", "remediation") or "Review the drift, validate the intended source SHA, and rerun or promote the matching ADO deployment pipeline."),
        ),
        _jira_adf_paragraph(),
        _jira_adf_paragraph(_jira_adf_text("NPR commit: "), _jira_adf_text(_short_sha(npr_sha), npr_commit_url)),
        _jira_adf_paragraph(_jira_adf_text("PRD commit: "), _jira_adf_text(_short_sha(prd_sha), prd_commit_url)),
        _jira_adf_paragraph(_jira_adf_text("Main commit: "), _jira_adf_text(_short_sha(main_sha), main_commit_url)),
    ]

    if npr_pipeline:
        content.append(_jira_adf_paragraph(_jira_adf_text("NPR pipeline: "), _jira_adf_text("Open NPR pipeline", npr_pipeline)))

    if prd_pipeline:
        content.append(_jira_adf_paragraph(_jira_adf_text("PRD pipeline: "), _jira_adf_text("Open PRD pipeline", prd_pipeline)))

    prs = []
    for pr in merged.get("pull_requests") or merged.get("pullRequests") or []:
        if isinstance(pr, dict):
            number = pr.get("number") or pr.get("id")
            url = pr.get("url") or pr.get("html_url") or pr.get("htmlUrl") or ""
            if number:
                prs.append((f"PR #{number}", url))

    if prs:
        content.append(_jira_adf_paragraph())
        content.append(_jira_adf_paragraph(_jira_adf_text("Pull requests:")))
        for label, url in prs:
            content.append(_jira_adf_paragraph(_jira_adf_text(label, url)))

    existing_jira = []
    for ticket in merged.get("jira_tickets") or merged.get("jiraTickets") or []:
        if isinstance(ticket, dict) and ticket.get("key"):
            existing_jira.append((str(ticket.get("key")), ticket.get("url") or ""))

    if existing_jira:
        content.append(_jira_adf_paragraph())
        content.append(_jira_adf_paragraph(_jira_adf_text("Existing Jira links found in PR/commit metadata:")))
        for key, url in existing_jira:
            content.append(_jira_adf_paragraph(_jira_adf_text(key, url)))

    if users:
        content.append(_jira_adf_paragraph())
        content.append(_jira_adf_paragraph(_jira_adf_text("Responsible user candidates: "), _jira_adf_text(", ".join(users))))

    return {"type": "doc", "version": 1, "content": content}

def _jira_find_assignable_account_id(issue_key: str, identities: List[str]) -> Tuple[str, str]:
    queries = []
    for identity in identities:
        clean = _clean_user_identity_value(identity)
        if clean and clean not in queries:
            queries.append(clean)
    for query in queries:
        search_paths = [
            ("/user/assignable/search", {"issueKey": issue_key, "query": query, "maxResults": 10}),
            ("/user/search", {"query": query, "maxResults": 10}),
        ]
        for path, params in search_paths:
            try:
                results = _jira_json_request("GET", path, query=params, version="3")
            except Exception:
                continue
            if not isinstance(results, list):
                continue
            for user in results:
                if not isinstance(user, dict):
                    continue
                account_id = user.get("accountId") or ""
                if not account_id:
                    continue
                display = user.get("displayName") or user.get("emailAddress") or query
                return account_id, display
    return "", ""


def _jira_assign_issue(issue_key: str, identities: List[str]) -> JsonDict:
    account_id, display = _jira_find_assignable_account_id(issue_key, identities)
    if not account_id:
        return {"assigned": False, "message": "No assignable Jira user matched the responsible user list."}
    _jira_json_request("PUT", f"/issue/{urllib.parse.quote(issue_key, safe='')}/assignee", {"accountId": account_id}, version="3")
    return {"assigned": True, "accountId": account_id, "displayName": display}


def _create_jira_issue_for_drift(data: JsonDict) -> JsonDict:
    if not _jira_configured():
        raise RuntimeError("Jira is not configured. Set JIRA_BASE_URL, JIRA_EMAIL, and JIRA_API_TOKEN.")
    project_key = _jira_create_project_key(data)
    if not project_key:
        raise RuntimeError("Set JIRA_CREATE_PROJECT_KEY, JIRA_DRIFT_PROJECT_KEY, JIRA_PROJECT_KEY, or JIRA_PROJECT_KEYS before creating drift tickets. Use the Jira project key prefix, for example ABC in ABC-123.")

    rows = _rows_for_jira_request(data)
    cached = _matching_cached_row(data) or {}
    merged = dict(cached)
    merged.update({k: v for k, v in data.items() if v not in (None, "", [])})
    provider = _value_from_any(merged, "provider", "providerLabel", "provider_label") or "Cloud"
    scope = _value_from_any(merged, "group_label", "groupLabel", "group", "name") or "deployment"
    summary = str(data.get("summary_override") or f"Terraform drift fix: {provider} {scope} NPR/PRD/main alignment")[:255]
    description_adf = _jira_description_adf(merged, rows)

    issue_body = {
        "fields": {
            "project": {"key": project_key},
            "summary": summary,
            "description": description_adf,
            "issuetype": {"name": _jira_issue_type()},
            "labels": ["terrabot", "terraform-drift"],
        }
    }

    try:
        issue = _jira_json_request("POST", "/issue", issue_body, version="3")
    except Exception as first_exc:
        issue_body_no_labels = json.loads(json.dumps(issue_body))
        issue_body_no_labels.get("fields", {}).pop("labels", None)
        try:
            issue = _jira_json_request("POST", "/issue", issue_body_no_labels, version="3")
        except Exception:
            server_body = json.loads(json.dumps(issue_body_no_labels))
            server_body["fields"]["description"] = (
                 "Terrabot detected Terraform deployed-commit drift.\n\n"
                 f"Status: {_value_from_any(merged, 'status') or 'drift'}\n"
                 f"Severity: {_value_from_any(merged, 'severity') or 'unknown'}\n"
                 f"Drift description: {_value_from_any(merged, 'drift_description', 'summary', 'commit_summary') or 'NPR, PRD, and main are not aligned.'}\n"
                 f"Fix guidance: {_value_from_any(merged, 'fix_instructions', 'remediation') or 'Review the drift, validate the intended source SHA, and rerun or promote the matching ADO deployment pipeline.'}\n"
            )
            try:
                issue = _jira_json_request("POST", "/issue", server_body, version="2")
            except Exception as second_exc:
                raise RuntimeError(f"Jira issue creation failed. First error: {first_exc}; fallback error: {second_exc}") from second_exc

    key = issue.get("key") or ""
    ticket = {
        "key": key,
        "id": issue.get("id"),
        "url": _jira_issue_url(key),
        "self": issue.get("self"),
        "status": "Created",
        "available": True,
        "display": True,
    }

    identities = _responsible_identities_from_data(merged, rows)
    assignment = {"assigned": False, "message": "No responsible user found."}
    if key and identities:
        try:
            assignment = _jira_assign_issue(key, identities)
        except Exception as exc:
            assignment = {"assigned": False, "message": str(exc)}
    ticket["assignment"] = assignment
    return ticket


def _append_created_jira_to_cache(data: JsonDict, ticket: JsonDict) -> None:
    if not ticket.get("key"):
        return
    state = _load_cache()
    if not state:
        return
    provider = _requested_provider(data)
    group = str(data.get("group") or data.get("group_label") or data.get("groupLabel") or "").strip()
    providers = state.get("providers") or {}
    search_providers = providers.items() if provider == "all" else [(provider, providers.get(provider) or {})]
    for _, provider_state in search_providers:
        rows = (provider_state or {}).get("environments") or []
        for row in rows:
            if not isinstance(row, dict):
                continue
            candidates = [row.get("group"), row.get("group_label"), row.get("groupLabel"), row.get("name")]
            if group and not any(str(item or "").strip() == group for item in candidates):
                continue
            for key in ("jiraTickets", "jira_tickets"):
                tickets = row.setdefault(key, [])
                if not any((item or {}).get("key") == ticket.get("key") for item in tickets if isinstance(item, dict)):
                    tickets.append(ticket)
    _save_cache(state)


def handle_commit_drift_create_jira_request(data: Optional[JsonDict], headers: Optional[Any] = None) -> Tuple[JsonDict, int]:
    data = data or {}
    try:
        ticket = _create_jira_issue_for_drift(data)
        try:
            _append_created_jira_to_cache(data, ticket)
        except Exception:
            pass
        return _json_safe({
            "ok": True,
            "reply": f"Created Jira ticket {ticket.get('key')}",
            "ticket": ticket,
            "jira_ticket": ticket,
        }), 200
    except Exception as exc:
        message = str(exc)
        if DEBUG:
            message = f"{message}\n{traceback.format_exc()}"
        return {"ok": False, "reply": "Failed to create Jira drift ticket.", "error": message}, 500




# Compatible aliases for Function App routes.
def handle_drift_jira_ticket_request(data: Optional[JsonDict], headers: Optional[Any] = None) -> Tuple[JsonDict, int]:
    return handle_commit_drift_create_jira_request(data, headers)


def handle_drift_create_jira_request(data: Optional[JsonDict], headers: Optional[Any] = None) -> Tuple[JsonDict, int]:
    return handle_commit_drift_create_jira_request(data, headers)


def handle_commit_drift_jira_ticket_request(data: Optional[JsonDict], headers: Optional[Any] = None) -> Tuple[JsonDict, int]:
    return handle_commit_drift_create_jira_request(data, headers)


def _provider_text_summary(provider_key: str, provider_state: JsonDict) -> List[str]:
    label = provider_state.get("label") or provider_key.upper()
    summary = provider_state.get("summary") or {}
    lines = [f"{label}: {provider_state.get('status', 'waiting')}"]
    if summary.get("main_sha"):
        lines.append(f"Main: {summary.get('main_branch')}@{_short_sha(summary.get('main_sha'))}.")
    for row in provider_state.get("environments") or []:
        if row.get("status") in {"drift", "error"}:
            lines.append(f"- {row.get('name')}: {row.get('summary')}")
            if row.get("fix_instructions") or row.get("remediation"):
                lines.append(f"  Fix: {row.get('fix_instructions') or row.get('remediation')}")
            tickets = row.get("jiraTickets") or row.get("jira_tickets") or []
            if tickets:
                lines.append("  Jira: " + ", ".join(f"{t.get('key')}={t.get('status')}" for t in tickets))
    return lines


def handle_commit_drift_question_request(data: Optional[JsonDict], headers: Optional[Any] = None) -> Tuple[JsonDict, int]:
    data = data or {}
    provider = _requested_provider(data)
    state = _load_cache() or _blank_state()
    lines = ["Backend Azure DevOps deployed-commit drift summary", ""]
    providers = ["aws", "azure"] if provider == "all" else [provider]
    for key in providers:
        provider_state = (state.get("providers") or {}).get(key) or _waiting_provider(key)
        lines.extend(_provider_text_summary(key, provider_state))
        lines.append("")
    return {"ok": True, "reply": "\n".join(lines).strip(), "drift": state}, 200


def handle_commit_drift_ingest_request(data: Optional[JsonDict], headers: Optional[Any] = None) -> Tuple[JsonDict, int]:
    return {
        "ok": True,
        "reply": "Pipeline/Foundry ingest is disabled. Drift is resolved directly by the backend from GitHub main and Azure DevOps successful pipeline runs.",
        "disabled": True,
    }, 200
