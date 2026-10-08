"""Diagnostic cumulative native coverage over verified round-end replay profiles.

Counters are merged by LLVM before export; covered counts represent a union,
not a sum of round percentages. Different harnesses may share the same pinned
framework objects. This module never changes feedback or active fuzz budgets.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

try:
    from .coverage_replay import CoverageError, cleanup_container, export_measurements, load_scope, sha256
except ImportError:
    from coverage_replay import CoverageError, cleanup_container, export_measurements, load_scope, sha256


def merge_profiles(scope_path: Path, profiles: list[Path], output_root: Path) -> Path:
    if not profiles:
        raise CoverageError("No complete replay profiles are available for cumulative coverage")
    scope = load_scope(scope_path)
    profile_inputs = []
    for profile in profiles:
        source_summary = profile.with_name("coverage_summary.json")
        if not source_summary.is_file():
            raise CoverageError(f"Round Coverage Summary is missing for profile: {profile}")
        summary = json.loads(source_summary.read_text(encoding="utf-8"))
        if summary.get("profile_hash") != sha256(profile):
            raise CoverageError(f"Round Coverage profile hash differs from its Summary: {profile}")
        quality = summary.get("quality_status")
        if quality not in {"complete", "partial_warning"}:
            raise CoverageError(f"Round Coverage quality is not union-eligible: {quality}")
        profile_inputs.append({"path": str(profile.resolve()), "hash": sha256(profile),
                               "summary_hash": sha256(source_summary), "quality_status": quality,
                               "warnings": summary.get("warnings", [])})
    inputs = {"scope_hash": sha256(scope_path),
              "profiles": profile_inputs,
              "worker_hash": sha256(Path(__file__)),
              "exporter_hash": sha256(Path(__file__).with_name("coverage_replay.py"))}
    key = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
    cache_key = key[:24]
    output_root.mkdir(parents=True, exist_ok=True)
    base = output_root / cache_key
    prior = [base] if base.exists() else []
    prior.extend(sorted(output_root.glob(f"{cache_key}__attempt_[0-9][0-9][0-9]")))
    for existing in prior:
        summary_path = existing / "coverage_summary.json"
        if not summary_path.is_file():
            continue
        summary = json.loads(summary_path.read_text())
        profile_path = existing / "coverage.profdata"
        if (summary.get("inputs") != inputs or not profile_path.is_file()
                or summary.get("profile_hash") != sha256(profile_path)):
            raise CoverageError(f"Cumulative coverage cache provenance differs: {existing}")
        return summary_path
    if not prior:
        output = base
    else:
        used = [int(path.name.rsplit("_", 1)[1]) for path in prior if "__attempt_" in path.name]
        next_number = max([1, *used]) + 1
        output = output_root / f"{cache_key}__attempt_{next_number:03d}"
    summary_path = output / "coverage_summary.json"
    output.mkdir(parents=True)
    (output / "inputs.json").write_text(json.dumps(inputs, indent=2) + "\n")
    name = "hbfg-cumulative-" + uuid.uuid4().hex[:16]
    argv = ["docker", "run", "--rm", "--network", "none", "--name", name,
            "-v", f"{scope_path.resolve()}:/scope.json:ro",
            "-v", f"{Path(__file__).resolve().parent}:/scripts:ro",
            "-v", f"{output.resolve()}:/output",
            "-e", f"HOST_UID={os.getuid()}", "-e", f"HOST_GID={os.getgid()}"]
    for index, path in enumerate(profiles):
        argv.extend(["-v", f"{path.resolve()}:/profiles/{index:04d}.profdata:ro"])
    argv.extend(["--entrypoint", "python3", scope["coverage_image"],
                 "/scripts/coverage_cumulative.py", "--worker"])
    try:
        process = subprocess.run(argv, capture_output=True, text=True, timeout=600, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        (output / "merge.log").write_text(str(exc) + "\n")
        raise CoverageError(f"Cumulative merge failed; see {output}") from exc
    finally:
        cleanup_errors = cleanup_container(name)
        (output / "cleanup.json").write_text(json.dumps(cleanup_errors) + "\n")
    (output / "merge.log").write_text(process.stdout + "\n" + process.stderr)
    if process.returncode:
        raise CoverageError(f"Cumulative LLVM merge/export failed; see {output}")
    try:
        result = json.loads(process.stdout)
    except ValueError as exc:
        raise CoverageError(f"Invalid cumulative worker output; see {output}") from exc
    if result.get("scope_hash") != inputs["scope_hash"] or result.get("profile_hash") != sha256(output / "coverage.profdata"):
        raise CoverageError("Cumulative worker output differs from requested inputs")
    source_warnings = [warning for item in inputs["profiles"] for warning in item["warnings"]]
    result["warnings"] = list(dict.fromkeys([*source_warnings, *result.get("warnings", [])]))
    if source_warnings or result.get("warnings"):
        result["quality_status"] = "partial_warning"
    result.update(inputs=inputs, cleanup_warnings=cleanup_errors,
                  measurement_scope="frozen_round_end_corpus_replay_union")
    summary_path.write_text(json.dumps(result, indent=2) + "\n")
    return summary_path


def worker() -> int:
    scope = load_scope(Path("/scope.json"))
    inputs = json.loads(Path("/output/inputs.json").read_text())
    profiles = [Path(f"/profiles/{i:04d}.profdata") for i in range(len(inputs["profiles"]))]
    for profile, reference in zip(profiles, inputs["profiles"]):
        if sha256(profile) != reference["hash"]:
            raise CoverageError("Cumulative input profile changed")
    profile = Path("/output/coverage.profdata")
    subprocess.run(["llvm-profdata-20", "merge", "-sparse", *(str(p) for p in profiles),
                    "-o", str(profile)], capture_output=True, text=True, timeout=300, check=True)
    exported = export_measurements(scope, profile)
    os.chown(profile, int(os.environ["HOST_UID"]), int(os.environ["HOST_GID"]))
    print(json.dumps({"scope_hash": sha256(Path("/scope.json")), "profile_hash": sha256(profile),
                      "pytorch_commit": scope["pytorch_commit"], "quality_status":
                      "partial_warning" if exported["warnings"] else "complete", **exported}))
    return 0


if __name__ == "__main__" and sys.argv[1:] == ["--worker"]:
    try:
        raise SystemExit(worker())
    except (CoverageError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
