#!/usr/bin/env python3
"""Write a portable human-readable report from a completed verified comparison."""
import argparse
import json
from pathlib import Path

MODELS = ("one-game-1000", "one-game-256", "four-game-256", "seven-game-256")


def score(metric):
    exact = metric.get("unique_exact_rows", metric.get("exact"))
    total = metric.get("examples", metric.get("total"))
    return f"{exact}/{total} ({100 * exact / total:.1f}%)"


def render(data):
    training = data["training"]
    newest = data["offline"]["seven-game-256"]
    prior = data["offline"]["four-game-256"]
    original = data["offline"]["one-game-1000"]
    def test_without_repayments(values):
        exact = total = 0
        for name in ("test-nine", "test-ten"):
            corpus = values["corpora"][name]
            repayment = corpus["by_operation"]["manage-loan:CmdDecreaseLoan"]
            exact += corpus["overall"]["unique_exact_rows"] - repayment["unique_exact_rows"]
            total += corpus["overall"]["examples"] - repayment["examples"]
        return f"{exact}/{total}"
    live = data["gameplay"]["seven-game-256"]["all"]
    baseline = data["gameplay"]["scripted-one-bus-repay"]["all"]
    profit_difference = data["scripted_comparisons"]["seven-game-256:all"]["operating_profit"]["paired_mean_difference"]
    lines = ["# Ten human games: training and saved gameplay comparison", "",
             "All ten recordings are preserved and verified by native OpenTTD replay. "
             "Games 1–7 supply 186 training choices, game 8 supplies 34 development choices, "
             "and games 9–10 supply 64 test choices. The ten games contain 284 supported choices in total.", "",
             f"The new policy matches **{score(newest['combined_test'])} held-out test choices**, compared with "
             f"{score(prior['combined_test'])} for the four-game policy and {score(original['combined_test'])} for the original 1,000-update policy. "
             "The largest improvement is loan repayment. Station insertion and copying remain weak. "
             f"Excluding repayments, the new policy matches {test_without_repayments(newest)} test choices versus {test_without_repayments(prior)} for the four-game policy. "
             "The gameplay results below measure whether decision matching translates into service and finances.", "",
             f"In gameplay, the new policy delivers passengers in {live['any_delivery']}/50 attempts, versus {baseline['any_delivery']}/50 for the script. "
             f"Its mean operating profit is {live['mean_operating_profit']:.1f}, versus {baseline['mean_operating_profit']:.1f} for the script; "
             f"the mean paired difference at matching time horizons is {profit_difference:.1f}. "
             f"It achieves sustained profitable service in {live['sustained_service']}/50 attempts. "
             f"Across all actors, {data['verification']['interface_terminations']} attempts end at interface limits. "
             "All failed attempts remain in the reported denominators.", "",
             "## Training and offline comparison", "",
             f"The unchanged C++/LibTorch imitation trainer ran 256 CUDA updates in {training['elapsed_seconds'] / 60:.1f} minutes. "
             "Learning rate was 0.0003 and seed was 20261002. The original and equal-update controls retain their original archives. "
             "Games 8–10 never entered the optimizer, and no weights were selected or tuned using these evaluation scores. "
             "No PPO updates were performed.", "",
             "| Policy | Training choices / updates | Original recording (12 choices) | Games 1–7 (186 choices) | Development game 8 | Test games 9–10 |",
             "| --- | --- | --- | --- | --- | --- |"]
    examples = (12, 12, 79, 186)
    updates = (1000, 256, 256, 256)
    for model, count, steps in zip(MODELS, examples, updates):
        values = data["offline"][model]
        metrics = [values["corpora"][key]["overall"] for key in ("original", "seven-games", "development")]
        lines.append(f"| {model} | {count} / {steps} | " + " | ".join(score(metric) for metric in (*metrics, values["combined_test"])) + " |")
    lines += ["", "Scores on games 1–7 mix fit and transfer for older models: one-game controls trained on the separate October 2 recording; "
              "the four-game policy trained on games 1–4; the new policy trained on all seven. "
              "The original recording is a regression/transfer check for the multi-game policies. "
              "The test score represents two recordings, not 64 independent games.", "",
              "![Exact human decision matching](human-decision-comparison.png)", "",
              "### What the new policy learned", "",
              "| Operation | Training games 1–7 | Development game 8 | Test games 9–10 |",
              "| --- | --- | --- | --- |"]
    corpora = data["offline"]["seven-game-256"]["corpora"]
    operations = sorted({key for value in corpora.values() for key in value["by_operation"]})
    for operation in operations:
        metrics = []
        for names in (("seven-games",), ("development",), ("test-nine", "test-ten")):
            exact = total = 0
            for name in names:
                value = corpora[name]["by_operation"].get(operation)
                if value:
                    exact += value["unique_exact_rows"]
                    total += value["examples"]
            metrics.append(f"{exact}/{total}" if total else "—")
        lines.append(f"| {operation} | " + " | ".join(metrics) + " |")
    lines += ["", "The new model matches every recorded repayment in training, development and test. "
              "It matches only 6/43 training station insertions, 0/7 copies and 0/5 deletions; "
              "test insertions and copies remain 0/10 and 0/4. This is a useful financing improvement, "
              "with unresolved route setup and editing.", "",
              f"Training negative log likelihood fell from {training['initial']['loss']:.6f} to {training['final']['loss']:.6f}. "
              "The final training choices have zero input aliases and target ties. Gradients are finite and masks exact. "
              f"Checkpoint reload error is {training['checkpoint_reload_max_error']:.3g}; maximum CPU/CUDA probability difference is "
              f"{training['cpu_device_probability_max_error']:.3g}. "
              "Every offline choice was repeated after reversing legal candidate rows; the comparison rejects errors above 1e-6. "
              "Full scores, operation breakdowns, original probabilities and permutation evidence remain in the raw reports.", "",
              "### Insertion diagnostics", ""]
    if "diagnostics" in data:
        diagnostics = data["diagnostics"]
        structure = diagnostics["insertion_structure_summary"]
        lines += ["All 43 training insertion targets pass independent native input, mask, parameter and row-alignment checks. "
                  f"Aliased targets: {structure['aliased_targets']}; changed choices after row permutation: {structure['permutation_changed_choices']}. "
                  "Errors split into 11 wrong stations with the right bus/position, 12 wrong target buses, and 14 wrong action/order primitives. "
                  "Six insertions are exact; there are no position-only errors when the correct bus and station are selected.", "",
                  "In all 11 wrong-station cases the candidate vectors differ only in slot 28, the encoded station ID. "
                  "They are distinct (differences 0.052–0.198), but there is no candidate-specific station geometry or demand in that vector. "
                  "The policy pools station and vehicle context once for all candidates. This suggests weak entity binding as a possible cause; "
                  "it does not prove the model cannot represent the targets.", "",
                  "| Training operation | Actual exact choices | Uniform over complete legal mask | Uniform given family/order primitive | Candidate count with primitive hint (mean / range) |",
                  "| --- | --- | --- | --- | --- |"]
        for value in diagnostics["choice_summary"]:
            if value["model"] == "seven-game-256" and value["corpus"] == "seven-games":
                lines.append(f"| {value['operation']} | {value['unique_exact']}/{value['examples']} | "
                             f"{100 * value['random_all_legal_accuracy']:.3f}% | {100 * value['random_given_primitive_accuracy']:.1f}% | "
                             f"{value['mean_same_primitive_candidates']:.1f} / {value['min_same_primitive_candidates']}–{value['max_same_primitive_candidates']} |")
        lines += ["", "The conditional baseline receives an oracle hint identifying the action family or order primitive; it is not an unrestricted random policy. "
                  "Repayment still competes with borrowing (two choices). Expected accuracy averages 1/candidate-count per state, not 1/mean-count. "
                  "The unrestricted model receives no primitive hint.", "",
                  "![Exact fit and conditional random guessing by action type](action-type-diagnostics.png)", "",
                  "| Isolated insertion training | Exact fit | Loss | Row-permuted exact fit |",
                  "| --- | --- | --- | --- |"]
        for trial in diagnostics["insertion_trials"]:
            lines.append(f"| {trial['epochs']} CUDA updates; fresh fixed-seed policy | {trial['unique_exact']}/43 | "
                         f"{trial['final_loss']:.6f} | {trial['permuted_unique_exact']}/43 |")
        lines += ["", "These isolated models use only the existing 43 training insertions, unchanged C++ optimization, learning rate 0.0003, "
                  "complete legal masks and seed 20261002. They receive no test labels and never replace a benchmark actor. "
                  "The 1,000-update trial follows the imperfect 256-update training fit. A finite-budget failure to memorize is evidence of remaining "
                  "underfitting, not proof of an absolute information ceiling.", "",
                  "See [candidate diagnostics](choice-diagnostics.json), [every insertion audit](insertion-structure.json) "
                  "and the [256-update diagnostic](insertions-only-256.json) / [1,000-update diagnostic](insertions-only-1000.json).", ""]
    lines += [
              "## Saved 50-game benchmark", "",
              "Each of four neural policies and the one-bus script attempted 50 native episodes: **250 total**. "
              "Each actor used the same 25 saved starting worlds, once greedily and once with seeded sampling. "
              "The script is deterministic and is repeated in both mode groups for pairing. "
              "Each episode receives 512 decisions × 128 simulation ticks (65,536 ticks, about 2.4 game years), "
              "Bankruptcy ends an episode early. The frozen protocol originally allowed no other early termination; "
              "unsupported native order states are preserved as explicit interface failures, with shorter budgets and saved states. "
              "No masks, features or benchmark weights were changed to bypass those failures. No actor learning or guidance runs during evaluation. "
              "Recurrent state resets per decision, matching the imitation training samples.", "",
              "The map sizes are 64×64, 128×128, 64×128 and one 128×64 case. There are **eight distinct map seeds**, "
              "reused across dimensions; these are 50 episodes, not 50 independent maps. "
              "They come from the frozen development seed ledger. Roads, two bus stops and one depot are supplied; "
              "no buses are supplied. This tests bus control with existing infrastructure and does not establish learned construction. "
              "Setup worlds 1–17 use 128-tick construction steps; later successful setups use 1-tick construction steps. "
              "The resulting saved starting states are identical for every actor within a case.", "",
              "| Actor / mode | Full budget / interface failures | Delivered passengers in any amount | Positive operating profit | Sustained profitable service | Mean passengers | Mean operating profit | Operating-profit difference from script at matched horizon | Mean cash after capital, excluding financing | Mean buses |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for actor, modes in data["gameplay"].items():
        for mode in ("greedy", "sampled"):
            value = modes[mode]
            baseline_difference = (data["scripted_comparisons"][actor + ":" + mode]["operating_profit"]["paired_mean_difference"]
                                   if actor in MODELS else 0)
            lines.append(f"| {actor} / {mode} | {value['completed_full_budget']}/25; {value['interface_terminations']} failures | "
                         f"{value['any_delivery']}/25 | {value['positive_operating_profit']}/25 | "
                         f"{value['sustained_service']}/25 | {value['mean_passengers']:.1f} | {value['mean_operating_profit']:.1f} | "
                         f"{baseline_difference:.1f} | "
                         f"{value['mean_cash_result_excluding_financing']:.1f} | {value['mean_buses']:.1f} |")
    lines += ["", "Sustained service requires positive passenger delivery and operating profit in each of the final three "
              "128-decision windows. Native operating profit sums transport income minus running, property and loan-interest expenses "
              "over the retained quarter history; it excludes bus capital purchases and loan principal. Loan principal is financing. "
              "Cash after capital, excluding financing = balance change − loan change. "
              "Cash before capital additionally adds net capital spend. Remaining cash flows are retained separately "
              "alongside the native operating-profit metric in the episode CSV. "
              "Monetary values use native game units rather than a converted display currency. "
              "Raw balance drops from repayments are not counted as operating losses.", "",
              "All planned cases remain in the denominators. Raw mean totals include the actual shorter histories of interface failures; "
              "the script-relative profit column and paired differences use the minimum common decision horizon in each pair. "
              "An early interface failure is not a profitable-service success.", "",
              "![Live gameplay and financial comparison](live-game-comparison.png)", "",
              "### Paired uncertainty", "",
              "Each difference below is the new policy minus the comparison actor on identical cases, at the minimum common simulated horizon. "
              "Intervals use 5,000 bootstrap resamples of the eight map-seed clusters, retaining dimensions and modes within a seed. "
              "They describe this narrow benchmark and cannot establish broad OpenTTD playing strength.", "",
              "| Comparison (all 50 paired episodes) | Mean passenger difference [95% cluster interval] | Mean operating-profit difference [95% cluster interval] |",
              "| --- | --- | --- |"]
    for comparison in (*MODELS[:-1], "scripted-one-bus-repay"):
        values = data["paired"][comparison + ":all"]
        cells = []
        for metric in ("passengers", "operating_profit"):
            value = values[metric]
            low, high = value["cluster_bootstrap_95_percent_interval"]
            cells.append(f"{value['paired_mean_difference']:.1f} [{low:.1f}, {high:.1f}]")
        lines.append(f"| {comparison} | " + " | ".join(cells) + " |")
    checks = data["verification"]
    lines += ["", "## Evidence and verification", "",
              f"The independent summary verified {checks['episodes']} episodes, {checks['decisions']:,} decisions and "
              f"{checks['simulation_ticks']:,} simulation ticks. {checks['full_budget_episodes']} attempts reached the full budget; "
              f"{checks['interface_terminations']} ended at unsupported order states. It recomputed every financial summary from the native transition chain, "
              "checked paired initial states, exact budgets, executed candidate identities, final states and save hashes. "
              "The first greedy and sampled save for every actor also passed a fresh native load/state roundtrip. "
              "CHECKPOINT qualification checks reject a pending action and verify that saving changes neither ticks nor native state. "
              "Engine, model, training report and frozen protocol hashes are rechecked after evaluation.", "",
              "- [Verified summary and raw evidence references](results.json)",
              "- [Offline scores](offline.csv) and [operation scores](offline-operations.csv)",
              "- [All 250 episode outcomes and final-save hashes](gameplay.csv)",
              "- [Paired episode differences](paired-differences.csv)",
              "- [Each model compared with the script at matching horizons](scripted-paired-differences.csv)",
              "- [Reproduced interface-failure prefixes](interface-prefix-verification.json) and [repository checks](verification-checks.json)",
              "- [Native checkpoint qualification](native-checkpoint-qualification.json)",
              "- [Human-decision figure PDF](human-decision-comparison.pdf) and [gameplay figure PDF](live-game-comparison.pdf)",
              "", "Each native episode retains its intermediate and final .sav files, decision journal, transition ledger, "
              "initial/final public state, exact input tensors and tensor metadata. Neural tensors are stored as losslessly verified gzip archives. "
              "The Windows evidence package also contains all 250 final saves, the selected model and training protocols. "
              "Raw native traces and model-comparison outputs remain in the WSL runtime under "
              "`/home/imsa/.local/share/openttd-rl/runs/human-ten-game-training-20261005-01/`.", "",
              "Failed setup attempts, the original inference-schema failure and episodes interrupted for parallel resumption are preserved. "
              "Prior full-budget episodes were reused only with matching save, model, engine, protocol and reader provenance. "
              "Explicit interface captures also retain their shorter budget and failure classification; they are not completed games. "
              "Older per-episode records use enclosing batch reader provenance. One qualified failure's reader checksum is recorded in a later supplement, "
              "and its original 395 native transitions and choices match exactly. The other two captures also match all 329 and 239 original transitions, "
              "choices, masks and input hashes. That checksum timing limitation is preserved in the raw record.", "",
              "## Practical conclusion", "",
              "More human data improved matching on unseen recordings, especially repayment choices. "
              "The fixed-budget model still needs better station targeting, copying, deletion and sustained fleet control. "
              "These recordings contain no explicit WAIT supervision: human pauses and reasoning are annotations rather than executable labels. "
              "Do not interpret the stronger test score as proof of profitable autonomous play or start a long PPO run from that score alone. "
              "The next model work should test candidate-specific station/order context and optimization using training/development data, "
              "because isolated insertion training still underfits. Data/tooling work should capture intentional waiting and decisions to preserve an already working route, "
              "then measure service, financing and imitation retention together.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.results.read_text())
    if data["status"] != "completed":
        raise ValueError("Report requires complete verified evidence")
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(render(data))
