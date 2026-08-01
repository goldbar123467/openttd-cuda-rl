#include <cuda_runtime.h>

#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

void CheckCuda(cudaError_t result, const char *operation)
{
    if (result != cudaSuccess) {
        throw std::runtime_error(
            std::string(operation) + ": " + cudaGetErrorString(result));
    }
}

__global__ void Add(const float *left, const float *right, float *result, int count)
{
    const int index = blockIdx.x * blockDim.x + threadIdx.x;
    if (index < count) result[index] = left[index] + right[index];
}

} // namespace

int main()
{
    try {
        constexpr int count = 1024;
        constexpr std::size_t bytes = count * sizeof(float);
        std::vector<float> left(count);
        std::vector<float> right(count);
        std::vector<float> result(count);
        for (int index = 0; index < count; ++index) {
            left[index] = static_cast<float>(index);
            right[index] = static_cast<float>(count - index);
        }

        float *device_left = nullptr;
        float *device_right = nullptr;
        float *device_result = nullptr;
        CheckCuda(cudaMalloc(&device_left, bytes), "cudaMalloc(left)");
        CheckCuda(cudaMalloc(&device_right, bytes), "cudaMalloc(right)");
        CheckCuda(cudaMalloc(&device_result, bytes), "cudaMalloc(result)");
        CheckCuda(cudaMemcpy(device_left, left.data(), bytes, cudaMemcpyHostToDevice), "copy(left)");
        CheckCuda(cudaMemcpy(device_right, right.data(), bytes, cudaMemcpyHostToDevice), "copy(right)");
        Add<<<4, 256>>>(device_left, device_right, device_result, count);
        CheckCuda(cudaGetLastError(), "Add kernel launch");
        CheckCuda(cudaMemcpy(result.data(), device_result, bytes, cudaMemcpyDeviceToHost), "copy(result)");
        CheckCuda(cudaFree(device_result), "cudaFree(result)");
        CheckCuda(cudaFree(device_right), "cudaFree(right)");
        CheckCuda(cudaFree(device_left), "cudaFree(left)");

        for (float value : result) {
            if (std::abs(value - static_cast<float>(count)) > 1.0e-6F) {
                throw std::runtime_error("CUDA vector result mismatch");
            }
        }
        cudaDeviceProp properties{};
        CheckCuda(cudaGetDeviceProperties(&properties, 0), "cudaGetDeviceProperties");
        if (properties.major != 12 || properties.minor != 0) {
            throw std::runtime_error("expected compute capability 12.0");
        }
        std::cout << "CUDA_PROBE=PASS"
                  << " runtime=" << CUDART_VERSION
                  << " gpu=\"" << properties.name << "\""
                  << " compute_capability=" << properties.major << '.' << properties.minor
                  << " count=" << count
                  << '\n';
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "CUDA_PROBE=FAIL " << error.what() << '\n';
        return 1;
    }
}
