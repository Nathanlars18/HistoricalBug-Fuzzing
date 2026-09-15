#!/usr/bin/env python3
"""Deterministic tests for EXP011 Helper selection and prompt projection."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = Path(
    "experiment/EXP011_bug_aware_harness_synthesis/scripts/"
    "build_harness_spec_json.py"
)
SPEC = importlib.util.spec_from_file_location("build_harness_spec_json", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

COMMIT = "a" * 40


def api_profile(
    parameters: list[tuple[list[str], str]] | None = None,
    returns: list[tuple[list[str], str]] | None = None,
    *,
    callable_kind: str = "function",
    domains: list[str] | None = None,
    constraints: list[str] | None = None,
    binding_types: list[str] | None = None,
) -> dict:
    return {
        "profile_id": "api_pytorch_test_default",
        "revision": 1,
        "metadata": {"content_hash": "1" * 64},
        "target": {
            "framework": "pytorch",
            "framework_version": "2.10.0",
            "framework_commit": COMMIT,
            "backend_scope": ["cpu"],
            "python_api": "torch.test",
            "callable_kind": callable_kind,
        },
        "python_contract": {
            "parameters": [
                {
                    "normalized_types": normalized_types,
                    "semantic_role": semantic_role,
                }
                for normalized_types, semantic_role in (parameters or [])
            ],
            "returns": [
                {
                    "normalized_types": normalized_types,
                    "semantic_role": semantic_role,
                }
                for normalized_types, semantic_role in (returns or [])
            ],
            "documented_domains": [
                {"domain_kind": domain_kind} for domain_kind in (domains or [])
            ],
        },
        "target_binding": {
            "binding_parameters": [
                {"schema_type": schema_type}
                for schema_type in (binding_types or [])
            ]
        },
        "documented_constraints": [
            {"constraint_kind": constraint_kind}
            for constraint_kind in (constraints or [])
        ],
    }


def helper_profile(
    profile_id: str,
    qualified_name: str,
    capability_kind: str,
    return_role: str = "void",
    dependencies: list[str] | None = None,
    *,
    readiness: str = "ready",
    review_status: str = "approved",
    revision: int = 1,
    framework_commit: str = COMMIT,
) -> dict:
    return {
        "profile_id": profile_id,
        "revision": revision,
        "metadata": {"content_hash": (profile_id[-1] * 64)[:64]},
        "target_environment": {
            "framework": "pytorch",
            "framework_commit": framework_commit,
            "backend": "cpu",
        },
        "callable_interface": {
            "qualified_name": qualified_name,
            "return": {"semantic_role": return_role},
        },
        "capability_contract": {
            "capability_kind": capability_kind,
            "summary": f"Capability of {qualified_name}",
            "fuzz_input_contract": {},
            "domain_constraints": [],
            "behavior_claims": [],
            "side_effects": {"status": "none", "kinds": []},
            "determinism": "deterministic",
        },
        "build_contract": {
            "helper_dependencies": [
                {
                    "profile_id": dependency,
                    "qualified_name": dependency,
                    "resolution_status": "resolved",
                }
                for dependency in (dependencies or [])
            ]
        },
        "validation": {"execution_readiness": readiness},
        "review": {"review_status": review_status},
    }


def helper_ids(profiles: list[dict]) -> list[str]:
    return [profile["profile_id"] for profile in profiles]


class HelperSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dtype = helper_profile(
            "hp_dtype", "fuzzer_utils::parseDataType", "byte_decoder", "dtype"
        )
        self.rank = helper_profile(
            "hp_rank", "fuzzer_utils::parseRank", "byte_decoder", "rank"
        )
        self.shape = helper_profile(
            "hp_shape", "fuzzer_utils::parseShape", "byte_decoder", "shape"
        )
        self.data = helper_profile(
            "hp_data", "fuzzer_utils::parseTensorData", "byte_decoder", "byte_buffer"
        )
        self.create = helper_profile(
            "hp_create",
            "fuzzer_utils::createTensor",
            "tensor_constructor",
            "tensor",
            ["hp_dtype", "hp_rank", "hp_shape", "hp_data"],
        )
        self.compare = helper_profile(
            "hp_compare", "fuzzer_utils::compareTensors", "oracle"
        )
        self.log = helper_profile(
            "hp_log", "fuzzer_utils::logErrorMessage", "artifact_handler"
        )

    def test_requires_ready_and_approved(self) -> None:
        blocked = helper_profile(
            "hp_blocked", "example::blocked", "utility", readiness="blocked"
        )
        unreviewed = helper_profile(
            "hp_unreviewed",
            "example::unreviewed",
            "utility",
            review_status="unreviewed",
        )
        selection = MODULE.select_helper_profiles(
            api_profile(), [self.log, blocked, unreviewed]
        )
        self.assertEqual(helper_ids(selection.available), ["hp_log"])

    def test_tensor_dtype_shape_and_oracle_are_detailed_with_dependencies(self) -> None:
        api = api_profile(
            [
                (["tensor"], "input_tensor"),
                (["tensor"], "other_tensor"),
                (["dtype"], "dtype"),
                (["shape"], "shape"),
            ],
            [(["tensor"], "result_tensor")],
        )
        profiles = [
            self.log,
            self.compare,
            self.create,
            self.data,
            self.shape,
            self.rank,
            self.dtype,
        ]
        selection = MODULE.select_helper_profiles(api, profiles)
        self.assertEqual(
            set(helper_ids(selection.detailed)),
            {"hp_compare", "hp_create", "hp_dtype", "hp_shape"},
        )
        self.assertEqual(
            set(helper_ids(selection.dependencies)), {"hp_data", "hp_rank"}
        )
        self.assertEqual(helper_ids(selection.fallback), ["hp_log"])
        self.assertEqual(helper_ids(selection.available).count("hp_create"), 1)

    def test_scalar_dimension_does_not_promote_parse_rank(self) -> None:
        api = api_profile(
            [(["integer"], "dimension_selector"), (["scalar"], "scalar")],
            [(["scalar"], "scalar_result")],
        )
        selection = MODULE.select_helper_profiles(api, [self.rank, self.log])
        self.assertEqual(selection.detailed, [])
        self.assertEqual(helper_ids(selection.fallback), ["hp_log", "hp_rank"])

    def test_tensor_method_counts_implicit_self_for_relation_helpers(self) -> None:
        relation = helper_profile(
            "hp_relation", "example::relateTensors", "relation_enforcer"
        )
        api = api_profile(
            [(["tensor"], "other_tensor")], callable_kind="tensor_method"
        )
        selection = MODULE.select_helper_profiles(
            api,
            [self.dtype, self.rank, self.shape, self.data, self.create, relation],
        )
        self.assertIn("hp_relation", helper_ids(selection.detailed))

    def test_selection_is_order_independent_and_mode_independent(self) -> None:
        api = api_profile([(["tensor"], "input_tensor")])
        profiles = [self.dtype, self.rank, self.shape, self.data, self.create, self.log]
        first = MODULE.select_helper_profiles(api, profiles)
        second = MODULE.select_helper_profiles(api, list(reversed(profiles)))
        self.assertEqual(first.selection_hash, second.selection_hash)
        self.assertNotIn("mode", MODULE.select_helper_profiles.__code__.co_varnames)

    def test_unavailable_dependency_is_rejected(self) -> None:
        blocked_rank = helper_profile(
            "hp_rank", "fuzzer_utils::parseRank", "byte_decoder", "rank", readiness="blocked"
        )
        api = api_profile([(["tensor"], "input_tensor")])
        with self.assertRaisesRegex(MODULE.InputError, "depends on unavailable Helper"):
            MODULE.select_helper_profiles(
                api, [self.dtype, blocked_rank, self.shape, self.data, self.create]
            )

    def test_duplicate_active_revision_is_rejected(self) -> None:
        second = helper_profile(
            "hp_log", "fuzzer_utils::logErrorMessage", "artifact_handler", revision=2
        )
        with self.assertRaisesRegex(MODULE.InputError, "Multiple eligible revisions"):
            MODULE.select_helper_profiles(api_profile(), [self.log, second])

    def test_prompt_uses_three_tier_projection_and_reports_size(self) -> None:
        api = api_profile([(["tensor"], "input_tensor")])
        selection = MODULE.select_helper_profiles(
            api, [self.dtype, self.rank, self.shape, self.data, self.create, self.log]
        )
        prompt = MODULE.build_prompt({}, "rules", api, selection, [], "controlled_baseline", [], 50_000)
        self.assertIn('"detailed_profiles"', prompt)
        self.assertIn('"dependency_profiles"', prompt)
        self.assertIn('"fallback_profile_index"', prompt)
        with self.assertRaisesRegex(MODULE.InputError, "section_sizes="):
            MODULE.build_prompt({}, "rules", api, selection, [], "controlled_baseline", [], 10)


if __name__ == "__main__":
    unittest.main()
