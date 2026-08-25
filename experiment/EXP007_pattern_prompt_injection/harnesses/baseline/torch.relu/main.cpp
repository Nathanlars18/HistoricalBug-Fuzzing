#include "fuzzer_utils.h"
#include <iostream>
#include <cstdint>
#include <cstddef>
#include <exception>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)
{
    try
    {
        size_t offset = 0;
        torch::Tensor input = fuzzer_utils::createTensor(data, size, offset);

        // Optional input-driven transformations to explore non-contiguous and
        // in-place paths as well as basic out-of-place relu.
        bool use_inplace = false;
        if (offset < size)
        {
            uint8_t flags = data[offset++];
            // If bit 0 set and tensor has at least 2 dimensions, make it
            // non-contiguous by transposing the last two dimensions.
            if ((flags & 0x01) && input.dim() >= 2)
            {
                int64_t ndim = input.dim();
                input = input.transpose(ndim - 1, ndim - 2);
            }
            use_inplace = (flags & 0x02) != 0;
        }

        if (use_inplace)
        {
            // In-place ReLU may fail for non-contiguous views or unsupported
            // dtypes. Such failures are expected for invalid/unsupported
            // fuzz inputs and are swallowed below.
            torch::relu_(input);
        }
        else
        {
            torch::Tensor output = torch::relu(input);
            // Ensure output is computed. Avoid unused-variable warnings.
            (void)output;
        }

        return 0;
    }
    catch (const std::exception &e)
    {
        std::cout << "Exception caught: " << e.what() << std::endl; // do not change this, I need to know the exception.
        return 0; // expected runtime error for invalid/unsupported PyTorch input
    }
    catch (...)
    {
        std::cout << "Unknown exception caught" << std::endl;
        return 0;
    }
}