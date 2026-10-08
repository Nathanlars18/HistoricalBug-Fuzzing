# API Profile Human Review Rules v1.0

## 1. Purpose

Human review checks whether an API Profile faithfully represents its cited,
version-pinned sources and deterministic validation results. It is not a channel
for adding historical-Bug knowledge, improving experimental outcomes, or editing
generated JSON by hand.

## 2. Reviewer boundary

The reviewer may assign `approved` or `needs_revision` and cite existing
Validation Issue IDs. The reviewer must not directly change Profile facts,
mapping results, readiness states, validation logs, content hashes, or revision
lineage. Corrections are made in evidence inputs, deterministic rules, or the
Builder and then materialized as a new revision.

Knowledge records, historical reproducer inputs, generated HarnessSpecs, fuzzing
results, and desired experimental outcomes are prohibited review evidence for an
API contract assertion or ordinary-valid smoke case.

## 3. Required checks

- **AP-01 Target identity:** framework version, commit, backend, Python API,
  callable variant, binding kind, and overload identify the intended target.
- **AP-02 Source fidelity:** every asserted fact resolves to the cited source,
  revision, locator, and hash where available; an excerpt does not contradict its
  source.
- **AP-03 Python contract:** parameter names, order, kinds, requiredness,
  defaults, annotations, and return annotation match the Python-facing source.
- **AP-04 Coverage honesty:** missing or uncollected domains, exceptions,
  constraints, and effects use an explicit incomplete coverage state; empty
  arrays are not presented as exhaustive without review evidence.
- **AP-05 Binding evidence:** an ATen binding is supported by the selected
  operator schema and, for wrappers, wrapper-source evidence. Leaf-name equality
  alone is insufficient.
- **AP-06 Mapping completeness:** every Python parameter has one disposition,
  every ATen binding parameter has one mapping, and every binding return is
  resolved to the documented Python return position. Renames, conversions, and
  conditional multi-parameter mappings reproduce the complete cited wrapper
  expression; no positional guess or single-branch approximation is accepted.
- **AP-07 Validation separation:** compile, smoke, reachability, adapter, and
  failure states agree with preserved diagnostics. Runtime success is not used as
  documentation evidence.
- **AP-08 Validation-case neutrality:** a custom ordinary-valid case is fixed by
  official API evidence, contains no Knowledge references, and does not encode a
  historical trigger or desired bug outcome.
- **AP-09 Review independence:** machine promotion leaves the record unreviewed;
  the human decision is recorded by a separate operation and revision.
- **AP-10 Downstream eligibility:** approval means evidence fidelity only.
  HarnessSpec eligibility additionally requires a resolved route,
  `validation_status = passed`, and `execution_readiness = ready`.

## 4. Decisions

Use `needs_revision` for a wrong or mismatched source, missing Python parameter,
guessed binding, unsupported conversion, false completeness claim, inconsistent
validation state, or outcome-directed validation case.

Use `approved` only when all asserted facts and mappings are supported and all
known limitations are represented explicitly. Approval does not claim that the
Profile is exhaustive, that fuzzing will be effective, or that a historical bug
will be reproduced.
