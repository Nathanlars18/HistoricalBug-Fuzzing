# torch.add Harness Manual Fix Record

Date:
2026-08-24

Reason:
LLM generated harness failed to compile with PyTorch 2.2 C++ API.

Original issues:

1.
std::complex<double> cannot convert to torch::Scalar

Original:
std::complex<double>

Fixed:
c10::complex<double>


2.
Tensor.dtype() returned caffe2::TypeMeta,
but torch::promote_types requires at::ScalarType.

Original:
input.dtype()

Fixed:
input.scalar_type()


Impact:
Only C++ API compatibility fixes.
No fuzzing logic, input generation strategy,
or oracle logic changed.
