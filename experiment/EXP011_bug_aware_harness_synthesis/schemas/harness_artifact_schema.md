# Harness Artifact Schema v1.2

## 1. Purpose

A Harness Artifact record describes one immutable C++ fuzzing Harness produced
from one exact Strategy Plan revision.

It records:

- the Strategy revision used for generation;
- the generated source file;
- the mapping from Strategy Steps to C++ segments;
- inserted runtime instrumentation;
- static validation and compilation results;
- Generator provenance.

It does not store fuzzing results, coverage, crashes, runtime event counts,
feedback decisions, or generation reasoning.

---

## 2. Layer Boundary

This Schema defines the structure and semantics of a Harness Artifact record.

It does not define:

- Knowledge selection;
- HarnessSpec synthesis;
- Strategy Primitive selection;
- Strategy Step ordering;
- Emitter implementation;
- compilation repair;
- fuzzing execution;
- metric calculation;
- feedback adjustment.

A record is created only after a complete C++ source file has been materialized.

If source generation fails before that point, the Generator saves a separate
failure log and does not create a Harness Artifact record.

A finalized Harness Artifact record is immutable.

---

## 3. Common Types

### 3.1 Identifier

Internal identifiers are non-empty lowercase strings containing letters,
digits, and underscores.

Recommended pattern:

```text
^[a-z][a-z0-9_]*$
```

Identifiers copied from upstream records retain their original valid syntax.

### 3.2 SHA-256 String

A SHA-256 string contains exactly 64 lowercase hexadecimal characters.

```text
^[0-9a-f]{64}$
```

Hashes are calculated from the exact bytes of the saved file.

### 3.3 Timestamp

Timestamps use RFC 3339 UTC format.

### 3.4 Relative Path

A relative path:

- is relative to the repository root;
- uses `/` as the separator;
- is not absolute;
- does not contain `..`.

### 3.5 File Reference

A File Reference contains:

| Field | Type | Required | Description |
| --- | --- | ---: | --- |
| `relative_path` | relative path | yes | Referenced file |
| `content_hash` | SHA-256 string | yes | Hash of the exact file bytes |

### 3.6 Artifact Reference

An Artifact Reference contains:

| Field | Type | Required | Description |
| --- | --- | ---: | --- |
| `artifact_id` | non-empty string | yes | Stable Artifact identifier |
| `artifact_version` | positive integer or non-empty string | yes | Exact Artifact version |
| `content_hash` | SHA-256 string | yes | Hash of the exact Artifact record |

### 3.7 Strategy Revision Reference

A Strategy Revision Reference contains:

| Field | Type | Required | Description |
| --- | --- | ---: | --- |
| `strategy_id` | non-empty string | yes | Stable Strategy identity |
| `revision_number` | positive integer | yes | Exact Strategy revision |
| `content_hash` | SHA-256 string | yes | Hash of the exact Strategy Plan record |

### 3.8 Source Span

A Source Span contains:

| Field | Type | Required | Description |
| --- | --- | ---: | --- |
| `start_line` | positive integer | yes | First included line |
| `end_line` | positive integer | yes | Last included line |

Both endpoints are inclusive.

`start_line == end_line` represents one source line.

`end_line` must be greater than or equal to `start_line`.

A Source Span is valid only for the exact source file identified by
`source_artifact.content_hash`.

---

## 4. Top-Level Record

A Harness Artifact record contains:

```json
{
  "schema_version": "1.2",
  "record_type": "harness_artifact",
  "identity": {},
  "source_context": {},
  "source_artifact": {},
  "materialization_map": [],
  "instrumentation_map": [],
  "validation": {},
  "provenance": {}
}
```

All top-level fields are required.

Unknown top-level fields are prohibited.

---

## 5. Identity

`identity` identifies the immutable generated Harness.

| Field | Type | Required | Description |
| --- | --- | ---: | --- |
| `harness_artifact_id` | identifier | yes | Stable Artifact identifier |
| `generation_key` | SHA-256 string | yes | Deterministic generation identity |

Recommended Artifact ID format:

```text
ha_<strategy-id>_r<strategy-revision>_<generation-key-prefix>
```

The prefix is the first 12 characters of `generation_key`.

The complete `generation_key` is authoritative.

The Generator calculates `generation_key` from:

- the exact Strategy Revision Reference;
- Generator ID and version;
- Generator entrypoint content hash;
- Generator component paths and content hashes, ordered by `relative_path`.

The original order of `component_refs` does not affect `generation_key`.

Timestamps, output paths, process IDs, and logging options do not participate in
`generation_key`.

Framework, target API, experiment mode, HarnessSpec, Catalog, Template, API
Profile, and Helper Profiles are resolved through the referenced Strategy Plan
and are not repeated here.

---

## 6. Source Context

`source_context` identifies the exact Strategy Plan implemented by this Harness.

```json
{
  "strategy_revision_ref": {
    "strategy_id": "strategy_pytorch_relu_static",
    "revision_number": 1,
    "content_hash": "0000000000000000000000000000000000000000000000000000000000000000"
  }
}
```

| Field | Type | Required | Description |
| --- | --- | ---: | --- |
| `strategy_revision_ref` | Strategy Revision Reference | yes | Exact Strategy Plan revision |

The referenced Strategy Plan resolves the exact:

- HarnessSpec revision;
- Strategy Catalog version;
- API Profile;
- Helper Profiles;
- Harness Template;
- Primitive and Emitter bindings.

These references are not duplicated in the Harness Artifact record.

---

## 7. Source Artifact

`source_artifact` identifies the complete generated C++ source file.

```json
{
  "relative_path": "experiment/.../harnesses/.../main.cpp",
  "content_hash": "0000000000000000000000000000000000000000000000000000000000000000",
  "encoding": "utf-8",
  "newline": "lf",
  "language": "cpp",
  "entrypoint": "LLVMFuzzerTestOneInput"
}
```

| Field | Type | Required | Allowed value |
| --- | --- | ---: | --- |
| `relative_path` | relative path | yes | Generated source path |
| `content_hash` | SHA-256 string | yes | Hash of the complete source |
| `encoding` | string | yes | `utf-8` |
| `newline` | string | yes | `lf` |
| `language` | string | yes | `cpp` |
| `entrypoint` | string | yes | `LLVMFuzzerTestOneInput` |

The source content is stored in the referenced file and is not embedded in the
record.

---

## 8. Materialization Map

`materialization_map` maps every Strategy Step to exactly one continuous C++
segment.

The array must be non-empty.

Each entry contains:

| Field | Type | Required | Description |
| --- | --- | ---: | --- |
| `branch_id` | non-empty string | yes | Exact Strategy branch |
| `step_id` | non-empty string | yes | Exact Strategy Step |
| `primitive_id` | identifier | yes | Exact Catalog Primitive |
| `emitter_id` | identifier | yes | Exact Catalog Emitter |
| `template_slot` | enum | yes | Slot receiving the segment |
| `emitted_segment_id` | identifier | yes | Generated segment identifier |
| `materialized_failure_handler_ids` | array of identifiers | yes | Failure Handlers emitted inside the segment |
| `source_span` | Source Span | yes | Segment location in final source |

Allowed `template_slot` values are:

```text
input_construction
pre_call_transform
pre_call_guard
pre_call_observation
target_call
post_call_observation
oracle_check
artifact_logging
cleanup
```

Materialization constraints:

- every Strategy Step appears exactly once;
- every emitted segment appears exactly once;
- one Step produces one continuous segment;
- one segment belongs to one Step;
- different materialized segment spans do not overlap;
- the Primitive, Emitter, slot, and branch match the Strategy Plan and Catalog;
- every Failure Handler appears exactly once under its triggering Step;
- Template and Generator infrastructure are not represented as Strategy Steps;
- code from different Strategy Steps is not fused.

A segment may contain multiple C++ statements and multiple instrumentation
events.

---

## 9. Instrumentation Map

`instrumentation_map` records runtime events inserted into the generated source.

It proves that instrumentation code was materialized. It does not prove that the
event occurred during fuzzing.

The array must be non-empty.

Each entry contains:

| Field | Type | Required | Description |
| --- | --- | ---: | --- |
| `instrumentation_binding_id` | identifier | yes | Instrumentation binding |
| `runtime_site_id` | non-negative integer | yes | Artifact-local runtime counter index |
| `event_kind` | enum | yes | Runtime event kind |
| `event_key` | non-empty string | yes | Stable runtime event key |
| `branch_id` | non-empty string | yes | Exact Strategy branch |
| `trace_refs` | array | yes | Related HarnessSpec or Strategy elements |
| `observation_locator` | Observation Locator | conditional | Exact nested Observation Point |
| `source_owner` | Source Owner | yes | Code region owning the event |
| `source_span` | Source Span | yes | Event location in final source |

Instrumentation IDs, runtime site IDs, and event keys are unique within one
Artifact. Runtime site IDs form the contiguous range from `0` through
`instrumentation_map.length - 1`.

Instrumentation spans may be contained within their owning materialized segment.

### 9.1 Event Kind

Allowed `event_kind` values are:

```text
branch_entered
input_constructed
input_rejected
observation_captured
activation_checked
activation_true
activation_unevaluable
activation_check_error
branch_activation_checked
branch_activation_true
branch_activation_unevaluable
branch_activation_check_error
target_api_reached
target_api_completed
target_api_exception
oracle_evaluated
oracle_passed
oracle_failed
```

`activation_false` is not stored because it is derived from:

```text
activation_checked - activation_true
```

`activation_checked` counts successful Boolean evaluations.
`activation_unevaluable` counts attempted evaluations that cannot produce a
Boolean result from the available runtime values. `activation_check_error`
counts failures in the checker implementation or execution.

The `branch_activation_*` events record the joint outcome across all required
Activation Targets in one Branch and one fuzz case. They are distinct from the
Target-level `activation_*` events and must not be reconstructed by summing
Target counts.

### 9.2 Trace Reference

Each Trace Reference contains:

| Field | Type | Required | Description |
| --- | --- | ---: | --- |
| `ref_type` | enum | yes | Referenced element category |
| `ref_id` | non-empty string | yes | Exact upstream identifier |

Allowed `ref_type` values are:

```text
evaluation_target
global_constraint
branch_constraint
branch_precondition
target_property
activation_target
oracle_requirement
failure_handler
```

`observation_point` is not a reference type because an Observation Point is a
nested HarnessSpec object without an independent ID.

`branch` is represented by the entry's `branch_id`. A Strategy Step is resolved
through `source_owner` and the Materialization Map. `trace_refs` may therefore
be empty for infrastructure and Step-local events.

### 9.3 Observation Locator

`observation_locator` identifies one Observation Point inside an Activation
Target.

It contains:

| Field | Type | Required | Description |
| --- | --- | ---: | --- |
| `observation_role` | enum | yes | Role copied from HarnessSpec |
| `observation_point` | enum | yes | Phase copied from HarnessSpec |

Allowed `observation_role` values are:

```text
evaluate
before
after
```

Allowed `observation_point` values are:

```text
before_target_api_call
after_target_api_call
```

`observation_locator`:

- is required only for `observation_captured`;
- is prohibited for all other event kinds;
- must exactly match one Observation Point in the referenced Activation Target.

### 9.4 Source Owner

A Source Owner contains:

| Field | Type | Required | Description |
| --- | --- | ---: | --- |
| `owner_type` | enum | yes | Owning generated-code category |
| `owner_id` | non-empty string | yes | Exact segment or infrastructure-region ID |

Allowed `owner_type` values are:

```text
strategy_segment
generator_infrastructure
```

For `strategy_segment`, `owner_id` references an `emitted_segment_id` in the
Materialization Map.

For `generator_infrastructure`, `owner_id` is one of:

```text
fuzzer_entry
branch_dispatch
branch_entry
iteration_exit
```

These IDs are shared with the versioned Generator and Harness Template.

### 9.5 Event Reference Requirements

| Event | Required trace references |
| --- | --- |
| `branch_entered` | none |
| `input_constructed` | none |
| `input_rejected` | Failure Handler |
| `observation_captured` | Activation Target and Target Property |
| `activation_checked` | Evaluation Target; plus Activation Target and Target Property when implementing a HarnessSpec Target |
| `activation_true` | Same references as the matching `activation_checked` event |
| `activation_unevaluable` | Same references as the matching `activation_checked` event |
| `activation_check_error` | Same references as the matching `activation_checked` event |
| `branch_activation_checked` | every Activation Target and Target Property in the Branch |
| `branch_activation_true` | every Activation Target and Target Property in the Branch |
| `branch_activation_unevaluable` | every Activation Target and Target Property in the Branch |
| `branch_activation_check_error` | every Activation Target and Target Property in the Branch |
| `target_api_reached` | none; Source Owner identifies the target-call Step |
| `target_api_completed` | none; Source Owner identifies the target-call Step |
| `target_api_exception` | none; Source Owner identifies the target-call Step |
| Oracle events | Oracle Requirement |

For every Activation Target:

- each declared Observation Point has exactly one matching
  `observation_captured` event;
- exactly one `activation_checked` event is present;
- exactly one `activation_true` event is present;
- exactly one `activation_unevaluable` event is present;
- exactly one `activation_check_error` event is present;
- each Target-level event references exactly one Evaluation Target, that
  Activation Target, and its Target Property;
- the activation events are evaluated only after all required observations are
  available.

Baseline measurement events reference one Evaluation Target but no HarnessSpec
Activation Target or Target Property. For every `(branch_id,
evaluation_target_id)` represented in an Artifact, the four Target-level event
kinds form one complete, non-duplicated quartet. The frozen Evaluation Target
Manifest—not this record—defines which Targets must exist across all groups.

A non-transition Target Property has one `evaluate` Observation Point.

A `state_transition` Target Property has one `before` and one `after`
Observation Point.


For every Branch with one or more Activation Targets, exactly one matching
`branch_activation_checked`, `branch_activation_true`,
`branch_activation_unevaluable`, and `branch_activation_check_error` event is
present. The Activation Target and Target Property references of each event
equal exactly the corresponding sets for that Branch. Other trace-reference
types may still describe relevant constraints. A Branch without Activation
Targets has none of these events.

For one Activation Target in one runtime snapshot:

- `activation_true <= activation_checked`;
- successful, unevaluable, and checker-error outcomes are recorded separately;
- a successful check may coexist with unevaluable or checker-error occurrences
  from other iterations.

The evaluation layer derives the Target state in this order: invalid snapshot
or binding gives `instrumentation_error`; otherwise any successful check gives
`checked_true` when a true event exists and `checked_false` otherwise;
without a successful check, an unevaluable event gives `unevaluable`, a
checker-error event gives `instrumentation_error`, and no event gives
`not_checked`.

---

## 10. Validation

`validation` records deterministic checks and optional human review.

```json
{
  "static_validation": {},
  "compile_check": {},
  "human_review": {}
}
```

### 10.1 Static Validation

`static_validation` contains:

| Field | Type | Required | Description |
| --- | --- | ---: | --- |
| `status` | enum | yes | Overall result |
| `checks` | non-empty array | yes | Deterministic checks executed |
| `issues` | array | yes | Detected issues |

Allowed `status` values are:

```text
passed
failed
```

Each check contains:

| Field | Type | Required |
| --- | --- | ---: |
| `check_id` | identifier | yes |
| `status` | `passed` or `failed` | yes |

Each issue contains:

| Field | Type | Required | Description |
| --- | --- | ---: | --- |
| `issue_code` | identifier | yes | Stable issue category |
| `severity` | enum | yes | `error` or `warning` |
| `message` | non-empty string | yes | Concise factual description |
| `related_ids` | array of non-empty strings | yes | Related identifiers |

If any check fails or any issue has severity `error`,
`static_validation.status` is `failed`.

### 10.2 Compile Check

`compile_check` contains:

| Field | Type | Required | Description |
| --- | --- | ---: | --- |
| `status` | enum | yes | Compilation result |
| `command_argv` | array of strings | yes | Planned or executed command |
| `build_environment_ref` | Artifact Reference or null | yes | Exact build environment |
| `exit_code` | integer or null | yes | Compiler process exit code |
| `skip_reason` | non-empty string or null | yes | Reason compilation was skipped |
| `diagnostics_ref` | File Reference or null | yes | Saved compiler diagnostics |
| `binary_artifact` | File Reference or null | yes | Compiled Harness binary |

Allowed `status` values are:

```text
passed
failed
skipped
```

For `passed`:

- `command_argv` is non-empty;
- `build_environment_ref` is non-null;
- `exit_code = 0`;
- `skip_reason = null`;
- `binary_artifact` is non-null.

For `failed`:

- `command_argv` is non-empty;
- `exit_code` is non-zero or `null` when no exit code was produced;
- `skip_reason = null`;
- `diagnostics_ref` is non-null;
- `binary_artifact = null`.

For `skipped`:

- `command_argv` may be empty or non-empty;
- `exit_code = null`;
- `skip_reason` is non-null;
- `binary_artifact = null`.

`diagnostics_ref`, when present, references a UTF-8 file containing the saved
compiler standard output and standard error.

If static validation fails, compilation is skipped.

A Harness may enter a formal fuzzing run only when static validation and
compilation both pass.

### 10.3 Human Review

`human_review` contains:

| Field | Type | Required | Description |
| --- | --- | ---: | --- |
| `status` | enum | yes | Review result |
| `reviewer_id` | non-empty string or null | yes | Reviewer identifier |
| `reviewed_at` | timestamp or null | yes | Review time |
| `review_note` | string or null | yes | Concise factual note |

Allowed `status` values are:

```text
not_reviewed
approved
changes_requested
```

For `not_reviewed`:

- `reviewer_id = null`;
- `reviewed_at = null`;
- `review_note = null`.

For `approved`:

- `reviewer_id` and `reviewed_at` are non-null;
- `review_note` may be `null`.

For `changes_requested`:

- `reviewer_id` and `reviewed_at` are non-null;
- `review_note` is non-empty.

A non-null `review_note` contains at most 1000 Unicode characters.

Human review does not override automatic validation.

---

## 11. Provenance

`provenance` identifies the exact Generator implementation and repository state.

It contains:

```json
{
  "generator": {
    "generator_id": "deterministic_harness_generator",
    "generator_version": "1.0",
    "entrypoint_ref": {
      "relative_path": "experiment/.../scripts/generate_harness.py",
      "content_hash": "0000000000000000000000000000000000000000000000000000000000000000"
    },
    "component_refs": []
  },
  "generation_run_id": "hgen_001",
  "generated_at": "2026-09-08T00:00:00Z",
  "repository_commit": "0000000000000000000000000000000000000000",
  "working_tree_state": "clean",
  "working_tree_diff_ref": null
}
```

### 11.1 Generator

| Field | Type | Required | Description |
| --- | --- | ---: | --- |
| `generator_id` | identifier | yes | Generator identity |
| `generator_version` | non-empty string | yes | Generator version |
| `entrypoint_ref` | File Reference | yes | Exact Generator entrypoint |
| `component_refs` | array of File References | yes | Additional Generator source files |

`component_refs` is empty when the entrypoint contains the complete Generator
and Emitter implementation.

Every source file that can affect generated code must appear as the entrypoint
or a component.

Duplicate component paths are prohibited.

### 11.2 Generation Context

| Field | Type | Required | Description |
| --- | --- | ---: | --- |
| `generation_run_id` | non-empty string | yes | Unique Generator invocation |
| `generated_at` | timestamp | yes | Artifact creation time |
| `repository_commit` | Git object ID | yes | Exact repository commit |
| `working_tree_state` | enum | yes | Repository state |
| `working_tree_diff_ref` | File Reference or null | yes | Saved diff when dirty |

`repository_commit` contains either 40 or 64 lowercase hexadecimal characters.

Allowed `working_tree_state` values are:

```text
clean
dirty
unknown
```

When `working_tree_state = dirty`, `working_tree_diff_ref` is non-null and
references a UTF-8 unified diff.

Otherwise, `working_tree_diff_ref = null`.

`generation_run_id` and `generated_at` do not participate in `generation_key`.

Output-affecting free-form options are prohibited. Such behavior must be
represented by a versioned Strategy Plan, Catalog, Template, Generator, or
Generator component.

---

## 12. Cross-Field Invariants

A valid Harness Artifact record satisfies:

1. The complete source file exists and matches `source_artifact.content_hash`.
2. The Strategy Plan exists and matches `source_context.strategy_revision_ref`.
3. Every Strategy Step is materialized exactly once.
4. Every Failure Handler is materialized under its triggering Step exactly once.
5. Every materialized Primitive, Emitter, slot, and branch matches the Strategy
   Plan and Catalog.
6. Materialized segment spans are valid, non-overlapping, and within the source.
7. Every Strategy-owned event references an existing emitted segment.
8. Every Generator-owned event references a valid infrastructure region.
9. Every Trace Reference resolves in the Strategy Plan or its HarnessSpec.
10. Every Observation Locator matches the referenced Activation Target.
11. Every required observation and activation event is present exactly once.
12. Instrumentation IDs, runtime site IDs, and event keys are unique within the
    Artifact; runtime site IDs are contiguous from zero.
13. Static validation status agrees with its checks and issues.
14. Compile status agrees with its command, environment, exit code, diagnostics,
    skip reason, and binary fields.
15. Runtime counts, coverage, crashes, and feedback results are absent.
16. No unrecognized top-level field is present.

Structural constraints are enforced by the corresponding JSON Schema.

Cross-record, reference-resolution, source-span, semantic, and content-hash
constraints are enforced by the deterministic Python Validator.

---

## 13. Readiness

The record does not contain a separate `lifecycle_status` or
`readiness_status`.

Fuzzing readiness is derived as:

```text
static_validation.status == passed
and
compile_check.status == passed
```

Artifact inclusion, exclusion, or replacement in an experiment is managed by
the experiment manifest rather than by mutating this immutable record.

Artifact lineage is resolved through the referenced Strategy revision. Runtime
results are stored in separate Fuzzing Run records.
