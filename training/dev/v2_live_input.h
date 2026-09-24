#pragma once

#include <filesystem>
#include "openttd_rl/v2/scalable_policy.h"
#include "openttd_rl/training/ppo.h"

namespace openttd_rl::development {
inline constexpr const char *kLiveV2TensorSchema = "openttd-rl-development-v2-public-tensors-1";

// The existing native M15 binary layouts, with seed features explicitly zero.
openttd_rl::v2::ScalablePolicyInput read_live_v2_input(
    const std::filesystem::path &observation, const std::filesystem::path &candidates);
openttd_rl::v2::ScalablePolicyInput live_v2_to(
    const openttd_rl::v2::ScalablePolicyInput &input, const torch::Device &device);
openttd_rl::training::MaskedPolicy live_v2_distribution(
    const openttd_rl::v2::ScalablePolicyOutput &output,
    const openttd_rl::v2::ScalablePolicyInput &input);
} // namespace openttd_rl::development
