# EXP005 FlashFuzz Coverage Baseline


## Goal

Evaluate FlashFuzz generated harness coverage performance on PyTorch 2.2 CPU APIs.

This experiment establishes baseline results for later Historical Bug Pattern Enhanced Harness comparison.


## Environment

- OS: WSL2 Ubuntu
- Framework: PyTorch 2.2
- Backend: CPU
- Compiler: clang 14
- Fuzzer: libFuzzer
- Mode: LLVM coverage fuzzing


## Configuration

Target APIs:

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


Time budget:

600 seconds/API


## Problems and Solutions


### Problem 1: Coverage data collection failure

Symptom:

No profraw files found.

Cause:

Coverage harness output path mismatch.

Solution:

Modified:

- docker/torch-2.2-cov.Dockerfile
- scripts/template/torch_cpu_cov/copy.py


Commit:

789d9af7


### Problem 2: Coverage result collection failure

Symptom:

Coverage summary could not be generated.

Cause:

expmanager.py copied results incorrectly.

Solution:

Modified expmanager.py.

Commit:

eba1e89d


## Results


| API | Time | Covered branches |
|-|-|-|
|torch.add|600s|235|


Coverage trend:

|Time|Branches|
|-|-|
|0-60|202|
|60-120|202|
|120-180|203|
|180-240|203|
|240-300|233|
|300-360|233|
|360-420|233|
|420-480|235|
|480-540|235|
|540-600|235|


## Next Step

Run remaining APIs.
### torch.mul


Configuration:

- Time budget: 600s


Coverage result:

| Metric | Value |
|-|-|
| Covered branches | 297 |
| Total branches | 30094 |
| Branch coverage | 0.99% |


Coverage evolution:

| Time | Covered branches |
|-|-|
|0-60s|286|
|60-120s|286|
|120-180s|286|
|180-240s|286|
|240-300s|292|
|300-360s|296|
|360-420s|296|
|420-480s|297|
|480-540s|297|
|540-600s|297|


Result:

Successfully completed.
### torch.matmul


Configuration:

- Time budget: 600s


Coverage result:

| Metric | Value |
|-|-|
| Covered branches | 606 |
| Total branches | 30094 |
| Branch coverage | 2.01% |


Coverage evolution:

| Time | Covered branches |
|-|-|
|0-60s|329|
|60-120s|338|
|120-180s|443|
|180-240s|509|
|240-300s|515|
|300-360s|588|
|360-420s|590|
|420-480s|598|
|480-540s|606|
|540-600s|606|


Result:

Successfully completed.
### torch.mm


Configuration:

- Time budget: 600s


Coverage result:

| Metric | Value |
|----|----|
| Covered branches |160|
| Total branches |30094|
| Branch coverage |0.53%|


Coverage evolution:

| Time | Covered branches |
|-|-|
|0-60s|117|
|60-120s|124|
|120-180s|124|
|180-240s|124|
|240-300s|160|
|300-360s|160|
|360-420s|160|
|420-480s|160|
|480-540s|160|
|540-600s|160|


Result:

Successfully completed.

### torch.addmm


Configuration:

- Time budget: 600s


Coverage result:

| Metric | Value |
|----|----|
| Covered branches | 126 |
| Total branches | 30094 |
| Branch coverage | 0.42% |


Coverage evolution:

| Time | Covered branches |
|-|-|
|0-60s|124|
|60-120s|125|
|120-180s|125|
|180-240s|126|
|240-300s|126|
|300-360s|126|
|360-420s|126|
|420-480s|126|
|480-540s|126|
|540-600s|126|


Result:

Successfully completed.
### torch.relu


Configuration:

- Time budget: 600s


Coverage result:

| Metric | Value |
|----|----|
| Covered branches |151|
| Total branches |30094|
| Branch coverage |0.50%|


Coverage evolution:

| Time | Covered branches |
|-|-|
|0-60s|142|
|60-120s|142|
|120-180s|142|
|180-240s|144|
|240-300s|144|
|300-360s|144|
|360-420s|151|
|420-480s|151|
|480-540s|151|
|540-600s|151|


Result:

Successfully completed.
### torch.sigmoid


Configuration:

- Time budget: 600s


Coverage result:

| Metric | Value |
|----|----|
| Covered branches | 164 |
| Total branches | 30094 |
| Branch coverage | 0.54% |


Coverage evolution:

| Time | Covered branches |
|-|-|
|0-60s|164|
|60-120s|164|
|120-180s|164|
|180-240s|164|
|240-300s|164|
|300-360s|164|
|360-420s|164|
|420-480s|164|
|480-540s|164|
|540-600s|164|

### torch.softmax


Configuration:

- Time budget: 600s


Coverage result:

| Metric | Value |
|----|----|
| Covered branches | 271 |
| Total branches | 30094 |
| Branch coverage | 0.90% |


Coverage evolution:

| Time | Covered branches |
|-|-|
|0-60s|267|
|60-120s|269|
|120-180s|269|
|180-240s|271|
|240-300s|271|
|300-360s|271|
|360-420s|271|
|420-480s|271|
|480-540s|271|
|540-600s|271|
### torch.tanh


Configuration:

- Time budget: 600s


Coverage result:

| Metric | Value |
|----|----|
| Covered branches | 241 |
| Total branches | 30094 |
| Branch coverage | 0.80% |


Coverage evolution:

| Time | Covered branches |
|-|-|
|0-60s|226|
|60-120s|238|
|120-180s|239|
|180-240s|239|
|240-300s|241|
|300-360s|241|
|360-420s|241|
|420-480s|241|
|480-540s|241|
|540-600s|241|
### torch.exp


Configuration:

- Time budget: 600s


Coverage result:

| Metric | Value |
|----|----|
| Covered branches | 188 |
| Total branches | 30094 |
| Branch coverage | 0.62% |


Coverage evolution:

| Time | Covered branches |
|-|-|
|0-60s|178|
|60-120s|178|
|120-180s|186|
|180-240s|187|
|240-300s|187|
|300-360s|188|
|360-420s|188|
|420-480s|188|
|480-540s|188|
|540-600s|188|

# EXP005 FlashFuzz Coverage Evaluation
## Experiment Versions


### Version 1: Original FlashFuzz Coverage Baseline


Location:

original_flashfuzz/


LLM:

Original FlashFuzz configuration


Purpose:

Historical coverage baseline.


---

### Version 2: DeepSeek Reproduction


Location:

deepseek_reproduction/


LLM:

DeepSeek-V4-Pro


Purpose:

Collect coverage baseline under
the final experimental LLM setting.
