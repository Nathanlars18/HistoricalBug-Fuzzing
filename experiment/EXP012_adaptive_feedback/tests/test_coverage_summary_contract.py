"""Cross-layer Coverage Summary contract tests."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from jsonschema import Draft202012Validator

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run_feedback_controller.py"
SPEC = importlib.util.spec_from_file_location("feedback_coverage_contract", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CoverageSummaryContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.coverage_dir = self.root / "attempt" / "coverage"
        self.coverage_dir.mkdir(parents=True)
        self.binary = self.root / "harness"
        self.binary.write_bytes(b"harness-binary")
        self.profile = self.coverage_dir / "coverage.profdata"
        self.profile.write_bytes(b"profile")
        self.summary_path = self.coverage_dir / "coverage_summary.json"
        self.summary = {
            "record_format_version": "1.0", "scope_hash": "a" * 64,
            "pytorch_commit": "b" * 40, "coverage_image": "sha256:" + "c" * 64,
            "source_prefix": "/root/pytorch/aten/src/ATen/",
            "harness_binary_hash": sha(self.binary), "corpus_file_count": 3,
            "source_file_count": 10,
            "measurements": {
                "lines": {"covered": 2, "total": 10, "percent": 20.0},
                "branches": {"covered": 1, "total": 5, "percent": 20.0}},
            "quality_status": "complete", "profile_hash": sha(self.profile),
            "warnings": [], "replay_seconds": 1.25,
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_summary(self) -> dict:
        self.summary_path.write_text(json.dumps(self.summary, indent=2) + "\n")
        digest = sha(self.summary_path)
        declared = {"status": "present", "location": {
            "file_ref": {"relative_path": self.summary_path.relative_to(self.root).as_posix(),
                         "content_hash": digest},
            "artifact_ref": {"artifact_id": "coverage_summary_fixture",
                             "artifact_version": 1, "content_hash": digest}}}
        artifact = {"validation": {"compile_check": {"status": "passed", "binary_artifact": {
            "relative_path": self.binary.relative_to(self.root).as_posix(),
            "content_hash": sha(self.binary)}}}}
        return declared, artifact

    def test_accepts_legacy_complete_and_extended_warning_summaries(self):
        for quality, extras in (
            ("complete", {}),
            ("partial_warning", {"resource_limits": {"candidate_sample_limit": 64},
                                  "thread_environment": {"OMP_NUM_THREADS": "1"},
                                  "cleanup_warnings": ["non-fatal cleanup note"]}),
        ):
            with self.subTest(quality=quality):
                self.summary["quality_status"] = quality
                self.summary["warnings"] = ["LLVM warning"] if quality == "partial_warning" else []
                self.summary.update(extras)
                declared, artifact = self.write_summary()
                with mock.patch.object(MODULE, "REPOSITORY_ROOT", self.root):
                    assessment, ref = MODULE.coverage_assessment(self.summary_path, artifact, declared)
                self.assertEqual(assessment["quality_status"], quality)
                self.assertEqual(ref["content_hash"], sha(self.summary_path))
                for key in extras:
                    self.summary.pop(key, None)

    def test_partial_failure_retains_reason_batch_counts_and_summary_reference(self):
        self.summary.update(
            source_file_count=None, measurements=None, quality_status="partial_failure",
            successful_batch_count=1, planned_batch_count=3,
            failed_batch={"batch_index": 1, "exit_code": 1, "timed_out": False,
                          "message": "llvm profile export failed"},
        )
        declared, artifact = self.write_summary()
        with mock.patch.object(MODULE, "REPOSITORY_ROOT", self.root):
            assessment, ref = MODULE.coverage_assessment(self.summary_path, artifact, declared)
        self.assertEqual(assessment["collection_state"], "partial")
        self.assertIsNone(assessment["measurements"])
        self.assertEqual(assessment["failure_reason"], "llvm profile export failed")
        self.assertEqual(assessment["completed_batch_count"], 1)
        self.assertEqual(assessment["planned_batch_count"], 3)
        self.assertEqual(assessment["failure_evidence_refs"][0]["content_hash"], ref["content_hash"])

    def test_rejects_corrupt_file_evidence_hash(self):
        declared, artifact = self.write_summary()
        declared["location"]["artifact_ref"]["content_hash"] = "0" * 64
        with mock.patch.object(MODULE, "REPOSITORY_ROOT", self.root):
            with self.assertRaisesRegex(MODULE.RoundInputError, "exact Fuzzing Round evidence"):
                MODULE.coverage_assessment(self.summary_path, artifact, declared)

    def test_collection_failure_carries_hashed_diagnostic_reference(self):
        log = self.root / "coverage_failure.log"
        log.write_text("docker worker could not start\n")
        digest = sha(log)
        location = {"file_ref": {"relative_path": log.relative_to(self.root).as_posix(),
                                  "content_hash": digest},
                    "artifact_ref": {"artifact_id": "coverage_failure_fixture",
                                     "artifact_version": 1, "content_hash": digest}}
        declared = {"status": "collection_failed", "diagnostic_refs": [location["artifact_ref"]],
                    "diagnostic_file_refs": [location]}
        with mock.patch.object(MODULE, "REPOSITORY_ROOT", self.root):
            assessment, ref = MODULE.coverage_assessment(None, {}, declared)
        self.assertIsNone(ref)
        self.assertEqual(assessment["collection_state"], "failed")
        self.assertEqual(assessment["failure_reason"], "docker worker could not start")
        self.assertEqual(assessment["failure_evidence_refs"], [location["artifact_ref"]])

    def test_controller_writes_machine_readable_error(self):
        path = self.root / "controller_result.json"
        MODULE.write_error_result(path, MODULE.RoundInputError("bad coverage hash"))
        value = json.loads(path.read_text())
        self.assertEqual(value["status"], "error")
        self.assertEqual(value["error_type"], "RoundInputError")
        self.assertEqual(value["message"], "bad coverage hash")

    def test_partial_failure_assessment_matches_decision_schema(self):
        schema = MODULE.load_json(MODULE.DEFAULT_DECISION_SCHEMA, global_input=True)
        coverage_schema = dict(schema["$defs"]["coverage_assessment"])
        coverage_schema["$defs"] = schema["$defs"]
        value = {"trend": "coverage_not_assessed",
                 "coverage_summary_ref": {"artifact_id": "coverage_summary_fixture",
                                           "artifact_version": 1, "content_hash": "a" * 64},
                 "collection_state": "partial", "measurements": None,
                 "scope_hash": "b" * 64, "pytorch_commit": "c" * 40,
                 "coverage_image": "sha256:" + "d" * 64,
                 "harness_binary_hash": "e" * 64, "quality_status": "partial_failure",
                 "failure_reason": "one batch did not replay", "completed_batch_count": 1,
                 "planned_batch_count": 2,
                 "failure_evidence_refs": [{"artifact_id": "coverage_summary_fixture",
                                             "artifact_version": 1, "content_hash": "a" * 64}]}
        Draft202012Validator(coverage_schema).validate(value)


if __name__ == "__main__":
    unittest.main()
