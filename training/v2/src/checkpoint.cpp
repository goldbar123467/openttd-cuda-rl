#include "openttd_rl/v2/checkpoint.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <cerrno>
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
#include <utility>
#include <vector>

namespace openttd_rl::v2 {

namespace {

constexpr std::array<char, 8> kStateMagic = {'O', 'T', 'R', 'L', 'V', '2', 'S', '1'};
constexpr std::uint32_t kStateVersion = 1;
constexpr std::size_t kMaximumStateBytes = 1024 * 1024;
constexpr std::size_t kMaximumPayloadBytes = 1024ULL * 1024ULL * 1024ULL;
std::atomic<std::uint64_t> temporary_counter{0};

class BytesWriter {
public:
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
        if (std::memcmp(data_.data() + offset_, expected, length) != 0) throw std::invalid_argument("checkpoint state magic mismatch");
        offset_ += length;
    }

    std::uint32_t u32()
    {
        require(4);
        std::uint32_t value = 0;
        for (unsigned int index = 0; index < 4U; ++index) value |= static_cast<std::uint32_t>(data_[offset_++]) << (8U * index);
        return value;
    }

    std::uint64_t u64()
    {
        require(8);
        std::uint64_t value = 0;
        for (unsigned int index = 0; index < 8U; ++index) value |= static_cast<std::uint64_t>(data_[offset_++]) << (8U * index);
        return value;
    }

    std::string string(std::size_t maximum)
    {
        const auto length = static_cast<std::size_t>(u32());
        if (length > maximum) throw std::length_error("checkpoint string exceeds bound");
        require(length);
        std::string result(reinterpret_cast<const char *>(data_.data() + offset_), length);
        offset_ += length;
        return result;
    }

    void finish() const
    {
        if (offset_ != data_.size()) throw std::invalid_argument("checkpoint state has trailing bytes");
    }

private:
    void require(std::size_t length) const
    {
        if (length > data_.size() - offset_) throw std::invalid_argument("checkpoint state is truncated");
    }

    const std::vector<std::uint8_t> &data_;
    std::size_t offset_{};
};

std::vector<std::uint8_t> read_bounded(const std::filesystem::path &path, std::size_t maximum)
{
    const auto size = std::filesystem::file_size(path);
    if (size > maximum) throw std::length_error("checkpoint payload exceeds bound: " + path.string());
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("cannot read checkpoint payload: " + path.string());
    std::vector<std::uint8_t> data(static_cast<std::size_t>(size));
    if (!data.empty()) input.read(reinterpret_cast<char *>(data.data()), static_cast<std::streamsize>(data.size()));
    if (!input || input.peek() != std::ifstream::traits_type::eof()) throw std::runtime_error("cannot read exact checkpoint payload");
    return data;
}

std::string sha256_bytes(const void *data, std::size_t length)
{
    std::array<std::uint8_t, 32> digest{};
    auto *context = EVP_MD_CTX_new();
    if (context == nullptr) throw std::runtime_error("cannot allocate SHA-256 context");
    const bool updated = EVP_DigestInit_ex(context, EVP_sha256(), nullptr) == 1 &&
        EVP_DigestUpdate(context, data, length) == 1;
    unsigned int digest_length = 0;
    const bool finalized = updated && EVP_DigestFinal_ex(context, digest.data(), &digest_length) == 1;
    EVP_MD_CTX_free(context);
    if (!finalized || digest_length != digest.size()) throw std::runtime_error("SHA-256 failed");
    std::ostringstream output;
    output << std::hex << std::setfill('0');
    for (const auto byte : digest) output << std::setw(2) << static_cast<unsigned int>(byte);
    return output.str();
}

std::string sha256_file(const std::filesystem::path &path)
{
    const auto data = read_bounded(path, kMaximumPayloadBytes);
    return sha256_bytes(data.data(), data.size());
}

void write_new(const std::filesystem::path &path, const void *data, std::size_t length)
{
    const int descriptor = ::open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, S_IRUSR | S_IWUSR | S_IRGRP | S_IROTH);
    if (descriptor < 0) throw std::runtime_error("cannot create checkpoint file: " + std::string(std::strerror(errno)));
    const auto *bytes = static_cast<const std::uint8_t *>(data);
    std::size_t offset = 0;
    try {
        while (offset < length) {
            const auto result = ::write(descriptor, bytes + offset, length - offset);
            if (result < 0 && errno == EINTR) continue;
            if (result <= 0) throw std::runtime_error("cannot write checkpoint file");
            offset += static_cast<std::size_t>(result);
        }
        if (::fsync(descriptor) != 0) throw std::runtime_error("cannot sync checkpoint file");
    } catch (...) {
        (void)::close(descriptor);
        throw;
    }
    if (::close(descriptor) != 0) throw std::runtime_error("cannot close checkpoint file");
}

void write_new(const std::filesystem::path &path, const std::string &text)
{
    write_new(path, text.data(), text.size());
}

void sync_existing_file(const std::filesystem::path &path)
{
    const int descriptor = ::open(path.c_str(), O_RDONLY | O_CLOEXEC);
    if (descriptor < 0) throw std::runtime_error("cannot reopen checkpoint payload");
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

void validate_runtime_state(const PolicyRuntimeState &state)
{
    for (const auto &[tensor, name] : std::array<std::pair<torch::Tensor, const char *>, 2>{
             std::pair{state.normalization_mean, "normalization mean"},
             std::pair{state.normalization_variance, "normalization variance"},
         }) {
        if (!tensor.defined() || tensor.device().is_cuda() || tensor.scalar_type() != torch::kFloat32 ||
            tensor.sizes() != torch::IntArrayRef({kStructuredFeatures}) || !torch::isfinite(tensor).all().item<bool>()) {
            throw std::invalid_argument(std::string(name) + " must be finite CPU float32[512]");
        }
    }
    if ((state.normalization_variance <= 0).any().item<bool>()) throw std::invalid_argument("normalization variance must be positive");
    if (!state.hidden_state.defined() || state.hidden_state.device().is_cuda() || state.hidden_state.scalar_type() != torch::kFloat32 ||
        state.hidden_state.dim() != 2 || state.hidden_state.size(0) <= 0 || state.hidden_state.size(1) != kHiddenSize ||
        !torch::isfinite(state.hidden_state).all().item<bool>()) {
        throw std::invalid_argument("checkpoint hidden state must be finite CPU float32[batch,256]");
    }
    if (state.rng_state.empty() || state.rng_state.size() > 65536) throw std::invalid_argument("checkpoint RNG state is empty or oversized");
    if (state.curriculum.tier > 3 || state.curriculum.map_width == 0 || state.curriculum.map_height == 0 ||
        state.curriculum.map_width > 4096 || state.curriculum.map_height > 4096) {
        throw std::invalid_argument("checkpoint curriculum state is outside the frozen map tiers");
    }
}

std::vector<std::uint8_t> encode_state(const PolicyRuntimeState &state)
{
    BytesWriter writer;
    writer.raw(kStateMagic.data(), kStateMagic.size());
    writer.u32(kStateVersion);
    writer.string(kCheckpointSchemaId);
    writer.string(kScalableContractSha256);
    writer.u64(state.normalization_count);
    writer.u32(state.curriculum.tier);
    writer.u32(state.curriculum.map_width);
    writer.u32(state.curriculum.map_height);
    writer.u64(state.curriculum.episode);
    writer.u64(state.curriculum.transition);
    writer.u64(state.completed_updates);
    writer.string(state.rng_state);
    if (writer.data().size() > kMaximumStateBytes) throw std::length_error("checkpoint state exceeds bound");
    return writer.data();
}

void decode_state(const std::vector<std::uint8_t> &data, PolicyRuntimeState &state)
{
    BytesReader reader(data);
    reader.expect(kStateMagic.data(), kStateMagic.size());
    if (reader.u32() != kStateVersion) throw std::invalid_argument("unsupported checkpoint state version");
    if (reader.string(128) != kCheckpointSchemaId) throw std::invalid_argument("checkpoint schema identity mismatch");
    if (reader.string(64) != kScalableContractSha256) throw std::invalid_argument("checkpoint contract identity mismatch");
    state.normalization_count = reader.u64();
    state.curriculum.tier = reader.u32();
    state.curriculum.map_width = reader.u32();
    state.curriculum.map_height = reader.u32();
    state.curriculum.episode = reader.u64();
    state.curriculum.transition = reader.u64();
    state.completed_updates = reader.u64();
    state.rng_state = reader.string(65536);
    reader.finish();
}

struct Manifest {
    std::string checkpoint_id;
    std::string model_sha;
    std::string optimizer_sha;
    std::string runtime_sha;
    std::string state_sha;
};

std::string manifest_text(const Manifest &manifest)
{
    return std::string("schema=") + kCheckpointSchemaId + "\ncontract=" + kScalableContractSha256 +
        "\ncheckpoint_id=" + manifest.checkpoint_id + "\nmodel_sha256=" + manifest.model_sha +
        "\noptimizer_sha256=" + manifest.optimizer_sha + "\nruntime_sha256=" + manifest.runtime_sha +
        "\nstate_sha256=" + manifest.state_sha + "\nboundary=after-completed-ppo-update-before-next-rollout\n";
}

Manifest parse_manifest(const std::filesystem::path &path)
{
    const auto bytes = read_bounded(path, 4096);
    const std::string text(bytes.begin(), bytes.end());
    std::istringstream input(text);
    std::vector<std::pair<std::string, std::string>> fields;
    std::string line;
    while (std::getline(input, line)) {
        const auto separator = line.find('=');
        if (separator == std::string::npos || separator == 0) throw std::invalid_argument("checkpoint manifest is malformed");
        fields.emplace_back(line.substr(0, separator), line.substr(separator + 1));
    }
    const std::array<std::string_view, 8> expected = {
        "schema", "contract", "checkpoint_id", "model_sha256", "optimizer_sha256", "runtime_sha256", "state_sha256", "boundary",
    };
    if (fields.size() != expected.size()) throw std::invalid_argument("checkpoint manifest field count mismatch");
    for (std::size_t index = 0; index < expected.size(); ++index) {
        if (fields[index].first != expected[index]) throw std::invalid_argument("checkpoint manifest field order mismatch");
    }
    if (fields[0].second != kCheckpointSchemaId || fields[1].second != kScalableContractSha256 ||
        fields[7].second != "after-completed-ppo-update-before-next-rollout") {
        throw std::invalid_argument("checkpoint manifest compatibility mismatch");
    }
    for (std::size_t index = 2; index <= 6; ++index) {
        if (fields[index].second.size() != 64 || fields[index].second.find_first_not_of("0123456789abcdef") != std::string::npos) {
            throw std::invalid_argument("checkpoint manifest digest is malformed");
        }
    }
    return {fields[2].second, fields[3].second, fields[4].second, fields[5].second, fields[6].second};
}

std::string checkpoint_id(const Manifest &manifest)
{
    const auto identity = std::string(kCheckpointSchemaId) + '\n' + kScalableContractSha256 + '\n' +
        manifest.model_sha + '\n' + manifest.optimizer_sha + '\n' + manifest.runtime_sha + '\n' + manifest.state_sha + '\n';
    return sha256_bytes(identity.data(), identity.size());
}

void require_exact_inventory(const std::filesystem::path &path)
{
    const std::array<std::string, 6> expected = {
        "COMMITTED", "checkpoint.manifest", "model.pt", "optimizer.pt", "runtime.pt", "state.bin",
    };
    std::vector<std::string> actual;
    for (const auto &entry : std::filesystem::directory_iterator(path)) {
        if (!entry.is_regular_file() || entry.is_symlink()) throw std::invalid_argument("checkpoint contains a non-regular entry");
        actual.push_back(entry.path().filename().string());
    }
    std::sort(actual.begin(), actual.end());
    if (!std::equal(actual.begin(), actual.end(), expected.begin(), expected.end())) {
        throw std::invalid_argument("checkpoint file inventory mismatch");
    }
}

} // namespace

SavedCheckpoint save_checkpoint(
    const std::filesystem::path &checkpoint_root,
    ScalablePolicy &model,
    torch::optim::Adam &optimizer,
    const PolicyRuntimeState &state)
{
    validate_runtime_state(state);
    if (!checkpoint_root.is_absolute()) throw std::invalid_argument("checkpoint root must be absolute");
    std::filesystem::create_directories(checkpoint_root);
    const auto temporary = checkpoint_root / (".tmp-" + std::to_string(::getpid()) + "-" + std::to_string(temporary_counter.fetch_add(1)));
    if (!std::filesystem::create_directory(temporary)) throw std::runtime_error("cannot create checkpoint staging directory");
    try {
        const auto model_path = temporary / "model.pt";
        const auto optimizer_path = temporary / "optimizer.pt";
        const auto runtime_path = temporary / "runtime.pt";
        const auto state_path = temporary / "state.bin";
        torch::save(model, model_path.string());
        torch::save(optimizer, optimizer_path.string());
        torch::serialize::OutputArchive runtime;
        runtime.write("normalization_mean", state.normalization_mean.contiguous());
        runtime.write("normalization_variance", state.normalization_variance.contiguous());
        runtime.write("hidden_state", state.hidden_state.contiguous());
        runtime.save_to(runtime_path.string());
        const auto state_bytes = encode_state(state);
        write_new(state_path, state_bytes.data(), state_bytes.size());
        sync_existing_file(model_path);
        sync_existing_file(optimizer_path);
        sync_existing_file(runtime_path);
        Manifest manifest{"", sha256_file(model_path), sha256_file(optimizer_path), sha256_file(runtime_path), sha256_file(state_path)};
        manifest.checkpoint_id = checkpoint_id(manifest);
        write_new(temporary / "checkpoint.manifest", manifest_text(manifest));
        write_new(temporary / "COMMITTED", manifest.checkpoint_id + "\n");
        sync_directory(temporary);
        const auto final_path = checkpoint_root / manifest.checkpoint_id;
        if (std::filesystem::exists(final_path)) throw std::runtime_error("checkpoint already exists; never overwriting");
        std::filesystem::rename(temporary, final_path);
        sync_directory(checkpoint_root);
        return {manifest.checkpoint_id, final_path};
    } catch (...) {
        std::error_code error;
        std::filesystem::remove_all(temporary, error);
        throw;
    }
}

PolicyRuntimeState load_checkpoint(
    const std::filesystem::path &checkpoint_path,
    ScalablePolicy &model,
    torch::optim::Adam &optimizer,
    const torch::Device &policy_device)
{
    if (!checkpoint_path.is_absolute() || !std::filesystem::is_directory(checkpoint_path) || std::filesystem::is_symlink(checkpoint_path)) {
        throw std::invalid_argument("checkpoint path must be an absolute real directory");
    }
    require_exact_inventory(checkpoint_path);
    const auto manifest = parse_manifest(checkpoint_path / "checkpoint.manifest");
    if (checkpoint_path.filename() != manifest.checkpoint_id || checkpoint_id(manifest) != manifest.checkpoint_id) {
        throw std::invalid_argument("checkpoint identity mismatch");
    }
    const auto committed = read_bounded(checkpoint_path / "COMMITTED", 128);
    if (std::string(committed.begin(), committed.end()) != manifest.checkpoint_id + "\n") {
        throw std::invalid_argument("checkpoint commit marker mismatch");
    }
    if (sha256_file(checkpoint_path / "model.pt") != manifest.model_sha ||
        sha256_file(checkpoint_path / "optimizer.pt") != manifest.optimizer_sha ||
        sha256_file(checkpoint_path / "runtime.pt") != manifest.runtime_sha ||
        sha256_file(checkpoint_path / "state.bin") != manifest.state_sha) {
        throw std::invalid_argument("checkpoint tensor payload digest mismatch");
    }
    PolicyRuntimeState result;
    decode_state(read_bounded(checkpoint_path / "state.bin", kMaximumStateBytes), result);
    torch::serialize::InputArchive runtime;
    runtime.load_from((checkpoint_path / "runtime.pt").string());
    runtime.read("normalization_mean", result.normalization_mean);
    runtime.read("normalization_variance", result.normalization_variance);
    runtime.read("hidden_state", result.hidden_state);
    result.normalization_mean = result.normalization_mean.to(torch::kCPU).contiguous();
    result.normalization_variance = result.normalization_variance.to(torch::kCPU).contiguous();
    result.hidden_state = result.hidden_state.to(torch::kCPU).contiguous();
    validate_runtime_state(result);
    torch::load(model, (checkpoint_path / "model.pt").string());
    model->to(policy_device);
    torch::load(optimizer, (checkpoint_path / "optimizer.pt").string());
    require_finite_policy(model, "checkpoint load");
    return result;
}

} // namespace openttd_rl::v2
