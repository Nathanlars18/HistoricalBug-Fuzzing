# EXP006: Historical Bug Information Database

EXP006 is the canonical Historical Bug Information Database. It owns the
processed historical bug reports, API-specific patterns, API-specific knowledge,
schemas, validation examples, quality reviews, and transformation scripts.

Its data flow is:

```text
raw issue/report -> structured bug report -> bug pattern -> knowledge base
```

Previous processed records are preserved under `legacy/`. Active Pattern and
Knowledge records will be regenerated under the v2.1 schemas after the Report
schema is finalized. New PyTorch historical bugs will continue to be added here.

EXP006 ends at API-specific Knowledge. HarnessSpec synthesis and executable
strategy design belong to EXP011.

The repository-level `dataset/` directory is only the raw source and interim
selection workspace; it does not contain this canonical processed database.

`legacy/README_legacy.md` preserves the original EXP006 documentation from FlashFuzz.
