# Pattern-to-Knowledge Rules v3.1

## 1. Purpose and cardinality

Map one API-specific Pattern v4.0 into at most one API-specific Knowledge v3.0
record. A result may be:

- `candidate`: one evidence-grounded Knowledge candidate; or
- `not_extractable`: the Pattern cannot support a useful testing hypothesis
  without unsupported speculation.

Never create content merely to satisfy a field or record-count target.

## 2. Layer boundary

Pattern records historical evidence. Knowledge proposes a bounded, same-API
testing hypothesis and open exploration guidance. HarnessSpec later determines
current applicability, implementability, risk-dimension tags, concrete target
properties, Activation, Oracles, branches, and budgets.

Do not emit concrete Tensor values, exact reproduction steps, mutations,
Strategy Primitives, validity/risk/activation predicates, HarnessSpec fields,
instrumentation, source code, or feedback logic.

## 3. Deterministic mapping

The Builder supplies:

| Pattern field | Knowledge field |
| --- | --- |
| Pattern ID and canonical hash | `derivation_information.input_pattern` |
| `scope.framework` | `scope.framework` |
| `scope.target_api` | `scope.target_api` |
| Builder/model/mapping identity | remaining derivation fields |
| accepted evidence references | all claim-reference validation |

The model must not emit or change those fields.

## 4. Semantic mapping

### 4.1 Learned hypothesis

Derive one hypothesis from the smallest sufficient combination of:

- `historical_conditions`;
- an optional supported `defect_mechanism`;
- `observed_failure` and its historical observations.

The statement must generalize beyond the exact reproducer without claiming a
new historical fact, cross-API transfer, or current-version failure. The
abstraction rationale must explain the evidence link and preserve uncertainty
about conditions whose necessity is not established.

State a bounded risk relationship: an evidence-grounded boundary or mechanism
may expose a class of unsafe or inconsistent behavior in the target API. Do not
substitute the meta-claim that testing an input is useful, and do not reproduce
the complete historical input, environment, and expected failure.

A condition marked `contributing` or `unknown` may motivate a candidate
boundary, but it must not be written as an established prerequisite, scope
restriction, or proven trigger. Use modal language, explain the uncertainty in
the rationale or limitations, and leave the condition open to variation. This
rule permits evidence-grounded exploration without converting one historical
example into a reproduction recipe.

Use `pattern_derived` only when the semantic content is conservatively entailed
by the cited Pattern. Use `analyst_inferred` for an evidence-grounded but
interpretive extension, including a new counterfactual, comparison, candidate
boundary, or variation dimension. If no meaningful statement can be produced
under those rules, return `not_extractable`.

### 4.2 Historical anchors

An anchor may cite only an individual `historical_condition` whose `necessity`
equals `required`. Do not automatically copy every required condition; retain
only conditions material to the hypothesis.

Never promote `contributing` or `unknown` conditions to anchors. Anchors apply
only to later Knowledge-directed exploration, not to generic testing.

### 4.3 Variation opportunities

Use variation opportunities to retain meaningful fuzzing freedom and explore
nearby or combined states instead of fixing the complete historical input.
They may be informed by:

- `contributing` and `unknown` historical conditions;
- aspects of a required condition that evidence does not require to remain
  constant;
- supported mechanism and failure evidence.

Do not silently transform a historical example into a necessary future value.
Do not promise that a variation will trigger a Bug. Interpretive opportunities
use `analyst_inferred`.

### 4.4 Observation candidates

Derive candidates conservatively from `observed_failure`, individual
historical observations, and supported mechanism evidence. A historical
symptom is not automatically a sound future Oracle. State only what may be
worth observing; leave executable Oracle selection and implementation to
HarnessSpec. A proposed historical fix or test expectation may motivate a
candidate observation, but must not be presented as the current expected
behavior of the API.

### 4.5 Limitations

Preserve unresolved information that materially limits the hypothesis,
generalization, or candidate observation. Missing evidence is a limitation,
not an exclusion condition or a fact to infer.

## 5. Taxonomy rule

Chen root-cause and symptom categories remain Pattern annotations. Do not copy
them into Knowledge, and do not mechanically map them to variation
opportunities, observations, Harness risk dimensions, Primitives, or Oracles.

Knowledge v3 defines no defect taxonomy and no operational risk-dimension
taxonomy.

## 6. Evidence rules

- Every asserted item cites one or more supplied Pattern evidence references.
- Do not cite Reports, Issues, commits, or external sources directly.
- Do not invent an API, historical condition, mechanism, failure, source, or
  evidence reference.
- `pattern_derived` describes a conservative evidence-backed abstraction.
- `analyst_inferred` identifies a proposed interpretation, not a historical
  fact.
- Empty arrays are valid. Empty strings and placeholder objects are invalid.

## 7. LLM and Builder responsibilities

The LLM emits only:

- extraction status and an optional non-extraction reason;
- `canonical_name`;
- the learned hypothesis;
- historical anchors;
- variation opportunities;
- observation candidates.

The Builder:

- validates Pattern v4.0 and computes its canonical hash;
- supplies addressable evidence references and required-condition references;
- injects IDs, derivation metadata, scope, and structural-validation status;
- rejects unsupported references, promoted non-required anchors, forbidden
  downstream fields, and unknown fields;
- writes a Knowledge record only for a validated `candidate` result;
- reports `not_extractable` without writing a fabricated Knowledge record.

Automatic validation does not prove that free text contains no overgeneralized
semantic claim. Experiment-used Knowledge must pass the review defined in
`../quality/knowledge_review_protocol.md`.
