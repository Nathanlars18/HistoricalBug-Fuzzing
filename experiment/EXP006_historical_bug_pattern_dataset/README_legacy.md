# EXP006 Historical Bug Pattern Dataset Construction


## Goal

Construct a historical bug pattern dataset for enhancing LLM-based harness generation.

The dataset extracts reusable testing patterns from real PyTorch bug reports.


## Data Source

PyTorch GitHub Issues and Pull Requests.


## Target APIs

- torch.add
- torch.mul
- torch.matmul
- torch.mm
- torch.addmm
- torch.relu
- torch.sigmoid
- torch.softmax
- torch.tanh
- torch.exp


## Bug Pattern Fields

Each bug contains:

- API
- Bug description
- Trigger condition
- Input shape
- dtype
- device
- Oracle
- Root cause
- Fix information


## Pattern Categories

Initial categories:

- empty tensor
- boundary shape
- special dtype
- NaN / Inf
- non-contiguous tensor
- gradient related
- device related


## Goal

Transform historical bug knowledge into executable harness generation constraints.
## Current Dataset Status

Target API:
- torch.matmul

Collected Bug Patterns:

| ID | Issue | Type |
|-|-|-|
|001|#191238|Crash|
|002|#71774|Wrong Result|
|003|#104832|Wrong Result|
|004|#170573|Invalid Output Constraint|


Total:

4 historical bug patterns
