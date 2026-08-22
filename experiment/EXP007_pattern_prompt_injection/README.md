# EXP007: Single-Pattern Prompt Injection

EXP007 is a single historical bug pattern prompt injection experiment. The
target API is `torch.matmul`.

The experiment compares a baseline harness with a single-pattern enhanced
harness. Its input depends on the EXP006 Historical Bug Information Database at
`experiment/EXP006_historical_bug_pattern_dataset/`, and its results provide
pilot evidence for RQ1 and RQ2.

Experiment-specific generation and coverage scripts are under `scripts/`, and
the final baseline and single-pattern harnesses are under `harnesses/`. Raw and
processed results are stored in `results/raw/EXP007/` and
`results/processed/EXP007/`. Analysis files are stored in
`analysis/RQ1_pattern_effectiveness/EXP007/`.

Large corpora and fuzzing binaries are intentionally not migrated. This
repository retains the final harnesses and coverage data needed for analysis.

See `README_legacy.md` for the original experiment documentation and
`config.yaml` for the migrated experiment configuration.
