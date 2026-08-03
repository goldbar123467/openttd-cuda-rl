#include "openttd_rl/v2/m22_evaluation.h"

#include <array>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {

struct Case {
    openttd_rl::v2::M22FinalPublicState state;
    std::int64_t program;
    std::int64_t mode;
};

void require(bool condition, const char *message)
{
    if (!condition) throw std::runtime_error(message);
}

void run()
{
    using namespace openttd_rl::v2;
    const std::array<Case, 16> cases = {{
        {{"service", "road", "temperate", 64, 64, "PASS", "not-applicable", "passenger-service", "G15"}, 1, 0},
        {{"service", "road", "arctic", 128, 64, "MAIL", "not-applicable", "single-leg", "G16"}, 2, 0},
        {{"service", "rail", "tropic", 512, 128, "PASS", "not-applicable", "passenger", "G17"}, 3, 1},
        {{"service", "rail", "toyland", 1024, 1024, "TOYS", "not-applicable", "freight", "G17"}, 4, 1},
        {{"service", "water", "temperate", 64, 128, "PASS", "not-applicable", "natural", "G18"}, 5, 2},
        {{"service", "water", "arctic", 128, 1024, "COAL", "not-applicable", "constructed", "G18"}, 6, 2},
        {{"service", "air", "tropic", 512, 64, "PASS", "not-applicable", "service", "G19"}, 7, 3},
        {{"service", "air", "toyland", 1024, 128, "GOOD", "not-applicable", "helicopter", "G19"}, 8, 3},
        {{"service", "multimodal", "temperate", 64, 1024, "GOOD", "not-applicable", "multimodal", "G19"}, 9, 4},
        {{"routing", "multimodal", "arctic", 128, 128, "PASS", "not-applicable", "router", "G19"}, 10, 4},
        {{"competition", "company", "tropic", 512, 1024, "PASS", "KrakenAI2", "head-to-head", "G20"}, 11, 5},
        {{"retention", "broad", "toyland", 1024, 64, "not-applicable", "not-applicable", "calendar", "G21"}, 12, 6},
        {{"retention", "broad", "temperate", 64, 64, "not-applicable", "not-applicable", "authority-economy", "G21"}, 13, 6},
        {{"retention", "broad", "arctic", 128, 128, "not-applicable", "not-applicable", "events", "G21"}, 14, 6},
        {{"retention", "broad", "tropic", 512, 1024, "not-applicable", "not-applicable", "gamescript", "G21"}, 15, 6},
        {{"retention", "broad", "toyland", 1024, 1024, "not-applicable", "not-applicable", "content", "G21"}, 16, 6},
    }};
    for (const auto &item : cases) {
        const auto batch = encode_m22_final_public_state(item.state);
        require(batch.program_mask.sum().item<std::int64_t>() == 2 &&
                batch.program_mask.index({0, 0}).item<bool>() &&
                batch.program_mask.index({0, item.program}).item<bool>(),
                "M22 evaluation public capability mask drifted");
        require(batch.public_features.index({0, item.mode}).item<float>() == 1.0F &&
                batch.public_features.index({0, 13 + item.program}).item<float>() == 1.0F &&
                batch.public_features.index({0, 11}).item<float>() == static_cast<float>(item.state.map_width) / 4096.0F &&
                batch.public_features.index({0, 12}).item<float>() == static_cast<float>(item.state.map_height) / 4096.0F,
                "M22 evaluation public feature encoding drifted");
        const auto encoded = m22_evaluation_input(batch, torch::kCPU);
        require(encoded.program_mask.sizes() == torch::IntArrayRef({1, kM22ProgramCount}) &&
                encoded.base.hidden_state.sizes() == torch::IntArrayRef({1, kHiddenSize}) &&
                encoded.base.recurrent_reset.item<bool>(),
                "M22 evaluation recurrent/generalist input drifted");
    }
    GeneralistPolicy model(UINT64_C(0x12345678), GeneralistArchitecture::Monolithic);
    model->eval();
    torch::NoGradGuard guard;
    const auto batch = encode_m22_final_public_state(cases.front().state);
    const auto output = model->forward(m22_evaluation_input(batch, torch::kCPU));
    require(torch::isfinite(output.program_logits).all().item<bool>() &&
            torch::isfinite(output.program_value).all().item<bool>() &&
            torch::isfinite(output.next_hidden).all().item<bool>() &&
            output.program_logits.index({0, 2}).item<float>() == -1.0e9F,
            "M22 evaluation forward/masking failed");

    auto invalid = cases.front().state;
    invalid.transport_mode = "air";
    try {
        static_cast<void>(encode_m22_final_public_state(invalid));
        require(false, "M22 evaluation accepted a gate/mode contradiction");
    } catch (const std::invalid_argument &) {
    }
    invalid = cases[10].state;
    invalid.opponent = "not-applicable";
    try {
        static_cast<void>(encode_m22_final_public_state(invalid));
        require(false, "M22 evaluation accepted a competition case without an opponent");
    } catch (const std::invalid_argument &) {
    }
    invalid = cases[11].state;
    invalid.native_probe = "unknown-probe";
    try {
        static_cast<void>(encode_m22_final_public_state(invalid));
        require(false, "M22 evaluation accepted an unknown public probe");
    } catch (const std::invalid_argument &) {
    }
    std::cout << "M22_EVALUATION_GATE=PASS programs=" << cases.size()
              << " seed_input=absent required_program_input=absent optimizer=absent\n";
}

} // namespace

int main()
{
    try {
        run();
        return 0;
    } catch (const c10::Error &error) {
        std::cerr << "M22_EVALUATION_GATE=FAIL " << error.what_without_backtrace() << '\n';
        return 1;
    } catch (const std::exception &error) {
        std::cerr << "M22_EVALUATION_GATE=FAIL " << error.what() << '\n';
        return 1;
    }
}
