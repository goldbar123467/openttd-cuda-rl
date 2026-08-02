#ifndef OPENTTD_RL_V2_CHECKPOINT_H
#define OPENTTD_RL_V2_CHECKPOINT_H

#include <cstdint>
#include <filesystem>
#include <string>

#include <torch/torch.h>

#include "openttd_rl/v2/scalable_policy.h"

namespace openttd_rl::v2 {

inline constexpr const char *kCheckpointSchemaId = "v2-m15-scalable-checkpoint-v1";

struct CurriculumState {
    std::uint32_t tier{};
    std::uint32_t map_width{};
    std::uint32_t map_height{};
    std::uint64_t episode{};
    std::uint64_t transition{};
};

struct PolicyRuntimeState {
    torch::Tensor normalization_mean;
    torch::Tensor normalization_variance;
    std::uint64_t normalization_count{};
    std::string rng_state;
    CurriculumState curriculum;
    std::uint64_t completed_updates{};
    torch::Tensor hidden_state;
};

struct SavedCheckpoint {
    std::string checkpoint_id;
    std::filesystem::path path;
};

[[nodiscard]] SavedCheckpoint save_checkpoint(
    const std::filesystem::path &checkpoint_root,
    ScalablePolicy &model,
    torch::optim::Adam &optimizer,
    const PolicyRuntimeState &state);

[[nodiscard]] PolicyRuntimeState load_checkpoint(
    const std::filesystem::path &checkpoint_path,
    ScalablePolicy &model,
    torch::optim::Adam &optimizer,
    const torch::Device &policy_device);

} // namespace openttd_rl::v2

#endif
