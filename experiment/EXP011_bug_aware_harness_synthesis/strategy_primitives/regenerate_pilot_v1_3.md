# Strategy v1.3 pilot regeneration

Run from `/home/nathan/HistoricalBug-Fuzzing`. Existing r001 Plans and all
HarnessSpecs/API/Helper Profiles stay unchanged. Catalog v4 is preserved under
catalog_snapshots. These commands create r002 baseline Plans with Catalog v5;
they do not regenerate HarnessSpec or API Profile.

## 1. Generate/revalidate baseline

Batch's old independent rank-2 running statistics do not match the ordinary
constructor recipe. Regenerate it through the constrained LLM builder. Cosine's
old implementation passes the new checks; adopt it deterministically to avoid
an unnecessary LLM call. Both produce a new immutable subject that needs review.

```bash
cd /home/nathan/HistoricalBug-Fuzzing
exp011_root=experiment/EXP011_bug_aware_harness_synthesis

.venv/bin/python -B "$exp011_root/scripts/build_strategy_plan_json.py" \
  --harness-spec "$exp011_root/harness_specs/pytorch/torch.batch_norm_update_stats/controlled_baseline/hs_pytorch_torch.batch_norm_update_stats_controlled_baseline_r4.json" \
  --harness-spec-review "$exp011_root/harness_spec_reviews/pytorch/torch.batch_norm_update_stats/controlled_baseline/hs_pytorch_torch.batch_norm_update_stats_controlled_baseline_r4__review_r1.json" \
  --parent-strategy "$exp011_root/strategy_primitives/plans/pytorch/torch_batch_norm_update_stats/controlled_baseline/st_hs_pytorch_torch_batch_norm_update_stats_controlled_baseline_hsr004_r001.json" \
  --strategy-revision 2 --revision-trigger catalog_update \
  --model deepseek-v4-pro --max-attempts 3

.venv/bin/python -B "$exp011_root/scripts/build_strategy_plan_json.py" \
  --harness-spec "$exp011_root/harness_specs/pytorch/torch.nn.functional.cosine_embedding_loss/controlled_baseline/hs_pytorch_torch.nn.functional.cosine_embedding_loss_controlled_baseline_r3.json" \
  --harness-spec-review "$exp011_root/harness_spec_reviews/pytorch/torch.nn.functional.cosine_embedding_loss/controlled_baseline/hs_pytorch_torch.nn.functional.cosine_embedding_loss_controlled_baseline_r3__review_r1.json" \
  --parent-strategy "$exp011_root/strategy_primitives/plans/pytorch/torch_nn_functional_cosine_embedding_loss/controlled_baseline/st_hs_pytorch_torch_nn_functional_cosine_embedding_loss_controlled_baseline_hsr003_r001.json" \
  --strategy-revision 2 --revision-trigger catalog_update --adopt-parent
```

Append `--dry-run` to either command for input/capability/prompt preflight without
LLM calls or Plan creation. An existing r002 is never overwritten; for another
revision explicitly name the immediately preceding parent and next revision.

## 2. Full local source preflight and human review

```bash
batch_baseline_plan="$exp011_root/strategy_primitives/plans/pytorch/torch_batch_norm_update_stats/controlled_baseline/st_hs_pytorch_torch_batch_norm_update_stats_controlled_baseline_hsr004_r002.json"
cosine_baseline_plan="$exp011_root/strategy_primitives/plans/pytorch/torch_nn_functional_cosine_embedding_loss/controlled_baseline/st_hs_pytorch_torch_nn_functional_cosine_embedding_loss_controlled_baseline_hsr003_r002.json"

.venv/bin/python -B "$exp011_root/scripts/build_harness_artifact.py" \
  --strategy-plan "$batch_baseline_plan" \
  --strategy-plan "$cosine_baseline_plan" --preflight-only
```

First inspect both new Plans under Human Review Rules v1.1. In the pilot, review
every Plan. Do not run the following approval commands merely because a Builder
reported success. If blocking findings exist, record needs_revision with concrete
--finding-json evidence and regenerate the next revision using --strategy-review.
For approved, unchanged reviewed subjects only:

```bash
.venv/bin/python -B "$exp011_root/scripts/review_strategy_plan.py" \
  --strategy-plan "$batch_baseline_plan" --decision approved --reviewer nathan
.venv/bin/python -B "$exp011_root/scripts/review_strategy_plan.py" \
  --strategy-plan "$cosine_baseline_plan" --decision approved --reviewer nathan
```

## 3. Generate Static only after baseline approval

Reuse the exact approved baseline implementation. Do not independently generate
a second default branch, copy a historical trigger input, or add unsupported
finite-output/exception oracles. The resource policy is shared exactly.

```bash
batch_baseline_review="$exp011_root/strategy_plan_reviews/pytorch/torch.batch_norm_update_stats/controlled_baseline/st_hs_pytorch_torch_batch_norm_update_stats_controlled_baseline_hsr004_r2__review_r1.json"
cosine_baseline_review="$exp011_root/strategy_plan_reviews/pytorch/torch.nn.functional.cosine_embedding_loss/controlled_baseline/st_hs_pytorch_torch_nn_functional_cosine_embedding_loss_controlled_baseline_hsr003_r2__review_r1.json"

.venv/bin/python -B "$exp011_root/scripts/build_strategy_plan_json.py" \
  --harness-spec "$exp011_root/harness_specs/pytorch/torch.batch_norm_update_stats/bug_aware_static/hs_pytorch_torch.batch_norm_update_stats_bug_aware_static_r6.json" \
  --harness-spec-review "$exp011_root/harness_spec_reviews/pytorch/torch.batch_norm_update_stats/bug_aware_static/hs_pytorch_torch.batch_norm_update_stats_bug_aware_static_r6__review_r1.json" \
  --canonical-default-strategy "$batch_baseline_plan" \
  --canonical-default-strategy-review "$batch_baseline_review" \
  --model deepseek-v4-pro --max-attempts 3

.venv/bin/python -B "$exp011_root/scripts/build_strategy_plan_json.py" \
  --harness-spec "$exp011_root/harness_specs/pytorch/torch.nn.functional.cosine_embedding_loss/bug_aware_static/hs_pytorch_torch.nn.functional.cosine_embedding_loss_bug_aware_static_r4.json" \
  --harness-spec-review "$exp011_root/harness_spec_reviews/pytorch/torch.nn.functional.cosine_embedding_loss/bug_aware_static/hs_pytorch_torch.nn.functional.cosine_embedding_loss_bug_aware_static_r4__review_r1.json" \
  --canonical-default-strategy "$cosine_baseline_plan" \
  --canonical-default-strategy-review "$cosine_baseline_review" \
  --model deepseek-v4-pro --max-attempts 3
```

Repeat local preflight and human review for Static before Artifact production.
Actual Artifact production requires `--strategy-review` pointing to the exact
approved new subject; optionally supply
`--compile-config runtime/flashfuzz_2_10/harness_compile_profile.json`.
Preflight does not compile. Caught API errors, native crashes, timeout and
Sanitizer evidence must be distinguished by the execution/analysis stages. A
Runner binding is not proof that every requested Tensor snapshot was captured.

## Local verification without an LLM

```bash
.venv/bin/python -B -m unittest discover \
  -s experiment/EXP011_bug_aware_harness_synthesis/tests
.venv/bin/python -B experiment/EXP011_bug_aware_harness_synthesis/tests/run_strategy_runtime_smoke.py
```

The second command requires the existing pinned Docker image. Temporary
fixtures are removed automatically; no approval or experimental Plan is created.
It checks two ordinary constructors, optional presence, float/integer arguments
and one deliberately invalid stats fixture for exception classification. It is
not a historical-bug reproduction or a statistical detection experiment.
