// Conversion oracle: expose authoritative native outputs without changing inference.
#include "v2_live_input.h"
#include "openttd_rl/v2/checkpoint.h"

#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {
void write_tensor(const char *name, const torch::Tensor &tensor)
{
    const auto flat = tensor.cpu().contiguous().flatten();
    if (flat.scalar_type() != torch::kFloat32 || !torch::isfinite(flat).all().item<bool>())
        throw std::runtime_error("oracle output must be finite float32");
    std::cout << '\"' << name << "\":[";
    const auto *values = flat.data_ptr<float>();
    for (int64_t index = 0; index < flat.numel(); ++index) {
        if (index != 0) std::cout << ',';
        std::cout << values[index];
    }
    std::cout << ']';
}
}

int main(int argc, char **argv)
{
    try {
        if ((argc != 3 && argc != 5) || std::string(argv[1]) != "--weights" ||
            (argc == 5 && std::string(argv[3]) != "--financial-features"))
            throw std::invalid_argument("required: --weights ABSOLUTE_FILE [--financial-features raw|signed-log-v1] (CPU conversion oracle)");
        const auto financial_features = openttd_rl::development::parse_financial_features(argc == 5 ? argv[4] : "raw");
        const std::filesystem::path path(argv[2]);
        if (!path.is_absolute() || !std::filesystem::is_regular_file(path))
            throw std::invalid_argument("oracle weights must be an existing absolute file");
        torch::set_num_threads(1);
        openttd_rl::v2::ScalablePolicy model(20260923);
        torch::serialize::InputArchive archive;
        archive.load_from(path.string(), torch::Device(torch::kCPU));
        openttd_rl::development::read_live_v2_weights(archive, model, financial_features);
        openttd_rl::v2::require_finite_policy(model, "export oracle weights");
        model->eval();
        auto hidden = torch::zeros({1, openttd_rl::v2::kHiddenSize}, torch::kFloat32);
        bool reset = false;
        torch::NoGradGuard guard;
        std::cout << std::setprecision(9);
        std::string line;
        while (std::getline(std::cin, line)) {
            if (line == "CLOSE") { std::cout << "{\"status\":\"CLOSED\"}" << std::endl; break; }
            if (line == "RESET") { reset = true; std::cout << "{\"status\":\"RESET\"}" << std::endl; continue; }
            const auto delimiter = line.find('\t');
            if (line.size() > 8192 || delimiter == std::string::npos || line.find('\t', delimiter + 1) != std::string::npos)
                throw std::invalid_argument("oracle expects observation.bin TAB candidates.bin");
            auto input = openttd_rl::development::read_live_v2_input(line.substr(0, delimiter), line.substr(delimiter + 1), financial_features);
            input.hidden_state = hidden;
            input.recurrent_reset.fill_(reset);
            reset = false;
            const auto output = model->forward(input);
            const auto distribution = openttd_rl::development::live_v2_distribution(output, input);
            hidden = output.next_hidden;
            std::cout << '{';
            write_tensor("family_logits", output.family_logits); std::cout << ',';
            write_tensor("candidate_logits", output.candidate_logits); std::cout << ',';
            write_tensor("value", output.value); std::cout << ',';
            write_tensor("next_hidden", output.next_hidden); std::cout << ',';
            write_tensor("probabilities", distribution.probabilities);
            std::cout << '}' << std::endl;
        }
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "V2 export oracle failed: " << error.what() << '\n';
        return 1;
    }
}
