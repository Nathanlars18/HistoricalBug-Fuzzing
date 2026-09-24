#!/usr/bin/env python3
"""Deterministically compute EXP014 run-, API-, and RQ-level results.

The analyzer consumes only frozen experiment artifacts. It does not execute
fuzzing, classify crashes, repair records, call an LLM, or mutate upstream
artifacts. Missing or invalid evidence is reported as unavailable, never zero.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

from jsonschema import Draft202012Validator, FormatChecker


ANALYZER_ID = "analyze_experiment_results"
ANALYZER_VERSION = "0.3.0"
MATRIX_FORMAT_VERSION = "0.4"
TARGET_MANIFEST_FORMAT_VERSION = "1.0"
GROUPS = (
    "structured_baseline",
    "bug_aware_static",
    "bug_aware_adaptive",
)
COMPLETED_TASK_STATUSES = {"completed", "completed_with_abnormal_events"}
TARGET_OUTCOME_EVENT_KINDS = (
    "activation_checked",
    "activation_true",
    "activation_unevaluable",
    "activation_check_error",
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
EXP_ROOT = REPOSITORY_ROOT / "experiment" / "EXP014_experimental_evaluation"
DEFAULT_MATRIX = EXP_ROOT / "configs" / "experiment_matrix.json"
DEFAULT_TARGET_MANIFEST = EXP_ROOT / "configs" / "evaluation_target_manifest.json"
DEFAULT_RUN_ROOT = EXP_ROOT / "runs"
DEFAULT_CASE_ROOT = (
    REPOSITORY_ROOT
    / "experiment"
    / "EXP013_crash_triage_and_result_analysis"
    / "results"
    / "cases"
)
DEFAULT_OUTPUT_ROOT = EXP_ROOT / "results"
ROUND_SCHEMA = (
    REPOSITORY_ROOT
    / "experiment"
    / "EXP012_adaptive_feedback"
    / "schemas"
    / "fuzzing_round_record.schema.json"
)
ARTIFACT_SCHEMA = (
    REPOSITORY_ROOT
    / "experiment"
    / "EXP011_bug_aware_harness_synthesis"
    / "schemas"
    / "harness_artifact_record.schema.json"
)
CASE_SCHEMA = (
    REPOSITORY_ROOT
    / "experiment"
    / "EXP013_crash_triage_and_result_analysis"
    / "schemas"
    / "crash_case_record.schema.json"
)
ANALYSIS_SCHEMA_NAMES = (
    "evaluation_target_manifest",
    "execution_index",
    "result_provenance",
    "runtime_snapshot",
)


class AnalysisError(RuntimeError):
    pass


class InputError(AnalysisError):
    pass


class ImmutableConflict(AnalysisError):
    pass


@dataclass(frozen=True)
class RoundResult:
    round_id: str
    api_id: str
    group_id: str
    repeat_id: str
    round_index: int
    target_states: Mapping[str, str]
    target_counts: Mapping[str, Mapping[str, int]]
    artifact_path: str
    round_record_path: str
    snapshot_path: str | None


def no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream, object_pairs_hook=no_duplicate_keys)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise InputError(f"Cannot read JSON {path}: {exc}") from exc


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
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise InputError(f"Cannot hash {path}: {exc}") from exc
    return digest.hexdigest()


def parse_utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise InputError(f"{label} must be a UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InputError(f"Invalid timestamp for {label}: {value!r}") from exc
    return parsed.astimezone(timezone.utc)


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InputError(f"{label} must be an object")
    return value


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{label} must be a non-empty string")
    return value


def repository_path(value: str | Path, label: str) -> Path:
    path = Path(value)
    resolved = (path if path.is_absolute() else REPOSITORY_ROOT / path).resolve()
    if not resolved.is_relative_to(REPOSITORY_ROOT):
        raise InputError(f"{label} escapes the repository: {value}")
    return resolved


def schema_validator(path: Path) -> Draft202012Validator:
    schema = require_object(load_json(path), f"Schema {path}")
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate_record(
    record: Any,
    validator: Draft202012Validator,
    label: str,
) -> dict[str, Any]:
    value = require_object(record, label)
    errors = sorted(validator.iter_errors(value), key=lambda item: item.json_path)
    if errors:
        first = errors[0]
        raise InputError(f"{label} violates its Schema at {first.json_path}: {first.message}")
    return value


def verify_file_reference(reference: Any, label: str) -> Path:
    value = require_object(reference, label)
    path = repository_path(require_string(value.get("relative_path"), label), label)
    declared = require_string(value.get("content_hash"), f"{label}.content_hash")
    actual = file_hash(path)
    if actual != declared:
        raise InputError(f"{label} hash mismatch: {actual} != {declared}")
    return path


def walk_file_references(value: Any, label: str = "matrix") -> Iterable[tuple[Any, str]]:
    if isinstance(value, dict):
        if {"relative_path", "content_hash"} <= set(value):
            yield value, label
            return
        for key, item in value.items():
            yield from walk_file_references(item, f"{label}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk_file_references(item, f"{label}[{index}]")


def analysis_schema_paths(matrix: Mapping[str, Any]) -> dict[str, Path]:
    analysis = require_object(matrix.get("analysis"), "matrix.analysis")
    references = require_object(
        analysis.get("input_schema_file_refs"),
        "matrix.analysis.input_schema_file_refs",
    )
    if set(references) != set(ANALYSIS_SCHEMA_NAMES):
        raise InputError(
            "matrix.analysis.input_schema_file_refs must contain exactly "
            f"{list(ANALYSIS_SCHEMA_NAMES)}"
        )
    return {
        name: verify_file_reference(references[name], f"analysis schema {name}")
        for name in ANALYSIS_SCHEMA_NAMES
    }


def matrix_api_ids(matrix: Mapping[str, Any]) -> list[str]:
    entries = matrix.get("api_entries")
    if not isinstance(entries, list) or not entries:
        raise InputError("matrix.api_entries must be a non-empty frozen list")
    ids = []
    for index, raw_entry in enumerate(entries):
        entry = require_object(raw_entry, f"api_entries[{index}]")
        enabled = entry.get("enabled", True)
        if not isinstance(enabled, bool):
            raise InputError(f"api_entries[{index}].enabled must be Boolean")
        if enabled:
            ids.append(require_string(entry.get("api_id"), f"api_entries[{index}].api_id"))
    if not ids:
        raise InputError("matrix.api_entries has no enabled API")
    if len(ids) != len(set(ids)):
        raise InputError("enabled matrix.api_entries contains duplicate api_id values")
    return ids


def expected_task_keys(
    matrix: Mapping[str, Any],
    api_ids: Sequence[str],
) -> set[str]:
    repeat_count = matrix["execution"]["repeat_count"]
    round_count = matrix["execution"]["round_count"]
    return {
        ":".join((api_id, group_id, f"repeat_{repeat_index:03d}", f"round_{round_index:03d}"))
        for api_id in api_ids
        for group_id in GROUPS
        for repeat_index in range(1, repeat_count + 1)
        for round_index in range(1, round_count + 1)
    }


def target_sets(manifest: Mapping[str, Any], api_ids: Sequence[str]) -> dict[str, tuple[str, ...]]:
    if manifest.get("format_version") != TARGET_MANIFEST_FORMAT_VERSION:
        raise InputError("Unsupported Evaluation Target Manifest format")
    if manifest.get("status") != "frozen":
        raise InputError("Evaluation Target Manifest is not frozen")
    if manifest.get("unresolved_bindings") not in (None, []):
        raise InputError("Evaluation Target Manifest has unresolved bindings")
    sets = manifest.get("api_target_sets")
    if not isinstance(sets, list) or not sets:
        raise InputError("Evaluation Target Manifest has no api_target_sets")
    result: dict[str, tuple[str, ...]] = {}
    for index, item in enumerate(sets):
        item = require_object(item, f"api_target_sets[{index}]")
        api_id = require_string(item.get("api_id"), f"api_target_sets[{index}].api_id")
        targets = item.get("targets")
        if not isinstance(targets, list) or not targets:
            raise InputError(f"Evaluation Target set for {api_id} is empty")
        identifiers = tuple(
            require_string(
                require_object(target, f"{api_id}.targets[]").get("evaluation_target_id"),
                f"{api_id}.targets[].evaluation_target_id",
            )
            for target in targets
        )
        if len(identifiers) != len(set(identifiers)):
            raise InputError(f"Evaluation Target set for {api_id} contains duplicates")
        if api_id in result:
            raise InputError(f"Duplicate Evaluation Target set for {api_id}")
        result[api_id] = tuple(sorted(identifiers))
    if set(result) != set(api_ids):
        raise InputError("Evaluation Target Manifest API set differs from matrix.api_entries")
    return result


def artifact_reference_key(reference: Mapping[str, Any]) -> tuple[str, str]:
    return (
        require_string(reference.get("artifact_id"), "artifact_ref.artifact_id"),
        require_string(reference.get("content_hash"), "artifact_ref.content_hash"),
    )


def artifact_candidates(state: Mapping[str, Any], run_root: Path) -> list[Path]:
    paths: set[Path] = set()
    for api_state in state.get("preparation", {}).values():
        if not isinstance(api_state, dict):
            continue
        for group_state in api_state.values():
            if isinstance(group_state, dict) and isinstance(group_state.get("artifact_path"), str):
                paths.add(repository_path(group_state["artifact_path"], "prepared artifact"))
    for api_state in state.get("adaptive_current", {}).values():
        if not isinstance(api_state, dict):
            continue
        for repeat_state in api_state.values():
            if isinstance(repeat_state, dict) and isinstance(repeat_state.get("artifact_path"), str):
                paths.add(repository_path(repeat_state["artifact_path"], "adaptive artifact"))
    if run_root.is_dir():
        for path in run_root.rglob("*.json"):
            try:
                value = load_json(path)
            except InputError:
                continue
            if isinstance(value, dict) and value.get("record_type") == "harness_artifact":
                paths.add(path.resolve())
    return sorted(paths, key=lambda item: item.as_posix())


def referenced_artifact_keys(
    state: Mapping[str, Any],
    round_validator: Draft202012Validator,
) -> set[tuple[str, str]]:
    result: set[tuple[str, str]] = set()
    for task_key, raw_task in require_object(state.get("tasks"), "execution_index.tasks").items():
        task = require_object(raw_task, f"task {task_key}")
        if task.get("status") not in COMPLETED_TASK_STATUSES:
            continue
        round_path = repository_path(
            require_string(task.get("round_record_path"), f"{task_key}.round_record_path"),
            "Fuzzing Round record",
        )
        record = validate_record(load_json(round_path), round_validator, f"Round {round_path}")
        result.add(artifact_reference_key(record["source_context"]["harness_artifact_ref"]))
    return result


def artifact_index(
    state: Mapping[str, Any],
    run_root: Path,
    validator: Draft202012Validator,
    required_keys: set[tuple[str, str]],
) -> dict[tuple[str, str], tuple[dict[str, Any], Path]]:
    result: dict[tuple[str, str], tuple[dict[str, Any], Path]] = {}
    for path in artifact_candidates(state, run_root):
        raw_record = load_json(path)
        if not isinstance(raw_record, dict) or raw_record.get("record_type") != "harness_artifact":
            continue
        identity = raw_record.get("identity")
        if not isinstance(identity, dict) or not isinstance(identity.get("harness_artifact_id"), str):
            continue
        key = (identity["harness_artifact_id"], canonical_hash(raw_record))
        if key not in required_keys:
            continue
        record = validate_record(raw_record, validator, f"Harness Artifact {path}")
        previous = result.get(key)
        if previous is not None:
            if previous[0] != record:
                raise InputError(f"Conflicting Harness Artifact records for {key[0]}")
            continue
        result[key] = (record, path)
    missing = sorted(required_keys - set(result))
    if missing:
        raise InputError(f"Referenced Harness Artifact records were not found: {missing[:5]}")
    return result


def trace_ids(event: Mapping[str, Any], ref_type: str) -> list[str]:
    return [ref["ref_id"] for ref in event["trace_refs"] if ref["ref_type"] == ref_type]


def artifact_target_ids(artifact: Mapping[str, Any]) -> set[str]:
    return {
        target_id
        for event in artifact["instrumentation_map"]
        if event["event_kind"] in TARGET_OUTCOME_EVENT_KINDS
        for target_id in trace_ids(event, "evaluation_target")
    }


def snapshot_is_valid(snapshot: Mapping[str, Any], artifact: Mapping[str, Any]) -> bool:
    site_counts = snapshot.get("site_counts")
    expected_count = len(artifact["instrumentation_map"])
    return (
        snapshot.get("artifact_id") == artifact["identity"]["harness_artifact_id"]
        and snapshot.get("generation_key") == artifact["identity"]["generation_key"]
        and snapshot.get("site_count") == expected_count
        and isinstance(site_counts, list)
        and len(site_counts) == expected_count
        and all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in site_counts)
        and snapshot.get("invalid_site_records") == 0
        and snapshot.get("export_failures") == 0
    )


def resolve_target_states(
    artifact: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    expected_targets: Sequence[str],
) -> tuple[dict[str, str], dict[str, dict[str, int]]]:
    expected = set(expected_targets)
    observed = artifact_target_ids(artifact)
    if observed - expected:
        raise InputError(f"Artifact references unknown Evaluation Targets: {sorted(observed - expected)}")
    states: dict[str, str] = {}
    counts: dict[str, dict[str, int]] = {}
    globally_valid = snapshot_is_valid(snapshot, artifact)
    site_counts = snapshot.get("site_counts", [])
    events_by_target: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for event in artifact["instrumentation_map"]:
        if event["event_kind"] not in TARGET_OUTCOME_EVENT_KINDS:
            continue
        for target_id in trace_ids(event, "evaluation_target"):
            events_by_target[target_id].append(event)
    for target_id in expected_targets:
        total = {kind: 0 for kind in TARGET_OUTCOME_EVENT_KINDS}
        events = events_by_target.get(target_id, [])
        branches: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for event in events:
            branches[event["branch_id"]].append(event)
        structure_valid = bool(branches)
        for branch_events in branches.values():
            for kind in TARGET_OUTCOME_EVENT_KINDS:
                matching = [event for event in branch_events if event["event_kind"] == kind]
                if len(matching) != 1:
                    structure_valid = False
                    continue
                site_id = matching[0]["runtime_site_id"]
                if not isinstance(site_id, int) or site_id < 0 or site_id >= len(site_counts):
                    structure_valid = False
                    continue
                total[kind] += site_counts[site_id]
        if total["activation_true"] > total["activation_checked"]:
            structure_valid = False
        counts[target_id] = total
        if not globally_valid or not structure_valid:
            states[target_id] = "instrumentation_error"
        elif total["activation_checked"] > 0:
            states[target_id] = (
                "checked_true" if total["activation_true"] > 0 else "checked_false"
            )
        elif total["activation_unevaluable"] > 0:
            states[target_id] = "unevaluable"
        elif total["activation_check_error"] > 0:
            states[target_id] = "instrumentation_error"
        else:
            states[target_id] = "not_checked"
    return states, counts


def verify_snapshot_location(round_record: Mapping[str, Any], path: Path) -> None:
    evidence = round_record["evidence"]["runtime_snapshot"]
    if evidence["status"] != "present":
        raise InputError("Completed Round has no runtime snapshot")
    file_ref = evidence["location"]["file_ref"]
    declared_path = repository_path(file_ref["relative_path"], "runtime snapshot")
    if declared_path != path.resolve() or file_hash(path) != file_ref["content_hash"]:
        raise InputError("Runtime snapshot path or hash differs from Fuzzing Round record")


def load_rounds(
    matrix: Mapping[str, Any],
    state: Mapping[str, Any],
    targets: Mapping[str, Sequence[str]],
    artifacts: Mapping[tuple[str, str], tuple[dict[str, Any], Path]],
    round_validator: Draft202012Validator,
    snapshot_validator: Draft202012Validator,
) -> tuple[list[RoundResult], list[dict[str, Any]]]:
    results: list[RoundResult] = []
    attrition: list[dict[str, Any]] = []
    tasks = require_object(state.get("tasks"), "execution_index.tasks")
    expected = expected_task_keys(matrix, tuple(targets))
    unexpected = sorted(set(tasks) - expected)
    if unexpected:
        raise InputError(f"Execution Index contains unexpected task keys: {unexpected[:5]}")
    for task_key in sorted(expected - set(tasks)):
        attrition.append({"task_key": task_key, "status": "missing_task"})
    for task_key, task in sorted(tasks.items()):
        task = require_object(task, f"task {task_key}")
        status = task.get("status")
        if status not in COMPLETED_TASK_STATUSES:
            attrition.append({"task_key": task_key, "status": status})
            continue
        round_path = repository_path(
            require_string(task.get("round_record_path"), f"{task_key}.round_record_path"),
            "Fuzzing Round record",
        )
        record = validate_record(load_json(round_path), round_validator, f"Round {round_path}")
        if record["validation"]["validation_status"] != "passed":
            raise InputError(f"Fuzzing Round validation failed: {round_path}")
        if record["attempt_selection"]["status"] != "selected_as_round_result":
            raise InputError(f"Task points to a non-selected Round record: {round_path}")
        identity = record["identity"]
        api_id = identity["target_api_id"]
        expected_task_key = ":".join(
            (
                api_id,
                identity["experimental_group"],
                identity["independent_repeat_id"],
                f"round_{identity['round_index']:03d}",
            )
        )
        if expected_task_key != task_key:
            raise InputError(
                f"Round identity does not match execution task {task_key}: "
                f"{expected_task_key}"
            )
        if identity["experimental_group"] not in GROUPS:
            raise InputError(f"Round uses an unknown experimental group: {round_path}")
        if api_id not in targets:
            raise InputError(f"Round references API outside frozen target set: {api_id}")
        artifact_ref = record["source_context"]["harness_artifact_ref"]
        key = artifact_reference_key(artifact_ref)
        if key not in artifacts:
            raise InputError(f"Harness Artifact for Round {identity['round_id']} was not found")
        artifact, artifact_path = artifacts[key]
        snapshot_value = task.get("runtime_snapshot_path")
        if record["evidence"]["runtime_snapshot"]["status"] == "missing":
            if snapshot_value is not None:
                raise InputError(f"{task_key} declares a snapshot path for missing evidence")
            snapshot_path = None
            states = {target_id: "instrumentation_error" for target_id in targets[api_id]}
            counts = {
                target_id: {kind: 0 for kind in TARGET_OUTCOME_EVENT_KINDS}
                for target_id in targets[api_id]
            }
        else:
            snapshot_path = repository_path(
                require_string(snapshot_value, f"{task_key}.runtime_snapshot_path"),
                "runtime snapshot",
            )
            verify_snapshot_location(record, snapshot_path)
            snapshot = validate_record(
                load_json(snapshot_path),
                snapshot_validator,
                f"Runtime Snapshot {snapshot_path}",
            )
            states, counts = resolve_target_states(artifact, snapshot, targets[api_id])
        results.append(
            RoundResult(
                round_id=identity["round_id"],
                api_id=api_id,
                group_id=identity["experimental_group"],
                repeat_id=identity["independent_repeat_id"],
                round_index=identity["round_index"],
                target_states=states,
                target_counts=counts,
                artifact_path=str(artifact_path),
                round_record_path=str(round_path),
                snapshot_path=None if snapshot_path is None else str(snapshot_path),
            )
        )
    return results, attrition


def coverage_diagnostics(
    rounds: Sequence[RoundResult], matrix: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Verify replay artifacts and report C++ coverage separately from RQ metrics."""
    enabled = matrix["coverage"]["enabled"]
    scope_hash = (
        file_hash(verify_file_reference(matrix["coverage"]["scope_file_ref"], "coverage scope"))
        if enabled else None
    )
    rows: list[dict[str, Any]] = []
    for item in rounds:
        record = load_json(Path(item.round_record_path))
        evidence = record["evidence"]["coverage_summary"]
        status = evidence["status"]
        if enabled and status == "not_collected":
            raise InputError(f"Enabled coverage was not attempted for {item.round_id}")
        row: dict[str, Any] = {
            "api_id": item.api_id,
            "group_id": item.group_id,
            "repeat_id": item.repeat_id,
            "round_index": item.round_index,
            "status": status,
            "quality_status": None,
            "source_file_count": None,
            "corpus_file_count": None,
            "lines_covered": None,
            "lines_total": None,
            "branches_covered": None,
            "branches_total": None,
            "warning_count": None,
        }
        if status == "present":
            location = require_object(evidence["location"], "coverage location")
            path = verify_file_reference(location["file_ref"], "coverage summary")
            if location["artifact_ref"]["content_hash"] != file_hash(path):
                raise InputError(f"Coverage Artifact hash differs from summary: {path}")
            summary = require_object(load_json(path), "coverage summary")
            if enabled and summary.get("scope_hash") != scope_hash:
                raise InputError(f"Coverage scope differs from frozen matrix: {path}")
            profile_path = path.with_name("coverage.profdata")
            if file_hash(profile_path) != summary.get("profile_hash"):
                raise InputError(f"Coverage profile hash differs from summary: {profile_path}")
            measures = require_object(summary.get("measurements"), "coverage measurements")
            row.update({
                "quality_status": summary.get("quality_status"),
                "source_file_count": summary.get("source_file_count"),
                "corpus_file_count": summary.get("corpus_file_count"),
                "lines_covered": measures["lines"]["covered"],
                "lines_total": measures["lines"]["total"],
                "branches_covered": measures["branches"]["covered"],
                "branches_total": measures["branches"]["total"],
                "warning_count": len(summary.get("warnings", [])),
            })
        rows.append(row)
    return rows


def latest_cases_at_cutoff(
    case_root: Path,
    cutoff: datetime,
    validator: Draft202012Validator,
) -> list[dict[str, Any]]:
    if not case_root.is_dir():
        return []
    selected: list[dict[str, Any]] = []
    for case_dir in sorted((path for path in case_root.iterdir() if path.is_dir()), key=lambda p: p.name):
        candidates: list[tuple[datetime, int, dict[str, Any]]] = []
        for path in sorted((case_dir / "records").glob("*.json")):
            record = validate_record(load_json(path), validator, f"Crash Case {path}")
            created = parse_utc(record["revision"]["created_at"], f"{path}.revision.created_at")
            if created <= cutoff:
                candidates.append((created, record["revision"]["revision_number"], record))
        if candidates:
            candidates.sort(key=lambda item: (item[0], item[1]))
            selected.append(candidates[-1][2])
    return selected


def relevant_cases(
    cases: Sequence[Mapping[str, Any]],
    rounds: Sequence[RoundResult],
) -> list[Mapping[str, Any]]:
    selected_round_ids = {item.round_id for item in rounds}
    direct = [
        case
        for case in cases
        if case["origin"]["fuzzing_round_ref"]["artifact_id"] in selected_round_ids
    ]
    relevant_cluster_ids = {
        case["deduplication"]["cluster_id"]
        for case in direct
        if case["deduplication"]["cluster_id"] is not None
    }
    return [
        case
        for case in cases
        if (
            case["origin"]["fuzzing_round_ref"]["artifact_id"] in selected_round_ids
            or case["deduplication"]["cluster_id"] in relevant_cluster_ids
        )
    ]


def validate_candidate_case_coverage(
    rounds: Sequence[RoundResult],
    cases: Sequence[Mapping[str, Any]],
) -> None:
    """Refuse to treat untriaged abnormal candidates as zero anomalies."""
    expected: set[tuple[str, str]] = set()
    for round_result in rounds:
        record = require_object(
            load_json(Path(round_result.round_record_path)),
            f"Round {round_result.round_record_path}",
        )
        evidence = require_object(record["evidence"], "Round evidence")
        candidate_evidence = require_object(
            evidence["candidate_evidence"], "Round candidate evidence"
        )
        if candidate_evidence["status"] == "present":
            for observation in candidate_evidence["observations"]:
                expected.add((round_result.round_id, observation["candidate_id"]))

    materialized = {
        (
            case["origin"]["fuzzing_round_ref"]["artifact_id"],
            case["origin"]["candidate_observation_id"],
        )
        for case in cases
    }
    missing = sorted(expected - materialized)
    if missing:
        preview = ", ".join(
            f"{round_id}/{candidate_id}" for round_id, candidate_id in missing[:5]
        )
        suffix = "" if len(missing) <= 5 else f" (and {len(missing) - 5} more)"
        raise InputError(
            "Crash analysis is incomplete at the analysis cutoff; missing Crash Case "
            f"records for {preview}{suffix}"
        )


def anomaly_occurrences(
    cases: Sequence[Mapping[str, Any]],
    rounds: Sequence[RoundResult],
) -> tuple[dict[tuple[str, str, str], dict[str, int]], int]:
    round_lookup = {item.round_id: item for item in rounds}
    selected_round_ids = set(round_lookup)
    by_cluster: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    relevant_cluster_ids: set[str] = set()
    unresolved = 0
    for case in cases:
        cluster_id = case["deduplication"]["cluster_id"]
        round_id = case["origin"]["fuzzing_round_ref"]["artifact_id"]
        if cluster_id is None:
            if round_id in selected_round_ids:
                unresolved += 1
            continue
        by_cluster[cluster_id].append(case)
        if round_id in selected_round_ids:
            relevant_cluster_ids.add(cluster_id)

    occurrences: dict[tuple[str, str, str], dict[str, int]] = defaultdict(dict)
    for cluster_id in sorted(relevant_cluster_ids):
        members = by_cluster[cluster_id]
        representatives = [
            item for item in members
            if item["deduplication"]["case_role"] == "representative"
        ]
        if len(representatives) != 1:
            unresolved += 1
            continue
        representative = representatives[0]
        if not (
            representative["reproduction"]["status"] == "stable"
            and representative["fault_attribution"]["status"] == "framework"
        ):
            continue
        for case in members:
            round_ref = case["origin"]["fuzzing_round_ref"]
            round_id = round_ref["artifact_id"]
            round_result = round_lookup.get(round_id)
            if round_result is None:
                continue
            if round_ref["content_hash"] != file_hash(Path(round_result.round_record_path)):
                raise InputError(
                    f"Crash Case round reference hash mismatch for {round_id}"
                )
            run_key = (
                round_result.api_id,
                round_result.group_id,
                round_result.repeat_id,
            )
            current = occurrences[run_key].get(cluster_id)
            occurrences[run_key][cluster_id] = (
                round_result.round_index
                if current is None
                else min(current, round_result.round_index)
            )
    return occurrences, unresolved


def run_metrics(
    matrix: Mapping[str, Any],
    targets: Mapping[str, Sequence[str]],
    rounds: Sequence[RoundResult],
    anomalies: Mapping[tuple[str, str, str], Mapping[str, int]],
) -> list[dict[str, Any]]:
    round_count = matrix["execution"]["round_count"]
    grouped: dict[tuple[str, str, str], list[RoundResult]] = defaultdict(list)
    for item in rounds:
        grouped[(item.api_id, item.group_id, item.repeat_id)].append(item)
    rows: list[dict[str, Any]] = []
    repeats = [
        f"repeat_{index:03d}"
        for index in range(1, matrix["execution"]["repeat_count"] + 1)
    ]
    for api_id in targets:
        denominator = len(targets[api_id])
        for group_id in GROUPS:
            for repeat_id in repeats:
                key = (api_id, group_id, repeat_id)
                items = sorted(grouped.get(key, []), key=lambda item: item.round_index)
                complete = [item.round_index for item in items] == list(range(1, round_count + 1))
                activated: set[str] = set()
                round_activation: dict[str, float] = {}
                for item in items:
                    activated.update(
                        target_id
                        for target_id, state in item.target_states.items()
                        if state == "checked_true"
                    )
                    round_activation[str(item.round_index)] = len(activated) / denominator
                cluster_rounds = anomalies.get(key, {})
                rows.append(
                    {
                        "api_id": api_id,
                        "group_id": group_id,
                        "repeat_id": repeat_id,
                        "completed": complete,
                        "completion_status": "complete" if complete else "incomplete",
                        "completed_round_count": len(items),
                        "target_count": denominator,
                        "activated_target_count": len(activated) if complete else None,
                        "target_activation_coverage": len(activated) / denominator if complete else None,
                        "cumulative_activation_by_round": round_activation,
                        "reproducible_anomaly_yield": len(cluster_rounds) if complete else None,
                        "post_feedback_anomaly_yield": (
                            sum(index >= 2 for index in cluster_rounds.values()) if complete else None
                        ),
                        "cluster_first_round": dict(sorted(cluster_rounds.items())),
                    }
                )
    return rows


def preparation_metric(
    state: Mapping[str, Any],
    api_id: str,
    expected_targets: Sequence[str],
    artifact_validator: Draft202012Validator,
) -> tuple[bool, str | None]:
    prepared = state.get("preparation", {}).get(api_id, {}).get("bug_aware_static")
    if not isinstance(prepared, dict) or prepared.get("status") != "success":
        return False, "static_preparation_failed_or_missing"
    if prepared.get("preflight", {}).get("status") != "passed":
        return False, "preflight_not_passed"
    path = repository_path(require_string(prepared.get("artifact_path"), "artifact_path"), "artifact")
    artifact = validate_record(load_json(path), artifact_validator, f"Harness Artifact {path}")
    validation = artifact["validation"]
    if validation["static_validation"]["status"] != "passed":
        return False, "artifact_static_validation_failed"
    if validation["compile_check"]["status"] != "passed":
        return False, "artifact_compile_failed"
    if set(expected_targets) != artifact_target_ids(artifact):
        return False, "evaluation_target_checker_set_mismatch"
    return True, None


def wilson_interval(successes: int, total: int) -> list[float] | None:
    if total == 0:
        return None
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


def round_artifact_reference(item: RoundResult) -> Mapping[str, Any]:
    record = require_object(load_json(Path(item.round_record_path)), "Fuzzing Round")
    return require_object(
        record["source_context"]["harness_artifact_ref"],
        "Fuzzing Round harness_artifact_ref",
    )


def validate_pairing(rounds: Sequence[RoundResult]) -> None:
    grouped = {
        (item.api_id, item.group_id, item.repeat_id, item.round_index): item
        for item in rounds
    }
    if len(grouped) != len(rounds):
        raise InputError("Duplicate completed Round identity")
    units = sorted({(item.api_id, item.repeat_id, item.round_index) for item in rounds})
    for api_id, repeat_id, round_index in units:
        present = [
            grouped.get((api_id, group_id, repeat_id, round_index))
            for group_id in GROUPS
        ]
        available = [item for item in present if item is not None]
        if len(available) > 1:
            seeds = {
                load_json(Path(item.round_record_path))["execution"]["seed"]
                for item in available
            }
            if len(seeds) != 1:
                raise InputError(
                    f"Paired seed mismatch for {api_id}/{repeat_id}/round {round_index}"
                )
        if round_index == 1:
            static = grouped.get((api_id, "bug_aware_static", repeat_id, 1))
            adaptive = grouped.get((api_id, "bug_aware_adaptive", repeat_id, 1))
            if static is not None and adaptive is not None:
                if round_artifact_reference(static) != round_artifact_reference(adaptive):
                    raise InputError(
                        f"Static and Adaptive H0 differ for {api_id}/{repeat_id}"
                    )

    for api_id in sorted({item.api_id for item in rounds}):
        for group_id in ("structured_baseline", "bug_aware_static"):
            group_rounds = [
                item for item in rounds
                if item.api_id == api_id and item.group_id == group_id
            ]
            artifact_refs = {
                canonical_hash(round_artifact_reference(item))
                for item in group_rounds
            }
            if len(artifact_refs) > 1:
                raise InputError(
                    f"{group_id} Harness changed across rounds/repeats for {api_id}"
                )


def validate_adaptive_lineage(
    rounds: Sequence[RoundResult],
    state: Mapping[str, Any],
) -> None:
    grouped: dict[tuple[str, str], list[RoundResult]] = defaultdict(list)
    for item in rounds:
        if item.group_id == "bug_aware_adaptive":
            grouped[(item.api_id, item.repeat_id)].append(item)

    feedback = state.get("feedback", {})
    for (api_id, repeat_id), items in grouped.items():
        ordered = sorted(items, key=lambda item: item.round_index)
        repeat_state = (
            feedback.get(api_id, {}).get(repeat_id, {})
            if isinstance(feedback, dict)
            else {}
        )
        for previous, current in zip(ordered, ordered[1:]):
            if current.round_index != previous.round_index + 1:
                continue
            previous_ref = round_artifact_reference(previous)
            current_ref = round_artifact_reference(current)
            changed = previous_ref != current_ref
            decision_key = f"round_{previous.round_index:03d}"
            decision = repeat_state.get(decision_key) if isinstance(repeat_state, dict) else None
            if not isinstance(decision, dict):
                if changed:
                    raise InputError(
                        f"Adaptive Harness changed without a prior feedback decision for "
                        f"{api_id}/{repeat_id}/{decision_key}"
                    )
                continue
            if changed and decision.get("materialization_outcome") != "accepted":
                raise InputError(
                    f"Adaptive Harness changed after a non-accepted decision for "
                    f"{api_id}/{repeat_id}/{decision_key}"
                )
            if changed:
                stage = decision.get("harness_artifact")
                if not isinstance(stage, dict) or not isinstance(stage.get("output_path"), str):
                    raise InputError(
                        f"Accepted adaptive decision lacks Harness Artifact output for "
                        f"{api_id}/{repeat_id}/{decision_key}"
                    )
                artifact = require_object(
                    load_json(repository_path(stage["output_path"], "adaptive Harness Artifact")),
                    "adaptive Harness Artifact",
                )
                expected_ref = {
                    "artifact_id": artifact["identity"]["harness_artifact_id"],
                    "artifact_version": artifact["schema_version"],
                    "content_hash": canonical_hash(artifact),
                }
                if expected_ref != current_ref:
                    raise InputError(
                        f"Adaptive Round does not use the accepted Harness Artifact for "
                        f"{api_id}/{repeat_id}/{decision_key}"
                    )


def paired_metrics(
    rows: Sequence[Mapping[str, Any]],
    final_round: int,
) -> list[dict[str, Any]]:
    lookup = {(row["api_id"], row["group_id"], row["repeat_id"]): row for row in rows}
    pairs: list[dict[str, Any]] = []
    units = sorted({(row["api_id"], row["repeat_id"]) for row in rows})
    for api_id, repeat_id in units:
        baseline = lookup.get((api_id, "structured_baseline", repeat_id))
        static = lookup.get((api_id, "bug_aware_static", repeat_id))
        adaptive = lookup.get((api_id, "bug_aware_adaptive", repeat_id))
        rq2_ok = bool(baseline and static and baseline["completed"] and static["completed"])
        rq3_ok = bool(static and adaptive and static["completed"] and adaptive["completed"])
        row: dict[str, Any] = {
            "api_id": api_id,
            "repeat_id": repeat_id,
            "rq2_pair_complete": rq2_ok,
            "rq3_pair_complete": rq3_ok,
            "rq2_activation_difference": None,
            "rq2_anomaly_yield_difference": None,
            "rq3_adaptive_activation_gain": None,
            "rq3_post_feedback_anomaly_gain": None,
        }
        if rq2_ok:
            row["rq2_activation_difference"] = (
                static["target_activation_coverage"] - baseline["target_activation_coverage"]
            )
            row["rq2_anomaly_yield_difference"] = (
                static["reproducible_anomaly_yield"] - baseline["reproducible_anomaly_yield"]
            )
        if rq3_ok:
            static_curve = static["cumulative_activation_by_round"]
            adaptive_curve = adaptive["cumulative_activation_by_round"]
            final_key = str(final_round)
            if "1" not in static_curve or final_key not in static_curve:
                raise InputError(f"Static activation curve is incomplete for {api_id}/{repeat_id}")
            if "1" not in adaptive_curve or final_key not in adaptive_curve:
                raise InputError(f"Adaptive activation curve is incomplete for {api_id}/{repeat_id}")
            row["rq3_adaptive_activation_gain"] = (
                adaptive_curve[final_key] - adaptive_curve["1"]
                - (static_curve[final_key] - static_curve["1"])
            )
            row["rq3_post_feedback_anomaly_gain"] = (
                adaptive["post_feedback_anomaly_yield"]
                - static["post_feedback_anomaly_yield"]
            )
        pairs.append(row)
    return pairs


def api_records(
    api_ids: Sequence[str],
    run_rows: Sequence[Mapping[str, Any]],
    pair_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result = []
    for api_id in api_ids:
        runs = [dict(row) for row in run_rows if row["api_id"] == api_id]
        pairs = [dict(row) for row in pair_rows if row["api_id"] == api_id]
        aggregates: dict[str, Any] = {}
        for group_id in GROUPS:
            group_runs = [row for row in runs if row["group_id"] == group_id]
            for field in ("target_activation_coverage", "reproducible_anomaly_yield"):
                values = [row[field] for row in group_runs if row[field] is not None]
                aggregates[f"median_{group_id}_{field}"] = median(values) if values else None
                aggregates[f"computable_{group_id}_{field}_repeat_count"] = len(values)
        for field in (
            "rq2_activation_difference",
            "rq2_anomaly_yield_difference",
            "rq3_adaptive_activation_gain",
            "rq3_post_feedback_anomaly_gain",
        ):
            values = [row[field] for row in pairs if row[field] is not None]
            aggregates[f"median_{field}"] = median(values) if values else None
            aggregates[f"computable_{field}_repeat_count"] = len(values)
        result.append({"api_id": api_id, "runs": runs, "paired_results": pairs, "aggregates": aggregates})
    return result


def rq_summary(
    api_ids: Sequence[str],
    state: Mapping[str, Any],
    targets: Mapping[str, Sequence[str]],
    rounds: Sequence[RoundResult],
    api_results: Sequence[Mapping[str, Any]],
    artifact_validator: Draft202012Validator,
) -> dict[str, Any]:
    harness_results = {}
    for api_id in api_ids:
        success, reason = preparation_metric(state, api_id, targets[api_id], artifact_validator)
        harness_results[api_id] = {"success": success, "failure_reason": reason}
    successes = sum(item["success"] for item in harness_results.values())
    static_round1: dict[str, list[RoundResult]] = defaultdict(list)
    for item in rounds:
        if item.group_id == "bug_aware_static" and item.round_index == 1:
            static_round1[item.api_id].append(item)
    reach = {}
    for api_id in api_ids:
        values = []
        for item in static_round1.get(api_id, []):
            reached = sum(
                state_name in {"checked_false", "checked_true"}
                for state_name in item.target_states.values()
            )
            values.append(reached / len(targets[api_id]))
        reach[api_id] = {
            "median_rate": median(values) if values else None,
            "computable_repeat_count": len(values),
        }
    api_aggregates = {item["api_id"]: item["aggregates"] for item in api_results}
    if set(api_aggregates) != set(api_ids):
        missing = sorted(set(api_ids) - set(api_aggregates))
        extra = sorted(set(api_aggregates) - set(api_ids))
        raise InputError(f"Per-API result set mismatch; missing={missing}, extra={extra}")
    return {
        "rq1": {
            "RQ1_M1_E2E_HARNESS_RATE": {
                "success_count": successes,
                "selected_api_count": len(api_ids),
                "rate": successes / len(api_ids),
                "wilson_95_interval": wilson_interval(successes, len(api_ids)),
                "per_api": harness_results,
            },
            "RQ1_M2_OBSERVATION_REACH_RATE": {
                "computable_api_count": sum(
                    value["median_rate"] is not None for value in reach.values()
                ),
                "per_api": reach,
            },
        },
        "rq2": {
            "RQ2_M1_TARGET_ACTIVATION_COVERAGE": {
                api_id: {
                    "structured_baseline_median": api_aggregates[api_id]["median_structured_baseline_target_activation_coverage"],
                    "bug_aware_static_median": api_aggregates[api_id]["median_bug_aware_static_target_activation_coverage"],
                    "paired_difference_median": api_aggregates[api_id]["median_rq2_activation_difference"],
                }
                for api_id in api_ids
            },
            "RQ2_M2_REPRODUCIBLE_ANOMALY_YIELD": {
                api_id: {
                    "structured_baseline_median": api_aggregates[api_id]["median_structured_baseline_reproducible_anomaly_yield"],
                    "bug_aware_static_median": api_aggregates[api_id]["median_bug_aware_static_reproducible_anomaly_yield"],
                    "paired_difference_median": api_aggregates[api_id]["median_rq2_anomaly_yield_difference"],
                }
                for api_id in api_ids
            },
        },
        "rq3": {
            "RQ3_M1_ADAPTIVE_ACTIVATION_GAIN": {
                api_id: api_aggregates[api_id]["median_rq3_adaptive_activation_gain"]
                for api_id in api_ids
            },
            "RQ3_M2_POST_FEEDBACK_ANOMALY_GAIN": {
                api_id: api_aggregates[api_id]["median_rq3_post_feedback_anomaly_gain"]
                for api_id in api_ids
            },
        },
    }


def write_json(path: Path, value: Any) -> None:
    data = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != data:
            raise ImmutableConflict(f"Existing result differs: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(data, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def write_text(path: Path, data: str) -> None:
    if path.exists():
        if path.read_text(encoding="utf-8") != data:
            raise ImmutableConflict(f"Existing result differs: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(data, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    if path.exists():
        if path.read_bytes() != temporary.read_bytes():
            temporary.unlink()
            raise ImmutableConflict(f"Existing result differs: {path}")
        temporary.unlink()
        return
    os.replace(temporary, path)


def readiness(
    matrix: Mapping[str, Any],
    manifest: Mapping[str, Any],
    run_root: Path,
) -> list[str]:
    issues = []
    if matrix.get("matrix_format_version") != MATRIX_FORMAT_VERSION:
        issues.append("unsupported matrix_format_version")
    if matrix.get("lifecycle", {}).get("status") != "frozen":
        issues.append("matrix lifecycle is not frozen")
    if matrix.get("unresolved_bindings"):
        issues.append(f"matrix has {len(matrix['unresolved_bindings'])} unresolved bindings")
    if not matrix.get("api_entries"):
        issues.append("matrix.api_entries is empty")
    if manifest.get("status") != "frozen":
        issues.append("Evaluation Target Manifest is not frozen")
    if not manifest.get("api_target_sets"):
        issues.append("Evaluation Target Manifest has no API target sets")
    entries = matrix.get("api_entries")
    target_sets_value = manifest.get("api_target_sets")
    if isinstance(entries, list) and entries and isinstance(target_sets_value, list) and target_sets_value:
        try:
            enabled_api_ids = set(matrix_api_ids(matrix))
            manifest_api_ids = {
                require_string(
                    require_object(item, "api_target_sets[]").get("api_id"),
                    "api_target_sets[].api_id",
                )
                for item in target_sets_value
            }
            if enabled_api_ids != manifest_api_ids:
                issues.append(
                    "enabled matrix API set differs from Evaluation Target Manifest API set"
                )
        except InputError as exc:
            issues.append(str(exc))
    if not (run_root / "execution_index.json").is_file():
        issues.append("execution_index.json is missing")
    if not (run_root / "result_provenance.json").is_file():
        issues.append("result_provenance.json is missing")
    return issues


def consumed_file_hashes(paths: Iterable[Path]) -> list[dict[str, str]]:
    unique = sorted({path.resolve() for path in paths}, key=lambda item: item.as_posix())
    return [
        {
            "relative_path": path.relative_to(REPOSITORY_ROOT).as_posix(),
            "content_hash": file_hash(path),
        }
        for path in unique
    ]


def render_summary(
    record: Mapping[str, Any],
    api_results: Sequence[Mapping[str, Any]],
) -> str:
    counts = record["counts"]
    rq1_group = record["rq_summary"]["rq1"]
    rq1 = rq1_group["RQ1_M1_E2E_HARNESS_RATE"]
    reach = rq1_group["RQ1_M2_OBSERVATION_REACH_RATE"]
    lines = [
        f"# Experiment Analysis: {record['matrix_id']}",
        "",
        f"- Analysis ID: `{record['analysis_id']}`",
        f"- Analysis cutoff: `{record['analysis_cutoff_at']}`",
        f"- APIs: {counts['api_count']}",
        f"- Valid Round records: {counts['round_record_count']}",
        f"- Attrited or missing tasks: {counts['attrited_task_count']}",
        f"- Unresolved current-run cases/clusters: {counts['unresolved_case_or_cluster_count']}",
        f"- Coverage replay present: {counts['coverage_present_round_count']}/{counts['round_record_count']} rounds (diagnostic only)",
        f"- Coverage replay with LLVM warnings: {counts['coverage_warning_round_count']} rounds",
        "",
        "## RQ1",
        "",
        f"- End-to-end Harness rate: {rq1['success_count']}/{rq1['selected_api_count']} ({rq1['rate']:.4f})",
        f"- APIs with computable observation reach: {reach['computable_api_count']}/{counts['api_count']}",
        "",
        "## Per-API primary medians",
        "",
        "| API | Observation reach | Baseline KTAC | Static KTAC | Baseline anomalies | Static anomalies | Adaptive activation gain | Adaptive anomaly gain |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in api_results:
        values = item["aggregates"]
        def shown(value: Any) -> str:
            return "unavailable" if value is None else f"{value:.4f}"
        lines.append(
            "| "
            + " | ".join(
                (
                    item["api_id"],
                    shown(reach["per_api"][item["api_id"]]["median_rate"]),
                    shown(values["median_structured_baseline_target_activation_coverage"]),
                    shown(values["median_bug_aware_static_target_activation_coverage"]),
                    shown(values["median_structured_baseline_reproducible_anomaly_yield"]),
                    shown(values["median_bug_aware_static_reproducible_anomaly_yield"]),
                    shown(values["median_rq3_adaptive_activation_gain"]),
                    shown(values["median_rq3_post_feedback_anomaly_gain"]),
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "Machine-readable JSON and CSV files remain the authoritative results.",
            "",
        ]
    )
    return "\n".join(lines)


def analyze(args: argparse.Namespace) -> dict[str, Any]:
    matrix_path = repository_path(args.matrix, "matrix")
    target_path = repository_path(args.target_manifest, "Evaluation Target Manifest")
    run_root = repository_path(args.run_root, "run root")
    case_root = repository_path(args.case_root, "Crash Case root")
    matrix = require_object(load_json(matrix_path), "experiment matrix")
    schema_paths = analysis_schema_paths(matrix)
    manifest_validator = schema_validator(schema_paths["evaluation_target_manifest"])
    manifest = validate_record(
        load_json(target_path),
        manifest_validator,
        "Evaluation Target Manifest",
    )
    for reference, label in walk_file_references(matrix):
        verify_file_reference(reference, label)
    blockers = readiness(matrix, manifest, run_root)
    if args.validate_only:
        return {
            "status": "ready" if not blockers else "valid_draft",
            "analyzer_version": ANALYZER_VERSION,
            "readiness_issues": blockers,
        }
    if blockers:
        raise InputError("Analysis is not ready: " + "; ".join(blockers))

    api_ids = matrix_api_ids(matrix)
    targets = target_sets(manifest, api_ids)
    state_path = run_root / "execution_index.json"
    provenance_path = run_root / "result_provenance.json"
    state = validate_record(
        load_json(state_path),
        schema_validator(schema_paths["execution_index"]),
        "Execution Index",
    )
    provenance = validate_record(
        load_json(provenance_path),
        schema_validator(schema_paths["result_provenance"]),
        "Result Provenance",
    )
    matrix_hash = canonical_hash(matrix)
    if state.get("matrix_content_hash") != matrix_hash or provenance.get("matrix_content_hash") != matrix_hash:
        raise InputError("Execution state or result provenance belongs to another matrix")
    cutoff = parse_utc(provenance.get("analysis_cutoff_at"), "analysis_cutoff_at")

    round_validator = schema_validator(ROUND_SCHEMA)
    artifact_validator = schema_validator(ARTIFACT_SCHEMA)
    case_validator = schema_validator(CASE_SCHEMA)
    snapshot_validator = schema_validator(schema_paths["runtime_snapshot"])
    required_artifacts = referenced_artifact_keys(state, round_validator)
    artifacts = artifact_index(
        state,
        run_root,
        artifact_validator,
        required_artifacts,
    )
    rounds, attrition = load_rounds(
        matrix,
        state,
        targets,
        artifacts,
        round_validator,
        snapshot_validator,
    )
    coverage_rows = coverage_diagnostics(rounds, matrix)
    cutoff_cases = latest_cases_at_cutoff(case_root, cutoff, case_validator)
    cases = relevant_cases(cutoff_cases, rounds)
    validate_candidate_case_coverage(rounds, cases)
    anomalies, unresolved_cases = anomaly_occurrences(cases, rounds)
    validate_pairing(rounds)
    validate_adaptive_lineage(rounds, state)
    runs = run_metrics(matrix, targets, rounds, anomalies)
    pairs = paired_metrics(runs, matrix["execution"]["round_count"])
    per_api = api_records(api_ids, runs, pairs)
    summary = rq_summary(api_ids, state, targets, rounds, per_api, artifact_validator)

    input_hashes = {
        "matrix": file_hash(matrix_path),
        "execution_index": file_hash(state_path),
        "result_provenance": file_hash(provenance_path),
        "evaluation_target_manifest": file_hash(target_path),
        "harness_artifacts": consumed_file_hashes(
            Path(item.artifact_path) for item in rounds
        ),
        "round_records": consumed_file_hashes(
            Path(item.round_record_path) for item in rounds
        ),
        "runtime_snapshots": consumed_file_hashes(
            Path(item.snapshot_path) for item in rounds if item.snapshot_path is not None
        ),
        "crash_case_records": sorted(canonical_hash(case) for case in cases),
    }
    analyzer_hash = file_hash(Path(__file__).resolve())
    analysis_key = canonical_hash(
        {
            "analyzer_version": ANALYZER_VERSION,
            "analyzer_content_hash": analyzer_hash,
            "input_hashes": input_hashes,
        }
    )
    record = {
        "analysis_format_version": "1.0",
        "analysis_id": f"analysis:{matrix['matrix_id']}:{analysis_key[:16]}",
        "analysis_key": analysis_key,
        "analyzer": {
            "analyzer_id": ANALYZER_ID,
            "analyzer_version": ANALYZER_VERSION,
            "content_hash": analyzer_hash,
        },
        "matrix_id": matrix["matrix_id"],
        "analysis_cutoff_at": provenance["analysis_cutoff_at"],
        "input_hashes": input_hashes,
        "counts": {
            "api_count": len(api_ids),
            "round_record_count": len(rounds),
            "attrited_task_count": len(attrition),
            "cutoff_case_count": len(cases),
            "unresolved_case_or_cluster_count": unresolved_cases,
            "coverage_present_round_count": sum(row["status"] == "present" for row in coverage_rows),
            "coverage_warning_round_count": sum(row["quality_status"] == "partial_warning" for row in coverage_rows),
        },
        "attrition": attrition,
        "rq_summary": summary,
    }
    output = repository_path(args.output_root, "output root") / matrix["matrix_id"] / analysis_key[:16]
    write_json(output / "analysis_record.json", record)
    write_text(output / "summary.md", render_summary(record, per_api))
    for item in per_api:
        safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", item["api_id"])
        write_json(output / "per_api" / f"{safe_id}.json", item)
    write_csv(
        output / "tables" / "run_metrics.csv",
        runs,
        (
            "api_id", "group_id", "repeat_id", "completed", "completion_status",
            "completed_round_count", "target_count",
            "activated_target_count", "target_activation_coverage",
            "reproducible_anomaly_yield", "post_feedback_anomaly_yield",
        ),
    )
    write_csv(
        output / "tables" / "coverage_diagnostics.csv",
        coverage_rows,
        (
            "api_id", "group_id", "repeat_id", "round_index", "status",
            "quality_status", "source_file_count", "corpus_file_count",
            "lines_covered", "lines_total", "branches_covered", "branches_total",
            "warning_count",
        ),
    )
    write_csv(
        output / "tables" / "paired_metrics.csv",
        pairs,
        (
            "api_id", "repeat_id", "rq2_pair_complete", "rq3_pair_complete",
            "rq2_activation_difference", "rq2_anomaly_yield_difference",
            "rq3_adaptive_activation_gain", "rq3_post_feedback_anomaly_gain",
        ),
    )
    return {"status": "completed", "analysis_path": str(output), **record["counts"]}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--target-manifest", type=Path, default=DEFAULT_TARGET_MANIFEST)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--case-root", type=Path, default=DEFAULT_CASE_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        print(json.dumps(analyze(parse_args(argv)), ensure_ascii=False, indent=2))
        return 0
    except AnalysisError as exc:
        print(
            json.dumps(
                {"status": "error", "error_type": type(exc).__name__, "message": str(exc)},
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
