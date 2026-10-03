# Knowledge Review Protocol v1.0

## Purpose

Automatic validation proves structure, lineage, scope, and reference
consistency. This review checks the semantic abstraction introduced when an
API-specific Pattern becomes Knowledge. It does not redesign the Knowledge or
judge whether a current Harness can implement it.

## Scope

- Review every Knowledge record selected for an experiment.
- Its bound Pattern must already be approved, or the Pattern and Knowledge must
  be reviewed together before downstream use.
- For larger exploratory collections, use a predeclared stratified sample that
  covers target API, hypothesis evidence status, presence or absence of
  historical anchors, and source Pattern mechanism/evidence status.
- Freeze the sample size, random seed, and strata before inspecting model
  quality results. Sampling does not approve unreviewed records.

## Checks

Compare each Knowledge record with its exact bound Pattern:

1. The target API and Pattern identity/hash are unchanged.
2. The learned hypothesis states a bounded risk relationship rather than a
   generic testing recommendation or a complete historical reproducer.
3. A `contributing` or `unknown` historical condition has not become an
   established prerequisite, scope restriction, or proven trigger.
4. `pattern_derived` text is semantically entailed by the cited Pattern;
   interpretive extensions are marked `analyst_inferred`.
5. Historical anchors cite only material conditions marked `required`.
6. Variation opportunities preserve meaningful fuzz-derived freedom, do not
   promise a Bug, and do not invent a new historical fact.
7. Observation candidates remain non-executable questions; they do not claim a
   current API contract or silently become Harness Oracles.
8. Material uncertainty from the Pattern remains visible in the hypothesis
   rationale or limitations.
9. No concrete input construction, Strategy Primitive, instrumentation,
   branch budget, or feedback action has entered Knowledge.

## Outcomes and recording

- `approved`: the semantic abstraction is acceptable for downstream use.
- `needs_revision`: the Pattern can support Knowledge, but the current
  abstraction must be regenerated under corrected general rules.
- `rejected`: the Pattern cannot support useful Knowledge without unsupported
  speculation.

Record the outcome, Knowledge ID and canonical hash, Pattern ID and canonical
hash, reviewer identifier, review time, and concise reason in the study review
ledger. Do not edit a generated Knowledge file in place. A systematic error
requires correcting the general mapping/contract and regenerating every
affected record, rather than adding a case-specific exception.
