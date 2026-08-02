#ifndef OPENTTD_RL_TRAINING_CHECKPOINT_H
#define OPENTTD_RL_TRAINING_CHECKPOINT_H

#include <filesystem>
#include <memory>
#include <string>

#include "openttd_rl/training/trainer.h"

namespace openttd_rl::training {

inline constexpr const char *kPpoCompatibilitySha256 = "8649da85cee2914d423a7ae8f1bcff0fa6a1c7d749bd04232976fbad6df518c0";

struct CheckpointProvenance {
    std::string run_name;
    std::string repository_commit;
    std::string source_build_identity;
    std::string parent_checkpoint;
    std::string development_evaluation_json;
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
