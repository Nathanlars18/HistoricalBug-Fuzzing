# Superseded HarnessSpec Archive at Contract v2.5

This archive separates the final reviewed HarnessSpecs from failed generation
diagnostics and earlier immutable revisions as of 2026-10-06.

## Active revisions

Only these exact revisions are admitted as HarnessSpec inputs for the next
Strategy review:

- `torch.batch_norm_update_stats` controlled Baseline r4;
- `torch.batch_norm_update_stats` bug-aware Static r6;
- `torch.nn.functional.cosine_embedding_loss` controlled Baseline r3;
- `torch.nn.functional.cosine_embedding_loss` bug-aware Static r4.

Each has an external `approved` review record under `harness_spec_reviews/`.

## Retention policy

Failed generation diagnostics were moved physically under
`failed_diagnostics/`; they are not valid HarnessSpecs and were not referenced
by another artifact.

Successful superseded revisions remain at their original immutable paths and
are indexed by `lineage_manifest.json`. This is intentional: review records and
generation traces store exact repository-relative paths, while child revisions
store their predecessor hashes. Moving or rewriting those issued records would
break the audit chain. They are archived logically and must not be selected as
new Strategy inputs.

No HarnessSpec, review record, generation trace, or content hash was rewritten
during archival.
