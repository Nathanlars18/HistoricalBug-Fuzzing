# Golden Case: `torch.matmul` and PyTorch Issue #71774

## Purpose

This package demonstrates one complete, reviewable path from historical evidence to executable feedback. It compares the same API and runtime under:

- `structured_baseline`: API Profile and the common Helper set, without historical Knowledge;
- `bug_aware_static`: the same environment plus the Knowledge derived from PyTorch Issue #71774.

It is a development smoke case: one repeat, three five-second rounds per group. It establishes end-to-end executability and observability, not statistical effectiveness.

## Historical claim and transformation

The local Issue record reports nondeterministic output for CPU `torch.matmul` with `torch.long` inputs and a zero contraction dimension. The mainline records are:

1. Bug Report: `br_pytorch_github_71774` revision 3;
2. Atomic Pattern: `pt_zero_inner_dimension_long_matmul_nondeterministic_output_p001`;
3. Specific Knowledge: `kn_pt_torch_matmul_empty_inner_dimension_long_dtype_determinism_k001`;
4. HarnessSpec: selects that Knowledge, while rejecting or deferring the other three `torch.matmul` Knowledge records for explicit backend or capability reasons;
5. Strategy Plan: materializes two CPU int64 tensors with shapes `(m, 0)` and `(0, n)` and two identical `at::matmul` invocations;
6. C++ Harness: evaluates four activation predicates before the calls and compares the two outputs with `torch::equal`.

The baseline constructs compatible nonempty tensors and performs one call. It contains the same evaluation-target instrumentation so that absence of the Issue-derived state is measurable rather than assumed.

## Verified smoke outcome

| Group | Started iterations | Issue target activated | Determinism Oracle evaluated | Oracle failures |
|---|---:|---:|---:|---:|
| Structured Baseline | 32,458 | 0 | not applicable | 0 |
| Bug-aware Static | 50,494 | 26,366 | 26,366 | 0 |

For Static, the knowledge branch entered 7,785, 10,157, and 8,424 times across the three rounds. Each of the four required properties was checked and true on every one of those branch executions. Both target calls completed and the determinism Oracle passed each time.

Therefore, this evidence supports the claim that Issue #71774 Knowledge was converted into executable, observable behavior. It does **not** show a new PyTorch 2.10 bug: no repeated-output mismatch was observed, and this short run is not an effectiveness comparison.

## Evidence layout

`evidence_manifest.json` is the exact allowlist. It records SHA-256 hashes for the source Report/Pattern/Knowledge, both HarnessSpecs and Strategy Plans, generated C++ files, structured compile evidence, six short fuzzing rounds, and analyzer outputs. `activation_summary.json` deterministically joins each Harness Artifact's `instrumentation_map.runtime_site_id` with the corresponding Runtime Snapshot `site_counts`.

Successful compilation produced no diagnostic text, so `command.json`, `process_result.json`, `builder_result.json`, and `harness_artifact.json.compile_check` jointly form the compile evidence; an empty `stderr.log` is expected.

Generated binaries, corpora, `.profraw` files, the Adaptive group, obsolete failed attempts, and raw dirty-working-tree snapshots containing unrelated repository state are intentionally excluded. `generation_provenance.json` preserves the commit, dirty-state declaration, and hashes of those local snapshots without publishing their unrelated contents.

## Helper-set provenance repair

The frozen smoke matrix records a run-local Helper build summary in its `helper_profile_set` binding, and the historical Runner validated but did not pass that binding to the HarnessSpec Builder. The produced HarnessSpecs are nevertheless explicit: they reference twelve approved r002 Helper Profiles. The formal matrix revision 7 now points to `helper_profile_set__pytorch_2_10_cpu__v001.json`, and the Runner passes that exact manifest to the Builder. The evidence package preserves both the historical binding and the post-run repair; it does not rewrite the completed smoke matrix.

## Reproducibility boundary

The current smoke artifacts record a dirty working tree and are suitable for a transparent development checkpoint. Before reporting paper-level results, rerun this case from a clean committed revision with the frozen formal matrix and the planned longer budget. Do not reinterpret these development counts as final experimental measurements.
