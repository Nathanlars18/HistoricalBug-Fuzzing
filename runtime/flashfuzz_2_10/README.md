# FlashFuzz / PyTorch 2.10 Runtime

This directory is the project-owned configuration for the PyTorch 2.10 CPU
experiment runtime. It does not replace the preserved PyTorch 2.2 checkpoint
and it does not modify `third_party/FlashFuzz`.

## Current state

The base, fuzz-runtime, and coverage-runtime images have been built. One-API
smoke tests have passed for both fuzz execution and LLVM profile generation
using `torch.relu`.

## Pinned inputs

- FlashFuzz base commit: `c1c752963596528e4752360cdaeac77a80f7e07d`
- PyTorch tag: `v2.10.0`
- PyTorch commit: `449b1768410104d3ed79d3bcfe4ba1d65c7f22c0`
- Scope: CPU-only C++ Harness fuzzing and later source coverage collection.

## Directory roles

- `runtime_config.json`: machine-readable planned inputs, image names, and
  initial resource policy. It is not runtime evidence.
- `docker/torch-2.10-base.Dockerfile`: pins the source checkout and compiler
  foundation.
- `docker/torch-2.10-fuzz-runtime.Dockerfile`: builds the instrumented CPU
  PyTorch runtime without embedding generated Harnesses or project overlays.
- `docker/torch-2.10-cov-runtime.Dockerfile`: builds a separate CPU PyTorch
  runtime with LLVM source-coverage flags enabled; smoke testing confirmed
  `.profraw` generation, `.profdata` merge, and `llvm-cov-20 report` execution.
- `overlay/`: reserved for project-owned changes to the FlashFuzz execution
  path after the initial smoke test identifies an actual compatibility need.
- `generation/`: reserved for the separately pinned Python 2.10 API-profile
  and Harness-generation environment.

## Deliberate boundaries

- The 2.10 fuzz runtime is shared by Baseline, Static Knowledge, and Adaptive
  experiments. Those methods differ in Harness/Spec inputs, not target
  framework version.
- Coverage uses a separate PyTorch build directory and image because it needs
  `-fprofile-instr-generate` and `-fcoverage-mapping`.
- Generated corpora, binaries, build directories, coverage profiles, logs, and
  Docker image exports remain outside Git.

## Initial build policy

The first PyTorch build must use two parallel jobs. The host has 12 GB WSL
memory; higher parallelism may be considered only after a successful build and
recorded resource observation.
