#include "fuzzer_utils.h"
#include <iostream>
#include <cstdint>
#include <vector>

using namespace fuzzer_utils;

// Helper to create a 2D tensor from fuzz input bytes
torch::Tensor create2DTensor(const uint8_t* data, size_t size, size_t& offset) {
    // Need at least 1 byte for dtype
    if (offset + 1 > size) {
        throw std::runtime_error("Not enough data for dtype");
    }

    // Parse dtype
    uint8_t dtype_selector = data[offset++];
    auto dtype = fuzzer_utils::parseDataType(dtype_selector);
    size_t dtypeSize = c10::elementSize(dtype);

    // Parse 2D shape (rank = 2)
    const uint8_t rank = 2;
    auto shape = fuzzer_utils::parseShape(data, offset, size, rank);

    // shape has exactly 2 elements (bounded 0..16 each), product <= 256, no overflow
    int64_t numElements = shape[0] * shape[1];

    // Parse raw bytes for tensor data
    auto inputBytes = fuzzer_utils::parseTensorData(data, offset, size, numElements, dtypeSize);

    auto options = torch::TensorOptions().dtype(dtype);

    if (numElements == 0) {
        // Empty tensor: no data needed
        return torch::empty(shape, options);
    } else {
        // inputBytes has size totalBytesNeeded (initialized with zeros),
        // so from_blob + clone is safe.
        return torch::from_blob(inputBytes.data(), shape, options).clone();
    }
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
    try {
        size_t offset = 0;

        // Create two 2D tensors from the input bytes
        auto t1 = create2DTensor(data, size, offset);
        auto t2 = create2DTensor(data, size, offset);

        // Main operation: matrix multiplication
        auto result = torch::mm(t1, t2);

        // Optionally test the out variant if shapes are compatible
        if (t1.size(1) == t2.size(0)) {
            auto out = torch::empty({t1.size(0), t2.size(1)}, t1.options());
            torch::mm_out(out, t1, t2);
        }
    } catch (const c10::Error& e) {
        // Expected PyTorch runtime error (shape mismatch, unsupported dtype, etc.)
        return 0;
    } catch (const std::exception& e) {
        // Other standard exceptions from parsing or invalid inputs
        return 0;
    }

    return 0;
}