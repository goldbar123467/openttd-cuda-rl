#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include <unistd.h>

#include <ATen/CPUGeneratorImpl.h>
#include <torch/cuda.h>
#include "openttd_rl/training/evaluation_model.h"
#include "openttd_rl/training/multimodal_trainer.h"

namespace {
void check(bool condition, const char *message)
{
    if (!condition) throw std::runtime_error(message);
}

void test_export(const torch::Device &device, openttd_rl::training::ArchitectureKind architecture,
                 const std::filesystem::path &root)
{
    using namespace openttd_rl::training;
    PpoConfig config;
    config.rollout_length = 4;
    config.minibatch_size = 4;
    config.optimization_epochs = 1;
    MultiModalPpoTrainer trainer(config, 123, architecture, device);
    const auto structured = torch::full({4, kStructuredFeatures}, 0.25F);
    const auto spatial = torch::full({4, kSpatialChannels, kSpatialHeight, kSpatialWidth}, 0.25F);
    const auto masks = torch::ones({4, kActionCount}, torch::kBool);
    const auto rollout = [&]() {
        const auto action = trainer.act(structured, spatial, masks, true);
        return MultiModalRolloutBatch{structured, spatial, masks, action.actions,
            action.log_probabilities, action.values, torch::ones({4}), action.values + 1.0F};
    };
    (void)trainer.update(rollout()); // Initialize Adam moments on the training device.
    const auto before = trainer.act(structured, spatial, masks, true);
    std::vector<const void *> storage;
    std::vector<torch::Tensor> parameters;
    for (const auto &parameter : trainer.model()->parameters()) {
        storage.push_back(parameter.const_data_ptr());
        parameters.push_back(parameter.detach().cpu().clone());
    }
    const auto rng = at::detail::getDefaultCPUGenerator().get_state().clone();
    const bool training = trainer.model()->is_training();
    const auto saved = save_evaluation_model(root / architecture_name(architecture), trainer.model(), architecture,
        {std::string(40, 'a'), 123, 1, 4, 0.0});
    check(torch::equal(rng, at::detail::getDefaultCPUGenerator().get_state()), "export changed Torch RNG");
    check(trainer.model()->is_training() == training, "export changed training mode");
    std::size_t index = 0;
    for (const auto &parameter : trainer.model()->parameters()) {
        check(parameter.device() == device, "export moved a live parameter off the training device");
        check(parameter.const_data_ptr() == storage[index], "export replaced optimizer parameter storage");
        check(torch::equal(parameter.detach().cpu(), parameters[index]), "export changed parameter values");
        ++index;
    }
    const auto after = trainer.act(structured, spatial, masks, true);
    check(torch::equal(before.logits, after.logits), "export changed live logits");
    check(torch::equal(before.values, after.values), "export changed live values");
    ReadOnlyEvaluationPolicy reloaded(saved.path, 456);
    const auto deployed = reloaded.act(structured, spatial, masks, true);
    check(torch::allclose(before.logits, deployed.logits, 1e-4, 1e-5), "CPU snapshot logits changed");
    check(torch::allclose(before.values, deployed.values, 1e-4, 1e-5), "CPU snapshot values changed");
    check(torch::equal(before.actions, deployed.actions), "CPU snapshot selected different actions");
    check(trainer.update(rollout()).update == 2, "training cannot continue after export");
}
} // namespace

int main(int argc, char **argv)
{
    const auto root = std::filesystem::temp_directory_path() /
        ("openttd-rl-export-device-" + std::to_string(::getpid()));
    try {
        check(argc == 2, "usage: rl_export_preserves_trainer cpu|cuda:0");
        const std::string selected = argv[1];
        check(selected == "cpu" || selected == "cuda:0", "invalid device");
        check(selected == "cpu" || torch::cuda::is_available(), "CUDA requested but unavailable");
        const torch::Device device(selected);
        torch::set_num_threads(1);
        for (const auto architecture : {openttd_rl::training::ArchitectureKind::StructuredMlp,
                 openttd_rl::training::ArchitectureKind::SpatialCnn,
                 openttd_rl::training::ArchitectureKind::CombinedCnnMlp}) {
            test_export(device, architecture, root);
        }
        std::filesystem::remove_all(root);
        std::cout << "EXPORT_PRESERVES_TRAINER=PASS device=" << selected << " architectures=3\n";
        return 0;
    } catch (const std::exception &error) {
        std::error_code ignored;
        std::filesystem::remove_all(root, ignored);
        std::cerr << "EXPORT_PRESERVES_TRAINER=FAIL " << error.what() << '\n';
        return 1;
    }
}
