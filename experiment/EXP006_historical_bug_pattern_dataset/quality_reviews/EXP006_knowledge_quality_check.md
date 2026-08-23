# EXP006 Knowledge Quality Evaluation

## Purpose

Manual evaluation of LLM-generated testing knowledge.

The evaluation focuses on whether historical bug patterns can be effectively transformed into reusable testing knowledge for harness generation.

Evaluation criteria:

- Pattern-knowledge consistency
- Knowledge abstraction quality
- Transferability
- Harness generation usefulness

## API Selection Strategy

The evaluated APIs are selected to cover diverse operator categories and bug dimensions, including linear algebra operators, neural network layers, tensor view operations, indexing operations, and autograd-related APIs.

The selection aims to evaluate whether generated knowledge can be abstracted beyond individual historical bugs and transferred across different API families.


|ID|Knowledge ID|Source Pattern|API|API Selection Reason|Risk Category|Pattern-Knowledge Alignment|Abstraction Quality|Transferability|Harness Guidance|Overall|Comment|
|-|-|-|-|-|-|-|-|-|-|-|-|
|001|torch_matmul_knowledge_001|torch_matmul_pattern_001|torch.matmul|Representative linear algebra API; selected because matrix multiplication involves complex backend dispatch and memory layout assumptions.|Memory Layout Boundary|Good|Good|High|Good|Pass|Correctly abstracts unaligned memory access into a general memory-layout testing strategy instead of reproducing the original issue.|
|002|torch_matmul_knowledge_002|torch_matmul_pattern_002|torch.matmul|Representative tensor computation operator; selected because zero-dimension and dtype boundary cases are important fuzzing edge conditions.|Shape Boundary + Dtype Boundary|Good|Good|High|Good|Pass|Successfully transforms zero-size reduction behavior into a reusable shape and dtype boundary testing strategy.|
|003|torch_matmul_knowledge_003|torch_matmul_pattern_003|torch.matmul|Selected to evaluate whether backend-specific output layout bugs can be generalized into reusable memory-layout and API-contract testing knowledge.|Memory Layout Boundary + API Contract Boundary|Good|Good|High|Good|Pass|Correctly abstracts non-contiguous output tensor handling into a transferable out-parameter testing strategy.|
|004|torch_matmul_knowledge_004|torch_matmul_pattern_004|torch.matmul|Selected as a representative memory safety issue involving out= semantics and view storage constraints.|Memory Layout Boundary + Shape Boundary|Good|Good|High|Good|Pass|Correctly extracts insufficient storage and implicit resize risks into general memory safety testing knowledge.|
|005|torch_mm_knowledge_001|torch_mm_pattern_001|torch.mm|Low-level matrix multiplication primitive; selected to evaluate cross-API generalization with torch.matmul and backend validation consistency.|Shape Boundary + API Contract Boundary|Good|Good|High|Good|Pass|Knowledge successfully generalizes backend-specific shape validation inconsistency into a reusable shape-contract testing strategy.|
|006|torch_nn_Conv2d_knowledge_001|torch_nn_Conv2d_pattern_001|torch.nn.Conv2d|Representative neural network layer; selected because convolution APIs contain complex shape parameters and multiple execution paths.|Shape Boundary|Good|Good|High|Good|Pass|Correctly abstracts asymmetric padding dimension mapping issues into general spatial parameter testing knowledge.|
|007|torch_Tensor_as_strided_knowledge_001|torch_Tensor_as_strided_pattern_001|torch.Tensor.as_strided|Representative low-level tensor view API; selected because view operations expose memory layout and autograd state boundary problems.|Gradient State Boundary + Memory Layout Boundary|Good|Good|High|Good|Pass|Successfully transforms a specific autograd/view bug into general gradient propagation and aliasing testing knowledge.|
|008|torch_nn_functional_grid_sample_knowledge_001|torch_nn_functional_grid_sample_pattern_001|torch.nn.functional.grid_sample|Representative neural network functional API; selected because option validation represents API contract boundary problems beyond tensor value mutation.|API Contract Boundary|Good|Good|High|Good|Pass|Successfully abstracts unsupported option validation bugs into a reusable parameter-contract testing strategy.|
|009|torch_einsum_knowledge_001|torch_einsum_pattern_001|torch.einsum|Representative high-level tensor operation; selected because it exposes autograd state and mutation-related boundary issues.|Gradient State Boundary + API Contract Boundary|Good|Good|High|Good|Pass|Successfully generalizes an operation-specific autograd mutation issue into reusable gradient-state testing knowledge. Minor formatting issue: important_considerations should be normalized into an array.|
|010|Tensor_setitem_knowledge_001|Tensor_setitem_pattern_001|Tensor.__setitem__|Representative tensor indexing API; selected because indexed assignment combines dtype conversion, broadcasting, and view semantics.|Dtype Boundary|Good|Good|Medium|Good|Pass|Correctly abstracts dtype promotion issues in indexed assignment into a reusable dtype-boundary testing strategy.|

# Additional Evaluation for GitHub Issue Generated Knowledge

The following knowledge entries are generated from newly collected
PyTorch GitHub issue reports.

The evaluation focuses on whether the generated knowledge:
- correctly follows the source pattern,
- provides reusable testing strategies,
- avoids literal reproduction of historical bugs,
- can guide future harness generation.


|ID|Knowledge ID|Source Pattern|API|Risk Category|Pattern-Knowledge Alignment|Abstraction Quality|Transferability|Harness Guidance|Overall|Comment|
|-|-|-|-|-|-|-|-|-|-|-|
|011|torch_add_knowledge_001|torch_add_pattern_001|torch.add|Backend Dispatch Boundary + Dtype Boundary|Good|Good|High|Good|Pass|Correctly abstracts scalar overflow and backend inconsistency into a general dtype conversion and multi-backend testing strategy instead of reproducing the original fp16 torch.add case.|
|012|torch_addmm_knowledge_001|torch_addmm_pattern_001|torch.addmm|Memory Layout Boundary + API Contract Boundary|Good|Good|High|Good|Pass|Successfully generalizes out parameter aliasing problems into reusable input-output storage alias testing guidance for APIs with out= or in-place semantics.|
|013|torch_cat_knowledge_001|torch_cat_pattern_001|torch.cat|Shape Boundary + Gradient State Boundary|Good|Good|Medium|Good|Pass|Correctly extracts zero-sized tensor and accelerator autograd interaction risks into a transferable empty tensor testing strategy.|
|014|torch_index_select_knowledge_001|torch_index_select_pattern_001|torch.index_select|API Contract Boundary + Graph Transformation Boundary|Good|Good|High|Good|Pass|Successfully abstracts missing validation differences between eager and compiled execution into general compiler semantic consistency testing.|
|015|torch_mm_knowledge_002|torch_mm_pattern_002|torch.mm|Dtype Boundary + Backend Dispatch Boundary|Good|Good|Medium|Good|Pass|Correctly identifies backend-specific dtype support differences and converts them into reusable dtype/backend compatibility testing knowledge.|
|016|torch_relu_knowledge_001|torch_relu_pattern_001|torch.relu|Graph Transformation Boundary + Numerical Edge Case|Good|Good|High|Good|Pass|Successfully generalizes compiler numerical inconsistencies involving special floating-point values into reusable activation and elementwise testing strategies.|
|017|torch_reshape_knowledge_001|torch_reshape_pattern_001|aten::_reshape_alias_copy|API Contract Boundary + Memory Layout Boundary|Good|Good|High|Good|Pass|Correctly abstracts invalid size/stride metadata handling into general tensor geometry and memory safety testing guidance.|
|018|torch_softmax_knowledge_001|torch_softmax_pattern_001|torch.softmax|Dtype Boundary + Numerical Edge Case|Good|Good|High|Good|Pass|Successfully transforms low-precision numerical inconsistency into a reusable precision-path comparison strategy.|
|019|torch_mul_knowledge_003|torch_mul_pattern_003|torch.mul|Shape Boundary + Memory Layout Boundary|Good|Good|High|Good|Pass|Correctly abstracts sparse-dense broadcasting failure into a general sparse layout normalization and broadcasting testing strategy.|
