# Dataset Scripts

These scripts were migrated from the read-only FlashFuzz research repository
for dataset construction and selection. Generated caches and build artifacts are
not included.

- `selection/` contains the DLFrameBRCode PyTorch filtering, LLM selection,
  review-column, merge, export, and structured-report generation utilities.
- `pattern_knowledge_generation/` contains the EXP006 batch and per-item tools
  used to transform structured bug reports into bug patterns and knowledge-base
  items.

The scripts operate on the data flow documented in `dataset/README.md`. Review
paths and runtime configuration before executing them in this repository.
