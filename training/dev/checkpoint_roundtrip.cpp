#include "live_checkpoint.h"
#include <ATen/Context.h>
#include <filesystem>
#include <iostream>
#include <iomanip>
#include <stdexcept>
#include <torch/cuda.h>
#include <unistd.h>

namespace {
void check(bool condition, const char *message)
{
    if (!condition) throw std::runtime_error(message);
}

void test(const torch::Device &device, openttd_rl::training::ArchitectureKind architecture,
          const std::filesystem::path &root)
{
    using namespace openttd_rl::training;
    using namespace openttd_rl::development;
    PpoConfig config;
    config.rollout_length = 4;
    config.minibatch_size = 2;
    config.optimization_epochs = 2;
    MultiModalPpoTrainer original(config, 123, architecture, device);
    const auto structured = torch::full({4, kStructuredFeatures}, .25F);
    const auto spatial = torch::full({4, kSpatialChannels, kSpatialHeight, kSpatialWidth}, .25F);
    const auto masks = torch::ones({4, kActionCount}, torch::kBool);
    auto rollout = [&](MultiModalPpoTrainer &trainer) {
        const auto a = trainer.act(structured, spatial, masks, false);
        return MultiModalRolloutBatch{structured, spatial, masks, a.actions, a.log_probabilities, a.values,
            torch::tensor({-1.F, 1.F, -.5F, .5F}), a.values + .5F};
    };
    (void)original.update(rollout(original));
    (void)original.rng().environment_episode()();
    original.model()->eval();
    const auto cpu_rng = at::globalContext().defaultGenerator(torch::kCPU).get_state().clone();
    const auto device_rng = at::globalContext().defaultGenerator(device).get_state().clone();
    const auto path = root / (std::string(architecture_name(architecture)) + ".pt");
    save_live_checkpoint(path, original);
    check(torch::equal(cpu_rng, at::globalContext().defaultGenerator(torch::kCPU).get_state()), "save advanced CPU RNG");
    check(torch::equal(device_rng, at::globalContext().defaultGenerator(device).get_state()), "save advanced device RNG");
    bool rejected = false;
    try { save_live_checkpoint(path, original); } catch (const std::exception &) { rejected = true; }
    check(rejected, "save overwrote existing checkpoint");
    const auto expected_cpu_random = torch::rand({8});
    const auto expected_device_random = torch::rand({8}, torch::TensorOptions().device(device));
    const auto expected_rollout = rollout(original);
    const auto expected_metrics = original.update(expected_rollout);
    const auto expected_rng = original.rng().mutable_states();
    MultiModalPpoTrainer resumed(config, 123, architecture, device);
    load_live_checkpoint(path, resumed);
    check(!resumed.model()->is_training(), "model mode not restored");
    check(torch::equal(expected_cpu_random, torch::rand({8})), "CPU Torch RNG not restored");
    check(torch::equal(expected_device_random, torch::rand({8}, torch::TensorOptions().device(device))), "device Torch RNG not restored");
    const auto actual_rollout = rollout(resumed);
    check(torch::equal(expected_rollout.actions, actual_rollout.actions), "sampled actions diverged");
    check(torch::equal(expected_rollout.old_log_probabilities, actual_rollout.old_log_probabilities), "behavior probabilities diverged");
    check(torch::equal(expected_rollout.old_values, actual_rollout.old_values), "values diverged");
    const auto actual_metrics = resumed.update(actual_rollout);
    if (actual_metrics.policy_loss != expected_metrics.policy_loss || actual_metrics.value_loss != expected_metrics.value_loss ||
        actual_metrics.gradient_norm != expected_metrics.gradient_norm) {
        std::cerr << std::setprecision(17) << "architecture=" << architecture_name(architecture)
                  << " policy=" << expected_metrics.policy_loss << '/' << actual_metrics.policy_loss
                  << " value=" << expected_metrics.value_loss << '/' << actual_metrics.value_loss
                  << " grad=" << expected_metrics.gradient_norm << '/' << actual_metrics.gradient_norm << '\n';
    }
    check(actual_metrics.policy_loss == expected_metrics.policy_loss && actual_metrics.value_loss == expected_metrics.value_loss &&
          actual_metrics.gradient_norm == expected_metrics.gradient_norm, "continued optimizer metrics diverged");
    check(resumed.counters().completed_updates == 2 && resumed.counters().accepted_samples == 8, "counters not restored");
    check(resumed.rng().mutable_states() == expected_rng, "native RNG streams diverged");
    const auto expected_parameters = original.model()->parameters();
    const auto actual_parameters = resumed.model()->parameters();
    for (std::size_t i = 0; i < expected_parameters.size(); ++i) {
        check(torch::equal(expected_parameters[i], actual_parameters[i]), "continued parameters differ bitwise");
    }
    // Subsequent steps require the restored Adam moments to remain attached to live parameters.
    (void)original.update(rollout(original));
    (void)resumed.update(rollout(resumed));
    for (std::size_t i = 0; i < expected_parameters.size(); ++i) {
        check(torch::equal(expected_parameters[i], actual_parameters[i]), "second continued update diverged");
    }
    MultiModalPpoTrainer wrong_seed(config, 124, architecture, device);
    rejected = false;
    try { load_live_checkpoint(path, wrong_seed); } catch (const std::exception &) { rejected = true; }
    check(rejected, "checkpoint accepted mismatched seed");
    config.entropy_coefficient = .05;
    MultiModalPpoTrainer wrong_entropy(config, 123, architecture, device);
    rejected = false;
    try { load_live_checkpoint(path, wrong_entropy); } catch (const std::exception &) { rejected = true; }
    check(rejected, "checkpoint accepted mismatched entropy coefficient");
    config.entropy_coefficient = .01;
    config.gae_lambda = 1.0;
    MultiModalPpoTrainer wrong_lambda(config, 123, architecture, device);
    rejected = false;
    try { load_live_checkpoint(path, wrong_lambda); } catch (const std::exception &) { rejected = true; }
    check(rejected, "checkpoint accepted mismatched GAE lambda");
    config.gae_lambda = .95;
    config.gamma = .9;
    MultiModalPpoTrainer wrong_config(config, 123, architecture, device);
    rejected = false;
    try { load_live_checkpoint(path, wrong_config); } catch (const std::exception &) { rejected = true; }
    check(rejected, "checkpoint accepted mismatched PPO config");
}
}

int main(int argc, char **argv)
{
    const auto root = std::filesystem::temp_directory_path() / ("rl-dev-checkpoint-" + std::to_string(::getpid()));
    try {
        check(argc == 2, "usage: rl_checkpoint_roundtrip cpu|cuda:0");
        const std::string selected(argv[1]);
        check(selected == "cpu" || selected == "cuda:0", "invalid device");
        check(selected == "cpu" || torch::cuda::is_available(), "CUDA requested but unavailable");
        torch::set_num_threads(1);
        at::globalContext().setDeterministicCuDNN(true);
        check(std::filesystem::create_directory(root), "test directory exists");
        for (const auto architecture : {openttd_rl::training::ArchitectureKind::StructuredMlp,
            openttd_rl::training::ArchitectureKind::SpatialCnn, openttd_rl::training::ArchitectureKind::CombinedCnnMlp}) {
            test(torch::Device(selected), architecture, root);
        }
        std::filesystem::remove_all(root);
        std::cout << "CHECKPOINT_ROUNDTRIP=PASS device=" << selected << " architectures=3 exact_continuation=true\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "CHECKPOINT_ROUNDTRIP=FAIL " << error.what() << '\n';
        return 1;
    }
}
