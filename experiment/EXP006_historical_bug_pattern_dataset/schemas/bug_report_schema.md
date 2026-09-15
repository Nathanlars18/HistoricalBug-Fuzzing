# Historical Bug Report Schema v2.0

## 1. Purpose and Boundary

A Bug Report is the canonical, evidence-grounded representation of one selected
historical bug case before Pattern abstraction:

```text
Source artifacts → Bug Report → API-specific Pattern(s) → Knowledge
```

It preserves captured artifacts, addressable evidence, source-specific facts and
claims, API scope, verification, unresolved information, and provenance. It does
not infer unsupported facts, determine Pattern splits, generate testing advice,
or contain Harness information. Issue closure is not proof of a fix, and supplied
reproduction code is not proof of independent reproduction.

Responsibilities are separated as follows:

| Concern | Owner |
|---|---|
| Report field semantics and vocabularies | `bug_report_schema.md` |
| Machine structure and format constraints | `bug_report_record.schema.json` |
| Benchmark/GitHub mapping and text canonicalization | `source_to_report_mapping.md` |
| IDs, normalization, hashes, references, and validation | `build_bug_report_json.py` |
| Report-to-Pattern abstraction and split decisions | `report_to_pattern_mapping.md` |

The Report Builder is deterministic and does not call an LLM.

## 2. Record Model and Pattern Bridge

One Report represents one selected bug case and may bundle an Issue or benchmark
record with comments, reproduction code, PRs, commits, curation records, and
project validation logs. Report identity is source-based; Pattern identity and
storage remain API-based.

A Report may support one or more Patterns. Every derived Pattern must retain the
Report ID, revision number, Report content hash, and cited Evidence IDs. Detailed
split rules remain in `report_to_pattern_mapping.md`.

## 3. Top-level Fields

| Field | Type | Purpose |
|---|---|---|
| `schema_version` | string | Report schema version; `2.0` for this design. |
| `identity` | object | Stable Report identity. |
| `revision_information` | object | Immutable revision lineage and reason. |
| `source_bundle` | object | Captured source artifacts. |
| `evidence_items` | array | Addressable source excerpts or locations. |
| `scope_assertions` | object | Evidence-backed API and component scope. |
| `reported_behavior` | object | Historical trigger, behavior, oracle, environment, and reproduction. |
| `reported_diagnosis` | object | Source-reported root-cause claims. |
| `resolution` | object | Historical fix claims and artifacts. |
| `verification` | object | Source-side acknowledgement or curation status. |
| `unresolved_information` | array | Material missing, ambiguous, or conflicting information. |
| `provenance` | object | Builder-owned generation provenance. |
| `review` | object | Machine validation and human review. |

All top-level fields are required. Unknown top-level fields are forbidden.

## 4. Common Conventions

### 4.1 Empty and Unknown Values

- Required strings are non-empty.
- An unavailable optional scalar uses `null`; an empty collection uses `[]`.
- `unknown` is used only where explicitly allowed by an enum.
- Missing information is never replaced by a placeholder or unsupported guess.

### 4.2 Assertion Basis

Every semantic assertion records one `assertion_basis`:

| Value | Meaning |
|---|---|
| `source_explicit` | Captured natural-language evidence states it directly. |
| `code_explicit` | A literal call, value, or relation is visible in captured code. |
| `curation_confirmed` | An approved human curation artifact establishes it. |
| `unknown` | Its basis cannot be established. |

Parsing an ID, normalizing text or time, and computing a hash are deterministic
transformations, not evidence bases; they are traced through Builder and Mapping
provenance. They cannot justify an affected API, trigger, root cause, or fix.

### 4.3 References and Hashes

Content hashes use `sha256:<64 lowercase hexadecimal characters>`. Local paths
are repository-relative. Artifact and Evidence references resolve inside the
same Report unless explicitly defined as versioned external references.

## 5. Identity and Revision Information

### 5.1 `identity`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `report_id` | string | yes | Stable, globally unique, source-based ID. |
| `framework` | string | yes | Framework represented by the case. |

Recommended form: `br_<framework>_<source>_<external-id-or-stable-hash>`.
The ID must not contain an API name or mutable title.

### 5.2 `revision_information`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `revision_number` | positive integer | yes | Immutable number beginning at 1. |
| `parent_revision_ref` | object or null | yes | Immediate previous revision of the same Report. |
| `revision_trigger` | enum | yes | Primary reason for creating this revision. |
| `change_summary` | string | yes | Concrete changes in this revision. |

Allowed triggers are `initial_generation`, `source_updated`, `mapping_updated`,
`builder_updated`, `data_corrected`, `review_updated`, and
`reproduction_updated`.

Revision 1 uses `initial_generation` and a null parent. A later parent reference
contains `report_id`, `revision_number`, and `content_hash`. Secondary reasons go
in `change_summary`. There is no lifecycle field; validation and review determine
usability. A review change creates a new revision.

## 6. Source Bundle

`source_bundle` contains `primary_source_ref` and `source_artifacts`.
`primary_source_ref` identifies one artifact; `source_artifacts` contains at
least one captured local artifact.

Each Source Artifact contains:

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `artifact_id` | string | yes | ID unique within this Report. |
| `artifact_role` | enum | yes | Function in the bug case. |
| `source_kind` | enum | yes | Technical source form. |
| `repository` | string or null | yes | Repository or benchmark namespace. |
| `external_id` | string or null | yes | Issue, PR, commit, or benchmark ID. |
| `url` | string or null | yes | Canonical external URL when known. |
| `local_path` | string | yes | Immutable repository-relative snapshot path. |
| `title` | string or null | yes | Source-provided title. |
| `source_native_state` | enum or null | yes | Native Issue/PR workflow state. |
| `source_created_at` | timestamp or null | yes | Creation time reported by the source. |
| `captured_at` | timestamp or null | yes | Local snapshot time. |
| `content_hash` | string | yes | SHA-256 of the complete local artifact. |

Artifact roles: `report`, `reproduction`, `discussion`, `resolution`, `curation`,
`validation_log`, `other`.

Source kinds: `github_issue`, `github_pull_request`, `git_commit`,
`benchmark_report`, `source_code`, `experiment_log`, `curation_table`, `other`.

`source_native_state` is `open`, `closed`, `merged`, `unknown`, or `null`.
`closed` and `merged` describe only the source object and do not establish a fix.
`unknown` means that the source kind has a native workflow state but it was not
captured or cannot be established; `null` means that the source kind has no such
state. Snapshot availability is established by `local_path` and `content_hash`.
An uncaptured URL is unresolved information, not a Source Artifact.

## 7. Evidence Items

An Evidence Item addresses source material without interpreting it.

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `evidence_id` | string | yes | ID unique within this Report. |
| `source_artifact_ref` | string | yes | Artifact containing the evidence. |
| `evidence_kind` | enum | yes | Kind of source content. |
| `locator` | object | yes | Exact location in the artifact. |
| `excerpt` | string or null | yes | Canonicalized source excerpt when embedded. |
| `attribution` | object | yes | Author identity and role. |
| `content_hash` | string | yes | Hash of the excerpt or exact located content. |

Evidence kinds: `source_metadata`, `api_reference`, `bug_description`,
`trigger_description`, `reproduction`, `observed_output`, `expected_behavior`,
`environment`, `discussion`, `root_cause_claim`, `fix_claim`, `other`.

Allowed locator forms are:

```json
{"locator_type": "line_range", "start_line": 20, "end_line": 43}
{"locator_type": "json_pointer", "value": "/comments/3/body"}
{"locator_type": "section", "value": "Reproduction"}
{"locator_type": "whole_artifact"}
```

Lines are one-based and inclusive; JSON pointers follow RFC 6901; a section
names a stable source heading or key. The JSON Schema defines the corresponding
discriminated structures, and the Validator checks ranges and resolution.

`excerpt` is null or 1–2,000 Unicode characters. Longer relevant content is split
by semantic unit or retained as a referenced artifact; it is never silently
truncated. A null excerpt requires a locator that resolves to loadable content.
Text canonicalization is versioned in `source_to_report_mapping.md`; the minimum
policy is UTF-8 with CRLF normalized to LF and no other rewriting.

A Source Artifact hash is computed from the complete stored file bytes. An
Evidence hash is computed from the UTF-8 bytes of the exact stored excerpt after
canonicalization; when `excerpt` is null, it is computed from the exact content
resolved by the locator. JSON quoting, IDs, locators, and other record fields are
not part of the Evidence hash input. Binary located content uses its raw bytes.

`attribution` contains nullable `actor` and `actor_role`. Roles are `reporter`,
`maintainer`, `benchmark_author`, `curator`, `system`, and `unknown`.
`source_kind` describes the container; `actor_role` describes its author.

## 8. Scope Assertions

`scope_assertions` contains `api_assertions` and `component_assertions`.

Each API Assertion contains `assertion_id`, `api_name`, `relation`,
`assertion_basis`, and `evidence_refs`. Relation is `primary`, `affected`, or
`mentioned`. An approved Report has exactly one primary assertion. `primary` and
`affected` APIs may become Pattern candidates; `mentioned` is context only.

Each Component Assertion contains `assertion_id`, `component_kind`,
`component_name`, `assertion_basis`, and `evidence_refs`. Component kind is
`operator`, `module`, `backend`, `compiler_component`, or `other`. API names
belong only in API Assertions. Alias normalization requires explicit source or an
approved versioned mapping.

## 9. Reported Behavior

`reported_behavior` contains `trigger_claims`, `operation_contexts`,
`failure_observations`, `expected_behavior_claims`, `historical_oracle_claims`,
`environment_facts`, and `reproduction`.

### 9.1 Claims and Facts

| Collection | Item fields |
|---|---|
| `trigger_claims` | `claim_id`, `dimension`, `subject`, `predicate`, `assertion_basis`, `evidence_refs` |
| `operation_contexts` | `context_id`, `statement`, `assertion_basis`, `evidence_refs` |
| `expected_behavior_claims` | `claim_id`, `statement`, `assertion_basis`, `evidence_refs` |
| `failure_observations` | `observation_id`, `failure_type`, `statement`, `assertion_basis`, `evidence_refs` |
| `historical_oracle_claims` | `claim_id`, `oracle_kind`, `statement`, `assertion_basis`, `evidence_refs` |
| `environment_facts` | `fact_id`, `property`, `value`, `assertion_basis`, `evidence_refs` |

Trigger dimensions are `shape`, `dtype`, `value`, `device`, `backend`, `layout`,
`memory`, `aliasing`, `output_tensor`, `state`, `execution`, `graph`,
`concurrency`, `api_contract`, `unknown`, and `other`. Necessity and abstraction
belong to Pattern extraction.

Failure types remain aligned with the Pattern layer:

| Value | Meaning |
|---|---|
| `crash` | Abnormal process termination, such as a fatal signal or abort. |
| `exception` | A language or framework exception without independently established abnormal termination. |
| `incorrect_output` | Execution completes with an incorrect value, shape, dtype, gradient, or result. |
| `timeout_hang` | Execution exceeds a defined timeout or makes no progress. |
| `memory_error` | The primary observation is OOM, allocation failure, leak, corruption, or a memory diagnostic. |
| `unknown` | A failure is reported but its observable category is unclear. |

One event may produce multiple observations, such as `memory_error` and `crash`.
The Builder does not infer an unreported category.

Historical oracle kinds are `signal`, `exception_class`,
`differential_reference`, `output_property`, `timeout`, `sanitizer`, and
`unknown`. They record historical detection only, not a proposed future oracle.

### 9.2 Reproduction

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `availability` | enum | yes | Whether source code or steps are present. |
| `source_evidence_refs` | array | yes | Evidence IDs for code or steps embedded in a source artifact. |
| `artifact_refs` | array | yes | Independently stored reproduction Artifact IDs. |
| `validation_status` | enum | yes | Independent project reproduction result. |
| `validation_evidence_refs` | array | yes | Evidence from project validation. |

Availability describes only what the historical source provides:

- `code_provided`: executable or near-executable reproduction code is present;
- `steps_provided`: actionable narrative steps or commands are present, but no
  adequate reproduction program is available;
- `absent`: captured sources were checked and contain neither code nor actionable
  steps;
- `unknown`: missing, inaccessible, unsupported, or ambiguous source material
  prevents classification.

When both code and steps exist, use `code_provided`. Embedded material uses
`source_evidence_refs`; standalone reproducer files use `artifact_refs`.
Validation status independently records the project result as `reproduced`,
`not_reproduced`, or `not_attempted`. Project validation evidence resolves to an
`experiment_log` artifact.

## 10. Diagnosis, Resolution, and Verification

### 10.1 `reported_diagnosis`

Each `root_cause_claims` item contains `claim_id`, `mechanism_layer`,
`statement`, `support_status`, `assertion_basis`, and `evidence_refs`.
Mechanism layers remain aligned with the Pattern layer: `api`, `aten`, `kernel`,
`backend`, `numerical`, and `unknown`.

Support status is:

| Value | Meaning |
|---|---|
| `reported` | One captured source states the claim. |
| `corroborated` | Independent captured sources support the same claim. |
| `officially_confirmed` | Official maintainer or project evidence explicitly confirms it. |
| `disputed` | Captured sources explicitly disagree with it. |
| `unknown` | Support strength cannot be established. |

`assertion_basis` records how content entered the Report, Evidence attribution
records who stated it, and `support_status` records support strength. A
`corroborated` claim cites at least two Evidence Items; the Validator additionally
requires those items to resolve to at least two independent Source Artifacts.

### 10.2 `resolution`

`resolution` contains `fix_status`, `resolution_claims`, and
`fix_artifact_refs`. `fix_status` contains `value`, `assertion_basis`, and
`evidence_refs`; value is `fixed`, `unfixed`, or `unknown`. Each resolution claim
contains `claim_id`, `statement`, `assertion_basis`, and `evidence_refs`.
Issue closure, a linked PR, or a commit mention alone does not establish `fixed`.

### 10.3 `verification`

`case_verification_status` contains `value`, `assertion_basis`, and
`evidence_refs`. Value is `official_confirmed`, `official_triaged`,
`benchmark_curated`, `user_reported`, or `unknown`.

This describes acknowledgement or curation of the bug case, not the truth of
every claim. It is distinct from project reproduction and human review. Report
completeness is derived from actual fields and unresolved items; no separate
`source_completeness` label is stored.

## 11. Unresolved Information

Each item contains `unresolved_id`, `field_path`, `description`, `reason`, and
`evidence_refs`. `field_path` is a slash-prefixed path into the current Report,
such as `/resolution/fix_status`. Reasons are `missing_source`, `not_collected`,
`ambiguous_source`, `conflicting_sources`, `unsupported_format`, and `other`.
Evidence references may be empty only when no captured evidence can identify the
missing material. Guessed values are forbidden.

`unresolved_information` records limitations in the historical sources and may
remain in an approved Report. It does not record defects in the structured
record itself; those belong to `review.validation_issues`.

## 12. Provenance and Review

### 12.1 `provenance`

Builder-owned fields are `generation_method`, `builder_ref`,
`generation_run_id`, `input_artifact_refs`, `mapping_ref`, `generated_at`, and
`content_hash`. Generation method is fixed as
`deterministic_source_mapping`. `builder_ref` and `mapping_ref` contain artifact
name, version, and content hash; `input_artifact_refs` lists artifacts consumed
in the run. No model field exists. Human decisions enter through captured
curation artifacts and are still mapped deterministically. Future LLM-assisted
Report extraction requires a new Schema version rather than another v2 method.
The Report hash is computed over the canonical record with its own hash cleared.

### 12.2 `review`

Review fields are `validation_status`, `validation_issues`,
`human_review_status`, `reviewer`, `reviewed_at`, and `review_notes`.
Validation status is `passed` or `failed`. A Validation Issue contains
`issue_id`, `field_path`, `severity`, and `message`; severity is `error` or
`warning`. It records a referential, hash, filesystem, or semantic consistency
problem in a structurally valid Report. A record that fails JSON Schema is not a
formal Report and its errors belong to the Builder run log.

Historical-source gaps belong to `unresolved_information`, not
`validation_issues`. Human review status is `not_reviewed`, `approved`,
`needs_revision`, or
`rejected`. Approval requires reviewer and timestamp. Validation checks structure
and consistency; human review checks faithfulness to captured evidence.

## 13. Semantic Invariants

1. Revision 1 has no parent; later revisions reference the immediate prior revision.
2. A canonical Report contains at least one Source Artifact and Evidence Item.
3. `primary_source_ref` and every Artifact or Evidence reference resolve.
4. IDs are unique within their Report namespaces.
5. An approved Report has exactly one primary API Assertion, passed validation, and no error-level Validation Issue.
6. Non-unknown fix and case-verification statuses cite Evidence.
7. Source reproduction Evidence references have evidence kind `reproduction`.
8. A reproduction result other than `not_attempted` cites validation evidence from an experiment log.
9. Reproduction Artifact references have role `reproduction`.
10. Non-unknown semantic assertions cite Evidence and use a non-unknown assertion basis.
11. Empty strings and unrecognized fields are rejected.

Structural constraints belong to `bug_report_record.schema.json`. Referential,
hash, filesystem, lineage, and semantic checks belong to the Builder Validator.

## 14. Versioning and Legacy

Version 2.0 replaces the v1 layout with source-based identity, immutable
revisions, artifact hashes, addressable Evidence Items, explicit assertion
basis, and structured verification and review. Legacy records remain read-only
and are regenerated from preserved sources rather than silently upgraded.
