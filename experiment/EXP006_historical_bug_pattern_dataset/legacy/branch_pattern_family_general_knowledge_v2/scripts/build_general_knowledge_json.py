import argparse
import copy
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


SCRIPT_DIR = Path(__file__).resolve().parent
EXP006_DIR = SCRIPT_DIR.parent

DEFAULT_FAMILY_ROOT = (
    EXP006_DIR
    / "pattern_families"
)

DEFAULT_KNOWLEDGE_ROOT = (
    EXP006_DIR
    / "knowledge_base"
)

DEFAULT_OUTPUT_ROOT = (
    EXP006_DIR
    / "general_knowledge"
)

CONTRACT_FILE = (
    EXP006_DIR
    / "schemas"
    / "general_knowledge_extraction_contract.json"
)

RULE_FILE = (
    EXP006_DIR
    / "schemas"
    / "pattern_family_to_general_knowledge_rules.md"
)

GENERAL_KNOWLEDGE_SCHEMA_VERSION = "1.0"
PATTERN_FAMILY_SCHEMA_VERSION = "1.1"
API_KNOWLEDGE_SCHEMA_VERSION = "2.0"

MAPPING_VERSION = "1.0"
PROMPT_VERSION = "general_knowledge_extract_v1"

DEFAULT_MODEL = "deepseek-v4-pro"

DEFAULT_API_URL = (
    "https://api.deepseek.com/chat/completions"
)

ACCEPTED_VALIDATION_STATUSES = {
    "automatically_validated",
    "human_verified"
}

CONFIDENCE_RANK = {
    "low": 0,
    "medium": 1,
    "high": 2
}


class PipelineError(RuntimeError):
    pass


def load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise PipelineError(
            f"Unable to read text file {path}: {error}"
        ) from error


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as file:
            value = json.load(file)
    except OSError as error:
        raise PipelineError(
            f"Unable to read JSON file {path}: {error}"
        ) from error
    except json.JSONDecodeError as error:
        raise PipelineError(
            f"Invalid JSON file {path}: {error}"
        ) from error

    if not isinstance(value, dict):
        raise PipelineError(
            f"JSON root must be an object: {path}"
        )

    return value


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":")
    ).encode("utf-8")


def canonical_json_hash(value: Any) -> str:
    digest = hashlib.sha256(
        canonical_json_bytes(value)
    ).hexdigest()

    return f"sha256:{digest}"


def require_dict(
    value: Any,
    label: str
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PipelineError(
            f"{label} must be an object"
        )

    return value


def require_list(
    value: Any,
    label: str
) -> list[Any]:
    if not isinstance(value, list):
        raise PipelineError(
            f"{label} must be an array"
        )

    return value


def require_string(
    value: Any,
    label: str
) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
    ):
        raise PipelineError(
            f"{label} must be a non-empty string"
        )

    return value.strip()


def require_string_or_null(
    value: Any,
    label: str
) -> str | None:
    if value is None:
        return None

    return require_string(value, label)


def require_positive_integer(
    value: Any,
    label: str
) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 1
    ):
        raise PipelineError(
            f"{label} must be a positive integer"
        )

    return value


def validate_exact_keys(
    value: Any,
    expected_keys: set[str],
    label: str
) -> dict[str, Any]:
    value = require_dict(value, label)

    actual_keys = set(value.keys())

    missing = expected_keys - actual_keys
    extra = actual_keys - expected_keys

    if missing:
        raise PipelineError(
            f"{label} is missing keys: "
            f"{sorted(missing)}"
        )

    if extra:
        raise PipelineError(
            f"{label} contains unsupported keys: "
            f"{sorted(extra)}"
        )

    return value


def find_empty_string(
    value: Any,
    path: str = ""
) -> str | None:
    if isinstance(value, str):
        if not value.strip():
            return path or "root"

        return None

    if isinstance(value, dict):
        for key, item in value.items():
            current_path = (
                f"{path}.{key}"
                if path
                else key
            )

            found = find_empty_string(
                item,
                current_path
            )

            if found:
                return found

    if isinstance(value, list):
        for index, item in enumerate(value):
            found = find_empty_string(
                item,
                f"{path}[{index}]"
            )

            if found:
                return found

    return None


def slugify(value: str) -> str:
    value = value.lower().strip()

    value = re.sub(
        r"[^a-z0-9]+",
        "_",
        value
    )

    value = re.sub(
        r"_+",
        "_",
        value
    )

    return value.strip("_")


def framework_prefix(framework: str) -> str:
    prefixes = {
        "pytorch": "pt",
        "tensorflow": "tf"
    }

    normalized = slugify(framework)

    return prefixes.get(
        normalized,
        normalized or "dl"
    )


def resolve_project_path(value: str) -> Path:
    path = Path(value).expanduser()

    if not path.is_absolute():
        path = EXP006_DIR / path

    return path.resolve()


def validate_safe_identifier(
    value: str,
    label: str
) -> str:
    value = require_string(value, label)

    if (
        "/" in value
        or "\\" in value
        or ".." in value
    ):
        raise PipelineError(
            f"{label} must be an identifier, not a path"
        )

    if not re.fullmatch(
        r"[A-Za-z0-9_.-]+",
        value
    ):
        raise PipelineError(
            f"{label} contains unsupported characters"
        )

    return value


def validate_configuration(
    contract: dict[str, Any],
    rules: str
) -> None:
    if contract.get("contract_version") != "1.0":
        raise PipelineError(
            "General Knowledge Contract version must be 1.0"
        )

    if (
        contract.get("target_schema_version")
        != GENERAL_KNOWLEDGE_SCHEMA_VERSION
    ):
        raise PipelineError(
            "Contract target schema version does not match "
            "the script schema version"
        )

    if (
        "Pattern-Family-to-General-Knowledge Rules v1.0"
        not in rules
    ):
        raise PipelineError(
            "Rules file does not identify version 1.0"
        )


def strip_evidence_refs(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}

        for key, item in value.items():
            if key == "evidence_refs":
                continue

            result[key] = strip_evidence_refs(item)

        return result

    if isinstance(value, list):
        return [
            strip_evidence_refs(item)
            for item in value
        ]

    return copy.deepcopy(value)


def meaningful_value(value: Any) -> bool:
    if value is None:
        return False

    if isinstance(value, str):
        return bool(value.strip())

    if isinstance(value, list):
        return any(
            meaningful_value(item)
            for item in value
        )

    if isinstance(value, dict):
        non_semantic_keys = {
            "evidence_refs",
            "condition_id",
            "goal_id",
            "limitation_id",
            "characteristic_id",
            "difference_id",
            "conflict_id",
            "supporting_pattern_ids",
            "affected_pattern_ids"
        }

        return any(
            meaningful_value(item)
            for key, item in value.items()
            if key not in non_semantic_keys
        )

    return True


def find_latest_family_file(
    family_root: Path,
    framework: str,
    family_id: str
) -> Path:
    framework_dir = (
        family_root
        / slugify(framework)
    )

    family_dir = (
        framework_dir
        / family_id
    )

    if not family_dir.is_dir():
        raise PipelineError(
            f"Pattern Family directory does not exist: "
            f"{family_dir}"
        )

    filename_pattern = re.compile(
        rf"^{re.escape(family_id)}_r(\d+)\.json$"
    )

    candidates = []

    for path in family_dir.glob("*.json"):
        match = filename_pattern.fullmatch(
            path.name
        )

        if match:
            candidates.append(
                (
                    int(match.group(1)),
                    path
                )
            )

    if not candidates:
        raise PipelineError(
            f"No Pattern Family revision was found in "
            f"{family_dir}"
        )

    revisions = [
        revision
        for revision, _ in candidates
    ]

    if len(revisions) != len(set(revisions)):
        raise PipelineError(
            f"Duplicate Pattern Family revision detected "
            f"under {family_dir}"
        )

    return max(
        candidates,
        key=lambda item: item[0]
    )[1]


def validate_pattern_family(
    family: dict[str, Any],
    family_path: Path,
    expected_framework: str,
    expected_family_id: str
) -> dict[str, Any]:
    if (
        family.get("schema_version")
        != PATTERN_FAMILY_SCHEMA_VERSION
    ):
        raise PipelineError(
            f"{family_path} is not a Pattern Family "
            f"Schema {PATTERN_FAMILY_SCHEMA_VERSION} record"
        )

    metadata = require_dict(
        family.get("metadata"),
        "Pattern Family metadata"
    )

    family_id = require_string(
        metadata.get("family_id"),
        "Pattern Family metadata.family_id"
    )

    canonical_name = require_string(
        metadata.get("canonical_name"),
        "Pattern Family metadata.canonical_name"
    )

    framework = require_string(
        metadata.get("framework"),
        "Pattern Family metadata.framework"
    )

    if family_id != expected_family_id:
        raise PipelineError(
            "Pattern Family ID does not match --family-id"
        )

    if slugify(framework) != slugify(
        expected_framework
    ):
        raise PipelineError(
            "Pattern Family framework does not match "
            "--framework"
        )

    revision_information = require_dict(
        family.get("revision_information"),
        "Pattern Family revision_information"
    )

    revision = require_positive_integer(
        revision_information.get("revision"),
        "Pattern Family revision_information.revision"
    )

    expected_filename = (
        f"{family_id}_r{revision:03d}.json"
    )

    if family_path.name != expected_filename:
        raise PipelineError(
            "Pattern Family filename does not match its "
            "identity and revision"
        )

    provenance = require_dict(
        family.get("provenance"),
        "Pattern Family provenance"
    )

    validation_status = provenance.get(
        "validation_status"
    )

    if (
        validation_status
        not in ACCEPTED_VALIDATION_STATUSES
    ):
        raise PipelineError(
            "Pattern Family must be automatically validated "
            "or human verified"
        )

    members = require_list(
        family.get("members"),
        "Pattern Family members"
    )

    if len(members) < 2:
        raise PipelineError(
            "Pattern Family must contain at least two members"
        )

    pattern_ids = set()
    member_apis = set()

    normalized_members = []

    for index, member in enumerate(members):
        label = f"Pattern Family members[{index}]"

        member = require_dict(member, label)

        pattern_id = require_string(
            member.get("pattern_id"),
            f"{label}.pattern_id"
        )

        pattern_hash = require_string(
            member.get("pattern_hash"),
            f"{label}.pattern_hash"
        )

        primary_api = require_string(
            member.get("primary_api"),
            f"{label}.primary_api"
        )

        if pattern_id in pattern_ids:
            raise PipelineError(
                f"Duplicate Family member Pattern ID: "
                f"{pattern_id}"
            )

        pattern_ids.add(pattern_id)
        member_apis.add(primary_api)

        normalized_members.append(
            {
                "pattern_id": pattern_id,
                "pattern_hash": pattern_hash,
                "primary_api": primary_api
            }
        )

    if len(member_apis) < 2:
        raise PipelineError(
            "Pattern Family must contain at least two "
            "distinct member APIs"
        )

    support = require_dict(
        family.get("support"),
        "Pattern Family support"
    )

    supporting_apis = require_list(
        support.get("supporting_apis"),
        "Pattern Family support.supporting_apis"
    )

    normalized_supporting_apis = []

    for index, api in enumerate(
        supporting_apis
    ):
        normalized_supporting_apis.append(
            require_string(
                api,
                "Pattern Family "
                f"support.supporting_apis[{index}]"
            )
        )

    if len(normalized_supporting_apis) != len(
        set(normalized_supporting_apis)
    ):
        raise PipelineError(
            "Pattern Family support.supporting_apis "
            "contains duplicates"
        )

    if sorted(
        normalized_supporting_apis
    ) != sorted(member_apis):
        raise PipelineError(
            "Pattern Family support.supporting_apis "
            "does not match the member API set"
        )

    pattern_count = require_positive_integer(
        support.get("pattern_count"),
        "Pattern Family support.pattern_count"
    )

    if pattern_count != len(
        normalized_members
    ):
        raise PipelineError(
            "Pattern Family support.pattern_count "
            "does not match the number of members"
        )

    distinct_api_count = (
        require_positive_integer(
            support.get("distinct_api_count"),
            "Pattern Family "
            "support.distinct_api_count"
        )
    )

    if distinct_api_count != len(
        member_apis
    ):
        raise PipelineError(
            "Pattern Family support.distinct_api_count "
            "does not match the member API set"
        )

    independent_report_count = (
        require_positive_integer(
            support.get(
                "independent_report_count"
            ),
            "Pattern Family "
            "support.independent_report_count"
        )
    )

    if independent_report_count < 2:
        raise PipelineError(
            "Pattern Family must be supported by at "
            "least two independent Reports or Issues"
        )

    support_tier = require_string(
        support.get("support_tier"),
        "Pattern Family support.support_tier"
    )

    if support_tier not in {
        "emerging",
        "corroborated",
        "broadly_supported"
    }:
        raise PipelineError(
            "Pattern Family support tier is invalid"
        )

    confidence = require_dict(
        family.get("confidence"),
        "Pattern Family confidence"
    )

    generalization_confidence = require_string(
        confidence.get("generalization"),
        "Pattern Family confidence.generalization"
    )

    if generalization_confidence not in CONFIDENCE_RANK:
        raise PipelineError(
            "Pattern Family generalization confidence "
            "is invalid"
        )

    return {
        "data": family,
        "path": family_path,
        "family_id": family_id,
        "canonical_name": canonical_name,
        "framework": framework,
        "revision": revision,
        "family_hash": canonical_json_hash(family),
        "members": sorted(
            normalized_members,
            key=lambda item: item["pattern_id"]
        ),
        "member_apis": sorted(member_apis),
        "support_tier": support_tier,
        "generalization_confidence": (
            generalization_confidence
        )
    }


def load_api_knowledge_index(
    knowledge_root: Path
) -> dict[str, list[dict[str, Any]]]:
    if not knowledge_root.is_dir():
        raise PipelineError(
            f"Knowledge root does not exist: "
            f"{knowledge_root}"
        )

    index: dict[
        str,
        list[dict[str, Any]]
    ] = {}

    seen_knowledge_ids = set()

    for path in sorted(
        knowledge_root.rglob("*.json")
    ):
        knowledge = load_json(path)

        if (
            knowledge.get("schema_version")
            != API_KNOWLEDGE_SCHEMA_VERSION
        ):
            raise PipelineError(
                f"Unsupported Knowledge schema in {path}"
            )

        metadata = require_dict(
            knowledge.get("metadata"),
            f"{path}: metadata"
        )

        if (
            metadata.get("knowledge_level")
            != "api_specific"
        ):
            raise PipelineError(
                f"{path} is not API-specific Knowledge"
            )

        knowledge_id = require_string(
            metadata.get("knowledge_id"),
            f"{path}: metadata.knowledge_id"
        )

        if knowledge_id in seen_knowledge_ids:
            raise PipelineError(
                f"Duplicate Knowledge ID detected: "
                f"{knowledge_id}"
            )

        seen_knowledge_ids.add(knowledge_id)

        derivation = require_dict(
            knowledge.get("derivation_information"),
            f"{path}: derivation_information"
        )

        input_patterns = require_list(
            derivation.get("input_patterns"),
            f"{path}: input_patterns"
        )

        if len(input_patterns) != 1:
            raise PipelineError(
                f"{path} must contain exactly one "
                "input Pattern"
            )

        input_pattern = require_dict(
            input_patterns[0],
            f"{path}: input_patterns[0]"
        )

        source_pattern_id = require_string(
            input_pattern.get("pattern_id"),
            f"{path}: source pattern ID"
        )

        source_pattern_hash = require_string(
            input_pattern.get("pattern_hash"),
            f"{path}: source pattern hash"
        )

        validation_status = derivation.get(
            "validation_status"
        )

        scope = require_dict(
            knowledge.get("scope"),
            f"{path}: scope"
        )

        framework = require_string(
            scope.get("framework"),
            f"{path}: scope.framework"
        )

        primary_api = require_string(
            scope.get("primary_api"),
            f"{path}: scope.primary_api"
        )

        directly_supported_apis = require_list(
            scope.get("directly_supported_apis"),
            f"{path}: scope.directly_supported_apis"
        )

        normalized_supported_apis = []

        for index, api in enumerate(
            directly_supported_apis
        ):
            normalized_supported_apis.append(
                require_string(
                    api,
                    f"{path}: "
                    "scope.directly_supported_apis"
                    f"[{index}]"
                )
            )

        if primary_api not in (
            normalized_supported_apis
        ):
            raise PipelineError(
                f"{path}: scope.primary_api must appear "
                "in scope.directly_supported_apis"
            )

        require_string(
            metadata.get("canonical_name"),
            f"{path}: metadata.canonical_name"
        )

        for field_name in [
            "evidence_basis",
            "knowledge_statement",
            "applicability",
            "testing_guidance",
            "confidence"
        ]:
            require_dict(
                knowledge.get(field_name),
                f"{path}: {field_name}"
            )

        context = {
            "data": knowledge,
            "path": path,
            "knowledge_id": knowledge_id,
            "knowledge_hash": canonical_json_hash(
                knowledge
            ),
            "source_pattern_id": source_pattern_id,
            "source_pattern_hash": source_pattern_hash,
            "framework": framework,
            "primary_api": primary_api,
            "validation_status": validation_status
        }

        index.setdefault(
            source_pattern_id,
            []
        ).append(context)

    return index


def resolve_member_knowledge(
    family_context: dict[str, Any],
    knowledge_index: dict[
        str,
        list[dict[str, Any]]
    ]
) -> list[dict[str, Any]]:
    resolved = []

    for member in family_context["members"]:
        pattern_id = member["pattern_id"]

        matches = knowledge_index.get(
            pattern_id,
            []
        )

        if not matches:
            raise PipelineError(
                f"No API-specific Knowledge record was "
                f"found for Family member {pattern_id}"
            )

        if len(matches) > 1:
            paths = [
                str(item["path"])
                for item in matches
            ]

            raise PipelineError(
                f"Multiple Knowledge records were found "
                f"for Family member {pattern_id}: {paths}"
            )

        knowledge = matches[0]

        if (
            knowledge["validation_status"]
            not in ACCEPTED_VALIDATION_STATUSES
        ):
            raise PipelineError(
                f"Knowledge {knowledge['knowledge_id']} "
                "must be automatically validated or "
                "human verified"
            )

        if slugify(
            knowledge["framework"]
        ) != slugify(
            family_context["framework"]
        ):
            raise PipelineError(
                f"Knowledge {knowledge['knowledge_id']} "
                "uses a different framework"
            )

        if (
            knowledge["primary_api"]
            != member["primary_api"]
        ):
            raise PipelineError(
                f"Knowledge {knowledge['knowledge_id']} "
                "primary API does not match its Family member"
            )

        if (
            knowledge["source_pattern_hash"]
            != member["pattern_hash"]
        ):
            raise PipelineError(
                f"Knowledge {knowledge['knowledge_id']} "
                "was derived from a different Pattern "
                "content hash"
            )

        resolved.append(knowledge)

    knowledge_ids = [
        item["knowledge_id"]
        for item in resolved
    ]

    if len(knowledge_ids) != len(
        set(knowledge_ids)
    ):
        raise PipelineError(
            "The same Knowledge record is mapped to more "
            "than one Family member"
        )

    return sorted(
        resolved,
        key=lambda item: item["source_pattern_id"]
    )


def add_ref(
    refs: list[str],
    value: str
) -> None:
    if value not in refs:
        refs.append(value)


def build_family_evidence_refs(
    family_context: dict[str, Any]
) -> list[str]:
    family = family_context["data"]
    family_id = family_context["family_id"]

    refs = []

    def add(path: str) -> None:
        add_ref(
            refs,
            f"family:{family_id}:{path}"
        )

    def add_if_meaningful(
        path: str,
        value: Any
    ) -> None:
        if meaningful_value(value):
            add(path)

    for field_name in [
        "family_core",
        "shared_characteristics",
        "applicability",
        "heterogeneity",
        "support",
        "confidence"
    ]:
        add_if_meaningful(
            field_name,
            family.get(field_name)
        )

    for member in family.get("members", []):
        if not isinstance(member, dict):
            continue

        pattern_id = member.get("pattern_id")

        if (
            isinstance(pattern_id, str)
            and pattern_id.strip()
            and meaningful_value(member)
        ):
            add(f"members.{pattern_id}")

    local_arrays = [
        (
            "shared_characteristics."
            "trigger_semantics",
            "characteristic_id"
        ),
        (
            "shared_characteristics."
            "mechanism_semantics",
            "characteristic_id"
        ),
        (
            "shared_characteristics."
            "execution_semantics",
            "characteristic_id"
        ),
        (
            "shared_characteristics."
            "failure_observables",
            "characteristic_id"
        ),
        (
            "applicability.required_capabilities",
            "condition_id"
        ),
        (
            "applicability.exclusion_conditions",
            "condition_id"
        ),
        (
            "heterogeneity.member_differences",
            "difference_id"
        ),
        (
            "heterogeneity.unresolved_conflicts",
            "conflict_id"
        )
    ]

    for field_path, id_field in local_arrays:
        current: Any = family

        for component in field_path.split("."):
            if not isinstance(current, dict):
                current = []
                break

            current = current.get(
                component,
                []
            )

        if not isinstance(current, list):
            continue

        if current:
            add(field_path)

        for index, item in enumerate(
            current,
            start=1
        ):
            if not meaningful_value(item):
                continue

            item_id = None

            if isinstance(item, dict):
                item_id = item.get(id_field)

            add(
                f"{field_path}."
                f"{item_id or index}"
            )

    if not any(
        ref.startswith(
            f"family:{family_id}:family_core"
        )
        for ref in refs
    ):
        raise PipelineError(
            "Pattern Family has no addressable "
            "family_core evidence"
        )

    return sorted(refs)


def build_knowledge_evidence_refs(
    knowledge_context: dict[str, Any]
) -> list[str]:
    knowledge = knowledge_context["data"]

    knowledge_id = knowledge_context[
        "knowledge_id"
    ]

    refs = []

    def add(path: str) -> None:
        add_ref(
            refs,
            f"knowledge:{knowledge_id}:{path}"
        )

    def add_if_meaningful(
        path: str,
        value: Any
    ) -> None:
        if meaningful_value(value):
            add(path)

    evidence_basis = knowledge.get(
        "evidence_basis",
        {}
    )

    if isinstance(evidence_basis, dict):
        add_if_meaningful(
            "evidence_basis.derivation_rationale",
            evidence_basis.get(
                "derivation_rationale"
            )
        )

        add_if_meaningful(
            "evidence_basis.limitations",
            evidence_basis.get(
                "limitations"
            )
        )

    statement = knowledge.get(
        "knowledge_statement",
        {}
    )

    if isinstance(statement, dict):
        statement_is_active = any(
            meaningful_value(
                statement.get(field_name)
            )
            for field_name in [
                "risk_principle",
                "testing_objective",
                "failure_relevance"
            ]
        )

        if statement_is_active:
            add("knowledge_statement")

        for field_name in [
            "risk_principle",
            "testing_objective",
            "failure_relevance"
        ]:
            add_if_meaningful(
                f"knowledge_statement.{field_name}",
                statement.get(field_name)
            )

    applicability = knowledge.get(
        "applicability",
        {}
    )

    if isinstance(applicability, dict):
        applicability_fields = [
            "candidate_family_tags",
            "applicability_conditions",
            "exclusion_conditions",
            "rationale"
        ]

        applicability_is_active = any(
            meaningful_value(
                applicability.get(field_name)
            )
            for field_name in applicability_fields
        )

        if applicability_is_active:
            add("applicability")

        add_if_meaningful(
            "applicability.candidate_family_tags",
            applicability.get(
                "candidate_family_tags"
            )
        )

        add_if_meaningful(
            "applicability.rationale",
            applicability.get("rationale")
        )

        for field_name in [
            "applicability_conditions",
            "exclusion_conditions"
        ]:
            items = applicability.get(
                field_name,
                []
            )

            if not isinstance(items, list):
                continue

            if items:
                add(
                    f"applicability.{field_name}"
                )

            for index, item in enumerate(
                items,
                start=1
            ):
                if not meaningful_value(item):
                    continue

                condition_id = None

                if isinstance(item, dict):
                    condition_id = item.get(
                        "condition_id"
                    )

                add(
                    f"applicability.{field_name}."
                    f"{condition_id or index}"
                )

    guidance = knowledge.get(
        "testing_guidance",
        {}
    )

    if isinstance(guidance, dict):
        guidance_fields = [
            "risk_dimensions",
            "exploration_goals",
            "oracle_guidance"
        ]

        guidance_is_active = any(
            meaningful_value(
                guidance.get(field_name)
            )
            for field_name in guidance_fields
        )

        if guidance_is_active:
            add("testing_guidance")

        add_if_meaningful(
            "testing_guidance.risk_dimensions",
            guidance.get("risk_dimensions")
        )

        goals = guidance.get(
            "exploration_goals",
            []
        )

        if isinstance(goals, list):
            if goals:
                add(
                    "testing_guidance."
                    "exploration_goals"
                )

            for index, goal in enumerate(
                goals,
                start=1
            ):
                if not meaningful_value(goal):
                    continue

                goal_id = None

                if isinstance(goal, dict):
                    goal_id = goal.get(
                        "goal_id"
                    )

                add(
                    "testing_guidance."
                    "exploration_goals."
                    f"{goal_id or index}"
                )

        oracle_guidance = guidance.get(
            "oracle_guidance",
            []
        )

        if isinstance(oracle_guidance, list):
            if oracle_guidance:
                add(
                    "testing_guidance."
                    "oracle_guidance"
                )

            for index, item in enumerate(
                oracle_guidance
            ):
                if meaningful_value(item):
                    add(
                        "testing_guidance."
                        f"oracle_guidance[{index}]"
                    )

    add_if_meaningful(
        "confidence",
        knowledge.get("confidence")
    )

    if not any(
        ref.startswith(
            f"knowledge:{knowledge_id}:"
            "knowledge_statement"
        )
        or ref.startswith(
            f"knowledge:{knowledge_id}:"
            "testing_guidance"
        )
        for ref in refs
    ):
        raise PipelineError(
            f"Knowledge {knowledge_id} has no "
            "addressable testing-principle or guidance "
            "evidence"
        )

    return sorted(refs)


def build_family_projection(
    family_context: dict[str, Any]
) -> dict[str, Any]:
    family = family_context["data"]

    projected_members = []

    for member in family.get("members", []):
        projected_members.append(
            {
                "pattern_id": member.get(
                    "pattern_id"
                ),
                "primary_api": member.get(
                    "primary_api"
                ),
                "membership_rationale": member.get(
                    "membership_rationale"
                ),
                "evidence_status": member.get(
                    "evidence_status"
                ),
                "confidence": member.get(
                    "confidence"
                )
            }
        )

    return {
        "metadata": {
            "family_id": family_context[
                "family_id"
            ],
            "canonical_name": family_context[
                "canonical_name"
            ],
            "framework": family_context[
                "framework"
            ]
        },
        "revision": family_context["revision"],
        "members": projected_members,
        "family_core": strip_evidence_refs(
            family.get("family_core")
        ),
        "shared_characteristics": (
            strip_evidence_refs(
                family.get(
                    "shared_characteristics"
                )
            )
        ),
        "applicability": strip_evidence_refs(
            family.get("applicability")
        ),
        "heterogeneity": strip_evidence_refs(
            family.get("heterogeneity")
        ),
        "support": strip_evidence_refs(
            family.get("support")
        ),
        "confidence": strip_evidence_refs(
            family.get("confidence")
        )
    }


def build_knowledge_projection(
    knowledge_context: dict[str, Any]
) -> dict[str, Any]:
    knowledge = knowledge_context["data"]

    metadata = knowledge.get(
        "metadata",
        {}
    )

    scope = knowledge.get(
        "scope",
        {}
    )

    evidence_basis = knowledge.get(
        "evidence_basis",
        {}
    )

    return {
        "knowledge_id": knowledge_context[
            "knowledge_id"
        ],
        "source_pattern_id": knowledge_context[
            "source_pattern_id"
        ],
        "primary_api": knowledge_context[
            "primary_api"
        ],
        "canonical_name": metadata.get(
            "canonical_name"
        ),
        "directly_supported_apis": scope.get(
            "directly_supported_apis",
            []
        ),
        "evidence_basis": {
            "derivation_rationale": (
                evidence_basis.get(
                    "derivation_rationale"
                )
            ),
            "limitations": evidence_basis.get(
                "limitations",
                []
            )
        },
        "knowledge_statement": (
            strip_evidence_refs(
                knowledge.get(
                    "knowledge_statement"
                )
            )
        ),
        "applicability": strip_evidence_refs(
            knowledge.get("applicability")
        ),
        "testing_guidance": (
            strip_evidence_refs(
                knowledge.get(
                    "testing_guidance"
                )
            )
        ),
        "confidence": strip_evidence_refs(
            knowledge.get("confidence")
        )
    }


def build_input_context(
    family_context: dict[str, Any],
    knowledge_contexts: list[
        dict[str, Any]
    ]
) -> dict[str, Any]:
    family_refs = build_family_evidence_refs(
        family_context
    )

    knowledge_inputs = []

    all_refs = list(family_refs)

    for knowledge_context in knowledge_contexts:
        refs = build_knowledge_evidence_refs(
            knowledge_context
        )

        for evidence_ref in refs:
            add_ref(all_refs, evidence_ref)

        knowledge_inputs.append(
            {
                "knowledge_id": (
                    knowledge_context[
                        "knowledge_id"
                    ]
                ),
                "knowledge_hash": (
                    knowledge_context[
                        "knowledge_hash"
                    ]
                ),
                "source_pattern_id": (
                    knowledge_context[
                        "source_pattern_id"
                    ]
                ),
                "primary_api": (
                    knowledge_context[
                        "primary_api"
                    ]
                ),
                "available_evidence_refs": refs,
                "knowledge": (
                    build_knowledge_projection(
                        knowledge_context
                    )
                )
            }
        )

    return {
        "pattern_family": {
            "family_id": family_context[
                "family_id"
            ],
            "family_revision": family_context[
                "revision"
            ],
            "family_hash": family_context[
                "family_hash"
            ],
            "available_evidence_refs": (
                family_refs
            ),
            "family": build_family_projection(
                family_context
            )
        },
        "member_knowledge": knowledge_inputs,
        "available_evidence_refs": sorted(
            all_refs
        )
    }


def build_prompt(
    contract: dict[str, Any],
    rules: str,
    input_context: dict[str, Any]
) -> str:
    return f"""
You are deriving one evidence-grounded General Knowledge candidate from one
validated Pattern Family and the API-specific Knowledge records associated
with all of its member Patterns.

The Pattern Family is the primary generalization source.
The member Knowledge records are supporting testing-guidance sources.

Follow the General Knowledge Extraction Contract and the
Pattern-Family-to-General-Knowledge Rules exactly.

Return JSON only.
Do not return Markdown, explanations, comments, or code fences.

====================
General Knowledge Extraction Contract
====================

{json.dumps(contract, indent=2, ensure_ascii=False)}

====================
Pattern-Family-to-General-Knowledge Rules
====================

{rules}

====================
Validated Input Context
====================

{json.dumps(input_context, indent=2, ensure_ascii=False)}
""".strip()


def call_deepseek(
    prompt: str,
    api_key: str,
    model: str,
    api_url: str
) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.2
    }

    try:
        response = requests.post(
            api_url,
            headers=headers,
            json=body,
            timeout=180
        )

        response.raise_for_status()
        result = response.json()

    except (
        requests.RequestException,
        ValueError
    ) as error:
        raise PipelineError(
            f"LLM request failed: {error}"
        ) from error

    try:
        content = result[
            "choices"
        ][0][
            "message"
        ][
            "content"
        ]
    except (
        KeyError,
        IndexError,
        TypeError
    ) as error:
        raise PipelineError(
            "LLM response does not contain message content"
        ) from error

    return require_string(
        content,
        "LLM response content"
    )


def extract_json(text: str) -> dict[str, Any]:
    text = text.strip()

    fenced = re.search(
        r"```(?:json)?\s*(.*?)```",
        text,
        flags=re.DOTALL | re.IGNORECASE
    )

    if fenced:
        text = fenced.group(1).strip()

    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise PipelineError(
            f"LLM response is not valid JSON: {error}"
        ) from error

    return require_dict(
        value,
        "LLM response"
    )


def validate_enum(
    value: Any,
    allowed_values: list[Any],
    label: str
) -> None:
    if value not in allowed_values:
        raise PipelineError(
            f"{label} has invalid value: {value}"
        )


def validate_evidence_refs(
    refs: Any,
    allowed_refs: set[str],
    label: str,
    required: bool,
    required_prefix: str | None = None
) -> list[str]:
    refs = require_list(refs, label)

    if required and not refs:
        raise PipelineError(
            f"{label} must not be empty"
        )

    seen = set()

    for index, evidence_ref in enumerate(refs):
        evidence_ref = require_string(
            evidence_ref,
            f"{label}[{index}]"
        )

        if evidence_ref in seen:
            raise PipelineError(
                f"{label} contains duplicate reference: "
                f"{evidence_ref}"
            )

        seen.add(evidence_ref)

        if evidence_ref not in allowed_refs:
            raise PipelineError(
                f"{label} contains unsupported reference: "
                f"{evidence_ref}"
            )

        if (
            required_prefix is not None
            and not evidence_ref.startswith(
                required_prefix
            )
        ):
            raise PipelineError(
                f"{label} contains a reference to the "
                "wrong source artifact"
            )

    return refs


def validate_condition_items(
    items: Any,
    label: str,
    allowed: dict[str, Any],
    allowed_refs: set[str],
    required: bool
) -> list[dict[str, Any]]:
    items = require_list(items, label)

    if required and not items:
        raise PipelineError(
            f"{label} must contain at least one item"
        )

    for index, item in enumerate(items):
        item_label = f"{label}[{index}]"

        item = validate_exact_keys(
            item,
            {
                "condition_kind",
                "statement",
                "evidence_status",
                "evidence_refs"
            },
            item_label
        )

        validate_enum(
            item["condition_kind"],
            allowed["condition_kind"],
            f"{item_label}.condition_kind"
        )

        require_string(
            item["statement"],
            f"{item_label}.statement"
        )

        validate_enum(
            item["evidence_status"],
            allowed["evidence_status"],
            f"{item_label}.evidence_status"
        )

        if item["evidence_status"] == "unknown":
            raise PipelineError(
                f"{item_label}.evidence_status cannot "
                "be unknown for an asserted condition"
            )

        validate_evidence_refs(
            item["evidence_refs"],
            allowed_refs,
            f"{item_label}.evidence_refs",
            required=True
        )

    return items


def validate_limitations(
    limitations: Any,
    allowed: dict[str, Any],
    allowed_refs: set[str]
) -> list[dict[str, Any]]:
    limitations = require_list(
        limitations,
        "evidence_basis.limitations"
    )

    for index, item in enumerate(limitations):
        label = (
            f"evidence_basis.limitations[{index}]"
        )

        item = validate_exact_keys(
            item,
            {
                "limitation_kind",
                "statement",
                "evidence_status",
                "evidence_refs"
            },
            label
        )

        validate_enum(
            item["limitation_kind"],
            allowed["limitation_kind"],
            f"{label}.limitation_kind"
        )

        require_string(
            item["statement"],
            f"{label}.statement"
        )

        validate_enum(
            item["evidence_status"],
            allowed["evidence_status"],
            f"{label}.evidence_status"
        )

        validate_evidence_refs(
            item["evidence_refs"],
            allowed_refs,
            f"{label}.evidence_refs",
            required=(
                item["evidence_status"]
                != "unknown"
            )
        )

    return limitations


def validate_exploration_goals(
    goals: Any,
    allowed: dict[str, Any],
    allowed_refs: set[str]
) -> list[dict[str, Any]]:
    goals = require_list(
        goals,
        "testing_guidance.exploration_goals"
    )

    if not goals:
        raise PipelineError(
            "At least one exploration goal is required "
            "for an accepted General Knowledge"
        )

    for index, goal in enumerate(goals):
        label = (
            "testing_guidance."
            f"exploration_goals[{index}]"
        )

        goal = validate_exact_keys(
            goal,
            {
                "target_dimension",
                "statement",
                "priority",
                "evidence_status",
                "evidence_refs"
            },
            label
        )

        validate_enum(
            goal["target_dimension"],
            allowed["risk_dimension"],
            f"{label}.target_dimension"
        )

        require_string(
            goal["statement"],
            f"{label}.statement"
        )

        validate_enum(
            goal["priority"],
            allowed["priority"],
            f"{label}.priority"
        )

        validate_enum(
            goal["evidence_status"],
            allowed["evidence_status"],
            f"{label}.evidence_status"
        )

        if goal["evidence_status"] == "unknown":
            raise PipelineError(
                f"{label}.evidence_status cannot be "
                "unknown for an asserted goal"
            )

        validate_evidence_refs(
            goal["evidence_refs"],
            allowed_refs,
            f"{label}.evidence_refs",
            required=True
        )

    return goals


def validate_oracle_guidance(
    items: Any,
    allowed: dict[str, Any],
    allowed_refs: set[str]
) -> list[dict[str, Any]]:
    items = require_list(
        items,
        "testing_guidance.oracle_guidance"
    )

    for index, item in enumerate(items):
        label = (
            "testing_guidance."
            f"oracle_guidance[{index}]"
        )

        item = validate_exact_keys(
            item,
            {
                "objective",
                "observation_kind",
                "evidence_status",
                "evidence_refs",
                "confidence"
            },
            label
        )

        require_string(
            item["objective"],
            f"{label}.objective"
        )

        validate_enum(
            item["observation_kind"],
            allowed["observation_kind"],
            f"{label}.observation_kind"
        )

        validate_enum(
            item["evidence_status"],
            allowed["evidence_status"],
            f"{label}.evidence_status"
        )

        if item["evidence_status"] == "unknown":
            raise PipelineError(
                f"{label}.evidence_status cannot be "
                "unknown for asserted Oracle guidance"
            )

        validate_evidence_refs(
            item["evidence_refs"],
            allowed_refs,
            f"{label}.evidence_refs",
            required=True
        )

        validate_enum(
            item["confidence"],
            allowed["confidence"],
            f"{label}.confidence"
        )

        if (
            item["observation_kind"]
            == "derived_oracle_candidate"
        ):
            if (
                item["evidence_status"]
                != "analyst_inferred"
            ):
                raise PipelineError(
                    f"{label}: derived_oracle_candidate "
                    "must use analyst_inferred"
                )

            if item["confidence"] == "high":
                raise PipelineError(
                    f"{label}: derived_oracle_candidate "
                    "cannot have high confidence"
                )

    return items


def collect_evidence_refs(
    value: Any
) -> list[str]:
    refs = []

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            evidence_refs = item.get(
                "evidence_refs"
            )

            if isinstance(evidence_refs, list):
                for evidence_ref in evidence_refs:
                    if (
                        isinstance(evidence_ref, str)
                        and evidence_ref not in refs
                    ):
                        refs.append(evidence_ref)

            for nested in item.values():
                visit(nested)

        elif isinstance(item, list):
            for nested in item:
                visit(nested)

    visit(value)

    return refs


def validate_general_candidate(
    candidate: Any,
    contract: dict[str, Any],
    family_context: dict[str, Any],
    knowledge_contexts: list[
        dict[str, Any]
    ],
    allowed_refs: set[str]
) -> dict[str, Any]:
    candidate = require_dict(
        candidate,
        "general_knowledge"
    )

    template = contract[
        "item_templates"
    ][
        "general_knowledge"
    ]

    validate_exact_keys(
        candidate,
        set(template.keys()),
        "general_knowledge"
    )

    empty_path = find_empty_string(candidate)

    if empty_path:
        raise PipelineError(
            f"Empty string is not allowed: {empty_path}"
        )

    allowed = contract["allowed_values"]

    canonical_name = require_string(
        candidate.get("canonical_name"),
        "general_knowledge.canonical_name"
    )

    if not re.fullmatch(
        r"[a-z][a-z0-9_]*",
        canonical_name
    ):
        raise PipelineError(
            "canonical_name must use lower_snake_case"
        )

    evidence_basis = validate_exact_keys(
        candidate.get("evidence_basis"),
        {
            "family_evidence_refs",
            "supporting_knowledge",
            "derivation_rationale",
            "limitations"
        },
        "evidence_basis"
    )

    family_prefix = (
        f"family:{family_context['family_id']}:"
    )

    family_evidence_refs = (
        validate_evidence_refs(
            evidence_basis[
                "family_evidence_refs"
            ],
            allowed_refs,
            "evidence_basis.family_evidence_refs",
            required=True,
            required_prefix=family_prefix
        )
    )

    semantic_family_prefixes = (
        f"{family_prefix}family_core",
        f"{family_prefix}shared_characteristics"
    )

    if not any(
        evidence_ref.startswith(
            semantic_family_prefixes
        )
        for evidence_ref
        in family_evidence_refs
    ):
        raise PipelineError(
            "family_evidence_refs must cite "
            "family_core or shared_characteristics; "
            "support or confidence alone is insufficient"
        )

    require_string(
        evidence_basis["derivation_rationale"],
        "evidence_basis.derivation_rationale"
    )

    validate_limitations(
        evidence_basis["limitations"],
        allowed,
        allowed_refs
    )

    supporting = require_list(
        evidence_basis["supporting_knowledge"],
        "evidence_basis.supporting_knowledge"
    )

    if len(supporting) < 2:
        raise PipelineError(
            "At least two supporting Knowledge records "
            "are required"
        )

    knowledge_by_id = {
        item["knowledge_id"]: item
        for item in knowledge_contexts
    }

    supporting_ids = set()
    supporting_apis = set()

    for index, item in enumerate(supporting):
        label = (
            "evidence_basis."
            f"supporting_knowledge[{index}]"
        )

        item = validate_exact_keys(
            item,
            {
                "knowledge_id",
                "evidence_refs"
            },
            label
        )

        knowledge_id = require_string(
            item["knowledge_id"],
            f"{label}.knowledge_id"
        )

        if knowledge_id not in knowledge_by_id:
            raise PipelineError(
                f"{label} references an unsupplied "
                f"Knowledge ID: {knowledge_id}"
            )

        if knowledge_id in supporting_ids:
            raise PipelineError(
                f"Duplicate supporting Knowledge ID: "
                f"{knowledge_id}"
            )

        supporting_ids.add(knowledge_id)
        supporting_apis.add(
            knowledge_by_id[
                knowledge_id
            ][
                "primary_api"
            ]
        )

        supporting_refs = validate_evidence_refs(
            item["evidence_refs"],
            allowed_refs,
            f"{label}.evidence_refs",
            required=True,
            required_prefix=(
                f"knowledge:{knowledge_id}:"
            )
        )

        semantic_knowledge_prefixes = (
            f"knowledge:{knowledge_id}:"
            "knowledge_statement",
            f"knowledge:{knowledge_id}:"
            "applicability",
            f"knowledge:{knowledge_id}:"
            "testing_guidance",
            f"knowledge:{knowledge_id}:"
            "evidence_basis.derivation_rationale"
        )

        if not any(
            evidence_ref.startswith(
                semantic_knowledge_prefixes
            )
            for evidence_ref in supporting_refs
        ):
            raise PipelineError(
                f"{label} must cite testing-principle, "
                "applicability, guidance, or derivation "
                "evidence; confidence alone is "
                "insufficient"
            )

    if len(supporting_apis) < 2:
        raise PipelineError(
            "Supporting Knowledge must represent at least "
            "two distinct APIs"
        )

    statement = validate_exact_keys(
        candidate.get("knowledge_statement"),
        {
            "risk_principle",
            "testing_objective",
            "failure_relevance",
            "evidence_status",
            "evidence_refs"
        },
        "knowledge_statement"
    )

    require_string(
        statement["risk_principle"],
        "knowledge_statement.risk_principle"
    )

    require_string(
        statement["testing_objective"],
        "knowledge_statement.testing_objective"
    )

    require_string_or_null(
        statement["failure_relevance"],
        "knowledge_statement.failure_relevance"
    )

    validate_enum(
        statement["evidence_status"],
        allowed["evidence_status"],
        "knowledge_statement.evidence_status"
    )

    if statement["evidence_status"] == "unknown":
        raise PipelineError(
            "Accepted knowledge_statement cannot use "
            "unknown evidence status"
        )

    statement_refs = validate_evidence_refs(
        statement["evidence_refs"],
        allowed_refs,
        "knowledge_statement.evidence_refs",
        required=True
    )

    if not any(
        ref.startswith(family_prefix)
        for ref in statement_refs
    ):
        raise PipelineError(
            "knowledge_statement must cite at least one "
            "Pattern Family reference"
        )

    applicability = validate_exact_keys(
        candidate.get("applicability"),
        {
            "retrieval_tags",
            "applicability_conditions",
            "exclusion_conditions",
            "rationale",
            "evidence_status",
            "evidence_refs"
        },
        "applicability"
    )

    retrieval_tags = require_list(
        applicability["retrieval_tags"],
        "applicability.retrieval_tags"
    )

    if not retrieval_tags:
        raise PipelineError(
            "At least one retrieval tag is required"
        )

    normalized_tags = []

    for index, tag in enumerate(retrieval_tags):
        tag = require_string(
            tag,
            f"applicability.retrieval_tags[{index}]"
        )

        if not re.fullmatch(
            r"[a-z][a-z0-9_]*",
            tag
        ):
            raise PipelineError(
                "retrieval_tags must use lower_snake_case"
            )

        normalized_tags.append(tag)

    if len(normalized_tags) != len(
        set(normalized_tags)
    ):
        raise PipelineError(
            "retrieval_tags must not contain duplicates"
        )

    validate_condition_items(
        applicability["applicability_conditions"],
        "applicability.applicability_conditions",
        allowed,
        allowed_refs,
        required=True
    )

    validate_condition_items(
        applicability["exclusion_conditions"],
        "applicability.exclusion_conditions",
        allowed,
        allowed_refs,
        required=False
    )

    require_string_or_null(
        applicability["rationale"],
        "applicability.rationale"
    )

    validate_enum(
        applicability["evidence_status"],
        allowed["evidence_status"],
        "applicability.evidence_status"
    )

    if applicability["evidence_status"] == "unknown":
        raise PipelineError(
            "Accepted Applicability cannot use unknown "
            "evidence status"
        )

    validate_evidence_refs(
        applicability["evidence_refs"],
        allowed_refs,
        "applicability.evidence_refs",
        required=True
    )

    guidance = validate_exact_keys(
        candidate.get("testing_guidance"),
        {
            "exploration_goals",
            "oracle_guidance"
        },
        "testing_guidance"
    )

    validate_exploration_goals(
        guidance["exploration_goals"],
        allowed,
        allowed_refs
    )

    validate_oracle_guidance(
        guidance["oracle_guidance"],
        allowed,
        allowed_refs
    )

    confidence = validate_exact_keys(
        candidate.get("confidence"),
        {
            "evidence_confidence",
            "abstraction_confidence",
            "applicability_confidence",
            "oracle_guidance_confidence",
            "generalization_confidence"
        },
        "confidence"
    )

    for key, value in confidence.items():
        validate_enum(
            value,
            allowed["confidence"],
            f"confidence.{key}"
        )

    if (
        statement["evidence_status"]
        == "analyst_inferred"
        and confidence[
            "abstraction_confidence"
        ] == "high"
    ):
        raise PipelineError(
            "abstraction_confidence cannot be high when "
            "the main statement is analyst_inferred"
        )

    if (
        applicability["evidence_status"]
        == "analyst_inferred"
        and confidence[
            "applicability_confidence"
        ] == "high"
    ):
        raise PipelineError(
            "applicability_confidence cannot be high when "
            "Applicability is analyst_inferred"
        )

    if (
        not guidance["oracle_guidance"]
        and confidence[
            "oracle_guidance_confidence"
        ] != "low"
    ):
        raise PipelineError(
            "oracle_guidance_confidence must be low when "
            "oracle_guidance is empty"
        )

    source_generalization = (
        family_context[
            "generalization_confidence"
        ]
    )

    if (
        CONFIDENCE_RANK[
            confidence[
                "generalization_confidence"
            ]
        ]
        > CONFIDENCE_RANK[
            source_generalization
        ]
    ):
        raise PipelineError(
            "generalization_confidence exceeds the source "
            "Pattern Family confidence"
        )

    all_candidate_refs = collect_evidence_refs(
        candidate
    )

    referenced_knowledge_ids = set()

    for evidence_ref in all_candidate_refs:
        if evidence_ref not in allowed_refs:
            raise PipelineError(
                f"Unsupported evidence reference: "
                f"{evidence_ref}"
            )

        if evidence_ref.startswith("knowledge:"):
            components = evidence_ref.split(
                ":",
                2
            )

            if len(components) != 3:
                raise PipelineError(
                    f"Malformed Knowledge evidence "
                    f"reference: {evidence_ref}"
                )

            referenced_knowledge_ids.add(
                components[1]
            )

        elif not evidence_ref.startswith(
            family_prefix
        ):
            raise PipelineError(
                "Direct Pattern or Report evidence "
                "references are not allowed"
            )

    if not referenced_knowledge_ids.issubset(
        supporting_ids
    ):
        missing = (
            referenced_knowledge_ids
            - supporting_ids
        )

        raise PipelineError(
            "Knowledge evidence is cited without a "
            "supporting_knowledge entry: "
            f"{sorted(missing)}"
        )

    return candidate


def validate_unresolved_issues(
    issues: Any,
    allowed_refs: set[str]
) -> list[dict[str, Any]]:
    issues = require_list(
        issues,
        "unresolved_issues"
    )

    for index, issue in enumerate(issues):
        label = f"unresolved_issues[{index}]"

        issue = validate_exact_keys(
            issue,
            {
                "issue",
                "evidence_refs",
                "required_action"
            },
            label
        )

        require_string(
            issue["issue"],
            f"{label}.issue"
        )

        require_string(
            issue["required_action"],
            f"{label}.required_action"
        )

        validate_evidence_refs(
            issue["evidence_refs"],
            allowed_refs,
            f"{label}.evidence_refs",
            required=False
        )

    return issues


def validate_response(
    response: dict[str, Any],
    contract: dict[str, Any],
    family_context: dict[str, Any],
    knowledge_contexts: list[
        dict[str, Any]
    ],
    allowed_refs: set[str]
) -> tuple[
    str,
    dict[str, Any] | None,
    list[dict[str, Any]]
]:
    validate_exact_keys(
        response,
        {
            "decision",
            "general_knowledge",
            "unresolved_issues"
        },
        "LLM response"
    )

    empty_path = find_empty_string(response)

    if empty_path:
        raise PipelineError(
            f"Empty string is not allowed: {empty_path}"
        )

    decision = response["decision"]

    validate_enum(
        decision,
        contract[
            "allowed_values"
        ][
            "decision"
        ],
        "decision"
    )

    issues = validate_unresolved_issues(
        response["unresolved_issues"],
        allowed_refs
    )

    if decision == "needs_revision":
        if response["general_knowledge"] is not None:
            raise PipelineError(
                "general_knowledge must be null for "
                "needs_revision"
            )

        if not issues:
            raise PipelineError(
                "needs_revision requires at least one "
                "unresolved issue"
            )

        return decision, None, issues

    if decision != "accept":
        raise PipelineError(
            f"Unsupported decision: {decision}"
        )

    if issues:
        raise PipelineError(
            "accept requires unresolved_issues to be empty"
        )

    candidate = validate_general_candidate(
        response["general_knowledge"],
        contract,
        family_context,
        knowledge_contexts,
        allowed_refs
    )

    return decision, candidate, issues


def call_llm_with_validation(
    prompt: str,
    api_key: str,
    model: str,
    api_url: str,
    max_attempts: int,
    contract: dict[str, Any],
    family_context: dict[str, Any],
    knowledge_contexts: list[
        dict[str, Any]
    ],
    allowed_refs: set[str]
) -> tuple[
    str,
    dict[str, Any] | None,
    list[dict[str, Any]]
]:
    errors = []

    for attempt in range(
        1,
        max_attempts + 1
    ):
        try:
            raw_response = call_deepseek(
                prompt=prompt,
                api_key=api_key,
                model=model,
                api_url=api_url
            )

            response = extract_json(
                raw_response
            )

            return validate_response(
                response=response,
                contract=contract,
                family_context=family_context,
                knowledge_contexts=(
                    knowledge_contexts
                ),
                allowed_refs=allowed_refs
            )

        except Exception as error:
            errors.append(
                f"attempt {attempt}: {error}"
            )

            print(
                f"[INVALID_RESPONSE] attempt "
                f"{attempt}/{max_attempts}: {error}"
            )

    raise PipelineError(
        "All LLM attempts failed validation: "
        + " | ".join(errors)
    )


def load_general_knowledge_snapshot(
    output_root: Path,
    framework: str
) -> dict[str, Any]:
    framework_dir = (
        output_root
        / slugify(framework)
    )

    by_id: dict[
        str,
        list[dict[str, Any]]
    ] = {}

    if not framework_dir.is_dir():
        return {
            "latest": {},
            "family_to_knowledge_id": {},
            "all_ids": set()
        }

    for path in sorted(
        framework_dir.glob("*/*.json")
    ):
        record = load_json(path)

        if (
            record.get("schema_version")
            != GENERAL_KNOWLEDGE_SCHEMA_VERSION
        ):
            raise PipelineError(
                f"Unsupported General Knowledge "
                f"schema in {path}"
            )

        metadata = require_dict(
            record.get("metadata"),
            f"{path}: metadata"
        )

        knowledge_id = require_string(
            metadata.get("knowledge_id"),
            f"{path}: knowledge_id"
        )

        if (
            metadata.get("knowledge_level")
            != "general"
        ):
            raise PipelineError(
                f"{path} is not General Knowledge"
            )

        revision_information = require_dict(
            record.get("revision_information"),
            f"{path}: revision_information"
        )

        revision = require_positive_integer(
            revision_information.get("revision"),
            f"{path}: revision"
        )

        expected_name = (
            f"{knowledge_id}_r{revision:03d}.json"
        )

        if path.name != expected_name:
            raise PipelineError(
                f"General Knowledge filename mismatch: "
                f"{path}"
            )

        derivation = require_dict(
            record.get("derivation_information"),
            f"{path}: derivation_information"
        )

        input_families = require_list(
            derivation.get(
                "input_pattern_families"
            ),
            f"{path}: input_pattern_families"
        )

        if len(input_families) != 1:
            raise PipelineError(
                f"{path} must reference exactly one "
                "Pattern Family"
            )

        family_id = require_string(
            input_families[0].get("family_id"),
            f"{path}: source family ID"
        )

        by_id.setdefault(
            knowledge_id,
            []
        ).append(
            {
                "data": record,
                "path": path,
                "knowledge_id": knowledge_id,
                "revision": revision,
                "knowledge_hash": (
                    canonical_json_hash(record)
                ),
                "family_id": family_id
            }
        )

    latest = {}

    for knowledge_id, revisions in by_id.items():
        revision_numbers = [
            item["revision"]
            for item in revisions
        ]

        if len(revision_numbers) != len(
            set(revision_numbers)
        ):
            raise PipelineError(
                f"Duplicate revision for General "
                f"Knowledge {knowledge_id}"
            )

        latest[knowledge_id] = max(
            revisions,
            key=lambda item: item["revision"]
        )

    family_to_knowledge_id = {}

    for knowledge_id, artifact in latest.items():
        family_id = artifact["family_id"]

        if family_id in family_to_knowledge_id:
            raise PipelineError(
                "Multiple General Knowledge identities "
                f"reference Family {family_id}"
            )

        family_to_knowledge_id[
            family_id
        ] = knowledge_id

    return {
        "latest": latest,
        "family_to_knowledge_id": (
            family_to_knowledge_id
        ),
        "all_ids": set(latest.keys())
    }


def current_input_knowledge_refs(
    knowledge_contexts: list[
        dict[str, Any]
    ]
) -> list[dict[str, Any]]:
    return [
        {
            "knowledge_id": item[
                "knowledge_id"
            ],
            "knowledge_hash": item[
                "knowledge_hash"
            ],
            "source_pattern_id": item[
                "source_pattern_id"
            ]
        }
        for item in sorted(
            knowledge_contexts,
            key=lambda value: value[
                "source_pattern_id"
            ]
        )
    ]


def source_inputs_are_unchanged(
    latest: dict[str, Any],
    family_context: dict[str, Any],
    knowledge_contexts: list[
        dict[str, Any]
    ],
    model: str
) -> bool:
    record = latest["data"]

    derivation = record.get(
        "derivation_information",
        {}
    )

    expected_family = {
        "family_id": family_context[
            "family_id"
        ],
        "family_revision": family_context[
            "revision"
        ],
        "family_hash": family_context[
            "family_hash"
        ]
    }

    actual_families = derivation.get(
        "input_pattern_families",
        []
    )

    if actual_families != [expected_family]:
        return False

    actual_knowledge = derivation.get(
        "input_knowledge",
        []
    )

    actual_knowledge = sorted(
        actual_knowledge,
        key=lambda item: item.get(
            "source_pattern_id",
            ""
        )
    )

    if actual_knowledge != (
        current_input_knowledge_refs(
            knowledge_contexts
        )
    ):
        return False

    return all(
        [
            derivation.get(
                "mapping_version"
            ) == MAPPING_VERSION,
            derivation.get(
                "prompt_version"
            ) == PROMPT_VERSION,
            derivation.get("model") == model
        ]
    )


def allocate_general_knowledge_id(
    snapshot: dict[str, Any],
    framework: str,
    canonical_name: str
) -> str:
    prefix = (
        f"gk_{framework_prefix(framework)}_"
    )

    maximum = 0

    for knowledge_id in snapshot["all_ids"]:
        if not knowledge_id.startswith(prefix):
            continue

        match = re.search(
            r"_g(\d+)$",
            knowledge_id
        )

        if match:
            maximum = max(
                maximum,
                int(match.group(1))
            )

    sequence = maximum + 1

    while True:
        knowledge_id = (
            f"{prefix}"
            f"{slugify(canonical_name)}_"
            f"g{sequence:03d}"
        )

        if knowledge_id not in snapshot["all_ids"]:
            return knowledge_id

        sequence += 1


def prepare_revision_identity(
    snapshot: dict[str, Any],
    family_context: dict[str, Any],
    canonical_name: str,
    force_reanalyze: bool
) -> dict[str, Any]:
    family_id = family_context["family_id"]

    existing_id = snapshot[
        "family_to_knowledge_id"
    ].get(family_id)

    if existing_id is None:
        return {
            "knowledge_id": (
                allocate_general_knowledge_id(
                    snapshot,
                    family_context["framework"],
                    canonical_name
                )
            ),
            "revision": 1,
            "previous_knowledge_hash": None,
            "change_type": "initial_creation",
            "change_summary": None
        }

    latest = snapshot["latest"][
        existing_id
    ]

    previous_record = latest["data"]

    previous_family = (
        previous_record[
            "derivation_information"
        ][
            "input_pattern_families"
        ][0]
    )

    source_family_changed = any(
        [
            previous_family.get(
                "family_revision"
            ) != family_context["revision"],
            previous_family.get(
                "family_hash"
            ) != family_context["family_hash"]
        ]
    )

    if source_family_changed:
        change_type = "source_family_update"
        change_summary = (
            "The source Pattern Family changed from "
            f"revision {previous_family.get('family_revision')} "
            f"to revision {family_context['revision']}."
        )

    else:
        change_type = "knowledge_reanalysis"

        if force_reanalyze:
            change_summary = (
                "The General Knowledge was explicitly "
                "reanalyzed using the current source inputs."
            )
        else:
            change_summary = (
                "Member Knowledge inputs or extraction "
                "configuration changed."
            )

    return {
        "knowledge_id": existing_id,
        "revision": latest["revision"] + 1,
        "previous_knowledge_hash": latest[
            "knowledge_hash"
        ],
        "change_type": change_type,
        "change_summary": change_summary
    }


def sort_unique_strings(
    values: list[str]
) -> list[str]:
    return sorted(set(values))


def normalize_evidence_ref_arrays(
    value: Any
) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if (
                key == "evidence_refs"
                and isinstance(item, list)
            ):
                value[key] = sort_unique_strings(
                    item
                )
            else:
                normalize_evidence_ref_arrays(
                    item
                )

    elif isinstance(value, list):
        for item in value:
            normalize_evidence_ref_arrays(
                item
            )


def add_local_ids(
    items: list[dict[str, Any]],
    id_field: str,
    prefix: str
) -> list[dict[str, Any]]:
    result = []

    for index, item in enumerate(
        items,
        start=1
    ):
        result.append(
            {
                id_field: f"{prefix}{index:02d}",
                **copy.deepcopy(item)
            }
        )

    return result


def materialize_general_knowledge(
    candidate: dict[str, Any],
    family_context: dict[str, Any],
    knowledge_contexts: list[
        dict[str, Any]
    ],
    identity: dict[str, Any],
    model: str
) -> dict[str, Any]:
    candidate = copy.deepcopy(candidate)

    normalize_evidence_ref_arrays(
        candidate
    )

    evidence_basis = candidate[
        "evidence_basis"
    ]

    all_candidate_refs = collect_evidence_refs(
        candidate
    )

    family_prefix = (
        f"family:{family_context['family_id']}:"
    )

    all_family_refs = {
        ref
        for ref in all_candidate_refs
        if ref.startswith(family_prefix)
    }

    family_refs = sorted(
        set(
            evidence_basis[
                "family_evidence_refs"
            ]
        )
        | all_family_refs
    )

    knowledge_refs_by_id: dict[
        str,
        set[str]
    ] = {}

    for evidence_ref in all_candidate_refs:
        if not evidence_ref.startswith(
            "knowledge:"
        ):
            continue

        components = evidence_ref.split(
            ":",
            2
        )

        if len(components) != 3:
            continue

        knowledge_refs_by_id.setdefault(
            components[1],
            set()
        ).add(evidence_ref)

    supporting_knowledge = []

    for item in sorted(
        evidence_basis[
            "supporting_knowledge"
        ],
        key=lambda value: value[
            "knowledge_id"
        ]
    ):
        knowledge_id = item["knowledge_id"]

        refs = (
            set(item["evidence_refs"])
            | knowledge_refs_by_id.get(
                knowledge_id,
                set()
            )
        )

        supporting_knowledge.append(
            {
                "knowledge_id": knowledge_id,
                "relation": "member_guidance",
                "evidence_refs": sorted(refs)
            }
        )

    limitations = sorted(
        evidence_basis["limitations"],
        key=lambda item: (
            item["limitation_kind"],
            item["statement"]
        )
    )

    applicability = copy.deepcopy(
        candidate["applicability"]
    )

    applicability["retrieval_tags"] = (
        sort_unique_strings(
            applicability["retrieval_tags"]
        )
    )

    applicability_conditions = sorted(
        applicability[
            "applicability_conditions"
        ],
        key=lambda item: (
            item["condition_kind"],
            item["statement"]
        )
    )

    exclusion_conditions = sorted(
        applicability[
            "exclusion_conditions"
        ],
        key=lambda item: (
            item["condition_kind"],
            item["statement"]
        )
    )

    applicability[
        "applicability_conditions"
    ] = add_local_ids(
        applicability_conditions,
        "condition_id",
        "ac_"
    )

    applicability[
        "exclusion_conditions"
    ] = add_local_ids(
        exclusion_conditions,
        "condition_id",
        "ec_"
    )

    guidance = copy.deepcopy(
        candidate["testing_guidance"]
    )

    priority_order = {
        "primary": 0,
        "secondary": 1
    }

    goals = sorted(
        guidance["exploration_goals"],
        key=lambda item: (
            priority_order[item["priority"]],
            item["target_dimension"],
            item["statement"]
        )
    )

    goals = add_local_ids(
        goals,
        "goal_id",
        "eg_"
    )

    oracle_guidance = sorted(
        guidance["oracle_guidance"],
        key=lambda item: (
            item["observation_kind"],
            item["objective"]
        )
    )

    risk_dimensions = sorted(
        {
            goal["target_dimension"]
            for goal in goals
        }
    )

    generated_at = datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )

    final_record = {
        "schema_version": (
            GENERAL_KNOWLEDGE_SCHEMA_VERSION
        ),

        "metadata": {
            "knowledge_id": identity[
                "knowledge_id"
            ],
            "canonical_name": candidate[
                "canonical_name"
            ],
            "knowledge_level": "general"
        },

        "revision_information": {
            "revision": identity["revision"],
            "previous_knowledge_hash": (
                identity[
                    "previous_knowledge_hash"
                ]
            ),
            "change_type": identity[
                "change_type"
            ],
            "change_summary": identity[
                "change_summary"
            ]
        },

        "derivation_information": {
            "method": "llm_assisted",
            "mapping_version": MAPPING_VERSION,
            "prompt_version": PROMPT_VERSION,
            "model": model,
            "input_pattern_families": [
                {
                    "family_id": family_context[
                        "family_id"
                    ],
                    "family_revision": (
                        family_context[
                            "revision"
                        ]
                    ),
                    "family_hash": (
                        family_context[
                            "family_hash"
                        ]
                    )
                }
            ],
            "input_knowledge": (
                current_input_knowledge_refs(
                    knowledge_contexts
                )
            ),
            "generated_at": generated_at,
            "validation_status": (
                "automatically_validated"
            )
        },

        "evidence_basis": {
            "supporting_families": [
                {
                    "family_id": family_context[
                        "family_id"
                    ],
                    "relation": (
                        "direct_generalization_basis"
                    ),
                    "evidence_refs": family_refs
                }
            ],
            "supporting_knowledge": (
                supporting_knowledge
            ),
            "derivation_rationale": (
                evidence_basis[
                    "derivation_rationale"
                ]
            ),
            "limitations": add_local_ids(
                limitations,
                "limitation_id",
                "lm_"
            )
        },

        "review": {
            "reviewer": None,
            "reviewed_at": None,
            "review_notes": []
        },

        "scope": {
            "framework": family_context[
                "framework"
            ],
            "directly_supported_apis": (
                family_context[
                    "member_apis"
                ]
            )
        },

        "knowledge_statement": copy.deepcopy(
            candidate["knowledge_statement"]
        ),

        "applicability": applicability,

        "testing_guidance": {
            "risk_dimensions": risk_dimensions,
            "exploration_goals": goals,
            "oracle_guidance": oracle_guidance
        },

        "support": {
            "source_family_support_tier": (
                family_context[
                    "support_tier"
                ]
            )
        },

        "confidence": copy.deepcopy(
            candidate["confidence"]
        )
    }

    normalize_evidence_ref_arrays(
        final_record
    )

    return final_record


def validate_final_record(
    record: dict[str, Any],
    family_context: dict[str, Any],
    knowledge_contexts: list[
        dict[str, Any]
    ]
) -> None:
    validate_exact_keys(
        record,
        {
            "schema_version",
            "metadata",
            "revision_information",
            "derivation_information",
            "evidence_basis",
            "review",
            "scope",
            "knowledge_statement",
            "applicability",
            "testing_guidance",
            "support",
            "confidence"
        },
        "Final General Knowledge"
    )

    if (
        record["schema_version"]
        != GENERAL_KNOWLEDGE_SCHEMA_VERSION
    ):
        raise PipelineError(
            "Final General Knowledge schema version "
            "is incorrect"
        )

    if (
        record["metadata"]["knowledge_level"]
        != "general"
    ):
        raise PipelineError(
            "Final Knowledge level must be general"
        )

    empty_path = find_empty_string(record)

    if empty_path:
        raise PipelineError(
            f"Final record contains an empty string: "
            f"{empty_path}"
        )

    revision = record[
        "revision_information"
    ][
        "revision"
    ]

    previous_hash = record[
        "revision_information"
    ][
        "previous_knowledge_hash"
    ]

    change_type = record[
        "revision_information"
    ][
        "change_type"
    ]

    if revision == 1:
        if previous_hash is not None:
            raise PipelineError(
                "Initial revision must not have a "
                "previous Knowledge hash"
            )

        if change_type != "initial_creation":
            raise PipelineError(
                "Initial revision must use "
                "initial_creation"
            )
    else:
        require_string(
            previous_hash,
            "previous_knowledge_hash"
        )

        if change_type not in {
            "source_family_update",
            "knowledge_reanalysis"
        }:
            raise PipelineError(
                "Later revision uses an invalid "
                "change_type"
            )

        require_string(
            record[
                "revision_information"
            ][
                "change_summary"
            ],
            "change_summary"
        )

    input_families = record[
        "derivation_information"
    ][
        "input_pattern_families"
    ]

    if len(input_families) != 1:
        raise PipelineError(
            "Final record must reference exactly one "
            "Pattern Family"
        )

    if input_families[0] != {
        "family_id": family_context["family_id"],
        "family_revision": family_context["revision"],
        "family_hash": family_context["family_hash"]
    }:
        raise PipelineError(
            "Final source Family reference is incorrect"
        )

    expected_knowledge = (
        current_input_knowledge_refs(
            knowledge_contexts
        )
    )

    if (
        record["derivation_information"][
            "input_knowledge"
        ]
        != expected_knowledge
    ):
        raise PipelineError(
            "Final input Knowledge references are incorrect"
        )

    if (
        record["scope"]["directly_supported_apis"]
        != family_context["member_apis"]
    ):
        raise PipelineError(
            "Final directly_supported_apis are incorrect"
        )

    if (
        record["support"][
            "source_family_support_tier"
        ]
        != family_context["support_tier"]
    ):
        raise PipelineError(
            "Final source Family support tier is incorrect"
        )

    goals = record[
        "testing_guidance"
    ][
        "exploration_goals"
    ]

    expected_dimensions = sorted(
        {
            goal["target_dimension"]
            for goal in goals
        }
    )

    if (
        record["testing_guidance"][
            "risk_dimensions"
        ]
        != expected_dimensions
    ):
        raise PipelineError(
            "Final risk_dimensions are incorrect"
        )

    for index, limitation in enumerate(
        record["evidence_basis"][
            "limitations"
        ],
        start=1
    ):
        if limitation.get(
            "limitation_id"
        ) != f"lm_{index:02d}":
            raise PipelineError(
                "Final limitation IDs are incorrect"
            )

    for field_name, prefix in [
        ("applicability_conditions", "ac_"),
        ("exclusion_conditions", "ec_")
    ]:
        for index, condition in enumerate(
            record["applicability"][
                field_name
            ],
            start=1
        ):
            if condition.get(
                "condition_id"
            ) != f"{prefix}{index:02d}":
                raise PipelineError(
                    f"Final {field_name} IDs are incorrect"
                )

    for index, goal in enumerate(
        goals,
        start=1
    ):
        if goal.get(
            "goal_id"
        ) != f"eg_{index:02d}":
            raise PipelineError(
                "Final exploration-goal IDs are incorrect"
            )


def output_path_for_record(
    output_root: Path,
    framework: str,
    knowledge_id: str,
    revision: int
) -> Path:
    return (
        output_root
        / slugify(framework)
        / knowledge_id
        / (
            f"{knowledge_id}_"
            f"r{revision:03d}.json"
        )
    )


def write_new_json(
    path: Path,
    value: dict[str, Any]
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    try:
        with path.open(
            "x",
            encoding="utf-8"
        ) as file:
            json.dump(
                value,
                file,
                indent=2,
                ensure_ascii=False
            )

            file.write("\n")

    except FileExistsError as error:
        raise PipelineError(
            f"Refusing to overwrite existing file: {path}"
        ) from error


def run(args: argparse.Namespace) -> int:
    contract = load_json(CONTRACT_FILE)
    rules = load_text(RULE_FILE)

    validate_configuration(
        contract,
        rules
    )

    framework = slugify(
        require_string(
            args.framework,
            "--framework"
        )
    )

    family_id = validate_safe_identifier(
        args.family_id,
        "--family-id"
    )

    family_root = resolve_project_path(
        args.family_root
    )

    knowledge_root = resolve_project_path(
        args.knowledge_root
    )

    output_root = resolve_project_path(
        args.output
    )

    family_path = find_latest_family_file(
        family_root=family_root,
        framework=framework,
        family_id=family_id
    )

    family = load_json(family_path)

    family_context = validate_pattern_family(
        family=family,
        family_path=family_path,
        expected_framework=framework,
        expected_family_id=family_id
    )

    print(
        f"[FAMILY] {family_id} "
        f"revision={family_context['revision']}"
    )

    knowledge_index = (
        load_api_knowledge_index(
            knowledge_root
        )
    )

    knowledge_contexts = (
        resolve_member_knowledge(
            family_context,
            knowledge_index
        )
    )

    print(
        f"[KNOWLEDGE] resolved "
        f"{len(knowledge_contexts)} member records"
    )

    snapshot = (
        load_general_knowledge_snapshot(
            output_root,
            framework
        )
    )

    existing_id = snapshot[
        "family_to_knowledge_id"
    ].get(family_id)

    if existing_id is not None:
        latest = snapshot["latest"][
            existing_id
        ]

        if (
            not args.force_reanalyze
            and source_inputs_are_unchanged(
                latest=latest,
                family_context=family_context,
                knowledge_contexts=(
                    knowledge_contexts
                ),
                model=args.model
            )
        ):
            print(
                f"[SKIP] Existing General Knowledge "
                f"{existing_id} revision "
                f"{latest['revision']} already uses the "
                "same source inputs and extraction "
                "configuration."
            )

            return 0

    input_context = build_input_context(
        family_context,
        knowledge_contexts
    )

    allowed_refs = set(
        input_context[
            "available_evidence_refs"
        ]
    )

    prompt = build_prompt(
        contract=contract,
        rules=rules,
        input_context=input_context
    )

    estimated_prompt_tokens = max(
        1,
        (len(prompt) + 3) // 4
    )

    print(
        f"[PROMPT] characters={len(prompt)} "
        f"estimated_tokens={estimated_prompt_tokens}"
    )

    decision, candidate, issues = (
        call_llm_with_validation(
            prompt=prompt,
            api_key=args.api_key,
            model=args.model,
            api_url=args.api_url,
            max_attempts=args.max_attempts,
            contract=contract,
            family_context=family_context,
            knowledge_contexts=(
                knowledge_contexts
            ),
            allowed_refs=allowed_refs
        )
    )

    if decision == "needs_revision":
        print(
            "[NEEDS_REVISION] No General Knowledge "
            "record was materialized."
        )

        print(
            json.dumps(
                {
                    "family_id": family_id,
                    "family_revision": (
                        family_context["revision"]
                    ),
                    "unresolved_issues": issues
                },
                indent=2,
                ensure_ascii=False
            )
        )

        return 2

    if candidate is None:
        raise PipelineError(
            "Accept decision did not contain a candidate"
        )

    identity = prepare_revision_identity(
        snapshot=snapshot,
        family_context=family_context,
        canonical_name=candidate[
            "canonical_name"
        ],
        force_reanalyze=(
            args.force_reanalyze
        )
    )

    final_record = (
        materialize_general_knowledge(
            candidate=candidate,
            family_context=family_context,
            knowledge_contexts=(
                knowledge_contexts
            ),
            identity=identity,
            model=args.model
        )
    )

    validate_final_record(
        final_record,
        family_context,
        knowledge_contexts
    )

    output_path = output_path_for_record(
        output_root=output_root,
        framework=framework,
        knowledge_id=identity[
            "knowledge_id"
        ],
        revision=identity["revision"]
    )

    if args.dry_run:
        print(
            "[DRY_RUN] Valid General Knowledge "
            f"{identity['knowledge_id']} "
            f"revision={identity['revision']}"
        )

        print(
            json.dumps(
                final_record,
                indent=2,
                ensure_ascii=False
            )
        )

        return 0

    write_new_json(
        output_path,
        final_record
    )

    print(f"[WRITE] {output_path}")

    return 0


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build one General Knowledge JSON revision "
            "from one validated Pattern Family and its "
            "member API-specific Knowledge records."
        )
    )

    parser.add_argument(
        "--framework",
        default="pytorch",
        help=(
            "Framework name. Defaults to pytorch."
        )
    )

    parser.add_argument(
        "--family-id",
        required=True,
        help=(
            "Stable Pattern Family ID, for example "
            "pf_pt_storage_layout_backend_f001."
        )
    )

    parser.add_argument(
        "--family-root",
        default=str(DEFAULT_FAMILY_ROOT),
        help=(
            "Pattern Family root directory. Defaults to "
            "EXP006/pattern_families."
        )
    )

    parser.add_argument(
        "--knowledge-root",
        default=str(DEFAULT_KNOWLEDGE_ROOT),
        help=(
            "API-specific Knowledge root directory. "
            "Defaults to EXP006/knowledge_base."
        )
    )

    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_ROOT),
        help=(
            "General Knowledge output root. Defaults to "
            "EXP006/general_knowledge."
        )
    )

    parser.add_argument(
        "--api-key",
        "--api_key",
        dest="api_key",
        default=os.environ.get(
            "DEEPSEEK_API_KEY"
        ),
        help=(
            "DeepSeek API key. Defaults to the "
            "DEEPSEEK_API_KEY environment variable."
        )
    )

    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="DeepSeek model name."
    )

    parser.add_argument(
        "--api-url",
        default=os.environ.get(
            "DEEPSEEK_API_URL",
            DEFAULT_API_URL
        ),
        help=(
            "DeepSeek chat-completions endpoint."
        )
    )

    parser.add_argument(
        "--max-attempts",
        type=int,
        default=2,
        help=(
            "Maximum attempts for invalid or failed LLM "
            "responses. Defaults to 2."
        )
    )

    parser.add_argument(
        "--force-reanalyze",
        action="store_true",
        help=(
            "Run the LLM again and create a new revision "
            "even when the current source inputs and "
            "configuration are unchanged."
        )
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Call the LLM, validate and materialize the "
            "record in memory, but do not write a file."
        )
    )

    return parser


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()

    if args.max_attempts < 1:
        parser.error(
            "--max-attempts must be at least 1"
        )

    if not args.api_key:
        parser.error(
            "Missing DeepSeek API key. Set "
            "DEEPSEEK_API_KEY or pass --api-key."
        )

    try:
        return run(args)

    except PipelineError as error:
        print(
            f"[FAILED] {error}",
            file=sys.stderr
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(main())