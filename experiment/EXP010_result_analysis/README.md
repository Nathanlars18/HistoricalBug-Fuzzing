# EXP010: Result Analysis and Comparison

EXP010 is the result analysis and comparison experiment. It aggregates the
migrated results from EXP007, EXP008, and EXP009; it does not generate a new
fuzzing harness.

The analysis compares baseline, single-pattern, multi-pattern, and reasoning
harnesses through coverage comparison, harness diffs, pattern-to-harness
mapping, and knowledge traceability. The resulting evidence supports RQ1 and
RQ2.

The current `torch.matmul` results are a pilot study. Validation across multiple
APIs and multiple trials is still required. Legacy documents also use coverage
figures whose measurement scope and denominator require reconciliation before
they are treated as directly comparable final results.

Analysis evidence is stored under `analysis/`, with source tables in
`analysis/tables/`, figures in `analysis/figures/`, and RQ1 evidence and diffs
under `analysis/RQ1_pattern_effectiveness/`. Experiment-specific analysis
scripts are retained in this directory under `scripts/`.
