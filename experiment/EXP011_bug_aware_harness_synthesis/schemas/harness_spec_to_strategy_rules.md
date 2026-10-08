# HarnessSpec-to-Strategy Synthesis Rules v1.5

For source-backed auxiliary-argument relations, reject a branch only when its
generated domain is proved wholly incompatible and the same relation is not an
explicit HarnessSpec target. A mixed valid/invalid domain remains admissible.
Do not transfer ordinary-valid recipes to contract-boundary exploration. Rank
selection and reference-derived shapes must retain their fuzz/dataflow origin;
they must not encode a single historical trigger.

## Executable domains and preflight

The supplied resource policy is an experimental bound, not an API fact. Use the
same exact policy for controlled baseline and Static. Uniform scalar Tensor fill
does not cover elementwise values. For `expected_valid` only, use the supplied
ordinary recipe: it is a documented/source-backed bounded constructor subset,
not a universal validity theorem. Do not import it into a contract-boundary or
invalid-input branch. No recipe means no invented ordinary-valid guarantee.

An exploration variable must vary its named property: `numel == 0` requires
zero and nonzero possibilities, and shape mismatch requires equal and unequal
possibilities. Varying only fill values cannot vary shape or numel. Reference
derived same-shape inputs have an invariant equality relation. Observe these
variables; never turn them into unconditional rejection guards.

Use `minimum_dimension=1` for a nonempty bounded ordinary Tensor domain, not a
literal historical shape. `construct_tensor_from_reference` supports same_shape,
leading_dimension or selected_dimension with reference_axis. Optional Tensor
arguments may be None, present, or selected with select_optional_tensor_from_fuzz.
Optional buffers and legitimate omitted trailing defaults need not each consume
bytes, but there must be a meaningful fuzz-derived target input. Defaults cannot
be omitted before an explicitly bound later positional argument.

Semantic-support labels are not proof: subjects, operators, predicate arguments,
phases and roles must match actual code. For before-and-after observations use
one evaluator per phase. An observation is not validity enforcement. Unsupported
predicate forms, return conversions or emitter capabilities are reported before
LLM generation; they must not be silently approximated. Materialization preflight
must pass before accepting a candidate; compilation is a separate evidence level.

The current exact dimension guard adapter supports cross_subject_relation with
left_property_ref=right_property_ref=dimension_size, relation=equals and explicit
left_axis/right_axis. It checks the named target input dimensions at pre_call_guard.
Output checks without preconditions support property_relation equality over a
target return's rank, numel, shape, int64 dtype or all_zero. Preferred checks only
record outcomes; only required checks can terminate on violation. Other argument
forms/preconditions require an explicit adapter, not a nearby semantic label.

## 1. Purpose and layer boundary

The HarnessSpec fixes **what** to explore, observe, and check. A Strategy Plan
fixes **how** those semantics are materialized as ordered, typed Primitive
steps and Runner-owned event bindings. Strategy synthesis must not select new
Knowledge, add or remove branches, change branch budgets, reinterpret API
facts, or invent historical concrete inputs.

The Primitive classification is a project-defined engineering taxonomy derived
from the API-test lifecycle: value construction, constraint/relation handling,
target invocation, in-process observation, and behavior checking. It is not
claimed as a standard taxonomy. Primitive implementations may use official
LLVM/libFuzzer, PyTorch C++/ATen, SanitizerCoverage, and Runner capabilities;
the Catalog is the auditable adapter between HarnessSpec semantics and those
capabilities.

## 2. Required approved inputs

Synthesis requires:

1. one schema-valid HarnessSpec v2.2;
2. one exact external HarnessSpec review whose subject ID, revision, canonical
   content hash, and path match the HarnessSpec and whose decision is
   `approved`;
3. the exact ready and approved API Profile referenced by the HarnessSpec;
4. the exact ready and approved Helper Profiles referenced by the HarnessSpec;
5. one schema-valid, approved Strategy Primitive Catalog v4; and
6. for Bug-aware Static/Adaptive, the exact validated controlled-baseline
   Strategy used as the canonical default branch.

An embedded `review.validation_status=passed` is machine validation, not a
substitute for external human approval.

## 3. HarnessSpec v2.2 mapping

Only these structured elements create implementation obligations:

- `global_constraint`: enforce in every applicable branch;
- `branch_constraint`: enforce in its branch;
- `target_condition`: vary/enable and observe according to `role`;
- `behavior_observation`: capture at its declared observation phase; and
- `behavior_check`: evaluate when required, or materialize/defer explicitly
  when preferred.

`exploration_goal`, `grouping_summary`, descriptions, source references, and
input-validity rationale are synthesis context. They cannot independently add
a guard, exact input, Oracle, or target-call repetition.

Each required in-Harness element has exactly one `spec_binding`. A binding may
contain multiple ordered steps when all are necessary and connected by dataflow.
An auxiliary step in a binding must be a transitive dataflow ancestor of a
direct semantic step; unrelated padding is forbidden.

## 4. Target-condition roles

### 4.1 `activation_required`

The Strategy must make the condition reachable and record it at every declared
phase. It may use construction, transformation, or a guard only when the
HarnessSpec actually requires the condition to hold for branch execution.

### 4.2 `exploration_variable`

The Strategy must keep a fuzz-dependent degree of freedom capable of reaching
both the condition and nearby alternatives, and must observe the condition at
every declared phase. It must not turn the condition into an unconditional
pre-call rejection guard. The condition need not hold on every execution.

Exact historical shapes, values, seeds, exception messages, and complete
reproduction inputs are forbidden unless the approved HarnessSpec contains an
explicit structured constraint requiring them. Resource bounds used to keep
generation safe are experiment policy, not API or Knowledge facts.

## 5. Behavior observations and Runner ownership

`before_target_api_call` and `after_target_api_call` observations are implemented
by in-Harness observation steps. `on_target_api_termination` is Builder-owned
and is bound to the Runner event set:

- `target_api_returned`;
- `caught_exception`;
- `process_exit`;
- `process_signal`;
- `timeout`; and
- `sanitizer_report`.

The LLM must not create steps for Builder-owned Runner observations. An
observation records what happened; it is not automatically a pass/fail Oracle.
No behavior check may be synthesized from prose when `behavior_checks` is empty.

## 6. API call, defaults, optional values, and returns

The Builder resolves the unique target-call Primitive from the API Profile.
Each branch contains exactly one target-call step. The call may bind Tensor,
floating, integer, boolean, optional, and prior-step values according to the
resolved port types.

For a parameter with an API default, omission means `api_default`; the Strategy
may omit it or vary it within a declared ordinary fuzz domain, provided no
HarnessSpec rule is contradicted and the shared default branch is identical.
Do not invent a Knowledge requirement to justify a generic configuration choice. Explicit
`None` is represented by the Catalog built-in `none` and is valid only for a
port accepting `optional_value`. A required parameter without an API default
must be bound. Zero, one, and multiple directly mapped returns are supported;
each declared return port is bound exactly once when required.

## 7. Primitive selection and dataflow

The LLM may select only supplied candidate Primitive IDs, slots, ports, and
parameters. It does not emit C++, Helper names, emitter IDs, template markers,
metadata, hashes, failure handlers, or Runner bindings.

Input references must name a Catalog built-in or an earlier output in the same
branch. Output IDs are branch-local. Slot order must follow the template
interface. Types must be compatible. A selected step must be consumed by a
later step, directly implement a Spec binding, or be the unique target call.

Primitive semantic support is necessary but not sufficient: predicate ID,
condition role, observation phase, argument binding, type flow, fuzz-dependency
policy, and template slot must all agree. Root-cause or symptom labels are not
Primitive selection keys.

## 8. Baseline/Static comparability

The controlled-baseline default branch must remain fuzz-dependent and use the
same Catalog, API Profile, Helper set, template, and experiment resource policy
as the Knowledge-aware treatment.

For initial Bug-aware Static/Adaptive synthesis, the Builder replaces
`br_default` with the exact branch from the approved canonical controlled-
baseline Strategy. No LLM rewrite, equivalent reconstruction, or metadata-only
approximation is allowed. Knowledge-directed branches may differ only because
their approved HarnessSpec semantics differ.

## 9. Blocking gaps

Return `blocked` only for a factual capability or semantic conflict that cannot
be repaired by changing identifiers, bindings, ordering, or formatting. A gap
may reference only a required element. Preferred behavior checks may be
deferred with a factual reason and cannot alone block synthesis.

Allowed reasons are:

- `required_capability_unavailable`;
- `api_input_unconstructable`;
- `type_flow_unresolvable`;
- `required_observation_unavailable`;
- `required_oracle_unavailable`; and
- `semantic_conflict_unresolvable`.

## 10. Deterministic Builder validation

The Builder, not the LLM, owns exact source references, review references,
hashes, target-call port resolution, API-default omission, Runner bindings,
failure handlers, identifier normalization, final schema validation, and
generation diagnostics.

Hard failures include unknown or unsupported predicates/phases, invalid types
or dataflow, missing required arguments, required elements without bindings,
exploration variables converted to unconditional guards, loss of target-input
fuzz dependence, review/hash/path mismatch, and Static default-branch drift.

The following are not failures by themselves: one execution missing an
exploration condition, a preferred check deferred with reason, an equivalent
typed step composition, or absence of exact historical concrete values.

## 11. Human review boundary

Machine-valid Strategy Plans remain `not_reviewed`. Human review is recorded in
an immutable external Strategy Review Record; generated Plan JSON is never
edited in place. Review checks provenance, complete structured mapping,
exploration freedom, semantic fidelity, observation ownership, Catalog/emitter
consistency, and exact default-branch reuse. `needs_revision` creates a new
Strategy revision; `approved` authorizes Harness Artifact materialization.
