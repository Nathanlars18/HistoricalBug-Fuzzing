# EXP008: Multi-Pattern Prompt Injection

EXP008 is a multi historical bug pattern prompt injection experiment targeting
`torch.matmul`. It injects multiple historical bug patterns from the EXP006
Historical Bug Information Database into the harness-generation prompt.

The experiment provides pilot evidence for RQ1 and RQ2. Experiment-specific
scripts and prompts are stored under `scripts/` and `prompts/`, and the
canonical final harness is under `harnesses/multi_pattern/`. Raw and processed
results are stored in `results/raw/EXP008/` and `results/processed/EXP008/`;
analysis files are under `analysis/RQ1_pattern_effectiveness/EXP008/`.

The EXP008 source baseline harness was byte-identical to the canonical
multi-pattern harness, so it is not retained as an independent baseline.
Baseline results should be traced to EXP005, EXP007, or the explicit comparison
files, as appropriate.

Large corpora, fuzzing binaries, generated build and coverage artifacts, raw
runtime logs, and duplicate FlashFuzz helpers are intentionally not migrated.
See `README_legacy.md` for the original experiment documentation.
