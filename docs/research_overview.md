# Research Overview

## Research goal

This project investigates whether knowledge derived from historical bugs can
guide large language models to generate more effective fuzzing harnesses for
deep-learning frameworks. The current artifact focuses on PyTorch and compares
baseline, single-pattern, multi-pattern, and knowledge-guided reasoning methods.

## Relationship to FlashFuzz

This repository is not a FlashFuzz fork and does not maintain the FlashFuzz
source code. FlashFuzz is a third-party harness execution and fuzzing dependency
that will be integrated under `third_party/FlashFuzz`.

## Research data flow

```text
raw issue/report
  -> EXP006 structured bug report
  -> EXP006 bug pattern
  -> EXP006 knowledge base
  -> EXP007 / EXP008 / EXP009 harness generation
  -> EXP010 result analysis
```

Repository-level `dataset/` stores raw source material and interim selection
artifacts. EXP006 is the canonical Historical Bug Information Database and owns
all processed reports, patterns, knowledge, schemas, validation examples, and
construction logic.

EXP005 provides the FlashFuzz coverage baseline. EXP007 tests single-pattern
prompt injection, EXP008 tests multi-pattern injection, EXP009 tests
knowledge-guided reasoning, and EXP010 aggregates the comparison evidence.

## Current scope

The migrated repository is a pilot research artifact. EXP006 currently contains
39 structured bug reports, 39 patterns, and 39 knowledge items, while the main
harness comparison centers on `torch.matmul`.

Future work will expand the information database to 30-50 PyTorch historical
bugs and validate the methods across multiple APIs and repeated trials.
