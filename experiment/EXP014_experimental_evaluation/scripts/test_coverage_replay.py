#!/usr/bin/env python3
"""Local, network-free checks for the frozen-corpus coverage interface."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from experiment.EXP014_experimental_evaluation.scripts import coverage_replay
from experiment.EXP014_experimental_evaluation.scripts import analyze_experiment_results
from experiment.EXP014_experimental_evaluation.scripts import run_experiment_matrix


ROOT = Path(__file__).resolve().parents[3]
SCOPE = ROOT / "experiment/EXP014_experimental_evaluation/configs/coverage_scope_pytorch_2_10.json"


class CoverageReplayTests(unittest.TestCase):
    def test_scope_requires_pinned_image(self) -> None:
        valid = coverage_replay.load_scope(SCOPE)
        self.assertTrue(valid["coverage_image"].startswith("sha256:"))
        with tempfile.TemporaryDirectory() as temporary:
            invalid = Path(temporary) / "scope.json"
            valid["coverage_image"] = "latest"
            invalid.write_text(json.dumps(valid), encoding="utf-8")
            with self.assertRaises(coverage_replay.CoverageError):
                coverage_replay.load_scope(invalid)

    def test_corpus_hash_is_checked_before_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            corpus = Path(temporary)
            sample = corpus / "seed"
            sample.write_bytes(b"fuzz bytes")
            manifest = {"files": [{"corpus_relative_path": "seed", "file_ref": {
                "content_hash": coverage_replay.sha256(sample)
            }}]}
            self.assertEqual(coverage_replay.verified_corpus_files(manifest, corpus), [sample])
            sample.write_bytes(b"changed")
            with self.assertRaises(coverage_replay.CoverageError):
                coverage_replay.verified_corpus_files(manifest, corpus)

    def test_runner_adds_scope_only_when_enabled(self) -> None:
        scope_ref = {
            "relative_path": SCOPE.relative_to(ROOT).as_posix(),
            "content_hash": run_experiment_matrix.file_hash(SCOPE),
        }
        matrix = {
            "execution": {"runner_adapters": {"round_argv_template": ["adapter", "{task_key}"]}},
            "coverage": {"enabled": False, "scope_file_ref": None},
        }
        self.assertEqual(run_experiment_matrix.round_adapter_argv(matrix, {"task_key": "round1"}),
                         ["adapter", "round1"])
        matrix["coverage"] = {"enabled": True, "scope_file_ref": scope_ref}
        self.assertEqual(run_experiment_matrix.round_adapter_argv(matrix, {"task_key": "round1"}),
                         ["adapter", "round1", "--coverage-scope", str(SCOPE)])

    def test_analyzer_verifies_profile_and_reports_diagnostic_only(self) -> None:
        analyzer = analyze_experiment_results
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scope = root / "scope.json"
            scope.write_text("{}", encoding="utf-8")
            profile = root / "coverage.profdata"
            profile.write_bytes(b"profile fixture")
            summary_path = root / "coverage_summary.json"
            summary = {
                "scope_hash": analyzer.file_hash(scope),
                "profile_hash": analyzer.file_hash(profile),
                "quality_status": "partial_warning",
                "source_file_count": 1,
                "corpus_file_count": 2,
                "measurements": {
                    "lines": {"covered": 1, "total": 3},
                    "branches": {"covered": 1, "total": 2},
                },
                "warnings": ["fixture warning"],
            }
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            record_path = root / "round.json"
            record_path.write_text(json.dumps({"evidence": {"coverage_summary": {
                "status": "present",
                "location": {
                    "file_ref": {"relative_path": "coverage_summary.json", "content_hash": analyzer.file_hash(summary_path)},
                    "artifact_ref": {"content_hash": analyzer.file_hash(summary_path)},
                },
            }}}), encoding="utf-8")
            round_result = analyzer.RoundResult(
                "round1", "torch.matmul", "structured_baseline", "repeat_001", 1,
                {}, {}, "artifact", str(record_path), None,
            )
            matrix = {"coverage": {"enabled": True, "scope_file_ref": {
                "relative_path": "scope.json", "content_hash": analyzer.file_hash(scope),
            }}}
            with mock.patch.object(analyzer, "REPOSITORY_ROOT", root):
                rows = analyzer.coverage_diagnostics([round_result], matrix)
                self.assertEqual(rows[0]["lines_covered"], 1)
                self.assertEqual(rows[0]["warning_count"], 1)
                profile.write_bytes(b"tampered")
                with self.assertRaises(analyzer.InputError):
                    analyzer.coverage_diagnostics([round_result], matrix)


if __name__ == "__main__":
    unittest.main()
