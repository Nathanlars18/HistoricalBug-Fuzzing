# Historical Bug Knowledge Schema v3.0

Input contract: one API-specific Pattern with `schema_version: "4.0"`.
Knowledge v3 records an evidence-grounded testing hypothesis, not a historical
Bug reproduction recipe or an executable Harness plan.

## 1. Responsibility

The active transformation is:

```text
API-specific Pattern
        ↓
zero or one API-specific Knowledge record
        ↓
HarnessSpec selection and executable planning
```

Pattern owns historical conditions, their reported necessity, the supported
defect mechanism, and the observed failure. Knowledge uses that evidence to
state one bounded risk hypothesis and to identify historical anchors, possible
variation space, and behavior worth observing.

Knowledge does not contain concrete Tensor construction, fixed reproduction
inputs, Strategy Primitives, risk-dimension tags, executable predicates,
Oracle implementations, C++ code, branch budgets, or feedback policy.

Initial extraction is **zero or one**, not exactly one. A Pattern that cannot
support a useful hypothesis without speculation produces a `not_extractable`
diagnostic instead of a fabricated Knowledge record.

## 2. Record shape

```json
{
  "schema_version": "3.0",
  "metadata": {
    "knowledge_id": "kn_pt_pv4_empty_input_boundary_k001",
    "canonical_name": "empty_input_boundary"
  },
  "derivation_information": {
    "method": "llm_assisted",
    "mapping_version": "3.1",
    "prompt_version": "knowledge_extract_v3_1",
    "model": "deepseek-v4-pro",
    "input_pattern": {
      "pattern_id": "pt_v4_example_p001",
      "pattern_hash": "sha256:..."
    },
    "generated_at": "2026-10-03",
    "validation_status": "structurally_validated"
  },
  "scope": {
    "framework": "pytorch",
    "target_api": "torch.example"
  },
  "learned_hypothesis": {
    "statement": "Boundary input states may expose insufficient validation or unsafe execution behavior in the target API.",
    "abstraction_rationale": "The source Pattern links a boundary condition to an observed failure while leaving other input properties unproven as necessary.",
    "evidence_status": "pattern_derived",
    "evidence_refs": [
      "pattern:pt_v4_example_p001:historical_condition:tc_01",
      "pattern:pt_v4_example_p001:observed_failure"
    ],
    "limitations": []
  },
  "exploration_guidance": {
    "historical_anchors": [],
    "variation_opportunities": [],
    "observation_candidates": []
  }
}
```

## 3. Metadata and derivation

`knowledge_id` is a stable Builder-generated identity. `canonical_name` is a
concise lower-snake-case testing-hypothesis name; it must not contain Issue,
Report, Pattern, commit, signal, or reproduction identifiers.

`input_pattern` records the exact Pattern ID and canonical SHA-256 hash used for
derivation. The Builder owns all derivation fields. In a generated Knowledge
record, `validation_status` is `structurally_validated`: shape, scope, lineage,
vocabularies, and evidence references passed automatic validation. Human review
is recorded separately against the immutable Knowledge ID and canonical hash;
it does not silently rewrite this Builder-owned field.

## 4. Scope

`scope` contains only `framework` and the single `target_api` inherited from the
Pattern. Knowledge v3 does not represent cross-API transfer. The Builder, not
the model, copies this scope.

## 5. Learned hypothesis

`statement` is the reusable, same-API testing hypothesis learned from the
Pattern. It is neither the complete historical trigger nor a claim that the
failure still exists in the current framework version.

The statement describes a bounded risk relationship: an evidence-grounded
boundary or mechanism may expose unsafe or inconsistent behavior in the target
API. It must not merely say that testing an input is useful. Conditions whose
necessity is `contributing` or `unknown` may motivate candidate boundaries, but
must not be stated as established prerequisites, fixed scope, or proven
triggers.

`abstraction_rationale` explains why the cited Pattern evidence motivates the
hypothesis and which historical constants are not proven necessary.

Allowed `evidence_status` values are:

- `pattern_derived`: a conservative abstraction semantically entailed by the
  cited Pattern facts;
- `analyst_inferred`: an LLM or analyst proposes a broader interpretation that
  remains grounded in cited Pattern evidence, including a new counterfactual,
  candidate boundary, comparison, or variation dimension.

`analyst_inferred` is a hypothesis label, not permission to introduce new
historical facts. `limitations` records material uncertainty, conflicts, or
scope restrictions. It may be empty.

## 6. Exploration guidance

All three arrays are required but may be empty. Their items have the same
shape:

```json
{
  "statement": "...",
  "evidence_status": "pattern_derived",
  "evidence_refs": ["pattern:..."]
}
```

### 6.1 Historical anchors

`historical_anchors` contains only source Pattern conditions whose
`necessity` is `required`. An anchor identifies evidence that should remain
represented in at least one Knowledge-directed exploration; it is not a global
constraint on the default or generic branches.

A `contributing` or `unknown` historical condition must never be promoted to an
anchor.

### 6.2 Variation opportunities

`variation_opportunities` describes evidence-grounded ways to explore beyond
the exact historical case. It may be informed by `contributing` or `unknown`
conditions, supported mechanisms, observed failures, and relations among them.

It must not claim that a proposed variation occurred historically, prescribe
concrete input values or code, or state that the variation will expose a Bug.
An interpretive generalization uses `analyst_inferred`.

### 6.3 Observation candidates

`observation_candidates` describes behavior worth observing in later testing.
It may abstract historical observations or propose a cautious future check.
It is not an executable Oracle: instrumentation, comparison procedures,
thresholds, expected exceptions, and implementation details belong to
HarnessSpec.

## 7. Evidence and absence rules

- Every asserted item has at least one valid reference supplied from the input
  Pattern.
- Knowledge cites Pattern fields and element IDs, never a Report or Issue
  directly.
- Absence is represented by an empty array. Placeholder items, empty strings,
  `unknown` enum values, and invented explanations are forbidden.
- Chen root-cause and symptom labels remain in Pattern. They are evidence
  context, not Knowledge fields and not direct mappings to exploration or
  Oracles.
- A historical constant is not necessary merely because it appears in one
  reproducer.

## 8. Validation boundary

The Builder validates:

1. exact top-level and nested keys;
2. Pattern schema version, identity, hash, and API scope;
3. lower-snake-case names and non-empty text;
4. controlled evidence-status values;
5. existence and uniqueness of all evidence references;
6. anchor references resolve only to Pattern conditions marked `required`;
7. forbidden executable or downstream fields are absent;
8. no empty placeholder item is emitted.

Automatic validation cannot prove that a hypothesis is scientifically useful
or semantically correct. That remains subject to review and later empirical
evaluation.

## 9. Human review

Every Knowledge record selected for an experiment must pass the lightweight
review in `../quality/knowledge_review_protocol.md`. A larger exploratory
collection may use a predeclared stratified sample, but an unreviewed record is
not thereby approved. Review decisions are bound to the Knowledge and Pattern
hashes in a separate ledger so generated records remain immutable.

## 10. Versioning

Knowledge v2.1 and Mapping/Contract v2.3 are preserved under
`schemas/legacy/knowledge_v2_1/`; their Builders are preserved under
`scripts/legacy/knowledge_v2_1/`.

New Knowledge outputs use `schema_version: "3.0"` and remain incompatible with
the current EXP011 Knowledge 2.1 reader until that interface is deliberately
updated. Existing HarnessSpecs and experiment artifacts are not relabelled or
rewritten.
