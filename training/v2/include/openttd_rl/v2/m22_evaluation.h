#ifndef OPENTTD_RL_V2_M22_EVALUATION_H
#define OPENTTD_RL_V2_M22_EVALUATION_H

#include <cstdint>
#include <filesystem>
#include <string>

#include <torch/torch.h>

#include "openttd_rl/v2/generalist_policy.h"

namespace openttd_rl::v2 {

inline constexpr std::int64_t kM22EvaluationFeatureCount = 32;

struct M22FinalPublicState {
    std::string task;
    std::string transport_mode;
    std::string climate;
    std::uint32_t map_width{};
    std::uint32_t map_height{};
    std::string cargo;
    std::string opponent;
    std::string native_probe;
    std::string source_gate;
};

struct M22EvaluationBatch {
    torch::Tensor public_features;
    torch::Tensor program_mask;
    torch::Tensor hidden_state;
    torch::Tensor recurrent_reset;
};

struct M22EvaluationPolicy {
    std::string checkpoint_id;
    GeneralistArchitecture architecture{GeneralistArchitecture::Monolithic};
    std::uint64_t run_seed{};
    GeneralistPolicy model;
};

[[nodiscard]] M22EvaluationBatch encode_m22_final_public_state(const M22FinalPublicState &state);
[[nodiscard]] GeneralistPolicyInput m22_evaluation_input(
    const M22EvaluationBatch &batch,
    const torch::Device &device);
[[nodiscard]] M22EvaluationPolicy load_m22_evaluation_policy(
    const std::filesystem::path &checkpoint_path,
    const torch::Device &policy_device);

} // namespace openttd_rl::v2

#endif
