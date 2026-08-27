# Copilot Instructions — tf-devops

Terraform AWS infrastructure monorepo for Vena Solutions. CI/CD runs on **Azure DevOps Pipelines**; infrastructure target is **AWS**.

## Vena Hubs

A **Vena hub** is a geographically-defined cloud environment that hosts the full Vena application stack and customer data for a set of tenants. Each hub has:
- A **primary region** where workloads run (at least 3 AZs)
- A **DR region** (backup/failover), suffixed `_dr` in directory names

Hubs are differentiated by geography (US, CA, EU), purpose (non-prod vs prod), and tenancy model.

### Environment Directory Types

Inside each AWS account directory (`dev_aws/`, `prod_aws/`, etc.) directories fall into these categories:

| Pattern | Type | Description |
|---------|------|-------------|
| `bolt`, `dev`, `minidev`, `us1`, `eu2`, `ca3` … | **Vena hub** | Full application stack for a set of tenants |
| `*_dr` (e.g., `bolt_dr`, `us1_dr`) | **DR hub** | Disaster recovery counterpart of its primary hub |
| `*_sqlstaging` (e.g., `bolt_sqlstaging`) | **SQL staging** | SQL staging environment for the named hub |
| `global` | **Account-global** | Shared resources for the AWS account: S3 buckets, IAM roles, KMS keys, ECR, ACM, WAF, SNS, CDN, etc. |
| `devops` / `dev_devops` | **DevOps tooling** | Auxiliary environment for CI/CD tooling (Jenkins, ADO agents, Hydra, VPC peering, security groups) |

## AWS Accounts

| Account | ID | Directory |
|---------|----|-----------|
| `npr-aws-saas` (non-prod) | `520103559707` | `terraform/dev_aws/` |
| `prd-aws-saas` (production) | `987100187255` | `terraform/prod_aws/` |

### dev_aws hubs & environments
- `bolt` — Vena hub (non-prod)
- `bolt_dr` — DR hub for bolt
- `bolt_sqlstaging` — SQL staging for bolt
- `dev` — Vena hub (non-prod)
- `dev_devops` — DevOps tooling (Jenkins, ADO, VPC peering, etc.)
- `dev_sqlstaging` — SQL staging for dev
- `global` — Account-wide shared resources
- `minidev` — Vena hub (non-prod, smaller)
- `minidev_sqlstaging` — SQL staging for minidev

### prod_aws hubs & environments
- `us1`, `us2`, `us3`, `us4` — US Vena hubs + their `_dr` counterparts
- `eu1`, `eu2` — EU Vena hubs + their `_dr` counterparts
- `ca3` — Canada Vena hub + `ca3_dr`
- `sqlstaging`, `sqlstaging_ca`, `sqlstaging_eu`, `sqlstaging_eu2`, `sqlstaging_us4`, `sqlstaging_west` — SQL staging variants
- `devops` — DevOps tooling
- `global` — Account-wide shared resources

## Repository Layout

```
terraform/
  modules/          # Reusable modules (~50+); called via relative path ../../modules/<name>
  dev_aws/          # npr-aws-saas (520103559707) — dev hubs, DR, SQL staging, global, devops
  prod_aws/         # prd-aws-saas (987100187255) — prod hubs, DR, SQL staging, global, devops
  services_aws/     # Prod services AWS account
  dev_services_aws/ # Dev services AWS account
  network_services/ # Shared network services
  datadog/          # Datadog monitors & synthetics (separate provider)
  pagerduty/        # PagerDuty resources
  root/             # Root/management account
pipeline-templates/ # Reusable Azure DevOps pipeline templates
azure-pipelines_*.yml  # Per-environment pipeline entry points
```

## Terraform Conventions

### General
- **Environments are directories, not workspaces.** Each subdirectory under `dev_aws/`, `prod_aws/`, etc. is an isolated environment with its own S3 remote state.
- **Variable files are named `vars.tf`**, not `variables.tf`.
- Resources and variables use `snake_case`.
- All variables must have `description` and `type`.
- **No hardcoded ARNs.** Use `data "aws_sns_topic"`, `data "aws_kms_key"`, `data "aws_secretsmanager_secret"`, etc.
- **KMS encryption is always enabled** on resources that support it.
- **Feature flags**: use boolean variables (e.g., `enable_kinesis_alarms_fifteen_mins_behind`) to toggle optional resources.

### Environment Structure by Type

**Vena hub** (`bolt`, `dev`, `us1`, `eu2`, etc.) — full application stack:
- Required files: `backend.tf`, `versions.tf`, `main.tf`, `outputs.tf`
- `main.tf` always opens with a `locals {}` block defining `env`, `subdomain`, `region`, `network_base`, `source_account_id`
- Tags always include `env` and `role`; prod hubs include `VantaNonProd = "false"` in `default_tags`
- May contain `s3.tf` for hub-specific bucket resources

**DR hub** (`*_dr`) — disaster recovery counterpart of a primary hub:
- Same required files as a hub; pass `is_dr_region = true` to all modules
- Non-essential alarms and resources are suppressed via `is_dr_region` — never delete them, only gate them

**SQL staging** (`*_sqlstaging`) — minimal; typically only `backend.tf`, `main.tf`, `outputs.tf`, `versions.tf`

**global** — account-wide shared resources; split by service into dedicated files:
- `kms.tf`, `iam.tf`, `roles.tf`, `roles_policy.tf`, `policy.tf`, `policy_attachment.tf`
- `s3.tf`, `ecr.tf`, `acm.tf`, `acm_pca.tf`, `cdn.tf`, `waf.tf`, `sns.tf`
- `lambdas.tf`, `groups.tf`, `historian.tf`, `tenant_to_tenant.tf`, `venalytics.tf`
- No `locals {}` env/subdomain pattern — uses account-level identifiers instead

**devops / dev_devops** — CI/CD tooling; contains unique files not found in hubs:
- `hydra.tf`, `peering.tf`, `routes.tf`, `security_groups.tf`, `lookups.tf`

### Modules
- **Every module** must contain: `main.tf`, `vars.tf`, `outputs.tf`, `versions.tf`
- Large modules split concerns into feature files: `cloudwatch.tf`, `iam.tf`, `alb.tf`, etc.
- **DR awareness**: modules expose `var.is_dr_region = false`; set to `true` in `*_dr` environments to disable non-essential CloudWatch alarms and secondary resources without removing them

## Version Pins

| Component | Version |
|-----------|---------|
| Terraform (current) | `>= 1.11.4` |
| AWS provider | `~> 5.34.0` |
| Terraform (pipeline) | `1.11.4` (pinned in `pipeline-templates/tf-stages.yml`) |

## Local Validation

```bash
# Plan all environments in an account directory
cd terraform/dev_aws && make

# Single environment
cd terraform/dev_aws/dev && terraform get -update && terraform validate && terraform plan
```

See [terraform/plan_test.sh](../terraform/plan_test.sh) for bulk init/validate/plan across subdirs.

## CI/CD Pipeline

- Root `azure-pipelines_*.yml` files are entry points per environment group (`dev`, `prod`, `bolt`, `drift`).
- They delegate to `pipeline-templates/tf-stages.yml`, which runs for each folder in `folderList`:
  1. **TF_Test** — `terraform fmt -check` + Checkov (security analysis)
  2. **TF_Plan** — `terraform plan` using AWS STS assume-role with `--external-id`
- AWS auth: ADO service connection + STS cross-account role assumption.
- See [pipeline-templates/tf-stages.yml](../pipeline-templates/tf-stages.yml) for stage structure.

## Scoped Instructions

Deeper conventions are captured in scoped instruction files that load automatically or on-demand:

| File | Loads when |
|------|-----------|
| [terraform-modules.instructions.md](instructions/terraform-modules.instructions.md) | Editing any file under `terraform/modules/**` |
| [hub-environments.instructions.md](instructions/hub-environments.instructions.md) | On-demand — creating/modifying hub environments, DR hubs, or wiring modules |
| [terabot_backend_context.yaml](terabot_backend_context.yaml) | Terrabot primary context (tf-devops + tf-azure-hub). Prefer live `.tf` if this file conflicts. This repo has no `.serena/` directory. |

## Module Calling Pattern

```hcl
module "kinesis" {
  source = "../../modules/kinesis"
  # ...vars
}
```

Paths are always relative; modules are never published to a registry.

## PR Conventions

- PR title format: `STO-NNNN Brief description` (JIRA ticket number prefix)
- Use [.github/PULL_REQUEST_TEMPLATE.md](PULL_REQUEST_TEMPLATE.md) for PR descriptions
- Label guidance is in the risk assessment section of the PR template
- Fill the managed template (JIRA link, Description, Why, How to test, Deployment plan, Checklist, Risk assessment). Default routine Terraform to `requires-review:team-only`.