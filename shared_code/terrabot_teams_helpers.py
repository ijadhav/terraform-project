from __future__ import annotations


def repair_response_contract(all_existing_files: bool) -> dict:
    if all_existing_files:
        return {
            "json_only": True,
            "questions_must_be_empty": True,
            "must_include_one_of": ["repair_edits"],
            "required_for_existing_files": "repair_edits",
            "semantic_owner": "foundry",
            "backend_role": "exact_live_file_edit_materialization_and_validation_only",
        }
    return {
        "json_only": True,
        "questions_must_be_empty": True,
        "must_include_one_of": ["repair_edits", "files"],
        "semantic_owner": "foundry",
        "backend_role": "exact_live_file_edit_materialization_and_validation_only",
    }


def repair_protocol(all_existing_files: bool) -> list[str]:
    protocol = [
        "Use the exact backend-supplied existing_live_content as repository truth for every existing file.",
        "Never reconstruct an existing file from memory, prior generated output, summaries, or snippets.",
        "For an existing file, select the smallest exact old_text from existing_live_content that implements original_user_request and return repair_edits[].",
        "old_text must occur exactly once in existing_live_content. Include exact surrounding context only when needed for uniqueness.",
        "new_text must be a complete replacement for old_text and must have the same HCL delimiter balance as old_text.",
        "Do not use a whole file, most of a file, or a large unrelated block as old_text when a smaller assignment/block can implement the request.",
        "Preserve every byte outside the selected old_text span. No formatting-only edits, reorderings, unrelated renames, removals, or cleanup are permitted.",
        "For Boolean enable/disable, replace only the exact repository Boolean assignment or the smallest enclosing assignment context needed for uniqueness.",
        "For ordinary modifications, replace only the exact affected attribute/block fragment. Do not return the entire existing file in repair mode.",
        "Before responding, verify the edit directly implements original_user_request and specifically eliminates backend_validation_error.",
        "If the rejected output was truncated or overwrote unrelated code, do not repair that generated output. Start again from existing_live_content and return a surgical repair_edits[] replacement.",
        "A repair turn may not ask the user questions. Return strict JSON only and set questions=[] if present.",
    ]
    if all_existing_files:
        protocol.append("HARD CONTRACT: every repair target already exists in the repository, therefore files[] is invalid for this repair turn; return repair_edits[] only.")
    else:
        protocol.append("For a genuinely new file with no existing_live_content, files[] may contain that complete new file; existing files must still use repair_edits[].")
    return protocol
