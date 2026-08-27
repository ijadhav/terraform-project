Terrabot Terraform primary context

Repos: venasolutions/tf-devops (AWS SaaS) and venasolutions/tf-azure-hub (Azure hubs)
Generated: 2026-08-27 from live README, module READMEs, .github templates/instructions, pipelines, and .tf
Use: Foundry / terrabot upload file. Treat this as the primary authoring guide for aligned Terraform changes.
Precedence
Live .tf / .tfvars / pipeline YAML in the target repo
.github/copilot-instructions.md, .github/instructions/*.md, CLAUDE.md
README.md and module READMEs (often terraform-docs; frequently stale)
This file
Org-wide guesses or terraform-github/.serena memories
If this file disagrees with live files, live files win.
Hard rules
Do not:
Push directly to main
Apply Terraform except via existing Azure DevOps pipelines after review
Run terraform state mv/rm/import unless a human runbook was requested
“Fix” legacy code to match newer conventions unless that file is already being changed
Apply terraform-github Serena memories to these two repos
Invent terraform/templates/hub_template or per-hub directories in tf-azure-hub
Add DynamoDB locking to AWS backends
Commit .terraform.lock.hcl in tf-devops (gitignored)
Default branch: main. Merge: delete_branch_on_merge = true, title PR_TITLE, message BLANK.
Serena / Foundry exceptions
Location	Status
tf-devops	No .serena/. Do not create one.
tf-azure-hub	No .serena/. Do not create one.
terraform-github/.serena/memories/	GitHub org/repo/team IaC only (vena_repos/*.tf, vena_teams/*.tf)
Do not copy from terraform-github Serena into these repos:
DynamoDB table vena-terraform-github for state lock
S3 bucket vena-terraform-github in ca-central-1
default_branch develop (these repos use main)
File-per-repo vena_repos/REPO_NAME.tf
Okta sync_groups / team module patterns
Archive-then-delete two-PR GitHub repo deletion workflow
That project’s Terraform ~> 1.8.1 / GitHub provider ~> 5.0 pins
Org facts that do apply:
PULL_REQUEST_TEMPLATE.md, gitstream.yml, .cm/gitstream.cm are managed files from terraform-github. Change them there, not in the hub repos.
Jira autolink format: #PROJECT-123
If .serena/ is added later to a hub repo, parse .serena/memories/ as exceptions for that repo only.
Read these files first
Both repos
.github/PULL_REQUEST_TEMPLATE.md
.github/CODEOWNERS
.github/copilot-instructions.md
.cm/gitstream.cm
README.md
tf-devops only
CLAUDE.md
.github/instructions/terraform-modules.instructions.md (modules)
.github/instructions/hub-environments.instructions.md (hubs / DR / sqlstaging)
.github/instructions/pr_template_assistance.instructions.md
terraform/README.md (4-line account-prefix note; root README is the real guide)
terraform/modules/<name>/README.md when touching that module (most have none)
tf-azure-hub only
docs/aks.md when touching AKS / k8s.tf / NAP / ACNS
monitoring/dd_monitors/README.md when touching Datadog (stale in places)
.pre-commit-config.yaml
vars/**/*.tfvars for the hub being changed
pipelines/azure-pipelines-npr.yml and pipelines/azure-pipelines-prd.yml when adding hubs
PRs, git, review
Title and Jira
gitStream requires a Jira key in branch name and description.
Place	Pattern
Branch	.../(VDP|PO|STO)-<digits> after a slash (case-insensitive)
PR body	#(VDP|PO|STO)-<digits> (hash required)
Title	STO-NNNN Short summary or [#STO-NNNN] Short summary
Example branch: cursor/sto-1234-add-us7-hub
Example body token: #STO-1234
Put the Jira URL as the first line after # JIRA ticket link.
PR body (use the managed template verbatim)
Headings:
# JIRA ticket link
### Description
### Why was this required?
### How to test?
### Deployment plan
### Checklist
### Risk assessment [REQUIRED]
Checklist: PR title format; merge-first?; other repos?; simultaneous deploys?
Risk labels (check the box and add the label):
requires-review:hotfix-process
requires-review:cab (changing the risk questions themselves)
requires-review:security (CSP header)
requires-review:third-party-libraries
requires-review:team-only (telegraph upgrade or “No to all”)
Default routine Terraform to No to all + requires-review:team-only.
How to test: terraform fmt / validate / plan for affected env dirs (AWS) or var-file stacks (Azure).
Deployment: Azure DevOps apply after merge. Prod/statestreet apply only on main (applyFromBranch: false). npr/bolt/sbx may applyFromBranch.
CODEOWNERS
tf-devops
* @venasolutions/devops-guardians-team
/terraform/modules/vena_datacentre/dns_firewall.tf @venasolutions/information-security-team @venasolutions/devops-guardians-team
.github/workflows/ @venasolutions/tooling-team
.cm/ @venasolutions/tooling-team
tf-azure-hub
* @venasolutions/saaseng-team
.github/workflows/ @venasolutions/tooling-team
.cm/ @venasolutions/tooling-team
Branches off main. Prefer the Jira key after a slash. Conventional commits (feat|fix|chore|docs|ci|refactor) are fine.
tf-devops (AWS SaaS)
Terraform for Vena multi-tenant SaaS on AWS only. CI: Azure DevOps. Terraform 1.11.4. Hub required_version >= 1.11.4. Typical AWS provider ~> 5.34.0. Pin lives inside backend.tf. Copy the sibling pin; do not mass-standardize.
Provider exceptions
~> 6.21.0 — every */global/backend.tf and every */observe/backend.tf
~> 5.95 — terraform/dev_aws/minidev only
~> 5.40.0 — eu4_dr and ca3_dr
Accounts
Account	ID	Directory	State bucket	Pipeline
npr-aws-saas	520103559707	terraform/dev_aws/	venacloud-terraform-minidev	azure-pipelines_dev.yml
prd-aws-saas	987100187255	terraform/prod_aws/	venacloud-terraform	azure-pipelines_prod.yml
statestreet	652061513354	terraform/statestreet/	venacloud-terraform-statestreet	prod pipeline folderListStateStreet
ADO role pattern: arn:aws:iam::<account>:role/vena-ado-role-<account>.
Other state buckets: services → venacloud-terraform-services; dev_services → ...-dev-services; network_services → ...-network-services; logarchive → ...-logarchive; ops_shared_services → venacloud-terraform-state; audit → ...-audit; root → ...-root; datadog/pagerduty → venacloud-terraform.
Nomenclature
Hub: one end-to-end Vena system (tier npr/prd + name like dev or us4).
all hubs: every env dir under dev_aws, prod_aws, statestreet except devops / global / sqlstaging / observe. CLAUDE.md omits observe; still exclude it.
DR: directory suffix _dr; different region and VPC CIDR.
Layout
terraform/
  modules/          # 82 local modules; never a registry
  dev_aws/          # npr + bolt + global + devops + sqlstaging + observe
  prod_aws/         # prod hubs + DR + sqlstaging* + global + devops + observe
  statestreet/
pipeline-templates/ # tf-stages.yml, tf-code-checks.yml
azure-pipelines_*.yml  # _dev, _prod, _bolt, _drift, _ops_shared_services, _logarchive_observe
Environments are directories, not workspaces. Variable files are vars.tf, never variables.tf.
Hub types
Vena hub (bolt, dev, minidev, us1–us4, eu1/eu2/eu4, ca3, statestreet)
Required files: backend.tf, versions.tf, main.tf, outputs.tf.
main.tf must open with locals: env, subdomain, region, network_base, source_account_id. VPC CIDR is "${local.network_base}.0.0/16". Tags: env + role; prod/DR set VantaNonProd = "false".
Root module: vena_datacentre via source = "../../modules/vena_datacentre".
Approved satellites only: vena_sqlstaging_peering, patch_management (Linux + Windows).
Tech debt — do not add more: otel_collector / otel_collector_daemon, file_metrics. Bolt has patch_management commented out; do not uncomment unless asked.
New hub features: new module under terraform/modules/<name>/, called from vena_datacentre/*.tf, gated by create_* or enable_*. Do not call new modules from hub main.tf.
DR hub (*_dr)
Pass is_dr_region = true
Disable cost-heavy flags: create_mtserver_rds, create_template_rds, create_auditdb_redshift, create_staging_redshift, create_bucketav
Keep VPC, subnets, SGs, Kinesis, S3
ASG min/max = 0
Still production tags
Gate resources; never delete them
us1_dr calls vena_datacentre only
SQL staging: module vena_sqlstaging; often data.terraform_remote_state to tf-dns. Separate dir because of a different permission set.
global: no hub locals; split files (kms.tf, iam.tf, roles.tf, s3.tf, ecr.tf, …). AWS provider often 6.21.
devops / dev_devops: hydra.tf, peering.tf, routes.tf, security_groups.tf, lookups.tf.
Live env lists
dev_aws: bolt, bolt_dr, bolt_sqlstaging, dev, dev_devops, dev_sqlstaging, global, minidev, minidev_sqlstaging, observe
prod_aws: us1–us4 + _dr, eu1/eu2/eu4 + _dr, ca3 + _dr, sqlstaging variants including sqlstaging_eu4, devops, global, observe
statestreet: statestreet, statestreet_dr, global, observe, sqlstaging
Bolt is isolated on azure-pipelines_bolt.yml (STO-8969). Do not add bolt folders back to azure-pipelines_dev.yml.
vena_datacentre
Owns VPC, RDS (mtserver, template), Redshift, ECS/Fargate/ALB, Kinesis/Firehose, S3, KMS, SM, SSM, Route53, CloudFront, WAF, CloudWatch, Datadog, CloudAMQP.
Wiring outputs: vpc_id, private_subnet_ids, private_subnet_rtbs, ecs_load_balancer_listener_arn, ecs_load_balancer_dns_name, ecs_agent_role_name, audit_stream_arn, s3_ss3_arn, rds_sse_arn.
Known exceptions (do not proliferate): hardcoded public_route53_role_arn in main.tf; versions.tf still >= 0.12.
Modules
New modules need main.tf, vars.tf, outputs.tf, versions.tf. Some legacy modules use output.tf — do not rename. Source: ../../modules/<name>. Never publish to a registry.
Feature flags: enable_* for ECS/app; create_* for stateful/cost-heavy (default true; DR sets false).
hcl
variable "is_dr_region" {
  description = "Set to true in DR hub environments to disable non-essential CloudWatch alarms and secondary resources."
  type        = bool
  default     = false
}
# Gate alarms: count = var.is_dr_region ? 0 : 1
Every variable: description + type, snake_case. KMS/SSE always on for S3, RDS, Kinesis, Redshift, SQS. No hardcoded ARNs — use data sources. Optional SSM:
hcl
data "aws_ssm_parameter" "optional_key" {
  count = local.feature_enabled ? 1 : 0
  name  = "/prod/service/optional-key"
}
s3 module README: versioning + logging + SSE required; glacier/delete must be explicit (-1 to disable); auto_delete_prefixes disables bucket-wide expiration for those prefixes.
Backend (S3)
No DynamoDB. encrypt = true. Bucket region always us-east-1. Key: <folder>/terraform.tfstate.
Exceptions: dev dir uses key dev2/terraform.tfstate; us2_dr and us4_dr use underscore keys. Copy siblings; do not invent.
hcl
terraform {
  backend "s3" {
    bucket  = "venacloud-terraform" # or -minidev / -statestreet / account-specific
    key     = "<folder>/terraform.tfstate"
    region  = "us-east-1"
    encrypt = true
  }
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.34.0" # copy sibling pin
    }
  }
}
No var interpolations in backend blocks.
CI/CD
Templates: pipeline-templates/tf-stages.yml. ADO templates tag v4.11.02. Auth: STS assume-role with --external-id.
Per folder: TF_Test (fmt -check + Checkov soft-fail) → TF_Plan → TF_Apply if changes and (isMain OR applyFromBranch).
applyFromBranch: dev true, bolt true, prod false.
Always pass terraformVersion: 1.11.4 (code-checks default is still 1.3.10).
Local:
bash
cd terraform/dev_aws/dev
terraform get -update && terraform validate && terraform plan
# or: cd terraform/dev_aws && make
Add an AWS hub
Copy a sibling hub of the same tier (dev or us1). No template directory exists.
Unique network_base and env.
backend.tf with existing bucket + new key.
Call vena_datacentre + approved satellites only.
Add the folder to the correct azure-pipelines_*.yml folderList (bolt → bolt pipeline).
Plan that directory; document in PR How to test.
Module changes: update vena_datacentre if I/O changed; plan npr (dev/minidev) plus one prod hub if used in prod; call out destroy/replace.
tf-azure-hub (Azure root module)
Not an env-directory monorepo. One root module at repo root. One apply = one hub (or DR overlay) via -var-file stack. Owners: saaseng-team. GitHub Actions disabled. ADO templates refs/tags/v4.11.8. Terraform 1.11.4 (>=1.11.4 in provider.tf). Variables file is variables.tf.
Do not create terraform/prd/us5/ directories. Hubs are var files.
Root README is terraform-docs and stale (still >=1.6.5, azurerm <5, old module tags). Trust provider.tf and live source = lines.
.tool-versions is gitignored but still tracked. Do not delete it.
Var files
vars/common.tfvars
vars/<tier>/tier.tfvars
vars/<tier>/<subscription>/hub.tfvars
vars/<tier>/<subscription>/dr.tfvars   # AFTER hub.tfvars
Tier	Hub	Region	DR	Pipeline
sbx	infra (sbx-infra)	centralus	—	active (infra)
npr	int (npr-int)	centralus	eastus2 overlay	active (int)
npr	int-dr / stg			commented out
prd	us5	eastus	westus	active + us5_dr
prd	us6	centralus	eastus2	active + us6_dr
prd	ca4	canadacentral	canadaeast	active + ca4_dr
prd	eu3	northeurope	westeurope	active + eu3_dr
Plan order:
bash
terraform plan \
  -var-file=vars/common.tfvars \
  -var-file=vars/<tier>/tier.tfvars \
  # sbx-infra also: npr/tier.tfvars then sbx/tier.tfvars
  -var-file=vars/<tier>/<sub>/hub.tfvars \
  [-var-file=vars/<tier>/<sub>/dr.tfvars]
subscription_type is not in tfvars; ADO injects npr|prd.
Naming
RG: rg-${subscription_type}-${hub_name}-${location}
DR RG: rg-${subscription_type}-${hub_name}-dr-${dr_location}
VNet: vnet-${subscription_type}-${hub_name}-${location}
AKS: aks-${subscription_type}-${hub_name}-cluster
LAW: log-${subscription_type}-${hub_name} (not law-...)
AGW: agw-${subscription_type}-${hub_name}
Tags: ManagedBy=Terraform, GithubRepo=https://github.com/venasolutions/tf-azure-hub. Prod: vanta_non_prod = "false". VantaContainsUserData true only when subscription_type == prd.
Providers and backend
azurerm: >=4.3.0, <4.77.0 (storage_queue + storage_use_azuread bug). Do not bump past 4.77.0 until hashicorp/terraform-provider-azurerm#32612 ships. storage_use_azuread = true on every alias.
Aliases: default hub sub; management_sub; infradevops_sub; npr_infradevops_sub (always NPR); insights_sub; global_sub. CloudAMQP API key via ephemeral Key Vault secret. Empty kubernetes/helm providers filled from AKS outputs at apply.
hcl
terraform {
  backend "azurerm" {
    use_azuread_auth = true
  }
}
No backend.tf. Pipeline injects stateFileName: tf-azure-hub (primary), tf-azure-hub-dr (DR), tf-azure-hub-datadog (monitors). Tenant venaprimary. Do not invent RG/storage/key in repo.
External modules (live pins — README is stale)
Use git tags, plus Checkov skip CKV_TF_1:
tf-azure-vnet v5.0.3 · tf-azure-storage-account v1.2.2 · tf-azure-event-hub v1.1.0 · tf-azure-container-apps v1.1.6 · tf-azure-app-gateway v2.0.5 · tf-azure-rbac v1.0.0 · tf-azure-function-app v1.0.2 · tf-azure-apim v1.0.2 · tf-azure-data-factory v1.0.2 · tf-azure-patch-mgmt v2.5.4 · tf-module-azure-db-mysql-flexible v2.0.4 · tf-module-azure-secret v1.0.0 · tf-module-cloudamqp v2.2.2 · terraform-azurerm-loadbalancer v1.0.1 · Azure/aks/azurerm ~> 11.4.0 · Datadog monitors tf-datadog-mac v1.0.1
Prefer existing Vena git modules. Pin a tag already used in this repo unless the task is a bump. Pass aliased providers when the child needs them. Gate with count = var.create_* && var.create_environment ? 1 : 0.
Feature flags and DR
create_* for APIM, AGW, KV, LAW, MySQL, SQL, diagnostics, RSV, WAN, environment, etc.
aca_app_*_enabled per Container App
enable_kubernetes master flag for AKS + AGW + related RBAC
deploy_in_dr_region for DR overlay
Dead tfvars key aca_app_jenkins_sample_project_enabled has no variable — ignore unless asked
DR: extra dr.tfvars; hub_name like us5-dr; primary_hub_name / primary_location point at primary; flip create_* and ACA flags off; typically create_mysql_db_dr_read_replica = true.
West US: ZRS unsupported. Reuse storage_account_zrs with account_replication = LRS — do not rename the variable. Also zones = [], no ACA zone redundancy, MSSQL elastic pool not zone redundant.
Do not uncomment npr-int DR or npr-stg stages without an explicit request.
AKS (docs/aks.md)
Azure CNI Overlay. ACNS/Cilium default (aks_acns_enabled). NAP opt-in (aks_nap_enabled); currently sbx-infra only. Prefer aks_nap_default_node_pools = "None". NAP + Terraform-managed pools: mode = Auto requires auto_scaling_enabled = false on user pools. Never enable NAP/ACNS globally in common.tfvars without a rollout plan.
Datadog monitors (monitoring/dd_monitors/)
Separate Terraform root. Add a service: new *_monitors.tf locals map → optional templates/*.tftpl → merge() into all_monitors in hub_monitors.tf (README still says main.tf). Live merge is currently only local.api_audit_monitors. Pipeline: monitoring/datadog-azure-pipelines.yml (templates v3.3.0, pr: none).
Azure CI and pre-commit
NPR: pipelines/azure-pipelines-npr.yml, applyFromBranch: true, drift + Teams.
PRD: pipelines/azure-pipelines-prd.yml, one stage pair per hub and *_dr.
Auth: WIF connections vena-azure-sub-<tier>-<hub>-wif.
Pre-commit: antonbabenko/pre-commit-terraform v1.91.0 — terraform_fmt, terraform_docs, terraform_tflint (unused_declarations and module_version disabled). After variable changes, expect README terraform-docs refresh.
Add an Azure hub / resource
Hub: copy nearest geography hub.tfvars; unique VNet/subnet CIDRs (CloudAMQP CIDR often outside the /21); optional dr.tfvars; wire pipeline stage (moduleName, WIF connection, adoEnvironment, azureRegion, var-file list, stateFileName). Do not duplicate .tf files per hub.
Resource: new <concern>.tf at repo root (or extend the existing service file); add variables with description+type; defaults in variables.tf or common.tfvars; hub overrides only in hub.tfvars; gate with create_* / enable_*; fmt + terraform-docs.
Do not confuse the two repos
tf-devops	tf-azure-hub
Environments	Directories	tfvars + pipeline stages
Modules	Relative ../../modules/	git ?ref=vX.Y.Z (+ AKS registry)
Variables file	vars.tf	variables.tf
State	S3 us-east-1, no DynamoDB	Partial azurerm backend, ADO fills the rest
ADO templates	v4.11.02 local pipeline-templates/	v4.11.8 remote ado-pipeline-templates
“all hubs”	AWS only; exclude observe	Azure hubs are us5/us6/ca4/eu3 + sbx-infra/npr-int
Security
Never commit keys, tokens, PEMs, or tfvars secrets. Azure: Key Vault + ephemeral data. AWS: SSM / Secrets Manager data sources. Least privilege IAM/RBAC. KMS/SSE on by default. Checkov is soft-fail; still avoid new CKV findings; skip comments need a reason matching existing style.
Diagnostics
Init backend errors: Azure needs ADO/WIF; AWS needs venacloud-terraform* + credentials. Do not create buckets from terrabot.
Plan destroy/replace: annotate the PR; do not apply.
Module version bumps: change one pin; plan sbx/npr first.
State migrations: write a runbook; do not run terraform state * autonomously.