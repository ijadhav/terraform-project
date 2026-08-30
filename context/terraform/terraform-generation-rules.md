# Terrabot primary Terraform generation rules

Concise, backend-loaded guidance for generating repository-aligned Terraform.
This is **primary context**, not ground truth. It is a compact summary of the
conventions in the live repositories; it exists to bias generation toward the
right files and patterns, never to override what the repository actually shows.

## Context precedence (highest wins)

1. **Live repository evidence** — the current file contents, tree, and matched
   files supplied in the request (`existing_pr_context`, `retrieved_value_context`,
   `retrieved_module_context`, live GitHub reads).
2. **Repository's own rules** — the target repo's `README.md`, module `README.md`,
   `.github/` (CODEOWNERS, PR template, `copilot-instructions.md`,
   `instructions/*.instructions.md`), `.cm/`, and `.Serena` if present.
3. **This primary Terraform context** (`context/terraform/*.md`).
4. **terrabot repository-context index** results (retrieval/grounding).
5. **Generic Foundry instructions**.

If this primary context disagrees with live repository evidence, **the live
repository always wins**. Treat this file as possibly stale: verify every path,
flag, module source, and variable name against the live files in the request.

## How to resolve repo and environment

- Resolve the **cloud** first (azure vs aws), then the **repo target**
  (`tf-azure-hub` for Azure hub consumer changes, `tf-devops` for AWS/DevOps),
  then the **environment/scope**.
- Environment names are hierarchical. A leaf scope (e.g. `npr-int`, `prd-us5`,
  `us1_dr`) belongs to a tier/account root (`npr`, `prd`, `sbx` for Azure;
  `dev_aws`, `prod_aws`, `statestreet` for AWS). Keep both the leaf and its
  parent when locating value files.
- Never invent an environment. Use only environments that exist in the live tree.

## Modifying an existing value or Boolean flag

- Boolean feature flags follow `create_<x>` (stateful/costly infra) and
  `enable_<x>` (app/service features), plus repo-specific families
  (e.g. `aca_app_<x>_enabled`).
- Route the edit by **exact ownership**: find the single live file that already
  contains the root assignment `<flag> = true|false` and change it in place.
  Do not add a second assignment, and do not pick a file merely because it is
  the environment's "obvious" file or the currently open editor.
- When the user names an explicit `.tf`/`.tfvars` path that exists in the
  request, that file is authoritative.
- Do not conflate related flags (e.g. `create_patch_management` is the patch
  management creation switch; `enable_pre_maintenance_event_grid` /
  `enable_post_maintenance_event_grid` are separate event-grid integrations).

## Modifying an existing resource

- Edit the live file that already owns the resource/module block. Preserve all
  existing content; return a targeted insert into the existing block rather than
  a regenerated whole file.

## Creating a new resource / new module consumer

- Find the nearest matching **sibling** resource in the same environment and
  reuse its exact module source/version, wiring, ingress/networking, naming, and
  input ordering. File placement is repository-answerable: add the new sibling to
  the file that already hosts the closest resource family.
- Declare new variables in the repo's variables file (see per-repo docs for the
  correct filename), and add concrete values to the correct environment value
  file. Give each new resource its own configuration root; never point a new
  resource at a pre-existing sibling's object variable.
- Missing **non-sensitive** values are not questions: reuse a grounded
  sibling/default, else emit a syntactically valid `__FILL__<input>__` token and
  matching `user_fillable` metadata. Only genuinely sensitive or blocking-ambiguous
  values may become questions.

## Validation

- Emit the repo-native validation commands the repository actually uses (see the
  per-repo docs). Common Azure: `terraform fmt`, `terraform_docs`,
  `terraform_tflint`, `terraform validate`, `pre-commit run --all-files`.
  Common AWS/DevOps: `terraform fmt -recursive -check`, `terraform validate`,
  Checkov. Do not invent validation steps a repo does not run.

## Hard rules

- Never copy or restate large raw repository contents; rely on the live evidence
  in the request.
- Never hardcode module sources, paths, flags, or environments that are not
  present in the live repository evidence.
- Preserve existing file content on every modification.
