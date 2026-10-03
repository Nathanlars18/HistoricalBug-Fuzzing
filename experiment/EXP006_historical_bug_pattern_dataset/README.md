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
Pattern schema/contract/mapping `4.0` uses evidence-linked historical condition
statements and optional Chen root-cause and symptom labels. It removes the mixed
primary/secondary defect classes, cross-API scope, custom trigger dimensions,
forced implementation layer, historical-oracle kind, and aggregate confidence.
See `schemas/pattern_schema.md` for the source citation and classification rules.

New Pattern outputs default to `bug_patterns/v4/<api>/`. Knowledge schema
`3.0` and contract/mapping `3.1` consume Pattern `4.0` and write to
`knowledge_base/v3/<api>/`. Knowledge v3 stores a same-API learned hypothesis,
historical anchors, variation opportunities, and observation candidates. It
does not contain operational risk-dimension tags or executable planning. A
Pattern may produce no Knowledge when evidence cannot support a useful
abstraction. No existing classifications or hashes are migrated automatically.
New Pattern IDs include `_v4_`; Knowledge IDs include `_pv4_` to avoid
collisions with legacy records. The current EXP011 reader still accepts only
Knowledge 2.1; it must be deliberately updated before consuming Knowledge 3.0.
Report v5 consumes admitted Issue Inventory entries and
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
Patterns and Knowledge selected for experiments require the lightweight reviews
in `quality/pattern_review_protocol.md` and
`quality/knowledge_review_protocol.md`; exploratory collections may use a
predeclared stratified sample, which does not approve unsampled records.

Offline regression checks (no model or Docker calls):

```bash
python3 -B -m unittest discover -s experiment/EXP006_historical_bug_pattern_dataset/tests
```

EXP006 ends at API-specific Knowledge. HarnessSpec synthesis and executable
strategy design belong to EXP011.

The repository-level `dataset/` directory is only the raw source and interim
selection workspace; it does not contain this canonical processed database.

`legacy/README_legacy.md` preserves the original EXP006 documentation from FlashFuzz.
