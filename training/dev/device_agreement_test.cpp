#include "openttd_rl/training/evaluation_model.h"
#include "openttd_rl/training/multimodal_trainer.h"
#include "openttd_rl/training/ppo.h"
#include <ATen/Context.h>
#include <filesystem>
#include <iostream>
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
    PpoConfig config;
    config.rollout_length = 4;
    config.minibatch_size = 4;
    config.optimization_epochs = 1;
    MultiModalPpoTrainer trainer(config, 925, architecture, device);
    const auto structured = torch::arange(4 * kStructuredFeatures, torch::kFloat32)
        .reshape({4, kStructuredFeatures}).sin();
    const auto spatial = torch::arange(4 * kSpatialChannels * kSpatialHeight * kSpatialWidth, torch::kFloat32)
        .reshape({4, kSpatialChannels, kSpatialHeight, kSpatialWidth}).sin().add(1).mul(.5);
    auto masks = torch::ones({4, kActionCount}, torch::kBool);
    masks.select(1, 5).fill_(false);
    masks[0].fill_(false);
    masks[0][0] = true;
    const auto action = trainer.act(structured, spatial, masks, true);
    (void)trainer.update({structured, spatial, masks, action.actions, action.log_probabilities,
        action.values, torch::ones({4}), action.values + .25F});
    const auto saved = save_evaluation_model(root / architecture_name(architecture), trainer.model(), architecture,
        {std::string(40, 'a'), 925, 1, 4, 0.0});
    ReadOnlyEvaluationPolicy cpu(saved.path, 0);
    MultiModalPpoTrainer imported(config, 2, architecture, device);
    cpu.copy_parameters_to(imported.model());
    const auto cpu_action = cpu.act(structured, spatial, masks, true);
    const auto cpu_distribution = masked_categorical(cpu_action.logits, masks);
    torch::Tensor probabilities;
    const auto copied = imported.act(structured, spatial, masks, true, &probabilities);
    check(torch::equal(cpu_action.actions, copied.actions), "CPU/device argmax differs");
    check(torch::allclose(probabilities, cpu_distribution.probabilities, 1e-5, 1e-6), "CPU/device probabilities differ");
    check(torch::allclose(copied.log_probabilities, cpu_action.log_probabilities, 1e-5, 1e-5), "CPU/device logp differs");
    check(probabilities.masked_select(~masks).eq(0).all().item<bool>(), "illegal probability is not zero");
    const auto regular = trainer.act(structured, spatial, masks, true);
    const auto rng = trainer.rng().mutable_states();
    const auto cpu_rng = at::globalContext().defaultGenerator(torch::kCPU).get_state().clone();
    const auto device_rng = at::globalContext().defaultGenerator(device).get_state().clone();
    std::vector<torch::Tensor> parameters, moments;
    std::vector<std::int64_t> steps;
    for (const auto &p : trainer.model()->parameters()) {
        parameters.push_back(p.detach().clone());
        const auto &state = static_cast<const torch::optim::AdamParamState &>(*trainer.optimizer().state().at(p.unsafeGetTensorImpl()));
        steps.push_back(state.step());
        moments.push_back(state.exp_avg().clone());
        moments.push_back(state.exp_avg_sq().clone());
    }
    for (const bool training : {true, false}) {
        trainer.model()->train(training);
        const auto inspected = trainer.act(structured, spatial, masks, true, &probabilities);
        check(torch::equal(regular.actions, inspected.actions) && torch::equal(regular.logits, inspected.logits) &&
            torch::equal(regular.log_probabilities, inspected.log_probabilities) && torch::equal(regular.values, inspected.values),
            "inspection changed regular ACT outputs");
        check(trainer.model()->is_training() == training, "inspection changed mode");
        bool rejected = false;
        try { (void)trainer.act(structured, spatial, torch::zeros_like(masks), true, &probabilities); }
        catch (const std::exception &) { rejected = true; }
        check(rejected && trainer.model()->is_training() == training, "inspection exception changed mode");
    }
    check(trainer.rng().mutable_states() == rng, "inspection advanced native RNG");
    check(torch::equal(cpu_rng, at::globalContext().defaultGenerator(torch::kCPU).get_state()), "inspection advanced CPU RNG");
    check(torch::equal(device_rng, at::globalContext().defaultGenerator(device).get_state()), "inspection advanced device RNG");
    check(trainer.counters().completed_updates == 1 && trainer.counters().accepted_samples == 4, "inspection changed counters");
    std::size_t i = 0;
    for (const auto &p : trainer.model()->parameters()) {
        check(torch::equal(parameters[i], p), "inspection changed parameters");
        const auto &state = static_cast<const torch::optim::AdamParamState &>(*trainer.optimizer().state().at(p.unsafeGetTensorImpl()));
        check(state.step() == steps[i] && torch::equal(state.exp_avg(), moments[2*i]) &&
            torch::equal(state.exp_avg_sq(), moments[2*i+1]), "inspection changed Adam state");
        ++i;
    }
    std::cout << " architecture=" << architecture_name(architecture)
              << " max_probability_error=" << (probabilities - cpu_distribution.probabilities).abs().max().item<double>() << '\n';
}
}
int main(int argc, char **argv)
{
    const auto root = std::filesystem::temp_directory_path() / ("openttd-device-agreement-" + std::to_string(::getpid()));
    try {
        check(argc == 2, "usage: rl_device_agreement_test cpu|cuda:0");
        const std::string selected(argv[1]);
        check(selected == "cpu" || selected == "cuda:0", "invalid device");
        check(selected == "cpu" || torch::cuda::is_available(), "CUDA requested but unavailable");
        torch::set_num_threads(1);
        at::globalContext().setDeterministicCuDNN(true);
        for (const auto architecture : {openttd_rl::training::ArchitectureKind::StructuredMlp,
             openttd_rl::training::ArchitectureKind::SpatialCnn, openttd_rl::training::ArchitectureKind::CombinedCnnMlp}) {
            test(torch::Device(selected), architecture, root);
        }
        std::filesystem::remove_all(root);
        std::cout << "DEVICE_AGREEMENT=PASS device=" << selected << '\n';
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "DEVICE_AGREEMENT=FAIL " << error.what() << '\n';
        return 1;
    }
}
