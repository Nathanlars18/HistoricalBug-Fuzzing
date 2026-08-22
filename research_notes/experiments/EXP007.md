# EXP007 Pattern Enhanced Harness Generation Experiment Log


## 1. Experiment Objective

### Research Question

验证历史 Bug Pattern 是否能够有效指导 LLM 生成针对特定 PyTorch API 的 C++ fuzz harness。

具体目标：

1. 历史 Bug 信息是否可以转换为 Prompt 中的约束信息；
2. LLM 是否能够根据 Bug Pattern 生成针对性的输入构造策略；
3. 生成的 Harness 是否可以通过 PyTorch C++ 编译环境验证。


---

# 2. Experimental Motivation

传统 FlashFuzz:

API Documentation
        |
        v
LLM
        |
        v
C++ Harness


本实验:

Historical Bug Pattern
        |
        v
Prompt Injection
        |
        v
LLM
        |
        v
Bug-oriented C++ Harness


核心假设：

历史 Bug 中包含的触发条件（shape、dtype、memory layout等）
可以帮助 LLM 生成更有效的测试输入。


---

# 3. Experimental Environment


## System

OS:
Ubuntu 22.04 (WSL2)

Hardware:
RTX 4060 Laptop GPU


## PyTorch

Version:

PyTorch 2.2.0a0+git8ac9b20


## Compiler

clang version:

14.0.0


## Fuzzing Framework

FlashFuzz

Docker:

ncsuswat/flashfuzz:torch2.2-fuzz


---

# 4. LLM Configuration


## Original FlashFuzz

LLM backend:

(记录FlashFuzz原始使用模型)


## EXP007

LLM:

DeepSeek-V4-Pro


API:

https://api.deepseek.com


Model:

deepseek-v4-pro


Reason for replacement:

由于原实验LLM服务不可稳定访问，
为了保证实验可复现性，
采用DeepSeek-V4-Pro作为统一LLM backend。


后续正式实验：

Baseline:

DeepSeek-V4-Pro + Original FlashFuzz Prompt


Our Method:

DeepSeek-V4-Pro + Historical Bug Pattern Prompt


保证LLM能力因素保持一致。


---

# 5. Experiment Target


Target API:

torch.matmul


Historical Bug Pattern:

matmul_pattern_001.json


Bug Category:

Memory Layout
Backend Dispatch


Trigger Conditions:

- dtype:
  float32

- device:
  CPU

- memory:
  data pointer not 4-byte aligned

- shape:
  matrix multiplication with M=1


Bug Oracle:

Crash


---

# 6. Prompt Construction


Input:

1. PyTorch API documentation

2. Helper skeleton

3. Historical Bug Pattern


Prompt pipeline:

API
 |
 + API Documentation
 |
 + Bug Pattern
 |
 v
DeepSeek-V4-Pro
 |
 v
main.cpp


---

# 7. Experiment Process


## Step 1: API Selection

Date:

2026-08-07


Selected:

torch.matmul


Reason:

存在明确历史 Bug Pattern，
适合作为方法有效性验证。


---

## Step 2: Harness Generation


Command:

```bash
python experiment/EXP007_pattern_prompt_injection/llm_deepseek_pattern.py \
--api-file experiment/EXP007_pattern_prompt_injection/api.txt \
--out-dir experiment/EXP007_pattern_prompt_injection/output \
--overwrite
Result:
SUCCESS
Generated:
output/torch.matmul/main.cpp
8. Generated Harness Analysis
Generated strategy:
Construct unaligned tensor memory
createUnalignedTensor()
Force M=1 shape condition

Use float32 dtype

Execute:

torch::matmul()
Observation:
LLM successfully transformed historical bug description
into concrete tensor construction strategy.
9. Compilation Experiment
Environment:
FlashFuzz Docker:
ncsuswat/flashfuzz:torch2.2-fuzz
Command:
bash build.sh
Result:
FAILED
Error:
no matching function for call to from_blob
10. Error Analysis
Problem:
Generated code used invalid LibTorch API:
torch::from_blob(
ptr,
shape,
dtype,
device,
free,
raw
)
However PyTorch C++ API does not support this overload.
Cause:
LLM confused Python API style
and LibTorch C++ API.
11. Repair
Modification:
Replace:
torch::from_blob(...)
with PyTorch 2.2 compatible version.
Purpose:
Maintain unaligned memory construction while satisfying C++ API.
12. Current Status
Stage	Status
Bug Pattern extraction	DONE
Prompt injection	DONE
LLM generation	DONE
Harness compilation	Repairing
Fuzz execution	Pending


13. Future Plan
Complete torch.matmul compilation.

Run fuzz testing.

Measure:
crash discovery
coverage
execution behavior

Extend to more APIs:
torch.add
torch.conv2d

Build comparison:
FlashFuzz baseline
vs
Pattern-enhanced Harness

# EXP007 Historical Bug Pattern Enhanced Harness Generation


## Experiment Goal

Verify whether historical PyTorch bug patterns can improve LLM-based harness generation.

Target:

torch.matmul


---

## Environment

OS:
WSL2 Ubuntu

Framework:
PyTorch 2.2.0

Backend:
CPU

Compiler:
clang


---

## LLM Configuration

Model:

DeepSeek-V4-Pro


API:

DeepSeek OpenAI-compatible API


Reason:

Compared with original GPT-OSS endpoint,
DeepSeek provides stable API access and stronger code generation ability.


---

## Harness Generation

Input:

- API documentation
- helper skeleton
- historical bug pattern


Historical Bug:

torch.matmul


Pattern information:

- special memory layout
- boundary tensor shapes
- M=1 condition
- dtype=float32


Generation Result:

SUCCESS


Generated file:

output/torch.matmul/main.cpp


---

## Compilation


Command:

bash build.sh


Result:

SUCCESS


---

## Fuzzing


Command:

./fuzz -max_total_time=60


Result:

SUCCESS


Statistics:

Runs:
19645


Coverage:
9362


Corpus:
242


Exec speed:
322 exec/s


---

## Crash Analysis


Found crashes:

No.


Observed exceptions:

matmul dimension mismatch


Classification:

Expected invalid input exception.

Not considered as PyTorch implementation bug.


---

## Next Step

1. Improve exception handling.
2. Run longer fuzzing.
3. Compare with FlashFuzz baseline.
## EXP007 DeepSeek-V4-Pro Pattern Harness Fuzzing Result

### Configuration

Target API:
torch.matmul

LLM:
DeepSeek-V4-Pro

Framework:
PyTorch C++ CPU

Fuzzing Engine:
libFuzzer


### Historical Bug Pattern

Pattern:
torch.matmul CPU kernel corner case

Extracted conditions:

- float32 tensor
- memory alignment issue
- tensor shape corner cases


### Harness Generation

Generated file:

experiment/EXP007_pattern_prompt_injection/output/torch.matmul/main.cpp


Generation result:

PASS


Compilation:

PASS


Exception handling:

PASS

Normal PyTorch runtime exceptions are caught and ignored.


### Fuzzing Configuration

Command:

./fuzz -max_total_time=300 corpus/


Time:

301 seconds


### Fuzzing Result

Executions:
33286

Coverage:
9050

Feature count:
24835

Corpus size:
459

Corpus size on disk:
10445 KB

Execution speed:
110 exec/s


Crash:

No libFuzzer crash detected.


Observation:

The generated harness successfully integrated historical bug knowledge.
The fuzzer explored diverse tensor configurations including:

- different tensor ranks
- different dtypes
- edge-case shapes
- alignment-related cases

However, many generated inputs triggered expected PyTorch shape mismatch exceptions,
indicating that further semantic constraint guidance may improve kernel-level exploration.
# EXP007 Pattern Prompt Injection Experiment

## Baseline Fuzzing Experiment

### Target

API:
torch.matmul

Framework:
PyTorch 2.2

Method:
Original FlashFuzz-style harness without historical bug pattern knowledge

Time Budget:
600s


## Fuzz Configuration

Container:

ncsuswat/flashfuzz:torch2.2-fuzz


Command:

bash fuzz.sh > baseline_600s.log 2>&1


## Result

Executed units:
81004

Average exec/sec:
134

New units added:
293

Peak RSS:
444 MB

Artifacts:
0

Corpus size:
691


## Observation

The baseline harness performs unrestricted tensor generation.
It serves as the comparison target for pattern-enhanced harnesses.、
---

# Single Historical Bug Pattern Experiment


## Method

Historical bug information was injected into LLM harness generation.

The generated harness integrates one representative historical bug pattern into tensor generation constraints.


## Configuration

API:

torch.matmul


Time Budget:

600s


Container:

ncsuswat/flashfuzz:torch2.2-fuzz


Command:

bash fuzz.sh > pattern_600s.log 2>&1


## Result

Executed units:

140341


Average exec/sec:

233


New units added:

281


Peak RSS:

465 MB


Artifacts:

0


Corpus size:

1768


## Observation

Compared with baseline:

- Execution throughput increased.
- Corpus size increased significantly.
- The generated harness explores more structured input space.

Coverage evaluation is required for final effectiveness comparison.
