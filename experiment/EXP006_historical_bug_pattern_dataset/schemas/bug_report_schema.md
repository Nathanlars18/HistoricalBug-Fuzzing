# Historical Bug Report Schema v5.1

## Purpose

A Report is the canonical, evidence-linked representation of what one admitted
historical Issue and its captured upstream material explicitly report. It is
the factual boundary between Issue selection and Pattern abstraction.

Report construction is deterministic and offline. It does not call an LLM,
classify a defect, infer a root cause, select a fuzzing strategy, or claim that
historical behavior persists in the current PyTorch build.

## Ownership

- The Issue layer owns discovery, immutable capture, deduplication, admission,
  and the candidate inventory.
- Report owns exact source-to-field mapping, Evidence IDs, explicit API
  relations, unresolved source information, and source-side disposition.
- Pattern owns API-specific semantic abstraction and optional symptom/root-cause
  classification. Its `target_api` is selected deterministically from a Report
  assertion whose relation is `affected`; cross-API transfer is outside Report
  and Pattern scope.

One admitted case normally creates one Report. A Report may contain several
`affected` APIs and does not force one of them to be primary.

## Required content

The top-level fields are:

- `identity`: repository, Issue number, canonical URL, and source-derived ID.
- `revision_information`: append-only Report revision lineage.
- `source_bundle`: exact inventory and immutable source-artifact references,
  including comment-capture completeness.
- `evidence_items`: addressable excerpts resolved from captured artifacts.
- `scope_assertions`: evidence-backed `affected` or `mentioned` APIs.
- `reported_behavior`: source-reported triggers, operations, failures,
  expectations, historical oracles, environment facts, and reproduction.
- `reported_diagnosis`: optional source-reported root-cause statements.
- `resolution`: optional source-reported fix information.
- `upstream_disposition`: what upstream evidence establishes about the case.
- `unresolved_information`: missing, ambiguous, conflicting, or uncollected
  information; absence is never filled from plausibility.
- `provenance`: deterministic builder and input bindings.
- `review`: structural/semantic validation and optional human review state.

## Evidence and assertions

Every nontrivial assertion cites one or more Evidence IDs. Evidence resolves to
an immutable source artifact using either a JSON pointer or a line range inside
a JSON string. Excerpts are convenience copies; hashes and locators remain the
authority. A resolved value longer than the excerpt limit uses `null` rather
than a silently truncated excerpt. Claim text and environment values are never
silently truncated.

Allowed assertion bases are deliberately narrow:

- `source_explicit`: stated in Issue, comment, or other prose evidence;
- `code_explicit`: visible directly in captured reproduction code;
- `patch_explicit`: visible directly in a captured patch or merged fix record.

Human approval is not an assertion basis and does not create source evidence.

The Builder also indexes a neutral evidence pool from captured upstream text:
Issue title/body, comment bodies, PR title/body, commit messages, and patches.
An indexed item is merely addressable source material. Unless a Report field
explicitly cites it, it is not an accepted Report claim. Curation tables and
search metadata are provenance, not historical behavioral evidence.

## API scope

`scope_assertions.api_assertions[].relation` is either:

- `affected`: evidence explicitly associates the reported defect with the API;
- `mentioned`: the API occurs as setup, comparison, oracle, or context only.

Search terms, dataset labels, filename text, API-family similarity, and wrapper
relationships do not by themselves establish `affected`. Pattern extraction
runs separately for each supported affected API.

## Optional facts and unresolved state

A valid Report may have no root-cause claim, fix claim, expected behavior, or
historical oracle. These are represented by empty arrays or `unknown`, plus an
`unresolved_information` entry when the absence matters. They are never made
mandatory merely to improve downstream completeness.

Failure to recognize an explicitly labelled reproduction does not establish
that none was provided. The deterministic Builder records `unknown` and an
unresolved item. `not_provided` is reserved for an explicitly supported absence
judgment.

`source_native_state` preserves a captured Issue, PR, or commit workflow state
without interpreting `closed` as fixed. `comments_capture_status` records
capture coverage; it does not by itself prove that a semantic fact is absent.

`upstream_disposition.status` distinguishes `reported`, `triaged_as_bug`,
`confirmed_bug`, `disputed`, `expected_behavior`, and `unknown`. GitHub `closed`
alone does not select any of these except that the Issue was reported.

## Validation boundary

JSON Schema validates local shape, enums, and conditional requirements.
Builder validation additionally checks source paths and hashes, locator
resolution and hashes, exact excerpts, Evidence and fix-artifact references,
duplicate IDs, revision lineage, input/mapping references, and Report content
hashes.

A valid Report requires the Issue-layer admission gates to provide at least one
affected API, one failure observation, and at least one trigger or operation
context. Human review is optional for routine records. A predeclared stratified
sample audits API relation, field placement, Evidence exactness, material
omission, and resolution handling. Explicit rejection blocks Pattern input;
`not_reviewed` does not. Review never changes cited source facts.

The active machine Schema is `bug_report_record_v5_1.schema.json`. The v5.0
Schema remains at `bug_report_record.schema.json` so existing calibration
records remain independently valid. Report v4 and earlier contracts and their
model-assisted builder are preserved under `schemas/legacy/` and
`scripts/legacy/`; they are not active inputs for v5.1 construction.
