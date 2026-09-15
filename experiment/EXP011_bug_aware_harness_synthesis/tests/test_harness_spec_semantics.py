#!/usr/bin/env python3
"""Deterministic tests for HarnessSpec target and activation semantics."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from jsonschema import Draft202012Validator


ROOT = Path("experiment/EXP011_bug_aware_harness_synthesis")
SCRIPT = ROOT / "scripts/build_harness_spec_json.py"
CONTRACT_PATH = ROOT / "schemas/harness_spec_synthesis_contract.json"
RECORD_SCHEMA_PATH = ROOT / "schemas/harness_spec_record.schema.json"
RULES_PATH = ROOT / "schemas/knowledge_to_harness_spec_rules.md"

SPEC = importlib.util.spec_from_file_location("build_harness_spec_json", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def source_ref(source_type: str, source_id: str) -> dict:
    return {"source_type": source_type, "source_id": source_id}


def api_profile() -> dict:
    return {
        "profile_id": "api_pytorch_relu_default",
        "revision": 1,
        "metadata": {"content_hash": "a" * 64},
        "target": {
            "framework": "pytorch",
            "framework_version": "2.10.0",
            "backend_scope": ["cpu"],
            "python_api": "torch.relu",
            "callable_kind": "function",
        },
        "python_contract": {
            "parameters": [{"parameter_id": "param_input"}],
            "returns": [{"return_id": "return_output"}],
        },
        "target_binding": {},
        "documented_constraints": [],
    }


def knowledge_record() -> dict:
    return {
        "schema_version": "2.1",
        "metadata": {
            "knowledge_id": "kn_pytorch_relu_001",
            "content_hash": "b" * 64,
        }
    }


def required_oracle(source_type: str, source_id: str) -> dict:
    return {
        "oracle_requirement_id": "temporary_oracle",
        "oracle_type": "crash",
        "observation_subjects": ["context.execution"],
        "oracle_preconditions": [],
        "expected_behavior": {
            "requirement_type": "no_crash",
            "parameters": {},
            "description": "The target API call must not crash.",
        },
        "source_refs": [source_ref(source_type, source_id)],
        "requirement_level": "required",
    }


def valid_plan() -> dict:
    knowledge_id = "kn_pytorch_relu_001"
    return {
        "knowledge_plan": {
            "knowledge_decisions": [
                {
                    "knowledge_id": knowledge_id,
                    "selection_status": "selected",
                    "applicability_status": "applicable",
                    "capability_status": "supported",
                    "reason_codes": ["direct_api_evidence"],
                    "decision_summary": "Use the historical property as one branch.",
                    "decision_confidence": "high",
                }
            ],
            "resolution_records": [],
        },
        "validity_constraints": {"global_constraints": []},
        "exploration_plan": {
            "branches": [
                {
                    "branch_id": "default_candidate",
                    "branch_kind": "default",
                    "input_validity_intent": "expected_valid",
                    "source_knowledge_ids": [],
                    "exploration_goal": "Exercise documented valid inputs.",
                    "risk_dimensions": [],
                    "target_properties": [],
                    "branch_preconditions": [],
                    "branch_constraints": [],
                    "activation_targets": [],
                    "oracle_requirements": [
                        required_oracle("api_profile", "api_pytorch_relu_default")
                    ],
                },
                {
                    "branch_id": "knowledge_candidate",
                    "branch_kind": "knowledge_directed",
                    "input_validity_intent": "boundary_valid",
                    "source_knowledge_ids": [knowledge_id],
                    "exploration_goal": "Exercise the historical layout boundary.",
                    "risk_dimensions": ["layout"],
                    "target_properties": [
                        {
                            "target_property_id": "historical_property",
                            "risk_dimensions": ["layout"],
                            "semantic_requirement": {
                                "requirement_type": "property_state",
                                "parameters": {
                                    "subject_ref": "param_input",
                                    "property_ref": "tensor.layout",
                                    "operator": "equals",
                                    "expected_value": "non_contiguous",
                                },
                                "description": "The input is non-contiguous before the call.",
                            },
                            "source_refs": [source_ref("knowledge", knowledge_id)],
                        }
                    ],
                    "branch_preconditions": [],
                    "branch_constraints": [],
                    "activation_targets": [
                        {
                            "activation_target_id": "historical_activation",
                            "target_property_id": "historical_property",
                            "observation_points": [
                                {
                                    "observation_role": "evaluate",
                                    "observation_point": "before_target_api_call",
                                }
                            ],
                        }
                    ],
                    "oracle_requirements": [required_oracle("knowledge", knowledge_id)],
                },
            ]
        },
    }


class HarnessSpecSemanticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.record_schema = json.loads(RECORD_SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.api = api_profile()
        cls.knowledge = [knowledge_record()]

    def normalize_and_validate(self, plan: dict) -> dict:
        normalized = MODULE.normalize_plan(plan, self.contract, self.knowledge)
        MODULE.validate_plan(
            normalized,
            "bug_aware_static",
            self.knowledge,
            self.api,
            self.contract,
        )
        return normalized

    def test_api_prompt_view_removes_nested_evidence_ids(self) -> None:
        profile = api_profile()
        profile["python_contract"]["evidence_refs"] = ["ev_runtime_docstring"]
        profile["python_contract"]["parameters"][0]["evidence_refs"] = [
            "ev_runtime_docstring"
        ]
        view = MODULE.api_view(profile)
        self.assertNotIn("evidence_refs", view["python_contract"])
        self.assertNotIn("evidence_refs", view["python_contract"]["parameters"][0])

    def test_oracle_requirement_type_is_not_a_target_property_type(self) -> None:
        plan = valid_plan()
        target = plan["exploration_plan"]["branches"][1]["target_properties"][0]
        target["semantic_requirement"] = {
            "requirement_type": "result_equivalence",
            "parameters": {"subject_ref": "return_output"},
            "description": "Repeated outputs agree.",
        }
        with self.assertRaisesRegex(
            MODULE.ValidationError, "is not valid for a Target Property"
        ):
            self.normalize_and_validate(plan)

    def test_expected_behavior_type_is_not_an_oracle_type(self) -> None:
        plan = valid_plan()
        plan["exploration_plan"]["branches"][0]["oracle_requirements"][0][
            "oracle_type"
        ] = "no_crash"
        with self.assertRaisesRegex(MODULE.ValidationError, "oracle_type.*is invalid"):
            self.normalize_and_validate(plan)

    def test_record_schema_is_valid_draft_2020_12(self) -> None:
        Draft202012Validator.check_schema(self.record_schema)

    def test_builder_assembles_schema_valid_baseline_record(self) -> None:
        plan = valid_plan()
        plan["knowledge_plan"]["knowledge_decisions"] = []
        plan["exploration_plan"]["branches"] = [
            plan["exploration_plan"]["branches"][0]
        ]
        plan = MODULE.normalize_plan(plan, self.contract, [])
        MODULE.validate_plan(
            plan, "controlled_baseline", [], self.api, self.contract
        )
        args = SimpleNamespace(
            mode="controlled_baseline",
            target_api="torch.relu",
            revision=1,
            revision_trigger="initial_creation",
            change_scope=["initial_definition"],
            change_summary="Initial controlled baseline definition.",
            model="test-model",
            contract=CONTRACT_PATH,
            rules=RULES_PATH,
        )
        helper = {
            "profile_id": "hp_create_tensor",
            "revision": 1,
            "metadata": {"content_hash": "c" * 64},
        }
        record = MODULE.assemble_record(
            plan,
            args,
            self.api,
            [helper],
            [],
            None,
            None,
            None,
            "run_test",
        )
        MODULE.validate_record(record, self.record_schema)

    def test_valid_plan_normalizes_local_ids_and_passes(self) -> None:
        plan = self.normalize_and_validate(valid_plan())
        branches = plan["exploration_plan"]["branches"]
        self.assertEqual(branches[0]["branch_id"], "br_default")
        self.assertEqual(branches[1]["branch_id"], "br_knowledge_001")
        target_id = branches[1]["target_properties"][0]["target_property_id"]
        self.assertEqual(target_id, "tp_br_knowledge_001_001")
        self.assertEqual(
            branches[1]["activation_targets"][0]["target_property_id"], target_id
        )

    def test_selected_knowledge_cannot_be_orphaned(self) -> None:
        plan = valid_plan()
        branch = plan["exploration_plan"]["branches"][1]
        branch["source_knowledge_ids"] = []
        branch["target_properties"][0]["source_refs"] = [
            source_ref("api_profile", "api_pytorch_relu_default")
        ]
        branch["oracle_requirements"][0]["source_refs"] = [
            source_ref("api_profile", "api_pytorch_relu_default")
        ]
        with self.assertRaisesRegex(MODULE.ValidationError, "source IDs must equal"):
            self.normalize_and_validate(plan)

    def test_oracle_only_knowledge_branch_is_allowed(self) -> None:
        plan = valid_plan()
        plan["knowledge_plan"]["knowledge_decisions"][0]["reason_codes"].append(
            "oracle_only_contribution"
        )
        branch = plan["exploration_plan"]["branches"][1]
        branch["target_properties"] = []
        branch["activation_targets"] = []
        self.normalize_and_validate(plan)

    def test_non_oracle_only_knowledge_requires_target_property(self) -> None:
        plan = valid_plan()
        branch = plan["exploration_plan"]["branches"][1]
        branch["target_properties"] = []
        branch["activation_targets"] = []
        with self.assertRaisesRegex(
            MODULE.ValidationError, "must be cited by a Target Property"
        ):
            self.normalize_and_validate(plan)

    def test_oracle_only_knowledge_cannot_cite_target_property(self) -> None:
        plan = valid_plan()
        plan["knowledge_plan"]["knowledge_decisions"][0]["reason_codes"].append(
            "oracle_only_contribution"
        )
        with self.assertRaisesRegex(
            MODULE.ValidationError, "must not be cited by a Target Property"
        ):
            self.normalize_and_validate(plan)

    def test_knowledge_branch_requires_activation_target(self) -> None:
        plan = valid_plan()
        plan["exploration_plan"]["branches"][1]["activation_targets"] = []
        with self.assertRaisesRegex(
            MODULE.ValidationError, "Every Target Property must have exactly one"
        ):
            self.normalize_and_validate(plan)

    def test_oracle_requires_observation_subject(self) -> None:
        plan = valid_plan()
        plan["exploration_plan"]["branches"][0]["oracle_requirements"][0][
            "observation_subjects"
        ] = []
        with self.assertRaisesRegex(MODULE.ValidationError, "must not be empty"):
            self.normalize_and_validate(plan)

    def test_oracle_subject_must_resolve_in_api_profile(self) -> None:
        plan = valid_plan()
        plan["exploration_plan"]["branches"][1]["oracle_requirements"][0][
            "observation_subjects"
        ] = ["generated_result_variable"]
        with self.assertRaisesRegex(MODULE.ValidationError, "do not resolve"):
            self.normalize_and_validate(plan)

    def test_non_transition_rejects_before_role(self) -> None:
        plan = valid_plan()
        observation = plan["exploration_plan"]["branches"][1]["activation_targets"][0][
            "observation_points"
        ][0]
        observation["observation_role"] = "before"
        with self.assertRaisesRegex(MODULE.ValidationError, "one evaluate observation"):
            self.normalize_and_validate(plan)

    def test_single_segment_property_path_is_allowed(self) -> None:
        plan = valid_plan()
        plan["exploration_plan"]["branches"][1]["target_properties"][0][
            "semantic_requirement"
        ]["parameters"]["property_ref"] = "dtype"
        self.normalize_and_validate(plan)

    def test_non_normalized_property_path_is_rejected(self) -> None:
        plan = valid_plan()
        plan["exploration_plan"]["branches"][1]["target_properties"][0][
            "semantic_requirement"
        ]["parameters"]["property_ref"] = "tensor.dtype()"
        with self.assertRaisesRegex(MODULE.ValidationError, "normalized property path"):
            self.normalize_and_validate(plan)

    def test_target_property_risk_must_belong_to_branch(self) -> None:
        plan = valid_plan()
        plan["exploration_plan"]["branches"][1]["target_properties"][0][
            "risk_dimensions"
        ] = ["dtype"]
        with self.assertRaisesRegex(MODULE.ValidationError, "non-empty subset"):
            self.normalize_and_validate(plan)

    def test_helper_profile_cannot_be_semantic_evidence(self) -> None:
        lookup = MODULE.source_lookup(self.api, [], self.knowledge)
        with self.assertRaisesRegex(MODULE.ValidationError, "unavailable source reference"):
            MODULE.expand_source_refs(
                source_ref("helper_profile", "hp_create_tensor"), lookup
            )

    def test_state_transition_requires_before_and_after_points(self) -> None:
        plan = valid_plan()
        target = plan["exploration_plan"]["branches"][1]["target_properties"][0]
        target["semantic_requirement"] = {
            "requirement_type": "state_transition",
            "parameters": {
                "subject_ref": "param_input",
                "property_ref": "tensor.version",
                "transition": "changed",
            },
            "description": "The tensor state changes across the target call.",
        }
        activation = plan["exploration_plan"]["branches"][1]["activation_targets"][0]
        activation["observation_points"] = [
            {
                "observation_role": "before",
                "observation_point": "before_target_api_call",
            },
            {
                "observation_role": "after",
                "observation_point": "after_target_api_call",
            },
        ]
        self.normalize_and_validate(plan)


if __name__ == "__main__":
    unittest.main()
