# Crash Candidate Triage and Result Analysis Protocol

## 1. Purpose

This protocol defines how abnormal fuzzing events are admitted, preserved, deduplicated, reproduced, attributed, and assessed for historical or potentially novel framework Bugs.

It distinguishes:

- raw runtime failures;
- admitted Candidate Events;
- duplicate Candidate Events;
- reproducible framework anomalies;
- historical Bug rediscoveries;
- potentially novel Bugs;
- externally confirmed novel Bugs.

A crash, Oracle violation, or activated risk condition is not automatically a framework Bug.

---

## 2. Scope and Exclusions

This protocol covers:

- native crashes and fatal signals;
- sanitizer findings;
- unexpected Target API exceptions;
- applicable Oracle violations;
- per-call hangs;
- abnormal memory exhaustion;
- Candidate evidence preservation;
- fault attribution;
- deduplication;
- reproduction;
- historical Issue matching;
- human adjudication.

This protocol does not:

- define the complete JSON record structure;
- implement Runner, Analyzer, or Validator behavior;
- change Feedback budgets or HarnessSpec semantics;
- calculate experiment-wide statistical results;
- modify Report, Pattern, or Knowledge records;
- automatically submit external Bug reports;
- automatically confirm a new framework Bug.

---

## 3. Responsibilities

### 3.1 Runner

The Runner:

- captures abnormal runtime events;
- writes an immutable Candidate Bundle for each attempt that produced Candidate artifacts;
- preserves triggering inputs, diagnostics, commands, environment, and artifact references;
- merges Candidate Bundles across process restarts into the selected logical Round;
- records execution, iteration, Branch, Site, and Target API invocation identifiers only when directly available;
- exposes the selected Round and Candidate Bundle through the execution index;
- does not determine whether an event is a framework Bug.

### 3.2 Analyzer

The deterministic Analyzer:

- consumes only the execution index, selected Fuzzing Round, and referenced Candidate Bundle;
- checks evidence availability;
- computes hashes and normalized signatures;
- performs exact deduplication;
- schedules replay attempts;
- records reproduction outcomes;
- prepares records for human review;
- does not independently confirm framework attribution or novelty.

### 3.3 Validator

The Validator checks:

- required fields and references;
- status compatibility;
- reproduction-count consistency;
- deduplication-reference consistency;
- derivation of reportable result categories.

Validation success proves record consistency, not that a semantic conclusion is correct.

### 3.4 Human Reviewer

A Human Reviewer determines:

- whether input and Oracle preconditions are satisfied;
- whether the failure belongs to the Harness, Helper, instrumentation, infrastructure, or framework;
- whether two Cases are semantically equivalent;
- whether replayed failures represent the same anomaly;
- whether a historical Issue matches;
- whether novelty evidence is sufficient.

### 3.5 LLM Assistance

LLM assistance is optional and is not required by this protocol.

An LLM may assist with:

- log summarization;
- stack-trace normalization suggestions;
- historical Issue search suggestions;
- reviewer checklist generation.

LLM output is not primary evidence and cannot independently determine fault attribution, Issue matching, or Bug novelty. Any LLM-assisted conclusion requires human verification against original evidence.

---

## 4. Core Terms

- **Runtime Event**: any event observed during generation, compilation, preflight, or fuzzing.
- **Candidate Event**: an abnormal fuzzing event admitted by this protocol.
- **Crash Case**: a Candidate Event with preserved evidence and a stable identity.
- **Candidate Cluster**: one or more Crash Cases judged to represent the same underlying anomaly.
- **Representative Case**: the Case selected to represent a Candidate Cluster.
- **Reproducible Framework Anomaly**: a replayable anomaly attributed to the framework rather than to the Harness, Helper, instrumentation, infrastructure, or expected rejection.
- **Historical Bug Rediscovery**: a reproducible framework anomaly matched to an existing historical Issue.
- **Potentially Novel Bug**: a reproducible framework anomaly for which no matching Issue is found within the recorded search scope.
- **Externally Confirmed Novel Bug**: a potentially novel Bug subsequently confirmed through an accepted framework-maintainer action.

Risk-condition activation alone does not create a Candidate Event.

---

## 5. Candidate Admission

### 5.1 Direct Admission Events

The following events are admitted when they occur during or as a result of Target API execution:

- native crash;
- fatal signal;
- unexpected abort;
- supported sanitizer finding;
- memory-safety violation;
- applicable Tier 1 Oracle violation.

### 5.2 Conditional Admission Events

The following events require additional applicability or attribution checks:

- Tier 2 Oracle violation;
- unexpected Target API exception;
- per-call timeout or hang;
- abnormal memory exhaustion;
- abnormal resource growth.

### 5.3 Diagnostic-Only Events

The following observations do not independently create a Crash Case:

- risk-condition activation without abnormal behavior;
- coverage stagnation;
- NaN or Inf output permitted by the API;
- Tier 3 Oracle observation;
- a single unverified timeout or OOM;
- normal completion of the fuzzing-round time budget.

Diagnostic evidence may support a later Candidate Event.

### 5.4 Excluded Events

The following are excluded from framework-anomaly analysis:

- HarnessSpec or Strategy synthesis failure;
- Harness compilation or startup failure;
- Runner, Docker, storage, or environment failure;
- ordinary input parsing failure;
- expected and controlled rejection of invalid input;
- failure before Target API execution;
- evidence too incomplete to establish the failing execution.

Excluded events remain available for experiment-reliability analysis.

---

## 6. Oracle Evidence Levels

Oracle evidence is classified independently from Knowledge confidence.

### 6.1 `tier_1_exact`

The Oracle checks an explicit and applicable contract or safety property.

Examples include:

- memory-safety violations;
- exact shape or dtype contract violations;
- violations of an explicitly guaranteed deterministic property.

A valid Tier 1 violation may directly admit a Candidate Event.

### 6.2 `tier_2_validated`

The Oracle is valid only after additional comparison conditions are verified.

Examples include:

- differential testing;
- metamorphic relations;
- numerical comparison with tolerance;
- frontend or backend consistency.

Admission requires verified semantic equivalence, applicable tolerance, compatible dtype and device, and satisfied Oracle preconditions.

### 6.3 `tier_3_heuristic`

The Oracle provides a suspicious signal without a sufficiently strong contract.

Examples include:

- unexpected NaN or Inf without a documented prohibition;
- unusual performance;
- abnormal but unconfirmed resource consumption.

Tier 3 evidence is diagnostic only.

### 6.4 `unevaluable`

The Oracle cannot be evaluated because required inputs, comparison conditions, runtime events, or tolerances are unavailable.

An unevaluable Oracle cannot admit a Candidate Event.

Each evaluated Oracle shall retain its type, version, preconditions, applicability result, effective tolerance or comparison configuration, observation, and evidence references.

---

## 7. Evidence Preservation

Each Crash Case shall preserve references to:

- API and overload;
- experiment group, repeat, round, attempt, seed, execution, and iteration;
- framework, Helper, compiler, sanitizer, instrumentation, and container versions;
- HarnessSpec, Strategy Plan, and Harness Artifact;
- original triggering input and content hash;
- corpus and run configuration;
- complete execution command;
- stdout, stderr, exit code, and terminating signal;
- sanitizer, exception, timeout, or OOM diagnostics;
- runtime instrumentation snapshot;
- relevant Branch, validity, activation, Target API, and Oracle events;
- available coverage context;
- first-observed timestamp;
- Feedback Decision when one exists.

Large inputs and logs shall be stored as referenced artifacts rather than embedded records.

Original evidence is immutable. Later analysis may append conclusions but shall not overwrite the original evidence.

The production ingest path shall not accept semantic overrides from a manually authored intake manifest. Missing Branch, Site, iteration, or Target invocation identifiers remain null or empty rather than being inferred.

One admitted occurrence is identified by its execution, iteration, Target API invocation, and primary anomaly signature. Cascading messages from the same occurrence are supporting diagnostics rather than automatically separate Candidate Events.

---

## 8. Triage Sequence

A Crash Case shall be processed in this order:

1. verify evidence completeness;
2. exclude infrastructure failure;
3. exclude Harness, Helper, and instrumentation faults;
4. confirm Target API execution;
5. assess input validity and expected rejection;
6. perform exact deduplication;
7. replay the original input;
8. minimize the input when practical;
9. construct an independent reproducer when practical;
10. perform semantic deduplication;
11. search for matching historical Issues;
12. conduct final human adjudication.

A conclusion that depends on an unresolved earlier step shall remain unresolved.

---

## 9. Validity and Fault Attribution

Fault attribution is recorded independently from reproduction and historical matching.

Allowed attribution outcomes are:

- `framework`;
- `harness`;
- `helper`;
- `instrumentation`;
- `infrastructure`;
- `unresolved`.

Expected or controlled input rejection is recorded by
`api_behavior_assessment`, not as a fault-attribution outcome.

### 9.1 Input Validity

Input validity shall be checked against:

- API Profile constraints;
- selected HarnessSpec Branch constraints;
- Helper preconditions;
- runtime-observed argument relationships.

A documented and controlled rejection of invalid input is not a framework Bug.

Invalid input may remain a framework-anomaly candidate when it causes memory corruption, unsafe behavior, or an uncontrolled native failure instead of safe rejection. The input-invalidity finding shall remain explicit.

### 9.2 Harness, Helper, and Instrumentation Faults

The analysis shall check for:

- out-of-bounds access in generated code;
- incorrect input-offset handling;
- invalid object lifetime;
- incorrect shape, dtype, device, or parameter binding;
- violated Helper preconditions;
- failure before Target API invocation;
- instrumentation that changes arguments, return values, control flow, or object lifetime.

Removing or replacing the Target API and observing the same failure is evidence of a non-framework fault, but final attribution still requires review.

---

## 10. Timeout, Hang, and OOM

A fuzzing-round time-budget expiration is not a per-call timeout.

A per-call timeout is eligible only when:

- Target API entry is recorded;
- the matching Target API exit is absent;
- the frozen per-call timeout is reached;
- Runner or infrastructure failure is excluded;
- replay evidence is available.

A hang is a per-call timeout that recurs during replay and cannot be attributed to the Runner or environment.

An OOM-related event is eligible only when:

- the input respects frozen Tensor and total-input limits;
- external container or host memory pressure is excluded;
- Target API execution is established;
- the event is not a normal controlled OOM response;
- abnormal allocation, memory growth, or termination is reproducible.

The following parameters shall be defined in a versioned experiment configuration:

- per-call timeout;
- process memory limit;
- maximum Tensor bytes;
- maximum total input bytes;
- maximum Tensor element count;
- timeout replay policy;
- OOM replay policy.

Initial values may be calibrated during the pilot but shall be frozen before the main experiment.

---

## 11. Deduplication

### 11.1 Case Role

Each Case is classified as:

- `representative`;
- `duplicate_member`.

A duplicate member shall reference its representative Case or Candidate Cluster.

### 11.2 Exact Deduplication

Exact deduplication may use:

- triggering-input hash;
- Harness Artifact hash;
- failure or Oracle type;
- signal, sanitizer, or exception type;
- normalized stack signature.

### 11.3 Semantic Deduplication

Semantic deduplication considers:

- API and overload;
- failure mechanism;
- relevant framework stack frames;
- Oracle violation;
- minimized reproducer;
- suspected root cause.

Cases shall not be merged solely because they use the same API or share one stack frame.

Each Candidate Cluster shall preserve its representative Case, members, merge rationale, first-observed location, and occurrence counts by experiment group.

Semantic deduplication requires human review.

---

## 12. Reproduction

The original input shall be replayed until five valid attempts are completed.

A valid replay attempt requires:

- identical input content;
- identical Harness Artifact;
- compatible build and runtime environment;
- confirmed Target API execution;
- no infrastructure failure;
- a readable replay result.

Infrastructure-failed attempts do not count toward the five valid attempts. At most two replacement attempts are permitted. If five valid attempts cannot be obtained, reproduction is `inconclusive`.

A replay is successful only when it produces the same primary failure class and the same or semantically equivalent failure signature.

### 12.1 Reproduction Stability

| Successful valid replays | Status |
| --- | --- |
| 4 or 5 of 5 | `stable` |
| 2 or 3 of 5 | `intermittent` |
| 1 of 5 | `weak` |
| 0 of 5 | `not_reproduced` |
| Fewer than 5 valid attempts | `inconclusive` |

Only `stable` anomalies enter the primary reproducible-anomaly metric.

Other anomalies remain available for secondary analysis.

### 12.2 Reproduction Artifacts

The Case records the availability of the original-input replay, minimized
input, minimal C++ reproducer, optional Python reproducer, and cross-validation
evidence separately. These artifacts do not form a mandatory ordinal level.

Input minimization shall not overwrite the original input. After minimization, input validity, risk activation, and anomaly equivalence shall be checked again.

### 12.3 Python Reproduction

Python reproduction is optional supporting evidence.

Failure to reproduce through Python does not invalidate a C++ API anomaly. Differences between Python and C++ behavior shall be recorded when relevant.

---

## 13. Historical Matching and Novelty

Historical search state and match outcome are recorded separately.

`search_status` is one of:

- `not_started`;
- `in_progress`;
- `completed`;
- `inconclusive`.

`match_status` is one of:

- `not_assessed`;
- `no_match`;
- `possible_match`;
- `confirmed_match`.

Issue search shall record:

- search date;
- searched sources;
- API and failure keywords;
- relevant version range;
- candidate matching Issues;
- match or rejection rationale.

A `possible_match` outcome or an `inconclusive` search maps to unresolved
novelty.

A `confirmed_match` maps to `known_bug_rediscovery`.

A `no_match` result does not prove global novelty. It may support
`potentially_novel` only when the search scope is complete, the anomaly is
stably reproducible, fault attribution is `framework`, and human review is
complete.

Novelty outcomes are:

- `not_assessed`;
- `not_applicable`;
- `known_bug_rediscovery`;
- `novelty_unresolved`;
- `potentially_novel`;
- `externally_confirmed_novel_bug`.

`externally_confirmed_novel_bug` additionally requires at least one of:

- explicit framework-maintainer confirmation;
- an official Issue accepted or labelled as a Bug;
- a linked fix PR or commit;
- an official regression test or release record addressing the reported behavior.

No other unspecified confirmation basis is permitted.

---

## 14. Feedback Interface

Feedback and Crash Triage are separate consumers of fuzzing evidence.

```text
Fuzzing Round
  ├── exploration measurements → Feedback Decision
  └── abnormal-event evidence → Crash Triage
```

The Crash Case may reference the originating Fuzzing Round, Runtime Snapshot, and Feedback Decision.

The Feedback Controller may transfer a Candidate Event for triage, but it shall not determine fault attribution, historical matching, or Bug novelty.

Crash Triage shall not modify an existing Feedback Decision, HarnessSpec, Strategy Plan, or main-experiment budget.

A Fuzzing Round may produce zero, one, or multiple Crash Cases.

---

## 15. Result Categories

Result counts are derived from Case role, fault attribution, reproduction status, historical matching, and novelty assessment.

### 15.1 Raw Native Crash Events

Occurrences of native crash, fatal signal, or unexpected abort before deduplication.

Cascading diagnostic messages from one occurrence do not create additional raw crash events.

### 15.2 Admitted Candidate Events

All events admitted under Section 5, including eligible crashes, sanitizer findings, Oracle violations, hangs, and OOM-related events.

### 15.3 Unique Candidate Clusters

Candidate Clusters remaining after exact and semantic deduplication.

### 15.4 Unique Reproducible Framework Anomalies

Representative Candidate Clusters satisfying:

- fault attribution is `framework`;
- reproduction status is `stable`.

### 15.5 Historical Bug Rediscoveries

Unique reproducible framework anomalies with:

```text
historical_matching.match_status = confirmed_match
```

### 15.6 Potentially Novel Bugs

Unique reproducible framework anomalies with:

```text
historical_matching.match_status = no_match
novelty_assessment.status = potentially_novel
```

### 15.7 Externally Confirmed Novel Bugs

Cases satisfying the external-confirmation requirements in Section 13.

Raw crash count and Candidate Event count are supporting metrics. They shall not be reported as confirmed Bug counts.

Experiment-wide denominators, statistical tests, and group comparisons are defined separately in the RQ, Metrics, and Experiment Matrix protocol.

---

## 16. Human Review

All Candidate Clusters included in reproducible-anomaly or Bug metrics require human review.

Exact duplicate members may rely on the review of their representative Case.

Where practical, the reviewer should not see the experiment group before completing fault attribution and semantic deduplication.

The review shall preserve:

- review timestamp;
- reviewed aspects and evidence;
- conclusion;
- summary and rationale;
- unresolved disagreement.

An unresolved disagreement shall produce an unresolved result rather than a forced Bug classification.

---

## 17. Pilot and Main-Experiment Policy

During the pilot, timeout, memory, replay, and deduplication parameters may be calibrated.

Every Crash Case revision records its own immutable UTC `revision.created_at`.
Cutoff-based analysis selects the newest valid revision whose timestamp is not
later than the frozen `analysis_cutoff_at`; later revisions remain available but
do not retroactively alter primary results.

Before the main experiment:

- all thresholds shall be frozen;
- all parameter versions shall be recorded;
- the same protocol shall apply to all experiment groups;
- protocol changes shall require a new version;
- main-experiment results shall not be retrospectively reclassified using undisclosed rules.

Replay, minimization, historical search, and cross-version confirmation costs are analysis costs and are not included in the equal fuzzing-time budget of the three experiment groups.

---

## 18. Final Restrictions

This protocol shall not:

- equate risk activation with a Bug;
- equate raw crash count with Bug count;
- automatically discard every invalid-input failure;
- require Python reproduction for C++ findings;
- automatically modify historical Knowledge;
- automatically change Feedback decisions;
- automatically claim novelty;
- automatically submit an Issue to framework maintainers.

External reporting is a separate human-authorized action conducted only after the required evidence and review are complete.