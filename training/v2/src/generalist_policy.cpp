#include "openttd_rl/v2/generalist_policy.h"

#include <cmath>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

#include <torch/nn/init.h>

namespace openttd_rl::v2 {

namespace {

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

void initialize_linear(torch::nn::Linear &layer, double gain = std::sqrt(2.0))
{
    torch::nn::init::orthogonal_(layer->weight, gain);
    torch::nn::init::constant_(layer->bias, 0.0);
}

torch::Tensor masked_pool(
    const torch::Tensor &tokens,
    const torch::Tensor &mask,
    const torch::Tensor &query,
    torch::nn::Linear key,
    torch::nn::Linear value)
{
    auto scores = (key(tokens) * query.unsqueeze(1)).sum(-1) / std::sqrt(static_cast<double>(kM22PlannerTokenWidth));
    scores = scores.masked_fill(torch::logical_not(mask), -1.0e9);
    const auto maximum = std::get<0>(scores.max(1, true));
    auto weights = torch::exp(scores - maximum) * mask.unsqueeze(-1).squeeze(-1).to(torch::kFloat32);
    weights = weights / weights.sum(1, true).clamp_min(1.0e-12);
    return torch::bmm(weights.unsqueeze(1), value(tokens)).squeeze(1);
}

} // namespace

GeneralistArchitecture parse_generalist_architecture(std::string_view value)
{
    if (value == "monolithic-generalist-v1") return GeneralistArchitecture::Monolithic;
    if (value == "specialist-router-v1") return GeneralistArchitecture::SpecialistRouter;
    throw std::invalid_argument("unsupported M22 generalist architecture");
}

std::string_view generalist_architecture_name(GeneralistArchitecture architecture)
{
    switch (architecture) {
        case GeneralistArchitecture::Monolithic: return "monolithic-generalist-v1";
        case GeneralistArchitecture::SpecialistRouter: return "specialist-router-v1";
    }
    throw std::invalid_argument("invalid M22 generalist architecture enum");
}

GeneralistPolicyImpl::GeneralistPolicyImpl(std::uint64_t initialization_seed, GeneralistArchitecture architecture) :
    architecture_(architecture)
{
    initialization_seed &= static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max());
    base_policy = register_module("base_policy", ScalablePolicy(initialization_seed));
    torch::manual_seed(initialization_seed ^ UINT64_C(0x22a11ce5));
    domain_projection = register_module("domain_projection", torch::nn::Linear(kM22DomainTokenFeatures, kM22PlannerTokenWidth));
    domain_kind_embedding = register_module("domain_kind_embedding", torch::nn::Embedding(kM22DomainCount, kM22PlannerTokenWidth));
    domain_key = register_module("domain_key", torch::nn::Linear(kM22PlannerTokenWidth, kM22PlannerTokenWidth));
    domain_value = register_module("domain_value", torch::nn::Linear(kM22PlannerTokenWidth, kM22PlannerTokenWidth));
    domain_query = register_module("domain_query", torch::nn::Linear(kHiddenSize, kM22PlannerTokenWidth));
    program_projection = register_module("program_projection", torch::nn::Linear(kM22ProgramFeatures, kM22PlannerTokenWidth));
    specialist_embedding = register_module("specialist_embedding", torch::nn::Embedding(kM22ModeCount, kM22PlannerTokenWidth));
    planner_fusion = register_module("planner_fusion", torch::nn::Linear(kHiddenSize + kM22PlannerTokenWidth, kHiddenSize));
    planner_norm = register_module("planner_norm", torch::nn::LayerNorm(torch::nn::LayerNormOptions({kHiddenSize})));
    program_query = register_module("program_query", torch::nn::Linear(kHiddenSize, kM22PlannerTokenWidth));
    program_bias = register_module("program_bias", torch::nn::Linear(kM22PlannerTokenWidth, 1));
    planner_value = register_module("planner_value", torch::nn::Linear(kHiddenSize, 1));
    program_mode = register_buffer("program_mode", torch::tensor(
        {0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 6, 6, 6, 6, 6}, torch::TensorOptions().dtype(torch::kInt64)));

    torch::NoGradGuard guard;
    for (auto *layer : {&domain_projection, &domain_key, &domain_value, &domain_query, &program_projection,
                        &planner_fusion, &program_query, &program_bias}) {
        initialize_linear(*layer);
    }
    initialize_linear(planner_value, 1.0);
    torch::nn::init::normal_(domain_kind_embedding->weight, 0.0, 0.02);
    torch::nn::init::normal_(specialist_embedding->weight, 0.0, 0.02);
    for (const auto &parameter : named_parameters(true)) {
        require_finite(parameter.value(), (std::string("M22 initialization parameter ") + parameter.key()).c_str());
    }
}

GeneralistPolicyOutput GeneralistPolicyImpl::forward(const GeneralistPolicyInput &input)
{
    const auto device = planner_value->weight.device();
    if (!input.base.structured.defined() || input.base.structured.dim() != 2 || input.base.structured.size(0) <= 0) {
        throw std::invalid_argument("M22 base structured observation must have a positive batch");
    }
    const auto batch = input.base.structured.size(0);
    validate_float(input.domain_tokens, device, {kM22DomainTokenCapacity, kM22DomainTokenFeatures}, batch, "domain tokens");
    validate_bool(input.domain_token_mask, device, {kM22DomainTokenCapacity}, batch, "domain token mask");
    validate_float(input.program_features, device, {kM22ProgramCount, kM22ProgramFeatures}, batch, "program features");
    validate_bool(input.program_mask, device, {kM22ProgramCount}, batch, "program mask");
    if (!input.domain_token_kind.defined() || input.domain_token_kind.scalar_type() != torch::kInt64 ||
        input.domain_token_kind.device() != device ||
        input.domain_token_kind.sizes() != torch::IntArrayRef({batch, kM22DomainTokenCapacity})) {
        throw std::invalid_argument("domain token kinds must be a same-device [batch,256] int64 tensor");
    }
    if (!input.domain_token_mask.any(1).all().item<bool>() || !input.program_mask.any(1).all().item<bool>()) {
        throw std::invalid_argument("each M22 batch row must expose a domain token and legal program");
    }
    const auto kind_error = torch::logical_or(input.domain_token_kind < 0, input.domain_token_kind >= kM22DomainCount);
    if (kind_error.any().item<bool>()) {
        throw std::invalid_argument("domain token kind exceeds the frozen 18-domain inventory");
    }

    const auto base = base_policy->forward(input.base);
    auto domain = torch::tanh(domain_projection(input.domain_tokens)) + domain_kind_embedding(input.domain_token_kind);
    const auto query = domain_query(base.next_hidden);
    const auto domain_summary = masked_pool(domain, input.domain_token_mask, query, domain_key, domain_value);
    auto planner = torch::silu(planner_fusion(torch::cat({base.next_hidden, domain_summary}, 1)));
    planner = planner_norm(planner + base.next_hidden);
    auto programs = torch::tanh(program_projection(input.program_features));
    if (architecture_ == GeneralistArchitecture::SpecialistRouter) {
        programs = programs + specialist_embedding(program_mode).unsqueeze(0);
    }
    auto logits = (programs * program_query(planner).unsqueeze(1)).sum(-1) /
        std::sqrt(static_cast<double>(kM22PlannerTokenWidth));
    logits = logits + program_bias(programs).squeeze(-1);
    logits = logits.masked_fill(torch::logical_not(input.program_mask), -1.0e9);
    auto value = planner_value(planner).squeeze(-1);
    require_finite(logits, "M22 program logits");
    require_finite(value, "M22 program value");
    return {logits, value, base.next_hidden};
}

void require_finite_generalist(const GeneralistPolicy &model, const char *stage)
{
    if (!model) throw std::invalid_argument(std::string(stage) + " has no model");
    for (const auto &parameter : model->named_parameters(true)) {
        require_finite(parameter.value(), (std::string(stage) + " parameter " + parameter.key()).c_str());
    }
    for (const auto &buffer : model->named_buffers(true)) {
        if (buffer.value().is_floating_point()) {
            require_finite(buffer.value(), (std::string(stage) + " buffer " + buffer.key()).c_str());
        }
    }
}

} // namespace openttd_rl::v2
