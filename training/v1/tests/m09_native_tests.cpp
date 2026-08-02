#include <array>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <unistd.h>

#include <torch/torch.h>

#include "openttd_rl/training/evaluation_model.h"

namespace {

void check(bool condition, const char *message)
{
    if (!condition) throw std::runtime_error(message);
}

std::filesystem::path unique_root()
{
    const auto stamp = std::chrono::steady_clock::now().time_since_epoch().count();
    return std::filesystem::temp_directory_path() /
        ("openttd-rl-m09-native-" + std::to_string(::getpid()) + "-" + std::to_string(stamp));
}

void test_architecture(openttd_rl::training::ArchitectureKind architecture, std::uint64_t seed)
{
    using namespace openttd_rl::training;
    const auto root = unique_root();
    MultiModalActorCritic model(architecture, seed);
    const auto saved = save_evaluation_model(
        root,
        model,
        architecture,
        {"412f40af7dbbab83323ad4ae73cda0744ebf887b", seed, 16, 2048, -0.125});
    check(saved.path == root / saved.package_id && saved.package_id.size() == 64U, "evaluation-model content address is invalid");
    const auto manifest_time = std::filesystem::last_write_time(saved.path / "manifest.json");
    const auto model_time = std::filesystem::last_write_time(saved.path / "model.pt");
    ReadOnlyEvaluationPolicy first(saved.path, 991);
    ReadOnlyEvaluationPolicy second(saved.path, 991);
    const auto before = first.state_sha256();
    auto structured = torch::linspace(-1.0, 1.0, 3 * kStructuredFeatures, torch::kFloat32).reshape({3, kStructuredFeatures});
    auto spatial = torch::linspace(0.0, 1.0, 3 * kSpatialChannels * kSpatialHeight * kSpatialWidth, torch::kFloat32)
                       .reshape({3, kSpatialChannels, kSpatialHeight, kSpatialWidth});
    auto masks = torch::ones({3, kActionCount}, torch::kBool);
    masks.index_put_({0, 3}, false);
    const auto deterministic = first.act(structured, spatial, masks, true);
    check(deterministic.actions.sizes() == torch::IntArrayRef({3}), "evaluator action shape drifted");
    const auto stochastic_a = first.act(structured, spatial, masks, false);
    const auto stochastic_b = second.act(structured, spatial, masks, false);
    check(torch::equal(stochastic_a.actions, stochastic_b.actions), "seeded evaluator sampling is not reproducible");
    check(first.state_sha256() == before, "evaluator mutated model parameters");
    check(std::filesystem::last_write_time(saved.path / "manifest.json") == manifest_time &&
              std::filesystem::last_write_time(saved.path / "model.pt") == model_time,
        "evaluator wrote its read-only package");
    std::filesystem::remove_all(root);
}

void test_corruption_rejected()
{
    using namespace openttd_rl::training;
    const auto root = unique_root();
    MultiModalActorCritic model(ArchitectureKind::StructuredMlp, 88);
    const auto saved = save_evaluation_model(
        root,
        model,
        ArchitectureKind::StructuredMlp,
        {"412f40af7dbbab83323ad4ae73cda0744ebf887b", 88, 16, 2048, 0.25});
    {
        std::fstream stream(saved.path / "model.pt", std::ios::in | std::ios::out | std::ios::binary);
        check(static_cast<bool>(stream), "cannot open corruption fixture");
        char value = 0;
        stream.read(&value, 1);
        value ^= 0x01;
        stream.seekp(0);
        stream.write(&value, 1);
    }
    bool rejected = false;
    try {
        ReadOnlyEvaluationPolicy invalid(saved.path, 1);
        (void)invalid;
    } catch (const std::invalid_argument &) {
        rejected = true;
    }
    check(rejected, "corrupt evaluation-model payload was accepted");
    std::filesystem::remove_all(root);
}

} // namespace

int main()
{
    try {
        torch::set_num_threads(2);
        test_architecture(openttd_rl::training::ArchitectureKind::StructuredMlp, 101);
        test_architecture(openttd_rl::training::ArchitectureKind::SpatialCnn, 102);
        test_architecture(openttd_rl::training::ArchitectureKind::CombinedCnnMlp, 103);
        test_corruption_rejected();
        std::cout << "M09_NATIVE_TESTS=PASS architectures=3 read_only=PASS corruption=PASS\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "M09_NATIVE_TESTS=FAIL " << error.what() << '\n';
        return 1;
    }
}
