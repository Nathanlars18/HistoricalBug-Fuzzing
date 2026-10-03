# Silent Heap Buffer Overflow in standard ops (add, pinv) via implicit view resizing

Issue: #170573

Repository:
pytorch/pytorch

Source:
GitHub Issue

Author:
jiren-the-gray

Date:
2025-12-17


## Description

When passing an undersized view as the out argument to standard operations
(e.g., torch.add, torch.matmul, torch.linalg.pinv),
PyTorch fails to validate the size requirements or safely handle the resize.

Instead of raising a RuntimeError (as expected for views),
the operation triggers a deprecated implicit resize path.

This path successfully updates the tensor metadata (shape) to match the operation result,
but fails to update the storage because views cannot be reallocated.

The kernel may then write the full result based on the new shape into the old storage buffer.


## Reproduction Script

```python
import torch

def reproduce_buffer_overflow():

    storage = torch.zeros(6, dtype=torch.float32)

    # out is a view with insufficient storage
    out_view = storage[:2]

    canary = storage[2:]
    canary.fill_(-1.0)

    a = torch.full((4,), 10.0)
    b = torch.full((4,), 20.0)

    print(f"Canary Before: {canary.tolist()}")

    try:
        torch.add(a, b, out=out_view)
    except Exception as e:
        print(e)

    print(f"Canary After: {canary.tolist()})


if __name__ == "__main__":
    reproduce_buffer_overflow()
Observed Behavior
The operation emits a warning:
"An output with one or more elements was resized since it had shape [2],
which does not match the required output shape [4]."
However, execution continues.
The memory region after the output view may be modified.
Expected Behavior
The operation should raise an error when an undersized view is provided as output.
Implicit resizing should not cause unsafe memory writes.
Affected Operations
torch.add
torch.matmul
torch.linalg.pinv
Environment
PyTorch:
2.9.0+cpu
OS:
Ubuntu 22.04.5 LTS
Device:
CPU
Activity
Official PyTorch maintainers participated in the discussion.
The issue was marked as triaged.
No fixing commit was referenced in the issue.
