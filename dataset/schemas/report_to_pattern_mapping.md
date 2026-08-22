Report to Pattern Mapping Design
1. Purpose
Bug Report to Pattern Mapping describes how structured historical bug reports are transformed into bug patterns.
The purpose is to maintain the traceability between:
Raw Bug Report

        ↓

Structured Bug Report

        ↓

Bug Pattern

        ↓

Knowledge Pattern
Bug Report preserves concrete bug information.
Bug Pattern abstracts reusable defect characteristics.
This mapping explains why a specific historical bug can be represented by a specific pattern.
2. Relationship Between Bug Report and Pattern
A Bug Report represents one concrete historical bug.
Example:
torch.matmul crashes when tensor storage alignment is invalid
A Bug Pattern represents an abstract defect pattern extracted from one or more bug reports.
Example:
Memory Layout Boundary
Therefore:
One Bug Report
        |
        ↓
One or More Bug Patterns
and:
One Bug Pattern
        |
        ↓
Multiple Historical Bugs
The relationship is not strictly one-to-one.
3. Mapping Principles
The mapping process considers the following information from Bug Report:
3.1 API Information
Used to determine:
affected API
operator
module
Example:
torch.matmul
is mapped to:
torch.matmul_out_view_memory_bug
3.2 Trigger Condition Matching
Trigger conditions are the most important evidence.
The mapping compares:
Bug Report:
non-contiguous tensor
with Pattern:
Memory Layout Boundary
because both describe abnormal tensor storage layout.
The following dimensions are considered:
Shape
Dtype
Device
Backend
Layout
Memory
State
3.3 Root Cause Matching
Root cause information is used to identify the underlying defect mechanism.
Example:
Bug Report:
Backend assumes aligned memory
Pattern:
Memory Layout Boundary
Reason:
The failure is caused by invalid tensor storage assumptions.
3.4 Bug Oracle Matching
Observable failure behavior is preserved.
Example:
Bug Report:
SIGBUS
Pattern:
Crash
This ensures that the generated Pattern keeps the bug detection condition.
4. Mapping Example
Example 1
Bug Report
Bug ID:
pytorch_191238


API:
torch.matmul


Trigger:
unaligned float32 tensor storage


Failure:
SIGBUS
↓
Pattern
API Specific Pattern:

torch.matmul_alignment_memory_bug


General Category:

Memory Layout Boundary
Mapping Reason
The bug is caused by abnormal tensor storage alignment rather than mathematical computation.
Therefore it is abstracted as a memory layout related pattern.
5. Pattern Abstraction Levels
The mapping supports two abstraction levels.
API Specific Pattern
Describes the concrete pattern of a specific API.
Example:
torch.matmul_out_view_memory_bug
General Pattern Category
Describes reusable patterns across different APIs.
Example:
Memory Layout Boundary
This abstraction enables future transfer across APIs.
6. Mapping Confidence
Each mapping should have a confidence level.
High
Conditions:
Trigger condition is clear
Root cause is confirmed
Fix information exists
Medium
Conditions:
Trigger condition is available
Root cause is partially known
Low
Conditions:
Only failure behavior is observed
7. Role in Research Questions
RQ1
The mapping provides ground truth for evaluating whether LLM can correctly extract bug patterns from historical bug reports.
RQ2
The mapping proves that the injected knowledge originates from real historical bugs.
RQ3
The mapping helps analyze whether general patterns can transfer across different APIs.
