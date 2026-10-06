#include "v2_live_input.h"
#include "checkpoint_io.h"

#include <algorithm>
#include <bit>
#include <cmath>
#include <cstring>
#include <fstream>
#include <limits>
#include <map>
#include <memory>
#include <set>
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

// Candidate-local entity binding, computed only from the current public tensor.
// The explicit v3-only tensor projection removes redundant native vehicle
// coordinates and binds marker 2. Every slot 14..19 must be zero on arrival.
class OrderContext {
public:
    explicit OrderContext(const ScalablePolicyInput &input)
    {
        const auto vehicles = input.vehicles.features.accessor<float, 3>();
        const auto vehicle_mask = input.vehicles.mask.accessor<bool, 2>();
        const auto stations = input.stations.features.accessor<float, 3>();
        const auto station_mask = input.stations.mask.accessor<bool, 2>();
        for (int64_t row = 0; row < kStationCapacity; ++row) if (station_mask[0][row] && stations[0][row][3] == 1.0F) {
            const auto id = integer(stations[0][row][0], 63999, 63999);
            if (!stations_.emplace(id, stations[0][row][5]).second)
                throw std::invalid_argument("v3 duplicate public station identity");
        }
        for (int64_t row = 0; row < kVehicleCapacity; ++row) if (vehicle_mask[0][row] && vehicles[0][row][2] == 1.0F) {
            const auto *values = &vehicles[0][row][0];
            Vehicle vehicle;
            vehicle.stopped = integer(values[13], 1, 1);
            const auto count = integer(values[16], 4, 4);
            if (values[38] != 0 || values[39] != 0)
                throw std::invalid_argument("v3 requires independent supported public orders");
            std::set<uint32_t> assigned;
            for (uint32_t index = 0; index < count; ++index) {
                const auto type = integer(values[20 + index * 4], 65535, 65535) & 255U;
                if (type != 0x21 && type != 0x61)
                    throw std::invalid_argument("v3 requires canonical station orders");
                const auto destination = integer(values[21 + index * 4], 65535, 63999);
                vehicle.orders.push_back(destination);
                assigned.insert(destination);
            }
            for (uint32_t index = count; index < 4; ++index)
                for (uint32_t column = 0; column < 4; ++column)
                    if (values[20 + index * 4 + column] != 0)
                        throw std::invalid_argument("v3 requires zero padded public orders");
            for (const auto station : assigned) ++assigned_[station];
            // Pinned 15.3 VehicleID pool End is 0xFF000 (the invalid sentinel
            // is 0xFFFFF). Native Unit uses End-1, not the sentinel.
            const auto id = integer(values[0], 1044479, 1044479);
            if (!vehicles_.emplace(id, std::move(vehicle)).second)
                throw std::invalid_argument("v3 duplicate public vehicle identity");
        }
    }

    void encode(float *features, const uint32_t *parameters) const
    {
        const auto found = vehicles_.find(parameters[1]);
        if (found == vehicles_.end()) throw std::invalid_argument("v3 target vehicle missing from public tensor");
        const auto &vehicle = found->second;
        for (size_t column = 14; column < 20; ++column)
            if (features[column] != 0) throw std::invalid_argument("v3 requires unused order slots 14..19");
        const auto operation = parameters[2] & 255U, index = (parameters[2] >> 8) & 255U;
        bool has_station = operation != 3;
        uint32_t station = parameters[3];
        if (operation == 1) {
            if (vehicle.orders.size() >= 4 || index > vehicle.orders.size())
                throw std::invalid_argument("v3 insertion position differs from public orders");
        } else if (operation == 2 || operation == 4) {
            if (index >= vehicle.orders.size()) throw std::invalid_argument("v3 order index differs from public orders");
            station = vehicle.orders[index];
        } else if (operation == 3) {
            const auto source = vehicles_.find(parameters[3]);
            if (source == vehicles_.end() || source->second.orders.empty() || parameters[1] == parameters[3])
                throw std::invalid_argument("v3 copy source missing or unsupported");
        }
        features[14] = has_station && std::find(vehicle.orders.begin(), vehicle.orders.end(), station) != vehicle.orders.end() ? 1.0F : 0.0F;
        features[15] = operation == 1 && ((index > 0 && vehicle.orders[index - 1] == station) ||
            (index < vehicle.orders.size() && vehicle.orders[index] == station)) ? 1.0F : 0.0F;
        features[16] = static_cast<float>(vehicle.orders.size()) / 4.0F;
        features[17] = static_cast<float>(vehicle.stopped);
        features[18] = 0; features[19] = 0;
        if (has_station) {
            const auto stop = stations_.find(station);
            if (stop == stations_.end()) throw std::invalid_argument("v3 candidate station missing from public tensor");
            const auto buses = assigned_.find(station);
            features[18] = static_cast<float>(std::log1p(buses == assigned_.end() ? 0 : buses->second) / std::log1p(1024.0));
            if (stop->second < 0 || stop->second > 1) throw std::invalid_argument("v3 public waiting count outside native bounds");
            features[19] = static_cast<float>(std::log1p(static_cast<double>(stop->second) * 65535) / std::log1p(65535.0));
        }
    }
private:
    static uint32_t integer(float value, double divisor, uint32_t maximum)
    {
        const double decoded = static_cast<double>(value) * divisor;
        const auto rounded = std::round(decoded);
        if (rounded < 0 || rounded > maximum ||
                value != static_cast<float>(rounded) / static_cast<float>(divisor))
            throw std::invalid_argument("v3 public categorical value outside exact native encoding");
        return static_cast<uint32_t>(rounded);
    }
    struct Vehicle { uint32_t stopped{}; std::vector<uint32_t> orders; };
    std::map<uint32_t, Vehicle> vehicles_;
    std::map<uint32_t, float> stations_;
    std::map<uint32_t, uint32_t> assigned_;
};
} // namespace

FinancialFeatures parse_financial_features(std::string_view name)
{
    if (name == "raw") return FinancialFeatures::Raw;
    if (name == "signed-log-v1") return FinancialFeatures::SignedLogV1;
    if (name == "signed-log-loan-v1") return FinancialFeatures::SignedLogLoanV1;
    if (name == "signed-log-actions-v1") return FinancialFeatures::SignedLogActionsV1;
    if (name == "signed-log-orders-v1") return FinancialFeatures::SignedLogOrdersV1;
    if (name == "signed-log-orders-v2") return FinancialFeatures::SignedLogOrdersV2;
    if (name == "signed-log-orders-v3") return FinancialFeatures::SignedLogOrdersV3;
    throw std::invalid_argument("unknown financial/action preprocessing mode");
}

const char *financial_features_name(FinancialFeatures mode)
{
    if (mode == FinancialFeatures::Raw) return "raw";
    if (mode == FinancialFeatures::SignedLogV1) return "signed-log-v1";
    if (mode == FinancialFeatures::SignedLogLoanV1) return "signed-log-loan-v1";
    if (mode == FinancialFeatures::SignedLogActionsV1) return "signed-log-actions-v1";
    if (mode == FinancialFeatures::SignedLogOrdersV1) return "signed-log-orders-v1";
    if (mode == FinancialFeatures::SignedLogOrdersV2) return "signed-log-orders-v2";
    if (mode == FinancialFeatures::SignedLogOrdersV3) return "signed-log-orders-v3";
    throw std::invalid_argument("unknown financial feature mode");
}

void transform_live_v2_finances(ScalablePolicyInput &input, FinancialFeatures mode)
{
    if (mode == FinancialFeatures::Raw) return;
    if (mode != FinancialFeatures::SignedLogV1 && mode != FinancialFeatures::SignedLogLoanV1 &&
        mode != FinancialFeatures::SignedLogActionsV1 && !uses_order_features(mode))
        throw std::invalid_argument("unknown financial feature mode");
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
    if (uses_order_features(mode)) {
        checkpoint_string(archive, "development_observation_schema", kOrdersObservationSchema);
        checkpoint_string(archive, "development_action_semantics", kOrdersActionSemantics);
    }
}

FinancialFeatures read_financial_features(torch::serialize::InputArchive &archive)
{
    torch::Tensor value;
    if (!archive.try_read(kFinancialFeaturesArchiveKey, value, true)) return FinancialFeatures::Raw;
    if (value.scalar_type() != torch::kUInt8 || value.dim() != 1 || value.numel() == 0 || value.numel() > 64)
        throw std::invalid_argument("financial feature metadata shape/type differs");
    value = value.cpu().contiguous();
    const auto mode = parse_financial_features(std::string_view(static_cast<const char *>(value.const_data_ptr()), static_cast<size_t>(value.numel())));
    // Shared by inference archives and complete PPO checkpoints so neither
    // reader can silently accept another order/observation interpretation.
    if (uses_order_features(mode)) {
        auto require_tag = [&](const char *key, std::string_view expected) {
            torch::Tensor tag;
            if (!archive.try_read(key, tag, true) || tag.scalar_type() != torch::kUInt8 || tag.dim() != 1 ||
                tag.numel() != static_cast<int64_t>(expected.size()))
                throw std::invalid_argument("orders model schema metadata missing or malformed");
            tag = tag.cpu().contiguous();
            if (std::string_view(static_cast<const char *>(tag.const_data_ptr()), expected.size()) != expected)
                throw std::invalid_argument("orders model schema metadata differs");
        };
        require_tag("development_observation_schema", kOrdersObservationSchema);
        require_tag("development_action_semantics", kOrdersActionSemantics);
    }
    return mode;
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
    // A binary marker binds this opt-in projection even when callers bypass
    // Python metadata checks. Historical archives and tensors stay unchanged.
    const float orders_marker = input.structured[0][511].item<float>();
    const float expected_marker = financial_features == FinancialFeatures::SignedLogOrdersV3 ? 2.0F :
        (uses_order_features(financial_features) ? 1.0F : 0.0F);
    if (orders_marker != expected_marker)
        throw std::invalid_argument("orders observation/preprocessing schema differs");
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
    const auto order_context = financial_features == FinancialFeatures::SignedLogOrdersV3 ?
        std::make_unique<OrderContext>(input) : nullptr;
    for (int64_t row = 0; row < kCandidateCapacity; ++row) if (mask[row]) {
        auto family = parameters[static_cast<size_t>(row * 16)];
        if (family >= kFamilyCount) throw std::invalid_argument("native V2 candidate family exceeds inventory");
        families[row] = family;
        family_mask[family] = true;
        if (financial_features == FinancialFeatures::SignedLogActionsV1 || uses_order_features(financial_features)) {
            // M15 exposes three active uint32 parameters after the family.
            // Keep every bit: a direct float cast aliases large adjacent IDs,
            // and normalized priority already aliases small co-located IDs.
            // Slots 20..31 contain p1, p2, p3 in little-endian byte order.
            // log1p(byte)/log(256) is injective on all 256 byte values and
            // gives small IDs a useful scale without changing public meaning.
            if (input.candidate_features[0][row].slice(0, 20, 32).abs().sum().item<float>() != 0.0F)
                throw std::invalid_argument("action feature encoding requires unused reserved slots 20..31");
            for (size_t parameter = 4; parameter < 16; ++parameter)
                if (parameters[static_cast<size_t>(row * 16) + parameter] != 0)
                    throw std::invalid_argument("action feature encoding requires unused trailing parameters 4..15");
            if (family == 11 && ((parameters[static_cast<size_t>(row * 16 + 1)] != 1 &&
                parameters[static_cast<size_t>(row * 16 + 1)] != 2) ||
                parameters[static_cast<size_t>(row * 16 + 2)] != 10000))
                throw std::invalid_argument("action feature encoding requires native borrow/repay 10000");
            if (uses_order_features(financial_features) && family == 6) {
                const auto descriptor = parameters[static_cast<size_t>(row * 16 + 2)];
                const auto value = parameters[static_cast<size_t>(row * 16 + 3)];
                const auto operation = descriptor & 255U, index = (descriptor >> 8) & 255U;
                const auto type = (descriptor >> 16) & 255U, flags = descriptor >> 24;
                const bool insert = operation == 1 && index <= 4 && (type == 0x21 || type == 0x61) && flags == 0 && value < 65535;
                const bool load = operation == 2 && index < 4 && type == 3 && flags == 0 &&
                    (value == 0 || value == 2 || value == 3 || value == 4);
                const bool copy = operation == 3 && descriptor == 3;
                const bool remove = operation == 4 && index < 4 && type == 0 && flags == 0 && value == 0;
                if (!insert && !load && !copy && !remove)
                    throw std::invalid_argument("unsupported orders-v1 primitive parameters");
            }
            for (size_t parameter = 1; parameter <= 3; ++parameter) {
                const auto value = parameters[static_cast<size_t>(row * 16) + parameter];
                for (size_t byte = 0; byte < 4; ++byte)
                    input.candidate_features[0][row][static_cast<int64_t>(20 + (parameter - 1) * 4 + byte)] =
                        static_cast<float>(std::log1p(static_cast<double>((value >> (8 * byte)) & 255U)) / std::log(256.0));
            }
            if ((financial_features == FinancialFeatures::SignedLogOrdersV2 ||
                    financial_features == FinancialFeatures::SignedLogOrdersV3) && family == 6) {
                // These are unordered public categories. The archived v1 fit
                // consistently chose endpoint value NoLoad=4 over FullAny=3.
                // Family already reaches the model via its learned embedding;
                // reuse only its redundant native one-hot slots for categories.
                // All exact uint32 limbs remain intact. No label/row is read.
                for (int64_t column = 0; column < 12; ++column)
                    if (input.candidate_features[0][row][column].item<float>() != (column == 6 ? 1.0F : 0.0F))
                        throw std::invalid_argument("categorical order features require native family one-hot slots");
                const auto descriptor = parameters[static_cast<size_t>(row * 16 + 2)];
                const auto operation = descriptor & 255U, index = (descriptor >> 8) & 255U;
                const auto value = parameters[static_cast<size_t>(row * 16 + 3)];
                if (operation != 3 && index >= 4)
                    throw std::invalid_argument("categorical order index outside supported four orders");
                input.candidate_features[0][row].slice(0, 0, 12).zero_();
                input.candidate_features[0][row][static_cast<int64_t>(operation - 1)] = 1.0F;
                if (operation == 2)
                    input.candidate_features[0][row][static_cast<int64_t>(4 + (value == 0 ? 0 : value - 1))] = 1.0F;
                if (operation != 3) input.candidate_features[0][row][static_cast<int64_t>(8 + index)] = 1.0F;
                if (order_context) order_context->encode(input.candidate_features[0][row].data_ptr<float>(),
                    parameters.data() + row * 16);
            }
        }
        if (financial_features == FinancialFeatures::SignedLogLoanV1 && family == 11) {
            const auto direction = parameters[static_cast<size_t>(row * 16 + 1)];
            const auto amount = parameters[static_cast<size_t>(row * 16 + 2)];
            if ((direction != 1 && direction != 2) || amount != 10000 ||
                input.candidate_features[0][row].slice(0, 30, 32).abs().sum().item<float>() != 0.0F)
                throw std::invalid_argument("loan feature encoding requires native borrow/repay 10000 and unused reserved slots");
            // Original float priority rounds UINT32_MAX-1 and -2 to the same
            // value. Preserve the exact public action meaning explicitly.
            input.candidate_features[0][row][direction == 1 ? 30 : 31] = 1.0F;
        }
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
