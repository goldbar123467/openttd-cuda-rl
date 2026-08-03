#ifndef OPENTTD_RL_V2_M23_DEPLOYMENT_H
#define OPENTTD_RL_V2_M23_DEPLOYMENT_H

#include <torch/torch.h>

#include "openttd_rl/v2/generalist_policy.h"

namespace openttd_rl::v2 {

inline constexpr std::int64_t kM23PublicFeatureCount = 32;
inline constexpr std::int64_t kM23MaximumBatch = 32;

struct M23DeploymentBatch {
    torch::Tensor public_features;
    torch::Tensor program_mask;
    torch::Tensor hidden_state;
    torch::Tensor recurrent_reset;
};

void validate_m23_deployment_batch(const M23DeploymentBatch &batch);

[[nodiscard]] GeneralistPolicyInput m23_deployment_input(
    const M23DeploymentBatch &batch,
    const torch::Device &device);

} // namespace openttd_rl::v2

#endif
