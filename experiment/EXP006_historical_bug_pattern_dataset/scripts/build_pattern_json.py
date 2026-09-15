import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from datetime import datetime, timezone

import requests


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
    "bug_patterns"
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

SCHEMA_VERSION = "2.1"
MAPPING_VERSION = "2.1"
PROMPT_VERSION = "pattern_extract_v2_5"

DEFAULT_MODEL = "deepseek-v4-pro"

DEFAULT_API_URL = (
    "https://api.deepseek.com/chat/completions"
)

MAX_LLM_ATTEMPTS = 3

CANDIDATE_KEYS = {
    "canonical_name",
    "provenance",
    "scope",
    "defect_classification",
    "trigger_signature",
    "defect_mechanism",
    "observed_failure",
    "confidence"
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

    classification = candidate.get(
        "defect_classification"
    )

    if isinstance(classification, dict):
        if (
            "secondary_categories" in classification
            and "secondary_defect_classes" not in classification
        ):
            classification["secondary_defect_classes"] = (
                classification.pop("secondary_categories")
            )

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
        and item.get("relation") in {"primary", "affected"}
        for item in assertions
    )


def latest_report_paths_for_api(api):
    """Return one newest Report revision per supported Report ID."""
    latest = {}
    for path in sorted(Path(BUG_REPORT_DIR).rglob("revision_*.json")):
        try:
            report = load_json(str(path))
        except (OSError, json.JSONDecodeError):
            continue
        if not report_supports_api(report, api):
            continue
        report_id = get_report_id(report, path.stem)
        revision = report.get("revision_information", {}).get("revision_number", 0)
        try:
            revision = int(revision)
        except (TypeError, ValueError):
            revision = 0
        previous = latest.get(report_id)
        if previous is None or revision > previous[0] or (revision == previous[0] and str(path) > str(previous[1])):
            latest[report_id] = (revision, path)
    return [item[1] for item in sorted(latest.values(), key=lambda item: (item[0], str(item[1])))]


def build_report_context(report, fallback_report_id, selected_api):
    report_id = get_report_id(report, fallback_report_id)
    framework = get_framework(report)
    evidence_items = report.get("evidence_items", [])
    if not isinstance(evidence_items, list):
        raise ValueError("Report evidence_items must be an array")
    available_evidence_refs = []
    for item in evidence_items:
        if not isinstance(item, dict) or not item.get("evidence_id"):
            raise ValueError("Every evidence item must contain evidence_id")
        available_evidence_refs.append(item["evidence_id"])
    if not available_evidence_refs:
        raise ValueError("Report has no addressable evidence_items")
    return {
        "report_id": report_id,
        "framework": framework,
        "selected_api": selected_api,
        "available_evidence_refs": available_evidence_refs,
        "report": report,
    }


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


def validate_candidate(
    candidate,
    report_context,
    contract
):
    validate_exact_keys(
        candidate,
        CANDIDATE_KEYS,
        "Pattern candidate"
    )

    forbidden_path = contains_forbidden_key(candidate)

    if forbidden_path:
        raise ValueError(
            f"Forbidden field detected: {forbidden_path}"
        )

    empty_string_path = find_empty_string(candidate)

    if empty_string_path:
        raise ValueError(
            f"Empty string is not allowed: {empty_string_path}"
        )

    vocabularies = contract[
        "controlled_vocabularies"
    ]

    allowed_refs = set(
        report_context["available_evidence_refs"]
    )

    require_string(
        candidate["canonical_name"],
        "canonical_name"
    )

    if not re.fullmatch(
        r"[a-z][a-z0-9_]*",
        candidate["canonical_name"]
    ):
        raise ValueError(
            "canonical_name must use lower_snake_case"
        )

    provenance = candidate["provenance"]

    validate_exact_keys(
        provenance,
        {
            "supporting_reports",
            "abstraction_rationale",
            "unresolved_information"
        },
        "provenance"
    )

    require_string(
        provenance["abstraction_rationale"],
        "provenance.abstraction_rationale"
    )

    validate_string_list(
        provenance["unresolved_information"],
        "provenance.unresolved_information"
    )

    supporting_reports = provenance[
        "supporting_reports"
    ]

    require_list(
        supporting_reports,
        "provenance.supporting_reports"
    )

    if len(supporting_reports) != 1:
        raise ValueError(
            "Initial extraction must contain exactly one "
            "supporting Report"
        )

    supporting_report = supporting_reports[0]

    validate_exact_keys(
        supporting_report,
        {
            "report_id",
            "relation",
            "evidence_refs",
            "source_verification"
        },
        "provenance.supporting_reports[0]"
    )

    if (
        supporting_report["report_id"]
        != report_context["report_id"]
    ):
        raise ValueError(
            "supporting_reports[0].report_id must match "
            "the input Report ID"
        )

    if supporting_report["relation"] != "direct_evidence":
        raise ValueError(
            "Initial extraction relation must be direct_evidence"
        )

    validate_evidence_refs(
        supporting_report["evidence_refs"],
        allowed_refs,
        "provenance.supporting_reports[0].evidence_refs",
        required=True
    )

    source_verification = supporting_report[
        "source_verification"
    ]

    validate_exact_keys(
        source_verification,
        {
            "issue_verification_status",
            "fix_status",
            "reproduction_status"
        },
        "source_verification"
    )

    validate_enum(
        source_verification[
            "issue_verification_status"
        ],
        vocabularies["issue_verification_status"],
        "issue_verification_status"
    )

    validate_enum(
        source_verification["fix_status"],
        vocabularies["fix_status"],
        "fix_status"
    )

    validate_enum(
        source_verification[
            "reproduction_status"
        ],
        vocabularies["reproduction_status"],
        "reproduction_status"
    )

    scope = candidate["scope"]

    validate_exact_keys(
        scope,
        {
            "primary_api",
            "confirmed_apis",
            "operator",
            "module"
        },
        "scope"
    )

    require_string(
        scope["primary_api"],
        "scope.primary_api"
    )

    validate_string_list(
        scope["confirmed_apis"],
        "scope.confirmed_apis"
    )

    if scope["primary_api"] not in scope["confirmed_apis"]:
        raise ValueError(
            "scope.primary_api must appear in "
            "scope.confirmed_apis"
        )

    selected_api = report_context["selected_api"]
    if scope["primary_api"] != selected_api:
        raise ValueError(
            f"scope.primary_api must match selected API {selected_api!r}"
        )
    if selected_api not in scope["confirmed_apis"]:
        raise ValueError(
            f"scope.confirmed_apis must include selected API {selected_api!r}"
        )

    for optional_key in ["operator", "module"]:
        value = scope[optional_key]

        if value is not None:
            require_string(
                value,
                f"scope.{optional_key}"
            )

    classification = candidate[
        "defect_classification"
    ]

    validate_exact_keys(
        classification,
        {
            "primary_defect_class",
            "secondary_defect_classes",
            "risk_dimensions"
        },
        "defect_classification"
    )

    validate_enum(
        classification["primary_defect_class"],
        vocabularies["defect_classes"],
        "primary_defect_class"
    )

    validate_string_list(
        classification[
            "secondary_defect_classes"
        ],
        "secondary_defect_classes"
    )

    for defect_class in classification[
        "secondary_defect_classes"
    ]:
        validate_enum(
            defect_class,
            vocabularies["defect_classes"],
            "secondary_defect_classes"
        )

    validate_string_list(
        classification["risk_dimensions"],
        "risk_dimensions"
    )

    for dimension in classification["risk_dimensions"]:
        validate_enum(
            dimension,
            vocabularies["risk_dimensions"],
            "risk_dimensions"
        )

    trigger_signature = candidate[
        "trigger_signature"
    ]

    validate_exact_keys(
        trigger_signature,
        {
            "conditions",
            "operation_context"
        },
        "trigger_signature"
    )

    conditions = trigger_signature["conditions"]

    require_list(
        conditions,
        "trigger_signature.conditions"
    )

    for index, condition in enumerate(conditions):
        label = f"trigger_signature.conditions[{index}]"

        validate_exact_keys(
            condition,
            {
                "dimension",
                "subject",
                "predicate",
                "necessity",
                "evidence_status",
                "evidence_refs"
            },
            label
        )

        validate_enum(
            condition["dimension"],
            vocabularies["risk_dimensions"],
            f"{label}.dimension"
        )

        require_string(
            condition["subject"],
            f"{label}.subject"
        )

        require_string(
            condition["predicate"],
            f"{label}.predicate"
        )

        validate_enum(
            condition["necessity"],
            vocabularies["condition_necessity"],
            f"{label}.necessity"
        )

        validate_enum(
            condition["evidence_status"],
            vocabularies["evidence_status"],
            f"{label}.evidence_status"
        )

        validate_evidence_refs(
            condition["evidence_refs"],
            allowed_refs,
            f"{label}.evidence_refs",
            required=True
        )

    operation_context = trigger_signature[
        "operation_context"
    ]

    if operation_context is not None:
        validate_exact_keys(
            operation_context,
            {
                "description",
                "evidence_status",
                "evidence_refs"
            },
            "trigger_signature.operation_context"
        )

        require_string(
            operation_context["description"],
            "trigger_signature.operation_context.description"
        )

        validate_enum(
            operation_context["evidence_status"],
            vocabularies["evidence_status"],
            "trigger_signature.operation_context.evidence_status"
        )

        validate_evidence_refs(
            operation_context["evidence_refs"],
            allowed_refs,
            "trigger_signature.operation_context.evidence_refs",
            required=True
        )

    mechanism = candidate["defect_mechanism"]

    validate_exact_keys(
        mechanism,
        {"hypotheses"},
        "defect_mechanism"
    )

    hypotheses = mechanism["hypotheses"]

    require_list(
        hypotheses,
        "defect_mechanism.hypotheses"
    )

    for index, hypothesis in enumerate(hypotheses):
        label = f"defect_mechanism.hypotheses[{index}]"

        validate_exact_keys(
            hypothesis,
            {
                "layer",
                "description",
                "status",
                "evidence_refs",
                "confidence"
            },
            label
        )

        validate_enum(
            hypothesis["layer"],
            vocabularies["mechanism_layers"],
            f"{label}.layer"
        )

        require_string(
            hypothesis["description"],
            f"{label}.description"
        )

        validate_enum(
            hypothesis["status"],
            vocabularies["mechanism_status"],
            f"{label}.status"
        )

        if hypothesis["status"] == "unknown":
            raise ValueError(
                f"{label}.status must not be unknown; "
                "use an empty hypotheses array when "
                "the mechanism is unavailable"
            )

        validate_evidence_refs(
            hypothesis["evidence_refs"],
            allowed_refs,
            f"{label}.evidence_refs",
            required=True
        )

        validate_enum(
            hypothesis["confidence"],
            vocabularies["confidence"],
            f"{label}.confidence"
        )

        if (
            hypothesis["status"] == "analyst_inferred"
            and hypothesis["confidence"] == "high"
        ):
            raise ValueError(
                f"{label}: analyst_inferred mechanism "
                "cannot have high confidence"
            )

    observed_failure = candidate["observed_failure"]

    validate_exact_keys(
        observed_failure,
        {
            "failure_type",
            "description",
            "historical_oracle",
            "evidence_refs"
        },
        "observed_failure"
    )

    validate_enum(
        observed_failure["failure_type"],
        vocabularies["failure_types"],
        "observed_failure.failure_type"
    )

    if observed_failure["description"] is not None:
        require_string(
            observed_failure["description"],
            "observed_failure.description"
        )

    known_failure = (
        observed_failure["failure_type"] != "unknown"
    )

    validate_evidence_refs(
        observed_failure["evidence_refs"],
        allowed_refs,
        "observed_failure.evidence_refs",
        required=known_failure
    )

    historical_oracle = observed_failure[
        "historical_oracle"
    ]

    if historical_oracle is not None:
        validate_exact_keys(
            historical_oracle,
            {
                "kind",
                "condition",
                "evidence_status",
                "evidence_refs"
            },
            "observed_failure.historical_oracle"
        )

        validate_enum(
            historical_oracle["kind"],
            vocabularies["historical_oracle_kinds"],
            "historical_oracle.kind"
        )

        require_string(
            historical_oracle["condition"],
            "historical_oracle.condition"
        )

        validate_enum(
            historical_oracle["evidence_status"],
            vocabularies["evidence_status"],
            "historical_oracle.evidence_status"
        )

        validate_evidence_refs(
            historical_oracle["evidence_refs"],
            allowed_refs,
            "historical_oracle.evidence_refs",
            required=True
        )

    confidence = candidate["confidence"]

    validate_exact_keys(
        confidence,
        {
            "trigger_confidence",
            "mechanism_confidence",
            "oracle_confidence"
        },
        "confidence"
    )

    for key, value in confidence.items():
        validate_enum(
            value,
            vocabularies["confidence"],
            f"confidence.{key}"
        )

    if not conditions and (
        confidence["trigger_confidence"] != "low"
    ):
        raise ValueError(
            "trigger_confidence must be low when "
            "no trigger conditions are available"
        )

    if not hypotheses and (
        confidence["mechanism_confidence"] != "low"
    ):
        raise ValueError(
            "mechanism_confidence must be low when "
            "no mechanism hypothesis is available"
        )

    if historical_oracle is None and (
        confidence["oracle_confidence"] != "low"
    ):
        raise ValueError(
            "oracle_confidence must be low when "
            "historical_oracle is null"
        )


def next_pattern_id(output_api_dir, framework, canonical_name):
    prefix = (
        f"{framework_prefix(framework)}_"
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
            supporting_reports = pattern.get(
                "provenance", {}
            ).get("supporting_reports", [])
            direct_support = any(
                item.get("report_id") == report_id
                and item.get("relation") == "direct_evidence"
                for item in supporting_reports
                if isinstance(item, dict)
            )
            input_reports = pattern.get(
                "derivation_information", {}
            ).get("input_reports", [])
            exact_input = any(
                item.get("report_id") == report_id
                and item.get("report_hash") == report_hash
                for item in input_reports
                if isinstance(item, dict)
            )
            if direct_support and exact_input:
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

        "provenance": candidate["provenance"],

        "scope": {
            "framework": report_context["framework"],
            **candidate["scope"]
        },

        "defect_classification": candidate[
            "defect_classification"
        ],

        "trigger_signature": candidate[
            "trigger_signature"
        ],

        "defect_mechanism": candidate[
            "defect_mechanism"
        ],

        "observed_failure": candidate[
            "observed_failure"
        ],

        "confidence": candidate["confidence"]
    }

    for index, condition in enumerate(
        final_pattern["trigger_signature"]["conditions"],
        start=1
    ):
        condition["condition_id"] = f"tc_{index:02d}"

    for index, hypothesis in enumerate(
        final_pattern["defect_mechanism"]["hypotheses"],
        start=1
    ):
        hypothesis["hypothesis_id"] = f"dm_{index:02d}"

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

    report_paths = latest_report_paths_for_api(api)
    if not report_paths:
        raise RuntimeError(
            f"No v2 Report supports API {api!r} under {BUG_REPORT_DIR}"
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
            report_context = build_report_context(
                report,
                fallback_report_id,
                api,
            )
        except (
            OSError,
            json.JSONDecodeError,
            ValueError,
        ) as error:
            print(f"[FAILED] {filename}: invalid v2 Report: {error}")
            failed_count += 1
            continue

        report_id = report_context["report_id"]
        report_hash = canonical_json_hash(report)

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


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Build Pattern v2 JSON records from structured "
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
            "EXP006/bug_patterns."
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
            "Call the LLM and validate output without "
            "writing Pattern JSON files."
        )
    )

    args = parser.parse_args()

    if not args.api_key:
        raise RuntimeError(
            "Missing DeepSeek API key. Set DEEPSEEK_API_KEY "
            "or pass --api-key."
        )

    output_root = resolve_output_dir(
        args.output
    )

    process_api(
        api=args.api,
        api_key=args.api_key,
        output_root=output_root,
        model=args.model,
        api_url=args.api_url,
        dry_run=args.dry_run
    )


if __name__ == "__main__":
    main()