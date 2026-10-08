# Strategy Plan Human Review Rules v1.2

## Scope

Human review evaluates one immutable, machine-valid Strategy Plan. Reviewers
record a decision and evidence-scoped findings in a separate immutable record.
They do not edit the generated Plan, replace fuzz-derived values with historical
inputs, add undocumented checks, or judge effectiveness from the Plan alone.

## Criteria

- `SR-01 Provenance`: HarnessSpec, approved HarnessSpec review, Catalog, API
  Profile, Helper Profiles, Builder, Contract, and Rules references are exact.
- `SR-02 Mapping completeness`: each required HarnessSpec v2.2 structured
  element is bound exactly once in its applicable branch.
- `SR-03 Exploration freedom`: exploration variables remain fuzz-dependent and
  are not converted to unconditional guards or complete historical inputs.
- `SR-04 Semantic fidelity`: predicates, roles, phases, target-call ports,
  optional None, API defaults, and return bindings preserve source semantics.
- `SR-05 Observation ownership`: in-process observations use Harness steps;
  termination/timeout/signal/sanitizer observations use Runner bindings; prose
  observations are not silently promoted to behavior checks.
- `SR-06 Catalog/emitter consistency`: selected Primitive IDs, ports,
  parameters, slots, types, failure outcomes, and emitters are mutually
  consistent and locally materializable.
- `SR-07 Control equality`: for Static/Adaptive plans, `br_default` exactly
  equals the approved controlled-baseline Strategy branch.
- `SR-08 Claim scope`: the Plan makes no claim of bug reproduction, activation
  frequency, detection effectiveness, or statistical superiority.
- `SR-09 Auxiliary compatibility`: source-backed companion arguments do not
  make every target invocation fail before the intended relation is evaluated.
  Mixed valid/invalid domains and explicitly targeted violations remain legal.

## Decisions

Check property-specific domains, not only byte-dependence: fill variation cannot
establish shape/numel variation. Check ordinary recipes only in expected_valid
branches; boundary exploration must not inherit these guards. Concrete smoke
inputs are witnesses, not fixed test cases or output invariants. Review uniform
fill, fixed rank/dtype and other coverage omissions as scoped limitations.

Require a saved local materialization preflight. Compilation/smoke evidence may
increase confidence but is not proof of exploration effectiveness. Caught
c10::Error at the target call is an API exception, not a native crash. After-call
observations are absent on this path. Signal/timeout/sanitizer and detailed
termination snapshots require Runner capability; a binding is a request, not
evidence that the Runner captured every requested subject.

Review repair must consume an exact-hash needs_revision record for the parent;
Artifact production requires an exact approved review for the new revision.
Do not edit a generated Plan to approve it. Catalog/resource changes are versioned
and invalidate old approval for the new subject. No full-scale coverage claim is
allowed for a currently unsupported capability.

`approved` requires zero blocking findings. Advisory findings may remain only
when they do not alter executable semantics or experimental comparability.

`needs_revision` requires at least one blocking finding tied to a criterion,
field path, and concrete evidence reference. Repair creates a new immutable
Strategy revision and a new review subject.

## Sampling policy

For the small-scale pilot, review every generated Strategy Plan. For a frozen
large-scale pipeline, review all new Catalog/API capability combinations and a
reproducible stratified sample of remaining Plans by API signature class,
HarnessSpec mode, predicate family, observation phase, and return cardinality.
Any blocking sampled defect pauses the affected stratum and triggers expanded
review plus a versioned Builder/Catalog repair; it is not repaired by editing
individual Plans.
