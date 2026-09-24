#include "fused_policy.h"
#include "fused_policy_kernel.h"
#include <c10/cuda/CUDAGuard.h>
#include <c10/cuda/CUDAException.h>
#include <c10/cuda/CUDAStream.h>
#include <limits>
#include <stdexcept>

namespace openttd_rl::development {
openttd_rl::training::MaskedPolicy fused_policy(const torch::Tensor &logits, const torch::Tensor &mask)
{
    if (!logits.defined() || !mask.defined() || !logits.is_cuda() || mask.device() != logits.device() ||
        logits.scalar_type() != torch::kFloat32 || mask.scalar_type() != torch::kBool ||
        logits.dim() != 2 || logits.size(1) != 41 || logits.size(0) < 1 || logits.size(0) > 65535 ||
        mask.sizes() != logits.sizes() || !logits.is_contiguous() || !mask.is_contiguous()) {
        throw std::invalid_argument("fused policy requires contiguous CUDA float32/bool [1..65535,41]");
    }
    if (logits.requires_grad()) throw std::invalid_argument("fused policy is inference-only; autograd is not supported");
    const c10::cuda::CUDAGuard guard(logits.device());
    auto logp = torch::empty_like(logits);
    auto probabilities = torch::empty_like(logits);
    auto entropy = torch::empty({logits.size(0)}, logits.options());
    auto status = torch::empty({logits.size(0)}, logits.options().dtype(torch::kInt32));
    launch_fused_policy(logits.data_ptr<float>(), mask.data_ptr<bool>(), logp.data_ptr<float>(),
                        probabilities.data_ptr<float>(), entropy.data_ptr<float>(), status.data_ptr<int>(),
                        static_cast<int>(logits.size(0)), c10::cuda::getCurrentCUDAStream().stream());
    C10_CUDA_KERNEL_LAUNCH_CHECK();
    // One synchronization validates every row, including finite masked-out
    // logits. Keep the trusted reference's fail-closed behavior.
    const auto host_status = status.cpu();
    const auto *errors = host_status.const_data_ptr<int>();
    for (std::int64_t row = 0; row < logits.size(0); ++row) {
        if (errors[row] == 2) throw std::invalid_argument("all-illegal action mask");
        if (errors[row] != 0) throw std::runtime_error("nonfinite fused policy input or result");
    }
    return {logp, probabilities, entropy};
}
}
