#include "openttd_rl/v2/m22_checkpoint.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include <torch/cuda.h>
#include <torch/nn/utils/clip_grad.h>
#include <torch/torch.h>
#include <unistd.h>

namespace {

void require(bool condition, const char *message)
{
    if (!condition) throw std::runtime_error(message);
}

openttd_rl::v2::M22CompactBatch compact(const openttd_rl::v2::M22Corpus &corpus)
{
    using namespace openttd_rl::v2;
    std::vector<const M22CorpusEntry *> entries;
    for (std::int64_t program = 1; program <= 8; ++program) {
        entries.push_back(&corpus.entry(M22CorpusSplit::Training, program));
    }
    return m22_compact_from_entries(
        entries,
        torch::zeros({8, kHiddenSize}, torch::kFloat32),
        torch::ones({8}, torch::kBool));
}

void optimization_step(openttd_rl::v2::M22Trainer &trainer, const openttd_rl::v2::M22CompactBatch &batch)
{
    using namespace openttd_rl::v2;
    const auto input = m22_encode_compact(batch, trainer.device());
    const auto output = trainer.model()->forward(input);
    const auto policy = m22_masked_categorical(output.program_logits, batch.program_mask.to(trainer.device()));
    const auto actions = m22_public_heuristic(batch).to(trainer.device());
    const auto selected = policy.log_probabilities.gather(1, actions.unsqueeze(1)).squeeze(1);
    const auto loss = -selected.mean() + 0.5 * torch::square(output.program_value).mean() - 0.01 * policy.entropy.mean();
    trainer.optimizer().zero_grad();
    loss.backward();
    const double norm = torch::nn::utils::clip_grad_norm_(trainer.model()->parameters(), 0.5, 2.0, true);
    require(std::isfinite(norm) && norm > 0.0, "M22 checkpoint fixture gradient is invalid");
    trainer.optimizer().step();
    require_finite_generalist(trainer.model(), "M22 checkpoint fixture update");
}

double maximum_parameter_difference(
    const openttd_rl::v2::GeneralistPolicy &left,
    const openttd_rl::v2::GeneralistPolicy &right)
{
    const auto left_parameters = left->named_parameters(true);
    const auto right_parameters = right->named_parameters(true);
    require(left_parameters.size() == right_parameters.size(), "M22 checkpoint parameter inventory drifted");
    double maximum = 0.0;
    for (const auto &item : left_parameters) {
        require(right_parameters.contains(item.key()), "M22 checkpoint lost a named parameter");
        maximum = std::max(maximum, torch::max(torch::abs(
            item.value().detach().to(torch::kCPU) - right_parameters[item.key()].detach().to(torch::kCPU))).item<double>());
    }
    return maximum;
}

void require_runtime_equal(
    const openttd_rl::v2::M22RuntimeState &left,
    const openttd_rl::v2::M22RuntimeState &right)
{
    require(left.run_seed == right.run_seed && left.architecture == right.architecture &&
            left.counters.completed_updates == right.counters.completed_updates &&
            left.counters.accepted_transitions == right.counters.accepted_transitions &&
            left.counters.completed_rollouts == right.counters.completed_rollouts &&
            left.action_rng == right.action_rng && left.minibatch_rng == right.minibatch_rng &&
            left.environment_rng == right.environment_rng && left.curriculum_rng == right.curriculum_rng,
            "M22 checkpoint runtime state recovery mismatch");
}

void run(const torch::Device &device, const std::filesystem::path &corpus_path)
{
    using namespace openttd_rl::v2;
    const auto corpus = load_m22_corpus(corpus_path);
    auto batch = compact(corpus);
    M22PpoConfig config;
    config.rollout_steps = 8;
    config.parallel_environments = 8;
    config.minibatch_size = 64;
    config.epochs = 1;
    M22Trainer trainer(config, UINT64_C(1910917137), GeneralistArchitecture::Monolithic, device);
    optimization_step(trainer, batch);
    trainer.counters() = {1, 64, 1};
    const auto sampled = trainer.act(batch, false);
    M22CampaignCheckpointState state{
        torch::zeros({kM22CompactFeatures}, torch::kFloat32),
        torch::ones({kM22CompactFeatures}, torch::kFloat32),
        64,
        sampled.next_hidden.clone(),
        {1, 2, 3, 4, 5, 6, 7, 8},
        2,
        0x1FE,
        1.0,
        8,
        64,
        "{\"checks\":[]}",
        "{\"eligible\":true}",
    };
    const auto before = trainer.act(batch, true);
    const auto runtime = trainer.runtime_state();
    const auto temporary = std::filesystem::temp_directory_path() /
        ("openttd-rl-m22-checkpoint-" + std::to_string(::getpid()) + "-" + (device.is_cuda() ? "cuda" : "cpu"));
    if (!std::filesystem::create_directory(temporary)) throw std::runtime_error("cannot create M22 checkpoint test directory");
    try {
        const auto saved = save_m22_checkpoint(temporary / "checkpoints", trainer, state);
        const auto after = trainer.act(batch, true);
        require(torch::equal(before.logits, after.logits) && torch::equal(before.values, after.values),
                "M22 checkpoint save mutated policy outputs");
        require_runtime_equal(runtime, trainer.runtime_state());

        bool overwrite_rejected = false;
        try {
            static_cast<void>(save_m22_checkpoint(temporary / "checkpoints", trainer, state));
        } catch (const std::runtime_error &) {
            overwrite_rejected = true;
        }
        require(overwrite_rejected, "M22 checkpoint save did not reject an existing content identity");

        auto loaded = load_m22_checkpoint(saved.path, device);
        require(loaded.checkpoint_id == saved.checkpoint_id && loaded.campaign.selection_json == state.selection_json &&
                loaded.campaign.retention_history_json == state.retention_history_json &&
                torch::equal(loaded.campaign.hidden_state, state.hidden_state),
                "M22 checkpoint campaign state recovery mismatch");
        require_runtime_equal(runtime, loaded.trainer->runtime_state());
        const auto recovered = loaded.trainer->act(batch, true);
        require(torch::equal(before.logits, recovered.logits) && torch::equal(before.values, recovered.values),
                "M22 same-device checkpoint forward recovery is not exact");

        const auto next_original = trainer.act(batch, false);
        const auto next_recovered = loaded.trainer->act(batch, false);
        require(torch::equal(next_original.actions, next_recovered.actions) &&
                torch::equal(next_original.log_probabilities, next_recovered.log_probabilities),
                "M22 checkpoint action stream recovery is not exact");
        optimization_step(trainer, batch);
        optimization_step(*loaded.trainer, batch);
        require(maximum_parameter_difference(trainer.model(), loaded.trainer->model()) == 0.0,
                "M22 checkpoint optimizer continuation is not exact");

        if (device.is_cuda()) {
            auto cpu = load_m22_checkpoint(saved.path, torch::kCPU);
            const auto cpu_output = cpu.trainer->act(batch, true);
            const auto error = torch::max(torch::abs(before.logits - cpu_output.logits)).item<double>();
            require(error <= 1.0e-4, "M22 canonical CPU checkpoint crossed device tolerance");
        }

        {
            std::ofstream extra(saved.path / "unexpected", std::ios::binary);
            extra << 'x';
        }
        bool inventory_rejected = false;
        try {
            static_cast<void>(load_m22_checkpoint(saved.path, device));
        } catch (const std::invalid_argument &) {
            inventory_rejected = true;
        }
        require(inventory_rejected, "M22 checkpoint accepted an unexpected inventory entry");
        std::filesystem::remove(saved.path / "unexpected");
        std::cout << "M22_CHECKPOINT_GATE=PASS device=" << device.str()
                  << " checkpoint=" << saved.checkpoint_id << '\n';
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
            throw std::invalid_argument("usage: m22_checkpoint_gate --device cpu|cuda:0 --corpus /absolute/path");
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
        std::cerr << "M22_CHECKPOINT_GATE=FAIL " << error.what_without_backtrace() << '\n';
        return 1;
    } catch (const std::exception &error) {
        std::cerr << "M22_CHECKPOINT_GATE=FAIL " << error.what() << '\n';
        return 1;
    }
}
