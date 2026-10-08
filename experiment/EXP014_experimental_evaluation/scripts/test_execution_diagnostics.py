"""Focused regressions for diagnostic unions, capture limits and analysis windows."""
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from experiment.EXP014_experimental_evaluation.scripts import analyze_experiment_results as analyzer
from experiment.EXP014_experimental_evaluation.scripts import coverage_replay as replay
from experiment.EXP014_experimental_evaluation.scripts import coverage_cumulative as cumulative


class ExecutionDiagnosticsTests(unittest.TestCase):
    def test_analysis_window_does_not_close_early(self):
        cutoff = datetime(2026, 10, 8, tzinfo=timezone.utc)
        early = analyzer.analysis_window(cutoff, datetime(2026, 10, 7, tzinfo=timezone.utc))
        self.assertEqual(early["status"], "provisional")
        final = analyzer.analysis_window(cutoff, datetime(2026, 10, 9, tzinfo=timezone.utc))
        self.assertEqual(final["status"], "final")
        self.assertEqual(final["as_of"], "2026-10-08T00:00:00Z")

    def test_cleanup_timeout_is_diagnostic_not_a_replacement_failure(self):
        with mock.patch.object(replay.subprocess, "run", side_effect=subprocess.TimeoutExpired("docker", 30)):
            self.assertTrue(replay.cleanup_container("fixture"))

    def test_capture_counts_expose_suppression(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = {"capture_summary": {"counts": {"attempts": 100, "saved": 64, "failures": 0,
                       "exception_attempts": 100, "oracle_attempts": 0, "limit_per_kind": 64}}}
            counts = bundle["capture_summary"]["counts"]
            path = root / "bundle.json"
            path.write_text(json.dumps(counts))
            record = {"evidence": {"candidate_evidence": {
                "capture_summary": bundle["capture_summary"],
                "capture_summary_file_ref": {"relative_path": "bundle.json", "content_hash": analyzer.file_hash(path)},
                "bundle_file_ref": None, "bundle_ref": None}}}
            record_path = root / "round.json"
            record_path.write_text(json.dumps(record))
            r = analyzer.RoundResult("r", "api", "g", "repeat", 1, {}, {}, "", str(record_path), None)
            with mock.patch.object(analyzer, "REPOSITORY_ROOT", root):
                row = analyzer.capture_diagnostics([r])[0]
            self.assertEqual(row["suppressed"], 36)
            self.assertEqual(row["saturated_process_count"], 1)

    def test_union_uses_llvm_profiles_and_keeps_different_runs_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scope = root / "scope.json"
            scope.write_text("{}")
            rounds = []
            for group, repeat, index in (("static", "r1", 1), ("static", "r1", 2), ("static", "r2", 1), ("adaptive", "r1", 1)):
                folder = root / f"{group}_{repeat}_{index}"
                folder.mkdir()
                profile = folder / "coverage.profdata"
                profile.write_bytes(f"profile-{group}-{repeat}-{index}".encode())
                summary = folder / "coverage_summary.json"
                summary.write_text(json.dumps({"scope_hash": analyzer.file_hash(scope),
                    "profile_hash": analyzer.file_hash(profile), "quality_status": "complete"}))
                record = folder / "round.json"
                record.write_text(json.dumps({"evidence": {"coverage_summary": {"status": "present", "location": {
                    "file_ref": {"relative_path": str(summary.relative_to(root)), "content_hash": analyzer.file_hash(summary)}}}}}))
                rounds.append(analyzer.RoundResult(str(folder), "api", group, repeat, index, {}, {}, "", str(record), None))
            calls = []
            merged = root / "merged.json"
            merged.write_text(json.dumps({"quality_status": "complete", "measurements": {
                "lines": {"covered": 7, "total": 10}, "branches": {"covered": 3, "total": 8}}}))
            def merge(scope, profiles, output):
                calls.append(list(profiles))
                return merged
            matrix = {"coverage": {"enabled": True, "scope_file_ref": {
                "relative_path": "scope.json", "content_hash": analyzer.file_hash(scope)}}}
            with mock.patch.object(analyzer, "REPOSITORY_ROOT", root), mock.patch.object(cumulative, "merge_profiles", side_effect=merge):
                rows = analyzer.cumulative_coverage_diagnostics(list(reversed(rounds)), matrix, root / "unions")
            self.assertEqual([len(p) for p in calls], [1, 1, 2, 1])
            self.assertTrue(all(row["lines_covered"] == 7 for row in rows))
            self.assertTrue(all(row["status"] == "complete" for row in rows))

    def test_replay_batch_timeout_preserves_partial_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            output.mkdir()
            (root / "manifest.json").write_text("{}")
            real_path = Path
            def mapped_path(value):
                if str(value) in ("/scope.json", "/output", "/corpus", "/manifest.json"):
                    return root / str(value).lstrip("/")
                return real_path(value)
            scope = {"scope_version": 1, "pytorch_commit": "c", "coverage_image": "i", "source_prefix": "s", "replay_batch_size": 2}
            with mock.patch.object(replay, "Path", side_effect=mapped_path), mock.patch.object(replay, "load_scope", return_value=scope), \
                 mock.patch.object(replay, "sha256", return_value="h"), mock.patch.object(replay, "verified_corpus_files", return_value=[root / "input"]), \
                 mock.patch.object(replay.subprocess, "run", side_effect=subprocess.TimeoutExpired("harness", 600)), \
                 mock.patch.object(replay.os, "chown"):
                self.assertEqual(replay.worker(), 1)
            summary = json.loads((output / "coverage_summary.json").read_text())
            self.assertEqual(summary["quality_status"], "partial_failure")
            self.assertTrue(summary["failed_batch"]["timed_out"])
            self.assertIsNone(summary["measurements"])

    def test_cumulative_merge_retries_in_new_directory_and_reuses_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scope_path = root / "scope.json"
            scope_path.write_text("{}\n")
            profile = root / "round.profdata"
            profile.write_bytes(b"round-profile")
            (root / "coverage_summary.json").write_text(json.dumps({
                "profile_hash": cumulative.sha256(profile),
                "quality_status": "partial_warning", "warnings": ["source LLVM warning"]}))
            output_root = root / "unions"
            scope = {"scope_version": 1, "coverage_image": "sha256:" + "a" * 64,
                     "pytorch_commit": "b" * 40, "source_prefix": "/root/pytorch/aten/src/ATen/",
                     "objects": [], "object_build_ids": {}, "replay_batch_size": 2}
            calls = []

            def docker_run(argv, **kwargs):
                calls.append(argv)
                if len(calls) == 1:
                    return subprocess.CompletedProcess(argv, 1, "", "temporary export failure")
                mount = next(item for item in argv if item.endswith(":/output"))
                output = Path(mount.rsplit(":", 1)[0])
                (output / "coverage.profdata").write_bytes(b"merged-profile")
                value = {"scope_hash": cumulative.sha256(scope_path),
                         "profile_hash": cumulative.sha256(output / "coverage.profdata"),
                         "quality_status": "complete", "measurements": {
                             "lines": {"covered": 3, "total": 5},
                             "branches": {"covered": 2, "total": 4}}}
                return subprocess.CompletedProcess(argv, 0, json.dumps(value), "")

            with mock.patch.object(cumulative, "load_scope", return_value=scope), \
                 mock.patch.object(cumulative.subprocess, "run", side_effect=docker_run), \
                 mock.patch.object(cumulative, "cleanup_container", return_value=[]):
                with self.assertRaisesRegex(cumulative.CoverageError, "LLVM merge/export failed"):
                    cumulative.merge_profiles(scope_path, [profile], output_root)
                recovered = cumulative.merge_profiles(scope_path, [profile], output_root)
                cached = cumulative.merge_profiles(scope_path, [profile], output_root)
            self.assertIn("__attempt_002", recovered.as_posix())
            self.assertEqual(recovered, cached)
            self.assertEqual(len(calls), 2)
            self.assertTrue((output_root / recovered.parent.name / "merge.log").is_file())
            merged = json.loads(recovered.read_text())
            self.assertEqual(merged["quality_status"], "partial_warning")
            self.assertIn("source LLVM warning", merged["warnings"])


if __name__ == "__main__":
    unittest.main()
