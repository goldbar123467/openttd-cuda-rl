#include <array>
#include <bit>
#include <cerrno>
#include <charconv>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <unistd.h>
#include <vector>

#include "openttd_rl/deployment/deployment_model.h"

namespace {

constexpr std::array<char, 8> kRequestMagic = {'O', 'T', 'R', 'L', 'D', 'S', '0', '1'};
constexpr std::array<char, 8> kResponseMagic = {'O', 'T', 'R', 'L', 'D', 'R', '0', '1'};
constexpr std::uint32_t kInspect = 2;
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
        if (value.size() > 65535U) throw std::length_error("deployment string exceeds bound");
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
        for (unsigned int index = 0; index < 4U; ++index) value |= static_cast<std::uint32_t>(data_[offset_++]) << (index * 8U);
        return value;
    }
    float f32() { return std::bit_cast<float>(u32()); }
    void finish() const
    {
        if (offset_ != data_.size()) throw std::invalid_argument("deployment request has trailing bytes");
    }

private:
    void require(std::size_t size) const
    {
        if (size > data_.size() - offset_) throw std::invalid_argument("deployment request is truncated");
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
        if (result < 0) throw std::runtime_error("deployment evaluator read failed: " + std::string(std::strerror(errno)));
        if (result == 0) {
            if (received == 0) return false;
            throw std::runtime_error("deployment evaluator frame was truncated");
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
        if (result <= 0) throw std::runtime_error("deployment evaluator write failed: " + std::string(std::strerror(errno)));
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

void send_response(std::uint32_t type, std::uint32_t status, const std::vector<std::uint8_t> &payload)
{
    std::array<std::uint8_t, 24> header{};
    std::memcpy(header.data(), kResponseMagic.data(), kResponseMagic.size());
    for (unsigned int index = 0; index < 4U; ++index) {
        header[8U + index] = static_cast<std::uint8_t>(type >> (index * 8U));
        header[12U + index] = static_cast<std::uint8_t>(status >> (index * 8U));
    }
    const auto length = static_cast<std::uint64_t>(payload.size());
    for (unsigned int index = 0; index < 8U; ++index) header[16U + index] = static_cast<std::uint8_t>(length >> (index * 8U));
    write_exact(STDOUT_FILENO, header.data(), header.size());
    if (!payload.empty()) write_exact(STDOUT_FILENO, payload.data(), payload.size());
}

std::vector<std::uint8_t> handle_inspect(
    openttd_rl::deployment::DeploymentPolicy &policy,
    openttd_rl::deployment::InGamePolicyAdapter *adapter,
    Reader &reader)
{
    const auto batch = static_cast<std::size_t>(reader.u32());
    if (batch == 0 || batch > 64U) throw std::invalid_argument("deployment INSPECT batch is outside [1,64]");
    const auto deterministic = reader.u8();
    if (deterministic > 1U) throw std::invalid_argument("deployment INSPECT mode is not boolean");
    std::vector<float> structured(batch * openttd_rl::deployment::kStructuredFeatures);
    std::vector<float> spatial(batch * openttd_rl::deployment::kSpatialFeatures);
    std::vector<std::uint8_t> masks(batch * openttd_rl::deployment::kActionCount);
    for (auto &value : structured) value = reader.f32();
    for (auto &value : spatial) value = reader.f32();
    for (auto &value : masks) value = reader.u8();
    reader.finish();
    const auto result = adapter == nullptr
        ? policy.inspect(structured, spatial, masks, batch, deterministic != 0U)
        : adapter->inspect(structured, spatial, masks, batch, deterministic != 0U);
    Writer writer;
    writer.u32(static_cast<std::uint32_t>(batch));
    for (std::size_t row = 0; row < batch; ++row) {
        writer.i64(result.actions[row]);
        writer.f64(result.log_probabilities[row]);
        writer.f64(result.values[row]);
        for (std::size_t action = 0; action < openttd_rl::deployment::kActionCount; ++action) {
            writer.f64(result.logits[row * openttd_rl::deployment::kActionCount + action]);
        }
        for (std::size_t action = 0; action < openttd_rl::deployment::kActionCount; ++action) {
            writer.f64(result.probabilities[row * openttd_rl::deployment::kActionCount + action]);
        }
    }
    return writer.data();
}

std::uint64_t parse_u64(std::string_view text)
{
    std::uint64_t value = 0;
    const auto result = std::from_chars(text.data(), text.data() + text.size(), value);
    if (result.ec != std::errc{} || result.ptr != text.data() + text.size()) throw std::invalid_argument("invalid deployment sampling seed");
    return value;
}

} // namespace

int main(int argc, char **argv)
{
    try {
        if constexpr (std::endian::native != std::endian::little) throw std::runtime_error("deployment evaluator requires little endian");
        std::filesystem::path package;
        std::uint64_t sampling_seed = 0;
        bool has_seed = false;
        std::string mode;
        for (int index = 1; index < argc; index += 2) {
            if (index + 1 >= argc) throw std::invalid_argument("deployment option lacks a value");
            const std::string_view option(argv[index]);
            const std::string value(argv[index + 1]);
            if (option == "--package") package = value;
            else if (option == "--sampling-seed") {
                sampling_seed = parse_u64(value);
                has_seed = true;
            } else if (option == "--mode") mode = value;
            else throw std::invalid_argument("unknown deployment option: " + std::string(option));
        }
        if (!package.is_absolute() || !has_seed || (mode != "standalone" && mode != "ingame")) {
            throw std::invalid_argument("absolute package, sampling seed, and standalone/ingame mode are required");
        }
        openttd_rl::deployment::DeploymentPolicy policy(package, sampling_seed);
        openttd_rl::deployment::InGamePolicyAdapter adapter(policy);
        while (true) {
            std::array<std::uint8_t, 20> header{};
            if (!read_exact_or_eof(STDIN_FILENO, header.data(), header.size())) return 0;
            if (std::memcmp(header.data(), kRequestMagic.data(), kRequestMagic.size()) != 0) throw std::runtime_error("deployment request magic mismatch");
            const auto type = decode_u32(header.data() + 8U);
            const auto length = decode_u64(header.data() + 12U);
            if (length > kMaximumFrameBytes) throw std::length_error("deployment request exceeds frame bound");
            std::vector<std::uint8_t> payload(static_cast<std::size_t>(length));
            if (!payload.empty() && !read_exact_or_eof(STDIN_FILENO, payload.data(), payload.size())) throw std::runtime_error("deployment body was truncated");
            try {
                Reader reader(payload);
                std::vector<std::uint8_t> response;
                if (type == kInspect) response = handle_inspect(policy, mode == "ingame" ? &adapter : nullptr, reader);
                else if (type == kExit) {
                    reader.finish();
                    Writer writer;
                    writer.string(policy.package_id());
                    writer.string(policy.model_sha256());
                    send_response(type, 0, writer.data());
                    return 0;
                } else throw std::invalid_argument("unknown deployment request type");
                send_response(type, 0, response);
            } catch (const std::exception &error) {
                Writer writer;
                writer.string(error.what());
                send_response(type, 1, writer.data());
            }
        }
    } catch (const std::exception &error) {
        std::cerr << "M10_ONNX_EVALUATOR=FAIL " << error.what() << '\n';
        return 1;
    }
}
