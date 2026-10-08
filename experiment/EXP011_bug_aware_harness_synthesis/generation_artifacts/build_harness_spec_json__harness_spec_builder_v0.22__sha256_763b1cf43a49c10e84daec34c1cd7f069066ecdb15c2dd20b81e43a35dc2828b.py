#!/usr/bin/env python3
"""Build and validate initial or feedback-derived HarnessSpec records.

Initial synthesis obtains only the semantic plan from an LLM. Feedback
application is deterministic and changes only Branch budget allocation; this
Builder never lowers Strategy Primitives or emits C++ code.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path
from typing import Any

try:
    import requests
    import yaml
    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry, Resource
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency; install environment/python-control-requirements.txt"
    ) from exc


BUILDER_VERSION = "harness_spec_builder_v0.22"
SCHEMA_VERSION = "2.2"
CONTRACT_VERSION = "2.5"
RULES_VERSION = "2.5"
DEFAULT_MODEL = "deepseek-v4-pro"
DEFAULT_API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MAX_PROMPT_CHARS = 75_000
ROOT = Path("experiment/EXP011_bug_aware_harness_synthesis")
DEFAULTS = {
    "config": ROOT / "config.yaml",
    "record_schema": ROOT / "schemas/harness_spec_record.schema.json",
    "record_schema_core": ROOT / "schemas/harness_spec_record_core__v2_2.schema.json",
    "legacy_record_schema_v2_1": ROOT / "schemas/legacy/harness_spec_v2_1/harness_spec_record.schema.json",
    "legacy_record_schema_v2_0": ROOT / "schemas/legacy/harness_spec_v2_0/harness_spec_record.schema.json",
    "generation_trace_schema": ROOT / "schemas/harness_spec_generation_trace.schema.json",
    "review_schema": ROOT / "schemas/harness_spec_review_record.schema.json",
    "api_schema": ROOT / "schemas/api_profile_record.schema.json",
    "helper_schema": ROOT / "schemas/helper_profile_record.schema.json",
    "contract": ROOT / "schemas/harness_spec_synthesis_contract.json",
    "rules": ROOT / "schemas/knowledge_to_harness_spec_rules.md",
    "api_profiles": ROOT / "api_profiles",
    "helper_profiles": ROOT / "helper_profiles",
    "knowledge_root": Path("experiment/EXP006_historical_bug_pattern_dataset/knowledge_base/v3"),
    "knowledge_review_ledger": Path(
        "experiment/EXP006_historical_bug_pattern_dataset/quality/knowledge_review_ledger.jsonl"
    ),
    "output_root": ROOT / "harness_specs",
    "generation_artifacts": ROOT / "generation_artifacts",
    "generation_traces": ROOT / "generation_traces",
}


class BuildError(RuntimeError):
    """Expected condition preventing safe record materialization."""


class InputError(BuildError):
    """A source artifact is missing, ambiguous, or incompatible."""


class LLMError(BuildError):
    """An LLM request or response cannot safely be used."""


class ValidationError(BuildError):
    """A plan or assembled record violates a declared invariant."""


@dataclass
class Outcome:
    target_api: str
    mode: str
    status: str
    attempts: int = 0
    output_path: str | None = None
    diagnostics_path: str | None = None
    message: str = ""


@dataclass(frozen=True)
class HelperSelection:
    """One mode-independent Helper selection for a version-pinned API Profile."""

    available: list[dict[str, Any]]
    detailed: list[dict[str, Any]]
    dependencies: list[dict[str, Any]]
    fallback: list[dict[str, Any]]
    selection_hash: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise InputError(f"Required file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise InputError(f"Invalid JSON in {path}: {exc}") from exc


def load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise InputError(f"Required file does not exist: {path}") from exc


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def safe_component(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    value = re.sub(r"_+", "_", value).strip("._-").lower()
    if not value:
        raise InputError("Path component cannot be empty")
    return value


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must be an object")
    return value


def require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValidationError(f"{label} must be an array")
    return value


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} must be a non-empty string")
    return value.strip()


def reject_unknown_keys(value: dict[str, Any], allowed: set[str], label: str) -> None:
    extras = sorted(set(value) - allowed)
    if extras:
        raise ValidationError(f"{label} has unsupported keys: {extras}")


def json_response(text: str) -> dict[str, Any]:
    text = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.I)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return require_object(json.loads(text), "LLM response")
    except json.JSONDecodeError as exc:
        raise LLMError(f"LLM response is not valid JSON: {exc}") from exc


def read_records(root: Path, schema: dict[str, Any], label: str) -> list[dict[str, Any]]:
    if not root.exists():
        raise InputError(f"Source directory does not exist: {root}")
    filename_pattern = {
        "API Profile": "api_profile__*__r*.json",
        "Helper Profile": "helper_profile__*__r*.json",
    }.get(label, "*.json")
    paths = sorted(
        path
        for path in root.rglob(filename_pattern)
        if path.is_file() and "_runs" not in path.parts
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    records: list[dict[str, Any]] = []
    for path in paths:
        record = load_json(path)
        errors = sorted(validator.iter_errors(record), key=lambda item: item.json_path)
        if errors:
            first = errors[0]
            raise InputError(f"Invalid {label} {path}: {first.json_path}: {first.message}")
        records.append(record)
    return records


def read_helper_profile_set(
    manifest_path: Path, schema: dict[str, Any]
) -> list[dict[str, Any]]:
    """Load only the exact Helper Profile revisions pinned by a set manifest."""

    manifest = require_object(load_json(manifest_path), "Helper Profile set manifest")
    if manifest.get("manifest_format_version") != "1.0":
        raise InputError("Unsupported Helper Profile set manifest format")
    entries = require_list(manifest.get("profiles"), "Helper Profile set profiles")
    if not entries:
        raise InputError("Helper Profile set manifest must pin at least one profile")

    records: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for index, value in enumerate(entries):
        entry = require_object(value, f"Helper Profile set profiles[{index}]")
        profile_id = require_string(entry.get("profile_id"), "profile_id")
        revision = entry.get("revision")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise InputError(f"Invalid Helper Profile revision for {profile_id}")
        key = (profile_id, revision)
        if key in seen:
            raise InputError(f"Duplicate Helper Profile set entry: {key}")
        seen.add(key)

        file_ref = require_object(entry.get("record_file_ref"), "record_file_ref")
        relative_path = require_string(file_ref.get("relative_path"), "relative_path")
        declared_hash = require_string(file_ref.get("content_hash"), "content_hash")
        path = Path(relative_path)
        if path.is_absolute() or ".." in path.parts:
            raise InputError(f"Unsafe Helper Profile path: {relative_path}")
        if not path.is_file():
            raise InputError(f"Pinned Helper Profile does not exist: {path}")
        actual_hash = file_hash(path)
        if actual_hash != declared_hash:
            raise InputError(
                f"Pinned Helper Profile hash mismatch for {path}: "
                f"{actual_hash} != {declared_hash}"
            )
        record = validate_profile_record(load_json(path), schema, f"Helper Profile {path}")
        if record.get("profile_id") != profile_id or record.get("revision") != revision:
            raise InputError(f"Helper Profile identity mismatch for {path}")
        records.append(record)
    return records


def profile_reference(profile: dict[str, Any]) -> dict[str, Any]:
    try:
        return {
            "profile_id": profile["profile_id"],
            "revision": profile["revision"],
            "content_hash": profile["metadata"]["content_hash"],
        }
    except (KeyError, TypeError) as exc:
        raise InputError("Profile is missing identity or content hash") from exc


def knowledge_reference(knowledge: dict[str, Any]) -> dict[str, Any]:
    try:
        return {
            "knowledge_id": knowledge["metadata"]["knowledge_id"],
            "schema_version": knowledge["schema_version"],
            "content_hash": canonical_hash(knowledge),
        }
    except (KeyError, TypeError) as exc:
        raise InputError("Knowledge is missing identity or schema version") from exc


def validate_profile_record(profile: Any, schema: dict[str, Any], label: str) -> dict[str, Any]:
    record = require_object(profile, label)
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(record),
        key=lambda item: item.json_path,
    )
    if errors:
        first = errors[0]
        raise InputError(f"Invalid {label}: {first.json_path}: {first.message}")
    return record


def validate_harness_record(
    value: Any,
    active_schema: dict[str, Any],
    label: str,
    args: argparse.Namespace | None = None,
) -> dict[str, Any]:
    """Validate each HarnessSpec revision against its own versioned Schema."""

    record = require_object(value, label)
    version = record.get("schema_version")
    schema_paths = {
        "2.0": getattr(
            args, "legacy_record_schema_v2_0", DEFAULTS["legacy_record_schema_v2_0"]
        ),
        "2.1": getattr(
            args, "legacy_record_schema_v2_1", DEFAULTS["legacy_record_schema_v2_1"]
        ),
    }
    if version == SCHEMA_VERSION:
        schema = active_schema
    elif version in schema_paths:
        schema = load_json(schema_paths[version])
    else:
        raise InputError(f"Invalid {label}: unsupported schema_version {version!r}")
    core_path = getattr(
        args, "record_schema_core", DEFAULTS["record_schema_core"]
    )
    core = require_object(load_json(core_path), "HarnessSpec core Schema")
    registry = Registry().with_resource(
        require_string(core.get("$id"), "HarnessSpec core Schema $id"),
        Resource.from_contents(core),
    )
    errors = sorted(
        Draft202012Validator(
            schema, registry=registry, format_checker=FormatChecker()
        ).iter_errors(record),
        key=lambda item: item.json_path,
    )
    if errors:
        first = errors[0]
        raise InputError(f"Invalid {label}: {first.json_path}: {first.message}")
    return record


def select_api_profile(args: argparse.Namespace, api_schema: dict[str, Any]) -> dict[str, Any]:
    if args.api_profile is not None:
        profile = validate_profile_record(load_json(args.api_profile), api_schema, "explicit API Profile")
        target = profile["target"]
        if target["framework"] != args.framework:
            raise InputError("Explicit API Profile framework does not match --framework")
        if args.target_api is not None and target["python_api"] != args.target_api:
            raise InputError("Explicit API Profile target does not match --target-api")
        args.target_api = target["python_api"]
    else:
        if args.target_api is None:
            raise InputError("Either --api-profile or --target-api is required")
        matches = []
        for candidate in read_records(args.api_profiles, api_schema, "API Profile"):
            target = candidate["target"]
            if target["framework"] == args.framework and target["python_api"] == args.target_api:
                matches.append(candidate)
        if len(matches) != 1:
            raise InputError(
                f"Expected exactly one API Profile for {args.framework}:{args.target_api}; "
                f"found {len(matches)}. Use --api-profile to select a revision explicitly."
            )
        profile = matches[0]
    if profile["target_binding"]["status"] != "resolved":
        raise InputError("Selected API Profile target binding is not resolved")
    if profile["validation"]["validation_status"] != "passed":
        raise InputError("Selected API Profile validation_status is not passed")
    if profile["validation"]["execution_readiness"] != "ready":
        raise InputError("Selected API Profile execution_readiness is not ready")
    if profile["review"]["review_status"] != "approved":
        raise InputError("Selected API Profile review_status is not approved")
    return profile


def api_helper_signals(api: dict[str, Any]) -> dict[str, Any]:
    """Derive only deterministic Helper-relevance signals from an API Profile."""

    contract = api["python_contract"]
    parameters = contract["parameters"]
    returns = contract["returns"]
    input_types = {
        normalized
        for parameter in parameters
        for normalized in parameter["normalized_types"]
    }
    input_roles = {parameter["semantic_role"] for parameter in parameters}
    return_types = {
        normalized
        for result in returns
        for normalized in result["normalized_types"]
    }
    return_roles = {result["semantic_role"] for result in returns}
    domain_kinds = {item["domain_kind"] for item in contract["documented_domains"]}
    constraint_kinds = {
        item["constraint_kind"] for item in api["documented_constraints"]
    }
    binding_types = {
        item["schema_type"].lower()
        for item in api["target_binding"]["binding_parameters"]
    }
    tensor_types = {"tensor", "tensor_sequence", "index_tensor"}
    tensor_roles = {
        "input_tensor",
        "other_tensor",
        "index_tensor",
        "output_tensor",
        "bias_tensor",
    }
    tensor_parameter_count = sum(
        bool(tensor_types.intersection(parameter["normalized_types"]))
        or parameter["semantic_role"] in tensor_roles
        for parameter in parameters
    )
    effective_tensor_count = tensor_parameter_count + int(
        api["target"]["callable_kind"] == "tensor_method"
    )
    has_tensor_input = (
        api["target"]["callable_kind"] == "tensor_method"
        or bool(input_types.intersection(tensor_types))
        or bool(input_roles.intersection(tensor_roles))
        or any("tensor" in value for value in binding_types)
    )
    return {
        "input_types": input_types,
        "input_roles": input_roles,
        "return_types": return_types,
        "return_roles": return_roles,
        "domain_kinds": domain_kinds,
        "constraint_kinds": constraint_kinds,
        "binding_types": binding_types,
        "tensor_parameter_count": tensor_parameter_count,
        "effective_tensor_count": effective_tensor_count,
        "has_tensor_input": has_tensor_input,
        "has_tensor_output": bool(return_types.intersection(tensor_types))
        or bool(return_roles.intersection({"result_tensor", "result_tensor_sequence"})),
        "has_dtype_input": "dtype" in input_types
        or "dtype" in input_roles
        or "dtype" in domain_kinds
        or any("scalartype" in value for value in binding_types),
        "has_shape_input": "shape" in input_types
        or "shape" in input_roles
        or any(
            value in {"int[]", "symint[]"}
            or "intarrayref" in value
            or "symintarrayref" in value
            for value in binding_types
        ),
        "has_layout_signal": bool(
            {"layout", "memory_format"}.intersection(input_types)
            or {"layout", "memory_format"}.intersection(input_roles)
            or {"layout", "memory_format"}.intersection(domain_kinds)
            or {"layout", "memory_format"}.intersection(constraint_kinds)
        ),
        "has_cross_parameter_signal": effective_tensor_count >= 2
        or "cross_parameter" in constraint_kinds,
    }


def helper_matches_api(profile: dict[str, Any], signals: dict[str, Any]) -> bool:
    """Return whether a Helper deserves a detailed prompt view for this API."""

    name = profile["callable_interface"]["qualified_name"]
    kind = profile["capability_contract"]["capability_kind"]
    return_role = profile["callable_interface"]["return"]["semantic_role"]

    if name == "fuzzer_utils::createTensor":
        return signals["has_tensor_input"]
    if name == "fuzzer_utils::parseDataType":
        return signals["has_dtype_input"]
    if name == "fuzzer_utils::parseShape":
        return signals["has_shape_input"]
    if name in {"fuzzer_utils::parseRank", "fuzzer_utils::parseTensorData"}:
        return False
    if name == "fuzzer_utils::compareTensors":
        return signals["has_tensor_output"]

    if kind == "tensor_constructor":
        return signals["has_tensor_input"]
    if kind == "tensor_transformer":
        return signals["has_tensor_input"] and signals["has_layout_signal"]
    if kind == "relation_enforcer":
        return signals["has_cross_parameter_signal"]
    if kind == "oracle":
        return signals["has_tensor_output"]
    if kind not in {"byte_decoder", "argument_generator"}:
        return False

    role_matches = {
        "dtype": {"dtype"},
        "shape": {"shape"},
        "tensor": {"tensor", "tensor_sequence", "index_tensor"},
        "boolean": {"boolean"},
        "string": {"string"},
    }
    return bool(role_matches.get(return_role, set()).intersection(signals["input_types"]))


def select_helper_profiles(
    api: dict[str, Any], profiles: list[dict[str, Any]]
) -> HelperSelection:
    """Apply strict eligibility, broad recall, and dependency-complete detail."""

    target = api["target"]
    available: list[dict[str, Any]] = []
    for helper in profiles:
        environment = helper["target_environment"]
        if environment["framework"] != target["framework"]:
            continue
        if environment["framework_commit"] != target["framework_commit"]:
            continue
        if environment["backend"] not in target["backend_scope"]:
            continue
        if helper["validation"]["execution_readiness"] != "ready":
            continue
        if helper["review"]["review_status"] != "approved":
            continue
        available.append(helper)
    available.sort(key=lambda item: (item["profile_id"], item["revision"]))
    if not available:
        raise InputError(
            "No ready and approved Helper Profile matches the API Profile environment"
        )

    by_id: dict[str, dict[str, Any]] = {}
    for helper in available:
        profile_id = helper["profile_id"]
        if profile_id in by_id:
            raise InputError(
                f"Multiple eligible revisions found for Helper Profile {profile_id}; "
                "provide one active revision before synthesis"
            )
        by_id[profile_id] = helper

    signals = api_helper_signals(api)
    detailed_ids = {
        helper["profile_id"]
        for helper in available
        if helper_matches_api(helper, signals)
    }
    dependency_ids: set[str] = set()
    expanded_ids: set[str] = set()
    pending = list(sorted(detailed_ids))
    while pending:
        profile_id = pending.pop()
        if profile_id in expanded_ids:
            continue
        expanded_ids.add(profile_id)
        helper = by_id[profile_id]
        for dependency in helper["build_contract"]["helper_dependencies"]:
            if dependency["resolution_status"] != "resolved" or not dependency["profile_id"]:
                raise InputError(
                    f"Detailed Helper {profile_id} has an unresolved dependency: "
                    f"{dependency['qualified_name']}"
                )
            dependency_id = dependency["profile_id"]
            if dependency_id not in by_id:
                raise InputError(
                    f"Detailed Helper {profile_id} depends on unavailable Helper "
                    f"{dependency_id}"
                )
            if dependency_id not in detailed_ids:
                dependency_ids.add(dependency_id)
            if dependency_id not in expanded_ids:
                pending.append(dependency_id)

    detailed = [item for item in available if item["profile_id"] in detailed_ids]
    dependencies = [
        item for item in available if item["profile_id"] in dependency_ids
    ]
    fallback = [
        item
        for item in available
        if item["profile_id"] not in detailed_ids
        and item["profile_id"] not in dependency_ids
    ]

    def presentation(profile_id: str) -> str:
        if profile_id in detailed_ids:
            return "detailed"
        if profile_id in dependency_ids:
            return "dependency"
        return "fallback"

    hash_payload = {
        "api_profile_ref": profile_reference(api),
        "helper_presentations": [
            {
                "profile_ref": profile_reference(item),
                "presentation": presentation(item["profile_id"]),
            }
            for item in available
        ],
    }
    return HelperSelection(
        available=available,
        detailed=detailed,
        dependencies=dependencies,
        fallback=fallback,
        selection_hash=canonical_hash(hash_payload),
    )


def select_helpers(
    args: argparse.Namespace, helper_schema: dict[str, Any], api: dict[str, Any]
) -> HelperSelection:
    if args.helper_profile_set is not None:
        return select_helper_profiles(
            api, read_helper_profile_set(args.helper_profile_set, helper_schema)
        )
    return select_helper_profiles(
        api, read_records(args.helper_profiles, helper_schema, "Helper Profile")
    )


def load_approved_knowledge_reviews(path: Path) -> set[tuple[str, str]]:
    if not path.is_file():
        raise InputError(f"Knowledge review ledger does not exist: {path}")
    approved: set[tuple[str, str]] = set()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            entry = require_object(json.loads(raw_line), f"Knowledge review ledger line {line_number}")
        except ValueError as exc:
            raise InputError(f"Invalid Knowledge review ledger line {line_number}: {exc}") from exc
        if entry.get("decision") != "approved":
            continue
        knowledge_id = require_string(entry.get("knowledge_id"), f"Knowledge review ledger line {line_number}.knowledge_id")
        content_hash = require_string(entry.get("knowledge_hash"), f"Knowledge review ledger line {line_number}.knowledge_hash")
        approved.add((knowledge_id, content_hash.removeprefix("sha256:")))
    return approved


def validate_knowledge_batch(
    records: list[dict[str, Any]], approved_reviews: set[tuple[str, str]]
) -> list[dict[str, Any]]:
    """Do not silently combine independently versioned extraction contracts."""
    ids = [knowledge_reference(item)["knowledge_id"] for item in records]
    if len(ids) != len(set(ids)):
        raise InputError("Duplicate eligible Knowledge ID")
    batches = set()
    for item in records:
        reference = knowledge_reference(item)
        if reference["schema_version"] != "3.0":
            raise InputError("HarnessSpec v2.2 accepts only Knowledge schema 3.0")
        if (reference["knowledge_id"], reference["content_hash"]) not in approved_reviews:
            raise InputError(
                "Knowledge is not approved with its exact content hash: "
                f"{reference['knowledge_id']}"
            )
        derivation = require_object(item.get("derivation_information"), "Knowledge derivation_information")
        batches.add(tuple(require_string(derivation.get(key), f"Knowledge {key}")
                          for key in ("mapping_version", "prompt_version")))
    if len(batches) > 1:
        raise InputError("Mixed Knowledge extraction versions; select one explicit batch")
    return sorted(records, key=lambda item: item["metadata"]["knowledge_id"])


def select_bound_knowledge(
    bindings: list[dict[str, Any]], framework: str, target_api: str,
    approved_reviews: set[tuple[str, str]],
) -> list[dict[str, Any]]:
    """Read exactly the pinned files, verifying raw bytes before constructing prompts."""
    records = []
    for binding in bindings:
        if not isinstance(binding, dict) or set(binding) != {"knowledge_id", "schema_version", "file_ref"}:
            raise InputError("Knowledge binding requires knowledge_id, schema_version and file_ref")
        ref = binding["file_ref"]
        if not isinstance(ref, dict) or set(ref) != {"relative_path", "content_hash"}:
            raise InputError("Invalid Knowledge file_ref")
        relative = ref["relative_path"]
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise InputError("Knowledge file_ref requires a repository-relative path")
        path = Path(__file__).resolve().parents[3] / relative
        try:
            payload = path.read_bytes()
            if hashlib.sha256(payload).hexdigest() != ref["content_hash"]:
                raise InputError(f"Knowledge file hash mismatch: {path}")
            record = require_object(json.loads(payload), "Knowledge")
        except (OSError, ValueError) as exc:
            raise InputError(f"Cannot read pinned Knowledge {path}: {exc}") from exc
        identity = knowledge_reference(record)
        if identity["knowledge_id"] != binding["knowledge_id"] or identity["schema_version"] != binding["schema_version"] or identity["schema_version"] != "3.0":
            raise InputError(f"Knowledge identity/version mismatch: {path}")
        scope = require_object(record.get("scope"), "Knowledge scope")
        if scope.get("framework") != framework or scope.get("target_api") != target_api:
            raise InputError(f"Pinned Knowledge does not directly support {framework}/{target_api}: {path}")
        records.append(record)
    return validate_knowledge_batch(records, approved_reviews)


def select_knowledge(
    root: Path, framework: str, target_api: str,
    approved_reviews: set[tuple[str, str]],
) -> list[dict[str, Any]]:
    if not root.exists():
        raise InputError(f"Knowledge root does not exist: {root}")
    result: list[dict[str, Any]] = []
    ids: set[str] = set()
    for path in sorted(item for item in root.rglob("*.json") if item.is_file()):
        record = load_json(path)
        if record.get("schema_version") != "3.0":
            continue
        scope = record.get("scope")
        if not isinstance(scope, dict) or scope.get("framework") != framework:
            continue
        if scope.get("target_api") != target_api:
            continue
        ref = knowledge_reference(record)
        if ref["knowledge_id"] in ids:
            raise InputError(f"Duplicate eligible Knowledge ID: {ref['knowledge_id']}")
        ids.add(ref["knowledge_id"])
        result.append(record)
    return validate_knowledge_batch(result, approved_reviews)


def prompt_semantic_view(value: Any) -> Any:
    """Remove nested evidence IDs that are not valid HarnessSpec source IDs."""

    if isinstance(value, list):
        return [prompt_semantic_view(item) for item in value]
    if isinstance(value, dict):
        return {
            key: prompt_semantic_view(item)
            for key, item in value.items()
            if key != "evidence_refs"
        }
    return value


def api_view(profile: dict[str, Any]) -> dict[str, Any]:
    target = profile["target"]
    return {
        "profile_id": profile["profile_id"],
        "revision": profile["revision"],
        "target": {key: target[key] for key in ("framework", "framework_version", "backend_scope", "python_api", "callable_kind")},
        "python_contract": prompt_semantic_view(profile["python_contract"]),
        "target_binding": prompt_semantic_view(profile["target_binding"]),
        "documented_constraints": prompt_semantic_view(profile["documented_constraints"]),
    }


def detailed_helper_view(profile: dict[str, Any]) -> dict[str, Any]:
    capability = profile["capability_contract"]
    return {
        "profile_id": profile["profile_id"],
        "revision": profile["revision"],
        "qualified_name": profile["callable_interface"]["qualified_name"],
        "capability_kind": capability["capability_kind"],
        "summary": capability["summary"],
        "fuzz_input_contract": capability["fuzz_input_contract"],
        "domain_constraints": capability["domain_constraints"],
        "behavior_claims": capability["behavior_claims"],
        "side_effects": capability["side_effects"],
        "determinism": capability["determinism"],
    }


def fallback_helper_view(profile: dict[str, Any]) -> dict[str, Any]:
    capability = profile["capability_contract"]
    return {
        "profile_id": profile["profile_id"],
        "revision": profile["revision"],
        "qualified_name": profile["callable_interface"]["qualified_name"],
        "capability_kind": capability["capability_kind"],
        "summary": capability["summary"],
    }


def knowledge_view(record: dict[str, Any]) -> dict[str, Any]:
    guidance = require_object(record.get("exploration_guidance"), "Knowledge exploration_guidance")

    def indexed_items(field: str) -> list[dict[str, Any]]:
        return [
            {
                "source_path": f"/exploration_guidance/{field}/{index}",
                **prompt_semantic_view(require_object(item, f"exploration_guidance.{field}[{index}]")),
            }
            for index, item in enumerate(require_list(guidance.get(field), f"exploration_guidance.{field}"))
        ]

    return {
        "knowledge_id": record["metadata"]["knowledge_id"],
        "canonical_name": record["metadata"].get("canonical_name"),
        "scope": record["scope"],
        "learned_hypothesis": {
            "source_path": "/learned_hypothesis",
            **prompt_semantic_view(record["learned_hypothesis"]),
        },
        "exploration_guidance": {
            "historical_anchors": indexed_items("historical_anchors"),
            "variation_opportunities": indexed_items("variation_opportunities"),
            "observation_candidates": indexed_items("observation_candidates"),
        },
        "limitations": [
            {
                "source_path": f"/learned_hypothesis/limitations/{index}",
                "statement": prompt_semantic_view(item),
            }
            for index, item in enumerate(
                require_list(
                    record["learned_hypothesis"].get("limitations", []),
                    "learned_hypothesis.limitations",
                )
            )
        ],
    }


def compact_errors(errors: list[str], limit: int = 12) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for error in errors:
        normalized = re.sub(r"\s+", " ", error).strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(normalized)
    return unique[:limit]


def build_prompt(
    contract: dict[str, Any],
    rules: str,
    api: dict[str, Any],
    helpers: HelperSelection,
    knowledge: list[dict[str, Any]],
    mode: str,
    repair: list[str],
    max_chars: int,
    review_context: dict[str, Any] | None = None,
    previous_response_text: str | None = None,
) -> str:
    bundle = {
        "spec_mode": mode,
        "api_profile": api_view(api),
        "helper_selection": {
            "selection_hash": helpers.selection_hash,
            "detailed_profiles": [
                detailed_helper_view(item) for item in helpers.detailed
            ],
            "dependency_profiles": [
                detailed_helper_view(item) for item in helpers.dependencies
            ],
            "fallback_profile_index": [
                fallback_helper_view(item) for item in helpers.fallback
            ],
        },
        "eligible_knowledge": [knowledge_view(item) for item in knowledge],
    }
    correction = ""
    if repair:
        correction = (
            "Previous response errors; return a complete corrected replacement:\n- "
            + "\n- ".join(compact_errors(repair))
        )
    mode_constraints = ""
    if mode == "controlled_baseline":
        mode_constraints = (
            "In controlled_baseline mode, knowledge_decisions must be [], and "
            "exploration_plan.branches must contain exactly one branch whose "
            "branch_kind is default. That branch uses source_knowledge_ids: [], "
            "grouping_summary: null, exploration_goal_source_refs: [], and no "
            "Knowledge source references."
        )
    else:
        mode_constraints = (
            "In bug-aware mode, do not emit a default branch. Return only "
            "knowledge_directed branches; the Builder injects the exact validated "
            "canonical Baseline default before semantic validation."
        )
    effective_review_context = copy.deepcopy(review_context)
    if previous_response_text is not None and effective_review_context is not None:
        # The immediately preceding candidate is the most useful repair anchor.
        # Avoid sending the parent semantic payload twice on retry.
        effective_review_context.pop("parent_semantic_plan", None)
    sections = {
        "instructions": (
            "Return only one JSON object for the semantic portion of a HarnessSpec.\n"
            "Do not emit Markdown, explanations, source code, Helper calls, Strategy "
            "Primitives, or Builder-owned fields. Every source reference must use the "
            "supplied API Profile profile_id or eligible Knowledge knowledge_id together "
            "with an exact source_path from the compact view; never use nested evidence IDs. "
            "Helper Profiles are capability context and must never be "
            "cited as semantic evidence. Every eligible Helper remains available. The "
            "fallback index is for capability discovery only; do not infer unstated "
            "constraints or behavior from its summaries. Fixed crash, signal, sanitizer, "
            "timeout, hang, and OOM monitoring belongs to the Runner and must not be emitted "
            "as branch-local checks."
        ),
        "mode_constraints": mode_constraints,
        "contract": json.dumps(
            contract, ensure_ascii=False, separators=(",", ":")
        ),
        "rules": rules,
        "input_bundle": json.dumps(
            bundle, ensure_ascii=False, separators=(",", ":")
        ),
        "review_regeneration_context": (
            "This is an evidence-bounded review regeneration. Treat each finding "
            "only as a mismatch to correct. Reconstruct the complete semantic plan "
            "from the same frozen API, Helper, and Knowledge inputs. Do not infer a "
            "replacement value, Predicate, Shape, dtype, budget, or expected outcome "
            "from the finding text.\n"
            + json.dumps(effective_review_context, ensure_ascii=False, separators=(",", ":"))
            if effective_review_context is not None
            else ""
        ),
        "previous_candidate": (
            "This is the exact previous candidate. Preserve unaffected semantics and "
            "return a complete corrected replacement; do not treat the candidate as "
            "evidence.\n" + previous_response_text
            if previous_response_text is not None
            else ""
        ),
        "correction": correction,
    }
    prompt = "\n\n".join(
        f"=== {name.replace('_', ' ').title()} ===\n{text}"
        for name, text in sections.items()
        if text
    )
    if len(prompt) > max_chars:
        sizes = {name: len(text) for name, text in sections.items()}
        raise InputError(
            f"Prompt is {len(prompt)} characters, exceeding --max-prompt-chars={max_chars}; "
            f"section_sizes={json.dumps(sizes, sort_keys=True)}"
        )
    return prompt


def call_llm(prompt: str, api_key: str, model: str, api_url: str) -> str:
    try:
        response = requests.post(
            api_url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0},
            timeout=180,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
        raise LLMError(f"LLM request failed: {exc}") from exc


def normalize_id_collection(
    items: list[Any], id_field: str, prefix: str, label: str
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for index, value in enumerate(items, start=1):
        item = require_object(value, f"{label}[{index - 1}]")
        old_id = require_string(item.get(id_field), f"{label}[{index - 1}].{id_field}")
        if old_id in mapping:
            raise ValidationError(f"Duplicate local identifier in {label}: {old_id}")
        new_id = f"{prefix}_{index:03d}"
        mapping[old_id] = new_id
        item[id_field] = new_id
    return mapping


def normalize_predicate_description(value: Any, label: str) -> None:
    """Materialize the Schema-required nullable Predicate description.

    Omitting a nullable description and spelling it as JSON null carry the same
    semantic information.  The Builder canonicalizes only that omission; it
    never invents explanatory text or changes Predicate arguments.
    """

    predicate = require_object(value, label)
    predicate.setdefault("description", None)


def api_observation_subject_ids(api: dict[str, Any]) -> set[str]:
    python_contract = require_object(api.get("python_contract"), "api.python_contract")
    subject_ids = {
        require_string(item.get("parameter_id"), "api parameter_id")
        for item in require_list(
            python_contract.get("parameters"), "api.python_contract.parameters"
        )
        if isinstance(item, dict)
    }
    subject_ids.update(
        require_string(item.get("return_id"), "api return_id")
        for item in require_list(
            python_contract.get("returns"), "api.python_contract.returns"
        )
        if isinstance(item, dict)
    )
    subject_ids.update(
        {
            "context.backend",
            "context.device",
            "context.autograd",
            "context.execution",
            "context.resource",
        }
    )
    return subject_ids


def api_return_subject_ids(api: dict[str, Any]) -> set[str]:
    python_contract = require_object(api.get("python_contract"), "api.python_contract")
    return {
        require_string(item.get("return_id"), "api return_id")
        for item in require_list(
            python_contract.get("returns"), "api.python_contract.returns"
        )
        if isinstance(item, dict)
    }


def predicate_subject_refs(predicate: dict[str, Any]) -> set[str]:
    arguments = require_object(predicate.get("arguments"), "predicate.arguments")
    return {
        value
        for key, value in arguments.items()
        if key in {"subject_ref", "left_subject_ref", "right_subject_ref"}
        and isinstance(value, str)
    }


def validate_subject_availability(
    subject_refs: set[str], observe_at: list[str], api: dict[str, Any], label: str
) -> None:
    if "before_target_api_call" in observe_at:
        unavailable = sorted(subject_refs & api_return_subject_ids(api))
        if unavailable:
            raise ValidationError(
                f"{label} cannot observe target return subjects before the API call: "
                f"{unavailable}"
            )


# HarnessSpec v2 semantic validation.  The legacy v1.8 helpers above remain only so
# archived revisions can still be read; these later definitions are the active path.
def normalize_plan(
    plan: dict[str, Any], contract: dict[str, Any], knowledge: list[dict[str, Any]]
) -> dict[str, Any]:
    expected = set(contract["response_requirements"]["root_object_keys"])
    reject_unknown_keys(plan, expected, "LLM response")
    if set(plan) != expected:
        raise ValidationError(f"LLM response must contain exactly {sorted(expected)}")
    decisions = require_list(
        require_object(plan.get("knowledge_plan"), "knowledge_plan").get("knowledge_decisions"),
        "knowledge_decisions",
    )
    expected_ids = {item["metadata"]["knowledge_id"] for item in knowledge}
    returned_ids = [
        require_string(
            require_object(value, f"knowledge_decisions[{index}]").get("knowledge_id"),
            f"knowledge_decisions[{index}].knowledge_id",
        )
        for index, value in enumerate(decisions)
    ]
    if set(returned_ids) != expected_ids or len(returned_ids) != len(set(returned_ids)):
        raise ValidationError("Exactly one decision is required for every eligible Knowledge record")
    normalize_v2_local_identifiers(plan)
    return plan


def normalize_v2_local_identifiers(plan: dict[str, Any]) -> None:
    branches = require_list(
        require_object(plan.get("exploration_plan"), "exploration_plan").get("branches"),
        "branches",
    )
    branch_mapping: dict[str, str] = {}
    knowledge_index = 0
    default_seen = False
    for index, value in enumerate(branches):
        branch = require_object(value, f"branches[{index}]")
        old_id = require_string(branch.get("branch_id"), f"branches[{index}].branch_id")
        if old_id in branch_mapping:
            raise ValidationError(f"Duplicate branch identifier: {old_id}")
        kind = branch.get("branch_kind")
        if kind == "default":
            if default_seen:
                raise ValidationError("Exactly one default branch is required")
            default_seen = True
            new_id = "br_default"
        elif kind == "knowledge_directed":
            knowledge_index += 1
            new_id = f"br_knowledge_{knowledge_index:03d}"
        else:
            raise ValidationError(f"Unsupported branch_kind in branches[{index}]: {kind!r}")
        branch_mapping[old_id] = new_id
        branch["branch_id"] = new_id

    global_constraints = require_list(
        plan["validity_constraints"].get("global_constraints"), "global_constraints"
    )
    normalize_id_collection(
        global_constraints,
        "constraint_id", "gc", "global_constraints",
    )
    for index, value in enumerate(global_constraints):
        constraint = require_object(value, f"global_constraints[{index}]")
        normalize_predicate_description(
            constraint.get("predicate"), f"global_constraints[{index}].predicate"
        )
    element_mappings: dict[tuple[str, str, str], str] = {}
    for index, value in enumerate(branches):
        branch = require_object(value, f"branches[{index}]")
        old_branch_id = next(
            old for old, new in branch_mapping.items() if new == branch["branch_id"]
        )
        prefix = branch["branch_id"]
        branch_constraints = require_list(
            branch.get("branch_constraints"), f"branches[{index}].branch_constraints"
        )
        constraint_mapping = normalize_id_collection(
            branch_constraints,
            "constraint_id", f"bc_{prefix}", f"branches[{index}].branch_constraints",
        )
        for old_id, new_id in constraint_mapping.items():
            element_mappings[(old_branch_id, "branch_constraint", old_id)] = new_id
        for item_index, item in enumerate(branch_constraints):
            constraint = require_object(
                item, f"branches[{index}].branch_constraints[{item_index}]"
            )
            normalize_predicate_description(
                constraint.get("predicate"),
                f"branches[{index}].branch_constraints[{item_index}].predicate",
            )
        target_conditions = require_list(
            branch.get("target_conditions"), f"branches[{index}].target_conditions"
        )
        condition_mapping = normalize_id_collection(
            target_conditions,
            "condition_id", f"tc_{prefix}", f"branches[{index}].target_conditions",
        )
        for old_id, new_id in condition_mapping.items():
            element_mappings[(old_branch_id, "target_condition", old_id)] = new_id
        for item_index, item in enumerate(target_conditions):
            condition = require_object(
                item, f"branches[{index}].target_conditions[{item_index}]"
            )
            normalize_predicate_description(
                condition.get("predicate"),
                f"branches[{index}].target_conditions[{item_index}].predicate",
            )
        observation_mapping = normalize_id_collection(
            require_list(branch.get("behavior_observations"), f"branches[{index}].behavior_observations"),
            "observation_id", f"obs_{prefix}", f"branches[{index}].behavior_observations",
        )
        for old_id, new_id in observation_mapping.items():
            element_mappings[(old_branch_id, "behavior_observation", old_id)] = new_id
        behavior_checks = require_list(
            branch.get("behavior_checks"), f"branches[{index}].behavior_checks"
        )
        check_mapping = normalize_id_collection(
            behavior_checks,
            "check_id", f"chk_{prefix}", f"branches[{index}].behavior_checks",
        )
        for old_id, new_id in check_mapping.items():
            element_mappings[(old_branch_id, "behavior_check", old_id)] = new_id
        for item_index, item in enumerate(behavior_checks):
            check = require_object(
                item, f"branches[{index}].behavior_checks[{item_index}]"
            )
            preconditions = require_list(
                check.get("preconditions"),
                f"branches[{index}].behavior_checks[{item_index}].preconditions",
            )
            for pre_index, predicate in enumerate(preconditions):
                normalize_predicate_description(
                    predicate,
                    f"branches[{index}].behavior_checks[{item_index}].preconditions[{pre_index}]",
                )
            normalize_predicate_description(
                check.get("expected_predicate"),
                f"branches[{index}].behavior_checks[{item_index}].expected_predicate",
            )

    decisions = require_list(
        plan["knowledge_plan"].get("knowledge_decisions"), "knowledge_decisions"
    )
    for index, value in enumerate(decisions):
        decision = require_object(value, f"knowledge_decisions[{index}]")
        rewritten: list[str] = []
        for branch_id in require_list(
            decision.get("branch_ids"), f"knowledge_decisions[{index}].branch_ids"
        ):
            branch_id = require_string(
                branch_id, f"knowledge_decisions[{index}].branch_ids[]"
            )
            if branch_id not in branch_mapping:
                raise ValidationError(
                    f"Knowledge decision references unknown branch ID: {branch_id}"
                )
            rewritten.append(branch_mapping[branch_id])
        decision["branch_ids"] = rewritten
        mappings = require_list(
            decision.get("component_mappings"),
            f"knowledge_decisions[{index}].component_mappings",
        )
        for mapping_index, mapping_value in enumerate(mappings):
            mapping = require_object(
                mapping_value,
                f"knowledge_decisions[{index}].component_mappings[{mapping_index}]",
            )
            mapping.setdefault("represented_scope", None)
            mapping.setdefault("deferred_scope", None)
            mapping.setdefault("decision_summary", None)
            refs = require_list(
                mapping.get("spec_element_refs"),
                f"knowledge_decisions[{index}].component_mappings[{mapping_index}].spec_element_refs",
            )
            for ref_index, ref_value in enumerate(refs):
                ref = require_object(
                    ref_value,
                    f"knowledge_decisions[{index}].component_mappings[{mapping_index}].spec_element_refs[{ref_index}]",
                )
                old_branch_id = require_string(ref.get("branch_id"), "spec_element_ref.branch_id")
                if old_branch_id not in branch_mapping:
                    raise ValidationError(
                        f"Component mapping references unknown branch ID: {old_branch_id}"
                    )
                ref["branch_id"] = branch_mapping[old_branch_id]
                element_type = require_string(
                    ref.get("element_type"), "spec_element_ref.element_type"
                )
                element_id = ref.get("element_id")
                if element_type == "exploration_goal":
                    # exploration_goal has no separate local element identifier.
                    # Canonicalize harmless model output instead of spending an
                    # LLM retry on a mechanically determined field.
                    ref["element_id"] = None
                    continue
                old_element_id = require_string(
                    element_id, "spec_element_ref.element_id"
                )
                key = (old_branch_id, element_type, old_element_id)
                if key not in element_mappings:
                    raise ValidationError(
                        "Component mapping references an unknown or mismatched branch element"
                    )
                ref["element_id"] = element_mappings[key]


def v2_knowledge_source_ids(items: list[Any], label: str) -> set[str]:
    result: set[str] = set()
    for index, value in enumerate(items):
        item = require_object(value, f"{label}[{index}]")
        for ref_index, ref_value in enumerate(require_list(item.get("source_refs"), f"{label}[{index}].source_refs")):
            ref = require_object(ref_value, f"{label}[{index}].source_refs[{ref_index}]")
            if ref.get("source_type") == "knowledge":
                result.add(require_string(ref.get("source_id"), "knowledge source_id"))
    return result


def validate_v2_predicate(
    predicate_value: Any, api: dict[str, Any], contract: dict[str, Any], label: str
) -> str:
    predicate = require_object(predicate_value, label)
    reject_unknown_keys(predicate, {"predicate_id", "arguments", "description"}, label)
    if set(predicate) != {"predicate_id", "arguments", "description"}:
        raise ValidationError(
            f"{label} must contain predicate_id, arguments, and description"
        )
    if predicate["description"] is not None:
        require_string(predicate["description"], f"{label}.description")
    predicate_id = require_string(predicate.get("predicate_id"), f"{label}.predicate_id")
    if predicate_id in {"no_abnormal_termination", "no_sanitizer_violation"}:
        raise ValidationError(
            "Fixed crash/signal/sanitizer monitoring belongs to the Runner, not a branch predicate"
        )
    contracts = require_object(contract.get("predicate_contracts"), "predicate_contracts")
    if predicate_id not in contracts:
        raise ValidationError(f"Unsupported predicate_id: {predicate_id}")
    shape = require_object(contracts[predicate_id], f"predicate_contracts.{predicate_id}")
    arguments = require_object(predicate.get("arguments"), f"{label}.arguments")
    required = set(require_list(shape.get("required_arguments"), f"{predicate_id}.required_arguments"))
    if set(arguments) != required:
        raise ValidationError(f"{label}.arguments must contain exactly {sorted(required)}")

    subject_ids = api_observation_subject_ids(api)
    execution_ids = subject_ids | {"target_call", "target_call_1", "target_call_2"}
    for key in ("subject_ref", "left_subject_ref", "right_subject_ref"):
        if key in arguments and require_string(arguments[key], f"{label}.{key}") not in subject_ids:
            raise ValidationError(f"{label}.{key} does not resolve in the API Profile")
    if "execution_ref" in arguments and require_string(arguments["execution_ref"], f"{label}.execution_ref") not in execution_ids:
        raise ValidationError(f"{label}.execution_ref does not resolve")

    property_pattern = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")
    property_subject_pairs: list[tuple[str, str]] = []
    property_to_subject = {
        "property_ref": "subject_ref",
        "left_property_ref": "left_subject_ref",
        "right_property_ref": "right_subject_ref",
    }
    for key in ("property_ref", "left_property_ref", "right_property_ref"):
        if key in arguments:
            value = require_string(arguments[key], f"{label}.{key}")
            if not property_pattern.fullmatch(value):
                raise ValidationError(f"{label}.{key} is not a normalized property path")
            subject_key = property_to_subject[key]
            if subject_key in arguments:
                property_subject_pairs.append((arguments[subject_key], value))
    tensor_property_roots = {
        "numel", "rank", "shape", "dtype", "layout", "stride",
        "requires_grad", "is_contiguous",
    }
    for subject_ref, property_ref in property_subject_pairs:
        if subject_ref.startswith("context.") and property_ref.split(".", 1)[0] in tensor_property_roots:
            raise ValidationError(
                f"{label} cannot apply tensor property {property_ref!r} to {subject_ref}"
            )
    for vocabulary_key, argument_key in (
        ("operators", "operator"), ("relations", "relation"), ("transitions", "transition")
    ):
        if argument_key in arguments:
            allowed = set(require_list(shape.get(vocabulary_key), f"{predicate_id}.{vocabulary_key}"))
            if arguments[argument_key] not in allowed:
                raise ValidationError(f"{label}.{argument_key} is not allowed for {predicate_id}")
    if predicate_id == "set_membership" and not require_list(arguments["values"], f"{label}.values"):
        raise ValidationError(f"{label}.values must not be empty")
    if predicate_id == "range_constraint":
        if arguments["lower_bound"] is None and arguments["upper_bound"] is None:
            raise ValidationError(f"{label} requires at least one range bound")
        if not isinstance(arguments["lower_inclusive"], bool) or not isinstance(arguments["upper_inclusive"], bool):
            raise ValidationError(f"{label} range inclusivity flags must be booleans")
        bounds = [arguments["lower_bound"], arguments["upper_bound"]]
        if any(
            value is not None
            and (not isinstance(value, (int, float)) or isinstance(value, bool))
            for value in bounds
        ):
            raise ValidationError(f"{label} range bounds must be numeric or null")
        lower, upper = bounds
        if lower is not None and upper is not None:
            if lower > upper:
                raise ValidationError(f"{label} range lower_bound exceeds upper_bound")
            if lower == upper and not (
                arguments["lower_inclusive"] and arguments["upper_inclusive"]
            ):
                raise ValidationError(f"{label} range is empty at equal exclusive bounds")
    property_ref = arguments.get("property_ref")
    if property_ref in {"numel", "rank"} and "value" in arguments:
        value = arguments["value"]
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValidationError(f"{label}.{property_ref} comparison requires an integer value")
    if predicate_id == "resource_bound":
        value = arguments["value"]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValidationError(f"{label} resource bound value must be numeric")
    return predicate_id


def validate_v2_subject_refs(values: Any, api: dict[str, Any], label: str) -> None:
    refs = require_list(values, label)
    normalized = [require_string(value, f"{label}[{index}]") for index, value in enumerate(refs)]
    if not normalized or len(normalized) != len(set(normalized)):
        raise ValidationError(f"{label} must contain distinct subject references")
    unknown = sorted(set(normalized) - api_observation_subject_ids(api))
    if unknown:
        raise ValidationError(f"{label} does not resolve in the API Profile: {unknown}")


def validate_v2_behavior_observation(
    value: Any, api: dict[str, Any], label: str,
) -> None:
    """Validate one record-only observation and its execution subject."""

    observation = require_object(value, label)
    subject_refs = require_list(observation.get("subject_refs"), f"{label}.subject_refs")
    validate_v2_subject_refs(subject_refs, api, f"{label}.subject_refs")
    require_string(observation.get("description"), f"{label}.description")
    observe_at = observation.get("observe_at")
    validate_subject_availability(
        set(subject_refs), [observe_at], api, f"{label}.subject_refs"
    )
    if (
        observe_at == "on_target_api_termination"
        and "context.execution" not in subject_refs
    ):
        raise ValidationError(
            f"{label}.subject_refs must include context.execution when "
            "observe_at is on_target_api_termination"
        )


def knowledge_component_paths(record: dict[str, Any]) -> set[str]:
    """Return the complete v3 component inventory that requires a mapping decision."""

    paths = {"/learned_hypothesis"}
    hypothesis = require_object(record.get("learned_hypothesis"), "learned_hypothesis")
    for index, _ in enumerate(
        require_list(hypothesis.get("limitations", []), "learned_hypothesis.limitations")
    ):
        paths.add(f"/learned_hypothesis/limitations/{index}")
    guidance = require_object(record.get("exploration_guidance"), "exploration_guidance")
    for field in (
        "historical_anchors",
        "variation_opportunities",
        "observation_candidates",
    ):
        for index, _ in enumerate(require_list(guidance.get(field), f"exploration_guidance.{field}")):
            paths.add(f"/exploration_guidance/{field}/{index}")
    return paths


def element_source_refs(branch: dict[str, Any], element_type: str, element_id: Any) -> list[Any]:
    if element_type == "exploration_goal":
        if element_id is not None:
            raise ValidationError("exploration_goal component references require element_id null")
        return require_list(
            branch.get("exploration_goal_source_refs"),
            f"{branch['branch_id']}.exploration_goal_source_refs",
        )
    field_and_id = {
        "branch_constraint": ("branch_constraints", "constraint_id"),
        "target_condition": ("target_conditions", "condition_id"),
        "behavior_observation": ("behavior_observations", "observation_id"),
        "behavior_check": ("behavior_checks", "check_id"),
    }
    if element_type not in field_and_id:
        raise ValidationError(f"Unsupported component mapping element_type: {element_type}")
    field, id_field = field_and_id[element_type]
    element_id = require_string(element_id, "spec_element_ref.element_id")
    matches = [item for item in branch[field] if item.get(id_field) == element_id]
    if len(matches) != 1:
        raise ValidationError(
            f"Component mapping does not resolve exactly one {element_type}: {element_id}"
        )
    return require_list(matches[0].get("source_refs"), f"{element_type}.source_refs")


def validate_plan(
    plan: dict[str, Any], mode: str, knowledge: list[dict[str, Any]],
    api: dict[str, Any], contract: dict[str, Any],
) -> None:
    knowledge_plan = require_object(plan.get("knowledge_plan"), "knowledge_plan")
    reject_unknown_keys(knowledge_plan, {"knowledge_decisions"}, "knowledge_plan")
    validity = require_object(plan.get("validity_constraints"), "validity_constraints")
    reject_unknown_keys(validity, {"global_constraints"}, "validity_constraints")
    exploration = require_object(plan.get("exploration_plan"), "exploration_plan")
    reject_unknown_keys(exploration, {"branches"}, "exploration_plan")
    decisions = require_list(knowledge_plan.get("knowledge_decisions"), "knowledge_decisions")
    branches = require_list(exploration.get("branches"), "branches")
    if not branches:
        raise ValidationError("At least one exploration branch is required")
    if mode == "controlled_baseline" and decisions:
        raise ValidationError("Controlled baseline cannot use Knowledge decisions")
    if mode != "controlled_baseline" and len(decisions) != len(knowledge):
        raise ValidationError("Bug-aware mode must decide every supplied Knowledge record")

    knowledge_ids = {item["metadata"]["knowledge_id"] for item in knowledge}
    decisions_by_id: dict[str, dict[str, Any]] = {}
    component_mappings_by_id: dict[str, list[dict[str, Any]]] = {}
    included: set[str] = set()
    for index, value in enumerate(decisions):
        decision = require_object(value, f"knowledge_decisions[{index}]")
        reject_unknown_keys(
            decision, {"knowledge_id", "disposition", "branch_ids", "decision_summary", "component_mappings"},
            f"knowledge_decisions[{index}]",
        )
        knowledge_id = require_string(decision.get("knowledge_id"), f"knowledge_decisions[{index}].knowledge_id")
        if knowledge_id not in knowledge_ids or knowledge_id in decisions_by_id:
            raise ValidationError(f"Unknown or duplicate Knowledge decision: {knowledge_id}")
        disposition = decision.get("disposition")
        if disposition not in contract["allowed_values"]["disposition"]:
            raise ValidationError(f"Invalid Knowledge disposition: {disposition}")
        branch_ids = require_list(decision.get("branch_ids"), f"knowledge_decisions[{index}].branch_ids")
        if disposition == "included":
            if not branch_ids:
                raise ValidationError("Included Knowledge must name at least one branch")
            included.add(knowledge_id)
        elif branch_ids:
            raise ValidationError("Deferred Knowledge must not name a branch")
        require_string(decision.get("decision_summary"), f"knowledge_decisions[{index}].decision_summary")
        mappings = require_list(
            decision.get("component_mappings"),
            f"knowledge_decisions[{index}].component_mappings",
        )
        expected_paths = knowledge_component_paths(
            next(item for item in knowledge if item["metadata"]["knowledge_id"] == knowledge_id)
        )
        returned_paths: list[str] = []
        normalized_mappings: list[dict[str, Any]] = []
        for mapping_index, mapping_value in enumerate(mappings):
            mapping = require_object(
                mapping_value,
                f"knowledge_decisions[{index}].component_mappings[{mapping_index}]",
            )
            reject_unknown_keys(
                mapping,
                {"source_path", "mapping_status", "spec_element_refs", "represented_scope", "deferred_scope", "decision_summary"},
                f"knowledge_decisions[{index}].component_mappings[{mapping_index}]",
            )
            source_path = require_string(mapping.get("source_path"), "component_mapping.source_path")
            returned_paths.append(source_path)
            status = mapping.get("mapping_status")
            if status not in contract["allowed_values"]["knowledge_mapping_status"]:
                raise ValidationError(
                    f"knowledge_decisions[{index}].component_mappings[{mapping_index}] "
                    f"has invalid mapping_status: {status}"
                )
            mapping_label = (
                f"knowledge_decisions[{index}].component_mappings[{mapping_index}]"
            )
            refs = require_list(
                mapping.get("spec_element_refs"), f"{mapping_label}.spec_element_refs"
            )
            represented_scope = mapping.get("represented_scope")
            deferred_scope = mapping.get("deferred_scope")
            decision_summary = mapping.get("decision_summary")
            if status == "represented":
                if (
                    not refs
                    or represented_scope is not None
                    or deferred_scope is not None
                    or decision_summary is not None
                ):
                    raise ValidationError(
                        f"{mapping_label} represented mapping requires exact refs and "
                        "null represented_scope, deferred_scope, and decision_summary"
                    )
            elif status == "partially_represented":
                if not refs:
                    raise ValidationError(
                        f"{mapping_label} partially_represented mapping requires refs"
                    )
                require_string(represented_scope, f"{mapping_label}.represented_scope")
                require_string(deferred_scope, f"{mapping_label}.deferred_scope")
                require_string(decision_summary, f"{mapping_label}.decision_summary")
            else:
                if refs or represented_scope is not None or deferred_scope is None:
                    raise ValidationError(
                        f"{mapping_label} deferred mapping requires no refs, null "
                        "represented_scope, and non-null deferred_scope"
                    )
                require_string(deferred_scope, f"{mapping_label}.deferred_scope")
                require_string(decision_summary, f"{mapping_label}.decision_summary")
            if disposition == "deferred" and status != "deferred":
                raise ValidationError("A deferred Knowledge decision cannot claim represented components")
            normalized_mappings.append(mapping)
        if set(returned_paths) != expected_paths or len(returned_paths) != len(set(returned_paths)):
            raise ValidationError(
                f"Knowledge component mappings must cover the exact component inventory for {knowledge_id}"
            )
        component_mappings_by_id[knowledge_id] = normalized_mappings
        decisions_by_id[knowledge_id] = decision

    global_constraints = require_list(validity.get("global_constraints"), "global_constraints")
    if v2_knowledge_source_ids(global_constraints, "global_constraints"):
        raise ValidationError("Historical Knowledge must not be promoted to global validity constraints")

    defaults = 0
    branch_by_id: dict[str, dict[str, Any]] = {}
    cited_in_structured_semantics: set[str] = set()
    for index, value in enumerate(branches):
        branch = require_object(value, f"branches[{index}]")
        branch_id = require_string(branch.get("branch_id"), f"branches[{index}].branch_id")
        if branch_id in branch_by_id:
            raise ValidationError(f"Duplicate branch ID: {branch_id}")
        branch_by_id[branch_id] = branch
        kind = branch.get("branch_kind")
        defaults += kind == "default"
        if kind not in contract["allowed_values"]["branch_kind"]:
            raise ValidationError(f"Unsupported branch kind: {kind}")
        validity_intent = branch.get("input_validity_intent")
        if validity_intent not in contract["allowed_values"]["input_validity_intent"]:
            raise ValidationError(f"Invalid input_validity_intent in {branch_id}")
        basis = require_object(branch.get("input_validity_basis"), f"{branch_id}.input_validity_basis")
        reject_unknown_keys(basis, {"basis_kind", "source_refs", "summary"}, f"{branch_id}.input_validity_basis")
        basis_kind = basis.get("basis_kind")
        if basis_kind not in contract["allowed_values"]["input_validity_basis_kind"]:
            raise ValidationError(f"Invalid input_validity_basis in {branch_id}")
        basis_refs = require_list(basis.get("source_refs"), f"{branch_id}.input_validity_basis.source_refs")
        require_string(basis.get("summary"), f"{branch_id}.input_validity_basis.summary")
        if (validity_intent == "contract_boundary_unresolved") != (basis_kind == "unresolved"):
            raise ValidationError(
                f"{branch_id} unresolved validity intent and basis_kind must be paired"
            )
        if basis_kind == "api_contract" and not basis_refs:
            raise ValidationError(f"{branch_id} evidence-backed validity basis requires source_refs")
        if basis_kind == "api_contract" and any(
            require_object(ref, "validity source_ref").get("source_type") != "api_profile"
            for ref in basis_refs
        ):
            raise ValidationError(f"{branch_id} api_contract basis may cite only API Profile evidence")
        if basis_kind == "canonical_baseline_definition" and basis_refs:
            raise ValidationError(
                f"{branch_id} canonical_baseline_definition must not cite source_refs"
            )
        source_ids = set(require_list(branch.get("source_knowledge_ids"), f"{branch_id}.source_knowledge_ids"))
        goal_source_refs = require_list(
            branch.get("exploration_goal_source_refs"),
            f"{branch_id}.exploration_goal_source_refs",
        )
        narrative_items: list[Any] = [
            {"source_refs": goal_source_refs},
            {"source_refs": basis_refs},
        ]
        structured_items: list[Any] = []
        for field in ("branch_constraints", "target_conditions", "behavior_observations", "behavior_checks"):
            structured_items.extend(
                require_list(branch.get(field), f"{branch_id}.{field}")
            )
        semantic_items = narrative_items + structured_items
        semantic_ids = v2_knowledge_source_ids(
            semantic_items, f"{branch_id}.semantic_items"
        )
        structured_ids = v2_knowledge_source_ids(
            structured_items, f"{branch_id}.structured_items"
        )
        if kind == "default":
            violations: list[str] = []
            if source_ids:
                violations.append(f"{branch_id}.source_knowledge_ids must be []")
            if semantic_ids:
                violations.append(
                    f"{branch_id}.semantic_items must not cite Knowledge"
                )
            if branch.get("grouping_summary") is not None:
                violations.append(f"{branch_id}.grouping_summary must be JSON null")
            if goal_source_refs:
                violations.append(f"{branch_id}.exploration_goal_source_refs must be []")
            if basis_kind != "canonical_baseline_definition":
                violations.append(
                    f"{branch_id}.input_validity_basis must use canonical_baseline_definition"
                )
            if violations:
                raise ValidationError(
                    "Default branch violates Knowledge isolation: "
                    + "; ".join(violations)
                )
        else:
            if basis_kind == "canonical_baseline_definition":
                raise ValidationError(
                    f"{branch_id} Knowledge branch cannot use canonical_baseline_definition"
                )
            if not source_ids or source_ids != semantic_ids or not source_ids.issubset(included):
                raise ValidationError(
                    "Knowledge branch source IDs must exactly equal its included branch-local contributions"
                )
            require_string(branch.get("grouping_summary"), f"{branch_id}.grouping_summary")
            if not goal_source_refs:
                raise ValidationError(
                    f"{branch_id}.exploration_goal_source_refs must cite its goal sources"
                )
            actionable_items = (
                require_list(branch.get("target_conditions"), f"{branch_id}.target_conditions")
                + require_list(branch.get("behavior_observations"), f"{branch_id}.behavior_observations")
                + require_list(branch.get("behavior_checks"), f"{branch_id}.behavior_checks")
            )
            if not actionable_items:
                raise ValidationError(
                    f"{branch_id} requires a target condition, behavior observation, or behavior check"
                )
            cited_in_structured_semantics.update(structured_ids)
        require_string(branch.get("exploration_goal"), f"{branch_id}.exploration_goal")

        for item_index, item in enumerate(require_list(branch.get("branch_constraints"), f"{branch_id}.branch_constraints")):
            constraint = require_object(item, f"{branch_id}.branch_constraints[{item_index}]")
            validate_v2_subject_refs(constraint.get("subjects"), api, f"{branch_id}.branch_constraints[{item_index}].subjects")
            validate_v2_predicate(constraint.get("predicate"), api, contract, f"{branch_id}.branch_constraints[{item_index}].predicate")
        for item_index, item in enumerate(require_list(branch.get("target_conditions"), f"{branch_id}.target_conditions")):
            condition = require_object(item, f"{branch_id}.target_conditions[{item_index}]")
            role = condition.get("role")
            if role not in contract["allowed_values"]["target_condition_role"]:
                raise ValidationError(f"Invalid target condition role in {branch_id}")
            predicate_id = validate_v2_predicate(condition.get("predicate"), api, contract, f"{branch_id}.target_conditions[{item_index}].predicate")
            observe_at = require_list(condition.get("observe_at"), f"{branch_id}.target_conditions[{item_index}].observe_at")
            validate_subject_availability(
                predicate_subject_refs(require_object(condition.get("predicate"), "predicate")),
                observe_at,
                api,
                f"{branch_id}.target_conditions[{item_index}]",
            )
            if predicate_id == "state_transition":
                if set(observe_at) != {"before_target_api_call", "after_target_api_call"} or len(observe_at) != 2:
                    raise ValidationError("state_transition condition requires before and after observations")
            elif len(observe_at) != 1:
                raise ValidationError("Non-transition target condition requires one observation point")
        for item_index, item in enumerate(require_list(branch.get("behavior_observations"), f"{branch_id}.behavior_observations")):
            validate_v2_behavior_observation(
                item, api, f"{branch_id}.behavior_observations[{item_index}]"
            )
        for item_index, item in enumerate(require_list(branch.get("behavior_checks"), f"{branch_id}.behavior_checks")):
            check = require_object(item, f"{branch_id}.behavior_checks[{item_index}]")
            validate_v2_subject_refs(check.get("subject_refs"), api, f"{branch_id}.behavior_checks[{item_index}].subject_refs")
            for pre_index, predicate in enumerate(require_list(check.get("preconditions"), f"{branch_id}.behavior_checks[{item_index}].preconditions")):
                validate_v2_predicate(predicate, api, contract, f"{branch_id}.behavior_checks[{item_index}].preconditions[{pre_index}]")
            expected_predicate_id = validate_v2_predicate(
                check.get("expected_predicate"), api, contract,
                f"{branch_id}.behavior_checks[{item_index}].expected_predicate",
            )
            if check.get("requirement_level") not in contract["allowed_values"]["requirement_level"]:
                raise ValidationError(f"Invalid behavior check requirement level in {branch_id}")

    if defaults != 1:
        raise ValidationError("Exactly one default branch is required")
    if mode == "controlled_baseline" and len(branches) != 1:
        raise ValidationError("Controlled baseline must contain only the default branch")
    for knowledge_id in included:
        decision_branch_ids = set(decisions_by_id[knowledge_id]["branch_ids"])
        actual_branch_ids = {
            branch_id
            for branch_id, branch in branch_by_id.items()
            if knowledge_id in branch.get("source_knowledge_ids", [])
        }
        if decision_branch_ids != actual_branch_ids:
            raise ValidationError(
                "Knowledge decision branch_ids must exactly match branches that use "
                f"the Knowledge: {knowledge_id}"
            )
        if not decision_branch_ids.issubset(branch_by_id):
            raise ValidationError(f"Knowledge decision names an unknown branch: {knowledge_id}")
        for branch_id in decision_branch_ids:
            branch = branch_by_id[branch_id]
            if branch.get("branch_kind") != "knowledge_directed" or knowledge_id not in branch.get("source_knowledge_ids", []):
                raise ValidationError(f"Knowledge decision and branch membership disagree: {knowledge_id}")
        for mapping in component_mappings_by_id[knowledge_id]:
            source_path = mapping["source_path"]
            for ref_value in mapping["spec_element_refs"]:
                ref = require_object(ref_value, "spec_element_ref")
                reject_unknown_keys(
                    ref, {"branch_id", "element_type", "element_id"}, "spec_element_ref"
                )
                branch_id = require_string(ref.get("branch_id"), "spec_element_ref.branch_id")
                if branch_id not in decision_branch_ids:
                    raise ValidationError(
                        "Component mapping branch must belong to its Knowledge decision"
                    )
                branch = branch_by_id.get(branch_id)
                if branch is None:
                    raise ValidationError("Component mapping references an unknown branch")
                source_refs = element_source_refs(
                    branch, ref.get("element_type"), ref.get("element_id")
                )
                if not any(
                    item.get("source_type") == "knowledge"
                    and item.get("source_id") == knowledge_id
                    and item.get("source_path") == source_path
                    for item in source_refs
                    if isinstance(item, dict)
                ):
                    raise ValidationError(
                        "Component mapping element must cite the same Knowledge source_path"
                    )
        mappings_by_path = {
            mapping["source_path"]: mapping
            for mapping in component_mappings_by_id[knowledge_id]
        }
        structured_fields = (
            ("branch_constraint", "branch_constraints", "constraint_id"),
            ("target_condition", "target_conditions", "condition_id"),
            ("behavior_observation", "behavior_observations", "observation_id"),
            ("behavior_check", "behavior_checks", "check_id"),
        )
        for branch_id in actual_branch_ids:
            branch = branch_by_id[branch_id]
            for element_type, field, id_field in structured_fields:
                for element in branch[field]:
                    element_id = element[id_field]
                    for source_ref in element["source_refs"]:
                        if (
                            source_ref.get("source_type") != "knowledge"
                            or source_ref.get("source_id") != knowledge_id
                        ):
                            continue
                        source_path = source_ref.get("source_path")
                        mapping = mappings_by_path.get(source_path)
                        expected_ref = {
                            "branch_id": branch_id,
                            "element_type": element_type,
                            "element_id": element_id,
                        }
                        if mapping is None or expected_ref not in mapping["spec_element_refs"]:
                            raise ValidationError(
                                "Every structured Knowledge citation must have a matching "
                                f"non-deferred component reference: {knowledge_id}{source_path}"
                            )
    if included != cited_in_structured_semantics:
        raise ValidationError(
            "Included Knowledge lacks an exact structured contribution: "
            f"{sorted(included - cited_in_structured_semantics)}"
        )


def semantic_response_schema_issues(
    response: dict[str, Any], contract: dict[str, Any]
) -> list[str]:
    """Return every local-shape error from the Contract-owned response Schema."""

    schema = require_object(
        contract.get("semantic_response_schema"), "semantic_response_schema"
    )
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:  # pragma: no cover - guarded by tests and startup
        raise InputError(f"Contract semantic_response_schema is invalid: {exc}") from exc
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{error.json_path}: {error.message}"
        for error in sorted(validator.iter_errors(response), key=lambda item: item.json_path)
    ]


def compact_source_references(value: Any) -> Any:
    """Project final-record Source References back to the LLM response shape."""

    if isinstance(value, list):
        return [compact_source_references(item) for item in value]
    if not isinstance(value, dict):
        return copy.deepcopy(value)
    expanded_keys = {
        "source_type", "source_id", "source_version", "content_hash", "source_path"
    }
    if set(value) == expanded_keys:
        return {
            "source_type": value["source_type"],
            "source_id": value["source_id"],
            "source_path": value["source_path"],
        }
    return {key: compact_source_references(item) for key, item in value.items()}


def semantic_plan_from_record(record: dict[str, Any]) -> dict[str, Any]:
    """Project one final record into the semantic response form used for repair."""

    plan = compact_source_references({
        "knowledge_plan": record["knowledge_plan"],
        "validity_constraints": record["validity_constraints"],
        "exploration_plan": {
            "branches": record["exploration_plan"]["branches"],
        },
    })
    for decision in plan["knowledge_plan"]["knowledge_decisions"]:
        decision["knowledge_id"] = decision.pop("knowledge_ref")["knowledge_id"]
    branches = plan["exploration_plan"]["branches"]
    for branch in branches:
        branch.pop("budget_share", None)
    if record["identity"]["spec_mode"] != "controlled_baseline":
        plan["exploration_plan"]["branches"] = [
            branch for branch in branches if branch["branch_kind"] != "default"
        ]
    return plan


def inject_canonical_default_plan(
    plan: dict[str, Any], canonical: dict[str, Any]
) -> None:
    """Inject the exact Baseline default into a bug-aware semantic candidate."""

    branch = compact_source_references(
        default_branch(canonical, "canonical default HarnessSpec")
    )
    branch.pop("budget_share", None)
    exploration = require_object(plan.get("exploration_plan"), "exploration_plan")
    branches = require_list(exploration.get("branches"), "exploration_plan.branches")
    exploration["branches"] = [branch, *branches]


def collect_candidate_semantic_issues(
    plan: dict[str, Any], api: dict[str, Any], knowledge: list[dict[str, Any]],
    contract: dict[str, Any],
) -> list[str]:
    """Collect independent Predicate, subject, source, and mapping issues."""

    issues: list[str] = []

    def capture(label: str, action: Any) -> None:
        try:
            action()
        except (KeyError, TypeError, ValidationError, ValueError) as exc:
            issues.append(f"{label}: {exc}")

    validity = plan.get("validity_constraints")
    exploration = plan.get("exploration_plan")
    if not isinstance(validity, dict) or not isinstance(exploration, dict):
        return issues
    global_constraints = validity.get("global_constraints")
    branches = exploration.get("branches")
    if not isinstance(global_constraints, list) or not isinstance(branches, list):
        return issues

    for index, value in enumerate(global_constraints):
        if not isinstance(value, dict):
            continue
        label = f"$.validity_constraints.global_constraints[{index}]"
        capture(
            f"{label}.subjects",
            lambda value=value, label=label: validate_v2_subject_refs(
                value.get("subjects"), api, f"{label}.subjects"
            ),
        )
        capture(
            f"{label}.predicate",
            lambda value=value, label=label: validate_v2_predicate(
                value.get("predicate"), api, contract, f"{label}.predicate"
            ),
        )

    branch_by_id: dict[str, dict[str, Any]] = {}
    for branch_index, branch_value in enumerate(branches):
        if not isinstance(branch_value, dict):
            continue
        branch = branch_value
        branch_id = branch.get("branch_id")
        if isinstance(branch_id, str):
            branch_by_id[branch_id] = branch
        branch_path = f"$.exploration_plan.branches[{branch_index}]"
        for field in ("branch_constraints", "target_conditions"):
            values = branch.get(field)
            if not isinstance(values, list):
                continue
            for item_index, item in enumerate(values):
                if not isinstance(item, dict):
                    continue
                label = f"{branch_path}.{field}[{item_index}]"
                if field == "branch_constraints":
                    capture(
                        f"{label}.subjects",
                        lambda item=item, label=label: validate_v2_subject_refs(
                            item.get("subjects"), api, f"{label}.subjects"
                        ),
                    )
                capture(
                    f"{label}.predicate",
                    lambda item=item, label=label: validate_v2_predicate(
                        item.get("predicate"), api, contract, f"{label}.predicate"
                    ),
                )
                if field == "target_conditions" and isinstance(item.get("predicate"), dict):
                    predicate_id = item["predicate"].get("predicate_id")
                    observe_at = item.get("observe_at")
                    if predicate_id == "state_transition":
                        if not isinstance(observe_at, list) or len(observe_at) != 2 or set(observe_at) != {"before_target_api_call", "after_target_api_call"}:
                            issues.append(
                                f"{label}.observe_at: state_transition requires exactly "
                                "before_target_api_call and after_target_api_call"
                            )
                    elif not isinstance(observe_at, list) or len(observe_at) != 1:
                        issues.append(
                            f"{label}.observe_at: non-state-transition target condition "
                            "requires exactly one observation point"
                        )
        observations = branch.get("behavior_observations")
        if isinstance(observations, list):
            for item_index, item in enumerate(observations):
                if not isinstance(item, dict):
                    continue
                label = f"{branch_path}.behavior_observations[{item_index}]"
                capture(
                    label,
                    lambda item=item, label=label: validate_v2_behavior_observation(
                        item, api, label
                    ),
                )
        checks = branch.get("behavior_checks")
        if isinstance(checks, list):
            for item_index, item in enumerate(checks):
                if not isinstance(item, dict):
                    continue
                label = f"{branch_path}.behavior_checks[{item_index}]"
                capture(
                    f"{label}.subject_refs",
                    lambda item=item, label=label: validate_v2_subject_refs(
                        item.get("subject_refs"), api, f"{label}.subject_refs"
                    ),
                )
                preconditions = item.get("preconditions")
                if isinstance(preconditions, list):
                    for pre_index, predicate in enumerate(preconditions):
                        capture(
                            f"{label}.preconditions[{pre_index}]",
                            lambda predicate=predicate, label=label, pre_index=pre_index: validate_v2_predicate(
                                predicate, api, contract,
                                f"{label}.preconditions[{pre_index}]",
                            ),
                        )
                capture(
                    f"{label}.expected_predicate",
                    lambda item=item, label=label: validate_v2_predicate(
                        item.get("expected_predicate"), api, contract,
                        f"{label}.expected_predicate",
                    ),
                )

    lookup = source_lookup(api, [], knowledge)

    def inspect_source_refs(value: Any, path: str = "$") -> None:
        if isinstance(value, list):
            for index, item in enumerate(value):
                inspect_source_refs(item, f"{path}[{index}]")
            return
        if not isinstance(value, dict):
            return
        for key, item in value.items():
            child = f"{path}.{key}"
            if key == "source_refs" and isinstance(item, list):
                for index, reference in enumerate(item):
                    capture(
                        f"{child}[{index}]",
                        lambda reference=reference: expand_source_refs(reference, lookup),
                    )
            else:
                inspect_source_refs(item, child)

    inspect_source_refs(plan)

    knowledge_plan = plan.get("knowledge_plan")
    decisions = knowledge_plan.get("knowledge_decisions") if isinstance(knowledge_plan, dict) else None
    if isinstance(decisions, list):
        for decision_index, decision in enumerate(decisions):
            if not isinstance(decision, dict):
                continue
            knowledge_id = decision.get("knowledge_id")
            mappings = decision.get("component_mappings")
            if not isinstance(mappings, list):
                continue
            for mapping_index, mapping in enumerate(mappings):
                if not isinstance(mapping, dict):
                    continue
                mapping_path = (
                    f"$.knowledge_plan.knowledge_decisions[{decision_index}]"
                    f".component_mappings[{mapping_index}]"
                )
                source_path = mapping.get("source_path")
                refs = mapping.get("spec_element_refs")
                if not isinstance(refs, list):
                    continue
                for ref_index, ref in enumerate(refs):
                    if not isinstance(ref, dict):
                        continue
                    ref_path = f"{mapping_path}.spec_element_refs[{ref_index}]"
                    branch = branch_by_id.get(ref.get("branch_id"))
                    if branch is None:
                        issues.append(f"{ref_path}: branch_id does not resolve")
                        continue
                    try:
                        element_refs = element_source_refs(
                            branch, ref.get("element_type"), ref.get("element_id")
                        )
                    except (KeyError, TypeError, ValidationError, ValueError) as exc:
                        issues.append(f"{ref_path}: {exc}")
                        continue
                    if not any(
                        isinstance(item, dict)
                        and item.get("source_type") == "knowledge"
                        and item.get("source_id") == knowledge_id
                        and item.get("source_path") == source_path
                        for item in element_refs
                    ):
                        issues.append(
                            f"{ref_path}: referenced element does not cite the same "
                            "Knowledge source_path"
                        )
    return issues


def validate_candidate_plan(
    response: dict[str, Any], mode: str, knowledge: list[dict[str, Any]],
    api: dict[str, Any], contract: dict[str, Any],
    canonical_default: dict[str, Any] | None,
) -> dict[str, Any]:
    """Validate one candidate while reporting independent issues together."""

    issues = semantic_response_schema_issues(response, contract)
    plan = copy.deepcopy(response)
    exploration = plan.get("exploration_plan")
    branches = exploration.get("branches") if isinstance(exploration, dict) else None
    if isinstance(branches, list):
        model_defaults = [
            branch for branch in branches
            if isinstance(branch, dict) and branch.get("branch_kind") == "default"
        ]
        if mode == "controlled_baseline":
            if len(model_defaults) != 1 or len(branches) != 1:
                issues.append(
                    "$.exploration_plan.branches: controlled_baseline requires "
                    "exactly one default branch"
                )
        else:
            if model_defaults:
                issues.append(
                    "$.exploration_plan.branches: bug-aware model output must not "
                    "contain a default branch"
                )
                exploration["branches"] = [
                    branch for branch in branches if branch not in model_defaults
                ]
            if canonical_default is None:
                issues.append("canonical default HarnessSpec is unavailable")
            else:
                try:
                    inject_canonical_default_plan(plan, canonical_default)
                except (KeyError, TypeError, ValidationError, ValueError) as exc:
                    issues.append(f"canonical default injection failed: {exc}")

    normalized: dict[str, Any] | None = None
    try:
        normalized = normalize_plan(plan, contract, knowledge)
    except (KeyError, TypeError, ValidationError, ValueError) as exc:
        issues.append(f"candidate normalization failed: {exc}")
    if normalized is not None:
        issues.extend(
            collect_candidate_semantic_issues(
                normalized, api, knowledge, contract
            )
        )
        try:
            validate_plan(normalized, mode, knowledge, api, contract)
        except (KeyError, TypeError, ValidationError, ValueError) as exc:
            issues.append(f"semantic validation failed: {exc}")

    unique: list[str] = []
    seen: set[str] = set()
    for issue in issues:
        normalized_issue = re.sub(r"\s+", " ", str(issue)).strip()
        if normalized_issue and normalized_issue not in seen:
            seen.add(normalized_issue)
            unique.append(normalized_issue)
    if unique:
        displayed = unique[:24]
        suffix = "" if len(unique) <= len(displayed) else f" | ... {len(unique) - len(displayed)} more"
        raise ValidationError(
            f"Candidate validation found {len(unique)} issue(s): "
            + " | ".join(displayed)
            + suffix
        )
    assert normalized is not None
    return normalized


def source_lookup(api: dict[str, Any], _helpers: list[dict[str, Any]], knowledge: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    records: list[tuple[str, dict[str, Any], str | int]] = [("api_profile", api, api["revision"])]
    for source_type, profile, version in records:
        lookup[(source_type, profile["profile_id"])] = {
            "reference": {
                "source_type": source_type,
                "source_id": profile["profile_id"],
                "source_version": version,
                "content_hash": profile["metadata"]["content_hash"],
            },
            "record": profile,
        }
    for item in knowledge:
        ref = knowledge_reference(item)
        lookup[("knowledge", ref["knowledge_id"])] = {
            "reference": {
                "source_type": "knowledge",
                "source_id": ref["knowledge_id"],
                "source_version": ref["schema_version"],
                "content_hash": ref["content_hash"],
            },
            "record": item,
        }
    return lookup


def resolve_json_pointer(record: Any, pointer: str) -> Any:
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValidationError("source_path must be a non-root JSON Pointer")
    current = record
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            raise ValidationError(f"source_path does not resolve: {pointer}")
    return current


def expand_source_refs(value: Any, lookup: dict[tuple[str, str], dict[str, Any]]) -> Any:
    if isinstance(value, list):
        return [expand_source_refs(item, lookup) for item in value]
    if not isinstance(value, dict):
        return value
    if "source_type" in value or "source_id" in value:
        if set(value) != {"source_type", "source_id", "source_path"}:
            raise ValidationError(
                "An LLM source reference must contain exactly source_type, source_id and source_path"
            )
        key = (value["source_type"], value["source_id"])
        if key not in lookup:
            raise ValidationError(f"LLM cited an unavailable source reference: {key}")
        source_path = require_string(value.get("source_path"), "source_ref.source_path")
        resolve_json_pointer(lookup[key]["record"], source_path)
        expanded = copy.deepcopy(lookup[key]["reference"])
        expanded["source_path"] = source_path
        return expanded
    return {key: expand_source_refs(item, lookup) for key, item in value.items()}


def validate_expanded_source_refs(value: Any, lookup: dict[tuple[str, str], dict[str, Any]], selected_knowledge_ids: set[str], path: str = "root") -> None:
    if isinstance(value, list):
        for index, item in enumerate(value):
            validate_expanded_source_refs(item, lookup, selected_knowledge_ids, f"{path}[{index}]")
        return
    if not isinstance(value, dict):
        return
    for key, item in value.items():
        child = f"{path}.{key}"
        if key == "source_refs":
            refs = require_list(item, child)
            empty_allowed = child.endswith(
                (".input_validity_basis.source_refs", ".exploration_goal_source_refs")
            )
            if not refs and not empty_allowed:
                raise ValidationError(f"{child} must not be empty")
            for index, reference in enumerate(refs):
                reference = require_object(reference, f"{child}[{index}]")
                expected = {"source_type", "source_id", "source_version", "content_hash", "source_path"}
                if set(reference) != expected:
                    raise ValidationError(f"{child}[{index}] must be a complete expanded source reference")
                source_key = (reference["source_type"], reference["source_id"])
                if source_key not in lookup:
                    raise ValidationError(f"{child}[{index}] does not match an eligible source artifact")
                expected_reference = copy.deepcopy(lookup[source_key]["reference"])
                expected_reference["source_path"] = reference["source_path"]
                resolve_json_pointer(lookup[source_key]["record"], reference["source_path"])
                if reference != expected_reference:
                    raise ValidationError(f"{child}[{index}] does not match an eligible source artifact")
                if reference["source_type"] == "knowledge" and reference["source_id"] not in selected_knowledge_ids:
                    raise ValidationError(f"{child}[{index}] cites Knowledge that was not selected")
        else:
            validate_expanded_source_refs(item, lookup, selected_knowledge_ids, child)


def validate_initial_budget_policy(
    policy: dict[str, Any],
    *,
    revision_number: int | None = None,
    revision_trigger: str | None = None,
) -> None:
    require_string(policy.get("policy_version"), "budget_policy.policy_version")
    require_string(policy.get("policy_id"), "budget_policy.policy_id")
    scope = require_object(policy.get("scope"), "budget_policy.scope")
    modes = require_list(scope.get("applicable_spec_modes"), "budget_policy.scope.applicable_spec_modes")
    if set(modes) != {"bug_aware_static", "bug_aware_adaptive"}:
        raise InputError("Initial budget policy must apply only to the two bug-aware modes")
    if scope.get("state_isolation") != "per_harness_spec":
        raise InputError("Initial budget policy must be isolated per HarnessSpec")
    if "applicable_revision_number" in scope:
        if set(scope) != {
            "applicable_spec_modes", "applicable_revision_number", "state_isolation"
        } or scope["applicable_revision_number"] != 1:
            raise InputError("Legacy initial budget policy must apply only to revision 1")
        if revision_number is not None and revision_number != 1:
            raise InputError(
                "Selected initial budget policy applies only to HarnessSpec revision 1"
            )
    else:
        expected_triggers = {
            "initial_creation", "manual_review", "source_artifact_update", "regeneration"
        }
        triggers = require_list(
            scope.get("applicable_revision_triggers"),
            "budget_policy.scope.applicable_revision_triggers",
        )
        if set(scope) != {
            "applicable_spec_modes", "applicable_revision_triggers", "state_isolation"
        } or set(triggers) != expected_triggers or len(triggers) != len(expected_triggers):
            raise InputError(
                "Revision-aware initial budget policy has an invalid trigger scope"
            )
        if revision_trigger is not None and revision_trigger not in expected_triggers:
            raise InputError(
                "Selected initial budget policy does not apply to this revision trigger"
            )

    allocation = require_object(policy.get("allocation"), "budget_policy.allocation")
    default_rule = require_object(allocation.get("default_branch"), "budget_policy.allocation.default_branch")
    other_rule = require_object(allocation.get("non_default_branches"), "budget_policy.allocation.non_default_branches")
    rounding = require_object(policy.get("rounding"), "budget_policy.rounding")
    if policy.get("policy_kind") != "initial_branch_allocation":
        raise InputError("Unsupported budget policy kind")
    if allocation.get("method") != "equal_with_default_floor":
        raise InputError("Unsupported initial budget allocation method")
    require_string(allocation.get("description"), "budget_policy.allocation.description")
    if allocation.get("target_total_share") != 1.0 or allocation.get("single_branch_default_share") != 1.0:
        raise InputError("Initial budget policy must allocate a total share of 1.0")
    if default_rule.get("base") != "equal_share" or other_rule.get("distribution") != "equal_remaining":
        raise InputError("Initial budget policy has unsupported structured allocation rules")
    if allocation.get("infeasible_policy") != "validation_error":
        raise InputError("Initial budget policy must reject infeasible allocations")
    if not isinstance(rounding.get("decimal_places"), int) or rounding["decimal_places"] < 0:
        raise InputError("budget_policy.rounding.decimal_places must be a non-negative integer")
    if rounding.get("residual_recipient") != "default_branch":
        raise InputError("Initial budget rounding residual must go to the default branch")
    for field, value in (
        ("default minimum", default_rule.get("minimum_share")),
        ("non-default minimum", other_rule.get("minimum_share")),
        ("sum tolerance", rounding.get("sum_tolerance")),
    ):
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise InputError(f"Budget policy {field} must be a non-negative number")


def allocate_budget(branches: list[dict[str, Any]], policy: dict[str, Any] | None, mode: str) -> None:
    defaults = [item for item in branches if item["branch_kind"] == "default"]
    if len(defaults) != 1:
        raise ValidationError("Exactly one default branch is required before budget allocation")
    default = defaults[0]
    if mode == "controlled_baseline":
        if len(branches) != 1:
            raise ValidationError("Controlled baseline must contain only the default branch")
        default["budget_share"] = 1.0
        return
    if policy is None:
        raise ValidationError("Bug-aware revision 1 requires an initial budget policy")

    allocation = policy["allocation"]
    rounding = policy["rounding"]
    count = len(branches)
    target = float(allocation["target_total_share"])
    if count == 1:
        default["budget_share"] = float(allocation["single_branch_default_share"])
        return
    default_minimum = float(allocation["default_branch"]["minimum_share"])
    other_minimum = float(allocation["non_default_branches"]["minimum_share"])
    default_share = max(target / count, default_minimum)
    remaining = target - default_share
    if remaining + float(rounding["sum_tolerance"]) < (count - 1) * other_minimum:
        raise ValidationError("Configured branch budget policy is infeasible")
    other_share = remaining / (count - 1)
    places = int(rounding["decimal_places"])
    for branch in branches:
        branch["budget_share"] = round(default_share if branch is default else other_share, places)
    residual = target - sum(float(branch["budget_share"]) for branch in branches)
    default["budget_share"] = round(float(default["budget_share"]) + residual, places)
    tolerance = float(rounding["sum_tolerance"])
    if float(default["budget_share"]) + tolerance < default_minimum:
        raise ValidationError("Default branch budget is below the policy minimum")
    if any(float(branch["budget_share"]) + tolerance < other_minimum for branch in branches if branch is not default):
        raise ValidationError("A non-default branch budget is below the policy minimum")
    if abs(sum(float(branch["budget_share"]) for branch in branches) - target) > tolerance:
        raise ValidationError("Allocated branch budgets do not sum to the policy target")




def harness_spec_reference(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "spec_id": record["identity"]["spec_id"],
        "revision_number": record["revision_information"]["revision_number"],
        "content_hash": canonical_hash(record),
    }


def selector_allocations(branches: list[dict[str, Any]]) -> dict[str, int]:
    if not branches or len(branches) > 256:
        raise ValidationError("Branch count is incompatible with a 256-slot selector")
    weights = [Decimal(str(branch["budget_share"])) for branch in branches]
    if any(weight <= 0 for weight in weights):
        raise ValidationError("Every Branch budget_share must be positive")
    total = sum(weights)
    quotas = [weight * Decimal(256) / total for weight in weights]
    allocations = [
        max(1, int(quota.to_integral_value(rounding=ROUND_FLOOR)))
        for quota in quotas
    ]
    while sum(allocations) > 256:
        candidates = [index for index, value in enumerate(allocations) if value > 1]
        if not candidates:
            raise ValidationError("Cannot assign a positive slot to every Branch")
        selected = min(
            candidates,
            key=lambda index: (
                -(Decimal(allocations[index]) - quotas[index]),
                branches[index]["branch_id"],
            ),
        )
        allocations[selected] -= 1
    while sum(allocations) < 256:
        selected = min(
            range(len(branches)),
            key=lambda index: (
                -(quotas[index] - Decimal(allocations[index])),
                branches[index]["branch_id"],
            ),
        )
        allocations[selected] += 1
    return {
        branch["branch_id"]: slots
        for branch, slots in zip(branches, allocations)
    }


def adaptive_identity_component(value: str) -> str:
    result = re.sub(r"[^A-Za-z0-9]+", "_", value.strip()).strip("_").lower()
    if not result:
        raise InputError("Adaptive identity component cannot be empty")
    return result


def adaptive_spec_id(parent: dict[str, Any], repeat_id: str) -> str:
    identity = parent["identity"]
    return (
        f"hs_{adaptive_identity_component(identity['framework'])}_"
        f"{adaptive_identity_component(identity['target_api'])}_"
        f"bug_aware_adaptive_{adaptive_identity_component(repeat_id)}"
    )


def validate_feedback_request(
    request: dict[str, Any],
    parent: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, int]]:
    required = {
        "request_version",
        "request_id",
        "scope",
        "input_references",
        "budget_decision",
        "candidate_directive",
        "required_pipeline",
        "request_key",
    }
    if set(request) != required or request["request_version"] != "1.1":
        raise InputError("Feedback Materialization Request does not match version 1.1")
    unsigned = {key: value for key, value in request.items() if key != "request_key"}
    if request["request_key"] != canonical_hash(unsigned):
        raise InputError("Feedback Materialization Request key is invalid")

    scope = require_object(request["scope"], "feedback_request.scope")
    if scope.get("experimental_group") != "bug_aware_adaptive":
        raise InputError("Feedback request is not scoped to bug_aware_adaptive")
    identity = parent["identity"]
    if scope.get("target_api_id") != identity["target_api"]:
        raise InputError("Feedback request target API does not match the parent HarnessSpec")

    references = require_object(
        request["input_references"], "feedback_request.input_references"
    )
    if references.get("current_harness_spec_ref") != harness_spec_reference(parent):
        raise InputError("Feedback request does not reference the exact parent HarnessSpec")

    budget = require_object(request["budget_decision"], "feedback_request.budget_decision")
    if (
        budget.get("budget_action") != "reallocate_budget"
        or budget.get("transition_kind") not in {
            "exploration_boost",
            "restore_pre_boost_allocation",
        }
    ):
        raise InputError("Feedback request does not contain an effective reallocation")

    def allocation(value: Any, label: str) -> dict[str, int]:
        items = require_list(value, label)
        result: dict[str, int] = {}
        for index, item_value in enumerate(items):
            item = require_object(item_value, f"{label}[{index}]")
            if set(item) != {"branch_id", "selector_slots"}:
                raise InputError(f"{label}[{index}] has unexpected fields")
            branch_id = require_string(item["branch_id"], f"{label}[{index}].branch_id")
            slots = item["selector_slots"]
            if isinstance(slots, bool) or not isinstance(slots, int) or slots < 1:
                raise InputError(f"{label}[{index}].selector_slots must be positive")
            if branch_id in result:
                raise InputError(f"{label} repeats Branch {branch_id}")
            result[branch_id] = slots
        return result

    current = allocation(budget.get("current_allocation"), "current_allocation")
    proposed = allocation(budget.get("proposed_allocation"), "proposed_allocation")
    expected_current = selector_allocations(parent["exploration_plan"]["branches"])
    if current != expected_current:
        raise InputError("Feedback current allocation does not match the parent")
    if set(proposed) != set(current) or sum(proposed.values()) != 256:
        raise InputError("Feedback proposed allocation changes Branches or total slots")
    if proposed == current:
        raise InputError("Feedback proposed allocation is not effective")

    repeat_id = require_string(
        scope.get("independent_repeat_id"), "scope.independent_repeat_id"
    )
    directive = require_object(
        request["candidate_directive"], "feedback_request.candidate_directive"
    )
    expected_id = adaptive_spec_id(parent, repeat_id)
    parent_mode = identity["spec_mode"]
    if parent_mode == "bug_aware_static":
        expected_directive = {
            "spec_id": expected_id,
            "spec_mode": "bug_aware_adaptive",
            "revision_number": 1,
            "lineage_kind": "derived_from_shared_h0",
        }
    elif parent_mode == "bug_aware_adaptive":
        if identity["spec_id"] != expected_id:
            raise InputError("Adaptive parent identity is outside this repeat")
        expected_directive = {
            "spec_id": expected_id,
            "spec_mode": "bug_aware_adaptive",
            "revision_number": parent["revision_information"]["revision_number"] + 1,
            "lineage_kind": "same_identity_revision",
        }
    else:
        raise InputError("Feedback parent must be shared Static H0 or an Adaptive revision")
    if directive != expected_directive:
        raise InputError("Feedback candidate directive is inconsistent with the parent")
    return directive, proposed


def build_feedback_revision(
    args: argparse.Namespace,
    record_schema: dict[str, Any],
    run_id: str,
) -> int:
    request = require_object(load_json(args.feedback_request), "feedback_request")
    parent = validate_harness_record(
        load_json(args.parent_spec), record_schema, "parent HarnessSpec", args
    )
    if parent["review"]["validation_status"] != "passed":
        raise InputError("Parent HarnessSpec validation_status is not passed")
    if parent.get("schema_version") != SCHEMA_VERSION:
        raise InputError("Feedback parent must first be migrated to HarnessSpec v2.2")
    directive, proposed = validate_feedback_request(request, parent)

    candidate = copy.deepcopy(parent)
    parent_ref = harness_spec_reference(parent)
    derived = directive["lineage_kind"] == "derived_from_shared_h0"
    candidate["identity"]["spec_id"] = directive["spec_id"]
    candidate["identity"]["spec_mode"] = directive["spec_mode"]
    candidate["revision_information"] = {
        "revision_number": directive["revision_number"],
        "parent_revision_ref": None if derived else parent_ref,
        "derived_from_spec_ref": parent_ref if derived else None,
        "feedback_request_ref": {
            "artifact_id": request["request_id"],
            "artifact_version": request["request_version"],
            "content_hash": file_hash(args.feedback_request),
        },
        "revision_trigger": "execution_feedback",
        "change_scopes": ["budget_allocation"],
        "change_summary": (
            f"Apply deterministic Branch-budget request {request['request_id']}"
        ),
        "lifecycle_status": "draft",
    }
    candidate["exploration_plan"]["budget_policy_ref"] = copy.deepcopy(
        request["input_references"]["feedback_policy_ref"]
    )
    for branch in candidate["exploration_plan"]["branches"]:
        branch["budget_share"] = proposed[branch["branch_id"]] / 256
    generator_refs = generation_artifact_refs(args)
    candidate["provenance"] = {
        "generation_method": "script",
        "generator_name": BUILDER_VERSION,
        "model_name": None,
        "generation_run_id": run_id,
        "script_ref": copy.deepcopy(generator_refs["script_ref"]),
        "contract_ref": copy.deepcopy(generator_refs["contract_ref"]),
        "rules_ref": copy.deepcopy(generator_refs["rules_ref"]),
        "schema_ref": copy.deepcopy(generator_refs["schema_ref"]),
        "schema_core_ref": copy.deepcopy(generator_refs["schema_core_ref"]),
        "generation_trace_ref": None,
        "generated_at": utc_now(),
    }
    candidate["review"] = {
        "validation_status": "passed",
        "validation_issues": [],
        "human_review_status": "not_reviewed",
        "reviewer_id": None,
        "reviewed_at": None,
        "review_notes": None,
    }
    validate_record(candidate, record_schema, args)
    path = destination(args.output_root, candidate)
    summary = {
        "target_api": candidate["identity"]["target_api"],
        "mode": candidate["identity"]["spec_mode"],
        "status": "dry_run" if args.dry_run else "success",
        "attempts": 0,
        "output_path": None if args.dry_run else str(path),
        "parent_revision_ref": candidate["revision_information"]["parent_revision_ref"],
        "derived_from_spec_ref": candidate["revision_information"]["derived_from_spec_ref"],
        "feedback_request_ref": candidate["revision_information"]["feedback_request_ref"],
    }
    if not args.dry_run:
        write_json(path, candidate)
    emit_result(args, summary)
    return 0

def api_semantic_projection(profile: dict[str, Any]) -> dict[str, Any]:
    """Return API facts that a HarnessSpec may depend on semantically."""
    return {
        key: copy.deepcopy(profile[key])
        for key in (
            "profile_id", "target", "python_contract", "target_binding",
            "documented_constraints", "flashfuzz_support",
        )
    }


def resolve_exact_api_profile(
    reference: dict[str, Any], profiles: list[dict[str, Any]]
) -> dict[str, Any]:
    matches = [item for item in profiles if profile_reference(item) == reference]
    if len(matches) != 1:
        raise InputError("HarnessSpec API Profile reference does not resolve exactly once")
    return matches[0]


def build_api_profile_refresh_revision(
    args: argparse.Namespace,
    record_schema: dict[str, Any],
    api_schema: dict[str, Any],
    run_id: str,
) -> int:
    """Create a new HarnessSpec revision that only refreshes its API reference."""
    parent = validate_harness_record(
        load_json(args.parent_spec), record_schema, "parent HarnessSpec", args
    )
    new_api = validate_profile_record(
        load_json(args.api_profile), api_schema, "replacement API Profile"
    )
    if parent["review"]["validation_status"] != "passed":
        raise InputError("Parent HarnessSpec validation_status is not passed")
    if parent.get("schema_version") != SCHEMA_VERSION:
        raise InputError("API Profile refresh parent must first be migrated to HarnessSpec v2.2")
    if (
        new_api["target_binding"]["status"] != "resolved"
        or new_api["validation"]["validation_status"] != "passed"
        or new_api["validation"]["execution_readiness"] != "ready"
        or new_api["review"]["review_status"] != "approved"
    ):
        raise InputError(
            "Replacement API Profile must be resolved, ready, passed, and approved"
        )

    old_ref = parent["target_context"]["api_profile_ref"]
    old_api = resolve_exact_api_profile(
        old_ref, read_records(args.api_profiles, api_schema, "API Profile")
    )
    if new_api["profile_id"] != old_api["profile_id"]:
        raise InputError("Replacement API Profile changes profile identity")
    if new_api["revision"] <= old_api["revision"]:
        raise InputError("Replacement API Profile is not a later revision")
    if api_semantic_projection(new_api) != api_semantic_projection(old_api):
        raise InputError(
            "Replacement API Profile changes API semantics; LLM resynthesis is required"
        )
    identity = parent["identity"]
    target = new_api["target"]
    if (
        target["framework"] != identity["framework"]
        or target["python_api"] != identity["target_api"]
    ):
        raise InputError("Replacement API Profile conflicts with HarnessSpec identity")

    candidate = copy.deepcopy(parent)
    parent_ref = harness_spec_reference(parent)
    candidate["revision_information"] = {
        "revision_number": parent["revision_information"]["revision_number"] + 1,
        "parent_revision_ref": parent_ref,
        "derived_from_spec_ref": None,
        "feedback_request_ref": None,
        "revision_trigger": "source_artifact_update",
        "change_scopes": ["target_context"],
        "change_summary": (
            "Deterministically refresh the exact API Profile reference after "
            "compile and runtime validation"
        ),
        "lifecycle_status": "draft",
    }
    candidate["target_context"]["api_profile_ref"] = profile_reference(new_api)
    generator_refs = generation_artifact_refs(args)
    candidate["provenance"] = {
        "generation_method": "script",
        "generator_name": BUILDER_VERSION,
        "model_name": None,
        "generation_run_id": run_id,
        "script_ref": copy.deepcopy(generator_refs["script_ref"]),
        "contract_ref": copy.deepcopy(generator_refs["contract_ref"]),
        "rules_ref": copy.deepcopy(generator_refs["rules_ref"]),
        "schema_ref": copy.deepcopy(generator_refs["schema_ref"]),
        "schema_core_ref": copy.deepcopy(generator_refs["schema_core_ref"]),
        "generation_trace_ref": None,
        "generated_at": utc_now(),
    }
    candidate["review"] = {
        "validation_status": "passed", "validation_issues": [],
        "human_review_status": "not_reviewed", "reviewer_id": None,
        "reviewed_at": None, "review_notes": None,
    }
    validate_record(candidate, record_schema, args)
    path = destination(args.output_root, candidate)
    if not args.dry_run:
        write_json(path, candidate)
    emit_result(args, {
        "target_api": identity["target_api"], "mode": identity["spec_mode"],
        "status": "dry_run" if args.dry_run else "success", "attempts": 0,
        "output_path": None if args.dry_run else str(path),
        "parent_revision_ref": parent_ref,
        "api_profile_ref": profile_reference(new_api),
    })
    return 0


def artifact_ref(
    path: Path, version: str | int | None, *, include_path: bool = False
) -> dict[str, Any]:
    reference = {
        "artifact_id": path.name,
        "artifact_version": version,
        "content_hash": file_hash(path),
    }
    if include_path:
        resolved = path.resolve()
        try:
            reference["relative_path"] = str(resolved.relative_to(Path.cwd().resolve()))
        except ValueError:
            reference["relative_path"] = str(resolved)
    return reference


def freeze_generation_artifact(
    source: Path, version: str, root: Path
) -> dict[str, Any]:
    """Persist exact generator bytes under a hash-qualified immutable name."""

    source = source.resolve()
    digest = file_hash(source)
    suffix = "".join(source.suffixes) or ".artifact"
    stem = safe_component(source.name.removesuffix(suffix))
    target = root / f"{stem}__{safe_component(version)}__sha256_{digest}{suffix}"
    root.mkdir(parents=True, exist_ok=True)
    payload = source.read_bytes()
    if target.exists():
        if target.read_bytes() != payload:
            raise InputError(f"Frozen generation artifact hash collision: {target}")
    else:
        temporary = target.with_suffix(target.suffix + f".{uuid.uuid4().hex}.tmp")
        temporary.write_bytes(payload)
        try:
            os.link(temporary, target)
        except FileExistsError:
            if target.read_bytes() != payload:
                raise InputError(f"Concurrent generation artifact mismatch: {target}")
        finally:
            temporary.unlink(missing_ok=True)
    return artifact_ref(target, version, include_path=True)


def generation_artifact_refs(args: argparse.Namespace) -> dict[str, dict[str, Any]]:
    existing = getattr(args, "_generation_artifact_refs", None)
    if existing is not None:
        return existing
    root = getattr(args, "generation_artifacts", None)
    if root is None or getattr(args, "dry_run", False):
        # Direct unit-level assembly and dry-run remain side-effect free.
        refs = {
            "script_ref": artifact_ref(Path(__file__).resolve(), BUILDER_VERSION, include_path=True),
            "contract_ref": artifact_ref(args.contract, CONTRACT_VERSION, include_path=True),
            "rules_ref": artifact_ref(args.rules, RULES_VERSION, include_path=True),
            "schema_ref": artifact_ref(args.record_schema, SCHEMA_VERSION, include_path=True),
            "schema_core_ref": artifact_ref(args.record_schema_core, SCHEMA_VERSION, include_path=True),
        }
    else:
        refs = {
            "script_ref": freeze_generation_artifact(
                Path(__file__), BUILDER_VERSION, root
            ),
            "contract_ref": freeze_generation_artifact(
                args.contract, CONTRACT_VERSION, root
            ),
            "rules_ref": freeze_generation_artifact(args.rules, RULES_VERSION, root),
            "schema_ref": freeze_generation_artifact(
                args.record_schema, SCHEMA_VERSION, root
            ),
            "schema_core_ref": freeze_generation_artifact(
                args.record_schema_core, SCHEMA_VERSION, root
            ),
        }
    args._generation_artifact_refs = refs
    return refs


def write_generation_trace(
    args: argparse.Namespace,
    run_id: str,
    attempt: int,
    prompt: str,
    response_text: str,
    prior_errors: list[str],
    review_record_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist the exact prompt/response pair before parsing model output."""

    trace = {
        "trace_version": "1.1",
        "generation_run_id": run_id,
        "attempt": attempt,
        "model_name": args.model,
        "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "prompt_text": prompt,
        "response_hash": hashlib.sha256(response_text.encode("utf-8")).hexdigest(),
        "response_text": response_text,
        "prior_errors": list(prior_errors),
        "review_record_ref": copy.deepcopy(review_record_ref),
        "created_at": utc_now(),
    }
    trace_schema = require_object(
        load_json(args.generation_trace_schema), "generation trace Schema"
    )
    validate_profile_record(trace, trace_schema, "generation trace")
    path = (
        args.generation_traces
        / safe_component(run_id)
        / f"attempt_{attempt:03d}.json"
    )
    write_immutable_json(path, trace, "generation trace")
    return artifact_ref(path, trace["trace_version"], include_path=True)


def migrate_baseline_to_v2_2(
    args: argparse.Namespace,
    record_schema: dict[str, Any],
    run_id: str,
) -> int:
    """Deterministically migrate a validated v2.0/v2.1 controlled Baseline."""

    contract = require_object(load_json(args.contract), "HarnessSpec Contract")
    if (
        contract.get("contract_version") != CONTRACT_VERSION
        or contract.get("target_schema_version") != SCHEMA_VERSION
    ):
        raise InputError("Contract version is incompatible with v2.2 migration")
    rules = load_text(args.rules)
    if not rules.startswith(
        f"# Knowledge v3 to HarnessSpec Synthesis Rules v{RULES_VERSION}"
    ):
        raise InputError("Rules version is incompatible with v2.2 migration")

    parent = validate_harness_record(
        load_json(args.parent_spec), record_schema, "parent HarnessSpec", args
    )
    identity = require_object(parent.get("identity"), "parent.identity")
    parent_version = parent.get("schema_version")
    if parent_version not in {"2.0", "2.1"}:
        raise InputError("--migrate-v2-2 requires a HarnessSpec v2.0 or v2.1 parent")
    if identity.get("spec_mode") != "controlled_baseline":
        raise InputError("Only controlled Baselines use deterministic v2.2 migration")
    if parent["review"].get("validation_status") != "passed":
        raise InputError("Migration parent validation_status is not passed")
    if parent["knowledge_plan"].get("knowledge_decisions"):
        raise InputError("Controlled Baseline migration cannot contain Knowledge decisions")
    branch = default_branch(parent, "migration parent")
    if len(parent["exploration_plan"]["branches"]) != 1:
        raise InputError("Migration parent must contain exactly one default Branch")

    candidate = copy.deepcopy(parent)
    candidate["schema_version"] = SCHEMA_VERSION
    migrated_branch = default_branch(candidate, "migration candidate")
    if parent_version == "2.0":
        migrated_branch["input_validity_basis"] = {
            "basis_kind": "canonical_baseline_definition",
            "source_refs": [],
            "summary": (
                "This branch is the canonical controlled-Baseline definition; "
                "it does not assert undocumented API boundary semantics."
            ),
        }
        migrated_branch["exploration_goal_source_refs"] = []
        change_scopes = ["branch_semantics"]
    else:
        change_scopes = ["metadata_only"]
    candidate["revision_information"] = {
        "revision_number": parent["revision_information"]["revision_number"] + 1,
        "parent_revision_ref": harness_spec_reference(parent),
        "derived_from_spec_ref": None,
        "feedback_request_ref": None,
        "revision_trigger": "source_artifact_update",
        "change_scopes": change_scopes,
        "change_summary": (
            f"Migrate the controlled Baseline from HarnessSpec v{parent_version} "
            "to v2.2"
        ),
        "lifecycle_status": "draft",
    }
    generator_refs = generation_artifact_refs(args)
    candidate["provenance"] = {
        "generation_method": "script",
        "generator_name": BUILDER_VERSION,
        "model_name": None,
        "generation_run_id": run_id,
        "script_ref": copy.deepcopy(generator_refs["script_ref"]),
        "contract_ref": copy.deepcopy(generator_refs["contract_ref"]),
        "rules_ref": copy.deepcopy(generator_refs["rules_ref"]),
        "schema_ref": copy.deepcopy(generator_refs["schema_ref"]),
        "schema_core_ref": copy.deepcopy(generator_refs["schema_core_ref"]),
        "generation_trace_ref": None,
        "generated_at": utc_now(),
    }
    candidate["review"] = {
        "validation_status": "passed",
        "validation_issues": [],
        "human_review_status": "not_reviewed",
        "reviewer_id": None,
        "reviewed_at": None,
        "review_notes": None,
    }
    if (
        parent_version == "2.0"
        and default_branch_projection(branch) == default_branch_projection(migrated_branch)
    ):
        raise ValidationError("v2.2 migration did not materialize the required semantics")
    validate_record(candidate, record_schema, args)
    path = destination(args.output_root, candidate)
    ensure_revision_available(path)
    if not args.dry_run:
        write_json(path, candidate)
    emit_result(
        args,
        {
            "target_api": identity["target_api"],
            "mode": identity["spec_mode"],
            "status": "dry_run" if args.dry_run else "success",
            "attempts": 0,
            "output_path": None if args.dry_run else str(path),
            "parent_revision_ref": candidate["revision_information"]["parent_revision_ref"],
            "migration": f"harness_spec_v{parent_version}_to_v2.2",
        },
    )
    return 0


def spec_id_for(framework: str, target_api: str, mode: str) -> str:
    return f"hs_{safe_component(framework)}_{safe_component(target_api)}_{mode}"


def revision_path(root: Path, framework: str, target_api: str, mode: str, revision: int) -> Path:
    spec_id = spec_id_for(framework, target_api, mode)
    return root / safe_component(framework) / safe_component(target_api) / mode / f"{spec_id}_r{revision}.json"


def parent_record_and_reference(
    args: argparse.Namespace,
    api: dict[str, Any],
    record_schema: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if args.revision == 1:
        return None, None
    parent_path = revision_path(args.output_root, api["target"]["framework"], args.target_api, args.mode, args.revision - 1)
    parent = validate_harness_record(
        load_json(parent_path), record_schema, "parent HarnessSpec", args
    )
    expected_identity = {
        "spec_id": spec_id_for(api["target"]["framework"], args.target_api, args.mode),
        "framework": api["target"]["framework"],
        "target_api": args.target_api,
        "spec_mode": args.mode,
    }
    if parent["identity"] != expected_identity or parent["revision_information"]["revision_number"] != args.revision - 1:
        raise InputError("Parent HarnessSpec identity or revision does not match the requested child")
    if parent["review"].get("validation_status") != "passed":
        raise InputError("Parent HarnessSpec validation_status is not passed")
    return parent, {
        "spec_id": parent["identity"]["spec_id"],
        "revision_number": args.revision - 1,
        "content_hash": canonical_hash(parent),
    }


def review_regeneration_context(
    args: argparse.Namespace,
    parent: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Validate and project one exact external needs-revision review."""

    if args.review_record is None:
        return None, None
    if parent is None:
        raise InputError("Review regeneration requires an existing parent HarnessSpec")
    review = validate_profile_record(
        load_json(args.review_record), load_json(args.review_schema),
        "HarnessSpec review record",
    )
    if review.get("decision") != "needs_revision":
        raise InputError("--review-record must have decision needs_revision")
    findings = require_list(review.get("findings"), "review_record.findings")
    blocking = [
        require_object(item, f"review_record.findings[{index}]")
        for index, item in enumerate(findings)
        if isinstance(item, dict) and item.get("severity") == "blocking"
    ]
    if not blocking:
        raise InputError("--review-record must contain at least one blocking finding")

    parent_path = revision_path(
        args.output_root,
        parent["identity"]["framework"],
        parent["identity"]["target_api"],
        parent["identity"]["spec_mode"],
        parent["revision_information"]["revision_number"],
    )
    subject = require_object(review.get("subject"), "review_record.subject")
    expected_subject = {
        "spec_id": parent["identity"]["spec_id"],
        "revision_number": parent["revision_information"]["revision_number"],
        "content_hash": canonical_hash(parent),
    }
    if any(subject.get(key) != value for key, value in expected_subject.items()):
        raise InputError("Review record subject does not match the exact parent HarnessSpec")
    subject_path = Path(
        require_string(subject.get("relative_path"), "review_record.subject.relative_path")
    )
    if subject_path.resolve() != parent_path.resolve():
        raise InputError("Review record subject path does not resolve to the parent HarnessSpec")

    rules_ref = require_object(review.get("rules_ref"), "review_record.rules_ref")
    rules_path = Path(
        require_string(rules_ref.get("relative_path"), "review_record.rules_ref.relative_path")
    )
    if not rules_path.is_file() or file_hash(rules_path) != rules_ref.get("content_hash"):
        raise InputError("Review record Rules reference does not resolve to its exact hash")

    reference = artifact_ref(
        args.review_record,
        review["schema_version"],
        include_path=True,
    )
    context = {
        "review_record_ref": copy.deepcopy(reference),
        "review_id": review["review_id"],
        "review_revision": review["review_revision"],
        "subject": expected_subject,
        "parent_semantic_plan": semantic_plan_from_record(parent),
        "blocking_findings": [
            {
                "criterion_id": item["criterion_id"],
                "field_path": item["field_path"],
                "evidence_ref": item["evidence_ref"],
                "mismatch_summary": item["mismatch_summary"],
            }
            for item in blocking
        ],
    }
    return context, reference


def validate_manual_review_frozen_inputs(
    parent: dict[str, Any],
    api: dict[str, Any],
    helpers: list[dict[str, Any]],
    knowledge: list[dict[str, Any]],
    policy: dict[str, Any] | None,
    policy_path: Path | None,
    canonical_default: dict[str, Any] | None,
) -> None:
    """Ensure manual review repairs do not silently change their source bundle."""

    expected_context = {
        "api_profile_ref": profile_reference(api),
        "available_helper_profile_refs": [profile_reference(item) for item in helpers],
        "framework_version": api["target"]["framework_version"],
        "backend_scope": api["target"]["backend_scope"],
    }
    if parent["target_context"] != expected_context:
        raise InputError(
            "Manual-review regeneration requires the parent's exact API and Helper inputs"
        )
    expected_knowledge = sorted(
        (item["knowledge_id"], item["schema_version"], item["content_hash"])
        for item in (knowledge_reference(record) for record in knowledge)
    )
    parent_knowledge = sorted(
        (
            decision["knowledge_ref"]["knowledge_id"],
            decision["knowledge_ref"]["schema_version"],
            decision["knowledge_ref"]["content_hash"],
        )
        for decision in parent["knowledge_plan"]["knowledge_decisions"]
    )
    if parent_knowledge != expected_knowledge:
        raise InputError(
            "Manual-review regeneration requires the parent's exact Knowledge bundle"
        )
    expected_policy_ref = (
        None
        if policy is None or policy_path is None
        else artifact_ref(policy_path, policy["policy_version"])
    )
    if parent["exploration_plan"]["budget_policy_ref"] != expected_policy_ref:
        raise InputError(
            "Manual-review regeneration requires the parent's exact budget policy"
        )
    recorded_canonical = parent["revision_information"].get(
        "canonical_default_spec_ref"
    )
    expected_canonical = (
        None if canonical_default is None else harness_spec_reference(canonical_default)
    )
    if recorded_canonical is not None and recorded_canonical != expected_canonical:
        raise InputError(
            "Manual-review regeneration uses a different canonical Baseline"
        )


def branch_structure_projection(record: dict[str, Any]) -> dict[str, Any]:
    exploration = record["exploration_plan"]
    return {
        "default_branch_id": exploration["default_branch_id"],
        "branches": [
            {
                "branch_id": branch["branch_id"],
                "branch_kind": branch["branch_kind"],
            }
            for branch in exploration["branches"]
        ],
    }


def branch_semantics_projection(record: dict[str, Any]) -> list[dict[str, Any]]:
    projected: list[dict[str, Any]] = []
    for branch in record["exploration_plan"]["branches"]:
        value = copy.deepcopy(branch)
        value.pop("budget_share", None)
        projected.append(value)
    return projected


def budget_projection(record: dict[str, Any]) -> dict[str, Any]:
    exploration = record["exploration_plan"]
    return {
        "budget_policy_ref": copy.deepcopy(exploration["budget_policy_ref"]),
        "branch_shares": [
            {
                "branch_id": branch["branch_id"],
                "budget_share": branch["budget_share"],
            }
            for branch in exploration["branches"]
        ],
    }


def derive_change_scopes(
    parent: dict[str, Any], candidate: dict[str, Any]
) -> list[str]:
    """Derive revision scopes from stable semantic projections.

    Identity, lineage, provenance, lifecycle, and review are Builder-owned
    revision metadata and therefore do not by themselves create a semantic
    scope.  The fixed ordering keeps the result reproducible.
    """

    scopes: list[str] = []
    if parent["target_context"] != candidate["target_context"]:
        scopes.append("target_context")
    if parent["knowledge_plan"] != candidate["knowledge_plan"]:
        scopes.append("knowledge_selection")
    if branch_structure_projection(parent) != branch_structure_projection(candidate):
        scopes.append("branch_structure")
    if branch_semantics_projection(parent) != branch_semantics_projection(candidate):
        scopes.append("branch_semantics")
    if budget_projection(parent) != budget_projection(candidate):
        scopes.append("budget_allocation")
    return scopes or ["metadata_only"]


def apply_derived_revision_metadata(
    candidate: dict[str, Any], parent: dict[str, Any] | None
) -> None:
    if parent is None:
        return
    scopes = derive_change_scopes(parent, candidate)
    revision = candidate["revision_information"]
    revision["change_scopes"] = scopes
    revision["change_summary"] = (
        f"Regenerate HarnessSpec revision from frozen inputs; changed scopes: "
        f"{', '.join(scopes)}"
    )


def ensure_revision_available(path: Path) -> None:
    if path.exists():
        raise InputError(
            "HarnessSpec revision already exists; immutable records cannot be "
            f"overwritten: {path}. Select the next explicit --revision."
        )


def assemble_record(plan: dict[str, Any], args: argparse.Namespace, api: dict[str, Any], helpers: list[dict[str, Any]], knowledge: list[dict[str, Any]], policy: dict[str, Any] | None, policy_path: Path | None, parent_ref: dict[str, Any] | None, run_id: str, generation_trace_ref: dict[str, Any]) -> dict[str, Any]:
    branches = copy.deepcopy(plan["exploration_plan"]["branches"])
    allocate_budget(branches, policy, args.mode)
    default = next(item for item in branches if item["branch_kind"] == "default")
    lookup = source_lookup(api, helpers, knowledge)
    expanded = expand_source_refs({"knowledge_plan": plan["knowledge_plan"], "validity_constraints": plan["validity_constraints"], "exploration_plan": {"branches": branches}}, lookup)
    included_ids = {
        item["knowledge_id"]
        for item in expanded["knowledge_plan"]["knowledge_decisions"]
        if item["disposition"] == "included"
    }
    validate_expanded_source_refs(expanded, lookup, included_ids)
    references = {item["metadata"]["knowledge_id"]: knowledge_reference(item) for item in knowledge}
    for decision in expanded["knowledge_plan"]["knowledge_decisions"]:
        decision["knowledge_ref"] = references[decision.pop("knowledge_id")]
    framework = api["target"]["framework"]
    spec_id = spec_id_for(framework, args.target_api, args.mode)
    generator_refs = generation_artifact_refs(args)
    record = {
        "schema_version": SCHEMA_VERSION,
        "identity": {"spec_id": spec_id, "framework": framework, "target_api": args.target_api, "spec_mode": args.mode},
        "revision_information": {
            "revision_number": args.revision,
            "parent_revision_ref": parent_ref,
            "canonical_default_spec_ref": None,
            "derived_from_spec_ref": None,
            "feedback_request_ref": None,
            "revision_trigger": args.revision_trigger,
            "change_scopes": args.change_scope or ["metadata_only"],
            "change_summary": args.change_summary or "Builder-derived revision metadata pending",
            "lifecycle_status": "draft",
        },
        "target_context": {"api_profile_ref": profile_reference(api), "available_helper_profile_refs": [profile_reference(item) for item in helpers], "framework_version": api["target"]["framework_version"], "backend_scope": api["target"]["backend_scope"]},
        "knowledge_plan": expanded["knowledge_plan"],
        "validity_constraints": expanded["validity_constraints"],
        "exploration_plan": {"default_branch_id": default["branch_id"], "budget_policy_ref": None if policy_path is None else artifact_ref(policy_path, policy["policy_version"]), "branches": expanded["exploration_plan"]["branches"]},
        "provenance": {"generation_method": "llm", "generator_name": BUILDER_VERSION, "model_name": args.model, "generation_run_id": run_id, "script_ref": copy.deepcopy(generator_refs["script_ref"]), "contract_ref": copy.deepcopy(generator_refs["contract_ref"]), "rules_ref": copy.deepcopy(generator_refs["rules_ref"]), "schema_ref": copy.deepcopy(generator_refs["schema_ref"]), "schema_core_ref": copy.deepcopy(generator_refs["schema_core_ref"]), "generation_trace_ref": copy.deepcopy(generation_trace_ref), "generated_at": utc_now()},
        "review": {"validation_status": "passed", "validation_issues": [], "human_review_status": "not_reviewed", "reviewer_id": None, "reviewed_at": None, "review_notes": None},
    }
    return record


def default_branch(record: dict[str, Any], label: str) -> dict[str, Any]:
    branches = require_list(record["exploration_plan"].get("branches"), f"{label}.branches")
    defaults = [
        require_object(branch, f"{label}.branch")
        for branch in branches
        if isinstance(branch, dict) and branch.get("branch_kind") == "default"
    ]
    if len(defaults) != 1:
        raise InputError(f"{label} must contain exactly one default Branch")
    return defaults[0]


def default_branch_projection(branch: dict[str, Any]) -> dict[str, Any]:
    """Return budget-independent Branch semantics for cross-group comparison."""
    projected = copy.deepcopy(branch)
    projected.pop("budget_share", None)
    return projected


def resolve_canonical_default_spec(
    args: argparse.Namespace,
    schema: dict[str, Any],
    api: dict[str, Any],
    helpers: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if args.mode == "controlled_baseline":
        return None
    canonical = validate_harness_record(
        load_json(args.canonical_default_spec), schema,
        "canonical default HarnessSpec", args
    )
    identity = canonical["identity"]
    if canonical.get("schema_version") != SCHEMA_VERSION:
        raise InputError(
            f"Canonical default HarnessSpec must use active schema v{SCHEMA_VERSION}"
        )
    if (
        identity.get("spec_mode") != "controlled_baseline"
        or identity.get("framework") != api["target"]["framework"]
        or identity.get("target_api") != api["target"]["python_api"]
    ):
        raise InputError("Canonical default HarnessSpec identity is incompatible")
    if canonical["review"].get("validation_status") != "passed":
        raise InputError("Canonical default HarnessSpec is not validated")
    context = canonical["target_context"]
    if context.get("api_profile_ref") != profile_reference(api):
        raise InputError("Canonical default HarnessSpec uses a different API Profile")
    expected_helpers = [profile_reference(item) for item in helpers]
    if context.get("available_helper_profile_refs") != expected_helpers:
        raise InputError("Canonical default HarnessSpec uses a different Helper Profile set")
    if len(canonical["exploration_plan"]["branches"]) != 1:
        raise InputError("Canonical baseline HarnessSpec must contain only its default Branch")
    default_branch(canonical, "canonical default HarnessSpec")
    return canonical


def apply_canonical_default_branch(
    record: dict[str, Any], canonical: dict[str, Any] | None
) -> None:
    if canonical is None:
        return
    current = default_branch(record, "bug-aware HarnessSpec")
    shared = copy.deepcopy(default_branch(canonical, "canonical default HarnessSpec"))
    shared["budget_share"] = current["budget_share"]
    branches = record["exploration_plan"]["branches"]
    index = next(
        index
        for index, branch in enumerate(branches)
        if branch.get("branch_kind") == "default"
    )
    branches[index] = shared
    record["exploration_plan"]["default_branch_id"] = shared["branch_id"]
    record["revision_information"]["canonical_default_spec_ref"] = (
        harness_spec_reference(canonical)
    )
    record["provenance"]["generation_method"] = "hybrid"
    if default_branch_projection(shared) != default_branch_projection(
        default_branch(canonical, "canonical default HarnessSpec")
    ):
        raise ValidationError("Canonical default Branch was not preserved exactly")


def validate_record(
    record: dict[str, Any],
    schema: dict[str, Any],
    args: argparse.Namespace | None = None,
) -> None:
    try:
        validate_harness_record(record, schema, "assembled HarnessSpec", args)
    except InputError as exc:
        raise ValidationError(str(exc).replace("Invalid assembled HarnessSpec: ", "")) from exc


def destination(root: Path, record: dict[str, Any]) -> Path:
    identity = record["identity"]
    revision = record["revision_information"]["revision_number"]
    return (
        root
        / safe_component(identity["framework"])
        / safe_component(identity["target_api"])
        / identity["spec_mode"]
        / f"{safe_component(identity['spec_id'])}_r{revision}.json"
    )


def write_immutable_json(path: Path, value: dict[str, Any], label: str) -> None:
    if path.exists():
        raise BuildError(f"Refusing to overwrite immutable {label}: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        os.link(temporary, path)
    except FileExistsError as exc:
        raise BuildError(f"Concurrent creation detected for {label}: {path}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path: Path, value: dict[str, Any]) -> None:
    write_immutable_json(path, value, "HarnessSpec revision")

def emit_result(
    args: argparse.Namespace,
    payload: dict[str, Any],
    *,
    stream: Any = sys.stdout,
) -> None:
    """Write the stable machine result and retain the human-visible JSON log."""
    if args.result_json is not None:
        write_json(args.result_json, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=stream)




def write_failure(
    path: Path,
    run_id: str,
    errors: list[str],
    generation_trace_refs: list[dict[str, Any]],
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    failure = path.with_suffix(path.suffix + f".{run_id}.failed.json")
    failure.write_text(json.dumps({"builder_version": BUILDER_VERSION, "generation_run_id": run_id, "generated_at": utc_now(), "generation_trace_refs": generation_trace_refs, "errors": compact_errors(errors)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return failure


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--framework", default="pytorch")
    parser.add_argument("--target-api")
    parser.add_argument("--api-profile", type=Path, help="Explicit API Profile; overrides automatic profile discovery.")
    parser.add_argument("--knowledge-binding", action="append", type=json.loads, default=[],
                        help="Exact Knowledge reference as JSON (knowledge_id, schema_version, file_ref); repeat per file. Overrides discovery.")
    parser.add_argument(
        "--helper-profile-set",
        type=Path,
        help="Stable manifest pinning the only Helper Profile revisions eligible for synthesis.",
    )
    parser.add_argument(
        "--canonical-default-spec",
        type=Path,
        help=(
            "Exact validated controlled-baseline HarnessSpec whose default Branch "
            "is reused by an initial bug-aware HarnessSpec."
        ),
    )
    parser.add_argument("--mode", choices=("controlled_baseline", "bug_aware_static", "bug_aware_adaptive"))
    parser.add_argument("--feedback-request", type=Path)
    parser.add_argument("--parent-spec", type=Path)
    parser.add_argument(
        "--review-record",
        type=Path,
        help=(
            "Exact external needs_revision review bound to the immediate parent; "
            "valid only for review-driven LLM regeneration."
        ),
    )
    parser.add_argument(
        "--migrate-v2-2", action="store_true",
        help="Deterministically migrate one validated v2.0/v2.1 controlled Baseline.",
    )
    parser.add_argument(
        "--refresh-api-profile-ref", action="store_true",
        help="Create a deterministic revision that only refreshes the API Profile reference.",
    )
    parser.add_argument("--revision", type=int, default=1)
    parser.add_argument("--revision-trigger", choices=("initial_creation", "manual_review", "source_artifact_update", "regeneration"))
    parser.add_argument("--change-scope", action="append", choices=("initial_definition", "knowledge_selection", "branch_structure", "branch_semantics", "budget_allocation", "target_context", "metadata_only"))
    parser.add_argument("--change-summary")
    for name, path in DEFAULTS.items():
        parser.add_argument("--" + name.replace("_", "-"), type=Path, default=path)
    parser.add_argument("--budget-policy", type=Path, help="Explicit initial budget policy; otherwise use config.paths.initial_budget_policy.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--max-prompt-chars", type=int, default=DEFAULT_MAX_PROMPT_CHARS)
    parser.add_argument(
        "--result-json",
        type=Path,
        help="Immutable machine-readable outcome selected by the orchestrator.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.revision < 1 or args.max_attempts < 1 or args.max_prompt_chars < 1:
        parser.error("--revision, --max-attempts, and --max-prompt-chars must be positive")
    if args.migrate_v2_2:
        if args.parent_spec is None:
            parser.error("--migrate-v2-2 requires --parent-spec")
        if (
            args.feedback_request is not None or args.review_record is not None
            or args.refresh_api_profile_ref
            or args.mode is not None or args.target_api is not None
            or args.api_profile is not None or args.knowledge_binding
            or args.canonical_default_spec is not None or args.budget_policy is not None
            or args.revision != 1 or args.revision_trigger is not None
            or args.change_scope is not None or args.change_summary is not None
        ):
            parser.error("v2.2 migration derives identity, revision, and semantics from its parent")
        return args
    if args.refresh_api_profile_ref:
        if args.parent_spec is None or args.api_profile is None:
            parser.error("--refresh-api-profile-ref requires --parent-spec and --api-profile")
        if (
            args.feedback_request is not None or args.review_record is not None
            or args.mode is not None or args.target_api is not None
        ):
            parser.error("API Profile refresh cannot be combined with feedback, mode, or target API")
        if (
            args.revision != 1 or args.revision_trigger is not None
            or args.change_scope is not None or args.change_summary is not None
            or args.budget_policy is not None
            or args.canonical_default_spec is not None
        ):
            parser.error("API Profile refresh owns revision and change metadata")
        return args
    feedback_mode = args.feedback_request is not None or args.parent_spec is not None
    if feedback_mode:
        if args.feedback_request is None or args.parent_spec is None:
            parser.error("--feedback-request and --parent-spec must be supplied together")
        if args.mode is not None or args.target_api is not None:
            parser.error("feedback application derives --mode and --target-api from inputs")
        if args.review_record is not None:
            parser.error("feedback application cannot use --review-record")
        if (
            args.revision != 1
            or args.revision_trigger is not None
            or args.change_scope is not None
            or args.change_summary is not None
            or args.budget_policy is not None
            or args.canonical_default_spec is not None
        ):
            parser.error("feedback application owns revision and budget metadata")
        return args
    if args.mode is None or args.target_api is None:
        parser.error("initial synthesis requires --mode and --target-api")
    if args.review_record is not None and args.mode == "bug_aware_adaptive":
        parser.error("review-driven regeneration does not revise Adaptive feedback state")
    if args.mode == "controlled_baseline" and args.canonical_default_spec is not None:
        parser.error("controlled baseline cannot use --canonical-default-spec")
    if args.mode != "controlled_baseline" and args.canonical_default_spec is None:
        parser.error("bug-aware initial synthesis requires --canonical-default-spec")
    if args.revision == 1:
        if args.review_record is not None:
            parser.error("revision 1 cannot use --review-record")
        if args.revision_trigger not in (None, "initial_creation"):
            parser.error("revision 1 requires --revision-trigger initial_creation")
        if args.change_scope not in (None, ["initial_definition"]):
            parser.error("revision 1 requires only --change-scope initial_definition")
        if args.change_summary not in (None, "Initial HarnessSpec synthesis"):
            parser.error("revision 1 has a Builder-owned change summary")
        args.revision_trigger = "initial_creation"
        args.change_scope = ["initial_definition"]
        args.change_summary = "Initial HarnessSpec synthesis"
    else:
        if args.revision_trigger is None:
            parser.error("revision 2+ requires --revision-trigger")
        if args.revision_trigger == "initial_creation":
            parser.error("revision 2+ cannot use --revision-trigger initial_creation")
        if args.review_record is not None and args.revision_trigger != "manual_review":
            parser.error("--review-record requires --revision-trigger manual_review")
        if args.review_record is None and args.revision_trigger == "manual_review":
            parser.error("--revision-trigger manual_review requires --review-record")
        if args.change_scope is not None or args.change_summary is not None:
            parser.error(
                "revision 2+ change scopes and summary are derived by the Builder"
            )
        args.change_scope = None
        args.change_summary = None
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        record_schema = load_json(args.record_schema)
        if args.migrate_v2_2:
            run_id = (
                f"schema_migration_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_"
                f"{uuid.uuid4().hex[:12]}"
            )
            return migrate_baseline_to_v2_2(args, record_schema, run_id)
        if args.refresh_api_profile_ref:
            run_id = (
                f"profile_refresh_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_"
                f"{uuid.uuid4().hex[:12]}"
            )
            return build_api_profile_refresh_revision(
                args, record_schema, load_json(args.api_schema), run_id
            )
        if args.feedback_request is not None:
            run_id = (
                f"feedback_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_"
                f"{uuid.uuid4().hex[:12]}"
            )
            return build_feedback_revision(args, record_schema, run_id)
        config = require_object(yaml.safe_load(load_text(args.config)), "config")
        policy: dict[str, Any] | None = None
        policy_path: Path | None = None
        if args.mode != "controlled_baseline":
            if args.mode == "bug_aware_adaptive" and args.revision != 1:
                raise InputError(
                    "Adaptive revision 2+ must use --feedback-request and --parent-spec"
                )
            if args.budget_policy is not None:
                policy_path = args.budget_policy
            else:
                paths = require_object(config.get("paths"), "config.paths")
                configured = require_string(paths.get("initial_budget_policy"), "config.paths.initial_budget_policy")
                policy_path = args.config.parent / configured
            policy = require_object(load_json(policy_path), "budget_policy")
            validate_initial_budget_policy(
                policy,
                revision_number=args.revision,
                revision_trigger=args.revision_trigger,
            )
        contract = load_json(args.contract)
        if contract.get("contract_version") != CONTRACT_VERSION or contract.get("target_schema_version") != SCHEMA_VERSION:
            raise InputError("Contract version is incompatible with this Builder")
        try:
            Draft202012Validator.check_schema(
                require_object(
                    contract.get("semantic_response_schema"),
                    "semantic_response_schema",
                )
            )
        except Exception as exc:
            raise InputError(
                f"Contract semantic_response_schema is invalid: {exc}"
            ) from exc
        rules = load_text(args.rules)
        if not rules.startswith(f"# Knowledge v3 to HarnessSpec Synthesis Rules v{RULES_VERSION}"):
            raise InputError("Rules version is incompatible with this Builder")
        api = select_api_profile(args, load_json(args.api_schema))
        helpers = select_helpers(args, load_json(args.helper_schema), api)
        if args.mode == "controlled_baseline" and args.knowledge_binding:
            raise InputError("Controlled Baseline must not receive Knowledge bindings")
        approved_reviews = (
            set()
            if args.mode == "controlled_baseline"
            else load_approved_knowledge_reviews(args.knowledge_review_ledger)
        )
        knowledge = [] if args.mode == "controlled_baseline" else (
            select_bound_knowledge(
                args.knowledge_binding, args.framework, args.target_api, approved_reviews
            )
            if args.knowledge_binding else select_knowledge(
                args.knowledge_root, args.framework, args.target_api, approved_reviews
            )
        )
        if args.mode != "controlled_baseline" and not knowledge:
            raise InputError("Bug-aware synthesis requires at least one API-specific Knowledge record")
        canonical_default = resolve_canonical_default_spec(
            args, record_schema, api, helpers.available
        )
        parent_record, parent_ref = parent_record_and_reference(
            args, api, record_schema
        )
        review_context, review_record_ref = review_regeneration_context(
            args, parent_record
        )
        if review_context is not None:
            assert parent_record is not None
            validate_manual_review_frozen_inputs(
                parent_record,
                api,
                helpers.available,
                knowledge,
                policy,
                policy_path,
                canonical_default,
            )
        run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:12]}"
        if args.dry_run:
            prompt = build_prompt(
                contract,
                rules,
                api,
                helpers,
                knowledge,
                args.mode,
                [],
                args.max_prompt_chars,
                review_context,
            )
            emit_result(
                args,
                {
                    "target_api": args.target_api,
                    "mode": args.mode,
                    "status": "dry_run",
                    "attempts": 0,
                    "api_profile": api["profile_id"],
                    "available_helper_profile_ids": [
                        item["profile_id"] for item in helpers.available
                    ],
                    "detailed_helper_profile_ids": [
                        item["profile_id"] for item in helpers.detailed
                    ],
                    "dependency_helper_profile_ids": [
                        item["profile_id"] for item in helpers.dependencies
                    ],
                    "fallback_helper_profile_ids": [
                        item["profile_id"] for item in helpers.fallback
                    ],
                    "helper_selection_hash": helpers.selection_hash,
                    "eligible_knowledge_ids": [
                        item["metadata"]["knowledge_id"] for item in knowledge
                    ],
                    "prompt_chars": len(prompt),
                    "max_prompt_chars": args.max_prompt_chars,
                    "parent_revision_ref": parent_ref,
                    "review_record_ref": review_record_ref,
                    "budget_policy_ref": None if policy_path is None else artifact_ref(policy_path, policy["policy_version"]),
                    "canonical_default_spec_ref": (
                        None
                        if canonical_default is None
                        else harness_spec_reference(canonical_default)
                    ),
                    "generation_run_id": run_id,
                },
            )
            return 0
        output_path = revision_path(
            args.output_root,
            api["target"]["framework"],
            args.target_api,
            args.mode,
            args.revision,
        )
        ensure_revision_available(output_path)
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise InputError("DEEPSEEK_API_KEY is required unless --dry-run is used")
        errors: list[str] = []
        generation_trace_refs: list[dict[str, Any]] = []
        previous_response_text: str | None = None
        for attempt in range(1, args.max_attempts + 1):
            response_text: str | None = None
            try:
                prompt = build_prompt(
                    contract, rules, api, helpers, knowledge, args.mode,
                    errors, args.max_prompt_chars, review_context,
                    previous_response_text,
                )
                response_text = call_llm(prompt, api_key, args.model, args.api_url)
                generation_trace_ref = write_generation_trace(
                    args, run_id, attempt, prompt, response_text, errors,
                    review_record_ref,
                )
                generation_trace_refs.append(generation_trace_ref)
                response = json_response(response_text)
                plan = validate_candidate_plan(
                    response,
                    args.mode,
                    knowledge,
                    api,
                    contract,
                    canonical_default,
                )
                record = assemble_record(
                    plan,
                    args,
                    api,
                    helpers.available,
                    knowledge,
                    policy,
                    policy_path,
                    parent_ref,
                    run_id,
                    generation_trace_ref,
                )
                apply_canonical_default_branch(record, canonical_default)
                apply_derived_revision_metadata(record, parent_record)
                validate_record(record, record_schema, args)
                path = destination(args.output_root, record)
                write_json(path, record)
                outcome = asdict(Outcome(args.target_api, args.mode, "success", attempt, str(path)))
                if review_record_ref is not None:
                    outcome["review_record_ref"] = review_record_ref
                emit_result(args, outcome)
                return 0
            except (LLMError, ValidationError, KeyError, TypeError, ValueError) as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
                if response_text is not None:
                    previous_response_text = response_text
        failed = revision_path(args.output_root, api["target"]["framework"], args.target_api, args.mode, args.revision)
        diagnostic = write_failure(failed, run_id, errors, generation_trace_refs)
        outcome = asdict(Outcome(args.target_api, args.mode, "failed", args.max_attempts, diagnostics_path=str(diagnostic), message=compact_errors(errors)[-1]))
        if review_record_ref is not None:
            outcome["review_record_ref"] = review_record_ref
        emit_result(args, outcome, stream=sys.stderr)
        return 1
    except BuildError as exc:
        outcome = asdict(Outcome(args.target_api, args.mode, "input_error", message=str(exc)))
        emit_result(args, outcome, stream=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
