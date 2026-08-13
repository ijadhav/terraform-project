from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

from terrabot_core.models import to_jsonable
from terrabot_core.scanner import scan_repository
from terrabot_core.service import ask_infrastructure, explain_workflow, scan_workspace
from terrabot_core.validator import run_validation_commands


def _print_json(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _print_plan_human(plan: Dict[str, Any], show_diff: bool = False, show_context_pack: bool = False) -> None:
    print(f"Terrabot status: {plan.get('status')}")
    print(plan.get("summary") or "")
    workflow = plan.get("workflow") or {}
    print("\nDetected workflow:")
    print(f"  type: {workflow.get('workflow_type')}")
    print(f"  confidence: {workflow.get('confidence')}")
    print(f"  cloud: {workflow.get('cloud')}")
    print(f"  resource_type: {workflow.get('resource_type')}")
    print(f"  target_environment: {workflow.get('target_environment')}")

    questions = plan.get("questions") or []
    if questions:
        print("\nQuestions before generation:")
        for question in questions:
            print(f"  - {question}")

    source_paths = plan.get("source_paths_used") or []
    if source_paths:
        print("\nSource files used:")
        for path in source_paths[:20]:
            print(f"  - {path}")

    commands = plan.get("validation_commands") or []
    if commands:
        print("\nRepo-native validation commands:")
        for command in commands:
            print(f"  - {command}")

    if show_diff:
        diff = plan.get("diff") or ""
        if diff:
            print("\nDiff:\n")
            print(diff)
        else:
            print("\nNo diff was generated yet.")

    if show_context_pack:
        print("\nContext pack:\n")
        print(json.dumps(plan.get("context_pack") or {}, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="terrabot", description="Repo-aware infrastructure assistant CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Scan the current repository and print repo/workflow context")
    scan.add_argument("--workspace", default=".", help="Workspace/repository root")
    scan.add_argument("--prompt", default="", help="Optional infrastructure prompt to guide workflow/evidence")
    scan.add_argument("--json", action="store_true", help="Print JSON output")

    explain = sub.add_parser("explain-workflow", help="Explain the inferred workflow for a prompt")
    explain.add_argument("--workspace", default=".", help="Workspace/repository root")
    explain.add_argument("prompt", nargs="*", help="Infrastructure prompt")
    explain.add_argument("--json", action="store_true", help="Print JSON output")

    ask = sub.add_parser("ask", help="Create a repo-aware infrastructure change plan")
    ask.add_argument("--workspace", default=".", help="Workspace/repository root")
    ask.add_argument("--json", action="store_true", help="Print JSON output")
    ask.add_argument("--diff", action="store_true", help="Print generated diff when available")
    ask.add_argument("--context-pack", action="store_true", help="Print the model context pack")
    ask.add_argument("prompt", nargs="+", help="Infrastructure request")

    validate = sub.add_parser("validate", help="Show or run repo-native validation commands")
    validate.add_argument("--workspace", default=".", help="Workspace/repository root")
    validate.add_argument("--run", action="store_true", help="Actually run allowlisted validation commands")
    validate.add_argument("--json", action="store_true", help="Print JSON output")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    workspace = str(Path(args.workspace).expanduser())

    try:
        if args.command == "scan":
            payload = scan_workspace(workspace, args.prompt)
            if args.json:
                _print_json(payload)
            else:
                profile = payload.get("repo_profile") or {}
                workflow = payload.get("workflow_profile") or {}
                print(f"Repository: {profile.get('repo_name')} ({profile.get('root')})")
                print(f"IaC tools: {', '.join(profile.get('iac_tools') or []) or 'none detected'}")
                print(f"Clouds: {', '.join(profile.get('clouds') or []) or 'unknown'}")
                print(f"Providers: {', '.join(profile.get('providers') or []) or 'none'}")
                print(f"Environments: {', '.join(profile.get('environments') or []) or 'none detected'}")
                print(f"Pipelines: {', '.join(profile.get('pipeline_files') or []) or 'none detected'}")
                print(f"Workflow: {workflow.get('workflow_type')} (confidence {workflow.get('confidence')})")
            return 0

        if args.command == "explain-workflow":
            prompt = " ".join(args.prompt).strip() or "Explain this repository workflow"
            payload = explain_workflow(workspace, prompt)
            if args.json:
                _print_json(payload)
            else:
                workflow = payload.get("workflow_profile") or {}
                print(f"Workflow: {workflow.get('workflow_type')}")
                print(f"Confidence: {workflow.get('confidence')}")
                print(f"Cloud: {workflow.get('cloud')}")
                print(f"Resource type: {workflow.get('resource_type')}")
                print(f"Environment: {workflow.get('target_environment')}")
                if workflow.get("questions"):
                    print("Questions:")
                    for question in workflow.get("questions") or []:
                        print(f"  - {question}")
                print("Evidence:")
                for item in payload.get("evidence") or []:
                    print(f"  - {item.get('path')}: {item.get('reason')}")
            return 0

        if args.command == "ask":
            prompt = " ".join(args.prompt).strip()
            plan = ask_infrastructure(workspace, prompt)
            if args.json:
                _print_json(plan)
            else:
                _print_plan_human(plan, show_diff=args.diff, show_context_pack=args.context_pack)
            return 0

        if args.command == "validate":
            profile = scan_repository(workspace)
            report = run_validation_commands(workspace, profile.validation_commands, run=args.run)
            payload = to_jsonable(report)
            if args.json:
                _print_json(payload)
            else:
                for run in payload.get("runs") or []:
                    status = "skipped" if run.get("skipped") else run.get("return_code")
                    print(f"{run.get('command')} -> {status}")
                    if run.get("reason"):
                        print(f"  {run.get('reason')}")
            return 0

    except Exception as exc:
        print(f"terrabot: {exc}", file=sys.stderr)
        return 1

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
