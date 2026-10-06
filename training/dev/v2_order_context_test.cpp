#include "v2_live_input.h"
#include <array>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>
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
    std::ofstream stream(path, std::ios::binary);
    stream.write(reinterpret_cast<const char *>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
    check(static_cast<bool>(stream), "fixture write failed");
}
template <typename F> void rejected(F action)
{
    bool failed = false;
    try { action(); } catch (const std::exception &) { failed = true; }
    check(failed, "v3 incompatible input was accepted");
}
}
int main(int argc, char **argv)
{
    try {
        check(argc == 2, "expected cpu|cuda:0");
        const torch::Device device(argv[1]);
        if (device.is_cuda() && !torch::cuda::is_available()) throw std::runtime_error("CUDA unavailable; no fallback");
        torch::set_num_threads(1);
        const auto mode = dev::FinancialFeatures::SignedLogOrdersV3;
        check(dev::parse_financial_features("signed-log-orders-v3") == mode &&
            std::string_view(dev::financial_features_name(mode)) == "signed-log-orders-v3", "v3 mode differs");
        const auto root = std::filesystem::temp_directory_path() / ("rl-order-context-" + std::to_string(::getpid()));
        check(std::filesystem::create_directory(root), "fresh fixture required");
        std::vector<uint8_t> observation(2182927), candidates(790528);
        put(observation, 511 * 4, 2.0F);
        constexpr size_t vehicles = 1286927, stations = 1220879;
        for (size_t row = 0; row < 2; ++row) {
            put(observation, vehicles + row * 160, static_cast<float>(row * 9) / 1044479.0F);
            put(observation, vehicles + row * 160 + 2 * 4, 1.0F);
            put(observation, vehicles + row * 160 + 13 * 4, row == 0 ? 1.0F : 0.0F);
            put(observation, vehicles + row * 160 + 16 * 4, row == 0 ? 0.75F : 0.5F);
            for (size_t index = 0; index < (row == 0 ? 3U : 2U); ++index) {
                put(observation, vehicles + (row * 40 + 20 + index * 4) * 4, 97.0F / 65535.0F);
                put(observation, vehicles + (row * 40 + 21 + index * 4) * 4, index == 1 ? 3.0F / 65535.0F : 0.0F);
            }
            observation[vehicles + 1024 * 160 + row] = 1;
        }
        for (size_t row = 0; row < 3; ++row) {
            const uint32_t id = row == 0 ? 0U : row == 1 ? 3U : 500U;
            put(observation, stations + row * 128, static_cast<float>(id) / 63999.0F);
            put(observation, stations + row * 128 + 3 * 4, 1.0F);
            put(observation, stations + row * 128 + 5 * 4, row == 0 ? 100.0F / 65535.0F : 0.0F);
            observation[stations + 512 * 128 + row] = 1;
        }
        const std::vector<std::array<uint32_t, 4>> parameters{
            {6, 0, 1U | (0x61U << 16), 0}, // Duplicate adjacent to the first order.
            {6, 0, 1U | (0x61U << 16), 3}, // In the list, but not adjacent here.
            {6, 0, 1U | (0x61U << 16), 500}, // New stop, empty queue, no assigned bus.
            {6, 0, 1U | (3U << 8) | (0x61U << 16), 0}, // Duplicate at append position.
            {6, 9, 1U | (0x61U << 16), 0},
            {6, 0, 2U | (3U << 16), 3}, {6, 0, 4, 0}, {6, 9, 3, 0}, {7, 0, 0, 0}};
        for (size_t row = 0; row < parameters.size(); ++row) {
            put(candidates, row * 128 + parameters[row][0] * 4, 1.0F);
            for (size_t word = 0; word < 4; ++word) put(candidates, 524288 + row * 64 + word * 4, parameters[row][word]);
            candidates[790528 - 4096 + row] = 1;
        }
        const auto obs = root / "obs.bin", action = root / "actions.bin";
        write(obs, observation); write(action, candidates);
        const auto input = dev::read_live_v2_input(obs, action, mode);
        auto features = input.candidate_features.accessor<float, 3>();
        for (int64_t row : {0, 1, 3, 4, 5, 6}) check(features[0][row][14] == 1, "existing-stop match differs");
        for (int64_t row : {0, 3, 4}) check(features[0][row][15] == 1, "adjacent duplicate differs");
        check(features[0][1][15] == 0 && features[0][2][14] == 0 && features[0][2][15] == 0, "nonadjacent/new stop differs");
        check(features[0][0][16] == 0.75F && features[0][4][16] == 0.5F &&
            features[0][0][17] == 1 && features[0][4][17] == 0, "target count/stopped state differs");
        const auto buses = static_cast<float>(std::log1p(2.0) / std::log1p(1024.0));
        check(std::abs(features[0][0][18] - buses) < 1e-7F && features[0][2][18] == 0,
            "assigned buses must count each bus once, including stopped buses");
        check(features[0][0][19] > 0.4F && features[0][1][19] == 0 && features[0][2][19] == 0, "public waiting count differs");
        for (int64_t column : {14, 15, 18, 19}) check(features[0][7][column] == 0, "copy has no station argument");
        auto old_observation = observation; put(old_observation, 511 * 4, 1.0F);
        write(root / "old.bin", old_observation);
        const auto old = dev::read_live_v2_input(root / "old.bin", action, dev::FinancialFeatures::SignedLogOrdersV2);
        check(torch::equal(old.candidate_features.slice(2, 0, 14), input.candidate_features.slice(2, 0, 14)) &&
            torch::equal(old.candidate_features.slice(2, 20, 32), input.candidate_features.slice(2, 20, 32)) &&
            torch::equal(old.candidate_mask, input.candidate_mask) && torch::equal(old.candidate_family, input.candidate_family),
            "v3 changed categories, exact limbs, actions or masks");
        check(torch::equal(old.candidate_features[0][8], input.candidate_features[0][8]), "v3 changed nonorder candidate");
        rejected([&] { (void)dev::read_live_v2_input(obs, action, dev::FinancialFeatures::SignedLogOrdersV2); });
        rejected([&] { (void)dev::read_live_v2_input(root / "old.bin", action, mode); });
        for (size_t column = 14; column < 20; ++column) {
            auto bad = candidates; put(bad, column * 4, 0.25F); write(root / "occupied.bin", bad);
            rejected([&] { (void)dev::read_live_v2_input(obs, root / "occupied.bin", mode); });
        }
        for (const auto &corruption : std::array<std::pair<size_t, uint32_t>, 3>{{{4, 42}, {12, 499}, {8, 1U | (4U << 8) | (0x61U << 16)}}}) {
            auto bad = candidates; put(bad, 524288 + corruption.first, corruption.second); write(root / "bad.bin", bad);
            rejected([&] { (void)dev::read_live_v2_input(obs, root / "bad.bin", mode); });
        }
        auto permuted = candidates;
        for (size_t row = 0; row < parameters.size(); ++row) {
            const auto other = parameters.size() - row - 1;
            std::memcpy(permuted.data() + row * 128, candidates.data() + other * 128, 128);
            std::memcpy(permuted.data() + 524288 + row * 64, candidates.data() + 524288 + other * 64, 64);
        }
        write(root / "permuted.bin", permuted);
        const auto reordered = dev::read_live_v2_input(obs, root / "permuted.bin", mode);
        for (size_t row = 0; row < parameters.size(); ++row)
            check(torch::equal(input.candidate_features[0][static_cast<int64_t>(row)],
                reordered.candidate_features[0][static_cast<int64_t>(parameters.size() - row - 1)]), "v3 entity binding depends on row order");
        v2::ScalablePolicy model(20261002); model->eval();
        torch::NoGradGuard guard;
        const auto expected = dev::live_v2_distribution(model->forward(input), input).probabilities;
        model->to(device);
        const auto on_device = dev::live_v2_to(input, device);
        const auto actual = dev::live_v2_distribution(model->forward(on_device), on_device).probabilities.cpu();
        check((expected - actual).abs().max().item<float>() < 1e-6F, "v3 CPU/CUDA probabilities differ");
        torch::serialize::OutputArchive archive; dev::write_live_v2_weights(archive, model, mode);
        std::stringstream stream; archive.save_to(stream); const auto data = stream.str();
        for (const auto requested : {mode, dev::FinancialFeatures::SignedLogOrdersV2}) {
            std::stringstream source(data); torch::serialize::InputArchive loaded; loaded.load_from(source, device);
            if (requested != mode) rejected([&] { dev::read_live_v2_weights(loaded, model, requested); });
            else dev::read_live_v2_weights(loaded, model, requested);
        }
        torch::serialize::OutputArchive v2_archive; dev::write_live_v2_weights(v2_archive, model, dev::FinancialFeatures::SignedLogOrdersV2);
        std::stringstream v2_stream; v2_archive.save_to(v2_stream);
        torch::serialize::InputArchive v2_loaded; v2_loaded.load_from(v2_stream, device);
        rejected([&] { dev::read_live_v2_weights(v2_loaded, model, mode); });
        std::cout << "{\"status\":\"passed\",\"device\":\"" << device
            << "\",\"v3_public_context\":true,\"occupied_slots_rejected\":true,\"v2_v3_inputs_and_archives_distinct\":true}" << std::endl;
        std::filesystem::remove_all(root);
    } catch (const std::exception &error) { std::cerr << error.what() << '\n'; return 1; }
}
