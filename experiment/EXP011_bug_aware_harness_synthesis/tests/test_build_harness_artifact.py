#!/usr/bin/env python3
"""Deterministic tests for Strategy Plan v1.2 materialization."""

from __future__ import annotations

import copy
import importlib.util
import json
import shutil
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


def primitive(primitive_id: str) -> dict:
    return next(
        item for item in load_catalog()["primitives"]
        if item["primitive_id"] == primitive_id
    )


def api_profile(*, returns: int = 1, with_defaults: bool = False) -> dict:
    parameters = [
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
    ]
    if with_defaults:
        parameters.extend(
            [
                {
                    "binding_parameter_id": "binding_param_002_momentum",
                    "ordinal": 2,
                    "schema_type": "float",
                    "default": 0.1,
                },
                {
                    "binding_parameter_id": "binding_param_003_optional",
                    "ordinal": 3,
                    "schema_type": "Tensor?",
                    "default": "None",
                },
            ]
        )
    python_returns = [
        {
            "return_id": f"return_{index:03d}",
            "normalized_types": ["tensor"],
            "semantic_role": "result_tensor",
        }
        for index in range(returns)
    ]
    return {
        "python_contract": {"returns": python_returns},
        "target_binding": {
            "cpp_callable": "at::matmul",
            "binding_parameters": parameters,
            "return_mapping": [
                {
                    "binding_return_position": index,
                    "python_return_ref": item["return_id"],
                    "mapping_kind": "direct",
                }
                for index, item in enumerate(python_returns)
            ],
        },
    }


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
        "exploration_plan": {
            "branches": [
                {
                    "branch_id": "br_zero_reduction",
                    "target_conditions": [
                        {
                            "condition_id": "tc_zero_numel",
                            "role": "exploration_variable",
                            "predicate": {
                                "predicate_id": "property_relation",
                                "arguments": {
                                    "subject_ref": "param_left",
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
                            "observation_id": "obs_termination",
                            "subject_refs": ["context.execution"],
                            "observe_at": "on_target_api_termination",
                            "description": "Record termination through Runner events.",
                            "source_refs": [source_ref()],
                        }
                    ],
                    "behavior_checks": [],
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
    *,
    dtype: str = "float32",
    fill: str = "fuzz_numeric",
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
            literal("dtype_policy", dtype),
            literal("fill_policy", fill),
            literal("max_dimension", 4),
        ],
        "output_bindings": [
            {"port_id": "tensor", "value_id": tensor_value},
            {"port_id": "next_cursor", "value_id": cursor_value},
        ],
    }


def strategy() -> dict:
    return {
        "implementation_plan": {
            "branch_strategies": [
                {
                    "source_branch_id": "br_zero_reduction",
                    "budget_share": 1.0,
                    "steps": [
                        construct_step(
                            "step_construct_left", "offset", [2, 0],
                            "left_tensor", "cursor_after_left",
                        ),
                        construct_step(
                            "step_construct_right", "cursor_after_left", [0, 3],
                            "right_tensor", "cursor_after_right",
                        ),
                        {
                            "step_id": "step_observe_zero",
                            "primitive_id": "evaluate_tensor_property",
                            "template_slot": "pre_call_observation",
                            "input_bindings": [
                                {"port_id": "subject", "value_ref": "left_tensor"}
                            ],
                            "parameter_bindings": [
                                literal("property_kind", "numel_equals_zero"),
                                literal("axis", 0),
                                literal("expected_integer", 0),
                            ],
                            "output_bindings": [
                                {"port_id": "property_holds", "value_id": "zero_observed"}
                            ],
                        },
                        {
                            "step_id": "step_call_matmul",
                            "primitive_id": "invoke_profiled_target_api",
                            "template_slot": "target_call",
                            "input_bindings": [
                                {"port_id": "binding_param_000_self", "value_ref": "left_tensor"},
                                {"port_id": "binding_param_001_other", "value_ref": "right_tensor"},
                            ],
                            "parameter_bindings": [],
                            "output_bindings": [
                                {"port_id": "return_000", "value_id": "matmul_result"}
                            ],
                        },
                    ],
                    "spec_bindings": [
                        {
                            "spec_element_type": "target_condition",
                            "spec_element_id": "tc_zero_numel",
                            "binding_kind": "in_harness_steps",
                            "implementation_step_ids": [
                                "step_construct_left", "step_observe_zero"
                            ],
                            "runner_events": [],
                        },
                        {
                            "spec_element_type": "behavior_observation",
                            "spec_element_id": "obs_termination",
                            "binding_kind": "runner_event",
                            "implementation_step_ids": [],
                            "runner_events": [
                                "target_api_returned", "process_signal", "timeout"
                            ],
                        },
                    ],
                    "failure_handlers": [],
                }
            ]
        }
    }


def resolved_inputs(
    *, catalog: dict | None = None, strategy_record: dict | None = None,
    harness_spec_record: dict | None = None, api_profile_record: dict | None = None,
) -> object:
    return MODULE.ResolvedInputs(
        strategy=strategy_record or strategy(),
        harness_spec=harness_spec_record or harness_spec(),
        catalog=catalog or load_catalog(),
        api_profile=api_profile_record or api_profile(),
        helper_profiles={},
    )


def materialize(resolved: object) -> tuple[str, list[dict], list[dict]]:
    source, materialization_map, instrumentation_map = MODULE.materialize_strategy(
        resolved, {"br_zero_reduction": (0, 255)}, TEMPLATE_PATH
    )
    source = MODULE.finalize_source(
        source, "ha_test", "0" * 64, len(instrumentation_map)
    )
    MODULE.resolve_source_spans(source, materialization_map, instrumentation_map)
    MODULE.validate_materialization_maps(
        resolved.strategy, resolved.harness_spec,
        materialization_map, instrumentation_map,
    )
    return source, materialization_map, instrumentation_map


def emitter_context(
    primitive_id: str, *, parameters: dict[str, object] | None = None,
    inputs: dict[str, object] | None = None, outputs: dict[str, str] | None = None,
    profile: dict | None = None, spec_bindings: tuple[dict, ...] = (),
) -> object:
    selected = primitive(primitive_id)
    if selected["primitive_kind"] == "target_api_invoke":
        selected = MODULE.resolve_materialization_primitive(
            selected, profile or api_profile()
        )
    return MODULE.EmitterContext(
        branch_id="br_zero_reduction",
        step={"step_id": "step_test", "template_slot": "target_call"},
        primitive=selected,
        inputs={
            key: value if isinstance(value, MODULE.BoundValue)
            else MODULE.BoundValue(str(value), "test")
            for key, value in (inputs or {}).items()
        },
        parameters={
            key: MODULE.BoundParameter("literal", value)
            for key, value in (parameters or {}).items()
        },
        output_names=outputs or {},
        spec_bindings=spec_bindings,
        failure_handlers=(
            {
                "failure_handler_id": "fh_short",
                "trigger": {
                    "step_id": "step_test",
                    "outcome_id": "insufficient_fuzz_data",
                },
                "terminal_action": "reject_input",
            },
        ),
        strategy_branch={"spec_bindings": list(spec_bindings)},
        harness_spec=harness_spec(),
        api_profile=profile or api_profile(),
        helper_profile=None,
    )


class HarnessArtifactBuilderTests(unittest.TestCase):
    def test_generic_pair_empty_evaluation_target_covers_either_tensor_once(self) -> None:
        target = {"evaluation_target_id": "et_pair_empty", "detector_id": "tensor_pair_empty_v1",
                  "parameter_bindings": [{"parameter_role": "left", "binding_parameter_id": "binding_param_000_left"},
                                         {"parameter_role": "right", "binding_parameter_id": "binding_param_001_right"}]}
        inputs = {"binding_param_000_left": MODULE.BoundValue("input1", "tensor"),
                  "binding_param_001_right": MODULE.BoundValue("input2", "tensor")}
        atoms = MODULE.evaluation_target_atoms(target, "br_test", inputs)
        self.assertIn("(input1.numel() == 0 || input2.numel() == 0)", atoms[0])
        self.assertEqual(sum(atom.event_kind == "activation_true" for atom in atoms if isinstance(atom, MODULE.EventAtom)), 1)

    def test_catalog_is_schema_valid_and_all_emitters_exist(self) -> None:
        schema = json.loads(CATALOG_SCHEMA_PATH.read_text(encoding="utf-8"))
        catalog = load_catalog()
        Draft202012Validator.check_schema(schema)
        self.assertEqual(
            list(
                Draft202012Validator(
                    schema, format_checker=FormatChecker()
                ).iter_errors(catalog)
            ),
            [],
        )
        expected = {
            item["implementation_binding"]["emitter_id"]
            for item in catalog["primitives"]
        }
        self.assertTrue(expected.issubset(MODULE.EMITTERS))
        self.assertEqual(
            MODULE.TEMPLATE_BUILTINS["none"],
            ("c10::nullopt", "optional_value"),
        )

    def test_v12_materialization_is_deterministic_and_runner_binding_is_external(self) -> None:
        first = materialize(resolved_inputs())
        second = materialize(resolved_inputs())
        self.assertEqual(first, second)
        source, materialization_map, events = first
        self.assertEqual(
            [entry["step_id"] for entry in materialization_map],
            [
                "step_construct_left", "step_construct_right",
                "step_observe_zero", "step_call_matmul",
            ],
        )
        condition_events = [
            item for item in events
            if ("target_condition", "tc_zero_numel") in {
                (ref["ref_type"], ref["ref_id"])
                for ref in item["trace_refs"]
            }
        ]
        self.assertEqual(
            {item["event_kind"] for item in condition_events},
            {
                "observation_captured", "activation_checked",
                "activation_true", "activation_unevaluable",
                "activation_check_error",
            },
        )
        self.assertNotIn("obs_termination", source)
        self.assertEqual(source.count('.emplace(at::matmul('), 1)
        self.assertIn('catch (const c10::Error&', source)

    def test_tensor_constructor_supports_zero_dynamic_shape_and_three_dtypes(self) -> None:
        for dtype, cpp_dtype in (
            ("float32", "torch::kFloat32"),
            ("int64", "torch::kInt64"),
            ("bool", "torch::kBool"),
        ):
            record = strategy()
            first = record["implementation_plan"]["branch_strategies"][0]["steps"][0]
            first["parameter_bindings"] = [
                literal("shape_template", [-1, 0]),
                literal("dtype_policy", dtype),
                literal("fill_policy", "fuzz_sign"),
                literal("max_dimension", 4),
            ]
            source, _, _ = materialize(
                resolved_inputs(strategy_record=record)
            )
            self.assertIn("% 5U", source)
            self.assertIn(cpp_dtype, source)

    def test_scalar_emitters_cover_float_integer_and_boolean(self) -> None:
        cases = (
            (
                "construct_floating_from_fuzz",
                {"minimum": -1.0, "maximum": 1.0},
                "const double",
            ),
            (
                "construct_integer_from_fuzz",
                {"minimum": -2, "maximum": 2},
                "const std::int64_t",
            ),
            ("construct_boolean_from_fuzz", {}, "const bool"),
        )
        for primitive_id, parameters, token in cases:
            context = emitter_context(
                primitive_id,
                parameters=parameters,
                inputs={"data": "Data", "size": "Size", "cursor": "cursor"},
                outputs={"value": "value", "next_cursor": "next_cursor"},
            )
            emitted = MODULE.emit_construct_scalar_from_fuzz(context)
            self.assertIn(
                token,
                "\n".join(
                    atom for atom in emitted.atoms if isinstance(atom, str)
                ),
            )
            self.assertEqual(
                emitted.outputs["value"].value_kind,
                primitive(primitive_id)["output_contract"][0]["produced_value_kind"],
            )

    def test_multibyte_integer_short_input_has_matching_rejection_event(self) -> None:
        context = emitter_context(
            "construct_integer_from_fuzz",
            parameters={"minimum": 0, "maximum": 65535},
            inputs={"data": "Data", "size": "Size", "cursor": "cursor"},
            outputs={"value": "value", "next_cursor": "next_cursor"},
        )
        emitted = MODULE.emit_construct_scalar_from_fuzz(context)
        rejected = [
            atom for atom in emitted.atoms
            if isinstance(atom, MODULE.EventAtom)
            and atom.event_kind == "input_rejected"
        ]
        self.assertEqual(len(rejected), 1)
        self.assertIn("< 2U", rejected[0].condition_expression)
        self.assertIn("return 0", "\n".join(
            atom for atom in emitted.atoms if isinstance(atom, str)
        ))

    def test_missing_target_exception_instrumentation_is_rejected(self) -> None:
        source, materialization, instrumentation = materialize(resolved_inputs())
        del source
        incomplete = [
            event for event in instrumentation
            if event["event_kind"] != "target_api_exception"
        ]
        for site_id, event in enumerate(incomplete):
            event["runtime_site_id"] = site_id
        with self.assertRaisesRegex(
            MODULE.MaterializationError, "target_api_exception"
        ):
            MODULE.validate_materialization_maps(
                strategy(), harness_spec(), materialization, incomplete
            )

    def test_build_request_changes_cache_key_without_changing_source_key(self) -> None:
        source_key = "a" * 64
        first = {
            "compile_profile_ref": {"artifact_id": "compile", "artifact_version": 1, "content_hash": "1" * 64},
            "dependency_refs": [], "environment_identity": "image-a", "strategy_review_ref": None,
        }
        changed = copy.deepcopy(first)
        changed["compile_profile_ref"]["content_hash"] = "2" * 64
        self.assertNotEqual(
            MODULE.build_generation_key(source_key, first),
            MODULE.build_generation_key(source_key, changed),
        )
        alternate_review = copy.deepcopy(first)
        alternate_review["strategy_review_ref"] = {
            "artifact_id": "another_approved_review",
            "artifact_version": "1.1",
            "content_hash": "3" * 64,
            "relative_path": "review.json",
        }
        self.assertEqual(
            MODULE.build_generation_key(source_key, first),
            MODULE.build_generation_key(source_key, alternate_review),
        )

    def test_compile_profile_hashes_explicit_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            profile_path = Path(temporary) / "compile.json"
            dependency = MODULE.REPOSITORY_ROOT / "third_party/FlashFuzz/scripts/template/torch_cpu/fuzzer_utils.h"
            record = {
                "profile_id": "test_compile", "profile_version": 1,
                "command_argv": ["clang++", "{source}", "-o", "{binary}"],
                "timeout_seconds": 10,
                "dependency_files": [dependency.relative_to(MODULE.REPOSITORY_ROOT).as_posix()],
                "environment_identity": "pytorch-test-image",
            }
            profile_path.write_text(json.dumps(record), encoding="utf-8")
            config = MODULE.load_compile_config(profile_path)
        self.assertEqual(len(config.dependency_refs), 1)
        self.assertEqual(config.environment_identity, "pytorch-test-image")
        self.assertEqual(config.dependency_refs[0]["content_hash"], MODULE.file_hash(dependency))

    def test_runtime_bounds_exception_text_without_sampling_counters(self) -> None:
        compiler = shutil.which("g++") or shutil.which("clang++")
        if compiler is None:
            self.skipTest("C++ compiler unavailable")
        runtime = ROOT / "runtime"
        source = r'''#include "harness_instrumentation.h"
int main() {
  hbfg::InstrumentationRegistry registry(0, {"artifact", "generation"});
  for (int i = 0; i < 20; ++i) {
    auto iteration = registry.begin_iteration();
    iteration.log_target_api_exception("fixture");
  }
  return 0;
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            (path / "runtime.cpp").write_text(source, encoding="utf-8")
            compiled = subprocess.run(
                [compiler, "-std=c++17", "-Wall", "-Werror", "-pthread",
                 f"-I{runtime}", str(path / "runtime.cpp"),
                 str(runtime / "harness_instrumentation.cpp"),
                 "-o", str(path / "runtime_smoke")],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            result = subprocess.run(
                [str(path / "runtime_smoke")],
                capture_output=True, text=True, timeout=10,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr.count("HBFG_TARGET_API_EXCEPTION="), 16)

    def test_unreferenced_profile_does_not_block_selected_task(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "api_profile__unrelated__r001.json"
            path.write_text(json.dumps({
                "profile_id": "unrelated_profile", "revision": 1,
                "metadata": {"content_hash": "0" * 64},
            }), encoding="utf-8")
            validator = mock.Mock()
            store = MODULE.load_profile_store(
                root, validator, "API Profile",
                [{"profile_id": "selected_profile", "revision": 1,
                  "content_hash": "1" * 64}],
            )
        self.assertEqual(store, {})
        validator.iter_errors.assert_not_called()

    def test_target_emitter_omits_trailing_defaults_and_accepts_none(self) -> None:
        profile = api_profile(with_defaults=True)
        context = emitter_context(
            "invoke_profiled_target_api",
            inputs={
                "binding_param_000_self": MODULE.BoundValue("left", "tensor"),
                "binding_param_001_other": MODULE.BoundValue("right", "tensor"),
            },
            outputs={"return_000": "result"},
            profile=profile,
        )
        emission = MODULE.emit_profiled_target_api(context)
        self.assertIn("at::matmul(left, right)", emission.atoms[1])

        context = emitter_context(
            "invoke_profiled_target_api",
            inputs={
                "binding_param_000_self": MODULE.BoundValue("left", "tensor"),
                "binding_param_001_other": MODULE.BoundValue("right", "tensor"),
                "binding_param_002_momentum": MODULE.BoundValue(
                    "momentum", "floating"
                ),
                "binding_param_003_optional": MODULE.BoundValue(
                    "c10::nullopt", "optional_value"
                ),
            },
            outputs={"return_000": "result"},
            profile=profile,
        )
        self.assertIn(
            "at::matmul(left, right, momentum, c10::nullopt)",
            MODULE.emit_profiled_target_api(context).atoms[1],
        )

    def test_target_emitter_supports_multiple_and_zero_returns(self) -> None:
        multi = api_profile(returns=2)
        context = emitter_context(
            "invoke_profiled_target_api",
            inputs={
                "binding_param_000_self": MODULE.BoundValue("left", "tensor"),
                "binding_param_001_other": MODULE.BoundValue("right", "tensor"),
            },
            outputs={"return_000": "first", "return_001": "second"},
            profile=multi,
        )
        self.assertIn(
            'auto [first, second] = std::move(*hbfg_call_result_step_test);',
            MODULE.emit_profiled_target_api(context).atoms,
        )
        no_return = api_profile(returns=0)
        context = emitter_context(
            "invoke_profiled_target_api",
            inputs={
                "binding_param_000_self": MODULE.BoundValue("left", "tensor"),
                "binding_param_001_other": MODULE.BoundValue("right", "tensor"),
            },
            outputs={},
            profile=no_return,
        )
        self.assertIn(
            'at::matmul(left, right);',
            MODULE.emit_profiled_target_api(context).atoms,
        )

    def test_reference_constructor_and_inequality_relation_are_observations(self) -> None:
        context = emitter_context(
            "construct_tensor_from_reference",
            parameters={
                "shape_policy": "same_shape", "dtype_policy": "bool",
                "fill_policy": "fuzz_sign",
            },
            inputs={
                "reference": "reference", "data": "Data",
                "size": "Size", "cursor": "cursor",
            },
            outputs={"tensor": "derived", "next_cursor": "next_cursor"},
        )
        source = "\n".join(
            atom for atom in
            MODULE.emit_construct_tensor_from_reference(context).atoms
            if isinstance(atom, str)
        )
        self.assertIn("reference.sizes().vec()", source)
        self.assertIn("torch::kBool", source)

        context = emitter_context(
            "construct_tensor_with_rank_range",
            parameters={"minimum_rank": 1, "maximum_rank": 2,
                        "minimum_dimension": 0, "max_dimension": 4,
                        "dtype_policy": "float32", "fill_policy": "fuzz_numeric"},
            inputs={"data": "Data", "size": "Size", "cursor": "cursor"},
            outputs={"tensor": "ranked", "next_cursor": "ranked_cursor"},
        )
        source = "\n".join(atom for atom in MODULE.emit_construct_tensor_with_rank_range(context).atoms if isinstance(atom, str))
        self.assertIn("ranked_rank", source)
        self.assertIn("ranked_shape.push_back", source)

        context = emitter_context(
            "construct_tensor_from_reference",
            parameters={"shape_policy": "drop_last_dimension", "dtype_policy": "int64", "fill_policy": "fuzz_sign"},
            inputs={"reference": "ranked", "data": "Data", "size": "Size", "cursor": "cursor"},
            outputs={"tensor": "labels", "next_cursor": "labels_cursor"},
        )
        source = "\n".join(atom for atom in MODULE.emit_construct_tensor_from_reference(context).atoms if isinstance(atom, str))
        self.assertIn("pop_back", source)

        binding = ({
            "spec_element_type": "target_condition",
            "spec_element_id": "tc_zero_numel",
            "binding_kind": "in_harness_steps",
            "implementation_step_ids": ["step_test"],
            "runner_events": [],
        },)
        context = emitter_context(
            "evaluate_tensor_relation",
            parameters={
                "property_kind": "shape", "relation_kind": "not_equals"
            },
            inputs={"left": "left", "right": "right"},
            outputs={"relation_holds": "relation_holds"},
            spec_bindings=binding,
        )
        context = MODULE.EmitterContext(
            **{
                **context.__dict__,
                "step": {
                    "step_id": "step_test",
                    "template_slot": "pre_call_observation",
                },
            }
        )
        emission = MODULE.emit_evaluate_tensor_relation(context)
        self.assertIn("!", emission.atoms[0])
        self.assertFalse(
            any(
                isinstance(atom, str) and "return 0" in atom
                for atom in emission.atoms
            )
        )

    def test_dynamic_target_contract_uses_profile_types(self) -> None:
        profile = api_profile(with_defaults=True)
        resolved = MODULE.resolve_materialization_primitive(
            primitive("invoke_profiled_target_api"), profile
        )
        contracts = {
            item["port_id"]: item for item in resolved["input_contract"]
        }
        self.assertEqual(
            contracts["binding_param_002_momentum"]["accepted_value_kinds"],
            ["floating"],
        )
        self.assertEqual(
            contracts["binding_param_003_optional"]["accepted_value_kinds"],
            ["tensor", "optional_value"],
        )
        self.assertFalse(contracts["binding_param_002_momentum"]["required"])

    def test_missing_emitter_duplicate_binding_and_slot_order_are_rejected(self) -> None:
        catalog = load_catalog()
        target = next(
            item for item in catalog["primitives"]
            if item["primitive_id"] == "invoke_profiled_target_api"
        )
        target["implementation_binding"]["emitter_id"] = "missing_emitter"
        with self.assertRaisesRegex(
            MODULE.MaterializationError, "No deterministic Emitter"
        ):
            materialize(resolved_inputs(catalog=catalog))

        record = strategy()
        bindings = record["implementation_plan"]["branch_strategies"][0]["spec_bindings"]
        bindings.append(copy.deepcopy(bindings[0]))
        with self.assertRaisesRegex(
            MODULE.MaterializationError, "more than once"
        ):
            materialize(resolved_inputs(strategy_record=record))

        record = strategy()
        steps = record["implementation_plan"]["branch_strategies"][0]["steps"]
        steps[2], steps[3] = steps[3], steps[2]
        with self.assertRaisesRegex(
            MODULE.MaterializationError, "template-slot order"
        ):
            materialize(resolved_inputs(strategy_record=record))

    def test_compile_argv_expands_host_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            staging = Path(temporary)
            argv = MODULE.resolve_compile_argv(
                (
                    "docker", "-e", "HOST_UID={host_uid}", "-e",
                    "HOST_GID={host_gid}", "-v",
                    "{artifact_dir}:/artifact", "{source}", "{binary}",
                ),
                staging,
                ROOT / "runtime/harness_instrumentation.h",
                ROOT / "runtime/harness_instrumentation.cpp",
            )
        self.assertIn(f"HOST_UID={MODULE.os.getuid()}", argv)
        self.assertIn(f"HOST_GID={MODULE.os.getgid()}", argv)
        self.assertEqual(argv[-2:], ["main.cpp", "harness_binary"])

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
            args=[], returncode=7, stdout="", stderr="compile failed"
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging, final = root / "staging", root / "final"
            staging.mkdir()
            final.mkdir()
            (staging / "main.cpp").write_text(
                "int main() {}\n", encoding="utf-8"
            )
            with (
                mock.patch.object(
                    MODULE.subprocess, "run", return_value=completed
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
                    config, staging, final,
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
