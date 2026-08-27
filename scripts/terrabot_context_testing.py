"""Local/Cursor entrypoint for Terrabot repository-context automated tests.

Examples:
    python3 scripts/terrabot_context_testing.py run --mode exploration --cloud all --count 8 --aad-object-id <id>
    python3 scripts/terrabot_context_testing.py run --mode context-regression --cloud aws --count 6 --aad-object-id <id>

This invokes the same queued-worker implementation synchronously for local
engineering/debugging. It does not create pull requests; the underlying runner
keeps its existing isolated test-branch behavior.
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid

from dotenv import load_dotenv

load_dotenv()

from shared_code import terrabot_service as core
from shared_code.automated_tests.terrabot_test_runner import execute_automated_test_job
from shared_code.automated_tests import terrabot_test_state


def _run(args: argparse.Namespace) -> int:
    aad_object_id = str(args.aad_object_id or os.getenv("TERRABOT_TEST_RUNNER_LOCAL_AAD_OBJECT_ID") or "").strip()
    if not aad_object_id:
        raise SystemExit("Pass --aad-object-id or set TERRABOT_TEST_RUNNER_LOCAL_AAD_OBJECT_ID.")
    command = f"run tests {args.mode} {args.cloud} {args.count}"
    run_id = "local-ctx-" + uuid.uuid4().hex[:10]
    report = execute_automated_test_job(
        core,
        {
            "run_id": run_id,
            "prompt": command,
            "aad_object_id": aad_object_id,
            "requester_hash": terrabot_test_state.requester_hash(aad_object_id),
            "cloud_filter": args.cloud,
            "run_mode": args.mode,
            "requested_cases": args.count,
            "conversation_reference": {},
            "created_at": terrabot_test_state.utc_now(),
        },
    )
    print(report)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Terrabot repository-context test workflow")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run the real Terrabot E2E automated-test worker locally")
    run.add_argument("--mode", choices=["regression", "exploration", "context-regression", "mixed"], default="regression")
    run.add_argument("--cloud", choices=["aws", "azure", "all"], default="all")
    run.add_argument("--count", type=int, default=8)
    run.add_argument("--aad-object-id", default="")
    run.set_defaults(func=_run)
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
