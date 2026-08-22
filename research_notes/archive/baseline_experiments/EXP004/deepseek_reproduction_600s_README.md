# DeepSeek-V4-Pro Reproduction

## Harness Generation

Model:
DeepSeek-V4-Pro

APIs:
- torch.add
- torch.addmm
- torch.exp
- torch.matmul
- torch.mm
- torch.mul
- torch.relu
- torch.sigmoid
- torch.softmax
- torch.tanh

Status:

10/10 harnesses generated successfully.

Generation path:

harness_generation/

# EXP004 Full Baseline 600s

## Goal

Reproduce FlashFuzz harness generation pipeline using DeepSeek-V4-Pro as LLM backend.

## Configuration

LLM:
DeepSeek-V4-Pro

Framework:
PyTorch 2.2

Backend:
CPU

Fuzzer:
libFuzzer

APIs:
10 PyTorch APIs

Time budget:
600s per API


## Harness Generation

All 10 APIs successfully generated C++ fuzz harnesses.

Compilation:
10/10 successful


## Fuzzing Results

Raw logs:
results/raw_logs/

Summary:
results/summary_600s.csv


Metrics:

- total executions
- execution throughput
- corpus growth
- peak memory usage
