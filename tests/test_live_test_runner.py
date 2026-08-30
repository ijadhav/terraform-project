from shared_code import live_test_runner as ltr


# --------------------------------------------------------------------------- #
# Pure parsing helpers
# --------------------------------------------------------------------------- #
def test_find_boolean_assignments():
    content = (
        'create_cloudamqp = true\n'
        'enable_kubernetes = false\n'
        'aca_app_nginx_enabled = true\n'
        'some_other = "x"\n'
        'count = 3\n'
    )
    found = ltr.find_boolean_assignments(content)
    flags = {f["flag"]: f["value"] for f in found}
    assert flags == {
        "create_cloudamqp": True,
        "enable_kubernetes": False,
        "aca_app_nginx_enabled": True,
    }


def test_find_module_blocks():
    content = (
        'module "vena_datacentre" {\n'
        '  source = "../../modules/vena_datacentre"\n'
        '  env    = local.env\n'
        '}\n'
    )
    blocks = ltr.find_module_blocks(content)
    assert blocks[0]["name"] == "vena_datacentre"
    assert blocks[0]["source"] == "../../modules/vena_datacentre"


def test_environment_from_path():
    assert ltr.environment_from_path("vars/npr/npr-int/hub.tfvars") == "npr-int"
    assert ltr.environment_from_path("vars/prd/tier.tfvars") == "prd"
    assert ltr.environment_from_path("terraform/dev_aws/dev/main.tf") == "dev"
    assert ltr.environment_from_path("main.tf") == ""


def test_boolean_prompt_direction():
    assert ltr._boolean_prompt("create_cloudamqp", True, "npr") == "Disable create_cloudamqp in npr"
    assert ltr._boolean_prompt("create_adf", False, "prd") == "Enable create_adf in prd"


# --------------------------------------------------------------------------- #
# Discovery with injected fakes (no network)
# --------------------------------------------------------------------------- #
_FAKE_TREE = {
    "azure": [
        "variables.tf",
        "vnet.tf",
        "vars/common.tfvars",
        "vars/npr/tier.tfvars",
        "vars/npr/npr-int/hub.tfvars",
    ],
    "aws": [
        "terraform/dev_aws/dev/main.tf",
        "terraform/modules/vena_datacentre/vars.tf",
    ],
}

_FAKE_FILES = {
    "vars/npr/tier.tfvars": "create_cloudamqp = true\nenable_kubernetes = false\n",
    "vars/common.tfvars": "create_adf = false\n",
    "vnet.tf": 'module "vnet" {\n  source = "git@github.com:venasolutions/tf-azure-vnet.git?ref=v5.0.3"\n}\n',
    "terraform/dev_aws/dev/main.tf": (
        'module "vena_datacentre" {\n'
        '  source = "../../modules/vena_datacentre"\n'
        '  create_subdomain_dns = true\n'
        '}\n'
    ),
}


def _fake_tree_fn(owner, repo, branch, token):
    return _FAKE_TREE["azure"] if "azure" in repo else _FAKE_TREE["aws"]


def _fake_fetch_fn(owner, repo, path, branch, token):
    return _FAKE_FILES.get(path, "")


def test_discover_cases_azure():
    target = {"cloud": "azure", "repo_target": "tf-azure-hub", "repo": "tf-azure-hub", "branch": "main"}
    cases = ltr.discover_cases_for_target(target, _fake_tree_fn, _fake_fetch_fn, "tok", "owner")
    types = {c["type"] for c in cases}
    assert "boolean_modification" in types
    assert "existing_module_new_consumer" in types
    assert "repository_context_regression" in types

    bool_case = next(c for c in cases if c["type"] == "boolean_modification")
    assert bool_case["flag"] == "create_cloudamqp"
    assert bool_case["current_value"] is True
    assert bool_case["desired_value"] is False
    assert bool_case["environment"] == "npr"
    assert bool_case["target_path"] == "vars/npr/tier.tfvars"
    assert bool_case["prompt"] == "Disable create_cloudamqp in npr"


def test_discover_cases_aws():
    target = {"cloud": "aws", "repo_target": "tf-devops", "repo": "tf-devops", "branch": "main"}
    cases = ltr.discover_cases_for_target(target, _fake_tree_fn, _fake_fetch_fn, "tok", "owner")
    bool_case = next(c for c in cases if c["type"] == "boolean_modification")
    assert bool_case["flag"] == "create_subdomain_dns"
    assert bool_case["target_path"] == "terraform/dev_aws/dev/main.tf"
    assert bool_case["environment"] == "dev"


# --------------------------------------------------------------------------- #
# Execution with injected fakes
# --------------------------------------------------------------------------- #
def _make_case():
    return {
        "type": "boolean_modification",
        "cloud": "azure",
        "repo_target": "tf-azure-hub",
        "repo": "tf-azure-hub",
        "branch": "main",
        "environment": "npr",
        "target_path": "vars/npr/tier.tfvars",
        "flag": "create_cloudamqp",
        "current_value": True,
        "desired_value": False,
        "prompt": "Disable create_cloudamqp in npr",
        "mode": "infra",
        "case_id": "c01-boolean_modification",
    }


def test_execute_case_success_pushes_branch():
    calls = []

    def backend_call(request):
        calls.append(request)
        if request.get("action") == "commit_branch":
            return {"ok": True, "branch_url": "https://github.com/o/r/tree/b", "committed": True}, 200
        return {
            "ok": True,
            "mode": "infra_preview",
            "files": [{"path": "vars/npr/tier.tfvars", "operation": "modify"}],
            "validation_commands": ["terraform fmt"],
            "pending_change_id": "pcid-1",
            "thread_id": "th-1",
        }, 200

    def retrieval_fn(prompt, owner, repo, branch, token):
        return {"paths": ["vars/npr/tier.tfvars"], "context_block": "create_cloudamqp = true"}

    result = ltr.execute_case(
        _make_case(), "run-1", "owner", "tok",
        verify_fn=lambda *a, **k: True,
        retrieval_fn=retrieval_fn,
        backend_call=backend_call,
        primary_loaded_fn=lambda *a, **k: True,
    )

    assert result["target_found"] is True
    assert result["flag_control_detected"] is True
    assert result["primary_context_loaded"] is True
    assert result["repository_context_retrieved"] is True
    assert result["repository_context_useful"] is True
    assert result["generated_file"] is True
    assert result["validation"] is True
    assert result["branch_pushed"] is True
    assert result["attempts"] == 2
    assert result["failure_reason"] == ""
    # Real backend workflow was used, not the generator; two calls: generate + commit.
    assert [c.get("action") for c in calls] == [None, "commit_branch"]
    assert calls[0]["run_id"] == "run-1"
    assert calls[0]["case_id"] == "c01-boolean_modification"
    assert calls[0]["source"] == "teams"


def test_execute_case_missing_target_skips_backend():
    called = []
    result = ltr.execute_case(
        _make_case(), "run-1", "owner", "tok",
        verify_fn=lambda *a, **k: False,
        retrieval_fn=lambda *a, **k: {"paths": [], "context_block": ""},
        backend_call=lambda req: called.append(req),
        primary_loaded_fn=lambda *a, **k: True,
    )
    assert result["target_found"] is False
    assert result["failure_reason"] == "target_missing_at_head"
    assert called == []  # never touches the backend when target is gone at HEAD


def test_aggregate_and_summary():
    results = [
        {
            "type": "boolean_modification", "repo_target": "tf-azure-hub", "environment": "npr",
            "prompt": "Disable create_cloudamqp in npr", "target_found": True,
            "flag_control_detected": True, "primary_context_loaded": True,
            "repository_context_retrieved": True, "repository_context_useful": True,
            "generated_file": True, "validation": True, "branch_pushed": True,
            "attempts": 2, "duration_seconds": 1.0, "failure_reason": "",
        },
        {
            "type": "repository_context_regression", "repo_target": "tf-azure-hub", "environment": "npr",
            "prompt": "Which repository file sets create_cloudamqp?", "target_found": True,
            "flag_control_detected": True, "primary_context_loaded": True,
            "repository_context_retrieved": True, "repository_context_useful": True,
            "generated_file": False, "validation": False, "branch_pushed": False,
            "attempts": 0, "duration_seconds": 0.5, "failure_reason": "",
        },
    ]
    agg = ltr.aggregate("run-9", results)
    assert agg["total_cases"] == 2
    assert agg["passed"] == 2
    assert agg["failed"] == 0
    assert agg["branch_pushed"] == 1
    assert agg["repository_context_useful"] == 2
    summary = ltr.format_teams_summary(agg)
    assert "Terrabot live test run" in summary
    assert "run-9" in summary
    assert summary.count("[PASS]") == 2


def test_run_suite_end_to_end_offline():
    config = ltr.RunnerConfig(
        owner="owner", azure_repo="tf-azure-hub", azure_branch="main",
        aws_repo="tf-devops", aws_branch="main", token="tok",
    )

    def backend_call(request):
        if request.get("action") == "commit_branch":
            return {"ok": True, "branch_url": "https://x/tree/b"}, 200
        return {
            "ok": True, "mode": "infra_preview",
            "files": [{"path": request.get("repo_target"), "operation": "modify"}],
            "validation_commands": ["terraform validate"],
            "pending_change_id": "p1", "thread_id": "t1",
        }, 200

    summary = ltr.run_suite(
        config,
        run_id="run-e2e",
        tree_fn=_fake_tree_fn,
        fetch_fn=_fake_fetch_fn,
        verify_fn=lambda *a, **k: True,
        retrieval_fn=lambda prompt, o, r, b, t: {"paths": ["vars/npr/tier.tfvars"], "context_block": prompt},
        backend_call=backend_call,
        primary_loaded_fn=lambda *a, **k: True,
    )
    assert summary["run_id"] == "run-e2e"
    assert summary["total_cases"] >= 4  # azure(3) + aws(>=1)
    assert summary["teams_summary"]
    assert summary["branch_pushed"] >= 1
