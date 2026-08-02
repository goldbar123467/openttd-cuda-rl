#include "openttd_rl/training/checkpoint.h"

#include <array>
#include <atomic>
#include <bit>
#include <cerrno>
#include <chrono>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <iomanip>
#include <limits>
#include <openssl/evp.h>
#include <sstream>
#include <stdexcept>
#include <string_view>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

namespace openttd_rl::training {

namespace {

constexpr std::array<char, 8> kStateMagic = {'O', 'T', 'R', 'L', 'S', 'T', '0', '1'};
constexpr std::array<char, 8> kHeaderMagic = {'O', 'T', 'R', 'L', 'C', 'P', '0', '1'};
constexpr std::uint32_t kCheckpointVersion = 1;
constexpr std::size_t kMaximumStateBytes = 1024 * 1024;
constexpr std::size_t kMaximumPayloadBytes = 256 * 1024 * 1024;
constexpr std::string_view kBridgeSha = "4701a21ae106f6fa120db1b89c3929d16c29afafb8e0198126173137ed2af2d6";
constexpr std::string_view kObservationSha = "7f8a46af1fe2a2c23e755c71b3bc2d04c9a0d057c573e901e5c9ed9178ca13eb";
constexpr std::string_view kActionSha = "215c7d3ebeea97f1629debee4a2d10301838ccfd3085e4828685591677b58536";
constexpr std::string_view kRewardSha = "9d8f9c2fc6074d899fa3b0047c55e3fb15cc5c17cddeaceaa1fd5389e53c8c9e";

std::atomic<std::uint64_t> temporary_counter{0};

class BytesWriter {
public:
    void u8(std::uint8_t value) { data_.push_back(value); }

    void raw(const void *data, std::size_t length)
    {
        const auto *bytes = static_cast<const std::uint8_t *>(data);
        data_.insert(data_.end(), bytes, bytes + length);
    }

    void u32(std::uint32_t value)
    {
        for (unsigned int shift = 0; shift < 32U; shift += 8U) data_.push_back(static_cast<std::uint8_t>(value >> shift));
    }

    void u64(std::uint64_t value)
    {
        for (unsigned int shift = 0; shift < 64U; shift += 8U) data_.push_back(static_cast<std::uint8_t>(value >> shift));
    }

    void f64(double value) { u64(std::bit_cast<std::uint64_t>(value)); }

    void string(const std::string &value)
    {
        if (value.size() > UINT32_MAX) throw std::length_error("checkpoint string is too large");
        u32(static_cast<std::uint32_t>(value.size()));
        raw(value.data(), value.size());
    }

    [[nodiscard]] const std::vector<std::uint8_t> &data() const noexcept { return data_; }

private:
    std::vector<std::uint8_t> data_;
};

class BytesReader {
public:
    explicit BytesReader(const std::vector<std::uint8_t> &data) : data_(data) {}

    void expect(const void *expected, std::size_t length)
    {
        require(length);
        if (std::memcmp(data_.data() + offset_, expected, length) != 0) throw std::invalid_argument("checkpoint magic mismatch");
        offset_ += length;
    }

    std::uint32_t u32()
    {
        require(4);
        std::uint32_t value = 0;
        for (unsigned int index = 0; index < 4U; ++index) value |= static_cast<std::uint32_t>(data_[offset_++]) << (index * 8U);
        return value;
    }

    std::uint64_t u64()
    {
        require(8);
        std::uint64_t value = 0;
        for (unsigned int index = 0; index < 8U; ++index) value |= static_cast<std::uint64_t>(data_[offset_++]) << (index * 8U);
        return value;
    }

    double f64() { return std::bit_cast<double>(u64()); }

    std::string string(std::size_t maximum = 65536)
    {
        const auto length = static_cast<std::size_t>(u32());
        if (length > maximum) throw std::length_error("checkpoint string exceeds bound");
        require(length);
        std::string value(reinterpret_cast<const char *>(data_.data() + offset_), length);
        offset_ += length;
        return value;
    }

    std::array<std::uint8_t, 32> digest()
    {
        std::array<std::uint8_t, 32> result{};
        require(result.size());
        std::memcpy(result.data(), data_.data() + offset_, result.size());
        offset_ += result.size();
        return result;
    }

    void finish() const
    {
        if (offset_ != data_.size()) throw std::invalid_argument("checkpoint has trailing bytes");
    }

private:
    void require(std::size_t length) const
    {
        if (length > data_.size() - offset_) throw std::invalid_argument("checkpoint is truncated");
    }

    const std::vector<std::uint8_t> &data_;
    std::size_t offset_{};
};

std::array<std::uint8_t, 32> sha256_bytes(const void *data, std::size_t length)
{
    std::array<std::uint8_t, 32> digest{};
    auto *context = EVP_MD_CTX_new();
    if (context == nullptr) throw std::runtime_error("cannot allocate SHA-256 context");
    const bool ok = EVP_DigestInit_ex(context, EVP_sha256(), nullptr) == 1 &&
        EVP_DigestUpdate(context, data, length) == 1;
    unsigned int digest_length = 0;
    const bool final_ok = ok && EVP_DigestFinal_ex(context, digest.data(), &digest_length) == 1;
    EVP_MD_CTX_free(context);
    if (!final_ok || digest_length != digest.size()) throw std::runtime_error("SHA-256 failed");
    return digest;
}

std::string hex_digest(const std::array<std::uint8_t, 32> &digest)
{
    std::ostringstream output;
    output << std::hex << std::setfill('0');
    for (const auto byte : digest) output << std::setw(2) << static_cast<unsigned int>(byte);
    return output.str();
}

std::array<std::uint8_t, 32> parse_digest(std::string_view text)
{
    if (text.size() != 64) throw std::invalid_argument("invalid SHA-256 text");
    std::array<std::uint8_t, 32> result{};
    for (std::size_t index = 0; index < result.size(); ++index) {
        const auto pair = text.substr(index * 2, 2);
        unsigned int value = 0;
        std::istringstream stream{std::string(pair)};
        stream >> std::hex >> value;
        if (!stream || !stream.eof() || value > 255U) throw std::invalid_argument("invalid SHA-256 text");
        result[index] = static_cast<std::uint8_t>(value);
    }
    return result;
}

std::vector<std::uint8_t> read_bounded(const std::filesystem::path &path, std::size_t maximum)
{
    const auto size = std::filesystem::file_size(path);
    if (size > maximum) throw std::length_error("checkpoint file exceeds bound: " + path.string());
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("cannot read checkpoint file: " + path.string());
    std::vector<std::uint8_t> data(static_cast<std::size_t>(size));
    if (!data.empty()) input.read(reinterpret_cast<char *>(data.data()), static_cast<std::streamsize>(data.size()));
    if (!input || input.peek() != std::ifstream::traits_type::eof()) throw std::runtime_error("cannot read exact checkpoint file");
    return data;
}

std::array<std::uint8_t, 32> sha256_file(const std::filesystem::path &path, std::size_t maximum)
{
    const auto data = read_bounded(path, maximum);
    return sha256_bytes(data.data(), data.size());
}

void write_exact(const std::filesystem::path &path, const void *data, std::size_t length)
{
    const int descriptor = ::open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, S_IRUSR | S_IWUSR | S_IRGRP | S_IROTH);
    if (descriptor < 0) throw std::runtime_error("cannot create checkpoint file: " + std::string(std::strerror(errno)));
    const auto *bytes = static_cast<const std::uint8_t *>(data);
    std::size_t written = 0;
    try {
        while (written < length) {
            const auto result = ::write(descriptor, bytes + written, length - written);
            if (result < 0 && errno == EINTR) continue;
            if (result <= 0) throw std::runtime_error("cannot write checkpoint file");
            written += static_cast<std::size_t>(result);
        }
        if (::fsync(descriptor) != 0) throw std::runtime_error("cannot sync checkpoint file");
    } catch (...) {
        (void)::close(descriptor);
        throw;
    }
    if (::close(descriptor) != 0) throw std::runtime_error("cannot close checkpoint file");
}

void sync_existing_file(const std::filesystem::path &path)
{
    const int descriptor = ::open(path.c_str(), O_RDONLY | O_CLOEXEC);
    if (descriptor < 0) throw std::runtime_error("cannot reopen checkpoint payload for sync");
    const int result = ::fsync(descriptor);
    const int saved_errno = errno;
    (void)::close(descriptor);
    if (result != 0) throw std::runtime_error("cannot sync checkpoint payload: " + std::string(std::strerror(saved_errno)));
}

void sync_directory(const std::filesystem::path &path)
{
    const int descriptor = ::open(path.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (descriptor < 0) throw std::runtime_error("cannot open checkpoint directory for sync");
    const int result = ::fsync(descriptor);
    const int saved_errno = errno;
    (void)::close(descriptor);
    if (result != 0) throw std::runtime_error("cannot sync checkpoint directory: " + std::string(std::strerror(saved_errno)));
}

std::string json_escape(const std::string &value)
{
    std::ostringstream output;
    output << '"';
    for (const char character : value) {
        const auto byte = static_cast<unsigned char>(character);
        if (byte == '"') output << "\\\"";
        else if (byte == '\\') output << "\\\\";
        else if (byte == '\n') output << "\\n";
        else if (byte == '\r') output << "\\r";
        else if (byte == '\t') output << "\\t";
        else if (byte < 0x20U) {
            output << "\\u00" << std::hex << std::setw(2) << std::setfill('0') << static_cast<unsigned int>(byte) << std::dec;
        } else output << static_cast<char>(byte);
    }
    output << '"';
    return output.str();
}

struct StateData {
    PpoConfig config;
    SeedLedger ledger;
    std::array<std::string, 3> rng_states;
    TrainerCounters counters;
    CheckpointProvenance provenance;
};

std::vector<std::uint8_t> encode_state(PpoTrainer &trainer, const CheckpointProvenance &provenance)
{
    BytesWriter writer;
    writer.raw(kStateMagic.data(), kStateMagic.size());
    writer.u32(kCheckpointVersion);
    const auto &config = trainer.config();
    writer.f64(config.gamma);
    writer.f64(config.gae_lambda);
    writer.f64(config.clip_epsilon);
    writer.f64(config.value_coefficient);
    writer.f64(config.entropy_coefficient);
    writer.f64(config.learning_rate);
    writer.f64(config.adam_epsilon);
    writer.f64(config.max_gradient_norm);
    writer.u64(static_cast<std::uint64_t>(config.rollout_length));
    writer.u64(static_cast<std::uint64_t>(config.environment_count));
    writer.u64(static_cast<std::uint64_t>(config.minibatch_size));
    writer.u64(static_cast<std::uint64_t>(config.optimization_epochs));
    const auto &ledger = trainer.rng().ledger();
    writer.u64(ledger.run_seed);
    for (const auto seed : ledger.stream_seeds) writer.u64(seed);
    for (const auto &state : trainer.rng().mutable_states()) writer.string(state);
    const auto &counters = trainer.counters();
    writer.u64(counters.completed_updates);
    writer.u64(counters.environment_steps);
    writer.u64(counters.simulation_ticks);
    writer.u64(counters.completed_episodes);
    writer.u64(counters.accepted_samples);
    writer.string(provenance.run_name);
    writer.string(provenance.repository_commit);
    writer.string(provenance.source_build_identity);
    writer.string(provenance.parent_checkpoint);
    if (writer.data().size() > kMaximumStateBytes) throw std::length_error("checkpoint state exceeds bound");
    return writer.data();
}

StateData decode_state(const std::vector<std::uint8_t> &data)
{
    BytesReader reader(data);
    reader.expect(kStateMagic.data(), kStateMagic.size());
    if (reader.u32() != kCheckpointVersion) throw std::invalid_argument("unsupported checkpoint state version");
    StateData result;
    result.config.gamma = reader.f64();
    result.config.gae_lambda = reader.f64();
    result.config.clip_epsilon = reader.f64();
    result.config.value_coefficient = reader.f64();
    result.config.entropy_coefficient = reader.f64();
    result.config.learning_rate = reader.f64();
    result.config.adam_epsilon = reader.f64();
    result.config.max_gradient_norm = reader.f64();
    const auto read_count = [&reader](const char *name) {
        const auto value = reader.u64();
        if (value > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max())) {
            throw std::invalid_argument(std::string("checkpoint ") + name + " overflows int64");
        }
        return static_cast<std::int64_t>(value);
    };
    result.config.rollout_length = read_count("rollout length");
    result.config.environment_count = read_count("environment count");
    result.config.minibatch_size = read_count("minibatch size");
    result.config.optimization_epochs = read_count("optimization epochs");
    result.config.validate();
    result.ledger.run_seed = reader.u64();
    for (auto &seed : result.ledger.stream_seeds) seed = reader.u64();
    for (auto &state : result.rng_states) state = reader.string();
    result.counters.completed_updates = reader.u64();
    result.counters.environment_steps = reader.u64();
    result.counters.simulation_ticks = reader.u64();
    result.counters.completed_episodes = reader.u64();
    result.counters.accepted_samples = reader.u64();
    result.provenance.run_name = reader.string(4096);
    result.provenance.repository_commit = reader.string(256);
    result.provenance.source_build_identity = reader.string(256);
    result.provenance.parent_checkpoint = reader.string(64);
    reader.finish();
    for (std::size_t index = 0; index < result.ledger.stream_seeds.size(); ++index) {
        if (result.ledger.stream_seeds[index] != derive_stream_seed(result.ledger.run_seed, kRngStreamNames[index])) {
            throw std::invalid_argument("checkpoint seed ledger is inconsistent");
        }
    }
    return result;
}

struct HeaderData {
    std::array<std::uint8_t, 32> model_sha{};
    std::array<std::uint8_t, 32> optimizer_payload_sha{};
    std::array<std::uint8_t, 32> optimizer_semantic_sha{};
    std::array<std::uint8_t, 32> state_sha{};
};

void encode_tensor(BytesWriter &writer, const torch::Tensor &tensor)
{
    if (!tensor.defined() || tensor.device().is_cuda()) throw std::invalid_argument("optimizer state tensor is undefined or not CPU");
    const auto contiguous = tensor.contiguous();
    require_finite_tensor(contiguous, "optimizer state");
    writer.u32(static_cast<std::uint32_t>(contiguous.scalar_type()));
    writer.u32(static_cast<std::uint32_t>(contiguous.dim()));
    for (const auto size : contiguous.sizes()) {
        if (size < 0) throw std::invalid_argument("optimizer tensor has a negative shape");
        writer.u64(static_cast<std::uint64_t>(size));
    }
    const auto byte_count = static_cast<std::uint64_t>(contiguous.nbytes());
    writer.u64(byte_count);
    writer.raw(contiguous.const_data_ptr(), static_cast<std::size_t>(byte_count));
}

std::array<std::uint8_t, 32> optimizer_semantic_sha256(PpoTrainer &trainer)
{
    BytesWriter writer;
    writer.raw("ADAMSEM1", 8);
    const auto &groups = trainer.optimizer().param_groups();
    if (groups.size() != 1) throw std::invalid_argument("M07 Adam checkpoint requires exactly one parameter group");
    const auto &parameters = groups[0].params();
    if (parameters.size() > UINT32_MAX) throw std::length_error("optimizer parameter count exceeds bound");
    writer.u32(static_cast<std::uint32_t>(parameters.size()));
    const auto &states = trainer.optimizer().state();
    for (std::size_t index = 0; index < parameters.size(); ++index) {
        writer.u32(static_cast<std::uint32_t>(index));
        const auto found = states.find(parameters[index].unsafeGetTensorImpl());
        if (found == states.end()) {
            writer.u8(0);
            continue;
        }
        writer.u8(1);
        const auto *state = dynamic_cast<const torch::optim::AdamParamState *>(found->second.get());
        if (state == nullptr || state->step() < 0) throw std::invalid_argument("optimizer contains invalid Adam state");
        writer.u64(static_cast<std::uint64_t>(state->step()));
        encode_tensor(writer, state->exp_avg());
        encode_tensor(writer, state->exp_avg_sq());
        writer.u8(state->max_exp_avg_sq().defined() ? 1U : 0U);
        if (state->max_exp_avg_sq().defined()) encode_tensor(writer, state->max_exp_avg_sq());
    }
    writer.f64(trainer.config().learning_rate);
    writer.f64(trainer.config().adam_epsilon);
    writer.f64(0.9);
    writer.f64(0.999);
    writer.f64(0.0);
    writer.u8(0);
    return sha256_bytes(writer.data().data(), writer.data().size());
}

std::vector<std::uint8_t> encode_header(const HeaderData &header)
{
    BytesWriter writer;
    writer.raw(kHeaderMagic.data(), kHeaderMagic.size());
    writer.u32(kCheckpointVersion);
    writer.raw(header.model_sha.data(), header.model_sha.size());
    writer.raw(header.optimizer_payload_sha.data(), header.optimizer_payload_sha.size());
    writer.raw(header.optimizer_semantic_sha.data(), header.optimizer_semantic_sha.size());
    writer.raw(header.state_sha.data(), header.state_sha.size());
    for (const auto digest : {std::string_view(kPpoCompatibilitySha256), kBridgeSha, kObservationSha, kActionSha, kRewardSha}) {
        const auto bytes = parse_digest(digest);
        writer.raw(bytes.data(), bytes.size());
    }
    writer.string(kArchitectureId);
    writer.string("2.13.0+cu130");
    return writer.data();
}

HeaderData decode_header(const std::vector<std::uint8_t> &data)
{
    BytesReader reader(data);
    reader.expect(kHeaderMagic.data(), kHeaderMagic.size());
    if (reader.u32() != kCheckpointVersion) throw std::invalid_argument("unsupported checkpoint header version");
    HeaderData result{reader.digest(), reader.digest(), reader.digest(), reader.digest()};
    for (const auto expected : {std::string_view(kPpoCompatibilitySha256), kBridgeSha, kObservationSha, kActionSha, kRewardSha}) {
        if (reader.digest() != parse_digest(expected)) throw std::invalid_argument("checkpoint compatibility identity mismatch");
    }
    if (reader.string(128) != kArchitectureId) throw std::invalid_argument("checkpoint architecture mismatch");
    if (reader.string(128) != "2.13.0+cu130") throw std::invalid_argument("checkpoint LibTorch version mismatch");
    reader.finish();
    return result;
}

std::vector<std::uint8_t> encode_checkpoint_identity(const HeaderData &header)
{
    BytesWriter writer;
    writer.raw("OTRLID01", 8);
    writer.u32(kCheckpointVersion);
    writer.raw(header.model_sha.data(), header.model_sha.size());
    writer.raw(header.optimizer_semantic_sha.data(), header.optimizer_semantic_sha.size());
    writer.raw(header.state_sha.data(), header.state_sha.size());
    for (const auto digest : {std::string_view(kPpoCompatibilitySha256), kBridgeSha, kObservationSha, kActionSha, kRewardSha}) {
        const auto bytes = parse_digest(digest);
        writer.raw(bytes.data(), bytes.size());
    }
    writer.string(kArchitectureId);
    writer.string("2.13.0+cu130");
    return writer.data();
}

std::string manifest_json(
    const std::string &checkpoint_id,
    const HeaderData &header,
    const StateData &state)
{
    std::ostringstream output;
    output << "{\"architecture_id\":\"" << kArchitectureId
           << "\",\"checkpoint_id\":\"" << checkpoint_id
           << "\",\"completed_updates\":" << state.counters.completed_updates
           << ",\"environment_steps\":" << state.counters.environment_steps
           << ",\"format\":\"openttd-rl-native-checkpoint-v1\""
           << ",\"model_sha256\":\"" << hex_digest(header.model_sha)
           << "\",\"optimizer_payload_sha256\":\"" << hex_digest(header.optimizer_payload_sha)
           << "\",\"optimizer_semantic_sha256\":\"" << hex_digest(header.optimizer_semantic_sha)
           << "\",\"parent_checkpoint\":" << json_escape(state.provenance.parent_checkpoint)
           << ",\"ppo_compatibility_sha256\":\"" << kPpoCompatibilitySha256
           << "\",\"repository_commit\":" << json_escape(state.provenance.repository_commit)
           << ",\"run_name\":" << json_escape(state.provenance.run_name)
           << ",\"state_sha256\":\"" << hex_digest(header.state_sha) << "\"}";
    return output.str();
}

std::filesystem::path make_temporary_directory(const std::filesystem::path &root, const char *prefix)
{
    if (!root.is_absolute()) throw std::invalid_argument("checkpoint artifact root must be absolute");
    std::filesystem::create_directories(root);
    for (unsigned int attempt = 0; attempt < 100U; ++attempt) {
        const auto sequence = temporary_counter.fetch_add(1);
        auto path = root / (std::string(".") + prefix + "-tmp-" + std::to_string(::getpid()) + "-" + std::to_string(sequence));
        std::error_code error;
        if (std::filesystem::create_directory(path, error)) return path;
        if (error && error != std::errc::file_exists) throw std::filesystem::filesystem_error("cannot create temporary artifact", path, error);
    }
    throw std::runtime_error("cannot allocate unique temporary artifact directory");
}

} // namespace

SavedCheckpoint save_checkpoint(
    const std::filesystem::path &checkpoint_root,
    PpoTrainer &trainer,
    const CheckpointProvenance &provenance)
{
    trainer.config().validate();
    require_finite_model(trainer.model(), "checkpoint");
    const auto temporary = make_temporary_directory(checkpoint_root, "checkpoint");
    try {
        const auto model_path = temporary / "model.pt";
        const auto optimizer_path = temporary / "optimizer.pt";
        const auto state_path = temporary / "state.bin";
        torch::save(trainer.model(), model_path.string());
        torch::save(trainer.optimizer(), optimizer_path.string());
        sync_existing_file(model_path);
        sync_existing_file(optimizer_path);
        const auto state_bytes = encode_state(trainer, provenance);
        write_exact(state_path, state_bytes.data(), state_bytes.size());
        HeaderData header{
            sha256_file(model_path, kMaximumPayloadBytes),
            sha256_file(optimizer_path, kMaximumPayloadBytes),
            optimizer_semantic_sha256(trainer),
            sha256_bytes(state_bytes.data(), state_bytes.size()),
        };
        const auto header_bytes = encode_header(header);
        const auto identity_bytes = encode_checkpoint_identity(header);
        const auto checkpoint_id = hex_digest(sha256_bytes(identity_bytes.data(), identity_bytes.size()));
        write_exact(temporary / "checkpoint.header", header_bytes.data(), header_bytes.size());
        const auto state = decode_state(state_bytes);
        const auto manifest = manifest_json(checkpoint_id, header, state);
        write_exact(temporary / "manifest.json", manifest.data(), manifest.size());
        sync_directory(temporary);
        const auto target = checkpoint_root / checkpoint_id;
        if (std::filesystem::exists(target)) throw std::runtime_error("checkpoint identity already exists; never overwriting");
        std::filesystem::rename(temporary, target);
        sync_directory(checkpoint_root);
        return {checkpoint_id, target};
    } catch (...) {
        std::error_code ignored;
        std::filesystem::remove_all(temporary, ignored);
        throw;
    }
}

LoadedCheckpoint load_checkpoint(const std::filesystem::path &checkpoint_path)
{
    if (!checkpoint_path.is_absolute() || !std::filesystem::is_directory(checkpoint_path)) {
        throw std::invalid_argument("checkpoint path must be an absolute directory");
    }
    const auto header_bytes = read_bounded(checkpoint_path / "checkpoint.header", 4096);
    const auto header = decode_header(header_bytes);
    const auto identity_bytes = encode_checkpoint_identity(header);
    const auto checkpoint_id = hex_digest(sha256_bytes(identity_bytes.data(), identity_bytes.size()));
    if (checkpoint_path.filename() != checkpoint_id) throw std::invalid_argument("checkpoint directory identity mismatch");
    if (sha256_file(checkpoint_path / "model.pt", kMaximumPayloadBytes) != header.model_sha ||
        sha256_file(checkpoint_path / "optimizer.pt", kMaximumPayloadBytes) != header.optimizer_payload_sha) {
        throw std::invalid_argument("checkpoint tensor payload digest mismatch");
    }
    const auto state_bytes = read_bounded(checkpoint_path / "state.bin", kMaximumStateBytes);
    if (sha256_bytes(state_bytes.data(), state_bytes.size()) != header.state_sha) {
        throw std::invalid_argument("checkpoint state payload digest mismatch");
    }
    const auto state = decode_state(state_bytes);
    const auto expected_manifest = manifest_json(checkpoint_id, header, state);
    const auto manifest = read_bounded(checkpoint_path / "manifest.json", 65536);
    if (std::string(manifest.begin(), manifest.end()) != expected_manifest) {
        throw std::invalid_argument("checkpoint manifest is not exact canonical metadata");
    }

    auto trainer = std::make_unique<PpoTrainer>(state.config, state.ledger.run_seed);
    torch::load(trainer->model(), (checkpoint_path / "model.pt").string());
    require_finite_model(trainer->model(), "loaded checkpoint");
    torch::load(trainer->optimizer(), (checkpoint_path / "optimizer.pt").string());
    if (optimizer_semantic_sha256(*trainer) != header.optimizer_semantic_sha) {
        throw std::invalid_argument("checkpoint optimizer semantic state mismatch");
    }
    trainer->rng().restore_mutable_states(state.rng_states);
    trainer->counters() = state.counters;
    return {checkpoint_id, state.provenance, std::move(trainer)};
}

std::filesystem::path write_numerical_diagnostic(
    const std::filesystem::path &artifact_root,
    const TrainerCounters &counters,
    const std::string &stage,
    const std::string &message)
{
    const auto temporary = make_temporary_directory(artifact_root, "diagnostic");
    try {
        const auto timestamp = static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::system_clock::now().time_since_epoch()).count());
        std::ostringstream output;
        output << "{\"completed_updates\":" << counters.completed_updates
               << ",\"environment_steps\":" << counters.environment_steps
               << ",\"format\":\"openttd-rl-numerical-diagnostic-v1\""
               << ",\"message\":" << json_escape(message)
               << ",\"normal_checkpoint_published\":false"
               << ",\"stage\":" << json_escape(stage)
               << ",\"unix_time_ns\":" << timestamp << '}';
        const auto payload = output.str();
        write_exact(temporary / "diagnostic.json", payload.data(), payload.size());
        sync_directory(temporary);
        const auto identity = hex_digest(sha256_bytes(payload.data(), payload.size()));
        const auto target = artifact_root / ("diagnostic-" + identity);
        if (std::filesystem::exists(target)) throw std::runtime_error("diagnostic identity already exists");
        std::filesystem::rename(temporary, target);
        sync_directory(artifact_root);
        return target;
    } catch (...) {
        std::error_code ignored;
        std::filesystem::remove_all(temporary, ignored);
        throw;
    }
}

} // namespace openttd_rl::training
