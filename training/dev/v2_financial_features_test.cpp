#include "v2_live_input.h"
#include "checkpoint_io.h"
#include <algorithm>
#include <cmath>
#include <functional>
#include <iostream>
#include <sstream>
#include <stdexcept>

namespace {
namespace dev = openttd_rl::development;
namespace v2 = openttd_rl::v2;

void require(bool condition, const char *message)
{
    if (!condition) throw std::runtime_error(message);
}

void rejects(const std::function<void()> &function)
{
    try { function(); }
    catch (const std::invalid_argument &) { return; }
    throw std::runtime_error("invalid financial metadata/mode was accepted");
}

double oracle(float value, double divisor)
{
    const double amount = static_cast<double>(value) * divisor;
    return std::copysign(std::log1p(std::abs(amount)) / std::log1p(1.0e9), amount);
}
} // namespace

int main()
{
    try {
        torch::set_num_threads(1);
        v2::ScalablePolicyInput input;
        input.structured = torch::full({2, v2::kStructuredFeatures}, 0.125F);
        input.structured.index_put_({0, 8}, 0.0001F);
        input.structured.index_put_({0, 9}, 0.00003F);
        input.structured.index_put_({1, 8}, -0.00002F);
        input.structured.index_put_({1, 9}, 0.0F);
        input.companies.features = torch::zeros({2, v2::kCompanyCapacity, v2::kCompanyFeatures});
        input.companies.features.select(1, 0).fill_(0.125F);
        input.companies.features.index_put_({0, 0, 2}, 0.0001F);
        input.companies.features.index_put_({0, 0, 3}, 0.00003F);
        input.companies.features.index_put_({0, 0, 4}, 0.0003F);
        input.companies.features.index_put_({1, 0, 2}, -0.00002F);
        input.companies.features.index_put_({1, 0, 3}, 0.0F);
        input.companies.features.index_put_({1, 0, 4}, 1.0F);
        input.candidate_features = torch::full({2, v2::kCandidateCapacity, v2::kCandidateFeatures}, 0.125F);
        input.candidate_features.select(2, 13).copy_(torch::linspace(-1.0F, 1.0F, v2::kCandidateCapacity).repeat({2, 1}));
        input.candidate_features.index_put_({0, 0, 13}, 0.0F);
        input.candidate_features.index_put_({0, 1, 13}, 0.1F); // Same currency amount as structured cash.
        const auto structured = input.structured.clone();
        const auto companies = input.companies.features.clone();
        const auto candidates = input.candidate_features.clone();
        dev::transform_live_v2_finances(input, dev::FinancialFeatures::Raw);
        require(torch::equal(input.structured, structured) && torch::equal(input.companies.features, companies) &&
            torch::equal(input.candidate_features, candidates), "raw mode changed inputs");
        dev::transform_live_v2_finances(input, dev::FinancialFeatures::SignedLogV1);
        double maximum_error = 0;
        auto compare = [&](const torch::Tensor &actual, const torch::Tensor &before, double divisor) {
            const auto a = actual.flatten(), b = before.flatten();
            for (int64_t i = 0; i < a.numel(); ++i)
                maximum_error = std::max(maximum_error, std::abs(a[i].item<double>() - oracle(b[i].item<float>(), divisor)));
        };
        compare(input.structured.slice(1, 8, 10), structured.slice(1, 8, 10), 1.0e9);
        compare(input.companies.features.slice(2, 2, 5), companies.slice(2, 2, 5), 1.0e9);
        compare(input.candidate_features.select(2, 13), candidates.select(2, 13), 1.0e6);
        require(maximum_error <= 2.0e-7, "signed-log transform exceeds scalar-oracle tolerance");
        require(input.structured[1][9].item<float>() == 0 && input.candidate_features[0][0][13].item<float>() == 0 &&
            input.companies.features.slice(1, 1).abs().sum().item<float>() == 0, "zero/redacted fields changed");
        require(input.structured[1][8].item<float>() < 0, "negative balance lost its sign");
        require(std::abs(input.structured[0][8].item<float>() - input.candidate_features[0][1][13].item<float>()) <= 2.0e-7F,
            "equal currency uses inconsistent feature scales");
        input.structured.slice(1, 8, 10).copy_(structured.slice(1, 8, 10));
        input.companies.features.slice(2, 2, 5).copy_(companies.slice(2, 2, 5));
        input.candidate_features.select(2, 13).copy_(candidates.select(2, 13));
        require(torch::equal(input.structured, structured) && torch::equal(input.companies.features, companies) &&
            torch::equal(input.candidate_features, candidates), "nonfinancial feature changed");
        for (auto mode : {dev::FinancialFeatures::Raw, dev::FinancialFeatures::SignedLogV1}) {
            torch::serialize::OutputArchive archive;
            archive.write("sentinel", torch::ones({1}), true);
            dev::write_financial_features(archive, mode);
            std::stringstream stream;
            archive.save_to(stream); stream.seekg(0);
            torch::serialize::InputArchive loaded;
            loaded.load_from(stream);
            require(dev::read_financial_features(loaded) == mode, "financial metadata did not roundtrip");
            require(dev::parse_financial_features(dev::financial_features_name(mode)) == mode, "mode name did not roundtrip");
        }
        rejects([] { (void)dev::parse_financial_features("signed-log-v2"); });
        rejects([] { (void)dev::parse_financial_features(" raw"); });
        for (bool malformed_type : {false, true}) {
            torch::serialize::OutputArchive archive;
            if (malformed_type) archive.write(dev::kFinancialFeaturesArchiveKey, torch::ones({1}), true);
            else dev::checkpoint_string(archive, dev::kFinancialFeaturesArchiveKey, "unknown");
            std::stringstream stream;
            archive.save_to(stream); stream.seekg(0);
            torch::serialize::InputArchive loaded;
            loaded.load_from(stream);
            rejects([&] { (void)dev::read_financial_features(loaded); });
        }
        std::cout << "Financial scalar oracle, raw preservation, signed/zero fields, currency consistency, metadata and rejection checks passed; max error "
            << maximum_error << '\n';
        return 0;
    } catch (const std::exception &error) { std::cerr << error.what() << '\n'; return 1; }
}
