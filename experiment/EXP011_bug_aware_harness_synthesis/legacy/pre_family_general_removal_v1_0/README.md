# EXP011: Bug-Aware Harness Synthesis

## Purpose

EXP011 develops and validates the static synthesis pipeline that converts API-specific Knowledge and General Knowledge into a structured HarnessSpec, then lowers the HarnessSpec into Strategy Primitives and an executable fuzzing harness.

EXP011 does not own historical Bug Reports, Patterns, Pattern Families, Knowledge, or General Knowledge. Those canonical knowledge artifacts remain in EXP006.

The adaptive feedback loop is outside this experiment and will be handled separately after the static pipeline is stable.

## Planned Pipeline

```text
API Profile + Helper Profile
            +
Knowledge + General Knowledge
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
| `schemas/` | Human-readable schemas for EXP011 artifacts |
| `api_profiles/` | Structured target-API capability and constraint profiles |
| `helper_profiles/` | Structured descriptions of available helper capabilities |
| `harness_specs/` | Generated and reviewed HarnessSpec instances |
| `strategy_primitives/` | Lowered executable strategy descriptions |
| `scripts/` | Validation, conversion, and generation scripts |
| `harnesses/` | Generated harness source and build metadata |

## Current Status

Planning and schema design. No main experiment has started.

