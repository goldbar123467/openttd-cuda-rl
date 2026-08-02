#ifndef OPENTTD_RL_TRAINING_SERVICE_H
#define OPENTTD_RL_TRAINING_SERVICE_H

#include <filesystem>

#include "openttd_rl/training/trainer.h"

namespace openttd_rl::training {

int run_trainer_service(
    PpoTrainer &trainer,
    int input_descriptor,
    int output_descriptor,
    const std::filesystem::path &diagnostic_root);

} // namespace openttd_rl::training

#endif
