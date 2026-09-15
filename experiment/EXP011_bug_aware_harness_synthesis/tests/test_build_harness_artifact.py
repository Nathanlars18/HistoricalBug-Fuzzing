#!/usr/bin/env python3
"""Deterministic tests for Strategy-to-Harness materialization."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path("experiment/EXP011_bug_aware_harness_synthesis")
SCRIPT = ROOT / "scripts/build_harness_artifact.py"
CATALOG_PATH = ROOT / "strategy_primitives/strategy_primitive_catalog.json"
CATALOG_SCHEMA_PATH = ROOT / "schemas/strategy_catalog_record.schema.json"
TEMPLATE_PATH = ROOT / "templates/libfuzzer_harness_v1.cpp.in"

SPEC = importlib.util.spec_from_file_location("build_harness_artifact", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def load_catalog() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def api_profile() -> dict:
    return {
        "python_contract": {
            "returns": [
                {
                    "return_id": "return_000",
                    "normalized_types": ["tensor"],
                    "semantic_role": "result_tensor",
                }
            ]
        },
        "target_binding": {
            "cpp_callable": "at::matmul",
            "binding_parameters": [
                {
                    "binding_parameter_id": "binding_param_000_self",
                    "ordinal": 0,
                    "schema_type": "Tensor",
                    "default": None,
                },
                {
                    "binding_parameter_id": "binding_param_001_other",
                    "ordinal": 1,
                    "schema_type": "Tensor",
                    "default": None,
                },
            ],
            "return_mapping": [
                {
                    "binding_return_position": 0,
                    "python_return_ref": "return_000",
                    "mapping_kind": "direct",
                }
            ],
        },
    }


def harness_spec() -> dict:
    return {
        "exploration_plan": {
            "branches": [
                {
                    "branch_id": "br_zero_reduction",
                    "target_properties": [
                        {
                            "target_property_id": "tp_zero_reduction"
                        }
                    ],
                    "activation_targets": [
                        {
                            "activation_target_id": "at_zero_reduction",
                            "target_property_id": "tp_zero_reduction",
                            "observation_points": [
                                {
                                    "observation_role": "before",
                                    "observation_point":
                                        "before_target_api_call",
                                }
                            ],
                        }
                    ],
                }
            ]
        }
    }


def literal(parameter_id: str, value: object) -> dict:
    return {
        "parameter_id": parameter_id,
        "binding_kind": "literal",
        "binding_value": value,
    }


def construct_step(
    step_id: str,
    cursor_ref: str,
    shape: list[int],
    tensor_value: str,
    cursor_value: str,
) -> dict:
    return {
        "step_id": step_id,
        "primitive_id": "construct_tensor_with_constraints",
        "template_slot": "input_construction",
        "input_bindings": [
            {"port_id": "data", "value_ref": "data"},
            {"port_id": "size", "value_ref": "size"},
            {"port_id": "cursor", "value_ref": cursor_ref},
        ],
        "parameter_bindings": [
            literal("shape_template", shape),
            literal("dtype_policy", "int64"),
            literal("fill_policy", "zero"),
            literal("max_dimension", 4),
        ],
        "output_bindings": [
            {"port_id": "tensor", "value_id": tensor_value},
            {"port_id": "next_cursor", "value_id": cursor_value},
        ],
    }


def strategy() -> dict:
    branch = {
        "source_branch_id": "br_zero_reduction",
        "budget_share": 1.0,
        "steps": [
            construct_step(
                "step_construct_left",
                "offset",
                [2, 0],
                "left_tensor",
                "cursor_after_left",
            ),
            construct_step(
                "step_construct_right",
                "cursor_after_left",
                [0, 3],
                "right_tensor",
                "cursor_after_right",
            ),
            {
                "step_id": "step_observe_zero_dimension",
                "primitive_id": "evaluate_tensor_property",
                "template_slot": "pre_call_observation",
                "input_bindings": [
                    {"port_id": "subject", "value_ref": "left_tensor"}
                ],
                "parameter_bindings": [
                    literal("property_kind", "dimension_size_equals"),
                    literal("axis", 1),
                    literal("expected_integer", 0),
                ],
                "output_bindings": [
                    {
                        "port_id": "property_holds",
                        "value_id": "zero_dimension_observed",
                    }
                ],
            },
            {
                "step_id": "step_call_matmul",
                "primitive_id": "invoke_profiled_target_api",
                "template_slot": "target_call",
                "input_bindings": [
                    {
                        "port_id": "binding_param_000_self",
                        "value_ref": "left_tensor",
                    },
                    {
                        "port_id": "binding_param_001_other",
                        "value_ref": "right_tensor",
                    },
                ],
                "parameter_bindings": [],
                "output_bindings": [
                    {
                        "port_id": "return_000",
                        "value_id": "matmul_result",
                    }
                ],
            },
            {
                "step_id": "step_oracle_all_zero",
                "primitive_id": "evaluate_output_property",
                "template_slot": "oracle_check",
                "input_bindings": [
                    {"port_id": "result", "value_ref": "matmul_result"}
                ],
                "parameter_bindings": [
                    literal("check_kind", "all_zero"),
                    literal("expected_integer", 0),
                ],
                "output_bindings": [
                    {
                        "port_id": "oracle_holds",
                        "value_id": "oracle_holds",
                    }
                ],
            },
        ],
        "spec_bindings": [
            {
                "spec_element_type": "target_property",
                "spec_element_id": "tp_zero_reduction",
                "implementation_step_ids": [
                    "step_observe_zero_dimension"
                ],
            },
            {
                "spec_element_type": "activation_target",
                "spec_element_id": "at_zero_reduction",
                "implementation_step_ids": [
                    "step_observe_zero_dimension"
                ],
            },
            {
                "spec_element_type": "oracle_requirement",
                "spec_element_id": "or_all_zero",
                "implementation_step_ids": ["step_oracle_all_zero"],
            },
        ],
        "failure_handlers": [],
    }
    return {
        "implementation_plan": {
            "branch_strategies": [branch]
        }
    }


def resolved_inputs(
    *,
    catalog: dict | None = None,
    strategy_record: dict | None = None,
    harness_spec_record: dict | None = None,
) -> object:
    return MODULE.ResolvedInputs(
        strategy=strategy_record or strategy(),
        harness_spec=harness_spec_record or harness_spec(),
        catalog=catalog or load_catalog(),
        api_profile=api_profile(),
        helper_profiles={},
    )


def materialize(resolved: object) -> tuple[str, list[dict], list[dict]]:
    ranges = {"br_zero_reduction": (0, 255)}
    source, materialization_map, instrumentation_map = (
        MODULE.materialize_strategy(resolved, ranges, TEMPLATE_PATH)
    )
    source = MODULE.finalize_source(
        source,
        "ha_test",
        "0" * 64,
        len(instrumentation_map),
    )
    MODULE.resolve_source_spans(
        source,
        materialization_map,
        instrumentation_map,
    )
    MODULE.validate_materialization_maps(
        resolved.strategy,
        resolved.harness_spec,
        materialization_map,
        instrumentation_map,
    )
    return source, materialization_map, instrumentation_map


class HarnessArtifactBuilderTests(unittest.TestCase):
    def test_catalog_is_schema_valid_and_approved(self) -> None:
        schema = json.loads(
            CATALOG_SCHEMA_PATH.read_text(encoding="utf-8")
        )
        catalog = load_catalog()
        Draft202012Validator.check_schema(schema)
        errors = list(
            Draft202012Validator(
                schema,
                format_checker=FormatChecker(),
            ).iter_errors(catalog)
        )
        self.assertEqual(errors, [])
        self.assertEqual(
            catalog["review"]["validation_status"],
            "passed",
        )
        self.assertEqual(
            catalog["review"]["human_review_status"],
            "approved",
        )

    def test_minimal_emitters_are_registered(self) -> None:
        expected = {
            "emit_construct_tensor_from_fuzz",
            "emit_construct_tensor_with_constraints",
            "emit_enforce_dimension_relation",
            "emit_evaluate_tensor_property",
            "emit_profiled_target_api",
            "emit_evaluate_output_property",
            "emit_evaluate_tensor_determinism",
        }
        self.assertTrue(expected.issubset(MODULE.EMITTERS))

    def test_materialization_is_deterministic_and_ordered(self) -> None:
        first = materialize(resolved_inputs())
        second = materialize(resolved_inputs())
        self.assertEqual(first, second)

        source, materialization_map, instrumentation_map = first
        slots = [item["template_slot"] for item in materialization_map]
        indexes = [MODULE.SLOT_ORDER.index(slot) for slot in slots]
        self.assertEqual(indexes, sorted(indexes))
        segment_by_step = {
            item["step_id"]: item["emitted_segment_id"]
            for item in materialization_map
        }
        self.assertLess(
            source.index(segment_by_step["step_construct_left"]),
            source.index(segment_by_step["step_call_matmul"]),
        )
        self.assertLess(
            source.index(segment_by_step["step_call_matmul"]),
            source.index(segment_by_step["step_oracle_all_zero"]),
        )
        event_kinds = {item["event_kind"] for item in instrumentation_map}
        self.assertTrue(
            {
                "activation_checked",
                "activation_true",
                "target_api_reached",
                "target_api_completed",
                "oracle_evaluated",
                "oracle_passed",
                "oracle_failed",
            }.issubset(event_kinds)
        )


    def test_determinism_materializes_two_identical_calls_and_comparison(self) -> None:
        spec_record = harness_spec()
        spec_branch = spec_record["exploration_plan"]["branches"][0]
        spec_branch["oracle_requirements"] = [
            {
                "oracle_requirement_id": "or_determinism",
                "oracle_type": "determinism",
            }
        ]
        strategy_record = strategy()
        branch = strategy_record["implementation_plan"]["branch_strategies"][0]
        first_call = next(
            step
            for step in branch["steps"]
            if step["primitive_id"] == "invoke_profiled_target_api"
        )
        second_call = copy.deepcopy(first_call)
        second_call["step_id"] = "step_call_matmul_repeat"
        second_call["output_bindings"][0]["value_id"] = "matmul_result_repeat"
        first_index = branch["steps"].index(first_call)
        branch["steps"].insert(first_index + 1, second_call)
        oracle = next(
            step
            for step in branch["steps"]
            if step["primitive_id"] == "evaluate_output_property"
        )
        oracle.update(
            {
                "step_id": "step_oracle_determinism",
                "primitive_id": "evaluate_tensor_determinism",
                "input_bindings": [
                    {"port_id": "first_result", "value_ref": "matmul_result"},
                    {
                        "port_id": "second_result",
                        "value_ref": "matmul_result_repeat",
                    },
                ],
                "parameter_bindings": [],
            }
        )
        oracle_binding = next(
            binding
            for binding in branch["spec_bindings"]
            if binding["spec_element_type"] == "oracle_requirement"
        )
        oracle_binding["spec_element_id"] = "or_determinism"
        oracle_binding["implementation_step_ids"] = [
            "step_oracle_determinism"
        ]

        source, _, instrumentation = materialize(
            resolved_inputs(
                strategy_record=strategy_record,
                harness_spec_record=spec_record,
            )
        )
        self.assertEqual(source.count("= at::matmul("), 2)
        self.assertIn("torch::equal(", source)
        self.assertEqual(
            sum(
                item["event_kind"] == "target_api_reached"
                for item in instrumentation
            ),
            2,
        )
        self.assertEqual(
            sum(
                item["event_kind"] == "target_api_completed"
                for item in instrumentation
            ),
            2,
        )

    def test_determinism_rejects_nonidentical_target_bindings(self) -> None:
        spec_record = harness_spec()
        spec_record["exploration_plan"]["branches"][0][
            "oracle_requirements"
        ] = [
            {
                "oracle_requirement_id": "or_determinism",
                "oracle_type": "determinism",
            }
        ]
        strategy_record = strategy()
        branch = strategy_record["implementation_plan"]["branch_strategies"][0]
        first_call = next(
            step
            for step in branch["steps"]
            if step["primitive_id"] == "invoke_profiled_target_api"
        )
        second_call = copy.deepcopy(first_call)
        second_call["step_id"] = "step_call_matmul_repeat"
        second_call["input_bindings"][1]["value_ref"] = "left_tensor"
        second_call["output_bindings"][0]["value_id"] = "matmul_result_repeat"
        branch["steps"].insert(branch["steps"].index(first_call) + 1, second_call)
        oracle = next(
            step
            for step in branch["steps"]
            if step["primitive_id"] == "evaluate_output_property"
        )
        oracle.update(
            {
                "step_id": "step_oracle_determinism",
                "primitive_id": "evaluate_tensor_determinism",
                "input_bindings": [
                    {"port_id": "first_result", "value_ref": "matmul_result"},
                    {
                        "port_id": "second_result",
                        "value_ref": "matmul_result_repeat",
                    },
                ],
                "parameter_bindings": [],
            }
        )
        oracle_binding = next(
            binding
            for binding in branch["spec_bindings"]
            if binding["spec_element_type"] == "oracle_requirement"
        )
        oracle_binding["spec_element_id"] = "or_determinism"
        oracle_binding["implementation_step_ids"] = [
            "step_oracle_determinism"
        ]
        with self.assertRaisesRegex(
            MODULE.MaterializationError,
            "identical bindings",
        ):
            materialize(
                resolved_inputs(
                    strategy_record=strategy_record,
                    harness_spec_record=spec_record,
                )
            )

    def test_dynamic_target_contract_uses_api_profile(self) -> None:
        catalog = load_catalog()
        primitive = next(
            item
            for item in catalog["primitives"]
            if item["primitive_kind"] == "target_api_invoke"
        )
        resolved = MODULE.resolve_materialization_primitive(
            primitive,
            api_profile(),
        )
        self.assertEqual(
            [item["port_id"] for item in resolved["input_contract"]],
            ["binding_param_000_self", "binding_param_001_other"],
        )
        self.assertEqual(
            resolved["output_contract"],
            [
                {
                    "port_id": "return_000",
                    "produced_value_kind": "tensor",
                    "binding_required": True,
                }
            ],
        )

    def test_missing_emitter_is_rejected(self) -> None:
        catalog = load_catalog()
        target = next(
            item
            for item in catalog["primitives"]
            if item["primitive_id"] == "invoke_profiled_target_api"
        )
        target["implementation_binding"]["emitter_id"] = "missing_emitter"
        with self.assertRaisesRegex(
            MODULE.MaterializationError,
            "No deterministic Emitter",
        ):
            materialize(resolved_inputs(catalog=catalog))

    def test_duplicate_spec_binding_is_rejected(self) -> None:
        strategy_record = strategy()
        bindings = strategy_record["implementation_plan"][
            "branch_strategies"
        ][0]["spec_bindings"]
        bindings.append(copy.deepcopy(bindings[0]))
        with self.assertRaisesRegex(
            MODULE.MaterializationError,
            "more than once",
        ):
            materialize(resolved_inputs(strategy_record=strategy_record))

    def test_out_of_order_slots_are_rejected(self) -> None:
        strategy_record = strategy()
        steps = strategy_record["implementation_plan"][
            "branch_strategies"
        ][0]["steps"]
        steps[2], steps[3] = steps[3], steps[2]
        with self.assertRaisesRegex(
            MODULE.MaterializationError,
            "template-slot order",
        ):
            materialize(resolved_inputs(strategy_record=strategy_record))

    def test_compile_failure_keeps_diagnostics_without_binary(self) -> None:
        config = MODULE.CompileConfiguration(
            command_argv=("compiler", "{source}", "-o", "{binary}"),
            timeout_seconds=10,
            build_environment_ref={
                "artifact_id": "test_compile_environment",
                "artifact_version": 1,
                "content_hash": "1" * 64,
            },
        )
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=7,
            stdout="",
            stderr="compile failed",
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = root / "staging"
            final = root / "final"
            staging.mkdir()
            final.mkdir()
            (staging / "main.cpp").write_text(
                "int main() {}\n",
                encoding="utf-8",
            )
            with (
                mock.patch.object(
                    MODULE.subprocess,
                    "run",
                    return_value=completed,
                ),
                mock.patch.object(
                    MODULE,
                    "file_reference",
                    side_effect=lambda content, reference=None: {
                        "relative_path": (reference or content).name,
                        "content_hash": MODULE.file_hash(content),
                    },
                ),
            ):
                result = MODULE.compile_harness(
                    config,
                    staging,
                    final,
                    ROOT / "runtime/harness_instrumentation.h",
                    ROOT / "runtime/harness_instrumentation.cpp",
                )

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["exit_code"], 7)
            self.assertIsNotNone(result["diagnostics_ref"])
            self.assertIsNone(result["binary_artifact"])
            self.assertIn(
                "compile failed",
                (staging / "compile_diagnostics.txt").read_text(
                    encoding="utf-8"
                ),
            )


if __name__ == "__main__":
    unittest.main()
