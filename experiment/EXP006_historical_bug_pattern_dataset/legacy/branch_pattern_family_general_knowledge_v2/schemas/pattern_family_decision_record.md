# Pattern Family Decision Record Specification v1.0

## 1. Purpose

A Pattern Family Decision Record is an immutable record of one successfully
validated Pattern Family analysis.

One Decision Record corresponds to exactly one semantic analysis input:

```text
one Candidate
+ one explicitly selected existing-Family context
+ one Family Contract version
+ one Family Rules version
+ one rendered Prompt
+ one model configuration
```

It preserves:

- the exact Candidate analyzed;
- the existing Family revisions supplied to the analysis;
- the Contract, Rules, Prompt, and model configuration;
- the resulting Contract-shaped Decision;
- validation provenance;
- the cache key used to avoid repeated LLM calls.

A Decision Record is both:

```text
an auditable analysis artifact
+
a reusable Decision-cache object
```

This specification defines the Decision Record JSON format.

It does not define:

- Candidate retrieval;
- Candidate cross-run comparison;
- existing-Family retrieval algorithms or thresholds;
- conversion-run scheduling;
- formal Family ID or revision allocation;
- final Pattern Family materialization;
- General Knowledge;
- HarnessSpec;
- human review of a final Pattern Family.

---

## 2. Relationship to Other Artifacts

```text
Candidate Manifest
    defines one immutable retrieved Candidate

Candidate Run Index
    records Candidate occurrence and change across retrieval runs

Decision Record
    records one immutable validated analysis result

Conversion Run Index
    records what happened during one conversion-script execution

Pattern Family JSON
    stores one formal materialized Family revision
```

A Decision Record does not replace any of these artifacts.

A Candidate Run ID and `analysis_recommended` are execution-scheduling
information. They do not belong to the semantic Decision-cache key.

Formal Family IDs, revision numbers, output paths, and materialization results
are not stored in a Decision Record.

They are stored in the Conversion Run Index and final Pattern Family
provenance.

---

## 3. Storage and Naming

Decision Records are stored under:

```text
quality/pattern_family_decisions/
└── objects/
    └── <framework>/
        └── <decision_record_id>.json
```

Example:

```text
quality/pattern_family_decisions/
└── objects/
    └── pytorch/
        └── pfd_pt_a13f09c2e641.json
```

Decision Record IDs use:

```text
pfd_{framework_prefix}_{analysis_input_hash_prefix}
```

Example:

```text
pfd_pt_a13f09c2e641
```

The default hash prefix length is 12 hexadecimal characters.

The full `analysis_input_hash` remains stored in the record.

If an existing short ID resolves to a different full hash, the script must stop
with a collision error. It must not overwrite the existing record.

After a validated Decision Record JSON file is written in the project-defined
canonical JSON format, the conversion script calculates its complete file
SHA-256 hash.

This file hash is called:

```text
decision_record_hash
```

`decision_record_hash` is not stored inside the Decision Record itself because
doing so would create a self-referential hash.

Artifacts that reference a Decision Record, including a Conversion Run Index
or final Pattern Family provenance, store:

```text
decision_record_id
decision_record_hash
analysis_input_hash
```

The Decision Record file is immutable after its hash has been calculated.

---

## 4. Representation Conventions

- All top-level fields are required.
- Required arrays remain present when empty.
- Unknown optional scalar values use `null`.
- Empty strings are not allowed.
- Dates use ISO 8601 UTC format.
- Hashes use the `sha256:` prefix.
- IDs and enumerated values are case-sensitive.
- Paths and timestamps do not participate in the analysis-input hash.
- Secret values, API keys, authorization headers, and endpoint credentials must
  never be stored.

Values shown as `null`, `[]`, or `0` below are placeholders, not fixed output
values.

---

## 5. Top-level Structure

```json
{
  "record_version": "1.0",

  "metadata": {
    "decision_record_id": null,
    "framework": null,
    "analysis_input_hash": null
  },

  "analysis_input": {
    "candidate": {
      "candidate_group_id": null,
      "candidate_group_hash": null
    },

    "existing_family_context": {
      "selection_scope": null,
      "selection_policy_version": null,
      "selection_policy_hash": null,
      "context_hash": null,
      "family_revisions": []
    },

    "family_contract": {
      "contract_version": null,
      "contract_hash": null
    },

    "family_rules": {
      "rules_version": null,
      "rules_hash": null
    },

    "prompt": {
      "prompt_version": null,
      "prompt_template_hash": null,
      "rendered_prompt_hash": null
    },

    "model": {
      "provider": null,
      "model": null,
      "configuration": {},
      "configuration_hash": null
    }
  },

  "generation_information": {
    "method": "llm_assisted",
    "conversion_script_version": null,
    "conversion_script_hash": null,
    "generated_at": null,
    "provider_response_id": null,
    "duration_ms": null,

    "token_usage": {
      "input_tokens": null,
      "output_tokens": null,
      "total_tokens": null
    },

    "decision_payload_hash": null
  },

  "decision_payload": {},

  "validation": {
    "status": null,
    "validator_version": null,
    "validator_hash": null,
    "validated_at": null,
    "warnings": []
  }
}
```

---

## 6. Metadata

```json
"metadata": {
  "decision_record_id": "pfd_pt_a13f09c2e641",
  "framework": "pytorch",
  "analysis_input_hash": "sha256:a13f09c2e641..."
}
```

| Field | Type | Required | Description |
|---|---|---:|---|
| `decision_record_id` | string | yes | Content-addressed Decision Record ID. |
| `framework` | string | yes | Framework of the input Candidate. |
| `analysis_input_hash` | string | yes | Full semantic cache-key hash. |

The framework must match:

- the Candidate framework;
- every member Pattern framework;
- every supplied existing Family framework.

---

## 7. Candidate Reference

```json
"candidate": {
  "candidate_group_id": "pfc_pt_123456789abc",
  "candidate_group_hash": "sha256:..."
}
```

The Candidate reference identifies the immutable Candidate content analyzed.

The Decision Record does not repeat:

- Candidate members;
- Candidate pairwise links;
- Candidate retrieval signals;
- Candidate warnings;
- Candidate Run status.

These remain available from the Candidate Manifest identified by the Candidate
ID and hash.

The conversion script must verify the Candidate ID and hash before constructing
the Prompt.

---

## 8. Existing Family Context

```json
"existing_family_context": {
  "selection_scope": "combined",
  "selection_policy_version": "1.0-provisional",
  "selection_policy_hash": "sha256:...",
  "context_hash": "sha256:...",

  "family_revisions": [
    {
      "family_id": "pf_pt_storage_layout_backend_f001",
      "revision": 2,
      "family_hash": "sha256:...",

      "selection_sources": [
        "related_previous_decision",
        "structured_signature_match"
      ]
    }
  ]
}
```

The existing Family context contains only Family revisions explicitly supplied
to the analysis.

Allowed `selection_scope` values are:

- `none_available`
- `related_previous_decisions_only`
- `structured_retrieval`
- `combined`
- `explicit_override`

Allowed `selection_sources` values are:

- `related_previous_decision`
- `member_pattern_overlap`
- `source_report_overlap`
- `structured_signature_match`
- `explicit`

Each Family revision reference contains:

| Field | Type | Required | Description |
|---|---|---:|---|
| `family_id` | string | yes | Stable formal Family identity. |
| `revision` | integer | yes | Exact supplied revision. |
| `family_hash` | string | yes | Exact supplied Family revision hash. |
| `selection_sources` | array | yes | Why this Family entered the context. |

`selection_policy_version` and `selection_policy_hash` identify the
deterministic shortlist policy when structured retrieval is used.

They may be `null` only when `selection_scope` is:

- `none_available`; or
- `explicit_override`.

`context_hash` is calculated from the canonically sorted list of:

```text
family_id
revision
family_hash
```

`selection_sources`, paths, timestamps, and retrieval scores do not participate
in `context_hash` unless they are included in the rendered Prompt.

The LLM may reference only Family IDs listed in `family_revisions`.

An empty context uses:

```json
"existing_family_context": {
  "selection_scope": "none_available",
  "selection_policy_version": null,
  "selection_policy_hash": null,
  "context_hash": "sha256:...",
  "family_revisions": []
}
```

An empty existing Family context does not by itself require
`needs_revision`.

---

## 9. Contract and Rules References

```json
"family_contract": {
  "contract_version": "1.1",
  "contract_hash": "sha256:..."
}
```

```json
"family_rules": {
  "rules_version": "1.1",
  "rules_hash": "sha256:..."
}
```

These references identify the exact Contract and Rules content used to construct
and validate the Decision.

The Decision Record does not copy Contract or Rules text.

The referenced versions and hashes must match the files actually used by the
conversion script.

---

## 10. Prompt Reference

```json
"prompt": {
  "prompt_version": "pattern_family_extract_v1",
  "prompt_template_hash": "sha256:...",
  "rendered_prompt_hash": "sha256:..."
}
```

| Field | Type | Required | Description |
|---|---|---:|---|
| `prompt_version` | string | yes | Prompt-template version. |
| `prompt_template_hash` | string | yes | Hash of the Prompt template. |
| `rendered_prompt_hash` | string | yes | Hash of the final rendered Prompt. |

The rendered Prompt contains:

```text
compact Candidate context
+ validated family-analysis Pattern projections
+ compact semantic projections of selected existing Family revisions
+ Family Contract
+ Family Rules
```

The Decision Record stores only Prompt hashes, not the full Prompt text.

The Prompt must be reproducible from the referenced immutable inputs and Prompt
template.

---

## 11. Model Configuration

```json
"model": {
  "provider": "openai_compatible",
  "model": "model-name",

  "configuration": {
    "temperature": 0,
    "max_output_tokens": 12000,
    "seed": null,
    "response_format": "json_object"
  },

  "configuration_hash": "sha256:..."
}
```

`configuration` stores only non-secret values that can affect the model output.

It must not contain:

- API keys;
- authorization headers;
- endpoint credentials;
- user-account identifiers.

`configuration_hash` is calculated from the canonical JSON representation of:

```text
provider
model
configuration
```

Changing any output-affecting model setting changes the configuration hash and
therefore changes the analysis-input hash.

---

## 12. Analysis-input Hash

`analysis_input_hash` is the SHA-256 hash of the canonical JSON representation
of:

```json
{
  "candidate_group_hash": "sha256:...",
  "existing_family_context_hash": "sha256:...",
  "family_contract_hash": "sha256:...",
  "family_rules_hash": "sha256:...",
  "prompt_version": "pattern_family_extract_v1",
  "prompt_template_hash": "sha256:...",
  "rendered_prompt_hash": "sha256:...",
  "model_configuration_hash": "sha256:..."
}
```

The following do not participate in `analysis_input_hash`:

- Candidate Run ID;
- Candidate change status;
- `analysis_recommended`;
- Candidate file path;
- existing Family file paths;
- generated timestamps;
- conversion-script version or hash;
- provider response ID;
- token usage;
- execution duration;
- Conversion Run ID.

The same semantic analysis input must produce the same
`analysis_input_hash`.

A change to any Prompt-visible Candidate, Pattern, existing Family, Contract,
Rules, Prompt, or model configuration must change the hash.

---

## 13. Generation Information

```json
"generation_information": {
  "method": "llm_assisted",
  "conversion_script_version": "build_pattern_family_json_v1",
  "conversion_script_hash": "sha256:...",
  "generated_at": "2026-08-30T03:30:00Z",
  "provider_response_id": null,
  "duration_ms": 8234,

  "token_usage": {
    "input_tokens": 5200,
    "output_tokens": 1800,
    "total_tokens": 7000
  },

  "decision_payload_hash": "sha256:..."
}
```

Allowed `method` value in Decision Record v1.0:

- `llm_assisted`

Manual correction of a final Family belongs to the Family review process.

A future manual or hybrid Decision workflow requires a new Decision Record
version or an explicitly extended method definition.

`provider_response_id` may be `null` when the provider does not return one.

Token counts may be `null` when the provider does not report them.

When all three token counts are available:

```text
total_tokens = input_tokens + output_tokens
```

`decision_payload_hash` is calculated from the canonical JSON representation of
`decision_payload`.

---

## 14. Decision Payload

`decision_payload` contains the complete validated LLM output.

Its content must conform exactly to:

```text
pattern_family_extraction_contract.json
```

Example boundary:

```json
"decision_payload": {
  "decision": "accept",
  "decision_rationale": "...",
  "decision_evidence_refs": [],
  "proposed_families": [],
  "excluded_patterns": [],
  "unresolved_issues": []
}
```

This document does not redefine:

- Decision values;
- proposed Family fields;
- lineage actions;
- evidence-reference syntax;
- cardinality requirements;
- Pattern membership rules.

Those definitions remain exclusively in:

```text
pattern_family_extraction_contract.json
patterns_to_family_rules.md
```

`reject` and `needs_revision` are valid Decision payloads when they satisfy the
Contract.

A valid `needs_revision` Decision is cacheable. It is reused until one of its
semantic analysis inputs changes.

### 14.1 Proposed Lineage Boundary

Each proposed Family stores its proposed lineage under:

```text
decision_payload.proposed_families[].lineage
```

This lineage is the analysis-stage proposal produced under the Family Contract.

It records:

- whether the proposed Family should create, reuse, update, derive, merge, or
  split a formal Family;
- the supplied existing Family IDs involved in the proposal;
- the rationale for the proposed relationship.

The Decision Record must not duplicate this lineage in another top-level field.

Proposed lineage is not proof that materialization succeeded.

The conversion script must independently validate the proposed lineage before
allocating a Family ID, allocating a revision, or writing a formal Family
artifact.

The actual materialization result is recorded in the Conversion Run Index.

The persisted lineage of a successfully materialized Family is stored in the
final Family's `revision_information`.

---

## 15. Validation

```json
"validation": {
  "status": "passed",
  "validator_version": "pattern_family_decision_validator_v1",
  "validator_hash": "sha256:...",
  "validated_at": "2026-08-30T03:30:02Z",
  "warnings": []
}
```

Allowed `status` values are:

- `passed`
- `passed_with_warnings`

The validator must verify at least:

- top-level Decision Record structure;
- Decision Record ID and analysis-input hash;
- Candidate ID and Candidate hash;
- existing Family IDs, revisions, and hashes;
- Contract and Rules versions and hashes;
- model-configuration hash;
- Decision-payload hash;
- Contract response structure;
- Decision cardinality;
- Pattern membership coverage;
- evidence-reference resolution;
- minimum Pattern, API, and independent Report counts;
- lineage target and parent references;
- confidence and controlled-enum values.

A Decision Record with validation errors must not be written as a completed
Decision-cache object.

Invalid or malformed LLM attempts are recorded only in the corresponding
Conversion Run Index entry.

Warnings must use controlled validator warning values defined by the
implementation.

Validation does not:

- allocate a formal Family ID;
- allocate a Family revision;
- calculate final output paths;
- perform final Family materialization;
- perform human review.

---

## 16. Cache Compatibility

A Decision Record is cache-compatible only when:

1. its full `analysis_input_hash` equals the current calculated hash;
2. its Decision Record ID resolves to that full hash;
3. its validation status is `passed` or `passed_with_warnings`;
4. its Candidate ID and hash resolve correctly;
5. all existing Family revision references still resolve to the recorded
   hashes;
6. its Contract, Rules, Prompt, and model hashes match the current analysis
   input;
7. its `decision_payload_hash` remains valid.

Cache compatibility does not depend on:

- current Candidate Run ID;
- current Candidate change status;
- current `analysis_recommended` value;
- whether the Decision was already reused in another Conversion Run.

A cache-compatible Decision is reused without another LLM call.

A valid cached `reject` or `needs_revision` Decision is reused in the same way
as a valid `accept` or `split` Decision.

---

## 17. Immutability

A completed Decision Record is immutable.

The conversion script must not:

- overwrite an existing Decision Record;
- add a later Conversion Run ID;
- append later Family output references;
- change the Decision after human review;
- update token usage after creation;
- replace an older Decision because a newer model is available.

When an analysis-affecting input changes, the script creates a new
`analysis_input_hash` and therefore a new Decision Record.

A later Decision may supersede an earlier Decision semantically, but it does not
modify or delete the earlier record.

---

## 18. Excluded Information

A Decision Record must not contain:

- complete Candidate Manifest content;
- complete Pattern JSON content;
- complete existing Family JSON content;
- complete Contract or Rules text;
- full Prompt text;
- raw Issue content;
- API keys or credentials;
- Candidate cross-run comparison state;
- Conversion Run summaries;
- formal Family output paths;
- formal Family revision allocation results;
- General Knowledge;
- HarnessSpec;
- Harness code;
- human-review notes for a final Family.

These remain in their owning artifacts.

---

## 19. Use by the Conversion Stage

---

## 20. Minimum Validation Checklist

A Decision Record is valid only if:

1. `record_version` is `1.0`;
2. the Decision Record ID uses the framework-specific prefix;
3. the full analysis-input hash can be reproduced;
4. the Candidate ID and hash resolve;
5. the existing Family context hash can be reproduced;
6. every existing Family reference resolves;
7. Contract and Rules versions and hashes resolve;
8. Prompt and model-configuration hashes can be reproduced;
9. `decision_payload` conforms to the Family Contract;
10. `decision_payload_hash` can be reproduced;
11. validation status is `passed` or `passed_with_warnings`;
12. token arithmetic is valid when token counts are available;
13. no forbidden secret or unrelated artifact content is present;
14. no existing immutable artifact was modified.