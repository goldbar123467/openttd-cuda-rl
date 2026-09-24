#pragma once

#include <filesystem>
#include "openttd_rl/training/multimodal_trainer.h"

namespace openttd_rl::development {
// Trainer state only. The launcher owns environment recovery and provenance.
void save_live_checkpoint(const std::filesystem::path &, training::MultiModalPpoTrainer &);
// Load only into a fresh, identically configured trainer; discard it on failure.
void load_live_checkpoint(const std::filesystem::path &, training::MultiModalPpoTrainer &);
}
