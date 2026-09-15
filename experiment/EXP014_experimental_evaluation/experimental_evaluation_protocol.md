# Experimental Evaluation Protocol

## 1. Document Status

- Protocol version: `0.1-draft`
- Experiment phase: `pilot_design`
- Framework: PyTorch 2.10
- Scope: internal three-group evaluation plus an auxiliary FlashFuzz comparison

This document defines the research questions, experimental groups, API selection, execution units, primary metrics, aggregation rules, and validity controls. Machine-readable configuration, runtime orchestration, and result-analysis implementations are defined separately after this protocol is reviewed.

## 2. Evaluation Boundary

The evaluation covers the pipeline from HarnessSpec synthesis to fuzzing results:

```text
API/Profile + Helper/Profile
        + optional Historical Bug Knowledge
                    ↓
              HarnessSpec
                    ↓
              Strategy Plan
                    ↓
              Harness Artifact
                    ↓
         Fuzzing / Instrumentation
                    ↓
       Feedback / Crash Triage / Metrics
```

EXP011 owns HarnessSpec, Strategy, and Harness generation. EXP012 owns deterministic feedback decisions and round records. EXP013 owns abnormal-event admission, deduplication, reproduction, and fault attribution. EXP014 coordinates the experiment and computes evaluation results; it does not redefine those artifacts.

### 2.1 Machine-interface conventions

- Canonical repeat IDs use `repeat_NNN`; canonical round IDs use
  `round_NNN`. A Task Key is
  `api_id:group_id:repeat_NNN:round_NNN`. Numeric repeat and round indexes
  remain separate fields.
- An Artifact Reference identifies a logical JSON record and hashes its
  canonical JSON representation. A File Reference identifies one repository
  file and hashes its raw bytes. The two reference types are not
  interchangeable.
- The Evaluation Target Manifest, Execution Index, Result Provenance, and
  Runtime Snapshot conform to their EXP014 JSON Schemas. Cross-record identity,
  task-universe, hash, and API-set checks remain Analyzer responsibilities.
- Missing or incomplete runs are retained as attrition and diagnostic
  per-round results. They do not enter primary metrics that require a completed
  900-second run.
- Generated `summary.md` files are human-readable views only. JSON and CSV
  artifacts remain authoritative.

## 3. Research Questions

### RQ1: Harness Realization

Under independently bounded HarnessSpec and Strategy synthesis attempts, followed by deterministic validation, materialization, compilation, and preflight checks, can historical Bug Knowledge be transformed into executable and runtime-observable test Harnesses?

Primary metrics:

1. `RQ1_M1_E2E_HARNESS_RATE`
2. `RQ1_M2_OBSERVATION_REACH_RATE`

### RQ2: Static Knowledge Effectiveness

Does historical Bug Knowledge improve static fuzzing effectiveness relative to a structurally equivalent baseline without Knowledge?

Comparison: `structured_baseline` versus `bug_aware_static`.

Primary metrics:

1. `RQ2_M1_TARGET_ACTIVATION_COVERAGE`
2. `RQ2_M2_REPRODUCIBLE_ANOMALY_YIELD`

### RQ3: Adaptive Feedback Effectiveness

Under equal fuzzing time, runtime resources, and the same initial Bug-aware Harness, does deterministic feedback further improve risk-condition exploration and reproducible framework-anomaly discovery?

Comparison: `bug_aware_static` versus `bug_aware_adaptive`.

Primary metrics:

1. `RQ3_M1_ADAPTIVE_ACTIVATION_GAIN`
2. `RQ3_M2_POST_FEEDBACK_ANOMALY_GAIN`

## 4. Experimental Groups

### 4.1 Structured Baseline

- Does not expose Historical Bug Knowledge to HarnessSpec or Strategy synthesis.
- Does not apply feedback-driven revisions.
- Uses the same API Profile, approved Helper set, Primitive infrastructure, Harness template, instrumentation framework, PyTorch build, resource limits, and fuzzing schedule as the other internal groups.
- Is an internal controlled baseline, not a strict reproduction of FlashFuzz.

### 4.2 Bug-aware Static

- Exposes approved API-specific Historical Bug Knowledge to HarnessSpec synthesis.
- Uses a fixed initial Bug-aware Harness for all rounds and repeats.
- Records round feedback inputs but does not apply feedback-driven revisions.

### 4.3 Bug-aware Adaptive

- Starts each repeat from the exact initial Harness used by Bug-aware Static.
- May apply deterministic feedback after rounds 1 and 2.
- Does not create a new revision after the final round.
- Rolls back to the latest valid Harness if a proposed revision cannot be validated, materialized, compiled, or passed through preflight.

### 4.4 FlashFuzz Original

FlashFuzz Original is an auxiliary external baseline on compatible overlapping APIs. It is reported separately whenever environment, API, Harness, or execution differences prevent a controlled comparison. Other fuzzers are discussed as related work or in a capability table unless they can be reproduced under the same evaluation conditions.

## 5. API Selection

### 5.1 Candidate Sources

APIs may be proposed from:

- APIs previously evaluated by FlashFuzz;
- APIs appearing in selected public benchmark datasets;
- additional PyTorch 2.10 APIs with usable historical Issues and current implementation support.

Source labels describe provenance only. They do not create separate experimental groups, and one API may have multiple source labels.

### 5.2 Inclusion Criteria

An API/overload is selected before synthesis results are observed when all of the following hold:

- the target C++ API/overload exists in the frozen PyTorch 2.10 build;
- its API Profile is verified;
- required Helper and Primitive capabilities are available or have a documented non-blocking fallback;
- at least one reviewed API-specific Knowledge record exists;
- at least one Knowledge-derived risk condition is suitable for deterministic runtime measurement;
- the API is not a duplicate of another selected API/overload;
- all three internal groups can use the same runtime environment and resource limits.

### 5.3 Exclusion Criteria

Exclusion requires a recorded reason, such as an unavailable API binding, unsupported mandatory capability, absent reviewed Knowledge, non-measurable risk condition, or duplicate overload. APIs must not be selected or removed according to observed group performance.

### 5.4 Analysis Status

The frozen selected API set is the denominator for RQ1. RQ2 and RQ3 use completed paired executions when the required comparison artifacts exist. Generation or execution attrition remains reported and must not be silently removed. The FlashFuzz-compatible subset is only a reporting subset of the selected APIs, not a separate API category.

The capability table is a derived audit view, not a second source of truth. It is generated from the frozen API Profiles, Helper Profiles, Primitive Catalog, Evaluation Target Manifest, and recorded synthesis outcomes. It reports binding availability, capability readiness, target count, initial-Harness status, FlashFuzz compatibility, and any exclusion reason.

## 6. Synthesis and Artifact Policy

For each API, the main experiment creates:

- one fixed Structured Baseline Harness;
- one fixed initial Bug-aware Harness `H0` through
  `bug_aware_static` synthesis.

Static and every Adaptive repeat reference that exact H0 HarnessSpec, Strategy,
core source, instrumented source, and binary for round 1. There is no
independent Adaptive H0 synthesis.

HarnessSpec synthesis and Strategy synthesis each allow at most three completed model responses for one API, mode, and revision. They are separate budgets: a successful path can therefore consume at most three HarnessSpec responses and three Strategy responses. Strategy synthesis starts only after HarnessSpec validation succeeds.

- Attempt 1 uses the frozen base prompt.
- Attempts 2 and 3 may add only normalized, deduplicated validator diagnostics from earlier attempts.
- An empty, malformed, off-contract, or validation-failing completed response consumes one synthesis attempt.
- A request that produces no model response because of an external service or transport failure is recorded separately as an infrastructure attempt and follows the frozen infrastructure-retry policy.
- Model identity, decoding configuration, Contract version, and base prompt template remain fixed across repair attempts.

RQ1 evaluates the Bug-aware initial-Harness synthesis case. Baseline synthesis and Adaptive revisions retain their own attempt records but are not additional RQ1 samples.

After an effective feedback decision, the experiment Runner orchestrates the
existing Builders: HarnessSpec applies the structured request without an LLM,
Strategy deterministically rebinds the prior implementation plan, and Harness
generation materializes, validates, compiles, and preflights the candidate.
The Runner records the resulting references for final Feedback Decision
validation; it does not implement these transformations itself.


Harness Artifact materialization is deterministic. A failed Artifact must be recorded and must not be regenerated repeatedly to obtain a successful sample. A confirmed infrastructure defect may be fixed only through a documented tool revision before restarting the affected formal experiment scope.

Instrumentation creates a derived Artifact rather than mutating the generated source in place. Preserve separate identities and SHA-256 hashes for the core Harness source, instrumented Harness source, and compiled binary. The instrumented Artifact records its parent Artifact, Evaluation Target Manifest revision, Instrumenter version, and Instrumenter content hash. Static and Adaptive `H0` hashes must match at both the core-source and instrumented-source stages; Baseline hashes are not expected to match them.

Ordinary fuzzing repeats reuse the fixed initial Harness. Independent repeated LLM synthesis, if studied, is a separate variability experiment and is not mixed with the main fuzzing repeats.

## 7. Experimental Units and Pilot Matrix

The terms below are distinct:

- `synthesis_attempt`: one completed LLM response within one stage-local bounded repair process;
- `fuzz_repeat`: one independent 900-second fuzzing execution sequence;
- `round`: one 300-second stage within a repeat;
- `run`: one API, group, and repeat across all three rounds.

The provisional pilot matrix is:

```text
selected API
× 3 internal groups
× 3 independent fuzz repeats
× 3 sequential rounds
× 300 seconds per round
```

Each run therefore receives 900 seconds of fuzzing time. Each API/group receives 2,700 seconds over three repeats. Synthesis, compilation, coverage replay, feedback computation, crash replay, and human review time are not deducted from fuzzing time and are reported separately where relevant.

## 8. Seeds, Corpus, and Round Transitions

- A frozen `master_seed` and the tuple `(api_id, fuzz_repeat_id, round_id)` deterministically derive each round seed; `group_id` is excluded from the derivation.
- Different repeats use different derived seeds, while all three groups receive the same paired seed for the same API, repeat, and round.
- The actual integer passed to the fuzzer is recorded. Its supported range is fixed after verifying the runtime interface.
- Each repeat begins with an independent copy of the same frozen initial Corpus.
- Runtime-generated Corpus is not shared across groups or repeats.
- Within one repeat, each round inherits its own group's previous-round Corpus.
- All three groups restart the fuzzer process at round boundaries.
- Baseline and Static restart without changing their Harnesses.
- Adaptive may materialize a valid revision before the next round.

Round-1 Static and Adaptive executions use the same `H0`, initial Corpus, and paired seed. Their separate runtime records remain necessary because system-level nondeterminism may still occur.

A round proceeds through `prepare`, `active_fuzzing`, `freeze_corpus`, `export_runtime`, `coverage_replay`, optional `feedback`, and `prepare_next_round`. The 300-second budget applies only to accumulated active fuzzing time. Compilation, snapshot export, hashing, coverage replay, feedback, and next-round preparation are outside this budget and are timed separately.

The initial Corpus, each round-start Corpus, and each round-end Corpus have immutable Manifests containing file-relative paths, file hashes, aggregate hash, file count, total bytes, and parent-Manifest reference. The next round begins only after the preceding end Manifest is finalized and a valid next Harness or rollback Harness is available.

If an abnormal event terminates the fuzzer early, the event input is isolated and the process resumes the remaining active-fuzzing budget under a frozen restart limit. Repeated-event suppression, the restart limit, and unrecoverable termination conditions must be fixed in the experiment matrix before the main experiment.

## 9. Evaluation Targets and Instrumentation

A frozen Evaluation Target Set defines the Knowledge-derived runtime properties used for measurement. It is independent of group-specific HarnessSpec revisions.

- Baseline synthesis must not receive Knowledge, Evaluation Target descriptions, or risk-generation guidance.
- After Baseline generation, deterministic instrumentation may insert the same read-only target checkers used by Static and Adaptive.
- A target checker must inspect the actual target-call arguments or result at its authoritative observation point.
- Diagnostic observation points may be recorded, but each Evaluation Target has one authoritative activation decision.
- Equivalent runtime predicates are deduplicated while retaining all supporting Knowledge references.
- Every frozen Evaluation Target is a formal measurement target and enters the metric denominator; there is no required/optional Target distinction.
- Optional diagnostic observation points are not Evaluation Targets and never enter the denominator.
- Targets are equally weighted in the initial protocol.

Each Target is linked to Artifact-local instrumentation through an explicit
`evaluation_target` Trace Reference. For each Artifact Branch that implements a
Target, exactly one `activation_checked`, `activation_true`,
`activation_unevaluable`, and `activation_check_error` site carries that Target
reference. The Harness Artifact resolves those sites to `runtime_site_id`
values, and the Runtime Snapshot supplies their counts. Analysis groups all
matching Branch sites for the Target; it must not infer bindings from Branch
names, Knowledge text, event-key spelling, or position.

Static and Adaptive sites also reference their HarnessSpec Activation Target
and Target Property. Baseline sites reference the Evaluation Target only, so
measurement does not expose Knowledge to Baseline synthesis.
`activation_checked` counts successful Boolean evaluations, with
`activation_true <= activation_checked`.

Per round, an Evaluation Target resolves to one of:

- `not_checked`
- `checked_false`
- `checked_true`
- `unevaluable`
- `instrumentation_error`

An invalid Snapshot, missing binding, inconsistent counter, or invalid runtime
site produces `instrumentation_error`. Otherwise, any successful check
produces `checked_true` when a true event exists and `checked_false`
otherwise. With no successful check, an unevaluable event produces
`unevaluable`, a checker-error event produces `instrumentation_error`, and
no event produces `not_checked`. Successful checks take precedence over
unevaluable or checker-error occurrences from other iterations; the latter
counts remain diagnostic and a checker error makes the round ineligible for
adaptive budget decisions. The five-state result is determined per Target per
round before cumulative Target coverage is computed.

The frozen target set must not be changed after main-experiment execution begins without creating a new protocol and matrix revision.

## 10. Primary Metric Definitions

### 10.1 RQ1_M1_E2E_HARNESS_RATE

```text
number of selected APIs producing a valid, compiled, preflight-passed
initial Bug-aware Harness with all frozen target checkers materialized
/
number of APIs in the frozen selected API set
```

The result is reported as `n/N`, a percentage, and a binomial confidence interval.

### 10.2 RQ1_M2_OBSERVATION_REACH_RATE

For a completed Bug-aware Static round-1 execution:

```text
number of frozen Evaluation Targets whose authoritative checker completed
with checked_false or checked_true
/
total number of frozen Evaluation Targets for the API
```

`not_checked`, `unevaluable`, and `instrumentation_error` do not enter the numerator. If the initial Bug-aware Harness cannot run, this metric is unavailable rather than zero; the failure remains captured by RQ1_M1 and the number of computable APIs is reported. Adaptive round 1 is not treated as an additional Harness sample.

### 10.3 RQ2_M1_TARGET_ACTIVATION_COVERAGE

For a completed 900-second run:

```text
number of frozen Evaluation Targets observed as checked_true at least once
/
number of frozen Evaluation Targets for the API
```

The main comparison uses paired Baseline and Static runs. `not_checked`, `checked_false`, `unevaluable`, and `instrumentation_error` remain in the denominator but not the numerator. Event frequency is diagnostic and does not increase the number of distinct activated targets.

### 10.4 RQ2_M2_REPRODUCIBLE_ANOMALY_YIELD

```text
number of distinct EXP013 clusters classified as reproducible
framework anomalies and discovered during a completed 900-second run
```

Repeated events from the same cluster count once. Harness faults, expected input rejection, non-reproducible events, and unresolved attribution do not enter the numerator. Equal fuzzing budgets permit direct count comparison; a per-hour representation is an equivalent presentation.

Discovery position is the earliest Raw Abnormal Event in that run which later maps to the confirmed cluster, ordered by `(round_index, elapsed_fuzz_seconds_in_round, event_sequence_id)`. It is not the later triage or confirmation time. A cluster counts only when its Raw Event occurred within the run and its classification was completed by the frozen analysis cutoff.

### 10.5 RQ3_M1_ADAPTIVE_ACTIVATION_GAIN

For a paired API and repeat:

```text
cumulative KTAC at round k
=
number of distinct frozen Targets with checked_true in any round from 1 to k
/
total number of frozen Evaluation Targets for the API
```

The Target set and denominator remain unchanged across rounds and Harness revisions. Repeated activation of one Target counts once in the cumulative union.

```text
(Adaptive cumulative KTAC at round 3 - Adaptive cumulative KTAC at round 1)
-
(Static cumulative KTAC at round 3 - Static cumulative KTAC at round 1)
```

A positive value indicates activation gain beyond continued Static fuzzing. APIs already at full activation after round 1 remain in the main result and are marked as ceiling cases for diagnostic analysis.

### 10.6 RQ3_M2_POST_FEEDBACK_ANOMALY_GAIN

For a paired API and repeat:

```text
number of Adaptive reproducible framework-anomaly clusters first observed
in rounds 2 or 3
-
number of Static reproducible framework-anomaly clusters first observed
in rounds 2 or 3
```

Rounds 2 and 3 are post-feedback decision windows even when the decision retains the current budget, freezes adaptation, or rolls back a failed revision. A cluster is post-feedback only when its earliest Raw Event in that run occurs in round 2 or 3; a cluster already observed in round 1 cannot become a post-feedback discovery. Round-1 discoveries remain in total results.

## 11. Diagnostic Data

Diagnostic data support interpretation but are not additional primary RQ metrics. They include stage success and failure reasons, synthesis attempts, target-reach and valid-input rates, event-level activation frequency, Oracle evaluability, Coverage, execution throughput, feedback actions, rollback, runtime termination, and generation/compilation/feedback overhead.

Coverage is measured by replaying each frozen round Corpus with the same coverage build and scope. Cumulative union coverage at 300, 600, and 900 seconds and per-round new coverage may be reported. Coverage values are not equated with Bug discovery.

## 12. Failure and Missing-Data Policy

- Generation failures remain in the RQ1 denominator.
- Method-induced validation, compilation, preflight, or adaptive-revision failures are recorded as method outcomes and are not retried beyond their defined limits.
- Adaptive revision failure triggers rollback to the latest valid Harness without extending fuzzing time. When a valid shared `H0` and round 1 exist, `keep`, `stop`, failed revision, and rollback outcomes remain in the RQ3 paired denominator.
- The Runner preserves the latest valid source and binary so that a failed revision cannot erase the rollback path.
- Infrastructure failures are identified separately and may be rerun only under a frozen infrastructure-retry rule; original failure records are retained.
- Missing numeric results are not replaced with zero unless zero is the observed value.
- RQ2/RQ3 paired-result denominators and attrition reasons are reported explicitly.
- EXP013 cases unresolved at the analysis cutoff do not enter confirmed framework-anomaly counts and are reported separately.

## 13. Aggregation and Statistical Analysis

- Round-level values describe trajectories and are not independent samples.
- Repeat-level values are first aggregated within each API, using the median unless a metric definition requires set union.
- APIs are the main cross-system statistical units.
- RQ2 uses paired Baseline–Static comparisons.
- RQ3 uses paired Static–Adaptive comparisons.
- Report medians, interquartile ranges, paired differences, and the number of positive, zero, and negative API-level effects.
- RQ1 proportions use binomial confidence intervals.
- Paired inferential tests and effect sizes are frozen after the API count and pilot variance are known; p-values do not replace effect sizes and confidence intervals.
- Global unique-cluster unions are reported separately from repeat-level statistical observations.

## 14. Execution Order and Resource Control

Group execution order is balanced or generated from a frozen reproducible schedule so that one group is not always run first. Main fuzzing jobs do not compete for uncontrolled shared resources.

The following are fixed or recorded for every run:

- Docker image and PyTorch build identity;
- CPU, memory, thread, and sanitizer settings;
- API/Profile, Helper/Profile, HarnessSpec, Strategy, Harness, and instrumentation references;
- initial Corpus identity;
- group, repeat, round, and seed;
- start, end, and termination status.

The matrix freezes an analysis-cutoff rule before execution. The rule derives an absolute UTC cutoff from the terminal time of the last core run plus a fixed delay. The resolved timestamp is stored in result provenance rather than written back into the frozen matrix. EXP013 records a UTC `revision.created_at` on every Crash Case revision; primary analysis selects the newest valid revision whose timestamp is not later than the cutoff. Confirmation after that cutoff does not retroactively change the frozen primary analysis and may be reported only as a later revision.

## 15. Pilot and Main-Experiment Freeze

The initial values of three repeats, three rounds, and 300 seconds per round are pilot parameters. Pilot execution may reveal unavailable fields, instrumentation defects, insufficient runtime, or excessive variance.

Before the main experiment, freeze:

- selected APIs and overloads;
- Evaluation Targets and detector versions;
- group definitions;
- seeds, repeats, rounds, and budgets;
- resource and execution-order policies;
- metric formulas and analysis cutoff;
- feedback policy and allowed adjustment scope;
- exclusion, retry, rollback, and missing-data rules.

Pilot runs are labeled separately and are not silently merged into main-experiment results.

A `draft` matrix is mutable and non-executable. A `frozen` matrix has no unresolved bindings, has passed Schema and semantic validation, and is immutable. Changes to a frozen matrix create a new revision with a parent reference and change reason. A Pilot matrix never changes phase into Main; the Main experiment uses a new matrix derived from the frozen Pilot matrix. Completion status belongs to run/result records, not to the matrix lifecycle.

## 16. Validity Threats

- Internal validity: LLM output variation, fuzzer randomness, execution order, shared-resource effects, Corpus evolution, instrumentation overhead, and failed revisions.
- Construct validity: activation and Coverage are not Bugs; raw crashes are not confirmed framework anomalies.
- External validity: results are limited to the selected PyTorch 2.10 APIs and may not generalize to other frameworks or versions.
- Conclusion validity: API count, rare anomalies, zero-heavy outcomes, and limited repeats may reduce statistical power.
- Data validity: incomplete Issues, extraction errors, Knowledge review decisions, and imperfect runtime predicates may affect results.
- Contamination risk: Knowledge-derived generation guidance must remain hidden from Baseline synthesis, and API selection must be frozen before observing group outcomes.

## 17. Machine-readable Records

The minimal executable set is:

- `configs/experiment_matrix.json` for frozen groups, inputs, schedules,
  resources, retry policy, and analysis rules;
- `configs/evaluation_target_manifest.json` for the frozen Evaluation Targets;
- the existing EXP011 HarnessSpec, Strategy, and Harness Artifact records;
- the existing EXP012 Round and Feedback Decision records;
- the existing EXP013 Crash Case records.

The experiment Runner writes one compact execution index that references
these records and the immutable Corpus manifests produced by execution. A new
Schema is added only if the single-API dry run proves an existing record cannot
represent a required fact.

Machine references reuse the established forms: `file_reference` contains a
repository-relative path and SHA-256 content hash, while
`artifact_reference` contains an Artifact ID, version, and SHA-256 content
hash. The cutoff rule belongs to the matrix; its resolved
`analysis_cutoff_at` belongs to result provenance.

An api_entry contains only execution bindings: api_id, a
target_manifest_entry_id, an exact API Profile binding, a compile-profile
file reference, and an initial-Corpus binding. API names, overload facts, and
Evaluation Targets remain owned by the Evaluation Target Manifest.

An artifact_binding combines:

- artifact_ref: the established Artifact ID, version, and canonical JSON
  content hash;
- record_file_ref: the repository-relative record path and raw file hash.

The Runner never guesses an Artifact location from its ID. Builder and Feedback Controller subprocesses
write an explicit result JSON selected by the Runner; stdout and stderr remain
diagnostic logs rather than machine interfaces.

The Runner has five phases: validate, plan, prepare, execute, and finalize.
Execute is forbidden until the matrix is frozen and all adapters and environment
bindings resolve. Each operation writes an attempt record before the execution
index advances. Resume reuses only records whose matrix hash, input references,
and operation key match.

Infrastructure retries apply only to frozen retryable categories. They retain
the paired seed and frozen round-start Corpus and never consume method-repair
attempts. A target or framework abnormal exit is recorded, its triggering input
is isolated, and only the remaining active-fuzzing budget may resume, subject
to the frozen per-round restart limit. At finalization, the Runner records the
last terminal core-run timestamp and resolves analysis_cutoff_at from the matrix
delay; classification before that cutoff remains owned by EXP013 and analysis.

## 18. Required Outputs

The evaluation must preserve:

- the frozen experiment matrix and Evaluation Target set;
- synthesis attempts and validation outcomes;
- per-round runtime records, Corpus manifests, and coverage artifacts;
- feedback decisions and revision lineage;
- EXP013 case and cluster records;
- metric-level results with explicit denominators;
- API-level paired tables and aggregate summaries;
- configuration, environment, and Artifact hashes sufficient for audit and reproduction.
