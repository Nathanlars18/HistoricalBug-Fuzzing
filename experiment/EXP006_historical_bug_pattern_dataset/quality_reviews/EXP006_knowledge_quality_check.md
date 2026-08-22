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
