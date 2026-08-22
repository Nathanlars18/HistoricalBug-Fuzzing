# EXP005: FlashFuzz Coverage Baseline

EXP005 is the FlashFuzz coverage baseline reproduction experiment. It provides
the baseline used to compare historical bug pattern enhanced harnesses in
EXP007, EXP008, and EXP009, and supplies baseline input to EXP010.

The experiment targets the PyTorch APIs listed in `api_list.txt` using PyTorch
2.2 on the CPU backend with libFuzzer. Its results support RQ2.

The migrated source contains final DeepSeek reproduction harnesses for all 10
listed APIs. The source `original_flashfuzz/` directory contains result data but
no `main.cpp` harness files, so no original FlashFuzz harness could be migrated;
the empty `harnesses/original_flashfuzz/` directory documents that missing
source category.

Duplicate FlashFuzz helpers, fuzzing binaries, corpora, build outputs, generated
coverage artifacts, caches, and large logs are intentionally not migrated.
Legacy scripts are preserved without rewriting hardcoded paths.
