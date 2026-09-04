# Report-to-Pattern Mapping v2.0

## 1. Purpose

This document defines how one structured historical Bug Report is mapped to one
or more API-specific Bug Patterns.

The mapping preserves the following relationship:

```text
Structured Bug Report
        ↓
API-specific Bug Pattern
        ↓
Specific Knowledge
        ↓
HarnessSpec
```

A Bug Report preserves concrete historical evidence.

A Bug Pattern is an evidence-grounded abstraction of defect mechanism, trigger
conditions, historical failure behavior, and directly supported API scope.

This document defines mapping decisions only. Field names, controlled
vocabularies, output format, and validation constraints are defined in:

- `pattern_schema.md`
- `pattern_extraction_contract.json`

## 2. Mapping Boundary

### Input

The input is one structured Bug Report with:

- a stable Report ID;
- framework and API information;
- addressable evidence references;
- available trigger, failure, mechanism, or fix information.

### Output

The output is one or more API-specific Pattern candidates.

Each initial Pattern must:

- be supported by the current input Report;
- contain exactly one `direct_evidence` source Report;
- preserve relevant evidence references;
- remain independent of Knowledge, HarnessSpec, and Pattern Family decisions.

This mapping does not produce:

- General Patterns;
- Pattern Families;
- General Knowledge;
- Harness Strategies;
- executable constraints;
- code-generation prompts or Harness code.

## 3. Cardinality and Split Rules

The default mapping is:

```text
One Bug Report
        ↓
One API-specific Bug Pattern
```

One Bug Report may be split into multiple Patterns only when it contains
independent and separately testable defect units.

Split the Report only when at least one condition holds:

1. Different affected APIs have independent defect behavior and are not merely
   aliases of the same call.

2. Different trigger groups correspond to different defect mechanisms or
   different historical failures.

3. Different execution scenarios are incompatible and cannot be represented by
   one coherent trigger signature.

4. Multiple independently supported root-cause hypotheses describe distinct
   defects rather than uncertainty about the same defect.

Do not split a Report merely because it contains several jointly required
conditions, such as shape, dtype, device, layout, and backend constraints for
one failure.

Do not split a Report because it mentions possible transfer APIs.

When the split decision is uncertain, prefer one conservative Pattern and
record the ambiguity in `provenance.unresolved_information`.

## 4. Field Mapping Rules

| Bug Report evidence | Pattern representation | Mapping rule |
|---|---|---|
| Report identifier and source status | `provenance.supporting_reports` | The input Report becomes the single `direct_evidence` source. |
| API and affected APIs | `scope` | Include only APIs explicitly supported by the Report. |
| Operator and module | `scope.operator`, `scope.module` | Preserve when explicit or deterministically normalized; otherwise use `null`. |
| Trigger facts | `trigger_signature` | Normalize historical conditions only; do not add generation strategies. |
| Execution sequence or call context | `trigger_signature.operation_context` | Include only when historically supported. |
| Root cause, developer reply, patch, or commit | `defect_mechanism.hypotheses` | Preserve evidence-backed explanations and uncertainty. |
| Historical failure behavior | `observed_failure` | Record factual behavior only. |
| Historical detection method | `historical_oracle` | Preserve only historically observed or used oracles. |
| Defect theme and risk dimensions | `defect_classification` | Select the most evidence-supported primary defect class. Risk dimensions may be an empty array when the available evidence does not establish a concrete triggering dimension. |
| Potential mechanism reuse | `transferability_hypothesis` | Record a cautious hypothesis only; do not claim cross-API equivalence. |
| Important missing information | `provenance.unresolved_information` | Record uncertainties that materially affect explanation or transferability. |

## 5. Evidence Rules

Every nontrivial Pattern claim must be traceable to the input Report.

The mapper must:

- cite only identifiers listed in `available_evidence_refs`;
- not invent Report IDs, APIs, operator names, root causes, fixes, or
  reproductions;
- distinguish facts from analyst inference;
- use `null`, `unknown`, or `low` when evidence is insufficient, according to
  `pattern_extraction_contract.json`;
- preserve conflicting mechanism hypotheses rather than silently selecting one;
- preserve uncertainty when the Report does not support a definite conclusion.

`provenance.unresolved_information` should contain only important unresolved
questions, for example:

- whether a failure affects another backend;
- whether a root cause is officially confirmed;
- whether a condition is necessary or only contributing.

It should be an empty array when no material uncertainty remains.

## 6. API Scope and Transferability

`scope.confirmed_apis` contains only APIs directly supported by historical
evidence.

Similar APIs, APIs with compatible signatures, or APIs that may share an
implementation must not be added to `confirmed_apis`.

Such information may be represented only through:

- `candidate_family_tags`;
- `applicability_conditions`;
- `exclusion_conditions`;
- `transferability_hypothesis.rationale`.

A transferability hypothesis does not prove that another API has the same Bug.
It only provides evidence-aware input for later Pattern Family retrieval and
General Knowledge construction.

## 7. Confidence Rules

Confidence is assigned independently for:

- trigger conditions;
- defect mechanism;
- historical oracle;
- transferability.

Use `high` only for direct or strongly corroborated evidence.

Use `medium` for well-supported but not explicitly confirmed conclusions.

Use `low` for incomplete, weakly supported, or analyst-inferred conclusions.

A fluent LLM explanation must not increase confidence.

## 8. Extraction Responsibilities

The LLM extracts semantic content:

- Pattern name;
- API scope;
- trigger conditions;
- defect classification;
- mechanism hypotheses;
- historical failure and oracle;
- transferability hypothesis;
- unresolved information;
- confidence values.

The conversion script performs deterministic work:

- provides the Report and allowed evidence references;
- assigns IDs, framework, hashes, timestamps, and derivation metadata;
- validates controlled vocabularies;
- validates evidence references;
- verifies API-scope constraints;
- rejects forbidden Harness Strategy, HarnessSpec, and code fields.

The script may normalize formatting, but it must not silently repair unsupported
semantic claims.

## 9. Review Rule

A Pattern that lacks sufficient evidence, has an unclear split decision, or
contains unsupported semantic claims must be marked `needs_revision`.

Human review should prioritize:

- low-confidence mechanism or transferability claims;
- multiple candidate Pattern splits;
- conflicting mechanism hypotheses;
- Patterns selected for experimental evaluation;
- Patterns later considered for Pattern Family construction.