#include "fused_policy.h"
#include <c10/cuda/CUDAGuard.h>
#include <c10/cuda/CUDAStream.h>
#include <algorithm>
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <torch/cuda.h>

namespace {
void check(bool value, const char *message) { if (!value) throw std::runtime_error(message); }
template<typename Function> void rejects(Function &&function)
{
    bool rejected = false;
    try { function(); } catch (const std::exception &) { rejected = true; }
    check(rejected, "invalid fused-policy input accepted");
}
template<typename Function> void rejects_with(Function &&function, const std::string &expected)
{
    try { function(); } catch (const std::exception &error) {
        if (error.what() == expected) return;
        throw std::runtime_error("wrong diagnostic: " + std::string(error.what()));
    }
    throw std::runtime_error("invalid fused-policy input accepted");
}
}
int main()
{
    using openttd_rl::development::fused_policy;
    using openttd_rl::training::masked_categorical;
    try {
        check(torch::cuda::is_available(), "CUDA unavailable; no CPU fallback");
        torch::set_num_threads(1);
        const torch::Device device(torch::kCUDA, 0);
        const c10::cuda::CUDAStreamGuard stream(c10::cuda::getStreamFromPool(false, 0));
        double maximum_logp = 0, maximum_probability = 0, maximum_entropy = 0;
        std::int64_t cases = 0;
        for (const std::int64_t rows : {1, 4, 64, 513}) {
            for (const float scale : {0.F, 1.F, 20.F, 1000.F}) {
                const auto sequence = torch::arange(rows * 41, torch::kFloat32).reshape({rows, 41});
                const auto cpu_logits = torch::sin(sequence * .17F) * scale;
                for (int pattern = 0; pattern < 3; ++pattern) {
                    auto cpu_mask = torch::ones({rows, 41}, torch::kBool);
                    if (pattern == 1) cpu_mask = sequence.to(torch::kInt64).remainder(3).ne(0);
                    if (pattern == 2) { cpu_mask.fill_(false); cpu_mask.select(1, 40).fill_(true); }
                    const auto expected = masked_categorical(cpu_logits, cpu_mask);
                    const auto actual = fused_policy(cpu_logits.to(device), cpu_mask.to(device));
                    const auto lp = actual.log_probabilities.cpu();
                    const auto p = actual.probabilities.cpu();
                    const auto entropy = actual.entropy.cpu();
                    check(torch::allclose(lp, expected.log_probabilities, 1e-5, 1e-5), "log-probability tolerance");
                    check(torch::allclose(p, expected.probabilities, 1e-5, 1e-6), "probability tolerance");
                    check(torch::allclose(entropy, expected.entropy, 1e-5, 1e-5), "entropy tolerance");
                    check(torch::equal(lp.argmax(1), expected.log_probabilities.argmax(1)), "greedy action differs");
                    check(p.masked_select(cpu_mask.logical_not()).eq(0).all().item<bool>(), "illegal probability nonzero");
                    check(torch::isneginf(lp.masked_select(cpu_mask.logical_not())).all().item<bool>(), "illegal log-probability finite");
                    maximum_logp = std::max(maximum_logp, (lp - expected.log_probabilities).masked_select(cpu_mask).abs().max().item<double>());
                    maximum_probability = std::max(maximum_probability, (p - expected.probabilities).abs().max().item<double>());
                    maximum_entropy = std::max(maximum_entropy, (entropy - expected.entropy).abs().max().item<double>());
                    cases += rows;
                }
            }
        }
        auto logits = torch::zeros({4, 41}, torch::TensorOptions().device(device));
        auto mask = torch::ones({4, 41}, logits.options().dtype(torch::kBool));
        rejects([&] { (void)fused_policy(logits, torch::zeros_like(mask)); });
        rejects([&] { (void)fused_policy(logits.cpu(), mask.cpu()); });
        rejects([&] { (void)fused_policy(logits.to(torch::kFloat64), mask); });
        rejects([&] { (void)fused_policy(logits, mask.to(torch::kInt32)); });
        rejects([&] { (void)fused_policy(torch::zeros({41, 4}, logits.options()).transpose(0, 1), mask); });
        rejects([&] { (void)fused_policy(logits, torch::ones({41, 4}, mask.options()).transpose(0, 1)); });
        logits.set_requires_grad(true);
        rejects([&] { (void)fused_policy(logits, mask); });
        logits.set_requires_grad(false);
        for (const float invalid : {std::numeric_limits<float>::quiet_NaN(), std::numeric_limits<float>::infinity(),
                                    -std::numeric_limits<float>::infinity()}) {
            for (const bool legal : {false, true}) {
                logits[2][17] = invalid;
                mask[2][17] = legal; // Reject illegal nonfinite logits as the oracle does.
                rejects_with([&] { (void)fused_policy(logits, mask); }, "nonfinite fused policy input at row 2");
                rejects([&] { (void)masked_categorical(logits.cpu(), mask.cpu()); });
                logits[2][17] = 0;
            }
        }
        mask[1].fill_(false);
        logits[2][17] = std::numeric_limits<float>::quiet_NaN();
        rejects_with([&] { (void)fused_policy(logits, mask); }, "all-illegal action mask at row 1");
        mask.fill_(true);
        logits.zero_();
        logits[0][0] = 1e38F;
        logits[0][1] = -1e38F;
        auto extreme = fused_policy(logits, mask);
        auto extreme_reference = masked_categorical(logits.cpu(), mask.cpu());
        check(torch::allclose(extreme.log_probabilities.cpu(), extreme_reference.log_probabilities, 1e-5, 1e-5), "extreme finite logp");
        check(torch::allclose(extreme.entropy.cpu(), extreme_reference.entropy, 1e-5, 1e-5), "extreme finite entropy");
        // Finite inputs can still overflow their subtraction; distinguish this
        // result failure from input rejection (and retain oracle fail-closed behavior).
        logits[0][0] = std::numeric_limits<float>::max();
        logits[0][1] = -std::numeric_limits<float>::max();
        rejects_with([&] { (void)fused_policy(logits, mask); }, "nonfinite fused policy entropy at row 0");
        rejects([&] { (void)masked_categorical(logits.cpu(), mask.cpu()); });
        const auto boundary_logits = torch::zeros({65535, 41}, logits.options());
        const auto boundary_mask = torch::ones({65535, 41}, mask.options());
        const auto boundary = fused_policy(boundary_logits, boundary_mask);
        const auto boundary_reference = masked_categorical(boundary_logits.cpu(), boundary_mask.cpu());
        check(torch::allclose(boundary.log_probabilities.cpu(), boundary_reference.log_probabilities, 1e-5, 1e-5), "boundary logp");
        check(torch::allclose(boundary.entropy.cpu(), boundary_reference.entropy, 1e-5, 1e-5), "boundary entropy");
        rejects([&] { (void)fused_policy(torch::zeros({65536, 41}, logits.options()), torch::ones({65536, 41}, mask.options())); });
        std::cout << "FUSED_POLICY=PASS rows=" << cases << " max_logp=" << maximum_logp
                  << " max_probability=" << maximum_probability << " max_entropy=" << maximum_entropy
                  << " nondefault_stream=true\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "FUSED_POLICY=FAIL " << error.what() << '\n';
        return 1;
    }
}
