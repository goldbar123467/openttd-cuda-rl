#ifndef OPENTTD_RL_V2_M22_TRAINER_H
#define OPENTTD_RL_V2_M22_TRAINER_H

#include <cstdint>
#include <memory>
#include <random>
#include <string>

#include <torch/torch.h>

#include "openttd_rl/v2/generalist_policy.h"
#include "openttd_rl/v2/m22_ppo.h"

namespace openttd_rl::v2 {

inline constexpr std::int64_t kM22CompactFeatures = 32;
inline constexpr std::int64_t kM22SequenceLength = 8;

struct M22CompactBatch {
    torch::Tensor public_features;
    torch::Tensor program_mask;
    torch::Tensor hidden_state;
    torch::Tensor recurrent_reset;

    [[nodiscard]] std::int64_t size() const;
    void validate() const;
    [[nodiscard]] M22CompactBatch index_select(const torch::Tensor &indices) const;
};

[[nodiscard]] GeneralistPolicyInput m22_encode_compact(
    const M22CompactBatch &compact,
    const torch::Device &device);
[[nodiscard]] torch::Tensor m22_public_heuristic(const M22CompactBatch &compact);

struct M22ActionBatch {
    torch::Tensor actions;
    torch::Tensor log_probabilities;
    torch::Tensor values;
    torch::Tensor logits;
    torch::Tensor next_hidden;
};

struct M22RolloutBatch {
    M22CompactBatch compact;
    torch::Tensor actions;
    torch::Tensor old_log_probabilities;
    torch::Tensor old_values;
    torch::Tensor advantages;
    torch::Tensor returns;

    [[nodiscard]] std::int64_t size() const;
    void validate(const M22PpoConfig &config) const;
};

struct M22TrainerCounters {
    std::uint64_t completed_updates{};
    std::uint64_t accepted_transitions{};
    std::uint64_t completed_rollouts{};
};

struct M22UpdateMetrics {
    double policy_loss{};
    double value_loss{};
    double entropy{};
    double approximate_kl{};
    double clip_fraction{};
    double gradient_norm{};
    double explained_variance{};
    std::uint64_t update{};
    std::uint64_t transitions{};
};

struct M22RuntimeState {
    std::uint64_t run_seed{};
    GeneralistArchitecture architecture{GeneralistArchitecture::Monolithic};
    M22TrainerCounters counters;
    std::string action_rng;
    std::string minibatch_rng;
    std::string environment_rng;
    std::string curriculum_rng;
};

[[nodiscard]] std::uint64_t m22_stream_seed(std::uint64_t run_seed, std::uint64_t stream_index) noexcept;

class M22Trainer {
public:
    M22Trainer(
        M22PpoConfig config,
        std::uint64_t run_seed,
        GeneralistArchitecture architecture,
        torch::Device device);

    [[nodiscard]] M22ActionBatch act(const M22CompactBatch &compact, bool deterministic);
    [[nodiscard]] M22UpdateMetrics update(const M22RolloutBatch &rollout);
    [[nodiscard]] M22RuntimeState runtime_state() const;
    void restore_runtime_state(const M22RuntimeState &state);
    void to(const torch::Device &device);

    [[nodiscard]] GeneralistPolicy &model() noexcept { return model_; }
    [[nodiscard]] const GeneralistPolicy &model() const noexcept { return model_; }
    [[nodiscard]] torch::optim::Adam &optimizer() noexcept { return *optimizer_; }
    [[nodiscard]] const M22PpoConfig &config() const noexcept { return config_; }
    [[nodiscard]] const torch::Device &device() const noexcept { return device_; }
    [[nodiscard]] GeneralistArchitecture architecture() const noexcept { return architecture_; }
    [[nodiscard]] std::uint64_t run_seed() const noexcept { return run_seed_; }
    [[nodiscard]] M22TrainerCounters &counters() noexcept { return counters_; }
    [[nodiscard]] const M22TrainerCounters &counters() const noexcept { return counters_; }
    [[nodiscard]] std::mt19937_64 &environment_rng() noexcept { return environment_rng_; }
    [[nodiscard]] std::mt19937_64 &curriculum_rng() noexcept { return curriculum_rng_; }

private:
    M22PpoConfig config_;
    std::uint64_t run_seed_;
    GeneralistArchitecture architecture_;
    torch::Device device_;
    GeneralistPolicy model_;
    std::unique_ptr<torch::optim::Adam> optimizer_;
    std::mt19937_64 action_rng_;
    std::mt19937_64 minibatch_rng_;
    std::mt19937_64 environment_rng_;
    std::mt19937_64 curriculum_rng_;
    M22TrainerCounters counters_;
};

} // namespace openttd_rl::v2

#endif
