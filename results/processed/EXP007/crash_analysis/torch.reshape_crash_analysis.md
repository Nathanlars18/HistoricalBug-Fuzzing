# EXP007 torch.reshape Crash Analysis


## 1. Experiment Overview

### Target API

torch.reshape


### Environment

- Framework: PyTorch 2.2
- Fuzzing Engine: libFuzzer
- Harness: FlashFuzz generated C++ harness
- Device: CPU
- Container:
  ncsuswat/flashfuzz:torch2.2-fuzz


### Purpose

This analysis investigates crashes discovered during baseline fuzzing,
including crash deduplication, reproduction, failure classification,
and root cause analysis.

## 2. Crash Summary


| Item | Result |
|-|-|
| Total crashes | 21 |
| Unique crashes | 9 |
| Replay success | 9/9 |
| Failure oracle | Assertion abort |
| Crash location | main.cpp:92 |

## 3. Failure Classification


After replaying all unique crashes,
all 9 crashes trigger the same failure oracle:

BUG: reshape corrupted tensor data


The crashes are therefore grouped into one failure category:


| Category | Count |
|-|-|
| Data corruption after reshape | 9 |

### Crash-43a


Input:

- dtype: Half
- shape: [11,10,10,7]
- contiguous: true


Observed behavior:


reshape() returns an output tensor,
but flattened values are different from the original tensor.


Failure:

BUG: reshape corrupted tensor data

### Crash B
592:
dtype:
BFloat16

shape:
[2,10,16]

### Crash C
5f:
dtype:
ComplexFloat

shape:
[7,1,9,8]

## 4. Root Cause Analysis


The detected failures are caused by violation of
reshape semantic invariants.


Expected behavior:

reshape should preserve:

1. number of elements
2. dtype
3. element ordering


Observed behavior:

The generated inputs trigger a situation where
the output tensor does not preserve flattened values.


Because the failure is detected by the harness oracle,
further investigation is required to determine whether
the issue originates from PyTorch implementation
or harness-generated invalid assumptions.

