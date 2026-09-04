#!/usr/bin/env python3
"""Verify and rehearse the FlashFuzz PyTorch 2.2 checkpoint safely."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

CHECKPOINT_ROOT = Path(__file__).resolve().parents[1]

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def run(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        args, cwd=cwd, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return result.stdout

def verify_checkpoint_hashes() -> None:
    sums_path = CHECKPOINT_ROOT / "SHA256SUMS"
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split("  ", 1)
        target = CHECKPOINT_ROOT / relative
        actual = sha256(target)
        if actual != expected:
            raise RuntimeError(
                f"checkpoint hash mismatch for {relative}: {actual} != {expected}"
            )

def copy_overlay(destination: Path) -> None:
    overlay_root = CHECKPOINT_ROOT / "overlay"
    for source in overlay_root.rglob("*"):
        if not source.is_file():
            continue
        relative = source.relative_to(overlay_root)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

def validate_recovery_files(destination: Path, manifest: dict) -> None:
    for record in manifest["recovery_files"]:
        target = destination / record["path"]
        if not target.is_file():
            raise RuntimeError(f"missing restored file: {record['path']}")
        actual = sha256(target)
        if actual != record["sha256"]:
            raise RuntimeError(
                f"restored hash mismatch for {record['path']}: "
                f"{actual} != {record['sha256']}"
            )
        if target.suffix == ".py":
            ast.parse(target.read_text(encoding="utf-8"), filename=str(target))

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--flashfuzz-repo", type=Path, required=True,
        help="Existing local FlashFuzz repository used only as a Git object source.",
    )
    args = parser.parse_args()
    source_repo = args.flashfuzz_repo.resolve()
    if not (source_repo / ".git").exists():
        raise SystemExit(f"not a Git repository: {source_repo}")
    manifest = json.loads(
        (CHECKPOINT_ROOT / "manifest.json").read_text(encoding="utf-8")
    )
    base_commit = manifest["source"]["flashfuzz_base_commit"]
    run("git", "cat-file", "-e", f"{base_commit}^{{commit}}", cwd=source_repo)
    verify_checkpoint_hashes()
    with tempfile.TemporaryDirectory(prefix="flashfuzz-2.2-restore-") as tmp:
        restored = Path(tmp) / "FlashFuzz"
        run(
            "git", "clone", "--quiet", "--no-hardlinks",
            str(source_repo), str(restored),
        )
        run("git", "checkout", "--quiet", base_commit, cwd=restored)
        patch = CHECKPOINT_ROOT / "patch" / "tracked_changes.patch"
        run("git", "apply", "--check", str(patch), cwd=restored)
        run("git", "apply", str(patch), cwd=restored)
        copy_overlay(restored)
        validate_recovery_files(restored, manifest)
        status = run(
            "git", "status", "--porcelain=v1", "--untracked-files=all",
            cwd=restored,
        ).splitlines()
        modified = sum(1 for line in status if line.startswith(" M"))
        untracked = sum(1 for line in status if line.startswith("??"))
        expected = manifest["recovery_status"]
        if modified != expected["tracked_modified_count"]:
            raise RuntimeError(
                f"restored modified count {modified} != "
                f"{expected['tracked_modified_count']}"
            )
        if untracked != expected["required_untracked_count"]:
            raise RuntimeError(
                f"restored untracked count {untracked} != "
                f"{expected['required_untracked_count']}"
            )
    print(json.dumps({
        "status": "ok",
        "base_commit": base_commit,
        "verified_recovery_files": len(manifest["recovery_files"]),
        "source_submodule_modified": False,
    }, indent=2))

if __name__ == "__main__":
    main()
