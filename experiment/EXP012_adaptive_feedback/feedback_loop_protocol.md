# Adaptive Feedback Loop Protocol v0.5

## 1. Purpose

This protocol defines the deterministic outer feedback loop used by the
`bug_aware_adaptive` experimental mode.

After each eligible fuzzing round, the feedback controller:

1. validates the supplied round evidence;
2. records the Round Gate Result, per-Branch diagnoses, and Coverage trend;
3. selects one deterministic Budget Action and Run Disposition;
4. emits one structured Materialization Request for an effective budget change;
5. uses the existing HarnessSpec, Strategy, and Harness Builders in deterministic
   feedback modes to validate and materialize the candidate;
6. records the Materialization Outcome and retains the correct accepted state.

The feedback controller does not call an LLM.

Bug-aware Static H0 is synthesized once through the existing pipeline and is
also the exact starting HarnessSpec, Strategy, and Harness Artifact for round 1
of every Adaptive repeat. Runtime feedback does not modify Knowledge or
Strategy semantics and does not invoke an LLM.

## 2. Layer Boundary

The feedback layer consumes exact references to:

- the current executable HarnessSpec: shared Static H0 before the first
  accepted adjustment, otherwise the latest accepted Adaptive revision;
- its validated Strategy Plan;
- its compiled Harness Artifact;
- the completed Fuzzing Round record;
- the corresponding runtime instrumentation snapshot;
- the normalized target-scope coverage summary;
- the frozen Adaptive Feedback Policy.

The feedback layer produces:

- one immutable Feedback Decision record;
- one Budget Action;
- one Materialization Outcome;
- one Run Disposition;
- optionally, one candidate HarnessSpec revision.

The feedback layer does not:

- extract or modify historical Knowledge;
- redefine API validity;
- select Helper functions or Strategy Primitives;
- generate arbitrary Strategy Steps;
- generate or edit C++ code;
- calculate raw coverage from compiler artifacts;
- classify a crash or Oracle failure as a confirmed Bug;
- change the total experimental time budget;
- carry state across APIs, groups, or independent repeats.

Metric calculation, crash adjudication, and experiment scheduling are owned by
their respective layers.

## 3. Fixed and Mutable State

### 3.1 Fixed State

The following remain unchanged throughout one Adaptive repeat:

- target framework, version, API, and overload;
- API and Helper Profile references;
- selected Knowledge and Knowledge decisions;
- global and Branch-local validity constraints;
- Branch set, Branch kinds, and Branch identifiers;
- Branch exploration goals;
- Branch validity intents;
- Target Properties;
- Activation Targets and predicates;
- Oracle Requirements and expected behavior;
- Strategy Primitive and Helper semantics;
- total round budget;
- feedback policy version;
- initial corpus and repeat seed policy.

A feedback action must not weaken validity, Activation, or Oracle definitions in
order to improve a measured rate.

### 3.2 Mutable State

Protocol v0.5 permits modification of only:

- positive Branch budget allocations;
- revision lineage and provenance;
- lifecycle state associated with candidate acceptance or rollback.

Branch creation, removal, merging, splitting, and semantic parameter adjustment
are outside Protocol v0.5.

## 4. Activation Accounting

Individual Activation Targets retain their existing runtime observations.

For every Branch with one or more Activation Targets, the generated Harness
provides one Branch-level combined Activation assessment per executed fuzz
case:

- `branch_activation_checked`: all required Activation Target predicates were
  evaluated successfully and produced Boolean results for that Branch;
- `branch_activation_true`: all required Activation Target predicates evaluated
  to true in the same fuzz case;
- `branch_activation_unevaluable`: a combined assessment was attempted, but at
  least one required predicate could not produce a Boolean result and no
  successful combined check was recorded for that fuzz case;
- `branch_activation_check_error`: a Branch checker failed because of an
  implementation or execution error.

`branch_activation_true` is a subset of `branch_activation_checked`. The
checked, unevaluable, and checker-error outcomes are mutually exclusive for one
Branch in one fuzz case, and each counter is incremented at most once per fuzz
case.

The Branch Activation Rate is defined only when the corresponding checked count
meets the minimum sample requirement in the Adaptive Feedback Policy:

```text
branch_activation_rate
=
branch_activation_true
/
branch_activation_checked
```

Target-level `activation_checked`, `activation_true`,
`activation_unevaluable`, and `activation_check_error` counts remain available
for Evaluation Target metrics and diagnosis. They are distinct from the
Branch-level counters and must not be summed or otherwise aggregated to infer
joint Branch activation.

A Branch without required Activation Targets has no Branch Activation Rate.

## 5. Feedback Evidence Eligibility

Before diagnosis, the controller verifies that all supplied evidence belongs to
the same API, experimental mode, repeat, round, HarnessSpec revision, Strategy
Plan, and Harness Artifact.

At minimum:

- the experimental group is `bug_aware_adaptive`;
- HarnessSpec and Strategy modes match and are either shared
  `bug_aware_static` H0 or a repeat-scoped `bug_aware_adaptive` revision;
- the Harness Artifact passed static validation and compilation;
- runtime `artifact_id` matches the Harness Artifact;
- runtime `generation_key` matches the Harness Artifact;
- runtime `site_count` matches the Instrumentation Map;
- all required metric sites resolve through the Instrumentation Map;
- runtime counters are non-negative and internally consistent;
- `invalid_site_records` is zero;
- the run termination reason is known;
- coverage evidence identifies the expected framework build and target scope;
- no required input artifact is missing or unresolved;
- every Branch-level Activation checker-error count is at or below the frozen
  policy limit.

A final runtime snapshot is preferred. A periodic snapshot may be used only when
the Fuzzing Round record confirms the expected round termination and the
snapshot satisfies the policy's permitted staleness bound.

The eligibility gate produces exactly one Round Gate Result:

- `evidence_ineligible`: required evidence is missing, inconsistent, stale, or
  belongs to a different run or artifact;
- `crash_or_sanitizer_candidate`: the round contains an observation that must be
  preserved and handed to crash analysis before adaptation;
- `insufficient_total_samples`: evidence is structurally eligible but the
  completed-iteration count is below the policy minimum;
- `eligible`: the evidence may be used for Branch diagnosis and adaptation.

An ineligible or under-sampled round does not modify HarnessSpec. These values
are diagnoses, not Budget Actions.

## 6. Round State Machine

Every Adaptive repeat begins from the exact reviewed Static H0 HarnessSpec,
Strategy, and Harness Artifact used by the Static group. No independent
Adaptive H0 synthesis occurs.

For every non-final round:

```text
accepted HarnessSpec
        +
accepted Strategy
        +
compiled Harness
        ↓
fuzzing round
        ↓
normalized round evidence
        ↓
Round Gate Result
        ↓
per-Branch diagnosis + global Coverage trend
        ↓
Budget Action + Run Disposition
        ↓
optional candidate HarnessSpec revision
        ↓
downstream validation and materialization
        ↓
Materialization Outcome
```

A `retain_current` Budget Action reuses the current HarnessSpec, Strategy, and
Harness. Only an effective `reallocate_budget` action may create a candidate
revision.

No unused HarnessSpec revision is generated after the final scheduled round.

## 7. Feedback Assessment

Assessment is staged so that upstream failures are not misinterpreted as
downstream ineffectiveness.

### 7.1 Round Gate Result

The controller first assigns one result from Section 5. Only `eligible` permits
the remaining assessment stages.

### 7.2 Per-Branch Diagnosis

Each active Branch receives exactly one primary status, using the following
precedence:

1. `branch_under_sampled`;
2. `branch_rejection_dominated`;
3. `branch_target_unreachable`;
4. `branch_activation_unevaluable`;
5. `branch_activation_absent`;
6. `branch_activation_rare`;
7. `branch_oracle_unevaluable`;
8. `branch_healthy`.

`branch_activation_unevaluable`, `branch_activation_absent`, and
`branch_activation_rare` apply only to a Branch with Activation Targets.
Absent and rare require enough successful checked cases; unevaluable requires
enough attempted assessments but no successful checked cases. An unevaluable
Branch is neither a budget recipient nor a donor. A Branch without Activation
Targets is evaluated without a Branch Activation Rate.

Lower-priority observations may be preserved as supporting diagnostics. They do
not independently trigger another budget modification in the same transition.

### 7.3 Global Coverage Trend

Eligible coverage evidence produces one of:

- `coverage_growing`;
- `coverage_plateau`;
- `coverage_unavailable`.

Coverage trend is global to the registered target scope. Protocol v0.5 does not
claim Branch-level Coverage attribution unless an independently validated
Branch-level Coverage record is supplied.

### 7.4 Policy Evaluation

The frozen Adaptive Feedback Policy maps the Round Gate Result, ordered
per-Branch diagnoses, global Coverage trend, and relevant prior Feedback
Decisions to one Budget Action and one Run Disposition.

Exact thresholds, history windows, and consecutive-round requirements are
defined only by the policy.

## 8. Decision Semantics

### 8.1 Budget Action

Exactly one Budget Action is recorded:

| Budget Action | Meaning |
| --- | --- |
| `retain_current` | Keep the current accepted Branch allocation |
| `reallocate_budget` | Attempt a policy-bounded Branch-budget change |

Only an effective `reallocate_budget` action creates a candidate HarnessSpec
revision. If the proposed allocation resolves to the current selector slots,
the effective action is `retain_current`.

### 8.2 Materialization Outcome

Exactly one Materialization Outcome is recorded:

| Materialization Outcome | Meaning |
| --- | --- |
| `not_attempted` | No candidate revision was created |
| `accepted` | The candidate passed every gate and became current |
| `rejected` | The candidate failed a gate and the accepted parent was retained |

Rollback is the procedure following a rejected candidate; it is not a Budget
Action.

### 8.3 Run Disposition

Exactly one Run Disposition is recorded:

| Run Disposition | Meaning |
| --- | --- |
| `continue` | The Runner may compute another feedback adjustment after a later round |
| `freeze_adaptation` | Keep the latest valid triplet and run all remaining scheduled fuzzing rounds without further adjustment |
| `handoff_crash_analysis` | Preserve the observation and transfer it to crash analysis |
| `abort_repeat` | End the repeat only for an unrecoverable method or infrastructure failure |

A crash, Sanitizer finding, target exception, or Oracle failure is a candidate
observation, not a confirmed Bug. The feedback controller does not alter
HarnessSpec in response before the crash-analysis policy is applied.

## 9. Deterministic Budget Reallocation

The adaptive rules are defined by the immutable, versioned
`policies/adaptive_feedback_policy.json`. The initial allocation policy in
EXP011 governs the shared Static H0. The adaptive policy governs every
feedback-derived allocation.

Branch allocation is calculated in the same 256-slot selector space used by the
Harness Generator. The feedback controller:

1. converts current Branch shares to effective selector-slot allocations;
2. applies the adaptive policy's eligibility, donor, recipient, floor, ceiling,
   and maximum-step rules;
3. preserves at least one slot for every active Branch;
4. ensures that the total allocation equals 256 slots;
5. resolves ties by canonical `branch_id` order;
6. derives each stored share as `selector_slots / 256`;
7. confirms that candidate selector ranges differ from the current ranges.

The adaptive policy owns all numeric thresholds and history rules, including:

- minimum usable sample counts;
- Branch floors and ceilings;
- maximum transfer per transition;
- Activation and Coverage thresholds;
- consecutive-round and retry limits;
- permitted snapshot staleness;
- deterministic tie-breaking.

The policy distinguishes a first eligible low or zero Activation observation
from persistent zero Activation after an exploration boost. It must prevent
unbounded repeated increases to a Branch that remains ineffective.

A proposed allocation that materializes to the same selector ranges yields
`retain_current` and `not_attempted`.

## 10. HarnessSpec Revision

A new HarnessSpec is created only for an effective
`reallocate_budget` action.

For the first accepted adjustment in one repeat:

- the candidate uses a repeat-scoped Adaptive `spec_id` and revision 1;
- `parent_revision_ref = null`;
- `derived_from_spec_ref` references the exact shared Static H0.

For later adjustments in the same repeat:

- the Adaptive `spec_id` is unchanged;
- the revision number increments by one;
- `parent_revision_ref` references the immediately preceding accepted
  Adaptive revision;
- `derived_from_spec_ref = null`.

Every candidate uses `revision_trigger = execution_feedback`,
`change_scopes = [budget_allocation]`, preserves every non-budget semantic
field, and references the exact Materialization Request and Adaptive Feedback
Policy. The request records both allocation vectors. It exists before
materialization; therefore the candidate does not claim to reference the final
Feedback Decision.

The Adaptive Feedback Policy is immutable during a registered experiment. A new
policy version is not created for each round.

## 11. Strategy and Harness Materialization

A Budget-only candidate may use deterministic Strategy rebinding only when all
of the following hold:

1. the effective Budget Action is `reallocate_budget`;
2. the source HarnessSpec is the current executable state and its exact
   reference matches the Materialization Request;
3. Branch identifiers, order, kinds, and count are unchanged;
4. only Branch budget shares and permitted revision, policy, Materialization
   Request, provenance, review, or lifecycle metadata differ;
5. Knowledge, validity constraints, Branch semantics, Target Properties,
   Activation Targets, and Oracle Requirements are unchanged under canonical
   comparison;
6. API Profile, Helper Profile, Primitive Catalog, and Harness Template
   references and versions are unchanged;
7. the parent Strategy is valid;
8. the new selector slots differ from the parent and satisfy the adaptive
   policy.

Because one Strategy identity implements one exact HarnessSpec revision, the
candidate receives a new Strategy identity whose revision starts at 1. The
implementation plan is copied from the accepted parent Strategy, exact
references and provenance are rebuilt deterministically, and the full Strategy
validator is rerun.

This process does not call an LLM. If any listed condition fails, deterministic
rebinding is prohibited and the candidate is rejected.

The Harness Generator then materializes and validates a new Harness Artifact.
Only selector ranges and exact artifact identity may change; implementation,
Activation, and Oracle semantics remain fixed.

## 12. Acceptance and Rollback

A `reallocate_budget` candidate receives `accepted` only when all required gates
pass:

1. HarnessSpec structural validation;
2. HarnessSpec same-identity parent or cross-identity H0 derivation,
   Materialization Request, and policy-reference validation;
3. canonical Budget-only diff validation;
4. deterministic Strategy rebinding;
5. Strategy structural and semantic validation;
6. Harness materialization;
7. Harness static validation;
8. compilation;
9. required preflight execution checks.

After acceptance:

- the candidate becomes the repeat-local current executable revision;
- the immutable parent remains available to Static and as a rollback source;
- the next scheduled Adaptive round uses the new Harness.

If any gate fails:

- the Materialization Outcome is `rejected`;
- the candidate remains rejected;
- the parent remains current;
- the previously accepted Harness is retained;
- the failure stage and diagnostics are recorded;
- rollback is performed without generating another candidate.

When no candidate is created, the Materialization Outcome is `not_attempted`.

Acceptance, rejection, and rollback never overwrite an earlier HarnessSpec,
Strategy, Harness, or Feedback Decision record.

## 13. Human Review

Before the main experiment:

- the Adaptive Feedback Policy is fully reviewed and frozen;
- shared Static H0 is reviewed before execution;
- Adaptive round 1 references that exact H0 rather than an independently
  synthesized equivalent record.

During an Adaptive repeat:

- no human modifies a Feedback Decision;
- no human edits a candidate revision;
- no per-round human approval is required for a policy-generated Budget-only
  revision that passes every acceptance gate.

After execution:

- Pilot revisions and decisions are fully audited;
- exceptional outcomes are fully audited;
- normal main-experiment revisions may use a preregistered stratified sample;
- audit findings do not overwrite executed artifacts.

Material errors are handled through the experiment's preregistered exclusion or
rerun policy.

## 14. Isolation and Fairness

Feedback state is isolated by:

```text
target API
+
experimental group
+
independent repeat
```

No allocation, Corpus, metric, or decision state is shared across APIs, groups,
or independent repeats.

Corpus evolution may continue across rounds within one repeat.

Structured Baseline and Bug-aware Static use the same round boundaries and
restart protocol as Bug-aware Adaptive, but they do not receive feedback-driven
HarnessSpec revisions.

Each Adaptive repeat starts from the same registered revision-1 allocation. A
later repeat must not inherit the final allocation of an earlier repeat.

## 15. Stopping Conditions

The feedback controller does not directly stop a fuzzing process. It returns a
Run Disposition, and the experiment Runner applies that disposition at the
round boundary.

The Runner terminates the current repeat when the registered experiment
protocol or Adaptive Feedback Policy requires it, including:

- completion of the final scheduled round;
- `handoff_crash_analysis`;
- repeated unusable evidence;
- repeated rejected candidates;
- absence of an effective permitted adjustment;
- an unrecoverable infrastructure or capability failure.

Final-round completion is a scheduler condition, not a feedback diagnosis. No
unused next HarnessSpec revision is created after it.

Termination does not imply that a Bug was found or that the current HarnessSpec
is optimal.

## 16. Provenance Requirements

Every Feedback Decision must preserve exact references or hashes for:

- the current HarnessSpec revision;
- the current Strategy Plan;
- the current Harness Artifact;
- the Fuzzing Round record;
- runtime and coverage evidence;
- the Adaptive Feedback Policy;
- the feedback-controller implementation;
- any candidate and accepted downstream artifacts.

It must also preserve:

- the Round Gate Result;
- ordered per-Branch primary and supporting diagnoses;
- the global Coverage trend;
- the Budget Action;
- the Materialization Outcome;
- the Run Disposition;
- old and proposed selector allocations when reallocation was attempted;
- rejection or termination reasons when applicable.

The Feedback Decision Schema defines the exact record fields. This protocol
defines their operational meaning only.

## 17. Deferred Extensions

The following are intentionally deferred:

- bounded exploration-parameter adjustment;
- Branch creation, removal, merging, or splitting;
- Knowledge reselection;
- Strategy semantic regeneration;
- LLM-based diagnosis or revision;
- Branch-level Coverage attribution;
- cross-repeat or cross-API learning.

Any such extension requires a new protocol and policy version and must not be
enabled silently during the main experiment.
