#include "openttd_rl/v2/m23_golden.h"
#include "openttd_rl/v2/m23_onnx.h"

#include <algorithm>
#include <array>
#include <cerrno>
#include <cmath>
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
#include <unistd.h>
#include <vector>

namespace {

constexpr double kAbsoluteTolerance = 0.00005;
constexpr double kRelativeTolerance = 0.00005;

struct Arguments {
    std::filesystem::path golden;
    std::filesystem::path monolithic_model;
    std::filesystem::path specialist_model;
    std::filesystem::path report;
};

struct ErrorSummary {
    double maximum_absolute{};
    double maximum_relative{};
    std::size_t failures{};
};

struct CaseResult {
    std::string case_id;
    std::uint32_t batch{};
    double logits_absolute{};
    double logits_relative{};
    double value_absolute{};
    double value_relative{};
    double hidden_absolute{};
    double hidden_relative{};
    double hidden_input_absolute{};
    bool action_exact{};
    bool passed{};
};

void require(bool condition, const char *message)
{
    if (!condition) throw std::invalid_argument(message);
}

[[nodiscard]] Arguments parse_arguments(int argc, char **argv)
{
    if (argc != 9) throw std::invalid_argument(
        "usage: m23_onnx_evaluator --golden ABS --monolithic-model ABS --specialist-model ABS --report NEW_ABS");
    std::map<std::string, std::filesystem::path> values;
    for (int index = 1; index < argc; index += 2) {
        if (!values.emplace(argv[index], argv[index + 1]).second) {
            throw std::invalid_argument("M23 ONNX evaluator argument is duplicated");
        }
    }
    constexpr std::array<std::string_view, 4> expected = {
        "--golden", "--monolithic-model", "--specialist-model", "--report",
    };
    require(values.size() == expected.size() && std::all_of(expected.begin(), expected.end(), [&](std::string_view key) {
        return values.contains(std::string(key));
    }), "M23 ONNX evaluator argument inventory is incomplete");
    Arguments result{
        values.at("--golden"), values.at("--monolithic-model"), values.at("--specialist-model"), values.at("--report"),
    };
    require(result.golden.is_absolute() && result.monolithic_model.is_absolute() &&
            result.specialist_model.is_absolute() && result.report.is_absolute() &&
            std::filesystem::is_regular_file(result.golden) &&
            std::filesystem::is_regular_file(result.monolithic_model) &&
            std::filesystem::is_regular_file(result.specialist_model) &&
            !std::filesystem::exists(result.report) &&
            std::filesystem::is_directory(result.report.parent_path()),
        "M23 ONNX evaluator path contract failed");
    return result;
}

[[nodiscard]] ErrorSummary compare(const std::vector<float> &actual, const std::vector<float> &expected)
{
    require(actual.size() == expected.size(), "M23 ONNX comparison tensor size drifted");
    ErrorSummary result;
    for (std::size_t index = 0; index < actual.size(); ++index) {
        const double absolute = std::abs(static_cast<double>(actual[index]) - static_cast<double>(expected[index]));
        const double scale = std::max(std::abs(static_cast<double>(expected[index])), 1.0e-12);
        const double relative = absolute / scale;
        result.maximum_absolute = std::max(result.maximum_absolute, absolute);
        result.maximum_relative = std::max(result.maximum_relative, relative);
        if (absolute > kAbsoluteTolerance + kRelativeTolerance * std::abs(static_cast<double>(expected[index]))) {
            ++result.failures;
        }
    }
    return result;
}

void write_report(
    const Arguments &arguments,
    const std::vector<CaseResult> &cases,
    const ErrorSummary &logits,
    const ErrorSummary &values,
    const ErrorSummary &hidden,
    const ErrorSummary &hidden_input,
    std::size_t action_failures,
    std::size_t failures)
{
    std::ostringstream output;
    output << std::setprecision(12)
           << "{\"cases\":[";
    for (std::size_t index = 0; index < cases.size(); ++index) {
        if (index > 0) output << ',';
        const auto &item = cases[index];
        output << "{\"action_exact\":" << (item.action_exact ? "true" : "false")
               << ",\"batch\":" << item.batch << ",\"case_id\":\"" << item.case_id
               << "\",\"hidden_absolute\":" << item.hidden_absolute
               << ",\"hidden_input_absolute\":" << item.hidden_input_absolute
               << ",\"hidden_relative\":" << item.hidden_relative
               << ",\"logits_absolute\":" << item.logits_absolute
               << ",\"logits_relative\":" << item.logits_relative
               << ",\"passed\":" << (item.passed ? "true" : "false")
               << ",\"value_absolute\":" << item.value_absolute
               << ",\"value_relative\":" << item.value_relative << '}';
    }
    output << "],\"failure_counts\":{\"action\":" << action_failures
           << ",\"float\":" << (logits.failures + values.failures + hidden.failures)
           << ",\"total\":" << failures << "},\"golden\":{\"sha256\":\""
           << openttd_rl::v2::m23_sha256_file(arguments.golden) << "\"},\"maximum_error\":{"
           << "\"hidden_absolute\":" << hidden.maximum_absolute
           << ",\"hidden_input_absolute\":" << hidden_input.maximum_absolute
           << ",\"hidden_input_relative\":" << hidden_input.maximum_relative
           << ",\"hidden_relative\":" << hidden.maximum_relative
           << ",\"logits_absolute\":" << logits.maximum_absolute
           << ",\"logits_relative\":" << logits.maximum_relative
           << ",\"value_absolute\":" << values.maximum_absolute
           << ",\"value_relative\":" << values.maximum_relative
           << "},\"models\":{\"monolithic_sha256\":\""
           << openttd_rl::v2::m23_sha256_file(arguments.monolithic_model)
           << "\",\"specialist_sha256\":\""
           << openttd_rl::v2::m23_sha256_file(arguments.specialist_model)
           << "\"},\"runtime\":\"onnxruntime-1.28.0-cpu\","
           << "\"schema_version\":\"openttd-rl-v2-m23-onnx-equivalence-report-1\",\"status\":\""
           << (failures == 0 ? "PASS" : "FAIL") << "\",\"tolerance\":{\"absolute\":"
           << kAbsoluteTolerance << ",\"relative\":" << kRelativeTolerance << "}}\n";
    const auto value = output.str();
    const int descriptor = ::open(arguments.report.c_str(),
        O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, S_IRUSR | S_IWUSR);
    if (descriptor < 0) throw std::runtime_error("cannot create M23 ONNX report: " + std::string(std::strerror(errno)));
    std::size_t written = 0;
    while (written < value.size()) {
        const auto count = ::write(descriptor, value.data() + written, value.size() - written);
        if (count <= 0) {
            ::close(descriptor);
            throw std::runtime_error("cannot write M23 ONNX report");
        }
        written += static_cast<std::size_t>(count);
    }
    if (::fsync(descriptor) != 0 || ::close(descriptor) != 0) {
        throw std::runtime_error("cannot sync or close M23 ONNX report");
    }
}

} // namespace

int main(int argc, char **argv)
{
    try {
        const auto arguments = parse_arguments(argc, argv);
        const auto golden = openttd_rl::v2::read_m23_golden_file(arguments.golden);
        openttd_rl::v2::M23OnnxModel monolithic(arguments.monolithic_model, "monolithic-generalist-v1");
        openttd_rl::v2::M23OnnxModel specialist(arguments.specialist_model, "specialist-router-v1");
        std::array<std::array<std::vector<float>, 2>, 2> carried;
        std::vector<CaseResult> case_results;
        ErrorSummary logits_summary;
        ErrorSummary value_summary;
        ErrorSummary hidden_summary;
        ErrorSummary hidden_input_summary;
        std::size_t action_failures = 0;
        std::size_t failures = 0;
        for (const auto &record : golden) {
            const auto architecture = static_cast<std::size_t>(record.definition.architecture);
            auto &model = architecture == 0 ? monolithic : specialist;
            std::vector<float> hidden = record.definition.initial_hidden;
            if (record.definition.hidden_mode == openttd_rl::v2::M23HiddenMode::Carry) {
                require(record.definition.sequence < 2 &&
                        carried[architecture][record.definition.sequence].size() == hidden.size(),
                    "M23 ONNX recurrent case lacks the preceding runtime hidden state");
                hidden = carried[architecture][record.definition.sequence];
            }
            const auto output = model.run(record.definition.batch, record.definition.public_features,
                record.definition.program_mask, hidden, record.definition.recurrent_reset);
            const auto logits = compare(output.program_logits, record.program_logits);
            const auto values = compare(output.program_value, record.program_value);
            const auto next_hidden = compare(output.next_hidden, record.next_hidden);
            const auto input_hidden = compare(hidden, record.hidden_input);
            const bool actions = output.greedy_program == record.greedy_program;
            const auto case_failures = logits.failures + values.failures + next_hidden.failures + (actions ? 0U : 1U);
            case_results.push_back({
                record.definition.case_id,
                record.definition.batch,
                logits.maximum_absolute,
                logits.maximum_relative,
                values.maximum_absolute,
                values.maximum_relative,
                next_hidden.maximum_absolute,
                next_hidden.maximum_relative,
                input_hidden.maximum_absolute,
                actions,
                case_failures == 0,
            });
            for (auto [summary, current] : std::array<std::pair<ErrorSummary *, const ErrorSummary *>, 4>{
                     std::pair{&logits_summary, &logits}, std::pair{&value_summary, &values},
                     std::pair{&hidden_summary, &next_hidden}, std::pair{&hidden_input_summary, &input_hidden},
                 }) {
                summary->maximum_absolute = std::max(summary->maximum_absolute, current->maximum_absolute);
                summary->maximum_relative = std::max(summary->maximum_relative, current->maximum_relative);
                summary->failures += current->failures;
            }
            action_failures += actions ? 0U : 1U;
            failures += case_failures;
            if (record.definition.case_class == openttd_rl::v2::M23GoldenClass::RecurrentSequence) {
                carried[architecture][record.definition.sequence] = output.next_hidden;
            }
        }
        write_report(arguments, case_results, logits_summary, value_summary, hidden_summary,
            hidden_input_summary, action_failures, failures);
        std::cout << "M23_ONNX_EQUIVALENCE=" << (failures == 0 ? "PASS" : "FAIL")
                  << " cases=" << case_results.size() << " failures=" << failures
                  << " max_abs=" << std::max({logits_summary.maximum_absolute, value_summary.maximum_absolute,
                      hidden_summary.maximum_absolute}) << '\n';
        return failures == 0 ? 0 : 2;
    } catch (const Ort::Exception &error) {
        std::cerr << "M23_ONNX_EQUIVALENCE=FAIL class=onnxruntime detail=" << error.what() << '\n';
        return 3;
    } catch (const std::exception &error) {
        std::cerr << "M23_ONNX_EQUIVALENCE=FAIL class=validation detail=" << error.what() << '\n';
        return 2;
    }
}
