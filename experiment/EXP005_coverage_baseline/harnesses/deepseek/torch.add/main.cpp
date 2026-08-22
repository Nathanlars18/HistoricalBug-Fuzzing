#include "fuzzer_utils.h"
#include <cstring>
#include <iostream>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *Data, size_t Size) {
    try {
        size_t offset = 0;

        // Parse the first tensor (input)
        torch::Tensor input = fuzzer_utils::createTensor(Data, Size, offset);

        // Parse the second tensor (other)
        torch::Tensor other = fuzzer_utils::createTensor(Data, Size, offset);

        // Parse alpha (optional, defaults to 1.0)
        double alpha = 1.0;
        if (offset + sizeof(double) <= Size) {
            std::memcpy(&alpha, Data + offset, sizeof(double));
            offset += sizeof(double);
        }

        // Call torch::add
        torch::Tensor result = torch::add(input, other, alpha);

        // Touch the result to avoid dead‑code elimination
        if (result.numel() > 0) {
            // Access one element – could throw for bool/complex, but we let it propagate
            volatile auto val = result.flatten()[0].item<float>();
            (void)val;
        }

    } catch (const std::exception &e) {
        // Log the exception (as per skeleton) and discard this input
        std::cout << "Exception caught: " << e.what() << std::endl;
        return -1;
    } catch (...) {
        return -1;
    }

    return 0; // keep the input
}