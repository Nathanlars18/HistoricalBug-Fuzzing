# torch.matmul comparison


| Experiment | Pattern Count | Harness Strategy |
|-|-|-|
|Baseline|0|Random tensor generation|
|Single Pattern|1|Memory alignment focused|
|Multi Pattern|4|Memory + Shape + Layout + Output constraint|


## Fuzz Result

|Experiment|Exec/s|New Units|Crash|
|-|-|-|-|
|Baseline|||
|Single Pattern|||
|Multi Pattern|||

---

# Harness Structure Analysis


## Code Size


| Version | LOC |
|---|---|
| Baseline | 49 |
| Single Pattern | 57 |
| Multi Pattern | 203 |


## Pattern Coverage in Generated Harness


Multi-pattern harness successfully incorporated:


| Historical Pattern | Generated Strategy |
|-|-|
| Unaligned Memory | testUnalignedFloatM1 |
| Zero Dimension | testZeroDimInt64 |
| Non-contiguous Output View | testNonContiguousOut |
| Output Storage Boundary | testUndersizedOutView |


The generated harness extends normal tensor generation
with historical bug-oriented input construction strategies.

# torch.matmul Experiment Comparison


## Harness Size Comparison

|Method|Historical Knowledge|Lines|
|-|-|-|
|Baseline|None|49|
|Single Pattern|matmul_pattern_001|57|
|Multi Pattern|pattern_001~004|203|


## Fuzzing Performance

|Method|Executed Units|Exec/s|New Units|
|-|-|-|-|
|Baseline| | | |
|Single Pattern| | | |
|Multi Pattern|28835|95|985|


## Coverage

|Method|60s|120s|180s|240s|300s|
|-|-|-|-|-|-|
|Baseline||||||
|Single Pattern||||||
|Multi Pattern|1.68%|1.76%|1.83%|1.87%|1.89%|



# torch.matmul Pattern Enhancement Experiment Comparison

## 1. Experimental Setting

Target API:

- torch.matmul

Framework:

- PyTorch 2.2

Backend:

- CPU

Fuzzing time:

- 300 seconds

Compared methods:

1. Baseline:
   - Original LLM generated harness without historical bug knowledge.

2. Single Pattern:
   - Harness generation guided by one historical bug pattern.

3. Multi Pattern:
   - Harness generation guided by multiple historical bug patterns.

The goal is to evaluate whether historical bug knowledge can improve
LLM-based harness generation for deep learning framework fuzzing.

---

# 2. Harness Generation Comparison

| Method | Harness Size (LOC) | Historical Bug Guidance |
|---|---:|---|
| Baseline | 49 | None |
| Single Pattern | 57 | One bug pattern (unaligned memory access) |
| Multi Pattern | 203 | Four bug patterns |

## Observation

The multi-pattern harness is significantly larger than baseline and
single-pattern harnesses.

This is because multiple historical bug patterns introduce diverse
input generation strategies, including:

- unaligned memory layout
- zero-dimension tensor cases
- non-contiguous tensor views
- abnormal output tensor layouts

The result indicates that historical bug knowledge can guide LLMs
to generate more specialized fuzzing strategies.

---

# 3. Fuzzing Performance Comparison

| Method | Executed Units | Exec/s | New Units Added | Peak RSS |
|---|---:|---:|---:|---:|
| Baseline | 43857 | 145 | 299 | 439 MB |
| Single Pattern | 72384 | 240 | 397 | 442 MB |
| Multi Pattern | 28835 | 95 | 985 | 476 MB |

## Observation

Compared with baseline, both single-pattern and multi-pattern harnesses
discover more new fuzzing units.

The multi-pattern approach achieves:

- 985 new units

which is:

- 3.29× higher than baseline
- 2.48× higher than single-pattern

Although the execution throughput decreases because the generated harness
contains additional pattern-specific construction logic, multi-pattern
guidance improves exploration effectiveness.

---

# 4. Coverage Comparison

| Method | 60s | 120s | 180s | 240s | 300s |
|---|---:|---:|---:|---:|---:|
| Baseline | 1.61% | 1.63% | 1.68% | 1.68% | 1.68% |
| Single Pattern | 1.57% | 1.57% | 1.58% | 1.58% | 1.63% |
| Multi Pattern | 1.68% | 1.76% | 1.83% | 1.87% | 1.89% |

## Observation

The multi-pattern harness achieves the highest final branch coverage.

At 300 seconds:

- Baseline: 1.68%
- Single Pattern: 1.63%
- Multi Pattern: 1.89%

Compared with baseline:

\[
\frac{1.89-1.68}{1.68}=12.5\%
\]

branch coverage improvement is achieved.

This demonstrates that multiple historical bug patterns can help LLMs
generate more diverse test inputs and explore additional execution paths.

---

# 5. Overall Analysis

The experimental results show that historical bug patterns provide
valuable guidance for LLM-based fuzz harness generation.

Compared with no historical knowledge, pattern-enhanced harnesses
generate more targeted tensor construction strategies.

The multi-pattern approach provides the strongest exploration capability,
achieving the highest number of newly discovered fuzzing units and the
highest final branch coverage.

However, introducing multiple patterns also increases harness complexity
and reduces execution throughput.

Future work will investigate adaptive pattern selection, where the LLM
automatically selects and combines relevant historical bug patterns
instead of applying all patterns equally.

