#!/usr/bin/env python3
"""Deterministic Runtime Promotion tests for API Profile construction."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


SCRIPT = Path(
    "experiment/EXP011_bug_aware_harness_synthesis/scripts/"
    "build_api_profile.py"
)
SPEC = importlib.util.spec_from_file_location("build_api_profile", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def profile(parameters: list[tuple[str, str | None]]) -> dict:
    return {
        "target_binding": {
            "cpp_callable": "at::example",
            "binding_parameters": [
                {
                    "binding_parameter_id": f"binding_param_{index:03d}_arg_{index}",
                    "name": f"arg_{index}",
                    "ordinal": index,
                    "schema_type": schema_type,
                    "default": default,
                }
                for index, (schema_type, default) in enumerate(parameters)
            ],
        }
    }


class RuntimePromotionSourceTests(unittest.TestCase):
    def test_schema_is_valid_draft_2020_12(self) -> None:
        schema = json.loads(MODULE.DEFAULT_SCHEMA.read_text(encoding="utf-8"))
        MODULE.jsonschema.Draft202012Validator.check_schema(schema)

    def test_runtime_signature_preserves_python_only_parameters(self) -> None:
        selected = MODULE.select_python_contract({
            "runtime": {
                "signature": "(model=None, *, fullgraph=False)",
                "parameters": [
                    {"name": "model", "kind": "positional_or_keyword",
                     "annotation": "Callable | None", "default": "None"},
                    {"name": "fullgraph", "kind": "keyword_only",
                     "annotation": "bool", "default": "False"},
                ],
                "return_annotation": "Callable",
            },
            "pyi": {"signatures": []},
        })
        self.assertEqual([item["name"] for item in selected["parameters"]],
                         ["model", "fullgraph"])
        self.assertEqual(selected["source"], "runtime_signature")

    def test_optional_types_preserve_none(self) -> None:
        self.assertEqual(MODULE.normalized_types("Tensor | None"), ["tensor", "none"])
        self.assertEqual(MODULE.normalized_types("Optional[bool]"), ["boolean", "none"])
        self.assertEqual(
            MODULE.normalized_types("dict[str, int | bool | Callable] | None"),
            ["object", "none"],
        )

    def test_fixed_tuple_return_is_split_by_position(self) -> None:
        returns = MODULE.build_returns(
            "tuple[Tensor, Tensor, int, bool, float]", ["ev_signature"]
        )
        self.assertEqual(
            [item["documented_type"] for item in returns],
            ["Tensor", "Tensor", "int", "bool", "float"],
        )
        self.assertEqual(
            [item["normalized_types"] for item in returns],
            [["tensor"], ["tensor"], ["integer"], ["boolean"], ["floating"]],
        )
        self.assertEqual([item["position"] for item in returns], list(range(5)))

    def test_non_tuple_return_remains_one_value(self) -> None:
        returns = MODULE.build_returns("Tensor | None", ["ev_signature"])
        self.assertEqual(len(returns), 1)
        self.assertEqual(returns[0]["normalized_types"], ["tensor", "none"])

    def test_wrapper_mapping_is_evidence_driven(self) -> None:
        python_parameters = MODULE.build_python_parameters([
            {"name": "input1", "kind": "positional_or_keyword",
             "annotation": "Tensor", "default": None},
            {"name": "size_average", "kind": "positional_or_keyword",
             "annotation": "Optional[bool]", "default": "None"},
            {"name": "reduce", "kind": "positional_or_keyword",
             "annotation": "Optional[bool]", "default": "None"},
            {"name": "reduction", "kind": "positional_or_keyword",
             "annotation": "str", "default": "'mean'"},
        ], ["ev_signature"])
        binding_parameters = [
            {"binding_parameter_id": "binding_input", "name": "input1",
             "ordinal": 0, "schema_type": "Tensor", "default": None},
            {"binding_parameter_id": "binding_reduction", "name": "reduction",
             "ordinal": 1, "schema_type": "int", "default": "Mean"},
        ]
        wrapper = """def wrapper(input1, size_average=None, reduce=None, reduction='mean'):
    if size_average is not None or reduce is not None:
        reduction = legacy_get_string(size_average, reduce)
    reduction_enum = get_enum(reduction)
    return cosine_embedding_loss(input1, reduction_enum)
"""
        mapping, dispositions, complete = MODULE.build_argument_mapping(
            python_parameters, binding_parameters, wrapper,
            "cosine_embedding_loss", ["ev_wrapper", "ev_schema"]
        )
        self.assertTrue(complete)
        self.assertEqual(mapping[1]["mapping_kind"], "packed")
        self.assertEqual(
            mapping[1]["source_parameter_refs"],
            [
                "param_001_size_average",
                "param_002_reduce",
                "param_003_reduction",
            ],
        )
        self.assertIn("legacy_get_string(size_average, reduce)", mapping[1]["transformation"])
        self.assertIn("else reduction", mapping[1]["transformation"])
        by_ref = {item["python_parameter_ref"]: item["disposition"]
                  for item in dispositions}
        self.assertEqual(by_ref["param_001_size_average"], "converted")
        self.assertEqual(by_ref["param_002_reduce"], "converted")

    def test_conditional_binding_expression_preserves_both_branches(self) -> None:
        python_parameters = MODULE.build_python_parameters([
            {"name": "size_average", "kind": "positional_or_keyword",
             "annotation": "Optional[bool]", "default": "None"},
            {"name": "reduce", "kind": "positional_or_keyword",
             "annotation": "Optional[bool]", "default": "None"},
            {"name": "reduction", "kind": "positional_or_keyword",
             "annotation": "str", "default": "'mean'"},
        ], ["ev_signature"])
        binding_parameters = [{
            "binding_parameter_id": "binding_reduction", "name": "reduction",
            "ordinal": 0, "schema_type": "int", "default": "Mean",
        }]
        wrapper = """def wrapper(size_average=None, reduce=None, reduction='mean'):
    if size_average is not None or reduce is not None:
        reduction_enum = legacy_get_enum(size_average, reduce)
    else:
        reduction_enum = get_enum(reduction)
    return target(reduction_enum)
"""
        mapping, dispositions, complete = MODULE.build_argument_mapping(
            python_parameters, binding_parameters, wrapper,
            "target", ["ev_wrapper", "ev_schema"]
        )
        self.assertTrue(complete)
        self.assertEqual(mapping[0]["mapping_kind"], "packed")
        self.assertEqual(len(mapping[0]["source_parameter_refs"]), 3)
        self.assertIn("legacy_get_enum(size_average, reduce)", mapping[0]["transformation"])
        self.assertIn("get_enum(reduction)", mapping[0]["transformation"])
        self.assertEqual(
            {item["disposition"] for item in dispositions}, {"converted"}
        )

    def test_incomplete_return_mapping_is_blocking(self) -> None:
        validation = MODULE.build_validation(
            runtime_resolved=True,
            runtime_doc_available=True,
            runtime_version_mismatch=False,
            signature_resolved=True,
            binding_kind="aten_operator",
            argument_mapping_complete=True,
            return_mapping_complete=False,
            cpp_resolved=True,
            refs={"signature": "ev_signature", "schema": "ev_schema"},
        )
        self.assertEqual(validation["validation_status"], "failed")
        self.assertEqual(validation["execution_readiness"], "blocked")
        self.assertIn(
            "issue_return_mapping_unresolved",
            {item["issue_id"] for item in validation["issues"]},
        )
        checks = {item["check_id"]: item for item in validation["checks"]}
        self.assertEqual(checks["check_return_mapping"]["status"], "blocked")

    def test_mapping_does_not_guess_by_position(self) -> None:
        python_parameters = MODULE.build_python_parameters([
            {"name": "python_name", "kind": "positional_or_keyword",
             "annotation": "Tensor", "default": None},
        ], ["ev_signature"])
        binding_parameters = [{
            "binding_parameter_id": "binding_native_name", "name": "native_name",
            "ordinal": 0, "schema_type": "Tensor", "default": None,
        }]
        mapping, dispositions, complete = MODULE.build_argument_mapping(
            python_parameters, binding_parameters, None, "example", ["ev_schema"]
        )
        self.assertFalse(complete)
        self.assertEqual(mapping[0]["mapping_kind"], "unresolved")
        self.assertEqual(dispositions[0]["disposition"], "unresolved")

    def test_validation_case_controls_tensor_shapes(self) -> None:
        candidate = profile([("Tensor", None), ("Tensor", None)])
        first_ref = candidate["target_binding"]["binding_parameters"][0]["binding_parameter_id"]
        second_ref = candidate["target_binding"]["binding_parameters"][1]["binding_parameter_id"]
        source = MODULE.cpp_runtime_probe_source(candidate, {
            first_ref: {"kind": "tensor", "shape": [2, 3],
                        "dtype": "float32", "fill": "ones"},
            second_ref: {"kind": "tensor", "shape": [2],
                         "dtype": "float32", "fill": "ones"},
        })
        self.assertIn("torch::ones({2, 3}", source)
        self.assertIn("torch::ones({2}", source)

    def test_supported_required_and_optional_types(self) -> None:
        source = MODULE.cpp_runtime_probe_source(profile([
            ("Tensor", None),
            ("Tensor?", None),
            ("float", None),
            ("int", None),
            ("bool", None),
            ("Tensor(a!)", None),
            ("SymInt", None),
            ("float?", None),
            ("int?", None),
            ("bool?", None),
            ("Tensor(a!)?", None),
            ("SymInt?", None),
        ]))

        self.assertIn("auto hbfg_arg_0 = torch::ones", source)
        self.assertIn("double hbfg_arg_2 = 0.1;", source)
        self.assertIn("int64_t hbfg_arg_3 = 1;", source)
        self.assertIn("bool hbfg_arg_4 = false;", source)
        self.assertIn("auto hbfg_arg_5 = torch::ones", source)
        self.assertIn("c10::SymInt hbfg_arg_6 = 1;", source)
        self.assertIn(
            "at::example(hbfg_arg_0, std::nullopt, hbfg_arg_2, "
            "hbfg_arg_3, hbfg_arg_4, hbfg_arg_5, hbfg_arg_6, std::nullopt, "
            "std::nullopt, std::nullopt, std::nullopt, std::nullopt)",
            source,
        )

    def test_trailing_default_parameters_are_omitted(self) -> None:
        source = MODULE.cpp_runtime_probe_source(profile([
            ("Tensor", None),
            ("float", "0.5"),
            ("bool?", "None"),
        ]))

        self.assertIn("at::example(hbfg_arg_0)", source)
        self.assertNotIn("hbfg_arg_1", source)
        self.assertNotIn("std::nullopt", source)

    def test_all_default_parameters_allow_a_zero_argument_call(self) -> None:
        source = MODULE.cpp_runtime_probe_source(profile([
            ("int", "1"),
            ("bool", "False"),
        ]))

        self.assertIn("at::example()", source)

    def test_required_parameter_after_omitted_default_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            MODULE.BuildError, "required parameter after an omitted default"
        ):
            MODULE.cpp_runtime_probe_source(profile([
                ("float", "0.5"),
                ("Tensor", None),
            ]))

    def test_unsupported_type_is_rejected(self) -> None:
        with self.assertRaisesRegex(MODULE.BuildError, "unsupported arg_0: str"):
            MODULE.cpp_runtime_probe_source(profile([("str", None)]))


if __name__ == "__main__":
    unittest.main()
