# API-specific Patterns to Pattern Family Rules v1.2


```text
rules_version: 1.2
rules_status: provisional
source_pattern_schema_version: 2.0
target_family_schema_version: 1.1
target_contract_version: 1.1
```

## 1. Purpose and Boundary

Analyze one Pattern Family Candidate Manifest and its complete API-specific
Pattern records, then return:

- `accept`
- `split`
- `reject`
- `needs_revision`

Candidate Manifest signals are retrieval evidence only. They do not prove
Family membership.

All Family claims must be supported by the provided validated
family-analysis Pattern projections.

Every cited value must resolve to an exact field in the corresponding immutable
member Pattern record.

Do not generate:

- General Knowledge;
- testing strategies;
- executable predicates;
- Oracles;
- HarnessSpec;
- Harness code;
- claims about unobserved target APIs.

---

## 2. Decision Rules

| Decision | Use when |
|---|---|
| `accept` | Exactly one defensible Family can be formed. Candidate outliers may be excluded. |
| `split` | Two or more distinct, defensible Families can be formed from different or overlapping member subsets. |
| `reject` | Available evidence is sufficient to show that no defensible Family can be formed. |
| `needs_revision` | Missing, malformed, inconsistent, or insufficient evidence prevents a reliable decision. |

Use `reject` when the evidence supports a negative decision.

Use `needs_revision` when the evidence is not sufficient to make a reliable
positive or negative decision.

For `accept` and `split`, every Candidate Pattern must appear in at least one
proposed Family or in `excluded_patterns`.

For `reject`, every Candidate Pattern must appear in `excluded_patterns`.

---

## 3. Family Formation Rules

Every proposed Family must contain:

```text
at least 2 Patterns
at least 2 distinct primary APIs
at least 2 independent Report or Issue sources
exactly 1 framework
exactly 1 evidence-grounded Family core
```

Independent sources are counted by underlying historical Report or Issue.

Therefore:

- multiple Patterns from one Report count as one source;
- duplicated copies of one Issue count as one source;
- one Issue appearing in multiple datasets counts as one source.

The Family core must apply to every member.

The following similarities cannot independently establish a Family:

- similar API names or signatures;
- similar parameter counts;
- all APIs accepting Tensor inputs;
- framework equality;
- broad backend or device equality;
- failure-type equality;
- Oracle-kind equality;
- exception-message similarity;
- Candidate Manifest graph connectivity;
- Candidate Manifest strong or weak signal labels;
- one broad defect class;
- unsupported `candidate_family_tags`.

A failure observable cannot be the only basis of a Family core.

---

## 4. Membership Rules

Include a Pattern only when:

1. its exact Pattern record is available;
2. its ID and hash match the Candidate Manifest;
3. its evidence supports the proposed Family core;
4. its membership rationale explains its Pattern-specific connection to the
   core;
5. its membership cites evidence from that Pattern;
6. its inclusion does not create an unresolved material membership or core
   conflict.

A valid membership rationale connects the Pattern through one or more of:

- risk boundary;
- trigger semantics;
- mechanism semantics;
- execution semantics;
- failure behavior combined with another supported basis.

Do not include a Pattern solely because it shares:

- a retrieval signal;
- a defect label;
- a failure type;
- an Oracle kind;
- a `candidate_family_tag`.

Exclude a Pattern when:

- it does not support the Family core;
- it is connected only through chain drift;
- its evidence contradicts the core;
- including it would require overgeneralization;
- its evidence is insufficient for membership;
- it belongs only to another Family produced by `split`.

Every exclusion must contain a reason and supporting evidence references when
available.

Preserve uncertainty from the source Pattern. A hypothetical mechanism must not
be rewritten as a confirmed fact.

---

## 5. Family Core Rules

The Family core is the narrowest evidence-grounded statement that meaningfully
applies to every member.

Allowed basis types are:

- `risk_boundary`
- `trigger_semantics`
- `mechanism_semantics`
- `execution_semantics`
- `failure_observable`

At least one basis type is required.

`failure_observable` cannot be used alone.

The Family core must:

- apply to every member;
- cite evidence contributed by every member;
- distinguish common semantics from member-specific details;
- avoid unsupported universal claims;
- preserve uncertainty;
- avoid claiming an identical root cause unless all members support it;
- avoid claiming identical trigger values unless all members support them;
- avoid naming unobserved target APIs;
- avoid concrete testing or Harness instructions.

`shared_defect_classes` and `shared_risk_dimensions` may be empty when the core
is supported through trigger, mechanism, or execution evidence.

Do not invent a broad shared classification merely to avoid an empty array.

The core normally uses `cross_pattern_derived`.

Use `analyst_inferred` only when an explicit semantic bridge is required.

Use `pattern_explicit` only when the same relevant claim is explicitly
represented in every cited Pattern.

---

## 6. Shared Characteristic Rules

Allowed characteristic groups are:

- `trigger_semantics`
- `mechanism_semantics`
- `execution_semantics`
- `failure_observables`

Each shared characteristic must:

- be supported by at least 2 member Patterns;
- be supported by at least 2 distinct APIs;
- list its exact supporting Pattern IDs;
- cite evidence from every listed Pattern;
- preserve source uncertainty.

A characteristic may be supported by all members or by a subset.

A subset-supported characteristic:

- is not automatically part of the Family core;
- must not be generalized to unsupported members;
- must not hide a contradiction with other members.

A property supported by only one Pattern remains member-specific and is not a
shared Family characteristic.

Historical failure observables do not automatically become executable Oracles.

Do not include concrete inputs, mutations, predicates, strategies, or code.

---

## 7. Applicability Rules

`required_capabilities` describes semantic capabilities that must exist before
the Family could be relevant to another API.

`exclusion_conditions` describes evidence-supported conditions under which the
Family should not be applied.

Allowed condition kinds are:

- `api_semantics`
- `input_capability`
- `execution_capability`

Each condition must:

- be supported by member Pattern evidence;
- identify its supporting Pattern IDs;
- remain at the semantic level;
- avoid naming predicted target APIs;
- avoid executable implementation details;
- avoid claiming that applicability proves transferability.

A Family-level applicability condition should normally be supported by at
least two Patterns from at least two APIs.

A property observed in only one member remains member-specific unless a
cross-Pattern inference is explicitly justified and marked
`analyst_inferred`.

Missing evidence is not an exclusion condition.

Do not infer:

```text
The Family excludes X
```

only because no source Pattern mentions X.

---

## 8. Heterogeneity and Conflict Rules

Use `member_differences` for known variations that do not invalidate the
Family.

Allowed difference dimensions are:

- `api_semantics`
- `risk_boundary`
- `trigger`
- `mechanism`
- `execution`
- `failure`
- `applicability`
- `evidence_quality`

Difference significance is:

- `minor`
- `material`

Use `unresolved_conflicts` when member evidence cannot currently be reconciled.

Allowed conflict impacts are:

- `membership`
- `family_core`
- `applicability`
- `generalization`

An open material conflict affecting `membership` or `family_core` blocks that
member combination from `accept`.

The analysis must then:

- exclude a conflicting Pattern;
- split the Candidate group;
- reject it;
- or return `needs_revision`.

An unresolved conflict affecting only `applicability` or `generalization` may
remain when:

- the Family core remains valid;
- the conflict is explicitly recorded;
- the affected confidence is reduced.

The model must explicitly record the conflict and reduce the affected confidence
dimension when required.

The model must not output or modify deterministic support metadata.

A top-level `unresolved_issue` prevents reliable Family creation.

A Family-level `unresolved_conflict` preserves a nonblocking uncertainty inside
an otherwise valid Family.

---

## 9. Split and Overlap Rules

Use `split` only when every resulting Family independently satisfies all Family
formation requirements.

Do not split solely by:

- renaming the same core;
- changing wording without changing semantics;
- API name;
- arbitrary member division;
- creating a single-Pattern Family.

Two proposed Families must differ materially in at least one of:

- Family core;
- basis types;
- risk boundary;
- trigger semantics;
- mechanism semantics;
- execution semantics;
- applicability.

If two proposals have essentially the same members, core, evidence basis, and
applicability, merge them.

A Pattern may belong to multiple Families only when:

- each Family has a distinct core;
- each membership has an independent rationale;
- each membership cites relevant Pattern evidence;
- the Families are not semantic duplicates.

A Pattern appearing in more than two Families is allowed but must be
prioritized for human review.

---

## 10. Evidence Rules

Evidence references use:

```text
pattern:{pattern_id}:{field_path}
```

Family evidence may cite only fields from provided member Pattern records.

The following are not historical Family evidence:

- Candidate Manifest similarity alone;
- pairwise-link status;
- graph connectivity;
- candidate warnings;
- unsupported LLM summaries;
- unsupported `candidate_family_tags`;
- raw Issue content not preserved in the Pattern records.

A Family claim must not be stronger than its source Pattern evidence.

Therefore:

- unknown Pattern information must not become a confirmed Family fact;
- analyst-inferred Pattern information must not become pattern-explicit Family
  evidence;
- one member’s confirmed fact must not be generalized to all members;
- absence of evidence must not become negative evidence;
- multiple low-confidence claims do not automatically become high confidence.

Allowed Family evidence statuses are:

- `pattern_explicit`
- `cross_pattern_derived`
- `analyst_inferred`

An accepted proposed Family must not use `unknown`.

If required evidence remains unknown:

- omit the claim when optional;
- record a nonblocking conflict when appropriate;
- or return `needs_revision` when it blocks Family formation.

---

## 11. Deterministic Metadata Boundary

The LLM must not output:

- `supporting_apis`;
- `pattern_count`;
- `distinct_api_count`;
- `independent_report_count`;
- `support_tier`;
- `tier_rationale`;
- a formal Family ID;
- a revision number;
- a file name;
- an output path;
- a Family hash.

These values are generated deterministically by the conversion script after the
Decision output has passed validation.

The exact support-tier thresholds and materialization rules are not part of the
LLM Prompt. They are defined by the final Pattern Family Schema and implemented
by the versioned conversion script.

---

## 12. Confidence Rules

Allowed values are:

- `high`
- `medium`
- `low`

### 12.1 Claim-level Confidence

Assign `high` when:

- evidence is direct and consistent;
- all cited Patterns support the claim;
- no material contradiction exists;
- little unsupported inference is required.

Assign `medium` when:

- evidence reasonably supports the claim;
- some abstraction is required;
- incomplete evidence does not invalidate the claim.

Assign `low` when:

- evidence is limited;
- substantial inference is required;
- evidence quality varies materially;
- unresolved nonblocking uncertainty remains.

A claim with `analyst_inferred` evidence cannot have `high` confidence.

### 12.2 Family-level Confidence

`membership` reflects whether the selected Patterns belong together.

`commonality` reflects the strength of the Family core and shared
characteristics.

`applicability` reflects the support for required capabilities and exclusions.

`generalization` reflects whether the Family can support later General
Knowledge.

Apply the following constraints:

- if any member has low membership confidence, Family membership cannot be
  `high`;
- an `analyst_inferred` Family core cannot have high commonality;
- an open material applicability conflict requires low applicability;
- an open material generalization conflict requires low generalization;
- a proposed Family supported by fewer than 3 Patterns, 3 distinct APIs, or
  3 independent Reports cannot have `high` generalization confidence;
- `low` generalization confidence does not invalidate an otherwise valid
  Family.

Confidence is based on evidence quality and consistency, not wording quality or
member count alone.

---

## 13. Existing-Family Lineage Rules

`lineage` describes the semantic relationship between one proposed Family and
the formal Pattern Family revisions explicitly provided in the current analysis
input.

Lineage is not historical Bug evidence.

It must not be used to establish:

- Family membership;
- the Family core;
- shared characteristics;
- applicability conditions;
- confidence.

The model may reference only existing Family IDs explicitly supplied in the
current analysis input.

The model must not generate:

- a new Family ID;
- a Family sequence number;
- a revision number;
- a file name;
- an output path;
- a Family hash;
- a local characteristic or condition ID.

Use the lineage actions according to the following semantic meanings:

| Action | Use when |
|---|---|
| `create_new` | No supplied existing Family represents the same semantic Family identity. |
| `reuse_existing` | The proposal is semantically equivalent to one supplied existing Family and does not require a new revision. |
| `update_existing` | The proposal preserves one existing Family identity but its members, evidence, scope, conflicts, or confidence must change. |
| `derive_new` | The proposal is a distinct new Family related to one or more existing Families without replacing them. |
| `merge_existing` | Two or more supplied existing Families are evidence-supported fragments of one unified Family. |
| `split_existing` | One supplied existing Family contains multiple independent Family cores and the proposal is one resulting child. |

A top-level `split` decision does not automatically imply `split_existing`.

For example, one new Candidate may contain two independent Families that both
use `create_new`.

Use `split_existing` only when a supplied formal Family is itself being divided.

Use `merge_existing` only when the supplied parent Families should be replaced
semantically by one unified Family.

If no relevant existing Family is supplied, the model must not invent an
existing Family ID.

In that case, use:

- `create_new`, when the new Family is independently defensible; or
- `needs_revision`, when missing existing-Family context prevents a reliable
  lineage decision.

Every lineage rationale must explain the semantic relationship.

The structural requirements for target and parent Family IDs are defined only
by `pattern_family_extraction_contract.json`.

Formal Family identity, revision, parent references, and output files are
assigned by the conversion script after validation.