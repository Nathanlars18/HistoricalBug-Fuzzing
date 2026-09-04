import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone

import requests


BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

EXP006_DIR = os.path.dirname(BASE_DIR)

PATTERN_DIR = os.path.join(
    EXP006_DIR,
    "bug_patterns"
)

DEFAULT_OUTPUT_DIR = os.path.join(
    EXP006_DIR,
    "knowledge_base"
)

CONTRACT_FILE = os.path.join(
    EXP006_DIR,
    "schemas",
    "knowledge_extraction_contract.json"
)

RULE_FILE = os.path.join(
    EXP006_DIR,
    "schemas",
    "pattern_to_knowledge_rules.md"
)

SCHEMA_VERSION = "2.0"
MAPPING_VERSION = "2.0"
PROMPT_VERSION = "knowledge_extract_v2"

DEFAULT_MODEL = "deepseek-v4-pro"

DEFAULT_API_URL = (
    "https://api.deepseek.com/chat/completions"
)

CANDIDATE_KEYS = {
    "canonical_name",
    "evidence_basis",
    "knowledge_statement",
    "applicability",
    "testing_guidance",
    "confidence"
}

FORBIDDEN_FIELD_NAMES = {
    "harnessspec",
    "harness_spec",
    "harness_strategy",
    "strategy_primitive",
    "strategy_primitives",
    "validity_predicate",
    "risk_predicate",
    "activation_predicate",
    "tensor_construction",
    "input_mutation",
    "harness_code",
    "generated_code",
    "code_generation_prompt",
    "general_knowledge",
    "pattern_family"
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


def require_string_or_null(value, label):
    if value is not None:
        require_string(value, label)


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

    digest = hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()

    return f"sha256:{digest}"


def framework_prefix(framework):
    prefixes = {
        "pytorch": "pt",
        "tensorflow": "tf"
    }

    normalized = slugify(framework)

    return prefixes.get(
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
        timeout=180
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
        items = []

        for item in value:
            normalized = deep_normalize(item)

            if normalized not in (None, "", [], {}):
                items.append(normalized)

        return items

    if isinstance(value, dict):
        return {
            key: deep_normalize(item)
            for key, item in value.items()
        }

    return value


def contains_forbidden_key(value, path=""):
    if isinstance(value, dict):
        for key, item in value.items():
            current_path = (
                f"{path}.{key}"
                if path
                else key
            )

            if slugify(key) in FORBIDDEN_FIELD_NAMES:
                return current_path

            nested = contains_forbidden_key(
                item,
                current_path
            )

            if nested:
                return nested

    if isinstance(value, list):
        for index, item in enumerate(value):
            nested = contains_forbidden_key(
                item,
                f"{path}[{index}]"
            )

            if nested:
                return nested

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


def get_pattern_metadata(pattern):
    metadata = pattern.get("metadata")

    require_dict(metadata, "Pattern metadata")

    pattern_id = metadata.get("pattern_id")
    canonical_name = metadata.get("canonical_name")

    require_string(pattern_id, "metadata.pattern_id")
    require_string(
        canonical_name,
        "metadata.canonical_name"
    )

    return metadata


def get_pattern_scope(pattern):
    scope = pattern.get("scope")

    require_dict(scope, "Pattern scope")

    framework = scope.get("framework")
    primary_api = scope.get("primary_api")
    confirmed_apis = scope.get("confirmed_apis")

    require_string(scope.get("framework"), "scope.framework")
    require_string(scope.get("primary_api"), "scope.primary_api")
    validate_string_list(
        scope.get("confirmed_apis"),
        "scope.confirmed_apis"
    )

    if primary_api not in confirmed_apis:
        raise ValueError(
            "Pattern scope.primary_api must appear in "
            "scope.confirmed_apis"
        )

    return {
        "framework": framework,
        "primary_api": primary_api,
        "confirmed_apis": confirmed_apis
    }


def build_available_evidence_refs(pattern, pattern_id):
    refs = []

    def add_ref(suffix):
        ref = f"pattern:{pattern_id}:{suffix}"

        if ref not in refs:
            refs.append(ref)

    for field_name in [
        "provenance",
        "scope",
        "defect_classification",
        "trigger_signature",
        "defect_mechanism",
        "observed_failure",
        "transferability_hypothesis",
        "confidence"
    ]:
        if field_name in pattern:
            add_ref(field_name)

    trigger_conditions = pattern.get(
        "trigger_signature",
        {}
    ).get(
        "conditions",
        []
    )

    if isinstance(trigger_conditions, list):
        for index, condition in enumerate(
            trigger_conditions,
            start=1
        ):
            condition_id = None

            if isinstance(condition, dict):
                condition_id = condition.get(
                    "condition_id"
                )

            add_ref(
                "trigger_condition:"
                f"{condition_id or index}"
            )

    hypotheses = pattern.get(
        "defect_mechanism",
        {}
    ).get(
        "hypotheses",
        []
    )

    if isinstance(hypotheses, list):
        for index, hypothesis in enumerate(
            hypotheses,
            start=1
        ):
            hypothesis_id = None

            if isinstance(hypothesis, dict):
                hypothesis_id = hypothesis.get(
                    "hypothesis_id"
                )

            add_ref(
                "mechanism_hypothesis:"
                f"{hypothesis_id or index}"
            )

    observed_failure = pattern.get(
        "observed_failure",
        {}
    )

    if (
        isinstance(observed_failure, dict)
        and observed_failure.get("historical_oracle")
        is not None
    ):
        add_ref("observed_failure.historical_oracle")

    return refs


def build_pattern_context(pattern):
    metadata = get_pattern_metadata(pattern)
    scope = get_pattern_scope(pattern)

    pattern_id = metadata["pattern_id"]

    available_evidence_refs = build_available_evidence_refs(
        pattern,
        pattern_id
    )

    if not available_evidence_refs:
        raise ValueError(
            "Pattern has no addressable evidence fields"
        )

    return {
        "pattern_id": pattern_id,
        "pattern_hash": canonical_json_hash(pattern),
        "framework": scope["framework"],
        "primary_api": scope["primary_api"],
        "directly_supported_apis": scope[
            "confirmed_apis"
        ],
        "available_evidence_refs": available_evidence_refs,
        "pattern": pattern
    }


def build_prompt(pattern_context, contract, rules):
    return f"""
You are deriving one evidence-grounded API-specific Knowledge candidate
from one API-specific historical Bug Pattern.

Follow the Pattern-to-Knowledge Rules and the Knowledge Extraction Contract
exactly.

Return JSON only.
Do not output Markdown, explanations, or code fences.

====================
Knowledge Extraction Contract
====================

{json.dumps(contract, indent=2, ensure_ascii=False)}

====================
Pattern-to-Knowledge Rules
====================

{rules}

====================
Input Pattern Context
====================

{json.dumps(pattern_context, indent=2, ensure_ascii=False)}
"""


def validate_response_envelope(response):
    validate_exact_keys(
        response,
        {"knowledge"},
        "LLM response"
    )

    require_dict(
        response["knowledge"],
        "LLM response.knowledge"
    )


def validate_conditions(
    conditions,
    label,
    vocabularies,
    allowed_refs
):
    require_list(conditions, label)

    for index, condition in enumerate(conditions):
        item_label = f"{label}[{index}]"

        validate_exact_keys(
            condition,
            {
                "condition_kind",
                "statement",
                "evidence_status",
                "evidence_refs"
            },
            item_label
        )

        validate_enum(
            condition["condition_kind"],
            vocabularies["condition_kind"],
            f"{item_label}.condition_kind"
        )

        require_string(
            condition["statement"],
            f"{item_label}.statement"
        )

        validate_enum(
            condition["evidence_status"],
            vocabularies["evidence_status"],
            f"{item_label}.evidence_status"
        )

        if condition["evidence_status"] == "unknown":
            raise ValueError(
                f"{item_label}.evidence_status cannot be "
                "unknown for an asserted condition"
            )

        validate_evidence_refs(
            condition["evidence_refs"],
            allowed_refs,
            f"{item_label}.evidence_refs",
            required=True
        )


def validate_exploration_goals(
    goals,
    vocabularies,
    allowed_refs
):
    require_list(goals, "testing_guidance.exploration_goals")

    for index, goal in enumerate(goals):
        label = (
            "testing_guidance."
            f"exploration_goals[{index}]"
        )

        validate_exact_keys(
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
            vocabularies["risk_dimensions"],
            f"{label}.target_dimension"
        )

        require_string(
            goal["statement"],
            f"{label}.statement"
        )

        validate_enum(
            goal["priority"],
            vocabularies["goal_priority"],
            f"{label}.priority"
        )

        validate_enum(
            goal["evidence_status"],
            vocabularies["evidence_status"],
            f"{label}.evidence_status"
        )

        if goal["evidence_status"] == "unknown":
            raise ValueError(
                f"{label}.evidence_status cannot be "
                "unknown for an asserted exploration goal"
            )

        validate_evidence_refs(
            goal["evidence_refs"],
            allowed_refs,
            f"{label}.evidence_refs",
            required=True
        )


def validate_oracle_guidance(
    oracle_guidance,
    vocabularies,
    allowed_refs
):
    require_list(
        oracle_guidance,
        "testing_guidance.oracle_guidance"
    )

    for index, oracle in enumerate(oracle_guidance):
        label = (
            "testing_guidance."
            f"oracle_guidance[{index}]"
        )

        validate_exact_keys(
            oracle,
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
            oracle["objective"],
            f"{label}.objective"
        )

        validate_enum(
            oracle["observation_kind"],
            vocabularies["observation_kind"],
            f"{label}.observation_kind"
        )

        validate_enum(
            oracle["evidence_status"],
            vocabularies["evidence_status"],
            f"{label}.evidence_status"
        )

        validate_evidence_refs(
            oracle["evidence_refs"],
            allowed_refs,
            f"{label}.evidence_refs",
            required=True
        )

        validate_enum(
            oracle["confidence"],
            vocabularies["confidence"],
            f"{label}.confidence"
        )

        if (
            oracle["observation_kind"]
            == "derived_oracle_candidate"
        ):
            if oracle["evidence_status"] != "analyst_inferred":
                raise ValueError(
                    f"{label}: derived_oracle_candidate must "
                    "use analyst_inferred evidence status"
                )

            if oracle["confidence"] == "high":
                raise ValueError(
                    f"{label}: derived_oracle_candidate cannot "
                    "have high confidence"
                )


def validate_candidate(
    candidate,
    pattern_context,
    contract
):
    candidate = deep_normalize(candidate)

    require_dict(candidate, "Knowledge candidate")

    validate_exact_keys(
        candidate,
        CANDIDATE_KEYS,
        "Knowledge candidate"
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
        pattern_context["available_evidence_refs"]
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

    evidence_basis = candidate["evidence_basis"]

    validate_exact_keys(
        evidence_basis,
        {
            "derivation_rationale",
            "limitations"
        },
        "evidence_basis"
    )

    require_string(
        evidence_basis["derivation_rationale"],
        "evidence_basis.derivation_rationale"
    )

    validate_string_list(
        evidence_basis["limitations"],
        "evidence_basis.limitations"
    )

    statement = candidate["knowledge_statement"]

    validate_exact_keys(
        statement,
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
        vocabularies["evidence_status"],
        "knowledge_statement.evidence_status"
    )

    if statement["evidence_status"] == "unknown":
        raise ValueError(
            "knowledge_statement.evidence_status cannot "
            "be unknown for an asserted Knowledge statement"
        )

    validate_evidence_refs(
        statement["evidence_refs"],
        allowed_refs,
        "knowledge_statement.evidence_refs",
        required=True
    )

    applicability = candidate["applicability"]

    validate_exact_keys(
        applicability,
        {
            "candidate_family_tags",
            "applicability_conditions",
            "exclusion_conditions",
            "rationale",
            "evidence_status",
            "evidence_refs"
        },
        "applicability"
    )

    validate_string_list(
        applicability["candidate_family_tags"],
        "applicability.candidate_family_tags"
    )

    for tag in applicability["candidate_family_tags"]:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", tag):
            raise ValueError(
                "candidate_family_tags must use "
                "lower_snake_case"
            )

    validate_conditions(
        applicability["applicability_conditions"],
        "applicability.applicability_conditions",
        vocabularies,
        allowed_refs
    )

    validate_conditions(
        applicability["exclusion_conditions"],
        "applicability.exclusion_conditions",
        vocabularies,
        allowed_refs
    )

    require_string_or_null(
        applicability["rationale"],
        "applicability.rationale"
    )

    validate_enum(
        applicability["evidence_status"],
        vocabularies["evidence_status"],
        "applicability.evidence_status"
    )

    applicability_is_active = any(
        [
            applicability["candidate_family_tags"],
            applicability["applicability_conditions"],
            applicability["exclusion_conditions"],
            applicability["rationale"] is not None
        ]
    )

    if (
        applicability_is_active
        and applicability["evidence_status"] == "unknown"
    ):
        raise ValueError(
            "applicability.evidence_status cannot be "
            "unknown when Applicability makes a claim"
        )

    validate_evidence_refs(
        applicability["evidence_refs"],
        allowed_refs,
        "applicability.evidence_refs",
        required=applicability_is_active
    )

    testing_guidance = candidate["testing_guidance"]

    validate_exact_keys(
        testing_guidance,
        {
            "risk_dimensions",
            "exploration_goals",
            "oracle_guidance"
        },
        "testing_guidance"
    )

    validate_string_list(
        testing_guidance["risk_dimensions"],
        "testing_guidance.risk_dimensions"
    )

    for dimension in testing_guidance["risk_dimensions"]:
        validate_enum(
            dimension,
            vocabularies["risk_dimensions"],
            "testing_guidance.risk_dimensions"
        )

    validate_exploration_goals(
        testing_guidance["exploration_goals"],
        vocabularies,
        allowed_refs
    )

    expected_dimensions = []

    for goal in testing_guidance["exploration_goals"]:
        dimension = goal["target_dimension"]

        if dimension not in expected_dimensions:
            expected_dimensions.append(dimension)

    if testing_guidance["risk_dimensions"] != expected_dimensions:
        raise ValueError(
            "testing_guidance.risk_dimensions must equal "
            "the ordered de-duplicated target_dimension "
            "values from exploration_goals"
        )

    validate_oracle_guidance(
        testing_guidance["oracle_guidance"],
        vocabularies,
        allowed_refs
    )

    confidence = candidate["confidence"]

    validate_exact_keys(
        confidence,
        {
            "evidence_confidence",
            "abstraction_confidence",
            "applicability_confidence",
            "oracle_guidance_confidence"
        },
        "confidence"
    )

    for key, value in confidence.items():
        validate_enum(
            value,
            vocabularies["confidence"],
            f"confidence.{key}"
        )

    if (
        statement["evidence_status"] == "analyst_inferred"
        and confidence["abstraction_confidence"] == "high"
    ):
        raise ValueError(
            "abstraction_confidence cannot be high when "
            "knowledge_statement is analyst_inferred"
        )

    if (
        not applicability_is_active
        and confidence["applicability_confidence"] != "low"
    ):
        raise ValueError(
            "applicability_confidence must be low when "
            "Applicability makes no claim"
        )

    if (
        not testing_guidance["oracle_guidance"]
        and confidence["oracle_guidance_confidence"] != "low"
    ):
        raise ValueError(
            "oracle_guidance_confidence must be low when "
            "oracle_guidance is empty"
        )

    return candidate


def collect_evidence_refs(value):
    refs = []

    def visit(item):
        if isinstance(item, dict):
            evidence_refs = item.get("evidence_refs")

            if isinstance(evidence_refs, list):
                for evidence_ref in evidence_refs:
                    if evidence_ref not in refs:
                        refs.append(evidence_ref)

            for nested in item.values():
                visit(nested)

        elif isinstance(item, list):
            for nested in item:
                visit(nested)

    visit(value)

    return refs


def next_knowledge_id(
    output_api_dir,
    framework,
    canonical_name
):
    prefix = (
        f"{framework_prefix(framework)}_"
        f"{slugify(canonical_name)}"
    )

    pattern = re.compile(
        rf"^kn_{re.escape(prefix)}_k(\d+)\.json$"
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

    return (
        f"kn_{prefix}_k{max_ordinal + 1:03d}"
    )


def has_existing_knowledge_for_pattern(
    output_api_dir,
    pattern_id
):
    if not os.path.isdir(output_api_dir):
        return False

    for filename in os.listdir(output_api_dir):
        if not filename.endswith(".json"):
            continue

        path = os.path.join(
            output_api_dir,
            filename
        )

        try:
            knowledge = load_json(path)

            input_patterns = knowledge.get(
                "derivation_information",
                {}
            ).get(
                "input_patterns",
                []
            )

            for input_pattern in input_patterns:
                if (
                    input_pattern.get("pattern_id")
                    == pattern_id
                ):
                    return True

        except (
            OSError,
            json.JSONDecodeError,
            AttributeError
        ):
            continue

    return False


def enrich_final_knowledge(
    candidate,
    pattern_context,
    knowledge_id,
    model
):
    source_refs = collect_evidence_refs(candidate)

    final_knowledge = {
        "schema_version": SCHEMA_VERSION,

        "metadata": {
            "knowledge_id": knowledge_id,
            "canonical_name": candidate[
                "canonical_name"
            ],
            "knowledge_level": "api_specific"
        },

        "derivation_information": {
            "method": "llm_assisted",
            "mapping_version": MAPPING_VERSION,
            "prompt_version": PROMPT_VERSION,
            "model": model,
            "input_patterns": [
                {
                    "pattern_id": pattern_context[
                        "pattern_id"
                    ],
                    "pattern_hash": pattern_context[
                        "pattern_hash"
                    ]
                }
            ],
            "generated_at": datetime.now(
                timezone.utc
            ).date().isoformat(),
            "validation_status": (
                "automatically_validated"
            )
        },

        "evidence_basis": {
            "supporting_patterns": [
                {
                    "pattern_id": pattern_context[
                        "pattern_id"
                    ],
                    "relation": "direct_derivation",
                    "evidence_refs": source_refs
                }
            ],
            "derivation_rationale": candidate[
                "evidence_basis"
            ]["derivation_rationale"],
            "limitations": candidate[
                "evidence_basis"
            ]["limitations"]
        },

        "scope": {
            "framework": pattern_context["framework"],
            "primary_api": pattern_context[
                "primary_api"
            ],
            "directly_supported_apis": pattern_context[
                "directly_supported_apis"
            ]
        },

        "knowledge_statement": candidate[
            "knowledge_statement"
        ],

        "applicability": candidate[
            "applicability"
        ],

        "testing_guidance": candidate[
            "testing_guidance"
        ],

        "confidence": candidate["confidence"]
    }

    for index, condition in enumerate(
        final_knowledge["applicability"][
            "applicability_conditions"
        ],
        start=1
    ):
        condition["condition_id"] = f"ac_{index:02d}"

    for index, condition in enumerate(
        final_knowledge["applicability"][
            "exclusion_conditions"
        ],
        start=1
    ):
        condition["condition_id"] = f"ec_{index:02d}"

    for index, goal in enumerate(
        final_knowledge["testing_guidance"][
            "exploration_goals"
        ],
        start=1
    ):
        goal["goal_id"] = f"eg_{index:02d}"

    return final_knowledge


def validate_api_argument(api):
    if not api.strip():
        raise ValueError("--api must not be empty")

    if "/" in api or "\\" in api or ".." in api:
        raise ValueError(
            "--api must be an API directory name, "
            "not a path"
        )

def validate_pattern_id_argument(pattern_id):
    if pattern_id is None:
        return

    if not pattern_id.strip():
        raise ValueError(
            "--pattern-id must not be empty"
        )

    if (
        "/" in pattern_id
        or "\\" in pattern_id
        or ".." in pattern_id
    ):
        raise ValueError(
            "--pattern-id must be a Pattern ID, "
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
    dry_run,
    pattern_id_filter=None
):
    validate_api_argument(api)
    validate_pattern_id_argument(pattern_id_filter)

    input_api_dir = os.path.join(
        PATTERN_DIR,
        api
    )

    output_api_dir = os.path.join(
        output_root,
        api
    )

    if not os.path.isdir(input_api_dir):
        raise RuntimeError(
            f"Input directory does not exist: "
            f"{input_api_dir}"
        )

    contract = load_json(CONTRACT_FILE)
    rules = load_text(RULE_FILE)

    generated_count = 0
    skipped_count = 0
    failed_count = 0
    needs_revision_count = 0
    selected_pattern_found = False

    for filename in sorted(os.listdir(input_api_dir)):
        if not filename.endswith(".json"):
            continue

        pattern_path = os.path.join(
            input_api_dir,
            filename
        )

        try:
            pattern = load_json(pattern_path)

            pattern_context = build_pattern_context(
                pattern
            )

        except (
            OSError,
            json.JSONDecodeError,
            ValueError
        ) as error:
            print(
                f"[FAILED] {filename}: invalid Pattern: "
                f"{error}"
            )

            failed_count += 1
            continue

        pattern_id = pattern_context["pattern_id"]

        if (
            pattern_id_filter is not None
            and pattern_id != pattern_id_filter
        ):
            continue

        selected_pattern_found = True

        if has_existing_knowledge_for_pattern(
            output_api_dir,
            pattern_id
        ):
            print(
                f"[SKIP] {filename}: existing Knowledge "
                f"already uses Pattern ID {pattern_id}"
            )

            skipped_count += 1
            continue

        print(
            f"[PROCESS] {filename} "
            f"(pattern_id={pattern_id})"
        )

        prompt = build_prompt(
            pattern_context,
            contract,
            rules
        )

        try:
            raw_response = call_deepseek(
                prompt,
                api_key,
                model,
                api_url
            )

            response = extract_json(raw_response)

            validate_response_envelope(response)

        except Exception as error:
            print(
                f"[FAILED] {filename}: LLM response "
                f"error: {error}"
            )

            failed_count += 1
            continue

        try:
            candidate = validate_candidate(
                response["knowledge"],
                pattern_context,
                contract
            )

        except Exception as error:
            print(
                f"[NEEDS_REVISION] {filename}: "
                f"{error}"
            )

            needs_revision_count += 1
            continue

        knowledge_id = next_knowledge_id(
            output_api_dir,
            pattern_context["framework"],
            candidate["canonical_name"]
        )

        final_knowledge = enrich_final_knowledge(
            candidate,
            pattern_context,
            knowledge_id,
            model
        )

        if dry_run:
            print(
                "[DRY-RUN] Valid Knowledge:",
                final_knowledge["metadata"][
                    "knowledge_id"
                ],
                "|",
                final_knowledge["metadata"][
                    "canonical_name"
                ]
            )

            generated_count += 1
            continue

        os.makedirs(
            output_api_dir,
            exist_ok=True
        )

        output_path = os.path.join(
            output_api_dir,
            f"{knowledge_id}.json"
        )

        try:
            with open(
                output_path,
                "x",
                encoding="utf-8"
            ) as output_file:
                json.dump(
                    final_knowledge,
                    output_file,
                    indent=2,
                    ensure_ascii=False
                )

            print(f"[WRITE] {output_path}")

            generated_count += 1

        except FileExistsError as error:
            print(
                f"[FAILED] {filename}: refusing to overwrite "
                f"existing Knowledge: {error}"
            )

            failed_count += 1

        except OSError as error:
            print(
                f"[FAILED] {filename}: write error: {error}"
            )

            failed_count += 1

    if (
        pattern_id_filter is not None
        and not selected_pattern_found
    ):
        raise RuntimeError(
            "No Pattern with the requested --pattern-id "
            f"was found under {input_api_dir}: "
            f"{pattern_id_filter}"
        )

    print()
    print("Knowledge extraction complete")
    print(f"Generated:      {generated_count}")
    print(f"Skipped:        {skipped_count}")
    print(f"Needs revision: {needs_revision_count}")
    print(f"Failed:         {failed_count}")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Build Knowledge v2 JSON records from "
            "API-specific historical Bug Patterns."
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
            "EXP006/knowledge_base."
        )
    )

    parser.add_argument(
        "--pattern-id",
        default=None,
        help=(
            "Optional exact Pattern ID. When provided, "
            "process only that Pattern within --api."
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
            "Call the LLM and validate the response "
            "without writing Knowledge JSON files."
        )
    )

    args = parser.parse_args()

    if not args.api_key:
        raise RuntimeError(
            "Missing DeepSeek API key. Set "
            "DEEPSEEK_API_KEY or pass --api-key."
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
        dry_run=args.dry_run,
        pattern_id_filter=args.pattern_id
    )


if __name__ == "__main__":
    main()