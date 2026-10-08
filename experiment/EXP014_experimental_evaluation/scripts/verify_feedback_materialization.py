"""Isolated synthetic interface test, NOT an adaptive experiment or evidence of benefit.

Supply an existing short-run state. Only the decision trigger is synthetic;
budget validation, certificates, builders, compilation and preflight are real.
The second path injects a builder failure and checks retention of the parent.
All outputs are new and labelled; source run records remain untouched.
"""
from __future__ import annotations
import argparse
import copy
from dataclasses import replace
import json
from pathlib import Path
import sys
from unittest import mock

SCRIPT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_ROOT))
sys.path.insert(0, str(SCRIPT_ROOT.parents[1] / "EXP012_adaptive_feedback/scripts"))
import run_experiment_matrix as runner
import run_feedback_controller as controller


def verify(matrix_path, source_root, output, python):
    if output.exists() or not output.resolve().is_relative_to(runner.REPOSITORY_ROOT):
        raise ValueError("Use a new fixture output root inside the repository")
    matrix = runner.load_json(matrix_path)
    runner.validate_matrix(matrix)
    runner.verify_declared_file_refs(matrix)
    source = runner.load_json(source_root / "execution_index.json")
    entry = matrix["api_entries"][0]
    task = runner.Task(entry["api_id"], entry["target_api"], "bug_aware_adaptive", 1, 1, 1)
    task_state = source["tasks"][task.key]
    triplet = source["preparation"][task.api_id][task.group_id]
    arguments = runner.feedback_arguments(matrix, task_state, triplet, [], output / "fixture")
    resolved = controller.resolve_inputs(controller.parse_args(arguments))
    assessment = controller.assess_round(resolved)
    default = resolved.harness_spec["exploration_plan"]["default_branch_id"]
    diagnoses = []
    for diagnosis in assessment.branch_diagnoses:
        item = copy.deepcopy(diagnosis)
        item.update(primary_status="branch_healthy" if item["branch_id"] == default else "branch_activation_absent",
                    budget_evidence_usable=True, budget_recipient_evidence_usable=True,
                    budget_donor_evidence_usable=True)
        if item["branch_id"] != default:
            item["trigger_condition"] = {"fixture_only": True}
        diagnoses.append(item)
    fixture_assessment = replace(assessment, round_gate={"result": "eligible"}, branch_diagnoses=tuple(diagnoses))
    budget = controller.decide_budget(resolved, fixture_assessment)
    if budget["budget_action"] != "reallocate_budget":
        raise ValueError("Synthetic fixture did not exercise budget reallocation")
    request = controller.materialization_request(resolved, budget)
    output.mkdir(parents=True)
    request_path = output / "synthetic_materialization_request.json"
    runner.write_immutable_json(request_path, request)
    results = {}
    for mode in ("accepted", "rejected"):
        root = output / mode
        root.mkdir()
        state = copy.deepcopy(source)
        state.update(feedback={}, adaptive_current={})
        state_path = root / "fixture_execution_index.json"
        runner.persist_state(state_path, state)
        parent = runner.active_triplet(state, task).copy()
        def dispatch(*, materialization_result=None, **kwargs):
            if materialization_result is None:
                return {"status": "materialization_required", "request_path": str(request_path)}, {}
            materialized = controller.validate_materialization_result(
                runner.load_json(materialization_result), request, resolved, request_path)
            fixture_result = {"fixture_only": True, "status": "decision_recorded",
                              "materialization_outcome": materialized["outcome"], "run_disposition": "continue"}
            result_path = root / "fixture_controller_result.json"
            runner.write_immutable_json(result_path, fixture_result)
            return {**fixture_result, "decision_path": str(result_path)}, {}
        with mock.patch.object(runner, "call_feedback_controller", side_effect=dispatch):
            if mode == "rejected":
                with mock.patch.object(runner, "run_builder_step", side_effect=runner.RunnerError("fixture-only injected builder failure")):
                    runner.apply_feedback_after_round(matrix, entry, task, state_path, state, root, python)
            else:
                runner.apply_feedback_after_round(matrix, entry, task, state_path, state, root, python)
        next_task = runner.Task(task.api_id, task.target_api, task.group_id, 1, 2, 1)
        current = runner.active_triplet(state, next_task)
        outcome = state["feedback"][task.api_id]["repeat_001"]["round_001"]["materialization_outcome"]
        if outcome != mode or (current["artifact_path"] == parent["artifact_path"]) != (mode == "rejected"):
            raise ValueError("Materialization selection/parent retention did not match expected fixture outcome")
        results[mode] = {"outcome": outcome, "next_round_artifact": current["artifact_path"],
                         "parent_retained": current["artifact_path"] == parent["artifact_path"]}
    summary = {"fixture_only": True, "not_effectiveness_evidence": True,
               "synthetic_trigger_only": True, "status": "passed", "results": results}
    runner.write_immutable_json(output / "fixture_summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--source-run-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()
    print(json.dumps(verify(args.matrix.resolve(), args.source_run_root.resolve(), args.output_root.resolve(), args.python), indent=2))


if __name__ == "__main__":
    main()
