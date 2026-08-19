# Centralized Repository Context Layer

Terrabot uses Azure AI Search for durable repository-level knowledge shared by every user working on the same GitHub repository. This replaces the retired `agent_memory_store` conversation/table cache. Azure Table Storage remains in the application only for operational Teams workflow/GitHub-auth state; it is not used for repository context.

## Stored data

A context item is one durable repository conclusion with:

- repository owner/name;
- category, subject, scope, and statement;
- exact repository evidence paths/excerpts;
- evidence branch and commit SHA;
- confidence and validation status;
- active/conflicted/superseded/invalidated status;
- duplicate identity/statement hashes;
- explicit supersession/conflict links;
- source task hash (not the user prompt or conversation text);
- created/updated timestamps.

Allowed categories are architecture decisions, implementation decisions, coding conventions, repository constraints, component relationships, workflows/procedures, API/integration behavior, resolved repository clarifications, and important repository facts.

Conversation transcripts and conversation summaries are not stored.

## Storage and retrieval

The layer uses the same `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_KEY`, Azure OpenAI endpoint/key, and embedding deployment already used by Terrabot's Azure AI Search corpus. Repository context has a dedicated index because its lifecycle/version/conflict schema differs from code chunks.

Default index: `terrabot-repository-context` (override with `AZURE_SEARCH_REPOSITORY_CONTEXT_INDEX_NAME`). `shared_code/create_search_index.py` now creates/updates both the existing corpus index and the repository-context index.

Before a Foundry repository task, the backend searches by GitHub owner/repository and current prompt, attaches a bounded `shared_repository_context` block, and marks results stale when the current commit differs from the evidence commit. Live repository evidence always wins.

## Evidence validation

`add_repository_context` and `update_repository_context` require at least one exact repository excerpt. The backend fetches each cited path at the supplied evidence commit/branch and verifies the excerpt exists before indexing. Candidates below `TERRABOT_REPOSITORY_CONTEXT_MIN_CONFIDENCE` (default `0.75`) are rejected. Conversation-summary-like statements are rejected.

A duplicate with the same repository/category/subject/scope and same normalized statement refreshes its evidence/version rather than creating another copy. A different statement for the same identity is stored as an explicit conflict and the previous active record is marked conflicted. Explicit update creates a new record and marks the old one superseded. Invalidation preserves the record and changes its status instead of deleting history.

## Automatic post-task extraction

After a Teams Terraform change passes backend semantic/HCL/self-validation and is committed to a GitHub branch, the backend starts a fresh Foundry extraction call. Input includes:

- current user request;
- bounded clarification exchange;
- relevant final repository code at the committed SHA;
- generated/tool results;
- Git compare/diff;
- backend validation results and declared validation commands;
- existing repository context.

Foundry may return zero or more durable candidates. Every candidate is then independently verified against GitHub at the committed SHA before storage. Extraction failure never rolls back an otherwise successful infrastructure commit; Function App diagnostics identify the failure.

## Backend APIs

All routes use the existing `TERRABOT_API_TOKEN` check when configured.

- `POST /api/repository-context/search`
- `POST /api/repository-context/add`
- `POST /api/repository-context/update`
- `POST /api/repository-context/invalidate`
- `GET /api/repository-context/tools` (function-tool schemas)

## Function App logging

Repository context emits structured WARNING-level lines so they remain visible under common Azure Functions log filtering. Events are prefixed with `[TerrabotDiag]` and `event=repository_context_*`, including index initialization, search start/completion, stale/conflict counts, evidence validation, duplicate refresh, conflict creation, update, invalidation, extraction start/completion, and failures.

## Environment variables

Required by the existing search/embedding architecture:

- `AZURE_SEARCH_ENDPOINT`
- `AZURE_SEARCH_KEY`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_API_VERSION` (existing default `2024-02-01`)
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`
- `AZURE_OPENAI_EMBEDDING_DIMENSIONS` (must match the embedding model; default `1536`)

Repository-context options:

- `AZURE_SEARCH_REPOSITORY_CONTEXT_INDEX_NAME=terrabot-repository-context`
- `TERRABOT_REPOSITORY_CONTEXT_ENABLED=true`
- `TERRABOT_REPOSITORY_CONTEXT_AUTO_CREATE_INDEX=true`
- `TERRABOT_REPOSITORY_CONTEXT_MIN_CONFIDENCE=0.75`
- `TERRABOT_REPOSITORY_CONTEXT_TOP_K=8`
- `TERRABOT_REPOSITORY_CONTEXT_MAX_CHARS=12000`

No new Table Storage setting is required for repository context.
