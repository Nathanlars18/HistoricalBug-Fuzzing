#include "fuzzer_utils.h" // General fuzzing utilities
#include <torch/torch.h>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <vector>
#include <iostream>
#include <exception>
#include <algorithm>

// Constants for target shape parsing
constexpr uint8_t MAX_TARGET_RANK = 4;
constexpr int64_t MAX_TARGET_DIM = 16; // Inclusive, dims will be in [0, 16]

// Parse a shape for torch.reshape from remaining fuzz data.
// Allows -1 dimensions (with ~20% probability) and dimensions in [0, MAX_TARGET_DIM].
// Updates offset to consume bytes read. If insufficient data, uses safe defaults.
static std::vector<int64_t> parseTargetShape(const uint8_t* data, size_t size, size_t& offset) {
    if (offset >= size) {
        // No data for shape, fallback to single -1 to test inference
        return {-1};
    }

    // Read rank (0..MAX_TARGET_RANK)
    uint8_t rank_byte = data[offset++];
    uint8_t rank = rank_byte % (MAX_TARGET_RANK + 1);

    std::vector<int64_t> shape;
    shape.reserve(rank);

    for (uint8_t i = 0; i < rank; ++i) {
        if (offset + sizeof(int64_t) <= size) {
            int64_t raw;
            std::memcpy(&raw, data + offset, sizeof(raw));
            offset += sizeof(raw);

            if (raw % 5 == 0) {
                // 20% chance to set dimension to -1
                shape.push_back(-1);
            } else {
                uint64_t abs_raw = static_cast<uint64_t>(std::abs(raw));
                int64_t dim = static_cast<int64_t>(abs_raw % (MAX_TARGET_DIM + 1));
                shape.push_back(dim);
            }
        } else {
            // Not enough data for this dimension, use safe default 1
            shape.push_back(1);
            // Prevent further reads by marking offset as exhausted
            offset = size;
        }
    }

    return shape;
}

// --- Fuzzer Entry Point ---
extern "C" int LLVMFuzzerTestOneInput(const uint8_t *Data, size_t Size)
{
    try
    {
        size_t offset = 0;

        // Create an input tensor from fuzz data
        torch::Tensor input = fuzzer_utils::createTensor(Data, Size, offset);

        // Parse a target shape from the remaining data
        std::vector<int64_t> target_shape = parseTargetShape(Data, Size, offset);

        // Call torch.reshape (the operator under test)
        torch::Tensor output = torch::reshape(input, target_shape);

        // --- Sanity checks to catch implementation bugs ---
        // reshape must preserve number of elements
        if (output.numel() != input.numel()) {
            std::cerr << "BUG: reshape changed number of elements: "
                      << input.numel() << " -> " << output.numel() << std::endl;
            std::abort();
        }

        // reshape must preserve dtype
        if (output.dtype() != input.dtype()) {
            std::cerr << "BUG: reshape changed dtype: "
                      << input.dtype() << " -> " << output.dtype() << std::endl;
            std::abort();
        }

        // reshape must preserve the underlying data values (same order after flattening)
        auto flat_input = input.flatten();
        auto flat_output = output.flatten();
        if (!torch::equal(flat_input, flat_output)) {
            std::cerr << "BUG: reshape corrupted tensor data" << std::endl;
            std::abort();
        }

        // If we reach here, everything is consistent
    }
    catch (const std::exception &e)
    {
        // Expected runtime exceptions from invalid fuzz inputs (shape mismatch, invalid -1 count, etc.)
        // are not treated as crashes.
        std::cout << "Exception caught: " << e.what() << std::endl; // do not change this, I need to know the exception.
        return 0; // keep the input, no crash
    }
    return 0; // normal execution
}