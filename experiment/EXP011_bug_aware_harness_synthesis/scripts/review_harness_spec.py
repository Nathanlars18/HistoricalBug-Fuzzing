#!/usr/bin/env python3
"""Create an immutable, exact-hash human review record for one HarnessSpec."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


ROOT = Path("experiment/EXP011_bug_aware_harness_synthesis")
REVIEW_RULES_VERSION = "1.3"
REVIEW_SCHEMA_VERSION = "1.1"


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Required file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(resolved)


def safe_component(value: str) -> str:
    result = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("._-").lower()
    if not result:
        raise ValueError("Empty path component")
    return result


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_immutable(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise ValueError(f"Refusing to overwrite immutable review record: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    try:
        os.link(temporary, path)
    except FileExistsError as exc:
        raise ValueError(f"Concurrent review creation detected: {path}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def artifact_ref(path: Path, version: str) -> dict[str, Any]:
    return {
        "artifact_id": path.name,
        "artifact_version": version,
        "content_hash": file_hash(path),
        "relative_path": relative_path(path),
    }


def freeze_rules(source: Path, root: Path) -> dict[str, Any]:
    digest = file_hash(source)
    target = root / f"harness_spec_human_review_rules__v{REVIEW_RULES_VERSION}__sha256_{digest}.md"
    payload = source.read_bytes()
    root.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() != payload:
            raise ValueError(f"Frozen review Rules hash collision: {target}")
    else:
        temporary = target.with_suffix(target.suffix + f".{uuid.uuid4().hex}.tmp")
        temporary.write_bytes(payload)
        try:
            os.link(temporary, target)
        except FileExistsError:
            if target.read_bytes() != payload:
                raise ValueError(f"Concurrent frozen review Rules mismatch: {target}")
        finally:
            temporary.unlink(missing_ok=True)
    return artifact_ref(target, REVIEW_RULES_VERSION)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harness-spec", type=Path, required=True)
    parser.add_argument("--decision", choices=("approved", "needs_revision"), required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--review-revision", type=int, default=1)
    parser.add_argument("--parent-review", type=Path)
    parser.add_argument(
        "--finding-json", action="append", type=json.loads, default=[],
        help="Repeat one JSON object per criterion-scoped finding.",
    )
    parser.add_argument("--review-notes")
    parser.add_argument(
        "--record-schema", type=Path,
        default=ROOT / "schemas/harness_spec_record.schema.json",
    )
    parser.add_argument(
        "--review-schema", type=Path,
        default=ROOT / "schemas/harness_spec_review_record.schema.json",
    )
    parser.add_argument(
        "--record-schema-core", type=Path,
        default=ROOT / "schemas/harness_spec_record_core__v2_2.schema.json",
    )
    parser.add_argument(
        "--rules", type=Path,
        default=ROOT / "schemas/harness_spec_human_review_rules.md",
    )
    parser.add_argument(
        "--output-root", type=Path, default=ROOT / "harness_spec_reviews"
    )
    parser.add_argument(
        "--review-artifacts", type=Path,
        default=ROOT / "harness_spec_review_artifacts",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.review_revision < 1:
        parser.error("--review-revision must be positive")
    if args.review_revision == 1 and args.parent_review is not None:
        parser.error("review revision 1 must not use --parent-review")
    if args.review_revision > 1 and args.parent_review is None:
        parser.error("review revision 2+ requires --parent-review")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        spec = load_json(args.harness_spec)
        spec_schema = load_json(args.record_schema)
        core_schema = load_json(args.record_schema_core)
        registry = Registry().with_resource(
            core_schema["$id"], Resource.from_contents(core_schema)
        )
        errors = sorted(
            Draft202012Validator(
                spec_schema, registry=registry, format_checker=FormatChecker()
            ).iter_errors(spec),
            key=lambda item: item.json_path,
        )
        if errors:
            raise ValueError(
                f"HarnessSpec Schema error at {errors[0].json_path}: {errors[0].message}"
            )
        if spec.get("schema_version") != "2.2":
            raise ValueError("Only HarnessSpec v2.2 is eligible for external review")
        if spec["review"].get("validation_status") != "passed":
            raise ValueError("HarnessSpec automatic validation has not passed")
        if not args.rules.read_text(encoding="utf-8").startswith(
            "# HarnessSpec Human Review Rules v1.3"
        ):
            raise ValueError("Human review Rules version is incompatible")

        reviewer = args.reviewer.strip()
        if not reviewer:
            raise ValueError("--reviewer must contain non-whitespace text")
        if not all(isinstance(item, dict) for item in args.finding_json):
            raise ValueError("Each --finding-json value must be a JSON object")
        blocking = [item for item in args.finding_json if item.get("severity") == "blocking"]
        if args.decision == "approved" and blocking:
            raise ValueError("approved review cannot contain a blocking finding")
        if args.decision == "needs_revision" and not blocking:
            raise ValueError("needs_revision requires at least one blocking finding")

        identity = spec["identity"]
        revision = spec["revision_information"]["revision_number"]
        subject = {
            "spec_id": identity["spec_id"],
            "revision_number": revision,
            "content_hash": canonical_hash(spec),
            "relative_path": relative_path(args.harness_spec),
        }
        review_schema = load_json(args.review_schema)
        parent_review_ref = None
        if args.parent_review is not None:
            parent = load_json(args.parent_review)
            parent_errors = sorted(
                Draft202012Validator(
                    review_schema, format_checker=FormatChecker()
                ).iter_errors(parent),
                key=lambda item: item.json_path,
            )
            if parent_errors:
                raise ValueError(
                    f"Parent review Schema error at {parent_errors[0].json_path}: "
                    f"{parent_errors[0].message}"
                )
            if parent.get("subject") != subject:
                raise ValueError("Parent review is bound to a different HarnessSpec")
            if parent.get("review_revision") != args.review_revision - 1:
                raise ValueError("Parent review revision is not the immediate predecessor")
            parent_review_ref = {
                "review_id": parent["review_id"],
                "review_revision": parent["review_revision"],
                "content_hash": canonical_hash(parent),
                "relative_path": relative_path(args.parent_review),
            }
        review_id = (
            f"hs_review:{identity['spec_id']}:r{revision}:rr{args.review_revision}"
        )
        rules_ref = artifact_ref(args.rules, REVIEW_RULES_VERSION)
        record = {
            "schema_version": REVIEW_SCHEMA_VERSION,
            "review_id": review_id,
            "review_revision": args.review_revision,
            "parent_review_ref": parent_review_ref,
            "subject": subject,
            "rules_ref": rules_ref,
            "decision": args.decision,
            "findings": args.finding_json,
            "reviewer_id": reviewer,
            "reviewed_at": utc_now(),
            "review_notes": args.review_notes,
        }
        review_errors = sorted(
            Draft202012Validator(
                review_schema, format_checker=FormatChecker()
            ).iter_errors(record),
            key=lambda item: item.json_path,
        )
        if review_errors:
            raise ValueError(
                f"Review record Schema error at {review_errors[0].json_path}: "
                f"{review_errors[0].message}"
            )
        if not args.dry_run:
            record["rules_ref"] = freeze_rules(args.rules, args.review_artifacts)
            frozen_errors = sorted(
                Draft202012Validator(
                    review_schema, format_checker=FormatChecker()
                ).iter_errors(record),
                key=lambda item: item.json_path,
            )
            if frozen_errors:
                raise ValueError(
                    f"Frozen review record Schema error at "
                    f"{frozen_errors[0].json_path}: {frozen_errors[0].message}"
                )
        output = (
            args.output_root
            / safe_component(identity["framework"])
            / safe_component(identity["target_api"])
            / identity["spec_mode"]
            / f"{safe_component(identity['spec_id'])}_r{revision}__review_r{args.review_revision}.json"
        )
        if not args.dry_run:
            write_immutable(output, record)
        print(json.dumps({
            "status": "dry_run" if args.dry_run else "success",
            "review_id": review_id,
            "review_revision": args.review_revision,
            "decision": args.decision,
            "subject_content_hash": record["subject"]["content_hash"],
            "output_path": None if args.dry_run else str(output),
        }, ensure_ascii=False, indent=2))
        return 0
    except (OSError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "input_error", "message": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
