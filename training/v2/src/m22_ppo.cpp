#include "openttd_rl/v2/m22_ppo.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <string>

namespace openttd_rl::v2 {

namespace {

void require_finite(const torch::Tensor &tensor, const char *name)
{
    if (!tensor.defined() || !torch::isfinite(tensor).all().item<bool>()) {
        throw std::runtime_error(std::string(name) + " is undefined or nonfinite");
    }
}

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

void M22PpoConfig::validate() const
{
    if (!(gamma >= 0.0 && gamma <= 1.0) || !(gae_lambda >= 0.0 && gae_lambda <= 1.0) ||
        !(policy_clip > 0.0 && policy_clip < 1.0) || !(value_clip > 0.0 && value_clip < 1.0) ||
        value_coefficient < 0.0 || entropy_coefficient < 0.0 || learning_rate <= 0.0 ||
        adam_epsilon <= 0.0 || maximum_gradient_norm <= 0.0 || rollout_steps <= 0 ||
        parallel_environments <= 0 || minibatch_size <= 0 || epochs <= 0) {
        throw std::invalid_argument("invalid M22 PPO configuration");
    }
    if (rollout_steps > std::numeric_limits<std::int64_t>::max() / parallel_environments) {
        throw std::invalid_argument("M22 rollout sample count overflows int64");
    }
    const auto samples = rollout_steps * parallel_environments;
    if (samples / parallel_environments != rollout_steps || samples % minibatch_size != 0) {
        throw std::invalid_argument("M22 rollout samples must divide into complete minibatches");
    }
}

M22GaeResult m22_compute_gae(
    const torch::Tensor &rewards,
    const torch::Tensor &values,
    const torch::Tensor &next_values,
    const torch::Tensor &bootstrap_mask,
    const torch::Tensor &continuation_mask,
    double gamma,
    double gae_lambda)
{
    if (!(gamma >= 0.0 && gamma <= 1.0) || !(gae_lambda >= 0.0 && gae_lambda <= 1.0)) {
        throw std::invalid_argument("M22 gamma and lambda must be in [0,1]");
    }
    for (const auto *tensor : {&rewards, &values, &next_values, &bootstrap_mask, &continuation_mask}) {
        require_cpu(*tensor, "M22 GAE input");
        if (tensor->dim() != 2) throw std::invalid_argument("M22 GAE inputs must use [time,environment]");
        require_same_shape(rewards, *tensor, "M22 GAE input shapes differ");
        require_finite(*tensor, "M22 GAE input");
    }
    const auto bootstrap_valid = (bootstrap_mask >= 0).logical_and(bootstrap_mask <= 1).all().item<bool>();
    const auto continuation_valid = (continuation_mask >= 0).logical_and(continuation_mask <= 1).all().item<bool>();
    if (!bootstrap_valid || !continuation_valid) {
        throw std::invalid_argument("M22 GAE masks must be in [0,1]");
    }
    const auto rewards64 = rewards.to(torch::kFloat64).contiguous();
    const auto values64 = values.to(torch::kFloat64).contiguous();
    const auto next64 = next_values.to(torch::kFloat64).contiguous();
    const auto bootstrap64 = bootstrap_mask.to(torch::kFloat64).contiguous();
    const auto continuation64 = continuation_mask.to(torch::kFloat64).contiguous();
    auto advantages = torch::zeros_like(rewards64);
    auto accumulator = torch::zeros({rewards.size(1)}, rewards64.options());
    for (std::int64_t time = rewards.size(0); time-- > 0;) {
        const auto delta = rewards64[time] + gamma * bootstrap64[time] * next64[time] - values64[time];
        accumulator = delta + gamma * gae_lambda * continuation64[time] * accumulator;
        advantages[time].copy_(accumulator);
    }
    auto returns = advantages + values64;
    require_finite(advantages, "M22 advantages");
    require_finite(returns, "M22 returns");
    return {advantages, returns};
}

torch::Tensor m22_normalize_advantages(const torch::Tensor &advantages, double epsilon)
{
    require_cpu(advantages, "M22 advantages");
    require_finite(advantages, "M22 advantages");
    if (advantages.numel() == 0 || epsilon <= 0.0) throw std::invalid_argument("invalid M22 advantage normalization input");
    const auto values = advantages.to(torch::kFloat64);
    const auto mean = values.mean();
    const auto variance = torch::mean(torch::square(values - mean));
    if (variance.item<double>() <= epsilon * epsilon) return torch::zeros_like(values);
    auto result = (values - mean) / torch::sqrt(variance + epsilon);
    require_finite(result, "normalized M22 advantages");
    return result;
}

M22MaskedPolicy m22_masked_categorical(const torch::Tensor &logits, const torch::Tensor &legal_mask)
{
    if (!logits.defined() || !legal_mask.defined() || logits.dim() != 2 ||
        legal_mask.scalar_type() != torch::kBool || legal_mask.sizes() != logits.sizes() ||
        legal_mask.device() != logits.device()) {
        throw std::invalid_argument("M22 logits and boolean masks must be aligned same-device [batch,program]");
    }
    require_finite(logits, "M22 logits");
    const auto mask = legal_mask.to(torch::kBool);
    if (!mask.any(1).all().item<bool>()) throw std::invalid_argument("M22 all-illegal program mask");
    const auto masked = logits.masked_fill(torch::logical_not(mask), -std::numeric_limits<double>::infinity());
    const auto log_probabilities = torch::log_softmax(masked, 1);
    const auto probabilities = torch::where(mask, torch::exp(log_probabilities), torch::zeros_like(log_probabilities));
    const auto safe_logs = torch::where(mask, log_probabilities, torch::zeros_like(log_probabilities));
    const auto entropy = -(probabilities * safe_logs).sum(1);
    require_finite(probabilities, "M22 probabilities");
    require_finite(entropy, "M22 entropy");
    return {log_probabilities, probabilities, entropy};
}

M22LossResult m22_ppo_loss(
    const torch::Tensor &new_log_probabilities,
    const torch::Tensor &old_log_probabilities,
    const torch::Tensor &advantages,
    const torch::Tensor &new_values,
    const torch::Tensor &old_values,
    const torch::Tensor &returns,
    const torch::Tensor &entropy,
    const M22PpoConfig &config)
{
    config.validate();
    for (const auto *tensor : {&new_log_probabilities, &old_log_probabilities, &advantages, &new_values,
                               &old_values, &returns, &entropy}) {
        if (!tensor->defined() || tensor->dim() != 1) throw std::invalid_argument("M22 PPO loss inputs must be vectors");
        require_same_shape(new_log_probabilities, *tensor, "M22 PPO loss input shapes differ");
        if (tensor->device() != new_log_probabilities.device()) throw std::invalid_argument("M22 PPO loss device mismatch");
        require_finite(*tensor, "M22 PPO loss input");
    }
    const auto log_ratio = new_log_probabilities - old_log_probabilities;
    const auto ratio = torch::exp(log_ratio);
    const auto unclipped = ratio * advantages;
    const auto clipped_ratio = torch::clamp(ratio, 1.0 - config.policy_clip, 1.0 + config.policy_clip);
    const auto policy = -torch::minimum(unclipped, clipped_ratio * advantages).mean();
    const auto unclipped_value = torch::square(new_values - returns);
    const auto clipped_values = old_values + torch::clamp(new_values - old_values, -config.value_clip, config.value_clip);
    const auto value = torch::maximum(unclipped_value, torch::square(clipped_values - returns)).mean();
    const auto entropy_mean = entropy.mean();
    const auto total = policy + config.value_coefficient * value - config.entropy_coefficient * entropy_mean;
    const auto approximate_kl = torch::mean((ratio - 1.0) - log_ratio);
    const auto clip_fraction = torch::mean((torch::abs(ratio - 1.0) > config.policy_clip).to(torch::kFloat64));
    for (const auto *tensor : {&total, &policy, &value, &entropy_mean, &approximate_kl, &clip_fraction}) {
        require_finite(*tensor, "M22 PPO loss component");
    }
    return {total, policy, value, entropy_mean, approximate_kl, clip_fraction};
}

std::vector<std::vector<std::int64_t>> m22_minibatch_indices(
    std::int64_t sample_count,
    std::int64_t minibatch_size,
    std::mt19937_64 &generator)
{
    if (sample_count <= 0 || minibatch_size <= 0 || sample_count % minibatch_size != 0) {
        throw std::invalid_argument("M22 samples must divide into complete positive minibatches");
    }
    std::vector<std::int64_t> indices(static_cast<std::size_t>(sample_count));
    std::iota(indices.begin(), indices.end(), INT64_C(0));
    std::shuffle(indices.begin(), indices.end(), generator);
    std::vector<std::vector<std::int64_t>> result;
    for (std::int64_t start = 0; start < sample_count; start += minibatch_size) {
        const auto begin = indices.begin() + start;
        result.emplace_back(begin, begin + minibatch_size);
    }
    return result;
}

} // namespace openttd_rl::v2
