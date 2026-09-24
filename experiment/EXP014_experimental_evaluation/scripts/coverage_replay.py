#!/usr/bin/env python3
"""Replay an immutable round-end corpus against the pinned PyTorch coverage build.

Only diagnostic coverage is produced; replay never consumes active fuzzing time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping


class CoverageError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_scope(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        value.get("scope_version") != 1
        or not isinstance(value.get("coverage_image"), str)
        or not value["coverage_image"].startswith("sha256:")
        or len(value["coverage_image"]) != 71
        or re.fullmatch(r"sha256:[0-9a-f]{64}", value["coverage_image"]) is None
        or not isinstance(value.get("source_prefix"), str)
        or not value["source_prefix"].startswith("/root/pytorch/")
        or not isinstance(value.get("objects"), list)
        or not value["objects"]
        or any(not isinstance(item, str) or not item.startswith("/root/pytorch/build-cov/") for item in value["objects"])
        or not isinstance(value.get("object_build_ids"), dict)
        or set(value.get("object_build_ids", {})) != set(value["objects"])
        or any(not isinstance(item, str) or re.fullmatch(r"[0-9a-f]{40}", item) is None
               for item in value["object_build_ids"].values())
        or not isinstance(value.get("pytorch_commit"), str)
        or re.fullmatch(r"[0-9a-f]{40}", value["pytorch_commit"]) is None
        or not isinstance(value.get("replay_batch_size"), int)
        or isinstance(value["replay_batch_size"], bool)
        or not 1 <= value["replay_batch_size"] <= 256
    ):
        raise CoverageError("Invalid coverage scope or unpinned coverage image")
    return value


def verified_corpus_files(manifest: Mapping[str, Any], corpus_dir: Path) -> list[Path]:
    result: list[Path] = []
    root = corpus_dir.resolve()
    for item in manifest["files"]:
        path = (root / item["corpus_relative_path"]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise CoverageError(f"Corpus file unavailable: {item['corpus_relative_path']}")
        if sha256(path) != item["file_ref"]["content_hash"]:
            raise CoverageError(f"Corpus file hash mismatch: {path}")
        result.append(path)
    if len(result) != len(set(result)):
        raise CoverageError("Duplicate corpus path")
    return sorted(result)


def replay(
    *,
    scope_path: Path,
    corpus_manifest: Mapping[str, Any],
    corpus_dir: Path,
    harness_binary: Path,
    output_dir: Path,
    timeout_seconds: int = 1800,
) -> Path:
    """Run the coverage worker; raise CoverageError without altering fuzz results."""
    scope = load_scope(scope_path)
    files = verified_corpus_files(corpus_manifest, corpus_dir)
    if not files:
        raise CoverageError("Frozen corpus is empty; no coverage replay input")
    if not harness_binary.is_file():
        raise CoverageError("Harness binary is unavailable")
    output_dir.mkdir(parents=True, exist_ok=False)
    argv = [
        "docker", "run", "--rm",
        "-v", f"{harness_binary.resolve().parent}:/artifact:ro",
        "-v", f"{corpus_dir.resolve()}:/corpus:ro",
        "-v", f"{scope_path.resolve()}:/scope.json:ro",
        "-v", f"{Path(__file__).resolve()}:/coverage_replay.py:ro",
        "-v", f"{output_dir.resolve()}:/output",
        "-e", f"HOST_UID={os.getuid()}",
        "-e", f"HOST_GID={os.getgid()}",
        "-e", "LD_LIBRARY_PATH=/root/pytorch/build-cov/lib",
        "--entrypoint", "python3", scope["coverage_image"],
        "/coverage_replay.py", "--worker",
    ]
    try:
        process = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_seconds, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CoverageError(f"Coverage container unavailable or timed out: {exc}") from exc
    log = output_dir / "replay.log"
    log.write_text(process.stdout + "\n" + process.stderr, encoding="utf-8")
    if process.returncode != 0:
        raise CoverageError(f"Coverage replay failed (exit {process.returncode}); see {log}")
    summary = output_dir / "coverage_summary.json"
    if not summary.is_file():
        raise CoverageError("Coverage worker did not produce a summary")
    result = json.loads(summary.read_text(encoding="utf-8"))
    if result.get("scope_hash") != sha256(scope_path) or result.get("harness_binary_hash") != sha256(harness_binary):
        raise CoverageError("Coverage output provenance differs from requested inputs")
    return summary


def worker() -> int:
    scope_path = Path("/scope.json")
    scope = load_scope(scope_path)
    output = Path("/output")
    corpus = Path("/corpus")
    started = time.monotonic()
    warnings: list[str] = []
    try:
        files = sorted(path for path in corpus.rglob("*") if path.is_file())
        if not files:
            raise CoverageError("Corpus is empty")
        with tempfile.TemporaryDirectory(prefix="coverage-replay-") as temp_name:
            temporary = Path(temp_name)
            profile = output / "coverage.profdata"
            for index in range(0, len(files), scope["replay_batch_size"]):
                raw = temporary / f"batch_{index:06d}.profraw"
                env = os.environ.copy()
                env["LLVM_PROFILE_FILE"] = str(raw)
                env["HBFG_METRICS_PATH"] = str(temporary / "runtime_metrics.json")
                run = subprocess.run(
                    ["/artifact/harness_binary", *(str(path) for path in files[index:index + scope["replay_batch_size"]])],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    cwd=temporary, env=env, timeout=600, check=False,
                )
                if run.returncode != 0 or not raw.is_file():
                    raise CoverageError(f"Replay batch {index // scope['replay_batch_size']} failed (exit {run.returncode}): {run.stderr[-1000:]}")
                next_profile = output / "coverage.next.profdata"
                merge_inputs = [str(profile), str(raw)] if profile.is_file() else [str(raw)]
                merge = subprocess.run(
                    ["llvm-profdata-20", "merge", "-sparse", *merge_inputs, "-o", str(next_profile)],
                    capture_output=True, text=True, check=False,
                )
                if merge.returncode != 0:
                    raise CoverageError(f"Profile merge failed: {merge.stderr[-1000:]}")
                next_profile.replace(profile)
                raw.unlink()
            objects = scope["objects"]
            profile_ids = subprocess.run(
                ["llvm-profdata-20", "show", "--binary-ids", str(profile)],
                capture_output=True, text=True, check=True,
            ).stdout.lower()
            for path in objects:
                expected_id = scope["object_build_ids"][path].lower()
                elf_notes = subprocess.run(
                    ["readelf", "-n", path], capture_output=True, text=True, check=True,
                ).stdout.lower()
                if expected_id not in profile_ids or f"build id: {expected_id}" not in elf_notes:
                    raise CoverageError(f"Coverage profile/ELF Build ID mismatch: {path}")
            export = subprocess.run(
                ["llvm-cov-20", "export", "--summary-only", objects[0],
                 *(part for path in objects[1:] for part in ("-object", path)),
                 f"-instr-profile={profile}"],
                capture_output=True, text=True, check=False,
            )
            warnings = [line for line in export.stderr.splitlines() if line.strip()]
            if export.returncode != 0:
                raise CoverageError(f"Coverage export failed: {export.stderr[-1000:]}")
            data = json.loads(export.stdout)
            matching = [item for group in data["data"] for item in group["files"]
                        if item["filename"].startswith(scope["source_prefix"])]
            if not matching:
                raise CoverageError("No files in frozen source scope were found")
            if len({item["filename"] for item in matching}) != len(matching):
                raise CoverageError("Coverage export repeats a source file; cannot sum safely")
            measures = {}
            for kind in ("lines", "branches"):
                total = sum(item["summary"][kind]["count"] for item in matching)
                covered = sum(item["summary"][kind]["covered"] for item in matching)
                measures[kind] = {"covered": covered, "total": total,
                                  "percent": (100.0 * covered / total) if total else None}
            summary = {
                "record_format_version": "1.0",
                "scope_hash": sha256(scope_path),
                "pytorch_commit": scope["pytorch_commit"],
                "coverage_image": scope["coverage_image"],
                "source_prefix": scope["source_prefix"],
                "harness_binary_hash": sha256(Path("/artifact/harness_binary")),
                "corpus_file_count": len(files),
                "source_file_count": len(matching),
                "measurements": measures,
                "quality_status": "partial_warning" if warnings else "complete",
                "profile_hash": sha256(profile),
                "warnings": warnings,
                "replay_seconds": round(time.monotonic() - started, 3),
            }
            (output / "coverage_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({"status": "present", "corpus_file_count": len(files), "warnings": len(warnings)}))
        return 0
    except (CoverageError, OSError, KeyError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"coverage replay error: {exc}", file=sys.stderr)
        return 1
    finally:
        uid, gid = int(os.environ.get("HOST_UID", "0")), int(os.environ.get("HOST_GID", "0"))
        for path in output.rglob("*"):
            os.chown(path, uid, gid)
        os.chown(output, uid, gid)


if __name__ == "__main__":
    if sys.argv[1:] == ["--worker"]:
        raise SystemExit(worker())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", type=Path, required=True)
    parser.add_argument("--corpus-manifest", type=Path, required=True)
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--harness-binary", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = replay(
            scope_path=args.scope,
            corpus_manifest=json.loads(args.corpus_manifest.read_text(encoding="utf-8")),
            corpus_dir=args.corpus_dir,
            harness_binary=args.harness_binary,
            output_dir=args.output_dir,
        )
    except (CoverageError, OSError, ValueError, KeyError) as exc:
        raise SystemExit(str(exc)) from exc
    print(result)
