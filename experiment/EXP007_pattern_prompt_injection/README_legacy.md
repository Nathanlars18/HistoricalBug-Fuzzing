# EXP007: Historical Bug Pattern Guided Harness Generation


## 1. Motivation

FlashFuzz uses LLM to generate PyTorch C++ fuzzing harnesses based on API
documentation and helper templates.

This experiment investigates whether historical bug knowledge can improve
LLM-generated harnesses.

Research question:

Can historical bug patterns extracted from real PyTorch issues guide LLM
to generate more effective fuzzing harnesses?


---

## 2. Experimental Hypothesis

Adding historical bug patterns into the LLM prompt can improve harness
generation quality by guiding the LLM to generate inputs closer to real
bug-triggering conditions.


---

## 3. Experimental Pipeline

Baseline:

PyTorch API
    |
    |
API documentation
    |
    |
LLM prompt
    |
    |
Generated Harness


Pattern-enhanced:

PyTorch API
    |
    |
API documentation
    |
    |
Historical Bug Pattern
    |
    |
Pattern-to-Prompt Adapter
    |
    |
LLM prompt
    |
    |
Generated Harness


---

## 4. Current Status

### Completed

- Created EXP006 historical bug pattern dataset.
- Collected initial torch.matmul historical bug patterns.
- Implemented initial Pattern-to-Prompt adapter.

Current tested pattern:

torch.matmul_pattern_001

Converted information:

- Bug category:
  - Memory Layout
  - Backend Dispatch

- Trigger conditions:
  - M=1 matrix multiplication
  - float32 dtype
  - unaligned tensor memory

- Oracle:
  - SIGBUS crash


Example generated guidance:

Historical bug information:
API:
torch.matmul
Trigger conditions:
shape: M=1
dtype: float32
data_ptr() % 4 != 0

---

## 5. Current Design Decision

The current Pattern-to-Prompt converter is intentionally simple.

Reason:

The first goal is to verify whether historical bug information itself
can improve harness generation.

Prompt optimization and advanced retrieval strategies will be considered
after validating the effectiveness on a single API.


---

## 6. Next Steps

### Step 1: Integrate Pattern Information into LLM Prompt

Modify:

testharness_generation/torch_cpu/llm_gptoss.py

experimental copy:

EXP007_pattern_prompt_injection/llm_gptoss_pattern.py

Add:

Pattern JSON
      |
pattern_to_prompt()
      |
LLM prompt


---

### Step 2: Single API Validation

Target API:

torch.matmul


Generate two groups:

Baseline:

without historical bug pattern

Pattern-enhanced:

with historical bug pattern


Compare:

- harness generation success rate
- compilation success rate
- fuzzing coverage
- bug triggering ability


---

### Step 3: Expansion

If torch.matmul experiment shows improvement:

Expand to more APIs.

Target:

10 PyTorch CPU APIs

Collect:

30-50 historical bug patterns


---

## 7. Future Improvements

Possible future directions:

- More precise pattern representation
- Automatic API-pattern matching
- Pattern retrieval mechanism
- Multiple bug pattern fusion
- Better prompt construction

## Current Status

Target API:
- torch.matmul

Experiment setting:
- Single API feasibility study
- Historical bug pattern:
  - matmul_pattern_001.json

Goal:
Verify whether historical bug information can influence LLM-generated harnesses.

# EXP007 Pattern Prompt Injection

## Goal

Evaluate whether historical PyTorch bug patterns can enhance LLM-based fuzzing harness generation.


## Compared Methods


### Baseline

LLM generates harness using:

- API documentation
- helper skeleton


### Pattern Enhanced

LLM receives:

- API documentation
- historical bug pattern information


## API

torch.matmul


## Experiment Pipeline


Bug Report

↓

Pattern Extraction

↓

Prompt Construction

↓

DeepSeek Harness Generation

↓

Compilation

↓

libFuzzer Testing


## Results

Pattern enhanced harness generated additional bug-oriented strategies:

- unaligned tensor memory
- float32 constraint
- offset based mutation


## Future Work

- More historical bug patterns
- More PyTorch APIs
- Statistical evaluation with repeated runs

