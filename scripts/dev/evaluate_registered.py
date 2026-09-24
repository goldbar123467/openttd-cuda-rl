#!/usr/bin/env python3
"""Execute a frozen, explicit V1 held-out registration without training or tuning."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

import bridge_validation
from evaluate_live import episode, package_snapshot, validate_m06_reward_contract
from local import ROOT, capture_source, source_identity, write_json
from report_credit_experiment import interval
from report_learning import summarize


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_registration(registration):
    expected = {"action_horizon": 512, "ticks_per_action": 128, "starting_balance": 100000,
        "sampling_seeds": [20260923, 20260924, 20260925], "primary_mode": "sampled",
        "diagnostic_mode": "greedy", "template_ids": ["m02-template-07", "m02-template-08"],
        "baselines": ["wait", "random", "scripted", "one-bus"], "minimum_sustained_per_model": 5,
        "bankruptcies_allowed": 0, "invalid_actions_allowed": 0}
    if registration.get("format") != "openttd-rl-registered-holdout-1" or registration.get("protocol") != expected:
        raise ValueError("Registration differs from the supported frozen protocol")
    status = registration.get("status")
    if status not in ("registered-before-final-access", "amended-before-final-results") or registration.get("allow_tuning_from_results") is not False:
        raise ValueError("A preregistered no-tuning evaluation is required")
    if status == "amended-before-final-results" and not registration.get("parent_registration_sha256"):
        raise ValueError("A setup amendment must retain its original registration identity")
    models = registration["models"]
    if sorted(model["training_seed"] for model in models) != [20260923, 20260924, 20260925]:
        raise ValueError("The three registered independent training seeds are required")
    if len({model["package"] for model in models}) != 3:
        raise ValueError("Registered models must be distinct")


def summaries_and_criteria(rows, registration):
    settings = registration["protocol"]
    cases = [(None, policy) for policy in settings["baselines"]]
    cases += [(model["training_seed"], policy) for model in registration["models"] for policy in ("sampled", "greedy")]
    expected = {(training_seed, policy, template, seed) for training_seed, policy in cases
        for template in settings["template_ids"]
        for seed in (settings["sampling_seeds"] if policy in ("random", "sampled") else [20260923])}
    actual = [(row.get("training_seed"), row["policy"], row["template_id"], row["sampling_seed"]) for row in rows]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError("Held-out scenario/model/sampling matrix differs")
    summaries = {}
    for policy in ("wait", "random", "scripted", "one-bus", "greedy", "sampled"):
        selected = [row for row in rows if row["policy"] == policy]
        if len(selected) != {"wait": 2, "random": 6, "scripted": 2, "one-bus": 2, "greedy": 6, "sampled": 18}[policy]:
            raise ValueError("Held-out case matrix is incomplete")
        summaries[policy] = summarize(selected)
    sampled = summaries["sampled"]
    service = {model["training_seed"]: sum(row["service_in_all_final_three_windows"] for row in rows
        if row.get("training_seed") == model["training_seed"] and row["policy"] == "sampled")
        for model in registration["models"]}
    checks = {"at_least_five_of_six_sustained_per_model": all(value >= 5 for value in service.values()),
        "positive_mean_operating_profit": sampled["mean_operating_profit"] > 0,
        "mean_operating_profit_above_random": sampled["mean_operating_profit"] > summaries["random"]["mean_operating_profit"],
        "mean_cash_above_random": sampled["mean_balance_change"] > summaries["random"]["mean_balance_change"],
        "mean_cash_above_original_script": sampled["mean_balance_change"] > summaries["scripted"]["mean_balance_change"],
        "no_sampled_invalid_actions": sampled["invalid_actions"] == 0,
        "no_sampled_bankruptcies": sampled["bankruptcies"] == 0}
    seed_statistics = {}
    for metric in ("passengers", "operating_profit", "operating_profit_less_capital", "balance_change"):
        values = {model["training_seed"]: statistics.mean(row[metric] for row in rows
            if row.get("training_seed") == model["training_seed"] and row["policy"] == "sampled")
            for model in registration["models"]}
        seed_statistics[metric] = {"training_seed_means": values, **interval(list(values.values()))}
    return dict(summaries=summaries, sustained_by_training_seed=service, acceptance_checks=checks,
                acceptance_passed=all(checks.values()), sampled_training_seed_statistics=seed_statistics)


def run(args):
    path = args.registration.resolve()
    registration_hash = digest(path)
    if path.with_suffix(".sha256").read_text().strip() != registration_hash:
        raise ValueError("Registration digest changed")
    registration = json.loads(path.read_text())
    validate_registration(registration)
    for name, expected in registration["code_sha256"].items():
        if digest(ROOT / name) != expected:
            raise ValueError("Registered evaluation code changed: " + name)
    engine, evaluator = (Path(registration[name]["path"]) for name in ("engine", "evaluator"))
    for name, executable in (("engine", engine), ("evaluator", evaluator)):
        if digest(executable) != registration[name]["sha256"]:
            raise ValueError("Registered native executable changed: " + name)
    for model in registration["models"]:
        if package_snapshot(Path(model["package"]), "native") != model["package_sha256"]:
            raise ValueError("Registered model package changed")
        if json.loads((Path(model["package"]) / "manifest.json").read_text())["run_seed"] != model["training_seed"]:
            raise ValueError("Registered independent training seed differs from model manifest")
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "registration.json", registration)
    report = {"kind": "preregistered-native-heldout-evaluation", "status": "preflight", "source": source_identity(),
        "registration": str(path), "registration_sha256": registration_hash, "split": "final-evaluation",
        "final_evaluation_accessed": False, "episodes": [],
        "claim": "Held out from this development campaign; fixed models and criteria. Two reserved V1 maps do not establish broad OpenTTD competence.",
        "uncertainty_scope": "Three training seeds conditional on the two fixed final maps and common sampling seeds; imprecise, not 18 independent models."}
    write_json(root / "run.json", report)
    try:
        capture_source(root / "source")
        # Final-scenario access occurs only after every
        # registered model, executable and evaluation-code identity is verified.
        report.update(status="running", final_evaluation_accessed=True)
        write_json(root / "run.json", report)
        templates = [Path(registration["instance_dir"]) / (name + ".json") for name in registration["protocol"]["template_ids"]]
        scenarios = [json.loads(template.read_text()) for template in templates]
        if any(scenario["split"] != "final-evaluation" or scenario["template_id"] != template.stem
               for template, scenario in zip(templates, scenarios, strict=True)):
            raise ValueError("Registered final scenario identities differ")
        report["template_sha256"] = {str(template): digest(template) for template in templates}
        reward = validate_m06_reward_contract.validate(ROOT / "config/v1/m06-reward-trajectory-contract.json",
            ROOT / "docs/project/schema/v1-m06-reward-trajectory-contract.schema.json")
        bridge_validation.configure("fast")
        cases = [(None, policy) for policy in registration["protocol"]["baselines"]]
        cases += [(model, policy) for model in registration["models"] for policy in ("sampled", "greedy")]
        for model, policy in cases:
            for template in templates:
                seeds = registration["protocol"]["sampling_seeds"] if policy in ("random", "sampled") else [20260923]
                for seed in seeds:
                    label = ("model-" + str(model["training_seed"])) if model else "baseline"
                    output = root / f"{label}-{policy}-{template.stem}-s{seed}"
                    row = episode(engine=engine, template=template, output=output, reward=reward,
                        policy=policy, seed=seed, evaluator=evaluator if model else None,
                        package=Path(model["package"]) if model else None, evaluation_split="final-evaluation")
                    row["training_seed"] = model["training_seed"] if model else None
                    report["episodes"].append(row)
                    write_json(root / "run.json", report)
        report.update(summaries_and_criteria(report["episodes"], registration), status="completed")
    except BaseException as exc:
        report.update(status="failed", error=str(exc))
        raise
    finally:
        write_json(root / "run.json", report)
    print(json.dumps({key: report[key] for key in ("status", "acceptance_passed", "acceptance_checks", "summaries")}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("registration", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
