# Dataset Scripts

These scripts were migrated from the read-only FlashFuzz research repository
for dataset construction and selection. Generated caches and build artifacts are
not included.

- `selection/` contains the DLFrameBRCode PyTorch filtering, LLM selection,
  review-column, merge, and export utilities.
- `legacy/report_builders_v1/` preserves the superseded DLFrameBRCode and
  GitHub-Issue-to-v1-Report generators. They are retained for traceability and
  must not be used to produce current EXP006 records.
- `experiment/EXP006_historical_bug_pattern_dataset/scripts/` owns the active
  transformations for the canonical historical-bug information database. A
  v2 Report Builder will be added there only after the Report schema and source
  mapping are finalized.

The scripts operate on the data flow documented in `dataset/README.md`. Review
paths and runtime configuration before executing them in this repository.
