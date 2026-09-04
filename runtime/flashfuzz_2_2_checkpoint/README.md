# FlashFuzz / PyTorch 2.2 Recovery Checkpoint

This directory preserves the minimal project-owned state required to recreate
the FlashFuzz PyTorch 2.2 experiment runtime without committing generated
corpora, binaries, coverage data, or large logs.

## Pinned base

- FlashFuzz commit: `c1c752963596528e4752360cdaeac77a80f7e07d`
- PyTorch tag: `v2.2.0`
- PyTorch commit: `8ac9b20d4b090c213799e81acf48a55ea8d437d6`
- Recorded runtime version: `2.2.0a0+git8ac9b20`

## Directory roles

- `patch/tracked_changes.patch`: reviewable Git diff for the 13 modified files.
- `overlay/`: exact final bytes for those 13 files plus the required untracked
  `scripts/copy.py` runtime extension.
- `manifest.json`: machine-readable provenance and recovery-file inventory.
- `SHA256SUMS`: integrity hashes for all checkpoint files except itself.
- `environment.json`: recorded framework, compiler, Docker, OS, and hardware
  evidence.
- `evidence/`: source Dockerfiles, untracked-file inventory, ignored-artifact
  summary, manual-fix note, and deduplicated crash inputs.
- `tools/verify_restore.py`: restores into a temporary clone and validates hashes;
  it never changes the source submodule.

## Verification

From the HistoricalBug-Fuzzing repository root:

```bash
python3 runtime/flashfuzz_2_2_checkpoint/tools/verify_restore.py \
  --flashfuzz-repo third_party/FlashFuzz
```

The verifier checks checkpoint integrity, checks out the pinned FlashFuzz base
in a temporary directory, applies the patch, overlays the exact files, and
compares every recovery-file hash with `manifest.json`.

## Deliberately excluded from Git

- generated per-API Helper copies and symlinks;
- fuzzing binaries and seed corpora;
- `.profraw`, HTML coverage output, and large execution logs;
- editor swap files;
- a full PyTorch source checkout or Docker image export.

These items are either reproducible from the pinned inputs or unsuitable for
Git. Small unique crash inputs are retained under `evidence/crash_inputs/`.
