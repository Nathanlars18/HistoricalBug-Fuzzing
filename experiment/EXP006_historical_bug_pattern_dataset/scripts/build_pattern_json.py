import argparse
import copy
import hashlib
import json
import os
import re
from pathlib import Path
from datetime import datetime, timezone

import requests
import build_bug_report_json as report_builder


BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

EXP006_DIR = os.path.dirname(BASE_DIR)

BUG_REPORT_DIR = os.path.join(
    EXP006_DIR,
    "bug_reports"
)

DEFAULT_OUTPUT_DIR = os.path.join(
    EXP006_DIR,
    "bug_patterns",
    "v4"
)

CONTRACT_FILE = os.path.join(
    EXP006_DIR,
    "schemas",
    "pattern_extraction_contract.json"
)

MAPPING_FILE = os.path.join(
    EXP006_DIR,
    "schemas",
    "report_to_pattern_mapping.md"
)

SCHEMA_VERSION = "4.0"
MAPPING_VERSION = "4.2"
PROMPT_VERSION = "pattern_extract_v4_2"

DEFAULT_MODEL = "deepseek-v4-pro"

DEFAULT_API_URL = (
    "https://api.deepseek.com/chat/completions"
)

MAX_LLM_ATTEMPTS = 3
MAX_PROMPT_CHARS = 150000

CANDIDATE_KEYS = {
    "canonical_name",
    "provenance",
    "scope",
    "historical_conditions",
    "defect_mechanism",
    "observed_failure"
}

FORBIDDEN_FIELD_NAMES = {
    "harness_strategy",
    "harnessspec",
    "harness_spec",
    "strategy_primitive",
    "strategy_primitives",
    "harness_code",
    "generated_code",
    "code"
}



def load_text(path):
    with open(path, "r", encoding="utf-8") as file:
        return file.read()


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def require_dict(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")


def require_list(value, label):
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")


def require_string(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")


def validate_exact_keys(value, expected_keys, label):
    require_dict(value, label)

    actual_keys = set(value.keys())

    missing = expected_keys - actual_keys
    extra = actual_keys - expected_keys

    if missing:
        raise ValueError(
            f"{label} is missing keys: {sorted(missing)}"
        )

    if extra:
        raise ValueError(
            f"{label} has unsupported keys: {sorted(extra)}"
        )


def slugify(value):
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


def canonical_json_hash(value):
    serialized = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":")
    )

    return "sha256:" + hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()


def framework_prefix(framework):
    mapping = {
        "pytorch": "pt",
        "tensorflow": "tf"
    }

    normalized = slugify(framework)

    return mapping.get(
        normalized,
        normalized or "dl"
    )


def call_deepseek(prompt, api_key, model, api_url):
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

    response = requests.post(
        api_url,
        headers=headers,
        json=body,
        timeout=120
    )

    response.raise_for_status()

    result = response.json()

    return result["choices"][0]["message"]["content"]


def extract_json(text):
    text = text.strip()

    fenced = re.search(
        r"```(?:json)?\s*(.*?)```",
        text,
        flags=re.DOTALL | re.IGNORECASE
    )

    if fenced:
        text = fenced.group(1).strip()

    return json.loads(text)


def deep_normalize(value):
    if isinstance(value, str):
        value = value.strip()
        return value if value else None

    if isinstance(value, list):
        normalized_items = []

        for item in value:
            normalized_item = deep_normalize(item)

            if normalized_item not in (None, "", [], {}):
                normalized_items.append(normalized_item)

        return normalized_items

    if isinstance(value, dict):
        return {
            key: deep_normalize(item)
            for key, item in value.items()
        }

    return value


def normalize_candidate(candidate):
    candidate = deep_normalize(candidate)

    require_dict(candidate, "Pattern candidate")

    return candidate


def contains_forbidden_key(value, path=""):
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = slugify(key)

            current_path = (
                f"{path}.{key}"
                if path
                else key
            )

            if normalized_key in FORBIDDEN_FIELD_NAMES:
                return current_path

            nested_path = contains_forbidden_key(
                item,
                current_path
            )

            if nested_path:
                return nested_path

    elif isinstance(value, list):
        for index, item in enumerate(value):
            nested_path = contains_forbidden_key(
                item,
                f"{path}[{index}]"
            )

            if nested_path:
                return nested_path

    return None


def find_empty_string(value, path=""):
    if isinstance(value, str) and not value.strip():
        return path or "root"

    if isinstance(value, dict):
        for key, item in value.items():
            current_path = (
                f"{path}.{key}"
                if path
                else key
            )

            result = find_empty_string(
                item,
                current_path
            )

            if result:
                return result

    if isinstance(value, list):
        for index, item in enumerate(value):
            result = find_empty_string(
                item,
                f"{path}[{index}]"
            )

            if result:
                return result

    return None


def get_report_id(report, fallback_report_id):
    identity = report.get("identity", {})
    if isinstance(identity, dict) and identity.get("report_id"):
        return identity["report_id"]
    return fallback_report_id


def get_framework(report, fallback_framework="pytorch"):
    identity = report.get("identity", {})
    if isinstance(identity, dict) and identity.get("framework"):
        return identity["framework"]
    return fallback_framework


def report_supports_api(report, selected_api):
    scope = report.get("scope_assertions", {})
    assertions = scope.get("api_assertions", []) if isinstance(scope, dict) else []
    selected = selected_api.casefold()
    return any(
        isinstance(item, dict)
        and str(item.get("api_name", "")).casefold() == selected
        and item.get("relation") == "affected"
        for item in assertions
    )


def latest_report_records():
    """Select latest identity/revision before API or approval filtering. Fail closed."""
    latest = {}
    seen = set()
    for path in sorted(Path(BUG_REPORT_DIR).rglob("revision_*.json")):
        try:
            report = load_json(str(path))
            report_id = report["identity"]["report_id"]
            revision = report["revision_information"]["revision_number"]
            if not isinstance(report_id, str) or not report_id or type(revision) is not int or revision < 1:
                raise ValueError("Invalid Report identity/revision")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"Cannot select latest Report safely: {path}: {exc}") from exc
        previous = latest.get(report_id)
        if (report_id, revision) in seen:
            raise ValueError(f"Duplicate Report identity/revision: {report_id} r{revision}")
        seen.add((report_id, revision))
        if previous is None or revision > previous[0]:
            latest[report_id] = (revision, path, report)
    return [latest[key] for key in sorted(latest)]


def latest_report_paths_for_api(api):
    return [path for _, path, report in latest_report_records() if report_supports_api(report, api)]


def build_report_context(report, fallback_report_id, selected_api):
    report_builder.validate_report(report)
    review = report["review"]
    if review["validation_status"] != "passed":
        raise ValueError("Report must be validation-passed")
    if review["human_review_status"] == "rejected":
        raise ValueError("Human-rejected Report must not enter Pattern extraction")
    if not report_supports_api(report, selected_api):
        raise ValueError("Selected API is not affected in this Report revision")
    report_id = get_report_id(report, fallback_report_id)
    framework = get_framework(report)
    evidence_items = report.get("evidence_items", [])
    if not isinstance(evidence_items, list):
        raise ValueError("Report evidence_items must be an array")
    evidence_by_id = {}
    for item in evidence_items:
        if not isinstance(item, dict) or not item.get("evidence_id"):
            raise ValueError("Every evidence item must contain evidence_id")
        evidence_id = item["evidence_id"]
        if evidence_id in evidence_by_id:
            raise ValueError(f"Duplicate Report evidence_id: {evidence_id}")
        evidence_by_id[evidence_id] = item
    available_evidence_refs = [item["evidence_id"] for item in evidence_items]
    if not available_evidence_refs:
        raise ValueError("Report has no addressable source evidence")
    artifacts = {a["artifact_id"]: a for a in report["source_bundle"]["source_artifacts"]}
    by_id = {}
    for evidence_id in available_evidence_refs:
        item = evidence_by_id[evidence_id]
        artifact = artifacts.get(item["source_artifact_ref"])
        if artifact is None:
            raise ValueError(f"Evidence references an unknown source artifact: {evidence_id}")
        locator = {"artifact_path": artifact["local_path"], **item["locator"]}
        _, content = report_builder.resolve_locator(locator, report_builder.PROJECT_ROOT)
        by_id[evidence_id] = {
            "evidence_id": evidence_id,
            "artifact_role": artifact["artifact_role"],
            "attribution": {"actor": None, "actor_role": "unknown"},
            "content": content,
        }
    context = {
        "report_id": report_id,
        "report_revision": report["revision_information"]["revision_number"],
        "framework": framework,
        "selected_api": selected_api,
        "available_evidence_refs": available_evidence_refs,
        "report": report,
        "resolved_evidence": [by_id[ref] for ref in available_evidence_refs],
    }
    if len(json.dumps(context, ensure_ascii=False)) > MAX_PROMPT_CHARS:
        raise ValueError("Report evidence exceeds context budget; do not silently truncate")
    return context


def build_prompt(report_context, contract, mapping):
    return f"""
You are extracting evidence-grounded API-specific Bug Patterns
from one structured historical Bug Report.

Follow the Report-to-Pattern Mapping Specification and the
Pattern Extraction Contract exactly.

Return JSON only.
Do not output Markdown, explanations, or code fences.

====================
Pattern Extraction Contract
====================

{json.dumps(contract, indent=2, ensure_ascii=False)}

====================
Report-to-Pattern Mapping Specification
====================

{mapping}

====================
Input Report Context
====================

{json.dumps(report_context, indent=2, ensure_ascii=False)}
"""


def build_repair_prompt(base_prompt, previous_response, validation_error):
    return f"""
{base_prompt}

====================
Previous Response Repair
====================

The previous response failed deterministic validation:
{validation_error}

Return a complete corrected JSON response, not a patch.
Preserve only evidence-supported content. Do not invent missing values.
When an optional object cannot be completed from evidence, return null.

Previous response:
{previous_response}
"""


def validate_enum(value, allowed_values, label):
    if value not in allowed_values:
        raise ValueError(
            f"{label} has invalid value: {value}"
        )


def validate_string_list(value, label):
    require_list(value, label)

    for index, item in enumerate(value):
        require_string(
            item,
            f"{label}[{index}]"
        )


def validate_evidence_refs(
    evidence_refs,
    allowed_evidence_refs,
    label,
    required
):
    require_list(evidence_refs, label)

    if required and not evidence_refs:
        raise ValueError(
            f"{label} must not be empty"
        )

    for evidence_ref in evidence_refs:
        require_string(
            evidence_ref,
            label
        )

        if evidence_ref not in allowed_evidence_refs:
            raise ValueError(
                f"{label} contains unsupported reference: "
                f"{evidence_ref}"
            )


def semantic_evidence_refs(candidate):
    """Return the exact evidence union used by semantic Pattern fields."""
    refs = []

    def collect(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "evidence_refs":
                    validate_string_list(item, "evidence_refs")
                    refs.extend(item)
                else:
                    collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    for field in (
        "historical_conditions",
        "defect_mechanism",
        "observed_failure",
    ):
        collect(candidate.get(field))

    return sorted(set(refs))


def validate_response_envelope(response):
    validate_exact_keys(
        response,
        {"patterns"},
        "LLM response"
    )

    patterns = response["patterns"]

    require_list(patterns, "LLM response.patterns")

    if not patterns:
        raise ValueError(
            "LLM response.patterns must not be empty"
        )


def validate_candidate(candidate, report_context, contract):
    validate_exact_keys(candidate, CANDIDATE_KEYS, "Pattern candidate")

    forbidden_path = contains_forbidden_key(candidate)
    if forbidden_path:
        raise ValueError(f"Forbidden field detected: {forbidden_path}")

    empty_string_path = find_empty_string(candidate)
    if empty_string_path:
        raise ValueError(f"Empty string is not allowed: {empty_string_path}")

    vocabularies = contract["controlled_vocabularies"]
    allowed_refs = set(report_context["available_evidence_refs"])

    require_string(candidate["canonical_name"], "canonical_name")
    if not re.fullmatch(r"[a-z][a-z0-9_]*", candidate["canonical_name"]):
        raise ValueError("canonical_name must use lower_snake_case")

    provenance = candidate["provenance"]
    validate_exact_keys(
        provenance,
        {"source_report", "abstraction_rationale", "unresolved_information"},
        "provenance",
    )
    require_string(
        provenance["abstraction_rationale"],
        "provenance.abstraction_rationale",
    )
    validate_string_list(
        provenance["unresolved_information"],
        "provenance.unresolved_information",
    )

    source_report = provenance["source_report"]
    validate_exact_keys(
        source_report,
        {"report_id"},
        "provenance.source_report",
    )
    if source_report["report_id"] != report_context["report_id"]:
        raise ValueError("provenance.source_report.report_id must match the input Report")

    scope = candidate["scope"]
    validate_exact_keys(scope, {"target_api"}, "scope")
    require_string(scope["target_api"], "scope.target_api")
    if scope["target_api"] != report_context["selected_api"]:
        raise ValueError("scope.target_api must match the selected API exactly")

    conditions = candidate["historical_conditions"]
    require_list(conditions, "historical_conditions")
    for index, condition in enumerate(conditions):
        label = f"historical_conditions[{index}]"
        validate_exact_keys(
            condition,
            {"statement", "necessity", "evidence_status", "evidence_refs"},
            label,
        )
        require_string(condition["statement"], f"{label}.statement")
        validate_enum(
            condition["necessity"],
            vocabularies["condition_necessity"],
            f"{label}.necessity",
        )
        validate_enum(
            condition["evidence_status"],
            vocabularies["evidence_status"],
            f"{label}.evidence_status",
        )
        validate_evidence_refs(
            condition["evidence_refs"],
            allowed_refs,
            f"{label}.evidence_refs",
            required=True,
        )

    mechanism = candidate["defect_mechanism"]
    if mechanism is not None:
        validate_exact_keys(
            mechanism,
            {"description", "root_cause_category", "evidence_status", "evidence_refs"},
            "defect_mechanism",
        )
        require_string(mechanism["description"], "defect_mechanism.description")
        category = mechanism["root_cause_category"]
        if category is not None:
            validate_enum(
                category,
                vocabularies["root_cause_categories"],
                "defect_mechanism.root_cause_category",
            )
        validate_enum(
            mechanism["evidence_status"],
            vocabularies["evidence_status"],
            "defect_mechanism.evidence_status",
        )
        validate_evidence_refs(
            mechanism["evidence_refs"],
            allowed_refs,
            "defect_mechanism.evidence_refs",
            required=True,
        )

    failure = candidate["observed_failure"]
    validate_exact_keys(
        failure,
        {
            "description",
            "symptom_category",
            "evidence_status",
            "evidence_refs",
            "historical_observations",
        },
        "observed_failure",
    )
    require_string(failure["description"], "observed_failure.description")
    category = failure["symptom_category"]
    if category is not None:
        validate_enum(
            category,
            vocabularies["symptom_categories"],
            "observed_failure.symptom_category",
        )
    validate_enum(
        failure["evidence_status"],
        vocabularies["evidence_status"],
        "observed_failure.evidence_status",
    )
    validate_evidence_refs(
        failure["evidence_refs"],
        allowed_refs,
        "observed_failure.evidence_refs",
        required=True,
    )

    observations = failure["historical_observations"]
    require_list(observations, "observed_failure.historical_observations")
    for index, observation in enumerate(observations):
        label = f"observed_failure.historical_observations[{index}]"
        validate_exact_keys(
            observation,
            {"statement", "evidence_status", "evidence_refs"},
            label,
        )
        require_string(observation["statement"], f"{label}.statement")
        validate_enum(
            observation["evidence_status"],
            vocabularies["evidence_status"],
            f"{label}.evidence_status",
        )
        validate_evidence_refs(
            observation["evidence_refs"],
            allowed_refs,
            f"{label}.evidence_refs",
            required=True,
        )


def validate_stored_pattern(pattern, contract):
    """Validate the current Pattern record shape without reclassifying it."""
    require_dict(pattern, "Pattern")
    if pattern.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"Expected Pattern schema {SCHEMA_VERSION}; re-extract legacy data from Reports"
        )
    validate_exact_keys(
        pattern,
        {
            "schema_version",
            "metadata",
            "derivation_information",
            "provenance",
            "scope",
            "historical_conditions",
            "defect_mechanism",
            "observed_failure",
        },
        "Pattern",
    )
    validate_exact_keys(
        pattern["metadata"],
        {"pattern_id", "canonical_name", "pattern_level"},
        "metadata",
    )
    require_string(pattern["metadata"]["pattern_id"], "metadata.pattern_id")
    if pattern["metadata"]["pattern_level"] != "api_specific":
        raise ValueError("metadata.pattern_level must be api_specific")

    scope = pattern["scope"]
    validate_exact_keys(scope, {"framework", "target_api"}, "scope")
    require_string(scope["framework"], "scope.framework")

    source_report = pattern["provenance"].get("source_report")
    require_dict(source_report, "provenance.source_report")
    validate_exact_keys(
        source_report,
        {"report_id", "report_revision", "report_hash", "evidence_refs"},
        "provenance.source_report",
    )
    if type(source_report["report_revision"]) is not int or source_report["report_revision"] < 1:
        raise ValueError("provenance.source_report.report_revision must be a positive integer")
    require_string(source_report["report_hash"], "provenance.source_report.report_hash")
    validate_string_list(
        source_report["evidence_refs"],
        "provenance.source_report.evidence_refs",
    )
    declared_refs = source_report["evidence_refs"]
    if not declared_refs:
        raise ValueError("provenance.source_report.evidence_refs must not be empty")
    if len(declared_refs) != len(set(declared_refs)):
        raise ValueError("provenance.source_report.evidence_refs must not contain duplicates")

    candidate = {
        "canonical_name": pattern["metadata"]["canonical_name"],
        "provenance": copy.deepcopy(pattern["provenance"]),
        "scope": copy.deepcopy(pattern["scope"]),
        "historical_conditions": copy.deepcopy(pattern["historical_conditions"]),
        "defect_mechanism": copy.deepcopy(pattern["defect_mechanism"]),
        "observed_failure": copy.deepcopy(pattern["observed_failure"]),
    }
    candidate["scope"].pop("framework")
    candidate["provenance"]["source_report"].pop("report_revision")
    candidate["provenance"]["source_report"].pop("report_hash")
    candidate["provenance"]["source_report"].pop("evidence_refs")

    condition_ids = set()
    for condition in candidate["historical_conditions"]:
        condition_id = condition.pop("condition_id", None)
        require_string(condition_id, "historical_conditions.condition_id")
        if condition_id in condition_ids:
            raise ValueError(f"Duplicate condition_id: {condition_id}")
        condition_ids.add(condition_id)

    observation_ids = set()
    for observation in candidate["observed_failure"]["historical_observations"]:
        observation_id = observation.pop("observation_id", None)
        require_string(observation_id, "historical_observations.observation_id")
        if observation_id in observation_ids:
            raise ValueError(f"Duplicate observation_id: {observation_id}")
        observation_ids.add(observation_id)

    refs = semantic_evidence_refs(candidate)
    if sorted(declared_refs) != refs:
        raise ValueError(
            "provenance.source_report.evidence_refs must equal the evidence "
            "union used by semantic Pattern fields"
        )
    validate_candidate(
        candidate,
        {
            "report_id": source_report["report_id"],
            "selected_api": candidate["scope"]["target_api"],
            "available_evidence_refs": sorted(set(refs)),
        },
        contract,
    )

def next_pattern_id(output_api_dir, framework, canonical_name):
    prefix = (
        f"{framework_prefix(framework)}_v4_"
        f"{slugify(canonical_name)}"
    )

    pattern = re.compile(
        rf"^{re.escape(prefix)}_p(\d+)\.json$"
    )

    max_ordinal = 0

    if os.path.isdir(output_api_dir):
        for filename in os.listdir(output_api_dir):
            match = pattern.match(filename)

            if match:
                max_ordinal = max(
                    max_ordinal,
                    int(match.group(1))
                )

    next_ordinal = max_ordinal + 1

    return (
        f"{prefix}_p{next_ordinal:03d}"
    )


def has_existing_pattern_for_report(
    output_api_dir,
    report_id,
    report_hash
):
    if not os.path.isdir(output_api_dir):
        return False

    for filename in os.listdir(output_api_dir):
        if not filename.endswith(".json"):
            continue
        path = os.path.join(output_api_dir, filename)
        try:
            pattern = load_json(path)
            if pattern.get("schema_version") != SCHEMA_VERSION:
                continue
            source_report = pattern.get("provenance", {}).get("source_report", {})
            direct_support = source_report.get("report_id") == report_id
            input_reports = pattern.get(
                "derivation_information", {}
            ).get("input_reports", [])
            derivation = pattern.get("derivation_information", {})
            exact_input = any(
                item.get("report_id") == report_id
                and item.get("report_hash") == report_hash
                for item in input_reports
                if isinstance(item, dict)
            )
            current_extractor = (
                derivation.get("mapping_version") == MAPPING_VERSION
                and derivation.get("prompt_version") == PROMPT_VERSION
            )
            if (
                direct_support
                and exact_input
                and current_extractor
                and source_report.get("report_hash") == report_hash
            ):
                return True
        except (OSError, json.JSONDecodeError, AttributeError):
            continue
    return False


def enrich_final_pattern(
    candidate,
    report_context,
    report_hash,
    pattern_id,
    model
):
    final_pattern = {
        "schema_version": SCHEMA_VERSION,

        "metadata": {
            "pattern_id": pattern_id,
            "canonical_name": candidate[
                "canonical_name"
            ],
            "pattern_level": "api_specific"
        },

        "derivation_information": {
            "method": "llm_assisted",
            "mapping_version": MAPPING_VERSION,
            "prompt_version": PROMPT_VERSION,
            "model": model,
            "input_reports": [
                {
                    "report_id": report_context["report_id"],
                    "report_hash": report_hash
                }
            ],
            "generated_at": datetime.now(
                timezone.utc
            ).date().isoformat(),
            "validation_status": "automatically_validated"
        },

        "provenance": {
            **candidate["provenance"],
            "source_report": {
                "report_id": candidate["provenance"]["source_report"]["report_id"],
                "evidence_refs": semantic_evidence_refs(candidate),
                "report_revision": report_context["report_revision"],
                "report_hash": report_hash
            }
        },

        "scope": {
            "framework": report_context["framework"],
            **candidate["scope"]
        },

        "historical_conditions": candidate["historical_conditions"],

        "defect_mechanism": candidate[
            "defect_mechanism"
        ],

        "observed_failure": candidate["observed_failure"]
    }

    for index, condition in enumerate(
        final_pattern["historical_conditions"],
        start=1
    ):
        condition["condition_id"] = f"tc_{index:02d}"

    for index, observation in enumerate(
        final_pattern["observed_failure"]["historical_observations"],
        start=1
    ):
        observation["observation_id"] = f"ho_{index:02d}"

    return final_pattern


def validate_api_argument(api):
    if not api.strip():
        raise ValueError("--api must not be empty")

    if "/" in api or "\\" in api or ".." in api:
        raise ValueError(
            "--api must be an API directory name, "
            "not a path"
        )


def resolve_output_dir(output_value):
    if os.path.isabs(output_value):
        return output_value

    return os.path.join(
        EXP006_DIR,
        output_value
    )


def process_api(
    api,
    api_key,
    output_root,
    model,
    api_url,
    dry_run
):
    validate_api_argument(api)

    output_api_dir = os.path.join(
        output_root,
        api
    )

    for existing_path in Path(output_api_dir).glob("*.json"):
        existing = load_json(existing_path)
        if not isinstance(existing, dict) or existing.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Output directory contains legacy or invalid Patterns; use the separate v4 output root")

    report_paths = latest_report_paths_for_api(api)
    if not report_paths:
        raise RuntimeError(
            f"No latest Report supports API {api!r} under {BUG_REPORT_DIR}"
        )

    contract = load_json(CONTRACT_FILE)
    mapping = load_text(MAPPING_FILE)

    generated_count = 0
    skipped_count = 0
    failed_count = 0

    for report_path in report_paths:
        filename = os.path.basename(report_path)
        fallback_report_id = os.path.splitext(filename)[0]

        try:
            report = load_json(str(report_path))
            report_builder.validate_revision_chain(report_path.parent)
            report_context = build_report_context(
                report,
                fallback_report_id,
                api,
            )
        except (
            OSError,
            json.JSONDecodeError,
            ValueError,
            report_builder.ReportError,
        ) as error:
            print(f"[FAILED] {filename}: Report input rejected: {error}")
            failed_count += 1
            continue

        report_id = report_context["report_id"]
        report_hash = report["provenance"]["content_hash"]

        if has_existing_pattern_for_report(
            output_api_dir,
            report_id,
            report_hash
        ):
            print(
                f"[SKIP] {filename}: existing Pattern "
                f"already uses Report ID {report_id}"
            )

            skipped_count += 1
            continue

        print(
            f"[PROCESS] {filename} "
            f"(report_id={report_id})"
        )

        prompt = build_prompt(
            report_context,
            contract,
            mapping
        )
        if len(prompt) > MAX_PROMPT_CHARS:
            print(f"[FAILED] {filename}: prompt exceeds {MAX_PROMPT_CHARS} characters")
            failed_count += 1
            continue
        if dry_run:
            print(f"[DRY-RUN] {report_id}: non-rejected input validated; prompt_chars={len(prompt)}; no model call")
            continue

        candidates = None
        previous_response = ""
        validation_error = ""

        for attempt_index in range(1, MAX_LLM_ATTEMPTS + 1):
            attempt_prompt = (
                prompt
                if attempt_index == 1
                else build_repair_prompt(
                    prompt,
                    previous_response,
                    validation_error,
                )
            )
            try:
                if len(attempt_prompt) > MAX_PROMPT_CHARS:
                    raise ValueError("Repair prompt exceeds context budget")
                raw_response = call_deepseek(
                    attempt_prompt,
                    api_key,
                    model,
                    api_url,
                )
                previous_response = raw_response
                response = extract_json(raw_response)
                validate_response_envelope(response)

                validated_candidates = []
                for raw_candidate in response["patterns"]:
                    candidate = normalize_candidate(raw_candidate)
                    validate_candidate(candidate, report_context, contract)
                    validated_candidates.append(candidate)

                canonical_names = [
                    candidate["canonical_name"]
                    for candidate in validated_candidates
                ]
                if len(canonical_names) != len(set(canonical_names)):
                    raise ValueError(
                        "duplicated canonical_name values in one response"
                    )

                candidates = validated_candidates
                break
            except requests.RequestException as error:
                validation_error = str(error)
                print(
                    f"[FAILED] {filename}: network request failed: "
                    f"{validation_error}"
                )
                break
            except Exception as error:
                validation_error = str(error)
                if attempt_index < MAX_LLM_ATTEMPTS:
                    print(
                        f"[RETRY] {filename}: attempt {attempt_index} "
                        f"failed validation: {validation_error}"
                    )
                else:
                    print(
                        f"[FAILED] {filename}: all {MAX_LLM_ATTEMPTS} "
                        f"LLM attempts failed: {validation_error}"
                    )

        if candidates is None:
            failed_count += 1
            continue

        final_patterns = []

        for candidate in candidates:
            pattern_id = next_pattern_id(
                output_api_dir,
                report_context["framework"],
                candidate["canonical_name"]
            )

            final_pattern = enrich_final_pattern(
                candidate,
                report_context,
                report_hash,
                pattern_id,
                model
            )

            final_patterns.append(final_pattern)

        if dry_run:
            for final_pattern in final_patterns:
                print(
                    "[DRY-RUN] Valid Pattern:",
                    final_pattern["metadata"]["pattern_id"],
                    "|",
                    final_pattern["metadata"][
                        "canonical_name"
                    ]
                )

            generated_count += len(final_patterns)
            continue

        os.makedirs(
            output_api_dir,
            exist_ok=True
        )

        try:
            for final_pattern in final_patterns:
                output_path = os.path.join(
                    output_api_dir,
                    (
                        final_pattern["metadata"]["pattern_id"]
                        + ".json"
                    )
                )

                with open(
                    output_path,
                    "x",
                    encoding="utf-8"
                ) as output_file:
                    json.dump(
                        final_pattern,
                        output_file,
                        indent=2,
                        ensure_ascii=False
                    )

                print(
                    "[WRITE]",
                    output_path
                )

            generated_count += len(final_patterns)

        except FileExistsError as error:
            print(
                f"[FAILED] {filename}: refusing to overwrite "
                f"an existing Pattern: {error}"
            )

            failed_count += 1

        except OSError as error:
            print(
                f"[FAILED] {filename}: write error: {error}"
            )

            failed_count += 1

    print()
    print("Pattern extraction complete")
    print(f"Generated: {generated_count}")
    print(f"Skipped:   {skipped_count}")
    print(f"Failed:    {failed_count}")
    return 1 if failed_count else 0


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Build Pattern v4 JSON records from structured "
            "historical Bug Reports."
        )
    )

    parser.add_argument(
        "--api",
        required=True,
        help=(
            "Input API directory name, for example "
            "torch.matmul"
        )
    )

    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT_DIR,
        help=(
            "Output root directory. Defaults to "
            "EXP006/bug_patterns/v4."
        )
    )

    parser.add_argument(
        "--api-key",
        "--api_key",
        dest="api_key",
        default=os.environ.get("DEEPSEEK_API_KEY"),
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
        help="DeepSeek chat-completions endpoint."
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Validate non-rejected inputs and prompt size without model calls or writes."
        )
    )

    args = parser.parse_args()

    if not args.api_key and not args.dry_run:
        raise RuntimeError(
            "Missing DeepSeek API key. Set DEEPSEEK_API_KEY "
            "or pass --api-key."
        )

    output_root = resolve_output_dir(
        args.output
    )

    return process_api(
        api=args.api,
        api_key=args.api_key,
        output_root=output_root,
        model=args.model,
        api_url=args.api_url,
        dry_run=args.dry_run
    )


if __name__ == "__main__":
    raise SystemExit(main())
