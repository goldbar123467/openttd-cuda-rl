#include "v2_live_input.h"
#include "checkpoint_io.h"

#include <bit>
#include <cmath>
#include <cstring>
#include <fstream>
#include <limits>
#include <stdexcept>
#include <vector>

namespace openttd_rl::development {
namespace {
using namespace openttd_rl::v2;

class Reader {
public:
    Reader(const std::filesystem::path &path, size_t expected) : data_(expected)
    {
        static_assert(std::endian::native == std::endian::little);
        if (!path.is_absolute() || !std::filesystem::is_regular_file(path) || std::filesystem::file_size(path) != expected)
            throw std::invalid_argument("live V2 tensor file path/size differs");
        std::ifstream stream(path, std::ios::binary);
        stream.read(reinterpret_cast<char *>(data_.data()), static_cast<std::streamsize>(expected));
        if (!stream || stream.peek() != std::char_traits<char>::eof()) throw std::runtime_error("live V2 tensor read failed");
    }
    torch::Tensor floats(std::initializer_list<int64_t> shape)
    {
        size_t count = 1;
        for (int64_t size : shape) count *= static_cast<size_t>(size);
        require(count * sizeof(float));
        std::vector<float> aligned(count);
        std::memcpy(aligned.data(), data_.data() + position_, count * sizeof(float));
        position_ += count * sizeof(float);
        auto result = torch::from_blob(aligned.data(), shape, torch::kFloat32).clone();
        if (!torch::isfinite(result).all().item<bool>()) throw std::invalid_argument("nonfinite native V2 features");
        return result;
    }
    torch::Tensor mask(int64_t count)
    {
        require(static_cast<size_t>(count));
        for (int64_t index = 0; index < count; ++index)
            if (data_[position_ + static_cast<size_t>(index)] > 1) throw std::invalid_argument("native V2 mask is not binary");
        auto result = torch::from_blob(data_.data() + position_, {1, count}, torch::kUInt8).to(torch::kBool);
        position_ += static_cast<size_t>(count);
        return result;
    }
    std::vector<uint32_t> words(size_t count)
    {
        require(count * sizeof(uint32_t));
        std::vector<uint32_t> result(count);
        std::memcpy(result.data(), data_.data() + position_, count * sizeof(uint32_t));
        position_ += count * sizeof(uint32_t);
        return result;
    }
    void finished() const
    {
        if (position_ != data_.size()) throw std::invalid_argument("unconsumed native V2 tensor bytes");
    }
private:
    void require(size_t bytes) const
    {
        if (bytes > data_.size() - position_) throw std::invalid_argument("truncated native V2 tensor section");
    }
    std::vector<uint8_t> data_;
    size_t position_{};
};
} // namespace

FinancialFeatures parse_financial_features(std::string_view name)
{
    if (name == "raw") return FinancialFeatures::Raw;
    if (name == "signed-log-v1") return FinancialFeatures::SignedLogV1;
    throw std::invalid_argument("financial features must be raw or signed-log-v1");
}

const char *financial_features_name(FinancialFeatures mode)
{
    if (mode == FinancialFeatures::Raw) return "raw";
    if (mode == FinancialFeatures::SignedLogV1) return "signed-log-v1";
    throw std::invalid_argument("unknown financial feature mode");
}

void transform_live_v2_finances(ScalablePolicyInput &input, FinancialFeatures mode)
{
    if (mode == FinancialFeatures::Raw) return;
    if (mode != FinancialFeatures::SignedLogV1) throw std::invalid_argument("unknown financial feature mode");
    // Native financial fields use different linear divisors. Recover their
    // bounded currency units and apply one signed logarithmic scale. Zero and
    // redacted/padded fields remain zero; no extra information enters the model.
    auto transform = [](const torch::Tensor &values, double native_divisor) {
        return torch::sign(values) * torch::log1p(values.abs() * native_divisor) / std::log1p(1.0e9);
    };
    auto cash_loan = input.structured.slice(1, 8, 10);
    cash_loan.copy_(transform(cash_loan, 1.0e9));
    auto company_money = input.companies.features.slice(2, 2, 5);
    company_money.copy_(transform(company_money, 1.0e9));
    auto candidate_cost = input.candidate_features.select(2, 13);
    candidate_cost.copy_(transform(candidate_cost, 1.0e6));
}

void write_financial_features(torch::serialize::OutputArchive &archive, FinancialFeatures mode)
{
    // Omit the tag for legacy raw models, preserving their inference archives.
    if (mode != FinancialFeatures::Raw) checkpoint_string(archive, kFinancialFeaturesArchiveKey, financial_features_name(mode));
}

FinancialFeatures read_financial_features(torch::serialize::InputArchive &archive)
{
    torch::Tensor value;
    if (!archive.try_read(kFinancialFeaturesArchiveKey, value, true)) return FinancialFeatures::Raw;
    if (value.scalar_type() != torch::kUInt8 || value.dim() != 1 || value.numel() == 0 || value.numel() > 64)
        throw std::invalid_argument("financial feature metadata shape/type differs");
    value = value.cpu().contiguous();
    return parse_financial_features(std::string_view(static_cast<const char *>(value.const_data_ptr()), static_cast<size_t>(value.numel())));
}

void write_live_v2_weights(torch::serialize::OutputArchive &archive, const ScalablePolicy &model, FinancialFeatures mode)
{
    if (mode == FinancialFeatures::Raw) {
        model->save(archive);
    } else {
        // A tag alone is insufficient: legacy Module::load ignores extra keys.
        // Nest preprocessed weights so raw-only readers fail on missing weights.
        torch::serialize::OutputArchive policy;
        model->save(policy);
        archive.write("development_preprocessed_policy", policy);
        write_financial_features(archive, mode);
    }
}

void read_live_v2_weights(torch::serialize::InputArchive &archive, ScalablePolicy &model, FinancialFeatures mode)
{
    if (read_financial_features(archive) != mode)
        throw std::invalid_argument("inference weights require different financial preprocessing");
    if (mode == FinancialFeatures::Raw) {
        model->load(archive);
    } else {
        torch::serialize::InputArchive policy;
        archive.read("development_preprocessed_policy", policy);
        model->load(policy);
    }
}

openttd_rl::v2::ScalablePolicyInput read_live_v2_input(
    const std::filesystem::path &observation, const std::filesystem::path &candidates, FinancialFeatures financial_features)
{
    Reader reader(observation, 2182927);
    ScalablePolicyInput input;
    input.structured = reader.floats({1, kStructuredFeatures});
    if (input.structured.slice(1, 13, 16).abs().sum().item<float>() != 0.0F)
        throw std::invalid_argument("live V2 policy refuses unredacted seed features");
    input.global_spatial = reader.floats({1, kSpatialChannels, 64, 64});
    input.regional_spatial = reader.floats({1, kSpatialChannels, 64, 64});
    input.local_spatial = reader.floats({1, kSpatialChannels, 32, 32});
    auto table = [&](int64_t count, int64_t features) {
        auto values = reader.floats({1, count, features});
        return EntityTable{values, reader.mask(count)};
    };
    input.companies = table(kCompanyCapacity, kCompanyFeatures);
    input.towns = table(kTownCapacity, kTownFeatures);
    input.industries = table(kIndustryCapacity, kIndustryFeatures);
    input.stations = table(kStationCapacity, kStationFeatures);
    input.vehicles = table(kVehicleCapacity, kVehicleFeatures);
    if (input.vehicles.features.slice(2, 7, 9).abs().sum().item<float>() != 0.0F)
        throw std::invalid_argument("live V2 policy refuses private breakdown countdown features");
    std::pair<float, float> previous{-1.0F, -1.0F};
    for (int64_t row = 0; row < kVehicleCapacity; ++row) if (input.vehicles.mask[0][row].item<bool>()) {
        const auto values = input.vehicles.features[0][row];
        const std::pair<float, float> identity{values[2].item<float>() == 1.0F ? 0.0F : 1.0F, values[0].item<float>()};
        if (identity <= previous) throw std::invalid_argument("live vehicle rows must follow public identity order");
        previous = identity;
    }
    input.graph_nodes = reader.floats({1, kGraphNodeCapacity, kGraphNodeFeatures});
    input.graph_node_mask = reader.mask(kGraphNodeCapacity);
    input.graph_edge_features = reader.floats({1, kGraphEdgeCapacity, kGraphEdgeFeatures});
    input.graph_edge_mask = reader.mask(kGraphEdgeCapacity);
    input.graph_edge_index = torch::round(input.graph_edge_features.slice(2, 0, 2) * 2047).to(torch::kInt64);
    reader.finished();

    Reader actions(candidates, 790528);
    input.candidate_features = actions.floats({1, kCandidateCapacity, kCandidateFeatures});
    const auto parameters = actions.words(static_cast<size_t>(kCandidateCapacity * 16));
    input.candidate_mask = actions.mask(kCandidateCapacity);
    input.candidate_family = torch::zeros({1, kCandidateCapacity}, torch::kInt64);
    input.family_mask = torch::zeros({1, kFamilyCount}, torch::kBool);
    auto *families = input.candidate_family.data_ptr<int64_t>();
    auto *family_mask = input.family_mask.data_ptr<bool>();
    const auto *mask = input.candidate_mask.data_ptr<bool>();
    for (int64_t row = 0; row < kCandidateCapacity; ++row) if (mask[row]) {
        auto family = parameters[static_cast<size_t>(row * 16)];
        if (family >= kFamilyCount) throw std::invalid_argument("native V2 candidate family exceeds inventory");
        families[row] = family;
        family_mask[family] = true;
    }
    actions.finished();
    input.hidden_state = torch::zeros({1, kHiddenSize}, torch::kFloat32);
    input.recurrent_reset = torch::zeros({1}, torch::kBool);
    transform_live_v2_finances(input, financial_features);
    return input;
}

openttd_rl::v2::ScalablePolicyInput live_v2_to(const ScalablePolicyInput &input, const torch::Device &device)
{
    auto table = [&](const EntityTable &value) { return EntityTable{value.features.to(device), value.mask.to(device)}; };
    return {input.structured.to(device), input.global_spatial.to(device), input.regional_spatial.to(device),
        input.local_spatial.to(device), table(input.companies), table(input.towns), table(input.industries),
        table(input.stations), table(input.vehicles), input.graph_nodes.to(device), input.graph_node_mask.to(device),
        input.graph_edge_index.to(device), input.graph_edge_features.to(device), input.graph_edge_mask.to(device),
        input.candidate_features.to(device), input.candidate_family.to(device), input.candidate_mask.to(device),
        input.family_mask.to(device), input.hidden_state.to(device), input.recurrent_reset.to(device)};
}

openttd_rl::training::MaskedPolicy live_v2_distribution(const ScalablePolicyOutput &output, const ScalablePolicyInput &input)
{
    using openttd_rl::training::masked_categorical;
    const auto family = masked_categorical(output.family_logits, input.family_mask);
    auto family_ids = torch::arange(kFamilyCount, input.candidate_family.options()).view({1, kFamilyCount, 1});
    const auto membership = (input.candidate_family.unsqueeze(1) == family_ids) & input.candidate_mask.unsqueeze(1);
    const auto expanded = output.candidate_logits.unsqueeze(1).expand({-1, kFamilyCount, -1});
    auto masked = expanded.masked_fill(~membership, -std::numeric_limits<float>::infinity());
    // An absent family needs a finite dummy reduction. logsumexp(all -inf)
    // has undefined gradients even when a later where discards that result.
    masked = torch::where(input.family_mask.unsqueeze(2), masked, torch::zeros_like(masked));
    const auto partition = torch::logsumexp(masked, 2);
    const auto safe_partition = torch::where(input.family_mask, partition, torch::zeros_like(partition));
    // P(candidate) = P(family) * P(candidate | family), so a large family quota
    // does not automatically receive more sampling mass than the WAIT family.
    const auto logits = output.candidate_logits - safe_partition.gather(1, input.candidate_family) +
        family.log_probabilities.gather(1, input.candidate_family);
    return masked_categorical(torch::where(input.candidate_mask, logits, torch::zeros_like(logits)), input.candidate_mask);
}
} // namespace openttd_rl::development
