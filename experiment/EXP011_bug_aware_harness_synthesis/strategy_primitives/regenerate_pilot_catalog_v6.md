# Strategy Catalog v6 pilot regeneration

Run from `/home/nathan/HistoricalBug-Fuzzing`. Catalog v6 adds bounded rank
selection, a reference `drop_last_dimension` transform, and a source-backed
auxiliary-rank mask check. HarnessSpecs, API Profiles and Helper Profiles are
unchanged. Baseline and batch Static use deterministic adoption without an LLM;
only cosine Static requires one constrained LLM regeneration.

```bash
cd /home/nathan/HistoricalBug-Fuzzing
exp011_root=experiment/EXP011_bug_aware_harness_synthesis

batch_baseline_parent="$exp011_root/strategy_primitives/plans/pytorch/torch_batch_norm_update_stats/controlled_baseline/st_hs_pytorch_torch_batch_norm_update_stats_controlled_baseline_hsr004_r002.json"
cosine_baseline_parent="$exp011_root/strategy_primitives/plans/pytorch/torch_nn_functional_cosine_embedding_loss/controlled_baseline/st_hs_pytorch_torch_nn_functional_cosine_embedding_loss_controlled_baseline_hsr003_r002.json"

.venv/bin/python -B "$exp011_root/scripts/build_strategy_plan_json.py" \
  --harness-spec "$exp011_root/harness_specs/pytorch/torch.batch_norm_update_stats/controlled_baseline/hs_pytorch_torch.batch_norm_update_stats_controlled_baseline_r4.json" \
  --harness-spec-review "$exp011_root/harness_spec_reviews/pytorch/torch.batch_norm_update_stats/controlled_baseline/hs_pytorch_torch.batch_norm_update_stats_controlled_baseline_r4__review_r1.json" \
  --parent-strategy "$batch_baseline_parent" --strategy-revision 3 \
  --revision-trigger catalog_update --adopt-parent

.venv/bin/python -B "$exp011_root/scripts/build_strategy_plan_json.py" \
  --harness-spec "$exp011_root/harness_specs/pytorch/torch.nn.functional.cosine_embedding_loss/controlled_baseline/hs_pytorch_torch.nn.functional.cosine_embedding_loss_controlled_baseline_r3.json" \
  --harness-spec-review "$exp011_root/harness_spec_reviews/pytorch/torch.nn.functional.cosine_embedding_loss/controlled_baseline/hs_pytorch_torch.nn.functional.cosine_embedding_loss_controlled_baseline_r3__review_r1.json" \
  --parent-strategy "$cosine_baseline_parent" --strategy-revision 3 \
  --revision-trigger catalog_update --adopt-parent
```

Preflight and inspect both immutable r003 Plans. Approval remains a human act:

```bash
batch_baseline_plan="$exp011_root/strategy_primitives/plans/pytorch/torch_batch_norm_update_stats/controlled_baseline/st_hs_pytorch_torch_batch_norm_update_stats_controlled_baseline_hsr004_r003.json"
cosine_baseline_plan="$exp011_root/strategy_primitives/plans/pytorch/torch_nn_functional_cosine_embedding_loss/controlled_baseline/st_hs_pytorch_torch_nn_functional_cosine_embedding_loss_controlled_baseline_hsr003_r003.json"

.venv/bin/python -B "$exp011_root/scripts/build_harness_artifact.py" \
  --strategy-plan "$batch_baseline_plan" --strategy-plan "$cosine_baseline_plan" \
  --preflight-only

.venv/bin/python -B "$exp011_root/scripts/review_strategy_plan.py" \
  --strategy-plan "$batch_baseline_plan" --decision approved --reviewer nathan
.venv/bin/python -B "$exp011_root/scripts/review_strategy_plan.py" \
  --strategy-plan "$cosine_baseline_plan" --decision approved --reviewer nathan
```

Do not run the approval commands before inspection. After approval, use the
review paths below; review directories preserve dotted Python API names.

```bash
batch_baseline_review="$exp011_root/strategy_plan_reviews/pytorch/torch.batch_norm_update_stats/controlled_baseline/st_hs_pytorch_torch_batch_norm_update_stats_controlled_baseline_hsr004_r3__review_r1.json"
cosine_baseline_review="$exp011_root/strategy_plan_reviews/pytorch/torch.nn.functional.cosine_embedding_loss/controlled_baseline/st_hs_pytorch_torch_nn_functional_cosine_embedding_loss_controlled_baseline_hsr003_r3__review_r1.json"
batch_static_parent="$exp011_root/strategy_primitives/plans/pytorch/torch_batch_norm_update_stats/bug_aware_static/st_hs_pytorch_torch_batch_norm_update_stats_bug_aware_static_hsr006_r001.json"
cosine_static_parent="$exp011_root/strategy_primitives/plans/pytorch/torch_nn_functional_cosine_embedding_loss/bug_aware_static/st_hs_pytorch_torch_nn_functional_cosine_embedding_loss_bug_aware_static_hsr004_r001.json"

.venv/bin/python -B "$exp011_root/scripts/review_strategy_plan.py" \
  --strategy-plan "$cosine_static_parent" --decision needs_revision --reviewer nathan \
  --finding-json '{"criterion_id":"SR-09","severity":"blocking","field_path":"$.implementation_plan.branch_strategies[1].steps[2]","evidence_ref":"https://github.com/pytorch/pytorch/blob/449b1768410104d3ed79d3bcfe4ba1d65c7f22c0/aten/src/ATen/native/Loss.cpp","mismatch_summary":"The knowledge branch constructs rank-1 input tensors and a rank-1 target. At the pinned source revision, a rank-1 target requires rank-2 inputs, so every generated call is rejected by this auxiliary relation before the intended input1/input2 shape relation can be exercised. Regenerate with bounded independent input ranks and a source-backed compatible target relation; do not fix a historical trigger."}'

cosine_static_review="$exp011_root/strategy_plan_reviews/pytorch/torch.nn.functional.cosine_embedding_loss/bug_aware_static/st_hs_pytorch_torch_nn_functional_cosine_embedding_loss_bug_aware_static_hsr004_r1__review_r1.json"

.venv/bin/python -B "$exp011_root/scripts/build_strategy_plan_json.py" \
  --harness-spec "$exp011_root/harness_specs/pytorch/torch.batch_norm_update_stats/bug_aware_static/hs_pytorch_torch.batch_norm_update_stats_bug_aware_static_r6.json" \
  --harness-spec-review "$exp011_root/harness_spec_reviews/pytorch/torch.batch_norm_update_stats/bug_aware_static/hs_pytorch_torch.batch_norm_update_stats_bug_aware_static_r6__review_r1.json" \
  --canonical-default-strategy "$batch_baseline_plan" \
  --canonical-default-strategy-review "$batch_baseline_review" \
  --parent-strategy "$batch_static_parent" --strategy-revision 2 \
  --revision-trigger catalog_update --adopt-parent

.venv/bin/python -B "$exp011_root/scripts/build_strategy_plan_json.py" \
  --harness-spec "$exp011_root/harness_specs/pytorch/torch.nn.functional.cosine_embedding_loss/bug_aware_static/hs_pytorch_torch.nn.functional.cosine_embedding_loss_bug_aware_static_r4.json" \
  --harness-spec-review "$exp011_root/harness_spec_reviews/pytorch/torch.nn.functional.cosine_embedding_loss/bug_aware_static/hs_pytorch_torch.nn.functional.cosine_embedding_loss_bug_aware_static_r4__review_r1.json" \
  --canonical-default-strategy "$cosine_baseline_plan" \
  --canonical-default-strategy-review "$cosine_baseline_review" \
  --parent-strategy "$cosine_static_parent" --strategy-review "$cosine_static_review" \
  --strategy-revision 2 --revision-trigger catalog_update \
  --model deepseek-v4-pro --max-attempts 3
```

Finally run `build_harness_artifact.py --preflight-only` on both new Static
Plans, inspect them under Human Review Rules v1.2, and create separate approved
review records only if no blocking finding remains. Builder success is machine
validation, not human approval or evidence of detection effectiveness.
