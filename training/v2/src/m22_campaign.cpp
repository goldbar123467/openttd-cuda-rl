#include "openttd_rl/v2/m22_campaign.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <iomanip>
#include <random>
#include <sstream>
#include <stdexcept>
#include <utility>
#include <vector>

namespace openttd_rl::v2 {

namespace {

using torch::indexing::Slice;

constexpr std::array<std::uint32_t, 7> kStageWeights = {20, 15, 15, 15, 15, 10, 10};
const std::array<std::vector<std::uint8_t>, 7> kStagePrograms = {
    std::vector<std::uint8_t>{1},
    std::vector<std::uint8_t>{2},
    std::vector<std::uint8_t>{3, 4},
    std::vector<std::uint8_t>{5, 6},
    std::vector<std::uint8_t>{7, 8, 9, 10},
    std::vector<std::uint8_t>{11},
    std::vector<std::uint8_t>{12, 13, 14, 15, 16},
};
constexpr std::array<std::uint64_t, 7> kStageStarts = {0, 4, 8, 12, 16, 20, 24};

M22CompactBatch concatenate(const std::vector<M22CompactBatch> &items)
{
    std::vector<torch::Tensor> features;
    std::vector<torch::Tensor> masks;
    std::vector<torch::Tensor> hidden;
    std::vector<torch::Tensor> resets;
    for (const auto &item : items) {
        features.push_back(item.public_features);
        masks.push_back(item.program_mask);
        hidden.push_back(item.hidden_state);
        resets.push_back(item.recurrent_reset);
    }
    return {torch::cat(features), torch::cat(masks), torch::cat(hidden), torch::cat(resets)};
}

std::uint32_t introduced_programs(std::uint32_t stage)
{
    std::uint32_t result = 0;
    for (std::uint32_t index = 0; index <= stage; ++index) {
        result += static_cast<std::uint32_t>(kStagePrograms[index].size());
    }
    return result;
}

std::string retention_json(const M22RetentionResult &result)
{
    std::ostringstream output;
    output << std::setprecision(17)
           << "{\"accuracy\":" << result.accuracy
           << ",\"catastrophic_regression\":" << (result.catastrophic_regression ? "true" : "false")
           << ",\"checkpoint_allowed\":" << (result.checkpoint_allowed ? "true" : "false")
           << ",\"introduced_programs\":" << result.introduced_programs
           << ",\"mean_reward\":" << result.mean_reward
           << ",\"pass_mask\":" << result.pass_mask
           << ",\"passed_programs\":" << result.passed_programs
           << ",\"selection_eligible\":" << (result.selection_eligible ? "true" : "false")
           << ",\"stage\":" << result.stage
           << ",\"update\":" << result.update << '}';
    return output.str();
}

} // namespace

M22Campaign::M22Campaign(M22Corpus corpus, std::unique_ptr<M22Trainer> trainer) :
    corpus_(std::move(corpus)),
    trainer_(std::move(trainer)),
    hidden_state_(torch::zeros({8, kHiddenSize}, torch::kFloat32)),
    environment_case_cursor_(8, 0)
{
    if (!trainer_) throw std::invalid_argument("M22 campaign trainer is null");
    if (trainer_->config().parallel_environments != 8 || trainer_->config().rollout_steps != 16) {
        throw std::invalid_argument("M22 production campaign requires the frozen 16x8 rollout geometry");
    }
}

M22Campaign::M22Campaign(
    M22Corpus corpus,
    std::unique_ptr<M22Trainer> trainer,
    const M22CampaignCheckpointState &state) :
    corpus_(std::move(corpus)),
    trainer_(std::move(trainer)),
    hidden_state_(state.hidden_state.clone()),
    environment_case_cursor_(state.environment_case_cursor),
    curriculum_stage_(state.curriculum_stage),
    retention_pass_mask_(state.retention_pass_mask),
    retention_best_accuracy_(state.retention_best_accuracy),
    episode_(state.episode),
    transition_(state.transition),
    retention_history_json_(state.retention_history_json)
{
    if (!trainer_) throw std::invalid_argument("M22 resumed campaign trainer is null");
    if (trainer_->config().parallel_environments != 8 || trainer_->config().rollout_steps != 16 ||
        hidden_state_.sizes() != torch::IntArrayRef({8, kHiddenSize}) || environment_case_cursor_.size() != 8 ||
        transition_ != trainer_->counters().accepted_transitions) {
        throw std::invalid_argument("M22 resumed campaign state disagrees with its trainer boundary");
    }
}

std::uint32_t M22Campaign::stage_for_next_update() const noexcept
{
    const auto completed = trainer_->counters().completed_updates;
    std::uint32_t result = 0;
    for (std::uint32_t stage = 0; stage < kStageStarts.size(); ++stage) {
        if (completed >= kStageStarts[stage]) result = stage;
    }
    return result;
}

const M22CorpusEntry &M22Campaign::sample_training_entry()
{
    std::vector<double> weights;
    for (std::uint32_t stage = 0; stage <= curriculum_stage_; ++stage) {
        weights.push_back(static_cast<double>(kStageWeights[stage]));
    }
    std::discrete_distribution<std::size_t> choose_stage(weights.begin(), weights.end());
    const auto stage = choose_stage(trainer_->curriculum_rng());
    const auto &programs = kStagePrograms[stage];
    std::uniform_int_distribution<std::size_t> choose_program(0, programs.size() - 1);
    const auto program = programs[choose_program(trainer_->environment_rng())];
    return corpus_.entry(M22CorpusSplit::Training, program);
}

M22CampaignUpdateResult M22Campaign::run_update()
{
    const auto &config = trainer_->config();
    curriculum_stage_ = stage_for_next_update();
    std::vector<M22CompactBatch> compact_steps;
    std::vector<torch::Tensor> actions;
    std::vector<torch::Tensor> logs;
    std::vector<torch::Tensor> values;
    std::vector<torch::Tensor> rewards;
    auto bootstrap = torch::ones({config.rollout_steps, config.parallel_environments}, torch::kFloat32);
    auto continuation = torch::ones_like(bootstrap);
    double reward_sum = 0.0;
    std::uint64_t correct = 0;
    std::vector<const M22CorpusEntry *> current(8, nullptr);
    for (std::int64_t time = 0; time < config.rollout_steps; ++time) {
        const bool reset = time % kM22SequenceLength == 0;
        if (reset) {
            for (std::size_t environment = 0; environment < current.size(); ++environment) {
                current[environment] = &sample_training_entry();
                environment_case_cursor_[environment] = current[environment]->program;
                ++episode_;
            }
        }
        auto compact = m22_compact_from_entries(
            current,
            hidden_state_,
            torch::full({config.parallel_environments}, reset, torch::kBool));
        const auto action = trainer_->act(compact, false);
        auto step_rewards = torch::empty({config.parallel_environments}, torch::kFloat32);
        auto reward_view = step_rewards.accessor<float, 1>();
        const auto action_view = action.actions.accessor<std::int64_t, 1>();
        for (std::int64_t environment = 0; environment < config.parallel_environments; ++environment) {
            const auto &entry = *current[static_cast<std::size_t>(environment)];
            const double reward = entry.rewards[static_cast<std::size_t>(action_view[environment])];
            reward_view[environment] = static_cast<float>(reward);
            reward_sum += reward;
            correct += action_view[environment] == entry.program ? 1U : 0U;
        }
        compact_steps.push_back(std::move(compact));
        actions.push_back(action.actions);
        logs.push_back(action.log_probabilities);
        values.push_back(action.values);
        rewards.push_back(step_rewards);
        hidden_state_ = action.next_hidden;
        if ((time + 1) % kM22SequenceLength == 0) {
            bootstrap.index_put_({time, Slice()}, 0.0F);
            continuation.index_put_({time, Slice()}, 0.0F);
        }
    }
    const auto value_matrix = torch::cat(values).reshape({config.rollout_steps, config.parallel_environments});
    auto next_values = torch::zeros_like(value_matrix);
    next_values.index_put_({Slice(0, config.rollout_steps - 1), Slice()}, value_matrix.index({Slice(1), Slice()}));
    const auto gae = m22_compute_gae(
        torch::cat(rewards).reshape({config.rollout_steps, config.parallel_environments}),
        value_matrix,
        next_values,
        bootstrap,
        continuation,
        config.gamma,
        config.gae_lambda);
    M22RolloutBatch rollout{
        concatenate(compact_steps), torch::cat(actions), torch::cat(logs), value_matrix.flatten(),
        m22_normalize_advantages(gae.advantages.flatten()), gae.returns.flatten(),
    };
    M22CampaignUpdateResult result;
    result.trainer = trainer_->update(rollout);
    transition_ += static_cast<std::uint64_t>(rollout.size());
    if (transition_ != trainer_->counters().accepted_transitions) {
        throw std::logic_error("M22 campaign/trainer transition counters diverged");
    }
    result.stage = curriculum_stage_;
    result.mean_rollout_reward = reward_sum / static_cast<double>(rollout.size());
    result.correct_program_fraction = static_cast<double>(correct) / static_cast<double>(rollout.size());
    if (result.trainer.update % 4U == 0U) {
        result.retention_ran = true;
        result.retention = evaluate_development();
    }
    return result;
}

M22RetentionResult M22Campaign::evaluate_development()
{
    const auto count = introduced_programs(curriculum_stage_);
    std::vector<const M22CorpusEntry *> entries;
    for (std::uint32_t program = 1; program <= count; ++program) {
        entries.push_back(&corpus_.entry(M22CorpusSplit::Development, program));
    }
    const auto compact = m22_compact_from_entries(
        entries,
        torch::zeros({static_cast<std::int64_t>(entries.size()), kHiddenSize}, torch::kFloat32),
        torch::ones({static_cast<std::int64_t>(entries.size())}, torch::kBool));
    const auto action = trainer_->act(compact, true);
    const auto action_view = action.actions.accessor<std::int64_t, 1>();
    std::uint32_t passed = 0;
    std::uint32_t pass_mask = 0;
    double reward = 0.0;
    for (std::size_t index = 0; index < entries.size(); ++index) {
        const auto &entry = *entries[index];
        const auto selected = action_view[static_cast<std::int64_t>(index)];
        reward += entry.rewards[static_cast<std::size_t>(selected)];
        if (selected == entry.program) {
            ++passed;
            pass_mask |= UINT32_C(1) << entry.program;
        }
    }
    M22RetentionResult result;
    result.update = trainer_->counters().completed_updates;
    result.stage = curriculum_stage_;
    result.introduced_programs = count;
    result.passed_programs = passed;
    result.pass_mask = pass_mask;
    result.accuracy = static_cast<double>(passed) / static_cast<double>(count);
    result.mean_reward = reward / static_cast<double>(count);
    result.catastrophic_regression = (retention_pass_mask_ & ~pass_mask) != 0 ||
        retention_best_accuracy_ - result.accuracy > 0.05;
    result.checkpoint_allowed = !result.catastrophic_regression;
    result.selection_eligible = result.checkpoint_allowed && passed == count;
    retention_pass_mask_ |= pass_mask;
    retention_best_accuracy_ = std::max(retention_best_accuracy_, result.accuracy);
    last_retention_ = result;
    append_retention(result);
    return result;
}

void M22Campaign::append_retention(const M22RetentionResult &result)
{
    constexpr std::string_view empty = "{\"checks\":[]}";
    constexpr std::string_view suffix = "]}";
    if (retention_history_json_ == empty) {
        retention_history_json_ = "{\"checks\":[" + retention_json(result) + "]}";
        return;
    }
    if (!retention_history_json_.starts_with("{\"checks\":[") || !retention_history_json_.ends_with(suffix)) {
        throw std::invalid_argument("M22 retention history checkpoint text is malformed");
    }
    retention_history_json_.erase(retention_history_json_.size() - suffix.size());
    retention_history_json_ += ',' + retention_json(result) + "]}";
}

M22CampaignCheckpointState M22Campaign::checkpoint_state() const
{
    if (last_retention_.update != trainer_->counters().completed_updates || last_retention_.update % 4U != 0U) {
        throw std::logic_error("M22 checkpoint requested outside a completed retention boundary");
    }
    std::ostringstream selection;
    selection << std::setprecision(17)
              << "{\"accuracy\":" << last_retention_.accuracy
              << ",\"eligible\":" << (last_retention_.selection_eligible ? "true" : "false")
              << ",\"mean_reward\":" << last_retention_.mean_reward
              << ",\"passed_programs\":" << last_retention_.passed_programs
              << ",\"stage\":" << last_retention_.stage
              << ",\"update\":" << last_retention_.update << '}';
    return {
        torch::zeros({kM22CompactFeatures}, torch::kFloat32),
        torch::ones({kM22CompactFeatures}, torch::kFloat32),
        transition_,
        hidden_state_.clone(),
        environment_case_cursor_,
        curriculum_stage_,
        retention_pass_mask_,
        retention_best_accuracy_,
        episode_,
        transition_,
        retention_history_json_,
        selection.str(),
    };
}

std::string m22_campaign_update_json(const M22CampaignUpdateResult &result)
{
    std::ostringstream output;
    output << std::setprecision(17)
           << "{\"correct_program_fraction\":" << result.correct_program_fraction
           << ",\"entropy\":" << result.trainer.entropy
           << ",\"gradient_norm\":" << result.trainer.gradient_norm
           << ",\"mean_rollout_reward\":" << result.mean_rollout_reward
           << ",\"policy_loss\":" << result.trainer.policy_loss
           << ",\"retention_ran\":" << (result.retention_ran ? "true" : "false");
    if (result.retention_ran) output << ",\"retention\":" << retention_json(result.retention);
    output << ",\"stage\":" << result.stage
           << ",\"transitions\":" << result.trainer.transitions
           << ",\"update\":" << result.trainer.update
           << ",\"value_loss\":" << result.trainer.value_loss << '}';
    return output.str();
}

} // namespace openttd_rl::v2
