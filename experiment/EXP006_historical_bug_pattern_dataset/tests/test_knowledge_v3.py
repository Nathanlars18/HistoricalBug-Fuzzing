import copy
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path


EXP006 = Path(__file__).resolve().parents[1]
SCRIPTS = EXP006 / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_knowledge_json as builder  # noqa: E402


class KnowledgeV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(
            (EXP006 / "schemas" / "knowledge_extraction_contract.json")
            .read_text(encoding="utf-8")
        )
        cls.required_pattern = json.loads(
            next(
                (EXP006 / "bug_patterns" / "v4" / "torch.compile")
                .glob("*.json")
            ).read_text(encoding="utf-8")
        )
        cls.unknown_pattern = json.loads(
            next(
                (
                    EXP006
                    / "bug_patterns"
                    / "v4"
                    / "torch.batch_norm_update_stats"
                ).glob("*.json")
            ).read_text(encoding="utf-8")
        )

    def candidate(self, context):
        condition_ref = next(
            ref
            for ref in context["available_evidence_refs"]
            if ":historical_condition:" in ref
        )
        return {
            "canonical_name": "boundary_behavior_hypothesis",
            "learned_hypothesis": {
                "statement": (
                    "Boundary states may expose unsafe or inconsistent "
                    "behavior in the target API."
                ),
                "abstraction_rationale": (
                    "The cited historical condition and observed failure "
                    "motivate bounded exploration without fixing the full "
                    "historical input."
                ),
                "evidence_status": "pattern_derived",
                "evidence_refs": [condition_ref],
                "limitations": []
            },
            "exploration_guidance": {
                "historical_anchors": [],
                "variation_opportunities": [
                    {
                        "statement": (
                            "Vary properties not established as necessary "
                            "while retaining a relevant boundary state."
                        ),
                        "evidence_status": "analyst_inferred",
                        "evidence_refs": [condition_ref]
                    }
                ],
                "observation_candidates": []
            }
        }

    def test_context_exposes_only_required_conditions_as_anchor_refs(self):
        context = builder.build_pattern_context(self.required_pattern)
        expected = {
            "pattern:"
            f"{context['pattern_id']}:historical_condition:tc_01",
            "pattern:"
            f"{context['pattern_id']}:historical_condition:tc_02"
        }
        self.assertEqual(set(context["required_condition_refs"]), expected)

    def test_unknown_condition_cannot_be_promoted_to_anchor(self):
        context = builder.build_pattern_context(self.unknown_pattern)
        self.assertEqual(context["required_condition_refs"], [])
        candidate = self.candidate(context)
        candidate["exploration_guidance"]["historical_anchors"] = [
            copy.deepcopy(
                candidate["exploration_guidance"][
                    "variation_opportunities"
                ][0]
            )
        ]
        with self.assertRaisesRegex(ValueError, "non-required"):
            builder.validate_candidate(candidate, context, self.contract)

    def test_valid_candidate_enriches_to_minimal_v3_record(self):
        context = builder.build_pattern_context(self.required_pattern)
        candidate = self.candidate(context)
        anchor_ref = context["required_condition_refs"][0]
        candidate["exploration_guidance"]["historical_anchors"] = [
            {
                "statement": "Retain the historically required compiled path.",
                "evidence_status": "pattern_derived",
                "evidence_refs": [anchor_ref]
            }
        ]
        candidate = builder.validate_candidate(
            candidate, context, self.contract
        )
        record = builder.enrich_final_knowledge(
            candidate,
            context,
            "kn_pt_pv4_boundary_behavior_hypothesis_k001",
            "test-model"
        )
        self.assertEqual(record["schema_version"], "3.0")
        self.assertEqual(
            record["scope"],
            {"framework": "pytorch", "target_api": "torch.compile"}
        )
        self.assertEqual(
            record["derivation_information"]["validation_status"],
            "structurally_validated"
        )
        self.assertEqual(
            record["derivation_information"]["mapping_version"],
            "3.1"
        )
        self.assertEqual(
            record["derivation_information"]["prompt_version"],
            "knowledge_extract_v3_1"
        )
        self.assertNotIn("risk_dimensions", json.dumps(record))
        self.assertNotIn("confidence", record)
        self.assertNotIn("applicability", record)

    def test_not_extractable_is_a_valid_envelope(self):
        response = {
            "status": "not_extractable",
            "reason": "The Pattern does not support a reusable hypothesis.",
            "knowledge": None
        }
        builder.validate_response_envelope(response)

    def test_duplicate_evidence_reference_is_rejected(self):
        context = builder.build_pattern_context(self.required_pattern)
        candidate = self.candidate(context)
        reference = candidate["learned_hypothesis"]["evidence_refs"][0]
        candidate["learned_hypothesis"]["evidence_refs"] = [
            reference,
            reference
        ]
        with self.assertRaisesRegex(ValueError, "duplicates"):
            builder.validate_candidate(candidate, context, self.contract)

    def test_old_mapping_does_not_block_regeneration(self):
        context = builder.build_pattern_context(self.required_pattern)
        candidate = builder.validate_candidate(
            self.candidate(context), context, self.contract
        )
        record = builder.enrich_final_knowledge(
            candidate,
            context,
            "kn_pt_pv4_boundary_behavior_hypothesis_k001",
            "test-model"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "knowledge.json"
            old_record = copy.deepcopy(record)
            old_record["derivation_information"]["mapping_version"] = "3.0"
            old_record["derivation_information"][
                "prompt_version"
            ] = "knowledge_extract_v3_0"
            path.write_text(
                json.dumps(old_record), encoding="utf-8"
            )
            self.assertFalse(
                builder.has_existing_knowledge_for_pattern(
                    directory,
                    context["pattern_id"],
                    context["pattern_hash"],
                    "test-model"
                )
            )
            path.write_text(json.dumps(record), encoding="utf-8")
            self.assertTrue(
                builder.has_existing_knowledge_for_pattern(
                    directory,
                    context["pattern_id"],
                    context["pattern_hash"],
                    "test-model"
                )
            )

    def test_document_json_examples_parse(self):
        text = (
            EXP006 / "schemas" / "knowledge_schema.md"
        ).read_text(encoding="utf-8")
        for block in re.findall(r"```json\n(.*?)\n```", text, flags=re.S):
            json.loads(block)


if __name__ == "__main__":
    unittest.main()
