#!/usr/bin/env python3
"""Deterministic tests for the single-round execution adapter."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from argparse import Namespace
from unittest import mock
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


SCRIPT = Path(__file__).with_name("run_fuzzing_round.py")
SPEC = importlib.util.spec_from_file_location("run_fuzzing_round", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class RoundAdapterTests(unittest.TestCase):
    def test_owned_schemas_are_valid(self) -> None:
        for path in (
            MODULE.DEFAULTS["runtime_snapshot_schema"],
            MODULE.DEFAULTS["corpus_schema"],
            MODULE.DEFAULTS["candidate_bundle_schema"],
        ):
            schema = json.loads(path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)

    def test_signal_mapping(self) -> None:
        self.assertEqual(MODULE.signal_name(134), "SIGABRT")
        self.assertEqual(MODULE.signal_name(-11), "SIGSEGV")
        self.assertIsNone(MODULE.signal_name(0))

    def test_docker_command_preserves_runtime_bindings(self) -> None:
        argv = MODULE.docker_command(
            image="sha256:" + "1" * 64,
            artifact_dir=Path("/tmp/artifact"),
            attempt_dir=Path("/tmp/attempt"),
            active_seconds=7,
            seed=13,
            container_name="hbfg-test",
        )
        joined = "\0".join(argv)
        self.assertIn("HBFG_METRICS_PATH=/output/runtime_snapshot.json", argv)
        self.assertIn("/tmp/artifact:/artifact:ro", argv)
        self.assertIn("/tmp/attempt:/output", argv)
        self.assertIn("-max_total_time=7", joined)
        self.assertIn("-seed=13", joined)

    def test_candidate_bundle_is_deterministic_and_schema_valid(self) -> None:
        validator = MODULE.schema_validator(
            MODULE.DEFAULTS["candidate_bundle_schema"], "Candidate Bundle"
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            attempt = root / "attempt_001"
            candidates = attempt / "candidates"
            candidates.mkdir(parents=True)
            (candidates / "crash-deadbeef").write_bytes(b"trigger")
            log = attempt / "run.log"
            log.write_text("ERROR: AddressSanitizer #17", encoding="utf-8")
            args = Namespace(
                task_key="torch.matmul:bug_aware_static:repeat_001:round_001",
                attempt_index=1,
                api_id="torch.matmul",
                target_api="torch.matmul",
                group_id="bug_aware_static",
                repeat_id="repeat_001",
                round_index=1,
                attempt_dir=attempt,
            )
            with mock.patch.object(MODULE, "REPOSITORY_ROOT", root):
                bundle, binding, observations = MODULE.build_candidate_bundle(
                    args=args,
                    execution_id="ex_fixture",
                    observed_at="2026-09-20T00:00:00Z",
                    candidates_dir=candidates,
                    run_log_path=log,
                    validator=validator,
                )
            self.assertIsNotNone(bundle)
            self.assertIsNotNone(binding)
            self.assertEqual(bundle["candidates"][0]["observation_kind"], "sanitizer")
            self.assertEqual(bundle["candidates"][0]["iteration_index"], 17)
            self.assertEqual(observations[0]["candidate_id"], bundle["candidates"][0]["candidate_id"])

    def test_runtime_snapshot_identity_and_counts(self) -> None:
        validator = MODULE.schema_validator(
            MODULE.DEFAULTS["runtime_snapshot_schema"], "Runtime Snapshot"
        )
        snapshot = {
            "record_format_version": "1.0",
            "runtime_version": "1.0",
            "artifact_id": "ha_test",
            "generation_key": "1" * 64,
            "snapshot_kind": "final",
            "snapshot_interval": 1,
            "site_count": 2,
            "started_iterations": 3,
            "finished_iterations": 3,
            "unwound_iterations": 0,
            "invalid_site_records": 0,
            "export_failures": 0,
            "site_counts": [3, 1],
        }
        artifact = {
            "identity": {
                "harness_artifact_id": "ha_test",
                "generation_key": "1" * 64,
            }
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "snapshot.json"
            path.write_text(json.dumps(snapshot), encoding="utf-8")
            loaded = MODULE.validate_runtime_snapshot(path, validator, artifact)
            self.assertEqual(loaded, snapshot)
            snapshot["site_counts"] = [3]
            path.write_text(json.dumps(snapshot), encoding="utf-8")
            with self.assertRaisesRegex(MODULE.InputError, "site_counts length"):
                MODULE.validate_runtime_snapshot(path, validator, artifact)

    def test_corpus_schema_distinguishes_initial_and_round_output(self) -> None:
        schema = json.loads(
            MODULE.DEFAULTS["corpus_schema"].read_text(encoding="utf-8")
        )
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        base = {
            "record_format_version": "1.0",
            "record_type": "corpus_manifest",
            "identity": {"corpus_id": "corpus_test", "artifact_version": 1},
            "source": {"kind": "initial", "source_round_id": None},
            "files": [],
            "provenance": {
                "generator_ref": {
                    "artifact_id": "run_fuzzing_round",
                    "artifact_version": "0.2.0",
                    "content_hash": "1" * 64,
                },
                "generated_at": "2026-09-16T00:00:00Z",
            },
        }
        self.assertEqual(list(validator.iter_errors(base)), [])
        base["source"] = {"kind": "round_output", "source_round_id": None}
        self.assertTrue(list(validator.iter_errors(base)))


if __name__ == "__main__":
    unittest.main()
