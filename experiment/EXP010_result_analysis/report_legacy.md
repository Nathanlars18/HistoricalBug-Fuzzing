# EXP010 Torch.matmul Result Analysis


## Experimental Setting

Target API:

torch.matmul


Framework:

PyTorch 2.2


Time budget:

600 seconds


Compared Methods:

1. Baseline
2. Single historical bug pattern
3. Multi historical bug patterns
4. Reasoning-based pattern integration



## Coverage Result


|Method|Coverage|
|-|-|
|Baseline|1.82%|
|Single Pattern|1.77%|
|Multi Pattern|2.04%|
|Reasoning Pattern|2.02%|



## Analysis


Compared with baseline, multi-pattern achieves:

12.09% relative coverage improvement.


Single pattern does not improve coverage,
indicating that isolated historical bug knowledge
may be insufficient for exploring complex tensor
behaviors.


Multi-pattern combination provides stronger guidance
by covering multiple trigger conditions including
shape, dtype and memory layout constraints.


Reasoning-based pattern integration achieves similar
performance with multi-pattern strategy.


# EXP010: Torch.matmul Coverage Result Analysis


## 1. Experiment Objective

This experiment analyzes the effectiveness of historical bug pattern enhanced harness generation.

Based on previous experiments:

- EXP007: single historical bug pattern injection
- EXP008: multi historical bug pattern injection
- EXP009: reasoning-based historical bug pattern generation

we compare their coverage performance with the original FlashFuzz baseline.


The target API is:

- API: torch.matmul
- Framework: PyTorch 2.2
- Backend: CPU
- Fuzzing engine: libFuzzer
- Time budget: 600 seconds


The main research question:

> Can historical bug patterns improve the testing effectiveness of generated harnesses?


---

## 2. Experimental Configurations


Four configurations are compared:


| Method | Description |
|------|------|
| baseline | Original FlashFuzz generated harness without historical bug knowledge |
| single_pattern | Harness enhanced with one historical bug pattern |
| multi_pattern | Harness enhanced with multiple historical bug patterns |
| reasoning_pattern | LLM reasoning over historical bug patterns to generate testing strategy |



---

## 3. Coverage Comparison


The final branch coverage results are:


| Method | Final Coverage | Improvement |
|---|---|---|
| baseline | 1.82% | - |
| single_pattern | 1.77% | -2.75% |
| multi_pattern | 2.04% | +12.09% |
| reasoning_pattern | 2.02% | +10.99% |



The coverage curve is shown below:


![Torch.matmul Coverage Curve](figures/torch.matmul_coverage_curve.png)



---

## 4. Result Analysis


### 4.1 Baseline Performance


The original FlashFuzz harness achieved:

Coverage: 1.82%

This result is used as the reference point for evaluating historical bug pattern enhancement.



---

### 4.2 Single Pattern Enhancement


The single-pattern strategy achieved:

Coverage: 1.77%

which is slightly lower than the baseline:


1.82% -> 1.77%
(-2.75%)


This indicates that introducing only one historical bug pattern does not always improve fuzzing effectiveness.

A possible reason is that a single pattern may bias the generated harness toward a narrow input space, reducing exploration diversity.

Therefore, historical bug information needs to be combined with broader testing knowledge rather than directly applied as a single constraint.



---

### 4.3 Multi Pattern Enhancement


The multi-pattern strategy achieved:


Coverage: 2.04%


Compared with baseline:


2.04% - 1.82% = +12.09%


The result demonstrates that combining multiple historical bug patterns can improve harness exploration ability.

Multiple patterns provide different input generation strategies, including:

- boundary tensor shapes
- special dtype conditions
- memory layout cases
- edge-case tensor states


These complementary constraints help the generated harness explore additional ATen native code paths.



---

### 4.4 Reasoning Pattern Enhancement


The reasoning-based strategy achieved:


Coverage: 2.02%


Compared with baseline:


+10.99%


The result is close to the manually designed multi-pattern strategy.

This suggests that LLM-based reasoning can effectively summarize and generalize historical bug knowledge instead of simply copying individual bug cases.

The reasoning process allows historical bugs to be transformed into more general testing strategies.



---

## 5. Overall Findings


The torch.matmul experiment provides three main observations:


### Finding 1

A single historical bug pattern is insufficient to guarantee coverage improvement.

Although historical bugs contain valuable testing information, directly injecting one pattern may restrict exploration.



### Finding 2

Multiple historical bug patterns significantly improve testing effectiveness.

The multi-pattern strategy improves branch coverage by:

+12.09%

compared with the baseline.



### Finding 3

LLM reasoning can effectively utilize historical bug knowledge.

The reasoning-based strategy achieves:

+10.99%

coverage improvement, close to the manually constructed multi-pattern approach.



---

## 6. Conclusion


The EXP010 analysis validates the effectiveness of historical bug pattern enhanced harness generation.

For torch.matmul:

- single pattern enhancement shows limited effectiveness;
- multi-pattern enhancement provides clear coverage improvement;
- LLM reasoning over historical bug patterns achieves comparable performance.


These results support the hypothesis that historical bug knowledge can improve automated testing

## 4. Historical Bug Knowledge to Harness Analysis

To verify whether historical bug knowledge is effectively utilized, we performed a Pattern-Harness mapping analysis.

The analysis shows that historical knowledge affects the generated harness in three major aspects:

1. Tensor transformation:
   - non-contiguous tensors
   - tensor view transformations
   - memory layout variations

2. API invocation:
   - introduction of matmul_out testing
   - abnormal output tensor generation

3. Testing strategy:
   - generalized exploration instead of literal bug reproduction

Detailed analysis:

- analysis/torch.matmul_pattern_mapping.csv
- analysis/torch.matmul_knowledge_traceability.csv
- analysis/torch.matmul_harness_analysis.md
