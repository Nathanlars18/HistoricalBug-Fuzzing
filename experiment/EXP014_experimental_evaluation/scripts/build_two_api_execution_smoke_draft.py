#!/usr/bin/env python3
"""Create a draft EXP014 matrix for deterministic two-API smoke preparation.

The script reuses exact approved HarnessSpecs/Strategies and creates no model
requests. The output intentionally remains a draft until a human reviews and
freezes the targets, schedule, resource settings, and analysis window.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EXP011 = ROOT / "experiment/EXP011_bug_aware_harness_synthesis"
EXP014 = ROOT / "experiment/EXP014_experimental_evaluation"
sys.path.insert(0, str(EXP014 / "scripts"))
sys.path.insert(0, str(EXP011 / "scripts"))
import run_experiment_matrix as runner  # noqa: E402
from budget_derivation import authorize  # noqa: E402

BASE = EXP014 / "configs/experiment_matrix.json"
TARGETS = EXP014 / "configs/evaluation_target_manifest__two_api_smoke_v002.json"
OUTPUT = EXP014 / "configs/two_api_execution_smoke__draft_v007.json"

APPROVED = {
    "torch.batch_norm_update_stats": {
        "profile": "experiment/EXP011_bug_aware_harness_synthesis/api_profiles/pytorch/v2.10.0/cpu/torch.batch_norm_update_stats/api_profile__aten.batch_norm_update_stats.default__r007.json",
        "knowledge": "experiment/EXP006_historical_bug_pattern_dataset/knowledge_base/v3/torch.batch_norm_update_stats/kn_pt_pv4_empty_input_division_by_zero_in_batch_norm_update_stats_k002.json",
        "groups": {
            "structured_baseline": ("harness_specs/pytorch/torch.batch_norm_update_stats/controlled_baseline/hs_pytorch_torch.batch_norm_update_stats_controlled_baseline_r4.json", "harness_spec_reviews/pytorch/torch.batch_norm_update_stats/controlled_baseline/hs_pytorch_torch.batch_norm_update_stats_controlled_baseline_r4__review_r1.json", "strategy_primitives/plans/pytorch/torch_batch_norm_update_stats/controlled_baseline/st_hs_pytorch_torch_batch_norm_update_stats_controlled_baseline_hsr004_r003.json", "strategy_plan_reviews/pytorch/torch.batch_norm_update_stats/controlled_baseline/st_hs_pytorch_torch_batch_norm_update_stats_controlled_baseline_hsr004_r3__review_r1.json"),
            "bug_aware_static": ("harness_specs/pytorch/torch.batch_norm_update_stats/bug_aware_static/hs_pytorch_torch.batch_norm_update_stats_bug_aware_static_r6.json", "harness_spec_reviews/pytorch/torch.batch_norm_update_stats/bug_aware_static/hs_pytorch_torch.batch_norm_update_stats_bug_aware_static_r6__review_r1.json", "strategy_primitives/plans/pytorch/torch_batch_norm_update_stats/bug_aware_static/st_hs_pytorch_torch_batch_norm_update_stats_bug_aware_static_hsr006_r002.json", "strategy_plan_reviews/pytorch/torch.batch_norm_update_stats/bug_aware_static/st_hs_pytorch_torch_batch_norm_update_stats_bug_aware_static_hsr006_r2__review_r1.json"),
        },
        "corpus": "experiment/EXP014_experimental_evaluation/configs/initial_corpora/torch_batch_norm_update_stats_empty/corpus_manifest.json",
    },
    "torch.nn.functional.cosine_embedding_loss": {
        "profile": "experiment/EXP011_bug_aware_harness_synthesis/api_profiles/pytorch/v2.10.0/cpu/torch.nn.functional.cosine_embedding_loss/api_profile__aten.cosine_embedding_loss.default__r006.json",
        "knowledge": "experiment/EXP006_historical_bug_pattern_dataset/knowledge_base/v3/torch.nn.functional.cosine_embedding_loss/kn_pt_pv4_cosine_embedding_loss_mismatched_dimension_validation_boundary_k001.json",
        "groups": {
            "structured_baseline": ("harness_specs/pytorch/torch.nn.functional.cosine_embedding_loss/controlled_baseline/hs_pytorch_torch.nn.functional.cosine_embedding_loss_controlled_baseline_r3.json", "harness_spec_reviews/pytorch/torch.nn.functional.cosine_embedding_loss/controlled_baseline/hs_pytorch_torch.nn.functional.cosine_embedding_loss_controlled_baseline_r3__review_r1.json", "strategy_primitives/plans/pytorch/torch_nn_functional_cosine_embedding_loss/controlled_baseline/st_hs_pytorch_torch_nn_functional_cosine_embedding_loss_controlled_baseline_hsr003_r003.json", "strategy_plan_reviews/pytorch/torch.nn.functional.cosine_embedding_loss/controlled_baseline/st_hs_pytorch_torch_nn_functional_cosine_embedding_loss_controlled_baseline_hsr003_r3__review_r1.json"),
            "bug_aware_static": ("harness_specs/pytorch/torch.nn.functional.cosine_embedding_loss/bug_aware_static/hs_pytorch_torch.nn.functional.cosine_embedding_loss_bug_aware_static_r4.json", "harness_spec_reviews/pytorch/torch.nn.functional.cosine_embedding_loss/bug_aware_static/hs_pytorch_torch.nn.functional.cosine_embedding_loss_bug_aware_static_r4__review_r1.json", "strategy_primitives/plans/pytorch/torch_nn_functional_cosine_embedding_loss/bug_aware_static/st_hs_pytorch_torch_nn_functional_cosine_embedding_loss_bug_aware_static_hsr004_r002.json", "strategy_plan_reviews/pytorch/torch.nn.functional.cosine_embedding_loss/bug_aware_static/st_hs_pytorch_torch_nn_functional_cosine_embedding_loss_bug_aware_static_hsr004_r2__review_r1.json"),
        },
        "corpus": "experiment/EXP014_experimental_evaluation/configs/initial_corpora/torch_nn_functional_cosine_embedding_loss_empty/corpus_manifest.json",
    },
}


def ref(path: Path) -> dict[str, str]:
    return {"relative_path": path.resolve().relative_to(ROOT).as_posix(), "content_hash": runner.file_hash(path)}


def artifact_binding(path: Path, artifact_id: str, version: int) -> dict:
    record = runner.load_json(path)
    return {"artifact_ref": {"artifact_id": artifact_id, "artifact_version": version,
                              "content_hash": runner.content_hash(record)}, "record_file_ref": ref(path)}


def refresh_file_refs(value):
    if isinstance(value, dict):
        for child in value.values():
            refresh_file_refs(child)
        if isinstance(value.get("relative_path"), str) and isinstance(value.get("content_hash"), str):
            path = runner.repository_path(value["relative_path"])
            value["content_hash"] = runner.file_hash(path)
        if isinstance(value.get("record_file_ref"), dict) and isinstance(value.get("artifact_ref"), dict):
            record_path = runner.repository_path(value["record_file_ref"]["relative_path"])
            value["artifact_ref"]["content_hash"] = runner.content_hash(runner.load_json(record_path))
    elif isinstance(value, list):
        for child in value:
            refresh_file_refs(child)


def build() -> dict:
    matrix = copy.deepcopy(runner.load_json(BASE))
    matrix["matrix_id"] = "pytorch_2_10_two_api_execution_smoke_draft_v007"
    matrix["matrix_revision"] = {"revision_number": 7, "change_reason": "preserve post-start failure timing and diagnostics without misclassifying it as retryable launch failure; retain v002 pair-empty target and human-freeze gate"}
    matrix["lifecycle"] = {"status": "draft", "phase": "execution_smoke_review"}
    matrix["preparation"] = {"mode": "reuse_approved"}
    matrix["inputs"]["shared_artifact_refs"]["knowledge_review_ledger"] = ref(
        ROOT / "experiment/EXP006_historical_bug_pattern_dataset/quality/knowledge_review_ledger.jsonl")
    matrix["inputs"]["shared_file_refs"]["execution_semantics"] = ref(
        EXP014 / "scripts/execution_semantics.py")
    matrix["inputs"]["shared_file_refs"]["round_worker"] = ref(
        EXP014 / "scripts/execution_worker.py")
    matrix["feedback"]["condition_feedback_file_ref"] = ref(
        ROOT / "experiment/EXP012_adaptive_feedback/scripts/condition_feedback.py")
    matrix["feedback"]["protocol_file_ref"] = ref(
        ROOT / "experiment/EXP012_adaptive_feedback/feedback_loop_protocol.md")
    matrix["feedback"]["execution_semantics_file_ref"] = ref(
        EXP014 / "scripts/execution_semantics.py")
    matrix["feedback"]["decision_schema_file_ref"] = ref(
        ROOT / "experiment/EXP012_adaptive_feedback/schemas/feedback_decision_record.schema.json")
    matrix["feedback"]["harness_spec_schema_file_ref"] = ref(
        EXP011 / "schemas/harness_spec_record.schema.json")
    matrix["feedback"]["strategy_schema_file_ref"] = ref(
        EXP011 / "schemas/strategy_plan_record.schema.json")
    matrix["feedback"]["harness_artifact_schema_file_ref"] = ref(
        EXP011 / "schemas/harness_artifact_record.schema.json")
    matrix["api_entries"] = []
    matrix["execution"]["repeat_count"] = 1
    matrix["execution"]["round_count"] = 2
    matrix["execution"]["active_fuzzing_seconds_per_round"] = 15
    matrix["execution"]["resource_limits"] = {"timeout": None, "rss_limit_mb": None, "max_len": None,
        "process_memory_mb": None, "candidate_sample_limit": 64}
    matrix["execution"]["group_order_by_repeat"] = [{"repeat_id": 1, "group_order": ["structured_baseline", "bug_aware_static", "bug_aware_adaptive"]}]
    matrix["feedback"]["decision_after_rounds"] = [1]
    matrix["analysis"]["analysis_cutoff_policy"]["delay_seconds"] = 86400
    matrix["inputs"]["shared_artifact_refs"]["evaluation_target_manifest"] = artifact_binding(
        TARGETS, "etm_pytorch_2_10_two_api_smoke_v002", 2)

    for api, settings in APPROVED.items():
        profile_path = ROOT / settings["profile"]
        profile = runner.load_json(profile_path)
        knowledge_path = ROOT / settings["knowledge"]
        knowledge = runner.load_json(knowledge_path)
        profile_binding = artifact_binding(profile_path, re.sub(r"[^A-Za-z0-9._:-]+", "_", profile["profile_id"]), profile["revision"])
        kb = {"knowledge_id": knowledge["metadata"]["knowledge_id"], "schema_version": knowledge["schema_version"], "file_ref": ref(knowledge_path)}
        corpus_path = ROOT / settings["corpus"]
        entry = {
            "api_id": api, "enabled": True, "target_api": api,
            "target_manifest_entry_id": api,
            "api_profile_binding": profile_binding,
            "compile_profile_file_ref": ref(ROOT / "runtime/flashfuzz_2_10/harness_compile_profile.json"),
            "initial_corpus_binding": artifact_binding(corpus_path, runner.load_json(corpus_path)["identity"]["corpus_id"], 1),
            "knowledge_bindings": [kb],
            "approved_inputs": {},
        }
        spec_hashes = {}
        plan_hashes = {}
        for group, (spec_rel, spec_review_rel, plan_rel, plan_review_rel) in settings["groups"].items():
            spec_path, spec_review = EXP011 / spec_rel, EXP011 / spec_review_rel
            plan_path, plan_review = EXP011 / plan_rel, EXP011 / plan_review_rel
            authorize(spec_review, spec_path, "spec")
            authorize(plan_review, plan_path, "strategy")
            entry["approved_inputs"][group] = {
                "spec_file_ref": ref(spec_path), "spec_review_file_ref": ref(spec_review),
                "strategy_file_ref": ref(plan_path), "strategy_review_file_ref": ref(plan_review),
            }
            spec_hashes[group] = runner.default_branch_spec_hash(spec_path)
            plan_hashes[group] = runner.default_branch_strategy_hash(spec_path, plan_path)
        if spec_hashes["structured_baseline"] != spec_hashes["bug_aware_static"] or plan_hashes["structured_baseline"] != plan_hashes["bug_aware_static"]:
            raise runner.ConfigurationError(f"Approved Static default branch differs from Baseline for {api}")
        matrix["api_entries"].append(entry)

    refresh_file_refs(matrix)
    matrix["unresolved_bindings"] = []
    runner.validate_matrix(matrix)
    runner.verify_declared_file_refs(matrix)
    return matrix


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--operational-smoke", action="store_true",
                        help="Freeze a separate pipeline-only smoke run, not a formal experiment or human artifact approval")
    parser.add_argument("--target-output", type=Path)
    parser.add_argument("--smoke-id", default="pytorch_2_10_operational_smoke_v001")
    parser.add_argument("--analysis-cutoff-delay-seconds", type=int, default=900)
    parser.add_argument("--round-count", type=int, default=2)
    parser.add_argument("--active-seconds", type=int, default=15)
    parser.add_argument("--enable-coverage", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT) or output.exists():
        raise SystemExit("Output must be a new file inside the repository")
    matrix = build()
    if args.round_count < 1 or args.active_seconds < 1:
        raise SystemExit("Round count and active seconds must be positive")
    matrix["execution"]["round_count"] = args.round_count
    matrix["execution"]["active_fuzzing_seconds_per_round"] = args.active_seconds
    matrix["execution"]["thread_environment"] = {
        "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"}
    matrix["feedback"]["decision_after_rounds"] = list(range(1, args.round_count))
    if args.enable_coverage:
        matrix["coverage"].update(enabled=True, replay_after_each_round=True,
                                 scope_file_ref=ref(EXP014 / "configs/coverage_scope_pytorch_2_10.json"),
                                 replay_worker_file_ref=ref(EXP014 / "scripts/coverage_replay.py"),
                                 cumulative_worker_file_ref=ref(EXP014 / "scripts/coverage_cumulative.py"))
    else:
        matrix["coverage"].update(enabled=False, replay_after_each_round=False, scope_file_ref=None)
    if args.operational_smoke:
        if args.target_output is None:
            raise SystemExit("Operational smoke requires a new --target-output")
        target_output = args.target_output.resolve()
        if not target_output.is_relative_to(ROOT) or target_output.exists():
            raise SystemExit("Target output must be a new file inside the repository")
        targets = copy.deepcopy(runner.load_json(TARGETS))
        if not re.fullmatch(r"[A-Za-z0-9_]+", args.smoke_id):
            raise SystemExit("Smoke ID must contain only letters, digits and underscores")
        targets.update(manifest_id="etm_" + args.smoke_id, revision=1, status="frozen")
        target_output.parent.mkdir(parents=True, exist_ok=True)
        target_output.write_text(json.dumps(targets, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        matrix["matrix_id"] = args.smoke_id
        matrix["matrix_revision"] = {"revision_number": 1,
            "change_reason": "Independent pipeline-only smoke; approved semantics reused. Schedule, coverage and analysis window are explicitly configured, not effectiveness evidence."}
        matrix["lifecycle"] = {"status": "frozen", "phase": "operational_smoke"}
        if args.analysis_cutoff_delay_seconds <= 0:
            raise SystemExit("Analysis cutoff delay must be positive")
        matrix["analysis"]["analysis_cutoff_policy"]["delay_seconds"] = args.analysis_cutoff_delay_seconds
        matrix["inputs"]["shared_artifact_refs"]["evaluation_target_manifest"] = artifact_binding(
            target_output, targets["manifest_id"], targets["revision"])
    runner.validate_matrix(matrix)
    runner.verify_declared_file_refs(matrix)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(matrix, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "valid_operational_smoke" if args.operational_smoke else "valid_draft", "matrix_id": matrix["matrix_id"], "path": output.relative_to(ROOT).as_posix(),
                      "api_ids": [item["api_id"] for item in matrix["api_entries"]],
                      "execution_ready": args.operational_smoke, "requires_human_freeze": not args.operational_smoke}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
