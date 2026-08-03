#ifndef OPENTTD_RL_V2_M22_CHECKPOINT_H
#define OPENTTD_RL_V2_M22_CHECKPOINT_H

#include <cstdint>
#include <filesystem>
#include <memory>
#include <string>
#include <vector>

#include <torch/torch.h>

#include "openttd_rl/v2/m22_corpus.h"

namespace openttd_rl::v2 {

inline constexpr const char *kM22CheckpointSchemaId = "v2-m22-generalist-checkpoint-v1";

struct M22CampaignCheckpointState {
    torch::Tensor normalization_mean;
    torch::Tensor normalization_variance;
    std::uint64_t normalization_count{};
    torch::Tensor hidden_state;
    std::vector<std::uint32_t> environment_case_cursor;
    std::uint32_t curriculum_stage{};
    std::uint32_t retention_pass_mask{};
    double retention_best_accuracy{};
    std::uint64_t episode{};
    std::uint64_t transition{};
    std::string retention_history_json;
    std::string selection_json;
};

struct M22SavedCheckpoint {
    std::string checkpoint_id;
    std::filesystem::path path;
};

struct M22LoadedCheckpoint {
    std::string checkpoint_id;
    M22CampaignCheckpointState campaign;
    std::unique_ptr<M22Trainer> trainer;
};

[[nodiscard]] M22SavedCheckpoint save_m22_checkpoint(
    const std::filesystem::path &checkpoint_root,
    M22Trainer &trainer,
    const M22CampaignCheckpointState &campaign);

[[nodiscard]] M22LoadedCheckpoint load_m22_checkpoint(
    const std::filesystem::path &checkpoint_path,
    const torch::Device &policy_device);

} // namespace openttd_rl::v2

#endif
