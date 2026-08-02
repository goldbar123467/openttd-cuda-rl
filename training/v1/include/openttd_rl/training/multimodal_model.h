#ifndef OPENTTD_RL_TRAINING_MULTIMODAL_MODEL_H
#define OPENTTD_RL_TRAINING_MULTIMODAL_MODEL_H

#include <cstdint>
#include <string>
#include <utility>

#include <torch/torch.h>

#include "openttd_rl/training/model.h"

namespace openttd_rl::training {

inline constexpr std::int64_t kSpatialChannels = 32;
inline constexpr std::int64_t kSpatialHeight = 32;
inline constexpr std::int64_t kSpatialWidth = 32;
inline constexpr const char *kM08CompatibilitySha256 =
    "52c8b622b79d793e85ef749822e6886cd7cdda63194a471d38ab25da910e101d";

enum class ArchitectureKind : std::uint8_t {
    StructuredMlp = 0,
    SpatialCnn = 1,
    CombinedCnnMlp = 2,
};

[[nodiscard]] ArchitectureKind parse_architecture_kind(const std::string &name);
[[nodiscard]] const char *architecture_name(ArchitectureKind kind) noexcept;

struct MultiModalActorCriticImpl final : torch::nn::Module {
    MultiModalActorCriticImpl(ArchitectureKind kind, std::uint64_t initialization_seed);

    [[nodiscard]] std::pair<torch::Tensor, torch::Tensor> forward(
        const torch::Tensor &structured,
        const torch::Tensor &spatial);
    [[nodiscard]] ArchitectureKind kind() const noexcept { return kind_; }

    torch::nn::Linear structured_1{nullptr};
    torch::nn::Linear structured_2{nullptr};
    torch::nn::Conv2d spatial_1{nullptr};
    torch::nn::Conv2d spatial_2{nullptr};
    torch::nn::Conv2d spatial_3{nullptr};
    torch::nn::Linear spatial_projection{nullptr};
    torch::nn::Linear fusion{nullptr};
    torch::nn::Linear policy_head{nullptr};
    torch::nn::Linear value_head{nullptr};

private:
    [[nodiscard]] torch::Tensor encode_spatial(const torch::Tensor &spatial);
    ArchitectureKind kind_;
};

TORCH_MODULE(MultiModalActorCritic);

void require_finite_multimodal_model(const MultiModalActorCritic &model, const char *stage);

} // namespace openttd_rl::training

#endif
