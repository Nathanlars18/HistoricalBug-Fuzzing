# HarnessSpec-to-Strategy Synthesis Rules v1.1

## 1. Purpose and Boundary

These rules guide the LLM in converting one validated HarnessSpec revision into
a semantic Strategy implementation plan under one exact Strategy Catalog
version.

The HarnessSpec fixes what must be tested. The Strategy Catalog fixes what may
be used to implement it. The Synthesis Contract fixes the input and response
format.

The LLM selects and connects supplied Strategy Primitives. It does not define
record metadata, implementation code, Failure Handlers, or validation results.

Builder and Validator own deterministic normalization and validation.

---

## 2. Input Preconditions and Output Choice

The LLM may reason only from the supplied:

- HarnessSpec View;
- Resolved API Primitive View;
- Template Interface View;
- Primitive Candidate Views.

Missing, malformed, unresolved, or unapproved required views are Builder
preflight failures. They are not valid reasons for an LLM `blocked` response.

The response must use exactly one mode:

- `materialized`: every source Branch has a complete candidate implementation;
- `blocked`: at least one required Branch has a genuine implementation gap.

A partial Strategy Plan is prohibited.

If any required Branch cannot be implemented, return only `blocked`. Continue
examining the supplied views sufficiently to report all directly supported,
independent blocking gaps. Do not speculate about unavailable evidence.

---

## 3. Fixed HarnessSpec Semantics

The Strategy must preserve the exact HarnessSpec revision.

It must not:

- add, remove, merge, or split Branches;
- change Branch budgets or exploration goals;
- change Constraints, Preconditions, Target Properties, Activation Targets, or
  Oracle Requirements;
- change the target API;
- introduce alternative semantic behavior.

Each source Branch contains one target-API invocation Step by default. A Branch
that implements a `determinism` Oracle contains exactly two target-API
invocation Steps with identical input and parameter bindings, so that the two
independently produced results can be compared. No other repetition is allowed.

For `expected_valid` and `boundary_valid` Branches, the Strategy must preserve
the intended API-call validity.

For an `intentionally_invalid` Branch:

- preserve the explicitly intended invalid state;
- do not silently normalize, reject, or repair that state before the API call;
- continue to satisfy unrelated required validity and safety constraints.

Historical Knowledge confidence, evidence strength, and Bug frequency are
already handled before Strategy synthesis and must not be used to rerank
Strategy Primitives.

---

## 4. Branch Synthesis Procedure

Process each source Branch through the following stages.

### 4.1 Build the Requirement Inventory

Use `required_spec_elements` as the authoritative required-element inventory.

For the current Branch, identify:

- applicable Global Constraints;
- Branch-local Constraints and Preconditions;
- Target Properties;
- Activation Targets and their observation points;
- required Oracle Requirements;
- preferred Oracle Requirements;
- target-API input and output ports;
- exposable HarnessSpec parameters.

Do not independently promote optional elements into required elements.

### 4.2 Match Semantic Candidates

Match each required element against the supplied Primitive Candidate Views.

For a Constraint, Precondition, or Target Property:

- match its `semantic_requirement.requirement_type` against
  `semantic_support.requirement_types`;
- for a Target Property, also check its `risk_dimensions` against the
  Primitive's supported risk dimensions.

A single Primitive need not cover every risk dimension of a compound Target
Property. Multiple compatible Primitives may jointly implement it.

The union of the directly implementing Steps must cover every risk dimension of
the Target Property. An overlap with only one dimension is insufficient.

For an Activation Target:

- use the referenced Target Property's requirement type and risk dimensions;
- require a Primitive capable of evaluating the property;
- require compatibility with each specified observation phase.

For an Oracle Requirement:

- match `oracle_type` against `semantic_support.oracle_types`;
- verify that the Primitive ports, parameters, and limitations can represent
  the observation subjects, Oracle Preconditions, and expected behavior.

`semantic_support` establishes candidate compatibility only. It does not by
itself prove complete implementation.

A Primitive with empty Semantic Support may be used as a dataflow dependency,
such as decoding or intermediate-value construction. It cannot independently
satisfy a Spec Element.

### 4.3 Construct a Candidate Path

Construct an ordered candidate path using only:

- built-in values supplied by the Template Interface;
- outputs produced by earlier Steps in the same Branch;
- the supplied target API Primitive;
- eligible Primitive Candidate Views.

Each `value_ref` is either an exact built-in value ID or the `value_id` of an
Output Binding produced by an earlier Step in the same Branch. Do not emit
synthetic `step:<step_id>.<output_port_id>` references.

Use the exact slot order supplied by the Template Interface. Do not invent or
hard-code unavailable slots.

The candidate path must provide:

1. sources for every required target-API input;
2. construction or transformation Steps for required target states;
3. required Guards and Preconditions;
4. required pre-call and post-call observations;
5. one target API invocation, or two identically bound invocations when a
   selected `determinism` Oracle requires repeated execution;
6. required Oracle evaluation;
7. bindings for every required Spec Element.

Every selected Step must contribute to dataflow, implement a Spec Element, or
be one of the permitted target API invocations.

### 4.4 Resolve Candidate Failure

If a candidate combination produces an incompatible dataflow, impossible slot
order, unsupported parameter binding, or semantic conflict, try the next
eligible candidate combination.

Do not return `blocked` merely because the first-ranked combination fails.

A Branch is provisionally materializable only when at least one coherent
candidate path remains. Passing this provisional process does not imply final
Validator acceptance.

If no eligible combination can implement a required element or complete the
path, record a Blocking Gap.

---

## 5. Primitive Selection and Step Reuse

### 5.1 Eligibility

A Primitive is eligible only when:

- it appears in the supplied Primitive Candidate Views;
- its Semantic Support is compatible with the intended use;
- its ports and parameters can be bound from available values or exposed
  HarnessSpec parameters;
- its permitted slots include the required execution phase;
- its limitations do not conflict with fixed HarnessSpec semantics;
- its use does not invalidate required Preconditions, observations, or Oracles.

### 5.2 Tie-Breaking

When multiple complete candidate paths remain valid, use this order:

1. reuse an existing Step whose binding signature is identical;
2. minimize newly introduced Steps;
3. minimize additional intermediate values and conversion dependencies;
4. use lexical `primitive_id` order as the final tie-breaker.

Do not prefer a Primitive merely because its Semantic Support lists more
categories.

### 5.3 Binding Signature

Two Step uses have the same binding signature only when they have:

- the same source Branch;
- the same `primitive_id`;
- the same template slot and execution phase;
- identical canonical input origins;
- identical parameter bindings;
- one execution effect that genuinely satisfies all referenced Spec Elements.

Input origins are identical only when corresponding ports reference:

- the same built-in value; or
- the same earlier Output Binding `value_id`.

Do not infer equivalence between independently constructed runtime values.

Parameter bindings are identical only when corresponding parameters have the
same binding kind and:

- equal normalized JSON values for `literal`;
- the same canonical value origin for `value_ref`;
- the same element type, element ID, and parameter name for `spec_parameter`.

Different inputs, parameters, phases, or execution effects require separate
Steps, even when the same Primitive is selected.

One produced output may be consumed by multiple later Steps.

A Step may be reused by multiple Spec Bindings only when one execution
genuinely implements all of them.

---

## 6. Spec Binding, Activation, and Oracle Rules

### 6.1 Spec Binding

For each applicable pair of source Branch and required Spec Element, emit one
Spec Binding.

One Spec Binding may reference multiple Steps when those Steps jointly implement
the element.

Every listed Step must either directly implement the element or be a dataflow
ancestor of a directly implementing Step in that same Binding. Do not add an
unrelated Step merely because its Semantic Support happens to overlap.

One Step may be referenced by multiple Spec Bindings only when the Step-reuse
rules are satisfied.

Within each Spec Binding, list `implementation_step_ids` once each in the same
order as the Branch's main-path `steps`. The Builder rejects unknown or
duplicate IDs and canonicalizes otherwise valid IDs to that execution order.

Use these semantic boundaries:

- Constraints and Preconditions bind to Steps that directly construct, enforce,
  transform, or guard the required condition.
- Target Properties bind to Steps that directly construct or transform the
  intended target state.
- Activation Targets bind to Steps that evaluate the target state at the
  required observation point.
- Oracle Requirements bind to Steps that directly perform the required
  comparison, check, or exception assessment.

Do not bind unrelated parsing, cleanup, logging, or infrastructure Steps merely
to increase apparent coverage.

Global Constraints receive one applicable Binding in each source Branch.
Branch-local elements receive Bindings only in their own Branch.

The target API invocation is fixed execution infrastructure and must not appear
as a Spec Binding.

An Activation Target remains a bindable and attributable Spec Element, but it
is not a `spec_parameter` source. Observation phase determines Primitive
selection and template placement; predicate parameters come from the referenced
Target Property.

### 6.2 Activation Targets

A non-transition Activation Target uses exactly one evaluation Step at its
specified observation point.

A state-transition Activation Target requires distinct `before` and `after`
observation Steps at their respective phases.

Each declared observation point must be covered independently. For each phase,
the directly observing Steps must jointly support the referenced Target
Property's requirement type and all of its risk dimensions.

A pre-call and a post-call observation cannot be merged into one Step.

An Activation Target verifies that the intended property occurred at runtime. It
does not replace the Step that constructs the Target Property.

### 6.3 Oracle Requirements

Every required Oracle must be implemented.

An Oracle is meaningful only when its Oracle Preconditions are satisfied by the
current Branch and candidate path.

If a required Oracle or its required Preconditions cannot be implemented,
synthesis is `blocked`.

A preferred Oracle is included only when it:

- reuses existing main-path values or Steps; or
- requires at most one compatible direct checking Primitive;
- preserves the Branch validity intent and execution order;
- introduces no unresolved dependency.

A preferred Oracle may be omitted when these conditions are not met. Its
omission does not block synthesis.

A preferred Oracle that is included receives one applicable Spec Binding.

Expected target-API exceptions are Oracle outcomes, not pre-call failure
outcomes.

---

## 7. Blocking-Gap Decisions

A Blocking Gap represents a genuine implementation or semantic gap established
from the supplied views.

Use the most specific applicable reason:

| Reason code | Decision condition |
| --- | --- |
| `api_input_unconstructable` | A required target-API input has no constructible source path. |
| `required_capability_unavailable` | A required non-input semantic operation has no supporting Primitive. |
| `type_flow_unresolvable` | Required capabilities exist individually but cannot form a compatible dataflow. |
| `required_observation_unavailable` | A required Activation Target cannot be observed at its specified phase. |
| `required_oracle_unavailable` | A required Oracle or its Preconditions cannot be implemented. |
| `semantic_conflict_unresolvable` | All otherwise eligible implementations conflict with fixed HarnessSpec semantics. |

Use `semantic_conflict_unresolvable` only after eligible alternatives have been
considered.

### 7.1 Gap Grouping

One Blocking Gap may cover multiple Branches only when they share:

- the same root cause;
- the same reason code;
- the same missing capability or conflicting condition;
- the same affected semantic scope.

List every affected Branch exactly once in `affected_branch_ids`.

The Builder normalizes and sorts `affected_branch_ids`. The LLM does not decide
their canonical order.

If different Branches are blocked by different Spec Elements or different
causes, create separate Blocking Gaps.

### 7.2 Spec Element Attribution

When a gap can be attributed to one exact Spec Element, provide both:

- `spec_element_type`;
- `spec_element_id`.

The referenced element must be required in every affected Branch. A preferred
Oracle cannot justify a blocked response.

When no exact element applies, set both fields to JSON `null`.

This includes API-level or global gaps that cannot be attributed to one exact
Spec Element.

Do not use empty strings, `"null"`, or `"unknown"` as substitutes for JSON
`null`.

If affected Branches require different element references, split the gap rather
than attaching an inaccurate shared reference.

For a multi-Branch gap with exact element references, the referenced elements
must have canonically equivalent semantics after local IDs and evidence
provenance are removed.

### 7.3 Non-Blocking Errors

The following are response-repair errors, not Blocking Gaps:

- invalid JSON;
- omitted required response fields;
- misspelled or invented identifiers;
- invalid local references;
- use of unavailable enum values;
- other format errors that can be corrected without changing semantics.

---

## 8. Failure and Output Boundary

The LLM does not output Failure Handlers and does not choose or override
`terminal_action`.

For each selected pre-call Primitive, the Builder derives Failure Handlers from
its declared failure outcomes.

A Primitive with externally handled failure outcomes is ineligible when placed
after `target_call`. This is a plan-validity condition; Failure Handler
derivation only copies outcomes from already-valid pre-call Steps.

Version 1.0 does not support LLM-designed fallback Step sequences.

A handled pre-call failure is not a successful Branch activation and does not
count as an executed or passed Oracle.

For `materialized`, output only the semantic implementation plan required by the
Synthesis Contract.

For `blocked`, output only the structured Blocking Gaps required by the
Synthesis Contract.

Do not output Builder-owned metadata, implementation code, raw Helper calls,
template markers, or unsupported implementation claims.
