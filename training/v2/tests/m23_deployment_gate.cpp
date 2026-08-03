#include "openttd_rl/v2/m22_evaluation.h"
#include "openttd_rl/v2/m23_deployment.h"

#include <array>
#include <cstdint>
#include <iostream>
#include <limits>
#include <stdexcept>

namespace {

void require(bool condition, const char *message)
{
    if (!condition) throw std::runtime_error(message);
}

void require_equal(const torch::Tensor &left, const torch::Tensor &right, const char *message)
{
    require(torch::equal(left, right), message);
}

void run()
{
    using namespace openttd_rl::v2;
    const M22FinalPublicState state{
        "service", "road", "temperate", 128, 128, "PASS", "not-applicable", "passenger-service", "G15",
    };
    const auto old_batch = encode_m22_final_public_state(state);
    const M23DeploymentBatch new_batch{
        old_batch.public_features,
        old_batch.program_mask,
        old_batch.hidden_state,
        old_batch.recurrent_reset,
    };
    const auto old_input = m22_evaluation_input(old_batch, torch::kCPU);
    const auto new_input = m23_deployment_input(new_batch, torch::kCPU);
    require_equal(old_input.base.structured, new_input.base.structured, "M23 structured adapter drifted from M22");
    require_equal(old_input.base.global_spatial, new_input.base.global_spatial, "M23 global adapter drifted from M22");
    require_equal(old_input.base.regional_spatial, new_input.base.regional_spatial, "M23 regional adapter drifted from M22");
    require_equal(old_input.base.local_spatial, new_input.base.local_spatial, "M23 local adapter drifted from M22");
    require_equal(old_input.base.companies.features, new_input.base.companies.features, "M23 company adapter drifted");
    require_equal(old_input.base.towns.features, new_input.base.towns.features, "M23 town adapter drifted");
    require_equal(old_input.base.industries.features, new_input.base.industries.features, "M23 industry adapter drifted");
    require_equal(old_input.base.stations.features, new_input.base.stations.features, "M23 station adapter drifted");
    require_equal(old_input.base.vehicles.features, new_input.base.vehicles.features, "M23 vehicle adapter drifted");
    require_equal(old_input.base.graph_nodes, new_input.base.graph_nodes, "M23 graph node adapter drifted");
    require_equal(old_input.base.graph_edge_features, new_input.base.graph_edge_features, "M23 graph edge adapter drifted");
    require_equal(old_input.base.candidate_features, new_input.base.candidate_features, "M23 candidate adapter drifted");
    require_equal(old_input.domain_tokens, new_input.domain_tokens, "M23 domain adapter drifted from M22");
    require_equal(old_input.program_features, new_input.program_features, "M23 program adapter drifted from M22");
    require_equal(old_input.program_mask, new_input.program_mask, "M23 mask adapter drifted from M22");

    at::globalContext().setDeterministicAlgorithms(true, false);
    torch::manual_seed(230023);
    GeneralistPolicy model(UINT64_C(230023), GeneralistArchitecture::Monolithic);
    model->eval();
    torch::NoGradGuard guard;
    const auto old_output = model->forward(old_input);
    const auto new_output = model->forward(new_input);
    require_equal(old_output.program_logits, new_output.program_logits, "M23 batch-one logits drifted from M22");
    require_equal(old_output.program_value, new_output.program_value, "M23 batch-one value drifted from M22");
    require_equal(old_output.next_hidden, new_output.next_hidden, "M23 batch-one hidden state drifted from M22");

    for (const auto batch_size : std::array<std::int64_t, 3>{1, 8, 32}) {
        auto features = torch::zeros({batch_size, kM23PublicFeatureCount}, torch::kFloat32);
        features.index_put_({torch::indexing::Slice(), 0}, 1.0F);
        features.index_put_({torch::indexing::Slice(), 7}, 1.0F);
        features.index_put_({torch::indexing::Slice(), 11}, 1.0F / 32.0F);
        features.index_put_({torch::indexing::Slice(), 12}, 1.0F / 32.0F);
        features.index_put_({torch::indexing::Slice(), 13}, 1.0F / 64.0F);
        features.index_put_({torch::indexing::Slice(), 14}, 1.0F);
        auto mask = torch::zeros({batch_size, kM22ProgramCount}, torch::kBool);
        mask.index_put_({torch::indexing::Slice(), 0}, true);
        mask.index_put_({torch::indexing::Slice(), 1}, true);
        const auto hidden = torch::randn({batch_size, kHiddenSize}, torch::kFloat32) * 0.25F;
        const auto reset = torch::ones({batch_size}, torch::kBool);
        const M23DeploymentBatch batch{features, mask, hidden, reset};
        const auto output = model->forward(m23_deployment_input(batch, torch::kCPU));
        require(output.program_logits.sizes() == torch::IntArrayRef({batch_size, kM22ProgramCount}) &&
                output.program_value.sizes() == torch::IntArrayRef({batch_size}) &&
                output.next_hidden.sizes() == torch::IntArrayRef({batch_size, kHiddenSize}) &&
                torch::isfinite(output.program_logits).all().item<bool>() &&
                torch::isfinite(output.program_value).all().item<bool>() &&
                torch::isfinite(output.next_hidden).all().item<bool>(),
                "M23 dynamic-batch output contract failed");
        const auto zero_hidden = torch::zeros_like(hidden);
        const M23DeploymentBatch zero_batch{features, mask, zero_hidden, reset};
        const auto zero_output = model->forward(m23_deployment_input(zero_batch, torch::kCPU));
        require_equal(output.next_hidden, zero_output.next_hidden, "M23 recurrent reset did not zero carried hidden state");
    }

    auto invalid = new_batch;
    invalid.program_mask = torch::zeros_like(invalid.program_mask);
    try {
        validate_m23_deployment_batch(invalid);
        require(false, "M23 accepted an all-illegal program mask");
    } catch (const std::invalid_argument &) {
    }
    invalid = new_batch;
    invalid.public_features.index_put_({0, 0}, std::numeric_limits<float>::infinity());
    try {
        validate_m23_deployment_batch(invalid);
        require(false, "M23 accepted nonfinite public features");
    } catch (const std::invalid_argument &) {
    }
    invalid = new_batch;
    invalid.public_features = torch::zeros({33, kM23PublicFeatureCount}, torch::kFloat32);
    try {
        validate_m23_deployment_batch(invalid);
        require(false, "M23 accepted batch 33");
    } catch (const std::invalid_argument &) {
    }
    std::cout << "M23_DEPLOYMENT_GATE=PASS batch=1,8,32 m22_adapter=exact reset=exact invalid=3\n";
}

} // namespace

int main()
{
    try {
        run();
        return 0;
    } catch (const c10::Error &error) {
        std::cerr << "M23_DEPLOYMENT_GATE=FAIL " << error.what_without_backtrace() << '\n';
        return 1;
    } catch (const std::exception &error) {
        std::cerr << "M23_DEPLOYMENT_GATE=FAIL " << error.what() << '\n';
        return 1;
    }
}
