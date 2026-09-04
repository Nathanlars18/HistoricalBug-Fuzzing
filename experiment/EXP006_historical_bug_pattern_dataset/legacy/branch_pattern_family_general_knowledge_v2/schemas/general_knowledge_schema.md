# Historical Bug General Knowledge Schema v1.0

## 1. Purpose and Boundary

A General Knowledge record represents an evidence-grounded cross-API testing
principle derived from one validated Pattern Family revision and the validated
API-specific Knowledge records associated with its member Patterns.

It records:

- a reusable cross-API risk principle;
- semantic applicability and exclusion boundaries;
- high-level exploration and Oracle guidance;
- evidence limitations;
- directly supported API scope;
- source Family support strength;
- confidence and human-review information.

A Pattern Family explains why multiple API-specific Patterns belong together.
General Knowledge explains what reusable testing principle may be learned from
that Family.

General Knowledge does not contain raw Reports, complete source artifacts,
concrete inputs, executable strategies, predicates, Oracle implementations,
HarnessSpec, generated code, or feedback-loop state.

This Schema defines the final General Knowledge JSON format only. It does not
define extraction decisions, LLM output, Prompt construction, source discovery,
retry behavior, file allocation, or HarnessSpec construction.

---

## 2. Representation Conventions

- All top-level fields are required.
- Required objects remain present.
- Required arrays remain present when empty.
- Unknown optional scalar values use `null`.
- Unknown or unavailable list values use `[]`.
- Empty strings are not allowed.
- `"unknown"` is used only where explicitly allowed by an enum.
- Dates use ISO 8601 UTC format.
- Hashes use the `sha256:` prefix.
- Identifiers and enum values are case-sensitive.
- Arrays representing sets are sorted and de-duplicated.
- Local identifiers are unique within one General Knowledge record.
- Evidence references resolve only to exact source artifacts listed in
  `derivation_information`.
- Values shown as `null`, `[]`, `0`, or `"low"` in the structural template are
  placeholders or conservative initial values, not fixed outputs.

---

## 3. Top-level JSON Structure

```json
{
  "schema_version": "1.0",

  "metadata": {
    "knowledge_id": null,
    "canonical_name": null,
    "knowledge_level": "general"
  },

  "revision_information": {
    "revision": 1,
    "previous_knowledge_hash": null,
    "change_type": "initial_creation",
    "change_summary": null
  },

  "derivation_information": {
    "method": null,
    "mapping_version": "1.0",
    "prompt_version": null,
    "model": null,
    "input_pattern_families": [],
    "input_knowledge": [],
    "generated_at": null,
    "validation_status": "not_reviewed"
  },

  "evidence_basis": {
    "supporting_families": [],
    "supporting_knowledge": [],
    "derivation_rationale": null,
    "limitations": []
  },

  "review": {
    "reviewer": null,
    "reviewed_at": null,
    "review_notes": []
  },

  "scope": {
    "framework": "pytorch",
    "directly_supported_apis": []
  },

  "knowledge_statement": {
    "risk_principle": null,
    "testing_objective": null,
    "failure_relevance": null,
    "evidence_status": "unknown",
    "evidence_refs": []
  },

  "applicability": {
    "retrieval_tags": [],
    "applicability_conditions": [],
    "exclusion_conditions": [],
    "rationale": null,
    "evidence_status": "unknown",
    "evidence_refs": []
  },

  "testing_guidance": {
    "risk_dimensions": [],
    "exploration_goals": [],
    "oracle_guidance": []
  },

  "support": {
    "source_family_support_tier": null
  },

  "confidence": {
    "evidence_confidence": "low",
    "abstraction_confidence": "low",
    "applicability_confidence": "low",
    "oracle_guidance_confidence": "low",
    "generalization_confidence": "low"
  }
}
```

---

## 4. Field Definitions

### 4.1 Metadata

| Field | Type | Required | Purpose |
|---|---|---:|---|
| `knowledge_id` | string | yes | Stable and globally unique General Knowledge identifier. |
| `canonical_name` | string | yes | Lowercase snake_case name of the cross-API testing principle. |
| `knowledge_level` | enum | yes | Must be `general`. |

Recommended identifier format:

```text
gk_{framework_prefix}_{canonical_name}_g{ordinal}
```

Example:

```text
gk_pt_storage_layout_boundary_exploration_g001
```

The `g{ordinal}` component identifies the stable General Knowledge identity. It
is not the revision number.

The canonical name describes a reusable testing principle rather than a
specific API, source artifact, concrete input, or implementation.

---

### 4.2 Revision Information

| Field | Type | Required | Purpose |
|---|---|---:|---|
| `revision` | integer | yes | Revision number of the stable General Knowledge identity. |
| `previous_knowledge_hash` | string or null | yes | Exact file hash of the preceding revision. |
| `change_type` | enum | yes | Reason for creating the revision. |
| `change_summary` | string or null | yes | Concise description of the material change. |

Structural requirements:

- the first revision is `1`;
- `initial_creation` uses `previous_knowledge_hash = null`;
- later revisions retain the same `knowledge_id`;
- later revisions increment `revision` by exactly one;
- later revisions reference the exact preceding revision hash;
- `change_summary` is `null` for initial creation;
- `change_summary` is non-empty for later revisions.

---

### 4.3 Derivation Information

| Field | Type | Required | Purpose |
|---|---|---:|---|
| `method` | enum | yes | How the General Knowledge record was derived. |
| `mapping_version` | string | yes | Version of the Family-to-General-Knowledge mapping rules. |
| `prompt_version` | string or null | yes | Prompt version when LLM assistance is used. |
| `model` | string or null | yes | Model identifier when LLM assistance is used. |
| `input_pattern_families` | array | yes | Exact Pattern Family revision used as the generalization basis. |
| `input_knowledge` | array | yes | Exact API-specific Knowledge records used as guidance inputs. |
| `generated_at` | datetime string | yes | UTC generation time. |
| `validation_status` | enum | yes | Current validation and review state. |

#### Input Pattern Family item

Each `input_pattern_families` item contains:

| Field | Type | Required | Purpose |
|---|---|---:|---|
| `family_id` | string | yes | Stable source Pattern Family identity. |
| `family_revision` | integer | yes | Exact source Family revision. |
| `family_hash` | string | yes | Exact file hash of the source Family revision. |

Schema v1.0 requires exactly one input Pattern Family item.

#### Input API-specific Knowledge item

Each `input_knowledge` item contains:

| Field | Type | Required | Purpose |
|---|---|---:|---|
| `knowledge_id` | string | yes | Exact API-specific Knowledge identity. |
| `knowledge_hash` | string | yes | Exact file hash of the input Knowledge record. |
| `source_pattern_id` | string | yes | Source Family member Pattern represented by the Knowledge record. |

Each source Family member Pattern is represented by exactly one input
API-specific Knowledge item.

---

### 4.4 Evidence Basis

| Field | Type | Required | Purpose |
|---|---|---:|---|
| `supporting_families` | array | yes | Pattern Family evidence supporting the generalization. |
| `supporting_knowledge` | array | yes | API-specific Knowledge records contributing testing guidance. |
| `derivation_rationale` | string | yes | Why the source evidence supports the General Knowledge. |
| `limitations` | array | yes | Material boundaries, conflicts, differences, or evidence gaps. |

#### Supporting Family item

Each `supporting_families` item contains:

| Field | Type | Required | Purpose |
|---|---|---:|---|
| `family_id` | string | yes | Source Pattern Family identity. |
| `relation` | enum | yes | How the Family supports the General Knowledge. |
| `evidence_refs` | array | yes | Source Family fields supporting the generalization. |

Schema v1.0 requires exactly one supporting Family item.

Its allowed relation is:

```text
direct_generalization_basis
```

The Family ID must match the item in
`derivation_information.input_pattern_families`.

#### Supporting API-specific Knowledge item

Each `supporting_knowledge` item contains:

| Field | Type | Required | Purpose |
|---|---|---:|---|
| `knowledge_id` | string | yes | Input API-specific Knowledge identity. |
| `relation` | enum | yes | How the Knowledge contributes guidance. |
| `evidence_refs` | array | yes | Input Knowledge fields contributing guidance. |

The allowed relation is:

```text
member_guidance
```

Each supporting Knowledge ID must occur in
`derivation_information.input_knowledge`.

#### Limitation item

Each `limitations` item contains:

| Field | Type | Required | Purpose |
|---|---|---:|---|
| `limitation_id` | string | yes | Stable record-local limitation identifier. |
| `limitation_kind` | enum | yes | Type of limitation or uncertainty. |
| `statement` | string | yes | Concise description of the limitation. |
| `evidence_status` | enum | yes | Origin of the limitation statement. |
| `evidence_refs` | array | yes | Evidence supporting the limitation. |

Local limitation IDs use:

```text
lm_01
lm_02
...
```

---

### 4.5 Review

| Field | Type | Required | Purpose |
|---|---|---:|---|
| `reviewer` | string or null | yes | Stable project-local reviewer label. |
| `reviewed_at` | datetime string or null | yes | UTC completion time of human review. |
| `review_notes` | array of strings | yes | Concise human-review findings. |

Structural requirements:

- `reviewer` and `reviewed_at` are either both null or both non-null;
- `human_verified` requires non-null `reviewer` and `reviewed_at`;
- `not_reviewed` and `automatically_validated` require null `reviewer` and
  `reviewed_at`;
- human-reviewed `needs_revision` requires reviewer information and at least one
  review note;
- before human review, `review_notes` is empty.

---

### 4.6 Scope

| Field | Type | Required | Purpose |
|---|---|---:|---|
| `framework` | string | yes | Framework shared by all source artifacts. |
| `directly_supported_apis` | array of strings | yes | APIs directly supported by source Family evidence. |

`directly_supported_apis` equals the sorted and de-duplicated API set of the
source Pattern Family members.

General Knowledge has no `primary_api`.

Candidate target APIs are not stored in `directly_supported_apis`.

---

### 4.7 Knowledge Statement

| Field | Type | Required | Purpose |
|---|---|---:|---|
| `risk_principle` | string | yes | Reusable cross-API testing risk. |
| `testing_objective` | string | yes | High-level testing objective. |
| `failure_relevance` | string or null | yes | Historically relevant failure connection. |
| `evidence_status` | enum | yes | Origin of the Knowledge statement. |
| `evidence_refs` | array | yes | Family or Knowledge evidence supporting the statement. |

The Knowledge statement requires at least one source Family evidence reference.

---

### 4.8 Applicability

| Field | Type | Required | Purpose |
|---|---|---:|---|
| `retrieval_tags` | array of strings | yes | Normalized tags used for later Knowledge retrieval. |
| `applicability_conditions` | array | yes | Semantic prerequisites for considering the Knowledge. |
| `exclusion_conditions` | array | yes | Conditions under which the Knowledge must not be selected. |
| `rationale` | string or null | yes | Explanation of the applicability boundary. |
| `evidence_status` | enum | yes | Origin of the applicability abstraction. |
| `evidence_refs` | array | yes | Evidence supporting the applicability boundary. |

Retrieval tags use lowercase snake_case and are sorted and de-duplicated.

#### Applicability or exclusion condition item

Each condition item contains:

| Field | Type | Required | Purpose |
|---|---|---:|---|
| `condition_id` | string | yes | Stable record-local condition identifier. |
| `condition_kind` | enum | yes | Broad semantic condition category. |
| `statement` | string | yes | Human-readable semantic condition. |
| `evidence_status` | enum | yes | Origin of the condition. |
| `evidence_refs` | array | yes | Evidence supporting the condition. |

Local ID formats:

```text
applicability_conditions → ac_01, ac_02, ...
exclusion_conditions     → ec_01, ec_02, ...
```

When no applicability claim is present:

```text
applicability_conditions = []
exclusion_conditions = []
rationale = null
evidence_status = unknown
evidence_refs = []
```

---

### 4.9 Testing Guidance

| Field | Type | Required | Purpose |
|---|---|---:|---|
| `risk_dimensions` | array | yes | Dimensions targeted by exploration goals. |
| `exploration_goals` | array | yes | High-level cross-API exploration directions. |
| `oracle_guidance` | array | yes | High-level behavior worth observing. |

#### Exploration goal item

Each `exploration_goals` item contains:

| Field | Type | Required | Purpose |
|---|---|---:|---|
| `goal_id` | string | yes | Stable record-local goal identifier. |
| `target_dimension` | enum | yes | Risk dimension targeted by the goal. |
| `statement` | string | yes | High-level exploration direction. |
| `priority` | enum | yes | Relative research importance. |
| `evidence_status` | enum | yes | Origin of the goal. |
| `evidence_refs` | array | yes | Evidence supporting the goal. |

Local goal IDs use:

```text
eg_01
eg_02
...
```

#### Oracle guidance item

Each `oracle_guidance` item contains:

| Field | Type | Required | Purpose |
|---|---|---:|---|
| `objective` | string | yes | High-level behavior later testing should observe. |
| `observation_kind` | enum | yes | Historical observation or derived Oracle candidate. |
| `evidence_status` | enum | yes | Origin of the Oracle guidance. |
| `evidence_refs` | array | yes | Evidence supporting the guidance. |
| `confidence` | enum | yes | Confidence in the individual guidance item. |

Testing guidance does not contain executable strategies, concrete input
construction, predicates, instrumentation, or code.

---

### 4.10 Support

| Field | Type | Required | Purpose |
|---|---|---:|---|
| `source_family_support_tier` | enum | yes | Support tier of the exact source Pattern Family revision. |

The value equals:

```text
source Pattern Family support.support_tier
```

Support tier describes historical evidence strength. It does not prove
applicability to a new target API.

---

### 4.11 Confidence

| Field | Type | Required | Purpose |
|---|---|---:|---|
| `evidence_confidence` | enum | yes | Confidence in source completeness and traceability. |
| `abstraction_confidence` | enum | yes | Confidence in the reusable testing principle. |
| `applicability_confidence` | enum | yes | Confidence in applicability and exclusion boundaries. |
| `oracle_guidance_confidence` | enum | yes | Aggregate confidence in Oracle guidance. |
| `generalization_confidence` | enum | yes | Confidence in considering the principle for semantically compatible APIs beyond directly supported APIs. |

Structural requirements:

- `generalization_confidence` does not exceed the source Family
  `confidence.generalization`;
- `applicability_confidence` is `low` when Applicability makes no claim;
- `oracle_guidance_confidence` is `low` when `oracle_guidance` is empty;
- when `knowledge_statement.evidence_status` is `analyst_inferred`,
  `abstraction_confidence` must not be `high`;
- when `applicability.evidence_status` is `analyst_inferred`,
  `applicability_confidence` must not be `high`;
- when an `oracle_guidance` item uses `analyst_inferred`, that item's
  `confidence` must not be `high`.

---

## 5. Controlled Enums

### 5.1 Knowledge Level

```text
general
```

### 5.2 Change Type

```text
initial_creation
source_family_update
knowledge_reanalysis
```

### 5.3 Derivation Method

```text
direct_mapping
llm_assisted
manual
hybrid
```

### 5.4 Validation Status

```text
not_reviewed
automatically_validated
human_verified
needs_revision
```

### 5.5 Supporting Family Relation

```text
direct_generalization_basis
```

### 5.6 Supporting Knowledge Relation

```text
member_guidance
```

### 5.7 Evidence Status

| Value | Meaning |
|---|---|
| `family_explicit` | Directly represented in the cited source Family. |
| `family_derived` | Derived from cited Family and compatible member Knowledge evidence. |
| `analyst_inferred` | Reasoned interpretation based on cited evidence. |
| `unknown` | No reliable positive claim is made. |

### 5.8 Limitation Kind

```text
member_difference
unresolved_conflict
applicability_boundary
evidence_gap
support_boundary
```

### 5.9 Condition Kind

```text
api_semantics
input_capability
execution_capability
```

### 5.10 Risk Dimension

```text
shape
dtype
value
device
backend
layout
memory
aliasing
output_tensor
state
execution
graph
concurrency
api_contract
```

### 5.11 Priority

```text
primary
secondary
```

### 5.12 Observation Kind

```text
historical_observable
derived_oracle_candidate
```

### 5.13 Support Tier

```text
emerging
corroborated
broadly_supported
```

### 5.14 Confidence

```text
high
medium
low
```

---

## 6. Evidence Reference Format

Evidence references use:

```text
family:<family_id>:<field_or_local_element_path>
knowledge:<knowledge_id>:<field_or_local_element_path>
```

Examples:

```text
family:pf_pt_storage_layout_backend_f001:family_core

knowledge:kn_pt_matmul_storage_boundary_exploration_k001:
testing_guidance.exploration_goals.eg_01
```

Stored evidence references are uninterrupted strings. The line break above is
for readability only.

Every reference resolves to an exact artifact listed in
`derivation_information`.

Direct Report and direct Pattern references are not used in General Knowledge
Schema v1.0.

---

## 7. Structural Validation Invariants

A structurally valid General Knowledge record satisfies all of the following:

1. `schema_version` is `1.0`.
2. `metadata.knowledge_level` is `general`.
3. IDs, revisions, hashes, dates, and controlled values use the defined formats.
4. Exactly one source Pattern Family revision is present.
5. Exactly one `direct_generalization_basis` item references that Family.
6. Every source Family member Pattern is represented exactly once by a validated
   input API-specific Knowledge record.
7. Every supporting Knowledge ID occurs in `input_knowledge`; an accepted
   General Knowledge record contains at least two distinct supporting Knowledge
   records associated with at least two distinct directly supported APIs.
8. All source artifacts use the same framework.
9. `scope.directly_supported_apis` equals the source Family member API set.
10. Candidate target APIs are absent from `directly_supported_apis`.
11. Evidence references resolve only to the listed Family or Knowledge inputs.
12. The core Knowledge statement contains at least one Family evidence reference.
13. Direct Report and direct Pattern evidence references are absent.
14. Local IDs are unique within their corresponding arrays.
15. `risk_dimensions` equals the sorted, de-duplicated set of
    `exploration_goals[].target_dimension`.
16. `support.source_family_support_tier` equals the source Family support tier.
17. Confidence values satisfy the cross-field structural requirements.
18. Review metadata is consistent with `validation_status`.
19. Empty strings and unsupported additional fields are absent.
20. The record contains no executable strategy, predicate, instrumentation,
    HarnessSpec, generated code, or feedback-loop state.