#include "openttd_rl/training/evaluation_model.h"

#include "openttd_rl/training/ppo.h"
#include "openttd_rl/training/rng.h"

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

namespace openttd_rl::training {

namespace {

constexpr std::size_t kMaximumModelBytes = 256U * 1024U * 1024U;
constexpr std::size_t kMaximumManifestBytes = 65536U;
std::atomic<std::uint64_t> temporary_counter{0};

class Sha256 {
public:
    Sha256() : context_(EVP_MD_CTX_new())
    {
        if (context_ == nullptr || EVP_DigestInit_ex(context_, EVP_sha256(), nullptr) != 1) {
            if (context_ != nullptr) EVP_MD_CTX_free(context_);
            throw std::runtime_error("cannot initialize SHA-256");
        }
    }
    ~Sha256() { EVP_MD_CTX_free(context_); }
    Sha256(const Sha256 &) = delete;
    Sha256 &operator=(const Sha256 &) = delete;
    void update(const void *data, std::size_t size)
    {
        if (EVP_DigestUpdate(context_, data, size) != 1) throw std::runtime_error("SHA-256 update failed");
    }
    [[nodiscard]] std::string finish()
    {
        std::array<unsigned char, 32> digest{};
        unsigned int size = 0;
        if (EVP_DigestFinal_ex(context_, digest.data(), &size) != 1 || size != digest.size()) {
            throw std::runtime_error("SHA-256 finalization failed");
        }
        std::ostringstream output;
        output << std::hex << std::setfill('0');
        for (const auto byte : digest) output << std::setw(2) << static_cast<unsigned int>(byte);
        return output.str();
    }

private:
    EVP_MD_CTX *context_;
};

std::string sha256_bytes(const void *data, std::size_t size)
{
    Sha256 digest;
    digest.update(data, size);
    return digest.finish();
}

std::string sha256_file(const std::filesystem::path &path, std::size_t maximum)
{
    const auto size = std::filesystem::file_size(path);
    if (size > maximum) throw std::length_error("evaluation-model file exceeds bound: " + path.string());
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("cannot read evaluation-model file: " + path.string());
    Sha256 digest;
    std::array<char, 1024U * 1024U> buffer{};
    while (input) {
        input.read(buffer.data(), static_cast<std::streamsize>(buffer.size()));
        const auto count = input.gcount();
        if (count > 0) digest.update(buffer.data(), static_cast<std::size_t>(count));
    }
    if (!input.eof()) throw std::runtime_error("cannot hash evaluation-model file");
    return digest.finish();
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

void require_provenance(const EvaluationModelProvenance &provenance)
{
    if (provenance.repository_commit.size() != 40U || provenance.completed_updates == 0 ||
        provenance.accepted_samples == 0 || !std::isfinite(provenance.training_mean_reward)) {
        throw std::invalid_argument("evaluation-model provenance is incomplete");
    }
    for (const char value : provenance.repository_commit) {
        if (!((value >= '0' && value <= '9') || (value >= 'a' && value <= 'f'))) {
            throw std::invalid_argument("evaluation-model repository commit is not lowercase hex");
        }
    }
}

std::filesystem::path temporary_directory(const std::filesystem::path &root)
{
    if (!root.is_absolute()) throw std::invalid_argument("evaluation-model root must be absolute");
    std::filesystem::create_directories(root);
    for (unsigned int attempt = 0; attempt < 100U; ++attempt) {
        const auto suffix = std::to_string(::getpid()) + "-" + std::to_string(temporary_counter.fetch_add(1));
        const auto path = root / (".evaluation-model-tmp-" + suffix);
        std::error_code error;
        if (std::filesystem::create_directory(path, error)) return path;
        if (error && error != std::errc::file_exists) {
            throw std::filesystem::filesystem_error("cannot create evaluation-model temporary directory", path, error);
        }
    }
    throw std::runtime_error("cannot allocate evaluation-model temporary directory");
}

void sync_file(const std::filesystem::path &path)
{
    const int descriptor = ::open(path.c_str(), O_RDONLY | O_CLOEXEC);
    if (descriptor < 0) throw std::runtime_error("cannot open evaluation-model file for sync: " + std::string(std::strerror(errno)));
    const int result = ::fsync(descriptor);
    const int saved_errno = errno;
    (void)::close(descriptor);
    if (result != 0) throw std::runtime_error("cannot sync evaluation-model file: " + std::string(std::strerror(saved_errno)));
}

void sync_directory(const std::filesystem::path &path)
{
    const int descriptor = ::open(path.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (descriptor < 0) throw std::runtime_error("cannot open evaluation-model directory for sync");
    const int result = ::fsync(descriptor);
    const int saved_errno = errno;
    (void)::close(descriptor);
    if (result != 0) throw std::runtime_error("cannot sync evaluation-model directory: " + std::string(std::strerror(saved_errno)));
}

void write_new(const std::filesystem::path &path, const std::string &data)
{
    const int descriptor = ::open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, S_IRUSR | S_IWUSR | S_IRGRP | S_IROTH);
    if (descriptor < 0) throw std::runtime_error("cannot create evaluation-model manifest");
    std::size_t offset = 0;
    try {
        while (offset < data.size()) {
            const auto count = ::write(descriptor, data.data() + offset, data.size() - offset);
            if (count < 0 && errno == EINTR) continue;
            if (count <= 0) throw std::runtime_error("cannot write evaluation-model manifest");
            offset += static_cast<std::size_t>(count);
        }
        if (::fsync(descriptor) != 0) throw std::runtime_error("cannot sync evaluation-model manifest");
    } catch (...) {
        (void)::close(descriptor);
        throw;
    }
    if (::close(descriptor) != 0) throw std::runtime_error("cannot close evaluation-model manifest");
}

std::string bounded_text(const std::filesystem::path &path)
{
    const auto size = std::filesystem::file_size(path);
    if (size == 0 || size > kMaximumManifestBytes) throw std::length_error("evaluation-model manifest size is invalid");
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("cannot read evaluation-model manifest");
    std::string value(static_cast<std::size_t>(size), '\0');
    input.read(value.data(), static_cast<std::streamsize>(value.size()));
    if (!input || input.peek() != std::ifstream::traits_type::eof()) throw std::runtime_error("cannot read exact evaluation-model manifest");
    return value;
}

std::string manifest_string(const std::string &manifest, std::string_view key)
{
    const std::string marker = "\"" + std::string(key) + "\":\"";
    const auto start = manifest.find(marker);
    if (start == std::string::npos || manifest.find(marker, start + 1U) != std::string::npos) {
        throw std::invalid_argument("evaluation-model manifest field is missing or duplicated: " + std::string(key));
    }
    const auto value_start = start + marker.size();
    const auto end = manifest.find('"', value_start);
    if (end == std::string::npos || manifest.find('\\', value_start) < end) {
        throw std::invalid_argument("evaluation-model manifest string is unsupported: " + std::string(key));
    }
    return manifest.substr(value_start, end - value_start);
}

void require_cpu_inputs(const torch::Tensor &structured, const torch::Tensor &spatial, const torch::Tensor &masks)
{
    for (const auto *tensor : {&structured, &spatial, &masks}) {
        if (!tensor->defined() || tensor->device().is_cuda()) throw std::invalid_argument("evaluator accepts CPU inputs only");
    }
    if (structured.scalar_type() != torch::kFloat32 || structured.dim() != 2 || structured.size(1) != kStructuredFeatures) {
        throw std::invalid_argument("evaluator structured input must be float32 [batch,256]");
    }
    if (spatial.scalar_type() != torch::kFloat32 || spatial.dim() != 4 || spatial.size(0) != structured.size(0) ||
        spatial.size(1) != kSpatialChannels || spatial.size(2) != kSpatialHeight || spatial.size(3) != kSpatialWidth) {
        throw std::invalid_argument("evaluator spatial input must be float32 [batch,32,32,32]");
    }
    if (masks.dim() != 2 || masks.size(0) != structured.size(0) || masks.size(1) != kActionCount) {
        throw std::invalid_argument("evaluator mask input must be [batch,41]");
    }
    require_finite_tensor(structured, "evaluator structured input");
    require_finite_tensor(spatial, "evaluator spatial input");
    if ((spatial < 0).any().item<bool>() || (spatial > 1).any().item<bool>()) {
        throw std::invalid_argument("evaluator spatial input left [0,1]");
    }
}

} // namespace

SavedEvaluationModel save_evaluation_model(
    const std::filesystem::path &package_root,
    MultiModalActorCritic &model,
    ArchitectureKind architecture,
    const EvaluationModelProvenance &provenance)
{
    require_provenance(provenance);
    require_finite_multimodal_model(model, "evaluation export");
    if (model->kind() != architecture) throw std::invalid_argument("evaluation export architecture disagrees with model");
    const auto temporary = temporary_directory(package_root);
    try {
        model->to(torch::kCPU, torch::kFloat32);
        require_finite_multimodal_model(model, "canonical CPU evaluation export");
        const auto model_path = temporary / "model.pt";
        torch::serialize::OutputArchive archive;
        model->save(archive);
        archive.save_to(model_path.string());
        sync_file(model_path);
        const auto model_sha = sha256_file(model_path, kMaximumModelBytes);
        std::ostringstream manifest;
        manifest << "{\"accepted_samples\":" << provenance.accepted_samples
                 << ",\"architecture\":" << json_escape(architecture_name(architecture))
                 << ",\"completed_updates\":" << provenance.completed_updates
                 << ",\"format\":\"openttd-rl-evaluation-model-v1\""
                 << ",\"m08_compatibility_sha256\":\"" << kM08CompatibilitySha256 << "\""
                 << ",\"m09_compatibility_sha256\":\"" << kM09EvaluationCompatibilitySha256 << "\""
                 << ",\"model_sha256\":\"" << model_sha << "\""
                 << ",\"repository_commit\":" << json_escape(provenance.repository_commit)
                 << ",\"run_seed\":" << provenance.run_seed
                 << ",\"training_mean_reward\":" << std::setprecision(17) << provenance.training_mean_reward
                 << "}";
        const std::string manifest_data = manifest.str();
        const auto package_id = sha256_bytes(manifest_data.data(), manifest_data.size());
        write_new(temporary / "manifest.json", manifest_data);
        sync_directory(temporary);
        const auto final_path = package_root / package_id;
        if (std::filesystem::exists(final_path)) throw std::runtime_error("evaluation-model content address already exists");
        std::filesystem::rename(temporary, final_path);
        sync_directory(package_root);
        return {package_id, final_path};
    } catch (...) {
        std::error_code ignored;
        std::filesystem::remove_all(temporary, ignored);
        throw;
    }
}

ReadOnlyEvaluationPolicy::ReadOnlyEvaluationPolicy(
    const std::filesystem::path &package_path,
    std::uint64_t sampling_seed)
    : architecture_(ArchitectureKind::StructuredMlp),
      model_(ArchitectureKind::StructuredMlp, 0),
      sampling_generator_(sampling_seed)
{
    if (!package_path.is_absolute() || !std::filesystem::is_directory(package_path)) {
        throw std::invalid_argument("evaluation-model package must be an existing absolute directory");
    }
    const auto manifest = bounded_text(package_path / "manifest.json");
    package_id_ = sha256_bytes(manifest.data(), manifest.size());
    if (package_path.filename() != package_id_) throw std::invalid_argument("evaluation-model package content address mismatch");
    if (manifest_string(manifest, "format") != "openttd-rl-evaluation-model-v1" ||
        manifest_string(manifest, "m08_compatibility_sha256") != kM08CompatibilitySha256 ||
        manifest_string(manifest, "m09_compatibility_sha256") != kM09EvaluationCompatibilitySha256) {
        throw std::invalid_argument("evaluation-model package compatibility mismatch");
    }
    architecture_ = parse_architecture_kind(manifest_string(manifest, "architecture"));
    model_sha256_ = manifest_string(manifest, "model_sha256");
    const auto model_path = package_path / "model.pt";
    if (sha256_file(model_path, kMaximumModelBytes) != model_sha256_) {
        throw std::invalid_argument("evaluation-model payload digest mismatch");
    }
    model_ = MultiModalActorCritic(architecture_, 0);
    torch::serialize::InputArchive archive;
    archive.load_from(model_path.string(), torch::Device(torch::kCPU));
    model_->load(archive);
    model_->to(torch::kCPU, torch::kFloat32);
    model_->eval();
    require_finite_multimodal_model(model_, "loaded evaluation");
}

EvaluationActionBatch ReadOnlyEvaluationPolicy::act(
    const torch::Tensor &structured,
    const torch::Tensor &spatial,
    const torch::Tensor &legal_masks,
    bool deterministic)
{
    require_cpu_inputs(structured, spatial, legal_masks);
    torch::InferenceMode guard;
    auto [logits, values] = model_->forward(structured, spatial);
    auto policy = masked_categorical(logits, legal_masks);
    torch::Tensor actions;
    if (deterministic) actions = policy.log_probabilities.argmax(1);
    else actions = sample_masked_actions(policy.log_probabilities, legal_masks, sampling_generator_);
    auto selected = policy.log_probabilities.gather(1, actions.unsqueeze(1)).squeeze(1);
    require_finite_tensor(selected, "evaluation selected log probabilities");
    return {actions, selected, values, logits};
}

std::string ReadOnlyEvaluationPolicy::state_sha256() const
{
    Sha256 digest;
    constexpr std::string_view domain = "OTRLM09MODELSTATE1";
    digest.update(domain.data(), domain.size());
    for (const auto &parameter : model_->named_parameters(true)) {
        const auto &name = parameter.key();
        const auto tensor = parameter.value().to(torch::kCPU).contiguous();
        digest.update(name.data(), name.size());
        const std::uint64_t bytes = static_cast<std::uint64_t>(tensor.nbytes());
        digest.update(&bytes, sizeof(bytes));
        digest.update(tensor.const_data_ptr(), static_cast<std::size_t>(bytes));
    }
    return digest.finish();
}

} // namespace openttd_rl::training
