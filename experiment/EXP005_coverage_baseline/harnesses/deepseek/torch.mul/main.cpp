#include "fuzzer_utils.h"
#include <iostream>
#include <cstring>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *Data, size_t Size)
{
    try {
        size_t offset = 0;

        // Create the first tensor from fuzz data
        torch::Tensor input = fuzzer_utils::createTensor(Data, Size, offset);

        // Decide whether to multiply by a scalar or by a second tensor
        bool use_scalar = false;
        if (offset < Size) {
            uint8_t flag = Data[offset++];
            use_scalar = (flag % 2 == 0);   // even -> scalar, odd -> tensor
        } else {
            use_scalar = true;  // default to scalar if no more data
        }

        // If scalar is chosen, parse a double from the remaining bytes (if any)
        double scalar_value = 1.0;
        if (use_scalar && offset + sizeof(double) <= Size) {
            std::memcpy(&scalar_value, Data + offset, sizeof(double));
            offset += sizeof(double);
        }

        if (use_scalar) {
            // Multiply with a scalar
            auto result = torch::mul(input, scalar_value);

            // Attempt the out= variant with a tensor created from remaining data
            // This may throw if shapes are incompatible; we simply ignore and move on.
            try {
                size_t out_offset = offset;
                torch::Tensor out = fuzzer_utils::createTensor(Data, Size, out_offset);
                torch::mul_out(out, input, scalar_value);
            } catch (...) {
                // out tensor might be incompatible – that's fine, just ignore
            }
        } else {
            // Create the second tensor from the remaining fuzz data
            torch::Tensor other = fuzzer_utils::createTensor(Data, Size, offset);

            // Multiply two tensors
            auto result = torch::mul(input, other);

            // Try the out= variant
            try {
                size_t out_offset = offset;
                torch::Tensor out = fuzzer_utils::createTensor(Data, Size, out_offset);
                torch::mul_out(out, input, other);
            } catch (...) {
                // ignore shape/dtype mismatches
            }
        }
    } catch (const std::exception &e) {
        std::cout << "Exception caught: " << e.what() << std::endl; // required output
        return -1; // discard the input
    }
    return 0; // keep the input
}