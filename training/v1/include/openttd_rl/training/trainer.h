#ifndef OPENTTD_RL_TRAINING_TRAINER_H
#define OPENTTD_RL_TRAINING_TRAINER_H

#include <cstdint>
#include <memory>

#include <torch/torch.h>

#include "openttd_rl/training/model.h"
#include "openttd_rl/training/ppo.h"
#include "openttd_rl/training/rng.h"

namespace openttd_rl::training {

struct TrainerCounters {
    std::uint64_t completed_updates{};
    std::uint64_t environment_steps{};
    std::uint64_t simulation_ticks{};
    std::uint64_t completed_episodes{};
    std::uint64_t accepted_samples{};
};

struct ActionBatch {
    torch::Tensor actions;
    torch::Tensor log_probabilities;
    torch::Tensor values;
    torch::Tensor logits;
};

struct UpdateMetrics {
    double policy_loss{};
    double value_loss{};
    double entropy{};
    double approximate_kl{};
    double clip_fraction{};
    double gradient_norm{};
    double explained_variance{};
    double learning_rate{};
    std::uint64_t update{};
    std::uint64_t samples{};
};

class PpoTrainer {
public:
    PpoTrainer(PpoConfig config, std::uint64_t run_seed);

    [[nodiscard]] ActionBatch act(
        const torch::Tensor &observations,
        const torch::Tensor &legal_masks,
        bool deterministic);
    [[nodiscard]] UpdateMetrics update(const RolloutBatch &rollout);

    [[nodiscard]] ActorCritic &model() noexcept { return model_; }
    [[nodiscard]] const ActorCritic &model() const noexcept { return model_; }
    [[nodiscard]] torch::optim::Adam &optimizer() noexcept { return *optimizer_; }
    [[nodiscard]] const PpoConfig &config() const noexcept { return config_; }
    [[nodiscard]] RngStreams &rng() noexcept { return rng_; }
    [[nodiscard]] const RngStreams &rng() const noexcept { return rng_; }
    [[nodiscard]] TrainerCounters &counters() noexcept { return counters_; }
    [[nodiscard]] const TrainerCounters &counters() const noexcept { return counters_; }

private:
    PpoConfig config_;
    RngStreams rng_;
    ActorCritic model_;
    std::unique_ptr<torch::optim::Adam> optimizer_;
    TrainerCounters counters_;
};

} // namespace openttd_rl::training

#endif
