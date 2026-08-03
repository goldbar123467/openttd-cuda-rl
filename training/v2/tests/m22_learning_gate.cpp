#include "openttd_rl/v2/generalist_policy.h"
#include "openttd_rl/v2/m22_ppo.h"

#include <cmath>
#include <cstdint>
#include <iostream>
#include <random>
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

openttd_rl::v2::GeneralistPolicyInput make_input(
    const torch::Device &device,
    std::int64_t batch,
    std::int64_t capability,
    bool recurrent_reset,
    bool nonzero_hidden)
{
    using namespace openttd_rl::v2;
    const auto floats = torch::TensorOptions().dtype(torch::kFloat32).device(device);
    const auto booleans = torch::TensorOptions().dtype(torch::kBool).device(device);
    const auto integers = torch::TensorOptions().dtype(torch::kInt64).device(device);
    auto structured = torch::zeros({batch, kStructuredFeatures}, floats);
    structured.index_put_({Slice(), 0}, 64.0F / 4096.0F);
    structured.index_put_({Slice(), 1}, 64.0F / 4096.0F);
    structured.index_put_({Slice(), 2}, 4096.0F / 1048576.0F);
    structured.index_put_({Slice(), 7}, 1.0F / 15.0F);
    structured.index_put_({Slice(), 12}, 1.0F);
    auto global = torch::zeros({batch, kSpatialChannels, kGlobalSpatialSide, kGlobalSpatialSide}, floats);
    auto regional = torch::zeros({batch, kSpatialChannels, kRegionalSpatialSide, kRegionalSpatialSide}, floats);
    auto local = torch::zeros({batch, kSpatialChannels, kLocalSpatialSide, kLocalSpatialSide}, floats);
    global.index_put_({Slice(), 0, Slice(), Slice()}, 1.0F);
    regional.index_put_({Slice(), 0, Slice(), Slice()}, 1.0F);
    local.index_put_({Slice(), 0, Slice(), Slice()}, 1.0F);
    EntityTable companies{torch::zeros({batch, kCompanyCapacity, kCompanyFeatures}, floats), torch::zeros({batch, kCompanyCapacity}, booleans)};
    EntityTable towns{torch::zeros({batch, kTownCapacity, kTownFeatures}, floats), torch::zeros({batch, kTownCapacity}, booleans)};
    EntityTable industries{torch::zeros({batch, kIndustryCapacity, kIndustryFeatures}, floats), torch::zeros({batch, kIndustryCapacity}, booleans)};
    EntityTable stations{torch::zeros({batch, kStationCapacity, kStationFeatures}, floats), torch::zeros({batch, kStationCapacity}, booleans)};
    EntityTable vehicles{torch::zeros({batch, kVehicleCapacity, kVehicleFeatures}, floats), torch::zeros({batch, kVehicleCapacity}, booleans)};
    companies.mask.index_put_({Slice(), 0}, true);
    towns.mask.index_put_({Slice(), 0}, true);
    auto candidate_mask = torch::zeros({batch, kCandidateCapacity}, booleans);
    candidate_mask.index_put_({Slice(), 0}, true);
    auto family_mask = torch::zeros({batch, kFamilyCount}, booleans);
    family_mask.index_put_({Slice(), 0}, true);
    auto hidden = nonzero_hidden ? torch::full({batch, kHiddenSize}, 0.25F, floats) : torch::zeros({batch, kHiddenSize}, floats);
    ScalablePolicyInput base{
        structured,
        global,
        regional,
        local,
        companies,
        towns,
        industries,
        stations,
        vehicles,
        torch::zeros({batch, kGraphNodeCapacity, kGraphNodeFeatures}, floats),
        torch::zeros({batch, kGraphNodeCapacity}, booleans),
        torch::zeros({batch, kGraphEdgeCapacity, 2}, integers),
        torch::zeros({batch, kGraphEdgeCapacity, kGraphEdgeFeatures}, floats),
        torch::zeros({batch, kGraphEdgeCapacity}, booleans),
        torch::zeros({batch, kCandidateCapacity, kCandidateFeatures}, floats),
        torch::zeros({batch, kCandidateCapacity}, integers),
        candidate_mask,
        family_mask,
        hidden,
        torch::full({batch}, recurrent_reset, booleans),
    };
    auto domain_tokens = torch::zeros({batch, kM22DomainTokenCapacity, kM22DomainTokenFeatures}, floats);
    domain_tokens.index_put_({Slice(), 0, capability}, 1.0F);
    domain_tokens.index_put_({Slice(), 0, 24}, 0.75F);
    auto domain_kind = torch::zeros({batch, kM22DomainTokenCapacity}, integers);
    domain_kind.index_put_({Slice(), 0}, capability % kM22DomainCount);
    auto domain_mask = torch::zeros({batch, kM22DomainTokenCapacity}, booleans);
    domain_mask.index_put_({Slice(), 0}, true);
    auto program_features = torch::zeros({batch, kM22ProgramCount, kM22ProgramFeatures}, floats);
    for (std::int64_t program = 0; program < kM22ProgramCount; ++program) {
        program_features.index_put_({Slice(), program, program}, 1.0F);
        const std::int64_t mode = program <= 2 ? 0 : program <= 4 ? 1 : program <= 6 ? 2 :
            program <= 8 ? 3 : program <= 10 ? 4 : program == 11 ? 5 : 6;
        program_features.index_put_({Slice(), program, 17 + mode}, 1.0F);
        program_features.index_put_({Slice(), program, 24}, static_cast<float>(program) / 16.0F);
    }
    auto program_mask = torch::ones({batch, kM22ProgramCount}, booleans);
    return {base, domain_tokens, domain_kind, domain_mask, program_features, program_mask};
}

double maximum_parameter_difference(
    const openttd_rl::v2::GeneralistPolicy &left,
    const openttd_rl::v2::GeneralistPolicy &right)
{
    const auto left_parameters = left->named_parameters(true);
    const auto right_parameters = right->named_parameters(true);
    require(left_parameters.size() == right_parameters.size(), "parameter inventories differ");
    double maximum = 0.0;
    for (const auto &item : left_parameters) {
        require(right_parameters.contains(item.key()), "parameter name is missing");
        const auto difference = torch::max(torch::abs(
            item.value().detach().to(torch::kCPU) - right_parameters[item.key()].detach().to(torch::kCPU))).item<double>();
        maximum = std::max(maximum, difference);
    }
    return maximum;
}

std::int64_t parameter_count(const openttd_rl::v2::GeneralistPolicy &model)
{
    std::int64_t result = 0;
    for (const auto &parameter : model->parameters(true)) result += parameter.numel();
    return result;
}

void test_gae_and_minibatches()
{
    using namespace openttd_rl::v2;
    const auto rewards = torch::tensor({{1.0F}, {1.0F}}, torch::kFloat32);
    const auto zeros = torch::zeros_like(rewards);
    const auto ones = torch::ones_like(rewards);
    auto continuation = torch::tensor({{1.0F}, {0.0F}}, torch::kFloat32);
    const auto gae = m22_compute_gae(rewards, zeros, zeros, ones, continuation, 0.99, 0.95);
    require(std::abs(gae.advantages.index({0, 0}).item<double>() - 1.9405) < 1.0e-12, "M22 GAE oracle mismatch");
    require(std::abs(gae.advantages.index({1, 0}).item<double>() - 1.0) < 1.0e-12, "M22 terminal GAE mismatch");
    auto normalized = m22_normalize_advantages(gae.advantages.flatten());
    require(torch::isfinite(normalized).all().item<bool>(), "normalized advantages are nonfinite");
    std::mt19937_64 left(123), right(123);
    require(m22_minibatch_indices(128, 64, left) == m22_minibatch_indices(128, 64, right),
            "M22 minibatch shuffle is not seeded-exact");
}

void test_invalid_domain_kind(const torch::Device &device)
{
    using namespace openttd_rl::v2;
    auto model = GeneralistPolicy(UINT64_C(22001), GeneralistArchitecture::Monolithic);
    model->to(device);
    auto input = make_input(device, 1, 1, true, false);
    input.domain_token_kind.index_put_({0, 1}, kM22DomainCount);
    try {
        static_cast<void>(model->forward(input));
    } catch (const std::invalid_argument &) {
        return;
    }
    throw std::runtime_error("out-of-range M22 domain kind was accepted");
}

void test_cpu_cuda_parity()
{
    using namespace openttd_rl::v2;
    auto cpu = GeneralistPolicy(UINT64_C(22002), GeneralistArchitecture::Monolithic);
    auto cuda = GeneralistPolicy(UINT64_C(22002), GeneralistArchitecture::Monolithic);
    cuda->to(torch::Device(torch::kCUDA, 0));
    torch::NoGradGuard guard;
    const auto cpu_output = cpu->forward(make_input(torch::kCPU, 1, 7, true, false));
    const auto cuda_output = cuda->forward(make_input(torch::Device(torch::kCUDA, 0), 1, 7, true, false));
    const auto logit_error = torch::max(torch::abs(cpu_output.program_logits - cuda_output.program_logits.to(torch::kCPU))).item<double>();
    const auto value_error = torch::max(torch::abs(cpu_output.program_value - cuda_output.program_value.to(torch::kCPU))).item<double>();
    const auto hidden_error = torch::max(torch::abs(cpu_output.next_hidden - cuda_output.next_hidden.to(torch::kCPU))).item<double>();
    require(logit_error <= 1.0e-4 && value_error <= 1.0e-4 && hidden_error <= 1.0e-4,
            "M22 CPU/CUDA forward parity exceeded the contract");
}

void run(const torch::Device &device)
{
    using namespace openttd_rl::v2;
    M22PpoConfig config;
    config.validate();
    test_gae_and_minibatches();
    test_invalid_domain_kind(device);
    auto model = GeneralistPolicy(UINT64_C(1910917137), GeneralistArchitecture::Monolithic);
    auto specialist = GeneralistPolicy(UINT64_C(1910917137), GeneralistArchitecture::SpecialistRouter);
    model->to(device);
    specialist->to(device);
    auto input = make_input(device, 2, 3, false, true);
    auto output = model->forward(input);
    require(output.program_logits.sizes() == torch::IntArrayRef({2, kM22ProgramCount}), "program logits shape drifted");
    require(output.program_value.sizes() == torch::IntArrayRef({2}), "program value shape drifted");
    require(output.next_hidden.sizes() == torch::IntArrayRef({2, kHiddenSize}), "next hidden shape drifted");
    require(torch::isfinite(output.program_logits).all().item<bool>(), "program logits are nonfinite");
    const auto specialist_output = specialist->forward(input);
    require(!torch::equal(output.program_logits, specialist_output.program_logits), "specialist router collapsed to monolithic logits");
    require(parameter_count(model) == kM22ParameterCount && parameter_count(specialist) == kM22ParameterCount,
            "M22 learned architecture parameter count drifted");

    auto masked_input = make_input(device, 1, 4, true, false);
    masked_input.program_mask.index_put_({0, 16}, false);
    const auto masked_output = model->forward(masked_input);
    require(masked_output.program_logits.index({0, 16}).item<float>() == -1.0e9F, "illegal program logit is not frozen");

    auto reset_nonzero = make_input(device, 1, 5, true, true);
    auto reset_zero = make_input(device, 1, 5, true, false);
    {
        torch::NoGradGuard no_grad;
        const auto reset_a = model->forward(reset_nonzero);
        const auto reset_b = model->forward(reset_zero);
        require(torch::equal(reset_a.next_hidden, reset_b.next_hidden), "explicit recurrent reset retained prior hidden state");
    }

    input = make_input(device, 2, 3, false, false);
    output = model->forward(input);
    const auto distribution = m22_masked_categorical(output.program_logits, input.program_mask);
    try {
        static_cast<void>(m22_masked_categorical(output.program_logits, input.program_mask.to(torch::kFloat32)));
        throw std::runtime_error("non-boolean M22 program mask was accepted");
    } catch (const std::invalid_argument &) {
    }
    const auto actions = torch::full({2}, 3, torch::TensorOptions().dtype(torch::kInt64).device(device));
    const auto selected = distribution.log_probabilities.gather(1, actions.unsqueeze(1)).squeeze(1);
    const auto old_logs = selected.detach();
    const auto old_values = output.program_value.detach();
    const auto advantages = torch::tensor({1.0F, -0.5F}, torch::TensorOptions().dtype(torch::kFloat32).device(device));
    const auto returns = old_values + torch::tensor({1.0F, -0.25F}, torch::TensorOptions().dtype(torch::kFloat32).device(device));
    const auto loss = m22_ppo_loss(selected, old_logs, advantages, output.program_value, old_values, returns,
                                   distribution.entropy, config);
    auto optimizer = torch::optim::Adam(model->parameters(), torch::optim::AdamOptions(config.learning_rate).eps(config.adam_epsilon));
    optimizer.zero_grad();
    loss.total.backward();
    double gradient_sum = 0.0;
    for (const auto &parameter : model->parameters(true)) {
        if (parameter.grad().defined()) {
            require(torch::isfinite(parameter.grad()).all().item<bool>(), "M22 gradient is nonfinite");
            gradient_sum += torch::sum(torch::abs(parameter.grad())).item<double>();
        }
    }
    require(gradient_sum > 0.0, "M22 PPO produced no model gradient");
    torch::nn::utils::clip_grad_norm_(model->parameters(), config.maximum_gradient_norm);
    auto before = GeneralistPolicy(UINT64_C(1910917137), GeneralistArchitecture::Monolithic);
    before->to(device);
    optimizer.step();
    require(maximum_parameter_difference(model, before) > 0.0, "M22 Adam step did not mutate parameters");
    require_finite_generalist(model, "M22 optimizer step");
    require(parameter_count(model) == kM22ParameterCount, "M22 policy parameter count drifted after update");
    if (device.is_cuda()) test_cpu_cuda_parity();
    std::cout << "M22_LEARNING_GATE=PASS device=" << device.str()
              << " parameters=" << parameter_count(model)
              << " gradient_sum=" << gradient_sum << '\n';
}

} // namespace

int main(int argc, char **argv)
{
    try {
        if (argc != 3 || std::string(argv[1]) != "--device") {
            throw std::invalid_argument("usage: m22_learning_gate --device cpu|cuda:0");
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
        std::cerr << "M22_LEARNING_GATE=FAIL " << error.what_without_backtrace() << '\n';
        return 1;
    } catch (const std::exception &error) {
        std::cerr << "M22_LEARNING_GATE=FAIL " << error.what() << '\n';
        return 1;
    }
}
