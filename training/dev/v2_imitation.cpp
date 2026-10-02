#include "v2_imitation.h"
#include <algorithm>
#include <charconv>
#include <cmath>
#include <fstream>
#include <map>
#include <set>
#include <stdexcept>

namespace openttd_rl::development {
namespace {
std::vector<std::string> split(const std::string &line, char separator)
{
    std::vector<std::string> parts;
    size_t begin = 0;
    do {
        const auto end = line.find(separator, begin);
        parts.push_back(line.substr(begin, end == std::string::npos ? end : end - begin));
        if (parts.back().empty()) throw std::invalid_argument("empty imitation manifest field");
        if (end == std::string::npos) return parts;
        begin = end + 1;
    } while (true);
}

int64_t integer(const std::string &value, int64_t maximum)
{
    int64_t result = -1;
    const auto parsed = std::from_chars(value.data(), value.data() + value.size(), result);
    if (parsed.ec != std::errc{} || parsed.ptr != value.data() + value.size() || result < 0 || result >= maximum)
        throw std::invalid_argument("imitation row/family outside native inventory");
    return result;
}
} // namespace

ImitationInputAliases audit_imitation_inputs(const openttd_rl::v2::ScalablePolicyInput &input, int64_t action)
{
    if (input.candidate_mask.dim() != 2 || input.candidate_mask.size(0) != 1 || action < 0 ||
        action >= input.candidate_mask.size(1) || !input.candidate_mask[0][action].item<bool>())
        throw std::invalid_argument("imitation input audit requires one legal target");
    const auto features = input.candidate_features.to(torch::kCPU).contiguous();
    const auto families = input.candidate_family.to(torch::kCPU).contiguous();
    const auto mask = input.candidate_mask.to(torch::kCPU).contiguous();
    if (features.dim() != 3 || features.size(0) != 1 || features.size(1) != mask.size(1) ||
        features.scalar_type() != torch::kFloat32 || families.sizes() != mask.sizes() ||
        families.scalar_type() != torch::kInt64 || mask.scalar_type() != torch::kBool ||
        !torch::isfinite(features).all().item<bool>())
        throw std::invalid_argument("imitation input audit requires finite native candidate features");
    // Exact numeric float equality matches the network boundary, including +0
    // and -0. Family embeddings distinguish identical vectors across families.
    std::map<std::pair<int64_t, std::vector<float>>, std::vector<int64_t>> groups;
    const auto *feature_data = features.data_ptr<float>();
    const auto *family_data = families.data_ptr<int64_t>();
    const auto *mask_data = mask.data_ptr<bool>();
    const auto width = features.size(2);
    for (int64_t row = 0; row < mask.size(1); ++row) {
        if (!mask_data[row]) continue;
        const auto *first = feature_data + row * width;
        groups[{family_data[row], std::vector<float>(first, first + width)}].push_back(row);
    }
    ImitationInputAliases result;
    for (const auto &[features_key, rows] : groups) {
        (void)features_key;
        if (rows.size() < 2) continue;
        ++result.group_count;
        result.candidate_count += rows.size();
        if (std::find(rows.begin(), rows.end(), action) != rows.end())
            for (const auto row : rows) if (row != action) result.target_rows.push_back(row);
    }
    return result;
}

ImitationPrediction measure_imitation_prediction(const openttd_rl::v2::ScalablePolicyInput &input,
    const torch::Tensor &probabilities, int64_t action, const ImitationInputAliases &aliases)
{
    if (input.candidate_mask.dim() != 2 || input.candidate_mask.size(0) != 1 ||
        probabilities.sizes() != input.candidate_mask.sizes() || action < 0 || action >= probabilities.size(1) ||
        !input.candidate_mask[0][action].item<bool>())
        throw std::invalid_argument("imitation prediction requires one legal target and aligned probabilities");
    const auto values = probabilities.to(torch::kCPU, torch::kFloat64).contiguous();
    const auto mask = input.candidate_mask.to(torch::kCPU).contiguous();
    const auto *value_data = values.data_ptr<double>();
    const auto *mask_data = mask.data_ptr<bool>();
    ImitationPrediction result;
    result.predicted_row = -1;
    result.target_probability = value_data[action];
    size_t alternatives = 0;
    for (int64_t row = 0; row < values.size(1); ++row) {
        const auto value = value_data[row];
        if (!std::isfinite(value) || value < 0.0 || value > 1.0 || (!mask_data[row] && value != 0.0))
            throw std::runtime_error("invalid or illegal candidate probability in imitation evaluation");
        if (!mask_data[row]) continue;
        if (result.predicted_row < 0 || value > value_data[result.predicted_row]) result.predicted_row = row;
        if (row != action) {
            ++alternatives;
            result.best_alternative_probability = std::max(result.best_alternative_probability, value);
        }
    }
    result.target_probability_margin = result.target_probability - result.best_alternative_probability;
    result.row_correct = result.predicted_row == action;
    result.target_tied = alternatives > 0 && std::abs(result.target_probability_margin) <= kImitationProbabilityMargin;
    result.unique_exact = result.row_correct && aliases.target_rows.empty() &&
        result.target_probability_margin > kImitationProbabilityMargin;
    return result;
}

std::vector<ImitationExample> read_imitation_examples(const std::filesystem::path &manifest,
    FinancialFeatures financial_features)
{
    using namespace openttd_rl::v2;
    if (!manifest.is_absolute() || !std::filesystem::is_regular_file(manifest) ||
        std::filesystem::file_size(manifest) > 16U * 1024U * 1024U)
        throw std::invalid_argument("imitation manifest must be a bounded absolute file");
    std::ifstream stream(manifest);
    std::string line;
    if (!std::getline(stream, line) || line != kImitationManifest)
        throw std::invalid_argument("imitation manifest schema differs");
    std::vector<ImitationExample> result;
    std::set<std::pair<std::string, std::string>> identities;
    while (std::getline(stream, line)) {
        if (line.size() > 65536 || result.size() >= 512)
            throw std::invalid_argument("imitation manifest exceeds development bounds");
        const auto parts = split(line, '\t');
        if (parts.size() != 7 || !identities.emplace(parts[1], parts[0]).second)
            throw std::invalid_argument("imitation columns or unique game/sample identity differ");
        auto input = read_live_v2_input(parts[2], parts[3], financial_features);
        const auto action = integer(parts[4], kCandidateCapacity), family = integer(parts[5], kFamilyCount);
        // Compare every legal row, not merely the label. A filtered or stale
        // mask changes the supervised likelihood and must fail closed.
        auto expected = torch::zeros_like(input.candidate_mask);
        int64_t previous = -1;
        for (const auto &value : split(parts[6], ',')) {
            const auto row = integer(value, kCandidateCapacity);
            if (row <= previous) throw std::invalid_argument("imitation legal rows must be sorted and unique");
            expected[0][row] = true;
            previous = row;
        }
        if (!torch::equal(expected, input.candidate_mask) || !input.candidate_mask[0][action].item<bool>() ||
            input.candidate_family[0][action].item<int64_t>() != family)
            throw std::invalid_argument("imitation label/family or exact native legal mask differs");
        input.recurrent_reset.fill_(true);
        result.push_back({parts[0], parts[1], std::move(input), action, family});
    }
    if (!stream.eof() || result.empty()) throw std::invalid_argument("imitation manifest is empty or unreadable");
    return result;
}

torch::Tensor imitation_loss(const openttd_rl::v2::ScalablePolicyOutput &output,
    const openttd_rl::v2::ScalablePolicyInput &input, int64_t action)
{
    if (input.candidate_mask.size(0) != 1 || action < 0 || action >= input.candidate_mask.size(1) ||
        !input.candidate_mask[0][action].item<bool>())
        throw std::invalid_argument("imitation target must be an exact legal native candidate row");
    const auto loss = -live_v2_distribution(output, input).log_probabilities[0][action];
    if (!torch::isfinite(loss).item<bool>()) throw std::runtime_error("nonfinite imitation loss");
    return loss;
}
} // namespace openttd_rl::development
