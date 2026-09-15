# Source-to-Report Mapping v2.0

## 1. Purpose and Boundary

This document defines deterministic mapping from captured historical-bug source
artifacts to one Bug Report v2 record:

```text
Captured sources + approved curation
                  ↓
             Bug Report v2
```

It defines source admission, source-specific section mapping, evidence basis,
normalization, missing/conflicting-data handling, and dataset expansion. It does
not redefine Report fields, infer unsupported semantics, decide Report-to-Pattern
splits, or produce Pattern, Knowledge, HarnessSpec, or Harness content.

The Builder implements these rules without an LLM. Report structure is defined
by `bug_report_record.schema.json`; field semantics are defined by
`bug_report_schema.md`; later abstraction is defined by
`report_to_pattern_mapping.md`.

## 2. Supported Source Profiles

| Profile | Primary artifact | Companion artifacts |
|---|---|---|
| `dlframe_benchmark_v1` | DLFrame report text | Paired reproduction code and final human-selection row |
| `curated_github_issue_text_v1` | Locally curated GitHub Issue text, including the expanded torch.matmul captures | Optional reproduction, discussion, PR, commit, curation, or validation artifacts |

A case bundle contains one case-defining primary source and explicitly linked
companion artifacts. Companion artifacts need not share the primary source's
external ID. File or directory names may discover candidates, but semantic
claims require captured Evidence. The Builder must not guess unsupported source
layouts.

## 3. Admission and Immutability

A candidate Report is materialized only when:

1. the primary artifact exists and has a stable source namespace and case ID;
2. captured material supports at least one concrete `failure_observation`;
3. one primary API can be established from source, code, or approved curation;
4. all consumed files can be hashed and their relationships validated; and
5. the profile-specific admission decision does not explicitly exclude the case.

A concrete failure may be a crash, exception, incorrect output, timeout or hang,
memory error, or explicitly reported but unclassified failure. A risk conjecture
without reported behavior is insufficient. An unclassified reported failure uses
`unknown`; absence of failure Evidence does not create an `unknown` observation.

For the current data:

- a DLFrame row with `human_include = Yes` is admitted;
- a row with `human_include = No` is skipped and logged;
- a GitHub Issue under `github_issue_collection/excluded/` is skipped;
- the expanded `dataset/raw/exp006_matmul_reports/pytorch/torch.matmul/` capture
  has deterministic priority over a duplicate interim Issue text;
- the non-selected duplicate remains an alternate Source Artifact for traceability;
- other GitHub Issue files remain candidates until Report review approves or
  rejects them.

Materialization is not approval. A materialized candidate remains
`not_reviewed` until human review; only an `approved` Report may enter the formal
Report-to-Pattern pipeline.

Captured artifacts are immutable snapshots. Corrections or stronger evidence
are added as new artifacts and produce a new Report revision; existing artifact
content is not overwritten. An external URL without a captured local snapshot
is not a Source Artifact.

## 4. Canonicalization, Identity, and Hashing

Artifact hashes are computed from complete stored bytes, including any BOM and
original line endings. Logical text is decoded with UTF-8 BOM handling, so an
initial BOM is not part of Evidence text; CRLF or CR line endings are normalized
to LF. No spelling, whitespace, punctuation, translation, or semantic rewriting
is allowed.

Report identity is source-based:

```text
br_pytorch_dlframe_<benchmark-id>
br_pytorch_github_<issue-number>
```

`artifact_role` is a classification, not an identity. A case may contain
multiple Artifacts with the same role; every Artifact has a unique stable ID,
such as `art_reproduction_001` and `art_reproduction_002`. Stable source identity
or canonical path ordering, not filesystem discovery order, determines suffixes.

An Evidence ID identifies a logical evidence unit in one Source Artifact. A
revision that only corrects locator coordinates while retaining the same
artifact, content, kind, and meaning keeps the Evidence ID. A change to the
artifact, located content, evidence kind, or semantic unit creates a new ID.
Section names and JSON pointers provide semantic anchors; line-only evidence
uses its canonical content and occurrence to avoid dependence on line numbers.
Exact ID and hash construction remains Builder-owned and versioned.

Dates are normalized only when an explicit source value can be parsed. Missing
time zones, day values, or dates are not inferred. For a line-range Evidence
locator, canonical located content joins the inclusive normalized lines with LF
and does not add a terminal LF after the final located line.

## 5. Common Mapping Rules

### 5.1 Assertion basis

Use the Report Schema vocabularies as follows:

- `source_explicit`: captured source text directly states the assertion;
- `code_explicit`: captured code literally establishes the call, value, or
  relation;
- `curation_confirmed`: an approved human-curation artifact establishes it;
- `unknown`: the basis cannot be established.

Directory names, filenames, preliminary LLM responses, and Builder guesses are
not semantic Evidence. They may support discovery or deterministic joins only.

### 5.2 Source and Evidence separation

Each consumed file becomes one Source Artifact. Relevant sections or exact code
locations become Evidence Items. Embedded reproduction code is cited through
`source_evidence_refs`; separately stored code is retained through
`artifact_refs`.

If embedded and standalone code are identical after canonicalization, both
Source Artifacts remain captured, but one reproduction Evidence Item is
sufficient and the standalone file remains an Artifact reference. They do not
provide independent confirmation. Distinct reproduction content receives
distinct Evidence when it supports a claim. The Validator detects exact
content-equivalent copies rather than requiring a separate link field.

Directness and strength use existing Report fields rather than a new score:

- direct source text or literal code may establish a supported assertion;
- approved curation may establish admission, primary-API selection, or review,
  but does not become historical behavior, diagnosis, resolution, or oracle;
- contextual mentions may be retained as Evidence but cannot alone establish a
  strong conclusion; and
- copied, reformatted, or transcribed content does not increase support strength.

### 5.3 API scope

Explicit source statements, literal code calls, and approved curation are API
candidate sources, not an overwrite priority. Preserve every supported API and
assign `primary`, `affected`, or `mentioned` according to its evidenced role.

An approved alias mapping may normalize equivalent names. A wrapper, compiler
entry, and tested operator may remain separate assertions. If source text names
API X while code calls incompatible API Y, preserve both, record
`conflicting_sources`, and require human curation before approval. Curation may
select the primary API but must not erase contrary source or code Evidence.

Folder and filename API labels remain lookup hints only. A lookup hint may be
compared with a source-derived primary API as a consistency check, but it never
selects or proves that API. Bare terminal-name matches such as `add`, `relu`, or
`reshape` do not establish a fully qualified API. When the source-derived primary
API differs from the lookup hint, retain the source-derived API and emit a
record-level validation warning for human review.

### 5.4 Primary source

`primary_source_ref` identifies the Artifact that defines case identity and
contains the core historical Bug report. It points to the DLFrame report text or
the curated GitHub Issue text, not to curation tables, standalone reproduction,
PRs, commits, or validation logs. Exactly one primary source is selected. If a
later revision adds a stronger raw source snapshot, it may become primary while
the previous captured Artifact remains in the bundle.

## 6. Profile: `dlframe_benchmark_v1`

For case `<id>`, the expected bundle is:

```text
reports/<id>_summary_with_code.txt
reproduction_code/<id>.py
selected_bug_review_final.csv row with bug_id = <id>
```

| DLFrame material | Report mapping |
|---|---|
| Report text | Primary `benchmark_report` Artifact |
| Paired `.py` file | `source_code` Artifact with role `reproduction` |
| Numeric filename stem | Benchmark external ID, not automatically a GitHub Issue ID |
| `[Title]` | Artifact title |
| `Bug` or equivalent description | Bug-description Evidence |
| `To Reproduce` code or steps | Reproduction Evidence |
| `Expected behavior` | Expected-behavior Evidence and claim |
| Literal calls in code | API-reference Evidence with `code_explicit` basis |
| Final selection row | `curation_table` Artifact; only approved curation fields may be mapped |

The final selection row may establish inclusion and primary-API selection. Its
Pattern category, summarized trigger, Pattern/Knowledge feasibility, Harness
feasibility, confidence, reason, and review note do not become historical Bug
facts. A selected DLFrame case may use `benchmark_curated` verification, citing
the benchmark and curation Evidence.

Absent Issue metadata, root cause, fix, or environment remains absent or
unresolved according to material relevance; it is never reconstructed from the
benchmark ID or downstream Pattern data.

## 7. Profile: `curated_github_issue_text_v1`

The current text files are curated local representations of GitHub Issues, not
raw GitHub API exports. `source_kind = github_issue` identifies the upstream
source object; this Profile identifies its local capture representation. The
Artifact hash authenticates only the stored local bytes, not the live Issue or
its completeness. Issue ID is read from captured text when present; otherwise a
strict `issue_<digits>_*.txt` filename may provide deterministic case identity.
A disagreement between text and filename is an error. Filename-derived identity
does not support semantic Bug claims. Use an explicitly captured URL when
available and otherwise store `null`; do not synthesize one. Missing native
state maps to `unknown`, not `null`. The Builder run log
records the selected Profile, while Report provenance records this Mapping
document's version and hash.

The following sections are eligible for Report mapping when present:

| Source section | Report use |
|---|---|
| Issue ID, URL, title, state, creation date, author, labels | Source metadata Evidence |
| Description or reported bug | Bug-description Evidence |
| Minimal Reproduction or Reproduction | Reproduction Evidence |
| Observed Behavior, Actual Behavior, Error, or Output | Failure-observation Evidence |
| Expected Behavior | Expected-behavior Evidence |
| Environment | Environment Evidence and facts |
| Discussion | Discussion Evidence; semantic claims require an explicit statement in the located text |
| Root Cause | Root-cause claim only when traceable to an explicit source statement rather than an unattributed curator summary |
| Fix or Final Resolution | Resolution claim; fix status is evaluated separately |

The following analyst material is excluded from historical behavior, diagnosis,
resolution, and verification claims:

- human Bug category or severity annotations;
- summarized or proposed Pattern and trigger abstractions;
- Potential Fuzzing Value;
- Harness generation guidance or directions;
- related concepts and generalization suggestions;
- Pattern/Knowledge/Harness feasibility and review notes.

Excluded material may remain in a captured curation Artifact for audit. It must
not support historical trigger, behavior, oracle, diagnosis, resolution, or
verification claims. It may support only the curation decisions allowed in
Section 5.2 and must not be cited as a reporter or maintainer statement.

An Issue state of `closed` records only native workflow state. It does not set
`resolution.fix_status` to `fixed`. A mentioned PR or commit may support a
resolution claim, but `fixed` requires captured Evidence that the change was
merged or applied and addressed the reported behavior. Official confirmation or
triage requires attributable official project Evidence; otherwise the case
remains `user_reported` or uses the evidence-supported weaker status.

## 8. Behavior, Diagnosis, Resolution, and Reproduction

Behavior claims preserve the source's concrete statement and cited excerpt. The
Builder may map an explicitly named failure to the corresponding controlled
value, but it does not infer necessity, generality, risk priority, or a future
testing strategy. An explicitly reported but unclassified failure or oracle
keeps the original statement and uses the Schema's `unknown` category. Absence
of an oracle produces an empty oracle collection; it does not create a synthetic
`unknown` claim.

Root-cause and resolution claims retain attribution and support strength. A
discussion fragment with an exact locator may use `actor = null` and
`actor_role = unknown`. It supports a root-cause claim only when the text
explicitly asserts causality; a named and verified official actor is required
for `officially_confirmed`. Unattributed curator summaries do not become
historical root-cause claims. Conflicting claims are retained separately.

The presence of source reproduction code sets source availability only. A
standalone code Artifact or executable or near-executable embedded program maps
to `code_provided`; actionable narrative steps without an adequate program map
to `steps_provided`. `absent` requires a checked, supported capture with neither;
an ambiguous or unsupported representation maps to `unknown`. Project
reproduction status remains `not_attempted` unless a captured experiment log
records an independent result. A source-reported successful reproduction is not
project validation.

## 9. Curation and Non-evidence Inputs

Final human curation may determine admission, primary-API selection, and Report
review only. Every mapped curation decision must cite a captured curation
Artifact and exact row or section.

Preliminary LLM selection responses are audit material only. They are not input
Evidence for API scope, trigger, observed behavior, oracle, diagnosis,
resolution, or verification. Downstream Pattern and Knowledge records are also
forbidden as Report inputs.

## 10. Missing, Conflicting, and Duplicate Data

- Missing optional scalar data maps to `null`; missing collections map to `[]`.
- `unknown` is used only where the Report Schema permits it.
- An unsupported primary-source layout rejects materialization; an unsupported
  optional companion is omitted and recorded as unresolved when material.
- Material absent, ambiguous, conflicting, or unsupported information is
  recorded in `unresolved_information`; record defects belong to validation.
- Independent conflicting sources are preserved with separate claims and
  Evidence references.
- Independent support requires distinct upstream source identity and independent
  authorship or production. A copy, excerpt, translation, reformatted file, or
  curation derived from another Artifact is not independent. Different paths,
  filenames, authors inside one Artifact, or stored copies alone are insufficient.
- Source identity is deduplicated first by source namespace and external ID and
  then checked by content hash. Identical content is never independent support.
- A filename/code mismatch, duplicate external ID, unresolved primary source,
  or broken Evidence locator fails validation rather than being silently fixed.

## 11. Output and Versioning

The Builder processes cases in an explicit profile order and then by numeric or
lexical case ID. Discovery and construction failures are isolated per case and
retained in the run log; missing Schema or Mapping inputs remain fatal run-level
errors. The Builder emits one immutable Report revision per admitted valid case.
A rejected, skipped, or invalid case produces no canonical Report but retains its
reason in the run log. Error-level record defects remain outside canonical
`bug_reports`; valid records may retain warning-level `validation_issues`. One
case may later produce multiple Patterns, but it does not produce multiple
Reports merely because several APIs or conditions are mentioned.

Adding cases under an existing source profile does not change this mapping
version. Adding a new source profile or clarifying compatible behavior increments
the minor version; changing existing mapping semantics increments the major
version. Every Report records the mapping version and content hash used for its
generation.
