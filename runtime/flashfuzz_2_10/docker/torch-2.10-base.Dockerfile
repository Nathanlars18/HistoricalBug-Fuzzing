# Project-owned PyTorch 2.10 source/build foundation.
# Build context: repository root. This file intentionally copies no project files.
FROM ubuntu:24.04

ARG LLVM_MAJOR=20
ARG PYTORCH_TAG=v2.10.0
ARG PYTORCH_COMMIT=449b1768410104d3ed79d3bcfe4ba1d65c7f22c0

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    cmake \
    curl \
    git \
    gnupg \
    liblapack-dev \
    libopenblas-dev \
    lsb-release \
    ninja-build \
    patch \
    python3 \
    python3-dev \
    python3-pip \
    python3-venv \
    software-properties-common \
    wget \
    && rm -rf /var/lib/apt/lists/*

RUN wget -q https://apt.llvm.org/llvm.sh -O /tmp/llvm.sh \
    && chmod +x /tmp/llvm.sh \
    && /tmp/llvm.sh "${LLVM_MAJOR}" \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
       "clang-${LLVM_MAJOR}" \
       "lld-${LLVM_MAJOR}" \
       "libclang-${LLVM_MAJOR}-dev" \
       "llvm-${LLVM_MAJOR}" \
       "llvm-${LLVM_MAJOR}-dev" \
    && update-alternatives --install /usr/bin/clang clang "/usr/bin/clang-${LLVM_MAJOR}" 100 \
    && update-alternatives --install /usr/bin/clang++ clang++ "/usr/bin/clang++-${LLVM_MAJOR}" 100 \
    && update-alternatives --install /usr/bin/ld ld "/usr/bin/lld-${LLVM_MAJOR}" 100 \
    && rm -rf /var/lib/apt/lists/* /tmp/llvm.sh

WORKDIR /root

RUN git clone --recursive --branch "${PYTORCH_TAG}" \
      https://github.com/pytorch/pytorch.git /root/pytorch \
    && test "$(git -C /root/pytorch rev-parse HEAD)" = "${PYTORCH_COMMIT}"

CMD ["bash"]
