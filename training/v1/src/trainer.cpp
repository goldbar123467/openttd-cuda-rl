#include "openttd_rl/training/trainer.h"

#include <cmath>
#include <stdexcept>

#include <torch/nn/utils/clip_grad.h>

namespace openttd_rl::training {

namespace {

torch::Tensor indices_tensor(const std::vector<std::int64_t> &indices)
{
    return torch::from_blob(
               const_cast<std::int64_t *>(indices.data()),
               {static_cast<std::int64_t>(indices.size())},
               torch::TensorOptions().dtype(torch::kInt64))
        .clone();
}

void require_finite_gradients(const ActorCritic &model)
{
    for (const auto &parameter : model->named_parameters(true)) {
        if (!parameter.value().grad().defined()) {
            throw std::runtime_error("missing gradient: " + parameter.key());
        }
        require_finite_tensor(parameter.value().grad(), ("gradient " + parameter.key()).c_str());
    }
}

} // namespace

PpoTrainer::PpoTrainer(PpoConfig config, std::uint64_t run_seed)
    : config_(config), rng_(run_seed), model_(rng_.initialization_seed())
{
    config_.validate();
    optimizer_ = std::make_unique<torch::optim::Adam>(
        model_->parameters(),
        torch::optim::AdamOptions(config_.learning_rate).eps(config_.adam_epsilon));
    model_->to(torch::kCPU, torch::kFloat32);
}

ActionBatch PpoTrainer::act(
    const torch::Tensor &observations,
    const torch::Tensor &legal_masks,
    bool deterministic)
{
    const bool was_training = model_->is_training();
    model_->eval();
    torch::NoGradGuard guard;
    auto [logits, values] = model_->forward(observations);
    auto policy = masked_categorical(logits, legal_masks);
    torch::Tensor actions;
    if (deterministic) {
        actions = policy.log_probabilities.argmax(1);
    } else {
        actions = sample_masked_actions(policy.log_probabilities, legal_masks, rng_.action_sampling());
    }
    auto selected_log_probabilities = policy.log_probabilities.gather(1, actions.unsqueeze(1)).squeeze(1);
    require_finite_tensor(selected_log_probabilities, "selected log probabilities");
    if (was_training) model_->train();
    return {
        actions,
        selected_log_probabilities,
        values,
        logits,
    };
}

UpdateMetrics PpoTrainer::update(const RolloutBatch &rollout)
{
    config_.validate();
    rollout.validate(kStructuredFeatures, kActionCount);
    const auto expected_samples = config_.rollout_length * config_.environment_count;
    if (rollout.size() != expected_samples) throw std::invalid_argument("rollout sample count disagrees with configuration");
    model_->train();

    UpdateMetrics metrics;
    std::uint64_t minibatches = 0;
    for (std::int64_t epoch = 0; epoch < config_.optimization_epochs; ++epoch) {
        const auto batches = minibatch_indices(rollout.size(), config_.minibatch_size, rng_.minibatch_shuffle());
        for (const auto &batch : batches) {
            const auto indices = indices_tensor(batch);
            const auto observations = rollout.observations.index_select(0, indices);
            const auto masks = rollout.legal_masks.index_select(0, indices);
            const auto actions = rollout.actions.index_select(0, indices);
            const auto old_log_probabilities = rollout.old_log_probabilities.index_select(0, indices);
            const auto advantages = rollout.advantages.index_select(0, indices);
            const auto returns = rollout.returns.index_select(0, indices);

            auto [logits, values] = model_->forward(observations);
            auto policy = masked_categorical(logits, masks);
            auto new_log_probabilities = policy.log_probabilities.gather(1, actions.unsqueeze(1)).squeeze(1);
            auto losses = ppo_loss(
                new_log_probabilities,
                old_log_probabilities,
                advantages,
                values,
                returns,
                policy.entropy,
                config_);
            optimizer_->zero_grad();
            losses.total.backward();
            require_finite_gradients(model_);
            const double gradient_norm = torch::nn::utils::clip_grad_norm_(
                model_->parameters(), config_.max_gradient_norm, 2.0, true);
            if (!std::isfinite(gradient_norm)) throw std::runtime_error("nonfinite global gradient norm");
            require_finite_gradients(model_);
            optimizer_->step();
            require_finite_model(model_, "updated");

            metrics.policy_loss += losses.policy.item<double>();
            metrics.value_loss += losses.value.item<double>();
            metrics.entropy += losses.entropy.item<double>();
            metrics.approximate_kl += losses.approximate_kl.item<double>();
            metrics.clip_fraction += losses.clip_fraction.item<double>();
            metrics.gradient_norm += gradient_norm;
            ++minibatches;
        }
    }
    if (minibatches == 0) throw std::logic_error("PPO update executed no minibatches");
    const double denominator = static_cast<double>(minibatches);
    metrics.policy_loss /= denominator;
    metrics.value_loss /= denominator;
    metrics.entropy /= denominator;
    metrics.approximate_kl /= denominator;
    metrics.clip_fraction /= denominator;
    metrics.gradient_norm /= denominator;
    metrics.explained_variance = explained_variance(rollout.old_values, rollout.returns);
    metrics.learning_rate = config_.learning_rate;

    ++counters_.completed_updates;
    counters_.environment_steps += static_cast<std::uint64_t>(rollout.size());
    counters_.accepted_samples += static_cast<std::uint64_t>(rollout.size());
    metrics.update = counters_.completed_updates;
    metrics.samples = counters_.accepted_samples;
    return metrics;
}

} // namespace openttd_rl::training
