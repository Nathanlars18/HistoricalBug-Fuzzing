# Source-to-Report Mapping v5.2

## Boundary

The active Builder consumes only an `admitted` candidate from the Issue
candidate inventory and the immutable capture referenced by that entry. It is
offline, deterministic, and does not call an LLM or fetch network resources.

The candidate inventory proves how the case was discovered and admitted. It is
not copied into Report claims. Dataset annotations and GitHub search matches
remain discovery provenance unless an upstream source locator independently
supports the same fact.

## Input requirements

An input consists of:

1. one candidate inventory file conforming to Issue Protocol v0.8;
2. one admitted candidate with a non-null snapshot;
3. the referenced `capture.json`;
4. the native Issue JSON and complete or explicitly partial comments capture;
5. optional source-provided reproduction, PR, commit, patch, and dataset-origin
   artifacts declared by `capture.json`.

The Builder rejects missing files, hash mismatches, non-admitted candidates,
unresolved admission locators, and unsupported locator kinds.

## Deterministic mapping

- Repository, Issue number, URL, and source workflow state come from native
  source fields without semantic reinterpretation. Discovery timestamps,
  labels, authors, and search metadata remain in the inventory or immutable
  capture unless a Report assertion explicitly cites them; they are not copied
  merely to make the Report self-contained.
- Inventory API associations become Report API assertions only after their
  exact locators resolve. `matched_api_terms` are never mapped as assertions.
- Admission `trigger_conditions` locators become source-explicit trigger
  claims. Admission `operation_contexts` locators become source-explicit
  operation-context claims.
- Admission `erroneous_behavior` locators become source-explicit failure
  observations.
- Explicit Markdown sections named reproduction, expected behavior, versions,
  environment, root cause, cause, fix, or final resolution may be mapped to
  their matching Report fields using exact line-range Evidence. Generic
  headings such as `Explanation` do not establish a root cause. Unlabelled
  prose or code is retained as source but is not promoted by keyword guessing.
- A captured PR or commit supports a resolution only when its native content
  explicitly links it to the Issue. An explicitly linked, unmerged PR with a
  captured patch supports `fix_proposed`; `fixed` additionally requires the
  linked change to be merged and the patch to be captured. Issue or PR state
  `closed` is insufficient. A fix-section claim alone does not determine the
  resolution status.
- Issue title/body, captured comment bodies, captured PR title/body, commit
  messages, and captured patch text are indexed as neutral Evidence Items.
  Indexing makes source text addressable but does not turn it into an accepted
  trigger, diagnosis, fix, or other Report claim. Dataset curation records stay
  as provenance artifacts and are not promoted to historical behavior evidence.
- Comments become Report claims only through an exact admitted locator or an
  explicitly labelled deterministic section. The Builder does not classify
  comments by keywords; later Pattern extraction may interpret neutral Evidence
  while citing it and preserving uncertainty.
- Admission locators should select the smallest self-contained passage that
  supports one gate. They must not combine the observed failure with a
  comparison result, warning, expected result, or unrelated context merely
  because those lines are adjacent.
- Oversized excerpts are represented as `null` and recovered from their
  verified locator. Claims and environment values fail validation rather than
  being silently shortened.
- Missing facts remain empty or `unknown` and are recorded under
  `unresolved_information`; they are not inferred.
- Absence of an explicitly labelled reproduction section or separately
  captured reproduction artifact maps to `unknown`, not `not_provided`. A
  complete comment capture does not prove that unstructured Issue prose
  contains no reproduction material. `not_provided` therefore requires
  explicit negative source evidence or a separately justified exhaustive
  parser.

No Report mapping assigns Pattern symptom classes, Chen root-cause classes,
risk dimensions, fuzzing relevance, Harness guidance, or current-version
reproducibility.

## Provenance and revisions

Source artifacts use repository-relative paths and SHA-256 hashes. Repeated
registration merges non-null metadata and may not erase or conflict with
existing identity, URL, workflow-state, or capture-time values. Evidence
IDs are derived from artifact, locator, and resolved text. Report IDs are
source-based. The Report content hash excludes its own hash field.

Re-running the same candidate with the same source, mapping, and builder reuses
the latest semantic revision. Changed sources, mapping, or review create an
append-only revision with a parent reference. Existing v2-v4 Reports are
validated only against their frozen legacy Schemas and are never relabelled.

Directory validation fully checks the latest revision. Earlier revisions remain
in the active lineage and are reported as `historical_valid` when their record,
source Evidence, content hash, and parent link remain valid but a mutable
Inventory or Mapping path now contains a newer version. That dependency drift
is a warning, not record corruption. Capture, Evidence, content-hash, or lineage
failures remain errors. Formal-study Inventory files must be frozen; later
screening or mapping changes use a new versioned file rather than overwriting a
frozen input.

## Sampled quality assurance

The Builder validates every Report structurally and against its source
locators. Human review is a study-level quality audit, not a second extraction
pipeline and not a requirement for every Report. Before formal Pattern results
are inspected, freeze the audit sample size, random seed, and stratification
variables (at minimum discovery source and source format). Review the sampled
records for API relation, field placement, exact Evidence resolution, material
source omission, and resolution/disposition handling. A systematic error
requires fixing the general rule and regenerating every affected Report. An
explicitly rejected Report cannot enter Pattern extraction; `not_reviewed`
alone is not a rejection.
