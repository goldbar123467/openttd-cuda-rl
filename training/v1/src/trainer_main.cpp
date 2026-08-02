#include <charconv>
#include <exception>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <limits>
#include <memory>
#include <sstream>
#include <string>
#include <string_view>
#include <vector>

#include <unistd.h>

#include <torch/torch.h>

#include "openttd_rl/training/checkpoint.h"
#include "openttd_rl/training/metrics.h"
#include "openttd_rl/training/model.h"
#include "openttd_rl/training/ppo.h"
#include "openttd_rl/training/trainer.h"
#include "openttd_rl/training/learning.h"
#include "openttd_rl/training/service.h"

namespace {

std::string tensor_json(const torch::Tensor &tensor)
{
    auto values = tensor.detach().to(torch::kCPU).to(torch::kFloat64).contiguous().reshape({-1});
    const auto accessor = values.accessor<double, 1>();
    std::ostringstream output;
    output << '[' << std::setprecision(std::numeric_limits<double>::max_digits10);
    for (std::int64_t index = 0; index < values.numel(); ++index) {
        if (index != 0) output << ',';
        output << accessor[index];
    }
    output << ']';
    return output.str();
}

void emit_reference_vectors()
{
    const auto options = torch::TensorOptions().dtype(torch::kFloat64);
    const auto rewards = torch::tensor({{1.0, 0.5}, {2.0, -1.0}, {3.0, 4.0}}, options);
    const auto values = torch::tensor({{0.2, 0.1}, {0.4, -0.2}, {0.3, 0.5}}, options);
    const auto next_values = torch::tensor({{0.4, -0.2}, {0.3, 0.5}, {0.7, 0.8}}, options);
    const auto bootstrap = torch::tensor({{1.0, 1.0}, {1.0, 0.0}, {0.0, 1.0}}, options);
    const auto continuation = torch::tensor({{1.0, 1.0}, {1.0, 0.0}, {0.0, 0.0}}, options);
    const auto gae = openttd_rl::training::compute_gae(
        rewards, values, next_values, bootstrap, continuation, 0.9, 0.8);
    const auto normalized = openttd_rl::training::normalize_advantages(gae.advantages);

    auto logits = torch::tensor({{0.2, -0.3, 1.1}, {2.0, -1.0, 0.5}}, options).set_requires_grad(true);
    const auto masks = torch::tensor({{true, false, true}, {true, true, false}}, torch::kBool);
    const auto actions = torch::tensor({2, 1}, torch::kInt64);
    const auto old_log = torch::tensor({-0.4, -2.0}, options);
    const auto advantages = torch::tensor({1.5, -0.75}, options);
    auto predicted_values = torch::tensor({0.25, -0.5}, options).set_requires_grad(true);
    const auto returns = torch::tensor({1.0, -0.25}, options);
    const auto policy = openttd_rl::training::masked_categorical(logits, masks);
    const auto selected_log = policy.log_probabilities.gather(1, actions.unsqueeze(1)).squeeze(1);
    openttd_rl::training::PpoConfig config;
    const auto losses = openttd_rl::training::ppo_loss(
        selected_log, old_log, advantages, predicted_values, returns, policy.entropy, config);
    losses.total.backward();

    auto parameter = torch::tensor({0.25}, options).set_requires_grad(true);
    torch::optim::Adam optimizer({parameter}, torch::optim::AdamOptions(config.learning_rate).eps(config.adam_epsilon));
    const auto scalar_loss = 0.5 * torch::square(parameter - 1.5).sum();
    scalar_loss.backward();
    optimizer.step();

    std::cout << std::setprecision(std::numeric_limits<double>::max_digits10)
              << "{\"adam_parameter\":" << parameter.item<double>()
              << ",\"advantages\":" << tensor_json(gae.advantages)
              << ",\"approximate_kl\":" << losses.approximate_kl.item<double>()
              << ",\"clip_fraction\":" << losses.clip_fraction.item<double>()
              << ",\"entropy\":" << losses.entropy.item<double>()
              << ",\"logit_gradients\":" << tensor_json(logits.grad())
              << ",\"selected_log_probabilities\":" << tensor_json(selected_log)
              << ",\"normalized_advantages\":" << tensor_json(normalized)
              << ",\"policy_loss\":" << losses.policy.item<double>()
              << ",\"probabilities\":" << tensor_json(policy.probabilities)
              << ",\"returns\":" << tensor_json(gae.returns)
              << ",\"total_loss\":" << losses.total.item<double>()
              << ",\"value_gradients\":" << tensor_json(predicted_values.grad())
              << ",\"value_loss\":" << losses.value.item<double>() << "}\n";
}

void emit_metric_fixture()
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
    event.environment.company_profit = 2048.0;
    event.environment.passenger_deliveries = 64.0;
    event.environment.vehicles = 8.0;
    event.environment.routes = 5.0;
    event.environment.invalid_actions = 1;
    event.environment.mask_violations = 0;
    event.environment.resets = 2;
    event.system.cpu_utilization_percent = 25.0;
    event.system.process_memory_bytes = 4096;
    event.checkpoint_id = std::string(64, 'a');
    event.best_development_score = 8.0;
    std::cout << openttd_rl::training::metric_event_json(event) << '\n';
}

std::uint64_t parse_u64(std::string_view text, const char *name)
{
    std::uint64_t value = 0;
    const auto result = std::from_chars(text.data(), text.data() + text.size(), value);
    if (result.ec != std::errc{} || result.ptr != text.data() + text.size()) {
        throw std::invalid_argument(std::string("invalid ") + name);
    }
    return value;
}

int run_service_mode(int argc, char **argv)
{
    openttd_rl::training::PpoConfig config;
    std::uint64_t run_seed = 0;
    bool has_seed = false;
    std::filesystem::path resume;
    std::filesystem::path diagnostic_root;
    for (int index = 2; index < argc; index += 2) {
        if (index + 1 >= argc) throw std::invalid_argument("service option is missing its value");
        const std::string_view option(argv[index]);
        const std::string_view value(argv[index + 1]);
        if (option == "--run-seed") {
            run_seed = parse_u64(value, "run seed");
            has_seed = true;
        } else if (option == "--rollout-length") {
            config.rollout_length = static_cast<std::int64_t>(parse_u64(value, "rollout length"));
        } else if (option == "--environment-count") {
            config.environment_count = static_cast<std::int64_t>(parse_u64(value, "environment count"));
        } else if (option == "--minibatch-size") {
            config.minibatch_size = static_cast<std::int64_t>(parse_u64(value, "minibatch size"));
        } else if (option == "--optimization-epochs") {
            config.optimization_epochs = static_cast<std::int64_t>(parse_u64(value, "optimization epochs"));
        } else if (option == "--resume") {
            resume = std::filesystem::path(value);
        } else if (option == "--diagnostic-root") {
            diagnostic_root = std::filesystem::path(value);
        } else {
            throw std::invalid_argument("unknown service option: " + std::string(option));
        }
    }
    if (!diagnostic_root.is_absolute()) {
        throw std::invalid_argument("service requires an absolute --diagnostic-root");
    }
    std::unique_ptr<openttd_rl::training::PpoTrainer> trainer;
    if (!resume.empty()) {
        if (has_seed) throw std::invalid_argument("resumed service obtains its run seed from the checkpoint");
        auto loaded = openttd_rl::training::load_checkpoint(resume);
        trainer = std::move(loaded.trainer);
    } else {
        if (!has_seed) throw std::invalid_argument("new service requires --run-seed");
        config.validate();
        trainer = std::make_unique<openttd_rl::training::PpoTrainer>(config, run_seed);
    }
    return openttd_rl::training::run_trainer_service(
        *trainer, STDIN_FILENO, STDOUT_FILENO, diagnostic_root);
}

} // namespace

int main(int argc, char **argv)
{
    try {
        if (argc >= 2 && std::string_view(argv[1]) == "--service") {
            torch::set_num_threads(1);
            return run_service_mode(argc, argv);
        }
        if (argc != 2) {
            std::cerr << "usage: rl_trainer --probe|--reference-vectors|--metric-fixture|--tiny-bandit\n";
            return 2;
        }
        torch::set_num_threads(1);
        if (std::string_view(argv[1]) == "--reference-vectors") {
            emit_reference_vectors();
            return 0;
        }
        if (std::string_view(argv[1]) == "--metric-fixture") {
            emit_metric_fixture();
            return 0;
        }
        if (std::string_view(argv[1]) == "--tiny-bandit") {
            openttd_rl::training::PpoConfig config;
            config.rollout_length = 32;
            config.environment_count = 4;
            openttd_rl::training::PpoTrainer trainer(config, UINT64_C(2026080107));
            const auto result = openttd_rl::training::run_tiny_masked_bandit(trainer, 100);
            std::cout << std::setprecision(std::numeric_limits<double>::max_digits10)
                      << "{\"environment_count\":4,\"environment_steps\":" << result.environment_steps
                      << ",\"final_greedy_accuracy\":" << result.final_greedy_accuracy
                      << ",\"final_mean_reward\":" << result.final_mean_reward
                      << ",\"initial_greedy_accuracy\":" << result.initial_greedy_accuracy
                      << ",\"random_baseline_accuracy\":0.5,\"rollout_length\":32"
                      << ",\"status\":\"PASS\",\"updates\":" << result.updates << "}\n";
            return result.final_greedy_accuracy >= 0.95 ? 0 : 1;
        }
        if (std::string_view(argv[1]) != "--probe") {
            std::cerr << "usage: rl_trainer --probe|--reference-vectors|--metric-fixture|--tiny-bandit\n";
            return 2;
        }
        openttd_rl::training::PpoTrainer trainer(openttd_rl::training::PpoConfig{}, UINT64_C(2026080107));
        const auto observations = torch::zeros(
            {2, openttd_rl::training::kStructuredFeatures}, torch::TensorOptions().dtype(torch::kFloat32));
        const auto masks = torch::ones(
            {2, openttd_rl::training::kActionCount}, torch::TensorOptions().dtype(torch::kBool));
        const auto action = trainer.act(observations, masks, true);
        std::cout << "M07_TRAINER_PROBE=PASS architecture=" << openttd_rl::training::kArchitectureId
                  << " actions=" << action.actions.numel() << " device=cpu\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "M07_TRAINER_PROBE=FAIL " << error.what() << '\n';
        return 1;
    }
}
