# Role

You are a researcher constructing a historical bug pattern dataset
for PyTorch fuzzing.


# Task

Analyze the following PyTorch bug report.

Determine whether it can be converted into a reusable bug pattern
and harness generation knowledge.


# Criteria


Include a bug if:

1. The trigger condition can be reproduced by input generation.

2. The failure has a clear oracle.

3. The bug can be abstracted into a general pattern.


Exclude:

1. Pure documentation issues.

2. Pure performance regression.

3. Environment-specific issues.

4. Network or external dependency failures.


# Reference Examples


Example 1:

Bug:
torch.cosine_similarity accepts tensors with different ranks.

Pattern:
Shape Boundary

Include:
Yes


Example 2:

Bug:
kthvalue returns wrong result on non-contiguous CUDA tensor.

Pattern:
Memory Layout Boundary

Include:
Yes


# Input Bug Report

{bug_report}


# Output

Return JSON only.

The JSON format must strictly follow:

{
    "target_api": "",
    "bug_category": "",
    "trigger_condition": "",
    "oracle_type": "",
    "pattern_extractability": "",
    "knowledge_generation_feasibility": "",
    "include": "",
    "reason": "",
    "confidence": ""
}


Field constraints:


target_api:

The main PyTorch API affected by the bug.


bug_category:

Choose exactly one:

- Shape Boundary
- Memory Layout Boundary
- Dtype Boundary
- Device Boundary
- Gradient Boundary
- State Boundary
- Other


trigger_condition:

Describe the input condition that triggers the bug.


oracle_type:

Choose exactly one:

- Crash
- Exception
- Incorrect Output
- Performance Issue
- Documentation Issue


pattern_extractability:

Choose exactly one:

- High
- Medium
- Low


knowledge_generation_feasibility:

Choose exactly one:

- High
- Medium
- Low


include:

Choose exactly one:

- Yes
- No


confidence:

Choose exactly one:

- High
- Medium
- Low


Do not add explanations outside JSON.
