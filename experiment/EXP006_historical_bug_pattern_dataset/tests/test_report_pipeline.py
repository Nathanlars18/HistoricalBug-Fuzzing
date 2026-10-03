"""Offline Report v5 tests: no network, model, or experiment writes."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_bug_report_json as report


class ReportV5Tests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name) / "repo"
        self.project.mkdir()
        mapping_path = self.project / "schemas" / "source_to_report_mapping.md"
        mapping_path.parent.mkdir(parents=True)
        mapping_path.write_text("# Source-to-Report Mapping v5.2\n", encoding="utf-8")
        schema_path = self.write("schemas/bug_report_record.schema.json", report.read_json(report.SCHEMA_PATH))
        for name, value in (("PROJECT_ROOT", self.project), ("OUTPUT_ROOT", self.project / "reports"),
                            ("MAPPING_PATH", mapping_path), ("SCHEMA_PATH", schema_path)):
            item = patch.object(report, name, value)
            item.start()
            self.addCleanup(item.stop)
        self.issue_path = self.write("raw/issue.json", {
            "number": 100, "html_url": "https://github.com/pytorch/pytorch/issues/100",
            "title": "torch.alpha and torch.beta produce the wrong value", "state": "closed",
            "created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-02T00:00:00Z",
            "closed_at": "2024-01-02T00:00:00Z", "labels": [],
            "body": "Call torch.alpha(x) with an empty tensor.\nThe returned value is 1, expected 0.",
        })
        comments_path = self.write("raw/comments.json", [{
            "body": "A maintainer notes that the bounds check is missing."
        }])
        self.capture_path = self.write("raw/capture.json", {
            "issue_path": str(self.issue_path), "comments_paths": [str(comments_path)],
            "comments_complete": True, "captured_at": "2026-01-01T00:00:00Z", "companions": [],
        })
        body_locator = {"artifact_path": str(self.issue_path), "locator_type": "json_string_line_range",
                        "value": "/body", "start_line": 1, "end_line": 1}
        failure_locator = {"artifact_path": str(self.issue_path), "locator_type": "json_string_line_range",
                           "value": "/body", "start_line": 2, "end_line": 2}
        self.inventory_path = self.write("manifests/inventory.json", {
            "inventory_version": "1.0", "protocol_version": "0.8", "inventory_id": "inventory_fixture",
            "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
            "collection_scope": {"repository": "pytorch/pytorch", "created_from": "2024-01-01",
                                 "created_to": "2024-12-31", "dataset_sources": [], "github_queries": []},
            "candidates": [{
                "candidate_id": "ic_pytorch_pytorch_100", "source_kind": "github_search",
                "repository": "pytorch/pytorch", "issue_number": 100,
                "canonical_url": "https://github.com/pytorch/pytorch/issues/100",
                "created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-02T00:00:00Z",
                "closed_at": "2024-01-02T00:00:00Z", "native_labels": [],
                "discovered_by": [{"kind": "github_search", "query": "fixture"}],
                "matched_api_terms": ["torch.alpha"],
                "snapshot": {"capture_path": str(self.capture_path),
                             "content_hash": report.sha256_file(self.capture_path),
                             "captured_at": "2026-01-01T00:00:00Z"},
                "duplicate_of": None,
                "screening": {"status": "admitted", "reason_codes": [], "reviewed_by": "fixture",
                              "reviewed_at": "2026-01-01T00:00:00Z",
                              "api_associations": [
                                  {"api_name": "torch.alpha", "relation": "affected", "source_locator": body_locator},
                                  {"api_name": "torch.beta", "relation": "mentioned", "source_locator": body_locator}],
                              "admission_gate_locators": {
                                  "trigger_conditions": [body_locator],
                                  "operation_contexts": [],
                                  "erroneous_behavior": [failure_locator]}}
            }],
        })

    def write(self, relative: str, value: object) -> Path:
        path = self.project / relative
        report.atomic_write(path, value)
        return path

    def test_schema_and_legacy_versions_load(self) -> None:
        import jsonschema
        jsonschema.Draft202012Validator.check_schema(report.schema_for("5.0"))
        for version in ("2.0", "3.0", "4.0", "5.0"):
            self.assertEqual(report.schema_for(version)["properties"]["schema_version"]["const"], version)

    def test_evidence_linked_and_closed_is_not_fixed(self) -> None:
        candidate = report.read_json(self.inventory_path)["candidates"][0]
        built = report.build_report(self.inventory_path, candidate, "2026-01-01T00:00:00Z")
        report.validate_report(built)
        self.assertEqual([item["relation"] for item in built["scope_assertions"]["api_assertions"]],
                         ["affected", "mentioned"])
        self.assertEqual(built["resolution"]["status"], "unknown")
        self.assertEqual(built["reported_behavior"]["reproduction"]["availability"], "unknown")
        self.assertTrue(any(
            item["field_path"] == "/reported_behavior/reproduction"
            for item in built["unresolved_information"]
        ))
        self.assertEqual(built["upstream_disposition"]["status"], "reported")
        self.assertNotIn("generation_method", built["provenance"])
        self.assertNotIn("extraction_run_ref", built["provenance"])

    def test_neutral_source_pool_is_addressable_but_not_promoted(self) -> None:
        candidate = report.read_json(self.inventory_path)["candidates"][0]
        built = report.build_report(self.inventory_path, candidate, "2026-01-01T00:00:00Z")
        artifacts = {item["artifact_id"]: item for item in built["source_bundle"]["source_artifacts"]}
        resolved = []
        for item in built["evidence_items"]:
            artifact = artifacts[item["source_artifact_ref"]]
            _, text = report.resolve_locator(
                {"artifact_path": artifact["local_path"], **item["locator"]}, report.PROJECT_ROOT
            )
            resolved.append(text)
        self.assertIn("torch.alpha and torch.beta produce the wrong value", resolved)
        self.assertIn("A maintainer notes that the bounds check is missing.", resolved)
        self.assertEqual(built["reported_diagnosis"]["root_cause_claims"], [])

    def test_repeated_build_reuses_revision(self) -> None:
        first = report.build_candidates(self.inventory_path, None, False)
        second = report.build_candidates(self.inventory_path, None, False)
        self.assertEqual(first[0]["status"], "generated")
        self.assertEqual(second[0]["status"], "reused")
        self.assertEqual(first[0]["output_path"], second[0]["output_path"])

    def test_revision_chain_validation(self) -> None:
        first = report.build_candidates(self.inventory_path, None, False)
        report.MAPPING_PATH.write_text("# Source-to-Report Mapping v5.2\nchanged\n", encoding="utf-8")
        second = report.build_candidates(self.inventory_path, None, False)
        self.assertEqual(first[0]["status"], "generated")
        self.assertEqual(second[0]["status"], "generated")
        directory = self.project / "reports" / "pytorch_pytorch" / "br_pytorch_pytorch_100"
        chain = report.validate_revision_chain(directory)
        self.assertEqual([item["revision_information"]["revision_number"] for item in chain], [1, 2])
        validation = report.validate_path(directory)
        self.assertEqual([item["status"] for item in validation], ["historical_valid", "valid"])
        self.assertTrue(validation[0]["warnings"])
        self.assertEqual(validation[0]["errors"], [])

    def test_admission_requires_api_and_both_gates(self) -> None:
        inventory = report.read_json(self.inventory_path)
        inventory["candidates"][0]["screening"]["api_associations"][0]["relation"] = "mentioned"
        with self.assertRaisesRegex(ValueError, "affected API"):
            report.inventory_contract.validate_inventory(inventory)
        inventory = report.read_json(self.inventory_path)
        inventory["candidates"][0]["screening"]["admission_gate_locators"]["erroneous_behavior"] = []
        with self.assertRaisesRegex(ValueError, "trigger/operation context and erroneous behavior"):
            report.inventory_contract.validate_inventory(inventory)

    def test_search_term_does_not_create_assertion(self) -> None:
        inventory = report.read_json(self.inventory_path)
        inventory["candidates"][0]["matched_api_terms"].append("torch.not_affected")
        built = report.build_report(self.inventory_path, inventory["candidates"][0], "2026-01-01T00:00:00Z")
        names = {item["api_name"] for item in built["scope_assertions"]["api_assertions"]}
        self.assertNotIn("torch.not_affected", names)

    def test_artifact_reregistration_preserves_metadata(self) -> None:
        store = report.EvidenceStore(self.project)
        artifact = store.add_artifact(
            self.issue_path, "issue", "github_issue", "100",
            "https://github.com/pytorch/pytorch/issues/100", "closed",
            "2026-01-01T00:00:00Z",
        )
        store.add_artifact(self.issue_path, "issue", "github_issue")
        item = store.artifacts[self.issue_path.resolve()]
        self.assertEqual(item["artifact_id"], artifact)
        self.assertEqual(item["external_id"], "100")
        self.assertEqual(item["url"], "https://github.com/pytorch/pytorch/issues/100")

    def test_oversized_evidence_uses_null_excerpt_without_truncation(self) -> None:
        body = "x" * 4500
        issue = report.read_json(self.issue_path)
        issue["body"] = body
        report.atomic_write(self.issue_path, issue)
        store = report.EvidenceStore(self.project)
        store.add_artifact(self.issue_path, "issue", "github_issue")
        evidence_id, resolved = store.add({
            "artifact_path": str(self.issue_path), "locator_type": "json_pointer",
            "value": "/body",
        })
        self.assertEqual(resolved, body)
        self.assertIsNone(store.evidence[evidence_id]["excerpt"])
        self.assertEqual(store.evidence[evidence_id]["content_hash"],
                         report.sha256_bytes(body.encode()))

    def test_primary_issue_identity_is_rechecked(self) -> None:
        candidate = report.read_json(self.inventory_path)["candidates"][0]
        built = report.build_report(self.inventory_path, candidate, "2026-01-01T00:00:00Z")
        built["identity"]["canonical_url"] = "https://github.com/pytorch/pytorch/issues/999"
        built["provenance"]["content_hash"] = report.content_hash(built)
        errors = report.semantic_errors(built)
        self.assertIn("primary source URL disagrees with Report identity", errors)
        self.assertIn("primary Issue URL disagrees with Report identity", errors)

    def test_linked_pr_needs_captured_patch_for_fix_proposed(self) -> None:
        pr_path = self.write("raw/pr_200.json", {
            "number": 200,
            "html_url": "https://github.com/pytorch/pytorch/pull/200",
            "title": "Fixes #100",
            "body": "Fixes #100",
            "merged": False,
        })
        capture = report.read_json(self.capture_path)
        capture["companions"] = [{
            "local_path": str(pr_path),
            "artifact_role": "resolution",
            "source_kind": "github_pull_request",
            "external_id": "200",
            "url": "https://github.com/pytorch/pytorch/pull/200",
        }]
        report.atomic_write(self.capture_path, capture)
        inventory = report.read_json(self.inventory_path)
        inventory["candidates"][0]["snapshot"]["content_hash"] = report.sha256_file(self.capture_path)
        candidate = inventory["candidates"][0]
        without_patch = report.build_report(self.inventory_path, candidate, "2026-01-01T00:00:00Z")
        self.assertEqual(without_patch["resolution"]["status"], "unknown")

        patch_path = self.write("raw/pr_200_files.json", [{
            "filename": "aten/src/ATen/example.cpp",
            "patch": "@@ -1 +1 @@\n-old\n+new",
        }])
        capture["companions"].append({
            "local_path": str(patch_path),
            "artifact_role": "resolution",
            "source_kind": "github_pull_request",
            "external_id": "200",
            "url": "https://github.com/pytorch/pytorch/pull/200/files",
        })
        report.atomic_write(self.capture_path, capture)
        inventory["candidates"][0]["snapshot"]["content_hash"] = report.sha256_file(self.capture_path)
        with_patch = report.build_report(self.inventory_path, inventory["candidates"][0],
                                         "2026-01-01T00:00:00Z")
        report.validate_report(with_patch)
        self.assertEqual(with_patch["resolution"]["status"], "fix_proposed")


if __name__ == "__main__":
    unittest.main()
