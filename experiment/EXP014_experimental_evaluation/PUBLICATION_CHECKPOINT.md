# Strategy-to-execution publication checkpoint

This checkpoint includes the reviewed Strategy/Primitive contracts,
deterministic Harness materialization and instrumentation, feedback controls,
Crash Case semantics/replay interfaces, execution/resume handling, Coverage
replay/union analysis, and their tests. Uncommitted API Profile/HarnessSpec
compatibility dependencies are included so the published stack is coherent.
It does not include unrelated EXP006 report extractions, presentations or
research manuscripts from the working tree.

## Validation on 2026-10-08

- EXP011 unit/regression suite: 138 passed.
- EXP012 suite: 21 passed.
- EXP013 suite: 8 passed.
- EXP014 suite: 38 passed.
- Total: 205 tests passed, without LLM calls or new fuzzing rounds.
- The two-API v012 short operational run completed 18/18 tasks; its final
  analysis and evidence-retention boundaries are documented in
  [results/two_api_operational_smoke_v012/README.md](results/two_api_operational_smoke_v012/README.md).

This evidence establishes the tested short-run interfaces. It is not proof of
bug-finding effectiveness, arbitrary API support, or absence of hidden defects.
LLVM warnings, sampling limitations and unfinished crash attribution remain
visible rather than silently normalized away.

## Archive boundaries

- EXP011 `legacy/strategy_stack_pre_v1_2/scripts/`: two unreferenced `.orig`
  snapshots physically moved, with original SHA-256 hashes preserved.
- EXP011 `legacy/superseded_strategy_plans_pre_smoke_v012/`: nine old Plans
  and two Catalog snapshots logically archived, preserving issued paths.
- EXP011 `legacy/superseded_harness_specs_v2_5/`: existing Spec lineage archive.
- EXP014 `legacy/pre_v012_operational_smoke/`: 29 earlier generated
  configurations and six earlier run indexes logically archived.

No frozen matrix, approved input, successful run record or evidence hash was
rewritten during archival. Large raw run evidence remains local and is ignored
by Git; the published checkpoint contains bounded byte-preserving metadata.

## Next: small-scale experiment preparation

Prepare and review public Issues using the existing Issue-to-Report-to-Pattern-
to-Knowledge source/evidence rules. Freeze admission/exclusion criteria and
separate executable target admission from historical Issue relevance; record
unsupported bindings explicitly. Then review API/Helper Profiles, synthesize
and review Specs/Strategies, validate Harnesses and freeze a NEW small-scale
matrix with its APIs, groups, budgets, independent repeats, seeds and analysis
rules before executing. Keep operational smoke and synthetic fixtures out of
formal effectiveness tables.

Pending candidates from this checkpoint can be triaged separately. If precise
native Coverage is promoted to a formal metric, investigate the LLVM profile
warnings first; while warnings remain, retain Coverage as qualified diagnostic
evidence. Do not adjust test domains or budgets merely to improve the pilot
checkpoint results.
