from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPAIR = ROOT / "shared_code" / "terrabot_core_parts" / "09_repair_pipeline.py"
GEN = ROOT / "shared_code" / "terrabot_core_parts" / "07_teams_generation_flow.py"
ROUTER = ROOT / "shared_code" / "terrabot_core_parts" / "10_teams_router_runtime.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _exec_function(path: Path, name: str, namespace: dict) -> dict:
    tree = ast.parse(_source(path))
    matches = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    assert matches, f"{name} missing from {path.name}"
    module = ast.Module(body=[matches[-1]], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), "exec"), namespace, namespace)
    return namespace


def _function_names(path: Path) -> set[str]:
    tree = ast.parse(_source(path))
    return {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}


def test_repair_call_reuses_existing_foundry_conversation():
    calls = []

    def call_agent(conversation_id, raw):
        calls.append((conversation_id, json.loads(raw)))
        return conversation_id or "new-conversation", '{"files": []}'

    ns = {
        "json": json,
        "_teams_diag_log": lambda *args, **kwargs: None,
        "_TEAMS_MULTICLOUD_PREVIOUS_CALL_AGENT": call_agent,
    }
    _exec_function(REPAIR, "_teams_call_agent_for_backend_repair", ns)
    conversation_id, _reply = ns["_teams_call_agent_for_backend_repair"](
        {"repair_files": [{"path": "main.tf"}]},
        conversation_id="conv-existing",
    )
    assert conversation_id == "conv-existing"
    assert calls and calls[0][0] == "conv-existing"


def test_repair_payload_carries_hard_rules_and_exact_boolean_hint():
    live = "module \"x\" {\n  enabled = true\n}\n"
    ns = {
        "_teams_collect_live_repair_files": lambda *args, **kwargs: [{
            "path": "main.tf",
            "repository_ref": "main",
            "existing_live_content": live,
            "rejected_generated_content": "short",
            "existing_nonblank_line_count": 3,
            "rejected_nonblank_line_count": 1,
            "existing_sha256": "sha",
            "rejected_sha256": "bad",
            "must_return_complete_final_file": True,
            "repair_baseline_source": "github_exact",
        }],
        "_get_backend_existing_infra_context": lambda _ctx: {
            "matched_files": [{
                "path": "main.tf",
                "feature_flag_match": {
                    "flag": "enabled",
                    "current_value": "true",
                    "new_value": "false",
                    "line_number": 2,
                },
            }]
        },
        "_modular_repair_protocol": lambda all_existing: ["protocol"],
        "_modular_repair_response_contract": lambda all_existing: {"existing": all_existing},
    }
    _exec_function(REPAIR, "_teams_build_backend_repair_payload", ns)
    payload = ns["_teams_build_backend_repair_payload"](
        {"cloud": "aws", "workflow": "aws_infra_modification", "repo_target": "tf-devops", "files": []},
        "disable x",
        "validation failed",
        retrieved_value_context=[{"source": "ctx"}],
    )
    assert payload["repair_chain_context"]["same_task_continuation"] is True
    assert payload["hard_validation_contract"]["applies_to_every_repair_response"] is True
    assert payload["exact_edit_hints"][0]["exact_live_line"] == "  enabled = true"
    assert "never the full file" in payload["repair_edit_output_shape"]["repair_edits"][0]["new_text"]


def test_generation_hard_validation_aggregates_preservation_and_precommit_rules():
    def enforce(result, _ctx):
        raise ValueError("preservation failed")

    def parallel(_result, _prompt, _thread):
        raise ValueError("semantic failed")

    ns = {
        "enforce_modification_uses_backend_matched_files": enforce,
        "_run_parallel_precommit_validations": parallel,
    }
    _exec_function(GEN, "_teams_run_generation_hard_validations", ns)
    try:
        ns["_teams_run_generation_hard_validations"]({"files": []}, "prompt", "conv", [])
    except ValueError as exc:
        text = str(exc)
    else:
        raise AssertionError("expected hard validation failure")
    assert "preservation failed" in text
    assert "semantic failed" in text


def test_generation_loop_repairs_in_same_conversation_and_revalidates_candidate():
    text = _source(GEN)
    assert "conversation_id=repair_conversation_id or None" in text
    assert "candidate_result = _teams_run_generation_hard_validations(" in text
    assert "agent_result = _teams_run_generation_hard_validations(" in text
    assert "repeating the same outer validation would only" in text


def test_initial_generation_prompt_contains_same_hard_contract():
    text = _source(ROUTER)
    assert 'payload["backend_hard_validation_contract"]' in text
    assert '"applies_to_first_generation_and_every_repair": True' in text
    assert "Do not rely on a later repair round" in text


def test_patch_preserves_all_preexisting_function_names():
    originals = {
        REPAIR: Path("/mnt/data/09_repair_pipeline(9).py"),
        GEN: Path("/mnt/data/07_teams_generation_flow(8).py"),
        ROUTER: Path("/mnt/data/10_teams_router_runtime(10).py"),
    }
    for patched, original in originals.items():
        if not original.exists():
            continue
        missing = _function_names(original) - _function_names(patched)
        assert not missing, f"functions removed from {patched.name}: {sorted(missing)}"
