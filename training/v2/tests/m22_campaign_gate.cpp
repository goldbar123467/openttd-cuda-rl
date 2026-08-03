#include "openttd_rl/v2/m22_campaign.h"

#include <algorithm>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <string>

#include <torch/cuda.h>
#include <unistd.h>

namespace {

void require(bool condition, const char *message)
{
    if (!condition) throw std::runtime_error(message);
}

bool sha256(const std::string &value)
{
    return value.size() == 64 && value.find_first_not_of("0123456789abcdef") == std::string::npos;
}

double maximum_parameter_difference(
    const openttd_rl::v2::GeneralistPolicy &left,
    const openttd_rl::v2::GeneralistPolicy &right)
{
    const auto left_parameters = left->named_parameters(true);
    const auto right_parameters = right->named_parameters(true);
    require(left_parameters.size() == right_parameters.size(), "M22 campaign parameter inventory drifted");
    double maximum = 0.0;
    for (const auto &item : left_parameters) {
        require(right_parameters.contains(item.key()), "M22 campaign lost a named parameter");
        maximum = std::max(maximum, torch::max(torch::abs(
            item.value().detach().to(torch::kCPU) - right_parameters[item.key()].detach().to(torch::kCPU))).item<double>());
    }
    return maximum;
}

void test_baselines(const openttd_rl::v2::M22Corpus &corpus)
{
    using namespace openttd_rl::v2;
    std::vector<const M22CorpusEntry *> entries;
    for (std::int64_t program = 1; program < kM22ProgramCount; ++program) {
        entries.push_back(&corpus.entry(M22CorpusSplit::Development, program));
    }
    const auto compact = m22_compact_from_entries(
        entries,
        torch::zeros({16, kHiddenSize}, torch::kFloat32),
        torch::ones({16}, torch::kBool));
    const auto heuristic = m22_public_heuristic(compact);
    for (std::int64_t row = 0; row < 16; ++row) {
        require(heuristic.index({row}).item<std::int64_t>() == row + 1,
                "M22 matched public heuristic lost a development program");
        require(entries[static_cast<std::size_t>(row)]->rewards[0] == 0.0,
                "M22 wait-only baseline reward drifted");
    }
}

void run(const torch::Device &device, const std::filesystem::path &corpus_path)
{
    using namespace openttd_rl::v2;
    const auto corpus = load_m22_corpus(corpus_path);
    test_baselines(corpus);
    auto trainer = std::make_unique<M22Trainer>(
        M22PpoConfig{}, UINT64_C(1910917137), GeneralistArchitecture::Monolithic, device);
    M22Campaign uninterrupted(corpus, std::move(trainer));
    M22CampaignUpdateResult boundary;
    for (std::uint32_t update = 1; update <= 4; ++update) boundary = uninterrupted.run_update();
    require(boundary.retention_ran && boundary.retention.checkpoint_allowed &&
            uninterrupted.transition() == 512 && uninterrupted.episode() == 64,
            "M22 campaign did not reach the completed retention boundary");
    require(sha256(boundary.case_order_sha256) && sha256(boundary.actions_sha256) &&
            sha256(boundary.log_probabilities_sha256) && sha256(boundary.values_sha256) &&
            sha256(boundary.rewards_sha256) && sha256(boundary.hidden_state_sha256),
            "M22 campaign did not publish complete exact-recovery trace identities");
    require(std::accumulate(boundary.case_program_counts.begin(), boundary.case_program_counts.end(), UINT32_C(0)) == 128U &&
            std::accumulate(boundary.action_counts.begin(), boundary.action_counts.end(), UINT32_C(0)) == 128U,
            "M22 campaign case/action count projection drifted");
    const auto temporary = std::filesystem::temp_directory_path() /
        ("openttd-rl-m22-campaign-" + std::to_string(::getpid()) + "-" + (device.is_cuda() ? "cuda" : "cpu"));
    if (!std::filesystem::create_directory(temporary)) throw std::runtime_error("cannot create M22 campaign test directory");
    try {
        const auto saved = save_m22_checkpoint(
            temporary / "boundary", uninterrupted.trainer(), uninterrupted.checkpoint_state());
        auto loaded = load_m22_checkpoint(saved.path, device);
        M22Campaign resumed(corpus, std::move(loaded.trainer), loaded.campaign);
        const auto continuous_result = uninterrupted.run_update();
        const auto resumed_result = resumed.run_update();
        require(m22_campaign_update_json(continuous_result) == m22_campaign_update_json(resumed_result),
                "M22 resumed campaign metrics differ from uninterrupted metrics");
        require(maximum_parameter_difference(uninterrupted.trainer().model(), resumed.trainer().model()) == 0.0,
                "M22 resumed campaign parameters differ from uninterrupted parameters");
        const auto continuous_runtime = uninterrupted.trainer().runtime_state();
        const auto resumed_runtime = resumed.trainer().runtime_state();
        require(continuous_runtime.action_rng == resumed_runtime.action_rng &&
                continuous_runtime.minibatch_rng == resumed_runtime.minibatch_rng &&
                continuous_runtime.environment_rng == resumed_runtime.environment_rng &&
                continuous_runtime.curriculum_rng == resumed_runtime.curriculum_rng,
                "M22 resumed campaign RNG streams differ from uninterrupted streams");
        std::cout << "M22_CAMPAIGN_GATE=PASS device=" << device.str()
                  << " boundary=" << saved.checkpoint_id
                  << " update=" << continuous_result.trainer.update << '\n';
    } catch (...) {
        std::error_code ignored;
        std::filesystem::remove_all(temporary, ignored);
        throw;
    }
    std::error_code ignored;
    std::filesystem::remove_all(temporary, ignored);
}

} // namespace

int main(int argc, char **argv)
{
    try {
        if (argc != 5 || std::string(argv[1]) != "--device" || std::string(argv[3]) != "--corpus") {
            throw std::invalid_argument("usage: m22_campaign_gate --device cpu|cuda:0 --corpus /absolute/path");
        }
        const std::string requested = argv[2];
        if (requested == "cpu") {
            run(torch::kCPU, argv[4]);
        } else if (requested == "cuda:0") {
            if (!torch::cuda::is_available()) throw std::runtime_error("CUDA is unavailable");
            run(torch::Device(torch::kCUDA, 0), argv[4]);
        } else {
            throw std::invalid_argument("device must be cpu or cuda:0");
        }
        return 0;
    } catch (const c10::Error &error) {
        std::cerr << "M22_CAMPAIGN_GATE=FAIL " << error.what_without_backtrace() << '\n';
        return 1;
    } catch (const std::exception &error) {
        std::cerr << "M22_CAMPAIGN_GATE=FAIL " << error.what() << '\n';
        return 1;
    }
}
