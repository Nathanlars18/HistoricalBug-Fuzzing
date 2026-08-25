#include "fuzzer_utils.h"
#include <torch/torch.h>
#include <iostream>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *Data, size_t Size)
{
    try
    {
        size_t offset = 0;

        // Parse two tensors from the fuzz input
        torch::Tensor t1 = fuzzer_utils::createTensor(Data, Size, offset);
        torch::Tensor t2 = fuzzer_utils::createTensor(Data, Size, offset);

        // Try matmul in both orders to cover a wider range of edge cases
        try
        {
            auto result1 = torch::matmul(t1, t2);
            (void)result1; // suppress unused warning
        }
        catch (const std::exception &e)
        {
            std::cout << "matmul(t1, t2) exception: " << e.what() << std::endl;
            // Shape/dtype mismatches and other expected errors are not crashes
        }

        try
        {
            auto result2 = torch::matmul(t2, t1);
            (void)result2;
        }
        catch (const std::exception &e)
        {
            std::cout << "matmul(t2, t1) exception: " << e.what() << std::endl;
        }
    }
    catch (const std::exception &e)
    {
        // Exception during parsing or any other unexpected error
        std::cout << "Exception caught: " << e.what() << std::endl;
        return 0; // do not treat as a crash
    }
    catch (...)
    {
        std::cout << "Unknown exception caught" << std::endl;
        return 0;
    }

    return 0; // execution succeeded (from fuzzer's perspective)
}