#include "fuzzer_utils.h"
#include <torch/torch.h>
#include <cstdint>
#include <vector>
#include <iostream>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *Data, size_t Size)
{
    try
    {
        size_t offset = 0;

        // Need at least two bytes: one for number of tensors, one for dim.
        if (Size < 2)
        {
            return 0;
        }

        // Parse number of tensors (0..8). This includes the edge case of an empty list.
        uint8_t num_tensors_raw = Data[offset++];
        size_t num_tensors = static_cast<size_t>(num_tensors_raw % 9);

        // Parse dim and map it to a reasonable range [-4, 4]. This covers
        // both valid and invalid dimensions for tensors with rank up to 4.
        uint8_t dim_raw = Data[offset++];
        int64_t dim = static_cast<int64_t>(dim_raw % 9) - 4;

        std::vector<torch::Tensor> tensors;
        tensors.reserve(num_tensors);

        for (size_t i = 0; i < num_tensors; ++i)
        {
            // createTensor parses dtype, rank, shape, and data from the fuzz input.
            // It may throw if the input is exhausted or contains invalid metadata.
            // Such exceptions are expected and handled in the outer catch block.
            tensors.push_back(fuzzer_utils::createTensor(Data, Size, offset));
        }

        // Perform the torch.cat operation. Any shape mismatch, dtype mismatch,
        // invalid dim, or other runtime errors are caught below and treated
        // as expected (non-crashing) behavior.
        auto result = torch::cat(tensors, dim);

        // Prevent compiler from optimizing away the result (optional).
        (void)result;
    }
    catch (const std::exception &e)
    {
        // Log the exception message for debugging, but do not treat it as a crash.
        std::cout << "Exception caught: " << e.what() << std::endl;
        return 0; // Expected runtime exception from invalid fuzz input; not a bug.
    }
    return 0; // Input processed successfully.
}