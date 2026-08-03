#ifndef OPENTTD_RL_V2_M22_PPO_H
#define OPENTTD_RL_V2_M22_PPO_H

#include <cstdint>
#include <random>
#include <vector>

#include <torch/torch.h>

namespace openttd_rl::v2 {

struct M22PpoConfig {
    double gamma{0.99};
    double gae_lambda{0.95};
    double policy_clip{0.2};
    double value_clip{0.2};
    double value_coefficient{0.5};
    double entropy_coefficient{0.01};
    double learning_rate{0.0003};
    double adam_epsilon{1.0e-8};
    double maximum_gradient_norm{0.5};
    std::int64_t rollout_steps{16};
    std::int64_t parallel_environments{8};
    std::int64_t minibatch_size{64};
    std::int64_t epochs{4};

    void validate() const;
};

struct M22GaeResult {
    torch::Tensor advantages;
    torch::Tensor returns;
};

struct M22MaskedPolicy {
    torch::Tensor log_probabilities;
    torch::Tensor probabilities;
    torch::Tensor entropy;
};

struct M22LossResult {
    torch::Tensor total;
    torch::Tensor policy;
    torch::Tensor value;
    torch::Tensor entropy;
    torch::Tensor approximate_kl;
    torch::Tensor clip_fraction;
};

[[nodiscard]] M22GaeResult m22_compute_gae(
    const torch::Tensor &rewards,
    const torch::Tensor &values,
    const torch::Tensor &next_values,
    const torch::Tensor &bootstrap_mask,
    const torch::Tensor &continuation_mask,
    double gamma,
    double gae_lambda);
[[nodiscard]] torch::Tensor m22_normalize_advantages(const torch::Tensor &advantages, double epsilon = 1.0e-8);
[[nodiscard]] M22MaskedPolicy m22_masked_categorical(const torch::Tensor &logits, const torch::Tensor &legal_mask);
[[nodiscard]] M22LossResult m22_ppo_loss(
    const torch::Tensor &new_log_probabilities,
    const torch::Tensor &old_log_probabilities,
    const torch::Tensor &advantages,
    const torch::Tensor &new_values,
    const torch::Tensor &old_values,
    const torch::Tensor &returns,
    const torch::Tensor &entropy,
    const M22PpoConfig &config);
[[nodiscard]] std::vector<std::vector<std::int64_t>> m22_minibatch_indices(
    std::int64_t sample_count,
    std::int64_t minibatch_size,
    std::mt19937_64 &generator);

} // namespace openttd_rl::v2

#endif
