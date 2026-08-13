# Terrabot repo-aware CLI and VS Code extension migration

This branch starts the migration from a backend-only Azure Function assistant to a local repo-aware infrastructure assistant.

## Target behavior

A developer opens an infra repository and asks:

```text
@terrabot add a private storage account for analytics in npr
```

Terrabot now has local building blocks to:

1. scan the current workspace,
2. detect Terraform, providers, cloud, tfvars layout, and pipelines,
3. infer the infrastructure workflow from repo evidence,
4. retrieve similar local examples,
5. apply a default company policy pack plus repo policy files,
6. build a compact context pack for a model/generator,
7. validate generated file contracts,
8. create a unified diff, and
9. surface missing values instead of inventing them.

## Commands

Run from the project root after installing the package, or directly with `python -m`:

```bash
python -m terrabot_cli.main scan --workspace /path/to/repo --json
python -m terrabot_cli.main explain-workflow --workspace /path/to/repo "add a private storage account for analytics in npr"
python -m terrabot_cli.main ask --workspace /path/to/repo "add a private storage account for analytics in npr" --diff
python -m terrabot_cli.main validate --workspace /path/to/repo
```

The `ask` command intentionally does not write files. It returns a plan, questions, source files, validation commands, and a diff only when generation has produced validated files.

## Generator contract

Set `TERRABOT_GENERATOR_COMMAND` to plug in a model process. The command receives the context pack JSON on stdin and must return JSON on stdout:

```json
{
  "summary": "Adds a repo-aware Terraform change.",
  "source_paths_used": ["storage_accounts.tf", "variables.tf"],
  "files": [
    {
      "path": "storage_accounts.tf",
      "operation": "modify",
      "content": "full final file content",
      "source_paths_used": ["storage_accounts.tf", "variables.tf"]
    }
  ],
  "questions": [],
  "validation_commands": ["terraform fmt -check -recursive", "terraform validate"]
}
```

Terrabot blocks generated files when they cite unknown evidence paths, traverse outside the workspace, contain obvious secrets, or policy checks fail.

## Repo overrides

A repo can optionally add `.terrabot/repo.json` or `.terrabot/repo.yaml` with lightweight hints:

```yaml
clouds: [azure]
iac_tools: [terraform]
environments: [sbx, npr, prd]
validation_commands: [pre-commit run --all-files]
```

Overrides are optional. The default path is inference from live repo files.
