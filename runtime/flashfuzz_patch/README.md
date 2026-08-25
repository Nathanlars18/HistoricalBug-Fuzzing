# FlashFuzz Patch

This directory contains modifications applied to FlashFuzz
for the HistoricalBug-Fuzzing project.

## Base Version

Repository:
FlashFuzz

Original Commit:
c1c752963596528e4752360cdaeac77a80f7e07d

## Modified Files

- expmanager.py

  Purpose:
  Extend experiment management for multi-API fuzzing.


- scripts/build_test_harness.py

  Purpose:
  Modify harness generation process.


- scripts/coverage_fuzzing.py

  Purpose:
  Modify coverage collection process.


## Usage

Clone FlashFuzz separately:

third_party/FlashFuzz/

Then apply these files before running experiments.
