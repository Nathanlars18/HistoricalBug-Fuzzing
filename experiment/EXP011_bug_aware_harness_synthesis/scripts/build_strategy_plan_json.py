#!/usr/bin/env python3
"""Build validated Strategy Plan records from validated HarnessSpec records.

The Builder:

1. validates shared schemas, Contract, Rules, and Strategy Catalog;
2. resolves exact HarnessSpec, API Profile, and Helper Profile references;
3. prepares compact Strategy-synthesis views;
4. requests only a semantic implementation plan or blocking gaps from the LLM;
5. normalizes branch-local identifiers;
6. derives deterministic failure handlers;
7. validates the semantic plan and final Strategy record;
8. writes immutable Strategy records or structured diagnostics.

It does not:

- select historical Knowledge;
- change HarnessSpec branches or budgets;
- generate Strategy Catalog entries;
- emit C++ code;
- compile or execute a Harness;
- perform adaptive feedback.
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
from pathlib import Path
from typing import Any, Iterable
try:
    import requests
    import yaml
    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry, Resource
except ImportError as exc:
    raise SystemExit('Missing dependency; install environment/python-control-requirements.txt') from exc
BUILDER_VERSION = 'strategy_plan_builder_v0.9'
STRATEGY_SCHEMA_VERSION = '1.3'
CONTRACT_VERSION = '1.8'
RULES_VERSION = '1.5'

sys.path.insert(0, str(Path(__file__).resolve().parent))
from strategy_domains import infer_domains, exploration_domain_error, ordinary_recipe_errors, meaningful_fuzz_domain, companion_relation_errors
DEFAULT_MODEL = 'deepseek-v4-pro'
DEFAULT_API_URL = 'https://api.deepseek.com/chat/completions'
DEFAULT_MAX_PROMPT_CHARS = 75000
DEFAULT_MAX_REPAIR_CHARS = 8000
ROOT = Path('experiment/EXP011_bug_aware_harness_synthesis')
DEFAULTS = {'config': ROOT / 'config.yaml', 'catalog': ROOT / 'strategy_primitives' / 'strategy_primitive_catalog.json', 'harness_spec_schema': ROOT / 'schemas' / 'harness_spec_record.schema.json', 'harness_spec_schema_core': ROOT / 'schemas' / 'harness_spec_record_core__v2_2.schema.json', 'harness_spec_review_schema': ROOT / 'schemas' / 'harness_spec_review_record.schema.json', 'strategy_review_schema': ROOT / 'schemas' / 'strategy_plan_review_record.schema.json', 'api_profile_schema': ROOT / 'schemas' / 'api_profile_record.schema.json', 'helper_profile_schema': ROOT / 'schemas' / 'helper_profile_record.schema.json', 'catalog_schema': ROOT / 'schemas' / 'strategy_catalog_record.schema.json', 'record_schema': ROOT / 'schemas' / 'strategy_plan_record.schema.json', 'contract': ROOT / 'schemas' / 'strategy_synthesis_contract.json', 'rules': ROOT / 'schemas' / 'harness_spec_to_strategy_rules.md', 'api_profiles': ROOT / 'api_profiles', 'helper_profiles': ROOT / 'helper_profiles', 'output_root': ROOT / 'strategy_primitives'}
IDENTIFIER_RE = re.compile('^[a-z][a-z0-9_]*$')
SHA256_RE = re.compile('^[0-9a-f]{64}$')
SLOTS = ['input_construction', 'pre_call_transform', 'pre_call_guard', 'pre_call_observation', 'target_call', 'post_call_observation', 'oracle_check', 'artifact_logging', 'cleanup']
PRE_CALL_SLOTS = {'input_construction', 'pre_call_transform', 'pre_call_guard', 'pre_call_observation'}
VALUE_KINDS = {'raw_bytes', 'byte_cursor', 'boolean', 'integer', 'floating', 'string', 'scalar', 'dtype', 'rank', 'shape', 'device', 'layout', 'tensor', 'tensor_list', 'optional_value', 'tuple_value', 'exception_state', 'observation_result', 'artifact'}
PRIMITIVE_KINDS = {'input_decode', 'value_construct', 'value_transform', 'relation_enforce', 'predicate_evaluate', 'target_api_invoke', 'oracle_evaluate', 'artifact_record'}
TRACEABLE_SPEC_TYPES = {
    'global_constraint',
    'branch_constraint',
    'target_condition',
    'behavior_observation',
    'behavior_check',
}
PARAMETER_SOURCE_TYPES = {
    'global_constraint',
    'branch_constraint',
    'target_condition',
    'behavior_check',
}
RUNNER_EVENTS = {
    'target_api_reached',
    'target_api_returned',
    'caught_exception',
    'process_exit',
    'process_signal',
    'timeout',
    'sanitizer_report',
    'coverage_observation',
}
BLOCKING_REASON_CODES = {'required_capability_unavailable', 'api_input_unconstructable', 'type_flow_unresolvable', 'required_observation_unavailable', 'required_oracle_unavailable', 'semantic_conflict_unresolvable'}
TERMINAL_ACTIONS = {'reject_input', 'record_and_return'}

class BuildError(RuntimeError):
    """Base class for expected Builder failures."""

class GlobalInputError(BuildError):
    """A shared Schema, Contract, Rules, Catalog, or configuration failed."""

class ItemInputError(BuildError):
    """One HarnessSpec or one of its exact references failed."""

class CapabilityGap(ItemInputError):
    """A valid intent has no exact local adapter; not an invalid Knowledge record."""

class LLMError(BuildError):
    """The LLM request or returned representation failed."""

class PlanValidationError(BuildError):
    """The semantic Strategy plan failed validation."""

@dataclass
class Outcome:
    harness_spec: str
    target_api: str | None
    mode: str | None
    status: str
    attempts: int = 0
    output_path: str | None = None
    diagnostics_path: str | None = None
    message: str = ''

@dataclass(frozen=True)
class ResolvedInputs:
    spec: dict[str, Any]
    api: dict[str, Any]
    resolved_api_primitive: dict[str, Any]
    candidate_primitives: list[dict[str, Any]]
    harness_spec_review_ref: dict[str, Any]

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

def new_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    return f'run_{timestamp}_{uuid.uuid4().hex[:12]}'

def load_json(path: Path, *, global_input: bool=False) -> Any:
    error_type = GlobalInputError if global_input else ItemInputError
    try:
        with path.open('r', encoding='utf-8') as handle:
            return json.load(handle, object_pairs_hook=reject_duplicate_json_keys)
    except FileNotFoundError as exc:
        raise error_type(f'Required file does not exist: {path}') from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise error_type(f'Invalid JSON in {path}: {exc}') from exc

def reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for (key, value) in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result

def load_text(path: Path, *, global_input: bool=False) -> str:
    error_type = GlobalInputError if global_input else ItemInputError
    try:
        return path.read_text(encoding='utf-8')
    except FileNotFoundError as exc:
        raise error_type(f'Required file does not exist: {path}') from exc

def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda : handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()

def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()

def profile_content_hash(profile: dict[str, Any]) -> str:
    value = copy.deepcopy(profile)
    value['metadata'].pop('content_hash', None)
    return canonical_hash(value)

def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PlanValidationError(f'{label} must be an object')
    return value

def require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise PlanValidationError(f'{label} must be an array')
    return value

def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlanValidationError(f'{label} must be a non-empty string')
    return value

def require_identifier(value: Any, label: str) -> str:
    value = require_string(value, label)
    if not IDENTIFIER_RE.fullmatch(value):
        raise PlanValidationError(f'{label} is not a valid identifier: {value!r}')
    return value

def reject_unknown_keys(value: dict[str, Any], allowed: set[str], label: str) -> None:
    extras = sorted(set(value) - allowed)
    if extras:
        raise PlanValidationError(f'{label} has unsupported fields: {extras}')

def ensure_unique(values: Iterable[Any], label: str) -> None:
    seen: set[str] = set()
    for value in values:
        marker = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if marker in seen:
            raise PlanValidationError(f'{label} contains a duplicate value')
        seen.add(marker)

def safe_component(value: str) -> str:
    result = re.sub('[^A-Za-z0-9]+', '_', value.strip()).strip('_').lower()
    if not result:
        raise ItemInputError('A path or identifier component became empty')
    if not result[0].isalpha():
        result = 'x_' + result
    return result

def schema_validator(
    schema: dict[str, Any],
    label: str,
    resources: list[dict[str, Any]] | None = None,
) -> Draft202012Validator:
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        raise GlobalInputError(f'Invalid JSON Schema for {label}: {exc}') from exc
    registry = Registry()
    for resource_schema in resources or []:
        registry = registry.with_resource(
            resource_schema['$id'], Resource.from_contents(resource_schema)
        )
    return Draft202012Validator(
        schema,
        registry=registry,
        format_checker=FormatChecker(),
    )

def validate_against(value: Any, validator: Draft202012Validator, label: str, error_type: type[BuildError]) -> None:
    errors = sorted(validator.iter_errors(value), key=lambda item: item.json_path)
    if not errors:
        return
    message = '\n'.join((f'{item.json_path}: {item.message}' for item in errors[:12]))
    raise error_type(f'{label} violates its JSON Schema:\n{message}')

def artifact_ref(path: Path, artifact_id: str, version: str | int) -> dict[str, Any]:
    return {'artifact_id': require_identifier(artifact_id, 'artifact_id'), 'artifact_version': version, 'content_hash': file_hash(path)}

def profile_key(reference: dict[str, Any]) -> tuple[str, int, str]:
    try:
        profile_id = reference['profile_id']
        revision = reference['revision']
        content_hash = reference['content_hash']
    except (KeyError, TypeError) as exc:
        raise ItemInputError(f'Malformed Profile Reference: {reference!r}') from exc
    if not isinstance(profile_id, str) or not profile_id.strip() or (not isinstance(revision, int)) or (revision < 1):
        raise ItemInputError(f'Malformed Profile identity: {reference!r}')
    if not isinstance(content_hash, str) or not SHA256_RE.fullmatch(content_hash):
        raise ItemInputError(f'Malformed Profile content hash: {reference!r}')
    return (profile_id, revision, content_hash)

def record_profile_key(record: dict[str, Any]) -> tuple[str, int, str]:
    try:
        return (record['profile_id'], record['revision'], record['metadata']['content_hash'])
    except (KeyError, TypeError) as exc:
        raise GlobalInputError('Profile record lacks an exact identity or content hash') from exc

def read_profile_store(root: Path, validator: Draft202012Validator, label: str) -> dict[tuple[str, int, str], dict[str, Any]]:
    if not root.is_dir():
        raise GlobalInputError(f'{label} directory does not exist: {root}')
    store: dict[tuple[str, int, str], dict[str, Any]] = {}
    revisions: dict[tuple[str, int], str] = {}
    filename_pattern = {
        'API Profile': 'api_profile__*__r*.json',
        'Helper Profile': 'helper_profile__*__r*.json',
    }.get(label, '*.json')
    paths = sorted(
        path
        for path in root.rglob(filename_pattern)
        if path.is_file()
        and '_runs' not in path.parts
        and 'legacy' not in path.parts
    )
    for path in paths:
        record = load_json(path, global_input=True)
        validate_against(record, validator, f'{label} {path}', GlobalInputError)
        key = record_profile_key(record)
        expected_hash = profile_content_hash(record)
        if key[2] != expected_hash:
            raise GlobalInputError(f'{label} {path} has a non-reproducible metadata.content_hash')
        revision_key = (key[0], key[1])
        if revision_key in revisions:
            raise GlobalInputError(f'Duplicate {label} revision: {revision_key}; hashes are {revisions[revision_key]} and {key[2]}')
        revisions[revision_key] = key[2]
        if key in store:
            raise GlobalInputError(f'Duplicate exact {label} reference: {key}')
        store[key] = record
    return store

def read_harness_spec_review_store(
    paths: list[Path],
    validator: Draft202012Validator,
) -> dict[tuple[str, int, str], tuple[dict[str, Any], Path]]:
    store: dict[tuple[str, int, str], tuple[dict[str, Any], Path]] = {}
    for path in paths:
        review = load_json(path, global_input=True)
        if review.get('record_type') == 'budget_derivation_certificate':
            from budget_derivation import validate
            try:
                validate(review, path, Path(review['subject']['relative_path']), 'spec')
            except (ValueError, KeyError) as exc:
                raise GlobalInputError(str(exc)) from exc
            subject = review['subject']
            key = (subject['spec_id'], subject['revision_number'], subject['content_hash'])
            if key in store:
                raise GlobalInputError(f'Duplicate authorization for {key}')
            store[key] = (review, path)
            continue
        validate_against(
            review,
            validator,
            f'HarnessSpec review {path}',
            GlobalInputError,
        )
        if review['decision'] != 'approved':
            raise GlobalInputError(
                f'HarnessSpec review is not approved: {path}'
            )
        subject = review['subject']
        key = (
            subject['spec_id'],
            subject['revision_number'],
            subject['content_hash'],
        )
        if key in store:
            raise GlobalInputError(
                f'Duplicate approved HarnessSpec review for {key}'
            )
        store[key] = (review, path)
    return store

def resolve_harness_spec_review(
    spec: dict[str, Any],
    spec_path: Path,
    review_store: dict[tuple[str, int, str], tuple[dict[str, Any], Path]],
) -> dict[str, Any]:
    key = (
        spec['identity']['spec_id'],
        spec['revision_information']['revision_number'],
        canonical_hash(spec),
    )
    stored = review_store.get(key)
    if stored is None:
        raise ItemInputError(
            'An exact approved HarnessSpec review is required for Strategy synthesis'
        )
    review, review_path = stored
    subject_path = Path(review['subject']['relative_path'])
    if subject_path.resolve() != spec_path.resolve():
        raise ItemInputError(
            'HarnessSpec review subject path does not match --harness-spec'
        )
    return {
        'review_id': review['review_id'],
        'review_revision': review['review_revision'],
        'content_hash': canonical_hash(review),
        'relative_path': str(review_path),
    }

def helper_is_ready_and_approved(profile: dict[str, Any]) -> bool:
    return profile.get('validation', {}).get('execution_readiness') == 'ready' and profile.get('review', {}).get('review_status') == 'approved'

def api_is_ready_and_approved(profile: dict[str, Any]) -> bool:
    return profile.get('target_binding', {}).get('status') == 'resolved' and profile.get('validation', {}).get('validation_status') == 'passed' and (profile.get('validation', {}).get('execution_readiness') == 'ready') and (profile.get('review', {}).get('review_status') == 'approved')

def catalog_review_is_approved(catalog: dict[str, Any]) -> bool:
    review = catalog.get('review')
    return isinstance(review, dict) and review.get('validation_status') == 'passed' and (review.get('human_review_status') == 'approved')

def validate_exact_profile_ref(reference: Any, label: str) -> dict[str, Any] | None:
    if reference is None:
        return None
    value = require_object(reference, label)
    expected = {'profile_id', 'revision', 'content_hash'}
    reject_unknown_keys(value, expected, label)
    if set(value) != expected:
        raise PlanValidationError(f'{label} is incomplete')
    profile_key(value)
    return value

def validate_catalog(value: Any, validator: Draft202012Validator, harness_spec_schema: dict[str, Any]) -> dict[str, Any]:
    """Validate Catalog fields needed by this Builder.

    JSON Schema owns record shape. This function owns cross-field semantics,
    identifier uniqueness, and compatibility with the HarnessSpec v2.2
    lifecycle boundary. Predicate identifiers remain open vocabulary in the
    HarnessSpec; the Catalog declares the exact subset each Primitive can
    materialize.
    """
    validate_against(value, validator, 'Strategy Catalog', PlanValidationError)
    catalog = require_object(value, 'Strategy Catalog')
    if harness_spec_schema.get('$id') != 'urn:historicalbug-fuzzing:schema:harness-spec-record:2.2':
        raise PlanValidationError('Strategy v1.2 requires HarnessSpec Schema v2.2')
    expected_root = {'schema_version', 'catalog_id', 'catalog_version', 'target_language', 'template_interface', 'primitives', 'provenance', 'review'}
    reject_unknown_keys(catalog, expected_root | {'argument_relation_rules'}, 'Strategy Catalog')
    if not expected_root <= set(catalog):
        raise PlanValidationError('Strategy Catalog is missing required root fields')
    if catalog['schema_version'] != '1.1':
        raise PlanValidationError('Catalog schema_version must be 1.1')
    if catalog['target_language'] != 'cpp':
        raise PlanValidationError('Catalog target_language must be cpp')
    require_identifier(catalog['catalog_id'], 'catalog_id')
    if not isinstance(catalog['catalog_version'], int) or catalog['catalog_version'] < 1:
        raise PlanValidationError('catalog_version must be a positive integer')
    if not catalog_review_is_approved(catalog):
        raise PlanValidationError('Catalog must have validation_status=passed and human_review_status=approved')
    interface = require_object(catalog['template_interface'], 'template_interface')
    expected_interface = {'template_ref', 'available_slots', 'built_in_values'}
    if set(interface) != expected_interface:
        raise PlanValidationError('template_interface has incorrect fields')
    template_ref = require_object(interface['template_ref'], 'template_ref')
    if set(template_ref) != {'artifact_id', 'artifact_version', 'content_hash'}:
        raise PlanValidationError('template_ref must be an exact Artifact Reference')
    require_identifier(template_ref['artifact_id'], 'template_ref.artifact_id')
    if not isinstance(template_ref['content_hash'], str) or not SHA256_RE.fullmatch(template_ref['content_hash']):
        raise PlanValidationError('template_ref.content_hash must be a lowercase SHA-256 hash')
    slots = require_list(interface['available_slots'], 'available_slots')
    if not slots:
        raise PlanValidationError('available_slots must not be empty')
    if any((slot not in SLOTS for slot in slots)):
        raise PlanValidationError('available_slots contains an unknown slot')
    ensure_unique(slots, 'available_slots')
    if slots != sorted(slots, key=SLOTS.index):
        raise PlanValidationError('available_slots does not follow the canonical slot order')
    builtins = require_list(interface['built_in_values'], 'built_in_values')
    if not builtins:
        raise PlanValidationError('built_in_values must not be empty')
    builtin_ids: list[str] = []
    for (index, item) in enumerate(builtins):
        item = require_object(item, f'built_in_values[{index}]')
        if set(item) != {'value_id', 'value_kind', 'description'}:
            raise PlanValidationError(f'built_in_values[{index}] has incorrect fields')
        builtin_ids.append(require_identifier(item['value_id'], f'built_in_values[{index}].value_id'))
        if item['value_kind'] not in VALUE_KINDS:
            raise PlanValidationError(f'built_in_values[{index}] has unknown value_kind')
        require_string(item['description'], f'built_in_values[{index}].description')
    ensure_unique(builtin_ids, 'built-in value IDs')
    primitives = require_list(catalog['primitives'], 'primitives')
    if not primitives:
        raise PlanValidationError('Catalog primitives must not be empty')
    primitive_ids: list[str] = []
    api_primitive_ids: list[str] = []
    for (index, primitive) in enumerate(primitives):
        validate_catalog_primitive(primitive, index, slots)
        primitive_ids.append(primitive['primitive_id'])
        if primitive['primitive_kind'] == 'target_api_invoke':
            api_primitive_ids.append(primitive['primitive_id'])
    ensure_unique(primitive_ids, 'Primitive IDs')
    if len(api_primitive_ids) != 1:
        raise PlanValidationError('Catalog must contain exactly one target_api_invoke Primitive')
    api_primitive = next((item for item in primitives if item['primitive_kind'] == 'target_api_invoke'))
    if api_primitive['allowed_template_slots'] != ['target_call']:
        raise PlanValidationError('target_api_invoke must be restricted to the target_call slot')
    ensure_unique([r['rule_id'] for r in catalog.get('argument_relation_rules', [])], 'argument relation rule IDs')
    for rule in catalog.get('argument_relation_rules', []):
        evidence = rule['evidence']
        if hashlib.sha256(evidence['excerpt'].encode()).hexdigest() != evidence['excerpt_sha256']:
            raise PlanValidationError('Argument relation source excerpt hash mismatch')
        if f"/blob/{rule['framework_commit']}/" not in evidence['source_url']:
            raise PlanValidationError('Argument relation evidence must use the exact framework commit')
    return catalog

def validate_catalog_primitive(value: Any, index: int, catalog_slots: list[str]) -> None:
    primitive = require_object(value, f'primitives[{index}]')
    required = {'primitive_id', 'primitive_kind', 'summary', 'semantic_support', 'allowed_template_slots', 'input_contract', 'output_contract', 'parameter_contract', 'outcome_contract', 'implementation_binding', 'limitations'}
    reject_unknown_keys(primitive, required, f'primitives[{index}]')
    if set(primitive) != required:
        raise PlanValidationError(f'primitives[{index}] is incomplete')
    require_identifier(primitive['primitive_id'], f'primitives[{index}].primitive_id')
    if primitive['primitive_kind'] not in PRIMITIVE_KINDS:
        raise PlanValidationError(f'primitives[{index}] has an unknown primitive_kind')
    require_string(primitive['summary'], f'primitives[{index}].summary')
    support = require_object(primitive['semantic_support'], f'primitives[{index}].semantic_support')
    expected_support = {
        'predicate_ids',
        'condition_roles',
        'observation_phases',
        'behavior_check_levels',
        'subject_kinds',
        'fuzz_dependency',
    }
    if set(support) != expected_support:
        raise PlanValidationError(f'primitives[{index}].semantic_support has incorrect fields')
    for name in (
        'predicate_ids',
        'condition_roles',
        'observation_phases',
        'behavior_check_levels',
        'subject_kinds',
    ):
        values = require_list(support[name], f'primitives[{index}].semantic_support.{name}')
        ensure_unique(values, f'primitives[{index}].semantic_support.{name}')
        for item in values:
            require_string(item, f'primitives[{index}].semantic_support.{name}')
    if any(role not in {'activation_required', 'exploration_variable'} for role in support['condition_roles']):
        raise PlanValidationError('semantic_support.condition_roles contains an unknown role')
    if any(phase not in {'before_target_api_call', 'after_target_api_call', 'on_target_api_termination'} for phase in support['observation_phases']):
        raise PlanValidationError('semantic_support.observation_phases contains an unknown phase')
    if any(level not in {'required', 'preferred'} for level in support['behavior_check_levels']):
        raise PlanValidationError('semantic_support.behavior_check_levels contains an unknown level')
    if support['fuzz_dependency'] not in {'none', 'propagates', 'produces'}:
        raise PlanValidationError('semantic_support.fuzz_dependency is invalid')
    allowed_slots = require_list(primitive['allowed_template_slots'], f'primitives[{index}].allowed_template_slots')
    if not allowed_slots or any((slot not in catalog_slots for slot in allowed_slots)):
        raise PlanValidationError(f'primitives[{index}] has an unavailable template slot')
    ensure_unique(allowed_slots, f'primitives[{index}].allowed_template_slots')
    validate_input_ports(primitive['input_contract'], index)
    validate_output_ports(primitive['output_contract'], index)
    validate_parameter_contract(primitive['parameter_contract'], index)
    outcome_contract = require_object(primitive['outcome_contract'], f'primitives[{index}].outcome_contract')
    if set(outcome_contract) != {'failure_outcomes'}:
        raise PlanValidationError(f'primitives[{index}].outcome_contract has incorrect fields')
    outcome_ids: list[str] = []
    for (outcome_index, outcome) in enumerate(require_list(outcome_contract['failure_outcomes'], f'primitives[{index}].failure_outcomes')):
        outcome = require_object(outcome, f'primitives[{index}].failure_outcomes[{outcome_index}]')
        if set(outcome) != {'outcome_id', 'description', 'terminal_action'}:
            raise PlanValidationError('Failure Outcome has incorrect fields')
        outcome_id = require_identifier(outcome['outcome_id'], 'failure_outcome.outcome_id')
        if outcome_id == 'success':
            raise PlanValidationError('success is reserved and cannot be a failure outcome')
        if outcome['terminal_action'] not in TERMINAL_ACTIONS:
            raise PlanValidationError('Failure Outcome has an unknown terminal_action')
        require_string(outcome['description'], 'failure_outcome.description')
        outcome_ids.append(outcome_id)
    ensure_unique(outcome_ids, f'primitives[{index}] failure outcome IDs')
    binding = require_object(primitive['implementation_binding'], f'primitives[{index}].implementation_binding')
    if set(binding) != {'kind', 'emitter_id', 'helper_profile_ref'}:
        raise PlanValidationError('implementation_binding has incorrect fields')
    if binding['kind'] not in {'helper_backed', 'generator_native', 'api_binding'}:
        raise PlanValidationError('implementation_binding.kind is unknown')
    require_identifier(binding['emitter_id'], 'implementation_binding.emitter_id')
    helper_ref = validate_exact_profile_ref(binding['helper_profile_ref'], 'implementation_binding.helper_profile_ref')
    if (binding['kind'] == 'helper_backed') != (helper_ref is not None):
        raise PlanValidationError('helper_profile_ref conflicts with implementation kind')
    if primitive['primitive_kind'] == 'target_api_invoke' and binding['kind'] != 'api_binding':
        raise PlanValidationError('target_api_invoke must use api_binding')
    if binding['kind'] == 'api_binding' and primitive['primitive_kind'] != 'target_api_invoke':
        raise PlanValidationError('api_binding is reserved for target_api_invoke')
    limitations = require_list(primitive['limitations'], f'primitives[{index}].limitations')
    for item in limitations:
        require_string(item, f'primitives[{index}].limitations')

def validate_input_ports(value: Any, primitive_index: int) -> None:
    ports = require_list(value, f'primitives[{primitive_index}].input_contract')
    port_ids: list[str] = []
    for (index, port) in enumerate(ports):
        port = require_object(port, f'input_contract[{index}]')
        if set(port) != {'port_id', 'accepted_value_kinds', 'required'}:
            raise PlanValidationError('Input Port has incorrect fields')
        port_ids.append(require_identifier(port['port_id'], 'input_port.port_id'))
        kinds = require_list(port['accepted_value_kinds'], 'input_port.accepted_value_kinds')
        if not kinds or any((kind not in VALUE_KINDS for kind in kinds)):
            raise PlanValidationError('Input Port has an invalid accepted_value_kinds value')
        ensure_unique(kinds, 'Input Port value kinds')
        if not isinstance(port['required'], bool):
            raise PlanValidationError('Input Port required must be boolean')
    ensure_unique(port_ids, 'Input Port IDs')

def validate_output_ports(value: Any, primitive_index: int) -> None:
    ports = require_list(value, f'primitives[{primitive_index}].output_contract')
    port_ids: list[str] = []
    for (index, port) in enumerate(ports):
        port = require_object(port, f'output_contract[{index}]')
        if set(port) != {'port_id', 'produced_value_kind', 'binding_required'}:
            raise PlanValidationError('Output Port has incorrect fields')
        port_ids.append(require_identifier(port['port_id'], 'output_port.port_id'))
        if port['produced_value_kind'] not in VALUE_KINDS:
            raise PlanValidationError('Output Port has an unknown produced_value_kind')
        if not isinstance(port['binding_required'], bool):
            raise PlanValidationError('Output Port binding_required must be boolean')
    ensure_unique(port_ids, 'Output Port IDs')

def validate_parameter_contract(value: Any, primitive_index: int) -> None:
    parameters = require_list(value, f'primitives[{primitive_index}].parameter_contract')
    parameter_ids: list[str] = []
    for (index, parameter) in enumerate(parameters):
        parameter = require_object(parameter, f'parameter_contract[{index}]')
        allowed = {'parameter_id', 'value_kind', 'required', 'allowed_binding_kinds', 'default_value', 'allowed_values'}
        reject_unknown_keys(parameter, allowed, f'parameter_contract[{index}]')
        required = {'parameter_id', 'value_kind', 'required', 'allowed_binding_kinds'}
        if not required.issubset(parameter):
            raise PlanValidationError('Parameter Contract is incomplete')
        parameter_ids.append(require_identifier(parameter['parameter_id'], 'parameter_id'))
        if parameter['value_kind'] not in VALUE_KINDS:
            raise PlanValidationError('Parameter Contract has an unknown value_kind')
        if not isinstance(parameter['required'], bool):
            raise PlanValidationError('Parameter required must be boolean')
        kinds = require_list(parameter['allowed_binding_kinds'], 'allowed_binding_kinds')
        if not kinds or any((kind not in {'literal', 'value_ref', 'spec_parameter'} for kind in kinds)):
            raise PlanValidationError('Parameter Contract contains an invalid binding kind')
        ensure_unique(kinds, 'Parameter binding kinds')
        if 'allowed_values' in parameter:
            allowed_values = require_list(parameter['allowed_values'], 'allowed_values')
            if not allowed_values:
                raise PlanValidationError('allowed_values must be non-empty when present')
    ensure_unique(parameter_ids, 'Parameter IDs')

def api_schema_type_to_kinds(schema_type: str) -> list[str]:
    compact = re.sub('\\s+', '', schema_type).lower()
    optional = compact.endswith('?') or 'optional' in compact
    compact = compact.rstrip('?')
    if 'tensor[]' in compact or 'tensorlist' in compact:
        base = 'tensor_list'
    elif 'tensor' in compact:
        base = 'tensor'
    elif 'scalartype' in compact or 'dtype' in compact:
        base = 'dtype'
    elif 'int[]' in compact or 'symint[]' in compact or 'intarrayref' in compact:
        base = 'shape'
    elif 'device' in compact:
        base = 'device'
    elif 'layout' in compact or 'memoryformat' in compact:
        base = 'layout'
    elif 'bool' in compact:
        base = 'boolean'
    elif any((token in compact for token in ('float', 'double'))):
        base = 'floating'
    elif any((token in compact for token in ('symint', 'int', 'long'))):
        base = 'integer'
    elif 'scalar' in compact or 'number' in compact:
        base = 'scalar'
    elif 'str' in compact or 'string' in compact:
        base = 'string'
    else:
        raise ItemInputError(f'Unsupported API binding schema type: {schema_type!r}')
    if optional:
        return [base, 'optional_value']
    return [base]

def normalized_return_kind(result: dict[str, Any]) -> str:
    normalized_types = set(result.get('normalized_types', []))
    semantic_role = result.get('semantic_role')
    if 'tensor_sequence' in normalized_types or semantic_role == 'result_tensor_sequence':
        return 'tensor_list'
    if {'tensor', 'index_tensor'}.intersection(normalized_types) or semantic_role == 'result_tensor':
        return 'tensor'
    if 'boolean' in normalized_types or semantic_role == 'boolean_result':
        return 'boolean'
    if {'integer', 'index'}.intersection(normalized_types) or semantic_role == 'index_result':
        return 'integer'
    if 'shape' in normalized_types or semantic_role == 'shape_result':
        return 'shape'
    if {'scalar', 'number', 'floating'}.intersection(normalized_types) or semantic_role == 'scalar_result':
        return 'scalar'
    if len(normalized_types) > 1 or semantic_role == 'object_result':
        return 'tuple_value'
    raise ItemInputError(f"Cannot map API return {result.get('return_id')!r} to a Strategy value kind")

def resolve_api_output_ports(api: dict[str, Any]) -> list[dict[str, Any]]:
    mappings = api['target_binding']['return_mapping']
    if any(m['mapping_kind'] == 'omitted' for m in mappings) and any(m['mapping_kind'] != 'omitted' for m in mappings):
        raise ItemInputError('Partial return omission needs an explicit tuple-position adapter')
    returns = {item['return_id']: item for item in api['python_contract']['returns']}
    ports: list[dict[str, Any]] = []
    seen_refs: set[str] = set()
    for mapping in sorted(api['target_binding']['return_mapping'], key=lambda item: item['binding_return_position']):
        kind = mapping['mapping_kind']
        if kind == 'omitted':
            continue
        if kind != 'direct':
            raise ItemInputError(f'No deterministic adapter exists for API return mapping kind {kind!r}')
        return_ref = mapping['python_return_ref']
        if return_ref is None or return_ref not in returns:
            raise ItemInputError('API return mapping does not resolve to one documented Python return')
        if return_ref in seen_refs:
            raise ItemInputError(f'API return mapping repeats Python return reference {return_ref!r}')
        value_kind = normalized_return_kind(returns[return_ref])
        if kind == 'packed' and value_kind not in {'tuple_value', 'tensor_list'}:
            raise ItemInputError('A packed API return must resolve to tuple_value or tensor_list')
        seen_refs.add(return_ref)
        ports.append({'port_id': return_ref, 'produced_value_kind': value_kind, 'binding_required': True})
    return ports

def resolve_api_primitive(catalog: dict[str, Any], api: dict[str, Any]) -> dict[str, Any]:
    primitive = next((item for item in catalog['primitives'] if item['primitive_kind'] == 'target_api_invoke'))
    binding = api['target_binding']
    input_ports: list[dict[str, Any]] = []
    for parameter in sorted(binding['binding_parameters'], key=lambda item: item['ordinal']):
        accepted_kinds = api_schema_type_to_kinds(parameter['schema_type'])
        has_api_default = parameter['default'] is not None
        input_ports.append({
            'port_id': parameter['binding_parameter_id'],
            'accepted_value_kinds': accepted_kinds,
            'required': not has_api_default,
            'binding_policy': (
                'api_default_when_omitted'
                if has_api_default
                else 'explicit_value_required'
            ),
            'api_default': parameter['default'] if has_api_default else None,
            'accepts_none': 'optional_value' in accepted_kinds,
        })
    output_ports = resolve_api_output_ports(api)
    resolved_primitive = copy.deepcopy(primitive)
    resolved_primitive['input_contract'] = [
        {
            'port_id': item['port_id'],
            'accepted_value_kinds': item['accepted_value_kinds'],
            'required': item['required'],
        }
        for item in input_ports
    ]
    resolved_primitive['output_contract'] = output_ports
    return {'target_api_primitive_id': primitive['primitive_id'], 'input_ports': input_ports, 'output_ports': output_ports, 'api_binding': {'api_profile_ref': {'profile_id': api['profile_id'], 'revision': api['revision'], 'content_hash': api['metadata']['content_hash']}, 'operator_name': binding['operator_name'], 'operator_overload': binding['operator_overload'], 'cpp_callable': binding['cpp_callable'], 'argument_mapping': copy.deepcopy(binding['argument_mapping']), 'return_mapping': copy.deepcopy(binding['return_mapping'])}, '_resolved_primitive': resolved_primitive}

def validate_spec_source(spec: dict[str, Any]) -> None:
    if spec['review']['validation_status'] != 'passed':
        raise ItemInputError('HarnessSpec must have review.validation_status=passed')
    lifecycle = spec['revision_information']['lifecycle_status']
    if lifecycle not in {'draft', 'active'}:
        raise ItemInputError('HarnessSpec lifecycle_status is not usable')

def resolve_item_inputs(
    spec_path: Path,
    catalog: dict[str, Any],
    spec_validator: Draft202012Validator,
    api_store: dict[tuple[str, int, str], dict[str, Any]],
    helper_store: dict[tuple[str, int, str], dict[str, Any]],
    review_store: dict[tuple[str, int, str], tuple[dict[str, Any], Path]],
) -> ResolvedInputs:
    spec = load_json(spec_path)
    validate_against(spec, spec_validator, f'HarnessSpec {spec_path}', ItemInputError)
    validate_spec_source(spec)
    review_ref = resolve_harness_spec_review(spec, spec_path, review_store)
    api_key = profile_key(spec['target_context']['api_profile_ref'])
    api = api_store.get(api_key)
    if api is None:
        raise ItemInputError(f'Exact API Profile is unavailable: {api_key}')
    if not api_is_ready_and_approved(api):
        raise ItemInputError('Exact API Profile is not resolved, ready, passed, and approved')
    identity = spec['identity']
    target = api['target']
    if identity['framework'] != target['framework'] or identity['target_api'] != target['python_api']:
        raise ItemInputError('HarnessSpec identity conflicts with its API Profile')
    available_helpers: dict[tuple[str, int, str], dict[str, Any]] = {}
    for reference in spec['target_context']['available_helper_profile_refs']:
        key = profile_key(reference)
        helper = helper_store.get(key)
        if helper is None:
            raise ItemInputError(f'Exact Helper Profile is unavailable: {key}')
        if not helper_is_ready_and_approved(helper):
            raise ItemInputError(f'Helper Profile is not ready and approved: {key[0]}')
        available_helpers[key] = helper
    resolved_api = resolve_api_primitive(catalog, api)
    candidate_primitives: list[dict[str, Any]] = []
    for primitive in catalog['primitives']:
        binding = primitive['implementation_binding']
        if binding['kind'] == 'helper_backed':
            helper_key = profile_key(binding['helper_profile_ref'])
            if helper_key not in available_helpers:
                continue
        if primitive['primitive_id'] == resolved_api['target_api_primitive_id']:
            continue
        candidate_primitives.append(primitive)
    if not candidate_primitives:
        raise ItemInputError('No eligible Strategy Primitive remains for this HarnessSpec')
    return ResolvedInputs(
        spec=spec,
        api=api,
        resolved_api_primitive=resolved_api,
        candidate_primitives=candidate_primitives,
        harness_spec_review_ref=review_ref,
    )

def spec_element_id(element_type: str, value: dict[str, Any]) -> str:
    id_fields = {
        'global_constraint': 'constraint_id',
        'branch_constraint': 'constraint_id',
        'target_condition': 'condition_id',
        'behavior_observation': 'observation_id',
        'behavior_check': 'check_id',
    }
    return require_string(value[id_fields[element_type]], f'{element_type} ID')

def branch_element_entries(spec: dict[str, Any], branch: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    groups = [
        ('global_constraint', spec['validity_constraints']['global_constraints']),
        ('branch_constraint', branch['branch_constraints']),
        ('target_condition', branch['target_conditions']),
        ('behavior_observation', branch['behavior_observations']),
        ('behavior_check', branch['behavior_checks']),
    ]
    for (element_type, values) in groups:
        for value in values:
            required = element_type != 'behavior_check' or value['requirement_level'] == 'required'
            entries.append({'source_branch_id': branch['branch_id'], 'spec_element_type': element_type, 'spec_element_id': spec_element_id(element_type, value), 'required': required, 'value': value})
    return entries

def all_element_entries(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return [entry for branch in spec['exploration_plan']['branches'] for entry in branch_element_entries(spec, branch)]

def semantic_requirements(entry: dict[str, Any]) -> list[dict[str, Any]]:
    value = entry['value']
    element_type = entry['spec_element_type']
    if element_type in {'global_constraint', 'branch_constraint', 'target_condition'}:
        return [value['predicate']]
    if element_type == 'behavior_check':
        return [*value['preconditions'], value['expected_predicate']]
    return []
RUNTIME_REFERENCE_PARAMETER_NAMES = {'subject_ref', 'left_subject_ref', 'right_subject_ref', 'input_ref', 'output_ref', 'source_subject_ref', 'target_subject_ref', 'operand_ref', 'result_ref', 'value_ref'}

def is_runtime_reference_parameter(name: str) -> bool:
    return name in RUNTIME_REFERENCE_PARAMETER_NAMES or name.endswith('_subject_ref') or name.endswith('_value_ref')

def json_value_kind(value: Any) -> str:
    if value is None:
        return 'optional_value'
    if isinstance(value, bool):
        return 'boolean'
    if isinstance(value, int):
        return 'integer'
    if isinstance(value, float):
        return 'floating'
    if isinstance(value, str):
        return 'string'
    if isinstance(value, list):
        if value and all((isinstance(item, int) and (not isinstance(item, bool)) for item in value)):
            return 'shape'
        return 'tuple_value'
    if isinstance(value, dict):
        return 'tuple_value'
    raise ItemInputError(f'Unsupported HarnessSpec parameter value: {value!r}')

def exposed_parameters(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for entry in entries:
        if entry['spec_element_type'] not in PARAMETER_SOURCE_TYPES:
            continue
        merged: dict[str, Any] = {}
        for requirement in semantic_requirements(entry):
            for (name, value) in requirement.get('arguments', {}).items():
                if is_runtime_reference_parameter(name):
                    continue
                if name in merged and merged[name] != value:
                    raise ItemInputError(f"Ambiguous exposable HarnessSpec parameter {name!r} for {entry['spec_element_type']} {entry['spec_element_id']}")
                merged[name] = value
        for name in sorted(merged):
            result.append({'source_branch_id': entry['source_branch_id'], 'spec_element_type': entry['spec_element_type'], 'spec_element_id': entry['spec_element_id'], 'parameter_name': name, 'parameter_value': merged[name], 'value_kind': json_value_kind(merged[name])})
    return result

def build_harness_spec_view(spec: dict[str, Any]) -> dict[str, Any]:
    entries = all_element_entries(spec)
    source_branches: list[dict[str, Any]] = []
    for branch in spec['exploration_plan']['branches']:
        source_branches.append({
            'source_branch_id': branch['branch_id'],
            'branch_kind': branch['branch_kind'],
            'input_validity_intent': branch['input_validity_intent'],
            'exploration_goal': branch['exploration_goal'],
            'branch_constraints': compact_semantic_value(branch['branch_constraints']),
            'target_conditions': compact_semantic_value(branch['target_conditions']),
            'behavior_observations': compact_semantic_value(branch['behavior_observations']),
            'behavior_checks': compact_semantic_value(branch['behavior_checks']),
        })
    runner_observations = [
        entry for entry in entries
        if entry['spec_element_type'] == 'behavior_observation'
        and entry['value']['observe_at'] == 'on_target_api_termination'
    ]
    required_spec_elements = [
        {
            'source_branch_id': entry['source_branch_id'],
            'spec_element_type': entry['spec_element_type'],
            'spec_element_id': entry['spec_element_id'],
        }
        for entry in entries
        if entry['required'] and entry not in runner_observations
    ]
    runner_observation_elements = [
        {
            'source_branch_id': entry['source_branch_id'],
            'spec_element_type': entry['spec_element_type'],
            'spec_element_id': entry['spec_element_id'],
            'runner_events': [
                'target_api_returned',
                'caught_exception',
                'process_exit',
                'process_signal',
                'timeout',
                'sanitizer_report',
            ],
        }
        for entry in runner_observations
    ]
    return {
        'identity': spec['identity'],
        'global_constraints': compact_semantic_value(spec['validity_constraints']['global_constraints']),
        'source_branches': source_branches,
        'required_spec_elements': required_spec_elements,
        'runner_observation_elements': runner_observation_elements,
        'exposable_spec_parameters': exposed_parameters(entries),
    }

def compact_semantic_value(value: Any) -> Any:
    if isinstance(value, list):
        return [compact_semantic_value(item) for item in value]
    if isinstance(value, dict):
        return {key: compact_semantic_value(item) for (key, item) in value.items() if key != 'source_refs'}
    return copy.deepcopy(value)

def primitive_view(primitive: dict[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(primitive[key]) for key in ('primitive_id', 'primitive_kind', 'semantic_support', 'allowed_template_slots', 'input_contract', 'output_contract', 'parameter_contract', 'outcome_contract', 'limitations')}

def validated_ordinary_witnesses(api: dict[str, Any]) -> list[dict[str, Any]]:
    witnesses: list[dict[str, Any]] = []
    for evidence in api.get('evidence', []):
        if evidence.get('source_kind') != 'validation_case':
            continue
        location = evidence.get('source_location')
        path = Path(location) if isinstance(location, str) else None
        if path is None or not path.is_file():
            raise ItemInputError('Validation-case evidence must resolve to its original file, not a truncated excerpt')
        if file_hash(path) != evidence.get('content_hash'):
            raise ItemInputError(f'Validation-case evidence hash mismatch: {path}')
        case = load_json(path)
        arguments = case.get('arguments')
        if not isinstance(arguments, list):
            continue
        witnesses.append({
            'case_id': case.get('case_id'),
            'arguments': copy.deepcopy(arguments),
            'source_ref': artifact_ref(path, case.get('case_id', path.name), case.get('schema_version', '1.0')),
            'interpretation': (
                'Observed ordinary-valid smoke witness only. Generalize '
                'documented relations and retain fuzz freedom; do not copy '
                'its concrete shapes or fill values as test requirements.'
            ),
        })
    return witnesses

RESOURCE_POLICY_PATH = ROOT / 'strategy_primitives/strategy_resource_policy__v001.json'
ORDINARY_RECIPES_PATH = ROOT / 'strategy_primitives/ordinary_input_recipes__v001.json'

def ordinary_recipe(api: dict[str, Any]) -> dict[str, Any] | None:
    recipes = load_json(ORDINARY_RECIPES_PATH)
    for recipe in recipes['recipes']:
        if (recipe['python_api'] == api['target']['python_api']
                and recipe['framework_commit'] == api['target']['framework_commit']):
            evidence = recipe['evidence']
            if 'relative_path' in evidence and file_hash(Path(evidence['relative_path'])) != evidence['content_hash']:
                raise ItemInputError('Ordinary recipe source hash mismatch')
            return recipe
    return None

def argument_relation_rules(api: dict[str, Any], catalog: dict[str, Any]) -> list[dict[str, Any]]:
    selected = [r for r in catalog.get('argument_relation_rules', [])
                if r['python_api'] == api['target']['python_api'] and r['framework_commit'] == api['target']['framework_commit']]
    parameters = {p['binding_parameter_id']: p for p in api['target_binding']['binding_parameters']}
    for rule in selected:
        if rule['reference_port'] not in parameters or rule['dependent_port'] not in parameters:
            raise ItemInputError(f"Argument relation {rule['rule_id']} references an unavailable target port")
        dependent = parameters[rule['dependent_port']]
        expected_subject = f"param_{dependent['ordinal']:03d}_{dependent['name']}"
        if rule['dependent_subject_ref'] != expected_subject:
            raise ItemInputError(f"Argument relation {rule['rule_id']} has a mismatched dependent subject")
    return selected

def capability_preflight(resolved: ResolvedInputs, catalog: dict[str, Any]) -> None:
    """Exact supported forms, not broad semantic_support tags."""
    import build_harness_artifact as emitter
    from strategy_domains import zero_numel_form, output_check_parameters, dimension_equality_form
    template = ROOT / 'templates/libfuzzer_harness_v1.cpp.in'
    from template_contract import verify_template
    try:
        verify_template(template, catalog['template_interface']['template_ref']['content_hash'])
    except ValueError as exc:
        raise ItemInputError(str(exc)) from exc
    for primitive in catalog['primitives']:
        name = primitive['implementation_binding']['emitter_id']
        if name not in emitter.EMITTERS:
            raise CapabilityGap(f'Catalog/emitter capability gap: {name}')
    for entry in all_element_entries(resolved.spec):
        kind, value = entry['spec_element_type'], entry['value']
        if kind == 'behavior_observation':
            if value['observe_at'] != 'on_target_api_termination':
                raise CapabilityGap(f'Capability gap: standalone observation {entry["spec_element_id"]} has no exact emitter')
            continue
        if kind == 'behavior_check':
            expected = value['expected_predicate']
            survival = (expected['predicate_id'] == 'execution_survives' and value['subject_refs'] == ['context.execution']
                        and expected['arguments'] in ({}, {'subject_ref': 'context.execution'}))
            output = output_check_parameters(expected)
            if value['preconditions'] or not (survival or output):
                raise CapabilityGap(f'Capability gap: Behavior Check {entry["spec_element_id"]} needs an exact predicate/precondition adapter')
            continue
        predicate = value['predicate']
        a, pid = predicate['arguments'], predicate['predicate_id']
        if kind in {'global_constraint', 'branch_constraint'}:
            if not dimension_equality_form(predicate):
                raise CapabilityGap(f'Capability gap: constraint {entry["spec_element_id"]} requires an exact enforcement adapter; observation is insufficient')
            continue
        supported = zero_numel_form(predicate) or (
            pid == 'property_relation' and a.get('operator') == 'equals'
            and ((a.get('property_ref') == 'rank' and isinstance(a.get('value'), int))
                 or (a.get('property_ref') == 'dtype' and a.get('value') == 'int64')))
        supported |= (pid == 'cross_subject_relation' and a.get('left_property_ref') == a.get('right_property_ref')
                      and a.get('left_property_ref') in {'shape', 'rank', 'numel'}
                      and a.get('relation') in {'equals', 'not_equals'})
        if value.get('role') == 'exploration_variable' and (
            (pid == 'property_relation' and a.get('property_ref') == 'dtype')
            or ((pid == 'property_relation' and a.get('property_ref') == 'rank'
                 or pid == 'cross_subject_relation' and a.get('left_property_ref') == 'rank')
                and not any(p['primitive_id'] == 'construct_tensor_with_rank_range' for p in catalog['primitives']))):
            raise CapabilityGap(f'Capability gap: {entry["spec_element_id"]} needs a rank/dtype-varying constructor; current constructors fix these properties')
        if not supported:
            raise CapabilityGap(f'Capability gap: unsupported exact predicate form for {entry["spec_element_id"]}')

def materialization_preflight(record: dict[str, Any], resolved: ResolvedInputs,
                              catalog: dict[str, Any], helper_store: dict) -> dict[str, Any]:
    import build_harness_artifact as emitter
    try:
        inputs = emitter.ResolvedInputs(strategy=record, harness_spec=resolved.spec,
            api_profile=resolved.api, catalog=catalog, helper_profiles=helper_store)
        ranges = emitter.allocate_selector_ranges(resolved.spec['exploration_plan']['branches'])
        source, materialization, instrumentation = emitter.materialize_strategy(
            inputs, ranges, ROOT / 'templates/libfuzzer_harness_v1.cpp.in')
        source = emitter.finalize_source(source, 'preflight', '0' * 64, len(instrumentation))
        emitter.resolve_source_spans(source, materialization, instrumentation)
        emitter.validate_materialization_maps(record, resolved.spec, materialization, instrumentation)
    except emitter.BuildError as exc:
        raise PlanValidationError(f'Materialization preflight: {exc}') from exc
    return {'status': 'passed', 'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
            'step_count': len(materialization), 'instrumentation_sites': len(instrumentation),
            'compile_status': 'not_run',
            'template_contract': __import__('template_contract').verify_template(
                ROOT / 'templates/libfuzzer_harness_v1.cpp.in',
                catalog['template_interface']['template_ref']['content_hash'])}

def source_extension_refs(args: argparse.Namespace) -> dict[str, Any]:
    return {
        'resource_policy_ref': file_source_ref(RESOURCE_POLICY_PATH, 'strategy_resource_policy', '1.0'),
        'ordinary_recipes_ref': file_source_ref(ORDINARY_RECIPES_PATH, 'ordinary_input_recipes', '1.0'),
        'strategy_review_ref': None if getattr(args, 'strategy_review', None) is None else
            file_source_ref(args.strategy_review, safe_component(args.strategy_review.stem), '1.0'),
        'generation_trace_ref': None,
    }

def file_source_ref(path: Path, name: str, version: str) -> dict[str, Any]:
    return {**artifact_ref(path, name, version), 'relative_path': str(path)}

def build_prompt_views(resolved: ResolvedInputs, catalog: dict[str, Any]) -> dict[str, Any]:
    api_view = copy.deepcopy(resolved.resolved_api_primitive)
    api_view.pop('_resolved_primitive', None)
    api_view['python_signature'] = resolved.api['python_contract']['signature']
    api_view['documented_constraints'] = copy.deepcopy(
        resolved.api['documented_constraints']
    )
    api_view['ordinary_valid_witnesses'] = validated_ordinary_witnesses(
        resolved.api
    )
    api_view['ordinary_input_recipe'] = ordinary_recipe(resolved.api)
    api_view['argument_relation_rules'] = argument_relation_rules(resolved.api, catalog)
    api_view['resource_policy'] = load_json(RESOURCE_POLICY_PATH)
    interface = catalog['template_interface']
    return {'harness_spec_view': build_harness_spec_view(resolved.spec), 'resolved_api_primitive_view': api_view, 'template_interface_view': {'available_slots': interface['available_slots'], 'slot_order': {slot: index for (index, slot) in enumerate(interface['available_slots'])}, 'built_in_values': interface['built_in_values']}, 'primitive_candidate_views': [primitive_view(item) for item in sorted(resolved.candidate_primitives, key=lambda item: item['primitive_id'])]}

def compact_errors(errors: list[str], max_chars: int=DEFAULT_MAX_REPAIR_CHARS) -> list[str]:
    deduplicated: list[str] = []
    seen: set[str] = set()
    for error in errors:
        normalized = ' '.join(str(error).split())
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduplicated.append(normalized)
    result: list[str] = []
    size = 0
    for error in deduplicated:
        addition = len(error) + (1 if result else 0)
        if size + addition > max_chars:
            break
        result.append(error)
        size += addition
    return result

def build_prompt(
    contract: dict[str, Any],
    rules: str,
    views: dict[str, Any],
    repair_errors: list[str],
    max_chars: int,
    previous_candidate: dict[str, Any] | None = None,
) -> str:
    sections = ['You are synthesizing a Strategy implementation plan. Return one JSON object only.', 'SYNTHESIS CONTRACT:\n' + json.dumps(contract, ensure_ascii=False, separators=(',', ':')), 'SYNTHESIS RULES:\n' + rules.strip(), 'INPUT VIEWS:\n' + json.dumps(views, ensure_ascii=False, separators=(',', ':'))]
    if repair_errors:
        if previous_candidate is not None:
            sections.append(
                'PREVIOUS CANDIDATE TO REPAIR:\n'
                + json.dumps(previous_candidate, ensure_ascii=False, separators=(',', ':'))
            )
        sections.append('REPAIR THE PREVIOUS RESPONSE USING THESE VALIDATION ERRORS:\n' + json.dumps(compact_errors(repair_errors), ensure_ascii=False))
    prompt = '\n\n'.join(sections)
    if len(prompt) > max_chars:
        section_sizes = {name: len(json.dumps(value, ensure_ascii=False, separators=(',', ':'))) for (name, value) in views.items()}
        raise ItemInputError(f'Prompt size {len(prompt)} exceeds --max-prompt-chars={max_chars}; view sizes={section_sizes}')
    return prompt

def call_llm(prompt: str, api_key: str, model: str, api_url: str) -> str:
    try:
        response = requests.post(api_url, headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}, json={'model': model, 'messages': [{'role': 'user', 'content': prompt}], 'temperature': 0}, timeout=180)
        response.raise_for_status()
        payload = response.json()
        return payload['choices'][0]['message']['content']
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
        raise LLMError(f'LLM request failed: {exc}') from exc

def parse_llm_response(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith('```'):
        raise LLMError('Markdown fences are forbidden')
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError(f'LLM response is not valid JSON: {exc}') from exc
    return require_object(value, 'LLM response')

def validate_response_shape(response: dict[str, Any]) -> str:
    allowed = {'synthesis_status', 'implementation_plan', 'blocking_gaps'}
    reject_unknown_keys(response, allowed, 'LLM response')
    status = response.get('synthesis_status')
    if status == 'materialized':
        if set(response) != {'synthesis_status', 'implementation_plan'}:
            raise PlanValidationError('materialized response must contain only implementation_plan')
        require_object(response['implementation_plan'], 'implementation_plan')
    elif status == 'blocked':
        if set(response) != {'synthesis_status', 'blocking_gaps'}:
            raise PlanValidationError('blocked response must contain only blocking_gaps')
        gaps = require_list(response['blocking_gaps'], 'blocking_gaps')
        if not gaps:
            raise PlanValidationError('blocked response requires at least one Blocking Gap')
    else:
        raise PlanValidationError('synthesis_status must be materialized or blocked')
    return status

def build_spec_context(spec: dict[str, Any]) -> tuple[list[str], dict[tuple[str, str, str], dict[str, Any]], set[tuple[str, str, str]], dict[tuple[str, str, str, str], dict[str, Any]]]:
    branch_ids = [branch['branch_id'] for branch in spec['exploration_plan']['branches']]
    entries = all_element_entries(spec)
    element_map = {(entry['source_branch_id'], entry['spec_element_type'], entry['spec_element_id']): entry for entry in entries}
    required_elements = {key for (key, entry) in element_map.items() if entry['required']}
    parameters = {(item['source_branch_id'], item['spec_element_type'], item['spec_element_id'], item['parameter_name']): item for item in exposed_parameters(entries)}
    return (branch_ids, element_map, required_elements, parameters)

def gap_semantic_payload(entry: dict[str, Any], spec: dict[str, Any]) -> Any:
    value = compact_semantic_value(entry['value'])
    id_fields = {'constraint_id', 'condition_id', 'observation_id', 'check_id'}
    if isinstance(value, dict):
        value = {key: item for (key, item) in value.items() if key not in id_fields}
    return value

def has_semantic_candidate(entry: dict[str, Any], resolved: ResolvedInputs) -> bool:
    if (
        entry['spec_element_type'] == 'behavior_observation'
        and entry['value']['observe_at'] == 'on_target_api_termination'
    ):
        return True
    matching = [
        primitive
        for primitive in resolved.candidate_primitives
        if any(
            directly_implements(entry, primitive, slot, resolved.spec)
            for slot in primitive['allowed_template_slots']
        )
    ]
    required_predicates = {
        item['predicate_id'] for item in semantic_requirements(entry)
    }
    covered_predicates = set().union(
        *(set(item['semantic_support']['predicate_ids']) for item in matching)
    ) if matching else set()
    return bool(matching) and not (required_predicates - covered_predicates)

def validate_blocked_response(response: dict[str, Any], resolved: ResolvedInputs) -> list[dict[str, Any]]:
    (branch_ids, element_map, required_elements, _) = build_spec_context(resolved.spec)
    branch_set = set(branch_ids)
    normalized: list[dict[str, Any]] = []
    markers: set[str] = set()
    for (index, raw_gap) in enumerate(response['blocking_gaps']):
        gap = require_object(raw_gap, f'blocking_gaps[{index}]')
        expected = {'affected_branch_ids', 'spec_element_type', 'spec_element_id', 'reason_code', 'details'}
        if set(gap) != expected:
            raise PlanValidationError(f'blocking_gaps[{index}] has incorrect fields')
        affected = require_list(gap['affected_branch_ids'], f'blocking_gaps[{index}].affected_branch_ids')
        if not affected or any((branch_id not in branch_set for branch_id in affected)):
            raise PlanValidationError(f'blocking_gaps[{index}] has unknown or empty affected_branch_ids')
        ensure_unique(affected, f'blocking_gaps[{index}].affected_branch_ids')
        element_type = gap['spec_element_type']
        element_id = gap['spec_element_id']
        if (element_type is None) != (element_id is None):
            raise PlanValidationError('Blocking Gap must set both Spec Element fields or neither')
        if element_type is not None:
            if element_type not in TRACEABLE_SPEC_TYPES or not isinstance(element_id, str) or (not element_id.strip()):
                raise PlanValidationError('Blocking Gap has an invalid Spec Element reference')
            semantic_markers: set[str] = set()
            for branch_id in affected:
                key = (branch_id, element_type, element_id)
                if key not in element_map:
                    raise PlanValidationError('Blocking Gap Spec Element is not applicable to every affected Branch')
                if key not in required_elements:
                    raise PlanValidationError('Blocking Gap may reference only required Spec Elements')
                semantic_markers.add(canonical_hash(gap_semantic_payload(element_map[key], resolved.spec)))
            if len(semantic_markers) != 1:
                raise PlanValidationError('Multi-Branch Blocking Gap references non-equivalent semantics')
        if gap['reason_code'] not in BLOCKING_REASON_CODES:
            raise PlanValidationError('Blocking Gap has an unknown reason_code')
        reason_code = gap['reason_code']
        allowed_element_types = {
            'required_capability_unavailable': {
                'global_constraint', 'branch_constraint', 'target_condition'
            },
            'required_observation_unavailable': {
                'target_condition', 'behavior_observation'
            },
            'required_oracle_unavailable': {'behavior_check'},
            'api_input_unconstructable': {
                None, 'global_constraint', 'branch_constraint', 'target_condition'
            },
            'type_flow_unresolvable': TRACEABLE_SPEC_TYPES | {None},
            'semantic_conflict_unresolvable': TRACEABLE_SPEC_TYPES | {None},
        }
        if element_type not in allowed_element_types[reason_code]:
            raise PlanValidationError(f'Blocking reason {reason_code} is incompatible with {element_type!r}')
        if reason_code in {'required_capability_unavailable', 'required_observation_unavailable', 'required_oracle_unavailable'}:
            for branch_id in affected:
                entry = element_map[branch_id, element_type, element_id]
                if has_semantic_candidate(entry, resolved):
                    raise PlanValidationError(f'Blocking reason {reason_code} contradicts an available semantic candidate; use a more precise dataflow or conflict reason')
        require_string(gap['details'], f'blocking_gaps[{index}].details')
        normalized_gap = copy.deepcopy(gap)
        normalized_gap['affected_branch_ids'] = sorted(affected)
        marker = canonical_hash(normalized_gap)
        if marker in markers:
            raise PlanValidationError('blocking_gaps contains a duplicate gap')
        markers.add(marker)
        normalized.append(normalized_gap)
    return sorted(normalized, key=lambda item: (item['reason_code'], item['spec_element_type'] or '', item['spec_element_id'] or '', item['affected_branch_ids']))

def normalize_materialized_plan(response: dict[str, Any], resolved: ResolvedInputs, catalog: dict[str, Any]) -> dict[str, Any]:
    plan = require_object(response['implementation_plan'], 'implementation_plan')
    if set(plan) != {'branch_strategies'}:
        raise PlanValidationError('implementation_plan must contain only branch_strategies')
    raw_branches = require_list(plan['branch_strategies'], 'branch_strategies')
    source_order = [branch['branch_id'] for branch in resolved.spec['exploration_plan']['branches']]
    raw_by_source: dict[str, dict[str, Any]] = {}
    for (index, raw_branch) in enumerate(raw_branches):
        branch = require_object(raw_branch, f'branch_strategies[{index}]')
        source_id = require_string(branch.get('source_branch_id'), f'branch_strategies[{index}].source_branch_id')
        if source_id in raw_by_source:
            raise PlanValidationError(f'Duplicate source_branch_id: {source_id}')
        raw_by_source[source_id] = branch
    if set(raw_by_source) != set(source_order):
        raise PlanValidationError('Strategy Branch set must exactly equal the HarnessSpec Branch set')
    primitive_map = {item['primitive_id']: item for item in resolved.candidate_primitives}
    api_primitive = resolved.resolved_api_primitive['_resolved_primitive']
    primitive_map[api_primitive['primitive_id']] = api_primitive
    builtin_ids = {item['value_id'] for item in catalog['template_interface']['built_in_values']}
    normalized_branches: list[dict[str, Any]] = []
    for source_id in source_order:
        branch = copy.deepcopy(raw_by_source[source_id])
        expected_branch_fields = {'source_branch_id', 'steps', 'spec_bindings'}
        if set(branch) != expected_branch_fields:
            raise PlanValidationError(f'Branch {source_id} has incorrect fields')
        steps = require_list(branch['steps'], f'Branch {source_id}.steps')
        if not steps:
            raise PlanValidationError(f'Branch {source_id} must contain at least one Step')
        step_id_map: dict[str, str] = {}
        value_id_map: dict[str, str] = {}
        for (index, step) in enumerate(steps, start=1):
            step = require_object(step, f'Branch {source_id}.steps[{index - 1}]')
            primitive_id = require_string(step.get('primitive_id'), 'primitive_id')
            primitive = primitive_map.get(primitive_id)
            if primitive is None:
                raise PlanValidationError(f'Step at index {index - 1} selects unavailable Primitive {primitive_id!r}')
            old_step_id = require_string(step.get('step_id'), 'step_id')
            if old_step_id in step_id_map:
                raise PlanValidationError(f'Branch {source_id} has duplicate step_id {old_step_id}')
            step_id_map[old_step_id] = f'step_{index:03d}'
            raw_outputs = require_list(step.get('output_bindings'), f'Step {old_step_id}.output_bindings')
            output_order = {item['port_id']: position for (position, item) in enumerate(primitive['output_contract'])}
            output_by_port: dict[str, dict[str, Any]] = {}
            for output in raw_outputs:
                output = require_object(output, 'output_binding')
                port_id = require_string(output.get('port_id'), 'output_binding.port_id')
                if port_id not in output_order:
                    raise PlanValidationError(f'Step {old_step_id} binds unknown output port {port_id!r}')
                if port_id in output_by_port:
                    raise PlanValidationError(f'Step {old_step_id} repeats output port {port_id!r}')
                output_by_port[port_id] = output
                old_value_id = require_string(output.get('value_id'), 'output_binding.value_id')
                if old_value_id in value_id_map:
                    raise PlanValidationError(f'Branch {source_id} has duplicate value_id {old_value_id}')
                if old_value_id in builtin_ids:
                    raise PlanValidationError(f'Branch {source_id} output value collides with built-in {old_value_id!r}')
                value_id_map[old_value_id] = f'value_{len(value_id_map) + 1:03d}'
            step['output_bindings'] = sorted(output_by_port.values(), key=lambda item: output_order[item['port_id']])
        for step in steps:
            old_step_id = step['step_id']
            step['step_id'] = step_id_map[old_step_id]
            for binding in step['input_bindings']:
                reference = binding['value_ref']
                if reference in value_id_map:
                    binding['value_ref'] = value_id_map[reference]
            for binding in step['parameter_bindings']:
                if binding['binding_kind'] == 'value_ref' and binding['binding_value'] in value_id_map:
                    binding['binding_value'] = value_id_map[binding['binding_value']]
            for binding in step['output_bindings']:
                binding['value_id'] = value_id_map[binding['value_id']]
        for binding in branch['spec_bindings']:
            implementation_ids = require_list(binding.get('implementation_step_ids'), 'implementation_step_ids')
            if any((step_id not in step_id_map for step_id in implementation_ids)):
                raise PlanValidationError(f'Branch {source_id} has a Spec Binding that references an unknown Step')
            ensure_unique(implementation_ids, 'implementation_step_ids')
            binding['implementation_step_ids'] = sorted((step_id_map[step_id] for step_id in implementation_ids), key=lambda value: int(value.split('_')[1]))
            binding['binding_kind'] = 'in_harness_steps'
            binding['runner_events'] = []
        source_branch = next(
            item for item in resolved.spec['exploration_plan']['branches']
            if item['branch_id'] == source_id
        )
        for observation in source_branch['behavior_observations']:
            if observation['observe_at'] != 'on_target_api_termination':
                continue
            branch['spec_bindings'].append({
                'spec_element_type': 'behavior_observation',
                'spec_element_id': observation['observation_id'],
                'binding_kind': 'runner_event',
                'implementation_step_ids': [],
                'runner_events': [
                    'target_api_returned',
                    'caught_exception',
                    'process_exit',
                    'process_signal',
                    'timeout',
                    'sanitizer_report',
                ],
            })
        normalized_branches.append(branch)
    return {'branch_strategies': normalized_branches}

def primitive_contract_maps(primitive: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    inputs = {item['port_id']: item for item in primitive['input_contract']}
    outputs = {item['port_id']: item for item in primitive['output_contract']}
    parameters = {item['parameter_id']: item for item in primitive['parameter_contract']}
    return (inputs, outputs, parameters)

def validate_binding_set(values: Any, declared: dict[str, dict[str, Any]], id_field: str, required_field: str, label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for value in require_list(values, label):
        item = require_object(value, label)
        item_id = require_string(item.get(id_field), f'{label}.{id_field}')
        if item_id in result:
            raise PlanValidationError(f'{label} repeats {item_id}')
        if item_id not in declared:
            raise PlanValidationError(f'{label} references undeclared {item_id}')
        result[item_id] = item
    missing = sorted((item_id for (item_id, contract) in declared.items() if contract[required_field] and item_id not in result))
    if missing:
        raise PlanValidationError(f'{label} misses required bindings: {missing}')
    return result

def value_kind_compatible(actual: str, expected: str) -> bool:
    if actual == expected:
        return True
    if expected == 'scalar' and actual in {'integer', 'floating'}:
        return True
    return False

def literal_matches_value_kind(value: Any, expected: str) -> bool:
    if expected == 'optional_value':
        return value is None
    if expected == 'boolean':
        return isinstance(value, bool)
    if expected in {'integer', 'rank'}:
        return isinstance(value, int) and (not isinstance(value, bool))
    if expected == 'floating':
        return isinstance(value, (int, float)) and (not isinstance(value, bool))
    if expected == 'scalar':
        return isinstance(value, (int, float)) and (not isinstance(value, bool))
    if expected in {'string', 'dtype', 'device', 'layout'}:
        return isinstance(value, str) and bool(value)
    if expected == 'shape':
        return isinstance(value, list) and all((isinstance(item, int) and (not isinstance(item, bool)) for item in value))
    if expected == 'tuple_value':
        return isinstance(value, (list, dict))
    return False

def transitive_ancestors(step_id: str, predecessors: dict[str, set[str]]) -> set[str]:
    result: set[str] = set()
    pending = list(predecessors.get(step_id, set()))
    while pending:
        current = pending.pop()
        if current in result:
            continue
        result.add(current)
        pending.extend(predecessors.get(current, set()))
    return result

def observation_slot(phase: str) -> str:
    if phase == 'before_target_api_call':
        return 'pre_call_observation'
    if phase == 'after_target_api_call':
        return 'post_call_observation'
    raise PlanValidationError(
        f'Observation phase {phase!r} belongs to the Runner, not a Harness slot'
    )

def directly_implements(entry: dict[str, Any], primitive: dict[str, Any], slot: str, spec: dict[str, Any]) -> bool:
    support = primitive['semantic_support']
    element_type = entry['spec_element_type']
    value = entry['value']
    predicate_ids = {
        item['predicate_id'] for item in semantic_requirements(entry)
    }
    if predicate_ids and not predicate_ids.intersection(support['predicate_ids']):
        return False
    if element_type == 'target_condition':
        expected_slots = {observation_slot(phase) for phase in value['observe_at']}
        return (
            slot in expected_slots
            and value['role'] in support['condition_roles']
            and bool(set(value['observe_at']).intersection(support['observation_phases']))
        )
    if element_type == 'behavior_observation':
        if value['observe_at'] == 'on_target_api_termination':
            return False
        return (
            slot == observation_slot(value['observe_at'])
            and value['observe_at'] in support['observation_phases']
        )
    if element_type == 'behavior_check':
        return value['requirement_level'] in support['behavior_check_levels']
    # Observing a condition is not enforcing a validity constraint.
    return (element_type in {'global_constraint', 'branch_constraint'}
            and primitive['primitive_kind'] == 'relation_enforce'
            and slot == 'pre_call_guard')

def validate_binding_semantics(entry: dict[str, Any], implementation_ids: list[str], step_map: dict[str, dict[str, Any]], primitive_map: dict[str, dict[str, Any]], predecessors: dict[str, set[str]], spec: dict[str, Any]) -> None:
    if (
        entry['spec_element_type'] == 'target_condition'
        and entry['value']['role'] == 'exploration_variable'
    ):
        enforcing = [
            step_id for step_id in implementation_ids
            if primitive_map[step_map[step_id]['primitive_id']]['primitive_kind']
            == 'relation_enforce'
            or step_map[step_id]['template_slot'] == 'pre_call_guard'
        ]
        if enforcing:
            raise PlanValidationError(
                'exploration_variable must be varied and observed, not enforced '
                f'as a per-execution guard: {enforcing}'
            )
    direct_ids = [step_id for step_id in implementation_ids if directly_implements(entry, primitive_map[step_map[step_id]['primitive_id']], step_map[step_id]['template_slot'], spec)]
    if not direct_ids:
        raise PlanValidationError('Spec Binding has no directly compatible semantic Step')
    element_type = entry['spec_element_type']
    value = entry['value']
    required_predicates = {
        item['predicate_id'] for item in semantic_requirements(entry)
    }
    covered_predicates = set().union(*(
        set(primitive_map[step_map[step_id]['primitive_id']]['semantic_support']['predicate_ids'])
        for step_id in direct_ids
    ))
    if required_predicates - covered_predicates:
        raise PlanValidationError(
            'Spec Binding misses predicate support: '
            f'{sorted(required_predicates - covered_predicates)}'
        )
    if element_type == 'target_condition':
        for phase in value['observe_at']:
            slot = observation_slot(phase)
            if not any(step_map[step_id]['template_slot'] == slot for step_id in direct_ids):
                raise PlanValidationError(
                    f'Target Condition misses required observation slot {slot}'
                )
    direct_ancestors = {step_id: transitive_ancestors(step_id, predecessors) for step_id in direct_ids}
    unrelated = [step_id for step_id in implementation_ids if step_id not in direct_ids and (not any((step_id in ancestors for ancestors in direct_ancestors.values())))]
    if unrelated:
        raise PlanValidationError(f'Spec Binding contains unrelated auxiliary Steps: {unrelated}')

def step_literal_parameters(step: dict[str, Any]) -> dict[str, Any]:
    return {
        binding['parameter_id']: binding['binding_value']
        for binding in step['parameter_bindings']
        if binding['binding_kind'] == 'literal'
    }

def python_subject_target_value(
    subject_ref: str,
    target_step: dict[str, Any],
    api: dict[str, Any],
) -> str:
    target_values = {
        item['port_id']: item['value_ref']
        for item in target_step['input_bindings']
    }
    returns = {item['port_id']: item['value_id'] for item in target_step['output_bindings']}
    if subject_ref in returns:
        return returns[subject_ref]
    matches = [
        item['binding_parameter_ref']
        for item in api['target_binding']['argument_mapping']
        if subject_ref in item.get('source_parameter_refs', [])
        or item.get('python_parameter_ref') == subject_ref
    ]
    conversions = [item for item in api['target_binding']['argument_mapping']
                   if (subject_ref in item.get('source_parameter_refs', []) or item.get('python_parameter_ref') == subject_ref)
                   and item.get('mapping_kind') not in {'direct', 'renamed'}]
    if conversions:
        raise PlanValidationError('Predicate over a transformed Python parameter needs an explicit semantic adapter')
    if len(matches) != 1 or matches[0] not in target_values:
        raise PlanValidationError(
            f'Predicate subject {subject_ref!r} does not resolve to one bound target input'
        )
    return target_values[matches[0]]

def validate_predicate_argument_fidelity(
    entry: dict[str, Any],
    implementation_ids: list[str],
    step_map: dict[str, dict[str, Any]],
    target_step: dict[str, Any],
    api: dict[str, Any],
) -> None:
    from strategy_domains import output_check_parameters, dimension_equality_form
    kind = entry['spec_element_type']
    if kind == 'behavior_check':
        check = entry['value']
        evaluators = [step_map[s] for s in implementation_ids if step_map[s]['primitive_id'] in {'evaluate_output_property', 'evaluate_execution_survival'}]
        if len(evaluators) != 1 or check['preconditions']:
            raise PlanValidationError('Behavior Check requires one exact evaluator and supported preconditions')
        step = evaluators[0]
        expected = check['expected_predicate']
        if expected['predicate_id'] == 'execution_survives':
            if step['primitive_id'] != 'evaluate_execution_survival' or check['subject_refs'] != ['context.execution']:
                raise PlanValidationError('Execution-survival check subject or primitive mismatch')
            return
        parameters = output_check_parameters(expected)
        if parameters is None or step['primitive_id'] != 'evaluate_output_property':
            raise PlanValidationError('Unsupported exact output check')
        subject = expected['arguments'].get('subject_ref')
        if check['subject_refs'] != [subject] or subject not in {b['port_id'] for b in target_step['output_bindings']}:
            raise PlanValidationError('Output check must refer to one actual target return')
        bound = {b['port_id']: b['value_ref'] for b in step['input_bindings']}
        if bound.get('result') != python_subject_target_value(subject, target_step, api):
            raise PlanValidationError('Output evaluator observes the wrong target return')
        actual = step_literal_parameters(step)
        if any(actual.get(k) != v for k, v in parameters.items()):
            raise PlanValidationError('Output check arguments do not preserve expected predicate')
        return
    if kind in {'global_constraint', 'branch_constraint'}:
        predicate = entry['value']['predicate']
        if not dimension_equality_form(predicate):
            raise PlanValidationError('Unsupported constraint enforcement form')
        a = predicate['arguments']
        guards = [step_map[s] for s in implementation_ids if step_map[s]['primitive_id'] == 'enforce_dimension_relation']
        if len(guards) != 1:
            raise PlanValidationError('Dimension constraint needs one enforcement guard')
        step = guards[0]
        inputs = {b['port_id']: b['value_ref'] for b in step['input_bindings']}
        p = step_literal_parameters(step)
        if (inputs.get('left') != python_subject_target_value(a['left_subject_ref'], target_step, api)
                or inputs.get('right') != python_subject_target_value(a['right_subject_ref'], target_step, api)
                or p.get('left_axis') != a['left_axis'] or p.get('right_axis') != a['right_axis'] or p.get('relation_kind') != 'equal'):
            raise PlanValidationError('Dimension constraint guard subjects/axes/relation mismatch')
        return
    if kind != 'target_condition':
        return
    predicate = entry['value']['predicate']
    arguments = predicate['arguments']
    predicate_id = predicate['predicate_id']
    implementation_steps = [step_map[item] for item in implementation_ids]
    if predicate_id in {'property_relation', 'range_constraint'}:
        subject_ref = arguments.get('subject_ref')
        expected_value = python_subject_target_value(subject_ref, target_step, api)
        evaluators = [
            step for step in implementation_steps
            if step['primitive_id'] == 'evaluate_tensor_property'
        ]
        phases = entry['value']['observe_at']
        if len(evaluators) != len(phases):
            raise PlanValidationError(
                f'{predicate_id} requires one evaluate_tensor_property Step per observation phase'
            )
        if len(phases) > 1:
            for step in evaluators:
                phase = next((p for p in phases if observation_slot(p) == step['template_slot']), None)
                if phase is None:
                    raise PlanValidationError('Evaluator phase is not declared')
                single = copy.deepcopy(entry)
                single['value']['observe_at'] = [phase]
                validate_predicate_argument_fidelity(single, [step['step_id']], step_map, target_step, api)
            return
        evaluator = evaluators[0]
        bound_subjects = {
            item['port_id']: item['value_ref'] for item in evaluator['input_bindings']
        }
        if bound_subjects.get('subject') != expected_value:
            raise PlanValidationError(
                f'{predicate_id} evaluator observes the wrong target input'
            )
        params = step_literal_parameters(evaluator)
        zero_numel = (
            arguments.get('property_ref') == 'numel'
            and (
                (
                    predicate_id == 'property_relation'
                    and arguments.get('operator') == 'equals'
                    and arguments.get('value') == 0
                )
                or (
                    predicate_id == 'range_constraint'
                    and arguments.get('lower_bound') == 0
                    and arguments.get('upper_bound') == 0
                    and arguments.get('lower_inclusive') is True
                    and arguments.get('upper_inclusive') is True
                )
            )
        )
        scalar_equality = (
            predicate_id == 'property_relation' and arguments.get('operator') == 'equals'
            and ((arguments.get('property_ref') == 'rank' and params.get('property_kind') == 'rank_equals'
                  and params.get('expected_integer') == arguments.get('value'))
                 or (arguments.get('property_ref') == 'dtype' and arguments.get('value') == 'int64'
                     and params.get('property_kind') == 'dtype_is_int64')))
        if not (zero_numel and params.get('property_kind') == 'numel_equals_zero') and not scalar_equality:
            raise PlanValidationError(
                f'Unsupported or mismatched {predicate_id} argument form'
            )
        return
    if predicate_id == 'cross_subject_relation':
        expected_left = python_subject_target_value(
            arguments.get('left_subject_ref'), target_step, api
        )
        expected_right = python_subject_target_value(
            arguments.get('right_subject_ref'), target_step, api
        )
        evaluators = [
            step for step in implementation_steps
            if step['primitive_id'] == 'evaluate_tensor_relation'
        ]
        phases = entry['value']['observe_at']
        if len(evaluators) != len(phases):
            raise PlanValidationError(
                'cross_subject_relation requires one evaluate_tensor_relation Step per phase'
            )
        if len(phases) > 1:
            for step in evaluators:
                phase = next((p for p in phases if observation_slot(p) == step['template_slot']), None)
                if phase is None:
                    raise PlanValidationError('Evaluator phase is not declared')
                single = copy.deepcopy(entry)
                single['value']['observe_at'] = [phase]
                validate_predicate_argument_fidelity(single, [step['step_id']], step_map, target_step, api)
            return
        evaluator = evaluators[0]
        inputs = {
            item['port_id']: item['value_ref'] for item in evaluator['input_bindings']
        }
        params = step_literal_parameters(evaluator)
        if (
            inputs.get('left') != expected_left
            or inputs.get('right') != expected_right
            or arguments.get('left_property_ref') != arguments.get('right_property_ref')
            or params.get('property_kind') != arguments.get('left_property_ref')
            or params.get('relation_kind') != arguments.get('relation')
        ):
            raise PlanValidationError(
                'cross_subject_relation Step does not preserve its subjects, properties, and relation'
            )
        return
    raise PlanValidationError(
        f'No argument-fidelity validator exists for predicate {predicate_id!r}'
    )

def derive_failure_handlers(steps: list[dict[str, Any]], primitive_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    handlers: list[dict[str, Any]] = []
    for step in steps:
        primitive = primitive_map[step['primitive_id']]
        failures = primitive['outcome_contract']['failure_outcomes']
        for outcome in failures:
            handlers.append({'failure_handler_id': f"fh_{step['step_id']}_{outcome['outcome_id']}", 'trigger': {'step_id': step['step_id'], 'outcome_id': outcome['outcome_id']}, 'terminal_action': outcome['terminal_action']})
    return handlers


def literal_parameter_value(step: dict[str, Any], parameter_id: str) -> Any:
    for binding in step['parameter_bindings']:
        if (
            binding['parameter_id'] == parameter_id
            and binding['binding_kind'] == 'literal'
        ):
            return binding['binding_value']
    return None


def directly_fuzz_dependent_output_ports(step: dict[str, Any]) -> set[str]:
    primitive_id = step['primitive_id']
    if primitive_id in {'construct_tensor_from_fuzz', 'construct_tensor_with_rank_range'}:
        return {'tensor', 'next_cursor'}
    if primitive_id == 'construct_tensor_from_reference':
        return {'tensor', 'next_cursor'} if literal_parameter_value(step, 'fill_policy') in {'fuzz_numeric', 'fuzz_sign'} else set()
    if primitive_id == 'select_optional_tensor_from_fuzz':
        return {'optional_value', 'next_cursor'}
    if primitive_id in {
        'construct_floating_from_fuzz',
        'construct_integer_from_fuzz',
        'construct_boolean_from_fuzz',
    }:
        if primitive_id != 'construct_boolean_from_fuzz' and literal_parameter_value(step, 'minimum') == literal_parameter_value(step, 'maximum'):
            return set()
        return {'value', 'next_cursor'}
    if primitive_id != 'construct_tensor_with_constraints':
        return set()
    shape = literal_parameter_value(step, 'shape_template')
    fill_policy = literal_parameter_value(step, 'fill_policy')
    consumes_fuzz_bytes = (
        isinstance(shape, list)
        and any(item == -1 for item in shape)
    ) or fill_policy in {'fuzz_numeric', 'fuzz_sign'}
    return {'tensor', 'next_cursor'} if consumes_fuzz_bytes else set()


def validate_default_branch_fuzz_dependence(
    spec: dict[str, Any],
    source_id: str,
    target_steps: list[str],
    step_map: dict[str, dict[str, Any]],
    primitive_map: dict[str, dict[str, Any]],
    fuzz_dependent_values: set[str],
) -> None:
    source_branch = next(
        branch
        for branch in spec['exploration_plan']['branches']
        if branch['branch_id'] == source_id
    )
    if source_branch['branch_kind'] != 'default':
        return
    for target_step_id in target_steps:
        target_step = step_map[target_step_id]
        target_primitive = primitive_map[target_step['primitive_id']]
        input_bindings = {
            binding['port_id']: binding['value_ref']
            for binding in target_step['input_bindings']
        }
        tensor_ports = [
            contract['port_id']
            for contract in target_primitive['input_contract']
            if contract['required'] and 'optional_value' not in contract['accepted_value_kinds']
            if any(
                kind in {'tensor', 'tensor_list'}
                for kind in contract['accepted_value_kinds']
            )
        ]
        if tensor_ports:
            missing = [
                port_id
                for port_id in tensor_ports
                if input_bindings.get(port_id) not in {None, 'none'}
                if input_bindings.get(port_id) not in fuzz_dependent_values
            ]
            if missing:
                raise PlanValidationError(
                    f'Default Branch {source_id} target tensor inputs do not '
                    f'depend on consumed LibFuzzer bytes: {missing}'
                )
        if not any(
            value_ref in fuzz_dependent_values
            for value_ref in input_bindings.values()
        ):
            raise PlanValidationError(
                f'Default Branch {source_id} target inputs do not depend on '
                'consumed LibFuzzer bytes'
            )


def validate_knowledge_branch_fuzz_dependence(
    spec: dict[str, Any],
    source_id: str,
    target_steps: list[str],
    step_map: dict[str, dict[str, Any]],
    fuzz_dependent_values: set[str],
) -> None:
    """Require a real post-selector fuzz degree of freedom in Knowledge paths."""
    source_branch = next(
        branch
        for branch in spec['exploration_plan']['branches']
        if branch['branch_id'] == source_id
    )
    if source_branch['branch_kind'] != 'knowledge_directed':
        return
    target_inputs = {
        binding['value_ref']
        for step_id in target_steps
        for binding in step_map[step_id]['input_bindings']
    }
    if not target_inputs.intersection(fuzz_dependent_values):
        raise PlanValidationError(
            f'Knowledge-directed Branch {source_id} fixes every target input; '
            'at least one meaningful target-input degree of freedom must depend '
            'on consumed LibFuzzer bytes'
        )

def validate_exploration_variable_fuzz_dependence(
    spec: dict[str, Any],
    source_id: str,
    target_step: dict[str, Any],
    api: dict[str, Any],
    fuzz_dependent_values: set[str],
    domains: dict[str, dict[str, Any]] | None = None,
) -> None:
    branch = next(
        item for item in spec['exploration_plan']['branches']
        if item['branch_id'] == source_id
    )
    for condition in branch['target_conditions']:
        if condition['role'] != 'exploration_variable':
            continue
        arguments = condition['predicate']['arguments']
        subject_refs = [
            arguments[name]
            for name in (
                'subject_ref', 'left_subject_ref', 'right_subject_ref'
            )
            if isinstance(arguments.get(name), str)
        ]
        relevant_values = {
            python_subject_target_value(subject, target_step, api)
            for subject in subject_refs
        }
        if not relevant_values.intersection(fuzz_dependent_values):
            raise PlanValidationError(
                f"Exploration variable {condition['condition_id']} loses fuzz "
                'dependence on all referenced target inputs'
            )
        if domains is not None:
            subjects = {subject: domains.get(python_subject_target_value(subject, target_step, api), {})
                        for subject in subject_refs}
            error = exploration_domain_error(condition['predicate'], subjects)
            if error:
                raise PlanValidationError(f"Exploration variable {condition['condition_id']}: {error}")



def validate_materialized_plan(plan: dict[str, Any], resolved: ResolvedInputs, catalog: dict[str, Any]) -> None:
    (branch_ids, element_map, required_elements, exposed_parameter_map) = build_spec_context(resolved.spec)
    primitive_map = {item['primitive_id']: item for item in resolved.candidate_primitives}
    api_primitive = resolved.resolved_api_primitive['_resolved_primitive']
    primitive_map[api_primitive['primitive_id']] = api_primitive
    interface = catalog['template_interface']
    slot_order = {slot: index for (index, slot) in enumerate(interface['available_slots'])}
    builtin_kinds = {item['value_id']: item['value_kind'] for item in interface['built_in_values']}
    api_primitive_id = resolved.resolved_api_primitive['target_api_primitive_id']
    for branch in plan['branch_strategies']:
        source_id = branch['source_branch_id']
        if source_id not in branch_ids:
            raise PlanValidationError(f'Unknown source Branch: {source_id}')
        steps = branch['steps']
        step_map = {step['step_id']: step for step in steps}
        if len(step_map) != len(steps):
            raise PlanValidationError(f'Branch {source_id} has duplicate Step IDs')
        available_values = dict(builtin_kinds)
        fuzz_dependent_values = {'data'}
        producer_by_value: dict[str, str] = {}
        consumers_by_value: dict[str, set[str]] = {}
        predecessors: dict[str, set[str]] = {step['step_id']: set() for step in steps}
        target_steps: list[str] = []
        previous_slot_index = -1
        for step in steps:
            expected_step_fields = {'step_id', 'primitive_id', 'template_slot', 'input_bindings', 'parameter_bindings', 'output_bindings'}
            if set(step) != expected_step_fields:
                raise PlanValidationError(f"Step {step.get('step_id')} has incorrect fields")
            primitive = primitive_map.get(step['primitive_id'])
            if primitive is None:
                raise PlanValidationError(f"Step {step['step_id']} selects an unavailable Primitive")
            slot = step['template_slot']
            if slot not in slot_order or slot not in primitive['allowed_template_slots']:
                raise PlanValidationError(f"Step {step['step_id']} has an invalid template slot")
            if primitive['outcome_contract']['failure_outcomes'] and slot not in PRE_CALL_SLOTS:
                raise PlanValidationError(f"Step {step['step_id']} places a Primitive with externally handled failure outcomes after target_call")
            current_slot_index = slot_order[slot]
            if current_slot_index < previous_slot_index:
                raise PlanValidationError(f'Branch {source_id} violates template slot order')
            previous_slot_index = current_slot_index
            if primitive['primitive_kind'] == 'target_api_invoke':
                target_steps.append(step['step_id'])
                if primitive['primitive_id'] != api_primitive_id or slot != 'target_call':
                    raise PlanValidationError('Target API Step uses the wrong Primitive or slot')
                provided = {b['port_id'] for b in step['input_bindings']}
                omitted = False
                for port in primitive['input_contract']:
                    if port['port_id'] not in provided:
                        omitted = True
                    elif omitted:
                        raise PlanValidationError('Target API cannot bind a later argument after omitting a default')
            (input_contract, output_contract, parameter_contract) = primitive_contract_maps(primitive)
            input_bindings = validate_binding_set(step['input_bindings'], input_contract, 'port_id', 'required', f"Step {step['step_id']} input_bindings")
            output_bindings = validate_binding_set(step['output_bindings'], output_contract, 'port_id', 'binding_required', f"Step {step['step_id']} output_bindings")
            parameter_bindings = validate_binding_set(step['parameter_bindings'], parameter_contract, 'parameter_id', 'required', f"Step {step['step_id']} parameter_bindings")
            input_has_fuzz_dependency = False
            parameter_has_fuzz_dependency = False
            for (port_id, binding) in input_bindings.items():
                if set(binding) != {'port_id', 'value_ref'}:
                    raise PlanValidationError('Input Binding has incorrect fields')
                value_ref = require_string(binding['value_ref'], 'input_binding.value_ref')
                if value_ref not in available_values:
                    raise PlanValidationError(f"Step {step['step_id']} references an unavailable or later value {value_ref}")
                if not any((value_kind_compatible(available_values[value_ref], expected) for expected in input_contract[port_id]['accepted_value_kinds'])):
                    raise PlanValidationError(f"Step {step['step_id']} has an incompatible input kind for {port_id}")
                input_has_fuzz_dependency |= value_ref in fuzz_dependent_values
                consumers_by_value.setdefault(value_ref, set()).add(step['step_id'])
                producer = producer_by_value.get(value_ref)
                if producer is not None:
                    predecessors[step['step_id']].add(producer)
            for (parameter_id, binding) in parameter_bindings.items():
                if set(binding) != {'parameter_id', 'binding_kind', 'binding_value'}:
                    raise PlanValidationError('Parameter Binding has incorrect fields')
                contract = parameter_contract[parameter_id]
                binding_kind = binding['binding_kind']
                if binding_kind not in contract['allowed_binding_kinds']:
                    raise PlanValidationError(f"Step {step['step_id']} uses a forbidden parameter binding kind")
                binding_value = binding['binding_value']
                if binding_kind == 'value_ref':
                    if binding_value not in available_values or not value_kind_compatible(available_values[binding_value], contract['value_kind']):
                        raise PlanValidationError(f"Step {step['step_id']} parameter value_ref is unavailable or type-incompatible")
                    parameter_has_fuzz_dependency |= binding_value in fuzz_dependent_values
                    consumers_by_value.setdefault(binding_value, set()).add(step['step_id'])
                    producer = producer_by_value.get(binding_value)
                    if producer is not None:
                        predecessors[step['step_id']].add(producer)
                elif binding_kind == 'spec_parameter':
                    reference = require_object(binding_value, 'spec_parameter_ref')
                    key = (source_id, reference.get('spec_element_type'), reference.get('spec_element_id'), reference.get('parameter_name'))
                    exposed = exposed_parameter_map.get(key)
                    if exposed is None:
                        raise PlanValidationError(f"Step {step['step_id']} references a non-exposable Spec parameter")
                    if not value_kind_compatible(exposed['value_kind'], contract['value_kind']):
                        raise PlanValidationError(f"Step {step['step_id']} uses a type-incompatible Spec parameter")
                else:
                    if not literal_matches_value_kind(binding_value, contract['value_kind']):
                        raise PlanValidationError(f"Step {step['step_id']} literal is type-incompatible")
                    if 'allowed_values' in contract and binding_value not in contract['allowed_values']:
                        raise PlanValidationError(f"Step {step['step_id']} literal is outside allowed_values")
            direct_fuzz_ports = directly_fuzz_dependent_output_ports(step)
            support_fuzz_policy = primitive['semantic_support']['fuzz_dependency']
            propagate_fuzz_dependency = (
                support_fuzz_policy == 'propagates'
                and (input_has_fuzz_dependency or parameter_has_fuzz_dependency)
            )
            for (port_id, binding) in output_bindings.items():
                if set(binding) != {'port_id', 'value_id'}:
                    raise PlanValidationError('Output Binding has incorrect fields')
                value_id = require_identifier(binding['value_id'], 'output_binding.value_id')
                if value_id in available_values:
                    raise PlanValidationError(f'Branch {source_id} repeats value ID {value_id}')
                available_values[value_id] = output_contract[port_id]['produced_value_kind']
                producer_by_value[value_id] = step['step_id']
                consumers_by_value.setdefault(value_id, set())
                if port_id in direct_fuzz_ports or propagate_fuzz_dependency:
                    fuzz_dependent_values.add(value_id)
        if len(target_steps) != 1:
            raise PlanValidationError(
                f"Branch {source_id} requires exactly one target API invocation Step"
            )
        domains = infer_domains(steps)
        for name, domain in domains.items():
            meaningful = meaningful_fuzz_domain(domain)
            if meaningful is True:
                fuzz_dependent_values.add(name)
            elif meaningful is False:
                fuzz_dependent_values.discard(name)
        source_branch = next(b for b in resolved.spec['exploration_plan']['branches'] if b['branch_id'] == source_id)
        recipe = ordinary_recipe(resolved.api) if source_branch.get('input_validity_intent') == 'expected_valid' else None
        if recipe is not None:
            errors = ordinary_recipe_errors(source_branch, domains, recipe, step_map[target_steps[0]])
            if errors:
                raise PlanValidationError('Ordinary-input recipe: ' + '; '.join(errors))
        errors = companion_relation_errors(source_branch, domains, step_map[target_steps[0]], argument_relation_rules(resolved.api, catalog))
        if errors:
            raise PlanValidationError('Auxiliary argument relation: ' + '; '.join(errors))
        validate_default_branch_fuzz_dependence(
            resolved.spec,
            source_id,
            target_steps,
            step_map,
            primitive_map,
            fuzz_dependent_values,
        )
        validate_knowledge_branch_fuzz_dependence(
            resolved.spec,
            source_id,
            target_steps,
            step_map,
            fuzz_dependent_values,
        )
        validate_exploration_variable_fuzz_dependence(
            resolved.spec,
            source_id,
            step_map[target_steps[0]],
            resolved.api,
            fuzz_dependent_values,
            domains,
        )
        binding_keys: set[tuple[str, str, str]] = set()
        steps_used_by_bindings: set[str] = set()
        for binding in branch['spec_bindings']:
            expected = {
                'spec_element_type',
                'spec_element_id',
                'binding_kind',
                'implementation_step_ids',
                'runner_events',
            }
            if set(binding) != expected:
                raise PlanValidationError(f'Branch {source_id} has a malformed Spec Binding')
            key = (source_id, binding['spec_element_type'], binding['spec_element_id'])
            if key not in element_map:
                raise PlanValidationError(f'Branch {source_id} binds an unknown Spec Element: {key[1:]}')
            if key in binding_keys:
                raise PlanValidationError(f'Branch {source_id} binds one Spec Element more than once')
            binding_keys.add(key)
            entry = element_map[key]
            implementation_ids = binding['implementation_step_ids']
            runner_events = binding['runner_events']
            if binding['binding_kind'] == 'runner_event':
                if implementation_ids or not runner_events:
                    raise PlanValidationError(
                        'runner_event binding requires runner_events and forbids implementation steps'
                    )
                if any(event not in RUNNER_EVENTS for event in runner_events):
                    raise PlanValidationError('runner_event binding contains an unknown Runner event')
                if (
                    entry['spec_element_type'] != 'behavior_observation'
                    or entry['value']['observe_at'] != 'on_target_api_termination'
                ):
                    raise PlanValidationError(
                        'Runner binding is allowed only for termination observations'
                    )
                required_termination_events = {
                    'target_api_returned', 'caught_exception', 'process_exit',
                    'process_signal', 'timeout', 'sanitizer_report'
                }
                if not required_termination_events.issubset(runner_events):
                    raise PlanValidationError(
                        'Termination observation does not cover the complete Runner event set'
                    )
                continue
            if binding['binding_kind'] != 'in_harness_steps' or runner_events:
                raise PlanValidationError('Spec Binding has an invalid binding_kind payload')
            if not implementation_ids or len(implementation_ids) != len(set(implementation_ids)) or any((step_id not in step_map for step_id in implementation_ids)):
                raise PlanValidationError(f'Branch {source_id} has invalid implementation_step_ids')
            ordered_ids = sorted(implementation_ids, key=lambda step_id: steps.index(step_map[step_id]))
            if implementation_ids != ordered_ids:
                raise PlanValidationError('implementation_step_ids are not in execution order')
            if target_steps[0] in implementation_ids:
                raise PlanValidationError('Target API invocation cannot be used as a Spec Binding implementation Step')
            validate_binding_semantics(entry, implementation_ids, step_map, primitive_map, predecessors, resolved.spec)
            validate_predicate_argument_fidelity(
                entry,
                implementation_ids,
                step_map,
                step_map[target_steps[0]],
                resolved.api,
            )
            steps_used_by_bindings.update(implementation_ids)
        branch_required = {key for key in required_elements if key[0] == source_id}
        missing_bindings = branch_required - binding_keys
        if missing_bindings:
            raise PlanValidationError(f'Branch {source_id} misses required Spec Bindings: {sorted(missing_bindings)}')
        for step in steps:
            produced_values = [item['value_id'] for item in step['output_bindings']]
            used = step['step_id'] in target_steps or step['step_id'] in steps_used_by_bindings or any((consumers_by_value.get(value_id) for value_id in produced_values))
            if not used:
                raise PlanValidationError(f"Step {step['step_id']} is neither consumed nor semantically referenced")

def materialize_failure_handlers(plan: dict[str, Any], resolved: ResolvedInputs) -> None:
    primitive_map = {item['primitive_id']: item for item in resolved.candidate_primitives}
    api_primitive = resolved.resolved_api_primitive['_resolved_primitive']
    primitive_map[api_primitive['primitive_id']] = api_primitive
    for branch in plan['branch_strategies']:
        branch['failure_handlers'] = derive_failure_handlers(branch['steps'], primitive_map)

def strategy_id_for(spec: dict[str, Any]) -> str:
    spec_id = safe_component(spec['identity']['spec_id'])
    source_revision = spec['revision_information']['revision_number']
    return f'st_{spec_id}_hsr{source_revision:03d}'

def assemble_record(
    plan: dict[str, Any],
    resolved: ResolvedInputs,
    catalog: dict[str, Any],
    args: argparse.Namespace,
    run_id: str,
    parent_strategy: dict[str, Any] | None,
) -> dict[str, Any]:
    spec = resolved.spec
    identity = spec['identity']
    parent_ref = (
        None if parent_strategy is None else strategy_reference(parent_strategy)
    )
    if parent_strategy is None:
        revision_information = {
            'revision_number': 1,
            'parent_revision_ref': None,
            'revision_trigger': 'initial_creation',
            'change_scopes': ['initial_definition'],
            'change_summary': 'Initial Strategy synthesis for this HarnessSpec revision',
        }
    else:
        scopes = ['source_context']
        old_branches = parent_strategy['implementation_plan']['branch_strategies']
        new_branches = plan['branch_strategies']
        projections = {
            'primitive_selection': lambda b: [s['primitive_id'] for s in b['steps']],
            'dataflow': lambda b: [(s['input_bindings'], s['output_bindings']) for s in b['steps']],
            'parameter_binding': lambda b: [s['parameter_bindings'] for s in b['steps']],
            'template_placement': lambda b: [s['template_slot'] for s in b['steps']],
            'failure_handling': lambda b: b['failure_handlers'],
            'spec_binding': lambda b: b['spec_bindings'],
        }
        for scope, projection in projections.items():
            if [projection(b) for b in old_branches] != [projection(b) for b in new_branches]:
                scopes.append(scope)
        revision_information = {
            'revision_number': args.strategy_revision,
            'parent_revision_ref': parent_ref,
            'revision_trigger': getattr(args, 'revision_trigger', 'validation_repair'),
            'change_scopes': scopes,
            'change_summary': 'Revalidate or repair executable domains, bindings and materialization without changing HarnessSpec semantics',
        }
    return {
        'schema_version': STRATEGY_SCHEMA_VERSION,
        'identity': {
            'strategy_id': strategy_id_for(spec),
            'framework': identity['framework'],
            'target_api': identity['target_api'],
            'spec_mode': identity['spec_mode'],
        },
        'revision_information': revision_information,
        'source_context': {
            **source_extension_refs(args),
            'harness_spec_ref': harness_spec_reference(spec),
            'harness_spec_review_ref': copy.deepcopy(
                resolved.harness_spec_review_ref
            ),
            'strategy_catalog_ref': {
                'catalog_id': catalog['catalog_id'],
                'catalog_version': catalog['catalog_version'],
                'content_hash': canonical_hash(catalog),
            },
            'derived_from_strategy_ref': None,
        },
        'implementation_plan': plan,
        'provenance': {
            'generation_method': 'hybrid',
            'generator_name': BUILDER_VERSION,
            'model_name': args.model,
            'generation_run_id': run_id,
            'script_ref': artifact_ref(Path(__file__).resolve(), 'build_strategy_plan_json', BUILDER_VERSION),
            'contract_ref': artifact_ref(args.contract, 'strategy_synthesis_contract', CONTRACT_VERSION),
            'rules_ref': artifact_ref(args.rules, 'harness_spec_to_strategy_rules', RULES_VERSION),
            'generated_at': utc_now(),
        },
        'review': {
            'validation_status': 'passed',
            'validation_issues': [],
            'human_review_status': 'not_reviewed',
            'reviewer_id': None,
            'reviewed_at': None,
            'review_notes': None,
        },
    }

def harness_spec_reference(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        'spec_id': spec['identity']['spec_id'],
        'revision_number': spec['revision_information']['revision_number'],
        'content_hash': canonical_hash(spec),
    }


def strategy_reference(strategy: dict[str, Any]) -> dict[str, Any]:
    return {
        'strategy_id': strategy['identity']['strategy_id'],
        'revision_number': strategy['revision_information']['revision_number'],
        'content_hash': canonical_hash(strategy),
    }


def canonical_default_strategy_branch(
    strategy: dict[str, Any], label: str
) -> dict[str, Any]:
    branches = strategy['implementation_plan']['branch_strategies']
    if len(branches) != 1:
        raise ItemInputError(f'{label} must contain exactly one Branch strategy')
    return branches[0]

def validate_approved_strategy_review(
    review_path: Path,
    strategy_path: Path,
    strategy: dict[str, Any],
    validator: Draft202012Validator,
) -> None:
    review = require_object(load_json(review_path), 'Strategy review')
    validate_against(
        review,
        validator,
        f'Strategy review {review_path}',
        ItemInputError,
    )
    if review['decision'] != 'approved':
        raise ItemInputError('Canonical default Strategy review is not approved')
    review_rules = review['rules_ref']
    if file_hash(Path(review_rules['relative_path'])) != review_rules['content_hash']:
        raise ItemInputError('Canonical Strategy review Rules hash mismatch')
    expected_subject = {
        'strategy_id': strategy['identity']['strategy_id'],
        'revision_number': strategy['revision_information']['revision_number'],
        'content_hash': canonical_hash(strategy),
        'relative_path': str(strategy_path),
    }
    subject = review['subject']
    if (
        subject['strategy_id'] != expected_subject['strategy_id']
        or subject['revision_number'] != expected_subject['revision_number']
        or subject['content_hash'] != expected_subject['content_hash']
        or Path(subject['relative_path']).resolve() != strategy_path.resolve()
    ):
        raise ItemInputError(
            'Canonical default Strategy review subject does not match exactly'
        )


def resolve_canonical_default_strategy(
    args: argparse.Namespace,
    resolved: ResolvedInputs,
    catalog: dict[str, Any],
    record_validator: Draft202012Validator,
    strategy_review_validator: Draft202012Validator,
) -> dict[str, Any] | None:
    mode = resolved.spec['identity']['spec_mode']
    if mode == 'controlled_baseline':
        if args.canonical_default_strategy is not None:
            raise ItemInputError(
                'Controlled baseline cannot consume --canonical-default-strategy'
            )
        if args.canonical_default_strategy_review is not None:
            raise ItemInputError(
                'Controlled baseline cannot consume --canonical-default-strategy-review'
            )
        return None
    if (
        args.canonical_default_strategy is None
        or args.canonical_default_strategy_review is None
    ):
        raise ItemInputError(
            'Initial bug-aware Strategy synthesis requires '
            '--canonical-default-strategy and its approved review'
        )
    canonical = require_object(
        load_json(args.canonical_default_strategy),
        'canonical default Strategy',
    )
    validate_against(
        canonical,
        record_validator,
        f'canonical default Strategy {args.canonical_default_strategy}',
        ItemInputError,
    )
    identity = canonical['identity']
    current = resolved.spec['identity']
    if (
        identity.get('spec_mode') != 'controlled_baseline'
        or identity.get('framework') != current['framework']
        or identity.get('target_api') != current['target_api']
    ):
        raise ItemInputError('Canonical default Strategy identity is incompatible')
    expected_catalog = {
        'catalog_id': catalog['catalog_id'],
        'catalog_version': catalog['catalog_version'],
        'content_hash': canonical_hash(catalog),
    }
    if canonical['source_context']['strategy_catalog_ref'] != expected_catalog:
        raise ItemInputError('Canonical default Strategy uses a different Catalog')
    if canonical['source_context'].get('resource_policy_ref') != source_extension_refs(args)['resource_policy_ref']:
        raise ItemInputError('Canonical default Strategy uses a different resource policy')
    if canonical['source_context'].get('ordinary_recipes_ref') != source_extension_refs(args)['ordinary_recipes_ref']:
        raise ItemInputError('Canonical default Strategy uses different ordinary recipes')
    source_ref = canonical['source_context']['harness_spec_ref']
    sources = [load_json(path) for path in (ROOT / 'harness_specs').rglob(
        f'{source_ref["spec_id"]}_r{source_ref["revision_number"]}.json') if 'legacy' not in path.parts]
    sources = [source for source in sources if canonical_hash(source) == source_ref['content_hash']]
    if len(sources) != 1:
        raise ItemInputError('Canonical baseline exact HarnessSpec is unavailable')
    baseline_context = sources[0]['target_context']
    current_context = resolved.spec['target_context']
    if (baseline_context['api_profile_ref'] != current_context['api_profile_ref']
            or sorted(map(profile_key, baseline_context['available_helper_profile_refs'])) !=
               sorted(map(profile_key, current_context['available_helper_profile_refs']))):
        raise ItemInputError('Baseline/Static API or Helper Profile sets differ')
    if canonical['review']['validation_status'] != 'passed':
        raise ItemInputError('Canonical default Strategy is not validated')
    validate_approved_strategy_review(
        args.canonical_default_strategy_review,
        args.canonical_default_strategy,
        canonical,
        strategy_review_validator,
    )
    canonical_default_strategy_branch(canonical, 'canonical default Strategy')
    return canonical


def apply_canonical_default_strategy(
    plan: dict[str, Any], canonical: dict[str, Any] | None
) -> None:
    if canonical is None:
        return
    shared = copy.deepcopy(
        canonical_default_strategy_branch(canonical, 'canonical default Strategy')
    )
    shared.pop('failure_handlers', None)
    branches = plan['branch_strategies']
    indexes = [
        index
        for index, branch in enumerate(branches)
        if branch.get('source_branch_id') == shared['source_branch_id']
    ]
    if len(indexes) != 1:
        raise PlanValidationError(
            'Bug-aware plan must contain exactly one canonical default strategy'
        )
    branches[indexes[0]] = shared



def resolve_generation_parent(
    args: argparse.Namespace,
    spec: dict[str, Any],
    catalog: dict[str, Any],
    record_validator: Draft202012Validator,
) -> dict[str, Any] | None:
    if args.strategy_revision == 1:
        return None
    parent = require_object(
        load_json(args.parent_strategy),
        'parent Strategy Plan',
    )
    validate_against(
        parent,
        record_validator,
        f'parent Strategy Plan {args.parent_strategy}',
        ItemInputError,
    )
    expected_identity = {
        'strategy_id': strategy_id_for(spec),
        'framework': spec['identity']['framework'],
        'target_api': spec['identity']['target_api'],
        'spec_mode': spec['identity']['spec_mode'],
    }
    if parent['identity'] != expected_identity:
        raise ItemInputError('Parent Strategy identity does not match this HarnessSpec')
    if parent['revision_information']['revision_number'] != args.strategy_revision - 1:
        raise ItemInputError('Parent Strategy is not the immediately preceding revision')
    if parent['source_context']['harness_spec_ref'] != harness_spec_reference(spec):
        raise ItemInputError('Parent Strategy does not reference the exact HarnessSpec')
    expected_catalog_ref = {
        'catalog_id': catalog['catalog_id'],
        'catalog_version': catalog['catalog_version'],
        'content_hash': canonical_hash(catalog),
    }
    if parent['source_context']['strategy_catalog_ref'] != expected_catalog_ref:
        if getattr(args, 'revision_trigger', None) != 'catalog_update':
            raise ItemInputError('Catalog change requires --revision-trigger catalog_update')
        previous = parent['source_context']['strategy_catalog_ref']
        snapshot = ROOT / 'strategy_primitives/catalog_snapshots' / f'strategy_primitive_catalog__v{previous["catalog_version"]:03d}.json'
        if not snapshot.is_file() or canonical_hash(load_json(snapshot)) != previous['content_hash']:
            raise ItemInputError('Parent Catalog snapshot is unavailable or mismatched')
    if parent['review']['validation_status'] != 'passed':
        raise ItemInputError('Parent Strategy validation_status is not passed')
    return parent

def repair_review(args: argparse.Namespace, parent: dict[str, Any] | None,
                  validator: Draft202012Validator) -> list[str]:
    path = getattr(args, 'strategy_review', None)
    if path is None:
        if getattr(args, 'revision_trigger', None) == 'manual_review':
            raise ItemInputError('manual_review repair requires --strategy-review')
        return []
    if parent is None:
        raise ItemInputError('Repair review requires a parent Strategy')
    review = load_json(path)
    validate_against(review, validator, 'Strategy repair review', ItemInputError)
    if file_hash(Path(review['rules_ref']['relative_path'])) != review['rules_ref']['content_hash']:
        raise ItemInputError('Strategy repair review Rules hash mismatch')
    subject = review['subject']
    if (review['decision'] != 'needs_revision' or subject['strategy_id'] != parent['identity']['strategy_id']
            or subject['revision_number'] != parent['revision_information']['revision_number']
            or subject['content_hash'] != canonical_hash(parent)
            or Path(subject['relative_path']).resolve() != args.parent_strategy.resolve()):
        raise ItemInputError('Repair review must be an exact-hash needs_revision review of the parent Strategy')
    return [json.dumps(finding, ensure_ascii=False) for finding in review['findings'] if finding['severity'] == 'blocking']


def feedback_semantic_projection(spec: dict[str, Any]) -> dict[str, Any]:
    branches = copy.deepcopy(spec['exploration_plan']['branches'])
    for branch in branches:
        branch.pop('budget_share', None)
    return {
        'target': {
            'framework': spec['identity']['framework'],
            'target_api': spec['identity']['target_api'],
        },
        'target_context': copy.deepcopy(spec['target_context']),
        'knowledge_plan': copy.deepcopy(spec['knowledge_plan']),
        'validity_constraints': copy.deepcopy(spec['validity_constraints']),
        'exploration_plan': {
            'default_branch_id': spec['exploration_plan']['default_branch_id'],
            'branches': branches,
        },
    }


def assemble_rebound_record(
    resolved: ResolvedInputs,
    source_strategy: dict[str, Any],
    catalog: dict[str, Any],
    args: argparse.Namespace,
    run_id: str,
) -> dict[str, Any]:
    spec = resolved.spec
    identity = spec['identity']
    return {
        'schema_version': STRATEGY_SCHEMA_VERSION,
        'identity': {
            'strategy_id': strategy_id_for(spec),
            'framework': identity['framework'],
            'target_api': identity['target_api'],
            'spec_mode': identity['spec_mode'],
        },
        'revision_information': {
            'revision_number': 1,
            'parent_revision_ref': None,
            'revision_trigger': 'initial_creation',
            'change_scopes': ['initial_definition'],
            'change_summary': (
                'Deterministic Strategy rebind for a budget-only HarnessSpec revision'
            ),
        },
        'source_context': {
            **source_extension_refs(args),
            'harness_spec_ref': harness_spec_reference(spec),
            'harness_spec_review_ref': copy.deepcopy(
                resolved.harness_spec_review_ref
            ),
            'strategy_catalog_ref': {
                'catalog_id': catalog['catalog_id'],
                'catalog_version': catalog['catalog_version'],
                'content_hash': canonical_hash(catalog),
            },
            'derived_from_strategy_ref': strategy_reference(source_strategy),
        },
        'implementation_plan': copy.deepcopy(source_strategy['implementation_plan']),
        'provenance': {
            'generation_method': 'script',
            'generator_name': BUILDER_VERSION,
            'model_name': None,
            'generation_run_id': run_id,
            'script_ref': artifact_ref(
                Path(__file__).resolve(),
                'build_strategy_plan_json',
                BUILDER_VERSION,
            ),
            'contract_ref': artifact_ref(
                args.contract,
                'strategy_synthesis_contract',
                CONTRACT_VERSION,
            ),
            'rules_ref': artifact_ref(
                args.rules,
                'harness_spec_to_strategy_rules',
                RULES_VERSION,
            ),
            'generated_at': utc_now(),
        },
        'review': {
            'validation_status': 'passed',
            'validation_issues': [],
            'human_review_status': 'not_reviewed',
            'reviewer_id': None,
            'reviewed_at': None,
            'review_notes': None,
        },
    }


def rebind_one(
    candidate_spec_path: Path,
    source_spec_path: Path,
    source_strategy_path: Path,
    args: argparse.Namespace,
    catalog: dict[str, Any],
    spec_validator: Draft202012Validator,
    record_validator: Draft202012Validator,
    api_store: dict[tuple[str, int, str], dict[str, Any]],
    helper_store: dict[tuple[str, int, str], dict[str, Any]],
    review_store: dict[tuple[str, int, str], tuple[dict[str, Any], Path]],
) -> Outcome:
    run_id = new_run_id()
    resolved = resolve_item_inputs(
        candidate_spec_path,
        catalog,
        spec_validator,
        api_store,
        helper_store,
        review_store,
    )
    candidate = resolved.spec
    source_spec = require_object(load_json(source_spec_path), 'source HarnessSpec')
    validate_against(
        source_spec,
        spec_validator,
        f'source HarnessSpec {source_spec_path}',
        ItemInputError,
    )
    source_strategy = require_object(
        load_json(source_strategy_path), 'source Strategy Plan'
    )
    validate_against(
        source_strategy,
        record_validator,
        f'source Strategy Plan {source_strategy_path}',
        ItemInputError,
    )
    if source_strategy['review']['validation_status'] != 'passed':
        raise ItemInputError('Source Strategy validation_status is not passed')
    if source_strategy['source_context']['harness_spec_ref'] != harness_spec_reference(source_spec):
        raise ItemInputError('Source Strategy does not reference the exact source HarnessSpec')
    if source_strategy['source_context']['strategy_catalog_ref'] != {
        'catalog_id': catalog['catalog_id'],
        'catalog_version': catalog['catalog_version'],
        'content_hash': canonical_hash(catalog),
    }:
        raise ItemInputError('Source Strategy and candidate use different Catalogs')

    revision = candidate['revision_information']
    if (
        candidate['identity']['spec_mode'] != 'bug_aware_adaptive'
        or revision['revision_trigger'] != 'execution_feedback'
        or revision['change_scopes'] != ['budget_allocation']
        or revision['feedback_request_ref'] is None
    ):
        raise ItemInputError('Candidate HarnessSpec is not a budget-only feedback revision')
    source_ref = (
        revision['derived_from_spec_ref']
        if revision['revision_number'] == 1
        else revision['parent_revision_ref']
    )
    if source_ref != harness_spec_reference(source_spec):
        raise ItemInputError('Candidate lineage does not reference the exact source HarnessSpec')
    if feedback_semantic_projection(candidate) != feedback_semantic_projection(source_spec):
        raise ItemInputError('Candidate changes non-budget HarnessSpec semantics')

    source_identity = source_strategy['identity']
    if (
        source_identity['framework'] != candidate['identity']['framework']
        or source_identity['target_api'] != candidate['identity']['target_api']
    ):
        raise ItemInputError('Source Strategy target does not match the candidate')
    plan = copy.deepcopy(source_strategy['implementation_plan'])
    validate_materialized_plan(plan, resolved, catalog)
    record = assemble_rebound_record(
        resolved,
        source_strategy,
        catalog,
        args,
        run_id,
    )
    validate_against(record, record_validator, 'Strategy Plan record', PlanValidationError)
    output_path = strategy_destination(args.output_root, record)
    if args.dry_run:
        return Outcome(
            harness_spec=str(candidate_spec_path),
            target_api=candidate['identity']['target_api'],
            mode=candidate['identity']['spec_mode'],
            status='dry_run',
            attempts=0,
            message='Deterministic feedback rebind validated',
        )
    capability_preflight(resolved, catalog)
    preflight = materialization_preflight(record, resolved, catalog, helper_store)
    attach_generation_trace(record, args, run_id, load_json(args.contract), load_text(args.rules), catalog,
                            build_prompt_views(resolved, catalog), [], preflight)
    validate_against(record, record_validator, 'Rebound Strategy Plan with trace', PlanValidationError)
    atomic_write_json(output_path, record)
    return Outcome(
        harness_spec=str(candidate_spec_path),
        target_api=candidate['identity']['target_api'],
        mode=candidate['identity']['spec_mode'],
        status='success',
        attempts=0,
        output_path=str(output_path),
    )



def strategy_destination(output_root: Path, record: dict[str, Any]) -> Path:
    identity = record['identity']
    revision = record['revision_information']['revision_number']
    return output_root / 'plans' / safe_component(identity['framework']) / safe_component(identity['target_api']) / identity['spec_mode'] / f"{identity['strategy_id']}_r{revision:03d}.json"

def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise ItemInputError(f'Refusing to overwrite immutable artifact: {path}')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f'.{uuid.uuid4().hex}.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    try:
        os.link(temporary, path)
    except FileExistsError as exc:
        raise ItemInputError(f'Concurrent artifact creation detected: {path}') from exc
    finally:
        temporary.unlink(missing_ok=True)

def write_machine_result(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    if args.result_json is not None:
        atomic_write_json(args.result_json, payload)


def write_diagnostic(output_root: Path, run_id: str, status: str, spec_path: Path, spec: dict[str, Any] | None, catalog: dict[str, Any], attempts: int, *, gaps: list[dict[str, Any]] | None=None, errors: list[str] | None=None) -> Path:
    diagnostic_id = f'diag_{run_id[4:]}'
    identity = None if spec is None else spec.get('identity')
    harness_spec_ref = None
    if spec is not None and identity is not None:
        harness_spec_ref = {'spec_id': identity['spec_id'], 'revision_number': spec['revision_information']['revision_number'], 'content_hash': canonical_hash(spec)}
    diagnostic = {'diagnostic_version': '1.0', 'diagnostic_id': diagnostic_id, 'generation_run_id': run_id, 'status': status, 'harness_spec_path': str(spec_path), 'harness_spec_ref': harness_spec_ref, 'strategy_catalog_ref': {'catalog_id': catalog['catalog_id'], 'catalog_version': catalog['catalog_version'], 'content_hash': canonical_hash(catalog)}, 'attempts': attempts, 'blocking_gaps': gaps or [], 'errors': compact_errors(errors or []), 'created_at': utc_now()}
    path = output_root / 'diagnostics' / f'{diagnostic_id}.json'
    atomic_write_json(path, diagnostic)
    return path

def prompt_statistics(views: dict[str, Any], prompt: str, maximum: int) -> dict[str, Any]:
    return {'prompt_chars': len(prompt), 'max_prompt_chars': maximum, 'view_chars': {name: len(json.dumps(value, ensure_ascii=False, separators=(',', ':'))) for (name, value) in views.items()}, 'candidate_primitive_count': len(views['primitive_candidate_views']), 'source_branch_count': len(views['harness_spec_view']['source_branches'])}

def read_spec_paths(args: argparse.Namespace) -> list[Path]:
    paths = list(args.harness_spec or [])
    if args.harness_spec_list is not None:
        content = load_text(args.harness_spec_list, global_input=True)
        base = args.harness_spec_list.parent
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            candidate = Path(line)
            paths.append(candidate if candidate.is_absolute() else base / candidate)
    deduplicated: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        marker = str(path.resolve())
        if marker in seen:
            continue
        seen.add(marker)
        deduplicated.append(path)
    return sorted(deduplicated, key=lambda path: str(path.resolve()))

def apply_config_defaults(args: argparse.Namespace) -> None:
    if not args.config.exists():
        return
    try:
        config = yaml.safe_load(load_text(args.config, global_input=True)) or {}
    except yaml.YAMLError as exc:
        raise GlobalInputError(f'Invalid YAML in {args.config}: {exc}') from exc
    if not isinstance(config, dict) or not isinstance(config.get('paths', {}), dict):
        raise GlobalInputError('config.yaml paths must be an object')
    configured_paths = config.get('paths', {})
    mapping = {'api_profiles': 'api_profiles', 'helper_profiles': 'helper_profiles', 'strategy_primitives': 'output_root'}
    for (config_name, argument_name) in mapping.items():
        configured = configured_paths.get(config_name)
        if not isinstance(configured, str) or not configured.strip():
            continue
        expected_default = DEFAULTS[argument_name]
        if getattr(args, argument_name) == expected_default:
            setattr(args, argument_name, args.config.parent / configured)

def validate_contract_and_rules(contract: dict[str, Any], rules: str) -> None:
    if contract.get('contract_version') != CONTRACT_VERSION:
        raise GlobalInputError(f"Contract version must be {CONTRACT_VERSION}; got {contract.get('contract_version')!r}")
    if contract.get('target_record_schema_version') != STRATEGY_SCHEMA_VERSION:
        raise GlobalInputError('Contract target record Schema version is incompatible')
    expected_header = f'# HarnessSpec-to-Strategy Synthesis Rules v{RULES_VERSION}'
    if not rules.startswith(expected_header):
        raise GlobalInputError(f'Rules document must begin with {expected_header!r}')

def write_generation_trace(args: argparse.Namespace, run_id: str, contract: dict, rules: str,
                           catalog: dict, views: dict, attempts: list, preflight: dict) -> Path:
    path = args.output_root / 'generation_traces' / f'{run_id}.json'
    stack_paths = [Path(__file__).resolve(), Path(__file__).with_name('strategy_domains.py'),
                   Path(__file__).with_name('build_harness_artifact.py'),
                   ROOT / 'templates/libfuzzer_harness_v1.cpp.in',
                   ROOT / 'runtime/harness_instrumentation.h', ROOT / 'runtime/harness_instrumentation.cpp',
                   args.record_schema, args.harness_spec_schema, args.harness_spec_schema_core]
    atomic_write_json(path, {'schema_version': '1.0', 'generation_run_id': run_id,
        'frozen_inputs': {'contract': contract, 'rules': rules, 'catalog': catalog,
                         'resource_policy': load_json(RESOURCE_POLICY_PATH),
                         'ordinary_recipes': load_json(ORDINARY_RECIPES_PATH), 'views': views},
        'stack_snapshot': [{'name': p.name, 'sha256': file_hash(p), 'source': load_text(p)} for p in stack_paths],
        'attempts': attempts, 'materialization_preflight': preflight})
    return path

def attach_generation_trace(record: dict, args: argparse.Namespace, run_id: str,
                            contract: dict, rules: str, catalog: dict, views: dict,
                            attempts: list, preflight: dict) -> None:
    path = write_generation_trace(args, run_id, contract, rules, catalog, views, attempts, preflight)
    record['source_context']['generation_trace_ref'] = file_source_ref(path, safe_component(run_id), '1.0')

def build_one(spec_path: Path, args: argparse.Namespace, catalog: dict[str, Any], contract: dict[str, Any], rules: str, spec_validator: Draft202012Validator, record_validator: Draft202012Validator, strategy_review_validator: Draft202012Validator, api_store: dict[tuple[str, int, str], dict[str, Any]], helper_store: dict[tuple[str, int, str], dict[str, Any]], review_store: dict[tuple[str, int, str], tuple[dict[str, Any], Path]], api_key: str | None) -> Outcome:
    run_id = new_run_id()
    spec: dict[str, Any] | None = None
    try:
        resolved = resolve_item_inputs(
            spec_path,
            catalog,
            spec_validator,
            api_store,
            helper_store,
            review_store,
        )
        spec = resolved.spec
        target_api = spec['identity']['target_api']
        mode = spec['identity']['spec_mode']
        parent_strategy = resolve_generation_parent(
            args,
            spec,
            catalog,
            record_validator,
        )
        findings = repair_review(args, parent_strategy, strategy_review_validator)
        capability_preflight(resolved, catalog)
        canonical_default = resolve_canonical_default_strategy(
            args,
            resolved,
            catalog,
            record_validator,
            strategy_review_validator,
        )
        views = build_prompt_views(resolved, catalog)
        if canonical_default is not None:
            canonical_view = copy.deepcopy(canonical_default_strategy_branch(canonical_default, 'canonical default Strategy'))
            canonical_view.pop('failure_handlers', None)
            views['canonical_default_strategy_view'] = canonical_view
        if parent_strategy is not None:
            views['parent_strategy_view'] = copy.deepcopy(parent_strategy['implementation_plan'])
        initial_prompt = build_prompt(contract, rules, views, findings, args.max_prompt_chars)
        destination_probe = {'identity': {'strategy_id': strategy_id_for(spec), **{k: spec['identity'][k] for k in ('framework', 'target_api', 'spec_mode')}},
                             'source_context': {'harness_spec_ref': harness_spec_reference(spec)},
                             'revision_information': {'revision_number': args.strategy_revision}}
        destination = strategy_destination(args.output_root, destination_probe)
        if destination.exists():
            raise ItemInputError(f'Refusing to overwrite immutable Strategy revision: {destination}')
        if args.dry_run:
            summary = {
                'harness_spec': str(spec_path),
                'target_api': target_api,
                'mode': mode,
                'strategy_id': strategy_id_for(spec),
                'strategy_revision': args.strategy_revision,
                'parent_strategy_ref': (
                    None
                    if parent_strategy is None
                    else strategy_reference(parent_strategy)
                ),
                'catalog_id': catalog['catalog_id'],
                'catalog_version': catalog['catalog_version'],
                **prompt_statistics(
                    views,
                    initial_prompt,
                    args.max_prompt_chars,
                ),
            }
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return Outcome(harness_spec=str(spec_path), target_api=target_api, mode=mode, status='dry_run')
        if args.adopt_parent:
            if parent_strategy is None:
                raise ItemInputError('--adopt-parent requires a parent Strategy')
            plan = copy.deepcopy(parent_strategy['implementation_plan'])
            apply_canonical_default_strategy(plan, canonical_default)
            materialize_failure_handlers(plan, resolved)
            validate_materialized_plan(plan, resolved, catalog)
            record = assemble_record(plan, resolved, catalog, args, run_id, parent_strategy)
            record['provenance']['generation_method'] = 'script'
            record['provenance']['model_name'] = None
            preflight = materialization_preflight(record, resolved, catalog, helper_store)
            attach_generation_trace(record, args, run_id, contract, rules, catalog, views, [], preflight)
            validate_against(record, record_validator, 'Adopted Strategy Plan', PlanValidationError)
            atomic_write_json(destination, record)
            return Outcome(harness_spec=str(spec_path), target_api=target_api, mode=mode,
                           status='success', attempts=0, output_path=str(destination), message='Deterministic revalidation; implementation preserved')
        if api_key is None:
            raise GlobalInputError('DEEPSEEK_API_KEY is required unless --dry-run is used')
        repair_errors: list[str] = list(findings)
        previous_candidate: dict[str, Any] | None = None
        attempts_trace: list[dict[str, Any]] = []
        for attempt in range(1, args.max_attempts + 1):
            try:
                prompt = build_prompt(
                    contract,
                    rules,
                    views,
                    repair_errors,
                    args.max_prompt_chars,
                    previous_candidate,
                )
                raw_response = call_llm(prompt, api_key, args.model, args.api_url)
                attempts_trace.append({'attempt': attempt, 'prompt': prompt, 'raw_response': raw_response, 'validation_error': None})
                response = parse_llm_response(raw_response)
                previous_candidate = copy.deepcopy(response)
                status = validate_response_shape(response)
                if status == 'blocked':
                    gaps = validate_blocked_response(response, resolved)
                    write_generation_trace(args, run_id, contract, rules, catalog, views, attempts_trace,
                                           {'status': 'blocked', 'gaps': gaps})
                    diagnostic_path = write_diagnostic(args.output_root, run_id, 'blocked', spec_path, spec, catalog, attempt, gaps=gaps)
                    return Outcome(harness_spec=str(spec_path), target_api=target_api, mode=mode, status='blocked', attempts=attempt, diagnostics_path=str(diagnostic_path), message='Strategy synthesis returned validated blocking gaps')
                plan = normalize_materialized_plan(response, resolved, catalog)
                apply_canonical_default_strategy(plan, canonical_default)
                materialize_failure_handlers(plan, resolved)
                validate_materialized_plan(plan, resolved, catalog)
                record = assemble_record(
                    plan,
                    resolved,
                    catalog,
                    args,
                    run_id,
                    parent_strategy,
                )
                validate_against(record, record_validator, 'Strategy Plan record', PlanValidationError)
                preflight = materialization_preflight(record, resolved, catalog, helper_store)
                attach_generation_trace(record, args, run_id, contract, rules, catalog, views, attempts_trace, preflight)
                validate_against(record, record_validator, 'Strategy Plan with trace', PlanValidationError)
                output_path = strategy_destination(args.output_root, record)
                atomic_write_json(output_path, record)
                return Outcome(harness_spec=str(spec_path), target_api=target_api, mode=mode, status='success', attempts=attempt, output_path=str(output_path))
            except (LLMError, PlanValidationError) as exc:
                repair_errors.append(f'{type(exc).__name__}: {exc}')
                if attempts_trace and attempts_trace[-1]['attempt'] == attempt:
                    attempts_trace[-1]['validation_error'] = str(exc)
        write_generation_trace(args, run_id, contract, rules, catalog, views, attempts_trace, {'status': 'failed', 'errors': repair_errors})
        diagnostic_path = write_diagnostic(args.output_root, run_id, 'generation_failed', spec_path, spec, catalog, args.max_attempts, errors=repair_errors)
        compacted = compact_errors(repair_errors)
        return Outcome(harness_spec=str(spec_path), target_api=target_api, mode=mode, status='generation_failed', attempts=args.max_attempts, diagnostics_path=str(diagnostic_path), message=compacted[-1] if compacted else 'Generation failed')
    except GlobalInputError:
        raise
    except (ItemInputError, PlanValidationError) as exc:
        outcome_status = 'blocked' if isinstance(exc, CapabilityGap) else 'input_error'
        diagnostic_path = write_diagnostic(args.output_root, run_id, outcome_status, spec_path, spec, catalog, 0, errors=[f'{type(exc).__name__}: {exc}'])
        identity = {} if spec is None else spec.get('identity', {})
        return Outcome(harness_spec=str(spec_path), target_api=identity.get('target_api'), mode=identity.get('spec_mode'), status=outcome_status, diagnostics_path=str(diagnostic_path), message=str(exc))

def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--harness-spec', type=Path, action='append', help='Exact HarnessSpec path; repeatable.')
    parser.add_argument('--harness-spec-list', type=Path, help='Text file with one HarnessSpec path per line.')
    parser.add_argument(
        '--harness-spec-review',
        type=Path,
        action='append',
        default=[],
        help=(
            'Exact approved external HarnessSpec review; repeat once per '
            'HarnessSpec subject.'
        ),
    )
    parser.add_argument(
        '--rebind-from-strategy',
        type=Path,
        help='Exact prior Strategy copied for a budget-only feedback revision.',
    )
    parser.add_argument(
        '--rebind-source-spec',
        type=Path,
        help='Exact HarnessSpec implemented by --rebind-from-strategy.',
    )
    parser.add_argument(
        '--canonical-default-strategy',
        type=Path,
        help=(
            'Exact validated controlled-baseline Strategy whose br_default '
            'implementation is reused by initial bug-aware synthesis.'
        ),
    )
    parser.add_argument(
        '--canonical-default-strategy-review',
        type=Path,
        help='Exact approved external review for --canonical-default-strategy.',
    )
    for (name, default) in DEFAULTS.items():
        parser.add_argument('--' + name.replace('_', '-'), type=Path, default=default)
    parser.add_argument(
        '--strategy-revision',
        type=int,
        default=1,
        help='Immutable Strategy revision to create; defaults to 1.',
    )
    parser.add_argument(
        '--parent-strategy',
        type=Path,
        help='Exact immediately preceding Strategy record for revision > 1.',
    )
    parser.add_argument('--result-json', type=Path, help='Immutable machine-readable outcome selected by the orchestrator.')
    parser.add_argument('--strategy-review', type=Path, help='Exact needs_revision external review of --parent-strategy.')
    parser.add_argument('--revision-trigger', choices=['validation_repair', 'catalog_update', 'manual_review', 'regeneration'], default='validation_repair')
    parser.add_argument('--adopt-parent', action='store_true', help='Revalidate/copy parent implementation into a new immutable revision without an LLM call.')
    parser.add_argument('--model', default=DEFAULT_MODEL)
    parser.add_argument('--api-url', default=DEFAULT_API_URL)
    parser.add_argument('--max-attempts', type=int, default=3)
    parser.add_argument('--max-prompt-chars', type=int, default=DEFAULT_MAX_PROMPT_CHARS)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--validate-catalog-only', action='store_true')
    args = parser.parse_args(argv)
    if args.strategy_revision < 1:
        parser.error('--strategy-revision must be positive')
    if args.strategy_revision == 1 and args.parent_strategy is not None:
        parser.error('--parent-strategy is forbidden for Strategy revision 1')
    if args.strategy_revision > 1 and args.parent_strategy is None:
        parser.error('--parent-strategy is required for Strategy revision > 1')
    if args.adopt_parent and args.parent_strategy is None:
        parser.error('--adopt-parent requires --parent-strategy')
    if args.max_attempts < 1:
        parser.error('--max-attempts must be positive')
    if args.max_prompt_chars < 1:
        parser.error('--max-prompt-chars must be positive')
    if args.rebind_from_strategy is not None and (
        args.strategy_revision != 1
        or args.parent_strategy is not None
        or args.canonical_default_strategy is not None
        or args.canonical_default_strategy_review is not None
    ):
        parser.error(
            'Initial Strategy revision options cannot be combined with '
            'deterministic feedback rebinding'
        )
    if (args.rebind_from_strategy is None) != (args.rebind_source_spec is None):
        parser.error(
            '--rebind-from-strategy and --rebind-source-spec must be supplied together'
        )
    if (args.canonical_default_strategy is None) != (
        args.canonical_default_strategy_review is None
    ):
        parser.error(
            '--canonical-default-strategy and '
            '--canonical-default-strategy-review must be supplied together'
        )
    return args

def main(argv: list[str] | None=None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        apply_config_defaults(args)
        harness_spec_schema = load_json(args.harness_spec_schema, global_input=True)
        harness_spec_schema_core = load_json(
            args.harness_spec_schema_core, global_input=True
        )
        harness_spec_review_schema = load_json(
            args.harness_spec_review_schema, global_input=True
        )
        strategy_review_schema = load_json(
            args.strategy_review_schema, global_input=True
        )
        api_profile_schema = load_json(args.api_profile_schema, global_input=True)
        helper_profile_schema = load_json(args.helper_profile_schema, global_input=True)
        catalog_schema = load_json(args.catalog_schema, global_input=True)
        record_schema = load_json(args.record_schema, global_input=True)
        spec_validator = schema_validator(
            harness_spec_schema,
            'HarnessSpec record',
            [harness_spec_schema_core],
        )
        spec_review_validator = schema_validator(
            harness_spec_review_schema, 'HarnessSpec review record'
        )
        strategy_review_validator = schema_validator(
            strategy_review_schema, 'Strategy review record'
        )
        api_validator = schema_validator(api_profile_schema, 'API Profile record')
        helper_validator = schema_validator(helper_profile_schema, 'Helper Profile record')
        catalog_validator = schema_validator(catalog_schema, 'Strategy Catalog record')
        record_validator = schema_validator(record_schema, 'Strategy Plan record')
        contract_value = load_json(args.contract, global_input=True)
        try:
            contract = require_object(contract_value, 'Synthesis Contract')
        except PlanValidationError as exc:
            raise GlobalInputError(str(exc)) from exc
        rules = load_text(args.rules, global_input=True)
        validate_contract_and_rules(contract, rules)
        try:
            catalog = validate_catalog(load_json(args.catalog, global_input=True), catalog_validator, harness_spec_schema)
        except PlanValidationError as exc:
            raise GlobalInputError(str(exc)) from exc
        helper_store = read_profile_store(args.helper_profiles, helper_validator, 'Helper Profile')
        for primitive in catalog['primitives']:
            helper_ref = primitive['implementation_binding']['helper_profile_ref']
            if helper_ref is None:
                continue
            try:
                helper_key = profile_key(helper_ref)
            except ItemInputError as exc:
                raise GlobalInputError(str(exc)) from exc
            helper = helper_store.get(helper_key)
            if helper is None or not helper_is_ready_and_approved(helper):
                raise GlobalInputError(f'Catalog references an unavailable or unapproved Helper Profile: {helper_key}')
        if args.validate_catalog_only:
            result = {'status': 'passed', 'catalog_id': catalog['catalog_id'], 'catalog_version': catalog['catalog_version'], 'catalog_content_hash': canonical_hash(catalog), 'primitive_count': len(catalog['primitives'])}
            write_machine_result(args, result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        review_store = read_harness_spec_review_store(
            args.harness_spec_review,
            spec_review_validator,
        )
        api_store = read_profile_store(args.api_profiles, api_validator, 'API Profile')
        spec_paths = read_spec_paths(args)
        if not spec_paths:
            raise GlobalInputError('Provide --harness-spec and/or --harness-spec-list')
        if args.strategy_revision > 1 and len(spec_paths) != 1:
            raise GlobalInputError(
                'Strategy revision repair requires exactly one HarnessSpec'
            )
        outcomes: list[Outcome] = []
        if args.rebind_from_strategy is not None:
            if len(spec_paths) != 1:
                raise GlobalInputError(
                    'Deterministic feedback rebinding requires exactly one HarnessSpec'
                )
            try:
                outcome = rebind_one(
                    spec_paths[0],
                    args.rebind_source_spec,
                    args.rebind_from_strategy,
                    args,
                    catalog,
                    spec_validator,
                    record_validator,
                    api_store,
                    helper_store,
                    review_store,
                )
            except (ItemInputError, PlanValidationError) as exc:
                run_id = new_run_id()
                diagnostic = write_diagnostic(
                    args.output_root,
                    run_id,
                    'input_error',
                    spec_paths[0],
                    None,
                    catalog,
                    0,
                    errors=[f'{type(exc).__name__}: {exc}'],
                )
                outcome = Outcome(
                    harness_spec=str(spec_paths[0]),
                    target_api=None,
                    mode=None,
                    status='input_error',
                    diagnostics_path=str(diagnostic),
                    message=str(exc),
                )
            outcomes.append(outcome)
            stream = sys.stdout if outcome.status in {'success', 'dry_run'} else sys.stderr
            print(json.dumps(asdict(outcome), ensure_ascii=False, indent=2), file=stream)
        else:
            api_key = None if (args.dry_run or args.adopt_parent) else os.environ.get('DEEPSEEK_API_KEY')
            if not args.dry_run and not args.adopt_parent and (not api_key):
                raise GlobalInputError('DEEPSEEK_API_KEY is required unless --dry-run is used')
            for spec_path in spec_paths:
                outcome = build_one(
                    spec_path,
                    args,
                    catalog,
                    contract,
                    rules,
                    spec_validator,
                    record_validator,
                    strategy_review_validator,
                    api_store,
                    helper_store,
                    review_store,
                    api_key,
                )
                outcomes.append(outcome)
                stream = sys.stdout if outcome.status in {'success', 'dry_run'} else sys.stderr
                print(json.dumps(asdict(outcome), ensure_ascii=False, indent=2), file=stream)
        result = {
            'status': 'success' if all(outcome.status in {'success', 'dry_run'} for outcome in outcomes) else 'failed',
            'outcomes': [asdict(outcome) for outcome in outcomes],
        }
        write_machine_result(args, result)
        if result['status'] == 'success':
            return 0
        return 1
    except GlobalInputError as exc:
        result = {'status': 'global_input_error', 'message': str(exc)}
        write_machine_result(args, result)
        print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
if __name__ == '__main__':
    raise SystemExit(main())
