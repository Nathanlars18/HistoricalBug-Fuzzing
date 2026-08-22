# EXP009: Pattern Reasoning

EXP009 is a pattern reasoning and knowledge-guided harness-generation
experiment targeting `torch.matmul`. It uses the `knowledge_base` in the EXP006
Historical Bug Information Database as its input.

The method turns historical bug knowledge into harness-generation guidance
through a reasoning prompt. It is compared with the EXP008 multi-pattern prompt
injection method, and its results provide pilot evidence for RQ1 and RQ2.

Experiment-specific scripts, prompts, knowledge configuration, and the
canonical harness are stored under `scripts/`, `prompts/`,
`knowledge_config/`, and `harnesses/reasoning/`. Raw and processed results are
stored in `results/raw/EXP009/` and `results/processed/EXP009/`; analysis files
are under `analysis/RQ1_pattern_effectiveness/EXP009/`.

The original EXP009 README was identical to the EXP008 README and is retained
only as `README_legacy.md`. Three source copies of the reasoning harness were
byte-identical, so only `results/exp009_reasoning_main.cpp` was migrated as the
canonical harness. Large corpora, fuzzing binaries, generated artifacts, and
duplicate FlashFuzz helpers are intentionally not migrated.
