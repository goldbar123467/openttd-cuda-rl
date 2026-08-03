#include "openttd_rl/v2/m23_equivalence.h"
#include "openttd_rl/v2/m23_onnx.h"

#include <algorithm>
#include <array>
#include <filesystem>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <string_view>

namespace {

struct Arguments {
    std::filesystem::path golden;
    std::filesystem::path monolithic_model;
    std::filesystem::path specialist_model;
    std::filesystem::path report;
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

} // namespace

int main(int argc, char **argv)
{
    try {
        const auto arguments = parse_arguments(argc, argv);
        openttd_rl::v2::M23OnnxModel monolithic(arguments.monolithic_model, "monolithic-generalist-v1");
        openttd_rl::v2::M23OnnxModel specialist(arguments.specialist_model, "specialist-router-v1");
        const auto summary = openttd_rl::v2::run_m23_onnx_equivalence(
            arguments.golden, monolithic, specialist, arguments.report, "onnxruntime-1.28.0-cpu");
        std::cout << "M23_ONNX_EQUIVALENCE=" << (summary.failures == 0 ? "PASS" : "FAIL")
                  << " cases=" << summary.cases << " failures=" << summary.failures
                  << " max_abs=" << summary.maximum_absolute << '\n';
        return summary.failures == 0 ? 0 : 2;
    } catch (const Ort::Exception &error) {
        std::cerr << "M23_ONNX_EQUIVALENCE=FAIL class=onnxruntime detail=" << error.what() << '\n';
        return 3;
    } catch (const std::exception &error) {
        std::cerr << "M23_ONNX_EQUIVALENCE=FAIL class=validation detail=" << error.what() << '\n';
        return 2;
    }
}
