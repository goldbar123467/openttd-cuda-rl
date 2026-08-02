#include <array>
#include <bit>
#include <cerrno>
#include <charconv>
#include <cstdint>
#include <cstring>
#include <exception>
#include <filesystem>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <string_view>
#include <sys/types.h>
#include <unistd.h>
#include <vector>

#include <torch/torch.h>

#include "openttd_rl/training/evaluation_model.h"

namespace {

constexpr std::array<char, 8> kRequestMagic = {'O', 'T', 'R', 'L', 'E', 'S', '0', '1'};
constexpr std::array<char, 8> kResponseMagic = {'O', 'T', 'R', 'L', 'E', 'R', '0', '1'};
constexpr std::uint32_t kAct = 1;
constexpr std::uint32_t kExit = 4;
constexpr std::size_t kMaximumFrameBytes = 64U * 1024U * 1024U;

class Writer {
public:
    void u32(std::uint32_t value)
    {
        for (unsigned int shift = 0; shift < 32U; shift += 8U) data_.push_back(static_cast<std::uint8_t>(value >> shift));
    }
    void u64(std::uint64_t value)
    {
        for (unsigned int shift = 0; shift < 64U; shift += 8U) data_.push_back(static_cast<std::uint8_t>(value >> shift));
    }
    void i64(std::int64_t value) { u64(std::bit_cast<std::uint64_t>(value)); }
    void f64(double value) { u64(std::bit_cast<std::uint64_t>(value)); }
    void string(const std::string &value)
    {
        if (value.size() > 65535U) throw std::length_error("evaluator string exceeds bound");
        u32(static_cast<std::uint32_t>(value.size()));
        data_.insert(data_.end(), value.begin(), value.end());
    }
    [[nodiscard]] const std::vector<std::uint8_t> &data() const noexcept { return data_; }

private:
    std::vector<std::uint8_t> data_;
};

class Reader {
public:
    explicit Reader(const std::vector<std::uint8_t> &data) : data_(data) {}
    std::uint8_t u8() { require(1); return data_[offset_++]; }
    std::uint32_t u32()
    {
        require(4);
        std::uint32_t value = 0;
        for (unsigned int index = 0; index < 4U; ++index) {
            value |= static_cast<std::uint32_t>(data_[offset_++]) << (index * 8U);
        }
        return value;
    }
    float f32() { return std::bit_cast<float>(u32()); }
    void finish() const
    {
        if (offset_ != data_.size()) throw std::invalid_argument("evaluator request has trailing bytes");
    }

private:
    void require(std::size_t size) const
    {
        if (size > data_.size() - offset_) throw std::invalid_argument("evaluator request is truncated");
    }
    const std::vector<std::uint8_t> &data_;
    std::size_t offset_{};
};

bool read_exact_or_eof(int descriptor, void *buffer, std::size_t length)
{
    auto *bytes = static_cast<std::uint8_t *>(buffer);
    std::size_t received = 0;
    while (received < length) {
        const auto result = ::read(descriptor, bytes + received, length - received);
        if (result < 0 && errno == EINTR) continue;
        if (result < 0) throw std::runtime_error("M09 evaluator read failed: " + std::string(std::strerror(errno)));
        if (result == 0) {
            if (received == 0) return false;
            throw std::runtime_error("M09 evaluator frame was truncated");
        }
        received += static_cast<std::size_t>(result);
    }
    return true;
}

void write_exact(int descriptor, const void *buffer, std::size_t length)
{
    const auto *bytes = static_cast<const std::uint8_t *>(buffer);
    std::size_t written = 0;
    while (written < length) {
        const auto result = ::write(descriptor, bytes + written, length - written);
        if (result < 0 && errno == EINTR) continue;
        if (result <= 0) throw std::runtime_error("M09 evaluator write failed: " + std::string(std::strerror(errno)));
        written += static_cast<std::size_t>(result);
    }
}

std::uint32_t decode_u32(const std::uint8_t *bytes)
{
    std::uint32_t value = 0;
    for (unsigned int index = 0; index < 4U; ++index) value |= static_cast<std::uint32_t>(bytes[index]) << (index * 8U);
    return value;
}

std::uint64_t decode_u64(const std::uint8_t *bytes)
{
    std::uint64_t value = 0;
    for (unsigned int index = 0; index < 8U; ++index) value |= static_cast<std::uint64_t>(bytes[index]) << (index * 8U);
    return value;
}

void send_response(int descriptor, std::uint32_t type, std::uint32_t status, const std::vector<std::uint8_t> &payload)
{
    std::array<std::uint8_t, 24> header{};
    std::memcpy(header.data(), kResponseMagic.data(), kResponseMagic.size());
    for (unsigned int index = 0; index < 4U; ++index) {
        header[8U + index] = static_cast<std::uint8_t>(type >> (index * 8U));
        header[12U + index] = static_cast<std::uint8_t>(status >> (index * 8U));
    }
    const auto length = static_cast<std::uint64_t>(payload.size());
    for (unsigned int index = 0; index < 8U; ++index) header[16U + index] = static_cast<std::uint8_t>(length >> (index * 8U));
    write_exact(descriptor, header.data(), header.size());
    if (!payload.empty()) write_exact(descriptor, payload.data(), payload.size());
}

torch::Tensor read_structured(Reader &reader, std::int64_t samples)
{
    auto result = torch::empty({samples, openttd_rl::training::kStructuredFeatures}, torch::kFloat32);
    auto view = result.accessor<float, 2>();
    for (std::int64_t sample = 0; sample < samples; ++sample) {
        for (std::int64_t feature = 0; feature < openttd_rl::training::kStructuredFeatures; ++feature) {
            view[sample][feature] = reader.f32();
        }
    }
    return result;
}

torch::Tensor read_spatial(Reader &reader, std::int64_t samples)
{
    auto result = torch::empty(
        {samples, openttd_rl::training::kSpatialChannels, openttd_rl::training::kSpatialHeight, openttd_rl::training::kSpatialWidth},
        torch::kFloat32);
    auto flat_tensor = result.reshape({samples, -1});
    auto flat = flat_tensor.accessor<float, 2>();
    const auto features = openttd_rl::training::kSpatialChannels * openttd_rl::training::kSpatialHeight *
        openttd_rl::training::kSpatialWidth;
    for (std::int64_t sample = 0; sample < samples; ++sample) {
        for (std::int64_t feature = 0; feature < features; ++feature) flat[sample][feature] = reader.f32();
    }
    return result;
}

torch::Tensor read_masks(Reader &reader, std::int64_t samples)
{
    auto result = torch::empty({samples, openttd_rl::training::kActionCount}, torch::kBool);
    auto view = result.accessor<bool, 2>();
    for (std::int64_t sample = 0; sample < samples; ++sample) {
        for (std::int64_t action = 0; action < openttd_rl::training::kActionCount; ++action) {
            const auto value = reader.u8();
            if (value > 1U) throw std::invalid_argument("evaluator action mask is not boolean");
            view[sample][action] = value != 0U;
        }
    }
    return result;
}

std::vector<std::uint8_t> handle_act(openttd_rl::training::ReadOnlyEvaluationPolicy &policy, Reader &reader)
{
    const auto samples = static_cast<std::int64_t>(reader.u32());
    if (samples <= 0 || samples > 64) throw std::invalid_argument("evaluator ACT batch is outside [1,64]");
    const auto deterministic = reader.u8();
    if (deterministic > 1U) throw std::invalid_argument("evaluator ACT mode is not boolean");
    const auto structured = read_structured(reader, samples);
    const auto spatial = read_spatial(reader, samples);
    const auto masks = read_masks(reader, samples);
    reader.finish();
    const auto result = policy.act(structured, spatial, masks, deterministic != 0U);
    const auto action_tensor = result.actions.contiguous();
    const auto actions = action_tensor.accessor<std::int64_t, 1>();
    const auto log_tensor = result.log_probabilities.to(torch::kFloat64).contiguous();
    const auto value_tensor = result.values.to(torch::kFloat64).contiguous();
    const auto log_probabilities = log_tensor.accessor<double, 1>();
    const auto values = value_tensor.accessor<double, 1>();
    Writer writer;
    writer.u32(static_cast<std::uint32_t>(samples));
    for (std::int64_t sample = 0; sample < samples; ++sample) {
        writer.i64(actions[sample]);
        writer.f64(log_probabilities[sample]);
        writer.f64(values[sample]);
    }
    return writer.data();
}

int run_service(openttd_rl::training::ReadOnlyEvaluationPolicy &policy)
{
    if constexpr (std::endian::native != std::endian::little) {
        throw std::runtime_error("M09 evaluator requires an explicitly supported little-endian host");
    }
    const auto initial_state = policy.state_sha256();
    while (true) {
        std::array<std::uint8_t, 20> header{};
        if (!read_exact_or_eof(STDIN_FILENO, header.data(), header.size())) return 0;
        if (std::memcmp(header.data(), kRequestMagic.data(), kRequestMagic.size()) != 0) {
            throw std::runtime_error("M09 evaluator request magic mismatch");
        }
        const auto type = decode_u32(header.data() + 8);
        const auto length = decode_u64(header.data() + 12);
        if (length > kMaximumFrameBytes) throw std::length_error("M09 evaluator request exceeds frame bound");
        std::vector<std::uint8_t> payload(static_cast<std::size_t>(length));
        if (!payload.empty() && !read_exact_or_eof(STDIN_FILENO, payload.data(), payload.size())) {
            throw std::runtime_error("M09 evaluator request body was truncated");
        }
        try {
            Reader reader(payload);
            std::vector<std::uint8_t> response;
            if (type == kAct) response = handle_act(policy, reader);
            else if (type == kExit) {
                reader.finish();
                const auto final_state = policy.state_sha256();
                if (final_state != initial_state) throw std::runtime_error("read-only evaluator mutated model state");
                Writer writer;
                writer.string(policy.package_id());
                writer.string(final_state);
                send_response(STDOUT_FILENO, type, 0, writer.data());
                return 0;
            } else throw std::invalid_argument("unknown M09 evaluator request type");
            send_response(STDOUT_FILENO, type, 0, response);
        } catch (const std::exception &error) {
            Writer writer;
            writer.string(error.what());
            send_response(STDOUT_FILENO, type, 1, writer.data());
        }
    }
}

std::uint64_t parse_u64(std::string_view text)
{
    std::uint64_t value = 0;
    const auto result = std::from_chars(text.data(), text.data() + text.size(), value);
    if (result.ec != std::errc{} || result.ptr != text.data() + text.size()) {
        throw std::invalid_argument("invalid sampling seed");
    }
    return value;
}

} // namespace

int main(int argc, char **argv)
{
    try {
        std::filesystem::path package;
        std::uint64_t sampling_seed = 0;
        bool has_seed = false;
        for (int index = 1; index < argc; index += 2) {
            if (index + 1 >= argc) throw std::invalid_argument("evaluator option is missing its value");
            const std::string_view option(argv[index]);
            const std::string_view value(argv[index + 1]);
            if (option == "--package") package = value;
            else if (option == "--sampling-seed") {
                sampling_seed = parse_u64(value);
                has_seed = true;
            } else throw std::invalid_argument("unknown evaluator option: " + std::string(option));
        }
        if (!package.is_absolute() || !has_seed) throw std::invalid_argument("absolute package and sampling seed are required");
        torch::set_num_threads(6);
        openttd_rl::training::ReadOnlyEvaluationPolicy policy(package, sampling_seed);
        return run_service(policy);
    } catch (const std::exception &error) {
        std::cerr << "M09_EVALUATOR=FAIL " << error.what() << '\n';
        return 1;
    }
}
