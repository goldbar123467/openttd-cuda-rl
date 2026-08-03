#include "openttd_rl/v2/m22_checkpoint.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <bit>
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <limits>
#include <openssl/evp.h>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <sys/stat.h>
#include <unistd.h>
#include <utility>
#include <vector>

namespace openttd_rl::v2 {

namespace {

constexpr std::array<char, 8> kStateMagic = {'O', 'T', 'R', 'L', 'M', '2', '2', 'K'};
constexpr std::uint32_t kStateVersion = 1;
constexpr std::size_t kMaximumStateBytes = 2 * 1024 * 1024;
constexpr std::size_t kMaximumPayloadBytes = 1024ULL * 1024ULL * 1024ULL;
constexpr std::size_t kMaximumJsonBytes = 1024 * 1024;
constexpr std::string_view kBoundary = "after-completed-ppo-update-and-retention-check-before-next-rollout";
std::atomic<std::uint64_t> temporary_counter{0};

class BytesWriter {
public:
    void raw(const void *data, std::size_t length)
    {
        const auto *bytes = static_cast<const std::uint8_t *>(data);
        data_.insert(data_.end(), bytes, bytes + length);
    }

    void u8(std::uint8_t value) { data_.push_back(value); }

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
        if (value.size() > UINT32_MAX) throw std::length_error("M22 checkpoint string is too large");
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
        require_available(length);
        if (std::memcmp(data_.data() + offset_, expected, length) != 0) {
            throw std::invalid_argument("M22 checkpoint state magic mismatch");
        }
        offset_ += length;
    }

    std::uint8_t u8()
    {
        require_available(1);
        return data_[offset_++];
    }

    std::uint32_t u32()
    {
        std::uint32_t result = 0;
        for (unsigned int shift = 0; shift < 32U; shift += 8U) result |= static_cast<std::uint32_t>(u8()) << shift;
        return result;
    }

    std::uint64_t u64()
    {
        std::uint64_t result = 0;
        for (unsigned int shift = 0; shift < 64U; shift += 8U) result |= static_cast<std::uint64_t>(u8()) << shift;
        return result;
    }

    double f64() { return std::bit_cast<double>(u64()); }

    std::string string(std::size_t maximum)
    {
        const auto length = u32();
        if (length > maximum) throw std::length_error("M22 checkpoint string exceeds bound");
        require_available(length);
        std::string result(reinterpret_cast<const char *>(data_.data() + offset_), length);
        offset_ += length;
        return result;
    }

    void finish() const
    {
        if (offset_ != data_.size()) throw std::invalid_argument("M22 checkpoint state has trailing bytes");
    }

private:
    void require_available(std::size_t length) const
    {
        if (length > data_.size() - offset_) throw std::invalid_argument("M22 checkpoint state is truncated");
    }

    const std::vector<std::uint8_t> &data_;
    std::size_t offset_{};
};

std::vector<std::uint8_t> read_bounded(const std::filesystem::path &path, std::size_t maximum)
{
    if (!std::filesystem::is_regular_file(path) || std::filesystem::is_symlink(path)) {
        throw std::invalid_argument("M22 checkpoint payload is missing, non-regular, or a symlink");
    }
    const auto size = std::filesystem::file_size(path);
    if (size > maximum) throw std::length_error("M22 checkpoint payload exceeds bound: " + path.string());
    std::vector<std::uint8_t> data(static_cast<std::size_t>(size));
    std::ifstream input(path, std::ios::binary);
    input.read(reinterpret_cast<char *>(data.data()), static_cast<std::streamsize>(data.size()));
    if (!input || input.peek() != std::ifstream::traits_type::eof()) {
        throw std::runtime_error("cannot read exact M22 checkpoint payload");
    }
    return data;
}

std::string sha256_bytes(const void *data, std::size_t length)
{
    std::array<unsigned char, EVP_MAX_MD_SIZE> digest{};
    unsigned int digest_length = 0;
    auto *context = EVP_MD_CTX_new();
    if (context == nullptr) throw std::runtime_error("cannot allocate SHA-256 context");
    const bool success = EVP_DigestInit_ex(context, EVP_sha256(), nullptr) == 1 &&
        EVP_DigestUpdate(context, data, length) == 1 &&
        EVP_DigestFinal_ex(context, digest.data(), &digest_length) == 1;
    EVP_MD_CTX_free(context);
    if (!success || digest_length != 32) throw std::runtime_error("cannot compute SHA-256");
    static constexpr char alphabet[] = "0123456789abcdef";
    std::string result;
    result.reserve(64);
    for (unsigned int index = 0; index < digest_length; ++index) {
        result.push_back(alphabet[digest[index] >> 4U]);
        result.push_back(alphabet[digest[index] & 0x0FU]);
    }
    return result;
}

std::string sha256_file(const std::filesystem::path &path)
{
    const auto bytes = read_bounded(path, kMaximumPayloadBytes);
    return sha256_bytes(bytes.data(), bytes.size());
}

void write_new(const std::filesystem::path &path, const void *data, std::size_t length)
{
    const int descriptor = ::open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, S_IRUSR | S_IWUSR);
    if (descriptor < 0) throw std::runtime_error("cannot create M22 checkpoint file: " + std::string(std::strerror(errno)));
    try {
        std::size_t written = 0;
        while (written < length) {
            const auto result = ::write(descriptor, static_cast<const char *>(data) + written, length - written);
            if (result <= 0) throw std::runtime_error("cannot write M22 checkpoint file");
            written += static_cast<std::size_t>(result);
        }
        if (::fsync(descriptor) != 0) throw std::runtime_error("cannot sync M22 checkpoint file");
    } catch (...) {
        ::close(descriptor);
        throw;
    }
    if (::close(descriptor) != 0) throw std::runtime_error("cannot close M22 checkpoint file");
}

void write_new(const std::filesystem::path &path, const std::string &value)
{
    write_new(path, value.data(), value.size());
}

void sync_existing_file(const std::filesystem::path &path)
{
    const int descriptor = ::open(path.c_str(), O_RDONLY | O_CLOEXEC);
    if (descriptor < 0) throw std::runtime_error("cannot reopen M22 checkpoint payload");
    const int result = ::fsync(descriptor);
    const int saved_errno = errno;
    ::close(descriptor);
    if (result != 0) throw std::runtime_error("cannot sync M22 checkpoint payload: " + std::string(std::strerror(saved_errno)));
}

void sync_directory(const std::filesystem::path &path)
{
    const int descriptor = ::open(path.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (descriptor < 0) throw std::runtime_error("cannot open M22 checkpoint directory for sync");
    const int result = ::fsync(descriptor);
    const int saved_errno = errno;
    ::close(descriptor);
    if (result != 0) throw std::runtime_error("cannot sync M22 checkpoint directory: " + std::string(std::strerror(saved_errno)));
}

void validate_json(const std::string &value, const char *name)
{
    if (value.size() < 2 || value.size() > kMaximumJsonBytes || value.front() != '{' || value.back() != '}' ||
        value.find('\0') != std::string::npos || value.find('\n') != std::string::npos || value.find('\r') != std::string::npos) {
        throw std::invalid_argument(std::string(name) + " must be bounded single-line canonical JSON object text");
    }
}

void validate_campaign(const M22CampaignCheckpointState &state)
{
    for (const auto *tensor : {&state.normalization_mean, &state.normalization_variance}) {
        if (!tensor->defined() || !tensor->device().is_cpu() || tensor->scalar_type() != torch::kFloat32 ||
            tensor->sizes() != torch::IntArrayRef({kM22CompactFeatures}) || !torch::isfinite(*tensor).all().item<bool>()) {
            throw std::invalid_argument("M22 checkpoint normalization must be finite CPU float32[32]");
        }
    }
    if ((state.normalization_variance <= 0).any().item<bool>()) {
        throw std::invalid_argument("M22 checkpoint normalization variance must be positive");
    }
    if (!state.hidden_state.defined() || !state.hidden_state.device().is_cpu() ||
        state.hidden_state.scalar_type() != torch::kFloat32 ||
        state.hidden_state.sizes() != torch::IntArrayRef({8, kHiddenSize}) ||
        !torch::isfinite(state.hidden_state).all().item<bool>()) {
        throw std::invalid_argument("M22 checkpoint hidden state must be finite CPU float32[8,256]");
    }
    if (state.environment_case_cursor.size() != 8 ||
        std::any_of(state.environment_case_cursor.begin(), state.environment_case_cursor.end(), [](auto value) { return value > 16; }) ||
        state.curriculum_stage > 6 || state.retention_pass_mask >= (UINT32_C(1) << 17U) ||
        !std::isfinite(state.retention_best_accuracy) || state.retention_best_accuracy < 0.0 ||
        state.retention_best_accuracy > 1.0 || state.transition < state.normalization_count) {
        throw std::invalid_argument("M22 checkpoint campaign cursor, stage, or transition is invalid");
    }
    validate_json(state.retention_history_json, "M22 retention history");
    validate_json(state.selection_json, "M22 development selection");
}

void encode_config(BytesWriter &writer, const M22PpoConfig &config)
{
    config.validate();
    for (const auto value : {config.gamma, config.gae_lambda, config.policy_clip, config.value_clip,
             config.value_coefficient, config.entropy_coefficient, config.learning_rate,
             config.adam_epsilon, config.maximum_gradient_norm}) {
        writer.f64(value);
    }
    writer.u64(static_cast<std::uint64_t>(config.rollout_steps));
    writer.u64(static_cast<std::uint64_t>(config.parallel_environments));
    writer.u64(static_cast<std::uint64_t>(config.minibatch_size));
    writer.u64(static_cast<std::uint64_t>(config.epochs));
}

M22PpoConfig decode_config(BytesReader &reader)
{
    M22PpoConfig config;
    config.gamma = reader.f64();
    config.gae_lambda = reader.f64();
    config.policy_clip = reader.f64();
    config.value_clip = reader.f64();
    config.value_coefficient = reader.f64();
    config.entropy_coefficient = reader.f64();
    config.learning_rate = reader.f64();
    config.adam_epsilon = reader.f64();
    config.maximum_gradient_norm = reader.f64();
    const auto rollout = reader.u64();
    const auto environments = reader.u64();
    const auto minibatch = reader.u64();
    const auto epochs = reader.u64();
    if (rollout > INT64_MAX || environments > INT64_MAX || minibatch > INT64_MAX || epochs > INT64_MAX) {
        throw std::invalid_argument("M22 checkpoint PPO dimension exceeds int64");
    }
    config.rollout_steps = static_cast<std::int64_t>(rollout);
    config.parallel_environments = static_cast<std::int64_t>(environments);
    config.minibatch_size = static_cast<std::int64_t>(minibatch);
    config.epochs = static_cast<std::int64_t>(epochs);
    config.validate();
    return config;
}

std::vector<std::uint8_t> encode_state(
    const M22Trainer &trainer,
    const M22CampaignCheckpointState &campaign,
    const std::string &selection_sha)
{
    validate_campaign(campaign);
    const auto runtime = trainer.runtime_state();
    BytesWriter writer;
    writer.raw(kStateMagic.data(), kStateMagic.size());
    writer.u32(kStateVersion);
    writer.string(kM22CheckpointSchemaId);
    writer.string(kM22LearningContractSha256);
    writer.string(kM22NativeCorpusSha256);
    encode_config(writer, trainer.config());
    writer.u64(runtime.run_seed);
    writer.u8(static_cast<std::uint8_t>(runtime.architecture));
    writer.u64(runtime.counters.completed_updates);
    writer.u64(runtime.counters.accepted_transitions);
    writer.u64(runtime.counters.completed_rollouts);
    writer.string(runtime.action_rng);
    writer.string(runtime.minibatch_rng);
    writer.string(runtime.environment_rng);
    writer.string(runtime.curriculum_rng);
    writer.u64(campaign.normalization_count);
    writer.u32(campaign.curriculum_stage);
    writer.u32(campaign.retention_pass_mask);
    writer.f64(campaign.retention_best_accuracy);
    writer.u64(campaign.episode);
    writer.u64(campaign.transition);
    writer.u32(static_cast<std::uint32_t>(campaign.environment_case_cursor.size()));
    for (const auto cursor : campaign.environment_case_cursor) writer.u32(cursor);
    writer.string(campaign.retention_history_json);
    writer.string(selection_sha);
    if (writer.data().size() > kMaximumStateBytes) throw std::length_error("M22 checkpoint trainer state exceeds bound");
    return writer.data();
}

struct DecodedState {
    M22PpoConfig config;
    M22RuntimeState runtime;
    M22CampaignCheckpointState campaign;
    std::string selection_sha;
};

DecodedState decode_state(const std::vector<std::uint8_t> &data)
{
    BytesReader reader(data);
    reader.expect(kStateMagic.data(), kStateMagic.size());
    if (reader.u32() != kStateVersion || reader.string(128) != kM22CheckpointSchemaId ||
        reader.string(64) != kM22LearningContractSha256 || reader.string(64) != kM22NativeCorpusSha256) {
        throw std::invalid_argument("M22 checkpoint state compatibility mismatch");
    }
    DecodedState result;
    result.config = decode_config(reader);
    result.runtime.run_seed = reader.u64();
    const auto architecture = reader.u8();
    if (architecture > static_cast<std::uint8_t>(GeneralistArchitecture::SpecialistRouter)) {
        throw std::invalid_argument("M22 checkpoint architecture is invalid");
    }
    result.runtime.architecture = static_cast<GeneralistArchitecture>(architecture);
    result.runtime.counters.completed_updates = reader.u64();
    result.runtime.counters.accepted_transitions = reader.u64();
    result.runtime.counters.completed_rollouts = reader.u64();
    result.runtime.action_rng = reader.string(65536);
    result.runtime.minibatch_rng = reader.string(65536);
    result.runtime.environment_rng = reader.string(65536);
    result.runtime.curriculum_rng = reader.string(65536);
    result.campaign.normalization_count = reader.u64();
    result.campaign.curriculum_stage = reader.u32();
    result.campaign.retention_pass_mask = reader.u32();
    result.campaign.retention_best_accuracy = reader.f64();
    result.campaign.episode = reader.u64();
    result.campaign.transition = reader.u64();
    const auto cursor_count = reader.u32();
    if (cursor_count != 8) throw std::invalid_argument("M22 checkpoint environment cursor count drifted");
    result.campaign.environment_case_cursor.reserve(cursor_count);
    for (std::uint32_t index = 0; index < cursor_count; ++index) result.campaign.environment_case_cursor.push_back(reader.u32());
    result.campaign.retention_history_json = reader.string(kMaximumJsonBytes);
    result.selection_sha = reader.string(64);
    reader.finish();
    return result;
}

struct Manifest {
    std::string architecture;
    std::uint64_t run_seed{};
    std::string checkpoint_id;
    std::string model_sha;
    std::string optimizer_sha;
    std::string runtime_sha;
    std::string state_sha;
    std::string selection_sha;
};

std::string checkpoint_id(const Manifest &manifest)
{
    const auto identity = std::string(kM22CheckpointSchemaId) + '\n' + kM22LearningContractSha256 + '\n' +
        kM22NativeCorpusSha256 + '\n' + manifest.architecture + '\n' + std::to_string(manifest.run_seed) + '\n' +
        manifest.model_sha + '\n' + manifest.optimizer_sha + '\n' + manifest.runtime_sha + '\n' +
        manifest.state_sha + '\n' + manifest.selection_sha + '\n' + std::string(kBoundary) + '\n';
    return sha256_bytes(identity.data(), identity.size());
}

std::string manifest_text(const Manifest &manifest)
{
    return std::string("schema=") + kM22CheckpointSchemaId + "\ncontract=" + kM22LearningContractSha256 +
        "\ncorpus=" + kM22NativeCorpusSha256 + "\narchitecture=" + manifest.architecture +
        "\nrun_seed=" + std::to_string(manifest.run_seed) + "\ncheckpoint_id=" + manifest.checkpoint_id +
        "\nmodel_sha256=" + manifest.model_sha + "\noptimizer_sha256=" + manifest.optimizer_sha +
        "\nruntime_sha256=" + manifest.runtime_sha + "\ntrainer_state_sha256=" + manifest.state_sha +
        "\nselection_sha256=" + manifest.selection_sha + "\nboundary=" + std::string(kBoundary) + "\n";
}

Manifest parse_manifest(const std::filesystem::path &path)
{
    const auto bytes = read_bounded(path, 8192);
    std::istringstream input(std::string(bytes.begin(), bytes.end()));
    std::vector<std::pair<std::string, std::string>> fields;
    std::string line;
    while (std::getline(input, line)) {
        const auto separator = line.find('=');
        if (separator == std::string::npos || separator == 0) throw std::invalid_argument("M22 checkpoint manifest is malformed");
        fields.emplace_back(line.substr(0, separator), line.substr(separator + 1));
    }
    const std::array<std::string_view, 12> names = {
        "schema", "contract", "corpus", "architecture", "run_seed", "checkpoint_id", "model_sha256",
        "optimizer_sha256", "runtime_sha256", "trainer_state_sha256", "selection_sha256", "boundary",
    };
    if (fields.size() != names.size()) throw std::invalid_argument("M22 checkpoint manifest field count drifted");
    for (std::size_t index = 0; index < names.size(); ++index) {
        if (fields[index].first != names[index]) throw std::invalid_argument("M22 checkpoint manifest field order drifted");
    }
    if (fields[0].second != kM22CheckpointSchemaId || fields[1].second != kM22LearningContractSha256 ||
        fields[2].second != kM22NativeCorpusSha256 || fields[11].second != kBoundary) {
        throw std::invalid_argument("M22 checkpoint manifest compatibility mismatch");
    }
    const auto architecture = parse_generalist_architecture(fields[3].second);
    (void)architecture;
    std::uint64_t run_seed = 0;
    try {
        std::size_t consumed = 0;
        run_seed = std::stoull(fields[4].second, &consumed);
        if (consumed != fields[4].second.size()) throw std::invalid_argument("trailing");
    } catch (const std::exception &) {
        throw std::invalid_argument("M22 checkpoint run seed is malformed");
    }
    for (std::size_t index = 5; index <= 10; ++index) {
        if (fields[index].second.size() != 64 || fields[index].second.find_first_not_of("0123456789abcdef") != std::string::npos) {
            throw std::invalid_argument("M22 checkpoint digest is malformed");
        }
    }
    return {fields[3].second, run_seed, fields[5].second, fields[6].second, fields[7].second,
            fields[8].second, fields[9].second, fields[10].second};
}

void require_inventory(const std::filesystem::path &path)
{
    const std::array<std::string, 7> expected = {
        "COMMITTED", "m22.manifest", "model.pt", "optimizer.pt", "runtime.pt", "selection.json", "trainer-state.bin",
    };
    std::vector<std::string> actual;
    for (const auto &entry : std::filesystem::directory_iterator(path)) {
        if (!entry.is_regular_file() || entry.is_symlink()) throw std::invalid_argument("M22 checkpoint contains a non-regular entry");
        actual.push_back(entry.path().filename().string());
    }
    std::sort(actual.begin(), actual.end());
    if (!std::equal(actual.begin(), actual.end(), expected.begin(), expected.end())) {
        throw std::invalid_argument("M22 checkpoint file inventory mismatch");
    }
}

} // namespace

M22SavedCheckpoint save_m22_checkpoint(
    const std::filesystem::path &checkpoint_root,
    M22Trainer &trainer,
    const M22CampaignCheckpointState &campaign)
{
    validate_campaign(campaign);
    if (!checkpoint_root.is_absolute()) throw std::invalid_argument("M22 checkpoint root must be absolute");
    std::filesystem::create_directories(checkpoint_root);
    if (!std::filesystem::is_directory(checkpoint_root) || std::filesystem::is_symlink(checkpoint_root)) {
        throw std::invalid_argument("M22 checkpoint root must be a real directory");
    }
    const auto temporary = checkpoint_root / (".tmp-" + std::to_string(::getpid()) + "-" +
        std::to_string(temporary_counter.fetch_add(1)));
    if (!std::filesystem::create_directory(temporary)) throw std::runtime_error("cannot create M22 checkpoint staging directory");
    const auto original_device = trainer.device();
    bool moved = false;
    try {
        const auto selection_sha = sha256_bytes(campaign.selection_json.data(), campaign.selection_json.size());
        const auto state_bytes = encode_state(trainer, campaign, selection_sha);
        trainer.to(torch::kCPU);
        moved = true;
        const auto model_path = temporary / "model.pt";
        const auto optimizer_path = temporary / "optimizer.pt";
        const auto runtime_path = temporary / "runtime.pt";
        const auto state_path = temporary / "trainer-state.bin";
        torch::save(trainer.model(), model_path.string());
        torch::save(trainer.optimizer(), optimizer_path.string());
        torch::serialize::OutputArchive runtime;
        runtime.write("normalization_mean", campaign.normalization_mean.contiguous());
        runtime.write("normalization_variance", campaign.normalization_variance.contiguous());
        runtime.write("hidden_state", campaign.hidden_state.contiguous());
        runtime.save_to(runtime_path.string());
        write_new(state_path, state_bytes.data(), state_bytes.size());
        write_new(temporary / "selection.json", campaign.selection_json);
        sync_existing_file(model_path);
        sync_existing_file(optimizer_path);
        sync_existing_file(runtime_path);
        trainer.to(original_device);
        moved = false;
        Manifest manifest{
            std::string(generalist_architecture_name(trainer.architecture())), trainer.run_seed(), "",
            sha256_file(model_path), sha256_file(optimizer_path), sha256_file(runtime_path),
            sha256_file(state_path), selection_sha,
        };
        manifest.checkpoint_id = checkpoint_id(manifest);
        write_new(temporary / "m22.manifest", manifest_text(manifest));
        write_new(temporary / "COMMITTED", manifest.checkpoint_id + "\n");
        sync_directory(temporary);
        const auto final_path = checkpoint_root / manifest.checkpoint_id;
        if (std::filesystem::exists(final_path)) throw std::runtime_error("M22 checkpoint already exists; never overwriting");
        std::filesystem::rename(temporary, final_path);
        sync_directory(checkpoint_root);
        return {manifest.checkpoint_id, final_path};
    } catch (...) {
        if (moved) {
            try {
                trainer.to(original_device);
            } catch (...) {
            }
        }
        std::error_code error;
        std::filesystem::remove_all(temporary, error);
        throw;
    }
}

M22LoadedCheckpoint load_m22_checkpoint(
    const std::filesystem::path &checkpoint_path,
    const torch::Device &policy_device)
{
    if (!checkpoint_path.is_absolute() || !std::filesystem::is_directory(checkpoint_path) ||
        std::filesystem::is_symlink(checkpoint_path)) {
        throw std::invalid_argument("M22 checkpoint path must be an absolute real directory");
    }
    require_inventory(checkpoint_path);
    const auto manifest = parse_manifest(checkpoint_path / "m22.manifest");
    if (checkpoint_path.filename() != manifest.checkpoint_id || checkpoint_id(manifest) != manifest.checkpoint_id) {
        throw std::invalid_argument("M22 checkpoint identity mismatch");
    }
    const auto committed = read_bounded(checkpoint_path / "COMMITTED", 128);
    if (std::string(committed.begin(), committed.end()) != manifest.checkpoint_id + "\n") {
        throw std::invalid_argument("M22 checkpoint commit marker mismatch");
    }
    if (sha256_file(checkpoint_path / "model.pt") != manifest.model_sha ||
        sha256_file(checkpoint_path / "optimizer.pt") != manifest.optimizer_sha ||
        sha256_file(checkpoint_path / "runtime.pt") != manifest.runtime_sha ||
        sha256_file(checkpoint_path / "trainer-state.bin") != manifest.state_sha ||
        sha256_file(checkpoint_path / "selection.json") != manifest.selection_sha) {
        throw std::invalid_argument("M22 checkpoint payload digest mismatch");
    }
    auto decoded = decode_state(read_bounded(checkpoint_path / "trainer-state.bin", kMaximumStateBytes));
    const auto selection = read_bounded(checkpoint_path / "selection.json", kMaximumJsonBytes);
    decoded.campaign.selection_json.assign(selection.begin(), selection.end());
    if (sha256_bytes(selection.data(), selection.size()) != decoded.selection_sha || decoded.selection_sha != manifest.selection_sha) {
        throw std::invalid_argument("M22 checkpoint selection identity mismatch");
    }
    torch::serialize::InputArchive runtime;
    runtime.load_from((checkpoint_path / "runtime.pt").string());
    runtime.read("normalization_mean", decoded.campaign.normalization_mean);
    runtime.read("normalization_variance", decoded.campaign.normalization_variance);
    runtime.read("hidden_state", decoded.campaign.hidden_state);
    decoded.campaign.normalization_mean = decoded.campaign.normalization_mean.to(torch::kCPU).contiguous();
    decoded.campaign.normalization_variance = decoded.campaign.normalization_variance.to(torch::kCPU).contiguous();
    decoded.campaign.hidden_state = decoded.campaign.hidden_state.to(torch::kCPU).contiguous();
    validate_campaign(decoded.campaign);
    const auto architecture = parse_generalist_architecture(manifest.architecture);
    if (decoded.runtime.run_seed != manifest.run_seed || decoded.runtime.architecture != architecture) {
        throw std::invalid_argument("M22 checkpoint manifest/runtime identity mismatch");
    }
    auto trainer = std::make_unique<M22Trainer>(decoded.config, decoded.runtime.run_seed, architecture, torch::kCPU);
    torch::load(trainer->model(), (checkpoint_path / "model.pt").string());
    torch::load(trainer->optimizer(), (checkpoint_path / "optimizer.pt").string());
    require_finite_generalist(trainer->model(), "M22 checkpoint load");
    if (!policy_device.is_cpu()) trainer->to(policy_device);
    trainer->restore_runtime_state(decoded.runtime);
    return {manifest.checkpoint_id, std::move(decoded.campaign), std::move(trainer)};
}

} // namespace openttd_rl::v2
