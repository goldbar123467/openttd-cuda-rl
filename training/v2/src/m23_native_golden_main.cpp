#include "openttd_rl/v2/m22_evaluation.h"
#include "openttd_rl/v2/m23_deployment.h"
#include "openttd_rl/v2/m23_golden.h"

#include <algorithm>
#include <array>
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <filesystem>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <sys/stat.h>
#include <torch/torch.h>
#include <unistd.h>
#include <vector>

namespace {

struct Arguments {
    std::filesystem::path monolithic_checkpoint;
    std::filesystem::path specialist_checkpoint;
    std::filesystem::path output;
    std::filesystem::path report;
};

[[nodiscard]] Arguments parse_arguments(int argc, char **argv)
{
    if (argc != 9) throw std::invalid_argument(
        "usage: m23_native_golden --monolithic-checkpoint ABS --specialist-checkpoint ABS --output NEW_ABS --report NEW_ABS");
    std::map<std::string, std::filesystem::path> values;
    for (int index = 1; index < argc; index += 2) {
        if (!values.emplace(argv[index], argv[index + 1]).second) {
            throw std::invalid_argument("M23 native golden argument is duplicated");
        }
    }
    constexpr std::array<std::string_view, 4> expected = {
        "--monolithic-checkpoint", "--specialist-checkpoint", "--output", "--report",
    };
    if (values.size() != expected.size() || !std::all_of(expected.begin(), expected.end(), [&](std::string_view key) {
        return values.contains(std::string(key));
    })) throw std::invalid_argument("M23 native golden argument inventory is incomplete");
    Arguments result{
        values.at("--monolithic-checkpoint"), values.at("--specialist-checkpoint"),
        values.at("--output"), values.at("--report"),
    };
    if (!result.monolithic_checkpoint.is_absolute() || !result.specialist_checkpoint.is_absolute() ||
        !result.output.is_absolute() || !result.report.is_absolute() ||
        !std::filesystem::is_directory(result.monolithic_checkpoint) ||
        !std::filesystem::is_directory(result.specialist_checkpoint) ||
        std::filesystem::exists(result.output) || std::filesystem::exists(result.report) ||
        result.output.parent_path() != result.report.parent_path() ||
        !std::filesystem::is_directory(result.output.parent_path())) {
        throw std::invalid_argument("M23 native golden path contract failed");
    }
    return result;
}

template <typename Value>
[[nodiscard]] std::vector<Value> tensor_vector(const torch::Tensor &tensor, torch::ScalarType type)
{
    const auto value = tensor.detach().to(torch::kCPU).contiguous().reshape({-1});
    if (value.scalar_type() != type) throw std::runtime_error("M23 native golden tensor dtype drifted");
    const auto *begin = value.data_ptr<Value>();
    return std::vector<Value>(begin, begin + value.numel());
}

[[nodiscard]] torch::Tensor float_tensor(std::vector<float> &values, std::uint32_t batch, std::int64_t width)
{
    return torch::from_blob(values.data(), {static_cast<std::int64_t>(batch), width}, torch::kFloat32).clone();
}

[[nodiscard]] torch::Tensor bool_tensor(const std::vector<std::uint8_t> &values, std::uint32_t batch, std::int64_t width)
{
    auto result = torch::zeros({static_cast<std::int64_t>(batch), width}, torch::kBool);
    auto accessor = result.accessor<bool, 2>();
    for (std::uint32_t row = 0; row < batch; ++row) {
        for (std::int64_t column = 0; column < width; ++column) {
            accessor[static_cast<std::int64_t>(row)][column] =
                values[static_cast<std::size_t>(row) * static_cast<std::size_t>(width) +
                    static_cast<std::size_t>(column)] != 0;
        }
    }
    return result;
}

[[nodiscard]] torch::Tensor reset_tensor(const std::vector<std::uint8_t> &values)
{
    auto result = torch::zeros({static_cast<std::int64_t>(values.size())}, torch::kBool);
    auto accessor = result.accessor<bool, 1>();
    for (std::size_t index = 0; index < values.size(); ++index) {
        accessor[static_cast<std::int64_t>(index)] = values[index] != 0;
    }
    return result;
}

void append_records(
    std::vector<openttd_rl::v2::M23GoldenRecord> &records,
    openttd_rl::v2::M23GoldenArchitecture architecture,
    const std::filesystem::path &checkpoint)
{
    using namespace openttd_rl::v2;
    auto policy = load_m22_evaluation_policy(checkpoint, torch::kCPU);
    const auto expected_architecture = architecture == M23GoldenArchitecture::Monolithic ?
        GeneralistArchitecture::Monolithic : GeneralistArchitecture::SpecialistRouter;
    if (policy.architecture != expected_architecture) {
        throw std::invalid_argument("M23 native golden checkpoint architecture mismatch");
    }
    auto cases = generate_m23_golden_cases(architecture);
    std::array<std::vector<float>, 2> carried;
    for (auto &definition : cases) {
        std::vector<float> hidden = definition.initial_hidden;
        if (definition.hidden_mode == M23HiddenMode::Carry) {
            if (definition.sequence >= carried.size() || carried[definition.sequence].size() != hidden.size()) {
                throw std::runtime_error("M23 recurrent case lacks the exact preceding hidden state");
            }
            hidden = carried[definition.sequence];
        }
        auto features = float_tensor(definition.public_features, definition.batch, kM23PublicFeatureCount);
        auto mask = bool_tensor(definition.program_mask, definition.batch, kM22ProgramCount);
        auto hidden_tensor = float_tensor(hidden, definition.batch, kHiddenSize);
        auto reset = reset_tensor(definition.recurrent_reset);
        const M23DeploymentBatch batch{features, mask, hidden_tensor, reset};
        torch::NoGradGuard guard;
        const auto output = policy.model->forward(m23_deployment_input(batch, torch::kCPU));
        const auto actions = output.program_logits.argmax(1);
        M23GoldenRecord record{
            std::move(definition),
            std::move(hidden),
            tensor_vector<float>(output.program_logits, torch::kFloat32),
            tensor_vector<float>(output.program_value, torch::kFloat32),
            tensor_vector<float>(output.next_hidden, torch::kFloat32),
            tensor_vector<std::int64_t>(actions, torch::kInt64),
        };
        validate_m23_golden_record(record);
        if (record.definition.case_class == M23GoldenClass::RecurrentSequence) {
            carried[record.definition.sequence] = record.next_hidden;
        }
        records.push_back(std::move(record));
    }
}

void write_report(const Arguments &arguments, const std::vector<openttd_rl::v2::M23GoldenRecord> &records)
{
    std::size_t rows = 0;
    for (const auto &record : records) rows += record.definition.batch;
    std::ostringstream output;
    output << "{\"architectures\":[\"monolithic-generalist-v1\",\"specialist-router-v1\"],"
           << "\"cases\":" << records.size() << ",\"file\":{\"bytes\":"
           << std::filesystem::file_size(arguments.output) << ",\"sha256\":\""
           << openttd_rl::v2::m23_sha256_file(arguments.output) << "\"},\"rows\":" << rows
           << ",\"schema_version\":\"openttd-rl-v2-m23-native-golden-report-1\",\"status\":\"PASS\"}\n";
    const auto value = output.str();
    const int descriptor = ::open(arguments.report.c_str(),
        O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, S_IRUSR | S_IWUSR);
    if (descriptor < 0) throw std::runtime_error("cannot create M23 native golden report: " +
        std::string(std::strerror(errno)));
    std::size_t written = 0;
    while (written < value.size()) {
        const auto count = ::write(descriptor, value.data() + written, value.size() - written);
        if (count <= 0) {
            ::close(descriptor);
            throw std::runtime_error("cannot write M23 native golden report");
        }
        written += static_cast<std::size_t>(count);
    }
    if (::fsync(descriptor) != 0 || ::close(descriptor) != 0) {
        throw std::runtime_error("cannot sync or close M23 native golden report");
    }
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
        std::vector<openttd_rl::v2::M23GoldenRecord> records;
        records.reserve(48);
        append_records(records, openttd_rl::v2::M23GoldenArchitecture::Monolithic,
            arguments.monolithic_checkpoint);
        append_records(records, openttd_rl::v2::M23GoldenArchitecture::Specialist,
            arguments.specialist_checkpoint);
        openttd_rl::v2::write_m23_golden_file(arguments.output, records);
        const auto reread = openttd_rl::v2::read_m23_golden_file(arguments.output);
        if (reread.size() != records.size()) throw std::runtime_error("M23 native golden round trip lost cases");
        write_report(arguments, records);
        std::cout << "M23_NATIVE_GOLDEN=PASS cases=" << records.size()
                  << " sha256=" << openttd_rl::v2::m23_sha256_file(arguments.output) << '\n';
        return 0;
    } catch (const c10::Error &error) {
        std::cerr << "M23_NATIVE_GOLDEN=FAIL class=runtime detail=" << error.what_without_backtrace() << '\n';
        return 3;
    } catch (const std::exception &error) {
        std::cerr << "M23_NATIVE_GOLDEN=FAIL class=validation detail=" << error.what() << '\n';
        return 2;
    }
}
