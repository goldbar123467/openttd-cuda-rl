#include <algorithm>
#include <cmath>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

#include <unistd.h>

#include <torch/torch.h>
#include <torch/nn/utils/clip_grad.h>

#include "openttd_rl/training/checkpoint.h"
#include "openttd_rl/training/metrics.h"
#include "openttd_rl/training/model.h"
#include "openttd_rl/training/ppo.h"
#include "openttd_rl/training/rng.h"
#include "openttd_rl/training/trainer.h"

namespace {

void check(bool condition, const std::string &message)
{
    if (!condition) throw std::runtime_error(message);
}

void near(double actual, double expected, double tolerance, const std::string &message)
{
    if (!std::isfinite(actual) || std::abs(actual - expected) > tolerance) {
        throw std::runtime_error(message + ": actual=" + std::to_string(actual) + " expected=" + std::to_string(expected));
    }
}

void test_gae()
{
    const auto options = torch::TensorOptions().dtype(torch::kFloat64);
    const auto rewards = torch::tensor({{1.0, 0.5}, {2.0, -1.0}, {3.0, 4.0}}, options);
    const auto values = torch::tensor({{0.2, 0.1}, {0.4, -0.2}, {0.3, 0.5}}, options);
    const auto next_values = torch::tensor({{0.4, -0.2}, {0.3, 0.5}, {0.7, 0.8}}, options);
    const auto bootstrap = torch::tensor({{1.0, 1.0}, {1.0, 0.0}, {0.0, 1.0}}, options);
    const auto continuation = torch::tensor({{1.0, 1.0}, {1.0, 0.0}, {0.0, 0.0}}, options);
    const auto result = openttd_rl::training::compute_gae(
        rewards, values, next_values, bootstrap, continuation, 0.9, 0.8);
    const auto expected_advantages = torch::tensor({{3.90608, -0.356}, {3.814, -0.8}, {2.7, 4.22}}, options);
    check(torch::allclose(result.advantages, expected_advantages, 1e-12, 1e-12), "fixed GAE vector mismatch");
    check(torch::allclose(result.returns, expected_advantages + values, 1e-12, 1e-12), "fixed return vector mismatch");
}

void test_advantage_normalization()
{
    const auto constant = torch::full({7}, 3.25, torch::TensorOptions().dtype(torch::kFloat64));
    check(torch::equal(openttd_rl::training::normalize_advantages(constant), torch::zeros_like(constant)),
        "zero-variance advantages must become exact zeros");
    const auto values = torch::tensor({-1.0, 1.0, 3.0}, torch::TensorOptions().dtype(torch::kFloat64));
    const auto normalized = openttd_rl::training::normalize_advantages(values);
    near(normalized.mean().item<double>(), 0.0, 1e-15, "normalized mean");
    near(torch::mean(torch::square(normalized)).item<double>(), 1.0, 1e-8, "population variance");
}

void test_masked_policy()
{
    const auto logits = torch::tensor({{0.0, 1000.0, 2.0}, {-50.0, 50.0, 0.0}}, torch::kFloat64);
    const auto masks = torch::tensor({{true, false, true}, {false, true, false}}, torch::kBool);
    const auto policy = openttd_rl::training::masked_categorical(logits, masks);
    check(policy.probabilities[0][1].item<double>() == 0.0, "illegal action received probability");
    check(policy.probabilities[1][0].item<double>() == 0.0 && policy.probabilities[1][2].item<double>() == 0.0,
        "single legal mask leaked probability");
    check(policy.probabilities[1][1].item<double>() == 1.0, "single legal action is not certain");
    check(policy.entropy[1].item<double>() == 0.0, "single-action entropy must be zero");
    bool rejected = false;
    try {
        (void)openttd_rl::training::masked_categorical(logits.index({0}).unsqueeze(0), torch::zeros({1, 3}, torch::kBool));
    } catch (const std::invalid_argument &) {
        rejected = true;
    }
    check(rejected, "all-illegal mask was accepted");
}

void test_clipped_loss()
{
    openttd_rl::training::PpoConfig config;
    const auto old_log = torch::zeros({5}, torch::kFloat64);
    const auto ratios = torch::tensor({0.5, 0.9, 1.0, 1.1, 1.5}, torch::kFloat64);
    const auto new_log = torch::log(ratios);
    const auto advantages = torch::tensor({1.0, -1.0, 0.0, 2.0, -2.0}, torch::kFloat64);
    const auto values = torch::tensor({1.0, 2.0, 3.0, 4.0, 5.0}, torch::kFloat64);
    const auto returns = torch::tensor({0.0, 2.0, 4.0, 4.0, 7.0}, torch::kFloat64);
    const auto entropy = torch::tensor({0.1, 0.2, 0.3, 0.4, 0.5}, torch::kFloat64);
    const auto loss = openttd_rl::training::ppo_loss(new_log, old_log, advantages, values, returns, entropy, config);
    double surrogate_sum = 0.0;
    for (std::int64_t index = 0; index < 5; ++index) {
        const double ratio = ratios[index].item<double>();
        const double advantage = advantages[index].item<double>();
        const double clipped = std::clamp(ratio, 0.8, 1.2);
        surrogate_sum += std::min(ratio * advantage, clipped * advantage);
    }
    const double expected_policy = -surrogate_sum / 5.0;
    near(loss.policy.item<double>(), expected_policy, 1e-12, "clipped policy loss");
    near(loss.value.item<double>(), 1.2, 1e-12, "plain MSE value loss");
    near(loss.entropy.item<double>(), 0.3, 1e-12, "masked entropy reduction");
    near(loss.total.item<double>(), expected_policy + 0.5 * 1.2 - 0.01 * 0.3, 1e-12, "total PPO loss");
}

void test_rng_and_minibatches()
{
    openttd_rl::training::RngStreams first(42);
    openttd_rl::training::RngStreams second(42);
    check(first.ledger().stream_seeds == second.ledger().stream_seeds, "seed derivation is not repeatable");
    for (std::size_t left = 0; left < first.ledger().stream_seeds.size(); ++left) {
        for (std::size_t right = left + 1; right < first.ledger().stream_seeds.size(); ++right) {
            check(first.ledger().stream_seeds[left] != first.ledger().stream_seeds[right], "RNG streams are not independent");
        }
    }
    const auto first_batches = openttd_rl::training::minibatch_indices(16, 4, first.minibatch_shuffle());
    const auto second_batches = openttd_rl::training::minibatch_indices(16, 4, second.minibatch_shuffle());
    check(first_batches == second_batches, "seeded shuffle differs");
    std::vector<std::int64_t> flattened;
    for (const auto &batch : first_batches) flattened.insert(flattened.end(), batch.begin(), batch.end());
    std::sort(flattened.begin(), flattened.end());
    for (std::int64_t index = 0; index < 16; ++index) check(flattened[static_cast<std::size_t>(index)] == index, "shuffle coverage mismatch");
    const auto states = first.mutable_states();
    const auto expected = first.minibatch_shuffle()();
    first.restore_mutable_states(states);
    check(first.minibatch_shuffle()() == expected, "RNG state round trip mismatch");
}

openttd_rl::training::RolloutBatch make_rollout(
    openttd_rl::training::PpoTrainer &trainer,
    const openttd_rl::training::PpoConfig &config)
{
    const auto samples = config.rollout_length * config.environment_count;
    auto observations = torch::arange(
        samples * openttd_rl::training::kStructuredFeatures,
        torch::TensorOptions().dtype(torch::kFloat32)).reshape({samples, openttd_rl::training::kStructuredFeatures});
    observations = torch::sin(observations * 0.013F);
    auto masks = torch::ones({samples, openttd_rl::training::kActionCount}, torch::kBool);
    masks.index_put_({torch::indexing::Slice(), torch::indexing::Slice(2, torch::indexing::None)}, false);
    const auto behavior = trainer.act(observations, masks, false);
    auto rewards = torch::where(behavior.actions == 0, torch::ones({samples}), -torch::ones({samples})).to(torch::kFloat64);
    auto values = behavior.values.to(torch::kFloat64);
    auto next_values = torch::roll(values, -config.environment_count, 0);
    auto bootstrap = torch::ones({config.rollout_length, config.environment_count}, torch::kFloat64);
    auto continuation = torch::ones_like(bootstrap);
    continuation.index_put_({config.rollout_length - 1, torch::indexing::Slice()}, 0.0);
    next_values.index_put_({torch::indexing::Slice(samples - config.environment_count, torch::indexing::None)}, 0.0);
    bootstrap.index_put_({config.rollout_length - 1, torch::indexing::Slice()}, 0.0);
    const auto gae = openttd_rl::training::compute_gae(
        rewards.reshape({config.rollout_length, config.environment_count}),
        values.reshape({config.rollout_length, config.environment_count}),
        next_values.reshape({config.rollout_length, config.environment_count}),
        bootstrap,
        continuation,
        config.gamma,
        config.gae_lambda);
    return {
        observations,
        masks,
        behavior.actions,
        behavior.log_probabilities,
        behavior.values,
        openttd_rl::training::normalize_advantages(gae.advantages).reshape({samples}).to(torch::kFloat32),
        gae.returns.reshape({samples}).to(torch::kFloat32),
    };
}

void test_optimizer_update_and_evaluation()
{
    openttd_rl::training::PpoConfig config;
    config.rollout_length = 8;
    config.environment_count = 2;
    config.minibatch_size = 4;
    config.optimization_epochs = 2;
    openttd_rl::training::PpoTrainer trainer(config, 501);
    const auto rollout = make_rollout(trainer, config);
    std::vector<torch::Tensor> before;
    for (const auto &parameter : trainer.model()->parameters()) before.push_back(parameter.detach().clone());
    const auto metrics = trainer.update(rollout);
    check(metrics.update == 1 && metrics.samples == 16, "trainer counters did not advance at completed update boundary");
    check(std::isfinite(metrics.policy_loss) && std::isfinite(metrics.value_loss) &&
        std::isfinite(metrics.entropy) && std::isfinite(metrics.gradient_norm), "update metrics are nonfinite");
    bool changed = false;
    const auto after = trainer.model()->parameters();
    for (std::size_t index = 0; index < before.size(); ++index) {
        changed = changed || !torch::equal(before[index], after[index]);
    }
    check(changed, "optimizer update did not change parameters");

    const auto counters = trainer.counters();
    const auto deterministic_first = trainer.act(rollout.observations, rollout.legal_masks, true);
    const auto deterministic_second = trainer.act(rollout.observations, rollout.legal_masks, true);
    check(torch::equal(deterministic_first.actions, deterministic_second.actions), "greedy evaluation is not repeatable");
    check(trainer.counters().completed_updates == counters.completed_updates &&
        trainer.counters().environment_steps == counters.environment_steps, "evaluation mutated trainer counters");

    for (auto &parameter : trainer.model()->parameters()) parameter.mutable_grad() = torch::full_like(parameter, 1000.0);
    const double norm = torch::nn::utils::clip_grad_norm_(trainer.model()->parameters(), config.max_gradient_norm, 2.0, true);
    check(norm > config.max_gradient_norm, "synthetic gradient did not exercise clipping");
    double clipped_square_sum = 0.0;
    for (const auto &parameter : trainer.model()->parameters()) {
        clipped_square_sum += torch::sum(torch::square(parameter.grad())).item<double>();
    }
    check(std::sqrt(clipped_square_sum) <= config.max_gradient_norm + 1e-5, "global gradient norm was not clipped");
}

void test_checkpoint_recovery_and_corruption(const std::filesystem::path &temporary_root)
{
    openttd_rl::training::PpoConfig config;
    config.rollout_length = 8;
    config.environment_count = 2;
    config.minibatch_size = 4;
    config.optimization_epochs = 2;
    openttd_rl::training::PpoTrainer uninterrupted(config, 777);
    const auto rollout = make_rollout(uninterrupted, config);
    (void)uninterrupted.update(rollout);
    uninterrupted.counters().simulation_ticks = 2048;
    uninterrupted.counters().completed_episodes = 3;
    const auto checkpoint = openttd_rl::training::save_checkpoint(
        temporary_root / "checkpoints",
        uninterrupted,
        {"native-test", "0123456789abcdef", "m06-source", "", "{\"mean_return\":1.25}"});
    check(checkpoint.checkpoint_id.size() == 64 && checkpoint.path.filename() == checkpoint.checkpoint_id,
        "checkpoint is not content addressed");
    bool overwrite_rejected = false;
    try {
        (void)openttd_rl::training::save_checkpoint(
            temporary_root / "checkpoints",
            uninterrupted,
            {"native-test", "0123456789abcdef", "m06-source", "", "{\"mean_return\":1.25}"});
    } catch (const std::runtime_error &) {
        overwrite_rejected = true;
    }
    check(overwrite_rejected, "checkpoint writer overwrote an existing identity");

    auto loaded = openttd_rl::training::load_checkpoint(checkpoint.path);
    check(loaded.checkpoint_id == checkpoint.checkpoint_id, "loaded checkpoint identity changed");
    check(loaded.provenance.development_evaluation_json == "{\"mean_return\":1.25}",
        "checkpoint development evaluation metadata did not round trip");
    check(loaded.trainer->counters().completed_updates == 1 && loaded.trainer->counters().simulation_ticks == 2048 &&
        loaded.trainer->counters().completed_episodes == 3, "checkpoint counters did not round trip");
    const auto expected_greedy = uninterrupted.act(rollout.observations, rollout.legal_masks, true);
    const auto loaded_greedy = loaded.trainer->act(rollout.observations, rollout.legal_masks, true);
    check(torch::equal(expected_greedy.actions, loaded_greedy.actions) &&
        torch::equal(expected_greedy.logits, loaded_greedy.logits) &&
        torch::equal(expected_greedy.values, loaded_greedy.values), "checkpoint inference did not round trip exactly");
    const auto expected_sample = uninterrupted.act(rollout.observations, rollout.legal_masks, false);
    const auto loaded_sample = loaded.trainer->act(rollout.observations, rollout.legal_masks, false);
    check(torch::equal(expected_sample.actions, loaded_sample.actions), "checkpoint action RNG state did not round trip");
    const auto expected_metrics = uninterrupted.update(rollout);
    const auto loaded_metrics = loaded.trainer->update(rollout);
    near(loaded_metrics.policy_loss, expected_metrics.policy_loss, 0.0, "resumed policy loss differs");
    near(loaded_metrics.value_loss, expected_metrics.value_loss, 0.0, "resumed value loss differs");
    const auto uninterrupted_parameters = uninterrupted.model()->parameters();
    const auto loaded_parameters = loaded.trainer->model()->parameters();
    for (std::size_t index = 0; index < uninterrupted_parameters.size(); ++index) {
        check(torch::equal(uninterrupted_parameters[index], loaded_parameters[index]), "resumed parameter differs");
    }

    const auto corrupt = temporary_root / checkpoint.checkpoint_id;
    std::filesystem::copy(checkpoint.path, corrupt, std::filesystem::copy_options::recursive);
    {
        std::fstream model(corrupt / "model.pt", std::ios::binary | std::ios::in | std::ios::out);
        char byte = 0;
        model.read(&byte, 1);
        byte ^= 1;
        model.seekp(0);
        model.write(&byte, 1);
    }
    bool corruption_rejected = false;
    try {
        (void)openttd_rl::training::load_checkpoint(corrupt);
    } catch (const std::invalid_argument &) {
        corruption_rejected = true;
    }
    check(corruption_rejected, "corrupt checkpoint tensor payload was accepted");
}

void test_metrics_monitor_and_numerical_diagnostic(const std::filesystem::path &temporary_root)
{
    openttd_rl::training::MetricEvent event;
    event.sequence = 4;
    event.unix_time_ns = 123;
    event.elapsed_ns = 456000000;
    event.steps_per_second = 1122.8070175438597;
    event.run = {"test-run", "abcdef", "15.3", "m06-v1", 99, 2, "cpu"};
    event.counters = {4, 512, 65536, 2, 512};
    event.training = {0.1, 0.2, 0.3, 0.004, 0.05, 0.49, 0.6, 0.0003, 4, 512};
    event.environment.mean_episode_return = 7.5;
    event.environment.mean_episode_length = 128.0;
    event.environment.invalid_actions = 1;
    event.environment.resets = 2;
    event.system.process_memory_bytes = 4096;
    event.checkpoint_id = std::string(64, 'a');
    event.best_development_score = 8.0;
    openttd_rl::training::JsonlMetricSink sink(temporary_root / "metrics.jsonl", true);
    const auto expected_line = sink.write(event);
    std::ifstream input(temporary_root / "metrics.jsonl");
    std::string observed_line;
    std::getline(input, observed_line);
    check(observed_line == expected_line, "structured metric sink changed the authoritative event");
    check(observed_line.find("\"gpu_available\":false") != std::string::npos &&
        observed_line.find("\"gpu_utilization_percent\":null") != std::string::npos,
        "missing GPU telemetry was fabricated or coerced to zero");
    const auto wide = openttd_rl::training::render_terminal_monitor(event, 140);
    const auto compact = openttd_rl::training::render_terminal_monitor(event, 80);
    check(wide.find("steps 512") != std::string::npos && wide.find("return 7.500") != std::string::npos,
        "wide monitor did not render logged sources");
    check(compact.find("step=512") != std::string::npos && compact.find('\x1b') == std::string::npos,
        "compact monitor is not stream-safe");

    const auto diagnostic = openttd_rl::training::write_numerical_diagnostic(
        temporary_root / "diagnostics", event.counters, "policy_logits", "injected nonfinite");
    check(std::filesystem::is_regular_file(diagnostic / "diagnostic.json") &&
        !std::filesystem::exists(diagnostic / "model.pt"), "numerical diagnostic published a normal checkpoint");
    openttd_rl::training::PpoTrainer trainer(openttd_rl::training::PpoConfig{}, 123);
    bool nonfinite_rejected = false;
    try {
        auto observations = torch::zeros({1, openttd_rl::training::kStructuredFeatures}, torch::kFloat32);
        observations.index_put_({0, 0}, std::numeric_limits<float>::quiet_NaN());
        (void)trainer.act(observations, torch::ones({1, openttd_rl::training::kActionCount}, torch::kBool), true);
    } catch (const std::runtime_error &) {
        nonfinite_rejected = true;
    }
    check(nonfinite_rejected, "nonfinite observation was accepted");
}

} // namespace

int main()
{
    try {
        torch::set_num_threads(1);
        test_gae();
        test_advantage_normalization();
        test_masked_policy();
        test_clipped_loss();
        test_rng_and_minibatches();
        test_optimizer_update_and_evaluation();
        const auto temporary_root = std::filesystem::temp_directory_path() /
            ("openttd-rl-m07-native-tests-" + std::to_string(::getpid()));
        std::error_code ignored;
        std::filesystem::remove_all(temporary_root, ignored);
        std::filesystem::create_directory(temporary_root);
        try {
            test_checkpoint_recovery_and_corruption(temporary_root);
            test_metrics_monitor_and_numerical_diagnostic(temporary_root);
        } catch (...) {
            std::filesystem::remove_all(temporary_root, ignored);
            throw;
        }
        std::filesystem::remove_all(temporary_root, ignored);
        std::cout << "M07_NATIVE_TESTS=PASS tests=8\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "M07_NATIVE_TESTS=FAIL " << error.what() << '\n';
        return 1;
    }
}
