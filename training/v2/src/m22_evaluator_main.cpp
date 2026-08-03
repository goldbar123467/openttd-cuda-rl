#include "openttd_rl/v2/m22_evaluation.h"

#include <algorithm>
#include <array>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <fcntl.h>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <sys/stat.h>
#include <torch/cuda.h>
#include <torch/torch.h>
#include <unistd.h>
#include <utility>
#include <vector>

namespace {

constexpr std::array<std::string_view, openttd_rl::v2::kM22ProgramCount> kPrograms = {
    "wait", "road-passenger", "road-cargo", "rail-passenger", "rail-freight", "ship-natural",
    "ship-constructed", "air-service", "air-helicopter", "multimodal-transfer", "mode-router",
    "competition-head-to-head", "calendar-inspect", "authority-economy", "event-recovery",
    "gamescript-response", "content-discovery",
};

struct Arguments {
    std::filesystem::path checkpoint;
    std::filesystem::path report;
    torch::Device device{torch::kCPU};
    openttd_rl::v2::M22FinalPublicState state;
};

[[nodiscard]] std::uint32_t parse_u32(const std::string &value, const char *name)
{
    try {
        std::size_t consumed = 0;
        const auto parsed = std::stoul(value, &consumed);
        if (consumed != value.size() || parsed > UINT32_MAX) throw std::invalid_argument("range");
        return static_cast<std::uint32_t>(parsed);
    } catch (const std::exception &) {
        throw std::invalid_argument(std::string("invalid M22 evaluator ") + name);
    }
}

[[nodiscard]] Arguments parse_arguments(int argc, char **argv)
{
    if (argc % 2 == 0) throw std::invalid_argument("M22 evaluator arguments must be unique key/value pairs");
    std::map<std::string, std::string> values;
    for (int index = 1; index < argc; index += 2) {
        if (index + 1 >= argc || !values.emplace(argv[index], argv[index + 1]).second) {
            throw std::invalid_argument("M22 evaluator argument is absent or duplicated");
        }
    }
    constexpr std::array<std::string_view, 13> expected = {
        "--checkpoint", "--report", "--device", "--task", "--transport-mode", "--climate", "--map-width",
        "--map-height", "--cargo", "--opponent", "--native-probe", "--source-gate", "--policy-split",
    };
    if (values.size() != expected.size() || !std::all_of(expected.begin(), expected.end(), [&](std::string_view key) {
        return values.contains(std::string(key));
    })) {
        throw std::invalid_argument(
            "usage: m22_evaluator --checkpoint ABS --report NEW_ABS --device cpu|cuda:0 --task VALUE "
            "--transport-mode VALUE --climate VALUE --map-width N --map-height N --cargo VALUE "
            "--opponent VALUE --native-probe VALUE --source-gate G15..G21 --policy-split final");
    }
    Arguments result;
    result.checkpoint = std::filesystem::path(values.at("--checkpoint"));
    result.report = std::filesystem::path(values.at("--report"));
    if (values.at("--device") == "cpu") result.device = torch::kCPU;
    else if (values.at("--device") == "cuda:0") result.device = torch::Device(torch::kCUDA, 0);
    else throw std::invalid_argument("M22 evaluator device must be cpu or cuda:0");
    if (values.at("--policy-split") != "final") throw std::invalid_argument("M22 evaluator accepts only the final split");
    result.state = {
        values.at("--task"), values.at("--transport-mode"), values.at("--climate"),
        parse_u32(values.at("--map-width"), "map width"), parse_u32(values.at("--map-height"), "map height"),
        values.at("--cargo"), values.at("--opponent"), values.at("--native-probe"), values.at("--source-gate"),
    };
    if (!result.checkpoint.is_absolute() || !result.report.is_absolute() ||
        !std::filesystem::is_directory(result.checkpoint) || std::filesystem::exists(result.report) ||
        std::filesystem::is_symlink(result.report)) {
        throw std::invalid_argument("M22 evaluator checkpoint/report path contract failed");
    }
    return result;
}

[[nodiscard]] std::string json_escape(std::string_view value)
{
    std::string result;
    result.reserve(value.size());
    for (const char raw_character : value) {
        const auto character = static_cast<unsigned char>(raw_character);
        if (character == '\\' || character == '"') {
            result.push_back('\\');
            result.push_back(static_cast<char>(character));
        } else if (character < 0x20U || character > 0x7eU) {
            throw std::invalid_argument("M22 evaluator report string is not printable ASCII");
        } else {
            result.push_back(static_cast<char>(character));
        }
    }
    return result;
}

void write_new(const std::filesystem::path &path, const std::string &value)
{
    if (path.has_parent_path() && !std::filesystem::is_directory(path.parent_path())) {
        throw std::invalid_argument("M22 evaluator report parent does not exist");
    }
    const int descriptor = ::open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, S_IRUSR | S_IWUSR);
    if (descriptor < 0) {
        throw std::runtime_error("cannot create M22 evaluator report: " + std::string(std::strerror(errno)));
    }
    try {
        std::size_t written = 0;
        while (written < value.size()) {
            const auto count = ::write(descriptor, value.data() + written, value.size() - written);
            if (count <= 0) throw std::runtime_error("cannot write M22 evaluator report");
            written += static_cast<std::size_t>(count);
        }
        if (::fsync(descriptor) != 0) throw std::runtime_error("cannot sync M22 evaluator report");
    } catch (...) {
        ::close(descriptor);
        throw;
    }
    if (::close(descriptor) != 0) throw std::runtime_error("cannot close M22 evaluator report");
}

void write_float_vector(std::ostream &output, const torch::Tensor &value)
{
    const auto cpu = value.detach().to(torch::kCPU).contiguous().reshape({-1});
    if (cpu.scalar_type() != torch::kFloat32 || !torch::isfinite(cpu).all().item<bool>()) {
        throw std::runtime_error("M22 evaluator output vector is nonfinite or not float32");
    }
    const auto values = cpu.accessor<float, 1>();
    output << '[';
    for (std::int64_t index = 0; index < cpu.size(0); ++index) {
        if (index > 0) output << ',';
        output << values[index];
    }
    output << ']';
}

void write_bool_vector(std::ostream &output, const torch::Tensor &value)
{
    const auto cpu = value.to(torch::kCPU).contiguous().reshape({-1});
    if (cpu.scalar_type() != torch::kBool) throw std::runtime_error("M22 evaluator mask is not boolean");
    const auto values = cpu.accessor<bool, 1>();
    output << '[';
    for (std::int64_t index = 0; index < cpu.size(0); ++index) {
        if (index > 0) output << ',';
        output << (values[index] ? "true" : "false");
    }
    output << ']';
}

void write_report(
    const Arguments &arguments,
    const openttd_rl::v2::M22EvaluationPolicy &policy,
    const openttd_rl::v2::M22EvaluationBatch &batch,
    const openttd_rl::v2::GeneralistPolicyOutput &output,
    std::int64_t action)
{
    if (action < 0 || action >= openttd_rl::v2::kM22ProgramCount ||
        !batch.program_mask.index({0, action}).item<bool>()) {
        throw std::runtime_error("M22 evaluator selected an illegal program");
    }
    const auto legal_active = batch.program_mask.index({0, torch::indexing::Slice(1, openttd_rl::v2::kM22ProgramCount)})
        .to(torch::kInt64).argmax().item<std::int64_t>() + 1;
    if (legal_active <= 0 || legal_active >= openttd_rl::v2::kM22ProgramCount) {
        throw std::runtime_error("M22 evaluator public capability projection is invalid");
    }
    std::ostringstream report;
    report << std::setprecision(9)
           << "{\"checkpoint\":{\"architecture\":\""
           << openttd_rl::v2::generalist_architecture_name(policy.architecture)
           << "\",\"id\":\"" << policy.checkpoint_id << "\",\"run_seed\":" << policy.run_seed
           << "},\"execution\":{\"device\":\"" << arguments.device.str()
           << "\",\"greedy_masked\":true,\"optimizer_constructed\":false,"
           << "\"optimizer_deserialized\":false,\"optimizer_path_opened\":false,"
           << "\"recurrent_reset\":true},\"policy\":{\"action\":\"" << kPrograms[static_cast<std::size_t>(action)]
           << "\",\"action_index\":" << action << ",\"legal_active_program\":\""
           << kPrograms[static_cast<std::size_t>(legal_active)] << "\",\"legal_active_index\":" << legal_active
           << ",\"logits\":";
    write_float_vector(report, output.program_logits);
    report << ",\"next_hidden\":";
    write_float_vector(report, output.next_hidden);
    report << ",\"value\":" << output.program_value.item<float>() << "},\"public_state\":{\"cargo\":\""
           << json_escape(arguments.state.cargo) << "\",\"climate\":\"" << json_escape(arguments.state.climate)
           << "\",\"map_height\":" << arguments.state.map_height << ",\"map_width\":" << arguments.state.map_width
           << ",\"native_probe\":\"" << json_escape(arguments.state.native_probe) << "\",\"opponent\":\""
           << json_escape(arguments.state.opponent) << "\",\"source_gate\":\""
           << json_escape(arguments.state.source_gate) << "\",\"task\":\"" << json_escape(arguments.state.task)
           << "\",\"transport_mode\":\"" << json_escape(arguments.state.transport_mode)
           << "\"},\"schema_version\":\"openttd-rl-v2-m22-evaluator-report-1\",\"status\":\"PASS\","
           << "\"tensor_input\":{\"program_mask\":";
    write_bool_vector(report, batch.program_mask);
    report << ",\"public_features\":";
    write_float_vector(report, batch.public_features);
    report << "}}\n";
    write_new(arguments.report, report.str());
}

} // namespace

int main(int argc, char **argv)
{
    try {
        const auto arguments = parse_arguments(argc, argv);
        at::globalContext().setDeterministicAlgorithms(true, false);
        at::globalContext().setAllowTF32CuBLAS(false);
        at::globalContext().setAllowTF32CuDNN(false);
        torch::set_num_threads(1);
        auto policy = openttd_rl::v2::load_m22_evaluation_policy(arguments.checkpoint, arguments.device);
        const auto batch = openttd_rl::v2::encode_m22_final_public_state(arguments.state);
        torch::NoGradGuard guard;
        const auto output = policy.model->forward(openttd_rl::v2::m22_evaluation_input(batch, arguments.device));
        if (arguments.device.is_cuda()) torch::cuda::synchronize();
        const auto action = output.program_logits.argmax(1).item<std::int64_t>();
        write_report(arguments, policy, batch, output, action);
        std::cout << "M22_EVALUATOR=PASS checkpoint=" << policy.checkpoint_id
                  << " action=" << kPrograms[static_cast<std::size_t>(action)] << '\n';
        return 0;
    } catch (const c10::Error &error) {
        std::cerr << "M22_EVALUATOR=FAIL class=runtime detail=" << error.what_without_backtrace() << '\n';
        return 3;
    } catch (const std::exception &error) {
        std::cerr << "M22_EVALUATOR=FAIL class=validation detail=" << error.what() << '\n';
        return 2;
    }
}
