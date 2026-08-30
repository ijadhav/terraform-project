# Primary context: `tf-azure-hub` (Azure hub consumer)

Azure hub infrastructure (`provider "azurerm"`). This is the repo Terrabot edits
for Azure consumer changes (`repo_target = tf-azure-hub`). Verify every fact
below against the live files supplied in the request; the live repo wins.

## Layout

- **Single root module at repo root**: ~30 domain `.tf` files (`main.tf`,
  `vnet.tf`, `aca_apps.tf`, `aca_env.tf`, `sql_staging.tf`,
  `maintenance_configuration.tf`, `key_vault.tf`, `storage_accounts.tf`, …).
- **Variables are declared in `variables.tf`** (not `vars.tf`).
- **No local `modules/` directory** — all modules are external Git sources.
- Separate Terraform root for Datadog monitors under `monitoring/dd_monitors/`.

## Environment / value resolution

Values live under `vars/` and are layered by the pipelines in this order:
`vars/common.tfvars` → `vars/<tier>/tier.tfvars` → `vars/<tier>/<scope>/hub.tfvars`
(DR adds `vars/<tier>/<scope>/dr.tfvars` and uses separate `tf-azure-hub-dr` state).

- **Tiers**: `npr`, `sbx`, `prd` (each has `tier.tfvars`).
- **Scopes** (folder = subscription/hub identity):
  - `npr`: `npr-int`, `npr-stg`
  - `sbx`: `sbx-infra`
  - `prd`: `prd-us5`, `prd-us6`, `prd-ca4`, `prd-eu3`
- `common.tfvars` holds shared defaults (storage objects, ACA app defaults,
  MySQL configs). `tier.tfvars` holds tier identity/defaults
  (`infra_devops`, patch/event-grid defaults, `create_cloudamqp`, Kusto).
  `hub.tfvars` holds hub identity (`hub_name`, `location`,
  `resource_group_name`, subnet CIDRs, `is_primary_hub`). `dr.tfvars` mostly
  flips `create_*` to `false`.
- `subscription_type` (`npr`/`sbx`/`prd`) drives naming but is **injected at
  apply time** by the pipeline (`type:` param), not stored in checked-in tfvars.

## Modules (external Git, pinned by tag)

- Pattern: `source = "git@github.com:venasolutions/<repo>.git?ref=vX.Y.Z"`,
  usually gated with `count = var.create_<x> ? 1 : 0`.
- Real examples (verify in live files):
  - `vnet.tf`: `git@github.com:venasolutions/tf-azure-vnet.git?ref=v5.0.3`.
  - `maintenance_configuration.tf`:
    `git@github.com:venasolutions/tf-azure-patch-mgmt.git?ref=v2.5.4`,
    gated by `create_patch_management`.
  - `aca_env.tf`:
    `git@github.com:venasolutions/tf-azure-container-apps.git?ref=v1.1.6`.
- **New consumer of an existing module**: (1) declare inputs in `variables.tf`,
  (2) add the `module` block in the correct domain `.tf` file with a `create_*`
  gate, (3) add defaults to `common.tfvars` and overrides in the correct
  `tier.tfvars` / `hub.tfvars`, DR disables in `dr.tfvars`. Reuse the exact
  module source/tag of the nearest sibling. Do **not** create a new consumer
  `.tf` file for a source-matched existing module.

## Boolean feature flags (declared in `variables.tf`, assigned in tfvars)

- `create_*`: `create_patch_management`, `create_cloudamqp`, `create_adf`,
  `create_key_vault`, `create_apim`, `create_app_gateway`, `create_sql_db`,
  `create_backup_vault`, `create_kusto_cluster`, `create_asgs`, …
- `enable_*`: `enable_kubernetes`, `enable_pre_maintenance_event_grid`,
  `enable_post_maintenance_event_grid`,
  `enable_storage_account_object_replication`,
  `enable_request_smuggling_protection`, …
- `aca_app_<x>_enabled`: `aca_app_nginx_enabled`, `aca_app_workflow_engine_enabled`,
  `aca_app_auth_service_enabled`, `aca_app_vena_copilot_enabled`, …
- Change a flag in the exact tfvars file that already owns its root assignment
  (often `tier.tfvars` for tier-wide flags, `hub.tfvars` for hub-scoped ones,
  `common.tfvars` for defaults). Resources are gated via
  `count = var.<flag> ? 1 : 0`.

## Variables / tfvars patterns

- Single `variables.tf` with section headers; `snake_case` names.
- Object-backed vars accessed as `var.<object>.<field>`
  (e.g. `storage_account_zrs`, `app_mysql_db_config`, `azurerm_kusto_cluster`).
- `map(object)` vars used with `for_each` (e.g. `eventhubs`, `dns_zones_for_link`).
- Default tags include `ManagedBy = "Terraform"` and the repo `GithubRepo` URL;
  Vanta tags (`VantaNonProd`, conditional `VantaContainsUserData`) merged in `main.tf`.

## Providers / versions / backend

- `provider.tf`: `required_version >= 1.11.4`; `azurerm >= 4.3.0, < 4.77.0`
  (upper bound is intentional); plus `azuread`, `random`, `github`, `cloudamqp`,
  `kubernetes`, `helm`, `azapi`, `null`, `local`, `tls`. Multiple `azurerm`
  aliases (`management_sub`, `infradevops_sub`, `insights_sub`, `global_sub`, …).
- Backend: `azurerm` with `use_azuread_auth = true` (bucket/key set at init).
- Terraform pinned to `1.11.4` (`.tool-values`/pipelines).

## Validation

- Pre-commit (`.pre-commit-config.yaml`) hooks: `terraform_fmt`,
  `terraform_docs`, `terraform_tflint`.
- ADO pipelines (`pipelines/azure-pipelines-{npr,prd}.yml`) run an external
  `terraform/tf-code-checks-template.yml@ADOPipelineTemplates` for code checks
  and `azure-tf-stages-template.yml` for plan/apply.
- Suggested validation commands to emit: `terraform fmt`, `terraform validate`,
  `tflint`, `pre-commit run --all-files`.

## Repo-specific exceptions

- CODEOWNERS: `*` → `@venasolutions/saaseng-team`; `.github/`, `.cm/` →
  `@venasolutions/tooling-team`.
- PR template requires a JIRA link and risk-assessment labels; `.cm/gitstream.cm`
  enforces a `VDP|PO|STO-\d+` JIRA reference in branch/description.
- Some modules carry `#checkov:skip=CKV_TF_1`. No `.Serena`, no `CLAUDE.md`.
