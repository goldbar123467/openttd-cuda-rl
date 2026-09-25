#include "gradient_clip.h"
#include <algorithm>
#include <iostream>
#include <limits>
#include <torch/cuda.h>

namespace dev = openttd_rl::development;

void require(bool condition, const char *message)
{
    if (!condition) throw std::runtime_error(message);
}

torch::Tensor parameter(const torch::Tensor &gradient)
{
    auto value = torch::zeros_like(gradient);
    value.mutable_grad() = gradient.clone();
    return value;
}

void oracle(const torch::Tensor &first, const torch::Tensor &second, double limit)
{
    auto a = parameter(first), b = parameter(second);
    // Independent scalar long-double sum over the actual stored inputs.
    long double squares = 0.0;
    for (const auto &input : {first, second}) {
        const auto cpu = input.to(torch::kCPU, torch::kFloat64).contiguous().flatten();
        const auto *values = cpu.data_ptr<double>();
        for (int64_t i = 0; i < cpu.numel(); ++i) squares += static_cast<long double>(values[i]) * values[i];
    }
    const double expected = static_cast<double>(std::sqrt(squares));
    const double actual = dev::clip_grad_norm_fp64_({a, b}, limit);
    require(std::abs(actual - expected) <= 1e-11 * std::max(1.0, expected), "norm differs from scalar oracle");
    const double coefficient = std::min(1.0, limit / (expected + 1e-6));
    for (const auto &pair : {std::make_pair(first, a), std::make_pair(second, b)}) {
        const auto expected_gradient = (pair.first.to(torch::kCPU, torch::kFloat64) * coefficient).to(pair.first.scalar_type());
        const auto actual_gradient = pair.second.grad().cpu();
        const double tolerance = pair.first.scalar_type() == torch::kFloat64 ? 1e-12 : 2e-7;
        require(torch::allclose(actual_gradient, expected_gradient, tolerance, tolerance), "clipped gradients differ from oracle");
        require(torch::count_nonzero(pair.second).item<int64_t>() == 0, "clipping changed parameters");
    }
}

int main(int argc, char **argv)
{
    try {
        if (argc != 2) throw std::invalid_argument("expected cpu or cuda:0");
        const torch::Device device(argv[1]);
        if (device.is_cuda() && !torch::cuda::is_available()) throw std::runtime_error("CUDA unavailable; no fallback");
        torch::set_num_threads(1);
        for (auto dtype : {torch::kFloat32, torch::kFloat64}) {
            const auto options = torch::TensorOptions().device(device).dtype(dtype);
            oracle(torch::tensor({3.0, -4.0}, options), torch::tensor({12.0}, options), 0.5);
            oracle(torch::tensor({0.01, -0.02}, options), torch::tensor({0.03}, options), 0.5);
            oracle(torch::zeros({32}, options), torch::zeros({1}, options), 0.5);
            oracle(torch::full({1000000}, 0.1, options), torch::tensor({1e-10, -1e-10}, options), 0.5);
            oracle(torch::tensor({1e30, -1e30}, options), torch::tensor({1.0}, options), 0.5);
            auto good = parameter(torch::ones({2}, options));
            for (double invalid : {std::numeric_limits<double>::quiet_NaN(), std::numeric_limits<double>::infinity()}) {
                auto bad = parameter(torch::tensor({invalid}, options));
                bool refused = false;
                try { dev::clip_grad_norm_fp64_({good, bad}, 0.5); } catch (const std::runtime_error &) { refused = true; }
                require(refused && torch::equal(good.grad(), torch::ones_like(good)), "nonfinite norm mutated gradients or was accepted");
            }
            require(dev::clip_grad_norm_fp64_({torch::zeros({1}, options)}, 0.5) == 0.0, "undefined gradients were not skipped");
        }
        require(dev::clip_grad_norm_fp64_({}, 0.5) == 0.0, "empty gradient set is not zero");
        for (double invalid : {0.0, -1.0, std::numeric_limits<double>::quiet_NaN(), std::numeric_limits<double>::infinity()}) {
            bool refused = false;
            try { dev::clip_grad_norm_fp64_({}, invalid); } catch (const std::invalid_argument &) { refused = true; }
            require(refused, "invalid clipping limit accepted");
        }
        std::cout << "{\"status\":\"passed\",\"device\":\"" << device << "\",\"oracle\":\"scalar-long-double\"}\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
