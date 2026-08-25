# EXP007 Baseline Experiment Report


## 1. Overview

This experiment evaluates the baseline fuzzing capability
of FlashFuzz-generated harnesses on PyTorch APIs.

The purpose is to establish a baseline before applying
historical Bug Pattern enhanced harness generation.


---

## 2. Research Objective


The experiment aims to answer:

RQ1:

How effective are existing LLM-generated harnesses
without historical bug knowledge?


The baseline results provide:

- crash discovery capability
- failure categories
- coverage information
- comparison reference for enhanced harnesses


---

## 3. Experimental Environment


Framework:
PyTorch 2.2


Fuzzing Framework:
FlashFuzz + libFuzzer


Execution Environment:

- Docker:
  ncsuswat/flashfuzz:torch2.2-fuzz

- Device:
  CPU mode


Compiler:

clang


---

## 4. Target APIs


The experiment evaluates:


| API |
|-|
| torch.add |
| torch.addmm |
| torch.cat |
| torch.index_select |
| torch.mm |
| torch.mul |
| torch.relu |
| torch.reshape |
| torch.softmax |
| torch.matmul |


---

## 5. Harness Preparation


The harnesses are generated using the
baseline FlashFuzz workflow.


Before fuzzing, several compilation and infrastructure
issues were fixed.


### 5.1 Compilation Compatibility Fixes


Examples:


torch.add:

- std::complex<double>
  changed to
  c10::complex<double>


- dtype()
  changed to
  scalar_type()


torch.mul:

- adjusted scalar-tensor overload usage


These modifications only ensure C++ API compatibility.
The fuzzing strategy and oracle logic were unchanged.



### 5.2 API Entry Fix


New APIs were missing top-level FlashFuzz directories.

The issue was solved by automatically generating:

torch_cpu/{api}
        |
        v
/api


before execution.


---

## 6. Experimental Configuration


Fuzzing mode:

libFuzzer


Time budget:

600 seconds


Repeat:

3 runs per API


Mode:

CPU fuzzing


---

## 7. Execution Process


For each API:


1. Compile harness

2. Execute fuzzing

3. Collect artifacts

4. Deduplicate crashes

5. Replay unique crashes

6. Analyze failure categories


---

## 8. Crash Results


Summary:


| API | Raw Crashes | Unique Crashes |
|-|-|-|
| torch.reshape | XX | XX |
| torch.add | XX | XX |
| ... | ... | ... |


All unique crashes were replayed
to verify reproducibility.


Detailed analysis:

results/processed/EXP007/crash_analysis/


---

## 9. Coverage Analysis


Coverage collection was performed separately.


Some APIs produced zero coverage results
because the coverage collection pipeline
did not correctly match fuzz execution.


Detailed analysis:

coverage_analysis/EXP007_coverage_analysis.md


The fuzzing results remain valid because
crashes were successfully reproduced.


---

## 10. Engineering Issues and Solutions


During experiment execution:


1. LLM-generated harness compilation problems

2. FlashFuzz API directory mapping problem

3. Coverage result path inconsistency


All fixes are recorded separately.


---

## 11. Conclusion


This experiment establishes the baseline performance
of FlashFuzz-generated harnesses.


The results will be used as comparison baseline
for historical Bug Pattern enhanced harness generation.

