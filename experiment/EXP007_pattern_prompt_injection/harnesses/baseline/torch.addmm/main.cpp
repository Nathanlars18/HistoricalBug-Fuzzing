#include "fuzzer_utils.h"
#include <torch/torch.h>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <exception>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *Data, size_t Size)
{
    try
    {
        size_t offset = 0;

        // Create three tensors: input, mat1, mat2
        torch::Tensor input = fuzzer_utils::createTensor(Data, Size, offset);
        torch::Tensor mat1 = fuzzer_utils::createTensor(Data, Size, offset);
        torch::Tensor mat2 = fuzzer_utils::createTensor(Data, Size, offset);

        // Parse beta and alpha as double if enough bytes remain, otherwise default to 1.0
        double beta = 1.0;
        double alpha = 1.0;

        if (offset + sizeof(double) <= Size)
        {
            double beta_raw;
            std::memcpy(&beta_raw, Data + offset, sizeof(double));
            beta = beta_raw;
            offset += sizeof(double);
        }

        if (offset + sizeof(double) <= Size)
        {
            double alpha_raw;
            std::memcpy(&alpha_raw, Data + offset, sizeof(double));
            alpha = alpha_raw;
            offset += sizeof(double);
        }

        // Call torch::addmm with the parsed tensors and scalars.
        // This may throw exceptions if shapes/dtypes are invalid, but those
        // are expected for fuzzing and should not be treated as crashes.
        auto result = torch::addmm(input, mat1, mat2, beta, alpha);

        // Force the result to be materialized (eager execution already computes it,
        // but touching the data ensures any lazy errors surface here).
        // We use .defined() to avoid unused variable warnings.
        (void)result.defined();

        // Optionally, we could also exercise the default beta/alpha overload
        // by calling torch::addmm(input, mat1, mat2), but that would require
        // duplicating the call and potentially causing extra exceptions.
        // For simplicity, we only use the explicit scalars.
    }
    catch (const c10::Error &e)
    {
        // Expected PyTorch runtime errors (shape mismatch, dtype mismatch, etc.)
        // These are not bugs and should be ignored.
        // Uncomment the following line if detailed logging is needed:
        // std::cout << "PyTorch error: " << e.what() << std::endl;
        return 0;
    }
    catch (const std::exception &e)
    {
        // Other exceptions (e.g., from fuzzer_utils due to insufficient input)
        // are also expected and should be ignored.
        // std::cout << "Exception caught: " << e.what() << std::endl;
        return 0;
    }
    catch (...)
    {
        // Catch any other unexpected exceptions to keep the fuzzer running.
        return 0;
    }

    return 0;
}