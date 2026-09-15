#!/usr/bin/env python3
"""Build and validate version-pinned Helper Capability Profile records.

The builder is deterministic and never calls an LLM. It extracts source facts,
merges separately reviewed semantic annotations, validates records, and writes
immutable revisions. It does not select Knowledge, design a HarnessSpec, lower
Strategy Primitives, or generate a fuzzing Harness.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import jsonschema
    from jsonschema.protocols import Validator
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "jsonschema is required; install environment/python-control-requirements.txt"
    ) from exc


BUILDER_VERSION = "helper_profile_builder_v0.1"
SCHEMA_VERSION = "1.0"
ANNOTATION_VERSION = "1.0"

DEFAULT_RUNTIME_CONFIG = Path("runtime/flashfuzz_2_10/runtime_config.json")
DEFAULT_SCHEMA = Path(
    "experiment/EXP011_bug_aware_harness_synthesis/"
    "schemas/helper_profile_record.schema.json"
)
DEFAULT_ANNOTATIONS = Path(
    "experiment/EXP011_bug_aware_harness_synthesis/"
    "annotations/helper_capability_annotations.json"
)
DEFAULT_OUTPUT_ROOT = Path(
    "experiment/EXP011_bug_aware_harness_synthesis/helper_profiles"
)
DEFAULT_FLASHFUZZ_ROOT = Path("third_party/FlashFuzz")
DEFAULT_HEADER = Path(
    "testharness_generation/torch_cpu/torch_cpu_helper/fuzzer_utils.h"
)
DEFAULT_IMPLEMENTATION = Path(
    "testharness_generation/torch_cpu/torch_cpu_helper/fuzzer_utils.cpp"
)

MANDATORY_CHECKS = (
    "header_parse",
    "definition_resolution",
    "declaration_definition_match",
    "dependency_resolution",
    "compile",
    "smoke_execution",
)

EVIDENCE_ALIASES = {
    "header": "ev_helper_header",
    "implementation": "ev_helper_implementation",
    "build_configuration": "ev_build_configuration",
    "annotation": "ev_curated_annotation",
}


class BuilderError(RuntimeError):
    """Base class for expected Builder failures."""


class FatalInputError(BuilderError):
    """A run-level input prevents safe processing."""


class ProfileBuildError(BuilderError):
    """One Helper cannot be converted into a Profile."""


class ProfileValidationError(ProfileBuildError):
    """One generated or existing Profile is invalid."""


def error_kind(error: BaseException) -> str:
    if isinstance(error, ProfileValidationError):
        return "profile_validation"
    if isinstance(error, ProfileBuildError):
        return "profile_build"
    if isinstance(error, OSError):
        return "io_error"
    return "builder_error"


BuildError = BuilderError


@dataclass(frozen=True)
class Parameter:
    name: str
    ordinal: int
    cpp_type: str
    direction: str
    default_kind: str
    default_value: str | None


@dataclass(frozen=True)
class Declaration:
    namespace: str
    function_name: str
    qualified_name: str
    declaration: str
    return_type: str
    parameters: tuple[Parameter, ...]
    signature_hash: str
    annotation_key: str
    profile_id: str
    output_slug: str


@dataclass
class Outcome:
    helper: str
    status: str
    profile_id: str | None = None
    path: str | None = None
    error_kind: str | None = None
    message: str = ""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def timestamp_slug(timestamp: str) -> str:
    return re.sub(r"[^0-9]", "", timestamp) + "Z"


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BuildError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle, object_pairs_hook=reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise BuildError(f"Invalid JSON in {path}: {exc}") from exc


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def profile_hash(profile: dict[str, Any]) -> str:
    value = copy.deepcopy(profile)
    value["metadata"].pop("content_hash", None)
    return canonical_hash(value)


def semantic_payload(profile: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(profile)
    value.pop("revision", None)
    value.pop("metadata", None)
    for item in value.get("evidence", []):
        item.pop("collected_at", None)
    return value


def safe_component(value: str) -> str:
    component = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    component = re.sub(r"_+", "_", component).strip("._-")
    if not component:
        raise BuildError(f"Cannot derive a path component from {value!r}")
    return component.lower()


def normalize_cpp(value: str) -> str:
    value = re.sub(r"\s+", " ", value.strip())
    value = re.sub(r"\s*([();])\s*", r"\1", value)
    value = re.sub(r"\s*,\s*", ", ", value)
    value = re.sub(r"\s*([*&])\s*", r" \1", value)
    return re.sub(r"\s+", " ", value).strip()


def git_head(repository: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise BuildError(f"Cannot resolve Git revision for {repository}: {detail}")
    return result.stdout.strip()


def strip_cpp_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", source)


def matching_delimiter(text: str, start: int, opening: str, closing: str) -> int:
    depth = 0
    in_string: str | None = None
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == in_string:
                in_string = None
            continue
        if char in {'"', "'"}:
            in_string = char
        elif char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return index
    return -1


def namespace_body(source: str) -> tuple[str, str]:
    matches = list(
        re.finditer(r"\bnamespace\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{", source)
    )
    if len(matches) != 1:
        raise BuildError(
            f"Expected one named Helper namespace, found {len(matches)}"
        )
    match = matches[0]
    opening = source.find("{", match.start())
    closing = matching_delimiter(source, opening, "{", "}")
    if closing < 0:
        raise BuildError("Helper namespace has no matching closing brace")
    return match.group(1), source[opening + 1 : closing]


def split_top_level(value: str, delimiter: str = ",") -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    in_string: str | None = None
    escaped = False
    for index, char in enumerate(value):
        if in_string is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == in_string:
                in_string = None
            continue
        if char in {'"', "'"}:
            in_string = char
        elif char in "([{<":
            depth += 1
        elif char in ")]}>":
            depth = max(0, depth - 1)
        elif char == delimiter and depth == 0:
            parts.append(value[start:index].strip())
            start = index + 1
    tail = value[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def split_default(parameter: str) -> tuple[str, str | None]:
    depth = 0
    for index, char in enumerate(parameter):
        if char in "([{<":
            depth += 1
        elif char in ")]}>":
            depth = max(0, depth - 1)
        elif char == "=" and depth == 0:
            return parameter[:index].strip(), parameter[index + 1 :].strip()
    return parameter.strip(), None


def parse_parameter(raw: str, ordinal: int) -> Parameter:
    core, default = split_default(raw)
    match = re.match(r"^(?P<type>.+?)(?P<name>[A-Za-z_][A-Za-z0-9_]*)$", core)
    if not match:
        raise BuildError(f"Unsupported or unnamed parameter declaration: {raw!r}")
    cpp_type = normalize_cpp(match.group("type"))
    name = match.group("name")
    if default is None:
        default_kind, default_value = "no_default", None
    elif default:
        default_kind, default_value = "literal", normalize_cpp(default)
    else:
        default_kind, default_value = "unresolved", None
    direction = (
        "in"
        if "const" in cpp_type or ("&" not in cpp_type and "*" not in cpp_type)
        else "inout"
    )
    return Parameter(
        name=name,
        ordinal=ordinal,
        cpp_type=cpp_type,
        direction=direction,
        default_kind=default_kind,
        default_value=default_value,
    )


def declaration_identity(
    namespace: str,
    return_type: str,
    name: str,
    raw_parameters: str,
    framework: str,
    framework_version: str,
    backend: str,
    provider: str,
    configuration_id: str,
) -> Declaration:
    parameter_parts = split_top_level(raw_parameters)
    if len(parameter_parts) == 1 and parameter_parts[0] in {"", "void"}:
        parameter_parts = []
    parameters = tuple(
        parse_parameter(raw, ordinal)
        for ordinal, raw in enumerate(parameter_parts)
    )
    rendered_parameters = []
    for item in parameters:
        rendered = f"{item.cpp_type} {item.name}"
        if item.default_kind == "literal":
            rendered += f" = {item.default_value}"
        rendered_parameters.append(rendered)
    normalized_return = normalize_cpp(return_type)
    declaration = normalize_cpp(
        f"{normalized_return} {name}({', '.join(rendered_parameters)});"
    )
    signature_hash = hashlib.sha256(declaration.encode("utf-8")).hexdigest()[:12]
    qualified_name = f"{namespace}::{name}"
    annotation_key = f"{qualified_name}#{signature_hash}"
    identity_parts = (
        framework,
        framework_version,
        backend,
        provider,
        configuration_id,
        qualified_name,
        signature_hash,
    )
    profile_id = "hp_" + "_".join(safe_component(part) for part in identity_parts)
    output_slug = f"{safe_component(qualified_name)}__sig_{signature_hash}"
    return Declaration(
        namespace=namespace,
        function_name=name,
        qualified_name=qualified_name,
        declaration=declaration,
        return_type=normalized_return,
        parameters=parameters,
        signature_hash=signature_hash,
        annotation_key=annotation_key,
        profile_id=profile_id,
        output_slug=output_slug,
    )


def discover_declarations(
    header: Path,
    framework: str,
    framework_version: str,
    backend: str,
    provider: str,
    configuration_id: str,
) -> list[Declaration]:
    if not header.is_file():
        raise BuildError(f"Helper header does not exist: {header}")
    source = strip_cpp_comments(header.read_text(encoding="utf-8"))
    namespace, body = namespace_body(source)
    pattern = re.compile(
        r"(?P<return>[A-Za-z_][A-Za-z0-9_:<>,\s*&]*?)"
        r"\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
        r"\s*\((?P<parameters>.*?)\)\s*;",
        flags=re.DOTALL,
    )
    declarations: list[Declaration] = []
    for match in pattern.finditer(body):
        declarations.append(
            declaration_identity(
                namespace,
                match.group("return"),
                match.group("name"),
                match.group("parameters"),
                framework,
                framework_version,
                backend,
                provider,
                configuration_id,
            )
        )
    if not declarations:
        raise BuildError(f"No public Helper declarations found in {header}")
    keys = [item.annotation_key for item in declarations]
    if len(keys) != len(set(keys)):
        raise BuildError("Duplicate normalized Helper declarations were found")
    return sorted(declarations, key=lambda item: item.annotation_key)


def definition_bodies(
    implementation: Path, declarations: list[Declaration]
) -> dict[str, list[str]]:
    if not implementation.is_file():
        return {item.annotation_key: [] for item in declarations}
    source = strip_cpp_comments(implementation.read_text(encoding="utf-8"))
    result: dict[str, list[str]] = {}
    for declaration in declarations:
        matches: list[str] = []
        pattern = re.compile(rf"\b{re.escape(declaration.function_name)}\s*\(")
        for match in pattern.finditer(source):
            opening_parenthesis = source.find("(", match.start())
            closing_parenthesis = matching_delimiter(
                source, opening_parenthesis, "(", ")"
            )
            if closing_parenthesis < 0:
                continue
            raw_parameters = source[opening_parenthesis + 1 : closing_parenthesis]
            parameter_count = len(split_top_level(raw_parameters))
            if not raw_parameters.strip() or raw_parameters.strip() == "void":
                parameter_count = 0
            if parameter_count != len(declaration.parameters):
                continue
            cursor = closing_parenthesis + 1
            while cursor < len(source) and source[cursor].isspace():
                cursor += 1
            if cursor >= len(source) or source[cursor] != "{":
                continue
            closing_brace = matching_delimiter(source, cursor, "{", "}")
            if closing_brace < 0:
                continue
            matches.append(source[match.start() : closing_brace + 1].strip())
        result[declaration.annotation_key] = matches
    return result


def parse_macros(header: Path) -> dict[str, str | None]:
    macros: dict[str, str | None] = {}
    pattern = re.compile(
        r"^\s*#\s*define\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s+(.+?))?\s*$"
    )
    for line in header.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match and "(" not in match.group(1):
            macros[match.group(1)] = match.group(2)
    return macros


def scalar_macro_value(raw: str | None) -> str | int | float | bool | None:
    if raw is None:
        return None
    text = raw.strip()
    if text.lower() in {"true", "false"}:
        return text.lower() == "true"
    try:
        return int(text, 0)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def load_annotations(
    path: Path, provider_revision: str, configuration_id: str
) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        raise BuildError(
            f"Annotation file does not exist: {path}. "
            "Run --discover-only first, then create reviewed annotations."
        )
    value = load_json(path)
    if not isinstance(value, dict):
        raise BuildError("Annotation root must be an object")
    if value.get("annotation_version") != ANNOTATION_VERSION:
        raise BuildError(
            f"annotation_version must be {ANNOTATION_VERSION!r}"
        )
    if value.get("provider_revision") != provider_revision:
        raise BuildError("Annotation provider_revision does not match source")
    if value.get("configuration_id") != configuration_id:
        raise BuildError("Annotation configuration_id does not match target")
    helpers = value.get("helpers")
    if not isinstance(helpers, dict):
        raise BuildError("annotations.helpers must be an object")
    return helpers


def resolve_evidence_refs(values: Any, available: set[str]) -> list[str]:
    if not isinstance(values, list):
        raise ProfileBuildError("evidence_sources must be an array")
    resolved = []
    for value in values:
        if not isinstance(value, str):
            raise ProfileBuildError("evidence_sources entries must be strings")
        reference = EVIDENCE_ALIASES.get(value, value)
        if reference not in available:
            raise ProfileBuildError(f"Unknown evidence source: {value}")
        if reference not in resolved:
            resolved.append(reference)
    return resolved


def evidence(
    evidence_id: str,
    source_kind: str,
    source_location: str,
    source_revision: str | None,
    locator: str | None,
    content_hash: str | None,
    excerpt: str | None,
    collected_at: str,
) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "source_kind": source_kind,
        "source_location": source_location,
        "source_revision": source_revision,
        "locator": locator,
        "content_hash": content_hash,
        "excerpt": excerpt[:1000] if excerpt else None,
        "collected_at": collected_at,
    }


def make_check(
    check_kind: str,
    status: str,
    summary: str,
    evidence_refs: list[str] | None = None,
    issue_refs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "check_id": f"check_{check_kind}",
        "check_kind": check_kind,
        "status": status,
        "summary": summary,
        "evidence_refs": evidence_refs or [],
        "issue_refs": issue_refs or [],
    }


def make_issue(
    issue_id: str,
    issue_kind: str,
    description: str,
    affected_refs: list[str],
    evidence_refs: list[str],
    blocking: bool = True,
) -> dict[str, Any]:
    return {
        "issue_id": issue_id,
        "issue_kind": issue_kind,
        "blocking": blocking,
        "description": description,
        "affected_refs": affected_refs,
        "evidence_refs": evidence_refs,
    }


def capability_issues(capability: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn explicitly unknown semantic facts into auditable validation issues."""
    evidence_refs = capability["evidence_refs"]
    fuzz = capability["fuzz_input_contract"]
    issues: list[dict[str, Any]] = []
    unknown_fuzz_fields = [
        field
        for field in ("interaction_mode", "offset_effect", "consumption_mode")
        if fuzz.get(field) == "unknown"
    ]
    if unknown_fuzz_fields:
        issues.append(
            make_issue(
                "issue_fuzz_contract_unverified",
                "behavior_unverified",
                "Unknown fuzz-input semantics: " + ", ".join(unknown_fuzz_fields),
                [
                    f"capability_contract.fuzz_input_contract.{field}"
                    for field in unknown_fuzz_fields
                ],
                evidence_refs,
                blocking=True,
            )
        )
    if capability["side_effects"].get("status") == "unknown":
        issues.append(
            make_issue(
                "issue_side_effects_unverified",
                "behavior_unverified",
                "Helper side effects have not been established.",
                ["capability_contract.side_effects"],
                evidence_refs,
                blocking=False,
            )
        )
    if capability.get("determinism") == "unknown":
        issues.append(
            make_issue(
                "issue_determinism_unverified",
                "behavior_unverified",
                "Helper determinism has not been established.",
                ["capability_contract.determinism"],
                evidence_refs,
                blocking=False,
            )
        )
    return issues


def map_parameter_reference(value: Any, parameters: dict[str, str]) -> Any:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProfileBuildError("Parameter reference must be a string or null")
    if value in parameters.values():
        return value
    if value not in parameters:
        raise ProfileBuildError(f"Unknown parameter name in annotation: {value}")
    return parameters[value]


def capability_from_annotation(
    annotation: dict[str, Any],
    parameters: list[dict[str, Any]],
    available_evidence: set[str],
) -> dict[str, Any]:
    raw = annotation.get("capability_contract")
    if not isinstance(raw, dict):
        raise ProfileBuildError("capability_contract annotation is required")
    capability = copy.deepcopy(raw)
    parameter_map = {item["name"]: item["parameter_id"] for item in parameters}

    required = {
        "capability_kind",
        "summary",
        "fuzz_input_contract",
        "domain_constraints",
        "behavior_claims",
        "side_effects",
        "determinism",
        "evidence_sources",
    }
    missing = sorted(required - set(capability))
    extra = sorted(set(capability) - required)
    if missing or extra:
        raise ProfileBuildError(
            f"capability_contract keys mismatch; missing={missing}, extra={extra}"
        )

    fuzz = capability["fuzz_input_contract"]
    if not isinstance(fuzz, dict):
        raise ProfileBuildError("capability_contract.fuzz_input_contract must be an object")
    for field in ("data_parameter_refs", "size_parameter_refs"):
        if not isinstance(fuzz.get(field), list):
            raise ProfileBuildError(f"fuzz_input_contract.{field} must be an array")
        fuzz[field] = [
            map_parameter_reference(item, parameter_map) for item in fuzz[field]
        ]
    fuzz["offset_parameter_ref"] = map_parameter_reference(
        fuzz.get("offset_parameter_ref"), parameter_map
    )

    constraints = capability["domain_constraints"]
    if not isinstance(constraints, list):
        raise ProfileBuildError("domain_constraints must be an array")
    for ordinal, constraint in enumerate(constraints, start=1):
        if not isinstance(constraint, dict):
            raise ProfileBuildError(f"domain_constraints[{ordinal - 1}] must be an object")
        constraint.setdefault("constraint_id", f"constraint_{ordinal:03d}")
        subjects = constraint.get("subjects")
        if not isinstance(subjects, list):
            raise ProfileBuildError(
                f"domain_constraints[{ordinal - 1}].subjects must be an array"
            )
        for subject in subjects:
            if not isinstance(subject, dict):
                raise ProfileBuildError("Constraint subjects must be objects")
            if subject.get("entity_kind") == "parameter":
                subject["entity_ref"] = map_parameter_reference(
                    subject.get("entity_ref"), parameter_map
                )
        sources = constraint.pop("evidence_sources", None)
        constraint["evidence_refs"] = resolve_evidence_refs(
            sources, available_evidence
        )

    claims = capability["behavior_claims"]
    if not isinstance(claims, list):
        raise ProfileBuildError("behavior_claims must be an array")
    for ordinal, claim in enumerate(claims, start=1):
        if not isinstance(claim, dict):
            raise ProfileBuildError(f"behavior_claims[{ordinal - 1}] must be an object")
        claim.setdefault("claim_id", f"claim_{ordinal:03d}")
        sources = claim.pop("evidence_sources", None)
        claim["evidence_refs"] = resolve_evidence_refs(
            sources, available_evidence
        )

    sources = capability.pop("evidence_sources")
    capability["evidence_refs"] = resolve_evidence_refs(
        sources, available_evidence
    )
    return capability


def review_from_annotation(annotation: dict[str, Any]) -> dict[str, Any]:
    raw = annotation.get("review")
    if raw is None:
        return {
            "review_status": "unreviewed",
            "reviewer": None,
            "reviewed_at": None,
            "issue_refs": [],
            "notes": None,
        }
    if not isinstance(raw, dict):
        raise ProfileBuildError("review annotation must be an object")
    return copy.deepcopy(raw)


def parameter_records(
    declaration: Declaration,
    annotation: dict[str, Any],
) -> list[dict[str, Any]]:
    roles = annotation.get("parameter_roles")
    if not isinstance(roles, dict):
        raise ProfileBuildError("parameter_roles annotation must be an object")
    declared_names = {item.name for item in declaration.parameters}
    if set(roles) != declared_names:
        raise ProfileBuildError(
            "parameter_roles must contain exactly the declared parameter names"
        )
    records = []
    for item in declaration.parameters:
        records.append(
            {
                "parameter_id": f"param_{item.ordinal:03d}_{safe_component(item.name)}",
                "name": item.name,
                "ordinal": item.ordinal,
                "cpp_type": item.cpp_type,
                "direction": item.direction,
                "semantic_role": roles[item.name],
                "default": {
                    "kind": item.default_kind,
                    "value": item.default_value,
                },
                "evidence_refs": ["ev_helper_header", "ev_curated_annotation"],
            }
        )
    return records


def return_record(
    declaration: Declaration, annotation: dict[str, Any]
) -> dict[str, Any]:
    role = annotation.get("return_role")
    if not isinstance(role, str) or not role:
        raise ProfileBuildError("return_role annotation is required")
    return {
        "cpp_type": declaration.return_type,
        "semantic_role": role,
        "evidence_refs": ["ev_helper_header", "ev_curated_annotation"],
    }


def invocation_template(declaration: Declaration) -> str:
    arguments = ", ".join(f"{{{{{item.name}}}}}" for item in declaration.parameters)
    return f"{declaration.qualified_name}({arguments})"


def active_macro_records(
    macros: dict[str, str | None],
    body: str | None,
    annotation: dict[str, Any],
) -> list[dict[str, Any]]:
    behavior_affecting = annotation.get("behavior_affecting_definitions", [])
    if not isinstance(behavior_affecting, list) or not all(
        isinstance(item, str) for item in behavior_affecting
    ):
        raise ProfileBuildError("behavior_affecting_definitions must be an array of names")
    used = {
        name
        for name in macros
        if body is not None and re.search(rf"\b{re.escape(name)}\b", body)
    }
    used.update(behavior_affecting)
    unknown = sorted(used - set(macros))
    if unknown:
        raise ProfileBuildError(f"Annotated compile definitions not found: {unknown}")
    return [
        {
            "name": name,
            "value": scalar_macro_value(macros[name]),
            "behavior_affecting": name in behavior_affecting,
            "evidence_refs": ["ev_helper_header"],
        }
        for name in sorted(used)
    ]


def build_base_profile(
    declaration: Declaration,
    annotation: dict[str, Any],
    body_matches: list[str],
    macros: dict[str, str | None],
    runtime_config: dict[str, Any],
    runtime_config_path: Path,
    annotations_path: Path,
    header: Path,
    implementation: Path,
    provider_revision: str,
    configuration_id: str,
    backend: str,
    collected_at: str,
) -> dict[str, Any]:
    parameters = parameter_records(declaration, annotation)
    body = body_matches[0] if len(body_matches) == 1 else None

    evidence_records = [
        evidence(
            "ev_helper_header",
            "helper_header",
            header.as_posix(),
            provider_revision,
            declaration.declaration,
            file_hash(header),
            declaration.declaration,
            collected_at,
        ),
        evidence(
            "ev_build_configuration",
            "build_configuration",
            runtime_config_path.as_posix(),
            runtime_config.get("config_version"),
            "target runtime configuration",
            file_hash(runtime_config_path),
            None,
            collected_at,
        ),
        evidence(
            "ev_curated_annotation",
            "curated_annotation",
            annotations_path.as_posix(),
            provider_revision,
            declaration.annotation_key,
            canonical_hash(annotation),
            None,
            collected_at,
        ),
    ]
    if implementation.is_file() and body is not None:
        evidence_records.append(
            evidence(
                "ev_helper_implementation",
                "helper_implementation",
                implementation.as_posix(),
                provider_revision,
                declaration.qualified_name,
                file_hash(implementation),
                body,
                collected_at,
            )
        )
    available_evidence = {item["evidence_id"] for item in evidence_records}
    capability = capability_from_annotation(
        annotation, parameters, available_evidence
    )

    issues = capability_issues(capability)
    checks = [
        make_check(
            "header_parse",
            "passed",
            "Public declaration was parsed deterministically.",
            ["ev_helper_header"],
        )
    ]
    if len(body_matches) == 1:
        checks.append(
            make_check(
                "definition_resolution",
                "passed",
                "One matching implementation body was located.",
                ["ev_helper_implementation"],
            )
        )
    else:
        issue_id = "issue_definition_unresolved"
        issues.append(
            make_issue(
                issue_id,
                "definition_unresolved",
                f"Expected one matching definition, found {len(body_matches)}.",
                ["callable_interface.declaration"],
                ["ev_helper_header"],
            )
        )
        checks.append(
            make_check(
                "definition_resolution",
                "failed",
                "A unique implementation body could not be resolved.",
                ["ev_helper_header"],
                [issue_id],
            )
        )

    checks.extend(
        [
            make_check(
                "declaration_definition_match",
                "not_run",
                "Compiler-backed declaration/definition comparison has not run.",
            ),
            make_check(
                "dependency_resolution",
                "not_run",
                "Direct dependencies have not been resolved.",
            ),
            make_check(
                "compile",
                "not_run",
                "Per-Helper compile validation has not run.",
            ),
            make_check(
                "smoke_execution",
                "not_run",
                "Per-Helper smoke execution has not run.",
            ),
        ]
    )

    framework = runtime_config["source_inputs"]["pytorch"]
    profile = {
        "schema_version": SCHEMA_VERSION,
        "profile_id": declaration.profile_id,
        "revision": 1,
        "metadata": {
            "parent_revision_ref": None,
            "generated_at": collected_at,
            "builder_version": BUILDER_VERSION,
            "content_hash": "",
        },
        "target_environment": {
            "framework": "pytorch",
            "framework_version": str(framework["tag"]).removeprefix("v"),
            "framework_commit": framework["commit"],
            "backend": backend,
            "provider": "flashfuzz_base",
            "provider_revision": provider_revision,
            "configuration_id": configuration_id,
        },
        "callable_interface": {
            "namespace": declaration.namespace,
            "function_name": declaration.function_name,
            "qualified_name": declaration.qualified_name,
            "declaration": declaration.declaration,
            "return": return_record(declaration, annotation),
            "parameters": parameters,
            "required_include": header.name,
            "invocation_template": invocation_template(declaration),
            "evidence_refs": ["ev_helper_header"],
        },
        "capability_contract": capability,
        "build_contract": {
            "compile_definitions": active_macro_records(
                macros, body, annotation
            ),
            "helper_dependencies": [],
            "evidence_refs": [
                "ev_helper_header",
                "ev_build_configuration",
            ],
        },
        "validation": {
            "validation_status": "failed" if issues else "partial",
            "execution_readiness": "blocked" if issues else "unassessed",
            "checks": checks,
            "issues": issues,
        },
        "evidence": evidence_records,
        "review": review_from_annotation(annotation),
    }
    profile["metadata"]["content_hash"] = profile_hash(profile)
    return profile


def find_check(profile: dict[str, Any], kind: str) -> dict[str, Any]:
    matches = [
        item
        for item in profile["validation"]["checks"]
        if item["check_kind"] == kind
    ]
    if len(matches) != 1:
        raise BuildError(f"Expected one {kind} check")
    return matches[0]


def direct_dependency_names(
    body: str | None, declarations: list[Declaration]
) -> list[str]:
    if body is None:
        return []
    opening = body.find("{")
    closing = body.rfind("}")
    if opening < 0 or closing <= opening:
        return []
    body = body[opening + 1 : closing]
    names = []
    for declaration in declarations:
        if re.search(rf"\b{re.escape(declaration.function_name)}\s*\(", body):
            if declaration.function_name not in names:
                names.append(declaration.function_name)
    return sorted(names)


def resolve_dependencies(
    profiles: dict[str, dict[str, Any]],
    declarations: dict[str, Declaration],
    bodies: dict[str, list[str]],
) -> None:
    name_to_keys: dict[str, list[str]] = {}
    for key, declaration in declarations.items():
        name_to_keys.setdefault(declaration.function_name, []).append(key)

    for key, profile in profiles.items():
        declaration = declarations[key]
        body = bodies[key][0] if len(bodies[key]) == 1 else None
        check = find_check(profile, "dependency_resolution")
        if body is None:
            definition_issues = [
                item["issue_id"]
                for item in profile["validation"]["issues"]
                if item["issue_kind"] == "definition_unresolved"
            ]
            check.update(
                status="blocked",
                summary="Dependency analysis requires a resolved implementation body.",
                evidence_refs=[],
                issue_refs=definition_issues,
            )
            continue
        dependencies = []
        issue_refs = []
        evidence_refs = (
            ["ev_helper_implementation"]
            if "ev_helper_implementation"
            in {item["evidence_id"] for item in profile["evidence"]}
            else ["ev_helper_header"]
        )
        for name in direct_dependency_names(body, list(declarations.values())):
            candidates = name_to_keys[name]
            resolved_candidates = [
                candidate for candidate in candidates if candidate in profiles
            ]
            if len(candidates) == 1 and len(resolved_candidates) == 1:
                target_key = resolved_candidates[0]
                dependencies.append(
                    {
                        "profile_id": profiles[target_key]["profile_id"],
                        "qualified_name": declarations[target_key].qualified_name,
                        "resolution_status": "resolved",
                        "evidence_refs": evidence_refs,
                    }
                )
            else:
                issue_id = f"issue_dependency_unresolved_{safe_component(name)}"
                issue_refs.append(issue_id)
                profile["validation"]["issues"].append(
                    make_issue(
                        issue_id,
                        "dependency_unresolved",
                        f"Direct Helper call {name!r} could not resolve uniquely.",
                        ["build_contract.helper_dependencies"],
                        evidence_refs,
                    )
                )
                dependencies.append(
                    {
                        "profile_id": None,
                        "qualified_name": f"{declaration.namespace}::{name}",
                        "resolution_status": "unresolved",
                        "evidence_refs": evidence_refs,
                    }
                )
        profile["build_contract"]["helper_dependencies"] = dependencies
        if issue_refs:
            check.update(
                status="failed",
                summary="One or more direct Helper dependencies are unresolved.",
                evidence_refs=evidence_refs,
                issue_refs=issue_refs,
            )
        else:
            check.update(
                status="passed",
                summary="All direct Helper dependencies are resolved.",
                evidence_refs=evidence_refs,
                issue_refs=[],
            )


def dependency_cycles(
    profiles: dict[str, dict[str, Any]]
) -> list[list[str]]:
    edges = {
        profile["profile_id"]: [
            item["profile_id"]
            for item in profile["build_contract"]["helper_dependencies"]
            if item["resolution_status"] == "resolved"
            and item["profile_id"] in {
                value["profile_id"] for value in profiles.values()
            }
        ]
        for profile in profiles.values()
    }
    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    components: list[list[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in edges[node]:
            if target not in indices:
                visit(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[target])
        if lowlinks[node] == indices[node]:
            component = []
            while True:
                member = stack.pop()
                on_stack.remove(member)
                component.append(member)
                if member == node:
                    break
            if len(component) > 1 or node in edges[node]:
                components.append(sorted(component))

    for node in sorted(edges):
        if node not in indices:
            visit(node)
    return components


def apply_cycle_issues(
    profiles: dict[str, dict[str, Any]], cycles: list[list[str]]
) -> None:
    by_id = {profile["profile_id"]: profile for profile in profiles.values()}
    for number, component in enumerate(cycles, start=1):
        issue_id = f"issue_dependency_cycle_{number:03d}"
        description = "Resolved Helper dependency cycle: " + " -> ".join(component)
        for profile_id in component:
            profile = by_id[profile_id]
            if issue_id not in {
                item["issue_id"] for item in profile["validation"]["issues"]
            }:
                profile["validation"]["issues"].append(
                    make_issue(
                        issue_id,
                        "dependency_cycle",
                        description,
                        ["build_contract.helper_dependencies"],
                        ["ev_helper_implementation"]
                        if any(
                            item["evidence_id"] == "ev_helper_implementation"
                            for item in profile["evidence"]
                        )
                        else ["ev_helper_header"],
                    )
                )
            check = find_check(profile, "dependency_resolution")
            check.update(
                status="failed",
                summary="The resolved Helper dependency graph contains a cycle.",
                issue_refs=sorted(set(check["issue_refs"] + [issue_id])),
            )


def derive_validation_state(profile: dict[str, Any]) -> None:
    statuses = {
        item["status"] for item in profile["validation"]["checks"]
    }
    if "failed" in statuses:
        validation_status = "failed"
    elif statuses & {"not_run", "blocked"}:
        validation_status = "partial"
    else:
        validation_status = "passed"
    blocking = any(
        item["blocking"] for item in profile["validation"]["issues"]
    )
    mandatory_passed = all(
        find_check(profile, kind)["status"] == "passed"
        for kind in MANDATORY_CHECKS
    )
    if blocking:
        readiness = "blocked"
    elif mandatory_passed:
        readiness = "ready"
    else:
        readiness = "unassessed"
    profile["validation"]["validation_status"] = validation_status
    profile["validation"]["execution_readiness"] = readiness
    profile["metadata"]["content_hash"] = profile_hash(profile)


def schema_validator(schema: dict[str, Any]) -> Validator:
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )


def unique_ids(items: list[dict[str, Any]], field: str, label: str) -> set[str]:
    values = [item[field] for item in items]
    if len(values) != len(set(values)):
        raise ProfileValidationError(f"Duplicate {label} identifiers")
    return set(values)


def validate_profile(profile: dict[str, Any], validator: Validator) -> None:
    errors = sorted(
        validator.iter_errors(profile),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        error = errors[0]
        location = ".".join(str(item) for item in error.absolute_path) or "<root>"
        raise ProfileValidationError(f"Schema validation failed at {location}: {error.message}")

    evidence_ids = unique_ids(profile["evidence"], "evidence_id", "Evidence")
    issue_ids = unique_ids(
        profile["validation"]["issues"], "issue_id", "Validation Issue"
    )
    checks = profile["validation"]["checks"]
    unique_ids(checks, "check_id", "Validation Check")
    kinds = [item["check_kind"] for item in checks]
    for required in MANDATORY_CHECKS:
        if kinds.count(required) != 1:
            raise ProfileValidationError(f"Exactly one {required} check is required")

    parameters = profile["callable_interface"]["parameters"]
    parameter_ids = unique_ids(parameters, "parameter_id", "Parameter")
    ordinals = sorted(item["ordinal"] for item in parameters)
    if ordinals != list(range(len(parameters))):
        raise ProfileValidationError("Parameter ordinals must be contiguous from zero")

    constraints = profile["capability_contract"]["domain_constraints"]
    claims = profile["capability_contract"]["behavior_claims"]
    unique_ids(constraints, "constraint_id", "Domain Constraint")
    unique_ids(claims, "claim_id", "Behavior Claim")

    evidence_ref_lists = [
        profile["callable_interface"]["evidence_refs"],
        profile["callable_interface"]["return"]["evidence_refs"],
        profile["capability_contract"]["evidence_refs"],
        profile["build_contract"]["evidence_refs"],
    ]
    evidence_ref_lists.extend(
        item["evidence_refs"] for item in parameters
    )
    evidence_ref_lists.extend(
        item["evidence_refs"] for item in constraints
    )
    evidence_ref_lists.extend(
        item["evidence_refs"] for item in claims
    )
    evidence_ref_lists.extend(
        item["evidence_refs"]
        for item in profile["build_contract"]["compile_definitions"]
    )
    evidence_ref_lists.extend(
        item["evidence_refs"]
        for item in profile["build_contract"]["helper_dependencies"]
    )
    evidence_ref_lists.extend(item["evidence_refs"] for item in checks)
    evidence_ref_lists.extend(
        item["evidence_refs"] for item in profile["validation"]["issues"]
    )
    for references in evidence_ref_lists:
        unknown = set(references) - evidence_ids
        if unknown:
            raise ProfileValidationError(f"Unknown Evidence references: {sorted(unknown)}")

    issue_ref_lists = [item["issue_refs"] for item in checks]
    issue_ref_lists.append(profile["review"]["issue_refs"])
    for references in issue_ref_lists:
        unknown = set(references) - issue_ids
        if unknown:
            raise ProfileValidationError(f"Unknown Validation Issue references: {sorted(unknown)}")

    fuzz = profile["capability_contract"]["fuzz_input_contract"]
    parameter_references = (
        fuzz["data_parameter_refs"] + fuzz["size_parameter_refs"]
    )
    if fuzz["offset_parameter_ref"] is not None:
        parameter_references.append(fuzz["offset_parameter_ref"])
    for constraint in constraints:
        for subject in constraint["subjects"]:
            if subject["entity_kind"] == "parameter":
                parameter_references.append(subject["entity_ref"])
    unknown_parameters = set(parameter_references) - parameter_ids
    if unknown_parameters:
        raise ProfileValidationError(
            f"Unknown Parameter references: {sorted(unknown_parameters)}"
        )

    minimum = fuzz["minimum_bytes"]
    maximum = fuzz["maximum_bytes"]
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ProfileValidationError("minimum_bytes cannot exceed maximum_bytes")
    for constraint in constraints:
        if constraint["relation"] == "range":
            value = constraint["value"]
            lower, upper = value.get("minimum"), value.get("maximum")
            if lower is None and upper is None:
                raise ProfileValidationError("A range must have at least one non-null bound")
            if (
                isinstance(lower, (int, float))
                and isinstance(upper, (int, float))
                and lower > upper
            ):
                raise ProfileValidationError("Range minimum cannot exceed maximum")

    parent = profile["metadata"]["parent_revision_ref"]
    if profile["revision"] == 1 and parent is not None:
        raise ProfileValidationError("Revision 1 cannot have a parent")
    if profile["revision"] > 1:
        if parent is None:
            raise ProfileValidationError("Later revisions require a parent")
        if (
            parent["profile_id"] != profile["profile_id"]
            or parent["revision"] >= profile["revision"]
        ):
            raise ProfileValidationError("Parent must be an earlier revision of this Profile")

    expected_hash = profile_hash(profile)
    if profile["metadata"]["content_hash"] != expected_hash:
        raise ProfileValidationError("metadata.content_hash does not match record content")


def existing_revisions(
    profile_dir: Path, output_slug: str
) -> list[tuple[Path, dict[str, Any]]]:
    records = []
    pattern = f"helper_profile__{output_slug}__r*.json"
    for candidate in sorted(profile_dir.glob(pattern)):
        records.append((candidate, load_json(candidate)))
    return records


def atomic_write_json(path: Path, value: Any) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def materialize(
    profile: dict[str, Any],
    declaration: Declaration,
    output_root: Path,
    validator: Validator,
    dry_run: bool,
) -> tuple[str, Path]:
    environment = profile["target_environment"]
    profile_dir = (
        output_root
        / safe_component(environment["framework"])
        / safe_component(environment["framework_version"])
        / safe_component(environment["backend"])
        / safe_component(environment["provider"])
        / safe_component(environment["configuration_id"])
        / declaration.output_slug
    )
    existing = existing_revisions(profile_dir, declaration.output_slug)
    if existing:
        latest_path, latest = max(existing, key=lambda item: item[1]["revision"])
        validate_profile(latest, validator)
        if latest["profile_id"] != profile["profile_id"]:
            raise BuildError(f"Profile identity collision at {latest_path}")
        if semantic_payload(latest) == semantic_payload(profile):
            return "unchanged", latest_path
        profile["revision"] = latest["revision"] + 1
        profile["metadata"]["parent_revision_ref"] = {
            "profile_id": latest["profile_id"],
            "revision": latest["revision"],
            "content_hash": latest["metadata"]["content_hash"],
        }
        profile["metadata"]["content_hash"] = profile_hash(profile)

    destination = profile_dir / (
        f"helper_profile__{declaration.output_slug}"
        f"__r{profile['revision']:03d}.json"
    )
    validate_profile(profile, validator)
    if destination.exists():
        raise BuildError(f"Refusing to overwrite existing record: {destination}")
    if not dry_run:
        atomic_write_json(destination, profile)
    return ("planned" if dry_run else "created"), destination


def read_selectors(direct: list[str], files: list[Path]) -> list[str]:
    values = list(direct)
    for path in files:
        if not path.is_file():
            raise BuildError(f"Helper list does not exist: {path}")
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.split("#", 1)[0].strip()
            if line:
                values.append(line)
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def select_declarations(
    declarations: list[Declaration],
    selectors: list[str],
    select_all: bool,
) -> list[Declaration]:
    if select_all and selectors:
        raise BuildError("--all cannot be combined with --helper or --helper-file")
    if select_all:
        return declarations
    if not selectors:
        raise BuildError("Provide --all, --helper, or --helper-file")
    selected = []
    for selector in selectors:
        matches = [
            item
            for item in declarations
            if selector in {
                item.qualified_name,
                item.function_name,
                item.annotation_key,
            }
        ]
        if not matches:
            raise BuildError(f"Unknown Helper selector: {selector}")
        if len(matches) > 1:
            raise BuildError(
                f"Ambiguous Helper selector {selector!r}; use an annotation key"
            )
        if matches[0] not in selected:
            selected.append(matches[0])
    return sorted(selected, key=lambda item: item.annotation_key)


def expand_dependency_closure(
    roots: list[Declaration],
    declarations: list[Declaration],
    bodies: dict[str, list[str]],
) -> list[Declaration]:
    """Include uniquely resolvable direct Helper dependencies recursively."""
    by_key = {item.annotation_key: item for item in declarations}
    by_name: dict[str, list[Declaration]] = {}
    for declaration in declarations:
        by_name.setdefault(declaration.function_name, []).append(declaration)

    selected = {item.annotation_key for item in roots}
    pending = list(roots)
    while pending:
        declaration = pending.pop()
        matches = bodies.get(declaration.annotation_key, [])
        body = matches[0] if len(matches) == 1 else None
        for name in direct_dependency_names(body, declarations):
            candidates = by_name.get(name, [])
            if len(candidates) != 1:
                continue
            dependency = candidates[0]
            if dependency.annotation_key not in selected:
                selected.add(dependency.annotation_key)
                pending.append(dependency)
    return sorted((by_key[key] for key in selected), key=lambda item: item.annotation_key)


def discover_output(
    declarations: list[Declaration],
    provider_revision: str,
    configuration_id: str,
    header: Path,
) -> dict[str, Any]:
    return {
        "builder_version": BUILDER_VERSION,
        "provider_revision": provider_revision,
        "configuration_id": configuration_id,
        "header": header.as_posix(),
        "header_sha256": file_hash(header),
        "helper_count": len(declarations),
        "helpers": [
            {
                "annotation_key": item.annotation_key,
                "profile_id": item.profile_id,
                "qualified_name": item.qualified_name,
                "declaration": item.declaration,
            }
            for item in declarations
        ],
    }


def write_summary(
    summary: dict[str, Any],
    requested: Path | None,
    output_root: Path,
    dry_run: bool,
) -> Path | None:
    if requested is not None:
        destination = requested
    elif dry_run:
        return None
    else:
        destination = (
            output_root
            / "_runs"
            / (
                "helper_profile_build_run__"
                + timestamp_slug(summary["generated_at"])
                + ".json"
            )
        )
    atomic_write_json(destination, summary)
    return destination


def validate_files(paths: list[Path], validator: Validator) -> int:
    failures = 0
    for path in paths:
        try:
            validate_profile(load_json(path), validator)
            print(f"[VALID] {path}")
        except (OSError, BuildError) as exc:
            failures += 1
            print(f"[INVALID] {path}: {exc}", file=sys.stderr)
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build deterministic Helper Capability Profiles"
    )
    parser.add_argument("--all", action="store_true", help="Process all public Helpers")
    parser.add_argument("--helper", action="append", default=[], help="Helper name or annotation key; repeatable")
    parser.add_argument("--helper-file", action="append", type=Path, default=[], help="One Helper selector per line")
    parser.add_argument("--discover-only", action="store_true", help="Print declarations and annotation keys without building")
    parser.add_argument("--runtime-config", type=Path, default=DEFAULT_RUNTIME_CONFIG)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--flashfuzz-root", type=Path, default=DEFAULT_FLASHFUZZ_ROOT)
    parser.add_argument("--header", type=Path, default=DEFAULT_HEADER, help="Path relative to FlashFuzz root")
    parser.add_argument("--implementation", type=Path, default=DEFAULT_IMPLEMENTATION, help="Path relative to FlashFuzz root")
    parser.add_argument("--backend", choices=["cpu"], default="cpu")
    parser.add_argument("--configuration-id", default="torch_2_10_cpu_debug_instrumented")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--summary-json", type=Path)
    parser.add_argument("--validate-only", action="append", type=Path, default=[], metavar="PROFILE")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.validate_only:
        try:
            validator = schema_validator(load_json(args.schema))
        except (OSError, BuilderError, jsonschema.SchemaError) as exc:
            print(f"[FATAL] Cannot load Helper Profile Schema: {exc}", file=sys.stderr)
            return 2
        return 1 if validate_files(args.validate_only, validator) else 0

    try:
        runtime_config = load_json(args.runtime_config)
        source = runtime_config["source_inputs"]
        framework_version = str(source["pytorch"]["tag"]).removeprefix("v")
        framework_commit = source["pytorch"]["commit"]
        if not re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", framework_commit):
            raise FatalInputError("Runtime configuration has an invalid PyTorch commit")
        expected_provider_revision = source["flashfuzz"]["base_commit"]
        provider_revision = git_head(args.flashfuzz_root)
        if provider_revision != expected_provider_revision:
            raise FatalInputError(
                "FlashFuzz commit mismatch: "
                f"expected {expected_provider_revision}, found {provider_revision}"
            )
        header = args.flashfuzz_root / args.header
        implementation = args.flashfuzz_root / args.implementation
        declarations = discover_declarations(
            header,
            "pytorch",
            framework_version,
            args.backend,
            "flashfuzz_base",
            args.configuration_id,
        )
        selectors = read_selectors(args.helper, args.helper_file)
        select_all = args.all or (args.discover_only and not selectors)
        roots = select_declarations(declarations, selectors, select_all)
    except (OSError, KeyError, BuilderError) as exc:
        print(f"[FATAL] {exc}", file=sys.stderr)
        return 2

    if args.discover_only:
        print(
            json.dumps(
                discover_output(
                    roots, provider_revision, args.configuration_id, header
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    try:
        validator = schema_validator(load_json(args.schema))
        annotations = load_annotations(
            args.annotations, provider_revision, args.configuration_id
        )
        bodies = definition_bodies(implementation, declarations)
        macros = parse_macros(header)
        selected = expand_dependency_closure(roots, declarations, bodies)
    except (OSError, BuilderError, jsonschema.SchemaError) as exc:
        print(f"[FATAL] {exc}", file=sys.stderr)
        return 2

    collected_at = utc_now()
    outcomes: list[Outcome] = []
    profiles: dict[str, dict[str, Any]] = {}
    selected_by_key = {item.annotation_key: item for item in selected}
    aborted_before_materialization = False

    for declaration in selected:
        annotation = annotations.get(declaration.annotation_key)
        if not isinstance(annotation, dict):
            outcome = Outcome(
                helper=declaration.annotation_key,
                status="failed",
                profile_id=declaration.profile_id,
                error_kind="annotation_missing",
                message="Missing reviewed semantic annotation.",
            )
            outcomes.append(outcome)
            print(
                f"[FAILED] {declaration.annotation_key}: {outcome.message}",
                file=sys.stderr,
            )
            if args.fail_fast:
                aborted_before_materialization = True
                break
            continue
        try:
            profiles[declaration.annotation_key] = build_base_profile(
                declaration,
                annotation,
                bodies[declaration.annotation_key],
                macros,
                runtime_config,
                args.runtime_config,
                args.annotations,
                header,
                implementation,
                provider_revision,
                args.configuration_id,
                args.backend,
                collected_at,
            )
        except (OSError, BuilderError) as exc:
            outcomes.append(
                Outcome(
                    helper=declaration.annotation_key,
                    status="failed",
                    profile_id=declaration.profile_id,
                    error_kind=error_kind(exc),
                    message=str(exc),
                )
            )
            print(f"[FAILED] {declaration.annotation_key}: {exc}", file=sys.stderr)
            if args.fail_fast:
                aborted_before_materialization = True
                break

    if aborted_before_materialization:
        completed = {item.helper for item in outcomes}
        for declaration in selected:
            if declaration.annotation_key not in completed:
                outcomes.append(
                    Outcome(
                        helper=declaration.annotation_key,
                        status="skipped",
                        profile_id=declaration.profile_id,
                        error_kind="fail_fast_abort",
                        message="Skipped because fail-fast aborted before materialization.",
                    )
                )
        profiles.clear()

    if profiles:
        resolve_dependencies(
            profiles,
            {key: selected_by_key[key] for key in profiles},
            bodies,
        )
        apply_cycle_issues(profiles, dependency_cycles(profiles))
        for profile in profiles.values():
            derive_validation_state(profile)

    failed_helpers = {item.helper for item in outcomes}
    materialization_keys = [
        key for key in sorted(profiles) if key not in failed_helpers
    ]

    # Fail-fast performs a complete dry preflight, so ordinary validation errors
    # cannot leave an intentionally partial set of immutable Profile revisions.
    if args.fail_fast and materialization_keys:
        preflight: list[tuple[str, str, Path]] = []
        for key in materialization_keys:
            declaration = selected_by_key[key]
            try:
                status, destination = materialize(
                    profiles[key], declaration, args.output_root, validator, True
                )
                preflight.append((key, status, destination))
            except (OSError, BuilderError) as exc:
                outcomes.append(
                    Outcome(
                        helper=key,
                        status="failed",
                        profile_id=profiles[key]["profile_id"],
                        error_kind=error_kind(exc),
                        message=str(exc),
                    )
                )
                print(f"[FAILED] {key}: {exc}", file=sys.stderr)
                break
        if any(item.status == "failed" for item in outcomes):
            completed = {item.helper for item in outcomes}
            for key in materialization_keys:
                if key not in completed:
                    outcomes.append(
                        Outcome(
                            helper=key,
                            status="skipped",
                            profile_id=profiles[key]["profile_id"],
                            error_kind="fail_fast_abort",
                            message="Skipped because fail-fast preflight failed.",
                        )
                    )
        elif args.dry_run:
            for key, status, destination in preflight:
                outcomes.append(
                    Outcome(
                        helper=key,
                        status=status,
                        profile_id=profiles[key]["profile_id"],
                        path=destination.as_posix(),
                    )
                )
                print(f"[{status.upper()}] {key}: {destination}")
        else:
            for key, _, _ in preflight:
                declaration = selected_by_key[key]
                try:
                    status, destination = materialize(
                        profiles[key], declaration, args.output_root, validator, False
                    )
                    outcomes.append(
                        Outcome(
                            helper=key,
                            status=status,
                            profile_id=profiles[key]["profile_id"],
                            path=destination.as_posix(),
                        )
                    )
                    print(f"[{status.upper()}] {key}: {destination}")
                except (OSError, BuilderError) as exc:
                    outcomes.append(
                        Outcome(
                            helper=key,
                            status="failed",
                            profile_id=profiles[key]["profile_id"],
                            error_kind=error_kind(exc),
                            message=str(exc),
                        )
                    )
                    print(f"[FAILED] {key}: {exc}", file=sys.stderr)
                    break
    elif not args.fail_fast:
        for key in materialization_keys:
            declaration = selected_by_key[key]
            profile = profiles[key]
            try:
                status, destination = materialize(
                    profile, declaration, args.output_root, validator, args.dry_run
                )
                outcomes.append(
                    Outcome(
                        helper=key,
                        status=status,
                        profile_id=profile["profile_id"],
                        path=destination.as_posix(),
                    )
                )
                print(f"[{status.upper()}] {key}: {destination}")
            except (OSError, BuilderError) as exc:
                outcomes.append(
                    Outcome(
                        helper=key,
                        status="failed",
                        profile_id=profile["profile_id"],
                        error_kind=error_kind(exc),
                        message=str(exc),
                    )
                )
                print(f"[FAILED] {key}: {exc}", file=sys.stderr)

    outcomes.sort(key=lambda item: item.helper)
    counts: dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome.status] = counts.get(outcome.status, 0) + 1
    summary = {
        "builder_version": BUILDER_VERSION,
        "schema_version": SCHEMA_VERSION,
        "generated_at": collected_at,
        "dry_run": args.dry_run,
        "fail_fast": args.fail_fast,
        "aborted_before_materialization": aborted_before_materialization,
        "requested_helpers": [item.annotation_key for item in roots],
        "dependency_closure_helpers": [
            item.annotation_key for item in selected
        ],
        "source": {
            "provider_revision": provider_revision,
            "framework_commit": framework_commit,
            "header": header.as_posix(),
            "header_sha256": file_hash(header),
            "implementation": implementation.as_posix(),
            "implementation_sha256": (
                file_hash(implementation) if implementation.is_file() else None
            ),
            "annotation_file": args.annotations.as_posix(),
            "annotation_sha256": file_hash(args.annotations),
        },
        "counts": counts,
        "outcomes": [asdict(item) for item in outcomes],
    }
    try:
        summary_path = write_summary(
            summary, args.summary_json, args.output_root, args.dry_run
        )
    except (OSError, BuilderError) as exc:
        print(f"[FATAL] Cannot write run summary: {exc}", file=sys.stderr)
        return 2
    print("[SUMMARY] " + json.dumps(counts, sort_keys=True))
    if summary_path is not None:
        print(f"[SUMMARY_FILE] {summary_path}")
    return 1 if counts.get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
