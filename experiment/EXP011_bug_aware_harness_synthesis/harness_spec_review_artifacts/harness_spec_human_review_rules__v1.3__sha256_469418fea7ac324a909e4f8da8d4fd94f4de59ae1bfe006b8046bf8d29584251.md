# HarnessSpec Human Review Rules v1.3

## 1. Purpose

Automatic validation proves structural, referential, and locally encoded
semantic invariants. Human review checks whether a generated HarnessSpec is a
faithful, neutral, and auditable mapping of its frozen inputs. It does not
redesign the HarnessSpec, optimize it for reproducing a historical Bug, or
judge its empirical effectiveness.

These rules apply to every HarnessSpec v2.2 before it can become an active input to
Strategy synthesis or a formal experiment.

## 2. Reviewer authority boundary

The reviewer may:

- compare the HarnessSpec with its exact API Profile, Helper Profile set,
  Knowledge bundle, canonical default HarnessSpec, Contract, and synthesis
  Rules;
- record criterion-scoped findings;
- create an immutable `approved` or `needs_revision` review record bound to the
  exact HarnessSpec content hash;
- request regeneration under corrected general rules when a blocking finding
  is systematic.

The reviewer must not:

- directly edit `knowledge_plan`, `validity_constraints`, any exploration
  Branch, Predicate, behavior observation, behavior check, or budget share;
- provide replacement JSON, a JSON Patch, implementation code, or a desired
  concrete Predicate, Shape, dtype, value, device, or budget;
- add Knowledge, API constraints, or expected behavior that was not among the
  frozen admissible inputs;
- approve or reject a record because it appears more or less likely to
  reproduce a historical Bug;
- use later fuzzing outcomes, coverage, crashes, Oracle results, or performance
  comparisons to retroactively justify an initial Static or Baseline plan.

Human review is a gate and an evidence-bounded diagnosis, not an alternative
HarnessSpec generator.

## 3. Admissible review evidence

A blocking finding may rely only on:

- the exact artifacts referenced by the HarnessSpec;
- the canonical controlled-Baseline default bound during bug-aware synthesis;
- the versioned HarnessSpec Schema, Contract, and synthesis Rules;
- deterministic validation results produced for the reviewed revision;
- a predeclared current-version probe or validation artifact whose protocol,
  target, and interpretation were frozen before inspecting the generated
  HarnessSpec.

An ad hoc post-generation probe may identify a question for later protocol
design, but it is not by itself sufficient blocking evidence and must not be
used to prescribe a replacement semantic value.

## 4. Review criteria

Apply every criterion relevant to the record's mode. A mode-specific criterion
is not a different approval threshold.

### HR-01 — Machine-validation gate

`validation_status` is `passed`, `validation_issues` contains no unresolved
error, and the record conforms to the active HarnessSpec JSON Schema.

### HR-02 — Frozen-input and provenance fidelity

Every API, Helper, Knowledge, policy, Contract, Rules, and parent reference
resolves to the exact declared revision and content hash. Semantic claims cite
only admissible supplied sources and their exact paths.

### HR-03 — Experimental-group isolation

A controlled Baseline contains no Knowledge decision or Knowledge-derived
semantic contribution. A bug-aware record uses the exact reviewed canonical
default-branch semantics; only Builder-owned budget allocation and additional
Knowledge-directed branches may differ.

### HR-04 — Knowledge decision and mapping fidelity

Every supplied Knowledge has one supported `included` or `deferred` decision.
For included Knowledge, material components selected from its hypothesis,
anchors, variations, observations, and limitations are represented without
changing their evidence status or certainty. A material supported component is
not silently omitted, and an unrepresentable component is deferred or its
omission is explained from the supplied capability context.

The reviewer reports an apparent omission or distortion and cites its source;
the reviewer does not prescribe the replacement Branch or Predicate.

Evidence is required for material semantic claims. Builder-derived identifiers,
hashes and lineage are justified by deterministic construction; branch shares
are justified by the referenced budget policy; Strategy-owned decoding and
sampling choices are not Knowledge claims. The reviewer must not require a
separate Knowledge citation for every field or demand concrete values for input
dimensions that intentionally remain fuzz-derived.

A source-supported candidate boundary may be explored even when its necessity
as a trigger is unknown. The record must preserve that uncertainty and must not
claim universal failure. For a compound variation, supported parts may be
represented while unsupported qualitative thresholds are deferred. Honest,
explicit deferral is not itself a blocking omission.

### HR-05 — Input-validity intent support

Each `input_validity_intent` is supported by the frozen API contract or other
admissible predeclared evidence. Historical failure, current rejection, or
reviewer intuition alone does not automatically establish `expected_valid` or
`intentionally_invalid`. If the supplied evidence cannot distinguish them, the
reviewer records the unresolved support gap rather than selecting a value.

### HR-06 — Predicate and capability fidelity

Each Constraint and Target Condition uses an exact supported Predicate and
subject reference without approximating a different source meaning. Historical
anchors, exploration variables, and activation claims retain their distinct
roles. Unsupported meaning is deferred rather than mapped to a nearby
Predicate.

### HR-07 — Observation and behavior-check support

Record-only questions remain `behavior_observations`. A `behavior_check` is
present only when its expected Predicate and preconditions have independent
support in the supplied sources. Fixed Runner monitoring is not duplicated as
a Knowledge-specific expected result.

### HR-08 — Fuzz freedom and non-replay

Knowledge-directed branches retain meaningful fuzz-derived freedom and do not
copy a complete historical reproducer. Exact historical values are fixed only
when the reviewed Knowledge and synthesis Rules require that treatment. Final
transitive byte influence remains a Strategy-validation responsibility.

### HR-09 — Builder-owned decisions

Identity, lineage, hashes, source expansion, canonical-default replacement,
budget allocation, provenance, and initial review state remain Builder-owned.
The reviewer checks their consistency but does not choose alternative values.

### HR-10 — Downstream-layer separation

The HarnessSpec states what to explore, observe, or check. It does not select
Strategy Primitives, prescribe implementation steps, encode Harness code, or
claim that current Strategy capabilities prove scientific usefulness.

An exploration goal may cite deferred material as explicit background,
limitation, or scope exclusion. It is blocking only when the goal positively
requires that component to be executed while its mapping states that the
component is absent, or when downstream implementation would have to infer an
unstated condition from prose.

## 5. Findings

Each structured finding in the external review record must identify:

- `criterion_id`: one criterion from HR-01 through HR-10;
- `severity`: `blocking` or `advisory`;
- `field_path`: the affected HarnessSpec location;
- `evidence_ref`: an exact admissible artifact and path, when applicable;
- `mismatch_summary`: a concise description of the unsupported, omitted, or
  conflicting meaning.

A finding must not contain a replacement value, replacement JSON, JSON Patch,
implementation choice, or desired experimental outcome.

## 6. Outcomes

- `approved`: machine validation passed and no blocking finding remains.
- `needs_revision`: at least one blocking finding is supported by these rules.
- no external record: no completed human decision has been recorded.

For `approved` or `needs_revision`, record reviewer identity, review time,
applicable Rules hash, exact subject hash, structured findings, and optional
review notes. The embedded HarnessSpec `review` object records automatic
validation and remains `not_reviewed`; the immutable external record is the
authoritative human decision. This avoids changing the hash of the object being
reviewed. Approval means only that the reviewed revision is an acceptable
evidence-bounded experimental specification. It does not prove Bug discovery,
runtime activation, effectiveness, superiority, or statistical significance.

Repeated review of the same immutable HarnessSpec creates a new external review
revision. Review revision 1 has no parent; revision 2+ cites the exact prior
review record and increments by one. A later review does not overwrite or erase
an earlier decision.

## 7. Revision and regeneration

Do not silently edit a reviewed or generated HarnessSpec. A fix produces a new
revision with an exact parent reference and a review-derived trigger. The
generator, not the reviewer, constructs the revised semantic payload from the
same frozen inputs and criterion-scoped findings. The child revision starts as
`not_reviewed` and must pass the full review again.

Pass the exact external review through `build_harness_spec_json.py
--review-record`. The Builder accepts only a `needs_revision` review whose
subject matches the immediate parent and records that review reference in every
generation trace. Do not copy findings into an ad hoc prompt.

Create review records only through `scripts/review_harness_spec.py`. The tool
does not edit the HarnessSpec, refuses overwrite, rejects approval with a
blocking finding, and rejects `needs_revision` without a blocking finding.
Downstream Strategy admission must resolve an `approved` record whose subject
triple `(spec_id, revision_number, content_hash)` exactly matches its input.

When a finding exposes a systematic mapping, Contract, Builder, or Validator
defect, correct the general rule or mechanism and regenerate every affected
record. Do not add an API-name, Knowledge-ID, or historical-Bug-specific
exception.

## 8. Experimental neutrality

Freeze the review-rule version, evidence cutoff, applicable criteria, severity
threshold, and revision limit before comparing experimental groups. Apply the
same rule version and decision threshold across APIs and modes. Knowledge-only
criteria are evaluated only where Knowledge is present, but they do not lower
or raise the approval standard.

Complete initial Baseline and Static review before inspecting their comparative
runtime effectiveness. Retain all reviewed revisions and findings so that
selection and regeneration are auditable.
