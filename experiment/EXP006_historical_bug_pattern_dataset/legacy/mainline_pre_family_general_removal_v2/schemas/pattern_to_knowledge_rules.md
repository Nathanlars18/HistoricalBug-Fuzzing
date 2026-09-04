# Pattern-to-Knowledge Rules v2.0

## 1. Purpose

This document defines how one API-specific historical Bug Pattern is mapped to
one API-specific Knowledge candidate during initial extraction.

```text
API-specific Bug Pattern
        ↓
API-specific Knowledge
        ↓
HarnessSpec
```

A Pattern records evidence-backed historical defect information. A Knowledge
record abstracts that information into a reusable testing principle,
applicability boundary, exploration goals, and Oracle guidance.

Field names, controlled vocabularies, output format, defaults, and validation
constraints are defined in:

- `knowledge_schema.md`
- `knowledge_extraction_contract.json`

## 2. Mapping Boundary

Input: one API-specific Pattern with a stable Pattern ID, Pattern hash,
directly supported API scope, and addressable Pattern evidence references.

Output: one API-specific Knowledge candidate.

```text
One API-specific Pattern
        ↓
One API-specific Knowledge candidate
```

This is an initial extraction constraint for traceability. It does not claim
that all testing knowledge is naturally one-to-one with Patterns.

Do not produce:

- multiple Knowledge candidates;
- General Knowledge, Pattern Families, or General Patterns;
- candidate transfer APIs;
- concrete input generation, Strategy Primitives, predicates, HarnessSpec,
  code-generation prompts, or Harness code.

## 3. Field Mapping

| Pattern evidence | Knowledge representation | Mapping rule |
| --- | --- | --- |
| `metadata.canonical_name` and `scope.primary_api` | `canonical_name` | Create a concise API-specific testing-principle name. Do not retain a defect-oriented Pattern name when a clearer testing-principle name is available. |
| Pattern ID and Pattern hash | `derivation_information.input_patterns` | Added by the script. |
| Pattern ID and selected Pattern evidence references | `evidence_basis.supporting_patterns` | Added by the script as one `direct_derivation` entry. |
| Evidence supporting the abstraction | `evidence_basis.derivation_rationale` | Explain why the Pattern supports the resulting Knowledge principle. |
| Material unresolved Pattern uncertainty | `evidence_basis.limitations` | Preserve only uncertainty that materially limits applicability, exploration, or Oracle interpretation. |
| `scope.framework`, `scope.primary_api`, `scope.confirmed_apis` | `scope` | Inherited by the script. `confirmed_apis` becomes `directly_supported_apis`. |
| `defect_classification`, `trigger_signature`, and `defect_mechanism` | `knowledge_statement.risk_principle` | Abstract the reusable testing risk; do not reproduce the full trigger or mechanism. |
| Trigger, mechanism, and failure evidence | `knowledge_statement.testing_objective` | State what testing should explore or observe at a high level. |
| `observed_failure` and relevant mechanism evidence | `knowledge_statement.failure_relevance` | Explain why the objective may reveal historically relevant behavior; otherwise use `null`. |
| `transferability_hypothesis.candidate_family_tags` | `applicability.candidate_family_tags` | Preserve cautious retrieval tags only; they do not establish transferability. |
| Pattern scope, trigger, mechanism, and transferability evidence | `applicability.applicability_conditions` | Derive semantic prerequisites for selecting the Knowledge. |
| Known semantic limits in Pattern evidence | `applicability.exclusion_conditions` | Derive known reasons not to select the Knowledge. |
| Pattern transferability rationale | `applicability.rationale` | State a concise applicability boundary without naming unverified APIs. |
| Selected risk dimensions, triggers, and mechanism evidence | `testing_guidance.exploration_goals` | Derive the smallest useful set of high-level exploration goals. |
| Exploration-goal target dimensions | `testing_guidance.risk_dimensions` | Use the de-duplicated set of `target_dimension` values. |
| `observed_failure.historical_oracle` and `observed_failure` | `testing_guidance.oracle_guidance` | Preserve evidence-supported observation targets only. |
| Pattern confidence and evidence completeness | `confidence` | Reassess Knowledge confidence; do not mechanically copy Pattern confidence. |

## 4. Essential Mapping Rules

### 4.1 Evidence and abstraction

Every nontrivial Knowledge claim must cite only identifiers supplied in
`available_evidence_refs`.

Knowledge must not add a historical fact, API, root cause, failure, or source
identifier that is absent from the input Pattern.

Use:

- `pattern_explicit` for directly preserved Pattern claims;
- `pattern_derived` for evidence-backed abstraction;
- `analyst_inferred` only for cautious interpretation with cited evidence;
- `unknown`, `null`, an empty array, or `low` when evidence is insufficient.

If the Pattern cannot support a required Knowledge statement without
speculation, return the conservative candidate and let validation mark it
`needs_revision`; do not invent a plausible statement.

### 4.2 Scope and applicability

`directly_supported_apis` is inherited from Pattern evidence. It must not
contain transfer candidates.

Applicability conditions answer whether this Knowledge may be selected for a
target API. They use only:

- `api_semantics`;
- `input_capability`;
- `execution_capability`.

Conditions must be semantic statements, not concrete Tensor settings, API-call
code, mutation operations, or executable predicates.

Use `exclusion_conditions` only for known semantic inapplicability. Use
`evidence_basis.limitations` for missing or insufficient evidence.

`candidate_family_tags` are retrieval hints for later analysis; they do not
assert a Pattern Family, General Pattern, or General Knowledge.

### 4.3 Exploration and Oracle guidance

Each exploration goal has one `target_dimension`, one high-level statement,
one priority, and cited evidence.

`risk_dimensions` must equal the de-duplicated set of exploration-goal target
dimensions. Do not copy every Pattern risk dimension automatically.

Use `historical_observable` only for an evidence-backed historical observation.

Use `derived_oracle_candidate` only when cautiously inferred from Pattern
evidence. It must have `analyst_inferred` status and cannot have `high`
confidence.

Oracle guidance must not contain executable assertions, instrumentation,
timeout thresholds, sanitizer configuration, reference calls, or C++ code.

### 4.4 Confidence

Confidence measures evidence support, not how fluent or general a statement
appears.

- `high`: directly and consistently supported by Pattern evidence;
- `medium`: strongly supported but requires modest interpretation;
- `low`: incomplete, weakly supported, unknown, or analyst-inferred.

`abstraction_confidence` cannot be `high` when the main Knowledge statement is
`analyst_inferred`.

`applicability_confidence` is `low` when Applicability makes no claim.

`oracle_guidance_confidence` is `low` when `oracle_guidance` is empty.

## 5. LLM and Script Responsibilities

The LLM emits:

- `canonical_name`;
- derivation rationale and limitations;
- Knowledge statement;
- applicability and exclusion conditions;
- candidate family tags and applicability rationale;
- exploration goals;
- Oracle guidance;
- confidence values.

The script:

- supplies the Pattern, Pattern hash, and allowed evidence references;
- creates provenance, scope, derivation metadata, and deterministic IDs;
- assigns condition and goal IDs;
- validates evidence references, controlled values, scope inheritance, and
  exploration-goal dimensions;
- rejects unsupported code, predicates, concrete test construction,
  HarnessSpec, and General Knowledge content.