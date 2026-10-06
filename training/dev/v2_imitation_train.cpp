// A separate supervised objective on the existing V2 policy. PPO remains in
// v2_live_train.cpp; demonstrations never enter its on-policy rollout buffer.
#include "v2_imitation.h"
#include "checkpoint_io.h"
#include "gradient_clip.h"
#include <algorithm>
#include <charconv>
#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <numeric>
#include <random>
#include <stdexcept>
#include <torch/cuda.h>
#include <torch/version.h>

namespace {
namespace dev = openttd_rl::development;
namespace v2 = openttd_rl::v2;
struct FamilyMetrics {
    size_t count{}, tied_target_count{}, input_alias_group_count{}, input_aliased_candidate_count{},
        target_input_alias_count{}, target_input_alias_alternative_count{};
    double loss{}, probability{}, accuracy{}, family_accuracy{}, unique_exact_accuracy{},
        minimum_target_probability_margin = std::numeric_limits<double>::infinity();
};
struct ExampleMetrics {
    std::string sample_id, game_id;
    int64_t target_row{}, family{};
    dev::ImitationInputAliases aliases;
    dev::ImitationPrediction prediction;
};
struct Metrics : FamilyMetrics {
    std::map<int64_t, FamilyMetrics> families;
    std::vector<ExampleMetrics> examples;
};

void accumulate(FamilyMetrics &metrics, const double loss, const bool family_correct,
    const dev::ImitationInputAliases &aliases, const dev::ImitationPrediction &prediction)
{
    ++metrics.count;
    metrics.loss += loss; metrics.probability += prediction.target_probability;
    metrics.accuracy += prediction.row_correct; metrics.family_accuracy += family_correct;
    metrics.unique_exact_accuracy += prediction.unique_exact;
    metrics.tied_target_count += prediction.target_tied;
    metrics.minimum_target_probability_margin = std::min(metrics.minimum_target_probability_margin, prediction.target_probability_margin);
    metrics.input_alias_group_count += aliases.group_count;
    metrics.input_aliased_candidate_count += aliases.candidate_count;
    metrics.target_input_alias_count += !aliases.target_rows.empty();
    metrics.target_input_alias_alternative_count += aliases.target_rows.size();
}

void normalize(FamilyMetrics &metrics)
{
    const auto count = static_cast<double>(metrics.count);
    metrics.loss /= count; metrics.probability /= count; metrics.accuracy /= count;
    metrics.family_accuracy /= count; metrics.unique_exact_accuracy /= count;
}

Metrics measure(v2::ScalablePolicy &model, const std::vector<dev::ImitationExample> &examples,
    const std::vector<dev::ImitationInputAliases> &aliases, const torch::Device &device)
{
    torch::NoGradGuard guard;
    model->eval();
    Metrics result;
    for (size_t index = 0; index < examples.size(); ++index) {
        const auto &example = examples[index];
        auto input = dev::live_v2_to(example.input, device);
        const auto output = model->forward(input);
        const auto policy = dev::live_v2_distribution(output, input);
        const auto loss = -policy.log_probabilities[0][example.action].item<double>();
        const auto prediction = dev::measure_imitation_prediction(example.input, policy.probabilities, example.action, aliases[index]);
        const auto family_correct = output.family_logits.argmax(1).item<int64_t>() == example.family;
        accumulate(result, loss, family_correct, aliases[index], prediction);
        accumulate(result.families[example.family], loss, family_correct, aliases[index], prediction);
        result.examples.push_back({example.sample_id, example.game_id, example.action, example.family, aliases[index], prediction});
    }
    normalize(result);
    for (auto &[id, family] : result.families) {
        (void)id;
        normalize(family);
    }
    if (!std::isfinite(result.loss)) throw std::runtime_error("nonfinite imitation evaluation loss");
    return result;
}

void check_gradients(v2::ScalablePolicy &model)
{
    for (const auto &parameter : model->named_parameters(true)) {
        // The supervised actor objective has no critic target; its head stays
        // untouched. Shared encoders still receive policy gradients.
        const auto gradient = parameter.value().grad();
        if (!gradient.defined() && parameter.key().starts_with("value_head.")) continue;
        if (!gradient.defined() || !torch::isfinite(gradient).all().item<bool>())
            throw std::runtime_error("missing/nonfinite imitation gradient: " + parameter.key());
    }
}

void print_string(const std::string &value)
{
    constexpr char hex[] = "0123456789abcdef";
    std::cout << '"';
    for (const char character : value) {
        const auto byte = static_cast<unsigned char>(character);
        if (byte == '"' || byte == '\\') std::cout << '\\' << static_cast<char>(byte);
        else if (byte < 0x20) std::cout << "\\u00" << hex[byte >> 4] << hex[byte & 15];
        else std::cout << static_cast<char>(byte);
    }
    std::cout << '"';
}

void print_fields(const FamilyMetrics &metrics)
{
    std::cout << "\"count\":" << metrics.count << ",\"loss\":" << metrics.loss
        << ",\"mean_target_probability\":" << metrics.probability
        << ",\"accuracy\":" << metrics.accuracy << ",\"family_head_accuracy\":" << metrics.family_accuracy
        << ",\"unique_exact_accuracy\":" << metrics.unique_exact_accuracy
        << ",\"tied_target_count\":" << metrics.tied_target_count
        << ",\"minimum_target_probability_margin\":" << metrics.minimum_target_probability_margin
        << ",\"input_alias_group_count\":" << metrics.input_alias_group_count
        << ",\"input_aliased_candidate_count\":" << metrics.input_aliased_candidate_count
        << ",\"target_input_alias_count\":" << metrics.target_input_alias_count
        << ",\"target_input_alias_alternative_count\":" << metrics.target_input_alias_alternative_count;
}

void print_metrics(const Metrics &metrics, bool include_examples = true)
{
    std::cout << '{'; print_fields(metrics);
    std::cout << ",\"unique_probability_margin_tolerance\":" << dev::kImitationProbabilityMargin
        << ",\"by_family\":{";
    bool first = true;
    for (const auto &[id, family] : metrics.families) {
        if (!first) std::cout << ',';
        first = false;
        std::cout << '"' << id << "\":{"; print_fields(family); std::cout << '}';
    }
    std::cout << '}';
    if (include_examples) {
        std::cout << ",\"examples\":[";
        first = true;
        for (const auto &example : metrics.examples) {
            if (!first) std::cout << ',';
            first = false;
            const auto &prediction = example.prediction;
            std::cout << "{\"sample_id\":"; print_string(example.sample_id);
            std::cout << ",\"game_id\":"; print_string(example.game_id);
            std::cout << ",\"family\":" << example.family << ",\"target_row\":" << example.target_row
                << ",\"predicted_row\":" << prediction.predicted_row
                << ",\"target_probability\":" << prediction.target_probability
                << ",\"best_alternative_probability\":" << prediction.best_alternative_probability
                << ",\"target_probability_margin\":" << prediction.target_probability_margin
                << ",\"row_correct\":" << (prediction.row_correct ? "true" : "false")
                << ",\"target_tied\":" << (prediction.target_tied ? "true" : "false")
                << ",\"unique_exact\":" << (prediction.unique_exact ? "true" : "false")
                << ",\"input_alias_group_count\":" << example.aliases.group_count
                << ",\"input_aliased_candidate_count\":" << example.aliases.candidate_count
                << ",\"target_input_alias_rows\":[";
            for (size_t index = 0; index < example.aliases.target_rows.size(); ++index) {
                if (index) std::cout << ',';
                std::cout << example.aliases.target_rows[index];
            }
            std::cout << "]}";
        }
        std::cout << ']';
    }
    std::cout << '}';
}

int64_t integer(const std::string &text, int64_t minimum, int64_t maximum)
{
    int64_t result = 0;
    const auto parsed = std::from_chars(text.data(), text.data() + text.size(), result);
    if (parsed.ec != std::errc{} || parsed.ptr != text.data() + text.size() || result < minimum || result > maximum)
        throw std::invalid_argument("imitation integer option outside bounds");
    return result;
}
} // namespace

int main(int argc, char **argv)
{
    try {
        if (argc != 15) throw std::invalid_argument("usage: --device cpu|cuda:0 --seed INTEGER --epochs INTEGER --learning-rate NUMBER --financial-features raw|signed-log-v1|signed-log-loan-v1|signed-log-actions-v1|signed-log-orders-v1|signed-log-orders-v2|signed-log-orders-v3 --manifest PATH --output PATH");
        std::map<std::string, std::string> args;
        for (int index = 1; index < argc; index += 2)
            if (!args.emplace(argv[index], argv[index + 1]).second) throw std::invalid_argument("duplicate imitation option");
        const auto device_name = args.at("--device");
        if (device_name != "cpu" && device_name != "cuda:0") throw std::invalid_argument("unsupported imitation device");
        torch::Device device(device_name);
        if (device.is_cuda() && !torch::cuda::is_available()) throw std::runtime_error("CUDA unavailable; no fallback");
        const auto seed = static_cast<uint64_t>(integer(args.at("--seed"), 0, 2147483647));
        const auto epochs = integer(args.at("--epochs"), 1, 1000);
        double learning_rate = 0;
        const auto &rate = args.at("--learning-rate");
        const auto parsed = std::from_chars(rate.data(), rate.data() + rate.size(), learning_rate);
        if (parsed.ec != std::errc{} || parsed.ptr != rate.data() + rate.size() || !std::isfinite(learning_rate) ||
            learning_rate <= 0 || learning_rate > 0.01) throw std::invalid_argument("invalid imitation learning rate");
        const auto features = dev::parse_financial_features(args.at("--financial-features"));
        const std::filesystem::path output_path(args.at("--output"));
        if (!output_path.is_absolute() || std::filesystem::exists(output_path) || !std::filesystem::is_directory(output_path.parent_path()))
            throw std::invalid_argument("imitation output requires a fresh absolute path");
        torch::set_num_threads(1);
        if (::setenv("CUBLAS_WORKSPACE_CONFIG", ":4096:8", 1) != 0) throw std::runtime_error("cuBLAS setup failed");
        at::globalContext().setDeterministicAlgorithms(true, false);
        at::globalContext().setDeterministicCuDNN(true);
        at::globalContext().setBenchmarkCuDNN(false);
        const auto examples = dev::read_imitation_examples(args.at("--manifest"), features);
        std::vector<dev::ImitationInputAliases> aliases;
        for (const auto &example : examples) aliases.push_back(dev::audit_imitation_inputs(example.input, example.action));
        size_t choices = 0;
        for (const auto &example : examples) choices += example.input.candidate_mask.sum().item<int64_t>() > 1 ? 1U : 0U;
        if (choices == 0) throw std::invalid_argument("imitation needs at least one genuine supported choice");
        v2::ScalablePolicy model(seed);
        model->to(device);
        torch::optim::Adam optimizer(model->parameters(), torch::optim::AdamOptions(learning_rate).eps(1e-5));
        std::mt19937_64 shuffle(seed);
        std::vector<size_t> indices(examples.size());
        std::iota(indices.begin(), indices.end(), 0U);
        const auto initial = measure(model, examples, aliases, device);
        std::cout << std::setprecision(17) << "{\"event\":\"initial\",\"examples\":" << examples.size()
            << ",\"choice_examples\":" << choices << ",\"metrics\":";
        print_metrics(initial); std::cout << "}" << std::endl;
        // New action-aware training must not try to fit an impossible exact
        // row label. Keep the initial audit and historical modes available for
        // reproducing and diagnosing earlier indistinguishable inputs.
        if (features == dev::FinancialFeatures::SignedLogActionsV1 || dev::uses_order_features(features)) {
            for (size_t index = 0; index < examples.size(); ++index) {
                if (aliases[index].target_rows.empty()) continue;
                throw std::invalid_argument("action-aware imitation target input alias: sample " + examples[index].sample_id +
                    " target row " + std::to_string(examples[index].action) + " aliases legal row " +
                    std::to_string(aliases[index].target_rows.front()));
            }
        }
        double max_gradient = 0;
        for (int64_t epoch = 0; epoch < epochs; ++epoch) {
            model->train();
            std::shuffle(indices.begin(), indices.end(), shuffle);
            // Accumulate one full-dataset mean, releasing each input graph
            // immediately. This keeps GPU memory bounded independently of N.
            optimizer.zero_grad();
            for (const auto index : indices) {
                const auto &example = examples[index];
                const auto input = dev::live_v2_to(example.input, device);
                auto loss = dev::imitation_loss(model->forward(input), input, example.action) / static_cast<double>(examples.size());
                loss.backward();
            }
            check_gradients(model);
            max_gradient = std::max(max_gradient, dev::clip_grad_norm_fp64_(model->parameters(), 0.5));
            optimizer.step();
            v2::require_finite_policy(model, "imitation update");
            const auto metrics = measure(model, examples, aliases, device);
            std::cout << "{\"event\":\"epoch\",\"epoch\":" << epoch + 1 << ",\"metrics\":";
            print_metrics(metrics, false); std::cout << "}" << std::endl;
        }
        const auto final = measure(model, examples, aliases, device);
        if (!(final.loss < initial.loss)) throw std::runtime_error("small imitation fit did not lower supervised loss");
        torch::serialize::OutputArchive saved;
        dev::write_live_v2_weights(saved, model, features);
        dev::publish_checkpoint(saved, output_path);
        v2::ScalablePolicy reloaded(0), reference(0);
        reloaded->to(device);
        torch::serialize::InputArchive archive, cpu_archive;
        archive.load_from(output_path.string(), device);
        cpu_archive.load_from(output_path.string(), torch::Device(torch::kCPU));
        dev::read_live_v2_weights(archive, reloaded, features);
        dev::read_live_v2_weights(cpu_archive, reference, features);
        v2::require_finite_policy(reloaded, "imitation checkpoint reload");
        model->eval(); reloaded->eval(); reference->eval();
        double reload_error = 0, probability_error = 0, value_error = 0;
        {
            torch::NoGradGuard guard;
            for (size_t index = 0; index < std::min<size_t>(8, examples.size()); ++index) {
                const auto input = dev::live_v2_to(examples[index].input, device);
                const auto expected = model->forward(input), actual = reloaded->forward(input);
                reload_error = std::max({reload_error, (expected.family_logits - actual.family_logits).abs().max().item<double>(),
                    (expected.candidate_logits - actual.candidate_logits).abs().max().item<double>(),
                    (expected.value - actual.value).abs().max().item<double>(),
                    (expected.next_hidden - actual.next_hidden).abs().max().item<double>()});
                const auto cpu = reference->forward(examples[index].input);
                probability_error = std::max(probability_error, (dev::live_v2_distribution(actual, input).probabilities.cpu() -
                    dev::live_v2_distribution(cpu, examples[index].input).probabilities).abs().max().item<double>());
                value_error = std::max(value_error, (actual.value.cpu() - cpu.value).abs().max().item<double>());
            }
        }
        model->zero_grad(); reference->zero_grad();
        const auto input = dev::live_v2_to(examples.front().input, device);
        const auto cuda_loss = dev::imitation_loss(model->forward(input), input, examples.front().action);
        const auto cpu_loss = dev::imitation_loss(reference->forward(examples.front().input), examples.front().input, examples.front().action);
        cuda_loss.backward(); cpu_loss.backward();
        check_gradients(model); check_gradients(reference);
        double gradient_error = 0;
        const auto parameters = model->parameters(), cpu_parameters = reference->parameters();
        for (size_t index = 0; index < parameters.size(); ++index) {
            if (!parameters[index].grad().defined()) continue;
            gradient_error = std::max(gradient_error, (parameters[index].grad().cpu() - cpu_parameters[index].grad()).abs().max().item<double>());
        }
        const auto loss_error = std::abs(cuda_loss.item<double>() - cpu_loss.item<double>());
        if (reload_error > 1e-6 || probability_error > 1e-5 || value_error > 1e-4 || loss_error > 1e-4 || gradient_error > 1e-4)
            throw std::runtime_error("imitation checkpoint/CPU-device agreement exceeded tolerance");
        std::cout << "{\"event\":\"completed\",\"device\":\"" << device_name << "\",\"torch\":\"" << TORCH_VERSION
            << "\",\"epochs\":" << epochs << ",\"examples\":" << examples.size() << ",\"initial\":";
        print_metrics(initial); std::cout << ",\"final\":"; print_metrics(final);
        std::cout << ",\"max_unclipped_gradient_norm\":" << max_gradient << ",\"checkpoint_reload_max_error\":" << reload_error
            << ",\"cpu_device_probability_max_error\":" << probability_error << ",\"cpu_device_value_max_error\":" << value_error
            << ",\"cpu_device_loss_error\":" << loss_error << ",\"cpu_device_gradient_max_error\":" << gradient_error
            << ",\"cpu_cuda_compared\":" << (device.is_cuda() ? "true" : "false")
            << ",\"finite_gradients\":true,\"exact_legal_masks\":true,\"context\":\"independent-reset\"}" << std::endl;
        return 0;
    } catch (const std::exception &error) { std::cerr << "V2 imitation failed: " << error.what() << '\n'; return 1; }
}
