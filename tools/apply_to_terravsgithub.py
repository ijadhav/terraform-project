#!/usr/bin/env python3
"""Apply the Cursor-backed Terrabot testing integration safely and idempotently.

The installer validates every edit in memory before writing. It only:

* adds the primary-context loader/document and Cursor prompt provider;
* imports the provider in the existing automated-test runner;
* invokes it after the backend has derived immutable live-repository cases;
* exposes the primary-context module through the ordered core loader;
* attaches primary context in the existing Foundry call path; and
* adds focused unit tests.

The latest Terrabot backend keeps ``call_agent`` in
``terrabot_core_parts/10_teams_router_runtime.py`` and executes that part in
``terrabot_service_core.py``'s shared namespace. A legacy monolithic-core
fallback is retained for older checkouts. No existing function is removed or
renamed.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


class InstallError(RuntimeError):
    """Raised when the target repository cannot be patched safely."""


@dataclass(frozen=True)
class PlannedFile:
    path: Path
    content: bytes
    reason: str


RUNNER_RELATIVE = Path("shared_code/automated_tests/terrabot_test_runner.py")
CORE_LOADER_RELATIVE = Path("shared_code/terrabot_service_core.py")
ROUTER_RUNTIME_RELATIVE = Path(
    "shared_code/terrabot_core_parts/10_teams_router_runtime.py"
)
# Compatibility alias for callers that imported the earlier installer constant.
CORE_RELATIVE = CORE_LOADER_RELATIVE

COPY_MAP = {
    Path("shared_code/context/terrabot_terraform_primary_context.yaml"): Path(
        "shared_code/context/terrabot_terraform_primary_context.yaml"
    ),
    Path("shared_code/terraform_primary_context.py"): Path(
        "shared_code/terraform_primary_context.py"
    ),
    Path("shared_code/automated_tests/cursor_prompt_provider.py"): Path(
        "shared_code/automated_tests/cursor_prompt_provider.py"
    ),
    Path("tests/test_terraform_primary_context.py"): Path(
        "tests/test_terraform_primary_context.py"
    ),
    Path("tests/test_cursor_prompt_provider.py"): Path(
        "tests/test_cursor_prompt_provider.py"
    ),
}

RUNNER_IMPORT = "from shared_code.automated_tests import cursor_prompt_provider"
CORE_IMPORT = "from shared_code import terraform_primary_context"


def _bundle_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InstallError(f"Unable to read {path}: {exc}") from exc


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise InstallError(
            f"Expected exactly one {label} anchor, found {count}. "
            "The target file may not match the latest Terrabot workflow."
        )
    return text.replace(old, new, 1)


def _top_level_function_slice(text: str, function_name: str) -> tuple[int, int]:
    marker = f"def {function_name}("
    start = text.find(marker)
    if start < 0:
        raise InstallError(f"Could not find function {function_name}.")
    if start > 0 and text[start - 1] not in {"\n", "\r"}:
        raise InstallError(f"Function marker for {function_name} was not top-level.")

    search_from = start + len(marker)
    next_def = text.find("\ndef ", search_from)
    next_async_def = text.find("\nasync def ", search_from)
    candidates = [value + 1 for value in (next_def, next_async_def) if value >= 0]
    end = min(candidates) if candidates else len(text)
    return start, end


def _patch_runner(text: str) -> str:
    if RUNNER_IMPORT not in text:
        import_anchor = "from shared_code import repository_context\n"
        text = _replace_once(
            text,
            import_anchor,
            import_anchor + RUNNER_IMPORT + "\n",
            label="automated-test runner import",
        )

    start, end = _top_level_function_slice(text, "_derive_test_cases")
    function_text = text[start:end]
    invocation = "cursor_prompt_provider.apply_cursor_generated_prompts("
    if invocation in function_text:
        return text

    return_anchor = "    return cases[:count], errors\n"
    replacement = (
        "    selected_cases = cases[:count]\n"
        "    selected_cases = cursor_prompt_provider.apply_cursor_generated_prompts(\n"
        "        selected_cases,\n"
        "        run_id=run_id,\n"
        "        log_event=_diag,\n"
        "    )\n"
        "    return selected_cases, errors\n"
    )
    if function_text.count(return_anchor) != 1:
        raise InstallError(
            "Expected one final 'return cases[:count], errors' in _derive_test_cases; "
            f"found {function_text.count(return_anchor)}."
        )
    function_text = function_text.replace(return_anchor, replacement, 1)
    return text[:start] + function_text + text[end:]


def _patch_core_loader(text: str) -> str:
    """Expose the primary-context module to all ordered core parts."""
    if CORE_IMPORT in text:
        return text
    import_anchor = "from pathlib import Path\n"
    return _replace_once(
        text,
        import_anchor,
        import_anchor + "\n" + CORE_IMPORT + "\n",
        label="ordered Terrabot core-loader import",
    )


def _patch_call_agent(text: str) -> str:
    """Attach primary context inside the existing call_agent implementation."""
    start, end = _top_level_function_slice(text, "call_agent")
    function_text = text[start:end]
    invocation = "terraform_primary_context.attach_primary_context_to_agent_input("
    if invocation in function_text:
        return text

    attach_anchor = (
        "    context_enriched_input = (\n"
        "        _teams_attach_repository_context(agent_input, active) if teams_active else agent_input\n"
        "    )\n"
    )
    replacement = attach_anchor + (
        "    context_enriched_input = terraform_primary_context.attach_primary_context_to_agent_input(\n"
        "        context_enriched_input,\n"
        "        logger=LOGGER,\n"
        "    )\n"
    )
    if function_text.count(attach_anchor) != 1:
        raise InstallError(
            "Expected one repository-context attachment block in call_agent; "
            f"found {function_text.count(attach_anchor)}."
        )
    function_text = function_text.replace(attach_anchor, replacement, 1)
    return text[:start] + function_text + text[end:]


def _patch_legacy_core(text: str) -> str:
    """Patch an older monolithic Terrabot core when no core-parts file exists."""
    if CORE_IMPORT not in text:
        import_anchor = "from shared_code import repository_context as shared_repository_context\n"
        text = _replace_once(
            text,
            import_anchor,
            import_anchor + CORE_IMPORT + "\n",
            label="legacy Terrabot core primary-context import",
        )
    return _patch_call_agent(text)


def build_plan(repo_root: Path) -> list[PlannedFile]:
    root = repo_root.resolve()
    runner_path = root / RUNNER_RELATIVE
    core_loader_path = root / CORE_LOADER_RELATIVE
    router_runtime_path = root / ROUTER_RUNTIME_RELATIVE

    if not runner_path.is_file():
        raise InstallError(f"Required latest-workflow file not found: {runner_path}")
    if not core_loader_path.is_file():
        raise InstallError(f"Required Terrabot core file not found: {core_loader_path}")

    runner_before = _read_text(runner_path)
    runner_after = _patch_runner(runner_before)

    planned: list[PlannedFile] = []
    if runner_after != runner_before:
        planned.append(
            PlannedFile(
                runner_path,
                runner_after.encode("utf-8"),
                "wire Cursor prompt generation after immutable case derivation",
            )
        )

    if router_runtime_path.is_file():
        # Current modular layout: import once in the shared loader namespace,
        # then patch the part that owns call_agent.
        loader_before = _read_text(core_loader_path)
        loader_after = _patch_core_loader(loader_before)
        runtime_before = _read_text(router_runtime_path)
        runtime_after = _patch_call_agent(runtime_before)

        if loader_after != loader_before:
            planned.append(
                PlannedFile(
                    core_loader_path,
                    loader_after.encode("utf-8"),
                    "expose Terraform primary context to ordered core parts",
                )
            )
        if runtime_after != runtime_before:
            planned.append(
                PlannedFile(
                    router_runtime_path,
                    runtime_after.encode("utf-8"),
                    "attach Terraform primary context after repository-index context",
                )
            )
    else:
        # Legacy fallback: the same file owns imports and call_agent.
        core_before = _read_text(core_loader_path)
        core_after = _patch_legacy_core(core_before)
        if core_after != core_before:
            planned.append(
                PlannedFile(
                    core_loader_path,
                    core_after.encode("utf-8"),
                    "attach Terraform primary context in legacy monolithic core",
                )
            )

    bundle = _bundle_root()
    for source_relative, target_relative in COPY_MAP.items():
        source = bundle / source_relative
        if not source.is_file():
            raise InstallError(f"Bundle source file is missing: {source}")
        content = source.read_bytes()
        target = root / target_relative
        existing = target.read_bytes() if target.is_file() else None
        if existing != content:
            planned.append(
                PlannedFile(target, content, f"install {source_relative.as_posix()}")
            )

    return planned


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode if path.exists() else None
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temporary, mode)
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def apply_plan(plan: list[PlannedFile]) -> None:
    for item in plan:
        _atomic_write(item.path, item.content)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Safely add Cursor-backed prompt generation to Terrabot."
    )
    parser.add_argument("repo_root", type=Path, help="Path to the Terravsgithub repository root")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate anchors and show planned changes without writing files",
    )
    args = parser.parse_args(argv)

    try:
        plan = build_plan(args.repo_root)
    except InstallError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not plan:
        print("Terrabot Cursor testing integration is already up to date.")
        return 0

    action = "WOULD UPDATE" if args.check else "UPDATED"
    if not args.check:
        try:
            apply_plan(plan)
        except OSError as exc:
            print(f"ERROR: unable to write integration files: {exc}", file=sys.stderr)
            return 3

    root = args.repo_root.resolve()
    for item in plan:
        try:
            relative = item.path.resolve().relative_to(root)
        except ValueError:
            relative = item.path
        print(f"{action}: {relative} - {item.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
