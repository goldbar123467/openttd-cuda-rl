// Development recurrent V2 adapter over the trusted V1 PPO/GAE implementation.
#include "v2_live_input.h"
#include "checkpoint_io.h"
#include "openttd_rl/training/model.h"
#include "openttd_rl/training/rng.h"

#include <algorithm>
#include <charconv>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <torch/cuda.h>
#include <torch/nn/utils/clip_grad.h>
#include <torch/version.h>

namespace {
namespace train = openttd_rl::training;
namespace v2 = openttd_rl::v2;
namespace dev = openttd_rl::development;
constexpr int64_t kSequence = 8;

std::vector<std::string> fields(const std::string &line)
{
    if (line.size() > 16384) throw std::invalid_argument("trainer request exceeds bound");
    std::vector<std::string> result;
    size_t begin = 0;
    do {
        const auto end = line.find('\t', begin);
        result.push_back(line.substr(begin, end == std::string::npos ? end : end - begin));
        if (end == std::string::npos) break;
        begin = end + 1;
    } while (true);
    return result;
}

bool flag(const std::string &value)
{
    if (value != "0" && value != "1") throw std::invalid_argument("expected binary flag");
    return value == "1";
}

struct Transition {
    v2::ScalablePolicyInput input;
    int64_t action{};
    float log_probability{}, value{}, reward{}, next_value{};
    bool bootstrap{}, continuation{};
};

class Trainer {
public:
    Trainer(uint64_t seed, torch::Device device, int64_t rollout_length = 32, double gae_lambda = 0.95,
        dev::FinancialFeatures financial_features = dev::FinancialFeatures::Raw, double entropy_coefficient = 0.01,
        bool choice_weighted = false, bool diagnostics = false) :
        device_(std::move(device)), financial_features_(financial_features), choice_weighted_(choice_weighted),
        diagnostics_(diagnostics), rng_(seed), model_(rng_.initialization_seed())
    {
        if (device_.is_cuda() && !torch::cuda::is_available()) throw std::runtime_error("CUDA unavailable; no fallback");
        if (rollout_length != 32 && rollout_length != 64 && rollout_length != 128) throw std::invalid_argument("rollout length must be 32, 64 or 128");
        if (!std::isfinite(gae_lambda) || gae_lambda < 0.0 || gae_lambda > 1.0) throw std::invalid_argument("gae-lambda must be finite and in [0,1]");
        if (!std::isfinite(entropy_coefficient) || entropy_coefficient < 0.0 || entropy_coefficient > 1.0)
            throw std::invalid_argument("entropy-coefficient must be finite and in [0,1]");
        config_.entropy_coefficient = entropy_coefficient;
        config_.rollout_length = rollout_length;
        config_.gae_lambda = gae_lambda;
        config_.environment_count = 1;
        config_.minibatch_size = kSequence;
        config_.optimization_epochs = 4;
        config_.validate();
        model_->to(device_);
        optimizer_ = std::make_unique<torch::optim::Adam>(model_->parameters(),
            torch::optim::AdamOptions(config_.learning_rate).eps(config_.adam_epsilon));
        hidden_ = torch::zeros({1, v2::kHiddenSize}, torch::TensorOptions().device(device_));
    }

    void act(const std::vector<std::string> &request)
    {
        if ((request.size() != 4 && request.size() != 5) || pending_ || rollout_.size() >= static_cast<size_t>(config_.rollout_length)) throw std::invalid_argument("ACT at invalid rollout boundary");
        const bool reset = flag(request[3]);
        if (reset != expected_reset_) throw std::invalid_argument("recurrent reset flag disagrees with episode boundary");
        torch::NoGradGuard guard;
        model_->eval();
        auto cpu = dev::read_live_v2_input(request[1], request[2], financial_features_);
        if (reset) hidden_.zero_();
        cpu.hidden_state = hidden_.cpu().clone();
        cpu.recurrent_reset.fill_(reset);
        const auto input = dev::live_v2_to(cpu, device_);
        const auto output = model_->forward(input);
        const auto policy = dev::live_v2_distribution(output, input);
        const auto log_probabilities = policy.log_probabilities.cpu();
        const auto actions = train::sample_masked_actions(log_probabilities, cpu.candidate_mask, rng_.action_sampling());
        const int64_t action = actions.item<int64_t>();
        rollout_.push_back({cpu, action, log_probabilities[0][action].item<float>(), output.value.item<float>(), 0, 0, false, false});
        hidden_ = output.next_hidden.detach();
        pending_ = true;
        std::cout << "{\"row\":" << action << ",\"log_probability\":" << rollout_.back().log_probability
            << ",\"value\":" << rollout_.back().value;
        if (request.size() == 5) {
            const auto row = proposal_row(request[4], cpu.candidate_mask);
            std::cout << ",\"proposal_probability\":" << policy.probabilities[0][row].item<float>()
                << ",\"sampling_legal_count\":" << cpu.candidate_mask.sum().item<int64_t>()
                << ",\"entropy\":" << policy.entropy.item<float>();
        }
        std::cout << "}" << std::endl;
    }

    static int64_t proposal_row(const std::string &text, const torch::Tensor &mask)
    {
        int64_t row = -1;
        const auto parsed = std::from_chars(text.data(), text.data() + text.size(), row);
        if (parsed.ec != std::errc{} || parsed.ptr != text.data() + text.size() || row < 0 ||
            row >= mask.size(1) || !mask[0][row].item<bool>())
            throw std::invalid_argument("proposal row must be a legal candidate");
        return row;
    }

    void probe(const std::vector<std::string> &request)
    {
        if (request.size() != 4 || pending_ || !rollout_.empty())
            throw std::invalid_argument("PROBE requires a completed update");
        torch::NoGradGuard guard;
        struct ModeGuard {
            v2::ScalablePolicy &model;
            bool training;
            ~ModeGuard() { model->train(training); }
        } mode{model_, model_->is_training()};
        model_->eval();
        auto input = dev::live_v2_to(dev::read_live_v2_input(request[1], request[2], financial_features_), device_);
        input.hidden_state = torch::zeros_like(hidden_);
        input.recurrent_reset.fill_(true);
        const auto row = proposal_row(request[3], input.candidate_mask);
        const auto output = model_->forward(input);
        const auto policy = dev::live_v2_distribution(output, input);
        // No actor hidden-state assignment, sampling, shuffle or optimizer step.
        std::cout << "{\"proposal_probability\":" << policy.probabilities[0][row].item<float>()
            << ",\"value\":" << output.value.item<float>() << ",\"entropy\":" << policy.entropy.item<float>()
            << ",\"sampling_legal_count\":" << input.candidate_mask.sum().item<int64_t>() << "}" << std::endl;
    }

    void reward(const std::vector<std::string> &request)
    {
        if (request.size() != 6 || !pending_) throw std::invalid_argument("REWARD without a pending ACT");
        size_t consumed = 0;
        const float reward = std::stof(request[1], &consumed);
        if (consumed != request[1].size() || !std::isfinite(reward)) throw std::invalid_argument("reward is not finite numeric data");
        const bool bootstrap = flag(request[2]), continuation = flag(request[3]);
        if (continuation && !bootstrap) throw std::invalid_argument("continuing transition cannot disable bootstrap");
        float next_value = 0;
        if (bootstrap) {
            torch::NoGradGuard guard;
            auto input = dev::live_v2_to(dev::read_live_v2_input(request[4], request[5], financial_features_), device_);
            input.hidden_state = hidden_;
            // Bootstrap inference must not advance the recurrent actor state.
            next_value = model_->forward(input).value.item<float>();
        } else if (request[4] != "-" || request[5] != "-") {
            throw std::invalid_argument("terminal transition must not provide future tensors");
        }
        auto &transition = rollout_.back();
        transition.reward = reward; transition.next_value = next_value;
        transition.bootstrap = bootstrap; transition.continuation = continuation;
        pending_ = false;
        expected_reset_ = !continuation;
        std::cout << "{\"accepted\":" << rollout_.size() << ",\"next_value\":" << next_value << "}" << std::endl;
    }

    void update()
    {
        if (pending_ || rollout_.size() != static_cast<size_t>(config_.rollout_length)) throw std::invalid_argument("UPDATE requires a complete on-policy rollout");
        auto floats = [this](const std::vector<float> &values) {
            return torch::tensor(values, torch::kFloat32).reshape({config_.rollout_length, 1});
        };
        std::vector<float> rewards, values, next_values, bootstrap, continuation, old_logs, choices;
        for (const auto &t : rollout_) {
            rewards.push_back(t.reward); values.push_back(t.value); next_values.push_back(t.next_value);
            bootstrap.push_back(t.bootstrap ? 1.0F : 0.0F); continuation.push_back(t.continuation ? 1.0F : 0.0F);
            old_logs.push_back(t.log_probability);
            choices.push_back(t.input.candidate_mask.sum().item<int64_t>() >= 2 ? 1.0F : 0.0F);
        }
        auto gae = train::compute_gae(floats(rewards), floats(values), floats(next_values),
            floats(bootstrap).to(torch::kBool), floats(continuation).to(torch::kBool), config_.gamma, config_.gae_lambda);
        const auto choice_weights = floats(choices).flatten();
        const auto raw_advantages = gae.advantages.flatten();
        const auto advantages = (choice_weighted_ ? train::normalize_choice_advantages(raw_advantages, choice_weights) :
            train::normalize_advantages(raw_advantages)).to(torch::kFloat32);
        const auto returns = gae.returns.flatten().to(torch::kFloat32);
        const auto old_log_probabilities = floats(old_logs).flatten();
        double policy_loss = 0, value_loss = 0, entropy = 0, kl = 0, gradient = 0, behavior_error = 0;
        double choice_entropy = 0, choice_kl = 0, choice_clip = 0;
        const auto choice_count = choice_weights.sum().item<int64_t>();
        const auto choice_advantages = raw_advantages.masked_select(choice_weights.to(torch::kBool));
        const double choice_mean = choice_count ? choice_advantages.mean().item<double>() : 0;
        const double choice_std = choice_count ? torch::sqrt(torch::square(choice_advantages - choice_mean).mean()).item<double>() : 0;
        uint64_t batches = 0;
        model_->train();
        {
            torch::NoGradGuard guard;
            // Audit every sequence before any parameter changes, including
            // sequences whose interior crosses a real environment reset.
            for (int64_t begin = 0; begin < config_.rollout_length; begin += kSequence) {
                auto hidden = rollout_[static_cast<size_t>(begin)].input.hidden_state.to(device_);
                for (int64_t offset = 0; offset < kSequence; ++offset) {
                    const auto &transition = rollout_[static_cast<size_t>(begin + offset)];
                    auto input = dev::live_v2_to(transition.input, device_);
                    input.hidden_state = hidden;
                    const auto output = model_->forward(input);
                    const auto policy = dev::live_v2_distribution(output, input);
                    const double actual = policy.log_probabilities[0][transition.action].item<double>();
                    behavior_error = std::max(behavior_error, std::abs(actual - transition.log_probability));
                    hidden = output.next_hidden;
                }
            }
            if (behavior_error > 1e-4) throw std::runtime_error("recurrent replay changed behavior log probabilities");
        }
        // Shuffle whole eight-step sequences. The stored initial hidden state
        // starts each sequence; subsequent states are recomputed with gradients.
        // Reset masks cut recurrent gradients at actual environment resets.
        for (int64_t epoch = 0; epoch < config_.optimization_epochs; ++epoch) {
            for (const auto &batch : train::minibatch_indices(config_.rollout_length / kSequence, 1, rng_.minibatch_shuffle())) {
                const int64_t begin = batch.front() * kSequence;
                auto hidden = rollout_[static_cast<size_t>(begin)].input.hidden_state.to(device_);
                std::vector<torch::Tensor> log_parts, value_parts, entropy_parts;
                for (int64_t offset = 0; offset < kSequence; ++offset) {
                    const auto &transition = rollout_[static_cast<size_t>(begin + offset)];
                    auto input = dev::live_v2_to(transition.input, device_);
                    input.hidden_state = hidden;
                    auto output = model_->forward(input);
                    auto policy = dev::live_v2_distribution(output, input);
                    log_parts.push_back(policy.log_probabilities.select(1, transition.action));
                    value_parts.push_back(output.value);
                    entropy_parts.push_back(policy.entropy);
                    hidden = output.next_hidden;
                }
                auto new_logs = torch::cat(log_parts);
                auto old = old_log_probabilities.slice(0, begin, begin + kSequence).to(device_);
                const auto batch_weights = choice_weights.slice(0, begin, begin + kSequence).to(device_);
                const auto batch_entropy = torch::cat(entropy_parts);
                auto losses = train::ppo_loss(new_logs, old, advantages.slice(0, begin, begin + kSequence).to(device_),
                    torch::cat(value_parts), returns.slice(0, begin, begin + kSequence).to(device_), batch_entropy, config_,
                    choice_weighted_ ? batch_weights : torch::Tensor{});
                const auto log_ratio = new_logs.detach() - old;
                const auto ratio = log_ratio.exp();
                choice_entropy += (batch_entropy.detach() * batch_weights).sum().item<double>();
                choice_kl += (((ratio - 1) - log_ratio) * batch_weights).sum().item<double>();
                choice_clip += ((torch::abs(ratio - 1) > config_.clip_epsilon).to(torch::kFloat64) * batch_weights).sum().item<double>();
                optimizer_->zero_grad();
                losses.total.backward();
                for (const auto &parameter : model_->named_parameters(true)) {
                    if (!parameter.value().grad().defined() || !torch::isfinite(parameter.value().grad()).all().item<bool>())
                        throw std::runtime_error("missing/nonfinite recurrent policy gradient: " + parameter.key());
                }
                const double norm = torch::nn::utils::clip_grad_norm_(model_->parameters(), config_.max_gradient_norm, 2.0, true);
                if (!std::isfinite(norm)) throw std::runtime_error("nonfinite recurrent policy gradient norm");
                optimizer_->step();
                v2::require_finite_policy(model_, "live PPO update");
                policy_loss += losses.policy.item<double>(); value_loss += losses.value.item<double>();
                entropy += losses.entropy.item<double>(); kl += losses.approximate_kl.item<double>(); gradient += norm;
                ++batches;
            }
        }
        ++updates_;
        const double denominator = static_cast<double>(batches);
        const double choice_denominator = std::max(1.0, static_cast<double>(choice_count * config_.optimization_epochs));
        std::cout << "{\"update\":" << updates_ << ",\"transitions\":" << updates_ * static_cast<uint64_t>(config_.rollout_length)
            << ",\"policy_loss\":" << policy_loss / denominator << ",\"value_loss\":" << value_loss / denominator
            << ",\"entropy\":" << entropy / denominator << ",\"approximate_kl\":" << kl / denominator
            << ",\"gradient_norm\":" << gradient / denominator << ",\"behavior_replay_max_error\":" << behavior_error
            << ",\"explained_variance\":" << train::explained_variance(floats(values).flatten(), returns);
        if (diagnostics_) std::cout << ",\"choice_steps\":" << choice_count << ",\"forced_steps\":" << config_.rollout_length - choice_count
            << ",\"entropy_choice\":" << choice_entropy / choice_denominator
            << ",\"approx_kl_choice\":" << choice_kl / choice_denominator
            << ",\"clip_fraction_choice\":" << choice_clip / choice_denominator
            << ",\"advantage_choice_mean\":" << choice_mean << ",\"advantage_choice_std\":" << choice_std;
        std::cout << "}" << std::endl;
        save_probe_ = rollout_.back().input;
        rollout_.clear();
    }

    std::string checkpoint_identity() const
    {
        std::ostringstream out;
        out << "openttd-rl-development-v2-trainer-checkpoint-1\n" << TORCH_VERSION << '\n'
            << "v2-m15-public-development-v2\n" << device_ << '\n' << rng_.ledger().run_seed << '\n' << std::hexfloat
            << config_.gamma << ' ' << config_.gae_lambda << ' ' << config_.clip_epsilon << ' '
            << config_.value_coefficient << ' ' << config_.entropy_coefficient << ' ' << config_.learning_rate << ' '
            << config_.adam_epsilon << ' ' << config_.max_gradient_norm << '\n' << config_.rollout_length << ' ' << kSequence << ' '
            << config_.optimization_epochs << '\n' << at::globalContext().deterministicCuDNN() << ' '
            << at::globalContext().benchmarkCuDNN() << ' ' << torch::get_num_threads() << '\n'
            << at::globalContext().deterministicAlgorithms() << ' ' << at::globalContext().deterministicAlgorithmsWarnOnly()
            << "\ncublas-workspace=:4096:8";
        if (financial_features_ != dev::FinancialFeatures::Raw)
            out << "\nfinancial-features=" << dev::financial_features_name(financial_features_);
        if (choice_weighted_) out << "\npolicy-loss=choice-weighted-v1";
        return out.str();
    }

    void checkpoint_info() const
    {
        std::cout << "{\"format\":\"openttd-rl-development-v2-reset-checkpoint-1\",\"reset_only\":true,"
            << "\"deterministic_algorithms\":true,\"cublas_workspace_config\":\":4096:8\",\"updates\":"
            << updates_ << "}" << std::endl;
    }

    void training_info() const
    {
        std::cout << "{\"rollout_steps\":" << config_.rollout_length << ",\"sequence_length\":" << kSequence
            << ",\"optimization_epochs\":" << config_.optimization_epochs << std::setprecision(17)
            << ",\"gamma\":" << config_.gamma << ",\"gae_lambda\":" << config_.gae_lambda
            << ",\"entropy_coefficient\":" << config_.entropy_coefficient
            << ",\"choice_weighted\":" << (choice_weighted_ ? "true" : "false")
            << ",\"learning_rate\":" << config_.learning_rate << ",\"clip_epsilon\":" << config_.clip_epsilon
            << ",\"max_gradient_norm\":" << config_.max_gradient_norm << ",\"value_coefficient\":" << config_.value_coefficient
            << "}" << std::setprecision(9) << std::endl;
    }

    void financial_features_info() const
    {
        std::cout << "{\"financial_features\":\"" << dev::financial_features_name(financial_features_) << "\"}" << std::endl;
    }

    void check_checkpoint_state()
    {
        v2::require_finite_policy(model_, "checkpoint policy");
        train::require_finite_tensor(hidden_, "checkpoint hidden state");
        if (hidden_.device() != device_ || hidden_.scalar_type() != torch::kFloat32 ||
            hidden_.sizes() != torch::IntArrayRef({1, v2::kHiddenSize}))
            throw std::invalid_argument("checkpoint recurrent shape/device mismatch");
        for (const auto &parameter : model_->parameters()) {
            if (parameter.device() != device_) throw std::invalid_argument("checkpoint parameter device mismatch");
        }
        for (const auto &entry : optimizer_->state()) {
            const auto *state = dynamic_cast<const torch::optim::AdamParamState *>(entry.second.get());
            if (state == nullptr || state->step() < 0) throw std::invalid_argument("checkpoint Adam state invalid");
            for (const auto &moment : {state->exp_avg(), state->exp_avg_sq()}) {
                train::require_finite_tensor(moment, "checkpoint Adam moment");
                if (moment.device() != device_) throw std::invalid_argument("checkpoint Adam device mismatch");
            }
        }
    }

    void checkpoint(const std::string &name)
    {
        if (pending_ || !rollout_.empty() || !expected_reset_ || updates_ == 0)
            throw std::invalid_argument("CHECKPOINT requires an updated trainer at a native reset boundary");
        check_checkpoint_state();
        torch::serialize::OutputArchive archive, model, optimizer;
        dev::checkpoint_string(archive, "identity", checkpoint_identity());
        model_->save(model); optimizer_->save(optimizer);
        archive.write("model", model); archive.write("optimizer", optimizer);
        const auto states = rng_.mutable_states();
        for (size_t i = 0; i < states.size(); ++i) dev::checkpoint_string(archive, "rng_" + std::to_string(i), states[i]);
        archive.write("torch_cpu_rng", at::globalContext().defaultGenerator(torch::kCPU).get_state(), true);
        if (device_.is_cuda()) archive.write("torch_cuda_rng", at::globalContext().defaultGenerator(device_).get_state(), true);
        archive.write("hidden", hidden_, true);
        archive.write("counters", torch::tensor({static_cast<int64_t>(updates_), model_->is_training() ? int64_t{1} : int64_t{0}}, torch::kInt64), true);
        dev::publish_checkpoint(archive, std::filesystem::path(name));
        std::cout << "{\"status\":\"SAVED_RESET_CHECKPOINT\",\"updates\":" << updates_
            << ",\"transitions\":" << updates_ * static_cast<uint64_t>(config_.rollout_length) << "}" << std::endl;
    }

    void restore(const std::string &name)
    {
        const std::filesystem::path path(name);
        if (updates_ != 0 || pending_ || !rollout_.empty() || !expected_reset_ || !path.is_absolute() ||
            std::filesystem::file_size(path) > 512U * 1024U * 1024U)
            throw std::invalid_argument("RESTORE requires a bounded checkpoint and fresh trainer");
        torch::serialize::InputArchive archive, model, optimizer;
        archive.load_from(path.string());
        if (dev::checkpoint_string(archive, "identity") != checkpoint_identity())
            throw std::invalid_argument("checkpoint configuration, seed, schema, runtime or device mismatch");
        std::array<std::string, 3> states;
        for (size_t i = 0; i < states.size(); ++i) states[i] = dev::checkpoint_string(archive, "rng_" + std::to_string(i));
        torch::Tensor counters, cpu_rng, cuda_rng;
        archive.read("counters", counters, true);
        if (!counters.device().is_cpu() || counters.scalar_type() != torch::kInt64 || counters.sizes() != torch::IntArrayRef({2}))
            throw std::invalid_argument("checkpoint counter shape/type mismatch");
        const auto count = counters[0].item<int64_t>(), mode = counters[1].item<int64_t>();
        if (count <= 0 || count > std::numeric_limits<int64_t>::max() / config_.rollout_length || (mode != 0 && mode != 1))
            throw std::invalid_argument("checkpoint counters invalid");
        archive.read("torch_cpu_rng", cpu_rng, true);
        if (device_.is_cuda()) archive.read("torch_cuda_rng", cuda_rng, true);
        archive.read("model", model); archive.read("optimizer", optimizer); archive.read("hidden", hidden_, true);
        model_->load(model); optimizer_->load(optimizer);
        check_checkpoint_state();
        rng_.restore_mutable_states(states);
        updates_ = static_cast<uint64_t>(count);
        model_->train(mode != 0);
        auto cpu_generator = at::globalContext().defaultGenerator(torch::kCPU);
        cpu_generator.set_state(cpu_rng);
        if (device_.is_cuda()) {
            auto cuda_generator = at::globalContext().defaultGenerator(device_);
            cuda_generator.set_state(cuda_rng);
        }
        std::cout << "{\"status\":\"RESTORED_RESET_CHECKPOINT\",\"updates\":" << updates_
            << ",\"transitions\":" << updates_ * static_cast<uint64_t>(config_.rollout_length) << "}" << std::endl;
    }

    void save(const std::string &name)
    {
        const std::filesystem::path path(name);
        if (pending_ || !rollout_.empty() || !save_probe_ || !path.is_absolute() || std::filesystem::exists(path))
            throw std::invalid_argument("SAVE needs a fresh absolute file at an update boundary");
        torch::serialize::OutputArchive archive;
        dev::write_live_v2_weights(archive, model_, financial_features_);
        archive.save_to(path.string());
        // Reload into a separate module and check the current trained policy
        // on an actual collected input before declaring the weights usable.
        torch::NoGradGuard guard;
        v2::ScalablePolicy reloaded(0);
        torch::serialize::InputArchive saved;
        saved.load_from(path.string(), device_);
        reloaded->to(device_);
        dev::read_live_v2_weights(saved, reloaded, financial_features_);
        reloaded->eval();
        v2::require_finite_policy(reloaded, "saved inference weights");
        const auto input = dev::live_v2_to(*save_probe_, device_);
        const auto expected = model_->forward(input), actual = reloaded->forward(input);
        const double error = std::max({(expected.family_logits - actual.family_logits).abs().max().item<double>(),
            (expected.candidate_logits - actual.candidate_logits).abs().max().item<double>(),
            (expected.value - actual.value).abs().max().item<double>(),
            (expected.next_hidden - actual.next_hidden).abs().max().item<double>()});
        if (error > 1e-6) throw std::runtime_error("saved V2 inference weights changed model outputs");
        std::cout << "{\"status\":\"SAVED_INFERENCE_WEIGHTS\",\"updates\":" << updates_
            << ",\"reload_output_max_error\":" << error << "}" << std::endl;
    }

private:
    torch::Device device_;
    dev::FinancialFeatures financial_features_;
    bool choice_weighted_;
    bool diagnostics_;
    train::PpoConfig config_;
    train::RngStreams rng_;
    v2::ScalablePolicy model_;
    std::unique_ptr<torch::optim::Adam> optimizer_;
    torch::Tensor hidden_;
    std::vector<Transition> rollout_;
    std::optional<v2::ScalablePolicyInput> save_probe_;
    bool pending_{};
    bool expected_reset_{true};
    uint64_t updates_{};
};
} // namespace

int main(int argc, char **argv)
{
    try {
        if (argc < 5 || argc > 17 || argc % 2 != 1 || std::string(argv[1]) != "--device" || std::string(argv[3]) != "--seed")
            throw std::invalid_argument("usage: --device cpu|cuda:0 --seed INTEGER [--rollout-length 32|64|128] [--gae-lambda NUMBER] [--financial-features raw|signed-log-v1] [--entropy-coefficient NUMBER] [--policy-loss historical|choice-weighted] [--recovery-diagnostics 0|1]");
        if (std::string(argv[2]) != "cpu" && std::string(argv[2]) != "cuda:0") throw std::invalid_argument("unsupported device");
        int64_t rollout_length = 32;
        double gae_lambda = 0.95;
        double entropy_coefficient = 0.01;
        auto financial_features = dev::FinancialFeatures::Raw;
        bool has_rollout = false, has_lambda = false, has_financial_features = false, has_entropy = false, has_loss = false;
        bool choice_weighted = false, diagnostics = false, has_diagnostics = false;
        for (int index = 5; index < argc; index += 2) {
            const std::string option(argv[index]), value(argv[index + 1]);
            if (option == "--rollout-length" && !has_rollout) {
                if (value != "32" && value != "64" && value != "128")
                    throw std::invalid_argument("rollout length must be 32, 64 or 128");
                rollout_length = value == "128" ? 128 : (value == "64" ? 64 : 32);
                has_rollout = true;
            } else if (option == "--gae-lambda" && !has_lambda) {
                const auto parsed = std::from_chars(value.data(), value.data() + value.size(), gae_lambda);
                if (parsed.ec != std::errc{} || parsed.ptr != value.data() + value.size() ||
                    !std::isfinite(gae_lambda) || gae_lambda < 0.0 || gae_lambda > 1.0)
                    throw std::invalid_argument("gae-lambda must be finite and in [0,1]");
                has_lambda = true;
            } else if (option == "--entropy-coefficient" && !has_entropy) {
                const auto parsed = std::from_chars(value.data(), value.data() + value.size(), entropy_coefficient);
                if (parsed.ec != std::errc{} || parsed.ptr != value.data() + value.size() ||
                    !std::isfinite(entropy_coefficient) || entropy_coefficient < 0.0 || entropy_coefficient > 1.0)
                    throw std::invalid_argument("entropy-coefficient must be finite and in [0,1]");
                has_entropy = true;
            } else if (option == "--recovery-diagnostics" && !has_diagnostics) {
                diagnostics = flag(value);
                has_diagnostics = true;
            } else if (option == "--policy-loss" && !has_loss) {
                if (value != "historical" && value != "choice-weighted") throw std::invalid_argument("unsupported policy loss");
                choice_weighted = value == "choice-weighted";
                has_loss = true;
            } else if (option == "--financial-features" && !has_financial_features) {
                financial_features = dev::parse_financial_features(value);
                has_financial_features = true;
            } else {
                throw std::invalid_argument("unknown or duplicate trainer option");
            }
        }
        torch::set_num_threads(1);
        // CuDNN's flag alone does not cover the graph encoder's scatter_add or
        // gather backward. Require deterministic alternatives, never warn-only.
        // Configure cuBLAS before the first device tensor/handle is created.
        if (::setenv("CUBLAS_WORKSPACE_CONFIG", ":4096:8", 1) != 0)
            throw std::runtime_error("cannot configure deterministic cuBLAS workspace");
        at::globalContext().setDeterministicAlgorithms(true, false);
        at::globalContext().setDeterministicCuDNN(true);
        at::globalContext().setBenchmarkCuDNN(false);
        Trainer trainer(std::stoull(argv[4]), torch::Device(argv[2]), rollout_length, gae_lambda, financial_features, entropy_coefficient, choice_weighted, diagnostics);
        std::cout << std::setprecision(9);
        std::string line;
        while (std::getline(std::cin, line)) {
            const auto request = fields(line);
            if (request[0] == "ACT") trainer.act(request);
            else if (request[0] == "PROBE") trainer.probe(request);
            else if (request[0] == "REWARD") trainer.reward(request);
            else if (request[0] == "UPDATE" && request.size() == 1) trainer.update();
            else if (request[0] == "SAVE" && request.size() == 2) trainer.save(request[1]);
            else if (request[0] == "CHECKPOINT" && request.size() == 2) trainer.checkpoint(request[1]);
            else if (request[0] == "RESTORE" && request.size() == 2) trainer.restore(request[1]);
            else if (request[0] == "CHECKPOINT_INFO" && request.size() == 1) trainer.checkpoint_info();
            else if (request[0] == "TRAINING_INFO" && request.size() == 1) trainer.training_info();
            else if (request[0] == "FINANCIAL_FEATURES_INFO" && request.size() == 1) trainer.financial_features_info();
            else if (request[0] == "CLOSE" && request.size() == 1) { std::cout << "{\"status\":\"CLOSED\"}" << std::endl; break; }
            else throw std::invalid_argument("unknown live PPO request");
        }
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "live V2 PPO failed: " << error.what() << '\n';
        return 1;
    }
}
