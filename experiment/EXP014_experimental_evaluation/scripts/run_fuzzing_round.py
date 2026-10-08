#!/usr/bin/env python3
"""Run one compiled Harness round and emit EXP012/EXP014 records."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import signal
import sys
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

if str(Path(__file__).resolve().parents[3]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from experiment.EXP014_experimental_evaluation.scripts.execution_semantics import (
    FORMAT_VERSION, RUNTIME_VERSION, snapshot_issues, validate_limits, text_output,
)

try:
    from coverage_replay import CoverageError, load_scope, replay as replay_coverage
except ModuleNotFoundError as exc:
    if exc.name != "coverage_replay":
        raise
    from experiment.EXP014_experimental_evaluation.scripts.coverage_replay import (
        CoverageError,
        load_scope,
        replay as replay_coverage,
    )


ADAPTER_ID = "run_fuzzing_round"
ADAPTER_VERSION = "0.5.0"
DEFAULT_IMAGE = (
    "sha256:10968a7f565bb6c1fa008d3a5800af46a8085de7d880c3db3751c287d29865c8"
)
EXP_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = EXP_ROOT.parents[1]
EXP011_ROOT = REPOSITORY_ROOT / "experiment/EXP011_bug_aware_harness_synthesis"
EXP012_ROOT = REPOSITORY_ROOT / "experiment/EXP012_adaptive_feedback"
EXP013_ROOT = REPOSITORY_ROOT / "experiment/EXP013_crash_triage_and_result_analysis"
RUNTIME_ROOT = REPOSITORY_ROOT / "runtime/flashfuzz_2_10"
DEFAULTS = {
    "round_schema": EXP012_ROOT / "schemas/fuzzing_round_record.schema.json",
    "runtime_snapshot_schema": EXP_ROOT / "schemas/runtime_snapshot.schema.json",
    "corpus_schema": EXP_ROOT / "schemas/corpus_manifest.schema.json",
    "harness_artifact_schema": EXP011_ROOT / "schemas/harness_artifact_record.schema.json",
    "strategy_schema": EXP011_ROOT / "schemas/strategy_plan_record.schema.json",
    "harness_spec_schema": EXP011_ROOT / "schemas/harness_spec_record.schema.json",
    "candidate_bundle_schema": EXP013_ROOT / "schemas/candidate_bundle_record.schema.json",
    "runtime_config": RUNTIME_ROOT / "runtime_config.json",
    "instrumentation_header": EXP011_ROOT / "runtime/harness_instrumentation.h",
    "instrumentation_source": EXP011_ROOT / "runtime/harness_instrumentation.cpp",
}
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


class AdapterError(RuntimeError):
    """Base adapter failure."""


class InputError(AdapterError):
    """Input or cross-record validation failure."""


class InfrastructureError(AdapterError):
    """Docker or host execution failure."""


@dataclass(frozen=True)
class ResolvedHarness:
    harness_spec: dict[str, Any]
    strategy: dict[str, Any]
    artifact: dict[str, Any]
    binary_path: Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"Cannot read JSON {path}: {exc}") from exc


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def repository_relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPOSITORY_ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise InputError(f"Path must be inside repository: {resolved}") from exc


def repository_path(relative_path: str) -> Path:
    path = (REPOSITORY_ROOT / relative_path).resolve()
    try:
        path.relative_to(REPOSITORY_ROOT.resolve())
    except ValueError as exc:
        raise InputError(f"Reference escapes repository: {relative_path}") from exc
    return path


def file_reference(path: Path) -> dict[str, str]:
    return {
        "relative_path": repository_relative(path),
        "content_hash": file_hash(path),
    }


def artifact_reference(
    artifact_id: str,
    artifact_version: str | int,
    content_hash: str,
) -> dict[str, Any]:
    if not IDENTIFIER_RE.fullmatch(artifact_id):
        raise InputError(f"Invalid Artifact ID: {artifact_id!r}")
    return {
        "artifact_id": artifact_id,
        "artifact_version": artifact_version,
        "content_hash": content_hash,
    }


def schema_validator(path: Path, label: str) -> Draft202012Validator:
    schema = load_json(path)
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        raise InputError(f"Invalid {label} Schema: {exc}") from exc
    registry = Registry()
    core_path = REPOSITORY_ROOT / "experiment/EXP011_bug_aware_harness_synthesis/schemas/harness_spec_record_core__v2_2.schema.json"
    core = load_json(core_path)
    registry = registry.with_resource(core["$id"], Resource.from_contents(core))
    return Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())


def validate_record(
    value: Any,
    validator: Draft202012Validator,
    label: str,
) -> None:
    try:
        errors = sorted(validator.iter_errors(value), key=lambda item: item.json_path)
    except Exception as exc:
        raise InputError(f"Cannot validate {label}: {exc}") from exc
    if errors:
        details = "; ".join(
            f"{item.json_path}: {item.message}" for item in errors[:12]
        )
        raise InputError(f"{label} violates its Schema: {details}")


def verify_file_reference(reference: Mapping[str, Any], label: str) -> Path:
    relative = reference.get("relative_path")
    declared = reference.get("content_hash")
    if not isinstance(relative, str) or not isinstance(declared, str):
        raise InputError(f"{label} is not a File Reference")
    path = repository_path(relative)
    if not path.is_file():
        raise InputError(f"{label} does not exist: {relative}")
    actual = file_hash(path)
    if actual != declared:
        raise InputError(f"{label} hash mismatch: {actual} != {declared}")
    return path


def spec_reference(record: Mapping[str, Any]) -> dict[str, Any]:
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


def adapter_reference() -> dict[str, Any]:
    return artifact_reference(
        ADAPTER_ID,
        ADAPTER_VERSION,
        file_hash(Path(__file__).resolve()),
    )


def resolve_harness(
    harness_record_path: Path,
    strategy_path: Path,
    harness_spec_path: Path,
    artifact_validator: Draft202012Validator,
    strategy_validator: Draft202012Validator,
    spec_validator: Draft202012Validator,
) -> ResolvedHarness:
    artifact = load_json(harness_record_path)
    strategy = load_json(strategy_path)
    harness_spec = load_json(harness_spec_path)
    validate_record(artifact, artifact_validator, "Harness Artifact")
    validate_record(strategy, strategy_validator, "Strategy Plan")
    validate_record(harness_spec, spec_validator, "HarnessSpec")

    if artifact["source_context"]["strategy_revision_ref"] != strategy_reference(strategy):
        raise InputError("Harness Artifact does not reference the exact Strategy")
    if strategy["source_context"]["harness_spec_ref"] != spec_reference(harness_spec):
        raise InputError("Strategy does not reference the exact HarnessSpec")
    if artifact["validation"]["compile_check"]["status"] != "passed":
        raise InputError("Harness Artifact compilation did not pass")
    binary_ref = artifact["validation"]["compile_check"]["binary_artifact"]
    if not isinstance(binary_ref, dict):
        raise InputError("Harness Artifact has no compiled binary reference")
    binary_path = verify_file_reference(binary_ref, "Harness binary")
    if not os.access(binary_path, os.X_OK):
        raise InputError(f"Harness binary is not executable: {binary_path}")

    target_api = harness_spec["identity"]["target_api"]
    mode = harness_spec["identity"]["spec_mode"]
    if (
        strategy["identity"]["target_api"] != target_api
        or strategy["identity"]["spec_mode"] != mode
    ):
        raise InputError("HarnessSpec and Strategy scopes differ")
    return ResolvedHarness(harness_spec, strategy, artifact, binary_path)


def runtime_environment_reference(path: Path) -> dict[str, Any]:
    record = load_json(path)
    version = record.get("config_version")
    if not isinstance(version, str) or not version:
        raise InputError("Runtime configuration has no config_version")
    return artifact_reference(
        "pytorch_2_10_runtime_environment",
        version,
        canonical_hash(record),
    )


def instrumentation_reference(header: Path, source: Path) -> dict[str, Any]:
    for path in (header, source):
        if not path.is_file():
            raise InputError(f"Instrumentation component is missing: {path}")
    payload = {
        "header": file_reference(header),
        "source": file_reference(source),
    }
    return artifact_reference("harness_instrumentation_runtime", RUNTIME_VERSION, canonical_hash(payload))


def corpus_artifact_reference(record: Mapping[str, Any]) -> dict[str, Any]:
    identity = record["identity"]
    return artifact_reference(
        identity["corpus_id"],
        identity["artifact_version"],
        canonical_hash(record),
    )


def validate_corpus_files(record: Mapping[str, Any]) -> None:
    names: set[str] = set()
    for item in record["files"]:
        name = item["corpus_relative_path"]
        if name in names:
            raise InputError(f"Duplicate Corpus path: {name}")
        names.add(name)
        path = verify_file_reference(item["file_ref"], f"Corpus file {name}")
        if path.stat().st_size != item["size_bytes"]:
            raise InputError(f"Corpus size mismatch: {name}")


def load_corpus_manifest(
    path: Path,
    validator: Draft202012Validator,
) -> dict[str, Any]:
    record = load_json(path)
    validate_record(record, validator, "Corpus Manifest")
    validate_corpus_files(record)
    return record


def copy_corpus(record: Mapping[str, Any], destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for item in record["files"]:
        source = verify_file_reference(item["file_ref"], "Corpus source file")
        target = destination / item["corpus_relative_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def build_corpus_manifest(
    corpus_dir: Path,
    output_path: Path,
    corpus_id: str,
    kind: str,
    source_round_id: str | None,
    validator: Draft202012Validator,
) -> tuple[dict[str, Any], dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for path in sorted(item for item in corpus_dir.rglob("*") if item.is_file()):
        files.append(
            {
                "corpus_relative_path": path.relative_to(corpus_dir).as_posix(),
                "file_ref": file_reference(path),
                "size_bytes": path.stat().st_size,
            }
        )
    record = {
        "record_format_version": "1.0",
        "record_type": "corpus_manifest",
        "identity": {"corpus_id": corpus_id, "artifact_version": 1},
        "source": {"kind": kind, "source_round_id": source_round_id},
        "files": files,
        "provenance": {
            "generator_ref": adapter_reference(),
            "generated_at": utc_now(),
        },
    }
    validate_record(record, validator, "Corpus Manifest")
    write_json_atomic(output_path, record)
    binding = {
        "artifact_ref": corpus_artifact_reference(record),
        "record_file_ref": file_reference(output_path),
    }
    return record, binding


def validate_runtime_snapshot(
    path: Path,
    validator: Draft202012Validator,
    artifact: Mapping[str, Any],
) -> dict[str, Any]:
    snapshot = load_json(path)
    validate_record(snapshot, validator, "Runtime Snapshot")
    identity = artifact["identity"]
    if (
        snapshot["artifact_id"] != identity["harness_artifact_id"]
        or snapshot["generation_key"] != identity["generation_key"]
    ):
        raise InputError("Runtime Snapshot identifies a different Harness Artifact")
    if len(snapshot["site_counts"]) != snapshot["site_count"]:
        raise InputError("Runtime Snapshot site_counts length differs from site_count")
    if snapshot["finished_iterations"] > snapshot["started_iterations"]:
        raise InputError("Runtime Snapshot finished count exceeds started count")
    if snapshot["finished_iterations"] + snapshot["unwound_iterations"] > snapshot["started_iterations"]:
        raise InputError("Runtime Snapshot completed and unwound counts exceed started invocations")
    if snapshot["invalid_site_records"] or snapshot["export_failures"]:
        raise InputError("Runtime instrumentation reported invalid records or export failures")
    issues = snapshot_issues(snapshot, artifact)
    if issues:
        raise InputError("Runtime Snapshot: " + ", ".join(issues))
    return snapshot


def signal_name(return_code: int) -> str | None:
    signal_number = -return_code if return_code < 0 else return_code - 128
    if signal_number <= 0:
        return None
    try:
        return signal.Signals(signal_number).name
    except ValueError:
        return None


def classify_nonzero_exit(return_code: int, container_state: Mapping[str, Any] | None,
                          timed_out: bool, candidate_observed: bool) -> str:
    """Describe evidence without inferring a PyTorch defect from an exit code."""
    if container_state and container_state.get("OOMKilled") is True:
        return "container_oom_killed"
    if timed_out:
        return "adapter_timeout"
    if candidate_observed:
        return "candidate_artifact_observed"
    if return_code in {125, 126, 127}:
        return "container_or_command_launch_failure"
    if signal_name(return_code):
        return "signal_termination_unclassified"
    return "nonzero_exit_unclassified"


def log_reference(path: Path, execution_id: str) -> dict[str, Any]:
    return artifact_reference(
        f"run_log_{execution_id}",
        1,
        file_hash(path),
    )



def evidence_location(path: Path, prefix: str) -> dict[str, Any]:
    digest = file_hash(path)
    return {
        "artifact_ref": artifact_reference(f"{prefix}_{digest[:16]}", 1, digest),
        "file_ref": file_reference(path),
    }


def classify_candidate(path: Path, diagnostic_text: str) -> tuple[str, str]:
    name = path.name.lower()
    if name.startswith(("timeout-", "oom-", "slow-unit-", "leak-")):
        return "resource_anomaly", name.split("-", 1)[0]
    if "HBFG_ORACLE_FAILURE=" in diagnostic_text:
        return "oracle_failure", "behavior_check_failure"
    markers = (
        "addresssanitizer",
        "undefinedbehaviorsanitizer",
        "memorysanitizer",
        "threadsanitizer",
        "runtime error:",
    )
    if any(marker in diagnostic_text.lower() for marker in markers):
        return "sanitizer", "sanitizer_finding"
    return "crash", "native_process_termination"


def iteration_from_log(text: str) -> int | None:
    matches = re.findall(r"(?:^|\s)#(\d+)\b", text)
    return int(matches[-1]) if matches else None


def validate_capture_counts(counts: Mapping[str, Any] | None, limit: int) -> None:
    if counts is None:
        return
    required = {"attempts", "saved", "failures", "exception_attempts", "oracle_attempts", "limit_per_kind", "complete"}
    if set(counts) != required or counts["complete"] is not True:
        raise InputError("Runtime capture summary is incomplete or has an unknown shape")
    numeric = ("attempts", "saved", "failures", "exception_attempts", "oracle_attempts", "limit_per_kind")
    if any(isinstance(counts[name], bool) or not isinstance(counts[name], int) or counts[name] < 0 for name in numeric):
        raise InputError("Runtime capture summary contains an invalid count")
    if (counts["limit_per_kind"] != limit
            or counts["attempts"] != counts["exception_attempts"] + counts["oracle_attempts"]
            or counts["saved"] > counts["attempts"]
            or counts["failures"] > counts["attempts"]
            or counts["saved"] > 2 * limit
            or counts["saved"] + counts["failures"] > counts["attempts"]):
        raise InputError("Runtime capture summary counts contradict the configured per-kind sample limit")


def build_candidate_bundle(
    *,
    args: argparse.Namespace,
    execution_id: str,
    observed_at: str,
    candidates_dir: Path,
    run_log_path: Path,
    validator: Draft202012Validator,
    artifact: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[dict[str, Any]]]:
    paths = sorted(path for path in candidates_dir.rglob("*") if path.is_file())
    observation_dir = args.attempt_dir.resolve() / "observations"
    event_paths = sorted(observation_dir.glob("event_*.json"))
    if not paths and not event_paths:
        return None, None, []
    diagnostic_text = run_log_path.read_text(encoding="utf-8", errors="replace")
    diagnostic = evidence_location(run_log_path, "diagnostic")
    # libFuzzer progress lines identify statistics, not the failing invocation.
    iteration = None
    candidates: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    sources = [(path, None) for path in paths]
    for event_path in event_paths:
        event = load_json(event_path)
        input_path = event_path.with_suffix(".input")
        if not input_path.is_file() or event.get("kind") not in {"target_exception", "oracle_failure"}:
            raise InputError(f"Incomplete structured anomaly capture: {event_path}")
        if artifact is None or event.get("artifact_id") != artifact["identity"]["harness_artifact_id"]:
            raise InputError("Structured capture identifies another Harness Artifact")
        sources.append((input_path, (event_path, event)))
    for path, captured in sources:
        input_location = evidence_location(path, "input")
        kind, subtype = classify_candidate(path, diagnostic_text)
        branch_ids, site_ids, invocation = [], [], None
        event_context = None
        current_diagnostic = diagnostic
        if captured:
            event_path, event = captured
            kind, subtype = event["kind"], "captured_target_exception" if event["kind"] == "target_exception" else "behavior_check_failure"
            event_context = evidence_location(event_path, "event_context")
            iteration = event["iteration_index"]
            table = {b["runtime_site_id"]: b for b in artifact["instrumentation_map"]}
            bindings = [table[i] for i in event["runtime_sites"] if i in table]
            if len(bindings) != len(event["runtime_sites"]):
                raise InputError("Structured capture has unknown runtime sites")
            site_ids = sorted({b["instrumentation_binding_id"] for b in bindings})
            branch_ids = sorted({b["branch_id"] for b in bindings})
            reached = [b for b in bindings if b["event_kind"] == "target_api_reached"]
            if reached and not event["sites_truncated"]:
                invocation = f"{execution_id}:i{iteration}:{reached[-1]['instrumentation_binding_id']}:n{len(reached)}"
            detail = event_path.with_suffix(".diagnostic.txt")
            marker = "HBFG_TARGET_API_EXCEPTION=" if kind == "target_exception" else "HBFG_ORACLE_FAILURE="
            detail.write_text(marker + event["message"] + "\n", encoding="utf-8")
            current_diagnostic = evidence_location(detail, "diagnostic")
        else:
            iteration = None
        candidate_key = canonical_hash({
            "task_key": args.task_key,
            "attempt_index": args.attempt_index,
            "input_hash": input_location["file_ref"]["content_hash"],
            "observation_kind": kind,
            "source_name": path.name,
        })
        candidate_id = f"cand_{candidate_key[:20]}"
        candidates.append({
            "candidate_id": candidate_id,
            "source_attempt_index": args.attempt_index,
            "observation_kind": kind,
            "observation_subtype": subtype,
            "observed_at": observed_at,
            "triggering_input": input_location,
            "primary_diagnostic": current_diagnostic,
            "branch_ids": branch_ids,
            "site_ids": site_ids,
            "iteration_index": iteration,
            "target_invocation_id": invocation,
            "oracle_evidence_tier": "unevaluable" if kind == "oracle_failure" else None,
            "source_execution_id": execution_id,
            "event_context": event_context,
            "harness_artifact_file_ref": file_reference(args.harness_record) if captured else None,
            "source_config_file_ref": file_reference(args.attempt_dir.resolve() / "round_config.json") if (args.attempt_dir.resolve() / "round_config.json").is_file() else None,
        })
        observations.append({
            "candidate_id": candidate_id,
            "observation_kind": kind,
            "branch_ids": branch_ids,
            "site_ids": site_ids,
            "evidence_refs": [input_location["artifact_ref"], current_diagnostic["artifact_ref"]] + ([] if event_context is None else [event_context["artifact_ref"]]),
        })
    bundle_id = "cb_" + canonical_hash({
        "task_key": args.task_key,
        "attempt_index": args.attempt_index,
        "candidates": candidates,
    })[:20]
    capture_summary_path = observation_dir / "capture_summary.json"
    capture_counts = load_json(capture_summary_path) if capture_summary_path.is_file() else None
    capture_limit = getattr(args, "candidate_sample_limit", 64)
    validate_capture_counts(capture_counts, capture_limit)
    bundle = {
        "record_format_version": "1.1",
        "record_type": "candidate_bundle",
        "identity": {"bundle_id": bundle_id, "artifact_version": 1},
        "round_context": {
            "task_key": args.task_key,
            "api_id": args.api_id,
            "target_api_id": args.target_api,
            "experimental_group": args.group_id,
            "repeat_id": args.repeat_id,
            "round_index": args.round_index,
            "attempt_index": args.attempt_index,
            "execution_id": execution_id,
        },
        "candidates": candidates,
        "provenance": {"producer_ref": adapter_reference(), "generated_at": utc_now()},
        "capture_summary": {
            "sampling": "first_n_per_kind_per_process",
            "limit_per_kind": capture_limit,
            "counts": capture_counts,
            "state": "complete" if capture_counts is not None else "unavailable_after_exit",
        },
    }
    validate_record(bundle, validator, "Candidate Bundle")
    bundle_path = args.attempt_dir.resolve() / "candidate_bundle.json"
    write_json_atomic(bundle_path, bundle)
    binding = {
        "artifact_ref": artifact_reference(bundle_id, 1, canonical_hash(bundle)),
        "record_file_ref": file_reference(bundle_path),
    }
    return bundle, binding, observations

def docker_command(
    *,
    image: str,
    artifact_dir: Path,
    attempt_dir: Path,
    active_seconds: int,
    seed: int,
    container_name: str,
    limits: Mapping[str, Any] | None = None,
) -> list[str]:
    limits = dict(limits or {})
    flags = " ".join(f"-{key}={limits[key]}" for key in ("timeout", "rss_limit_mb", "max_len") if limits.get(key) is not None)
    fuzzer_argv = ["/artifact/harness_binary", "/output/corpus",
                  f"-max_total_time={active_seconds}", f"-seed={seed}",
                  "-artifact_prefix=/output/candidates/"]
    fuzzer_argv.extend(flags.split())
    return [
        "docker", "run", "--network", "none", "--name", container_name,
        "-e", f"HOST_UID={os.getuid()}",
        "-e", f"HOST_GID={os.getgid()}",
        "-e", "HBFG_METRICS_PATH=/output/runtime_snapshot.json",
        "-e", "HBFG_METRICS_SNAPSHOT_INTERVAL=65536",
        "-e", "HBFG_CANDIDATE_DIR=/output/observations",
        "-e", f"HBFG_CANDIDATE_SAMPLE_LIMIT={limits.get('candidate_sample_limit', 64)}",
        *[part for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")
          if os.environ.get(key) is not None for part in ("-e", f"{key}={os.environ[key]}")],
        *(["--memory", f"{limits['process_memory_mb']}m"] if limits.get("process_memory_mb") else []),
        "-v", f"{artifact_dir.resolve()}:/artifact:ro",
        "-v", f"{attempt_dir.resolve()}:/output",
        "-v", f"{Path(__file__).with_name('execution_worker.py').resolve()}:/execution_worker.py:ro",
        "-w", "/output",
        image,
        "python3", "/execution_worker.py", *fuzzer_argv,
    ]


def save_run_log(attempt_dir: Path, process: subprocess.CompletedProcess[str]) -> Path:
    chunks = [
        f"# docker stdout\n{process.stdout}",
        f"# docker stderr\n{process.stderr}",
    ]
    for name in ("fuzzer_stdout.log", "fuzzer_stderr.log"):
        path = attempt_dir / name
        content = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        chunks.append(f"# {name}\n{content}")
    output = attempt_dir / "run.log"
    output.write_text("\n".join(chunks), encoding="utf-8", newline="\n")
    return output


def build_round_record(
    *,
    args: argparse.Namespace,
    resolved: ResolvedHarness,
    execution_id: str,
    started_at: str,
    ended_at: str,
    elapsed: float,
    process: subprocess.CompletedProcess[str],
    round_config: Mapping[str, Any],
    input_corpus_ref: Mapping[str, Any] | None,
    output_manifest: Mapping[str, Any],
    output_manifest_path: Path,
    snapshot: Mapping[str, Any] | None,
    snapshot_path: Path | None,
    run_log_path: Path,
    candidate_binding: Mapping[str, Any] | None,
    candidate_observations: Sequence[Mapping[str, Any]],
    coverage_evidence: Mapping[str, Any],
    round_validator: Draft202012Validator,
) -> dict[str, Any]:
    artifact = resolved.artifact
    snapshot_location = None
    if snapshot is not None and snapshot_path is not None:
        snapshot_location = {
            "artifact_ref": artifact_reference(
                f"runtime_snapshot_{execution_id}",
                snapshot["record_format_version"],
                canonical_hash(snapshot),
            ),
            "file_ref": file_reference(snapshot_path),
        }
    output_location = {
        "artifact_ref": corpus_artifact_reference(output_manifest),
        "file_ref": file_reference(output_manifest_path),
    }
    log_ref = log_reference(run_log_path, execution_id)
    capture_path = args.attempt_dir.resolve() / "observations" / "capture_summary.json"
    capture_counts = load_json(capture_path) if capture_path.is_file() else None
    capture_limit = getattr(args, "candidate_sample_limit", 64)
    validate_capture_counts(capture_counts, capture_limit)
    capture_summary = {"sampling": "first_n_per_kind_per_process", "limit_per_kind": capture_limit,
                       "counts": capture_counts,
                       "state": "complete" if capture_counts is not None else "unavailable_after_exit"}
    record = {
        "record_format_version": "1.0",
        "record_type": "fuzzing_round",
        "identity": {
            "round_id": args.task_key,
            "execution_id": execution_id,
            "target_api_id": args.target_api,
            "experimental_group": args.group_id,
            "independent_repeat_id": args.repeat_id,
            "round_index": args.round_index,
            "attempt_index": args.attempt_index,
        },
        "schedule": {
            "planned_final_round_index": args.planned_final_round_index,
            "planned_duration_seconds": int(math.ceil(args.active_seconds)),
        },
        "source_context": {
            "harness_spec_ref": spec_reference(resolved.harness_spec),
            "strategy_ref": strategy_reference(resolved.strategy),
            "harness_artifact_ref": harness_artifact_reference(artifact),
            "fuzzing_config_ref": artifact_reference(
                f"round_config_{execution_id}", 1, canonical_hash(round_config)
            ),
            "runtime_environment_ref": runtime_environment_reference(args.runtime_config),
            "input_corpus_ref": dict(input_corpus_ref) if input_corpus_ref else None,
            "instrumentation_runtime_ref": instrumentation_reference(
                args.instrumentation_header, args.instrumentation_source
            ),
            "instrumentation_contract_version": FORMAT_VERSION,
        },
        "attempt_selection": {
            "status": "selected_as_round_result",
            "reason_code": "only_attempt",
        },
        "execution": {
            "seed": args.seed,
            "started_at": started_at,
            "ended_at": ended_at,
            "actual_duration_seconds": round(elapsed, 6),
            "termination": {
                "reason": ("time_budget_reached" if elapsed >= args.active_seconds else "completed_early") if process.returncode == 0 else ("candidate_detected" if candidate_binding else "unknown"),
                "exit_code": process.returncode,
                "signal_name": signal_name(process.returncode),
                "diagnostic_refs": [] if process.returncode == 0 else [log_ref],
            },
        },
        "evidence": {
            "runtime_snapshot": {
                "status": "present" if snapshot is not None else "missing",
                "location": snapshot_location,
                "snapshot_kind": None if snapshot is None else snapshot["snapshot_kind"],
                "staleness_iterations": None if snapshot is None or snapshot["snapshot_kind"] != "final" else 0,
            },
            "coverage_summary": dict(coverage_evidence),
            "output_corpus": {
                "status": "present",
                "location": output_location,
                "diagnostic_refs": [],
            },
            "candidate_evidence": {
                "status": "present" if candidate_binding else "absent",
                "bundle_ref": None if not candidate_binding else dict(candidate_binding["artifact_ref"]),
                "bundle_file_ref": None if not candidate_binding else dict(candidate_binding["record_file_ref"]),
                "capture_summary": capture_summary,
                "capture_summary_file_ref": file_reference(capture_path) if capture_path.is_file() else None,
                "process_capture_summaries": [],
                "observations": [dict(item) for item in candidate_observations],
            },
            "run_log_refs": [log_ref],
        },
        "validation": {
            "validation_status": "passed",
            "validation_issues": [],
        },
        "provenance": {
            "runner_artifact_ref": adapter_reference(),
            "generated_at": utc_now(),
        },
    }
    budget_path = args.attempt_dir / "budget_evidence.json"
    if budget_path.is_file():
        record["record_format_version"] = "1.1"
        record["execution"]["budget"] = load_json(budget_path)
    validate_record(record, round_validator, "Fuzzing Round Record")
    return record


def write_adapter_result(path: Path, value: Mapping[str, Any]) -> None:
    write_json_atomic(path, dict(value))


def common_validators(args: argparse.Namespace) -> dict[str, Draft202012Validator]:
    return {
        "round": schema_validator(args.round_schema, "Fuzzing Round"),
        "runtime": schema_validator(args.runtime_snapshot_schema, "Runtime Snapshot"),
        "corpus": schema_validator(args.corpus_schema, "Corpus Manifest"),
        "artifact": schema_validator(args.harness_artifact_schema, "Harness Artifact"),
        "strategy": schema_validator(args.strategy_schema, "Strategy Plan"),
        "spec": schema_validator(args.harness_spec_schema, "HarnessSpec"),
        "candidate": schema_validator(args.candidate_bundle_schema, "Candidate Bundle"),
    }


def command_preflight(args: argparse.Namespace) -> int:
    terminal = utc_now()
    try:
        validators = common_validators(args)
        resolve_harness(
            args.harness_record,
            args.strategy_plan,
            args.harness_spec,
            validators["artifact"],
            validators["strategy"],
            validators["spec"],
        )
        completed = subprocess.run(
            ["docker", "image", "inspect", args.runtime_image],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if completed.returncode != 0:
            raise InfrastructureError(completed.stderr.strip() or "Docker image inspect failed")
        resolved = resolve_harness(args.harness_record, args.strategy_plan, args.harness_spec,
                                   validators['artifact'], validators['strategy'], validators['spec'])
        limits = {"timeout": args.per_call_timeout_seconds, "rss_limit_mb": args.rss_limit_mb,
                  "max_len": args.max_input_bytes, "process_memory_mb": args.process_memory_mb,
                  "candidate_sample_limit": args.candidate_sample_limit}
        try:
            validate_limits(limits)
        except ValueError as exc:
            raise InputError(str(exc)) from exc
        flags = [f"-{name}={limits[key]}" for key, name in (("timeout", "timeout"), ("rss_limit_mb", "rss_limit_mb"), ("max_len", "max_len")) if limits[key] is not None]
        argv = ["docker", "run", "--rm", "--network", "none",
                "-e", f"HBFG_CANDIDATE_SAMPLE_LIMIT={limits['candidate_sample_limit']}",
                *( ["--memory", f"{limits['process_memory_mb']}m"] if limits["process_memory_mb"] is not None else []),
                "-v", f"{resolved.binary_path.parent}:/artifact:ro", args.runtime_image,
                "/artifact/harness_binary", "-help=1", *flags]
        probe = subprocess.run(argv,
                               capture_output=True, text=True, timeout=60, check=False)
        if probe.returncode != 0:
            raise InfrastructureError('Binary load probe failed: ' + probe.stderr[-1000:])
        result = {"status": "passed", "terminal_at": utc_now(), 'probe_kind': 'binary_load_help_probe',
                  'resource_limits': limits, 'argv': argv}
        code = 0
    except (AdapterError, OSError, subprocess.TimeoutExpired) as exc:
        result = {"status": "failed", "terminal_at": terminal, "message": str(exc)}
        code = 2
    write_adapter_result(args.result_json, result)
    return code


def command_init_corpus(args: argparse.Namespace) -> int:
    validator = schema_validator(args.corpus_schema, "Corpus Manifest")
    _, binding = build_corpus_manifest(
        args.corpus_dir,
        args.output,
        args.corpus_id,
        "initial",
        None,
        validator,
    )
    result = {"status": "passed", "corpus_binding": binding}
    if args.result_json:
        write_adapter_result(args.result_json, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_run(args: argparse.Namespace) -> int:
    result_path = args.result_json.resolve()
    terminal = utc_now()
    operation_started_monotonic = time.monotonic()
    active_started_monotonic: float | None = None
    process: subprocess.CompletedProcess[str] | None = None
    container_name = f"hbfg-{uuid.uuid4().hex[:16]}"
    command_evidence_path: Path | None = None
    try:
        if args.active_seconds <= 0:
            raise InputError("active_seconds must be positive")
        if args.seed < 0:
            raise InputError("seed must be non-negative")
        if args.repeat_index < 1 or args.round_index < 1 or args.attempt_index < 1:
            raise InputError("repeat, round, and attempt indices must be positive")
        if args.repeat_id != f"repeat_{args.repeat_index:03d}":
            raise InputError("repeat_id does not match repeat_index")
        if args.round_index > args.planned_final_round_index:
            raise InputError("round_index exceeds planned_final_round_index")
        if args.round_id != f"round_{args.round_index:03d}":
            raise InputError("round_id does not match round_index")
        if not IDENTIFIER_RE.fullmatch(args.task_key):
            raise InputError("task_key is not a valid Round identifier")
        if args.coverage_scope is not None:
            try:
                load_scope(args.coverage_scope.resolve())
            except (CoverageError, OSError, ValueError) as exc:
                raise InputError(f"Invalid coverage scope: {exc}") from exc

        attempt_dir = args.attempt_dir.resolve()
        repository_relative(attempt_dir)
        if result_path.parent != attempt_dir:
            raise InputError("result_json must be stored directly in attempt_dir")
        if attempt_dir.exists() and any(attempt_dir.iterdir()):
            raise InputError("attempt_dir is not empty; use a new immutable attempt")
        attempt_dir.mkdir(parents=True, exist_ok=True)
        corpus_dir = attempt_dir / "corpus"
        candidates_dir = attempt_dir / "candidates"
        corpus_dir.mkdir(exist_ok=True)
        candidates_dir.mkdir(exist_ok=True)
        (attempt_dir / "observations").mkdir(exist_ok=True)
        limits = {
            "timeout": args.per_call_timeout_seconds,
            "rss_limit_mb": args.rss_limit_mb,
            "max_len": args.max_input_bytes,
            "process_memory_mb": args.process_memory_mb,
            "candidate_sample_limit": args.candidate_sample_limit,
        }
        try:
            validate_limits(limits)
        except ValueError as exc:
            raise InputError(str(exc)) from exc

        validators = common_validators(args)
        resolved = resolve_harness(
            args.harness_record,
            args.strategy_plan,
            args.harness_spec,
            validators["artifact"],
            validators["strategy"],
            validators["spec"],
        )
        if resolved.harness_spec["identity"]["target_api"] != args.target_api:
            raise InputError("target_api differs from HarnessSpec")
        allowed_spec_modes = {
            "structured_baseline": {"controlled_baseline"},
            "bug_aware_static": {"bug_aware_static"},
            "bug_aware_adaptive": {"bug_aware_static", "bug_aware_adaptive"},
        }
        if resolved.harness_spec["identity"]["spec_mode"] not in allowed_spec_modes[
            args.group_id
        ]:
            raise InputError("experimental group differs from HarnessSpec mode")

        input_ref = None
        if args.round_start_corpus_record is not None:
            start_manifest = load_corpus_manifest(
                args.round_start_corpus_record, validators["corpus"]
            )
            copy_corpus(start_manifest, corpus_dir)
            input_ref = corpus_artifact_reference(start_manifest)

        execution_id = f"ex_{uuid.uuid4().hex}"
        active_seconds = int(math.ceil(args.active_seconds))
        round_config = {
            "config_format_version": "1.0",
            "execution_id": execution_id,
            "api_id": args.api_id,
            "target_api": args.target_api,
            "task_key": args.task_key,
            "runtime_image": args.runtime_image,
            "seed": args.seed,
            "active_seconds": active_seconds,
            "harness_binary_ref": file_reference(resolved.binary_path),
            "limits": limits,
            "initialization_included_in_process_budget": True,
            "budget_resolution_seconds": 1,
            "thread_environment": {k: os.environ.get(k) for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")},
        }
        round_config_path = attempt_dir / "round_config.json"
        write_json_atomic(round_config_path, round_config)
        started_at = utc_now()
        active_started_monotonic = time.monotonic()
        argv = docker_command(
            image=args.runtime_image,
            artifact_dir=args.harness_record.resolve().parent,
            attempt_dir=attempt_dir,
            active_seconds=active_seconds,
            seed=args.seed,
            container_name=container_name,
            limits=limits,
        )
        command_evidence_path = attempt_dir / "execution_command.json"
        write_json_atomic(command_evidence_path, {
            "argv": argv,
            "requested_resource_limits": limits,
            "network_mode_requested": "none",
            "runtime_image_requested": args.runtime_image,
        })
        timed_out = False
        try:
            process = subprocess.run(argv, capture_output=True, text=True,
                                     timeout=active_seconds + args.timeout_grace_seconds, check=False)
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            process = subprocess.CompletedProcess(argv, 124, text_output(exc.stdout), text_output(exc.stderr))
            try:
                subprocess.run(["docker", "kill", container_name], capture_output=True, text=True, timeout=30, check=False)
            except (OSError, subprocess.TimeoutExpired):
                pass
        container_state = None
        container_facts = None
        try:
            state_check = subprocess.run(["docker", "inspect", "--format", "{{json .}}", container_name],
                                         capture_output=True, text=True, timeout=30, check=False)
            inspection = {
                "status": "available" if state_check.returncode == 0 else "unavailable",
                "return_code": state_check.returncode,
                "stderr_tail": (state_check.stderr or "")[-2000:],
            }
        except subprocess.TimeoutExpired as exc:
            state_check = None
            inspection = {"status": "timeout", "error": str(exc)}
        except OSError as exc:
            state_check = None
            inspection = {"status": "unavailable", "error": f"{type(exc).__name__}: {exc}"}
        if state_check is not None and state_check.returncode == 0:
            try:
                inspected = json.loads(state_check.stdout)
                container_state = inspected.get("State")
                host_config = inspected.get("HostConfig", {})
                container_config = inspected.get("Config", {})
                container_facts = {
                    "image_id": inspected.get("Image"),
                    "configured_image": container_config.get("Image"),
                    "environment": sorted(container_config.get("Env", [])),
                    "network_mode": host_config.get("NetworkMode"),
                    "memory_bytes": host_config.get("Memory"),
                    "nano_cpus": host_config.get("NanoCpus"),
                    "state": container_state,
                }
            except ValueError:
                pass
        try:
            cleanup_process = subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, text=True, timeout=30, check=False)
            cleanup = {"status": "removed" if cleanup_process.returncode == 0 else "unconfirmed",
                       "return_code": cleanup_process.returncode, "stderr_tail": (cleanup_process.stderr or "")[-2000:]}
        except subprocess.TimeoutExpired as exc:
            cleanup = {"status": "timeout", "error": str(exc)}
        except OSError as exc:
            cleanup = {"status": "unavailable", "error": f"{type(exc).__name__}: {exc}"}
        write_json_atomic(attempt_dir / "container_state.json", {
            "facts": container_facts, "state": container_state,
            "inspection": inspection,
            "cleanup": cleanup,
            "adapter_timed_out": timed_out,
        })
        ended_at = utc_now()
        wall_elapsed = time.monotonic() - active_started_monotonic
        journal_path = attempt_dir / "fuzzer_process.json"
        journal = load_json(journal_path) if journal_path.is_file() else {}
        measured = journal.get("elapsed_seconds") if journal.get("state") == "finished" else None
        if measured is not None and (not isinstance(measured, (int, float)) or isinstance(measured, bool) or measured < 0):
            raise InputError("Invalid fuzzer-process timing journal")
        elapsed = float(measured) if measured is not None else 0.0
        run_log = save_run_log(attempt_dir, process)

        if process.returncode in {125, 126, 127} or journal.get("state") == "launch_failed":
            write_adapter_result(result_path, {
                "status": "infrastructure_failure", "terminal_at": ended_at,
                "active_seconds_consumed": 0.0, "remaining_active_seconds": float(args.active_seconds),
                "failure_category": "container_start_failure", "message": "Fuzzer process did not start",
                "diagnostic_log_file_ref": file_reference(run_log),
                "execution_command_file_ref": file_reference(command_evidence_path),
            })
            return 2

        corpus_id = "corpus_" + hashlib.sha256(
            args.task_key.encode("utf-8")
        ).hexdigest()[:16]
        output_manifest_path = attempt_dir / "corpus_manifest.json"
        output_manifest, output_binding = build_corpus_manifest(
            corpus_dir,
            output_manifest_path,
            corpus_id,
            "round_output",
            args.task_key,
            validators["corpus"],
        )

        coverage_evidence: dict[str, Any] = {
            "status": "not_collected", "location": None, "diagnostic_refs": [],
            "diagnostic_file_refs": [],
        }
        if args.coverage_scope is not None:
            try:
                coverage_path = replay_coverage(
                    scope_path=args.coverage_scope.resolve(),
                    corpus_manifest=output_manifest,
                    corpus_dir=corpus_dir,
                    harness_binary=resolved.binary_path,
                    output_dir=attempt_dir / "coverage",
                    resource_limits=limits,
                    thread_environment={k: os.environ.get(k) for k in
                                        ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")},
                )
                coverage_evidence = {
                    "status": "present",
                    "location": evidence_location(coverage_path, "coverage_summary"),
                    "diagnostic_refs": [],
                    "diagnostic_file_refs": [],
                }
            except (CoverageError, OSError, ValueError) as exc:
                diagnostic_path = attempt_dir / "coverage_failure.log"
                diagnostic_path.write_text(str(exc) + "\n", encoding="utf-8")
                diagnostic_location = evidence_location(diagnostic_path, "coverage_failure")
                coverage_evidence = {
                    "status": "collection_failed", "location": None,
                    "diagnostic_refs": [diagnostic_location["artifact_ref"]],
                    "diagnostic_file_refs": [diagnostic_location],
                }

        _, candidate_binding, candidate_observations = build_candidate_bundle(
            args=args,
            execution_id=execution_id,
            observed_at=ended_at,
            candidates_dir=candidates_dir,
            run_log_path=run_log,
            validator=validators["candidate"],
            artifact=resolved.artifact,
        )
        snapshot_path = attempt_dir / "runtime_snapshot.json"
        snapshot = None
        if snapshot_path.is_file():
            snapshot = validate_runtime_snapshot(
                snapshot_path, validators["runtime"], resolved.artifact
            )

        consumed = min(float(args.active_seconds), elapsed) if measured is not None else float(args.active_seconds)
        budget_evidence = {
            "planned_seconds": float(args.active_seconds), "process_seconds": measured,
            "wall_seconds": wall_elapsed, "outside_process_seconds": None if measured is None else max(0.0, wall_elapsed - elapsed),
            "remaining_seconds": None if measured is None else max(0.0, float(args.active_seconds) - consumed),
            "timing_status": "measured" if measured is not None else "unknown_budget_reserved_no_retry",
            "overrun_seconds": None if measured is None else max(0.0, elapsed - float(args.active_seconds)),
        }
        write_json_atomic(attempt_dir / "budget_evidence.json", budget_evidence)
        if process.returncode != 0:
            result = {
                "status": "target_or_framework_exit",
                "exit_classification": classify_nonzero_exit(
                    process.returncode, container_state, timed_out, candidate_binding is not None
                ),
                "container_oom_killed": bool(container_state and container_state.get("OOMKilled")),
                "adapter_timed_out": timed_out,
                "container_facts_file_ref": file_reference(attempt_dir / "container_state.json"),
                "execution_command_file_ref": file_reference(command_evidence_path),
                "terminal_at": ended_at,
                "active_seconds_consumed": consumed,
                "remaining_active_seconds": max(0.0, float(args.active_seconds) - consumed),
                "return_code": process.returncode,
                "signal_name": signal_name(process.returncode),
                "resume_corpus_binding": output_binding,
                "diagnostic_log_file_ref": file_reference(run_log),
                "budget_evidence_file_ref": file_reference(attempt_dir / "budget_evidence.json"),
            }
            round_record = build_round_record(
                args=args,
                resolved=resolved,
                execution_id=execution_id,
                started_at=started_at,
                ended_at=ended_at,
                elapsed=elapsed,
                process=process,
                round_config=round_config,
                input_corpus_ref=input_ref,
                output_manifest=output_manifest,
                output_manifest_path=output_manifest_path,
                snapshot=snapshot,
                snapshot_path=snapshot_path if snapshot is not None else None,
                run_log_path=run_log,
                candidate_binding=candidate_binding,
                candidate_observations=candidate_observations,
                coverage_evidence=coverage_evidence,
                round_validator=validators["round"],
            )
            round_record_path = attempt_dir / "fuzzing_round_record.json"
            write_json_atomic(round_record_path, round_record)
            result["round_record_file_ref"] = file_reference(round_record_path)
            result["candidate_bundle_binding"] = candidate_binding
            result["budget_complete"] = measured is not None and consumed >= float(args.active_seconds)
            result["budget_timing_status"] = budget_evidence["timing_status"]
            if snapshot is not None:
                result["runtime_snapshot_file_ref"] = file_reference(snapshot_path)
            write_adapter_result(result_path, result)
            return 3

        if snapshot is None:
            raise InputError("Harness completed without a Runtime Snapshot")
        round_record = build_round_record(
            args=args,
            resolved=resolved,
            execution_id=execution_id,
            started_at=started_at,
            ended_at=ended_at,
            elapsed=elapsed,
            process=process,
            round_config=round_config,
            input_corpus_ref=input_ref,
            output_manifest=output_manifest,
            output_manifest_path=output_manifest_path,
            snapshot=snapshot,
            snapshot_path=snapshot_path,
            run_log_path=run_log,
            candidate_binding=candidate_binding,
            candidate_observations=candidate_observations,
            coverage_evidence=coverage_evidence,
            round_validator=validators["round"],
        )
        round_record_path = attempt_dir / "fuzzing_round_record.json"
        write_json_atomic(round_record_path, round_record)
        result = {
            "status": "completed" if measured is not None and consumed >= float(args.active_seconds) else "budget_incomplete",
            "terminal_at": ended_at,
            "active_seconds_consumed": consumed,
            "remaining_active_seconds": (budget_evidence["remaining_seconds"]
                                         if budget_evidence["remaining_seconds"] is not None else 0.0),
            "budget_complete": measured is not None and consumed >= float(args.active_seconds),
            "budget_evidence_file_ref": file_reference(attempt_dir / "budget_evidence.json"),
            "container_facts_file_ref": file_reference(attempt_dir / "container_state.json"),
            "execution_command_file_ref": file_reference(command_evidence_path),
            "budget_timing_status": budget_evidence["timing_status"],
            "round_end_corpus_binding": output_binding,
            "round_record_file_ref": file_reference(round_record_path),
            "runtime_snapshot_file_ref": file_reference(snapshot_path),
            "candidate_bundle_binding": candidate_binding,
        }
        write_adapter_result(result_path, result)
        return 0 if result["status"] == "completed" else 3

    except InputError as exc:
        journal_path = locals().get("attempt_dir")
        journal = {}
        if isinstance(journal_path, Path) and (journal_path / "fuzzer_process.json").is_file():
            try:
                journal = load_json(journal_path / "fuzzer_process.json")
            except InputError:
                pass
        measured = journal.get("elapsed_seconds") if journal.get("state") == "finished" else None
        measured = float(measured) if isinstance(measured, (int, float)) and not isinstance(measured, bool) and math.isfinite(measured) and measured >= 0 else None
        consumed = min(float(args.active_seconds), measured) if measured is not None else (float(args.active_seconds) if process is not None else 0.0)
        result = {
            "status": "method_failure",
            "terminal_at": utc_now(),
            "active_seconds_consumed": consumed,
            "remaining_active_seconds": max(0.0, float(args.active_seconds) - consumed),
            "budget_timing_status": "measured" if measured is not None else ("unknown_budget_reserved_no_retry" if process is not None else "not_started"),
            "message": str(exc),
        }
        if command_evidence_path is not None and command_evidence_path.is_file():
            result["execution_command_file_ref"] = file_reference(command_evidence_path)
        write_adapter_result(result_path, result)
        return 4
    except subprocess.TimeoutExpired as exc:
        message = f"Subprocess exceeded its configured timeout: {exc}"
    except (InfrastructureError, OSError) as exc:
        message = str(exc)
    finally:
        try:
            subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, text=True, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass

    attempt_path = locals().get("attempt_dir")
    journal = {}
    if isinstance(attempt_path, Path) and (attempt_path / "fuzzer_process.json").is_file():
        try:
            journal = load_json(attempt_path / "fuzzer_process.json")
        except InputError:
            pass
    measured = journal.get("elapsed_seconds") if journal.get("state") == "finished" else None
    measured = float(measured) if isinstance(measured, (int, float)) and not isinstance(measured, bool) and math.isfinite(measured) and measured >= 0 else None
    timing_status = "measured" if measured is not None else ("unknown_budget_reserved_no_retry" if process is not None else "not_started")
    consumed = min(float(args.active_seconds), measured) if measured is not None else (float(args.active_seconds) if process is not None else 0.0)
    budget_ref = None
    if isinstance(attempt_path, Path) and attempt_path.is_dir():
        wall_elapsed = max(0.0, time.monotonic() - active_started_monotonic) if active_started_monotonic is not None else 0.0
        budget_path = attempt_path / "budget_evidence.json"
        if not budget_path.is_file():
            write_json_atomic(budget_path, {
                "planned_seconds": float(args.active_seconds),
                "process_seconds": measured,
                "wall_seconds": wall_elapsed,
                "outside_process_seconds": None if measured is None else max(0.0, wall_elapsed - measured),
                "remaining_seconds": None if measured is None else max(0.0, float(args.active_seconds) - min(float(args.active_seconds), measured)),
                "timing_status": timing_status,
                "overrun_seconds": None if measured is None else max(0.0, measured - float(args.active_seconds)),
            })
        budget_ref = file_reference(budget_path)
    run_log_ref = None
    if process is not None and isinstance(attempt_path, Path) and attempt_path.is_dir():
        log_path = attempt_path / "run.log"
        if not log_path.is_file():
            log_path = save_run_log(attempt_path, process)
        run_log_ref = file_reference(log_path)
    result = {
        "status": "infrastructure_failure",
        "terminal_at": utc_now(),
        "active_seconds_consumed": consumed,
        "remaining_active_seconds": max(0.0, float(args.active_seconds) - consumed),
        "budget_timing_status": timing_status,
        "failure_category": "container_start_failure" if process is None else "post_start_adapter_failure",
        "message": message,
    }
    if budget_ref is not None:
        result["budget_evidence_file_ref"] = budget_ref
    if run_log_ref is not None:
        result["diagnostic_log_file_ref"] = run_log_ref
    if isinstance(attempt_path, Path) and (attempt_path / "container_state.json").is_file():
        result["container_facts_file_ref"] = file_reference(attempt_path / "container_state.json")
    if command_evidence_path is not None and command_evidence_path.is_file():
        result["execution_command_file_ref"] = file_reference(command_evidence_path)
    write_adapter_result(result_path, result)
    return 2


def add_schema_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--round-schema", type=Path, default=DEFAULTS["round_schema"])
    parser.add_argument(
        "--runtime-snapshot-schema",
        type=Path,
        default=DEFAULTS["runtime_snapshot_schema"],
    )
    parser.add_argument("--corpus-schema", type=Path, default=DEFAULTS["corpus_schema"])
    parser.add_argument(
        "--harness-artifact-schema",
        type=Path,
        default=DEFAULTS["harness_artifact_schema"],
    )
    parser.add_argument("--strategy-schema", type=Path, default=DEFAULTS["strategy_schema"])
    parser.add_argument("--harness-spec-schema", type=Path, default=DEFAULTS["harness_spec_schema"])
    parser.add_argument(
        "--candidate-bundle-schema",
        type=Path,
        default=DEFAULTS["candidate_bundle_schema"],
    )


def add_harness_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--harness-record", type=Path, required=True)
    parser.add_argument("--strategy-plan", type=Path, required=True)
    parser.add_argument("--harness-spec", type=Path, required=True)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight_parser = subparsers.add_parser("preflight")
    add_harness_arguments(preflight_parser)
    add_schema_arguments(preflight_parser)
    preflight_parser.add_argument("--runtime-image", default=DEFAULT_IMAGE)
    preflight_parser.add_argument("--per-call-timeout-seconds", type=int)
    preflight_parser.add_argument("--rss-limit-mb", type=int)
    preflight_parser.add_argument("--max-input-bytes", type=int)
    preflight_parser.add_argument("--process-memory-mb", type=int)
    preflight_parser.add_argument("--candidate-sample-limit", type=int, default=64)
    preflight_parser.add_argument("--result-json", type=Path, required=True)
    preflight_parser.set_defaults(handler=command_preflight)

    corpus_parser = subparsers.add_parser("init-corpus")
    corpus_parser.add_argument("--corpus-dir", type=Path, required=True)
    corpus_parser.add_argument("--corpus-id", required=True)
    corpus_parser.add_argument("--output", type=Path, required=True)
    corpus_parser.add_argument("--result-json", type=Path)
    corpus_parser.add_argument("--corpus-schema", type=Path, default=DEFAULTS["corpus_schema"])
    corpus_parser.set_defaults(handler=command_init_corpus)

    run_parser = subparsers.add_parser("run")
    add_harness_arguments(run_parser)
    add_schema_arguments(run_parser)
    run_parser.add_argument("--api-id", required=True)
    run_parser.add_argument("--target-api", required=True)
    run_parser.add_argument(
        "--group-id",
        choices=("structured_baseline", "bug_aware_static", "bug_aware_adaptive"),
        required=True,
    )
    run_parser.add_argument("--repeat-id", required=True)
    run_parser.add_argument("--repeat-index", type=int, required=True)
    run_parser.add_argument("--round-id", required=True)
    run_parser.add_argument("--round-index", type=int, required=True)
    run_parser.add_argument("--planned-final-round-index", type=int, default=3)
    run_parser.add_argument("--attempt-index", type=int, default=1)
    run_parser.add_argument("--task-key", required=True)
    run_parser.add_argument("--seed", type=int, required=True)
    run_parser.add_argument("--active-seconds", type=float, required=True)
    run_parser.add_argument("--round-start-corpus-record", type=Path)
    run_parser.add_argument("--attempt-dir", type=Path, required=True)
    run_parser.add_argument("--result-json", type=Path, required=True)
    run_parser.add_argument("--runtime-image", default=DEFAULT_IMAGE)
    run_parser.add_argument("--coverage-scope", type=Path)
    run_parser.add_argument("--timeout-grace-seconds", type=int, default=60)
    run_parser.add_argument("--per-call-timeout-seconds", type=int)
    run_parser.add_argument("--rss-limit-mb", type=int)
    run_parser.add_argument("--max-input-bytes", type=int)
    run_parser.add_argument("--process-memory-mb", type=int)
    run_parser.add_argument("--candidate-sample-limit", type=int, default=64)
    run_parser.add_argument("--runtime-config", type=Path, default=DEFAULTS["runtime_config"])
    run_parser.add_argument(
        "--instrumentation-header", type=Path, default=DEFAULTS["instrumentation_header"]
    )
    run_parser.add_argument(
        "--instrumentation-source", type=Path, default=DEFAULTS["instrumentation_source"]
    )
    run_parser.set_defaults(handler=command_run)
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
