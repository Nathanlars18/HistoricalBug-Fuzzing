# EXP006 Knowledge Quality Summary


## Dataset

Total generated knowledge:
71


## Manual Evaluation Progress

Evaluated:
20 / 71


## Current Results

Pass:
20

Minor Issue:
0

Major Issue:
0


## Evaluation Scope

The evaluation checks:

- Pattern-knowledge consistency
- Knowledge abstraction quality
- Transferability
- Harness generation usefulness


## Observed Issues

1. Some list fields may occasionally be generated as strings.
   - Fixed through normalization.

2. Some generalized testing strategies may extend beyond original reports.
   - Considered acceptable because knowledge aims at transferable testing guidance.

3. Newly generated knowledge entries occasionally contain broader
transferability descriptions than the original issue scope.
These cases were manually reviewed and accepted because the goal
of knowledge generation is reusable fuzzing guidance rather than
exact bug reproduction.


## Additional Evaluation Results

Nine newly generated knowledge entries from GitHub Issue based
bug patterns were manually evaluated.

All evaluated entries passed the quality criteria.

The results indicate that the generated knowledge can:
- preserve the semantics of source bug patterns,
- provide reusable testing guidance,
- support future harness generation.
