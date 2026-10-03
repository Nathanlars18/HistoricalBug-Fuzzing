# matmul returns uninitialized memory for int64 tensors with inner dimension of zero

Issue: #71774

Repository: pytorch/pytorch

Source:
https://github.com/pytorch/pytorch/issues/71774


## Description

This was found in opinfo tests. Observed in Windows CI test and internal @mode/opt.

Only seen on dtype=torch.long, not with ints.

Similar bugs are found in:

- __rmatmul__, int64
- addmm_decomposed, float16 (turns out this is actually a jit-only issue)
- linalg_multi_dot, int64


## Minimal Reproduction


```python
import torch
from torch import tensor

for i in [0, 5]:

    a = tensor(
        [
            [-4,  3,  9,  7,  0, -6,  4,  0, -3,  2],
            [-9, -7, -7, -2,  8,  4, -4, -4, -4,  4],
            [-6,  8, -4,  5, -7,  5, -2,  9, -7, -1],
            [-4,  4, -3, -1,  0,  2,  4,  6, -7, -1],
            [-3,  5, -9,  4, -7, -9, -1,  2, -7, -6],
        ],
        dtype=torch.long
    )


    b = tensor(
        [
            [-8,  2, -7, -9, -7],
            [-8,  6,  3,  8, -4],
            [ 9, -5,  5,  4, -6],
            [-8,  7, -1, -8,  9],
            [-5, -9, -3,  4,  2],
            [ 9, -5,  2,  0, -9],
            [ 2,  9, -5,  1,  3],
            [-6,  2, -5, -7,  2],
            [-4, -2,  2, -6,  0],
            [ 1, -3, -3, -8, -1],
        ],
        dtype=torch.long
    )


    a0 = a.size(dim=0)
    a1 = a.size(dim=1)

    b0 = b.size(dim=0)
    b1 = b.size(dim=1)


    a = a[:a0-i, :a1-i]

    b = b[:b0-i, :b1-i]


    print("A:", a)
    print("B:", b)


    c = torch.matmul(b, a)

    d = torch.matmul(b, a)


    print("C:", c)
    print("D:", d)


    assert((c==d).all().item())

Observed Behavior
When the inner dimension becomes zero:
A: tensor([], size=(0, 5), dtype=torch.int64)

B: tensor([], size=(5, 0), dtype=torch.int64)
torch.matmul returns different values between repeated executions.
Example:
C:

tensor([
 [140142115139344, 15, 8083509854526923635, ...]
])


D:

tensor([
 [140142115139088, 15, 8083509854526923635, ...]
])
The output contains different values from uninitialized memory.
The assertion fails:
AssertionError
Expected Behavior
The output should be deterministic.
For matrix multiplication with zero inner dimension, the result should not contain uninitialized values.
Environment
Framework:
PyTorch
dtype:
torch.long
Backend:
CPU
Discussion
A maintainer comment noted:
Happens with fbgemm only
Activity
Labels added:
module: linear algebra
module: correctness (silent)
Issue was triaged by PyTorch maintainers.
