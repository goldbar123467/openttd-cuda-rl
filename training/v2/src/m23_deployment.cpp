#include "openttd_rl/v2/m23_deployment.h"

#include <algorithm>
#include <array>
#include <stdexcept>
#include <string>
#include <vector>

namespace openttd_rl::v2 {

namespace {

using torch::indexing::Slice;

constexpr std::array<std::int64_t, kM22ProgramCount> kProgramMode = {
    0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 6, 6, 6, 6, 6,
};

void require_cpu_float(const torch::Tensor &value, std::int64_t batch, std::int64_t width, const char *name)
{
    if (!value.defined() || !value.device().is_cpu() || value.scalar_type() != torch::kFloat32 ||
        value.sizes() != torch::IntArrayRef({batch, width}) || !torch::isfinite(value).all().item<bool>()) {
        throw std::invalid_argument(std::string("M23 ") + name + " must be finite CPU float32 with the frozen shape");
    }
}

void require_cpu_bool(const torch::Tensor &value, const std::vector<std::int64_t> &shape, const char *name)
{
    if (!value.defined() || !value.device().is_cpu() || value.scalar_type() != torch::kBool ||
        value.sizes() != torch::IntArrayRef(shape)) {
        throw std::invalid_argument(std::string("M23 ") + name + " must be CPU bool with the frozen shape");
    }
}

} // namespace

void validate_m23_deployment_batch(const M23DeploymentBatch &batch)
{
    if (!batch.public_features.defined() || batch.public_features.dim() != 2) {
        throw std::invalid_argument("M23 public features must be a rank-two tensor");
    }
    const auto batch_size = batch.public_features.size(0);
    if (batch_size <= 0 || batch_size > kM23MaximumBatch) {
        throw std::invalid_argument("M23 batch must contain 1 through 32 rows");
    }
    require_cpu_float(batch.public_features, batch_size, kM23PublicFeatureCount, "public features");
    require_cpu_bool(batch.program_mask, {batch_size, kM22ProgramCount}, "program mask");
    require_cpu_float(batch.hidden_state, batch_size, kHiddenSize, "hidden state");
    require_cpu_bool(batch.recurrent_reset, {batch_size}, "recurrent reset");
    if (!batch.program_mask.any(1).all().item<bool>()) {
        throw std::invalid_argument("M23 each batch row must expose at least one legal program");
    }
}

GeneralistPolicyInput m23_deployment_input(const M23DeploymentBatch &batch, const torch::Device &device)
{
    validate_m23_deployment_batch(batch);
    if (!device.is_cpu() && !device.is_cuda()) {
        throw std::invalid_argument("M23 deployment adapter accepts only CPU or CUDA tensor devices");
    }
    const auto batch_size = batch.public_features.size(0);
    const auto state = batch.public_features.to(device);
    const auto floats = torch::TensorOptions().dtype(torch::kFloat32).device(device);
    const auto booleans = torch::TensorOptions().dtype(torch::kBool).device(device);
    const auto integers = torch::TensorOptions().dtype(torch::kInt64).device(device);
    auto structured = torch::zeros({batch_size, kStructuredFeatures}, floats);
    structured.index_put_({Slice(), Slice(0, kM23PublicFeatureCount)}, state);
    auto global = torch::zeros({batch_size, kSpatialChannels, kGlobalSpatialSide, kGlobalSpatialSide}, floats);
    auto regional = torch::zeros({batch_size, kSpatialChannels, kRegionalSpatialSide, kRegionalSpatialSide}, floats);
    auto local = torch::zeros({batch_size, kSpatialChannels, kLocalSpatialSide, kLocalSpatialSide}, floats);
    for (auto *spatial : {&global, &regional, &local}) {
        spatial->index_put_({Slice(), 0, Slice(), Slice()}, 1.0F);
        spatial->index_put_({Slice(), 1, Slice(), Slice()},
            state.index({Slice(), 11}).view({batch_size, 1, 1}));
        spatial->index_put_({Slice(), 2, Slice(), Slice()},
            state.index({Slice(), 12}).view({batch_size, 1, 1}));
    }
    auto make_entity = [&](std::int64_t capacity, std::int64_t features) {
        EntityTable table{
            torch::zeros({batch_size, capacity, features}, floats),
            torch::zeros({batch_size, capacity}, booleans),
        };
        const auto copied = std::min(features, kM23PublicFeatureCount);
        table.features.index_put_({Slice(), 0, Slice(0, copied)}, state.index({Slice(), Slice(0, copied)}));
        table.mask.index_put_({Slice(), 0}, true);
        return table;
    };
    auto companies = make_entity(kCompanyCapacity, kCompanyFeatures);
    auto towns = make_entity(kTownCapacity, kTownFeatures);
    auto industries = make_entity(kIndustryCapacity, kIndustryFeatures);
    auto stations = make_entity(kStationCapacity, kStationFeatures);
    auto vehicles = make_entity(kVehicleCapacity, kVehicleFeatures);
    auto graph_nodes = torch::zeros({batch_size, kGraphNodeCapacity, kGraphNodeFeatures}, floats);
    auto graph_node_mask = torch::zeros({batch_size, kGraphNodeCapacity}, booleans);
    graph_nodes.index_put_({Slice(), 0, Slice()}, state.index({Slice(), Slice(0, kGraphNodeFeatures)}));
    graph_node_mask.index_put_({Slice(), 0}, true);
    auto graph_edge_index = torch::zeros({batch_size, kGraphEdgeCapacity, 2}, integers);
    auto graph_edge_features = torch::zeros({batch_size, kGraphEdgeCapacity, kGraphEdgeFeatures}, floats);
    auto graph_edge_mask = torch::zeros({batch_size, kGraphEdgeCapacity}, booleans);
    graph_edge_features.index_put_({Slice(), 0, Slice()}, state.index({Slice(), Slice(14, 30)}));
    graph_edge_mask.index_put_({Slice(), 0}, true);
    auto candidate_features = torch::zeros({batch_size, kCandidateCapacity, kCandidateFeatures}, floats);
    candidate_features.index_put_({Slice(), 0, Slice()}, state);
    auto candidate_family = torch::zeros({batch_size, kCandidateCapacity}, integers);
    auto candidate_mask = torch::zeros({batch_size, kCandidateCapacity}, booleans);
    candidate_mask.index_put_({Slice(), 0}, true);
    auto family_mask = torch::zeros({batch_size, kFamilyCount}, booleans);
    family_mask.index_put_({Slice(), 0}, true);
    ScalablePolicyInput base{
        structured,
        global,
        regional,
        local,
        companies,
        towns,
        industries,
        stations,
        vehicles,
        graph_nodes,
        graph_node_mask,
        graph_edge_index,
        graph_edge_features,
        graph_edge_mask,
        candidate_features,
        candidate_family,
        candidate_mask,
        family_mask,
        batch.hidden_state.to(device),
        batch.recurrent_reset.to(device),
    };
    auto domain_tokens = torch::zeros(
        {batch_size, kM22DomainTokenCapacity, kM22DomainTokenFeatures}, floats);
    domain_tokens.index_put_({Slice(), 0, Slice(0, kM23PublicFeatureCount)}, state);
    auto domain_kind = torch::zeros({batch_size, kM22DomainTokenCapacity}, integers);
    domain_kind.index_put_({Slice(), 0}, state.index({Slice(), Slice(0, 7)}).argmax(1));
    auto domain_mask = torch::zeros({batch_size, kM22DomainTokenCapacity}, booleans);
    domain_mask.index_put_({Slice(), 0}, true);
    auto program_features = torch::zeros({batch_size, kM22ProgramCount, kM22ProgramFeatures}, floats);
    for (std::int64_t program = 0; program < kM22ProgramCount; ++program) {
        program_features.index_put_({Slice(), program, program}, 1.0F);
        program_features.index_put_({Slice(), program, 17 + kProgramMode[static_cast<std::size_t>(program)]}, 1.0F);
        const auto capability = program == 0 ? torch::ones({batch_size}, floats) :
            state.index({Slice(), 13 + program});
        program_features.index_put_({Slice(), program, 24}, capability);
        program_features.index_put_({Slice(), program, 25}, state.index({Slice(), 11}));
        program_features.index_put_({Slice(), program, 26}, state.index({Slice(), 12}));
        for (std::int64_t climate = 0; climate < 4; ++climate) {
            program_features.index_put_({Slice(), program, 27 + climate}, state.index({Slice(), 7 + climate}));
        }
        program_features.index_put_({Slice(), program, 31},
            state.index({Slice(), kProgramMode[static_cast<std::size_t>(program)]}));
    }
    return {
        base,
        domain_tokens,
        domain_kind,
        domain_mask,
        program_features,
        batch.program_mask.to(device),
    };
}

} // namespace openttd_rl::v2
