# Helper Capability Profile Schema v1.0

## 1. Purpose

A Helper Capability Profile is a versioned, evidence-backed description of one
public C++ Helper function available to Harness synthesis. It records the
callable interface, capability boundary, fuzz-input interaction, build
configuration, and validation state.

It does not select a Helper for an API, prescribe execution order, or contain a
full Helper implementation or Harness.

## 2. Core Invariants

One Profile represents one public callable under one framework release,
backend, provider, and behavior-affecting configuration.

Changing the callable identity, framework release, backend, provider, or
configuration creates a new `profile_id`. Correcting or changing the same
logical target creates a new immutable `revision`.

Every asserted capability, constraint, and behavior claim has evidence.
Unknown behavior remains explicit. Only `execution_readiness = ready` may be
treated as an executable Helper binding; other Profiles remain available for
traceability and capability-gap analysis.

## 3. Top-Level Fields

| Field | Type | Required in record | Description |
| --- | --- | --- | --- |
| `schema_version` | string | yes | Record-format version |
| `profile_id` | string | yes | Stable Helper identity |
| `revision` | positive integer | yes | Internal Profile revision |
| `metadata` | object | yes | Builder-owned lineage and hash metadata |
| `target_environment` | object | yes | Framework, provider, and configuration |
| `callable_interface` | object | yes | Public C++ invocation contract |
| `capability_contract` | object | yes | Supported behavior and limitations |
| `build_contract` | object | yes | Build facts and direct dependencies |
| `validation` | object | yes | Validation and execution readiness |
| `evidence` | array | yes | Referenced evidence records |
| `review` | object | yes | Human-review state |

Use `null` for an unavailable scalar or object and `[]` for an empty list.
Identifiers are stable, non-empty, independent of timestamps and absolute local
paths, and unique within their scope. Local references resolve within the same
Profile; external Profile IDs resolve through the generated Helper Catalog.

## 4. `metadata`

| Field | Type | Required in record | Description |
| --- | --- | --- | --- |
| `parent_revision_ref` | Profile Revision Reference or null | yes | Immediate predecessor |
| `generated_at` | timestamp | yes | Materialization time |
| `builder_version` | string | yes | Deterministic Builder version |
| `content_hash` | SHA-256 string | yes | Immutable record hash |

### 4.1 Profile Revision Reference

| Field | Type | Required in record | Description |
| --- | --- | --- | --- |
| `profile_id` | string | yes | Referenced Profile |
| `revision` | positive integer | yes | Earlier internal revision |
| `content_hash` | SHA-256 string | yes | Referenced record hash |

Revision 1 has `parent_revision_ref = null`; later revisions reference the
immediate retained revision with the same `profile_id`. The Builder owns this
section, `profile_id`, and `revision`.

Version meanings are distinct: `schema_version` is the record format,
`framework_version` is the external release, `provider_revision` is the
external FlashFuzz or project revision, `configuration_id` is a coexisting
build variant, and `revision` is the internal Profile revision.

## 5. `target_environment`

| Field | Type | Required in record | Description |
| --- | --- | --- | --- |
| `framework` | string | yes | Framework name |
| `framework_version` | string | yes | Exact release |
| `framework_commit` | Git object ID | yes | Exact framework revision |
| `backend` | enum | yes | `cpu`, `cuda`, `mps`, or `other` |
| `provider` | enum | yes | `flashfuzz_base` or `project_overlay` |
| `provider_revision` | string | yes | Exact provider revision |
| `configuration_id` | string | yes | Behavior-affecting build variant |

Different provider revisions of the same logical Helper may form a revision
chain. Configurations that coexist use different `configuration_id` values.

## 6. `callable_interface`

| Field | Type | Required in record | Description |
| --- | --- | --- | --- |
| `namespace` | string | yes | Declaring C++ namespace |
| `function_name` | string | yes | Unqualified function name |
| `qualified_name` | string | yes | Fully qualified callable name |
| `declaration` | string | yes | Normalized public declaration |
| `return` | Return object | yes | Return contract |
| `parameters` | array of Parameter objects | yes | Ordered parameters |
| `required_include` | string | yes | Header required by the caller |
| `invocation_template` | string or null | yes | Builder-generated call syntax |
| `evidence_refs` | array of Evidence IDs | yes | Interface evidence |

The Builder derives `invocation_template` from the qualified name and parameter
order, using symbolic placeholders. It contains no declarations, control flow,
or strategy. Failure to derive it produces `null` and a Validation Issue;
generated templates are not manually edited.

### 6.1 Parameter Object

| Field | Type | Required in record | Description |
| --- | --- | --- | --- |
| `parameter_id` | string | yes | Profile-local identifier |
| `name` | string | yes | Declared name |
| `ordinal` | non-negative integer | yes | Declaration order |
| `cpp_type` | string | yes | Normalized C++ type |
| `direction` | enum | yes | `in`, `out`, or `inout` |
| `semantic_role` | enum | yes | Normalized role |
| `default` | Default object | yes | Default-argument state |
| `evidence_refs` | array of Evidence IDs | yes | Supporting evidence |

Allowed roles: `fuzz_data`, `fuzz_size`, `byte_offset`, `selector_byte`,
`tensor`, `expected_tensor`, `actual_tensor`, `dtype_selector`, `rank`, `shape`,
`element_count`, `element_size`, `tolerance`, `message`, `path`, `directory`,
`timestamp`, `configuration`, and `other`.

### 6.2 Default Object

| Field | Type | Required in record | Description |
| --- | --- | --- | --- |
| `kind` | enum | yes | `no_default`, `literal`, or `unresolved` |
| `value` | string or null | yes | Exact spelling when `literal` |

`value` is non-null only for `literal`. Argument omission is derived from this
object; no separate `required` flag is stored.

### 6.3 Return Object

| Field | Type | Required in record | Description |
| --- | --- | --- | --- |
| `cpp_type` | string | yes | Normalized C++ return type |
| `semantic_role` | enum | yes | Normalized return role |
| `evidence_refs` | array of Evidence IDs | yes | Supporting evidence |

Allowed return roles: `void`, `dtype`, `rank`, `shape`, `byte_buffer`, `tensor`,
`comparison_result`, `boolean`, `timestamp`, `string`, and `other`.

## 7. `capability_contract`

| Field | Type | Required in record | Description |
| --- | --- | --- | --- |
| `capability_kind` | enum | yes | Primary capability category |
| `summary` | string | yes | Concise factual behavior |
| `fuzz_input_contract` | Fuzz Input Contract object | yes | Fuzz-data interaction |
| `domain_constraints` | array of Domain Constraint objects | yes | Structured boundaries |
| `behavior_claims` | array of Behavior Claim objects | yes | Non-duplicative semantic facts |
| `side_effects` | Side Effects object | yes | Observable effects |
| `determinism` | enum | yes | Determinism under this configuration |
| `evidence_refs` | array of Evidence IDs | yes | Overall capability evidence |

Allowed capability kinds: `byte_decoder`, `argument_generator`,
`tensor_constructor`, `tensor_transformer`, `relation_enforcer`, `oracle`,
`artifact_handler`, and `utility`. The summary must not recommend an API,
Knowledge record, branch, priority, or budget.

### 7.1 Fuzz Input Contract Object

| Field | Type | Required in record | Description |
| --- | --- | --- | --- |
| `interaction_mode` | enum | yes | Fuzz-derived-data interaction |
| `data_parameter_refs` | array of Parameter IDs | yes | Raw-buffer parameters |
| `size_parameter_refs` | array of Parameter IDs | yes | Buffer-size parameters |
| `offset_parameter_ref` | Parameter ID or null | yes | Shared cursor |
| `offset_effect` | enum | yes | Cursor mutation |
| `consumption_mode` | enum | yes | Cursor-based byte consumption |
| `minimum_bytes` | non-negative integer or null | yes | Proven lower bound |
| `maximum_bytes` | non-negative integer or null | yes | Proven upper bound |
| `consumption_formula` | string or null | yes | Symbolic rule when known |

Allowed interaction modes: `none`, `selector_value`, `decode_buffer`,
`record_buffer`, `mixed`, and `unknown`. Allowed offset effects: `none`,
`advances`, `may_advance`, `resets`, `may_advance_or_reset`, and `unknown`.
Allowed consumption modes: `none`, `fixed`, `bounded`, `data_dependent`,
`remaining_input`, and `unknown`.

`advances` means every normal return moves the cursor forward; `may_advance`
means it moves forward or stays unchanged. `resets` assigns a boundary or
initial value instead of consuming forward. `may_advance_or_reset` is reserved
for a Helper whose source contains both forward-consumption and reset paths.

`interaction_mode = none` requires empty data and size references, a null offset
reference, `offset_effect = none`, and `consumption_mode = none`.
`record_buffer` may reference data and size without cursor consumption.

### 7.2 Domain Constraint Object

| Field | Type | Required in record | Description |
| --- | --- | --- | --- |
| `constraint_id` | string | yes | Profile-local identifier |
| `subjects` | array of Subject Reference objects | yes | Constrained entities |
| `relation` | enum | yes | Constraint or cross-entity relation |
| `value` | JSON value or null | yes | Structured bound or value set |
| `verification_level` | enum | yes | Evidence strength |
| `evidence_refs` | array of Evidence IDs | yes | Supporting evidence |

Allowed relations: `equals`, `range`, `one_of`, `excludes`, `requires`,
`less_than_or_equal`, `same_as`, `compatible_with`, and `unknown`.

#### Subject Reference Object

| Field | Type | Required in record | Description |
| --- | --- | --- | --- |
| `entity_kind` | enum | yes | `parameter`, `return`, `fuzz_input`, or `environment` |
| `entity_ref` | Parameter ID or null | yes | Parameter reference when applicable |
| `property` | string | yes | Normalized property token |

Multiple subjects express input-input or input-output relations; one subject
expresses a bound or membership constraint. `property` uses normalized tokens
such as `rank`, `dtype`, `value`, or `buffer_extent`, not prose.

### 7.3 Behavior Claim Object

| Field | Type | Required in record | Description |
| --- | --- | --- | --- |
| `claim_id` | string | yes | Profile-local identifier |
| `claim_kind` | enum | yes | Claim category |
| `statement` | string | yes | Concise factual statement |
| `verification_level` | enum | yes | Evidence strength |
| `evidence_refs` | array of Evidence IDs | yes | Supporting evidence |

Allowed claim kinds: `precondition`, `postcondition`, `guarantee`, `limitation`,
`fallback`, and `failure_behavior`. Allowed verification levels: `declared`,
`statically_verified`, `runtime_verified`, and `unknown`.

Constraints are structured machine-actionable predicates. Claims contain only
semantics that cannot be represented adequately as constraints. The same fact
must not occur in both arrays. `unknown` does not authorize a guessed statement.

### 7.4 Side Effects Object

| Field | Type | Required in record | Description |
| --- | --- | --- | --- |
| `status` | enum | yes | `known` or `unknown` |
| `kinds` | array of enums | yes | Confirmed effects |

Allowed kinds: `stdout_write`, `stderr_write`, `file_write`,
`directory_creation`, `parameter_mutation`, `global_state_mutation`,
`randomness`, and `other`. `known` with `[]` means no established side effect;
`unknown` requires `[]` and a non-blocking Validation Issue.

Allowed determinism values: `deterministic`, `configuration_dependent`,
`input_and_state_dependent`, `nondeterministic`, and `unknown`.

## 8. `build_contract`

| Field | Type | Required in record | Description |
| --- | --- | --- | --- |
| `compile_definitions` | array of Compile Definition objects | yes | Recorded macros and build options |
| `helper_dependencies` | array of Helper Dependency objects | yes | Direct public-Helper calls |
| `evidence_refs` | array of Evidence IDs | yes | Configuration evidence |

### 8.1 Compile Definition Object

| Field | Type | Required in record | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Macro or build-option name |
| `value` | JSON scalar or null | yes | Recorded value |
| `behavior_affecting` | boolean | yes | Whether it changes capability semantics |
| `evidence_refs` | array of Evidence IDs | yes | Supporting evidence |

### 8.2 Helper Dependency Object

| Field | Type | Required in record | Description |
| --- | --- | --- | --- |
| `profile_id` | string or null | yes | Stable dependency Profile ID when resolved |
| `qualified_name` | string | yes | Directly called public Helper |
| `resolution_status` | enum | yes | `resolved` or `unresolved` |
| `evidence_refs` | array of Evidence IDs | yes | Call-site evidence |

The Builder records direct public-Helper calls only. Transitive dependencies
are derived from the dependency graph. Internal functions and constants are
represented by evidence, constraints, or claims. A resolved dependency matches
a Profile in the same target environment; an unresolved dependency creates a
blocking issue.

## 9. `validation`

| Field | Type | Required in record | Description |
| --- | --- | --- | --- |
| `validation_status` | enum | yes | `passed`, `partial`, or `failed` |
| `execution_readiness` | enum | yes | `ready`, `unassessed`, or `blocked` |
| `checks` | array of Validation Check objects | yes | Per-check results |
| `issues` | array of Validation Issue objects | yes | Remaining problems |

### 9.1 Validation Check Object

| Field | Type | Required in record | Description |
| --- | --- | --- | --- |
| `check_id` | string | yes | Profile-local identifier |
| `check_kind` | enum | yes | Validation category |
| `status` | enum | yes | `passed`, `failed`, `not_run`, or `blocked` |
| `summary` | string | yes | Concise result |
| `evidence_refs` | array of Evidence IDs | yes | Validation evidence |
| `issue_refs` | array of Validation Issue IDs | yes | Related issues |

Allowed check kinds: `header_parse`, `definition_resolution`,
`declaration_definition_match`, `dependency_resolution`, `compile`,
`smoke_execution`, and `behavior_observation`.

`validation_status = passed` means every applicable check passed. `partial`
means no check failed but at least one check is `not_run` or `blocked`.
`failed` means at least one check failed.

- `passed` requires evidence and no issue reference.
- `failed` requires evidence and at least one issue reference.
- `not_run` requires empty evidence and issue references, with its reason in
  `summary`.
- `blocked` requires at least one issue reference; evidence is optional.

The first six checks are required for `execution_readiness = ready`.
`dependency_resolution` passes when no direct dependency exists or all resolve.
A smoke check directly invokes the Helper at least once in the pinned
environment and verifies its return, termination, or expected side effect. It
does not require fuzzing, coverage, or exhaustive inputs. Behavior observation
is optional for basic readiness.

### 9.2 Validation Issue Object

| Field | Type | Required in record | Description |
| --- | --- | --- | --- |
| `issue_id` | string | yes | Profile-local identifier |
| `issue_kind` | enum | yes | Normalized category |
| `blocking` | boolean | yes | Whether execution is blocked |
| `description` | string | yes | Concise problem statement |
| `affected_refs` | array of local references | yes | Affected fields or objects |
| `evidence_refs` | array of Evidence IDs | yes | Supporting evidence |

Allowed issue kinds: `source_unavailable`, `declaration_unresolved`,
`definition_unresolved`, `signature_mismatch`, `dependency_unresolved`,
`dependency_cycle`, `configuration_mismatch`, `compile_failure`,
`smoke_failure`, `behavior_unverified`, `evidence_gap`, and `other`.
`dependency_cycle` records a self-dependency or cycle in the resolved Helper
dependency graph. Readiness cannot be `ready` while a blocking issue remains.

## 10. `evidence`

| Field | Type | Required in record | Description |
| --- | --- | --- | --- |
| `evidence_id` | string | yes | Profile-local identifier |
| `source_kind` | enum | yes | Evidence category |
| `source_location` | string | yes | Repository, container, or artifact location |
| `source_revision` | string or null | yes | Exact source revision |
| `locator` | string or null | yes | Function, declaration, or line locator |
| `content_hash` | SHA-256 string or null | yes | Evidence content hash |
| `excerpt` | string or null | yes | Relevant excerpt, at most 1000 characters |
| `collected_at` | timestamp | yes | Collection time |

Allowed source kinds: `helper_header`, `helper_implementation`,
`build_configuration`, `curated_annotation`, `compile_log`, `smoke_test_log`,
`runtime_trace`, and `manual_review`. Excerpts contain only the minimum relevant
declaration, constant, or fragment. An annotation must also cite the source or
execution evidence supporting its semantics.

## 11. `review` and Field Ownership

| Field | Type | Required in record | Description |
| --- | --- | --- | --- |
| `review_status` | enum | yes | `unreviewed`, `approved`, `needs_revision`, or `rejected` |
| `reviewer` | string or null | yes | Reviewer identity |
| `reviewed_at` | timestamp or null | yes | Review time |
| `issue_refs` | array of Validation Issue IDs | yes | Reviewed issues |
| `notes` | string or null | yes | Concise review note |

`approved` requires reviewer identity, review time, no unresolved blocking
issue, and full review of all non-deterministically extracted fields in that
Profile. Initial Profiles and every new or semantically changed Profile are
reviewed individually, not by sampling. An unchanged immutable revision retains
its review; run-level sampling belongs in a run report.

Human review covers capability kind, semantic roles, fuzz-input and offset
semantics, constraints, claims, side effects, determinism, evidence alignment,
and issue severity. It does not replace compile or smoke evidence.

The deterministic Builder owns identity, revision metadata, hashes,
declarations, defaults, invocation templates, source locations, direct call
dependencies, reference validation, and compile or smoke results.
Human-reviewed annotations supply semantics that deterministic extraction
cannot establish safely. An LLM may assist offline drafting, but its output is
neither evidence nor an accepted Profile input without human review.

## 12. Responsibility Boundary

This Profile must not contain API or Knowledge selection, branch priority or
budget, API-specific recommendations, Helper call order, control flow,
activation or feedback results, complete implementations, Strategy Primitives,
or Harness code.

HarnessSpec records why a capability is required and may bind it to an exact
Profile revision. Strategy Primitives record invocation order, parameter
mapping, guards, and instrumentation. Harness generation renders those
decisions into C++.
