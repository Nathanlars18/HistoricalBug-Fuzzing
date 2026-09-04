# EXP006 Pattern Quality Evaluation

## Purpose

Manual evaluation of LLM-generated bug patterns.

Evaluation criteria:
- Schema compliance
- Report-pattern consistency
- Pattern abstraction quality
- Harness generation usefulness


|ID|Pattern ID|API|Bug Category|Source Report|Selection Reason|Schema Valid|Alignment|Abstraction|Trigger Quality|Harness Guidance|Overall|Comment|
|-|-|-|-|-|-|-|-|-|-|-|-|
|001|torch_matmul_pattern_001|torch.matmul|Memory Layout Boundary|matmul_bug_001.json|Core matrix operation; memory layout bug representative|Yes|Good|Good|Good|Good|Pass|Correctly extracts unaligned memory access condition and SIGBUS oracle|
| 002 | torch_matmul_pattern_002 | torch.matmul | Shape Boundary | matmul_bug_002.json | Core matrix operation; zero-dimension boundary bug representative | Yes | Good | Good | Good | Good | Pass | Correctly extracts zero inner dimension condition and incorrect output oracle |
| 003 | torch_mm_pattern_001 | torch.mm | Shape Boundary / API Contract Boundary | mm_bug_001.json | Low-level matrix operator; CUDA shape validation bug representative | Yes | Good | Good | Good | Good | Pass | Correctly abstracts CUDA shape validation failure into reusable pattern |
|004|torch_nn_Conv2d_pattern_001|torch.nn.Conv2d|Shape Boundary|Conv2d_bug_001.json|Representative CNN operator; asymmetric parameter boundary bug|Yes|Good|Good|Good|Good|Pass|Correctly extracts asymmetric padding dimension mapping issue and provides executable constraints|
|005|torch_nn_functional_grid_sample_pattern_001|torch.nn.functional.grid_sample|API Contract Boundary|grid_sample_bug_001.json|Representative API validation bug; tests invalid argument handling|Yes|Good|Good|Good|Good|Pass|Correctly abstracts invalid argument validation failure into reusable API contract pattern|
|006|torch_Tensor_as_strided_pattern_001|torch.Tensor.as_strided|Gradient State Boundary / Memory Layout Boundary|as_strided_bug_001.json|Representative autograd and view aliasing bug|Yes|Good|Good|Good|Good|Minor Issue|Pattern is semantically correct, but source metadata was not extracted|
|007|torch_Tensor_getitem_pattern_001|torch.Tensor.__getitem__|Shape Boundary|getitem_bug_001.json|Representative tensor indexing boundary bug; empty slice behavior|Yes|Good|Good|Good|Good|Pass|Correctly extracts zero-length slice boundary condition and incorrect output oracle|
|008|torch_argmax_pattern_001|torch.argmax|Gradient State Boundary / API Contract Boundary|argmax_bug_001.json|Representative autograd state validation bug for non-differentiable operators|Yes|Good|Good|Good|Good|Pass|Correctly extracts requires_grad state leakage condition and gradient invariant oracle|
|009|torch_einsum_pattern_001|torch.einsum|Gradient State Boundary / API Contract Boundary|einsum_bug_001.json|Representative autograd graph mutation bug|Yes|Good|Good|Good|Good|Minor Issue|Pattern abstraction is correct, but source metadata extraction is incomplete|
|010|torch_nn_functional_embedding_bag_pattern_001|torch.nn.functional.embedding_bag|API Contract Boundary / Execution State Boundary|embedding_bag_bug_001.json|Representative optional parameter execution path bug|Yes|Good|Good|Good|Good|Pass|Correctly abstracts optional parameter path failure into reusable testing strategy|
|-|-|-|-|-|-|-|-|-|-|-|-|
|011|torch_add_pattern_001|torch.add|Backend Dispatch Boundary / Dtype Boundary|add_bug_001.json|Representative dtype/backend inconsistency bug|Yes|Good|Good|Good|Good|Pass|Correctly extracts float16 scalar overflow condition and CPU/CUDA behavior mismatch oracle|
|012|torch_addmm_pattern_001|torch.addmm|Memory Layout Boundary / API Contract Boundary|addmm_bug_001.json|Representative out aliasing incorrect-result bug|Yes|Good|Good|Good|Good|Pass|Correctly extracts output-input alias condition and differential oracle strategy|
|013|torch_cat_pattern_001|torch.cat|Shape Boundary / Gradient State Boundary|cat_bug_001.json|PASS|PASS|PASS|PASS|PASS|PASS|Correctly extracts empty tensor CUDA edge case and provides suitable fuzzing constraints|
|014|torch_index_select_pattern_001|torch.index_select|API Contract Boundary / Graph Transformation Boundary|index_select_bug_001.json|PASS|PASS|PASS|PASS|PASS|PASS|Accurately captures invalid index behavior difference between eager and compiled execution|
|015|torch_mm_pattern_002|torch.mm|Dtype Boundary / Backend Dispatch Boundary|mm_bug_002.json|PASS|PASS|PASS|MINOR|PASS|Minor Issue|Pattern is consistent with issue title, but original report lacks detailed trigger and failure inform
|016|torch_relu_pattern_001|torch.relu|Graph Transformation Boundary / Numerical Edge Case|relu_bug_001.json|PASS|PASS|PASS|PASS|PASS|PASS|Correctly identifies compiler generated numerical inconsistency caused by special floating-point values|
|017|torch_reshape_pattern_001|torch.reshape|API Contract Boundary / Memory Layout Boundary|reshape_bug_001.json|PASS|MINOR|PASS|PASS|PASS|Minor Issue|Pattern targets underlying ATen operator instead of Python API, but this is acceptable for backend fuzzing|
|018|torch_softmax_pattern_001|torch.softmax|Dtype Boundary / Numerical Edge Case|softmax_bug_001.json|PASS|PASS|PASS|PASS|PASS|PASS|Correctly abstracts low precision numerical inconsistency and provides differential testing strategy|
