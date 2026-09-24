#pragma once
#include "openttd_rl/training/ppo.h"

namespace openttd_rl::development {
// Inference only: contiguous CUDA float32 [B,41], CUDA bool [B,41].
// No autograd implementation; PPO updates retain the trusted LibTorch path.
openttd_rl::training::MaskedPolicy fused_policy(const torch::Tensor &logits, const torch::Tensor &mask);
}
