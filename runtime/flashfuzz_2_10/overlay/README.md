# Execution Overlay

No FlashFuzz file is copied here yet.

After the PyTorch 2.10 fuzz-runtime smoke test, this directory may contain the
smallest necessary project-owned adaptations to the execution dispatcher,
Harness build template, or Helper implementation. Each addition must be tied
to an observed compatibility issue and must preserve `third_party/FlashFuzz`
as a clean pinned dependency.
