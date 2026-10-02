#include "v2_live_input.h"

#include <array>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unistd.h>
#include <vector>
#include <torch/cuda.h>
#include <torch/csrc/autograd/autograd.h>

namespace dev = openttd_rl::development;
namespace v2 = openttd_rl::v2;
namespace {
constexpr size_t kObservationBytes = 2182927;
constexpr size_t kCandidateBytes = 790528;
constexpr size_t kFeatureBytes = 4096 * 32 * 4;
constexpr size_t kMaskOffset = kFeatureBytes + 4096 * 16 * 4;
using Parameters = std::array<uint32_t, 4>;

void check(bool condition, const char *message)
{
    if (!condition) throw std::runtime_error(message);
}

void write(const std::filesystem::path &path, const std::vector<uint8_t> &bytes)
{
    std::ofstream stream(path, std::ios::binary);
    stream.write(reinterpret_cast<const char *>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
    check(static_cast<bool>(stream), "fixture write failed");
}

template <typename T>
void store(std::vector<uint8_t> &bytes, size_t offset, T value)
{
    std::memcpy(bytes.data() + offset, &value, sizeof(value));
}

std::vector<uint8_t> fixture(const std::vector<Parameters> &rows)
{
    std::vector<uint8_t> bytes(kCandidateBytes);
    for (size_t row = 0; row < rows.size(); ++row) {
        const auto &p = rows[row];
        store(bytes, row * 128 + p[0] * 4, 1.0F);
        store(bytes, row * 128 + 12 * 4, 1.0F);
        store(bytes, row * 128 + 13 * 4, 0.000125F);
        // Same native geometry and priority for every action in a family.
        // Identity and orientation must come from parameters, never row order.
        store(bytes, row * 128 + 14 * 4, 0.5F);
        store(bytes, row * 128 + 15 * 4, 0.25F);
        for (size_t word = 0; word < p.size(); ++word)
            store(bytes, kFeatureBytes + row * 64 + word * 4, p[word]);
        bytes[kMaskOffset + row] = 1;
    }
    return bytes;
}

void expect_rejected(const std::filesystem::path &observation, const std::filesystem::path &candidates)
{
    bool refused = false;
    try { (void)dev::read_live_v2_input(observation, candidates, dev::FinancialFeatures::SignedLogActionsV1); }
    catch (const std::invalid_argument &) { refused = true; }
    check(refused, "new action encoding accepted an unknown parameter or occupied reserved feature");
}
} // namespace

int main(int argc, char **argv)
{
    try {
        if (argc != 2) throw std::invalid_argument("expected cpu|cuda:0");
        const torch::Device device(argv[1]);
        if (device.is_cuda() && !torch::cuda::is_available()) throw std::runtime_error("CUDA unavailable; no fallback");
        torch::set_num_threads(1);
        check(::setenv("CUBLAS_WORKSPACE_CONFIG", ":4096:8", 1) == 0, "cannot configure cuBLAS");
        at::globalContext().setDeterministicAlgorithms(true, false);
        const auto mode = dev::FinancialFeatures::SignedLogActionsV1;
        check(dev::parse_financial_features("signed-log-actions-v1") == mode &&
            std::string(dev::financial_features_name(mode)) == "signed-log-actions-v1", "new mode name does not round-trip");
        const auto root = std::filesystem::temp_directory_path() / ("rl-action-features-" + std::to_string(::getpid()));
        check(std::filesystem::create_directory(root), "test requires a fresh artifact directory");
        const auto observation = root / "observation.bin", candidates = root / "candidates.bin";
        write(observation, std::vector<uint8_t>(kObservationBytes));

        std::vector<Parameters> rows{
            {0, 0, 0, 0},
            {1, 1, 2, 0}, {1, 2, 1, 0}, {1, 3, 2, 0},
            {2, 100, 5, 1}, {2, 100, 10, 1}, {2, 101, 5, 1},
            {3, 100, 0, 0}, {3, 100, 1, 0}, {3, 100, 2, 0}, {3, 100, 3, 0},
            {4, 100, 0, 0}, {4, 100, 1, 0}, {4, 100, 2, 0}, {4, 100, 3, 0},
            {5, 100, 116, 0}, {5, 100, 117, 0}, {5, 101, 116, 0},
            {6, 1, 3, 4}, {6, 2, 3, 4}, {6, 1, 4, 3}, {6, 1, 5, 4}, {6, 1, 3, 6},
            {11, 1, 10000, 0}, {11, 2, 10000, 0},
        };
        for (uint32_t family = 7; family <= 10; ++family)
            for (uint32_t identity : {1U, 2U, 0xfffffffeU, 0xffffffffU}) rows.push_back({family, identity, 0, 0});
        // Exercise every possible byte at every limb, including byte carries and
        // adjacent uint32 values that cannot be distinguished by one float32.
        for (uint32_t value = 0; value < 256; ++value) {
            const auto word = value * 0x01010101U;
            rows.push_back({6, word, word, word});
        }
        for (uint32_t word : {255U, 256U, 65535U, 65536U, 16777215U, 16777216U, 0xfffffffeU, 0xffffffffU}) {
            rows.push_back({6, word, 1, 2});
            rows.push_back({6, 1, word, 2});
            rows.push_back({6, 1, 2, word});
        }
        auto bytes = fixture(rows);
        // Masked padding is not an action and may contain uninterpreted data.
        const size_t padding = rows.size() + 1;
        store(bytes, padding * 128 + 25 * 4, 0.75F);
        store(bytes, kFeatureBytes + padding * 64, std::numeric_limits<uint32_t>::max());
        store(bytes, kFeatureBytes + padding * 64 + 15 * 4, std::numeric_limits<uint32_t>::max());
        write(candidates, bytes);
        const auto raw = dev::read_live_v2_input(observation, candidates, dev::FinancialFeatures::Raw);
        const auto old = dev::read_live_v2_input(observation, candidates, dev::FinancialFeatures::SignedLogV1);
        const auto loan = dev::read_live_v2_input(observation, candidates, dev::FinancialFeatures::SignedLogLoanV1);
        const auto input = dev::read_live_v2_input(observation, candidates, mode);
        std::vector<float> native_features(kFeatureBytes / sizeof(float));
        std::memcpy(native_features.data(), bytes.data(), kFeatureBytes);
        const auto expected_raw = torch::from_blob(native_features.data(), {1, 4096, 32}, torch::kFloat32);
        check(torch::equal(raw.candidate_features, expected_raw), "raw preprocessing no longer preserves native candidate features");
        check(torch::equal(raw.candidate_features.slice(2, 0, 13), old.candidate_features.slice(2, 0, 13)) &&
            torch::equal(raw.candidate_features.slice(2, 14, 32), old.candidate_features.slice(2, 14, 32)), "old signed-log action features changed");
        check(torch::equal(old.candidate_features.slice(2, 0, 30), loan.candidate_features.slice(2, 0, 30)), "old loan mode changed nonreserved features");
        check(torch::equal(old.candidate_features.slice(2, 0, 20), input.candidate_features.slice(2, 0, 20)), "new action mode changed native nonreserved features");
        check(torch::equal(old.structured, input.structured) && torch::equal(old.companies.features, input.companies.features), "new action mode changed signed-log finances");
        check(torch::equal(old.candidate_mask, input.candidate_mask) && torch::equal(old.candidate_family, input.candidate_family) &&
            torch::equal(old.family_mask, input.family_mask), "new action mode changed native masks or families");
        const auto padded_row = static_cast<int64_t>(padding);
        check(torch::equal(old.candidate_features[0][padded_row], input.candidate_features[0][padded_row]), "new mode interpreted masked padding");

        size_t distinguished_pairs = 0;
        for (size_t row = 0; row < rows.size(); ++row) {
            const auto &p = rows[row];
            const auto tensor_row = static_cast<int64_t>(row);
            if (p[0] == 11) {
                check(loan.candidate_features[0][tensor_row][30].item<float>() == (p[1] == 1 ? 1.0F : 0.0F) &&
                    loan.candidate_features[0][tensor_row][31].item<float>() == (p[1] == 2 ? 1.0F : 0.0F), "old loan direction features changed");
            } else {
                check(torch::equal(old.candidate_features[0][tensor_row], loan.candidate_features[0][tensor_row]), "old loan mode changed another action family");
            }
            for (size_t word = 1; word <= 3; ++word) for (size_t limb = 0; limb < 4; ++limb) {
                const auto byte = (p[word] >> (limb * 8)) & 255U;
                const double expected = std::log1p(static_cast<double>(byte)) / std::log(256.0);
                const auto slot = static_cast<int64_t>(20 + (word - 1) * 4 + limb);
                const auto actual = input.candidate_features[0][tensor_row][slot].item<float>();
                check(std::abs(static_cast<double>(actual) - expected) < 1e-7, "action limb value or position differs");
            }
            for (size_t other = 0; other < row; ++other) if (p[0] == rows[other][0] && p != rows[other]) {
                const auto tensor_other = static_cast<int64_t>(other);
                check(torch::equal(old.candidate_features[0][tensor_row], old.candidate_features[0][tensor_other]), "fixture did not reproduce legacy same-feature actions");
                check(!torch::equal(input.candidate_features[0][tensor_row], input.candidate_features[0][tensor_other]), "distinct public parameters still alias after encoding");
                ++distinguished_pairs;
            }
        }

        // Every reserved feature and every trailing parameter must fail closed
        // when occupied by a legal row. Historical modes retain their behavior.
        for (size_t word = 4; word < 16; ++word) {
            auto malformed = bytes;
            store(malformed, kFeatureBytes + 4 * 64 + word * 4, uint32_t{1});
            write(root / "invalid.bin", malformed);
            expect_rejected(observation, root / "invalid.bin");
        }
        for (size_t feature = 20; feature < 32; ++feature) {
            auto malformed = bytes;
            store(malformed, 4 * 128 + feature * 4, 0.5F);
            write(root / "invalid.bin", malformed);
            expect_rejected(observation, root / "invalid.bin");
        }
        (void)dev::read_live_v2_input(observation, root / "invalid.bin", dev::FinancialFeatures::Raw);
        (void)dev::read_live_v2_input(observation, root / "invalid.bin", dev::FinancialFeatures::SignedLogV1);
        for (const auto &[word, value] : std::vector<std::pair<size_t, uint32_t>>{{1, 0}, {1, 3}, {2, 20000}}) {
            auto malformed = bytes;
            store(malformed, kFeatureBytes + 23 * 64 + word * 4, value);
            write(root / "invalid.bin", malformed);
            expect_rejected(observation, root / "invalid.bin");
        }

        // Reversing row order must reverse outputs, not change action meaning.
        auto reordered = bytes;
        for (size_t row = 0; row < 4096; ++row) {
            const size_t from = 4095 - row;
            std::memcpy(reordered.data() + row * 128, bytes.data() + from * 128, 128);
            std::memcpy(reordered.data() + kFeatureBytes + row * 64, bytes.data() + kFeatureBytes + from * 64, 64);
            reordered[kMaskOffset + row] = bytes[kMaskOffset + from];
        }
        write(root / "reordered.bin", reordered);
        const auto reversed = dev::read_live_v2_input(observation, root / "reordered.bin", mode);
        check(torch::equal(input.candidate_features.flip({1}), reversed.candidate_features) &&
            torch::equal(input.candidate_family.flip({1}), reversed.candidate_family) &&
            torch::equal(input.candidate_mask.flip({1}), reversed.candidate_mask), "encoding depends on candidate row order");
        v2::ScalablePolicy model(20261002);
        model->to(device);
        model->eval();
        const auto on_device = dev::live_v2_to(input, device), reversed_device = dev::live_v2_to(reversed, device);
        // Test the real policy path: each requested semantic difference must
        // permit a gradient that changes the corresponding logit contrast.
        // These are numerical fixtures, never manufactured human labels.
        const auto gradient_output = model->forward(on_device);
        const std::vector<std::pair<int64_t, int64_t>> contrasts{
            {1, 2}, {4, 5}, {7, 8}, {11, 12}, {15, 16},
            {18, 19}, {18, 20}, {18, 21}, {18, 22},
            {25, 26}, {29, 30}, {33, 34}, {37, 38}, {23, 24},
        };
        double minimum_contrast_gradient = std::numeric_limits<double>::infinity();
        for (const auto &[left, right] : contrasts) {
            const auto contrast = gradient_output.candidate_logits[0][left] - gradient_output.candidate_logits[0][right];
            const auto gradients = torch::autograd::grad({contrast}, {model->candidate_projection->weight}, {}, true);
            check(gradients.size() == 1 && torch::isfinite(gradients[0]).all().item<bool>(), "semantic contrast gradient is nonfinite");
            const auto magnitude = gradients[0].abs().max().item<double>();
            check(magnitude > 1e-7, "public action distinction did not reach a trainable policy contrast");
            minimum_contrast_gradient = std::min(minimum_contrast_gradient, magnitude);
        }
        torch::NoGradGuard guard;
        const auto original_output = model->forward(on_device), reversed_output = model->forward(reversed_device);
        check(torch::allclose(original_output.candidate_logits.flip({1}), reversed_output.candidate_logits, 1e-6, 1e-6), "policy candidate logits depend on row order");
        const auto original_distribution = dev::live_v2_distribution(original_output, on_device);
        const auto reversed_distribution = dev::live_v2_distribution(reversed_output, reversed_device);
        check(torch::allclose(original_distribution.probabilities.flip({1}), reversed_distribution.probabilities, 1e-5, 1e-7), "policy candidate probabilities depend on row order");

        std::stringstream archive_bytes;
        torch::serialize::OutputArchive saved;
        dev::write_live_v2_weights(saved, model, mode);
        saved.save_to(archive_bytes);
        const auto serialized = archive_bytes.str();
        for (auto wrong_mode : {dev::FinancialFeatures::Raw, dev::FinancialFeatures::SignedLogV1, dev::FinancialFeatures::SignedLogLoanV1}) {
            std::stringstream source(serialized);
            torch::serialize::InputArchive loaded;
            loaded.load_from(source, device);
            v2::ScalablePolicy wrong(0);
            bool refused = false;
            try { dev::read_live_v2_weights(loaded, wrong, wrong_mode); }
            catch (const std::invalid_argument &) { refused = true; }
            check(refused, "new action archive accepted historical preprocessing");
        }
        std::stringstream source(serialized);
        torch::serialize::InputArchive loaded;
        loaded.load_from(source, device);
        v2::ScalablePolicy restored(0);
        restored->to(device);
        dev::read_live_v2_weights(loaded, restored, mode);
        check(torch::equal(original_output.candidate_logits, restored->forward(on_device).candidate_logits), "new action archive reload changed outputs");
        std::cout << "{\"status\":\"passed\",\"fixture\":\"synthetic-public-action-parameters\",\"device\":\"" << device
            << "\",\"legal_rows\":" << rows.size() << ",\"same_family_distinct_pairs\":" << distinguished_pairs
            << ",\"semantic_gradient_contrasts\":" << contrasts.size() << ",\"minimum_contrast_gradient\":" << minimum_contrast_gradient
            << ",\"all_bytes_checked\":true,\"legacy_unchanged\":true,\"permutation_equivariant\":true,"
            << "\"unknown_schema_rejected\":true,\"wrong_preprocessing_rejected\":true}" << std::endl;
        std::filesystem::remove_all(root);
        return 0;
    } catch (const std::exception &error) { std::cerr << error.what() << '\n'; return 1; }
}
