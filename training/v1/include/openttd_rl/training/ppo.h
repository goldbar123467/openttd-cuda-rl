#ifndef OPENTTD_RL_TRAINING_PPO_H
#define OPENTTD_RL_TRAINING_PPO_H

#include <cstdint>
#include <random>
#include <vector>

#include <torch/torch.h>

namespace openttd_rl::training {

struct PpoConfig {
    double gamma{0.99};
    double gae_lambda{0.95};
    double clip_epsilon{0.2};
    double value_coefficient{0.5};
    double entropy_coefficient{0.01};
    double learning_rate{0.0003};
    double adam_epsilon{0.00001};
    double max_gradient_norm{0.5};
    std::int64_t rollout_length{128};
    std::int64_t environment_count{1};
    std::int64_t minibatch_size{32};
    std::int64_t optimization_epochs{4};

    void validate() const;
};

struct GaeResult {
    torch::Tensor advantages;
    torch::Tensor returns;
};

struct MaskedPolicy {
    torch::Tensor log_probabilities;
    torch::Tensor probabilities;
    torch::Tensor entropy;
};

struct LossResult {
    torch::Tensor total;
    torch::Tensor policy;
    torch::Tensor value;
    torch::Tensor entropy;
    torch::Tensor approximate_kl;
    torch::Tensor clip_fraction;
};

struct RolloutBatch {
    torch::Tensor observations;
    torch::Tensor legal_masks;
    torch::Tensor actions;
    torch::Tensor old_log_probabilities;
    torch::Tensor old_values;
    torch::Tensor advantages;
    torch::Tensor returns;

    [[nodiscard]] std::int64_t size() const;
    void validate(std::int64_t expected_observation_features, std::int64_t expected_action_count) const;
};

[[nodiscard]] GaeResult compute_gae(
    const torch::Tensor &rewards,
    const torch::Tensor &values,
    const torch::Tensor &next_values,
    const torch::Tensor &bootstrap_mask,
    const torch::Tensor &continuation_mask,
    double gamma,
    double gae_lambda);

[[nodiscard]] torch::Tensor normalize_advantages(const torch::Tensor &advantages, double epsilon = 1e-8);
[[nodiscard]] MaskedPolicy masked_categorical(const torch::Tensor &logits, const torch::Tensor &legal_mask);
[[nodiscard]] LossResult ppo_loss(
    const torch::Tensor &new_log_probabilities,
    const torch::Tensor &old_log_probabilities,
    const torch::Tensor &advantages,
    const torch::Tensor &new_values,
    const torch::Tensor &returns,
    const torch::Tensor &entropy,
    const PpoConfig &config);

[[nodiscard]] std::vector<std::vector<std::int64_t>> minibatch_indices(
    std::int64_t sample_count,
    std::int64_t minibatch_size,
    std::mt19937_64 &generator);

[[nodiscard]] double explained_variance(const torch::Tensor &values, const torch::Tensor &returns);

} // namespace openttd_rl::training

#endif
