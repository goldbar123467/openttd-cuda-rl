#include "openttd_rl/training/ppo.h"
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <torch/cuda.h>
#ifdef RL_DEV_FUSED_POLICY
#include "fused_policy.h"
#endif

int main(int argc, char **argv)
{
    using namespace openttd_rl::training;
    try {
        if (argc != 2) throw std::invalid_argument("usage: rl_policy_benchmark cpu|cuda:0");
        const std::string name(argv[1]);
        if (name != "cpu" && name != "cuda:0") throw std::invalid_argument("unsupported device");
        const torch::Device device(name);
        if (device.is_cuda() && !torch::cuda::is_available()) throw std::runtime_error("CUDA unavailable; no fallback");
        torch::set_num_threads(1);
        torch::NoGradGuard guard;
        std::cout << std::setprecision(12) << "{\"device\":\"" << name << "\",\"results\":[";
        bool first = true;
        for (const std::int64_t rows : {4, 64, 512}) {
            const auto sequence = torch::arange(rows * 41, torch::kFloat32).reshape({rows, 41});
            const auto cpu_logits = torch::sin(sequence * .17F) * 8.F;
            const auto cpu_mask = sequence.to(torch::kInt64).remainder(3).ne(0);
            const auto expected = masked_categorical(cpu_logits, cpu_mask);
            const auto logits = cpu_logits.to(device);
            const auto mask = cpu_mask.to(device);
            auto actual = masked_categorical(logits, mask);
            if (!torch::allclose(actual.probabilities.cpu(), expected.probabilities, 1e-5, 1e-6) ||
                !torch::allclose(actual.log_probabilities.cpu(), expected.log_probabilities, 1e-5, 1e-5) ||
                !torch::allclose(actual.entropy.cpu(), expected.entropy, 1e-5, 1e-5)) {
                throw std::runtime_error("CPU reference mismatch");
            }
            for (int i = 0; i < 10; ++i) actual = masked_categorical(logits, mask);
            if (device.is_cuda()) torch::cuda::synchronize();
            const auto start = std::chrono::steady_clock::now();
            constexpr int iterations = 100;
            for (int i = 0; i < iterations; ++i) actual = masked_categorical(logits, mask);
            if (device.is_cuda()) torch::cuda::synchronize();
            const auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - start).count();
            if (!first) std::cout << ',';
            first = false;
            std::cout << "{\"batch\":" << rows << ",\"iterations\":" << iterations
                      << ",\"reference_wall_us_per_call\":" << static_cast<double>(ns) / (iterations * 1000.)
                      << ",\"cpu_comparison\":\"passed\"";
#ifdef RL_DEV_FUSED_POLICY
            if (device.is_cuda()) {
                actual = openttd_rl::development::fused_policy(logits, mask);
                if (!torch::allclose(actual.probabilities.cpu(), expected.probabilities, 1e-5, 1e-6) ||
                    !torch::allclose(actual.log_probabilities.cpu(), expected.log_probabilities, 1e-5, 1e-5) ||
                    !torch::allclose(actual.entropy.cpu(), expected.entropy, 1e-5, 1e-5)) {
                    throw std::runtime_error("fused CPU reference mismatch");
                }
                for (int i = 0; i < 10; ++i) actual = openttd_rl::development::fused_policy(logits, mask);
                torch::cuda::synchronize();
                const auto fused_start = std::chrono::steady_clock::now();
                for (int i = 0; i < iterations; ++i) actual = openttd_rl::development::fused_policy(logits, mask);
                torch::cuda::synchronize();
                const auto fused_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
                    std::chrono::steady_clock::now() - fused_start).count();
                std::cout << ",\"fused_wall_us_per_call\":" << static_cast<double>(fused_ns) / (iterations * 1000.);
            }
#endif
            std::cout << '}';
        }
        std::cout << "]}\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
