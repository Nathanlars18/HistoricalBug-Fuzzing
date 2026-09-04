# Pattern-Family-to-General-Knowledge Rules v1.0

## 1. Task and Source Model

This document defines how one validated Pattern Family revision and its member
API-specific Knowledge records are mapped to one General Knowledge candidate.

```text
One validated Pattern Family revision
        +
One API-specific Knowledge record for every Family member Pattern
        ↓
One General Knowledge candidate
```

The Pattern Family is the primary derivation source. It establishes:

- why the member Patterns belong together;
- the shared historical risk basis;
- cross-API commonality;
- member differences and conflicts;
- applicability and generalization boundaries.

The member Knowledge records are supporting guidance sources. They provide:

- reusable testing objectives;
- applicability information;
- exploration goals;
- Oracle observation guidance;
- API-specific evidence limitations.

General Knowledge combines these two roles into one cross-API reusable testing
principle.

The output structure, controlled values, cardinality, and content boundary are
defined by `general_knowledge_extraction_contract.json`.

The final persisted record is defined by `general_knowledge_schema.md`.

Do not create multiple General Knowledge candidates from one Family.

If the Family appears to contain multiple independent principles that cannot be
represented coherently in one record, return `needs_revision` and request
upstream Family review.

---

## 2. Source Authority and Evidence Use

### 2.1 Source authority

The Pattern Family governs:

- membership;
- sharedness;
- the common risk basis;
- cross-API generalization;
- Family-level applicability;
- material member differences and conflicts.

The member Knowledge records govern:

- testing-principle phrasing;
- exploration guidance;
- applicability details;
- Oracle guidance;
- Knowledge-level limitations.

A member Knowledge record must not replace, broaden, or contradict the Pattern
Family core.

If a material Knowledge claim conflicts with the Family core, return
`needs_revision` rather than choosing one interpretation.

### 2.2 Member-to-Knowledge correspondence

Every Family member Pattern must be represented by exactly one supplied
API-specific Knowledge record.

The Knowledge record's `source_pattern_id` must identify that Family member.

A Knowledge record that does not correspond to a current Family member must not
be used.

All member Knowledge records must be considered during extraction.

`supporting_knowledge` contains the Knowledge records that materially support
the resulting General Knowledge. An accepted result requires at least two such
records associated with at least two distinct Family member APIs.

A Knowledge record may be omitted from `supporting_knowledge` when it adds no
material support beyond other compatible records.

If omission reflects a material difference, conflict, or scope restriction,
preserve that information as a limitation.

### 2.3 No evidence double counting

The Pattern Family and its member Knowledge records are derived views of
overlapping underlying Pattern evidence.

They must not be counted as independent historical evidence merely because the
same claim appears in both artifact types.

The Pattern Family establishes the historical cross-API evidence basis.

The member Knowledge records establish whether compatible reusable testing
guidance can be synthesized from that basis.

The minimum supporting-Knowledge requirement is a guidance-consistency
requirement. It does not create additional independent Bug evidence.

### 2.4 Evidence references

The General Knowledge core must cite Pattern Family evidence.

Testing guidance may cite Family evidence, Knowledge evidence, or both,
according to the actual source of the claim.

Every reference must resolve to the supplied Family revision or one of its
supplied member Knowledge records.

Do not cite Reports, Issues, commits, pull requests, or Patterns directly.

---

## 3. Decision Rules

### 3.1 Accept

Use `accept` only when all of the following hold:

1. One valid Family revision and one usable Knowledge record for every Family
   member are available.
2. The Family supports one coherent cross-API risk principle.
3. At least two Knowledge records from at least two distinct member APIs
   materially support compatible testing guidance.
4. The proposed principle remains compatible with every Family member.
5. A defensible testing objective can be stated.
6. At least one evidence-grounded applicability condition can be stated.
7. At least one useful retrieval tag can be derived.
8. At least one evidence-grounded exploration goal can be stated.
9. Material differences, boundaries, and evidence gaps are preserved as
   limitations.
10. No unresolved conflict invalidates the common principle or applicability
    boundary.
11. Every nontrivial claim can be traced to supplied evidence.

Oracle guidance is optional.

`failure_relevance` may be `null` when no reliable shared failure connection is
supported.

The accepted core Knowledge statement must not use `unknown`.

### 3.2 Needs revision

Use `needs_revision` when a defensible General Knowledge record would require:

- a missing or invalid member Knowledge record;
- fewer than two supporting APIs;
- reliance on a principle present in only one member;
- choosing between materially contradictory sources;
- inventing an applicability boundary;
- inventing an exploration goal;
- unsupported cross-API generalization;
- unavailable or inconsistent evidence references;
- splitting or revising the source Pattern Family.

Each unresolved issue must identify:

- the blocking problem;
- related evidence when available;
- the required upstream correction or review.

`needs_revision` means that no final General Knowledge record should be
materialized from the current inputs.

---

## 4. General Knowledge Synthesis

### 4.1 Common-core rule

General Knowledge represents the smallest useful testing principle that remains
valid across the Pattern Family.

Do not copy the union of all member Knowledge statements.

Do not generalize a property found in only one member unless the Pattern Family
independently establishes it as part of the shared core.

Compatible member guidance may be combined when it describes complementary
aspects of the same Family-level risk.

Independent testing principles must not be forced into one record.

Cross-API applicability must be expressed through semantic properties, not API
name similarity, module proximity, documentation similarity, or superficially
similar signatures.

### 4.2 Field synthesis

| Output field | Synthesis rule |
| --- | --- |
| `canonical_name` | Name the reusable cross-API testing principle, not a source API, Family ID, Bug ID, or historical failure instance. |
| `family_evidence_refs` | Select Family fields establishing the common risk, applicability, or material heterogeneity. |
| `supporting_knowledge` | Select member Knowledge records materially contributing compatible testing guidance. |
| `derivation_rationale` | Explain how the Family core and member guidance support one General Knowledge principle. |
| `limitations` | Preserve material differences, conflicts, applicability boundaries, evidence gaps, and support boundaries. |
| `risk_principle` | State the reusable cross-API risk supported by the Family. |
| `testing_objective` | State what later testing should explore or observe at a high level. |
| `failure_relevance` | State a shared historically relevant failure connection when supported; otherwise use `null`. |
| `retrieval_tags` | Derive stable semantic tags from the shared risk, required capabilities, and risk dimensions. |
| `applicability_conditions` | State semantic prerequisites for considering the Knowledge for another API. |
| `exclusion_conditions` | State known semantic conditions under which the Knowledge should not be selected. |
| `applicability.rationale` | Explain how the applicability boundary follows from the supplied evidence. |
| `exploration_goals` | Synthesize the smallest useful set of compatible high-level testing directions. |
| `oracle_guidance` | Preserve or cautiously generalize evidence-supported observation targets. |
| `confidence` | Reassess support for the General Knowledge; do not copy source confidence mechanically. |

### 4.3 Applicability and retrieval

Applicability conditions describe required:

- API semantics;
- input capabilities;
- execution capabilities.

They must not name unverified target APIs.

Known semantic incompatibility belongs in `exclusion_conditions`.

Missing evidence, uncertain applicability, untested environments, and incomplete
support belong in `limitations`, not exclusion conditions.

Retrieval tags must describe stable semantic concepts. Do not use source
artifact IDs or arbitrary API names as retrieval tags.

A retrieval match means only that later HarnessSpec construction may consider
the General Knowledge. It does not prove applicability to the target API.

### 4.4 Exploration and Oracle guidance

Exploration goals must remain anchored in the Family core and compatible member
Knowledge guidance.

Do not copy every member goal automatically.

Use `primary` for goals central to the shared risk.

Use `secondary` for narrower but compatible supporting directions.

Each goal targets exactly one risk dimension.

Use `historical_observable` only when the observation is directly supported as
historically relevant by the supplied evidence.

Use `derived_oracle_candidate` for a cautious abstraction of compatible
observation guidance that is not directly established as one shared historical
observable.

A derived Oracle candidate must use `analyst_inferred` and must not use `high`
confidence.

Do not merge incompatible failure observations into one Oracle.

When no reliable Oracle guidance exists, return an empty `oracle_guidance`
array.

---

## 5. Differences, Evidence Status, and Confidence

### 5.1 Differences and limitations

Use limitation kinds as follows:

| Limitation kind | Use |
| --- | --- |
| `member_difference` | A member difference that narrows or qualifies the common principle. |
| `unresolved_conflict` | A contradiction that remains visible but does not invalidate the accepted core. |
| `applicability_boundary` | A semantic boundary limiting possible application. |
| `evidence_gap` | Missing, incomplete, or weak source evidence. |
| `support_boundary` | Narrow support across APIs, backends, devices, execution modes, or related dimensions. |

A difference does not automatically require `needs_revision`.

Use a limitation when the shared principle remains defensible.

Use `needs_revision` when a conflict affects:

- whether the members share the same risk;
- the meaning of the testing objective;
- the minimum applicability conditions;
- whether the principle is genuinely cross-API.

Do not hide a material conflict by lowering confidence without recording the
conflict or limitation.

### 5.2 Evidence status

Use evidence status according to the origin of the specific claim:

| Evidence status | Meaning |
| --- | --- |
| `family_explicit` | Directly represented in the supplied Pattern Family. |
| `family_derived` | Derived from Family evidence and compatible member Knowledge evidence. |
| `analyst_inferred` | Requires a cautious interpretation beyond explicit or direct derivation. |
| `unknown` | No reliable positive claim is made. |

`analyst_inferred` is allowed only when it:

- cites supporting evidence;
- remains within the source evidence boundary;
- is stated cautiously;
- obeys the Contract confidence restrictions.

Do not use `family_explicit` for a claim appearing only in member Knowledge.

Do not use `family_derived` merely because a claim appears plausible.

### 5.3 Confidence

Assess confidence dimensions separately:

| Confidence field | Assessment target |
| --- | --- |
| `evidence_confidence` | Completeness, consistency, independence, and traceability of the underlying historical evidence. |
| `abstraction_confidence` | Strength of the common cross-API testing principle. |
| `applicability_confidence` | Strength and clarity of applicability and exclusion boundaries. |
| `oracle_guidance_confidence` | Consistency and historical support of Oracle guidance. |
| `generalization_confidence` | Support for considering the principle beyond directly supported APIs. |

Use:

- `high` only for direct, consistent, sufficiently broad evidence without
  material unresolved conflict;
- `medium` for evidence-supported conclusions requiring bounded abstraction;
- `low` for narrow support, incomplete evidence, substantial inference,
  unresolved boundaries, or missing optional guidance.

Do not increase confidence because the same underlying claim appears in both
the Pattern Family and member Knowledge artifacts.

Do not mechanically convert Family support tier into a confidence value.

The minimum two-API supporting-Knowledge requirement does not justify `high`
confidence by itself.

`generalization_confidence` must not exceed the source Family generalization
confidence.

If Oracle guidance is empty, `oracle_guidance_confidence` must be `low`.

All other evidence-status and confidence relationships must satisfy the
Contract.

---

## 6. Output Rule

Return only the JSON object defined by
`general_knowledge_extraction_contract.json`.

Use only the supplied Family revision, member Knowledge records, and allowed
evidence references.

All generated content must respect the Contract content boundary.

Do not emit fields absent from the Contract response template.

Do not leave template placeholders in required non-null fields.

Deterministic identifiers, provenance, revision information, scope, support,
review state, fixed relations, local element IDs, and derived risk dimensions
are added by the conversion script.