# EXP006 Bug Report Quality Summary


## Purpose

This document summarizes manual validation results
of structured bug reports generated from PyTorch GitHub Issues.


## Validation Scope

The validation checks whether generated reports
correctly preserve original issue information.

Criteria:

- Issue mapping
- API identification
- Description preservation
- Raw reference traceability
- Schema correctness


## Overall Result


| Metric | Value |
|---|---|
| Total Checked Reports | XX |
| PASS Reports | XX |
| FAIL Reports | XX |
| Pass Rate | XX% |


## API Level Statistics


| API | Reports | PASS | FAIL |
|---|---|---|---|
| torch.add |3|3|0|
| torch.addmm|4|4|0|
| torch.mm|2|2|0|
| torch.mul|3|3|0|
| torch.relu|3|3|0|
| torch.reshape|3|3|0|
| torch.softmax|5|5|0|


## Failed Cases


### reshape_bug_002

Issue:

#106665


Problem:

API mapping error.

Original issue:
torch.nn.Linear


Generated report:

torch.reshape


Impact:

The bug description remains correct,
but API classification is incorrect.


Recommendation:

Improve API extraction validation
with operator name verification.


## Conclusion


The generated structured reports generally preserve
original PyTorch issue information.

Most reports correctly maintain:
- trigger conditions
- failure behavior
- bug description
- raw references


Future improvement should focus on:
- API extraction validation
- operator normalization
- cross-checking affected API names.

## Excluded Cases

One issue (#106665) was removed after manual API verification.

Reason:
The original issue concerns torch.nn.Linear rather than torch.reshape.

The case was excluded before pattern extraction.
