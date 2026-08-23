# EXP006 Bug Report Quality Check


## Purpose

This document records manual validation
of structured bug reports generated from
PyTorch GitHub Issues.


## Validation Criteria


| Criterion | Description |
|---|---|
| Issue ID | Correct mapping to original issue |
| API | Correct affected API |
| Description | Bug information preserved |
| Raw Reference | Traceable to original issue |
| Schema | Valid JSON structure |


---
# torch.add

| Report | Issue | Schema | API | Description | Raw | Result | Notes |
|---|---|---|---|---|---|---|---|
| add_bug_001 | 152731 | PASS | PASS | PASS | PASS | PASS | CPU/CUDA float16 overflow |
| add_bug_002 | 154501 | PASS | PASS | PASS | PASS | PASS | Complex Inf numerical issue |
| add_bug_003 | 170573 | PASS | PASS | PASS | PASS | PASS | out view memory corruption |

# torch.addmm

| Report | Issue | Schema | API | Description | Raw | Result | Notes |
|---|---|---|---|---|---|---|---|
| addmm_bug_001 | 48900 | PASS | PASS | PASS | PASS | PASS | out alias incorrect result |
| addmm_bug_002 | 138906 | PASS | PASS | PASS | PASS | PASS | output-input alias |
| addmm_bug_003 | 183887 | PASS | PASS | PASS | PASS | PASS | compile inconsistency |
| addmm_bug_004 | 183899 | PASS | PASS | PASS | PASS | PASS | beta=0 shape boundary |

# torch.cat


| Report | Issue | Schema | API | Description | Raw | Result | Notes |
|---|---|---|---|---|---|---|---|
| cat_bug_001 | 60997 | PASS | PASS | PASS | PASS | PASS | Empty TensorList dispatcher boundary |
| cat_bug_002 | 63998 | PASS | PASS | PASS | PASS | PASS | CPU/CUDA memory format inconsistency |
| cat_bug_003 | 86918 | PASS | PASS | PASS | PASS | PASS | Empty tensor dimension validation |
| cat_bug_004 | 118970 | PASS | PASS | PASS | PASS | PASS | Empty tensor CUDA memory error |
| cat_bug_005 | 139609 | PASS | PASS | PASS | PASS | PASS | Non-standard boolean storage |
# torch.index_select


| Report | Issue | Schema | API | Description | Raw | Result | Notes |
|---|---|---|---|---|---|---|---|
| index_select_bug_001 | 121251 | PASS | PASS | PASS | PASS | PASS | torch.compile invalid index behavior |
| index_select_bug_002 | 154235 | PASS | PASS | PASS | PASS | PASS | MPS missing index validation |
| index_select_bug_003 | 169779 | PASS | PASS | PASS | PASS | PASS | Negative index semantic inconsistency |
| index_select_bug_004 | 188756 | PASS | PASS | PASS | PASS | PASS | INT32 overflow large tensor boundary |
# torch.mm

| Report | Issue | Schema | API | Description | Raw | Result | Notes |
|---|---|---|---|---|---|---|---|
| mm_bug_002 | 85852 | PASS | PASS | PASS | PASS | PASS | Memory alias / out tensor overlap |
| mm_bug_003 | 191693 | PASS | PASS | PASS | PASS | PASS | MPS bool dtype backend dispatch failure |
# torch.mul

| Report | Issue | Schema | API | Description | Raw | Result | Notes |
|---|---|---|---|---|---|---|---|
| mul_bug_002 | 85053 | PASS | PASS | PASS | PASS | PASS | TensorIterator invalid out shape crash |
| mul_bug_003 | 115731 | PASS | PASS | PASS | PASS | PASS | Empty tensor float16 CPU crash |
| mul_bug_004 | 188900 | PASS | PASS | PASS | PASS | PASS | Sparse broadcasting incorrect result |
# torch.relu

| Report | Issue | Schema | API | Description | Raw | Result | Notes |
|---|---|---|---|---|---|---|---|
| relu_bug_001 | 49536 | PASS | PASS | PASS | PASS | PASS | Vulkan backend operator failure |
| relu_bug_002 | 61519 | PASS | PASS | PASS | PASS | PASS | Inplace ReLU autograd limitation |
| relu_bug_003 | 117544 | PASS | PASS | PASS | PASS | PASS | torch.compile numerical inconsistency |
# torch.reshape

| Report | Issue | Schema | API | Description | Raw | Result | Notes |
|---|---|---|---|---|---|---|---|
| reshape_bug_001 | 89068 | PASS | PASS | PASS | PASS | PASS | Zero-element output tensor reshape handling |
| reshape_bug_002 | 194050 | PASS | PASS | PASS | PASS | PASS | Unchecked reshape stride causes out-of-bound copy |
| reshape_bug_003 | 194051 | PASS | PASS | PASS | PASS | PASS | Unchecked reshape stride creates out-of-storage view |
# torch.softmax

| Report | Issue | Schema | API | Description | Raw | Result | Notes |
|---|---|---|---|---|---|---|---|
| softmax_bug_001 | 55056 | PASS | PASS | PASS | PASS | PASS | All negative infinity softmax NaN |
| softmax_bug_002 | 75923 | PASS | PASS | PASS | PASS | PASS | Non-contiguous output tensor failure |
| softmax_bug_003 | 123911 | PASS | PASS | PASS | PASS | PASS | FP16 numerical inconsistency |
| softmax_bug_004 | 139701 | PASS | PASS | PASS | PASS | PASS | Layout transformation numerical difference |
| softmax_bug_005 | 147284 | PASS | PASS | PASS | PASS | PASS | CUDA softmax boundary condition |

---

# Excluded Issues

| Issue | Original API Category | Reason |
|---|---|---|
| 106665 | torch.reshape | API mismatch. Original issue targets torch.nn.Linear and was removed from reshape dataset |
