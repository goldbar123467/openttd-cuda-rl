#ifndef OPENTTD_RL_TRAINING_MULTIMODAL_TRAINER_H
#define OPENTTD_RL_TRAINING_MULTIMODAL_TRAINER_H

#include <cstdint>
#include <memory>

#include <torch/torch.h>

#include "openttd_rl/training/multimodal_model.h"
#include "openttd_rl/training/trainer.h"

namespace openttd_rl::training {

struct MultiModalRolloutBatch {
    torch::Tensor structured;
    torch::Tensor spatial;
    torch::Tensor legal_masks;
    torch::Tensor actions;
    torch::Tensor old_log_probabilities;
    torch::Tensor old_values;
    torch::Tensor advantages;
    torch::Tensor returns;

    [[nodiscard]] std::int64_t size() const;
    void validate() const;
};

class MultiModalPpoTrainer {
public:
    MultiModalPpoTrainer(
        PpoConfig config,
        std::uint64_t run_seed,
        ArchitectureKind architecture,
        torch::Device device);

    [[nodiscard]] ActionBatch act(
        const torch::Tensor &structured,
        const torch::Tensor &spatial,
        const torch::Tensor &legal_masks,
        bool deterministic);
    [[nodiscard]] UpdateMetrics update(const MultiModalRolloutBatch &rollout);

    [[nodiscard]] MultiModalActorCritic &model() noexcept { return model_; }
    [[nodiscard]] const MultiModalActorCritic &model() const noexcept { return model_; }
    [[nodiscard]] torch::optim::Adam &optimizer() noexcept { return *optimizer_; }
    [[nodiscard]] const PpoConfig &config() const noexcept { return config_; }
    [[nodiscard]] ArchitectureKind architecture() const noexcept { return architecture_; }
    [[nodiscard]] const torch::Device &device() const noexcept { return device_; }
    [[nodiscard]] RngStreams &rng() noexcept { return rng_; }
    [[nodiscard]] const RngStreams &rng() const noexcept { return rng_; }
    [[nodiscard]] TrainerCounters &counters() noexcept { return counters_; }
    [[nodiscard]] const TrainerCounters &counters() const noexcept { return counters_; }

private:
    PpoConfig config_;
    RngStreams rng_;
    ArchitectureKind architecture_;
    torch::Device device_;
    MultiModalActorCritic model_;
    std::unique_ptr<torch::optim::Adam> optimizer_;
    TrainerCounters counters_;
};

} // namespace openttd_rl::training

#endif
