from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional

TEXT_EXTENSIONS = {
    ".tf",
    ".tfvars",
    ".hcl",
    ".md",
    ".yml",
    ".yaml",
    ".json",
    ".txt",
    ".sh",
    ".ps1",
    ".toml",
    ".rego",
}

IGNORED_DIRS = {
    ".git",
    ".terraform",
    ".terragrunt-cache",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".python_packages",
    "dist",
    "build",
    "coverage",
}

IGNORED_FILE_SUFFIXES = {
    ".tfstate",
    ".tfstate.backup",
    ".pem",
    ".key",
    ".pfx",
    ".crt",
    ".cer",
    ".zip",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".pyc",
    ".DS_Store",
}

SENSITIVE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    "terraform.tfstate",
    "terraform.tfstate.backup",
}


def normalize_path(path: str) -> str:
    return str(path).replace(os.sep, "/")


def is_ignored_path(relative_path: str) -> bool:
    rp = normalize_path(relative_path).strip("/")
    lower = rp.lower()
    parts = lower.split("/") if lower else []

    if any(part in IGNORED_DIRS for part in parts):
        return True
    if parts and parts[-1] in SENSITIVE_NAMES:
        return True
    if any(lower.endswith(suffix.lower()) for suffix in IGNORED_FILE_SUFFIXES):
        return True
    if lower.endswith(".auto.tfvars") and "example" not in lower and "sample" not in lower:
        # auto tfvars often carry deployment-specific values. Do not include by default.
        return True
    return False


def should_read_file(path: Path, relative_path: str, max_bytes: int = 600_000) -> bool:
    if is_ignored_path(relative_path):
        return False
    if path.suffix.lower() not in TEXT_EXTENSIONS and path.name not in {
        "Makefile",
        "Taskfile.yml",
        "Taskfile.yaml",
        ".pre-commit-config.yaml",
        ".tool-versions",
        "CODEOWNERS",
    }:
        return False
    try:
        return path.stat().st_size <= max_bytes
    except OSError:
        return False


def read_text(path: Path) -> Optional[str]:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
        except OSError:
            return None
    return None


def iter_repo_files(root: Path) -> Iterable[Path]:
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]
        for filename in filenames:
            path = Path(dirpath) / filename
            try:
                relative = normalize_path(str(path.relative_to(root)))
            except ValueError:
                continue
            if should_read_file(path, relative):
                yield path


def find_git_root(path: Path) -> Path:
    current = path.resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current] + list(current.parents):
        if (candidate / ".git").exists():
            return candidate
    return current
