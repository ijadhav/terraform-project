"""Manual smoke test for live PR + repository chat context (no mocking).

Run this where GITHUB_TOKEN, GITHUB_OWNER, GITHUB_AWS_REPO, and/or
GITHUB_AZURE_REPO are set (local .env, or the deployed Function App), e.g.:

    python3 scripts/test_live_pr_and_repo_context.py "has anyone added a storage account for checkout?" azure

It prints exactly what would be attached to the Foundry agent payload as
`pull_request_context` and `repository_context` for a real question, so you
can confirm both features are actually reaching real GitHub data.
"""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()

from shared_code import pr_context
from shared_code import repo_chat_context


def run_suite() -> int:
    """Run the automated live Terrabot test suite and print ONE aggregated result.

    This reuses the same live-context framework as the smoke check below; it
    constructs prompts from the current live Terraform in tf-devops/tf-azure-hub,
    verifies each target at HEAD, runs each case through the real backend
    workflow, aggregates independent per-case results, and (best effort) sends a
    single aggregated message to the requesting user's Teams chat.
    """
    from shared_code import live_test_runner

    summary = live_test_runner.run_suite()
    print(summary["teams_summary"])

    # Optional Teams delivery from a standalone run. Identity is never hardcoded:
    # it is taken from the requester's own conversation reference/id supplied via
    # environment (the Teams-triggered path uses the live turn identity instead).
    try:
        from shared_code import teams_bot

        conversation_id = os.getenv("TERRABOT_TEST_TEAMS_CONVERSATION_ID", "").strip()
        sender = teams_bot.send_proactive_teams_message
        if conversation_id and callable(sender):
            delivered = sender(conversation_id, summary["teams_summary"])
            print(f"\nTeams delivery attempted: {delivered}")
        else:
            print(
                "\nTeams delivery skipped (standalone run). Trigger 'run terrabot tests' "
                "from Teams to receive the aggregated result in your chat, or set "
                "TERRABOT_TEST_TEAMS_CONVERSATION_ID with bot credentials configured."
            )
    except Exception as exc:  # pragma: no cover - delivery is best effort
        print(f"\nTeams delivery unavailable: {exc}")

    return 0 if summary["failed"] == 0 else 1


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in {"--run-suite", "run-suite", "suite"}:
        raise SystemExit(run_suite())

    prompt = sys.argv[1] if len(sys.argv) > 1 else "has anyone already added a storage account for checkout?"
    cloud = sys.argv[2] if len(sys.argv) > 2 else "azure"

    token = os.getenv("GITHUB_TOKEN")
    owner = os.getenv("GITHUB_OWNER")
    repo = os.getenv("GITHUB_AWS_REPO") if cloud == "aws" else os.getenv("GITHUB_AZURE_REPO")
    branch = os.getenv("GITHUB_AWS_BASE_BRANCH", "main") if cloud == "aws" else os.getenv("GITHUB_AZURE_BASE_BRANCH", "main")

    print(f"owner={owner!r} repo={repo!r} branch={branch!r} token_set={bool(token)}")
    if not (owner and repo):
        print("Missing GITHUB_OWNER / repo env var for this cloud; nothing to query.")
        return

    print("\n=== Pull request context ===")
    pr_result = pr_context.build_pr_context_block(prompt, owner, repo, token=token, cloud=cloud)
    print(f"matched {len(pr_result['matches'])} pull request(s)")
    print(pr_result["context_block"] or "(empty — no related open PR found)")

    print("\n=== Live repository context ===")
    repo_result = repo_chat_context.build_live_repo_chat_context(prompt, owner, repo, branch=branch, token=token)
    print(f"fetched {len(repo_result['paths'])} file(s): {repo_result['paths']}")
    print((repo_result["context_block"] or "(empty — no matching file found)")[:2000])


if __name__ == "__main__":
    main()
