#include "openttd_rl/v2/m22_checkpoint.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <c10/cuda/CUDACachingAllocator.h>
#include <cuda_runtime_api.h>
#include <torch/cuda.h>
#include <torch/torch.h>
#include <unistd.h>

namespace {

using Clock = std::chrono::steady_clock;
using openttd_rl::v2::GeneralistPolicyInput;
using openttd_rl::v2::GeneralistPolicyOutput;
using openttd_rl::v2::M22CompactBatch;
using openttd_rl::v2::M22Corpus;
using openttd_rl::v2::M22LoadedCheckpoint;
using openttd_rl::v2::M22Trainer;

constexpr double kForwardTolerance = 1.0e-4;
constexpr double kLossTolerance = 1.0e-5;
constexpr double kGradientTolerance = 5.0e-4;
constexpr double kUpdateTolerance = 5.0e-4;
constexpr double kCheckpointTolerance = 1.0e-4;
constexpr int kWarmups = 10;
constexpr int kSamples = 30;
constexpr std::array<std::int64_t, 3> kBatches = {1, 8, 32};

struct Arguments {
    std::filesystem::path checkpoint;
    std::filesystem::path corpus;
    std::filesystem::path report;
};

struct DeviceDescription {
    std::string name;
    int major{};
    int minor{};
    std::uint64_t total_memory_bytes{};
};

struct ParityResult {
    std::int64_t batch{};
    double forward_max_abs{};
    double loss_max_abs{};
    double gradient_max_abs{};
    double update_max_abs{};
    double checkpoint_max_abs{};
    double minimum_greedy_margin{};
    std::int64_t identical_greedy_programs{};
};

struct TimingSummary {
    double median_ns{};
    double p95_ns{};
    double samples_per_second{};
};

struct BenchmarkBatch {
    std::int64_t batch{};
    TimingSummary cpu;
    TimingSummary cuda;
    double speedup{};
    std::int64_t peak_allocated_bytes{};
    std::int64_t peak_reserved_bytes{};
};

struct RetentionResult {
    std::vector<std::int64_t> cpu_actions;
    std::vector<std::int64_t> cuda_actions;
    double mean_reward{};
};

[[nodiscard]] Arguments parse_arguments(int argc, char **argv)
{
    Arguments result;
    for (int index = 1; index < argc; ++index) {
        const std::string value(argv[index]);
        if (value == "--checkpoint" && index + 1 < argc) {
            result.checkpoint = argv[++index];
        } else if (value == "--corpus" && index + 1 < argc) {
            result.corpus = argv[++index];
        } else if (value == "--report" && index + 1 < argc) {
            result.report = argv[++index];
        } else {
            throw std::invalid_argument(
                "usage: m22_qualification_gate --checkpoint ABSOLUTE_DIRECTORY --corpus ABSOLUTE_FILE --report ABSOLUTE_FILE");
        }
    }
    if (!result.checkpoint.is_absolute() || !result.corpus.is_absolute() || !result.report.is_absolute() ||
        !std::filesystem::is_directory(result.checkpoint) || !std::filesystem::is_regular_file(result.corpus)) {
        throw std::invalid_argument("M22 qualification inputs must be existing absolute paths and report must be absolute");
    }
    return result;
}

void require(bool condition, const std::string &message)
{
    if (!condition) throw std::runtime_error(message);
}

void check_cuda(cudaError_t status, const char *operation)
{
    if (status != cudaSuccess) {
        throw std::runtime_error(std::string(operation) + " failed: " + cudaGetErrorString(status));
    }
}

[[nodiscard]] DeviceDescription describe_device()
{
    cudaDeviceProp properties{};
    check_cuda(cudaGetDeviceProperties(&properties, 0), "cudaGetDeviceProperties");
    return {
        properties.name,
        properties.major,
        properties.minor,
        static_cast<std::uint64_t>(properties.totalGlobalMem),
    };
}

[[nodiscard]] M22CompactBatch make_batch(const M22Corpus &corpus, std::int64_t batch)
{
    using namespace openttd_rl::v2;
    std::vector<const M22CorpusEntry *> entries;
    entries.reserve(static_cast<std::size_t>(batch));
    for (std::int64_t row = 0; row < batch; ++row) {
        entries.push_back(&corpus.entry(M22CorpusSplit::Development, 1 + row % 16));
    }
    auto hidden = torch::sin(torch::arange(
        batch * kHiddenSize, torch::TensorOptions().dtype(torch::kFloat32)) * 0.001F).reshape({batch, kHiddenSize}) * 0.01F;
    auto reset = torch::arange(batch, torch::TensorOptions().dtype(torch::kInt64)).remainder(3).eq(0);
    return m22_compact_from_entries(entries, hidden, reset);
}

[[nodiscard]] M22CompactBatch retention_batch(const M22Corpus &corpus)
{
    using namespace openttd_rl::v2;
    std::vector<const M22CorpusEntry *> entries;
    for (std::int64_t program = 1; program < kM22ProgramCount; ++program) {
        entries.push_back(&corpus.entry(M22CorpusSplit::Development, program));
    }
    return m22_compact_from_entries(
        entries,
        torch::zeros({kM22ProgramCount - 1, kHiddenSize}, torch::kFloat32),
        torch::ones({kM22ProgramCount - 1}, torch::kBool));
}

[[nodiscard]] double maximum_absolute_difference(const torch::Tensor &left, const torch::Tensor &right)
{
    require(left.defined() && right.defined() && left.sizes() == right.sizes(), "M22 parity tensor shape drifted");
    return (left.detach().to(torch::kCPU) - right.detach().to(torch::kCPU)).abs().max().item<double>();
}

[[nodiscard]] double forward_difference(const GeneralistPolicyOutput &left, const GeneralistPolicyOutput &right)
{
    return std::max({
        maximum_absolute_difference(left.program_logits, right.program_logits),
        maximum_absolute_difference(left.program_value, right.program_value),
        maximum_absolute_difference(left.next_hidden, right.next_hidden),
    });
}

[[nodiscard]] GeneralistPolicyOutput forward(M22Trainer &trainer, const M22CompactBatch &batch)
{
    return trainer.model()->forward(openttd_rl::v2::m22_encode_compact(batch, trainer.device()));
}

[[nodiscard]] torch::Tensor comparison_loss(
    M22Trainer &trainer,
    const M22CompactBatch &batch,
    const GeneralistPolicyInput &input)
{
    using namespace openttd_rl::v2;
    const auto output = trainer.model()->forward(input);
    const auto mask = batch.program_mask.to(trainer.device());
    const auto policy = m22_masked_categorical(output.program_logits, mask);
    const auto actions = m22_public_heuristic(batch).to(trainer.device());
    const auto selected = policy.log_probabilities.gather(1, actions.unsqueeze(1)).squeeze(1);
    const auto samples = batch.size();
    const auto options = torch::TensorOptions().dtype(torch::kFloat32).device(trainer.device());
    const auto advantages = torch::linspace(-1.0, 1.0, samples, options);
    const auto old_logs = selected.detach() - 0.03F;
    const auto old_values = output.program_value.detach() + 0.02F;
    const auto returns = output.program_value.detach() + torch::cos(advantages * 0.7F);
    return m22_ppo_loss(
        selected, old_logs, advantages, output.program_value, old_values, returns, policy.entropy, trainer.config()).total;
}

[[nodiscard]] double maximum_gradient_difference(M22Trainer &left, M22Trainer &right)
{
    const auto left_parameters = left.model()->named_parameters(true);
    const auto right_parameters = right.model()->named_parameters(true);
    require(left_parameters.size() == right_parameters.size(), "M22 parity parameter inventory drifted");
    double result = 0.0;
    for (const auto &item : left_parameters) {
        require(right_parameters.contains(item.key()), "M22 parity parameter name drifted");
        const auto left_gradient = item.value().grad();
        const auto right_gradient = right_parameters[item.key()].grad();
        require(left_gradient.defined() == right_gradient.defined(), "M22 parity gradient definition drifted");
        if (left_gradient.defined()) {
            result = std::max(result, maximum_absolute_difference(left_gradient, right_gradient));
        }
    }
    return result;
}

[[nodiscard]] double maximum_parameter_difference(M22Trainer &left, M22Trainer &right)
{
    const auto left_parameters = left.model()->named_parameters(true);
    const auto right_parameters = right.model()->named_parameters(true);
    require(left_parameters.size() == right_parameters.size(), "M22 parity parameter inventory drifted");
    double result = 0.0;
    for (const auto &item : left_parameters) {
        require(right_parameters.contains(item.key()), "M22 parity parameter name drifted");
        result = std::max(result, maximum_absolute_difference(item.value(), right_parameters[item.key()]));
    }
    return result;
}

[[nodiscard]] ParityResult run_parity(
    const std::filesystem::path &checkpoint,
    const M22Corpus &corpus,
    std::int64_t batch_size)
{
    using namespace openttd_rl::v2;
    const torch::Device cuda_device(torch::kCUDA, 0);
    auto cpu = load_m22_checkpoint(checkpoint, torch::kCPU);
    auto cuda = load_m22_checkpoint(checkpoint, cuda_device);
    const auto batch = make_batch(corpus, batch_size);
    cpu.trainer->model()->train();
    cuda.trainer->model()->train();
    const auto cpu_output = forward(*cpu.trainer, batch);
    const auto cuda_output = forward(*cuda.trainer, batch);
    torch::cuda::synchronize();

    ParityResult result;
    result.batch = batch_size;
    result.forward_max_abs = forward_difference(cpu_output, cuda_output);
    require(result.forward_max_abs <= kForwardTolerance, "M22 CPU/CUDA forward parity exceeded tolerance");
    const auto cpu_top = std::get<0>(cpu_output.program_logits.topk(2, 1)).to(torch::kCPU);
    const auto margins = cpu_top.index({torch::indexing::Slice(), 0}) - cpu_top.index({torch::indexing::Slice(), 1});
    result.minimum_greedy_margin = margins.min().item<double>();
    require(result.minimum_greedy_margin > 2.0 * kForwardTolerance, "M22 greedy program is not numerically stable");
    const auto cpu_actions = cpu_output.program_logits.argmax(1).to(torch::kCPU);
    const auto cuda_actions = cuda_output.program_logits.argmax(1).to(torch::kCPU);
    require(torch::equal(cpu_actions, cuda_actions), "M22 stable greedy program differs between CPU and CUDA");
    result.identical_greedy_programs = batch_size;

    const auto cpu_input = m22_encode_compact(batch, cpu.trainer->device());
    const auto cuda_input = m22_encode_compact(batch, cuda.trainer->device());
    cpu.trainer->optimizer().zero_grad();
    cuda.trainer->optimizer().zero_grad();
    const auto cpu_loss = comparison_loss(*cpu.trainer, batch, cpu_input);
    const auto cuda_loss = comparison_loss(*cuda.trainer, batch, cuda_input);
    result.loss_max_abs = maximum_absolute_difference(cpu_loss, cuda_loss);
    require(result.loss_max_abs <= kLossTolerance, "M22 CPU/CUDA PPO loss parity exceeded tolerance");
    cpu_loss.backward();
    cuda_loss.backward();
    torch::cuda::synchronize();
    result.gradient_max_abs = maximum_gradient_difference(*cpu.trainer, *cuda.trainer);
    require(result.gradient_max_abs <= kGradientTolerance, "M22 CPU/CUDA gradient parity exceeded tolerance");
    cpu.trainer->optimizer().step();
    cuda.trainer->optimizer().step();
    torch::cuda::synchronize();
    require_finite_generalist(cpu.trainer->model(), "M22 CPU parity update");
    require_finite_generalist(cuda.trainer->model(), "M22 CUDA parity update");
    result.update_max_abs = maximum_parameter_difference(*cpu.trainer, *cuda.trainer);
    require(result.update_max_abs <= kUpdateTolerance, "M22 CPU/CUDA optimizer-update parity exceeded tolerance");

    const auto temporary = std::filesystem::temp_directory_path() /
        ("openttd-rl-m22-qualification-" + std::to_string(::getpid()) + '-' + std::to_string(batch_size));
    require(std::filesystem::create_directory(temporary), "cannot create M22 qualification checkpoint directory");
    try {
        const auto saved = save_m22_checkpoint(temporary / "checkpoints", *cuda.trainer, cuda.campaign);
        auto restored = load_m22_checkpoint(saved.path, torch::kCPU);
        const auto cpu_updated = forward(*cpu.trainer, batch);
        const auto restored_output = forward(*restored.trainer, batch);
        result.checkpoint_max_abs = forward_difference(cpu_updated, restored_output);
        require(result.checkpoint_max_abs <= kCheckpointTolerance,
                "M22 canonical CUDA checkpoint crossed CPU tolerance");
    } catch (...) {
        std::error_code ignored;
        std::filesystem::remove_all(temporary, ignored);
        throw;
    }
    std::error_code ignored;
    std::filesystem::remove_all(temporary, ignored);
    return result;
}

[[nodiscard]] TimingSummary summarize(std::vector<double> durations, std::int64_t batch)
{
    require(durations.size() == static_cast<std::size_t>(kSamples), "M22 benchmark sample count drifted");
    std::sort(durations.begin(), durations.end());
    TimingSummary result;
    result.median_ns = durations[durations.size() / 2U];
    const auto p95 = static_cast<std::size_t>(std::ceil(0.95 * static_cast<double>(durations.size()))) - 1U;
    result.p95_ns = durations[p95];
    result.samples_per_second = static_cast<double>(batch) * 1.0e9 / result.median_ns;
    return result;
}

[[nodiscard]] TimingSummary benchmark(
    const std::filesystem::path &checkpoint,
    const M22Corpus &corpus,
    std::int64_t batch_size,
    const torch::Device &device,
    bool update,
    std::int64_t *peak_allocated,
    std::int64_t *peak_reserved)
{
    auto loaded = openttd_rl::v2::load_m22_checkpoint(checkpoint, device);
    const auto batch = make_batch(corpus, batch_size);
    const auto input = openttd_rl::v2::m22_encode_compact(batch, device);
    if (update) loaded.trainer->model()->train();
    else loaded.trainer->model()->eval();
    auto iteration = [&]() {
        if (update) {
            loaded.trainer->optimizer().zero_grad();
            const auto loss = comparison_loss(*loaded.trainer, batch, input);
            loss.backward();
            loaded.trainer->optimizer().step();
        } else {
            torch::NoGradGuard guard;
            static_cast<void>(loaded.trainer->model()->forward(input));
        }
    };
    for (int index = 0; index < kWarmups; ++index) iteration();
    if (device.is_cuda()) {
        torch::cuda::synchronize();
        c10::cuda::CUDACachingAllocator::resetPeakStats(0);
    }
    std::vector<double> durations;
    durations.reserve(kSamples);
    for (int index = 0; index < kSamples; ++index) {
        if (device.is_cuda()) torch::cuda::synchronize();
        const auto started = Clock::now();
        iteration();
        if (device.is_cuda()) torch::cuda::synchronize();
        durations.push_back(std::chrono::duration<double, std::nano>(Clock::now() - started).count());
    }
    openttd_rl::v2::require_finite_generalist(
        loaded.trainer->model(), update ? "M22 update benchmark" : "M22 inference benchmark");
    if (device.is_cuda()) {
        const auto stats = c10::cuda::CUDACachingAllocator::getDeviceStats(0);
        constexpr std::size_t aggregate = static_cast<std::size_t>(c10::CachingAllocator::StatType::AGGREGATE);
        *peak_allocated = stats.allocated_bytes[aggregate].peak;
        *peak_reserved = stats.reserved_bytes[aggregate].peak;
    }
    return summarize(std::move(durations), batch_size);
}

[[nodiscard]] BenchmarkBatch run_benchmark(
    const std::filesystem::path &checkpoint,
    const M22Corpus &corpus,
    std::int64_t batch,
    bool update)
{
    BenchmarkBatch result;
    result.batch = batch;
    result.cpu = benchmark(checkpoint, corpus, batch, torch::kCPU, update,
                           &result.peak_allocated_bytes, &result.peak_reserved_bytes);
    result.cuda = benchmark(checkpoint, corpus, batch, torch::Device(torch::kCUDA, 0), update,
                            &result.peak_allocated_bytes, &result.peak_reserved_bytes);
    result.speedup = result.cpu.median_ns / result.cuda.median_ns;
    require(std::isfinite(result.speedup) && result.speedup > 0.0 &&
            result.peak_allocated_bytes > 0 && result.peak_reserved_bytes > 0,
            "M22 benchmark result is invalid");
    return result;
}

[[nodiscard]] std::vector<std::int64_t> tensor_vector(const torch::Tensor &tensor)
{
    const auto value = tensor.to(torch::kCPU).contiguous();
    require(value.scalar_type() == torch::kInt64 && value.dim() == 1, "M22 action vector is invalid");
    std::vector<std::int64_t> result;
    const auto access = value.accessor<std::int64_t, 1>();
    for (std::int64_t index = 0; index < value.size(0); ++index) result.push_back(access[index]);
    return result;
}

[[nodiscard]] RetentionResult run_retention(const std::filesystem::path &checkpoint, const M22Corpus &corpus)
{
    using namespace openttd_rl::v2;
    const auto batch = retention_batch(corpus);
    auto cpu = load_m22_checkpoint(checkpoint, torch::kCPU);
    auto cuda = load_m22_checkpoint(checkpoint, torch::Device(torch::kCUDA, 0));
    const auto cpu_output = cpu.trainer->act(batch, true);
    const auto cuda_output = cuda.trainer->act(batch, true);
    RetentionResult result{tensor_vector(cpu_output.actions), tensor_vector(cuda_output.actions), 0.0};
    require(result.cpu_actions == result.cuda_actions, "M22 native-qualified retention actions differ by device");
    for (std::int64_t index = 0; index < kM22ProgramCount - 1; ++index) {
        const auto program = index + 1;
        require(result.cpu_actions[static_cast<std::size_t>(index)] == program,
                "M22 selected checkpoint lost a native-qualified development program");
        result.mean_reward += corpus.entry(M22CorpusSplit::Development, program).rewards[static_cast<std::size_t>(program)];
    }
    result.mean_reward /= static_cast<double>(kM22ProgramCount - 1);
    require(std::isfinite(result.mean_reward) && result.mean_reward > 0.0, "M22 retention reward is invalid");
    return result;
}

[[nodiscard]] std::string json_escape(std::string_view value)
{
    std::string result;
    for (const char character : value) {
        if (character == '\\' || character == '"') result.push_back('\\');
        result.push_back(character);
    }
    return result;
}

void write_actions(std::ostream &output, const std::vector<std::int64_t> &actions)
{
    output << '[';
    for (std::size_t index = 0; index < actions.size(); ++index) {
        if (index > 0) output << ',';
        output << actions[index];
    }
    output << ']';
}

void write_timing(std::ostream &output, const TimingSummary &value)
{
    output << "{\"median_ns\":" << value.median_ns
           << ",\"p95_ns\":" << value.p95_ns
           << ",\"samples_per_second\":" << value.samples_per_second << '}';
}

void write_benchmark_batches(std::ostream &output, const std::vector<BenchmarkBatch> &items)
{
    for (std::size_t index = 0; index < items.size(); ++index) {
        const auto &value = items[index];
        output << "{\"batch\":" << value.batch << ",\"cpu\":";
        write_timing(output, value.cpu);
        output << ",\"cuda\":";
        write_timing(output, value.cuda);
        output << ",\"speedup\":" << value.speedup
               << ",\"peak_allocated_bytes\":" << value.peak_allocated_bytes
               << ",\"peak_reserved_bytes\":" << value.peak_reserved_bytes << '}';
        if (index + 1U < items.size()) output << ',';
    }
}

void write_report(
    const Arguments &arguments,
    const DeviceDescription &device,
    const M22LoadedCheckpoint &identity,
    const std::vector<ParityResult> &parity,
    const std::vector<BenchmarkBatch> &update_benchmarks,
    const std::vector<BenchmarkBatch> &inference_benchmarks,
    const RetentionResult &retention)
{
    if (arguments.report.has_parent_path()) std::filesystem::create_directories(arguments.report.parent_path());
    std::ofstream output(arguments.report, std::ios::binary | std::ios::trunc);
    require(static_cast<bool>(output), "cannot open M22 qualification report");
    output << std::setprecision(17)
           << "{\"schema_version\":\"openttd-rl-v2-m22-device-result-1\","
           << "\"checkpoint\":{\"architecture\":\""
           << json_escape(openttd_rl::v2::generalist_architecture_name(identity.trainer->architecture()))
           << "\",\"id\":\"" << identity.checkpoint_id
           << "\",\"seed\":" << identity.trainer->run_seed()
           << ",\"update\":" << identity.trainer->counters().completed_updates << "},"
           << "\"device\":{\"name\":\"" << json_escape(device.name)
           << "\",\"compute_capability\":\"" << device.major << '.' << device.minor
           << "\",\"total_memory_bytes\":" << device.total_memory_bytes << "},"
           << "\"parity\":[";
    for (std::size_t index = 0; index < parity.size(); ++index) {
        const auto &value = parity[index];
        output << "{\"batch\":" << value.batch
               << ",\"forward_max_abs\":" << value.forward_max_abs
               << ",\"loss_max_abs\":" << value.loss_max_abs
               << ",\"gradient_max_abs\":" << value.gradient_max_abs
               << ",\"update_max_abs\":" << value.update_max_abs
               << ",\"checkpoint_max_abs\":" << value.checkpoint_max_abs
               << ",\"minimum_greedy_margin\":" << value.minimum_greedy_margin
               << ",\"identical_greedy_programs\":" << value.identical_greedy_programs << '}';
        if (index + 1U < parity.size()) output << ',';
    }
    output << "],\"benchmarks\":[{\"workload\":\"forward-backward-adam-update\","
           << "\"warmups\":" << kWarmups << ",\"samples\":" << kSamples << ",\"batches\":[";
    write_benchmark_batches(output, update_benchmarks);
    output << "]},{\"workload\":\"batched-inference\",\"warmups\":" << kWarmups
           << ",\"samples\":" << kSamples << ",\"batches\":[";
    write_benchmark_batches(output, inference_benchmarks);
    output << "]}],\"retention\":{\"split\":\"development\",\"programs\":16,\"cpu_actions\":";
    write_actions(output, retention.cpu_actions);
    output << ",\"cuda_actions\":";
    write_actions(output, retention.cuda_actions);
    output << ",\"mean_reward\":" << retention.mean_reward
           << ",\"all_programs_pass\":true,\"devices_identical\":true},"
           << "\"semantics\":{\"simulation\":\"cpu-only\","
           << "\"observation_encoding\":\"cpu-public-state-to-device-copy\","
           << "\"policy\":\"cuda:0-production-cpu-oracle\","
           << "\"dtype\":\"float32\",\"mixed_precision\":false,\"tf32\":false,"
           << "\"deterministic_algorithms\":true}}\n";
    require(static_cast<bool>(output), "cannot write M22 qualification report");
}

} // namespace

int main(int argc, char **argv)
{
    try {
        const auto arguments = parse_arguments(argc, argv);
        if (!torch::cuda::is_available()) {
            std::cerr << "M22_QUALIFICATION_GATE=FAIL class=cuda-unavailable detail=no CUDA device visible to LibTorch\n";
            return 3;
        }
        const auto device = describe_device();
        if (device.major < 12) {
            std::cerr << "M22_QUALIFICATION_GATE=FAIL class=compute-capability-unsupported detail="
                      << device.major << '.' << device.minor << '\n';
            return 5;
        }
        at::globalContext().setDeterministicAlgorithms(true, false);
        at::globalContext().setAllowTF32CuBLAS(false);
        at::globalContext().setAllowTF32CuDNN(false);
        torch::set_num_threads(6);
        const auto corpus = openttd_rl::v2::load_m22_corpus(arguments.corpus);
        const auto identity = openttd_rl::v2::load_m22_checkpoint(arguments.checkpoint, torch::kCPU);
        std::vector<ParityResult> parity;
        std::vector<BenchmarkBatch> updates;
        std::vector<BenchmarkBatch> inference;
        for (const auto batch : kBatches) {
            parity.push_back(run_parity(arguments.checkpoint, corpus, batch));
            std::cout << "M22_QUALIFICATION_PARITY batch=" << batch
                      << " forward=" << parity.back().forward_max_abs
                      << " gradient=" << parity.back().gradient_max_abs
                      << " update=" << parity.back().update_max_abs << '\n';
            updates.push_back(run_benchmark(arguments.checkpoint, corpus, batch, true));
            std::cout << "M22_QUALIFICATION_BENCHMARK workload=update batch=" << batch
                      << " speedup=" << updates.back().speedup << '\n';
            inference.push_back(run_benchmark(arguments.checkpoint, corpus, batch, false));
            std::cout << "M22_QUALIFICATION_BENCHMARK workload=inference batch=" << batch
                      << " speedup=" << inference.back().speedup << '\n';
        }
        const auto retention = run_retention(arguments.checkpoint, corpus);
        write_report(arguments, device, identity, parity, updates, inference, retention);
        std::cout << "M22_QUALIFICATION_GATE=PASS checkpoint=" << identity.checkpoint_id
                  << " programs=16 report=" << arguments.report << '\n';
        return 0;
    } catch (const c10::Error &error) {
        std::string message = error.what_without_backtrace();
        std::string lowered = message;
        std::transform(lowered.begin(), lowered.end(), lowered.begin(), [](unsigned char value) {
            return static_cast<char>(std::tolower(value));
        });
        const bool out_of_memory = lowered.find("out of memory") != std::string::npos;
        std::cerr << "M22_QUALIFICATION_GATE=FAIL class="
                  << (out_of_memory ? "cuda-out-of-memory" : "nonfinite-or-runtime")
                  << " detail=" << message << '\n';
        return out_of_memory ? 4 : 6;
    } catch (const std::exception &error) {
        std::cerr << "M22_QUALIFICATION_GATE=FAIL class=validation detail=" << error.what() << '\n';
        return 2;
    }
}
