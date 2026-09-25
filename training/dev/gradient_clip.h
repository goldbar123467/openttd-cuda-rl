#pragma once

#include <cmath>
#include <stdexcept>
#include <vector>
#include <torch/torch.h>

namespace openttd_rl::development {

// Versioned development alternative to LibTorch's parameter-dtype reduction.
// Only norm accumulation uses float64. Parameters, gradients, Adam state, the
// max-norm limit and LibTorch's 1e-6 clipping epsilon retain their original types
// and semantics. Keep the historical call available for exact reproductions.
inline double clip_grad_norm_fp64_(const std::vector<torch::Tensor> &parameters, double max_norm)
{
    if (!std::isfinite(max_norm) || max_norm <= 0.0)
        throw std::invalid_argument("max gradient norm must be finite and positive");
    torch::NoGradGuard guard;
    std::vector<torch::Tensor> gradients, norms;
    for (const auto &parameter : parameters) {
        const auto gradient = parameter.grad();
        if (!gradient.defined()) continue;
        if (gradient.is_sparse() || (gradient.scalar_type() != torch::kFloat32 && gradient.scalar_type() != torch::kFloat64))
            throw std::invalid_argument("fp64 gradient clipping requires dense float32/float64 gradients");
        if (!gradients.empty() && gradient.device() != gradients.front().device())
            throw std::invalid_argument("gradient clipping requires a single device");
        gradients.push_back(gradient);
        norms.push_back(gradient.to(torch::kFloat64).norm(2.0));
    }
    if (gradients.empty()) return 0.0;
    const auto total = torch::stack(norms).norm(2.0);
    const double value = total.item<double>();
    // Check before mutating any gradient, including when an individual tensor
    // contains NaN/Inf. CUDA requests perform this reduction on CUDA.
    if (!std::isfinite(value)) throw std::runtime_error("nonfinite fp64 gradient norm");
    const auto coefficient = torch::clamp(max_norm / (total + 1e-6), std::nullopt, 1.0);
    for (auto &gradient : gradients) gradient.mul_(coefficient);
    return value;
}

} // namespace openttd_rl::development
