# Strategy lineage archive at the v012 execution checkpoint

The `lineage_manifest.json` records nine superseded Strategy Plans and two
historical Catalog snapshots as of 2026-10-08. The four current initial Plans
are selected explicitly by `two_api_operational_smoke__v012.json`: Baseline
revision 3 and Static revision 2 for each of the two executable APIs.

This is a logical archive. Earlier issued Plans and Catalog snapshots remain
at their original paths, unchanged, because reviews, traces, predecessor
hashes and frozen experiments depend on their identity. Do not select archived
Plans simply because they still appear under `strategy_primitives/plans/`.

Two unreferenced pre-upgrade `.orig` scripts were physically moved into
`../strategy_stack_pre_v1_2/scripts/`, preserving their bytes and hashes.
Earlier HarnessSpecs remain covered by `../superseded_harness_specs_v2_5/`.
No approved Plan, Spec, review, Catalog or frozen matrix was rewritten here.
