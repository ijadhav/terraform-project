from pathlib import Path

from terrabot_core.scanner import scan_repository
from terrabot_core.workflow_inferer import infer_workflow
from terrabot_core.retriever import retrieve_context
from terrabot_core.policy_loader import evaluate_policy
from terrabot_core.generator import generate_change_plan
from shared_code.request_router import route_request


def make_azure_repo(root: Path):
    (root / "vars" / "npr" / "npr-int").mkdir(parents=True)
    (root / "pipelines").mkdir()
    (root / "provider.tf").write_text(
        'terraform {\n  required_providers {\n    azurerm = { source = "hashicorp/azurerm" }\n  }\n}\nprovider "azurerm" { features {} }\n',
        encoding="utf-8",
    )
    (root / "storage_accounts.tf").write_text(
        'module "azurerm_storage_account_zrs" {\n'
        '  source = "git@github.com:example/tf-azure-storage-account.git?ref=v1.0.0"\n'
        '  storage_account_public_network_access_enabled = false\n'
        '}\n',
        encoding="utf-8",
    )
    (root / "variables.tf").write_text('variable "storage_account_zrs" { type = any }\n', encoding="utf-8")
    (root / "vars" / "npr" / "tier.tfvars").write_text('subscription_type = "npr"\n', encoding="utf-8")
    (root / "vars" / "npr" / "npr-int" / "hub.tfvars").write_text('resource_group_name = "rg-npr-int"\n', encoding="utf-8")
    (root / "pipelines" / "azure-pipelines-npr.yml").write_text(
        'stages:\n- template: terraform/azure-tf-stages-template.yml\n  parameters:\n    terraformVersion: "1.11.4"\n    terraformPlanArguments: |\n      -var-file="vars/common.tfvars" \\\n      -var-file="vars/npr/tier.tfvars" \\\n      -var-file="vars/npr/npr-int/hub.tfvars"\n',
        encoding="utf-8",
    )
    (root / ".pre-commit-config.yaml").write_text(
        'repos:\n- repo: https://github.com/antonbabenko/pre-commit-terraform\n  hooks:\n  - id: terraform_fmt\n  - id: terraform_tflint\n',
        encoding="utf-8",
    )


def test_scan_detects_terraform_azure_env_pipeline(tmp_path):
    make_azure_repo(tmp_path)
    profile = scan_repository(str(tmp_path))
    assert "terraform" in profile.iac_tools
    assert "azure" in profile.clouds
    assert "azurerm" in profile.providers
    assert "npr" in profile.environments
    assert "azure-pipelines" in profile.pipeline_systems
    assert "pre-commit run --all-files" in profile.validation_commands


def test_workflow_inference_storage_account(tmp_path):
    make_azure_repo(tmp_path)
    profile = scan_repository(str(tmp_path))
    workflow = infer_workflow("add a private storage account for analytics in npr", profile)
    assert workflow.cloud == "azure"
    assert workflow.resource_type == "storage_account"
    assert workflow.target_environment == "npr"
    assert workflow.workflow_type == "terraform_existing_module_consumer"
    assert "storage_accounts.tf" in workflow.target_files


def test_retriever_policy_and_plan_need_model(tmp_path):
    make_azure_repo(tmp_path)
    profile = scan_repository(str(tmp_path))
    workflow = infer_workflow("add a private storage account for analytics in npr", profile)
    evidence = retrieve_context(str(tmp_path), "add a private storage account for analytics in npr", profile, workflow)
    assert any(item.path == "storage_accounts.tf" for item in evidence)
    policy = evaluate_policy("add a private storage account for analytics in npr", profile, workflow, evidence, str(tmp_path))
    assert policy.allowed
    plan = generate_change_plan(str(tmp_path), "add a private storage account for analytics in npr", profile, workflow, evidence, policy)
    assert plan.status in {"ready_for_model", "needs_values"}
    assert "storage_accounts.tf" in plan.source_paths_used


def test_router_accepts_repo_aware_workflow(tmp_path):
    make_azure_repo(tmp_path)
    profile = scan_repository(str(tmp_path))
    workflow = infer_workflow("add a private storage account for analytics in npr", profile)
    decision = route_request(
        "add a private storage account for analytics in npr",
        repo_profile=profile,
        workflow_profile=workflow,
    )
    assert decision.request_type == "infra"
    assert decision.workflow == "terraform_existing_module_consumer"
