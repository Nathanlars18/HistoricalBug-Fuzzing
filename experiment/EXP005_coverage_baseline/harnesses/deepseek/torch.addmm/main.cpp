#include "fuzzer_utils.h"
#include <cstdint>
#include <vector>
#include <iostream>
#include <exception>
#include <torch/torch.h>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *Data, size_t Size)
{
    try
    {
        size_t offset = 0;

        // Create three tensors: input, mat1, mat2
        torch::Tensor input = fuzzer_utils::createTensor(Data, Size, offset);
        torch::Tensor mat1  = fuzzer_utils::createTensor(Data, Size, offset);
        torch::Tensor mat2  = fuzzer_utils::createTensor(Data, Size, offset);

        // Parse beta and alpha scalars from remaining data if available
        double beta_val = 1.0, alpha_val = 1.0;
        const size_t needed = 2 * sizeof(double);
        if (offset + needed <= Size)
        {
            std::memcpy(&beta_val, Data + offset, sizeof(double));
            offset += sizeof(double);
            std::memcpy(&alpha_val, Data + offset, sizeof(double));
            offset += sizeof(double);
        }
        torch::Scalar beta(beta_val);
        torch::Scalar alpha(alpha_val);

        // --- 1. Call addmm without out argument ---
        torch::Tensor result = torch::addmm(input, mat1, mat2, beta, alpha);

        // --- 2. Optionally compute expected output shape and call addmm_out ---
        if (mat1.dim() >= 2 && mat2.dim() >= 2)
        {
            int64_t n = mat1.size(0);
            int64_t p = mat2.size(1);
            // Even if the inner dimension doesn't match, we try to create an out tensor
            // with the "expected" shape to see if the op throws or handles it.
            auto out_options = mat1.options();          // reuse dtype/device of mat1
            torch::Tensor out = torch::empty({n, p}, out_options);

            // Wrap in a try-catch to discard any shape/dtype incompatibility errors
            try
            {
                torch::addmm_out(out, input, mat1, mat2, beta, alpha);
            }
            catch (const std::exception &e)
            {
                // Expected for shape mismatches or invalid dtypes – ignore
            }
        }
    }
    catch (const std::exception &e)
    {
        std::cout << "Exception caught: " << e.what() << std::endl;
        return -1; // discard the input
    }
    return 0; // keep the input
}