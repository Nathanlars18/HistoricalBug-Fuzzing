# Historical Bug Pattern Family Schema v1.1

## 1. Purpose

A Pattern Family represents an evidence-grounded relationship among multiple
API-specific historical Bug Patterns from the same framework.

One Pattern Family JSON file represents one Family revision.

It records:

- exact member Patterns and their historical sources;
- the common risk semantics shared by the members;
- shared trigger, mechanism, execution, and failure characteristics;
- applicability boundaries;
- member differences and unresolved conflicts;
- support breadth and confidence;
- generation and review provenance.

This Schema defines only the final Pattern Family JSON format.

Candidate retrieval and the `accept`, `split`, `reject`, and `needs_revision`
decisions are defined in separate Policy, Contract, Rules, and Validator
components.

Deterministic support metadata is defined by Section 13 of this Schema and
implemented by the versioned conversion script.

---

## 2. Representation Conventions

- All top-level fields are required.
- Required arrays remain present when empty.
- Unknown scalar values use `null`.
- Unknown or empty list values use `[]`.
- Empty strings are not allowed.
- `"unknown"` is used only where explicitly allowed by an enum.
- Dates use ISO 8601 format.
- Evidence references point to exact fields in member Pattern records.
- Values shown as `null`, `[]`, or `0` in the structure below are placeholders,
  not fixed output values.

---

## 3. Top-level Structure

```json
{
  "schema_version": "1.1",

  "metadata": {
    "family_id": null,
    "canonical_name": null,
    "framework": null
  },

  "revision_information": {
    "revision": 1,
    "previous_family_hash": null,
    "change_type": "initial_creation",
    "parent_family_refs": [],
    "change_summary": null
  },

  "provenance": {
    "method": null,

    "candidate_policy_version": null,
    "candidate_policy_hash": null,

    "family_contract_version": null,
    "family_contract_hash": null,

    "family_rules_version": null,
    "family_rules_hash": null,

    "prompt_version": null,
    "model": null,

    "input_candidate_manifests": [],

    "source_decision_record": {
      "decision_record_id": null,
      "decision_record_hash": null,
      "analysis_input_hash": null
    },

    "generated_at": null,
    "validation_status": "not_reviewed"
  },

  "review": {
    "reviewer": null,
    "reviewed_at": null,
    "review_notes": []
  },

  "members": [],

  "family_core": {
    "statement": null,
    "basis_types": [],
    "shared_defect_classes": [],
    "shared_risk_dimensions": [],
    "evidence_status": "unknown",
    "evidence_refs": [],
    "confidence": null
  },

  "shared_characteristics": {
    "trigger_semantics": [],
    "mechanism_semantics": [],
    "execution_semantics": [],
    "failure_observables": []
  },

  "applicability": {
    "required_capabilities": [],
    "exclusion_conditions": []
  },

  "heterogeneity": {
    "member_differences": [],
    "unresolved_conflicts": []
  },

  "support": {
    "supporting_apis": [],
    "pattern_count": 0,
    "distinct_api_count": 0,
    "independent_report_count": 0,
    "support_tier": null,
    "tier_rationale": null
  },

  "confidence": {
    "membership": null,
    "commonality": null,
    "applicability": null,
    "generalization": null
  }
}
```

---

## 4. Metadata

```json
"metadata": {
  "family_id": "pf_pt_storage_layout_backend_f001",
  "canonical_name": "storage_layout_backend",
  "framework": "pytorch"
}
```

| Field | Type | Required | Description |
|---|---|---:|---|
| `family_id` | string | yes | Stable Family identity, excluding revision. |
| `canonical_name` | string | yes | Concise lowercase snake_case semantic name. |
| `framework` | string | yes | Framework shared by all member Patterns. |

`canonical_name` describes the shared risk or mechanism semantics.

It must not contain:

- a specific API name;
- a Report, Issue, or Pattern ID;
- a commit ID;
- a concrete Tensor value;
- an unsupported claim of universality.

---

## 5. Revision Information

```json
"revision_information": {
  "revision": 1,
  "previous_family_hash": null,
  "change_type": "initial_creation",
  "parent_family_refs": [],
  "change_summary": null
}
```

| Field | Type | Required | Description |
|---|---|---:|---|
| `revision` | integer | yes | Family revision number beginning at 1. |
| `previous_family_hash` | string or null | yes | Hash of the immediately preceding revision. |
| `change_type` | enum | yes | Type of revision operation. |
| `parent_family_refs` | array | yes | Parent Families involved in merge, split, or derivation. |
| `change_summary` | string or null | yes | Concise explanation of the revision. |

Allowed `change_type` values:

- `initial_creation`
- `member_update`
- `member_reanalysis`
- `family_merge`
- `family_split`

Each `parent_family_refs` item uses:

```json
{
  "family_id": "pf_pt_previous_family_f001",
  "revision": 2,
  "family_hash": "sha256:...",
  "relation": "split_from"
}
```

Allowed `relation` values:

- `split_from`
- `merged_from`
- `derived_from`

Revision operation rules:

- an independently created Family uses revision `1`,
  `change_type = "initial_creation"`, and no parent references;
- a Family created with `derive_new` uses revision `1`,
  `change_type = "initial_creation"`, and one or more `derived_from` parent
  references;
- `update_existing` retains the Family ID, increments the revision, sets
  `previous_family_hash`, and uses either `member_update` or
  `member_reanalysis`;
- a merged Family receives a new Family ID, revision `1`,
  `change_type = "family_merge"`, and at least two `merged_from` parent
  references;
- each split child receives a new Family ID, revision `1`,
  `change_type = "family_split"`, and exactly one `split_from` parent
  reference;
- `reuse_existing` creates no new Family revision.

An independently created initial Family uses:

```json
{
  "revision": 1,
  "previous_family_hash": null,
  "change_type": "initial_creation",
  "parent_family_refs": [],
  "change_summary": null
}
```

---

## 6. Provenance

```json
"provenance": {
  "method": "llm_assisted",

  "candidate_policy_version": "1.1-provisional",
  "candidate_policy_hash": "sha256:...",

  "family_contract_version": "1.1",
  "family_contract_hash": "sha256:...",

  "family_rules_version": "1.2",
  "family_rules_hash": "sha256:...",

  "prompt_version": "pattern_family_extract_v1",
  "model": "model-name",

  "input_candidate_manifests": [
    {
      "candidate_group_id": "pfc_pt_a13f09c2",
      "candidate_group_hash": "sha256:..."
    }
  ],

  "source_decision_record": {
    "decision_record_id": "pfd_pt_a13f09c2e641",
    "decision_record_hash": "sha256:...",
    "analysis_input_hash": "sha256:a13f09c2e641..."
  },

  "generated_at": "2026-08-29T10:30:00+08:00",
  "validation_status": "automatically_validated"
}
```

| Field | Type | Required | Description |
|---|---|---:|---|
| `method` | enum | yes | Family construction method. |
| `candidate_policy_version` | string | yes | Candidate Policy version. |
| `candidate_policy_hash` | string | yes | Exact Candidate Policy hash. |
| `family_contract_version` | string | yes | Family Contract version. |
| `family_contract_hash` | string | yes | Exact Family Contract hash. |
| `family_rules_version` | string | yes | Family Rules version. |
| `family_rules_hash` | string | yes | Exact Family Rules hash. |
| `prompt_version` | string | yes | Prompt-template version. |
| `model` | string or null | yes | Model used when applicable. |
| `input_candidate_manifests` | array | yes | Candidate Manifests used to construct the Family. |
| `source_decision_record` | object | yes | Exact validated Decision Record that supplied the semantic proposal. |
| `generated_at` | datetime string | yes | Generation time. |
| `validation_status` | enum | yes | Current validation state. |

Allowed `method` values:

- `llm_assisted`
- `manual`
- `hybrid`

Allowed `validation_status` values:

- `not_reviewed`
- `automatically_validated`
- `human_verified`
- `needs_revision`

Each Candidate Manifest reference contains:

```json
{
  "candidate_group_id": "pfc_pt_a13f09c2",
  "candidate_group_hash": "sha256:..."
}
```

Member Pattern IDs and hashes are not repeated here because they are already
stored in `members`.

Each `source_decision_record` uses:

```json
{
  "decision_record_id": "pfd_pt_a13f09c2e641",
  "decision_record_hash": "sha256:...",
  "analysis_input_hash": "sha256:a13f09c2e641..."
}
```

| Field | Type | Required | Description |
|---|---|---:|---|
| `decision_record_id` | string or null | yes | Exact Decision Record identity. |
| `decision_record_hash` | string or null | yes | SHA-256 hash of the complete immutable Decision Record file. |
| `analysis_input_hash` | string or null | yes | Semantic analysis-input hash stored by the Decision Record. |

For `llm_assisted` construction, all three fields must be non-null and resolve
to one valid immutable Decision Record.

For `hybrid` construction, all three fields identify the Decision Record used
as the machine-assisted source before human modification.

For `manual` construction, no Decision Record is required and the object uses:

```json
{
  "decision_record_id": null,
  "decision_record_hash": null,
  "analysis_input_hash": null
}
```

The final Pattern Family does not copy the complete Decision payload.

The Decision Record remains the owner of the proposed Decision and proposed
lineage. The final Family stores the materialized result through
`revision_information`.

---

## 7. Review

```json
"review": {
  "reviewer": null,
  "reviewed_at": null,
  "review_notes": []
}
```

| Field | Type | Required | Description |
|---|---|---:|---|
| `reviewer` | string or null | yes | Stable project-local reviewer label. |
| `reviewed_at` | datetime string or null | yes | Review completion time. |
| `review_notes` | array of strings | yes | Concise review findings. |

Before human review, all review fields remain null or empty.

---

## 8. Members

`members` contains the API-specific Patterns included in the Family.

Each member uses:

```json
{
  "pattern_id": "pt_matmul_unaligned_storage_p001",
  "pattern_hash": "sha256:...",
  "primary_api": "torch.matmul",

  "source_report_ids": [
    "pt_report_001"
  ],

  "membership_rationale": "The Pattern exhibits the storage-sensitive risk represented by the Family core.",

  "evidence_status": "cross_pattern_derived",

  "evidence_refs": [
    "pattern:pt_matmul_unaligned_storage_p001:defect_classification",
    "pattern:pt_matmul_unaligned_storage_p001:trigger_signature"
  ],

  "confidence": "medium"
}
```

| Field | Type | Required | Description |
|---|---|---:|---|
| `pattern_id` | string | yes | Exact member Pattern ID. |
| `pattern_hash` | string | yes | Exact member Pattern hash. |
| `primary_api` | string | yes | Primary API copied from the Pattern. |
| `source_report_ids` | array | yes | Direct Report sources copied from the Pattern. |
| `membership_rationale` | string | yes | Family-specific reason for membership. |
| `evidence_status` | enum | yes | Origin of the membership claim. |
| `evidence_refs` | array | yes | Pattern evidence supporting membership. |
| `confidence` | enum | yes | Confidence in the membership. |

Candidate retrieval signals are not membership evidence.

If one Pattern belongs to multiple Families, each Family records its own
membership rationale and evidence.

---

## 9. Family Core

```json
"family_core": {
  "statement": "Storage- or layout-sensitive tensor execution may expose backend failures across APIs.",

  "basis_types": [
    "risk_boundary",
    "trigger_semantics",
    "execution_semantics"
  ],

  "shared_defect_classes": [
    "memory_layout_boundary"
  ],

  "shared_risk_dimensions": [
    "layout",
    "memory"
  ],

  "evidence_status": "cross_pattern_derived",

  "evidence_refs": [
    "pattern:pt_conv2d_storage_boundary_p001:defect_classification",
    "pattern:pt_matmul_unaligned_storage_p001:defect_classification"
  ],

  "confidence": "medium"
}
```

| Field | Type | Required | Description |
|---|---|---:|---|
| `statement` | string | yes | Narrowest defensible common Family statement. |
| `basis_types` | array of enums | yes | Evidence dimensions forming the common core. |
| `shared_defect_classes` | array | yes | Defect classes shared across the Family. |
| `shared_risk_dimensions` | array | yes | Risk dimensions shared across the Family. |
| `evidence_status` | enum | yes | Origin of the Family-core claim. |
| `evidence_refs` | array | yes | Pattern evidence supporting the core. |
| `confidence` | enum | yes | Confidence in the Family core. |

Allowed `basis_types` values:

- `risk_boundary`
- `trigger_semantics`
- `mechanism_semantics`
- `execution_semantics`
- `failure_observable`

The Family core applies to every member. Therefore, a separate
`supporting_pattern_ids` field is not required here.

---

## 10. Shared Characteristics

```json
"shared_characteristics": {
  "trigger_semantics": [],
  "mechanism_semantics": [],
  "execution_semantics": [],
  "failure_observables": []
}
```

Each characteristic uses:

```json
{
  "characteristic_id": "st_01",

  "statement": "The failure is associated with non-standard storage-layout conditions.",

  "supporting_pattern_ids": [
    "pt_conv2d_storage_boundary_p001",
    "pt_matmul_unaligned_storage_p001"
  ],

  "evidence_status": "cross_pattern_derived",

  "evidence_refs": [
    "pattern:pt_conv2d_storage_boundary_p001:trigger_signature",
    "pattern:pt_matmul_unaligned_storage_p001:trigger_signature"
  ],

  "confidence": "medium"
}
```

| Field | Type | Required | Description |
|---|---|---:|---|
| `characteristic_id` | string | yes | Stable Family-local characteristic ID. |
| `statement` | string | yes | Shared semantic characteristic. |
| `supporting_pattern_ids` | array | yes | Members supporting the characteristic. |
| `evidence_status` | enum | yes | Origin of the characteristic. |
| `evidence_refs` | array | yes | Pattern evidence supporting it. |
| `confidence` | enum | yes | Confidence in the characteristic. |

Recommended ID prefixes:

```text
trigger_semantics    → st_
mechanism_semantics  → sm_
execution_semantics  → se_
failure_observables  → sf_
```

A characteristic may be supported by all members or by a documented subset.
Subset-supported characteristics are not automatically part of the Family
core.

Counts and coverage ratios are not stored because they can be calculated from
`supporting_pattern_ids` and `members`.

---

## 11. Applicability

```json
"applicability": {
  "required_capabilities": [],
  "exclusion_conditions": []
}
```

Each capability or exclusion condition uses:

```json
{
  "condition_id": "rc_01",
  "kind": "input_capability",

  "statement": "The API accepts tensor inputs whose storage or layout properties may affect execution.",

  "supporting_pattern_ids": [
    "pt_conv2d_storage_boundary_p001",
    "pt_matmul_unaligned_storage_p001"
  ],

  "evidence_status": "cross_pattern_derived",

  "evidence_refs": [
    "pattern:pt_conv2d_storage_boundary_p001:transferability_hypothesis",
    "pattern:pt_matmul_unaligned_storage_p001:transferability_hypothesis"
  ],

  "confidence": "medium"
}
```

| Field | Type | Required | Description |
|---|---|---:|---|
| `condition_id` | string | yes | Stable Family-local condition ID. |
| `kind` | enum | yes | Capability or exclusion category. |
| `statement` | string | yes | Semantic applicability condition. |
| `supporting_pattern_ids` | array | yes | Members supporting the condition. |
| `evidence_status` | enum | yes | Origin of the condition. |
| `evidence_refs` | array | yes | Pattern evidence supporting it. |
| `confidence` | enum | yes | Confidence in the condition. |

Allowed `kind` values:

- `api_semantics`
- `input_capability`
- `execution_capability`

Recommended ID prefixes:

```text
required_capabilities → rc_
exclusion_conditions  → ec_
```

These fields describe semantic capabilities, not specific candidate target
APIs or executable predicates.

---

## 12. Heterogeneity

```json
"heterogeneity": {
  "member_differences": [],
  "unresolved_conflicts": []
}
```

### 12.1 Member Difference

```json
{
  "difference_id": "md_01",
  "dimension": "mechanism",

  "statement": "The member Patterns reach different backend implementation paths.",

  "affected_pattern_ids": [
    "pt_conv2d_storage_boundary_p001",
    "pt_matmul_unaligned_storage_p001"
  ],

  "significance": "material",
  "evidence_status": "cross_pattern_derived",

  "evidence_refs": [
    "pattern:pt_conv2d_storage_boundary_p001:defect_mechanism",
    "pattern:pt_matmul_unaligned_storage_p001:defect_mechanism"
  ],

  "confidence": "medium"
}
```

Allowed `dimension` values:

- `api_semantics`
- `risk_boundary`
- `trigger`
- `mechanism`
- `execution`
- `failure`
- `applicability`
- `evidence_quality`

Allowed `significance` values:

- `minor`
- `material`

### 12.2 Unresolved Conflict

```json
{
  "conflict_id": "uc_01",
  "impact": "applicability",

  "statement": "The available evidence disagrees on whether the risk requires backend-specific execution.",

  "affected_pattern_ids": [
    "pattern_a",
    "pattern_b"
  ],

  "evidence_status": "cross_pattern_derived",

  "evidence_refs": [
    "pattern:pattern_a:execution_context",
    "pattern:pattern_b:execution_context"
  ],

  "confidence": "medium",
  "resolution_status": "open"
}
```

Allowed `impact` values:

- `membership`
- `family_core`
- `applicability`
- `generalization`

Allowed `resolution_status` values:

- `open`
- `deferred`

Resolved conflicts are removed from `unresolved_conflicts` and described in the
revision `change_summary`.

Recommended ID prefixes:

```text
member_differences    → md_
unresolved_conflicts  → uc_
```

---
## 13. Support

```json
"support": {
  "supporting_apis": [
    "torch.conv2d",
    "torch.matmul"
  ],

  "pattern_count": 2,
  "distinct_api_count": 2,
  "independent_report_count": 2,

  "support_tier": "emerging",

  "tier_rationale": "The Family is supported by two APIs and two independent historical Reports."
}
```

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `supporting_apis` | array | yes | Sorted, de-duplicated member primary APIs. |
| `pattern_count` | integer | yes | Number of final member Patterns. |
| `distinct_api_count` | integer | yes | Number of distinct member primary APIs. |
| `independent_report_count` | integer | yes | Number of independent historical Report or Issue sources. |
| `support_tier` | enum | yes | Deterministically derived evidence-support tier. |
| `tier_rationale` | string | yes | Deterministic explanation of the counts, ceiling, final tier, and applied caps. |

Allowed `support_tier` values:

- `emerging`
- `corroborated`
- `broadly_supported`

All fields in `support` are generated by the conversion script after the
proposed Family has passed validation.

The LLM or analyst must not directly output or modify these fields.

### 13.1 Deterministic Counts

The conversion script calculates:

- `supporting_apis` from sorted and de-duplicated member `primary_api` values;
- `pattern_count` from the final accepted member set;
- `distinct_api_count` from distinct member `primary_api` values;
- `independent_report_count` from distinct underlying historical Report or
  Issue sources.

Multiple Patterns extracted from the same Report count as one independent
source.

Duplicate copies of the same Issue count as one independent source.

### 13.2 Count-based Ceiling

| Tier | Minimum Patterns | Minimum APIs | Minimum independent Reports |
| --- | --- | --- | --- |
| `emerging` | 2 | 2 | 2 |
| `corroborated` | 3 | 3 | 3 |
| `broadly_supported` | 5 | 4 | 5 |

The count-based ceiling is the highest tier whose three numerical thresholds
are all satisfied.

A proposed Family that does not satisfy the `emerging` thresholds is invalid
and must not be materialized.

### 13.3 Deterministic Qualitative Caps

A Family may receive `corroborated` only when:

- membership confidence is `medium` or `high`;
- commonality confidence is `medium` or `high`;
- no open material conflict affects membership or the Family core.

A Family may receive `broadly_supported` only when:

- membership confidence is `high`;
- commonality confidence is `high`;
- generalization confidence is `medium` or `high`;
- no open material conflict exists;
- the Family core is not based solely on `analyst_inferred` evidence;
- no low-confidence member materially supports the Family core.

The conversion script selects the highest tier satisfying both the count-based
ceiling and the qualitative requirements.

### 13.4 Tier Rationale

The conversion script generates `tier_rationale`.

It records:

- Pattern count;
- distinct API count;
- independent Report count;
- count-based ceiling;
- final assigned tier;
- every qualitative condition that caused a lower tier.

The script must not request or copy an LLM-generated tier rationale.
---

## 14. Family-level Confidence

```json
"confidence": {
  "membership": "medium",
  "commonality": "medium",
  "applicability": "low",
  "generalization": "low"
}
```

| Field | Type | Required | Description |
|---|---|---:|---|
| `membership` | enum | yes | Confidence that the selected members belong together. |
| `commonality` | enum | yes | Confidence in the Family core and shared characteristics. |
| `applicability` | enum | yes | Confidence in the applicability conditions. |
| `generalization` | enum | yes | Confidence that the Family can support later General Knowledge. |

These confidence dimensions are independent.

---

## 15. Controlled Enums

### 15.1 Evidence Status

Allowed values:

- `pattern_explicit`
- `cross_pattern_derived`
- `analyst_inferred`
- `unknown`

Definitions:

- `pattern_explicit`: directly represented in cited Pattern fields;
- `cross_pattern_derived`: abstracted across cited Pattern evidence without
  introducing a new historical fact;
- `analyst_inferred`: reasoned interpretation based on cited Pattern evidence;
- `unknown`: evidence status cannot be reliably assigned.

### 15.2 Confidence

Allowed values:

- `high`
- `medium`
- `low`

`null` may appear only before a value has been assigned.

### 15.3 Validation Status

Allowed values:

- `not_reviewed`
- `automatically_validated`
- `human_verified`
- `needs_revision`

### 15.4 Support Tier

Allowed values:

- `emerging`
- `corroborated`
- `broadly_supported`

---

## 16. Field-source Summary

The conversion script supplies deterministic metadata, including:

- IDs and hashes;
- framework;
- revision metadata;
- provenance versions and hashes;
- source Decision Record identity, file hash, and analysis-input hash;
- generation time;
- member API and Report metadata;
- local IDs;
- supporting API values;
- support counts;
- support tier;
- support-tier rationale;
- validation status.

The LLM or analyst proposes semantic and decision content, including:

- canonical name;
- membership rationale;
- Family core;
- shared characteristics;
- applicability conditions;
- differences and conflicts;
- evidence status and references;
- confidence values;
- the proposed relationship to explicitly supplied existing Families.

The proposed existing-Family relationship is not copied directly into the
final Family JSON. The conversion script materializes it through
`revision_information`, Family identity allocation, revision allocation, and
parent Family references.

Human review supplies:

- reviewer;
- review time;
- review notes;
- final `human_verified` status.