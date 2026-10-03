# MPS matmul with sliced (strided) out argument produces wrong output, may corrupt memory

## Source

Repository:

pytorch/pytorch

Issue:

#104832

Title:

MPS matmul with sliced (strided) out argument produces wrong output, may corrupt memory


## Description

When using torch.matmul with an out argument that is a view that is not contiguous, 
the operation does not correctly write the result to the output tensor on the MPS backend.

Instead of computing the matrix multiplication result, the output tensor remains unchanged
and contains zeros.


## Minimal Reproduction

```python
import torch

X = torch.randn(256,256).to("mps")
Y = torch.randn(256,256).to("mps")

Z = torch.zeros(256,2*256).to("mps")

torch.matmul(
    X,
    Y,
    out=Z[:,128:(128+256)]
)
The same operation works correctly on CPU:
import torch

X = torch.randn(256,256)
Y = torch.randn(256,256)

Z = torch.zeros(256,2*256)

torch.matmul(
    X,
    Y,
    out=Z[:,128:(128+256)]
)
Observed Behavior
On MPS backend:
torch.matmul does not update the output tensor correctly.
The output remains zero.
The result differs from CPU implementation.
The issue may also cause segmentation faults in some cases,
although the reporter could not provide a consistent reproduction.
Trigger Conditions
The issue requires:
API: torch.matmul
Backend: MPS
out argument is provided
out tensor is a non-contiguous view
sliced tensor view is used as output storage
Example:
out = base_tensor[:, start:end]
where the resulting tensor is not contiguous.
Expected Behavior
torch.matmul should correctly write the multiplication result into
the provided output tensor regardless of whether the output tensor is contiguous.
Environment
PyTorch version:
2.0.1
OS:
macOS 13.4
Device:
Apple M2 Max
Backend:
MPS
Issue Status
The issue was triaged by PyTorch maintainers.
Later discussion reported that the issue could no longer be reproduced
on newer nightly versions and a regression test was added.
