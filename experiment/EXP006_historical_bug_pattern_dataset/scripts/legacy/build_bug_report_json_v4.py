#!/usr/bin/env python3
"""Build evidence-grounded Report v4 candidates; assistance is opt-in."""

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
from urllib.parse import urlparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


SCRIPT_VERSION = "4.0.0"
REPORT_SCHEMA_VERSION = "4.0"
MAPPING_VERSION = "4.0"

SCRIPT_PATH = Path(__file__).resolve()
EXP006_DIR = SCRIPT_PATH.parent.parent
PROJECT_ROOT = EXP006_DIR.parent.parent
SCHEMA_PATH = EXP006_DIR / "schemas" / "bug_report_record.schema.json"
V2_SCHEMA_PATH = EXP006_DIR / "schemas" / "legacy" / "bug_report_record_v2.schema.json"
V3_SCHEMA_PATH = EXP006_DIR / "schemas" / "legacy" / "bug_report_record_v3.schema.json"
EXTRACTION_PROMPT_PATH = EXP006_DIR / "schemas" / "report_extraction_prompt.md"
EXTRACTION_ROOT = EXP006_DIR / "quality" / "report_extractions"
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
PROFILE_SNAPSHOT = "github_issue_snapshot_v1"
PROFILE_ALIASES = {
    "dlframe": PROFILE_DLFRAME,
    "github": PROFILE_GITHUB,
    PROFILE_DLFRAME: PROFILE_DLFRAME,
    PROFILE_GITHUB: PROFILE_GITHUB,
}

PROFILE_ORDER = {PROFILE_DLFRAME: 0, PROFILE_GITHUB: 1, PROFILE_SNAPSHOT: 2}
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
    "minified repro": "reproduction",
    "code for reproducing": "reproduction",
    "reproduction": "reproduction",
    "observed behavior": "observed",
    "actual behavior": "observed",
    "observed": "observed",
    "error": "observed",
    "error log": "observed",
    "error messages and stack trace": "observed",
    "expected behavior": "expected",
    "expected": "expected",
    "environment": "environment",
    "versions": "environment",
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
    match = re.search(r"^#\s+Source-to-Report Mapping v([0-9]+\.[0-9]+)(?: \(Draft\))?\s*$", text, re.M)
    if not match:
        raise ReportBuildError("startup", "mapping_version_missing", str(MAPPING_PATH))
    return match.group(1)


def normalize_heading(value: str) -> str:
    value = value.strip().strip("*").strip()
    value = re.sub(r"^#+\s*", "", value)
    # GitHub Issue templates commonly prefix headings with an emoji, for
    # example ``### 🐛 Describe the bug``. The decoration is not part of the
    # heading's semantic identity.
    value = re.sub(r"^[^A-Za-z0-9`]+", "", value)
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

    strong = re.match(r"^(?:\*\*|__)(.+?)(?:\*\*|__)\s*:?[ \t]*(.*)$", stripped)
    if strong:
        raw_heading = strong.group(1).strip()
        key = SECTION_ALIASES.get(normalize_heading(raw_heading))
        if key:
            return key, raw_heading, strong.group(2).strip()

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

    # Lookup hints cannot promote an incidental mention to an affected API.
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
        return "unknown"
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


EXTRACTION_FIELDS = {
    "/scope_assertions/api_assertions": ("api_assertion", "assertion_id"),
    "/reported_behavior/trigger_claims": ("trigger_claim", "claim_id"),
    "/reported_behavior/operation_contexts": ("operation_context", "context_id"),
    "/reported_behavior/failure_observations": ("failure_observation", "observation_id"),
    "/reported_behavior/expected_behavior_claims": ("statement_claim", "claim_id"),
    "/reported_behavior/historical_oracle_claims": ("historical_oracle_claim", "claim_id"),
    "/reported_diagnosis/root_cause_claims": ("root_cause_claim", "claim_id"),
    "/resolution/resolution_claims": ("statement_claim", "claim_id"),
}

V3_EXTRACTION_FIELDS = {
    "/scope_assertions/api_assertions": ("api_assertion", "assertion_id"),
    "/scope_assertions/component_assertions": ("component_assertion", "assertion_id"),
    "/reported_behavior/trigger_claims": ("trigger_claim", "claim_id"),
    "/reported_behavior/operation_contexts": ("operation_context", "context_id"),
    "/reported_behavior/failure_observations": ("failure_observation", "observation_id"),
    "/reported_behavior/expected_behavior_claims": ("statement_claim", "claim_id"),
    "/reported_behavior/historical_oracle_claims": ("historical_oracle_claim", "claim_id"),
    "/reported_behavior/environment_facts": ("environment_fact", "fact_id"),
    "/reported_diagnosis/root_cause_claims": ("root_cause_claim", "claim_id"),
    "/resolution/resolution_claims": ("statement_claim", "claim_id"),
}


def extraction_fields_for(report: dict[str, Any]) -> dict[str, tuple[str, str]]:
    return V3_EXTRACTION_FIELDS if report.get("schema_version") == "3.0" else EXTRACTION_FIELDS


def read_json(path: Path) -> Any:
    return json.loads(read_text(path))


def source_path(relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ReportBuildError("input", "relative_path_required", str(relative))
    path = PROJECT_ROOT / relative
    repository_relative(path)
    if not path.is_file():
        raise ReportBuildError("input", "missing_file", relative)
    return path


def file_ref(path: Path) -> dict[str, str]:
    return {"local_path": repository_relative(path), "content_hash": sha256_file(path)}


def referenced_json(ref: dict[str, str]) -> Any:
    path = source_path(ref["local_path"])
    if sha256_file(path) != ref["content_hash"]:
        raise ReportBuildError("validation", "file_hash_mismatch", ref["local_path"])
    return read_json(path)


def unresolved(report: dict[str, Any], field_path: str, description: str,
               refs: list[str] | None = None, reason: str = "other") -> None:
    report["unresolved_information"].append({
        "unresolved_id": "unresolved_" + short_hash(field_path + description),
        "field_path": field_path, "description": description,
        "reason": reason, "evidence_refs": refs or [],
    })


def snapshot_report(bundle: CaseBundle, run_id: str, generated_at: str,
                    mapping_hash: str, builder_hash: str) -> dict[str, Any]:
    """Read immutable native GitHub JSON; collection metadata has no bug claims."""
    metadata = read_json(bundle.primary_path)
    issue_path = source_path(metadata["issue_path"])
    issue = read_json(issue_path)
    issue_id = str(issue["number"])
    canonical_url = f"https://github.com/pytorch/pytorch/issues/{issue_id}"
    if not issue_id.isdigit() or int(issue_id) < 1 or issue.get("html_url") != canonical_url:
        raise ReportBuildError("input", "invalid_upstream_issue", str(issue.get("html_url")))
    capture_time = explicit_timestamp(metadata.get("captured_at"))
    if capture_time is None or type(metadata.get("comments_complete")) is not bool:
        raise ReportBuildError("input", "capture_metadata_invalid", "Need captured_at and comments_complete")
    artifacts: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []

    def artifact(path, role, kind, external_id, url=None, title=None, state=None,
                 created=None, repository="pytorch/pytorch", captured=capture_time):
        aid = "art_" + short_hash(repository_relative(path))
        if any(a["artifact_id"] == aid for a in artifacts):
            raise ReportBuildError("input", "duplicate_capture_path", str(path))
        item = make_artifact(artifact_id=aid, path=path, role=role, kind=kind,
                             repository=repository, external_id=external_id, url=url,
                             title=title, native_state=state, created_at=created)
        item["captured_at"] = captured
        artifacts.append(item)
        return aid

    def text_evidence(aid, pointer, text, kind, actor=None, actor_role="unknown"):
        if text is None or text == "":
            return
        if not isinstance(text, str):
            raise ReportBuildError("input", "text_required", pointer)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        evidence.append({
            "evidence_id": "ev_" + short_hash(aid + pointer + text),
            "source_artifact_ref": aid, "evidence_kind": kind,
            "locator": {"locator_type": "json_pointer", "value": pointer},
            "excerpt": text if len(text) <= 2000 else None,
            "attribution": {"actor": actor, "actor_role": actor_role},
            "content_hash": sha256_text(text),
        })

    def section_evidence(aid, pointer, section, kind, actor=None,
                         actor_role="unknown"):
        content = section.located_text.replace("\r\n", "\n").replace("\r", "\n")
        if not section.body.strip():
            return None
        evidence_id = "ev_" + short_hash(
            aid + pointer + str(section.start_line) + str(section.end_line) + content
        )
        evidence.append({
            "evidence_id": evidence_id,
            "source_artifact_ref": aid,
            "evidence_kind": kind,
            "locator": {
                "locator_type": "json_string_line_range",
                "value": pointer,
                "start_line": section.start_line,
                "end_line": section.end_line,
            },
            "excerpt": content if len(content) <= 2000 else None,
            "attribution": {"actor": actor, "actor_role": actor_role},
            "content_hash": sha256_text(content),
        })
        return evidence_id

    primary = artifact(issue_path, "report", "github_issue", issue_id, canonical_url,
                       issue.get("title"), normalize_state(issue.get("state")),
                       explicit_timestamp(issue.get("created_at")))
    author = (issue.get("user") or {}).get("login")
    text_evidence(primary, "/title", issue.get("title"), "bug_description", author, "reporter")
    text_evidence(primary, "/body", issue.get("body"), "bug_description", author, "reporter")
    sections = parse_sections(issue.get("body") or "")
    section_kind = {
        "description": "bug_description",
        "reproduction": "reproduction",
        "observed": "observed_output",
        "expected": "expected_behavior",
        "environment": "environment",
        "discussion": "discussion",
        "root_cause": "root_cause_claim",
        "fix": "fix_claim",
        "api": "api_reference",
    }
    section_refs: dict[tuple[str, int], str] = {}
    for section_key, values in sections.items():
        kind = section_kind.get(section_key)
        if kind is None:
            continue
        for index, section in enumerate(values):
            ref = section_evidence(
                primary, "/body", section, kind, author, "reporter"
            )
            if ref is not None:
                section_refs[(section_key, index)] = ref
    seen_comments = set()
    for relative in metadata.get("comments_paths", []):
        path = source_path(relative)
        comments = read_json(path)
        if not isinstance(comments, list):
            raise ReportBuildError("input", "comments_array_required", relative)
        aid = artifact(path, "discussion", "github_issue", issue_id, canonical_url,
                       state=normalize_state(issue.get("state")))
        for index, comment in enumerate(comments):
            cid = comment.get("id")
            if type(cid) is not int or cid in seen_comments:
                raise ReportBuildError("input", "invalid_comment_identity", str(cid))
            if comment.get("html_url") != f"{canonical_url}#issuecomment-{cid}":
                raise ReportBuildError("input", "unrelated_comment", str(cid))
            seen_comments.add(cid)
            actor = (comment.get("user") or {}).get("login")
            text_evidence(aid, f"/{index}/body", comment.get("body"), "discussion",
                          actor, "reporter" if actor and actor == author else "unknown")
    if metadata["comments_complete"] and issue.get("comments") != len(seen_comments):
        raise ReportBuildError("input", "comment_count_mismatch", "Complete capture count disagrees with Issue metadata")
    for companion in metadata.get("companions", []):
        path = source_path(companion["local_path"])
        aid = artifact(path, companion["artifact_role"], companion["source_kind"],
                       companion.get("external_id"), companion.get("url"),
                       state=companion.get("source_native_state"),
                       repository=companion.get("repository"),
                       captured=explicit_timestamp(companion.get("captured_at")))
        role = companion["artifact_role"]
        kind = companion["source_kind"]
        if role == "reproduction":
            content = read_text(path)
            if content:
                evidence.append({
                    "evidence_id": "ev_" + short_hash(aid + content),
                    "source_artifact_ref": aid,
                    "evidence_kind": "reproduction",
                    "locator": {"locator_type": "whole_artifact"},
                    "excerpt": content if len(content) <= 2000 else None,
                    "attribution": {"actor": None, "actor_role": "unknown"},
                    "content_hash": sha256_text(content),
                })
        elif role == "resolution" and kind == "github_pull_request":
            value = read_json(path)
            if isinstance(value, dict):
                actor = (value.get("user") or {}).get("login")
                text_evidence(aid, "/title", value.get("title"), "fix_claim", actor)
                text_evidence(aid, "/body", value.get("body"), "fix_claim", actor)
            elif isinstance(value, list):
                for index, file_item in enumerate(value):
                    if isinstance(file_item, dict):
                        text_evidence(
                            aid, f"/{index}/patch", file_item.get("patch"),
                            "fix_claim", None,
                        )
    artifact(bundle.primary_path, "other", "other", None, repository="HistoricalBug-Fuzzing")
    title_evidence = next(
        (item for item in evidence
         if item["source_artifact_ref"] == primary
         and item["locator"].get("locator_type") == "json_pointer"
         and item["locator"].get("value") == "/title"),
        None,
    )
    report = build_base_report(
        report_id=f"br_pytorch_github_{issue_id}", artifacts=artifacts,
        primary_source_ref=primary, evidence_items=evidence, api_assertions=[],
        component_assertions=[], trigger_claims=[], operation_contexts=[],
        failure_observations=[], expected_claims=[], oracle_claims=[], environment_facts=[],
        reproduction={"availability": "unknown", "source_evidence_refs": [],
                      "artifact_refs": [], "validation_status": "not_attempted",
                      "validation_evidence_refs": []}, root_cause_claims=[],
        resolution_claims=[], fix_artifact_refs=[],
        verification_status={"value": "user_reported", "assertion_basis": "source_explicit",
                             "evidence_refs": [title_evidence["evidence_id"]] if title_evidence else []},
        unresolved=[], validation_issues=[], run_id=run_id, generated_at=generated_at,
        mapping_hash=mapping_hash, builder_hash=builder_hash,
    )
    # Preserve the full text first. Section headings locate observations, not causes.
    body_evidence = next((e for e in evidence if e["source_artifact_ref"] == primary
                          and e["locator"].get("value") == "/body"), None)
    if body_evidence:
        for section_key, target, id_key in (
            ("observed", "failure_observations", "observation_id"),
            ("expected", "expected_behavior_claims", "claim_id"),
        ):
            for index, section in enumerate(sections.get(section_key, [])):
                if section.body.strip() and len(section.body.strip()) <= 4000:
                    evidence_ref = section_refs.get(
                        (section_key, index), body_evidence["evidence_id"]
                    )
                    report["reported_behavior"][target].append({
                        id_key: f"rule_{section_key}_{index + 1}",
                        "statement": section.body.strip(), "assertion_basis": "source_explicit",
                        "evidence_refs": [evidence_ref],
                    })
    reproduction_refs = [
        section_refs[("reproduction", index)]
        for index in range(len(sections.get("reproduction", [])))
        if ("reproduction", index) in section_refs
    ]
    standalone_reproduction_artifacts = [
        item["artifact_id"] for item in artifacts
        if item["artifact_role"] == "reproduction"
    ]
    report["reported_behavior"]["reproduction"].update({
        "availability": reproduction_availability(
            first_section(sections, "reproduction"),
            standalone_reproduction_artifacts,
        ),
        "source_evidence_refs": reproduction_refs,
        "artifact_refs": standalone_reproduction_artifacts,
    })
    unresolved(report, "/reported_behavior", "Raw free text requires semantic extraction/review; metadata parsing does not establish all case facts.",
               [e["evidence_id"] for e in evidence])
    if not reproduction_refs and not standalone_reproduction_artifacts:
        unresolved(report, "/reported_behavior/reproduction", "No explicit reproduction section or standalone reproducer was captured.")
    if not metadata["comments_complete"]:
        unresolved(report, "/source_bundle", "Comment capture is incomplete; absence of contrary evidence is not established.", reason="not_collected")
    return report


def extraction_units(report: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = {a["artifact_id"]: a for a in report["source_bundle"]["source_artifacts"]}
    units = []
    broad_issue_bodies = {
        (item["source_artifact_ref"], item["locator"].get("value"))
        for item in report["evidence_items"]
        if item["locator"].get("locator_type") == "json_pointer"
        and item["locator"].get("value") == "/body"
    }
    for item in report["evidence_items"]:
        source = artifacts[item["source_artifact_ref"]]
        path = source_path(source["local_path"])
        if sha256_file(path) != source["content_hash"]:
            raise ReportBuildError("input", "source_hash_mismatch", source["local_path"])
        content = resolve_evidence_content(path, item["locator"])
        if sha256_text(content) != item["content_hash"]:
            raise ReportBuildError("input", "evidence_hash_mismatch", item["evidence_id"])
        # Dataset/curation and processing logs cannot prove historical statements.
        if source["artifact_role"] in {"curation", "validation_log", "other"}:
            continue
        # The complete Issue body already contains its section line ranges.
        # Send one lossless source unit instead of duplicating the same text.
        locator = item["locator"]
        if (
            report.get("schema_version") != "3.0"
            and
            locator.get("locator_type") == "json_string_line_range"
            and (item["source_artifact_ref"], locator.get("value")) in broad_issue_bodies
        ):
            continue
        units.append({"evidence_id": item["evidence_id"], "content": content,
                      "source_kind": source["source_kind"], "artifact_role": source["artifact_role"],
                      "repository": source["repository"], "url": source["url"],
                      "attribution": item["attribution"], "locator": item["locator"]})
    return units


def collection_at(report: dict[str, Any], pointer: str) -> list[dict[str, Any]]:
    parent, name = pointer.strip("/").split("/")
    return report[parent][name]


def validate_proposals(
    response: Any,
    report: dict[str, Any],
    units: list[dict[str, Any]],
    *,
    allow_primary: bool = False,
) -> list[dict[str, Any]]:
    import jsonschema
    legacy = report.get("schema_version") == "3.0"
    expected_keys = {"candidates", "examined_evidence_ids", "notes"} if legacy else {"candidates", "notes"}
    if not isinstance(response, dict) or set(response) != expected_keys:
        raise ValueError(f"Expected exactly {sorted(expected_keys)}")
    by_id = {u["evidence_id"]: u for u in units}
    if legacy:
        examined = response["examined_evidence_ids"]
        if not isinstance(examined, list) or any(not isinstance(v, str) for v in examined) or len(examined) != len(set(examined)) or set(examined) != set(by_id):
            raise ValueError("Response must account for every supplied evidence unit")
    if not isinstance(response["notes"], list) or any(not isinstance(n, str) or len(n) > 4000 for n in response["notes"]):
        raise ValueError("notes must be bounded strings")
    candidate_limit = 100 if legacy else 50
    if not isinstance(response["candidates"], list) or len(response["candidates"]) > candidate_limit:
        raise ValueError(f"candidates must be an array of at most {candidate_limit} items")
    fields = extraction_fields_for(report)
    schema = load_json_schema(report.get("schema_version", REPORT_SCHEMA_VERSION))
    proposals = []
    seen = set()
    for candidate in response["candidates"]:
        if not isinstance(candidate, dict) or set(candidate) != {"field_path", "value", "evidence"}:
            raise ValueError("Invalid candidate envelope")
        field_path = candidate["field_path"]
        if field_path not in fields or not isinstance(candidate["value"], dict):
            raise ValueError("Candidate field is not allowed")
        definition, id_key = fields[field_path]
        value = copy.deepcopy(candidate["value"])
        if id_key in value or "evidence_refs" in value:
            raise ValueError("Identifiers and evidence references are Builder-owned")
        refs = []
        if not isinstance(candidate["evidence"], list) or not candidate["evidence"]:
            raise ValueError("Candidate needs quoted evidence")
        for support in candidate["evidence"]:
            if not isinstance(support, dict) or set(support) != {"evidence_id", "quote"}:
                raise ValueError("Invalid evidence quote")
            unit = by_id.get(support["evidence_id"])
            quote = support["quote"]
            if unit is None or not isinstance(quote, str) or not quote.strip() or len(quote) > 2000 or quote not in unit["content"]:
                raise ValueError("Quote is not an exact excerpt of supplied evidence")
            refs.append(support["evidence_id"])
        if value.get("assertion_basis") not in {"source_explicit", "code_explicit"}:
            raise ValueError("Model cannot assign a curation or unknown evidence basis")
        if "support_status" in value and value["support_status"] not in {"reported", "disputed", "unknown"}:
            raise ValueError("Model cannot promote confirmation/support strength")
        if not legacy and field_path == "/scope_assertions/api_assertions":
            if value.get("relation") == "primary" and not allow_primary:
                raise ValueError("Model cannot select the primary API")
            api_name = value.get("api_name")
            if not isinstance(api_name, str) or not any(
                api_name.casefold() in quote["quote"].casefold()
                for quote in candidate["evidence"]
            ):
                raise ValueError("API name must occur in its quoted source text")
        if not legacy and "statement" in value:
            if value["statement"] not in [support["quote"] for support in candidate["evidence"]]:
                raise ValueError("statement must equal one verbatim evidence quote")
        candidate_id = "candidate_" + short_hash(canonical_json_bytes(candidate).decode("utf-8"), 24)
        if candidate_id in seen:
            raise ValueError("Duplicate candidate")
        seen.add(candidate_id)
        value.update({id_key: candidate_id, "evidence_refs": list(dict.fromkeys(refs))})
        item_schema = {"$ref": f"#/$defs/{definition}", "$defs": schema["$defs"]}
        jsonschema.Draft202012Validator(item_schema, format_checker=jsonschema.FormatChecker()).validate(value)
        proposals.append({"candidate_id": candidate_id, "field_path": field_path,
                          "item": value, "quotes": candidate["evidence"], "disposition": "pending"})
    return proposals


def request_extraction(request: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    import requests
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise ReportBuildError("llm", "missing_api_key", "DEEPSEEK_API_KEY is not set")
    response = requests.post(
        config["api_url"], headers={"Authorization": f"Bearer {key}"},
        json={"model": config["model"], "messages": request["messages"],
              "thinking": {"type": config["thinking_mode"]},
              "temperature": 0, "max_tokens": config["max_output_tokens"],
              "response_format": {"type": "json_object"}},
        timeout=config["timeout_seconds"], allow_redirects=False,
    )
    response.raise_for_status()
    payload = response.json()
    choice = payload["choices"][0]
    return {
        "content": choice["message"].get("content") or "",
        "finish_reason": choice.get("finish_reason"),
        "response_id": payload.get("id"),
        "model": payload.get("model"),
        "usage": payload.get("usage"),
    }


def schema_definition_closure(
    roots: dict[str, Any], definitions: dict[str, Any]
) -> dict[str, Any]:
    """Return only local definitions transitively referenced by prompt schemas."""
    needed: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            ref = value.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                name = ref.rsplit("/", 1)[-1]
                if name not in needed and name in definitions:
                    needed.add(name)
                    visit(definitions[name])
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(roots)
    return {name: definitions[name] for name in sorted(needed)}


def run_extraction(report: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    units = extraction_units(report)
    schema = load_json_schema()
    field_schemas = {}
    for field_path, (definition, id_key) in EXTRACTION_FIELDS.items():
        value = copy.deepcopy(schema["$defs"][definition])
        value["properties"].pop(id_key)
        value["properties"].pop("evidence_refs")
        value["required"] = [k for k in value["required"] if k not in {id_key, "evidence_refs"}]
        value.pop("allOf", None)
        field_schemas[field_path] = value
    prompt_definitions = schema_definition_closure(field_schemas, schema["$defs"])
    prompt = read_text(EXTRACTION_PROMPT_PATH)
    context = {"source_units": units, "allowed_fields": field_schemas,
               "definitions": prompt_definitions,
               "existing_claims": {p: collection_at(report, p) for p in EXTRACTION_FIELDS}}
    config = {"enabled": bool(args.enable_llm), "model": args.model,
              "api_url": args.api_url, "max_attempts": args.max_attempts,
              "timeout_seconds": args.llm_timeout, "max_prompt_chars": args.max_prompt_chars,
              "max_output_tokens": args.max_output_tokens,
              "thinking_mode": "disabled", "temperature": 0}
    request = {"messages": [{"role": "system", "content": prompt},
                             {"role": "user", "content": json.dumps(context, ensure_ascii=False)}]}
    identity = {"request": request, "config": config,
                "source_refs": [file_ref(source_path(a["local_path"])) for a in report["source_bundle"]["source_artifacts"]],
                "builder_hash": sha256_file(SCRIPT_PATH), "schema_hash": sha256_file(SCHEMA_PATH),
                "mapping_hash": sha256_file(MAPPING_PATH), "prompt_hash": sha256_file(EXTRACTION_PROMPT_PATH)}
    cache_key = sha256_bytes(canonical_json_bytes(identity))
    suffix = "_" + uuid.uuid4().hex[:12] if args.new_extraction_run else ""
    directory = EXTRACTION_ROOT / (cache_key.split(":", 1)[1] + suffix)
    log_path = directory / "extraction.json"
    if log_path.exists() and not args.dry_run:
        log = read_json(log_path)
        if log.get("request_identity") != identity or log.get("cache_key") != cache_key:
            raise ReportBuildError("cache", "identity_mismatch", str(log_path))
        validate_log_payload(log, report)
        return log
    log = {"cache_key": cache_key, "request_identity": identity,
           "source_evidence_ids": [u["evidence_id"] for u in units],
           "routing_reason": "Source free text and rule-derived statements require semantic review; empty-field count is not a trigger.",
           "uncovered_evidence_ids": [u["evidence_id"] for u in units],
           "attempts": [], "proposals": [], "status": "rules_only",
           "llm_consulted": False, "response": None, "review_ref": None}
    if args.dry_run:
        log["status"] = "dry_run"
        return log
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / ".active"
    try:
        lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ReportBuildError("extraction", "run_locked", f"Inspect interrupted/active run before retrying: {directory}") from exc
    os.close(lock_fd)
    try:
        existing_attempts = sorted(directory.glob("request_*.json"))
        if existing_attempts:
            raise ReportBuildError("extraction", "incomplete_run", "A request was reserved; inspect saved evidence or explicitly start --new-extraction-run")
        if args.enable_llm and units:
            log["status"] = "pending_review"
            current = copy.deepcopy(request)
            for attempt in range(1, args.max_attempts + 1):
                if sum(len(m["content"]) for m in current["messages"]) > args.max_prompt_chars:
                    log["status"] = "input_limit"
                    break
                reservation = directory / f"request_{attempt:03d}.json"
                atomic_write_json(reservation, {"attempt": attempt, "request": current})
                log["llm_consulted"] = True
                entry: dict[str, Any] = {"attempt": attempt, "request_ref": file_ref(reservation)}
                log["attempts"].append(entry)
                try:
                    provider_response = request_extraction(current, config)
                except Exception as exc:
                    # No response body, credentials, or unbounded provider error is logged.
                    entry["error_type"] = type(exc).__name__
                    log["status"] = "request_failed"
                    break
                if isinstance(provider_response, str):
                    provider_response = {
                        "content": provider_response, "finish_reason": None,
                        "response_id": None, "model": None, "usage": None,
                    }
                raw = provider_response["content"]
                raw_path = directory / f"response_{attempt:03d}.json"
                atomic_write_json(raw_path, provider_response)
                entry["response_ref"] = file_ref(raw_path)
                entry["finish_reason"] = provider_response.get("finish_reason")
                entry["provider_model"] = provider_response.get("model")
                entry["usage"] = provider_response.get("usage")
                try:
                    if not raw.strip():
                        raise ValueError("empty_response")
                    if provider_response.get("finish_reason") == "length":
                        raise ValueError("truncated_response")
                    parsed = json.loads(raw)
                    proposals = validate_proposals(parsed, report, units)
                except Exception as exc:  # malformed proposals only; never a second transport call on network failure
                    entry["validation_error"] = str(exc)[:2000]
                    log["status"] = "invalid_response"
                    correction = (
                        "Return a smaller valid JSON object using only verbatim source spans. "
                        "Correct only format or reference errors; omit uncertain candidates. "
                        "Do not invent facts. Error: " + str(exc)[:2000]
                    )
                    correction_messages = list(request["messages"])
                    if raw.strip() and provider_response.get("finish_reason") != "length":
                        correction_messages.append({"role": "assistant", "content": raw})
                    correction_messages.append({"role": "user", "content": correction})
                    current = {"messages": correction_messages}
                    continue
                log.update(response=parsed, proposals=proposals, status="pending_review")
                break
        atomic_write_json(log_path, log)
    finally:
        lock.unlink(missing_ok=True)
    return log


def validate_log_payload(log: dict[str, Any], report: dict[str, Any]) -> None:
    if sha256_bytes(canonical_json_bytes(log["request_identity"])) != log["cache_key"]:
        raise ValueError("Extraction request identity hash mismatch")
    for ref in log["request_identity"]["source_refs"]:
        referenced = source_path(ref["local_path"])
        if sha256_file(referenced) != ref["content_hash"]:
            raise ValueError("Extraction source hash mismatch")
    expected_refs = [{"local_path": a["local_path"], "content_hash": a["content_hash"]}
                     for a in report["source_bundle"]["source_artifacts"]]
    if log["request_identity"]["source_refs"] != expected_refs:
        raise ValueError("Extraction sources do not match this Report")
    if type(log.get("llm_consulted")) is not bool or log["llm_consulted"] != bool(log["attempts"]):
        raise ValueError("Consultation status disagrees with saved requests")
    config = log["request_identity"]["config"]
    if len(log["attempts"]) > config["max_attempts"]:
        raise ValueError("Extraction exceeded request budget")
    response_contents = []
    for attempt in log["attempts"]:
        referenced_json(attempt["request_ref"])
        if "response_ref" in attempt:
            response_contents.append(referenced_json(attempt["response_ref"])["content"])
    if log["response"] is not None:
        if not response_contents or json.loads(response_contents[-1]) != log["response"]:
            raise ValueError("Parsed response disagrees with preserved model output")
        expected = validate_proposals(log["response"], report, extraction_units(report))
        actual = [{**p, "disposition": "pending"} for p in log["proposals"]]
        if actual != expected:
            raise ValueError("Extraction candidates disagree with validated response")
    elif log["proposals"]:
        raise ValueError("Extraction candidates require a preserved response")
    if log.get("manual_response") is not None:
        expected = validate_proposals(
            log["manual_response"], report, extraction_units(report), allow_primary=True
        )
        actual = [{**p, "disposition": "pending"} for p in log["manual_proposals"]]
        if actual != expected:
            raise ValueError("Manual candidates disagree with their evidence")
    for proposal in log["proposals"] + log.get("manual_proposals", []):
        disposition = proposal.get("disposition")
        if disposition not in {"pending", "accepted", "rejected"}:
            raise ValueError("Invalid candidate disposition")
        if disposition == "accepted" and proposal["item"] not in collection_at(report, proposal["field_path"]):
            raise ValueError("Accepted candidate missing or altered in Report")


def attach_extraction(report: dict[str, Any], log: dict[str, Any], args: argparse.Namespace) -> None:
    # Hash-named immutable log; no Report hash is embedded in it.
    log_hash = sha256_bytes(canonical_json_bytes(log))
    path = EXTRACTION_ROOT / "records" / (log_hash.split(":", 1)[1] + ".json")
    if not args.dry_run and not path.exists():
        atomic_write_json(path, log)
    report["provenance"]["extraction_run_ref"] = {
        "local_path": repository_relative(path),
        "content_hash": sha256_file(path) if path.exists() else sha256_text(json.dumps(log, ensure_ascii=False, indent=2) + "\n"),
    }
    report["provenance"]["generation_method"] = "llm_assisted_source_mapping" if log["llm_consulted"] else "deterministic_source_mapping"
    unresolved(report, "/review", "Extraction candidates and uncovered source context require human review before downstream use.")
    report["provenance"]["content_hash"] = report_content_hash(report)


def validate_extraction_reference(report: dict[str, Any], log_override=None) -> list[str]:
    try:
        log = log_override if log_override is not None else referenced_json(report["provenance"]["extraction_run_ref"])
        validate_log_payload(log, report)
        expected_method = "llm_assisted_source_mapping" if log["llm_consulted"] else "deterministic_source_mapping"
        if report["provenance"]["generation_method"] != expected_method:
            raise ValueError("generation_method disagrees with extraction log")
        if report["review"]["human_review_status"] == "approved":
            behavior = report["reported_behavior"]
            if not (behavior["trigger_claims"] or behavior["operation_contexts"] or
                    behavior["reproduction"]["source_evidence_refs"] or behavior["reproduction"]["artifact_refs"]):
                raise ValueError("Approved Report lacks basic operation/input context")
            if any(p["disposition"] == "pending" for p in log["proposals"] + log.get("manual_proposals", [])) or not log.get("review_ref"):
                raise ValueError("Approval needs explicit candidate decisions and a bound review record")
            review = referenced_json(log["review_ref"])
            if review.get("decision") != "approved" or review.get("reviewer") != report["review"]["reviewer"] or review.get("reviewed_at") != report["review"]["reviewed_at"]:
                raise ValueError("Report review disagrees with the review record")
            if review.get("critical_statements_checked") is not True or review.get("contradictory_context_checked") is not True:
                raise ValueError("Approval lacks explicit critical-statement/context checks")
            expected_decisions = {p["candidate_id"]: "accept" if p["disposition"] == "accepted" else "reject"
                                  for p in log["proposals"]}
            if review.get("candidate_decisions") != expected_decisions:
                raise ValueError("Candidate dispositions disagree with human decisions")
            if review.get("additional_candidates", []) != log.get("manual_response", {}).get("candidates", []):
                raise ValueError("Manual candidates disagree with human decisions")
            for pointer, value in review.get("status_updates", {}).items():
                section, field = pointer.strip("/").split("/")
                if report[section][field] != value:
                    raise ValueError("Aggregate status disagrees with human decisions")
            previous = referenced_json(review["report_ref"])
            if previous["identity"] != report["identity"] or review["extraction_run_ref"] != previous["provenance"]["extraction_run_ref"]:
                raise ValueError("Review is bound to a different source Report")
            if report["revision_information"]["parent_revision_ref"] != {
                "report_id": previous["identity"]["report_id"],
                "revision_number": previous["revision_information"]["revision_number"],
                "content_hash": previous["provenance"]["content_hash"],
            }:
                raise ValueError("Approved revision is not the reviewed Report's child")
        return []
    except (KeyError, TypeError, ValueError, OSError, ReportBuildError) as exc:
        return [f"/provenance/extraction_run_ref: {exc}"]


def load_json_schema(version: str = REPORT_SCHEMA_VERSION) -> dict[str, Any]:
    if version not in {"2.0", "3.0", "4.0"}:
        raise ReportBuildError("validation", "unsupported_report_version", str(version))
    path = {
        "2.0": V2_SCHEMA_PATH,
        "3.0": V3_SCHEMA_PATH,
        "4.0": SCHEMA_PATH,
    }[version]
    try:
        return json.loads(path.read_text(encoding="utf-8"))
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
    repository_relative(artifact_path)
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
    if locator_type in {"json_pointer", "json_string_line_range"}:
        value = json.loads(text)
        pointer = locator["value"]
        if not pointer.startswith("/") or re.search(r"~(?![01])", pointer):
            raise ReportBuildError("validation", "invalid_json_pointer", pointer)
        try:
            for token in pointer[1:].split("/"):
                token = token.replace("~1", "/").replace("~0", "~")
                if isinstance(value, list):
                    if not re.fullmatch(r"0|[1-9][0-9]*", token):
                        raise ValueError("Invalid array index")
                    value = value[int(token)]
                elif isinstance(value, dict):
                    value = value[token]
                else:
                    raise ValueError("Cannot descend into scalar")
        except (KeyError, IndexError, ValueError) as exc:
            raise ReportBuildError("validation", "locator_unresolved", pointer) from exc
        if not isinstance(value, str):
            raise ReportBuildError("validation", "non_text_evidence", pointer)
        value = value.replace("\r\n", "\n").replace("\r", "\n")
        if locator_type == "json_pointer":
            return value
        pointed_lines = value.splitlines()
        start = locator["start_line"]
        end = locator["end_line"]
        if start < 1 or end < start or end > len(pointed_lines):
            raise ReportBuildError(
                "validation", "locator_out_of_range",
                f"{artifact_path}:{pointer}:{start}-{end}",
            )
        return "\n".join(pointed_lines[start - 1 : end])
    if locator_type == "section":
        sections = parse_sections(text)
        matches = [s for values in sections.values() for s in values
                   if s.heading == locator["value"]]
        if len(matches) != 1:
            raise ReportBuildError("validation", "ambiguous_section", locator["value"])
        return matches[0].located_text
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
    for pointer, (_, id_key) in extraction_fields_for(report).items():
        identifiers = [item[id_key] for item in collection_at(report, pointer)]
        if len(identifiers) != len(set(identifiers)):
            errors.append(f"{pointer}: duplicate {id_key}")

    api_assertions = report["scope_assertions"]["api_assertions"]
    primary_apis = [item for item in api_assertions if item["relation"] == "primary"]
    if (report["schema_version"] == "2.0" or report["review"]["human_review_status"] == "approved") and len(primary_apis) != 1:
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
        except (ReportBuildError, OSError, ValueError) as exc:
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


def validate_report(report: dict[str, Any], schema: dict[str, Any], extraction_log=None) -> None:
    if report.get("schema_version") != schema.get("properties", {}).get("schema_version", {}).get("const"):
        schema = load_json_schema(report.get("schema_version"))
    structural = json_schema_errors(report, schema)
    if structural:
        raise ReportBuildError(
            "validation",
            "schema_validation_error",
            f"Report has {len(structural)} JSON Schema error(s)",
            structural,
        )
    semantic = semantic_validation_errors(report)
    if report["schema_version"] in {"3.0", "4.0"}:
        semantic.extend(validate_extraction_reference(report, extraction_log))
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
    provenance.pop("extraction_run_ref", None)
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
    if bundle.profile == PROFILE_SNAPSHOT:
        return snapshot_report(bundle, run_id, generated_at, mapping_hash, builder_hash)
    if bundle.profile == PROFILE_DLFRAME:
        return build_dlframe_report(
            bundle, run_id, generated_at, mapping_hash, builder_hash
        )
    if bundle.profile == PROFILE_GITHUB:
        return build_github_report(
            bundle, run_id, generated_at, mapping_hash, builder_hash
        )
    raise ReportBuildError("startup", "unsupported_profile", bundle.profile)


def review_report(path: Path, review_path: Path, schema: dict[str, Any], dry_run: bool) -> Path:
    """Apply explicit human decisions to a new revision, without an LLM call."""
    report = read_json(path)
    validate_report(report, schema)
    if report["schema_version"] != "4.0":
        raise ReportBuildError("review", "v4_required", "Re-extract older sources before v4 review")
    review = read_json(review_path)
    allowed_fields = {
        "report_ref", "extraction_run_ref", "reviewer", "reviewed_at", "decision",
        "review_notes", "critical_statements_checked", "contradictory_context_checked",
        "candidate_decisions", "additional_candidates", "remove_claim_ids",
        "resolved_unresolved", "status_updates",
    }
    if not isinstance(review, dict) or set(review) - allowed_fields:
        raise ReportBuildError("review", "invalid_review_fields", "Unknown review fields are not accepted")
    if review.get("report_ref") != file_ref(path) or review.get("extraction_run_ref") != report["provenance"]["extraction_run_ref"]:
        raise ReportBuildError("review", "review_binding_mismatch", "Review must bind exact Report and extraction log")
    if (not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip()
            or explicit_timestamp(review.get("reviewed_at")) is None
            or review.get("decision") not in {"approved", "needs_revision", "rejected"}
            or not isinstance(review.get("review_notes"), str) or not review["review_notes"].strip()):
        raise ReportBuildError("review", "invalid_review", "Need reviewer, UTC timestamp, decision and scoped review_notes")
    if review["decision"] == "approved" and (review.get("critical_statements_checked") is not True or review.get("contradictory_context_checked") is not True):
        raise ReportBuildError("review", "incomplete_review", "Approval requires explicit critical-statement and contrary-context checks")
    chain = load_revision_chain(path.parent, schema)
    if not chain or chain[-1][0].resolve() != path.resolve():
        raise ReportBuildError("review", "not_latest_revision", "Review the latest revision, not an older one")
    log = referenced_json(report["provenance"]["extraction_run_ref"])
    if log.get("review_ref"):
        raise ReportBuildError("review", "already_reviewed", "Re-extract for a new semantic review; do not replay prior decisions")
    decisions = review.get("candidate_decisions", {})
    if not isinstance(decisions, dict) or set(decisions) != {p["candidate_id"] for p in log["proposals"]} or any(v not in {"accept", "reject"} for v in decisions.values()):
        raise ReportBuildError("review", "candidate_decisions_incomplete", "Decide every proposed candidate exactly once")
    manual = review.get("additional_candidates", [])
    log["manual_response"] = {"candidates": manual, "notes": []}
    log["manual_proposals"] = validate_proposals(
        log["manual_response"], report, extraction_units(report), allow_primary=True
    )
    removals = review.get("remove_claim_ids", {})
    if not isinstance(removals, dict):
        raise ReportBuildError("review", "invalid_removal", "remove_claim_ids must be an object")
    for field_path, ids in removals.items():
        if field_path not in EXTRACTION_FIELDS or not isinstance(ids, list) or len(ids) != len(set(ids)):
            raise ReportBuildError("review", "invalid_removal", field_path)
        values = collection_at(report, field_path)
        id_key = EXTRACTION_FIELDS[field_path][1]
        if not set(ids) <= {v[id_key] for v in values}:
            raise ReportBuildError("review", "unknown_claim", field_path)
        values[:] = [v for v in values if v[id_key] not in ids]
    for proposal in log["proposals"] + log["manual_proposals"]:
        action = decisions[proposal["candidate_id"]] if proposal in log["proposals"] else "accept"
        proposal["disposition"] = "accepted" if action == "accept" else "rejected"
        if action == "accept":
            values = collection_at(report, proposal["field_path"])
            values.append(copy.deepcopy(proposal["item"]))
    updates = review.get("status_updates", {})
    allowed_updates = {
        "/resolution/fix_status", "/resolution/fix_artifact_refs",
        "/verification/case_verification_status", "/reported_behavior/reproduction",
    }
    if not isinstance(updates, dict) or set(updates) - allowed_updates:
        raise ReportBuildError("review", "invalid_status_update", "Only explicit human status updates are allowed")
    for pointer, value in updates.items():
        section, field = pointer.strip("/").split("/")
        report[section][field] = copy.deepcopy(value)
    # Status updates must still pass the Schema and evidence-reference checks below.
    resolved = review.get("resolved_unresolved", {})
    known = {u["unresolved_id"] for u in report["unresolved_information"]}
    if not isinstance(resolved, dict) or not set(resolved) <= known or any(not isinstance(v, str) or not v.strip() for v in resolved.values()):
        raise ReportBuildError("review", "invalid_resolution", "Name existing unresolved IDs and give reasons")
    report["unresolved_information"] = [u for u in report["unresolved_information"] if u["unresolved_id"] not in resolved]
    if review["decision"] == "approved" and any(u["field_path"] in {"/review", "/reported_behavior", "/scope_assertions", "/source_bundle"} for u in report["unresolved_information"]):
        raise ReportBuildError("review", "blocking_unresolved", "Resolve broad extraction/capture/API gaps before approval")
    log["review_ref"] = file_ref(review_path)
    log["status"] = "reviewed"
    attach_extraction(report, log, argparse.Namespace(dry_run=dry_run))
    # attach_extraction's pending marker is for machine runs, not this explicit review.
    report["unresolved_information"] = [u for u in report["unresolved_information"] if u["field_path"] != "/review"]
    report["review"].update(human_review_status=review["decision"], reviewer=review["reviewer"],
                            reviewed_at=review["reviewed_at"], review_notes=review["review_notes"])
    previous = chain[-1][1]
    revision = previous["revision_information"]["revision_number"] + 1
    report["revision_information"] = {
        "revision_number": revision,
        "parent_revision_ref": {"report_id": previous["identity"]["report_id"],
                                "revision_number": revision - 1, "content_hash": previous["provenance"]["content_hash"]},
        "revision_trigger": "review_updated", "change_summary": "Applied source-bound human extraction review.",
    }
    report["provenance"].update(generation_run_id=new_run_id(), generated_at=utc_now())
    report["provenance"]["content_hash"] = report_content_hash(report)
    validate_report(report, schema, log if dry_run else None)
    target = path.parent / f"revision_{revision:03d}.json"
    if not dry_run:
        atomic_write_json(target, report)
    return target


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
    actions.add_argument("--snapshot-bundle", type=Path, action="append", help="Collection metadata for immutable raw GitHub captures")
    actions.add_argument("--review-report", type=Path, help="Create a new revision from explicit human decisions")
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
    parser.add_argument("--review-file", type=Path, help="Source-bound human decisions; required with --review-report")
    parser.add_argument("--enable-llm", action="store_true", help="Opt in to paid extraction; dry-run never calls a model")
    parser.add_argument("--model", help="Explicit provider model ID; required with --enable-llm")
    parser.add_argument("--api-url", default="https://api.deepseek.com/chat/completions")
    parser.add_argument("--max-attempts", type=int, choices=(1, 2), default=2)
    parser.add_argument("--llm-timeout", type=int, default=120)
    parser.add_argument("--max-prompt-chars", type=int, default=75000)
    parser.add_argument("--max-output-tokens", type=int, default=8192)
    parser.add_argument("--new-extraction-run", action="store_true", help="Explicitly permit a new bounded run instead of reusing saved extraction")
    args = parser.parse_args(argv)
    if args.enable_llm and not args.model:
        parser.error("--enable-llm requires --model")
    if bool(args.review_report) != bool(args.review_file):
        parser.error("--review-report and --review-file must be supplied together")
    if (args.review_report or args.validate_only) and (args.enable_llm or args.new_extraction_run):
        parser.error("Review/validation cannot call an LLM or start extraction")
    if args.snapshot_bundle and args.profile:
        parser.error("--snapshot-bundle does not use legacy --profile discovery")
    endpoint = urlparse(args.api_url)
    if args.enable_llm and (endpoint.scheme != "https" or not endpoint.netloc or endpoint.username or endpoint.password):
        parser.error("LLM endpoint must be HTTPS without embedded credentials")
    if min(args.llm_timeout, args.max_prompt_chars, args.max_output_tokens) < 1:
        parser.error("Timeout and input/output limits must be positive")
    return args


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

    if args.review_report:
        path = review_report(args.review_report, args.review_file, schema, args.dry_run)
        print(json.dumps({"status": "dry_run" if args.dry_run else "review_recorded", "output_path": repository_relative(path)}))
        return 0

    if args.case_id and not args.profile:
        raise ReportBuildError("startup", "profile_required", "--case-id requires --profile")

    run_id = new_run_id()
    generated_at = utc_now()
    mapping_hash = sha256_file(MAPPING_PATH)
    builder_hash = sha256_file(SCRIPT_PATH)
    case_ids = set(args.case_id) if args.case_id else None
    selected_profile = PROFILE_ALIASES.get(args.profile) if args.profile else None
    bundles: list[CaseBundle] = []
    if args.snapshot_bundle:
        for path in args.snapshot_bundle:
            try:
                repository_relative(path)
                metadata = read_json(path)
                issue = read_json(source_path(metadata["issue_path"]))
                bundles.append(CaseBundle(PROFILE_SNAPSHOT, str(issue["number"]), path))
            except (ReportBuildError, OSError, ValueError, KeyError, TypeError) as exc:
                bundles.append(CaseBundle(PROFILE_SNAPSHOT, path.stem, path,
                                         preflight_error_stage="discovery",
                                         preflight_error_code="invalid_snapshot_bundle",
                                         preflight_error_message=f"{path}: {exc}"))
    if not args.snapshot_bundle and selected_profile in (None, PROFILE_DLFRAME):
        bundles.extend(discover_dlframe(case_ids))
    if not args.snapshot_bundle and selected_profile in (None, PROFILE_GITHUB):
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
            log = run_extraction(report, args)
            attach_extraction(report, log, args)
            case_dir = output_case_dir(report)
            status, target, report = choose_revision(report, case_dir, schema)
            validate_report(report, schema, log if args.dry_run and status != "unchanged" else None)
            if status == "generated" and target is not None and not args.dry_run:
                atomic_write_json(target, report)
            result = CaseResult(
                bundle.profile,
                bundle.case_id,
                "dry_run" if args.dry_run else status,
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
