from __future__ import annotations

import unittest

from experiment.EXP013_crash_triage_and_result_analysis.scripts.case_semantics import (
    analysis_complete,
    analysis_subject_hash,
    diagnostic_signature,
    reproduction_status,
)
from experiment.EXP013_crash_triage_and_result_analysis.scripts.replay_executor import trace_sites


class CaseSemanticsTests(unittest.TestCase):
    def test_trace_is_bound_to_exact_replay_input(self) -> None:
        trace = (
            '{"iteration":0,"input_hex":"00ff","sites_truncated":false,"runtime_site_ids":[1,2]}\n'
            '{"iteration":1,"input_hex":"abcd","sites_truncated":false,"runtime_site_ids":[9]}\n'
        )
        self.assertEqual(trace_sites(trace, bytes.fromhex("00ff")), [1, 2])
        self.assertEqual(trace_sites(trace, bytes.fromhex("ffff")), [])

    def test_signature_keeps_stack_frames_but_ignores_fuzzer_progress(self) -> None:
        first = "#17 cov: 3 ft: 4\n#0 0x1234 in at::native::run /tmp/build-one/src.cpp:8\n"
        second = "#99 cov: 20 ft: 30\n#0 0xabcd in at::native::run /opt/build-two/src.cpp:8\n"
        self.assertEqual(diagnostic_signature("process_termination", "abort", first),
                         diagnostic_signature("process_termination", "abort", second))

    def test_replay_status_requires_five_valid_attempts(self) -> None:
        policy = {"replay": {
            "required_valid_attempts": 5,
            "automatic_success_equivalence": ["exact_match"],
            "reviewed_success_equivalence": ["exact_match", "semantically_equivalent"],
            "completed_status_by_success_count": {"0": "not_reproduced", "1": "weak", "2": "intermittent", "3": "intermittent", "4": "stable", "5": "stable"},
        }}
        attempts = [{"valid_attempt": True, "equivalence_status": "exact_match"} for _ in range(4)]
        self.assertEqual(reproduction_status(attempts, policy), "inconclusive")
        attempts.append({"valid_attempt": True, "equivalence_status": "different"})
        self.assertEqual(reproduction_status(attempts, policy), "stable")

    def test_legacy_cases_are_not_silently_complete(self) -> None:
        self.assertFalse(analysis_complete({"record_format_version": "1.1"}))

    def test_reviewed_rejection_is_complete_without_an_anomaly_cluster(self) -> None:
        record = {
            "record_format_version": "1.2", "capture_record": {"policy_snapshot": {"policy_id": "p"}},
            "deduplication": {"case_role": "unassigned", "status": "pending", "cluster_id": None, "representative_case_ref": None, "assignment_kind": "not_assigned", "exact_fingerprint": None},
            "workflow_status": "closed", "human_review": {"status": "completed", "conclusion": "accepted", "reviewed_aspects": ["admission", "fault_attribution", "final_case"], "reviewed_subject_hash": None},
            "admission": {"status": "rejected"}, "fault_attribution": {"status": "not_assessed"},
            "reproduction": {"status": "not_attempted", "attempts": []}, "unresolved_questions": [],
        }
        record["human_review"]["reviewed_subject_hash"] = analysis_subject_hash(record)
        self.assertTrue(analysis_complete(record))

    def test_open_admitted_case_needs_a_completed_exact_cluster(self) -> None:
        record = {
            "record_format_version": "1.2", "capture_record": {"policy_snapshot": {"policy_id": "p"}},
            "deduplication": {"case_role": "unassigned", "status": "pending", "cluster_id": None, "representative_case_ref": None, "assignment_kind": "not_assigned", "exact_fingerprint": None},
            "workflow_status": "closed", "human_review": {"status": "completed", "conclusion": "accepted", "reviewed_aspects": ["admission", "fault_attribution", "final_case"], "reviewed_subject_hash": None},
            "admission": {"status": "admitted"}, "fault_attribution": {"status": "harness"},
            "reproduction": {"status": "not_attempted", "attempts": []}, "unresolved_questions": [],
        }
        record["human_review"]["reviewed_subject_hash"] = analysis_subject_hash(record)
        self.assertFalse(analysis_complete(record))

    def test_analysis_hash_excludes_derived_reproduction_status(self) -> None:
        base = {"reproduction": {"status": "weak", "attempts": [{"ordinal": 1}]}}
        changed = {"reproduction": {"status": "stable", "attempts": [{"ordinal": 1}]}}
        self.assertEqual(analysis_subject_hash(base), analysis_subject_hash(changed))
        changed["reproduction"]["attempts"][0]["ordinal"] = 2
        self.assertNotEqual(analysis_subject_hash(base), analysis_subject_hash(changed))


if __name__ == "__main__":
    unittest.main()
