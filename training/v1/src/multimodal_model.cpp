#include "openttd_rl/training/multimodal_model.h"

#include <cmath>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

#include <torch/nn/init.h>

namespace openttd_rl::training {

namespace {

void initialize_linear(torch::nn::Linear &layer, double gain)
{
    torch::nn::init::orthogonal_(layer->weight, gain);
    torch::nn::init::constant_(layer->bias, 0.0);
}

void initialize_convolution(torch::nn::Conv2d &layer, double gain)
{
    torch::nn::init::orthogonal_(layer->weight, gain);
    torch::nn::init::constant_(layer->bias, 0.0);
}

void require_finite_without_cuda_synchronization(const torch::Tensor &tensor, const char *name)
{
    if (!tensor.device().is_cuda()) require_finite_tensor(tensor, name);
}

void validate_input(
    const torch::Tensor &tensor,
    const torch::Device &device,
    const std::vector<std::int64_t> &tail,
    const char *name)
{
    if (!tensor.defined() || tensor.scalar_type() != torch::kFloat32 || tensor.dim() != static_cast<std::int64_t>(tail.size() + 1U)) {
        throw std::invalid_argument(std::string(name) + " must be a batched float32 tensor");
    }
    for (std::size_t index = 0; index < tail.size(); ++index) {
        if (tensor.size(static_cast<std::int64_t>(index + 1U)) != tail[index]) {
            throw std::invalid_argument(std::string(name) + " has the wrong shape");
        }
    }
    if (tensor.device() != device) throw std::invalid_argument(std::string(name) + " is on the wrong device");
    require_finite_without_cuda_synchronization(tensor, name);
}

} // namespace

ArchitectureKind parse_architecture_kind(const std::string &name)
{
    if (name == "structured-mlp-v1") return ArchitectureKind::StructuredMlp;
    if (name == "spatial-cnn-v1") return ArchitectureKind::SpatialCnn;
    if (name == "combined-cnn-mlp-v1") return ArchitectureKind::CombinedCnnMlp;
    throw std::invalid_argument("unknown M08 architecture: " + name);
}

const char *architecture_name(ArchitectureKind kind) noexcept
{
    switch (kind) {
        case ArchitectureKind::StructuredMlp: return "structured-mlp-v1";
        case ArchitectureKind::SpatialCnn: return "spatial-cnn-v1";
        case ArchitectureKind::CombinedCnnMlp: return "combined-cnn-mlp-v1";
    }
    return "invalid-architecture";
}

MultiModalActorCriticImpl::MultiModalActorCriticImpl(
    ArchitectureKind kind,
    std::uint64_t initialization_seed)
    : kind_(kind)
{
    initialization_seed &= static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max());
    torch::manual_seed(initialization_seed);
    if (kind_ == ArchitectureKind::StructuredMlp) {
        structured_1 = register_module("hidden_1", torch::nn::Linear(kStructuredFeatures, kHiddenFeatures));
        structured_2 = register_module("hidden_2", torch::nn::Linear(kHiddenFeatures, kHiddenFeatures));
    } else {
        if (kind_ == ArchitectureKind::CombinedCnnMlp) {
            structured_1 = register_module("structured_1", torch::nn::Linear(kStructuredFeatures, kHiddenFeatures));
        }
        spatial_1 = register_module("spatial_1", torch::nn::Conv2d(
            torch::nn::Conv2dOptions(kSpatialChannels, 32, 3).stride(1).padding(1)));
        spatial_2 = register_module("spatial_2", torch::nn::Conv2d(
            torch::nn::Conv2dOptions(32, 64, 3).stride(2).padding(1)));
        spatial_3 = register_module("spatial_3", torch::nn::Conv2d(
            torch::nn::Conv2dOptions(64, 64, 3).stride(2).padding(1)));
        spatial_projection = register_module("spatial_projection", torch::nn::Linear(64 * 8 * 8, kHiddenFeatures));
        if (kind_ == ArchitectureKind::CombinedCnnMlp) {
            fusion = register_module("fusion", torch::nn::Linear(2 * kHiddenFeatures, kHiddenFeatures));
        }
    }
    policy_head = register_module("policy_head", torch::nn::Linear(kHiddenFeatures, kActionCount));
    value_head = register_module("value_head", torch::nn::Linear(kHiddenFeatures, 1));

    torch::NoGradGuard guard;
    if (structured_1) initialize_linear(structured_1, std::sqrt(2.0));
    if (structured_2) initialize_linear(structured_2, std::sqrt(2.0));
    if (spatial_1) initialize_convolution(spatial_1, std::sqrt(2.0));
    if (spatial_2) initialize_convolution(spatial_2, std::sqrt(2.0));
    if (spatial_3) initialize_convolution(spatial_3, std::sqrt(2.0));
    if (spatial_projection) initialize_linear(spatial_projection, std::sqrt(2.0));
    if (fusion) initialize_linear(fusion, std::sqrt(2.0));
    initialize_linear(policy_head, 0.01);
    initialize_linear(value_head, 1.0);
    for (const auto &parameter : named_parameters(true)) {
        require_finite_tensor(
            parameter.value(),
            (std::string("initialization parameter ") + parameter.key()).c_str());
    }
}

torch::Tensor MultiModalActorCriticImpl::encode_spatial(const torch::Tensor &spatial)
{
    auto hidden = torch::tanh(spatial_1(spatial));
    require_finite_without_cuda_synchronization(hidden, "spatial_1 activations");
    hidden = torch::tanh(spatial_2(hidden));
    require_finite_without_cuda_synchronization(hidden, "spatial_2 activations");
    hidden = torch::tanh(spatial_3(hidden));
    require_finite_without_cuda_synchronization(hidden, "spatial_3 activations");
    hidden = torch::tanh(spatial_projection(hidden.flatten(1)));
    require_finite_without_cuda_synchronization(hidden, "spatial projection activations");
    return hidden;
}

std::pair<torch::Tensor, torch::Tensor> MultiModalActorCriticImpl::forward(
    const torch::Tensor &structured,
    const torch::Tensor &spatial)
{
    const auto device = policy_head->weight.device();
    torch::Tensor hidden;
    if (kind_ == ArchitectureKind::StructuredMlp) {
        validate_input(structured, device, {kStructuredFeatures}, "structured observation");
        hidden = torch::tanh(structured_1(structured));
        require_finite_without_cuda_synchronization(hidden, "hidden_1 activations");
        hidden = torch::tanh(structured_2(hidden));
        require_finite_without_cuda_synchronization(hidden, "hidden_2 activations");
    } else {
        validate_input(spatial, device, {kSpatialChannels, kSpatialHeight, kSpatialWidth}, "spatial observation");
        auto spatial_hidden = encode_spatial(spatial);
        if (kind_ == ArchitectureKind::SpatialCnn) {
            hidden = spatial_hidden;
        } else {
            validate_input(structured, device, {kStructuredFeatures}, "structured observation");
            auto structured_hidden = torch::tanh(structured_1(structured));
            require_finite_without_cuda_synchronization(structured_hidden, "structured projection activations");
            hidden = torch::tanh(fusion(torch::cat({structured_hidden, spatial_hidden}, 1)));
            require_finite_without_cuda_synchronization(hidden, "fusion activations");
        }
    }
    auto logits = policy_head(hidden);
    auto values = value_head(hidden).squeeze(-1);
    require_finite_without_cuda_synchronization(logits, "M08 policy logits");
    require_finite_without_cuda_synchronization(values, "M08 state values");
    return {logits, values};
}

void require_finite_multimodal_model(const MultiModalActorCritic &model, const char *stage)
{
    for (const auto &parameter : model->named_parameters(true)) {
        require_finite_tensor(parameter.value(), (std::string(stage) + " parameter " + parameter.key()).c_str());
    }
}

} // namespace openttd_rl::training
