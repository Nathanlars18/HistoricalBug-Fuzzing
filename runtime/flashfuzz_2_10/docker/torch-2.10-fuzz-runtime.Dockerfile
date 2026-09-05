# Instrumented PyTorch 2.10 CPU runtime for libFuzzer Harnesses.
# This image deliberately does not copy FlashFuzz scripts or Harnesses so that
# changing a Harness does not invalidate the costly framework build layer.
ARG BASE_IMAGE=historicalbug/flashfuzz:torch2.10-base
FROM ${BASE_IMAGE}

ARG PYTORCH_BUILD_JOBS=2

WORKDIR /root/pytorch

RUN python3 -m pip install --no-cache-dir --break-system-packages -r requirements.txt \
    && cmake -S . -B build-fuzz \
       -DUSE_CPP_CODE_COVERAGE=1 \
       -DCMAKE_C_COMPILER=clang \
       -DCMAKE_CXX_COMPILER=clang++ \
       -DCMAKE_BUILD_TYPE=Debug \
       -DDEBUG=1 \
       -DCMAKE_CXX_FLAGS="-fsanitize=fuzzer-no-link -fno-omit-frame-pointer -D_GLIBCXX_USE_CXX11_ABI=1 -Wno-error" \
       -DCMAKE_C_FLAGS="-fsanitize=fuzzer-no-link -fno-omit-frame-pointer -Wno-error" \
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
    && cmake --build build-fuzz --parallel "${PYTORCH_BUILD_JOBS}"

WORKDIR /workspace

CMD ["bash"]
