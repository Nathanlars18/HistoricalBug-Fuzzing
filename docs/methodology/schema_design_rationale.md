# Schema and Field Design Rationale

## Scope

The repository uses schemas to make intermediate research artifacts machine-checkable and traceable across the pipeline:

`Issue evidence -> Report -> Pattern -> Knowledge -> HarnessSpec -> Strategy Plan -> C++ Harness -> Fuzzing/Feedback -> Analysis`.

A schema is introduced only when a record crosses a layer boundary, must be validated independently, or must remain reproducible after its producer changes. Narrative design decisions stay in rules or protocol documents; executable lowering stays in Builders and emitters. This separation avoids using a schema as an implementation or as an argument that the method is correct.

## Evidence basis

The design draws from four source classes:

1. **Representation standards.** JSON Schema Draft 2020-12 defines local record structure and conditional constraints. W3C PROV supplies the conceptual distinction among entities, activities, derivation, and attribution.
2. **Tool contracts.** LLVM libFuzzer defines the byte-input entry point, corpus/crash behavior, and coverage-guided execution; SanitizerCoverage motivates stable instrumentation-site mappings and counters. PyTorch's official C++ documentation and operator schemas define callable signatures. FlashFuzz source and its published method define the inherited Helper and baseline-Harness boundary.
3. **Empirical bug evidence.** Historical Issue text, reproducer code, and documented outcomes justify risk dimensions, target properties, and Oracles. They do not justify claims outside the cited Issue scope.
4. **Study controls.** Branch budgets, retry ceilings, experiment groups, feedback thresholds, and round duration are project choices. They are versioned and pilot-calibrated rather than presented as external facts.

Authoritative references:

- [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12)
- [W3C PROV-O](https://www.w3.org/TR/prov-o/)
- [LLVM libFuzzer](https://llvm.org/docs/LibFuzzer.html)
- [LLVM SanitizerCoverage](https://clang.llvm.org/docs/SanitizerCoverage.html)
- [PyTorch C++ documentation](https://docs.pytorch.org/cppdocs/)
- [FlashFuzz paper](https://www.cs.cornell.edu/~saikatd/papers/flashfuzz-icst26.pdf)
- [ACM Artifact Review and Badging](https://www.acm.org/publications/policies/artifact-review-and-badging-current)

## Field-group crosswalk

| Field group | Why it exists | Primary basis | Owner and check |
|---|---|---|---|
| identity, version, content hash | prevent silent replacement and make exact records addressable | provenance and artifact reproducibility | Builder computes; Validator checks format/reference/hash |
| parent/derived references | distinguish revision history from semantic derivation | W3C PROV concepts plus project revision policy | Builder resolves exact prior records; Validator rejects missing/cyclic lineage |
| source/evidence references | keep claims bounded by an inspectable excerpt or artifact | Issue/reproducer evidence | Report mapper records; later layers may cite but not rewrite |
| API contract and environment | bind a plan to one callable, version, backend, and overload | PyTorch documentation and runtime probe | API Profile Builder extracts; Validator checks pinned environment |
| Helper capability and dependencies | expose only callable input-construction/observation mechanisms | FlashFuzz source and compile/smoke probes | Helper Builder extracts; review approves semantics; set manifest pins revisions |
| risk dimensions and target properties | state which historical condition the test intends to reach | observed corpus of Pattern/Knowledge records | LLM proposes from Knowledge; controlled vocabulary and Validator constrain |
| activation targets and observation points | distinguish “code ran” from “risk condition occurred” | issue predicates plus instrumentation requirements | HarnessSpec owns semantics; Strategy binds; runtime counters measure |
| Oracle requirements | state the post-call relation that can falsify expected behavior | historical failure mode and API contract | HarnessSpec owns semantic requirement; Strategy/Harness implement it |
| Strategy steps, values, and bindings | make lowering order, dataflow, and fallbacks explicit | C++ type/dataflow and template interface | Strategy Builder emits; Validator checks references and dependency order |
| materialization and instrumentation maps | connect semantic plan elements to generated source spans and runtime sites | generator interface and SanitizerCoverage-style site identity | Generator owns; Validator checks one-to-one mappings |
| round, feedback, crash, and metric records | separate raw execution evidence from deterministic decisions and analysis | libFuzzer outputs plus frozen experiment protocol | Runner records; controller/analyzer derive without rewriting evidence |

## Why these fields, rather than more fields

A field is retained only if all applicable questions have satisfactory answers:

1. Which downstream decision, validation, or audit consumes it?
2. Is it source evidence, deterministic derivation, LLM output, or study configuration?
3. Would recomputing it lose provenance or permit ambiguity?
4. Which layer owns it, and which Validator can reject an invalid value?
5. Does another field already carry the same meaning?

Fields that are runtime observations do not belong in planning records; code-generation details do not belong in HarnessSpec; LLM decision rules do not belong in JSON Schema. Optional fields must represent a real unavailable/not-applicable state, not act as placeholders for unfinished design.

## Classification completeness claim

The vocabularies are **not claimed to be universally complete for all APIs or fuzzers**. They are operationally complete for the currently frozen PyTorch/FlashFuzz scope when every source record maps without an unclassified value and every required semantic element can be lowered or produces an explicit capability gap.

Before freezing a study version:

1. run a vocabulary-coverage audit over all included Report, Pattern, Knowledge, API Profile, and Helper Profile records;
2. record every `unknown`, extension, and unsupported capability;
3. add a vocabulary value only when at least one concrete source or tool state cannot be expressed by existing values;
4. version the schema/contract/rules together and preserve old records;
5. pilot the resulting pipeline and report unmapped or blocked cases.

This gives a falsifiable bounded-completeness argument: no unmapped cases in the declared corpus and environment. New backends, APIs, or failure modes require a new version rather than an unsupported claim of universal coverage.

## Golden-case validation

The `torch.matmul` / Issue #71774 golden case is the first end-to-end validation instance. It connects an exact Issue-derived Knowledge record to a static Strategy, generated C++, successful compilation, short fuzzing rounds, activation counters, and a determinism Oracle. The baseline uses the same API/runtime/Helper boundary without Knowledge. This case validates the purpose of the principal field groups while keeping effectiveness claims for the later frozen experiment.
