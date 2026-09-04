# HistoricalBug-Fuzzing

HistoricalBug-Fuzzing studies how historical deep-learning framework bugs can
improve fuzzing harness generation. It structures historical PyTorch bug
reports, extracts reusable bug patterns and knowledge, injects that information
into prompts, and evaluates the resulting harnesses against a coverage
baseline.

This repository is not a FlashFuzz fork. FlashFuzz is a pinned external
execution dependency under `third_party/FlashFuzz`. Research-specific runtime
extensions are maintained separately under `runtime/`.

## Repository structure

- `dataset/`: raw issues and reports, reproduction code, selection records, and
  intermediate LLM selection responses.
- `experiment/EXP006_historical_bug_pattern_dataset/`: the canonical Historical
  Bug Information Database, including structured reports, patterns, knowledge,
  schemas, validation, and construction scripts.
- `experiment/EXP005_coverage_baseline/`: FlashFuzz coverage baseline.
- `experiment/EXP007_pattern_prompt_injection/`: single-pattern prompt
  injection pilot.
- `experiment/EXP008_matmul_multi_pattern/`: multi-pattern prompt injection
  pilot.
- `experiment/EXP009_pattern_reasoning/`: knowledge-guided pattern reasoning
  pilot.
- `experiment/EXP010_result_analysis/`: comparison and result-analysis
  definition.
- `experiment/EXP011_bug_aware_harness_synthesis/`: static synthesis from
  API-specific Knowledge to HarnessSpec, Strategy Primitives, and Harnesses.
- `results/`: raw and processed experimental results.
- `analysis/`: RQ-oriented evidence, tables, figures, mappings, and diffs.
- `research_notes/archive/baseline_experiments/`: early EXP001-EXP004 exploration
  and reproduction notes.
- `scripts/`: repository-level utilities that are not owned by a single
  experiment.
- `third_party/`: location reserved for external execution dependencies.
- `runtime/flashfuzz_2_2_checkpoint/`: versioned FlashFuzz/PyTorch 2.2 patch,
  exact overlay, recovery manifest, hashes, and environment evidence.

## Current migration status

The lightweight research assets for EXP005-EXP010 have been migrated. EXP006
preserves its previous processed records under `legacy/`; active records will be
regenerated after the revised Report schema is finalized. EXP007-EXP009 retain
their final harnesses, prompts, experiment-specific scripts, and lightweight
results. EXP010 aggregates the pilot analysis. EXP011 is in planning and schema
design; no main synthesis experiment has started.

Large corpora, fuzzing binaries, build products, profraw/profdata files, caches,
large runtime logs, and duplicate FlashFuzz helpers are intentionally excluded.
EXP001-EXP004 are archived as research notes rather than formal experiments.

## Experiment list

- EXP005: FlashFuzz coverage baseline for RQ2 and later comparisons.
- EXP006: canonical Historical Bug Information Database.
- EXP007: single-pattern prompt injection.
- EXP008: multi-pattern prompt injection.
- EXP009: pattern reasoning and knowledge-guided harness generation.
- EXP010: result analysis across baseline and enhanced harnesses.
- EXP011: static bug-aware HarnessSpec and Harness synthesis.

See `experiment/registry.yaml` for outputs and dependencies.

## Data flow

```text
raw issue/report
  -> EXP006 structured bug report
  -> bug pattern
  -> knowledge base
  -> EXP007 / EXP008 / EXP009 pilot harness generation
  -> EXP011 static bug-aware harness synthesis
  -> EXP010 analysis
```

`dataset/` is the raw-source and interim-selection workspace. Canonical
processed historical bug information belongs to EXP006.

## Next steps

- Finalize the EXP006 Report schema and regenerate active v2 records.
- Complete API and Helper Profiles for EXP011.
- Validate a version-consistent PyTorch execution environment before the main
  controlled experiments.
- Improve traceability from historical issue through knowledge, HarnessSpec,
  runtime behavior, and final analysis evidence.
