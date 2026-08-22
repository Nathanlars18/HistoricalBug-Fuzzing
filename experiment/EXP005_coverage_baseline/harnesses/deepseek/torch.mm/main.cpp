#include "fuzzer_utils.h"
#include <iostream>
#include <stdexcept>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *Data, size_t Size) {
    try {
        size_t offset = 0;

        // First matrix
        torch::Tensor input = fuzzer_utils::createTensor(Data, Size, offset);

        // Second matrix (use remaining bytes; may throw if not enough data)
        torch::Tensor mat2 = fuzzer_utils::createTensor(Data, Size, offset);

        // Perform matrix multiplication – let the API validate shapes, dtypes, etc.
        torch::Tensor out = torch::mm(input, mat2);

        // No explicit output check – the fuzzer will detect crashes/assertions.
    } catch (const std::exception &e) {
        std::cout << "Exception caught: " << e.what() << std::endl; // do not change this, I need to know the exception.
        return -1; // discard input that caused a (non-fatal) exception
    } catch (...) {
        std::cout << "Unknown exception caught" << std::endl;
        return -1;
    }
    return 0; // keep the input as interesting
}