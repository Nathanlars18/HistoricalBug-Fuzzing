# Historical Bug-Aware Strategy Schema v1.1

## 1. Purpose and Boundary

This document defines the human-readable data model for:

1. the Strategy Catalog;
2. the Strategy Plan.

The Strategy layer converts one validated HarnessSpec revision into one
implementation-oriented Strategy Plan under an exact Strategy Catalog version.

It answers:

> How is each HarnessSpec branch implemented using the available API binding,
> Helper capabilities, reviewed Strategy Primitives, and Harness template
> interface?

The Strategy layer may:

- select reviewed Strategy Primitives;
- bind Primitive inputs, parameters, and outputs;
- order Primitive steps;
- place steps into semantic template slots;
- map HarnessSpec elements to implementation steps;
- handle expected pre-call construction and guard failures.

The Strategy layer must not:

- add, remove, merge, or split HarnessSpec branches;
- modify branch budgets or semantic goals;
- change Target Properties, Activation Targets, or Oracles;
- introduce unavailable Helpers or Primitives;
- emit arbitrary C++ source code;
- define feedback or adaptive-budget policies.

On successful synthesis, the LLM generates only the semantic
`implementation_plan`. When no valid plan can be constructed from the supplied
views, it may instead return structured blocking gaps. A blocked response is a
synthesis diagnostic and is not a Strategy Plan record.

The deterministic Builder owns identity, revision information, exact artifact
references, normalized identifiers, provenance, and initial review state.

---

## 2. Artifact Relationship and Versioning

```text
HarnessSpec revision
        +
Strategy Catalog version
        ↓
Strategy Plan revision
        ↓
Deterministic Harness Generator
        ↓
C++ Harness artifact
```

One Strategy Plan implements exactly one HarnessSpec revision.

A Strategy Plan may have multiple revisions while its source HarnessSpec remains
unchanged, for example after validation or compilation repair.

When the source HarnessSpec revision changes, a new `strategy_id` is created and
its Strategy revision starts from 1.

### 2.1 Template and Catalog Versions

`template_ref.artifact_version` identifies the version of the Harness template
artifact.

`catalog_version` identifies the complete Strategy Catalog snapshot, including:

- the referenced template;
- the template interface;
- built-in runtime values;
- all Primitive definitions;
- Primitive implementation bindings;
- Helper Profile references;
- Primitive limitations.

The two versions are independent and need not use the same number.

Multiple Catalog versions may reference the same template version when only
Primitive definitions change.

A change to the template version, template content hash, slot interface, or
built-in values requires a new Catalog version.

One Catalog version references exactly one immutable template artifact version
and content hash.

The same template `artifact_version` must not identify different template
content.

---

## 3. Common Types and References

### 3.1 Identifier

Identifiers are non-empty lowercase strings containing letters, digits, and
underscores.

Recommended pattern:

```text
^[a-z][a-z0-9_]*$
```

Identifiers must not contain paths, whitespace, C++ code, or natural-language
explanations.

Fields copied exactly from an upstream artifact use that artifact's identifier
syntax and are described as non-empty strings in this Schema. They are not
renamed by the Strategy Builder.

### 3.2 Hash and Timestamp

`content_hash` is the lowercase SHA-256 hash of the exact referenced artifact:

```text
^[0-9a-f]{64}$
```

Timestamps use RFC 3339 UTC format.

### 3.3 Reference Structures

| Reference | Required fields |
| --- | --- |
| Artifact Reference | `artifact_id`, `artifact_version`, `content_hash` |
| HarnessSpec Reference | `spec_id`, `revision_number`, `content_hash` |
| Strategy Catalog Reference | `catalog_id`, `catalog_version`, `content_hash` |
| Strategy Revision Reference | `strategy_id`, `revision_number`, `content_hash` |
| Helper Profile Reference | `profile_id`, `revision`, `content_hash` |

All references identify exact immutable artifact content.

---

# Part I: Strategy Catalog

## 4. Strategy Catalog

The Strategy Catalog is the versioned implementation-capability snapshot used
by Strategy synthesis.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `schema_version` | string | yes | Catalog record-format version |
| `catalog_id` | identifier | yes | Stable Catalog identity |
| `catalog_version` | positive integer | yes | Catalog snapshot version |
| `target_language` | enum | yes | Target Harness language |
| `template_interface` | object | yes | Template artifact and exposed interface |
| `primitives` | non-empty array | yes | Reviewed Strategy Primitives |
| `provenance` | object | yes | Catalog construction sources |
| `review` | object | yes | Validation and human-review state |

Initial fixed values:

```text
schema_version = "1.0"
target_language = "cpp"
```

Primitive IDs are unique within one Catalog.

Only a Catalog with passed machine validation and approved human review may be
used for main experiments.

`strategy_catalog_record.schema.json` validates the Catalog record structure.
The Builder separately validates identifier uniqueness, exact Helper Profile
references, HarnessSpec vocabulary compatibility, and execution semantics that
cannot be expressed reliably in JSON Schema.

---

## 5. Template Interface

The Template Interface describes the runtime values and semantic placement slots
provided by one exact Harness template.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `template_ref` | Artifact Reference | yes | Exact Harness template |
| `available_slots` | ordered non-empty array | yes | Semantic code-placement order |
| `built_in_values` | non-empty array | yes | Values supplied by the template |

### 5.1 Template Slots

Initial slot vocabulary:

```text
input_construction
pre_call_transform
pre_call_guard
pre_call_observation
target_call
post_call_observation
oracle_check
artifact_logging
cleanup
```

`available_slots` is ordered.

The order defines the permitted high-level execution order. Strategy Steps must
use slots in non-decreasing order.

Within the same slot, the order of Steps in the Strategy Plan is authoritative.

Slots describe semantic placement rather than physical line numbers or raw
template markers.

The Harness Generator owns the mapping from semantic slots to physical template
locations.

### 5.2 Built-in Value

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `value_id` | identifier | yes | Template-provided runtime value |
| `value_kind` | enum | yes | Normalized dataflow type |
| `description` | non-empty string | yes | Concise semantic meaning |

Expected initial built-in values may include:

```text
fuzz_data
fuzz_size
runtime_context
```

The Strategy Plan may use only built-in values declared by the exact Catalog.

---

## 6. Value Kinds

Initial normalized `value_kind` vocabulary:

```text
raw_bytes
byte_cursor
boolean
integer
floating
string
scalar
dtype
rank
shape
device
layout
tensor
tensor_list
optional_value
tuple_value
exception_state
observation_result
artifact
```

Value kinds describe dataflow compatibility rather than complete C++ types.

A target API return value is resolved by the Builder from the exact API Profile:

- Tensor return → `tensor`;
- scalar return → `scalar`;
- Boolean return → `boolean`;
- Tensor-list return → `tensor_list`;
- tuple return → `tuple_value`;
- void return → no output binding.

There is no generic `api_result` value kind.

If an API parameter or return cannot be mapped to the current vocabulary,
Strategy synthesis reports a capability gap. Supporting a new value kind
requires a new Catalog version and corresponding Builder and Generator support.

---

## 7. Strategy Primitive

A Strategy Primitive is a reviewed, typed, reusable implementation operation.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `primitive_id` | identifier | yes | Stable Primitive identifier |
| `primitive_kind` | enum | yes | Implementation operation category |
| `summary` | non-empty string | yes | Concise operation description |
| `semantic_support` | object | yes | Supported HarnessSpec semantic vocabularies |
| `allowed_template_slots` | non-empty array | yes | Permitted placement slots |
| `input_contract` | array | yes | Runtime input ports |
| `output_contract` | array | yes | Runtime output ports |
| `parameter_contract` | array | yes | Configuration parameters |
| `outcome_contract` | object | yes | Declared runtime failure outcomes |
| `implementation_binding` | object | yes | Reviewed emitter and Helper binding |
| `limitations` | array of strings | yes | Known implementation limitations |

A Primitive contains no arbitrary C++ source text.

### 7.1 Primitive Kind

Initial vocabulary:

```text
input_decode
value_construct
value_transform
relation_enforce
predicate_evaluate
target_api_invoke
oracle_evaluate
artifact_record
```

Branch dispatch, common runtime initialization, target-API reach counters, and
common cleanup are deterministic Harness Generator infrastructure rather than
LLM-selected Primitives.

### 7.2 Semantic Support

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `risk_dimensions` | array | yes | Supported HarnessSpec risk dimensions |
| `requirement_types` | array | yes | Supported Semantic Requirement types |
| `oracle_types` | array | yes | Supported HarnessSpec Oracle types |

`risk_dimensions` reuses the HarnessSpec vocabulary:

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

`requirement_types` and `oracle_types` reuse the exact controlled vocabularies
from the HarnessSpec version consumed by the Builder.

The Catalog Schema records the vocabulary expected by this Strategy version.
The Builder also compares Catalog values with the loaded HarnessSpec Schema so
that vocabulary drift fails before synthesis.

No independent `capability_tags` namespace is defined.

Empty Semantic Support arrays are permitted for infrastructure operations that
do not directly implement a HarnessSpec semantic element.

Semantic Support identifies possible compatibility and does not independently
prove complete implementation.

---

## 8. Primitive Contracts

### 8.1 Input Port

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `port_id` | identifier | yes | Primitive-local input port |
| `accepted_value_kinds` | non-empty array | yes | Accepted runtime value kinds |
| `required` | boolean | yes | Whether the Step must bind this port |

Input port IDs are unique within one Primitive.

### 8.2 Output Port

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `port_id` | identifier | yes | Primitive-local output port |
| `produced_value_kind` | enum | yes | Produced runtime value kind |
| `binding_required` | boolean | yes | Whether the Step must bind this output |

Output port IDs are unique within one Primitive.

A side-effect-only Primitive may have an empty `output_contract`.

### 8.3 Parameter Contract

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `parameter_id` | identifier | yes | Primitive-local parameter |
| `value_kind` | enum | yes | Expected parameter type |
| `required` | boolean | yes | Whether an explicit binding is mandatory |
| `allowed_binding_kinds` | non-empty array | yes | Permitted binding forms |
| `default_value` | JSON value | no | Default for an omitted optional parameter |
| `allowed_values` | non-empty array | no | Closed permitted value set |

Allowed parameter binding kinds:

```text
literal
value_ref
spec_parameter
```

A required parameter must be explicitly bound.

An optional parameter may be omitted. If `default_value` is present, the emitter
uses that value.

A missing `default_value` means no Catalog default is declared.

An explicit `default_value = null` means JSON null is the actual default.

A literal string is data only and must not contain a C++ expression.

### 8.4 Outcome Contract

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `failure_outcomes` | array | yes | Declared non-success runtime outcomes |

Success is implicit and uses the reserved identifier:

```text
success
```

Each Failure Outcome contains:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `outcome_id` | identifier | yes | Primitive-local failure outcome |
| `description` | non-empty string | yes | Concise outcome meaning |
| `terminal_action` | enum | yes | Deterministic safe action for this outcome |

Failure outcome IDs are unique within one Primitive.

`success` is prohibited inside `failure_outcomes`.

Allowed `terminal_action` values and their execution semantics are defined in
Section 14. The Catalog selects the action; the LLM does not invent or override
it. For every selected pre-call Primitive failure outcome, the Builder derives
the corresponding Failure Handler from this declaration.

Compiler failures, missing references, unavailable Primitives, and type
mismatches are not runtime outcomes.

In Strategy v1.1, externally handled failure outcomes may be selected only in
pre-call slots. Post-call target exceptions and Oracle failures remain Oracle
semantics; low-level recovery internal to one Primitive is not represented as
a Failure Handler.

### 8.5 Implementation Binding

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `kind` | enum | yes | Implementation source |
| `emitter_id` | identifier | yes | Reviewed Generator emitter |
| `helper_profile_ref` | Helper Profile Reference or null | yes | Exact Helper when applicable |

Allowed `kind` values:

```text
helper_backed
generator_native
api_binding
```

Constraints:

- `helper_backed` requires a non-null `helper_profile_ref`;
- `generator_native` requires `helper_profile_ref = null`;
- `api_binding` requires `helper_profile_ref = null`;
- every binding requires a known `emitter_id`;
- `emitter_id` is an implementation identifier, not C++ source code.

For `helper_backed` and `generator_native`, the Catalog port contracts are
authoritative.

For `api_binding`, the Builder resolves effective input and output ports from
the exact API Profile referenced through HarnessSpec.

The Builder creates an API-specific Resolved Primitive View in memory. It is
used for prompt construction and validation but is not stored as a separate
artifact.

The Harness Generator repeats the same resolution before rendering the target
API call.

---

# Part II: Strategy Plan

## 9. Strategy Plan Root

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `schema_version` | string | yes | Strategy Plan record-format version |
| `identity` | object | yes | Stable Strategy identity |
| `revision_information` | object | yes | Same-Strategy revision chain |
| `source_context` | object | yes | Exact source HarnessSpec and Catalog |
| `implementation_plan` | object | yes | Per-branch implementation |
| `provenance` | object | yes | Generation artifacts and run |
| `review` | object | yes | Validation and human-review state |

Initial fixed value:

```text
schema_version = "1.1"
```

### 9.1 Identity

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `strategy_id` | identifier | yes | Stable identity for one HarnessSpec revision |
| `framework` | identifier | yes | Target framework |
| `target_api` | non-empty string | yes | Exact target API |
| `spec_mode` | enum | yes | Experimental mode inherited from HarnessSpec |

Allowed `spec_mode` values:

```text
controlled_baseline
bug_aware_static
bug_aware_adaptive
```

Identity fields remain unchanged across revisions of the same `strategy_id`.

### 9.2 Revision Information

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `revision_number` | positive integer | yes | Strategy implementation revision |
| `parent_revision_ref` | Strategy Revision Reference or null | yes | Immediate previous revision |
| `revision_trigger` | enum | yes | Event causing this revision |
| `change_scopes` | non-empty array | yes | Structured changed areas |
| `change_summary` | non-empty string | yes | Concise change description |

Allowed `revision_trigger` values:

```text
initial_creation
validation_repair
compile_repair
catalog_update
manual_review
regeneration
```

Allowed `change_scopes` values:

```text
initial_definition
primitive_selection
dataflow
parameter_binding
template_placement
failure_handling
spec_binding
source_context
metadata_only
```

Revision rules:

- revision 1 has `parent_revision_ref = null`;
- revision 1 uses `initial_creation`;
- revision 1 includes `initial_definition`;
- later revisions reference the immediate previous revision of the same
  `strategy_id`;
- all revisions of one `strategy_id` reference the same HarnessSpec revision;
- `metadata_only`, when present, is the only `change_scopes` value.

There is no `lifecycle_status`.

The Harness artifact explicitly references the Strategy revision it uses.

### 9.3 Source Context

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `harness_spec_ref` | HarnessSpec Reference | yes | Exact HarnessSpec implemented |
| `strategy_catalog_ref` | Strategy Catalog Reference | yes | Exact implementation capability snapshot |
| `derived_from_strategy_ref` | Strategy Revision Reference or null | yes | Exact source Strategy when a budget-only plan is deterministically rebound |

API Profile and Helper Profile sets are resolved through these references and
are not duplicated in the Strategy Plan. Initial LLM-derived plans set
`derived_from_strategy_ref = null`. A feedback-derived budget-only plan starts
a new Strategy identity for the new HarnessSpec and references the exact copied
Strategy through `derived_from_strategy_ref`; its implementation plan is
otherwise unchanged.

---

## 10. Implementation Plan

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `branch_strategies` | non-empty array | yes | Implementation for every HarnessSpec branch |

The Strategy branch set exactly equals the referenced HarnessSpec branch set.

Branch dispatch and budget interpretation are Generator-owned infrastructure.

### 10.1 Branch Strategy

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `source_branch_id` | non-empty string | yes | Exact HarnessSpec branch ID copied without renaming |
| `steps` | ordered non-empty array | yes | Main-path Strategy Steps |
| `spec_bindings` | array | yes | HarnessSpec-to-Step mappings |
| `failure_handlers` | array | yes | Expected pre-call failure handling |

A Branch Strategy does not repeat HarnessSpec budgets, risk dimensions,
Knowledge IDs, validity intent, or exploration goals.

---

## 11. Strategy Step

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `step_id` | identifier | yes | Branch-local Step identifier |
| `primitive_id` | identifier | yes | Primitive in the exact Catalog |
| `template_slot` | enum | yes | Semantic placement slot |
| `input_bindings` | array | yes | Runtime input bindings |
| `parameter_bindings` | array | yes | Primitive parameter bindings |
| `output_bindings` | array | yes | Runtime output bindings |

The Strategy Plan does not repeat `primitive_kind`.

The Builder resolves `primitive_kind` through `primitive_id`.

The selected slot must be:

- exposed by the Catalog Template Interface;
- allowed by the selected Primitive.

The `steps` array is the main execution order.

Step slots are non-decreasing according to
`template_interface.available_slots`. Steps in the same slot execute in array
order.

Each branch contains exactly one Primitive with:

```text
primitive_kind = target_api_invoke
template_slot = target_call
```

---

## 12. Bindings and Type Resolution

### 12.1 Input Binding

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `port_id` | identifier | yes | Primitive input port |
| `value_ref` | identifier | yes | Built-in or prior Step output |

A `value_ref` resolves to:

- a Built-in Value declared by the Catalog; or
- an Output Binding produced earlier in the same branch.

Forward references are prohibited.

### 12.2 Output Binding

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `port_id` | identifier | yes | Primitive output port |
| `value_id` | identifier | yes | Newly produced branch-local value |

The Strategy Plan does not declare an output type.

The Builder derives it from the selected Primitive or Resolved API Primitive
View and maintains:

```text
value_id -> produced_value_kind
```

Output value IDs are unique within one branch.

### 12.3 Parameter Binding

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `parameter_id` | identifier | yes | Primitive parameter |
| `binding_kind` | enum | yes | Binding source |
| `binding_value` | JSON value | yes | Value interpreted by binding kind |

Allowed `binding_kind` values:

```text
literal
value_ref
spec_parameter
```

For `literal`, `binding_value` is a JSON data value conforming to the Parameter
Contract.

For `value_ref`, `binding_value` is one Built-in or previously produced
`value_id`.

For `spec_parameter`, `binding_value` contains:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `spec_element_type` | enum | yes | HarnessSpec object category |
| `spec_element_id` | non-empty string | yes | Exact HarnessSpec element ID copied without renaming |
| `parameter_name` | non-empty string | yes | Exact exposed Semantic Requirement parameter name |

Allowed primary parameter sources:

| Spec element type | Parameter source |
| --- | --- |
| `global_constraint` | `semantic_requirement.parameters` |
| `branch_constraint` | `semantic_requirement.parameters` |
| `branch_precondition` | `semantic_requirement.parameters` |
| `target_property` | `semantic_requirement.parameters` |
| `oracle_requirement` | `expected_behavior.parameters` |

An Activation Target is not a primary parameter source. Its observation phase
controls Primitive selection and template placement, while the observed
property parameters are obtained through its referenced Target Property.

Arbitrary JSON Paths and array-index references are prohibited.

Only literal configuration values are exposable. Runtime entity references,
including `subject_ref` and equivalent input/output references, remain semantic
input origins and must be implemented through Step input bindings. Ambiguous
parameter names with different values are rejected rather than silently
discarded. Each exposed parameter includes its deterministically inferred
`value_kind` in the synthesis view; that view field is not stored in the final
Strategy Plan.

### 12.4 Type Validation

The Builder validates:

1. every referenced port and parameter exists;
2. every required port and parameter is bound;
3. undeclared ports and parameters are rejected;
4. every input value exists before use;
5. every output value ID is unique;
6. every value kind is accepted by the consuming port or parameter;
7. literals conform to the Parameter Contract;
8. API inputs and outputs match the Resolved API Primitive View.

---

## 13. Spec Binding

A Spec Binding maps one HarnessSpec element to the Strategy Steps that implement
it.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `spec_element_type` | enum | yes | HarnessSpec object category |
| `spec_element_id` | non-empty string | yes | Exact HarnessSpec element ID copied without renaming |
| `implementation_step_ids` | ordered non-empty array | yes | Implementing main-path Steps |

Allowed `spec_element_type` values:

```text
global_constraint
branch_constraint
branch_precondition
target_property
activation_target
oracle_requirement
```

One HarnessSpec element has at most one Spec Binding in one branch. That binding
may reference multiple Steps.

One Step may be referenced by multiple Spec Bindings.

For a compound Target Property, the union of directly implementing Steps must
cover every declared risk dimension. For an Activation Target, every required
observation phase must have a compatible direct observation Step. Any additional
Step listed in a Spec Binding must be a dataflow ancestor of a direct semantic
Step in the same Binding.

A Spec Binding does not repeat HarnessSpec semantic content.

Target-API invocation is not represented as a Spec Binding. It is a fixed
Strategy invariant.

Required coverage:

- every global Constraint is bound in every branch;
- every branch-local Constraint is bound in its branch;
- every Branch Precondition is bound in its branch;
- every Target Property is bound in its branch;
- every Activation Target is bound in its branch;
- every required Oracle Requirement is bound in its branch.

Preferred Oracle Requirements may be omitted.

`implementation_step_ids` references main-path Steps only. The Builder rejects
unknown or duplicate Step IDs, then orders valid IDs according to the branch's
`steps` execution order before materializing the final record.

---

## 14. Failure Handler

A Failure Handler processes one declared non-success outcome from a pre-call
main-path Step.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `failure_handler_id` | identifier | yes | Branch-local handler identifier |
| `trigger` | object | yes | Exact Step and failure outcome |
| `terminal_action` | enum | yes | Safe iteration-ending action |

`trigger` contains:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `step_id` | identifier | yes | Main-path Step producing the outcome |
| `outcome_id` | identifier | yes | Declared Primitive failure outcome |

Allowed `terminal_action` values:

```text
reject_input
record_and_return
```

Meanings:

- `reject_input`: the generated input cannot safely or validly reach the intended
  API path and is counted as rejected input;
- `record_and_return`: the runtime failure is recorded before ending the current
  fuzz iteration.

Version 1.0 does not support arbitrary fallback Step sequences or resumption.

Low-level recovery internal to one Primitive belongs to that reviewed Primitive
implementation.

Alternative semantic strategies belong in separate HarnessSpec branches.

Failure Handler constraints:

- `step_id` resolves in the same branch;
- `outcome_id` is declared by that Step's Primitive;
- `outcome_id = success` is prohibited;
- the triggering Step occurs before `target_call`;
- a Handler is not a Strategy Step;
- a Handler cannot appear in `implementation_step_ids`;
- a Handler cannot satisfy a Constraint, Target Property, Activation Target, or
  Oracle;
- a handled iteration is not counted as branch activation;
- an unexecuted Oracle is not counted as passed;
- expected target-API exceptions are Oracle outcomes rather than Failure Handler
  triggers.

---

## 15. Provenance and Review

### 15.1 Catalog Provenance

Catalog Provenance contains:

```text
generation_method
source_refs
generated_at
```

`source_refs` identify the exact Helper Profiles, emitter implementation, and
template sources used to construct the Catalog.

### 15.2 Strategy Plan Provenance

Strategy Plan Provenance contains:

```text
generation_method
generator_name
model_name
generation_run_id
script_ref
contract_ref
rules_ref
generated_at
```

Allowed `generation_method` values:

```text
manual
script
llm
hybrid
```

The planned Builder normally records `hybrid`.

### 15.3 Review

Catalog and Strategy Plan use the same Review structure as HarnessSpec v1.6:

```text
validation_status
validation_issues
human_review_status
reviewer_id
reviewed_at
review_notes
```

Only artifacts with:

```text
validation_status = passed
human_review_status = approved
```

may be used to generate main-experiment Harnesses.

A successful initial Strategy Builder output uses:

```text
validation_status = passed
human_review_status = not_reviewed
```

`approved` is prohibited when machine validation has not passed.

---

## 16. Structural Invariants

A valid Strategy Catalog and Strategy Plan satisfy:

1. Record-format versions match their machine schemas.
2. Every external reference resolves to exact immutable content.
3. Catalog and template versions are independent.
4. One Catalog version references exactly one template version and hash.
5. A template or template-interface change creates a new Catalog version.
6. Primitive IDs are unique within one Catalog.
7. Built-in value IDs are unique within one Catalog.
8. Primitive port and parameter IDs are unique within their Primitive.
9. No Primitive contains arbitrary C++ source code.
10. Every Helper-backed Primitive references one exact Helper Profile.
11. Every Primitive emitter exists in the referenced Generator implementation.
12. One Strategy identity implements one exact HarnessSpec revision.
13. All revisions of one Strategy identity retain the same HarnessSpec reference.
14. Strategy identity framework, API, and mode match HarnessSpec.
15. Strategy branches exactly equal HarnessSpec branches.
16. Each HarnessSpec branch appears exactly once.
17. Strategy does not repeat or modify HarnessSpec budgets or semantic goals.
18. Every Step references a Primitive in the exact Catalog.
19. Every Step uses a template slot exposed by the Catalog.
20. Every Step uses a slot allowed by its Primitive.
21. Step slots are non-decreasing according to the Catalog slot order.
22. Every required Primitive input, output, and parameter is bound.
23. No undeclared port or parameter is bound.
24. Every input value exists before use.
25. Output value IDs are unique within each branch.
26. All dataflow and parameter value kinds are compatible.
27. Every branch contains exactly one target API invocation in `target_call`,
    except a branch implementing a `determinism` Oracle contains exactly two
    invocations with identical input and parameter bindings.
28. Every required HarnessSpec semantic element has one valid Spec Binding.
29. Spec Bindings reference main-path Steps in the same branch.
30. Every required Oracle is implemented; preferred Oracles may be omitted.
31. Every Primitive failure outcome declares one permitted terminal action.
32. Every Failure Handler references a declared pre-call failure outcome and
    copies its terminal action unchanged.
33. Failure Handlers cannot satisfy HarnessSpec semantic elements.
34. Handled iterations are not counted as activated or Oracle-passing executions.
35. Every Step either produces a value consumed later, appears in a Spec Binding,
    or is a target API invocation permitted by invariant 27.
36. Strategy Plan content contains no arbitrary C++ source code.
37. Only machine-valid and human-approved Catalogs and Strategy Plans enter
    main-experiment Harness generation.
38. Catalog semantic vocabularies are compatible with the exact HarnessSpec
    Schema loaded for synthesis.
39. Compound Target Properties have complete aggregate risk-dimension coverage.
40. Activation Targets cover every declared observation phase.
41. Auxiliary Spec-Binding Steps are dataflow ancestors of direct semantic
    Steps rather than unrelated padding.
