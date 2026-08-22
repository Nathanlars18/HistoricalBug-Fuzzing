#include "fuzzer_utils.h"
#include <iostream>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *Data, size_t Size)
{
    try
    {
        size_t offset = 0;
        // Build a tensor with varied properties from fuzz data
        torch::Tensor input = fuzzer_utils::createTensor(Data, Size, offset);
        // Invoke the operator under test
        torch::Tensor output = torch::relu(input);
        // Small check to prevent the compiler from optimizing away the call
        if (!output.defined())
        {
            std::cerr << "torch.relu returned an undefined tensor" << std::endl;
        }
    }
    catch (const std::exception &e)
    {
        std::cout << "Exception caught: " << e.what() << std::endl; // do not change this
        return -1; // discard the input
    }
    return 0; // keep the input
}