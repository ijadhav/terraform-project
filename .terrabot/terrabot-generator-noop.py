#!/usr/bin/env python3
import json
import sys

data = json.load(sys.stdin)

context_pack = data.get("context_pack", data)
workflow = context_pack.get("workflow_profile") or data.get("workflow") or {}

evidence = context_pack.get("evidence") or data.get("evidence") or []
source_paths_used = []
for item in evidence:
    path = item.get("path")
    if path and path not in source_paths_used:
        source_paths_used.append(path)

validation_commands = (
    data.get("validation_commands")
    or context_pack.get("validation_commands")
    or workflow.get("validation_commands")
    or []
)

print(json.dumps({
    "summary": "Generator command is wired successfully. This test generator returns no file edits.",
    "source_paths_used": source_paths_used,
    "files": [],
    "questions": [],
    "validation_commands": validation_commands
}, indent=2))
