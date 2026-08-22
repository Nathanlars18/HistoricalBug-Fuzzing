# Pattern to Knowledge Abstraction Rules


# 1. Purpose


This document defines the transformation rules
from historical bug patterns to reusable testing knowledge.


The goal is to transform concrete bug reproduction
information into general testing guidance that can
help LLMs generate more effective fuzzing harnesses.


The transformation should remove unnecessary
API-specific details while preserving important
bug characteristics.


---

# 2. General Conversion Principle


Historical bug patterns describe:

- specific APIs
- concrete triggering inputs
- exact failure cases


Historical bug knowledge describes:

- general bug principles
- risky input dimensions
- reusable testing strategies


The conversion follows:


Bug Instance

↓

Bug Pattern

↓

Knowledge Abstraction


The generated knowledge should guide LLM reasoning
rather than directly reproduce historical bugs.


---

# 3. Field Mapping Rules


## Rule 1: API Specific Pattern → Bug Theme


### Pattern Field

pattern_abstraction.api_specific_pattern


### Knowledge Field

knowledge_abstraction.bug_theme


### Principle

Remove API-specific names and convert the
specific bug name into a general failure category.


### Example


Pattern:

matmul_unaligned_memory_access_bug


Knowledge:

Memory layout assumption violation


Explanation:

The goal is not to reproduce the exact matmul bug,
but to identify the general risk caused by abnormal
tensor storage layouts.


---


## Rule 2: Trigger Condition → Risk Dimensions


### Pattern Field

trigger_condition


### Knowledge Field

risk_dimensions


### Principle


Concrete trigger values should be generalized
into broader testing dimensions.


Examples:


Pattern:

M = 1


Knowledge:

Degenerate tensor dimensions


---


Pattern:

dtype=int64


Knowledge:

Integer dtype boundary cases


---


Pattern:

data_ptr % 4 != 0


Knowledge:

Abnormal memory alignment conditions


---


## Rule 3: Root Cause → General Principle


### Pattern Field

root_cause


### Knowledge Field

general_principle


### Principle


Convert implementation-specific explanations
into general mechanisms.


Example:


Pattern:

BLAS assumes aligned memory but receives
unaligned tensor storage.


Knowledge:

Backend implementations may rely on hidden
memory layout assumptions.


---


## Rule 4: Harness Strategy → Testing Insights


### Pattern Field

harness_strategy


### Knowledge Field

testing_insights


### Principle


Convert historical reproduction methods into
general exploration strategies.


Example:


Pattern:

Create tensor from buffer with offset.


Knowledge:

Explore tensors with unusual storage layouts.


---


## Rule 5: Bug Oracle → Oracle Strategy


### Pattern Field

bug_oracle


### Knowledge Field

testing_insights.oracle_strategy


### Principle


Preserve the failure detection method.


Examples:


Crash:

Monitor sanitizer failures.


Wrong Result:

Compare output against reference implementation.


Memory Corruption:

Check invalid memory modification.


---


## Rule 6: Pattern Category → Risk Category


### Pattern Field

bug_category


### Knowledge Field

knowledge_abstraction.risk_category


### Principle


Map concrete bug categories into predefined
knowledge categories.


---


# 4. Example Transformation


## Input Pattern


```json

{
"api_specific_pattern":
"matmul_unaligned_memory_access_bug",

"trigger_condition":
{
"memory":
"data_ptr % 4 !=0"
},

"root_cause":
"BLAS assumes aligned memory"
}

## Output Knowledge

{
"bug_theme":
"Memory layout assumption violation",

"general_principle":
"Backend implementations may fail when tensor
storage violates hidden memory assumptions",

"risk_dimensions":
{
"memory":
"abnormal tensor storage layout"
},

"testing_insights":
{
"input_exploration":
"Explore non-contiguous and unusual memory layouts"
}
}
