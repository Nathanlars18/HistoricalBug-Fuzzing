# Report source calibration — 2026-09-28

The directory name predates the active Report v5 contract and is retained so
frozen inventory locators remain stable. It does not identify the schema of
newly generated Reports.

Three purposively selected historical cases for testing source preservation and
extraction boundaries, not an experiment cohort or a statistically representative
sample. No reproducer, fuzzer, or paid LLM was run for this calibration capture.

## Frozen discovery sources

- [BugsInDLLs](https://github.com/ncsu-swat/bugsindlls/tree/3651d10efe415a3da509f3d3c6fd860e19100582):
  `bug_dataset_pytorch.csv`, CSV record 2 is the header (record 1 is metadata).
- [Benchmarking-DL-Fuzzers](https://github.com/dmc1778/Benchmarking-DL-Fuzzers/tree/265ddb8f29fe018c94c01a52ce3871ee37da7bd2):
  `data/torch_groundtruth.csv`, CSV record 1 is the header.

The complete table bytes and immutable commit/content metadata are in `datasets/`.
Each `dataset_origin.json` retains the matching CSV record number(s), headers,
and original values. These are attributed dataset annotations, not source claims.
Downloaded bytes were checked against the upstream Git blob ID; capture receipts
add SHA-256, source URL, timestamp and response metadata. No whole repository was
cloned, and downloaded code was not executed.

## Cases and calibration purposes

| Issue | Dataset | Source-supported context | What to check |
|---|---|---|---|
| [120803](https://github.com/pytorch/pytorch/issues/120803) | BugsInDLLs | Empty `[0,0]` input to `torch.batch_norm_update_stats`; floating-point exception reported | Preserve input and error text; do not infer a confirmed root cause or fix from headings/closure |
| [112732](https://github.com/pytorch/pytorch/issues/112732) | BugsInDLLs | `torch.nn.functional.cosine_embedding_loss` crashes; body emphasizes empty/mixed-dtype tensors, later comment points to mismatched shapes | Preserve separate attributed explanations and distinguish deprecation warning from crash |
| [100343](https://github.com/pytorch/pytorch/issues/100343) | Benchmarking-DL-Fuzzers | Out-of-bounds indexing under `torch.compile`, with `torch.sum` in the reproducer | Do not equate a dataset's `torch.sum` label with confirmed root attribution; preserve correction from “fixed” to “CUDA only” |

All three have native Issue JSON and complete available Issue comment arrays:
1, 3, and 9 comments respectively; the captured count matches Issue metadata.
PR 120882 and 112782 and their file lists were captured because they explicitly
reference the corresponding Issues. Both captured PR records have `merged=false`.
A closed Issue/PR or dataset PR link is not proof that a fix landed. A later fix
claim needs identified commit/landing evidence. For 100343, no full landing chain
was captured; comments are statements, not independent verification of a fix.
PR discussions, linked issues, and other externally referenced resources were not
recursively collected. Their absence must not be described as complete fix evidence.

Case 100343 is a compiler-path calibration case, not a commitment to include it
in the current eager C++/CPU experiment. Current-experiment feasibility remains
separate from historical-case admission. This does not select three pilot APIs.

## Active deterministic result

The admitted inventory entries generate Report v5 revisions under
`experiment/EXP006_historical_bug_pattern_dataset/bug_reports/v5/`. Report
construction is offline and made **zero LLM calls**. Admission locators provide
the affected API, trigger/operation context, and observed failure; captured
Issue, comment, PR, commit, and patch text is additionally indexed as neutral
Evidence without being promoted to a semantic Report claim.

The active latest revisions are validation-passed and remain `not_reviewed`
under the sampled quality-assurance policy. Earlier revisions are retained in
their append-only chains. A missing diagnosis, historical oracle, or confirmed
fix remains explicitly unresolved for Pattern interpretation rather than being
filled by the Report Builder.
