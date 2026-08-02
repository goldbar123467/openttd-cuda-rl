#include "openttd_rl/training/ppo.h"

#include "openttd_rl/training/model.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <random>
#include <stdexcept>
#include <string>

namespace openttd_rl::training {

namespace {

void require_cpu(const torch::Tensor &tensor, const char *name)
{
    if (!tensor.defined() || tensor.device().is_cuda()) {
        throw std::invalid_argument(std::string(name) + " must be a defined CPU tensor");
    }
}

void require_same_shape(const torch::Tensor &left, const torch::Tensor &right, const char *message)
{
    if (left.sizes() != right.sizes()) throw std::invalid_argument(message);
}

} // namespace

void PpoConfig::validate() const
{
    if (!(gamma >= 0.0 && gamma <= 1.0) || !(gae_lambda >= 0.0 && gae_lambda <= 1.0)) {
        throw std::invalid_argument("gamma and gae_lambda must be in [0,1]");
    }
    if (!(clip_epsilon > 0.0 && clip_epsilon <= 1.0) || value_coefficient < 0.0 ||
        entropy_coefficient < 0.0 || learning_rate <= 0.0 || adam_epsilon <= 0.0 ||
        max_gradient_norm <= 0.0) {
        throw std::invalid_argument("invalid PPO optimization hyperparameter");
    }
    if (rollout_length <= 0 || environment_count <= 0 || minibatch_size <= 0 || optimization_epochs <= 0) {
        throw std::invalid_argument("PPO sizes and epochs must be positive");
    }
    const auto samples = rollout_length * environment_count;
    if (samples / environment_count != rollout_length || samples % minibatch_size != 0) {
        throw std::invalid_argument("rollout samples must divide into complete minibatches");
    }
}

std::int64_t RolloutBatch::size() const
{
    return observations.defined() && observations.dim() > 0 ? observations.size(0) : 0;
}

void RolloutBatch::validate(std::int64_t expected_observation_features, std::int64_t expected_action_count) const
{
    require_cpu(observations, "observations");
    require_cpu(legal_masks, "legal masks");
    require_cpu(actions, "actions");
    const auto samples = size();
    if (observations.scalar_type() != torch::kFloat32 || observations.dim() != 2 ||
        observations.size(1) != expected_observation_features) {
        throw std::invalid_argument("rollout observations have the wrong dtype or shape");
    }
    if (legal_masks.dim() != 2 || legal_masks.size(0) != samples || legal_masks.size(1) != expected_action_count) {
        throw std::invalid_argument("rollout legal masks have the wrong shape");
    }
    if (actions.scalar_type() != torch::kInt64 || actions.dim() != 1 || actions.size(0) != samples) {
        throw std::invalid_argument("rollout actions must be int64 [samples]");
    }
    for (const auto *tensor : {&old_log_probabilities, &old_values, &advantages, &returns}) {
        require_cpu(*tensor, "rollout vector");
        if (tensor->dim() != 1 || tensor->size(0) != samples) {
            throw std::invalid_argument("rollout vectors must be aligned [samples]");
        }
        require_finite_tensor(*tensor, "rollout vector");
    }
    require_finite_tensor(observations, "rollout observations");
    auto boolean_mask = legal_masks.to(torch::kBool);
    if (!boolean_mask.any(1).all().item<bool>()) throw std::invalid_argument("rollout contains an all-illegal mask");
    const auto selected_legal = boolean_mask.gather(1, actions.unsqueeze(1)).squeeze(1);
    if (!selected_legal.all().item<bool>()) throw std::invalid_argument("stored rollout action is illegal under stored mask");
}

GaeResult compute_gae(
    const torch::Tensor &rewards,
    const torch::Tensor &values,
    const torch::Tensor &next_values,
    const torch::Tensor &bootstrap_mask,
    const torch::Tensor &continuation_mask,
    double gamma,
    double gae_lambda)
{
    if (!(gamma >= 0.0 && gamma <= 1.0) || !(gae_lambda >= 0.0 && gae_lambda <= 1.0)) {
        throw std::invalid_argument("gamma and gae_lambda must be in [0,1]");
    }
    for (const auto *tensor : {&rewards, &values, &next_values, &bootstrap_mask, &continuation_mask}) {
        require_cpu(*tensor, "GAE input");
        if (tensor->dim() != 2) throw std::invalid_argument("GAE inputs must use [time,environment] layout");
        require_same_shape(rewards, *tensor, "GAE input shapes differ");
        require_finite_tensor(*tensor, "GAE input");
    }
    const auto bootstrap_valid = (bootstrap_mask >= 0).logical_and(bootstrap_mask <= 1).all().item<bool>();
    const auto continuation_valid = (continuation_mask >= 0).logical_and(continuation_mask <= 1).all().item<bool>();
    if (!bootstrap_valid || !continuation_valid) throw std::invalid_argument("GAE masks must be in [0,1]");

    auto reward64 = rewards.to(torch::kFloat64).contiguous();
    auto value64 = values.to(torch::kFloat64).contiguous();
    auto next64 = next_values.to(torch::kFloat64).contiguous();
    auto bootstrap64 = bootstrap_mask.to(torch::kFloat64).contiguous();
    auto continuation64 = continuation_mask.to(torch::kFloat64).contiguous();
    auto advantages = torch::zeros_like(reward64);
    auto accumulator = torch::zeros({rewards.size(1)}, reward64.options());
    for (std::int64_t time = rewards.size(0); time-- > 0;) {
        const auto delta = reward64[time] + gamma * bootstrap64[time] * next64[time] - value64[time];
        accumulator = delta + gamma * gae_lambda * continuation64[time] * accumulator;
        advantages[time].copy_(accumulator);
    }
    auto returns = advantages + value64;
    require_finite_tensor(advantages, "advantages");
    require_finite_tensor(returns, "returns");
    return {advantages, returns};
}

torch::Tensor normalize_advantages(const torch::Tensor &advantages, double epsilon)
{
    require_cpu(advantages, "advantages");
    require_finite_tensor(advantages, "advantages");
    if (advantages.numel() == 0 || epsilon <= 0.0) throw std::invalid_argument("invalid advantage normalization input");
    auto values = advantages.to(torch::kFloat64);
    const auto mean = values.mean();
    const auto variance = torch::mean(torch::square(values - mean));
    if (variance.item<double>() <= epsilon * epsilon) return torch::zeros_like(values);
    auto normalized = (values - mean) / torch::sqrt(variance + epsilon);
    require_finite_tensor(normalized, "normalized advantages");
    return normalized;
}

MaskedPolicy masked_categorical(const torch::Tensor &logits, const torch::Tensor &legal_mask)
{
    require_cpu(logits, "policy logits");
    require_cpu(legal_mask, "legal action mask");
    if (logits.dim() != 2 || legal_mask.sizes() != logits.sizes()) {
        throw std::invalid_argument("policy logits and legal masks must have identical [batch,action] shape");
    }
    require_finite_tensor(logits, "policy logits");
    auto mask = legal_mask.to(torch::kBool);
    if (!mask.any(1).all().item<bool>()) throw std::invalid_argument("all-illegal action mask");
    auto masked_logits = logits.masked_fill(mask.logical_not(), -std::numeric_limits<double>::infinity());
    auto log_probabilities = torch::log_softmax(masked_logits, 1);
    auto probabilities = torch::where(mask, torch::exp(log_probabilities), torch::zeros_like(log_probabilities));
    require_finite_tensor(probabilities, "masked probabilities");
    auto safe_log_probabilities = torch::where(mask, log_probabilities, torch::zeros_like(log_probabilities));
    auto entropy = -(probabilities * safe_log_probabilities).sum(1);
    require_finite_tensor(entropy, "masked entropy");
    return {log_probabilities, probabilities, entropy};
}

LossResult ppo_loss(
    const torch::Tensor &new_log_probabilities,
    const torch::Tensor &old_log_probabilities,
    const torch::Tensor &advantages,
    const torch::Tensor &new_values,
    const torch::Tensor &returns,
    const torch::Tensor &entropy,
    const PpoConfig &config)
{
    config.validate();
    for (const auto *tensor : {&new_log_probabilities, &old_log_probabilities, &advantages, &new_values, &returns, &entropy}) {
        require_cpu(*tensor, "PPO loss input");
        if (tensor->dim() != 1) throw std::invalid_argument("PPO loss inputs must be one-dimensional");
        require_same_shape(new_log_probabilities, *tensor, "PPO loss input shapes differ");
        require_finite_tensor(*tensor, "PPO loss input");
    }
    const auto log_ratio = new_log_probabilities - old_log_probabilities;
    const auto ratio = torch::exp(log_ratio);
    require_finite_tensor(ratio, "probability ratio");
    const auto unclipped = ratio * advantages;
    const auto clipped_ratio = torch::clamp(ratio, 1.0 - config.clip_epsilon, 1.0 + config.clip_epsilon);
    const auto policy = -torch::minimum(unclipped, clipped_ratio * advantages).mean();
    const auto value = torch::mean(torch::square(new_values - returns));
    const auto entropy_mean = entropy.mean();
    const auto total = policy + config.value_coefficient * value - config.entropy_coefficient * entropy_mean;
    const auto approximate_kl = torch::mean((ratio - 1.0) - log_ratio);
    const auto clip_fraction = torch::mean((torch::abs(ratio - 1.0) > config.clip_epsilon).to(torch::kFloat64));
    for (const auto *tensor : {&total, &policy, &value, &entropy_mean, &approximate_kl, &clip_fraction}) {
        require_finite_tensor(*tensor, "PPO loss component");
    }
    return {total, policy, value, entropy_mean, approximate_kl, clip_fraction};
}

std::vector<std::vector<std::int64_t>> minibatch_indices(
    std::int64_t sample_count,
    std::int64_t minibatch_size,
    std::mt19937_64 &generator)
{
    if (sample_count <= 0 || minibatch_size <= 0 || sample_count % minibatch_size != 0) {
        throw std::invalid_argument("samples must divide into complete positive minibatches");
    }
    std::vector<std::int64_t> indices(static_cast<std::size_t>(sample_count));
    std::iota(indices.begin(), indices.end(), INT64_C(0));
    std::shuffle(indices.begin(), indices.end(), generator);
    std::vector<std::vector<std::int64_t>> batches;
    for (std::int64_t start = 0; start < sample_count; start += minibatch_size) {
        const auto begin = indices.begin() + start;
        batches.emplace_back(begin, begin + minibatch_size);
    }
    return batches;
}

double explained_variance(const torch::Tensor &values, const torch::Tensor &returns)
{
    require_cpu(values, "values");
    require_cpu(returns, "returns");
    require_same_shape(values, returns, "explained variance shapes differ");
    require_finite_tensor(values, "values");
    require_finite_tensor(returns, "returns");
    const auto targets = returns.to(torch::kFloat64);
    const auto variance = torch::mean(torch::square(targets - targets.mean())).item<double>();
    if (variance <= 1e-16) return 0.0;
    const auto residual = targets - values.to(torch::kFloat64);
    return 1.0 - torch::mean(torch::square(residual - residual.mean())).item<double>() / variance;
}

} // namespace openttd_rl::training
