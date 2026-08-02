#ifndef OPENTTD_RL_TRAINING_EVALUATION_MODEL_H
#define OPENTTD_RL_TRAINING_EVALUATION_MODEL_H

#include <cstdint>
#include <filesystem>
#include <random>
#include <string>

#include <torch/torch.h>

#include "openttd_rl/training/multimodal_model.h"

namespace openttd_rl::training {

inline constexpr const char *kM09EvaluationCompatibilitySha256 =
    "c64c9876c1f6cf46dcc2642bd4628ed45f4659d1866a047d4e51def60dab9a5e";

struct EvaluationModelProvenance {
    std::string repository_commit;
    std::uint64_t run_seed{};
    std::uint64_t completed_updates{};
    std::uint64_t accepted_samples{};
    double training_mean_reward{};
};

struct SavedEvaluationModel {
    std::string package_id;
    std::filesystem::path path;
};

struct EvaluationActionBatch {
    torch::Tensor actions;
    torch::Tensor log_probabilities;
    torch::Tensor values;
    torch::Tensor logits;
};

[[nodiscard]] SavedEvaluationModel save_evaluation_model(
    const std::filesystem::path &package_root,
    MultiModalActorCritic &model,
    ArchitectureKind architecture,
    const EvaluationModelProvenance &provenance);

class ReadOnlyEvaluationPolicy {
public:
    ReadOnlyEvaluationPolicy(const std::filesystem::path &package_path, std::uint64_t sampling_seed);

    [[nodiscard]] EvaluationActionBatch act(
        const torch::Tensor &structured,
        const torch::Tensor &spatial,
        const torch::Tensor &legal_masks,
        bool deterministic);
    [[nodiscard]] const std::string &package_id() const noexcept { return package_id_; }
    [[nodiscard]] const std::string &model_sha256() const noexcept { return model_sha256_; }
    [[nodiscard]] std::string state_sha256() const;
    [[nodiscard]] ArchitectureKind architecture() const noexcept { return architecture_; }

private:
    std::string package_id_;
    std::string model_sha256_;
    ArchitectureKind architecture_;
    MultiModalActorCritic model_;
    std::mt19937_64 sampling_generator_;
};

} // namespace openttd_rl::training

#endif
