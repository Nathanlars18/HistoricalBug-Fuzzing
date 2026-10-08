#!/usr/bin/env python3
"""Focused checks for immutable external Strategy review records."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path("experiment/EXP011_bug_aware_harness_synthesis")
SCRIPT = ROOT / "scripts/review_strategy_plan.py"
SPEC = importlib.util.spec_from_file_location("review_strategy_plan", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def review(decision: str, findings: list[dict]) -> dict:
    return {
        "schema_version": "1.0",
        "review_id": "strategy_review:test:r1:rr1",
        "review_revision": 1,
        "parent_review_ref": None,
        "subject": {
            "strategy_id": "st_test",
            "revision_number": 1,
            "content_hash": "0" * 64,
            "relative_path": "plan.json",
        },
        "rules_ref": {
            "artifact_id": "strategy_plan_human_review_rules.md",
            "artifact_version": "1.0",
            "content_hash": "1" * 64,
            "relative_path": "rules.md",
        },
        "decision": decision,
        "findings": findings,
        "reviewer_id": "nathan",
        "reviewed_at": "2026-10-06T00:00:00Z",
        "review_notes": None,
    }


def blocking_finding() -> dict:
    return {
        "criterion_id": "SR-03",
        "severity": "blocking",
        "field_path": "$.implementation_plan",
        "evidence_ref": "strategy:st_test",
        "mismatch_summary": "Exploration variable was converted to a guard.",
    }


class StrategyReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(
            (ROOT / "schemas/strategy_plan_review_record.schema.json").read_text()
        )
        cls.validator = Draft202012Validator(cls.schema)

    def test_schema_is_valid(self) -> None:
        Draft202012Validator.check_schema(self.schema)

    def test_approved_forbids_blocking_finding(self) -> None:
        self.assertTrue(
            list(self.validator.iter_errors(review("approved", [blocking_finding()])))
        )

    def test_needs_revision_requires_blocking_finding(self) -> None:
        self.assertTrue(
            list(self.validator.iter_errors(review("needs_revision", [])))
        )
        self.assertEqual(
            list(self.validator.iter_errors(review("needs_revision", [blocking_finding()]))),
            [],
        )

    def test_rules_header_matches_script_version(self) -> None:
        rules = (
            ROOT / "schemas/strategy_plan_human_review_rules.md"
        ).read_text(encoding="utf-8")
        self.assertTrue(rules.startswith('# Strategy Plan Human Review Rules v1.2'))
        self.assertEqual(MODULE.RULES_VERSION, '1.2')

    def test_rules_freeze_is_content_addressed_and_idempotent(self) -> None:
        rules = ROOT / "schemas/strategy_plan_human_review_rules.md"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = MODULE.freeze_rules(rules, root)
            second = MODULE.freeze_rules(rules, root)
            self.assertEqual(first, second)
            frozen = Path(first["relative_path"])
            self.assertEqual(frozen.read_bytes(), rules.read_bytes())
            self.assertIn(first["content_hash"], frozen.name)


if __name__ == "__main__":
    unittest.main()
