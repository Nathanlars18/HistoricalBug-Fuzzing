# Strategy Layer Schema and Responsibility Model v1.3

## v1.3 executable-domain update

New records use Plan v1.3, Catalog v6, Contract v1.8 and Rules v1.5. The JSON
Schema still reads v1.2 immutable parents; it does not silently upgrade them.
New source_context references the exact resource policy, ordinary-input recipe
set, optional repair review and immutable generation trace. The trace freezes
input views, contract/rules/catalog, emitter and validator source, template,
runtime, schemas, LLM attempts (if any), and full local materialization result.
It is audit evidence, not an effectiveness result. API keys are never recorded.

Builder validates property-specific fuzz domains: empty/nonempty possibilities
and equality/mismatch possibilities cannot be established by varying fill alone.
Fixed rank/dtype or unsupported exact predicate forms are capability gaps, not
invalid Knowledge. Ordinary recipes are source-backed bounded generator subsets
and apply only to expected_valid branches. The generic validator contains no API
name dispatch for these rules; versioned recipe data carries source provenance.
Recipes do not fix historical input dimensions or promise all legal API inputs.

Catalog v6 adds a bounded fuzz-selected rank constructor and a generic
drop-last reference-shape transform. Source-backed companion-argument rules
reject only domains proved wholly incompatible with an API relation unless the
same violation is explicitly targeted by the HarnessSpec. Mixed valid/invalid
domains remain admissible, so this mask check is not an ordinary-input guard and
does not turn boundary exploration into reproduction.

An immutable revision may use --strategy-review for an exact needs_revision
parent review. Catalog changes require --revision-trigger catalog_update and a
matching archived parent Catalog. --adopt-parent revalidates unchanged code
without an LLM; it cannot automatically repair a failing implementation.

Artifact --preflight-only checks exact inputs, semantic fidelity, source spans
and event maps without creating an executable Artifact or claiming human
approval. Actual Artifact production requires --strategy-review with an exact
approved review. Target c10::Error is caught at the target call, recorded as
target_api_exception, and skips after-call observers. Native signal/sanitizer
faults are not caught. A call-site event is not internal native-code coverage.
Runner bindings survive into Artifact metadata as requested capabilities; they
do not prove Tensor snapshots or all external process outcomes were collected.

The paired resource policy explicitly limits rank/dimensions/dtypes and uniform
Tensor fill. Integer constructors consume enough bytes for the declared int64
interval; floating constructors have 256 possible positions. Unsupported
predicate preconditions, Tensor layouts, elementwise fill and return conversions
must be reported as capability limitations, not silently counted as coverage.

## Status

This document defines the semantic boundary of the final Builder-materialized
Strategy Plan record. The normative local shape is
`strategy_plan_record.schema.json`; cross-record, Catalog, type-flow, exact
reference, fuzz-dependency, and source-review checks are enforced by
`build_strategy_plan_json.py`.

## 1. Layer position

```text
approved HarnessSpec v2.2
        + approved HarnessSpec review
        + approved API/Helper Profiles
        + approved Primitive Catalog
        v
constrained Strategy synthesis (LLM chooses allowed non-target operations)
        v
deterministic Builder materialization and validation
        v
machine-valid Strategy Plan v1.3 (not_reviewed)
        v
external human Strategy review
        v
Harness Artifact generation
```

HarnessSpec owns the test intent. Strategy owns the executable arrangement of
typed operations. The Harness Artifact Builder owns C++ emission. The Runner
owns process termination, timeout, signal, sanitizer, and coverage events.

## 2. Primitive model

A Primitive is a typed semantic operation with:

- a stable `primitive_id` and lifecycle `primitive_kind`;
- exact input, output, and parameter contracts;
- allowed template slots;
- declared predicate/role/phase/check support;
- a fuzz-dependency policy (`none`, `propagates`, or `produces`);
- deterministic failure outcomes;
- one emitter/helper/API implementation binding; and
- explicit limitations.

The five responsibility families are value construction, constraint/relation,
target invocation, in-process observation, and behavior checking. This is a
project taxonomy derived from the API-test lifecycle, not a claim of a standard
or universally complete taxonomy. Runner events and review decisions are not
ordinary in-process Primitives.

## 3. Plan identity and immutable revision

`identity` binds the Strategy to framework, API, and HarnessSpec mode.
`revision_information` makes each correction a new immutable revision.
Generated records never become approved by editing embedded fields; external
review records own human decisions.

## 4. Exact source context

`source_context` contains:

- `harness_spec_ref`: exact Spec ID, revision, and canonical hash;
- `harness_spec_review_ref`: exact approved external review ID, revision, hash,
  and path;
- `strategy_catalog_ref`: exact Catalog ID, version, and canonical hash; and
- `derived_from_strategy_ref`: exact prior Strategy when deterministic rebinding
  is used, otherwise null.

The Builder rejects any subject ID, revision, hash, decision, or path mismatch.

## 5. Branch strategy

There is exactly one Strategy branch for each HarnessSpec branch. Branch order
follows the Spec. A Branch contains:

- ordered `steps`;
- `spec_bindings`; and
- Builder-derived `failure_handlers`.

Initial Bug-aware Static/Adaptive synthesis replaces `br_default` with the exact
branch from the validated controlled-baseline Strategy. This preserves paired
comparability and prevents an LLM from changing the control condition.

## 6. Strategy step

Each Step selects one Catalog Primitive, one permitted template slot, exact
input and parameter bindings, and exact output ports. Values come from Catalog
built-ins or earlier outputs in the same branch. No cross-branch or forward
references are allowed.

API defaults are represented by omitting an optional target-call input binding.
Explicit `None` is the Catalog built-in `none`. Required API ports must be
bound. The resolved target-call Primitive may have zero, one, or multiple
return ports.

## 7. HarnessSpec v2.2 bindings

Traceable element types are:

- `global_constraint`;
- `branch_constraint`;
- `target_condition`;
- `behavior_observation`; and
- `behavior_check`.

`in_harness_steps` bindings contain one or more ordered implementation Step IDs
and no Runner events. `runner_event` bindings contain no Step IDs and are valid
only for `behavior_observation` at `on_target_api_termination`.

The Builder binds termination observations to all of:

- `target_api_returned`;
- `caught_exception`;
- `process_exit`;
- `process_signal`;
- `timeout`; and
- `sanitizer_report`.

This declares the Runner outcomes to collect without converting observation
prose into a pass/fail Oracle. Artifact metadata retains the requested subjects.
Whether the actual Runner captured them requires separate runtime evidence.

## 8. Exploration freedom and anti-reproduction rules

Default branches must transitively feed fuzz-dependent values to required,
non-optional Tensor target inputs. Legitimate None/optional buffers and omitted
trailing defaults are exempt; there must still be a meaningful target-input
degree of freedom. Knowledge-directed branches must retain at least one meaningful
fuzz-dependent target input.

An `exploration_variable` is observed, not imposed as an unconditional guard.
It may be true or false on any single execution. A Strategy must not invent
exact historical shapes, values, seeds, or exception text. Bounded ranks,
dimensions, and scalar ranges are operational experiment policy and must be
reported as such.

An `activation_required` condition may be constructed or guarded only to the
degree explicitly required by the structured predicate.

## 9. Validation ownership

JSON Schema validates local record shape, required fields, enums, and conditional
binding payloads. The Python Builder validates:

- exact API/Profile/Review/Catalog references;
- one Strategy branch per Spec branch;
- one target call per branch;
- ports, parameters, types, value order, and slot order;
- predicate, role, phase, and check-level support;
- exact required Spec coverage;
- Runner observation ownership;
- auxiliary-step dataflow ancestry;
- deterministic failure handlers;
- default/Knowledge fuzz dependence; and
- exact controlled-baseline default-branch reuse.

## 10. Human review

The external Strategy Review Record applies these criteria:

- `SR-01 Provenance`: exact approved sources and hashes;
- `SR-02 Mapping completeness`: all required structured elements bound once;
- `SR-03 Exploration freedom`: no ungrounded historical-input fixation;
- `SR-04 Semantic fidelity`: predicates, roles, phases, and API defaults match;
- `SR-05 Observation ownership`: Harness versus Runner boundary is correct;
- `SR-06 Catalog/emitter consistency`: every Step is actually materializable;
- `SR-07 Control equality`: Static/Adaptive `br_default` exactly equals the
  approved baseline Strategy branch; and
- `SR-08 Claim scope`: observations are not mislabeled as Oracles or evidence of
  effectiveness.

Blocking findings yield `needs_revision`. Advisory findings may accompany an
approval only when they do not change executable semantics. Reviewers inspect
and record findings; they do not edit generated Plan JSON in place.

## 11. Primitive coverage policy

Catalog coverage is capability-driven, not an assertion that every possible API
is already supported. The current general interface includes CPU Tensor
construction for float32/int64/bool, bounded zero/dynamic shapes, floating/
integer/boolean scalar construction, explicit or fuzz-selected optional None, API-default
omission, equality/inequality and rank/shape/numel observation, multi-input
calls, and zero/one/multiple direct returns.

Unsupported devices, dtypes, packed wrapper transformations, stateful objects,
or predicates fail closed as explicit gaps. Adding a capability requires a new
Catalog revision, emitter implementation, tests, and human approval before it
can enter an experiment.
