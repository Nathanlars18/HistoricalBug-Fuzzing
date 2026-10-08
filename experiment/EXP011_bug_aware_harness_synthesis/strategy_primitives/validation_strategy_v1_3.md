# Strategy v1.3 local validation, 2026-10-07

## Scope and preservation

No LLM service was called during this implementation/validation. Real pilot
baseline Plans remain r001; no r002 or Static experimental Plan was created.
Existing HarnessSpec/API/Helper Profile records and unrelated repository edits
were preserved. Catalog v4 is copied intact into catalog_snapshots before v5.
Temporary test Plans/reviews use synthetic test-fixture reviewers and are removed;
they are not human approvals or empirical experiment results.

## Verified

- `python -B -m unittest discover -s experiment/EXP011_bug_aware_harness_synthesis/tests`:
  126 tests, passed.
- Catalog v5 JSON/local-contract validation: passed, 13 primitives;
  canonical content hash `25312b4a2162d17e73c0938e18842487d434ba6b07ebea429888d8bb2fb7c8c5`.
- Real cosine baseline: unchanged implementation passes new semantic checks,
  deterministic CLI adoption and full Artifact source/span/event-map preflight.
- Real batch baseline: old independent rank-2 running stats rejected; a bounded,
  dynamic input with channel-derived rank-1 stats passes, as does explicit None.
- Both approved Static HarnessSpec sources: deterministic test fixtures preserve
  zero/nonzero and equal/mismatched possibilities without ordinary nonempty guards,
  and pass semantic and full materialization checks. These are test fixtures,
  not substitutes for the future LLM-generated Static Plans.
- Regression cases cover original validation-case file/hash (not truncated JSON),
  wrong/middle default omission, optional presence, fixed/degenerate fuzz domains,
  shape correlation, per-phase observations, unsupported forms, return conversion
  gaps, scalar shape checks, preferred versus required checks, external approval
  routing, exact parent repair reviews, and immutable-output refusal.
- Native scalar boundary tests compile and execute signed int64 endpoints,
  multi-byte integer ranges, boolean bit decoding and large finite floating bounds.
- `git diff --check`: passed.

## Pinned-image C++ compile and single-seed smoke

Command: `python -B experiment/EXP011_bug_aware_harness_synthesis/tests/run_strategy_runtime_smoke.py`.

Image: `sha256:10968a7f565bb6c1fa008d3a5800af46a8085de7d880c3db3751c287d29865c8`.

| Fixture | Compile | Process exit | Caught target c10::Error |
| --- | --- | --- | --- |
| batch_norm ordinary dynamic stats | passed | 0 | no |
| cosine ordinary default arguments | passed | 0 | no |
| batch_norm deliberately invalid stats | passed | 0 | yes |
| batch_norm fuzz-selected optional stats | passed | 0 | no |
| cosine explicit float margin / integer reduction | passed | 0 | no |

The invalid-stats fixture exists only to test exception classification; the new
ordinary recipe rejects it. The tests do not establish full API validity,
target-internal code coverage, activation frequency, historical-bug reproduction,
statistical superiority or completeness of the Primitive catalogue. Native
signal/timeout/Sanitizer handling and requested Tensor snapshots still require
separately verified Runner/analysis capabilities. Current Tensor fill is uniform
per Tensor, rank/dtype are constructor-fixed, and unsupported predicate forms or
wrapper/return conversions remain explicit capability gaps.
