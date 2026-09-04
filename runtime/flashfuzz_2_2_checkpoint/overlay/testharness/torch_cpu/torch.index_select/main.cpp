#include "fuzzer_utils.h"
#include <torch/torch.h>
#include <cstdint>
#include <cstring>
#include <vector>
#include <algorithm>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *Data, size_t Size)
{
    try
    {
        size_t offset = 0;

        // ----- Create input tensor using provided utilities -----
        torch::Tensor input = fuzzer_utils::createTensor(Data, Size, offset);

        // ----- Parse dim (int64_t) from remaining bytes -----
        int64_t dim = 0;
        if (offset + sizeof(int64_t) <= Size)
        {
            std::memcpy(&dim, Data + offset, sizeof(int64_t));
        }
        offset += sizeof(int64_t); // advance regardless

        // ----- Build 1-D LongTensor index from remaining bytes -----
        const size_t max_index_count = 1024; // cap to avoid excessive allocations
        size_t remaining = (offset < Size) ? (Size - offset) : 0;
        size_t num_indices = std::min(remaining / sizeof(int64_t), max_index_count);

        torch::Tensor index;
        if (num_indices == 0)
        {
            // No complete int64 available -> empty index tensor (valid input)
            index = torch::empty({0}, torch::TensorOptions().dtype(torch::kLong));
        }
        else
        {
            std::vector<int64_t> indices(num_indices);
            std::memcpy(indices.data(), Data + offset, num_indices * sizeof(int64_t));
            // Create tensor from vector and clone to manage memory safely
            index = torch::from_blob(
                        indices.data(),
                        {static_cast<int64_t>(num_indices)},
                        torch::TensorOptions().dtype(torch::kLong))
                        .clone();
        }

        // ----- Call the target operator -----
        // Any invalid arguments (dtype mismatch, out-of-range dim, index out of bounds,
        // shape issues) will throw a c10::Error or std::exception, which we catch below.
        auto result = torch::index_select(input, dim, index);

        // The result is not used, but the operation has been fully executed.
        // To guarantee kernel execution even for lazy cases, explicitly materialize.
        (void)result.contiguous();
    }
    catch (const std::exception &e)
    {
        // Expected runtime errors from invalid fuzz inputs.
        // This includes c10::Error, std::runtime_error from tensor parsing, etc.
        // Returning 0 tells libFuzzer this is not a crash.
        return 0;
    }

    return 0;
}