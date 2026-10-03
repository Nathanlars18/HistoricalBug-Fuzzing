# EXP006: Historical Bug Information Database

EXP006 is the canonical Historical Bug Information Database. It owns the
processed historical bug reports, API-specific patterns, API-specific knowledge,
schemas, validation examples, quality reviews, and transformation scripts.

Its data flow is:

```text
raw issue/report -> structured bug report -> bug pattern -> knowledge base
```

Previously active Report/Pattern/Knowledge records were moved byte-for-byte to
`dataset/legacy/pre_report_v3_20260928/original_layout/` with their old sources.
Existing EXP006 `legacy/` trees were not moved. Historical outputs are not the
active v4 input pool; see the archive README for path-resolution limitations.
Pattern schema `3.0` (contract/mapping currently `3.3`) uses evidence-linked
Chen root causes, symptom arrays, and historical trigger conditions; it removes
the mixed primary/secondary defect classes and forced implementation-layer enum.
See `schemas/pattern_schema.md` for the source citation and classification rules.

New Pattern outputs default to `bug_patterns/v3/<api>/`. Knowledge schema remains
`2.1`, while its contract/mapping `2.2` consumes Pattern `3.0` and writes to
`knowledge_base/pattern_v3/<api>/`. No existing classifications or hashes are
migrated automatically. New Pattern IDs include `_v3_`; Knowledge IDs include
`_pv3_` to avoid collisions with legacy records. EXP011-014 input wiring must be reviewed before consuming
these new outputs. Report v5 consumes admitted Issue Inventory entries and
immutable captures. Its active Builder is offline and deterministic: it
resolves only explicit source locators, creates Evidence IDs, and leaves
unavailable facts unresolved. It does not call an LLM or force a primary API.
Report v2-v4 contracts and the v4 assisted Builder are frozen under
`schemas/legacy/` and `scripts/legacy/`; no legacy record is relabelled in
place. Pattern compatibility with v5 is reviewed explicitly at the
Report-to-Pattern boundary. See `schemas/source_to_report_mapping.md` for the
active mapping.

Report and Pattern `--dry-run` are offline checks with no model calls or writes.
Knowledge `--dry-run` still calls the LLM and only suppresses output writes.

Offline regression checks (no model or Docker calls):

```bash
python3 -B -m unittest discover -s experiment/EXP006_historical_bug_pattern_dataset/tests
```

EXP006 ends at API-specific Knowledge. HarnessSpec synthesis and executable
strategy design belong to EXP011.

The repository-level `dataset/` directory is only the raw source and interim
selection workspace; it does not contain this canonical processed database.

`legacy/README_legacy.md` preserves the original EXP006 documentation from FlashFuzz.
