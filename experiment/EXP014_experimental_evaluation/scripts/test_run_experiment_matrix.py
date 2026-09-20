#!/usr/bin/env python3
"""Deterministic regression tests for EXP014 matrix orchestration."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("run_experiment_matrix.py")
SPEC = importlib.util.spec_from_file_location("run_experiment_matrix", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class MatrixRunnerPrepareTests(unittest.TestCase):
    def test_round_attempt_paths_separate_adapter_and_runner_outputs(self) -> None:
        operation_root = Path("/tmp/round_001")
        adapter_dir, process_dir = MODULE.round_attempt_paths(operation_root, 1)
        self.assertEqual(adapter_dir, operation_root / "attempt_001")
        self.assertEqual(
            process_dir, operation_root / "runner_processes" / "attempt_001"
        )
        self.assertNotEqual(adapter_dir, process_dir)

    def test_restarted_round_merges_candidate_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            operation = root / "round"
            task = MODULE.Task("torch.matmul", "torch.matmul", "bug_aware_adaptive", 1, 1, 7)
            records = []
            fragments = []
            candidate_id = "cand_fixture"
            for index in (1, 2):
                attempt = operation / f"attempt_{index:03d}"
                attempt.mkdir(parents=True)
                record = {
                    "identity": {"attempt_index": index, "execution_id": f"ex_{index}"},
                    "execution": {
                        "started_at": f"2026-09-20T00:00:0{index}Z",
                        "ended_at": f"2026-09-20T00:00:1{index}Z",
                        "actual_duration_seconds": 1.0,
                    },
                    "attempt_selection": {"status": "selected_as_round_result", "reason_code": "only_attempt"},
                    "evidence": {
                        "run_log_refs": [{"artifact_id": f"log_{index}", "artifact_version": 1, "content_hash": str(index) * 64}],
                        "candidate_evidence": {"status": "absent", "bundle_ref": None, "bundle_file_ref": None, "observations": []},
                    },
                    "provenance": {},
                }
                binding = None
                if index == 1:
                    candidate = {
                        "candidate_id": candidate_id,
                        "source_attempt_index": 1,
                        "observation_kind": "crash",
                        "observation_subtype": "native_process_termination",
                        "observed_at": "2026-09-20T00:00:11Z",
                        "triggering_input": {}, "primary_diagnostic": None,
                        "branch_ids": [], "site_ids": [], "iteration_index": None,
                        "target_invocation_id": None, "oracle_evidence_tier": None,
                    }
                    bundle = {
                        "record_type": "candidate_bundle",
                        "identity": {"bundle_id": "cb_fixture", "artifact_version": 1},
                        "candidates": [candidate],
                    }
                    bundle_path = attempt / "candidate_bundle.json"
                    MODULE.write_json(bundle_path, bundle)
                    binding = {
                        "artifact_ref": {"artifact_id": "cb_fixture", "artifact_version": 1, "content_hash": MODULE.content_hash(bundle)},
                        "record_file_ref": {"relative_path": bundle_path.relative_to(root).as_posix(), "content_hash": MODULE.file_hash(bundle_path)},
                    }
                    record["evidence"]["candidate_evidence"] = {
                        "status": "present",
                        "bundle_ref": binding["artifact_ref"],
                        "bundle_file_ref": binding["record_file_ref"],
                        "observations": [{"candidate_id": candidate_id, "observation_kind": "crash", "branch_ids": [], "site_ids": [], "evidence_refs": [{"artifact_id": "input_fixture", "artifact_version": 1, "content_hash": "a" * 64}]}],
                    }
                round_path = attempt / "fuzzing_round_record.json"
                MODULE.write_json(round_path, record)
                result = {
                    "round_record_file_ref": {"relative_path": round_path.relative_to(root).as_posix(), "content_hash": MODULE.file_hash(round_path)},
                    "candidate_bundle_binding": binding,
                }
                fragments.append({"adapter_result": result})
                records.append(record)
            with mock.patch.object(MODULE, "REPOSITORY_ROOT", root):
                selected_path, bundle_path = MODULE.materialize_selected_round(fragments, operation, task)
            selected = json.loads(selected_path.read_text(encoding="utf-8"))
            self.assertIsNotNone(bundle_path)
            self.assertEqual(selected["execution"]["actual_duration_seconds"], 2.0)
            self.assertEqual(selected["evidence"]["candidate_evidence"]["observations"][0]["candidate_id"], candidate_id)

    def test_prior_round_must_complete_before_next_round(self) -> None:
        task = MODULE.Task(
            api_id="torch.matmul",
            target_api="torch.matmul",
            group_id="structured_baseline",
            repeat_id=1,
            round_index=2,
            seed=1,
        )
        state = {
            "tasks": {
                "torch.matmul:structured_baseline:repeat_001:round_001": {
                    "status": "method_failed"
                }
            }
        }
        with self.assertRaisesRegex(MODULE.RunnerError, "did not complete successfully"):
            MODULE.prior_round_corpus(task, state, Path("/tmp/initial.json"))

    def test_initial_artifact_builder_receives_run_local_spec_root(self) -> None:
        matrix = {
            "core_groups": [
                {
                    "group_id": "structured_baseline",
                    "harness_spec_builder_mode": "controlled_baseline",
                },
                {
                    "group_id": "bug_aware_static",
                    "harness_spec_builder_mode": "bug_aware_static",
                },
                {
                    "group_id": "bug_aware_adaptive",
                    "harness_spec_builder_mode": "reuse_bug_aware_static_h0",
                },
            ],
            "synthesis": {
                "harness_spec": {"maximum_completed_responses": 3},
                "strategy": {"maximum_completed_responses": 3},
            },
        }
        entry = {"api_id": "torch.matmul", "compile_profile_file_ref": {}}
        state = {"preparation": {}}
        run_root = Path("/tmp/hbfg_matrix_smoke")
        captured: dict[str, list[str]] = {}

        def fake_builder_step(**kwargs: object) -> Path:
            step_name = str(kwargs["step_name"])
            captured[step_name] = list(kwargs["argv"])  # type: ignore[arg-type]
            return Path(f"/tmp/{step_name}.json")

        profile = {"target": {"python_api": "torch.matmul"}}
        with (
            mock.patch.object(
                MODULE,
                "api_profile",
                return_value=(profile, Path("/tmp/api_profile.json")),
            ),
            mock.patch.object(MODULE, "model_arguments", return_value=[]),
            mock.patch.object(
                MODULE,
                "helper_profile_set",
                return_value=Path("/tmp/helper_profile_set.json"),
            ),
            mock.patch.object(
                MODULE,
                "verify_file_reference",
                return_value=Path("/tmp/compile_profile.json"),
            ),
            mock.patch.object(
                MODULE,
                "evaluation_target_manifest",
                return_value=Path("/tmp/evaluation_target_manifest.json"),
            ),
            mock.patch.object(
                MODULE, "run_builder_step", side_effect=fake_builder_step
            ),
            mock.patch.object(MODULE, "preflight"),
            mock.patch.object(MODULE, "persist_state"),
        ):
            MODULE.prepare_group(
                matrix,
                entry,
                "structured_baseline",
                Path("/tmp/execution_index.json"),
                state,
                run_root,
                "python",
            )

        spec_argv = captured["harness_spec"]
        helper_option_index = spec_argv.index("--helper-profile-set")
        self.assertEqual(
            spec_argv[helper_option_index + 1], "/tmp/helper_profile_set.json"
        )

        argv = captured["harness_artifact"]
        option_index = argv.index("--harness-spec-root")
        expected = (
            run_root
            / "prepare"
            / MODULE.safe_component("torch.matmul")
            / "structured_baseline"
            / "harness_specs"
        )
        self.assertEqual(argv[option_index + 1], str(expected))
