from __future__ import annotations

import unittest
import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).with_name("build_two_api_execution_smoke_draft.py")
SPEC = importlib.util.spec_from_file_location("build_two_api_execution_smoke_draft", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
draft = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = draft
SPEC.loader.exec_module(draft)


class TwoApiExecutionSmokeDraftTests(unittest.TestCase):
    def test_build_binds_exact_reused_approvals_and_remains_a_draft(self) -> None:
        matrix = draft.build()
        self.assertEqual(matrix["lifecycle"]["status"], "draft")
        self.assertEqual(matrix["preparation"]["mode"], "reuse_approved")
        self.assertEqual(
            {entry["api_id"] for entry in matrix["api_entries"]},
            set(draft.APPROVED),
        )
        for entry in matrix["api_entries"]:
            self.assertIn("--knowledge-review-ledger", draft.runner.frozen_knowledge_arguments(entry, matrix))
            self.assertEqual(
                set(entry["approved_inputs"]),
                {"structured_baseline", "bug_aware_static"},
            )

    def test_target_manifest_avoids_duplicate_cosine_empty_weight(self) -> None:
        manifest = draft.runner.load_json(draft.TARGETS)
        targets = {
            item["api_id"]: item["targets"]
            for item in manifest["api_target_sets"]
        }
        self.assertEqual(
            [target["detector_id"] for target in targets["torch.batch_norm_update_stats"]],
            ["tensor_empty_v1"],
        )
        self.assertEqual(
            {target["detector_id"] for target in targets["torch.nn.functional.cosine_embedding_loss"]},
            {"tensor_shape_mismatch_v1", "tensor_pair_empty_v1"},
        )
        self.assertEqual(len(targets["torch.nn.functional.cosine_embedding_loss"]), 2)

    def test_smoke_schedule_is_small_and_seed_paired(self) -> None:
        matrix = draft.build()
        self.assertEqual(matrix["execution"]["repeat_count"], 1)
        self.assertEqual(matrix["execution"]["round_count"], 2)
        self.assertEqual(matrix["execution"]["active_fuzzing_seconds_per_round"], 15)
        tasks = draft.runner.build_tasks(matrix, matrix["api_entries"])
        self.assertEqual(len(tasks), 12)
        for entry in matrix["api_entries"]:
            path = draft.ROOT / entry["approved_inputs"]["structured_baseline"]["spec_file_ref"]["relative_path"]
            from experiment.EXP014_experimental_evaluation.scripts import run_fuzzing_round
            validator = run_fuzzing_round.schema_validator(run_fuzzing_round.DEFAULTS["harness_spec_schema"], "HarnessSpec")
            run_fuzzing_round.validate_record(draft.runner.load_json(path), validator, "approved HarnessSpec")
        by_key = {task.key: task for task in tasks}
        for api in draft.APPROVED:
            for repeat in ("repeat_001",):
                for round_id in ("round_001", "round_002"):
                    seeds = {
                        by_key[f"{api}:{group}:{repeat}:{round_id}"].seed
                        for group in ("structured_baseline", "bug_aware_static", "bug_aware_adaptive")
                    }
                    self.assertEqual(len(seeds), 1)


if __name__ == "__main__":
    unittest.main()
