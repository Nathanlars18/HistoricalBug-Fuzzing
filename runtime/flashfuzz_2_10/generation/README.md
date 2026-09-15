# Python API-Metadata Environment

This directory documents the separately pinned Python environment used to
extract API Profile facts. It is not the C++ fuzz or coverage runtime.

The image is defined by
`../docker/torch-2.10-api-metadata.Dockerfile`. It reuses the pinned PyTorch
source base, installs the official PyTorch 2.10 CPU package, and rejects the
build unless `torch.__version__` and `torch.version.git_version` match the
configured target.

The environment supplies runtime docstrings and signatures. Versioned PyTorch
source remains the authority for operator schemas and C++/ATen bindings.
Generated Harnesses are still compiled and executed only in the dedicated fuzz
and coverage images.
