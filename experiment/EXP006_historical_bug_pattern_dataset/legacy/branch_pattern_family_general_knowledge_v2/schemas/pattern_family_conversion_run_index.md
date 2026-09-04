# Pattern Family Conversion Run Index v1.1

## 1. Purpose

A Pattern Family Conversion Run Index records one complete execution of the
Pattern Family decision and materialization pipeline.

It answers the following questions:

1. Which Candidate Run was used?
2. Which Candidate Groups were selected?
3. Which Candidates reused an existing Decision Record?
4. Which Candidates required a new LLM call?
5. What decision was produced for each Candidate?
6. Which formal Pattern Family artifacts were created, revised, reused, or rejected?
7. Which failures occurred during analysis or materialization?
8. What was the total execution and token cost of the run?

The Conversion Run Index is an orchestration and traceability artifact.

It is not:

- a Candidate Manifest;
- a Candidate Run Index;
- a Pattern Family Decision Record;
- a formal Pattern Family record;
- a human review record;
- a General Knowledge record.

---

## 2. Artifact Boundary

The relevant artifacts have the following responsibilities.

| Artifact | Responsibility |
|---|---|
| Candidate Manifest | Describes one deterministic Candidate Group |
| Candidate Run Index | Describes one Candidate construction run and cross-run changes |
| Decision Record | Stores one validated semantic judgment and its proposed Family payload |
| Formal Pattern Family | Stores one materialized Pattern Family or Family revision |
| Conversion Run Index | Records the execution that connects Candidates, Decisions, and materialized Families |

The Conversion Run Index references the other artifacts by identifier and hash.

It must not copy their complete contents.

---

## 3. Pipeline Position

```text
Candidate Run Index
        |
        v
Enumerate current Candidates
        |
        v
Construct current semantic analysis inputs
        |
        v
Decision-cache and materialization lookup
        |
        +---- complete cache/materialization hit
        |           |
        |           v
        |       No work required
        |
        +---- Decision cache miss
        |           |
        |           v
        |       LLM analysis
        |           |
        |           v
        |       Decision Record
        |
        +---- valid Decision but missing materialization
                    |
                    v
             Reuse Decision Record
                    |
                    v
        Deterministic materialization
                    |
                    v
          Pattern Family JSON
                    |
                    v
        Conversion Run Index

Candidate Run analysis_recommended is a deterministic change hint.
It does not replace the current Decision-cache and materialization checks.

---

## 4. Version

```text
conversion_run_index_version: 1.1
```

This version defines the structure of the generated JSON run index.

The Markdown document is intended for human readers.

The conversion script generates the corresponding JSON artifact.

---

## 5. Identifier and Storage

### 5.1 Conversion Run ID

Required format for v1.1:

```text
pfxr_<framework-prefix>_<six-digit-sequence>
```

Example:

```text
pfxr_pt_000001
```

Where:

- `pfxr` means Pattern Family Conversion Run;
- `pt` means PyTorch;
- the final component is a monotonically increasing run sequence.

This naming rule is mandatory for Conversion Run Index v1.1.

### 5.2 Recommended storage location

```text
quality/
  pattern_family_conversion_runs/
    <framework>/
      <conversion_run_id>/
        conversion_run_index.json
```

Example:

```text
quality/
  pattern_family_conversion_runs/
    pytorch/
      pfxr_pt_000001/
        conversion_run_index.json
```

### 5.3 Lifecycle

A finalized Conversion Run Index is immutable.

A later execution must create a new `conversion_run_id`.

A finalized run must never overwrite an earlier run.

A dry run:

- does not call the LLM;
- does not materialize Family artifacts;
- does not consume a Conversion Run ID;
- does not generate a finalized Conversion Run Index.

Sequence gaps are allowed when a non-dry-run execution fails before finalization.

---

## 6. Top-Level JSON Structure

```json
{
  "conversion_run_index_version": "1.1",
  "metadata": {
    "conversion_run_id": "pfxr_pt_000001",
    "framework": "pytorch",
    "status": "completed"
  },
  "input": {
    "candidate_run": {
      "candidate_run_id": "pfcr_pt_000001",
      "candidate_run_index_hash": "sha256:<candidate-run-index-file-hash>"
    },
    "selection": {
      "mode": "cache_aware",
      "requested_candidate_ids": []
    }
  },
  "configuration": {
    "conversion_script": {
      "version": "1.0",
      "content_hash": "sha256:<script-content-hash>"
    },
    "family_contract": {
      "version": "1.1",
      "content_hash": "sha256:<contract-content-hash>"
    },
    "family_rules": {
      "version": "1.1",
      "content_hash": "sha256:<rules-content-hash>"
    },
    "family_schema": {
      "version": "1.1",
      "content_hash": "sha256:<schema-content-hash>"
    },
    "prompt": {
      "version": "1.0",
      "template_hash": "sha256:<prompt-template-hash>"
    },
    "existing_family_retrieval": {
        "mode": "related_candidate_history","implementation": "script_builtin",
        "version": "builtin-1.0",
        "configuration_hash": "sha256:<retrieval-configuration-hash>"
    },
    "materialization": {
        "implementation": "script_builtin",
        "version": "builtin-1.0",
        "configuration_hash": "sha256:<materialization-configuration-hash>"
    },
    "model": {
      "provider": "openai",
      "model_name": "<model-name>",
      "configuration": {
        "temperature": 0,
        "top_p": 1,
        "max_output_tokens": 12000
      },
      "configuration_hash": "sha256:<model-configuration-hash>"
    },
    "retry_policy": {
      "max_attempts_per_candidate": 2
    }
  },
  "timing": {
    "started_at": "2026-08-30T10:00:00Z",
    "completed_at": "2026-08-30T10:05:00Z",
    "duration_ms": 300000
  },
  "summary": {
    "current_candidate_count": 10,
    "selected_candidate_count": 3,
    "not_selected_candidate_count": 7,
    "completed_candidate_count": 3,
    "failed_candidate_count": 0,
    "decision_record_counts": {
      "generated": 1,
      "reused": 2
    },
    "decision_counts": {
      "accept": 2,
      "split": 0,
      "reject": 1,
      "needs_revision": 0
    },
    "llm_call_count": 1,
    "invalid_attempt_count": 0,
    "token_usage": {
      "input_tokens": 8000,
      "output_tokens": 1200,
      "total_tokens": 9200
    },
    "materialization_counts": {
      "created_new_family": 1,
      "reused_existing_revision": 1,
      "created_new_revision": 0,
      "created_derived_family": 0,
      "created_merged_family": 0,
      "created_split_child": 0,
      "failed": 0
    }
  },
  "candidate_results": [
    {
      "candidate_group_id": "pfc_pt_000001",
      "candidate_group_hash": "sha256:<candidate-group-hash>",
      "selection_reason": "analysis_recommended",
      "processing_status": "completed",
      "decision": {
        "source": "generated",
        "decision_record_id": "pfd_pt_000001",
        "decision_record_hash": "sha256:<decision-record-file-hash>",
        "analysis_input_hash": "sha256:<analysis-input-hash>",
        "decision_value": "accept",
        "llm_call_count": 1,
        "invalid_attempt_count": 0,
        "token_usage": {
          "input_tokens": 8000,
          "output_tokens": 1200,
          "total_tokens": 9200
        }
      },
      "failed_attempts": [],
      "materialization": {
        "status": "succeeded",
        "results": [
          {
            "proposed_family_index": 0,
            "requested_lineage_action": "create_new",
            "outcome": "created_new_family",
            "family_ref": {
              "family_id": "pf_pytorch_shape_boundary",
              "family_revision": 1,
              "family_artifact_hash": "sha256:<family-file-hash>"
            },
            "error_codes": []
          }
        ]
      },
      "errors": []
    }
  ],
  "run_errors": []
}
```

---

## 7. Metadata

### 7.1 `conversion_run_id`

Unique identifier of this Conversion Run.

It must not be reused.

### 7.2 `framework`

Framework processed by the run.

Initial controlled value:

```text
pytorch
```

The value must match the framework of:

- the Candidate Run;
- the referenced Pattern records;
- the referenced Decision Records;
- the generated or reused Pattern Families.

### 7.3 `status`

Allowed values:

| Value | Meaning |
|---|---|
| `completed` | All selected Candidates completed successfully |
| `completed_with_failures` | At least one selected Candidate failed, but the run continued |
| `failed` | The run could not perform meaningful Candidate processing |

A Candidate rejection is not a run failure.

A `reject` or `needs_revision` decision is a valid completed result.

---

## 8. Input Candidate Run

### 8.1 `candidate_run_id`

Identifier of the Candidate Run selected as input.

One Conversion Run processes exactly one Candidate Run.

### 8.2 `candidate_run_index_hash`

Exact SHA-256 hash of the referenced Candidate Run Index JSON file.

The hash protects against silent modification of the input run.

The Conversion Run Index does not copy:

- the full Candidate list;
- Candidate member details;
- Candidate evidence;
- cross-run comparison details.

Those remain in the Candidate Run Index and Candidate Manifests.

---

## 9. Candidate Selection

### 9.1 `selection.mode`

Allowed values:

| Value | Meaning |
|---|---|
| `cache_aware` | Evaluate current Candidates and select only those requiring a new Decision or materialization action. |
| `explicit_candidates` | Process only explicitly requested Candidate IDs. |

`cache_aware` is the default mode.

In `cache_aware` mode, the conversion script evaluates every current Candidate
for:

- current semantic analysis-input hash;
- compatible Decision Record availability;
- previous materialization availability;
- referenced Family artifact integrity.

A Candidate requires processing when:

- no compatible Decision Record exists;
- a valid Decision exists but required materialization is absent;
- a previous materialization reference is incomplete or invalid.

`analysis_recommended` may be used as a processing priority, but it is not the
sole selection condition.

### 9.2 `requested_candidate_ids`

This field is non-empty only when:

```text
selection.mode = explicit_candidates
Otherwise it must be an empty array.
Candidate evaluation and processing order must be deterministic:
candidate_group_id ascending
```
---

## 10. Configuration

The configuration object records the requested run-level configuration.

It does not replace the exact per-decision information stored in a Decision Record.

### 10.1 Script

The conversion script version and content hash support reproducibility.

Timestamps and filesystem paths must not be included in the script content hash.

### 10.2 Contract, Rules, and Schema

The run records:

- Pattern Family extraction contract version and hash;
- Patterns-to-Family rules version and hash;
- final Pattern Family schema version and hash.

The contract and rules guide LLM analysis.

The Family Schema guides deterministic output validation.

### 10.3 Prompt

The prompt entry identifies the prompt template used by the run.

The complete rendered prompt is not stored in the Conversion Run Index.

Exact rendered-prompt information belongs in each newly generated Decision Record.

### 10.4 Existing Family Retrieval

The initial implementation uses deterministic retrieval logic built into the
conversion script.

For v1.1, it first retrieves formal Family revisions directly related to
earlier Decisions or earlier versions of the current Candidate.

The resulting shortlist:

- is constructed in memory;
- is not stored as a separate artifact;
- contains only compact relevant Family projections;
- contributes to the rendered Prompt and `analysis_input_hash`.

The complete Pattern Family corpus must not be included in the LLM Prompt.

A separate retrieval policy file may be introduced later only if multiple
retrieval strategies need to be experimentally compared.

### 10.5 Materialization

The initial materialization logic is implemented directly by the conversion
script.

The Run records:

- the built-in materialization version;
- its deterministic configuration hash;
- actual materialization outcomes.

The built-in implementation controls:

- Family identifier allocation;
- revision allocation;
- output directory rules;
- overwrite prohibition;
- idempotency checks;
- staged validation;
- Candidate-level atomicity.

A separate materialization policy file may be introduced later only if multiple
materialization strategies need to be configured or experimentally compared.

### 10.6 Model

The run stores the non-secret model configuration.

Credentials and API keys must never be recorded.

### 10.7 Retry Policy

`max_attempts_per_candidate` limits LLM calls for one Candidate.

A repair attempt counts as an additional attempt.

Changing the actual prompt, model, contract, rules, or semantic input must
produce a different `analysis_input_hash`.

---

## 11. Timing

All timestamps use UTC ISO 8601 format.

Example:

```text
2026-08-30T10:00:00Z
```

`duration_ms` is the total elapsed time of the run.

It must be greater than or equal to the sum of Candidate processing durations,
because the run can contain validation, indexing, and file operations.

---

## 12. Summary

The summary is a deterministic aggregation of `candidate_results`.

It is not an independent source of truth.

### 12.1 Candidate counts

The following invariant must hold:

```text
current_candidate_count
=
selected_candidate_count
+
not_selected_candidate_count
```

The following invariant must also hold:

```text
selected_candidate_count
=
completed_candidate_count
+
failed_candidate_count
```

### 12.2 Decision Record counts

`generated` counts newly created Decision Records.

`reused` counts valid existing Decision Records reused through
`analysis_input_hash`.

A cache hit must not call the LLM.

### 12.3 Decision counts

Allowed decision values:

```text
accept
split
reject
needs_revision
```

The sum of the decision counts must equal the number of Candidate results that
reference a valid Decision Record.

### 12.4 Token usage

Token usage includes only LLM calls executed during this Conversion Run.

A reused Decision Record contributes zero new tokens.

The summary includes tokens from:

- successful calls;
- invalid JSON responses;
- contract validation failures;
- repair attempts;
- other completed provider responses.

Monetary cost is not stored because pricing can change independently of the run.

### 12.5 Materialization counts

Materialization counts are counts of Family proposal outcomes, not Candidate
counts.

One `split` decision can create multiple `created_split_child` outcomes.

---

## 13. Candidate Result

Each selected Candidate has exactly one result entry.

### 13.1 Candidate reference

The Candidate result stores only:

- `candidate_group_id`;
- `candidate_group_hash`.

It must not copy the complete Candidate Manifest.

The hash must equal the Candidate hash referenced by the input Candidate Run.

### 13.2 `selection_reason`

Allowed values:

| Value | Meaning |
|---|---|
| `decision_cache_miss` | No compatible Decision Record exists for the current semantic input. |
| `materialization_required` | A compatible Decision exists, but required materialization is missing or invalid. |
| `explicit_request` | Selected by an explicit Candidate ID request. |

### 13.3 `processing_status`

Allowed values:

| Value | Meaning |
|---|---|
| `completed` | A valid Decision was obtained and its materialization stage completed |
| `failed` | Analysis or materialization could not complete |

A `reject` decision has:

```text
processing_status = completed
```

---

## 14. Decision Result

### 14.1 `source`

Allowed values:

| Value | Meaning |
|---|---|
| `generated` | A new Decision Record was generated in this run |
| `reused` | An existing compatible Decision Record was reused |
| `unavailable` | No valid Decision Record was obtained |

### 14.2 Decision Record reference

A valid decision stores:

- `decision_record_id`;
- `decision_record_hash`;
- `analysis_input_hash`.

The complete Decision Record is not copied.

### 14.3 `decision_value`

This is a convenience projection for run indexing.

It must exactly equal the decision stored in the referenced Decision Record.

It is not an independent decision source.

When `source = unavailable`, the value must be `null`.

### 14.4 LLM call counts

`llm_call_count` is the number of provider calls performed for this Candidate
during this run.

For a pure cache hit:

```text
llm_call_count = 0
```

### 14.5 Candidate token usage

Candidate token usage aggregates every LLM attempt executed for the Candidate in
this run.

The run summary token counts must equal the sum of all Candidate token counts.

---

## 15. Failed LLM Attempts

`failed_attempts` records only unsuccessful LLM or provider attempts.

It does not repeat the successful response stored through a Decision Record.

Recommended failed-attempt structure:

```json
{
  "attempt_number": 1,
  "failure_kind": "contract_validation_failed",
  "response_hash": "sha256:<response-hash>",
  "error_codes": [
    "missing_required_field"
  ],
  "token_usage": {
    "input_tokens": 8000,
    "output_tokens": 500,
    "total_tokens": 8500
  },
  "duration_ms": 12000
}
```

Allowed initial `failure_kind` values:

```text
invalid_json
contract_validation_failed
provider_error
timeout
```

The raw invalid LLM response is not stored in the Conversion Run Index.

`response_hash` may be `null` when no response was received.

---

## 16. Materialization

### 16.1 Materialization status

Allowed values:

| Value | Meaning |
|---|---|
| `succeeded` | All proposed Family outputs for the Candidate were materialized or safely reused |
| `not_applicable` | The decision was `reject` or `needs_revision` |
| `not_started` | No valid Decision Record was available |
| `failed` | A valid Decision existed, but deterministic materialization failed |

For `reject` and `needs_revision`:

```text
materialization.status = not_applicable
materialization.results = []
```

### 16.2 Proposal index

`proposed_family_index` is the zero-based index of the proposal in:

```text
decision_payload.proposed_families
```

It creates an exact mapping between one proposal and one actual materialization
result.

### 16.3 Requested lineage action

Allowed values must match the extraction contract:

```text
create_new
reuse_existing
update_existing
derive_new
merge_existing
split_existing
```

### 16.4 Materialization outcome

Allowed initial values:

| Value | Meaning |
|---|---|
| `created_new_family` | Created a new independent Family |
| `reused_existing_revision` | Reused an unchanged existing Family revision |
| `created_new_revision` | Created a new revision of an existing Family |
| `created_derived_family` | Created a Family derived from another Family |
| `created_merged_family` | Created a Family by merging existing Families |
| `created_split_child` | Created one child Family from a split operation |
| `failed` | The proposal could not be materialized |

### 16.5 Family reference

A successful result stores:

- stable Family identifier;
- actual Family revision;
- exact Family artifact file hash.

It does not copy the Family JSON.

When `outcome = failed`, `family_ref` must be `null`.

---

## 17. Candidate-Level Atomicity

Materialization is atomic at the Candidate level.

If one Decision proposes multiple Families, such as a `split` decision:

- all proposed Families must pass validation before finalization;
- all output paths must be checked before finalization;
- no existing artifact may be overwritten;
- either all proposals are committed or none are treated as successfully committed.

A partial split must not be reported as successful.

The implementation should stage all Candidate outputs before moving them to
their final locations.

---

## 18. Idempotency

The converter must not create duplicate Family artifacts when the same valid
Decision is processed again.

The initial idempotency key is:

```text
decision_record_hash + proposed_family_index
```

Before materializing a proposal, the converter should:

1. search previous Conversion Run Indexes for the same key;
2. verify that the referenced Family artifact still exists;
3. verify that its artifact hash matches;
4. reuse the existing materialization when all checks pass.

If a previous mapping exists but its Family artifact is missing or has a
different hash, the converter must report an error.

It must not silently create a replacement or overwrite another revision.

The Conversion Run Index therefore also serves as the forward mapping from:

```text
Decision proposal
    ->
actual Pattern Family artifact
```

---

## 19. Errors

### 19.1 Candidate errors

Candidate-level errors use the following structure:

```json
{
  "stage": "materialization",
  "code": "family_validation_failed",
  "message": "Generated Family record failed schema validation.",
  "recoverable": true
}
```

Recommended `stage` values:

```text
candidate_loading
context_retrieval
decision_lookup
llm_analysis
decision_validation
materialization
family_validation
artifact_write
```

Error messages must be concise and must not contain credentials, complete
prompts, or raw provider responses.

### 19.2 Run errors

`run_errors` records errors that affect the complete run.

Example:

```json
{
  "stage": "configuration",
  "code": "contract_hash_mismatch",
  "message": "The configured contract hash does not match the loaded file.",
  "recoverable": false
}
```

A run-level error does not replace Candidate-specific errors.\

### 19.3 Candidate Failure Handling

A Candidate-level failure must not stop the processing of the remaining selected
Candidates.

When one Candidate fails:

1. record the failure in its Candidate result;
2. set its `processing_status` to `failed`;
3. continue processing the remaining Candidates;
4. finalize the run after all selected Candidates have been processed.

If at least one Candidate fails while at least one other Candidate completes,
the final run status must be:

```text
completed_with_failures
A fatal run-level configuration or input error may stop the complete run.
```

---

## 20. Validation Invariants

A valid Conversion Run Index must satisfy all of the following:

1. `conversion_run_id` is unique.
2. The referenced Candidate Run exists.
3. The Candidate Run hash matches the referenced file.
4. Every Candidate result exists in the referenced Candidate Run.
5. Every Candidate ID appears at most once in the run.
6. Candidate processing order is deterministic.
7. A reused Decision Record has a matching `analysis_input_hash`.
8. `decision_value` matches the referenced Decision Record.
9. A generated Decision Record passes Decision Record validation.
10. A successful Family reference points to an existing Family artifact.
11. The Family artifact hash matches the referenced file.
12. A newly materialized Family references the source Decision Record.
13. `proposed_family_index` exists in the source Decision payload.
14. Reject and needs-revision decisions produce no Family artifacts.
15. Candidate count summaries match `candidate_results`.
16. Decision count summaries match Candidate decision values.
17. Token summaries equal the sum of per-Candidate token usage.
18. Materialization summaries match materialization result entries.
19. No existing Candidate, Decision, or Family artifact is overwritten.
20. The finalized Conversion Run Index is immutable.

---

## 21. Information Excluded from the Run Index

The Conversion Run Index must not contain:

- complete Candidate Manifest contents;
- complete source Pattern records;
- complete issue or Bug Report contents;
- complete existing Family records;
- complete Decision payloads;
- complete final Family JSON contents;
- rendered prompts;
- raw successful LLM responses;
- raw invalid LLM responses;
- API credentials;
- human review conclusions;
- General Knowledge outputs.

These belong to their corresponding artifacts.

---

## 22. Human Review Boundary

The Conversion Run Index records automated execution facts.

Human review must be represented separately.

A later review artifact may reference:

- `conversion_run_id`;
- `decision_record_id`;
- `family_id`;
- `family_revision`.

Human review must not mutate the finalized Conversion Run Index.

---

## 23. Minimum Completion Checklist

Before finalizing a Conversion Run Index, verify:

- Candidate Run ID and hash are valid.
- Selection mode is valid.
- Every selected Candidate has one result.
- Decision cache hits were verified by `analysis_input_hash`.
- Newly generated Decision Records passed validation.
- Failed attempts contain no raw LLM responses.
- Decision projections match their Decision Records.
- Materialization followed the configured policy.
- Multi-Family materialization was Candidate-level atomic.
- Family artifact hashes match the generated files.
- No artifact was overwritten.
- Summary counts were recomputed from Candidate results.
- Token totals were recomputed from Candidate results.
- Run status matches the Candidate outcomes.
- The final index is immutable.