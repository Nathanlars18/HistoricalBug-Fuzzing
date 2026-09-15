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
RUNNER_VERSION = "0.4.0"
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


def run_command(
    argv: Sequence[str],
    attempt_dir: Path,
    *,
    timeout_seconds: int | None = None,
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
            exc.stdout or "",
            encoding="utf-8",
        )
        (attempt_dir / "stderr.log").write_text(
            exc.stderr or "",
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

    attempt_number = 1 + sum(
        1 for key in step_state if key.startswith(f"{step_name}_failed_")
    )
    attempt_dir = log_root / step_name / f"attempt_{attempt_number:03d}"
    while attempt_dir.exists():
        attempt_number += 1
        attempt_dir = log_root / step_name / f"attempt_{attempt_number:03d}"
    result_path = attempt_dir / "builder_result.json"
    process = run_command(
        [*argv, "--result-json", str(result_path)],
        attempt_dir,
    )
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
) -> None:
    template = matrix["execution"]["runner_adapters"]["preflight_argv_template"]
    result_path = attempt_dir / "adapter_result.json"
    process_path = attempt_dir / "process_result.json"
    if result_path.is_file() and process_path.is_file():
        result = require_object(load_json(result_path), "saved preflight result")
        process = require_object(load_json(process_path), "saved preflight process")
        if process.get("returncode") != 0 or result.get("status") != "passed":
            raise RunnerError(f"Saved preflight failed: {result}")
        return
    argv = expand_argv(template, {**values, "result_json": result_path})
    process = run_command(argv, attempt_dir)
    result = require_object(load_json(result_path), "preflight result")
    if process["returncode"] != 0 or result.get("status") != "passed":
        raise RunnerError(f"Preflight failed: {result}")


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
            for key in ("spec_path", "strategy_path", "artifact_path")
        }
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
            "--mode",
            mode,
            "--max-attempts",
            str(max_attempts),
            *model_args,
            "--output-root",
            str(operation_root / "harness_specs"),
        ],
        log_root=operation_root / "attempts",
        output_reader=lambda result: builder_output_path(result, "HarnessSpec Builder"),
    )

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
            "--max-attempts",
            str(strategy_attempts),
            *model_args,
            "--output-root",
            str(operation_root / "strategy_plans"),
        ],
        log_root=operation_root / "attempts",
        output_reader=strategy_output_path,
    )

    compile_path = verify_file_reference(
        entry.get("compile_profile_file_ref"),
        f"api_entries[{entry['api_id']}].compile_profile_file_ref",
    )
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
    for entry in entries:
        prepare_group(
            matrix,
            entry,
            "structured_baseline",
            state_path,
            state,
            run_root,
            python,
        )
        prepare_group(
            matrix,
            entry,
            "bug_aware_static",
            state_path,
            state,
            run_root,
            python,
        )
        prepare_group(
            matrix,
            entry,
            "bug_aware_adaptive",
            state_path,
            state,
            run_root,
            python,
        )


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
    return repository_path(
        require_string(prior.get("round_end_corpus_record"), "round_end_corpus_record")
    )


def structured_round_result(path: Path) -> dict[str, Any]:
    result = require_object(load_json(path), "round adapter result")
    status = result.get("status")
    if status not in {
        "completed",
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
        current["status"] = "success"
        by_api[repeat_key] = current
    return require_object(current, "adaptive current triplet")


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
        raise RunnerError(f"Preparation is incomplete for {task.key}")

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
    infra_attempt = sum(
        item.get("adapter_result", {}).get("status") == "infrastructure_failure"
        for item in fragments
    )
    process_restart = sum(
        item.get("adapter_result", {}).get("status") == "target_or_framework_exit"
        for item in fragments
    )
    if fragments and fragments[-1]["adapter_result"]["status"] == "target_or_framework_exit":
        last = fragments[-1]["adapter_result"]
        remaining = float(last["remaining_active_seconds"])
        _, current_corpus = resolve_artifact_binding(last.get("resume_corpus_binding"), "resume_corpus_binding")
    operation_root = run_root / "rounds" / task.key.replace(":", "/")

    while True:
        attempt_number = len(fragments) + 1
        attempt_dir = operation_root / f"attempt_{attempt_number:03d}"
        while attempt_dir.exists():
            attempt_number += 1
            attempt_dir = operation_root / f"attempt_{attempt_number:03d}"
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
            "harness_record": prepared["artifact_path"],
            "round_start_corpus_record": current_corpus,
            "result_json": result_path,
            "attempt_dir": attempt_dir,
        }
        argv = expand_argv(
            matrix["execution"]["runner_adapters"]["round_argv_template"],
            values,
        )
        process = run_command(
            argv,
            attempt_dir,
            timeout_seconds=max(int(remaining) + 120, 180),
        )
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
        fragments.append(fragment)
        state["tasks"][task.key] = {
            "status": "in_progress",
            "seed": task.seed,
            "fragments": fragments,
            "updated_at": result["terminal_at"],
        }
        persist_state(state_path, state)

        status = result["status"]
        if status == "completed":
            end_binding = result.get("round_end_corpus_binding")
            _, end_path = resolve_artifact_binding(
                end_binding,
                "round_end_corpus_binding",
            )
            round_record_path = verify_file_reference(
                result.get("round_record_file_ref"),
                "round result round_record_file_ref",
            )
            runtime_snapshot_ref = result.get("runtime_snapshot_file_ref")
            runtime_snapshot_path = (
                None if runtime_snapshot_ref is None
                else verify_file_reference(runtime_snapshot_ref, "runtime snapshot")
            )
            state["tasks"][task.key] = {
                "status": (
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
                raise RunnerError(
                    f"Non-retryable or exhausted infrastructure failure "
                    f"for {task.key}: {category!r}"
                )
            infra_attempt += 1
            current_corpus = original_corpus
            remaining = float(total_budget)
            continue

        if process_restart >= maximum_restarts:
            raise RunnerError(f"Process restart limit exhausted for {task.key}")
        process_restart += 1
        remaining = float(result["remaining_active_seconds"])
        if remaining <= 0:
            raise RunnerError(
                f"Abnormal exit has no remaining budget for {task.key}"
            )
        resume_binding = result.get("resume_corpus_binding")
        _, current_corpus = resolve_artifact_binding(
            resume_binding,
            "resume_corpus_binding",
        )
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
) -> tuple[dict[str, Any], dict[str, Any]]:
    result_path = attempt_dir / "controller_result.json"
    process_path = attempt_dir / "process_result.json"
    if result_path.is_file() and process_path.is_file():
        result = require_object(load_json(result_path), "saved Feedback result")
        process = require_object(load_json(process_path), "saved Feedback process")
        if process.get("returncode") not in {0, 3}:
            raise RunnerError(f"Saved Feedback Controller call failed: {result}")
        return result, process
    argv = [
        python,
        str(FEEDBACK_CONTROLLER),
        *arguments,
    ]
    if materialization_result is not None:
        argv.extend(["--materialization-result", str(materialization_result)])
    argv.extend(["--result-json", str(result_path)])
    process = run_command(argv, attempt_dir)
    result = load_builder_result(result_path, "Feedback Controller")
    if process["returncode"] not in {0, 3}:
        raise RunnerError(f"Feedback Controller failed: {result}")
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
    initial, _ = call_feedback_controller(
        python=python,
        arguments=common,
        attempt_dir=feedback_root / "controller_initial",
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
        compile_path = verify_file_reference(
            entry.get("compile_profile_file_ref"),
            f"api_entries[{entry['api_id']}].compile_profile_file_ref",
        )
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
                "--harness-spec-root",
                str(materialization_root / "harness_specs"),
                "--compile-config",
                str(compile_path),
                "--output-root",
                str(materialization_root / "harnesses"),
            ],
            log_root=materialization_root / "attempts",
            output_reader=artifact_output_path,
        )
        failed_stage = "preflight_execution"
        preflight(
            matrix,
            {
                "api_id": task.api_id,
                "target_api": task.target_api,
                "group_id": task.group_id,
                "harness_record": candidate_artifact,
            },
            materialization_root / "attempts" / "preflight" / "attempt_001",
        )
    except RunnerError as exc:
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
