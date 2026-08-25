#include "fuzzer_utils.h"
#include <torch/torch.h>
#include <iostream>
#include <cstring>
#include <cstdint>
#include <vector>
#include <complex>
#include <limits>

namespace {

// Helper to parse a scalar from fuzz data
at::Scalar parseScalar(const uint8_t* data, size_t& offset, size_t size) {
    if (offset >= size) {
        return at::Scalar(1.0);
    }
    uint8_t type_selector = data[offset++];
    switch (type_selector % 4) {
        case 0: { // double
            double val = 0.0;
            if (offset + sizeof(double) <= size) {
                std::memcpy(&val, data + offset, sizeof(double));
                offset += sizeof(double);
            }
            return at::Scalar(val);
        }
        case 1: { // int64_t
            int64_t val = 0;
            if (offset + sizeof(int64_t) <= size) {
                std::memcpy(&val, data + offset, sizeof(int64_t));
                offset += sizeof(int64_t);
            }
            return at::Scalar(val);
        }
        case 2: { // bool
            bool val = false;
            if (offset + sizeof(uint8_t) <= size) {
                val = data[offset] != 0;
                offset += 1;
            }
            return at::Scalar(val);
        }
        case 3: { // complex<double>
            double re = 0.0, im = 0.0;
            if (offset + 2 * sizeof(double) <= size) {
                std::memcpy(&re, data + offset, sizeof(double));
                offset += sizeof(double);
                std::memcpy(&im, data + offset, sizeof(double));
                offset += sizeof(double);
            }
            return at::Scalar(c10::complex<double>(re, im));
        }
    }
    return at::Scalar(1.0);
}

} // anonymous namespace

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* Data, size_t Size) {
    // Minimum data: 1 byte for mode, and at least 2 bytes for tensor metadata
    if (Size < 3) {
        return 0;
    }

    size_t offset = 0;
    try {
        // Read operation mode (0: tensor*tensor, 1: tensor*scalar, 2: scalar*tensor)
        uint8_t mode = Data[offset++] % 3;

        // Inputs
        torch::Tensor t1, t2;
        at::Scalar scalar;

        // Create tensor(s) and/or scalar based on mode
        if (mode == 0) {
            t1 = fuzzer_utils::createTensor(Data, Size, offset);
            t2 = fuzzer_utils::createTensor(Data, Size, offset);
        } else if (mode == 1) {
            t1 = fuzzer_utils::createTensor(Data, Size, offset);
            scalar = parseScalar(Data, offset, Size);
        } else { // mode == 2
            scalar = parseScalar(Data, offset, Size);
            t1 = fuzzer_utils::createTensor(Data, Size, offset);
        }

        // Perform the main multiplication (without out)
        if (mode == 0) {
            auto result = at::mul(t1, t2);
            (void)result; // suppress unused warning
        } else if (mode == 1) {
            auto result = at::mul(t1, scalar);
            (void)result;
        } else {
            auto result = at::mul(scalar, t1);
            (void)result;
        }

        // Optionally test the out= variant using remaining fuzz data
        if (offset < Size) {
            uint8_t use_out_flag = Data[offset++];
            bool use_out = (use_out_flag % 2) != 0;
            if (use_out && offset + 2 <= Size) {
                // Try to create an out tensor; if this fails (e.g., not enough data),
                // we simply skip the out variant.
                try {
                    torch::Tensor out = fuzzer_utils::createTensor(Data, Size, offset);
                    // Call the out variant inside a nested try to catch shape/dtype errors
                    try {
                        if (mode == 0) {
                            at::mul_out(out, t1, t2);
                        } else if (mode == 1) {
                            at::mul_out(out, t1, scalar);
                        } else {
                            at::mul_out(out, scalar, t1);
                        }
                    } catch (const c10::Error&) {
                        // Expected: shape/dtype mismatch, invalid argument, etc.
                    } catch (const std::exception&) {
                        // Expected runtime error
                    }
                } catch (const std::exception&) {
                    // createTensor failed due to insufficient data; ignore
                }
            }
        }
    } catch (const c10::Error& e) {
        // Expected PyTorch error (shape mismatch, type promotion, etc.)
        std::cout << "Exception caught: " << e.what() << std::endl;
        return 0;
    } catch (const std::exception& e) {
        // Expected generic runtime error from parsing or API
        std::cout << "Exception caught: " << e.what() << std::endl;
        return 0;
    }

    return 0;
}