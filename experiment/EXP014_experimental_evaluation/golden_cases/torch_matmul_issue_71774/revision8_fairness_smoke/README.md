# Revision 8 fairness smoke: `torch.matmul` / Issue #71774

This is a short engineering smoke package for the revision 8 controlled-design
checks. It is not a statistical result and it is not an exact reproduction of
the historical Issue input.

## Scope

- one API: `torch.matmul`;
- three groups: Structured Baseline, Bug-aware Static, and Bug-aware Adaptive;
- one paired repeat and three five-second rounds per group;
- the Static and Adaptive initial Harness use the same validated Baseline
  generic branch;
- the Knowledge-directed Static branch keeps dynamic tensor dimensions and
  `fuzz_int64` data generation.

## Included evidence

The package contains the frozen smoke matrix, both HarnessSpecs, both Strategy
Plans, generated C++ sources, compile/materialization metadata, nine round
records with runtime snapshots, two feedback decisions, and the deterministic
analysis summary.

The generated binaries, `.profraw` coverage files, runtime Corpus files, raw
fuzzer logs, temporary command records, and dirty working-tree snapshots are
intentionally excluded. The raw Runner state remains in the local run
directory and is not a portable source artifact because it contains
host-specific absolute paths.

## Interpretation

The package demonstrates that the revised pipeline can produce, compile,
instrument, execute, observe, and analyze all three groups while preserving the
shared generic branch. It does not establish bug discovery, effectiveness, or
statistical superiority. Those claims require the frozen multi-API pilot.
