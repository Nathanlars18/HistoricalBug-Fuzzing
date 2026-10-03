# Pattern-to-Knowledge Rules v2.3

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

Input: one schema-v4.0 API-specific Pattern with a stable Pattern ID, Pattern hash,
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
- concrete input generation, Strategy Primitives, predicates, HarnessSpec,
  code-generation prompts, or Harness code.

## 3. Field Mapping

| Pattern evidence | Knowledge representation | Mapping rule |
| --- | --- | --- |
| `metadata.canonical_name` and `scope.target_api` | `canonical_name` | Create a concise API-specific testing-principle name. Do not retain a defect-oriented Pattern name when a clearer testing-principle name is available. |
| Pattern ID and Pattern hash | `derivation_information.input_patterns` | Added by the script. |
| Pattern ID and selected Pattern evidence references | `evidence_basis.supporting_patterns` | Added by the script as one `direct_derivation` entry. |
| Evidence supporting the abstraction | `evidence_basis.derivation_rationale` | Explain why the Pattern supports the resulting Knowledge principle. |
| Material unresolved Pattern uncertainty | `evidence_basis.limitations` | Preserve only uncertainty that materially limits applicability, exploration, or Oracle interpretation. |
| `scope.framework`, `scope.target_api` | `scope` | Inherited by the script. The target becomes both `primary_api` and the sole `directly_supported_apis` entry in Knowledge v2.1. |
| `historical_conditions`, optional `defect_mechanism`, and `observed_failure` | `knowledge_statement.risk_principle` | Abstract the reusable testing risk; do not reproduce the full historical case. |
| Trigger, mechanism, and failure evidence | `knowledge_statement.testing_objective` | State what testing should explore or observe at a high level. |
| `observed_failure` and relevant mechanism evidence | `knowledge_statement.failure_relevance` | Explain why the objective may reveal historically relevant behavior; otherwise use `null`. |
| Pattern scope, trigger, and mechanism evidence | `applicability.applicability_conditions` | Derive semantic prerequisites within the directly supported API scope. |
| Known semantic limits in Pattern evidence | `applicability.exclusion_conditions` | Derive known reasons not to select the Knowledge. |
| Pattern scope, trigger, and mechanism evidence | `applicability.rationale` | State a concise applicability boundary within the directly supported API scope. |
| Historical conditions, triggers, and mechanism evidence | `testing_guidance.exploration_goals` | Derive the smallest useful set of high-level exploration goals. |
| Exploration-goal target dimensions | `testing_guidance.risk_dimensions` | Use the de-duplicated set of `target_dimension` values. |
| `observed_failure.historical_observations` and `observed_failure` | `testing_guidance.oracle_guidance` | Derive observation candidates conservatively; historical observations are not automatically future Oracles. |
| Pattern evidence completeness | `confidence` | Assess Knowledge confidence from cited Pattern evidence; Pattern v4 has no aggregate confidence field to copy. |

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

Root-cause categories organize explanations; symptom categories organize
manifestations. Neither is a direct lookup for exploration goals or Oracles.
Do not duplicate taxonomy labels in Knowledge. A null mechanism or taxonomy
label alone does not make a Pattern unusable when conditions and failure
evidence support a testing principle.
Preserve uncertainty about necessity; justify generalization of historical
constants instead of silently fixing them as mandatory future test inputs.

### 4.2 Scope and applicability

`directly_supported_apis` is inherited from Pattern evidence. It must match the API scope directly supported by the source Pattern.

Applicability conditions answer whether this Knowledge is relevant to a testing
scenario within its directly supported API scope. They use only:

- `api_semantics`;
- `input_capability`;
- `execution_capability`.

Conditions must be semantic statements, not concrete Tensor settings, API-call
code, mutation operations, or executable predicates.

Use `exclusion_conditions` only for known semantic inapplicability. Use
`evidence_basis.limitations` for missing or insufficient evidence.

### 4.3 Exploration and Oracle guidance

Each exploration goal has one `target_dimension`, one high-level statement,
one priority, and cited evidence.

`risk_dimensions` must equal the de-duplicated set of exploration-goal target
dimensions. Do not copy every historical condition dimension automatically.

Use `historical_observable` only for an evidence-backed historical observation.

Use `derived_oracle_candidate` only when cautiously inferred from Pattern
evidence. It must have `analyst_inferred` status and cannot have `high`
confidence.

Oracle guidance must not contain executable assertions, instrumentation,
timeout thresholds, sanitizer configuration, reference calls, or C++ code.

### 4.4 Confidence

Confidence measures evidence support, not how fluent or broad a statement
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
- applicability conditions, exclusions, and rationale;
- exploration goals;
- Oracle guidance;
- confidence values.

The script:

- supplies the Pattern, Pattern hash, and allowed evidence references;
- creates provenance, scope, derivation metadata, and deterministic IDs;
- assigns condition and goal IDs;
- validates evidence references, controlled values, scope inheritance, and
  exploration-goal dimensions;
- rejects unsupported code, predicates, concrete test construction and HarnessSpec content.
