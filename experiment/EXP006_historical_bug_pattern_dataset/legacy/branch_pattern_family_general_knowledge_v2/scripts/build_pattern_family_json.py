from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

try:
    from build_pattern_family_candidates import (
        candidate_group_hash as recompute_candidate_group_hash,
        canonical_json_hash,
    )
except ImportError as exc:
    raise RuntimeError(
        "Unable to import deterministic Candidate hash helpers from "
        "build_pattern_family_candidates.py."
    ) from exc


SCRIPT_VERSION = "build_pattern_family_json_v0_1"

DECISION_RECORD_VERSION = "1.0"
CONVERSION_RUN_INDEX_VERSION = "1.1"
FAMILY_SCHEMA_VERSION = "1.1"
PROMPT_VERSION = "pattern_family_extract_v1"

DECISION_VALIDATOR_VERSION = "pattern_family_decision_validator_v0_1"
FAMILY_VALIDATOR_VERSION = "pattern_family_validator_v0_1"

EXISTING_FAMILY_RETRIEVAL_VERSION = "builtin-1.0"
MATERIALIZATION_VERSION = "builtin-1.0"

DEFAULT_PROVIDER = "deepseek"
DEFAULT_MODEL = os.environ.get(
    "PATTERN_FAMILY_MODEL",
    "deepseek-v4-pro",
)
DEFAULT_API_URL = os.environ.get(
    "PATTERN_FAMILY_API_URL",
    "https://api.deepseek.com/chat/completions",
)

DEFAULT_MAX_OUTPUT_TOKENS = 12000
DEFAULT_MAX_ATTEMPTS = 2
DEFAULT_MAX_EXISTING_FAMILIES = 3

SCRIPT_DIR = Path(__file__).resolve().parent
EXP006_DIR = SCRIPT_DIR.parent
SCHEMA_DIR = EXP006_DIR / "schemas"

CANDIDATE_ROOT = (
    EXP006_DIR
    / "quality"
    / "pattern_family_candidates"
)

DECISION_ROOT = (
    EXP006_DIR
    / "quality"
    / "pattern_family_decisions"
    / "objects"
)

CONVERSION_RUN_ROOT = (
    EXP006_DIR
    / "quality"
    / "pattern_family_conversion_runs"
)

FAMILY_ROOT = EXP006_DIR / "pattern_families"

DEFAULT_CANDIDATE_POLICY_PATH = (
    SCHEMA_DIR
    / "pattern_family_candidate_policy.json"
)

DEFAULT_FAMILY_CONTRACT_PATH = (
    SCHEMA_DIR
    / "pattern_family_extraction_contract.json"
)

DEFAULT_FAMILY_RULES_PATH = (
    SCHEMA_DIR
    / "patterns_to_family_rules.md"
)

DEFAULT_FAMILY_SCHEMA_PATH = (
    SCHEMA_DIR
    / "pattern_family_schema.md"
)


PROMPT_TEMPLATE = """You are validating whether API-specific historical bug Patterns form one or more evidence-grounded Pattern Families.

Follow these boundaries strictly:

1. Candidate retrieval signals are only retrieval evidence. They are not sufficient Family membership evidence.
2. Base semantic claims only on the supplied Pattern projections.
3. Preserve uncertainty. Do not invent missing triggers, mechanisms, failures, APIs, Reports, or evidence references.
4. Use only existing Family IDs explicitly supplied in EXISTING_FAMILY_CONTEXT.
5. Do not produce General Knowledge, testing strategies, HarnessSpec, executable predicates, code, or concrete fuzz inputs.
6. Return exactly one JSON object matching FAMILY_EXTRACTION_CONTRACT.
7. Return JSON only. Do not use Markdown fences, comments, or explanatory text.

CANDIDATE_CONTEXT
{candidate_context}

PATTERN_PROJECTIONS
{pattern_projections}

EXISTING_FAMILY_CONTEXT
{existing_family_context}

FAMILY_EXTRACTION_CONTRACT
{family_contract}

PATTERNS_TO_FAMILY_RULES
{family_rules}
"""


class PipelineError(Exception):
    def __init__(
        self,
        stage: str,
        code: str,
        message: str,
        recoverable: bool = True,
        failed_attempts: (
            list[dict[str, Any]]
            | None
        ) = None,
        token_usage: (
            dict[str, int]
            | None
        ) = None,
        llm_call_count: int = 0,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.code = code
        self.message = message
        self.recoverable = recoverable
        self.failed_attempts = (
            copy.deepcopy(
                failed_attempts
            )
            if failed_attempts
            is not None
            else []
        )
        self.token_usage = (
            copy.deepcopy(
                token_usage
            )
            if token_usage
            is not None
            else {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            }
        )
        self.llm_call_count = (
            llm_call_count
        )

    def as_record(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "code": self.code,
            "message": self.message,
            "recoverable": self.recoverable,
        }


class ContractValidationError(PipelineError):
    def __init__(
        self,
        code: str,
        message: str,
    ) -> None:
        super().__init__(
            stage="decision_validation",
            code=code,
            message=message,
            recoverable=True,
        )


def utc_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_hash(value: Any) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            canonical_json_bytes(value)
        ).hexdigest()
    )


def text_hash(value: str) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            value.encode("utf-8")
        ).hexdigest()
    )


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        while True:
            block = file.read(1024 * 1024)

            if not block:
                break

            digest.update(block)

    return f"sha256:{digest.hexdigest()}"


def pretty_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            value = json.load(file)
    except FileNotFoundError as exc:
        raise PipelineError(
            "candidate_loading",
            "file_not_found",
            f"Required file does not exist: {path}",
            False,
        ) from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(
            "candidate_loading",
            "invalid_json_file",
            f"Invalid JSON file: {path}",
            False,
        ) from exc

    if not isinstance(value, dict):
        raise PipelineError(
            "candidate_loading",
            "invalid_top_level_type",
            f"Top-level JSON value must be an object: {path}",
            False,
        )

    return value


def write_json_exclusive(
    path: Path,
    value: Any,
) -> str:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    data = pretty_json_bytes(value)

    descriptor, temporary_name = (
        tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
    )
    temporary_path = Path(
        temporary_name
    )

    try:
        with os.fdopen(
            descriptor,
            "wb",
        ) as file:
            file.write(data)
            file.flush()
            os.fsync(
                file.fileno()
            )

        try:
            os.link(
                temporary_path,
                path,
            )
        except FileExistsError as exc:
            raise PipelineError(
                "artifact_write",
                "artifact_already_exists",
                "Refusing to overwrite existing artifact: "
                f"{path}",
                False,
            ) from exc
        except OSError as exc:
            raise PipelineError(
                "artifact_write",
                "atomic_publish_failed",
                "Unable to atomically publish artifact: "
                f"{path}",
                False,
            ) from exc

    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass

    return (
        "sha256:"
        + hashlib.sha256(
            data
        ).hexdigest()
    )


def slugify(value: str) -> str:
    result = value.strip().lower()
    result = re.sub(
        r"[^a-z0-9]+",
        "_",
        result,
    )
    result = re.sub(
        r"_+",
        "_",
        result,
    )
    return result.strip("_")


def framework_prefix(framework: str) -> str:
    normalized = slugify(framework)

    known = {
        "pytorch": "pt",
        "tensorflow": "tf",
        "jax": "jx",
        "mindspore": "ms",
    }

    if normalized in known:
        return known[normalized]

    letters = re.sub(
        r"[^a-z0-9]",
        "",
        normalized,
    )

    if len(letters) < 2:
        raise PipelineError(
            "configuration",
            "invalid_framework",
            f"Cannot derive framework prefix from {framework!r}.",
            False,
        )

    return letters[:2]


def require_dict(
    value: Any,
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractValidationError(
            "invalid_object",
            f"{label} must be an object.",
        )

    return value


def require_list(
    value: Any,
    label: str,
) -> list[Any]:
    if not isinstance(value, list):
        raise ContractValidationError(
            "invalid_array",
            f"{label} must be an array.",
        )

    return value


def require_string(
    value: Any,
    label: str,
) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
    ):
        raise ContractValidationError(
            "missing_required_text",
            f"{label} must be a non-empty string.",
        )

    return value.strip()


def require_enum(
    value: Any,
    allowed: set[str],
    label: str,
) -> str:
    text = require_string(
        value,
        label,
    )

    if text not in allowed:
        raise ContractValidationError(
            "invalid_enum_value",
            f"{label} uses unsupported value {text!r}.",
        )

    return text


def require_exact_keys(
    value: dict[str, Any],
    expected: set[str],
    label: str,
) -> None:
    actual = set(value)

    missing = sorted(expected - actual)
    additional = sorted(actual - expected)

    if missing:
        raise ContractValidationError(
            "missing_required_field",
            f"{label} is missing fields: {missing}",
        )

    if additional:
        raise ContractValidationError(
            "additional_field",
            f"{label} contains additional fields: {additional}",
        )


def reject_empty_strings(
    value: Any,
    path: str = "$",
) -> None:
    if isinstance(value, str):
        if not value.strip():
            raise ContractValidationError(
                "empty_string",
                f"Empty string is not allowed at {path}.",
            )
        return

    if isinstance(value, list):
        for index, item in enumerate(value):
            reject_empty_strings(
                item,
                f"{path}[{index}]",
            )
        return

    if isinstance(value, dict):
        for key, item in value.items():
            reject_empty_strings(
                item,
                f"{path}.{key}",
            )


def require_unique_strings(
    value: Any,
    label: str,
    allow_empty: bool = True,
) -> list[str]:
    items = require_list(
        value,
        label,
    )

    normalized: list[str] = []

    for index, item in enumerate(items):
        normalized.append(
            require_string(
                item,
                f"{label}[{index}]",
            )
        )

    if not allow_empty and not normalized:
        raise ContractValidationError(
            "empty_required_array",
            f"{label} must not be empty.",
        )

    if len(normalized) != len(set(normalized)):
        raise ContractValidationError(
            "duplicate_array_item",
            f"{label} contains duplicate values.",
        )

    return normalized


def ensure_within(
    path: Path,
    root: Path,
) -> Path:
    resolved_path = path.resolve()
    resolved_root = root.resolve()

    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise PipelineError(
            "candidate_loading",
            "path_outside_project",
            f"Path escapes EXP006 root: {path}",
            False,
        ) from exc

    return resolved_path


def parse_front_matter_value(
    text: str,
    key: str,
) -> str:
    match = re.search(
        rf"(?m)^\s*{re.escape(key)}\s*:\s*(\S+)\s*$",
        text,
    )

    if match is None:
        raise PipelineError(
            "configuration",
            "missing_document_version",
            f"Unable to read {key} from rules document.",
            False,
        )

    return match.group(1)


def load_configuration(
    candidate_policy_path: Path,
    family_contract_path: Path,
    family_rules_path: Path,
    family_schema_path: Path,
) -> dict[str, Any]:
    candidate_policy = load_json(
        candidate_policy_path
    )
    family_contract = load_json(
        family_contract_path
    )

    family_rules_text = family_rules_path.read_text(
        encoding="utf-8"
    )
    family_schema_text = family_schema_path.read_text(
        encoding="utf-8"
    )

    contract_version = str(
        family_contract.get(
            "contract_version"
        )
    )
    target_schema_version = str(
        family_contract.get(
            "target_schema_version"
        )
    )
    rules_version = parse_front_matter_value(
        family_rules_text,
        "rules_version",
    )

    if target_schema_version != FAMILY_SCHEMA_VERSION:
        raise PipelineError(
            "configuration",
            "schema_version_mismatch",
            "Family Contract target_schema_version does not match "
            f"the script: {target_schema_version!r} != "
            f"{FAMILY_SCHEMA_VERSION!r}.",
            False,
        )

    return {
        "candidate_policy": candidate_policy,
        "candidate_policy_path": candidate_policy_path,
        "candidate_policy_hash": file_hash(
            candidate_policy_path
        ),
        "family_contract": family_contract,
        "family_contract_path": family_contract_path,
        "family_contract_hash": file_hash(
            family_contract_path
        ),
        "family_contract_version": contract_version,
        "family_rules_text": family_rules_text,
        "family_rules_path": family_rules_path,
        "family_rules_hash": file_hash(
            family_rules_path
        ),
        "family_rules_version": rules_version,
        "family_schema_text": family_schema_text,
        "family_schema_path": family_schema_path,
        "family_schema_hash": file_hash(
            family_schema_path
        ),
    }


def resolve_candidate_run_path(
    framework: str,
    candidate_run: str | None,
) -> Path:
    runs_root = (
        CANDIDATE_ROOT
        / "runs"
        / slugify(framework)
    )

    if candidate_run:
        supplied = Path(
            candidate_run
        ).expanduser()

        if supplied.exists():
            return supplied.resolve()

        candidate_path = (
            runs_root
            / candidate_run
            / "candidate_run_index.json"
        )

        if candidate_path.is_file():
            return candidate_path.resolve()

        raise PipelineError(
            "candidate_loading",
            "candidate_run_not_found",
            f"Candidate Run was not found: {candidate_run}",
            False,
        )

    if not runs_root.is_dir():
        raise PipelineError(
            "candidate_loading",
            "candidate_run_root_not_found",
            f"Candidate Run directory does not exist: {runs_root}",
            False,
        )

    candidates = sorted(
        runs_root.glob(
            "*/candidate_run_index.json"
        )
    )

    if not candidates:
        raise PipelineError(
            "candidate_loading",
            "candidate_run_not_found",
            f"No Candidate Run Index found under {runs_root}.",
            False,
        )

    return candidates[-1].resolve()


def candidate_manifest_path(
    entry: dict[str, Any],
) -> Path:
    relpath = entry.get(
        "candidate_object_relpath"
    )

    if not isinstance(relpath, str):
        raise PipelineError(
            "candidate_loading",
            "missing_candidate_relpath",
            "Candidate Run entry has no candidate_object_relpath.",
            False,
        )

    return ensure_within(
        CANDIDATE_ROOT / relpath,
        CANDIDATE_ROOT,
    )


def build_pattern_projection(
    pattern: dict[str, Any],
    pattern_id: str,
    pattern_hash: str,
    source_report_ids: list[str],
) -> dict[str, Any]:
    metadata = pattern.get(
        "metadata",
        {},
    )
    provenance = pattern.get(
        "provenance",
        {},
    )

    projection: dict[str, Any] = {
        "pattern_id": pattern_id,
        "pattern_hash": pattern_hash,
        "source_report_ids": sorted(
            set(source_report_ids)
        ),
        "metadata": {
            "canonical_name": (
                metadata.get(
                    "canonical_name"
                )
            ),
        },
        "provenance": {
            "supporting_reports": copy.deepcopy(
                provenance.get(
                    "supporting_reports",
                    [],
                )
            ),
            "abstraction_rationale": (
                provenance.get(
                    "abstraction_rationale"
                )
            ),
            "unresolved_information": copy.deepcopy(
                provenance.get(
                    "unresolved_information",
                    [],
                )
            ),
        },
    }

    semantic_fields = [
        "scope",
        "defect_classification",
        "trigger_signature",
        "defect_mechanism",
        "observed_failure",
        "transferability_hypothesis",
        "confidence",
    ]

    for field in semantic_fields:
        if field in pattern:
            projection[field] = copy.deepcopy(
                pattern[field]
            )

    return projection


def validate_pattern_against_member(
    pattern: dict[str, Any],
    member: dict[str, Any],
    framework: str,
) -> dict[str, Any]:
    metadata = pattern.get("metadata")
    derivation = pattern.get(
        "derivation_information"
    )
    scope = pattern.get("scope")

    if not isinstance(metadata, dict):
        raise PipelineError(
            "candidate_loading",
            "invalid_pattern_metadata",
            "Pattern metadata must be an object.",
        )

    if not isinstance(derivation, dict):
        raise PipelineError(
            "candidate_loading",
            "invalid_pattern_derivation",
            "Pattern derivation_information must be an object.",
        )

    if not isinstance(scope, dict):
        raise PipelineError(
            "candidate_loading",
            "invalid_pattern_scope",
            "Pattern scope must be an object.",
        )

    pattern_id = metadata.get("pattern_id")
    expected_pattern_id = member.get(
        "pattern_id"
    )

    if pattern_id != expected_pattern_id:
        raise PipelineError(
            "candidate_loading",
            "pattern_id_mismatch",
            f"Pattern ID mismatch for {expected_pattern_id}.",
        )

    if metadata.get("pattern_level") != "api_specific":
        raise PipelineError(
            "candidate_loading",
            "invalid_pattern_level",
            f"{pattern_id} is not api_specific.",
        )

    if str(
        pattern.get("schema_version")
    ) != "2.0":
        raise PipelineError(
            "candidate_loading",
            "invalid_pattern_schema_version",
            f"{pattern_id} is not Pattern Schema v2.0.",
        )

    validation_status = derivation.get(
        "validation_status"
    )

    if validation_status not in {
        "automatically_validated",
        "human_verified",
    }:
        raise PipelineError(
            "candidate_loading",
            "ineligible_pattern_validation_status",
            f"{pattern_id} has validation_status "
            f"{validation_status!r}.",
        )

    if scope.get("framework") != framework:
        raise PipelineError(
            "candidate_loading",
            "pattern_framework_mismatch",
            f"{pattern_id} framework does not match Candidate Run.",
        )

    if scope.get("primary_api") != member.get(
        "primary_api"
    ):
        raise PipelineError(
            "candidate_loading",
            "primary_api_mismatch",
            f"{pattern_id} primary_api does not match Candidate Manifest.",
        )

    actual_hash = canonical_json_hash(
        pattern
    )

    if actual_hash != member.get(
        "pattern_hash"
    ):
        raise PipelineError(
            "candidate_loading",
            "pattern_hash_mismatch",
            f"{pattern_id} content hash does not match Candidate Manifest.",
        )

    return build_pattern_projection(
        pattern=pattern,
        pattern_id=pattern_id,
        pattern_hash=actual_hash,
        source_report_ids=list(
            member.get(
                "source_report_ids",
                [],
            )
        ),
    )


def load_candidate_bundle(
    entry: dict[str, Any],
    framework: str,
) -> dict[str, Any]:
    manifest_path = candidate_manifest_path(
        entry
    )
    manifest = load_json(
        manifest_path
    )

    metadata = manifest.get("metadata")

    if not isinstance(metadata, dict):
        raise PipelineError(
            "candidate_loading",
            "invalid_candidate_metadata",
            "Candidate Manifest metadata must be an object.",
        )

    candidate_id = metadata.get(
        "candidate_group_id"
    )
    candidate_hash = metadata.get(
        "candidate_group_hash"
    )

    if candidate_id != entry.get(
        "candidate_group_id"
    ):
        raise PipelineError(
            "candidate_loading",
            "candidate_id_mismatch",
            "Candidate Manifest ID does not match Candidate Run entry.",
        )

    if candidate_hash != entry.get(
        "candidate_group_hash"
    ):
        raise PipelineError(
            "candidate_loading",
            "candidate_hash_mismatch",
            f"Candidate hash mismatch for {candidate_id}.",
        )

    recomputed_hash = recompute_candidate_group_hash(
        manifest
    )

    if recomputed_hash != candidate_hash:
        raise PipelineError(
            "candidate_loading",
            "candidate_semantic_hash_mismatch",
            f"Candidate Manifest semantic hash is invalid: {candidate_id}.",
        )

    if metadata.get("framework") != framework:
        raise PipelineError(
            "candidate_loading",
            "candidate_framework_mismatch",
            f"Candidate {candidate_id} has a different framework.",
        )

    members = manifest.get("members")

    if not isinstance(members, list):
        raise PipelineError(
            "candidate_loading",
            "invalid_candidate_members",
            f"Candidate {candidate_id} members must be an array.",
        )

    pattern_projections: list[
        dict[str, Any]
    ] = []
    members_by_id: dict[
        str,
        dict[str, Any]
    ] = {}

    for member in members:
        if not isinstance(member, dict):
            raise PipelineError(
                "candidate_loading",
                "invalid_candidate_member",
                f"Candidate {candidate_id} contains an invalid member.",
            )

        pattern_relpath = member.get(
            "pattern_relpath"
        )

        if not isinstance(
            pattern_relpath,
            str,
        ):
            raise PipelineError(
                "candidate_loading",
                "missing_pattern_relpath",
                f"Candidate member has no pattern_relpath.",
            )

        pattern_path = ensure_within(
            EXP006_DIR / pattern_relpath,
            EXP006_DIR,
        )

        pattern = load_json(
            pattern_path
        )

        projection = validate_pattern_against_member(
            pattern=pattern,
            member=member,
            framework=framework,
        )

        pattern_id = projection[
            "pattern_id"
        ]

        if pattern_id in members_by_id:
            raise PipelineError(
                "candidate_loading",
                "duplicate_candidate_member",
                f"Duplicate Pattern ID in Candidate: {pattern_id}.",
            )

        member_copy = copy.deepcopy(
            member
        )
        member_copy["_pattern_path"] = str(
            pattern_path
        )
        member_copy["_projection"] = projection

        members_by_id[
            pattern_id
        ] = member_copy

        pattern_projections.append(
            projection
        )

    pattern_projections.sort(
        key=lambda item: item[
            "pattern_id"
        ]
    )

    compact_candidate_context = {
        "candidate_group_id": candidate_id,
        "candidate_group_hash": candidate_hash,
        "framework": framework,
        "member_pattern_ids": sorted(
            members_by_id
        ),
        "eligibility_summary": copy.deepcopy(
            manifest.get(
                "eligibility_summary",
                {},
            )
        ),
        "group_consistency": copy.deepcopy(
            manifest.get(
                "group_consistency",
                {},
            )
        ),
        "retrieval_warnings": copy.deepcopy(
            manifest.get(
                "retrieval_warnings",
                [],
            )
        ),
    }

    return {
        "entry": entry,
        "manifest": manifest,
        "manifest_path": manifest_path,
        "candidate_group_id": candidate_id,
        "candidate_group_hash": candidate_hash,
        "members_by_id": members_by_id,
        "pattern_projections": pattern_projections,
        "candidate_context": compact_candidate_context,
    }


def load_family_snapshot(
    framework: str,
) -> dict[str, Any]:
    root = FAMILY_ROOT / slugify(
        framework
    )

    artifacts: list[
        dict[str, Any]
    ] = []

    if root.is_dir():
        for path in sorted(
            root.rglob("*.json")
        ):
            try:
                data = load_json(path)
            except PipelineError as exc:
                raise PipelineError(
                    "context_retrieval",
                    "invalid_existing_family_artifact",
                    "Unable to load existing Family artifact: "
                    f"{path}",
                    False,
                ) from exc

            if data.get(
                "schema_version"
            ) != FAMILY_SCHEMA_VERSION:
                raise PipelineError(
                    "context_retrieval",
                    "existing_family_schema_mismatch",
                    "Existing Family uses an incompatible schema: "
                    f"{path}",
                    False,
                )

            metadata = data.get("metadata")
            revision_info = data.get(
                "revision_information"
            )

            if (
                not isinstance(metadata, dict)
                or not isinstance(
                    revision_info,
                    dict,
                )
            ):
                raise PipelineError(
                    "context_retrieval",
                    "invalid_existing_family_structure",
                    "Existing Family metadata or revision information "
                    f"is invalid: {path}",
                    False,
                )

            if metadata.get(
                "framework"
            ) != framework:
                raise PipelineError(
                    "context_retrieval",
                    "existing_family_framework_mismatch",
                    "Existing Family framework does not match its "
                    f"storage directory: {path}",
                    False,
                )

            family_id = metadata.get(
                "family_id"
            )
            revision = revision_info.get(
                "revision"
            )

            if (
                not isinstance(family_id, str)
                or not family_id.strip()
                or not isinstance(revision, int)
                or revision < 1
            ):
                raise PipelineError(
                    "context_retrieval",
                    "invalid_existing_family_identity",
                    "Existing Family ID or revision is invalid: "
                    f"{path}",
                    False,
                )

            artifacts.append(
                {
                    "family_id": family_id,
                    "revision": revision,
                    "family_hash": file_hash(
                        path
                    ),
                    "path": path,
                    "data": data,
                }
            )

    by_key: dict[
        tuple[str, int],
        dict[str, Any]
    ] = {}
    latest: dict[
        str,
        dict[str, Any]
    ] = {}

    for artifact in artifacts:
        key = (
            artifact["family_id"],
            artifact["revision"],
        )

        if key in by_key:
            raise PipelineError(
                "context_retrieval",
                "duplicate_family_revision",
                f"Duplicate Family revision: {key}",
                False,
            )

        by_key[key] = artifact

        previous = latest.get(
            artifact["family_id"]
        )

        if (
            previous is None
            or artifact["revision"]
            > previous["revision"]
        ):
            latest[
                artifact["family_id"]
            ] = artifact

    return {
        "artifacts": artifacts,
        "by_key": by_key,
        "latest": latest,
    }


def family_projection(
    artifact: dict[str, Any],
    selection_sources: list[str],
) -> dict[str, Any]:
    data = artifact["data"]

    return {
        "family_id": artifact[
            "family_id"
        ],
        "revision": artifact[
            "revision"
        ],
        "family_hash": artifact[
            "family_hash"
        ],
        "selection_sources": sorted(
            set(selection_sources)
        ),
        "canonical_name": data.get(
            "metadata",
            {},
        ).get("canonical_name"),
        "members": copy.deepcopy(
            data.get(
                "members",
                [],
            )
        ),
        "family_core": copy.deepcopy(
            data.get(
                "family_core",
                {},
            )
        ),
        "shared_characteristics": copy.deepcopy(
            data.get(
                "shared_characteristics",
                {},
            )
        ),
        "applicability": copy.deepcopy(
            data.get(
                "applicability",
                {},
            )
        ),
        "heterogeneity": copy.deepcopy(
            data.get(
                "heterogeneity",
                {},
            )
        ),
        "support": copy.deepcopy(
            data.get(
                "support",
                {},
            )
        ),
        "confidence": copy.deepcopy(
            data.get(
                "confidence",
                {},
            )
        ),
    }


def select_existing_family_context(
    bundle: dict[str, Any],
    family_snapshot: dict[str, Any],
    max_families: int,
) -> dict[str, Any]:
    candidate_pattern_ids = set(
        bundle["members_by_id"]
    )

    candidate_report_ids: set[str] = set()

    for member in bundle[
        "members_by_id"
    ].values():
        candidate_report_ids.update(
            member.get(
                "source_report_ids",
                [],
            )
        )

    related_candidate_ids = set(
        bundle["entry"].get(
            "related_previous_candidate_ids",
            [],
        )
    )
    related_candidate_ids.add(
        bundle["candidate_group_id"]
    )

    scored: list[
        tuple[
            int,
            str,
            int,
            dict[str, Any],
            list[str],
        ]
    ] = []

    for artifact in family_snapshot[
        "latest"
    ].values():
        data = artifact["data"]
        sources: list[str] = []
        score = 0

        family_pattern_ids = {
            member.get("pattern_id")
            for member in data.get(
                "members",
                [],
            )
            if isinstance(member, dict)
        }

        overlap = candidate_pattern_ids & family_pattern_ids

        if overlap:
            score += 20 * len(overlap)
            sources.append(
                "member_pattern_overlap"
            )

        family_report_ids: set[str] = set()

        for member in data.get(
            "members",
            [],
        ):
            if isinstance(member, dict):
                family_report_ids.update(
                    member.get(
                        "source_report_ids",
                        [],
                    )
                )

        report_overlap = (
            candidate_report_ids
            & family_report_ids
        )

        if report_overlap:
            score += 10 * len(
                report_overlap
            )
            sources.append(
                "source_report_overlap"
            )

        provenance = data.get(
            "provenance",
            {},
        )

        family_candidate_ids = {
            item.get(
                "candidate_group_id"
            )
            for item in provenance.get(
                "input_candidate_manifests",
                [],
            )
            if isinstance(item, dict)
        }

        if (
            related_candidate_ids
            & family_candidate_ids
        ):
            score += 100
            sources.append(
                "related_previous_decision"
            )

        if score > 0:
            scored.append(
                (
                    score,
                    artifact["family_id"],
                    artifact["revision"],
                    artifact,
                    sources,
                )
            )

    scored.sort(
        key=lambda item: (
            -item[0],
            item[1],
            -item[2],
        )
    )

    selected = scored[
        :max_families
    ]

    projections = [
        family_projection(
            artifact=item[3],
            selection_sources=item[4],
        )
        for item in selected
    ]

    references = [
        {
            "family_id": item[
                "family_id"
            ],
            "revision": item[
                "revision"
            ],
            "family_hash": item[
                "family_hash"
            ],
            "selection_sources": item[
                "selection_sources"
            ],
        }
        for item in projections
    ]

    retrieval_configuration = {
        "mode": "related_candidate_history",
        "maximum_family_count": max_families,
        "candidate_id_match_weight": 100,
        "member_pattern_overlap_weight": 20,
        "source_report_overlap_weight": 10,
        "tie_breaking": [
            "score_descending",
            "family_id_ascending",
            "revision_descending",
        ],
    }

    if references:
        all_selection_sources = {
            source
            for item in references
            for source in item[
                "selection_sources"
            ]
        }

        if all_selection_sources == {
            "related_previous_decision"
        }:
            selection_scope = (
                "related_previous_decisions_only"
            )
        elif (
            "related_previous_decision"
            in all_selection_sources
        ):
            selection_scope = "combined"
        else:
            selection_scope = (
                "structured_retrieval"
            )

        policy_version: str | None = (
            EXISTING_FAMILY_RETRIEVAL_VERSION
        )
        policy_hash: str | None = (
            canonical_hash(
                retrieval_configuration
            )
        )
    else:
        selection_scope = (
            "none_available"
        )
        policy_version = None
        policy_hash = None

    context_hash_payload = [
        {
            "family_id": item[
                "family_id"
            ],
            "revision": item[
                "revision"
            ],
            "family_hash": item[
                "family_hash"
            ],
        }
        for item in references
    ]

    prompt_context = [
        {
            key: copy.deepcopy(value)
            for key, value in item.items()
            if key != "selection_sources"
        }
        for item in projections
    ]

    return {
        "record_context": {
            "selection_scope": selection_scope,
            "selection_policy_version": (
                policy_version
            ),
            "selection_policy_hash": (
                policy_hash
            ),
            "context_hash": canonical_hash(
                context_hash_payload
            ),
            "family_revisions": references,
        },
        "prompt_context": prompt_context,
        "retrieval_configuration": (
            retrieval_configuration
        ),
    }


def render_prompt(
    bundle: dict[str, Any],
    existing_context: dict[str, Any],
    configuration: dict[str, Any],
) -> str:
    return PROMPT_TEMPLATE.format(
        candidate_context=json.dumps(
            bundle[
                "candidate_context"
            ],
            ensure_ascii=False,
            indent=2,
        ),
        pattern_projections=json.dumps(
            bundle[
                "pattern_projections"
            ],
            ensure_ascii=False,
            indent=2,
        ),
        existing_family_context=json.dumps(
            existing_context[
                "prompt_context"
            ],
            ensure_ascii=False,
            indent=2,
        ),
        family_contract=json.dumps(
            configuration[
                "family_contract"
            ],
            ensure_ascii=False,
            indent=2,
        ),
        family_rules=configuration[
            "family_rules_text"
        ],
    )


def build_analysis_descriptor(
    bundle: dict[str, Any],
    existing_context: dict[str, Any],
    configuration: dict[str, Any],
    provider: str,
    model: str,
    max_output_tokens: int,
) -> dict[str, Any]:
    prompt = render_prompt(
        bundle=bundle,
        existing_context=existing_context,
        configuration=configuration,
    )

    model_configuration = {
        "temperature": 0,
        "top_p": 1,
        "max_output_tokens": (
            max_output_tokens
        ),
        "response_format": {
            "type": "json_object"
        },
    }

    model_descriptor = {
        "provider": provider,
        "model": model,
        "configuration": (
            model_configuration
        ),
        "configuration_hash": (
            canonical_hash(
                model_configuration
            )
        ),
    }

    analysis_payload = {
        "candidate_group_hash": bundle[
            "candidate_group_hash"
        ],
        "existing_family_context_hash": (
            existing_context[
                "record_context"
            ]["context_hash"]
        ),
        "family_contract_hash": (
            configuration[
                "family_contract_hash"
            ]
        ),
        "family_rules_hash": (
            configuration[
                "family_rules_hash"
            ]
        ),
        "prompt_version": (
            PROMPT_VERSION
        ),
        "prompt_template_hash": (
            text_hash(
                PROMPT_TEMPLATE
            )
        ),
        "rendered_prompt_hash": (
            text_hash(prompt)
        ),
        "model_configuration_hash": (
            model_descriptor[
                "configuration_hash"
            ]
        ),
    }

    return {
        "prompt": prompt,
        "prompt_template_hash": (
            analysis_payload[
                "prompt_template_hash"
            ]
        ),
        "rendered_prompt_hash": (
            analysis_payload[
                "rendered_prompt_hash"
            ]
        ),
        "model": model_descriptor,
        "analysis_input_hash": (
            canonical_hash(
                analysis_payload
            )
        ),
    }


def evidence_ref_resolves(
    evidence_ref: str,
    pattern_projections: dict[
        str,
        dict[str, Any]
    ],
) -> bool:
    match = re.fullmatch(
        r"pattern:([^:]+):(.+)",
        evidence_ref,
    )

    if match is None:
        return False

    pattern_id = match.group(1)
    field_path = match.group(2)

    projection = pattern_projections.get(
        pattern_id
    )

    if projection is None:
        return False

    current: Any = projection

    for segment in field_path.split("."):
        if isinstance(current, dict):
            if segment not in current:
                return False

            current = current[segment]
            continue

        if isinstance(current, list):
            if not segment.isdigit():
                return False

            index = int(segment)

            if (
                index < 0
                or index >= len(current)
            ):
                return False

            current = current[index]
            continue

        return False

    return True


def validate_evidence_refs(
    value: Any,
    label: str,
    pattern_projections: dict[
        str,
        dict[str, Any]
    ],
    allow_empty: bool,
) -> list[str]:
    refs = require_unique_strings(
        value,
        label,
        allow_empty=allow_empty,
    )

    for ref in refs:
        if not evidence_ref_resolves(
            ref,
            pattern_projections,
        ):
            raise ContractValidationError(
                "unresolved_evidence_reference",
                f"{label} contains unresolved reference: {ref}",
            )

    return refs


def validate_supporting_ids(
    value: Any,
    members: set[str],
    label: str,
    allow_empty: bool = False,
) -> list[str]:
    ids = require_unique_strings(
        value,
        label,
        allow_empty=allow_empty,
    )

    unknown = sorted(
        set(ids) - members
    )

    if unknown:
        raise ContractValidationError(
            "unknown_family_member_reference",
            f"{label} references non-members: {unknown}",
        )

    return ids


def validate_claim_item(
    item: Any,
    template: dict[str, Any],
    label: str,
    members: set[str],
    pattern_projections: dict[
        str,
        dict[str, Any]
    ],
    allowed_values: dict[str, Any],
    id_field: str,
    id_allowed_empty: bool = False,
) -> None:
    item = require_dict(
        item,
        label,
    )

    require_exact_keys(
        item,
        set(template),
        label,
    )

    require_string(
        item.get("statement"),
        f"{label}.statement",
    )

    validate_supporting_ids(
        item.get(id_field),
        members,
        f"{label}.{id_field}",
        allow_empty=id_allowed_empty,
    )

    require_enum(
        item.get("evidence_status"),
        set(
            allowed_values[
                "evidence_status"
            ]
        ),
        f"{label}.evidence_status",
    )

    validate_evidence_refs(
        item.get("evidence_refs"),
        f"{label}.evidence_refs",
        pattern_projections,
        allow_empty=False,
    )

    require_enum(
        item.get("confidence"),
        set(
            allowed_values[
                "confidence"
            ]
        ),
        f"{label}.confidence",
    )


def validate_proposed_family(
    proposal: Any,
    proposal_index: int,
    contract: dict[str, Any],
    input_pattern_ids: set[str],
    members_by_id: dict[
        str,
        dict[str, Any]
    ],
    pattern_projections: dict[
        str,
        dict[str, Any]
    ],
    existing_family_ids: set[str],
    decision: str,
) -> None:
    templates = contract[
        "item_templates"
    ]
    allowed = contract[
        "allowed_values"
    ]

    label = (
        f"proposed_families"
        f"[{proposal_index}]"
    )

    proposal = require_dict(
        proposal,
        label,
    )

    require_exact_keys(
        proposal,
        set(
            templates[
                "proposed_family"
            ]
        ),
        label,
    )

    canonical_name = require_string(
        proposal.get(
            "canonical_name"
        ),
        f"{label}.canonical_name",
    )

    if re.fullmatch(
        r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*",
        canonical_name,
    ) is None:
        raise ContractValidationError(
            "invalid_canonical_name",
            f"{label}.canonical_name must use lowercase snake_case.",
        )

    member_items = require_list(
        proposal.get("members"),
        f"{label}.members",
    )

    if len(member_items) < 2:
        raise ContractValidationError(
            "insufficient_family_members",
            f"{label} must contain at least two Patterns.",
        )

    member_ids: list[str] = []

    for member_index, member in enumerate(
        member_items
    ):
        member_label = (
            f"{label}.members"
            f"[{member_index}]"
        )

        member = require_dict(
            member,
            member_label,
        )

        require_exact_keys(
            member,
            set(
                templates[
                    "family_member"
                ]
            ),
            member_label,
        )

        pattern_id = require_string(
            member.get("pattern_id"),
            f"{member_label}.pattern_id",
        )

        if pattern_id not in input_pattern_ids:
            raise ContractValidationError(
                "unknown_pattern_id",
                f"{member_label} references unknown Pattern {pattern_id}.",
            )

        member_ids.append(
            pattern_id
        )

        require_string(
            member.get(
                "membership_rationale"
            ),
            (
                f"{member_label}."
                "membership_rationale"
            ),
        )

        require_enum(
            member.get(
                "evidence_status"
            ),
            set(
                allowed[
                    "evidence_status"
                ]
            ),
            (
                f"{member_label}."
                "evidence_status"
            ),
        )

        validate_evidence_refs(
            member.get(
                "evidence_refs"
            ),
            (
                f"{member_label}."
                "evidence_refs"
            ),
            pattern_projections,
            allow_empty=False,
        )

        require_enum(
            member.get("confidence"),
            set(
                allowed["confidence"]
            ),
            f"{member_label}.confidence",
        )

    if len(member_ids) != len(
        set(member_ids)
    ):
        raise ContractValidationError(
            "duplicate_family_member",
            f"{label} contains a duplicate Pattern member.",
        )

    member_set = set(member_ids)

    primary_apis = {
        members_by_id[
            pattern_id
        ].get("primary_api")
        for pattern_id in member_set
    }

    report_ids: set[str] = set()

    for pattern_id in member_set:
        report_ids.update(
            members_by_id[
                pattern_id
            ].get(
                "source_report_ids",
                [],
            )
        )

    if len(primary_apis) < 2:
        raise ContractValidationError(
            "insufficient_api_support",
            f"{label} requires at least two distinct primary APIs.",
        )

    if len(report_ids) < 2:
        raise ContractValidationError(
            "insufficient_source_support",
            f"{label} requires at least two independent Reports or Issues.",
        )

    family_core = require_dict(
        proposal.get("family_core"),
        f"{label}.family_core",
    )

    require_exact_keys(
        family_core,
        set(
            templates[
                "proposed_family"
            ]["family_core"]
        ),
        f"{label}.family_core",
    )

    require_string(
        family_core.get("statement"),
        f"{label}.family_core.statement",
    )

    basis_types = require_unique_strings(
        family_core.get(
            "basis_types"
        ),
        f"{label}.family_core.basis_types",
        allow_empty=False,
    )

    invalid_basis_types = (
        set(basis_types)
        - set(
            allowed[
                "basis_type"
            ]
        )
    )

    if invalid_basis_types:
        raise ContractValidationError(
            "invalid_basis_type",
            f"{label}.family_core contains unsupported basis types.",
        )

    require_unique_strings(
        family_core.get(
            "shared_defect_classes"
        ),
        (
            f"{label}.family_core."
            "shared_defect_classes"
        ),
    )

    require_unique_strings(
        family_core.get(
            "shared_risk_dimensions"
        ),
        (
            f"{label}.family_core."
            "shared_risk_dimensions"
        ),
    )

    require_enum(
        family_core.get(
            "evidence_status"
        ),
        set(
            allowed[
                "evidence_status"
            ]
        ),
        (
            f"{label}.family_core."
            "evidence_status"
        ),
    )

    validate_evidence_refs(
        family_core.get(
            "evidence_refs"
        ),
        (
            f"{label}.family_core."
            "evidence_refs"
        ),
        pattern_projections,
        allow_empty=False,
    )

    require_enum(
        family_core.get("confidence"),
        set(
            allowed["confidence"]
        ),
        f"{label}.family_core.confidence",
    )

    shared = require_dict(
        proposal.get(
            "shared_characteristics"
        ),
        f"{label}.shared_characteristics",
    )

    require_exact_keys(
        shared,
        set(
            templates[
                "proposed_family"
            ]["shared_characteristics"]
        ),
        f"{label}.shared_characteristics",
    )

    for field in [
        "trigger_semantics",
        "mechanism_semantics",
        "execution_semantics",
        "failure_observables",
    ]:
        items = require_list(
            shared.get(field),
            (
                f"{label}."
                "shared_characteristics."
                f"{field}"
            ),
        )

        for index, item in enumerate(
            items
        ):
            validate_claim_item(
                item=item,
                template=templates[
                    "shared_characteristic"
                ],
                label=(
                    f"{label}."
                    "shared_characteristics."
                    f"{field}[{index}]"
                ),
                members=member_set,
                pattern_projections=(
                    pattern_projections
                ),
                allowed_values=allowed,
                id_field=(
                    "supporting_pattern_ids"
                ),
            )

    applicability = require_dict(
        proposal.get("applicability"),
        f"{label}.applicability",
    )

    require_exact_keys(
        applicability,
        set(
            templates[
                "proposed_family"
            ]["applicability"]
        ),
        f"{label}.applicability",
    )

    for field in [
        "required_capabilities",
        "exclusion_conditions",
    ]:
        items = require_list(
            applicability.get(field),
            (
                f"{label}."
                f"applicability.{field}"
            ),
        )

        for index, item in enumerate(
            items
        ):
            validate_claim_item(
                item=item,
                template=templates[
                    "applicability_condition"
                ],
                label=(
                    f"{label}."
                    f"applicability.{field}"
                    f"[{index}]"
                ),
                members=member_set,
                pattern_projections=(
                    pattern_projections
                ),
                allowed_values=allowed,
                id_field=(
                    "supporting_pattern_ids"
                ),
            )

            require_enum(
                item.get("kind"),
                set(
                    allowed[
                        "applicability_kind"
                    ]
                ),
                (
                    f"{label}."
                    f"applicability.{field}"
                    f"[{index}].kind"
                ),
            )

    heterogeneity = require_dict(
        proposal.get("heterogeneity"),
        f"{label}.heterogeneity",
    )

    require_exact_keys(
        heterogeneity,
        set(
            templates[
                "proposed_family"
            ]["heterogeneity"]
        ),
        f"{label}.heterogeneity",
    )

    differences = require_list(
        heterogeneity.get(
            "member_differences"
        ),
        (
            f"{label}.heterogeneity."
            "member_differences"
        ),
    )

    for index, item in enumerate(
        differences
    ):
        item_label = (
            f"{label}.heterogeneity."
            f"member_differences[{index}]"
        )

        validate_claim_item(
            item=item,
            template=templates[
                "member_difference"
            ],
            label=item_label,
            members=member_set,
            pattern_projections=(
                pattern_projections
            ),
            allowed_values=allowed,
            id_field=(
                "affected_pattern_ids"
            ),
        )

        require_enum(
            item.get("dimension"),
            set(
                allowed[
                    "difference_dimension"
                ]
            ),
            f"{item_label}.dimension",
        )

        require_enum(
            item.get("significance"),
            set(
                allowed[
                    "difference_significance"
                ]
            ),
            f"{item_label}.significance",
        )

    conflicts = require_list(
        heterogeneity.get(
            "unresolved_conflicts"
        ),
        (
            f"{label}.heterogeneity."
            "unresolved_conflicts"
        ),
    )

    for index, item in enumerate(
        conflicts
    ):
        item_label = (
            f"{label}.heterogeneity."
            f"unresolved_conflicts[{index}]"
        )

        validate_claim_item(
            item=item,
            template=templates[
                "unresolved_conflict"
            ],
            label=item_label,
            members=member_set,
            pattern_projections=(
                pattern_projections
            ),
            allowed_values=allowed,
            id_field=(
                "affected_pattern_ids"
            ),
        )

        require_enum(
            item.get("impact"),
            set(
                allowed[
                    "conflict_impact"
                ]
            ),
            f"{item_label}.impact",
        )

        require_enum(
            item.get(
                "resolution_status"
            ),
            set(
                allowed[
                    "conflict_resolution_status"
                ]
            ),
            (
                f"{item_label}."
                "resolution_status"
            ),
        )

    lineage = require_dict(
        proposal.get("lineage"),
        f"{label}.lineage",
    )

    require_exact_keys(
        lineage,
        set(
            templates[
                "proposed_family"
            ]["lineage"]
        ),
        f"{label}.lineage",
    )

    action = require_enum(
        lineage.get("action"),
        set(
            allowed[
                "lineage_action"
            ]
        ),
        f"{label}.lineage.action",
    )

    target_family_id = lineage.get(
        "target_family_id"
    )
    parent_family_ids = (
        require_unique_strings(
            lineage.get(
                "parent_family_ids"
            ),
            (
                f"{label}.lineage."
                "parent_family_ids"
            ),
        )
    )

    require_string(
        lineage.get("rationale"),
        f"{label}.lineage.rationale",
    )

    if action == "create_new":
        if (
            target_family_id is not None
            or parent_family_ids
        ):
            raise ContractValidationError(
                "invalid_create_new_lineage",
                f"{label} create_new must not reference existing Families.",
            )

    elif action in {
        "reuse_existing",
        "update_existing",
    }:
        if (
            not isinstance(
                target_family_id,
                str,
            )
            or target_family_id
            not in existing_family_ids
            or parent_family_ids
        ):
            raise ContractValidationError(
                "invalid_target_family",
                f"{label} {action} must reference exactly one supplied target Family.",
            )

    elif action == "derive_new":
        if (
            target_family_id is not None
            or not parent_family_ids
        ):
            raise ContractValidationError(
                "invalid_derive_lineage",
                f"{label} derive_new requires one or more parent Families.",
            )

    elif action == "merge_existing":
        if (
            target_family_id is not None
            or len(parent_family_ids) < 2
        ):
            raise ContractValidationError(
                "invalid_merge_lineage",
                f"{label} merge_existing requires at least two parent Families.",
            )

    elif action == "split_existing":
        if (
            decision != "split"
            or target_family_id
            is not None
            or len(
                parent_family_ids
            ) != 1
        ):
            raise ContractValidationError(
                "invalid_split_lineage",
                f"{label} split_existing requires a split decision and one parent Family.",
            )

    for family_id in parent_family_ids:
        if family_id not in existing_family_ids:
            raise ContractValidationError(
                "unknown_parent_family",
                f"{label} references an unsupplied Family: {family_id}",
            )

    confidence = require_dict(
        proposal.get("confidence"),
        f"{label}.confidence",
    )

    require_exact_keys(
        confidence,
        set(
            templates[
                "proposed_family"
            ]["confidence"]
        ),
        f"{label}.confidence",
    )

    for field in [
        "membership",
        "commonality",
        "applicability",
        "generalization",
    ]:
        require_enum(
            confidence.get(field),
            set(
                allowed["confidence"]
            ),
            f"{label}.confidence.{field}",
        )


def validate_decision_payload(
    payload: Any,
    contract: dict[str, Any],
    bundle: dict[str, Any],
    existing_context: dict[str, Any],
) -> dict[str, Any]:
    payload = require_dict(
        payload,
        "$",
    )

    require_exact_keys(
        payload,
        set(
            contract[
                "response_template"
            ]
        ),
        "$",
    )

    reject_empty_strings(
        payload
    )

    allowed = contract[
        "allowed_values"
    ]
    templates = contract[
        "item_templates"
    ]

    decision = require_enum(
        payload.get("decision"),
        set(
            allowed["decision"]
        ),
        "decision",
    )

    require_string(
        payload.get(
            "decision_rationale"
        ),
        "decision_rationale",
    )

    pattern_projection_map = {
        item["pattern_id"]: item
        for item in bundle[
            "pattern_projections"
        ]
    }

    decision_refs = (
        validate_evidence_refs(
            payload.get(
                "decision_evidence_refs"
            ),
            "decision_evidence_refs",
            pattern_projection_map,
            allow_empty=(
                decision
                == "needs_revision"
            ),
        )
    )

    if (
        decision in {
            "accept",
            "split",
            "reject",
        }
        and not decision_refs
    ):
        raise ContractValidationError(
            "missing_decision_evidence",
            "decision_evidence_refs must not be empty.",
        )

    proposed = require_list(
        payload.get(
            "proposed_families"
        ),
        "proposed_families",
    )
    excluded = require_list(
        payload.get(
            "excluded_patterns"
        ),
        "excluded_patterns",
    )
    unresolved = require_list(
        payload.get(
            "unresolved_issues"
        ),
        "unresolved_issues",
    )

    cardinality = contract[
        "decision_cardinality"
    ][decision]

    minimum = cardinality.get(
        "minimum_proposed_family_count",
        0,
    )
    maximum = cardinality.get(
        "maximum_proposed_family_count"
    )

    if len(proposed) < minimum:
        raise ContractValidationError(
            "too_few_proposed_families",
            f"{decision} requires at least {minimum} proposed Families.",
        )

    if (
        maximum is not None
        and len(proposed) > maximum
    ):
        raise ContractValidationError(
            "too_many_proposed_families",
            f"{decision} allows at most {maximum} proposed Families.",
        )

    minimum_unresolved = cardinality.get(
        "minimum_unresolved_issue_count",
        0,
    )
    maximum_unresolved = cardinality.get(
        "maximum_unresolved_issue_count"
    )

    if len(unresolved) < minimum_unresolved:
        raise ContractValidationError(
            "too_few_unresolved_issues",
            f"{decision} requires unresolved issues.",
        )

    if (
        maximum_unresolved is not None
        and len(unresolved)
        > maximum_unresolved
    ):
        raise ContractValidationError(
            "too_many_unresolved_issues",
            f"{decision} does not allow unresolved issues.",
        )

    input_pattern_ids = set(
        bundle["members_by_id"]
    )
    existing_family_ids = {
        item["family_id"]
        for item in existing_context[
            "record_context"
        ]["family_revisions"]
    }

    proposed_memberships: list[
        set[str]
    ] = []

    for index, proposal in enumerate(
        proposed
    ):
        validate_proposed_family(
            proposal=proposal,
            proposal_index=index,
            contract=contract,
            input_pattern_ids=(
                input_pattern_ids
            ),
            members_by_id=bundle[
                "members_by_id"
            ],
            pattern_projections=(
                pattern_projection_map
            ),
            existing_family_ids=(
                existing_family_ids
            ),
            decision=decision,
        )

        proposed_memberships.append(
            {
                item["pattern_id"]
                for item in proposal[
                    "members"
                ]
            }
        )

    excluded_ids: list[str] = []

    for index, item in enumerate(
        excluded
    ):
        label = (
            f"excluded_patterns"
            f"[{index}]"
        )

        item = require_dict(
            item,
            label,
        )

        require_exact_keys(
            item,
            set(
                templates[
                    "excluded_pattern"
                ]
            ),
            label,
        )

        pattern_id = require_string(
            item.get("pattern_id"),
            f"{label}.pattern_id",
        )

        if pattern_id not in input_pattern_ids:
            raise ContractValidationError(
                "unknown_excluded_pattern",
                f"{label} references unknown Pattern {pattern_id}.",
            )

        excluded_ids.append(
            pattern_id
        )

        require_string(
            item.get("reason"),
            f"{label}.reason",
        )

        validate_evidence_refs(
            item.get("evidence_refs"),
            f"{label}.evidence_refs",
            pattern_projection_map,
            allow_empty=False,
        )

    if len(excluded_ids) != len(
        set(excluded_ids)
    ):
        raise ContractValidationError(
            "duplicate_excluded_pattern",
            "excluded_patterns contains duplicates.",
        )

    assigned_ids: set[str] = set()

    for member_set in proposed_memberships:
        assigned_ids.update(
            member_set
        )

    overlap_with_excluded = (
        assigned_ids
        & set(excluded_ids)
    )

    if overlap_with_excluded:
        raise ContractValidationError(
            "assigned_and_excluded_pattern",
            "Patterns cannot be both assigned and excluded: "
            f"{sorted(overlap_with_excluded)}",
        )

    if decision in {
        "accept",
        "split",
    }:
        covered = (
            assigned_ids
            | set(excluded_ids)
        )

        if covered != input_pattern_ids:
            raise ContractValidationError(
                "incomplete_pattern_coverage",
                "Every input Pattern must be assigned or excluded.",
            )

    if (
        decision == "reject"
        and set(excluded_ids)
        != input_pattern_ids
    ):
        raise ContractValidationError(
            "incomplete_rejection",
            "reject must exclude every input Pattern.",
        )

    for index, item in enumerate(
        unresolved
    ):
        label = (
            f"unresolved_issues"
            f"[{index}]"
        )

        item = require_dict(
            item,
            label,
        )

        require_exact_keys(
            item,
            set(
                templates[
                    "unresolved_issue"
                ]
            ),
            label,
        )

        require_string(
            item.get("issue"),
            f"{label}.issue",
        )

        validate_supporting_ids(
            item.get(
                "affected_pattern_ids"
            ),
            input_pattern_ids,
            (
                f"{label}."
                "affected_pattern_ids"
            ),
            allow_empty=True,
        )

        validate_evidence_refs(
            item.get("evidence_refs"),
            f"{label}.evidence_refs",
            pattern_projection_map,
            allow_empty=True,
        )

        require_string(
            item.get(
                "required_action"
            ),
            f"{label}.required_action",
        )

    if decision == "split":
        split_parent_counts: dict[
            str,
            int
        ] = {}

        for proposal in proposed:
            lineage = proposal["lineage"]

            if (
                lineage["action"]
                == "split_existing"
            ):
                parent_id = (
                    lineage[
                        "parent_family_ids"
                    ][0]
                )
                split_parent_counts[
                    parent_id
                ] = (
                    split_parent_counts.get(
                        parent_id,
                        0,
                    )
                    + 1
                )

        for parent_id, count in (
            split_parent_counts.items()
        ):
            if count < 2:
                raise ContractValidationError(
                    "incomplete_existing_family_split",
                    "split_existing requires at least two children "
                    f"for parent {parent_id}.",
                )

    return payload


def normalize_usage(
    usage: Any,
) -> dict[str, int]:
    if not isinstance(usage, dict):
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }

    input_tokens = usage.get(
        "prompt_tokens",
        usage.get(
            "input_tokens",
            0,
        ),
    )
    output_tokens = usage.get(
        "completion_tokens",
        usage.get(
            "output_tokens",
            0,
        ),
    )
    total_tokens = usage.get(
        "total_tokens",
        0,
    )

    values = [
        input_tokens,
        output_tokens,
        total_tokens,
    ]

    normalized = [
        item
        if isinstance(item, int)
        and item >= 0
        else 0
        for item in values
    ]

    if normalized[2] == 0:
        normalized[2] = (
            normalized[0]
            + normalized[1]
        )

    return {
        "input_tokens": normalized[0],
        "output_tokens": normalized[1],
        "total_tokens": normalized[2],
    }


def add_usage(
    destination: dict[str, int],
    source: dict[str, int],
) -> None:
    for field in [
        "input_tokens",
        "output_tokens",
        "total_tokens",
    ]:
        destination[field] += source[field]


def call_llm(
    api_url: str,
    api_key: str,
    model: str,
    prompt: str,
    max_output_tokens: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    started = time.monotonic()

    response = requests.post(
        api_url,
        headers={
            "Authorization": (
                f"Bearer {api_key}"
            ),
            "Content-Type": (
                "application/json"
            ),
        },
        json={
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "temperature": 0,
            "top_p": 1,
            "max_tokens": (
                max_output_tokens
            ),
            "response_format": {
                "type": "json_object"
            },
        },
        timeout=timeout_seconds,
    )

    duration_ms = int(
        (
            time.monotonic()
            - started
        )
        * 1000
    )

    response.raise_for_status()

    body = response.json()

    choices = body.get("choices")

    if (
        not isinstance(choices, list)
        or not choices
        or not isinstance(
            choices[0],
            dict,
        )
    ):
        raise ValueError(
            "Provider response contains no choices."
        )

    message = choices[0].get(
        "message"
    )

    if not isinstance(message, dict):
        raise ValueError(
            "Provider response contains no message."
        )

    content = message.get(
        "content"
    )

    if not isinstance(content, str):
        raise ValueError(
            "Provider response content is not text."
        )

    return {
        "content": content,
        "provider_response_id": (
            body.get("id")
        ),
        "token_usage": normalize_usage(
            body.get("usage")
        ),
        "duration_ms": duration_ms,
    }


def decision_record_path(
    framework: str,
    analysis_input_hash: str,
) -> Path:
    digest = analysis_input_hash.removeprefix(
        "sha256:"
    )

    decision_record_id = (
        f"pfd_{framework_prefix(framework)}_"
        f"{digest[:12]}"
    )

    return (
        DECISION_ROOT
        / slugify(framework)
        / f"{decision_record_id}.json"
    )


def validate_cached_decision_record(
    record: dict[str, Any],
    expected_analysis_hash: str,
    expected_framework: str,
) -> None:
    if record.get(
        "record_version"
    ) != DECISION_RECORD_VERSION:
        raise PipelineError(
            "decision_lookup",
            "decision_record_version_mismatch",
            "Cached Decision Record has an incompatible version.",
            False,
        )

    metadata = record.get("metadata")

    if not isinstance(metadata, dict):
        raise PipelineError(
            "decision_lookup",
            "invalid_cached_decision_record",
            "Cached Decision Record metadata is invalid.",
            False,
        )

    if metadata.get(
        "analysis_input_hash"
    ) != expected_analysis_hash:
        raise PipelineError(
            "decision_lookup",
            "decision_cache_hash_mismatch",
            "Cached Decision Record analysis_input_hash does not match.",
            False,
        )

    if metadata.get(
        "framework"
    ) != expected_framework:
        raise PipelineError(
            "decision_lookup",
            "decision_cache_framework_mismatch",
            "Cached Decision Record framework does not match.",
            False,
        )

    validation = record.get("validation")

    if (
        not isinstance(validation, dict)
        or validation.get("status")
        != "passed"
    ):
        raise PipelineError(
            "decision_lookup",
            "cached_decision_not_validated",
            "Cached Decision Record is not validated.",
            False,
        )


def build_decision_record(
    framework: str,
    bundle: dict[str, Any],
    existing_context: dict[str, Any],
    configuration: dict[str, Any],
    analysis: dict[str, Any],
    decision_payload: dict[str, Any],
    successful_call: dict[str, Any],
    script_hash: str,
) -> dict[str, Any]:
    analysis_input_hash = analysis[
        "analysis_input_hash"
    ]
    digest = analysis_input_hash.removeprefix(
        "sha256:"
    )
    decision_record_id = (
        f"pfd_{framework_prefix(framework)}_"
        f"{digest[:12]}"
    )

    generated_at = utc_timestamp()

    return {
        "record_version": (
            DECISION_RECORD_VERSION
        ),
        "metadata": {
            "decision_record_id": (
                decision_record_id
            ),
            "framework": framework,
            "analysis_input_hash": (
                analysis_input_hash
            ),
        },
        "analysis_input": {
            "candidate": {
                "candidate_group_id": (
                    bundle[
                        "candidate_group_id"
                    ]
                ),
                "candidate_group_hash": (
                    bundle[
                        "candidate_group_hash"
                    ]
                ),
            },
            "existing_family_context": (
                copy.deepcopy(
                    existing_context[
                        "record_context"
                    ]
                )
            ),
            "family_contract": {
                "contract_version": (
                    configuration[
                        "family_contract_version"
                    ]
                ),
                "contract_hash": (
                    configuration[
                        "family_contract_hash"
                    ]
                ),
            },
            "family_rules": {
                "rules_version": (
                    configuration[
                        "family_rules_version"
                    ]
                ),
                "rules_hash": (
                    configuration[
                        "family_rules_hash"
                    ]
                ),
            },
            "prompt": {
                "prompt_version": (
                    PROMPT_VERSION
                ),
                "prompt_template_hash": (
                    analysis[
                        "prompt_template_hash"
                    ]
                ),
                "rendered_prompt_hash": (
                    analysis[
                        "rendered_prompt_hash"
                    ]
                ),
            },
            "model": copy.deepcopy(
                analysis["model"]
            ),
        },
        "generation_information": {
            "method": "llm_assisted",
            "conversion_script_version": (
                SCRIPT_VERSION
            ),
            "conversion_script_hash": (
                script_hash
            ),
            "generated_at": generated_at,
            "provider_response_id": (
                successful_call.get(
                    "provider_response_id"
                )
            ),
            "duration_ms": (
                successful_call[
                    "duration_ms"
                ]
            ),
            "token_usage": copy.deepcopy(
                successful_call[
                    "token_usage"
                ]
            ),
            "decision_payload_hash": (
                canonical_hash(
                    decision_payload
                )
            ),
        },
        "decision_payload": copy.deepcopy(
            decision_payload
        ),
        "validation": {
            "status": "passed",
            "validator_version": (
                DECISION_VALIDATOR_VERSION
            ),
            "validator_hash": (
                script_hash
            ),
            "validated_at": generated_at,
            "warnings": [],
        },
    }


def obtain_decision(
    framework: str,
    bundle: dict[str, Any],
    existing_context: dict[str, Any],
    configuration: dict[str, Any],
    analysis: dict[str, Any],
    script_hash: str,
    api_url: str,
    api_key: str,
    model: str,
    max_output_tokens: int,
    max_attempts: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    path = decision_record_path(
        framework,
        analysis[
            "analysis_input_hash"
        ],
    )

    if path.is_file():
        record = load_json(path)

        validate_cached_decision_record(
            record=record,
            expected_analysis_hash=(
                analysis[
                    "analysis_input_hash"
                ]
            ),
            expected_framework=framework,
        )

        validate_decision_payload(
            payload=record[
                "decision_payload"
            ],
            contract=configuration[
                "family_contract"
            ],
            bundle=bundle,
            existing_context=(
                existing_context
            ),
        )

        return {
            "source": "reused",
            "record": record,
            "record_path": path,
            "record_hash": file_hash(
                path
            ),
            "llm_call_count": 0,
            "failed_attempts": [],
            "token_usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            },
        }

    failed_attempts: list[
        dict[str, Any]
    ] = []
    total_usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }

    successful_call: (
        dict[str, Any]
        | None
    ) = None
    valid_payload: (
        dict[str, Any]
        | None
    ) = None

    for attempt_number in range(
        1,
        max_attempts + 1,
    ):
        call_started = time.monotonic()

        try:
            result = call_llm(
                api_url=api_url,
                api_key=api_key,
                model=model,
                prompt=analysis["prompt"],
                max_output_tokens=(
                    max_output_tokens
                ),
                timeout_seconds=(
                    timeout_seconds
                ),
            )

            add_usage(
                total_usage,
                result["token_usage"],
            )

            try:
                payload = json.loads(
                    result["content"]
                )
            except json.JSONDecodeError:
                failed_attempts.append(
                    {
                        "attempt_number": (
                            attempt_number
                        ),
                        "failure_kind": (
                            "invalid_json"
                        ),
                        "response_hash": (
                            text_hash(
                                result[
                                    "content"
                                ]
                            )
                        ),
                        "error_codes": [
                            "invalid_json"
                        ],
                        "token_usage": (
                            result[
                                "token_usage"
                            ]
                        ),
                        "duration_ms": (
                            result[
                                "duration_ms"
                            ]
                        ),
                    }
                )
                continue

            try:
                valid_payload = (
                    validate_decision_payload(
                        payload=payload,
                        contract=configuration[
                            "family_contract"
                        ],
                        bundle=bundle,
                        existing_context=(
                            existing_context
                        ),
                    )
                )
            except ContractValidationError as exc:
                failed_attempts.append(
                    {
                        "attempt_number": (
                            attempt_number
                        ),
                        "failure_kind": (
                            "contract_validation_failed"
                        ),
                        "response_hash": (
                            text_hash(
                                result[
                                    "content"
                                ]
                            )
                        ),
                        "error_codes": [
                            exc.code
                        ],
                        "token_usage": (
                            result[
                                "token_usage"
                            ]
                        ),
                        "duration_ms": (
                            result[
                                "duration_ms"
                            ]
                        ),
                    }
                )
                continue

            successful_call = result
            break

        except requests.Timeout:
            duration_ms = int(
                (
                    time.monotonic()
                    - call_started
                )
                * 1000
            )
            failed_attempts.append(
                {
                    "attempt_number": (
                        attempt_number
                    ),
                    "failure_kind": (
                        "timeout"
                    ),
                    "response_hash": None,
                    "error_codes": [
                        "provider_timeout"
                    ],
                    "token_usage": {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "total_tokens": 0,
                    },
                    "duration_ms": (
                        duration_ms
                    ),
                }
            )

        except (
            requests.RequestException,
            ValueError,
        ) as exc:
            duration_ms = int(
                (
                    time.monotonic()
                    - call_started
                )
                * 1000
            )
            failed_attempts.append(
                {
                    "attempt_number": (
                        attempt_number
                    ),
                    "failure_kind": (
                        "provider_error"
                    ),
                    "response_hash": None,
                    "error_codes": [
                        type(exc).__name__
                    ],
                    "token_usage": {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "total_tokens": 0,
                    },
                    "duration_ms": (
                        duration_ms
                    ),
                }
            )

    if (
        valid_payload is None
        or successful_call is None
    ):
        raise PipelineError(
            "llm_analysis",
            "no_valid_decision",
            "No valid Pattern Family Decision was obtained after "
            f"{max_attempts} attempts.",
            True,
            failed_attempts=failed_attempts,
            token_usage=total_usage,
            llm_call_count=len(
                failed_attempts
            ),
        )

    record = build_decision_record(
        framework=framework,
        bundle=bundle,
        existing_context=(
            existing_context
        ),
        configuration=configuration,
        analysis=analysis,
        decision_payload=(
            valid_payload
        ),
        successful_call=(
            successful_call
        ),
        script_hash=script_hash,
    )

    record_hash = write_json_exclusive(
        path,
        record,
    )

    return {
        "source": "generated",
        "record": record,
        "record_path": path,
        "record_hash": record_hash,
        "llm_call_count": len(
            failed_attempts
        )
        + 1,
        "failed_attempts": (
            failed_attempts
        ),
        "token_usage": total_usage,
    }


def add_local_ids(
    items: list[dict[str, Any]],
    id_field: str,
    prefix: str,
) -> list[dict[str, Any]]:
    result: list[
        dict[str, Any]
    ] = []

    for index, item in enumerate(
        items,
        start=1,
    ):
        result.append(
            {
                id_field: (
                    f"{prefix}{index:02d}"
                ),
                **copy.deepcopy(item),
            }
        )

    return result


def support_tier(
    proposal: dict[str, Any],
    materialized_members: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:
    supporting_apis = sorted(
        {
            member["primary_api"]
            for member in materialized_members
        }
    )
    reports = sorted(
        {
            report_id
            for member
            in materialized_members
            for report_id
            in member[
                "source_report_ids"
            ]
        }
    )

    pattern_count = len(
        materialized_members
    )
    api_count = len(
        supporting_apis
    )
    report_count = len(
        reports
    )

    if (
        pattern_count < 2
        or api_count < 2
        or report_count < 2
    ):
        raise PipelineError(
            "family_validation",
            "insufficient_family_support",
            "Family does not satisfy the emerging support threshold.",
        )

    ceiling = "emerging"

    if (
        pattern_count >= 3
        and api_count >= 3
        and report_count >= 3
    ):
        ceiling = "corroborated"

    if (
        pattern_count >= 5
        and api_count >= 4
        and report_count >= 5
    ):
        ceiling = (
            "broadly_supported"
        )

    confidence = proposal[
        "confidence"
    ]
    conflicts = proposal[
        "heterogeneity"
    ]["unresolved_conflicts"]

    open_membership_or_core = any(
        item["resolution_status"]
        == "open"
        and item["impact"]
        in {
            "membership",
            "family_core",
        }
        for item in conflicts
    )

    open_material_conflict = any(
        item["resolution_status"]
        == "open"
        for item in conflicts
    )

    corroborated_allowed = (
        confidence["membership"]
        in {"medium", "high"}
        and confidence["commonality"]
        in {"medium", "high"}
        and not open_membership_or_core
    )

    low_member_confidence = any(
        member["confidence"] == "low"
        for member in proposal[
            "members"
        ]
    )

    broadly_allowed = (
        confidence["membership"]
        == "high"
        and confidence["commonality"]
        == "high"
        and confidence[
            "generalization"
        ]
        in {"medium", "high"}
        and not open_material_conflict
        and proposal[
            "family_core"
        ]["evidence_status"]
        != "analyst_inferred"
        and not low_member_confidence
    )

    final_tier = "emerging"
    applied_caps: list[str] = []

    if ceiling in {
        "corroborated",
        "broadly_supported",
    }:
        if corroborated_allowed:
            final_tier = (
                "corroborated"
            )
        else:
            applied_caps.append(
                "corroborated_qualitative_requirements_not_met"
            )

    if ceiling == "broadly_supported":
        if broadly_allowed:
            final_tier = (
                "broadly_supported"
            )
        else:
            applied_caps.append(
                "broadly_supported_qualitative_requirements_not_met"
            )

    cap_text = (
        " No qualitative cap was applied."
        if not applied_caps
        else (
            " Applied caps: "
            + ", ".join(applied_caps)
            + "."
        )
    )

    rationale = (
        f"Counts: {pattern_count} Patterns, "
        f"{api_count} distinct APIs, and "
        f"{report_count} independent Reports; "
        f"count-based ceiling: {ceiling}; "
        f"final tier: {final_tier}."
        f"{cap_text}"
    )

    return {
        "supporting_apis": (
            supporting_apis
        ),
        "pattern_count": (
            pattern_count
        ),
        "distinct_api_count": (
            api_count
        ),
        "independent_report_count": (
            report_count
        ),
        "support_tier": final_tier,
        "tier_rationale": rationale,
    }


def family_sequence(
    family_snapshot: dict[str, Any],
    framework: str,
) -> int:
    prefix = (
        f"pf_{framework_prefix(framework)}_"
    )
    maximum = 0

    for family_id in family_snapshot[
        "latest"
    ]:
        if not family_id.startswith(
            prefix
        ):
            continue

        match = re.search(
            r"_f(\d+)$",
            family_id,
        )

        if match:
            maximum = max(
                maximum,
                int(match.group(1)),
            )

    return maximum + 1


def allocate_family_id(
    canonical_name: str,
    framework: str,
    sequence_state: dict[str, int],
    reserved_ids: set[str],
) -> str:
    prefix = framework_prefix(
        framework
    )
    canonical_slug = slugify(
        canonical_name
    )

    while True:
        sequence = sequence_state[
            "next"
        ]
        sequence_state["next"] += 1

        family_id = (
            f"pf_{prefix}_"
            f"{canonical_slug}_"
            f"f{sequence:03d}"
        )

        if family_id not in reserved_ids:
            reserved_ids.add(
                family_id
            )
            return family_id


def existing_family_ref(
    artifact: dict[str, Any],
    relation: str,
) -> dict[str, Any]:
    return {
        "family_id": artifact[
            "family_id"
        ],
        "revision": artifact[
            "revision"
        ],
        "family_hash": artifact[
            "family_hash"
        ],
        "relation": relation,
    }


def materialize_family_record(
    proposal: dict[str, Any],
    framework: str,
    bundle: dict[str, Any],
    decision_result: dict[str, Any],
    configuration: dict[str, Any],
    family_snapshot: dict[str, Any],
    sequence_state: dict[str, int],
    reserved_ids: set[str],
    generated_at: str,
) -> tuple[
    dict[str, Any],
    str,
    int,
    str,
]:
    lineage = proposal["lineage"]
    action = lineage["action"]
    latest = family_snapshot[
        "latest"
    ]

    parent_refs: list[
        dict[str, Any]
    ] = []
    previous_family_hash: (
        str
        | None
    ) = None

    if action == "update_existing":
        target = latest[
            lineage[
                "target_family_id"
            ]
        ]
        family_id = target[
            "family_id"
        ]
        revision = (
            target["revision"]
            + 1
        )
        previous_family_hash = (
            target[
                "family_hash"
            ]
        )

        old_members = {
            item["pattern_id"]
            for item in target[
                "data"
            ].get("members", [])
        }
        new_members = {
            item["pattern_id"]
            for item in proposal[
                "members"
            ]
        }

        change_type = (
            "member_update"
            if old_members != new_members
            else "member_reanalysis"
        )
        outcome = (
            "created_new_revision"
        )

    else:
        family_id = allocate_family_id(
            canonical_name=proposal[
                "canonical_name"
            ],
            framework=framework,
            sequence_state=(
                sequence_state
            ),
            reserved_ids=(
                reserved_ids
            ),
        )
        revision = 1

        if action == "create_new":
            change_type = (
                "initial_creation"
            )
            outcome = (
                "created_new_family"
            )

        elif action == "derive_new":
            change_type = (
                "initial_creation"
            )
            outcome = (
                "created_derived_family"
            )
            parent_refs = [
                existing_family_ref(
                    latest[parent_id],
                    "derived_from",
                )
                for parent_id
                in lineage[
                    "parent_family_ids"
                ]
            ]

        elif action == "merge_existing":
            change_type = (
                "family_merge"
            )
            outcome = (
                "created_merged_family"
            )
            parent_refs = [
                existing_family_ref(
                    latest[parent_id],
                    "merged_from",
                )
                for parent_id
                in lineage[
                    "parent_family_ids"
                ]
            ]

        elif action == "split_existing":
            change_type = (
                "family_split"
            )
            outcome = (
                "created_split_child"
            )
            parent_refs = [
                existing_family_ref(
                    latest[
                        lineage[
                            "parent_family_ids"
                        ][0]
                    ],
                    "split_from",
                )
            ]

        else:
            raise PipelineError(
                "materialization",
                "unsupported_materialization_action",
                f"Cannot create a Family for action {action!r}.",
            )

    materialized_members: list[
        dict[str, Any]
    ] = []

    for member in sorted(
        proposal["members"],
        key=lambda item: item[
            "pattern_id"
        ],
    ):
        source = bundle[
            "members_by_id"
        ][member["pattern_id"]]

        materialized_members.append(
            {
                "pattern_id": (
                    member[
                        "pattern_id"
                    ]
                ),
                "pattern_hash": (
                    source[
                        "pattern_hash"
                    ]
                ),
                "primary_api": (
                    source[
                        "primary_api"
                    ]
                ),
                "source_report_ids": (
                    sorted(
                        set(
                            source.get(
                                "source_report_ids",
                                [],
                            )
                        )
                    )
                ),
                "membership_rationale": (
                    member[
                        "membership_rationale"
                    ]
                ),
                "evidence_status": (
                    member[
                        "evidence_status"
                    ]
                ),
                "evidence_refs": (
                    member[
                        "evidence_refs"
                    ]
                ),
                "confidence": (
                    member[
                        "confidence"
                    ]
                ),
            }
        )

    shared = proposal[
        "shared_characteristics"
    ]
    applicability = proposal[
        "applicability"
    ]
    heterogeneity = proposal[
        "heterogeneity"
    ]

    record = {
        "schema_version": (
            FAMILY_SCHEMA_VERSION
        ),
        "metadata": {
            "family_id": family_id,
            "canonical_name": (
                proposal[
                    "canonical_name"
                ]
            ),
            "framework": framework,
        },
        "revision_information": {
            "revision": revision,
            "previous_family_hash": (
                previous_family_hash
            ),
            "change_type": (
                change_type
            ),
            "parent_family_refs": (
                parent_refs
            ),
            "change_summary": (
                None
                if action
                == "create_new"
                else lineage[
                    "rationale"
                ]
            ),
        },
        "provenance": {
            "method": "llm_assisted",
            "candidate_policy_version": (
                configuration[
                    "candidate_policy"
                ]["policy_version"]
            ),
            "candidate_policy_hash": (
                configuration[
                    "candidate_policy_hash"
                ]
            ),
            "family_contract_version": (
                configuration[
                    "family_contract_version"
                ]
            ),
            "family_contract_hash": (
                configuration[
                    "family_contract_hash"
                ]
            ),
            "family_rules_version": (
                configuration[
                    "family_rules_version"
                ]
            ),
            "family_rules_hash": (
                configuration[
                    "family_rules_hash"
                ]
            ),
            "prompt_version": (
                PROMPT_VERSION
            ),
            "model": (
                decision_result[
                    "record"
                ]["analysis_input"][
                    "model"
                ]["model"]
            ),
            "input_candidate_manifests": [
                {
                    "candidate_group_id": (
                        bundle[
                            "candidate_group_id"
                        ]
                    ),
                    "candidate_group_hash": (
                        bundle[
                            "candidate_group_hash"
                        ]
                    ),
                }
            ],
            "source_decision_record": {
                "decision_record_id": (
                    decision_result[
                        "record"
                    ]["metadata"][
                        "decision_record_id"
                    ]
                ),
                "decision_record_hash": (
                    decision_result[
                        "record_hash"
                    ]
                ),
                "analysis_input_hash": (
                    decision_result[
                        "record"
                    ]["metadata"][
                        "analysis_input_hash"
                    ]
                ),
            },
            "generated_at": (
                generated_at
            ),
            "validation_status": (
                "automatically_validated"
            ),
        },
        "review": {
            "reviewer": None,
            "reviewed_at": None,
            "review_notes": [],
        },
        "members": materialized_members,
        "family_core": copy.deepcopy(
            proposal["family_core"]
        ),
        "shared_characteristics": {
            "trigger_semantics": (
                add_local_ids(
                    shared[
                        "trigger_semantics"
                    ],
                    "characteristic_id",
                    "st_",
                )
            ),
            "mechanism_semantics": (
                add_local_ids(
                    shared[
                        "mechanism_semantics"
                    ],
                    "characteristic_id",
                    "sm_",
                )
            ),
            "execution_semantics": (
                add_local_ids(
                    shared[
                        "execution_semantics"
                    ],
                    "characteristic_id",
                    "se_",
                )
            ),
            "failure_observables": (
                add_local_ids(
                    shared[
                        "failure_observables"
                    ],
                    "characteristic_id",
                    "sf_",
                )
            ),
        },
        "applicability": {
            "required_capabilities": (
                add_local_ids(
                    applicability[
                        "required_capabilities"
                    ],
                    "condition_id",
                    "rc_",
                )
            ),
            "exclusion_conditions": (
                add_local_ids(
                    applicability[
                        "exclusion_conditions"
                    ],
                    "condition_id",
                    "ec_",
                )
            ),
        },
        "heterogeneity": {
            "member_differences": (
                add_local_ids(
                    heterogeneity[
                        "member_differences"
                    ],
                    "difference_id",
                    "md_",
                )
            ),
            "unresolved_conflicts": (
                add_local_ids(
                    heterogeneity[
                        "unresolved_conflicts"
                    ],
                    "conflict_id",
                    "uc_",
                )
            ),
        },
        "support": support_tier(
            proposal,
            materialized_members,
        ),
        "confidence": copy.deepcopy(
            proposal["confidence"]
        ),
    }

    validate_materialized_family(
        record
    )

    return (
        record,
        family_id,
        revision,
        outcome,
    )


def validate_materialized_family(
    record: dict[str, Any],
) -> None:
    required_top_level = {
        "schema_version",
        "metadata",
        "revision_information",
        "provenance",
        "review",
        "members",
        "family_core",
        "shared_characteristics",
        "applicability",
        "heterogeneity",
        "support",
        "confidence",
    }

    if set(record) != required_top_level:
        raise PipelineError(
            "family_validation",
            "invalid_family_top_level",
            "Materialized Family has invalid top-level fields.",
        )

    if record.get(
        "schema_version"
    ) != FAMILY_SCHEMA_VERSION:
        raise PipelineError(
            "family_validation",
            "family_schema_version_mismatch",
            "Materialized Family uses the wrong schema version.",
        )

    reject_empty_strings(
        record
    )

    members = record["members"]
    support = record["support"]

    if support[
        "pattern_count"
    ] != len(members):
        raise PipelineError(
            "family_validation",
            "support_count_mismatch",
            "Family support.pattern_count is incorrect.",
        )

    if len(
        {
            member["pattern_id"]
            for member in members
        }
    ) != len(members):
        raise PipelineError(
            "family_validation",
            "duplicate_materialized_member",
            "Materialized Family contains duplicate members.",
        )


def family_output_path(
    framework: str,
    family_id: str,
    revision: int,
) -> Path:
    return (
        FAMILY_ROOT
        / slugify(framework)
        / family_id
        / (
            f"{family_id}_"
            f"r{revision:03d}.json"
        )
    )


def load_previous_materializations(
    framework: str,
    family_snapshot: dict[str, Any],
) -> dict[
    tuple[str, int],
    dict[str, Any]
]:
    root = (
        CONVERSION_RUN_ROOT
        / slugify(framework)
    )

    mappings: dict[
        tuple[str, int],
        dict[str, Any]
    ] = {}

    if not root.is_dir():
        return mappings

    for path in sorted(
        root.glob(
            "*/conversion_run_index.json"
        )
    ):
        try:
            run = load_json(path)
        except PipelineError as exc:
            raise PipelineError(
                "decision_lookup",
                "invalid_conversion_run_index",
                "Unable to load previous Conversion Run Index: "
                f"{path}",
                False,
            ) from exc

        if run.get(
            "conversion_run_index_version"
        ) != CONVERSION_RUN_INDEX_VERSION:
            raise PipelineError(
                "decision_lookup",
                "conversion_run_version_mismatch",
                "Previous Conversion Run Index uses an incompatible "
                f"version: {path}",
                False,
            )

        for result in run.get(
            "candidate_results",
            [],
        ):
            if not isinstance(result, dict):
                continue

            decision = result.get(
                "decision",
                {},
            )
            decision_hash = decision.get(
                "decision_record_hash"
            )

            if not isinstance(
                decision_hash,
                str,
            ):
                continue

            materialization = result.get(
                "materialization",
                {},
            )

            for item in materialization.get(
                "results",
                [],
            ):
                if not isinstance(item, dict):
                    continue

                proposal_index = item.get(
                    "proposed_family_index"
                )
                family_ref = item.get(
                    "family_ref"
                )

                if (
                    not isinstance(
                        proposal_index,
                        int,
                    )
                    or not isinstance(
                        family_ref,
                        dict,
                    )
                ):
                    continue

                family_id = family_ref.get(
                    "family_id"
                )
                revision = family_ref.get(
                    "family_revision"
                )
                expected_hash = family_ref.get(
                    "family_artifact_hash"
                )

                artifact = (
                    family_snapshot[
                        "by_key"
                    ].get(
                        (
                            family_id,
                            revision,
                        )
                    )
                )

                if (
                    artifact is None
                    or artifact[
                        "family_hash"
                    ]
                    != expected_hash
                ):
                    continue

                key = (
                    decision_hash,
                    proposal_index,
                )

                previous = mappings.get(
                    key
                )

                if (
                    previous is not None
                    and previous
                    != family_ref
                ):
                    raise PipelineError(
                        "decision_lookup",
                        "materialization_mapping_conflict",
                        "Conflicting previous materialization mappings "
                        f"exist for {key}.",
                        False,
                    )

                mappings[key] = copy.deepcopy(
                    family_ref
                )

    return mappings


def materialize_decision(
    framework: str,
    bundle: dict[str, Any],
    decision_result: dict[str, Any],
    configuration: dict[str, Any],
    family_snapshot: dict[str, Any],
    previous_materializations: dict[
        tuple[str, int],
        dict[str, Any]
    ],
    sequence_state: dict[str, int],
    reserved_ids: set[str],
) -> dict[str, Any]:
    payload = decision_result[
        "record"
    ]["decision_payload"]
    decision = payload["decision"]

    if decision in {
        "reject",
        "needs_revision",
    }:
        return {
            "status": "not_applicable",
            "results": [],
        }

    generated_at = utc_timestamp()
    staged: list[
        tuple[
            Path,
            Path,
            dict[str, Any],
        ]
    ] = []
    results: list[
        dict[str, Any]
    ] = []

    staging_parent = (
        EXP006_DIR
        / "quality"
        / ".pattern_family_staging"
    )
    staging_parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    staging_directory = Path(
        tempfile.mkdtemp(
            prefix="family_candidate_",
            dir=staging_parent,
        )
    )

    try:
        for proposal_index, proposal in enumerate(
            payload[
                "proposed_families"
            ]
        ):
            action = proposal[
                "lineage"
            ]["action"]

            idempotency_key = (
                decision_result[
                    "record_hash"
                ],
                proposal_index,
            )

            prior_ref = (
                previous_materializations.get(
                    idempotency_key
                )
            )

            if prior_ref is not None:
                results.append(
                    {
                        "proposed_family_index": (
                            proposal_index
                        ),
                        "requested_lineage_action": (
                            action
                        ),
                        "outcome": (
                            "reused_existing_revision"
                        ),
                        "family_ref": copy.deepcopy(
                            prior_ref
                        ),
                        "error_codes": [],
                    }
                )
                continue

            if action == "reuse_existing":
                target_id = proposal[
                    "lineage"
                ]["target_family_id"]
                target = family_snapshot[
                    "latest"
                ][target_id]

                results.append(
                    {
                        "proposed_family_index": (
                            proposal_index
                        ),
                        "requested_lineage_action": (
                            action
                        ),
                        "outcome": (
                            "reused_existing_revision"
                        ),
                        "family_ref": {
                            "family_id": (
                                target[
                                    "family_id"
                                ]
                            ),
                            "family_revision": (
                                target[
                                    "revision"
                                ]
                            ),
                            "family_artifact_hash": (
                                target[
                                    "family_hash"
                                ]
                            ),
                        },
                        "error_codes": [],
                    }
                )
                continue

            (
                record,
                family_id,
                revision,
                outcome,
            ) = materialize_family_record(
                proposal=proposal,
                framework=framework,
                bundle=bundle,
                decision_result=(
                    decision_result
                ),
                configuration=configuration,
                family_snapshot=(
                    family_snapshot
                ),
                sequence_state=(
                    sequence_state
                ),
                reserved_ids=(
                    reserved_ids
                ),
                generated_at=(
                    generated_at
                ),
            )

            destination = family_output_path(
                framework=framework,
                family_id=family_id,
                revision=revision,
            )

            if destination.exists():
                raise PipelineError(
                    "artifact_write",
                    "family_artifact_exists",
                    "Refusing to overwrite existing Family artifact: "
                    f"{destination}",
                    False,
                )

            staged_path = (
                staging_directory
                / destination.name
            )

            data = pretty_json_bytes(
                record
            )
            staged_path.write_bytes(
                data
            )
            artifact_hash = (
                "sha256:"
                + hashlib.sha256(
                    data
                ).hexdigest()
            )

            staged.append(
                (
                    staged_path,
                    destination,
                    record,
                )
            )

            results.append(
                {
                    "proposed_family_index": (
                        proposal_index
                    ),
                    "requested_lineage_action": (
                        action
                    ),
                    "outcome": outcome,
                    "family_ref": {
                        "family_id": family_id,
                        "family_revision": (
                            revision
                        ),
                        "family_artifact_hash": (
                            artifact_hash
                        ),
                    },
                    "error_codes": [],
                }
            )

        committed: list[Path] = []

        try:
            for (
                staged_path,
                destination,
                _record,
            ) in staged:
                destination.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                os.link(
                    staged_path,
                    destination,
                )
                committed.append(
                    destination
                )

        except Exception as exc:
            for destination in reversed(
                committed
            ):
                try:
                    destination.unlink()
                except OSError:
                    pass

            raise PipelineError(
                "artifact_write",
                "candidate_atomic_commit_failed",
                "Candidate-level Family commit failed.",
                True,
            ) from exc

        return {
            "status": "succeeded",
            "results": results,
        }

    finally:
        shutil.rmtree(
            staging_directory,
            ignore_errors=True,
        )


def next_conversion_run_id(
    framework: str,
) -> str:
    root = (
        CONVERSION_RUN_ROOT
        / slugify(framework)
    )
    prefix = (
        f"pfxr_"
        f"{framework_prefix(framework)}_"
    )
    maximum = 0

    if root.is_dir():
        for path in root.iterdir():
            if not path.is_dir():
                continue

            match = re.fullmatch(
                re.escape(prefix)
                + r"(\d{6})",
                path.name,
            )

            if match:
                maximum = max(
                    maximum,
                    int(match.group(1)),
                )

    return (
        f"{prefix}"
        f"{maximum + 1:06d}"
    )


def build_summary(
    current_candidate_count: int,
    candidate_results: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:
    completed = sum(
        result[
            "processing_status"
        ]
        == "completed"
        for result in candidate_results
    )
    failed = len(
        candidate_results
    ) - completed

    decision_record_counts = {
        "generated": 0,
        "reused": 0,
    }

    decision_counts = {
        "accept": 0,
        "split": 0,
        "reject": 0,
        "needs_revision": 0,
    }

    total_usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }

    materialization_counts = {
        "created_new_family": 0,
        "reused_existing_revision": 0,
        "created_new_revision": 0,
        "created_derived_family": 0,
        "created_merged_family": 0,
        "created_split_child": 0,
        "failed": 0,
    }

    llm_call_count = 0
    invalid_attempt_count = 0

    for result in candidate_results:
        decision = result[
            "decision"
        ]
        source = decision["source"]

        if source in decision_record_counts:
            decision_record_counts[
                source
            ] += 1

        decision_value = decision.get(
            "decision_value"
        )

        if decision_value in decision_counts:
            decision_counts[
                decision_value
            ] += 1

        llm_call_count += decision.get(
            "llm_call_count",
            0,
        )
        invalid_attempt_count += (
            decision.get(
                "invalid_attempt_count",
                0,
            )
        )

        add_usage(
            total_usage,
            decision.get(
                "token_usage",
                {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                },
            ),
        )

        for item in result[
            "materialization"
        ]["results"]:
            outcome = item[
                "outcome"
            ]

            if outcome in materialization_counts:
                materialization_counts[
                    outcome
                ] += 1

    selected = len(
        candidate_results
    )

    return {
        "current_candidate_count": (
            current_candidate_count
        ),
        "selected_candidate_count": (
            selected
        ),
        "not_selected_candidate_count": (
            current_candidate_count
            - selected
        ),
        "completed_candidate_count": (
            completed
        ),
        "failed_candidate_count": (
            failed
        ),
        "decision_record_counts": (
            decision_record_counts
        ),
        "decision_counts": (
            decision_counts
        ),
        "llm_call_count": (
            llm_call_count
        ),
        "invalid_attempt_count": (
            invalid_attempt_count
        ),
        "token_usage": total_usage,
        "materialization_counts": (
            materialization_counts
        ),
    }


def empty_decision_result() -> dict[str, Any]:
    return {
        "source": "unavailable",
        "decision_record_id": None,
        "decision_record_hash": None,
        "analysis_input_hash": None,
        "decision_value": None,
        "llm_call_count": 0,
        "invalid_attempt_count": 0,
        "token_usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        },
    }


def process_candidate(
    framework: str,
    bundle: dict[str, Any],
    existing_context: dict[str, Any],
    configuration: dict[str, Any],
    analysis: dict[str, Any],
    script_hash: str,
    api_url: str,
    api_key: str,
    model: str,
    max_output_tokens: int,
    max_attempts: int,
    timeout_seconds: int,
    family_snapshot: dict[str, Any],
    previous_materializations: dict[
        tuple[str, int],
        dict[str, Any]
    ],
    sequence_state: dict[str, int],
    reserved_ids: set[str],
    selection_reason: str,
) -> dict[str, Any]:
    result = {
        "candidate_group_id": (
            bundle[
                "candidate_group_id"
            ]
        ),
        "candidate_group_hash": (
            bundle[
                "candidate_group_hash"
            ]
        ),
        "selection_reason": (
            selection_reason
        ),
        "processing_status": (
            "failed"
        ),
        "decision": (
            empty_decision_result()
        ),
        "failed_attempts": [],
        "materialization": {
            "status": "not_started",
            "results": [],
        },
        "errors": [],
    }

    try:
        decision_result = obtain_decision(
            framework=framework,
            bundle=bundle,
            existing_context=(
                existing_context
            ),
            configuration=configuration,
            analysis=analysis,
            script_hash=script_hash,
            api_url=api_url,
            api_key=api_key,
            model=model,
            max_output_tokens=(
                max_output_tokens
            ),
            max_attempts=max_attempts,
            timeout_seconds=(
                timeout_seconds
            ),
        )

        record = decision_result[
            "record"
        ]
        payload = record[
            "decision_payload"
        ]

        result["decision"] = {
            "source": (
                decision_result[
                    "source"
                ]
            ),
            "decision_record_id": (
                record["metadata"][
                    "decision_record_id"
                ]
            ),
            "decision_record_hash": (
                decision_result[
                    "record_hash"
                ]
            ),
            "analysis_input_hash": (
                record["metadata"][
                    "analysis_input_hash"
                ]
            ),
            "decision_value": (
                payload["decision"]
            ),
            "llm_call_count": (
                decision_result[
                    "llm_call_count"
                ]
            ),
            "invalid_attempt_count": (
                len(
                    decision_result[
                        "failed_attempts"
                    ]
                )
            ),
            "token_usage": (
                decision_result[
                    "token_usage"
                ]
            ),
        }
        result["failed_attempts"] = (
            decision_result[
                "failed_attempts"
            ]
        )

        result["materialization"] = (
            materialize_decision(
                framework=framework,
                bundle=bundle,
                decision_result=(
                    decision_result
                ),
                configuration=(
                    configuration
                ),
                family_snapshot=(
                    family_snapshot
                ),
                previous_materializations=(
                    previous_materializations
                ),
                sequence_state=(
                    sequence_state
                ),
                reserved_ids=(
                    reserved_ids
                ),
            )
        )

        result["processing_status"] = (
            "completed"
        )

    except PipelineError as exc:
        result["errors"].append(
            exc.as_record()
        )

        if exc.failed_attempts:
            result["failed_attempts"] = (
                copy.deepcopy(
                    exc.failed_attempts
                )
            )
            result["decision"][
                "llm_call_count"
            ] = exc.llm_call_count
            result["decision"][
                "invalid_attempt_count"
            ] = len(
                exc.failed_attempts
            )
            result["decision"][
                "token_usage"
            ] = copy.deepcopy(
                exc.token_usage
            )

        if result[
            "materialization"
        ]["status"] != "not_started":
            result[
                "materialization"
            ]["status"] = "failed"

    except Exception as exc:
        result["errors"].append(
            {
                "stage": "materialization",
                "code": (
                    "unexpected_candidate_error"
                ),
                "message": (
                    f"Unexpected candidate error: "
                    f"{type(exc).__name__}"
                ),
                "recoverable": True,
            }
        )

    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert deterministic Pattern Family Candidates into "
            "validated Decision Records and formal Pattern Families."
        )
    )

    parser.add_argument(
        "--framework",
        required=True,
        help="Framework name, for example pytorch.",
    )
    parser.add_argument(
        "--candidate-run",
        help=(
            "Candidate Run ID or path to candidate_run_index.json. "
            "Defaults to the latest Run for the framework."
        ),
    )
    parser.add_argument(
        "--candidate-id",
        action="append",
        dest="candidate_ids",
        default=[],
        help=(
            "Explicit Candidate ID. May be supplied multiple times. "
            "When omitted, cache-aware selection is used."
        ),
    )
    parser.add_argument(
        "--candidate-policy",
        default=str(
            DEFAULT_CANDIDATE_POLICY_PATH
        ),
    )
    parser.add_argument(
        "--family-contract",
        default=str(
            DEFAULT_FAMILY_CONTRACT_PATH
        ),
    )
    parser.add_argument(
        "--family-rules",
        default=str(
            DEFAULT_FAMILY_RULES_PATH
        ),
    )
    parser.add_argument(
        "--family-schema",
        default=str(
            DEFAULT_FAMILY_SCHEMA_PATH
        ),
    )
    parser.add_argument(
        "--provider",
        default=DEFAULT_PROVIDER,
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
    )
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get(
            "DEEPSEEK_API_KEY"
        ),
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=(
            DEFAULT_MAX_OUTPUT_TOKENS
        ),
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=DEFAULT_MAX_ATTEMPTS,
    )
    parser.add_argument(
        "--max-existing-families",
        type=int,
        default=(
            DEFAULT_MAX_EXISTING_FAMILIES
        ),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=180,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Validate and print the execution plan without calling "
            "the LLM or writing artifacts."
        ),
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.max_attempts < 1:
        parser.error(
            "--max-attempts must be at least 1."
        )

    if args.max_existing_families < 0:
        parser.error(
            "--max-existing-families must be non-negative."
        )

    if args.max_output_tokens < 1:
        parser.error(
            "--max-output-tokens must be positive."
        )

    if (
        not args.dry_run
        and not args.api_key
    ):
        parser.error(
            "--api-key or DEEPSEEK_API_KEY is required for a non-dry run."
        )

    framework = args.framework.strip()
    started_at = utc_timestamp()
    started_clock = time.monotonic()

    try:
        configuration = load_configuration(
            candidate_policy_path=Path(
                args.candidate_policy
            ).resolve(),
            family_contract_path=Path(
                args.family_contract
            ).resolve(),
            family_rules_path=Path(
                args.family_rules
            ).resolve(),
            family_schema_path=Path(
                args.family_schema
            ).resolve(),
        )

        candidate_run_path = (
            resolve_candidate_run_path(
                framework=framework,
                candidate_run=(
                    args.candidate_run
                ),
            )
        )
        candidate_run = load_json(
            candidate_run_path
        )
        candidate_run_hash = file_hash(
            candidate_run_path
        )

        run_metadata = candidate_run.get(
            "metadata"
        )

        if not isinstance(
            run_metadata,
            dict,
        ):
            raise PipelineError(
                "candidate_loading",
                "invalid_candidate_run_metadata",
                "Candidate Run metadata must be an object.",
                False,
            )

        if run_metadata.get(
            "framework"
        ) != framework:
            raise PipelineError(
                "candidate_loading",
                "candidate_run_framework_mismatch",
                "Candidate Run framework does not match --framework.",
                False,
            )
        expected_run_version = (
            configuration[
                "candidate_policy"
            ]["run_index_version"]
        )

        if candidate_run.get(
            "run_version"
        ) != expected_run_version:
            raise PipelineError(
                "candidate_loading",
                "candidate_run_version_mismatch",
                "Candidate Run version does not match the current "
                "Candidate Policy.",
                False,
            )

        run_generation = candidate_run.get(
            "generation_information"
        )

        if not isinstance(
            run_generation,
            dict,
        ):
            raise PipelineError(
                "candidate_loading",
                "invalid_candidate_run_generation",
                "Candidate Run generation_information must be an object.",
                False,
            )

        if run_generation.get(
            "retrieval_policy_version"
        ) != configuration[
            "candidate_policy"
        ]["policy_version"]:
            raise PipelineError(
                "candidate_loading",
                "candidate_policy_version_mismatch",
                "Candidate Run was generated with a different "
                "Candidate Policy version.",
                False,
            )

        if run_generation.get(
            "retrieval_policy_hash"
        ) != configuration[
            "candidate_policy_hash"
        ]:
            raise PipelineError(
                "candidate_loading",
                "candidate_policy_hash_mismatch",
                "Candidate Run was generated from different Candidate "
                "Policy content.",
                False,
            )

        candidate_entries = candidate_run.get(
            "candidates"
        )

        if not isinstance(
            candidate_entries,
            list,
        ):
            raise PipelineError(
                "candidate_loading",
                "invalid_candidate_run_entries",
                "Candidate Run candidates must be an array.",
                False,
            )

        candidate_entries = sorted(
            candidate_entries,
            key=lambda item: item[
                "candidate_group_id"
            ],
        )

        entry_by_id = {
            entry["candidate_group_id"]: entry
            for entry in candidate_entries
        }

        explicit_ids = sorted(
            set(args.candidate_ids)
        )

        if explicit_ids:
            unknown_ids = sorted(
                set(explicit_ids)
                - set(entry_by_id)
            )

            if unknown_ids:
                raise PipelineError(
                    "candidate_loading",
                    "unknown_explicit_candidate",
                    f"Explicit Candidate IDs are not in the input Run: {unknown_ids}",
                    False,
                )

            selection_mode = (
                "explicit_candidates"
            )
            requested_ids = explicit_ids
            selected_entries = [
                entry_by_id[
                    candidate_id
                ]
                for candidate_id
                in explicit_ids
            ]

        else:
            selection_mode = (
                "cache_aware"
            )
            requested_ids = []
            selected_entries = (
                candidate_entries
            )

        family_snapshot = (
            load_family_snapshot(
                framework
            )
        )
        previous_materializations = (
            load_previous_materializations(
                framework,
                family_snapshot,
            )
        )

        script_hash = file_hash(
            Path(__file__).resolve()
        )

        plans: list[
            dict[str, Any]
        ] = []

        for entry in selected_entries:
            bundle = load_candidate_bundle(
                entry=entry,
                framework=framework,
            )

            existing_context = (
                select_existing_family_context(
                    bundle=bundle,
                    family_snapshot=(
                        family_snapshot
                    ),
                    max_families=(
                        args.max_existing_families
                    ),
                )
            )

            analysis = (
                build_analysis_descriptor(
                    bundle=bundle,
                    existing_context=(
                        existing_context
                    ),
                    configuration=(
                        configuration
                    ),
                    provider=args.provider,
                    model=args.model,
                    max_output_tokens=(
                        args.max_output_tokens
                    ),
                )
            )

            cache_path = decision_record_path(
                framework,
                analysis[
                    "analysis_input_hash"
                ],
            )
            cache_hit = cache_path.is_file()

            if explicit_ids:
                selection_reason = (
                    "explicit_request"
                )
                should_process = True

            elif not cache_hit:
                selection_reason = (
                    "decision_cache_miss"
                )
                should_process = True

            else:
                cached_record = load_json(
                    cache_path
                )
                validate_cached_decision_record(
                    cached_record,
                    analysis[
                        "analysis_input_hash"
                    ],
                    framework,
                )
                validate_decision_payload(
                    cached_record[
                        "decision_payload"
                    ],
                    configuration[
                        "family_contract"
                    ],
                    bundle,
                    existing_context,
                )

                cached_hash = file_hash(
                    cache_path
                )
                proposals = cached_record[
                    "decision_payload"
                ]["proposed_families"]

                materialization_complete = all(
                    (
                        (
                            cached_hash,
                            index,
                        )
                        in previous_materializations
                    )
                    or (
                        proposal[
                            "lineage"
                        ]["action"]
                        == "reuse_existing"
                    )
                    for index, proposal
                    in enumerate(proposals)
                )

                if (
                    cached_record[
                        "decision_payload"
                    ]["decision"]
                    in {
                        "reject",
                        "needs_revision",
                    }
                ):
                    materialization_complete = (
                        True
                    )

                selection_reason = (
                    "materialization_required"
                )
                should_process = (
                    not materialization_complete
                )

            plans.append(
                {
                    "entry": entry,
                    "bundle": bundle,
                    "existing_context": (
                        existing_context
                    ),
                    "analysis": analysis,
                    "cache_hit": cache_hit,
                    "selection_reason": (
                        selection_reason
                    ),
                    "should_process": (
                        should_process
                    ),
                }
            )

        work_plans = [
            plan
            for plan in plans
            if plan[
                "should_process"
            ]
        ]

        if args.dry_run:
            print(
                json.dumps(
                    {
                        "dry_run": True,
                        "candidate_run_id": (
                            run_metadata[
                                "run_id"
                            ]
                        ),
                        "candidate_run_index_hash": (
                            candidate_run_hash
                        ),
                        "selection_mode": (
                            selection_mode
                        ),
                        "current_candidate_count": (
                            len(
                                candidate_entries
                            )
                        ),
                        "evaluated_candidate_count": (
                            len(plans)
                        ),
                        "selected_candidate_count": (
                            len(work_plans)
                        ),
                        "candidates": [
                            {
                                "candidate_group_id": (
                                    plan[
                                        "bundle"
                                    ][
                                        "candidate_group_id"
                                    ]
                                ),
                                "candidate_group_hash": (
                                    plan[
                                        "bundle"
                                    ][
                                        "candidate_group_hash"
                                    ]
                                ),
                                "analysis_input_hash": (
                                    plan[
                                        "analysis"
                                    ][
                                        "analysis_input_hash"
                                    ]
                                ),
                                "decision_cache_hit": (
                                    plan[
                                        "cache_hit"
                                    ]
                                ),
                                "selection_reason": (
                                    plan[
                                        "selection_reason"
                                    ]
                                ),
                                "would_process": (
                                    plan[
                                        "should_process"
                                    ]
                                ),
                                "existing_family_count": (
                                    len(
                                        plan[
                                            "existing_context"
                                        ][
                                            "record_context"
                                        ][
                                            "family_revisions"
                                        ]
                                    )
                                ),
                            }
                            for plan in plans
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if not work_plans:
            print(
                "No Candidate requires a new Decision or materialization."
            )
            return 0

        conversion_run_id = (
            next_conversion_run_id(
                framework
            )
        )

        sequence_state = {
            "next": family_sequence(
                family_snapshot,
                framework,
            )
        }
        reserved_ids = set(
            family_snapshot[
                "latest"
            ]
        )

        candidate_results: list[
            dict[str, Any]
        ] = []

        for plan in work_plans:
            result = process_candidate(
                framework=framework,
                bundle=plan["bundle"],
                existing_context=plan[
                    "existing_context"
                ],
                configuration=(
                    configuration
                ),
                analysis=plan["analysis"],
                script_hash=script_hash,
                api_url=args.api_url,
                api_key=args.api_key,
                model=args.model,
                max_output_tokens=(
                    args.max_output_tokens
                ),
                max_attempts=(
                    args.max_attempts
                ),
                timeout_seconds=(
                    args.timeout_seconds
                ),
                family_snapshot=(
                    family_snapshot
                ),
                previous_materializations=(
                    previous_materializations
                ),
                sequence_state=(
                    sequence_state
                ),
                reserved_ids=(
                    reserved_ids
                ),
                selection_reason=plan[
                    "selection_reason"
                ],
            )

            candidate_results.append(
                result
            )

        completed_at = utc_timestamp()
        duration_ms = int(
            (
                time.monotonic()
                - started_clock
            )
            * 1000
        )

        summary = build_summary(
            current_candidate_count=len(
                candidate_entries
            ),
            candidate_results=(
                candidate_results
            ),
        )

        if (
            summary[
                "failed_candidate_count"
            ]
            == 0
        ):
            run_status = "completed"
        elif (
            summary[
                "completed_candidate_count"
            ]
            > 0
        ):
            run_status = (
                "completed_with_failures"
            )
        else:
            run_status = "failed"

        retrieval_configuration = {
            "mode": (
                "related_candidate_history"
            ),
            "maximum_family_count": (
                args.max_existing_families
            ),
            "candidate_id_match_weight": 100,
            "member_pattern_overlap_weight": 20,
            "source_report_overlap_weight": 10,
            "tie_breaking": [
                "score_descending",
                "family_id_ascending",
                "revision_descending",
            ],
        }

        materialization_configuration = {
            "candidate_level_atomicity": True,
            "overwrite_existing": False,
            "idempotency_key": (
                "decision_record_hash"
                "+proposed_family_index"
            ),
            "family_id_format": (
                "pf_<framework-prefix>_"
                "<canonical-name>_f<sequence>"
            ),
            "family_revision_format": (
                "r<three-digit-sequence>"
            ),
        }

        model_configuration = {
            "temperature": 0,
            "top_p": 1,
            "max_output_tokens": (
                args.max_output_tokens
            ),
            "response_format": {
                "type": "json_object"
            },
        }

        conversion_run_index = {
            "conversion_run_index_version": (
                CONVERSION_RUN_INDEX_VERSION
            ),
            "metadata": {
                "conversion_run_id": (
                    conversion_run_id
                ),
                "framework": framework,
                "status": run_status,
            },
            "input": {
                "candidate_run": {
                    "candidate_run_id": (
                        run_metadata[
                            "run_id"
                        ]
                    ),
                    "candidate_run_index_hash": (
                        candidate_run_hash
                    ),
                },
                "selection": {
                    "mode": (
                        selection_mode
                    ),
                    "requested_candidate_ids": (
                        requested_ids
                    ),
                },
            },
            "configuration": {
                "conversion_script": {
                    "version": (
                        SCRIPT_VERSION
                    ),
                    "content_hash": (
                        script_hash
                    ),
                },
                "family_contract": {
                    "version": (
                        configuration[
                            "family_contract_version"
                        ]
                    ),
                    "content_hash": (
                        configuration[
                            "family_contract_hash"
                        ]
                    ),
                },
                "family_rules": {
                    "version": (
                        configuration[
                            "family_rules_version"
                        ]
                    ),
                    "content_hash": (
                        configuration[
                            "family_rules_hash"
                        ]
                    ),
                },
                "family_schema": {
                    "version": (
                        FAMILY_SCHEMA_VERSION
                    ),
                    "content_hash": (
                        configuration[
                            "family_schema_hash"
                        ]
                    ),
                },
                "prompt": {
                    "version": (
                        PROMPT_VERSION
                    ),
                    "template_hash": (
                        text_hash(
                            PROMPT_TEMPLATE
                        )
                    ),
                },
                "existing_family_retrieval": {
                    "mode": (
                        "related_candidate_history"
                    ),
                    "implementation": (
                        "script_builtin"
                    ),
                    "version": (
                        EXISTING_FAMILY_RETRIEVAL_VERSION
                    ),
                    "configuration_hash": (
                        canonical_hash(
                            retrieval_configuration
                        )
                    ),
                },
                "materialization": {
                    "implementation": (
                        "script_builtin"
                    ),
                    "version": (
                        MATERIALIZATION_VERSION
                    ),
                    "configuration_hash": (
                        canonical_hash(
                            materialization_configuration
                        )
                    ),
                },
                "model": {
                    "provider": (
                        args.provider
                    ),
                    "model_name": (
                        args.model
                    ),
                    "configuration": (
                        model_configuration
                    ),
                    "configuration_hash": (
                        canonical_hash(
                            model_configuration
                        )
                    ),
                },
                "retry_policy": {
                    "max_attempts_per_candidate": (
                        args.max_attempts
                    ),
                },
            },
            "timing": {
                "started_at": (
                    started_at
                ),
                "completed_at": (
                    completed_at
                ),
                "duration_ms": (
                    duration_ms
                ),
            },
            "summary": summary,
            "candidate_results": (
                candidate_results
            ),
            "run_errors": [],
        }

        output_path = (
            CONVERSION_RUN_ROOT
            / slugify(framework)
            / conversion_run_id
            / "conversion_run_index.json"
        )

        run_hash = write_json_exclusive(
            output_path,
            conversion_run_index,
        )

        print(
            json.dumps(
                {
                    "status": run_status,
                    "conversion_run_id": (
                        conversion_run_id
                    ),
                    "conversion_run_index": (
                        str(output_path)
                    ),
                    "conversion_run_index_hash": (
                        run_hash
                    ),
                    "summary": summary,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

        return (
            0
            if run_status
            == "completed"
            else 1
        )

    except PipelineError as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error": (
                        exc.as_record()
                    ),
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())