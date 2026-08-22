# EXP008: Multi Historical Bug Pattern Guided Harness Generation


## Goal

Evaluate whether multiple historical bug patterns can improve
LLM-based PyTorch fuzz harness generation.


## Target API

torch.matmul


## Method

Historical bug patterns:

1. Unaligned memory access
2. Zero dimension tensor
3. Non-contiguous output view
4. Output storage boundary


The patterns are converted into prompt guidance
and provided to LLM during harness generation.


## Compared Methods

|Method|Description|
|-|-|
|Baseline|LLM generated harness without bug knowledge|
|Single Pattern|Harness guided by one historical bug|
|Multi Pattern|Harness guided by four historical bugs|


## Results

Multi-pattern harness:

- Generated LOC: 203
- New fuzzing units: 985
- Branch coverage: 1.89%


## Conclusion

Historical bug patterns can guide LLMs to generate
more targeted tensor input strategies.

Future work will explore automatic pattern selection
instead of manually applying all patterns.
