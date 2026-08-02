#include "openttd_rl/training/rng.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <sstream>
#include <stdexcept>

namespace openttd_rl::training {

namespace {

std::uint64_t fnv1a64(const std::string &text)
{
    std::uint64_t value = UINT64_C(14695981039346656037);
    for (const char character : text) {
        const auto byte = static_cast<unsigned char>(character);
        value ^= static_cast<std::uint64_t>(byte);
        value *= UINT64_C(1099511628211);
    }
    return value;
}

std::uint64_t splitmix64(std::uint64_t value)
{
    value += UINT64_C(0x9e3779b97f4a7c15);
    value = (value ^ (value >> 30U)) * UINT64_C(0xbf58476d1ce4e5b9);
    value = (value ^ (value >> 27U)) * UINT64_C(0x94d049bb133111eb);
    return value ^ (value >> 31U);
}

template <typename Generator>
std::string encode_generator(const Generator &generator)
{
    std::ostringstream stream;
    stream.imbue(std::locale::classic());
    stream << generator;
    if (!stream) throw std::runtime_error("cannot serialize RNG state");
    return stream.str();
}

template <typename Generator>
void decode_generator(const std::string &state, Generator &generator)
{
    std::istringstream stream(state);
    stream.imbue(std::locale::classic());
    Generator candidate;
    if (!(stream >> candidate)) throw std::invalid_argument("invalid RNG state");
    char trailing = 0;
    if (stream >> trailing || !stream.eof()) throw std::invalid_argument("invalid RNG state");
    generator = candidate;
}

} // namespace

std::uint64_t derive_stream_seed(std::uint64_t run_seed, const std::string &label)
{
    return splitmix64(run_seed ^ fnv1a64(label));
}

RngStreams::RngStreams(std::uint64_t run_seed)
{
    ledger_.run_seed = run_seed;
    for (std::size_t index = 0; index < kRngStreamNames.size(); ++index) {
        ledger_.stream_seeds[index] = derive_stream_seed(run_seed, kRngStreamNames[index]);
    }
    action_sampling_.seed(ledger_.stream_seeds[1]);
    minibatch_shuffle_.seed(ledger_.stream_seeds[2]);
    environment_episode_.seed(ledger_.stream_seeds[3]);
}

std::array<std::string, 3> RngStreams::mutable_states() const
{
    return {
        encode_generator(action_sampling_),
        encode_generator(minibatch_shuffle_),
        encode_generator(environment_episode_),
    };
}

void RngStreams::restore_mutable_states(const std::array<std::string, 3> &states)
{
    auto action = action_sampling_;
    auto minibatch = minibatch_shuffle_;
    auto environment = environment_episode_;
    decode_generator(states[0], action);
    decode_generator(states[1], minibatch);
    decode_generator(states[2], environment);
    action_sampling_ = action;
    minibatch_shuffle_ = minibatch;
    environment_episode_ = environment;
}

torch::Tensor sample_masked_actions(
    const torch::Tensor &log_probabilities,
    const torch::Tensor &legal_mask,
    std::mt19937_64 &generator)
{
    if (log_probabilities.device().is_cuda() || legal_mask.device().is_cuda() ||
        log_probabilities.dim() != 2 || legal_mask.sizes() != log_probabilities.sizes()) {
        throw std::invalid_argument("sampling requires aligned two-dimensional CPU tensors");
    }
    auto mask = legal_mask.to(torch::kBool).contiguous();
    if (!(mask.any(1).all().item<bool>())) throw std::invalid_argument("all-illegal action mask");
    auto probabilities = torch::exp(log_probabilities).to(torch::kFloat64).contiguous();
    if (!torch::isfinite(probabilities).all().item<bool>()) {
        throw std::runtime_error("nonfinite masked probabilities");
    }
    auto result = torch::empty({probabilities.size(0)}, torch::TensorOptions().dtype(torch::kInt64));
    const auto probability_view = probabilities.accessor<double, 2>();
    const auto mask_view = mask.accessor<bool, 2>();
    auto action_view = result.accessor<std::int64_t, 1>();
    for (std::int64_t row = 0; row < probabilities.size(0); ++row) {
        const double draw = std::generate_canonical<double, 53>(generator);
        double cumulative = 0.0;
        std::int64_t last_legal = -1;
        action_view[row] = -1;
        for (std::int64_t action = 0; action < probabilities.size(1); ++action) {
            if (!mask_view[row][action]) continue;
            last_legal = action;
            cumulative += probability_view[row][action];
            if (draw < cumulative && action_view[row] < 0) action_view[row] = action;
        }
        if (action_view[row] < 0) action_view[row] = last_legal;
        if (action_view[row] < 0) throw std::logic_error("legal mask validation was inconsistent");
    }
    return result;
}

} // namespace openttd_rl::training
