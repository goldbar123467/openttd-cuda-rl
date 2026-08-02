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

#include "openttd_rl/training/checkpoint.h"
#include "openttd_rl/training/evaluation_model.h"
#include "openttd_rl/training/multimodal_trainer.h"

namespace {

constexpr std::array<char, 8> kRequestMagic = {'O', 'T', 'R', 'L', 'M', 'S', '0', '1'};
constexpr std::array<char, 8> kResponseMagic = {'O', 'T', 'R', 'L', 'M', 'R', '0', '1'};
constexpr std::uint32_t kAct = 1;
constexpr std::uint32_t kUpdate = 2;
constexpr std::uint32_t kExport = 3;
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
        if (value.size() > 65535U) throw std::length_error("service string exceeds bound");
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
    std::uint64_t u64()
    {
        require(8);
        std::uint64_t value = 0;
        for (unsigned int index = 0; index < 8U; ++index) {
            value |= static_cast<std::uint64_t>(data_[offset_++]) << (index * 8U);
        }
        return value;
    }
    std::int64_t i64() { return std::bit_cast<std::int64_t>(u64()); }
    double f64() { return std::bit_cast<double>(u64()); }
    float f32() { return std::bit_cast<float>(u32()); }
    std::string string(std::size_t maximum = 65536U)
    {
        const auto length = static_cast<std::size_t>(u32());
        if (length > maximum) throw std::length_error("service string exceeds bound");
        require(length);
        std::string value(reinterpret_cast<const char *>(data_.data() + offset_), length);
        offset_ += length;
        return value;
    }
    void finish() const
    {
        if (offset_ != data_.size()) throw std::invalid_argument("service request has trailing bytes");
    }

private:
    void require(std::size_t size) const
    {
        if (size > data_.size() - offset_) throw std::invalid_argument("service request is truncated");
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
        if (result < 0) throw std::runtime_error("M08 trainer read failed: " + std::string(std::strerror(errno)));
        if (result == 0) {
            if (received == 0) return false;
            throw std::runtime_error("M08 trainer frame header was truncated");
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
        if (result <= 0) throw std::runtime_error("M08 trainer write failed: " + std::string(std::strerror(errno)));
        written += static_cast<std::size_t>(result);
    }
}

std::uint32_t decode_u32(const std::uint8_t *bytes)
{
    std::uint32_t value = 0;
    for (unsigned int index = 0; index < 4U; ++index) {
        value |= static_cast<std::uint32_t>(bytes[index]) << (index * 8U);
    }
    return value;
}

std::uint64_t decode_u64(const std::uint8_t *bytes)
{
    std::uint64_t value = 0;
    for (unsigned int index = 0; index < 8U; ++index) {
        value |= static_cast<std::uint64_t>(bytes[index]) << (index * 8U);
    }
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
    for (unsigned int index = 0; index < 8U; ++index) {
        header[16U + index] = static_cast<std::uint8_t>(length >> (index * 8U));
    }
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
        {samples,
            openttd_rl::training::kSpatialChannels,
            openttd_rl::training::kSpatialHeight,
            openttd_rl::training::kSpatialWidth},
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
            if (value > 1U) throw std::invalid_argument("service action mask is not boolean");
            view[sample][action] = value != 0U;
        }
    }
    return result;
}

std::vector<std::uint8_t> handle_act(openttd_rl::training::MultiModalPpoTrainer &trainer, Reader &reader)
{
    const auto samples = static_cast<std::int64_t>(reader.u32());
    if (samples <= 0 || samples > 64) throw std::invalid_argument("service ACT batch is outside [1,64]");
    const auto deterministic = reader.u8();
    if (deterministic > 1U) throw std::invalid_argument("service ACT mode is not boolean");
    const auto structured = read_structured(reader, samples);
    const auto spatial = read_spatial(reader, samples);
    const auto masks = read_masks(reader, samples);
    reader.finish();
    const auto result = trainer.act(structured, spatial, masks, deterministic != 0U);
    const auto action_tensor = result.actions.contiguous();
    const auto log_probability_tensor = result.log_probabilities.to(torch::kFloat64).contiguous();
    const auto value_tensor = result.values.to(torch::kFloat64).contiguous();
    const auto actions = action_tensor.accessor<std::int64_t, 1>();
    const auto log_probabilities = log_probability_tensor.accessor<double, 1>();
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

std::vector<std::uint8_t> handle_update(openttd_rl::training::MultiModalPpoTrainer &trainer, Reader &reader)
{
    const auto samples = static_cast<std::int64_t>(reader.u32());
    const auto &config = trainer.config();
    if (samples != config.rollout_length * config.environment_count) {
        throw std::invalid_argument("service UPDATE sample count disagrees with trainer configuration");
    }
    auto structured = read_structured(reader, samples);
    auto spatial = read_spatial(reader, samples);
    auto masks = read_masks(reader, samples);
    auto actions = torch::empty({samples}, torch::kInt64);
    auto old_log_probabilities = torch::empty({samples}, torch::kFloat64);
    auto old_values = torch::empty({samples}, torch::kFloat64);
    auto rewards = torch::empty({samples}, torch::kFloat64);
    auto next_values = torch::empty({samples}, torch::kFloat64);
    auto bootstrap = torch::empty({samples}, torch::kFloat64);
    auto continuation = torch::empty({samples}, torch::kFloat64);
    auto action_view = actions.accessor<std::int64_t, 1>();
    auto old_log_view = old_log_probabilities.accessor<double, 1>();
    auto old_value_view = old_values.accessor<double, 1>();
    auto reward_view = rewards.accessor<double, 1>();
    auto next_value_view = next_values.accessor<double, 1>();
    auto bootstrap_view = bootstrap.accessor<double, 1>();
    auto continuation_view = continuation.accessor<double, 1>();
    for (std::int64_t sample = 0; sample < samples; ++sample) {
        action_view[sample] = reader.i64();
        old_log_view[sample] = reader.f64();
        old_value_view[sample] = reader.f64();
        reward_view[sample] = reader.f64();
        next_value_view[sample] = reader.f64();
        const auto bootstrap_value = reader.u8();
        const auto continuation_value = reader.u8();
        if (bootstrap_value > 1U || continuation_value > 1U) {
            throw std::invalid_argument("service GAE mask is not boolean");
        }
        bootstrap_view[sample] = static_cast<double>(bootstrap_value);
        continuation_view[sample] = static_cast<double>(continuation_value);
    }
    reader.finish();
    const auto shape = std::vector<std::int64_t>{config.rollout_length, config.environment_count};
    const auto gae = openttd_rl::training::compute_gae(
        rewards.reshape(shape),
        old_values.reshape(shape),
        next_values.reshape(shape),
        bootstrap.reshape(shape),
        continuation.reshape(shape),
        config.gamma,
        config.gae_lambda);
    openttd_rl::training::MultiModalRolloutBatch rollout{
        structured,
        spatial,
        masks,
        actions,
        old_log_probabilities,
        old_values,
        openttd_rl::training::normalize_advantages(gae.advantages).reshape({samples}).to(torch::kFloat32),
        gae.returns.reshape({samples}).to(torch::kFloat32),
    };
    const auto metrics = trainer.update(rollout);
    Writer writer;
    writer.f64(metrics.policy_loss);
    writer.f64(metrics.value_loss);
    writer.f64(metrics.entropy);
    writer.f64(metrics.approximate_kl);
    writer.f64(metrics.clip_fraction);
    writer.f64(metrics.gradient_norm);
    writer.f64(metrics.explained_variance);
    writer.f64(metrics.learning_rate);
    writer.u64(metrics.update);
    writer.u64(metrics.samples);
    return writer.data();
}

std::vector<std::uint8_t> handle_export(openttd_rl::training::MultiModalPpoTrainer &trainer, Reader &reader)
{
    const std::filesystem::path package_root(reader.string(4096));
    const std::string repository_commit = reader.string(64);
    const double training_mean_reward = reader.f64();
    reader.finish();
    const auto &counters = trainer.counters();
    const auto saved = openttd_rl::training::save_evaluation_model(
        package_root,
        trainer.model(),
        trainer.architecture(),
        {
            repository_commit,
            trainer.rng().ledger().run_seed,
            counters.completed_updates,
            counters.accepted_samples,
            training_mean_reward,
        });
    Writer writer;
    writer.string(saved.package_id);
    writer.string(saved.path.string());
    return writer.data();
}

int run_service(
    openttd_rl::training::MultiModalPpoTrainer &trainer,
    const std::filesystem::path &diagnostic_root)
{
    if (!diagnostic_root.is_absolute()) throw std::invalid_argument("diagnostic root must be absolute");
    if constexpr (std::endian::native != std::endian::little) {
        throw std::runtime_error("M08 trainer requires an explicitly supported little-endian host");
    }
    while (true) {
        std::array<std::uint8_t, 20> header{};
        if (!read_exact_or_eof(STDIN_FILENO, header.data(), header.size())) return 0;
        if (std::memcmp(header.data(), kRequestMagic.data(), kRequestMagic.size()) != 0) {
            throw std::runtime_error("M08 trainer request magic mismatch");
        }
        const auto type = decode_u32(header.data() + 8);
        const auto length = decode_u64(header.data() + 12);
        if (length > kMaximumFrameBytes) throw std::length_error("M08 trainer request exceeds frame bound");
        std::vector<std::uint8_t> payload(static_cast<std::size_t>(length));
        if (!payload.empty() && !read_exact_or_eof(STDIN_FILENO, payload.data(), payload.size())) {
            throw std::runtime_error("M08 trainer request body was truncated");
        }
        try {
            Reader reader(payload);
            std::vector<std::uint8_t> response;
            if (type == kAct) response = handle_act(trainer, reader);
            else if (type == kUpdate) response = handle_update(trainer, reader);
            else if (type == kExport) response = handle_export(trainer, reader);
            else if (type == kExit) {
                reader.finish();
                send_response(STDOUT_FILENO, type, 0, {});
                return 0;
            } else throw std::invalid_argument("unknown M08 trainer request type");
            send_response(STDOUT_FILENO, type, 0, response);
        } catch (const std::exception &error) {
            const bool numerical_failure = std::string_view(error.what()).find("nonfinite") != std::string_view::npos;
            std::string error_message(error.what());
            if (numerical_failure) {
                try {
                    (void)openttd_rl::training::write_numerical_diagnostic(
                        diagnostic_root,
                        trainer.counters(),
                        type == kUpdate ? "m08-trainer-update" : (type == kExport ? "m09-model-export" : "m08-trainer-act"),
                        error.what());
                } catch (const std::exception &diagnostic_error) {
                    error_message += "; diagnostic publication failed: ";
                    error_message += diagnostic_error.what();
                }
            }
            Writer writer;
            writer.string(error_message);
            send_response(STDOUT_FILENO, type, 1, writer.data());
            if (numerical_failure) return 1;
        }
    }
}

std::uint64_t parse_u64(std::string_view text, const char *name)
{
    std::uint64_t value = 0;
    const auto result = std::from_chars(text.data(), text.data() + text.size(), value);
    if (result.ec != std::errc{} || result.ptr != text.data() + text.size()) {
        throw std::invalid_argument(std::string("invalid ") + name);
    }
    return value;
}

} // namespace

int main(int argc, char **argv)
{
    try {
        openttd_rl::training::PpoConfig config;
        std::uint64_t run_seed = 0;
        bool has_seed = false;
        std::filesystem::path diagnostic_root;
        std::string architecture;
        std::string device_name;
        for (int index = 1; index < argc; index += 2) {
            if (index + 1 >= argc) throw std::invalid_argument("service option is missing its value");
            const std::string_view option(argv[index]);
            const std::string_view value(argv[index + 1]);
            if (option == "--run-seed") {
                run_seed = parse_u64(value, "run seed");
                has_seed = true;
            } else if (option == "--rollout-length") {
                config.rollout_length = static_cast<std::int64_t>(parse_u64(value, "rollout length"));
            } else if (option == "--environment-count") {
                config.environment_count = static_cast<std::int64_t>(parse_u64(value, "environment count"));
            } else if (option == "--minibatch-size") {
                config.minibatch_size = static_cast<std::int64_t>(parse_u64(value, "minibatch size"));
            } else if (option == "--optimization-epochs") {
                config.optimization_epochs = static_cast<std::int64_t>(parse_u64(value, "optimization epochs"));
            } else if (option == "--diagnostic-root") {
                diagnostic_root = value;
            } else if (option == "--architecture") {
                architecture = value;
            } else if (option == "--device") {
                device_name = value;
            } else {
                throw std::invalid_argument("unknown service option: " + std::string(option));
            }
        }
        if (!has_seed || !diagnostic_root.is_absolute() || architecture.empty() || device_name.empty()) {
            throw std::invalid_argument("run seed, diagnostic root, architecture, and device are required");
        }
        const auto kind = openttd_rl::training::parse_architecture_kind(architecture);
        torch::Device device(torch::kCPU);
        if (device_name == "cuda:0") device = torch::Device(torch::kCUDA, 0);
        else if (device_name != "cpu") throw std::invalid_argument("device must be cpu or cuda:0");
        torch::set_num_threads(device.is_cpu() ? 6 : 1);
        openttd_rl::training::MultiModalPpoTrainer trainer(config, run_seed, kind, device);
        return run_service(trainer, diagnostic_root);
    } catch (const std::exception &error) {
        std::cerr << "M08_TRAINER=FAIL " << error.what() << '\n';
        return 1;
    }
}
