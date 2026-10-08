# Knowledge v3 to HarnessSpec Synthesis Rules v2.1

## 1. Boundary

Convert one reviewed same-API Knowledge v3 bundle plus the exact API and Helper
Profiles into the semantic portion of one HarnessSpec v2.1. Do not retrieve new
Knowledge, classify defects, copy historical reproducers, emit implementation
code, allocate budgets, or invent expected behavior.

The Builder owns eligibility, exact artifact references, local ID
normalization, budget allocation, provenance, and review state. The LLM returns
only `knowledge_plan`, `validity_constraints`, and exploration branches.

## 2. Processing order

1. Create one `included` or `deferred` decision for every supplied Knowledge.
2. Identify API/Profile constraints shared by every branch.
3. Group compatible included Knowledge contributions into the fewest coherent
   Knowledge-directed branches.
4. Map historical anchors, variations, and observation candidates without
   reproducing the complete historical input.
5. Verify Predicate support, source paths, subjects, and branch membership.
6. Record one explicit represented, partially represented, or deferred mapping
   for every material Knowledge component.

## 3. Decisions

The Builder supplies only Knowledge that has matching `scope.target_api`, schema
version 3.0, and an approved review ledger entry bound to its canonical hash.
Do not reassess its scientific validity or rank it by subjective confidence.

Use `included` when at least one contribution can be represented by supported
Predicates or an evidence-cited exploration goal in the current capability
context. List every branch using it.

Use `deferred` only when no safe current representation exists, such as an
unsupported Predicate, an explicit environment conflict, incompatible required
conditions, or an observation that cannot be made meaningful with current
capabilities. A deferred decision has no branch IDs. Explain the concrete gap in
`decision_summary`.

Every decision also contains one `component_mapping` for the learned hypothesis,
each historical anchor, each variation opportunity, each observation candidate,
and each limitation. Use the exact Knowledge JSON Pointer as `source_path`.

- `represented`: the cited HarnessSpec elements preserve the full component;
- `partially_represented`: the cited elements preserve only the exact scope
  stated in `represented_scope`, while `deferred_scope` states what remains;
- `deferred`: no HarnessSpec element is claimed to represent the component.

Represented and partially represented mappings cite exact `spec_element_refs`.
Deferred mappings cite none. Mapping records expose coverage and omission; they
do not require every component to become a Predicate and do not authorize a
nearby or stronger meaning.

## 4. Branch grouping

Return exactly one `default` branch. It uses no Knowledge and represents the
canonical general API-valid path. For bug-aware generation, the Builder replaces
its semantic content with the exact reviewed Baseline default before writing the
record. Do not return `generic_exploration`.

Group compatible included Knowledge into one `knowledge_directed` branch.
Separate them only when one of these concrete conditions holds:

- evidence-supported validity intents differ;
- required anchors or constraints cannot hold together;
- device/backend/execution contexts are mutually exclusive;
- one invocation cannot preserve independent activation claims;
- evidence-supported expected checks conflict.

Branch membership is the merge/split record. Do not emit a separate relationship
taxonomy. `grouping_summary` states the concise reason.

## 5. Knowledge v3 mapping

### Learned hypothesis

Use it to state the branch goal and cite it through
`exploration_goal_source_refs`. It is not itself a concrete Predicate and does
not prove that the historical failure still exists.

### Historical anchors

An anchor must remain represented in at least one branch using its Knowledge.
Map it to:

- a branch constraint when it must hold but is not the state being measured; or
- an `activation_required` target condition when runtime confirmation is needed
  to claim the Knowledge state was exercised.

Never make a historical anchor global because the default branch must remain
Knowledge-independent.

### Variation opportunities

Map a supported opportunity to an `exploration_variable` target condition. It
identifies a fuzz-derived dimension or range; it is not conjoined into the
activation claim. Do not fix one concrete historical value unless an anchor
requires it.

### Observation candidates

Use `behavior_observation` when behavior should be recorded but no sound
pass/fail expectation is established. Use `behavior_check` only when the
expected Predicate is independently supported by the supplied sources.

### Limitations

Use limitations to narrow a branch, mark a mapping partial, or justify deferral.
Each limitation uses its exact `/learned_hypothesis/limitations/<index>` path.
Do not silently turn an uncertainty into a fixed Constraint.

## 6. Validity and exploration

`expected_valid` means supplied current-contract evidence supports that the
planned inputs are intended to satisfy the API contract, including valid
boundary states. `intentionally_invalid` means supplied evidence supports that
one explicit API condition is violated to test safe handling. Unrelated
validity and safety requirements still hold.

`contract_boundary_unresolved` is mandatory when the supplied evidence cannot
distinguish those two claims. Historical failure, current rejection, or an
intuitive boundary classification alone is not sufficient. Every branch records
an `input_validity_basis`: `api_contract`, `knowledge_supported`,
`canonical_baseline_definition`, or `unresolved`, with exact source references
where evidence exists. `unresolved` pairs only with
`contract_boundary_unresolved`; the other intents must not use it.

The default branch uses `canonical_baseline_definition`, cites no Knowledge,
and is copied exactly from the reviewed Baseline into bug-aware modes.

Every Knowledge branch must leave at least one target-API input degree of
freedom influenced by Fuzzer bytes. A selector byte does not count. Do not copy
all historical shapes, dtypes, values, layouts, and contexts into one branch.
The Strategy layer performs the final transitive dataflow check.

## 7. Predicates

Predicates are the current implementation vocabulary, not a defect taxonomy.
Use only Contract-declared IDs and exact argument keys. Use exact API Profile
parameter/return IDs or allowed `context.*` subjects. Property paths are
normalized lowercase dot paths, never source code, method calls, generated
variables, Helper IDs, or Primitive IDs.

If the intended meaning cannot be represented without distortion, defer the
Knowledge rather than choosing a nearby Predicate.

## 8. Source references

Every Constraint, Target Condition, Observation, and Check has at least one
source reference. Emit `source_type`, exact supplied `source_id`, and exact JSON
Pointer `source_path`; the Builder adds version and hash.

Knowledge paths are limited to:

```text
/learned_hypothesis
/learned_hypothesis/limitations/<index>
/exploration_guidance/historical_anchors/<index>
/exploration_guidance/variation_opportunities/<index>
/exploration_guidance/observation_candidates/<index>
```

API Profile paths must resolve in the supplied compact view. Do not cite Pattern
or Report directly.

## 9. Runtime monitoring and behavior checks

Crash, signal, sanitizer, timeout, hang, and OOM monitoring are fixed Runner
responsibilities shared by all groups. Do not add a default `no_crash` check to
every branch.

A semantic behavior check must specify subjects, optional preconditions, one
expected Predicate, source references, and `required` or `preferred` status.
An observation without a justified expected outcome remains record-only.

## 10. Output verification

Before returning, verify:

- every supplied Knowledge has one decision;
- every material Knowledge component has one explicit mapping;
- every represented or partially represented mapping resolves to an exact
  branch element that cites the same Knowledge path;
- every deferred mapping has no element reference and states the deferred scope;
- every included decision lists existing Knowledge-directed branches and every
  deferred decision lists none;
- exactly one default branch exists and no generic branch exists;
- every Knowledge-directed branch cites only included Knowledge;
- every branch-local Knowledge source equals a branch `source_knowledge_id`;
- each included Knowledge has at least one substantive cited contribution;
- each Knowledge branch has at least one condition, observation, or check;
- every source path resolves in its supplied artifact;
- every branch validity intent has a compatible evidence basis;
- every Predicate uses a declared argument contract;
- no risk dimensions, Oracle categories, code, Helper calls, Primitive IDs,
  concrete historical reproducer, budget share, or hidden reasoning is emitted.
