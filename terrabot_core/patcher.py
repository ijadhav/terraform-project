from __future__ import annotations

import difflib
from pathlib import Path
from typing import Iterable, List

from terrabot_core.filesystem import normalize_path, read_text
from terrabot_core.models import PatchFile


def build_unified_diff(workspace: str, files: Iterable[PatchFile]) -> str:
    workspace_path = Path(workspace).expanduser().resolve()
    chunks: List[str] = []
    for file in files:
        target = (workspace_path / file.path).resolve()
        try:
            target.relative_to(workspace_path)
        except ValueError:
            raise ValueError(f"Refusing to diff path outside workspace: {file.path}")

        old_text = ""
        if target.exists() and file.operation != "add":
            old_text = read_text(target) or ""

        if file.operation == "delete":
            new_text = ""
        elif file.operation in {"insert_into_block", "fill"} and file.content is None:
            # Typed edits are expanded by the API additive guard before apply.
            # For the early model-path diff, show no destructive full-file diff
            # rather than pretending the target content is empty.
            new_text = old_text
        else:
            new_text = file.content or ""

        old_lines = old_text.splitlines(keepends=True)
        new_lines = new_text.splitlines(keepends=True)
        if new_text and not new_text.endswith("\n"):
            new_lines.append("\n")
        if old_text == new_text:
            continue
        chunks.extend(
            difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"a/{normalize_path(file.path)}",
                tofile=f"b/{normalize_path(file.path)}",
                lineterm="",
            )
        )
    return "\n".join(chunks)
