# PyTorch 2.10 CPU runtime for source coverage collection.
# This image uses a separate build directory because coverage instrumentation
# must not be mixed with the plain libFuzzer runtime build.
ARG BASE_IMAGE=historicalbug/flashfuzz:torch2.10-base
FROM ${BASE_IMAGE}

ARG PYTORCH_BUILD_JOBS=2

WORKDIR /root/pytorch

RUN python3 -m pip install --no-cache-dir --break-system-packages -r requirements.txt \
    && cmake -S . -B build-cov \
       -DUSE_CPP_CODE_COVERAGE=1 \
       -DCMAKE_C_COMPILER=clang \
       -DCMAKE_CXX_COMPILER=clang++ \
       -DCMAKE_BUILD_TYPE=Debug \
       -DDEBUG=1 \
       -DCMAKE_CXX_FLAGS="-O0 -g -fsanitize=fuzzer-no-link -fno-omit-frame-pointer -D_GLIBCXX_USE_CXX11_ABI=1 -Wno-error -fprofile-instr-generate -fcoverage-mapping" \
       -DCMAKE_C_FLAGS="-O0 -g -fsanitize=fuzzer-no-link -fno-omit-frame-pointer -Wno-error -fprofile-instr-generate -fcoverage-mapping" \
       -DUSE_CUDA=0 \
       -DUSE_NCCL=0 \
       -DUSE_KINETO=0 \
       -DUSE_DISTRIBUTED=0 \
       -DBUILD_CAFFE2=0 \
       -DBUILD_CAFFE2_OPS=0 \
       -DUSE_TENSORPIPE=0 \
       -DUSE_QNNPACK=0 \
       -DUSE_MIOPEN=0 \
       -DUSE_XNNPACK=0 \
       -DUSE_MKLDNN=0 \
       -DUSE_FBGEMM=0 \
       -DUSE_NNPACK=0 \
       -DBUILD_TEST=0 \
       -G Ninja \
    && cmake --build build-cov --parallel "${PYTORCH_BUILD_JOBS}"

WORKDIR /workspace

CMD ["bash"]
