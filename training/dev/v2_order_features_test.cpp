#include "v2_live_input.h"
#include "checkpoint_io.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <unistd.h>
#include <torch/cuda.h>

namespace dev = openttd_rl::development;
namespace v2 = openttd_rl::v2;
namespace {
void check(bool ok, const char *message) { if (!ok) throw std::runtime_error(message); }
template <typename T> void put(std::vector<uint8_t> &bytes, size_t offset, T value)
{ std::memcpy(bytes.data() + offset, &value, sizeof(value)); }
void write(const std::filesystem::path &path, const std::vector<uint8_t> &bytes)
{
    std::ofstream output(path, std::ios::binary);
    output.write(reinterpret_cast<const char *>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
    check(static_cast<bool>(output), "fixture write failed");
}
template <typename Function> void rejected(Function function)
{
    bool failed = false;
    try { function(); } catch (const std::exception &) { failed = true; }
    check(failed, "incompatible order semantics were accepted");
}
}

int main(int argc, char **argv)
{
    try {
        if (argc != 2) throw std::invalid_argument("expected cpu|cuda:0");
        const torch::Device device(argv[1]);
        if (device.is_cuda() && !torch::cuda::is_available()) throw std::runtime_error("CUDA unavailable; no fallback");
        torch::set_num_threads(1);
        const auto mode = dev::FinancialFeatures::SignedLogOrdersV1;
        const auto categorical_mode = dev::FinancialFeatures::SignedLogOrdersV2;
        check(dev::parse_financial_features("signed-log-orders-v1") == mode, "orders mode parsing differs");
        check(dev::parse_financial_features("signed-log-orders-v2") == categorical_mode &&
            std::string_view(dev::financial_features_name(categorical_mode)) == "signed-log-orders-v2",
            "categorical orders mode parsing/name differs");
        const auto root = std::filesystem::temp_directory_path() / ("rl-order-features-" + std::to_string(::getpid()));
        check(std::filesystem::create_directory(root), "fresh fixture directory required");
        const auto obs = root / "obs.bin", candidate = root / "candidate.bin";
        std::vector<uint8_t> observation(2182927), bytes(790528);
        put(observation, 511 * 4, 1.0F);
        // Two co-located owned vehicles: identity, public order sequence and
        // loading flags must survive the actual native float32 reader.
        constexpr size_t vehicles = 1286927;
        for (size_t row = 0; row < 2; ++row) {
            put(observation, vehicles + (row * 40) * 4, static_cast<float>(row + 1) / 1048575.0F);
            put(observation, vehicles + (row * 40 + 2) * 4, 1.0F);
            put(observation, vehicles + (row * 40 + 13) * 4, 1.0F);
            put(observation, vehicles + (row * 40 + 16) * 4, 0.5F);
            put(observation, vehicles + (row * 40 + 20) * 4, static_cast<float>(97 + row * 48 * 256) / 65535.0F);
            put(observation, vehicles + (row * 40 + 21) * 4, 1.0F / 65535.0F);
            put(observation, vehicles + (row * 40 + 22) * 4, 512.0F / 65535.0F);
            put(observation, vehicles + (row * 40 + 23) * 4, 1000.0F / 65535.0F);
            observation[vehicles + 1024 * 40 * 4 + row] = 1;
        }
        const std::vector<std::array<uint32_t, 4>> rows{
            {5, 100, 116, 0}, {5, 101, 116, 0},
            {6, 0, 1U | (0x61U << 16), 0}, {6, 1, 1U | (0x61U << 16), 0},
            {6, 0, 1U | (1U << 8) | (0x61U << 16), 0},
            {6, 0, 1U | (0x61U << 16), 2}, {6, 0, 1U | (0x21U << 16), 0},
            {6, 0, 2U | (3U << 16), 0}, {6, 0, 2U | (3U << 16), 2},
            {6, 0, 2U | (3U << 16), 3}, {6, 0, 2U | (3U << 16), 4},
            {6, 0, 2U | (1U << 8) | (3U << 16), 3},
            {6, 1, 3, 0}, {6, 1, 3, 2}, {6, 2, 3, 0},
            {6, 1, 4, 0}, {6, 1, 4U | (1U << 8), 0},
            {7, 0, 0, 0}, {7, 1, 0, 0},
            {6, 0, 1U | (2U << 8) | (0x61U << 16), 0},
            {6, 0, 1U | (3U << 8) | (0x61U << 16), 0},
            {6, 0, 2U | (2U << 8) | (3U << 16), 3},
            {6, 0, 2U | (3U << 8) | (3U << 16), 3},
            {6, 1, 4U | (2U << 8), 0}, {6, 1, 4U | (3U << 8), 0}};
        // Independent semantic expectations: operation slots 0..3, loading
        // categories 4..7, and order positions 8..11. A copy has no position.
        const std::vector<std::vector<int64_t>> category_slots{
            {}, {}, {0, 8}, {0, 8}, {0, 9}, {0, 8}, {0, 8},
            {1, 4, 8}, {1, 5, 8}, {1, 6, 8}, {1, 7, 8}, {1, 6, 9},
            {2}, {2}, {2}, {3, 8}, {3, 9}, {}, {},
            {0, 10}, {0, 11}, {1, 6, 10}, {1, 6, 11}, {3, 10}, {3, 11}};
        check(category_slots.size() == rows.size(), "categorical expectation inventory differs");
        for (size_t row = 0; row < rows.size(); ++row) {
            put(bytes, row * 128 + rows[row][0] * 4, 1.0F);
            for (size_t word = 0; word < 4; ++word) put(bytes, 4096 * 128 + row * 64 + word * 4, rows[row][word]);
            bytes[790528 - 4096 + row] = 1;
        }
        write(obs, observation); write(candidate, bytes);
        const auto input = dev::read_live_v2_input(obs, candidate, mode);
        const auto categorical = dev::read_live_v2_input(obs, candidate, categorical_mode);
        check(torch::equal(input.candidate_features.slice(2, 20, 32), categorical.candidate_features.slice(2, 20, 32)),
            "categorical preprocessing changed exact parameter byte limbs");
        check(torch::equal(input.candidate_features.slice(2, 12, 20), categorical.candidate_features.slice(2, 12, 20)) &&
            torch::equal(input.candidate_family, categorical.candidate_family) &&
            torch::equal(input.candidate_mask, categorical.candidate_mask) && torch::equal(input.family_mask, categorical.family_mask),
            "categorical preprocessing changed family, mask, or noncategorical features");
        check(torch::equal(input.vehicles.features, categorical.vehicles.features), "categorical preprocessing changed public vehicle state");
        for (size_t row = 0; row < rows.size(); ++row) {
            const auto position = static_cast<int64_t>(row);
            if (rows[row][0] != 6) {
                check(torch::equal(input.candidate_features[0][position], categorical.candidate_features[0][position]),
                    "categorical order preprocessing changed a nonorder action");
                continue;
            }
            for (int64_t column = 0; column < 12; ++column) {
                const bool active = std::find(category_slots[row].begin(), category_slots[row].end(), column) != category_slots[row].end();
                check(categorical.candidate_features[0][position][column].item<float>() == (active ? 1.0F : 0.0F),
                    "order operation/loading/position categorical slot differs");
                check(input.candidate_features[0][position][column].item<float>() == (column == 6 ? 1.0F : 0.0F),
                    "archived orders-v1 native family slots changed");
            }
        }
        for (size_t row = 0; row < rows.size(); ++row) for (size_t other = 0; other < row; ++other)
            if (rows[row][0] == rows[other][0])
                check(!torch::equal(input.candidate_features[0][static_cast<int64_t>(row)],
                    input.candidate_features[0][static_cast<int64_t>(other)]), "supported order parameters alias");
        for (size_t row = 0; row < rows.size(); ++row) for (size_t other = 0; other < row; ++other)
            if (rows[row][0] == rows[other][0])
                check(!torch::equal(categorical.candidate_features[0][static_cast<int64_t>(row)],
                    categorical.candidate_features[0][static_cast<int64_t>(other)]), "categorical supported order parameters alias");
        check(input.vehicles.features[0][0][20].item<float>() != input.vehicles.features[0][1][20].item<float>(),
            "loading state absent from vehicle inputs");
        for (const auto old : {dev::FinancialFeatures::Raw, dev::FinancialFeatures::SignedLogV1,
                dev::FinancialFeatures::SignedLogLoanV1, dev::FinancialFeatures::SignedLogActionsV1})
            rejected([&] { (void)dev::read_live_v2_input(obs, candidate, old); });
        auto legacy = observation; put(legacy, 511 * 4, 0.0F); write(root / "legacy.bin", legacy);
        rejected([&] { (void)dev::read_live_v2_input(root / "legacy.bin", candidate, mode); });
        rejected([&] { (void)dev::read_live_v2_input(root / "legacy.bin", candidate, categorical_mode); });
        for (const auto descriptor : {0U, 5U, 4U | (4U << 8), 1U | (0x61U << 16) | (1U << 24), 3U | (1U << 8)}) {
            auto bad = bytes; put(bad, 4096 * 128 + 2 * 64 + 8, descriptor); write(root / "bad.bin", bad);
            rejected([&] { (void)dev::read_live_v2_input(obs, root / "bad.bin", mode); });
            rejected([&] { (void)dev::read_live_v2_input(obs, root / "bad.bin", categorical_mode); });
        }
        // The archived v1 reader accepted an insertion at position four. Keep
        // that compatibility, while v2's four categorical positions reject it.
        for (const auto descriptor : {1U | (4U << 8) | (0x61U << 16),
                2U | (4U << 8) | (3U << 16), 4U | (4U << 8)}) {
            auto bad = bytes; put(bad, 4096 * 128 + 2 * 64 + 8, descriptor); write(root / "index-four.bin", bad);
            if ((descriptor & 255U) == 1)
                (void)dev::read_live_v2_input(obs, root / "index-four.bin", mode);
            rejected([&] { (void)dev::read_live_v2_input(obs, root / "index-four.bin", categorical_mode); });
        }
        for (const auto &corruption : std::array<std::pair<size_t, float>, 3>{{{6, 0.0F}, {6, 0.5F}, {5, 1.0F}}}) {
            auto bad = bytes; put(bad, 2 * 128 + corruption.first * 4, corruption.second); write(root / "onehot.bin", bad);
            rejected([&] { (void)dev::read_live_v2_input(obs, root / "onehot.bin", categorical_mode); });
        }
        v2::ScalablePolicy model(20261002); model->to(device); model->eval();
        const auto on_device = dev::live_v2_to(input, device);
        torch::NoGradGuard guard;
        const auto expected = model->forward(on_device);
        torch::serialize::OutputArchive saved; dev::write_live_v2_weights(saved, model, mode);
        std::stringstream stream; saved.save_to(stream); const auto serialized = stream.str();
        torch::serialize::InputArchive restored; std::stringstream source(serialized); restored.load_from(source, device);
        v2::ScalablePolicy reloaded(0); reloaded->to(device); dev::read_live_v2_weights(restored, reloaded, mode);
        check(torch::equal(expected.candidate_logits, reloaded->forward(on_device).candidate_logits), "order model reload changed outputs");
        std::stringstream wrong_source(serialized); torch::serialize::InputArchive wrong; wrong.load_from(wrong_source, device);
        rejected([&] { dev::read_live_v2_weights(wrong, reloaded, dev::FinancialFeatures::SignedLogActionsV1); });
        std::stringstream wrong_categorical_source(serialized); torch::serialize::InputArchive wrong_categorical;
        wrong_categorical.load_from(wrong_categorical_source, device);
        rejected([&] { dev::read_live_v2_weights(wrong_categorical, reloaded, categorical_mode); });
        const auto categorical_on_device = dev::live_v2_to(categorical, device);
        check(categorical_on_device.candidate_features.device() == device, "categorical fixture did not use requested device");
        const auto categorical_expected = model->forward(categorical_on_device);
        torch::serialize::OutputArchive categorical_saved;
        dev::write_live_v2_weights(categorical_saved, model, categorical_mode);
        std::stringstream categorical_stream; categorical_saved.save_to(categorical_stream);
        const auto categorical_serialized = categorical_stream.str();
        std::stringstream categorical_source(categorical_serialized); torch::serialize::InputArchive categorical_restored;
        categorical_restored.load_from(categorical_source, device);
        dev::read_live_v2_weights(categorical_restored, reloaded, categorical_mode);
        check(torch::equal(categorical_expected.candidate_logits, reloaded->forward(categorical_on_device).candidate_logits),
            "categorical order model reload changed outputs");
        std::stringstream wrong_v1_source(categorical_serialized); torch::serialize::InputArchive wrong_v1;
        wrong_v1.load_from(wrong_v1_source, device);
        rejected([&] { dev::read_live_v2_weights(wrong_v1, reloaded, mode); });
        // Matching preprocessing text alone cannot smuggle old semantics.
        torch::serialize::OutputArchive incomplete, policy; model->save(policy);
        incomplete.write("development_preprocessed_policy", policy);
        dev::checkpoint_string(incomplete, dev::kFinancialFeaturesArchiveKey, "signed-log-orders-v1");
        std::stringstream incomplete_stream; incomplete.save_to(incomplete_stream);
        torch::serialize::InputArchive missing; missing.load_from(incomplete_stream, device);
        rejected([&] { dev::read_live_v2_weights(missing, reloaded, mode); });
        std::cout << "{\"status\":\"passed\",\"device\":\"" << device << "\",\"legal_rows\":" << rows.size()
            << ",\"exact_order_distinctions\":true,\"v2_categorical_slots\":true,\"v1_v2_archive_mismatch_rejected\":true,"
            << "\"model_and_tensor_compatibility\":true}" << std::endl;
        std::filesystem::remove_all(root);
        return 0;
    } catch (const std::exception &error) { std::cerr << error.what() << '\n'; return 1; }
}
