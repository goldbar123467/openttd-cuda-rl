// ONNX owns the neural forward pass; reuse the live native reader and sampler.
#include "v2_live_input.h"
#include "openttd_rl/training/rng.h"
#include <onnxruntime_cxx_api.h>

#include <array>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
constexpr std::array<const char *, 25> input_names{
    "structured", "global_spatial", "regional_spatial", "local_spatial", "companies", "company_mask",
    "towns", "town_mask", "industries", "industry_mask", "stations", "station_mask", "vehicles", "vehicle_mask",
    "graph_nodes", "graph_node_mask", "graph_edge_index", "graph_edges", "graph_edge_mask",
    "candidate_features", "candidate_family", "candidate_mask", "family_mask", "hidden_state", "recurrent_reset"};
constexpr std::array<const char *, 5> output_names{"family_logits", "candidate_logits", "value", "next_hidden", "probabilities"};

std::vector<torch::Tensor> tensors(const openttd_rl::v2::ScalablePolicyInput &v)
{
    return {v.structured, v.global_spatial, v.regional_spatial, v.local_spatial, v.companies.features, v.companies.mask,
        v.towns.features, v.towns.mask, v.industries.features, v.industries.mask, v.stations.features, v.stations.mask,
        v.vehicles.features, v.vehicles.mask, v.graph_nodes, v.graph_node_mask, v.graph_edge_index, v.graph_edge_features,
        v.graph_edge_mask, v.candidate_features, v.candidate_family, v.candidate_mask, v.family_mask, v.hidden_state, v.recurrent_reset};
}

ONNXTensorElementDataType element_type(const torch::Tensor &value)
{
    switch (value.scalar_type()) {
        case torch::kFloat32: return ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT;
        case torch::kInt64: return ONNX_TENSOR_ELEMENT_DATA_TYPE_INT64;
        case torch::kBool: return ONNX_TENSOR_ELEMENT_DATA_TYPE_BOOL;
        default: throw std::invalid_argument("unsupported native ONNX input type");
    }
}
}

int main(int argc, char **argv)
{
    try {
        std::map<std::string, std::string> args;
        for (int index = 1; index < argc; index += 2) {
            if (index + 1 >= argc || !args.emplace(argv[index], argv[index + 1]).second)
                throw std::invalid_argument("expected unique --device, --seed, --mode, --weights arguments");
        }
        if (args.size() != 4 + args.count("--financial-features") || !args.contains("--device") || !args.contains("--seed") || !args.contains("--mode") || !args.contains("--weights"))
            throw std::invalid_argument("required: --device cpu --seed INTEGER --mode greedy|sampled --weights MODEL.onnx");
        if (args.at("--device") != "cpu") throw std::invalid_argument("V2 ONNX deployment supports explicit CPU only; no device fallback");
        if (args.at("--mode") != "greedy" && args.at("--mode") != "sampled") throw std::invalid_argument("unsupported inference mode");
        const auto financial_features = openttd_rl::development::parse_financial_features(
            args.contains("--financial-features") ? args.at("--financial-features") : "raw");
        const std::filesystem::path path(args.at("--weights"));
        if (!path.is_absolute() || !std::filesystem::is_regular_file(path)) throw std::invalid_argument("ONNX weights require an existing absolute file");
        if (std::string(OrtGetApiBase()->GetVersionString()) != "1.28.0") throw std::runtime_error("development ONNX Runtime must be 1.28.0");
        torch::set_num_threads(1);
        torch::NoGradGuard no_grad;
        openttd_rl::training::RngStreams rng(std::stoull(args.at("--seed")));
        Ort::Env environment(ORT_LOGGING_LEVEL_WARNING, "openttd-v2-live");
        Ort::SessionOptions options;
        options.SetIntraOpNumThreads(1); options.SetInterOpNumThreads(1);
        Ort::Session session(environment, path.c_str(), options);
        Ort::AllocatorWithDefaultOptions allocator;
        const auto metadata = session.GetModelMetadata();
        for (const auto &[key, expected] : std::map<std::string, std::string>{
            {"openttd_rl.kind", "development-v2-live-recurrent-policy-1"},
            {"openttd_rl.tensor_schema", openttd_rl::development::kLiveV2TensorSchema},
            {"openttd_rl.observation_schema", "v2-m15-public-development-v2"},
            {"openttd_rl.financial_features", openttd_rl::development::financial_features_name(financial_features)}}) {
            const auto value = metadata.LookupCustomMetadataMapAllocated(key.c_str(), allocator);
            if (!value || value.get() != expected) throw std::invalid_argument("ONNX compatibility metadata differs: " + key);
        }
        if (financial_features != openttd_rl::development::FinancialFeatures::Raw) {
            const auto location = metadata.LookupCustomMetadataMapAllocated("openttd_rl.preprocessing_location", allocator);
            if (!location || std::string(location.get()) != "embedded-onnx-graph-v1")
                throw std::invalid_argument("ONNX financial preprocessing must be embedded in the graph");
        }
        if (session.GetInputCount() != input_names.size() || session.GetOutputCount() != output_names.size())
            throw std::invalid_argument("ONNX input/output inventory differs");
        for (size_t i = 0; i < input_names.size(); ++i)
            if (std::string(session.GetInputNameAllocated(i, allocator).get()) != input_names[i]) throw std::invalid_argument("ONNX input order differs");
        const std::array<std::vector<int64_t>, 5> output_shapes{{{1, 12}, {1, 4096}, {1}, {1, 256}, {1, 4096}}};
        for (size_t i = 0; i < output_names.size(); ++i) {
            if (std::string(session.GetOutputNameAllocated(i, allocator).get()) != output_names[i]) throw std::invalid_argument("ONNX output order differs");
            const auto type_info = session.GetOutputTypeInfo(i);
            const auto info = type_info.GetTensorTypeAndShapeInfo();
            if (info.GetElementType() != ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT || info.GetShape() != output_shapes[i])
                throw std::invalid_argument("ONNX output type/shape differs");
        }
        const auto memory = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
        auto hidden = torch::zeros({1, openttd_rl::v2::kHiddenSize}, torch::kFloat32);
        std::string line;
        std::cout << std::setprecision(9);
        while (std::getline(std::cin, line)) {
            if (line == "CLOSE") { std::cout << "{\"status\":\"CLOSED\"}" << std::endl; break; }
            if (line == "FINANCIAL_FEATURES_INFO") {
                std::cout << "{\"financial_features\":\"" << openttd_rl::development::financial_features_name(financial_features) << "\"}" << std::endl;
                continue;
            }
            if (line == "RESET") { hidden.zero_(); std::cout << "{\"status\":\"RESET\"}" << std::endl; continue; }
            const auto delimiter = line.find('\t');
            if (line.size() > 8192 || delimiter == std::string::npos || line.find('\t', delimiter + 1) != std::string::npos)
                throw std::invalid_argument("inference expects observation.bin TAB candidates.bin");
            // Always pass original public inputs. Signed-log preprocessing is
            // embedded in the qualified ONNX graph, never applied twice here.
            auto input = openttd_rl::development::read_live_v2_input(line.substr(0, delimiter), line.substr(delimiter + 1));
            input.hidden_state = hidden;
            if (!input.candidate_mask.any().item<bool>()) throw std::invalid_argument("all-illegal candidate mask");
            const auto bad_edges = ((input.graph_edge_index < 0) | (input.graph_edge_index >= 2048)).any(2) & input.graph_edge_mask;
            if (bad_edges.any().item<bool>()) throw std::invalid_argument("active graph edge exceeds capacity");
            auto native = tensors(input);
            std::vector<Ort::Value> values;
            values.reserve(native.size());
            for (size_t i = 0; i < native.size(); ++i) {
                native[i] = native[i].contiguous();
                const auto type = element_type(native[i]);
                const auto shape = native[i].sizes().vec();
                const auto type_info = session.GetInputTypeInfo(i);
                const auto info = type_info.GetTensorTypeAndShapeInfo();
                if (info.GetElementType() != type || info.GetShape() != shape) throw std::invalid_argument("ONNX input type/shape differs");
                values.push_back(Ort::Value::CreateTensor(memory, native[i].data_ptr(), native[i].nbytes(), shape.data(), shape.size(), type));
            }
            auto results = session.Run(Ort::RunOptions{nullptr}, input_names.data(), values.data(), values.size(), output_names.data(), output_names.size());
            std::array<torch::Tensor, 5> output;
            for (size_t i = 0; i < output.size(); ++i) {
                if (!results[i].IsTensor()) throw std::runtime_error("ONNX returned a non-tensor");
                const auto info = results[i].GetTensorTypeAndShapeInfo();
                if (info.GetElementType() != ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT || info.GetShape() != output_shapes[i])
                    throw std::runtime_error("ONNX returned incompatible output");
                output[i] = torch::from_blob(results[i].GetTensorMutableData<float>(), output_shapes[i], torch::kFloat32).clone();
                if (!torch::isfinite(output[i]).all().item<bool>()) throw std::runtime_error("nonfinite ONNX output");
            }
            const openttd_rl::v2::ScalablePolicyOutput policy_output{output[0], output[1], output[2], output[3]};
            const auto distribution = openttd_rl::development::live_v2_distribution(policy_output, input);
            if ((distribution.probabilities - output[4]).abs().max().item<float>() > 1e-5F ||
                (output[4].masked_select(~input.candidate_mask) != 0).any().item<bool>())
                throw std::runtime_error("ONNX distribution differs from native masking");
            const auto actions = args.at("--mode") == "greedy" ? distribution.log_probabilities.argmax(1) :
                openttd_rl::training::sample_masked_actions(distribution.log_probabilities, input.candidate_mask, rng.action_sampling());
            const auto action = actions.item<int64_t>();
            hidden = output[3];
            std::cout << "{\"schema_version\":\"" << openttd_rl::development::kLiveV2TensorSchema << "\",\"row\":" << action
                << ",\"value\":" << output[2].item<float>() << ",\"log_probability\":" << distribution.log_probabilities[0][action].item<float>()
                << ",\"entropy\":" << distribution.entropy.item<float>() << ",\"probabilities\":[";
            const auto probabilities = distribution.probabilities.contiguous();
            const auto *p = probabilities.data_ptr<float>();
            for (int64_t row = 0; row < openttd_rl::v2::kCandidateCapacity; ++row) {
                if (row != 0) std::cout << ',';
                std::cout << p[row];
            }
            std::cout << "]}" << std::endl;
        }
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "live V2 ONNX inference failed: " << error.what() << '\n';
        return 1;
    }
}
