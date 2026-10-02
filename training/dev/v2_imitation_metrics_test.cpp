#include "v2_imitation.h"
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <torch/cuda.h>

namespace dev = openttd_rl::development;
namespace v2 = openttd_rl::v2;

void check(bool condition, const char *message) { if (!condition) throw std::runtime_error(message); }

int main(int argc, char **argv)
{
    try {
        if (argc != 2) throw std::invalid_argument("expected cpu|cuda:0");
        const torch::Device device(argv[1]);
        if (device.is_cuda() && !torch::cuda::is_available()) throw std::runtime_error("CUDA unavailable; no fallback");
        torch::set_num_threads(1);
        v2::ScalablePolicyInput input;
        input.candidate_features = torch::zeros({1, 6, v2::kCandidateFeatures});
        input.candidate_family = torch::tensor({{3, 3, 4, 3, 7, 7}}, torch::kInt64);
        input.candidate_mask = torch::tensor({{true, true, true, false, true, true}}, torch::kBool);
        input.candidate_features[0][4][0] = 1.0F;
        input.candidate_features[0][5][0] = 1.0F;
        input.candidate_features[0][1][1] = -0.0F;
        auto aliases = dev::audit_imitation_inputs(input, 0);
        check(aliases.group_count == 2 && aliases.candidate_count == 4, "legal same-family alias inventory differs");
        check(aliases.target_rows == std::vector<int64_t>{1}, "alias audit included other family or illegal row");

        auto probabilities = torch::tensor({{0.4, 0.4, 0.1, 0.0, 0.05, 0.05}}, torch::kFloat64).to(device);
        auto prediction = dev::measure_imitation_prediction(input, probabilities, 0, aliases);
        check(prediction.row_correct && prediction.target_tied && !prediction.unique_exact,
            "first-row argmax tie was counted as unique imitation");
        check(prediction.target_probability_margin == 0.0, "exact tie margin differs");
        auto second_aliases = dev::audit_imitation_inputs(input, 1);
        prediction = dev::measure_imitation_prediction(input, probabilities, 1, second_aliases);
        check(!prediction.row_correct && prediction.target_tied && !prediction.unique_exact,
            "tie behavior depends incorrectly on the target's row order");

        // A clear logit winner cannot repair an input alias. This deliberately
        // inconsistent probability fixture guards the stronger unique metric.
        probabilities = torch::tensor({{0.7, 0.1, 0.1, 0.0, 0.05, 0.05}}, torch::kFloat64).to(device);
        prediction = dev::measure_imitation_prediction(input, probabilities, 0, aliases);
        check(prediction.row_correct && !prediction.target_tied && !prediction.unique_exact,
            "target alias was ignored by unique accuracy");

        input.candidate_features[0][1][2] = 0.25F;
        aliases = dev::audit_imitation_inputs(input, 0);
        check(aliases.target_rows.empty() && aliases.group_count == 1, "distinct input was retained as an alias");
        prediction = dev::measure_imitation_prediction(input, probabilities, 0, aliases);
        check(prediction.row_correct && !prediction.target_tied && prediction.unique_exact,
            "distinct clear target winner was not counted as unique");
        check(std::abs(prediction.target_probability_margin - 0.6) < 1e-12, "best legal alternative margin differs");

        probabilities = torch::tensor({{0.4000002, 0.3999998, 0.1, 0.0, 0.05, 0.05}}, torch::kFloat64).to(device);
        prediction = dev::measure_imitation_prediction(input, probabilities, 0, aliases);
        check(prediction.row_correct && prediction.target_tied && !prediction.unique_exact,
            "roundoff-scale winner was counted as unique");
        probabilities = torch::tensor({{0.400001, 0.399999, 0.1, 0.0, 0.05, 0.05}}, torch::kFloat64).to(device);
        prediction = dev::measure_imitation_prediction(input, probabilities, 0, aliases);
        check(prediction.unique_exact && !prediction.target_tied, "meaningful probability margin was rejected");

        // A different-family legal alternative must still defeat the target.
        probabilities = torch::tensor({{0.2, 0.1, 0.6, 0.0, 0.05, 0.05}}, torch::kFloat64).to(device);
        prediction = dev::measure_imitation_prediction(input, probabilities, 0, aliases);
        check(prediction.predicted_row == 2 && !prediction.row_correct && !prediction.unique_exact &&
            !prediction.target_tied && prediction.target_probability_margin < -0.39,
            "global legal alternatives were omitted from unique accuracy");

        bool refused = false;
        probabilities[0][3] = 0.1;
        try { (void)dev::measure_imitation_prediction(input, probabilities, 0, aliases); }
        catch (const std::runtime_error &) { refused = true; }
        check(refused, "illegal prediction probability was accepted");
        refused = false;
        input.candidate_features[0][0][0] = std::numeric_limits<float>::quiet_NaN();
        try { (void)dev::audit_imitation_inputs(input, 0); }
        catch (const std::invalid_argument &) { refused = true; }
        check(refused, "nonfinite input alias audit was accepted");
        std::cout << "{\"status\":\"passed\",\"fixture\":\"synthetic-imitation-ties-and-input-aliases\",\"device\":\""
            << device << "\",\"legacy_argmax_tie_rejected\":true,\"legal_global_margin_checked\":true,"
            "\"encoded_target_alias_checked\":true}" << std::endl;
        return 0;
    } catch (const std::exception &error) { std::cerr << error.what() << '\n'; return 1; }
}
