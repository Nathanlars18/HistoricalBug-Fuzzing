"""Offline Pattern v4 regressions; fixtures are synthetic research-neutral data."""
import copy
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

EXP006 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXP006 / "scripts"))
import batch_build_patterns as batch_patterns
import build_knowledge_json as knowledge
import build_pattern_json as pattern


class PatternTaxonomyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = pattern.load_json(pattern.CONTRACT_FILE)

    def setUp(self):
        network = patch.object(pattern.requests, "post", side_effect=AssertionError("network forbidden"))
        network.start()
        self.addCleanup(network.stop)
        self.context = {
            "report_id": "br_fixture",
            "report_revision": 1,
            "framework": "pytorch",
            "selected_api": "torch.fixture",
            "available_evidence_refs": ["ev_fixture"],
        }
        self.candidate = copy.deepcopy(self.contract["response_template"]["patterns"][0])
        self.candidate["canonical_name"] = "fixture_behavior"
        self.candidate["scope"]["target_api"] = "torch.fixture"
        self.candidate["provenance"] = {
            "source_report": {"report_id": "br_fixture"},
            "abstraction_rationale": "Synthetic evidence fixture.",
            "unresolved_information": [],
        }
        self.candidate["observed_failure"].update(
            description="The fixture reports an incorrect result.",
            symptom_category="incorrect_functionality",
            evidence_refs=["ev_fixture"],
        )

    def validate(self):
        pattern.validate_candidate(self.candidate, self.context, self.contract)

    def record(self):
        self.validate()
        return pattern.enrich_final_pattern(
            copy.deepcopy(self.candidate),
            self.context,
            "sha256:fixture",
            "pt_v4_fixture_p001",
            "offline_fixture",
        )

    def test_versions_and_published_vocabularies(self):
        self.assertEqual(pattern.SCHEMA_VERSION, "4.0")
        self.assertEqual(self.contract["contract_version"], pattern.MAPPING_VERSION)
        vocab = self.contract["controlled_vocabularies"]
        self.assertEqual(len(vocab["root_cause_categories"]), 13)
        self.assertEqual(len(vocab["symptom_categories"]), 6)
        self.assertNotIn("trigger_dimensions", vocab)
        self.assertNotIn("historical_oracle_kinds", vocab)
        self.assertNotIn("confidence", vocab)
        kc = knowledge.load_json(knowledge.CONTRACT_FILE)
        self.assertEqual(kc["input_assumptions"]["pattern_schema_version"], "4.0")
        self.assertEqual(kc["contract_version"], knowledge.MAPPING_VERSION)

    def test_contract_preserves_field_role_boundaries(self):
        rules = "\n".join(self.contract["semantic_rules"])
        self.assertIn("Do not place an implementation defect", rules)
        self.assertIn("must not be duplicated across fields", rules)
        self.assertIn("Do not repeat invocation or input facts", rules)

    def test_nullable_mechanism_and_taxonomy_labels(self):
        self.validate()
        self.assertIsNone(self.candidate["defect_mechanism"])
        mechanism = copy.deepcopy(self.contract["optional_object_templates"]["defect_mechanism"])
        mechanism.update(description="Synthetic supported mechanism.", evidence_refs=["ev_fixture"])
        self.candidate["defect_mechanism"] = mechanism
        self.validate()
        for category in self.contract["controlled_vocabularies"]["root_cause_categories"]:
            with self.subTest(category=category):
                mechanism["root_cause_category"] = category
                self.validate()
        mechanism["root_cause_category"] = "dtype_boundary"
        with self.assertRaises(ValueError):
            self.validate()

    def test_single_nullable_symptom(self):
        self.validate()
        self.candidate["observed_failure"]["symptom_category"] = None
        self.validate()
        self.candidate["observed_failure"]["symptom_category"] = ["crash", "hang"]
        with self.assertRaises(ValueError):
            self.validate()

    def test_historical_conditions_are_free_text_and_conservative(self):
        condition = copy.deepcopy(self.contract["array_item_templates"]["historical_condition"])
        condition.update(statement="The historical case used an empty input.", evidence_refs=["ev_fixture"])
        self.candidate["historical_conditions"] = [condition]
        self.validate()
        condition["necessity"] = "mandatory"
        with self.assertRaises(ValueError):
            self.validate()
        condition["necessity"] = "unknown"
        condition["dimension"] = "shape"
        with self.assertRaisesRegex(ValueError, "unsupported keys"):
            self.validate()

    def test_removed_v3_fields_are_rejected(self):
        for key in ["trigger_signature", "confidence", "defect_classification"]:
            candidate = copy.deepcopy(self.candidate)
            candidate[key] = {}
            with self.subTest(key=key), self.assertRaises(ValueError):
                pattern.validate_candidate(candidate, self.context, self.contract)
        self.candidate["scope"]["primary_api"] = "torch.fixture"
        with self.assertRaises(ValueError):
            self.validate()

    def test_script_owned_ids_and_knowledge_context(self):
        condition = copy.deepcopy(self.contract["array_item_templates"]["historical_condition"])
        condition.update(statement="Historical condition.", evidence_refs=["ev_fixture"])
        observation = copy.deepcopy(self.contract["array_item_templates"]["historical_observation"])
        observation.update(statement="Historical comparison.", evidence_refs=["ev_fixture"])
        self.candidate["historical_conditions"] = [condition]
        self.candidate["observed_failure"]["historical_observations"] = [observation]
        record = self.record()
        self.assertEqual(record["historical_conditions"][0]["condition_id"], "tc_01")
        self.assertEqual(record["observed_failure"]["historical_observations"][0]["observation_id"], "ho_01")
        before = copy.deepcopy(record)
        context = knowledge.build_pattern_context(record)
        self.assertEqual(record, before)
        self.assertEqual(context["target_api"], "torch.fixture")
        self.assertEqual(context["required_condition_refs"], [])
        self.assertIn("pattern:pt_v4_fixture_p001:historical_conditions", context["available_evidence_refs"])

    def test_builder_owns_exact_semantic_evidence_union(self):
        self.context["available_evidence_refs"].append("ev_other")
        mechanism = copy.deepcopy(self.contract["optional_object_templates"]["defect_mechanism"])
        mechanism.update(description="Synthetic supported mechanism.", evidence_refs=["ev_other"])
        self.candidate["defect_mechanism"] = mechanism
        record = self.record()
        self.assertEqual(
            record["provenance"]["source_report"]["evidence_refs"],
            ["ev_fixture", "ev_other"],
        )
        pattern.validate_stored_pattern(record, self.contract)

        record["provenance"]["source_report"]["evidence_refs"] = ["ev_fixture"]
        with self.assertRaisesRegex(ValueError, "must equal the evidence union"):
            pattern.validate_stored_pattern(record, self.contract)

    def test_candidate_cannot_declare_provenance_evidence_union(self):
        self.candidate["provenance"]["source_report"]["evidence_refs"] = ["ev_fixture"]
        with self.assertRaisesRegex(ValueError, "unsupported keys"):
            self.validate()

    def test_stored_record_rejects_duplicate_item_ids(self):
        condition = copy.deepcopy(self.contract["array_item_templates"]["historical_condition"])
        condition.update(statement="Historical condition.", evidence_refs=["ev_fixture"])
        self.candidate["historical_conditions"] = [condition, copy.deepcopy(condition)]
        record = self.record()
        record["historical_conditions"][1]["condition_id"] = "tc_01"
        with self.assertRaisesRegex(ValueError, "Duplicate condition_id"):
            knowledge.build_pattern_context(record)

    def test_skip_checks_current_version_and_exact_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            current = self.record()
            with patch.object(pattern.os, "listdir", return_value=["fixture.json"]), patch.object(
                pattern, "load_json", return_value=current
            ):
                self.assertTrue(pattern.has_existing_pattern_for_report(directory, "br_fixture", "sha256:fixture"))
                self.assertFalse(pattern.has_existing_pattern_for_report(directory, "br_fixture", "sha256:changed"))
                current["derivation_information"]["mapping_version"] = "4.0"
                self.assertFalse(pattern.has_existing_pattern_for_report(directory, "br_fixture", "sha256:fixture"))

    def test_batch_discovers_only_affected_apis_from_latest_revision(self):
        paths = [Path("a/revision_001.json"), Path("a/revision_002.json")]
        reports = [
            {"identity": {"report_id": "r"}, "revision_information": {"revision_number": 1},
             "scope_assertions": {"api_assertions": [{"api_name": "torch.old", "relation": "affected"}]}},
            {"identity": {"report_id": "r"}, "revision_information": {"revision_number": 2},
             "scope_assertions": {"api_assertions": [
                 {"api_name": "torch.fixture", "relation": "affected"},
                 {"api_name": "torch.mentioned", "relation": "mentioned"}]}},
        ]
        with patch.object(pattern.Path, "rglob", return_value=paths), patch.object(
            pattern, "load_json", side_effect=reports
        ):
            self.assertEqual(batch_patterns.discover_apis(), ["torch.fixture"])

    def test_ids_and_paths_are_version_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(pattern.next_pattern_id(directory, "pytorch", "fixture"), "pt_v4_fixture_p001")
            self.assertEqual(knowledge.next_knowledge_id(directory, "pytorch", "fixture"), "kn_pt_pv4_fixture_k001")
        self.assertEqual(Path(pattern.DEFAULT_OUTPUT_DIR).name, "v4")
        self.assertEqual(knowledge.PATTERN_DIR, pattern.DEFAULT_OUTPUT_DIR)
        self.assertEqual(Path(knowledge.DEFAULT_OUTPUT_DIR).name, "v3")

    def test_document_json_examples_parse(self):
        text = (EXP006 / "schemas" / "pattern_schema.md").read_text(encoding="utf-8")
        for block in re.findall(r"```json\n(.*?)\n```", text, flags=re.S):
            json.loads(block)


if __name__ == "__main__":
    unittest.main()
