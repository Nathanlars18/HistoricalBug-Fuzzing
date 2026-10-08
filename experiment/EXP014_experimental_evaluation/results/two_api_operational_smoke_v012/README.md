# Two-API operational checkpoint, 2026-10-08

This is an execution-interface checkpoint, not a formal effectiveness study.
The final-cutoff report is [analysis/eca55e59c3bea0dd/summary.md](analysis/eca55e59c3bea0dd/summary.md).
Machine-readable records and CSV tables are authoritative.

## Verified in this checkpoint

- Two executable C++ targets, three groups, one independent repeat, three
  requested 15-second rounds per group: all 18 tasks completed with valid
  Round records; no task attrition.
- All 18 round Coverage summaries were available. All carried the LLVM
  `7 functions have mismatched data` warning, with no partial replay failures.
- All 18 prefix profile-union computations completed. The source warnings
  remain explicit in their cumulative summaries.
- Four real feedback decisions were eligible and retained the current budget
  (`no_eligible_recipient`); the real run did not trigger materialization.
- Separate `feedback_interface_smoke_v007` synthetic acceptance and rejection
  paths passed. This is interface evidence, not observed adaptive benefit.
- 58,935 capture attempts produced 768 retained candidates and zero capture
  write failures; 58,167 attempts were suppressed by first-N storage limits.
  The candidates await Case intake, replay and human attribution. They are
  not confirmed PyTorch defects or exhaustive anomaly-yield observations.
- Requested fuzzing budget was 270 seconds; measured fuzzer process time was
  329.1039573699891 seconds. Report both rather than claiming an exact
  270-second process runtime. Coverage replay and merging are separate work.
- The fixed analysis window is final; this does not mean crash triage is
  complete. `torch.compile` remains outside the executable sample.

## Published evidence and local retention

`checkpoint_manifest.json` lists 207 byte-preserving evidence copies and their
SHA-256 hashes. The copy location is `evidence/<source_relative_path>`; issued
references inside each record intentionally retain their original paths.
The package contains round records, runtime snapshots, budget/process records,
capture summaries/bundles, corpus manifests, Coverage summaries and union
inputs, four feedback decisions, four compiled Harness source/metadata pairs,
the execution index and provenance, and the separate synthetic fixture result.

This is a partial evidence snapshot. Profile and binary hashes remain in the
metadata, but binaries, `.profdata`, corpus bytes, candidate input bytes, full
logs and working-tree captures remain in the original local run directories.
They were not deleted, and this Git package is not a standalone replay bundle.
Do not treat missing uploaded raw evidence as zero events or completed triage.

Frozen matrix versions are audit snapshots, not automatically reusable with
future edits. A new experiment must freeze a new matrix and use a new run root;
do not update old hashes to make historical runs match newer source.
