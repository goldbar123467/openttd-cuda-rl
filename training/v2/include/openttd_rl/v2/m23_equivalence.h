#ifndef OPENTTD_RL_V2_M23_EQUIVALENCE_H
#define OPENTTD_RL_V2_M23_EQUIVALENCE_H

#include <cstddef>
#include <filesystem>
#include <string_view>

namespace openttd_rl::v2 {

class M23OnnxModel;

struct M23EquivalenceSummary {
    std::size_t cases{};
    std::size_t failures{};
    double maximum_absolute{};
};

[[nodiscard]] M23EquivalenceSummary run_m23_onnx_equivalence(
    const std::filesystem::path &golden_path,
    M23OnnxModel &monolithic,
    M23OnnxModel &specialist,
    const std::filesystem::path &report_path,
    std::string_view runtime);

} // namespace openttd_rl::v2

#endif
