#!/usr/bin/env python3
"""Controlled Candidate Bundle to Crash Case integration fixture."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ADAPTER = load_module(
    "candidate_fixture_round_adapter",
    REPO / "experiment/EXP014_experimental_evaluation/scripts/run_fuzzing_round.py",
)
ANALYZER = load_module(
    "candidate_fixture_crash_analyzer",
    REPO / "experiment/EXP013_crash_triage_and_result_analysis/scripts/analyze_crash_cases.py",
)


class CandidateBundleIntegrationTest(unittest.TestCase):
    def test_bundle_ingests_without_semantic_manifest(self) -> None:
        results = REPO / "experiment/EXP013_crash_triage_and_result_analysis/results"
        results.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=results) as temporary:
            root = Path(temporary)
            attempt = root / "attempt_001"
            candidates = attempt / "candidates"
            candidates.mkdir(parents=True)
            (candidates / "crash-fixture").write_bytes(b"fixture-input")
            run_log = attempt / "run.log"
            run_log.write_text("libFuzzer: deadly signal #3", encoding="utf-8")
            output_manifest = {
                "record_format_version": "1.0",
                "record_type": "corpus_manifest",
                "identity": {"corpus_id": "corpus_fixture", "artifact_version": 1},
                "source": {"kind": "round_output", "source_round_id": "fixture_round"},
                "files": [],
                "provenance": {"generator_ref": ADAPTER.adapter_reference(), "generated_at": "2026-09-20T00:00:00Z"},
            }
            output_manifest_path = attempt / "corpus_manifest.json"
            ADAPTER.write_json_atomic(output_manifest_path, output_manifest)
            args = Namespace(
                task_key="torch.matmul:bug_aware_static:repeat_001:round_001",
                api_id="torch.matmul",
                target_api="torch.matmul",
                group_id="bug_aware_static",
                repeat_id="repeat_001",
                repeat_index=1,
                round_id="round_001",
                round_index=1,
                attempt_index=1,
                planned_final_round_index=3,
                active_seconds=5,
                seed=7,
                attempt_dir=attempt,
                runtime_config=ADAPTER.DEFAULTS["runtime_config"],
                instrumentation_header=ADAPTER.DEFAULTS["instrumentation_header"],
                instrumentation_source=ADAPTER.DEFAULTS["instrumentation_source"],
            )
            bundle_validator = ADAPTER.schema_validator(
                ADAPTER.DEFAULTS["candidate_bundle_schema"], "Candidate Bundle"
            )
            _, binding, observations = ADAPTER.build_candidate_bundle(
                args=args,
                execution_id="ex_fixture",
                observed_at="2026-09-20T00:00:05Z",
                candidates_dir=candidates,
                run_log_path=run_log,
                validator=bundle_validator,
            )
            self.assertIsNotNone(binding)
            resolved = ADAPTER.ResolvedHarness(
                harness_spec={
                    "identity": {"spec_id": "hs_fixture", "target_api": "torch.matmul", "spec_mode": "bug_aware_static"},
                    "revision_information": {"revision_number": 1},
                },
                strategy={"identity": {"strategy_id": "st_fixture"}, "revision_information": {"revision_number": 1}},
                artifact={"schema_version": "1.0", "identity": {"harness_artifact_id": "ha_fixture", "generation_key": "1" * 64}},
                binary_path=root / "unused",
            )
            round_record = ADAPTER.build_round_record(
                args=args,
                resolved=resolved,
                execution_id="ex_fixture",
                started_at="2026-09-20T00:00:00Z",
                ended_at="2026-09-20T00:00:05Z",
                elapsed=5.0,
                process=subprocess.CompletedProcess([], 134, "", ""),
                round_config={"fixture": True},
                input_corpus_ref=None,
                output_manifest=output_manifest,
                output_manifest_path=output_manifest_path,
                snapshot=None,
                snapshot_path=None,
                run_log_path=run_log,
                candidate_binding=binding,
                candidate_observations=observations,
                round_validator=ADAPTER.schema_validator(ADAPTER.DEFAULTS["round_schema"], "Fuzzing Round"),
            )
            round_path = attempt / "fuzzing_round_record.json"
            ADAPTER.write_json_atomic(round_path, round_record)
            execution_index = root / "execution_index.json"
            execution_index.write_text(
                json.dumps({"tasks": {args.task_key: {"status": "completed_with_abnormal_events", "round_record_path": str(round_path)}}}),
                encoding="utf-8",
            )
            output = root / "cases"
            status = ANALYZER.main([
                "--output-root", str(output),
                "ingest", "--execution-index", str(execution_index),
            ])
            self.assertEqual(status, 0)
            cases = list(output.glob("cases/*/records/*_r001.json"))
            self.assertEqual(len(cases), 1)
            case = json.loads(cases[0].read_text(encoding="utf-8"))
            self.assertEqual(case["origin"]["candidate_observation_id"], observations[0]["candidate_id"])
            self.assertEqual(case["candidate_event"]["observations"][0]["kind"], "process_termination")


if __name__ == "__main__":
    unittest.main()
