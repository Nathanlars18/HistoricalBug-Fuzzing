# Historical Bug Knowledge Schema


## 1. Metadata

Basic information of this knowledge item.

Fields:

- Knowledge ID
- Source Pattern ID
- Source Report
- API Name
- Original Issue
- verification_status

The reliability level of the original bug report.

Examples:
- official_triaged
- fixed
- user_reported


- Confidence
The confidence of extracted knowledge abstraction.

Values:
- high
- medium
- low

Purpose:

Identify the origin of the extracted knowledge.


---

## 2. Knowledge Abstraction


Describe the general bug principle extracted from historical bugs.


Fields:

- Bug Theme

The high-level description of the bug.


- General Principle

The underlying reason why similar bugs may happen.


- Risk Category

General categories:

1. Shape Boundary
2. Dtype Boundary
3. Device Transition
4. Memory Layout Boundary
5. Numerical Edge Case
6. Gradient State Boundary
7. Backend Dispatch Boundary
8. Execution State Boundary
9. Graph Transformation Boundary
10. API Contract Boundary


---

## 3. Risk Dimensions


Describe which input dimensions are related to potential bugs.


Fields:

- Shape

Possible shape-related risks.


- Dtype

Possible datatype-related risks.


- Memory

Possible storage/layout-related risks.


- Device

Possible device/backend transition risks.


- Execution State

Possible operation state risks.


---

## 4. Failure Mechanism


Describe why the bug can happen.

Fields:

- Layer

- Description

Possible layers:

- API Layer
- ATen Layer
- Kernel Layer
- Backend Layer
- Numerical Layer


---

## 5. Testing Insights


Describe general testing strategies learned from historical bugs.


Fields:

- Input Exploration

What kinds of inputs should be explored.


- Constraint Awareness

Important constraints to consider.


- Oracle Strategy

How to detect failures.


---

## 6. Transferability


Describe whether this knowledge can apply to other APIs.


Fields:

- Level

high / medium / low

Describe whether this knowledge represents
a general testing principle beyond the original API.

- Reason

---

## 7. LLM Reasoning Guidance


Knowledge usage instructions for LLM.


Fields:

- Important Considerations

Important testing directions.


- Avoid Literal Reproduction

Whether LLM should avoid directly copying
historical bug reproduction.


- Generation Strategy

How LLM should transform knowledge into harness logic.


