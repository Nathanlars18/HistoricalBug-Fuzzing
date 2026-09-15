# Target-version Python metadata environment for API Profile extraction.
ARG BASE_IMAGE=historicalbug/flashfuzz:torch2.10-base
FROM ${BASE_IMAGE}

ARG PYTORCH_VERSION=2.10.0
ARG PYTORCH_COMMIT=449b1768410104d3ed79d3bcfe4ba1d65c7f22c0

RUN python3 -m pip install --no-cache-dir --break-system-packages \
      "torch==${PYTORCH_VERSION}" \
      --index-url https://download.pytorch.org/whl/cpu \
    && python3 -c "import torch; assert torch.__version__.split('+', 1)[0] == '${PYTORCH_VERSION}'; assert torch.version.git_version == '${PYTORCH_COMMIT}'"

WORKDIR /workspace
CMD ["python3"]
