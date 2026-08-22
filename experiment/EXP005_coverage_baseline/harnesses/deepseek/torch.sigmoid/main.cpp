#include "fuzzer_utils.h"
#include <iostream>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *Data, size_t Size)
{
    try
    {
        size_t offset = 0;
        
        // Create the input tensor from the fuzzer data
        torch::Tensor input = fuzzer_utils::createTensor(Data, Size, offset);
        
        // Invoke torch.sigmoid on the input tensor
        torch::Tensor output = torch::sigmoid(input);
        
        // Force evaluation by converting to a simple scalar (optional, but helps detect issues with lazy ops)
        // For complex or half tensors, this may still be safe with CPU backend.
        // The explicit call to .item() will cause synchronization.
        // However, for non-scalar tensors, we just access the output; this is enough to trigger computation.
        // We'll simply use output.sizes() to ensure shape is accessible.
        auto sizes = output.sizes();
        (void)sizes; // suppress unused warning
        
        // Optionally test the out= variant with a pre-allocated tensor if enough data remains.
        // For robustness, only attempt if offset allows reading more metadata.
        // This is not required but can increase coverage.
        if (Size > offset + 2) // need at least dtype+rank bytes for a new tensor
        {
            try
            {
                torch::Tensor out = fuzzer_utils::createTensor(Data, Size, offset);
                // Note: shape/dtype mismatch between input and out will be caught by PyTorch.
                torch::sigmoid_out(out, input);
                // Check out sizes to force evaluation
                auto out_sizes = out.sizes();
                (void)out_sizes;
            }
            catch (...)
            {
                // The out= variant may throw if shapes are incompatible; that's fine.
                // We ignore to keep fuzzing.
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