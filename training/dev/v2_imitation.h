#pragma once

#include "v2_live_input.h"
#include <filesystem>
#include <string>
#include <vector>

namespace openttd_rl::development {
inline constexpr const char *kImitationManifest = "openttd-rl-development-v2-imitation-1";
struct ImitationExample {
    std::string sample_id, game_id;
    openttd_rl::v2::ScalablePolicyInput input;
    int64_t action{}, family{};
};

inline constexpr double kImitationProbabilityMargin = 1e-6;
struct ImitationInputAliases {
    size_t group_count{}, candidate_count{};
    // Excludes the target itself; rows have the same family and exactly equal
    // encoded features, so the shared candidate scorer cannot distinguish them.
    std::vector<int64_t> target_rows;
};
struct ImitationPrediction {
    int64_t predicted_row{};
    double target_probability{}, best_alternative_probability{}, target_probability_margin{};
    bool row_correct{}, target_tied{}, unique_exact{};
};

ImitationInputAliases audit_imitation_inputs(const openttd_rl::v2::ScalablePolicyInput &input, int64_t action);
ImitationPrediction measure_imitation_prediction(const openttd_rl::v2::ScalablePolicyInput &input,
    const torch::Tensor &probabilities, int64_t action, const ImitationInputAliases &aliases);

// Sparse supported decisions are independent reset-context examples. Missing
// commands and elapsed simulation time are never relabelled as WAIT samples.
std::vector<ImitationExample> read_imitation_examples(const std::filesystem::path &manifest,
    FinancialFeatures financial_features);
torch::Tensor imitation_loss(const openttd_rl::v2::ScalablePolicyOutput &output,
    const openttd_rl::v2::ScalablePolicyInput &input, int64_t action);
} // namespace openttd_rl::development
