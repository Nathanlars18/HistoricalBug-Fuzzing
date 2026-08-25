#include "fuzzer_utils.h"
#include <torch/torch.h>
#include <cstdint>
#include <iostream>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *Data, size_t Size) {
    try {
        size_t offset = 0;

        // Parse first tensor from the fuzz input
        auto tensor1 = fuzzer_utils::createTensor(Data, Size, offset);

        // Parse second tensor from the remaining input
        auto tensor2 = fuzzer_utils::createTensor(Data, Size, offset);

        // Invoke torch.matmul. PyTorch will validate shapes, dtypes, and
        // other constraints internally. If the operation fails due to an
        // invalid input (e.g., incompatible shapes, unsupported dtype), an
        // exception is thrown and caught below.
        auto result = torch::matmul(tensor1, tensor2);

        // The result is intentionally unused; the computation has side effects
        // and is not optimized away by the compiler.
        (void)result;
    } catch (const std::exception &e) {
        // Expected runtime errors caused by random fuzz inputs (shape mismatch,
        // dtype mismatch, invalid arguments) are not considered crashes.
        // Returning 0 tells libFuzzer to continue with the next input.
        return 0;
    } catch (...) {
        // Catch any other exceptions (e.g., c10::Error not derived from std::exception)
        // to prevent the fuzzer from crashing on expected invalid inputs.
        return 0;
    }
    return 0;
}