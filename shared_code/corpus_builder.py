import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional

from shared_code.repo_catalog import (
    detect_repo_name_from_path,
    get_repo_rule,
    infer_doc_type,
    infer_module_name,
    infer_environment_name,
    infer_flags,
    should_index_file,
)

try:
    from terrabot_core.scanner import scan_repository
    from terrabot_core.terraform_parser import infer_resource_type_from_text, providers_to_clouds
except Exception:  # pragma: no cover - keeps Azure Function import resilient
    scan_repository = None
    infer_resource_type_from_text = None
    providers_to_clouds = None


def read_text_file(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="utf-8-sig")
        except Exception:
            return None
    except Exception:
        return None


def normalize_content(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    return text.strip()


def build_doc_id(repo_name: str, relative_path: str) -> str:
    raw = f"{repo_name}::{relative_path}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{repo_name}-{digest}"


def _find_git_root(file_path: Path) -> Optional[Path]:
    current = file_path.parent if file_path.is_file() else file_path
    for candidate in [current] + list(current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def find_repo_root_parts(file_path: Path, base_root: Optional[Path] = None) -> Optional[tuple[str, Path]]:
    if base_root is not None:
        repo_root = base_root.resolve()
        try:
            file_path.resolve().relative_to(repo_root)
        except ValueError:
            return None
        return repo_root.name, repo_root

    path_str = str(file_path).replace("\\", "/")
    repo_name = detect_repo_name_from_path(path_str)
    git_root = _find_git_root(file_path)
    if git_root is not None:
        return git_root.name, git_root
    if repo_name:
        rule = get_repo_rule(repo_name)
        parts = list(file_path.parts)
        for i, part in enumerate(parts):
            if part == rule.root_folder_name:
                return repo_name, Path(*parts[: i + 1])
    return None


def infer_resource_type(relative_path: str, content: str) -> Optional[str]:
    if infer_resource_type_from_text:
        return infer_resource_type_from_text(relative_path, content)
    rp = relative_path.lower()
    text = (content or "").lower()
    resource_map = {
        "s3": ["s3", "bucket"],
        "ec2": ["ec2", "instance"],
        "iam": ["iam"],
        "rds": ["rds", "db_instance", "database"],
        "vpc": ["vpc"],
        "security_group": ["security_group", "security group"],
        "storage_account": ["storage account", "azurerm_storage_account"],
        "key_vault": ["key vault", "azurerm_key_vault"],
        "vnet": ["vnet", "virtual network", "azurerm_virtual_network"],
        "subnet": ["subnet", "azurerm_subnet"],
        "aks": ["aks", "azurerm_kubernetes_cluster"],
        "vmss": ["vmss", "virtual machine scale set"],
        "rbac": ["rbac", "role_assignment", "azurerm_role_assignment"],
        "mysql": ["mysql", "mysql flexible", "azurerm_mysql"],
        "data_factory": ["data factory", "azurerm_data_factory"],
    }

    for resource_type, hints in resource_map.items():
        if any(hint in rp or hint in text for hint in hints):
            return resource_type
    return None


def _infer_cloud_from_content(relative_path: str, content: str, fallback: str = "unknown") -> str:
    text = (content or "").lower()
    rp = relative_path.lower()
    if "azurerm_" in text or "azuread_" in text or "azurerm" in text or "azure-pipelines" in rp:
        return "azure"
    if "aws_" in text or "provider \"aws\"" in text or "/dev_aws/" in rp or "/prod_aws/" in rp:
        return "aws"
    return fallback


def build_document(file_path: Path, repo_root: Optional[Path] = None, repo_name: Optional[str] = None, cloud: Optional[str] = None) -> Optional[Dict[str, Any]]:
    found = find_repo_root_parts(file_path, base_root=repo_root)
    if not found:
        return None

    inferred_repo_name, found_root = found
    repo_name = repo_name or inferred_repo_name
    relative_path = str(file_path.relative_to(found_root)).replace("\\", "/")

    if not should_index_file(relative_path):
        return None

    content = read_text_file(file_path)
    if not content:
        return None

    content = normalize_content(content)
    if not content:
        return None

    rule = get_repo_rule(repo_name)
    doc_type = infer_doc_type(repo_name, relative_path)
    module_name = infer_module_name(repo_name, relative_path)
    environment_name = infer_environment_name(repo_name, relative_path)
    flags = infer_flags(repo_name, relative_path)
    resource_type = infer_resource_type(relative_path, content)
    inferred_cloud = cloud or _infer_cloud_from_content(relative_path, content, fallback=rule.cloud)

    return {
        "id": build_doc_id(repo_name, relative_path),
        "repo_name": repo_name,
        "cloud": inferred_cloud,
        "strategy": rule.strategy,
        "doc_type": doc_type,
        "path": relative_path,
        "module_name": module_name,
        "resource_type": resource_type,
        "environment_name": environment_name,
        "is_module_definition": flags["is_module_definition"],
        "is_module_usage": flags["is_module_usage"],
        "is_value_source": flags["is_value_source"],
        "is_repo_template": flags["is_repo_template"],
        "content": content,
    }


def collect_repo_documents(base_dir: str) -> List[Dict[str, Any]]:
    base_path = Path(base_dir).resolve()
    if not base_path.exists():
        raise FileNotFoundError(f"Base directory does not exist: {base_dir}")

    repo_name = base_path.name
    cloud = None
    if scan_repository:
        try:
            profile = scan_repository(str(base_path))
            repo_name = profile.repo_name
            cloud = profile.clouds[0] if len(profile.clouds) == 1 else None
        except Exception:
            pass

    documents: List[Dict[str, Any]] = []

    for file_path in base_path.rglob("*"):
        if not file_path.is_file():
            continue

        doc = build_document(file_path, repo_root=base_path, repo_name=repo_name, cloud=cloud)
        if doc:
            documents.append(doc)

    return documents
