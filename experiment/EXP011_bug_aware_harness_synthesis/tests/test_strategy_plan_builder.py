#!/usr/bin/env python3
"""Deterministic tests for Strategy synthesis views and semantics."""

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
CATALOG_SCHEMA = ROOT / "schemas/strategy_catalog_record.schema.json"

SPEC = importlib.util.spec_from_file_location("build_strategy_plan_json", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def semantic_requirement(requirement_type: str) -> dict:
    return {
        "requirement_type": requirement_type,
        "parameters": {
            "subject_ref": "param_input",
            "property_ref": "tensor.layout",
            "operator": "equals",
            "expected_value": "non_contiguous",
        },
        "description": "Exercise the requested state.",
    }


def harness_spec(*, preferred_oracle: bool = False) -> dict:
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
                    "input_validity_intent": "boundary_valid",
                    "exploration_goal": "Exercise shape and dtype together.",
                    "risk_dimensions": ["shape", "dtype"],
                    "branch_constraints": [],
                    "branch_preconditions": [],
                    "target_properties": [
                        {
                            "target_property_id": "tp_test",
                            "risk_dimensions": ["shape", "dtype"],
                            "semantic_requirement": semantic_requirement(
                                "property_state"
                            ),
                            "source_refs": [
                                {
                                    "source_type": "knowledge",
                                    "source_id": "kn_test",
                                }
                            ],
                        }
                    ],
                    "activation_targets": [
                        {
                            "activation_target_id": "at_test",
                            "target_property_id": "tp_test",
                            "observation_points": [
                                {
                                    "observation_role": "before",
                                    "observation_point": "before_target_api_call",
                                },
                                {
                                    "observation_role": "after",
                                    "observation_point": "after_target_api_call",
                                },
                            ],
                        }
                    ],
                    "oracle_requirements": [
                        {
                            "oracle_requirement_id": "or_test",
                            "oracle_type": "crash",
                            "observation_subjects": ["target_api_call"],
                            "oracle_preconditions": [],
                            "expected_behavior": {
                                "requirement_type": "no_crash",
                                "parameters": {},
                                "description": "The call must not crash.",
                            },
                            "source_refs": [
                                {
                                    "source_type": "knowledge",
                                    "source_id": "kn_test",
                                }
                            ],
                            "requirement_level": (
                                "preferred" if preferred_oracle else "required"
                            ),
                        }
                    ],
                }
            ]
        },
    }


def primitive(
    primitive_id: str,
    *,
    slot: str,
    requirement_types: list[str] | None = None,
    risk_dimensions: list[str] | None = None,
    oracle_types: list[str] | None = None,
) -> dict:
    return {
        "primitive_id": primitive_id,
        "primitive_kind": "predicate_evaluate",
        "semantic_support": {
            "requirement_types": requirement_types or [],
            "risk_dimensions": risk_dimensions or [],
            "oracle_types": oracle_types or [],
        },
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


def entry(spec: dict, element_type: str) -> dict:
    return next(
        item
        for item in MODULE.all_element_entries(spec)
        if item["spec_element_type"] == element_type
    )


class StrategyBuilderTests(unittest.TestCase):
    def test_catalog_schema_is_valid_draft_2020_12(self) -> None:
        schema = json.loads(CATALOG_SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)

    def test_fuzz_constructor_marks_tensor_and_cursor_dependent(self) -> None:
        candidate = {
            'primitive_id': 'construct_tensor_from_fuzz',
            'parameter_bindings': [],
        }
        self.assertEqual(
            MODULE.directly_fuzz_dependent_output_ports(candidate),
            {'tensor', 'next_cursor'},
        )

    def test_fixed_zero_constrained_tensor_is_not_fuzz_dependent(self) -> None:
        candidate = {
            'primitive_id': 'construct_tensor_with_constraints',
            'parameter_bindings': [
                {
                    'parameter_id': 'shape_template',
                    'binding_kind': 'literal',
                    'binding_value': [4, 2],
                },
                {
                    'parameter_id': 'fill_policy',
                    'binding_kind': 'literal',
                    'binding_value': 'zero',
                },
            ],
        }
        self.assertEqual(
            MODULE.directly_fuzz_dependent_output_ports(candidate),
            set(),
        )
        candidate['parameter_bindings'][0]['binding_value'] = [-1, 2]
        self.assertEqual(
            MODULE.directly_fuzz_dependent_output_ports(candidate),
            {'tensor', 'next_cursor'},
        )
        candidate['parameter_bindings'][0]['binding_value'] = [4, 2]
        candidate['parameter_bindings'][1]['binding_value'] = 'fuzz_int64'
        self.assertEqual(
            MODULE.directly_fuzz_dependent_output_ports(candidate),
            {'tensor', 'next_cursor'},
        )

    def test_default_branch_requires_fuzz_dependent_target_tensors(self) -> None:
        spec = harness_spec()
        spec['exploration_plan']['branches'][0]['branch_kind'] = 'default'
        target_step = {
            'step_id': 's_api',
            'primitive_id': 'p_api',
            'input_bindings': [
                {'port_id': 'left', 'value_ref': 'lhs'},
                {'port_id': 'right', 'value_ref': 'rhs'},
            ],
        }
        target_primitive = {
            'input_contract': [
                {
                    'port_id': 'left',
                    'accepted_value_kinds': ['tensor'],
                },
                {
                    'port_id': 'right',
                    'accepted_value_kinds': ['tensor'],
                },
            ],
        }
        with self.assertRaisesRegex(
            MODULE.PlanValidationError,
            'do not depend on consumed LibFuzzer bytes',
        ):
            MODULE.validate_default_branch_fuzz_dependence(
                spec,
                'br_test',
                ['s_api'],
                {'s_api': target_step},
                {'p_api': target_primitive},
                {'lhs'},
            )
        MODULE.validate_default_branch_fuzz_dependence(
            spec,
            'br_test',
            ['s_api'],
            {'s_api': target_step},
            {'p_api': target_primitive},
            {'lhs', 'rhs'},
        )

    def test_knowledge_branch_requires_a_fuzz_dependent_target_input(self) -> None:
        spec = harness_spec()
        target_step = {
            'step_id': 's_api',
            'input_bindings': [
                {'port_id': 'left', 'value_ref': 'lhs'},
                {'port_id': 'right', 'value_ref': 'rhs'},
            ],
        }
        with self.assertRaisesRegex(
            MODULE.PlanValidationError,
            'fixes every target input',
        ):
            MODULE.validate_knowledge_branch_fuzz_dependence(
                spec,
                'br_test',
                ['s_api'],
                {'s_api': target_step},
                set(),
            )
        MODULE.validate_knowledge_branch_fuzz_dependence(
            spec,
            'br_test',
            ['s_api'],
            {'s_api': target_step},
            {'rhs'},
        )

    def test_exposed_parameters_exclude_runtime_references(self) -> None:
        parameters = MODULE.exposed_parameters(
            MODULE.all_element_entries(harness_spec())
        )
        names = {item["parameter_name"] for item in parameters}
        self.assertNotIn("subject_ref", names)
        self.assertIn("property_ref", names)
        self.assertIn("operator", names)
        self.assertTrue(all("value_kind" in item for item in parameters))

    def test_ambiguous_exposed_parameter_is_rejected(self) -> None:
        spec = harness_spec()
        oracle = spec["exploration_plan"]["branches"][0][
            "oracle_requirements"
        ][0]
        oracle["oracle_preconditions"] = [
            {
                "requirement_type": "range_constraint",
                "parameters": {"threshold": 1},
                "description": None,
            }
        ]
        oracle["expected_behavior"]["parameters"] = {"threshold": 2}
        with self.assertRaisesRegex(
            MODULE.ItemInputError, "Ambiguous exposable"
        ):
            MODULE.exposed_parameters(MODULE.all_element_entries(spec))

    def test_target_property_requires_union_of_all_risks(self) -> None:
        spec = harness_spec()
        shape = primitive(
            "p_shape",
            slot="pre_call_transform",
            requirement_types=["property_state"],
            risk_dimensions=["shape"],
        )
        dtype = primitive(
            "p_dtype",
            slot="pre_call_transform",
            requirement_types=["property_state"],
            risk_dimensions=["dtype"],
        )
        steps = {
            "s1": step("s1", "p_shape", "pre_call_transform"),
            "s2": step("s2", "p_dtype", "pre_call_transform"),
        }
        MODULE.validate_binding_semantics(
            entry(spec, "target_property"),
            ["s1", "s2"],
            steps,
            {"p_shape": shape, "p_dtype": dtype},
            {"s1": set(), "s2": set()},
            spec,
        )
        with self.assertRaisesRegex(
            MODULE.PlanValidationError, "misses risk dimensions"
        ):
            MODULE.validate_binding_semantics(
                entry(spec, "target_property"),
                ["s1"],
                steps,
                {"p_shape": shape, "p_dtype": dtype},
                {"s1": set(), "s2": set()},
                spec,
            )

    def test_activation_requires_each_observation_phase(self) -> None:
        spec = harness_spec()
        before = primitive(
            "p_before",
            slot="pre_call_observation",
            requirement_types=["property_state"],
            risk_dimensions=["shape", "dtype"],
        )
        after = primitive(
            "p_after",
            slot="post_call_observation",
            requirement_types=["property_state"],
            risk_dimensions=["shape", "dtype"],
        )
        steps = {
            "s1": step("s1", "p_before", "pre_call_observation"),
            "s2": step("s2", "p_after", "post_call_observation"),
        }
        primitives = {"p_before": before, "p_after": after}
        MODULE.validate_binding_semantics(
            entry(spec, "activation_target"),
            ["s1", "s2"],
            steps,
            primitives,
            {"s1": set(), "s2": set()},
            spec,
        )
        with self.assertRaisesRegex(
            MODULE.PlanValidationError, "misses required observation slot"
        ):
            MODULE.validate_binding_semantics(
                entry(spec, "activation_target"),
                ["s1"],
                steps,
                primitives,
                {"s1": set(), "s2": set()},
                spec,
            )

    def test_auxiliary_binding_step_must_be_dataflow_ancestor(self) -> None:
        spec = harness_spec()
        auxiliary = primitive("p_aux", slot="input_construction")
        direct = primitive(
            "p_direct",
            slot="pre_call_transform",
            requirement_types=["property_state"],
            risk_dimensions=["shape", "dtype"],
        )
        steps = {
            "s1": step("s1", "p_aux", "input_construction"),
            "s2": step("s2", "p_direct", "pre_call_transform"),
        }
        primitives = {"p_aux": auxiliary, "p_direct": direct}
        MODULE.validate_binding_semantics(
            entry(spec, "target_property"),
            ["s1", "s2"],
            steps,
            primitives,
            {"s1": set(), "s2": {"s1"}},
            spec,
        )
        with self.assertRaisesRegex(
            MODULE.PlanValidationError, "unrelated auxiliary"
        ):
            MODULE.validate_binding_semantics(
                entry(spec, "target_property"),
                ["s1", "s2"],
                steps,
                primitives,
                {"s1": set(), "s2": set()},
                spec,
            )

    def test_blocked_cannot_reference_preferred_oracle(self) -> None:
        spec = harness_spec(preferred_oracle=True)
        resolved = MODULE.ResolvedInputs(
            spec=spec,
            api={},
            resolved_api_primitive={},
            candidate_primitives=[],
        )
        response = {
            "blocking_gaps": [
                {
                    "affected_branch_ids": ["br_test"],
                    "spec_element_type": "oracle_requirement",
                    "spec_element_id": "or_test",
                    "reason_code": "required_oracle_unavailable",
                    "details": "No compatible required oracle exists.",
                }
            ]
        }
        with self.assertRaisesRegex(
            MODULE.PlanValidationError, "only required Spec Elements"
        ):
            MODULE.validate_blocked_response(response, resolved)

    def test_partial_risk_candidate_does_not_disprove_capability_gap(self) -> None:
        spec = harness_spec()
        shape_only = primitive(
            "p_shape",
            slot="pre_call_transform",
            requirement_types=["property_state"],
            risk_dimensions=["shape"],
        )
        resolved = MODULE.ResolvedInputs(
            spec=spec,
            api={},
            resolved_api_primitive={},
            candidate_primitives=[shape_only],
        )
        response = {
            "blocking_gaps": [
                {
                    "affected_branch_ids": ["br_test"],
                    "spec_element_type": "target_property",
                    "spec_element_id": "tp_test",
                    "reason_code": "required_capability_unavailable",
                    "details": "No candidate covers the required dtype dimension.",
                }
            ]
        }
        gaps = MODULE.validate_blocked_response(response, resolved)
        self.assertEqual(len(gaps), 1)

        resolved.candidate_primitives.append(
            primitive(
                "p_dtype",
                slot="pre_call_transform",
                requirement_types=["property_state"],
                risk_dimensions=["dtype"],
            )
        )
        with self.assertRaisesRegex(
            MODULE.PlanValidationError, "contradicts an available"
        ):
            MODULE.validate_blocked_response(response, resolved)

    def test_prompt_candidates_exclude_resolved_api_primitive(self) -> None:
        spec = harness_spec()
        candidate = primitive("p_candidate", slot="input_construction")
        api_primitive = primitive("p_api", slot="target_call")
        api_primitive["primitive_kind"] = "target_api_invoke"
        resolved = MODULE.ResolvedInputs(
            spec=spec,
            api={},
            resolved_api_primitive={
                "target_api_primitive_id": "p_api",
                "input_ports": [],
                "output_ports": [],
                "api_binding": {},
                "_resolved_primitive": api_primitive,
            },
            candidate_primitives=[candidate],
        )
        catalog = {
            "template_interface": {
                "available_slots": ["input_construction", "target_call"],
                "built_in_values": [
                    {
                        "value_id": "fuzz_data",
                        "value_kind": "raw_bytes",
                        "description": "Fuzz bytes.",
                    }
                ],
            }
        }
        views = MODULE.build_prompt_views(resolved, catalog)
        ids = [
            item["primitive_id"]
            for item in views["primitive_candidate_views"]
        ]
        self.assertEqual(ids, ["p_candidate"])
        self.assertEqual(
            views["resolved_api_primitive_view"][
                "target_api_primitive_id"
            ],
            "p_api",
        )

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
