#include "openttd_rl/v2/m23_onnx.h"

#include <cmath>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

struct Arguments {
    std::filesystem::path package;
    std::string probe;
};

[[nodiscard]] Arguments parse_arguments(int argc, char **argv)
{
    if (argc != 5 || std::string(argv[1]) != "--package" || std::string(argv[3]) != "--probe") {
        throw std::invalid_argument(
            "usage: m23_package_smoke --package ABS --probe load|valid|nonfinite|all-illegal|batch-zero|batch-over-32");
    }
    Arguments result{argv[2], argv[4]};
    if (!result.package.is_absolute()) throw std::invalid_argument("M23 package smoke path must be absolute");
    return result;
}

void run_probe(openttd_rl::v2::M23DeploymentPackage &package, const std::string &probe)
{
    if (probe == "load") return;
    std::uint32_t batch = probe == "batch-zero" ? 0U : probe == "batch-over-32" ? 33U : 1U;
    std::vector<float> features(static_cast<std::size_t>(batch) * 32U, 0.0F);
    std::vector<std::uint8_t> mask(static_cast<std::size_t>(batch) * 17U, 0U);
    std::vector<float> hidden(static_cast<std::size_t>(batch) * 256U, 0.0F);
    std::vector<std::uint8_t> reset(batch, 1U);
    for (std::uint32_t row = 0; row < batch; ++row) mask[static_cast<std::size_t>(row) * 17U] = 1U;
    if (probe == "nonfinite") features[0] = std::numeric_limits<float>::quiet_NaN();
    if (probe == "all-illegal") mask.assign(17U, 0U);
    if (probe != "valid" && probe != "nonfinite" && probe != "all-illegal" && probe != "batch-zero" &&
        probe != "batch-over-32") throw std::invalid_argument("M23 package smoke probe is unknown");
    const auto output = package.model().run(batch, features, mask, hidden, reset);
    if (probe == "valid" && (output.greedy_program.size() != 1U || output.greedy_program[0] != 0)) {
        throw std::runtime_error("M23 valid package smoke returned an unexpected action");
    }
}

} // namespace

int main(int argc, char **argv)
{
    try {
        const auto arguments = parse_arguments(argc, argv);
        openttd_rl::v2::M23DeploymentPackage package(arguments.package);
        run_probe(package, arguments.probe);
        std::cout << "M23_PACKAGE_SMOKE=PASS package_id=" << package.package_id()
                  << " architecture=" << package.architecture_id() << " probe=" << arguments.probe << '\n';
        return 0;
    } catch (const Ort::Exception &error) {
        std::cerr << "M23_PACKAGE_SMOKE=FAIL class=onnxruntime detail=" << error.what() << '\n';
        return 3;
    } catch (const std::exception &error) {
        std::cerr << "M23_PACKAGE_SMOKE=FAIL class=validation detail=" << error.what() << '\n';
        return 2;
    }
}
