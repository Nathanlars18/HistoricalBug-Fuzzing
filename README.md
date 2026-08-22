# HistoricalBug-Fuzzing

HistoricalBug-Fuzzing studies how historical deep-learning framework bugs can
improve fuzzing harness generation. It structures historical PyTorch bug
reports, extracts reusable bug patterns and knowledge, injects that information
into prompts, and evaluates the resulting harnesses against a coverage
baseline.

This repository is not a FlashFuzz fork. FlashFuzz is an external execution
dependency and will be added under `third_party/FlashFuzz`; its original source
is not maintained as part of this research artifact.

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
- `results/`: raw and processed experimental results.
- `analysis/`: RQ-oriented evidence, tables, figures, mappings, and diffs.
- `research_notes/archive/baseline_experiments/`: early EXP001-EXP004 exploration
  and reproduction notes.
- `scripts/`: repository-level utilities that are not owned by a single
  experiment.
- `third_party/`: location reserved for external execution dependencies.

## Current migration status

The lightweight research assets for EXP005-EXP010 have been migrated. EXP006
currently contains 39 structured bug reports, 39 bug patterns, and 39 knowledge
items. EXP007-EXP009 retain their final harnesses, prompts, experiment-specific
scripts, and lightweight results. EXP010 aggregates the pilot analysis.

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

See `experiment/registry.yaml` for outputs and dependencies.

## Data flow

```text
raw issue/report
  -> EXP006 structured bug report
  -> bug pattern
  -> knowledge base
  -> EXP007 / EXP008 / EXP009 harness generation
  -> EXP010 analysis
```

`dataset/` is the raw-source and interim-selection workspace. Canonical
processed historical bug information belongs to EXP006.

## Next steps

- Expand EXP006 to 30-50 PyTorch historical bugs.
- Extend evaluation from the current `torch.matmul` pilot to multiple APIs.
- Run multiple controlled trials and reconcile legacy coverage definitions.
- Add the FlashFuzz execution dependency under `third_party/FlashFuzz`.
- Improve traceability from historical issue through knowledge and harness
  behavior to final analysis evidence.
