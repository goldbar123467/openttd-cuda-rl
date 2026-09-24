#pragma once

#include <filesystem>
#include <string_view>
#include "openttd_rl/v2/scalable_policy.h"
#include "openttd_rl/training/ppo.h"

namespace openttd_rl::development {
inline constexpr const char *kLiveV2TensorSchema = "openttd-rl-development-v2-public-tensors-1";
enum class FinancialFeatures { Raw, SignedLogV1 };
inline constexpr const char *kFinancialFeaturesArchiveKey = "development_financial_features";
FinancialFeatures parse_financial_features(std::string_view name);
const char *financial_features_name(FinancialFeatures mode);
void transform_live_v2_finances(openttd_rl::v2::ScalablePolicyInput &input, FinancialFeatures mode);
void write_financial_features(torch::serialize::OutputArchive &archive, FinancialFeatures mode);
FinancialFeatures read_financial_features(torch::serialize::InputArchive &archive);
void write_live_v2_weights(torch::serialize::OutputArchive &archive,
    const openttd_rl::v2::ScalablePolicy &model, FinancialFeatures mode);
void read_live_v2_weights(torch::serialize::InputArchive &archive,
    openttd_rl::v2::ScalablePolicy &model, FinancialFeatures mode);

// The existing native M15 binary layouts, with seed features explicitly zero.
openttd_rl::v2::ScalablePolicyInput read_live_v2_input(
    const std::filesystem::path &observation, const std::filesystem::path &candidates,
    FinancialFeatures financial_features = FinancialFeatures::Raw);
openttd_rl::v2::ScalablePolicyInput live_v2_to(
    const openttd_rl::v2::ScalablePolicyInput &input, const torch::Device &device);
openttd_rl::training::MaskedPolicy live_v2_distribution(
    const openttd_rl::v2::ScalablePolicyOutput &output,
    const openttd_rl::v2::ScalablePolicyInput &input);
} // namespace openttd_rl::development
