#include "openttd_rl/v2/m22_trainer.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include <torch/cuda.h>
#include <torch/torch.h>

namespace {

using torch::indexing::Slice;

void require(bool condition, const char *message)
{
    if (!condition) throw std::runtime_error(message);
}

std::int64_t program_mode(std::int64_t program)
{
    if (program <= 2) return 0;
    if (program <= 4) return 1;
    if (program <= 6) return 2;
    if (program <= 8) return 3;
    if (program <= 10) return 4;
    if (program == 11) return 5;
    return 6;
}

openttd_rl::v2::M22CompactBatch make_compact(
    std::int64_t batch,
    std::int64_t program_offset,
    const torch::Tensor &hidden,
    bool reset)
{
    using namespace openttd_rl::v2;
    const auto floats = torch::TensorOptions().dtype(torch::kFloat32);
    const auto booleans = torch::TensorOptions().dtype(torch::kBool);
    auto features = torch::zeros({batch, kM22CompactFeatures}, floats);
    auto mask = torch::zeros({batch, kM22ProgramCount}, booleans);
    mask.index_put_({Slice(), 0}, true);
    for (std::int64_t row = 0; row < batch; ++row) {
        const auto program = 1 + (program_offset + row) % 16;
        features.index_put_({row, program_mode(program)}, 1.0F);
        features.index_put_({row, 7 + program % 4}, 1.0F);
        features.index_put_({row, 11}, 64.0F / 4096.0F);
        features.index_put_({row, 12}, 64.0F / 4096.0F);
        features.index_put_({row, 13}, 4096.0F / 1048576.0F);
        features.index_put_({row, 13 + program}, 1.0F);
        features.index_put_({row, 31}, 0.5F);
        mask.index_put_({row, program}, true);
    }
    return {features, mask, hidden.clone(), torch::full({batch}, reset, booleans)};
}

openttd_rl::v2::M22CompactBatch concatenate(const std::vector<openttd_rl::v2::M22CompactBatch> &items)
{
    std::vector<torch::Tensor> features;
    std::vector<torch::Tensor> masks;
    std::vector<torch::Tensor> hidden;
    std::vector<torch::Tensor> resets;
    for (const auto &item : items) {
        features.push_back(item.public_features);
        masks.push_back(item.program_mask);
        hidden.push_back(item.hidden_state);
        resets.push_back(item.recurrent_reset);
    }
    return {torch::cat(features), torch::cat(masks), torch::cat(hidden), torch::cat(resets)};
}

openttd_rl::v2::M22RolloutBatch collect_rollout(
    openttd_rl::v2::M22Trainer &trainer,
    const openttd_rl::v2::M22PpoConfig &config)
{
    using namespace openttd_rl::v2;
    std::vector<M22CompactBatch> compact_steps;
    std::vector<torch::Tensor> actions;
    std::vector<torch::Tensor> logs;
    std::vector<torch::Tensor> values;
    std::vector<torch::Tensor> rewards;
    auto hidden = torch::zeros({config.parallel_environments, kHiddenSize}, torch::kFloat32);
    for (std::int64_t time = 0; time < config.rollout_steps; ++time) {
        auto compact = make_compact(config.parallel_environments, time * 2, hidden, time == 0);
        const auto correct = m22_public_heuristic(compact);
        const auto action = trainer.act(compact, false);
        compact_steps.push_back(compact);
        actions.push_back(action.actions);
        logs.push_back(action.log_probabilities);
        values.push_back(action.values);
        rewards.push_back((action.actions == correct).to(torch::kFloat32));
        hidden = action.next_hidden;
    }
    const auto value_matrix = torch::cat(values).reshape({config.rollout_steps, config.parallel_environments});
    auto next_values = torch::zeros_like(value_matrix);
    next_values.index_put_({Slice(0, config.rollout_steps - 1), Slice()}, value_matrix.index({Slice(1), Slice()}));
    auto bootstrap = torch::ones_like(value_matrix);
    auto continuation = torch::ones_like(value_matrix);
    bootstrap.index_put_({config.rollout_steps - 1, Slice()}, 0.0F);
    continuation.index_put_({config.rollout_steps - 1, Slice()}, 0.0F);
    const auto gae = m22_compute_gae(
        torch::cat(rewards).reshape({config.rollout_steps, config.parallel_environments}),
        value_matrix,
        next_values,
        bootstrap,
        continuation,
        config.gamma,
        config.gae_lambda);
    return {
        concatenate(compact_steps),
        torch::cat(actions),
        torch::cat(logs),
        value_matrix.flatten(),
        m22_normalize_advantages(gae.advantages.flatten()),
        gae.returns.flatten(),
    };
}

double maximum_parameter_change(
    const std::vector<torch::Tensor> &before,
    const openttd_rl::v2::GeneralistPolicy &model)
{
    const auto after = model->parameters(true);
    require(before.size() == after.size(), "M22 parameter inventory drifted during update");
    double maximum = 0.0;
    for (std::size_t index = 0; index < before.size(); ++index) {
        maximum = std::max(maximum, torch::max(torch::abs(
            before[index] - after[index].detach().to(torch::kCPU))).item<double>());
    }
    return maximum;
}

void test_encoder_and_heuristic(const torch::Device &device)
{
    using namespace openttd_rl::v2;
    const auto hidden = torch::zeros({2, kHiddenSize}, torch::kFloat32);
    auto compact = make_compact(2, 3, hidden, true);
    compact.validate();
    const auto heuristic = m22_public_heuristic(compact);
    require(heuristic.index({0}).item<std::int64_t>() == 4 && heuristic.index({1}).item<std::int64_t>() == 5,
            "M22 public heuristic did not select the capability-compatible program");
    const auto input = m22_encode_compact(compact, device);
    require(input.base.graph_node_mask.index({0, 0}).item<bool>() &&
            input.base.graph_edge_mask.index({0, 0}).item<bool>(),
            "M22 compact encoder did not exercise graph state");
    require(input.domain_token_mask.index({0, 0}).item<bool>() &&
            input.program_mask.index({0, 4}).item<bool>(),
            "M22 compact encoder lost attention or legal-program state");
    auto invalid = compact;
    invalid.public_features = compact.public_features.clone();
    invalid.public_features.index_put_({0, 17}, 0.0F);
    try {
        invalid.validate();
        throw std::runtime_error("M22 compact encoder accepted a legal program without public capability");
    } catch (const std::invalid_argument &) {
    }
}

void test_rng_recovery(const torch::Device &device)
{
    using namespace openttd_rl::v2;
    M22PpoConfig config;
    config.rollout_steps = 8;
    config.parallel_environments = 2;
    config.minibatch_size = 16;
    config.epochs = 2;
    M22Trainer uninterrupted(config, UINT64_C(2200301), GeneralistArchitecture::Monolithic, device);
    const auto compact = make_compact(2, 1, torch::zeros({2, kHiddenSize}), true);
    static_cast<void>(uninterrupted.act(compact, false));
    const auto state = uninterrupted.runtime_state();
    M22Trainer recovered(config, UINT64_C(2200301), GeneralistArchitecture::Monolithic, device);
    recovered.restore_runtime_state(state);
    const auto left = uninterrupted.act(compact, false);
    const auto right = recovered.act(compact, false);
    require(torch::equal(left.actions, right.actions) && torch::equal(left.log_probabilities, right.log_probabilities),
            "M22 action RNG recovery is not exact");
    auto malformed = state;
    malformed.action_rng = "not-an-rng";
    try {
        recovered.restore_runtime_state(malformed);
        throw std::runtime_error("malformed M22 RNG state was accepted");
    } catch (const std::invalid_argument &) {
    }
}

openttd_rl::v2::M22UpdateMetrics test_trainer(
    const torch::Device &device,
    openttd_rl::v2::GeneralistArchitecture architecture,
    std::uint64_t seed)
{
    using namespace openttd_rl::v2;
    M22PpoConfig config;
    config.rollout_steps = 8;
    config.parallel_environments = 2;
    config.minibatch_size = 16;
    config.epochs = 2;
    M22Trainer trainer(config, seed, architecture, device);
    std::vector<torch::Tensor> before;
    for (const auto &parameter : trainer.model()->parameters(true)) {
        before.push_back(parameter.detach().to(torch::kCPU).clone());
    }
    const auto rollout = collect_rollout(trainer, config);
    rollout.validate(config);
    const auto metrics = trainer.update(rollout);
    require(metrics.update == 1 && metrics.transitions == 16 && trainer.counters().completed_rollouts == 1,
            "M22 trainer counters drifted");
    require(std::isfinite(metrics.policy_loss) && std::isfinite(metrics.value_loss) &&
            std::isfinite(metrics.entropy) && std::isfinite(metrics.gradient_norm) && metrics.gradient_norm > 0.0,
            "M22 trainer metrics are nonfinite or vacuous");
    require(maximum_parameter_change(before, trainer.model()) > 0.0, "M22 recurrent PPO update did not mutate parameters");
    require_finite_generalist(trainer.model(), "M22 trainer gate");
    return metrics;
}

void run(const torch::Device &device)
{
    using namespace openttd_rl::v2;
    test_encoder_and_heuristic(device);
    test_rng_recovery(device);
    const auto monolithic = test_trainer(device, GeneralistArchitecture::Monolithic, UINT64_C(1910917137));
    const auto specialist = test_trainer(device, GeneralistArchitecture::SpecialistRouter, UINT64_C(1910917137));
    std::cout << "M22_TRAINER_GATE=PASS device=" << device.str()
              << " monolithic_loss=" << monolithic.policy_loss
              << " specialist_loss=" << specialist.policy_loss
              << " transitions=" << (monolithic.transitions + specialist.transitions) << '\n';
}

} // namespace

int main(int argc, char **argv)
{
    try {
        if (argc != 3 || std::string(argv[1]) != "--device") {
            throw std::invalid_argument("usage: m22_trainer_gate --device cpu|cuda:0");
        }
        const std::string requested = argv[2];
        if (requested == "cpu") {
            run(torch::kCPU);
        } else if (requested == "cuda:0") {
            if (!torch::cuda::is_available()) throw std::runtime_error("CUDA is unavailable");
            run(torch::Device(torch::kCUDA, 0));
        } else {
            throw std::invalid_argument("device must be cpu or cuda:0");
        }
        return 0;
    } catch (const c10::Error &error) {
        std::cerr << "M22_TRAINER_GATE=FAIL " << error.what_without_backtrace() << '\n';
        return 1;
    } catch (const std::exception &error) {
        std::cerr << "M22_TRAINER_GATE=FAIL " << error.what() << '\n';
        return 1;
    }
}
