#ifndef OPENTTD_RL_TRAINING_CHECKPOINT_H
#define OPENTTD_RL_TRAINING_CHECKPOINT_H

#include <filesystem>
#include <memory>
#include <string>

#include "openttd_rl/training/trainer.h"

namespace openttd_rl::training {

inline constexpr const char *kPpoCompatibilitySha256 = "1b1f13cfb036afed82a630949ee727f6f20a94241923ab3a1aa60a1ec763f0de";

struct CheckpointProvenance {
    std::string run_name;
    std::string repository_commit;
    std::string source_build_identity;
    std::string parent_checkpoint;
};

struct SavedCheckpoint {
    std::string checkpoint_id;
    std::filesystem::path path;
};

struct LoadedCheckpoint {
    std::string checkpoint_id;
    CheckpointProvenance provenance;
    std::unique_ptr<PpoTrainer> trainer;
};

[[nodiscard]] SavedCheckpoint save_checkpoint(
    const std::filesystem::path &checkpoint_root,
    PpoTrainer &trainer,
    const CheckpointProvenance &provenance);

[[nodiscard]] LoadedCheckpoint load_checkpoint(const std::filesystem::path &checkpoint_path);

[[nodiscard]] std::filesystem::path write_numerical_diagnostic(
    const std::filesystem::path &artifact_root,
    const TrainerCounters &counters,
    const std::string &stage,
    const std::string &message);

} // namespace openttd_rl::training

#endif
