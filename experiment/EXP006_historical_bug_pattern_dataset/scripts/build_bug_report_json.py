#!/usr/bin/env python3
"""Deterministically build and validate Historical Bug Report v2 records."""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


SCRIPT_VERSION = "2.0.5"
REPORT_SCHEMA_VERSION = "2.0"
MAPPING_VERSION = "2.0"

SCRIPT_PATH = Path(__file__).resolve()
EXP006_DIR = SCRIPT_PATH.parent.parent
PROJECT_ROOT = EXP006_DIR.parent.parent
SCHEMA_PATH = EXP006_DIR / "schemas" / "bug_report_record.schema.json"
MAPPING_PATH = EXP006_DIR / "schemas" / "source_to_report_mapping.md"
OUTPUT_ROOT = EXP006_DIR / "bug_reports"
RUN_LOG_ROOT = EXP006_DIR / "quality" / "report_build_runs"

DLFRAME_ROOT = PROJECT_ROOT / "dataset" / "raw" / "DLFrameBRCode_PyTorch"
DLFRAME_REPORT_ROOT = DLFRAME_ROOT / "reports"
DLFRAME_CODE_ROOT = DLFRAME_ROOT / "reproduction_code"
SELECTION_PATH = (
    PROJECT_ROOT
    / "dataset"
    / "interim"
    / "bug_selection"
    / "selected_bug_review_final.csv"
)
GITHUB_ISSUE_ROOT = (
    PROJECT_ROOT / "dataset" / "interim" / "github_issue_collection"
)
MATMUL_ISSUE_ROOT = (
    PROJECT_ROOT
    / "dataset"
    / "raw"
    / "exp006_matmul_reports"
    / "pytorch"
    / "torch.matmul"
)

PROFILE_DLFRAME = "dlframe_benchmark_v1"
PROFILE_GITHUB = "curated_github_issue_text_v1"
PROFILE_ALIASES = {
    "dlframe": PROFILE_DLFRAME,
    "github": PROFILE_GITHUB,
    PROFILE_DLFRAME: PROFILE_DLFRAME,
    PROFILE_GITHUB: PROFILE_GITHUB,
}

PROFILE_ORDER = {PROFILE_DLFRAME: 0, PROFILE_GITHUB: 1}
SOURCE_BOUNDARY_KEYS = {
    "title",
    "description",
    "reproduction",
    "observed",
    "expected",
    "environment",
    "discussion",
    "root_cause",
    "fix",
    "status",
    "created",
    "author",
    "labels",
    "issue_id",
    "repository",
}

SECTION_ALIASES = {
    "title": "title",
    "bug": "description",
    "describe the bug": "description",
    "description": "description",
    "bug description": "description",
    "bug summary": "description",
    "to reproduce": "reproduction",
    "minimal reproduction": "reproduction",
    "reproduction": "reproduction",
    "example": "reproduction",
    "observed behavior": "observed",
    "actual behavior": "observed",
    "observed": "observed",
    "error": "observed",
    "output": "observed",
    "expected behavior": "expected",
    "expected": "expected",
    "environment": "environment",
    "discussion": "discussion",
    "root cause": "root_cause",
    "root cause / technical information": "root_cause",
    "explanation": "explanation",
    "fix": "fix",
    "final resolution": "fix",
    "api": "api",
    "affected operations": "api",
    "status": "status",
    "activity": "ignored",
    "issue status": "ignored",
    "state": "status",
    "opened": "created",
    "created": "created",
    "author": "author",
    "labels": "labels",
    "issue id": "issue_id",
    "issue": "issue_id",
    "issue number": "issue_id",
    "repository": "repository",
    "acknowledgement": "ignored",
    "acknowledgment": "ignored",
    "category": "analyst",
    "bug category": "analyst",
    "bug category (human annotation)": "analyst",
    "trigger condition": "analyst",
    "trigger conditions": "analyst",
    "potential fuzzing value": "analyst",
    "harness generation guidance": "analyst",
    "potential harness generation directions": "analyst",
    "potential harness strategy": "analyst",
    "harness strategy": "analyst",
    "bug pattern candidate": "analyst",
    "pattern": "analyst",
    "related concepts": "analyst",
    "related concepts (preliminary only)": "analyst",
    "oracle": "analyst",
    "selection decision": "analyst",
    "research value": "analyst",
    "severity": "analyst",
    "bug type": "analyst",
    "notes": "analyst",
    "reason": "analyst",
}

# Strong section boundaries accepted without Markdown markers. They also allow
# deterministic recovery after a captured reproduction has an unclosed fence.
PLAIN_BOUNDARY_HEADINGS = {
    "observed behavior",
    "actual behavior",
    "expected behavior",
    "environment",
    "discussion",
    "root cause",
    "fix",
    "affected operations",
    "activity",
    "trigger conditions",
    "issue status",
}

FAILURE_MARKERS = {
    "memory_error": (
        "out of bounds",
        "out-of-bounds",
        "buffer overflow",
        "heap-buffer-overflow",
        "illegal memory access",
        "memory corruption",
        "unsafe memory write",
        "memory region after",
        "allocation failure",
        "out of memory",
        "oom",
    ),
    "incorrect_output": (
        "incorrect",
        "wrong result",
        "wrong output",
        "mismatch",
        "different result",
        "different value",
        "different output",
        "differs from",
        "inconsistent",
        "remains zero",
        "uninitialized value",
        "doesn't provide the correct",
        "does not provide the correct",
        "silently drops",
        "returns nan",
    ),
    "crash": (
        "segmentation fault",
        "segfault",
        "sigsegv",
        "sigabrt",
        "abort",
        "crash",
        "fatal signal",
        "internal assert failed",
    ),
    "timeout_hang": ("timeout", "timed out", "hang", "deadlock", "no progress"),
    "exception": (
        "assertionerror",
        "runtimeerror",
        "indexerror",
        "valueerror",
        "typeerror",
        "exception",
        "raises an error",
        "raises error",
    ),
}


class ReportBuildError(Exception):
    def __init__(
        self, stage: str, code: str, message: str, details: Sequence[str] | None = None
    ):
        super().__init__(message)
        self.stage = stage
        self.code = code
        self.details = list(details or [])


@dataclass(frozen=True)
class Section:
    key: str
    heading: str
    body: str
    start_line: int
    end_line: int
    located_text: str


@dataclass(frozen=True)
class SelectionRow:
    values: dict[str, str]
    line_number: int
    located_text: str


@dataclass(frozen=True)
class CaseBundle:
    profile: str
    case_id: str
    primary_path: Path
    admission: str = "candidate"
    reproduction_path: Path | None = None
    curation_path: Path | None = None
    selection: SelectionRow | None = None
    lookup_api_hint: str | None = None
    alternate_paths: tuple[Path, ...] = ()
    preflight_error_stage: str | None = None
    preflight_error_code: str | None = None
    preflight_error_message: str | None = None


@dataclass
class CaseResult:
    profile: str
    case_id: str
    status: str
    output_path: str | None = None
    error_stage: str | None = None
    error_code: str | None = None
    message: str | None = None
    traceback_text: str | None = None
    details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "case_id": self.case_id,
            "status": self.status,
            "output_path": self.output_path,
            "error_stage": self.error_stage,
            "error_code": self.error_code,
            "message": self.message,
            "traceback": self.traceback_text,
            "details": self.details,
        }


@dataclass
class EvidenceFactory:
    items: list[dict[str, Any]] = field(default_factory=list)
    used_ids: set[str] = field(default_factory=set)
    id_by_locator: dict[tuple[str, str, int, int, str], str] = field(default_factory=dict)

    def add(
        self,
        artifact_id: str,
        evidence_kind: str,
        section: Section,
        actor: str | None,
        actor_role: str,
    ) -> str:
        content_hash = sha256_text(section.located_text)
        locator_key = (artifact_id, evidence_kind, section.start_line, section.end_line, content_hash)
        existing_id = self.id_by_locator.get(locator_key)
        if existing_id is not None:
            return existing_id
        anchor = f"{artifact_id}|{evidence_kind}|{content_hash}"
        stem = f"ev_{slugify(artifact_id)}_{slugify(evidence_kind)}_{short_hash(anchor)}"
        evidence_id = stem
        suffix = 2
        while evidence_id in self.used_ids:
            evidence_id = f"{stem}_{suffix}"
            suffix += 1
        self.used_ids.add(evidence_id)
        self.id_by_locator[locator_key] = evidence_id

        excerpt = section.located_text if len(section.located_text) <= 2000 else None
        self.items.append(
            {
                "evidence_id": evidence_id,
                "source_artifact_ref": artifact_id,
                "evidence_kind": evidence_kind,
                "locator": {
                    "locator_type": "line_range",
                    "start_line": section.start_line,
                    "end_line": section.end_line,
                },
                "excerpt": excerpt,
                "attribution": {"actor": actor, "actor_role": actor_role},
                "content_hash": content_hash,
            }
        )
        return evidence_id


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"report-build-{stamp}-{uuid.uuid4().hex[:8]}"


def slugify(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._:-]+", "_", value.strip())
    value = re.sub(r"_+", "_", value).strip("_.:-")
    return value or "item"


def short_hash(value: str, length: int = 12) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def report_content_hash(report: dict[str, Any]) -> str:
    value = copy.deepcopy(report)
    value["provenance"].pop("content_hash", None)
    return sha256_bytes(canonical_json_bytes(value))


def read_text(path: Path) -> str:
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise ReportBuildError("parse", "text_read_error", f"{path}: {exc}") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n")


def repository_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise ReportBuildError(
            "bundle", "path_outside_repository", f"Path is outside repository: {path}"
        ) from exc


def parse_mapping_version(text: str) -> str:
    match = re.search(r"^#\s+Source-to-Report Mapping v([0-9]+\.[0-9]+)\s*$", text, re.M)
    if not match:
        raise ReportBuildError("startup", "mapping_version_missing", str(MAPPING_PATH))
    return match.group(1)


def normalize_heading(value: str) -> str:
    value = value.strip().strip("*").strip()
    value = re.sub(r"^#+\s*", "", value)
    value = value.strip().rstrip(":").strip()
    value = re.sub(r"\s+", " ", value)
    return value.casefold()


def parse_heading(line: str) -> tuple[str, str, str] | None:
    stripped = line.strip()
    bracket = re.match(r"^\[([^\]]+)\]\s*(.*)$", stripped)
    if bracket:
        raw_heading = bracket.group(1)
        key = SECTION_ALIASES.get(normalize_heading(raw_heading))
        if key:
            return key, raw_heading, bracket.group(2).strip()

    markdown = stripped.startswith("#")
    candidate = re.sub(r"^#+\s*", "", stripped) if markdown else stripped
    has_colon = candidate.endswith(":")
    candidate = candidate[:-1] if has_colon else candidate
    normalized = normalize_heading(candidate)
    if (
        not markdown
        and not has_colon
        and normalized not in PLAIN_BOUNDARY_HEADINGS
    ):
        return None
    key = SECTION_ALIASES.get(normalized)
    if key:
        return key, candidate.strip(), ""
    return None


def parse_sections(text: str) -> dict[str, list[Section]]:
    lines = text.splitlines()
    found: dict[str, list[Section]] = {}
    current: tuple[str, str, int, str] | None = None
    active_fence: str | None = None
    analyst_context = False

    def finish(end_index: int) -> None:
        nonlocal current
        if current is None:
            return
        key, heading, start_index, inline_value = current
        body_lines = lines[start_index + 1 : end_index]
        parts = ([inline_value] if inline_value else []) + body_lines
        body = "\n".join(parts).strip()
        located = "\n".join(lines[start_index:end_index])
        if located.strip():
            found.setdefault(key, []).append(
                Section(
                    key=key,
                    heading=heading,
                    body=body,
                    start_line=start_index + 1,
                    end_line=max(start_index + 1, end_index),
                    located_text=located,
                )
            )
        current = None

    for index, line in enumerate(lines):
        fence_match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if fence_match:
            fence = fence_match.group(1)[0]
            if active_fence is None:
                active_fence = fence
            elif active_fence == fence:
                active_fence = None
            continue
        heading = parse_heading(line)
        if active_fence is not None:
            if (
                heading is None
                or normalize_heading(heading[1]) not in PLAIN_BOUNDARY_HEADINGS
            ):
                continue
            # The captured source omitted the closing fence. A strong, exact
            # section heading deterministically terminates the code region.
            active_fence = None
        elif heading is None:
            continue
        key, raw_heading, inline_value = heading
        finish(index)
        if key == "analyst":
            analyst_context = True
            continue
        if analyst_context:
            normalized = normalize_heading(raw_heading)
            if key not in SOURCE_BOUNDARY_KEYS or (
                key == "reproduction" and normalized == "example"
            ):
                continue
            analyst_context = False
        if key != "ignored":
            current = (key, raw_heading, index, inline_value)
    finish(len(lines))
    return found


def has_unclosed_code_fence(text: str) -> bool:
    active_fence: str | None = None
    for line in text.splitlines():
        match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if not match:
            continue
        fence = match.group(1)[0]
        if active_fence is None:
            active_fence = fence
        elif active_fence == fence:
            active_fence = None
    return active_fence is not None


def first_section(
    sections: dict[str, list[Section]], *keys: str
) -> Section | None:
    for key in keys:
        values = sections.get(key, [])
        if values:
            return values[0]
    return None


def bounded_statement(section: Section, label: str) -> str:
    value = section.body.strip()
    if not value:
        raise ReportBuildError("parse", "empty_section", f"Empty {label} section")
    if len(value) > 4000:
        raise ReportBuildError(
            "parse", "statement_too_long", f"{label} exceeds 4000 characters"
        )
    return value


def classify_failure(statement: str) -> str:
    lowered = statement.casefold()
    for failure_type, markers in FAILURE_MARKERS.items():
        if any(marker in lowered for marker in markers):
            return failure_type
    return "unknown"


def normalize_state(value: str | None) -> str:
    if not value:
        return "unknown"
    token = value.strip().splitlines()[0].strip().casefold()
    if token in {"open", "opened"}:
        return "open"
    if token in {"closed", "close"}:
        return "closed"
    return "unknown"


def explicit_timestamp(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip().splitlines()[0].strip()
    if "T" not in candidate:
        return None
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def extract_issue_id(text: str, path: Path) -> tuple[str, str]:
    patterns = (
        r"(?im)^\s*PyTorch\s+GitHub\s+Issue\s*#\s*(\d+)\s*$",
        r"(?im)^\s*Issue(?:\s+ID|\s+Number)?\s*:\s*(?:\n\s*)*#?\s*(\d+)\s*$",
    )
    content_ids: set[str] = set()
    for pattern in patterns:
        content_ids.update(re.findall(pattern, text))
    if len(content_ids) > 1:
        raise ReportBuildError(
            "parse",
            "multiple_issue_ids",
            f"Multiple Issue IDs in {path}: {sorted(content_ids)}",
        )

    filename_match = re.fullmatch(
        r"issue_(\d+)(?:_[A-Za-z0-9._-]+)?\.txt", path.name
    )
    filename_id = filename_match.group(1) if filename_match else None
    content_id = next(iter(content_ids), None)
    if content_id and filename_id and content_id != filename_id:
        raise ReportBuildError(
            "bundle",
            "issue_id_mismatch",
            f"Content ID {content_id} differs from filename ID {filename_id}: {path}",
        )
    if content_id:
        return content_id, "captured_text"
    if filename_id:
        return filename_id, "strict_filename"
    raise ReportBuildError("bundle", "issue_id_missing", str(path))


def extract_issue_url(text: str, issue_id: str) -> str | None:
    urls = set(
        re.findall(
            r"https://github\.com/pytorch/pytorch/issues/(\d+)(?:\b|/)", text
        )
    )
    if any(value != issue_id for value in urls):
        raise ReportBuildError(
            "parse", "issue_url_mismatch", f"Issue URL does not match {issue_id}"
        )
    if issue_id in urls:
        return f"https://github.com/pytorch/pytorch/issues/{issue_id}"
    return None


def find_line_section(text: str, pattern: str, key: str) -> Section | None:
    lines = text.splitlines()
    compiled = re.compile(pattern, re.I)
    for index, line in enumerate(lines):
        if compiled.search(line):
            return Section(key, key, line.strip(), index + 1, index + 1, line)
    return None


def make_artifact(
    *,
    artifact_id: str,
    path: Path,
    role: str,
    kind: str,
    repository: str | None,
    external_id: str | None,
    url: str | None,
    title: str | None,
    native_state: str | None,
    created_at: str | None,
) -> dict[str, Any]:
    if not path.is_file():
        raise ReportBuildError("bundle", "artifact_missing", str(path))
    return {
        "artifact_id": artifact_id,
        "artifact_role": role,
        "source_kind": kind,
        "repository": repository,
        "external_id": external_id,
        "url": url,
        "local_path": repository_relative(path),
        "title": title,
        "source_native_state": native_state,
        "source_created_at": created_at,
        "captured_at": None,
        "content_hash": sha256_file(path),
    }


API_TOKEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_.])(?:"
    r"torch(?:\.[A-Za-z_][A-Za-z0-9_]*)+|"
    r"aten::[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*|"
    r"nn(?:\.[A-Za-z_][A-Za-z0-9_]*)+|"
    r"Tensor(?:\.[A-Za-z_][A-Za-z0-9_]*)+"
    r")(?![A-Za-z0-9_.])"
)


def extract_api_tokens(value: str) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for match in API_TOKEN_PATTERN.finditer(value):
        token = match.group(0)
        identity = token.casefold()
        if identity not in seen:
            seen.add(identity)
            tokens.append(token)
    return tokens


def api_terminal_name(api_name: str) -> str:
    value = api_name.split("::", 1)[-1]
    return value.rsplit(".", 1)[-1].casefold()


def build_github_api_assertions(
    sections: dict[str, list[Section]],
    lookup_api_hint: str,
    evidence: EvidenceFactory,
    artifact_id: str,
    actor: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: dict[str, tuple[str, Section, str]] = {}

    def add_candidates(section: Section, basis: str) -> None:
        for token in extract_api_tokens(section.body):
            candidates.setdefault(token.casefold(), (token, section, basis))

    title_sections = sections.get("title", [])
    api_sections = sections.get("api", [])
    for section in title_sections:
        add_candidates(section, "source_explicit")
    for section in api_sections:
        add_candidates(section, "source_explicit")

    primary_key: str | None = None
    if title_sections:
        title_tokens = extract_api_tokens(title_sections[0].body)
        if len(title_tokens) == 1:
            primary_key = title_tokens[0].casefold()
    if primary_key is None and api_sections:
        first_line = next(
            (line.strip() for line in api_sections[0].body.splitlines() if line.strip()),
            "",
        )
        first_line_tokens = extract_api_tokens(first_line)
        if len(first_line_tokens) == 1:
            primary_key = first_line_tokens[0].casefold()

    supporting_sections = (
        title_sections
        + api_sections
        + sections.get("description", [])
        + sections.get("reproduction", [])
        + sections.get("observed", [])
        + sections.get("expected", [])
    )
    supporting: dict[str, tuple[str, Section, str]] = dict(candidates)
    for section in supporting_sections:
        basis = "code_explicit" if section.key == "reproduction" else "source_explicit"
        for token in extract_api_tokens(section.body):
            supporting.setdefault(token.casefold(), (token, section, basis))

    # The requested API is the deterministic target for this profile. If the
    # source explicitly mentions it, prefer it over incidental APIs, dtypes,
    # and helper calls found in the reproduction.
    lookup_key = lookup_api_hint.casefold()
    if lookup_key in supporting:
        primary_key = lookup_key
    if primary_key is None and title_sections:
        title_text = title_sections[0].body.casefold()
        matching = {
            key
            for key, (token, _, _) in supporting.items()
            if re.search(
                rf"(?<![A-Za-z0-9_]){re.escape(api_terminal_name(token))}(?![A-Za-z0-9_])",
                title_text,
            )
        }
        if len(matching) == 1:
            primary_key = next(iter(matching))
    if primary_key is None and len(candidates) == 1:
        primary_key = next(iter(candidates))
    if primary_key is None:
        raise ReportBuildError(
            "admission",
            "primary_api_ambiguous",
            "Captured source does not establish one primary API",
            [value[0] for value in supporting.values()],
        )

    primary = supporting.get(primary_key)
    if primary is None:
        raise ReportBuildError(
            "admission", "primary_api_evidence_missing", primary_key
        )
    candidates.setdefault(primary_key, primary)

    assertions: list[dict[str, Any]] = []
    ordered = sorted(
        candidates.items(),
        key=lambda item: (0 if item[0] == primary_key else 1, item[0]),
    )
    for index, (identity, (api_name, section, basis)) in enumerate(ordered, 1):
        evidence_ref = evidence.add(
            artifact_id, "api_reference", section, actor, "reporter"
        )
        assertions.append(
            {
                "assertion_id": f"api_assertion_{index:03d}",
                "api_name": api_name,
                "relation": "primary" if identity == primary_key else "mentioned",
                "assertion_basis": basis,
                "evidence_refs": [evidence_ref],
            }
        )

    warnings: list[dict[str, Any]] = []
    if lookup_api_hint.casefold() != primary[0].casefold():
        warnings.append(
            {
                "issue_id": "validation_lookup_api_differs_001",
                "field_path": "/scope_assertions/api_assertions",
                "severity": "warning",
                "message": (
                    f"Lookup hint {lookup_api_hint!r} differs from source-derived "
                    f"primary API {primary[0]!r}; the source-derived API was retained."
                ),
            }
        )
    return assertions, warnings


def reproduction_availability(
    section: Section | None, standalone_artifacts: Sequence[str]
) -> str:
    if standalone_artifacts:
        return "code_provided"
    if section is None or not section.body.strip():
        return "absent"
    body = section.body
    if re.search(r"```[^\n]*\n.+?```|~~~[^\n]*\n.+?~~~", body, re.S):
        return "code_provided"
    code_line = re.compile(
        r"^\s*(?:from\s+\S+\s+import\s+|import\s+\S+|[A-Za-z_]\w*\s*=|"
        r"(?:torch|nn|Tensor)\.[A-Za-z_]\w*\s*\()"
    )
    if any(code_line.search(line) for line in body.splitlines()):
        return "code_provided"
    return "steps_provided"


def parse_environment(section: Section, evidence_ref: str) -> list[dict[str, Any]]:
    lines = [line.strip() for line in section.body.splitlines()]
    facts: list[dict[str, Any]] = []
    seen: set[str] = set()
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not value:
            while index < len(lines) and not lines[index]:
                index += 1
            if index < len(lines) and ":" not in lines[index]:
                value = lines[index]
                index += 1
        if not key or not value:
            continue
        identity = key.casefold()
        if identity in seen:
            continue
        seen.add(identity)
        if len(key) > 1000 or len(value) > 4000:
            raise ReportBuildError(
                "parse",
                "environment_fact_too_long",
                "Environment property/value exceeds the Report contract",
            )
        facts.append(
            {
                "fact_id": f"fact_environment_{len(facts) + 1:03d}",
                "property": key,
                "value": value,
                "assertion_basis": "source_explicit",
                "evidence_refs": [evidence_ref],
            }
        )
    return facts


def load_selection_rows() -> dict[str, SelectionRow]:
    text = read_text(SELECTION_PATH)
    lines = text.splitlines()
    reader = csv.DictReader(io.StringIO(text))
    rows: dict[str, SelectionRow] = {}
    for values in reader:
        bug_id = (values.get("bug_id") or "").strip()
        if not bug_id:
            continue
        if bug_id in rows:
            raise ReportBuildError(
                "discovery", "duplicate_selection_id", f"Duplicate selection ID: {bug_id}"
            )
        line_number = reader.line_num
        located = lines[line_number - 1] if line_number <= len(lines) else ""
        rows[bug_id] = SelectionRow(
            values={key: (value or "").strip() for key, value in values.items()},
            line_number=line_number,
            located_text=located,
        )
    return rows


def discover_dlframe(case_ids: set[str] | None = None) -> list[CaseBundle]:
    selections = load_selection_rows()
    bundles: list[CaseBundle] = []
    for report_path in sorted(DLFRAME_REPORT_ROOT.glob("*_summary_with_code.txt")):
        filename_match = re.fullmatch(r"(\d+)_summary_with_code\.txt", report_path.name)
        if filename_match is None:
            if case_ids is None:
                bundles.append(
                    CaseBundle(
                        profile=PROFILE_DLFRAME,
                        case_id=report_path.stem,
                        primary_path=report_path,
                        admission="discovery_failed",
                        preflight_error_stage="discovery",
                        preflight_error_code="invalid_dlframe_filename",
                        preflight_error_message=f"Unsupported filename: {report_path.name}",
                    )
                )
            continue
        case_id = filename_match.group(1)
        if case_ids is not None and case_id not in case_ids:
            continue
        selection = selections.get(case_id)
        admission = "not_selected"
        lookup_api_hint: str | None = None
        error_code: str | None = None
        error_message: str | None = None
        if selection is not None:
            decision = selection.values.get("human_include", "").strip().casefold()
            lookup_api_hint = selection.values.get("target_api") or None
            if decision == "yes":
                admission = "candidate"
                if lookup_api_hint is None:
                    admission = "discovery_failed"
                    error_code = "selected_api_missing"
                    error_message = f"Selected DLFrame case {case_id} has no target_api"
            elif decision == "no":
                admission = "excluded"
            else:
                admission = "discovery_failed"
                error_code = "invalid_curation_decision"
                error_message = (
                    f"DLFrame case {case_id} has unsupported human_include value "
                    f"{selection.values.get('human_include', '')!r}"
                )
        bundles.append(
            CaseBundle(
                profile=PROFILE_DLFRAME,
                case_id=case_id,
                primary_path=report_path,
                admission=admission,
                reproduction_path=DLFRAME_CODE_ROOT / f"{case_id}.py",
                curation_path=SELECTION_PATH if selection else None,
                selection=selection,
                lookup_api_hint=lookup_api_hint,
                preflight_error_stage="discovery" if error_code else None,
                preflight_error_code=error_code,
                preflight_error_message=error_message,
            )
        )
    return bundles


def discover_github(case_ids: set[str] | None = None) -> list[CaseBundle]:
    """Discover one deterministic primary source per Issue.

    The interim collection and the expanded torch.matmul capture may contain
    the same Issue. The expanded capture is preferred for the pilot, while
    the other local artifact is retained on the CaseBundle for provenance.
    """
    source_roots = (
        (MATMUL_ISSUE_ROOT, 0),
        (GITHUB_ISSUE_ROOT, 1),
    )
    paths_by_case: dict[str, list[tuple[int, Path]]] = {}
    invalid: list[tuple[Path, str]] = []
    for root, priority in source_roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if root == GITHUB_ISSUE_ROOT and path.suffix.lower() != ".txt":
                continue
            if root == MATMUL_ISSUE_ROOT and path.suffix.lower() != ".md":
                continue
            if root == GITHUB_ISSUE_ROOT and not re.fullmatch(
                r"issue_(\d+)(?:_[A-Za-z0-9._-]+)?\.txt", path.name
            ):
                if case_ids is None:
                    invalid.append((path, "invalid_github_filename"))
                continue
            try:
                case_id, _ = extract_issue_id(read_text(path), path)
            except ReportBuildError as exc:
                if case_ids is None:
                    invalid.append((path, exc.code))
                continue
            if case_ids is not None and case_id not in case_ids:
                continue
            paths_by_case.setdefault(case_id, []).append((priority, path))

    bundles: list[CaseBundle] = []
    for path, code in invalid:
        bundles.append(CaseBundle(
            profile=PROFILE_GITHUB,
            case_id=path.stem,
            primary_path=path,
            admission="discovery_failed",
            preflight_error_stage="discovery",
            preflight_error_code=code,
            preflight_error_message=f"Unsupported or unreadable source: {path}",
        ))

    for case_id, records in sorted(paths_by_case.items()):
        records.sort(key=lambda item: (item[0], item[1].as_posix()))
        best_priority = records[0][0]
        same_priority = [item for item in records if item[0] == best_priority]
        if len(same_priority) > 1:
            bundles.append(CaseBundle(
                profile=PROFILE_GITHUB,
                case_id=case_id,
                primary_path=same_priority[0][1],
                admission="discovery_failed",
                preflight_error_stage="discovery",
                preflight_error_code="duplicate_primary_source",
                preflight_error_message=(
                    f"Issue {case_id} has multiple sources at the same priority: "
                    + ", ".join(str(item[1]) for item in same_priority)
                ),
            ))
            continue
        primary = records[0][1]
        alternates = tuple(item[1] for item in records[1:])
        excluded = primary.is_relative_to(GITHUB_ISSUE_ROOT) and "excluded" in primary.relative_to(GITHUB_ISSUE_ROOT).parts
        bundles.append(CaseBundle(
            profile=PROFILE_GITHUB,
            case_id=case_id,
            primary_path=primary,
            admission="excluded" if excluded else "candidate",
            lookup_api_hint=None if excluded else (
                "torch.matmul" if primary.is_relative_to(MATMUL_ISSUE_ROOT) else primary.parent.name
            ),
            alternate_paths=alternates,
        ))
    return bundles


def build_base_report(
    *,
    report_id: str,
    artifacts: list[dict[str, Any]],
    primary_source_ref: str,
    evidence_items: list[dict[str, Any]],
    api_assertions: list[dict[str, Any]],
    component_assertions: list[dict[str, Any]],
    trigger_claims: list[dict[str, Any]],
    operation_contexts: list[dict[str, Any]],
    failure_observations: list[dict[str, Any]],
    expected_claims: list[dict[str, Any]],
    oracle_claims: list[dict[str, Any]],
    environment_facts: list[dict[str, Any]],
    reproduction: dict[str, Any],
    root_cause_claims: list[dict[str, Any]],
    resolution_claims: list[dict[str, Any]],
    fix_artifact_refs: list[str],
    verification_status: dict[str, Any],
    unresolved: list[dict[str, Any]],
    validation_issues: list[dict[str, Any]],
    run_id: str,
    generated_at: str,
    mapping_hash: str,
    builder_hash: str,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "identity": {"report_id": report_id, "framework": "pytorch"},
        "revision_information": {
            "revision_number": 1,
            "parent_revision_ref": None,
            "revision_trigger": "initial_generation",
            "change_summary": "Initial deterministic mapping from captured sources.",
        },
        "source_bundle": {
            "primary_source_ref": primary_source_ref,
            "source_artifacts": artifacts,
        },
        "evidence_items": evidence_items,
        "scope_assertions": {
            "api_assertions": api_assertions,
            "component_assertions": component_assertions,
        },
        "reported_behavior": {
            "trigger_claims": trigger_claims,
            "operation_contexts": operation_contexts,
            "failure_observations": failure_observations,
            "expected_behavior_claims": expected_claims,
            "historical_oracle_claims": oracle_claims,
            "environment_facts": environment_facts,
            "reproduction": reproduction,
        },
        "reported_diagnosis": {"root_cause_claims": root_cause_claims},
        "resolution": {
            "fix_status": {
                "value": "unknown",
                "assertion_basis": "unknown",
                "evidence_refs": [],
            },
            "resolution_claims": resolution_claims,
            "fix_artifact_refs": fix_artifact_refs,
        },
        "verification": {"case_verification_status": verification_status},
        "unresolved_information": unresolved,
        "provenance": {
            "generation_method": "deterministic_source_mapping",
            "builder_ref": {
                "artifact_name": SCRIPT_PATH.name,
                "artifact_version": SCRIPT_VERSION,
                "content_hash": builder_hash,
            },
            "generation_run_id": run_id,
            "input_artifact_refs": [item["artifact_id"] for item in artifacts],
            "mapping_ref": {
                "artifact_name": MAPPING_PATH.name,
                "artifact_version": MAPPING_VERSION,
                "content_hash": mapping_hash,
            },
            "generated_at": generated_at,
            "content_hash": "sha256:" + "0" * 64,
        },
        "review": {
            "validation_status": "passed",
            "validation_issues": validation_issues,
            "human_review_status": "not_reviewed",
            "reviewer": None,
            "reviewed_at": None,
            "review_notes": None,
        },
    }
    report["provenance"]["content_hash"] = report_content_hash(report)
    return report


def build_dlframe_report(
    bundle: CaseBundle,
    run_id: str,
    generated_at: str,
    mapping_hash: str,
    builder_hash: str,
) -> dict[str, Any]:
    if (
        bundle.selection is None
        or not bundle.lookup_api_hint
        or bundle.curation_path is None
    ):
        raise ReportBuildError("admission", "curation_missing", bundle.case_id)
    if bundle.reproduction_path is None or not bundle.reproduction_path.is_file():
        raise ReportBuildError("bundle", "reproduction_missing", bundle.case_id)

    text = read_text(bundle.primary_path)
    sections = parse_sections(text)
    title_section = first_section(sections, "title")
    description = first_section(sections, "description")
    reproduction_section = first_section(sections, "reproduction")
    expected = first_section(sections, "expected")
    if description is None:
        raise ReportBuildError("admission", "failure_description_missing", bundle.case_id)

    primary_id = "art_primary_report"
    reproduction_id = "art_reproduction_001"
    curation_id = "art_curation_001"
    title = title_section.body.strip() if title_section and title_section.body.strip() else None
    artifacts = [
        make_artifact(
            artifact_id=primary_id,
            path=bundle.primary_path,
            role="report",
            kind="benchmark_report",
            repository="DLFrameBRCode_PyTorch",
            external_id=bundle.case_id,
            url=None,
            title=title,
            native_state=None,
            created_at=None,
        ),
        make_artifact(
            artifact_id=reproduction_id,
            path=bundle.reproduction_path,
            role="reproduction",
            kind="source_code",
            repository="DLFrameBRCode_PyTorch",
            external_id=bundle.case_id,
            url=None,
            title=None,
            native_state=None,
            created_at=None,
        ),
        make_artifact(
            artifact_id=curation_id,
            path=bundle.curation_path,
            role="curation",
            kind="curation_table",
            repository="HistoricalBug-Fuzzing",
            external_id=f"selected_bug_review_final:{bundle.case_id}",
            url=None,
            title=f"Final selection row {bundle.case_id}",
            native_state=None,
            created_at=None,
        ),
    ]

    evidence = EvidenceFactory()
    if title_section:
        evidence.add(primary_id, "source_metadata", title_section, None, "benchmark_author")
    description_ref = evidence.add(
        primary_id, "bug_description", description, None, "benchmark_author"
    )
    source_reproduction_refs: list[str] = []
    if reproduction_section and reproduction_section.body.strip():
        source_reproduction_refs.append(
            evidence.add(
                primary_id,
                "reproduction",
                reproduction_section,
                None,
                "benchmark_author",
            )
        )
    expected_claims: list[dict[str, Any]] = []
    if expected and expected.body.strip():
        expected_ref = evidence.add(
            primary_id, "expected_behavior", expected, None, "benchmark_author"
        )
        expected_claims.append(
            {
                "claim_id": "claim_expected_001",
                "statement": bounded_statement(expected, "expected behavior"),
                "assertion_basis": "source_explicit",
                "evidence_refs": [expected_ref],
            }
        )

    selection_section = Section(
        key="curation",
        heading="selected_bug_review_final.csv",
        body=bundle.selection.located_text,
        start_line=bundle.selection.line_number,
        end_line=bundle.selection.line_number,
        located_text=bundle.selection.located_text,
    )
    curation_ref = evidence.add(
        curation_id, "api_reference", selection_section, None, "curator"
    )
    description_statement = bounded_statement(description, "bug description")
    return build_base_report(
        report_id=f"br_pytorch_dlframe_{bundle.case_id}",
        artifacts=artifacts,
        primary_source_ref=primary_id,
        evidence_items=evidence.items,
        api_assertions=[
            {
                "assertion_id": "api_primary_001",
                "api_name": bundle.lookup_api_hint,
                "relation": "primary",
                "assertion_basis": "curation_confirmed",
                "evidence_refs": [curation_ref],
            }
        ],
        component_assertions=[],
        trigger_claims=[],
        operation_contexts=[],
        failure_observations=[
            {
                "observation_id": "obs_failure_001",
                "failure_type": classify_failure(description_statement),
                "statement": description_statement,
                "assertion_basis": "source_explicit",
                "evidence_refs": [description_ref],
            }
        ],
        expected_claims=expected_claims,
        oracle_claims=[],
        environment_facts=[],
        reproduction={
            "availability": reproduction_availability(
                reproduction_section, [reproduction_id]
            ),
            "source_evidence_refs": source_reproduction_refs,
            "artifact_refs": [reproduction_id],
            "validation_status": "not_attempted",
            "validation_evidence_refs": [],
        },
        root_cause_claims=[],
        resolution_claims=[],
        fix_artifact_refs=[],
        verification_status={
            "value": "benchmark_curated",
            "assertion_basis": "curation_confirmed",
            "evidence_refs": [description_ref, curation_ref],
        },
        unresolved=[],
        validation_issues=[],
        run_id=run_id,
        generated_at=generated_at,
        mapping_hash=mapping_hash,
        builder_hash=builder_hash,
    )


def build_github_report(
    bundle: CaseBundle,
    run_id: str,
    generated_at: str,
    mapping_hash: str,
    builder_hash: str,
) -> dict[str, Any]:
    text = read_text(bundle.primary_path)
    issue_id, issue_id_origin = extract_issue_id(text, bundle.primary_path)
    if issue_id != bundle.case_id:
        raise ReportBuildError("bundle", "discovery_id_mismatch", bundle.case_id)
    if not bundle.lookup_api_hint:
        raise ReportBuildError("admission", "lookup_api_hint_missing", issue_id)

    sections = parse_sections(text)
    title_section = first_section(sections, "title")
    description = first_section(sections, "description")
    observed = first_section(sections, "observed")
    expected = first_section(sections, "expected")
    reproduction_section = first_section(sections, "reproduction")
    environment = first_section(sections, "environment")
    status = first_section(sections, "status")
    created = first_section(sections, "created")
    author_section = first_section(sections, "author")
    fix = first_section(sections, "fix")

    failure_section = observed or description
    if failure_section is None:
        raise ReportBuildError("admission", "failure_description_missing", issue_id)

    author = (
        author_section.body.strip().splitlines()[0]
        if author_section and author_section.body.strip()
        else None
    )
    title = title_section.body.strip() if title_section and title_section.body.strip() else None
    url = extract_issue_url(text, issue_id)
    native_state = normalize_state(status.body if status else None)
    created_at = explicit_timestamp(created.body if created else None)
    primary_id = "art_primary_report"
    artifacts = [
        make_artifact(
            artifact_id=primary_id,
            path=bundle.primary_path,
            role="report",
            kind="github_issue",
            repository="pytorch/pytorch",
            external_id=issue_id,
            url=url,
            title=title,
            native_state=native_state,
            created_at=created_at,
        )
    ]
    for index, alternate_path in enumerate(bundle.alternate_paths, 1):
        artifacts.append(
            make_artifact(
                artifact_id=f"art_alternate_source_{index:03d}",
                path=alternate_path,
                role="other",
                kind="github_issue",
                repository="pytorch/pytorch",
                external_id=issue_id,
                url=url,
                title=title,
                native_state=native_state,
                created_at=created_at,
            )
        )

    evidence = EvidenceFactory()
    metadata_section = (
        first_section(sections, "issue_id")
        or title_section
        or find_line_section(text, rf"Issue\s*#?\s*{re.escape(issue_id)}", "issue_id")
    )
    metadata_ref: str | None = None
    if metadata_section:
        metadata_ref = evidence.add(
            primary_id, "source_metadata", metadata_section, author, "reporter"
        )

    description_ref: str | None = None
    if description and description.body.strip():
        description_ref = evidence.add(
            primary_id, "bug_description", description, author, "reporter"
        )
    failure_ref = (
        evidence.add(primary_id, "observed_output", observed, author, "reporter")
        if observed and observed.body.strip()
        else description_ref
    )
    if failure_ref is None:
        raise ReportBuildError("admission", "failure_evidence_missing", issue_id)

    api_assertions, validation_issues = build_github_api_assertions(
        sections,
        bundle.lookup_api_hint,
        evidence,
        primary_id,
        author,
    )

    source_reproduction_refs: list[str] = []
    if reproduction_section and reproduction_section.body.strip():
        source_reproduction_refs.append(
            evidence.add(
                primary_id,
                "reproduction",
                reproduction_section,
                author,
                "reporter",
            )
        )
    expected_claims: list[dict[str, Any]] = []
    if expected and expected.body.strip():
        expected_ref = evidence.add(
            primary_id, "expected_behavior", expected, author, "reporter"
        )
        expected_claims.append(
            {
                "claim_id": "claim_expected_001",
                "statement": bounded_statement(expected, "expected behavior"),
                "assertion_basis": "source_explicit",
                "evidence_refs": [expected_ref],
            }
        )

    unresolved: list[dict[str, Any]] = []
    if issue_id_origin == "strict_filename":
        unresolved.append(
            {
                "unresolved_id": "unresolved_issue_id_source_001",
                "field_path": "/source_bundle/source_artifacts/0/external_id",
                "description": (
                    "The captured text omits the upstream Issue ID; the strict "
                    "snapshot filename supplied case identity."
                ),
                "reason": "not_collected",
                "evidence_refs": [],
            }
        )
    if url is None:
        unresolved.append(
            {
                "unresolved_id": "unresolved_issue_url_001",
                "field_path": "/source_bundle/source_artifacts/0/url",
                "description": "The curated local Issue text does not contain its canonical URL.",
                "reason": "not_collected",
                "evidence_refs": [],
            }
        )
    if status and status.body.strip() and native_state == "unknown":
        status_ref = evidence.add(
            primary_id, "source_metadata", status, author, "reporter"
        )
        unresolved.append(
            {
                "unresolved_id": "unresolved_issue_state_001",
                "field_path": "/source_bundle/source_artifacts/0/source_native_state",
                "description": "The captured state value is not a recognized native Issue state.",
                "reason": "unsupported_format",
                "evidence_refs": [status_ref],
            }
        )
    if created and created.body.strip() and created_at is None:
        created_ref = evidence.add(
            primary_id, "source_metadata", created, author, "reporter"
        )
        unresolved.append(
            {
                "unresolved_id": "unresolved_issue_created_at_001",
                "field_path": "/source_bundle/source_artifacts/0/source_created_at",
                "description": "The captured creation time is incomplete or lacks a timezone.",
                "reason": "unsupported_format",
                "evidence_refs": [created_ref],
            }
        )
    if has_unclosed_code_fence(text):
        unresolved.append(
            {
                "unresolved_id": "unresolved_code_fence_001",
                "field_path": "/reported_behavior/reproduction",
                "description": "The captured text contains an unclosed code fence.",
                "reason": "unsupported_format",
                "evidence_refs": source_reproduction_refs,
            }
        )

    environment_facts: list[dict[str, Any]] = []
    if environment and environment.body.strip():
        environment_ref = evidence.add(
            primary_id, "environment", environment, author, "reporter"
        )
        environment_facts = parse_environment(environment, environment_ref)
        if not environment_facts:
            unresolved.append(
                {
                    "unresolved_id": "unresolved_environment_format_001",
                    "field_path": "/reported_behavior/environment_facts",
                    "description": "Environment text is present but has no recognized key-value facts.",
                    "reason": "unsupported_format",
                    "evidence_refs": [environment_ref],
                }
            )

    resolution_claims: list[dict[str, Any]] = []
    if fix and fix.body.strip():
        fix_ref = evidence.add(primary_id, "fix_claim", fix, None, "unknown")
        resolution_claims.append(
            {
                "claim_id": "claim_resolution_001",
                "statement": bounded_statement(fix, "fix"),
                "assertion_basis": "source_explicit",
                "evidence_refs": [fix_ref],
            }
        )

    verification_refs = [value for value in (description_ref, metadata_ref) if value]
    if not verification_refs:
        verification_refs = [failure_ref]
    failure_statement = bounded_statement(failure_section, "failure")
    return build_base_report(
        report_id=f"br_pytorch_github_{issue_id}",
        artifacts=artifacts,
        primary_source_ref=primary_id,
        evidence_items=evidence.items,
        api_assertions=api_assertions,
        component_assertions=[],
        trigger_claims=[],
        operation_contexts=[],
        failure_observations=[
            {
                "observation_id": "obs_failure_001",
                "failure_type": classify_failure(failure_statement),
                "statement": failure_statement,
                "assertion_basis": "source_explicit",
                "evidence_refs": [failure_ref],
            }
        ],
        expected_claims=expected_claims,
        oracle_claims=[],
        environment_facts=environment_facts,
        reproduction={
            "availability": reproduction_availability(reproduction_section, []),
            "source_evidence_refs": source_reproduction_refs,
            "artifact_refs": [],
            "validation_status": "not_attempted",
            "validation_evidence_refs": [],
        },
        root_cause_claims=[],
        resolution_claims=resolution_claims,
        fix_artifact_refs=[],
        verification_status={
            "value": "user_reported",
            "assertion_basis": "source_explicit",
            "evidence_refs": verification_refs,
        },
        unresolved=unresolved,
        validation_issues=validation_issues,
        run_id=run_id,
        generated_at=generated_at,
        mapping_hash=mapping_hash,
        builder_hash=builder_hash,
    )


def load_json_schema() -> dict[str, Any]:
    try:
        return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportBuildError("startup", "schema_load_error", str(exc)) from exc


def json_schema_errors(report: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    try:
        import jsonschema
    except ImportError as exc:
        raise ReportBuildError(
            "startup", "jsonschema_missing", "Install a Draft 2020-12 capable jsonschema package"
        ) from exc
    validator_class = getattr(jsonschema, "Draft202012Validator", None)
    if validator_class is None:
        raise ReportBuildError(
            "startup", "jsonschema_too_old", "Draft202012Validator is unavailable"
        )
    validator_class.check_schema(schema)
    validator = validator_class(schema, format_checker=jsonschema.FormatChecker())
    messages: list[str] = []
    for error in sorted(
        validator.iter_errors(report),
        key=lambda item: tuple(str(part) for part in item.path),
    ):
        path = "/" + "/".join(str(part) for part in error.path)
        messages.append(f"{path}: {error.message}")
    return messages


def all_evidence_refs(report: dict[str, Any]) -> Iterable[tuple[str, str]]:
    scope = report["scope_assertions"]
    for group in ("api_assertions", "component_assertions"):
        for item in scope[group]:
            for ref in item["evidence_refs"]:
                yield f"/scope_assertions/{group}", ref
    behavior = report["reported_behavior"]
    for group in (
        "trigger_claims",
        "operation_contexts",
        "failure_observations",
        "expected_behavior_claims",
        "historical_oracle_claims",
        "environment_facts",
    ):
        for item in behavior[group]:
            for ref in item["evidence_refs"]:
                yield f"/reported_behavior/{group}", ref
    for ref in behavior["reproduction"]["source_evidence_refs"]:
        yield "/reported_behavior/reproduction/source_evidence_refs", ref
    for ref in behavior["reproduction"]["validation_evidence_refs"]:
        yield "/reported_behavior/reproduction/validation_evidence_refs", ref
    for item in report["reported_diagnosis"]["root_cause_claims"]:
        for ref in item["evidence_refs"]:
            yield "/reported_diagnosis/root_cause_claims", ref
    for ref in report["resolution"]["fix_status"]["evidence_refs"]:
        yield "/resolution/fix_status/evidence_refs", ref
    for item in report["resolution"]["resolution_claims"]:
        for ref in item["evidence_refs"]:
            yield "/resolution/resolution_claims", ref
    for ref in report["verification"]["case_verification_status"]["evidence_refs"]:
        yield "/verification/case_verification_status/evidence_refs", ref
    for item in report["unresolved_information"]:
        for ref in item["evidence_refs"]:
            yield "/unresolved_information", ref


def resolve_evidence_content(artifact_path: Path, locator: dict[str, Any]) -> str:
    text = read_text(artifact_path)
    lines = text.splitlines()
    locator_type = locator["locator_type"]
    if locator_type == "line_range":
        start = locator["start_line"]
        end = locator["end_line"]
        if start < 1 or end < start or end > len(lines):
            raise ReportBuildError(
                "validation", "locator_out_of_range", f"{artifact_path}:{start}-{end}"
            )
        return "\n".join(lines[start - 1 : end])
    if locator_type == "whole_artifact":
        return text
    raise ReportBuildError(
        "validation",
        "locator_not_supported_by_builder",
        f"Builder cannot resolve {locator_type} for {artifact_path}",
    )


def semantic_validation_errors(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    artifacts = report["source_bundle"]["source_artifacts"]
    artifact_by_id = {item["artifact_id"]: item for item in artifacts}
    if len(artifact_by_id) != len(artifacts):
        errors.append("/source_bundle/source_artifacts: duplicate artifact_id")
    primary_source = report["source_bundle"]["primary_source_ref"]
    if primary_source not in artifact_by_id:
        errors.append("/source_bundle/primary_source_ref: unresolved reference")

    evidence_items = report["evidence_items"]
    evidence_by_id = {item["evidence_id"]: item for item in evidence_items}
    if len(evidence_by_id) != len(evidence_items):
        errors.append("/evidence_items: duplicate evidence_id")

    api_assertions = report["scope_assertions"]["api_assertions"]
    primary_apis = [item for item in api_assertions if item["relation"] == "primary"]
    if len(primary_apis) != 1:
        errors.append(
            "/scope_assertions/api_assertions: exactly one primary API is required"
        )

    unresolved_items = report["unresolved_information"]
    unresolved_ids = [item["unresolved_id"] for item in unresolved_items]
    if len(set(unresolved_ids)) != len(unresolved_ids):
        errors.append("/unresolved_information: duplicate unresolved_id")

    validation_issues = report["review"]["validation_issues"]
    validation_issue_ids = [item["issue_id"] for item in validation_issues]
    if len(set(validation_issue_ids)) != len(validation_issue_ids):
        errors.append("/review/validation_issues: duplicate issue_id")

    for artifact in artifacts:
        path = PROJECT_ROOT / artifact["local_path"]
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(PROJECT_ROOT.resolve())
        except (OSError, ValueError):
            errors.append(f"/source_bundle/source_artifacts: invalid path {path}")
            continue
        if sha256_file(resolved) != artifact["content_hash"]:
            errors.append(f"/source_bundle/source_artifacts: hash mismatch {path}")

    for evidence in evidence_items:
        artifact = artifact_by_id.get(evidence["source_artifact_ref"])
        if artifact is None:
            errors.append(f"/evidence_items/{evidence['evidence_id']}: unresolved artifact")
            continue
        try:
            content = resolve_evidence_content(
                PROJECT_ROOT / artifact["local_path"], evidence["locator"]
            )
        except ReportBuildError as exc:
            errors.append(f"/evidence_items/{evidence['evidence_id']}: {exc}")
            continue
        if sha256_text(content) != evidence["content_hash"]:
            errors.append(f"/evidence_items/{evidence['evidence_id']}: hash mismatch")
        if evidence["excerpt"] is not None and evidence["excerpt"] != content:
            errors.append(f"/evidence_items/{evidence['evidence_id']}: excerpt mismatch")

    for location, ref in all_evidence_refs(report):
        if ref not in evidence_by_id:
            errors.append(f"{location}: unresolved Evidence reference {ref}")

    reproduction = report["reported_behavior"]["reproduction"]
    for ref in reproduction["source_evidence_refs"]:
        evidence = evidence_by_id.get(ref)
        if evidence is not None and evidence["evidence_kind"] != "reproduction":
            errors.append(
                "/reported_behavior/reproduction/source_evidence_refs: "
                f"{ref} is not reproduction Evidence"
            )
    for ref in reproduction["artifact_refs"]:
        artifact = artifact_by_id.get(ref)
        if artifact is None:
            errors.append(f"/reported_behavior/reproduction/artifact_refs: unresolved {ref}")
        elif artifact["artifact_role"] != "reproduction":
            errors.append(f"/reported_behavior/reproduction/artifact_refs: wrong role {ref}")
    for ref in reproduction["validation_evidence_refs"]:
        evidence = evidence_by_id.get(ref)
        if evidence is None:
            continue
        artifact = artifact_by_id.get(evidence["source_artifact_ref"])
        if artifact is not None and artifact["source_kind"] != "experiment_log":
            errors.append(
                "/reported_behavior/reproduction/validation_evidence_refs: "
                f"{ref} does not originate from an experiment_log"
            )

    for ref in report["resolution"]["fix_artifact_refs"]:
        artifact = artifact_by_id.get(ref)
        if artifact is None:
            errors.append(f"/resolution/fix_artifact_refs: unresolved {ref}")
        elif artifact["artifact_role"] != "resolution":
            errors.append(f"/resolution/fix_artifact_refs: wrong role {ref}")

    input_refs = report["provenance"]["input_artifact_refs"]
    if len(input_refs) != len(set(input_refs)):
        errors.append("/provenance/input_artifact_refs: duplicate reference")
    if set(input_refs) != set(artifact_by_id):
        errors.append("/provenance/input_artifact_refs: must equal consumed Artifact IDs")

    for claim in report["reported_diagnosis"]["root_cause_claims"]:
        if claim["support_status"] != "corroborated":
            continue
        source_ids = {
            evidence_by_id[ref]["source_artifact_ref"]
            for ref in claim["evidence_refs"]
            if ref in evidence_by_id
        }
        hashes = {
            artifact_by_id[ref]["content_hash"]
            for ref in source_ids
            if ref in artifact_by_id
        }
        if len(source_ids) < 2 or len(hashes) < 2:
            errors.append(
                f"/reported_diagnosis/root_cause_claims/{claim['claim_id']}: "
                "corroborated requires distinct non-identical Artifacts"
            )

    fix_status = report["resolution"]["fix_status"]
    if fix_status["value"] == "fixed" and not report["resolution"]["fix_artifact_refs"]:
        errors.append("/resolution/fix_status: fixed requires a captured resolution Artifact")

    if report["provenance"]["content_hash"] != report_content_hash(report):
        errors.append("/provenance/content_hash: hash mismatch")
    return errors


def validate_report(report: dict[str, Any], schema: dict[str, Any]) -> None:
    structural = json_schema_errors(report, schema)
    if structural:
        raise ReportBuildError(
            "validation",
            "schema_validation_error",
            f"Report has {len(structural)} JSON Schema error(s)",
            structural,
        )
    semantic = semantic_validation_errors(report)
    if semantic:
        raise ReportBuildError(
            "validation",
            "semantic_validation_error",
            f"Report has {len(semantic)} semantic validation error(s)",
            semantic,
        )


def derivation_signature(report: dict[str, Any]) -> str:
    value = copy.deepcopy(report)
    value.pop("revision_information", None)
    value.pop("review", None)
    provenance = value["provenance"]
    provenance.pop("generation_run_id", None)
    provenance.pop("generated_at", None)
    provenance.pop("content_hash", None)
    return sha256_bytes(canonical_json_bytes(value))


def revision_files(case_dir: Path) -> list[Path]:
    values: list[tuple[int, Path]] = []
    for path in case_dir.glob("revision_*.json"):
        match = re.fullmatch(r"revision_(\d+)\.json", path.name)
        if match:
            values.append((int(match.group(1)), path))
    return [path for _, path in sorted(values)]


def load_revision_chain(
    case_dir: Path, schema: dict[str, Any]
) -> list[tuple[Path, dict[str, Any]]]:
    files = revision_files(case_dir)
    chain: list[tuple[Path, dict[str, Any]]] = []
    previous: dict[str, Any] | None = None
    report_id: str | None = None
    for expected_revision, path in enumerate(files, 1):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ReportBuildError("lineage", "revision_unreadable", f"{path}: {exc}") from exc
        validate_report(record, schema)
        actual_revision = record["revision_information"]["revision_number"]
        if actual_revision != expected_revision:
            raise ReportBuildError(
                "lineage",
                "revision_sequence_invalid",
                f"{path} contains revision {actual_revision}; expected {expected_revision}",
            )
        current_report_id = record["identity"]["report_id"]
        if report_id is None:
            report_id = current_report_id
        elif current_report_id != report_id:
            raise ReportBuildError("lineage", "report_id_mismatch", str(path))
        parent = record["revision_information"]["parent_revision_ref"]
        if previous is None:
            if parent is not None:
                raise ReportBuildError(
                    "lineage", "initial_revision_has_parent", str(path)
                )
        else:
            expected_parent = {
                "report_id": previous["identity"]["report_id"],
                "revision_number": previous["revision_information"]["revision_number"],
                "content_hash": previous["provenance"]["content_hash"],
            }
            if parent != expected_parent:
                raise ReportBuildError(
                    "lineage", "parent_revision_mismatch", str(path)
                )
        chain.append((path, record))
        previous = record
    return chain


def choose_revision(
    report: dict[str, Any], case_dir: Path, schema: dict[str, Any]
) -> tuple[str, Path | None, dict[str, Any]]:
    chain = load_revision_chain(case_dir, schema) if case_dir.is_dir() else []
    if not chain:
        target = case_dir / "revision_001.json"
        return "generated", target, report

    latest_path, latest = chain[-1]
    if latest["identity"]["report_id"] != report["identity"]["report_id"]:
        raise ReportBuildError("lineage", "report_id_mismatch", str(latest_path))

    old_by_path = {
        item["local_path"]: item["content_hash"]
        for item in latest["source_bundle"]["source_artifacts"]
    }
    for item in report["source_bundle"]["source_artifacts"]:
        old_hash = old_by_path.get(item["local_path"])
        if old_hash is not None and old_hash != item["content_hash"]:
            raise ReportBuildError(
                "lineage",
                "immutable_source_changed",
                f"Source changed in place: {item['local_path']}",
            )

    if derivation_signature(latest) == derivation_signature(report):
        return "unchanged", latest_path, latest

    old_artifacts = latest["source_bundle"]["source_artifacts"]
    new_artifacts = report["source_bundle"]["source_artifacts"]
    old_reproduction = {
        item["local_path"] for item in old_artifacts if item["artifact_role"] == "reproduction"
    }
    new_reproduction = {
        item["local_path"] for item in new_artifacts if item["artifact_role"] == "reproduction"
    }
    if old_reproduction != new_reproduction:
        trigger = "reproduction_updated"
    elif latest["provenance"]["mapping_ref"] != report["provenance"]["mapping_ref"]:
        trigger = "mapping_updated"
    elif latest["provenance"]["builder_ref"] != report["provenance"]["builder_ref"]:
        trigger = "builder_updated"
    elif old_artifacts != new_artifacts:
        trigger = "source_updated"
    else:
        trigger = "data_corrected"

    latest_revision = latest["revision_information"]["revision_number"]
    next_revision = latest_revision + 1
    report["revision_information"] = {
        "revision_number": next_revision,
        "parent_revision_ref": {
            "report_id": latest["identity"]["report_id"],
            "revision_number": latest_revision,
            "content_hash": latest["provenance"]["content_hash"],
        },
        "revision_trigger": trigger,
        "change_summary": f"Regenerated after {trigger.replace('_', ' ')}.",
    }
    report["provenance"]["content_hash"] = report_content_hash(report)
    return "generated", case_dir / f"revision_{next_revision:03d}.json", report


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as target:
            json.dump(value, target, ensure_ascii=False, indent=2)
            target.write("\n")
            target.flush()
            os.fsync(target.fileno())
        os.chmod(temporary, 0o644)
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise ReportBuildError("output", "output_conflict", str(path)) from exc
    finally:
        temporary.unlink(missing_ok=True)


def output_case_dir(report: dict[str, Any]) -> Path:
    report_id = report["identity"]["report_id"]
    source = "dlframe" if "_dlframe_" in report_id else "github"
    return OUTPUT_ROOT / source / report_id


def build_one(
    bundle: CaseBundle,
    run_id: str,
    generated_at: str,
    mapping_hash: str,
    builder_hash: str,
) -> dict[str, Any]:
    if bundle.profile == PROFILE_DLFRAME:
        return build_dlframe_report(
            bundle, run_id, generated_at, mapping_hash, builder_hash
        )
    if bundle.profile == PROFILE_GITHUB:
        return build_github_report(
            bundle, run_id, generated_at, mapping_hash, builder_hash
        )
    raise ReportBuildError("startup", "unsupported_profile", bundle.profile)


def validate_existing(path: Path, schema: dict[str, Any]) -> list[CaseResult]:
    files = sorted(path.rglob("revision_*.json")) if path.is_dir() else [path]
    if not files:
        raise ReportBuildError(
            "validation",
            "validation_target_empty",
            f"No revision_*.json files found under {path}",
        )
    results: list[CaseResult] = []
    for file_path in files:
        try:
            report = json.loads(file_path.read_text(encoding="utf-8"))
            validate_report(report, schema)
            results.append(
                CaseResult("validation", file_path.stem, "validated", str(file_path))
            )
        except Exception as exc:  # validation mode reports all local failures
            if isinstance(exc, ReportBuildError):
                stage, code = exc.stage, exc.code
                details = exc.details
            else:
                stage, code = "validation", "unexpected_validation_error"
                details = []
            results.append(
                CaseResult(
                    "validation",
                    file_path.stem,
                    "failed",
                    str(file_path),
                    stage,
                    code,
                    str(exc),
                    details=details,
                )
            )
    return results


def write_run_log(
    run_id: str,
    generated_at: str,
    dry_run: bool,
    results: Sequence[CaseResult],
) -> Path | None:
    if dry_run:
        return None
    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    payload = {
        "run_id": run_id,
        "builder_version": SCRIPT_VERSION,
        "generated_at": generated_at,
        "counts": counts,
        "results": [result.to_dict() for result in results],
    }
    path = RUN_LOG_ROOT / f"{run_id}.json"
    atomic_write_json(path, payload)
    return path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--all", action="store_true", help="Process all discovered cases")
    actions.add_argument("--case-id", action="append", help="Process one or more case IDs")
    actions.add_argument(
        "--validate-only", type=Path, metavar="PATH", help="Validate one record or directory"
    )
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILE_ALIASES),
        help="Limit discovery to one source profile",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing")
    parser.add_argument("--fail-fast", action="store_true", help="Stop after first failed case")
    parser.add_argument("--show-skipped", action="store_true", help="Print skipped case results")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    schema = load_json_schema()
    mapping_text = read_text(MAPPING_PATH)
    actual_mapping_version = parse_mapping_version(mapping_text)
    if actual_mapping_version != MAPPING_VERSION:
        raise ReportBuildError(
            "startup",
            "mapping_version_mismatch",
            f"Expected {MAPPING_VERSION}, found {actual_mapping_version}",
        )

    if args.validate_only:
        results = validate_existing(args.validate_only, schema)
        print(json.dumps([item.to_dict() for item in results], ensure_ascii=False, indent=2))
        return 1 if any(item.status == "failed" for item in results) else 0

    if args.case_id and not args.profile:
        raise ReportBuildError("startup", "profile_required", "--case-id requires --profile")

    run_id = new_run_id()
    generated_at = utc_now()
    mapping_hash = sha256_file(MAPPING_PATH)
    builder_hash = sha256_file(SCRIPT_PATH)
    case_ids = set(args.case_id) if args.case_id else None
    selected_profile = PROFILE_ALIASES.get(args.profile) if args.profile else None
    bundles: list[CaseBundle] = []
    if selected_profile in (None, PROFILE_DLFRAME):
        bundles.extend(discover_dlframe(case_ids))
    if selected_profile in (None, PROFILE_GITHUB):
        bundles.extend(discover_github(case_ids))
    bundles.sort(
        key=lambda item: (
            PROFILE_ORDER[item.profile],
            0 if item.case_id.isdigit() else 1,
            int(item.case_id) if item.case_id.isdigit() else item.case_id,
        )
    )
    if not bundles:
        raise ReportBuildError("discovery", "no_cases_discovered", "No cases matched")

    if case_ids:
        discovered = {item.case_id for item in bundles}
        missing = sorted(case_ids - discovered)
        if missing:
            raise ReportBuildError(
                "discovery", "case_not_found", f"Cases not found: {missing}"
            )

    results: list[CaseResult] = []
    for bundle in bundles:
        if bundle.preflight_error_code:
            result = CaseResult(
                bundle.profile,
                bundle.case_id,
                "failed",
                error_stage=bundle.preflight_error_stage,
                error_code=bundle.preflight_error_code,
                message=bundle.preflight_error_message,
            )
            results.append(result)
            print(json.dumps(result.to_dict(), ensure_ascii=False))
            if args.fail_fast:
                break
            continue
        if bundle.admission != "candidate":
            status = (
                "skipped_excluded"
                if bundle.admission == "excluded"
                else "skipped_not_selected"
            )
            result = CaseResult(bundle.profile, bundle.case_id, status)
            results.append(result)
            if args.show_skipped:
                print(json.dumps(result.to_dict(), ensure_ascii=False))
            continue
        try:
            report = build_one(
                bundle, run_id, generated_at, mapping_hash, builder_hash
            )
            case_dir = output_case_dir(report)
            status, target, report = choose_revision(report, case_dir, schema)
            validate_report(report, schema)
            if status == "generated" and target is not None and not args.dry_run:
                atomic_write_json(target, report)
            result = CaseResult(
                bundle.profile,
                bundle.case_id,
                status,
                repository_relative(target) if target is not None else None,
            )
        except ReportBuildError as exc:
            result = CaseResult(
                bundle.profile,
                bundle.case_id,
                "failed",
                error_stage=exc.stage,
                error_code=exc.code,
                message=str(exc),
                details=exc.details,
            )
        except Exception as exc:  # isolate unexpected per-case failures
            result = CaseResult(
                bundle.profile,
                bundle.case_id,
                "failed",
                error_stage="internal",
                error_code="unexpected_error",
                message=str(exc),
                traceback_text=traceback.format_exc(),
            )
        results.append(result)
        print(json.dumps(result.to_dict(), ensure_ascii=False))
        if result.status == "failed" and args.fail_fast:
            break

    run_log = write_run_log(run_id, generated_at, args.dry_run, results)
    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    summary = {
        "run_id": run_id,
        "dry_run": args.dry_run,
        "counts": counts,
        "run_log": repository_relative(run_log) if run_log else None,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if counts.get("failed", 0) else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReportBuildError as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "stage": exc.stage,
                    "error_code": exc.code,
                    "message": str(exc),
                    "details": exc.details,
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        raise SystemExit(1)
