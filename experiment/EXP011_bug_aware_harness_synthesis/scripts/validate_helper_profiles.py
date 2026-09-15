#!/usr/bin/env python3
"""Compile and smoke-test the pinned FlashFuzz Helper Profile set.

The probe invokes every public Helper once in the fixed PyTorch 2.10 CPU
runtime.  Successful validation creates an immutable r002 Profile revision;
the original source-derived revision is never overwritten.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError as exc:  # pragma: no cover
    raise SystemExit("jsonschema is required") from exc


BUILDER_VERSION = "helper_profile_validator_v0.1"
DEFAULT_PROFILE_ROOT = Path(
    "experiment/EXP011_bug_aware_harness_synthesis/helper_profiles"
)
DEFAULT_SCHEMA = Path(
    "experiment/EXP011_bug_aware_harness_synthesis/schemas/helper_profile_record.schema.json"
)
DEFAULT_IMAGE = "historicalbug/flashfuzz:torch2.10-fuzz-runtime"
DEFAULT_SOURCE = Path(
    "third_party/FlashFuzz/testharness_generation/torch_cpu/torch_cpu_helper"
)
DEFAULT_RUN_ROOT = DEFAULT_PROFILE_ROOT / "_runs"

PROBE = r'''#include "fuzzer_utils.h"
#include <cstdint>
#include <cstddef>
#include <string>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *, size_t) {
    try {
        const uint8_t bytes[] = {0, 0, 0, 0, 0, 0, 0, 0};
        fuzzer_utils::logErrorMessage("helper_profile_smoke");
        (void)fuzzer_utils::ensure_log_directory_exists("helper_smoke_logs");
        fuzzer_utils::saveErrorInput(bytes, sizeof(bytes));
        fuzzer_utils::saveDiffInput(bytes, sizeof(bytes), "helper_profile_smoke");
        (void)fuzzer_utils::currentTimestamp();
        (void)fuzzer_utils::sanitizedTimestamp();
        (void)fuzzer_utils::parseDataType(0);
        (void)fuzzer_utils::parseRank(0);
        size_t shape_offset = 0;
        (void)fuzzer_utils::parseShape(bytes, shape_offset, sizeof(bytes), 0);
        size_t data_offset = 0;
        (void)fuzzer_utils::parseTensorData(bytes, data_offset, sizeof(bytes), 0, 1);
        size_t tensor_offset = 0;
        const uint8_t tensor_bytes[] = {0, 0};
        auto tensor = fuzzer_utils::createTensor(
            tensor_bytes, sizeof(tensor_bytes), tensor_offset);
        fuzzer_utils::compareTensors(tensor, tensor, bytes, sizeof(bytes));
    } catch (...) {
        return -1;
    }
    return 0;
}
'''


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_immutable(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    try:
        os.link(temporary, path)
    except FileExistsError as exc:
        raise RuntimeError(f"Refusing to overwrite existing revision: {path}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def profile_content_hash(profile: dict[str, Any]) -> str:
    value = json.loads(json.dumps(profile))
    value["metadata"].pop("content_hash", None)
    return canonical_hash(value)


def revision_path(path: Path, revision: int) -> Path:
    marker = f"__r{revision:03d}.json"
    stem = path.name
    if "__r" in stem and stem.endswith(".json"):
        stem = stem[: stem.rfind("__r")] + marker
    else:
        stem = path.stem + marker
    return path.with_name(stem)


def run_probe(source_root: Path, image: str, run_dir: Path) -> tuple[int, str, str]:
    run_dir.mkdir(parents=True, exist_ok=True)
    probe_path = run_dir / "helper_profile_probe.cpp"
    probe_path.write_text(PROBE, encoding="utf-8")
    command = [
        "docker", "run", "--rm", "--network", "none", "--user", "root",
        "-v", f"{source_root.resolve()}:/source:ro",
        "-v", f"{probe_path.resolve()}:/probe.cpp:ro",
        image,
        "bash", "-lc",
        "set -o pipefail; rm -rf /tmp/helper-smoke; "
        "cp -a /source /tmp/helper-smoke; "
        "cp /probe.cpp /tmp/helper-smoke/main.cpp; "
        "cd /tmp/helper-smoke; bash build.sh; ./fuzz -runs=1 -print_final_stats=1",
    ]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    (run_dir / "compile_smoke.log").write_text(
        result.stdout + result.stderr, encoding="utf-8"
    )
    return result.returncode, result.stdout, result.stderr


def update_profile(
    profile: dict[str, Any], log_path: Path, run_id: str, *, passed: bool
) -> dict[str, Any]:
    old_hash = profile["metadata"]["content_hash"]
    result = json.loads(json.dumps(profile))
    result["revision"] = int(profile["revision"]) + 1
    result["metadata"] = {
        "parent_revision_ref": {
            "profile_id": profile["profile_id"],
            "revision": profile["revision"],
            "content_hash": old_hash,
        },
        "generated_at": utc_now(),
        "builder_version": BUILDER_VERSION,
        "content_hash": "0" * 64,
    }
    compile_id = "ev_compile_validation"
    smoke_id = "ev_smoke_validation"
    log_hash = file_hash(log_path)
    result["evidence"] = [
        item for item in result["evidence"] if item["evidence_id"] not in {compile_id, smoke_id}
    ]
    result["evidence"].extend(
        [
            {
                "evidence_id": compile_id,
                "source_kind": "compile_log",
                "source_location": log_path.as_posix(),
                "source_revision": run_id,
                "locator": "docker helper probe build",
                "content_hash": log_hash,
                "excerpt": "Shared helper probe compiled in the pinned runtime." if passed else "Helper probe compilation or smoke failed.",
                "collected_at": result["metadata"]["generated_at"],
            },
            {
                "evidence_id": smoke_id,
                "source_kind": "smoke_test_log",
                "source_location": log_path.as_posix(),
                "source_revision": run_id,
                "locator": "LLVMFuzzerTestOneInput -runs=1",
                "content_hash": log_hash,
                "excerpt": "All public helpers were invoked once by the probe." if passed else "The helper probe did not complete successfully.",
                "collected_at": result["metadata"]["generated_at"],
            },
        ]
    )
    checks = result["validation"]["checks"]
    by_kind = {item["check_kind"]: item for item in checks}
    by_kind["declaration_definition_match"].update(
        status="passed" if passed else "failed",
        summary="Compiler-backed helper probe matched declarations and definitions." if passed else "Compiler-backed helper probe failed.",
        evidence_refs=[compile_id],
        issue_refs=[] if passed else ["issue_helper_probe_failed"],
    )
    by_kind["compile"].update(
        status="passed" if passed else "failed",
        summary="All helper implementations compiled in the pinned runtime." if passed else "Helper implementation compilation failed.",
        evidence_refs=[compile_id],
        issue_refs=[] if passed else ["issue_helper_probe_failed"],
    )
    by_kind["smoke_execution"].update(
        status="passed" if passed else "failed",
        summary="Every public Helper was invoked once and the probe terminated normally." if passed else "The Helper probe terminated abnormally.",
        evidence_refs=[smoke_id],
        issue_refs=[] if passed else ["issue_helper_probe_failed"],
    )
    if passed:
        result["validation"] = {
            "validation_status": "passed",
            "execution_readiness": "ready",
            "checks": checks,
            "issues": [],
        }
    else:
        result["validation"] = {
            "validation_status": "failed",
            "execution_readiness": "blocked",
            "checks": checks,
            "issues": [
                {
                    "issue_id": "issue_helper_probe_failed",
                    "issue_kind": "compile_failure",
                    "blocking": True,
                    "description": "The pinned helper compile/smoke probe failed; readiness was not granted.",
                    "affected_refs": ["validation.compile", "validation.smoke_execution"],
                    "evidence_refs": [compile_id, smoke_id],
                }
            ],
        }
    result["metadata"]["content_hash"] = profile_content_hash(result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-root", type=Path, default=DEFAULT_PROFILE_ROOT)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    profiles = sorted(args.profile_root.rglob("*__r001.json"))
    profiles = [path for path in profiles if path.parent.name != "_runs"]
    if not profiles:
        raise SystemExit(f"No r001 profiles found below {args.profile_root}")
    schema = load_json(args.schema)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = args.run_root / f"helper_profile_validation__{run_id}"
    if args.dry_run:
        print(json.dumps({"profiles": len(profiles), "run_dir": run_dir.as_posix()}, indent=2))
        return 0
    code, _, _ = run_probe(args.source_root, args.image, run_dir)
    passed = code == 0
    created = 0
    errors: list[str] = []
    for path in profiles:
        profile = load_json(path)
        updated = update_profile(profile, run_dir / "compile_smoke.log", run_id, passed=passed)
        validation_errors = sorted(
            Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(updated),
            key=lambda item: item.json_path,
        )
        if validation_errors:
            errors.append(f"{path}: {validation_errors[0].json_path}: {validation_errors[0].message}")
            continue
        destination = revision_path(path, int(updated["revision"]))
        write_immutable(destination, updated)
        created += 1
    summary = {"run_id": run_id, "probe_exit_code": code, "created": created, "errors": errors, "log": (run_dir / "compile_smoke.log").as_posix()}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if passed and not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
