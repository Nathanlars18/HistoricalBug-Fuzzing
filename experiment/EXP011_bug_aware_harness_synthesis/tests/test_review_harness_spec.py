#!/usr/bin/env python3
"""External HarnessSpec review-record regression tests."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path("experiment/EXP011_bug_aware_harness_synthesis")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


BUILDER = load_module("review_test_builder", ROOT / "scripts/build_harness_spec_json.py")
REVIEW = load_module("review_harness_spec", ROOT / "scripts/review_harness_spec.py")
SEMANTICS = load_module(
    "review_test_fixtures", ROOT / "tests/test_harness_spec_semantics.py"
)


class ReviewHarnessSpecTests(unittest.TestCase):
    def build_spec(self) -> dict:
        contract = json.loads(
            (ROOT / "schemas/harness_spec_synthesis_contract.json").read_text()
        )
        api = SEMANTICS.api_profile()
        plan = {
            "knowledge_plan": {"knowledge_decisions": []},
            "validity_constraints": {"global_constraints": []},
            "exploration_plan": {"branches": [SEMANTICS.baseline_branch()]},
        }
        plan = BUILDER.normalize_plan(plan, contract, [])
        BUILDER.validate_plan(plan, "controlled_baseline", [], api, contract)
        helper = {
            "profile_id": "hp_create_tensor", "revision": 1,
            "metadata": {"content_hash": "c" * 64},
        }
        return BUILDER.assemble_record(
            plan, SEMANTICS.builder_args(), api, [helper], [], None, None, None,
            "run_review_test", SEMANTICS.trace_ref(),
        )

    def invoke(self, argv: list[str]) -> tuple[int, dict]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = REVIEW.main(argv)
        payload = json.loads((stdout if code == 0 else stderr).getvalue())
        return code, payload

    def test_review_revisions_are_immutable_and_parent_linked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            spec_path = temporary / "spec.json"
            spec_path.write_text(json.dumps(self.build_spec()), encoding="utf-8")
            output_root = temporary / "reviews"
            artifact_root = temporary / "review_artifacts"
            common = [
                "--harness-spec", str(spec_path), "--decision", "approved",
                "--reviewer", "reviewer-a", "--output-root", str(output_root),
                "--review-artifacts", str(artifact_root),
            ]
            code, first = self.invoke(common)
            self.assertEqual(code, 0, first)
            first_path = Path(first["output_path"])
            self.assertTrue(first_path.exists())
            first_record = json.loads(first_path.read_text())
            self.assertEqual(first_record["review_revision"], 1)
            self.assertIsNone(first_record["parent_review_ref"])
            self.assertIn("__sha256_", first_record["rules_ref"]["artifact_id"])

            code, second = self.invoke(common + [
                "--review-revision", "2", "--parent-review", str(first_path),
                "--dry-run",
            ])
            self.assertEqual(code, 0, second)
            self.assertEqual(second["review_revision"], 2)

    def test_non_object_finding_is_structured_input_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec_path = Path(directory) / "spec.json"
            spec_path.write_text(json.dumps(self.build_spec()), encoding="utf-8")
            code, payload = self.invoke([
                "--harness-spec", str(spec_path), "--decision", "approved",
                "--reviewer", "reviewer-a", "--finding-json", "[]", "--dry-run",
            ])
            self.assertEqual(code, 2)
            self.assertIn("must be a JSON object", payload["message"])

    def test_whitespace_reviewer_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec_path = Path(directory) / "spec.json"
            spec_path.write_text(json.dumps(self.build_spec()), encoding="utf-8")
            code, payload = self.invoke([
                "--harness-spec", str(spec_path), "--decision", "approved",
                "--reviewer", "   ", "--dry-run",
            ])
            self.assertEqual(code, 2)
            self.assertIn("non-whitespace", payload["message"])


if __name__ == "__main__":
    unittest.main()
