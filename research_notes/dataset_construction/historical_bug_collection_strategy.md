# Historical Bug Collection Strategy

## 1. Overview

This document describes the methodology used to construct the
historical bug dataset for PyTorch fuzzing research.

The objective of this dataset is to collect real-world PyTorch bugs
and transform them into reusable bug patterns and knowledge for
automatic harness generation.

The dataset construction process follows a data-driven approach.

Instead of defining bug patterns in advance and searching for
corresponding issues, we first collect historical bugs and then
extract generalized patterns from the collected data.


---

# 2. Dataset Construction Pipeline


The complete pipeline contains four stages:

GitHub Issues
      |
      v
Bug Issue Collection
      |
      v
Manual Filtering
      |
      v
Structured Bug Report Generation
      |
      v
Bug Pattern Extraction
      |
      v
Knowledge Base Construction
      |
      v
Pattern Distribution Analysis


---

# 3. Bug Source


Historical bugs are collected from the official PyTorch repository:


https://github.com/pytorch/pytorch/issues


Each collected issue preserves:

- issue title
- issue description
- reproduction code
- environment information
- discussion information
- related pull requests


---

# 4. API Selection


The dataset focuses on selected PyTorch APIs.

APIs are selected based on:


1. Importance in deep learning workloads.

2. Availability of historical issues.

3. Existing fuzzing relevance.

4. Diversity of API behaviors.


The selected APIs include:

- matrix operations
- tensor operations
- neural network operators
- mathematical operators


---

# 5. Historical Bug Collection Process


## Phase 1: API-oriented Discovery


For each selected API, we search the PyTorch issue database
using API-related keywords.


Examples:


repo:pytorch/pytorch torch.mm
repo:pytorch/pytorch torch.addmm


The objective is to discover historical bugs related to
the target API.


At this stage, no predefined bug pattern constraints are applied.


---

## Phase 2: Manual Filtering


Collected candidate issues are manually reviewed.

The purpose is to identify bugs that can provide useful
information for fuzzing and harness generation.


## Included Issues


### Incorrect Behavior

Examples:

- wrong results
- incorrect outputs
- silent correctness failures


### Runtime Failures

Examples:

- crashes
- unexpected RuntimeError
- internal errors


### Backend-specific Bugs

Examples:

- CPU/CUDA inconsistency
- MPS backend failures


### Invalid Input Handling

Examples:

- unsupported dtype behavior
- abnormal tensor layouts
- boundary conditions



## Excluded Issues


### Feature Requests

Examples:

support xxx
add xxx


### Pure Performance Issues

Examples:

slow
optimization
performance regression


### Documentation-only Issues


### Duplicate Reports


---

# 6. Bug Report Generation


Filtered issues are converted into structured bug reports.

Each report contains:


- affected API
- bug category
- triggering conditions
- input constraints
- environment
- reproduction information
- failure oracle


---

# 7. Bug Pattern Extraction


Bug patterns are automatically extracted from
structured bug reports.


The purpose is to identify reusable triggering characteristics.


Examples:


Issue:

torch.mm fails with bool tensors on MPS


Extracted Pattern:

Unsupported dtype reaches backend implementation



Issue:

torch.addmm produces incorrect output when out aliases input


Extracted Pattern:

Output tensor aliasing causes incorrect computation



---

# 8. Knowledge Base Construction


Bug patterns are further transformed into structured knowledge.


Knowledge describes:


- affected API behavior
- triggering conditions
- input generation strategy
- expected oracle


The knowledge base is later used for
pattern-enhanced harness generation.


---

# 9. Pattern Distribution Analysis


After bug pattern extraction, we analyze the distribution
of extracted patterns.


The analysis is performed on the final pattern dataset,
rather than during issue collection.


The objective is to answer:


"What general bug patterns exist in historical PyTorch bugs?"


Example:


Memory Alias        8
Dtype Boundary      7
Shape Boundary      6
Backend Dispatch    5


The distribution is used to evaluate whether
generalizable bug knowledge can be obtained.


---

# 10. Data Organization


Raw collected issues:


dataset/interim/github_issue_collection/


Example:


torch.mm/
    issue_191693_bool_mps_mm.txt
    issue_85852_out_alias_mm.txt


Generated reports:


experiment/EXP006_historical_bug_pattern_dataset/bug_reports/


Generated patterns:


experiment/EXP006_historical_bug_pattern_dataset/bug_patterns/


Knowledge:


experiment/EXP006_historical_bug_pattern_dataset/knowledge_base/


---

# 11. Quality Control


Before converting issues:


Each issue is checked for:


1. Is it a real software bug?

2. Is the affected API clear?

3. Are triggering conditions available?

4. Can it provide harness generation guidance?

5. Is it duplicated with existing issues?
