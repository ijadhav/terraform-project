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

## 6. Rescuing bare "cannot safely ground exact names" refusals (guaranteed, never a dead end)

Even after the environment/picker fixes above, a modification request could
still hit a dead end: the agent selects the correct file (e.g. `waf.tf`) but
refuses with something like *"Cannot safely disable MCP waf rules yet
because the exact MCP rule identifiers are not grounded in the repository
evidence"* instead of asking the user to pick from the parameters it
already had in its context.

`shared_code/terrabot_service.py::call_agent` includes a rescue that now
**guarantees** the user is never left with this bare refusal:

1. `_teams_looks_like_grounding_refusal` detects the refusal shape.
2. File content is recovered two ways: `_teams_extract_selected_file_
   contents` first (entries explicitly marked "selected"), then
   `_teams_extract_any_file_contents` as a broader fallback that recovers
   content from **any** file-like entry in the payload — including plain
   `candidates` list entries that were never marked "selected" (this is the
   fix for the case where the picker's candidate list did not carry a
   `selection_state`).
3. `_teams_extract_candidate_rule_identifiers` understands "rule" the way
   this repository actually uses it — **primarily a Boolean parameter/flag**
   (`name = true` / `name = false`), per explicit product guidance, ranked
   by overlap with the request's own wording (a request about "mcp waf"
   surfaces `mcp_waf_bot_control_enabled` ahead of an unrelated flag in the
   same file) — and only falls back to nested `rule { name = "..." }` blocks
   or bare `resource`/`data` declarations when no Boolean parameters are
   found.
4. If named identifiers were found, `_teams_build_grounding_rescue_reply`
   asks the user to pick among them, e.g. *"I found these candidates:
   `mcp_waf_bot_control_enabled`, `mcp_rate_limit_enabled`. Which one(s)
   should be set to `false`?"*
5. **If nothing could be extracted at all**, `_teams_build_generic_
   clarification_reply` still returns an interactive question instead of the
   refusal — this is the guarantee: the user is never shown the bare
   "cannot safely"/"not grounded" text again, worst case they get a generic
   "please name the specific rule/parameter" question instead.

This is a safety net; `foundry-agent-instructions` rules 12–13 require the
agent to ask this kind of question itself (and to understand "rule" as a
Boolean parameter first) rather than relying on the backend to rewrite a
refusal after the fact.

Once the user answers with a specific identifier and generation succeeds,
that turn is recorded into `agent_memory_store` exactly like any other
`call_agent` turn (see §2.2), now additionally tagged with `topic_tags`
(e.g. `["waf", "mcp", "disable"]`) extracted from the prompt/response. A
later request mentioning the same topic (e.g. another "mcp waf" question)
is retrieved by topical relevance, not just recency — see §2.2's
`get_combined_memory_context(..., prompt=...)` — so the resolution "waf mcp
rules → `mcp_waf_bot_control_enabled`" surfaces even if unrelated requests
happened in between.

**Known limitation**: the rescued reply is only what is returned to Teams;
the underlying Foundry conversation still has the agent's own original
refusal in its history (the rescue rewrites the outbound text after the
model call, not the model's own turn). A capable model should still connect
the user's next answer to the rescued question, but a stronger fix would
require intercepting before the conversation item is written, which needs
deeper changes to `_call_agent_base` than this pass makes.

Tests: `tests/test_grounding_refusal_rescue.py`.

## 7. Duplicate/related pull-request awareness for infrastructure requests (always checked)

`shared_code/terrabot_service.py::handle_teams_chat_request` wraps every
infra-generation-facing response with `_teams_attach_related_pull_requests`,
which looks up open pull requests (via `shared_code/pr_context.py`, which
returns drafts too — GitHub's `state=open` includes draft PRs) on the
resolved cloud's repository and attaches the best keyword matches as
`related_pull_requests` / `related_pull_requests_context`.

The trigger condition is intentionally broad — not a fixed mode whitelist —
so the check always runs whenever the request is infrastructure-flavored:

```python
is_infra_flavored = (
    mode in {"infra_preview", "clarification", "branch_created"}
    or decision_state in {
        "infra_modification_target_selection", "aws_module_selection", "azure_module_branch_selection",
    }
    or router_request_type == "infra"
)
```

`shared_code/teams_bot.py` renders matches as a "Related pull request(s)
already raised" section, including whether each match is a draft. This is
informational only — Terrabot still proceeds with the requested generation
unless the user says otherwise. `foundry-agent-instructions` rule 14 tells
the agent to always mention `related_pull_requests` when present, including
drafts, and to re-check once the cloud/repo is resolved if it was not
supplied on an earlier turn.

If a duplicate/draft PR still is not detected for a request that clearly has
one, use the `TEAMS-PR-CHECK-*` log lines (see §10) to see exactly why: no
repository resolved for the cloud, no prompt available, zero open PRs
returned from GitHub (check `pr_context: fetched N pull request(s)` — zero
here usually means a token/permissions/repo-name problem, not a matching
problem), or zero matched despite PRs being fetched (a genuine keyword-
overlap miss — compare the logged `prompt_tokens` against the PR's actual
title/branch text).

Tests: `tests/test_related_pull_request_awareness.py`.

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

Pure-logic behavior for all new modules/fixes is covered under `tests/`:

* `tests/test_agent_memory_store.py`
* `tests/test_pr_context.py`
* `tests/test_repo_chat_context.py`
* `tests/test_aws_environment_resolution.py`
* `tests/test_infra_target_candidate_ranking.py`
* `tests/test_grounding_refusal_rescue.py`
* `tests/test_related_pull_request_awareness.py`

These tests avoid real network/table-storage calls (monkeypatching the
GitHub-calling functions and forcing the Table Storage backend off) so they
run offline and deterministically.

## 10. Logging reference (for debugging this workflow in production)

Every new subsystem added by this workflow logs at INFO level (WARNING/
ERROR for failures) with a distinct, greppable prefix, alongside the
pre-existing `TEAMS-DIAG-*` transport-layer logs in `shared_code/teams_bot.py`
and the existing generation/validation logs elsewhere in
`shared_code/terrabot_service.py`. Grep any Function App log stream for
these prefixes to trace one request end-to-end:

| Prefix | Where | What it tells you |
| --- | --- | --- |
| `TEAMS-AGENT-CALL-1/2/3/RETRY/ERROR` | `terrabot_service.call_agent` | Every prompt sent to the Foundry agent and the reply received, including a byte count, a preview of both, whether the reply looks like a bare refusal, and whether a rescue (see below) was applied. |
| `TEAMS-MEMORY-1/2/3/ERROR` | `terrabot_service._teams_attach_agent_memory_context` / `_teams_record_agent_memory_turn` | Whether cached memory was found and attached before a call, and confirmation (with topic tags) after a turn is recorded. |
| `agent_memory: recorded turn ...` / `agent_memory: ... context lookup ...` | `shared_code/agent_memory_store.py` | Low-level cache reads/writes: which key, how many entries, whether relevance-ranking was used, resulting character count. |
| `TEAMS-RESCUE-1/2/3/4/ERROR` | `terrabot_service._teams_maybe_rescue_grounding_refusal` | When a bare refusal was detected, which file-recovery mode succeeded (`selected` vs `any-file-fallback`), which files were recovered, and whether named identifiers were found or the generic fallback question was used instead. |
| `TEAMS-PR-CHECK-TRIGGER/SKIP/ERROR` | `terrabot_service.handle_teams_chat_request` / `_teams_attach_related_pull_requests` | Whether the duplicate/related-PR check ran for this response, and why it was skipped when it was (missing prompt, unresolved cloud, or the response was not infra-flavored). |
| `pr_context: searching/fetched/matched/found/no related` | `shared_code/pr_context.py` | The actual GitHub call outcome: how many open PRs were fetched (zero here usually means a token/permissions/repo-name problem), how many matched the prompt by keyword overlap, and the final PR numbers/draft flags. |
| `repo_chat_context: searching/listed/candidate/fetched/no file` | `shared_code/repo_chat_context.py` | Live-repository Q&A evidence gathering for Teams plain-language questions: tree size scanned, which paths matched by keyword, which files were actually fetched. |

Example trace for one "disable mcp waf rules" request:

```
TEAMS-AGENT-CALL-1[...]: sending prompt to Foundry agent ... effective_prompt='disable mcp waf rules in dev_aws global'
TEAMS-MEMORY-1: no cached agent memory available for conversation=... cloud=aws repo_target=tf-devops
TEAMS-AGENT-CALL-2[...]: Foundry agent responded ... looks_like_refusal=True
TEAMS-RESCUE-2: grounding refusal detected, attempting rescue ... extraction_mode=any-file-fallback files_recovered=['terraform/dev_aws/global/waf.tf']
TEAMS-RESCUE-3: rescued refusal with named identifiers from recovered file content.
TEAMS-MEMORY-3: recorded agent turn to memory cache ... topic_tags=['disable', 'mcp', 'waf', 'rules', 'dev_aws', 'global']
TEAMS-PR-CHECK-TRIGGER: checking for a related/duplicate pull request mode=clarification ...
pr_context: searching for pull requests repo=venasolutions/tf-devops state=open token_configured=True
pr_context: fetched 12 pull request(s) for venasolutions/tf-devops (3 draft)
pr_context: matched 1 of 12 pull request(s) against prompt_tokens=[...] (best_score=26)
TEAMS-PR-CHECK: found 1 related pull request(s) (including drafts) ... numbers=[142] draft_flags=[True]
```
