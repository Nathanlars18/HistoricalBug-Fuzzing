#include "fuzzer_utils.h"
#include <iostream>
#include <cstring>
#include <vector>
#include <torch/torch.h>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *Data, size_t Size)
{
    try
    {
        size_t offset = 0;

        // Create a tensor from the fuzz input
        torch::Tensor input = fuzzer_utils::createTensor(Data, Size, offset);

        // Parse the `dim` argument from remaining bytes
        int64_t dim;
        if (offset + sizeof(int64_t) <= Size)
        {
            std::memcpy(&dim, Data + offset, sizeof(int64_t));
            offset += sizeof(int64_t);
        }
        else if (offset < Size)
        {
            int8_t small_dim;
            std::memcpy(&small_dim, Data + offset, sizeof(int8_t));
            dim = static_cast<int64_t>(small_dim);
            offset += sizeof(int8_t);
        }
        else
        {
            dim = 0;
        }

        // Parse optional `dtype` argument for the output
        c10::optional<torch::ScalarType> dtype_opt = c10::nullopt;
        if (offset < Size)
        {
            uint8_t use_dtype = Data[offset++];
            if (use_dtype != 0 && offset < Size)
            {
                uint8_t dtype_selector = Data[offset++];
                static const std::vector<torch::ScalarType> float_dtypes = {
                    torch::kFloat,
                    torch::kDouble,
                    torch::kHalf,
                    torch::kBFloat16
                };
                dtype_opt = float_dtypes[dtype_selector % float_dtypes.size()];
            }
        }

        // Call the operator under test
        torch::Tensor output = torch::softmax(input, dim, dtype_opt);

        // Force materialization (eager execution already computed it, but just in case)
        (void)output;
    }
    catch (const c10::Error &e)
    {
        // PyTorch-specific exceptions (invalid dim, dtype, shape, etc.) are expected
        std::cout << "Exception caught: " << e.what() << std::endl;
        return 0;
    }
    catch (const std::exception &e)
    {
        std::cout << "Exception caught: " << e.what() << std::endl;
        return 0;
    }
    catch (...)
    {
        std::cout << "Unknown exception caught" << std::endl;
        return 0;
    }
    return 0;
}