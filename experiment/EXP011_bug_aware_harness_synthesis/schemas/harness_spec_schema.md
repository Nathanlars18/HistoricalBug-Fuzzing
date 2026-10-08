# Historical Bug-Aware HarnessSpec Schema v2.2

## 1. Responsibility

A HarnessSpec is one immutable, target-API-specific semantic testing plan. It
decides which reviewed same-API Knowledge records can be used together, groups
compatible contributions into exploration branches, defines observable target
conditions and evidence-supported behavior checks, and records exact inputs and
review state.

It defines **what** to explore and observe. Strategy defines **how** supported
Predicates are implemented with Primitives; the generated Harness contains the
concrete byte decoding, values, API calls, instrumentation, and checks.

HarnessSpec does not classify defects, copy historical reproducers, contain
Helper calls or C++ code, store results, or define experiment-wide seeds and
time budgets.

## 2. Experimental modes

- `controlled_baseline`: one canonical default branch, no Knowledge;
- `bug_aware_static`: the exact baseline default branch plus Knowledge-directed branches;
- `bug_aware_adaptive`: initially identical to Static; the current feedback policy may create later revisions that change branch budget shares only.

The experiment runner owns equal total budget and paired seeds. The Builder
owns branch shares. In bug-aware generation the LLM emits only
Knowledge-directed branches; the Builder injects the exact validated Baseline
default before semantic validation. Model-created default semantics therefore
cannot influence the record or consume a repair attempt.

Contract v2.5 contains the machine-validatable semantic-response shape used by
both the prompt and the Builder. Local shape issues and independent Predicate,
subject, source, observation-point, and component-mapping issues are collected
before a repair request so that one candidate does not consume one attempt per
hidden error. Deterministic normalization is limited to local identifiers,
nullable bookkeeping fields, and canonical-default injection; the Builder does
not guess property paths, observation phases, Predicates, or mapping claims.

HarnessSpec files are immutable. Revision 1 uses `initial_creation`; a later
revision explicitly names its revision number and trigger, resolves the
immediately preceding same-identity revision as `parent_revision_ref`, and has
its `change_scopes` and summary derived by the Builder from deterministic
parent/child projections. A source-artifact or review regeneration is valid for
controlled-Baseline and Static identities. Adaptive revision 2+ remains owned
by the feedback-request path. Destination collisions are rejected before an
LLM request is made.

The legacy initial budget policy applies only to revision 1. A later Static
regeneration uses a separately versioned revision-aware initial policy; old
records retain their original policy hash and are never rewritten.

## 3. Top-level objects

| Field | Purpose |
| --- | --- |
| `identity` | Stable API, framework, and experimental mode |
| `revision_information` | Immutable lineage, including Static-to-Adaptive derivation and feedback revisions |
| `target_context` | Exact API Profile and mode-independent available Helper Profile set |
| `knowledge_plan` | One `included` or `deferred` decision for every supplied reviewed Knowledge |
| `validity_constraints` | API/Profile-derived requirements shared by all branches |
| `exploration_plan` | Canonical default and Knowledge-directed branches with Builder-owned shares |
| `provenance` | Exact Builder, model, Contract, Rules, active Schema pair, accepted-attempt trace, and generation run |
| `review` | Automatic validation and generation-time review state; exact human decisions are external immutable records |

New v2.2 records persist `revision_information.canonical_default_spec_ref`
when a bug-aware plan imports its default Branch. The field is nullable and
optional at the Schema level so already-issued v2.2 records remain readable;
Builder v0.22 emits it for new records and uses it to freeze manual-review
regeneration to the same canonical Baseline.

## 4. Knowledge decisions

Each supplied Knowledge v3 record receives exactly one decision:

- `included`: contributes to one or more listed `branch_ids`;
- `deferred`: cannot be converted safely with the current API context and
  supported Predicate/Helper capabilities; `branch_ids` is empty.

Reviewed Knowledge is not ranked by LLM confidence and is not rejected for
subjective importance. Same-API scope and review eligibility are checked
deterministically before synthesis. Each decision inventories the learned
hypothesis, anchors, variations, observations, and limitations as
`represented`, `partially_represented`, or `deferred`, with exact references to
the HarnessSpec elements that claim representation. This makes omissions
explicit without forcing every component into a Predicate.

For `represented`, the exact element references are the complete mapping, so
the three explanatory scope/summary fields are null. `partially_represented`
requires exact references plus non-empty represented scope, deferred scope, and
decision summary. `deferred` has no element references and requires a non-empty
deferred scope and decision summary. A free-text goal or validity basis does not
count as the required structured Knowledge contribution.

Evidence is attached to claims that change semantic meaning. Builder-derived
IDs, hashes, lineage and policy-owned branch shares are justified by their
versioned mechanisms. Concrete decoding ranges and sampling weights belong to
Strategy or the experiment protocol. Unspecified tensor dimensions, values,
dtypes and layouts therefore remain open to Fuzzer input rather than requiring
invented Knowledge citations.

## 5. Predicate

A Predicate is a versioned implementation-interface expression:

```json
{
  "predicate_id": "property_relation",
  "arguments": {
    "subject_ref": "param_input",
    "property_ref": "numel",
    "operator": "equals",
    "value": 0
  },
  "description": "The input is empty before the target call."
}
```

Predicate IDs are not defect classes and make no completeness claim. The
Synthesis Contract lists only operations currently understood by downstream
validation and Strategy materialization. An unsupported Knowledge contribution
is deferred rather than forced into a nearby Predicate.

The validator checks internally decidable facts such as non-empty numeric
ranges, return-value availability at an observation phase, exact branch
membership, and bidirectional agreement between structured source references
and component mappings. Whether source prose scientifically supports a
particular semantic generalization remains an evidence-bounded human-review
question.

Every materialized Predicate contains `description`. The value is either
non-empty text supplied by synthesis or JSON `null`; when the LLM omits this
nullable field, the Builder deterministically materializes `null` without
inventing semantic content. Unknown Predicate fields, malformed arguments, and
non-normalized property paths remain validation errors.

## 6. Source references

Every semantic item cites an exact immutable API Profile or Knowledge artifact
and a JSON Pointer `source_path`. For Knowledge, supported paths are the learned
hypothesis and individual historical-anchor, variation-opportunity, or
observation-candidate items, plus individual limitation items. The Builder
attaches version and content hash and rejects nonexistent paths. Branch goals
use `exploration_goal_source_refs`, so a free-text goal cannot silently stand in
for an uncited constraint.

## 7. Constraints

`validity_constraints.global_constraints` contains only API/Profile requirements
that must hold for every branch. Knowledge historical anchors are never global.

`branch_constraints` contains conditions that must hold for one branch. A
condition deliberately varied is a Target Condition, not a Constraint. A
condition intentionally violated to test API error handling is represented by
the branch validity intent and a Target Condition; unrelated validity and safety
requirements remain Constraints.

## 8. Exploration branches

The only branch kinds are:

- `default`: canonical general valid-input exploration shared exactly in
  semantic content across Baseline, Static, and Adaptive;
- `knowledge_directed`: one compatible group of included Knowledge records.

`generic_exploration` was removed because an extra non-Knowledge branch only in
bug-aware groups would confound the effect attributed to Knowledge.

Each branch records:

- `input_validity_intent`: `expected_valid`, `intentionally_invalid`, or
  `contract_boundary_unresolved`;
- `input_validity_basis`: the exact evidence class, source references, and a
  concise justification for that intent;
- `source_knowledge_ids`: empty for default, non-empty for Knowledge-directed;
- `grouping_summary`: concise merge/split explanation, null for default;
- `exploration_goal`: human-readable primary intent;
- `branch_constraints`;
- `target_conditions`;
- `behavior_observations`;
- `behavior_checks`;
- Builder-owned `budget_share`.

`contract_boundary_unresolved` is not an invalid-input claim. It records that
the frozen API Profile and Knowledge do not establish whether the explored
boundary is currently accepted by contract. It must pair with an `unresolved`
basis. `expected_valid` and `intentionally_invalid` must pair with a supported
non-unresolved basis; historical failure or current rejection alone is not
sufficient. The default Branch uses `canonical_baseline_definition` and makes
no undocumented boundary claim. A Knowledge-directed Branch may use
`api_contract` only with current API Profile evidence; otherwise its basis is
`unresolved`. Historical Knowledge is never promoted into a current-validity
basis.

## 9. Target conditions and activation

A Target Condition combines the earlier Target Property and Activation Target:

- `activation_required`: must be observed true before the branch can claim that
  its Knowledge-derived state was exercised;
- `exploration_variable`: identifies an evidence-grounded variation that should
  remain fuzz-derived and is not conjoined into the activation claim.

`observe_at` states whether the Predicate is evaluated before or after the API
call. A transition uses both phases. Historical anchors may become branch
constraints or activation-required conditions. Variation opportunities may
become exploration variables. Only supported conditions are materialized.

Every Knowledge branch must retain at least one target-API input degree of
freedom influenced by Fuzzer bytes. Exact historical values are fixed only when
the reviewed Knowledge marks the corresponding condition as a historical
anchor. This is validated finally at Strategy dataflow level.

## 10. Observations and behavior checks

`behavior_observations` record values or execution behavior without declaring a
pass/fail result. They are appropriate when Knowledge identifies behavior worth
observing but current evidence does not justify an expected relation.

`behavior_checks` contain a supported expected Predicate and produce a semantic
pass/fail result. A Knowledge observation candidate alone does not establish a
sound check. Expected behavior must be supported by the API Profile, Knowledge,
or a stated metamorphic/differential relation.

Crash, signal, sanitizer, timeout, hang, and OOM monitoring are fixed Runner
responsibilities shared by every group. They are not repeated as LLM-generated
checks in every branch. `behavior_check` therefore replaces the earlier dual
`oracle_type + expected_behavior` representation.

## 11. Fixed runtime evidence chain

Downstream instrumentation uses stable events rather than LLM-created event
names:

```text
branch_selected
input_constructed
validity_checked
input_valid | input_rejected
target_condition_checked
target_condition_satisfied
target_api_reached
target_api_completed
behavior_check_evaluated
behavior_check_passed | behavior_check_failed
iteration_completed
```

HarnessSpec supplies branch, condition, observation, and check IDs. Runtime
records establish whether the planned code path actually ran. Code Coverage is
diagnostic evidence and does not replace these semantic events.

## 12. Knowledge v3 mapping

| Knowledge v3 field | HarnessSpec use |
| --- | --- |
| `scope.target_api` | deterministic eligibility |
| `learned_hypothesis` | branch-goal candidate |
| `historical_anchors` | branch constraint or activation-required condition |
| `variation_opportunities` | exploration-variable condition |
| `observation_candidates` | record-only observation or evidence-supported check |
| `limitations` | defer decision, branch boundary, or review warning |

Chen root-cause and symptom categories remain Pattern evidence. They are never
mechanically mapped to a Predicate, branch, or behavior check.

## 13. Review and activation

Automatic validation proves shape, identifiers, source paths, decision/branch
coverage, Predicate argument form, and cross references. It cannot prove that a
plan is scientifically useful or that a behavior check is sound.

Every HarnessSpec used in a formal experiment must be human approved. Review
confirms canonical default equality, faithful Knowledge mapping, remaining fuzz
freedom, supported expected behavior, and absence of complete historical replay.
Review follows `harness_spec_human_review_rules.md`. The reviewer creates an
external immutable record bound to the exact `(spec_id, revision_number,
content_hash)`. It contains an evidence-bounded decision and findings but does not edit semantic fields,
prescribe replacement values, or optimize a record for historical-Bug
reproduction. A revision requested by review is generated as a new immutable
child and is reviewed again from `not_reviewed`. Re-reviewing the same exact
HarnessSpec creates a new external review revision linked to the immediate
prior review; no review record is overwritten.

Review-driven regeneration uses `--review-record`. The Builder accepts only an
external `needs_revision` record bound to the exact immediate parent hash and a
`manual_review` child revision. It projects only criterion ID, field path,
evidence reference, and mismatch summary into the prompt. Reviewer identity,
notes, and any replacement semantics are not prompt instructions. Every attempt
trace stores the exact review-record artifact reference, so the reason for the
child revision is auditable without adding review text to HarnessSpec semantics.
The parent API Profile, Helper set, Knowledge bundle, budget policy, and recorded
canonical Baseline are frozen inputs; review repair cannot silently exchange
experimental inputs.

For v2.2, the immutable HarnessSpec remains `draft` with embedded
`human_review_status = not_reviewed`; these fields describe the generated object
and are never rewritten. A downstream-admissible revision requires automatic
validation passed and an exact external human review decision of `approved`.
Admission is derived from both immutable records. Approval establishes
specification fidelity, not runtime activation, Bug discovery, effectiveness,
superiority, or statistical significance.

## 14. Version boundary

HarnessSpec v1.8, its Contract and Rules are preserved under
`schemas/legacy/harness_spec_v1_8/`. Immutable v2.0 and v2.1 records are checked
only with their dedicated schemas under `schemas/legacy/`; they are never
silently accepted by the active v2.2 Schema. The Builder emits v2.2 only.
Controlled Baselines migrate deterministically without an LLM;
Knowledge-bearing records are regenerated because validity bases and component
mappings are semantic.

Before writing a generated record, the Builder freezes exact script, active
Schema wrapper, Schema core, Contract, and Rules bytes under hash-qualified
paths. Every LLM attempt also produces an immutable exact prompt/response trace;
the successful HarnessSpec cites its accepted attempt, while failed diagnostics
retain all completed-attempt references. Downstream Strategy support must
explicitly declare HarnessSpec v2.2 and exact approved-review admission before
a plan is materialized.
