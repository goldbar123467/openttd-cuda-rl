#include "openttd_rl/v2/m22_trainer.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <locale>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include <torch/cuda.h>
#include <torch/nn/utils/clip_grad.h>

namespace openttd_rl::v2 {

namespace {

using torch::indexing::Slice;

constexpr std::array<std::int64_t, kM22ProgramCount> kProgramMode = {
    0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 6, 6, 6, 6, 6,
};

void require_finite(const torch::Tensor &tensor, const char *name)
{
    if (!tensor.defined() || !torch::isfinite(tensor).all().item<bool>()) {
        throw std::runtime_error(std::string(name) + " is undefined or nonfinite");
    }
}

void require_cpu_vector(const torch::Tensor &tensor, torch::ScalarType type, std::int64_t size, const char *name)
{
    if (!tensor.defined() || !tensor.device().is_cpu() || tensor.scalar_type() != type ||
        tensor.dim() != 1 || tensor.size(0) != size) {
        throw std::invalid_argument(std::string(name) + " has the wrong CPU vector contract");
    }
    if (tensor.is_floating_point()) require_finite(tensor, name);
}

torch::Tensor indices_tensor(const std::vector<std::int64_t> &indices)
{
    return torch::from_blob(
               const_cast<std::int64_t *>(indices.data()),
               {static_cast<std::int64_t>(indices.size())},
               torch::TensorOptions().dtype(torch::kInt64))
        .clone();
}

std::string serialize_rng(const std::mt19937_64 &generator)
{
    std::ostringstream output;
    output.imbue(std::locale::classic());
    output << generator;
    if (!output) throw std::runtime_error("cannot serialize M22 RNG state");
    return output.str();
}

std::mt19937_64 parse_rng(const std::string &state)
{
    if (state.empty() || state.size() > 65536) throw std::invalid_argument("M22 RNG state is empty or oversized");
    std::istringstream input(state);
    input.imbue(std::locale::classic());
    std::mt19937_64 candidate;
    if (!(input >> candidate)) throw std::invalid_argument("M22 RNG state is malformed");
    char trailing = 0;
    if (input >> trailing || !input.eof()) throw std::invalid_argument("M22 RNG state is malformed");
    return candidate;
}

double explained_variance(const torch::Tensor &predictions, const torch::Tensor &targets)
{
    const auto prediction64 = predictions.to(torch::kFloat64);
    const auto target64 = targets.to(torch::kFloat64);
    const auto target_variance = torch::mean(torch::square(target64 - target64.mean())).item<double>();
    if (target_variance <= 1.0e-20) return 0.0;
    const auto residual = target64 - prediction64;
    const auto residual_variance = torch::mean(torch::square(residual - residual.mean())).item<double>();
    const double result = 1.0 - residual_variance / target_variance;
    if (!std::isfinite(result)) throw std::runtime_error("M22 explained variance is nonfinite");
    return result;
}

void require_finite_gradients(const GeneralistPolicy &model)
{
    std::int64_t defined = 0;
    for (const auto &parameter : model->named_parameters(true)) {
        if (parameter.value().grad().defined()) {
            require_finite(parameter.value().grad(), (std::string("M22 gradient ") + parameter.key()).c_str());
            ++defined;
        }
    }
    if (defined == 0) throw std::runtime_error("M22 update produced no gradients");
}

void move_optimizer_state(torch::optim::Adam &optimizer, const torch::Device &device)
{
    for (auto &item : optimizer.state()) {
        auto *state = dynamic_cast<torch::optim::AdamParamState *>(item.second.get());
        if (state == nullptr) throw std::invalid_argument("M22 optimizer contains a non-Adam state");
        if (state->exp_avg().defined()) state->exp_avg(state->exp_avg().to(device));
        if (state->exp_avg_sq().defined()) state->exp_avg_sq(state->exp_avg_sq().to(device));
        if (state->max_exp_avg_sq().defined()) state->max_exp_avg_sq(state->max_exp_avg_sq().to(device));
    }
}

} // namespace

std::int64_t M22CompactBatch::size() const
{
    return public_features.defined() && public_features.dim() > 0 ? public_features.size(0) : 0;
}

void M22CompactBatch::validate() const
{
    const auto batch = size();
    if (batch <= 0 || !public_features.device().is_cpu() || public_features.scalar_type() != torch::kFloat32 ||
        public_features.sizes() != torch::IntArrayRef({batch, kM22CompactFeatures})) {
        throw std::invalid_argument("M22 public features must be CPU float32 [batch,32]");
    }
    if (!program_mask.defined() || !program_mask.device().is_cpu() || program_mask.scalar_type() != torch::kBool ||
        program_mask.sizes() != torch::IntArrayRef({batch, kM22ProgramCount})) {
        throw std::invalid_argument("M22 program mask must be CPU bool [batch,17]");
    }
    if (!hidden_state.defined() || !hidden_state.device().is_cpu() || hidden_state.scalar_type() != torch::kFloat32 ||
        hidden_state.sizes() != torch::IntArrayRef({batch, kHiddenSize})) {
        throw std::invalid_argument("M22 hidden state must be CPU float32 [batch,256]");
    }
    if (!recurrent_reset.defined() || !recurrent_reset.device().is_cpu() || recurrent_reset.scalar_type() != torch::kBool ||
        recurrent_reset.sizes() != torch::IntArrayRef({batch})) {
        throw std::invalid_argument("M22 recurrent reset must be CPU bool [batch]");
    }
    require_finite(public_features, "M22 public features");
    require_finite(hidden_state, "M22 hidden state");
    if ((public_features < 0).any().item<bool>() || (public_features > 1).any().item<bool>()) {
        throw std::invalid_argument("M22 public features must remain in [0,1]");
    }
    if (!torch::equal(public_features.index({Slice(), Slice(0, 7)}).sum(1), torch::ones({batch}))) {
        throw std::invalid_argument("M22 public mode must be exactly one-hot");
    }
    if (!torch::equal(public_features.index({Slice(), Slice(7, 11)}).sum(1), torch::ones({batch}))) {
        throw std::invalid_argument("M22 public climate must be exactly one-hot");
    }
    if ((public_features.index({Slice(), Slice(11, 14)}) <= 0).any().item<bool>()) {
        throw std::invalid_argument("M22 normalized public map dimensions must be positive");
    }
    const auto capabilities = public_features.index({Slice(), Slice(14, 30)});
    if (!torch::equal(capabilities, torch::round(capabilities))) {
        throw std::invalid_argument("M22 public capabilities must be binary");
    }
    if (!program_mask.any(1).all().item<bool>() || !program_mask.index({Slice(), 0}).all().item<bool>()) {
        throw std::invalid_argument("M22 program mask must expose WAIT and at least one legal program");
    }
    const auto illegal_capability = torch::logical_and(
        program_mask.index({Slice(), Slice(1, kM22ProgramCount)}),
        torch::logical_not(capabilities.to(torch::kBool)));
    if (illegal_capability.any().item<bool>()) {
        throw std::invalid_argument("M22 legal active program lacks its public capability");
    }
}

M22CompactBatch M22CompactBatch::index_select(const torch::Tensor &indices) const
{
    validate();
    if (!indices.defined() || !indices.device().is_cpu() || indices.scalar_type() != torch::kInt64 || indices.dim() != 1) {
        throw std::invalid_argument("M22 compact indices must be a CPU int64 vector");
    }
    return {
        public_features.index_select(0, indices),
        program_mask.index_select(0, indices),
        hidden_state.index_select(0, indices),
        recurrent_reset.index_select(0, indices),
    };
}

GeneralistPolicyInput m22_encode_compact(const M22CompactBatch &compact, const torch::Device &device)
{
    compact.validate();
    const auto batch = compact.size();
    const auto floats = torch::TensorOptions().dtype(torch::kFloat32).device(device);
    const auto booleans = torch::TensorOptions().dtype(torch::kBool).device(device);
    const auto integers = torch::TensorOptions().dtype(torch::kInt64).device(device);
    const auto state = compact.public_features.to(device);
    auto structured = torch::zeros({batch, kStructuredFeatures}, floats);
    structured.index_put_({Slice(), Slice(0, kM22CompactFeatures)}, state);

    auto global = torch::zeros({batch, kSpatialChannels, kGlobalSpatialSide, kGlobalSpatialSide}, floats);
    auto regional = torch::zeros({batch, kSpatialChannels, kRegionalSpatialSide, kRegionalSpatialSide}, floats);
    auto local = torch::zeros({batch, kSpatialChannels, kLocalSpatialSide, kLocalSpatialSide}, floats);
    for (auto *spatial : {&global, &regional, &local}) {
        spatial->index_put_({Slice(), 0, Slice(), Slice()}, 1.0F);
        spatial->index_put_({Slice(), 1, Slice(), Slice()}, state.index({Slice(), 11}).view({batch, 1, 1}));
        spatial->index_put_({Slice(), 2, Slice(), Slice()}, state.index({Slice(), 12}).view({batch, 1, 1}));
    }

    auto make_entity = [&](std::int64_t capacity, std::int64_t features) {
        EntityTable table{
            torch::zeros({batch, capacity, features}, floats),
            torch::zeros({batch, capacity}, booleans),
        };
        const auto copied = std::min(features, kM22CompactFeatures);
        table.features.index_put_({Slice(), 0, Slice(0, copied)}, state.index({Slice(), Slice(0, copied)}));
        table.mask.index_put_({Slice(), 0}, true);
        return table;
    };
    auto companies = make_entity(kCompanyCapacity, kCompanyFeatures);
    auto towns = make_entity(kTownCapacity, kTownFeatures);
    auto industries = make_entity(kIndustryCapacity, kIndustryFeatures);
    auto stations = make_entity(kStationCapacity, kStationFeatures);
    auto vehicles = make_entity(kVehicleCapacity, kVehicleFeatures);

    auto graph_nodes = torch::zeros({batch, kGraphNodeCapacity, kGraphNodeFeatures}, floats);
    auto graph_node_mask = torch::zeros({batch, kGraphNodeCapacity}, booleans);
    graph_nodes.index_put_({Slice(), 0, Slice()}, state.index({Slice(), Slice(0, kGraphNodeFeatures)}));
    graph_node_mask.index_put_({Slice(), 0}, true);
    auto graph_edge_index = torch::zeros({batch, kGraphEdgeCapacity, 2}, integers);
    auto graph_edge_features = torch::zeros({batch, kGraphEdgeCapacity, kGraphEdgeFeatures}, floats);
    auto graph_edge_mask = torch::zeros({batch, kGraphEdgeCapacity}, booleans);
    graph_edge_features.index_put_({Slice(), 0, Slice()}, state.index({Slice(), Slice(14, 30)}));
    graph_edge_mask.index_put_({Slice(), 0}, true);

    auto candidate_features = torch::zeros({batch, kCandidateCapacity, kCandidateFeatures}, floats);
    candidate_features.index_put_({Slice(), 0, Slice()}, state);
    auto candidate_family = torch::zeros({batch, kCandidateCapacity}, integers);
    auto candidate_mask = torch::zeros({batch, kCandidateCapacity}, booleans);
    candidate_mask.index_put_({Slice(), 0}, true);
    auto family_mask = torch::zeros({batch, kFamilyCount}, booleans);
    family_mask.index_put_({Slice(), 0}, true);

    ScalablePolicyInput base{
        structured, global, regional, local, companies, towns, industries, stations, vehicles,
        graph_nodes, graph_node_mask, graph_edge_index, graph_edge_features, graph_edge_mask,
        candidate_features, candidate_family, candidate_mask, family_mask,
        compact.hidden_state.to(device), compact.recurrent_reset.to(device),
    };

    auto domain_tokens = torch::zeros({batch, kM22DomainTokenCapacity, kM22DomainTokenFeatures}, floats);
    domain_tokens.index_put_({Slice(), 0, Slice(0, kM22CompactFeatures)}, state);
    auto domain_kind = torch::zeros({batch, kM22DomainTokenCapacity}, integers);
    domain_kind.index_put_({Slice(), 0}, state.index({Slice(), Slice(0, 7)}).argmax(1));
    auto domain_mask = torch::zeros({batch, kM22DomainTokenCapacity}, booleans);
    domain_mask.index_put_({Slice(), 0}, true);

    auto program_features = torch::zeros({batch, kM22ProgramCount, kM22ProgramFeatures}, floats);
    for (std::int64_t program = 0; program < kM22ProgramCount; ++program) {
        program_features.index_put_({Slice(), program, program}, 1.0F);
        program_features.index_put_({Slice(), program, 17 + kProgramMode[static_cast<std::size_t>(program)]}, 1.0F);
        const auto capability = program == 0 ? torch::ones({batch}, floats) : state.index({Slice(), 13 + program});
        program_features.index_put_({Slice(), program, 24}, capability);
        program_features.index_put_({Slice(), program, 25}, state.index({Slice(), 11}));
        program_features.index_put_({Slice(), program, 26}, state.index({Slice(), 12}));
        program_features.index_put_({Slice(), program, 27}, state.index({Slice(), 7}));
        program_features.index_put_({Slice(), program, 28}, state.index({Slice(), 8}));
        program_features.index_put_({Slice(), program, 29}, state.index({Slice(), 9}));
        program_features.index_put_({Slice(), program, 30}, state.index({Slice(), 10}));
        program_features.index_put_({Slice(), program, 31}, state.index({Slice(), kProgramMode[static_cast<std::size_t>(program)]}));
    }
    return {
        base, domain_tokens, domain_kind, domain_mask, program_features, compact.program_mask.to(device),
    };
}

torch::Tensor m22_public_heuristic(const M22CompactBatch &compact)
{
    compact.validate();
    auto result = torch::zeros({compact.size()}, torch::TensorOptions().dtype(torch::kInt64));
    const auto capability_tensor = compact.public_features.index({Slice(), Slice(14, 30)}).contiguous();
    const auto capabilities = capability_tensor.accessor<float, 2>();
    const auto mask = compact.program_mask.accessor<bool, 2>();
    auto actions = result.accessor<std::int64_t, 1>();
    for (std::int64_t row = 0; row < compact.size(); ++row) {
        for (std::int64_t program = 1; program < kM22ProgramCount; ++program) {
            if (mask[row][program] && capabilities[row][program - 1] == 1.0F) {
                actions[row] = program;
                break;
            }
        }
    }
    return result;
}

std::int64_t M22RolloutBatch::size() const
{
    return compact.size();
}

void M22RolloutBatch::validate(const M22PpoConfig &config) const
{
    config.validate();
    compact.validate();
    const auto samples = config.rollout_steps * config.parallel_environments;
    if (size() != samples) throw std::invalid_argument("M22 rollout sample count disagrees with configuration");
    require_cpu_vector(actions, torch::kInt64, samples, "M22 rollout actions");
    require_cpu_vector(old_log_probabilities, torch::kFloat32, samples, "M22 old log probabilities");
    require_cpu_vector(old_values, torch::kFloat32, samples, "M22 old values");
    require_cpu_vector(advantages, torch::kFloat64, samples, "M22 advantages");
    require_cpu_vector(returns, torch::kFloat64, samples, "M22 returns");
    if ((actions < 0).any().item<bool>() || (actions >= kM22ProgramCount).any().item<bool>()) {
        throw std::invalid_argument("M22 rollout action exceeds program inventory");
    }
    if (!compact.program_mask.gather(1, actions.unsqueeze(1)).all().item<bool>()) {
        throw std::invalid_argument("M22 rollout contains an illegal action");
    }
    if (config.rollout_steps % kM22SequenceLength != 0 || config.minibatch_size % kM22SequenceLength != 0) {
        throw std::invalid_argument("M22 recurrent rollout/minibatch boundaries must divide into exact length-eight sequences");
    }
}

std::uint64_t m22_stream_seed(std::uint64_t run_seed, std::uint64_t stream_index) noexcept
{
    std::uint64_t value = run_seed + UINT64_C(0x9e3779b97f4a7c15) * (stream_index + 1U);
    value = (value ^ (value >> 30U)) * UINT64_C(0xbf58476d1ce4e5b9);
    value = (value ^ (value >> 27U)) * UINT64_C(0x94d049bb133111eb);
    return value ^ (value >> 31U);
}

M22Trainer::M22Trainer(
    M22PpoConfig config,
    std::uint64_t run_seed,
    GeneralistArchitecture architecture,
    torch::Device device) :
    config_(config),
    run_seed_(run_seed),
    architecture_(architecture),
    device_(std::move(device)),
    model_(m22_stream_seed(run_seed, 0), architecture),
    action_rng_(m22_stream_seed(run_seed, 1)),
    minibatch_rng_(m22_stream_seed(run_seed, 2)),
    environment_rng_(m22_stream_seed(run_seed, 3)),
    curriculum_rng_(m22_stream_seed(run_seed, 4))
{
    config_.validate();
    at::globalContext().setDeterministicAlgorithms(true, false);
    at::globalContext().setAllowTF32CuBLAS(false);
    at::globalContext().setAllowTF32CuDNN(false);
    if (architecture_ != GeneralistArchitecture::Monolithic && architecture_ != GeneralistArchitecture::SpecialistRouter) {
        throw std::invalid_argument("M22 trainer requires a learned architecture");
    }
    if (device_.is_cuda()) {
        if (!torch::cuda::is_available()) throw std::runtime_error("cuda-unavailable: M22 trainer requested CUDA");
        if (!device_.has_index() || device_.index() != 0) throw std::invalid_argument("cuda-unsupported: M22 accepts only cuda:0");
    } else if (!device_.is_cpu()) {
        throw std::invalid_argument("device-unsupported: M22 accepts only cpu or cuda:0");
    }
    model_->to(device_);
    optimizer_ = std::make_unique<torch::optim::Adam>(
        model_->parameters(),
        torch::optim::AdamOptions(config_.learning_rate).eps(config_.adam_epsilon));
}

M22ActionBatch M22Trainer::act(const M22CompactBatch &compact, bool deterministic)
{
    compact.validate();
    const bool was_training = model_->is_training();
    model_->eval();
    torch::NoGradGuard guard;
    const auto output = model_->forward(m22_encode_compact(compact, device_));
    const auto policy = m22_masked_categorical(output.program_logits, compact.program_mask.to(device_));
    const auto probabilities = policy.probabilities.to(torch::kCPU).contiguous();
    const auto probability_rows = probabilities.accessor<float, 2>();
    auto actions = torch::zeros({compact.size()}, torch::TensorOptions().dtype(torch::kInt64));
    auto selected = actions.accessor<std::int64_t, 1>();
    const auto greedy = policy.log_probabilities.argmax(1).to(torch::kCPU);
    const auto greedy_rows = greedy.accessor<std::int64_t, 1>();
    for (std::int64_t row = 0; row < compact.size(); ++row) {
        if (deterministic) {
            selected[row] = greedy_rows[row];
            continue;
        }
        const double draw = std::generate_canonical<double, std::numeric_limits<double>::digits>(action_rng_);
        double cumulative = 0.0;
        selected[row] = greedy_rows[row];
        for (std::int64_t program = 0; program < kM22ProgramCount; ++program) {
            cumulative += static_cast<double>(probability_rows[row][program]);
            if (draw < cumulative) {
                selected[row] = program;
                break;
            }
        }
    }
    const auto device_actions = actions.to(device_);
    const auto selected_logs = policy.log_probabilities.gather(1, device_actions.unsqueeze(1)).squeeze(1);
    require_finite(selected_logs, "M22 selected log probabilities");
    if (was_training) model_->train();
    return {
        actions,
        selected_logs.to(torch::kCPU).contiguous(),
        output.program_value.to(torch::kCPU).contiguous(),
        output.program_logits.to(torch::kCPU).contiguous(),
        output.next_hidden.to(torch::kCPU).contiguous(),
    };
}

M22UpdateMetrics M22Trainer::update(const M22RolloutBatch &rollout)
{
    rollout.validate(config_);
    model_->train();
    const auto sequence_count = (config_.rollout_steps / kM22SequenceLength) * config_.parallel_environments;
    const auto sequences_per_minibatch = config_.minibatch_size / kM22SequenceLength;
    M22UpdateMetrics metrics;
    std::uint64_t minibatches = 0;
    for (std::int64_t epoch = 0; epoch < config_.epochs; ++epoch) {
        const auto batches = m22_minibatch_indices(sequence_count, sequences_per_minibatch, minibatch_rng_);
        for (const auto &sequences : batches) {
            std::vector<std::int64_t> ordered;
            ordered.reserve(static_cast<std::size_t>(config_.minibatch_size));
            std::vector<torch::Tensor> log_probabilities;
            std::vector<torch::Tensor> values;
            std::vector<torch::Tensor> entropies;
            torch::Tensor hidden;
            for (std::int64_t time = 0; time < kM22SequenceLength; ++time) {
                std::vector<std::int64_t> time_indices;
                time_indices.reserve(sequences.size());
                for (const auto sequence : sequences) {
                    const auto block = sequence / config_.parallel_environments;
                    const auto environment = sequence % config_.parallel_environments;
                    const auto index = (block * kM22SequenceLength + time) * config_.parallel_environments + environment;
                    time_indices.push_back(index);
                    ordered.push_back(index);
                }
                const auto indices = indices_tensor(time_indices);
                auto compact = rollout.compact.index_select(indices);
                auto input = m22_encode_compact(compact, device_);
                if (hidden.defined()) input.base.hidden_state = hidden;
                const auto output = model_->forward(input);
                const auto policy = m22_masked_categorical(output.program_logits, compact.program_mask.to(device_));
                const auto actions = rollout.actions.index_select(0, indices).to(device_);
                log_probabilities.push_back(policy.log_probabilities.gather(1, actions.unsqueeze(1)).squeeze(1));
                values.push_back(output.program_value);
                entropies.push_back(policy.entropy);
                hidden = output.next_hidden;
            }
            const auto indices = indices_tensor(ordered);
            const auto new_logs = torch::cat(log_probabilities, 0);
            const auto new_values = torch::cat(values, 0);
            const auto entropy = torch::cat(entropies, 0);
            const auto old_logs = rollout.old_log_probabilities.index_select(0, indices).to(device_);
            const auto old_values = rollout.old_values.index_select(0, indices).to(device_);
            const auto advantages = rollout.advantages.index_select(0, indices).to(device_, torch::kFloat32);
            const auto returns = rollout.returns.index_select(0, indices).to(device_, torch::kFloat32);
            const auto loss = m22_ppo_loss(
                new_logs, old_logs, advantages, new_values, old_values, returns, entropy, config_);
            optimizer_->zero_grad();
            loss.total.backward();
            require_finite_gradients(model_);
            const double gradient_norm = torch::nn::utils::clip_grad_norm_(
                model_->parameters(), config_.maximum_gradient_norm, 2.0, true);
            if (!std::isfinite(gradient_norm)) throw std::runtime_error("M22 global gradient norm is nonfinite");
            require_finite_gradients(model_);
            optimizer_->step();
            require_finite_generalist(model_, "M22 trainer update");
            metrics.policy_loss += loss.policy.item<double>();
            metrics.value_loss += loss.value.item<double>();
            metrics.entropy += loss.entropy.item<double>();
            metrics.approximate_kl += loss.approximate_kl.item<double>();
            metrics.clip_fraction += loss.clip_fraction.item<double>();
            metrics.gradient_norm += gradient_norm;
            ++minibatches;
        }
    }
    if (minibatches == 0) throw std::logic_error("M22 PPO update executed no recurrent minibatches");
    const auto denominator = static_cast<double>(minibatches);
    metrics.policy_loss /= denominator;
    metrics.value_loss /= denominator;
    metrics.entropy /= denominator;
    metrics.approximate_kl /= denominator;
    metrics.clip_fraction /= denominator;
    metrics.gradient_norm /= denominator;
    metrics.explained_variance = explained_variance(rollout.old_values, rollout.returns);
    ++counters_.completed_updates;
    ++counters_.completed_rollouts;
    counters_.accepted_transitions += static_cast<std::uint64_t>(rollout.size());
    metrics.update = counters_.completed_updates;
    metrics.transitions = counters_.accepted_transitions;
    return metrics;
}

M22RuntimeState M22Trainer::runtime_state() const
{
    return {
        run_seed_, architecture_, counters_, serialize_rng(action_rng_), serialize_rng(minibatch_rng_),
        serialize_rng(environment_rng_), serialize_rng(curriculum_rng_),
    };
}

void M22Trainer::restore_runtime_state(const M22RuntimeState &state)
{
    if (state.run_seed != run_seed_ || state.architecture != architecture_) {
        throw std::invalid_argument("M22 runtime state trainer identity mismatch");
    }
    auto action = parse_rng(state.action_rng);
    auto minibatch = parse_rng(state.minibatch_rng);
    auto environment = parse_rng(state.environment_rng);
    auto curriculum = parse_rng(state.curriculum_rng);
    action_rng_ = action;
    minibatch_rng_ = minibatch;
    environment_rng_ = environment;
    curriculum_rng_ = curriculum;
    counters_ = state.counters;
}

void M22Trainer::to(const torch::Device &device)
{
    if (device.is_cuda()) {
        if (!torch::cuda::is_available()) throw std::runtime_error("cuda-unavailable: M22 trainer requested CUDA");
        if (!device.has_index() || device.index() != 0) throw std::invalid_argument("cuda-unsupported: M22 accepts only cuda:0");
    } else if (!device.is_cpu()) {
        throw std::invalid_argument("device-unsupported: M22 accepts only cpu or cuda:0");
    }
    model_->to(device);
    move_optimizer_state(*optimizer_, device);
    device_ = device;
}

} // namespace openttd_rl::v2
