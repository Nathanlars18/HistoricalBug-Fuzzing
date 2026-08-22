# Historical Bug Pattern Schema


## 1. Metadata

- Pattern ID
- API Name
- Source Report
- Source
- Date
- Severity


## 2. Bug Category

Primary Category:

Secondary Category:


Available categories:

1 Shape Boundary
2 Dtype Boundary
3 Device Transition
4 Memory Layout
5 Numerical Edge Case
6 Gradient/Autograd
7 Backend Dispatch
8 Concurrency

## 3. Pattern Abstraction

API Specific Pattern:

The concrete bug pattern extracted from a specific API.

Example:

torch.matmul_out_view_memory_bug


General Category:

The abstract category that may apply to multiple APIs.

Available categories:

1. Shape Boundary
2. Dtype Boundary
3. Device Transition
4. Memory Layout Boundary
5. Numerical Edge Case
6. Gradient State Boundary
7. Backend Dispatch Boundary
8. Execution State Boundary
9. Graph Transformation Boundary
10. API Contract Boundary


Transferability:

Describe whether this pattern may transfer to other APIs.

Values:

- high
- medium
- low

## 4. Trigger Condition

- Shape Trigger
- Dtype Trigger
- Device Trigger
- Memory Trigger
- Value Trigger
- State Trigger
- Execution Trigger

Concrete Constraints:


## 5. Root Cause

- API Layer
- ATen Layer
- Kernel Layer
- Backend Layer
- Numerical Layer

Confidence:


## 6. Bug Oracle

- Crash
- Exception
- Incorrect Output
- Timeout/Hang
- Memory Error
The observable behavior used to determine whether a bug is triggered.

Types:

- Crash:
  Process termination, SIGSEGV, SIGBUS, SIGABRT.

- Exception:
  RuntimeError, ValueError, AssertionError.

- Wrong Result:
  Output differs from reference result.

- Hang:
  Operation exceeds execution time limit.

- Memory Corruption:
  Memory outside valid tensor region is modified.

## 7. Harness Strategy

- Input Mutation
- Tensor Construction
- Constraint Injection
- Operation Sequence

- Oracle Construction
## 8. Verification Status

Describe the confidence level of the historical bug information.


Fields:

- level:
  - fixed
  - official_triaged
  - user_reported

- fixed:
  - true
  - false


Example:

```json
{
  "verification_status": {
    "level": "official_triaged",
    "fixed": false
  }
}
```
