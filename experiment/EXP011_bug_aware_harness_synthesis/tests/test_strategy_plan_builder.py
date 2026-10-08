#!/usr/bin/env python3
"""Deterministic tests for HarnessSpec v2.2 to Strategy Plan v1.2."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path("experiment/EXP011_bug_aware_harness_synthesis")
SCRIPT = ROOT / "scripts/build_strategy_plan_json.py"

SPEC = importlib.util.spec_from_file_location("build_strategy_plan_json", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def source_ref() -> dict:
    return {
        "source_type": "knowledge",
        "source_id": "kn_test",
        "source_version": "3.0",
        "content_hash": "0" * 64,
        "source_path": "/test",
    }


def harness_spec() -> dict:
    return {
        "identity": {
            "spec_id": "hs_test",
            "framework": "pytorch",
            "target_api": "torch.test",
            "spec_mode": "bug_aware_static",
        },
        "validity_constraints": {"global_constraints": []},
        "exploration_plan": {
            "branches": [
                {
                    "branch_id": "br_test",
                    "branch_kind": "knowledge_directed",
                    "input_validity_intent": "contract_boundary_unresolved",
                    "exploration_goal": "Vary and observe empty tensors.",
                    "branch_constraints": [],
                    "target_conditions": [
                        {
                            "condition_id": "tc_test",
                            "role": "exploration_variable",
                            "predicate": {
                                "predicate_id": "property_relation",
                                "arguments": {
                                    "subject_ref": "param_input",
                                    "property_ref": "numel",
                                    "operator": "equals",
                                    "value": 0,
                                },
                                "description": None,
                            },
                            "observe_at": ["before_target_api_call"],
                            "source_refs": [source_ref()],
                        }
                    ],
                    "behavior_observations": [
                        {
                            "observation_id": "obs_test",
                            "subject_refs": ["context.execution", "param_input"],
                            "observe_at": "on_target_api_termination",
                            "description": "Record target termination.",
                            "source_refs": [source_ref()],
                        }
                    ],
                    "behavior_checks": [],
                }
            ]
        },
    }


def semantic_support(**overrides: object) -> dict:
    value = {
        "predicate_ids": [],
        "condition_roles": [],
        "observation_phases": [],
        "behavior_check_levels": [],
        "subject_kinds": [],
        "fuzz_dependency": "none",
    }
    value.update(overrides)
    return value


def primitive(primitive_id: str, slot: str, **support: object) -> dict:
    return {
        "primitive_id": primitive_id,
        "primitive_kind": "predicate_evaluate",
        "semantic_support": semantic_support(**support),
        "allowed_template_slots": [slot],
        "input_contract": [],
        "output_contract": [],
        "parameter_contract": [],
        "outcome_contract": {"failure_outcomes": []},
        "limitations": [],
    }


def step(step_id: str, primitive_id: str, slot: str) -> dict:
    return {
        "step_id": step_id,
        "primitive_id": primitive_id,
        "template_slot": slot,
        "input_bindings": [],
        "parameter_bindings": [],
        "output_bindings": [],
    }


class StrategyBuilderTests(unittest.TestCase):
    def test_json_schemas_are_valid(self) -> None:
        for name in (
            "strategy_catalog_record.schema.json",
            "strategy_plan_record.schema.json",
            "strategy_plan_review_record.schema.json",
        ):
            Draft202012Validator.check_schema(
                json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
            )

    def test_catalog_v5_matches_catalog_schema(self) -> None:
        schema = json.loads(
            (ROOT / "schemas/strategy_catalog_record.schema.json").read_text()
        )
        catalog = json.loads(
            (ROOT / "strategy_primitives/strategy_primitive_catalog.json").read_text()
        )
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(catalog)), [])
        self.assertEqual(catalog['catalog_version'], 6)

    def test_v22_entries_replace_legacy_element_types(self) -> None:
        entries = MODULE.all_element_entries(harness_spec())
        self.assertEqual(
            [item["spec_element_type"] for item in entries],
            ["target_condition", "behavior_observation"],
        )

    def test_runner_observation_is_builder_owned(self) -> None:
        view = MODULE.build_harness_spec_view(harness_spec())
        self.assertEqual(
            [item["spec_element_type"] for item in view["required_spec_elements"]],
            ["target_condition"],
        )
        runner = view["runner_observation_elements"][0]
        self.assertEqual(runner["spec_element_id"], "obs_test")
        self.assertIn("process_signal", runner["runner_events"])
        self.assertIn("sanitizer_report", runner["runner_events"])

    def test_exposed_parameters_exclude_subject_reference(self) -> None:
        parameters = MODULE.exposed_parameters(
            MODULE.all_element_entries(harness_spec())
        )
        names = {item["parameter_name"] for item in parameters}
        self.assertNotIn("subject_ref", names)
        self.assertEqual(names, {"operator", "property_ref", "value"})

    def test_exploration_variable_cannot_be_guarded(self) -> None:
        spec = harness_spec()
        evaluator = primitive(
            "p_guard",
            "pre_call_guard",
            predicate_ids=["property_relation"],
            condition_roles=["exploration_variable"],
            observation_phases=["before_target_api_call"],
        )
        evaluator["primitive_kind"] = "relation_enforce"
        with self.assertRaisesRegex(
            MODULE.PlanValidationError, "observed, not enforced"
        ):
            MODULE.validate_binding_semantics(
                MODULE.all_element_entries(spec)[0],
                ["s1"],
                {"s1": step("s1", "p_guard", "pre_call_guard")},
                {"p_guard": evaluator},
                {"s1": set()},
                spec,
            )

    def test_exploration_variable_requires_declared_phase(self) -> None:
        spec = harness_spec()
        evaluator = primitive(
            "p_eval",
            "post_call_observation",
            predicate_ids=["property_relation"],
            condition_roles=["exploration_variable"],
            observation_phases=["after_target_api_call"],
        )
        with self.assertRaisesRegex(
            MODULE.PlanValidationError, "no directly compatible"
        ):
            MODULE.validate_binding_semantics(
                MODULE.all_element_entries(spec)[0],
                ["s1"],
                {"s1": step("s1", "p_eval", "post_call_observation")},
                {"p_eval": evaluator},
                {"s1": set()},
                spec,
            )

    def test_scalar_and_optional_api_kinds(self) -> None:
        self.assertEqual(MODULE.api_schema_type_to_kinds("float"), ["floating"])
        self.assertEqual(MODULE.api_schema_type_to_kinds("int"), ["integer"])
        self.assertEqual(MODULE.api_schema_type_to_kinds("bool"), ["boolean"])
        self.assertEqual(
            MODULE.api_schema_type_to_kinds("Tensor?"),
            ["tensor", "optional_value"],
        )

    def test_multi_return_ports_are_preserved(self) -> None:
        api = {
            "python_contract": {
                "returns": [
                    {"return_id": "r0", "normalized_types": ["tensor"], "semantic_role": "result_tensor"},
                    {"return_id": "r1", "normalized_types": ["tensor"], "semantic_role": "result_tensor"},
                ]
            },
            "target_binding": {
                "return_mapping": [
                    {"binding_return_position": 0, "python_return_ref": "r0", "mapping_kind": "direct"},
                    {"binding_return_position": 1, "python_return_ref": "r1", "mapping_kind": "direct"},
                ]
            },
        }
        self.assertEqual(
            [item["port_id"] for item in MODULE.resolve_api_output_ports(api)],
            ["r0", "r1"],
        )

    def test_constrained_zero_shape_can_remain_fuzz_dependent(self) -> None:
        candidate = {
            "primitive_id": "construct_tensor_with_constraints",
            "parameter_bindings": [
                {"parameter_id": "shape_template", "binding_kind": "literal", "binding_value": [-1, 2]},
                {"parameter_id": "fill_policy", "binding_kind": "literal", "binding_value": "zero"},
            ],
        }
        self.assertEqual(
            MODULE.directly_fuzz_dependent_output_ports(candidate),
            {"tensor", "next_cursor"},
        )

    def test_fixed_zero_tensor_is_not_fuzz_dependent(self) -> None:
        candidate = {
            "primitive_id": "construct_tensor_with_constraints",
            "parameter_bindings": [
                {"parameter_id": "shape_template", "binding_kind": "literal", "binding_value": [0, 2]},
                {"parameter_id": "fill_policy", "binding_kind": "literal", "binding_value": "zero"},
            ],
        }
        self.assertEqual(MODULE.directly_fuzz_dependent_output_ports(candidate), set())

    def test_exact_review_subject_is_required(self) -> None:
        spec = harness_spec()
        spec["revision_information"] = {"revision_number": 1}
        digest = MODULE.canonical_hash(spec)
        review = {
            "review_id": "review:test",
            "review_revision": 1,
            "subject": {
                "spec_id": "hs_test",
                "revision_number": 1,
                "content_hash": digest,
                "relative_path": "spec.json",
            },
        }
        with self.assertRaisesRegex(MODULE.ItemInputError, "exact approved"):
            MODULE.resolve_harness_spec_review(spec, Path("spec.json"), {})
        result = MODULE.resolve_harness_spec_review(
            spec,
            Path("spec.json"),
            {("hs_test", 1, digest): (review, Path("review.json"))},
        )
        self.assertEqual(result["review_id"], "review:test")

    def test_runner_events_are_not_in_process_primitives(self) -> None:
        self.assertIn("timeout", MODULE.RUNNER_EVENTS)
        self.assertNotIn("runner_event", MODULE.PRIMITIVE_KINDS)

    def test_profile_hash_excludes_only_content_hash(self) -> None:
        profile = {
            "profile_id": "hp_test",
            "revision": 1,
            "metadata": {"content_hash": "0" * 64, "source": "test"},
        }
        expected = MODULE.profile_content_hash(profile)
        changed = copy.deepcopy(profile)
        changed["metadata"]["content_hash"] = "f" * 64
        self.assertEqual(expected, MODULE.profile_content_hash(changed))
        changed["metadata"]["source"] = "changed"
        self.assertNotEqual(expected, MODULE.profile_content_hash(changed))


if __name__ == "__main__":
    unittest.main()
