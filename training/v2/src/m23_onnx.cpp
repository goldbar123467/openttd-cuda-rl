#include "openttd_rl/v2/m23_onnx.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <stdexcept>
#include <string_view>

namespace openttd_rl::v2 {

namespace {

constexpr std::array<std::string_view, 4> kInputNames = {
    "public_features", "program_mask", "hidden_state", "recurrent_reset",
};
constexpr std::array<std::string_view, 3> kOutputNames = {
    "program_logits", "program_value", "next_hidden",
};

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

} // namespace openttd_rl::v2
