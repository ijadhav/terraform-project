from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shared_code import terraform_primary_context


class TerraformPrimaryContextTests(unittest.TestCase):
    def setUp(self) -> None:
        terraform_primary_context.clear_primary_context_cache()

    def tearDown(self) -> None:
        terraform_primary_context.clear_primary_context_cache()

    def test_loads_and_attaches_context_to_json_object(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.yaml"
            path.write_text("schema_version: test\nrules:\n  - preserve\n", encoding="utf-8")
            with patch.dict(
                os.environ,
                {
                    "TERRABOT_TERRAFORM_PRIMARY_CONTEXT_ENABLED": "true",
                    "TERRABOT_TERRAFORM_PRIMARY_CONTEXT_PATH": str(path),
                },
                clear=False,
            ):
                enriched = terraform_primary_context.attach_primary_context_to_agent_input(
                    json.dumps({"prompt": "change one flag"})
                )

        payload = json.loads(enriched)
        self.assertEqual(payload["prompt"], "change one flag")
        context = payload["terraform_primary_context"]
        self.assertEqual(context["format"], "yaml")
        self.assertIn("preserve", context["content"])
        self.assertEqual(len(context["sha256"]), 64)
        self.assertEqual(
            context["authority"],
            "repository_conventions_only_live_selected_commit_wins",
        )

    def test_non_json_input_is_left_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.yaml"
            path.write_text("schema_version: test\n", encoding="utf-8")
            with patch.dict(
                os.environ,
                {
                    "TERRABOT_TERRAFORM_PRIMARY_CONTEXT_ENABLED": "true",
                    "TERRABOT_TERRAFORM_PRIMARY_CONTEXT_PATH": str(path),
                },
                clear=False,
            ):
                original = "plain text prompt"
                self.assertEqual(
                    terraform_primary_context.attach_primary_context_to_agent_input(original),
                    original,
                )

    def test_missing_context_fails_open(self) -> None:
        with patch.dict(
            os.environ,
            {
                "TERRABOT_TERRAFORM_PRIMARY_CONTEXT_ENABLED": "true",
                "TERRABOT_TERRAFORM_PRIMARY_CONTEXT_PATH": "/missing/context.yaml",
            },
            clear=False,
        ):
            original = json.dumps({"prompt": "test"})
            self.assertEqual(
                terraform_primary_context.attach_primary_context_to_agent_input(original),
                original,
            )

    def test_disabled_context_is_not_attached(self) -> None:
        with patch.dict(
            os.environ,
            {"TERRABOT_TERRAFORM_PRIMARY_CONTEXT_ENABLED": "false"},
            clear=False,
        ):
            original = json.dumps({"prompt": "test"})
            self.assertEqual(
                terraform_primary_context.attach_primary_context_to_agent_input(original),
                original,
            )


if __name__ == "__main__":
    unittest.main()
