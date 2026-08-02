#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <system_error>
#include <unistd.h>
#include <vector>

#include <torch/cuda.h>
#include <torch/torch.h>

#include "openttd_rl/v2/checkpoint.h"
#include "openttd_rl/v2/scalable_policy.h"

namespace {

using namespace torch::indexing;
using openttd_rl::v2::EntityTable;
using openttd_rl::v2::PolicyRuntimeState;
using openttd_rl::v2::ScalablePolicy;
using openttd_rl::v2::ScalablePolicyInput;
using openttd_rl::v2::ScalablePolicyOutput;

struct Arguments {
    torch::Device device{torch::kCPU};
    std::filesystem::path artifact_root;
};

struct Measurements {
    std::int64_t parameter_count{};
    double reset_max_abs_error{};
    double checkpoint_max_abs_error{};
    std::string checkpoint_id;
    std::int64_t forward_nanoseconds{};
};

void check(bool condition, const std::string &message)
{
    if (!condition) throw std::runtime_error(message);
}

Arguments parse_arguments(int argc, char **argv)
{
    Arguments result;
    bool has_device = false;
    for (int index = 1; index < argc; ++index) {
        const std::string value(argv[index]);
        if (value == "--device" && index + 1 < argc) {
            const std::string name(argv[++index]);
            if (name == "cpu") result.device = torch::Device(torch::kCPU);
            else if (name == "cuda:0") result.device = torch::Device(torch::kCUDA, 0);
            else throw std::invalid_argument("--device must be cpu or cuda:0");
            has_device = true;
        } else if (value == "--artifact-root" && index + 1 < argc) {
            result.artifact_root = argv[++index];
        } else {
            throw std::invalid_argument("usage: m15_policy_gate --device cpu|cuda:0 [--artifact-root NEW_ABSOLUTE_PATH]");
        }
    }
    if (!has_device) throw std::invalid_argument("--device is required");
    if (!result.artifact_root.empty() && (!result.artifact_root.is_absolute() || std::filesystem::exists(result.artifact_root))) {
        throw std::invalid_argument("--artifact-root must be a new absolute path");
    }
    if (result.device.is_cuda() && !torch::cuda::is_available()) throw std::runtime_error("CUDA is unavailable");
    return result;
}

torch::Tensor patterned(const std::vector<std::int64_t> &shape, const torch::Device &device, float scale)
{
    std::int64_t count = 1;
    for (const auto size : shape) count *= size;
    return torch::sin(torch::arange(count, torch::TensorOptions().dtype(torch::kFloat32).device(device)) * scale).reshape(shape);
}

EntityTable entity_table(
    std::int64_t batch,
    std::int64_t capacity,
    std::int64_t features,
    std::int64_t valid,
    const torch::Device &device,
    float scale)
{
    auto mask = torch::zeros({batch, capacity}, torch::TensorOptions().dtype(torch::kBool).device(device));
    mask.index_put_({Slice(), Slice(0, valid)}, true);
    return {patterned({batch, capacity, features}, device, scale), mask};
}

ScalablePolicyInput make_input(std::int64_t batch, const torch::Device &device)
{
    auto graph_node_mask = torch::zeros(
        {batch, openttd_rl::v2::kGraphNodeCapacity},
        torch::TensorOptions().dtype(torch::kBool).device(device));
    graph_node_mask.index_put_({Slice(), Slice(0, 96)}, true);
    auto edge_mask = torch::zeros(
        {batch, openttd_rl::v2::kGraphEdgeCapacity},
        torch::TensorOptions().dtype(torch::kBool).device(device));
    edge_mask.index_put_({Slice(), Slice(0, 192)}, true);
    auto edge_ordinal = torch::arange(
        openttd_rl::v2::kGraphEdgeCapacity,
        torch::TensorOptions().dtype(torch::kInt64).device(device));
    auto edge_index = torch::stack({
        edge_ordinal.remainder(96),
        (edge_ordinal + 7).remainder(96),
    }, 1).unsqueeze(0).repeat({batch, 1, 1});
    auto candidate_mask = torch::zeros(
        {batch, openttd_rl::v2::kCandidateCapacity},
        torch::TensorOptions().dtype(torch::kBool).device(device));
    candidate_mask.index_put_({Slice(), Slice(0, 257)}, true);
    auto candidate_family = torch::arange(
        openttd_rl::v2::kCandidateCapacity,
        torch::TensorOptions().dtype(torch::kInt64).device(device)).remainder(openttd_rl::v2::kFamilyCount).unsqueeze(0).repeat({batch, 1});
    auto family_mask = torch::zeros(
        {batch, openttd_rl::v2::kFamilyCount},
        torch::TensorOptions().dtype(torch::kBool).device(device));
    family_mask.index_put_({Slice(), Slice(0, 9)}, true);
    return {
        patterned({batch, openttd_rl::v2::kStructuredFeatures}, device, 0.007F),
        patterned({batch, openttd_rl::v2::kSpatialChannels, openttd_rl::v2::kGlobalSpatialSide, openttd_rl::v2::kGlobalSpatialSide}, device, 0.003F),
        patterned({batch, openttd_rl::v2::kSpatialChannels, openttd_rl::v2::kRegionalSpatialSide, openttd_rl::v2::kRegionalSpatialSide}, device, 0.005F),
        patterned({batch, openttd_rl::v2::kSpatialChannels, openttd_rl::v2::kLocalSpatialSide, openttd_rl::v2::kLocalSpatialSide}, device, 0.011F),
        entity_table(batch, openttd_rl::v2::kCompanyCapacity, openttd_rl::v2::kCompanyFeatures, 3, device, 0.013F),
        entity_table(batch, openttd_rl::v2::kTownCapacity, openttd_rl::v2::kTownFeatures, 31, device, 0.017F),
        entity_table(batch, openttd_rl::v2::kIndustryCapacity, openttd_rl::v2::kIndustryFeatures, 17, device, 0.019F),
        entity_table(batch, openttd_rl::v2::kStationCapacity, openttd_rl::v2::kStationFeatures, 43, device, 0.023F),
        entity_table(batch, openttd_rl::v2::kVehicleCapacity, openttd_rl::v2::kVehicleFeatures, 67, device, 0.029F),
        patterned({batch, openttd_rl::v2::kGraphNodeCapacity, openttd_rl::v2::kGraphNodeFeatures}, device, 0.031F),
        graph_node_mask,
        edge_index,
        patterned({batch, openttd_rl::v2::kGraphEdgeCapacity, openttd_rl::v2::kGraphEdgeFeatures}, device, 0.037F),
        edge_mask,
        patterned({batch, openttd_rl::v2::kCandidateCapacity, openttd_rl::v2::kCandidateFeatures}, device, 0.041F),
        candidate_family,
        candidate_mask,
        family_mask,
        torch::zeros({batch, openttd_rl::v2::kHiddenSize}, torch::TensorOptions().dtype(torch::kFloat32).device(device)),
        torch::zeros({batch}, torch::TensorOptions().dtype(torch::kBool).device(device)),
    };
}

double maximum_output_error(const ScalablePolicyOutput &left, const ScalablePolicyOutput &right)
{
    return std::max({
        (left.family_logits - right.family_logits).abs().max().item<double>(),
        (left.candidate_logits - right.candidate_logits).abs().max().item<double>(),
        (left.value - right.value).abs().max().item<double>(),
        (left.next_hidden - right.next_hidden).abs().max().item<double>(),
    });
}

void optimize_once(ScalablePolicy &model, torch::optim::Adam &optimizer, const ScalablePolicyInput &input)
{
    optimizer.zero_grad();
    const auto output = model->forward(input);
    const auto loss = -output.family_logits.index({Slice(), 0}).mean() -
        output.candidate_logits.index({Slice(), 0}).mean() + output.value.square().mean() +
        0.01 * output.next_hidden.square().mean();
    loss.backward();
    torch::nn::utils::clip_grad_norm_(model->parameters(), 1.0);
    optimizer.step();
    openttd_rl::v2::require_finite_policy(model, "optimization");
}

void test_forward_gradient_and_masks(const torch::Device &device, Measurements &measurements)
{
    ScalablePolicy model(918273);
    model->to(device);
    model->train();
    for (const auto &parameter : model->parameters()) measurements.parameter_count += parameter.numel();
    const auto input = make_input(2, device);
    const auto started = std::chrono::steady_clock::now();
    const auto output = model->forward(input);
    if (device.is_cuda()) torch::cuda::synchronize();
    measurements.forward_nanoseconds = std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now() - started).count();
    check(output.family_logits.sizes() == torch::IntArrayRef({2, openttd_rl::v2::kFamilyCount}), "family logits shape mismatch");
    check(output.candidate_logits.sizes() == torch::IntArrayRef({2, openttd_rl::v2::kCandidateCapacity}), "candidate logits shape mismatch");
    check(output.value.sizes() == torch::IntArrayRef({2}), "value shape mismatch");
    check(output.next_hidden.sizes() == torch::IntArrayRef({2, openttd_rl::v2::kHiddenSize}), "hidden state shape mismatch");
    check((output.family_logits.index({Slice(), Slice(9, None)}) == -1.0e9).all().item<bool>(), "illegal family logits were not masked");
    check((output.candidate_logits.index({Slice(), Slice(257, None)}) == -1.0e9).all().item<bool>(), "illegal candidate logits were not masked");
    const auto loss = output.family_logits.index({Slice(), Slice(0, 9)}).square().mean() +
        output.candidate_logits.index({Slice(), Slice(0, 257)}).square().mean() + output.value.square().mean();
    loss.backward();
    bool nonzero = false;
    for (const auto &parameter : model->named_parameters(true)) {
        check(parameter.value().grad().defined(), "trainable policy parameter has no gradient: " + parameter.key());
        check(torch::isfinite(parameter.value().grad()).all().item<bool>(), "policy gradient is nonfinite: " + parameter.key());
        nonzero = nonzero || parameter.value().grad().abs().max().item<float>() > 0.0F;
    }
    check(nonzero, "policy produced no nonzero gradient");
}

void test_recurrent_reset(const torch::Device &device, Measurements &measurements)
{
    ScalablePolicy model(44119);
    model->to(device);
    model->eval();
    auto zero = make_input(2, device);
    auto reset = make_input(2, device);
    reset.hidden_state = patterned({2, openttd_rl::v2::kHiddenSize}, device, 0.17F);
    reset.recurrent_reset = torch::ones({2}, torch::TensorOptions().dtype(torch::kBool).device(device));
    auto retained = reset;
    retained.recurrent_reset = torch::zeros({2}, torch::TensorOptions().dtype(torch::kBool).device(device));
    torch::NoGradGuard guard;
    const auto zero_output = model->forward(zero);
    const auto reset_output = model->forward(reset);
    const auto retained_output = model->forward(retained);
    measurements.reset_max_abs_error = maximum_output_error(zero_output, reset_output);
    check(measurements.reset_max_abs_error == 0.0, "explicit recurrent reset is not exact");
    check(maximum_output_error(zero_output, retained_output) > 1.0e-5, "retained recurrent state has no effect");
}

void test_invalid_inputs(const torch::Device &device)
{
    ScalablePolicy model(77);
    model->to(device);
    auto bad = make_input(1, device);
    bad.family_mask.zero_();
    bool all_mask_rejected = false;
    try {
        (void)model->forward(bad);
    } catch (const std::invalid_argument &) {
        all_mask_rejected = true;
    }
    check(all_mask_rejected, "all-illegal family mask was accepted");
    bad = make_input(1, device);
    bad.structured.index_put_({0, 0}, std::numeric_limits<float>::quiet_NaN());
    bool nonfinite_rejected = false;
    try {
        (void)model->forward(bad);
    } catch (const std::runtime_error &) {
        nonfinite_rejected = true;
    }
    check(nonfinite_rejected, "nonfinite policy input was accepted");
    bad = make_input(1, device);
    bad.graph_edge_index.index_put_({0, 0, 1}, openttd_rl::v2::kGraphNodeCapacity);
    bool bad_edge_rejected = false;
    try {
        (void)model->forward(bad);
    } catch (const std::invalid_argument &) {
        bad_edge_rejected = true;
    }
    check(bad_edge_rejected, "out-of-range legal graph edge was accepted");
}

PolicyRuntimeState runtime_state(const torch::Tensor &hidden)
{
    std::mt19937_64 generator(9917);
    (void)generator();
    std::ostringstream rng;
    rng << generator;
    return {
        torch::linspace(-0.25, 0.25, openttd_rl::v2::kStructuredFeatures, torch::kFloat32),
        torch::linspace(0.5, 1.5, openttd_rl::v2::kStructuredFeatures, torch::kFloat32),
        8192,
        rng.str(),
        {2, 256, 256, 41, 733},
        19,
        hidden.detach().to(torch::kCPU).contiguous(),
    };
}

void compare_parameters(const ScalablePolicy &left, const ScalablePolicy &right)
{
    const auto left_parameters = left->named_parameters(true);
    const auto right_parameters = right->named_parameters(true);
    check(left_parameters.size() == right_parameters.size(), "checkpoint parameter inventory mismatch");
    for (const auto &parameter : left_parameters) {
        check(right_parameters.contains(parameter.key()), "checkpoint lost parameter " + parameter.key());
        check(torch::equal(parameter.value(), right_parameters[parameter.key()]), "checkpoint parameter mismatch: " + parameter.key());
    }
}

void test_checkpoint(const std::filesystem::path &checkpoint_root, Measurements &measurements)
{
    ScalablePolicy original(1618);
    torch::optim::Adam original_optimizer(original->parameters(), torch::optim::AdamOptions(0.0003));
    const auto input = make_input(1, torch::Device(torch::kCPU));
    optimize_once(original, original_optimizer, input);
    torch::NoGradGuard guard;
    const auto before = original->forward(input);
    auto state = runtime_state(before.next_hidden);
    const auto saved = openttd_rl::v2::save_checkpoint(checkpoint_root, original, original_optimizer, state);
    measurements.checkpoint_id = saved.checkpoint_id;

    ScalablePolicy recovered(999999);
    torch::optim::Adam recovered_optimizer(recovered->parameters(), torch::optim::AdamOptions(0.0003));
    const auto recovered_state = openttd_rl::v2::load_checkpoint(
        saved.path, recovered, recovered_optimizer, torch::Device(torch::kCPU));
    const auto after = recovered->forward(input);
    measurements.checkpoint_max_abs_error = maximum_output_error(before, after);
    check(measurements.checkpoint_max_abs_error == 0.0, "checkpoint forward recovery is not exact");
    compare_parameters(original, recovered);
    check(recovered_state.rng_state == state.rng_state &&
        recovered_state.normalization_count == state.normalization_count &&
        recovered_state.curriculum.transition == state.curriculum.transition &&
        recovered_state.completed_updates == state.completed_updates &&
        torch::equal(recovered_state.normalization_mean, state.normalization_mean) &&
        torch::equal(recovered_state.normalization_variance, state.normalization_variance) &&
        torch::equal(recovered_state.hidden_state, state.hidden_state),
        "checkpoint runtime state recovery mismatch");

    bool overwrite_rejected = false;
    try {
        (void)openttd_rl::v2::save_checkpoint(checkpoint_root, original, original_optimizer, state);
    } catch (const std::runtime_error &) {
        overwrite_rejected = true;
    }
    check(overwrite_rejected, "checkpoint save overwrote an existing generation");
}

void write_report(
    const std::filesystem::path &artifact_root,
    const torch::Device &device,
    const Measurements &measurements)
{
    std::ofstream output(artifact_root / "policy-report.json", std::ios::binary | std::ios::trunc);
    if (!output) throw std::runtime_error("cannot create policy report");
    output << std::setprecision(17)
           << "{\"schema_version\":\"openttd-rl-v2-m15-policy-report-1\","
           << "\"policy_schema_id\":\"" << openttd_rl::v2::kPolicySchemaId << "\","
           << "\"contract_sha256\":\"" << openttd_rl::v2::kScalableContractSha256 << "\","
           << "\"device\":\"" << device.str() << "\","
           << "\"parameter_count\":" << measurements.parameter_count << ','
           << "\"forward_nanoseconds\":" << measurements.forward_nanoseconds << ','
           << "\"reset_max_abs_error\":" << measurements.reset_max_abs_error << ','
           << "\"checkpoint_max_abs_error\":" << measurements.checkpoint_max_abs_error << ','
           << "\"checkpoint_id\":\"" << measurements.checkpoint_id << "\","
           << "\"outputs\":[\"family_logits\",\"candidate_logits\",\"value\",\"next_hidden\"],"
           << "\"tests\":{\"forward_gradient_masks\":\"PASS\",\"recurrent_reset\":\"PASS\","
           << "\"invalid_inputs\":\"PASS\",\"checkpoint_recovery\":\"PASS\"}}\n";
    if (!output) throw std::runtime_error("cannot write policy report");
}

} // namespace

int main(int argc, char **argv)
{
    std::filesystem::path temporary_root;
    bool remove_temporary = false;
    try {
        const auto arguments = parse_arguments(argc, argv);
        torch::set_num_threads(arguments.device.is_cpu() ? 6 : 1);
        Measurements measurements;
        test_forward_gradient_and_masks(arguments.device, measurements);
        test_recurrent_reset(arguments.device, measurements);
        test_invalid_inputs(arguments.device);

        std::filesystem::path artifact_root = arguments.artifact_root;
        if (artifact_root.empty()) {
            artifact_root = std::filesystem::temp_directory_path() /
                ("openttd-rl-v2-m15-policy-" + std::to_string(::getpid()) + '-' + arguments.device.str());
            temporary_root = artifact_root;
            remove_temporary = true;
        }
        if (!std::filesystem::create_directories(artifact_root)) throw std::runtime_error("cannot create policy artifact root");
        test_checkpoint(artifact_root / "checkpoints", measurements);
        if (arguments.device.is_cuda()) torch::cuda::synchronize();
        if (!arguments.artifact_root.empty()) write_report(artifact_root, arguments.device, measurements);
        if (remove_temporary) {
            std::error_code error;
            std::filesystem::remove_all(temporary_root, error);
            if (error) throw std::runtime_error("cannot remove policy test temporary directory");
        }
        std::cout << "V2_M15_POLICY_GATE=PASS device=" << arguments.device.str()
                  << " parameters=" << measurements.parameter_count
                  << " checkpoint=" << measurements.checkpoint_id << '\n';
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "V2_M15_POLICY_GATE=FAIL " << error.what() << '\n';
        return 1;
    }
}
