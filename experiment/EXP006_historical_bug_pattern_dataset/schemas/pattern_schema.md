# Bug Pattern Schema v4.0

## 1. Responsibility

A Pattern is an evidence-linked abstraction of one admitted historical Bug Report for one affected API. It answers four questions:

1. which API is this Pattern about;
2. under which historical conditions was the defect observed;
3. what supported mechanism, if any, was reported;
4. what historical failure was observed.

It does not define future input generation, Harness code, an experimental oracle, a fuzzing strategy, or feedback policy. Those belong to Knowledge and later layers.

The unit is `one Report × one affected API × one independently testable defect unit`. If a Report explicitly affects several APIs, the Builder projects it into separate API-specific Patterns. Multiple conditions or symptoms alone do not justify splitting.

## 2. Why the schema is deliberately small

Report already preserves source facts and evidence. Pattern therefore keeps only information needed for abstraction and downstream Knowledge generation. It removes the former `primary_api/confirmed_apis`, project-defined trigger dimensions, subject/predicate triples, custom oracle-kind taxonomy, and aggregate confidence fields because those either duplicated Report facts or forced uncertain interpretation into rigid labels.

Missing causal or classification evidence is represented by `null` or an empty optional list. The Builder must not call a missing value an error or ask the model to guess merely to satisfy the schema.

## 3. Record shape

```json
{
  "schema_version": "4.0",
  "metadata": {
    "pattern_id": "pt_v4_example_p001",
    "canonical_name": "example_boundary_failure",
    "pattern_level": "api_specific"
  },
  "derivation_information": {
    "method": "llm_assisted",
    "mapping_version": "4.2",
    "prompt_version": "pattern_extract_v4_2",
    "model": "deepseek-v4-pro",
    "input_reports": [
      {
        "report_id": "br_example",
        "report_hash": "sha256:example"
      }
    ],
    "generated_at": "2026-10-03",
    "validation_status": "automatically_validated"
  },
  "provenance": {
    "source_report": {
      "report_id": "br_example",
      "report_revision": 1,
      "report_hash": "sha256:example",
      "evidence_refs": ["ev_example"]
    },
    "abstraction_rationale": "The cited Report describes this API-specific historical behavior.",
    "unresolved_information": []
  },
  "scope": {
    "framework": "pytorch",
    "target_api": "torch.example"
  },
  "historical_conditions": [
    {
      "condition_id": "tc_01",
      "statement": "The historical case used an empty input.",
      "necessity": "unknown",
      "evidence_status": "source_explicit",
      "evidence_refs": ["ev_example"]
    }
  ],
  "defect_mechanism": null,
  "observed_failure": {
    "description": "The process terminated unexpectedly.",
    "symptom_category": "crash",
    "evidence_status": "analyst_normalized",
    "evidence_refs": ["ev_example"],
    "historical_observations": []
  }
}
```

## 4. Field semantics

### 4.1 Metadata and derivation

`metadata` provides a stable Pattern identity. `derivation_information` records how the artifact was created and the exact Report hash used. These fields are Builder-owned, not model-generated.

### 4.2 Provenance

`source_report` binds the Pattern to one Report revision and its content hash. The Builder computes `evidence_refs` as the exact de-duplicated union referenced by `historical_conditions`, `defect_mechanism`, `observed_failure`, and `historical_observations`; the model does not declare this provenance index. `abstraction_rationale` explains the bounded Report-to-Pattern transformation. `unresolved_information` records material gaps without inventing values.

### 4.3 Scope

`target_api` is the one API represented by this Pattern. It must exactly match an `affected` API assertion in the Report. APIs that are only mentioned cannot become targets. Cross-API knowledge transfer is not represented here.

### 4.4 Historical conditions

Each item is a source-grounded statement about the historical invocation, input, environment, execution context, or externally visible state:

- `statement`: normalized condition without prescribing future generation;
- `necessity`: `required`, `contributing`, or `unknown`;
- `evidence_status`: how the statement relates to the source;
- `evidence_refs`: supporting Report Evidence IDs.

The default for necessity is `unknown`. A concrete value in one reproducer does not prove necessity.

Implementation defects, missing checks, causal explanations, patch actions, and corrected expectations are not historical conditions. They belong in `defect_mechanism` or `observed_failure.historical_observations` as appropriate.

### 4.5 Defect mechanism

`defect_mechanism` is either `null` or one evidence-backed object containing `description`, optional `root_cause_category`, `evidence_status`, and `evidence_refs`. A failure symptom or trigger keyword cannot by itself establish a cause.

The optional root-cause vocabulary reuses the 13 categories reported by Chen et al.:

1. `type_issue`
2. `tensor_shape_misalignment`
3. `incorrect_algorithm_implementation`
4. `environment_incompatibility`
5. `api_incompatibility`
6. `api_misuse`
7. `incorrect_assignment`
8. `incorrect_exception_handling`
9. `misconfiguration`
10. `numerical_issue`
11. `concurrency_issue`
12. `dependent_module_issue`
13. `others`

The label classifies a supported mechanism; it is not a substitute for one. If the mechanism is supported but its category is uncertain, use `null`. `others` means a known mechanism outside the other categories, not “unknown”.

### 4.6 Observed failure

`description` preserves the API-specific historical manifestation. `symptom_category` is one optional Chen-category label: `crash`, `incorrect_functionality`, `build_failure`, `poor_performance`, `hang`, or `unreported`. Use `null` when the evidence does not support a reliable mapping; use `unreported` only when the source explicitly indicates that the symptom was not reported.

`historical_observations` stores evidence-linked statements describing detection, comparison, reproduction, or corrected expected behavior. It must not repeat invocation/input facts already captured by `historical_conditions`, or causal and patch-action details already captured by `defect_mechanism`. It is deliberately free text rather than a custom oracle taxonomy. It records history and does not prescribe the future Harness oracle.

Each semantic fact is assigned to its narrowest field. One Evidence ID may support several distinct statements, but substantially equivalent statements are not duplicated merely to make the Pattern appear more complete.

### 4.7 Evidence status

Allowed values are:

- `source_explicit`: stated directly in source text;
- `code_derived`: directly derived from cited source code;
- `patch_derived`: directly derived from a cited patch;
- `analyst_normalized`: conservative restatement or taxonomy mapping grounded in cited evidence.

`analyst_normalized` does not authorize new facts or causal claims.

## 5. Taxonomy provenance

The root-cause and symptom vocabularies are reused from Chen et al., *Toward Understanding Deep Learning Framework Bugs*, ACM TOSEM 2023, DOI `10.1145/3587155`. The paper's categories improve external grounding; our evidence links, nullable labels, and API-specific projection are project-specific representation choices and must be described as such.

## 6. Validation boundary

Automatic validation checks shape, version, IDs, selected API equality, evidence-reference membership, controlled values, and absence of downstream fields. It cannot prove semantic correctness of a condition, causal explanation, or taxonomy label.

Patterns used in experiments require the lightweight human review defined in `../quality/pattern_review_protocol.md`. Bulk exploratory Patterns may be reviewed by a predeclared stratified sample, but an unreviewed Pattern must not be presented as ground truth.
