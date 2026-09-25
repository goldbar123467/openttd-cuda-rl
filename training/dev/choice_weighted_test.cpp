// Independent scalar oracle for the optional reduction in the existing PPO.
#include "openttd_rl/training/ppo.h"
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <torch/cuda.h>

namespace t = openttd_rl::training;
void check(bool ok, const char *why) { if (!ok) throw std::runtime_error(why); }
void near(double a, double b, double tol = 1e-12) { check(std::abs(a - b) <= tol, "scalar oracle mismatch"); }
template<class F> void rejects(F function) { bool failed = false; try { function(); } catch (const std::exception &) { failed = true; } check(failed, "accepted invalid weights"); }

void losses(torch::Device device)
{
    auto options = torch::TensorOptions().dtype(torch::kFloat64).device(device);
    const auto old = torch::tensor({-.7, -.4, -.8, -.9}, options);
    const auto delta = torch::tensor({.3, -.4, .05, -.1}, options);
    const auto logs = (old + delta).detach().set_requires_grad(true);
    const auto advantage = torch::tensor({2., -3., 4., -1.}, options);
    const auto values = torch::tensor({1., 2., -1., 3.}, options).set_requires_grad(true);
    const auto returns = torch::tensor({2., 1., 3., -1.}, options);
    const auto entropy = torch::tensor({.5, .6, .7, .8}, options).set_requires_grad(true);
    t::PpoConfig config;
    auto call = [&](const torch::Tensor &weights) { return t::ppo_loss(logs, old, advantage, values, returns, entropy, config, weights); };
    const auto all = torch::ones({4}, options);
    const auto historical = call({});
    const auto weighted = call(all);
    for (const auto &pair : {std::make_pair(historical.total, weighted.total), {historical.policy, weighted.policy},
            {historical.value, weighted.value}, {historical.entropy, weighted.entropy},
            {historical.approximate_kl, weighted.approximate_kl}, {historical.clip_fraction, weighted.clip_fraction}})
        near(pair.first.item<double>(), pair.second.item<double>());
    // Recompute every component in scalar double arithmetic, independent of
    // tensor reductions. Include 0, 1, 2 and 4 choices and clipped signs.
    for (const auto &weights : {torch::zeros({4}, options), torch::tensor({1., 0., 0., 0.}, options),
            torch::tensor({1., 0., 0., 1.}, options), all}) {
        auto result = call(weights);
        double policy = 0, ent = 0, kl = 0, clip = 0, value = 0, count = 0;
        for (int64_t i = 0; i < 4; ++i) {
            const double ratio = std::exp(delta[i].item<double>()), adv = advantage[i].item<double>();
            const double w = weights[i].item<double>();
            policy -= w * std::min(ratio * adv, std::clamp(ratio, .8, 1.2) * adv);
            ent += w * entropy[i].item<double>();
            kl += w * ((ratio - 1) - delta[i].item<double>());
            clip += w * (std::abs(ratio - 1) > .2 ? 1 : 0);
            value += std::pow(values[i].item<double>() - returns[i].item<double>(), 2) / 4;
            count += w;
        }
        const double n = std::max(count, 1.);
        near(result.policy.item<double>(), policy / n);
        near(result.entropy.item<double>(), ent / n);
        near(result.approximate_kl.item<double>(), kl / n);
        near(result.clip_fraction.item<double>(), clip / n);
        near(result.value.item<double>(), value);
        near(result.total.item<double>(), policy / n + .5 * value - .01 * ent / n);
    }
    auto zero = call(torch::zeros({4}, options));
    zero.total.backward();
    check(logs.grad().abs().max().item<double>() == 0, "zero-choice actor gradient");
    check(entropy.grad().abs().max().item<double>() == 0, "zero-choice entropy gradient");
    check(values.grad().abs().max().item<double>() > 0, "zero-choice lost value gradient");
    for (const double bad : {-.1, .5, 2., std::numeric_limits<double>::infinity(), std::numeric_limits<double>::quiet_NaN()})
        rejects([&] { (void)call(torch::tensor({1., bad, 0., 0.}, options)); });
    rejects([&] { (void)call(torch::ones({1}, options)); });
    rejects([&] { (void)call(all.clone().set_requires_grad(true)); });
    if (device.is_cuda()) rejects([&] { (void)call(all.cpu()); });
}

void normalization()
{
    auto adv = torch::tensor({2., 4., 100., -100.}, torch::kFloat64);
    auto both = t::normalize_choice_advantages(adv, torch::tensor({1., 1., 0., 0.}));
    near(both[0].item<double>(), -1 / std::sqrt(1. + 1e-8));
    near(both[1].item<double>(), 1 / std::sqrt(1. + 1e-8));
    check(torch::equal(both.slice(0, 2), adv.slice(0, 2)), "forced advantage changed");
    check(torch::equal(t::normalize_choice_advantages(adv, torch::zeros({4})), adv), "zero choices erased advantages");
    check(torch::equal(t::normalize_choice_advantages(adv, torch::tensor({1., 0., 0., 0.})), adv), "lone choice erased");
    check(torch::equal(t::normalize_choice_advantages(adv, torch::ones({4})), t::normalize_advantages(adv)), "all-choice normalization differs");
    check(t::normalize_choice_advantages(torch::ones({4}), torch::ones({4})).abs().sum().item<double>() == 0, "constant choices nonzero");
    rejects([&] { (void)t::normalize_choice_advantages(adv, torch::tensor({1., .5, 0., 0.})); });
}

void optimizer_semantics(torch::Device device)
{
    // Real Adam, with a shared trunk and independent actor/value heads. Warm
    // momentum first, then take a value-only step with defined zero actor grads.
    auto opts = torch::TensorOptions().dtype(torch::kFloat64).device(device);
    auto trunk = torch::tensor({.4}, opts).set_requires_grad(true);
    auto actor = torch::tensor({.7}, opts).set_requires_grad(true);
    auto critic = torch::tensor({.9}, opts).set_requires_grad(true);
    torch::optim::Adam optimizer({trunk, actor, critic}, torch::optim::AdamOptions(.001));
    (trunk * actor + torch::square(trunk * critic - 1)).sum().backward(); optimizer.step(); optimizer.zero_grad();
    const auto before_actor = actor.detach().clone(), before_trunk = trunk.detach().clone();
    const auto before_logit = (trunk * actor).detach().clone();
    auto loss = t::ppo_loss(trunk * actor, torch::zeros({1}, opts), torch::ones({1}, opts),
        trunk * critic, torch::ones({1}, opts), trunk * actor * 0, t::PpoConfig{}, torch::zeros({1}, opts));
    loss.total.backward();
    check(actor.grad().abs().item<double>() == 0, "actor receives nonzero gradient");
    optimizer.step();
    const double head_drift = (actor - before_actor).abs().item<double>();
    const double trunk_drift = (trunk - before_trunk).abs().item<double>();
    const double policy_drift = (trunk * actor - before_logit).abs().item<double>();
    check(head_drift > 0 && trunk_drift > 0 && policy_drift > 0, "Adam/shared trunk drift unexpectedly eliminated");
    std::cout << "zero_choice_adam_head_drift=" << head_drift << " shared_trunk_drift=" << trunk_drift
        << " policy_logit_drift=" << policy_drift << '\n';
}

int main(int argc, char **argv)
{
    try {
        check(argc == 2, "expected cpu or cuda:0");
        torch::Device device(argv[1]);
        if (device.is_cuda()) check(torch::cuda::is_available(), "CUDA unavailable; no fallback");
        torch::set_num_threads(1);
        normalization(); losses(device); optimizer_semantics(device);
        std::cout << "CHOICE_WEIGHTED=PASS device=" << device << " float64_tolerance=1e-12\n";
        return 0;
    } catch (const std::exception &error) { std::cerr << error.what() << '\n'; return 1; }
}
