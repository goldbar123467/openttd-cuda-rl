#include "openttd_rl/v2/m22_evaluation.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <limits>
#include <openssl/evp.h>
#include <sstream>
#include <stdexcept>
#include <string_view>
#include <utility>
#include <vector>

#include <torch/cuda.h>

namespace openttd_rl::v2 {

namespace {

using torch::indexing::Slice;

constexpr std::size_t kMaximumPayloadBytes = 1024ULL * 1024ULL * 1024ULL;
constexpr std::string_view kCheckpointSchema = "v2-m22-generalist-checkpoint-v1";
constexpr std::string_view kNativeCorpusSha256 = "0af952bb840bca2a80a577e2a2446845f2db749d7efbaeb06af4b94418ff6725";
constexpr std::string_view kBoundary = "after-completed-ppo-update-and-retention-check-before-next-rollout";
constexpr std::array<std::int64_t, kM22ProgramCount> kProgramMode = {
    0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 6, 6, 6, 6, 6,
};
constexpr std::array<std::string_view, 7> kModes = {
    "road", "rail", "water", "air", "multimodal", "company", "broad",
};
constexpr std::array<std::string_view, 4> kClimates = {
    "temperate", "arctic", "tropic", "toyland",
};

struct Manifest {
    GeneralistArchitecture architecture{GeneralistArchitecture::Monolithic};
    std::string architecture_name;
    std::uint64_t run_seed{};
    std::string checkpoint_id;
    std::string model_sha;
    std::string optimizer_sha;
    std::string runtime_sha;
    std::string state_sha;
    std::string selection_sha;
};

[[nodiscard]] bool safe_token(std::string_view value)
{
    return !value.empty() && value.size() <= 80 &&
        std::all_of(value.begin(), value.end(), [](unsigned char character) {
            return (character >= 'a' && character <= 'z') ||
                (character >= '0' && character <= '9') || character == '-' || character == '_';
        });
}

[[nodiscard]] bool digest(std::string_view value)
{
    return value.size() == 64 && value.find_first_not_of("0123456789abcdef") == std::string_view::npos;
}

[[nodiscard]] std::vector<std::uint8_t> read_bounded(const std::filesystem::path &path, std::size_t maximum)
{
    if (!std::filesystem::is_regular_file(path) || std::filesystem::is_symlink(path)) {
        throw std::invalid_argument("M22 evaluation payload is missing, non-regular, or a symlink");
    }
    const auto size = std::filesystem::file_size(path);
    if (size > maximum) throw std::length_error("M22 evaluation payload exceeds its byte bound");
    std::vector<std::uint8_t> result(static_cast<std::size_t>(size));
    std::ifstream input(path, std::ios::binary);
    input.read(reinterpret_cast<char *>(result.data()), static_cast<std::streamsize>(result.size()));
    if (!input || input.peek() != std::ifstream::traits_type::eof()) {
        throw std::runtime_error("cannot read exact M22 evaluation payload");
    }
    return result;
}

[[nodiscard]] std::string sha256_bytes(const void *data, std::size_t length)
{
    std::array<unsigned char, EVP_MAX_MD_SIZE> digest_bytes{};
    unsigned int digest_length = 0;
    auto *context = EVP_MD_CTX_new();
    if (context == nullptr) throw std::runtime_error("cannot allocate M22 evaluation SHA-256 context");
    const bool success = EVP_DigestInit_ex(context, EVP_sha256(), nullptr) == 1 &&
        EVP_DigestUpdate(context, data, length) == 1 &&
        EVP_DigestFinal_ex(context, digest_bytes.data(), &digest_length) == 1;
    EVP_MD_CTX_free(context);
    if (!success || digest_length != 32) throw std::runtime_error("cannot compute M22 evaluation SHA-256");
    static constexpr char alphabet[] = "0123456789abcdef";
    std::string result;
    result.reserve(64);
    for (unsigned int index = 0; index < digest_length; ++index) {
        result.push_back(alphabet[digest_bytes[index] >> 4U]);
        result.push_back(alphabet[digest_bytes[index] & 0x0FU]);
    }
    return result;
}

[[nodiscard]] std::string sha256_file(const std::filesystem::path &path)
{
    const auto bytes = read_bounded(path, kMaximumPayloadBytes);
    return sha256_bytes(bytes.data(), bytes.size());
}

[[nodiscard]] std::uint64_t initialization_seed(std::uint64_t run_seed) noexcept
{
    std::uint64_t value = run_seed + UINT64_C(0x9e3779b97f4a7c15);
    value = (value ^ (value >> 30U)) * UINT64_C(0xbf58476d1ce4e5b9);
    value = (value ^ (value >> 27U)) * UINT64_C(0x94d049bb133111eb);
    return value ^ (value >> 31U);
}

[[nodiscard]] std::string checkpoint_id(const Manifest &manifest)
{
    const auto identity = std::string(kCheckpointSchema) + '\n' + kM22LearningContractSha256 + '\n' +
        std::string(kNativeCorpusSha256) + '\n' + manifest.architecture_name + '\n' + std::to_string(manifest.run_seed) + '\n' +
        manifest.model_sha + '\n' + manifest.optimizer_sha + '\n' + manifest.runtime_sha + '\n' +
        manifest.state_sha + '\n' + manifest.selection_sha + '\n' + std::string(kBoundary) + '\n';
    return sha256_bytes(identity.data(), identity.size());
}

[[nodiscard]] Manifest parse_manifest(const std::filesystem::path &path)
{
    const auto bytes = read_bounded(path, 8192);
    std::istringstream input(std::string(bytes.begin(), bytes.end()));
    std::vector<std::pair<std::string, std::string>> fields;
    std::string line;
    while (std::getline(input, line)) {
        const auto separator = line.find('=');
        if (separator == std::string::npos || separator == 0) {
            throw std::invalid_argument("M22 evaluation checkpoint manifest is malformed");
        }
        fields.emplace_back(line.substr(0, separator), line.substr(separator + 1));
    }
    constexpr std::array<std::string_view, 12> names = {
        "schema", "contract", "corpus", "architecture", "run_seed", "checkpoint_id", "model_sha256",
        "optimizer_sha256", "runtime_sha256", "trainer_state_sha256", "selection_sha256", "boundary",
    };
    if (fields.size() != names.size()) throw std::invalid_argument("M22 evaluation manifest field count drifted");
    for (std::size_t index = 0; index < names.size(); ++index) {
        if (fields[index].first != names[index]) throw std::invalid_argument("M22 evaluation manifest field order drifted");
    }
    if (fields[0].second != kCheckpointSchema || fields[1].second != kM22LearningContractSha256 ||
        fields[2].second != kNativeCorpusSha256 || fields[11].second != kBoundary) {
        throw std::invalid_argument("M22 evaluation manifest compatibility mismatch");
    }
    std::uint64_t run_seed = 0;
    try {
        std::size_t consumed = 0;
        run_seed = std::stoull(fields[4].second, &consumed);
        if (consumed != fields[4].second.size()) throw std::invalid_argument("trailing");
    } catch (const std::exception &) {
        throw std::invalid_argument("M22 evaluation run seed is malformed");
    }
    for (std::size_t index = 5; index <= 10; ++index) {
        if (!digest(fields[index].second)) throw std::invalid_argument("M22 evaluation digest is malformed");
    }
    return {
        parse_generalist_architecture(fields[3].second), fields[3].second, run_seed, fields[5].second,
        fields[6].second, fields[7].second, fields[8].second, fields[9].second, fields[10].second,
    };
}

void require_inventory(const std::filesystem::path &path)
{
    constexpr std::array<std::string_view, 7> expected = {
        "COMMITTED", "m22.manifest", "model.pt", "optimizer.pt", "runtime.pt", "selection.json", "trainer-state.bin",
    };
    std::vector<std::string> actual;
    for (const auto &entry : std::filesystem::directory_iterator(path)) {
        if (!entry.is_regular_file() || entry.is_symlink()) {
            throw std::invalid_argument("M22 evaluation checkpoint contains a non-regular entry");
        }
        actual.push_back(entry.path().filename().string());
    }
    std::sort(actual.begin(), actual.end());
    if (actual.size() != expected.size() || !std::equal(actual.begin(), actual.end(), expected.begin())) {
        throw std::invalid_argument("M22 evaluation checkpoint inventory mismatch");
    }
}

[[nodiscard]] std::int64_t index_of(
    std::string_view value,
    const auto &values,
    const char *name)
{
    const auto found = std::find(values.begin(), values.end(), value);
    if (found == values.end()) throw std::invalid_argument(std::string("unknown M22 final ") + name);
    return static_cast<std::int64_t>(found - values.begin());
}

[[nodiscard]] bool one_of(std::string_view value, std::initializer_list<std::string_view> values)
{
    return std::find(values.begin(), values.end(), value) != values.end();
}

[[nodiscard]] std::int64_t public_program(const M22FinalPublicState &state)
{
    const auto probe = std::string_view(state.native_probe);
    if (state.source_gate == "G15") return 1;
    if (state.source_gate == "G16") return 2;
    if (state.source_gate == "G17") {
        if (one_of(probe, {"passenger", "rail-passenger", "passenger-service"})) return 3;
        if (one_of(probe, {"freight", "rail-freight", "freight-service"})) return 4;
    } else if (state.source_gate == "G18") {
        if (one_of(probe, {"natural", "ship-natural", "natural-service"})) return 5;
        if (one_of(probe, {"constructed", "ship-constructed", "constructed-service"})) return 6;
    } else if (state.source_gate == "G19") {
        if (one_of(probe, {"service", "air-service", "airplane"})) return 7;
        if (one_of(probe, {"helicopter", "air-helicopter"})) return 8;
        if (one_of(probe, {"multimodal", "multimodal-transfer", "transfer"})) return 9;
        if (one_of(probe, {"router", "mode-router", "routing"})) return 10;
    } else if (state.source_gate == "G20") {
        return 11;
    } else if (state.source_gate == "G21") {
        if (one_of(probe, {"calendar", "calendar-inspect"})) return 12;
        if (one_of(probe, {"authority_economy", "authority-economy"})) return 13;
        if (one_of(probe, {"events", "event-recovery"})) return 14;
        if (one_of(probe, {"gamescript", "gamescript-response"})) return 15;
        if (one_of(probe, {"content", "content-discovery"})) return 16;
    }
    throw std::invalid_argument("M22 final public gate/probe pair does not identify a legal capability");
}

void validate_public_state(const M22FinalPublicState &state)
{
    if (!one_of(state.task, {"service", "routing", "competition", "retention"}) ||
        !safe_token(state.native_probe)) {
        throw std::invalid_argument("M22 final task or native probe is invalid");
    }
    const auto mode = index_of(state.transport_mode, kModes, "transport mode");
    static_cast<void>(index_of(state.climate, kClimates, "climate"));
    const bool width = one_of(std::to_string(state.map_width), {"64", "128", "512", "1024"});
    const bool height = one_of(std::to_string(state.map_height), {"64", "128", "1024"});
    if (!width || !height || (state.cargo != "not-applicable" &&
        (state.cargo.size() != 4 || !std::all_of(state.cargo.begin(), state.cargo.end(), [](unsigned char character) {
            return (character >= 'A' && character <= 'Z') || (character >= '0' && character <= '9') || character == '_';
        })))) {
        throw std::invalid_argument("M22 final map dimensions or cargo are invalid");
    }
    if (!one_of(state.opponent, {"AAAHogEx", "KrakenAI2", "NoOpAI", "not-applicable"})) {
        throw std::invalid_argument("M22 final opponent is invalid");
    }
    const std::int64_t expected_mode = state.source_gate == "G15" || state.source_gate == "G16" ? 0 :
        state.source_gate == "G17" ? 1 : state.source_gate == "G18" ? 2 :
        state.source_gate == "G19" ? (state.transport_mode == "multimodal" ? 4 : 3) :
        state.source_gate == "G20" ? 5 : state.source_gate == "G21" ? 6 : -1;
    if (mode != expected_mode ||
        (state.source_gate == "G20" && (state.task != "competition" || state.opponent == "not-applicable")) ||
        (state.source_gate != "G20" && state.opponent != "not-applicable")) {
        throw std::invalid_argument("M22 final public mode, gate, task, or opponent combination is invalid");
    }
    static_cast<void>(public_program(state));
}

[[nodiscard]] float context_feature(const M22FinalPublicState &state)
{
    std::string identity = state.cargo;
    identity.push_back('\0');
    identity += state.native_probe;
    std::array<unsigned char, EVP_MAX_MD_SIZE> digest_bytes{};
    unsigned int digest_length = 0;
    auto *context = EVP_MD_CTX_new();
    if (context == nullptr) throw std::runtime_error("cannot allocate M22 context SHA-256");
    const bool success = EVP_DigestInit_ex(context, EVP_sha256(), nullptr) == 1 &&
        EVP_DigestUpdate(context, identity.data(), identity.size()) == 1 &&
        EVP_DigestFinal_ex(context, digest_bytes.data(), &digest_length) == 1;
    EVP_MD_CTX_free(context);
    if (!success || digest_length != 32) throw std::runtime_error("cannot compute M22 context SHA-256");
    const std::uint32_t prefix = static_cast<std::uint32_t>(digest_bytes[0]) << 24U |
        static_cast<std::uint32_t>(digest_bytes[1]) << 16U |
        static_cast<std::uint32_t>(digest_bytes[2]) << 8U | static_cast<std::uint32_t>(digest_bytes[3]);
    return static_cast<float>(static_cast<double>(prefix) / 4294967295.0);
}

void validate_batch(const M22EvaluationBatch &batch)
{
    if (!batch.public_features.defined() || !batch.public_features.device().is_cpu() ||
        batch.public_features.scalar_type() != torch::kFloat32 ||
        batch.public_features.sizes() != torch::IntArrayRef({1, kM22EvaluationFeatureCount}) ||
        !torch::isfinite(batch.public_features).all().item<bool>() ||
        !batch.program_mask.defined() || !batch.program_mask.device().is_cpu() ||
        batch.program_mask.scalar_type() != torch::kBool ||
        batch.program_mask.sizes() != torch::IntArrayRef({1, kM22ProgramCount}) ||
        batch.program_mask.sum().item<std::int64_t>() != 2 || !batch.program_mask.index({0, 0}).item<bool>() ||
        !batch.hidden_state.defined() || !batch.hidden_state.device().is_cpu() ||
        batch.hidden_state.scalar_type() != torch::kFloat32 ||
        batch.hidden_state.sizes() != torch::IntArrayRef({1, kHiddenSize}) ||
        !torch::equal(batch.hidden_state, torch::zeros_like(batch.hidden_state)) ||
        !batch.recurrent_reset.defined() || !batch.recurrent_reset.device().is_cpu() ||
        batch.recurrent_reset.scalar_type() != torch::kBool ||
        batch.recurrent_reset.sizes() != torch::IntArrayRef({1}) || !batch.recurrent_reset.item<bool>()) {
        throw std::invalid_argument("M22 final evaluation batch violated its optimizer-free one-case contract");
    }
}

} // namespace

M22EvaluationBatch encode_m22_final_public_state(const M22FinalPublicState &state)
{
    validate_public_state(state);
    const auto mode = index_of(state.transport_mode, kModes, "transport mode");
    const auto climate = index_of(state.climate, kClimates, "climate");
    const auto program = public_program(state);
    auto features = torch::zeros({1, kM22EvaluationFeatureCount}, torch::kFloat32);
    features.index_put_({0, mode}, 1.0F);
    features.index_put_({0, 7 + climate}, 1.0F);
    features.index_put_({0, 11}, static_cast<float>(state.map_width) / 4096.0F);
    features.index_put_({0, 12}, static_cast<float>(state.map_height) / 4096.0F);
    features.index_put_({0, 13}, static_cast<float>(state.map_width * state.map_height) / 1048576.0F);
    features.index_put_({0, 13 + program}, 1.0F);
    const float opponent = state.opponent == "AAAHogEx" ? 1.0F / 3.0F :
        state.opponent == "KrakenAI2" ? 2.0F / 3.0F : state.opponent == "NoOpAI" ? 1.0F : 0.0F;
    features.index_put_({0, 30}, opponent);
    features.index_put_({0, 31}, context_feature(state));
    auto mask = torch::zeros({1, kM22ProgramCount}, torch::kBool);
    mask.index_put_({0, 0}, true);
    mask.index_put_({0, program}, true);
    M22EvaluationBatch result{
        features, mask, torch::zeros({1, kHiddenSize}, torch::kFloat32), torch::ones({1}, torch::kBool),
    };
    validate_batch(result);
    return result;
}

GeneralistPolicyInput m22_evaluation_input(const M22EvaluationBatch &batch, const torch::Device &device)
{
    validate_batch(batch);
    const auto state = batch.public_features.to(device);
    const auto floats = torch::TensorOptions().dtype(torch::kFloat32).device(device);
    const auto booleans = torch::TensorOptions().dtype(torch::kBool).device(device);
    const auto integers = torch::TensorOptions().dtype(torch::kInt64).device(device);
    auto structured = torch::zeros({1, kStructuredFeatures}, floats);
    structured.index_put_({Slice(), Slice(0, kM22EvaluationFeatureCount)}, state);
    auto global = torch::zeros({1, kSpatialChannels, kGlobalSpatialSide, kGlobalSpatialSide}, floats);
    auto regional = torch::zeros({1, kSpatialChannels, kRegionalSpatialSide, kRegionalSpatialSide}, floats);
    auto local = torch::zeros({1, kSpatialChannels, kLocalSpatialSide, kLocalSpatialSide}, floats);
    for (auto *spatial : {&global, &regional, &local}) {
        spatial->index_put_({Slice(), 0, Slice(), Slice()}, 1.0F);
        spatial->index_put_({Slice(), 1, Slice(), Slice()}, state.index({Slice(), 11}).view({1, 1, 1}));
        spatial->index_put_({Slice(), 2, Slice(), Slice()}, state.index({Slice(), 12}).view({1, 1, 1}));
    }
    auto make_entity = [&](std::int64_t capacity, std::int64_t features) {
        EntityTable table{torch::zeros({1, capacity, features}, floats), torch::zeros({1, capacity}, booleans)};
        const auto copied = std::min(features, kM22EvaluationFeatureCount);
        table.features.index_put_({Slice(), 0, Slice(0, copied)}, state.index({Slice(), Slice(0, copied)}));
        table.mask.index_put_({Slice(), 0}, true);
        return table;
    };
    auto companies = make_entity(kCompanyCapacity, kCompanyFeatures);
    auto towns = make_entity(kTownCapacity, kTownFeatures);
    auto industries = make_entity(kIndustryCapacity, kIndustryFeatures);
    auto stations = make_entity(kStationCapacity, kStationFeatures);
    auto vehicles = make_entity(kVehicleCapacity, kVehicleFeatures);
    auto graph_nodes = torch::zeros({1, kGraphNodeCapacity, kGraphNodeFeatures}, floats);
    auto graph_node_mask = torch::zeros({1, kGraphNodeCapacity}, booleans);
    graph_nodes.index_put_({Slice(), 0, Slice()}, state.index({Slice(), Slice(0, kGraphNodeFeatures)}));
    graph_node_mask.index_put_({Slice(), 0}, true);
    auto graph_edge_index = torch::zeros({1, kGraphEdgeCapacity, 2}, integers);
    auto graph_edge_features = torch::zeros({1, kGraphEdgeCapacity, kGraphEdgeFeatures}, floats);
    auto graph_edge_mask = torch::zeros({1, kGraphEdgeCapacity}, booleans);
    graph_edge_features.index_put_({Slice(), 0, Slice()}, state.index({Slice(), Slice(14, 30)}));
    graph_edge_mask.index_put_({Slice(), 0}, true);
    auto candidate_features = torch::zeros({1, kCandidateCapacity, kCandidateFeatures}, floats);
    candidate_features.index_put_({Slice(), 0, Slice()}, state);
    auto candidate_family = torch::zeros({1, kCandidateCapacity}, integers);
    auto candidate_mask = torch::zeros({1, kCandidateCapacity}, booleans);
    candidate_mask.index_put_({Slice(), 0}, true);
    auto family_mask = torch::zeros({1, kFamilyCount}, booleans);
    family_mask.index_put_({Slice(), 0}, true);
    ScalablePolicyInput base{
        structured, global, regional, local, companies, towns, industries, stations, vehicles,
        graph_nodes, graph_node_mask, graph_edge_index, graph_edge_features, graph_edge_mask,
        candidate_features, candidate_family, candidate_mask, family_mask,
        batch.hidden_state.to(device), batch.recurrent_reset.to(device),
    };
    auto domain_tokens = torch::zeros({1, kM22DomainTokenCapacity, kM22DomainTokenFeatures}, floats);
    domain_tokens.index_put_({Slice(), 0, Slice(0, kM22EvaluationFeatureCount)}, state);
    auto domain_kind = torch::zeros({1, kM22DomainTokenCapacity}, integers);
    domain_kind.index_put_({Slice(), 0}, state.index({Slice(), Slice(0, 7)}).argmax(1));
    auto domain_mask = torch::zeros({1, kM22DomainTokenCapacity}, booleans);
    domain_mask.index_put_({Slice(), 0}, true);
    auto program_features = torch::zeros({1, kM22ProgramCount, kM22ProgramFeatures}, floats);
    for (std::int64_t program = 0; program < kM22ProgramCount; ++program) {
        program_features.index_put_({Slice(), program, program}, 1.0F);
        program_features.index_put_({Slice(), program, 17 + kProgramMode[static_cast<std::size_t>(program)]}, 1.0F);
        const auto capability = program == 0 ? torch::ones({1}, floats) : state.index({Slice(), 13 + program});
        program_features.index_put_({Slice(), program, 24}, capability);
        program_features.index_put_({Slice(), program, 25}, state.index({Slice(), 11}));
        program_features.index_put_({Slice(), program, 26}, state.index({Slice(), 12}));
        for (std::int64_t climate = 0; climate < 4; ++climate) {
            program_features.index_put_({Slice(), program, 27 + climate}, state.index({Slice(), 7 + climate}));
        }
        program_features.index_put_({Slice(), program, 31}, state.index({Slice(), kProgramMode[static_cast<std::size_t>(program)]}));
    }
    return {base, domain_tokens, domain_kind, domain_mask, program_features, batch.program_mask.to(device)};
}

M22EvaluationPolicy load_m22_evaluation_policy(
    const std::filesystem::path &checkpoint_path,
    const torch::Device &policy_device)
{
    if (!checkpoint_path.is_absolute() || !std::filesystem::is_directory(checkpoint_path) ||
        std::filesystem::is_symlink(checkpoint_path)) {
        throw std::invalid_argument("M22 evaluation checkpoint must be an absolute real directory");
    }
    if (policy_device.is_cuda()) {
        if (!torch::cuda::is_available() || !policy_device.has_index() || policy_device.index() != 0) {
            throw std::invalid_argument("M22 evaluation accepts only an available cuda:0 device");
        }
    } else if (!policy_device.is_cpu()) {
        throw std::invalid_argument("M22 evaluation accepts only cpu or cuda:0");
    }
    require_inventory(checkpoint_path);
    const auto manifest = parse_manifest(checkpoint_path / "m22.manifest");
    if (checkpoint_path.filename() != manifest.checkpoint_id || checkpoint_id(manifest) != manifest.checkpoint_id) {
        throw std::invalid_argument("M22 evaluation checkpoint identity mismatch");
    }
    const auto committed = read_bounded(checkpoint_path / "COMMITTED", 128);
    if (std::string(committed.begin(), committed.end()) != manifest.checkpoint_id + '\n' ||
        sha256_file(checkpoint_path / "model.pt") != manifest.model_sha ||
        sha256_file(checkpoint_path / "selection.json") != manifest.selection_sha) {
        throw std::invalid_argument("M22 evaluation model or development-selection identity mismatch");
    }
    GeneralistPolicy model(initialization_seed(manifest.run_seed), manifest.architecture);
    torch::load(model, (checkpoint_path / "model.pt").string());
    model->to(policy_device);
    model->eval();
    require_finite_generalist(model, "M22 optimizer-free evaluation load");
    return {manifest.checkpoint_id, manifest.architecture, manifest.run_seed, std::move(model)};
}

} // namespace openttd_rl::v2
