# SIGBUS in CPU matmul when fp32 weight is not 4-byte aligned (M=1 path, aarch64 macOS)


## Metadata

Repository:

pytorch/pytorch


Issue ID:

#191238


Source:

GitHub Issue


Author:

guptaishaan


Module Labels:

- module: crash
- module: cpu
- module: linear algebra
- module: arm
- module: edge cases


Status:

triaged


---

# Original Issue Description


## Describe the bug

A float32 tensor whose data_ptr() is not 4-byte aligned crashes the process with SIGBUS
when used as the right-hand operand of a large matmul with a single row (M == 1).

With M >= 2 the identical call is fine, so this looks specific to the GEMV path.


PyTorch constructs such a tensor without complaint — torch.frombuffer accepts any byte
offset.

A hard process crash reachable from pure Python seems wrong regardless of whether
unaligned storage is considered supported; at minimum I'd expect a Python-level exception
rather than a signal that kills the interpreter.


---

# Minimal Reproduction


```python
import torch
import torch.nn.functional as F

N, K = 50257, 768

buf = bytearray(N * K * 4 + 8)

W = torch.frombuffer(
    memoryview(buf),
    dtype=torch.float32,
    count=N * K,
    offset=1
).view(N, K)


assert W.is_contiguous()
assert W.data_ptr() % 4 == 1


with torch.no_grad():

    F.linear(torch.randn(2, K), W)   # OK

    F.linear(torch.randn(1, K), W)   # SIGBUS
Result:
3/3 runs, exit code 138.
The crash kills the interpreter, so nothing prints after the failing line.
Scope
Byte alignment of the weight
Matrix size:
N = 50257
K = 768
M = 1
data_ptr() % 4	Result
0	OK
1	SIGBUS
2	SIGBUS
3	SIGBUS


Operations with unaligned weight at M=1
Operation	Result
F.linear	SIGBUS
torch.matmul	SIGBUS
torch.mv	SIGBUS
torch.addmm	SIGBUS
W.sum()	OK
W.clone()	OK


The issue only appears in the large-matrix BLAS path.
Small matrices use another execution path.
M >= 2 is safe for all tested sizes and offsets.
Tested Versions
torch	Python	BLAS	Result
2.12.0	3.13.13	Accelerate	SIGBUS
2.10.0	3.12.13	Accelerate	SIGBUS


Environment:
OS: macOS 15.0 arm64

CPU:
Apple M1 Pro


PyTorch:
2.12.0
Why This Happens in Practice
This is not only triggered by manually created tensors.
safetensors can mmap checkpoints and provide tensors as views into the mapping.
If the JSON header length of a safetensors file is not padded to a multiple of 4,
the fp32 tensor data region can become misaligned.
Example:
header_len            : 8277
data region starts at : 8285

8285 % 4 == 1
Therefore fp32 tensors in this checkpoint are offset by one byte.
Practical symptom:
KV-cache generation with a HuggingFace causal language model crashes during the final
vocab projection, which runs with:
seq_len == 1
Prefill stage:
seq_len > 1
works correctly.
Expected Behavior
Possible solutions:
Handle unaligned inputs in CPU BLAS dispatch.
Example:
Copy data into an aligned temporary buffer before calling BLAS.
Reject unaligned tensors with a clear Python-level exception.
A SIGBUS should not be reachable from:
torch.frombuffer + F.linear
Additional Discussion
Author clarification
The author later clarified:
The crash is confirmed as an alignment fault.
The exception code:
EXC_BAD_ACCESS code=257
corresponds to:
EXC_ARM_DA_ALIGN
which indicates a data alignment fault.
The fault address is consistent with:
offset = 1
PyTorch actually calls SGEMM.
The original description mentioned GEMV.
The actual path:
PyTorch cpublas::gemm
        |
        v
Accelerate cblas_sgemm
        |
        v
internal M==1 optimization
        |
        v
cblas_sgemv
The M==1 special behavior comes from Apple's Accelerate library.
The fault occurs inside Apple Accelerate.
The PyTorch side controls whether it passes an unaligned float pointer into BLAS.
Maintainer Discussion
A later comment reported:
Running the same reproduction on newer macOS versions with newer Accelerate implementations
did not reproduce the crash.
The issue is therefore dependent on Accelerate behavior.
However, older systems can still encounter a hard crash when loading unaligned checkpoints.
A proposed solution:
Skip the BLAS fast path when tensor pointers are misaligned and use a safe fallback implementation.
References
GitHub Issue:
pytorch/pytorch#191238
