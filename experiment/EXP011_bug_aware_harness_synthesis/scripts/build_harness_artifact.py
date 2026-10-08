#!/usr/bin/env python3
"""Deterministically materialize validated Strategy Plans as C++ Harness Artifacts."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import uuid
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


BUILDER_ID = "build_harness_artifact"
BUILDER_VERSION = "0.13.0"
ARTIFACT_SCHEMA_VERSION = "1.3"

EXP_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = EXP_ROOT.parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from template_contract import COMPATIBILITY_PATH, verify_template

DEFAULTS = {
    "strategy_schema": EXP_ROOT / "schemas" / "strategy_plan_record.schema.json",
    "catalog_schema": EXP_ROOT / "schemas" / "strategy_catalog_record.schema.json",
    "harness_spec_schema": EXP_ROOT / "schemas" / "harness_spec_record.schema.json",
    "api_profile_schema": EXP_ROOT / "schemas" / "api_profile_record.schema.json",
    "helper_profile_schema": EXP_ROOT / "schemas" / "helper_profile_record.schema.json",
    "artifact_schema": EXP_ROOT / "schemas" / "harness_artifact_record.schema.json",
    "evaluation_target_schema": (
        REPOSITORY_ROOT
        / "experiment"
        / "EXP014_experimental_evaluation"
        / "schemas"
        / "evaluation_target_manifest.schema.json"
    ),
    "catalog": EXP_ROOT / "strategy_primitives" / "strategy_primitive_catalog.json",
    "harness_specs": EXP_ROOT / "harness_specs",
    "api_profiles": EXP_ROOT / "api_profiles",
    "helper_profiles": EXP_ROOT / "helper_profiles",
    "template": EXP_ROOT / "templates" / "libfuzzer_harness_v1.cpp.in",
    "runtime_header": EXP_ROOT / "runtime" / "harness_instrumentation.h",
    "runtime_source": EXP_ROOT / "runtime" / "harness_instrumentation.cpp",
    "output_root": EXP_ROOT / "harnesses",
}

SLOT_ORDER = (
    "input_construction",
    "pre_call_transform",
    "pre_call_guard",
    "pre_call_observation",
    "target_call",
    "post_call_observation",
    "oracle_check",
    "artifact_logging",
    "cleanup",
)

EVENT_KINDS = {
    "branch_entered",
    "input_constructed",
    "input_rejected",
    "observation_captured",
    "activation_checked",
    "activation_true",
    "activation_unevaluable",
    "activation_check_error",
    "branch_activation_checked",
    "branch_activation_true",
    "branch_activation_unevaluable",
    "branch_activation_check_error",
    "target_api_reached",
    "target_api_completed",
    "target_api_exception",
    "oracle_evaluated",
    "oracle_passed",
    "oracle_failed",
}

TRACE_REF_TYPES = {
    "evaluation_target",
    "global_constraint",
    "branch_constraint",
    "target_condition",
    "behavior_observation",
    "behavior_check",
    "failure_handler",
}

RUNTIME_REFERENCE_PARAMETER_NAMES = {
    "subject_ref",
    "left_subject_ref",
    "right_subject_ref",
    "input_ref",
    "output_ref",
    "source_subject_ref",
    "target_subject_ref",
    "operand_ref",
    "result_ref",
    "value_ref",
}

# These IDs form part of the fixed template interface.
TEMPLATE_BUILTINS = {
    "data": ("Data", "raw_bytes"),
    "size": ("Size", "integer"),
    "offset": ("hbfg_offset", "byte_cursor"),
    "selector": ("hbfg_selector", "integer"),
    "none": ("c10::nullopt", "optional_value"),
}

INSERT_MARKERS = {
    "generated_includes": "/* HBFG_INSERT:generated_includes */",
    "generated_support_code": "/* HBFG_INSERT:generated_support_code */",
    "branch_dispatch": "/* HBFG_INSERT:branch_dispatch */",
}

VALUE_MARKERS = {
    "instrumentation_site_count":
        "/* HBFG_VALUE:instrumentation_site_count */",
    "artifact_id":
        "/* HBFG_VALUE:artifact_id */",
    "generation_key":
        "/* HBFG_VALUE:generation_key */",
}


class BuildError(RuntimeError):
    """Base error for one Harness generation operation."""


class InputError(BuildError):
    """An input record, reference, or source file is invalid."""


class MaterializationError(BuildError):
    """A Strategy Plan cannot be deterministically materialized."""


class CompileError(BuildError):
    """Compilation configuration is invalid."""


@dataclass(frozen=True)
class CompileConfiguration:
    command_argv: tuple[str, ...]
    timeout_seconds: int
    build_environment_ref: Mapping[str, Any]
    dependency_refs: tuple[Mapping[str, Any], ...] = ()
    environment_identity: str | None = None


@dataclass(frozen=True)
class BoundValue:
    cpp_expression: str
    value_kind: str


@dataclass(frozen=True)
class BoundParameter:
    binding_kind: str
    value: Any


@dataclass(frozen=True)
class TraceRef:
    ref_type: str
    ref_id: str


@dataclass(frozen=True)
class ObservationLocator:
    observation_role: str
    observation_point: str


@dataclass(frozen=True)
class EventAtom:
    event_kind: str
    key_suffix: str
    condition_expression: str | None = None
    trace_refs: tuple[TraceRef, ...] = ()
    observation_locator: ObservationLocator | None = None


CodeAtom = str | EventAtom


@dataclass(frozen=True)
class SupportBlock:
    support_id: str
    code: str


@dataclass(frozen=True)
class EmissionResult:
    atoms: tuple[CodeAtom, ...]
    outputs: Mapping[str, BoundValue]
    includes: tuple[str, ...] = ()
    support_blocks: tuple[SupportBlock, ...] = ()
    materialized_failure_handler_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class EmitterContext:
    branch_id: str
    step: Mapping[str, Any]
    primitive: Mapping[str, Any]
    inputs: Mapping[str, BoundValue]
    parameters: Mapping[str, BoundParameter]
    output_names: Mapping[str, str]
    spec_bindings: tuple[Mapping[str, Any], ...]
    failure_handlers: tuple[Mapping[str, Any], ...]
    strategy_branch: Mapping[str, Any]
    harness_spec: Mapping[str, Any]
    api_profile: Mapping[str, Any]
    helper_profile: Mapping[str, Any] | None


Emitter = Callable[[EmitterContext], EmissionResult]
EMITTERS: dict[str, Emitter] = {}


def register_emitter(emitter_id: str) -> Callable[[Emitter], Emitter]:
    """Register one trusted deterministic Emitter."""

    if not re.fullmatch(r"[a-z][a-z0-9_]*", emitter_id):
        raise ValueError(f"Invalid emitter_id: {emitter_id!r}")

    def decorator(function: Emitter) -> Emitter:
        if emitter_id in EMITTERS:
            raise ValueError(f"Duplicate emitter_id: {emitter_id}")
        EMITTERS[emitter_id] = function
        return function

    return decorator


def require_input(context: EmitterContext, port_id: str) -> BoundValue:
    value = context.inputs.get(port_id)
    if value is None:
        raise MaterializationError(
            f"Emitter {context.primitive['implementation_binding']['emitter_id']} "
            f"requires input port {port_id!r}"
        )
    return value


def parameter_value(
    context: EmitterContext,
    parameter_id: str,
    default: Any = None,
) -> Any:
    parameter = context.parameters.get(parameter_id)
    return default if parameter is None else parameter.value


def require_literal_parameter(
    context: EmitterContext,
    parameter_id: str,
    expected_type: type | tuple[type, ...],
) -> Any:
    value = parameter_value(context, parameter_id)
    if isinstance(value, BoundValue) or not isinstance(value, expected_type):
        raise MaterializationError(
            f"Emitter parameter {parameter_id!r} must resolve to a controlled "
            "literal or HarnessSpec value"
        )
    if isinstance(value, bool) and expected_type is not bool:
        raise MaterializationError(
            f"Emitter parameter {parameter_id!r} cannot be boolean"
        )
    return value


def one_spec_binding(
    context: EmitterContext,
    element_type: str,
) -> Mapping[str, Any]:
    matches = [
        binding
        for binding in context.spec_bindings
        if binding["spec_element_type"] == element_type
    ]
    if len(matches) != 1:
        raise MaterializationError(
            f"Step {context.step['step_id']} must bind exactly one "
            f"{element_type} for this Emitter"
        )
    return matches[0]


def harness_spec_branch(context: EmitterContext) -> Mapping[str, Any]:
    matches = [
        branch
        for branch in context.harness_spec["exploration_plan"]["branches"]
        if branch["branch_id"] == context.branch_id
    ]
    if len(matches) != 1:
        raise MaterializationError(
            f"HarnessSpec Branch {context.branch_id!r} does not resolve exactly once"
        )
    return matches[0]


def failure_handler(
    context: EmitterContext,
    outcome_id: str,
) -> Mapping[str, Any]:
    matches = [
        handler
        for handler in context.failure_handlers
        if handler["trigger"]["outcome_id"] == outcome_id
    ]
    if len(matches) != 1:
        raise MaterializationError(
            f"Step {context.step['step_id']} must materialize exactly one "
            f"handler for outcome {outcome_id!r}"
        )
    return matches[0]


def checked_axis(value: Any, parameter_id: str) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
        or value > 7
    ):
        raise MaterializationError(
            f"Emitter parameter {parameter_id!r} must be an integer in 0..7"
        )
    return value


def checked_shape(value: Any) -> list[int]:
    if (
        not isinstance(value, list)
        or not 0 <= len(value) <= 4
        or any(
            not isinstance(item, int)
            or isinstance(item, bool)
            or item < -1
            or item > 16
            for item in value
        )
    ):
        raise MaterializationError(
            "shape_template must contain 0..4 dimensions in -1..16"
        )
    return value


@register_emitter("emit_construct_tensor_from_fuzz")
def emit_construct_tensor_from_fuzz(
    context: EmitterContext,
) -> EmissionResult:
    data = require_input(context, "data").cpp_expression
    size = require_input(context, "size").cpp_expression
    cursor = require_input(context, "cursor").cpp_expression
    tensor_name = context.output_names["tensor"]
    cursor_name = context.output_names["next_cursor"]
    dtype_policy = require_literal_parameter(context, "dtype_policy", str)
    max_dimension = require_literal_parameter(context, "max_dimension", int)
    minimum_dimension = parameter_value(context, 'minimum_dimension', 0)
    if minimum_dimension not in {0, 1} or minimum_dimension > max_dimension:
        raise MaterializationError('minimum_dimension must be 0 or 1 and <= max_dimension')
    if dtype_policy not in {"float32", "int64", "bool"} or not 1 <= max_dimension <= 16:
        raise MaterializationError(
            "construct_tensor_from_fuzz supports float32/int64/bool and "
            "max_dimension in 1..16"
        )
    dtype_cpp = {
        "float32": "torch::kFloat32",
        "int64": "torch::kInt64",
        "bool": "torch::kBool",
    }[dtype_policy]

    handler = failure_handler(context, "insufficient_fuzz_data")
    handler_id = handler["failure_handler_id"]
    short_expression = f"({size} < {cursor} || {size} - {cursor} < 3U)"
    atoms: tuple[CodeAtom, ...] = (
        EventAtom(
            event_kind="input_rejected",
            key_suffix=f"{context.step['step_id']}_short",
            condition_expression=short_expression,
            trace_refs=(TraceRef("failure_handler", handler_id),),
        ),
        f"if ({short_expression}) {{ return 0; }}",
        f"std::size_t {cursor_name} = {cursor};",
        (
            f"const std::int64_t {tensor_name}_rows = "
            f"{minimum_dimension} + static_cast<std::int64_t>({data}[{cursor_name}++] % {max_dimension - minimum_dimension + 1}U);"
        ),
        (
            f"const std::int64_t {tensor_name}_cols = "
            f"{minimum_dimension} + static_cast<std::int64_t>({data}[{cursor_name}++] % {max_dimension - minimum_dimension + 1}U);"
        ),
        (
            f"const std::int64_t {tensor_name}_fill = "
            f"static_cast<std::int64_t>({data}[{cursor_name}++] % 17U) - 8;"
        ),
        (
            f"auto {tensor_name} = torch::full({{{tensor_name}_rows, "
            f"{tensor_name}_cols}}, {tensor_name}_fill, "
            f"torch::TensorOptions().dtype({dtype_cpp}).device(torch::kCPU));"
        ),
        EventAtom(
            event_kind="input_constructed",
            key_suffix=context.step["step_id"],
        ),
    )
    return EmissionResult(
        atoms=atoms,
        outputs={
            "tensor": BoundValue(tensor_name, "tensor"),
            "next_cursor": BoundValue(cursor_name, "byte_cursor"),
        },
        includes=("<cstdint>",),
        materialized_failure_handler_ids=(handler_id,),
    )


@register_emitter("emit_construct_tensor_with_constraints")
def emit_construct_tensor_with_constraints(
    context: EmitterContext,
) -> EmissionResult:
    data = require_input(context, "data").cpp_expression
    size = require_input(context, "size").cpp_expression
    cursor = require_input(context, "cursor").cpp_expression
    tensor_name = context.output_names["tensor"]
    cursor_name = context.output_names["next_cursor"]
    shape = checked_shape(
        require_literal_parameter(context, "shape_template", list)
    )
    dtype_policy = require_literal_parameter(context, "dtype_policy", str)
    fill_policy = require_literal_parameter(context, "fill_policy", str)
    max_dimension = require_literal_parameter(context, "max_dimension", int)
    if dtype_policy not in {"float32", "int64", "bool"} or fill_policy not in {"zero", "fuzz_numeric", "fuzz_sign"}:
        raise MaterializationError(
            "Constrained tensor construction supports float32/int64/bool with "
            "zero, fuzz_numeric, or fuzz_sign fill"
        )
    if not 1 <= max_dimension <= 16:
        raise MaterializationError("max_dimension must be in 1..16")
    minimum_dimension = parameter_value(context, 'minimum_dimension', 0)
    if minimum_dimension not in {0, 1} or minimum_dimension > max_dimension:
        raise MaterializationError('minimum_dimension must be 0 or 1 and <= max_dimension')

    atoms: list[CodeAtom] = [f"std::size_t {cursor_name} = {cursor};"]
    dimension_expressions: list[str] = []
    for index, dimension in enumerate(shape):
        if dimension != -1:
            dimension_expressions.append(str(dimension))
            continue
        dimension_name = f"{tensor_name}_dim_{index}"
        atoms.append(
            f"const std::int64_t {dimension_name} = "
            f"({cursor_name} < {size}) ? "
            f"{minimum_dimension} + static_cast<std::int64_t>({data}[{cursor_name}++] % "
            f"{max_dimension - minimum_dimension + 1}U) : {minimum_dimension};"
        )
        dimension_expressions.append(dimension_name)

    fill_expression = "0"
    if fill_policy == "fuzz_numeric":
        fill_expression = (
            f"(({cursor_name} < {size}) ? "
            f"static_cast<std::int64_t>({data}[{cursor_name}++] % 17U) - 8 : 0)"
        )
    elif fill_policy == "fuzz_sign":
        fill_expression = (
            f"(({cursor_name} < {size}) ? "
            f"(({data}[{cursor_name}++] & 1U) ? 1 : -1) : 1)"
        )
    shape_expression = ", ".join(dimension_expressions)
    dtype_cpp = {
        "float32": "torch::kFloat32",
        "int64": "torch::kInt64",
        "bool": "torch::kBool",
    }[dtype_policy]
    atoms.extend(
        [
            (
                f"auto {tensor_name} = torch::full({{{shape_expression}}}, "
                f"{fill_expression}, "
                f"torch::TensorOptions().dtype({dtype_cpp}).device(torch::kCPU));"
            ),
            EventAtom(
                event_kind="input_constructed",
                key_suffix=context.step["step_id"],
            ),
        ]
    )
    return EmissionResult(
        atoms=tuple(atoms),
        outputs={
            "tensor": BoundValue(tensor_name, "tensor"),
            "next_cursor": BoundValue(cursor_name, "byte_cursor"),
        },
        includes=("<cstdint>",),
    )


@register_emitter("emit_construct_tensor_with_rank_range")
def emit_construct_tensor_with_rank_range(context: EmitterContext) -> EmissionResult:
    data = require_input(context, 'data').cpp_expression
    size = require_input(context, 'size').cpp_expression
    cursor = require_input(context, 'cursor').cpp_expression
    tensor = context.output_names['tensor']
    next_cursor = context.output_names['next_cursor']
    low = require_literal_parameter(context, 'minimum_rank', int)
    high = require_literal_parameter(context, 'maximum_rank', int)
    minimum = parameter_value(context, 'minimum_dimension', 0)
    maximum = require_literal_parameter(context, 'max_dimension', int)
    dtype = require_literal_parameter(context, 'dtype_policy', str)
    fill = require_literal_parameter(context, 'fill_policy', str)
    if not 0 <= low <= high <= 4 or minimum not in {0, 1} or not minimum <= maximum <= 16 or maximum < 1:
        raise MaterializationError('Rank range must be in 0..4; dimension bounds must follow the resource policy')
    if dtype not in {'float32', 'int64', 'bool'} or fill not in {'zero', 'fuzz_numeric', 'fuzz_sign'}:
        raise MaterializationError('Unsupported rank-range dtype/fill policy')
    dtype_cpp = {'float32': 'torch::kFloat32', 'int64': 'torch::kInt64', 'bool': 'torch::kBool'}[dtype]
    atoms: list[CodeAtom] = [
        f'std::size_t {next_cursor} = {cursor};',
        f'const std::int64_t {tensor}_rank = ({next_cursor} < {size}) ? {low} + static_cast<std::int64_t>({data}[{next_cursor}++] % {high-low+1}U) : {low};',
        f'std::vector<std::int64_t> {tensor}_shape;',
        f'for (std::int64_t axis = 0; axis < {tensor}_rank; ++axis) {{',
        f'  {tensor}_shape.push_back(({next_cursor} < {size}) ? {minimum} + static_cast<std::int64_t>({data}[{next_cursor}++] % {maximum-minimum+1}U) : {minimum});',
        '}',
    ]
    fill_expression = '0'
    if fill == 'fuzz_numeric':
        fill_expression = f'(({next_cursor} < {size}) ? static_cast<std::int64_t>({data}[{next_cursor}++] % 17U) - 8 : 0)'
    elif fill == 'fuzz_sign':
        fill_expression = f'(({next_cursor} < {size}) ? (({data}[{next_cursor}++] & 1U) ? 1 : -1) : 1)'
    atoms.extend((f'auto {tensor} = torch::full({tensor}_shape, {fill_expression}, torch::TensorOptions().dtype({dtype_cpp}).device(torch::kCPU));',
                  EventAtom('input_constructed', context.step['step_id'])))
    return EmissionResult(atoms=tuple(atoms), outputs={'tensor': BoundValue(tensor, 'tensor'),
        'next_cursor': BoundValue(next_cursor, 'byte_cursor')}, includes=('<cstdint>', '<vector>'))


@register_emitter("emit_construct_tensor_from_reference")
def emit_construct_tensor_from_reference(context: EmitterContext) -> EmissionResult:
    reference = require_input(context, "reference").cpp_expression
    data = require_input(context, "data").cpp_expression
    size = require_input(context, "size").cpp_expression
    cursor = require_input(context, "cursor").cpp_expression
    tensor_name = context.output_names["tensor"]
    cursor_name = context.output_names["next_cursor"]
    shape_policy = require_literal_parameter(context, "shape_policy", str)
    dtype_policy = require_literal_parameter(context, "dtype_policy", str)
    fill_policy = require_literal_parameter(context, "fill_policy", str)
    if shape_policy not in {"same_shape", "leading_dimension", "selected_dimension", "drop_last_dimension"}:
        raise MaterializationError("Unsupported reference shape policy")
    if dtype_policy not in {"float32", "int64", "bool"}:
        raise MaterializationError("Unsupported reference-derived dtype")
    if fill_policy not in {"zero", "fuzz_numeric", "fuzz_sign"}:
        raise MaterializationError("Unsupported reference-derived fill policy")
    dtype_cpp = {
        "float32": "torch::kFloat32",
        "int64": "torch::kInt64",
        "bool": "torch::kBool",
    }[dtype_policy]
    reference_axis = checked_axis(parameter_value(context, 'reference_axis', 0), 'reference_axis') if shape_policy == 'selected_dimension' else 0
    shape_expression = (
        f"{reference}.sizes().vec()"
        if shape_policy == "same_shape"
        else f"std::vector<std::int64_t>{{{reference}.dim() > {reference_axis} ? {reference}.size({reference_axis}) : 0}}"
    )
    atoms: list[CodeAtom] = [f"std::size_t {cursor_name} = {cursor};"]
    if shape_policy == 'drop_last_dimension':
        atoms.extend((f'auto {tensor_name}_shape = {reference}.sizes().vec();',
                      f'if (!{tensor_name}_shape.empty()) {{ {tensor_name}_shape.pop_back(); }}'))
        shape_expression = f'{tensor_name}_shape'
    fill_expression = "0"
    if fill_policy == "fuzz_numeric":
        fill_expression = (
            f"(({cursor_name} < {size}) ? "
            f"static_cast<std::int64_t>({data}[{cursor_name}++] % 17U) - 8 : 0)"
        )
    elif fill_policy == "fuzz_sign":
        fill_expression = (
            f"(({cursor_name} < {size}) ? "
            f"(({data}[{cursor_name}++] & 1U) ? 1 : -1) : 1)"
        )
    atoms.extend((
        f"auto {tensor_name} = torch::full({shape_expression}, {fill_expression}, "
        f"torch::TensorOptions().dtype({dtype_cpp}).device(torch::kCPU));",
        EventAtom("input_constructed", context.step["step_id"]),
    ))
    return EmissionResult(
        atoms=tuple(atoms),
        outputs={
            "tensor": BoundValue(tensor_name, "tensor"),
            "next_cursor": BoundValue(cursor_name, "byte_cursor"),
        },
        includes=("<cstdint>", "<vector>"),
    )


@register_emitter("emit_construct_scalar_from_fuzz")
def emit_construct_scalar_from_fuzz(context: EmitterContext) -> EmissionResult:
    data = require_input(context, "data").cpp_expression
    size = require_input(context, "size").cpp_expression
    cursor = require_input(context, "cursor").cpp_expression
    value_name = context.output_names["value"]
    cursor_name = context.output_names["next_cursor"]
    handler = failure_handler(context, "insufficient_fuzz_data")
    handler_id = handler["failure_handler_id"]
    primitive_id = context.primitive["primitive_id"]
    byte_count = 1
    if primitive_id == "construct_integer_from_fuzz":
        minimum, maximum = parameter_value(context, "minimum"), parameter_value(context, "maximum")
        if (not isinstance(minimum, int) or isinstance(minimum, bool)
                or not isinstance(maximum, int) or isinstance(maximum, bool)
                or not -(2**63) <= minimum <= maximum <= 2**63 - 1):
            raise MaterializationError('Integer bounds must fit signed int64')
        byte_count = max(1, ((maximum - minimum).bit_length() + 7) // 8)
    short_expression = f"({size} < {cursor} || {size} - {cursor} < {byte_count}U)"
    atoms: list[CodeAtom] = [
        EventAtom(
            event_kind="input_rejected",
            key_suffix=f"{context.step['step_id']}_short",
            condition_expression=short_expression,
            trace_refs=(TraceRef("failure_handler", handler_id),),
        ),
        f"if ({short_expression}) {{ return 0; }}",
        f"std::size_t {cursor_name} = {cursor};",
    ]
    if primitive_id == "construct_boolean_from_fuzz":
        atoms.append(
            f"const bool {value_name} = ({data}[{cursor_name}++] & 1U) != 0U;"
        )
        value_kind = "boolean"
    else:
        minimum = parameter_value(context, "minimum")
        maximum = parameter_value(context, "maximum")
        if not isinstance(minimum, (int, float)) or isinstance(minimum, bool):
            raise MaterializationError("Scalar minimum must be numeric")
        if not isinstance(maximum, (int, float)) or isinstance(maximum, bool) or maximum < minimum:
            raise MaterializationError("Scalar maximum must be numeric and >= minimum")
        try:
            finite = math.isfinite(minimum) and math.isfinite(maximum)
        except OverflowError:
            finite = False
        if not finite:
            raise MaterializationError('Scalar bounds must be finite')
        if primitive_id == "construct_integer_from_fuzz":
            if not isinstance(minimum, int) or not isinstance(maximum, int):
                raise MaterializationError("Integer scalar bounds must be integers")
            if not -(2**63) <= minimum <= maximum <= 2**63 - 1:
                raise MaterializationError('Integer bounds must fit signed int64')
            width = maximum - minimum + 1
            byte_count = max(1, ((width - 1).bit_length() + 7) // 8)
            atoms.extend([
                f'std::uint64_t {value_name}_bits = 0;',
                f'for (unsigned i = 0; i < {byte_count}U; ++i) {{ {value_name}_bits |= static_cast<std::uint64_t>({data}[{cursor_name}++]) << (8U * i); }}',
            ])
            offset = f'{value_name}_bits' if width == 2**64 else f'({value_name}_bits % {width}ULL)'
            minimum_cpp = '(-9223372036854775807LL - 1LL)' if minimum == -(2**63) else f'{minimum}LL'
            atoms.append(f'const std::int64_t {value_name} = static_cast<std::int64_t>(static_cast<__int128>({minimum_cpp}) + static_cast<__int128>({offset}));')
            value_kind = "integer"
        elif primitive_id == "construct_floating_from_fuzz":
            atoms.extend((
                f'const double {value_name}_position = static_cast<double>({data}[{cursor_name}++]) / 255.0;',
                f'const double {value_name} = (1.0 - {value_name}_position) * {float(minimum)!r} + {value_name}_position * {float(maximum)!r};',
            ))
            value_kind = "floating"
        else:
            raise MaterializationError(
                f"Unsupported scalar constructor: {primitive_id}"
            )
    atoms.append(EventAtom("input_constructed", context.step["step_id"]))
    return EmissionResult(
        atoms=tuple(atoms),
        outputs={
            "value": BoundValue(value_name, value_kind),
            "next_cursor": BoundValue(cursor_name, "byte_cursor"),
        },
        includes=("<cstdint>",),
        materialized_failure_handler_ids=(handler_id,),
    )


@register_emitter('emit_select_optional_tensor_from_fuzz')
def emit_select_optional_tensor_from_fuzz(context: EmitterContext) -> EmissionResult:
    tensor = require_input(context, 'tensor').cpp_expression
    data = require_input(context, 'data').cpp_expression
    size = require_input(context, 'size').cpp_expression
    cursor = require_input(context, 'cursor').cpp_expression
    name = context.output_names['optional_value']
    next_cursor = context.output_names['next_cursor']
    return EmissionResult(atoms=(
        f'std::size_t {next_cursor} = {cursor};',
        f'std::optional<at::Tensor> {name};',
        f'if ({next_cursor} < {size} && ({data}[{next_cursor}++] & 1U)) {{ {name} = {tensor}; }}',
    ), outputs={'optional_value': BoundValue(name, 'optional_value'),
                'next_cursor': BoundValue(next_cursor, 'byte_cursor')}, includes=('<optional>',))


@register_emitter("emit_enforce_dimension_relation")
def emit_enforce_dimension_relation(
    context: EmitterContext,
) -> EmissionResult:
    left = require_input(context, "left").cpp_expression
    right = require_input(context, "right").cpp_expression
    left_axis = checked_axis(
        require_literal_parameter(context, "left_axis", int),
        "left_axis",
    )
    right_axis = checked_axis(
        require_literal_parameter(context, "right_axis", int),
        "right_axis",
    )
    relation_kind = require_literal_parameter(context, "relation_kind", str)
    if relation_kind != "equal":
        raise MaterializationError("Only the equal dimension relation is supported")
    output_name = context.output_names["relation_satisfied"]
    condition = (
        f"({left}.dim() > {left_axis} && {right}.dim() > {right_axis} && "
        f"{left}.size({left_axis}) == {right}.size({right_axis}))"
    )
    handler = failure_handler(context, "relation_unsatisfied")
    handler_id = handler["failure_handler_id"]
    return EmissionResult(
        atoms=(
            f"const bool {output_name} = {condition};",
            EventAtom(
                event_kind="input_rejected",
                key_suffix=f"{context.step['step_id']}_relation",
                condition_expression=f"!{output_name}",
                trace_refs=(TraceRef("failure_handler", handler_id),),
            ),
            f"if (!{output_name}) {{ return 0; }}",
        ),
        outputs={
            "relation_satisfied": BoundValue(output_name, "boolean"),
        },
        materialized_failure_handler_ids=(handler_id,),
    )


def activation_context(
    context: EmitterContext,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    activation_binding = one_spec_binding(context, "activation_target")
    branch = harness_spec_branch(context)
    activation_id = activation_binding["spec_element_id"]
    activations = [
        item
        for item in branch["activation_targets"]
        if item["activation_target_id"] == activation_id
    ]
    if len(activations) != 1:
        raise MaterializationError(
            "Activation Target binding does not resolve exactly once"
        )
    property_id = activations[0]["target_property_id"]
    properties = [
        item
        for item in branch["target_properties"]
        if item["target_property_id"] == property_id
    ]
    if len(properties) != 1:
        raise MaterializationError(
            "Activation Target does not resolve one Target Property"
        )
    return activations[0], properties[0]


def branch_activation_atoms(context: EmitterContext) -> tuple[EventAtom, ...]:
    """Emit one joint Branch Activation quartet after its last target check."""

    spec_branch = harness_spec_branch(context)
    activations = spec_branch["activation_targets"]
    if not activations:
        return ()

    steps = context.strategy_branch["steps"]
    step_by_id = {step["step_id"]: step for step in steps}
    activation_step_ids: list[str] = []
    condition_names: list[str] = []

    for activation in activations:
        activation_id = activation["activation_target_id"]
        bindings = [
            binding
            for binding in context.strategy_branch["spec_bindings"]
            if binding["spec_element_type"] == "activation_target"
            and binding["spec_element_id"] == activation_id
        ]
        if len(bindings) != 1 or len(bindings[0]["implementation_step_ids"]) != 1:
            raise MaterializationError(
                "Each Activation Target must resolve to exactly one observation Step"
            )
        step_id = bindings[0]["implementation_step_ids"][0]
        step = step_by_id.get(step_id)
        if step is None or step["primitive_id"] != "evaluate_tensor_property":
            raise MaterializationError(
                "Joint Branch Activation v1 requires tensor-property observation Steps"
            )
        outputs = [
            output
            for output in step["output_bindings"]
            if output["port_id"] == "property_holds"
        ]
        if len(outputs) != 1:
            raise MaterializationError(
                "Each Activation observation Step must expose property_holds once"
            )
        activation_step_ids.append(step_id)
        condition_names.append(
            f"hbfg_{safe_component(context.branch_id)}_{outputs[0]['value_id']}"
        )

    activation_step_set = set(activation_step_ids)
    ordered_activation_steps = [
        step["step_id"]
        for step in steps
        if step["step_id"] in activation_step_set
    ]
    if context.step["step_id"] != ordered_activation_steps[-1]:
        return ()

    target_properties = {
        item["target_property_id"]: item
        for item in spec_branch["target_properties"]
    }
    refs: list[TraceRef] = []
    for activation in activations:
        property_id = activation["target_property_id"]
        if property_id not in target_properties:
            raise MaterializationError(
                "Branch Activation references an unknown Target Property"
            )
        refs.extend(
            (
                TraceRef("activation_target", activation["activation_target_id"]),
                TraceRef("target_property", property_id),
            )
        )

    joint_condition = "(" + " && ".join(condition_names) + ")"
    branch_refs = tuple(refs)
    return (
        EventAtom(
            "branch_activation_checked",
            context.branch_id,
            trace_refs=branch_refs,
        ),
        EventAtom(
            "branch_activation_true",
            context.branch_id,
            condition_expression=joint_condition,
            trace_refs=branch_refs,
        ),
        EventAtom(
            "branch_activation_unevaluable",
            context.branch_id,
            condition_expression="false",
            trace_refs=branch_refs,
        ),
        EventAtom(
            "branch_activation_check_error",
            context.branch_id,
            condition_expression="false",
            trace_refs=branch_refs,
        ),
    )


@register_emitter("emit_evaluate_tensor_property")
def emit_evaluate_tensor_property(
    context: EmitterContext,
) -> EmissionResult:
    subject = require_input(context, "subject").cpp_expression
    property_kind = require_literal_parameter(context, "property_kind", str)
    axis = checked_axis(parameter_value(context, "axis", 0), "axis")
    expected_integer = require_literal_parameter(
        context, "expected_integer", int
    )
    output_name = context.output_names["property_holds"]
    expressions = {
        "dtype_is_int64": f"({subject}.scalar_type() == torch::kInt64)",
        "rank_equals": f"({subject}.dim() == {expected_integer})",
        "dimension_size_equals": (
            f"({subject}.dim() > {axis} && "
            f"{subject}.size({axis}) == {expected_integer})"
        ),
        "numel_equals_zero": f"({subject}.numel() == 0)",
        "is_contiguous": f"{subject}.is_contiguous()",
        "is_non_contiguous": f"!{subject}.is_contiguous()",
    }
    if property_kind not in expressions:
        raise MaterializationError(
            f"Unsupported tensor property kind: {property_kind!r}"
        )

    condition_binding = one_spec_binding(context, "target_condition")
    branch = harness_spec_branch(context)
    condition_id = condition_binding["spec_element_id"]
    conditions = [
        item for item in branch["target_conditions"]
        if item["condition_id"] == condition_id
    ]
    if len(conditions) != 1:
        raise MaterializationError(
            "Target Condition binding does not resolve exactly once"
        )
    condition = conditions[0]
    observation_points = condition["observe_at"]
    point = ('before_target_api_call' if context.step['template_slot'] == 'pre_call_observation' else 'after_target_api_call')
    if point not in observation_points:
        raise MaterializationError('Tensor-property Step phase is not declared')
    expected_slot = (
        "pre_call_observation"
        if point == "before_target_api_call"
        else "post_call_observation"
    )
    if context.step["template_slot"] != expected_slot:
        raise MaterializationError(
            "Observation Step slot does not match the HarnessSpec Observation Point"
        )

    refs = (TraceRef("target_condition", condition_id),)
    return EmissionResult(
        atoms=(
            f"const bool {output_name} = {expressions[property_kind]};",
            EventAtom(
                event_kind="observation_captured",
                key_suffix=f'{condition_id}_{context.step["step_id"]}',
                trace_refs=refs,
                observation_locator=ObservationLocator(
                    "before" if point == "before_target_api_call" else "after",
                    point,
                ),
            ),
            EventAtom("activation_checked", f'{condition_id}_{context.step["step_id"]}', trace_refs=refs),
            EventAtom(
                "activation_true",
                f'{condition_id}_{context.step["step_id"]}',
                condition_expression=output_name,
                trace_refs=refs,
            ),
            EventAtom(
                "activation_unevaluable",
                f'{condition_id}_{context.step["step_id"]}',
                condition_expression="false",
                trace_refs=refs,
            ),
            EventAtom(
                "activation_check_error",
                f'{condition_id}_{context.step["step_id"]}',
                condition_expression="false",
                trace_refs=refs,
            ),
        ),
        outputs={
            "property_holds": BoundValue(output_name, "boolean"),
        },
    )


@register_emitter("emit_evaluate_tensor_relation")
def emit_evaluate_tensor_relation(context: EmitterContext) -> EmissionResult:
    left = require_input(context, "left").cpp_expression
    right = require_input(context, "right").cpp_expression
    property_kind = require_literal_parameter(context, "property_kind", str)
    relation_kind = require_literal_parameter(context, "relation_kind", str)
    if property_kind not in {"shape", "rank", "numel"}:
        raise MaterializationError("Unsupported tensor relation property")
    if relation_kind not in {"equals", "not_equals"}:
        raise MaterializationError("Unsupported tensor relation kind")
    equality = {
        "shape": f"({left}.sizes().equals({right}.sizes()))",
        "rank": f"({left}.dim() == {right}.dim())",
        "numel": f"({left}.numel() == {right}.numel())",
    }[property_kind]
    expression = equality if relation_kind == "equals" else f"!{equality}"
    output_name = context.output_names["relation_holds"]
    condition_binding = one_spec_binding(context, "target_condition")
    condition_id = condition_binding["spec_element_id"]
    refs = (TraceRef("target_condition", condition_id),)
    event_suffix = f'{condition_id}_{context.step["step_id"]}'
    point = (
        "before_target_api_call"
        if context.step["template_slot"] == "pre_call_observation"
        else "after_target_api_call"
    )
    return EmissionResult(
        atoms=(
            f"const bool {output_name} = {expression};",
            EventAtom(
                "observation_captured",
                event_suffix,
                trace_refs=refs,
                observation_locator=ObservationLocator(
                    "before" if point == "before_target_api_call" else "after",
                    point,
                ),
            ),
            EventAtom('activation_checked', event_suffix, trace_refs=refs),
            EventAtom(
                'activation_true', event_suffix,
                condition_expression=output_name, trace_refs=refs,
            ),
            EventAtom(
                'activation_unevaluable', event_suffix,
                condition_expression="false", trace_refs=refs,
            ),
            EventAtom(
                'activation_check_error', event_suffix,
                condition_expression="false", trace_refs=refs,
            ),
        ),
        outputs={"relation_holds": BoundValue(output_name, "boolean")},
    )


def resolved_target_output_contract(
    api_profile: Mapping[str, Any],
) -> list[dict[str, Any]]:
    mappings = api_profile['target_binding']['return_mapping']
    if any(m['mapping_kind'] == 'omitted' for m in mappings) and any(m['mapping_kind'] != 'omitted' for m in mappings):
        raise MaterializationError('Partial return omission needs an explicit tuple-position adapter')
    returns = {
        item["return_id"]: item
        for item in api_profile["python_contract"]["returns"]
    }
    ports: list[dict[str, Any]] = []
    seen: set[str] = set()
    for mapping in sorted(
        api_profile["target_binding"]["return_mapping"],
        key=lambda item: item["binding_return_position"],
    ):
        mapping_kind = mapping["mapping_kind"]
        if mapping_kind == "omitted":
            continue
        if mapping_kind != 'direct':
            raise MaterializationError(
                f"Unsupported target return mapping kind: {mapping_kind!r}"
            )
        return_id = mapping["python_return_ref"]
        if return_id is None or return_id not in returns or return_id in seen:
            raise MaterializationError(
                "Target return mapping does not resolve uniquely"
            )
        result = returns[return_id]
        normalized = set(result.get("normalized_types", []))
        role = result.get("semantic_role")
        if "tensor_sequence" in normalized or role == "result_tensor_sequence":
            value_kind = "tensor_list"
        elif (
            {"tensor", "index_tensor"}.intersection(normalized)
            or role == "result_tensor"
        ):
            value_kind = "tensor"
        elif "boolean" in normalized or role == "boolean_result":
            value_kind = "boolean"
        elif (
            {"integer", "index"}.intersection(normalized)
            or role == "index_result"
        ):
            value_kind = "integer"
        elif "shape" in normalized or role == "shape_result":
            value_kind = "shape"
        elif (
            {"scalar", "number", "floating"}.intersection(normalized)
            or role == "scalar_result"
        ):
            value_kind = "scalar"
        elif len(normalized) > 1 or role == "object_result":
            value_kind = "tuple_value"
        else:
            raise MaterializationError(
                f"Cannot resolve target return kind for {return_id!r}"
            )
        seen.add(return_id)
        ports.append(
            {
                "port_id": return_id,
                "produced_value_kind": value_kind,
                "binding_required": True,
            }
        )
    return ports


def api_schema_type_to_kinds(schema_type: str) -> list[str]:
    compact = re.sub(r"\s+", "", schema_type).lower()
    optional = compact.endswith("?") or "optional" in compact
    compact = compact.rstrip("?")
    if "tensor[]" in compact or "tensorlist" in compact:
        base = "tensor_list"
    elif "tensor" in compact:
        base = "tensor"
    elif "scalartype" in compact or "dtype" in compact:
        base = "dtype"
    elif (
        "int[]" in compact
        or "symint[]" in compact
        or "intarrayref" in compact
    ):
        base = "shape"
    elif "device" in compact:
        base = "device"
    elif "bool" in compact:
        base = "boolean"
    elif "float" in compact or "double" in compact:
        base = "floating"
    elif "symint" in compact or "int" in compact or "long" in compact:
        base = "integer"
    elif "scalar" in compact or "number" in compact:
        base = "scalar"
    elif "str" in compact or "string" in compact:
        base = "string"
    else:
        raise MaterializationError(
            f"Unsupported API binding schema type: {schema_type!r}"
        )
    return [base, "optional_value"] if optional else [base]


def resolve_materialization_primitive(
    primitive: Mapping[str, Any],
    api_profile: Mapping[str, Any],
) -> Mapping[str, Any]:
    if primitive["primitive_kind"] != "target_api_invoke":
        return primitive
    resolved = copy.deepcopy(primitive)
    resolved["input_contract"] = [
        {
            "port_id": parameter["binding_parameter_id"],
            "accepted_value_kinds": api_schema_type_to_kinds(
                parameter["schema_type"]
            ),
            "required": parameter["default"] is None,
        }
        for parameter in sorted(
            api_profile["target_binding"]["binding_parameters"],
            key=lambda item: item["ordinal"],
        )
    ]
    resolved["output_contract"] = resolved_target_output_contract(api_profile)
    return resolved


@register_emitter("emit_profiled_target_api")
def emit_profiled_target_api(context: EmitterContext) -> EmissionResult:
    binding = context.api_profile["target_binding"]
    callable_name = binding["cpp_callable"]
    if not isinstance(callable_name, str) or not re.fullmatch(
        r"at::[A-Za-z_][A-Za-z0-9_]*", callable_name
    ):
        raise MaterializationError("API Profile cpp_callable is unsupported")

    parameters = sorted(
        binding["binding_parameters"],
        key=lambda item: item["ordinal"],
    )
    arguments: list[str] = []
    omitted_default = False
    for parameter in parameters:
        port_id = parameter["binding_parameter_id"]
        value = context.inputs.get(port_id)
        if value is None:
            if parameter["default"] is None:
                raise MaterializationError(
                    f"Target API Step misses required argument {port_id!r}"
                )
            omitted_default = True
            continue
        if omitted_default:
            raise MaterializationError(
                "Target API Step cannot bind an argument after omitting a default"
            )
        arguments.append(value.cpp_expression)

    output_ports = [
        item["port_id"] for item in context.primitive["output_contract"]
    ]
    output_names = [context.output_names[port_id] for port_id in output_ports]
    invocation = f"{callable_name}({', '.join(arguments)})"
    temporary = 'hbfg_call_result_' + context.step['step_id']
    declaration = () if not output_ports else (f'std::optional<decltype({invocation})> {temporary};',)
    if not output_ports:
        call_atom = f"{invocation};"
    elif len(output_ports) == 1:
        call_atom = f"auto {output_names[0]} = std::move(*{temporary});"
    else:
        call_atom = f"auto [{', '.join(output_names)}] = std::move(*{temporary});"
    output_kinds = {
        item["port_id"]: item["produced_value_kind"]
        for item in context.primitive["output_contract"]
    }
    return EmissionResult(
        atoms=(
            EventAtom("target_api_reached", context.step["step_id"]),
            *declaration,
            'try {',
            f'{temporary}.emplace({invocation});' if output_ports else call_atom,
            '} catch (const c10::Error& hbfg_error) {',
            EventAtom('target_api_exception', context.step['step_id']),
            'hbfg_iteration.log_target_api_exception(hbfg_error.what_without_backtrace());',
            'return 0;',
            '}',
            EventAtom("target_api_completed", context.step["step_id"]),
            *((call_atom,) if output_ports else ()),
        ),
        outputs={
            port_id: BoundValue(context.output_names[port_id], output_kinds[port_id])
            for port_id in output_ports
        },
        includes=('<optional>', '<utility>', '<cstdio>', '<c10/util/Exception.h>'),
    )


@register_emitter("emit_execution_survival_oracle")
def emit_execution_survival_oracle(
    context: EmitterContext,
) -> EmissionResult:
    """Record no-crash only after control returns from the target API call."""

    binding = one_spec_binding(context, "behavior_check")
    oracle_id = binding["spec_element_id"]
    branch = harness_spec_branch(context)
    matches = [
        check
        for check in branch["behavior_checks"]
        if check["check_id"] == oracle_id
    ]
    if len(matches) != 1:
        raise MaterializationError(
            "Execution-survival Behavior Check binding does not resolve exactly once"
        )
    oracle = matches[0]
    if (
        oracle["expected_predicate"]["predicate_id"] != "execution_survives"
        or oracle["subject_refs"] != ["context.execution"]
    ):
        raise MaterializationError(
            "Execution-survival Emitter supports execution_survives over "
            "context.execution"
        )

    output_name = context.output_names["oracle_holds"]
    refs = (TraceRef("behavior_check", oracle_id),)
    return EmissionResult(
        atoms=(
            f"const bool {output_name} = true;",
            EventAtom("oracle_evaluated", oracle_id, trace_refs=refs),
            EventAtom(
                "oracle_passed",
                oracle_id,
                condition_expression=output_name,
                trace_refs=refs,
            ),
            EventAtom(
                "oracle_failed",
                oracle_id,
                condition_expression="false",
                trace_refs=refs,
            ),
        ),
        outputs={
            "oracle_holds": BoundValue(output_name, "boolean"),
        },
    )


@register_emitter("emit_evaluate_output_property")
def emit_evaluate_output_property(
    context: EmitterContext,
) -> EmissionResult:
    result = require_input(context, "result").cpp_expression
    check_kind = require_literal_parameter(context, "check_kind", str)
    expected_integer = require_literal_parameter(
        context, "expected_integer", int
    )
    expected_shape = parameter_value(context, "expected_shape", [])
    output_name = context.output_names["oracle_holds"]
    if check_kind == "all_zero":
        expression = f"torch::all({result} == 0).item<bool>()"
    elif check_kind == "numel_equals":
        expression = f"({result}.numel() == {expected_integer})"
    elif check_kind == "rank_equals":
        expression = f"({result}.dim() == {expected_integer})"
    elif check_kind == "dtype_is_int64":
        expression = f"({result}.scalar_type() == torch::kInt64)"
    elif check_kind == "shape_equals":
        shape = checked_shape(expected_shape)
        comparisons = [
            f"{result}.size({index}) == {dimension}"
            for index, dimension in enumerate(shape)
        ]
        expression = (
            f"({result}.dim() == {len(shape)}"
            + (' && ' + ' && '.join(comparisons) if comparisons else '')
            + ")"
        )
    else:
        raise MaterializationError(
            f"Unsupported output-property Oracle: {check_kind!r}"
        )

    oracle_binding = one_spec_binding(context, "behavior_check")
    oracle_id = oracle_binding["spec_element_id"]
    checks = [check for check in harness_spec_branch(context)['behavior_checks'] if check['check_id'] == oracle_id]
    if len(checks) != 1:
        raise MaterializationError('Output check binding does not resolve exactly once')
    required = checks[0]['requirement_level'] == 'required'
    refs = (TraceRef("behavior_check", oracle_id),)
    return EmissionResult(
        atoms=(
            f"const bool {output_name} = {expression};",
            EventAtom("oracle_evaluated", oracle_id, trace_refs=refs),
            EventAtom(
                "oracle_passed",
                oracle_id,
                condition_expression=output_name,
                trace_refs=refs,
            ),
            EventAtom(
                "oracle_failed",
                oracle_id,
                condition_expression=f"!{output_name}",
                trace_refs=refs,
            ),
            *((f'if (!{output_name}) {{ std::abort(); }}',) if required else ()),
        ),
        outputs={
            "oracle_holds": BoundValue(output_name, "boolean"),
        },
        includes=("<cstdlib>",),
    )


@register_emitter("emit_evaluate_tensor_determinism")
def emit_evaluate_tensor_determinism(
    context: EmitterContext,
) -> EmissionResult:
    first = require_input(context, "first_result").cpp_expression
    second = require_input(context, "second_result").cpp_expression
    output_name = context.output_names["oracle_holds"]
    oracle_binding = one_spec_binding(context, "behavior_check")
    oracle_id = oracle_binding["spec_element_id"]
    refs = (TraceRef("behavior_check", oracle_id),)
    return EmissionResult(
        atoms=(
            f"const bool {output_name} = torch::equal({first}, {second});",
            EventAtom("oracle_evaluated", oracle_id, trace_refs=refs),
            EventAtom(
                "oracle_passed",
                oracle_id,
                condition_expression=output_name,
                trace_refs=refs,
            ),
            EventAtom(
                "oracle_failed",
                oracle_id,
                condition_expression=f"!{output_name}",
                trace_refs=refs,
            ),
            f"if (!{output_name}) {{ std::abort(); }}",
        ),
        outputs={
            "oracle_holds": BoundValue(output_name, "boolean"),
        },
        includes=("<cstdlib>",),
    )


@dataclass
class MaterializationState:
    includes: set[str]
    support_blocks: dict[str, str]
    materialization_map: list[dict[str, Any]]
    instrumentation_map: list[dict[str, Any]]
    segment_blocks: dict[str, list[str]]


@dataclass(frozen=True)
class ResolvedInputs:
    strategy: Mapping[str, Any]
    harness_spec: Mapping[str, Any]
    catalog: Mapping[str, Any]
    api_profile: Mapping[str, Any]
    helper_profiles: Mapping[tuple[str, int, str], Mapping[str, Any]]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def profile_content_hash(record: Mapping[str, Any]) -> str:
    copied = copy.deepcopy(record)
    copied["metadata"].pop("content_hash", None)
    return canonical_hash(copied)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise InputError(f"File does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise InputError(
            f"Invalid JSON in {path}: line {exc.lineno}, column {exc.colno}"
        ) from exc


def load_validator(path: Path) -> Draft202012Validator:
    schema = load_json(path)
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        raise InputError(f"Invalid JSON Schema {path}: {exc}") from exc
    core = load_json(EXP_ROOT / 'schemas/harness_spec_record_core__v2_2.schema.json')
    registry = Registry().with_resource(core['$id'], Resource.from_contents(core))
    return Draft202012Validator(
        schema,
        registry=registry,
        format_checker=FormatChecker(),
    )


def validate_record(
    record: Any,
    validator: Draft202012Validator,
    label: str,
) -> None:
    errors = sorted(
        validator.iter_errors(record),
        key=lambda item: list(item.absolute_path),
    )
    if not errors:
        return

    details = []
    for error in errors[:20]:
        location = ".".join(str(item) for item in error.absolute_path)
        details.append(f"{location or '<root>'}: {error.message}")

    raise InputError(f"{label} failed Schema validation: {'; '.join(details)}")


def safe_component(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")
    if not normalized:
        raise InputError(f"Cannot derive a path component from {value!r}")
    if not normalized[0].isalpha():
        normalized = f"x_{normalized}"
    return normalized


def repository_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPOSITORY_ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise InputError(f"Path is outside the repository: {path}") from exc


def file_reference(
    content_path: Path,
    reference_path: Path | None = None,
) -> dict[str, str]:
    return {
        "relative_path": repository_relative(reference_path or content_path),
        "content_hash": file_hash(content_path),
    }


def evaluation_targets_for_api(
    manifest: Mapping[str, Any] | None,
    api_id: str,
) -> tuple[Mapping[str, Any], ...]:
    if manifest is None:
        return ()
    if manifest.get("unresolved_bindings") not in (None, []):
        raise InputError("Evaluation Target Manifest has unresolved bindings")
    sets = manifest.get("api_target_sets")
    if not isinstance(sets, list):
        raise InputError("Evaluation Target Manifest api_target_sets is invalid")
    matches = [item for item in sets if item.get("api_id") == api_id]
    if len(matches) != 1:
        raise InputError(
            f"Evaluation Target Manifest must contain exactly one API set for {api_id}"
        )
    targets = matches[0].get("targets")
    if not isinstance(targets, list) or not targets:
        raise InputError(f"Evaluation Target set for {api_id} is empty")
    seen: set[str] = set()
    for target in targets:
        target_id = target.get("evaluation_target_id")
        if not isinstance(target_id, str) or not target_id or target_id in seen:
            raise InputError(f"Evaluation Target IDs are invalid or duplicated for {api_id}")
        seen.add(target_id)
        detector = target.get("detector_id")
        if detector not in {"matmul_empty_inner_long_pair_v1", "tensor_empty_v1", "tensor_shape_mismatch_v1", "tensor_pair_empty_v1"}:
            raise InputError(
                f"Unsupported Evaluation Target detector: {target.get('detector_id')!r}"
            )
        roles = {
            item.get("parameter_role")
            for item in target.get("parameter_bindings", [])
        }
        required_roles = {"subject"} if detector == "tensor_empty_v1" else {"left", "right"}
        if roles != required_roles or len(target.get("parameter_bindings", [])) != len(required_roles):
            raise InputError(
                f"Detector parameter bindings do not match {required_roles}: {target_id}"
            )
        for source in target.get("source_knowledge_refs", []):
            file_ref = source.get("file_ref", {})
            path = REPOSITORY_ROOT / file_ref.get("relative_path", "")
            if not path.is_file() or file_hash(path) != file_ref.get("content_hash"):
                raise InputError(f"Evaluation Target source hash is invalid: {path}")
    return tuple(targets)


def profile_key(reference: Mapping[str, Any]) -> tuple[str, int, str]:
    try:
        profile_id = reference["profile_id"]
        revision = reference["revision"]
        content_hash = reference["content_hash"]
    except (KeyError, TypeError) as exc:
        raise InputError(f"Malformed Profile Reference: {reference!r}") from exc

    if not isinstance(profile_id, str) or not profile_id:
        raise InputError("Profile Reference has an invalid profile_id")
    if not isinstance(revision, int) or revision < 1:
        raise InputError("Profile Reference has an invalid revision")
    if not re.fullmatch(r"[0-9a-f]{64}", content_hash):
        raise InputError("Profile Reference has an invalid content_hash")

    return profile_id, revision, content_hash


def load_profile_store(
    root: Path,
    validator: Draft202012Validator,
    label: str,
    wanted_refs: Sequence[Mapping[str, Any]] | None = None,
) -> dict[tuple[str, int, str], dict[str, Any]]:
    if not root.is_dir():
        raise InputError(f"{label} directory does not exist: {root}")

    store: dict[tuple[str, int, str], dict[str, Any]] = {}
    revision_keys: set[tuple[str, int]] = set()
    wanted = None if wanted_refs is None else {profile_key(ref) for ref in wanted_refs}

    filename_pattern = {
        "API Profile": "api_profile__*__r*.json",
        "Helper Profile": "helper_profile__*__r*.json",
    }.get(label, "*.json")
    paths = sorted(
        path
        for path in root.rglob(filename_pattern)
        if path.is_file()
        and "_runs" not in path.parts
        and "legacy" not in path.parts
    )
    for path in paths:
        try:
            record = load_json(path)
            key = (record["profile_id"], record["revision"], record["metadata"]["content_hash"])
        except (BuildError, KeyError, TypeError):
            if wanted is not None:
                # A malformed requested record will be reported as unavailable;
                # unrelated records must not block this task.
                continue
            raise
        if wanted is not None and key not in wanted:
            continue
        validate_record(record, validator, f"{label} {path}")
        if key[2] != profile_content_hash(record):
            raise InputError(
                f"{label} has a non-reproducible metadata.content_hash: {path}"
            )

        revision_key = key[:2]
        if revision_key in revision_keys:
            raise InputError(
                f"Duplicate {label} revision: {revision_key}"
            )
        if key in store:
            raise InputError(f"Duplicate exact {label} reference: {key}")

        revision_keys.add(revision_key)
        store[key] = record

    return store


def load_harness_spec_store(
    root: Path,
    validator: Draft202012Validator,
    wanted_refs: Sequence[Mapping[str, Any]] | None = None,
) -> dict[tuple[str, int, str], dict[str, Any]]:
    if not root.is_dir():
        raise InputError(f"HarnessSpec directory does not exist: {root}")

    store: dict[tuple[str, int, str], dict[str, Any]] = {}

    paths = sorted(root.rglob('hs_*_r*.json')) if wanted_refs is None else sorted({
        path for ref in wanted_refs
        for path in root.rglob(f'{ref["spec_id"]}_r{ref["revision_number"]}.json')
        if 'legacy' not in path.parts
    })
    wanted = None if wanted_refs is None else {(r['spec_id'], r['revision_number'], r['content_hash']) for r in wanted_refs}
    for path in paths:
        record = load_json(path)
        if not isinstance(record, dict) or 'identity' not in record or 'revision_information' not in record:
            continue

        key = (
            record["identity"]["spec_id"],
            record["revision_information"]["revision_number"],
            canonical_hash(record),
        )
        if wanted is not None and key not in wanted:
            continue
        validate_record(record, validator, f'HarnessSpec {path}')
        if key in store:
            raise InputError(f"Duplicate exact HarnessSpec reference: {key}")
        store[key] = record

    return store

def approved_strategy_review(path: Path | None, strategy_path: Path, strategy: dict[str, Any]) -> dict[str, Any]:
    if path is None:
        raise InputError('Artifact requires --strategy-review: exact approved external Strategy review')
    review = load_json(path)
    if review.get('record_type') == 'budget_derivation_certificate':
        from budget_derivation import validate
        try:
            validate(review, path, strategy_path, 'strategy')
        except (ValueError, KeyError) as exc:
            raise InputError(str(exc)) from exc
        return {'artifact_id': path.name, 'artifact_version': review['schema_version'],
                'content_hash': file_hash(path), 'relative_path': repository_relative(path)}
    validator = load_validator(EXP_ROOT / 'schemas/strategy_plan_review_record.schema.json')
    validate_record(review, validator, 'Strategy review')
    if file_hash(Path(review['rules_ref']['relative_path'])) != review['rules_ref']['content_hash']:
        raise InputError('Strategy review Rules hash mismatch')
    subject = review['subject']
    if (review['decision'] != 'approved' or subject['strategy_id'] != strategy['identity']['strategy_id']
        or subject['revision_number'] != strategy['revision_information']['revision_number']
        or subject['content_hash'] != canonical_hash(strategy)
        or Path(subject['relative_path']).resolve() != strategy_path.resolve()):
        raise InputError('Strategy review approval/subject does not match exactly')
    return {'artifact_id': path.name, 'artifact_version': review['schema_version'],
            'content_hash': file_hash(path), 'relative_path': repository_relative(path)}

def revalidate_strategy(resolved: ResolvedInputs) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import build_strategy_plan_json as builder
    try:
        candidate = builder.ResolvedInputs(spec=resolved.harness_spec, api=resolved.api_profile,
            resolved_api_primitive=builder.resolve_api_primitive(resolved.catalog, resolved.api_profile),
            candidate_primitives=list(resolved.catalog['primitives']),
            harness_spec_review_ref=resolved.strategy['source_context']['harness_spec_review_ref'])
        builder.capability_preflight(candidate, resolved.catalog)
        builder.validate_materialized_plan(resolved.strategy['implementation_plan'], candidate, resolved.catalog)
        hs_review_ref = resolved.strategy['source_context']['harness_spec_review_ref']
        hs_review = load_json(Path(hs_review_ref['relative_path']))
        derived = hs_review.get('record_type') == 'budget_derivation_certificate'
        if derived:
            from budget_derivation import validate
            validate(hs_review, Path(hs_review_ref['relative_path']), Path(hs_review['subject']['relative_path']), 'spec')
        else:
            validate_record(hs_review, load_validator(EXP_ROOT / 'schemas/harness_spec_review_record.schema.json'), 'HarnessSpec review')
        hs_ref = resolved.strategy['source_context']['harness_spec_ref']
        if (canonical_hash(hs_review) != hs_review_ref['content_hash'] or (not derived and hs_review['decision'] != 'approved')
                or any(hs_review['subject'][k] != hs_ref[k] for k in ('spec_id', 'revision_number', 'content_hash'))):
            raise InputError('HarnessSpec review does not match the exact approved subject')
        if resolved.strategy.get('schema_version') == '1.3':
            for key in ('resource_policy_ref', 'ordinary_recipes_ref', 'generation_trace_ref'):
                ref = resolved.strategy['source_context'].get(key)
                if ref is None or not Path(ref['relative_path']).is_file() or file_hash(Path(ref['relative_path'])) != ref['content_hash']:
                    raise InputError(f'Exact Strategy source artifact is unavailable: {key}')
            if resolved.strategy['source_context']['resource_policy_ref']['content_hash'] != builder.file_hash(builder.RESOURCE_POLICY_PATH):
                raise InputError('Strategy uses a different resource policy')
            if resolved.strategy['source_context']['ordinary_recipes_ref']['content_hash'] != builder.file_hash(builder.ORDINARY_RECIPES_PATH):
                raise InputError('Strategy uses different ordinary recipes')
            trace_ref = resolved.strategy['source_context']['generation_trace_ref']
            trace = load_json(Path(trace_ref['relative_path']))
            if resolved.strategy['identity']['spec_mode'] != 'controlled_baseline' and not derived:
                frozen = trace.get('frozen_inputs', {}).get('views', {}).get('canonical_default_strategy_view')
                if not isinstance(frozen, dict):
                    raise InputError('Bug-aware Strategy lacks its frozen canonical default branch')
                defaults = [branch for branch in resolved.strategy['implementation_plan']['branch_strategies']
                            if branch['source_branch_id'] == frozen.get('source_branch_id')]
                actual = copy.deepcopy(defaults[0]) if len(defaults) == 1 else None
                if actual is not None:
                    actual.pop('failure_handlers', None)
                if actual != frozen:
                    raise InputError('Bug-aware default branch differs from its frozen canonical Strategy')
    except builder.BuildError as exc:
        raise InputError(f'Strategy semantic revalidation: {exc}') from exc


def api_profile_is_usable(profile: Mapping[str, Any]) -> bool:
    return (
        profile["target_binding"]["status"] == "resolved"
        and profile["validation"]["validation_status"] == "passed"
        and profile["validation"]["execution_readiness"] == "ready"
        and profile["review"]["review_status"] == "approved"
    )


def helper_profile_is_usable(profile: Mapping[str, Any]) -> bool:
    return (
        profile["validation"]["execution_readiness"] == "ready"
        and profile["review"]["review_status"] == "approved"
    )


def resolve_inputs(
    strategy: Mapping[str, Any],
    catalog: Mapping[str, Any],
    spec_store: Mapping[tuple[str, int, str], Mapping[str, Any]],
    api_store: Mapping[tuple[str, int, str], Mapping[str, Any]],
    helper_store: Mapping[tuple[str, int, str], Mapping[str, Any]],
    template_path: Path,
) -> ResolvedInputs:
    if strategy["review"]["validation_status"] != "passed":
        raise InputError("Strategy Plan validation_status is not passed")

    expected_catalog_ref = {
        "catalog_id": catalog["catalog_id"],
        "catalog_version": catalog["catalog_version"],
        "content_hash": canonical_hash(catalog),
    }
    if strategy["source_context"]["strategy_catalog_ref"] != expected_catalog_ref:
        raise InputError("Strategy Plan does not reference the loaded Catalog")

    template_ref = catalog["template_interface"]["template_ref"]
    try:
        verify_template(template_path, template_ref["content_hash"])
    except ValueError as exc:
        raise InputError(str(exc)) from exc

    spec_ref = strategy["source_context"]["harness_spec_ref"]
    spec_key = (
        spec_ref["spec_id"],
        spec_ref["revision_number"],
        spec_ref["content_hash"],
    )
    harness_spec = spec_store.get(spec_key)
    if harness_spec is None:
        raise InputError(f"Exact HarnessSpec is unavailable: {spec_key}")

    strategy_identity = strategy["identity"]
    spec_identity = harness_spec["identity"]

    for field in ("framework", "target_api", "spec_mode"):
        if strategy_identity[field] != spec_identity[field]:
            raise InputError(
                f"Strategy and HarnessSpec disagree on identity.{field}"
            )

    if harness_spec["review"]["validation_status"] != "passed":
        raise InputError("HarnessSpec validation_status is not passed")

    if harness_spec["revision_information"]["lifecycle_status"] not in {
        "draft",
        "active",
    }:
        raise InputError("HarnessSpec lifecycle status is not usable")

    api_ref = harness_spec["target_context"]["api_profile_ref"]
    api_profile = api_store.get(profile_key(api_ref))
    if api_profile is None:
        raise InputError("Exact API Profile is unavailable")
    if not api_profile_is_usable(api_profile):
        raise InputError("API Profile is not resolved, ready, and approved")

    target = api_profile["target"]
    if (
        target["framework"] != strategy_identity["framework"]
        or target["python_api"] != strategy_identity["target_api"]
    ):
        raise InputError("API Profile target conflicts with Strategy identity")

    available_helpers: dict[
        tuple[str, int, str],
        Mapping[str, Any],
    ] = {}

    used_helpers = used_helper_keys(strategy, catalog)
    for reference in harness_spec["target_context"][
        "available_helper_profile_refs"
    ]:
        key = profile_key(reference)
        helper = helper_store.get(key)
        if helper is None:
            raise InputError(f"Exact Helper Profile is unavailable: {key}")
        if key in used_helpers and not helper_profile_is_usable(helper):
            raise InputError(
                f"Helper Profile is not ready and approved: {key[0]}"
            )
        available_helpers[key] = helper
    if not used_helpers.issubset(available_helpers):
        raise InputError('Selected Primitive requires a Helper outside the frozen available pool')

    expected_builtins = {
        value_id: value_kind
        for value_id, (_, value_kind) in TEMPLATE_BUILTINS.items()
    }
    actual_builtins = {
        item["value_id"]: item["value_kind"]
        for item in catalog["template_interface"]["built_in_values"]
    }
    if actual_builtins != expected_builtins:
        raise InputError(
            "Catalog built_in_values do not match the fixed template interface"
        )

    spec_branch_ids = [
        branch["branch_id"]
        for branch in harness_spec["exploration_plan"]["branches"]
    ]
    strategy_branch_ids = [
        branch["source_branch_id"]
        for branch in strategy["implementation_plan"]["branch_strategies"]
    ]
    if strategy_branch_ids != spec_branch_ids:
        raise InputError(
            "Strategy Branch order does not match the HarnessSpec Branch order"
        )

    return ResolvedInputs(
        strategy=strategy,
        harness_spec=harness_spec,
        catalog=catalog,
        api_profile=api_profile,
        helper_profiles=available_helpers,
    )


def strategy_reference(strategy: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "strategy_id": strategy["identity"]["strategy_id"],
        "revision_number": strategy["revision_information"]["revision_number"],
        "content_hash": canonical_hash(strategy),
    }


def used_helper_keys(strategy: Mapping[str, Any], catalog: Mapping[str, Any]) -> set[tuple[str, int, str]]:
    primitives = {item['primitive_id']: item for item in catalog['primitives']}
    result = set()
    for branch in strategy['implementation_plan']['branch_strategies']:
        for step in branch['steps']:
            primitive = primitives.get(step['primitive_id'])
            if primitive is None:
                raise InputError(f"Unknown Primitive: {step['primitive_id']}")
            ref = primitive['implementation_binding'].get('helper_profile_ref')
            if ref is not None:
                result.add(profile_key(ref))
    return result


def generator_components(
    template: Path,
    runtime_header: Path,
    runtime_source: Path,
    evaluation_target_manifest: Path | None = None,
) -> tuple[dict[str, str], list[dict[str, str]]]:
    entrypoint = file_reference(Path(__file__).resolve())

    components = [
        file_reference(template),
        file_reference(COMPATIBILITY_PATH),
        file_reference(EXP_ROOT / 'scripts/template_contract.py'),
        file_reference(runtime_header),
        file_reference(runtime_source),
        file_reference(EXP_ROOT / 'scripts/build_strategy_plan_json.py'),
        file_reference(EXP_ROOT / 'scripts/strategy_domains.py'),
        file_reference(EXP_ROOT / 'strategy_primitives/strategy_resource_policy__v001.json'),
        file_reference(EXP_ROOT / 'strategy_primitives/ordinary_input_recipes__v001.json'),
        file_reference(DEFAULTS['artifact_schema']),
    ]
    if evaluation_target_manifest is not None:
        components.append(file_reference(evaluation_target_manifest))
    components.sort(key=lambda item: item["relative_path"])

    return entrypoint, components


def generation_key(
    strategy_ref: Mapping[str, Any],
    entrypoint_ref: Mapping[str, Any],
    component_refs: Sequence[Mapping[str, Any]],
) -> str:
    payload = {
        "strategy_revision_ref": strategy_ref,
        "generator_id": BUILDER_ID,
        "generator_version": BUILDER_VERSION,
        "entrypoint_ref": entrypoint_ref,
        "component_refs": list(component_refs),
    }
    return canonical_hash(payload)


def build_request(config: CompileConfiguration | None, review_ref: Mapping[str, Any] | None) -> dict[str, Any]:
    return {
        'compile_profile_ref': None if config is None else dict(config.build_environment_ref),
        'dependency_refs': [] if config is None else [dict(ref) for ref in config.dependency_refs],
        'environment_identity': None if config is None else config.environment_identity,
        'strategy_review_ref': review_ref,
    }


def build_generation_key(source_key: str, request: Mapping[str, Any]) -> str:
    build_identity = {
        key: request[key]
        for key in ('compile_profile_ref', 'dependency_refs', 'environment_identity')
    }
    return canonical_hash({
        'source_generation_key': source_key,
        'build_request': build_identity,
    })


def harness_artifact_id(
    strategy: Mapping[str, Any],
    key: str,
) -> str:
    strategy_id = strategy["identity"]["strategy_id"]
    revision = strategy["revision_information"]["revision_number"]
    return f"ha_{strategy_id}_r{revision}_{key[:12]}"


def allocate_selector_ranges(
    branches: Sequence[Mapping[str, Any]],
) -> dict[str, tuple[int, int]]:
    if len(branches) > 256:
        raise MaterializationError(
            "More than 256 positive-budget Branches cannot be selected "
            "with one selector byte"
        )

    weights = [Decimal(str(branch["budget_share"])) for branch in branches]
    if any(weight <= 0 for weight in weights):
        raise MaterializationError("Every Branch budget_share must be positive")

    total = sum(weights)
    quotas = [weight * Decimal(256) / total for weight in weights]
    allocations = [
        max(1, int(quota.to_integral_value(rounding=ROUND_FLOOR)))
        for quota in quotas
    ]

    while sum(allocations) > 256:
        candidates = [
            index
            for index, allocation in enumerate(allocations)
            if allocation > 1
        ]
        if not candidates:
            raise MaterializationError(
                "Cannot satisfy the one-selector-per-Branch requirement"
            )

        index = min(
            candidates,
            key=lambda item: (
                -(Decimal(allocations[item]) - quotas[item]),
                branches[item]["branch_id"],
            ),
        )
        allocations[index] -= 1

    while sum(allocations) < 256:
        index = min(
            range(len(branches)),
            key=lambda item: (
                -(quotas[item] - Decimal(allocations[item])),
                branches[item]["branch_id"],
            ),
        )
        allocations[index] += 1

    ranges: dict[str, tuple[int, int]] = {}
    start = 0

    for branch, allocation in zip(branches, allocations):
        end = start + allocation - 1
        ranges[branch["branch_id"]] = (start, end)
        start = end + 1

    if start != 256:
        raise MaterializationError("Selector allocation does not cover 0..255")

    return ranges


def primitive_map(catalog: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}

    for primitive in catalog["primitives"]:
        primitive_id = primitive["primitive_id"]
        if primitive_id in result:
            raise InputError(f"Duplicate Catalog Primitive: {primitive_id}")
        result[primitive_id] = primitive

    return result


def is_runtime_reference_parameter(name: str) -> bool:
    return (
        name in RUNTIME_REFERENCE_PARAMETER_NAMES
        or name.endswith("_subject_ref")
        or name.endswith("_value_ref")
    )


def resolve_spec_parameter(
    harness_spec: Mapping[str, Any],
    branch_id: str,
    reference: Mapping[str, Any],
) -> Any:
    branch = next(
        (
            item
            for item in harness_spec["exploration_plan"]["branches"]
            if item["branch_id"] == branch_id
        ),
        None,
    )
    if branch is None:
        raise MaterializationError(f"Unknown HarnessSpec Branch: {branch_id}")

    element_type = reference["spec_element_type"]
    element_id = reference["spec_element_id"]
    parameter_name = reference["parameter_name"]
    groups = {
        "global_constraint": (
            harness_spec["validity_constraints"]["global_constraints"],
            "constraint_id",
        ),
        "branch_constraint": (branch["branch_constraints"], "constraint_id"),
        "target_condition": (branch["target_conditions"], "condition_id"),
        "behavior_check": (branch["behavior_checks"], "check_id"),
    }
    if element_type not in groups:
        raise MaterializationError(
            f"Unsupported HarnessSpec parameter source: {element_type}"
        )
    if is_runtime_reference_parameter(parameter_name):
        raise MaterializationError(
            f"Runtime reference {parameter_name} must use a value_ref binding"
        )

    elements, id_field = groups[element_type]
    matches = [item for item in elements if item[id_field] == element_id]
    if len(matches) != 1:
        raise MaterializationError(
            "HarnessSpec parameter source does not resolve exactly once: "
            f"{branch_id}/{element_type}/{element_id}"
        )

    element = matches[0]
    if element_type == "behavior_check":
        requirements = [
            *element["preconditions"],
            element["expected_predicate"],
        ]
    else:
        requirements = [element["predicate"]]

    values = [
        requirement["arguments"][parameter_name]
        for requirement in requirements
        if parameter_name in requirement.get("arguments", {})
    ]
    if not values:
        raise MaterializationError(
            "HarnessSpec parameter is not exposed by its source element: "
            f"{branch_id}/{element_type}/{element_id}/{parameter_name}"
        )
    if any(value != values[0] for value in values[1:]):
        raise MaterializationError(
            "HarnessSpec parameter has conflicting values: "
            f"{branch_id}/{element_type}/{element_id}/{parameter_name}"
        )
    return copy.deepcopy(values[0])


def resolve_parameter_bindings(
    branch_id: str,
    step: Mapping[str, Any],
    values: Mapping[str, BoundValue],
    harness_spec: Mapping[str, Any],
) -> dict[str, BoundParameter]:
    result: dict[str, BoundParameter] = {}

    for binding in step["parameter_bindings"]:
        parameter_id = binding["parameter_id"]
        kind = binding["binding_kind"]
        raw_value = binding["binding_value"]

        if kind == "literal":
            value = raw_value
        elif kind == "value_ref":
            if raw_value not in values:
                raise MaterializationError(
                    f"Step {step['step_id']} references unavailable "
                    f"parameter value {raw_value}"
                )
            value = values[raw_value]
        elif kind == "spec_parameter":
            value = resolve_spec_parameter(
                harness_spec,
                branch_id,
                raw_value,
            )
        else:
            raise MaterializationError(
                f"Unsupported parameter binding kind: {kind}"
            )

        result[parameter_id] = BoundParameter(
            binding_kind=kind,
            value=value,
        )

    return result


def resolve_helper_profile(
    primitive: Mapping[str, Any],
    helpers: Mapping[tuple[str, int, str], Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    reference = primitive["implementation_binding"]["helper_profile_ref"]
    if reference is None:
        return None

    helper = helpers.get(profile_key(reference))
    if helper is None:
        raise MaterializationError(
            f"Primitive {primitive['primitive_id']} references an unavailable "
            "Helper Profile"
        )
    return helper


def validate_include(include: str) -> None:
    if not re.fullmatch(r'(?:<[^<>\r\n]+>|"[^"\r\n]+")', include):
        raise MaterializationError(f"Invalid generated include: {include!r}")


def validate_emission(
    step: Mapping[str, Any],
    primitive: Mapping[str, Any],
    emission: EmissionResult,
    expected_handler_ids: Sequence[str],
) -> None:
    if not isinstance(emission, EmissionResult):
        raise MaterializationError(
            f"Emitter for Step {step['step_id']} returned an invalid result"
        )

    if not emission.atoms:
        raise MaterializationError(
            f"Emitter for Step {step['step_id']} returned no code"
        )

    for include in emission.includes:
        validate_include(include)

    support_ids: set[str] = set()
    for block in emission.support_blocks:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", block.support_id):
            raise MaterializationError(
                f"Invalid support_id: {block.support_id!r}"
            )
        if not block.code.strip():
            raise MaterializationError(
                f"Support Block {block.support_id} is empty"
            )
        if block.support_id in support_ids:
            raise MaterializationError(
                f"Duplicate Support Block: {block.support_id}"
            )
        support_ids.add(block.support_id)

    bound_output_ports = {
        item["port_id"]
        for item in step["output_bindings"]
    }
    if set(emission.outputs) != bound_output_ports:
        raise MaterializationError(
            f"Emitter outputs do not match Step {step['step_id']} "
            "output bindings"
        )

    output_contract = {
        item["port_id"]: item
        for item in primitive["output_contract"]
    }
    for port_id, value in emission.outputs.items():
        if not isinstance(value, BoundValue):
            raise MaterializationError(
                f"Emitter output {port_id} is not a BoundValue"
            )
        if not value.cpp_expression.strip():
            raise MaterializationError(
                f"Emitter output {port_id} has an empty C++ expression"
            )
        expected_kind = output_contract[port_id]["produced_value_kind"]
        if value.value_kind != expected_kind:
            raise MaterializationError(
                f"Emitter output {port_id} has kind {value.value_kind}, "
                f"expected {expected_kind}"
            )

    actual_handlers = list(emission.materialized_failure_handler_ids)
    if len(actual_handlers) != len(set(actual_handlers)):
        raise MaterializationError(
            f"Emitter for Step {step['step_id']} repeats a Failure Handler"
        )
    if set(actual_handlers) != set(expected_handler_ids):
        raise MaterializationError(
            f"Emitter for Step {step['step_id']} did not materialize exactly "
            "its assigned Failure Handlers"
        )
    event_handlers = {
        ref.ref_id for atom in emission.atoms if isinstance(atom, EventAtom)
        and atom.event_kind == 'input_rejected' for ref in atom.trace_refs
        if ref.ref_type == 'failure_handler'
    }
    if event_handlers != set(expected_handler_ids):
        raise MaterializationError(f"Step {step['step_id']} failure paths lack exact input_rejected events")


def normalized_trace_refs(
    trace_refs: Sequence[TraceRef],
) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for reference in trace_refs:
        if reference.ref_type not in TRACE_REF_TYPES:
            raise MaterializationError(
                f"Unknown trace ref type: {reference.ref_type}"
            )
        if not reference.ref_id:
            raise MaterializationError("Trace reference has an empty ref_id")

        key = (reference.ref_type, reference.ref_id)
        if key in seen:
            raise MaterializationError(f"Duplicate trace reference: {key}")

        seen.add(key)
        normalized.append(
            {
                "ref_type": reference.ref_type,
                "ref_id": reference.ref_id,
            }
        )

    normalized.sort(key=lambda item: (item["ref_type"], item["ref_id"]))
    return normalized


def validate_event_semantics(
    event: EventAtom,
    trace_refs: Sequence[Mapping[str, str]],
) -> None:
    if event.event_kind not in EVENT_KINDS:
        raise MaterializationError(
            f"Unknown instrumentation event kind: {event.event_kind}"
        )
    if not event.key_suffix:
        raise MaterializationError("Instrumentation event has no key suffix")

    ref_types = {item["ref_type"] for item in trace_refs}

    if event.event_kind == "observation_captured":
        if event.observation_locator is None:
            raise MaterializationError(
                "observation_captured requires an Observation Locator"
            )
        if "target_condition" not in ref_types and "evaluation_target" not in ref_types:
            raise MaterializationError(
                "observation_captured requires a Target Condition or "
                "Evaluation Target reference"
            )
    elif event.observation_locator is not None:
        raise MaterializationError(
            "Observation Locator is allowed only for observation_captured"
        )

    if event.event_kind in {
        "activation_checked",
        "activation_true",
        "activation_unevaluable",
        "activation_check_error",
    }:
        evaluation_ref_count = sum(
            item["ref_type"] == "evaluation_target" for item in trace_refs
        )
        condition_ref_count = sum(
            item["ref_type"] == "target_condition" for item in trace_refs
        )
        if evaluation_ref_count not in {0, 1}:
            raise MaterializationError(
                f"{event.event_kind} resolves more than one Evaluation Target"
            )
        if condition_ref_count not in {0, 1}:
            raise MaterializationError(
                f"{event.event_kind} resolves more than one Target Condition"
            )

    if event.event_kind in {
        "branch_activation_checked",
        "branch_activation_true",
        "branch_activation_unevaluable",
        "branch_activation_check_error",
    }:
        if "target_condition" not in ref_types:
            raise MaterializationError(
                f"{event.event_kind} requires Target Condition references"
            )

    if event.event_kind.startswith("oracle_"):
        if "behavior_check" not in ref_types:
            raise MaterializationError(
                f"{event.event_kind} requires a Behavior Check reference"
            )

    if event.event_kind == "input_rejected":
        if "failure_handler" not in ref_types:
            raise MaterializationError(
                "input_rejected requires a Failure Handler reference"
            )

    condition_events = {
        "activation_true",
        "branch_activation_true",
        "oracle_passed",
        "oracle_failed",
    }
    if (
        event.event_kind in condition_events
        and not event.condition_expression
    ):
        raise MaterializationError(
            f"{event.event_kind} requires a condition expression"
        )


def add_event(
    state: MaterializationState,
    branch_id: str,
    event: EventAtom,
    source_owner: Mapping[str, str],
) -> str:
    trace_refs = normalized_trace_refs(event.trace_refs)
    validate_event_semantics(event, trace_refs)

    site_id = len(state.instrumentation_map)
    binding_id = f"ins_{site_id + 1:04d}"
    event_key = f"{branch_id}:{event.event_kind}:{event.key_suffix}"

    if any(
        item["event_key"] == event_key
        for item in state.instrumentation_map
    ):
        raise MaterializationError(
            f"Duplicate instrumentation event_key: {event_key}"
        )

    entry: dict[str, Any] = {
        "instrumentation_binding_id": binding_id,
        "runtime_site_id": site_id,
        "event_kind": event.event_kind,
        "event_key": event_key,
        "branch_id": branch_id,
        "trace_refs": trace_refs,
        "source_owner": dict(source_owner),
        "source_span": {
            "start_line": 1,
            "end_line": 1,
        },
    }

    if event.observation_locator is not None:
        entry["observation_locator"] = {
            "observation_role":
                event.observation_locator.observation_role,
            "observation_point":
                event.observation_locator.observation_point,
        }

    state.instrumentation_map.append(entry)

    capture = ""
    if event.event_kind == "oracle_failed":
        capture = (f' if ({event.condition_expression}) {{ '
                   f'hbfg_iteration.capture_anomaly("oracle_failure", "{event.key_suffix}"); }}')

    if event.condition_expression is None:
        statement = f"hbfg_iteration.record({site_id});"
    else:
        statement = (
            f"hbfg_iteration.record_if({site_id}, "
            f"static_cast<bool>({event.condition_expression}));"
        )

    return f"{statement}{capture}  // HBFG_EVENT:{binding_id}"


def add_support_blocks(
    state: MaterializationState,
    blocks: Sequence[SupportBlock],
) -> None:
    for block in blocks:
        previous = state.support_blocks.get(block.support_id)
        if previous is not None and previous != block.code:
            raise MaterializationError(
                f"Support Block {block.support_id} has conflicting definitions"
            )
        state.support_blocks[block.support_id] = block.code


def indent_lines(lines: Sequence[str], spaces: int) -> list[str]:
    prefix = " " * spaces
    return [
        f"{prefix}{line}" if line else ""
        for line in lines
    ]


def evaluation_target_atoms(
    target: Mapping[str, Any],
    branch_id: str,
    inputs: Mapping[str, BoundValue],
) -> tuple[CodeAtom, ...]:
    bindings = {
        item["parameter_role"]: item["binding_parameter_id"]
        for item in target["parameter_bindings"]
    }
    left = inputs.get(bindings.get("left", bindings.get("subject")))
    right = inputs.get(bindings.get("right")) if "right" in bindings else left
    if (
        left is None
        or right is None
        or left.value_kind != "tensor"
        or right.value_kind != "tensor"
    ):
        raise MaterializationError(
            f"Evaluation Target {target['evaluation_target_id']} "
            "cannot resolve tensor inputs"
        )
    target_id = target["evaluation_target_id"]
    name = f"hbfg_{safe_component(branch_id)}_{safe_component(target_id)}"
    left_expr = left.cpp_expression
    right_expr = right.cpp_expression
    condition = (
        f"({left_expr}.dim() >= 2 && {right_expr}.dim() >= 2 && "
        f"{left_expr}.size({left_expr}.dim() - 1) == 0 && "
        f"{right_expr}.size({right_expr}.dim() - 2) == 0 && "
        f"{left_expr}.scalar_type() == torch::kInt64 && "
        f"{right_expr}.scalar_type() == torch::kInt64)"
    )
    if target['detector_id'] == 'tensor_empty_v1':
        condition = f"({left_expr}.numel() == 0)"
    elif target['detector_id'] == 'tensor_pair_empty_v1':
        condition = f"({left_expr}.numel() == 0 || {right_expr}.numel() == 0)"
    elif target['detector_id'] == 'tensor_shape_mismatch_v1':
        condition = f"(!{left_expr}.sizes().equals({right_expr}.sizes()))"
    refs = (TraceRef("evaluation_target", target_id),)
    return (
        f"const bool {name} = {condition};",
        EventAtom("activation_checked", target_id, trace_refs=refs),
        EventAtom(
            "activation_true",
            target_id,
            condition_expression=name,
            trace_refs=refs,
        ),
        EventAtom(
            "activation_unevaluable",
            target_id,
            condition_expression="false",
            trace_refs=refs,
        ),
        EventAtom(
            "activation_check_error",
            target_id,
            condition_expression="false",
            trace_refs=refs,
        ),
    )


def materialize_strategy(
    resolved: ResolvedInputs,
    selector_ranges: Mapping[str, tuple[int, int]],
    template_path: Path,
    evaluation_targets: Sequence[Mapping[str, Any]] = (),
) -> tuple[
    str,
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    strategy = resolved.strategy
    harness_spec = resolved.harness_spec
    catalog = resolved.catalog

    primitives = primitive_map(catalog)
    state = MaterializationState(
        includes=set(),
        support_blocks={},
        materialization_map=[],
        instrumentation_map=[],
        segment_blocks={},
    )

    dispatch_lines: list[str] = []

    for branch_index, branch in enumerate(
        strategy["implementation_plan"]["branch_strategies"]
    ):
        branch_id = branch["source_branch_id"]
        start, end = selector_ranges[branch_id]
        evaluation_injected = False
        slot_indexes = [
            SLOT_ORDER.index(step["template_slot"])
            for step in branch["steps"]
        ]
        if slot_indexes != sorted(slot_indexes):
            raise MaterializationError(
                f"Branch {branch_id} violates canonical template-slot order"
            )
        binding_keys = [
            (
                binding["spec_element_type"],
                binding["spec_element_id"],
            )
            for binding in branch["spec_bindings"]
        ]
        if len(binding_keys) != len(set(binding_keys)):
            raise MaterializationError(
                f"Branch {branch_id} binds one HarnessSpec element more than once"
            )

        if branch_index == 0:
            dispatch_lines.append(f"if (hbfg_selector <= {end}) {{")
        elif end == 255:
            dispatch_lines.append("else {")
        else:
            dispatch_lines.append(
                f"else if (hbfg_selector <= {end}) {{"
            )

        branch_entry = EventAtom(
            event_kind="branch_entered",
            key_suffix="entry",
        )
        entry_line = add_event(
            state,
            branch_id,
            branch_entry,
            {
                "owner_type": "generator_infrastructure",
                "owner_id": "branch_entry",
            },
        )
        dispatch_lines.extend(indent_lines([entry_line], 2))

        values = {
            value_id: BoundValue(expression, value_kind)
            for value_id, (expression, value_kind)
            in TEMPLATE_BUILTINS.items()
        }

        failure_handlers = branch["failure_handlers"]

        for step_index, step in enumerate(branch["steps"], start=1):
            primitive = primitives.get(step["primitive_id"])
            if primitive is None:
                raise MaterializationError(
                    f"Step {step['step_id']} references unknown Primitive "
                    f"{step['primitive_id']}"
                )
            primitive = resolve_materialization_primitive(
                primitive,
                resolved.api_profile,
            )

            emitter_id = primitive["implementation_binding"]["emitter_id"]
            emitter = EMITTERS.get(emitter_id)
            if emitter is None:
                raise MaterializationError(
                    f"No deterministic Emitter is registered for {emitter_id}"
                )

            inputs: dict[str, BoundValue] = {}
            for binding in step["input_bindings"]:
                value_ref = binding["value_ref"]
                if value_ref not in values:
                    raise MaterializationError(
                        f"Step {step['step_id']} references unavailable value "
                        f"{value_ref}"
                    )
                inputs[binding["port_id"]] = values[value_ref]

            parameters = resolve_parameter_bindings(
                branch_id,
                step,
                values,
                harness_spec,
            )

            output_names = {
                binding["port_id"]: (
                    f"hbfg_{safe_component(branch_id)}_"
                    f"{binding['value_id']}"
                )
                for binding in step["output_bindings"]
            }

            step_bindings = tuple(
                binding
                for binding in branch["spec_bindings"]
                if step["step_id"] in binding["implementation_step_ids"]
            )
            step_handlers = tuple(
                handler
                for handler in failure_handlers
                if handler["trigger"]["step_id"] == step["step_id"]
            )

            context = EmitterContext(
                branch_id=branch_id,
                step=step,
                primitive=primitive,
                inputs=inputs,
                parameters=parameters,
                output_names=output_names,
                spec_bindings=step_bindings,
                failure_handlers=step_handlers,
                strategy_branch=branch,
                harness_spec=harness_spec,
                api_profile=resolved.api_profile,
                helper_profile=resolve_helper_profile(
                    primitive,
                    resolved.helper_profiles,
                ),
            )

            try:
                emission = emitter(context)
            except BuildError:
                raise
            except Exception as exc:
                raise MaterializationError(
                    f"Emitter {emitter_id} failed for Step "
                    f"{step['step_id']}: {exc}"
                ) from exc

            expected_handler_ids = [
                item["failure_handler_id"]
                for item in step_handlers
            ]
            validate_emission(
                step,
                primitive,
                emission,
                expected_handler_ids,
            )

            state.includes.update(emission.includes)
            add_support_blocks(state, emission.support_blocks)

            injected_atoms: tuple[CodeAtom, ...] = ()
            if (
                evaluation_targets
                and not evaluation_injected
                and step["template_slot"] == "target_call"
            ):
                injected_atoms = tuple(
                    atom
                    for target in evaluation_targets
                    for atom in evaluation_target_atoms(
                        target, branch_id, inputs
                    )
                )
                evaluation_injected = True

            segment_id = (
                f"seg_{safe_component(branch_id)}_{step_index:03d}"
            )
            segment_lines = [
                f"// HBFG_SEGMENT_BEGIN:{segment_id}",
            ]

            for atom in (*injected_atoms, *emission.atoms):
                if isinstance(atom, str):
                    if not atom.strip():
                        segment_lines.append("")
                    else:
                        segment_lines.extend(atom.splitlines())
                    continue

                segment_lines.append(
                    add_event(
                        state,
                        branch_id,
                        atom,
                        {
                            "owner_type": "strategy_segment",
                            "owner_id": segment_id,
                        },
                    )
                )

            segment_lines.append(
                f"// HBFG_SEGMENT_END:{segment_id}"
            )
            state.segment_blocks[segment_id] = segment_lines
            dispatch_lines.extend(indent_lines(segment_lines, 2))

            state.materialization_map.append(
                {
                    "branch_id": branch_id,
                    "step_id": step["step_id"],
                    "primitive_id": primitive["primitive_id"],
                    "emitter_id": emitter_id,
                    "template_slot": step["template_slot"],
                    "emitted_segment_id": segment_id,
                    "materialized_failure_handler_ids":
                        sorted(expected_handler_ids),
                    "source_span": {
                        "start_line": 1,
                        "end_line": 1,
                    },
                }
            )

            output_bindings = {
                item["port_id"]: item["value_id"]
                for item in step["output_bindings"]
            }
            for port_id, bound_value in emission.outputs.items():
                values[output_bindings[port_id]] = bound_value

        dispatch_lines.append("}")

    includes = "\n".join(
        f"#include {include}"
        for include in sorted(state.includes)
    )

    support_code = "\n\n".join(
        code.rstrip()
        for code in state.support_blocks.values()
    )

    template = template_path.read_text(encoding="utf-8")
    source = replace_line_marker(
        template,
        INSERT_MARKERS["generated_includes"],
        includes,
    )
    source = replace_line_marker(
        source,
        INSERT_MARKERS["generated_support_code"],
        support_code,
    )
    source = replace_line_marker(
        source,
        INSERT_MARKERS["branch_dispatch"],
        "\n".join(indent_lines(dispatch_lines, 4)),
    )

    return (
        source,
        state.materialization_map,
        state.instrumentation_map,
    )


def replace_line_marker(text: str, marker: str, replacement: str) -> str:
    pattern = re.compile(
        rf"(?m)^[ \t]*{re.escape(marker)}[ \t]*$"
    )
    result, count = pattern.subn(lambda _: replacement, text)
    if count != 1:
        raise MaterializationError(
            f"Expected exactly one template marker {marker!r}, found {count}"
        )
    return result


def cpp_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def replace_value_marker(
    text: str,
    marker: str,
    replacement: str,
) -> str:
    count = text.count(marker)
    if count != 1:
        raise MaterializationError(
            f"Expected exactly one template value marker {marker!r}, "
            f"found {count}"
        )
    return text.replace(marker, replacement)


def finalize_source(
    source: str,
    artifact_id: str,
    key: str,
    site_count: int,
) -> str:
    source = replace_value_marker(
        source,
        VALUE_MARKERS["instrumentation_site_count"],
        str(site_count),
    )
    source = replace_value_marker(
        source,
        VALUE_MARKERS["artifact_id"],
        cpp_string(artifact_id),
    )
    source = replace_value_marker(
        source,
        VALUE_MARKERS["generation_key"],
        cpp_string(key),
    )

    if "HBFG_INSERT:" in source or "HBFG_VALUE:" in source:
        raise MaterializationError(
            "Generated source contains an unresolved template marker"
        )

    if source.count("LLVMFuzzerTestOneInput") != 1:
        raise MaterializationError(
            "Generated source must contain exactly one LibFuzzer entrypoint"
        )

    return source.rstrip() + "\n"


def unique_marker_line(lines: Sequence[str], marker: str) -> int:
    matches = [
        index + 1
        for index, line in enumerate(lines)
        if marker in line
    ]
    if len(matches) != 1:
        raise MaterializationError(
            f"Expected one source marker {marker!r}, found {len(matches)}"
        )
    return matches[0]


def resolve_source_spans(
    source: str,
    materialization_map: list[dict[str, Any]],
    instrumentation_map: list[dict[str, Any]],
) -> None:
    lines = source.splitlines()

    for entry in materialization_map:
        segment_id = entry["emitted_segment_id"]
        start = unique_marker_line(
            lines,
            f"HBFG_SEGMENT_BEGIN:{segment_id}",
        )
        end = unique_marker_line(
            lines,
            f"HBFG_SEGMENT_END:{segment_id}",
        )
        if end < start:
            raise MaterializationError(
                f"Segment {segment_id} has reversed source markers"
            )
        entry["source_span"] = {
            "start_line": start,
            "end_line": end,
        }

    for entry in instrumentation_map:
        line = unique_marker_line(
            lines,
            f"HBFG_EVENT:{entry['instrumentation_binding_id']}",
        )
        entry["source_span"] = {
            "start_line": line,
            "end_line": line,
        }


def bound_determinism_oracle_ids(
    strategy_branch: Mapping[str, Any],
    spec_branch: Mapping[str, Any],
) -> set[str]:
    oracle_types = {
        item["oracle_requirement_id"]: item["oracle_type"]
        for item in spec_branch.get("oracle_requirements", [])
    }
    return {
        binding["spec_element_id"]
        for binding in strategy_branch["spec_bindings"]
        if binding["spec_element_type"] == "oracle_requirement"
        and oracle_types.get(binding["spec_element_id"]) == "determinism"
    }


def validate_materialization_maps(
    strategy: Mapping[str, Any],
    harness_spec: Mapping[str, Any],
    materialization_map: Sequence[Mapping[str, Any]],
    instrumentation_map: Sequence[Mapping[str, Any]],
    evaluation_target_ids: Sequence[str] = (),
) -> None:
    expected_steps = [
        (
            branch["source_branch_id"],
            step["step_id"],
        )
        for branch in strategy["implementation_plan"]["branch_strategies"]
        for step in branch["steps"]
    ]
    actual_steps = [
        (entry["branch_id"], entry["step_id"])
        for entry in materialization_map
    ]
    if actual_steps != expected_steps:
        raise MaterializationError(
            "Materialization Map does not match Strategy Step order"
        )

    segment_ids = [
        entry["emitted_segment_id"]
        for entry in materialization_map
    ]
    if len(segment_ids) != len(set(segment_ids)):
        raise MaterializationError(
            "Materialization Map contains duplicate segment IDs"
        )

    site_ids = [
        entry["runtime_site_id"]
        for entry in instrumentation_map
    ]
    if site_ids != list(range(len(instrumentation_map))):
        raise MaterializationError(
            "runtime_site_id values are not contiguous from zero"
        )

    binding_ids = [
        entry["instrumentation_binding_id"]
        for entry in instrumentation_map
    ]
    event_keys = [
        entry["event_key"]
        for entry in instrumentation_map
    ]
    if len(binding_ids) != len(set(binding_ids)):
        raise MaterializationError(
            "Instrumentation Map contains duplicate binding IDs"
        )
    if len(event_keys) != len(set(event_keys)):
        raise MaterializationError(
            "Instrumentation Map contains duplicate event keys"
        )

    segment_spans = {
        entry["emitted_segment_id"]: entry["source_span"]
        for entry in materialization_map
    }
    ordered_segments = sorted(
        materialization_map,
        key=lambda item: item["source_span"]["start_line"],
    )
    for previous, current in zip(ordered_segments, ordered_segments[1:]):
        if (
            previous["source_span"]["end_line"]
            >= current["source_span"]["start_line"]
        ):
            raise MaterializationError(
                "Materialized Strategy segment source spans overlap"
            )

    allowed_infrastructure_owners = {
        "fuzzer_entry",
        "branch_dispatch",
        "branch_entry",
        "iteration_exit",
    }
    for event in instrumentation_map:
        owner = event["source_owner"]
        if owner["owner_type"] == "strategy_segment":
            owner_span = segment_spans.get(owner["owner_id"])
            if owner_span is None:
                raise MaterializationError(
                    f"Instrumentation references unknown segment {owner['owner_id']}"
                )
            event_line = event["source_span"]["start_line"]
            if not owner_span["start_line"] <= event_line <= owner_span["end_line"]:
                raise MaterializationError(
                    "Instrumentation source line is outside its owning segment"
                )
        elif owner["owner_id"] not in allowed_infrastructure_owners:
            raise MaterializationError(
                f"Unknown Generator infrastructure owner {owner['owner_id']}"
            )

    strategy_branches = {
        branch["source_branch_id"]: branch
        for branch in strategy["implementation_plan"]["branch_strategies"]
    }
    branch_ids = list(strategy_branches)
    if any(event["branch_id"] not in branch_ids for event in instrumentation_map):
        raise MaterializationError(
            "Instrumentation Map references an unknown Branch"
        )

    spec_branches = {
        branch["branch_id"]: branch
        for branch in harness_spec["exploration_plan"]["branches"]
    }
    for branch_id in branch_ids:
        count = sum(
            entry["branch_id"] == branch_id
            and entry["event_kind"] == "branch_entered"
            for entry in instrumentation_map
        )
        if count != 1:
            raise MaterializationError(
                f"Branch {branch_id} must have exactly one branch_entered event"
            )

        strategy_branch = strategy_branches[branch_id]
        expected_target_count = 1
        target_entries = [
            entry
            for entry in materialization_map
            if entry["branch_id"] == branch_id
            and entry["template_slot"] == "target_call"
        ]
        if len(target_entries) != expected_target_count:
            raise MaterializationError(
                f"Branch {branch_id} must materialize exactly "
                f"{expected_target_count} target_call segment(s)"
            )
        target_segments = {
            entry["emitted_segment_id"] for entry in target_entries
        }
        for event_kind in ("target_api_reached", "target_api_completed", "target_api_exception"):
            matching = [
                event
                for event in instrumentation_map
                if event["branch_id"] == branch_id
                and event["event_kind"] == event_kind
                and event["source_owner"]["owner_type"] == "strategy_segment"
                and event["source_owner"]["owner_id"] in target_segments
            ]
            if len(matching) != expected_target_count:
                raise MaterializationError(
                    f"Branch {branch_id} must materialize exactly "
                    f"{expected_target_count} {event_kind} event(s)"
                )
            for segment_id in target_segments:
                if sum(
                    event["source_owner"]["owner_id"] == segment_id
                    for event in matching
                ) != 1:
                    raise MaterializationError(
                        f"Target segment {segment_id} must own one "
                        f"{event_kind} event"
                    )

    for branch_id in branch_ids:
        conditions = spec_branches[branch_id]["target_conditions"]
        for condition in conditions:
            condition_id = condition["condition_id"]

            def matching_events(event_kind: str) -> list[Mapping[str, Any]]:
                return [
                    event
                    for event in instrumentation_map
                    if event["branch_id"] == branch_id
                    and event["event_kind"] == event_kind
                    and {
                        (ref["ref_type"], ref["ref_id"])
                        for ref in event["trace_refs"]
                    }.issuperset(
                        {
                            ("target_condition", condition_id),
                        }
                    )
                ]

            for event_kind in (
                "activation_checked",
                "activation_true",
                "activation_unevaluable",
                "activation_check_error",
            ):
                if len(matching_events(event_kind)) != len(condition['observe_at']):
                    raise MaterializationError(
                        f'Target Condition {condition_id} must have one {event_kind} event per phase'
                    )

            observations = matching_events("observation_captured")
            expected_locators = {
                (
                    "before" if point == "before_target_api_call" else "after",
                    point,
                )
                for point in condition["observe_at"]
            }
            actual_locators = {
                (
                    event["observation_locator"]["observation_role"],
                    event["observation_locator"]["observation_point"],
                )
                for event in observations
            }
            if actual_locators != expected_locators or len(observations) != len(
                expected_locators
            ):
                raise MaterializationError(
                    f"Target Condition {condition_id} observation events do not "
                    "match its HarnessSpec observation points"
                )
    target_event_kinds = {
        "activation_checked",
        "activation_true",
        "activation_unevaluable",
        "activation_check_error",
    }
    target_groups: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for event in instrumentation_map:
        if event["event_kind"] not in target_event_kinds:
            continue
        evaluation_refs = [
            ref["ref_id"]
            for ref in event["trace_refs"]
            if ref["ref_type"] == "evaluation_target"
        ]
        if not evaluation_refs:
            continue
        if len(evaluation_refs) != 1:
            raise MaterializationError(
                f"{event['event_kind']} must resolve at most one Evaluation Target"
            )
        target_groups.setdefault(
            (event["branch_id"], evaluation_refs[0]), []
        ).append(event)
    for (branch_id, evaluation_target_id), events in target_groups.items():
        counts = {
            event_kind: sum(
                event["event_kind"] == event_kind for event in events
            )
            for event_kind in target_event_kinds
        }
        if any(count != 1 for count in counts.values()):
            raise MaterializationError(
                "Evaluation Target event quartet is incomplete or duplicated for "
                f"Branch {branch_id}, Target {evaluation_target_id}: {counts}"
            )
    if evaluation_target_ids:
        expected_target_ids = set(evaluation_target_ids)
        for branch_id in branch_ids:
            for target_id in expected_target_ids:
                events = [
                    event
                    for event in instrumentation_map
                    if event["branch_id"] == branch_id
                    and event["event_kind"] in target_event_kinds
                    and ("evaluation_target", target_id)
                    in {
                        (ref["ref_type"], ref["ref_id"])
                        for ref in event["trace_refs"]
                    }
                ]
                if len(events) != 4:
                    raise MaterializationError(
                        f"Branch {branch_id} must materialize one quartet "
                        f"for {target_id}"
                    )


def git_snapshot() -> tuple[str, str, str | None]:
    try:
        commit = subprocess.run(
            ["git", "-C", str(REPOSITORY_ROOT), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        status = subprocess.run(
            [
                "git",
                "-C",
                str(REPOSITORY_ROOT),
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout

        if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", commit):
            raise InputError("Repository HEAD is not a supported Git hash")

        if not status:
            return commit, "clean", None

        diff = subprocess.run(
            [
                "git",
                "-C",
                str(REPOSITORY_ROOT),
                "diff",
                "--binary",
                "HEAD",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout

        snapshot = (
            "# git status --porcelain=v1 --untracked-files=all\n"
            f"{status}"
            "\n# git diff --binary HEAD\n"
            f"{diff}"
        )
        return commit, "dirty", snapshot

    except subprocess.CalledProcessError as exc:
        raise InputError("Cannot capture Git provenance") from exc


def load_compile_config(path: Path | None) -> CompileConfiguration | None:
    if path is None:
        return None

    value = load_json(path)
    required = {
        "profile_id",
        "profile_version",
        "command_argv",
        "timeout_seconds",
    }
    optional = {"dependency_files", "environment_identity"}
    if (
        not isinstance(value, dict)
        or not required.issubset(value)
        or set(value) - required - optional
    ):
        raise CompileError(
            "Compile profile must contain profile_id, profile_version, "
            "command_argv, and timeout_seconds; only dependency_files and "
            "environment_identity are optional"
        )

    profile_id = value["profile_id"]
    if not re.fullmatch(r"[a-z][a-z0-9_]*", profile_id):
        raise CompileError("compile_profile.profile_id is invalid")
    profile_version = value["profile_version"]
    if not (
        isinstance(profile_version, int)
        and not isinstance(profile_version, bool)
        and profile_version >= 1
    ) and not (
        isinstance(profile_version, str)
        and bool(profile_version.strip())
    ):
        raise CompileError("compile_profile.profile_version is invalid")

    argv = value["command_argv"]
    if (
        not isinstance(argv, list)
        or not argv
        or not all(isinstance(item, str) and item for item in argv)
    ):
        raise CompileError("compile_profile.command_argv is invalid")
    joined_argv = "\0".join(argv)
    for required_marker in ("{source}", "{binary}"):
        if required_marker not in joined_argv:
            raise CompileError(
                f"compile_profile.command_argv misses {required_marker}"
            )

    timeout = value["timeout_seconds"]
    if (
        not isinstance(timeout, int)
        or isinstance(timeout, bool)
        or timeout < 1
    ):
        raise CompileError("compile_profile.timeout_seconds must be positive")

    dependency_files = value.get("dependency_files", [])
    if not isinstance(dependency_files, list) or not all(
        isinstance(item, str) and item for item in dependency_files
    ):
        raise CompileError(
            "compile_profile.dependency_files must be repository-relative files"
        )
    dependency_refs: list[dict[str, str]] = []
    for item in sorted(set(dependency_files)):
        relative = Path(item)
        dependency = REPOSITORY_ROOT / relative
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or not dependency.is_file()
        ):
            raise CompileError(
                f"Compile dependency is invalid or missing: {item}"
            )
        dependency_refs.append(file_reference(dependency))

    environment_identity = value.get("environment_identity")
    if environment_identity is not None and (
        not isinstance(environment_identity, str)
        or not environment_identity.strip()
    ):
        raise CompileError(
            "compile_profile.environment_identity must be a non-empty string"
        )

    return CompileConfiguration(
        command_argv=tuple(argv),
        timeout_seconds=timeout,
        build_environment_ref={
            "artifact_id": profile_id,
            "artifact_version": profile_version,
            "content_hash": file_hash(path),
        },
        dependency_refs=tuple(dependency_refs),
        environment_identity=environment_identity,
    )


def resolve_compile_argv(
    command_argv: Sequence[str],
    staging_dir: Path,
    runtime_header: Path,
    runtime_source: Path,
) -> list[str]:
    replacements = {
        "{source}": "main.cpp",
        "{binary}": "harness_binary",
        "{runtime_cpp}": str(runtime_source.resolve()),
        "{runtime_header}": str(runtime_header.resolve()),
        "{runtime_header_dir}": str(runtime_header.resolve().parent),
        "{repository_root}": str(REPOSITORY_ROOT.resolve()),
        "{artifact_dir}": str(staging_dir.resolve()),
        "{host_uid}": str(os.getuid()),
        "{host_gid}": str(os.getgid()),
    }

    result: list[str] = []
    for argument in command_argv:
        resolved = argument
        for marker, value in replacements.items():
            resolved = resolved.replace(marker, value)

        if re.search(r"\{[^{}]+\}", resolved):
            raise CompileError(
                f"Unknown compile-command placeholder in {argument!r}"
            )
        result.append(resolved)

    return result


def compile_harness(
    config: CompileConfiguration | None,
    staging_dir: Path,
    final_dir: Path,
    runtime_header: Path,
    runtime_source: Path,
) -> dict[str, Any]:
    if config is None:
        return {
            "status": "skipped",
            "command_argv": [],
            "build_environment_ref": None,
            "exit_code": None,
            "skip_reason": "compile_config_not_provided",
            "diagnostics_ref": None,
            "binary_artifact": None,
        }

    argv = resolve_compile_argv(
        config.command_argv,
        staging_dir,
        runtime_header,
        runtime_source,
    )
    diagnostics_path = staging_dir / "compile_diagnostics.txt"
    final_diagnostics_path = final_dir / "compile_diagnostics.txt"
    binary_path = staging_dir / "harness_binary"
    final_binary_path = final_dir / "harness_binary"

    try:
        completed = subprocess.run(
            argv,
            cwd=staging_dir,
            capture_output=True,
            text=True,
            timeout=config.timeout_seconds,
            check=False,
        )
        diagnostics = (
            "# stdout\n"
            f"{completed.stdout}"
            "\n# stderr\n"
            f"{completed.stderr}"
        )

        if completed.returncode == 0 and binary_path.is_file():
            diagnostics_ref = None
            if diagnostics.strip() not in {"# stdout\n\n# stderr", ""}:
                diagnostics_path.write_text(
                    diagnostics,
                    encoding="utf-8",
                    newline="\n",
                )
                diagnostics_ref = file_reference(
                    diagnostics_path,
                    final_diagnostics_path,
                )

            return {
                "status": "passed",
                "command_argv": argv,
                "build_environment_ref":
                    copy.deepcopy(config.build_environment_ref),
                "exit_code": 0,
                "skip_reason": None,
                "diagnostics_ref": diagnostics_ref,
                "binary_artifact": file_reference(
                    binary_path,
                    final_binary_path,
                ),
            }

        if completed.returncode == 0:
            diagnostics += (
                "\nCompiler returned zero but did not create harness_binary.\n"
            )

        diagnostics_path.write_text(
            diagnostics,
            encoding="utf-8",
            newline="\n",
        )
        return {
            "status": "failed",
            "command_argv": argv,
            "build_environment_ref":
                copy.deepcopy(config.build_environment_ref),
            "exit_code": (
                completed.returncode
                if completed.returncode != 0
                else None
            ),
            "skip_reason": None,
            "diagnostics_ref": file_reference(
                diagnostics_path,
                final_diagnostics_path,
            ),
            "binary_artifact": None,
        }

    except subprocess.TimeoutExpired as exc:
        diagnostics = (
            "Compilation timed out.\n"
            f"stdout:\n{exc.stdout or ''}\n"
            f"stderr:\n{exc.stderr or ''}\n"
        )
    except OSError as exc:
        diagnostics = f"Compiler process could not be started: {exc}\n"

    diagnostics_path.write_text(
        diagnostics,
        encoding="utf-8",
        newline="\n",
    )
    return {
        "status": "failed",
        "command_argv": argv,
        "build_environment_ref":
            copy.deepcopy(config.build_environment_ref),
        "exit_code": None,
        "skip_reason": None,
        "diagnostics_ref": file_reference(
            diagnostics_path,
            final_diagnostics_path,
        ),
        "binary_artifact": None,
    }


def build_artifact_record(
    *,
    artifact_id: str,
    key: str,
    strategy_ref: Mapping[str, Any],
    source_ref: Mapping[str, Any],
    materialization_map: Sequence[Mapping[str, Any]],
    instrumentation_map: Sequence[Mapping[str, Any]],
    compile_check: Mapping[str, Any],
    entrypoint_ref: Mapping[str, Any],
    component_refs: Sequence[Mapping[str, Any]],
    run_id: str,
    repository_commit: str,
    working_tree_state: str,
    working_tree_diff_ref: Mapping[str, Any] | None,
    strategy_review_ref: Mapping[str, Any] | None = None,
    runner_observation_bindings: Sequence[Mapping[str, Any]] = (),
    source_key: str | None = None,
    request: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    checks = [
        {
            "check_id": "strategy_materialization_complete",
            "status": "passed",
        },
        {
            "check_id": "template_markers_resolved",
            "status": "passed",
        },
        {
            "check_id": "source_spans_resolved",
            "status": "passed",
        },
        {
            "check_id": "instrumentation_sites_contiguous",
            "status": "passed",
        },
    ]

    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "record_type": "harness_artifact",
        "identity": {
            "harness_artifact_id": artifact_id,
            "generation_key": key,
            "source_generation_key": source_key or key,
        },
        "source_context": {
            "strategy_revision_ref": dict(strategy_ref),
            'strategy_review_ref': strategy_review_ref,
            'runner_observation_bindings': list(runner_observation_bindings),
            'observability': {
                'condition_scope': (
                    'Per-condition, per-phase counters; no joint-condition '
                    'or native-code reachability proof.'
                ),
                'snapshot_scope': (
                    'Periodic or normal-exit snapshots; missing or '
                    'crash-truncated observations are unknown, not zero.'
                ),
                'exception_scope': (
                    'c10::Error at target invocation only; an exception is '
                    'not automatically invalid input or a detected bug.'
                ),
                'exception_text_policy': (
                    'First 16 target exceptions per process; at most 1024 '
                    'bytes per message; instrumentation counters are not sampled.'
                ),
            },
        },
        "source_artifact": {
            **dict(source_ref),
            "encoding": "utf-8",
            "newline": "lf",
            "language": "cpp",
            "entrypoint": "LLVMFuzzerTestOneInput",
        },
        "materialization_map": list(materialization_map),
        "instrumentation_map": list(instrumentation_map),
        "validation": {
            "static_validation": {
                "status": "passed",
                "checks": checks,
                "issues": [],
            },
            "compile_check": dict(compile_check),
            "human_review": {
                "status": "not_reviewed",
                "reviewer_id": None,
                "reviewed_at": None,
                "review_note": None,
            },
        },
        "provenance": {
            'build_request': dict(
                request or build_request(None, strategy_review_ref)
            ),
            "generator": {
                "generator_id": BUILDER_ID,
                "generator_version": BUILDER_VERSION,
                "entrypoint_ref": dict(entrypoint_ref),
                "component_refs": list(component_refs),
            },
            "generation_run_id": run_id,
            "generated_at": utc_now(),
            "repository_commit": repository_commit,
            "working_tree_state": working_tree_state,
            "working_tree_diff_ref": (
                dict(working_tree_diff_ref)
                if working_tree_diff_ref is not None
                else None
            ),
        },
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        write_json(temporary, value)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def verify_file_reference(reference: Mapping[str, Any], label: str) -> None:
    path = REPOSITORY_ROOT / reference["relative_path"]
    if not path.is_file():
        raise MaterializationError(f"{label} is missing: {path}")
    if file_hash(path) != reference["content_hash"]:
        raise MaterializationError(f"{label} content hash is invalid: {path}")


def existing_artifact_status(
    final_dir: Path,
    artifact_id: str,
    key: str,
    expected_strategy_ref: Mapping[str, Any],
    expected_entrypoint_ref: Mapping[str, Any],
    expected_component_refs: Sequence[Mapping[str, Any]],
    artifact_validator: Draft202012Validator,
    expected_build_request: Mapping[str, Any] | None = None,
    expected_source_hash: str | None = None,
    expected_materialization_map: Sequence[Mapping[str, Any]] | None = None,
    expected_instrumentation_map: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any] | None:
    if not final_dir.exists():
        return None

    record_path = final_dir / "harness_artifact.json"
    source_path = final_dir / "main.cpp"
    if not record_path.is_file() or not source_path.is_file():
        raise MaterializationError(
            f"Existing Artifact directory is incomplete: {final_dir}"
        )

    record = load_json(record_path)
    validate_record(record, artifact_validator, f"Artifact {record_path}")

    if (
        record["identity"]["harness_artifact_id"] != artifact_id
        or record["identity"]["generation_key"] != key
    ):
        raise MaterializationError(
            f"Existing Artifact directory conflicts with {artifact_id}"
        )

    if record["source_context"]["strategy_revision_ref"] != expected_strategy_ref:
        raise MaterializationError(
            f"Existing Artifact Strategy reference is stale: {final_dir}"
        )

    generator = record["provenance"]["generator"]
    if (
        generator["generator_id"] != BUILDER_ID
        or generator["generator_version"] != BUILDER_VERSION
        or generator["entrypoint_ref"] != expected_entrypoint_ref
        or generator["component_refs"] != list(expected_component_refs)
    ):
        raise MaterializationError(
            f"Existing Artifact Generator provenance is stale: {final_dir}"
        )

    expected_source_path = repository_relative(source_path)
    if record["source_artifact"]["relative_path"] != expected_source_path:
        raise MaterializationError(
            f"Existing Artifact source path is inconsistent: {final_dir}"
        )
    if record["source_artifact"]["content_hash"] != file_hash(source_path):
        raise MaterializationError(
            f"Existing Artifact source hash is invalid: {final_dir}"
        )

    compile_check = record["validation"]["compile_check"]
    if expected_build_request is not None:
        stored_request = record["provenance"].get("build_request", {})
        identity_keys = (
            "compile_profile_ref", "dependency_refs", "environment_identity"
        )
        if any(stored_request.get(key) != expected_build_request.get(key)
               for key in identity_keys):
            raise MaterializationError(
                "Existing Artifact build request does not match"
            )
        requested_profile = expected_build_request["compile_profile_ref"]
        if compile_check["build_environment_ref"] != requested_profile:
            raise MaterializationError(
                "Existing Artifact compile profile does not match"
            )
        if requested_profile is not None and compile_check["status"] != "passed":
            raise MaterializationError(
                "Existing Artifact does not satisfy requested compilation"
            )
    if (
        expected_source_hash is not None
        and record["source_artifact"]["content_hash"] != expected_source_hash
    ):
        raise MaterializationError(
            "Existing Artifact source differs from fresh materialization"
        )
    for field, expected in (
        ("materialization_map", expected_materialization_map),
        ("instrumentation_map", expected_instrumentation_map),
    ):
        if expected is not None and record[field] != list(expected):
            raise MaterializationError(
                f"Existing Artifact {field} differs from fresh validation"
            )
    for field in ("diagnostics_ref", "binary_artifact"):
        reference = compile_check[field]
        if reference is not None:
            verify_file_reference(reference, f"Existing Artifact {field}")
    diff_ref = record["provenance"]["working_tree_diff_ref"]
    if diff_ref is not None:
        verify_file_reference(diff_ref, "Existing working-tree snapshot")

    return record


def build_one(
    *,
    strategy_path: Path,
    strategy_validator: Draft202012Validator,
    artifact_validator: Draft202012Validator,
    catalog: Mapping[str, Any],
    spec_store: Mapping[tuple[str, int, str], Mapping[str, Any]],
    api_store: Mapping[tuple[str, int, str], Mapping[str, Any]],
    helper_store: Mapping[tuple[str, int, str], Mapping[str, Any]],
    template_path: Path,
    runtime_header: Path,
    runtime_source: Path,
    evaluation_target_manifest: Path | None,
    evaluation_target_record: Mapping[str, Any] | None,
    output_root: Path,
    compile_config: CompileConfiguration | None,
    run_id: str,
    repository_commit: str,
    working_tree_state: str,
    working_tree_snapshot: str | None,
    strategy_review_path: Path | None = None,
    preflight_only: bool = False,
) -> dict[str, Any]:
    strategy = load_json(strategy_path)
    validate_record(strategy, strategy_validator, f"Strategy {strategy_path}")
    external_review_ref = None if preflight_only else approved_strategy_review(strategy_review_path, strategy_path, strategy)

    resolved = resolve_inputs(
        strategy,
        catalog,
        spec_store,
        api_store,
        helper_store,
        template_path,
    )
    revalidate_strategy(resolved)

    strategy_ref = strategy_reference(strategy)
    evaluation_targets = evaluation_targets_for_api(
        evaluation_target_record,
        strategy["identity"]["target_api"],
    )
    entrypoint_ref, component_refs = generator_components(
        template_path,
        runtime_header,
        runtime_source,
        evaluation_target_manifest,
    )
    source_key = generation_key(
        strategy_ref,
        entrypoint_ref,
        component_refs,
    )
    request = build_request(compile_config, external_review_ref)
    key = build_generation_key(source_key, request)
    artifact_id = harness_artifact_id(strategy, key)

    identity = strategy["identity"]
    final_dir = (
        output_root
        / safe_component(identity["framework"])
        / safe_component(identity["target_api"])
        / identity["spec_mode"]
        / artifact_id
    )

    spec_branches = resolved.harness_spec["exploration_plan"]["branches"]
    selector_ranges = allocate_selector_ranges(spec_branches)

    source, materialization_map, instrumentation_map = (
        materialize_strategy(
            resolved,
            selector_ranges,
            template_path,
            evaluation_targets,
        )
    )
    source = finalize_source(
        source,
        artifact_id,
        key,
        len(instrumentation_map),
    )
    resolve_source_spans(
        source,
        materialization_map,
        instrumentation_map,
    )
    validate_materialization_maps(
        strategy,
        resolved.harness_spec,
        materialization_map,
        instrumentation_map,
        [item["evaluation_target_id"] for item in evaluation_targets],
    )
    if preflight_only:
        return {'strategy_path': repository_relative(strategy_path), 'status': 'preflight_passed',
                'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                'materialized_steps': len(materialization_map), 'instrumentation_sites': len(instrumentation_map),
                'compile_status': 'not_run', 'artifact_path': None}

    existing = existing_artifact_status(
        final_dir,
        artifact_id,
        key,
        strategy_ref,
        entrypoint_ref,
        component_refs,
        artifact_validator,
        request,
        hashlib.sha256(source.encode()).hexdigest(),
        materialization_map,
        instrumentation_map,
    )
    if existing is not None:
        return {
            "strategy_path": repository_relative(strategy_path),
            "status": "reused",
            "artifact_id": artifact_id,
            "artifact_path": repository_relative(
                final_dir / "harness_artifact.json"
            ),
            "source_status": "passed",
            "compile_status":
                existing["validation"]["compile_check"]["status"],
            "execution_readiness": (
                "compiled_not_run" if compile_config is not None
                else "source_only"
            ),
            "runtime_validation": "not_run",
        }

    final_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(
        tempfile.mkdtemp(
            prefix=f".{artifact_id}.",
            dir=final_dir.parent,
        )
    )

    try:
        source_path = staging_dir / "main.cpp"
        source_path.write_text(
            source,
            encoding="utf-8",
            newline="\n",
        )

        working_tree_diff_ref = None
        if working_tree_snapshot is not None:
            snapshot_path = staging_dir / "working_tree_state.txt"
            snapshot_path.write_text(
                working_tree_snapshot,
                encoding="utf-8",
                newline="\n",
            )
            working_tree_diff_ref = file_reference(
                snapshot_path,
                final_dir / "working_tree_state.txt",
            )

        compile_check = compile_harness(
            compile_config,
            staging_dir,
            final_dir,
            runtime_header,
            runtime_source,
        )

        if compile_check["status"] == "failed":
            failed_dir = (
                output_root / "failed_builds" / artifact_id / run_id
            )
            for field in ("diagnostics_ref", "binary_artifact"):
                reference = compile_check[field]
                if reference is not None:
                    reference["relative_path"] = repository_relative(
                        failed_dir / Path(reference["relative_path"]).name
                    )
            if working_tree_diff_ref is not None:
                working_tree_diff_ref["relative_path"] = repository_relative(
                    failed_dir / "working_tree_state.txt"
                )
            final_dir = failed_dir
            final_dir.parent.mkdir(parents=True, exist_ok=True)

        source_ref = file_reference(
            source_path,
            final_dir / "main.cpp",
        )

        record = build_artifact_record(
            artifact_id=artifact_id,
            key=key,
            strategy_ref=strategy_ref,
            source_ref=source_ref,
            materialization_map=materialization_map,
            instrumentation_map=instrumentation_map,
            compile_check=compile_check,
            entrypoint_ref=entrypoint_ref,
            component_refs=component_refs,
            run_id=run_id,
            repository_commit=repository_commit,
            working_tree_state=working_tree_state,
            working_tree_diff_ref=working_tree_diff_ref,
            strategy_review_ref=external_review_ref,
            source_key=source_key,
            request=request,
            runner_observation_bindings=[{
                'source_branch_id': branch['source_branch_id'],
                'spec_element_id': binding['spec_element_id'],
                'runner_events': list(binding['runner_events']),
                'subject_refs': next(obs['subject_refs'] for spec_branch in resolved.harness_spec['exploration_plan']['branches']
                    if spec_branch['branch_id'] == branch['source_branch_id'] for obs in spec_branch['behavior_observations']
                    if obs['observation_id'] == binding['spec_element_id']),
                'observe_at': 'on_target_api_termination',
                'capability_scope': 'Requested external process outcomes; in-harness c10::Error is target_api_exception. Tensor snapshots and native target-code reachability need explicit Runner capabilities, not this binding alone.'
            } for branch in strategy['implementation_plan']['branch_strategies']
              for binding in branch['spec_bindings'] if binding['binding_kind'] == 'runner_event'],
        )
        validate_record(
            record,
            artifact_validator,
            f"Harness Artifact {artifact_id}",
        )

        write_json(
            staging_dir / "harness_artifact.json",
            record,
        )

        if final_dir.exists():
            raise MaterializationError(
                f"Artifact directory appeared concurrently: {final_dir}"
            )
        staging_dir.rename(final_dir)

        return {
            "strategy_path": repository_relative(strategy_path),
            "status": (
                "failed" if compile_check["status"] == "failed"
                else "generated"
            ),
            "artifact_id": artifact_id,
            "artifact_path": repository_relative(
                final_dir / "harness_artifact.json"
            ),
            "compile_status": compile_check["status"],
            "source_status": "passed",
            "execution_readiness": {
                "passed": "compiled_not_run",
                "failed": "blocked",
                "skipped": "source_only",
            }[compile_check["status"]],
            "runtime_validation": "not_run",
        }

    except Exception:
        if staging_dir.exists():
            retained = (
                output_root
                / "failed_builds"
                / artifact_id
                / f"{run_id}_assembly"
            )
            retained.parent.mkdir(parents=True, exist_ok=True)
            staging_dir.rename(retained)
        raise


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Deterministically materialize validated Strategy Plans as "
            "C++ Harness Artifacts."
        )
    )
    parser.add_argument(
        "--strategy-plan",
        type=Path,
        action="append",
        required=True,
        help="Strategy Plan JSON; repeat for batch generation.",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=DEFAULTS["catalog"],
    )
    parser.add_argument(
        "--harness-spec-root",
        type=Path,
        default=DEFAULTS["harness_specs"],
    )
    parser.add_argument(
        "--api-profile-root",
        type=Path,
        default=DEFAULTS["api_profiles"],
    )
    parser.add_argument(
        "--helper-profile-root",
        type=Path,
        default=DEFAULTS["helper_profiles"],
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=DEFAULTS["template"],
    )
    parser.add_argument(
        "--runtime-header",
        type=Path,
        default=DEFAULTS["runtime_header"],
    )
    parser.add_argument(
        "--runtime-source",
        type=Path,
        default=DEFAULTS["runtime_source"],
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULTS["output_root"],
    )
    parser.add_argument(
        "--compile-config",
        type=Path,
        help=(
            "Compile profile containing profile_id, profile_version, "
            "complete command_argv, and timeout_seconds. Its exact file "
            "hash becomes build_environment_ref.content_hash."
        ),
    )
    parser.add_argument(
        "--strategy-schema",
        type=Path,
        default=DEFAULTS["strategy_schema"],
    )
    parser.add_argument(
        "--catalog-schema",
        type=Path,
        default=DEFAULTS["catalog_schema"],
    )
    parser.add_argument(
        "--harness-spec-schema",
        type=Path,
        default=DEFAULTS["harness_spec_schema"],
    )
    parser.add_argument(
        "--api-profile-schema",
        type=Path,
        default=DEFAULTS["api_profile_schema"],
    )
    parser.add_argument(
        "--helper-profile-schema",
        type=Path,
        default=DEFAULTS["helper_profile_schema"],
    )
    parser.add_argument(
        "--artifact-schema",
        type=Path,
        default=DEFAULTS["artifact_schema"],
    )
    parser.add_argument(
        "--evaluation-target-manifest",
        type=Path,
        help=(
            "Manifest used for deterministic post-synthesis target checks."
        ),
    )
    parser.add_argument(
        "--evaluation-target-schema",
        type=Path,
        default=DEFAULTS["evaluation_target_schema"],
    )
    parser.add_argument(
        "--result-json",
        type=Path,
        help="Machine-readable outcome selected by the orchestrator.",
    )
    parser.add_argument('--strategy-review', type=Path, action='append', default=[], help='Exact approved external review; repeat for each Strategy subject.')
    parser.add_argument('--preflight-only', action='store_true', help='Run semantic and full source/map validation without producing an Artifact or requiring human approval.')
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    run_id = (
        "harness_generation_"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_"
        f"{uuid.uuid4().hex[:12]}"
    )
    started_at = utc_now()

    try:
        strategy_validator = load_validator(args.strategy_schema)
        catalog_validator = load_validator(args.catalog_schema)
        harness_spec_validator = load_validator(args.harness_spec_schema)
        api_profile_validator = load_validator(args.api_profile_schema)
        helper_profile_validator = load_validator(args.helper_profile_schema)
        artifact_validator = load_validator(args.artifact_schema)
        evaluation_target_record = None
        if args.evaluation_target_manifest is not None:
            evaluation_target_validator = load_validator(
                args.evaluation_target_schema
            )
            evaluation_target_record = load_json(
                args.evaluation_target_manifest
            )
            validate_record(
                evaluation_target_record,
                evaluation_target_validator,
                "Evaluation Target Manifest",
            )

        catalog = load_json(args.catalog)
        validate_record(catalog, catalog_validator, "Strategy Catalog")
        if (
            catalog["review"]["validation_status"] != "passed"
            or catalog["review"]["human_review_status"] != "approved"
        ):
            raise InputError("Strategy Catalog is not passed and approved")

        selected_strategies = [load_json(path) for path in args.strategy_plan]
        for path, strategy in zip(args.strategy_plan, selected_strategies):
            validate_record(strategy, strategy_validator, f'Strategy {path}')
        reviews_by_hash = {}
        for path in args.strategy_review:
            review = load_json(path)
            digest = review.get('subject', {}).get('content_hash')
            if digest in reviews_by_hash:
                raise InputError('More than one Strategy review for the same subject')
            reviews_by_hash[digest] = path
        spec_store = load_harness_spec_store(
            args.harness_spec_root,
            harness_spec_validator,
            [strategy['source_context']['harness_spec_ref'] for strategy in selected_strategies],
        )
        selected_specs = []
        for strategy in selected_strategies:
            ref = strategy['source_context']['harness_spec_ref']
            key = (ref['spec_id'], ref['revision_number'], ref['content_hash'])
            spec = spec_store.get(key)
            if spec is None:
                raise InputError(f'Exact HarnessSpec is unavailable: {key}')
            selected_specs.append(spec)
        api_refs = [spec['target_context']['api_profile_ref'] for spec in selected_specs]
        helper_refs = [
            ref for spec in selected_specs
            for ref in spec['target_context']['available_helper_profile_refs']
        ]
        api_store = load_profile_store(
            args.api_profile_root,
            api_profile_validator,
            "API Profile",
            api_refs,
        )
        helper_store = load_profile_store(
            args.helper_profile_root,
            helper_profile_validator,
            "Helper Profile",
            helper_refs,
        )
        compile_config = (
            None if args.preflight_only
            else load_compile_config(args.compile_config)
        )

        repository_relative(args.output_root)

        for required_path in (
            args.template,
            args.runtime_header,
            args.runtime_source,
        ):
            if not required_path.is_file():
                raise InputError(f"Required source file is missing: {required_path}")

        repository_commit, working_tree_state, snapshot = git_snapshot()

    except BuildError as exc:
        result = {
            "status": "global_input_error",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
        if args.result_json is not None:
            write_json_atomic(args.result_json, result)
        print(json.dumps(result, ensure_ascii=False, indent=2), file=os.sys.stderr)
        return 2

    results: list[dict[str, Any]] = []

    for strategy_path in sorted(
        {path.resolve() for path in args.strategy_plan},
        key=lambda path: path.as_posix(),
    ):
        try:
            result = build_one(
                strategy_path=strategy_path,
                strategy_validator=strategy_validator,
                artifact_validator=artifact_validator,
                catalog=catalog,
                spec_store=spec_store,
                api_store=api_store,
                helper_store=helper_store,
                template_path=args.template,
                runtime_header=args.runtime_header,
                runtime_source=args.runtime_source,
                evaluation_target_manifest=args.evaluation_target_manifest,
                evaluation_target_record=evaluation_target_record,
                output_root=args.output_root,
                compile_config=compile_config,
                run_id=run_id,
                repository_commit=repository_commit,
                working_tree_state=working_tree_state,
                working_tree_snapshot=snapshot,
                strategy_review_path=reviews_by_hash.get(canonical_hash(load_json(strategy_path))),
                preflight_only=args.preflight_only,
            )
        except Exception as exc:
            result = {
                "strategy_path": (
                    repository_relative(strategy_path)
                    if strategy_path.is_relative_to(REPOSITORY_ROOT)
                    else str(strategy_path)
                ),
                "status": "failed",
                "error_type": type(exc).__name__,
                "message": str(exc),
            }

        results.append(result)

    summary = {
        "run_id": run_id,
        "generator_id": BUILDER_ID,
        "generator_version": BUILDER_VERSION,
        "started_at": started_at,
        "finished_at": utc_now(),
        "results": results,
    }

    summary_path = (
        args.output_root
        / "run_summaries"
        / f"{run_id}.json"
    )
    write_json_atomic(summary_path, summary)

    generated = sum(
        item["status"] == "generated"
        for item in results
    )
    reused = sum(
        item["status"] == "reused"
        for item in results
    )
    failed = sum(
        item["status"] == "failed"
        for item in results
    )
    preflight_passed = sum(
        item["status"] == "preflight_passed"
        for item in results
    )
    machine_result = {
        **summary,
        "status": "failed" if failed else "success",
        "summary_path": repository_relative(summary_path),
    }
    if args.result_json is not None:
        write_json_atomic(args.result_json, machine_result)

    print(
        f"generated={generated} reused={reused} failed={failed} "
        f"preflight_passed={preflight_passed} "
        f"summary={summary_path}"
    )
    return 1 if failed else 0



if __name__ == "__main__":
    raise SystemExit(main())
