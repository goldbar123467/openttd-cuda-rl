#include "openttd_rl/v2/m23_onnx.h"
#include "openttd_rl/v2/m23_golden.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <fstream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>

namespace openttd_rl::v2 {

namespace {

constexpr std::array<std::string_view, 4> kInputNames = {
    "public_features", "program_mask", "hidden_state", "recurrent_reset",
};
constexpr std::array<std::string_view, 3> kOutputNames = {
    "program_logits", "program_value", "next_hidden",
};
constexpr std::string_view kPackageFormat = "openttd-rl-v2-deployment-package-1";
constexpr std::string_view kLearningContract = "f3ae8f89dfb6edf19b910c55f55845279b77ddd7be5adbd1db244984f968b07b";
constexpr std::string_view kSourceTree = "f8985045f9ba14bad1e46a81cb58fdbb8037f277";
constexpr std::string_view kMonolithicCheckpoint = "03894fd1238b69b6724d82eb441380312be4e8226efa602fa5e43972f7fa9f5f";
constexpr std::string_view kSpecialistCheckpoint = "458b2b1413ca483cb9b061518ce9d80e5e9afc85852a66015d81da07bcc7fd2f";
constexpr std::uintmax_t kMaximumPackageFileBytes = 67108864U;

void require(bool condition, const char *message)
{
    if (!condition) throw std::invalid_argument(message);
}

void require_signature(
    const Ort::Session &session,
    std::size_t index,
    std::string_view expected_name,
    ONNXTensorElementDataType expected_type,
    const std::vector<std::int64_t> &expected_shape,
    bool input)
{
    Ort::AllocatorWithDefaultOptions allocator;
    const auto name = input ? session.GetInputNameAllocated(index, allocator) :
        session.GetOutputNameAllocated(index, allocator);
    require(name != nullptr && std::string_view(name.get()) == expected_name,
        input ? "M23 ONNX input name drifted" : "M23 ONNX output name drifted");
    const auto type = input ? session.GetInputTypeInfo(index) : session.GetOutputTypeInfo(index);
    const auto tensor = type.GetTensorTypeAndShapeInfo();
    require(tensor.GetElementType() == expected_type,
        input ? "M23 ONNX input dtype drifted" : "M23 ONNX output dtype drifted");
    require(tensor.GetShape() == expected_shape,
        input ? "M23 ONNX input shape drifted" : "M23 ONNX output shape drifted");
}

void require_finite(const std::vector<float> &values, const char *message)
{
    require(std::all_of(values.begin(), values.end(), [](float value) { return std::isfinite(value); }), message);
}

[[nodiscard]] std::string bounded_text(const std::filesystem::path &path, std::uintmax_t maximum)
{
    require(std::filesystem::is_regular_file(path) && !std::filesystem::is_symlink(path),
        "M23 package text is not a regular file");
    const auto size = std::filesystem::file_size(path);
    require(size > 0U && size <= maximum, "M23 package text size is invalid");
    std::ifstream stream(path, std::ios::binary);
    require(stream.good(), "M23 package text cannot be opened");
    std::string value(static_cast<std::size_t>(size), '\0');
    stream.read(value.data(), static_cast<std::streamsize>(value.size()));
    require(stream.good() || stream.eof(), "M23 package text cannot be read");
    require(stream.gcount() == static_cast<std::streamsize>(value.size()), "M23 package text was truncated");
    return value;
}

[[nodiscard]] std::string manifest_string(const std::string &manifest, std::string_view key)
{
    const std::string marker = "\"" + std::string(key) + "\":\"";
    const auto start = manifest.find(marker);
    require(start != std::string::npos && manifest.find(marker, start + marker.size()) == std::string::npos,
        "M23 deployment manifest string field is missing or duplicated");
    const auto value_start = start + marker.size();
    const auto end = manifest.find('"', value_start);
    require(end != std::string::npos, "M23 deployment manifest string field is unterminated");
    return manifest.substr(value_start, end - value_start);
}

[[nodiscard]] std::uint64_t manifest_integer(const std::string &manifest, std::string_view key)
{
    const std::string marker = "\"" + std::string(key) + "\":";
    const auto start = manifest.find(marker);
    require(start != std::string::npos && manifest.find(marker, start + marker.size()) == std::string::npos,
        "M23 deployment manifest integer field is missing or duplicated");
    auto end = start + marker.size();
    require(end < manifest.size() && manifest[end] >= '0' && manifest[end] <= '9',
        "M23 deployment manifest integer field is invalid");
    std::uint64_t value = 0;
    while (end < manifest.size() && manifest[end] >= '0' && manifest[end] <= '9') {
        const auto digit = static_cast<std::uint64_t>(manifest[end] - '0');
        require(value <= (std::numeric_limits<std::uint64_t>::max() - digit) / 10U,
            "M23 deployment manifest integer field overflows");
        value = value * 10U + digit;
        ++end;
    }
    return value;
}

[[nodiscard]] std::string manifest_identity_payload(const std::string &manifest)
{
    const std::string marker = ",\"package_id\":\"";
    const auto start = manifest.find(marker);
    require(start != std::string::npos && manifest.find(marker, start + marker.size()) == std::string::npos,
        "M23 deployment package_id is missing or duplicated");
    const auto value_start = start + marker.size();
    const auto end = manifest.find('"', value_start);
    require(end != std::string::npos && end - value_start == 64U, "M23 deployment package_id is invalid");
    std::string result = manifest;
    result.erase(start, end + 1U - start);
    return result;
}

void validate_package_inventory(const std::filesystem::path &root)
{
    constexpr std::array<std::string_view, 6> expected = {
        "INSTALL.md", "MODEL_CARD.md", "evaluation.json", "golden.jsonl", "manifest.json", "model.onnx",
    };
    std::vector<std::string> observed;
    for (const auto &entry : std::filesystem::directory_iterator(root)) {
        require(!entry.is_symlink() && entry.is_regular_file(), "M23 deployment package contains a symlink or nonfile");
        const auto size = entry.file_size();
        require(size > 0U && size <= kMaximumPackageFileBytes, "M23 deployment package file size is invalid");
        observed.push_back(entry.path().filename().string());
    }
    std::sort(observed.begin(), observed.end());
    require(observed.size() == expected.size() && std::equal(observed.begin(), observed.end(), expected.begin()),
        "M23 deployment package file inventory drifted");
}

} // namespace

M23OnnxModel::M23OnnxModel(std::filesystem::path model_path, std::string architecture_id) :
    model_path_(std::move(model_path)),
    architecture_id_(std::move(architecture_id)),
    environment_(ORT_LOGGING_LEVEL_ERROR, "openttd-rl-v2-m23")
{
    require(model_path_.is_absolute() && std::filesystem::is_regular_file(model_path_) &&
            !std::filesystem::is_symlink(model_path_),
        "M23 ONNX model must be an absolute regular file");
    require(architecture_id_ == "monolithic-generalist-v1" || architecture_id_ == "specialist-router-v1",
        "M23 ONNX architecture is unsupported");
    require(std::string_view(OrtGetApiBase()->GetVersionString()) == "1.28.0",
        "M23 ONNX Runtime version mismatch");
    options_.SetExecutionMode(ExecutionMode::ORT_SEQUENTIAL);
    options_.SetIntraOpNumThreads(1);
    options_.SetInterOpNumThreads(1);
    options_.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);
    options_.DisableMemPattern();
    session_ = std::make_unique<Ort::Session>(environment_, model_path_.c_str(), options_);
    require(session_->GetInputCount() == kInputNames.size() && session_->GetOutputCount() == kOutputNames.size(),
        "M23 ONNX input/output count drifted");
    require_signature(*session_, 0, kInputNames[0], ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT, {-1, 32}, true);
    require_signature(*session_, 1, kInputNames[1], ONNX_TENSOR_ELEMENT_DATA_TYPE_BOOL, {-1, 17}, true);
    require_signature(*session_, 2, kInputNames[2], ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT, {-1, 256}, true);
    require_signature(*session_, 3, kInputNames[3], ONNX_TENSOR_ELEMENT_DATA_TYPE_BOOL, {-1}, true);
    require_signature(*session_, 0, kOutputNames[0], ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT, {-1, 17}, false);
    require_signature(*session_, 1, kOutputNames[1], ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT, {-1}, false);
    require_signature(*session_, 2, kOutputNames[2], ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT, {-1, 256}, false);
}

M23OnnxOutput M23OnnxModel::run(
    std::uint32_t batch,
    const std::vector<float> &public_features,
    const std::vector<std::uint8_t> &program_mask,
    const std::vector<float> &hidden_state,
    const std::vector<std::uint8_t> &recurrent_reset)
{
    require(batch >= 1U && batch <= 32U, "M23 ONNX batch must be 1 through 32");
    require(public_features.size() == static_cast<std::size_t>(batch) * 32U &&
            program_mask.size() == static_cast<std::size_t>(batch) * 17U &&
            hidden_state.size() == static_cast<std::size_t>(batch) * 256U &&
            recurrent_reset.size() == batch,
        "M23 ONNX input tensor sizes drifted");
    require_finite(public_features, "M23 ONNX public features are nonfinite");
    require_finite(hidden_state, "M23 ONNX hidden state is nonfinite");
    require(std::all_of(program_mask.begin(), program_mask.end(), [](std::uint8_t value) { return value <= 1; }) &&
            std::all_of(recurrent_reset.begin(), recurrent_reset.end(), [](std::uint8_t value) { return value <= 1; }),
        "M23 ONNX boolean input contains a non-boolean byte");
    for (std::uint32_t row = 0; row < batch; ++row) {
        const auto begin = program_mask.begin() + static_cast<std::ptrdiff_t>(row * 17U);
        require(std::any_of(begin, begin + 17, [](std::uint8_t value) { return value == 1; }),
            "M23 ONNX program mask contains an all-illegal row");
    }
    std::vector<std::uint8_t> mask_bytes = program_mask;
    std::vector<std::uint8_t> reset_bytes = recurrent_reset;
    const std::array<std::int64_t, 2> feature_shape = {static_cast<std::int64_t>(batch), 32};
    const std::array<std::int64_t, 2> mask_shape = {static_cast<std::int64_t>(batch), 17};
    const std::array<std::int64_t, 2> hidden_shape = {static_cast<std::int64_t>(batch), 256};
    const std::array<std::int64_t, 1> reset_shape = {static_cast<std::int64_t>(batch)};
    auto memory = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
    std::vector<Ort::Value> inputs;
    inputs.reserve(4);
    inputs.push_back(Ort::Value::CreateTensor<float>(memory, const_cast<float *>(public_features.data()),
        public_features.size(), feature_shape.data(), feature_shape.size()));
    inputs.push_back(Ort::Value::CreateTensor(memory, mask_bytes.data(), mask_bytes.size(),
        mask_shape.data(), mask_shape.size(), ONNX_TENSOR_ELEMENT_DATA_TYPE_BOOL));
    inputs.push_back(Ort::Value::CreateTensor<float>(memory, const_cast<float *>(hidden_state.data()),
        hidden_state.size(), hidden_shape.data(), hidden_shape.size()));
    inputs.push_back(Ort::Value::CreateTensor(memory, reset_bytes.data(), reset_bytes.size(),
        reset_shape.data(), reset_shape.size(), ONNX_TENSOR_ELEMENT_DATA_TYPE_BOOL));
    const std::array<const char *, 4> input_names = {
        kInputNames[0].data(), kInputNames[1].data(), kInputNames[2].data(), kInputNames[3].data(),
    };
    const std::array<const char *, 3> output_names = {
        kOutputNames[0].data(), kOutputNames[1].data(), kOutputNames[2].data(),
    };
    auto outputs = session_->Run(Ort::RunOptions{nullptr}, input_names.data(), inputs.data(), inputs.size(),
        output_names.data(), output_names.size());
    require(outputs.size() == 3 && std::all_of(outputs.begin(), outputs.end(), [](const Ort::Value &value) {
        return value.IsTensor();
    }), "M23 ONNX runtime output inventory drifted");
    const auto copy_float = [&](std::size_t index, std::size_t size) {
        const auto info = outputs[index].GetTensorTypeAndShapeInfo();
        require(info.GetElementType() == ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT &&
                info.GetElementCount() == size,
            "M23 ONNX runtime output tensor shape or type drifted");
        const auto *values = outputs[index].GetTensorData<float>();
        return std::vector<float>(values, values + size);
    };
    M23OnnxOutput result{
        copy_float(0, static_cast<std::size_t>(batch) * 17U),
        copy_float(1, batch),
        copy_float(2, static_cast<std::size_t>(batch) * 256U),
        std::vector<std::int64_t>(batch),
    };
    require_finite(result.program_logits, "M23 ONNX program logits are nonfinite");
    require_finite(result.program_value, "M23 ONNX program value is nonfinite");
    require_finite(result.next_hidden, "M23 ONNX next hidden is nonfinite");
    for (std::uint32_t row = 0; row < batch; ++row) {
        const auto begin = result.program_logits.begin() + static_cast<std::ptrdiff_t>(row * 17U);
        const auto action = static_cast<std::int64_t>(std::max_element(begin, begin + 17) - begin);
        require(program_mask[static_cast<std::size_t>(row) * 17U + static_cast<std::size_t>(action)] == 1,
            "M23 ONNX selected an illegal program");
        result.greedy_program[row] = action;
    }
    return result;
}

M23DeploymentPackage::M23DeploymentPackage(std::filesystem::path package_path) :
    package_path_(std::move(package_path))
{
    require(package_path_.is_absolute() && std::filesystem::is_directory(package_path_) &&
            !std::filesystem::is_symlink(package_path_),
        "M23 deployment package must be an absolute nonsymlink directory");
    validate_package_inventory(package_path_);
    const auto manifest = bounded_text(package_path_ / "manifest.json", 65536U);
    require(manifest.find_first_of(" \n\r\t") == std::string::npos,
        "M23 deployment manifest is not compact canonical JSON");
    package_id_ = manifest_string(manifest, "package_id");
    require(package_path_.filename() == package_id_ &&
            m23_sha256_bytes(manifest_identity_payload(manifest)) == package_id_,
        "M23 deployment package content address mismatch");
    architecture_id_ = manifest_string(manifest, "architecture_id");
    checkpoint_id_ = manifest_string(manifest, "checkpoint_id");
    const bool monolithic = architecture_id_ == "monolithic-generalist-v1" &&
        checkpoint_id_ == kMonolithicCheckpoint &&
        manifest_string(manifest, "role") == "accepted-default-in-game-policy";
    const bool specialist = architecture_id_ == "specialist-router-v1" &&
        checkpoint_id_ == kSpecialistCheckpoint &&
        manifest_string(manifest, "role") == "published-matched-comparison";
    require(monolithic || specialist, "M23 deployment architecture/checkpoint selection mismatch");
    require(manifest_string(manifest, "format") == kPackageFormat &&
            manifest_integer(manifest, "compatibility_version") == 1U &&
            manifest_integer(manifest, "architecture_version") == 1U &&
            manifest_integer(manifest, "onnx_opset") == 18U &&
            manifest_integer(manifest, "recurrent_width") == 256U &&
            manifest_string(manifest, "learning_contract_sha256") == kLearningContract &&
            manifest_string(manifest, "source_tree_id") == kSourceTree &&
            manifest_string(manifest, "onnxruntime_version") == "1.28.0" &&
            manifest_string(manifest, "normalization") ==
                "already-normalized-public-float32-features-no-runtime-fitting" &&
            manifest_string(manifest, "recurrent_reset_semantics") ==
                "true-row-zeros-hidden-before-GRUCell-false-row-carries-hidden" &&
            manifest_string(manifest, "training_dependencies") == "forbidden",
        "M23 deployment package compatibility mismatch");
    for (const auto name : {"model.onnx", "golden.jsonl", "evaluation.json", "INSTALL.md", "MODEL_CARD.md"}) {
        require(m23_sha256_file(package_path_ / name) == manifest_string(manifest, name),
            "M23 deployment package payload digest mismatch");
    }
    model_sha256_ = m23_sha256_file(package_path_ / "model.onnx");
    require(model_sha256_ == manifest_string(manifest, "model_sha256"),
        "M23 deployment package model provenance mismatch");
    model_ = std::make_unique<M23OnnxModel>(package_path_ / "model.onnx", architecture_id_);
}

} // namespace openttd_rl::v2
