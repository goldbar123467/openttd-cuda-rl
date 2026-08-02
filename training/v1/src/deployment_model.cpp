#include "openttd_rl/deployment/deployment_model.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <fstream>
#include <limits>
#include <openssl/evp.h>
#include <sstream>
#include <stdexcept>
#include <string_view>
#include <system_error>

namespace openttd_rl::deployment {

namespace {

constexpr std::size_t kMaximumFileBytes = 64U * 1024U * 1024U;
constexpr std::size_t kMaximumManifestBytes = 1024U * 1024U;
constexpr std::string_view kFormat = "openttd-rl-deployment-package-v1";
constexpr std::string_view kObservation = "7f8a46af1fe2a2c23e755c71b3bc2d04c9a0d057c573e901e5c9ed9178ca13eb";
constexpr std::string_view kAction = "215c7d3ebeea97f1629debee4a2d10301838ccfd3085e4828685591677b58536";
constexpr std::string_view kReward = "9d8f9c2fc6074d899fa3b0047c55e3fb15cc5c17cddeaceaa1fd5389e53c8c9e";
constexpr std::string_view kM09 = "c64c9876c1f6cf46dcc2642bd4628ed45f4659d1866a047d4e51def60dab9a5e";
constexpr std::string_view kUpstreamCommit = "29f808ef0022064e6d9a83c8476d1e0f4686af86";
constexpr std::string_view kEnvironmentVersion = "openttd-rl-v1-m06-environment-1";

class Sha256 {
public:
    Sha256() : context_(EVP_MD_CTX_new())
    {
        if (context_ == nullptr || EVP_DigestInit_ex(context_, EVP_sha256(), nullptr) != 1) {
            if (context_ != nullptr) EVP_MD_CTX_free(context_);
            throw std::runtime_error("cannot initialize deployment SHA-256");
        }
    }
    ~Sha256() { EVP_MD_CTX_free(context_); }
    Sha256(const Sha256 &) = delete;
    Sha256 &operator=(const Sha256 &) = delete;
    void update(const void *data, std::size_t size)
    {
        if (EVP_DigestUpdate(context_, data, size) != 1) throw std::runtime_error("deployment SHA-256 update failed");
    }
    [[nodiscard]] std::string finish()
    {
        std::array<unsigned char, 32> digest{};
        unsigned int size = 0;
        if (EVP_DigestFinal_ex(context_, digest.data(), &size) != 1 || size != digest.size()) {
            throw std::runtime_error("deployment SHA-256 finalization failed");
        }
        constexpr char hexadecimal[] = "0123456789abcdef";
        std::string output;
        output.reserve(64U);
        for (const auto byte : digest) {
            output.push_back(hexadecimal[byte >> 4U]);
            output.push_back(hexadecimal[byte & 0x0FU]);
        }
        return output;
    }

private:
    EVP_MD_CTX *context_;
};

std::string sha256_bytes(std::string_view value)
{
    Sha256 digest;
    digest.update(value.data(), value.size());
    return digest.finish();
}

std::string sha256_file(const std::filesystem::path &path)
{
    if (!std::filesystem::is_regular_file(path) || std::filesystem::is_symlink(path)) {
        throw std::invalid_argument("deployment payload is not a regular nonsymlink file: " + path.string());
    }
    const auto size = std::filesystem::file_size(path);
    if (size == 0 || size > kMaximumFileBytes) throw std::length_error("deployment payload size is outside bounds");
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("cannot read deployment payload");
    Sha256 digest;
    std::array<char, 1024U * 1024U> buffer{};
    while (input) {
        input.read(buffer.data(), static_cast<std::streamsize>(buffer.size()));
        const auto count = input.gcount();
        if (count > 0) digest.update(buffer.data(), static_cast<std::size_t>(count));
    }
    if (!input.eof()) throw std::runtime_error("deployment payload hash read failed");
    return digest.finish();
}

std::string bounded_manifest(const std::filesystem::path &path)
{
    if (!std::filesystem::is_regular_file(path) || std::filesystem::is_symlink(path)) {
        throw std::invalid_argument("deployment manifest is not a regular nonsymlink file");
    }
    const auto size = std::filesystem::file_size(path);
    if (size == 0 || size > kMaximumManifestBytes) throw std::length_error("deployment manifest size is invalid");
    std::ifstream input(path, std::ios::binary);
    std::string value(static_cast<std::size_t>(size), '\0');
    input.read(value.data(), static_cast<std::streamsize>(value.size()));
    if (!input || input.peek() != std::ifstream::traits_type::eof()) throw std::runtime_error("cannot read exact deployment manifest");
    return value;
}

std::string manifest_string(const std::string &manifest, std::string_view key)
{
    const std::string marker = "\"" + std::string(key) + "\":\"";
    const auto start = manifest.find(marker);
    if (start == std::string::npos || manifest.find(marker, start + 1U) != std::string::npos) {
        throw std::invalid_argument("deployment manifest string field is missing or duplicated: " + std::string(key));
    }
    const auto value_start = start + marker.size();
    const auto end = manifest.find('"', value_start);
    if (end == std::string::npos || manifest.find('\\', value_start) < end) {
        throw std::invalid_argument("deployment manifest string value is unsupported: " + std::string(key));
    }
    return manifest.substr(value_start, end - value_start);
}

std::uint64_t manifest_integer(const std::string &manifest, std::string_view key)
{
    const std::string marker = "\"" + std::string(key) + "\":";
    const auto start = manifest.find(marker);
    if (start == std::string::npos || manifest.find(marker, start + 1U) != std::string::npos) {
        throw std::invalid_argument("deployment manifest integer field is missing or duplicated: " + std::string(key));
    }
    std::size_t end = start + marker.size();
    std::uint64_t value = 0;
    if (end >= manifest.size() || manifest[end] < '0' || manifest[end] > '9') {
        throw std::invalid_argument("deployment manifest integer field is invalid: " + std::string(key));
    }
    while (end < manifest.size() && manifest[end] >= '0' && manifest[end] <= '9') {
        const auto digit = static_cast<std::uint64_t>(manifest[end] - '0');
        if (value > (std::numeric_limits<std::uint64_t>::max() - digit) / 10U) {
            throw std::overflow_error("deployment manifest integer overflows");
        }
        value = value * 10U + digit;
        ++end;
    }
    return value;
}

ArchitectureKind parse_architecture(const std::string &value)
{
    if (value == "structured-mlp-v1") return ArchitectureKind::StructuredMlp;
    if (value == "spatial-cnn-v1") return ArchitectureKind::SpatialCnn;
    if (value == "combined-cnn-mlp-v1") return ArchitectureKind::CombinedCnnMlp;
    throw std::invalid_argument("unknown deployment architecture");
}

std::string manifest_identity_payload(const std::string &manifest)
{
    const std::string marker = ",\"package_id\":\"";
    const auto start = manifest.find(marker);
    if (start == std::string::npos || manifest.find(marker, start + 1U) != std::string::npos) {
        throw std::invalid_argument("deployment package_id field is missing or duplicated");
    }
    const auto value_start = start + marker.size();
    const auto end = manifest.find('"', value_start);
    if (end == std::string::npos || end - value_start != 64U) throw std::invalid_argument("deployment package_id is invalid");
    std::string result = manifest;
    result.erase(start, end + 1U - start);
    return result;
}

void validate_inventory(const std::filesystem::path &root)
{
    const std::array<std::string_view, 5> expected = {"INSTALL.md", "evaluation.json", "golden.jsonl", "manifest.json", "model.onnx"};
    std::vector<std::string> observed;
    for (const auto &entry : std::filesystem::directory_iterator(root)) {
        if (entry.is_symlink() || !entry.is_regular_file()) throw std::invalid_argument("deployment package contains a symlink or nonfile");
        observed.push_back(entry.path().filename().string());
    }
    std::sort(observed.begin(), observed.end());
    if (observed.size() != expected.size() || !std::equal(observed.begin(), observed.end(), expected.begin())) {
        throw std::invalid_argument("deployment package file inventory drifted");
    }
}

void require_shape(const Ort::Session &session, std::size_t index, const std::vector<std::int64_t> &expected, bool input)
{
    const auto type = input ? session.GetInputTypeInfo(index) : session.GetOutputTypeInfo(index);
    const auto info = type.GetTensorTypeAndShapeInfo();
    if (info.GetElementType() != ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT || info.GetShape() != expected) {
        throw std::invalid_argument("deployment ONNX tensor dtype/shape drifted");
    }
}

void require_inputs(
    const std::vector<float> &structured,
    const std::vector<float> &spatial,
    const std::vector<std::uint8_t> &masks,
    std::size_t batch)
{
    if (batch == 0 || batch > 64U || structured.size() != batch * kStructuredFeatures ||
        spatial.size() != batch * kSpatialFeatures || masks.size() != batch * kActionCount) {
        throw std::invalid_argument("deployment input batch shape is invalid");
    }
    if (std::any_of(structured.begin(), structured.end(), [](float value) { return !std::isfinite(value); }) ||
        std::any_of(spatial.begin(), spatial.end(), [](float value) { return !std::isfinite(value) || value < 0.0F || value > 1.0F; })) {
        throw std::invalid_argument("deployment observations are nonfinite or outside encoding bounds");
    }
    for (std::size_t row = 0; row < batch; ++row) {
        bool any = false;
        for (std::size_t action = 0; action < kActionCount; ++action) {
            const auto value = masks[row * kActionCount + action];
            if (value > 1U) throw std::invalid_argument("deployment legal mask is not boolean");
            any = any || value != 0U;
        }
        if (!any) throw std::invalid_argument("deployment legal mask is all illegal");
    }
}

} // namespace

const char *architecture_name(ArchitectureKind kind) noexcept
{
    switch (kind) {
        case ArchitectureKind::StructuredMlp: return "structured-mlp-v1";
        case ArchitectureKind::SpatialCnn: return "spatial-cnn-v1";
        case ArchitectureKind::CombinedCnnMlp: return "combined-cnn-mlp-v1";
    }
    return "invalid-architecture";
}

DeploymentPolicy::DeploymentPolicy(const std::filesystem::path &package_path, std::uint64_t sampling_seed)
    : package_path_(package_path),
      environment_(ORT_LOGGING_LEVEL_WARNING, "openttd-rl-v1-deployment"),
      sampling_generator_(sampling_seed)
{
    if (!package_path_.is_absolute() || !std::filesystem::is_directory(package_path_) || std::filesystem::is_symlink(package_path_)) {
        throw std::invalid_argument("deployment package must be an absolute nonsymlink directory");
    }
    validate_inventory(package_path_);
    const auto manifest = bounded_manifest(package_path_ / "manifest.json");
    package_id_ = manifest_string(manifest, "package_id");
    if (package_path_.filename() != package_id_ || sha256_bytes(manifest_identity_payload(manifest)) != package_id_) {
        throw std::invalid_argument("deployment package content address mismatch");
    }
    if (manifest_string(manifest, "format") != kFormat || manifest_integer(manifest, "compatibility_version") != 1U ||
        manifest_integer(manifest, "architecture_version") != 1U || manifest_integer(manifest, "onnx_opset") != 18U ||
        manifest_string(manifest, "observation_sha256") != kObservation ||
        manifest_string(manifest, "action_sha256") != kAction || manifest_string(manifest, "mask_sha256") != kAction ||
        manifest_string(manifest, "reward_sha256") != kReward || manifest_string(manifest, "m09_sha256") != kM09 ||
        manifest_string(manifest, "m10_sha256") != kM10CompatibilitySha256 ||
        manifest_string(manifest, "onnxruntime_version") != "1.28.0" ||
        manifest_string(manifest, "openttd_upstream_commit") != kUpstreamCommit ||
        manifest_string(manifest, "environment_version") != kEnvironmentVersion ||
        manifest_string(manifest, "normalization") != "none-frozen-m04-preprocessing" ||
        manifest_string(manifest, "recurrent_state") != "none-v1-feed-forward") {
        throw std::invalid_argument("deployment package compatibility mismatch");
    }
    architecture_ = parse_architecture(manifest_string(manifest, "architecture_id"));
    model_sha256_ = manifest_string(manifest, "model.onnx");
    for (const auto name : {"model.onnx", "golden.jsonl", "evaluation.json", "INSTALL.md"}) {
        if (sha256_file(package_path_ / name) != manifest_string(manifest, name)) {
            throw std::invalid_argument("deployment payload digest mismatch: " + std::string(name));
        }
    }
    if (std::string(OrtGetApiBase()->GetVersionString()) != "1.28.0") {
        throw std::runtime_error("deployment ONNX Runtime version mismatch");
    }
    options_.SetIntraOpNumThreads(1);
    options_.SetInterOpNumThreads(1);
    options_.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);
    session_ = std::make_unique<Ort::Session>(environment_, (package_path_ / "model.onnx").c_str(), options_);
    const std::size_t expected_inputs = architecture_ == ArchitectureKind::CombinedCnnMlp ? 2U : 1U;
    if (session_->GetInputCount() != expected_inputs || session_->GetOutputCount() != 2U) {
        throw std::invalid_argument("deployment ONNX input/output count drifted");
    }
    Ort::AllocatorWithDefaultOptions allocator;
    std::vector<std::string> names;
    for (std::size_t index = 0; index < expected_inputs; ++index) names.emplace_back(session_->GetInputNameAllocated(index, allocator).get());
    const std::vector<std::string> expected_names = architecture_ == ArchitectureKind::StructuredMlp
        ? std::vector<std::string>{"structured"}
        : architecture_ == ArchitectureKind::SpatialCnn ? std::vector<std::string>{"spatial"}
                                                        : std::vector<std::string>{"structured", "spatial"};
    if (names != expected_names || std::string(session_->GetOutputNameAllocated(0, allocator).get()) != "policy_logits" ||
        std::string(session_->GetOutputNameAllocated(1, allocator).get()) != "value") {
        throw std::invalid_argument("deployment ONNX tensor names drifted");
    }
    std::size_t input_index = 0;
    if (architecture_ != ArchitectureKind::SpatialCnn) require_shape(*session_, input_index++, {-1, 256}, true);
    if (architecture_ != ArchitectureKind::StructuredMlp) require_shape(*session_, input_index, {-1, 32, 32, 32}, true);
    require_shape(*session_, 0, {-1, 41}, false);
    require_shape(*session_, 1, {-1}, false);
}

DeploymentPolicy::~DeploymentPolicy() = default;

InspectionBatch DeploymentPolicy::inspect(
    const std::vector<float> &structured,
    const std::vector<float> &spatial,
    const std::vector<std::uint8_t> &legal_masks,
    std::size_t batch,
    bool deterministic)
{
    require_inputs(structured, spatial, legal_masks, batch);
    const std::array<std::int64_t, 2> structured_shape{static_cast<std::int64_t>(batch), 256};
    const std::array<std::int64_t, 4> spatial_shape{static_cast<std::int64_t>(batch), 32, 32, 32};
    auto memory = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
    std::vector<Ort::Value> inputs;
    std::vector<const char *> input_names;
    if (architecture_ != ArchitectureKind::SpatialCnn) {
        inputs.push_back(Ort::Value::CreateTensor<float>(memory, const_cast<float *>(structured.data()), structured.size(), structured_shape.data(), structured_shape.size()));
        input_names.push_back("structured");
    }
    if (architecture_ != ArchitectureKind::StructuredMlp) {
        inputs.push_back(Ort::Value::CreateTensor<float>(memory, const_cast<float *>(spatial.data()), spatial.size(), spatial_shape.data(), spatial_shape.size()));
        input_names.push_back("spatial");
    }
    const std::array<const char *, 2> output_names{"policy_logits", "value"};
    auto outputs = session_->Run(Ort::RunOptions{nullptr}, input_names.data(), inputs.data(), inputs.size(), output_names.data(), output_names.size());
    if (outputs.size() != 2U || !outputs[0].IsTensor() || !outputs[1].IsTensor() ||
        outputs[0].GetTensorTypeAndShapeInfo().GetShape() != std::vector<std::int64_t>({static_cast<std::int64_t>(batch), 41}) ||
        outputs[1].GetTensorTypeAndShapeInfo().GetShape() != std::vector<std::int64_t>({static_cast<std::int64_t>(batch)})) {
        throw std::runtime_error("deployment ONNX runtime output shape drifted");
    }
    const float *raw_logits = outputs[0].GetTensorData<float>();
    const float *raw_values = outputs[1].GetTensorData<float>();
    InspectionBatch result;
    result.actions.resize(batch);
    result.log_probabilities.resize(batch);
    result.values.resize(batch);
    result.logits.resize(batch * kActionCount);
    result.probabilities.resize(batch * kActionCount);
    for (std::size_t row = 0; row < batch; ++row) {
        double maximum = -std::numeric_limits<double>::infinity();
        for (std::size_t action = 0; action < kActionCount; ++action) {
            const float value = raw_logits[row * kActionCount + action];
            if (!std::isfinite(value)) throw std::runtime_error("deployment ONNX emitted nonfinite logits");
            result.logits[row * kActionCount + action] = static_cast<double>(value);
            if (legal_masks[row * kActionCount + action] != 0U) maximum = std::max(maximum, static_cast<double>(value));
        }
        double total = 0.0;
        for (std::size_t action = 0; action < kActionCount; ++action) {
            double probability = 0.0;
            if (legal_masks[row * kActionCount + action] != 0U) probability = std::exp(result.logits[row * kActionCount + action] - maximum);
            result.probabilities[row * kActionCount + action] = probability;
            total += probability;
        }
        std::size_t greedy = 0;
        double greedy_probability = -1.0;
        for (std::size_t action = 0; action < kActionCount; ++action) {
            auto &probability = result.probabilities[row * kActionCount + action];
            probability /= total;
            if (probability > greedy_probability) {
                greedy_probability = probability;
                greedy = action;
            }
        }
        std::size_t selected = greedy;
        if (!deterministic) {
            const double draw = std::generate_canonical<double, 53>(sampling_generator_);
            double cumulative = 0.0;
            std::size_t last_legal = 0;
            bool found = false;
            for (std::size_t action = 0; action < kActionCount; ++action) {
                if (legal_masks[row * kActionCount + action] == 0U) continue;
                last_legal = action;
                cumulative += result.probabilities[row * kActionCount + action];
                if (!found && draw < cumulative) {
                    selected = action;
                    found = true;
                }
            }
            if (!found) selected = last_legal;
        }
        result.actions[row] = static_cast<std::int64_t>(selected);
        result.log_probabilities[row] = std::log(result.probabilities[row * kActionCount + selected]);
        result.values[row] = static_cast<double>(raw_values[row]);
        if (!std::isfinite(result.values[row]) || !std::isfinite(result.log_probabilities[row])) {
            throw std::runtime_error("deployment ONNX emitted nonfinite interpreted output");
        }
    }
    return result;
}

InspectionBatch InGamePolicyAdapter::inspect(
    const std::vector<float> &structured,
    const std::vector<float> &spatial,
    const std::vector<std::uint8_t> &legal_masks,
    std::size_t batch,
    bool deterministic)
{
    const std::vector<float> structured_copy(structured);
    const std::vector<float> spatial_copy(spatial);
    const std::vector<std::uint8_t> mask_copy(legal_masks);
    auto result = policy_.inspect(structured_copy, spatial_copy, mask_copy, batch, deterministic);
    for (std::size_t row = 0; row < batch; ++row) {
        const auto action = static_cast<std::size_t>(result.actions[row]);
        if (action >= kActionCount || mask_copy[row * kActionCount + action] == 0U) {
            throw std::runtime_error("in-game adapter received an illegal deployment action");
        }
    }
    return result;
}

} // namespace openttd_rl::deployment
