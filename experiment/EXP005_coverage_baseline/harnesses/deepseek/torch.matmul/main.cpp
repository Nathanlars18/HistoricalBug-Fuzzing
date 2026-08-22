#include "fuzzer_utils.h"
#include <iostream>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *Data, size_t Size)
{
    try
    {
        size_t offset = 0;
        // Create first tensor from fuzz data
        auto input = fuzzer_utils::createTensor(Data, Size, offset);
        // Create second tensor from remaining data
        auto other = fuzzer_utils::createTensor(Data, Size, offset);

        // Perform matrix multiplication – covers all permitted dimensionality and dtype combos,
        // including empty tensors, incompatible shapes, and broadcasting edge cases.
        auto result = torch::matmul(input, other);

        // (Optional) minimal introspection – kept for coverage feedback, not validation.
        // std::cout << "result shape: " << result.sizes() << " dtype: " << result.dtype() << std::endl;
    }
    catch (const std::exception &e)
    {
        // Print exception to confirm error paths are exercised (as requested)
        std::cout << "Exception caught: " << e.what() << std::endl;
        return -1; // discard input that caused exception
    }
    return 0; // keep input
}