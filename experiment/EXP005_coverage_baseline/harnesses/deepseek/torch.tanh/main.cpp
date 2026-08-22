#include "fuzzer_utils.h"
#include <iostream>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    try {
        size_t offset = 0;

        // Create input tensor from fuzz data
        torch::Tensor input_tensor;
        try {
            input_tensor = fuzzer_utils::createTensor(data, size, offset);
        } catch (const std::exception &e) {
            // If we can't create a tensor, skip this input
            std::cerr << "Failed to create input tensor: " << e.what() << std::endl;
            return 0;  // skip without crashing
        }

        // 1. Basic tanh
        try {
            auto result = torch::tanh(input_tensor);
            (void)result;
        } catch (const std::exception &e) {
            std::cerr << "Exception in tanh: " << e.what() << std::endl;
        }

        // 2. In-place tanh_ on a clone
        try {
            auto cloned = input_tensor.clone();
            torch::tanh_(cloned);
        } catch (const std::exception &e) {
            std::cerr << "Exception in tanh_: " << e.what() << std::endl;
        }

        // 3. Out variant: try to create an output tensor from remaining data
        if (size - offset >= 2) {
            try {
                torch::Tensor out_tensor = fuzzer_utils::createTensor(data, size, offset);
                torch::tanh_out(out_tensor, input_tensor);
            } catch (const std::exception &e) {
                std::cerr << "Exception in tanh_out: " << e.what() << std::endl;
            }
        }

    } catch (const std::exception &e) {
        std::cout << "Exception caught: " << e.what() << std::endl;
        return -1; // discard the input
    }
    return 0; // keep the input
}