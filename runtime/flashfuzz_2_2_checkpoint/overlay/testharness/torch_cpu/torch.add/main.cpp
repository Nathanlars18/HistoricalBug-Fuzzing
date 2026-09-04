#include <torch/torch.h>
#include "fuzzer_utils.h"
#include <cstdint>
#include <cstring>
#include <iostream>
#include <complex>
#include <vector>

namespace {

// Helper to read a double from fuzz data; if insufficient bytes, return default_val.
double readDouble(const uint8_t* data, size_t size, size_t& offset, double default_val) {
    if (offset + sizeof(double) <= size) {
        double val;
        std::memcpy(&val, data + offset, sizeof(val));
        offset += sizeof(val);
        return val;
    }
    return default_val;
}

// Helper to read an int64 from fuzz data; if insufficient, return default_val.
int64_t readInt64(const uint8_t* data, size_t size, size_t& offset, int64_t default_val) {
    if (offset + sizeof(int64_t) <= size) {
        int64_t val;
        std::memcpy(&val, data + offset, sizeof(val));
        offset += sizeof(val);
        return val;
    }
    return default_val;
}

// Helper to read a complex<double> from fuzz data; if insufficient, return default_val.
c10::complex<double> readComplex(
    const uint8_t* data,
    size_t size,
    size_t& offset,
    c10::complex<double> default_val
)
{
    if (offset + 2 * sizeof(double) <= size) {

        double real, imag;

        std::memcpy(&real, data + offset, sizeof(real));
        offset += sizeof(real);

        std::memcpy(&imag, data + offset, sizeof(imag));
        offset += sizeof(imag);

        return c10::complex<double>(real, imag);
    }

    return default_val;
}
} // anonymous namespace

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *Data, size_t Size) {
    try {
        size_t offset = 0;

        // --------------------- Parse first tensor (input) ---------------------
        auto input = fuzzer_utils::createTensor(Data, Size, offset);

        // -------------------- Determine other operand type --------------------
        bool has_tensor_other = false;
        torch::Tensor other_tensor;
        torch::Scalar scalar_other(0.0);

        if (offset < Size) {
            uint8_t mode = Data[offset++];
            if (mode % 2 == 0) {
                // other is a tensor
                other_tensor = fuzzer_utils::createTensor(Data, Size, offset);
                has_tensor_other = true;
            } else {
                // other is a scalar
                has_tensor_other = false;
                if (offset < Size) {
                    uint8_t scalar_kind = Data[offset++];
                    switch (scalar_kind % 3) {
                        case 0: { // double
                            double val = readDouble(Data, Size, offset, 0.0);
                            scalar_other = torch::Scalar(val);
                            break;
                        }
                        case 1: { // int64
                            int64_t val = readInt64(Data, Size, offset, 0);
                            scalar_other = torch::Scalar(val);
                            break;
                        }
                        case 2: { // complex<double>
                            auto val = readComplex(Data, Size, offset, {0.0, 0.0});
                            scalar_other = torch::Scalar(val);
                            break;
                        }
                    }
                } else {
                    scalar_other = torch::Scalar(0.0);
                }
            }
        } else {
            // No data left for other; use scalar zero
            has_tensor_other = false;
            scalar_other = torch::Scalar(0.0);
        }

        // ----------------------------- Parse alpha -----------------------------
        double alpha = readDouble(Data, Size, offset, 1.0);

        // ----------------------------- Parse out flag --------------------------
        bool use_out = false;
        if (offset < Size) {
            uint8_t out_flag = Data[offset++];
            use_out = (out_flag % 2 == 1);
        }

        // ------------------- Attempt operation with out if desired ------------
        if (use_out) {
            try {
                std::vector<int64_t> out_shape;
                torch::ScalarType out_dtype;

                if (has_tensor_other) {
                    // Compute broadcast shape and promoted dtype
                    out_shape = at::infer_size(input.sizes(), other_tensor.sizes());
                    out_dtype = torch::promote_types(
                        input.scalar_type(),
                        other_tensor.scalar_type()
                    );
                } else {
                    // Scalar other: result shape is same as input
                    out_shape = input.sizes().vec();
                    out_dtype = torch::promote_types(input.scalar_type(),scalar_other.type());
                }

                auto out = torch::empty(out_shape, torch::TensorOptions().dtype(out_dtype));

                if (has_tensor_other) {
                    torch::add_out(out, input, other_tensor, alpha);
                } else {
                    torch::add_out(out, input, scalar_other, alpha);
                }
                // Success with out
                return 0;
            } catch (const std::exception& e) {
                // If out computation or add_out failed (e.g., shape/dtype mismatch,
                // unsupported promotion), fallback to regular add without out.
                // We deliberately ignore the exception here to keep fuzzing.
            }
        }

        // ------------------------------ Regular add ----------------------------
        if (has_tensor_other) {
            auto result = torch::add(input, other_tensor, alpha);
        } else {
            auto result = torch::add(input, scalar_other, alpha);
        }

        return 0;
    }
    catch (const c10::Error& e) {
        // Expected runtime error: shape mismatch, dtype mismatch, invalid args, etc.
        // Print only for debugging; return 0 to keep the input in the corpus.
        std::cout << "Exception caught (c10::Error): " << e.what() << std::endl;
        return 0;
    }
    catch (const std::exception& e) {
        // Expected std::exception from parse helpers or PyTorch API.
        std::cout << "Exception caught: " << e.what() << std::endl;
        return 0;
    }
    catch (...) {
        // Catch any other exceptions to avoid crashing. Sanitizer traps are not exceptions.
        return 0;
    }
}
