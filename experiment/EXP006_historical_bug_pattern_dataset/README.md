# EXP006: Historical Bug Pattern Dataset Construction

EXP006 constructs a historical bug pattern dataset for research on reusable
fuzzing knowledge.

The canonical dataset is stored at:

`dataset/processed/historical_bug_patterns_v1/`

Its data flow is:

```text
bug report -> bug pattern -> knowledge base
```

The current dataset contains 39 structured bug reports, 39 bug patterns, and
39 knowledge items. Future work will expand coverage to 30-50 PyTorch
historical bugs.

`README_legacy.md` preserves the original EXP006 documentation from FlashFuzz.
