# Historical Bug-Aware HarnessSpec Schema v1.0

## 1. Purpose

A HarnessSpec is a structured, target-API-specific testing plan produced after
API-specific Knowledge and General Knowledge have been retrieved, assessed, and
resolved.

It records:

- the target API and capability context;
- the final decision for each candidate Knowledge record;
- material relationships and resolutions among multiple Knowledge records;
- validity, safety, and environment constraints;
- semantic exploration branches and their execution-budget shares;
- runtime activation and Oracle requirements;
- revision lineage, provenance, validation, and review information.

A HarnessSpec defines **what** a generated Harness should explore, preserve,
activate, and observe.

It does not define **how** Helper functions or Strategy Primitives implement the
plan.

It must not contain:

- full Bug Reports, Patterns, Pattern Families, or Knowledge records;
- full API documentation;
- Helper source code or concrete Helper calls;
- Strategy Primitive implementations;
- C++ Harness code;
- actual fuzzing results or crash-analysis records;
- feedback-update thresholds or policies;
- hidden LLM reasoning or chain-of-thought.

Selection, relationship-resolution, branch-construction, budget-allocation, and
feedback-update policies belong in separate Rules or Policy documents.

---

## 2. Record Scope

One HarnessSpec record represents:

```text
one framework
+
one target API
+
one experimental mode
+
one stable HarnessSpec identity
+
one immutable semantic revision
```

One HarnessSpec revision may contain multiple exploration branches.

Static and adaptive HarnessSpecs use the same schema. Feedback-driven semantic
changes create a new revision rather than overwriting the previous revision.

Administrative lifecycle metadata may change without changing the semantic
content of a revision.

The original external FlashFuzz baseline does not have to use this schema. A
controlled no-Knowledge baseline may use it when identical synthesis and
execution infrastructure is required across experimental groups.

---

## 3. Top-Level Structure

| Field | Type | Required | Purpose |
| --- | --- | --- | --- |
| `schema_version` | string | yes | HarnessSpec record-format version |
| `identity` | object | yes | Stable identity and experimental mode |
| `revision_information` | object | yes | Same-Spec revision chain and cross-Spec origin |
| `target_context` | object | yes | Target API and capability context |
| `knowledge_plan` | object | yes | Candidate decisions and multi-Knowledge resolutions |
| `validity_constraints` | object | yes | Constraints shared by all branches |
| `exploration_plan` | object | yes | Semantic branches and budget shares |
| `provenance` | object | yes | Exact generation artifacts and run information |
| `review` | object | yes | Automatic validation and human review state |

---

## 4. General Conventions

### 4.1 Missing values

Use:

- `null` for an unavailable scalar or object value;
- `[]` when a list has no entries.

Do not use strings such as `"N/A"`, `"none"`, or `"null"` as missing values.

The enum value `unknown` is allowed only where explicitly defined.

### 4.2 Identifiers

Identifiers must be:

- non-empty;
- stable across references;
- normalized consistently;
- independent of timestamps and absolute file paths.

Internal references must resolve within the HarnessSpec. External artifact
references must resolve in the project artifact store.

### 4.3 Text

Required text fields must be concise and non-empty.

They must not contain source code, unsupported factual claims, complete source
records, or hidden model reasoning.

### 4.4 Semantic Requirement

A Semantic Requirement describes an implementation-independent predicate,
relation, or expected behavior.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `requirement_type` | string | yes | Normalized semantic predicate or relation |
| `parameters` | object | yes | Structured subjects, operands, and values |
| `description` | string or null | yes | Short clarification when necessary |

The controlled `requirement_type` vocabulary is defined by the machine-readable
contract.

---

## 5. Shared Reference Objects

### 5.1 Artifact Reference

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `artifact_id` | string | yes | Stable artifact identifier |
| `artifact_version` | integer, string, or null | yes | Exact artifact version when applicable |
| `content_hash` | string | yes | Hash of the referenced artifact content |

### 5.2 Knowledge Reference

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `knowledge_id` | string | yes | Stable Knowledge identifier |
| `revision` | integer | yes | Positive Knowledge revision number |
| `content_hash` | string | yes | Hash of the referenced Knowledge content |

### 5.3 HarnessSpec Revision Reference

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `spec_id` | string | yes | Stable HarnessSpec identifier |
| `revision_number` | integer | yes | Positive HarnessSpec revision number |

### 5.4 API Profile Reference

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `profile_id` | string | yes | Stable API Profile identifier |
| `revision` | integer | yes | Positive profile revision |
| `content_hash` | string | yes | Hash of the referenced profile content |

### 5.5 Helper Profile Reference

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `profile_id` | string | yes | Stable Helper Capability Profile identifier |
| `version` | string | yes | Exact profile version |
| `content_hash` | string | yes | Hash of the referenced profile content |

### 5.6 Source Reference

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `source_type` | enum | yes | Source artifact category |
| `source_id` | string | yes | Stable source identifier |
| `source_revision` | integer or string | yes | Exact source revision or version |
| `content_hash` | string | yes | Hash of the exact source content |

Allowed `source_type` values:

```text
api_profile
helper_profile
knowledge
```

Every Source Reference identifies an externally stored, versioned artifact. Its
`source_revision` and `content_hash` are therefore non-null in a final
HarnessSpec record.

---

## 6. `schema_version`

| Field | Type | Required | Allowed value |
| --- | --- | --- | --- |
| `schema_version` | string | yes | `"1.0"` |

`schema_version` describes the record format and is independent of the
HarnessSpec revision number.

---

## 7. `identity`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `spec_id` | string | yes | Stable HarnessSpec identifier |
| `framework` | string | yes | Target framework |
| `target_api` | string | yes | Canonical target API name |
| `spec_mode` | enum | yes | Experimental mode |

Allowed `spec_mode` values:

```text
controlled_baseline
bug_aware_static
bug_aware_adaptive
```

Meanings:

- `controlled_baseline`: uses the HarnessSpec infrastructure without historical Knowledge;
- `bug_aware_static`: uses historical Knowledge without execution-feedback-driven revision;
- `bug_aware_adaptive`: uses historical Knowledge and may receive execution-feedback-driven revisions.

All fields in `identity` remain unchanged across revisions of the same `spec_id`.

---

## 8. `revision_information`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `revision_number` | integer | yes | Positive revision number within the same `spec_id` |
| `parent_revision_ref` | HarnessSpec Revision Reference or null | yes | Immediate previous revision of the same HarnessSpec |
| `forked_from_spec_ref` | HarnessSpec Revision Reference or null | yes | Cross-Spec revision used to create revision 1 |
| `revision_trigger` | enum | yes | Event that caused this revision to be created |
| `change_scopes` | array of enums | yes | Structured sections changed from the parent or fork source |
| `change_summary` | string | yes | Concise human-readable change summary |
| `lifecycle_status` | enum | yes | Operational state of this revision |

Allowed `revision_trigger` values:

```text
initial_creation
cross_spec_derivation
manual_review
execution_feedback
source_artifact_update
regeneration
```

Allowed `change_scopes` values:

```text
initial_definition
knowledge_selection
relationship_resolution
global_constraints
branch_structure
branch_semantics
budget_allocation
activation_plan
oracle_plan
target_context
metadata_only
```

Allowed `lifecycle_status` values:

```text
draft
active
superseded
retired
```

Lineage semantics:

- revision 1 has `parent_revision_ref = null`;
- revision 2 or later points `parent_revision_ref` to the immediately preceding revision of the same `spec_id`;
- `forked_from_spec_ref` is allowed only on revision 1 and points to a different `spec_id`;
- later revisions trace their origin through the parent chain to revision 1, then through `forked_from_spec_ref` when present;
- `cross_spec_derivation` requires a non-null `forked_from_spec_ref`;
- `initial_creation` requires a null `forked_from_spec_ref`.

Change-scope semantics:

- changing only branch `budget_share` values is `budget_allocation`;
- adding, removing, splitting, or merging branches is `branch_structure`;
- changing a branch goal, target property, precondition, or constraint without changing the branch set is `branch_semantics`;
- changing candidate selection is `knowledge_selection`;
- changing only provenance, review, or other non-semantic metadata is `metadata_only`.

`change_scopes` should be computed by a deterministic structured diff whenever a
parent or fork source is available. It should not be inferred from free-form LLM
explanations.

Lifecycle semantics:

- `draft`: not approved for execution;
- `active`: approved current revision for its experimental run;
- `superseded`: replaced by a later active revision;
- `retired`: withdrawn without a replacement revision.

---

## 9. `target_context`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `api_profile_ref` | API Profile Reference | yes | Exact Target API Profile |
| `helper_profile_ref` | Helper Profile Reference | yes | Exact Helper Capability Profile |
| `framework_version` | string or null | yes | Framework version targeted by this revision |
| `backend_scope` | array of strings | yes | Backends covered by this HarnessSpec |

`backend_scope` uses normalized backend identifiers such as:

```text
cpu
cuda
mps
```

The API Profile owns the exact API signature, parameter roles, binding
information, and API-level constraints.

The Helper Profile owns available Helper capabilities and limitations.

Complete profile content is not copied into the HarnessSpec.

---

## 10. `knowledge_plan`

The `knowledge_plan` records the exact retrieved candidate set, the final
decision for each candidate, and material multi-Knowledge resolutions.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `candidate_manifest_ref` | Artifact Reference or null | yes | Exact candidate-retrieval manifest |
| `candidate_decisions` | array of Candidate Decision objects | yes | One final decision for each candidate Knowledge |
| `resolution_records` | array of Resolution Record objects | yes | Material relationships and their effects |

Full Knowledge content must not be embedded in this object.

### 10.1 Candidate Decision

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `knowledge_ref` | Knowledge Reference | yes | Exact candidate Knowledge revision |
| `knowledge_type` | enum | yes | API-specific or General Knowledge |
| `selection_status` | enum | yes | Final inclusion decision for this revision |
| `applicability_status` | enum | yes | Semantic applicability to the target API |
| `capability_status` | enum | yes | Implementability under the referenced Helper Profile |
| `reason_codes` | array of strings | yes | Normalized decision reasons |
| `decision_summary` | string | yes | Concise human-readable decision summary |
| `decision_confidence` | enum or null | yes | Confidence in the final combined decision |

Allowed `knowledge_type` values:

```text
api_specific
general
```

Allowed `selection_status` values:

```text
selected
deferred
rejected
```

Meanings:

- `selected`: contributes to the current HarnessSpec;
- `deferred`: may be useful, but is not used in this revision because evidence, capability, resolution, or budget remains pending;
- `rejected`: has been determined not applicable, not feasible, prohibited, or not worth retaining for this target.

Allowed `applicability_status` values:

```text
applicable
partially_applicable
not_applicable
unknown
```

Allowed `capability_status` values:

```text
supported
partially_supported
unsupported
unknown
```

Allowed non-null `decision_confidence` values:

```text
high
medium
low
```

`null` means that confidence could not be responsibly assessed.

The controlled `reason_codes` vocabulary belongs to the machine-readable
contract.

Branch contribution is recorded only through each branch's
`source_knowledge_ids`; it is not duplicated in Candidate Decision.

### 10.2 Resolution Record

A Resolution Record is created only when a relationship between two or more
Knowledge records materially affects selection, attribution, branch formation,
activation, or Oracle planning.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `resolution_id` | string | yes | Unique resolution identifier |
| `involved_knowledge_ids` | array of strings | yes | All Knowledge records involved |
| `relationship_type` | enum | yes | High-level semantic relationship |
| `interaction_dimensions` | array of enums | yes | Dimensions in which the relationship occurs |
| `resolution_effects` | array of Resolution Effect objects | yes | Structured effects of the resolution |
| `resolution_summary` | string | yes | Concise human-readable summary |

Allowed `relationship_type` values:

```text
duplicate
subsumption
partial_overlap
complementary
conflicting
```

Allowed `interaction_dimensions` values:

```text
lineage
applicability
validity_constraint
exploration_goal
target_property
helper_capability
backend_scope
activation_requirement
oracle_requirement
```

An independent relationship does not require a Resolution Record.

### 10.3 Resolution Effect

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `effect_id` | string | yes | Unique effect identifier within the resolution |
| `effect_type` | enum | yes | Machine-readable resolution outcome |
| `target_knowledge_ids` | array of strings | yes | Knowledge records to which this effect applies |
| `result_branch_ids` | array of strings | yes | Branches created or affected by this effect |

Allowed `effect_type` values:

```text
merge_into_branch
separate_into_branches
keep_separate
prefer_candidates
deduplicate_contribution
defer_candidates
reject_candidates
```

Multiple effects may appear in one Resolution Record. For example, overlapping
Knowledge may be merged into one branch while shared lineage contributions are
also de-duplicated.

---

## 11. `validity_constraints`

The `validity_constraints` object contains requirements that must hold for every
exploration branch in this revision.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `global_constraints` | array of Constraint objects | yes | Constraints shared by all branches |

Branch-specific constraints belong in the corresponding Exploration Branch.

### 11.1 Constraint Object

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `constraint_id` | string | yes | Unique constraint identifier |
| `constraint_kind` | enum | yes | Semantic constraint category |
| `constraint_role` | enum | yes | Why the constraint must be preserved |
| `subjects` | array of strings | yes | API parameters or contextual objects constrained |
| `semantic_requirement` | Semantic Requirement | yes | Implementation-independent condition |
| `source_refs` | array of Source References | yes | Sources supporting the constraint |
| `verification_status` | enum | yes | Evidence status |

Allowed `constraint_kind` values:

```text
shape_relation
rank
dtype
device
layout
argument_relation
backend
resource
api_precondition
```

Allowed `constraint_role` values:

```text
api_validity
safety_guardrail
environment_requirement
```

Allowed `verification_status` values:

```text
confirmed
inferred
unresolved
```

Every listed Constraint is mandatory for its scope. A condition intentionally
violated by an `intentionally_invalid` branch is represented as a Target
Property, not as a Constraint of that branch.

---

## 12. `exploration_plan`

The `exploration_plan` defines the semantic testing branches that the Strategy
layer must implement.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `default_branch_id` | string | yes | Canonical default valid-input branch |
| `branches` | array of Exploration Branch objects | yes | Branches executed by this revision |

`default_branch_id` equals the `branch_id` of the unique branch whose
`branch_kind` is `default`. It is derived deterministically from `branches` and
is not an independent planning decision.

Only branches that participate in the current revision are stored. A removed or
disabled branch remains traceable through the parent revision and is not kept as
a zero-budget branch in the current revision.

### 12.1 Exploration Branch

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `branch_id` | string | yes | Unique branch identifier |
| `branch_kind` | enum | yes | Default, generic, or Knowledge-directed branch |
| `input_validity_intent` | enum | yes | Intended validity class of generated inputs |
| `source_knowledge_ids` | array of strings | yes | Selected Knowledge supporting the branch |
| `exploration_goal` | string | yes | Concise semantic testing objective |
| `risk_dimensions` | array of strings | yes | Controlled risk dimensions covered |
| `target_properties` | array of Target Property objects | yes | Structured states intentionally explored |
| `branch_preconditions` | array of Branch Precondition objects | yes | Conditions gating entry into this branch |
| `branch_constraints` | array of Constraint objects | yes | Conditions that must hold throughout this branch |
| `budget_share` | number | yes | Relative execution-budget share in `[0, 1]` |
| `activation_targets` | array of Activation Target objects | yes | Runtime evidence that the intended path occurred |
| `activation_logic` | enum | yes | Combination rule for activation targets |
| `oracle_requirements` | array of Oracle Requirement objects | yes | Semantic observations required or preferred |

Allowed `branch_kind` values:

```text
default
generic_exploration
knowledge_directed
```

Meanings:

- `default`: canonical API-valid branch shared across comparable modes;
- `generic_exploration`: API/Profile-derived exploration without historical Knowledge;
- `knowledge_directed`: branch derived from selected API-specific or General Knowledge.

Allowed `input_validity_intent` values:

```text
expected_valid
boundary_valid
intentionally_invalid
```

Meanings:

- `expected_valid`: inputs are intended to satisfy ordinary API validity requirements;
- `boundary_valid`: inputs remain valid while approaching a semantic boundary;
- `intentionally_invalid`: a specific API validity condition is deliberately violated to test error handling.

Allowed `activation_logic` values:

```text
all_required
any_required
```

The default and generic branches do not use historical Knowledge and therefore
have an empty `source_knowledge_ids` array.

A Knowledge-directed branch references at least one selected Knowledge record.

`budget_share` is branch-level execution allocation, not a Knowledge confidence
score or Knowledge importance weight.

For an initial HarnessSpec revision, the Builder assigns `budget_share`
deterministically from the versioned budget policy. Adaptive feedback may change
the stored shares only by creating a new HarnessSpec revision.

`risk_dimensions` reuses the controlled vocabulary defined by API-specific and
General Knowledge and enumerated by the HarnessSpec synthesis contract.

### 12.2 Target Property

A Target Property is a state deliberately generated or explored by the branch.
It is not a condition that must hold for every branch.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `target_property_id` | string | yes | Unique target-property identifier |
| `subject` | string | yes | API parameter, output, exception, or contextual object |
| `property_name` | string | yes | Normalized semantic property |
| `desired_state` | JSON value | yes | Intended state, relation, or range |
| `source_refs` | array of Source References | yes | Sources supporting this target property |

A Target Property defines the desired semantic state, not how that state is
created.

### 12.3 Branch Precondition

A Branch Precondition determines whether execution may enter a branch. It does
not describe a property being fuzzed.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `precondition_id` | string | yes | Unique precondition identifier |
| `semantic_requirement` | Semantic Requirement | yes | Entry-gating condition |
| `source_refs` | array of Source References | yes | Supporting sources |
| `verification_status` | enum | yes | Evidence status |

Allowed `verification_status` values:

```text
confirmed
inferred
unresolved
```

### 12.4 Activation Target

An Activation Target records runtime evidence that the intended semantic state
or target API path actually occurred. It does not define how instrumentation is
implemented.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `activation_target_id` | string | yes | Unique activation-target identifier |
| `activation_kind` | enum | yes | Type of runtime activation evidence |
| `target_property_ids` | array of strings | yes | Target Properties whose states must be observed |
| `observation_point` | enum | yes | Semantic observation point |

Allowed `activation_kind` values:

```text
property_state
target_api_reached
```

Allowed `observation_point` values:

```text
before_target_api_call
at_target_api_call
after_target_api_call
```

For `property_state`, `target_property_ids` is non-empty.

For `target_api_reached`, `target_property_ids` is empty and
`observation_point` is `at_target_api_call`.

Oracle readiness is defined by Oracle Preconditions rather than by an Activation
Target.

### 12.5 Oracle Requirement

An Oracle Requirement describes what semantic behavior should be observed. It
does not define concrete instrumentation or implementation code.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `oracle_requirement_id` | string | yes | Unique Oracle requirement identifier |
| `oracle_type` | string | yes | Controlled Oracle category |
| `observation_subjects` | array of strings | yes | Inputs, outputs, exceptions, states, or executions compared |
| `oracle_preconditions` | array of Semantic Requirements | yes | Conditions required for this Oracle to be meaningful |
| `expected_behavior` | Semantic Requirement | yes | Structured expected relation or behavior |
| `source_refs` | array of Source References | yes | Sources supporting the Oracle requirement |
| `requirement_level` | enum | yes | Whether implementation is mandatory or preferred |

Allowed `requirement_level` values:

```text
required
preferred
```

`oracle_type` reuses the project's controlled Oracle vocabulary.

---

## 13. `provenance`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `generation_method` | enum | yes | Main generation method |
| `generator_name` | string | yes | Generator or synthesis pipeline name |
| `model_name` | string or null | yes | LLM identifier when applicable |
| `generation_run_id` | string | yes | Stable identifier for the synthesis run |
| `script_ref` | Artifact Reference or null | yes | Exact conversion or synthesis script |
| `contract_ref` | Artifact Reference | yes | Exact machine-readable contract |
| `rules_ref` | Artifact Reference | yes | Exact synthesis-rules document |
| `generated_at` | string | yes | ISO 8601 generation timestamp |

Allowed `generation_method` values:

```text
manual
script
llm
hybrid
```

---

## 14. `review`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `validation_status` | enum | yes | Automatic validation result |
| `validation_issues` | array of Validation Issue objects | yes | Structured validation findings |
| `human_review_status` | enum | yes | Human review state |
| `reviewer_id` | string or null | yes | Reviewer identifier |
| `reviewed_at` | string or null | yes | ISO 8601 review timestamp |
| `review_notes` | string or null | yes | Concise review note |

Allowed `validation_status` values:

```text
not_validated
passed
failed
```

Allowed `human_review_status` values:

```text
not_reviewed
approved
needs_revision
```

### 14.1 Validation Issue

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `issue_code` | string | yes | Normalized validation issue code |
| `severity` | enum | yes | Issue severity |
| `field_path` | string | yes | Related HarnessSpec field path |
| `message` | string | yes | Concise issue description |

Allowed `severity` values:

```text
error
warning
```

---

## 15. Structural Invariants

A valid HarnessSpec must satisfy:

1. `schema_version` is `"1.0"`.
2. `revision_number` is a positive integer.
3. All `identity` fields remain unchanged across revisions of the same `spec_id`.
4. Revision 1 has `parent_revision_ref = null`; later revisions reference the immediately preceding revision of the same `spec_id`.
5. `forked_from_spec_ref`, when present, appears only on revision 1 and references a different `spec_id` with the same framework and target API.
6. `initial_creation` has no fork source; `cross_spec_derivation` has a fork source.
7. Revision 1 includes `initial_definition`; later revisions do not.
8. `metadata_only` does not appear with a semantic change scope.
9. Internal IDs required to be unique are unique within the record.
10. Internal references resolve within the record; external references resolve to exact artifact revisions or versions.
11. A controlled baseline has `candidate_manifest_ref = null`, no Candidate Decisions, no Resolution Records, and no Knowledge-directed branches.
12. A bug-aware Static or Adaptive HarnessSpec has a non-null `candidate_manifest_ref`.
13. Each candidate Knowledge appears exactly once in `candidate_decisions`.
14. A selected candidate is not `not_applicable`, `unsupported`, or `unknown` in either applicability or capability.
15. Every Knowledge referenced by a Knowledge-directed branch is selected.
16. Every Knowledge ID in a Resolution Record resolves to exactly one Candidate Decision.
17. A Resolution Record involves at least two Knowledge records and contains at least one interaction dimension and one effect.
18. Every Resolution Effect targets only Knowledge involved in its Resolution Record, and every referenced result branch exists.
19. Exactly one branch has `branch_kind = default`, and `default_branch_id` resolves to it.
20. The default branch uses `input_validity_intent = expected_valid` and has no source Knowledge.
21. A generic branch has no source Knowledge; a Knowledge-directed branch has at least one selected source Knowledge.
22. Every branch has `budget_share > 0`, and all branch budget shares sum to `1` within implementation-defined floating-point tolerance.
23. Every global or branch Constraint is mandatory for its scope.
24. A condition deliberately violated by an intentionally invalid branch is a Target Property rather than a Constraint of that branch.
25. Target Properties referenced by an Activation Target exist in the same branch.
26. `property_state` Activation Targets reference at least one Target Property.
27. `target_api_reached` Activation Targets reference no Target Property and use `at_target_api_call`.
28. Full Knowledge content is not embedded in `knowledge_plan`.
29. Semantic requirements, target properties, constraints, preconditions, activation targets, and Oracle requirements contain no Helper calls, Strategy Primitive implementations, or source code.
30. A revision with unresolved required references, unresolved Constraints or Preconditions, or failed automatic validation is not `active`.
31. An `active` revision has `validation_status = passed` and `human_review_status = approved`.
32. At most one revision of the same `spec_id` is `active`.
33. Change scopes are derived from structured parent/fork comparison when such a source exists.

---

## 16. Compact Record Skeleton

```json
{
  "schema_version": "1.0",
  "identity": {
    "spec_id": "",
    "framework": "pytorch",
    "target_api": "",
    "spec_mode": "bug_aware_static"
  },
  "revision_information": {
    "revision_number": 1,
    "parent_revision_ref": null,
    "forked_from_spec_ref": null,
    "revision_trigger": "initial_creation",
    "change_scopes": ["initial_definition"],
    "change_summary": "",
    "lifecycle_status": "draft"
  },
  "target_context": {
    "api_profile_ref": {
      "profile_id": "",
      "revision": 1,
      "content_hash": ""
    },
    "helper_profile_ref": {
      "profile_id": "",
      "version": "",
      "content_hash": ""
    },
    "framework_version": null,
    "backend_scope": []
  },
  "knowledge_plan": {
    "candidate_manifest_ref": null,
    "candidate_decisions": [],
    "resolution_records": []
  },
  "validity_constraints": {
    "global_constraints": []
  },
  "exploration_plan": {
    "default_branch_id": "",
    "branches": []
  },
  "provenance": {
    "generation_method": "hybrid",
    "generator_name": "",
    "model_name": null,
    "generation_run_id": "",
    "script_ref": null,
    "contract_ref": {
      "artifact_id": "",
      "artifact_version": "1.0",
      "content_hash": ""
    },
    "rules_ref": {
      "artifact_id": "",
      "artifact_version": "1.0",
      "content_hash": ""
    },
    "generated_at": ""
  },
  "review": {
    "validation_status": "not_validated",
    "validation_issues": [],
    "human_review_status": "not_reviewed",
    "reviewer_id": null,
    "reviewed_at": null,
    "review_notes": null
  }
}
```
