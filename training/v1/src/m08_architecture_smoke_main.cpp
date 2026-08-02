#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include <torch/cuda.h>
#include <torch/torch.h>

#include "openttd_rl/training/multimodal_trainer.h"

namespace {

using Clock = std::chrono::steady_clock;
using openttd_rl::training::ArchitectureKind;
using openttd_rl::training::MultiModalPpoTrainer;

constexpr std::int64_t kSamplesPerUpdate = 32;
constexpr int kUpdates = 8;
constexpr double kObjectiveDelta = 0.05;

struct Arguments {
    std::filesystem::path report;
    torch::Device device{torch::kCPU};
};

struct SmokeResult {
    std::string architecture;
    double initial_target_log_probability = 0.0;
    double final_target_log_probability = 0.0;
    std::uint64_t samples_to_objective = 0;
    std::uint64_t accepted_samples = 0;
    std::int64_t elapsed_ns = 0;
    std::int64_t parameter_count = 0;
};

[[nodiscard]] Arguments parse_arguments(int argc, char **argv)
{
    Arguments arguments;
    bool has_device = false;
    for (int index = 1; index < argc; ++index) {
        const std::string value(argv[index]);
        if (value == "--report" && index + 1 < argc) {
            arguments.report = argv[++index];
        } else if (value == "--device" && index + 1 < argc) {
            const std::string device(argv[++index]);
            if (device == "cpu") arguments.device = torch::Device(torch::kCPU);
            else if (device == "cuda:0") arguments.device = torch::Device(torch::kCUDA, 0);
            else throw std::invalid_argument("--device must be cpu or cuda:0");
            has_device = true;
        } else {
            throw std::invalid_argument("usage: m08_architecture_smoke --device cpu|cuda:0 --report ABSOLUTE_PATH");
        }
    }
    if (!has_device || !arguments.report.is_absolute()) {
        throw std::invalid_argument("--device and an absolute --report are required");
    }
    return arguments;
}

[[nodiscard]] torch::Tensor structured_observations()
{
    auto values = torch::arange(
        kSamplesPerUpdate * openttd_rl::training::kStructuredFeatures,
        torch::TensorOptions().dtype(torch::kFloat32));
    return torch::sin(values.reshape({kSamplesPerUpdate, openttd_rl::training::kStructuredFeatures}) * 0.013F);
}

[[nodiscard]] torch::Tensor spatial_observations()
{
    auto values = torch::arange(
        kSamplesPerUpdate * openttd_rl::training::kSpatialChannels * openttd_rl::training::kSpatialHeight *
            openttd_rl::training::kSpatialWidth,
        torch::TensorOptions().dtype(torch::kFloat32));
    return (values.remainder(257) / 256.0F).reshape(
        {kSamplesPerUpdate,
            openttd_rl::training::kSpatialChannels,
            openttd_rl::training::kSpatialHeight,
            openttd_rl::training::kSpatialWidth});
}

[[nodiscard]] torch::Tensor legal_masks()
{
    auto masks = torch::zeros({kSamplesPerUpdate, openttd_rl::training::kActionCount}, torch::kBool);
    masks.index_put_({torch::indexing::Slice(), torch::indexing::Slice(0, 2)}, true);
    return masks;
}

[[nodiscard]] double target_log_probability(
    MultiModalPpoTrainer &trainer,
    const torch::Tensor &structured,
    const torch::Tensor &spatial,
    const torch::Tensor &masks)
{
    const auto evaluation = trainer.act(structured, spatial, masks, true);
    const auto policy = openttd_rl::training::masked_categorical(evaluation.logits, masks);
    return policy.log_probabilities.index({torch::indexing::Slice(), 0}).mean().item<double>();
}

[[nodiscard]] openttd_rl::training::MultiModalRolloutBatch make_rollout(
    MultiModalPpoTrainer &trainer,
    const torch::Tensor &structured,
    const torch::Tensor &spatial,
    const torch::Tensor &masks)
{
    const auto behavior = trainer.act(structured, spatial, masks, true);
    const auto policy = openttd_rl::training::masked_categorical(behavior.logits, masks);
    const auto actions = torch::zeros({kSamplesPerUpdate}, torch::kInt64);
    return {
        structured,
        spatial,
        masks,
        actions,
        policy.log_probabilities.gather(1, actions.unsqueeze(1)).squeeze(1),
        behavior.values,
        torch::ones({kSamplesPerUpdate}, torch::kFloat32),
        torch::zeros({kSamplesPerUpdate}, torch::kFloat32),
    };
}

[[nodiscard]] SmokeResult run_architecture(ArchitectureKind architecture, const torch::Device &device)
{
    openttd_rl::training::PpoConfig config;
    config.rollout_length = kSamplesPerUpdate;
    config.environment_count = 1;
    config.minibatch_size = kSamplesPerUpdate;
    config.optimization_epochs = 2;
    config.learning_rate = 0.003;
    config.value_coefficient = 0.0;
    config.entropy_coefficient = 0.0;
    MultiModalPpoTrainer trainer(config, 991, architecture, device);
    const auto structured = structured_observations();
    const auto spatial = spatial_observations();
    const auto masks = legal_masks();
    SmokeResult result;
    result.architecture = openttd_rl::training::architecture_name(architecture);
    for (const auto &parameter : trainer.model()->parameters()) result.parameter_count += parameter.numel();
    result.initial_target_log_probability = target_log_probability(trainer, structured, spatial, masks);
    const auto started = Clock::now();
    for (int update = 0; update < kUpdates; ++update) {
        const auto metrics = trainer.update(make_rollout(trainer, structured, spatial, masks));
        if (metrics.update != static_cast<std::uint64_t>(update + 1)) {
            throw std::runtime_error("architecture smoke update counter drifted");
        }
        const auto objective = target_log_probability(trainer, structured, spatial, masks);
        if (result.samples_to_objective == 0 &&
            objective >= result.initial_target_log_probability + kObjectiveDelta) {
            result.samples_to_objective = metrics.samples;
        }
    }
    if (device.is_cuda()) torch::cuda::synchronize();
    result.elapsed_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - started).count();
    result.final_target_log_probability = target_log_probability(trainer, structured, spatial, masks);
    result.accepted_samples = trainer.counters().accepted_samples;
    if (result.samples_to_objective == 0 ||
        result.final_target_log_probability < result.initial_target_log_probability + kObjectiveDelta) {
        throw std::runtime_error(result.architecture + " did not reach the fixed learning objective");
    }
    return result;
}

void write_report(const std::filesystem::path &path, const torch::Device &device, const std::vector<SmokeResult> &results)
{
    if (path.has_parent_path()) std::filesystem::create_directories(path.parent_path());
    std::ofstream output(path, std::ios::binary | std::ios::trunc);
    if (!output) throw std::runtime_error("could not open architecture smoke report");
    output << std::setprecision(17)
           << "{\"schema_version\":\"openttd-rl-v1-m08-architecture-smoke-1\","
           << "\"compatibility_sha256\":\"" << openttd_rl::training::kM08CompatibilitySha256 << "\","
           << "\"device\":\"" << device.str() << "\",\"updates\":"
           << kUpdates << ",\"samples_per_update\":" << kSamplesPerUpdate
           << ",\"objective_delta\":" << kObjectiveDelta << ",\"architectures\":[";
    for (std::size_t index = 0; index < results.size(); ++index) {
        const auto &result = results[index];
        if (index != 0) output << ',';
        output << "{\"architecture\":\"" << result.architecture
               << "\",\"initial_target_log_probability\":" << result.initial_target_log_probability
               << ",\"final_target_log_probability\":" << result.final_target_log_probability
               << ",\"samples_to_objective\":" << result.samples_to_objective
               << ",\"accepted_samples\":" << result.accepted_samples
               << ",\"elapsed_ns\":" << result.elapsed_ns
               << ",\"parameter_count\":" << result.parameter_count << '}';
    }
    output << "]}\n";
    if (!output) throw std::runtime_error("could not write architecture smoke report");
}

} // namespace

int main(int argc, char **argv)
{
    try {
        const auto arguments = parse_arguments(argc, argv);
        torch::set_num_threads(arguments.device.is_cpu() ? 6 : 1);
        std::vector<SmokeResult> results;
        for (const auto architecture : {
                 ArchitectureKind::StructuredMlp,
                 ArchitectureKind::SpatialCnn,
                 ArchitectureKind::CombinedCnnMlp,
             }) {
            results.push_back(run_architecture(architecture, arguments.device));
        }
        write_report(arguments.report, arguments.device, results);
        std::cout << "M08_ARCHITECTURE_SMOKE=PASS device=" << arguments.device.str()
                  << " architectures=3 report=" << arguments.report.string() << '\n';
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "M08_ARCHITECTURE_SMOKE=FAIL " << error.what() << '\n';
        return 1;
    }
}
