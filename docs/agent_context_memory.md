# Long-term agent context memory, live-repo Q&A, and PR-aware grounding

This document describes the backend and Foundry-agent-configuration changes
that give Terrabot a durable, centralized memory of prior agent turns, a
Teams-side ability to answer infrastructure questions about the live
repository (matching what the VS Code extension already does for the open
workspace), and awareness of already-raised pull requests.

## 1. Why: the problem with "live repo head, every time"

Previously every Foundry agent call rebuilt its grounding context from the
live GitHub repository head. That is correct for anything that must be
verified as *currently true* (file contents, whether a resource exists,
current variable values), but it has two costs:

* **Redundant work** — the same module/environment/file is frequently
  re-fetched and re-sent on every turn of a long conversation.
* **No cross-user continuity** — two users working the same repository area
  (for example, both adding resources to `envs/prd/main.tf`) got no benefit
  from each other's Terrabot activity.

## 2. What was added

### 2.1 `shared_code/agent_memory_store.py` — the cached memory file

A new module that records every Foundry agent turn (prompt, files
searched/supplied, a summary of retrieved context, a summary of generated
code, and the agent's response) and lets later requests read it back as a
bounded context block.

* **Cached file**: a JSON Lines file is always written to
  (`TERRABOT_AGENT_MEMORY_CACHE_FILE`, default a temp-dir file) — this is the
  literal "cached file in between" that sits between the live repository and
  the agent.
* **Durable + centralized**: when Azure Table Storage is configured (reusing
  the same `TERRABOT_STATE_STORAGE_CONNECTION_STRING` /
  `TERRABOT_STATE_STORAGE_ACCOUNT_URL` settings already used for Teams
  workflow state), entries are also written there so the memory survives
  Azure Functions worker restarts/scale-out and is shared by every user, not
  just the worker instance that happened to serve a given request.
* **Two scopes per entry**:
  - `conversation:<id>` — this Teams conversation's own history.
  - `centralized:<cloud>:<repo_target>` — every user's history for the same
    cloud/repository area. This is what satisfies "maintain the centralized
    changes by users."

Key functions: `record_agent_turn(...)`, `get_conversation_memory_context(...)`,
`get_centralized_memory_context(...)`, `get_combined_memory_context(...)`,
`clear_conversation_memory(...)`.

### 2.2 Wiring into `shared_code/terrabot_service.py`

* `call_agent(...)` (the single choke point every Teams Foundry call goes
  through — chat, infrastructure generation, and validation reruns) now:
  1. Attaches `agent_memory_context` — the cached memory block — to the
     outgoing agent payload before compaction, so the agent can reuse
     context it (or another user, for the centralized scope) already
     retrieved instead of re-deriving everything from the live repository.
  2. After a successful response, records the turn back into
     `agent_memory_store` — prompt, files searched (extracted from the
     agent-input payload's `existing_pr_context` / `retrieved_*_context`
     entries), a summary of any files the agent generated/modified, and the
     response text. This appends the memory cache on *every* request/response
     pair, per the requirement.
* `_teams_plain_chat_reply(...)` (plain-language Teams chat) now builds and
  attaches three context blocks before calling the agent:
  - `repository_context` — live-repository evidence (see §2.3).
  - `pull_request_context` — related already-raised PRs (see §2.4).
  - `agent_memory_context` — cached memory for this conversation/cloud/repo.
  It then records its own turn into the memory cache the same way.

None of this changes VS Code's behavior — the VS Code extension continues to
supply the open workspace directly (`shared_code/vscode_bridge.py`).

### 2.3 `shared_code/repo_chat_context.py` — live-repo Q&A for Teams

Gives Teams the same "answer questions about the repository" ability VS Code
already has. It walks the GitHub git tree for the resolved cloud's repo,
scores files by keyword overlap with the question, fetches the best matches,
and returns a bounded context block plus the list of paths used (so that
list can be recorded into agent memory as "files searched").

### 2.4 `shared_code/pr_context.py` — pull-request-aware grounding

Lists open pull requests for a repository and ranks them against the current
prompt by keyword overlap (title, branch name, body). Used to:

* Let chat answers reference in-flight work ("PR #142 already adds a storage
  account for checkout in prd").
* Let infrastructure requests avoid proposing duplicate work.

`build_multi_repo_pr_context_block(...)` checks every configured cloud
repository when the cloud cannot be resolved from the question alone, so a
cloud-agnostic query can still find a relevant PR.

## 3. Foundry agent instruction changes

The repository's `foundry-agent-instructions` file is the source of truth
that gets pasted into the Foundry agent's system instructions in the Azure
AI Foundry portal. It has been updated (see the "TEAMS CONVERSATION CONTEXT"
section and the two new numbered rules immediately after it) to describe the
new payload keys so the agent uses them correctly:

- **Rule 8 — AGENT MEMORY CONTEXT**: explains `agent_memory_context` (the
  cached long-term memory block from `agent_memory_store`), and that it is
  always subordinate to live repository evidence for any claim about current
  state, but useful for continuity and "what has already been done"
  questions.
- **Rule 9 — REPOSITORY_CONTEXT AND PULL_REQUEST_CONTEXT**: explains the two
  Teams plain-chat evidence fields (`repository_context` from
  `repo_chat_context`, `pull_request_context` from `pr_context`), how to cite
  them, and that they do not change the chat-mode output contract (plain
  text only, never Terraform/files/branches/PRs from a chat question).
- **Rule 10 — RELATED_PULL_REQUESTS (duplicate-work check)**: explains the
  `related_pull_requests` field attached to infrastructure requests
  (creation, modification, and clarifications on the way to one), including
  drafts, and how the agent should surface it without blocking generation on
  its presence.
- **Rule 11 — INTERACTIVE RESOURCE RESOLUTION**: requires the agent to
  actually read every resource-related file in the resolved environment
  (not only the fixed main.tf/variables.tf/backend.tf/outputs.tf set) before
  asking anything, and to ask specific, evidence-backed clarifying questions
  naming the actual candidate resources/attributes it found — instead of a
  bare numbered file-target picker — whenever a modification request names
  a resource by description rather than an exact identifier. Also documents
  the `content_summary`/`relevance_score` fields attached to each candidate
  (see §5 below).
- **Rule 12 — NEVER RETURN A BARE REFUSAL**: forbids a "cannot safely ground
  exact names" style refusal when the selected file's content was already
  supplied; requires parsing named sub-blocks (e.g. WAF `rule` blocks) and
  asking a question that lists the actual identifiers found, and describes
  the backend's best-effort rescue safety net (see §6 below) as a fallback,
  not a substitute for asking well-formed questions in the first place.

## 4. Bug fix: AWS `global` environment resolving to `minidev`

`detect_explicit_aws_environment` in `shared_code/terrabot_service.py` only
recognized "global" when paired with "root" (`terraform/root/global`).
A prompt such as "disable mcp waf rules in dev_aws global" matched none of
the explicit environment checks (no `minidev`/`bolt`/standalone `dev` token),
so `resolve_aws_environment_path` fell through to its `terraform/dev_aws/
minidev` default — silently analyzing and proposing changes against the
wrong environment folder.

Fixed by adding an explicit `\bglobal\b` check (before the `minidev`/`bolt`/
`dev` checks) that resolves to `terraform/dev_aws/global` by default, or
`terraform/prod_aws/global` when the prompt also mentions "prod"/
"production". Regression tests: `tests/test_aws_environment_resolution.py`.

## 5. Fix: infra-target picker showed alphabetical files, not the relevant one

Once the environment resolved correctly (§4), the modification-target
picker could still fail the user: it showed the first several files in
whatever order the upstream matcher returned (often alphabetical —
`acm.tf, acm_pca.tf, awsconfig.tf, backend.tf, ...`) and never surfaced a
file like `waf.tf` that actually declared the resource the request was
about, because candidates were never re-sorted by relevance before being
truncated to a handful.

Fixed in `shared_code/terrabot_service.py`:
- The candidates list is re-sorted by a freshly computed relevance score
  (`_teams_semantic_candidate_score`) against the current prompt immediately
  before the API response is built, so the most relevant file is first
  regardless of how the upstream matcher ordered it.
- Each candidate now carries `content_summary` — a one-line, evidence-based
  description of what the file actually declares (`_teams_describe_tf_file_
  contents`, extracted from real `resource`/`data`/`module`/`variable`
  blocks in its content) — and `relevance_score`.
- `shared_code/teams_bot.py` renders the picker ordered by `relevance_score`
  when present, shows up to 15 candidates (previously a hard cap of 6) with
  each one's `content_summary`, and notes how many more exist beyond that
  cap.

Tests: `tests/test_infra_target_candidate_ranking.py`.

## 6. Rescuing bare "cannot safely ground exact names" refusals

Even after the environment/picker fixes above, a modification request could
still hit a dead end: the agent selects the correct file (e.g. `waf.tf`) but
refuses with something like *"Cannot safely disable MCP waf rules yet
because the exact MCP rule names are not grounded in the repository
evidence"* instead of asking the user to pick from the named
`rule { name = "..." }` blocks it already had in its context.

`shared_code/terrabot_service.py::call_agent` now includes a best-effort
rescue: if a reply looks like a bare grounding refusal (`_teams_looks_like_
grounding_refusal`) and the selected file's live content was part of the
same request (`_teams_extract_selected_file_contents`), the backend extracts
named rule/resource identifiers from that content
(`_teams_extract_candidate_rule_identifiers`) and rewrites the reply into a
clarification that names them (`_teams_build_grounding_rescue_reply`), e.g.
*"I found these candidates: `mcp-bot-control`, `mcp-rate-limit`,
`aws_wafv2_web_acl.mcp`. Which one(s) should be disabled?"* instead of a
dead end. This is a safety net only — `foundry-agent-instructions` rule 12
requires the agent to ask this kind of question itself rather than relying
on the backend to rewrite a refusal after the fact.

Once the user answers with a specific identifier and generation succeeds,
that turn is recorded into `agent_memory_store` exactly like any other
`call_agent` turn (see §2.2) — no extra wiring was needed, because memory
recording already happens for every reply, including the follow-up that
resolves a clarification. A later request mentioning the same resource area
(for example another "mcp waf" request in the same repository) will have
this resolution available via `agent_memory_context`.

**Known limitation**: the rescued reply is only what is returned to Teams;
the underlying Foundry conversation still has the agent's own original
refusal in its history (the rescue rewrites the outbound text after the
model call, not the model's own turn). A capable model should still connect
the user's next answer to the rescued question, but a stronger fix would
require intercepting before the conversation item is written, which needs
deeper changes to `_call_agent_base` than this pass makes.

Tests: `tests/test_grounding_refusal_rescue.py`.

## 7. Duplicate/related pull-request awareness for infrastructure requests

`shared_code/terrabot_service.py::handle_teams_chat_request` now wraps every
infra-generation-facing response (`infra_preview`, `clarification`,
`branch_created`) with `_teams_attach_related_pull_requests`, which looks up
open pull requests (via `shared_code/pr_context.py`, which returns drafts
too — GitHub's `state=open` includes draft PRs) on the resolved cloud's
repository and attaches the best keyword matches as `related_pull_requests`
/ `related_pull_requests_context`. `shared_code/teams_bot.py` renders these
as a "Related pull request(s) already raised" section, including whether
each match is a draft. This is informational only — Terrabot still proceeds
with the requested generation unless the user says otherwise. Tests:
`tests/test_related_pull_request_awareness.py`.

After editing `foundry-agent-instructions`, re-sync it to the live Foundry
agent's instructions field in the Azure AI Foundry portal (the file itself is
not read automatically by the deployed agent). No agent-side code change is
required beyond that: the new fields are additional JSON keys attached to
the same request payload the agent already parses.

## 8. Configuration reference

| Setting | Default | Purpose |
| --- | --- | --- |
| `TERRABOT_AGENT_MEMORY_CACHE_FILE` | `<tempdir>/terrabot-agent-memory-cache.jsonl` | Local JSON Lines cache file path. |
| `TERRABOT_AGENT_MEMORY_TABLE` | `TerrabotAgentMemory` | Azure Table Storage table name for durable/centralized memory. |
| `TERRABOT_AGENT_MEMORY_MAX_ENTRIES` | `40` | Max cached turns kept per conversation/centralized key. |
| `TERRABOT_AGENT_MEMORY_MAX_FIELD_CHARS` | `1500` | Max characters kept per memory field. |
| `TERRABOT_AGENT_MEMORY_MAX_CONTEXT_CHARS` | `12000` | Max characters in a single formatted memory context block. |
| `TERRABOT_AGENT_MEMORY_TTL_SECONDS` | `7776000` (90 days) | Expiry for durable Table Storage memory entries. |

Table Storage reuses the existing `TERRABOT_STATE_STORAGE_CONNECTION_STRING`
/ `TERRABOT_STATE_STORAGE_ACCOUNT_URL` settings; no new credentials are
required if Teams workflow state durability is already configured.

## 9. Testing

Pure-logic behavior for all three new modules is covered under `tests/`:

* `tests/test_agent_memory_store.py`
* `tests/test_pr_context.py`
* `tests/test_repo_chat_context.py`

These tests avoid real network/table-storage calls (monkeypatching the
GitHub-calling functions and forcing the Table Storage backend off) so they
run offline and deterministically.
