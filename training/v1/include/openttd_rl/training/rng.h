#ifndef OPENTTD_RL_TRAINING_RNG_H
#define OPENTTD_RL_TRAINING_RNG_H

#include <array>
#include <cstdint>
#include <random>
#include <string>

#include <torch/torch.h>

namespace openttd_rl::training {

inline constexpr std::array<const char *, 4> kRngStreamNames = {
    "parameter_initialization",
    "action_sampling",
    "minibatch_shuffle",
    "environment_episode",
};

struct SeedLedger {
    std::uint64_t run_seed{};
    std::array<std::uint64_t, 4> stream_seeds{};
};

class RngStreams {
public:
    explicit RngStreams(std::uint64_t run_seed);

    [[nodiscard]] const SeedLedger &ledger() const noexcept { return ledger_; }
    [[nodiscard]] std::mt19937_64 &action_sampling() noexcept { return action_sampling_; }
    [[nodiscard]] std::mt19937_64 &minibatch_shuffle() noexcept { return minibatch_shuffle_; }
    [[nodiscard]] std::mt19937_64 &environment_episode() noexcept { return environment_episode_; }
    [[nodiscard]] std::uint64_t initialization_seed() const noexcept { return ledger_.stream_seeds[0]; }

    [[nodiscard]] std::array<std::string, 3> mutable_states() const;
    void restore_mutable_states(const std::array<std::string, 3> &states);

private:
    SeedLedger ledger_;
    std::mt19937_64 action_sampling_;
    std::mt19937_64 minibatch_shuffle_;
    std::mt19937_64 environment_episode_;
};

[[nodiscard]] std::uint64_t derive_stream_seed(std::uint64_t run_seed, const std::string &label);
[[nodiscard]] torch::Tensor sample_masked_actions(
    const torch::Tensor &log_probabilities,
    const torch::Tensor &legal_mask,
    std::mt19937_64 &generator);

} // namespace openttd_rl::training

#endif
