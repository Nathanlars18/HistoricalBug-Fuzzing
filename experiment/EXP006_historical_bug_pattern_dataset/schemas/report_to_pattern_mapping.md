# Report-to-Pattern Mapping v4.2

## 1. Boundary

Report is the factual, source-linked record. Pattern is an API-specific abstraction made from one admitted Report. The transformation may normalize wording and apply an optional published taxonomy label, but it must not add an unsupported historical fact or a future testing design.

Only the latest validation-passed, non-rejected Report revision is eligible. All Pattern evidence references must resolve to Evidence IDs in that revision. Live retrieval is forbidden during Pattern extraction.

## 2. Projection unit

The deterministic Builder enumerates Report API assertions whose relation is `affected`. It invokes extraction separately for each selected API.

- one affected API normally produces one Pattern;
- several affected APIs produce separate API-specific Patterns;
- `mentioned` APIs are not eligible;
- multiple conditions, symptoms, or possible explanations do not alone create multiple Patterns;
- multiple Patterns for one Report/API pair require independently testable defect units and later human review.

This split keeps API scope explicit without claiming cross-API transfer.

## 3. Mapping

| Report evidence | Pattern field | Rule |
|---|---|---|
| `identity`, revision and content hash | `provenance.source_report` | Builder copies exact identity, revision and hash, then derives `evidence_refs` as the exact union used by the semantic Pattern fields. |
| selected `affected` API assertion | `scope.target_api` | Must match exactly; no API inference. |
| `reported_behavior.trigger_claims` and relevant operation context | `historical_conditions` | Normalize factual invocation, input, environment, execution-context, or externally visible state conditions; do not place implementation causes or fixes here, prescribe generators, or overstate necessity. |
| `reported_diagnosis.root_cause_claims`, cited code or patch evidence | `defect_mechanism` | Use one supported description or `null`; category is optional. |
| `reported_behavior.failure_observations` | `observed_failure.description` | Summarize the historical manifestation with evidence. |
| the same manifestation evidence | `observed_failure.symptom_category` | Optionally map to one Chen category; use `null` if unreliable. |
| source-explicit detection, comparison, reproduction or corrected-expectation statements | `observed_failure.historical_observations` | Preserve factual observations in free text; do not duplicate historical conditions or mechanism/patch-action details, and do not invent a future oracle. |
| unresolved or contradictory source material | `provenance.unresolved_information` | Preserve the gap rather than forcing a value. |

Report fix status and issue state remain provenance context. They do not automatically establish the root cause, symptom, or present-version behavior.

## 4. Evidence-strength rules

- A reproducer constant proves historical presence, not necessity.
- Error text proves an observed manifestation, not its cause.
- A patch may support a mechanism only when the cited change and surrounding source justify that interpretation.
- A mechanism shown for one file, backend, device path, or execution path must not be generalized to another path merely because both received a similar guard or fix.
- Historical observations retain detection, comparison, reproduction, and corrected-behavior evidence. Incidental warnings and project-management metadata such as priority or assignment are excluded unless they change the failure semantics.
- Each semantic fact belongs in its narrowest field: setup in `historical_conditions`, cause in `defect_mechanism`, manifestation in `observed_failure.description`, and detection/comparison/reproduction/corrected expectation in `historical_observations`. The same evidence may support distinct facts, but substantially equivalent statements are not duplicated across fields.
- Benchmark curator labels remain attributed annotations; they are not maintainer confirmation.
- `others` is used only for a supported mechanism outside the other 12 root-cause categories.
- `null` is valid for optional classification fields and must not trigger a retry by itself.

## 5. Model and validator responsibilities

The model proposes normalized statements and optional labels from the supplied Report and resolved evidence. The Builder owns IDs, API projection, Report revision/hash, the exact semantic evidence-reference union, output version, timestamps, and stable item IDs.

The validator rejects:

- an API different from the selected affected API;
- unknown Evidence IDs;
- a stored provenance evidence set that differs from the exact evidence union used by semantic Pattern fields;
- unsupported keys or controlled values;
- empty required descriptions;
- downstream Harness, mutation, Strategy, code-generation, or feedback fields.

Automatic acceptance means structurally and referentially valid, not semantically proven. Experiment-used Patterns require the review described in `../quality/pattern_review_protocol.md`.
