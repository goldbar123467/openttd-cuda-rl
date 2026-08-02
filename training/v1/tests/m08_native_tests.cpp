#include <exception>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

#include <torch/torch.h>

#include "openttd_rl/training/model.h"
#include "openttd_rl/training/multimodal_model.h"
#include "openttd_rl/training/multimodal_trainer.h"

namespace {

using openttd_rl::training::ArchitectureKind;
using openttd_rl::training::MultiModalActorCritic;

void check(bool condition, const std::string &message)
{
    if (!condition) throw std::runtime_error(message);
}

torch::Tensor structured_observations(std::int64_t batch)
{
    auto values = torch::arange(
        batch * openttd_rl::training::kStructuredFeatures,
        torch::TensorOptions().dtype(torch::kFloat32));
    return torch::sin(values.reshape({batch, openttd_rl::training::kStructuredFeatures}) * 0.013F);
}

torch::Tensor spatial_observations(std::int64_t batch)
{
    auto values = torch::arange(
        batch * openttd_rl::training::kSpatialChannels * openttd_rl::training::kSpatialHeight *
            openttd_rl::training::kSpatialWidth,
        torch::TensorOptions().dtype(torch::kFloat32));
    return ((values.remainder(257) / 256.0F).reshape(
        {batch,
            openttd_rl::training::kSpatialChannels,
            openttd_rl::training::kSpatialHeight,
            openttd_rl::training::kSpatialWidth}));
}

void test_architecture_identity()
{
    const std::vector<std::pair<std::string, ArchitectureKind>> identities{
        {"structured-mlp-v1", ArchitectureKind::StructuredMlp},
        {"spatial-cnn-v1", ArchitectureKind::SpatialCnn},
        {"combined-cnn-mlp-v1", ArchitectureKind::CombinedCnnMlp},
    };
    for (const auto &[name, kind] : identities) {
        check(openttd_rl::training::parse_architecture_kind(name) == kind, "architecture parser mismatch");
        check(std::string(openttd_rl::training::architecture_name(kind)) == name, "architecture name mismatch");
    }
    bool rejected = false;
    try {
        (void)openttd_rl::training::parse_architecture_kind("unknown-v1");
    } catch (const std::invalid_argument &) {
        rejected = true;
    }
    check(rejected, "unknown architecture was accepted");
}

void test_structured_oracle_compatibility()
{
    constexpr std::uint64_t seed = 8431;
    openttd_rl::training::ActorCritic oracle(seed);
    MultiModalActorCritic unified(ArchitectureKind::StructuredMlp, seed);
    const auto structured = structured_observations(7);
    const auto spatial = spatial_observations(7);
    torch::NoGradGuard guard;
    const auto expected = oracle->forward(structured);
    const auto actual = unified->forward(structured, spatial);
    check(torch::equal(expected.first, actual.first), "unified structured logits changed the M07 CPU oracle");
    check(torch::equal(expected.second, actual.second), "unified structured values changed the M07 CPU oracle");
    const auto oracle_parameters = oracle->named_parameters(true);
    const auto unified_parameters = unified->named_parameters(true);
    check(oracle_parameters.size() == unified_parameters.size(), "unified structured parameter count changed");
    for (const auto &parameter : oracle_parameters) {
        check(unified_parameters.contains(parameter.key()), "unified structured parameter name changed");
        check(torch::equal(parameter.value(), unified_parameters[parameter.key()]),
            "unified structured parameter value changed");
    }
}

std::int64_t parameter_count(const MultiModalActorCritic &model)
{
    std::int64_t count = 0;
    for (const auto &parameter : model->parameters()) count += parameter.numel();
    return count;
}

void test_all_architectures_forward_and_gradient()
{
    const auto structured = structured_observations(4);
    const auto spatial = spatial_observations(4);
    std::vector<std::int64_t> counts;
    for (const auto kind : {
             ArchitectureKind::StructuredMlp,
             ArchitectureKind::SpatialCnn,
             ArchitectureKind::CombinedCnnMlp,
         }) {
        MultiModalActorCritic model(kind, 9427);
        const auto output = model->forward(structured, spatial);
        check(output.first.sizes() == torch::IntArrayRef({4, openttd_rl::training::kActionCount}),
            "policy output has the wrong shape");
        check(output.second.sizes() == torch::IntArrayRef({4}), "value output has the wrong shape");
        check(output.first.scalar_type() == torch::kFloat32 && output.second.scalar_type() == torch::kFloat32,
            "model output has the wrong dtype");
        const auto loss = output.first.square().mean() + output.second.square().mean();
        loss.backward();
        bool observed_nonzero_gradient = false;
        for (const auto &parameter : model->named_parameters(true)) {
            check(parameter.value().grad().defined(), "trainable parameter has no gradient");
            openttd_rl::training::require_finite_tensor(parameter.value().grad(), "M08 test gradient");
            observed_nonzero_gradient = observed_nonzero_gradient || parameter.value().grad().abs().max().item<float>() > 0.0F;
        }
        check(observed_nonzero_gradient, "architecture produced no nonzero gradients");
        counts.push_back(parameter_count(model));
    }
    check(counts[0] != counts[1] && counts[0] != counts[2] && counts[1] != counts[2],
        "architecture parameter counts are not distinct");
}

void test_batch_invariance()
{
    for (const auto kind : {
             ArchitectureKind::StructuredMlp,
             ArchitectureKind::SpatialCnn,
             ArchitectureKind::CombinedCnnMlp,
         }) {
        MultiModalActorCritic model(kind, 5519);
        model->eval();
        const auto structured = structured_observations(3);
        const auto spatial = spatial_observations(3);
        torch::NoGradGuard guard;
        const auto batch = model->forward(structured, spatial);
        const auto single = model->forward(structured.index({1}).unsqueeze(0), spatial.index({1}).unsqueeze(0));
        check(torch::allclose(batch.first.index({1}), single.first.index({0}), 1e-6, 1e-6),
            "policy output depends on batch companions");
        check(torch::allclose(batch.second.index({1}), single.second.index({0}), 1e-6, 1e-6),
            "value output depends on batch companions");
    }
}

void test_invalid_inputs_are_rejected()
{
    MultiModalActorCritic structured_model(ArchitectureKind::StructuredMlp, 31);
    MultiModalActorCritic spatial_model(ArchitectureKind::SpatialCnn, 31);
    const auto structured = structured_observations(2);
    const auto spatial = spatial_observations(2);
    bool bad_structured_rejected = false;
    try {
        (void)structured_model->forward(torch::zeros({2, 255}, torch::kFloat32), spatial);
    } catch (const std::invalid_argument &) {
        bad_structured_rejected = true;
    }
    check(bad_structured_rejected, "wrong structured shape was accepted");

    bool bad_spatial_rejected = false;
    try {
        (void)spatial_model->forward(structured, torch::zeros({2, 31, 32, 32}, torch::kFloat32));
    } catch (const std::invalid_argument &) {
        bad_spatial_rejected = true;
    }
    check(bad_spatial_rejected, "wrong spatial shape was accepted");

    auto nonfinite = structured.clone();
    nonfinite.index_put_({0, 0}, std::numeric_limits<float>::quiet_NaN());
    bool nonfinite_rejected = false;
    try {
        (void)structured_model->forward(nonfinite, spatial);
    } catch (const std::runtime_error &) {
        nonfinite_rejected = true;
    }
    check(nonfinite_rejected, "nonfinite structured input was accepted");
}

openttd_rl::training::MultiModalRolloutBatch make_learning_rollout(
    openttd_rl::training::MultiModalPpoTrainer &trainer,
    std::int64_t samples)
{
    const auto structured = structured_observations(samples);
    const auto spatial = spatial_observations(samples);
    auto masks = torch::zeros({samples, openttd_rl::training::kActionCount}, torch::kBool);
    masks.index_put_({torch::indexing::Slice(), torch::indexing::Slice(0, 2)}, true);
    const auto behavior = trainer.act(structured, spatial, masks, true);
    const auto policy = openttd_rl::training::masked_categorical(behavior.logits, masks);
    const auto actions = torch::zeros({samples}, torch::kInt64);
    const auto old_log_probabilities = policy.log_probabilities.gather(1, actions.unsqueeze(1)).squeeze(1);
    return {
        structured,
        spatial,
        masks,
        actions,
        old_log_probabilities,
        behavior.values,
        torch::ones({samples}, torch::kFloat32),
        torch::zeros({samples}, torch::kFloat32),
    };
}

double target_log_probability(
    openttd_rl::training::MultiModalPpoTrainer &trainer,
    std::int64_t samples)
{
    const auto structured = structured_observations(samples);
    const auto spatial = spatial_observations(samples);
    auto masks = torch::zeros({samples, openttd_rl::training::kActionCount}, torch::kBool);
    masks.index_put_({torch::indexing::Slice(), torch::indexing::Slice(0, 2)}, true);
    const auto evaluation = trainer.act(structured, spatial, masks, true);
    const auto policy = openttd_rl::training::masked_categorical(evaluation.logits, masks);
    return policy.log_probabilities.index({torch::indexing::Slice(), 0}).mean().item<double>();
}

void test_all_architectures_train_end_to_end()
{
    constexpr std::int64_t samples = 32;
    for (const auto kind : {
             ArchitectureKind::StructuredMlp,
             ArchitectureKind::SpatialCnn,
             ArchitectureKind::CombinedCnnMlp,
         }) {
        openttd_rl::training::PpoConfig config;
        config.rollout_length = samples;
        config.environment_count = 1;
        config.minibatch_size = samples;
        config.optimization_epochs = 2;
        config.learning_rate = 0.003;
        config.value_coefficient = 0.0;
        config.entropy_coefficient = 0.0;
        openttd_rl::training::MultiModalPpoTrainer trainer(
            config,
            991,
            kind,
            torch::Device(torch::kCPU));
        const double before = target_log_probability(trainer, samples);
        for (int update = 0; update < 8; ++update) {
            const auto rollout = make_learning_rollout(trainer, samples);
            const auto metrics = trainer.update(rollout);
            check(metrics.update == static_cast<std::uint64_t>(update + 1), "multimodal update counter drifted");
            check(std::isfinite(metrics.policy_loss) && std::isfinite(metrics.gradient_norm),
                "multimodal update metric is nonfinite");
        }
        const double after = target_log_probability(trainer, samples);
        check(after > before + 0.05, "architecture did not improve its end-to-end PPO objective");
        check(trainer.counters().accepted_samples == 8U * static_cast<std::uint64_t>(samples),
            "multimodal trainer sample accounting drifted");
    }
}

} // namespace

int main()
{
    try {
        torch::set_num_threads(1);
        test_architecture_identity();
        test_structured_oracle_compatibility();
        test_all_architectures_forward_and_gradient();
        test_batch_invariance();
        test_invalid_inputs_are_rejected();
        test_all_architectures_train_end_to_end();
        std::cout << "M08_NATIVE_TESTS=PASS tests=6 architectures=3\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "M08_NATIVE_TESTS=FAIL " << error.what() << '\n';
        return 1;
    }
}
