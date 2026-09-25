#include "openttd_rl/training/multimodal_trainer.h"
#include <ATen/Context.h>
#include <algorithm>
#include <iostream>
#include <stdexcept>
#include <torch/cuda.h>

namespace {
void check(bool condition, const char *message)
{
    if (!condition) throw std::runtime_error(message);
}

void test(const torch::Device &device, openttd_rl::training::ArchitectureKind architecture)
{
    using namespace openttd_rl::training;
    PpoConfig config;
    config.rollout_length = 8;
    config.environment_count = 1;
    config.minibatch_size = 4; // Corruption below is in the second audit chunk.
    config.optimization_epochs = 1;
    MultiModalPpoTrainer trainer(config, 725, architecture, device);
    const auto structured = torch::arange(8 * kStructuredFeatures, torch::kFloat32)
        .reshape({8, kStructuredFeatures}).sin();
    const auto spatial = torch::full({8, kSpatialChannels, kSpatialHeight, kSpatialWidth}, .25F);
    auto masks = torch::ones({8, kActionCount}, torch::kBool);
    masks.select(1, 5).fill_(false);
    // Both the fused and reference call sites must accept this boolean-equivalent
    // dtype; the underlying kernel itself still enforces bool.
    const auto action = trainer.act(structured, spatial, masks.to(torch::kInt32), false);
    MultiModalRolloutBatch rollout{structured, spatial, masks, action.actions, action.log_probabilities,
        action.values, torch::ones({8}), action.values + .25F};
    const auto rng = trainer.rng().mutable_states();
    const auto cpu_rng = at::globalContext().defaultGenerator(torch::kCPU).get_state().clone();
    const auto device_rng = at::globalContext().defaultGenerator(device).get_state().clone();
    std::vector<torch::Tensor> parameters;
    for (const auto &p : trainer.model()->parameters()) parameters.push_back(p.detach().clone());
    trainer.model()->eval();
    const auto error = trainer.audit_behavior(rollout);
    check(error <= 1e-5, "clean replay error exceeds kernel budget");
    check(trainer.behavior_replay_samples() == 8, "audit omitted the final chunk");
    check(!trainer.model()->is_training(), "audit changed caller mode");
    check(trainer.rng().mutable_states() == rng, "audit advanced native RNG");
    check(torch::equal(cpu_rng, at::globalContext().defaultGenerator(torch::kCPU).get_state()), "audit advanced CPU RNG");
    check(torch::equal(device_rng, at::globalContext().defaultGenerator(device).get_state()), "audit advanced device RNG");
    // A corrupt final-row probability must reject before any optimizer step.
    auto corrupt = rollout;
    corrupt.old_log_probabilities = rollout.old_log_probabilities.clone();
    corrupt.old_log_probabilities.index_put_({7}, corrupt.old_log_probabilities[7] + 1e-3);
    bool rejected = false;
    try { (void)trainer.update(corrupt); }
    catch (const std::runtime_error &e) { rejected = std::string(e.what()) == "behavior replay changed log probabilities"; }
    check(rejected, "corrupt behavior probability accepted");
    check(!trainer.model()->is_training(), "rejected update changed caller mode");
    check(trainer.counters().completed_updates == 0 && trainer.optimizer().state().empty(), "rejection mutated optimizer");
    check(trainer.rng().mutable_states() == rng, "rejected update shuffled samples");
    for (std::size_t i = 0; i < parameters.size(); ++i) {
        check(torch::equal(parameters[i], trainer.model()->parameters()[i]), "audit mutated parameters");
    }
    // Exceptions after entering eval mode must restore both train and eval.
    for (const bool training : {true, false}) {
        trainer.model()->train(training);
        rejected = false;
        try { (void)trainer.act(structured, spatial, torch::zeros_like(masks), false); }
        catch (const std::exception &) { rejected = true; }
        check(rejected && trainer.model()->is_training() == training, "ACT exception did not restore mode");
    }
    const auto metrics = trainer.update(rollout);
    check(metrics.update == 1, "clean rollout did not update");
    std::cout << " architecture=" << architecture_name(architecture) << " max_replay_error=" << error << '\n';
}
}

int main(int argc, char **argv)
{
    try {
        check(argc == 2, "usage: rl_behavior_replay_test cpu|cuda:0");
        const std::string selected(argv[1]);
        check(selected == "cpu" || selected == "cuda:0", "invalid device");
        check(selected == "cpu" || torch::cuda::is_available(), "CUDA requested but unavailable");
        torch::set_num_threads(1);
        at::globalContext().setDeterministicCuDNN(true);
        for (const auto architecture : {openttd_rl::training::ArchitectureKind::StructuredMlp,
             openttd_rl::training::ArchitectureKind::SpatialCnn, openttd_rl::training::ArchitectureKind::CombinedCnnMlp}) {
            test(torch::Device(selected), architecture);
        }
        std::cout << "BEHAVIOR_REPLAY=PASS device=" << selected << '\n';
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "BEHAVIOR_REPLAY=FAIL " << error.what() << '\n';
        return 1;
    }
}
