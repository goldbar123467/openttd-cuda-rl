#ifndef OPENTTD_RL_DEPLOYMENT_DEPLOYMENT_MODEL_H
#define OPENTTD_RL_DEPLOYMENT_DEPLOYMENT_MODEL_H

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <random>
#include <string>
#include <vector>

#include <onnxruntime_cxx_api.h>

namespace openttd_rl::deployment {

inline constexpr std::size_t kStructuredFeatures = 256U;
inline constexpr std::size_t kSpatialFeatures = 32U * 32U * 32U;
inline constexpr std::size_t kActionCount = 41U;
inline constexpr const char *kM10CompatibilitySha256 =
    "e77edf9be1343970a55becbb05da96a6b9a17edbd8df2c7999701dd8fa1f33b6";

enum class ArchitectureKind : std::uint8_t {
    StructuredMlp = 0,
    SpatialCnn = 1,
    CombinedCnnMlp = 2,
};

struct InspectionBatch {
    std::vector<std::int64_t> actions;
    std::vector<double> log_probabilities;
    std::vector<double> values;
    std::vector<double> logits;
    std::vector<double> probabilities;
};

class DeploymentPolicy {
public:
    DeploymentPolicy(const std::filesystem::path &package_path, std::uint64_t sampling_seed);
    ~DeploymentPolicy();
    DeploymentPolicy(const DeploymentPolicy &) = delete;
    DeploymentPolicy &operator=(const DeploymentPolicy &) = delete;

    [[nodiscard]] InspectionBatch inspect(
        const std::vector<float> &structured,
        const std::vector<float> &spatial,
        const std::vector<std::uint8_t> &legal_masks,
        std::size_t batch,
        bool deterministic);
    [[nodiscard]] const std::string &package_id() const noexcept { return package_id_; }
    [[nodiscard]] const std::string &model_sha256() const noexcept { return model_sha256_; }
    [[nodiscard]] ArchitectureKind architecture() const noexcept { return architecture_; }

private:
    std::filesystem::path package_path_;
    std::string package_id_;
    std::string model_sha256_;
    ArchitectureKind architecture_{};
    Ort::Env environment_;
    Ort::SessionOptions options_;
    std::unique_ptr<Ort::Session> session_;
    std::mt19937_64 sampling_generator_;
};

class InGamePolicyAdapter {
public:
    explicit InGamePolicyAdapter(DeploymentPolicy &policy) : policy_(policy) {}
    [[nodiscard]] InspectionBatch inspect(
        const std::vector<float> &structured,
        const std::vector<float> &spatial,
        const std::vector<std::uint8_t> &legal_masks,
        std::size_t batch,
        bool deterministic);

private:
    DeploymentPolicy &policy_;
};

[[nodiscard]] const char *architecture_name(ArchitectureKind kind) noexcept;

} // namespace openttd_rl::deployment

#endif
