#!/usr/bin/env python3
"""Build deterministic, evidence-linked Report v5 records from admitted Issues."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import jsonschema


SCRIPT_VERSION = "5.1.1"
SCHEMA_VERSION = "5.1"
MAPPING_VERSION = "5.2"
SCRIPT_PATH = Path(__file__).resolve()
EXP006_DIR = SCRIPT_PATH.parent.parent
PROJECT_ROOT = EXP006_DIR.parent.parent
SCHEMA_PATH = EXP006_DIR / "schemas" / "bug_report_record_v5_1.schema.json"
MAPPING_PATH = EXP006_DIR / "schemas" / "source_to_report_mapping.md"
OUTPUT_ROOT = EXP006_DIR / "bug_reports" / "v5"
LEGACY_SCHEMAS = {
    "2.0": EXP006_DIR / "schemas" / "legacy" / "bug_report_record_v2.schema.json",
    "3.0": EXP006_DIR / "schemas" / "legacy" / "bug_report_record_v3.schema.json",
    "4.0": EXP006_DIR / "schemas" / "legacy" / "bug_report_record_v4.schema.json",
    "5.0": EXP006_DIR / "schemas" / "bug_report_record.schema.json",
}

sys.path.insert(0, str(PROJECT_ROOT / "dataset" / "scripts"))
import collect_issue_sources as inventory_contract  # noqa: E402


class ReportError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def content_hash(report: dict[str, Any]) -> str:
    candidate = json.loads(json.dumps(report))
    candidate["provenance"]["content_hash"] = "sha256:" + "0" * 64
    return sha256_bytes(canonical_bytes(candidate))


def atomic_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def repository_path(text: str, base: Path | None = None) -> Path:
    path = Path(text)
    candidates = [path] if path.is_absolute() else [PROJECT_ROOT / path]
    if base is not None and not path.is_absolute():
        candidates.append(base / path)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise ReportError(f"referenced file does not exist: {text}")


def repository_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError as exc:
        raise ReportError(f"path is outside repository: {path}") from exc


def file_ref(path: Path) -> dict[str, str]:
    return {"local_path": repository_relative(path), "content_hash": sha256_file(path)}


def decode_pointer_token(value: str) -> str:
    if re.search(r"~(?![01])", value):
        raise ReportError(f"invalid JSON pointer token: {value}")
    return value.replace("~1", "/").replace("~0", "~")


def resolve_pointer(document: Any, pointer: str) -> Any:
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise ReportError(f"invalid JSON pointer: {pointer}")
    current = document
    for raw in pointer[1:].split("/"):
        token = decode_pointer_token(raw)
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            raise ReportError(f"unresolved JSON pointer: {pointer}")
    return current


def resolve_locator(locator: dict[str, Any], inventory_dir: Path) -> tuple[Path, str]:
    path = repository_path(locator["artifact_path"], inventory_dir)
    document = read_json(path)
    value = resolve_pointer(document, locator["value"])
    if not isinstance(value, str):
        raise ReportError(f"locator does not resolve to text: {locator}")
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    if locator["locator_type"] == "json_string_line_range":
        lines = text.splitlines()
        start, end = locator["start_line"], locator["end_line"]
        if end > len(lines):
            raise ReportError(f"locator line range exceeds source: {locator}")
        text = "\n".join(lines[start - 1:end])
    text = text.strip()
    if not text:
        raise ReportError(f"locator resolves to empty text: {locator}")
    return path, text


def artifact_id(path: Path) -> str:
    return "src_" + hashlib.sha256(repository_relative(path).encode()).hexdigest()[:16]


def evidence_id(path: Path, locator: dict[str, Any], text: str) -> str:
    key = canonical_bytes([repository_relative(path), locator, text])
    return "ev_" + hashlib.sha256(key).hexdigest()[:16]


class EvidenceStore:
    def __init__(self, inventory_dir: Path):
        self.inventory_dir = inventory_dir
        self.artifacts: dict[Path, dict[str, Any]] = {}
        self.evidence: dict[str, dict[str, Any]] = {}

    def add_artifact(self, path: Path, role: str, kind: str, external_id: str | None = None,
                     url: str | None = None, source_native_state: str | None = None,
                     captured_at: str | None = None) -> str:
        path = path.resolve()
        aid = artifact_id(path)
        item = {"artifact_id": aid, "artifact_role": role, "source_kind": kind,
                "local_path": repository_relative(path), "content_hash": sha256_file(path),
                "external_id": external_id, "url": url,
                "source_native_state": source_native_state, "captured_at": captured_at}
        previous = self.artifacts.get(path)
        if previous is not None:
            for key in ("artifact_id", "artifact_role", "source_kind", "local_path", "content_hash"):
                if previous[key] != item[key]:
                    raise ReportError(f"conflicting source artifact registration for {path}: {key}")
            for key in ("external_id", "url", "source_native_state", "captured_at"):
                if item[key] is None:
                    item[key] = previous[key]
                elif previous[key] is not None and previous[key] != item[key]:
                    raise ReportError(f"conflicting source artifact metadata for {path}: {key}")
        self.artifacts[path] = item
        return aid

    def add(self, locator: dict[str, Any]) -> tuple[str, str]:
        path, text = resolve_locator(locator, self.inventory_dir)
        artifact = self.artifacts.get(path.resolve())
        if artifact is None:
            raise ReportError(f"locator references an unregistered source artifact: {path}")
        aid = artifact["artifact_id"]
        public_locator = {key: value for key, value in locator.items() if key != "artifact_path"}
        eid = evidence_id(path, public_locator, text)
        self.evidence[eid] = {"evidence_id": eid, "source_artifact_ref": aid,
                              "locator": public_locator,
                              "excerpt": text if len(text) <= 4000 else None,
                              "content_hash": sha256_bytes(text.encode())}
        return eid, text


def claim(prefix: str, evidence_ref: str, statement: str, basis: str = "source_explicit") -> dict[str, Any]:
    cid = prefix + "_" + hashlib.sha256((evidence_ref + statement).encode()).hexdigest()[:16]
    return {"claim_id": cid, "statement": statement, "assertion_basis": basis,
            "evidence_refs": [evidence_ref]}


def unresolved(field_path: str, description: str, reason: str = "missing_source") -> dict[str, Any]:
    uid = "unresolved_" + hashlib.sha256((field_path + description).encode()).hexdigest()[:16]
    return {"unresolved_id": uid, "field_path": field_path, "description": description,
            "reason": reason, "evidence_refs": []}


SECTION_NAMES = {
    "to reproduce": "reproduction", "minified repro": "reproduction",
    "minimal reproduction": "reproduction", "reproduction": "reproduction",
    "expected behavior": "expected", "expected": "expected",
    "versions": "environment", "environment": "environment",
    "root cause": "root_cause", "cause": "root_cause",
    "fix": "fix", "final resolution": "fix",
}


def markdown_sections(text: str) -> dict[str, tuple[int, int, str]]:
    """Return only explicitly headed sections; never classify free prose."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    headings: list[tuple[int, str]] = []
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        match = re.match(r"^#{1,6}\s+(.+?)\s*$", stripped)
        if not match:
            match = re.match(r"^\*\*(.+?)\*\*\s*$", stripped)
        if not match:
            continue
        normalized = re.sub(r"[^a-z0-9 ]+", " ", match.group(1).lower())
        normalized = " ".join(normalized.split())
        if normalized in SECTION_NAMES:
            headings.append((index, SECTION_NAMES[normalized]))
    result: dict[str, tuple[int, int, str]] = {}
    for offset, (heading_line, kind) in enumerate(headings):
        start = heading_line + 1
        end = (headings[offset + 1][0] - 1) if offset + 1 < len(headings) else len(lines)
        while start <= end and not lines[start - 1].strip():
            start += 1
        while end >= start and not lines[end - 1].strip():
            end -= 1
        if start <= end and kind not in result:
            result[kind] = (start, end, "\n".join(lines[start - 1:end]).strip())
    return result


def capture_artifacts(capture_path: Path, capture: dict[str, Any], store: EvidenceStore,
                      issue: dict[str, Any]) -> str:
    issue_path = repository_path(capture["issue_path"], capture_path.parent)
    primary = store.add_artifact(
        issue_path, "issue", "github_issue", str(issue["number"]), issue.get("html_url"),
        issue.get("state") if issue.get("state") in {"open", "closed"} else "unknown",
        capture.get("captured_at"),
    )
    for text in capture.get("comments_paths", []):
        store.add_artifact(
            repository_path(text, capture_path.parent), "comment_thread", "github_comments",
            captured_at=capture.get("captured_at"),
        )
    for companion in capture.get("companions", []):
        path = repository_path(companion["local_path"], capture_path.parent)
        role = companion.get("artifact_role", "curation")
        kind = companion.get("source_kind", "other")
        if kind == "curation_table":
            kind = "dataset_record"
        native_state = companion.get("source_native_state")
        if kind == "github_pull_request":
            document = read_json(path)
            if isinstance(document, dict) and document.get("merged") is True:
                native_state = "merged"
        if native_state not in {"open", "closed", "merged", "other", "unknown", None}:
            native_state = "other"
        store.add_artifact(
            path, role, kind if kind in {
                "github_issue", "github_comments", "github_pull_request", "github_commit",
                "dataset_record", "other"} else "other",
            companion.get("external_id"), companion.get("url"), native_state,
            companion.get("captured_at") or capture.get("captured_at"),
        )
    return primary


def index_neutral_source_evidence(capture_path: Path, capture: dict[str, Any],
                                  store: EvidenceStore) -> None:
    """Index captured upstream text without assigning it a Report meaning."""
    issue_path = repository_path(capture["issue_path"], capture_path.parent)
    issue = read_json(issue_path)
    for pointer in ("/title", "/body"):
        if isinstance(resolve_pointer(issue, pointer), str) and resolve_pointer(issue, pointer).strip():
            store.add({"artifact_path": repository_relative(issue_path),
                       "locator_type": "json_pointer", "value": pointer})

    for text in capture.get("comments_paths", []):
        path = repository_path(text, capture_path.parent)
        comments = read_json(path)
        if not isinstance(comments, list):
            raise ReportError(f"captured comments must be an array: {path}")
        for index, item in enumerate(comments):
            if isinstance(item, dict) and isinstance(item.get("body"), str) \
                    and item["body"].strip():
                store.add({"artifact_path": repository_relative(path),
                           "locator_type": "json_pointer", "value": f"/{index}/body"})

    for companion in capture.get("companions", []):
        if companion.get("source_kind") not in {"github_pull_request", "github_commit"}:
            continue
        path = repository_path(companion["local_path"], capture_path.parent)
        document = read_json(path)
        pointers: list[str] = []
        if isinstance(document, dict):
            pointers.extend(pointer for pointer in ("/title", "/body", "/commit/message")
                            if isinstance(_pointer_or_none(document, pointer), str)
                            and _pointer_or_none(document, pointer).strip())
        elif isinstance(document, list):
            pointers.extend(
                f"/{index}/patch"
                for index, item in enumerate(document)
                if isinstance(item, dict) and isinstance(item.get("patch"), str)
                and item["patch"].strip()
            )
        for pointer in pointers:
            store.add({"artifact_path": repository_relative(path),
                       "locator_type": "json_pointer", "value": pointer})


def _pointer_or_none(document: Any, pointer: str) -> Any:
    try:
        return resolve_pointer(document, pointer)
    except ReportError:
        return None


def linked_resolution(capture_path: Path, capture: dict[str, Any], store: EvidenceStore,
                      issue_number: int) -> tuple[str, list[dict[str, Any]], list[str]]:
    """Map only explicitly linked, captured PRs; never infer a fix from Issue state."""
    groups: dict[str, dict[str, Any]] = {}
    for companion in capture.get("companions", []):
        if (companion.get("artifact_role") != "resolution"
                or companion.get("source_kind") != "github_pull_request"):
            continue
        key = str(companion.get("external_id") or companion.get("local_path"))
        path = repository_path(companion["local_path"], capture_path.parent)
        document = read_json(path)
        group = groups.setdefault(key, {"records": [], "patches": []})
        if isinstance(document, dict):
            group["records"].append((path, document))
        elif isinstance(document, list):
            group["patches"].append((path, document))

    claims: list[dict[str, Any]] = []
    artifact_refs: set[str] = set()
    fixed = False
    proposed = False
    for group in groups.values():
        for path, record in group["records"]:
            title = str(record.get("title") or "").strip()
            body = str(record.get("body") or "").strip()
            relation_text = "\n".join(value for value in (title, body) if value)
            closing = re.search(
                rf"(?i)\b(?:fix(?:e[sd])?|close[sd]?|resolve[sd]?)\s+#?{issue_number}\b",
                relation_text,
            )
            direct_url = re.search(
                rf"https://github\.com/[^/]+/[^/]+/issues/{issue_number}\b",
                relation_text,
            )
            if not closing and not direct_url:
                continue
            artifact_refs.add(store.artifacts[path.resolve()]["artifact_id"])
            for field, text in (("title", title), ("body", body)):
                if not text:
                    continue
                locator = {"artifact_path": repository_relative(path),
                           "locator_type": "json_pointer", "value": f"/{field}"}
                eid, resolved = store.add(locator)
                claims.append(claim("resolution", eid, resolved))
            patch_files = [
                patch
                for patch_path, items in group["patches"]
                for patch in items
                if isinstance(patch, dict) and str(patch.get("patch") or "").strip()
            ]
            for patch_path, _ in group["patches"]:
                artifact_refs.add(store.artifacts[patch_path.resolve()]["artifact_id"])
            if record.get("merged") is True and patch_files:
                fixed = True
            elif patch_files:
                proposed = True

    status = "fixed" if fixed else "fix_proposed" if proposed else "unknown"
    unique_claims = {item["claim_id"]: item for item in claims}
    return status, list(unique_claims.values()), sorted(artifact_refs)


def build_report(inventory_path: Path, candidate: dict[str, Any], generated_at: str) -> dict[str, Any]:
    snapshot = candidate.get("snapshot")
    if candidate["screening"]["status"] != "admitted" or snapshot is None:
        raise ReportError("Report construction requires an admitted candidate with a snapshot")
    capture_path = repository_path(snapshot["capture_path"], inventory_path.parent)
    if sha256_file(capture_path) != snapshot["content_hash"]:
        raise ReportError("capture hash does not match candidate inventory")
    capture = read_json(capture_path)
    issue_path = repository_path(capture["issue_path"], capture_path.parent)
    issue = read_json(issue_path)
    if int(issue.get("number", 0)) != candidate["issue_number"]:
        raise ReportError("capture Issue number disagrees with inventory")
    store = EvidenceStore(inventory_path.parent)
    primary_source_ref = capture_artifacts(capture_path, capture, store, issue)
    index_neutral_source_evidence(capture_path, capture, store)
    api_assertions = []
    for association in candidate["screening"]["api_associations"]:
        eid, _ = store.add(association["source_locator"])
        seed = association["api_name"] + association["relation"] + eid
        api_assertions.append({"assertion_id": "api_" + hashlib.sha256(seed.encode()).hexdigest()[:16],
                               "api_name": association["api_name"], "relation": association["relation"],
                               "assertion_basis": "source_explicit", "evidence_refs": [eid]})
    triggers, operations, failures = [], [], []
    gates = candidate["screening"]["admission_gate_locators"]
    for locator in gates["trigger_conditions"]:
        eid, text = store.add(locator)
        triggers.append(claim("trigger", eid, text))
    for locator in gates["operation_contexts"]:
        eid, text = store.add(locator)
        operations.append(claim("operation", eid, text))
    for locator in gates["erroneous_behavior"]:
        eid, text = store.add(locator)
        failures.append(claim("failure", eid, text))
    optional_claims: dict[str, list[dict[str, Any]]] = {
        "expected": [], "root_cause": [], "fix": [], "environment": [], "reproduction": []}
    for kind, (start, end, text) in markdown_sections(str(issue.get("body") or "")).items():
        locator = {"artifact_path": repository_relative(issue_path), "locator_type": "json_string_line_range",
                   "value": "/body", "start_line": start, "end_line": end}
        eid, _ = store.add(locator)
        optional_claims[kind].append(claim(kind, eid, text))
    expected_claims = optional_claims["expected"]
    root_claims = [{**item, "support_status": "reported"} for item in optional_claims["root_cause"]]
    resolution_status, linked_resolution_claims, fix_artifact_refs = linked_resolution(
        capture_path, capture, store, candidate["issue_number"]
    )
    resolution_claims = optional_claims["fix"] + linked_resolution_claims
    reproduction_refs = [ref for item in optional_claims["reproduction"] for ref in item["evidence_refs"]]
    reproduction_text = "\n".join(item["statement"] for item in optional_claims["reproduction"])
    reproduction_availability = (
        "code_provided" if "```" in reproduction_text
        else "steps_provided" if reproduction_refs
        else "unknown"
    )
    environment_facts = [
        {"fact_id": item["claim_id"].replace("environment_", "env_"),
         "name": "reported_environment", "value": item["statement"],
         "evidence_refs": item["evidence_refs"]}
        for item in optional_claims["environment"]
    ]
    unresolved_items = [
        unresolved(path, description)
        for present, path, description in (
            (root_claims, "/reported_diagnosis/root_cause_claims", "No explicit root-cause statement was mapped."),
            (resolution_status != "unknown", "/resolution/status",
             "No explicit source evidence established a fix disposition."),
            (expected_claims, "/reported_behavior/expected_behavior_claims", "No explicit expected behavior was mapped."),
            (False, "/reported_behavior/historical_oracle_claims", "No explicit historical oracle was mapped."),
        ) if not present
    ]
    if reproduction_availability == "unknown":
        unresolved_items.append(unresolved(
            "/reported_behavior/reproduction",
            "No explicitly labelled reproduction section or captured reproduction artifact was mapped.",
            reason="ambiguous_source",
        ))
    repository_slug = re.sub(r"[^a-z0-9]+", "_", candidate["repository"].lower()).strip("_")
    report_id = f"br_{repository_slug}_{candidate['issue_number']}"
    report = {
        "schema_version": SCHEMA_VERSION,
        "identity": {"report_id": report_id, "repository": candidate["repository"],
                     "issue_number": candidate["issue_number"], "canonical_url": candidate["canonical_url"]},
        "revision_information": {"revision_number": 1, "parent_revision_ref": None,
                                 "revision_trigger": "initial_mapping"},
        "source_bundle": {"inventory_ref": file_ref(inventory_path),
                          "primary_source_ref": primary_source_ref,
                          "comments_capture_status": (
                              "complete" if capture.get("comments_complete") is True
                              else "partial" if capture.get("comments_paths")
                              else "unavailable"
                          ),
                          "source_artifacts": sorted(store.artifacts.values(), key=lambda x: x["artifact_id"])},
        "evidence_items": sorted(store.evidence.values(), key=lambda x: x["evidence_id"]),
        "scope_assertions": {"api_assertions": api_assertions},
        "reported_behavior": {"trigger_claims": triggers, "operation_contexts": operations,
                              "failure_observations": failures, "expected_behavior_claims": expected_claims,
                              "historical_oracle_claims": [], "environment_facts": environment_facts,
                              "reproduction": {"availability": reproduction_availability,
                                               "source_evidence_refs": reproduction_refs,
                                               "validation_status": "not_attempted"}},
        "reported_diagnosis": {"root_cause_claims": root_claims},
        "resolution": {"status": resolution_status,
                       "resolution_claims": resolution_claims,
                       "fix_artifact_refs": fix_artifact_refs},
        "upstream_disposition": {
            "status": "reported", "evidence_refs": api_assertions[0]["evidence_refs"]},
        "unresolved_information": unresolved_items,
        "provenance": {"builder_id": "build_bug_report_json", "builder_version": SCRIPT_VERSION,
                       "generation_run_id": "run_" + uuid.uuid4().hex[:16],
                       "input_artifact_refs": [file_ref(inventory_path), file_ref(capture_path)],
                       "mapping_ref": file_ref(MAPPING_PATH), "generated_at": generated_at,
                       "content_hash": "sha256:" + "0" * 64},
        "review": {"validation_status": "passed", "validation_issues": [],
                   "human_review_status": "not_reviewed", "reviewed_by": None, "reviewed_at": None},
    }
    report["provenance"]["content_hash"] = content_hash(report)
    return report


def schema_for(version: str) -> dict[str, Any]:
    path = SCHEMA_PATH if version == SCHEMA_VERSION else LEGACY_SCHEMAS.get(version)
    if path is None or not path.is_file():
        raise ReportError(f"unsupported Report schema_version: {version}")
    return read_json(path)


def structural_errors(report: dict[str, Any]) -> list[str]:
    validator = jsonschema.Draft202012Validator(schema_for(str(report.get("schema_version", ""))),
                                                format_checker=jsonschema.FormatChecker())
    return [f"{'.'.join(str(p) for p in error.absolute_path) or '$'}: {error.message}"
            for error in sorted(validator.iter_errors(report), key=lambda e: list(e.absolute_path))]


def semantic_errors(report: dict[str, Any]) -> list[str]:
    errors = structural_errors(report)
    if errors or report.get("schema_version") != SCHEMA_VERSION:
        return errors
    artifacts = report["source_bundle"]["source_artifacts"]
    artifact_by_id = {item["artifact_id"]: item for item in artifacts}
    artifact_ids = set(artifact_by_id)
    evidence_ids = {item["evidence_id"] for item in report["evidence_items"]}
    if report["source_bundle"]["primary_source_ref"] not in artifact_ids:
        errors.append("source_bundle.primary_source_ref is unresolved")
    if len(artifact_ids) != len(artifacts):
        errors.append("duplicate source artifact IDs")
    if len(evidence_ids) != len(report["evidence_items"]):
        errors.append("duplicate Evidence IDs")
    resolved_artifacts: dict[str, Path] = {}
    for item in artifacts:
        try:
            path = repository_path(item["local_path"])
            resolved_artifacts[item["artifact_id"]] = path
            if item["artifact_id"] != artifact_id(path):
                errors.append(f"source artifact ID mismatch: {item['artifact_id']}")
            if item["content_hash"] != sha256_file(path):
                errors.append(f"source artifact hash mismatch: {item['artifact_id']}")
        except (OSError, ReportError) as exc:
            errors.append(f"source artifact unavailable: {item['artifact_id']}: {exc}")
    primary_ref = report["source_bundle"]["primary_source_ref"]
    primary_artifact = artifact_by_id.get(primary_ref)
    primary_path = resolved_artifacts.get(primary_ref)
    if primary_artifact is not None:
        if primary_artifact["artifact_role"] != "issue" \
                or primary_artifact["source_kind"] != "github_issue":
            errors.append("primary source must be a captured GitHub Issue")
        if primary_artifact.get("external_id") != str(report["identity"]["issue_number"]):
            errors.append("primary source external_id disagrees with Report identity")
        if primary_artifact.get("url") != report["identity"]["canonical_url"]:
            errors.append("primary source URL disagrees with Report identity")
    if primary_path is not None:
        try:
            primary_record = read_json(primary_path)
            if int(primary_record.get("number", 0)) != report["identity"]["issue_number"]:
                errors.append("primary Issue number disagrees with Report identity")
            if primary_record.get("html_url") != report["identity"]["canonical_url"]:
                errors.append("primary Issue URL disagrees with Report identity")
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            errors.append(f"primary Issue cannot be checked: {exc}")
    for item in report["evidence_items"]:
        source_ref = item["source_artifact_ref"]
        if source_ref not in artifact_ids:
            errors.append(f"unresolved Evidence artifact: {item['evidence_id']}")
            continue
        path = resolved_artifacts.get(source_ref)
        if path is None:
            continue
        locator = {"artifact_path": repository_relative(path), **item["locator"]}
        try:
            _, text = resolve_locator(locator, PROJECT_ROOT)
        except (OSError, ReportError, json.JSONDecodeError) as exc:
            errors.append(f"Evidence locator failed: {item['evidence_id']}: {exc}")
            continue
        if item["content_hash"] != sha256_bytes(text.encode()):
            errors.append(f"Evidence content hash mismatch: {item['evidence_id']}")
        expected_excerpt = text if len(text) <= 4000 else None
        if item["excerpt"] != expected_excerpt:
            errors.append(f"Evidence excerpt mismatch: {item['evidence_id']}")
    def refs(value: Any) -> Iterable[str]:
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "evidence_refs" or key == "source_evidence_refs":
                    yield from child
                else:
                    yield from refs(child)
        elif isinstance(value, list):
            for child in value:
                yield from refs(child)
    for ref in refs(report):
        if ref not in evidence_ids:
            errors.append(f"unresolved Evidence reference: {ref}")
    for ref in report["resolution"]["fix_artifact_refs"]:
        if ref not in artifact_ids:
            errors.append(f"unresolved fix artifact reference: {ref}")
    for name, reference in [
        ("source_bundle.inventory_ref", report["source_bundle"]["inventory_ref"]),
        ("provenance.mapping_ref", report["provenance"]["mapping_ref"]),
        *[(f"provenance.input_artifact_refs[{index}]", reference)
          for index, reference in enumerate(report["provenance"]["input_artifact_refs"])],
    ]:
        try:
            path = repository_path(reference["local_path"])
            if reference["content_hash"] != sha256_file(path):
                errors.append(f"{name} hash mismatch")
        except (OSError, ReportError) as exc:
            errors.append(f"{name} unavailable: {exc}")
    reproduction = report["reported_behavior"]["reproduction"]
    if reproduction["availability"] in {"code_provided", "steps_provided"} \
            and not reproduction["source_evidence_refs"]:
        errors.append("provided reproduction has no source Evidence")
    if reproduction["availability"] == "not_provided" and reproduction["source_evidence_refs"]:
        errors.append("not_provided reproduction has source Evidence")
    resolution = report["resolution"]
    if resolution["status"] in {"fixed", "fix_proposed", "no_fix"} \
            and not resolution["resolution_claims"]:
        errors.append("non-unknown resolution has no claim")
    if resolution["status"] in {"fixed", "fix_proposed"} and not resolution["fix_artifact_refs"]:
        errors.append("fixed/proposed resolution has no fix artifact")
    review = report["review"]
    if review["human_review_status"] == "approved" \
            and (not review["reviewed_by"] or not review["reviewed_at"]):
        errors.append("approved review requires reviewer and timestamp")
    if report["provenance"]["content_hash"] != content_hash(report):
        errors.append("provenance.content_hash mismatch")
    return sorted(set(errors))


def validate_report(report: dict[str, Any]) -> None:
    errors = semantic_errors(report)
    if errors:
        raise ReportError("Report validation failed:\n- " + "\n- ".join(errors))


def validate_revision_chain(directory: Path) -> list[dict[str, Any]]:
    paths = sorted(directory.glob("revision_*.json"))
    if not paths:
        raise ReportError(f"Report revision chain is empty: {directory}")
    reports = [read_json(path) for path in paths]
    report_id = reports[0].get("identity", {}).get("report_id")
    for index, current in enumerate(reports, start=1):
        errors = structural_errors(current)
        if errors:
            raise ReportError("Report revision is structurally invalid:\n- " + "\n- ".join(errors))
        if current.get("schema_version") == SCHEMA_VERSION \
                and current.get("provenance", {}).get("content_hash") != content_hash(current):
            raise ReportError(f"Report revision {index} content hash mismatch")
        revision = current.get("revision_information", {})
        if current.get("identity", {}).get("report_id") != report_id:
            raise ReportError("Report revision chain contains multiple Report IDs")
        if revision.get("revision_number") != index:
            raise ReportError("Report revision numbers must be contiguous and start at 1")
        parent = revision.get("parent_revision_ref")
        if index == 1:
            if parent is not None:
                raise ReportError("Report revision 1 must not have a parent")
            continue
        previous = reports[index - 2]
        expected = {
            "record_id": previous["identity"]["report_id"],
            "record_version": previous["revision_information"]["revision_number"],
            "content_hash": previous["provenance"]["content_hash"],
        }
        if parent != expected:
            raise ReportError(f"Report revision {index} has an invalid parent reference")
    return reports


def semantic_signature(report: dict[str, Any]) -> str:
    value = json.loads(json.dumps(report))
    value["revision_information"] = {"revision_number": 0, "parent_revision_ref": None,
                                     "revision_trigger": "initial_mapping"}
    value["provenance"].update({"generation_run_id": "run", "generated_at": "1970-01-01T00:00:00Z",
                                "content_hash": "sha256:" + "0" * 64})
    return sha256_bytes(canonical_bytes(value))


def write_revision(report: dict[str, Any], dry_run: bool) -> tuple[str, Path]:
    directory = OUTPUT_ROOT / report["identity"]["repository"].replace("/", "_") / report["identity"]["report_id"]
    revisions = sorted(directory.glob("revision_*.json")) if directory.is_dir() else []
    if revisions:
        latest = read_json(revisions[-1])
        if semantic_signature(latest) == semantic_signature(report):
            return "reused", revisions[-1]
        mapping_changed = (
            latest.get("schema_version") != report.get("schema_version")
            or latest.get("provenance", {}).get("builder_version")
            != report.get("provenance", {}).get("builder_version")
            or latest.get("provenance", {}).get("mapping_ref")
            != report.get("provenance", {}).get("mapping_ref")
        )
        report["revision_information"] = {
            "revision_number": latest["revision_information"]["revision_number"] + 1,
            "parent_revision_ref": {"record_id": latest["identity"]["report_id"],
                                    "record_version": latest["revision_information"]["revision_number"],
                                    "content_hash": latest["provenance"]["content_hash"]},
            "revision_trigger": "mapping_updated" if mapping_changed else "source_updated",
        }
        report["provenance"]["content_hash"] = content_hash(report)
        validate_report(report)
    target = directory / f"revision_{report['revision_information']['revision_number']:03d}.json"
    if not dry_run:
        atomic_write(target, report)
    return "dry_run" if dry_run else "generated", target


def build_candidates(inventory_path: Path, selected_ids: set[str] | None, dry_run: bool) -> list[dict[str, Any]]:
    inventory = read_json(inventory_path)
    inventory_contract.validate_inventory(inventory, PROJECT_ROOT)
    candidates = [item for item in inventory["candidates"]
                  if item["screening"]["status"] == "admitted"
                  and (selected_ids is None or item["candidate_id"] in selected_ids)]
    if selected_ids is not None:
        missing = selected_ids - {item["candidate_id"] for item in candidates}
        if missing:
            raise ReportError(f"selected candidates are missing or not admitted: {sorted(missing)}")
    results = []
    generated_at = utc_now()
    for candidate in candidates:
        report = build_report(inventory_path.resolve(), candidate, generated_at)
        validate_report(report)
        status, target = write_revision(report, dry_run)
        results.append({"candidate_id": candidate["candidate_id"], "status": status,
                        "output_path": repository_relative(target)})
    return results


def validate_path(path: Path) -> list[dict[str, Any]]:
    if not path.is_dir():
        try:
            record = read_json(path)
            errors = semantic_errors(record)
            return [{"path": repository_relative(path),
                     "status": "valid" if not errors else "invalid",
                     "errors": errors, "warnings": []}]
        except Exception as exc:
            return [{"path": str(path), "status": "invalid", "errors": [str(exc)], "warnings": []}]

    results: list[dict[str, Any]] = []
    grouped: dict[Path, list[Path]] = {}
    for item in sorted(path.rglob("revision_*.json")):
        grouped.setdefault(item.parent, []).append(item)
    for directory, paths in sorted(grouped.items()):
        chain_error: str | None = None
        try:
            validate_revision_chain(directory)
        except Exception as exc:
            chain_error = str(exc)
        latest = paths[-1]
        for item in paths:
            try:
                record = read_json(item)
                errors = semantic_errors(record)
                warnings: list[str] = []
                if item != latest:
                    mutable_names = historical_mutable_reference_names(record)
                    retained = []
                    for error in errors:
                        if any(error.startswith(f"{name} hash mismatch")
                               or error.startswith(f"{name} unavailable")
                               for name in mutable_names):
                            warnings.append("historical dependency drift: " + error)
                        else:
                            retained.append(error)
                    errors = retained
                if item == latest and chain_error is not None:
                    errors.append("revision chain: " + chain_error)
                status = "invalid" if errors else "historical_valid" if item != latest else "valid"
                results.append({"path": repository_relative(item), "status": status,
                                "errors": sorted(set(errors)), "warnings": sorted(set(warnings))})
            except Exception as exc:
                results.append({"path": str(item), "status": "invalid",
                                "errors": [str(exc)], "warnings": []})
    return results


def historical_mutable_reference_names(report: dict[str, Any]) -> set[str]:
    """Return provenance references that may legitimately drift after a revision is frozen."""
    names = {"source_bundle.inventory_ref", "provenance.mapping_ref"}
    inventory_ref = report.get("source_bundle", {}).get("inventory_ref")
    for index, reference in enumerate(report.get("provenance", {}).get("input_artifact_refs", [])):
        if reference == inventory_ref:
            names.add(f"provenance.input_artifact_refs[{index}]")
    return names


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--inventory", type=Path)
    actions.add_argument("--validate-only", type=Path)
    parser.add_argument("--candidate-id", action="append")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.validate_only:
        results = validate_path(args.validate_only)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 1 if any(item["status"] == "invalid" for item in results) else 0
    results = build_candidates(args.inventory, set(args.candidate_id) if args.candidate_id else None, args.dry_run)
    print(json.dumps({"status": "completed", "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ReportError, inventory_contract.InventoryError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
