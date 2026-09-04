from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any


SCRIPT_VERSION = "build_pattern_family_candidates_v2"
RUN_INDEX_VERSION = "1.0"

SCRIPT_DIR = Path(__file__).resolve().parent
EXP006_DIR = SCRIPT_DIR.parent

DEFAULT_PATTERN_ROOT = EXP006_DIR / "bug_patterns"

DEFAULT_POLICY_FILE = (
    EXP006_DIR
    / "schemas"
    / "pattern_family_candidate_policy.json"
)

DEFAULT_OUTPUT_ROOT = (
    EXP006_DIR
    / "quality"
    / "pattern_family_candidates"
)


class PatternSkipped(Exception):
    """The Pattern is valid enough to inspect but is ineligible by Policy."""


@dataclass(frozen=True)
class PatternRecord:
    path: Path
    pattern_relpath: str
    pattern_id: str
    pattern_hash: str
    framework: str
    primary_api: str
    source_report_ids: tuple[str, ...]
    validation_status: str
    retrieval_signature: dict[str, Any]
    signal_provenance: dict[str, Any]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_json_hash(value: Any) -> str:
    digest = hashlib.sha256(
        canonical_json_bytes(value)
    ).hexdigest()

    return f"sha256:{digest}"


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        while True:
            block = file.read(1024 * 1024)

            if not block:
                break

            digest.update(block)

    return f"sha256:{digest.hexdigest()}"


def utc_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def slugify(value: str) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized)
    return normalized.strip("_")


def require_dict(
    value: Any,
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(
            f"{label} must be an object"
        )

    return value


def require_list(
    value: Any,
    label: str,
) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(
            f"{label} must be an array"
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
        raise ValueError(
            f"{label} must be a non-empty string"
        )

    return value.strip()


def meaningful_scalar(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and value.strip().lower() != "unknown"
    )


def normalize_scalar(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = value.strip()

    if not normalized:
        return None

    return normalized


def normalize_array(
    value: Any,
    label: str,
    policy: dict[str, Any],
) -> list[str]:
    values = require_list(value, label)

    array_policy = policy[
        "normalization"
    ]["array_normalization"]

    normalized: list[str] = []

    for item in values:
        if (
            item is None
            and array_policy["remove_null"]
        ):
            continue

        if not isinstance(item, str):
            raise ValueError(
                f"{label} must contain only strings"
            )

        item = item.strip()

        if (
            not item
            and array_policy["remove_empty_string"]
        ):
            continue

        if (
            item.lower() == "unknown"
            and array_policy["remove_unknown_enum"]
        ):
            continue

        normalized.append(item)

    if array_policy["remove_duplicates"]:
        normalized = list(
            dict.fromkeys(normalized)
        )

    if array_policy["sort_values"]:
        normalized = sorted(normalized)

    return normalized


def assert_within_exp006(path: Path) -> None:
    try:
        path.resolve().relative_to(
            EXP006_DIR.resolve()
        )
    except ValueError as error:
        raise ValueError(
            "Pattern files must be located "
            "inside EXP006"
        ) from error


def validate_policy(
    policy: dict[str, Any],
) -> None:
    require_string(
        policy.get("policy_version"),
        "policy_version",
    )

    require_string(
        policy.get("manifest_version"),
        "manifest_version",
    )

    run_index_version = require_string(
        policy.get("run_index_version"),
        "run_index_version",
    )

    if run_index_version != RUN_INDEX_VERSION:
        raise ValueError(
            "Policy run_index_version does not "
            f"match script: {run_index_version!r} "
            f"!= {RUN_INDEX_VERSION!r}"
        )

    execution_boundary = require_dict(
        policy.get("execution_boundary"),
        "execution_boundary",
    )

    forbidden_enabled_fields = [
        "llm_usage_allowed",
        "embedding_usage_allowed",
        "semantic_summary_allowed",
        "family_decision_allowed",
        "general_knowledge_generation_allowed",
    ]

    for field_name in forbidden_enabled_fields:
        if execution_boundary.get(field_name) is not False:
            raise ValueError(
                f"{field_name} must be false for "
                "deterministic Candidate generation"
            )

    artifact_policy = require_dict(
        policy.get("candidate_artifact_policy"),
        "candidate_artifact_policy",
    )

    if (
        artifact_policy.get("candidate_purpose")
        != "family_analysis_input"
    ):
        raise ValueError(
            "candidate_artifact_policy."
            "candidate_purpose must be "
            "family_analysis_input"
        )

    if (
        artifact_policy.get("candidate_status")
        != "retrieved_candidate"
    ):
        raise ValueError(
            "candidate_artifact_policy."
            "candidate_status must be "
            "retrieved_candidate"
        )

    if (
        artifact_policy.get(
            "candidate_objects_are_immutable"
        )
        is not True
    ):
        raise ValueError(
            "Candidate objects must be immutable"
        )

    if (
        artifact_policy.get(
            "candidate_objects_store_llm_analysis_status"
        )
        is not False
    ):
        raise ValueError(
            "Candidate objects must not store "
            "LLM analysis status"
        )

    grouping_policy = require_dict(
        policy.get("grouping_policy"),
        "grouping_policy",
    )

    if (
        grouping_policy.get("grouping_method")
        != "connected_components"
    ):
        raise ValueError(
            "Only connected_components is "
            "supported in v2"
        )

    identifier_policy = require_dict(
        policy.get(
            "candidate_identifier_policy"
        ),
        "candidate_identifier_policy",
    )

    short_hash_length = int(
        identifier_policy["short_hash_length"]
    )

    if short_hash_length < 8:
        raise ValueError(
            "candidate_identifier_policy."
            "short_hash_length must be at least 8"
        )

    run_identifier_policy = require_dict(
        policy.get("run_identifier_policy"),
        "run_identifier_policy",
    )

    sequence_width = int(
        run_identifier_policy[
            "sequence_width"
        ]
    )

    if sequence_width < 1:
        raise ValueError(
            "run_identifier_policy."
            "sequence_width must be positive"
        )

    hashing_policy = require_dict(
        policy.get("hashing_policy"),
        "hashing_policy",
    )

    if (
        hashing_policy.get(
            "retrieval_policy_hash_mode"
        )
        != "canonical_json"
    ):
        raise ValueError(
            "retrieval_policy_hash_mode must be "
            "canonical_json"
        )

    if (
        hashing_policy.get(
            "candidate_group_hash_mode"
        )
        != "explicit_semantic_allowlist"
    ):
        raise ValueError(
            "candidate_group_hash_mode must be "
            "explicit_semantic_allowlist"
        )

    tracking_policy = require_dict(
        policy.get(
            "candidate_run_tracking_policy"
        ),
        "candidate_run_tracking_policy",
    )

    if tracking_policy.get("enabled") is not True:
        raise ValueError(
            "Candidate Run tracking must be enabled"
        )

    allowed_statuses = set(
        require_list(
            tracking_policy.get(
                "allowed_current_candidate_change_statuses"
            ),
            (
                "candidate_run_tracking_policy."
                "allowed_current_candidate_change_statuses"
            ),
        )
    )

    recommended_statuses = set(
        require_list(
            tracking_policy.get(
                "analysis_recommended_for_statuses"
            ),
            (
                "candidate_run_tracking_policy."
                "analysis_recommended_for_statuses"
            ),
        )
    )

    not_recommended_statuses = set(
        require_list(
            tracking_policy.get(
                "analysis_not_recommended_for_statuses"
            ),
            (
                "candidate_run_tracking_policy."
                "analysis_not_recommended_for_statuses"
            ),
        )
    )

    if (
        recommended_statuses
        & not_recommended_statuses
    ):
        raise ValueError(
            "Analysis-recommended and "
            "not-recommended statuses overlap"
        )

    if (
        recommended_statuses
        | not_recommended_statuses
    ) != allowed_statuses:
        raise ValueError(
            "Analysis recommendation statuses "
            "must partition all allowed statuses"
        )

    if (
        tracking_policy.get(
            "first_run_policy_compatibility_value"
        )
        is not None
    ):
        raise ValueError(
            "First-run Policy compatibility "
            "must be null"
        )

    output_policy = require_dict(
        policy.get("output_policy"),
        "output_policy",
    )

    safe_components = {
        "candidate_object_subdirectory": (
            output_policy.get(
                "candidate_object_subdirectory"
            )
        ),
        "candidate_run_subdirectory": (
            output_policy.get(
                "candidate_run_subdirectory"
            )
        ),
        "run_index_filename": (
            run_identifier_policy.get(
                "run_index_filename"
            )
        ),
    }

    for label, value in safe_components.items():
        value = require_string(
            value,
            label,
        )

        if (
            "/" in value
            or "\\" in value
            or value in {".", ".."}
        ):
            raise ValueError(
                f"Unsafe path component "
                f"{label}: {value!r}"
            )

def direct_source_report_ids(
    pattern: dict[str, Any],
    policy: dict[str, Any],
) -> list[str]:
    provenance = require_dict(
        pattern.get("provenance"),
        "provenance",
    )

    supporting_reports = require_list(
        provenance.get("supporting_reports"),
        "provenance.supporting_reports",
    )

    report_ids: list[str] = []

    for index, report in enumerate(
        supporting_reports
    ):
        report = require_dict(
            report,
            (
                "provenance.supporting_reports"
                f"[{index}]"
            ),
        )

        if report.get("relation") != "direct_evidence":
            continue

        report_id = require_string(
            report.get("report_id"),
            (
                "provenance.supporting_reports"
                f"[{index}].report_id"
            ),
        )

        report_ids.append(report_id)

    report_ids = sorted(set(report_ids))

    require_direct = policy[
        "input_requirements"
    ]["require_direct_source_report"]

    if require_direct and not report_ids:
        raise ValueError(
            "Pattern has no direct supporting Report"
        )

    return report_ids


def extract_pattern_record(
    path: Path,
    policy: dict[str, Any],
    framework_filter: str | None,
) -> PatternRecord:
    assert_within_exp006(path)

    pattern = load_json(path)
    require_dict(pattern, str(path))

    input_requirements = policy[
        "input_requirements"
    ]

    required_schema_version = str(
        input_requirements["schema_version"]
    )

    schema_version = str(
        pattern.get("schema_version", "")
    )

    if schema_version != required_schema_version:
        raise PatternSkipped(
            f"schema_version={schema_version!r}"
        )

    metadata = require_dict(
        pattern.get("metadata"),
        "metadata",
    )

    pattern_level = require_string(
        metadata.get("pattern_level"),
        "metadata.pattern_level",
    )

    required_level = input_requirements[
        "pattern_level"
    ]

    if pattern_level != required_level:
        raise PatternSkipped(
            f"pattern_level={pattern_level!r}"
        )

    pattern_id = require_string(
        metadata.get("pattern_id"),
        "metadata.pattern_id",
    )

    derivation = require_dict(
        pattern.get("derivation_information"),
        "derivation_information",
    )

    validation_status = require_string(
        derivation.get("validation_status"),
        (
            "derivation_information."
            "validation_status"
        ),
    )

    allowed_statuses = set(
        input_requirements[
            "allowed_validation_statuses"
        ]
    )

    if validation_status not in allowed_statuses:
        raise PatternSkipped(
            f"validation_status={validation_status!r}"
        )

    scope = require_dict(
        pattern.get("scope"),
        "scope",
    )

    framework = require_string(
        scope.get("framework"),
        "scope.framework",
    )

    if (
        framework_filter is not None
        and framework.lower()
        != framework_filter.lower()
    ):
        raise PatternSkipped(
            f"framework={framework!r}"
        )

    primary_api = require_string(
        scope.get("primary_api"),
        "scope.primary_api",
    )

    source_report_ids = direct_source_report_ids(
        pattern,
        policy,
    )

    classification = require_dict(
        pattern.get("defect_classification"),
        "defect_classification",
    )

    primary_defect_class = normalize_scalar(
        classification.get(
            "primary_defect_class"
        )
    )

    secondary_defect_classes = normalize_array(
        classification.get(
            "secondary_defect_classes",
            [],
        ),
        (
            "defect_classification."
            "secondary_defect_classes"
        ),
        policy,
    )

    risk_dimensions = normalize_array(
        classification.get(
            "risk_dimensions",
            [],
        ),
        "defect_classification.risk_dimensions",
        policy,
    )

    transferability = require_dict(
        pattern.get(
            "transferability_hypothesis"
        ),
        "transferability_hypothesis",
    )

    candidate_family_tags = normalize_array(
        transferability.get(
            "candidate_family_tags",
            [],
        ),
        (
            "transferability_hypothesis."
            "candidate_family_tags"
        ),
        policy,
    )

    transferability_evidence_status = (
        require_string(
            transferability.get(
                "evidence_status"
            ),
            (
                "transferability_hypothesis."
                "evidence_status"
            ),
        )
    )

    transferability_confidence = (
        require_string(
            transferability.get("confidence"),
            (
                "transferability_hypothesis."
                "confidence"
            ),
        )
    )

    if transferability_confidence not in {
        "high",
        "medium",
        "low",
    }:
        raise ValueError(
            "transferability_hypothesis."
            "confidence must be high, medium, "
            "or low"
        )

    trigger_signature = require_dict(
        pattern.get("trigger_signature"),
        "trigger_signature",
    )

    conditions = require_list(
        trigger_signature.get("conditions"),
        "trigger_signature.conditions",
    )

    trigger_dimensions: list[str] = []

    for index, condition in enumerate(conditions):
        condition = require_dict(
            condition,
            (
                "trigger_signature.conditions"
                f"[{index}]"
            ),
        )

        dimension = normalize_scalar(
            condition.get("dimension")
        )

        if meaningful_scalar(dimension):
            trigger_dimensions.append(dimension)

    trigger_dimensions = sorted(
        set(trigger_dimensions)
    )

    mechanism = require_dict(
        pattern.get("defect_mechanism"),
        "defect_mechanism",
    )

    hypotheses = require_list(
        mechanism.get("hypotheses"),
        "defect_mechanism.hypotheses",
    )

    mechanism_layers: list[str] = []

    for index, hypothesis in enumerate(
        hypotheses
    ):
        hypothesis = require_dict(
            hypothesis,
            (
                "defect_mechanism.hypotheses"
                f"[{index}]"
            ),
        )

        layer = normalize_scalar(
            hypothesis.get("layer")
        )

        if meaningful_scalar(layer):
            mechanism_layers.append(layer)

    mechanism_layers = sorted(
        set(mechanism_layers)
    )

    observed_failure = require_dict(
        pattern.get("observed_failure"),
        "observed_failure",
    )

    failure_type = normalize_scalar(
        observed_failure.get("failure_type")
    )

    failure_types = (
        [failure_type]
        if meaningful_scalar(failure_type)
        else []
    )

    historical_oracle = (
        observed_failure.get(
            "historical_oracle"
        )
    )

    historical_oracle_kinds: list[str] = []

    if historical_oracle is not None:
        historical_oracle = require_dict(
            historical_oracle,
            (
                "observed_failure."
                "historical_oracle"
            ),
        )

        oracle_kind = normalize_scalar(
            historical_oracle.get("kind")
        )

        if meaningful_scalar(oracle_kind):
            historical_oracle_kinds.append(
                oracle_kind
            )

    pattern_hash = canonical_json_hash(pattern)

    relative_path = (
        path.resolve()
        .relative_to(EXP006_DIR.resolve())
        .as_posix()
    )

    return PatternRecord(
        path=path.resolve(),
        pattern_relpath=relative_path,
        pattern_id=pattern_id,
        pattern_hash=pattern_hash,
        framework=framework,
        primary_api=primary_api,
        source_report_ids=tuple(
            source_report_ids
        ),
        validation_status=validation_status,
        retrieval_signature={
            "primary_defect_class": (
                primary_defect_class
            ),
            "secondary_defect_classes": (
                secondary_defect_classes
            ),
            "risk_dimensions": (
                risk_dimensions
            ),
            "candidate_family_tags": (
                candidate_family_tags
            ),
            "trigger_dimensions": (
                trigger_dimensions
            ),
            "mechanism_layers": (
                mechanism_layers
            ),
            "failure_types": failure_types,
            "historical_oracle_kinds": (
                historical_oracle_kinds
            ),
        },
        signal_provenance={
            "transferability_evidence_status": (
                transferability_evidence_status
            ),
            "transferability_confidence": (
                transferability_confidence
            ),
        },
    )


def is_legacy_path(path: Path) -> bool:
    return any(
        part.lower() == "legacy"
        for part in path.parts
    )


def scan_patterns(
    pattern_root: Path,
    policy: dict[str, Any],
    framework_filter: str | None,
) -> tuple[
    list[PatternRecord],
    list[str],
    list[str],
]:
    if not pattern_root.is_dir():
        raise FileNotFoundError(
            "Pattern root does not exist: "
            f"{pattern_root}"
        )

    records: list[PatternRecord] = []
    skipped: list[str] = []
    invalid: list[str] = []

    pattern_paths = sorted(
        path
        for path in pattern_root.rglob("*.json")
        if not is_legacy_path(path)
    )

    for path in pattern_paths:
        try:
            record = extract_pattern_record(
                path,
                policy,
                framework_filter,
            )

            records.append(record)

        except PatternSkipped as error:
            skipped.append(
                f"{path}: {error}"
            )

        except (
            OSError,
            json.JSONDecodeError,
            ValueError,
        ) as error:
            invalid.append(
                f"{path}: {error}"
            )

    records.sort(
        key=lambda item: item.pattern_id
    )

    duplicate_ids: dict[
        str,
        list[Path],
    ] = {}

    for record in records:
        duplicate_ids.setdefault(
            record.pattern_id,
            [],
        ).append(record.path)

    for pattern_id, paths in sorted(
        duplicate_ids.items()
    ):
        if len(paths) <= 1:
            continue

        invalid.append(
            "Duplicate Pattern ID "
            f"{pattern_id}: "
            + ", ".join(
                str(path)
                for path in paths
            )
        )

    return records, skipped, invalid


def flat_signal_values(
    record: PatternRecord,
) -> dict[str, Any]:
    values = dict(
        record.retrieval_signature
    )

    values.update(
        record.signal_provenance
    )

    return values


def as_set(value: Any) -> set[str]:
    if isinstance(value, list):
        return {
            item
            for item in value
            if meaningful_scalar(item)
        }

    if meaningful_scalar(value):
        return {value.strip()}

    return set()


def shared_values(
    left_value: Any,
    right_value: Any,
) -> list[str]:
    return sorted(
        as_set(left_value)
        & as_set(right_value)
    )


def compare_requirement(
    requirement: dict[str, Any],
    left_values: dict[str, Any],
    right_values: dict[str, Any],
) -> bool:
    field = require_string(
        requirement.get("field"),
        "requirement.field",
    )

    comparison = require_string(
        requirement.get("comparison"),
        "requirement.comparison",
    )

    left = left_values.get(field)
    right = right_values.get(field)

    if comparison == "exact_equal_non_null":
        return (
            meaningful_scalar(left)
            and meaningful_scalar(right)
            and left == right
        )

    if comparison == "intersection_non_empty":
        return bool(
            as_set(left) & as_set(right)
        )

    if comparison == "both_values_not_equal":
        disallowed_value = (
            requirement.get("value")
        )

        return (
            left is not None
            and right is not None
            and left != disallowed_value
            and right != disallowed_value
        )

    if comparison == "both_values_in":
        allowed_values = set(
            requirement.get("values", [])
        )

        return (
            left in allowed_values
            and right in allowed_values
        )

    raise ValueError(
        f"Unsupported comparison: {comparison}"
    )


def evaluate_strong_signals(
    left: PatternRecord,
    right: PatternRecord,
    policy: dict[str, Any],
) -> list[str]:
    left_values = flat_signal_values(left)
    right_values = flat_signal_values(right)

    matched: list[str] = []

    for rule in policy[
        "strong_signal_rules"
    ]:
        requirements = rule.get(
            "requirements",
            {},
        )

        all_requirements = requirements.get(
            "all",
            [],
        )

        any_requirements = requirements.get(
            "any",
            [],
        )

        all_passed = all(
            compare_requirement(
                requirement,
                left_values,
                right_values,
            )
            for requirement
            in all_requirements
        )

        any_passed = (
            True
            if not any_requirements
            else any(
                compare_requirement(
                    requirement,
                    left_values,
                    right_values,
                )
                for requirement
                in any_requirements
            )
        )

        if all_passed and any_passed:
            matched.append(rule["name"])

    return sorted(matched)


def evaluate_weak_signals(
    left: PatternRecord,
    right: PatternRecord,
    policy: dict[str, Any],
) -> tuple[list[str], list[str]]:
    left_values = flat_signal_values(left)
    right_values = flat_signal_values(right)

    matched_signals: list[str] = []
    matched_categories: set[str] = set()

    for rule in policy[
        "weak_signal_rules"
    ]:
        if compare_requirement(
            rule,
            left_values,
            right_values,
        ):
            matched_signals.append(
                rule["name"]
            )

            matched_categories.add(
                rule["category"]
            )

    return (
        sorted(matched_signals),
        sorted(matched_categories),
    )


def jaccard(
    left_value: Any,
    right_value: Any,
    policy: dict[str, Any],
) -> float | None:
    left = as_set(left_value)
    right = as_set(right_value)

    if not left and not right:
        return policy[
            "normalization"
        ]["jaccard_both_empty_value"]

    union = left | right

    if not union:
        return None

    precision = int(
        policy[
            "normalization"
        ]["jaccard_precision"]
    )

    return round(
        len(left & right) / len(union),
        precision,
    )


def candidate_link_passes(
    strong_signals: list[str],
    weak_signals: list[str],
    matched_categories: list[str],
    policy: dict[str, Any],
) -> bool:
    link_policy = policy[
        "candidate_link_policy"
    ]

    for condition in link_policy[
        "pass_if_any_condition_matches"
    ]:
        condition_name = condition[
            "condition_name"
        ]

        if condition_name == "strong_signal_path":
            minimum = int(
                condition[
                    "minimum_strong_signal_count"
                ]
            )

            if len(strong_signals) >= minimum:
                return True

        elif (
            condition_name
            == "weak_signal_fallback"
        ):
            minimum_signals = int(
                condition[
                    "minimum_weak_signal_count"
                ]
            )

            minimum_categories = int(
                condition[
                    "minimum_distinct_signal_category_count"
                ]
            )

            required_categories = set(
                condition[
                    "require_at_least_one_category_from"
                ]
            )

            category_set = set(
                matched_categories
            )

            if (
                len(weak_signals)
                >= minimum_signals
                and len(category_set)
                >= minimum_categories
                and bool(
                    category_set
                    & required_categories
                )
            ):
                return True

        else:
            raise ValueError(
                "Unsupported candidate-link "
                f"condition: {condition_name}"
            )

    return False


def build_pairwise_link(
    left: PatternRecord,
    right: PatternRecord,
    policy: dict[str, Any],
) -> dict[str, Any]:
    if left.pattern_id > right.pattern_id:
        left, right = right, left

    left_signature = (
        left.retrieval_signature
    )

    right_signature = (
        right.retrieval_signature
    )

    strong_signals = (
        evaluate_strong_signals(
            left,
            right,
            policy,
        )
    )

    weak_signals, matched_categories = (
        evaluate_weak_signals(
            left,
            right,
            policy,
        )
    )

    link_passed = candidate_link_passes(
        strong_signals,
        weak_signals,
        matched_categories,
        policy,
    )

    primary_left = left_signature[
        "primary_defect_class"
    ]

    primary_right = right_signature[
        "primary_defect_class"
    ]

    primary_match = (
        meaningful_scalar(primary_left)
        and meaningful_scalar(primary_right)
        and primary_left == primary_right
    )

    return {
        "left_pattern_id": left.pattern_id,
        "right_pattern_id": right.pattern_id,

        "exact_matches": {
            "primary_defect_class_match": (
                primary_match
            ),
            "shared_secondary_defect_classes": (
                shared_values(
                    left_signature[
                        "secondary_defect_classes"
                    ],
                    right_signature[
                        "secondary_defect_classes"
                    ],
                )
            ),
            "shared_risk_dimensions": (
                shared_values(
                    left_signature[
                        "risk_dimensions"
                    ],
                    right_signature[
                        "risk_dimensions"
                    ],
                )
            ),
            "shared_candidate_family_tags": (
                shared_values(
                    left_signature[
                        "candidate_family_tags"
                    ],
                    right_signature[
                        "candidate_family_tags"
                    ],
                )
            ),
            "shared_trigger_dimensions": (
                shared_values(
                    left_signature[
                        "trigger_dimensions"
                    ],
                    right_signature[
                        "trigger_dimensions"
                    ],
                )
            ),
            "shared_mechanism_layers": (
                shared_values(
                    left_signature[
                        "mechanism_layers"
                    ],
                    right_signature[
                        "mechanism_layers"
                    ],
                )
            ),
            "shared_failure_types": (
                shared_values(
                    left_signature[
                        "failure_types"
                    ],
                    right_signature[
                        "failure_types"
                    ],
                )
            ),
            "shared_historical_oracle_kinds": (
                shared_values(
                    left_signature[
                        "historical_oracle_kinds"
                    ],
                    right_signature[
                        "historical_oracle_kinds"
                    ],
                )
            ),
        },

        "set_overlap_metrics": {
            "secondary_defect_class_jaccard": (
                jaccard(
                    left_signature[
                        "secondary_defect_classes"
                    ],
                    right_signature[
                        "secondary_defect_classes"
                    ],
                    policy,
                )
            ),
            "risk_dimension_jaccard": (
                jaccard(
                    left_signature[
                        "risk_dimensions"
                    ],
                    right_signature[
                        "risk_dimensions"
                    ],
                    policy,
                )
            ),
            "candidate_family_tag_jaccard": (
                jaccard(
                    left_signature[
                        "candidate_family_tags"
                    ],
                    right_signature[
                        "candidate_family_tags"
                    ],
                    policy,
                )
            ),
            "trigger_dimension_jaccard": (
                jaccard(
                    left_signature[
                        "trigger_dimensions"
                    ],
                    right_signature[
                        "trigger_dimensions"
                    ],
                    policy,
                )
            ),
            "mechanism_layer_jaccard": (
                jaccard(
                    left_signature[
                        "mechanism_layers"
                    ],
                    right_signature[
                        "mechanism_layers"
                    ],
                    policy,
                )
            ),
            "failure_type_jaccard": (
                jaccard(
                    left_signature[
                        "failure_types"
                    ],
                    right_signature[
                        "failure_types"
                    ],
                    policy,
                )
            ),
            "historical_oracle_kind_jaccard": (
                jaccard(
                    left_signature[
                        "historical_oracle_kinds"
                    ],
                    right_signature[
                        "historical_oracle_kinds"
                    ],
                    policy,
                )
            ),
        },

        "signal_classification": {
            "strong_signals": strong_signals,
            "weak_signals": weak_signals,
            "matched_signal_categories": (
                matched_categories
            ),
            "strong_signal_count": len(
                strong_signals
            ),
            "weak_signal_count": len(
                weak_signals
            ),
        },

        "candidate_link_passed": (
            link_passed
        ),
    }


def pair_key(
    left_pattern_id: str,
    right_pattern_id: str,
) -> tuple[str, str]:
    return tuple(
        sorted(
            (
                left_pattern_id,
                right_pattern_id,
            )
        )
    )


def connected_components(
    node_ids: list[str],
    adjacency: dict[str, set[str]],
) -> list[list[str]]:
    remaining = set(node_ids)
    components: list[list[str]] = []

    while remaining:
        start = min(remaining)
        stack = [start]
        component: set[str] = set()

        while stack:
            node = stack.pop()

            if node in component:
                continue

            component.add(node)
            remaining.discard(node)

            for neighbor in sorted(
                adjacency.get(node, set()),
                reverse=True,
            ):
                if neighbor not in component:
                    stack.append(neighbor)

        components.append(
            sorted(component)
        )

    components.sort(
        key=lambda component: component[0]
    )

    return components


def build_candidate_components(
    records: list[PatternRecord],
    pair_links: dict[
        tuple[str, str],
        dict[str, Any],
    ],
    policy: dict[str, Any],
) -> list[list[str]]:
    node_ids = [
        record.pattern_id
        for record in records
    ]

    adjacency = {
        pattern_id: set()
        for pattern_id in node_ids
    }

    for key, link in pair_links.items():
        if not link[
            "candidate_link_passed"
        ]:
            continue

        left_id, right_id = key

        adjacency[left_id].add(right_id)
        adjacency[right_id].add(left_id)

    components = connected_components(
        node_ids,
        adjacency,
    )

    minimum_size = int(
        policy[
            "grouping_policy"
        ]["minimum_component_size"]
    )

    return [
        component
        for component in components
        if len(component) >= minimum_size
    ]


def intersect_member_field(
    records: list[PatternRecord],
    field_name: str,
) -> list[str]:
    member_sets = [
        as_set(
            record.retrieval_signature[
                field_name
            ]
        )
        for record in records
    ]

    if not member_sets:
        return []

    return sorted(
        set.intersection(*member_sets)
    )


def shared_primary_defect_class(
    records: list[PatternRecord],
) -> str | None:
    values = [
        record.retrieval_signature[
            "primary_defect_class"
        ]
        for record in records
    ]

    if not values:
        return None

    first_value = values[0]

    if not meaningful_scalar(first_value):
        return None

    if all(
        value == first_value
        for value in values
    ):
        return first_value

    return None


def build_eligibility_summary(
    records: list[PatternRecord],
    policy: dict[str, Any],
) -> dict[str, Any]:
    eligibility_policy = policy[
        "eligibility_policy"
    ]

    pattern_count = len(records)

    distinct_api_count = len(
        {
            record.primary_api
            for record in records
        }
    )

    independent_report_count = len(
        {
            report_id
            for record in records
            for report_id
            in record.source_report_ids
        }
    )

    frameworks = {
        record.framework
        for record in records
    }

    all_members_api_specific = True
    all_members_valid_v2 = True
    same_framework = len(frameworks) == 1

    minimum_pattern_count_met = (
        pattern_count
        >= int(
            eligibility_policy[
                "minimum_pattern_count"
            ]
        )
    )

    minimum_distinct_api_count_met = (
        distinct_api_count
        >= int(
            eligibility_policy[
                "minimum_distinct_api_count"
            ]
        )
    )

    minimum_independent_report_count_met = (
        independent_report_count
        >= int(
            eligibility_policy[
                "minimum_independent_report_count"
            ]
        )
    )

    minimum_candidate_conditions_met = all(
        (
            minimum_pattern_count_met,
            minimum_distinct_api_count_met,
            minimum_independent_report_count_met,
            all_members_api_specific,
            all_members_valid_v2,
            same_framework,
        )
    )

    return {
        "pattern_count": pattern_count,
        "distinct_api_count": (
            distinct_api_count
        ),
        "independent_report_count": (
            independent_report_count
        ),
        "all_members_api_specific": (
            all_members_api_specific
        ),
        "all_members_valid_v2": (
            all_members_valid_v2
        ),
        "same_framework": same_framework,
        "minimum_pattern_count_met": (
            minimum_pattern_count_met
        ),
        "minimum_distinct_api_count_met": (
            minimum_distinct_api_count_met
        ),
        "minimum_independent_report_count_met": (
            minimum_independent_report_count_met
        ),
        "minimum_candidate_conditions_met": (
            minimum_candidate_conditions_met
        ),
    }


def build_group_retrieval_signals(
    records: list[PatternRecord],
) -> dict[str, Any]:
    return {
        "shared_primary_defect_class": (
            shared_primary_defect_class(records)
        ),
        "shared_secondary_defect_classes": (
            intersect_member_field(
                records,
                "secondary_defect_classes",
            )
        ),
        "shared_risk_dimensions": (
            intersect_member_field(
                records,
                "risk_dimensions",
            )
        ),
        "shared_candidate_family_tags": (
            intersect_member_field(
                records,
                "candidate_family_tags",
            )
        ),
        "shared_trigger_dimensions": (
            intersect_member_field(
                records,
                "trigger_dimensions",
            )
        ),
        "shared_mechanism_layers": (
            intersect_member_field(
                records,
                "mechanism_layers",
            )
        ),
        "shared_failure_types": (
            intersect_member_field(
                records,
                "failure_types",
            )
        ),
        "shared_historical_oracle_kinds": (
            intersect_member_field(
                records,
                "historical_oracle_kinds",
            )
        ),
    }


def build_strong_subgroups(
    component_ids: list[str],
    internal_links: list[dict[str, Any]],
    policy: dict[str, Any],
) -> list[list[str]]:
    subgroup_policy = policy[
        "group_consistency_policy"
    ]["subgroup_rule"]

    if not subgroup_policy["enabled"]:
        return []

    adjacency = {
        pattern_id: set()
        for pattern_id in component_ids
    }

    for link in internal_links:
        strong_signals = link[
            "signal_classification"
        ]["strong_signals"]

        if not strong_signals:
            continue

        left_id = link["left_pattern_id"]
        right_id = link["right_pattern_id"]

        adjacency[left_id].add(right_id)
        adjacency[right_id].add(left_id)

    subgroups = connected_components(
        component_ids,
        adjacency,
    )

    minimum_size = int(
        subgroup_policy[
            "minimum_subgroup_size"
        ]
    )

    subgroups = [
        subgroup
        for subgroup in subgroups
        if len(subgroup) >= minimum_size
    ]

    if subgroup_policy[
        "remove_full_group_subgroup"
    ]:
        full_group = sorted(component_ids)

        subgroups = [
            subgroup
            for subgroup in subgroups
            if subgroup != full_group
        ]

    if subgroup_policy[
        "remove_duplicate_subgroups"
    ]:
        unique_subgroups = {
            tuple(subgroup)
            for subgroup in subgroups
        }

        subgroups = [
            list(subgroup)
            for subgroup in sorted(
                unique_subgroups
            )
        ]

    return subgroups


def build_group_consistency(
    records: list[PatternRecord],
    internal_links: list[dict[str, Any]],
    policy: dict[str, Any],
) -> dict[str, Any]:
    pattern_ids = [
        record.pattern_id
        for record in records
    ]

    pairwise_link_count = len(
        internal_links
    )

    passed_links = [
        link
        for link in internal_links
        if link["candidate_link_passed"]
    ]

    failed_links = [
        link
        for link in internal_links
        if not link["candidate_link_passed"]
    ]

    strong_signal_sets = [
        set(
            link[
                "signal_classification"
            ]["strong_signals"]
        )
        for link in internal_links
    ]

    all_members_share_strong_signal = (
        bool(strong_signal_sets)
        and all(strong_signal_sets)
        and bool(
            set.intersection(
                *strong_signal_sets
            )
        )
    )

    chain_rule = policy[
        "group_consistency_policy"
    ]["chain_drift_rule"]

    chain_drift_flag = (
        chain_rule["enabled"]
        and len(failed_links)
        > int(
            chain_rule[
                "flag_when_failed_internal_pair_count_greater_than"
            ]
        )
    )

    outlier_policy = policy[
        "group_consistency_policy"
    ]["outlier_rule"]

    member_link_coverage: list[
        dict[str, Any]
    ] = []

    outlier_ids: list[str] = []

    possible_link_count = max(
        len(records) - 1,
        0,
    )

    precision = int(
        policy[
            "normalization"
        ]["jaccard_precision"]
    )

    for pattern_id in pattern_ids:
        passed_link_count = sum(
            1
            for link in passed_links
            if pattern_id
            in {
                link["left_pattern_id"],
                link["right_pattern_id"],
            }
        )

        link_coverage = (
            round(
                passed_link_count
                / possible_link_count,
                precision,
            )
            if possible_link_count
            else 0.0
        )

        flagged = (
            outlier_policy["enabled"]
            and len(records)
            >= int(
                outlier_policy[
                    "minimum_group_size"
                ]
            )
            and link_coverage
            < float(
                outlier_policy[
                    "link_coverage_threshold"
                ]
            )
        )

        if flagged:
            outlier_ids.append(pattern_id)

        member_link_coverage.append(
            {
                "pattern_id": pattern_id,
                "passed_link_count": (
                    passed_link_count
                ),
                "possible_link_count": (
                    possible_link_count
                ),
                "link_coverage": (
                    link_coverage
                ),
                "rule_flagged_outlier": (
                    flagged
                ),
            }
        )

    subgroups = build_strong_subgroups(
        pattern_ids,
        internal_links,
        policy,
    )

    return {
        "grouping_method": policy[
            "grouping_policy"
        ]["grouping_method"],
        "all_members_share_strong_signal": (
            all_members_share_strong_signal
        ),
        "pairwise_link_count": (
            pairwise_link_count
        ),
        "passed_pairwise_link_count": (
            len(passed_links)
        ),
        "failed_pairwise_link_count": (
            len(failed_links)
        ),
        "chain_drift_flag": (
            chain_drift_flag
        ),
        "member_link_coverage": (
            member_link_coverage
        ),
        "rule_flagged_outlier_pattern_ids": (
            sorted(outlier_ids)
        ),
        "rule_detected_subgroups": (
            subgroups
        ),
    }


def build_retrieval_warnings(
    records: list[PatternRecord],
    eligibility: dict[str, Any],
    group_signals: dict[str, Any],
    consistency: dict[str, Any],
    policy: dict[str, Any],
) -> list[str]:
    allowed_warnings = set(
        policy[
            "warning_policy"
        ]["allowed_warning_values"]
    )

    warnings: set[str] = set()

    def add_warning(name: str) -> None:
        if name not in allowed_warnings:
            raise ValueError(
                "Unsupported warning name: "
                f"{name}"
            )

        warnings.add(name)

    if (
        eligibility[
            "independent_report_count"
        ]
        < eligibility["pattern_count"]
    ):
        add_warning(
            "duplicate_report_source"
        )

    if consistency["chain_drift_flag"]:
        add_warning("chain_drift")

    if not consistency[
        "all_members_share_strong_signal"
    ]:
        add_warning("weak_shared_signal")

    if consistency[
        "rule_flagged_outlier_pattern_ids"
    ]:
        add_warning(
            "rule_flagged_outlier"
        )

    large_threshold = int(
        policy[
            "grouping_policy"
        ]["candidate_group_large_threshold"]
    )

    if len(records) > large_threshold:
        add_warning(
            "candidate_group_too_large"
        )

    if any(
        record.retrieval_signature[
            "candidate_family_tags"
        ]
        and record.signal_provenance[
            "transferability_confidence"
        ]
        == "low"
        for record in records
    ):
        add_warning(
            "low_confidence_source_pattern"
        )

    if (
        group_signals[
            "shared_candidate_family_tags"
        ]
        and any(
            record.signal_provenance[
                "transferability_evidence_status"
            ]
            == "unknown"
            for record in records
        )
    ):
        add_warning(
            "missing_transferability_evidence"
        )

    return sorted(warnings)


def framework_prefix(
    framework: str,
    policy: dict[str, Any],
) -> str:
    identifier_policy = policy[
        "candidate_identifier_policy"
    ]

    prefix_map = identifier_policy[
        "prefix_by_framework"
    ]

    normalized_framework = slugify(
        framework
    )

    if normalized_framework in prefix_map:
        return prefix_map[
            normalized_framework
        ]

    fallback = identifier_policy[
        "fallback_framework_prefix"
    ]

    return fallback.format(
        normalized_framework=(
            normalized_framework
        )
    )


def run_prefix(
    framework: str,
    policy: dict[str, Any],
) -> str:
    identifier_policy = policy[
        "run_identifier_policy"
    ]

    prefix_map = identifier_policy[
        "prefix_by_framework"
    ]

    normalized_framework = slugify(
        framework
    )

    if normalized_framework in prefix_map:
        return prefix_map[
            normalized_framework
        ]

    fallback = identifier_policy[
        "fallback_framework_prefix"
    ]

    return fallback.format(
        normalized_framework=(
            normalized_framework
        )
    )


def build_candidate_group_id(
    records: list[PatternRecord],
    framework: str,
    policy: dict[str, Any],
    policy_hash: str,
) -> str:
    identifier_policy = policy[
        "candidate_identifier_policy"
    ]

    identity_payload = {
        "sorted_member_pattern_ids": (
            sorted(
                record.pattern_id
                for record in records
            )
        ),
        "sorted_member_pattern_hashes": (
            sorted(
                record.pattern_hash
                for record in records
            )
        ),
        "retrieval_policy_version": (
            policy["policy_version"]
        ),
        "retrieval_policy_hash": (
            policy_hash
        ),
    }

    digest = hashlib.sha256(
        canonical_json_bytes(
            identity_payload
        )
    ).hexdigest()

    short_length = int(
        identifier_policy[
            "short_hash_length"
        ]
    )

    return (
        framework_prefix(
            framework,
            policy,
        )
        + "_"
        + digest[:short_length]
    )


def source_corpus_hash(
    records: list[PatternRecord],
) -> str:
    inventory = [
        {
            "pattern_id": (
                record.pattern_id
            ),
            "pattern_hash": (
                record.pattern_hash
            ),
        }
        for record in sorted(
            records,
            key=lambda item: item.pattern_id,
        )
    ]

    return canonical_json_hash(inventory)


def manifest_member(
    record: PatternRecord,
) -> dict[str, Any]:
    return {
        "pattern_id": record.pattern_id,
        "pattern_hash": record.pattern_hash,
        "pattern_relpath": (
            record.pattern_relpath
        ),
        "primary_api": record.primary_api,
        "source_report_ids": list(
            record.source_report_ids
        ),
        "validation_status": (
            record.validation_status
        ),
        "retrieval_signature": (
            record.retrieval_signature
        ),
        "signal_provenance": (
            record.signal_provenance
        ),
    }


def semantic_manifest_member(
    member: dict[str, Any],
) -> dict[str, Any]:
    return {
        "pattern_id": member["pattern_id"],
        "pattern_hash": (
            member["pattern_hash"]
        ),
        "primary_api": (
            member["primary_api"]
        ),
        "source_report_ids": (
            member["source_report_ids"]
        ),
        "validation_status": (
            member["validation_status"]
        ),
        "retrieval_signature": (
            member["retrieval_signature"]
        ),
        "signal_provenance": (
            member["signal_provenance"]
        ),
    }


def candidate_semantic_payload(
    manifest: dict[str, Any],
) -> dict[str, Any]:
    generation_information = manifest[
        "generation_information"
    ]

    return {
        "manifest_version": (
            manifest["manifest_version"]
        ),
        "framework": (
            manifest["metadata"]["framework"]
        ),
        "retrieval_policy_version": (
            generation_information[
                "retrieval_policy_version"
            ]
        ),
        "retrieval_policy_hash": (
            generation_information[
                "retrieval_policy_hash"
            ]
        ),
        "members": [
            semantic_manifest_member(member)
            for member in manifest["members"]
        ],
        "eligibility_summary": (
            manifest["eligibility_summary"]
        ),
        "group_retrieval_signals": (
            manifest[
                "group_retrieval_signals"
            ]
        ),
        "pairwise_links": (
            manifest["pairwise_links"]
        ),
        "group_consistency": (
            manifest["group_consistency"]
        ),
        "retrieval_warnings": (
            manifest["retrieval_warnings"]
        ),
    }


def candidate_group_hash(
    manifest: dict[str, Any],
) -> str:
    return canonical_json_hash(
        candidate_semantic_payload(
            manifest
        )
    )


def build_manifest(
    component_ids: list[str],
    records_by_id: dict[
        str,
        PatternRecord,
    ],
    pair_links: dict[
        tuple[str, str],
        dict[str, Any],
    ],
    framework_corpus_hash: str,
    script_content_hash: str,
    policy: dict[str, Any],
    policy_hash: str,
) -> dict[str, Any] | None:
    records = [
        records_by_id[pattern_id]
        for pattern_id
        in sorted(component_ids)
    ]

    eligibility = (
        build_eligibility_summary(
            records,
            policy,
        )
    )

    if not eligibility[
        "minimum_candidate_conditions_met"
    ]:
        return None

    framework = records[0].framework

    internal_links = [
        pair_links[
            pair_key(
                left.pattern_id,
                right.pattern_id,
            )
        ]
        for left, right
        in combinations(records, 2)
    ]

    internal_links.sort(
        key=lambda link: (
            link["left_pattern_id"],
            link["right_pattern_id"],
        )
    )

    group_signals = (
        build_group_retrieval_signals(
            records
        )
    )

    consistency = (
        build_group_consistency(
            records,
            internal_links,
            policy,
        )
    )

    warnings = build_retrieval_warnings(
        records,
        eligibility,
        group_signals,
        consistency,
        policy,
    )

    candidate_group_id = (
        build_candidate_group_id(
            records,
            framework,
            policy,
            policy_hash,
        )
    )

    manifest = {
        "manifest_version": (
            policy["manifest_version"]
        ),

        "metadata": {
            "candidate_group_id": (
                candidate_group_id
            ),
            "candidate_group_hash": None,
            "candidate_purpose": (
                policy[
                    "candidate_artifact_policy"
                ]["candidate_purpose"]
            ),
            "candidate_status": (
                policy[
                    "candidate_artifact_policy"
                ]["candidate_status"]
            ),
            "framework": framework,
        },

        "generation_information": {
            "method": policy[
                "execution_boundary"
            ]["method"],
            "retrieval_policy_version": (
                policy["policy_version"]
            ),
            "retrieval_policy_hash": (
                policy_hash
            ),
            "script_version": (
                SCRIPT_VERSION
            ),
            "script_hash": (
                script_content_hash
            ),
            "source_corpus_hash": (
                framework_corpus_hash
            ),
            "generated_at": (
                utc_timestamp()
            ),
        },

        "members": [
            manifest_member(record)
            for record in records
        ],

        "eligibility_summary": (
            eligibility
        ),

        "group_retrieval_signals": (
            group_signals
        ),

        "pairwise_links": (
            internal_links
        ),

        "group_consistency": (
            consistency
        ),

        "existing_family_matches": [],

        "retrieval_warnings": (
            warnings
        ),
    }

    manifest["metadata"][
        "candidate_group_hash"
    ] = candidate_group_hash(manifest)

    return manifest


def group_records_by_framework(
    records: list[PatternRecord],
) -> dict[str, list[PatternRecord]]:
    grouped: dict[
        str,
        list[PatternRecord],
    ] = {}

    for record in records:
        grouped.setdefault(
            record.framework,
            [],
        ).append(record)

    for framework in grouped:
        grouped[framework] = sorted(
            grouped[framework],
            key=lambda item: item.pattern_id,
        )

    return grouped


def build_framework_manifests(
    records: list[PatternRecord],
    policy: dict[str, Any],
    policy_hash: str,
    script_content_hash: str,
) -> list[dict[str, Any]]:
    records_by_id = {
        record.pattern_id: record
        for record in records
    }

    pair_links: dict[
        tuple[str, str],
        dict[str, Any],
    ] = {}

    for left, right in combinations(
        records,
        2,
    ):
        key = pair_key(
            left.pattern_id,
            right.pattern_id,
        )

        pair_links[key] = (
            build_pairwise_link(
                left,
                right,
                policy,
            )
        )

    components = build_candidate_components(
        records,
        pair_links,
        policy,
    )

    corpus_hash = source_corpus_hash(
        records
    )

    manifests: list[dict[str, Any]] = []

    for component_ids in components:
        manifest = build_manifest(
            component_ids,
            records_by_id,
            pair_links,
            corpus_hash,
            script_content_hash,
            policy,
            policy_hash,
        )

        if manifest is not None:
            manifests.append(manifest)

    manifests.sort(
        key=lambda manifest: (
            manifest["metadata"][
                "candidate_group_id"
            ]
        )
    )

    return manifests


def resolve_path(
    value: str | None,
    default_path: Path,
) -> Path:
    if value is None:
        return default_path.resolve()

    path = Path(value).expanduser()

    if path.is_absolute():
        return path.resolve()

    return (
        EXP006_DIR
        / path
    ).resolve()


def candidate_object_path(
    manifest: dict[str, Any],
    output_root: Path,
    policy: dict[str, Any],
) -> Path:
    framework = manifest[
        "metadata"
    ]["framework"]

    framework_directory = slugify(
        framework
    )

    if not framework_directory:
        raise ValueError(
            "Invalid framework directory: "
            f"{framework!r}"
        )

    candidate_group_id = manifest[
        "metadata"
    ]["candidate_group_id"]

    filename_template = policy[
        "candidate_identifier_policy"
    ]["filename_template"]

    filename = filename_template.format(
        candidate_group_id=(
            candidate_group_id
        )
    )

    if (
        "/" in filename
        or "\\" in filename
        or filename in {".", ".."}
    ):
        raise ValueError(
            "Unsafe Candidate filename: "
            f"{filename}"
        )

    object_subdirectory = policy[
        "output_policy"
    ]["candidate_object_subdirectory"]

    return (
        output_root
        / object_subdirectory
        / framework_directory
        / filename
    )


def run_root(
    output_root: Path,
    framework: str,
    policy: dict[str, Any],
) -> Path:
    run_subdirectory = policy[
        "output_policy"
    ]["candidate_run_subdirectory"]

    return (
        output_root
        / run_subdirectory
        / slugify(framework)
    )


def run_index_path(
    output_root: Path,
    framework: str,
    run_id: str,
    policy: dict[str, Any],
) -> Path:
    identifier_policy = policy[
        "run_identifier_policy"
    ]

    run_directory_name = (
        identifier_policy[
            "run_directory_template"
        ].format(run_id=run_id)
    )

    index_filename = identifier_policy[
        "run_index_filename"
    ]

    for label, value in {
        "run directory": run_directory_name,
        "Run Index filename": index_filename,
    }.items():
        if (
            "/" in value
            or "\\" in value
            or value in {".", ".."}
        ):
            raise ValueError(
                f"Unsafe {label}: {value!r}"
            )

    return (
        run_root(
            output_root,
            framework,
            policy,
        )
        / run_directory_name
        / index_filename
    )


def existing_run_indices(
    output_root: Path,
    framework: str,
    policy: dict[str, Any],
) -> list[
    tuple[int, Path, dict[str, Any]]
]:
    root = run_root(
        output_root,
        framework,
        policy,
    )

    if not root.is_dir():
        return []

    identifier_policy = policy[
        "run_identifier_policy"
    ]

    index_filename = identifier_policy[
        "run_index_filename"
    ]

    sequence_width = int(
        identifier_policy[
            "sequence_width"
        ]
    )

    expected_prefix = run_prefix(
        framework,
        policy,
    )

    run_id_pattern = re.compile(
        rf"^{re.escape(expected_prefix)}_"
        rf"(\d{{{sequence_width}}})$"
    )

    results: list[
        tuple[int, Path, dict[str, Any]]
    ] = []

    for path in sorted(
        root.glob(
            f"*/{index_filename}"
        )
    ):
        index = load_json(path)
        require_dict(index, str(path))

        if (
            index.get("run_version")
            != policy["run_index_version"]
        ):
            raise ValueError(
                "Unsupported Run Index version "
                f"in {path}: "
                f"{index.get('run_version')!r}"
            )

        metadata = require_dict(
            index.get("metadata"),
            f"{path}.metadata",
        )

        run_id = require_string(
            metadata.get("run_id"),
            f"{path}.metadata.run_id",
        )

        match = run_id_pattern.fullmatch(
            run_id
        )

        if match is None:
            raise ValueError(
                "Invalid Candidate Run ID "
                f"in {path}: {run_id}"
            )

        if path.parent.name != run_id:
            raise ValueError(
                "Run directory name does not "
                f"match Run ID in {path}"
            )

        declared_framework = (
            require_string(
                metadata.get("framework"),
                f"{path}.metadata.framework",
            )
        )

        if (
            declared_framework.lower()
            != framework.lower()
        ):
            raise ValueError(
                "Run Index framework mismatch "
                f"in {path}"
            )

        results.append(
            (
                int(match.group(1)),
                path.resolve(),
                index,
            )
        )

    results.sort(
        key=lambda item: item[0]
    )

    return results


def next_run_id(
    output_root: Path,
    framework: str,
    policy: dict[str, Any],
) -> str:
    existing = existing_run_indices(
        output_root,
        framework,
        policy,
    )

    next_sequence = (
        existing[-1][0] + 1
        if existing
        else 1
    )

    sequence_width = int(
        policy[
            "run_identifier_policy"
        ]["sequence_width"]
    )

    return (
        f"{run_prefix(framework, policy)}"
        f"_{next_sequence:0{sequence_width}d}"
    )


def resolve_previous_run(
    previous_run_argument: str,
    output_root: Path,
    framework: str,
    policy: dict[str, Any],
) -> tuple[
    dict[str, Any] | None,
    str,
]:
    if previous_run_argument == "none":
        return None, "none"

    if previous_run_argument == "auto":
        existing = existing_run_indices(
            output_root,
            framework,
            policy,
        )

        if not existing:
            return None, "none"

        _, _, index = existing[-1]

        return (
            index,
            "latest_previous_run",
        )

    path = Path(
        previous_run_argument
    ).expanduser()

    if not path.is_absolute():
        path = (
            EXP006_DIR
            / path
        )

    path = path.resolve()

    if path.is_dir():
        path = (
            path
            / policy[
                "run_identifier_policy"
            ]["run_index_filename"]
        )

    if not path.is_file():
        raise FileNotFoundError(
            "Previous Run Index does not "
            f"exist: {path}"
        )

    try:
        path.relative_to(
            output_root.resolve()
        )
    except ValueError as error:
        raise ValueError(
            "Explicit previous Run Index must "
            "remain inside the configured "
            "Candidate output root"
        ) from error

    index = load_json(path)
    require_dict(index, str(path))

    if (
        index.get("run_version")
        != policy["run_index_version"]
    ):
        raise ValueError(
            "Previous Run Index has an "
            "unsupported run_version"
        )

    metadata = require_dict(
        index.get("metadata"),
        f"{path}.metadata",
    )

    declared_framework = require_string(
        metadata.get("framework"),
        f"{path}.metadata.framework",
    )

    if (
        declared_framework.lower()
        != framework.lower()
    ):
        raise ValueError(
            "Previous Run Index framework "
            f"{declared_framework!r} does not "
            f"match current framework "
            f"{framework!r}"
        )

    require_string(
        metadata.get("run_id"),
        f"{path}.metadata.run_id",
    )

    return (
        index,
        "explicit_previous_run",
    )


def member_id_set(
    candidate_entry: dict[str, Any],
) -> set[str]:
    member_ids = candidate_entry.get(
        "member_pattern_ids"
    )

    if not isinstance(member_ids, list):
        raise ValueError(
            "Run Index candidate entry is "
            "missing member_pattern_ids"
        )

    if not all(
        isinstance(item, str)
        and item
        for item in member_ids
    ):
        raise ValueError(
            "member_pattern_ids must contain "
            "non-empty strings"
        )

    return set(member_ids)


def previous_candidate_entries(
    previous_index: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if previous_index is None:
        return []

    candidates = require_list(
        previous_index.get(
            "candidates",
            [],
        ),
        "previous_run.candidates",
    )

    normalized: list[
        dict[str, Any]
    ] = []

    for index, candidate in enumerate(
        candidates
    ):
        candidate = require_dict(
            candidate,
            (
                "previous_run.candidates"
                f"[{index}]"
            ),
        )

        require_string(
            candidate.get(
                "candidate_group_id"
            ),
            (
                "previous_run.candidates"
                f"[{index}].candidate_group_id"
            ),
        )

        require_string(
            candidate.get(
                "candidate_group_hash"
            ),
            (
                "previous_run.candidates"
                f"[{index}].candidate_group_hash"
            ),
        )

        member_id_set(candidate)
        normalized.append(candidate)

    return normalized


def current_candidate_entry(
    manifest: dict[str, Any],
    object_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    return {
        "candidate_group_id": (
            manifest["metadata"][
                "candidate_group_id"
            ]
        ),
        "candidate_group_hash": (
            manifest["metadata"][
                "candidate_group_hash"
            ]
        ),
        "candidate_object_relpath": (
            object_path
            .relative_to(output_root)
            .as_posix()
        ),
        "member_pattern_ids": sorted(
            member["pattern_id"]
            for member in manifest["members"]
        ),
        "change_status": None,
        "related_previous_candidate_ids": [],
        "analysis_recommended": None,
    }


def classify_candidate_changes(
    current_entries: list[
        dict[str, Any]
    ],
    previous_index: dict[str, Any] | None,
    policy: dict[str, Any],
    policy_hash: str,
) -> tuple[
    list[dict[str, Any]],
    list[str],
    list[str],
    bool | None,
]:
    tracking_policy = policy[
        "candidate_run_tracking_policy"
    ]

    allowed_statuses = set(
        tracking_policy[
            "allowed_current_candidate_change_statuses"
        ]
    )

    recommended_statuses = set(
        tracking_policy[
            "analysis_recommended_for_statuses"
        ]
    )

    previous_entries = (
        previous_candidate_entries(
            previous_index
        )
    )

    if previous_index is None:
        for current in current_entries:
            current["change_status"] = "new"
            current[
                "related_previous_candidate_ids"
            ] = []
            current[
                "analysis_recommended"
            ] = (
                "new"
                in recommended_statuses
            )

        current_entries.sort(
            key=lambda entry: (
                entry["candidate_group_id"]
            )
        )

        return (
            current_entries,
            [],
            [],
            tracking_policy[
                "first_run_policy_compatibility_value"
            ],
        )

    previous_generation = require_dict(
        previous_index.get(
            "generation_information"
        ),
        (
            "previous_run."
            "generation_information"
        ),
    )

    previous_policy_version = (
        previous_generation.get(
            "retrieval_policy_version"
        )
    )

    previous_policy_hash = (
        previous_generation.get(
            "retrieval_policy_hash"
        )
    )

    policy_compatible = (
        previous_policy_version
        == policy["policy_version"]
        and previous_policy_hash
        == policy_hash
    )

    previous_by_id = {
        entry["candidate_group_id"]: entry
        for entry in previous_entries
    }

    current_by_id = {
        entry["candidate_group_id"]: entry
        for entry in current_entries
    }

    previous_sets = {
        candidate_id: member_id_set(entry)
        for candidate_id, entry
        in previous_by_id.items()
    }

    current_sets = {
        candidate_id: member_id_set(entry)
        for candidate_id, entry
        in current_by_id.items()
    }

    current_overlaps: dict[
        str,
        list[str],
    ] = {
        candidate_id: []
        for candidate_id in current_by_id
    }

    previous_overlaps: dict[
        str,
        list[str],
    ] = {
        candidate_id: []
        for candidate_id in previous_by_id
    }

    for current_id, current_members in (
        current_sets.items()
    ):
        for (
            previous_id,
            previous_members,
        ) in previous_sets.items():
            if current_members & previous_members:
                current_overlaps[
                    current_id
                ].append(previous_id)

                previous_overlaps[
                    previous_id
                ].append(current_id)

    unchanged_previous_ids: set[str] = set()

    for current in current_entries:
        current_id = current[
            "candidate_group_id"
        ]

        current_hash = current[
            "candidate_group_hash"
        ]

        current_members = current_sets[
            current_id
        ]

        overlap_ids = sorted(
            current_overlaps[current_id]
        )

        exact_hash_matches = [
            previous_id
            for previous_id in overlap_ids
            if previous_by_id[
                previous_id
            ]["candidate_group_hash"]
            == current_hash
        ]

        if (
            policy_compatible
            and exact_hash_matches
        ):
            status = "unchanged"
            related_ids = sorted(
                exact_hash_matches
            )

            unchanged_previous_ids.update(
                related_ids
            )

        elif not overlap_ids:
            status = "new"
            related_ids = []

        elif len(overlap_ids) > 1:
            status = "merged_component"
            related_ids = overlap_ids

        else:
            previous_id = overlap_ids[0]
            previous_members = (
                previous_sets[previous_id]
            )

            related_ids = [previous_id]

            if (
                len(
                    previous_overlaps[
                        previous_id
                    ]
                )
                > 1
            ):
                status = "split_component"

            elif (
                current_members
                == previous_members
            ):
                status = "changed"

            elif (
                previous_members
                < current_members
            ):
                status = "expanded"

            elif (
                current_members
                < previous_members
            ):
                status = "contracted"

            else:
                status = "changed"

        if status not in allowed_statuses:
            raise ValueError(
                "Policy does not allow "
                f"change_status={status!r}"
            )

        current["change_status"] = status
        current[
            "related_previous_candidate_ids"
        ] = sorted(related_ids)

        current[
            "analysis_recommended"
        ] = (
            status
            in recommended_statuses
        )

    retired_ids = sorted(
        previous_id
        for previous_id, overlaps
        in previous_overlaps.items()
        if not overlaps
    )

    superseded_ids = sorted(
        previous_id
        for previous_id, overlaps
        in previous_overlaps.items()
        if overlaps
        and previous_id
        not in unchanged_previous_ids
    )

    current_entries.sort(
        key=lambda entry: (
            entry["candidate_group_id"]
        )
    )

    return (
        current_entries,
        retired_ids,
        superseded_ids,
        policy_compatible,
    )


def count_change_statuses(
    candidate_entries: list[
        dict[str, Any]
    ],
    policy: dict[str, Any],
) -> dict[str, int]:
    allowed_statuses = policy[
        "candidate_run_tracking_policy"
    ][
        "allowed_current_candidate_change_statuses"
    ]

    counts = {
        status: 0
        for status in allowed_statuses
    }

    for entry in candidate_entries:
        status = entry["change_status"]

        if status not in counts:
            raise ValueError(
                "Unsupported change_status: "
                f"{status}"
            )

        counts[status] += 1

    return counts


def build_run_index(
    run_id: str,
    framework: str,
    current_entries: list[
        dict[str, Any]
    ],
    previous_index: dict[str, Any] | None,
    comparison_mode: str,
    retired_ids: list[str],
    superseded_ids: list[str],
    policy_compatible: bool | None,
    policy: dict[str, Any],
    policy_hash: str,
    script_content_hash: str,
    corpus_hash: str,
    eligible_pattern_count: int,
) -> dict[str, Any]:
    status_counts = count_change_statuses(
        current_entries,
        policy,
    )

    analysis_recommended_count = sum(
        1
        for entry in current_entries
        if entry["analysis_recommended"]
    )

    if previous_index is None:
        previous_run_id = None
    else:
        previous_metadata = require_dict(
            previous_index.get("metadata"),
            "previous_run.metadata",
        )

        previous_run_id = require_string(
            previous_metadata.get("run_id"),
            "previous_run.metadata.run_id",
        )

    if comparison_mode == "none":
        if (
            previous_run_id is not None
            or policy_compatible is not None
        ):
            raise ValueError(
                "comparison_mode=none requires "
                "null previous Run and null "
                "Policy compatibility"
            )

    return {
        "run_version": (
            policy["run_index_version"]
        ),

        "metadata": {
            "run_id": run_id,
            "framework": framework,
        },

        "generation_information": {
            "method": policy[
                "execution_boundary"
            ]["method"],
            "retrieval_policy_version": (
                policy["policy_version"]
            ),
            "retrieval_policy_hash": (
                policy_hash
            ),
            "script_version": (
                SCRIPT_VERSION
            ),
            "script_hash": (
                script_content_hash
            ),
            "source_corpus_hash": (
                corpus_hash
            ),
            "generated_at": (
                utc_timestamp()
            ),
        },

        "comparison": {
            "comparison_mode": (
                comparison_mode
            ),
            "previous_run_id": (
                previous_run_id
            ),
            "policy_compatible": (
                policy_compatible
            ),
        },

        "summary": {
            "eligible_pattern_count": (
                eligible_pattern_count
            ),
            "candidate_count": len(
                current_entries
            ),
            "analysis_recommended_count": (
                analysis_recommended_count
            ),
            "change_status_counts": (
                status_counts
            ),
            "retired_candidate_count": len(
                retired_ids
            ),
            "superseded_candidate_count": len(
                superseded_ids
            ),
        },

        "candidates": current_entries,

        "retired_candidate_ids": sorted(
            retired_ids
        ),

        "superseded_candidate_ids": sorted(
            superseded_ids
        ),
    }


def validate_existing_candidate_object(
    path: Path,
    manifest: dict[str, Any],
) -> None:
    existing = load_json(path)
    require_dict(existing, str(path))

    existing_id = (
        existing.get("metadata", {}).get(
            "candidate_group_id"
        )
    )

    existing_hash = (
        existing.get("metadata", {}).get(
            "candidate_group_hash"
        )
    )

    new_id = manifest[
        "metadata"
    ]["candidate_group_id"]

    new_hash = manifest[
        "metadata"
    ]["candidate_group_hash"]

    if (
        existing_id != new_id
        or existing_hash != new_hash
    ):
        raise FileExistsError(
            "Candidate ID collision or "
            "unversioned semantic change detected: "
            f"{path}. Increase the short hash "
            "length or change the retrieval "
            "Policy version."
        )


def write_json_exclusive(
    path: Path,
    value: dict[str, Any],
    policy: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    indent = int(
        policy[
            "output_policy"
        ]["output_json_indent"]
    )

    ensure_ascii = bool(
        policy[
            "output_policy"
        ]["output_ensure_ascii"]
    )

    with path.open(
        "x",
        encoding="utf-8",
    ) as output_file:
        json.dump(
            value,
            output_file,
            indent=indent,
            ensure_ascii=ensure_ascii,
        )

        output_file.write("\n")


def process_framework(
    framework: str,
    records: list[PatternRecord],
    policy: dict[str, Any],
    policy_hash: str,
    script_content_hash: str,
    output_root: Path,
    previous_run_argument: str,
    dry_run: bool,
) -> tuple[int, int, Path]:
    manifests = (
        build_framework_manifests(
            records,
            policy,
            policy_hash,
            script_content_hash,
        )
    )

    run_id = next_run_id(
        output_root,
        framework,
        policy,
    )

    object_plans: list[
        tuple[
            Path,
            dict[str, Any],
            bool,
        ]
    ] = []

    current_entries: list[
        dict[str, Any]
    ] = []

    new_object_count = 0
    reused_object_count = 0

    for manifest in manifests:
        object_path = candidate_object_path(
            manifest,
            output_root,
            policy,
        )

        already_exists = (
            object_path.exists()
        )

        if already_exists:
            validate_existing_candidate_object(
                object_path,
                manifest,
            )

            reused_object_count += 1

        else:
            new_object_count += 1

        object_plans.append(
            (
                object_path,
                manifest,
                already_exists,
            )
        )

        current_entries.append(
            current_candidate_entry(
                manifest,
                object_path,
                output_root,
            )
        )

    previous_index, comparison_mode = (
        resolve_previous_run(
            previous_run_argument,
            output_root,
            framework,
            policy,
        )
    )

    (
        current_entries,
        retired_ids,
        superseded_ids,
        policy_compatible,
    ) = classify_candidate_changes(
        current_entries,
        previous_index,
        policy,
        policy_hash,
    )

    corpus_hash = source_corpus_hash(
        records
    )

    index = build_run_index(
        run_id,
        framework,
        current_entries,
        previous_index,
        comparison_mode,
        retired_ids,
        superseded_ids,
        policy_compatible,
        policy,
        policy_hash,
        script_content_hash,
        corpus_hash,
        len(records),
    )

    index_path = run_index_path(
        output_root,
        framework,
        run_id,
        policy,
    )

    if index_path.exists():
        raise FileExistsError(
            "Refusing to overwrite an existing "
            f"Run Index: {index_path}"
        )

    print()
    print(f"Framework: {framework}")
    print(f"Eligible Patterns: {len(records)}")
    print(f"Candidate groups: {len(manifests)}")
    print(f"Run ID: {run_id}")

    if previous_index is None:
        print("Previous Run: none")
    else:
        print(
            "Previous Run: "
            f"{previous_index.get('run_id')}"
        )

    print(
        "Policy-compatible comparison: "
        f"{policy_compatible}"
    )

    for entry in current_entries:
        print(
            "[CANDIDATE]",
            entry["candidate_group_id"],
            "| status=",
            entry["change_status"],
            "| analysis_recommended=",
            entry["analysis_recommended"],
            "| members=",
            len(
                entry[
                    "member_pattern_ids"
                ]
            ),
        )

    if retired_ids:
        print(
            "Retired Candidates: "
            + ", ".join(retired_ids)
        )

    if superseded_ids:
        print(
            "Superseded Candidates: "
            + ", ".join(
                superseded_ids
            )
        )

    if dry_run:
        print(
            f"[DRY-RUN] New Candidate objects: "
            f"{new_object_count}"
        )

        print(
            f"[DRY-RUN] Reused Candidate objects: "
            f"{reused_object_count}"
        )

        print(
            "[DRY-RUN] Run Index -> "
            f"{index_path}"
        )

        return (
            new_object_count,
            reused_object_count,
            index_path,
        )

    for (
        object_path,
        manifest,
        already_exists,
    ) in object_plans:
        if already_exists:
            print(
                "[REUSE] "
                f"{object_path}"
            )

            continue

        write_json_exclusive(
            object_path,
            manifest,
            policy,
        )

        print(
            "[WRITE] "
            f"{object_path}"
        )

    write_json_exclusive(
        index_path,
        index,
        policy,
    )

    print(
        "[WRITE] "
        f"{index_path}"
    )

    return (
        new_object_count,
        reused_object_count,
        index_path,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Deterministically rebuild Pattern "
            "Family Candidates from all eligible "
            "API-specific Pattern v2 JSON records, "
            "reuse unchanged Candidate objects, "
            "and write an immutable Run Index."
        )
    )

    parser.add_argument(
        "--pattern-root",
        default=None,
        help=(
            "Pattern input root. Defaults to "
            "EXP006/bug_patterns."
        ),
    )

    parser.add_argument(
        "--policy",
        default=None,
        help=(
            "Candidate Policy JSON. Defaults to "
            "schemas/"
            "pattern_family_candidate_policy.json."
        ),
    )

    parser.add_argument(
        "--output",
        default=None,
        help=(
            "Candidate output root. Defaults to "
            "the output root declared by Policy."
        ),
    )

    parser.add_argument(
        "--framework",
        default=None,
        help=(
            "Optional framework filter, for "
            "example pytorch."
        ),
    )

    parser.add_argument(
        "--previous-run",
        default="auto",
        help=(
            "Previous Candidate Run used for "
            "change comparison. Use 'auto' for "
            "the latest Run, 'none' for no "
            "comparison, or provide a Run "
            "directory/Run Index path. An "
            "explicit path requires --framework."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Build, compare, and validate without "
            "writing Candidate objects or Run "
            "Indexes."
        ),
    )

    parser.add_argument(
        "--show-skipped",
        action="store_true",
        help=(
            "Print Patterns excluded by Policy."
        ),
    )

    args = parser.parse_args()

    if (
        args.previous_run
        not in {"auto", "none"}
        and args.framework is None
    ):
        parser.error(
            "An explicit --previous-run path "
            "requires --framework."
        )

    policy_path = resolve_path(
        args.policy,
        DEFAULT_POLICY_FILE,
    )

    policy = load_json(policy_path)
    require_dict(policy, str(policy_path))
    validate_policy(policy)

    policy_hash = file_hash(
        policy_path
    )

    pattern_root = resolve_path(
        args.pattern_root,
        DEFAULT_PATTERN_ROOT,
    )

    if args.output is None:
        configured_output = policy[
            "output_policy"
        ]["output_root"]

        output_root = resolve_path(
            configured_output,
            DEFAULT_OUTPUT_ROOT,
        )
    else:
        output_root = resolve_path(
            args.output,
            DEFAULT_OUTPUT_ROOT,
        )

    records, skipped, invalid = (
        scan_patterns(
            pattern_root,
            policy,
            args.framework,
        )
    )

    if args.show_skipped:
        for message in skipped:
            print(f"[SKIP] {message}")

    if invalid:
        for message in invalid:
            print(f"[INVALID] {message}")

        print()
        print(
            "Candidate generation stopped "
            "because invalid Pattern inputs "
            "were detected."
        )

        return 2

    print("Pattern scan complete")
    print(f"Eligible: {len(records)}")
    print(f"Skipped:  {len(skipped)}")
    print(f"Invalid:  {len(invalid)}")

    records_by_framework = (
        group_records_by_framework(records)
    )

    if (
        not records_by_framework
        and args.framework is not None
    ):
        records_by_framework[
            args.framework
        ] = []

    if not records_by_framework:
        print(
            "No eligible Pattern v2 records "
            "were found."
        )

        return 0

    if (
        args.previous_run
        not in {"auto", "none"}
        and len(records_by_framework) != 1
    ):
        parser.error(
            "An explicit --previous-run path "
            "can be used with only one framework."
        )

    script_content_hash = file_hash(
        Path(__file__).resolve()
    )

    total_new_objects = 0
    total_reused_objects = 0
    run_index_paths: list[Path] = []

    for framework in sorted(
        records_by_framework
    ):
        (
            new_objects,
            reused_objects,
            index_path,
        ) = process_framework(
            framework,
            records_by_framework[framework],
            policy,
            policy_hash,
            script_content_hash,
            output_root,
            args.previous_run,
            args.dry_run,
        )

        total_new_objects += new_objects
        total_reused_objects += (
            reused_objects
        )

        run_index_paths.append(
            index_path
        )

    print()
    print(
        "Candidate generation complete"
    )

    print(
        "New Candidate objects: "
        f"{total_new_objects}"
    )

    print(
        "Reused Candidate objects: "
        f"{total_reused_objects}"
    )

    print(
        "Candidate Runs: "
        f"{len(run_index_paths)}"
    )

    for path in run_index_paths:
        print(f"Run Index: {path}")

    if args.dry_run:
        print(
            "Dry run only; no files were written."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())