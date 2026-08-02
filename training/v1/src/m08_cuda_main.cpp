#include <algorithm>
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
#include <utility>
#include <vector>

#include <unistd.h>

#include <cuda_runtime_api.h>
#include <c10/cuda/CUDACachingAllocator.h>
#include <torch/cuda.h>
#include <torch/torch.h>

#include "openttd_rl/training/multimodal_model.h"
#include "openttd_rl/training/ppo.h"

namespace {

using Clock = std::chrono::steady_clock;
using openttd_rl::training::ArchitectureKind;
using openttd_rl::training::MultiModalActorCritic;

constexpr double kForwardAbsoluteTolerance = 1e-4;
constexpr double kForwardRelativeTolerance = 1e-4;
constexpr double kLossAbsoluteTolerance = 1e-5;
constexpr double kGradientAbsoluteTolerance = 5e-4;
constexpr double kUpdateAbsoluteTolerance = 5e-4;

struct Arguments {
    std::filesystem::path report;
    bool quick = false;
    bool inject_oom = false;
};

struct DeviceDescription {
    std::string name;
    int major = 0;
    int minor = 0;
    std::uint64_t total_memory_bytes = 0;
};

struct ParityResult {
    std::string architecture;
    double forward_absolute = 0.0;
    double forward_relative = 0.0;
    double loss_absolute = 0.0;
    double gradient_absolute = 0.0;
    double updated_parameter_absolute = 0.0;
    double checkpoint_absolute = 0.0;
    std::int64_t compared_greedy_actions = 0;
    bool forward_allclose = false;
};

struct TimingSummary {
    double median_ns = 0.0;
    double p95_ns = 0.0;
    double samples_per_second = 0.0;
};

struct BenchmarkResult {
    std::int64_t batch_size = 0;
    TimingSummary cpu;
    TimingSummary cuda;
    double speedup = 0.0;
    std::int64_t peak_allocated_bytes = 0;
    std::int64_t peak_reserved_bytes = 0;
};

[[nodiscard]] Arguments parse_arguments(int argc, char **argv)
{
    Arguments arguments;
    for (int index = 1; index < argc; ++index) {
        const std::string value(argv[index]);
        if (value == "--report" && index + 1 < argc) {
            arguments.report = argv[++index];
        } else if (value == "--quick") {
            arguments.quick = true;
        } else if (value == "--inject-oom") {
            arguments.inject_oom = true;
        } else {
            throw std::invalid_argument("usage: m08_cuda_gate --report ABSOLUTE_PATH [--quick] [--inject-oom]");
        }
    }
    if (!arguments.report.is_absolute()) {
        throw std::invalid_argument("--report must name an absolute path");
    }
    return arguments;
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

[[nodiscard]] torch::Tensor make_structured(std::int64_t batch)
{
    auto values = torch::arange(
        batch * openttd_rl::training::kStructuredFeatures,
        torch::TensorOptions().dtype(torch::kFloat32));
    return torch::sin(values.reshape({batch, openttd_rl::training::kStructuredFeatures}) * 0.013F);
}

[[nodiscard]] torch::Tensor make_spatial(std::int64_t batch)
{
    auto values = torch::arange(
        batch * openttd_rl::training::kSpatialChannels * openttd_rl::training::kSpatialHeight *
            openttd_rl::training::kSpatialWidth,
        torch::TensorOptions().dtype(torch::kFloat32));
    return (values.remainder(257) / 256.0F).reshape(
        {batch,
            openttd_rl::training::kSpatialChannels,
            openttd_rl::training::kSpatialHeight,
            openttd_rl::training::kSpatialWidth});
}

[[nodiscard]] double maximum_absolute_difference(const torch::Tensor &left, const torch::Tensor &right)
{
    return (left.detach().cpu() - right.detach().cpu()).abs().max().item<double>();
}

[[nodiscard]] double maximum_relative_difference(const torch::Tensor &left, const torch::Tensor &right)
{
    const auto cpu_left = left.detach().cpu();
    const auto cpu_right = right.detach().cpu();
    return ((cpu_left - cpu_right).abs() / cpu_left.abs().clamp_min(1e-12)).max().item<double>();
}

[[nodiscard]] torch::Tensor comparison_loss(const std::pair<torch::Tensor, torch::Tensor> &output)
{
    return output.first.square().mean() + output.second.square().mean() + 0.01 * output.first.mean();
}

[[nodiscard]] torch::Tensor parity_ppo_loss(
    const std::pair<torch::Tensor, torch::Tensor> &output,
    const torch::Device &device)
{
    const auto samples = output.second.size(0);
    auto masks = torch::zeros({samples, openttd_rl::training::kActionCount},
        torch::TensorOptions().dtype(torch::kBool).device(device));
    masks.index_put_({torch::indexing::Slice(), torch::indexing::Slice(0, 5)}, true);
    const auto actions = torch::arange(samples, torch::TensorOptions().dtype(torch::kInt64).device(device)).remainder(5);
    const auto policy = openttd_rl::training::masked_categorical(output.first, masks);
    const auto selected = policy.log_probabilities.gather(1, actions.unsqueeze(1)).squeeze(1);
    const auto old_log_probabilities = selected.detach() - 0.03;
    const auto advantages = torch::linspace(-1.0, 1.0, samples, torch::TensorOptions().dtype(torch::kFloat32).device(device));
    const auto returns = torch::cos(advantages * 0.7);
    openttd_rl::training::PpoConfig config;
    return openttd_rl::training::ppo_loss(
        selected,
        old_log_probabilities,
        advantages,
        output.second,
        returns,
        policy.entropy,
        config).total;
}

void require_within(
    const torch::Tensor &cpu,
    const torch::Tensor &cuda,
    double absolute,
    double relative,
    const std::string &what)
{
    if (!torch::allclose(cpu.detach().cpu(), cuda.detach().cpu(), relative, absolute)) {
        throw std::runtime_error(
            what + " exceeded CPU/CUDA tolerance: max_absolute=" +
            std::to_string(maximum_absolute_difference(cpu, cuda)) + " max_relative=" +
            std::to_string(maximum_relative_difference(cpu, cuda)));
    }
}

[[nodiscard]] ParityResult run_parity(ArchitectureKind kind)
{
    constexpr std::uint64_t seed = 1729;
    const torch::Device cuda_device(torch::kCUDA, 0);
    MultiModalActorCritic cpu(kind, seed);
    MultiModalActorCritic accelerated(kind, seed);
    accelerated->to(cuda_device);
    torch::optim::Adam cpu_optimizer(cpu->parameters(), torch::optim::AdamOptions(3e-4).eps(1e-5));
    torch::optim::Adam cuda_optimizer(accelerated->parameters(), torch::optim::AdamOptions(3e-4).eps(1e-5));
    const auto structured = make_structured(8);
    const auto spatial = make_spatial(8);
    const auto cuda_structured = structured.to(cuda_device);
    const auto cuda_spatial = spatial.to(cuda_device);

    const auto cpu_output = cpu->forward(structured, spatial);
    const auto cuda_output = accelerated->forward(cuda_structured, cuda_spatial);
    torch::cuda::synchronize();
    require_within(cpu_output.first, cuda_output.first, kForwardAbsoluteTolerance, kForwardRelativeTolerance,
        "policy forward parity");
    require_within(cpu_output.second, cuda_output.second, kForwardAbsoluteTolerance, kForwardRelativeTolerance,
        "value forward parity");

    ParityResult result;
    result.architecture = openttd_rl::training::architecture_name(kind);
    result.forward_absolute = std::max(
        maximum_absolute_difference(cpu_output.first, cuda_output.first),
        maximum_absolute_difference(cpu_output.second, cuda_output.second));
    result.forward_relative = std::max(
        maximum_relative_difference(cpu_output.first, cuda_output.first),
        maximum_relative_difference(cpu_output.second, cuda_output.second));
    result.forward_allclose = true;
    const auto cpu_loss = parity_ppo_loss(cpu_output, torch::Device(torch::kCPU));
    const auto cuda_loss = parity_ppo_loss(cuda_output, cuda_device);
    result.loss_absolute = maximum_absolute_difference(cpu_loss, cuda_loss);
    if (result.loss_absolute > kLossAbsoluteTolerance) throw std::runtime_error("loss parity exceeded tolerance");

    cpu_loss.backward();
    cuda_loss.backward();
    torch::cuda::synchronize();
    const auto cpu_parameters = cpu->named_parameters(true);
    const auto cuda_parameters = accelerated->named_parameters(true);
    for (const auto &parameter : cpu_parameters) {
        const auto &cuda_parameter = cuda_parameters[parameter.key()];
        result.gradient_absolute = std::max(
            result.gradient_absolute,
            maximum_absolute_difference(parameter.value().grad(), cuda_parameter.grad()));
    }
    if (result.gradient_absolute > kGradientAbsoluteTolerance) {
        throw std::runtime_error("gradient parity exceeded tolerance");
    }

    cpu_optimizer.step();
    cuda_optimizer.step();
    torch::cuda::synchronize();
    const auto cpu_updated = cpu->named_parameters(true);
    const auto cuda_updated = accelerated->named_parameters(true);
    for (const auto &parameter : cpu_updated) {
        result.updated_parameter_absolute = std::max(
            result.updated_parameter_absolute,
            maximum_absolute_difference(parameter.value(), cuda_updated[parameter.key()]));
    }
    if (result.updated_parameter_absolute > kUpdateAbsoluteTolerance) {
        throw std::runtime_error("updated parameter parity exceeded tolerance");
    }

    const auto cpu_top = std::get<0>(cpu_output.first.topk(2, 1));
    const auto cpu_actions = cpu_output.first.argmax(1);
    const auto cuda_actions = cuda_output.first.argmax(1).cpu();
    const auto margins = cpu_top.index({torch::indexing::Slice(), 0}) - cpu_top.index({torch::indexing::Slice(), 1});
    for (std::int64_t row = 0; row < margins.size(0); ++row) {
        if (margins[row].item<float>() > static_cast<float>(2.0 * kForwardAbsoluteTolerance)) {
            ++result.compared_greedy_actions;
            if (cpu_actions[row].item<std::int64_t>() != cuda_actions[row].item<std::int64_t>()) {
                throw std::runtime_error("stable greedy action changed between CPU and CUDA");
            }
        }
    }

    accelerated->to(torch::kCPU);
    const auto moved_output = accelerated->forward(structured, spatial);
    const auto cpu_updated_output = cpu->forward(structured, spatial);
    result.checkpoint_absolute = std::max(
        maximum_absolute_difference(cpu_updated_output.first, moved_output.first),
        maximum_absolute_difference(cpu_updated_output.second, moved_output.second));
    require_within(cpu_updated_output.first, moved_output.first, kForwardAbsoluteTolerance, kForwardRelativeTolerance,
        "CUDA-to-CPU policy move");
    require_within(cpu_updated_output.second, moved_output.second, kForwardAbsoluteTolerance, kForwardRelativeTolerance,
        "CUDA-to-CPU value move");

    const auto checkpoint = std::filesystem::temp_directory_path() /
        ("openttd-rl-m08-canonical-" + std::to_string(::getpid()) + "-" + result.architecture + ".pt");
    torch::serialize::OutputArchive output_archive;
    accelerated->save(output_archive);
    output_archive.save_to(checkpoint.string());
    MultiModalActorCritic restored(kind, seed + 1U);
    torch::serialize::InputArchive input_archive;
    input_archive.load_from(checkpoint.string(), torch::Device(torch::kCPU));
    restored->load(input_archive);
    std::error_code ignored;
    std::filesystem::remove(checkpoint, ignored);
    const auto restored_output = restored->forward(structured, spatial);
    require_within(moved_output.first, restored_output.first, 0.0, 0.0, "canonical CPU checkpoint policy");
    require_within(moved_output.second, restored_output.second, 0.0, 0.0, "canonical CPU checkpoint value");
    return result;
}

void run_update(
    MultiModalActorCritic &model,
    torch::optim::Adam &optimizer,
    const torch::Tensor &structured,
    const torch::Tensor &spatial)
{
    optimizer.zero_grad();
    const auto output = model->forward(structured, spatial);
    auto loss = comparison_loss(output);
    loss.backward();
    optimizer.step();
}

[[nodiscard]] TimingSummary summarize(std::vector<double> durations, std::int64_t batch_size)
{
    std::sort(durations.begin(), durations.end());
    const std::size_t median_index = durations.size() / 2U;
    const std::size_t p95_index = static_cast<std::size_t>(
        std::ceil(0.95 * static_cast<double>(durations.size()))) - 1U;
    TimingSummary result;
    result.median_ns = durations[median_index];
    result.p95_ns = durations[p95_index];
    result.samples_per_second = static_cast<double>(batch_size) * 1e9 / result.median_ns;
    return result;
}

[[nodiscard]] TimingSummary benchmark_device(
    std::int64_t batch_size,
    const torch::Device &device,
    int warmup_iterations,
    int measurement_iterations,
    std::int64_t *peak_allocated_bytes,
    std::int64_t *peak_reserved_bytes)
{
    MultiModalActorCritic model(ArchitectureKind::CombinedCnnMlp, 3191);
    model->to(device);
    torch::optim::Adam optimizer(model->parameters(), torch::optim::AdamOptions(3e-4).eps(1e-5));
    const auto structured = make_structured(batch_size).to(device);
    const auto spatial = make_spatial(batch_size).to(device);
    for (int iteration = 0; iteration < warmup_iterations; ++iteration) {
        run_update(model, optimizer, structured, spatial);
    }
    if (device.is_cuda()) {
        torch::cuda::synchronize();
        c10::cuda::CUDACachingAllocator::resetPeakStats(0);
    }
    std::vector<double> durations;
    durations.reserve(static_cast<std::size_t>(measurement_iterations));
    for (int iteration = 0; iteration < measurement_iterations; ++iteration) {
        if (device.is_cuda()) torch::cuda::synchronize();
        const auto started = Clock::now();
        run_update(model, optimizer, structured, spatial);
        if (device.is_cuda()) torch::cuda::synchronize();
        const auto elapsed = std::chrono::duration<double, std::nano>(Clock::now() - started).count();
        durations.push_back(elapsed);
    }
    if (device.is_cuda()) {
        const auto stats = c10::cuda::CUDACachingAllocator::getDeviceStats(0);
        constexpr std::size_t aggregate = static_cast<std::size_t>(c10::CachingAllocator::StatType::AGGREGATE);
        *peak_allocated_bytes = stats.allocated_bytes[aggregate].peak;
        *peak_reserved_bytes = stats.reserved_bytes[aggregate].peak;
    }
    return summarize(std::move(durations), batch_size);
}

[[nodiscard]] TimingSummary benchmark_inference_device(
    std::int64_t batch_size,
    const torch::Device &device,
    int warmup_iterations,
    int measurement_iterations,
    std::int64_t *peak_allocated_bytes,
    std::int64_t *peak_reserved_bytes)
{
    MultiModalActorCritic model(ArchitectureKind::CombinedCnnMlp, 3191);
    model->to(device);
    model->eval();
    const auto structured = make_structured(batch_size).to(device);
    const auto spatial = make_spatial(batch_size).to(device);
    torch::NoGradGuard guard;
    for (int iteration = 0; iteration < warmup_iterations; ++iteration) {
        (void)model->forward(structured, spatial);
    }
    if (device.is_cuda()) {
        torch::cuda::synchronize();
        c10::cuda::CUDACachingAllocator::resetPeakStats(0);
    }
    std::vector<double> durations;
    durations.reserve(static_cast<std::size_t>(measurement_iterations));
    for (int iteration = 0; iteration < measurement_iterations; ++iteration) {
        if (device.is_cuda()) torch::cuda::synchronize();
        const auto started = Clock::now();
        (void)model->forward(structured, spatial);
        if (device.is_cuda()) torch::cuda::synchronize();
        durations.push_back(std::chrono::duration<double, std::nano>(Clock::now() - started).count());
    }
    if (device.is_cuda()) {
        const auto stats = c10::cuda::CUDACachingAllocator::getDeviceStats(0);
        constexpr std::size_t aggregate = static_cast<std::size_t>(c10::CachingAllocator::StatType::AGGREGATE);
        *peak_allocated_bytes = stats.allocated_bytes[aggregate].peak;
        *peak_reserved_bytes = stats.reserved_bytes[aggregate].peak;
    }
    return summarize(std::move(durations), batch_size);
}

[[nodiscard]] BenchmarkResult run_benchmark(
    std::int64_t batch_size,
    int warmup_iterations,
    int measurement_iterations)
{
    BenchmarkResult result;
    result.batch_size = batch_size;
    result.cpu = benchmark_device(
        batch_size,
        torch::Device(torch::kCPU),
        warmup_iterations,
        measurement_iterations,
        &result.peak_allocated_bytes,
        &result.peak_reserved_bytes);
    result.cuda = benchmark_device(
        batch_size,
        torch::Device(torch::kCUDA, 0),
        warmup_iterations,
        measurement_iterations,
        &result.peak_allocated_bytes,
        &result.peak_reserved_bytes);
    result.speedup = result.cpu.median_ns / result.cuda.median_ns;
    return result;
}

[[nodiscard]] BenchmarkResult run_inference_benchmark(
    std::int64_t batch_size,
    int warmup_iterations,
    int measurement_iterations)
{
    BenchmarkResult result;
    result.batch_size = batch_size;
    result.cpu = benchmark_inference_device(
        batch_size,
        torch::Device(torch::kCPU),
        warmup_iterations,
        measurement_iterations,
        &result.peak_allocated_bytes,
        &result.peak_reserved_bytes);
    result.cuda = benchmark_inference_device(
        batch_size,
        torch::Device(torch::kCUDA, 0),
        warmup_iterations,
        measurement_iterations,
        &result.peak_allocated_bytes,
        &result.peak_reserved_bytes);
    result.speedup = result.cpu.median_ns / result.cuda.median_ns;
    return result;
}

[[nodiscard]] std::string json_escape(const std::string &value)
{
    std::string output;
    for (const char character : value) {
        if (character == '\\' || character == '"') output.push_back('\\');
        output.push_back(character);
    }
    return output;
}

void write_timing(std::ostream &output, const TimingSummary &timing)
{
    output << "{\"median_ns\":" << timing.median_ns
           << ",\"p95_ns\":" << timing.p95_ns
           << ",\"samples_per_second\":" << timing.samples_per_second << '}';
}

void write_benchmark_batches(std::ostream &output, const std::vector<BenchmarkResult> &benchmarks)
{
    for (std::size_t index = 0; index < benchmarks.size(); ++index) {
        const auto &value = benchmarks[index];
        output << "    {\"batch_size\":" << value.batch_size << ",\"cpu\":";
        write_timing(output, value.cpu);
        output << ",\"cuda\":";
        write_timing(output, value.cuda);
        output << ",\"speedup\":" << value.speedup
               << ",\"peak_allocated_bytes\":" << value.peak_allocated_bytes
               << ",\"peak_reserved_bytes\":" << value.peak_reserved_bytes << '}';
        output << (index + 1U == benchmarks.size() ? "\n" : ",\n");
    }
}

void write_report(
    const std::filesystem::path &path,
    const DeviceDescription &device,
    const std::vector<ParityResult> &parity,
    const std::vector<BenchmarkResult> &update_benchmarks,
    const std::vector<BenchmarkResult> &inference_benchmarks,
    bool quick)
{
    if (path.has_parent_path()) std::filesystem::create_directories(path.parent_path());
    std::ofstream output(path, std::ios::binary | std::ios::trunc);
    if (!output) throw std::runtime_error("could not open CUDA gate report");
    output << std::setprecision(17)
           << "{\n  \"schema_version\":\"openttd-rl-v1-m08-cuda-gate-report-1\",\n"
           << "  \"compatibility_sha256\":\"" << openttd_rl::training::kM08CompatibilitySha256 << "\",\n"
           << "  \"mode\":\"" << (quick ? "diagnostic-quick" : "contract-full") << "\",\n"
           << "  \"device\":{\"name\":\"" << json_escape(device.name) << "\",\"compute_capability\":\""
           << device.major << '.' << device.minor << "\",\"total_memory_bytes\":" << device.total_memory_bytes << "},\n"
           << "  \"parity\":[\n";
    for (std::size_t index = 0; index < parity.size(); ++index) {
        const auto &value = parity[index];
        output << "    {\"architecture\":\"" << value.architecture
               << "\",\"forward_absolute\":" << value.forward_absolute
               << ",\"forward_relative\":" << value.forward_relative
               << ",\"loss_absolute\":" << value.loss_absolute
               << ",\"gradient_absolute\":" << value.gradient_absolute
               << ",\"updated_parameter_absolute\":" << value.updated_parameter_absolute
               << ",\"checkpoint_absolute\":" << value.checkpoint_absolute
               << ",\"compared_greedy_actions\":" << value.compared_greedy_actions
               << ",\"forward_allclose\":" << (value.forward_allclose ? "true" : "false") << '}';
        output << (index + 1U == parity.size() ? "\n" : ",\n");
    }
    output << "  ],\n  \"benchmarks\":[{\"architecture\":\"combined-cnn-mlp-v1\","
           << "\"workload\":\"forward-backward-adam-update\",\"warmup_iterations\":"
           << (quick ? 2 : 20) << ",\"measurement_iterations\":" << (quick ? 3 : 100) << ",\"batches\":[\n";
    write_benchmark_batches(output, update_benchmarks);
    const bool update_accepted = std::any_of(update_benchmarks.begin(), update_benchmarks.end(), [](const BenchmarkResult &result) {
        return result.speedup >= 1.1;
    });
    output << "  ],\"minimum_accepted_speedup\":1.1000000000000001,\"accepted\":"
           << (update_accepted ? "true" : "false")
           << "},{\"architecture\":\"combined-cnn-mlp-v1\",\"workload\":\"batched-inference\","
           << "\"warmup_iterations\":" << (quick ? 2 : 20)
           << ",\"measurement_iterations\":" << (quick ? 3 : 100) << ",\"batches\":[\n";
    write_benchmark_batches(output, inference_benchmarks);
    const bool inference_accepted = std::any_of(
        inference_benchmarks.begin(), inference_benchmarks.end(), [](const BenchmarkResult &result) {
            return result.speedup >= 1.1;
        });
    output << "  ],\"minimum_accepted_speedup\":1.1000000000000001,\"accepted\":"
           << (inference_accepted ? "true" : "false")
           << "}],\n  \"production_disposition\":{"
           << "\"openttd_simulation\":\"cpu-semantic-boundary\","
           << "\"observation_preprocessing\":\"cpu-direct-copy-no-kernel\","
           << "\"ppo_update\":\"cuda-for-measured-batches\","
           << "\"batched_inference\":\"cuda-for-measured-batches\","
           << "\"tf32\":false}\n}\n";
    if (!output) throw std::runtime_error("could not write CUDA gate report");
    if (!update_accepted || !inference_accepted) {
        throw std::runtime_error("a production tensor workload did not reach the 1.1x CUDA benefit gate");
    }
}

[[nodiscard]] bool contains_case_insensitive(std::string value, const std::string &needle)
{
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char character) {
        return static_cast<char>(std::tolower(character));
    });
    return value.find(needle) != std::string::npos;
}

} // namespace

int main(int argc, char **argv)
{
    try {
        const auto arguments = parse_arguments(argc, argv);
        if (!torch::cuda::is_available()) {
            std::cerr << "M08_CUDA_GATE=FAIL class=cuda-unavailable detail=no CUDA device visible to LibTorch\n";
            return 3;
        }
        const auto device = describe_device();
        if (device.major < 12) {
            std::cerr << "M08_CUDA_GATE=FAIL class=cuda-unsupported compute_capability="
                      << device.major << '.' << device.minor << " required=12.0\n";
            return 5;
        }
        if (arguments.inject_oom) {
            auto injection = torch::empty(
                {static_cast<std::int64_t>(device.total_memory_bytes) * 2},
                torch::TensorOptions().dtype(torch::kUInt8).device(torch::Device(torch::kCUDA, 0)));
            injection.fill_(1);
            torch::cuda::synchronize();
            throw std::runtime_error("injected CUDA OOM allocation unexpectedly succeeded");
        }
        at::globalContext().setAllowTF32CuBLAS(false);
        at::globalContext().setAllowTF32CuDNN(false);
        torch::set_num_threads(arguments.quick ? 4 : std::max(1, torch::get_num_threads()));
        std::vector<ParityResult> parity;
        for (const auto kind : {
                 ArchitectureKind::StructuredMlp,
                 ArchitectureKind::SpatialCnn,
                 ArchitectureKind::CombinedCnnMlp,
             }) {
            parity.push_back(run_parity(kind));
        }
        const std::vector<std::int64_t> batches = arguments.quick
            ? std::vector<std::int64_t>{1, 64}
            : std::vector<std::int64_t>{1, 4, 16, 64, 256, 1024};
        const int warmup_iterations = arguments.quick ? 2 : 20;
        const int measurement_iterations = arguments.quick ? 3 : 100;
        std::vector<BenchmarkResult> benchmarks;
        std::vector<BenchmarkResult> inference_benchmarks;
        for (const auto batch : batches) {
            benchmarks.push_back(run_benchmark(batch, warmup_iterations, measurement_iterations));
            std::cout << "M08_CUDA_BENCHMARK workload=update batch=" << batch
                      << " speedup=" << benchmarks.back().speedup << '\n';
            inference_benchmarks.push_back(run_inference_benchmark(batch, warmup_iterations, measurement_iterations));
            std::cout << "M08_CUDA_BENCHMARK workload=inference batch=" << batch
                      << " speedup=" << inference_benchmarks.back().speedup << '\n';
        }
        write_report(arguments.report, device, parity, benchmarks, inference_benchmarks, arguments.quick);
        std::cout << "M08_CUDA_GATE=PASS architectures=3 batches=" << batches.size()
                  << " report=" << arguments.report.string() << '\n';
        return 0;
    } catch (const c10::Error &error) {
        const bool out_of_memory = contains_case_insensitive(error.what_without_backtrace(), "out of memory");
        std::cerr << "M08_CUDA_GATE=FAIL class=" << (out_of_memory ? "cuda-out-of-memory" : "cuda-runtime-error")
                  << " detail=" << error.what_without_backtrace() << '\n';
        return out_of_memory ? 4 : 6;
    } catch (const std::exception &error) {
        std::cerr << "M08_CUDA_GATE=FAIL class=validation-error detail=" << error.what() << '\n';
        return 2;
    }
}
