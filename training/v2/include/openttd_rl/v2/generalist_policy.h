#ifndef OPENTTD_RL_V2_GENERALIST_POLICY_H
#define OPENTTD_RL_V2_GENERALIST_POLICY_H

#include <cstdint>
#include <string_view>

#include <torch/torch.h>

#include "openttd_rl/v2/scalable_policy.h"

namespace openttd_rl::v2 {

inline constexpr std::int64_t kM22DomainCount = 18;
inline constexpr std::int64_t kM22DomainTokenCapacity = 256;
inline constexpr std::int64_t kM22DomainTokenFeatures = 64;
inline constexpr std::int64_t kM22ProgramCount = 17;
inline constexpr std::int64_t kM22ProgramFeatures = 64;
inline constexpr std::int64_t kM22ModeCount = 7;
inline constexpr std::int64_t kM22PlannerTokenWidth = 128;
inline constexpr std::int64_t kM22ParameterCount = 1457520;
inline constexpr const char *kM22LearningContractSha256 =
    "0d47417080e1675ba3040a0eef210fd4cc8c7523b832edfa3d282da7134f6b40";

enum class GeneralistArchitecture : std::uint8_t {
    Monolithic = 0,
    SpecialistRouter = 1,
};

[[nodiscard]] GeneralistArchitecture parse_generalist_architecture(std::string_view value);
[[nodiscard]] std::string_view generalist_architecture_name(GeneralistArchitecture architecture);

struct GeneralistPolicyInput {
    ScalablePolicyInput base;
    torch::Tensor domain_tokens;
    torch::Tensor domain_token_kind;
    torch::Tensor domain_token_mask;
    torch::Tensor program_features;
    torch::Tensor program_mask;
};

struct GeneralistPolicyOutput {
    torch::Tensor program_logits;
    torch::Tensor program_value;
    torch::Tensor next_hidden;
};

struct GeneralistPolicyImpl final : torch::nn::Module {
    GeneralistPolicyImpl(std::uint64_t initialization_seed, GeneralistArchitecture architecture);

    [[nodiscard]] GeneralistPolicyOutput forward(const GeneralistPolicyInput &input);
    [[nodiscard]] GeneralistArchitecture architecture() const noexcept { return architecture_; }

    ScalablePolicy base_policy{nullptr};
    torch::nn::Linear domain_projection{nullptr};
    torch::nn::Embedding domain_kind_embedding{nullptr};
    torch::nn::Linear domain_key{nullptr};
    torch::nn::Linear domain_value{nullptr};
    torch::nn::Linear domain_query{nullptr};
    torch::nn::Linear program_projection{nullptr};
    torch::nn::Embedding specialist_embedding{nullptr};
    torch::nn::Linear planner_fusion{nullptr};
    torch::nn::LayerNorm planner_norm{nullptr};
    torch::nn::Linear program_query{nullptr};
    torch::nn::Linear program_bias{nullptr};
    torch::nn::Linear planner_value{nullptr};
    torch::Tensor program_mode;

private:
    GeneralistArchitecture architecture_;
};

TORCH_MODULE(GeneralistPolicy);

void require_finite_generalist(const GeneralistPolicy &model, const char *stage);

} // namespace openttd_rl::v2

#endif
