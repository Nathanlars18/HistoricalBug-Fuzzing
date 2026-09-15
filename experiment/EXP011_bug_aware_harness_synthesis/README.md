# EXP011: Bug-Aware Harness Synthesis

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
| `harness_specs/` | Generated and reviewed HarnessSpec instances |
| `strategy_primitives/` | Lowered executable strategy descriptions |
| `scripts/` | Validation, conversion, and generation scripts |
| `harnesses/` | Generated harness source and build metadata |
| `legacy/` | Superseded design snapshots retained for traceability |

## Current Status

Planning and schema design. No main experiment has started.

## Helper Selection Invariants

- The eligible Helper set is restricted to profiles matching the API environment with `execution_readiness = ready` and `review_status = approved`.
- Selection depends only on the version-pinned API Profile and eligible Helper Profiles. Knowledge, experiment mode, and feedback do not affect it, so all experiment groups use the same Helper set for the same API.
- Every eligible Helper remains available to HarnessSpec synthesis. API-relevant roots receive detailed prompt views, their transitive dependencies are identified separately, and the remainder appear in a compact fallback index.
- Multiple Tensor parameters reuse one Helper Profile reference; call multiplicity and cross-input relations belong to Strategy Primitives. Scalar and dimension parameters may be decoded directly when no dedicated Helper exists. `parseRank` describes constructed-Tensor rank and is not selected merely because an API accepts a dimension selector.
- Helper projection is sorted and content-hashed deterministically. Prompt input is never silently clipped; an oversized prompt fails with per-section size diagnostics.
