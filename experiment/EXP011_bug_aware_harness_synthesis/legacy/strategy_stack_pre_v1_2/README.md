# Strategy stack before Plan v1.2

This logical archive records the Strategy implementation that preceded the
HarnessSpec v2.2 alignment performed on 2026-10-06.

The tracked baseline is recoverable from Git commit
`9693c72e24ff2d66a2f0ef89fddeba7533c2020b`. The two pre-upgrade script
snapshots already retained by the project are:

- `scripts/build_strategy_plan_json.py.orig` in this archive, SHA-256
  `b4c6dd2926d0fd808ca8c7d750af02b9161b827caa8379c8f954ba16f3654736`;
- `scripts/build_harness_artifact.py.orig` in this archive, SHA-256
  `8e1ed23dc5a687b65f628f37fa084bc7f0a39505d36cf37fc1e94a0a7b1e1fa4`.

The pre-upgrade stack used Strategy Plan Schema 1.1, Contract 1.5, Rules 1.2,
and Primitive Catalog 3. It expected the legacy HarnessSpec vocabulary
`branch_precondition`, `target_property`, `activation_target`, and
`oracle_requirement`, so it is not eligible to consume approved HarnessSpec
v2.2 records.

Before replacement, the working-tree documentation also contained two narrow
clarifications not present in the Git baseline: `expected_valid` superseded the
legacy `boundary_valid` spelling, and root-cause/symptom labels were explicitly
not Primitive-selection proof. Both meanings are preserved in the v1.2/v1.3
successor documents.

This directory is provenance only. Do not use the archived stack for new Plan
generation or formal experiments.

On 2026-10-08 both unreferenced `.orig` snapshots were moved from the active
project `scripts/` directory into this archive's `scripts/` directory. Their
bytes and the SHA-256 values above were preserved; issued Plans, reviews,
Catalog snapshots and frozen runtime references were not moved or rewritten.
