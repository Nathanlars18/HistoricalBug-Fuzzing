# EXP007: Single-Pattern Prompt Injection

EXP007 is a pilot experiment for injecting a single historical bug pattern into
harness-generation prompts. The target API is `torch.matmul`.

The experiment compares a baseline harness with a single-pattern enhanced
harness. Its input comes from the EXP006 historical bug pattern dataset at
`dataset/processed/historical_bug_patterns_v1/`, and its results provide pilot
evidence for RQ1 and RQ2.

Large corpora and fuzzing binaries are intentionally not migrated. This
repository retains the final harnesses and coverage data needed for analysis.

See `README_legacy.md` for the original experiment documentation and
`config.yaml` for the migrated experiment configuration.
