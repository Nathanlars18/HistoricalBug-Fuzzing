#!/usr/bin/env python3
"""Validate, prepare, execute, resume, and finalize an EXP014 matrix.

The Runner owns orchestration and execution state. It never performs semantic
Knowledge selection, Strategy synthesis decisions, crash triage, or metric
calculation. Draft matrices may be validated and planned, but only a frozen,
fully bound matrix may prepare or execute experiment artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
sys.path.insert(0, str(Path(__file__).resolve().parent))
from execution_semantics import text_output, validate_limits


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
EXP_ROOT = REPOSITORY_ROOT / "experiment" / "EXP014_experimental_evaluation"
DEFAULT_MATRIX = EXP_ROOT / "configs" / "experiment_matrix.json"
DEFAULT_RUN_ROOT = EXP_ROOT / "runs"
SPEC_BUILDER = REPOSITORY_ROOT / (
    "experiment/EXP011_bug_aware_harness_synthesis/scripts/"
    "build_harness_spec_json.py"
)
STRATEGY_BUILDER = REPOSITORY_ROOT / (
    "experiment/EXP011_bug_aware_harness_synthesis/scripts/"
    "build_strategy_plan_json.py"
)
ARTIFACT_BUILDER = REPOSITORY_ROOT / (
    "experiment/EXP011_bug_aware_harness_synthesis/scripts/"
    "build_harness_artifact.py"
)
RUNNER_VERSION = "0.8.0"
FEEDBACK_CONTROLLER = REPOSITORY_ROOT / (
    "experiment/EXP012_adaptive_feedback/scripts/"
    "run_feedback_controller.py"
)
MATRIX_VERSION = "0.4"
GROUP_IDS = (
    "structured_baseline",
    "bug_aware_static",
    "bug_aware_adaptive",
)
TERMINAL_TASK_STATUSES = {
    "completed",
    "completed_with_abnormal_events",
    "method_failed",
    "aborted_by_feedback",
    "budget_incomplete",
    "blocked_by_prior_failure",
    "infrastructure_failed",
}


class RunnerError(RuntimeError):
    pass


class ConfigurationError(RunnerError):
    pass


class ExecutionNotReady(ConfigurationError):
    pass


class ImmutableConflict(RunnerError):
    pass


@dataclass(frozen=True)
class Task:
    api_id: str
    target_api: str
    group_id: str
    repeat_id: int
    round_index: int
    seed: int | None

    @property
    def canonical_repeat_id(self) -> str:
        return f"repeat_{self.repeat_id:03d}"

    @property
    def canonical_round_id(self) -> str:
        return f"round_{self.round_index:03d}"

    @property
    def key(self) -> str:
        return ":".join(
            (
                self.api_id,
                self.group_id,
                self.canonical_repeat_id,
                self.canonical_round_id,
            )
        )


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"Invalid UTC timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ConfigurationError(f"Timestamp lacks timezone: {value!r}")
    return parsed.astimezone(timezone.utc)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"Cannot read JSON {path}: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def write_immutable_json(path: Path, value: Any) -> None:
    if path.exists():
        raise ImmutableConflict(f"Refusing to overwrite immutable record: {path}")
    write_json(path, value)


def write_or_verify_immutable_json(path: Path, value: Any) -> None:
    if path.exists():
        if load_json(path) != value:
            raise ImmutableConflict(
                f"Existing immutable record has different content: {path}"
            )
        return
    write_immutable_json(path, value)


def repository_path(value: str | Path) -> Path:
    path = Path(value)
    resolved = path if path.is_absolute() else REPOSITORY_ROOT / path
    resolved = resolved.resolve()
    if not resolved.is_relative_to(REPOSITORY_ROOT):
        raise ConfigurationError(f"Input path escapes repository: {value}")
    return resolved


def run_root_path(value: str | Path) -> Path:
    resolved = Path(value).resolve()
    if not resolved.is_relative_to(REPOSITORY_ROOT):
        raise ConfigurationError("Run root must remain inside the repository")
    if resolved == Path(resolved.anchor):
        raise ConfigurationError("Run root cannot be a filesystem root")
    return resolved


def safe_component(value: str) -> str:
    result = re.sub(r"[^A-Za-z0-9]+", "_", value.strip()).strip("_").lower()
    if not result:
        raise ConfigurationError(f"Empty path component from {value!r}")
    return result


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigurationError(f"{label} must be an object")
    return value


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ConfigurationError(f"{label} must be a non-empty string")
    return value


def verify_file_reference(reference: Any, label: str) -> Path:
    item = require_object(reference, label)
    relative = require_string(item.get("relative_path"), f"{label}.relative_path")
    declared = require_string(item.get("content_hash"), f"{label}.content_hash")
    path = repository_path(relative)
    if not path.is_file():
        raise ConfigurationError(f"{label} is missing: {relative}")
    actual = file_hash(path)
    if actual != declared:
        raise ConfigurationError(
            f"{label} hash mismatch for {relative}: {actual} != {declared}"
        )
    return path


def resolve_artifact_binding(binding: Any, label: str) -> tuple[dict[str, Any], Path]:
    item = require_object(binding, label)
    artifact_ref = require_object(item.get("artifact_ref"), f"{label}.artifact_ref")
    record_path = verify_file_reference(
        item.get("record_file_ref"),
        f"{label}.record_file_ref",
    )
    record = require_object(load_json(record_path), f"{label} record")
    declared = require_string(
        artifact_ref.get("content_hash"),
        f"{label}.artifact_ref.content_hash",
    )
    actual = content_hash(record)
    if actual != declared:
        raise ConfigurationError(
            f"{label} canonical record hash mismatch: {actual} != {declared}"
        )
    return record, record_path


def verify_declared_file_refs(value: Any) -> list[str]:
    checked: list[str] = []

    def visit(node: Any, trail: str) -> None:
        if isinstance(node, dict):
            if "relative_path" in node and "content_hash" in node:
                path = verify_file_reference(node, trail)
                checked.append(path.relative_to(REPOSITORY_ROOT).as_posix())
            for key, child in node.items():
                visit(child, f"{trail}/{key}")
        elif isinstance(node, list):
            for index, child in enumerate(node):
                visit(child, f"{trail}/{index}")

    visit(value, "matrix")
    return sorted(set(checked))


def group_map(matrix: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    groups = matrix.get("core_groups")
    if not isinstance(groups, list):
        raise ConfigurationError("core_groups must be an array")
    result: dict[str, dict[str, Any]] = {}
    for value in groups:
        group = require_object(value, "core_groups item")
        group_id = require_string(group.get("group_id"), "core_groups.group_id")
        if group_id in result:
            raise ConfigurationError(f"Duplicate core group: {group_id}")
        result[group_id] = group
    if tuple(sorted(result)) != tuple(sorted(GROUP_IDS)):
        raise ConfigurationError("core_groups must contain exactly three internal groups")
    return result


def validate_controlled_design(matrix: Mapping[str, Any]) -> None:
    """Reject matrix settings that break the three-group causal comparison."""
    groups = group_map(matrix)
    expected = {
        "structured_baseline": {
            "harness_spec_builder_mode": "controlled_baseline",
            "knowledge_exposure": "none",
            "feedback_mode": "disabled",
            "initial_harness_policy": "independent_structured_baseline",
        },
        "bug_aware_static": {
            "harness_spec_builder_mode": "bug_aware_static",
            "knowledge_exposure": "api_specific",
            "feedback_mode": "observe_only",
            "initial_harness_policy": "shared_bug_aware_h0",
        },
        "bug_aware_adaptive": {
            "harness_spec_builder_mode": "reuse_bug_aware_static_h0",
            "knowledge_exposure": "api_specific",
            "feedback_mode": "adaptive",
            "initial_harness_policy": "reference_bug_aware_static_h0",
        },
    }
    for group_id, fields in expected.items():
        group = groups[group_id]
        for field, expected_value in fields.items():
            if group.get(field) != expected_value:
                raise ConfigurationError(
                    f"core_groups[{group_id}].{field} must be "
                    f"{expected_value!r}"
                )

    seed_policy = require_object(matrix.get("seed_policy"), "seed_policy")
    if seed_policy.get("group_id_excluded") is not True:
        raise ConfigurationError(
            "seed_policy.group_id_excluded must be true for paired groups"
        )

    corpus_policy = require_object(matrix.get("corpus_policy"), "corpus_policy")
    for field, expected_value in {
        "independent_copy_per_group_and_repeat": True,
        "inherit_within_repeat": True,
        "share_runtime_corpus_across_groups": False,
        "share_runtime_corpus_across_repeats": False,
    }.items():
        if corpus_policy.get(field) is not expected_value:
            raise ConfigurationError(
                f"corpus_policy.{field} must be {str(expected_value).lower()}"
            )

    feedback = require_object(matrix.get("feedback"), "feedback")
    shared = require_object(
        feedback.get("shared_initial_state"),
        "feedback.shared_initial_state",
    )
    if shared.get("source_group") != "bug_aware_static":
        raise ConfigurationError(
            "feedback.shared_initial_state.source_group must be bug_aware_static"
        )
    for field in (
        "reuse_exact_harness_spec",
        "reuse_exact_strategy",
        "reuse_exact_core_source",
        "reuse_exact_instrumented_source",
        "reuse_exact_binary",
    ):
        if shared.get(field) is not True:
            raise ConfigurationError(
                f"feedback.shared_initial_state.{field} must be true"
            )
    if feedback.get("extend_fuzzing_budget_after_revision_failure") is not False:
        raise ConfigurationError(
            "feedback.extend_fuzzing_budget_after_revision_failure must be false"
        )


def execution_readiness_issues(matrix: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    lifecycle = require_object(matrix.get("lifecycle"), "lifecycle")
    if lifecycle.get("status") != "frozen":
        issues.append("lifecycle.status is not frozen")
    unresolved = matrix.get("unresolved_bindings")
    if not isinstance(unresolved, list):
        raise ConfigurationError("unresolved_bindings must be an array")
    if unresolved:
        issues.append(f"{len(unresolved)} unresolved binding(s) remain")
    if not matrix.get("api_entries"):
        issues.append("api_entries is empty")
    return issues


def validate_matrix(matrix: Mapping[str, Any]) -> list[str]:
    if matrix.get("matrix_format_version") != MATRIX_VERSION:
        raise ConfigurationError(
            f"Unsupported matrix format {matrix.get('matrix_format_version')!r}; "
            f"expected {MATRIX_VERSION}"
        )
    require_string(matrix.get("matrix_id"), "matrix_id")
    group_map(matrix)

    execution = require_object(matrix.get("execution"), "execution")
    for field in (
        "repeat_count",
        "round_count",
        "active_fuzzing_seconds_per_round",
    ):
        value = execution.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ConfigurationError(f"execution.{field} must be positive")
    limits = require_object(execution.get("resource_limits", {"candidate_sample_limit": 64}), "execution.resource_limits")
    threads = require_object(execution.get("thread_environment", {}), "execution.thread_environment")
    if set(threads) - {"OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"} or any(
        not isinstance(v, str) or not v.isdigit() or int(v) < 1 for v in threads.values()
    ):
        raise ConfigurationError("Explicit thread environment must contain positive thread counts")
    unknown_limits = set(limits) - {"timeout", "rss_limit_mb", "max_len", "process_memory_mb", "candidate_sample_limit"}
    if unknown_limits:
        raise ConfigurationError(f"Unsupported execution resource limits: {sorted(unknown_limits)}")
    normalized_limits = {"timeout": limits.get("timeout"), "rss_limit_mb": limits.get("rss_limit_mb"),
                         "max_len": limits.get("max_len"), "process_memory_mb": limits.get("process_memory_mb"),
                         "candidate_sample_limit": limits.get("candidate_sample_limit", 64)}
    try:
        validate_limits(normalized_limits)
    except ValueError as exc:
        raise ConfigurationError(str(exc)) from exc

    order_rows = execution.get("group_order_by_repeat")
    if not isinstance(order_rows, list):
        raise ConfigurationError("execution.group_order_by_repeat must be an array")
    orders: dict[int, list[str]] = {}
    for row_value in order_rows:
        row = require_object(row_value, "group_order_by_repeat item")
        repeat_id = row.get("repeat_id")
        order = row.get("group_order")
        if (
            not isinstance(repeat_id, int)
            or isinstance(repeat_id, bool)
            or repeat_id in orders
        ):
            raise ConfigurationError("group_order repeat_id must be unique integers")
        if (
            not isinstance(order, list)
            or len(order) != len(GROUP_IDS)
            or len(set(order)) != len(order)
            or set(order) != set(GROUP_IDS)
        ):
            raise ConfigurationError(
                f"group_order for repeat {repeat_id} must be an exact permutation"
            )
        orders[repeat_id] = order
    expected_repeats = set(range(1, execution["repeat_count"] + 1))
    if set(orders) != expected_repeats:
        raise ConfigurationError("group_order_by_repeat does not cover every repeat")

    feedback = require_object(matrix.get("feedback"), "feedback")
    decision_rounds = feedback.get("decision_after_rounds")
    if not isinstance(decision_rounds, list):
        raise ConfigurationError("feedback.decision_after_rounds must be an array")
    for value in decision_rounds:
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or not 1 <= value < execution["round_count"]
        ):
            raise ConfigurationError("feedback decision round is out of range")

    entries = matrix.get("api_entries")
    if not isinstance(entries, list):
        raise ConfigurationError("api_entries must be an array")
    seen: set[str] = set()
    for value in entries:
        entry = require_object(value, "api_entries item")
        api_id = require_string(entry.get("api_id"), "api_entries.api_id")
        require_string(
            entry.get("target_manifest_entry_id"),
            f"api_entries[{api_id}].target_manifest_entry_id",
        )
        if api_id in seen:
            raise ConfigurationError(f"Duplicate api_id: {api_id}")
        seen.add(api_id)

    seed_policy = require_object(matrix.get("seed_policy"), "seed_policy")
    if (
        seed_policy.get("canonical_input_encoding") != "utf8_nul_separated_v1"
        or seed_policy.get("digest_projection")
        != "first_8_bytes_unsigned_big_endian"
    ):
        raise ConfigurationError("Unsupported seed derivation encoding")

    validate_controlled_design(matrix)

    coverage = require_object(matrix.get("coverage"), "coverage")
    if not isinstance(coverage.get("enabled"), bool):
        raise ConfigurationError("coverage.enabled must be boolean")
    if coverage["enabled"]:
        if coverage.get("replay_after_each_round") is not True:
            raise ConfigurationError("Enabled coverage requires replay_after_each_round")
        if coverage.get("input") != "frozen_round_end_corpus":
            raise ConfigurationError("Coverage must replay the frozen round-end corpus")
        if coverage.get("cumulative_merge") != "set_union":
            raise ConfigurationError("Unsupported cumulative coverage merge")
        scope_path = verify_file_reference(coverage.get("scope_file_ref"), "coverage scope")
        try:
            from coverage_replay import CoverageError, load_scope
        except ModuleNotFoundError as exc:
            if exc.name != "coverage_replay":
                raise
            from experiment.EXP014_experimental_evaluation.scripts.coverage_replay import (
                CoverageError,
                load_scope,
            )
        try:
            load_scope(scope_path)
        except (CoverageError, OSError, ValueError) as exc:
            raise ConfigurationError(f"Invalid coverage scope: {exc}") from exc

    return execution_readiness_issues(matrix)


def require_execution_ready(matrix: Mapping[str, Any]) -> None:
    issues = execution_readiness_issues(matrix)
    if issues:
        raise ExecutionNotReady("; ".join(issues))
    execution = require_object(matrix["execution"], "execution")
    adapters = require_object(
        execution.get("runner_adapters"),
        "execution.runner_adapters",
    )
    for field in ("round_argv_template", "preflight_argv_template"):
        value = adapters.get(field)
        if (
            not isinstance(value, list)
            or not value
            or not all(isinstance(part, str) and part for part in value)
        ):
            raise ExecutionNotReady(f"runner adapter {field} is not bound")

    shared = require_object(
        matrix["inputs"].get("shared_artifact_refs"),
        "inputs.shared_artifact_refs",
    )
    for name in (
        "capability_snapshot",
        "evaluation_target_manifest",
        "helper_profile_set",
        "strategy_primitive_catalog",
    ):
        resolve_artifact_binding(shared.get(name), f"shared artifact {name}")
    environment = require_object(
        matrix.get("execution_environment"),
        "execution_environment",
    )
    resolve_artifact_binding(
        environment.get("fuzz_environment_snapshot_ref"),
        "fuzz environment snapshot",
    )
    resolve_artifact_binding(
        environment.get("coverage_environment_snapshot_ref"),
        "coverage environment snapshot",
    )
    verify_file_reference(
        environment.get("resource_profile_file_ref"),
        "resource profile",
    )
    if matrix.get('preparation', {}).get('mode', 'synthesize') != 'reuse_approved':
        model_arguments(matrix)
    for entry in matrix["api_entries"]:
        api_profile(entry)
        verify_file_reference(
            entry.get("compile_profile_file_ref"),
            f"compile profile for {entry['api_id']}",
        )
        initial_corpus_record(entry)


def selected_apis(
    matrix: Mapping[str, Any],
    requested: Sequence[str],
) -> list[dict[str, Any]]:
    wanted = set(requested)
    entries = [
        require_object(value, "api_entries item")
        for value in matrix["api_entries"]
        if require_object(value, "api_entries item").get("enabled", True)
    ]
    if wanted:
        unknown = wanted - {entry["api_id"] for entry in entries}
        if unknown:
            raise ConfigurationError(f"Unknown or disabled API ids: {sorted(unknown)}")
        entries = [entry for entry in entries if entry["api_id"] in wanted]
    return sorted(entries, key=lambda entry: entry["api_id"])


def derive_seed(
    matrix: Mapping[str, Any],
    api_id: str,
    repeat_id: int,
    round_index: int,
) -> int | None:
    policy = require_object(matrix.get("seed_policy"), "seed_policy")
    master = policy.get("master_seed")
    lower = policy.get("supported_seed_minimum")
    upper = policy.get("supported_seed_maximum")
    if master is None and lower is None and upper is None:
        return None
    if (
        not isinstance(master, int)
        or isinstance(master, bool)
        or not isinstance(lower, int)
        or isinstance(lower, bool)
        or not isinstance(upper, int)
        or isinstance(upper, bool)
        or lower > upper
    ):
        raise ConfigurationError("seed_policy range is incomplete or invalid")
    parts = (str(master), api_id, str(repeat_id), str(round_index))
    payload = b"\0".join(part.encode("utf-8") for part in parts)
    projected = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
    return lower + projected % (upper - lower + 1)


def api_profile(entry: Mapping[str, Any]) -> tuple[dict[str, Any], Path]:
    profile, path = resolve_artifact_binding(
        entry.get("api_profile_binding"),
        f"api_entries[{entry['api_id']}].api_profile_binding",
    )
    target = require_object(profile.get("target"), "API Profile target")
    require_string(target.get("python_api"), "API Profile target.python_api")
    return profile, path


def evaluation_target_manifest(matrix: Mapping[str, Any]) -> Path:
    """Resolve the common Target Manifest used by every generated Harness."""
    shared = require_object(
        matrix["inputs"].get("shared_artifact_refs"),
        "inputs.shared_artifact_refs",
    )
    _, path = resolve_artifact_binding(
        shared.get("evaluation_target_manifest"),
        "shared artifact evaluation_target_manifest",
    )
    return path


def frozen_knowledge_arguments(entry: Mapping[str, Any], matrix: Mapping[str, Any] | None = None) -> list[str]:
    """Reuse the Builder's exact-input validator; never select Knowledge here."""
    bindings = entry.get("knowledge_bindings")
    if not isinstance(bindings, list) or not bindings:
        raise ConfigurationError(
            f"{entry['api_id']}: new preparation requires non-empty knowledge_bindings "
            "(knowledge_id, schema_version, file_ref); legacy directory discovery is disabled"
        )
    name = "_matrix_harness_spec_input_validation"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, SPEC_BUILDER)
        if spec is None or spec.loader is None:
            raise ConfigurationError("Cannot load HarnessSpec input validator")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    module = sys.modules[name]
    profile, _ = api_profile(entry)
    try:
        ledger = repository_path(str(module.DEFAULTS["knowledge_review_ledger"]))
        pinned = (matrix or {}).get("inputs", {}).get("shared_artifact_refs", {}).get("knowledge_review_ledger")
        if pinned is not None:
            ledger = repository_path(pinned["relative_path"])
            if file_hash(ledger) != pinned["content_hash"]:
                raise ConfigurationError("Frozen Knowledge review ledger hash mismatch")
        reviews = module.load_approved_knowledge_reviews(ledger)
        module.select_bound_knowledge(bindings, profile["target"]["framework"],
                                      profile["target"]["python_api"], reviews)
    except module.InputError as exc:
        raise ConfigurationError(str(exc)) from exc
    return ["--knowledge-review-ledger", str(ledger), *[argument for binding in bindings
            for argument in ("--knowledge-binding", json.dumps(binding, sort_keys=True))]]


def validate_target_knowledge_bindings(matrix: Mapping[str, Any], entry: Mapping[str, Any]) -> None:
    manifest = load_json(evaluation_target_manifest(matrix))
    matches = [item for item in manifest["api_target_sets"] if item["api_id"] == entry["api_id"]]
    if len(matches) != 1:
        raise ConfigurationError(f"Expected one target set for {entry['api_id']}")
    target_set = matches[0]
    refs = [ref for target in target_set["targets"] for ref in target["source_knowledge_refs"]]
    refs += [item["knowledge_ref"] for item in target_set["excluded_knowledge"]]
    pinned = {item["knowledge_id"]: item for item in entry["knowledge_bindings"]}
    if {ref["knowledge_id"] for ref in refs} != set(pinned) or any(
        ref != pinned.get(ref["knowledge_id"]) for ref in refs
    ):
        raise ConfigurationError("Target Manifest Knowledge references differ from frozen API knowledge_bindings")


def helper_profile_set(matrix: Mapping[str, Any]) -> Path:
    """Resolve the exact Helper Profile set shared by all synthesis groups."""
    shared = require_object(
        matrix["inputs"].get("shared_artifact_refs"),
        "inputs.shared_artifact_refs",
    )
    _, path = resolve_artifact_binding(
        shared.get("helper_profile_set"),
        "shared artifact helper_profile_set",
    )
    return path


def build_tasks(
    matrix: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
) -> list[Task]:
    execution = require_object(matrix["execution"], "execution")
    orders = {
        row["repeat_id"]: row["group_order"]
        for row in execution["group_order_by_repeat"]
    }
    tasks: list[Task] = []
    for entry in entries:
        target_api = entry.get("target_api")
        if not isinstance(target_api, str) or not target_api:
            if execution_readiness_issues(matrix):
                target_api = f"<unresolved:{entry['api_id']}>"
            else:
                profile, _ = api_profile(entry)
                target_api = profile["target"]["python_api"]
        for repeat_id in range(1, execution["repeat_count"] + 1):
            for group_id in orders[repeat_id]:
                for round_index in range(1, execution["round_count"] + 1):
                    tasks.append(
                        Task(
                            api_id=entry["api_id"],
                            target_api=target_api,
                            group_id=group_id,
                            repeat_id=repeat_id,
                            round_index=round_index,
                            seed=derive_seed(
                                matrix,
                                entry["api_id"],
                                repeat_id,
                                round_index,
                            ),
                        )
                    )
    return tasks


def expand_argv(
    template: Sequence[str],
    values: Mapping[str, Any],
) -> list[str]:
    try:
        return [
            part.format_map({key: str(value) for key, value in values.items()})
            for part in template
        ]
    except KeyError as exc:
        raise ConfigurationError(
            f"Unknown runner template placeholder: {exc.args[0]}"
        ) from exc


def round_adapter_argv(matrix: Mapping[str, Any], values: Mapping[str, Any]) -> list[str]:
    argv = expand_argv(
        matrix["execution"]["runner_adapters"]["round_argv_template"], values
    )
    if matrix["coverage"]["enabled"]:
        scope_path = verify_file_reference(matrix["coverage"]["scope_file_ref"], "coverage scope")
        argv.extend(("--coverage-scope", str(scope_path)))
    argv.extend(resource_limit_arguments(matrix))
    return argv


def resource_limit_arguments(matrix: Mapping[str, Any]) -> list[str]:
    execution = require_object(matrix.get("execution", {}), "execution")
    if "resource_limits" not in execution:
        return []
    limits = require_object(execution["resource_limits"], "execution.resource_limits")
    args: list[str] = []
    for field, option in (("timeout", "--per-call-timeout-seconds"), ("rss_limit_mb", "--rss-limit-mb"),
                          ("max_len", "--max-input-bytes"), ("process_memory_mb", "--process-memory-mb")):
        value = limits.get(field)
        if value is not None:
            args.extend((option, str(value)))
    if "candidate_sample_limit" in limits and limits["candidate_sample_limit"] is not None:
        args.extend(("--candidate-sample-limit", str(limits["candidate_sample_limit"])))
    return args


def run_command(
    argv: Sequence[str],
    attempt_dir: Path,
    *,
    timeout_seconds: int | None = None,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if not argv or not all(isinstance(item, str) and item for item in argv):
        raise ConfigurationError("Command argv must be a non-empty string array")
    if attempt_dir.exists():
        raise ImmutableConflict(f"Attempt directory already exists: {attempt_dir}")
    attempt_dir.mkdir(parents=True)
    started_at = utc_now()
    started = time.monotonic()
    write_immutable_json(attempt_dir / "command.json", {"argv": list(argv)})
    try:
        completed = subprocess.run(
            list(argv),
            cwd=REPOSITORY_ROOT,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
            env=None if environment is None else {**os.environ, **environment},
        )
        outcome = {
            "started_at": started_at,
            "finished_at": utc_now(),
            "elapsed_seconds": time.monotonic() - started,
            "returncode": completed.returncode,
            "timed_out": False,
            "launch_error": None,
        }
        (attempt_dir / "stdout.log").write_text(
            completed.stdout,
            encoding="utf-8",
            newline="\n",
        )
        (attempt_dir / "stderr.log").write_text(
            completed.stderr,
            encoding="utf-8",
            newline="\n",
        )
    except subprocess.TimeoutExpired as exc:
        outcome = {
            "started_at": started_at,
            "finished_at": utc_now(),
            "elapsed_seconds": time.monotonic() - started,
            "returncode": None,
            "timed_out": True,
            "launch_error": None,
        }
        (attempt_dir / "stdout.log").write_text(
            text_output(exc.stdout),
            encoding="utf-8",
        )
        (attempt_dir / "stderr.log").write_text(
            text_output(exc.stderr),
            encoding="utf-8",
        )
    except OSError as exc:
        outcome = {
            "started_at": started_at,
            "finished_at": utc_now(),
            "elapsed_seconds": time.monotonic() - started,
            "returncode": None,
            "timed_out": False,
            "launch_error": f"{type(exc).__name__}: {exc}",
        }
        (attempt_dir / "stdout.log").write_text("", encoding="utf-8")
        (attempt_dir / "stderr.log").write_text(str(exc), encoding="utf-8")
    write_immutable_json(attempt_dir / "process_result.json", outcome)
    return outcome


def load_builder_result(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise RunnerError(f"{label} did not write its result JSON: {path}")
    return require_object(load_json(path), f"{label} result")


def builder_output_path(result: Mapping[str, Any], label: str) -> Path:
    value = require_string(result.get("output_path"), f"{label}.output_path")
    return repository_path(value)


def strategy_output_path(result: Mapping[str, Any]) -> Path:
    outcomes = result.get("outcomes")
    if not isinstance(outcomes, list) or len(outcomes) != 1:
        raise RunnerError("Strategy Builder must return exactly one outcome")
    outcome = require_object(outcomes[0], "Strategy Builder outcome")
    if outcome.get("status") != "success":
        raise RunnerError(f"Strategy Builder failed: {outcome}")
    return builder_output_path(outcome, "Strategy Builder outcome")


def artifact_output_path(result: Mapping[str, Any]) -> Path:
    outcomes = result.get("results")
    if not isinstance(outcomes, list) or len(outcomes) != 1:
        raise RunnerError("Harness Artifact Builder must return exactly one result")
    outcome = require_object(outcomes[0], "Harness Artifact result")
    if (
        outcome.get("status") not in {"generated", "reused"}
        or outcome.get("compile_status") != "passed"
    ):
        raise RunnerError(f"Harness Artifact did not compile: {outcome}")
    return repository_path(
        require_string(outcome.get("artifact_path"), "artifact_path")
    )


def model_arguments(matrix: Mapping[str, Any]) -> list[str]:
    reference = matrix["synthesis"].get("model_configuration_file_ref")
    if reference is None:
        raise ExecutionNotReady("synthesis.model_configuration_file_ref is unresolved")
    config = require_object(
        load_json(verify_file_reference(reference, "model configuration")),
        "model configuration",
    )
    model = require_string(config.get("model"), "model configuration.model")
    result = ["--model", model]
    api_url = config.get("api_url")
    if isinstance(api_url, str) and api_url:
        result.extend(["--api-url", api_url])
    return result


def initial_state(matrix: Mapping[str, Any], matrix_path: Path) -> dict[str, Any]:
    return {
        "runner_version": RUNNER_VERSION,
        "matrix_id": matrix["matrix_id"],
        "matrix_content_hash": content_hash(matrix),
        "matrix_file_ref": {
            "relative_path": matrix_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "content_hash": file_hash(matrix_path),
        },
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "preparation": {},
        "tasks": {},
        "result_provenance_ref": None,
    }


def load_or_create_state(
    path: Path,
    matrix: Mapping[str, Any],
    matrix_path: Path,
    resume: bool,
) -> dict[str, Any]:
    if path.exists():
        if not resume:
            raise ImmutableConflict(f"{path} exists; use --resume or a new run root")
        state = require_object(load_json(path), "execution index")
        if (
            state.get("runner_version") != RUNNER_VERSION
            or state.get("matrix_id") != matrix["matrix_id"]
            or state.get("matrix_content_hash") != content_hash(matrix)
        ):
            raise ImmutableConflict("Execution index does not match this Runner/matrix")
        return state
    if resume:
        raise ConfigurationError(f"Cannot resume missing execution index: {path}")
    state = initial_state(matrix, matrix_path)
    write_json(path, state)
    return state


def persist_state(path: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = utc_now()
    write_json(path, state)


def run_builder_step(
    *,
    state_path: Path,
    state: dict[str, Any],
    step_state: dict[str, Any],
    step_name: str,
    argv: list[str],
    log_root: Path,
    output_reader: Any,
) -> Path:
    existing = step_state.get(step_name)
    if isinstance(existing, dict) and existing.get("status") == "success":
        path = Path(require_string(existing.get("output_path"), "saved output_path"))
        if not path.is_file():
            raise ImmutableConflict(f"Saved Builder output is missing: {path}")
        declared_hash = require_string(
            existing.get("output_file_hash"),
            "saved output_file_hash",
        )
        actual_hash = file_hash(path)
        if actual_hash != declared_hash:
            raise ImmutableConflict(
                f"Saved Builder output hash mismatch: {actual_hash} != {declared_hash}"
            )
        return path
    if any(key.startswith(f'{step_name}_failed_') for key in step_state):
        raise RunnerError(f'{step_name} has a terminal failed attempt; resume cannot replenish its method budget')

    attempt_number = 1 + sum(
        1 for key in step_state if key.startswith(f"{step_name}_failed_")
    )
    attempt_dir = log_root / step_name / f"attempt_{attempt_number:03d}"
    result_path = attempt_dir / "builder_result.json"
    command = [*argv, '--result-json', str(result_path)]
    if attempt_dir.exists():
        if not result_path.is_file() or not (attempt_dir / 'process_result.json').is_file():
            raise RunnerError(f'Interrupted {step_name} attempt cannot be retried with an unknown response budget')
        if load_json(attempt_dir / 'command.json')['argv'] != command:
            raise ImmutableConflict('Saved Builder command differs')
        process = load_json(attempt_dir / 'process_result.json')
    else:
        process = run_command(command, attempt_dir)
    try:
        result = load_builder_result(result_path, step_name)
        if process["returncode"] != 0:
            raise RunnerError(f"{step_name} returned {process['returncode']}: {result}")
        output = output_reader(result)
    except RunnerError as exc:
        step_state[f"{step_name}_failed_{attempt_number:03d}"] = {
            "status": "failed",
            "message": str(exc),
            "attempt_dir": str(attempt_dir),
        }
        persist_state(state_path, state)
        raise

    step_state[step_name] = {
        "status": "success",
        "output_path": str(output),
        "output_file_hash": file_hash(output),
        "attempt_dir": str(attempt_dir),
        "finished_at": process["finished_at"],
    }
    persist_state(state_path, state)
    return output


def preflight(
    matrix: Mapping[str, Any],
    values: Mapping[str, Any],
    attempt_dir: Path,
) -> Path:
    template = matrix["execution"]["runner_adapters"]["preflight_argv_template"]
    result_path = attempt_dir / "adapter_result.json"
    process_path = attempt_dir / "process_result.json"
    if result_path.is_file() and process_path.is_file():
        result = require_object(load_json(result_path), "saved preflight result")
        process = require_object(load_json(process_path), "saved preflight process")
        if process.get("returncode") != 0 or result.get("status") != "passed":
            raise RunnerError(f"Saved preflight failed: {result}")
        return result_path
    argv = expand_argv(template, {**values, "result_json": result_path})
    argv.extend(resource_limit_arguments(matrix))
    process = run_command(argv, attempt_dir)
    if not result_path.is_file():
        raise RunnerError(f"Preflight adapter produced no result (exit {process['returncode']}); see {attempt_dir / 'stderr.log'}")
    result = require_object(load_json(result_path), "preflight result")
    if process["returncode"] != 0 or result.get("status") != "passed":
        raise RunnerError(f"Preflight failed: {result}")
    return result_path


def repository_file_reference(path: Path) -> dict[str, str]:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(REPOSITORY_ROOT.resolve())
    except ValueError as exc:
        raise RunnerError(f"Evidence file is outside the repository: {path}") from exc
    if not resolved.is_file():
        raise RunnerError(f"Evidence file does not exist: {path}")
    return {"relative_path": relative.as_posix(), "content_hash": file_hash(resolved)}


def default_branch_spec_hash(path: Path) -> str:
    record = require_object(load_json(path), f"HarnessSpec {path}")
    plan = require_object(record.get("exploration_plan"), "exploration_plan")
    branches = plan.get("branches")
    if not isinstance(branches, list):
        raise RunnerError("HarnessSpec exploration_plan.branches must be an array")
    defaults = [
        branch
        for branch in branches
        if isinstance(branch, dict) and branch.get("branch_kind") == "default"
    ]
    if len(defaults) != 1:
        raise RunnerError("HarnessSpec must contain exactly one default Branch")
    projection = dict(defaults[0])
    projection.pop("budget_share", None)
    return content_hash(projection)


def default_branch_strategy_hash(spec_path: Path, strategy_path: Path) -> str:
    spec = require_object(load_json(spec_path), f"HarnessSpec {spec_path}")
    default_id = require_string(
        require_object(spec.get("exploration_plan"), "exploration_plan").get(
            "default_branch_id"
        ),
        "default_branch_id",
    )
    strategy = require_object(load_json(strategy_path), f"Strategy {strategy_path}")
    implementation = require_object(
        strategy.get("implementation_plan"), "implementation_plan"
    )
    branches = implementation.get("branch_strategies")
    if not isinstance(branches, list):
        raise RunnerError("Strategy branch_strategies must be an array")
    defaults = [
        branch
        for branch in branches
        if isinstance(branch, dict) and branch.get("source_branch_id") == default_id
    ]
    if len(defaults) != 1:
        raise RunnerError("Strategy must implement exactly one default Branch")
    return content_hash(defaults[0])


def prepare_approved_group(matrix, entry, group_id, state_path, state, run_root, python):
    sys.path.insert(0, str(SPEC_BUILDER.parent))
    from budget_derivation import authorize
    binding = entry.get('approved_inputs', {}).get(group_id)
    if not isinstance(binding, dict):
        raise ConfigurationError(f'Missing approved inputs for {entry["api_id"]}/{group_id}')
    paths = {key: verify_file_reference(binding[key], key) for key in ('spec_file_ref', 'spec_review_file_ref', 'strategy_file_ref', 'strategy_review_file_ref')}
    try:
        authorize(paths['spec_review_file_ref'], paths['spec_file_ref'], 'spec')
        authorize(paths['strategy_review_file_ref'], paths['strategy_file_ref'], 'strategy')
    except ValueError as exc:
        raise ConfigurationError(str(exc)) from exc
    step = state['preparation'][entry['api_id']][group_id]
    spec, plan = paths['spec_file_ref'], paths['strategy_file_ref']
    expected = 'controlled_baseline' if group_id == 'structured_baseline' else 'bug_aware_static'
    if load_json(spec)['identity']['spec_mode'] != expected or load_json(spec)['identity']['target_api'] != entry['api_id']:
        raise ConfigurationError('Approved inputs are outside the frozen group/API scope')
    spec_hash, plan_hash = default_branch_spec_hash(spec), default_branch_strategy_hash(spec, plan)
    if group_id == 'bug_aware_static':
        baseline = state['preparation'][entry['api_id']].get('structured_baseline', {})
        if baseline.get('status') != 'success':
            raise ConfigurationError('Approved static preparation requires successful baseline preparation')
        if (spec_hash, plan_hash) != (baseline.get('default_branch_spec_hash'), baseline.get('default_branch_strategy_hash')):
            raise ConfigurationError('Approved static default branch differs from approved baseline')
    root = run_root / 'prepare' / safe_component(entry['api_id']) / group_id
    artifact = run_builder_step(state_path=state_path, state=state, step_state=step, step_name='harness_artifact',
        argv=[python, str(ARTIFACT_BUILDER), '--strategy-plan', str(plan), '--strategy-review', str(paths['strategy_review_file_ref']),
              '--harness-spec-root', str(spec.parent), '--evaluation-target-manifest', str(evaluation_target_manifest(matrix)),
              '--compile-config', str(verify_file_reference(entry['compile_profile_file_ref'], 'compile profile')),
              '--output-root', str(root / 'harnesses')], log_root=root / 'attempts', output_reader=artifact_output_path)
    preflight(matrix, {'harness_record': artifact, 'strategy_plan': plan, 'harness_spec': spec,
                      'api_id': entry['api_id'], 'target_api': entry['api_id'], 'group_id': group_id}, root / 'attempts/preflight/attempt_001')
    step.update(status='success', preparation_method='reuse_approved_not_new_synthesis', spec_path=str(spec), strategy_path=str(plan),
                artifact_path=str(artifact), default_branch_spec_hash=spec_hash, default_branch_strategy_hash=plan_hash,
                spec_authorization_path=str(paths['spec_review_file_ref']), strategy_authorization_path=str(paths['strategy_review_file_ref']),
                preflight={'status': 'passed'})
    persist_state(state_path, state)
    return step


def find_authorization(state, subject_path, kind):
    sys.path.insert(0, str(SPEC_BUILDER.parent))
    from budget_derivation import authorize, canonical
    subject_record = load_json(subject_path)
    matches = []
    for ref in state.get('authorization_records', []):
        path = verify_file_reference(ref, 'authorization')
        record = load_json(path)
        if record.get('subject', {}).get('content_hash') == canonical(subject_record):
            try:
                authorize(path, subject_path, kind)
            except ValueError as exc:
                raise ConfigurationError(str(exc)) from exc
            matches.append(path)
    if len(matches) > 1: raise ConfigurationError('Ambiguous exact authorization')
    return matches[0] if matches else None


def prepare_group(
    matrix: Mapping[str, Any],
    entry: Mapping[str, Any],
    group_id: str,
    state_path: Path,
    state: dict[str, Any],
    run_root: Path,
    python: str,
) -> dict[str, Any]:
    groups = group_map(matrix)
    group = groups[group_id]
    profile, profile_path = api_profile(entry)
    target_api = profile["target"]["python_api"]
    api_state = state["preparation"].setdefault(entry["api_id"], {})
    step_state = api_state.setdefault(group_id, {})

    if group["harness_spec_builder_mode"] == "reuse_bug_aware_static_h0":
        static = api_state.get("bug_aware_static")
        if not isinstance(static, dict) or static.get("status") != "success":
            raise RunnerError("Adaptive H0 requires completed Static preparation")
        triplet = {
            key: static[key]
            for key in (
                "spec_path",
                "strategy_path",
                "artifact_path",
                "default_branch_spec_hash",
                "default_branch_strategy_hash",
            )
        }
        for key in ('spec_authorization_path', 'strategy_authorization_path'):
            if key in static: triplet[key] = static[key]
        step_state.update(
            {
                **triplet,
                "status": "success",
                "reuse_source_group": "bug_aware_static",
                "reused_exact_triplet_hash": content_hash(triplet),
            }
        )
        persist_state(state_path, state)
        return step_state

    if matrix.get('preparation', {}).get('mode') == 'reuse_approved':
        return prepare_approved_group(matrix, entry, group_id, state_path, state, run_root, python)

    mode = require_string(
        group.get("harness_spec_builder_mode"),
        f"core_groups[{group_id}].harness_spec_builder_mode",
    )
    operation_root = (
        run_root / "prepare" / safe_component(entry["api_id"]) / group_id
    )
    model_args = model_arguments(matrix)
    max_attempts = matrix["synthesis"]["harness_spec"][
        "maximum_completed_responses"
    ]
    helper_set_path = helper_profile_set(matrix)
    baseline = api_state.get("structured_baseline")
    canonical_spec_args: list[str] = []
    canonical_strategy_args: list[str] = []
    if group_id == "bug_aware_static":
        if not isinstance(baseline, dict) or baseline.get("status") != "success":
            raise RunnerError("Static preparation requires completed Baseline preparation")
        canonical_spec_args = [
            "--canonical-default-spec",
            require_string(baseline.get("spec_path"), "baseline spec_path"),
        ]
        canonical_strategy_args = [
            "--canonical-default-strategy",
            require_string(baseline.get("strategy_path"), "baseline strategy_path"),
            '--canonical-default-strategy-review', require_string(baseline.get('strategy_authorization_path'), 'baseline Strategy authorization'),
        ]

    spec_path = run_builder_step(
        state_path=state_path,
        state=state,
        step_state=step_state,
        step_name="harness_spec",
        argv=[
            python,
            str(SPEC_BUILDER),
            "--target-api",
            target_api,
            "--api-profile",
            str(profile_path),
            "--helper-profile-set",
            str(helper_set_path),
            "--mode",
            mode,
            "--max-attempts",
            str(max_attempts),
            *canonical_spec_args,
            *(frozen_knowledge_arguments(entry, matrix) if group_id == "bug_aware_static" else []),
            *model_args,
            "--output-root",
            str(operation_root / "harness_specs"),
        ],
        log_root=operation_root / "attempts",
        output_reader=lambda result: builder_output_path(result, "HarnessSpec Builder"),
    )

    spec_authorization = find_authorization(state, spec_path, 'spec')
    if spec_authorization is None:
        step_state.update(status='awaiting_review', pending_subject=str(spec_path))
        persist_state(state_path, state)
        return step_state

    strategy_attempts = matrix["synthesis"]["strategy"][
        "maximum_completed_responses"
    ]
    strategy_path = run_builder_step(
        state_path=state_path,
        state=state,
        step_state=step_state,
        step_name="strategy",
        argv=[
            python,
            str(STRATEGY_BUILDER),
            "--harness-spec",
            str(spec_path),
            '--harness-spec-review', str(spec_authorization),
            "--max-attempts",
            str(strategy_attempts),
            *canonical_strategy_args,
            *model_args,
            "--output-root",
            str(operation_root / "strategy_plans"),
        ],
        log_root=operation_root / "attempts",
        output_reader=strategy_output_path,
    )
    strategy_authorization = find_authorization(state, strategy_path, 'strategy')
    if strategy_authorization is None:
        step_state.update(status='awaiting_review', pending_subject=str(strategy_path))
        persist_state(state_path, state)
        return step_state

    default_spec_hash = default_branch_spec_hash(spec_path)
    default_strategy_hash = default_branch_strategy_hash(spec_path, strategy_path)
    if group_id == "bug_aware_static":
        for field, value in (
            ("default_branch_spec_hash", default_spec_hash),
            ("default_branch_strategy_hash", default_strategy_hash),
        ):
            if value != baseline.get(field):
                raise RunnerError(
                    f"Static {field} differs from the controlled baseline"
                )

    compile_path = verify_file_reference(
        entry.get("compile_profile_file_ref"),
        f"api_entries[{entry['api_id']}].compile_profile_file_ref",
    )
    target_manifest_path = evaluation_target_manifest(matrix)
    artifact_path = run_builder_step(
        state_path=state_path,
        state=state,
        step_state=step_state,
        step_name="harness_artifact",
        argv=[
            python,
            str(ARTIFACT_BUILDER),
            "--strategy-plan",
            str(strategy_path),
            '--strategy-review', str(strategy_authorization),
            "--harness-spec-root",
            str(operation_root / "harness_specs"),
            "--evaluation-target-manifest",
            str(target_manifest_path),
            "--compile-config",
            str(compile_path),
            "--output-root",
            str(operation_root / "harnesses"),
        ],
        log_root=operation_root / "attempts",
        output_reader=artifact_output_path,
    )

    preflight_state = step_state.get("preflight")
    if not isinstance(preflight_state, dict) or preflight_state.get("status") != "passed":
        attempt_dir = operation_root / "attempts" / "preflight" / "attempt_001"
        preflight(
            matrix,
            {
                "api_id": entry["api_id"],
                "target_api": target_api,
                "group_id": group_id,
                "harness_record": artifact_path,
                "strategy_plan": strategy_path,
                "harness_spec": spec_path,
            },
            attempt_dir,
        )
        step_state["preflight"] = {
            "status": "passed",
            "attempt_dir": str(attempt_dir),
            "finished_at": utc_now(),
        }

    step_state.update(
        {
            "status": "success",
            "target_api": target_api,
            "spec_path": str(spec_path),
            "strategy_path": str(strategy_path),
            "artifact_path": str(artifact_path),
            "triplet_hash": content_hash(
                {
                    "spec_path": str(spec_path),
                    "strategy_path": str(strategy_path),
                    "artifact_path": str(artifact_path),
                }
            ),
            "default_branch_spec_hash": default_spec_hash,
            "default_branch_strategy_hash": default_strategy_hash,
            'spec_authorization_path': str(spec_authorization),
            'strategy_authorization_path': str(strategy_authorization),
        }
    )
    persist_state(state_path, state)
    return step_state


def prepare_all(
    matrix: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    state_path: Path,
    state: dict[str, Any],
    run_root: Path,
    python: str,
) -> None:
    # Check every API before the first paid generation. Historical execute/finalize
    # paths do not enter this preparation-only gate.
    for entry in entries:
        frozen_knowledge_arguments(entry, matrix)
        validate_target_knowledge_bindings(matrix, entry)
    for entry in entries:
        for group_id in GROUP_IDS:
            try:
                prepare_group(matrix, entry, group_id, state_path, state, run_root, python)
            except RunnerError as exc:
                state['preparation'].setdefault(entry['api_id'], {}).setdefault(group_id, {}).update(status='failed', message=str(exc))
                persist_state(state_path, state)


def initial_corpus_record(entry: Mapping[str, Any]) -> Path:
    _, path = resolve_artifact_binding(
        entry.get("initial_corpus_binding"),
        f"api_entries[{entry['api_id']}].initial_corpus_binding",
    )
    return path


def prior_round_corpus(
    task: Task,
    state: Mapping[str, Any],
    initial: Path,
) -> Path:
    if task.round_index == 1:
        return initial
    prior_key = ":".join(
        (
            task.api_id,
            task.group_id,
            f"repeat_{task.repeat_id:03d}",
            f"round_{task.round_index - 1:03d}",
        )
    )
    prior = require_object(state["tasks"].get(prior_key), f"prior task {prior_key}")
    prior_status = prior.get("status")
    if prior_status not in {"completed", "completed_with_abnormal_events"}:
        raise RunnerError(
            f"Cannot execute {task.key}; prior round {prior_key} did not "
            f"complete successfully (status={prior_status!r})"
        )
    return repository_path(
        require_string(prior.get("round_end_corpus_record"), "round_end_corpus_record")
    )


def round_attempt_paths(
    operation_root: Path, attempt_number: int
) -> tuple[Path, Path]:
    name = f"attempt_{attempt_number:03d}"
    return operation_root / name, operation_root / "runner_processes" / name


def structured_round_result(path: Path) -> dict[str, Any]:
    result = require_object(load_json(path), "round adapter result")
    status = result.get("status")
    if status not in {
        "completed",
        "budget_incomplete",
        "target_or_framework_exit",
        "infrastructure_failure",
        "method_failure",
    }:
        raise RunnerError(f"Unsupported round result status: {status!r}")
    require_string(result.get("terminal_at"), "round result terminal_at")
    consumed = result.get("active_seconds_consumed")
    remaining = result.get("remaining_active_seconds")
    for value, label in (
        (consumed, "active_seconds_consumed"),
        (remaining, "remaining_active_seconds"),
    ):
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise RunnerError(f"round result {label} must be non-negative")
    return result


def active_triplet(state: dict[str, Any], task: Task) -> dict[str, Any]:
    prepared = require_object(
        state["preparation"][task.api_id][task.group_id],
        f"prepared {task.api_id}/{task.group_id}",
    )
    if task.group_id != "bug_aware_adaptive":
        return prepared
    by_api = state.setdefault("adaptive_current", {}).setdefault(task.api_id, {})
    repeat_key = f"repeat_{task.repeat_id:03d}"
    current = by_api.get(repeat_key)
    if current is None:
        current = {
            key: prepared[key]
            for key in ("spec_path", "strategy_path", "artifact_path")
        }
        for key in ('spec_authorization_path', 'strategy_authorization_path'):
            if key in prepared: current[key] = prepared[key]
        current["status"] = "success"
        by_api[repeat_key] = current
    return require_object(current, "adaptive current triplet")



def file_reference(path: Path) -> dict[str, str]:
    resolved = path.resolve()
    if not resolved.is_relative_to(REPOSITORY_ROOT):
        raise ConfigurationError(f"Output path escapes repository: {resolved}")
    return {
        "relative_path": resolved.relative_to(REPOSITORY_ROOT).as_posix(),
        "content_hash": file_hash(resolved),
    }


def runner_reference() -> dict[str, Any]:
    return {
        "artifact_id": "run_experiment_matrix",
        "artifact_version": RUNNER_VERSION,
        "content_hash": file_hash(Path(__file__).resolve()),
    }


def materialize_selected_round(
    fragments: Sequence[Mapping[str, Any]],
    operation_root: Path,
    task: Task,
) -> tuple[Path, Path | None]:
    records: list[dict[str, Any]] = []
    bundles: list[dict[str, Any]] = []
    direct_round_path: Path | None = None
    direct_bundle_path: Path | None = None
    round_paths = []
    bundle_paths = []
    for fragment in fragments:
        if fragment.get('excluded_from_primary'):
            continue
        result = require_object(fragment.get("adapter_result"), "fragment adapter_result")
        round_ref = result.get("round_record_file_ref")
        if round_ref is None:
            continue
        round_path = verify_file_reference(round_ref, "fragment round record")
        direct_round_path = round_path
        record = require_object(load_json(round_path), "fragment round record")
        records.append(record)
        round_paths.append(round_path)
        binding = result.get("candidate_bundle_binding")
        if binding is not None:
            bundle, bundle_path = resolve_artifact_binding(binding, "candidate_bundle_binding")
            direct_bundle_path = bundle_path
            if bundle.get("record_type") != "candidate_bundle":
                raise ConfigurationError("Candidate binding does not identify a Candidate Bundle")
            bundles.append(bundle)
            bundle_paths.append(bundle_path)
    if not records or direct_round_path is None:
        raise ConfigurationError(f"No Fuzzing Round record is available for {task.key}")
    if len(records) == 1:
        return direct_round_path, direct_bundle_path

    selected = json.loads(json.dumps(records[-1]))
    capture_rows = []
    for record in records:
        item = record["evidence"]["candidate_evidence"]
        ref = item.get("capture_summary_file_ref")
        summary = item.get("capture_summary")
        if ref is not None and summary is not None:
            capture_rows.append({"file_ref": ref, "capture_summary": summary})
    if capture_rows:
        counts = [r["capture_summary"]["counts"] for r in capture_rows]
        complete_capture = all(c is not None for c in counts)
        capture_limit = capture_rows[0]["capture_summary"]["limit_per_kind"]
        if any(r["capture_summary"]["limit_per_kind"] != capture_limit for r in capture_rows):
            raise ConfigurationError("Candidate capture limits differ across restarted attempts")
        merged_counts = None
        if complete_capture:
            merged_counts = {key: sum(c[key] for c in counts) for key in
                ("attempts", "saved", "failures", "exception_attempts", "oracle_attempts")}
            merged_counts.update(limit_per_kind=capture_limit, complete=all(c["complete"] for c in counts))
        selected["evidence"]["candidate_evidence"].update(
            capture_summary={"sampling": "first_n_per_kind_per_process", "limit_per_kind": capture_limit,
                             "counts": merged_counts, "state": "merged" if complete_capture else "unavailable_after_exit"},
            capture_summary_file_ref=None, process_capture_summaries=capture_rows)
    selected["execution"]["started_at"] = records[0]["execution"]["started_at"]
    selected["execution"]["actual_duration_seconds"] = round(
        sum(float(item["execution"]["actual_duration_seconds"]) for item in records), 6
    )
    selected["attempt_selection"] = {
        "status": "selected_as_round_result",
        "reason_code": "deterministic_preference",
    }
    logs = {
        json.dumps(ref, sort_keys=True): ref
        for record in records
        for ref in record["evidence"]["run_log_refs"]
    }
    selected["evidence"]["run_log_refs"] = [logs[key] for key in sorted(logs)]
    selected['evidence']['process_fragment_refs'] = [file_reference(path) for path in round_paths]
    snapshots = []
    for record in records:
        evidence = record['evidence'].get('runtime_snapshot')
        if evidence and evidence['status'] == 'present':
            path = verify_file_reference(evidence['location']['file_ref'], 'fragment snapshot')
            snapshots.append(load_json(path))
    if snapshots:
        merged = json.loads(json.dumps(snapshots[-1]))
        for snapshot in snapshots:
            if any(snapshot[k] != merged[k] for k in ('artifact_id', 'generation_key', 'site_count', 'runtime_version', 'record_format_version')):
                raise ConfigurationError('Cannot merge different instrumentation layouts')
        for field in ('started_iterations', 'finished_iterations', 'unwound_iterations', 'invalid_site_records', 'export_failures'):
            merged[field] = sum(s[field] for s in snapshots)
        merged['site_counts'] = [sum(s['site_counts'][i] for s in snapshots) for i in range(merged['site_count'])]
        complete = len(snapshots) == len(records) and all(s['snapshot_kind'] == 'final' for s in snapshots)
        merged['snapshot_kind'] = 'final' if complete else 'periodic'
        snapshot_path = operation_root / 'runtime_snapshot.json'
        write_or_verify_immutable_json(snapshot_path, merged)
        selected['evidence']['runtime_snapshot'] = {'status': 'present', 'snapshot_kind': merged['snapshot_kind'],
            'staleness_iterations': 0 if complete else None,
            'location': {'file_ref': file_reference(snapshot_path), 'artifact_ref': {'artifact_id': 'merged_snapshot_' + content_hash(merged)[:20], 'artifact_version': merged['record_format_version'], 'content_hash': content_hash(merged)}}}
    budgets = [r['execution'].get('budget') for r in records]
    if all(budgets):
        measured = all(b['process_seconds'] is not None for b in budgets)
        seconds = sum(b['process_seconds'] for b in budgets) if measured else None
        planned = budgets[0]['planned_seconds']
        selected['record_format_version'] = '1.1'
        selected['schedule']['planned_duration_seconds'] = records[0]['schedule']['planned_duration_seconds']
        selected['execution']['budget'] = {'planned_seconds': planned, 'process_seconds': seconds,
            'remaining_seconds': max(0.0, planned - seconds) if measured else None,
            'timing_status': 'merged', 'all_process_durations_measured': measured}

    bundle_path = None
    if bundles:
        candidates = [candidate for bundle in bundles for candidate in bundle["candidates"]]
        candidate_ids = [item["candidate_id"] for item in candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ConfigurationError("Candidate IDs collide across restarted attempts")
        observations = [
            observation
            for record in records
            for observation in record["evidence"]["candidate_evidence"]["observations"]
        ]
        if sorted(item["candidate_id"] for item in observations) != sorted(candidate_ids):
            raise ConfigurationError("Candidate Bundle and Round observations disagree")
        candidates.sort(key=lambda item: item["candidate_id"])
        observations.sort(key=lambda item: item["candidate_id"])
        bundle_id = "cb_" + content_hash({"task_key": task.key, "candidates": candidates})[:20]
        bundle = {
            "record_format_version": "1.1",
            "record_type": "candidate_bundle",
            "identity": {"bundle_id": bundle_id, "artifact_version": 1},
            "round_context": {
                "task_key": task.key,
                "api_id": task.api_id,
                "target_api_id": task.target_api,
                "experimental_group": task.group_id,
                "repeat_id": task.canonical_repeat_id,
                "round_index": task.round_index,
                "attempt_index": selected["identity"]["attempt_index"],
                "execution_id": selected["identity"]["execution_id"],
            },
            "candidates": candidates,
            "provenance": {
                "producer_ref": runner_reference(),
                "generated_at": selected["execution"]["ended_at"],
            },
            'capture_summary': {'sampling': 'first_n_per_kind_per_process', 'limit_per_kind': bundles[-1].get('capture_summary', {}).get('limit_per_kind', 64), 'counts': None, 'state': 'merged'},
            'process_capture_summaries': [{'bundle_file_ref': file_reference(path), 'capture_summary': b.get('capture_summary')} for path, b in zip(bundle_paths, bundles)],
        }
        bundle_path = operation_root / "candidate_bundle.json"
        write_or_verify_immutable_json(bundle_path, bundle)
        selected["evidence"]["candidate_evidence"].update({
            "status": "present",
            "bundle_ref": {
                "artifact_id": bundle_id,
                "artifact_version": 1,
                "content_hash": content_hash(bundle),
            },
            "bundle_file_ref": file_reference(bundle_path),
            "observations": observations,
        })
    selected["provenance"] = {
        "runner_artifact_ref": runner_reference(),
        "generated_at": selected["execution"]["ended_at"],
    }
    selected_path = operation_root / "fuzzing_round_record.json"
    write_or_verify_immutable_json(selected_path, selected)
    return selected_path, bundle_path

def isolate_terminating_input(result, operation_root, corpus_path):
    binding = result.get('candidate_bundle_binding')
    if not binding:
        return corpus_path
    bundle, bundle_path = resolve_artifact_binding(binding, 'isolation candidate bundle')
    candidates = [c for c in bundle['candidates'] if c['observation_kind'] in {'crash', 'sanitizer', 'resource_anomaly'}
                  and Path(c['triggering_input']['file_ref']['relative_path']).parent.name == 'candidates']
    hashes = {c['triggering_input']['file_ref']['content_hash'] for c in candidates}
    if not hashes:
        return corpus_path
    corpus = load_json(corpus_path)
    filtered = [f for f in corpus['files'] if f['file_ref']['content_hash'] not in hashes]
    key = content_hash({'bundle': binding, 'corpus': file_reference(corpus_path)})[:20]
    output = operation_root / ('isolated_corpus_' + key + '.json')
    corpus['files'] = filtered
    corpus['source']['parent_manifest_file_ref'] = file_reference(corpus_path)
    corpus['provenance']['generator_ref'] = runner_reference()
    write_or_verify_immutable_json(output, corpus)
    write_or_verify_immutable_json(operation_root / ('isolation_' + key + '.json'), {
        'candidate_bundle_file_ref': file_reference(bundle_path), 'parent_corpus_file_ref': file_reference(corpus_path),
        'derived_corpus_file_ref': file_reference(output), 'excluded_input_hashes': sorted(hashes),
        'reason': 'terminating_libfuzzer_artifact_only', 'original_evidence_deleted': False})
    return output


def execute_task(
    matrix: Mapping[str, Any],
    entry: Mapping[str, Any],
    task: Task,
    state_path: Path,
    state: dict[str, Any],
    run_root: Path,
) -> None:
    existing = state["tasks"].get(task.key)
    if isinstance(existing, dict) and existing.get("status") in TERMINAL_TASK_STATUSES:
        return

    prepared = active_triplet(state, task)
    if prepared.get("status") != "success":
        state['tasks'][task.key] = {'status': 'method_failed', 'seed': task.seed, 'terminal_at': utc_now(), 'message': 'Preparation failed or is awaiting review'}
        persist_state(state_path, state)
        return

    total_budget = matrix["execution"]["active_fuzzing_seconds_per_round"]
    original_corpus = prior_round_corpus(
        task,
        state,
        initial_corpus_record(entry),
    )
    current_corpus = original_corpus
    remaining = float(total_budget)
    retry_policy = matrix["failure_handling"]["infrastructure_retry"]
    abnormal_policy = matrix["failure_handling"]["abnormal_exit"]
    maximum_infra = retry_policy["maximum_retries_per_operation"]
    maximum_restarts = abnormal_policy["maximum_process_restarts_per_round"]
    retryable = set(retry_policy["retryable_categories"])
    fragments = (
        list(existing.get("fragments", []))
        if isinstance(existing, dict)
        else []
    )
    infra_attempt = (existing or {}).get('infrastructure_retry_count', sum(
        item.get("adapter_result", {}).get("status") == "infrastructure_failure"
        for item in fragments
    ))
    process_restart = (existing or {}).get('restart_count', sum(
        item.get("adapter_result", {}).get("status") == "target_or_framework_exit"
        for item in fragments
    ))
    if fragments and fragments[-1]["adapter_result"]["status"] == "target_or_framework_exit":
        last = fragments[-1]["adapter_result"]
        remaining = float(last["remaining_active_seconds"])
        _, current_corpus = resolve_artifact_binding(last.get("resume_corpus_binding"), "resume_corpus_binding")
    operation_root = run_root / "rounds" / task.key.replace(":", "/")
    pending = existing.get('pending_attempt') if isinstance(existing, dict) else None
    if pending:
        remaining = float(pending['reserved_seconds'])
        current_corpus = verify_file_reference(pending['corpus_file_ref'], 'pending start corpus')

    while True:
        attempt_number = pending['attempt_number'] if pending else len(fragments) + 1
        attempt_dir, process_dir = round_attempt_paths(
            operation_root, attempt_number
        )
        if not pending and (attempt_dir.exists() or process_dir.exists()):
            raise ImmutableConflict('Unregistered attempt exists; reconcile its operation identity instead of rerunning')
        result_path = attempt_dir / "adapter_result.json"
        values = {
            "api_id": task.api_id,
            "target_api": task.target_api,
            "group_id": task.group_id,
            "repeat_id": task.canonical_repeat_id,
            "repeat_index": task.repeat_id,
            "round_id": task.canonical_round_id,
            "round_index": task.round_index,
            "task_key": task.key,
            "seed": task.seed,
            "active_seconds": remaining,
            "planned_final_round_index": matrix["execution"]["round_count"],
            "attempt_index": attempt_number,
            "harness_record": prepared["artifact_path"],
            "strategy_plan": prepared["strategy_path"],
            "harness_spec": prepared["spec_path"],
            "round_start_corpus_record": current_corpus,
            "result_json": result_path,
            "attempt_dir": attempt_dir,
        }
        argv = round_adapter_argv(matrix, values)
        operation_key = content_hash({'argv': argv, 'matrix': content_hash(matrix), 'corpus': file_reference(current_corpus)})
        if pending and pending['operation_key'] != operation_key:
            raise ImmutableConflict('Pending operation inputs changed')
        if not pending:
            pending = {'attempt_number': attempt_number, 'reserved_seconds': remaining,
                       'corpus_file_ref': file_reference(current_corpus), 'operation_key': operation_key}
            state['tasks'][task.key] = {'status': 'in_progress', 'seed': task.seed, 'fragments': fragments,
                                       'pending_attempt': pending, 'restart_count': process_restart,
                                       'infrastructure_retry_count': infra_attempt}
            persist_state(state_path, state)
        coverage_enabled = matrix["coverage"]["enabled"]
        process_path = process_dir / 'process_result.json'
        if result_path.is_file() and process_path.is_file():
            if load_json(process_dir / 'command.json')['argv'] != argv:
                raise ImmutableConflict('Saved process command changed')
            process = load_json(process_path)
        elif process_dir.exists():
            state['tasks'][task.key].update(status='infrastructure_failed', terminal_at=utc_now(), message='Interrupted operation lacks a complete result; budget is reserved, no automatic rerun')
            persist_state(state_path, state)
            return
        else:
            process = run_command(argv, process_dir,
                timeout_seconds=max(int(remaining) + (3600 if coverage_enabled else 120), 180),
                environment=matrix["execution"].get("thread_environment"))
        if not result_path.is_file():
            raise RunnerError(
                f"Round adapter failed without structured result: {task.key}"
            )
        result = structured_round_result(result_path)
        fragment = {
            "attempt_number": attempt_number,
            "process": process,
            "adapter_result": result,
        }
        if not fragments or fragments[-1]['attempt_number'] != attempt_number:
            fragments.append(fragment)
        state["tasks"][task.key] = {
            "status": "in_progress",
            "seed": task.seed,
            "fragments": fragments,
            "updated_at": result["terminal_at"],
            'pending_attempt': pending, 'restart_count': process_restart,
            'infrastructure_retry_count': infra_attempt,
        }
        persist_state(state_path, state)

        status = result["status"]
        if status in {"completed", "budget_incomplete"}:
            end_binding = result.get("round_end_corpus_binding")
            _, end_path = resolve_artifact_binding(
                end_binding,
                "round_end_corpus_binding",
            )
            verify_file_reference(
                result.get("round_record_file_ref"),
                "round result round_record_file_ref",
            )
            round_record_path, candidate_bundle_path = materialize_selected_round(
                fragments, operation_root, task
            )
            selected_record = load_json(round_record_path)
            runtime_snapshot_ref = selected_record.get('evidence', {}).get('runtime_snapshot', {}).get('location')
            runtime_snapshot_ref = None if runtime_snapshot_ref is None else runtime_snapshot_ref['file_ref']
            runtime_snapshot_path = (
                None if runtime_snapshot_ref is None
                else verify_file_reference(runtime_snapshot_ref, "runtime snapshot")
            )
            state["tasks"][task.key] = {
                "status": (
                    'budget_incomplete' if status == 'budget_incomplete' else
                    "completed_with_abnormal_events"
                    if process_restart
                    else "completed"
                ),
                "seed": task.seed,
                "fragments": fragments,
                "round_end_corpus_record": end_path.relative_to(
                    REPOSITORY_ROOT
                ).as_posix(),
                "terminal_at": result["terminal_at"],
                "round_record_path": str(round_record_path),
                "runtime_snapshot_path": None if runtime_snapshot_path is None else str(runtime_snapshot_path),
                "candidate_bundle_path": None if candidate_bundle_path is None else str(candidate_bundle_path),
            }
            persist_state(state_path, state)
            return

        if status == "method_failure":
            state["tasks"][task.key] = {
                "status": "method_failed",
                "seed": task.seed,
                "fragments": fragments,
                "terminal_at": result["terminal_at"],
            }
            persist_state(state_path, state)
            return
        if status == "infrastructure_failure":
            category = result.get("failure_category")
            if category not in retryable or infra_attempt >= maximum_infra:
                state['tasks'][task.key].update(status='infrastructure_failed', terminal_at=result['terminal_at'])
                persist_state(state_path, state)
                return
            infra_attempt += 1
            for fragment in fragments:
                fragment['excluded_from_primary'] = True
            current_corpus = original_corpus
            remaining = float(total_budget)
            pending = None
            continue

        exhausted = process_restart >= maximum_restarts
        remaining = float(result["remaining_active_seconds"])
        if exhausted or remaining <= 0 or result.get('budget_timing_status') == 'unknown_budget_reserved_no_retry':
            end_binding = result.get("resume_corpus_binding")
            _, end_path = resolve_artifact_binding(end_binding, "resume_corpus_binding")
            round_record_path, candidate_bundle_path = materialize_selected_round(
                fragments, operation_root, task
            )
            selected_record = load_json(round_record_path)
            runtime_snapshot_ref = selected_record.get('evidence', {}).get('runtime_snapshot', {}).get('location')
            runtime_snapshot_ref = None if runtime_snapshot_ref is None else runtime_snapshot_ref['file_ref']
            runtime_snapshot_path = (
                None if runtime_snapshot_ref is None
                else verify_file_reference(runtime_snapshot_ref, "runtime snapshot")
            )
            state["tasks"][task.key] = {
                "status": "completed_with_abnormal_events" if remaining <= 0 and result.get('budget_timing_status') == 'measured' else 'budget_incomplete',
                "seed": task.seed,
                "fragments": fragments,
                "round_end_corpus_record": end_path.relative_to(REPOSITORY_ROOT).as_posix(),
                "terminal_at": result["terminal_at"],
                "round_record_path": str(round_record_path),
                "runtime_snapshot_path": None if runtime_snapshot_path is None else str(runtime_snapshot_path),
                "candidate_bundle_path": None if candidate_bundle_path is None else str(candidate_bundle_path),
            }
            persist_state(state_path, state)
            return
        process_restart += 1
        resume_binding = result.get("resume_corpus_binding")
        _, current_corpus = resolve_artifact_binding(
            resume_binding,
            "resume_corpus_binding",
        )
        current_corpus = isolate_terminating_input(result, operation_root, current_corpus)
        pending = None
def harness_spec_reference(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "spec_id": record["identity"]["spec_id"],
        "revision_number": record["revision_information"]["revision_number"],
        "content_hash": content_hash(record),
    }


def strategy_reference(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "strategy_id": record["identity"]["strategy_id"],
        "revision_number": record["revision_information"]["revision_number"],
        "content_hash": content_hash(record),
    }


def harness_artifact_reference(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_id": record["identity"]["harness_artifact_id"],
        "artifact_version": record["schema_version"],
        "content_hash": content_hash(record),
    }


def feedback_arguments(
    matrix: Mapping[str, Any],
    task_state: Mapping[str, Any],
    triplet: Mapping[str, Any],
    decision_paths: Sequence[str],
    feedback_root: Path,
) -> list[str]:
    arguments = [
        "--round-record",
        task_state["round_record_path"],
        "--harness-artifact",
        triplet["artifact_path"],
        "--strategy-plan",
        triplet["strategy_path"],
        "--harness-spec",
        triplet["spec_path"],
        "--policy",
        str(verify_file_reference(matrix["feedback"]["policy_file_ref"], "feedback policy")),
        "--output-root",
        str(feedback_root / "decisions"),
        "--request-root",
        str(feedback_root / "requests"),
    ]
    snapshot = task_state.get("runtime_snapshot_path")
    if isinstance(snapshot, str):
        arguments.extend(["--runtime-snapshot", snapshot])
    for path in decision_paths:
        arguments.extend(["--prior-decision", path])
    return arguments


def call_feedback_controller(
    *,
    python: str,
    arguments: Sequence[str],
    attempt_dir: Path,
    materialization_result: Path | None = None,
    maximum_retries: int = 0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    argv = [
        python,
        str(FEEDBACK_CONTROLLER),
        *arguments,
    ]
    if materialization_result is not None:
        argv.extend(["--materialization-result", str(materialization_result)])
    maximum_attempts = maximum_retries + 1
    attempts_root = attempt_dir / "attempts"
    attempts_root.mkdir(parents=True, exist_ok=True)
    prior = sorted(attempts_root.glob("attempt_[0-9][0-9][0-9]"))
    legacy_result = attempt_dir / "controller_result.json"
    legacy_process = attempt_dir / "process_result.json"
    if legacy_result.exists() or legacy_process.exists():
        prior = [attempt_dir, *prior]
    for previous in prior:
        result_path = previous / "controller_result.json"
        process_path = previous / "process_result.json"
        process = require_object(load_json(process_path), "saved Feedback process") if process_path.is_file() else None
        result = require_object(load_json(result_path), "saved Feedback result") if result_path.is_file() else None
        if process is not None and process.get("returncode") in {0, 3}:
            if result is None:
                raise RunnerError(f"Feedback Controller exited successfully without a result JSON; inspect {previous}")
            if result.get("status") == "error":
                raise RunnerError(f"Feedback Controller failed ({result.get('error_type')}): {result.get('message')}; logs: {previous}")
            return result, process
        if process is not None and result is not None:
            raise RunnerError(f"Feedback Controller failed ({result.get('error_type', 'process_error')}): {result.get('message', result)}; logs: {previous}")
        retryable = process is None or process.get("timed_out") is True or process.get("launch_error") is not None
        if not retryable:
            stderr = (previous / "stderr.log").read_text(encoding="utf-8", errors="replace") if (previous / "stderr.log").is_file() else ""
            raise RunnerError(f"Feedback Controller failed with exit {process.get('returncode')}; {stderr[-2000:]}; logs: {previous}")
    if len(prior) >= maximum_attempts:
        raise RunnerError(f"Feedback Controller exhausted {maximum_attempts} bounded attempt(s); inspect {attempts_root}")
    number = len(prior) + 1
    current = attempts_root / f"attempt_{number:03d}"
    result_path = current / "controller_result.json"
    argv.extend(["--result-json", str(result_path)])
    process = run_command(argv, current)
    if not result_path.is_file():
        stderr = (current / "stderr.log").read_text(encoding="utf-8", errors="replace") if (current / "stderr.log").is_file() else ""
        raise RunnerError(f"Feedback Controller returned {process.get('returncode')} without a result JSON: {stderr[-2000:]}; logs: {current}")
    result = require_object(load_json(result_path), "Feedback Controller result")
    if result.get("status") == "error":
        raise RunnerError(f"Feedback Controller failed ({result.get('error_type')}): {result.get('message')}; logs: {current}")
    if process["returncode"] not in {0, 3}:
        raise RunnerError(f"Feedback Controller failed with exit {process['returncode']}: {result}; logs: {current}")
    return result, process


def update_feedback_disposition_state(
    feedback_state: dict[str, Any],
    round_index: int,
    disposition: Any,
) -> None:
    if disposition in {"freeze_adaptation", "handoff_crash_analysis"}:
        feedback_state["adaptation_status"] = "frozen"
        feedback_state["frozen_after_round_index"] = round_index
        feedback_state["freeze_reason"] = disposition
    elif disposition == "abort_repeat":
        feedback_state["repeat_status"] = "aborted"
        feedback_state["aborted_after_round_index"] = round_index


def materialization_failure_reference(
    path: Path,
    task: Task,
) -> dict[str, Any]:
    return {
        "artifact_id": (
            f"materialization_failure:{task.api_id}:"
            f"repeat{task.repeat_id}:round{task.round_index}"
        ),
        "artifact_version": "1.0",
        "content_hash": file_hash(path),
    }


def apply_feedback_after_round(
    matrix: Mapping[str, Any],
    entry: Mapping[str, Any],
    task: Task,
    state_path: Path,
    state: dict[str, Any],
    run_root: Path,
    python: str,
) -> None:
    if (
        task.group_id != "bug_aware_adaptive"
        or task.round_index not in matrix["feedback"]["decision_after_rounds"]
    ):
        return
    repeat_key = f"repeat_{task.repeat_id:03d}"
    feedback_state = (
        state.setdefault("feedback", {})
        .setdefault(task.api_id, {})
        .setdefault(repeat_key, {})
    )
    if feedback_state.get("adaptation_status") == "frozen":
        return
    if feedback_state.get("repeat_status") == "aborted":
        return
    round_key = f"round_{task.round_index:03d}"
    existing = feedback_state.get(round_key)
    if isinstance(existing, dict) and existing.get("status") == "decision_recorded":
        return

    task_state = require_object(state["tasks"][task.key], task.key)
    triplet = active_triplet(state, task)
    decision_paths = [
        value["decision_path"]
        for key, value in sorted(feedback_state.items())
        if key != round_key
        and isinstance(value, dict)
        and value.get("status") == "decision_recorded"
    ]
    feedback_root = (
        run_root
        / "feedback"
        / safe_component(task.api_id)
        / repeat_key
        / round_key
    )
    common = feedback_arguments(
        matrix,
        task_state,
        triplet,
        decision_paths,
        feedback_root,
    )
    feedback_retries = matrix["failure_handling"]["infrastructure_retry"]["maximum_retries_per_operation"]
    initial, _ = call_feedback_controller(
        python=python,
        arguments=common,
        attempt_dir=feedback_root / "controller_initial",
        maximum_retries=feedback_retries,
    )

    if initial.get("status") == "decision_recorded":
        decision_path = Path(require_string(initial.get("decision_path"), "decision_path"))
        disposition = initial.get("run_disposition")
        feedback_state[round_key] = {
            "status": "decision_recorded",
            "decision_path": str(decision_path),
            "materialization_outcome": initial.get("materialization_outcome"),
            "run_disposition": disposition,
        }
        update_feedback_disposition_state(feedback_state, task.round_index, disposition)
        persist_state(state_path, state)
        return
    if initial.get("status") != "materialization_required":
        raise RunnerError(f"Unexpected Feedback Controller result: {initial}")

    request_path = Path(require_string(initial.get("request_path"), "request_path"))
    request = require_object(load_json(request_path), "materialization request")
    materialization_root = feedback_root / "materialization"
    step_state = feedback_state.setdefault(round_key, {})
    candidate_spec: Path | None = None
    candidate_strategy: Path | None = None
    candidate_artifact: Path | None = None
    failed_stage = "harness_spec_validation"
    preflight_result_path: Path | None = None
    try:
        candidate_spec = run_builder_step(
            state_path=state_path,
            state=state,
            step_state=step_state,
            step_name="harness_spec",
            argv=[
                python,
                str(SPEC_BUILDER),
                "--feedback-request",
                str(request_path),
                "--parent-spec",
                triplet["spec_path"],
                "--output-root",
                str(materialization_root / "harness_specs"),
            ],
            log_root=materialization_root / "attempts",
            output_reader=lambda result: builder_output_path(result, "HarnessSpec Builder"),
        )
        sys.path.insert(0, str(SPEC_BUILDER.parent))
        from budget_derivation import create as create_certificate, validate as validate_certificate
        spec_certificate_path = materialization_root / 'spec_derivation_certificate.json'
        spec_certificate = create_certificate('spec', candidate_spec, triplet['spec_path'], triplet['strategy_path'],
            triplet['spec_authorization_path'], triplet['strategy_authorization_path'], request_path)
        write_or_verify_immutable_json(spec_certificate_path, spec_certificate)
        validate_certificate(spec_certificate, spec_certificate_path, candidate_spec, 'spec')
        failed_stage = "strategy_rebinding"
        candidate_strategy = run_builder_step(
            state_path=state_path,
            state=state,
            step_state=step_state,
            step_name="strategy",
            argv=[
                python,
                str(STRATEGY_BUILDER),
                "--harness-spec",
                str(candidate_spec),
                '--harness-spec-review', str(spec_certificate_path),
                "--rebind-source-spec",
                triplet["spec_path"],
                "--rebind-from-strategy",
                triplet["strategy_path"],
                "--output-root",
                str(materialization_root / "strategy_plans"),
            ],
            log_root=materialization_root / "attempts",
            output_reader=strategy_output_path,
        )
        strategy_certificate_path = materialization_root / 'strategy_derivation_certificate.json'
        strategy_certificate = create_certificate('strategy', candidate_strategy, triplet['spec_path'], triplet['strategy_path'],
            triplet['spec_authorization_path'], triplet['strategy_authorization_path'], request_path, candidate_spec)
        write_or_verify_immutable_json(strategy_certificate_path, strategy_certificate)
        validate_certificate(strategy_certificate, strategy_certificate_path, candidate_strategy, 'strategy')
        compile_path = verify_file_reference(
            entry.get("compile_profile_file_ref"),
            f"api_entries[{entry['api_id']}].compile_profile_file_ref",
        )
        target_manifest_path = evaluation_target_manifest(matrix)
        failed_stage = "harness_materialization"
        candidate_artifact = run_builder_step(
            state_path=state_path,
            state=state,
            step_state=step_state,
            step_name="harness_artifact",
            argv=[
                python,
                str(ARTIFACT_BUILDER),
                "--strategy-plan",
                str(candidate_strategy),
                '--strategy-review', str(strategy_certificate_path),
                "--harness-spec-root",
                str(materialization_root / "harness_specs"),
                "--evaluation-target-manifest",
                str(target_manifest_path),
                "--compile-config",
                str(compile_path),
                "--output-root",
                str(materialization_root / "harnesses"),
            ],
            log_root=materialization_root / "attempts",
            output_reader=artifact_output_path,
        )
        failed_stage = "preflight_execution"
        preflight_result_path = preflight(
            matrix,
            {
                "api_id": task.api_id,
                "target_api": task.target_api,
                "group_id": task.group_id,
                "harness_record": candidate_artifact,
                "strategy_plan": candidate_strategy,
                "harness_spec": candidate_spec,
            },
            materialization_root / "attempts" / "preflight" / "attempt_001",
        )
    except (RunnerError, ValueError, KeyError) as exc:
        diagnostic_path = materialization_root / "failure_diagnostic.json"
        diagnostic = {
            "diagnostic_format_version": "1.0",
            "request_id": request["request_id"],
            "failed_stage": failed_stage,
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
        write_or_verify_immutable_json(diagnostic_path, diagnostic)
        materialization = {
            "outcome": "rejected",
            "candidate_harness_spec_ref": (
                None
                if candidate_spec is None
                else harness_spec_reference(
                    require_object(load_json(candidate_spec), "candidate HarnessSpec")
                )
            ),
            "candidate_strategy_ref": (
                None
                if candidate_strategy is None
                else strategy_reference(
                    require_object(load_json(candidate_strategy), "candidate Strategy")
                )
            ),
            "candidate_harness_artifact_ref": (
                None
                if candidate_artifact is None
                else harness_artifact_reference(
                    require_object(load_json(candidate_artifact), "candidate Artifact")
                )
            ),
            "failed_stage": failed_stage,
            "warning_refs": [],
            "failure_diagnostic_refs": [
                materialization_failure_reference(diagnostic_path, task)
            ],
        }
    else:
        spec_record = require_object(load_json(candidate_spec), "candidate HarnessSpec")
        strategy_record = require_object(load_json(candidate_strategy), "candidate Strategy")
        artifact_record = require_object(load_json(candidate_artifact), "candidate Artifact")
        materialization = {
            "outcome": "accepted",
            "candidate_harness_spec_ref": harness_spec_reference(spec_record),
            "candidate_strategy_ref": strategy_reference(strategy_record),
            "candidate_harness_artifact_ref": harness_artifact_reference(artifact_record),
            "failed_stage": None,
            "warning_refs": [],
            "failure_diagnostic_refs": [],
            "validation_evidence": {
                "feedback_request_file_ref": repository_file_reference(request_path),
                "harness_spec_file_ref": repository_file_reference(candidate_spec),
                "strategy_plan_file_ref": repository_file_reference(candidate_strategy),
                "harness_artifact_file_ref": repository_file_reference(candidate_artifact),
                "preflight_result_file_ref": repository_file_reference(preflight_result_path),
            },
        }

    materialization_result = {
        "result_version": "1.0",
        "request_id": request["request_id"],
        "request_key": request["request_key"],
        "materialization": materialization,
    }
    materialization_result_path = materialization_root / "materialization_result.json"
    write_or_verify_immutable_json(materialization_result_path, materialization_result)
    final, _ = call_feedback_controller(
        python=python,
        arguments=common,
        attempt_dir=feedback_root / "controller_final",
        materialization_result=materialization_result_path,
        maximum_retries=feedback_retries,
    )
    if final.get("status") != "decision_recorded":
        raise RunnerError(f"Feedback decision was not recorded: {final}")

    if materialization["outcome"] == "accepted":
        state.setdefault("adaptive_current", {}).setdefault(task.api_id, {})[
            repeat_key
        ] = {
            "status": "success",
            "spec_path": str(candidate_spec),
            "strategy_path": str(candidate_strategy),
            "artifact_path": str(candidate_artifact),
            'spec_authorization_path': str(spec_certificate_path),
            'strategy_authorization_path': str(strategy_certificate_path),
        }
    disposition = final.get("run_disposition")
    step_state.update(
        {
            "status": "decision_recorded",
            "decision_path": require_string(final.get("decision_path"), "decision_path"),
            "materialization_outcome": final.get("materialization_outcome"),
            "run_disposition": disposition,
            "retained_parent_after_rejection": materialization["outcome"] == "rejected",
        }
    )
    update_feedback_disposition_state(feedback_state, task.round_index, disposition)
    persist_state(state_path, state)




def execute_all(
    matrix: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    state_path: Path,
    state: dict[str, Any],
    run_root: Path,
    python: str,
) -> None:
    entry_by_id = {entry["api_id"]: entry for entry in entries}
    for task in build_tasks(matrix, entries):
        if task.round_index > 1:
            previous_key = ':'.join((task.api_id, task.group_id, task.canonical_repeat_id, f'round_{task.round_index - 1:03d}'))
            if state['tasks'].get(previous_key, {}).get('status') not in {'completed', 'completed_with_abnormal_events'}:
                state['tasks'][task.key] = {'status': 'blocked_by_prior_failure', 'seed': task.seed, 'terminal_at': utc_now(), 'blocked_by': previous_key}
                persist_state(state_path, state)
                continue
        if task.group_id == "bug_aware_adaptive":
            repeat_state = (
                state.get("feedback", {})
                .get(task.api_id, {})
                .get(f"repeat_{task.repeat_id:03d}", {})
            )
            if repeat_state.get("repeat_status") == "aborted":
                state["tasks"][task.key] = {
                    "status": "aborted_by_feedback",
                    "seed": task.seed,
                    "terminal_at": utc_now(),
                    "aborted_after_round_index": repeat_state.get(
                        "aborted_after_round_index"
                    ),
                }
                persist_state(state_path, state)
                continue
        execute_task(
            matrix,
            entry_by_id[task.api_id],
            task,
            state_path,
            state,
            run_root,
        )
        if state['tasks'][task.key]['status'] not in {'completed', 'completed_with_abnormal_events'}:
            continue
        apply_feedback_after_round(
            matrix,
            entry_by_id[task.api_id],
            task,
            state_path,
            state,
            run_root,
            python,
        )


def plan_record(
    matrix: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    readiness: Sequence[str],
) -> dict[str, Any]:
    tasks = build_tasks(matrix, entries)
    return {
        "runner_version": RUNNER_VERSION,
        "matrix_id": matrix["matrix_id"],
        "matrix_content_hash": content_hash(matrix),
        "execution_ready": not readiness,
        "readiness_issues": list(readiness),
        "task_count": len(tasks),
        "tasks": [
            {
                "task_key": task.key,
                "api_id": task.api_id,
                "target_api": task.target_api,
                "group_id": task.group_id,
                "repeat_id": task.canonical_repeat_id,
                "repeat_index": task.repeat_id,
                "round_id": task.canonical_round_id,
                "round_index": task.round_index,
                "seed": task.seed,
            }
            for task in tasks
        ],
    }


def finalize(
    matrix: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    state_path: Path,
    state: dict[str, Any],
    run_root: Path,
) -> dict[str, Any]:
    tasks = build_tasks(matrix, entries)
    missing = [
        task.key
        for task in tasks
        if require_object(state["tasks"].get(task.key, {}), task.key).get("status")
        not in TERMINAL_TASK_STATUSES
    ]
    if missing:
        raise RunnerError(
            f"Cannot finalize; {len(missing)} core task(s) are non-terminal"
        )
    path = run_root / "result_provenance.json"
    if path.exists():
        existing = require_object(load_json(path), "result provenance")
        if (
            existing.get("runner_version") != RUNNER_VERSION
            or existing.get("matrix_id") != matrix["matrix_id"]
            or existing.get("matrix_content_hash") != content_hash(matrix)
            or existing.get("task_count") != len(tasks)
        ):
            raise ImmutableConflict("Existing result provenance differs")
        state["result_provenance_ref"] = {
            "relative_path": path.relative_to(REPOSITORY_ROOT).as_posix(),
            "content_hash": file_hash(path),
        }
        persist_state(state_path, state)
        return existing

    terminal_times = [
        parse_timestamp(state["tasks"][task.key]["terminal_at"])
        for task in tasks
    ]
    last_terminal = max(terminal_times)
    delay = matrix["analysis"]["analysis_cutoff_policy"]["delay_seconds"]
    if not isinstance(delay, int) or isinstance(delay, bool) or delay <= 0:
        raise ConfigurationError("analysis cutoff delay_seconds must be positive")
    cutoff = last_terminal + timedelta(seconds=delay)
    record = {
        "runner_version": RUNNER_VERSION,
        "matrix_id": matrix["matrix_id"],
        "matrix_content_hash": content_hash(matrix),
        "last_terminal_core_run_at": last_terminal.isoformat().replace("+00:00", "Z"),
        "analysis_cutoff_at": cutoff.isoformat().replace("+00:00", "Z"),
        "finalized_at": utc_now(),
        "task_count": len(tasks),
    }
    write_immutable_json(path, record)
    state["result_provenance_ref"] = {
        "relative_path": path.relative_to(REPOSITORY_ROOT).as_posix(),
        "content_hash": file_hash(path),
    }
    persist_state(state_path, state)
    return record


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument(
        "--phase",
        choices=("validate", "plan", "prepare", "execute", "finalize"),
        default="validate",
    )
    parser.add_argument("--api", action="append", default=[])
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument('--approval-record', type=Path, action='append', default=[], help='Exact external approval for a previously generated subject; never a repair opportunity.')
    args = parser.parse_args(argv)

    try:
        matrix_path = repository_path(args.matrix)
        matrix = require_object(load_json(matrix_path), "experiment matrix")
        readiness = validate_matrix(matrix)
        checked_refs = verify_declared_file_refs(matrix)
        entries = selected_apis(matrix, args.api)

        if args.phase == "validate":
            print(
                json.dumps(
                    {
                        "status": "passed" if not readiness else "valid_draft",
                        "matrix_id": matrix["matrix_id"],
                        "execution_ready": not readiness,
                        "readiness_issues": readiness,
                        "checked_file_refs": checked_refs,
                        "api_count": len(entries),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.phase == "plan":
            print(
                json.dumps(
                    plan_record(matrix, entries, readiness),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        require_execution_ready(matrix)
        run_root = run_root_path(args.run_root)
        state_path = run_root / "execution_index.json"
        state = load_or_create_state(
            state_path,
            matrix,
            matrix_path,
            args.resume,
        )
        selection = [entry['api_id'] for entry in entries]
        if 'selected_api_ids' in state and state['selected_api_ids'] != selection:
            raise ImmutableConflict('Resume cannot change the selected task set')
        state['selected_api_ids'] = selection
        for path in args.approval_record:
            ref = repository_file_reference(path)
            if ref not in state.setdefault('authorization_records', []):
                state['authorization_records'].append(ref)
        persist_state(state_path, state)

        if args.phase == "prepare":
            prepare_all(
                matrix,
                entries,
                state_path,
                state,
                run_root,
                args.python,
            )
            print(
                json.dumps(
                    {
                        "status": "prepared",
                        "state_path": str(state_path),
                        "api_count": len(entries),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.phase == "execute":
            if not state["preparation"]:
                raise RunnerError("execute requires a completed prepare phase")
            execute_all(
                matrix,
                entries,
                state_path,
                state,
                run_root,
                args.python,
            )
            print(
                json.dumps(
                    {
                        "status": "executed",
                        "state_path": str(state_path),
                        "terminal_task_count": sum(
                            value.get("status") in TERMINAL_TASK_STATUSES
                            for value in state["tasks"].values()
                        ),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        result = finalize(
            matrix,
            entries,
            state_path,
            state,
            run_root,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    except RunnerError as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
