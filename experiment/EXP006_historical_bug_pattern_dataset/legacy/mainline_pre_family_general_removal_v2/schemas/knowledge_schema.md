# Historical Bug Knowledge Schema v2.0

## 1. Purpose

A Knowledge record is an evidence-grounded, reusable testing principle derived
from one API-specific Bug Pattern.

It answers:

- What testing risk can be learned from the supporting historical Pattern?
- What should testing attempt to explore or observe?
- Under which semantic conditions may this Knowledge be applicable?
- Under which conditions should this Knowledge not be applied?
- What historically relevant failure behavior may be worth observing?
- How strongly is this Knowledge supported by the underlying Pattern?

The core pipeline is:

```text
Structured Bug Report
        ↓
API-specific Bug Pattern
        ↓
API-specific Knowledge
        ↓
HarnessSpec
        ↓
Harness Generator
```

Knowledge transforms evidence-backed historical Pattern information into a
reusable testing principle.

It is not a restatement of the original Report or Pattern.

## 2. Scope and Non-goals

### 2.1 Scope

Knowledge v2 represents API-specific testing knowledge.

It preserves:

- derivation from one supporting Pattern;
- directly supported API scope;
- reusable risk principle;
- high-level testing objective;
- applicability and exclusion conditions;
- high-level exploration goals;
- high-level Oracle guidance;
- limitations and confidence.

### 2.2 Non-goals

Knowledge v2 does not contain:

- raw Issue or Bug Report details;
- direct Report-level source verification;
- complete historical trigger signatures;
- complete defect-mechanism descriptions;
- concrete Tensor shapes, dtypes, values, devices, layouts, or offsets;
- input mutation implementation;
- Tensor construction implementation;
- Strategy Primitives;
- validity predicates;
- risk predicates;
- activation predicates;
- HarnessSpec;
- C++ Harness code;
- code-generation prompts;
- conflict resolution among multiple Knowledge records;
- General Knowledge or Pattern Family decisions.

The responsibilities of the layers are:

```text
Pattern
  → historical evidence, trigger, mechanism, and observed failure

Knowledge
  → reusable testing principle, applicability, and high-level guidance

HarnessSpec
  → Knowledge selection, constraint combination, executable strategies,
    activation predicates, Oracle instrumentation, priority,
    conflict resolution, and feedback updates
```

## 3. Cardinality and Relationships

The initial mapping is one-to-one:

```text
One API-specific Pattern
        ↓
One API-specific Knowledge
```

A Report may contain multiple independent Patterns, and each Pattern produces
its own Specific Knowledge:

```text
One Bug Report
        ↓
Multiple independent Patterns
        ↓
One Specific Knowledge per Pattern
```

If one Pattern appears to support multiple independent and separately usable
testing principles, the Pattern should first be reviewed to determine whether
it should have been split into multiple Patterns.

Initial extraction must not create multiple Knowledge records from one Pattern.

Multiple Patterns may later corroborate one API-specific Knowledge after
matching and human review, but this is not part of initial extraction.

Multiple Patterns do not automatically form General Knowledge.

General Knowledge will be designed later from reviewed Pattern Family or
General Pattern evidence.

## 4. Top-level JSON Structure

```json
{
  "schema_version": "2.0",

  "metadata": {
    "knowledge_id": null,
    "canonical_name": null,
    "knowledge_level": "api_specific"
  },

  "derivation_information": {
    "method": null,
    "mapping_version": "2.0",
    "prompt_version": null,
    "model": null,
    "input_patterns": [],
    "generated_at": null,
    "validation_status": "not_reviewed"
  },

  "evidence_basis": {
    "supporting_patterns": [],
    "derivation_rationale": null,
    "limitations": []
  },

  "scope": {
    "framework": "pytorch",
    "primary_api": null,
    "directly_supported_apis": []
  },

  "knowledge_statement": {
    "risk_principle": null,
    "testing_objective": null,
    "failure_relevance": null,
    "evidence_status": "unknown",
    "evidence_refs": []
  },

  "applicability": {
    "candidate_family_tags": [],
    "applicability_conditions": [],
    "exclusion_conditions": [],
    "rationale": null,
    "evidence_status": "unknown",
    "evidence_refs": []
  },

  "testing_guidance": {
    "risk_dimensions": [],
    "exploration_goals": [],
    "oracle_guidance": []
    },

  "confidence": {
    "evidence_confidence": "low",
    "abstraction_confidence": "low",
    "applicability_confidence": "low",
    "oracle_guidance_confidence": "low"
  }
}
```

## 5. Common Representation Rules

### 5.1 Required, Optional, and Unknown Values

- All top-level objects are required.
- Arrays must exist even when empty.
- Unknown free-text or ordinary scalar values must use `null`.
- Do not use empty strings such as `""`.
- The string `"unknown"` may be used only when it is an explicitly allowed
  value of a controlled enum field.
- Controlled fields must use only the allowed enum values defined below.
- Every nontrivial Knowledge claim must be traceable to Pattern evidence.
- Knowledge must not assert a stronger claim than its supporting Pattern allows.
- Knowledge must not add a new historical fact that does not exist in its
  supporting Pattern.

### 5.2 Evidence Status

The following values are used whenever the origin of a Knowledge claim must be
recorded:

- `pattern_explicit`
- `pattern_derived`
- `analyst_inferred`
- `unknown`

Definitions:

- `pattern_explicit`: directly preserved from a supporting Pattern field.
- `pattern_derived`: derived by combining or abstracting evidence-backed Pattern
  fields without adding unsupported facts.
- `analyst_inferred`: inferred by an LLM or human analyst from supporting
  Pattern evidence.
- `unknown`: no reliable basis is available.

### 5.3 Confidence Levels

- `high`
- `medium`
- `low`

Definitions:

- `high`: directly and consistently supported by the relevant Pattern evidence.
- `medium`: strongly supported by Pattern evidence but requires a modest
  additional interpretation.
- `low`: incomplete, weakly supported, or analyst-inferred.

Confidence must not be increased merely because a Knowledge statement is
well-written or appears generally plausible.

## 6. Metadata

```json
"metadata": {
  "knowledge_id": "kn_matmul_storage_boundary_exploration_k001",
  "canonical_name": "matmul_storage_boundary_exploration",
  "knowledge_level": "api_specific"
}
```

| Field | Type | Required | Purpose |
|---|---|---:|---|
| knowledge_id | string | yes | Stable and globally unique identifier for this Knowledge record. |
| canonical_name | string | yes | Human-readable testing-principle name in lowercase snake_case. |
| knowledge_level | enum | yes | Must be `api_specific` in Knowledge v2. |

Naming rules:

```text
knowledge_id:
kn_{framework_prefix}_{canonical_name}_k{ordinal}

framework_prefix:
pytorch    → pt
tensorflow → tf
other framework names → normalized lowercase framework name

canonical_name:
{api_or_operator}_{testing_principle}
```

Examples:

```text
kn_pt_matmul_storage_boundary_exploration_k001
kn_pt_rshift_cross_device_oracle_guidance_k001

matmul_storage_boundary_exploration
rshift_cross_device_oracle_guidance
```

A canonical name must not contain:

- Issue numbers;
- Report IDs;
- Pattern IDs;
- commit IDs;
- exact crash signals;
- exact reproduction scripts;
- arbitrary concrete Tensor values;
- implementation-specific code details.

## 7. Derivation Information

```json
"derivation_information": {
  "method": "llm_assisted",
  "mapping_version": "2.0",
  "prompt_version": "knowledge_extract_v2",
  "model": "deepseek-v4-pro",
  "input_patterns": [
    {
      "pattern_id": "pt_matmul_unaligned_storage_p001",
      "pattern_hash": "sha256:..."
    }
  ],
  "generated_at": "2026-08-28",
  "validation_status": "automatically_validated"
}
```

| Field | Type | Required | Purpose |
|---|---|---:|---|
| method | enum | yes | Records how Knowledge was derived from Pattern evidence. |
| mapping_version | string | yes | Version of `pattern_to_knowledge_rules.md` used. |
| prompt_version | string/null | yes | Prompt version when LLM assistance is used. |
| model | string/null | yes | Model identifier when LLM assistance is used. |
| input_patterns | array | yes | Exact Pattern record used as input. |
| generated_at | ISO date string | yes | Date on which this Knowledge record was generated. |
| validation_status | enum | yes | Current quality and review status of the Knowledge record. |

Each `input_patterns` item contains:

| Field | Type | Required | Purpose |
|---|---|---:|---|
| pattern_id | string | yes | Stable identifier of the source Pattern. |
| pattern_hash | string | yes | SHA-256 hash of the exact Pattern JSON used for derivation. |

Allowed `method` values:

- `direct_mapping`
- `llm_assisted`
- `manual`
- `hybrid`

Allowed `validation_status` values:

- `not_reviewed`
- `automatically_validated`
- `human_verified`
- `needs_revision`

## 8. Evidence Basis

```json
"evidence_basis": {
  "supporting_patterns": [
    {
      "pattern_id": "pt_matmul_unaligned_storage_p001",
      "relation": "direct_derivation",
      "evidence_refs": [
        "pattern:pt_matmul_unaligned_storage_p001:trigger_signature",
        "pattern:pt_matmul_unaligned_storage_p001:defect_mechanism"
      ]
    }
  ],
  "derivation_rationale": "The supporting Pattern indicates that storage-sensitive execution may expose failures under layout or memory boundary conditions; this is abstracted into a reusable exploration principle.",
  "limitations": [
    "The Pattern does not establish applicability to APIs without controllable tensor storage."
  ]
}
```

| Field | Type | Required | Purpose |
|---|---|---:|---|
| supporting_patterns | array | yes | Pattern records that directly support this Knowledge. |
| derivation_rationale | string | yes | Explains why Pattern evidence supports the Knowledge abstraction. |
| limitations | array | yes | Material limitations, uncertainties, or non-transfer conditions. |

Each `supporting_patterns` item contains:

| Field | Type | Required | Purpose |
|---|---|---:|---|
| pattern_id | string | yes | Identifier of the supporting Pattern. |
| relation | enum | yes | How the Pattern supports this Knowledge. |
| evidence_refs | array | yes | References to relevant Pattern fields or Pattern element IDs. |

Allowed `relation` values:

- `direct_derivation`
- `corroborating_derivation`

Rules:

- Initial Pattern-to-Knowledge extraction must create exactly one
  `direct_derivation` entry corresponding to the input Pattern.
- The LLM must not invent Pattern IDs.
- Additional `corroborating_derivation` Patterns may be added only after later
  matching and human review.
- Knowledge must not cite a Bug Report directly; it cites its supporting Pattern.
- `limitations` may be empty when no material limitation is identified.

## 9. Scope

```json
"scope": {
  "framework": "pytorch",
  "primary_api": "torch.matmul",
  "directly_supported_apis": [
    "torch.matmul"
  ]
}
```

| Field | Type | Required | Purpose |
|---|---|---:|---|
| framework | enum | yes | Target deep learning framework. |
| primary_api | string | yes | Main API directly supported by the source Pattern. |
| directly_supported_apis | array | yes | APIs directly supported by historical Pattern evidence. |

Rules:

- `primary_api` must appear in `directly_supported_apis`.
- `directly_supported_apis` is inherited from the directly supporting Pattern scope.
- Candidate transfer APIs must not be added to `directly_supported_apis`.
- Initial Knowledge v2 is API-specific and must not declare unverified cross-API support.

## 10. Knowledge Statement

```json
"knowledge_statement": {
  "risk_principle": "Storage-sensitive backend execution may be vulnerable to tensor layout or memory-boundary conditions.",
  "testing_objective": "Explore storage and layout boundary conditions when the target API exposes controllable tensor storage and backend-dependent execution.",
  "failure_relevance": "Such conditions may expose crash, exception, or semantic-divergence behavior associated with storage-sensitive execution paths.",
  "evidence_status": "pattern_derived",
  "evidence_refs": [
    "pattern:pt_matmul_unaligned_storage_p001:trigger_signature",
    "pattern:pt_matmul_unaligned_storage_p001:defect_mechanism",
    "pattern:pt_matmul_unaligned_storage_p001:observed_failure"
  ]
}
```

| Field | Type | Required | Purpose |
|---|---|---:|---|
| risk_principle | string | yes | Reusable testing risk learned from the supporting Pattern. |
| testing_objective | string | yes | High-level testing objective motivated by the risk principle. |
| failure_relevance | string/null | yes | Why the objective may reveal historically relevant failure behavior. |
| evidence_status | enum | yes | Origin of the Knowledge statement. |
| evidence_refs | array | yes | Pattern evidence supporting the Knowledge statement. |

Rules:

- `risk_principle` describes a reusable testing principle, not an exact Bug reproduction.
- `testing_objective` describes what testing should explore, not how to construct inputs.
- `failure_relevance` may be `null` if the Pattern does not support a reliable connection to a failure type.
- `pattern_explicit` and `pattern_derived` statements require evidence references.
- `analyst_inferred` statements require evidence references and may not have high abstraction confidence.
- Do not add concrete Tensor values, exact API call sequences, C++ code, or Strategy Primitive details.

## 11. Applicability

```json
"applicability": {
  "candidate_family_tags": [
    "memory_alignment",
    "storage_sensitive_backend"
  ],
  "applicability_conditions": [
    {
      "condition_id": "ac_01",
      "condition_kind": "input_capability",
      "statement": "The target API accepts tensor inputs whose storage or layout properties can be controlled without violating API-call validity.",
      "evidence_status": "pattern_derived",
      "evidence_refs": [
        "pattern:pt_matmul_unaligned_storage_p001:transferability_hypothesis"
      ]
    },
    {
      "condition_id": "ac_02",
      "condition_kind": "execution_capability",
      "statement": "The target API may execute through a backend path whose behavior is sensitive to storage or layout conditions.",
      "evidence_status": "analyst_inferred",
      "evidence_refs": [
        "pattern:pt_matmul_unaligned_storage_p001:defect_mechanism"
      ]
    }
  ],
  "exclusion_conditions": [
    {
      "condition_id": "ec_01",
      "condition_kind": "api_semantics",
      "statement": "Do not apply this Knowledge when the API has no tensor-storage-related execution behavior.",
      "evidence_status": "pattern_derived",
      "evidence_refs": [
        "pattern:pt_matmul_unaligned_storage_p001:transferability_hypothesis"
      ]
    }
  ],
  "rationale": "The testing principle is relevant only when the target API has compatible input and execution semantics.",
  "evidence_status": "pattern_derived",
  "evidence_refs": [
    "pattern:pt_matmul_unaligned_storage_p001:transferability_hypothesis"
  ]
}
```

| Field | Type | Required | Purpose |
|---|---|---:|---|
| candidate_family_tags | array | yes | Retrieval tags for later Pattern Family or General Knowledge analysis. |
| applicability_conditions | array | yes | Semantic prerequisites for considering this Knowledge for a target API. |
| exclusion_conditions | array | yes | Known semantic conditions under which this Knowledge must not be selected. |
| rationale | string/null | yes | Concise explanation of the applicability boundary. |
| evidence_status | enum | yes | Origin of the candidate tags or rationale. |
| evidence_refs | array | yes | Pattern evidence supporting the candidate tags or rationale. |

Each applicability_conditions or exclusion_conditions item contains:

| Field	| Type	| Required	| Purpose| 
| condition_id	| string	| yes	| Stable local identifier, generated by the script.| 
| condition_kind	| enum	| yes	| Broad kind of semantic prerequisite or exclusion.| 
| statement	| string	| yes	| Human-readable semantic condition; not an executable predicate.| 
| evidence_status	| enum	| yes	| Origin of this individual condition.| 
| evidence_refs	| array	| yes	| Pattern evidence supporting this individual condition.| 


Allowed condition_kind values:

- api_semantics
- input_capability
- execution_capability

Rules:

- Applicability is a candidate-selection rule, not proof of cross-API validity.
- This object must not list candidate APIs.
- A Pattern Family or General Knowledge decision must not be made here.
- condition_id values use ac_01, ac_02, … for applicability conditions and ec_01, ec_02, … for exclusion conditions.
- The extraction script, rather than the LLM, assigns condition_id.
- condition_kind must not use unknown or other. If a condition cannot be classified reliably, omit it and record the uncertainty in evidence_basis.limitations.
- Conditions must state semantic properties, not concrete Tensor values, mutation operations, API-call code, validity predicates, or activation predicates.
- candidate_family_tags may be empty.
- If no applicability claim is made, both condition lists must be empty, rationale must be null, evidence_status must be unknown, and evidence_refs may be empty.
- Applicability confidence is stored only in confidence.applicability_confidence.

## 12. Testing Guidance

```json
"testing_guidance": {
  "risk_dimensions": [
    "memory",
    "layout",
    "backend"
  ],
  "exploration_goals": [
    {
      "goal_id": "eg_01",
      "target_dimension": "memory",
      "statement": "Explore valid storage and memory-boundary conditions while preserving API-call validity.",
      "priority": "primary",
      "evidence_status": "pattern_derived",
      "evidence_refs": [
        "pattern:pt_matmul_unaligned_storage_p001:trigger_signature"
      ]
    },
    {
      "goal_id": "eg_02",
      "target_dimension": "backend",
      "statement": "Observe behavior when execution may enter a storage-sensitive backend path.",
      "priority": "secondary",
      "evidence_status": "analyst_inferred",
      "evidence_refs": [
        "pattern:pt_matmul_unaligned_storage_p001:defect_mechanism"
      ]
    }
  ],
  "oracle_guidance": [
    {
      "objective": "Observe unexpected process termination, exceptions, or behavior divergence under the identified risk condition.",
      "observation_kind": "historical_observable",
      "evidence_status": "pattern_derived",
      "evidence_refs": [
        "pattern:pt_matmul_unaligned_storage_p001:observed_failure"
      ],
      "confidence": "medium"
    }
  ]
}
```

| Field | Type | Required | Purpose |
|---|---|---:|---|
| risk_dimensions | array | yes | De-duplicated risk dimensions targeted by exploration goals. |
| exploration_goals | array | yes | High-level, evidence-grounded exploration directions. |
| oracle_guidance | array | yes | High-level guidance on behavior worth observing. |


Allowed risk_dimensions values:
- shape
- dtype
- value
- device
- backend
- layout
- memory
- aliasing
- output_tensor
- state
- execution
- graph
- concurrency
- api_contract

Each exploration_goals item contains:

| Field	| Type	| Required	| Purpose| 
| goal_id	| string	| yes	| Stable local identifier, generated by the script.| 
| target_dimension	| enum	| yes	| One risk dimension targeted by this exploration goal.| 
| statement	| string	| yes	| High-level exploration direction; not an executable strategy.| 
| priority	| enum	| yes	| Relative research importance of the goal, not a scheduling command.| 
| evidence_status	| enum	| yes	| Origin of this individual goal.| 
| evidence_refs	| array	| yes	| Pattern evidence supporting this individual goal.| 

Allowed priority values:

- primary
- secondary

Each oracle_guidance item contains:

| Field	| Type	| Required	| Purpose| 
| objective	| string	| yes	| High-level behavior that later testing should observe.| 
| observation_kind	| enum	| yes	| Whether this is a historical observation or a derived Oracle candidate.| 
| evidence_status	| enum	| yes	| Origin of the Oracle guidance.| 
| evidence_refs	| array	| yes	| Supporting Pattern evidence references.| 
| confidence	| enum	| yes	| Confidence in this individual Oracle guidance item.| 

Allowed observation_kind values:

- historical_observable
- derived_oracle_candidate
Rules:
- goal_id values use eg_01, eg_02, … and are assigned by the extraction script.
- risk_dimensions must equal the de-duplicated set of target_dimension values from exploration_goals.
- If exploration_goals is empty, risk_dimensions must also be empty.
- Exploration goals must remain high-level and must not define concrete Tensor construction, mutation operations, parameter values, execution code, validity predicates, risk predicates, or activation predicates.
- oracle_guidance must not define executable instrumentation or an exact Oracle implementation.
- Concrete constraints, Strategy Primitives, executable predicates, Oracle implementation, Knowledge conflict resolution, and priority combination belong to HarnessSpec.

## 13. Confidence

```json
"confidence": {
  "evidence_confidence": "high",
  "abstraction_confidence": "medium",
  "applicability_confidence": "medium",
  "oracle_guidance_confidence": "medium"
}
```

| Field | Purpose |
|---|---|
| evidence_confidence | Confidence that Pattern evidence is complete and correctly cited. |
| abstraction_confidence | Confidence that Pattern evidence supports the reusable Knowledge principle. |
| applicability_confidence | Confidence that applicability and exclusion conditions are justified. |
| oracle_guidance_confidence | Aggregate confidence in the Oracle guidance items. |

Rules:

- `evidence_confidence` evaluates evidence traceability, not the popularity of the source API.
- `abstraction_confidence` evaluates Pattern-to-Knowledge abstraction quality.
- `applicability_confidence` must be `low` when Applicability makes no claim.
- `oracle_guidance_confidence` must be `low` when `oracle_guidance` is empty.
- If `knowledge_statement.evidence_status` is `analyst_inferred`,
  `abstraction_confidence` must not be `high`.
- Confidence must not be assigned solely because an LLM produced fluent text.

## 14. Validation Rules

A Knowledge v2 record is valid only if all of the following hold:

1. `schema_version` is `2.0`.
2. `metadata.knowledge_level` is `api_specific`.
3. Exactly one `supporting_patterns` entry exists during initial extraction.
4. The supporting Pattern relation is `direct_derivation`.
5. The direct Pattern appears in `derivation_information.input_patterns`.
6. `scope.primary_api` appears in `scope.directly_supported_apis`.
7. Scope is inherited from directly supporting Pattern evidence.
8. All controlled values use defined vocabularies.
9. Every asserted Knowledge statement, applicability condition, exclusion condition, exploration goal, and Oracle guidance item has evidence references to Pattern fields.
10. Knowledge contains no Bug Report facts not represented by its supporting Pattern.
11. Knowledge contains no Strategy Primitive, HarnessSpec, code, mutation procedure, concrete input construction, executable predicate, or API-specific implementation plan.
12. Unknown free-text scalar information uses `null`, not an empty string.
13. `applicability_conditions` and `exclusion_conditions` use only the defined `condition_kind` values.
14. `risk_dimensions` equals the de-duplicated set of `target_dimension` values used by `exploration_goals`.
15. If Applicability makes no claim, `applicability_confidence` is `low`.
16. If `oracle_guidance` is empty, `oracle_guidance_confidence` is `low`.
17. If `knowledge_statement.evidence_status` is `analyst_inferred`, `abstraction_confidence` must not be `high`.
18. A Knowledge record with unsupported abstraction, unclear scope, or missing evidence must be marked `needs_revision`.

## 15. Versioning and Migration Notes

- Existing Knowledge v1 records are preserved under `legacy/knowledge_base_v1/`.
- Current Knowledge v2 records will later be written to `knowledge_base/<api>/`.
- Existing v1 testing strategies must not be copied directly into Knowledge v2.
- Existing v1 Report metadata must not be duplicated; Knowledge v2 cites supporting
  Pattern records instead.
- Existing v1 transferability statements must be revalidated against supporting
  Pattern evidence.
- General Knowledge will be designed later with Pattern Family construction and
  must not be generated during initial Knowledge v2 extraction.

Knowledge v2 is the reusable testing-principle layer. It remains independent
from HarnessSpec-level executable planning, Knowledge conflict resolution, and
feedback-loop optimization.