#include <torch/cuda.h>
#include <torch/torch.h>
#include <torch/version.h>

#include <cuda_runtime_api.h>

#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {

void CheckCuda(cudaError_t result, const char *operation)
{
    if (result != cudaSuccess) {
        throw std::runtime_error(
            std::string(operation) + ": " + cudaGetErrorString(result));
    }
}

} // namespace

int main()
{
    try {
#if !defined(_GLIBCXX_USE_CXX11_ABI) || _GLIBCXX_USE_CXX11_ABI != 1
        throw std::runtime_error("LibTorch probe requires _GLIBCXX_USE_CXX11_ABI=1");
#endif
        if (std::string(TORCH_VERSION) != "2.13.0") {
            throw std::runtime_error("unexpected LibTorch version: " + std::string(TORCH_VERSION));
        }
        if (!torch::cuda::is_available() || torch::cuda::device_count() < 1) {
            throw std::runtime_error("LibTorch CUDA backend/device is unavailable");
        }

        cudaDeviceProp properties{};
        CheckCuda(cudaGetDeviceProperties(&properties, 0), "cudaGetDeviceProperties");
        if (properties.major != 12 || properties.minor != 0) {
            throw std::runtime_error("expected compute capability 12.0");
        }

        torch::manual_seed(1234);
        const auto cpu_options = torch::TensorOptions().dtype(torch::kFloat32);
        const auto left = torch::arange(1, 17, cpu_options).reshape({4, 4});
        const auto right = torch::arange(17, 33, cpu_options).reshape({4, 4});
        const auto cpu_result = torch::matmul(left, right);
        const auto cuda_result = torch::matmul(left.cuda(), right.cuda()).cpu();
        const double max_error = (cpu_result - cuda_result).abs().max().item<double>();
        if (!std::isfinite(max_error) || max_error > 1.0e-5) {
            throw std::runtime_error("CPU/CUDA matmul parity failed");
        }

        auto parameter = torch::ones(
            {32, 32},
            torch::TensorOptions().dtype(torch::kFloat32).device(torch::kCUDA).requires_grad(true));
        const auto loss = (parameter * parameter).mean();
        loss.backward();
        const auto gradient = parameter.grad();
        if (!gradient.defined() || !torch::isfinite(gradient).all().item<bool>()) {
            throw std::runtime_error("CUDA autograd produced an invalid gradient");
        }
        CheckCuda(cudaDeviceSynchronize(), "cudaDeviceSynchronize");

        std::cout << "LIBTORCH_PROBE=PASS"
                  << " version=" << TORCH_VERSION
                  << " cuda_devices=" << static_cast<int>(torch::cuda::device_count())
                  << " gpu=\"" << properties.name << "\""
                  << " compute_capability=" << properties.major << '.' << properties.minor
                  << " cxx11_abi=" << _GLIBCXX_USE_CXX11_ABI
                  << " max_error=" << max_error
                  << '\n';
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "LIBTORCH_PROBE=FAIL " << error.what() << '\n';
        return 1;
    }
}
