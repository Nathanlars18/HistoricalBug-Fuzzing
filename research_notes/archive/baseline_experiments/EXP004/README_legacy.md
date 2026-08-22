# Exp004 Full FlashFuzz Baseline (600s)

## Configuration

- Framework: PyTorch
- Version: 2.2
- Backend: CPU
- Mode: fuzz
- Time budget: 600s
- Parallel workers: 1 per API

## API

torch.add

## Result

rounds: 201886
invalid: 111832
valid: 90054
validity_ratio: 0.446064

# Exp004 Full FlashFuzz Baseline Evaluation

## Goal

Reproduce FlashFuzz fuzzing pipeline on PyTorch CPU APIs
and collect baseline metrics for later historical bug pattern enhancement.

## Configuration

Framework:
PyTorch

Version:
2.2

Backend:
CPU

Mode:
fuzz

Time budget:
600 seconds per API

Parallel:
1


## APIs

10 PyTorch APIs:

torch.add
torch.addmm
torch.exp
torch.matmul
torch.mm
torch.mul
torch.relu
torch.sigmoid
torch.softmax
torch.tanh


## Metrics

Collected:

- fuzz rounds
- invalid inputs
- valid inputs
- validity ratio


## Observation

Simple tensor operators achieve higher validity ratio.

For APIs requiring semantic constraints
(e.g., torch.matmul, torch.mm),
randomly generated inputs often fail to satisfy
shape compatibility constraints.


## Result

See:

summary_by_api.csv

## Analysis

### Overall observation

The baseline results show that FlashFuzz can generate a large number of fuzzing executions, but the quality of generated inputs varies significantly across different APIs.

## DeepSeek-V4-Pro Harness Generation Result

Generated harnesses:

10/10 APIs

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

Generation directory:

deepseek_reproduction/harness_generation/

Status:

Successfully generated.
The validity ratio ranges from 0% to 80.7%, indicating that API semantic constraints strongly affect the effectiveness of generated harnesses.


### Simple tensor APIs

For APIs with relatively simple input constraints, FlashFuzz achieves higher validity ratios.

Examples:

- torch.mul: 0.807
- torch.sigmoid: 0.621
- torch.addmm: 0.596

These APIs mainly require valid tensor inputs and have fewer cross-parameter dependencies.


### APIs with complex semantic constraints

Some APIs require stronger relationships between multiple inputs.

Examples:

- torch.matmul: 0.000
- torch.mm: 0.000

Both APIs require matrix dimension compatibility:

A.shape[-1] == B.shape[-2]

However, randomly generated inputs frequently violate this constraint, causing invalid executions.

This indicates that generated harnesses may lack deep semantic understanding of API input requirements.


### Intermediate complexity APIs

Some APIs show medium validity ratios:

- torch.softmax: 0.498
- torch.relu: 0.536
- torch.exp: 0.557

These APIs have additional constraints such as dimension parameters or tensor properties.


### Motivation for historical bug pattern enhancement

The baseline results suggest that improving input validity alone is not sufficient.

Historical bug information may provide additional semantic knowledge, such as:

- boundary tensor shapes
- special dtypes
- empty tensors
- NaN/Inf values
- device-related conditions

Such information can guide harness generation toward bug-triggering inputs rather than random valid inputs.

## Key Findings

| API | Validity Ratio | Observation |
|---|---:|---|
| torch.mul | 80.7% | Simple tensor operation |
| torch.sigmoid | 62.1% | Simple unary operation |
| torch.softmax |49.8%| Requires dimension handling |
| torch.matmul |0%| Strong shape dependency |
| torch.mm |0%| Matrix compatibility constraint |


## Experiment Versions

### Original FlashFuzz

Location:

original_flashfuzz/

LLM:
Unknown / original FlashFuzz setting

Purpose:
Historical baseline record.


### DeepSeek Reproduction

Location:

deepseek_reproduction/

LLM:
DeepSeek-V4-Pro

Purpose:
Reproduce FlashFuzz baseline with fixed LLM configuration.
## Original FlashFuzz Results

The original fuzzing logs and artifacts are archived locally
and excluded from the repository due to large size.

The repository keeps only:

- stat.txt for each API
- summary_by_api.csv
- experiment configuration
