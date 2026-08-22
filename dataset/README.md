# Historical Bug Dataset

This directory contains the research data used to turn historical PyTorch bugs
into reusable inputs for fuzzing harness generation.

## Data flow

```text
raw historical bug reports
  -> structured bug reports
  -> bug patterns
  -> knowledge base
  -> harness generation
```

- `raw/` preserves source reports and reproduction code.
- `interim/` records dataset selection and intermediate LLM artifacts.
- `processed/historical_bug_patterns_v1/` is the canonical EXP006 dataset.
- `schemas/` documents transformations between dataset stages.
- `validation/` contains manually authored reference examples.

See `manifest.csv` for component counts and `lineage.csv` for provenance.
