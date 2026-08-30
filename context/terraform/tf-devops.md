# Primary context: `tf-devops` (AWS + DevOps)

AWS infrastructure and DevOps pipelines (`provider "aws"`). This is the repo
Terrabot edits for AWS changes (`repo_target = tf-devops`). Verify every fact
below against the live files supplied in the request; the live repo wins.

## Layout

```
terraform/
  modules/          # ~50+ reusable LOCAL modules (source = ../../modules/<name>)
  dev_aws/          # NPR account hubs
  prod_aws/         # PRD account hubs
  statestreet/      # private hub account
  datadog/ pagerduty/ root/ audit/ logarchive/ defaults/ scripts/ ...
pipeline-templates/ # CI templates (tf-code-checks.yml, tf-stages.yml, ...)
azure-pipelines_*.yml
```

- Each hub environment directory is a **self-contained Terraform root**
  (`backend.tf`, `versions.tf`, `main.tf`, `outputs.tf`, sometimes `provider.tf`).
- **Modules use `vars.tf`** (never `variables.tf`) with mandatory `description`
  and `type` on every variable; module files: `main.tf`, `vars.tf`, `outputs.tf`,
  `versions.tf`.

## Environment / value resolution

- **Environments are directories, not workspaces**, and config is **inline** in
  each env `main.tf` (`locals {}` block: `env`, `subdomain`, `region`,
  `network_base`, `source_account_id`) plus module arguments. There are **no
  tfvars files**.
- `dev_aws/` env dirs include: `dev`, `dev_devops`, `bolt`, `bolt_dr`,
  `minidev`, `global`, `observe`, `*_sqlstaging`.
- `prod_aws/` env dirs include: `us1`–`us4` (+ `_dr`), `eu1/eu2/eu4` (+ `_dr`),
  `ca3`/`ca3_dr`, `devops`, `global`, `observe`, `sqlstaging*`.
- Directory suffix conventions: hub = `dev`/`us1`/`bolt`; DR = `{hub}_dr`;
  SQL staging = `{hub}_sqlstaging`; account-global = `global`; DevOps tooling =
  `dev_devops`/`devops`.
- State: per-env S3 key in each `backend.tf` (e.g. `us1/terraform.tfstate`).

## Modules (local only)

- Always `source = "../../modules/<name>"` — never registry, never Git.
- **`vena_datacentre`** is the root hub module and must be the first/primary
  module in every hub `main.tf`. Approved siblings alongside it include
  `vena_sqlstaging_peering` and `patch_management`.
- Real examples (verify in live files):
  - `terraform/dev_aws/dev/main.tf`: `module "vena_datacentre"` with
    `source = "../../modules/vena_datacentre"`, inputs `env`, `subdomain`,
    `region`, `private_subnets`, `create_subdomain_dns`, `enable_ai_chat_service_ecs`.
  - `patch_management`: `source = "../../modules/patch_management"`.
  - `vena_sqlstaging_peering`: wires
    `private_route_tables = module.vena_datacentre.private_subnet_rtbs`.
- **New hub functionality goes INSIDE `vena_datacentre`** (add a sub-module +
  `create_*`/`enable_*` flag), **not** as a new top-level sibling module in the
  hub `main.tf`. This is an explicit anti-pattern in
  `.github/instructions/hub-environments.instructions.md`.
- **AWS clone/mirror**: when the user asks to create a new module by mirroring an
  existing one, treat the existing module as a read-only template and generate
  both the new module implementation directory and its consumer invocation.

## Boolean feature flags (module arguments in hub `main.tf`)

- `create_*` (stateful/costly): `create_staging_redshift`, `create_mtserver_rds`,
  `create_subdomain_dns`, `create_venacloud_presentation_bucket`, `create_bucketav`.
- `enable_*` (ECS services / app features): `enable_ai_chat_service_ecs`,
  `enable_workflow_engine_ecs`, `enable_homepage_bff_ecs`, `enable_kinesis_alarms_*`.
  Declared in `terraform/modules/vena_datacentre/vars.tf`.
- `is_dr_region = true` in `*_dr/main.tf` suppresses non-essential resources; DR
  dirs also set `create_* = false` for most stateful infra.
- Change a flag by editing the **module argument in the specific hub env
  `main.tf`** that owns it (no tfvars in this repo).

## Variables / patterns

- Hub config is inline `locals {}` + module args; modules declare inputs in
  `vars.tf` with `description` + `type`.
- No hardcoded ARNs — use data sources (`data.aws_ssm_parameter`,
  `data.aws_kms_key`, …). KMS encryption required on supported resources.
- Tags on hub modules: `Hub`, `Environment`, `Region`, `ManagedBy`.

## Providers / versions / backend

- `versions.tf`: `required_version >= 1.11.4`; `aws ~> 5.34.0`.
- Backend: `s3` with `encrypt = true`; bucket/key per environment.
- Separate provider roots for `datadog/` and `pagerduty/`.
- Terraform pinned to `1.11.4` in `pipeline-templates/tf-stages.yml`.

## Validation

- No `.pre-commit-config.yaml`. CI runs from `pipeline-templates/`:
  - `tf-code-checks.yml`: `terraform fmt -recursive -check=true -diff=true`;
    Checkov (`bridgecrew/checkov --framework terraform --soft-fail`).
  - `tf-stages.yml`: `terraform init`, `terraform validate` (verbose mode),
    `terraform plan`.
- Local: `terraform/plan_test.sh` and `terraform/dev_aws/Makefile` run
  `init`/`validate`/`plan` per directory.
- Suggested validation commands to emit: `terraform fmt -recursive -check`,
  `terraform validate`, `checkov -d .`.

## Repo-specific exceptions

- `README.md` documents layout/accounts/conventions; `CLAUDE.md` covers hub
  nomenclature and account→folder mapping; `.github/copilot-instructions.md` and
  `.github/instructions/*.instructions.md` carry per-scope rules.
- CODEOWNERS default `@venasolutions/devops-guardians-team`; `dns_firewall.tf`
  also requires `@venasolutions/information-security-team`.
- PR title format `[#STO-<num>]`; `.cm/gitstream.cm` enforces JIRA references.
- No `.Serena`.
