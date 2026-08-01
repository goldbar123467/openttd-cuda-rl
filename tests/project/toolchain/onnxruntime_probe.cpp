#include <onnxruntime_cxx_api.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

int main(int argc, char **argv)
{
    try {
        if (argc != 1 && argc != 2) {
            throw std::runtime_error("usage: v1_onnxruntime_probe [model.onnx]");
        }
        const std::string version = OrtGetApiBase()->GetVersionString();
        if (version != "1.28.0") {
            throw std::runtime_error("unexpected ONNX Runtime version: " + version);
        }
        Ort::Env environment(ORT_LOGGING_LEVEL_WARNING, "openttd-rl-v1-probe");
        Ort::SessionOptions options;
        options.SetIntraOpNumThreads(1);
        options.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);
        const auto providers = Ort::GetAvailableProviders();
        bool cpu_provider = false;
        for (const std::string &provider : providers) {
            if (provider == "CPUExecutionProvider") cpu_provider = true;
        }
        if (!cpu_provider) throw std::runtime_error("CPUExecutionProvider is unavailable");
        if (argc == 2) {
            Ort::Session session(environment, argv[1], options);
            if (session.GetInputCount() != 1 || session.GetOutputCount() != 1) {
                throw std::runtime_error("probe graph must have one input and one output");
            }
            Ort::AllocatorWithDefaultOptions allocator;
            const auto input_name = session.GetInputNameAllocated(0, allocator);
            const auto output_name = session.GetOutputNameAllocated(0, allocator);
            if (std::string(input_name.get()) != "input" ||
                std::string(output_name.get()) != "output") {
                throw std::runtime_error("probe tensor name mismatch");
            }
            const Ort::TypeInfo input_type_info = session.GetInputTypeInfo(0);
            const Ort::TypeInfo output_type_info = session.GetOutputTypeInfo(0);
            const auto input_info = input_type_info.GetTensorTypeAndShapeInfo();
            const auto output_info = output_type_info.GetTensorTypeAndShapeInfo();
            const auto input_shape = input_info.GetShape();
            const auto declared_output_shape = output_info.GetShape();
            if (input_info.GetElementType() != ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT ||
                output_info.GetElementType() != ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT ||
                input_shape != std::vector<int64_t>({2, 4}) ||
                declared_output_shape != std::vector<int64_t>({2, 3})) {
                std::ostringstream detail;
                detail << "probe tensor type or shape mismatch: input_type="
                       << input_info.GetElementType() << " output_type="
                       << output_info.GetElementType() << " input_shape=";
                for (const auto dimension : input_shape) detail << dimension << ',';
                detail << " output_shape=";
                for (const auto dimension : declared_output_shape) detail << dimension << ',';
                throw std::runtime_error(detail.str());
            }

            std::array<float, 8> input{1.0F, -2.0F, 0.5F, 3.0F, 2.0F, -1.0F, 0.0F, 0.0F};
            constexpr std::array<float, 6> expected{2.15F, 2.65F, 3.15F, 0.0F, 0.0F, 0.15F};
            constexpr std::array<int64_t, 2> input_dimensions{2, 4};
            auto memory = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
            auto input_tensor = Ort::Value::CreateTensor<float>(
                memory,
                input.data(),
                input.size(),
                input_dimensions.data(),
                input_dimensions.size());
            const std::array<const char *, 1> input_names{input_name.get()};
            const std::array<const char *, 1> output_names{output_name.get()};
            auto outputs = session.Run(
                Ort::RunOptions{nullptr},
                input_names.data(),
                &input_tensor,
                input_names.size(),
                output_names.data(),
                output_names.size());
            if (outputs.size() != 1 || !outputs[0].IsTensor()) {
                throw std::runtime_error("probe output is not one tensor");
            }
            const auto output_shape = outputs[0].GetTensorTypeAndShapeInfo().GetShape();
            if (output_shape != std::vector<int64_t>({2, 3})) {
                throw std::runtime_error("runtime output shape mismatch");
            }
            const float *actual = outputs[0].GetTensorData<float>();
            float maximum_error = 0.0F;
            for (std::size_t index = 0; index < expected.size(); ++index) {
                maximum_error = std::max(maximum_error, std::abs(actual[index] - expected[index]));
            }
            if (!std::isfinite(maximum_error) || maximum_error > 1.0e-6F) {
                throw std::runtime_error("runtime output mismatch");
            }
            std::cout << "ONNXRUNTIME_GRAPH_PROBE=PASS"
                      << " max_error=" << maximum_error
                      << " input_shape=2x4 output_shape=2x3"
                      << '\n';
        }
        std::cout << "ONNXRUNTIME_PROBE=PASS"
                  << " version=" << version
                  << " cpu_provider=true"
                  << " provider_count=" << providers.size()
                  << '\n';
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "ONNXRUNTIME_PROBE=FAIL " << error.what() << '\n';
        return 1;
    }
}
