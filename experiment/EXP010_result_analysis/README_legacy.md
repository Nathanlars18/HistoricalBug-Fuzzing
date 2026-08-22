# EXP010 Result Analysis

## Purpose

Analyze whether historical bug knowledge is effectively transferred into generated harnesses.

## Target API

torch.matmul

## Input Experiments

- EXP007 baseline/pattern
- EXP008 multi-pattern
- EXP009 reasoning-pattern

## Analysis Components

1. Coverage analysis
2. Harness transformation analysis
3. Pattern-to-Harness mapping
4. Knowledge-to-Prompt traceability

## Main Finding

Historical bug knowledge affects harness generation by introducing:
- tensor layout transformations
- non-contiguous tensor exploration
- output tensor constraint testing

The generated harness generalizes bug mechanisms instead of reproducing individual historical bugs.
