// Read-only inspection of the exact native policy input boundary.
#include "v2_live_input.h"
#include <array>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <stdexcept>
#include <vector>

int main(int argc, char **argv)
{
    try {
        if (argc != 7) throw std::invalid_argument("required: --observation ABS --candidates ABS --financial-features MODE");
        std::map<std::string, std::string> args;
        for (int i = 1; i < argc; i += 2)
            if (!args.emplace(argv[i], argv[i + 1]).second) throw std::invalid_argument("duplicate audit option");
        const auto mode = openttd_rl::development::parse_financial_features(args.at("--financial-features"));
        torch::set_num_threads(1);
        const auto input = openttd_rl::development::read_live_v2_input(args.at("--observation"), args.at("--candidates"), mode);
        std::ifstream candidates(args.at("--candidates"), std::ios::binary);
        candidates.seekg(4096 * 32 * sizeof(float));
        std::vector<std::array<uint32_t, 16>> parameters(4096);
        candidates.read(reinterpret_cast<char *>(parameters.data()), static_cast<std::streamsize>(parameters.size() * sizeof(parameters[0])));
        if (!candidates) throw std::runtime_error("candidate parameters unreadable");
        std::cout << std::setprecision(std::numeric_limits<float>::max_digits10) << "{\"rows\":[";
        bool first = true;
        for (int64_t row = 0; row < 4096; ++row) if (input.candidate_mask[0][row].item<bool>()) {
            if (!first) std::cout << ',';
            first = false;
            std::cout << "{\"row\":" << row << ",\"family\":" << input.candidate_family[0][row].item<int64_t>() << ",\"parameters\":[";
            for (size_t j = 0; j < 16; ++j) { if (j) std::cout << ','; std::cout << parameters[static_cast<size_t>(row)][j]; }
            std::cout << "],\"features\":[";
            for (int64_t j = 0; j < 32; ++j) { if (j) std::cout << ','; std::cout << input.candidate_features[0][row][j].item<float>(); }
            std::cout << "]}";
        }
        std::cout << "]}" << std::endl;
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "native action audit failed: " << error.what() << '\n';
        return 1;
    }
}
