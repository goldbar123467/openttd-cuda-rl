#include "v2_imitation.h"
#include "gradient_clip.h"
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <unistd.h>
#include <torch/cuda.h>

namespace dev = openttd_rl::development;
namespace v2 = openttd_rl::v2;
void check(bool condition, const char *message) { if (!condition) throw std::runtime_error(message); }

int main(int argc, char **argv)
{
    try {
        if (argc != 2 && argc != 4) throw std::invalid_argument("expected cpu|cuda:0 [native-observation.bin native-candidates.bin]");
        const torch::Device device(argv[1]);
        if (device.is_cuda() && !torch::cuda::is_available()) throw std::runtime_error("CUDA unavailable; no fallback");
        torch::set_num_threads(1);
        check(::setenv("CUBLAS_WORKSPACE_CONFIG", ":4096:8", 1) == 0, "cannot configure cuBLAS");
        at::globalContext().setDeterministicAlgorithms(true, false);
        if (argc == 4) {
            auto old = dev::read_live_v2_input(argv[2], argv[3], dev::FinancialFeatures::SignedLogV1);
            auto input = dev::read_live_v2_input(argv[2], argv[3], dev::FinancialFeatures::SignedLogLoanV1);
            std::vector<int64_t> loans;
            for (int64_t row = 0; row < v2::kCandidateCapacity; ++row)
                if (old.candidate_mask[0][row].item<bool>() && old.candidate_family[0][row].item<int64_t>() == 11) loans.push_back(row);
            check(loans.size() == 2, "native audit needs both legal borrow and repay candidates");
            check(torch::equal(old.candidate_features[0][loans[0]], old.candidate_features[0][loans[1]]), "native legacy loan vectors differ");
            check(!torch::equal(input.candidate_features[0][loans[0]], input.candidate_features[0][loans[1]]), "native corrected loan vectors still identical");
            check(torch::equal(old.candidate_features.slice(2, 0, 30), input.candidate_features.slice(2, 0, 30)), "native unrelated features changed");
            std::cout << "{\"status\":\"passed\",\"fixture\":\"recorded-native-public-loan-pair\",\"legacy_equal\":true,\"corrected_distinct\":true,\"rows\":["
                << loans[0] << ',' << loans[1] << "]}" << std::endl;
            return 0;
        }
        const auto root = std::filesystem::temp_directory_path() / ("rl-loan-features-" + std::to_string(::getpid()));
        check(std::filesystem::create_directory(root), "test requires a fresh artifact directory");
        auto write = [](const std::filesystem::path &path, const std::vector<uint8_t> &bytes) {
            std::ofstream stream(path, std::ios::binary);
            stream.write(reinterpret_cast<const char *>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
            check(static_cast<bool>(stream), "fixture write failed");
        };
        write(root / "observation.bin", std::vector<uint8_t>(2182927));
        std::vector<uint8_t> candidates(790528);
        auto word = [&](size_t offset, auto value) { std::memcpy(candidates.data() + offset, &value, sizeof(value)); };
        for (size_t row = 3; row <= 4; ++row) {
            word(row * 128 + 11 * 4, 1.0F); word(row * 128 + 12 * 4, 1.0F);
            word(4096 * 128 + row * 64, uint32_t{11});
            word(4096 * 128 + row * 64 + 4, static_cast<uint32_t>(row - 2));
            word(4096 * 128 + row * 64 + 8, uint32_t{10000});
            candidates[790528 - 4096 + row] = 1;
        }
        write(root / "candidates.bin", candidates);
        auto raw = dev::read_live_v2_input(root / "observation.bin", root / "candidates.bin");
        auto old = dev::read_live_v2_input(root / "observation.bin", root / "candidates.bin", dev::FinancialFeatures::SignedLogV1);
        auto input = dev::read_live_v2_input(root / "observation.bin", root / "candidates.bin", dev::FinancialFeatures::SignedLogLoanV1);
        check(torch::equal(raw.candidate_features, old.candidate_features), "old financial mode unexpectedly changed fixture features");
        check(torch::equal(old.candidate_features[0][3], old.candidate_features[0][4]), "fixture must reproduce indistinguishable legacy borrow/repay");
        check(torch::equal(input.candidate_features.slice(2, 0, 30), old.candidate_features.slice(2, 0, 30)), "loan mode changed unrelated candidate features");
        check(input.candidate_features[0][3][30].item<float>() == 1 && input.candidate_features[0][3][31].item<float>() == 0 &&
              input.candidate_features[0][4][30].item<float>() == 0 && input.candidate_features[0][4][31].item<float>() == 1,
              "new mode did not preserve exact opposite loan meanings");
        check(torch::equal(input.candidate_mask, old.candidate_mask), "preprocessing changed the native legal mask");
        word(4096 * 128 + 3 * 64 + 8, uint32_t{20000});
        write(root / "invalid.bin", candidates);
        bool refused = false;
        try { (void)dev::read_live_v2_input(root / "observation.bin", root / "invalid.bin", dev::FinancialFeatures::SignedLogLoanV1); }
        catch (const std::invalid_argument &) { refused = true; }
        check(refused, "unsupported loan amount was accepted");
        // Two artificial public contexts with opposite decisions. These are
        // numerical regression fixtures, never human training examples.
        auto first = dev::live_v2_to(input, device), second = dev::live_v2_to(input, device);
        // .to(cpu) can alias, so clone this intentionally different context.
        first.structured = first.structured.clone(); second.structured = second.structured.clone();
        first.structured[0][0] = -1; second.structured[0][0] = 1;
        first.recurrent_reset.fill_(true); second.recurrent_reset.fill_(true);
        v2::ScalablePolicy model(20261002);
        model->to(device);
        torch::optim::Adam optimizer(model->parameters(), torch::optim::AdamOptions(0.003).eps(1e-5));
        for (int iteration = 0; iteration < 96; ++iteration) {
            optimizer.zero_grad();
            auto loss = (dev::imitation_loss(model->forward(first), first, 3) + dev::imitation_loss(model->forward(second), second, 4)) / 2;
            loss.backward();
            (void)dev::clip_grad_norm_fp64_(model->parameters(), 0.5);
            optimizer.step();
            v2::require_finite_policy(model, "opposite loan fixture training");
        }
        torch::NoGradGuard guard;
        const auto borrow = dev::live_v2_distribution(model->forward(first), first).probabilities[0][3].item<double>();
        const auto repay = dev::live_v2_distribution(model->forward(second), second).probabilities[0][4].item<double>();
        check(borrow > 0.8 && repay > 0.8, "existing policy could not learn both opposite loan decisions");
        std::stringstream bytes;
        torch::serialize::OutputArchive saved;
        dev::write_live_v2_weights(saved, model, dev::FinancialFeatures::SignedLogLoanV1);
        saved.save_to(bytes);
        torch::serialize::InputArchive loaded;
        loaded.load_from(bytes, device);
        v2::ScalablePolicy wrong(0);
        refused = false;
        try { dev::read_live_v2_weights(loaded, wrong, dev::FinancialFeatures::SignedLogV1); }
        catch (const std::invalid_argument &) { refused = true; }
        check(refused, "loan checkpoint accepted the old indistinguishable preprocessing");
        std::cout << "{\"status\":\"passed\",\"fixture\":\"synthetic-opposite-loans\",\"device\":\"" << device
            << "\",\"borrow_probability\":" << borrow << ",\"repay_probability\":" << repay
            << ",\"legacy_unchanged\":true,\"wrong_amount_rejected\":true,\"wrong_preprocessing_rejected\":true}" << std::endl;
        std::filesystem::remove_all(root);
        return 0;
    } catch (const std::exception &error) { std::cerr << error.what() << '\n'; return 1; }
}
