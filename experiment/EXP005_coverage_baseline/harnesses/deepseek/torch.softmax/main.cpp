#include "fuzzer_utils.h"
#include <torch/torch.h>
#include <cstdint>
#include <iostream>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *Data, size_t Size)
{
    try
    {
        size_t offset = 0;

        // Build a tensor from the fuzzer input
        auto input = fuzzer_utils::createTensor(Data, Size, offset);

        // If there are enough bytes left, read a candidate dim value; otherwise default to 0
        int64_t dim_raw = 0;
        if (offset + sizeof(int64_t) <= Size) {
            dim_raw = *reinterpret_cast<const int64_t*>(Data + offset);
            offset += sizeof(int64_t);
        }

        // Map dim_raw onto a softmax dimension that is sometimes out‑of‑bounds
        int64_t dim = 0;
        int64_t ndim = static_cast<int64_t>(input.ndimension());
        if (ndim == 0) {
            // Scalar tensor: only dim=0 is conceivable; the API will decide its validity
            dim = 0;
        } else {
            // Make dim range from -1 (last dim) up to ndim (one past the last valid dim),
            // allowing the fuzzer to provoke out‐of‐bounds errors.
            dim = dim_raw % (ndim + 2) - 1; // [-1, ndim]
        }

        // Call the operation under test
        auto output = torch::softmax(input, dim);
        (void)output; // silence unused‑variable warning
    }
    catch (const std::exception &e)
    {
        // Output the exception message exactly as required by the harness
        std::cout << "Exception caught: " << e.what() << std::endl;
        return -1; // discard this input
    }
    return 0; // retain this input
}