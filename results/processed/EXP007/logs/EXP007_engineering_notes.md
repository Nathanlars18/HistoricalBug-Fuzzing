# LLM Harness Compilation Fix Log

## torch.add

Date:
2026-08-24

Original LLM generated harness:
testharness/torch_cpu/torch.add/main.cpp

Compilation environment:
PyTorch 2.2
clang

Errors:

1. std::complex<double> incompatible with torch::Scalar

Original:
std::complex<double>

Fix:
c10::complex<double>


2. Tensor.dtype() incompatible with torch::promote_types

Original:
input.dtype()

Fix:
input.scalar_type()


Reason:
PyTorch C++ API compatibility.

Scope:
Only compilation compatibility.
No mutation strategy / oracle / fuzzing logic changed.

## torch.mul

Original problem:
LLM generated Scalar-Tensor overload.

Compilation error:
at::mul(scalar, tensor)
at::mul_out(out, scalar, tensor)

Reason:
Python API supports Number * Tensor,
but ATen C++ API exposes Tensor * Scalar only.

Modification:
Changed scalar-first invocation to tensor-first invocation.

Files:
testharness/torch_cpu/torch.mul/main.cpp

Original:
main.llm_generated.cpp

Status:
Fixed

# Torch API Symlink Issue Fix (2026-08-24)

## Background

During EXP007 baseline fuzzing, newly added PyTorch APIs
(e.g., torch.cat) failed to start.

The original FlashFuzz workflow assumes that every API has
a top-level directory under /root/fuzz.

Example:

/root/fuzz/torch.relu
/root/fuzz/torch.mm

However, newly added APIs only existed as:

/root/fuzz/torch_cpu/torch.cat

without:

/root/fuzz/torch.cat


## Symptom

Running:

cd /root/fuzz/torch.cat
bash fuzz.sh

caused:

bash: fuzz.sh: No such file or directory


## Root Cause

The Docker image was built before newly added APIs were included.

The build process generated API entry points during image build,
but the existing image did not contain the new API symlinks.


## Temporary Fix

Modified FlashFuzz expmanager.py.

Before executing fuzzing, automatically create API symlink:

ln -sf torch_cpu/{api} {api}


Example:

ln -sf torch_cpu/torch.cat torch.cat


This allows EXP007 baseline experiments to run without rebuilding
the Docker image.


## Verification

torch.cat baseline test:

API:
torch.cat

Configuration:
PyTorch 2.2
CPU mode
30 seconds

Result:

Fuzzer exited with code: 0

Experiment completed successfully.


## Future Permanent Fix

After completing baseline experiments:

1. Modify build_test_harness.py
2. Generate API symlinks automatically during Docker image build
3. Rebuild torch2.2-fuzz Docker image
4. Verify all APIs have corresponding entry points


## Issue 2
reshape coverage missing
# 现象：
FileNotFoundError:
_cov_result/.../torch.reshape
# 原因：
coverage 阶段未生成 profraw。
# 处理：
单独补跑 coverage。

## torch.reshape baseline anomaly

During the 600s baseline fuzzing experiment,
torch.reshape generated two crash artifacts.

Artifacts:

- crash-592d0...
- crash-854d...

The crashes occurred during reshape execution
and caused libFuzzer termination.

Current analysis:
- The crash is triggered by fuzz-generated input.
- The current evidence does not confirm a PyTorch implementation bug.
- The artifacts are preserved for reproducibility.

Impact:
- The coverage phase terminated early because crash seeds
  affected corpus replay.

##  Issue:
Some coverage runs generated profraw files under
coverage_data/.work/run_0-600 instead of
coverage_data/0-600.

## Fix:
The analysis script was extended to detect both layouts.
No fuzzing results were regenerated.