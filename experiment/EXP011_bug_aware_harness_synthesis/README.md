# EXP011: Bug-Aware Harness Synthesis

Strategy v1.3 / Catalog v6: the current pilot regeneration, preflight and human
review sequence is in [strategy regeneration guide](strategy_primitives/regenerate_pilot_v1_3.md).
Do not overwrite existing Plan revisions or reuse approvals for new hashes.

## Purpose

EXP011 develops and validates the static synthesis pipeline that converts one or more API-specific Knowledge records into a structured HarnessSpec, then lowers the HarnessSpec into Strategy Primitives and an executable fuzzing harness.

EXP011 does not own historical Bug Reports, Patterns, or Knowledge records. Those canonical artifacts remain in EXP006.

The adaptive feedback loop is outside this experiment and will be handled separately after the static pipeline is stable.

## Planned Pipeline

```text
API Profile + available Helper Profiles
            +
API-specific Knowledge
            ↓
       HarnessSpec
            ↓
   Strategy Primitives
            ↓
          Harness
            ↓
   Build and pilot execution
```

## Directory Responsibilities

| Path | Responsibility |
|---|---|
| `schemas/` | Human-readable schemas and machine-validatable record schemas for EXP011 artifacts |
| `api_profiles/` | Structured target-API capability and constraint profiles |
| `helper_profiles/` | Structured descriptions of available helper capabilities |
| `harness_specs/` | Immutable generated HarnessSpec revisions |
| `harness_spec_reviews/` | Immutable human decisions bound to exact HarnessSpec hashes |
| `generation_artifacts/` | Hash-qualified snapshots of the Builder, active Schema pair, Contract, and Rules used for generation |
| `generation_traces/` | Immutable exact prompt/response records for every completed LLM attempt |
| `strategy_primitives/` | Lowered executable strategy descriptions |
| `scripts/` | Validation, conversion, and generation scripts |
| `harnesses/` | Generated harness source and build metadata |
| `legacy/` | Superseded design snapshots retained for traceability |

## Current Status

HarnessSpec v2.2 design and small-scale synthesis validation. No formal comparative experiment has started.

HarnessSpec v2.2 records explicit validity evidence, complete Knowledge
component-mapping decisions, frozen Schema provenance, and per-attempt
generation traces. Controlled Baselines migrate from v2.0/v2.1
deterministically without an LLM; Knowledge-bearing revisions are regenerated.
Human review is stored separately so that review never mutates the exact object
being reviewed, and repeated decisions form explicit review revisions.
An exact `needs_revision` review may drive a `manual_review` child through
`build_harness_spec_json.py --review-record`; the Builder validates its subject
hash and exposes only criterion-scoped mismatch fields to synthesis.
Contract/Rules v2.5 keep bug-aware default-branch construction entirely in the
Builder and validate the model response with a Contract-owned Schema before
cross-reference checks. Candidate errors are aggregated into one repair report;
semantic values such as property paths, observation phases, Predicates, and
Knowledge mappings are never guessed merely to make validation pass.

## Helper Selection Invariants

- The eligible Helper set is restricted to profiles matching the API environment with `execution_readiness = ready` and `review_status = approved`.
- Selection depends only on the version-pinned API Profile and eligible Helper Profiles. Knowledge, experiment mode, and feedback do not affect it, so all experiment groups use the same Helper set for the same API.
- Every eligible Helper remains available to HarnessSpec synthesis. API-relevant roots receive detailed prompt views, their transitive dependencies are identified separately, and the remainder appear in a compact fallback index.
- Multiple Tensor parameters reuse one Helper Profile reference; call multiplicity and cross-input relations belong to Strategy Primitives. Scalar and dimension parameters may be decoded directly when no dedicated Helper exists. `parseRank` describes constructed-Tensor rank and is not selected merely because an API accepts a dimension selector.
- Helper projection is sorted and content-hashed deterministically. Prompt input is never silently clipped; an oversized prompt fails with per-section size diagnostics.
