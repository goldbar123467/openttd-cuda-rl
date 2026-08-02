#include "openttd_rl/training/learning.h"

#include <stdexcept>

#include "openttd_rl/training/model.h"

namespace openttd_rl::training {

namespace {

std::pair<torch::Tensor, torch::Tensor> bandit_inputs(PpoTrainer &trainer, std::int64_t samples)
{
    auto observations = torch::zeros({samples, kStructuredFeatures}, torch::kFloat32);
    auto contexts = torch::empty({samples}, torch::kInt64);
    auto observation_view = observations.accessor<float, 2>();
    auto context_view = contexts.accessor<std::int64_t, 1>();
    std::uniform_int_distribution<int> distribution(0, 1);
    for (std::int64_t sample = 0; sample < samples; ++sample) {
        const auto context = static_cast<std::int64_t>(distribution(trainer.rng().environment_episode()));
        context_view[sample] = context;
        observation_view[sample][0] = context == 0 ? -1.0F : 1.0F;
        observation_view[sample][1] = 1.0F;
    }
    return {observations, contexts};
}

torch::Tensor bandit_masks(std::int64_t samples)
{
    auto masks = torch::zeros({samples, kActionCount}, torch::kBool);
    masks.index_put_({torch::indexing::Slice(), torch::indexing::Slice(0, 2)}, true);
    return masks;
}

} // namespace

double evaluate_tiny_masked_bandit(PpoTrainer &trainer, std::int64_t samples)
{
    if (samples <= 0 || samples % 2 != 0) throw std::invalid_argument("bandit evaluation samples must be positive and even");
    auto observations = torch::zeros({samples, kStructuredFeatures}, torch::kFloat32);
    auto contexts = torch::empty({samples}, torch::kInt64);
    auto observation_view = observations.accessor<float, 2>();
    auto context_view = contexts.accessor<std::int64_t, 1>();
    for (std::int64_t sample = 0; sample < samples; ++sample) {
        const auto context = sample % 2;
        context_view[sample] = context;
        observation_view[sample][0] = context == 0 ? -1.0F : 1.0F;
        observation_view[sample][1] = 1.0F;
    }
    const auto result = trainer.act(observations, bandit_masks(samples), true);
    return (result.actions == contexts).to(torch::kFloat64).mean().item<double>();
}

TinyBanditResult run_tiny_masked_bandit(PpoTrainer &trainer, std::uint64_t additional_updates)
{
    if (additional_updates == 0) throw std::invalid_argument("bandit run requires at least one update");
    const auto &config = trainer.config();
    const auto samples = config.rollout_length * config.environment_count;
    TinyBanditResult result;
    result.initial_greedy_accuracy = evaluate_tiny_masked_bandit(trainer);
    double final_reward = 0.0;
    for (std::uint64_t update = 0; update < additional_updates; ++update) {
        auto [observations, contexts] = bandit_inputs(trainer, samples);
        auto masks = bandit_masks(samples);
        const auto behavior = trainer.act(observations, masks, false);
        auto rewards = torch::where(behavior.actions == contexts, torch::ones({samples}), -torch::ones({samples})).to(torch::kFloat64);
        final_reward = rewards.mean().item<double>();
        auto zero_masks = torch::zeros({config.rollout_length, config.environment_count}, torch::kFloat64);
        const auto gae = compute_gae(
            rewards.reshape({config.rollout_length, config.environment_count}),
            behavior.values.to(torch::kFloat64).reshape({config.rollout_length, config.environment_count}),
            torch::zeros({config.rollout_length, config.environment_count}, torch::kFloat64),
            zero_masks,
            zero_masks,
            config.gamma,
            config.gae_lambda);
        RolloutBatch rollout{
            observations,
            masks,
            behavior.actions,
            behavior.log_probabilities,
            behavior.values,
            normalize_advantages(gae.advantages).reshape({samples}).to(torch::kFloat32),
            gae.returns.reshape({samples}).to(torch::kFloat32),
        };
        result.final_update = trainer.update(rollout);
        trainer.counters().completed_episodes += static_cast<std::uint64_t>(samples);
        trainer.counters().simulation_ticks += static_cast<std::uint64_t>(samples);
    }
    result.final_greedy_accuracy = evaluate_tiny_masked_bandit(trainer);
    result.final_mean_reward = final_reward;
    result.updates = trainer.counters().completed_updates;
    result.environment_steps = trainer.counters().environment_steps;
    return result;
}

} // namespace openttd_rl::training
