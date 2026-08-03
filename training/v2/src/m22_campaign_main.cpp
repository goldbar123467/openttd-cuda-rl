#include "openttd_rl/v2/m22_campaign.h"

#include <cstdint>
#include <filesystem>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>

#include <torch/cuda.h>

namespace {

std::map<std::string, std::string> arguments(int argc, char **argv)
{
    if (argc < 2 || argc % 2 == 0) throw std::invalid_argument("M22 campaign arguments must be --name value pairs");
    std::map<std::string, std::string> result;
    for (int index = 1; index < argc; index += 2) {
        const std::string key = argv[index];
        if (!key.starts_with("--") || !result.emplace(key, argv[index + 1]).second) {
            throw std::invalid_argument("M22 campaign argument is malformed or duplicated");
        }
    }
    return result;
}

const std::string &required(const std::map<std::string, std::string> &args, const std::string &name)
{
    const auto found = args.find(name);
    if (found == args.end()) throw std::invalid_argument("missing M22 campaign argument: " + name);
    return found->second;
}

std::uint64_t unsigned_value(const std::string &value, const char *name)
{
    try {
        std::size_t consumed = 0;
        const auto result = std::stoull(value, &consumed);
        if (consumed != value.size()) throw std::invalid_argument("trailing");
        return result;
    } catch (const std::exception &) {
        throw std::invalid_argument(std::string(name) + " must be an unsigned integer");
    }
}

torch::Device device(const std::string &value)
{
    if (value == "cpu") return torch::kCPU;
    if (value == "cuda:0") {
        if (!torch::cuda::is_available()) throw std::runtime_error("cuda-unavailable: M22 campaign requested cuda:0");
        return torch::Device(torch::kCUDA, 0);
    }
    throw std::invalid_argument("M22 campaign device must be cpu or cuda:0");
}

void run(int argc, char **argv)
{
    using namespace openttd_rl::v2;
    const auto args = arguments(argc, argv);
    const auto corpus = load_m22_corpus(std::filesystem::absolute(required(args, "--corpus")));
    const auto policy_device = device(required(args, "--device"));
    const auto additional = unsigned_value(required(args, "--additional-updates"), "additional updates");
    if (additional == 0 || additional > 48) throw std::invalid_argument("M22 additional updates must be in [1,48]");
    const auto checkpoint_root = std::filesystem::absolute(required(args, "--checkpoint-root"));
    std::unique_ptr<M22Campaign> campaign;
    const auto resume = args.find("--resume");
    if (resume != args.end()) {
        auto loaded = load_m22_checkpoint(std::filesystem::absolute(resume->second), policy_device);
        campaign = std::make_unique<M22Campaign>(corpus, std::move(loaded.trainer), loaded.campaign);
    } else {
        const auto architecture = parse_generalist_architecture(required(args, "--architecture"));
        const auto seed = unsigned_value(required(args, "--seed"), "run seed");
        M22PpoConfig config;
        auto trainer = std::make_unique<M22Trainer>(config, seed, architecture, policy_device);
        campaign = std::make_unique<M22Campaign>(corpus, std::move(trainer));
    }
    if (campaign->trainer().counters().completed_updates + additional > 48U) {
        throw std::invalid_argument("M22 campaign would exceed the frozen 48-update budget");
    }
    for (std::uint64_t index = 0; index < additional; ++index) {
        const auto result = campaign->run_update();
        std::cout << "M22_UPDATE " << m22_campaign_update_json(result) << '\n' << std::flush;
        if (result.retention_ran && result.trainer.update % 8U == 0U && result.retention.checkpoint_allowed) {
            const auto saved = save_m22_checkpoint(checkpoint_root, campaign->trainer(), campaign->checkpoint_state());
            std::cout << "M22_CHECKPOINT update=" << result.trainer.update << " id=" << saved.checkpoint_id
                      << " path=" << saved.path.string() << '\n' << std::flush;
        }
    }
    std::cout << "M22_CAMPAIGN=PASS architecture=" << generalist_architecture_name(campaign->trainer().architecture())
              << " seed=" << campaign->trainer().run_seed()
              << " updates=" << campaign->trainer().counters().completed_updates
              << " transitions=" << campaign->trainer().counters().accepted_transitions << '\n';
}

} // namespace

int main(int argc, char **argv)
{
    try {
        run(argc, argv);
        return 0;
    } catch (const c10::Error &error) {
        std::cerr << "M22_CAMPAIGN=FAIL " << error.what_without_backtrace() << '\n';
        return 1;
    } catch (const std::exception &error) {
        std::cerr << "M22_CAMPAIGN=FAIL " << error.what() << '\n';
        return 1;
    }
}
