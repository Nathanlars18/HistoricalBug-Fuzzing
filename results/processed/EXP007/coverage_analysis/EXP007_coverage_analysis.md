# EXP007 Coverage Analysis


## 1. Observation

During coverage collection,
all baseline experiments reported:

Coverage increase: 0


## 2. Investigation


The fuzzing process successfully executed:

- libFuzzer initialized
- target binary loaded
- inputs executed
- crashes reproduced


However, coverage extraction failed to reflect
the actual execution.


## 3. Possible Reason


The current experiment pipeline mixes:

- fuzz binary
- coverage binary
- result collection script


The generated coverage report does not correspond
to the fuzzing execution.


## 4. Conclusion


The coverage value is considered invalid
for this experiment.

Crash discovery results remain valid because
they are obtained from real fuzz execution.

