#include "openttd_rl/training/model.h"

#include <cmath>
#include <limits>
#include <stdexcept>
#include <string>

#include <torch/nn/init.h>

namespace openttd_rl::training {

namespace {

void initialize_linear(torch::nn::Linear &layer, double gain)
{
    torch::nn::init::orthogonal_(layer->weight, gain);
    torch::nn::init::constant_(layer->bias, 0.0);
}

} // namespace

ActorCriticImpl::ActorCriticImpl(std::uint64_t initialization_seed)
{
    if (initialization_seed > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max())) {
        initialization_seed &= static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max());
    }
    torch::manual_seed(initialization_seed);
    hidden_1 = register_module("hidden_1", torch::nn::Linear(kStructuredFeatures, kHiddenFeatures));
    hidden_2 = register_module("hidden_2", torch::nn::Linear(kHiddenFeatures, kHiddenFeatures));
    policy_head = register_module("policy_head", torch::nn::Linear(kHiddenFeatures, kActionCount));
    value_head = register_module("value_head", torch::nn::Linear(kHiddenFeatures, 1));

    torch::NoGradGuard guard;
    initialize_linear(hidden_1, std::sqrt(2.0));
    initialize_linear(hidden_2, std::sqrt(2.0));
    initialize_linear(policy_head, 0.01);
    initialize_linear(value_head, 1.0);
    for (const auto &parameter : named_parameters(true)) {
        require_finite_tensor(parameter.value(), (std::string("initialization parameter ") + parameter.key()).c_str());
    }
}

std::pair<torch::Tensor, torch::Tensor> ActorCriticImpl::forward(const torch::Tensor &structured)
{
    if (structured.device().is_cuda()) {
        throw std::invalid_argument("structured-mlp-v1 CPU oracle rejects CUDA tensors during M07");
    }
    if (structured.scalar_type() != torch::kFloat32 || structured.dim() != 2 ||
        structured.size(1) != kStructuredFeatures) {
        throw std::invalid_argument("structured observation must be CPU float32 [batch,256]");
    }
    require_finite_tensor(structured, "preprocessed observations");
    auto hidden = torch::tanh(hidden_1(structured));
    require_finite_tensor(hidden, "hidden_1 activations");
    hidden = torch::tanh(hidden_2(hidden));
    require_finite_tensor(hidden, "hidden_2 activations");
    auto logits = policy_head(hidden);
    auto values = value_head(hidden).squeeze(-1);
    require_finite_tensor(logits, "policy logits");
    require_finite_tensor(values, "state values");
    return {logits, values};
}

void require_finite_tensor(const torch::Tensor &tensor, const char *name)
{
    if (!tensor.defined()) throw std::invalid_argument(std::string(name) + " tensor is undefined");
    if (!torch::isfinite(tensor).all().item<bool>()) {
        throw std::runtime_error(std::string("nonfinite tensor: ") + name);
    }
}

void require_finite_model(const ActorCritic &model, const char *stage)
{
    for (const auto &parameter : model->named_parameters(true)) {
        require_finite_tensor(parameter.value(), (std::string(stage) + " parameter " + parameter.key()).c_str());
    }
}

} // namespace openttd_rl::training
