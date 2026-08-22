Bug Report Schema Design
1. Purpose
Bug Report is the structured representation of a historical bug extracted from raw bug reports.
The purpose of Bug Report is to preserve concrete bug information before abstraction into Bug Pattern.
The relationship is:
Raw Bug Report
        |
        v
Structured Bug Report
        |
        v
Bug Pattern
        |
        v
Knowledge Pattern
Bug Report focuses on:
What happened?
Which API is affected?
Under what conditions does the bug occur?
What behavior indicates failure?
It does not contain generalized patterns or testing strategies.
2. Metadata
Fields
{
 "bug_id":"",
 "title":"",
 "date":""
}
Meaning
Basic identification information of the historical bug.
Why needed
Each bug must have a unique identifier so that Pattern and Knowledge can trace back to the original bug source.
Example:
Pattern
   |
   |
source_bug:
pytorch_191238
3. Source Information
Fields
{
"repository":"",
"issue_id":"",
"source_type":"",
"issue_url":"",
"pr_id":"",
"commit_id":""
}
Meaning
Records where the bug originates.
Why needed
Historical bug knowledge requires reliable sources.
Issue provides:
trigger condition
reproduction
observed behavior
PR/Commit provides:
fixing information
root cause clues
4. API Information
Fields
{
"primary_api":"",
"affected_apis":[],
"operator":"",
"module":""
}
Meaning
Describes affected deep learning framework APIs.
Why needed
A single bug may affect multiple APIs.
For example:
one matmul-related bug may also affect:
torch.matmul
torch.mv
torch.addmm
Therefore both primary API and related APIs are recorded.
This field supports:
API retrieval
API identification evaluation in RQ1
5. Bug Description
Field
{
"bug_description":""
}
Meaning
A concise description of the observed bug.
Why needed
Preserves semantic information from the original issue.
It provides context for LLM-based extraction.
6. Trigger Conditions
Fields
{
"shape":[],
"dtype":[],
"device":[],
"backend":[],
"layout":[],
"memory":[],
"state":[],
"operation_context":""
}
Meaning
Describes the input conditions required to trigger the bug.
Why needed
Deep learning framework bugs are usually related to tensor properties.
Different dimensions represent different testing spaces:
Field	Meaning
shape	Tensor dimension conditions
dtype	Data type boundary
device	CPU/CUDA/MPS
backend	Implementation backend
layout	Tensor storage layout
memory	Memory-related conditions
state	Tensor execution state
operation_context	Operation sequence or usage scenario


These fields are later used for Pattern extraction.
7. Failure Behavior
Fields
{
"type":"",
"description":"",
"oracle":""
}
Meaning
Describes observable failure behavior.
Types
Crash

Exception

Incorrect Output

Timeout/Hang

Memory Error
Why needed
Fuzzing requires an oracle to determine whether an input triggers a bug.
8. Root Cause Information
Fields
{
"layer":"",
"description":""
}
Meaning
Stores the known cause of the bug if available.
Possible layers:
API Layer

ATen Layer

Kernel Layer

Backend Layer

Numerical Layer
Why needed
Pattern abstraction requires understanding the mechanism, not only the symptom.
9. Fix Information
Fields
{
"fixed":false,
"fix_description":"",
"commit":""
}
Meaning
Records whether the bug has been fixed and how.
Why needed
Used to evaluate confidence and reliability of historical information.
10. Verification Information
Fields
{
"status":"",
"confidence":""
}
Meaning
Describes verification quality.
Why needed
Different reports have different reliability.
Officially triaged issues are more reliable than unverified user reports.
11. Raw Content Reference
Field
{
"raw_content_reference":""
}
Meaning
Path to original markdown report.
Why needed
Maintains traceability:
JSON
 |
 v
Raw Issue
