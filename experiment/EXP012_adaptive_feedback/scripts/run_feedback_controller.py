#!/usr/bin/env python3
"""Evaluate one adaptive fuzzing round and record a deterministic decision.

The controller does not call an LLM, execute fuzzing, or confirm framework bugs.
It validates one already-finished round, diagnoses branches from the exact
Harness instrumentation map, applies the frozen feedback policy, and writes an
immutable Feedback Decision.

Budget-preserving decisions are completed in one invocation.  A budget change
uses a two-stage interface because the Decision Schema has no pending state:

1. without --materialization-result, write a deterministic materialization
   request and exit with code 3;
2. after the downstream deterministic pipeline returns accepted or rejected,
   rerun with --materialization-result and write the final Decision.

The second stage re-evaluates every input and verifies that the supplied result
belongs to the exact request.  No provisional Decision is persisted.
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
from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError as exc:  # pragma: no cover - environment error
    raise SystemExit(
        "Missing dependency; install environment/python-control-requirements.txt"
    ) from exc


CONTROLLER_ID = "run_feedback_controller"
CONTROLLER_VERSION = "0.5.3"
RECORD_FORMAT_VERSION = "1.2"
CANONICALIZATION_VERSION = "1.0"

EXP_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = EXP_ROOT.parents[1]
EXP011_ROOT = REPOSITORY_ROOT / "experiment" / "EXP011_bug_aware_harness_synthesis"

DEFAULT_POLICY = EXP_ROOT / "policies" / "adaptive_feedback_policy.json"
DEFAULT_ROUND_SCHEMA = EXP_ROOT / "schemas" / "fuzzing_round_record.schema.json"
DEFAULT_DECISION_SCHEMA = EXP_ROOT / "schemas" / "feedback_decision_record.schema.json"
DEFAULT_HARNESS_SPEC_SCHEMA = EXP011_ROOT / "schemas" / "harness_spec_record.schema.json"
DEFAULT_STRATEGY_SCHEMA = EXP011_ROOT / "schemas" / "strategy_plan_record.schema.json"
DEFAULT_HARNESS_ARTIFACT_SCHEMA = EXP011_ROOT / "schemas" / "harness_artifact_record.schema.json"
DEFAULT_OUTPUT_ROOT = EXP_ROOT / "decisions"
DEFAULT_REQUEST_ROOT = EXP_ROOT / "materialization_requests"

IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

BRANCH_STATUS_ORDER = (
    "branch_under_sampled",
    "branch_rejection_dominated",
    "branch_target_unreachable",
    "branch_activation_unevaluable",
    "branch_activation_absent",
    "branch_activation_rare",
    "branch_oracle_unevaluable",
    "branch_healthy",
)
CANDIDATE_OBSERVATION_CODES = {
    "crash": "crash_candidate_observed",
    "sanitizer": "sanitizer_candidate_observed",
    "target_exception": "target_exception_candidate_observed",
    "oracle_failure": "oracle_failure_candidate_observed",
}
KNOWN_TERMINATIONS = {
    "time_budget_reached",
    "candidate_detected",
    "completed_early",
    "infrastructure_failure",
    "cancelled",
    "unknown",
}


class ControllerError(RuntimeError):
    """Expected controller failure."""


class GlobalInputError(ControllerError):
    """A shared policy, schema, or controller setting is invalid."""


class RoundInputError(ControllerError):
    """The round bundle cannot be attributed or interpreted safely."""


class DecisionConflictError(ControllerError):
    """An immutable output conflicts with an existing record."""


class InstrumentationBindingError(RoundInputError):
    """Required instrumentation cannot be resolved unambiguously."""


class CounterConsistencyError(RoundInputError):
    """Runtime counters violate their ordering or cardinality contract."""


@dataclass(frozen=True)
class ResolvedRound:
    round_record: dict[str, Any]
    runtime_snapshot: dict[str, Any] | None
    harness_artifact: dict[str, Any]
    strategy: dict[str, Any]
    harness_spec: dict[str, Any]
    prior_decisions: tuple[dict[str, Any], ...]
    prior_decision_refs: tuple[dict[str, Any], ...]
    policy: dict[str, Any]
    input_references: dict[str, Any]
    evidence_issue_codes: tuple[str, ...]


@dataclass(frozen=True)
class Assessment:
    round_gate: dict[str, Any]
    branch_diagnoses: tuple[dict[str, Any], ...]
    coverage_assessment: dict[str, Any] | None
    instrumentation_issue_codes: tuple[str, ...] = ()

def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result

def load_json(path: Path, *, global_input: bool = False) -> Any:
    error_type = GlobalInputError if global_input else RoundInputError
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle, object_pairs_hook=reject_duplicate_keys)
    except FileNotFoundError as exc:
        raise error_type(f"Required file does not exist: {path}") from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise error_type(f"Invalid JSON in {path}: {exc}") from exc

def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()

def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RoundInputError(f"{label} must be an object")
    return value

def require_array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise RoundInputError(f"{label} must be an array")
    return value

def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RoundInputError(f"{label} must be a non-empty string")
    return value

def require_identifier(value: Any, label: str) -> str:
    result = require_string(value, label)
    if not IDENTIFIER_RE.fullmatch(result):
        raise RoundInputError(f"{label} is not a valid identifier: {result!r}")
    return result

def require_positive_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise RoundInputError(f"{label} must be a positive integer")
    return value

def require_non_negative_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RoundInputError(f"{label} must be a non-negative integer")
    return value

def schema_validator(path: Path, label: str) -> Draft202012Validator:
    value = load_json(path, global_input=True)
    if not isinstance(value, dict):
        raise GlobalInputError(f"{label} Schema must be an object")
    try:
        Draft202012Validator.check_schema(value)
    except Exception as exc:
        raise GlobalInputError(f"Invalid {label} Schema: {exc}") from exc
    return Draft202012Validator(value, format_checker=FormatChecker())

def validate_against(
    value: Any,
    validator: Draft202012Validator,
    label: str,
    error_type: type[ControllerError] = RoundInputError,
) -> None:
    errors = sorted(validator.iter_errors(value), key=lambda item: item.json_path)
    if errors:
        details = "\n".join(
            f"{item.json_path}: {item.message}" for item in errors[:12]
        )
        raise error_type(f"{label} violates its Schema:\n{details}")

def artifact_reference(
    artifact_id: str,
    version: str | int,
    content_hash: str,
) -> dict[str, Any]:
    require_identifier(artifact_id, "artifact_id")
    valid_integer = isinstance(version, int) and not isinstance(version, bool) and version >= 1
    valid_string = (
        isinstance(version, str)
        and bool(version)
        and not any(character.isspace() for character in version)
        and re.fullmatch(r"0+", version) is None
    )
    if not (valid_integer or valid_string):
        raise RoundInputError("artifact_version must be a positive integer or nonzero version string")
    if not SHA256_RE.fullmatch(content_hash):
        raise RoundInputError("artifact content_hash is invalid")
    return {
        "artifact_id": artifact_id,
        "artifact_version": version,
        "content_hash": content_hash,
    }

def harness_spec_reference(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "spec_id": record["identity"]["spec_id"],
        "revision_number": record["revision_information"]["revision_number"],
        "content_hash": canonical_hash(record),
    }

def strategy_reference(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "strategy_id": record["identity"]["strategy_id"],
        "revision_number": record["revision_information"]["revision_number"],
        "content_hash": canonical_hash(record),
    }

def harness_artifact_reference(record: Mapping[str, Any]) -> dict[str, Any]:
    return artifact_reference(
        record["identity"]["harness_artifact_id"],
        record["schema_version"],
        canonical_hash(record),
    )

def policy_reference(policy: Mapping[str, Any], path: Path) -> dict[str, Any]:
    return artifact_reference(
        policy["policy_id"], policy["policy_version"], file_hash(path)
    )

def controller_reference(path: Path) -> dict[str, Any]:
    return artifact_reference(CONTROLLER_ID, CONTROLLER_VERSION, file_hash(path))

def round_reference(round_record: Mapping[str, Any], path: Path) -> dict[str, Any]:
    return artifact_reference(
        round_record["identity"]["round_id"],
        round_record["record_format_version"],
        file_hash(path),
    )

def evidence_artifact_reference(
    round_record: Mapping[str, Any], evidence_name: str
) -> dict[str, Any] | None:
    location = round_record["evidence"][evidence_name]["location"]
    if location is None:
        return None
    return copy.deepcopy(location["artifact_ref"])

def validate_round_record_semantics(record: Mapping[str, Any]) -> None:
    identity = record["identity"]
    if identity["experimental_group"] != "bug_aware_adaptive":
        raise RoundInputError(
            "Feedback Controller accepts only bug_aware_adaptive rounds"
        )
    if record["attempt_selection"]["status"] != "selected_as_round_result":
        raise RoundInputError(
            "Feedback Controller accepts only the selected Round attempt"
        )
    if identity["round_index"] > record["schedule"]["planned_final_round_index"]:
        raise RoundInputError(
            "identity.round_index exceeds schedule.planned_final_round_index"
        )
    if record["execution"]["termination"]["reason"] not in KNOWN_TERMINATIONS:
        raise RoundInputError("Unsupported Fuzzing Round termination reason")

def validate_feedback_spec_origin(harness_spec: Mapping[str, Any]) -> None:
    if (
        harness_spec["identity"]["spec_mode"] == "bug_aware_static"
        and harness_spec["revision_information"]["feedback_request_ref"] is not None
    ):
        raise RoundInputError(
            "Static H0 must not be derived from a Feedback Request"
        )

def load_runtime_snapshot_evidence(
    round_record: Mapping[str, Any], runtime_path: Path | None
) -> tuple[dict[str, Any] | None, tuple[str, ...]]:
    declared = round_record["evidence"]["runtime_snapshot"]
    if declared["status"] == "missing":
        if runtime_path is None:
            return None, ("runtime_snapshot_missing",)
        return None, ("runtime_snapshot_invalid",)
    if runtime_path is None:
        return None, ("runtime_snapshot_missing",)

    try:
        snapshot = require_object(load_json(runtime_path), "Runtime Snapshot")
        location = declared["location"]
        if file_hash(runtime_path) != location["file_ref"]["content_hash"]:
            return None, ("runtime_snapshot_invalid",)
        if canonical_hash(snapshot) != location["artifact_ref"]["content_hash"]:
            return None, ("runtime_snapshot_invalid",)
        return snapshot, ()
    except RoundInputError:
        return None, ("runtime_snapshot_invalid",)

def round_record_validation_issue_codes(
    round_record: Mapping[str, Any]
) -> tuple[str, ...]:
    if round_record["validation"]["validation_status"] == "passed":
        return ()
    return ("round_record_validation_failed",)

def unavailable_coverage_assessment() -> dict[str, Any]:
    return {
        "trend": "coverage_unavailable",
        "coverage_summary_ref": None,
    }

def validate_policy(policy: Any) -> dict[str, Any]:
    value = require_object(policy, "Adaptive Feedback Policy")
    required = {
        "policy_id",
        "policy_version",
        "policy_kind",
        "calibration",
        "protocol",
        "scope",
        "selector_space",
        "evidence_thresholds",
        "diagnosis_thresholds",
        "coverage_trend",
        "history_rules",
        "allocation_rules",
        "decision_rules",
        "post_materialization_rules",
        "tie_breaking",
        "required_invariants",
        "excluded_signals",
    }
    if set(value) != required:
        raise GlobalInputError(
            "Adaptive Feedback Policy fields do not match policy v0.4"
        )
    if value["policy_kind"] != "adaptive_branch_budget":
        raise GlobalInputError("Unsupported feedback policy kind")
    scope = require_object(value["scope"], "Adaptive Feedback Policy scope")
    if scope.get("applicable_spec_modes") != [
        "bug_aware_static",
        "bug_aware_adaptive",
    ]:
        raise GlobalInputError(
            "Feedback policy must allow shared Static H0 and Adaptive revisions"
        )
    if (
        scope.get("shared_initial_spec_mode") != "bug_aware_static"
        or scope.get("feedback_candidate_spec_mode") != "bug_aware_adaptive"
    ):
        raise GlobalInputError("Feedback policy mode transition is invalid")
    if value["calibration"].get("status") not in {
        "pilot_initial",
        "pilot_calibrated",
        "main_experiment_frozen",
    }:
        raise GlobalInputError("Unsupported policy calibration status")
    evidence = require_object(
        value["evidence_thresholds"],
        "Adaptive Feedback Policy evidence_thresholds",
    )
    require_positive_integer(
        evidence.get("minimum_branch_activation_attempts"),
        "evidence_thresholds.minimum_branch_activation_attempts",
    )
    require_non_negative_integer(
        evidence.get("maximum_branch_activation_check_error_count"),
        "evidence_thresholds.maximum_branch_activation_check_error_count",
    )
    diagnosis = require_object(
        value["diagnosis_thresholds"],
        "Adaptive Feedback Policy diagnosis_thresholds",
    )
    unevaluable = require_object(
        diagnosis.get("activation_unevaluable"),
        "diagnosis_thresholds.activation_unevaluable",
    )
    require_non_negative_integer(
        unevaluable.get("maximum_checked_count"),
        "diagnosis_thresholds.activation_unevaluable.maximum_checked_count",
    )
    require_positive_integer(
        unevaluable.get("minimum_unevaluable_count"),
        "diagnosis_thresholds.activation_unevaluable.minimum_unevaluable_count",
    )
    selector = value["selector_space"]
    if selector.get("total_slots") != 256:
        raise GlobalInputError("Controller v0.5 requires a 256-slot selector")
    allocation = value["allocation_rules"]
    if allocation.get("maximum_boost_recipients_per_transition") != 1:
        raise GlobalInputError(
            "Controller v0.5 requires one boost recipient per transition"
        )
    donor_rules = require_object(
        allocation.get("donor_rules"),
        "allocation_rules.donor_rules",
    )
    excluded_donor_statuses = donor_rules.get("excluded_branch_statuses")
    if excluded_donor_statuses != ["branch_activation_unevaluable"]:
        raise GlobalInputError(
            "Controller v0.5 requires unevaluable Branches to be excluded as donors"
        )
    return value

def load_prior_decisions(
    paths: Sequence[Path],
    validator: Draft202012Validator,
    scope: Mapping[str, Any],
) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    items: list[tuple[dict[str, Any], Path]] = []
    resolved_paths = [item.resolve() for item in paths]
    if len(resolved_paths) != len(set(resolved_paths)):
        raise RoundInputError("The same prior Decision path was supplied more than once")
    for path in sorted(resolved_paths, key=lambda item: item.as_posix()):
        record = require_object(load_json(path), f"Feedback Decision {path}")
        validate_against(record, validator, f"Feedback Decision {path}")
        key_payload = copy.deepcopy(record)
        declared_key = key_payload.pop("decision_key")
        if canonical_hash(key_payload) != declared_key:
            raise RoundInputError(f"Feedback Decision key does not verify: {path}")

        prior_scope = record["scope"]
        same_isolation = (
            prior_scope["target_api_id"] == scope["target_api_id"]
            and prior_scope["experimental_group"] == scope["experimental_group"]
            and prior_scope["independent_repeat_id"]
            == scope["independent_repeat_id"]
        )
        if not same_isolation:
            raise RoundInputError(
                f"Prior Decision crosses the feedback isolation boundary: {path}"
            )
        if prior_scope["effective_from_round_index"] != (
            prior_scope["observed_round_index"] + 1
        ):
            raise RoundInputError(f"Prior Decision has an invalid effective round: {path}")
        if prior_scope["observed_round_index"] >= scope["round_index"]:
            raise RoundInputError(
                f"Prior Decision is not earlier than the observed round: {path}"
            )
        items.append((record, path))

    items.sort(key=lambda pair: pair[0]["scope"]["observed_round_index"])
    indices = [item[0]["scope"]["observed_round_index"] for item in items]
    expected_indices = list(range(1, scope["round_index"]))
    if indices != expected_indices:
        raise RoundInputError(
            "Prior Decisions must contain exactly one contiguous record for every "
            "earlier round"
        )

    records = tuple(item[0] for item in items)
    references = tuple(
        {
            "decision_id": record["decision_id"],
            "content_hash": file_hash(path),
        }
        for record, path in items
    )
    for index, record in enumerate(records):
        declared = record["input_references"]["prior_feedback_decision_refs"]
        if declared != list(references[:index]):
            raise RoundInputError(
                "Prior Decision chain is incomplete, reordered, or hash-inconsistent"
            )
        if record["run_disposition"]["value"] != "continue":
            raise RoundInputError(
                "A new round cannot follow a non-continuing prior Decision"
            )
    return records, references

def expected_refs_after_decision(
    decision: Mapping[str, Any]
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    materialization = decision["materialization"]
    if materialization["outcome"] == "accepted":
        return (
            materialization["candidate_harness_spec_ref"],
            materialization["candidate_strategy_ref"],
            materialization["candidate_harness_artifact_ref"],
        )
    references = decision["input_references"]
    return (
        references["current_harness_spec_ref"],
        references["current_strategy_ref"],
        references["current_harness_artifact_ref"],
    )

def resolve_inputs(args: argparse.Namespace) -> ResolvedRound:
    round_validator = schema_validator(args.round_schema, "Fuzzing Round")
    decision_validator = schema_validator(args.decision_schema, "Feedback Decision")
    spec_validator = schema_validator(args.harness_spec_schema, "HarnessSpec")
    strategy_validator = schema_validator(args.strategy_schema, "Strategy Plan")
    artifact_validator = schema_validator(
        args.harness_artifact_schema, "Harness Artifact"
    )

    policy = validate_policy(load_json(args.policy, global_input=True))
    round_record = require_object(load_json(args.round_record), "Fuzzing Round record")
    validate_against(round_record, round_validator, "Fuzzing Round record")
    validate_round_record_semantics(round_record)

    harness_spec = require_object(load_json(args.harness_spec), "HarnessSpec")
    strategy = require_object(load_json(args.strategy_plan), "Strategy Plan")
    harness_artifact = require_object(
        load_json(args.harness_artifact), "Harness Artifact"
    )
    validate_against(harness_spec, spec_validator, "HarnessSpec")
    validate_against(strategy, strategy_validator, "Strategy Plan")
    validate_against(harness_artifact, artifact_validator, "Harness Artifact")

    scope = round_record["identity"]
    spec_identity = harness_spec["identity"]
    strategy_identity = strategy["identity"]
    allowed_modes = set(policy["scope"]["applicable_spec_modes"])
    if (
        scope["experimental_group"] != "bug_aware_adaptive"
        or spec_identity["target_api"] != scope["target_api_id"]
        or strategy_identity["target_api"] != scope["target_api_id"]
        or spec_identity["spec_mode"] != strategy_identity["spec_mode"]
        or spec_identity["spec_mode"] not in allowed_modes
    ):
        raise RoundInputError("Round, HarnessSpec, and Strategy scope do not match")
    validate_feedback_spec_origin(harness_spec)

    spec_ref = harness_spec_reference(harness_spec)
    strategy_ref = strategy_reference(strategy)
    artifact_ref = harness_artifact_reference(harness_artifact)
    if strategy["source_context"]["harness_spec_ref"] != spec_ref:
        raise RoundInputError("Strategy does not reference the exact HarnessSpec")
    if harness_artifact["source_context"]["strategy_revision_ref"] != strategy_ref:
        raise RoundInputError("Harness Artifact does not reference the exact Strategy")

    declared = round_record["source_context"]
    if declared["harness_spec_ref"] != spec_ref:
        raise RoundInputError("Fuzzing Round does not reference the exact HarnessSpec")
    if declared["strategy_ref"] != strategy_ref:
        raise RoundInputError("Fuzzing Round does not reference the exact Strategy")
    if declared["harness_artifact_ref"] != artifact_ref:
        raise RoundInputError("Fuzzing Round does not reference the exact Harness Artifact")

    prior_decisions, prior_refs = load_prior_decisions(
        args.prior_decision, decision_validator, scope
    )
    if prior_decisions:
        expected = expected_refs_after_decision(prior_decisions[-1])
        if expected != (spec_ref, strategy_ref, artifact_ref):
            raise RoundInputError(
                "Current artifacts do not continue the accepted prior Decision state"
            )
        prior_output_corpus = prior_decisions[-1]["input_references"][
            "output_corpus_ref"
        ]
        if declared["input_corpus_ref"] != prior_output_corpus:
            raise RoundInputError(
                "Current input corpus does not continue the preceding round output corpus"
            )

    runtime_snapshot, runtime_issues = load_runtime_snapshot_evidence(
        round_record, args.runtime_snapshot
    )
    evidence_issues = tuple(
        sorted(
            set(runtime_issues)
            | set(round_record_validation_issue_codes(round_record))
        )
    )
    input_references = {
        "current_harness_spec_ref": spec_ref,
        "current_strategy_ref": strategy_ref,
        "current_harness_artifact_ref": artifact_ref,
        "fuzzing_round_ref": round_reference(round_record, args.round_record),
        "runtime_snapshot_ref": evidence_artifact_reference(
            round_record, "runtime_snapshot"
        ),
        "coverage_summary_ref": evidence_artifact_reference(
            round_record, "coverage_summary"
        ),
        "output_corpus_ref": evidence_artifact_reference(
            round_record, "output_corpus"
        ),
        "feedback_policy_ref": policy_reference(policy, args.policy),
        "controller_ref": controller_reference(Path(__file__).resolve()),
        "prior_feedback_decision_refs": list(prior_refs),
    }
    return ResolvedRound(
        round_record=round_record,
        runtime_snapshot=runtime_snapshot,
        harness_artifact=harness_artifact,
        strategy=strategy,
        harness_spec=harness_spec,
        prior_decisions=prior_decisions,
        prior_decision_refs=prior_refs,
        policy=policy,
        input_references=input_references,
        evidence_issue_codes=evidence_issues,
    )

def event_index(
    harness_artifact: Mapping[str, Any],
    runtime_snapshot: Mapping[str, Any],
) -> tuple[dict[tuple[str, str], list[dict[str, Any]]], list[int]]:
    site_count = require_non_negative_integer(
        runtime_snapshot.get("site_count"), "runtime_snapshot.site_count"
    )
    counts_raw = require_array(
        runtime_snapshot.get("site_counts"), "runtime_snapshot.site_counts"
    )
    counts = [
        require_non_negative_integer(value, f"site_counts[{index}]")
        for index, value in enumerate(counts_raw)
    ]
    if len(counts) != site_count:
        raise CounterConsistencyError("site_counts length does not equal site_count")

    entries = require_array(
        harness_artifact["instrumentation_map"], "instrumentation_map"
    )
    if len(entries) != site_count:
        raise InstrumentationBindingError(
            "Runtime site_count does not match the Harness instrumentation map"
        )
    by_site: dict[int, dict[str, Any]] = {}
    by_branch_kind: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for entry in entries:
        site_id = require_non_negative_integer(
            entry["runtime_site_id"], "runtime_site_id"
        )
        if site_id in by_site:
            raise InstrumentationBindingError(f"Duplicate runtime_site_id: {site_id}")
        if site_id >= site_count:
            raise InstrumentationBindingError(
                f"runtime_site_id is out of range: {site_id}"
            )
        by_site[site_id] = entry
        key = (entry["branch_id"], entry["event_kind"])
        by_branch_kind.setdefault(key, []).append(entry)
    if set(by_site) != set(range(site_count)):
        raise InstrumentationBindingError(
            "Instrumentation site IDs are not contiguous"
        )
    return by_branch_kind, counts

def event_total(
    index: Mapping[tuple[str, str], Sequence[Mapping[str, Any]]],
    counts: Sequence[int],
    branch_id: str,
    event_kind: str,
    *,
    exactly_one: bool = False,
    require_present: bool = False,
    aggregation: str = "sum",
) -> tuple[int, list[str]]:
    entries = list(index.get((branch_id, event_kind), ()))
    if exactly_one and len(entries) != 1:
        raise InstrumentationBindingError(
            f"Branch {branch_id} requires exactly one {event_kind} site"
        )
    if require_present and not entries:
        raise InstrumentationBindingError(
            f"Branch {branch_id} requires at least one {event_kind} site"
        )
    values = [counts[item["runtime_site_id"]] for item in entries]
    if aggregation == "sum":
        total = sum(values)
    elif aggregation == "maximum":
        total = max(values, default=0)
    elif aggregation == "minimum":
        total = min(values, default=0)
    else:
        raise InstrumentationBindingError(
            f"Unsupported event aggregation: {aggregation}"
        )
    return (
        total,
        [item["instrumentation_binding_id"] for item in entries],
    )

def branch_measurements(
    harness_spec: Mapping[str, Any],
    harness_artifact: Mapping[str, Any],
    runtime_snapshot: Mapping[str, Any],
) -> list[dict[str, Any]]:
    index, counts = event_index(harness_artifact, runtime_snapshot)
    measurements: list[dict[str, Any]] = []

    for branch in harness_spec["exploration_plan"]["branches"]:
        branch_id = branch["branch_id"]
        binding_refs: list[str] = []
        selected, refs = event_total(
            index, counts, branch_id, "branch_entered", exactly_one=True
        )
        binding_refs.extend(refs)
        target_reached, refs = event_total(
            index,
            counts,
            branch_id,
            "target_api_reached",
            require_present=True,
            aggregation="maximum",
        )
        binding_refs.extend(refs)
        rejected, refs = event_total(index, counts, branch_id, "input_rejected")
        binding_refs.extend(refs)

        activation_required = bool(branch["activation_targets"])
        activation_checked: int | None = None
        activation_true: int | None = None
        activation_unevaluable: int | None = None
        activation_check_error: int | None = None
        if activation_required:
            activation_checked, refs = event_total(
                index, counts, branch_id, "branch_activation_checked",
                exactly_one=True,
            )
            binding_refs.extend(refs)
            activation_true, refs = event_total(
                index, counts, branch_id, "branch_activation_true",
                exactly_one=True,
            )
            binding_refs.extend(refs)
            activation_unevaluable, refs = event_total(
                index, counts, branch_id, "branch_activation_unevaluable",
                exactly_one=True,
            )
            binding_refs.extend(refs)
            activation_check_error, refs = event_total(
                index, counts, branch_id, "branch_activation_check_error",
                exactly_one=True,
            )
            binding_refs.extend(refs)

        required_oracles = [
            item
            for item in branch["oracle_requirements"]
            if item.get("requirement_level") == "required"
        ]
        oracle_required = bool(required_oracles)
        oracle_opportunities: int | None = None
        oracle_evaluated: int | None = None
        if oracle_required:
            oracle_opportunities, refs = event_total(
                index,
                counts,
                branch_id,
                "target_api_completed",
                require_present=True,
                aggregation="minimum",
            )
            binding_refs.extend(refs)
            oracle_evaluated, refs = event_total(
                index, counts, branch_id, "oracle_evaluated", exactly_one=True
            )
            binding_refs.extend(refs)

        if target_reached > selected or rejected > selected:
            raise CounterConsistencyError(
                f"Branch {branch_id} counters exceed branch_selected_count"
            )
        if activation_required and (
            activation_checked is None
            or activation_true is None
            or activation_unevaluable is None
            or activation_check_error is None
            or activation_true > activation_checked
            or activation_checked > selected
            or activation_unevaluable > selected
            or activation_check_error > selected
            or activation_checked + activation_unevaluable
            + activation_check_error > selected
        ):
            raise CounterConsistencyError(
                f"Branch {branch_id} Activation counters are inconsistent"
            )
        if oracle_required and (
            oracle_opportunities is None
            or oracle_evaluated is None
            or oracle_evaluated > oracle_opportunities
            or oracle_opportunities > target_reached
        ):
            raise CounterConsistencyError(
                f"Branch {branch_id} Oracle counters are inconsistent"
            )

        measurements.append(
            {
                "branch_id": branch_id,
                "measurements": {
                    "branch_selected_count": selected,
                    "target_reached_count": target_reached,
                    "input_rejected_count": rejected,
                    "activation_required": activation_required,
                    "activation_checked_count": activation_checked,
                    "activation_true_count": activation_true,
                    "activation_unevaluable_count": activation_unevaluable,
                    "activation_check_error_count": activation_check_error,
                    "oracle_required": oracle_required,
                    "oracle_opportunity_count": oracle_opportunities,
                    "oracle_evaluated_count": oracle_evaluated,
                },
                "instrumentation_binding_refs": sorted(set(binding_refs)),
            }
        )
    return measurements

def assess_round(resolved: ResolvedRound) -> Assessment:
    record = resolved.round_record
    snapshot = resolved.runtime_snapshot
    policy = resolved.policy
    termination = record["execution"]["termination"]
    candidate_evidence = record["evidence"]["candidate_evidence"]

    if candidate_evidence["status"] == "present":
        issue_codes = sorted(
            {
                CANDIDATE_OBSERVATION_CODES[item["observation_kind"]]
                for item in candidate_evidence["observations"]
            }
        )
        return Assessment(
            round_gate={
                "result": "crash_or_sanitizer_candidate",
                "issue_codes": issue_codes,
            },
            branch_diagnoses=(),
            coverage_assessment=None,
        )

    if termination["reason"] == "unknown":
        return Assessment(
            round_gate={
                "result": "evidence_ineligible",
                "issue_codes": ["termination_reason_unknown"],
            },
            branch_diagnoses=(),
            coverage_assessment=None,
        )
    if termination["reason"] == "infrastructure_failure":
        return Assessment(
            round_gate={
                "result": "evidence_ineligible",
                "issue_codes": ["infrastructure_failure_observed"],
            },
            branch_diagnoses=(),
            coverage_assessment=None,
        )
    if termination["reason"] == "cancelled":
        return Assessment(
            round_gate={
                "result": "evidence_ineligible",
                "issue_codes": ["round_cancelled"],
            },
            branch_diagnoses=(),
            coverage_assessment=None,
        )

    if resolved.evidence_issue_codes:
        return Assessment(
            round_gate={
                "result": "evidence_ineligible",
                "issue_codes": list(resolved.evidence_issue_codes),
            },
            branch_diagnoses=(),
            coverage_assessment=None,
        )

    if snapshot is None:
        return Assessment(
            round_gate={
                "result": "evidence_ineligible",
                "issue_codes": ["runtime_snapshot_missing"],
            },
            branch_diagnoses=(),
            coverage_assessment=None,
        )

    issues: list[str] = []
    snapshot_evidence = record["evidence"]["runtime_snapshot"]
    source_context = record["source_context"]
    if snapshot.get("record_format_version") != source_context[
        "instrumentation_contract_version"
    ]:
        issues.append("runtime_snapshot_invalid")
    if snapshot.get("runtime_version") != str(
        source_context["instrumentation_runtime_ref"]["artifact_version"]
    ):
        issues.append("runtime_snapshot_invalid")
    if snapshot.get("snapshot_kind") != snapshot_evidence["snapshot_kind"]:
        issues.append("runtime_snapshot_invalid")
    if snapshot.get("artifact_id") != resolved.harness_artifact["identity"][
        "harness_artifact_id"
    ]:
        issues.append("artifact_identity_mismatch")
    if snapshot.get("generation_key") != resolved.harness_artifact["identity"][
        "generation_key"
    ]:
        issues.append("generation_key_mismatch")

    for field in (
        "site_count",
        "started_iterations",
        "finished_iterations",
        "unwound_iterations",
        "invalid_site_records",
        "export_failures",
    ):
        try:
            require_non_negative_integer(snapshot.get(field), f"snapshot.{field}")
        except RoundInputError:
            issues.append("runtime_snapshot_invalid")

    if not issues:
        started = snapshot["started_iterations"]
        finished = snapshot["finished_iterations"]
        unwound = snapshot["unwound_iterations"]
        if finished > started or unwound > finished:
            issues.append("counter_inconsistent")
        if snapshot["invalid_site_records"] != 0:
            issues.append("invalid_site_record_observed")
        if snapshot["export_failures"] != 0:
            issues.append("runtime_export_failure")
        if snapshot["site_count"] != len(
            resolved.harness_artifact["instrumentation_map"]
        ):
            issues.append("site_count_mismatch")

    if snapshot.get("snapshot_kind") == "periodic":
        staleness = snapshot_evidence["staleness_iterations"]
        maximum = policy["evidence_thresholds"][
            "maximum_periodic_snapshot_staleness_iterations"
        ]
        if staleness is None or staleness > maximum:
            issues.append("snapshot_too_stale")

    measured: list[dict[str, Any]] = []
    instrumentation_issues: list[str] = []
    if not issues:
        try:
            measured = branch_measurements(
                resolved.harness_spec,
                resolved.harness_artifact,
                snapshot,
            )
        except InstrumentationBindingError:
            instrumentation_issues.append("missing_instrumentation_binding")
        except CounterConsistencyError:
            instrumentation_issues.append("counter_inconsistent")
        except RoundInputError:
            instrumentation_issues.append("runtime_snapshot_invalid")
    issues.extend(instrumentation_issues)
    if issues:
        return Assessment(
            round_gate={
                "result": "evidence_ineligible",
                "issue_codes": sorted(set(issues)),
            },
            branch_diagnoses=(),
            coverage_assessment=None,
            instrumentation_issue_codes=tuple(instrumentation_issues),
        )

    maximum_checker_errors = policy["evidence_thresholds"][
        "maximum_branch_activation_check_error_count"
    ]
    if any(
        (item["measurements"]["activation_check_error_count"] or 0)
        > maximum_checker_errors
        for item in measured
    ):
        return Assessment(
            round_gate={
                "result": "evidence_ineligible",
                "issue_codes": ["activation_checker_error_observed"],
            },
            branch_diagnoses=(),
            coverage_assessment=None,
        )

    minimum = policy["evidence_thresholds"]["minimum_completed_iterations"]
    if snapshot["finished_iterations"] < minimum:
        return Assessment(
            round_gate={
                "result": "insufficient_total_samples",
                "issue_codes": ["completed_iterations_below_minimum"],
            },
            branch_diagnoses=(),
            coverage_assessment=None,
        )

    diagnoses = tuple(diagnose_branch(item, policy) for item in measured)
    return Assessment(
        round_gate={"result": "eligible", "issue_codes": []},
        branch_diagnoses=diagnoses,
        coverage_assessment=unavailable_coverage_assessment(),
    )

def diagnose_branch(
    measured: Mapping[str, Any], policy: Mapping[str, Any]
) -> dict[str, Any]:
    values = measured["measurements"]
    evidence = policy["evidence_thresholds"]
    thresholds = policy["diagnosis_thresholds"]
    statuses: list[str] = []

    selected = values["branch_selected_count"]
    target_reached = values["target_reached_count"]
    rejected = values["input_rejected_count"]
    under_sampled = selected < evidence["minimum_branch_selected_cases"]
    if values["activation_required"]:
        checked = values["activation_checked_count"]
        attempts = checked + values["activation_unevaluable_count"]
        under_sampled = under_sampled or (
            attempts < evidence["minimum_branch_activation_attempts"]
        )
    if values["oracle_required"]:
        opportunities = values["oracle_opportunity_count"]
        under_sampled = under_sampled or (
            opportunities < evidence["minimum_oracle_opportunities"]
        )

    if under_sampled:
        statuses.append("branch_under_sampled")
    else:
        if selected > 0 and rejected / selected >= thresholds[
            "rejection_dominated"
        ]["minimum_rejection_rate"]:
            statuses.append("branch_rejection_dominated")
        if target_reached <= thresholds["target_unreachable"][
            "maximum_target_reached_count"
        ]:
            statuses.append("branch_target_unreachable")

        if values["activation_required"]:
            checked = values["activation_checked_count"]
            activated = values["activation_true_count"]
            unevaluable = values["activation_unevaluable_count"]
            unevaluable_threshold = thresholds["activation_unevaluable"]
            if (
                checked <= unevaluable_threshold["maximum_checked_count"]
                and unevaluable >= unevaluable_threshold[
                    "minimum_unevaluable_count"
                ]
            ):
                statuses.append("branch_activation_unevaluable")
            elif activated <= thresholds["activation_absent"][
                "maximum_activation_true_count"
            ]:
                statuses.append("branch_activation_absent")
            else:
                rate = activated / checked
                rare = thresholds["activation_rare"]
                if (
                    rate > rare["minimum_activation_rate_exclusive"]
                    and rate < rare["maximum_activation_rate_exclusive"]
                ):
                    statuses.append("branch_activation_rare")

        if values["oracle_required"]:
            opportunities = values["oracle_opportunity_count"]
            evaluated = values["oracle_evaluated_count"]
            if evaluated / opportunities < thresholds["oracle_unevaluable"][
                "minimum_evaluable_rate"
            ]:
                statuses.append("branch_oracle_unevaluable")

    ordered = [name for name in BRANCH_STATUS_ORDER if name in set(statuses)]
    if not ordered:
        ordered = ["branch_healthy"]
    return {
        "branch_id": measured["branch_id"],
        "primary_status": ordered[0],
        "supporting_statuses": ordered[1:],
        "measurements": copy.deepcopy(values),
        "instrumentation_binding_refs": list(
            measured["instrumentation_binding_refs"]
        ),
    }

def selector_allocations(branches: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not branches or len(branches) > 256:
        raise RoundInputError("Branch count is incompatible with a 256-slot selector")
    weights = [Decimal(str(branch["budget_share"])) for branch in branches]
    if any(weight <= 0 for weight in weights):
        raise RoundInputError("Every Branch budget_share must be positive")
    total = sum(weights)
    quotas = [weight * Decimal(256) / total for weight in weights]
    allocations = [
        max(1, int(quota.to_integral_value(rounding=ROUND_FLOOR)))
        for quota in quotas
    ]
    while sum(allocations) > 256:
        candidates = [i for i, value in enumerate(allocations) if value > 1]
        if not candidates:
            raise RoundInputError("Cannot assign a positive slot to every Branch")
        selected = min(
            candidates,
            key=lambda i: (
                -(Decimal(allocations[i]) - quotas[i]),
                branches[i]["branch_id"],
            ),
        )
        allocations[selected] -= 1
    while sum(allocations) < 256:
        selected = min(
            range(len(branches)),
            key=lambda i: (
                -(quotas[i] - Decimal(allocations[i])),
                branches[i]["branch_id"],
            ),
        )
        allocations[selected] += 1
    return [
        {"branch_id": branch["branch_id"], "selector_slots": slots}
        for branch, slots in zip(branches, allocations)
    ]

def accepted_boost_history(
    records: Sequence[Mapping[str, Any]],
    references: Sequence[Mapping[str, Any]],
) -> tuple[
    dict[str, int],
    dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]],
]:
    counts: dict[str, int] = {}
    open_episodes: dict[
        str, tuple[Mapping[str, Any], Mapping[str, Any]]
    ] = {}
    for record, reference in zip(records, references):
        if record["materialization"]["outcome"] != "accepted":
            continue
        budget = record["budget_decision"]
        if budget["transition_kind"] == "exploration_boost":
            recipients = {
                transfer["recipient_branch_id"] for transfer in budget["transfers"]
            }
            if len(recipients) != 1:
                raise RoundInputError(
                    "An accepted exploration boost must have exactly one recipient"
                )
            recipient = next(iter(recipients))
            if recipient in open_episodes:
                raise RoundInputError(
                    f"Branch {recipient} has overlapping accepted boost episodes"
                )
            counts[recipient] = counts.get(recipient, 0) + 1
            open_episodes[recipient] = (record, reference)
        elif budget["transition_kind"] == "restore_pre_boost_allocation":
            pre_boost_ref = budget["pre_boost_decision_ref"]
            matches = [
                branch_id
                for branch_id, (_, boost_ref) in open_episodes.items()
                if boost_ref == pre_boost_ref
            ]
            if len(matches) != 1:
                raise RoundInputError(
                    "An accepted restoration does not close exactly one boost episode"
                )
            del open_episodes[matches[0]]
    return counts, open_episodes

def allocation_map(vector: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in vector:
        branch_id = item["branch_id"]
        slots = item["selector_slots"]
        if branch_id in result:
            raise RoundInputError(f"Duplicate allocation for Branch {branch_id}")
        result[branch_id] = slots
    return result

def allocation_vector(values: Mapping[str, int]) -> list[dict[str, Any]]:
    return [
        {"branch_id": branch_id, "selector_slots": values[branch_id]}
        for branch_id in sorted(values)
    ]

def compute_transfers(
    current: Mapping[str, int], proposed: Mapping[str, int]
) -> list[dict[str, Any]]:
    donors = [[key, current[key] - proposed[key]] for key in sorted(current) if current[key] > proposed[key]]
    recipients = [[key, proposed[key] - current[key]] for key in sorted(current) if proposed[key] > current[key]]
    transfers: list[dict[str, Any]] = []
    donor_index = 0
    recipient_index = 0
    while donor_index < len(donors) and recipient_index < len(recipients):
        donor_id, donor_slots = donors[donor_index]
        recipient_id, recipient_slots = recipients[recipient_index]
        amount = min(donor_slots, recipient_slots)
        transfers.append(
            {
                "donor_branch_id": donor_id,
                "recipient_branch_id": recipient_id,
                "selector_slots": amount,
            }
        )
        donors[donor_index][1] -= amount
        recipients[recipient_index][1] -= amount
        if donors[donor_index][1] == 0:
            donor_index += 1
        if recipients[recipient_index][1] == 0:
            recipient_index += 1
    if donor_index != len(donors) or recipient_index != len(recipients):
        raise RoundInputError("Allocation vectors do not conserve selector slots")
    return transfers

def no_change_decision(
    current: Sequence[Mapping[str, Any]], reason: str
) -> dict[str, Any]:
    return {
        "budget_action": "retain_current",
        "transition_kind": "none",
        "no_change_reason": reason,
        "current_allocation": list(current),
        "proposed_allocation": None,
        "transfers": [],
        "pre_boost_decision_ref": None,
    }

def decide_budget(
    resolved: ResolvedRound, assessment: Assessment
) -> dict[str, Any]:
    branches = resolved.harness_spec["exploration_plan"]["branches"]
    current_vector = selector_allocations(branches)
    current = allocation_map(current_vector)
    identity = resolved.round_record["identity"]
    schedule = resolved.round_record["schedule"]
    if identity["round_index"] == schedule["planned_final_round_index"]:
        return no_change_decision(current_vector, "final_scheduled_round")
    if assessment.round_gate["result"] != "eligible":
        return no_change_decision(current_vector, "round_not_eligible")
    if len(branches) == 1:
        return no_change_decision(current_vector, "single_branch_only")

    policy = resolved.policy
    allocation_rules = policy["allocation_rules"]
    floors = allocation_rules["floor_slots"]
    ceilings = allocation_rules["ceiling_slots"]
    default_id = resolved.harness_spec["exploration_plan"]["default_branch_id"]
    diagnoses = {item["branch_id"]: item for item in assessment.branch_diagnoses}
    boost_counts, open_boosts = accepted_boost_history(
        resolved.prior_decisions, resolved.prior_decision_refs
    )

    persistent: list[
        tuple[
            int,
            str,
            Mapping[str, Any],
            Mapping[str, Any],
        ]
    ] = []
    history = policy["history_rules"]
    for branch_id, (boost_record, boost_ref) in open_boosts.items():
        diagnosis = diagnoses.get(branch_id)
        if diagnosis is None or diagnosis["primary_status"] != "branch_activation_absent":
            continue
        boost_round = boost_record["scope"]["observed_round_index"]
        later_eligible = sum(
            item["scope"]["observed_round_index"] > boost_round
            and item["round_assessment"]["round_gate"]["result"] == "eligible"
            for item in resolved.prior_decisions
        ) + 1
        checked = diagnosis["measurements"]["activation_checked_count"] or 0
        if (
            later_eligible >= history["minimum_post_boost_eligible_rounds"]
            and checked >= history["minimum_post_boost_activation_checked_cases"]
        ):
            persistent.append(
                (boost_round, branch_id, boost_record, boost_ref)
            )

    if persistent:
        _, _, boost_record, boost_ref = max(
            persistent, key=lambda item: (item[0], item[1])
        )
        proposed = allocation_map(
            boost_record["budget_decision"]["current_allocation"]
        )
        if set(proposed) != set(current):
            raise RoundInputError(
                "Pre-boost allocation does not match the current Branch set"
            )
        validate_allocation(proposed, branches, default_id, allocation_rules)
        transfers = compute_transfers(current, proposed)
        if proposed != current and transfers:
            validate_transfers(current, proposed, transfers)
            return {
                "budget_action": "reallocate_budget",
                "transition_kind": "restore_pre_boost_allocation",
                "no_change_reason": None,
                "current_allocation": allocation_vector(current),
                "proposed_allocation": allocation_vector(proposed),
                "transfers": transfers,
                "pre_boost_decision_ref": copy.deepcopy(boost_ref),
            }

    recipient_priority = {
        item["branch_status"]: item["priority"]
        for item in allocation_rules["recipient_rules"]
    }
    recipients: list[tuple[int, str]] = []
    for branch_id, diagnosis in diagnoses.items():
        status = diagnosis["primary_status"]
        if status not in recipient_priority:
            continue
        if boost_counts.get(branch_id, 0) >= history[
            "maximum_accepted_exploration_boosts_per_branch"
        ]:
            continue
        recipients.append((recipient_priority[status], branch_id))
    if not recipients:
        return no_change_decision(current_vector, "no_eligible_recipient")

    _, recipient = min(recipients, key=lambda item: (item[0], item[1]))
    ceiling = ceilings["multiple_branch_maximum"]
    capacity = ceiling - current[recipient]
    if capacity <= 0:
        return no_change_decision(current_vector, "recipient_at_ceiling")

    donors: list[tuple[int, str, int]] = []
    persistent_branches = {item[1] for item in persistent}
    excluded_donor_statuses = set(
        allocation_rules["donor_rules"]["excluded_branch_statuses"]
    )
    for branch_id, slots in current.items():
        if branch_id == recipient:
            continue
        if diagnoses[branch_id]["primary_status"] in excluded_donor_statuses:
            continue
        floor = (
            floors["default_branch"]
            if branch_id == default_id
            else floors["non_default_branch"]
        )
        surplus = slots - floor
        if surplus > 0:
            persistent_rank = 0 if branch_id in persistent_branches else 1
            donors.append((persistent_rank, branch_id, surplus))
    if not donors:
        return no_change_decision(current_vector, "no_eligible_donor")

    maximum = allocation_rules["maximum_transfer_slots_per_transition"]
    transferable = min(maximum, capacity, sum(item[2] for item in donors))
    if transferable < policy["selector_space"]["minimum_effective_transfer_slots"]:
        return no_change_decision(current_vector, "insufficient_donor_surplus")

    proposed = dict(current)
    remaining = transferable
    donors.sort(key=lambda item: (item[0], -item[2], item[1]))
    for _, donor, surplus in donors:
        amount = min(surplus, remaining)
        proposed[donor] -= amount
        proposed[recipient] += amount
        remaining -= amount
        if remaining == 0:
            break
    validate_allocation(proposed, branches, default_id, allocation_rules)
    transfers = compute_transfers(current, proposed)
    if not transfers or proposed == current:
        return no_change_decision(current_vector, "selector_ranges_unchanged")
    validate_transfers(current, proposed, transfers)
    return {
        "budget_action": "reallocate_budget",
        "transition_kind": "exploration_boost",
        "no_change_reason": None,
        "current_allocation": allocation_vector(current),
        "proposed_allocation": allocation_vector(proposed),
        "transfers": transfers,
        "pre_boost_decision_ref": None,
    }

def validate_allocation(
    allocation: Mapping[str, int],
    branches: Sequence[Mapping[str, Any]],
    default_id: str,
    rules: Mapping[str, Any],
) -> None:
    branch_ids = {item["branch_id"] for item in branches}
    if set(allocation) != branch_ids or sum(allocation.values()) != 256:
        raise RoundInputError("Allocation changes Branch identity or total slots")
    for branch_id, slots in allocation.items():
        if slots < 1:
            raise RoundInputError("Every active Branch must retain a positive slot")
        floor = rules["floor_slots"][
            "default_branch" if branch_id == default_id else "non_default_branch"
        ]
        ceiling = rules["ceiling_slots"][
            "single_branch" if len(branches) == 1 else "multiple_branch_maximum"
        ]
        if slots < floor or slots > ceiling:
            raise RoundInputError(
                f"Branch {branch_id} violates its allocation floor or ceiling"
            )

def validate_transfers(
    current: Mapping[str, int],
    proposed: Mapping[str, int],
    transfers: Sequence[Mapping[str, Any]],
) -> None:
    donor_ids = {item["donor_branch_id"] for item in transfers}
    recipient_ids = {item["recipient_branch_id"] for item in transfers}
    if donor_ids & recipient_ids:
        raise RoundInputError("Transfer donor and recipient sets must be disjoint")
    reconstructed = dict(current)
    for transfer in transfers:
        donor = transfer["donor_branch_id"]
        recipient = transfer["recipient_branch_id"]
        amount = require_positive_integer(
            transfer["selector_slots"], "transfer.selector_slots"
        )
        if donor == recipient or donor not in current or recipient not in current:
            raise RoundInputError("Transfer contains an invalid donor or recipient")
        reconstructed[donor] -= amount
        reconstructed[recipient] += amount
    if reconstructed != dict(proposed):
        raise RoundInputError("Transfers do not reconstruct the proposed allocation")


def consecutive_prior_results(
    records: Sequence[Mapping[str, Any]],
    *,
    gate_result: str | None = None,
    materialization_outcome: str | None = None,
) -> int:
    count = 0
    for record in reversed(records):
        if gate_result is not None and record["round_assessment"]["round_gate"][
            "result"
        ] != gate_result:
            break
        if materialization_outcome is not None and record["materialization"][
            "outcome"
        ] != materialization_outcome:
            break
        count += 1
    return count

def initial_run_disposition(
    resolved: ResolvedRound, assessment: Assessment
) -> dict[str, Any]:
    result = assessment.round_gate["result"]
    record = resolved.round_record
    if result == "crash_or_sanitizer_candidate":
        return {
            "value": "handoff_crash_analysis",
            "disposition_reason": None,
            "handoff_ref": copy.deepcopy(
                record["evidence"]["candidate_evidence"]["bundle_ref"]
            ),
        }
    if record["execution"]["termination"]["reason"] == "infrastructure_failure":
        return {
            "value": "abort_repeat",
            "disposition_reason": "unrecoverable_infrastructure_failure",
            "handoff_ref": None,
        }
    if record["identity"]["round_index"] == record["schedule"][
        "planned_final_round_index"
    ]:
        return {
            "value": "freeze_adaptation",
            "disposition_reason": "scheduled_rounds_completed",
            "handoff_ref": None,
        }
    if result == "evidence_ineligible":
        limit = resolved.policy["history_rules"][
            "consecutive_evidence_ineligible_before_freeze"
        ]
        count = consecutive_prior_results(
            resolved.prior_decisions, gate_result="evidence_ineligible"
        ) + 1
        if count >= limit:
            return {
                "value": "freeze_adaptation",
                "disposition_reason": "consecutive_evidence_ineligible_limit_reached",
                "handoff_ref": None,
            }
    return {"value": "continue", "disposition_reason": None, "handoff_ref": None}

def not_attempted_materialization() -> dict[str, Any]:
    return {
        "outcome": "not_attempted",
        "candidate_harness_spec_ref": None,
        "candidate_strategy_ref": None,
        "candidate_harness_artifact_ref": None,
        "failed_stage": None,
        "warning_refs": [],
        "failure_diagnostic_refs": [],
    }

def decision_scope(round_record: Mapping[str, Any]) -> dict[str, Any]:
    identity = round_record["identity"]
    return {
        "target_api_id": identity["target_api_id"],
        "experimental_group": identity["experimental_group"],
        "independent_repeat_id": identity["independent_repeat_id"],
        "observed_round_index": identity["round_index"],
        "effective_from_round_index": identity["round_index"] + 1,
    }

def decision_id(scope: Mapping[str, Any]) -> str:
    return (
        f"fd:{scope['target_api_id']}:{scope['independent_repeat_id']}:"
        f"round{scope['observed_round_index']}"
    )

def candidate_directive(
    resolved: ResolvedRound,
    scope: Mapping[str, Any],
) -> dict[str, Any]:
    identity = resolved.harness_spec["identity"]
    repeat_id = scope["independent_repeat_id"]
    expected_id = (
        f"hs_{safe_component(identity['framework'])}_"
        f"{safe_component(identity['target_api'])}_bug_aware_adaptive_"
        f"{safe_component(repeat_id)}"
    )
    if identity["spec_mode"] == "bug_aware_static":
        return {
            "spec_id": expected_id,
            "spec_mode": "bug_aware_adaptive",
            "revision_number": 1,
            "lineage_kind": "derived_from_shared_h0",
        }
    if identity["spec_mode"] != "bug_aware_adaptive" or identity["spec_id"] != expected_id:
        raise RoundInputError("Current Adaptive HarnessSpec identity is outside this repeat")
    return {
        "spec_id": expected_id,
        "spec_mode": "bug_aware_adaptive",
        "revision_number": (
            resolved.harness_spec["revision_information"]["revision_number"] + 1
        ),
        "lineage_kind": "same_identity_revision",
    }


def materialization_request(
    resolved: ResolvedRound,
    budget: Mapping[str, Any],
) -> dict[str, Any]:
    scope = decision_scope(resolved.round_record)
    payload = {
        "request_version": "1.1",
        "request_id": f"mr:{decision_id(scope)}",
        "scope": scope,
        "input_references": copy.deepcopy(resolved.input_references),
        "budget_decision": copy.deepcopy(budget),
        "candidate_directive": candidate_directive(resolved, scope),
        "required_pipeline": [
            "harness_spec_validation",
            "budget_only_diff_validation",
            "strategy_rebinding",
            "strategy_validation",
            "harness_materialization",
            "harness_static_validation",
            "compilation",
            "preflight_execution",
        ],
    }
    payload["request_key"] = canonical_hash(payload)
    return payload

def validate_materialization_result(
    value: Any, request: Mapping[str, Any]
) -> dict[str, Any]:
    result = require_object(value, "Materialization result")
    expected = {"result_version", "request_id", "request_key", "materialization"}
    if set(result) != expected:
        raise RoundInputError(
            f"Materialization result fields must be exactly {sorted(expected)}"
        )
    if result["result_version"] != "1.0":
        raise RoundInputError("Unsupported Materialization result version")
    if result["request_id"] != request["request_id"]:
        raise RoundInputError("Materialization result request_id does not match")
    if result["request_key"] != request["request_key"]:
        raise RoundInputError("Materialization result request_key does not match")
    materialization = require_object(result["materialization"], "materialization")
    outcome = materialization.get("outcome")
    candidate_ref = materialization.get("candidate_harness_spec_ref")
    if outcome == "accepted" or candidate_ref is not None:
        candidate_ref = require_object(
            candidate_ref,
            "materialization.candidate_harness_spec_ref",
        )
        directive = request["candidate_directive"]
        if (
            candidate_ref.get("spec_id") != directive["spec_id"]
            or candidate_ref.get("revision_number") != directive["revision_number"]
        ):
            raise RoundInputError(
                "Materialization result does not identify the requested candidate"
            )
    return copy.deepcopy(materialization)

def rejected_disposition(
    resolved: ResolvedRound, materialization: Mapping[str, Any]
) -> dict[str, Any]:
    if materialization["outcome"] != "rejected":
        return {"value": "continue", "disposition_reason": None, "handoff_ref": None}
    limit = resolved.policy["history_rules"][
        "consecutive_candidate_rejections_before_freeze"
    ]
    count = consecutive_prior_results(
        resolved.prior_decisions, materialization_outcome="rejected"
    ) + 1
    if count >= limit:
        return {
            "value": "freeze_adaptation",
            "disposition_reason": "consecutive_candidate_rejection_limit_reached",
            "handoff_ref": None,
        }
    return {"value": "continue", "disposition_reason": None, "handoff_ref": None}

def assemble_decision(
    resolved: ResolvedRound,
    assessment: Assessment,
    budget: Mapping[str, Any],
    materialization: Mapping[str, Any],
    disposition: Mapping[str, Any],
) -> dict[str, Any]:
    scope = decision_scope(resolved.round_record)
    record = {
        "record_format_version": RECORD_FORMAT_VERSION,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "decision_id": decision_id(scope),
        "decision_key": "0" * 64,
        "scope": scope,
        "input_references": copy.deepcopy(resolved.input_references),
        "round_assessment": {
            "round_gate": copy.deepcopy(assessment.round_gate),
            "branch_diagnoses": list(copy.deepcopy(assessment.branch_diagnoses)),
            "coverage_assessment": copy.deepcopy(assessment.coverage_assessment),
        },
        "budget_decision": copy.deepcopy(budget),
        "materialization": copy.deepcopy(materialization),
        "run_disposition": copy.deepcopy(disposition),
    }
    key_payload = copy.deepcopy(record)
    key_payload.pop("decision_key")
    record["decision_key"] = canonical_hash(key_payload)
    return record

def safe_component(value: str) -> str:
    result = re.sub(r"[^A-Za-z0-9]+", "_", value.strip()).strip("_").lower()
    if not result:
        raise RoundInputError(f"Cannot derive a path component from {value!r}")
    return result

def decision_path(root: Path, scope: Mapping[str, Any]) -> Path:
    return (
        root
        / safe_component(scope["target_api_id"])
        / safe_component(scope["independent_repeat_id"])
        / f"round_{scope['observed_round_index']:03d}"
        / "feedback_decision.json"
    )

def request_path(root: Path, scope: Mapping[str, Any]) -> Path:
    return (
        root
        / safe_component(scope["target_api_id"])
        / safe_component(scope["independent_repeat_id"])
        / f"round_{scope['observed_round_index']:03d}"
        / "materialization_request.json"
    )

def atomic_write_json(path: Path, value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if path.exists():
        existing = load_json(path)
        if existing == value:
            return "reused"
        raise DecisionConflictError(f"Refusing to overwrite immutable artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(encoded, encoding="utf-8", newline="\n")
    try:
        os.link(temporary, path)
    except FileExistsError as exc:
        raise DecisionConflictError(
            f"Concurrent artifact creation detected: {path}"
        ) from exc
    finally:
        temporary.unlink(missing_ok=True)
    return "written"

def publish_result(args: argparse.Namespace, value: Mapping[str, Any]) -> None:
    if args.result_json is not None:
        atomic_write_json(args.result_json, value)
    print(json.dumps(value, ensure_ascii=False, indent=2))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round-record", type=Path, required=True)
    parser.add_argument("--round-schema", type=Path, default=DEFAULT_ROUND_SCHEMA)
    parser.add_argument("--runtime-snapshot", type=Path)
    parser.add_argument("--harness-artifact", type=Path, required=True)
    parser.add_argument("--strategy-plan", type=Path, required=True)
    parser.add_argument("--harness-spec", type=Path, required=True)
    parser.add_argument("--prior-decision", type=Path, action="append", default=[])
    parser.add_argument("--materialization-result", type=Path)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--decision-schema", type=Path, default=DEFAULT_DECISION_SCHEMA)
    parser.add_argument("--harness-spec-schema", type=Path, default=DEFAULT_HARNESS_SPEC_SCHEMA)
    parser.add_argument("--strategy-schema", type=Path, default=DEFAULT_STRATEGY_SCHEMA)
    parser.add_argument(
        "--harness-artifact-schema",
        type=Path,
        default=DEFAULT_HARNESS_ARTIFACT_SCHEMA,
    )
    parser.add_argument("--result-json", type=Path)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--request-root", type=Path, default=DEFAULT_REQUEST_ROOT)
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Evaluate and validate inputs without writing a request or Decision.",
    )
    return parser.parse_args(argv)

def run(args: argparse.Namespace) -> int:
    resolved = resolve_inputs(args)
    assessment = assess_round(resolved)
    budget = decide_budget(resolved, assessment)
    scope = decision_scope(resolved.round_record)

    if budget["budget_action"] == "reallocate_budget":
        request = materialization_request(resolved, budget)
        if args.materialization_result is None:
            if args.validate_only:
                print(json.dumps(request, ensure_ascii=False, indent=2))
                return 0
            path = request_path(args.request_root, scope)
            status = atomic_write_json(path, request)
            publish_result(
                args,
                {
                    "status": "materialization_required",
                    "write_status": status,
                    "request_path": str(path),
                    "request_key": request["request_key"],
                },
            )
            return 3
        materialization = validate_materialization_result(
            load_json(args.materialization_result), request
        )
        disposition = rejected_disposition(resolved, materialization)
    else:
        if args.materialization_result is not None:
            raise RoundInputError(
                "materialization_result is forbidden when budget is unchanged"
            )
        materialization = not_attempted_materialization()
        disposition = initial_run_disposition(resolved, assessment)

    decision = assemble_decision(
        resolved,
        assessment,
        budget,
        materialization,
        disposition,
    )
    validator = schema_validator(args.decision_schema, "Feedback Decision")
    validate_against(
        decision,
        validator,
        "Feedback Decision",
        error_type=DecisionConflictError,
    )
    if args.validate_only:
        print(json.dumps(decision, ensure_ascii=False, indent=2))
        return 0
    output = decision_path(args.output_root, scope)
    status = atomic_write_json(output, decision)
    publish_result(
        args,
        {
            "status": "decision_recorded",
            "write_status": status,
            "decision_path": str(output),
            "decision_id": decision["decision_id"],
            "decision_key": decision["decision_key"],
            "round_gate": decision["round_assessment"]["round_gate"]["result"],
            "budget_action": decision["budget_decision"]["budget_action"],
            "materialization_outcome": decision["materialization"]["outcome"],
            "run_disposition": decision["run_disposition"]["value"],
        },
    )
    return 0

def main(argv: Sequence[str] | None = None) -> int:
    try:
        return run(parse_args(argv))
    except GlobalInputError as exc:
        print(f"Global input error: {exc}", file=sys.stderr)
        return 2
    except (RoundInputError, DecisionConflictError) as exc:
        print(f"Round processing error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
