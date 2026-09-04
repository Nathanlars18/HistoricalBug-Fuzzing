# Pattern Family Candidate Manifest v1.1

## 1. Purpose

A Pattern Family Candidate Manifest is an immutable deterministic artifact
representing one exact candidate group of API-specific Patterns.

It answers:

- Which exact Pattern versions form this candidate group?
- Which deterministic retrieval signals caused them to be grouped?
- Which minimum eligibility conditions were satisfied?
- Are there rule-detected chain-drift, outlier, duplication, or consistency risks?
- Which complete Pattern records must be loaded for later Family analysis?
- Can this exact Candidate object be reused in a later retrieval run?

The candidate pipeline is:

```text
All eligible API-specific Pattern JSON files
        ↓
Deterministic full-corpus candidate retrieval
        ↓
Immutable Candidate Manifest objects
        +
Immutable Candidate Run Index
        ↓
Family conversion script selects Candidates
and checks the Decision cache
        ↓
Candidate Manifest
+ complete member Pattern JSON files
+ Family Contract
+ Family Rules
        ↓
LLM Family analysis when required
        ↓
Pattern Family Validator
        ↓
Human review
```

The Candidate Manifest and Candidate Run Index have different responsibilities:

```text
Candidate Manifest
    = the exact, reusable content of one candidate group

Candidate Run Index
    = the relationship between Candidate objects across one retrieval run
```

A Candidate Manifest does not store:

- whether the LLM has already analyzed it;
- whether a prior Decision can be reused;
- its change status relative to a previous run;
- an `accept`, `split`, `reject`, or `needs_revision` decision.

Those states are handled by the Candidate Run Index and the later Family
conversion stage.

A Candidate Manifest is not a Pattern Family.

It does not establish:

- a shared defect mechanism;
- cross-API transferability;
- a General Pattern;
- General Knowledge;
- applicability to an unobserved API;
- acceptance, rejection, or splitting of a Pattern Family.

## 2. Deterministic-only Rule

The Candidate Manifest must be generated without an LLM.

Its contents are limited to:

1. fields copied from validated API-specific Pattern records;
2. deterministic counts and set operations;
3. deterministic pairwise comparisons;
4. results of versioned retrieval rules;
5. controlled warnings produced by those rules.

The candidate script must not generate:

- a semantic Family name;
- a natural-language commonality summary;
- a generalized trigger or mechanism;
- membership rationale;
- General Knowledge;
- an accept, split, reject, or needs-revision decision;
- a claim that all candidate members share the same Bug.

Input Pattern fields may themselves contain evidence-backed abstraction from an
earlier Pattern extraction stage. The Candidate Manifest must preserve their
evidence status and confidence where relevant and must not strengthen them.

## 3. Storage and Naming

Candidate Manifests and Candidate Run Indexes are stored separately:

```text
quality/pattern_family_candidates/
├── objects/
│   └── <framework>/
│       └── <candidate_group_id>.json
└── runs/
    └── <framework>/
        └── <run_id>/
            └── candidate_run_index.json
```

For PyTorch:

```text
quality/pattern_family_candidates/
├── objects/
│   └── pytorch/
│       └── pfc_pt_a13f09c2e641.json
└── runs/
    └── pytorch/
        └── pfcr_pt_000001/
            └── candidate_run_index.json
```

Candidate filenames use:

```text
pfc_{framework_prefix}_{short_hash}.json
```

The Candidate ID short hash is derived deterministically from:

```text
sorted member Pattern IDs
+ sorted member Pattern hashes
+ retrieval Policy version
+ canonical retrieval Policy hash
```

The default short-hash length is 12 hexadecimal characters.

A Candidate ID changes when:

- candidate membership changes;
- a member Pattern hash changes;
- the retrieval Policy version changes;
- the canonical retrieval Policy content changes.

A Candidate ID does not change merely because:

- an unrelated Pattern is added to the corpus;
- the retrieval script is reformatted without changing Candidate semantics;
- the script execution time changes;
- the source-corpus hash changes while this Candidate remains identical.

Candidate objects are immutable.

When the same Candidate ID and Candidate group hash already exist, the
candidate-retrieval script reuses the existing Candidate object rather than
writing another copy.

A Candidate ID must not contain a semantic Family name because the candidate
has not yet been accepted or interpreted as a Family.

## 4. Top-level Structure

```json
{
  "manifest_version": "1.1",

  "metadata": {
    "candidate_group_id": "pfc_pt_a13f09c2e641",
    "candidate_group_hash": "sha256:...",
    "candidate_purpose": "family_analysis_input",
    "candidate_status": "retrieved_candidate",
    "framework": "pytorch"
  },

  "generation_information": {
    "method": "deterministic_field_based_retrieval",
    "retrieval_policy_version": "1.1-provisional",
    "retrieval_policy_hash": "sha256:...",
    "script_version": "build_pattern_family_candidates_v2",
    "script_hash": "sha256:...",
    "source_corpus_hash": "sha256:...",
    "generated_at": "2026-08-29T10:30:00Z"
  },

  "members": [],

  "eligibility_summary": {},

  "group_retrieval_signals": {},

  "pairwise_links": [],

  "group_consistency": {},

  "existing_family_matches": [],

  "retrieval_warnings": []
}
```

## 5. Metadata

```json
"metadata": {
  "candidate_group_id": "pfc_pt_a13f09c2e641",
  "candidate_group_hash": "sha256:...",
  "candidate_purpose": "family_analysis_input",
  "candidate_status": "retrieved_candidate",
  "framework": "pytorch"
}
```

| Field | Type | Required | Purpose |
|---|---|---:|---|
| `candidate_group_id` | string | yes | Deterministic Candidate identifier using the `pfc_` prefix. |
| `candidate_group_hash` | string | yes | Full SHA-256 hash of the Candidate semantic payload. |
| `candidate_purpose` | enum | yes | Stable role of this artifact in the pipeline. |
| `candidate_status` | enum | yes | Immutable artifact type/status, not an LLM processing status. |
| `framework` | string | yes | Framework shared by all Candidate members. |

Allowed `candidate_purpose` value for v1.1:

- `family_analysis_input`

Allowed `candidate_status` value for v1.1:

- `retrieved_candidate`

`candidate_status` does not mean:

- pending LLM analysis;
- LLM analysis completed;
- Family accepted;
- Family rejected;
- human reviewed.

Family-analysis and Decision states are stored separately by the Family
conversion stage.

The Candidate group hash uses an explicit semantic-field allowlist containing:

- Manifest version;
- framework;
- retrieval Policy version and canonical Policy hash;
- member Pattern IDs and hashes;
- member APIs and direct Report IDs;
- member validation status;
- normalized retrieval signatures;
- transferability-signal provenance;
- eligibility summary;
- group retrieval signals;
- pairwise links;
- group consistency;
- retrieval warnings.

The Candidate group hash excludes non-semantic or run-specific fields,
including:

- `candidate_group_id`;
- `candidate_group_hash`;
- `candidate_purpose`;
- `candidate_status`;
- script version and script hash;
- source-corpus hash;
- generation time;
- member file paths;
- `existing_family_matches`.

Therefore, an unrelated Pattern added elsewhere in the corpus changes the Run
source-corpus hash but does not change an otherwise identical Candidate group
hash.

`candidate_group_id` is a short deterministic locator.

`candidate_group_hash` is the full semantic identity check.

If an existing Candidate ID resolves to a different Candidate group hash, the
script must stop rather than overwrite the existing file. This indicates a
short-hash collision, an unversioned Policy change, or an implementation error.

## 6. Generation Information

```json
"generation_information": {
  "method": "deterministic_field_based_retrieval",
  "retrieval_policy_version": "1.1-provisional",
  "retrieval_policy_hash": "sha256:...",
  "script_version": "build_pattern_family_candidates_v2",
  "script_hash": "sha256:...",
  "source_corpus_hash": "sha256:...",
  "generated_at": "2026-08-29T10:30:00Z"
}
```

| Field | Type | Required | Purpose |
|---|---|---:|---|
| `method` | enum | yes | Candidate-retrieval method. |
| `retrieval_policy_version` | string | yes | Version of signal and grouping rules. |
| `retrieval_policy_hash` | string | yes | Hash of the canonical retrieval Policy JSON. |
| `script_version` | string | yes | Version of the candidate-generation script. |
| `script_hash` | string | yes | File hash of the exact script used. |
| `source_corpus_hash` | string | yes | Hash of the ordered Pattern ID and Pattern hash inventory for this framework and run. |
| `generated_at` | ISO 8601 datetime | yes | Time at which this Candidate representation was generated. |

Allowed `method` value for v1.1:

- `deterministic_field_based_retrieval`

`retrieval_policy_hash` is calculated from canonical JSON content. Formatting-only
changes to the Policy file therefore do not change this hash.

`script_hash`, `source_corpus_hash`, and `generated_at` are provenance fields.
They do not participate in the Candidate semantic group hash.

When an identical Candidate object already exists, the object is reused. Its
stored generation information describes the run in which that immutable object
was first written. Later appearances of the same object are recorded in later
Candidate Run Indexes.

Embedding- or LLM-based retrieval is not included in v1.1.

## 7. Members

```json
"members": [
  {
    "pattern_id": "pt_matmul_unaligned_storage_p001",
    "pattern_hash": "sha256:...",
    "pattern_relpath": "bug_patterns/torch.matmul/pt_matmul_unaligned_storage_p001.json",
    "primary_api": "torch.matmul",
    "source_report_ids": [
      "pt_report_001"
    ],
    "validation_status": "automatically_validated",

    "retrieval_signature": {
      "primary_defect_class": "memory_layout_boundary",
      "secondary_defect_classes": [],
      "risk_dimensions": [
        "layout",
        "memory"
      ],
      "candidate_family_tags": [
        "storage_sensitive_backend"
      ],
      "trigger_dimensions": [
        "layout"
      ],
      "mechanism_layers": [
        "backend"
      ],
      "failure_types": [
        "crash"
      ],
      "historical_oracle_kinds": [
        "signal"
      ]
    },

    "signal_provenance": {
      "transferability_evidence_status": "analyst_inferred",
      "transferability_confidence": "medium"
    }
  }
]
```

| Field | Type | Required | Purpose |
|---|---|---:|---|
| pattern_id | string | yes | Stable Pattern identifier. |
| pattern_hash | string | yes | Hash of the exact Pattern JSON. |
| pattern_relpath | string | yes | Repository-relative Pattern path; absolute paths are not allowed. |
| primary_api | string | yes | Pattern primary API. |
| source_report_ids | array | yes | Report IDs directly supporting the Pattern. |
| validation_status | enum | yes | Pattern validation status copied from derivation information. |
| retrieval_signature | object | yes | Deterministic normalized fields used for candidate retrieval. |
| signal_provenance | object | yes | Evidence status and confidence associated with transferability-derived signals. |

The `retrieval_signature` object contains:

| Field | Type | Required | Source |
|---|---|---:|---|
| primary_defect_class | string | yes | `defect_classification.primary_defect_class` |
| secondary_defect_classes | array | yes | `defect_classification.secondary_defect_classes` |
| risk_dimensions | array | yes | `defect_classification.risk_dimensions` |
| candidate_family_tags | array | yes | `transferability_hypothesis.candidate_family_tags` |
| trigger_dimensions | array | yes | De-duplicated `trigger_signature.conditions[].dimension` |
| mechanism_layers | array | yes | De-duplicated `defect_mechanism.hypotheses[].layer` |
| failure_types | array | yes | Zero or one non-unknown `observed_failure.failure_type` value |
| historical_oracle_kinds | array | yes | Zero or one non-unknown `observed_failure.historical_oracle.kind` value |

The `signal_provenance` object contains:

| Field | Type | Required | Source |
|---|---|---:|---|
| transferability_evidence_status | enum | yes | `transferability_hypothesis.evidence_status` |
| transferability_confidence | enum | yes | `transferability_hypothesis.confidence` |

Allowed Pattern evidence-status values are inherited from Pattern v2:

- `source_explicit`
- `code_derived`
- `patch_derived`
- `analyst_inferred`
- `unknown`

Allowed confidence values:

- `high`
- `medium`
- `low`

Rules:

- Members must be sorted by `pattern_id`.
- Every Pattern hash must be recomputed from the canonical JSON representation
  of the complete input Pattern record.
- `pattern_relpath` must be relative to the EXP006 directory.
- A Pattern must not be copied into the Manifest in full.
- Only API-specific Pattern v2 records are allowed.
- Only Patterns with `validation_status` equal to `automatically_validated` or
  `human_verified` are eligible.
- Patterns marked `not_reviewed` or `needs_revision` are excluded.
- All members must belong to the same framework.
- Retrieval-signature arrays must be sorted and de-duplicated.
- Unknown failure types, mechanism layers, or Oracle kinds must not be copied
  into retrieval-signature arrays.
- The candidate script must copy or normalize values deterministically and must
  not generate semantic summaries.

## 8. Eligibility Summary

```json
"eligibility_summary": {
  "pattern_count": 3,
  "distinct_api_count": 3,
  "independent_report_count": 3,
  "all_members_api_specific": true,
  "all_members_valid_v2": true,
  "same_framework": true,
  "minimum_pattern_count_met": true,
  "minimum_distinct_api_count_met": true,
  "minimum_independent_report_count_met": true,
  "minimum_candidate_conditions_met": true
}
```

All fields are computed deterministically.

Initial minimum candidate conditions are:

```text
pattern_count >= 2
distinct_api_count >= 2
independent_report_count >= 2
all_members_api_specific = true
all_members_valid_v2 = true
same_framework = true
```

Satisfying these conditions does not mean that a Pattern Family is valid. It
only means that the group is eligible for Family analysis.

## 9. Group Retrieval Signals

```json
"group_retrieval_signals": {
  "shared_primary_defect_class": "memory_layout_boundary",
  "shared_secondary_defect_classes": [],
  "shared_risk_dimensions": [
    "layout"
  ],
  "shared_candidate_family_tags": [
    "storage_sensitive_backend"
  ],
  "shared_trigger_dimensions": [
    "layout"
  ],
  "shared_mechanism_layers": [
    "backend"
  ],
  "shared_failure_types": [],
  "shared_historical_oracle_kinds": []
}
```

Each shared field is the deterministic set intersection across all members.

Rules:

- Use `null` for `shared_primary_defect_class` when members do not all share the same value.
- Use empty arrays when no all-member intersection exists.
- Do not generate a semantic summary from these fields.
- Shared fields are retrieval signals, not Family claims.
- A broad field such as `backend` or `execution` must not alone establish a candidate link.

## 10. Pairwise Links and Signal Policy

```json
"pairwise_links": [
  {
    "left_pattern_id": "pt_conv2d_storage_boundary_p001",
    "right_pattern_id": "pt_matmul_unaligned_storage_p001",

    "exact_matches": {
      "primary_defect_class_match": true,
      "shared_secondary_defect_classes": [],
      "shared_risk_dimensions": [
        "layout",
        "memory"
      ],
      "shared_candidate_family_tags": [
        "storage_sensitive_backend"
      ],
      "shared_trigger_dimensions": [
        "layout"
      ],
      "shared_mechanism_layers": [
        "backend"
      ],
      "shared_failure_types": [
        "crash"
      ],
      "shared_historical_oracle_kinds": [
        "signal"
      ]
    },

    "set_overlap_metrics": {
      "secondary_defect_class_jaccard": null,
      "risk_dimension_jaccard": 0.67,
      "candidate_family_tag_jaccard": 1.0,
      "trigger_dimension_jaccard": 0.5,
      "mechanism_layer_jaccard": 1.0,
      "failure_type_jaccard": 1.0,
      "historical_oracle_kind_jaccard": 1.0
    },

    "signal_classification": {
      "strong_signals": [
        "primary_defect_class_with_shared_risk",
        "supported_family_tag_with_trigger_or_mechanism"
      ],
      "weak_signals": [
        "mechanism_layer_match",
        "failure_type_match"
      ],
      "matched_signal_categories": [
        "classification",
        "risk",
        "transferability",
        "trigger",
        "mechanism",
        "observation"
      ],
      "strong_signal_count": 2,
      "weak_signal_count": 2
    },

    "candidate_link_passed": true
  }
]
```

Each unordered member pair appears exactly once.

`left_pattern_id` must be lexicographically smaller than
`right_pattern_id`.

### 10.1 Set-overlap calculation

Jaccard overlap is calculated as:

```text
size(intersection) / size(union)
```

Use `null` when both sets are empty.

Values are rounded to six decimal places before being written to the Manifest.

No single weighted or aggregate similarity score is stored in Candidate
Manifest v1.

### 10.2 Strong signals

Allowed strong-signal values are:

- `primary_defect_class_with_shared_risk`
- `supported_family_tag_with_trigger_or_mechanism`
- `shared_trigger_with_mechanism`

Their deterministic definitions are:

#### `primary_defect_class_with_shared_risk`

True only when:

```text
primary_defect_class is equal
AND
shared_risk_dimensions is not empty
```

#### `supported_family_tag_with_trigger_or_mechanism`

True only when:

```text
shared_candidate_family_tags is not empty
AND
both Patterns have transferability_evidence_status != unknown
AND
both Patterns have transferability_confidence in {medium, high}
AND
(
  shared_trigger_dimensions is not empty
  OR
  shared_mechanism_layers is not empty
)
```

#### `shared_trigger_with_mechanism`

True only when:

```text
shared_trigger_dimensions is not empty
AND
shared_mechanism_layers is not empty
```

A strong signal is still a retrieval signal. It does not prove that the two
Patterns belong to the same Family.

### 10.3 Weak signals

Allowed weak-signal values are:

- `primary_defect_class_match`
- `secondary_defect_class_match`
- `risk_dimension_match`
- `candidate_family_tag_match`
- `trigger_dimension_match`
- `mechanism_layer_match`
- `failure_type_match`
- `historical_oracle_kind_match`

Weak signals are exact deterministic matches that are insufficient on their own
to establish a candidate link.

Signal categories are:

| Signal | Category |
|---|---|
| primary or secondary defect-class match | `classification` |
| risk-dimension match | `risk` |
| candidate-family-tag match | `transferability` |
| trigger-dimension match | `trigger` |
| mechanism-layer match | `mechanism` |
| failure-type or historical-Oracle-kind match | `observation` |

### 10.4 Candidate-link rule

A pair passes the v1 candidate-link rule when either condition holds:

```text
Condition A:
strong_signal_count >= 1
```

or:

```text
Condition B:
weak_signal_count >= 3
AND
matched signals cover at least two different categories
AND
at least one category is one of:
  classification
  transferability
  trigger
  mechanism
```

Observation-only overlap cannot establish a candidate link.

A matching failure type and historical Oracle kind normally describe the same
observation evidence and must not be treated as two independent semantic
categories.

The link rule is a high-recall retrieval heuristic. Its thresholds must be
evaluated on a small manually reviewed pilot set before large-scale generation.

## 11. Candidate-group Formation and Consistency

### 11.1 Graph construction

For each framework, construct an undirected graph:

```text
node = one eligible API-specific Pattern
edge = candidate_link_passed is true
```

Patterns from the same primary API may have a pairwise link for diagnostic
purposes, but a candidate group is eligible only when it contains at least two
different primary APIs and two independent Report sources.

### 11.2 Initial grouping

Candidate Manifest v1 uses connected components of the candidate-link graph as
high-recall candidate groups.

A connected component is emitted only when it satisfies the minimum eligibility
conditions in Section 8.

Connected components may contain chain drift. The candidate script must record
all passed and failed pairs inside the group so the later Family analysis stage
can split or reject it.

### 11.3 Group consistency structure

```json
"group_consistency": {
  "grouping_method": "connected_components",
  "all_members_share_strong_signal": false,

  "pairwise_link_count": 3,
  "passed_pairwise_link_count": 2,
  "failed_pairwise_link_count": 1,

  "chain_drift_flag": true,

  "member_link_coverage": [
    {
      "pattern_id": "pattern_a",
      "passed_link_count": 2,
      "possible_link_count": 2,
      "link_coverage": 1.0,
      "rule_flagged_outlier": false
    },
    {
      "pattern_id": "pattern_b",
      "passed_link_count": 1,
      "possible_link_count": 2,
      "link_coverage": 0.5,
      "rule_flagged_outlier": false
    },
    {
      "pattern_id": "pattern_c",
      "passed_link_count": 1,
      "possible_link_count": 2,
      "link_coverage": 0.5,
      "rule_flagged_outlier": false
    }
  ],

  "rule_flagged_outlier_pattern_ids": [],

  "rule_detected_subgroups": [
    [
      "pattern_a",
      "pattern_b"
    ],
    [
      "pattern_a",
      "pattern_c"
    ]
  ]
}
```

Rules:

- `pairwise_link_count` equals `n × (n - 1) / 2`.
- `chain_drift_flag` is true when at least one pair inside a connected component
  fails the candidate-link rule.
- `all_members_share_strong_signal` is true only when the same strong-signal
  definition is satisfied across every member.
- `link_coverage` equals passed links divided by `n - 1`.
- For groups of three or more members, a Pattern is rule-flagged as a possible
  outlier when `link_coverage < 0.5`.
- `rule_detected_subgroups` contains connected components of the graph formed
  only by strong-signal edges.
- Subgroups with fewer than two members are omitted.
- Pattern IDs inside subgroups are sorted.
- Duplicate subgroups are removed.
- If a connected component contains more than ten members, add
  `candidate_group_too_large` to `retrieval_warnings`.
- Group-consistency fields are deterministic warnings and are not Family
  membership decisions.

The later LLM stage must evaluate complete Pattern evidence before accepting,
splitting, or rejecting a candidate group.

## 12. Existing Family Matches

```json
"existing_family_matches": []
```

`existing_family_matches` is reserved for a future deterministic matching stage
between newly retrieved Candidate objects and existing human-verified Pattern
Families.

It remains empty in Candidate Manifest v1.1 because:

- v1.1 performs full-corpus Candidate reconstruction;
- v1.1 compares Candidate objects with previous Candidate Runs;
- v1.1 does not compare Candidate objects with accepted Pattern Families;
- automatic Family membership update, merge, and split are not allowed.

Candidate Run comparison and existing-Family matching are different operations.

```text
Candidate Run comparison
    compares Candidate objects across retrieval runs

Existing-Family matching
    compares Candidate evidence with accepted Pattern Families
```

Future existing-Family matches must be stored in a separate derived artifact or
new versioned structure. An immutable Candidate object must not be edited after
LLM or human Family analysis.

An existing-Family match, if introduced later, remains a retrieval result only.
It must not authorize automatic membership insertion, Family merging, or Family
splitting.

## 13. Retrieval Warnings

Allowed warning values:

- `duplicate_report_source`
- `chain_drift`
- `weak_shared_signal`
- `rule_flagged_outlier`
- `candidate_group_too_large`
- `low_confidence_source_pattern`
- `missing_transferability_evidence`

Example:

```json
"retrieval_warnings": [
  "chain_drift",
  "low_confidence_source_pattern"
]
```

Warnings must use only controlled values. The deterministic candidate script
must not generate free-text warning explanations.

## 14. Validation Rules

A Candidate Manifest is structurally valid only if:

1. `manifest_version` is `1.1`.
2. `candidate_group_id` begins with the Policy-defined `pfc_` framework prefix.
3. `candidate_purpose` is `family_analysis_input`.
4. `candidate_status` is `retrieved_candidate`.
5. `candidate_group_id` can be reproduced from sorted member Pattern IDs,
   sorted member Pattern hashes, retrieval Policy version, and canonical
   retrieval Policy hash.
6. `candidate_group_hash` equals the SHA-256 hash of the explicitly defined
   Candidate semantic payload.
7. Run-specific provenance fields do not participate in
   `candidate_group_hash`.
8. All member Pattern IDs and hashes resolve to existing Pattern JSON files.
9. All member Patterns are API-specific Pattern v2 records.
10. All members belong to the declared framework.
11. Every member has `automatically_validated` or `human_verified` status.
12. Members are sorted and contain no duplicate Pattern IDs.
13. Retrieval signatures exactly match deterministically normalized Pattern
    fields.
14. At least two Patterns, two distinct APIs, and two independent Report
    sources exist.
15. Every unordered member pair appears exactly once in `pairwise_links`.
16. Pairwise counts match `n × (n - 1) / 2`.
17. Shared group fields equal deterministic intersections across members.
18. Jaccard values can be reproduced and are rounded to six decimal places.
19. Strong and weak signal names use only controlled Policy values.
20. Strong and weak signal counts match their listed values.
21. `candidate_link_passed` matches the Policy candidate-link rule.
22. Candidate groups correspond to connected components of the passed-link
    graph.
23. Chain-drift, link-coverage, outlier, and subgroup fields can be reproduced.
24. All retrieval warnings use controlled Policy values.
25. `existing_family_matches` is empty in Candidate Manifest v1.1.
26. No `change_status`, `analysis_recommended`, previous-Candidate reference,
    Decision-cache state, or LLM execution state appears in the Candidate
    Manifest.
27. No Family name, semantic Family conclusion, General Knowledge, HarnessSpec,
    or LLM-generated interpretation appears in the Candidate Manifest.

Candidate Manifest validation does not determine whether a Candidate forms a
valid Pattern Family.

## 15. Use by the Family Analysis Stage

The Family conversion script reads a Candidate Run Index to select Candidate
objects for analysis.

For each selected Candidate, the script reads the complete immutable Candidate
Manifest and uses it to:

- verify the Candidate ID and Candidate hash;
- locate exact member Pattern IDs and Pattern hashes;
- verify the framework and member ordering;
- inspect deterministic retrieval warnings;
- verify that the Candidate was generated reproducibly.

The complete Candidate Manifest is an input to the conversion script, but it is
not copied directly into the LLM Prompt.

The conversion script constructs a compact Candidate context containing only
the Candidate identity, framework, exact member references, and any
retrieval-warning information required for interpretation.

The LLM receives:

```text
compact Candidate context
+ complete member Pattern JSON records
+ explicitly selected existing Pattern Family revisions
+ pattern_family_extraction_contract.json
+ patterns_to_family_rules.md
```

The LLM does not receive:

- the Candidate Manifest specification document;
- the complete Candidate Run Index;
- unrelated Candidate objects;
- unrelated existing Pattern Families;
- Decision-cache records;
- General Knowledge documents;
- HarnessSpec documents.

Candidate retrieval signals remain retrieval context only. They are not
historical evidence for Family membership or the Family core.

The exact analysis-input hash, Decision-cache compatibility rules, and
immutable Decision format are defined in
`pattern_family_decision_record.md`.

The execution-level selection, reuse, LLM-call, skip, failure, and output
summary are defined in
`pattern_family_conversion_run_index.md`.

The Family conversion stage must not modify:

- an immutable Candidate Manifest;
- an existing Candidate Run Index;
- an existing Decision Record;
- an existing Pattern Family revision.