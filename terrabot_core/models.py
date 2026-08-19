from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Dict, List, Optional


@dataclass
class TerraformBlock:
    path: str
    block_type: str
    labels: List[str] = field(default_factory=list)
    name: Optional[str] = None
    source: Optional[str] = None
    provider: Optional[str] = None
    start_line: int = 0
    end_line: int = 0
    snippet: str = ""


@dataclass
class TerraformRoot:
    path: str
    root_type: str
    providers: List[str] = field(default_factory=list)
    module_count: int = 0
    resource_count: int = 0
    variable_count: int = 0


@dataclass
class PipelineProfile:
    path: str
    system: str
    terraform_version: Optional[str] = None
    var_files: List[str] = field(default_factory=list)
    environments: List[str] = field(default_factory=list)
    validation_templates: List[str] = field(default_factory=list)


@dataclass
class RepoProfile:
    root: str
    repo_name: str
    languages: List[str] = field(default_factory=list)
    iac_tools: List[str] = field(default_factory=list)
    clouds: List[str] = field(default_factory=list)
    terraform_roots: List[TerraformRoot] = field(default_factory=list)
    providers: List[str] = field(default_factory=list)
    modules: List[TerraformBlock] = field(default_factory=list)
    resources: List[TerraformBlock] = field(default_factory=list)
    variables: List[TerraformBlock] = field(default_factory=list)
    data_sources: List[TerraformBlock] = field(default_factory=list)
    tfvars_files: List[str] = field(default_factory=list)
    environments: List[str] = field(default_factory=list)
    pipelines: List[PipelineProfile] = field(default_factory=list)
    pipeline_systems: List[str] = field(default_factory=list)
    pipeline_files: List[str] = field(default_factory=list)
    validation_commands: List[str] = field(default_factory=list)
    policy_files: List[str] = field(default_factory=list)
    repo_conventions: Dict[str, Any] = field(default_factory=dict)
    file_count: int = 0


@dataclass
class EvidenceItem:
    path: str
    reason: str
    score: float = 0.0
    kind: str = "file"
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    snippet: str = ""


@dataclass
class WorkflowProfile:
    workflow_type: str
    confidence: float
    cloud: Optional[str] = None
    resource_type: Optional[str] = None
    target_environment: Optional[str] = None
    target_files: List[str] = field(default_factory=list)
    value_files: List[str] = field(default_factory=list)
    validation_commands: List[str] = field(default_factory=list)
    apply_strategy: str = "review_patch_then_apply"
    evidence: List[EvidenceItem] = field(default_factory=list)
    needs_clarification: bool = False
    clarification_reason: Optional[str] = None
    questions: List[str] = field(default_factory=list)


@dataclass
class PolicyResult:
    allowed: bool = True
    blocking_issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    rules_applied: List[str] = field(default_factory=list)
    source_files: List[str] = field(default_factory=list)


@dataclass
class PatchFile:
    path: str
    operation: str
    content: Optional[str] = None
    source_paths_used: List[str] = field(default_factory=list)
    # Typed/safe edit fields used by the VS Code + Functions pipeline.
    # These must survive the HTTP generator -> GenerationPlan -> API response
    # round-trip; otherwise insert_into_block/fill operations lose their
    # target metadata and get rejected server-side.
    block: Optional[str] = None
    lines: List[str] = field(default_factory=list)
    anchor: Optional[str] = None
    replacements: List[Dict[str, str]] = field(default_factory=list)
    in_place: bool = False


@dataclass
class GenerationPlan:
    status: str
    summary: str
    workflow: WorkflowProfile
    evidence: List[EvidenceItem] = field(default_factory=list)
    policy: Optional[PolicyResult] = None
    files: List[PatchFile] = field(default_factory=list)
    diff: str = ""
    questions: List[str] = field(default_factory=list)
    source_paths_used: List[str] = field(default_factory=list)
    context_pack: Dict[str, Any] = field(default_factory=dict)
    validation_commands: List[str] = field(default_factory=list)


def to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {k: to_jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v) for v in value]
    return value


def unique_preserve_order(values: List[str]) -> List[str]:
    seen = set()
    out = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out
