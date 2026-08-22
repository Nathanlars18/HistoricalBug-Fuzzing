# EXP008 Multi Pattern Prompt Injection


## Target API

torch.matmul


## Goal

Evaluate whether multiple historical bug patterns
can improve LLM-generated PyTorch fuzz harness.


## Historical Patterns

Used 4 historical bug patterns:

1. matmul_unaligned_memory_access_bug

Category:
Memory Layout Boundary


2. matmul_zero_dimension_integer_backend_bug

Category:
Shape Boundary


3. matmul_noncontiguous_output_view_backend_bug

Category:
Memory Layout Boundary


4. matmul_out_view_storage_boundary_bug

Category:
Memory Layout Boundary


## Prompt Strategy

All historical patterns are provided to LLM.

The LLM is instructed to use historical knowledge
to guide tensor input generation.


## Generated Harness

Generated file:

output/torch.matmul/main.cpp


Observed strategies:

- unaligned memory tensor
- zero dimension tensor
- non-contiguous output tensor
- undersized output view


## Compilation

Success


## Fuzzing

Time budget:

300s


Result:

See logs/multi_pattern_300s.log

---

## Fuzzing Experiment

API:

torch.matmul


Configuration:

Prompt Strategy:
Multi Historical Bug Pattern Injection


Historical Patterns:

- matmul_pattern_001
- matmul_pattern_002
- matmul_pattern_003
- matmul_pattern_004


Time Budget:

300 seconds


Result:

| Metric | Value |
|---|---|
| Executed Units | 28835 |
| Average Exec/s | 95 |
| New Corpus Units | 985 |
| Peak RSS(MB) | 476 |
| Crash Artifacts | 0 |


Raw log:

## 7. Coverage Analysis


LLVM source coverage was collected after 300 seconds fuzzing.


The multi-pattern harness achieved:

|Time|Coverage|
|-|-|
|0-60s|1.68%|
|60-120s|1.76%|
|120-180s|1.83%|
|180-240s|1.87%|
|240-300s|1.89%|


The coverage continuously increased during fuzzing,
indicating that the generated harness gradually explored
more PyTorch ATen native execution paths.
logs/multi_pattern_300s.log

## Coverage Fuzzing

Mode:
multi-pattern

API:
torch.matmul

Historical patterns:
- matmul_unaligned_memory_access_bug
- matmul_zero_dimension_integer_backend_bug
- matmul_noncontiguous_output_view_backend_bug
- matmul_out_view_storage_boundary_bug

Coverage intervals:
0-60
60-120
120-180
180-240
240-300

Generated profraw:
5 files

Status:
SUCCESS
## Baseline Note

The baseline directory was inherited during experiment development.
For final evaluation, the baseline is unified with EXP007 baseline,
which represents the original FlashFuzz-style harness without
historical bug pattern guidance.

Therefore, EXP008 baseline is not included in comparison.
