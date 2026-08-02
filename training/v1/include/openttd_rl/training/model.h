#ifndef OPENTTD_RL_TRAINING_MODEL_H
#define OPENTTD_RL_TRAINING_MODEL_H

#include <cstdint>
#include <utility>

#include <torch/torch.h>

namespace openttd_rl::training {

inline constexpr std::int64_t kStructuredFeatures = 256;
inline constexpr std::int64_t kActionCount = 41;
inline constexpr std::int64_t kHiddenFeatures = 128;
inline constexpr const char *kArchitectureId = "structured-mlp-v1";

struct ActorCriticImpl final : torch::nn::Module {
    explicit ActorCriticImpl(std::uint64_t initialization_seed);

    [[nodiscard]] std::pair<torch::Tensor, torch::Tensor> forward(const torch::Tensor &structured);

    torch::nn::Linear hidden_1{nullptr};
    torch::nn::Linear hidden_2{nullptr};
    torch::nn::Linear policy_head{nullptr};
    torch::nn::Linear value_head{nullptr};
};

TORCH_MODULE(ActorCritic);

void require_finite_tensor(const torch::Tensor &tensor, const char *name);
void require_finite_model(const ActorCritic &model, const char *stage);

} // namespace openttd_rl::training

#endif
