#!/usr/bin/env python3
"""Focused tests for deterministic Runtime Snapshot attribution."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_feedback_controller.py"
SPEC = importlib.util.spec_from_file_location("run_feedback_controller", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FeedbackControllerSnapshotTests(unittest.TestCase):
    def test_snapshot_without_execution_id_is_eligible(self) -> None:
        snapshot = {
            "record_format_version": "1.0",
            "runtime_version": "1.0",
            "artifact_id": "ha_test",
            "generation_key": "1" * 64,
            "snapshot_kind": "final",
            "snapshot_interval": 1,
            "site_count": 0,
            "started_iterations": 2,
            "finished_iterations": 2,
            "unwound_iterations": 0,
            "invalid_site_records": 0,
            "export_failures": 0,
            "site_counts": [],
        }
        round_record = {
            "identity": {"execution_id": "ex_round_owned_identity"},
            "source_context": {
                "instrumentation_contract_version": "1.0",
                "instrumentation_runtime_ref": {"artifact_version": "1.0"},
            },
            "execution": {"termination": {"reason": "time_budget_reached"}},
            "evidence": {
                "candidate_evidence": {"status": "absent", "observations": []},
                "runtime_snapshot": {
                    "snapshot_kind": "final",
                    "staleness_iterations": 0,
                },
            },
        }
        resolved = MODULE.ResolvedRound(
            round_record=round_record,
            runtime_snapshot=snapshot,
            harness_artifact={
                "identity": {
                    "harness_artifact_id": "ha_test",
                    "generation_key": "1" * 64,
                },
                "instrumentation_map": [],
            },
            strategy={},
            harness_spec={"exploration_plan": {"branches": []}},
            prior_decisions=(),
            prior_decision_refs=(),
            policy={
                "evidence_thresholds": {
                    "maximum_branch_activation_check_error_count": 0,
                    "minimum_completed_iterations": 1,
                }
            },
            input_references={},
            evidence_issue_codes=(),
        )

        assessment = MODULE.assess_round(resolved)

        self.assertEqual(assessment.round_gate, {"result": "eligible", "issue_codes": []})

    def test_static_h0_may_have_noninitial_revision_number(self) -> None:
        harness_spec = {
            "identity": {"spec_mode": "bug_aware_static"},
            "revision_information": {
                "revision_number": 2,
                "feedback_request_ref": None,
            },
        }
        MODULE.validate_feedback_spec_origin(harness_spec)

    def test_feedback_derived_static_spec_is_not_h0(self) -> None:
        harness_spec = {
            "identity": {"spec_mode": "bug_aware_static"},
            "revision_information": {
                "revision_number": 2,
                "feedback_request_ref": {
                    "artifact_id": "feedback_request_test",
                    "artifact_version": 1,
                    "content_hash": "1" * 64,
                },
            },
        }
        with self.assertRaisesRegex(
            MODULE.RoundInputError,
            "must not be derived from a Feedback Request",
        ):
            MODULE.validate_feedback_spec_origin(harness_spec)

    def test_multiple_target_calls_use_branch_level_counts(self) -> None:
        harness_spec = {
            "exploration_plan": {
                "branches": [
                    {
                        "branch_id": "br_test",
                        "activation_targets": [],
                        "oracle_requirements": [
                            {"requirement_level": "required"}
                        ],
                    }
                ]
            }
        }
        event_kinds = [
            "branch_entered",
            "target_api_reached",
            "target_api_reached",
            "target_api_completed",
            "target_api_completed",
            "oracle_evaluated",
        ]
        harness_artifact = {
            "instrumentation_map": [
                {
                    "runtime_site_id": site_id,
                    "instrumentation_binding_id": f"ins_{site_id}",
                    "branch_id": "br_test",
                    "event_kind": event_kind,
                }
                for site_id, event_kind in enumerate(event_kinds)
            ]
        }
        snapshot = {
            "site_count": len(event_kinds),
            "site_counts": [10, 10, 10, 10, 9, 9],
        }

        measured = MODULE.branch_measurements(
            harness_spec,
            harness_artifact,
            snapshot,
        )

        values = measured[0]["measurements"]
        self.assertEqual(values["branch_selected_count"], 10)
        self.assertEqual(values["target_reached_count"], 10)
        self.assertEqual(values["oracle_opportunity_count"], 9)
        self.assertEqual(values["oracle_evaluated_count"], 9)

    def test_runtime_schema_rejects_execution_id(self) -> None:
        schema_path = (
            ROOT.parent
            / "EXP014_experimental_evaluation/schemas/runtime_snapshot.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        snapshot = {
            "record_format_version": "1.0",
            "runtime_version": "1.0",
            "artifact_id": "ha_test",
            "generation_key": "1" * 64,
            "snapshot_kind": "final",
            "snapshot_interval": 1,
            "site_count": 0,
            "started_iterations": 0,
            "finished_iterations": 0,
            "unwound_iterations": 0,
            "invalid_site_records": 0,
            "export_failures": 0,
            "site_counts": [],
            "execution_id": "not_owned_by_runtime_snapshot",
        }
        self.assertTrue(list(Draft202012Validator(schema).iter_errors(snapshot)))


if __name__ == "__main__":
    unittest.main()
