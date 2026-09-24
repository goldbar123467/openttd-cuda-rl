#include "v2_live_input.h"
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <torch/cuda.h>

int main(int argc, char **argv)
{
    try {
        if (argc != 2) throw std::invalid_argument("expected cpu or cuda:0");
        torch::Device device(argv[1]);
        if (device.is_cuda() && !torch::cuda::is_available()) throw std::runtime_error("CUDA unavailable");
        using namespace openttd_rl::v2;
        auto floats = torch::TensorOptions().device(device).dtype(torch::kFloat32).requires_grad(true);
        auto integers = torch::TensorOptions().device(device).dtype(torch::kInt64);
        auto booleans = torch::TensorOptions().device(device).dtype(torch::kBool);
        ScalablePolicyInput input;
        input.candidate_family = torch::zeros({2, kCandidateCapacity}, integers);
        input.candidate_mask = torch::zeros({2, kCandidateCapacity}, booleans);
        input.family_mask = torch::zeros({2, kFamilyCount}, booleans);
        input.candidate_mask.index_put_({0, 0}, true);
        input.family_mask.index_put_({0, 0}, true);
        input.family_mask.index_put_({0, 2}, true);
        for (int row = 1; row <= 3; ++row) {
            input.candidate_mask.index_put_({0, row}, true);
            input.candidate_family.index_put_({0, row}, 2);
        }
        input.candidate_mask.index_put_({1, 10}, true);
        input.candidate_family.index_put_({1, 10}, 5);
        input.family_mask.index_put_({1, 5}, true);
        ScalablePolicyOutput output{torch::zeros({2, kFamilyCount}, floats),
            torch::zeros({2, kCandidateCapacity}, floats), {}, {}};
        const auto policy = openttd_rl::development::live_v2_distribution(output, input);
        const auto p = policy.probabilities.cpu();
        auto near = [](double a, double b) { if (std::abs(a - b) > 1.0e-6) throw std::runtime_error("hierarchical probability/entropy differs"); };
        near(p[0][0].item<double>(), 0.5);
        for (int row = 1; row <= 3; ++row) near(p[0][row].item<double>(), 1.0 / 6.0);
        near(p[1][10].item<double>(), 1.0);
        near(policy.entropy[0].item<double>(), std::log(2.0) + 0.5 * std::log(3.0));
        near(policy.entropy[1].item<double>(), 0.0);
        if (p.masked_select(~input.candidate_mask.cpu()).abs().sum().item<double>() != 0.0)
            throw std::runtime_error("illegal candidate received probability");
        auto loss = -policy.log_probabilities[0][1] - policy.log_probabilities[1][10] - 0.01 * policy.entropy.sum();
        loss.backward();
        for (const auto &tensor : {output.family_logits, output.candidate_logits}) {
            if (!tensor.grad().defined() || !torch::isfinite(tensor.grad()).all().item<bool>())
                throw std::runtime_error("absent families produced nonfinite gradients");
        }
        if (output.candidate_logits.grad().masked_select(~input.candidate_mask).abs().sum().item<float>() != 0.0F)
            throw std::runtime_error("illegal candidate received gradient");
        std::cout << "Hierarchical family mass, one legal action, illegal masks and absent-family gradients passed on " << device << '\n';
        return 0;
    } catch (const std::exception &error) { std::cerr << error.what() << '\n'; return 1; }
}
