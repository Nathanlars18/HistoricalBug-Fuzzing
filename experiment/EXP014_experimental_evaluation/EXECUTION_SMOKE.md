# Two-API execution-interface checkpoint

This is a pipeline test, not a formal method-effectiveness experiment. It reuses
approved initial Spec/Strategy semantics without LLM calls. Historical frozen
matrices and generated records must not be overwritten or silently rehashed.

The recommended schedule is two APIs, three groups, one independent repeat,
three 15-second rounds (18 tasks, 270 requested fuzzing seconds). Compilation,
Coverage Replay, cumulative export and candidate replay are outside this budget.
Round-end Corpus coverage and cumulative profile-union coverage are diagnostic
only. LLVM warnings, missing profiles, capture saturation and incomplete crash
analysis remain explicit; no such state is automatically a PyTorch bug.

The checkout contains `two_api_operational_smoke__v010.json`; its interrupted
run is retained as historical evidence. The v011 matrix was an intermediate
snapshot made before the final compatibility adjustment. Use a fresh v012
matrix and run directory so all frozen references match the final code:

```bash
exp014_root=experiment/EXP014_experimental_evaluation
.venv/bin/python -B "$exp014_root/scripts/build_two_api_execution_smoke_draft.py" \
  --operational-smoke --smoke-id pytorch_2_10_operational_smoke_v012 \
  --output "$exp014_root/configs/two_api_operational_smoke__v012.json" \
  --target-output "$exp014_root/configs/evaluation_target_manifest__operational_smoke_v012.json" \
  --round-count 3 --active-seconds 15 --enable-coverage \
  --analysis-cutoff-delay-seconds 900
```

Once generated, do NOT regenerate this matrix. Execute the phases in order;
stop on errors instead of continuing into the next phase:

```bash
set -euo pipefail
exp014_root=experiment/EXP014_experimental_evaluation
matrix_path="$exp014_root/configs/two_api_operational_smoke__v012.json"
run_root="$exp014_root/runs/two_api_operational_smoke_v012"
.venv/bin/python -B "$exp014_root/scripts/run_experiment_matrix.py" --matrix "$matrix_path" --run-root "$run_root" --phase validate
.venv/bin/python -B "$exp014_root/scripts/run_experiment_matrix.py" --matrix "$matrix_path" --run-root "$run_root" --phase plan
.venv/bin/python -B "$exp014_root/scripts/run_experiment_matrix.py" --matrix "$matrix_path" --run-root "$run_root" --phase prepare
.venv/bin/python -B "$exp014_root/scripts/run_experiment_matrix.py" --matrix "$matrix_path" --run-root "$run_root" --phase execute --resume
.venv/bin/python -B "$exp014_root/scripts/run_experiment_matrix.py" --matrix "$matrix_path" --run-root "$run_root" --phase finalize --resume
```

To continue a supported interrupted phase, rerun that phase with the same paths
and `--resume`. In particular, both `execute` and `finalize` require `--resume`
after `prepare` has created the execution index.
Do not delete failed attempt evidence or automatically reclaim unknown consumed
budgets. The matrix pins one thread for OMP/MKL/OpenBLAS during round execution;
round configuration and Coverage summaries record the effective environment.

Analyze without requiring completed manual triage first:

```bash
.venv/bin/python -B "$exp014_root/scripts/analyze_experiment_results.py" \
  --matrix "$matrix_path" \
  --target-manifest "$exp014_root/configs/evaluation_target_manifest__operational_smoke_v012.json" \
  --run-root "$run_root" --case-root "$run_root/crash_cases/cases" \
  --output-root "$run_root/analysis"
```

The Analyzer computes cumulative unions at this step, retaining profdata,
input hashes and logs under `run_root/coverage_cumulative`. A cumulative failure
does not invalidate already completed fuzz rounds. Tables include
`coverage_diagnostics.csv`, `coverage_cumulative.csv`, `candidate_capture.csv`.
Before the fixed 900-second cutoff the window is provisional. Missing Cases
or pending reviews produce unavailable anomaly yields, not zero defects.

Candidate intake and exact deduplication, when requested, are separate:

```bash
crash_script=experiment/EXP013_crash_triage_and_result_analysis/scripts/analyze_crash_cases.py
.venv/bin/python -B "$crash_script" --output-root "$run_root/crash_cases" \
  ingest --execution-index "$run_root/execution_index.json"
.venv/bin/python -B "$crash_script" --output-root "$run_root/crash_cases" \
  deduplicate --round-root "$run_root/rounds"
```

Representative replay still requires the exact selected Case ID and source
Artifact; human fault attribution is not replaced by replay stability.

For an isolated feedback-materialization interface test using an existing
completed short run, use a NEW fixture root:

```bash
.venv/bin/python -B "$exp014_root/scripts/verify_feedback_materialization.py" \
  --matrix "$matrix_path" \
  --source-run-root "$exp014_root/runs/two_api_operational_smoke_v005" \
  --output-root "$exp014_root/runs/feedback_interface_smoke_v007"
```

This explicitly synthetic trigger tests real budget-only derivation,
certificates, compilation/preflight and next-round selection, plus an injected
builder failure and parent retention. It is not an observed adaptive benefit,
and its files are never admitted as experimental feedback records.

Do not promote this smoke run to a formal sample. A longer three-by-300-second
schedule may be frozen later with a NEW matrix; independent repeats and sample
eligibility must be specified separately from round count.
