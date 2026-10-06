#include "openttd_rl/training/multimodal_trainer.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <string>
#include <vector>

#include <torch/cuda.h>
#include <torch/nn/utils/clip_grad.h>
#ifdef RL_DEV_FUSED_POLICY
#include "fused_policy.h"
#endif

namespace openttd_rl::training {

namespace {

class EvaluationModeGuard {
public:
    explicit EvaluationModeGuard(MultiModalActorCritic &model)
        : model_(model), was_training_(model->is_training()) { model_->eval(); }
    ~EvaluationModeGuard() { model_->train(was_training_); }
    EvaluationModeGuard(const EvaluationModeGuard &) = delete;
    EvaluationModeGuard &operator=(const EvaluationModeGuard &) = delete;
private:
    MultiModalActorCritic &model_;
    bool was_training_;
};

torch::Tensor indices_tensor(const std::vector<std::int64_t> &indices)
{
    return torch::from_blob(
               const_cast<std::int64_t *>(indices.data()),
               {static_cast<std::int64_t>(indices.size())},
               torch::TensorOptions().dtype(torch::kInt64))
        .clone();
}

void require_cpu_tensor(const torch::Tensor &tensor, const char *name)
{
    if (!tensor.defined() || tensor.device().is_cuda()) {
        throw std::invalid_argument(std::string(name) + " must be a defined CPU tensor");
    }
}

void require_finite_gradients(const MultiModalActorCritic &model)
{
    for (const auto &parameter : model->named_parameters(true)) {
        if (!parameter.value().grad().defined()) throw std::runtime_error("missing gradient: " + parameter.key());
        require_finite_tensor(parameter.value().grad(), ("gradient " + parameter.key()).c_str());
    }
}

} // namespace

std::int64_t MultiModalRolloutBatch::size() const
{
    return structured.defined() && structured.dim() > 0 ? structured.size(0) : 0;
}

void MultiModalRolloutBatch::validate() const
{
    RolloutBatch structured_rollout{
        structured,
        legal_masks,
        actions,
        old_log_probabilities,
        old_values,
        advantages,
        returns,
    };
    structured_rollout.validate(kStructuredFeatures, kActionCount);
    require_cpu_tensor(spatial, "spatial rollout");
    if (spatial.scalar_type() != torch::kFloat32 || spatial.dim() != 4 || spatial.size(0) != size() ||
        spatial.size(1) != kSpatialChannels || spatial.size(2) != kSpatialHeight || spatial.size(3) != kSpatialWidth) {
        throw std::invalid_argument("spatial rollout must be CPU float32 [samples,32,32,32]");
    }
    require_finite_tensor(spatial, "spatial rollout");
    if ((spatial < 0).any().item<bool>() || (spatial > 1).any().item<bool>()) {
        throw std::invalid_argument("spatial rollout values must remain in the frozen [0,1] range");
    }
}

MultiModalPpoTrainer::MultiModalPpoTrainer(
    PpoConfig config,
    std::uint64_t run_seed,
    ArchitectureKind architecture,
    torch::Device device)
    : config_(config),
      rng_(run_seed),
      architecture_(architecture),
      device_(std::move(device)),
      model_(architecture, rng_.initialization_seed())
{
    config_.validate();
    if (device_.is_cuda()) {
        if (!torch::cuda::is_available()) {
            throw std::runtime_error("cuda-unavailable: CUDA was requested but LibTorch sees no CUDA device");
        }
        if (!device_.has_index() || device_.index() != 0) {
            throw std::invalid_argument("cuda-unsupported: M08 accepts only the measured cuda:0 device");
        }
    } else if (!device_.is_cpu()) {
        throw std::invalid_argument("device-unsupported: M08 accepts only cpu or cuda:0");
    }
    model_->to(device_, torch::kFloat32);
    optimizer_ = std::make_unique<torch::optim::Adam>(
        model_->parameters(),
        torch::optim::AdamOptions(config_.learning_rate).eps(config_.adam_epsilon));
}

ActionBatch MultiModalPpoTrainer::act(
    const torch::Tensor &structured,
    const torch::Tensor &spatial,
    const torch::Tensor &legal_masks,
    bool deterministic,
    torch::Tensor *device_probabilities)
{
    require_cpu_tensor(structured, "structured inference batch");
    require_cpu_tensor(spatial, "spatial inference batch");
    require_cpu_tensor(legal_masks, "legal-mask inference batch");
    EvaluationModeGuard mode(model_);
    torch::NoGradGuard guard;
    auto [device_logits, device_values] = model_->forward(structured.to(device_), spatial.to(device_));
#ifdef RL_DEV_FUSED_POLICY
    // Experimental development build only. The update/autograd path below
    // retains the trusted masked_categorical implementation.
    auto device_policy = device_.is_cuda()
        ? openttd_rl::development::fused_policy(device_logits, legal_masks.to(device_, torch::kBool))
        : masked_categorical(device_logits, legal_masks.to(device_));
#else
    auto device_policy = masked_categorical(device_logits, legal_masks.to(device_));
#endif
    const auto logits = device_logits.cpu();
    const auto values = device_values.cpu();
    const auto log_probabilities = device_policy.log_probabilities.cpu();
    torch::Tensor actions;
    if (deterministic) {
        actions = log_probabilities.argmax(1);
    } else {
        actions = sample_masked_actions(log_probabilities, legal_masks, rng_.action_sampling());
    }
    auto selected = log_probabilities.gather(1, actions.unsqueeze(1)).squeeze(1);
    require_finite_tensor(selected, "selected multimodal log probabilities");
    // Optional development inspection uses the actual ACT backend distribution.
    // The normal ACT path performs no extra copy or computation.
    if (device_probabilities != nullptr) *device_probabilities = device_policy.probabilities.cpu();
    return {actions, selected, values, logits};
}

double MultiModalPpoTrainer::audit_behavior(const MultiModalRolloutBatch &rollout)
{
    rollout.validate();
    EvaluationModeGuard mode(model_);
    torch::NoGradGuard guard;
    behavior_replay_max_error_ = 0.0;
    behavior_replay_samples_ = 0;
    for (std::int64_t start = 0; start < rollout.size(); start += config_.minibatch_size) {
        const auto count = std::min(config_.minibatch_size, rollout.size() - start);
        const auto structured = rollout.structured.narrow(0, start, count).to(device_);
        const auto spatial = rollout.spatial.narrow(0, start, count).to(device_);
        const auto masks = rollout.legal_masks.narrow(0, start, count).to(device_);
        const auto actions = rollout.actions.narrow(0, start, count).to(device_);
        const auto old_logp = rollout.old_log_probabilities.narrow(0, start, count).to(device_);
        const auto output = model_->forward(structured, spatial);
        const auto policy = masked_categorical(output.first, masks);
        const auto selected = policy.log_probabilities.gather(1, actions.unsqueeze(1)).squeeze(1);
        const auto error = (selected - old_logp).abs().max().item<double>();
        behavior_replay_max_error_ = std::max(behavior_replay_max_error_, error);
        behavior_replay_samples_ += count;
        if (!std::isfinite(error) || error > 1e-4) {
            throw std::runtime_error("behavior replay changed log probabilities");
        }
    }
    return behavior_replay_max_error_;
}

UpdateMetrics MultiModalPpoTrainer::update(const MultiModalRolloutBatch &rollout)
{
    config_.validate();
    rollout.validate();
    const auto expected_samples = config_.rollout_length * config_.environment_count;
    if (rollout.size() != expected_samples) throw std::invalid_argument("rollout sample count disagrees with configuration");
    (void)audit_behavior(rollout);
    model_->train();

    UpdateMetrics metrics;
    std::uint64_t minibatches = 0;
    for (std::int64_t epoch = 0; epoch < config_.optimization_epochs; ++epoch) {
        const auto batches = minibatch_indices(rollout.size(), config_.minibatch_size, rng_.minibatch_shuffle());
        for (const auto &batch : batches) {
            const auto indices = indices_tensor(batch);
            const auto structured = rollout.structured.index_select(0, indices).to(device_);
            const auto spatial = rollout.spatial.index_select(0, indices).to(device_);
            const auto masks = rollout.legal_masks.index_select(0, indices).to(device_);
            const auto actions = rollout.actions.index_select(0, indices).to(device_);
            const auto old_log_probabilities = rollout.old_log_probabilities.index_select(0, indices).to(device_);
            const auto advantages = rollout.advantages.index_select(0, indices).to(device_);
            const auto returns = rollout.returns.index_select(0, indices).to(device_);

            auto [logits, values] = model_->forward(structured, spatial);
            auto policy = masked_categorical(logits, masks);
            auto new_log_probabilities = policy.log_probabilities.gather(1, actions.unsqueeze(1)).squeeze(1);
            auto losses = ppo_loss(
                new_log_probabilities,
                old_log_probabilities,
                advantages,
                values,
                returns,
                policy.entropy,
                config_);
            optimizer_->zero_grad();
            losses.total.backward();
            require_finite_gradients(model_);
            const double gradient_norm = torch::nn::utils::clip_grad_norm_(
                model_->parameters(), config_.max_gradient_norm, 2.0, true);
            if (!std::isfinite(gradient_norm)) throw std::runtime_error("nonfinite global gradient norm");
            require_finite_gradients(model_);
            optimizer_->step();
            require_finite_multimodal_model(model_, "updated");

            metrics.policy_loss += losses.policy.item<double>();
            metrics.value_loss += losses.value.item<double>();
            metrics.entropy += losses.entropy.item<double>();
            metrics.approximate_kl += losses.approximate_kl.item<double>();
            metrics.clip_fraction += losses.clip_fraction.item<double>();
            metrics.gradient_norm += gradient_norm;
            ++minibatches;
        }
    }
    if (minibatches == 0) throw std::logic_error("PPO update executed no minibatches");
    const double denominator = static_cast<double>(minibatches);
    metrics.policy_loss /= denominator;
    metrics.value_loss /= denominator;
    metrics.entropy /= denominator;
    metrics.approximate_kl /= denominator;
    metrics.clip_fraction /= denominator;
    metrics.gradient_norm /= denominator;
    metrics.explained_variance = explained_variance(rollout.old_values, rollout.returns);
    metrics.learning_rate = config_.learning_rate;

    ++counters_.completed_updates;
    counters_.environment_steps += static_cast<std::uint64_t>(rollout.size());
    counters_.accepted_samples += static_cast<std::uint64_t>(rollout.size());
    metrics.update = counters_.completed_updates;
    metrics.samples = counters_.accepted_samples;
    return metrics;
}

} // namespace openttd_rl::training
