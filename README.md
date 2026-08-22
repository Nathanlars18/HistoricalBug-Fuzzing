# HistoricalBug-Fuzzing

This repository contains research artifacts for Historical Bug Pattern Enhanced Harness Generation for deep learning framework fuzzing.

This is not a FlashFuzz fork. FlashFuzz is used as the fuzzing and harness execution backend through `third_party/FlashFuzz`.

## Research Pipeline

Raw historical bug report
→ structured bug report
→ bug pattern
→ knowledge base
→ harness generation
→ fuzzing evaluation

## Main Components

- `dataset/`: historical bug reports, bug patterns, and knowledge base
- `experiment/`: experiment definitions and harnesses
- `scripts/`: dataset construction, harness generation, coverage, and analysis scripts
- `results/`: raw and processed experiment outputs
- `analysis/`: RQ-oriented analysis and paper evidence
- `third_party/`: external execution dependencies such as FlashFuzz
