from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from terrabot_core.filesystem import iter_repo_files, normalize_path, read_text
from terrabot_core.models import EvidenceItem, RepoProfile, WorkflowProfile, unique_preserve_order

_RELEVANT_EXTENSIONS = {".tf", ".tfvars", ".hcl", ".md", ".yml", ".yaml", ".json", ".rego"}
_STOPWORDS = {
    "the",
    "a",
    "an",
    "to",
    "in",
    "for",
    "of",
    "and",
    "or",
    "with",
    "on",
    "add",
    "create",
    "new",
    "please",
    "private",
}


def _tokens(text: str) -> List[str]:
    words = re.findall(r"[a-zA-Z0-9_\-]+", (text or "").lower())
    return [w for w in words if len(w) > 2 and w not in _STOPWORDS]


def _line_window(content: str, terms: List[str], window: int = 12) -> Tuple[int, int, str]:
    lines = content.splitlines()
    best_idx = 0
    best_score = -1
    lowered_terms = [t.lower() for t in terms if t]
    for idx, line in enumerate(lines):
        lower = line.lower()
        score = sum(1 for term in lowered_terms if term in lower)
        if score > best_score:
            best_idx = idx
            best_score = score
    start = max(0, best_idx - 3)
    end = min(len(lines), start + window)
    return start + 1, end, "\n".join(lines[start:end])[:2500]


# Evidence size budgets. Floored (guaranteed) files ship full content up to
# _FULL_CONTENT_MAX bytes; larger files fall back to multi-window extraction.
# _TOTAL_EVIDENCE_BUDGET caps the sum of all snippet bytes in one request.
_FULL_CONTENT_MAX = 24 * 1024
_MULTI_WINDOW_MAX = 8 * 1024
_TOTAL_EVIDENCE_BUDGET = 160 * 1024
_FLAG_LINE_RE = re.compile(r"\b(create|enable|deploy)_[a-z0-9_]+\b|_enabled\b")


def _multi_window(content: str, terms: List[str], window: int = 12, max_chars: int = _MULTI_WINDOW_MAX) -> Tuple[int, int, str]:
    """Extract a window around EVERY line matching a prompt term or a
    feature-flag pattern, concatenated with gap markers — instead of a single
    best-scoring window that can miss the section the request is about
    (e.g. a create_cloudamqp flag at line 254 of a 300-line main.tf).
    """
    lines = content.splitlines()
    lowered_terms = [t.lower() for t in terms if t]
    anchors: List[int] = []
    for idx, line in enumerate(lines):
        lower = line.lower()
        if any(term in lower for term in lowered_terms) or _FLAG_LINE_RE.search(lower):
            anchors.append(idx)

    if not anchors:
        # No matches at all — fall back to the head of the file.
        end = min(len(lines), window)
        return 1, end, "\n".join(lines[:end])[:max_chars]

    # Merge overlapping windows around each anchor.
    half = max(2, window // 2)
    ranges: List[List[int]] = []
    for a in anchors:
        start = max(0, a - half)
        end = min(len(lines), a + half + 1)
        if ranges and start <= ranges[-1][1] + 1:
            ranges[-1][1] = max(ranges[-1][1], end)
        else:
            ranges.append([start, end])

    pieces: List[str] = []
    total = 0
    first_start = ranges[0][0] + 1
    last_end = ranges[0][1]
    for start, end in ranges:
        chunk_header = f"# --- lines {start + 1}-{end} ---"
        chunk = chunk_header + "\n" + "\n".join(lines[start:end])
        if total + len(chunk) > max_chars:
            break
        pieces.append(chunk)
        total += len(chunk)
        last_end = end
    return first_start, last_end, "\n".join(pieces)


def _evidence_snippet(content: str, terms: List[str], guaranteed: bool) -> Tuple[int, int, str]:
    """Choose the snippet strategy per file:
    - guaranteed (floored) small file  -> FULL content (nothing can be missed)
    - guaranteed large file            -> multi-window (all matching sections)
    - organic file                     -> original single best window
    """
    if guaranteed:
        if len(content) <= _FULL_CONTENT_MAX:
            line_count = content.count("\n") + 1
            return 1, line_count, content
        return _multi_window(content, terms)
    return _line_window(content, terms)


def _kind_for_path(path: str) -> str:
    lower = path.lower()
    if lower.endswith(".tfvars"):
        return "tfvars"
    if lower.endswith(".tf"):
        return "terraform"
    if lower.endswith((".yml", ".yaml")):
        return "pipeline" if "pipeline" in lower or ".github/workflows" in lower else "yaml"
    if lower.endswith(".md"):
        return "documentation"
    if lower.endswith(".rego"):
        return "policy"
    return "file"


def _score_file(path: str, content: str, prompt_terms: List[str], workflow: WorkflowProfile, profile: RepoProfile) -> Tuple[float, List[str]]:
    lower_path = path.lower()
    lower_content = (content or "").lower()
    score = 0.0
    reasons: List[str] = []

    for term in prompt_terms:
        if term in lower_path:
            score += 2.0
        if term in lower_content:
            score += 0.6

    if workflow.resource_type:
        resource_terms = workflow.resource_type.replace("_", " ").split() + [workflow.resource_type]
        if any(term in lower_path for term in resource_terms):
            score += 5.0
            reasons.append(f"path matches resource type {workflow.resource_type}")
        if any(term in lower_content for term in resource_terms):
            score += 2.0
            reasons.append(f"content mentions resource type {workflow.resource_type}")

    if workflow.target_environment:
        env = workflow.target_environment.lower()
        if f"/{env}/" in lower_path or env in lower_path.split("/"):
            score += 5.0
            reasons.append(f"matches target environment {env}")
        if env in lower_content and lower_path.endswith((".yml", ".yaml")):
            score += 2.0
            reasons.append(f"pipeline/content mentions {env}")

    if lower_path in [p.lower() for p in workflow.target_files]:
        score += 6.0
        reasons.append("selected by workflow inference")
    if lower_path in [p.lower() for p in workflow.value_files]:
        score += 6.0
        reasons.append("target environment value file")
    if lower_path in {"variables.tf", "outputs.tf", "locals.tf", "provider.tf", "versions.tf", "main.tf"}:
        score += 2.0
        reasons.append("core Terraform convention file")
    if lower_path in [p.lower() for p in profile.policy_files]:
        score += 1.5
        reasons.append("repo policy/convention file")
    if lower_path in [p.lower() for p in profile.pipeline_files]:
        score += 2.5
        reasons.append("repo pipeline file")
    if lower_path.endswith(".tfvars"):
        score += 1.5
        reasons.append("Terraform values file")

    return score, unique_preserve_order(reasons)


def _floor_reason_paths(
    prompt_terms: List[str],
    all_paths: List[str],
    profile: RepoProfile,
    workflow: WorkflowProfile,
) -> Dict[str, str]:
    """Paths that MUST appear in evidence regardless of score.

    Two guarantees:
    1. Prompt-named paths — any file whose repo-relative path contains a
       prompt token (e.g. "redshift", "auditdb") is included, so a module the
       user explicitly names can never be dropped by top-K scoring.
    2. Convention exemplars — a small set of representative Terraform files
       from the target environment (or each terraform root when no
       environment is resolved), so the agent can infer layout/wiring/secret
       conventions even when the requested resource type has no existing
       example in the repo.
    """
    floors: Dict[str, str] = {}

    # Generic tokens that appear in nearly every Terraform path would floor
    # half the repository — exclude them from the guarantee (they still count
    # for organic scoring).
    generic = {
        "modules", "module", "terraform", "main", "vars", "variables",
        "outputs", "locals", "file", "files", "infra", "infrastructure",
        "resource", "resources",
        # generic infra nouns that name a KIND of thing, not a thing:
        # "add an instance" must not floor every *_instance module.
        "instance", "instances", "separate", "cluster", "server", "service",
        "database", "storage", "network", "account", "using", "existing",
        "pattern", "environment", "instead",
    }
    candidate_terms = [t for t in prompt_terms if len(t) >= 4 and t not in generic]

    # Dynamic over-match guard: a term that floors a large share of the repo
    # is generic by definition (whatever the stoplist says). Drop terms whose
    # match count exceeds both an absolute cap and 10% of scanned paths.
    max_matches = max(10, len(all_paths) // 10)
    floor_terms: List[str] = []
    for term in candidate_terms:
        hits = sum(1 for rel in all_paths if term in rel.lower())
        if hits <= max_matches:
            floor_terms.append(term)

    # Guarantee 1: prompt-named paths.
    for rel in all_paths:
        lower = rel.lower()
        if any(term in lower for term in floor_terms):
            floors.setdefault(rel, "path matches prompt keyword (guaranteed inclusion)")

    # Guarantee 2: convention exemplars.
    # getattr guards: RepoProfile/WorkflowProfile fields may be absent or None
    # for repos with little/no IaC — never let a missing field raise.
    exemplar_names = {"main.tf", "variables.tf", "vars.tf", "outputs.tf", "locals.tf", "providers.tf", "provider.tf"}
    env = (getattr(workflow, "target_environment", "") or "").lower()
    roots = [str(r).lower().rstrip("/") for r in (getattr(profile, "terraform_roots", None) or [])]

    def _is_exemplar(rel: str) -> bool:
        lower = rel.lower()
        name = lower.rsplit("/", 1)[-1]
        if name not in exemplar_names and not lower.endswith(".tfvars"):
            return False
        if env:
            return f"/{env}/" in f"/{lower}" or f"/{env}." in lower or lower.startswith(f"{env}/")
        if roots:
            return any(lower.startswith(root + "/") or lower == root for root in roots)
        # No resolved environment and no known terraform roots: only floor
        # top-level core files, not every main.tf in the repository.
        return "/" not in lower

    per_dir_budget: Dict[str, int] = {}
    for rel in all_paths:
        if rel in floors:
            continue
        if not _is_exemplar(rel):
            continue
        parent = rel.rsplit("/", 1)[0] if "/" in rel else "."
        used = per_dir_budget.get(parent, 0)
        if used >= 3:  # at most 3 exemplars per directory
            continue
        per_dir_budget[parent] = used + 1
        floors.setdefault(rel, "convention exemplar for target environment/root (guaranteed inclusion)")

    return floors


def retrieve_context(workspace: str, prompt: str, profile: RepoProfile, workflow: WorkflowProfile, limit: int = 10) -> List[EvidenceItem]:
    workspace_path = Path(workspace).expanduser().resolve()
    prompt_terms = _tokens(prompt) + ([workflow.resource_type] if workflow.resource_type else []) + ([workflow.target_environment] if workflow.target_environment else [])
    scored: List[EvidenceItem] = []

    # Seed evidence from workflow inference so exact block matches are never lost.
    for item in workflow.evidence:
        if item.path != "<repo-profile>":
            scored.append(item)

    # Single pass: gather relative paths and contents.
    contents: Dict[str, str] = {}
    for path in iter_repo_files(workspace_path):
        if path.suffix.lower() not in _RELEVANT_EXTENSIONS and path.name not in {"CODEOWNERS", ".pre-commit-config.yaml", ".tool-versions"}:
            continue
        relative = normalize_path(str(path.relative_to(workspace_path)))
        text = read_text(path)
        if not text:
            continue
        contents[relative] = text

    # Floor: paths guaranteed into evidence regardless of score.
    # FAIL-OPEN: the floor is an enhancement — if it raises for any repo
    # shape, degrade to the original score-only behavior rather than
    # failing the whole generation request.
    try:
        floors = _floor_reason_paths(prompt_terms, list(contents.keys()), profile, workflow)
    except Exception:
        floors = {}

    # CloudAMQP second-instance refactors need the wrapper module AND the real
    # implementation module. Do not assume the implementation file is named
    # modules/vena_datacentre/cloudamqp.tf; many repos keep it under
    # modules/cloudamqp/*.tf and only expose it through a create_cloudamqp flag.
    try:
        prompt_text = " ".join(prompt_terms).lower()
        wants_cloudamqp = any(t in prompt_text for t in ("cloudamqp", "rabbitmq", "rabbit"))
        wants_second = any(t in prompt_text for t in ("second", "another", "additional", "multiple", "multi-instance"))
        if wants_cloudamqp and wants_second:
            for rel, text in contents.items():
                lower = rel.lower()
                name = lower.rsplit("/", 1)[-1]
                in_cloudamqp_module = "/modules/cloudamqp/" in f"/{lower}"
                in_vena_wrapper = "/modules/vena_datacentre/" in f"/{lower}"
                if in_cloudamqp_module and lower.endswith(".tf"):
                    floors.setdefault(rel, "CloudAMQP implementation module for second-instance refactor")
                elif in_vena_wrapper and lower.endswith(".tf") and (
                    name in {"vars.tf", "variables.tf", "outputs.tf"}
                    or "cloudamqp" in name
                    or "create_cloudamqp" in text.lower()
                    or "cloudamqp" in text.lower()
                ):
                    floors.setdefault(rel, "vena_datacentre CloudAMQP wrapper surface for second-instance refactor")
    except Exception:
        pass

    # Module-source following (fail-open): consumer blocks inside floored
    # environment files reference local module paths (source = "../../modules/x").
    # Pull those modules' variables/vars files into evidence too, so the agent
    # can discover feature flags (create_* / enable_*) and required inputs.
    try:
        module_dirs: set = set()
        src_re = re.compile(r'source\s*=\s*"((?:\.\./)+[^"]+|\./[^"]+)"')
        for rel in list(floors.keys()):
            text = contents.get(rel) or ""
            base_dir = rel.rsplit("/", 1)[0] if "/" in rel else ""
            for match in src_re.findall(text):
                parts = (base_dir.split("/") if base_dir else [])
                for seg in match.split("/"):
                    if seg == "..":
                        if parts:
                            parts.pop()
                    elif seg not in {".", ""}:
                        parts.append(seg)
                resolved = "/".join(parts)
                if resolved:
                    module_dirs.add(resolved)
        if module_dirs:
            flag_re = re.compile(r'\b(create|enable|deploy)_[a-z0-9_]+\b|_enabled\b')
            for rel, text in contents.items():
                parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
                if not any(parent == d or parent.startswith(d + "/") for d in module_dirs):
                    continue
                name = rel.rsplit("/", 1)[-1].lower()
                is_vars = name in {"vars.tf", "variables.tf"}
                has_flags = bool(flag_re.search(text))
                if is_vars or has_flags:
                    floors.setdefault(
                        rel,
                        "module referenced by environment consumer block "
                        + ("(variables file)" if is_vars else "(contains feature flags)"),
                    )
    except Exception:
        pass  # module following is best-effort; never break retrieval

    for relative, text in contents.items():
        score, reasons = _score_file(relative, text, prompt_terms, workflow, profile)
        floor_reason = floors.get(relative)
        if floor_reason:
            score = max(score, 100.0)  # pin above any organic score
            reasons = [floor_reason] + reasons
        if score <= 0:
            continue
        start, end, snippet = _evidence_snippet(text, prompt_terms, guaranteed=relative in floors)
        scored.append(
            EvidenceItem(
                path=relative,
                reason="; ".join(reasons) or "keyword match",
                score=score,
                kind=_kind_for_path(relative),
                start_line=start,
                end_line=end,
                snippet=snippet,
            )
        )

    by_path: Dict[str, EvidenceItem] = {}
    for item in sorted(scored, key=lambda x: x.score, reverse=True):
        existing = by_path.get(item.path)
        if not existing or item.score > existing.score:
            by_path[item.path] = item

    ordered = list(by_path.values())
    floored = [i for i in ordered if getattr(i, "path", None) in floors]
    others = [i for i in ordered if getattr(i, "path", None) not in floors]

    # Floored items always ship; organic top-K fills the remainder. The limit
    # stretches when floors alone exceed it (never silently drop a guaranteed
    # path), capped at 2x limit to bound payload size.
    # Include all guaranteed/floored files up to a larger safety cap. The old
    # limit*2 cap could still drop required files after explicitly flooring
    # them (for example modules/cloudamqp/main.tf when many environment
    # exemplars were also floored).
    floor_cap = max(limit * 2, 40)
    max_total = max(limit, min(len(floored), floor_cap))
    result = floored[:floor_cap] + others
    result = result[: max(max_total, limit)]

    # Total evidence byte budget: floored items are protected; trim organic
    # items first, then downgrade the largest floored snippets to
    # multi-window until the payload fits.
    def _size(item: EvidenceItem) -> int:
        return len(item.snippet or "")

    while sum(_size(i) for i in result) > _TOTAL_EVIDENCE_BUDGET and any(i.path not in floors for i in result):
        organic = [i for i in result if i.path not in floors]
        result.remove(max(organic, key=_size))

    if sum(_size(i) for i in result) > _TOTAL_EVIDENCE_BUDGET:
        # Downgrade the largest snippets to multi-window. EvidenceItem may be
        # immutable, so rebuild rather than mutate; fail-open on any error.
        try:
            for idx in sorted(range(len(result)), key=lambda i: _size(result[i]), reverse=True):
                if sum(_size(i) for i in result) <= _TOTAL_EVIDENCE_BUDGET:
                    break
                item = result[idx]
                text = contents.get(item.path)
                if not text or len(item.snippet or "") <= _MULTI_WINDOW_MAX:
                    continue
                s, e, snip = _multi_window(text, prompt_terms)
                result[idx] = EvidenceItem(
                    path=item.path,
                    reason=item.reason,
                    score=item.score,
                    kind=item.kind,
                    start_line=s,
                    end_line=e,
                    snippet=snip,
                )
        except Exception:
            pass

    return result
