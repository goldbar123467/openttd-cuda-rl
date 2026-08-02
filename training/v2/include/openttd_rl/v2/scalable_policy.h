#ifndef OPENTTD_RL_V2_SCALABLE_POLICY_H
#define OPENTTD_RL_V2_SCALABLE_POLICY_H

#include <cstdint>

#include <torch/torch.h>

namespace openttd_rl::v2 {

inline constexpr std::int64_t kStructuredFeatures = 512;
inline constexpr std::int64_t kSpatialChannels = 32;
inline constexpr std::int64_t kGlobalSpatialSide = 64;
inline constexpr std::int64_t kRegionalSpatialSide = 64;
inline constexpr std::int64_t kLocalSpatialSide = 32;
inline constexpr std::int64_t kCompanyCapacity = 15;
inline constexpr std::int64_t kTownCapacity = 128;
inline constexpr std::int64_t kIndustryCapacity = 256;
inline constexpr std::int64_t kStationCapacity = 512;
inline constexpr std::int64_t kVehicleCapacity = 1024;
inline constexpr std::int64_t kCompanyFeatures = 32;
inline constexpr std::int64_t kTownFeatures = 24;
inline constexpr std::int64_t kIndustryFeatures = 24;
inline constexpr std::int64_t kStationFeatures = 32;
inline constexpr std::int64_t kVehicleFeatures = 40;
inline constexpr std::int64_t kGraphNodeCapacity = 2048;
inline constexpr std::int64_t kGraphNodeFeatures = 24;
inline constexpr std::int64_t kGraphEdgeCapacity = 8192;
inline constexpr std::int64_t kGraphEdgeFeatures = 16;
inline constexpr std::int64_t kCandidateCapacity = 4096;
inline constexpr std::int64_t kCandidateFeatures = 32;
inline constexpr std::int64_t kFamilyCount = 12;
inline constexpr std::int64_t kHiddenSize = 256;
inline constexpr const char *kPolicySchemaId = "v2-m15-policy-v1";
inline constexpr const char *kScalableContractSha256 =
    "b7a4ba1fc20507b77e2ef2ac01347665526cdbd4fc3e036587df5bdb3666d271";

struct EntityTable {
    torch::Tensor features;
    torch::Tensor mask;
};

struct ScalablePolicyInput {
    torch::Tensor structured;
    torch::Tensor global_spatial;
    torch::Tensor regional_spatial;
    torch::Tensor local_spatial;
    EntityTable companies;
    EntityTable towns;
    EntityTable industries;
    EntityTable stations;
    EntityTable vehicles;
    torch::Tensor graph_nodes;
    torch::Tensor graph_node_mask;
    torch::Tensor graph_edge_index;
    torch::Tensor graph_edge_features;
    torch::Tensor graph_edge_mask;
    torch::Tensor candidate_features;
    torch::Tensor candidate_family;
    torch::Tensor candidate_mask;
    torch::Tensor family_mask;
    torch::Tensor hidden_state;
    torch::Tensor recurrent_reset;
};

struct ScalablePolicyOutput {
    torch::Tensor family_logits;
    torch::Tensor candidate_logits;
    torch::Tensor value;
    torch::Tensor next_hidden;
};

struct ScalablePolicyImpl final : torch::nn::Module {
    explicit ScalablePolicyImpl(std::uint64_t initialization_seed);

    [[nodiscard]] ScalablePolicyOutput forward(const ScalablePolicyInput &input);

    torch::nn::Linear structured_1{nullptr};
    torch::nn::Linear structured_2{nullptr};
    torch::nn::Conv2d spatial_1{nullptr};
    torch::nn::Conv2d spatial_2{nullptr};
    torch::nn::Conv2d spatial_3{nullptr};
    torch::nn::Linear spatial_projection{nullptr};
    torch::nn::Linear company_projection{nullptr};
    torch::nn::Linear town_projection{nullptr};
    torch::nn::Linear industry_projection{nullptr};
    torch::nn::Linear station_projection{nullptr};
    torch::nn::Linear vehicle_projection{nullptr};
    torch::nn::Linear entity_query{nullptr};
    torch::nn::Linear entity_key{nullptr};
    torch::nn::Linear entity_value{nullptr};
    torch::nn::Linear entity_fusion{nullptr};
    torch::nn::LayerNorm entity_norm{nullptr};
    torch::nn::Linear entity_feedforward{nullptr};
    torch::nn::LayerNorm entity_output_norm{nullptr};
    torch::nn::Linear graph_node_projection{nullptr};
    torch::nn::Linear graph_edge_projection{nullptr};
    torch::nn::Linear graph_message{nullptr};
    torch::nn::LayerNorm graph_norm{nullptr};
    torch::nn::Linear graph_query{nullptr};
    torch::nn::Linear fusion{nullptr};
    torch::nn::LayerNorm fusion_norm{nullptr};
    torch::nn::GRUCell memory{nullptr};
    torch::nn::Linear family_head{nullptr};
    torch::nn::Embedding candidate_family_embedding{nullptr};
    torch::nn::Linear candidate_projection{nullptr};
    torch::nn::Linear candidate_query{nullptr};
    torch::nn::Linear candidate_bias{nullptr};
    torch::nn::Linear value_head{nullptr};
    torch::Tensor entity_type_embedding;

private:
    [[nodiscard]] torch::Tensor encode_spatial(const torch::Tensor &spatial);
    [[nodiscard]] torch::Tensor attend_entity(
        const EntityTable &table,
        torch::nn::Linear projection,
        std::int64_t type_index,
        const torch::Tensor &query);
    [[nodiscard]] torch::Tensor encode_graph(const ScalablePolicyInput &input, const torch::Tensor &query);
};

TORCH_MODULE(ScalablePolicy);

void require_finite_policy(const ScalablePolicy &model, const char *stage);

} // namespace openttd_rl::v2

#endif
