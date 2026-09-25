#include "v2_live_input.h"
#include "openttd_rl/training/rng.h"
#include "openttd_rl/v2/checkpoint.h"

#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <torch/cuda.h>

int main(int argc, char **argv)
{
    try {
        std::map<std::string, std::string> args;
        for (int index = 1; index < argc; index += 2) {
            if (index + 1 >= argc || !args.emplace(argv[index], argv[index + 1]).second)
                throw std::invalid_argument("expected unique --device, --seed, --mode arguments");
        }
        if (!args.contains("--device") || !args.contains("--seed") || !args.contains("--mode") ||
            args.size() != 3 + args.count("--weights") + args.count("--financial-features"))
            throw std::invalid_argument("required: --device cpu|cuda:0 --seed INTEGER --mode greedy|sampled [--weights FILE] [--financial-features raw|signed-log-v1]");
        if (args.at("--device") != "cpu" && args.at("--device") != "cuda:0") throw std::invalid_argument("unsupported device");
        if (args.at("--mode") != "greedy" && args.at("--mode") != "sampled") throw std::invalid_argument("unsupported mode");
        const auto financial_features = openttd_rl::development::parse_financial_features(
            args.contains("--financial-features") ? args.at("--financial-features") : "raw");
        const torch::Device device(args.at("--device"));
        if (device.is_cuda() && !torch::cuda::is_available()) throw std::runtime_error("CUDA requested but unavailable; no fallback");
        torch::set_num_threads(1);
        // Match live training: CUDA graph scatter_add otherwise changes low bits
        // between identical inference processes. Configure cuBLAS before handles.
        if (::setenv("CUBLAS_WORKSPACE_CONFIG", ":4096:8", 1) != 0)
            throw std::runtime_error("cannot configure deterministic cuBLAS workspace");
        at::globalContext().setDeterministicAlgorithms(true, false);
        at::globalContext().setDeterministicCuDNN(true);
        at::globalContext().setBenchmarkCuDNN(false);
        openttd_rl::training::RngStreams rng(std::stoull(args.at("--seed")));
        openttd_rl::v2::ScalablePolicy model(rng.initialization_seed());
        if (args.contains("--weights")) {
            const std::filesystem::path path(args.at("--weights"));
            if (!path.is_absolute() || !std::filesystem::is_regular_file(path))
                throw std::invalid_argument("inference weights must be an existing absolute file");
            torch::serialize::InputArchive archive;
            archive.load_from(path.string(), torch::Device(torch::kCPU));
            openttd_rl::development::read_live_v2_weights(archive, model, financial_features);
            openttd_rl::v2::require_finite_policy(model, "loaded inference weights");
        }
        model->to(device); model->eval();
        auto hidden = torch::zeros({1, openttd_rl::v2::kHiddenSize}, torch::TensorOptions().device(device));
        torch::NoGradGuard guard;
        std::cout << std::setprecision(9);
        std::string line;
        while (std::getline(std::cin, line)) {
            if (line == "CLOSE") { std::cout << "{\"status\":\"CLOSED\"}" << std::endl; break; }
            if (line == "RESET") { hidden.zero_(); std::cout << "{\"status\":\"RESET\"}" << std::endl; continue; }
            if (line == "DETERMINISM_INFO") {
                std::cout << "{\"deterministic_algorithms\":" << std::boolalpha
                    << at::globalContext().deterministicAlgorithms()
                    << ",\"warn_only\":" << at::globalContext().deterministicAlgorithmsWarnOnly()
                    << ",\"cudnn_deterministic\":" << at::globalContext().deterministicCuDNN()
                    << ",\"cudnn_benchmark\":" << at::globalContext().benchmarkCuDNN()
                    << ",\"cublas_workspace_config\":\"" << std::getenv("CUBLAS_WORKSPACE_CONFIG")
                    << "\",\"threads\":" << torch::get_num_threads() << "}" << std::endl;
                continue;
            }
            if (line == "FINANCIAL_FEATURES_INFO") {
                std::cout << "{\"financial_features\":\"" << openttd_rl::development::financial_features_name(financial_features) << "\"}" << std::endl;
                continue;
            }
            const auto delimiter = line.find('\t');
            if (line.size() > 8192 || delimiter == std::string::npos || line.find('\t', delimiter + 1) != std::string::npos)
                throw std::invalid_argument("inference expects observation.bin TAB candidates.bin");
            auto cpu = openttd_rl::development::read_live_v2_input(line.substr(0, delimiter), line.substr(delimiter + 1), financial_features);
            auto input = openttd_rl::development::live_v2_to(cpu, device);
            input.hidden_state = hidden;
            const auto output = model->forward(input);
            const auto distribution = openttd_rl::development::live_v2_distribution(output, input);
            const auto log_probabilities = distribution.log_probabilities.cpu();
            const auto probabilities = distribution.probabilities.cpu().contiguous();
            const auto actions = args.at("--mode") == "greedy" ? log_probabilities.argmax(1) :
                openttd_rl::training::sample_masked_actions(log_probabilities, cpu.candidate_mask, rng.action_sampling());
            const auto action = actions.item<int64_t>();
            hidden = output.next_hidden;
            std::cout << "{\"schema_version\":\"" << openttd_rl::development::kLiveV2TensorSchema << "\",\"row\":" << action
                << ",\"value\":" << output.value.item<float>() << ",\"log_probability\":" << log_probabilities[0][action].item<float>()
                << ",\"entropy\":" << distribution.entropy.item<float>() << ",\"probabilities\":[";
            const auto *values = probabilities.data_ptr<float>();
            for (int64_t row = 0; row < openttd_rl::v2::kCandidateCapacity; ++row) {
                if (row != 0) std::cout << ',';
                std::cout << values[row];
            }
            std::cout << "]}" << std::endl;
        }
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "live V2 inference failed: " << error.what() << '\n';
        return 1;
    }
}
