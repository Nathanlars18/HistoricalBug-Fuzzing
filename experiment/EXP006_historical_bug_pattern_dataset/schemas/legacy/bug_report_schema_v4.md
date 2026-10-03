# Historical Bug Report Schema v4.0

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
| Historical-case selection and original-source preservation | `dataset/issue_source_protocol.md` |
| Report field semantics and vocabularies | `bug_report_schema.md` |
| Machine structure and format constraints | `bug_report_record.schema.json` |
| Benchmark/GitHub mapping and text canonicalization | `source_to_report_mapping.md` |
| IDs, normalization, hashes, references, and validation | `build_bug_report_json.py` |
| Report-to-Pattern abstraction and split decisions | `report_to_pattern_mapping.md` |

The Builder uses rules first and optional evidence-constrained LLM
extraction for unresolved material. The LLM proposes source-grounded statements;
it does not author source facts, classify defect mechanisms, or approve Reports.
Historical-case admission is not Report approval. Report construction and review
check faithful representation; CPU feasibility and per-API case-count thresholds
belong to later experiment selection. Missing optional diagnosis, reproduction
code, or fix evidence does not disqualify an otherwise supported Report.

Implementation status: the machine Schema, Builder, extraction Prompt, and
Pattern consumer support v4 candidates and source-bound human review. Frozen v2
and v3 machine Schemas validate existing records without rewriting them. Offline
fixtures check implementation contracts, not semantic accuracy or completeness
on real Issues. Mapping owns extraction and call controls; this document owns
record semantics and approval.

## 2. Record Model and Pattern Bridge

One Report represents one selected bug case and may bundle an Issue or benchmark
record with comments, reproduction code, PRs, commits, curation records, and
project validation logs. Report identity is source-based; Pattern identity and
storage remain API-based.
For new upstream Issue captures, multiple datasets or affected APIs do not create
multiple Reports for the same Issue. Original dataset entries remain attributed
discovery sources; their labels do not become upstream facts by being imported.

A Report may support one or more Patterns. Every derived Pattern must retain the
Report ID, revision number, Report content hash, and cited Evidence IDs. Detailed
split rules remain in `report_to_pattern_mapping.md`.

## 3. Top-level Fields

| Field | Type | Purpose |
|---|---|---|
| `schema_version` | string | Report schema version; `4.0` for this design. |
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

Presence of a field does not require a known value. Formal downstream use
requires traceable sources, an evidenced affected API, basic operation/input/
environment context, and a concrete reported abnormal observation. Context may
be supported by operation descriptions, trigger claims, or reproduction evidence;
an arbitrary environment value or the mere presence of code is not sufficient.
`trigger_claims` need not be non-empty. Exact trigger boundaries, root cause,
expected behavior, historical oracle, code, and fix information are optional,
but relevant available statements must not be silently ignored. Missing minimum
information blocks approval, not preservation of the captured source bundle.

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
`assertion_basis` describes evidence, not the extraction tool. An LLM-extracted
statement still needs a source/code basis; model output is never an evidence
basis. Human acceptance does not turn a guess into a source-explicit fact.

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
`captured_at` comes from collection metadata, not Report generation time or file
modification time. Comment identities and upstream update times remain in the
captured source metadata. Material capture gaps are recorded through
`unresolved_information`; a local hash proves byte identity, not completeness.

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
{"locator_type": "json_string_line_range", "value": "/body", "start_line": 8, "end_line": 15}
{"locator_type": "section", "value": "Reproduction"}
{"locator_type": "whole_artifact"}
```

Lines are one-based and inclusive; JSON pointers follow RFC 6901.
`json_string_line_range` first resolves a JSON string using its pointer, then
locates an inclusive line range inside that decoded string. A section names a
stable source heading or key. The JSON Schema defines the corresponding
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
`primary` is an organizational choice among evidenced affected APIs, not a claim
that no other API is affected. Search queries, directory names, and dataset
labels are lookup hints only. A literal call proves use, not defect attribution.
Ambiguous attribution requires review rather than promoting a mention.

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
| `trigger_claims` | `claim_id`, `statement`, `assertion_basis`, `evidence_refs` |
| `operation_contexts` | `context_id`, `statement`, `assertion_basis`, `evidence_refs` |
| `expected_behavior_claims` | `claim_id`, `statement`, `assertion_basis`, `evidence_refs` |
| `failure_observations` | `observation_id`, `statement`, `assertion_basis`, `evidence_refs` |
| `historical_oracle_claims` | `claim_id`, `statement`, `assertion_basis`, `evidence_refs` |
| `environment_facts` | `fact_id`, `property`, `value`, `assertion_basis`, `evidence_refs` |

Each collection preserves an exact source statement and its Evidence. Report
does not assign trigger dimensions, symptom categories, process-outcome classes,
or oracle kinds. For example, `Floating point exception (core dumped)` remains
that exact observation; Pattern may later classify it with an evidence-backed
taxonomy. Concrete values appearing only in a reproducer remain reproduction
evidence and do not automatically become trigger claims. A trigger claim exists
only when the source explicitly relates a condition to the reported behavior.

Actual behavior, expected behavior, and historical detection method are distinct.
The same quoted passage may support more than one role only when it explicitly
states each proposition; a failure message alone does not establish how the
reporter decided that the behavior was wrong.

### 9.2 Reproduction

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `availability` | enum | yes | Whether source code or steps are present. |
| `source_evidence_refs` | array | yes | Evidence IDs for code or steps embedded in a source artifact. |
| `artifact_refs` | array | yes | Independently stored reproduction Artifact IDs. |
| `validation_status` | enum | yes | Independent project reproduction result. |
| `validation_evidence_refs` | array | yes | Evidence from project validation. |

Availability describes only what the historical source provides:

- `code_provided`: a source explicitly presents executable or near-executable
  code as reproduction material;
- `steps_provided`: actionable narrative steps or commands are present, but no
  adequate reproduction program is available;
- `absent`: complete captured sources were checked and explicitly contain neither
  reproduction code nor actionable steps;
- `unknown`: missing, inaccessible, unsupported, or ambiguous source material
  prevents classification.

When both code and steps exist, use `code_provided`. A generic example or fenced
code block is not reproduction material without source context establishing that
role. Embedded material uses
`source_evidence_refs`; standalone reproducer files use `artifact_refs`.
Validation status independently records the project result as `reproduced`,
`not_reproduced`, or `not_attempted`. Project validation evidence resolves to an
`experiment_log` artifact.

## 10. Diagnosis, Resolution, and Verification

### 10.1 `reported_diagnosis`

Each `root_cause_claims` item contains `claim_id`,
`statement`, `support_status`, `assertion_basis`, and `evidence_refs`.
The v2 `mechanism_layer` enum is removed in v3: it mixed implementation location
and mechanism character. Preserve explicit locations in the statement, source
references, or applicable component assertions. Root-cause classification is
Pattern-owned. Keep speculation, negation, author attribution, and disagreement
in the statement and evidence; `reported` does not mean proven. No explanation
in the sources permits `root_cause_claims: []`, not a guessed mechanism.

Support status is:

| Value | Meaning |
|---|---|
| `reported` | One captured source states the claim. |
| `corroborated` | Independent captured sources support the same claim. |
| `officially_confirmed` | Official maintainer or project evidence explicitly confirms it. |
| `disputed` | Captured sources explicitly disagree with it. |
| `unknown` | Support strength cannot be established. |

`assertion_basis` records the supporting evidence basis, Evidence attribution
records who stated it, and `support_status` records support strength. A
`corroborated` claim cites at least two Evidence Items; the Validator additionally
requires those items to resolve to at least two independent Source Artifacts.

### 10.2 `resolution`

`resolution` contains `fix_status`, `resolution_claims`, and
`fix_artifact_refs`. `fix_status` contains `value`, `assertion_basis`, and
`evidence_refs`; value is `fixed`, `unfixed`, or `unknown`. Each resolution claim
contains `claim_id`, `statement`, `assertion_basis`, and `evidence_refs`.
Issue closure, a linked PR, or a commit mention alone does not establish `fixed`.
Likewise, missing fix evidence does not establish `unfixed`. Distinguish a
workaround, a proposed change, a merged fix, and an evidenced fixed release in
the source statements; do not derive a cause merely from a patch.

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

`unresolved_information` records material source, collection, or mapping
limitations. Available but not-yet-mapped content must be distinguished from
source absence; an empty collection alone proves neither. Use the existing
reason vocabulary with a precise description and source references, rather than
inventing a semantic claim. Such items may remain in an approved Report only
when they do not compromise the claims being approved. Defects in the structured
record itself belong to `review.validation_issues`.

## 12. Provenance and Review

### 12.1 `provenance`

Builder-owned fields are `generation_method`, `builder_ref`,
`generation_run_id`, `input_artifact_refs`, `mapping_ref`, `generated_at`, and
`content_hash`, plus `extraction_run_ref`. Generation method is
`deterministic_source_mapping` when only rules were used, or
`llm_assisted_source_mapping` when an LLM was consulted or an LLM-derived
candidate was reused, even if none of its candidates were accepted.
`builder_ref` and `mapping_ref` contain artifact
name, version, and content hash; `input_artifact_refs` lists artifacts consumed
as historical/curation inputs, not model responses. `extraction_run_ref` contains
`local_path` and `content_hash` for an immutable processing log for this Report's
extraction, including rule-only runs. It records processed and uncovered source
units, call reasons, input hashes, model/configuration and Prompt identity,
attempts or verified reuse, response references, and candidate dispositions.
Mapping defines the operational requirements; model responses are audit data,
never historical Evidence. Human review remains separately attributable.

Keep large payloads in referenced, hashed files instead of duplicating them in
the Report. Exclude credentials from logs. Finalize the extraction log before
hashing the Report; it must not contain the final Report hash, avoiding a hash
cycle. The Report hash is computed with its own hash cleared.

### 12.2 `review`

Review fields are `validation_status`, `validation_issues`,
`human_review_status`, `reviewer`, `reviewed_at`, and `review_notes`.
Validation status is `passed` or `failed`. A Validation Issue contains
`issue_id`, `field_path`, `severity`, and `message`; severity is `error` or
`warning`. It records a referential, hash, filesystem, or semantic consistency
problem in a structurally valid Report. A record that fails JSON Schema is not a
formal Report and its errors belong to the Builder run log.

Source, collection, and unmapped-content gaps belong to `unresolved_information`, not
`validation_issues`. Human review status is `not_reviewed`, `approved`,
`needs_revision`, or
`rejected`. Approval requires reviewer and timestamp. Validation checks structure
and consistency; human review checks faithfulness to captured evidence.
Source admission does not supply a Report reviewer or approve its mapping.
For the v4 workflow, the LLM may locate exact source spans but cannot assign
primary API, trigger dimensions, symptom categories, oracle kinds, fix status,
or confirmation strength. Every proposed span still requires human verification
against its surrounding context before approval. Review must also
consider omitted contradictory evidence and ambiguous rule-derived statements.
Initial calibration checks all extracted statements in a small set of cases;
later sampling of other content must declare scope and escalation rules. A
sampled batch is not a batch of individually approved Reports. `review_notes`
records the review scope and remaining limitations; machine checks cannot prove
semantic entailment or extraction completeness.

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
12. Approval requires the minimum information in Section 4.1 and no unresolved
    ambiguity that invalidates the supported API, context, or abnormal behavior.
13. LLM candidates cannot assign identities, hashes, review status, or approval;
    accepted statements cite captured sources, not the extraction response.

Structural constraints belong to `bug_report_record.schema.json`. Referential,
hash, filesystem, lineage, and semantic checks belong to the Builder Validator.

## 14. Versioning and Legacy

Version 4.0 narrows assisted extraction to verbatim source spans and removes
Report-owned trigger, symptom, and historical-oracle classification. Version
3.0 introduced assisted extraction and removed `mechanism_layer`; frozen v2 and
v3 Schemas remain under `schemas/legacy`. Do not relabel existing records or edit
their hashes in place. Re-extraction uses
preserved sources and an explicit new revision; readers must validate each
version with its matching Schema. Pattern checks the latest revision, approval,
lineage, and source hashes before providing resolved Evidence text to the model.
Real-case extraction and human-review calibration remain necessary before batch
use; a version migration alone is not evidence of research validity.
