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
    def test_strategy_implementation_projection_ignores_rebound_spec_approval(self) -> None:
        parent = {"implementation_plan": {"steps": []}, "source_context": {
            "harness_spec_ref": {"content_hash": "a"},
            "harness_spec_review_ref": {"content_hash": "parent"},
            "strategy_review_ref": {"content_hash": "same"},
        }}
        child = {**parent, "source_context": {**parent["source_context"],
            "harness_spec_ref": {"content_hash": "b"},
            "harness_spec_review_ref": {"content_hash": "budget-certificate"}}}
        self.assertEqual(MODULE.implementation_projection(parent), MODULE.implementation_projection(child))

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

    def test_ordinary_target_exception_is_retained_without_freezing_feedback(self) -> None:
        snapshot = {"record_format_version": "1.0", "runtime_version": "1.1",
            "artifact_id": "ha_test", "generation_key": "1" * 64, "snapshot_kind": "final",
            "snapshot_interval": 1, "site_count": 0, "started_iterations": 1,
            "finished_iterations": 1, "unwound_iterations": 0, "invalid_site_records": 0,
            "export_failures": 0, "site_counts": []}
        record = {"identity": {"execution_id": "ex_round"}, "source_context": {
            "instrumentation_contract_version": "1.0", "instrumentation_runtime_ref": {"artifact_version": "1.1"}},
            "execution": {"termination": {"reason": "time_budget_reached"}}, "evidence": {
                "candidate_evidence": {"status": "present", "observations": [{"observation_kind": "target_exception"}]},
                "runtime_snapshot": {"snapshot_kind": "final", "staleness_iterations": 0}}}
        resolved = MODULE.ResolvedRound(round_record=record, runtime_snapshot=snapshot,
            harness_artifact={"identity": {"harness_artifact_id": "ha_test", "generation_key": "1" * 64}, "instrumentation_map": []},
            strategy={}, harness_spec={"exploration_plan": {"branches": []}}, prior_decisions=(), prior_decision_refs=(),
            policy={"evidence_thresholds": {"maximum_branch_activation_check_error_count": 0, "minimum_completed_iterations": 1}},
            input_references={}, evidence_issue_codes=())
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


class FeedbackVocabularyTests(unittest.TestCase):
    def test_diagnosis_names_are_version_bound(self):
        schema = json.loads(MODULE.DEFAULT_DECISION_SCHEMA.read_text())
        validator = Draft202012Validator(schema["allOf"][-1])
        record = {"record_format_version": "1.2", "round_assessment": {
            "round_gate": {"result": "crash_or_sanitizer_candidate"},
            "branch_diagnoses": [{"primary_status": "branch_target_unreachable", "supporting_statuses": ["branch_healthy"]}]}}
        self.assertFalse(list(validator.iter_errors(record)))
        record["record_format_version"] = "1.3"
        self.assertTrue(list(validator.iter_errors(record)))
        record["round_assessment"] = {"round_gate": {"result": "abnormal_candidate_observed"},
                                      "branch_diagnoses": [{"primary_status": "branch_target_not_observed", "supporting_statuses": ["branch_no_detected_bottleneck"]}]}
        self.assertFalse(list(validator.iter_errors(record)))
        record["record_format_version"] = "1.2"
        self.assertTrue(list(validator.iter_errors(record)))

    def test_current_policy_and_controller_agree(self):
        policy = MODULE.validate_policy(json.loads(MODULE.DEFAULT_POLICY.read_text()))
        self.assertIn("abnormal_candidate_observed", json.dumps(policy))
        self.assertNotIn("crash_or_sanitizer_candidate", json.dumps(policy))
        self.assertIn("branch_target_not_observed", MODULE.BRANCH_STATUS_ORDER)
        self.assertIn("branch_no_detected_bottleneck", MODULE.BRANCH_STATUS_ORDER)


class ConditionFeedbackTests(unittest.TestCase):
    def test_real_static_artifacts_keep_conditions_independent(self):
        root = ROOT.parent / "EXP011_bug_aware_harness_synthesis"
        pairs = [
            (root / "harness_specs/pytorch/torch.batch_norm_update_stats/bug_aware_static/hs_pytorch_torch.batch_norm_update_stats_bug_aware_static_r6.json",
             root / "strategy_primitives/plans/pytorch/torch_batch_norm_update_stats/bug_aware_static/st_hs_pytorch_torch_batch_norm_update_stats_bug_aware_static_hsr006_r002.json",
             next((root / "harnesses/pytorch/torch_batch_norm_update_stats/bug_aware_static").glob("*/harness_artifact.json"))),
            (root / "harness_specs/pytorch/torch.nn.functional.cosine_embedding_loss/bug_aware_static/hs_pytorch_torch.nn.functional.cosine_embedding_loss_bug_aware_static_r4.json",
             root / "strategy_primitives/plans/pytorch/torch_nn_functional_cosine_embedding_loss/bug_aware_static/st_hs_pytorch_torch_nn_functional_cosine_embedding_loss_bug_aware_static_hsr004_r002.json",
             next((root / "harnesses/pytorch/torch_nn_functional_cosine_embedding_loss/bug_aware_static").glob("*/harness_artifact.json"))),
        ]
        for spec_path, strategy_path, artifact_path in pairs:
            spec = json.loads(spec_path.read_text())
            strategy = json.loads(strategy_path.read_text())
            artifact = json.loads(artifact_path.read_text())
            MODULE.verify_static_h0_reviews(spec, strategy, artifact, spec_path, strategy_path)
            kinds = ["branch_entered", "target_api_reached", "target_api_completed"]
            counts = [0] * len(artifact["instrumentation_map"])
            for entry in artifact["instrumentation_map"]:
                if entry["event_kind"] in kinds:
                    counts[entry["runtime_site_id"]] = 25
                if entry["event_kind"] == "activation_checked":
                    counts[entry["runtime_site_id"]] = 25
                if entry["event_kind"] in {"activation_true", "activation_unevaluable", "activation_check_error"}:
                    counts[entry["runtime_site_id"]] = 0
            result = MODULE.branch_measurements(spec, artifact, {"site_count": len(counts), "site_counts": counts})
            for branch, measurement in zip(spec["exploration_plan"]["branches"], result):
                conditions = measurement["measurements"]["condition_measurements"]
                self.assertEqual(len(conditions), sum(len(c["observe_at"]) for c in branch["target_conditions"]))
                if conditions:
                    diagnosis = MODULE.diagnose_branch(measurement, MODULE.validate_policy(json.loads(MODULE.DEFAULT_POLICY.read_text())))
                    self.assertEqual(diagnosis["primary_status"], "branch_activation_absent")
                    self.assertEqual(diagnosis["trigger_condition"]["condition_id"], conditions[0]["condition_id"])
                    self.assertTrue(all(c["checked"] == 25 and c["true"] == 0 for c in conditions))
                    self.assertEqual(measurement["measurements"]["input_rejected_count"], 0)

    def test_bounded_restore_never_exceeds_transfer_cap(self):
        current = {"default": 68, "a": 94, "b": 94}
        target = {"default": 100, "a": 78, "b": 78}
        step = MODULE.bounded_step_toward(current, target, 16)
        self.assertEqual(sum(step.values()), 256)
        self.assertEqual(sum(max(0, step[k] - current[k]) for k in current), 16)
        self.assertEqual(sum(max(0, current[k] - step[k]) for k in current), 16)

    def test_unevaluable_attempts_do_not_substitute_for_successful_checks(self):
        measured = {"branch_id": "br_test", "instrumentation_binding_refs": [], "measurements": {
            "branch_selected_count": 100, "target_reached_count": 100, "input_rejected_count": 0,
            "target_exception_count": 0, "activation_required": False, "activation_checked_count": None,
            "activation_true_count": None, "activation_unevaluable_count": None,
            "activation_check_error_count": None, "oracle_required": False,
            "oracle_opportunity_count": None, "oracle_evaluated_count": None,
            "condition_measurements": [{"condition_id": "tc_test", "role": "exploration_variable",
                "observe_at": "before_target_api_call", "state": "available", "checked": 1,
                "true": 0, "unevaluable": 99, "error": 0, "rate": 0.0, "binding_refs": []}],
            "behavior_check_measurements": []}}
        policy = MODULE.validate_policy(json.loads(MODULE.DEFAULT_POLICY.read_text()))
        diagnosis = MODULE.diagnose_branch(measured, policy)
        self.assertEqual(diagnosis["primary_status"], "branch_under_sampled")
        self.assertIsNone(diagnosis["trigger_condition"])

    def test_missing_condition_does_not_erase_an_independent_observable_condition(self):
        root = ROOT.parent / "EXP011_bug_aware_harness_synthesis"
        spec = json.loads((root / "harness_specs/pytorch/torch.nn.functional.cosine_embedding_loss/bug_aware_static/hs_pytorch_torch.nn.functional.cosine_embedding_loss_bug_aware_static_r4.json").read_text())
        artifact_path = next((root / "harnesses/pytorch/torch_nn_functional_cosine_embedding_loss/bug_aware_static").glob("*/harness_artifact.json"))
        artifact = json.loads(artifact_path.read_text())
        branch = next(item for item in spec["exploration_plan"]["branches"] if len(item["target_conditions"]) > 1)
        unavailable_id = branch["target_conditions"][1]["condition_id"]
        counts = [0] * len(artifact["instrumentation_map"])
        base = {"branch_entered", "target_api_reached", "target_api_completed"}
        condition_events = {"activation_checked", "activation_true", "activation_unevaluable", "activation_check_error", "observation_captured"}
        for entry in artifact["instrumentation_map"]:
            if entry["event_kind"] in base:
                counts[entry["runtime_site_id"]] = 25
            if entry["event_kind"] == "activation_checked":
                counts[entry["runtime_site_id"]] = 25
            if entry["event_kind"] in condition_events and any(ref.get("ref_id") == unavailable_id for ref in entry["trace_refs"]):
                entry["trace_refs"] = [dict(ref, ref_id="unbound_condition") if ref.get("ref_id") == unavailable_id else ref for ref in entry["trace_refs"]]
        measured = MODULE.branch_measurements(spec, artifact, {"site_count": len(counts), "site_counts": counts})
        row = next(item for item in measured if item["branch_id"] == branch["branch_id"])
        diagnosis = MODULE.diagnose_branch(row, MODULE.validate_policy(json.loads(MODULE.DEFAULT_POLICY.read_text())))
        conditions = diagnosis["measurements"]["condition_measurements"]
        self.assertEqual(conditions[0]["state"], "available")
        self.assertEqual(conditions[1]["state"], "missing_or_ambiguous_instrumentation")
        self.assertEqual(diagnosis["primary_status"], "branch_activation_absent")
        self.assertTrue(diagnosis["budget_evidence_usable"])

    def test_secondary_unobservable_required_check_disqualifies_donor_only(self):
        measured = {"branch_id": "br_test", "instrumentation_binding_refs": [], "measurements": {
            "branch_selected_count": 100, "target_reached_count": 100, "input_rejected_count": 0,
            "target_exception_count": 0, "target_exception_observation_state": "available",
            "activation_required": False, "activation_checked_count": None, "activation_true_count": None,
            "activation_unevaluable_count": None, "activation_check_error_count": None,
            "oracle_required": False, "oracle_opportunity_count": None, "oracle_evaluated_count": None,
            "condition_measurements": [{"condition_id": "tc_test", "role": "exploration_variable",
                "observe_at": "before_target_api_call", "state": "available", "checked": 25,
                "true": 0, "unevaluable": 0, "error": 0, "rate": 0.0, "binding_refs": []}],
            "behavior_check_measurements": [{"check_id": "bc_test", "requirement_level": "required",
                "state": "available", "opportunities": 25, "evaluated": 0, "binding_refs": []}]}}
        diagnosis = MODULE.diagnose_branch(measured, MODULE.validate_policy(json.loads(MODULE.DEFAULT_POLICY.read_text())))
        self.assertEqual(diagnosis["primary_status"], "branch_activation_absent")
        self.assertIn("branch_oracle_unevaluable", diagnosis["supporting_statuses"])
        self.assertTrue(diagnosis["budget_recipient_evidence_usable"])
        self.assertFalse(diagnosis["budget_donor_evidence_usable"])

    def test_policy_hash_is_frozen_within_repeat(self):
        validator = MODULE.schema_validator(MODULE.DEFAULT_DECISION_SCHEMA, "Feedback Decision")
        schema = json.loads(MODULE.DEFAULT_DECISION_SCHEMA.read_text())
        self.assertIn("1.4", schema["properties"]["record_format_version"]["enum"])
        self.assertIn("1.5", schema["properties"]["record_format_version"]["enum"])


if __name__ == "__main__":
    unittest.main()
