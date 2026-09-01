# Terraform repository analysis used by Terrabot

Analysis date: 2026-08-31  
Supplied snapshot branches: `vena-ishika/STO-9604/terrabot-test`

- `venasolutions/tf-devops`: snapshot commit `1a4115a7249ef82ca9fc642cda1eacfc012c2252`
- `venasolutions/tf-azure-hub`: snapshot commit `e2e12cb9f60f0e6a93e5443e250f85e75da381a7`

The resulting primary context is a stable authoring playbook, not a replacement for live GitHub. Terrabot and Cursor must always prefer the exact selected-commit files when they differ from this snapshot.

## Corrections to the original Copilot-generated context

The original context included several generic assumptions that are unsafe for these repositories:

1. **`tf-devops` uses `vars.tf`, not a universal `variables.tf`, for its runnable AWS roots and most local modules.** New code must follow the nearest scoped module/root, not rename legacy files.
2. **`tf-devops` uses literal per-root S3 backend configuration.** The proposed `${var.*}` backend templates are invalid because ordinary Terraform variables cannot be referenced in a backend block.
3. **`tf-azure-hub` is not organized as one Terraform root per environment.** It is a shared root whose environment values are composed from common, tier, hub, and optional DR tfvars files.
4. **`tf-azure-hub` uses a partial AzureRM backend in code and injects state details from its pipelines.** Terrabot must not create environment-local backend files.
5. **Provider/module versions must come from live HCL and pipeline files.** The generated root README in `tf-azure-hub` contains stale version examples.
6. **Apply behavior is repository/pipeline-specific.** `applyFromBranch` is enabled in some current pipelines, so Terrabot must not state that every production apply is always manual unless the live pipeline and Azure DevOps environment prove it.
7. **Neither supplied snapshot contains `.serena` or `.Serena`.** This is only a snapshot observation. Live commits must still be scanned for those paths.
8. **Legacy exceptions exist.** The primary context prevents broad cleanup of old direct module calls, incomplete module file sets, literal identifiers, or formatting while making an unrelated change.

## `tf-devops` findings

### Shape and scale

The snapshot is an AWS Terraform monorepo with Azure DevOps pipelines. It contains approximately:

- 820 Terraform files
- 82 first-level directories under `terraform/modules`
- 720 module blocks
- 1,621 resources
- 885 data sources
- 1,338 variable blocks
- 608 outputs
- 48 S3 backend blocks

Primary roots include `terraform/dev_aws`, `terraform/prod_aws`, `terraform/services_aws`, `terraform/dev_services_aws`, `terraform/network_services`, `terraform/root`, `terraform/datadog`, and `terraform/pagerduty`.

### Authoritative repository guidance

Terrabot must inspect the live versions of:

- root `README.md`
- `terraform/README.md`
- `.github/copilot-instructions.md`
- `.github/instructions/terraform-modules.instructions.md`
- `.github/instructions/hub-environments.instructions.md`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `.github/CODEOWNERS`
- relevant module READMEs
- `pipeline-templates/**`
- `.cm/gitstream.cm` for review automation only

### Hub design

- Each environment is a directory and an independent Terraform root; workspaces are not the environment boundary.
- Common root files are `backend.tf`, `versions.tf`, `main.tf`, `vars.tf`, and `outputs.tf`.
- The principal hub module is `vena_datacentre`.
- New hub capabilities normally belong inside `vena_datacentre` behind a Boolean gate.
- Approved direct satellite patterns currently include `vena_sqlstaging_peering` and `patch_management`.
- Existing direct `otel_collector`, `otel_collector_daemon`, and `file_metrics` patterns are technical debt to preserve, not patterns to extend.
- Optional app/feature controls usually use `enable_*`; stateful or costly creation controls usually use `create_*`.
- DR roots use `_dr`, alternate region/network values, `is_dr_region = true`, reduced cost-heavy controls, and production tagging appropriate to a DR copy.

### Modules

The intended new-module shape is `main.tf`, `vars.tf`, `outputs.tf`, and `versions.tf`, with typed/described inputs. Some legacy modules do not have the full set, so this rule applies to new modules and active refactors rather than causing unrelated bulk changes.

Most module sources are relative paths. Existing pinned external exceptions must be preserved exactly. Terrabot must clone the nearest verified caller/module structure rather than substitute a generic module skeleton.

### Backend and state

Runnable roots contain literal S3 backend values. Terrabot must copy the nearest sibling convention and create a unique state key only when the user explicitly requests a new root. No repository-wide DynamoDB lock-table convention was observed in the supplied snapshot, so one must not be invented.

### Pipeline behavior

Root `azure-pipelines_*.yml` files delegate to `pipeline-templates/tf-stages.yml`. The current workflow includes recursive formatting, Checkov, Terraform init/validate/plan, sanitized plan JSON/text artifacts, and pipeline-specific apply conditions. Plan output is sanitized because it may contain sensitive values. Exact live pipeline settings and Azure DevOps environment approvals take precedence over generic policy statements.

## `tf-azure-hub` findings

### Shape and scale

This repository is a large shared Azure Terraform root plus an isolated `monitoring/dd_monitors` root. The supplied snapshot contains approximately:

- 38 Terraform files
- 16 tfvars files
- 38 module blocks
- 138 resources
- 41 data sources
- 345 variables
- 15 outputs

Most Azure modules are pinned Git SSH sources. The local `modules/datadog` directory is a legacy special case and must not be generalized as the normal module structure.

### Environment value layering

The pipelines compose values in this order:

1. `vars/common.tfvars`
2. `vars/<tier>/tier.tfvars`
3. `vars/<tier>/<hub>/hub.tfvars`
4. optional `vars/<tier>/<hub>/dr.tfvars`

Current examples include NPR `npr-int`, sandbox `sbx-infra`, and production hubs `prd-us5`, `prd-ca4`, `prd-eu3`, and `prd-us6`. The exact live tree determines valid environments.

### Provider/backend behavior

- `provider.tf` is the current source of provider constraints.
- Terraform is currently aligned to 1.11.4.
- AzureRM has a repository-specific upper bound associated with a regression comment; preserve it until the live file changes.
- The root backend is partial: `backend "azurerm"` with AAD authentication. Pipeline templates supply resource group, storage account, container, and state-key details.
- Multiple provider aliases and cross-subscription providers are part of the design and must be copied from the nearest sibling.
- CloudAMQP credentials are obtained through the existing ephemeral Key Vault secret pattern.

### Resource placement

Resources and module consumers are split by concern at the repository root, for example `aca_apps.tf`, `aca_env.tf`, `storage_accounts.tf`, `db_mysql.tf`, `key_vault.tf`, `rbac.tf`, and `vnet.tf`.

For Azure Container Apps:

- `aca_apps.tf` defines the application map and `container_app_enabled` gates.
- `aca_env.tf` passes the filtered application map to the pinned ACA module and wires diagnostics/RBAC.
- Enabling an existing app in one environment should normally be a surgical change in the most specific hub tfvars file.
- Creating a new app may require the map entry, Boolean variable, environment override only where needed, and verified sibling-based RBAC/secret wiring.

For object-backed families such as storage accounts:

- create a dedicated typed object variable in `variables.tf`;
- use that object from the consumer module block;
- add concrete literal values to the exact target tfvars file;
- preserve the nearest sibling's field shape, source ref, ordering, tags, and provider aliases;
- never make one tfvars object reference another.

### Pipeline behavior

`pipelines/azure-pipelines-npr.yml` and `pipelines/azure-pipelines-prd.yml` use `venasolutions/ado-pipeline-templates` at a pinned tag. The current NPR flow enables branch apply; PRD behavior must be read from the live template and Azure DevOps environment. The isolated monitoring root has separate state/provider behavior and must not be treated as a normal hub value change.

### Documentation exceptions

The root README is generated with terraform-docs and is not reliable for current version truth. Live `provider.tf`, `.tool-versions`, module source refs, pipeline files, and HCL interfaces win.

## Pull-request and review conventions

Both snapshots contain `.github/PULL_REQUEST_TEMPLATE.md`. Terrabot must use the live template as the PR body skeleton and preserve the current Jira/title convention. `CODEOWNERS` and `.cm/gitstream.cm` affect review/label behavior but do not replace Terraform design evidence.

## Resulting authority order

For every Terrabot task:

1. exact live selected-commit Terraform, tfvars, pipeline, README, `.github`, and `.serena/.Serena` evidence;
2. `terrabot_terraform_primary_context.yaml` for stable structure, conventions, and known exceptions;
3. validated repository-index context for prior mappings and clarifications, revalidated against the live commit.
