#!/usr/bin/env python3
"""Deterministic EXP013 Crash Case manager.

It ingests Runner-selected Candidate Bundles, creates and validates Case
revisions, performs exact deduplication, records externally executed replay
attempts, and derives descriptive summaries. It does not call an LLM, run
fuzzing, perform semantic deduplication, attribute faults, decide novelty, or
submit reports.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import os
import re
import sys
import uuid
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Install the repository control-plane requirements.") from exc

ANALYZER_ID = "analyze_crash_cases"
ANALYZER_VERSION = "0.3.0"
EXP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = EXP_ROOT.parents[1]
DEFAULT_CASE_SCHEMA = EXP_ROOT / "schemas/crash_case_record.schema.json"
DEFAULT_ROUND_SCHEMA = REPO_ROOT / "experiment/EXP012_adaptive_feedback/schemas/fuzzing_round_record.schema.json"
DEFAULT_BUNDLE_SCHEMA = EXP_ROOT / "schemas/candidate_bundle_record.schema.json"
DEFAULT_POLICY = EXP_ROOT / "policies/crash_analysis_policy.json"
DEFAULT_OUTPUT = EXP_ROOT / "results"
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
KIND_MAP = {
    "crash": "process_termination",
    "sanitizer": "sanitizer_finding",
    "target_exception": "target_exception",
    "oracle_failure": "oracle_violation",
    "resource_anomaly": "resource_anomaly",
}


class AnalyzerError(RuntimeError):
    pass


class InputError(AnalyzerError):
    pass


class ConflictError(AnalyzerError):
    pass


@dataclass
class Run:
    command: str
    started_at: str = field(default_factory=lambda: now())
    created: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)

    def fail(self, item: str, error: Exception) -> None:
        self.errors.append({"item": item, "type": type(error).__name__, "message": str(error)})


@dataclass(frozen=True)
class Context:
    output: Path
    policy_path: Path
    policy: dict[str, Any]
    case_validator: Draft202012Validator
    round_validator: Draft202012Validator
    bundle_validator: Draft202012Validator


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle, object_pairs_hook=no_duplicate_keys)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise InputError(f"cannot read JSON {path}: {exc}") from exc


def encoded(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def canonical_hash(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def confined(path: Path, root: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise InputError(f"{label} escapes {root}: {resolved}") from exc
    return resolved


def repo_file(value: str, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{label} must be a path")
    path = Path(value)
    path = path if path.is_absolute() else REPO_ROOT / path
    path = confined(path, REPO_ROOT, label)
    if not path.is_file():
        raise InputError(f"{label} is missing: {path}")
    return path


def relative(path: Path) -> str:
    return confined(path, REPO_ROOT, "artifact path").relative_to(REPO_ROOT.resolve()).as_posix()


def identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise InputError(f"invalid {label}: {value!r}")
    return value


def safe(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    if not result:
        raise InputError(f"cannot normalize identifier {value!r}")
    return result if result[0].isalpha() else f"x_{result}"


def artifact_ref(artifact_id: str, version: str | int, digest: str) -> dict[str, Any]:
    identifier(artifact_id, "artifact_id")
    if not isinstance(digest, str) or not SHA_RE.fullmatch(digest):
        raise InputError("invalid Artifact content_hash")
    return {"artifact_id": artifact_id, "artifact_version": version, "content_hash": digest}


def location(path: Path, prefix: str) -> dict[str, Any]:
    digest = hash_file(path)
    return {"artifact_ref": artifact_ref(f"{prefix}_{digest[:16]}", "1.0", digest), "file_ref": {"relative_path": relative(path), "content_hash": digest}}


def unique_refs(values: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    table = {json.dumps(item, sort_keys=True): copy.deepcopy(dict(item)) for item in values}
    return [table[key] for key in sorted(table)]


def validator(path: Path) -> Draft202012Validator:
    schema = load_json(path)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def schema_errors(value: Any, check: Draft202012Validator) -> list[str]:
    return [f"{item.json_path}: {item.message}" for item in sorted(check.iter_errors(value), key=lambda error: error.json_path)]


def policy(path: Path) -> dict[str, Any]:
    value = load_json(path)
    required = {
        "policy_format_version", "policy_id", "policy_version", "policy_status",
        "compatibility", "algorithms", "candidate_admission", "replay",
        "deduplication", "revision_control",
    }
    if not isinstance(value, dict) or not required <= set(value):
        raise InputError("Crash Analysis Policy is missing required fields")
    if value["policy_format_version"] != "1.0":
        raise InputError("unsupported Crash Analysis Policy format")
    if value["compatibility"].get("crash_case_record_version") != "1.1":
        raise InputError("Policy is incompatible with Crash Case Record 1.1")
    if value["compatibility"].get("candidate_bundle_record_version") != "1.0":
        raise InputError("Policy is incompatible with Candidate Bundle Record 1.0")
    if value["policy_status"] not in {"draft", "frozen"}:
        raise InputError("unsupported policy_status")
    replay = value["replay"]
    replay_fields = {
        "required_valid_attempts", "maximum_replacement_attempts",
        "replacement_eligible_only_for_invalid_attempts",
        "require_target_api_reached", "reuse_source_run_limits",
        "automatic_success_equivalence", "reviewed_success_equivalence",
        "completed_status_by_success_count",
        "inconclusive_when_valid_attempts_incomplete",
    }
    if not isinstance(replay, dict) or not replay_fields <= set(replay):
        raise InputError("Policy replay section is incomplete")
    required_attempts = replay["required_valid_attempts"]
    if isinstance(required_attempts, bool) or not isinstance(required_attempts, int) or required_attempts < 1:
        raise InputError("required_valid_attempts must be positive")
    expected_keys = {str(index) for index in range(required_attempts + 1)}
    if set(replay["completed_status_by_success_count"]) != expected_keys:
        raise InputError("completed replay status table is incomplete")
    if "exact_match" not in replay["automatic_success_equivalence"]:
        raise InputError("Analyzer 0.1 requires exact_match as automatic equivalence")
    return value


def round_ref(record: Mapping[str, Any], path: Path) -> dict[str, Any]:
    return artifact_ref(record["identity"]["round_id"], record["record_format_version"], hash_file(path))


def analyzer_ref() -> dict[str, Any]:
    return artifact_ref(ANALYZER_ID, ANALYZER_VERSION, hash_file(Path(__file__).resolve()))


def policy_reference(context: Context) -> dict[str, Any]:
    return artifact_ref(context.policy["policy_id"], context.policy["policy_version"], hash_file(context.policy_path))


def normalize_diagnostic(text: str) -> str:
    text = re.sub(r"\b0x[0-9a-fA-F]+\b", "<ADDR>", text)
    text = re.sub(r"\b[A-Za-z]:\\\S+|(?<!\w)/(?:\S+/)*\S+", "<PATH>", text)
    text = re.sub(r"\b(?:thread|tid)[ =:#-]*\d+\b", "<THREAD>", text, flags=re.I)
    return " ".join(text.split())


def signature(kind: str, subtype: str, diagnostic: Path | None, context: Context) -> dict[str, str]:
    text = diagnostic.read_text(encoding="utf-8", errors="replace")[:1024 * 1024] if diagnostic else ""
    frames = [normalize_diagnostic(line) for line in text.splitlines() if re.search(r"at::|c10::|torch::|aten::|libtorch", line)][:5]
    payload = {"observation_kind": kind, "observation_subtype": subtype, "normalized_primary_diagnostic": normalize_diagnostic(text), "normalized_framework_frames": frames}
    return {"algorithm_version": context.policy["algorithms"]["observation_signature"]["algorithm_version"], "signature_hash": canonical_hash(payload)}


def set_validation(record: dict[str, Any], context: Context, warnings: list[dict[str, Any]] | None = None) -> None:
    record["validation"] = {"status": "not_run", "validator_version": None, "validated_at": None, "issues": []}
    errors = schema_errors(record, context.case_validator) + semantic_errors(record)
    issues = [{"issue_id": f"vi_{index + 1:03d}_record_invalid", "severity": "error", "issue_code": "record_invalid", "instance_path": "", "message": message} for index, message in enumerate(errors)]
    issues += warnings or []
    record["validation"] = {"status": "failed" if errors else "passed", "validator_version": ANALYZER_VERSION, "validated_at": now(), "issues": issues}
    final = schema_errors(record, context.case_validator)
    if final:
        raise InputError(f"generated record violates Schema: {final[0]}")
    if errors:
        raise InputError(f"generated record is inconsistent: {errors[0]}")


def semantic_errors(record: Mapping[str, Any]) -> list[str]:
    result: list[str] = []
    if not all(key in record for key in ("identity", "origin", "evidence", "candidate_event")):
        return result
    expected_key = canonical_hash({"fuzzing_round_content_hash": record["origin"]["fuzzing_round_ref"]["content_hash"], "candidate_observation_id": record["origin"]["candidate_observation_id"], "triggering_input_content_hash": record["evidence"]["triggering_input_ref"]["file_ref"]["content_hash"]})
    if record["identity"]["case_key"] != expected_key:
        result.append("Case Key does not match frozen source values")
    if record["identity"]["case_id"] != f"cc_{safe(record['identity']['target_api_id'])}_{expected_key[:16]}":
        result.append("Case ID does not match target API and Case Key")
    observations = record["candidate_event"]["observations"]
    ids = [item["observation_id"] for item in observations]
    if len(ids) != len(set(ids)) or record["candidate_event"]["primary_observation_id"] not in ids:
        result.append("Observation identity is ambiguous")
    ordinals = [item["ordinal"] for item in record["reproduction"]["attempts"]]
    if ordinals != list(range(1, len(ordinals) + 1)):
        result.append("Replay ordinals are not contiguous")
    dedup = record["deduplication"]
    if dedup["case_role"] == "duplicate_member" and dedup["representative_case_ref"]["artifact_id"] == record["identity"]["case_id"]:
        result.append("Duplicate Case refers to itself")
    novelty, match = record["novelty_assessment"]["status"], record["historical_matching"]["match_status"]
    if novelty == "known_bug_rediscovery" and match != "confirmed_match":
        result.append("Known rediscovery lacks a confirmed historical match")
    if novelty == "potentially_novel" and match != "no_match":
        result.append("Potential novelty lacks a completed no-match result")
    return result


def admission(kind: str, tier: str | None, invocation: str | None, refs: list[dict[str, Any]], context: Context) -> dict[str, Any]:
    if kind == "oracle_violation":
        action = context.policy["candidate_admission"]["oracle_tier_actions"].get(tier)
        if action not in {"direct", "conditional"}:
            raise InputError("Oracle Case requires tier_1_exact or tier_2_validated evidence")
        basis = "tier_1_oracle_violation" if tier == "tier_1_exact" else "tier_2_oracle_violation"
    else:
        action = context.policy["candidate_admission"]["observation_actions"].get(kind)
        basis = {"process_termination": "native_process_termination", "sanitizer_finding": "sanitizer_finding", "target_exception": "unexpected_target_exception", "resource_anomaly": "abnormal_resource_growth"}.get(kind)
    if action not in {"direct", "conditional"} or basis is None:
        raise InputError(f"unsupported Candidate type: {kind}")
    reached = invocation is not None
    return {"status": "admitted" if action == "direct" and reached else "pending", "kind": action, "basis_code": basis, "condition_assessments": [{"condition_kind": "target_api_reached", "status": "satisfied" if reached else "unresolved", "evidence_refs": refs if reached else []}, {"condition_kind": "evidence_sufficient", "status": "satisfied", "evidence_refs": refs}], "rejection_reason_codes": [], "evidence_refs": refs}


def verified_location(value: Mapping[str, Any], label: str) -> tuple[dict[str, Any], Path]:
    if not isinstance(value, dict) or set(value) != {"artifact_ref", "file_ref"}:
        raise InputError(f"{label} must be an Evidence Location")
    ref = value["file_ref"]
    path = repo_file(ref.get("relative_path"), f"{label}.file_ref")
    digest = hash_file(path)
    if digest != ref.get("content_hash") or digest != value["artifact_ref"].get("content_hash"):
        raise InputError(f"{label} hash mismatch")
    return copy.deepcopy(dict(value)), path


def initial_record(
    round_path: Path,
    round_record: Mapping[str, Any],
    bundle: Mapping[str, Any],
    candidate: Mapping[str, Any],
    context: Context,
) -> dict[str, Any]:
    errors = schema_errors(round_record, context.round_validator)
    if errors:
        raise InputError(f"invalid Fuzzing Round: {errors[0]}")
    if round_record["validation"]["validation_status"] != "passed" or round_record["attempt_selection"]["status"] != "selected_as_round_result":
        raise InputError("Fuzzing Round must be validated and selected")
    candidate_id = identifier(candidate["candidate_id"], "candidate_id")
    matches = [entry for entry in round_record["evidence"]["candidate_evidence"]["observations"] if entry["candidate_id"] == candidate_id]
    if len(matches) != 1:
        raise InputError("Candidate Bundle item must resolve to exactly one Round observation")
    source = matches[0]
    kind = KIND_MAP.get(source["observation_kind"])
    if kind is None or candidate["observation_kind"] != source["observation_kind"]:
        raise InputError("Candidate Bundle and Round observation kinds disagree")
    subtype = candidate["observation_subtype"]
    invocation = candidate["target_invocation_id"]
    iteration = candidate["iteration_index"]
    tier = candidate["oracle_evidence_tier"]
    input_ref, input_path = verified_location(candidate["triggering_input"], "triggering input")
    diagnostic_value = candidate["primary_diagnostic"]
    if diagnostic_value is None:
        diagnostic_ref, diagnostic_path = None, None
    else:
        diagnostic_ref, diagnostic_path = verified_location(diagnostic_value, "primary diagnostic")
    refs = unique_refs(source["evidence_refs"])
    observation = {
        "observation_id": f"obs_{safe(candidate_id)}",
        "kind": kind,
        "subtype": subtype,
        "signature": signature(kind, subtype, diagnostic_path, context),
        "oracle_evidence_tier": tier if kind == "oracle_violation" else None,
        "threshold_config_ref": copy.deepcopy(round_record["source_context"]["fuzzing_config_ref"]) if kind == "resource_anomaly" else None,
        "evidence_refs": refs,
    }
    source_ref = round_ref(round_record, round_path)
    case_key = canonical_hash({"fuzzing_round_content_hash": source_ref["content_hash"], "candidate_observation_id": candidate_id, "triggering_input_content_hash": input_ref["file_ref"]["content_hash"]})
    api_id = round_record["identity"]["target_api_id"]
    case_id = f"cc_{safe(api_id)}_{case_key[:16]}"
    runtime = round_record["evidence"]["runtime_snapshot"]
    supporting = unique_refs(refs + round_record["evidence"]["run_log_refs"] + round_record["execution"]["termination"]["diagnostic_refs"] + [round_record["source_context"]["harness_artifact_ref"]])
    record = {
        "record_format_version": "1.1", "record_type": "crash_case",
        "identity": {"case_id": case_id, "case_key": case_key, "target_api_id": api_id},
        "revision": {"revision_number": 1, "created_at": now(), "parent_revision_ref": None, "revision_reason": "initial_capture"},
        "workflow_status": "captured",
        "origin": {"fuzzing_round_ref": source_ref, "feedback_decision_ref": None, "candidate_bundle_ref": copy.deepcopy(round_record["evidence"]["candidate_evidence"]["bundle_ref"]), "candidate_observation_id": candidate_id, "iteration_index": iteration, "target_invocation_id": invocation},
        "candidate_event": {"observed_at": candidate["observed_at"], "primary_observation_id": observation["observation_id"], "observations": [observation]},
        "admission": admission(kind, tier, invocation, refs, context),
        "evidence": {"triggering_input_ref": input_ref, "primary_diagnostic_ref": diagnostic_ref, "runtime_snapshot_ref": copy.deepcopy(runtime["location"]["artifact_ref"]) if runtime["status"] == "present" else None, "supporting_evidence_refs": supporting},
        "api_behavior_assessment": {"status": "not_assessed", "rationale": None, "evidence_refs": []},
        "fault_attribution": {"status": "not_assessed", "confidence": None, "rationale": None, "evidence_refs": []},
        "deduplication": {"status": "pending", "case_role": "unassigned", "cluster_id": None, "exact_fingerprint": None, "assignment_kind": "not_assigned", "representative_case_ref": None, "rationale": None},
        "reproduction": {"policy_ref": policy_reference(context), "status": "not_attempted", "attempts": [], "minimized_input_ref": None, "minimal_cpp_reproducer_ref": None, "python_reproducer_ref": None, "cross_validation_refs": []},
        "historical_matching": {"search_status": "not_started", "scope_status": "not_defined", "searched_at": None, "search_protocol_version": None, "search_evidence_ref": None, "sources": [], "version_range": None, "match_status": "not_assessed", "candidate_matches": [], "selected_match_ref": None, "rationale": None},
        "novelty_assessment": {"status": "not_assessed", "rationale": None, "evidence_refs": [], "external_confirmation": None},
        "human_review": {"status": "not_reviewed", "reviewed_at": None, "reviewed_aspects": [], "conclusion": "not_assessed", "summary": None},
        "unresolved_questions": [], "validation": {"status": "not_run", "validator_version": None, "validated_at": None, "issues": []},
        "provenance": {"builder_artifact_ref": analyzer_ref(), "canonicalization_version": "1.0", "generated_at": now()},
    }
    set_validation(record, context)
    return record


def write_bytes_atomic(path: Path, data: bytes, overwrite: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise ConflictError(f"refusing to overwrite {path}")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_atomic(path: Path, value: Any, overwrite: bool = False) -> None:
    write_bytes_atomic(path, encoded(value), overwrite)


@contextmanager
def locked(directory: Path, lock_name: str = ".case.lock"):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / lock_name).open("a") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def case_dir(context: Context, case_id: str) -> Path:
    return confined(context.output / "cases" / case_id, context.output, "Case directory")


def case_path(context: Context, case_id: str, revision: int) -> Path:
    return case_dir(context, case_id) / "records" / f"{case_id}_r{revision:03d}.json"


def selected_case_ids(context: Context, selected: Sequence[str]) -> list[str]:
    if selected:
        return sorted(set(identifier(item, "case_id") for item in selected))
    root = context.output / "cases"
    return sorted(path.name for path in root.iterdir() if path.is_dir() and ID_RE.fullmatch(path.name)) if root.is_dir() else []


def history(context: Context, case_id: str) -> list[tuple[Path, dict[str, Any]]]:
    paths = sorted((case_dir(context, case_id) / "records").glob(f"{case_id}_r*.json"))
    if not paths:
        raise InputError(f"Case not found: {case_id}")
    records = [(path, load_json(path)) for path in paths]
    for path, record in records:
        errors = schema_errors(record, context.case_validator)
        if errors:
            raise InputError(f"invalid Case record {path}: {errors[0]}")
        if record["identity"]["case_id"] != case_id:
            raise InputError(f"Case identity mismatch: {path}")
    if [record["revision"]["revision_number"] for _, record in records] != list(range(1, len(records) + 1)):
        raise InputError(f"non-contiguous revision chain: {case_id}")
    for index, (path, record) in enumerate(records[1:], 1):
        expected = artifact_ref(case_id, index, hash_file(records[index - 1][0]))
        if record["revision"]["parent_revision_ref"] != expected:
            raise InputError(f"invalid parent reference: {path}")
        previous = records[index - 1][1]
        for immutable in context.policy["revision_control"]["immutable_paths"]:
            if json_pointer(record, immutable) != json_pointer(previous, immutable):
                raise InputError(f"immutable field changed at {immutable}: {path}")
    return records


def new_revision(path: Path, record: Mapping[str, Any], reason: str) -> dict[str, Any]:
    result = copy.deepcopy(dict(record)); number = record["revision"]["revision_number"] + 1
    result["revision"] = {"revision_number": number, "created_at": now(), "parent_revision_ref": artifact_ref(record["identity"]["case_id"], number - 1, hash_file(path)), "revision_reason": reason}
    result["provenance"] = {"builder_artifact_ref": analyzer_ref(), "canonicalization_version": "1.0", "generated_at": now()}
    return result


class RoundIndex:
    def __init__(self, roots: Sequence[Path], check: Draft202012Validator):
        self.items: dict[tuple[str, str, str], dict[str, Any]] = {}
        for root in sorted({item.resolve() for item in roots}, key=lambda item: item.as_posix()):
            if not root.is_dir():
                raise InputError(f"Round root is missing: {root}")
            for path in sorted(root.rglob("*.json")):
                try:
                    record = load_json(path)
                except InputError:
                    continue
                if not isinstance(record, dict) or record.get("record_type") != "fuzzing_round" or schema_errors(record, check):
                    continue
                ref = round_ref(record, path); key = (ref["artifact_id"], str(ref["artifact_version"]), ref["content_hash"])
                if key in self.items:
                    raise InputError(f"duplicate Fuzzing Round reference: {key}")
                self.items[key] = record

    def resolve(self, ref: Mapping[str, Any]) -> dict[str, Any]:
        key = (str(ref["artifact_id"]), str(ref["artifact_version"]), str(ref["content_hash"]))
        if key not in self.items:
            raise InputError(f"unresolved Fuzzing Round reference: {key}")
        return self.items[key]


def exact_fingerprint(record: Mapping[str, Any], round_record: Mapping[str, Any], context: Context) -> dict[str, str]:
    table = {item["observation_id"]: item for item in record["candidate_event"]["observations"]}
    primary = table[record["candidate_event"]["primary_observation_id"]]
    payload = {"target_api_id": record["identity"]["target_api_id"], "harness_artifact_content_hash": round_record["source_context"]["harness_artifact_ref"]["content_hash"], "primary_observation_kind": primary["kind"], "primary_observation_subtype": primary["subtype"], "primary_observation_signature_hash": primary["signature"]["signature_hash"], "triggering_input_content_hash": record["evidence"]["triggering_input_ref"]["file_ref"]["content_hash"]}
    return {"algorithm_version": context.policy["algorithms"]["exact_fingerprint"]["algorithm_version"], "fingerprint_hash": canonical_hash(payload)}


def cmd_ingest(args: argparse.Namespace, context: Context, run: Run) -> None:
    execution_index = load_json(args.execution_index)
    tasks = execution_index.get("tasks") if isinstance(execution_index, dict) else None
    if not isinstance(tasks, dict):
        raise InputError("execution_index.tasks must be an object")
    selected = set(args.round_id)
    for task_key, task in sorted(tasks.items()):
        try:
            if not isinstance(task, dict) or not isinstance(task.get("round_record_path"), str):
                continue
            round_path = repo_file(task["round_record_path"], "round_record_path")
            round_record = load_json(round_path)
            round_id = round_record.get("identity", {}).get("round_id")
            if selected and round_id not in selected:
                continue
            errors = schema_errors(round_record, context.round_validator)
            if errors:
                raise InputError(f"invalid Fuzzing Round: {errors[0]}")
            evidence = round_record["evidence"]["candidate_evidence"]
            if evidence["status"] == "absent":
                run.skipped.append(str(round_id))
                continue
            bundle_file_ref = evidence.get("bundle_file_ref")
            if not isinstance(bundle_file_ref, dict):
                raise InputError("Candidate evidence has no bundle_file_ref")
            bundle_path = repo_file(bundle_file_ref.get("relative_path"), "bundle_file_ref")
            if hash_file(bundle_path) != bundle_file_ref.get("content_hash"):
                raise InputError("Candidate Bundle file hash mismatch")
            bundle = load_json(bundle_path)
            bundle_errors = schema_errors(bundle, context.bundle_validator)
            if bundle_errors:
                raise InputError(f"invalid Candidate Bundle: {bundle_errors[0]}")
            bundle_ref = evidence["bundle_ref"]
            identity = bundle["identity"]
            if bundle_ref != artifact_ref(identity["bundle_id"], identity["artifact_version"], canonical_hash(bundle)):
                raise InputError("Candidate Bundle Artifact Reference mismatch")
            bundle_ids = [item["candidate_id"] for item in bundle["candidates"]]
            round_ids = [item["candidate_id"] for item in evidence["observations"]]
            if len(bundle_ids) != len(set(bundle_ids)) or sorted(bundle_ids) != sorted(round_ids):
                raise InputError("Candidate Bundle and Round candidate sets disagree")
            for candidate in sorted(bundle["candidates"], key=lambda value: value["candidate_id"]):
                label = f"{round_id}#{candidate['candidate_id']}"
                record = initial_record(round_path, round_record, bundle, candidate, context)
                case_id = record["identity"]["case_id"]
                target = case_path(context, case_id, 1)
                if args.dry_run:
                    if target.exists() and load_json(target)["identity"]["case_key"] == record["identity"]["case_key"]:
                        run.skipped.append(label)
                    elif target.exists():
                        raise ConflictError(f"Case collision: {target}")
                    else:
                        run.created.append(str(target))
                    continue
                with locked(case_dir(context, case_id)):
                    if target.exists():
                        if load_json(target)["identity"]["case_key"] == record["identity"]["case_key"]:
                            run.skipped.append(label)
                            continue
                        raise ConflictError(f"Case collision: {target}")
                    write_atomic(target, record)
                run.created.append(str(target))
        except AnalyzerError as exc:
            run.fail(task_key, exc)
            if args.fail_fast:
                raise


def cmd_validate(args: argparse.Namespace, context: Context, run: Run) -> None:
    for case_id in selected_case_ids(context, args.case_id):
        try:
            for path, record in history(context, case_id):
                errors = schema_errors(record, context.case_validator) + semantic_errors(record)
                if errors: raise InputError(f"{path}: {errors[0]}")
                ref = record["evidence"]["triggering_input_ref"]["file_ref"]; source = REPO_ROOT / ref["relative_path"]
                if not source.is_file() or hash_file(source) != ref["content_hash"]: raise InputError(f"stale triggering input: {path}")
            run.skipped.append(case_id)
        except AnalyzerError as exc:
            run.fail(case_id, exc)
            if args.fail_fast: raise


def cmd_deduplicate(args: argparse.Namespace, context: Context, run: Run) -> None:
    guard = nullcontext() if args.dry_run else locked(context.output, ".deduplication.lock")
    with guard:
        _cmd_deduplicate_locked(args, context, run)


def _cmd_deduplicate_locked(args: argparse.Namespace, context: Context, run: Run) -> None:
    rounds = RoundIndex(args.round_root, context.round_validator)
    entries = []
    for case_id in selected_case_ids(context, args.case_id):
        try:
            path, record = history(context, case_id)[-1]
            if semantic_errors(record):
                raise InputError("invalid latest Case")
            primary = next(
                item for item in record["candidate_event"]["observations"]
                if item["observation_id"] == record["candidate_event"]["primary_observation_id"]
            )
            if record["admission"]["status"] != "admitted":
                run.skipped.append(case_id)
                continue
            if primary["subtype"] == "unclassified" or record["evidence"]["primary_diagnostic_ref"] is None:
                run.skipped.append(case_id)
                continue
            entries.append((case_id, path, record, exact_fingerprint(record, rounds.resolve(record["origin"]["fuzzing_round_ref"]), context)))
        except AnalyzerError as exc:
            run.fail(case_id, exc)
            if args.fail_fast: raise
    groups: dict[str, list[Any]] = {}
    for entry in entries: groups.setdefault(entry[3]["fingerprint_hash"], []).append(entry)
    for members in groups.values():
        members.sort(key=lambda value: (value[2]["candidate_event"]["observed_at"], value[0])); representative_ref = None
        cluster = f"{context.policy['deduplication']['cluster_id_prefix']}{members[0][2]['identity']['case_key'][:context.policy['deduplication']['cluster_hash_prefix_length']]}"
        for index, (case_id, path, record, fingerprint) in enumerate(members):
            desired = {"status": "completed", "case_role": "representative" if index == 0 else "duplicate_member", "cluster_id": cluster, "exact_fingerprint": fingerprint, "assignment_kind": "not_duplicate" if index == 0 else "exact_duplicate", "representative_case_ref": None if index == 0 else representative_ref, "rationale": None if index == 0 else "Deterministic exact-fingerprint grouping."}
            if record["deduplication"] == desired:
                run.skipped.append(case_id)
                if index == 0: representative_ref = artifact_ref(case_id, record["revision"]["revision_number"], hash_file(path))
                continue
            updated = new_revision(path, record, "analysis_updated"); updated["deduplication"] = desired; updated["workflow_status"] = "under_analysis"; set_validation(updated, context)
            target = case_path(context, case_id, updated["revision"]["revision_number"])
            if index == 0: representative_ref = artifact_ref(case_id, updated["revision"]["revision_number"], hashlib.sha256(encoded(updated)).hexdigest())
            if not args.dry_run:
                with locked(case_dir(context, case_id)): write_atomic(target, updated)
            run.created.append(str(target))


def cmd_replay(args: argparse.Namespace, context: Context, run: Run) -> None:
    manifest = load_json(args.replay_manifest)
    if not isinstance(manifest, dict):
        raise InputError("replay manifest must be an object")
    case_id = identifier(manifest.get("case_id"), "case_id")
    guard = nullcontext() if args.dry_run else locked(case_dir(context, case_id))
    with guard:
        _cmd_replay_locked(args, context, run, manifest, case_id)


def _cmd_replay_locked(
    args: argparse.Namespace, context: Context, run: Run,
    manifest: Mapping[str, Any], case_id: str,
) -> None:
    required_manifest = {"manifest_version", "case_id", "collection_status", "source_limits_verified", "attempts"}
    if set(manifest) != required_manifest or manifest["manifest_version"] != "1.0" or manifest["collection_status"] not in {"completed", "exhausted"} or not isinstance(manifest["source_limits_verified"], bool) or not isinstance(manifest["attempts"], list):
        raise InputError("invalid replay manifest")
    if context.policy["replay"]["reuse_source_run_limits"] and not manifest["source_limits_verified"]:
        raise InputError("Replay did not verify source-run limits")
    path, record = history(context, case_id)[-1]
    if record["deduplication"]["status"] != "completed" or record["deduplication"]["case_role"] != "representative": raise InputError("replay requires a deduplicated representative")
    primary = next(item for item in record["candidate_event"]["observations"] if item["observation_id"] == record["candidate_event"]["primary_observation_id"]); attempts = []
    for ordinal, raw in enumerate(manifest["attempts"], 1):
        required = {"valid_attempt", "execution_path", "target_api_reach_status", "evidence_paths"}
        allowed = required | {"invalid_reason", "observed_event_kind", "observed_signature_hash", "replaces_attempt_id"}
        if not isinstance(raw, dict) or not required <= set(raw) or not set(raw) <= allowed:
            raise InputError(f"invalid replay attempt {ordinal}")
        if not isinstance(raw["valid_attempt"], bool):
            raise InputError(f"valid_attempt must be boolean at attempt {ordinal}")
        if raw["target_api_reach_status"] not in {"reached", "not_reached", "unknown"}:
            raise InputError(f"invalid target_api_reach_status at attempt {ordinal}")
        execution = repo_file(raw["execution_path"], "execution_path")
        evidence = [repo_file(item, "evidence_path") for item in raw["evidence_paths"]]
        valid = raw["valid_attempt"]
        observed_hash, observed_kind = raw.get("observed_signature_hash"), raw.get("observed_event_kind")
        if observed_hash is not None and not SHA_RE.fullmatch(observed_hash): raise InputError("invalid observed_signature_hash")
        if valid and context.policy["replay"]["require_target_api_reached"] and raw["target_api_reach_status"] != "reached":
            raise InputError(f"valid attempt {ordinal} did not reach the Target API")
        replacement = raw.get("replaces_attempt_id")
        if replacement is not None:
            earlier = {item["attempt_id"]: item for item in attempts}
            if replacement not in earlier:
                raise InputError(f"attempt {ordinal} replaces an unknown or later attempt")
            if context.policy["replay"]["replacement_eligible_only_for_invalid_attempts"] and earlier[replacement]["valid_attempt"]:
                raise InputError(f"attempt {ordinal} replaces a valid attempt")
        exact = valid and observed_kind == primary["kind"] and observed_hash == primary["signature"]["signature_hash"]
        execution_ref = artifact_ref(f"replay_execution_{safe(case_id)}_{ordinal:03d}", "1.0", hash_file(execution))
        evidence_refs = [artifact_ref(f"replay_evidence_{hash_file(item)[:16]}", "1.0", hash_file(item)) for item in evidence] or [execution_ref]
        attempts.append({"attempt_id": f"ra_{safe(case_id)}_{ordinal:03d}", "ordinal": ordinal, "replaces_attempt_id": raw.get("replaces_attempt_id"), "valid_attempt": valid, "invalid_reason": None if valid else raw.get("invalid_reason", "unspecified_infrastructure_failure"), "execution_ref": execution_ref, "target_api_reach_status": raw["target_api_reach_status"], "observed_event_kind": observed_kind, "observed_signature_hash": observed_hash, "equivalence_status": "exact_match" if exact else ("different" if valid else "not_evaluable"), "evidence_refs": evidence_refs})
    replay_policy = context.policy["replay"]; valid = [item for item in attempts if item["valid_attempt"]]
    invalid_count = len(attempts) - len(valid)
    required_count = replay_policy["required_valid_attempts"]
    if invalid_count > replay_policy["maximum_replacement_attempts"] or len(valid) > required_count:
        raise InputError("replay counts violate Policy")
    if manifest["collection_status"] == "completed" and len(valid) != required_count:
        raise InputError("completed replay manifest lacks the required valid attempts")
    if manifest["collection_status"] == "exhausted" and (
        len(valid) >= required_count or invalid_count != replay_policy["maximum_replacement_attempts"]
    ):
        raise InputError("exhausted replay manifest has not exhausted replacements")
    status = "inconclusive"
    if len(valid) == required_count:
        successful = sum(
            item["equivalence_status"] in replay_policy["automatic_success_equivalence"]
            for item in valid
        )
        status = replay_policy["completed_status_by_success_count"][str(successful)]
    updated = new_revision(path, record, "new_evidence_received"); updated["reproduction"]["attempts"] = attempts; updated["reproduction"]["status"] = status; updated["workflow_status"] = "under_analysis"; set_validation(updated, context)
    target = case_path(context, case_id, updated["revision"]["revision_number"])
    if not args.dry_run:
        write_atomic(target, updated)
    run.created.append(str(target))


def json_pointer(record: Mapping[str, Any], pointer: str) -> Any:
    value: Any = record
    for token in pointer.lstrip("/").split("/"): value = value[token.replace("~1", "/").replace("~0", "~")]
    return value


def cmd_revise(args: argparse.Namespace, context: Context, run: Run) -> None:
    guard = nullcontext() if args.dry_run else locked(case_dir(context, args.case_id))
    with guard:
        _cmd_revise_locked(args, context, run)


def _cmd_revise_locked(args: argparse.Namespace, context: Context, run: Run) -> None:
    path, current = history(context, args.case_id)[-1]
    draft = load_json(args.draft)
    if not isinstance(draft, dict): raise InputError("draft must be an object")
    for pointer in context.policy["revision_control"]["immutable_paths"]:
        if json_pointer(draft, pointer) != json_pointer(current, pointer): raise InputError(f"draft changes immutable field {pointer}")
    generated = new_revision(path, current, args.revision_reason); draft["revision"] = generated["revision"]; draft["provenance"] = generated["provenance"]; set_validation(draft, context)
    target = case_path(context, args.case_id, draft["revision"]["revision_number"])
    if not args.dry_run:
        write_atomic(target, draft)
    run.created.append(str(target))


def cmd_summarize(args: argparse.Namespace, context: Context, run: Run) -> None:
    rows = []
    for case_id in selected_case_ids(context, args.case_id):
        try:
            path, record = history(context, case_id)[-1]
            if schema_errors(record, context.case_validator) or semantic_errors(record): raise InputError("invalid latest Case")
            primary = next(item for item in record["candidate_event"]["observations"] if item["observation_id"] == record["candidate_event"]["primary_observation_id"])
            rows.append({"case_id": case_id, "target_api_id": record["identity"]["target_api_id"], "event_kind": primary["kind"], "admission_status": record["admission"]["status"], "case_role": record["deduplication"]["case_role"], "reproduction_status": record["reproduction"]["status"], "fault_attribution": record["fault_attribution"]["status"], "historical_match": record["historical_matching"]["match_status"], "novelty_status": record["novelty_assessment"]["status"], "latest_record": relative(path)})
        except AnalyzerError as exc:
            run.fail(case_id, exc)
            if args.fail_fast: raise
    representatives = [row for row in rows if row["case_role"] == "representative"]
    reproducible = [row for row in representatives if row["reproduction_status"] == "stable" and row["fault_attribution"] == "framework"]
    summary = {"record_format_version": "1.0", "generated_at": now(), "counts": {"raw_native_crash_events": sum(row["event_kind"] == "process_termination" for row in rows), "admitted_candidate_events": sum(row["admission_status"] == "admitted" for row in rows), "unique_candidate_clusters": len(representatives), "unique_reproducible_framework_anomalies": len(reproducible), "historical_bug_rediscoveries": sum(row["historical_match"] == "confirmed_match" for row in reproducible), "potentially_novel_bugs": sum(row["novelty_status"] == "potentially_novel" for row in reproducible), "externally_confirmed_novel_bugs": sum(row["novelty_status"] == "externally_confirmed_novel_bug" for row in reproducible)}}
    output = confined(args.summary_root, context.output, "summary root")
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=True); write_atomic(output / "summary.json", summary, overwrite=True)
        csv_path = output / "case_inventory.csv"; temporary = csv_path.with_name(f".{csv_path.name}.{uuid.uuid4().hex}.tmp")
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["case_id"]); writer.writeheader(); writer.writerows(rows); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, csv_path)
    run.created += [str(output / "summary.json"), str(output / "case_inventory.csv")]


def save_run(run: Run, context: Context) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"); run_id = f"crash_{stamp}_{uuid.uuid4().hex[:8]}"; root = context.output / "analysis_runs" / run_id
    write_atomic(root / "run_manifest.json", {"run_format_version": "1.0", "run_id": run_id, "command": run.command, "analyzer_ref": analyzer_ref(), "started_at": run.started_at, "ended_at": now(), "created": run.created, "skipped": run.skipped, "failure_count": len(run.errors), "status": "failed" if run.errors else "completed"})
    if run.errors:
        data = "".join(
            json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n"
            for item in run.errors
        ).encode("utf-8")
        write_bytes_atomic(root / "errors.jsonl", data)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-schema", type=Path, default=DEFAULT_CASE_SCHEMA); parser.add_argument("--round-schema", type=Path, default=DEFAULT_ROUND_SCHEMA); parser.add_argument("--candidate-bundle-schema", type=Path, default=DEFAULT_BUNDLE_SCHEMA); parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY); parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT); parser.add_argument("--dry-run", action="store_true"); parser.add_argument("--fail-fast", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("ingest"); command.add_argument("--execution-index", type=Path, required=True); command.add_argument("--round-id", action="append", default=[])
    command = commands.add_parser("validate"); command.add_argument("--case-id", action="append", default=[])
    command = commands.add_parser("deduplicate"); command.add_argument("--case-id", action="append", default=[]); command.add_argument("--round-root", type=Path, action="append", required=True)
    command = commands.add_parser("replay"); command.add_argument("--replay-manifest", type=Path, required=True)
    command = commands.add_parser("revise"); command.add_argument("--case-id", required=True); command.add_argument("--draft", type=Path, required=True); command.add_argument("--revision-reason", choices=["evidence_updated", "analysis_updated", "human_review_updated", "new_evidence_received", "correction"], required=True)
    command = commands.add_parser("summarize"); command.add_argument("--case-id", action="append", default=[]); command.add_argument("--summary-root", type=Path, default=DEFAULT_OUTPUT / "summaries/latest")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        output = confined(args.output_root, REPO_ROOT, "output root")
        context = Context(output, args.policy.resolve(), policy(args.policy), validator(args.case_schema), validator(args.round_schema), validator(args.candidate_bundle_schema))
        run = Run(args.command)
        {"ingest": cmd_ingest, "validate": cmd_validate, "deduplicate": cmd_deduplicate, "replay": cmd_replay, "revise": cmd_revise, "summarize": cmd_summarize}[args.command](args, context, run)
        if not args.dry_run: save_run(run, context)
        print(json.dumps({"command": args.command, "created": len(run.created), "skipped": len(run.skipped), "failed": len(run.errors), "dry_run": args.dry_run}, ensure_ascii=False))
        return 1 if run.errors else 0
    except AnalyzerError as exc:
        print(f"error: {exc}", file=sys.stderr); return 2


if __name__ == "__main__":
    raise SystemExit(main())
