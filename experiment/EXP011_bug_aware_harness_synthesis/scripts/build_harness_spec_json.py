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
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency; install environment/python-control-requirements.txt"
    ) from exc


BUILDER_VERSION = "harness_spec_builder_v0.10"
SCHEMA_VERSION = "1.7"
CONTRACT_VERSION = "1.8"
RULES_VERSION = "1.7"
DEFAULT_MODEL = "deepseek-v4-pro"
DEFAULT_API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MAX_PROMPT_CHARS = 75_000
ROOT = Path("experiment/EXP011_bug_aware_harness_synthesis")
DEFAULTS = {
    "config": ROOT / "config.yaml",
    "record_schema": ROOT / "schemas/harness_spec_record.schema.json",
    "api_schema": ROOT / "schemas/api_profile_record.schema.json",
    "helper_schema": ROOT / "schemas/helper_profile_record.schema.json",
    "contract": ROOT / "schemas/harness_spec_synthesis_contract.json",
    "rules": ROOT / "schemas/knowledge_to_harness_spec_rules.md",
    "api_profiles": ROOT / "api_profiles",
    "helper_profiles": ROOT / "helper_profiles",
    "knowledge_root": Path("experiment/EXP006_historical_bug_pattern_dataset/knowledge_base"),
    "output_root": ROOT / "harness_specs",
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
    if profile["validation"]["validation_status"] == "failed":
        raise InputError("Selected API Profile has failed validation")
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


def select_knowledge(root: Path, framework: str, target_api: str) -> list[dict[str, Any]]:
    if not root.exists():
        raise InputError(f"Knowledge root does not exist: {root}")
    result: list[dict[str, Any]] = []
    ids: set[str] = set()
    for path in sorted(item for item in root.rglob("*.json") if item.is_file()):
        record = load_json(path)
        if record.get("schema_version") != "2.1":
            continue
        scope = record.get("scope")
        if not isinstance(scope, dict) or scope.get("framework") != framework:
            continue
        if target_api not in scope.get("directly_supported_apis", []):
            continue
        ref = knowledge_reference(record)
        if ref["knowledge_id"] in ids:
            raise InputError(f"Duplicate eligible Knowledge ID: {ref['knowledge_id']}")
        ids.add(ref["knowledge_id"])
        result.append(record)
    return sorted(result, key=lambda item: item["metadata"]["knowledge_id"])


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
    return {
        "knowledge_id": record["metadata"]["knowledge_id"],
        "canonical_name": record["metadata"].get("canonical_name"),
        "scope": record["scope"],
        "knowledge_statement": record["knowledge_statement"],
        "applicability": prompt_semantic_view(record["applicability"]),
        "testing_guidance": prompt_semantic_view(record["testing_guidance"]),
        "confidence": record["confidence"],
        "limitations": prompt_semantic_view(record["evidence_basis"].get("limitations", [])),
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
    sections = {
        "instructions": (
            "Return only one JSON object for the semantic portion of a HarnessSpec.\n"
            "Do not emit Markdown, explanations, source code, Helper calls, Strategy "
            "Primitives, or Builder-owned fields. Source References may use only the "
            "supplied API Profile profile_id or eligible Knowledge knowledge_id; never "
            "use nested evidence IDs. Helper Profiles are capability context and must never be "
            "cited as semantic evidence. Every eligible Helper remains available. The "
            "fallback index is for capability discovery only; do not infer unstated "
            "constraints or behavior from its summaries. Target-API reachability is a "
            "downstream execution invariant, not a risk Activation Target."
        ),
        "contract": json.dumps(
            contract, ensure_ascii=False, separators=(",", ":")
        ),
        "rules": rules,
        "input_bundle": json.dumps(
            bundle, ensure_ascii=False, separators=(",", ":")
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


def normalize_plan(plan: dict[str, Any], contract: dict[str, Any], knowledge: list[dict[str, Any]]) -> dict[str, Any]:
    expected = set(contract["response_requirements"]["root_object_keys"])
    reject_unknown_keys(plan, expected, "LLM response")
    if set(plan) != expected:
        raise ValidationError(f"LLM response must contain exactly {sorted(expected)}")
    decisions = require_list(plan["knowledge_plan"].get("knowledge_decisions"), "knowledge_decisions")
    expected_ids = {item["metadata"]["knowledge_id"] for item in knowledge}
    returned_ids = []
    for index, decision in enumerate(decisions):
        item = require_object(decision, f"knowledge_decisions[{index}]")
        returned_ids.append(require_string(item.get("knowledge_id"), f"knowledge_decisions[{index}].knowledge_id"))
    if set(returned_ids) != expected_ids or len(returned_ids) != len(set(returned_ids)):
        raise ValidationError("Exactly one decision is required for every eligible Knowledge record")
    normalize_local_identifiers(plan)
    return plan


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


def normalize_local_identifiers(plan: dict[str, Any]) -> None:
    """Assign deterministic revision-local IDs and rewrite their references."""

    branches = require_list(plan["exploration_plan"].get("branches"), "branches")
    branch_mapping: dict[str, str] = {}
    kind_counts = {"generic_exploration": 0, "knowledge_directed": 0}
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
        elif kind in kind_counts:
            kind_counts[kind] += 1
            prefix = "br_generic" if kind == "generic_exploration" else "br_knowledge"
            new_id = f"{prefix}_{kind_counts[kind]:03d}"
        else:
            raise ValidationError(f"Unsupported branch_kind in branches[{index}]: {kind!r}")
        branch_mapping[old_id] = new_id
        branch["branch_id"] = new_id

    resolutions = require_list(
        plan["knowledge_plan"].get("resolution_records"), "resolution_records"
    )
    for resolution_index, value in enumerate(resolutions, start=1):
        resolution = require_object(value, f"resolution_records[{resolution_index - 1}]")
        require_string(
            resolution.get("resolution_id"),
            f"resolution_records[{resolution_index - 1}].resolution_id",
        )
        resolution["resolution_id"] = f"res_{resolution_index:03d}"
        effects = require_list(
            resolution.get("resolution_effects"),
            f"resolution_records[{resolution_index - 1}].resolution_effects",
        )
        for effect_index, effect_value in enumerate(effects, start=1):
            effect = require_object(
                effect_value,
                f"resolution_records[{resolution_index - 1}].resolution_effects[{effect_index - 1}]",
            )
            require_string(effect.get("effect_id"), "resolution_effect.effect_id")
            effect["effect_id"] = f"eff_{resolution_index:03d}_{effect_index:02d}"
            result_ids = require_list(effect.get("result_branch_ids"), "resolution_effect.result_branch_ids")
            rewritten: list[str] = []
            for result_id in result_ids:
                result_id = require_string(result_id, "resolution_effect.result_branch_ids[]")
                if result_id not in branch_mapping:
                    raise ValidationError(
                        f"Resolution effect references unknown branch ID: {result_id}"
                    )
                rewritten.append(branch_mapping[result_id])
            effect["result_branch_ids"] = rewritten

    global_constraints = require_list(
        plan["validity_constraints"].get("global_constraints"), "global_constraints"
    )
    normalize_id_collection(global_constraints, "constraint_id", "gc", "global_constraints")

    for index, value in enumerate(branches):
        branch = require_object(value, f"branches[{index}]")
        branch_id = branch["branch_id"]
        normalize_id_collection(
            require_list(branch.get("branch_constraints"), f"branches[{index}].branch_constraints"),
            "constraint_id",
            f"bc_{branch_id}",
            f"branches[{index}].branch_constraints",
        )
        normalize_id_collection(
            require_list(branch.get("branch_preconditions"), f"branches[{index}].branch_preconditions"),
            "precondition_id",
            f"pre_{branch_id}",
            f"branches[{index}].branch_preconditions",
        )
        target_properties = require_list(
            branch.get("target_properties"), f"branches[{index}].target_properties"
        )
        target_mapping = normalize_id_collection(
            target_properties,
            "target_property_id",
            f"tp_{branch_id}",
            f"branches[{index}].target_properties",
        )
        activations = require_list(
            branch.get("activation_targets"), f"branches[{index}].activation_targets"
        )
        normalize_id_collection(
            activations,
            "activation_target_id",
            f"act_{branch_id}",
            f"branches[{index}].activation_targets",
        )
        for activation_index, activation_value in enumerate(activations):
            activation = require_object(
                activation_value, f"branches[{index}].activation_targets[{activation_index}]"
            )
            target_id = require_string(
                activation.get("target_property_id"),
                f"branches[{index}].activation_targets[{activation_index}].target_property_id",
            )
            if target_id not in target_mapping:
                raise ValidationError(
                    f"Activation Target references unknown Target Property: {target_id}"
                )
            activation["target_property_id"] = target_mapping[target_id]
        normalize_id_collection(
            require_list(branch.get("oracle_requirements"), f"branches[{index}].oracle_requirements"),
            "oracle_requirement_id",
            f"orc_{branch_id}",
            f"branches[{index}].oracle_requirements",
        )


def compact_knowledge_source_ids(items: list[Any], label: str) -> set[str]:
    result: set[str] = set()
    for index, value in enumerate(items):
        item = require_object(value, f"{label}[{index}]")
        refs = require_list(item.get("source_refs"), f"{label}[{index}].source_refs")
        for ref_index, ref_value in enumerate(refs):
            ref = require_object(ref_value, f"{label}[{index}].source_refs[{ref_index}]")
            if ref.get("source_type") == "knowledge":
                result.add(require_string(ref.get("source_id"), "knowledge source_id"))
    return result


def validate_activation_shape(
    activation: dict[str, Any], requirement_type: str, label: str
) -> None:
    observations = require_list(activation.get("observation_points"), f"{label}.observation_points")
    pairs: list[tuple[str, str]] = []
    for index, value in enumerate(observations):
        observation = require_object(value, f"{label}.observation_points[{index}]")
        pairs.append(
            (
                require_string(observation.get("observation_role"), "observation_role"),
                require_string(observation.get("observation_point"), "observation_point"),
            )
        )
    if len(pairs) != len(set(pairs)):
        raise ValidationError(f"{label} contains duplicate observation points")
    if requirement_type == "state_transition":
        expected = {
            ("before", "before_target_api_call"),
            ("after", "after_target_api_call"),
        }
        if set(pairs) != expected or len(pairs) != 2:
            raise ValidationError(
                f"{label} for state_transition requires one before and one after observation"
            )
    elif len(pairs) != 1 or pairs[0][0] != "evaluate":
        raise ValidationError(
            f"{label} for a non-transition Target Property requires one evaluate observation"
        )


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


def validate_target_requirement(
    target: dict[str, Any],
    api: dict[str, Any],
    contract: dict[str, Any],
    label: str,
) -> str:
    requirement = require_object(target.get("semantic_requirement"), f"{label}.semantic_requirement")
    requirement_type = require_string(
        requirement.get("requirement_type"), f"{label}.semantic_requirement.requirement_type"
    )
    parameter_contracts = require_object(
        contract.get("target_property_parameter_contracts"),
        "contract.target_property_parameter_contracts",
    )
    shape_value = parameter_contracts.get(requirement_type)
    if not isinstance(shape_value, dict):
        allowed = sorted(parameter_contracts)
        raise ValidationError(
            f"{label}.semantic_requirement.requirement_type {requirement_type!r} "
            f"is not valid for a Target Property; use one of {allowed}. "
            "Oracle expectations belong under oracle_requirement.expected_behavior"
        )
    shape = shape_value
    parameters = require_object(
        requirement.get("parameters"), f"{label}.semantic_requirement.parameters"
    )
    required_keys = set(
        require_list(shape.get("required"), f"target_property_parameter_contracts.{requirement_type}.required")
    )
    if set(parameters) != required_keys:
        raise ValidationError(
            f"{label} {requirement_type} parameters must contain exactly {sorted(required_keys)}"
        )

    subject_ids = api_observation_subject_ids(api)
    for key in ("subject_ref", "left_subject_ref", "right_subject_ref"):
        if key in parameters:
            subject_ref = require_string(parameters[key], f"{label}.{key}")
            if subject_ref not in subject_ids:
                raise ValidationError(f"{label}.{key} does not resolve in the API Profile: {subject_ref}")

    property_pattern = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")
    for key in ("property_ref", "left_property_ref", "right_property_ref"):
        if key in parameters:
            property_ref = require_string(parameters[key], f"{label}.{key}")
            if not property_pattern.fullmatch(property_ref):
                raise ValidationError(f"{label}.{key} is not a normalized property path")

    for vocabulary_key, parameter_key in (
        ("operators", "operator"),
        ("relations", "relation"),
        ("transitions", "transition"),
    ):
        if parameter_key in parameters:
            allowed = set(require_list(shape.get(vocabulary_key), f"{requirement_type}.{vocabulary_key}"))
            if parameters[parameter_key] not in allowed:
                raise ValidationError(
                    f"{label}.{parameter_key} is not allowed for {requirement_type}"
                )
    if requirement_type == "set_membership" and not require_list(parameters["values"], f"{label}.values"):
        raise ValidationError(f"{label}.values must not be empty")
    if requirement_type == "range_constraint":
        if parameters["lower_bound"] is None and parameters["upper_bound"] is None:
            raise ValidationError(f"{label} range_constraint requires at least one bound")
        if not isinstance(parameters["lower_inclusive"], bool) or not isinstance(
            parameters["upper_inclusive"], bool
        ):
            raise ValidationError(f"{label} range inclusivity flags must be booleans")

    backend_scope = api.get("target", {}).get("backend_scope")
    if (
        isinstance(backend_scope, list)
        and len(backend_scope) == 1
        and isinstance(backend_scope[0], str)
        and backend_scope[0]
        and parameters.get("subject_ref") == "context.backend"
        and parameters.get("property_ref") == "backend"
        and parameters.get("operator") == "equals"
        and parameters.get("expected_value") == backend_scope[0]
    ):
        raise ValidationError(
            f"{label} restates the singleton API Profile backend_scope as a "
            "Target Property; fixed context.backend belongs to target_context, "
            "not an Activation Target"
        )
    return requirement_type


def validate_oracle_observation_subjects(
    oracle: dict[str, Any],
    api: dict[str, Any],
    contract: dict[str, Any],
    label: str,
) -> None:
    oracle_type = require_string(oracle.get("oracle_type"), f"{label}.oracle_type")
    allowed_types = set(
        require_list(contract["allowed_values"].get("oracle_type"), "allowed_values.oracle_type")
    )
    if oracle_type not in allowed_types:
        raise ValidationError(
            f"{label}.oracle_type {oracle_type!r} is invalid; use one of "
            f"{sorted(allowed_types)}. Expected outcomes such as no_crash belong "
            "under expected_behavior.requirement_type"
        )
    subjects = require_list(
        oracle.get("observation_subjects"), f"{label}.observation_subjects"
    )
    if not subjects:
        raise ValidationError(f"{label}.observation_subjects must not be empty")
    normalized = [
        require_string(subject, f"{label}.observation_subjects[{index}]")
        for index, subject in enumerate(subjects)
    ]
    if len(normalized) != len(set(normalized)):
        raise ValidationError(f"{label}.observation_subjects contains duplicates")
    allowed = api_observation_subject_ids(api)
    unknown = sorted(set(normalized) - allowed)
    if unknown:
        raise ValidationError(
            f"{label}.observation_subjects do not resolve in the API Profile: {unknown}"
        )


def validate_plan(
    plan: dict[str, Any],
    mode: str,
    knowledge: list[dict[str, Any]],
    api: dict[str, Any],
    contract: dict[str, Any],
) -> None:
    decisions = plan["knowledge_plan"]["knowledge_decisions"]
    resolutions = plan["knowledge_plan"].get("resolution_records")
    branches = plan["exploration_plan"].get("branches")
    if not isinstance(resolutions, list) or not isinstance(branches, list) or not branches:
        raise ValidationError("Resolution records and non-empty branches are required")
    if mode == "controlled_baseline" and (decisions or resolutions):
        raise ValidationError("Controlled baseline cannot use Knowledge decisions or resolutions")
    if mode == "controlled_baseline" and (
        len(branches) != 1 or not isinstance(branches[0], dict) or branches[0].get("branch_kind") != "default"
    ):
        raise ValidationError("Controlled baseline must contain exactly one default branch")
    if mode != "controlled_baseline" and len(decisions) != len(knowledge):
        raise ValidationError("Bug-aware mode must decide every supplied Knowledge record")
    selected_reason_codes: dict[str, set[str]] = {}
    for decision_index, decision_value in enumerate(decisions):
        decision = require_object(
            decision_value, f"knowledge_decisions[{decision_index}]"
        )
        knowledge_id = require_string(
            decision.get("knowledge_id"),
            f"knowledge_decisions[{decision_index}].knowledge_id",
        )
        reason_codes = set(
            require_list(
                decision.get("reason_codes"),
                f"knowledge_decisions[{decision_index}].reason_codes",
            )
        )
        if (
            "oracle_only_contribution" in reason_codes
            and decision.get("selection_status") != "selected"
        ):
            raise ValidationError(
                "oracle_only_contribution is valid only for selected Knowledge"
            )
        if decision.get("selection_status") == "selected":
            selected_reason_codes[knowledge_id] = reason_codes
    selected = set(selected_reason_codes)
    substantive_knowledge_ids = compact_knowledge_source_ids(
        require_list(plan["validity_constraints"].get("global_constraints"), "global_constraints"),
        "global_constraints",
    )
    defaults = 0
    for index, branch in enumerate(branches):
        item = require_object(branch, f"branches[{index}]")
        kind = item.get("branch_kind")
        defaults += kind == "default"
        ids = require_list(item.get("source_knowledge_ids"), f"branches[{index}].source_knowledge_ids")
        local_semantic_items: list[Any] = []
        for field in (
            "branch_constraints",
            "branch_preconditions",
            "target_properties",
            "oracle_requirements",
        ):
            local_semantic_items.extend(require_list(item.get(field), f"branches[{index}].{field}"))
        local_knowledge_ids = compact_knowledge_source_ids(
            local_semantic_items, f"branches[{index}].semantic_items"
        )
        substantive_knowledge_ids.update(local_knowledge_ids)
        if kind == "knowledge_directed":
            if not ids or set(ids) != local_knowledge_ids or not set(ids).issubset(selected):
                raise ValidationError(
                    "Knowledge-directed branch source IDs must equal its selected branch-local Knowledge contributions"
                )
        elif ids or local_knowledge_ids:
            raise ValidationError("Default/generic branch cannot cite Knowledge")

        branch_dimensions = set(
            require_list(item.get("risk_dimensions"), f"branches[{index}].risk_dimensions")
        )
        target_properties = require_list(
            item.get("target_properties"), f"branches[{index}].target_properties"
        )
        target_knowledge_ids = compact_knowledge_source_ids(
            target_properties, f"branches[{index}].target_properties"
        )
        if kind == "knowledge_directed":
            branch_knowledge_ids = set(ids)
            oracle_only_ids = {
                knowledge_id
                for knowledge_id in branch_knowledge_ids
                if "oracle_only_contribution"
                in selected_reason_codes.get(knowledge_id, set())
            }
            missing_targets = sorted(
                branch_knowledge_ids - oracle_only_ids - target_knowledge_ids
            )
            if missing_targets:
                raise ValidationError(
                    "Knowledge contributions without oracle_only_contribution "
                    f"must be cited by a Target Property: {missing_targets}"
                )
            contradictory_targets = sorted(oracle_only_ids & target_knowledge_ids)
            if contradictory_targets:
                raise ValidationError(
                    "oracle_only_contribution Knowledge must not be cited by a "
                    f"Target Property: {contradictory_targets}"
                )
        else:
            oracle_only_ids = set()
        targets_by_id: dict[str, dict[str, Any]] = {}
        for target_index, target_value in enumerate(target_properties):
            target = require_object(
                target_value, f"branches[{index}].target_properties[{target_index}]"
            )
            target_id = require_string(target.get("target_property_id"), "target_property_id")
            if target_id in targets_by_id:
                raise ValidationError(f"Duplicate Target Property ID in branch: {target_id}")
            target_dimensions = set(
                require_list(target.get("risk_dimensions"), "target_property.risk_dimensions")
            )
            if not target_dimensions or not target_dimensions.issubset(branch_dimensions):
                raise ValidationError(
                    f"Target Property risk dimensions must be a non-empty subset of its branch: {target_id}"
                )
            validate_target_requirement(
                target,
                api,
                contract,
                f"branches[{index}].target_properties[{target_index}]",
            )
            targets_by_id[target_id] = target
        activations = require_list(item.get("activation_targets"), f"branches[{index}].activation_targets")
        activated_target_ids: set[str] = set()
        for activation_index, activation_value in enumerate(activations):
            activation = require_object(
                activation_value, f"branches[{index}].activation_targets[{activation_index}]"
            )
            target_id = require_string(activation.get("target_property_id"), "target_property_id")
            if target_id not in targets_by_id or target_id in activated_target_ids:
                raise ValidationError(
                    "Each Activation Target must reference one distinct Target Property in its branch"
                )
            activated_target_ids.add(target_id)
            requirement = require_object(
                targets_by_id[target_id].get("semantic_requirement"),
                f"target_properties[{target_id}].semantic_requirement",
            )
            validate_activation_shape(
                activation,
                require_string(requirement.get("requirement_type"), "requirement_type"),
                f"branches[{index}].activation_targets[{activation_index}]",
            )
        if activated_target_ids != set(targets_by_id):
            raise ValidationError(
                "Every Target Property must have exactly one Activation Target in its branch"
            )
        oracles = require_list(item.get("oracle_requirements"), f"branches[{index}].oracle_requirements")
        for oracle_index, oracle_value in enumerate(oracles):
            oracle = require_object(
                oracle_value,
                f"branches[{index}].oracle_requirements[{oracle_index}]",
            )
            validate_oracle_observation_subjects(
                oracle,
                api,
                contract,
                f"branches[{index}].oracle_requirements[{oracle_index}]",
            )
        if not any(isinstance(entry, dict) and entry.get("requirement_level") == "required" for entry in oracles):
            raise ValidationError("Every branch must include a required Oracle")
        if oracle_only_ids:
            oracle_knowledge_ids = compact_knowledge_source_ids(
                oracles, f"branches[{index}].oracle_requirements"
            )
            missing_oracle_evidence = sorted(oracle_only_ids - oracle_knowledge_ids)
            if missing_oracle_evidence:
                raise ValidationError(
                    "oracle_only_contribution Knowledge must be cited by an Oracle: "
                    f"{missing_oracle_evidence}"
                )
    if defaults != 1:
        raise ValidationError("Exactly one default branch is required")
    if not selected.issubset(substantive_knowledge_ids):
        missing = sorted(selected - substantive_knowledge_ids)
        raise ValidationError(
            f"Selected Knowledge has no substantive HarnessSpec contribution: {missing}"
        )


def source_lookup(api: dict[str, Any], _helpers: list[dict[str, Any]], knowledge: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    records: list[tuple[str, dict[str, Any], str | int]] = [("api_profile", api, api["revision"])]
    for source_type, profile, version in records:
        lookup[(source_type, profile["profile_id"])] = {"source_type": source_type, "source_id": profile["profile_id"], "source_version": version, "content_hash": profile["metadata"]["content_hash"]}
    for item in knowledge:
        ref = knowledge_reference(item)
        lookup[("knowledge", ref["knowledge_id"])] = {"source_type": "knowledge", "source_id": ref["knowledge_id"], "source_version": ref["schema_version"], "content_hash": ref["content_hash"]}
    return lookup


def expand_source_refs(value: Any, lookup: dict[tuple[str, str], dict[str, Any]]) -> Any:
    if isinstance(value, list):
        return [expand_source_refs(item, lookup) for item in value]
    if not isinstance(value, dict):
        return value
    if "source_type" in value or "source_id" in value:
        if set(value) != {"source_type", "source_id"}:
            raise ValidationError("An LLM source reference must contain exactly source_type and source_id")
        key = (value["source_type"], value["source_id"])
        if key not in lookup:
            raise ValidationError(f"LLM cited an unavailable source reference: {key}")
        return copy.deepcopy(lookup[key])
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
            if not refs:
                raise ValidationError(f"{child} must not be empty")
            for index, reference in enumerate(refs):
                reference = require_object(reference, f"{child}[{index}]")
                expected = {"source_type", "source_id", "source_version", "content_hash"}
                if set(reference) != expected:
                    raise ValidationError(f"{child}[{index}] must be a complete expanded source reference")
                source_key = (reference["source_type"], reference["source_id"])
                if source_key not in lookup or reference != lookup[source_key]:
                    raise ValidationError(f"{child}[{index}] does not match an eligible source artifact")
                if reference["source_type"] == "knowledge" and reference["source_id"] not in selected_knowledge_ids:
                    raise ValidationError(f"{child}[{index}] cites Knowledge that was not selected")
        else:
            validate_expanded_source_refs(item, lookup, selected_knowledge_ids, child)


def validate_initial_budget_policy(policy: dict[str, Any]) -> None:
    require_string(policy.get("policy_version"), "budget_policy.policy_version")
    require_string(policy.get("policy_id"), "budget_policy.policy_id")
    scope = require_object(policy.get("scope"), "budget_policy.scope")
    modes = require_list(scope.get("applicable_spec_modes"), "budget_policy.scope.applicable_spec_modes")
    if set(modes) != {"bug_aware_static", "bug_aware_adaptive"}:
        raise InputError("Initial budget policy must apply only to the two bug-aware modes")
    if scope.get("applicable_revision_number") != 1 or scope.get("state_isolation") != "per_harness_spec":
        raise InputError("Initial budget policy must be isolated per HarnessSpec revision 1")

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
        if parent["revision_information"]["revision_number"] != 1:
            raise InputError("Shared Static H0 must be HarnessSpec revision 1")
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
    parent = validate_profile_record(
        load_json(args.parent_spec), record_schema, "parent HarnessSpec"
    )
    if parent["review"]["validation_status"] != "passed":
        raise InputError("Parent HarnessSpec validation_status is not passed")
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
    candidate["provenance"] = {
        "generation_method": "script",
        "generator_name": BUILDER_VERSION,
        "model_name": None,
        "generation_run_id": run_id,
        "script_ref": artifact_ref(Path(__file__).resolve(), BUILDER_VERSION),
        "contract_ref": copy.deepcopy(parent["provenance"]["contract_ref"]),
        "rules_ref": copy.deepcopy(parent["provenance"]["rules_ref"]),
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
    validate_record(candidate, record_schema)
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
    parent = validate_profile_record(
        load_json(args.parent_spec), record_schema, "parent HarnessSpec"
    )
    new_api = validate_profile_record(
        load_json(args.api_profile), api_schema, "replacement API Profile"
    )
    if parent["review"]["validation_status"] != "passed":
        raise InputError("Parent HarnessSpec validation_status is not passed")
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
    candidate["provenance"] = {
        "generation_method": "script",
        "generator_name": BUILDER_VERSION,
        "model_name": None,
        "generation_run_id": run_id,
        "script_ref": artifact_ref(Path(__file__).resolve(), BUILDER_VERSION),
        "contract_ref": copy.deepcopy(parent["provenance"]["contract_ref"]),
        "rules_ref": copy.deepcopy(parent["provenance"]["rules_ref"]),
        "generated_at": utc_now(),
    }
    candidate["review"] = {
        "validation_status": "passed", "validation_issues": [],
        "human_review_status": "not_reviewed", "reviewer_id": None,
        "reviewed_at": None, "review_notes": None,
    }
    validate_record(candidate, record_schema)
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


def artifact_ref(path: Path, version: str | int | None) -> dict[str, Any]:
    return {"artifact_id": path.name, "artifact_version": version, "content_hash": file_hash(path)}


def spec_id_for(framework: str, target_api: str, mode: str) -> str:
    return f"hs_{safe_component(framework)}_{safe_component(target_api)}_{mode}"


def revision_path(root: Path, framework: str, target_api: str, mode: str, revision: int) -> Path:
    spec_id = spec_id_for(framework, target_api, mode)
    return root / safe_component(framework) / safe_component(target_api) / mode / f"{spec_id}_r{revision}.json"


def parent_reference(args: argparse.Namespace, api: dict[str, Any], record_schema: dict[str, Any]) -> dict[str, Any] | None:
    if args.revision == 1:
        return None
    parent_path = revision_path(args.output_root, api["target"]["framework"], args.target_api, args.mode, args.revision - 1)
    parent = validate_profile_record(load_json(parent_path), record_schema, "parent HarnessSpec")
    expected_identity = {
        "spec_id": spec_id_for(api["target"]["framework"], args.target_api, args.mode),
        "framework": api["target"]["framework"],
        "target_api": args.target_api,
        "spec_mode": args.mode,
    }
    if parent["identity"] != expected_identity or parent["revision_information"]["revision_number"] != args.revision - 1:
        raise InputError("Parent HarnessSpec identity or revision does not match the requested child")
    return {
        "spec_id": parent["identity"]["spec_id"],
        "revision_number": args.revision - 1,
        "content_hash": canonical_hash(parent),
    }


def assemble_record(plan: dict[str, Any], args: argparse.Namespace, api: dict[str, Any], helpers: list[dict[str, Any]], knowledge: list[dict[str, Any]], policy: dict[str, Any] | None, policy_path: Path | None, parent_ref: dict[str, Any] | None, run_id: str) -> dict[str, Any]:
    branches = copy.deepcopy(plan["exploration_plan"]["branches"])
    allocate_budget(branches, policy, args.mode)
    default = next(item for item in branches if item["branch_kind"] == "default")
    lookup = source_lookup(api, helpers, knowledge)
    expanded = expand_source_refs({"knowledge_plan": plan["knowledge_plan"], "validity_constraints": plan["validity_constraints"], "exploration_plan": {"branches": branches}}, lookup)
    selected_ids = {item["knowledge_id"] for item in expanded["knowledge_plan"]["knowledge_decisions"] if item["selection_status"] == "selected"}
    validate_expanded_source_refs(expanded, lookup, selected_ids)
    references = {item["metadata"]["knowledge_id"]: knowledge_reference(item) for item in knowledge}
    for decision in expanded["knowledge_plan"]["knowledge_decisions"]:
        decision["knowledge_ref"] = references[decision.pop("knowledge_id")]
    framework = api["target"]["framework"]
    spec_id = spec_id_for(framework, args.target_api, args.mode)
    return {
        "schema_version": SCHEMA_VERSION,
        "identity": {"spec_id": spec_id, "framework": framework, "target_api": args.target_api, "spec_mode": args.mode},
        "revision_information": {
            "revision_number": args.revision,
            "parent_revision_ref": parent_ref,
            "derived_from_spec_ref": None,
            "feedback_request_ref": None,
            "revision_trigger": args.revision_trigger,
            "change_scopes": args.change_scope,
            "change_summary": args.change_summary,
            "lifecycle_status": "draft",
        },
        "target_context": {"api_profile_ref": profile_reference(api), "available_helper_profile_refs": [profile_reference(item) for item in helpers], "framework_version": api["target"]["framework_version"], "backend_scope": api["target"]["backend_scope"]},
        "knowledge_plan": expanded["knowledge_plan"],
        "validity_constraints": expanded["validity_constraints"],
        "exploration_plan": {"default_branch_id": default["branch_id"], "budget_policy_ref": None if policy_path is None else artifact_ref(policy_path, policy["policy_version"]), "branches": expanded["exploration_plan"]["branches"]},
        "provenance": {"generation_method": "llm", "generator_name": BUILDER_VERSION, "model_name": args.model, "generation_run_id": run_id, "script_ref": artifact_ref(Path(__file__).resolve(), BUILDER_VERSION), "contract_ref": artifact_ref(args.contract, CONTRACT_VERSION), "rules_ref": artifact_ref(args.rules, RULES_VERSION), "generated_at": utc_now()},
        "review": {"validation_status": "passed", "validation_issues": [], "human_review_status": "not_reviewed", "reviewer_id": None, "reviewed_at": None, "review_notes": None},
    }


def validate_record(record: dict[str, Any], schema: dict[str, Any]) -> None:
    errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(record), key=lambda item: item.json_path)
    if errors:
        message = "\n".join(f"{item.json_path}: {item.message}" for item in errors[:12])
        raise ValidationError(f"Assembled record violates HarnessSpec Schema:\n{message}")


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


def write_json(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise BuildError(f"Refusing to overwrite immutable HarnessSpec revision: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        os.link(temporary, path)
    except FileExistsError as exc:
        raise BuildError(f"Concurrent creation detected for HarnessSpec revision: {path}") from exc
    finally:
        temporary.unlink(missing_ok=True)

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




def write_failure(path: Path, run_id: str, errors: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    failure = path.with_suffix(path.suffix + f".{run_id}.failed.json")
    failure.write_text(json.dumps({"builder_version": BUILDER_VERSION, "generation_run_id": run_id, "generated_at": utc_now(), "errors": compact_errors(errors)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return failure


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--framework", default="pytorch")
    parser.add_argument("--target-api")
    parser.add_argument("--api-profile", type=Path, help="Explicit API Profile; overrides automatic profile discovery.")
    parser.add_argument(
        "--helper-profile-set",
        type=Path,
        help="Stable manifest pinning the only Helper Profile revisions eligible for synthesis.",
    )
    parser.add_argument("--mode", choices=("controlled_baseline", "bug_aware_static", "bug_aware_adaptive"))
    parser.add_argument("--feedback-request", type=Path)
    parser.add_argument("--parent-spec", type=Path)
    parser.add_argument(
        "--refresh-api-profile-ref", action="store_true",
        help="Create a deterministic revision that only refreshes the API Profile reference.",
    )
    parser.add_argument("--revision", type=int, default=1)
    parser.add_argument("--revision-trigger", choices=("initial_creation", "manual_review", "source_artifact_update", "regeneration"))
    parser.add_argument("--change-scope", action="append", choices=("initial_definition", "knowledge_selection", "relationship_resolution", "global_constraints", "branch_structure", "branch_semantics", "budget_allocation", "activation_plan", "oracle_plan", "target_context", "metadata_only"))
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
    if args.refresh_api_profile_ref:
        if args.parent_spec is None or args.api_profile is None:
            parser.error("--refresh-api-profile-ref requires --parent-spec and --api-profile")
        if args.feedback_request is not None or args.mode is not None or args.target_api is not None:
            parser.error("API Profile refresh cannot be combined with feedback, mode, or target API")
        if (
            args.revision != 1 or args.revision_trigger is not None
            or args.change_scope is not None or args.change_summary is not None
            or args.budget_policy is not None
        ):
            parser.error("API Profile refresh owns revision and change metadata")
        return args
    feedback_mode = args.feedback_request is not None or args.parent_spec is not None
    if feedback_mode:
        if args.feedback_request is None or args.parent_spec is None:
            parser.error("--feedback-request and --parent-spec must be supplied together")
        if args.mode is not None or args.target_api is not None:
            parser.error("feedback application derives --mode and --target-api from inputs")
        if (
            args.revision != 1
            or args.revision_trigger is not None
            or args.change_scope is not None
            or args.change_summary is not None
            or args.budget_policy is not None
        ):
            parser.error("feedback application owns revision and budget metadata")
        return args
    if args.mode is None or args.target_api is None:
        parser.error("initial synthesis requires --mode and --target-api")
    if args.revision == 1:
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
        if args.revision_trigger is None or not args.change_scope or not args.change_summary:
            parser.error("revision 2+ requires --revision-trigger, --change-scope, and --change-summary")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        record_schema = load_json(args.record_schema)
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
            if args.revision != 1:
                raise InputError("Manual bug-aware revision 2+ synthesis is unsupported; use --feedback-request and --parent-spec")
            if args.budget_policy is not None:
                policy_path = args.budget_policy
            else:
                paths = require_object(config.get("paths"), "config.paths")
                configured = require_string(paths.get("initial_budget_policy"), "config.paths.initial_budget_policy")
                policy_path = args.config.parent / configured
            policy = require_object(load_json(policy_path), "budget_policy")
            validate_initial_budget_policy(policy)
        contract = load_json(args.contract)
        if contract.get("contract_version") != CONTRACT_VERSION or contract.get("target_schema_version") != SCHEMA_VERSION:
            raise InputError("Contract version is incompatible with this Builder")
        rules = load_text(args.rules)
        if not rules.startswith(f"# Knowledge-to-HarnessSpec Synthesis Rules v{RULES_VERSION}"):
            raise InputError("Rules version is incompatible with this Builder")
        api = select_api_profile(args, load_json(args.api_schema))
        helpers = select_helpers(args, load_json(args.helper_schema), api)
        knowledge = [] if args.mode == "controlled_baseline" else select_knowledge(args.knowledge_root, args.framework, args.target_api)
        if args.mode != "controlled_baseline" and not knowledge:
            raise InputError("Bug-aware synthesis requires at least one API-specific Knowledge record")
        parent_ref = parent_reference(args, api, record_schema)
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
                    "budget_policy_ref": None if policy_path is None else artifact_ref(policy_path, policy["policy_version"]),
                    "generation_run_id": run_id,
                },
            )
            return 0
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise InputError("DEEPSEEK_API_KEY is required unless --dry-run is used")
        errors: list[str] = []
        for attempt in range(1, args.max_attempts + 1):
            try:
                prompt = build_prompt(contract, rules, api, helpers, knowledge, args.mode, errors, args.max_prompt_chars)
                response = json_response(call_llm(prompt, api_key, args.model, args.api_url))
                plan = normalize_plan(response, contract, knowledge)
                validate_plan(plan, args.mode, knowledge, api, contract)
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
                )
                validate_record(record, record_schema)
                path = destination(args.output_root, record)
                write_json(path, record)
                outcome = asdict(Outcome(args.target_api, args.mode, "success", attempt, str(path)))
                emit_result(args, outcome)
                return 0
            except (LLMError, ValidationError, KeyError, TypeError, ValueError) as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
        failed = revision_path(args.output_root, api["target"]["framework"], args.target_api, args.mode, args.revision)
        diagnostic = write_failure(failed, run_id, errors)
        outcome = asdict(Outcome(args.target_api, args.mode, "failed", args.max_attempts, diagnostics_path=str(diagnostic), message=compact_errors(errors)[-1]))
        emit_result(args, outcome, stream=sys.stderr)
        return 1
    except BuildError as exc:
        outcome = asdict(Outcome(args.target_api, args.mode, "input_error", message=str(exc)))
        emit_result(args, outcome, stream=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
