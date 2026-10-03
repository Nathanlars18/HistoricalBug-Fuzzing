"""Offline tests for the Issue candidate inventory contract."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import collect_issue_sources as collector


class CandidateInventoryTests(unittest.TestCase):
    def test_merge_deduplicates_discovery_routes(self) -> None:
        inventory = collector.new_inventory("pytorch/pytorch", "2020-01-01", "2024-12-31")
        issue = {"number": 12, "labels": [], "created_at": None, "updated_at": None, "closed_at": None}
        collector.merge_candidate(inventory, issue, {"kind": "external_dataset", "source_name": "fixture"}, ["torch.x"])
        collector.merge_candidate(inventory, issue, {"kind": "github_search", "query": "fixture"}, ["torch.x"])
        self.assertEqual(len(inventory["candidates"]), 1)
        self.assertEqual(inventory["candidates"][0]["source_kind"], "both")

    def test_search_hit_is_not_affected_assertion(self) -> None:
        inventory = collector.new_inventory("pytorch/pytorch", "2020-01-01", "2024-12-31")
        issue = {"number": 12, "labels": [], "created_at": None, "updated_at": None, "closed_at": None}
        collector.merge_candidate(inventory, issue, {"kind": "github_search", "query": "fixture"}, ["torch.x"])
        collector.validate_inventory(inventory)
        candidate = inventory["candidates"][0]
        self.assertEqual(candidate["matched_api_terms"], ["torch.x"])
        self.assertEqual(candidate["screening"]["api_associations"], [])

    def test_admitted_candidate_requires_locators(self) -> None:
        inventory = collector.new_inventory("pytorch/pytorch", "2020-01-01", "2024-12-31")
        issue = {"number": 12, "labels": [], "created_at": None, "updated_at": None, "closed_at": None}
        collector.merge_candidate(inventory, issue, {"kind": "github_search", "query": "fixture"}, [])
        inventory["candidates"][0]["screening"]["status"] = "admitted"
        with self.assertRaisesRegex(collector.InventoryError, "affected API"):
            collector.validate_inventory(inventory)

    def test_admitted_candidate_accepts_trigger_or_operation_context(self) -> None:
        inventory = collector.new_inventory("pytorch/pytorch", "2020-01-01", "2024-12-31")
        issue = {"number": 12, "labels": [], "created_at": None,
                 "updated_at": None, "closed_at": None}
        collector.merge_candidate(inventory, issue, {"kind": "github_search", "query": "fixture"}, [])
        candidate = inventory["candidates"][0]
        locator = {"artifact_path": "raw/issue.json", "locator_type": "json_pointer",
                   "value": "/body"}
        candidate["screening"].update({
            "status": "admitted", "api_associations": [{
                "api_name": "torch.alpha", "relation": "affected", "source_locator": locator}],
            "admission_gate_locators": {
                "trigger_conditions": [], "operation_contexts": [locator],
                "erroneous_behavior": [locator]},
        })
        collector.validate_inventory(inventory)

    def test_search_paginates_to_frozen_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            inventory_path = Path(directory) / "inventory.json"
            args = type("Args", (), {"inventory": inventory_path, "repository": "pytorch/pytorch",
                                      "created_from": "2020-01-01", "created_to": "2024-12-31",
                                      "api_term": ["torch.x"], "limit": 101})()
            pages = [
                {"total_count": 150, "items": [{"number": index, "labels": []} for index in range(1, 101)]},
                {"total_count": 150, "items": [{"number": 101, "labels": []}]},
            ]
            with patch.object(collector, "github_json", side_effect=pages) as request:
                collector.command_search(args)
            value = collector.read_json(inventory_path)
            self.assertEqual(request.call_count, 2)
            self.assertEqual(len(value["candidates"]), 101)
            self.assertFalse(value["collection_scope"]["github_queries"][0]["exhausted"])


if __name__ == "__main__":
    unittest.main()
