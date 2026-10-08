#!/usr/bin/env python3
"""Deterministic HarnessSpec v2.2 boundary and semantic tests."""

from __future__ import annotations

import importlib.util
import contextlib
import io
import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from types import SimpleNamespace

from jsonschema import Draft202012Validator

ROOT = Path("experiment/EXP011_bug_aware_harness_synthesis")
SCRIPT = ROOT / "scripts/build_harness_spec_json.py"
CONTRACT_PATH = ROOT / "schemas/harness_spec_synthesis_contract.json"
RECORD_SCHEMA_PATH = ROOT / "schemas/harness_spec_record.schema.json"
RULES_PATH = ROOT / "schemas/knowledge_to_harness_spec_rules.md"
CORE_SCHEMA_PATH = ROOT / "schemas/harness_spec_record_core__v2_2.schema.json"
SPEC = importlib.util.spec_from_file_location("build_harness_spec_json", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def source_ref(source_type: str, source_id: str, source_path: str) -> dict:
    return {"source_type": source_type, "source_id": source_id, "source_path": source_path}


def trace_ref() -> dict:
    return {
        "artifact_id": "attempt_001.json",
        "artifact_version": "1.0",
        "content_hash": "d" * 64,
        "relative_path": "generation_traces/run_test/attempt_001.json",
    }


def review_ref() -> dict:
    return {
        "artifact_id": "review.json",
        "artifact_version": "1.1",
        "content_hash": "e" * 64,
        "relative_path": "harness_spec_reviews/review.json",
    }


def builder_args(**overrides: object) -> SimpleNamespace:
    values = {
        "mode": "controlled_baseline",
        "target_api": "torch.relu",
        "revision": 1,
        "revision_trigger": "initial_creation",
        "change_scope": ["initial_definition"],
        "change_summary": "Initial HarnessSpec synthesis",
        "model": "test-model",
        "contract": CONTRACT_PATH,
        "rules": RULES_PATH,
        "record_schema": RECORD_SCHEMA_PATH,
        "record_schema_core": CORE_SCHEMA_PATH,
        "review_record": None,
        "review_schema": ROOT / "schemas/harness_spec_review_record.schema.json",
        "dry_run": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def api_profile() -> dict:
    return {
        "profile_id": "api_pytorch_relu_default", "revision": 1,
        "metadata": {"content_hash": "a" * 64},
        "target": {"framework": "pytorch", "framework_version": "2.10.0",
                   "backend_scope": ["cpu"], "python_api": "torch.relu",
                   "callable_kind": "function"},
        "python_contract": {
            "parameters": [{"parameter_id": "param_input", "name": "input"}],
            "returns": [{"return_id": "return_output", "name": "output"}],
        },
        "target_binding": {"status": "resolved"}, "documented_constraints": [],
        "validation": {"validation_status": "passed", "execution_readiness": "ready"},
        "review": {"review_status": "approved"},
    }


def knowledge_record() -> dict:
    return {
        "schema_version": "3.0",
        "metadata": {"knowledge_id": "kn_pytorch_relu_001", "canonical_name": "relu_boundary"},
        "derivation_information": {"mapping_version": "3.1", "prompt_version": "knowledge_extract_v3_1"},
        "scope": {"framework": "pytorch", "target_api": "torch.relu"},
        "learned_hypothesis": {
            "statement": "A layout boundary may expose inconsistent output behavior.",
            "abstraction_rationale": "The historical case supports varying layout.",
            "evidence_status": "pattern_derived", "evidence_refs": ["pattern:test"],
            "limitations": ["The exact triggering layout is not established."],
        },
        "exploration_guidance": {
            "historical_anchors": [],
            "variation_opportunities": [{"statement": "Vary input layout.",
                "evidence_status": "analyst_inferred", "evidence_refs": ["pattern:test"]}],
            "observation_candidates": [{"statement": "Observe output shape and values.",
                "evidence_status": "pattern_derived", "evidence_refs": ["pattern:test"]}],
        },
    }


def property_predicate() -> dict:
    return {"predicate_id": "property_relation", "arguments": {
        "subject_ref": "param_input", "property_ref": "layout.contiguous",
        "operator": "equals", "value": False},
        "description": "The layout remains fuzz-derived around contiguity."}


def baseline_branch() -> dict:
    return {"branch_id": "default_candidate", "branch_kind": "default",
            "input_validity_intent": "expected_valid",
            "input_validity_basis": {
                "basis_kind": "canonical_baseline_definition", "source_refs": [],
                "summary": "Canonical controlled-Baseline definition."},
            "source_knowledge_ids": [],
            "grouping_summary": None,
            "exploration_goal": "Exercise API-valid inputs derived from raw fuzz bytes.",
            "exploration_goal_source_refs": [],
            "branch_constraints": [], "target_conditions": [],
            "behavior_observations": [], "behavior_checks": []}


def valid_plan() -> dict:
    knowledge_id = "kn_pytorch_relu_001"
    hypothesis_ref = source_ref("knowledge", knowledge_id, "/learned_hypothesis")
    variation_ref = source_ref("knowledge", knowledge_id,
                               "/exploration_guidance/variation_opportunities/0")
    return {
        "knowledge_plan": {"knowledge_decisions": [{
            "knowledge_id": knowledge_id, "disposition": "included",
            "branch_ids": ["knowledge_candidate"],
            "decision_summary": "Use supported variation without fixing a reproducer.",
            "component_mappings": [
                {"source_path": "/learned_hypothesis", "mapping_status": "represented",
                 "spec_element_refs": [{"branch_id": "knowledge_candidate",
                     "element_type": "exploration_goal", "element_id": None}],
                 "represented_scope": None, "deferred_scope": None,
                 "decision_summary": None},
                {"source_path": "/exploration_guidance/variation_opportunities/0",
                 "mapping_status": "represented",
                 "spec_element_refs": [{"branch_id": "knowledge_candidate",
                     "element_type": "target_condition", "element_id": "layout_condition"}],
                 "represented_scope": None, "deferred_scope": None,
                 "decision_summary": None},
                {"source_path": "/exploration_guidance/observation_candidates/0",
                 "mapping_status": "deferred", "spec_element_refs": [],
                 "represented_scope": None, "deferred_scope": "No sound structured observation mapping.",
                 "decision_summary": "Keep the observation candidate explicit but deferred."},
                {"source_path": "/learned_hypothesis/limitations/0",
                 "mapping_status": "deferred", "spec_element_refs": [],
                 "represented_scope": None, "deferred_scope": "The triggering layout remains unknown.",
                 "decision_summary": "The limitation is retained without inventing a constraint."}
            ]}]},
        "validity_constraints": {"global_constraints": []},
        "exploration_plan": {"branches": [baseline_branch(), {
            "branch_id": "knowledge_candidate", "branch_kind": "knowledge_directed",
            "input_validity_intent": "contract_boundary_unresolved",
            "input_validity_basis": {"basis_kind": "unresolved", "source_refs": [],
                "summary": "Supplied evidence does not establish current contract validity."},
            "source_knowledge_ids": [knowledge_id],
            "grouping_summary": "Layout-related exploration guidance.",
            "exploration_goal": "Vary layout while leaving tensor values fuzz-derived.",
            "exploration_goal_source_refs": [hypothesis_ref],
            "branch_constraints": [],
            "target_conditions": [{"condition_id": "layout_condition",
                "role": "exploration_variable", "predicate": property_predicate(),
                "observe_at": ["before_target_api_call"], "source_refs": [variation_ref]}],
            "behavior_observations": [], "behavior_checks": []}]},
    }


def bug_aware_response() -> dict:
    response = valid_plan()
    response["exploration_plan"]["branches"] = [
        branch
        for branch in response["exploration_plan"]["branches"]
        if branch["branch_kind"] == "knowledge_directed"
    ]
    return response


def canonical_baseline_record() -> dict:
    branch = baseline_branch()
    branch["branch_id"] = "br_default"
    branch["budget_share"] = 1.0
    return {"exploration_plan": {"branches": [branch]}}


class HarnessSpecV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.record_schema = json.loads(RECORD_SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.api = api_profile()
        cls.knowledge = [knowledge_record()]

    def normalize_and_validate(self, plan: dict) -> dict:
        normalized = MODULE.normalize_plan(plan, self.contract, self.knowledge)
        MODULE.validate_plan(normalized, "bug_aware_static", self.knowledge,
                             self.api, self.contract)
        return normalized

    def test_record_schema_is_valid_draft_2020_12(self) -> None:
        Draft202012Validator.check_schema(self.record_schema)

    def test_contract_semantic_response_schema_is_valid(self) -> None:
        self.assertEqual(self.contract["contract_version"], "2.5")
        Draft202012Validator.check_schema(
            self.contract["semantic_response_schema"]
        )

    def test_contract_preserves_open_variations_and_complete_observations(self) -> None:
        constraints = "\n".join(self.contract["output_constraints"])
        rules = RULES_PATH.read_text(encoding="utf-8")
        for text in (constraints, rules):
            normalized = text.lower()
            self.assertIn("merely permitting", normalized)
            self.assertIn("numeric bound", normalized)
            self.assertIn("context.execution", normalized)

    def test_contract_schema_vocabularies_cannot_drift(self) -> None:
        response_defs = self.contract["semantic_response_schema"]["$defs"]
        predicate_ids = set(
            response_defs["predicate"]["properties"]["predicate_id"]["enum"]
        )
        self.assertEqual(
            predicate_ids,
            set(self.contract["allowed_values"]["predicate_id"]),
        )
        self.assertEqual(
            predicate_ids,
            set(self.contract["predicate_contracts"]),
        )
        self.assertEqual(
            set(response_defs["source_ref"]["properties"]["source_type"]["enum"]),
            set(self.contract["allowed_values"]["source_type"]),
        )
        self.assertEqual(
            set(response_defs["component_mapping"]["properties"]["mapping_status"]["enum"]),
            set(self.contract["allowed_values"]["knowledge_mapping_status"]),
        )

    def test_v22_schema_requires_new_semantic_fields_but_reads_v20(self) -> None:
        plan = {"knowledge_plan": {"knowledge_decisions": []},
                "validity_constraints": {"global_constraints": []},
                "exploration_plan": {"branches": [baseline_branch()]}}
        plan = MODULE.normalize_plan(plan, self.contract, [])
        args = builder_args()
        helper = {"profile_id": "hp_create_tensor", "revision": 1,
                  "metadata": {"content_hash": "c" * 64}}
        record = MODULE.assemble_record(plan, args, self.api, [helper], [],
                                        None, None, None, "run_test", trace_ref())
        invalid_v22 = json.loads(json.dumps(record))
        invalid_v22["exploration_plan"]["branches"][0].pop("input_validity_basis")
        with self.assertRaises(MODULE.InputError):
            MODULE.validate_harness_record(
                invalid_v22, self.record_schema, "v2.2 record", args
            )

        archived_v20 = json.loads(json.dumps(invalid_v22))
        archived_v20["schema_version"] = "2.0"
        archived_v20["exploration_plan"]["branches"][0].pop("exploration_goal_source_refs")
        MODULE.validate_harness_record(
            archived_v20, self.record_schema, "v2.0 record", args
        )

    def test_api_profile_admission_requires_ready_approved_profile(self) -> None:
        args = SimpleNamespace(
            api_profile=Path("profile.json"),
            api_profiles=Path("unused"),
            framework="pytorch",
            target_api="torch.relu",
        )
        with mock.patch.object(MODULE, "load_json", return_value=self.api), \
             mock.patch.object(MODULE, "validate_profile_record", return_value=self.api):
            self.assertIs(MODULE.select_api_profile(args, {}), self.api)

        mutations = [
            ("target_binding", "status", "partial", "binding is not resolved"),
            ("validation", "validation_status", "partial", "validation_status is not passed"),
            ("validation", "execution_readiness", "unassessed", "execution_readiness is not ready"),
            ("review", "review_status", "unreviewed", "review_status is not approved"),
        ]
        for section, field, value, message in mutations:
            candidate = json.loads(json.dumps(self.api))
            candidate[section][field] = value
            with self.subTest(section=section, field=field), \
                 mock.patch.object(MODULE, "load_json", return_value=candidate), \
                 mock.patch.object(MODULE, "validate_profile_record", return_value=candidate), \
                 self.assertRaisesRegex(MODULE.InputError, message):
                MODULE.select_api_profile(args, {})

    def test_prompt_view_exposes_exact_knowledge_paths(self) -> None:
        view = MODULE.knowledge_view(self.knowledge[0])
        self.assertEqual(view["learned_hypothesis"]["source_path"], "/learned_hypothesis")
        item = view["exploration_guidance"]["variation_opportunities"][0]
        self.assertEqual(item["source_path"], "/exploration_guidance/variation_opportunities/0")
        self.assertNotIn("evidence_refs", item)

    def test_controlled_baseline_prompt_has_api_independent_isolation_rules(self) -> None:
        helpers = MODULE.HelperSelection([], [], [], [], "selection_hash")
        prompt = MODULE.build_prompt(
            self.contract,
            RULES_PATH.read_text(encoding="utf-8"),
            self.api,
            helpers,
            [],
            "controlled_baseline",
            [],
            75_000,
        )

        self.assertIn("source_knowledge_ids: []", prompt)
        self.assertIn("grouping_summary: null", prompt)
        self.assertIn("knowledge_decisions must be []", prompt)
        self.assertIn("exactly one branch", prompt)
        self.assertNotIn("batch_norm_update_stats", prompt)

    def test_bug_aware_prompt_assigns_default_branch_to_builder(self) -> None:
        prompt = MODULE.build_prompt(
            self.contract,
            RULES_PATH.read_text(encoding="utf-8"),
            self.api,
            MODULE.HelperSelection([], [], [], [], "selection_hash"),
            self.knowledge,
            "bug_aware_static",
            [],
            75_000,
        )
        self.assertIn("do not emit a default branch", prompt)
        self.assertIn("Builder injects", prompt)

    def test_bug_aware_candidate_receives_exact_canonical_default(self) -> None:
        canonical = canonical_baseline_record()
        plan = MODULE.validate_candidate_plan(
            bug_aware_response(),
            "bug_aware_static",
            self.knowledge,
            self.api,
            self.contract,
            canonical,
        )
        default = next(
            branch for branch in plan["exploration_plan"]["branches"]
            if branch["branch_kind"] == "default"
        )
        expected = baseline_branch()
        expected["branch_id"] = "br_default"
        self.assertEqual(default, expected)

    def test_candidate_reports_observation_and_mapping_errors_together(self) -> None:
        response = bug_aware_response()
        branch = response["exploration_plan"]["branches"][0]
        branch["target_conditions"][0]["observe_at"] = []
        branch["branch_constraints"] = [{
            "constraint_id": "hypothesis_constraint",
            "subjects": ["param_input"],
            "predicate": property_predicate(),
            "source_refs": [source_ref(
                "knowledge", "kn_pytorch_relu_001", "/learned_hypothesis"
            )],
        }]
        variation_mapping = response["knowledge_plan"]["knowledge_decisions"][0][
            "component_mappings"
        ][1]
        variation_mapping["spec_element_refs"].append({
            "branch_id": "knowledge_candidate",
            "element_type": "branch_constraint",
            "element_id": "hypothesis_constraint",
        })

        with self.assertRaises(MODULE.ValidationError) as raised:
            MODULE.validate_candidate_plan(
                response,
                "bug_aware_static",
                self.knowledge,
                self.api,
                self.contract,
                canonical_baseline_record(),
            )
        message = str(raised.exception)
        self.assertIn("observe_at", message)
        self.assertIn("same Knowledge source_path", message)

    def test_candidate_reports_normalized_property_path_precisely(self) -> None:
        response = bug_aware_response()
        response["exploration_plan"]["branches"][0]["target_conditions"][0][
            "predicate"
        ]["arguments"]["property_ref"] = "shape.1"
        with self.assertRaises(MODULE.ValidationError) as raised:
            MODULE.validate_candidate_plan(
                response,
                "bug_aware_static",
                self.knowledge,
                self.api,
                self.contract,
                canonical_baseline_record(),
            )
        self.assertIn("property_ref", str(raised.exception))
        self.assertIn("normalized property path", str(raised.exception))

    def test_range_constraint_rejects_inverted_and_empty_intervals(self) -> None:
        for lower, upper, lower_inclusive, upper_inclusive, message in (
            (2, 1, True, True, "lower_bound exceeds"),
            (0, 0, False, True, "range is empty"),
        ):
            with self.subTest(lower=lower, upper=upper):
                plan = valid_plan()
                predicate = plan["exploration_plan"]["branches"][1][
                    "target_conditions"
                ][0]["predicate"]
                predicate["predicate_id"] = "range_constraint"
                predicate["arguments"] = {
                    "subject_ref": "param_input",
                    "property_ref": "numel",
                    "lower_bound": lower,
                    "upper_bound": upper,
                    "lower_inclusive": lower_inclusive,
                    "upper_inclusive": upper_inclusive,
                }
                with self.assertRaisesRegex(MODULE.ValidationError, message):
                    self.normalize_and_validate(plan)

    def test_known_tensor_property_requires_compatible_value_and_subject(self) -> None:
        plan = valid_plan()
        arguments = plan["exploration_plan"]["branches"][1]["target_conditions"][0][
            "predicate"
        ]["arguments"]
        arguments.update(property_ref="numel", value="empty")
        with self.assertRaisesRegex(MODULE.ValidationError, "integer value"):
            self.normalize_and_validate(plan)

        plan = valid_plan()
        arguments = plan["exploration_plan"]["branches"][1]["target_conditions"][0][
            "predicate"
        ]["arguments"]
        arguments.update(
            subject_ref="context.execution", property_ref="numel", value=0
        )
        with self.assertRaisesRegex(MODULE.ValidationError, "tensor property"):
            self.normalize_and_validate(plan)

    def test_return_subject_is_unavailable_before_target_call(self) -> None:
        plan = valid_plan()
        arguments = plan["exploration_plan"]["branches"][1]["target_conditions"][0][
            "predicate"
        ]["arguments"]
        arguments["subject_ref"] = "return_output"
        with self.assertRaisesRegex(MODULE.ValidationError, "before the API call"):
            self.normalize_and_validate(plan)

    def test_output_and_resource_predicates_match_declared_contract(self) -> None:
        output_plan = valid_plan()
        condition = output_plan["exploration_plan"]["branches"][1][
            "target_conditions"
        ][0]
        condition["predicate"] = {
            "predicate_id": "output_property",
            "arguments": {
                "subject_ref": "return_output",
                "property_ref": "rank",
                "operator": "greater_or_equal",
                "value": 0,
            },
            "description": "Observe the output rank after normal completion.",
        }
        condition["observe_at"] = ["after_target_api_call"]
        self.normalize_and_validate(output_plan)

        resource_plan = valid_plan()
        condition = resource_plan["exploration_plan"]["branches"][1][
            "target_conditions"
        ][0]
        condition["predicate"] = {
            "predicate_id": "resource_bound",
            "arguments": {
                "subject_ref": "context.resource",
                "property_ref": "bytes",
                "operator": "less_or_equal",
                "value": 1024,
            },
            "description": "Observe a source-supported resource bound.",
        }
        self.normalize_and_validate(resource_plan)

    def test_unknown_normalized_property_remains_open(self) -> None:
        plan = valid_plan()
        arguments = plan["exploration_plan"]["branches"][1]["target_conditions"][0][
            "predicate"
        ]["arguments"]
        arguments.update(property_ref="custom_metric", value="source_defined")
        self.normalize_and_validate(plan)

    def test_termination_observation_requires_execution_subject(self) -> None:
        plan = valid_plan()
        decision = plan["knowledge_plan"]["knowledge_decisions"][0]
        observation_mapping = decision["component_mappings"][2]
        observation_mapping.update({
            "mapping_status": "represented",
            "spec_element_refs": [{
                "branch_id": "knowledge_candidate",
                "element_type": "behavior_observation",
                "element_id": "termination_observation",
            }],
            "represented_scope": None,
            "deferred_scope": None,
            "decision_summary": None,
        })
        plan["exploration_plan"]["branches"][1]["behavior_observations"] = [{
            "observation_id": "termination_observation",
            "subject_refs": ["param_input"],
            "observe_at": "on_target_api_termination",
            "description": "Record the target execution outcome.",
            "source_refs": [source_ref(
                "knowledge", "kn_pytorch_relu_001",
                "/exploration_guidance/observation_candidates/0",
            )],
        }]

        with self.assertRaisesRegex(
            MODULE.ValidationError, "must include context.execution"
        ):
            self.normalize_and_validate(plan)

    def test_termination_observation_accepts_execution_and_input_subjects(self) -> None:
        plan = valid_plan()
        decision = plan["knowledge_plan"]["knowledge_decisions"][0]
        observation_mapping = decision["component_mappings"][2]
        observation_mapping.update({
            "mapping_status": "represented",
            "spec_element_refs": [{
                "branch_id": "knowledge_candidate",
                "element_type": "behavior_observation",
                "element_id": "termination_observation",
            }],
            "represented_scope": None,
            "deferred_scope": None,
            "decision_summary": None,
        })
        plan["exploration_plan"]["branches"][1]["behavior_observations"] = [{
            "observation_id": "termination_observation",
            "subject_refs": ["context.execution", "param_input"],
            "observe_at": "on_target_api_termination",
            "description": "Record the target execution outcome and associated input.",
            "source_refs": [source_ref(
                "knowledge", "kn_pytorch_relu_001",
                "/exploration_guidance/observation_candidates/0",
            )],
        }]

        normalized = self.normalize_and_validate(plan)
        observation = normalized["exploration_plan"]["branches"][1][
            "behavior_observations"
        ][0]
        self.assertEqual(
            observation["subject_refs"], ["context.execution", "param_input"]
        )

    def test_bug_aware_model_default_is_rejected_even_when_structurally_valid(self) -> None:
        response = valid_plan()
        with self.assertRaisesRegex(
            MODULE.ValidationError, "must not contain a default branch"
        ):
            MODULE.validate_candidate_plan(
                response,
                "bug_aware_static",
                self.knowledge,
                self.api,
                self.contract,
                canonical_baseline_record(),
            )

    def test_valid_plan_normalizes_ids(self) -> None:
        plan = self.normalize_and_validate(valid_plan())
        branches = plan["exploration_plan"]["branches"]
        self.assertEqual([item["branch_id"] for item in branches],
                         ["br_default", "br_knowledge_001"])
        self.assertEqual(branches[1]["target_conditions"][0]["condition_id"],
                         "tc_br_knowledge_001_001")
        self.assertEqual(plan["knowledge_plan"]["knowledge_decisions"][0]["branch_ids"],
                         ["br_knowledge_001"])
        mapping_ref = plan["knowledge_plan"]["knowledge_decisions"][0]["component_mappings"][1]["spec_element_refs"][0]
        self.assertEqual(mapping_ref["branch_id"], "br_knowledge_001")
        self.assertEqual(mapping_ref["element_id"], "tc_br_knowledge_001_001")

    def test_exploration_goal_reference_id_is_canonicalized_to_null(self) -> None:
        plan = valid_plan()
        goal_ref = plan["knowledge_plan"]["knowledge_decisions"][0][
            "component_mappings"
        ][0]["spec_element_refs"][0]
        goal_ref["element_id"] = "model_invented_goal_id"
        normalized = self.normalize_and_validate(plan)
        normalized_ref = normalized["knowledge_plan"]["knowledge_decisions"][0][
            "component_mappings"
        ][0]["spec_element_refs"][0]
        self.assertIsNone(normalized_ref["element_id"])

    def test_knowledge_branch_cannot_use_canonical_baseline_validity_basis(self) -> None:
        plan = valid_plan()
        branch = plan["exploration_plan"]["branches"][1]
        branch["input_validity_intent"] = "expected_valid"
        branch["input_validity_basis"] = {
            "basis_kind": "canonical_baseline_definition",
            "source_refs": [],
            "summary": "Incorrectly borrows the Baseline definition.",
        }
        with self.assertRaisesRegex(
            MODULE.ValidationError, "cannot use canonical_baseline_definition"
        ):
            self.normalize_and_validate(plan)

    def test_historical_knowledge_cannot_define_current_validity_basis(self) -> None:
        plan = valid_plan()
        branch = plan["exploration_plan"]["branches"][1]
        branch["input_validity_intent"] = "expected_valid"
        branch["input_validity_basis"] = {
            "basis_kind": "knowledge_supported",
            "source_refs": [source_ref(
                "knowledge", "kn_pytorch_relu_001", "/learned_hypothesis"
            )],
            "summary": "Historical behavior alone is not a current API contract.",
        }
        with self.assertRaisesRegex(MODULE.ValidationError, "Invalid input_validity_basis"):
            self.normalize_and_validate(plan)

    def test_goal_only_knowledge_branch_is_not_a_structured_contribution(self) -> None:
        plan = valid_plan()
        decision = plan["knowledge_plan"]["knowledge_decisions"][0]
        variation_mapping = decision["component_mappings"][1]
        variation_mapping["spec_element_refs"] = [{
            "branch_id": "knowledge_candidate",
            "element_type": "exploration_goal",
            "element_id": None,
        }]
        branch = plan["exploration_plan"]["branches"][1]
        branch["exploration_goal_source_refs"].append(source_ref(
            "knowledge", "kn_pytorch_relu_001",
            "/exploration_guidance/variation_opportunities/0",
        ))
        branch["target_conditions"] = []
        with self.assertRaisesRegex(
            MODULE.ValidationError, "requires a target condition"
        ):
            self.normalize_and_validate(plan)

    def test_knowledge_goal_requires_exact_source_refs(self) -> None:
        plan = valid_plan()
        plan["exploration_plan"]["branches"][1]["exploration_goal_source_refs"] = []
        with self.assertRaisesRegex(
            MODULE.ValidationError, "exploration_goal_source_refs"
        ):
            self.normalize_and_validate(plan)

    def test_missing_predicate_descriptions_are_normalized_at_every_location(self) -> None:
        def without_description() -> dict:
            predicate = property_predicate()
            predicate.pop("description")
            return predicate

        plan = valid_plan()
        plan["validity_constraints"]["global_constraints"] = [{
            "constraint_id": "global_constraint",
            "subjects": ["param_input"],
            "predicate": without_description(),
            "source_refs": [],
        }]
        branch = plan["exploration_plan"]["branches"][1]
        branch["branch_constraints"] = [{
            "constraint_id": "branch_constraint",
            "subjects": ["param_input"],
            "predicate": without_description(),
            "source_refs": [],
        }]
        branch["target_conditions"][0]["predicate"].pop("description")
        branch["behavior_checks"] = [{
            "check_id": "behavior_check",
            "subject_refs": ["param_input"],
            "preconditions": [without_description()],
            "expected_predicate": without_description(),
            "source_refs": [],
            "requirement_level": "preferred",
        }]

        normalized = MODULE.normalize_plan(plan, self.contract, self.knowledge)
        normalized_branch = normalized["exploration_plan"]["branches"][1]
        predicates = [
            normalized["validity_constraints"]["global_constraints"][0]["predicate"],
            normalized_branch["branch_constraints"][0]["predicate"],
            normalized_branch["target_conditions"][0]["predicate"],
            normalized_branch["behavior_checks"][0]["preconditions"][0],
            normalized_branch["behavior_checks"][0]["expected_predicate"],
        ]
        self.assertTrue(all(predicate["description"] is None for predicate in predicates))

    def test_present_predicate_description_must_be_non_empty_text(self) -> None:
        predicate = property_predicate()
        predicate["description"] = ""
        with self.assertRaisesRegex(MODULE.ValidationError, "description"):
            MODULE.validate_v2_predicate(
                predicate, self.api, self.contract, "test_predicate"
            )

    def test_generic_branch_is_rejected(self) -> None:
        plan = valid_plan()
        plan["exploration_plan"]["branches"][1]["branch_kind"] = "generic_exploration"
        with self.assertRaisesRegex(MODULE.ValidationError, "Unsupported branch_kind"):
            MODULE.normalize_plan(plan, self.contract, self.knowledge)

    def test_deferred_knowledge_cannot_name_branch(self) -> None:
        plan = valid_plan()
        plan["knowledge_plan"]["knowledge_decisions"][0]["disposition"] = "deferred"
        with self.assertRaisesRegex(MODULE.ValidationError, "Deferred Knowledge"):
            self.normalize_and_validate(plan)

    def test_validity_intent_and_basis_must_pair(self) -> None:
        plan = valid_plan()
        plan["exploration_plan"]["branches"][1]["input_validity_intent"] = "expected_valid"
        with self.assertRaisesRegex(MODULE.ValidationError, "must be paired"):
            self.normalize_and_validate(plan)

    def test_component_mapping_inventory_cannot_silently_omit_limitation(self) -> None:
        plan = valid_plan()
        mappings = plan["knowledge_plan"]["knowledge_decisions"][0]["component_mappings"]
        mappings[:] = [item for item in mappings if "limitations" not in item["source_path"]]
        with self.assertRaisesRegex(MODULE.ValidationError, "exact component inventory"):
            self.normalize_and_validate(plan)

    def test_component_mapping_reference_must_cite_same_source_path(self) -> None:
        plan = valid_plan()
        variation = plan["knowledge_plan"]["knowledge_decisions"][0]["component_mappings"][1]
        variation["spec_element_refs"] = [{"branch_id": "knowledge_candidate",
            "element_type": "exploration_goal", "element_id": None}]
        with self.assertRaisesRegex(MODULE.ValidationError, "same Knowledge source_path"):
            self.normalize_and_validate(plan)

    def test_structured_citation_cannot_be_hidden_by_deferred_mapping(self) -> None:
        plan = valid_plan()
        variation = plan["knowledge_plan"]["knowledge_decisions"][0][
            "component_mappings"
        ][1]
        variation.update({
            "mapping_status": "deferred",
            "spec_element_refs": [],
            "represented_scope": None,
            "deferred_scope": "The variation is not structurally represented.",
            "decision_summary": "The component is deferred.",
        })
        with self.assertRaisesRegex(
            MODULE.ValidationError, "structured Knowledge citation"
        ):
            self.normalize_and_validate(plan)

    def test_knowledge_decision_lists_every_branch_that_uses_it(self) -> None:
        plan = valid_plan()
        duplicate = json.loads(json.dumps(plan["exploration_plan"]["branches"][1]))
        duplicate["branch_id"] = "second_knowledge_branch"
        plan["exploration_plan"]["branches"].append(duplicate)
        with self.assertRaisesRegex(MODULE.ValidationError, "exactly match branches"):
            self.normalize_and_validate(plan)

    def test_knowledge_cannot_be_global_constraint(self) -> None:
        plan = valid_plan()
        plan["validity_constraints"]["global_constraints"] = [{
            "constraint_id": "global_from_history", "subjects": ["param_input"],
            "predicate": property_predicate(), "source_refs": [
                source_ref("knowledge", "kn_pytorch_relu_001", "/learned_hypothesis")]}]
        with self.assertRaisesRegex(MODULE.ValidationError, "global validity"):
            self.normalize_and_validate(plan)

    def test_default_branch_reports_all_knowledge_isolation_violations(self) -> None:
        plan = {
            "knowledge_plan": {"knowledge_decisions": []},
            "validity_constraints": {"global_constraints": []},
            "exploration_plan": {"branches": [baseline_branch()]},
        }
        branch = plan["exploration_plan"]["branches"][0]
        branch["source_knowledge_ids"] = ["kn_unavailable"]
        branch["grouping_summary"] = "Knowledge-derived grouping"
        branch["target_conditions"] = [{
            "condition_id": "knowledge_condition",
            "role": "exploration_variable",
            "predicate": property_predicate(),
            "observe_at": ["before_target_api_call"],
            "source_refs": [source_ref(
                "knowledge", "kn_unavailable", "/learned_hypothesis"
            )],
        }]
        normalized = MODULE.normalize_plan(plan, self.contract, [])

        with self.assertRaises(MODULE.ValidationError) as raised:
            MODULE.validate_plan(
                normalized, "controlled_baseline", [], self.api, self.contract
            )
        message = str(raised.exception)
        self.assertIn("br_default.source_knowledge_ids must be []", message)
        self.assertIn("br_default.semantic_items must not cite Knowledge", message)
        self.assertIn("br_default.grouping_summary must be JSON null", message)

    def test_fixed_crash_monitor_is_not_branch_check(self) -> None:
        plan = valid_plan()
        branch = plan["exploration_plan"]["branches"][1]
        branch["behavior_checks"] = [{"check_id": "no_crash",
            "subject_refs": ["context.execution"], "preconditions": [],
            "expected_predicate": {"predicate_id": "no_abnormal_termination",
                "arguments": {"execution_ref": "context.execution"}, "description": "No crash."},
            "source_refs": [source_ref("knowledge", "kn_pytorch_relu_001", "/learned_hypothesis")],
            "requirement_level": "required"}]
        with self.assertRaisesRegex(MODULE.ValidationError, "belongs to the Runner"):
            self.normalize_and_validate(plan)

    def test_source_path_must_resolve(self) -> None:
        lookup = MODULE.source_lookup(self.api, [], self.knowledge)
        expanded = MODULE.expand_source_refs(
            source_ref("knowledge", "kn_pytorch_relu_001", "/learned_hypothesis"), lookup)
        self.assertEqual(expanded["source_version"], "3.0")
        with self.assertRaisesRegex(MODULE.ValidationError, "does not resolve"):
            MODULE.expand_source_refs(
                source_ref("knowledge", "kn_pytorch_relu_001", "/missing"), lookup)

    def test_review_ledger_approves_exact_hash_only(self) -> None:
        record = self.knowledge[0]
        reference = MODULE.knowledge_reference(record)
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"
            ledger.write_text(json.dumps({"knowledge_id": reference["knowledge_id"],
                "knowledge_hash": "sha256:" + reference["content_hash"],
                "decision": "approved"}) + "\n", encoding="utf-8")
            approved = MODULE.load_approved_knowledge_reviews(ledger)
        self.assertEqual(MODULE.validate_knowledge_batch([record], approved), [record])
        with self.assertRaisesRegex(MODULE.InputError, "not approved"):
            MODULE.validate_knowledge_batch([record], set())

    def test_builder_assembles_schema_valid_baseline(self) -> None:
        plan = {"knowledge_plan": {"knowledge_decisions": []},
                "validity_constraints": {"global_constraints": []},
                "exploration_plan": {"branches": [baseline_branch()]}}
        plan = MODULE.normalize_plan(plan, self.contract, [])
        MODULE.validate_plan(plan, "controlled_baseline", [], self.api, self.contract)
        args = builder_args()
        helper = {"profile_id": "hp_create_tensor", "revision": 1,
                  "metadata": {"content_hash": "c" * 64}}
        record = MODULE.assemble_record(plan, args, self.api, [helper], [],
                                        None, None, None, "run_test", trace_ref())
        MODULE.validate_record(record, self.record_schema, args)
        self.assertEqual(record["schema_version"], "2.2")
        self.assertEqual(record["exploration_plan"]["default_branch_id"], "br_default")

    def test_builder_assembles_schema_valid_static_record(self) -> None:
        plan = self.normalize_and_validate(valid_plan())
        policy_path = ROOT / "schemas/initial_branch_budget_policy.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        MODULE.validate_initial_budget_policy(policy)
        args = builder_args(mode="bug_aware_static")
        helper = {"profile_id": "hp_create_tensor", "revision": 1,
                  "metadata": {"content_hash": "c" * 64}}
        record = MODULE.assemble_record(plan, args, self.api, [helper], self.knowledge,
                                        policy, policy_path, None, "run_test", trace_ref())
        MODULE.validate_record(record, self.record_schema, args)
        decision = record["knowledge_plan"]["knowledge_decisions"][0]
        self.assertNotIn("knowledge_id", decision)
        self.assertEqual(decision["knowledge_ref"]["schema_version"], "3.0")
        source = record["exploration_plan"]["branches"][1]["target_conditions"][0]["source_refs"][0]
        self.assertEqual(source["source_path"], "/exploration_guidance/variation_opportunities/0")
        self.assertIsNone(
            record["revision_information"]["canonical_default_spec_ref"]
        )
        baseline_plan = {
            "knowledge_plan": {"knowledge_decisions": []},
            "validity_constraints": {"global_constraints": []},
            "exploration_plan": {"branches": [baseline_branch()]},
        }
        baseline_plan = MODULE.normalize_plan(
            baseline_plan, self.contract, []
        )
        baseline = MODULE.assemble_record(
            baseline_plan, builder_args(), self.api, [helper], [],
            None, None, None, "run_baseline", trace_ref(),
        )
        MODULE.apply_canonical_default_branch(record, baseline)
        self.assertEqual(
            record["revision_information"]["canonical_default_spec_ref"],
            MODULE.harness_spec_reference(baseline),
        )
        MODULE.validate_record(record, self.record_schema, args)

    def test_v20_record_cannot_smuggle_v22_component_mappings(self) -> None:
        plan = self.normalize_and_validate(valid_plan())
        policy_path = ROOT / "schemas/initial_branch_budget_policy.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        args = builder_args(mode="bug_aware_static")
        record = MODULE.assemble_record(
            plan, args, self.api, [], self.knowledge, policy, policy_path,
            None, "run_test", trace_ref(),
        )
        record["schema_version"] = "2.0"
        for branch in record["exploration_plan"]["branches"]:
            branch.pop("input_validity_basis")
            branch.pop("exploration_goal_source_refs")
            if branch["input_validity_intent"] == "contract_boundary_unresolved":
                branch["input_validity_intent"] = "expected_valid"
        with self.assertRaisesRegex(MODULE.InputError, "component_mappings"):
            MODULE.validate_harness_record(
                record, self.record_schema, "hybrid v2.0 record", args
            )

    def test_revision_change_scopes_are_builder_derived(self) -> None:
        plan = {"knowledge_plan": {"knowledge_decisions": []},
                "validity_constraints": {"global_constraints": []},
                "exploration_plan": {"branches": [baseline_branch()]}}
        plan = MODULE.normalize_plan(plan, self.contract, [])
        args = builder_args()
        parent = MODULE.assemble_record(plan, args, self.api, [], [],
                                        None, None, None, "run_parent", trace_ref())
        child = json.loads(json.dumps(parent))
        child["revision_information"]["revision_number"] = 2
        child["target_context"]["api_profile_ref"]["revision"] = 2
        child["exploration_plan"]["branches"][0]["exploration_goal"] = "Updated goal."
        child["exploration_plan"]["branches"][0]["budget_share"] = 0.75

        self.assertEqual(
            MODULE.derive_change_scopes(parent, child),
            ["target_context", "branch_semantics", "budget_allocation"],
        )
        MODULE.apply_derived_revision_metadata(child, parent)
        self.assertEqual(
            child["revision_information"]["change_scopes"],
            ["target_context", "branch_semantics", "budget_allocation"],
        )

    def test_revision_aware_budget_policy_does_not_rewrite_legacy_policy(self) -> None:
        legacy = json.loads(
            (ROOT / "schemas/initial_branch_budget_policy.json").read_text(encoding="utf-8")
        )
        current = json.loads(
            (ROOT / "schemas/initial_branch_budget_policy__v002.json").read_text(encoding="utf-8")
        )
        with self.assertRaisesRegex(MODULE.InputError, "revision 1"):
            MODULE.validate_initial_budget_policy(
                legacy,
                revision_number=2,
                revision_trigger="source_artifact_update",
            )
        MODULE.validate_initial_budget_policy(
            current,
            revision_number=2,
            revision_trigger="source_artifact_update",
        )

    def test_existing_revision_is_rejected_before_materialization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "existing.json"
            path.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(MODULE.InputError, "next explicit --revision"):
                MODULE.ensure_revision_available(path)
            MODULE.ensure_revision_available(Path(directory) / "available.json")

    def test_revision_two_metadata_is_not_user_declared(self) -> None:
        args = MODULE.parse_args([
            "--target-api", "torch.relu",
            "--mode", "controlled_baseline",
            "--revision", "2",
            "--revision-trigger", "source_artifact_update",
        ])
        self.assertIsNone(args.change_scope)
        self.assertIsNone(args.change_summary)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            MODULE.parse_args([
                "--target-api", "torch.relu",
                "--mode", "controlled_baseline",
                "--revision", "2",
                "--revision-trigger", "source_artifact_update",
                "--change-scope", "target_context",
            ])

    def test_manual_review_trigger_requires_review_record(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            MODULE.parse_args([
                "--target-api", "torch.relu", "--mode", "controlled_baseline",
                "--revision", "2", "--revision-trigger", "manual_review",
            ])
        args = MODULE.parse_args([
            "--target-api", "torch.relu", "--mode", "controlled_baseline",
            "--revision", "2", "--revision-trigger", "manual_review",
            "--review-record", "review.json",
        ])
        self.assertEqual(args.review_record, Path("review.json"))

    def test_review_regeneration_is_exact_parent_bound_and_prompt_scoped(self) -> None:
        plan = {
            "knowledge_plan": {"knowledge_decisions": []},
            "validity_constraints": {"global_constraints": []},
            "exploration_plan": {"branches": [baseline_branch()]},
        }
        plan = MODULE.normalize_plan(plan, self.contract, [])
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory) / "harness_specs"
            args = builder_args(
                output_root=output_root,
                revision=2,
                revision_trigger="manual_review",
                change_scope=None,
                change_summary=None,
            )
            parent = MODULE.assemble_record(
                plan, builder_args(), self.api, [{
                    "profile_id": "hp_create_tensor", "revision": 1,
                    "metadata": {"content_hash": "c" * 64},
                }], [], None, None, None, "run_parent", trace_ref(),
            )
            helper = {
                "profile_id": "hp_create_tensor", "revision": 1,
                "metadata": {"content_hash": "c" * 64},
            }
            MODULE.validate_manual_review_frozen_inputs(
                parent, self.api, [helper], [], None, None, None
            )
            changed_api = json.loads(json.dumps(self.api))
            changed_api["metadata"]["content_hash"] = "f" * 64
            with self.assertRaisesRegex(MODULE.InputError, "exact API and Helper"):
                MODULE.validate_manual_review_frozen_inputs(
                    parent, changed_api, [helper], [], None, None, None
                )
            parent_path = MODULE.revision_path(
                output_root, "pytorch", "torch.relu", "controlled_baseline", 1
            )
            parent_path.parent.mkdir(parents=True)
            parent_path.write_text(json.dumps(parent), encoding="utf-8")
            rules_path = ROOT / "schemas/harness_spec_human_review_rules.md"
            review = {
                "schema_version": "1.1",
                "review_id": "hs_review:relu:r1:rr1",
                "review_revision": 1,
                "parent_review_ref": None,
                "subject": {
                    "spec_id": parent["identity"]["spec_id"],
                    "revision_number": 1,
                    "content_hash": MODULE.canonical_hash(parent),
                    "relative_path": str(parent_path),
                },
                "rules_ref": {
                    "artifact_id": rules_path.name,
                    "artifact_version": "1.3",
                    "content_hash": MODULE.file_hash(rules_path),
                    "relative_path": str(rules_path),
                },
                "decision": "needs_revision",
                "findings": [{
                    "criterion_id": "HR-04",
                    "severity": "blocking",
                    "field_path": "$.knowledge_plan",
                    "evidence_ref": "knowledge:/variation/0",
                    "mismatch_summary": "The mapping claims more scope than its cited element represents.",
                }],
                "reviewer_id": "reviewer-a",
                "reviewed_at": "2026-10-05T00:00:00Z",
                "review_notes": None,
            }
            review_path = Path(directory) / "review.json"
            review_path.write_text(json.dumps(review), encoding="utf-8")
            args.review_record = review_path
            context, reference = MODULE.review_regeneration_context(args, parent)
            self.assertEqual(reference["content_hash"], MODULE.file_hash(review_path))
            self.assertEqual(context["blocking_findings"][0]["criterion_id"], "HR-04")
            self.assertIn("parent_semantic_plan", context)
            prompt = MODULE.build_prompt(
                self.contract, RULES_PATH.read_text(), self.api,
                MODULE.HelperSelection([], [], [], [], "selection_hash"), [],
                "controlled_baseline", [], 75_000, context,
            )
            self.assertIn("claims more scope", prompt)
            self.assertIn("parent_semantic_plan", prompt)

            retry_prompt = MODULE.build_prompt(
                self.contract, RULES_PATH.read_text(), self.api,
                MODULE.HelperSelection([], [], [], [], "selection_hash"), [],
                "controlled_baseline", ["invalid range"], 75_000, context,
                '{"previous":"candidate"}',
            )
            self.assertIn('{"previous":"candidate"}', retry_prompt)
            self.assertNotIn("parent_semantic_plan", retry_prompt)
            self.assertNotIn("reviewer-a", prompt)

            review["subject"]["content_hash"] = "0" * 64
            review_path.write_text(json.dumps(review), encoding="utf-8")
            with self.assertRaisesRegex(MODULE.InputError, "exact parent"):
                MODULE.review_regeneration_context(args, parent)

    def test_generation_artifacts_are_hash_qualified_and_immutable(self) -> None:
        plan = {"knowledge_plan": {"knowledge_decisions": []},
                "validity_constraints": {"global_constraints": []},
                "exploration_plan": {"branches": [baseline_branch()]}}
        plan = MODULE.normalize_plan(plan, self.contract, [])
        with tempfile.TemporaryDirectory() as directory:
            args = builder_args(
                generation_artifacts=Path(directory), dry_run=False
            )
            record = MODULE.assemble_record(plan, args, self.api, [], [],
                                            None, None, None, "run_test", trace_ref())
            for field in (
                "script_ref", "contract_ref", "rules_ref", "schema_ref",
                "schema_core_ref",
            ):
                ref = record["provenance"][field]
                self.assertIn("__sha256_", Path(ref["relative_path"]).name)
                self.assertTrue(Path(ref["relative_path"]).exists())
                self.assertEqual(MODULE.file_hash(Path(ref["relative_path"])), ref["content_hash"])

    def test_generation_trace_preserves_exact_prompt_and_response(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            args = builder_args(
                generation_traces=Path(directory),
                generation_trace_schema=(
                    ROOT / "schemas/harness_spec_generation_trace.schema.json"
                ),
            )
            reference = MODULE.write_generation_trace(
                args, "run_trace_test", 1, "exact prompt", "exact response",
                ["ValidationError: prior attempt"], review_ref(),
            )
            trace = json.loads(Path(reference["relative_path"]).read_text())
            self.assertEqual(trace["prompt_text"], "exact prompt")
            self.assertEqual(trace["response_text"], "exact response")
            self.assertEqual(
                trace["prior_errors"], ["ValidationError: prior attempt"]
            )
            self.assertEqual(trace["review_record_ref"], review_ref())
            self.assertEqual(
                MODULE.file_hash(Path(reference["relative_path"])),
                reference["content_hash"],
            )


if __name__ == "__main__":
    unittest.main()
