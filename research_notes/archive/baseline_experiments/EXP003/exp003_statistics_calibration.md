# Exp003 FlashFuzz Statistics Calibration
## 08 05
## Problem

Original FlashFuzz reproduction results showed abnormal validity statistics.

Example:
torch.mm:
rounds=118274
invalid=152014

invalid > rounds indicates duplicated log parsing.

## Root Cause

fuzz.sh used:

tee -a fuzz-0.log

which appended logs between repeated executions.

## Fix

1. Change append mode to overwrite mode.
2. Set WORKERS=1.
3. Remove old fuzz log before execution.
4. Add independent statistics collector.

## Status

Need rerun clean baseline.

2026-08-05

发现 FlashFuzz 原始 fuzz.sh:
- WORKERS=2
- tee -a追加日志

导致:
- fuzz-0.log包含两个libFuzzer worker输出
- stat::number_of_executed_units重复
- Exception caught数量超过rounds
- validity_ratio出现负值

修复:
- WORKERS=1
- tee覆盖写
- 每次实验删除旧log

保存镜像:
flashfuzz-torch22-clean-image

torch.add 60s clean run:
rounds = 9500
invalid = 2883
valid = 6617
validity_ratio = 0.696526
stat_entry_count = 1
done_entry_count = 1
statistics_status = OK

Conclusion:
The clean FlashFuzz torch2.2 image successfully avoids duplicated libFuzzer statistics.
The previous negative valid-count problem was caused by duplicated/appended logs, not by the API itself.

### First clean 60s repeated trials

We ran three independent 60-second trials for three representative PyTorch APIs:
torch.add, torch.mm, and torch.matmul.

All 9 runs produced exactly one `Done` marker and one `stat::number_of_executed_units` marker.
No run was marked as INCOMPLETE or INCONSISTENT by the new statistics parser.

This confirms that the previous negative-validity problem was caused by duplicated/appended fuzzing logs rather than by the API behavior itself.

Summary:
- torch.add: average validity_ratio = 0.697629
- torch.mm: average validity_ratio = 0.444010
- torch.matmul: average validity_ratio = 0.080365

The observed differences are consistent with API input constraints:
torch.add has relatively permissive tensor broadcasting constraints,
torch.mm requires valid 2D matrix multiplication dimensions,
and torch.matmul has more complex dimensional and broadcasting rules, leading to a much lower valid-input ratio.

## Exp003: Clean 60s FlashFuzz Baseline Statistics Calibration

### Goal

The goal of this experiment is to verify whether the cleaned FlashFuzz baseline can produce trustworthy validity statistics after fixing the duplicated/appended fuzzing log problem observed in earlier runs.

In previous exploratory 300-second runs, several APIs produced inconsistent statistics. For example, the number of invalid inputs could exceed the reported number of executed units, causing negative valid counts. Further inspection showed that the problem was caused by duplicated libFuzzer output and appended logs rather than by the API behavior itself.

### Fixes Applied

We created and used a clean FlashFuzz torch2.2 fuzzing image with the following fixes:

- Set `WORKERS=1` instead of `WORKERS=2`.
- Changed `tee -a "$LOG"` to `tee "$LOG"` to avoid appending to old logs.
- Added `rm -f "$LOG"` before each fuzzing run to remove stale logs.
- Patched both the per-API fuzz scripts and the template script used by `build_test_harness.py`.

The clean image used in this experiment is:

```text
ncsuswat/flashfuzz:torch2.2-fuzz-clean
Experimental Setup
We selected 10 representative PyTorch APIs:
torch.add
torch.mul
torch.matmul
torch.mm
torch.addmm
torch.relu
torch.sigmoid
torch.softmax
torch.tanh
torch.exp
Each API was fuzzed for 3 independent 60-second trials.
Total number of runs:
10 APIs × 3 trials = 30 runs
The results were stored under:
_fuzz_result/exp003_clean_60s_trials/
Statistics Definition
For each run, we computed:
rounds = stat::number_of_executed_units
invalid = number of "Exception caught:" entries
valid = rounds - invalid
validity_ratio = valid / rounds
We also checked whether each log contained exactly one final libFuzzer statistics entry:
stat_entry_count = 1
done_entry_count = 1
A run is considered trustworthy only if:
statistics_status = OK
Result Summary
API	n	rounds_mean	invalid_mean	valid_mean	validity_ratio_mean
torch.add	3	13656.333	4129.000	9527.333	0.697629
torch.addmm	3	5880.333	1277.000	4603.333	0.782017
torch.exp	3	32485.667	7580.000	24905.667	0.765752
torch.matmul	3	9285.667	8539.000	746.667	0.080365
torch.mm	3	20428.667	11282.333	9146.333	0.444010
torch.mul	3	6815.000	1202.667	5612.333	0.823839
torch.relu	3	34690.667	7455.000	27235.667	0.769559
torch.sigmoid	3	45769.000	8215.333	37553.667	0.816905
torch.softmax	3	43329.333	13296.000	30033.333	0.691723
torch.tanh	3	32079.667	15426.667	16653.000	0.519260


Key Findings
All 30 runs were successfully parsed by the new statistics checker.
For all runs:
statistics_status = OK
stat_entry_count = 1
done_entry_count = 1
This confirms that the previous negative-validity issue was caused by duplicated/appended logs rather than by the APIs themselves.
The clean FlashFuzz torch2.2 baseline now provides trustworthy validity statistics and can be used as the baseline for later comparison with Historical Bug Pattern enhanced harnesses.
Observations
The validity ratio differs significantly across APIs.
Element-wise APIs such as torch.mul, torch.sigmoid, torch.exp, and torch.relu generally have higher validity ratios because their input constraints are relatively permissive.
Matrix-related APIs such as torch.mm and especially torch.matmul have lower validity ratios because they require stricter shape, rank, and broadcasting constraints.
The very low validity ratio of torch.matmul suggests that shape-aware or historical bug pattern guided harness generation may have a large opportunity to improve valid input generation for complex APIs.O

