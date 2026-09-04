# Pattern Family Candidate Run Index v1.0

## 1. Purpose

A Pattern Family Candidate Run Index is an immutable deterministic artifact
describing one complete Candidate-retrieval run for one framework.

It records:

- the eligible Pattern corpus used in the Run;
- the Candidate objects appearing in the Run;
- Candidate changes relative to a previous Run;
- Candidates recommended for later Family analysis;
- previous Candidates that were retired or superseded.

The two Candidate artifacts have different responsibilities:

```text
Candidate Manifest
    = immutable content of one Candidate group

Candidate Run Index
    = occurrence and cross-run relationship of Candidate groups
```

A Run Index does not contain:

- LLM output;
- Decision-cache state;
- Family acceptance or rejection;
- human-review results;
- Pattern Family semantic content.

This document is human-readable. It is not included in an LLM Prompt and is
not read as an input by the Candidate-retrieval script.

---

## 2. Storage and Naming

Run Indexes are stored under:

```text
quality/pattern_family_candidates/
└── runs/
    └── <framework>/
        └── <run_id>/
            └── candidate_run_index.json
```

Example:

```text
quality/pattern_family_candidates/
└── runs/
    └── pytorch/
        ├── pfcr_pt_000001/
        │   └── candidate_run_index.json
        └── pfcr_pt_000002/
            └── candidate_run_index.json
```

Run IDs use:

```text
pfcr_{framework_prefix}_{six_digit_sequence}
```

Examples:

```text
pfcr_pt_000001
pfcr_pt_000002
pfcr_tf_000001
```

The sequence is maintained independently for each framework.

A Run ID is not a Candidate revision or Pattern Family revision.

A dry run does not consume a Run ID.

---

## 3. Top-level Structure

```json
{
  "run_version": "1.0",

  "metadata": {
    "run_id": "pfcr_pt_000003",
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

  "comparison": {
    "comparison_mode": "latest_previous_run",
    "previous_run_id": "pfcr_pt_000002",
    "policy_compatible": true
  },

  "summary": {
    "eligible_pattern_count": 20,
    "candidate_count": 4,
    "analysis_recommended_count": 1,

    "change_status_counts": {
      "new": 0,
      "unchanged": 3,
      "changed": 0,
      "expanded": 1,
      "contracted": 0,
      "merged_component": 0,
      "split_component": 0
    },

    "retired_candidate_count": 0,
    "superseded_candidate_count": 1
  },

  "candidates": [],

  "retired_candidate_ids": [],

  "superseded_candidate_ids": []
}
```

All top-level fields are required.

Arrays remain present when empty.

Unknown scalar values use `null`.

Empty strings are not allowed.

---

## 4. Metadata and Generation Information

### 4.1 Metadata

```json
"metadata": {
  "run_id": "pfcr_pt_000003",
  "framework": "pytorch"
}
```

| Field | Type | Required | Purpose |
|---|---|---:|---|
| `run_id` | string | yes | Identifier of this immutable Candidate Run. |
| `framework` | string | yes | Framework processed in this Run. |

A Run Index is written only after Candidate construction, Candidate-object
verification, and cross-run comparison complete successfully.

If execution fails, no completed Run Index is written.

### 4.2 Generation Information

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
| `retrieval_policy_version` | string | yes | Retrieval Policy version. |
| `retrieval_policy_hash` | string | yes | Canonical retrieval Policy hash. |
| `script_version` | string | yes | Candidate-retrieval script version. |
| `script_hash` | string | yes | Exact script file hash. |
| `source_corpus_hash` | string | yes | Hash of eligible Pattern IDs and Pattern hashes. |
| `generated_at` | datetime | yes | Run completion time in UTC. |

Allowed `method` value:

- `deterministic_field_based_retrieval`

The source-corpus hash is calculated independently for each framework.

A source-corpus change does not automatically mean that every Candidate
changed.

---

## 5. Comparison

```json
"comparison": {
  "comparison_mode": "latest_previous_run",
  "previous_run_id": "pfcr_pt_000002",
  "policy_compatible": true
}
```

| Field | Type | Required | Purpose |
|---|---|---:|---|
| `comparison_mode` | enum | yes | How the previous Run was selected. |
| `previous_run_id` | string or null | yes | Run used as the comparison baseline. |
| `policy_compatible` | boolean or null | yes | Whether current and previous Policy version and hash match. |

Allowed `comparison_mode` values:

- `latest_previous_run`
- `explicit_previous_run`
- `none`

For the first Run:

```json
"comparison": {
  "comparison_mode": "none",
  "previous_run_id": null,
  "policy_compatible": null
}
```

`policy_compatible` is true only when both Runs use the same:

```text
retrieval_policy_version
retrieval_policy_hash
```

A Candidate cannot be classified as `unchanged` across Policy-incompatible
Runs.

---

## 6. Summary

```json
"summary": {
  "eligible_pattern_count": 20,
  "candidate_count": 4,
  "analysis_recommended_count": 1,

  "change_status_counts": {
    "new": 0,
    "unchanged": 3,
    "changed": 0,
    "expanded": 1,
    "contracted": 0,
    "merged_component": 0,
    "split_component": 0
  },

  "retired_candidate_count": 0,
  "superseded_candidate_count": 1
}
```

All `change_status_counts` keys remain present, including zero-valued keys.

The following equalities must hold:

```text
candidate_count
=
sum(change_status_counts values)
```

```text
analysis_recommended_count
=
number of current Candidates with analysis_recommended = true
```

```text
retired_candidate_count
=
length(retired_candidate_ids)
```

```text
superseded_candidate_count
=
length(superseded_candidate_ids)
```

A valid Run may contain zero Candidate groups.

---

## 7. Candidate Entries

Each current Candidate uses:

```json
{
  "candidate_group_id": "pfc_pt_a13f09c2e641",
  "candidate_group_hash": "sha256:...",

  "candidate_object_relpath": "objects/pytorch/pfc_pt_a13f09c2e641.json",

  "member_pattern_ids": [
    "pt_conv2d_storage_boundary_p001",
    "pt_matmul_unaligned_storage_p001"
  ],

  "change_status": "expanded",

  "related_previous_candidate_ids": [
    "pfc_pt_17a91cb6e229"
  ],

  "analysis_recommended": true
}
```

| Field | Type | Required | Purpose |
|---|---|---:|---|
| `candidate_group_id` | string | yes | Current Candidate object ID. |
| `candidate_group_hash` | string | yes | Full Candidate semantic hash. |
| `candidate_object_relpath` | string | yes | Output-root-relative Candidate path. |
| `member_pattern_ids` | array | yes | Sorted current member Pattern IDs. |
| `change_status` | enum | yes | Relationship to the previous Run. |
| `related_previous_candidate_ids` | array | yes | Previous Candidates involved in the relationship. |
| `analysis_recommended` | boolean | yes | Structural recommendation for later analysis. |

The Candidate Manifest remains the authoritative source for:

- member Pattern hashes;
- member APIs and Report IDs;
- retrieval signatures;
- pairwise links;
- group consistency;
- retrieval warnings.

The Run Index does not duplicate those fields.

---

## 8. Change-status Rules

Allowed current Candidate statuses are:

| Status | Deterministic condition | Analysis recommended |
|---|---|---:|
| `new` | No member-ID overlap with any previous Candidate. | yes |
| `unchanged` | Policy-compatible and Candidate group hash is identical. | no |
| `changed` | One previous Candidate overlaps, but no exact subset, split, merge, or unchanged relation applies. | yes |
| `expanded` | One previous member set is a strict subset of the current member set. | yes |
| `contracted` | Current member set is a strict subset of one previous member set. | yes |
| `merged_component` | One current Candidate overlaps two or more previous Candidates. | yes |
| `split_component` | One previous Candidate overlaps two or more current Candidates. | yes |

Change classification uses:

```text
current and previous member Pattern-ID sets
+ current and previous Candidate group hashes
+ Policy compatibility
```

Important cases:

- Same member IDs with a different Candidate hash are `changed`.
- A member Pattern content change may produce `changed` even when its Pattern ID
  remains the same.
- `merged_component` takes precedence when one current Candidate overlaps
  multiple previous Candidates.
- `split_component` is used when one current Candidate overlaps one previous
  Candidate, but that previous Candidate overlaps multiple current Candidates.
- Merge and split statuses describe graph changes only. They do not authorize
  semantic Pattern Family merge or split.

---

## 9. Retired and Superseded Candidates

A previous Candidate is `retired` when it has no member Pattern-ID overlap with
any current Candidate.

Retired IDs are stored in:

```json
"retired_candidate_ids": []
```

A previous Candidate is `superseded` when it overlaps one or more changed
current Candidates and is not reused unchanged.

Superseded IDs are stored in:

```json
"superseded_candidate_ids": []
```

Retired and superseded Candidate objects are not deleted or modified.

The two ID arrays must not overlap.

Candidate retirement or supersession does not automatically invalidate or
revise an accepted Pattern Family.

---

## 10. Analysis Recommendation Boundary

`analysis_recommended` is produced only from deterministic Candidate change
status.

It does not mean:

- that an LLM has or has not run;
- that an LLM call is definitely required;
- that a compatible cached Decision does not exist;
- that an existing Pattern Family must change.

The Family conversion script evaluates Decision-cache compatibility
independently from Candidate change status.

The exact analysis-input hash and Decision-cache compatibility rules are
defined only in `pattern_family_decision_record.md`.

The analysis-input hash must account for all semantic inputs that can affect a
Decision, including:

- the Candidate group hash;
- explicitly supplied existing Family revision hashes;
- the Family Contract hash;
- the Family Rules hash;
- the Prompt-template version and hash;
- the model identifier and model configuration.

Therefore:

- a Candidate marked `analysis_recommended = true` may still reuse a compatible
  Decision Record;
- an unchanged Candidate may require new analysis after Contract, Rules,
  Prompt, model-configuration, or existing-Family-context changes;
- Candidate change status alone never determines whether an LLM call occurs.

Decision-cache results are not written into the Candidate Run Index.

They are recorded by the separate Pattern Family conversion stage.

---

## 11. Immutability and Ordering

A Run Index is immutable after creation.

The script must not:

- update a previous Run;
- reset previous change statuses;
- add LLM Decisions;
- add human-review results;
- overwrite an existing Run Index.

Ordering rules:

- Candidate entries are sorted by `candidate_group_id`;
- member Pattern IDs are sorted;
- related previous Candidate IDs are sorted;
- retired Candidate IDs are sorted;
- superseded Candidate IDs are sorted.

A new Run is written even when all Candidates are unchanged.

---

## 12. Validation Rules

A Candidate Run Index is valid only if:

1. `run_version` is `1.0`.
2. Run ID and framework follow the Candidate Policy.
3. Policy, script, and source-corpus hashes are present.
4. first Runs use `comparison_mode = none` and null previous-comparison fields.
5. non-first Runs reference an existing Run for the same framework.
6. `policy_compatible` matches Policy version and hash comparison.
7. every Candidate entry resolves to a Candidate Manifest with matching ID and
   hash.
8. Candidate and member-ID arrays are sorted and contain no duplicates.
9. every change status follows Section 8.
10. every related previous Candidate ID exists in the selected previous Run.
11. every `analysis_recommended` value follows the status table.
12. summary counts match Candidate and lifecycle arrays.
13. retired and superseded arrays do not overlap.
14. no previous Candidate or Run artifact was modified.
15. no LLM Decision, Family claim, or review result appears in the Run Index.

---

## 13. Use Boundary

The Candidate-retrieval script writes the Run Index.

The Family conversion script reads it to:

- locate current Candidate objects;
- inspect deterministic change relationships;
- prioritize analysis;
- establish retrieval provenance.

The Run Index itself is not included in the LLM Prompt.

The generated `candidate_run_index.json` is the machine-readable Run instance.

This Markdown document only defines how that JSON is interpreted and validated.