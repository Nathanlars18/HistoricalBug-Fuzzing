# EXP006: Historical Bug Information Database

EXP006 is the canonical Historical Bug Information Database. It owns the
processed historical bug reports, extracted patterns, generated knowledge,
schemas, validation examples, quality reviews, and transformation scripts.

Its data flow is:

```text
raw issue/report -> structured bug report -> bug pattern -> knowledge base
```

The current database contains 39 structured bug reports, 39 bug patterns, and
39 knowledge items. The next 30-50 PyTorch historical bugs will continue to be
added under this directory.

The repository-level `dataset/` directory is only the raw source and interim
selection workspace; it does not contain this canonical processed database.

`README_legacy.md` preserves the original EXP006 documentation from FlashFuzz.
