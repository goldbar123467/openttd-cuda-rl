#ifndef OPENTTD_RL_TRAINING_LEARNING_H
#define OPENTTD_RL_TRAINING_LEARNING_H

#include <cstdint>

#include "openttd_rl/training/trainer.h"

namespace openttd_rl::training {

struct TinyBanditResult {
    double initial_greedy_accuracy{};
    double final_greedy_accuracy{};
    double final_mean_reward{};
    std::uint64_t updates{};
    std::uint64_t environment_steps{};
    UpdateMetrics final_update;
};

[[nodiscard]] TinyBanditResult run_tiny_masked_bandit(PpoTrainer &trainer, std::uint64_t additional_updates);
[[nodiscard]] double evaluate_tiny_masked_bandit(PpoTrainer &trainer, std::int64_t samples = 512);

} // namespace openttd_rl::training

#endif
