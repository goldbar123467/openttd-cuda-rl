#include "openttd_rl/v2/scalable_policy.h"

#include <cmath>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

#include <torch/nn/init.h>

namespace openttd_rl::v2 {

namespace {

constexpr std::int64_t kTokenWidth = 128;

void require_finite(const torch::Tensor &tensor, const char *name)
{
    if (!tensor.defined() || !torch::isfinite(tensor).all().item<bool>()) {
        throw std::runtime_error(std::string(name) + " is undefined or nonfinite");
    }
}

void validate_float(
    const torch::Tensor &tensor,
    const torch::Device &device,
    const std::vector<std::int64_t> &tail,
    std::int64_t batch,
    const char *name)
{
    if (!tensor.defined() || tensor.scalar_type() != torch::kFloat32 || tensor.device() != device ||
        tensor.dim() != static_cast<std::int64_t>(tail.size() + 1U) || tensor.size(0) != batch) {
        throw std::invalid_argument(std::string(name) + " must be a same-device batched float32 tensor");
    }
    for (std::size_t index = 0; index < tail.size(); ++index) {
        if (tensor.size(static_cast<std::int64_t>(index + 1U)) != tail[index]) {
            throw std::invalid_argument(std::string(name) + " has the wrong shape");
        }
    }
    require_finite(tensor, name);
}

void validate_bool(
    const torch::Tensor &tensor,
    const torch::Device &device,
    const std::vector<std::int64_t> &tail,
    std::int64_t batch,
    const char *name)
{
    if (!tensor.defined() || tensor.scalar_type() != torch::kBool || tensor.device() != device ||
        tensor.dim() != static_cast<std::int64_t>(tail.size() + 1U) || tensor.size(0) != batch) {
        throw std::invalid_argument(std::string(name) + " must be a same-device batched boolean tensor");
    }
    for (std::size_t index = 0; index < tail.size(); ++index) {
        if (tensor.size(static_cast<std::int64_t>(index + 1U)) != tail[index]) {
            throw std::invalid_argument(std::string(name) + " has the wrong shape");
        }
    }
}

void validate_entity(
    const EntityTable &table,
    const torch::Device &device,
    std::int64_t batch,
    std::int64_t capacity,
    std::int64_t features,
    const char *name)
{
    validate_float(table.features, device, {capacity, features}, batch, name);
    validate_bool(table.mask, device, {capacity}, batch, (std::string(name) + " mask").c_str());
}

torch::Tensor masked_attention_pool(
    const torch::Tensor &tokens,
    const torch::Tensor &mask,
    const torch::Tensor &query,
    torch::nn::Linear key,
    torch::nn::Linear value)
{
    auto scores = (key(tokens) * query.unsqueeze(1)).sum(-1) / std::sqrt(static_cast<double>(kTokenWidth));
    scores = scores.masked_fill(torch::logical_not(mask), -1.0e9);
    const auto maximum = std::get<0>(scores.max(1, true));
    auto weights = torch::exp(scores - maximum) * mask.to(torch::kFloat32);
    weights = weights / weights.sum(1, true).clamp_min(1.0e-12);
    return torch::bmm(weights.unsqueeze(1), value(tokens)).squeeze(1);
}

void initialize_linear(torch::nn::Linear &layer, double gain = std::sqrt(2.0))
{
    torch::nn::init::orthogonal_(layer->weight, gain);
    torch::nn::init::constant_(layer->bias, 0.0);
}

void initialize_convolution(torch::nn::Conv2d &layer)
{
    torch::nn::init::orthogonal_(layer->weight, std::sqrt(2.0));
    torch::nn::init::constant_(layer->bias, 0.0);
}

} // namespace

ScalablePolicyImpl::ScalablePolicyImpl(std::uint64_t initialization_seed)
{
    initialization_seed &= static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max());
    torch::manual_seed(initialization_seed);

    structured_1 = register_module("structured_1", torch::nn::Linear(kStructuredFeatures, 256));
    structured_2 = register_module("structured_2", torch::nn::Linear(256, kTokenWidth));
    spatial_1 = register_module("spatial_1", torch::nn::Conv2d(torch::nn::Conv2dOptions(kSpatialChannels, 32, 5).stride(2).padding(2)));
    spatial_2 = register_module("spatial_2", torch::nn::Conv2d(torch::nn::Conv2dOptions(32, 64, 3).stride(2).padding(1)));
    spatial_3 = register_module("spatial_3", torch::nn::Conv2d(torch::nn::Conv2dOptions(64, kTokenWidth, 3).stride(2).padding(1)));
    spatial_projection = register_module("spatial_projection", torch::nn::Linear(3 * kTokenWidth, 256));

    company_projection = register_module("company_projection", torch::nn::Linear(kCompanyFeatures, kTokenWidth));
    town_projection = register_module("town_projection", torch::nn::Linear(kTownFeatures, kTokenWidth));
    industry_projection = register_module("industry_projection", torch::nn::Linear(kIndustryFeatures, kTokenWidth));
    station_projection = register_module("station_projection", torch::nn::Linear(kStationFeatures, kTokenWidth));
    vehicle_projection = register_module("vehicle_projection", torch::nn::Linear(kVehicleFeatures, kTokenWidth));
    entity_query = register_module("entity_query", torch::nn::Linear(kTokenWidth, kTokenWidth));
    entity_key = register_module("entity_key", torch::nn::Linear(kTokenWidth, kTokenWidth));
    entity_value = register_module("entity_value", torch::nn::Linear(kTokenWidth, kTokenWidth));
    entity_fusion = register_module("entity_fusion", torch::nn::Linear(5 * kTokenWidth, kTokenWidth));
    entity_norm = register_module("entity_norm", torch::nn::LayerNorm(torch::nn::LayerNormOptions({kTokenWidth})));
    entity_feedforward = register_module("entity_feedforward", torch::nn::Linear(kTokenWidth, kTokenWidth));
    entity_output_norm = register_module("entity_output_norm", torch::nn::LayerNorm(torch::nn::LayerNormOptions({kTokenWidth})));
    entity_type_embedding = register_parameter("entity_type_embedding", torch::empty({5, kTokenWidth}, torch::kFloat32));

    graph_node_projection = register_module("graph_node_projection", torch::nn::Linear(kGraphNodeFeatures, kTokenWidth));
    graph_edge_projection = register_module("graph_edge_projection", torch::nn::Linear(kGraphEdgeFeatures, kTokenWidth));
    graph_message = register_module("graph_message", torch::nn::Linear(2 * kTokenWidth, kTokenWidth));
    graph_norm = register_module("graph_norm", torch::nn::LayerNorm(torch::nn::LayerNormOptions({kTokenWidth})));
    graph_query = register_module("graph_query", torch::nn::Linear(kTokenWidth, kTokenWidth));

    fusion = register_module("fusion", torch::nn::Linear(6 * kTokenWidth, kHiddenSize));
    fusion_norm = register_module("fusion_norm", torch::nn::LayerNorm(torch::nn::LayerNormOptions({kHiddenSize})));
    memory = register_module("memory", torch::nn::GRUCell(torch::nn::GRUCellOptions(kHiddenSize, kHiddenSize)));
    family_head = register_module("family_head", torch::nn::Linear(kHiddenSize, kFamilyCount));
    candidate_family_embedding = register_module("candidate_family_embedding", torch::nn::Embedding(kFamilyCount, kTokenWidth));
    candidate_projection = register_module("candidate_projection", torch::nn::Linear(kCandidateFeatures, kTokenWidth));
    candidate_query = register_module("candidate_query", torch::nn::Linear(kHiddenSize, kTokenWidth));
    candidate_bias = register_module("candidate_bias", torch::nn::Linear(kTokenWidth, 1));
    value_head = register_module("value_head", torch::nn::Linear(kHiddenSize, 1));

    torch::NoGradGuard guard;
    for (auto *layer : {
             &structured_1, &structured_2, &spatial_projection, &company_projection, &town_projection,
             &industry_projection, &station_projection, &vehicle_projection, &entity_query, &entity_key,
             &entity_value, &entity_fusion, &entity_feedforward, &graph_node_projection,
             &graph_edge_projection, &graph_message, &graph_query, &fusion, &candidate_projection,
             &candidate_query, &candidate_bias,
         }) {
        initialize_linear(*layer);
    }
    initialize_linear(family_head, 0.01);
    initialize_linear(value_head, 1.0);
    initialize_convolution(spatial_1);
    initialize_convolution(spatial_2);
    initialize_convolution(spatial_3);
    torch::nn::init::normal_(entity_type_embedding, 0.0, 0.02);
    torch::nn::init::normal_(candidate_family_embedding->weight, 0.0, 0.02);
    for (const auto &parameter : named_parameters(true)) {
        require_finite(parameter.value(), (std::string("initialization parameter ") + parameter.key()).c_str());
    }
}

torch::Tensor ScalablePolicyImpl::encode_spatial(const torch::Tensor &spatial)
{
    auto hidden = torch::silu(spatial_1(spatial));
    hidden = torch::silu(spatial_2(hidden));
    hidden = torch::silu(spatial_3(hidden));
    return hidden.mean({2, 3});
}

torch::Tensor ScalablePolicyImpl::attend_entity(
    const EntityTable &table,
    torch::nn::Linear projection,
    std::int64_t type_index,
    const torch::Tensor &query)
{
    auto tokens = torch::tanh(projection(table.features)) + entity_type_embedding.index({type_index});
    return masked_attention_pool(tokens, table.mask, query, entity_key, entity_value);
}

torch::Tensor ScalablePolicyImpl::encode_graph(const ScalablePolicyInput &input, const torch::Tensor &query)
{
    auto nodes = torch::tanh(graph_node_projection(input.graph_nodes));
    auto edges = torch::tanh(graph_edge_projection(input.graph_edge_features));
    auto sources = input.graph_edge_index.select(2, 0);
    auto destinations = input.graph_edge_index.select(2, 1);
    const auto safe_sources = torch::where(input.graph_edge_mask, sources, torch::zeros_like(sources));
    const auto safe_destinations = torch::where(input.graph_edge_mask, destinations, torch::zeros_like(destinations));
    const auto expanded_sources = safe_sources.unsqueeze(-1).expand({-1, -1, kTokenWidth});
    const auto source_nodes = torch::gather(nodes, 1, expanded_sources);
    auto messages = torch::tanh(graph_message(torch::cat({source_nodes, edges}, -1)));
    messages = messages * input.graph_edge_mask.unsqueeze(-1).to(torch::kFloat32);
    const auto expanded_destinations = safe_destinations.unsqueeze(-1).expand({-1, -1, kTokenWidth});
    auto aggregate = torch::zeros_like(nodes).scatter_add(1, expanded_destinations, messages);
    auto degree = torch::zeros({nodes.size(0), nodes.size(1), 1}, nodes.options()).scatter_add(
        1,
        safe_destinations.unsqueeze(-1),
        input.graph_edge_mask.unsqueeze(-1).to(torch::kFloat32));
    nodes = graph_norm(nodes + aggregate / degree.clamp_min(1.0));
    nodes = nodes * input.graph_node_mask.unsqueeze(-1).to(torch::kFloat32);
    return masked_attention_pool(nodes, input.graph_node_mask, graph_query(query), entity_key, entity_value);
}

ScalablePolicyOutput ScalablePolicyImpl::forward(const ScalablePolicyInput &input)
{
    const auto device = family_head->weight.device();
    if (!input.structured.defined() || input.structured.dim() != 2 || input.structured.size(0) <= 0) {
        throw std::invalid_argument("structured observation must have a positive batch");
    }
    const auto batch = input.structured.size(0);
    validate_float(input.structured, device, {kStructuredFeatures}, batch, "structured observation");
    validate_float(input.global_spatial, device, {kSpatialChannels, kGlobalSpatialSide, kGlobalSpatialSide}, batch, "global spatial observation");
    validate_float(input.regional_spatial, device, {kSpatialChannels, kRegionalSpatialSide, kRegionalSpatialSide}, batch, "regional spatial observation");
    validate_float(input.local_spatial, device, {kSpatialChannels, kLocalSpatialSide, kLocalSpatialSide}, batch, "local spatial observation");
    validate_entity(input.companies, device, batch, kCompanyCapacity, kCompanyFeatures, "company table");
    validate_entity(input.towns, device, batch, kTownCapacity, kTownFeatures, "town table");
    validate_entity(input.industries, device, batch, kIndustryCapacity, kIndustryFeatures, "industry table");
    validate_entity(input.stations, device, batch, kStationCapacity, kStationFeatures, "station table");
    validate_entity(input.vehicles, device, batch, kVehicleCapacity, kVehicleFeatures, "vehicle table");
    validate_float(input.graph_nodes, device, {kGraphNodeCapacity, kGraphNodeFeatures}, batch, "graph nodes");
    validate_bool(input.graph_node_mask, device, {kGraphNodeCapacity}, batch, "graph node mask");
    if (!input.graph_edge_index.defined() || input.graph_edge_index.scalar_type() != torch::kInt64 ||
        input.graph_edge_index.device() != device || input.graph_edge_index.sizes() != torch::IntArrayRef({batch, kGraphEdgeCapacity, 2})) {
        throw std::invalid_argument("graph edge index must be a same-device [batch,8192,2] int64 tensor");
    }
    validate_float(input.graph_edge_features, device, {kGraphEdgeCapacity, kGraphEdgeFeatures}, batch, "graph edge features");
    validate_bool(input.graph_edge_mask, device, {kGraphEdgeCapacity}, batch, "graph edge mask");
    validate_float(input.candidate_features, device, {kCandidateCapacity, kCandidateFeatures}, batch, "candidate features");
    if (!input.candidate_family.defined() || input.candidate_family.scalar_type() != torch::kInt64 ||
        input.candidate_family.device() != device || input.candidate_family.sizes() != torch::IntArrayRef({batch, kCandidateCapacity})) {
        throw std::invalid_argument("candidate family must be a same-device [batch,4096] int64 tensor");
    }
    validate_bool(input.candidate_mask, device, {kCandidateCapacity}, batch, "candidate mask");
    validate_bool(input.family_mask, device, {kFamilyCount}, batch, "family mask");
    validate_float(input.hidden_state, device, {kHiddenSize}, batch, "hidden state");
    validate_bool(input.recurrent_reset, device, {}, batch, "recurrent reset mask");
    if (!input.candidate_mask.any(1).all().item<bool>() || !input.family_mask.any(1).all().item<bool>()) {
        throw std::invalid_argument("each batch row must expose a legal family and candidate");
    }
    const auto candidate_range_error = torch::logical_or(input.candidate_family < 0, input.candidate_family >= kFamilyCount);
    if (torch::logical_and(candidate_range_error, input.candidate_mask).any().item<bool>()) {
        throw std::invalid_argument("legal candidate family is outside the frozen family inventory");
    }
    const auto edge_range_error = torch::logical_or(
        torch::logical_or(input.graph_edge_index.select(2, 0) < 0, input.graph_edge_index.select(2, 0) >= kGraphNodeCapacity),
        torch::logical_or(input.graph_edge_index.select(2, 1) < 0, input.graph_edge_index.select(2, 1) >= kGraphNodeCapacity));
    if (torch::logical_and(edge_range_error, input.graph_edge_mask).any().item<bool>()) {
        throw std::invalid_argument("legal graph edge index exceeds node capacity");
    }

    const auto structured_hidden = torch::tanh(structured_2(torch::tanh(structured_1(input.structured))));
    const auto spatial_hidden = torch::tanh(spatial_projection(torch::cat({
        encode_spatial(input.global_spatial),
        encode_spatial(input.regional_spatial),
        encode_spatial(input.local_spatial),
    }, 1)));
    const auto query = entity_query(structured_hidden);
    auto entity_hidden = torch::tanh(entity_fusion(torch::cat({
        attend_entity(input.companies, company_projection, 0, query),
        attend_entity(input.towns, town_projection, 1, query),
        attend_entity(input.industries, industry_projection, 2, query),
        attend_entity(input.stations, station_projection, 3, query),
        attend_entity(input.vehicles, vehicle_projection, 4, query),
    }, 1)));
    entity_hidden = entity_norm(entity_hidden + query);
    entity_hidden = entity_output_norm(entity_hidden + torch::silu(entity_feedforward(entity_hidden)));
    const auto graph_hidden = encode_graph(input, structured_hidden);

    auto candidate_tokens = torch::tanh(candidate_projection(input.candidate_features));
    const auto safe_families = torch::where(input.candidate_mask, input.candidate_family, torch::zeros_like(input.candidate_family));
    candidate_tokens = candidate_tokens + candidate_family_embedding(safe_families);
    const auto candidate_weights = input.candidate_mask.to(torch::kFloat32);
    const auto candidate_summary = (candidate_tokens * candidate_weights.unsqueeze(-1)).sum(1) /
        candidate_weights.sum(1, true).clamp_min(1.0);

    auto fused = torch::silu(fusion_norm(fusion(torch::cat({
        structured_hidden,
        spatial_hidden,
        entity_hidden,
        graph_hidden,
        candidate_summary,
    }, 1))));
    const auto reset_hidden = input.hidden_state * torch::logical_not(input.recurrent_reset).to(torch::kFloat32).unsqueeze(1);
    const auto next_hidden = memory(fused, reset_hidden);
    auto family_logits = family_head(next_hidden).masked_fill(torch::logical_not(input.family_mask), -1.0e9);
    const auto candidate_queries = candidate_query(next_hidden).unsqueeze(1);
    auto candidate_logits = (candidate_tokens * candidate_queries).sum(-1) / std::sqrt(static_cast<double>(kTokenWidth));
    candidate_logits = candidate_logits + candidate_bias(candidate_tokens).squeeze(-1);
    candidate_logits = candidate_logits.masked_fill(torch::logical_not(input.candidate_mask), -1.0e9);
    const auto value = value_head(next_hidden).squeeze(-1);
    require_finite(family_logits, "family logits");
    require_finite(candidate_logits, "candidate logits");
    require_finite(value, "value");
    require_finite(next_hidden, "next hidden state");
    return {family_logits, candidate_logits, value, next_hidden};
}

void require_finite_policy(const ScalablePolicy &model, const char *stage)
{
    for (const auto &parameter : model->named_parameters(true)) {
        require_finite(parameter.value(), (std::string(stage) + " parameter " + parameter.key()).c_str());
    }
}

} // namespace openttd_rl::v2
